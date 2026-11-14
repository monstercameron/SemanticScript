from __future__ import annotations

import http.cookiejar
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

import dev_proxy


APP_ROOT = Path(__file__).resolve().parents[1]


class FakeTaskForgeHandler(BaseHTTPRequestHandler):
    todos = [
        {"id": 1, "title": "Try the API at /api/version", "body": "", "priority": 2, "done": 0},
        {"id": 2, "title": "Ship the client app", "body": "Fetched through proxy", "priority": 1, "done": 0},
    ]
    next_id = 3
    last_cookie_header = ""

    def log_message(self, fmt: str, *args) -> None:
        return

    def _read_json(self) -> dict:
        size = int(self.headers.get("Content-Length") or "0")
        if size <= 0:
            return {}
        return json.loads(self.rfile.read(size).decode("utf-8"))

    def _send(self, status: int, payload: dict, cookie: str | None = None) -> None:
        body = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        self.__class__.last_cookie_header = self.headers.get("Cookie", "")
        return "session=fake-session" in self.__class__.last_cookie_header

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/version":
            self._send(200, {"app": "TaskForge", "version": "test"})
            return
        if path == "/api/malicious-headers":
            body = b'{"ok":true}\n'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Upstream-Trace", "should-not-forward")
            self.send_header("Set-Cookie", "evil=attacker; Path=/; HttpOnly")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/auth/me":
            if not self._authorized():
                self._send(401, {"error": {"code": "unauthorized"}})
                return
            self._send(200, {"user": {"id": 1, "username": "demo", "displayName": "Demo"}})
            return
        if path == "/api/todos":
            if not self._authorized():
                self._send(401, {"error": {"code": "unauthorized"}})
                return
            self._send(200, {"todos": self.todos, "count": len(self.todos)})
            return
        self._send(404, {"error": {"code": "notFound"}})

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/auth/login":
            payload = self._read_json()
            if payload.get("username") == "demo" and payload.get("password") == "demo1234":
                self._send(
                    200,
                    {"user": {"id": 1, "username": "demo", "displayName": "Demo"}},
                    "session=fake-session; Path=/; HttpOnly; SameSite=Strict",
                )
                return
            self._send(401, {"error": {"code": "invalidCredentials"}})
            return
        if path == "/api/todos":
            if not self._authorized():
                self._send(401, {"error": {"code": "unauthorized"}})
                return
            payload = self._read_json()
            todo = {
                "id": self.next_id,
                "title": payload["title"],
                "body": payload.get("body", ""),
                "priority": int(payload.get("priority", 2)),
                "done": 0,
            }
            self.__class__.next_id += 1
            self.todos.append(todo)
            self._send(201, {"todo": todo})
            return
        if path.endswith("/complete") or path.endswith("/uncomplete"):
            if not self._authorized():
                self._send(401, {"error": {"code": "unauthorized"}})
                return
            parts = path.split("/")
            todo_id = int(parts[3])
            done = 1 if parts[4] == "complete" else 0
            for todo in self.todos:
                if todo["id"] == todo_id:
                    todo["done"] = done
            self._send(200, {"ok": True})
            return
        self._send(404, {"error": {"code": "notFound"}})

    def do_DELETE(self) -> None:
        path = urlsplit(self.path).path
        if path.startswith("/api/todos/"):
            if not self._authorized():
                self._send(401, {"error": {"code": "unauthorized"}})
                return
            todo_id = int(path.rsplit("/", 1)[1])
            self.__class__.todos = [todo for todo in self.todos if todo["id"] != todo_id]
            self._send(200, {"ok": True})
            return
        self._send(404, {"error": {"code": "notFound"}})


def start_server(server: ThreadingHTTPServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


class TaskForgeApiClientTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeTaskForgeHandler.todos = [
            {"id": 1, "title": "Try the API at /api/version", "body": "", "priority": 2, "done": 0},
            {"id": 2, "title": "Ship the client app", "body": "Fetched through proxy", "priority": 1, "done": 0},
        ]
        FakeTaskForgeHandler.next_id = 3
        FakeTaskForgeHandler.last_cookie_header = ""
        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), FakeTaskForgeHandler)
        start_server(self.upstream)
        api_origin = f"http://127.0.0.1:{self.upstream.server_address[1]}"
        self.proxy = dev_proxy.create_server("127.0.0.1", 0, api_origin, APP_ROOT)
        start_server(self.proxy)
        self.base = f"http://127.0.0.1:{self.proxy.server_address[1]}"
        self.cookiejar = http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookiejar))

    def tearDown(self) -> None:
        self.proxy.shutdown()
        self.proxy.server_close()
        self.upstream.shutdown()
        self.upstream.server_close()

    def request(self, method: str, path: str, payload: dict | None = None):
        body = None
        headers = {}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(self.base + path, data=body, headers=headers, method=method)
        try:
            response = self.opener.open(request, timeout=10)
        except HTTPError as error:
            response = error
        data = response.read()
        parsed = json.loads(data.decode("utf-8")) if data else None
        return response.status, parsed

    def request_text(self, path: str):
        response = self.opener.open(Request(self.base + path, method="GET"), timeout=10)
        return response.status, response.read().decode("utf-8")

    def test_static_assets_and_proxy_flow(self) -> None:
        index_status, index_body = self.request_text("/")
        self.assertEqual(index_status, 200)
        self.assertIn("TaskForge Todos", index_body)

        health_status, health_body = self.request("GET", "/__client_health")
        self.assertEqual(health_status, 200)
        self.assertTrue(health_body["ok"])

        status, payload = self.request("GET", "/api/version")
        self.assertEqual(status, 200)
        self.assertEqual(payload["app"], "TaskForge")

        status, payload = self.request("GET", "/api/todos")
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"]["code"], "unauthorized")

        status, payload = self.request("POST", "/api/auth/login", {"username": "demo", "password": "demo1234"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["user"]["username"], "demo")
        cookie_names = {cookie.name for cookie in self.cookiejar}
        self.assertIn(dev_proxy.PROXY_SESSION_COOKIE_NAME, cookie_names)
        self.assertNotIn("session", cookie_names)

        status, payload = self.request("GET", "/api/todos")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 2)
        self.assertEqual(FakeTaskForgeHandler.last_cookie_header, "session=fake-session")

        status, payload = self.request("POST", "/api/todos", {"title": "Write client tests", "priority": 2})
        self.assertEqual(status, 201)
        created_id = payload["todo"]["id"]

        status, _ = self.request("POST", f"/api/todos/{created_id}/complete")
        self.assertEqual(status, 200)

        status, payload = self.request("GET", "/api/todos")
        self.assertEqual(status, 200)
        created = next(todo for todo in payload["todos"] if todo["id"] == created_id)
        self.assertEqual(created["done"], 1)

        status, _ = self.request("DELETE", f"/api/todos/{created_id}")
        self.assertEqual(status, 200)

        status, payload = self.request("GET", "/api/todos")
        self.assertEqual(status, 200)
        self.assertNotIn(created_id, {todo["id"] for todo in payload["todos"]})

    def test_client_uses_relative_api_paths(self) -> None:
        app_js = (APP_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('"/api/todos"', app_js)
        self.assertNotIn("127.0.0.1:18090", app_js)

    def test_static_paths_reject_relative_segments(self) -> None:
        self.assertIsNone(dev_proxy._safe_static_path(APP_ROOT, "/../scripts/dev_proxy.py"))
        self.assertIsNone(dev_proxy._safe_static_path(APP_ROOT, "/%2e%2e/scripts/dev_proxy.py"))

    def test_api_origin_must_be_loopback(self) -> None:
        with self.assertRaises(ValueError):
            dev_proxy.make_handler(APP_ROOT, "http://example.com:18090")

    def test_forwarded_headers_reject_line_breaks(self) -> None:
        self.assertIsNone(dev_proxy._safe_header_pair("X-Test", "ok\r\nX-Injected: yes"))
        self.assertIsNone(dev_proxy._safe_header_pair("X-Test\nInjected", "ok"))
        self.assertIsNone(dev_proxy._upstream_session_from_set_cookie("session=bad\r\nX-Injected: yes"))

    def test_proxy_does_not_forward_upstream_headers_or_non_session_cookies(self) -> None:
        request = Request(self.base + "/api/malicious-headers", method="GET")
        response = self.opener.open(request, timeout=10)
        response.read()
        self.assertIsNone(response.headers.get("X-Upstream-Trace"))
        cookie_names = {cookie.name for cookie in self.cookiejar}
        self.assertNotIn("evil", cookie_names)


if __name__ == "__main__":
    unittest.main()
