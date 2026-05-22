from __future__ import annotations

import argparse
import json
import mimetypes
import posixpath
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def _json_bytes(payload: dict) -> bytes:
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


def _safe_static_path(static_root: Path, request_path: str) -> Path | None:
    parsed_path = urlsplit(request_path).path
    normalized = posixpath.normpath(parsed_path)
    if normalized.startswith("../") or normalized == "..":
        return None
    if normalized == "/":
        normalized = "/index.html"
    local = (static_root / normalized.lstrip("/")).resolve()
    try:
        local.relative_to(static_root)
    except ValueError:
        return None
    return local


def _forwardable_request_headers(headers) -> dict[str, str]:
    forwarded: dict[str, str] = {}
    for name, value in headers.items():
        lower = name.lower()
        if lower in HOP_BY_HOP_HEADERS or lower == "host":
            continue
        forwarded[name] = value
    return forwarded


def _forwardable_response_headers(headers) -> Iterable[tuple[str, str]]:
    for name, value in headers.items():
        lower = name.lower()
        if lower in HOP_BY_HOP_HEADERS or lower in {"content-length", "server", "date"}:
            continue
        yield name, value


def make_handler(static_root: Path, api_origin: str):
    static_root = static_root.resolve()
    api_origin = api_origin.rstrip("/") + "/"

    class TaskForgeApiClientHandler(BaseHTTPRequestHandler):
        server_version = "TaskForgeApiClient/0.1"

        def log_message(self, fmt: str, *args) -> None:
            sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))

        def do_GET(self) -> None:
            if self.path == "/__client_health":
                self._send_json(200, {"ok": True, "apiOrigin": api_origin.rstrip("/")})
                return
            if self.path.startswith("/api/"):
                self._proxy_api()
                return
            self._serve_static()

        def do_POST(self) -> None:
            if self.path.startswith("/api/"):
                self._proxy_api()
                return
            self._send_json(405, {"error": {"code": "methodNotAllowed", "message": "method not allowed"}})

        def do_DELETE(self) -> None:
            if self.path.startswith("/api/"):
                self._proxy_api()
                return
            self._send_json(405, {"error": {"code": "methodNotAllowed", "message": "method not allowed"}})

        def do_OPTIONS(self) -> None:
            if self.path.startswith("/api/"):
                self._proxy_api()
                return
            self.send_response(204)
            self.send_header("Allow", "GET, POST, DELETE, OPTIONS")
            self.end_headers()

        def _send_json(self, status: int, payload: dict) -> None:
            body = _json_bytes(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_static(self) -> None:
            path = _safe_static_path(static_root, self.path)
            if path is None or not path.is_file():
                self._send_json(404, {"error": {"code": "notFound", "message": "asset not found"}})
                return

            content = path.read_bytes()
            content_type, _ = mimetypes.guess_type(str(path))
            if content_type is None:
                content_type = "application/octet-stream"
            if path.suffix == ".js":
                content_type = "text/javascript"
            elif path.suffix == ".css":
                content_type = "text/css"

            self.send_response(200)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content)

        def _proxy_api(self) -> None:
            upstream_url = urljoin(api_origin, self.path.lstrip("/"))
            content_length = int(self.headers.get("Content-Length") or "0")
            body = self.rfile.read(content_length) if content_length else None
            request = Request(
                upstream_url,
                data=body,
                headers=_forwardable_request_headers(self.headers),
                method=self.command,
            )

            try:
                with urlopen(request, timeout=20) as response:
                    response_body = response.read()
                    self.send_response(response.status)
                    self._copy_response_headers(response.headers, response_body)
                    self.end_headers()
                    self.wfile.write(response_body)
            except HTTPError as error:
                response_body = error.read()
                self.send_response(error.code)
                self._copy_response_headers(error.headers, response_body)
                self.end_headers()
                self.wfile.write(response_body)
            except URLError as error:
                reason = getattr(error, "reason", error)
                self._send_json(
                    502,
                    {
                        "error": {
                            "code": "apiUnavailable",
                            "message": "could not reach TaskForge API",
                            "detail": str(reason),
                        }
                    },
                )

        def _copy_response_headers(self, headers, response_body: bytes) -> None:
            set_cookies = headers.get_all("Set-Cookie") if hasattr(headers, "get_all") else []
            for name, value in _forwardable_response_headers(headers):
                if name.lower() == "set-cookie":
                    continue
                self.send_header(name, value)
            for cookie in set_cookies or []:
                self.send_header("Set-Cookie", cookie)
            self.send_header("Content-Length", str(len(response_body)))
            self.send_header("Cache-Control", "no-store")

    return TaskForgeApiClientHandler


def create_server(host: str, port: int, api_origin: str, static_root: Path) -> ThreadingHTTPServer:
    handler = make_handler(static_root=static_root, api_origin=api_origin)
    return ThreadingHTTPServer((host, port), handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the TaskForge API todo client.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=18120, type=int)
    parser.add_argument("--api-origin", default="http://127.0.0.1:18090")
    parser.add_argument("--static-root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)

    server = create_server(
        host=args.host,
        port=args.port,
        api_origin=args.api_origin,
        static_root=Path(args.static_root),
    )
    print(f"TaskForge API client: http://{args.host}:{args.port}")
    print(f"Proxying /api/* to {args.api_origin.rstrip('/')}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
