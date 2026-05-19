"""End-to-end test harness for app/todo-web-pro.

Compiles the app via semsc, starts the native exe, exercises every
route shipped in this iteration, then tears the server down. Exit code
is 0 on success, non-zero on first failed assertion.

Current coverage (v1.0):
  - GET  /                            - 200 + HTML shell
  - GET  /assets/home.js              - 200 + JavaScript asset
  - GET  /health                       — 200 + JSON
  - GET  /api/version                  — 200 + JSON with bcrypt cost
  - POST /api/auth/register            — full flow: user inserted,
                                          session minted, cookie set,
                                          DB rows persist
  - GET  /this-route-does-not-exist    — 404
  - POST /api/auth/login               — 501 (v1.1 follow-up)
  - GET/DELETE /api/todos/:id          — 501 (v1.1 follow-up)
  - POST /api/todos/:id/complete       — 501 (v1.1 follow-up)

Session-validating routes (GET /api/auth/me, GET /api/todos, POST
/api/todos, POST /api/auth/logout) are wired through the full
implementation chain but the session lookup needs follow-up debugging
(see README.md). They are checked here for the "401 without session"
contract.
"""

from __future__ import annotations

import http.client
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BUILD_TAPE = REPO_ROOT / "app" / "todo-web-pro" / "build.sem"
BUILD_DIR = REPO_ROOT / "app" / "todo-web-pro" / "build"
EXE_PATH = BUILD_DIR / "todo_web_pro.exe"
DB_PATH = BUILD_DIR / "todo_web_pro.db"
ASSET_SOURCE_DIR = REPO_ROOT / "app" / "todo-web-pro" / "assets"
BUILD_ASSET_DIR = BUILD_DIR / "assets"
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 18090
READY_DEADLINE_SECONDS = 12.0
REQUEST_TIMEOUT_SECONDS = 5.0


class TestFailure(AssertionError):
    pass


def run_command(args, cwd=None, timeout=None):
    result = subprocess.run(
        args, cwd=cwd or REPO_ROOT,
        text=True, capture_output=True, timeout=timeout,
    )
    if result.returncode != 0:
        raise TestFailure(
            "command failed: {}\nstdout:\n{}\nstderr:\n{}".format(
                " ".join(str(arg) for arg in args),
                result.stdout, result.stderr,
            )
        )
    return result


def http_request(method, path, body=None, headers=None):
    connection = http.client.HTTPConnection(
        SERVER_HOST, SERVER_PORT, timeout=REQUEST_TIMEOUT_SECONDS
    )
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        body_text = response.read().decode("utf-8", errors="replace")
        header_dict = {key.lower(): value for key, value in response.getheaders()}
        return response.status, body_text, header_dict
    finally:
        connection.close()


def wait_for_ready():
    deadline = time.time() + READY_DEADLINE_SECONDS
    last_error = None
    while time.time() < deadline:
        try:
            status, body, _ = http_request("GET", "/health")
            if status == 200 and "ok" in body:
                return
        except (OSError, http.client.HTTPException) as exc:
            last_error = exc
        time.sleep(0.1)
    raise TestFailure(
        f"server did not become ready within {READY_DEADLINE_SECONDS}s; "
        f"last error: {last_error!r}"
    )


def stop_server(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def assert_equal(actual, expected, label):
    if actual != expected:
        raise TestFailure(f"{label}: expected {expected!r}, got {actual!r}")


def assert_in(needle, haystack, label):
    if needle not in haystack:
        raise TestFailure(f"{label}: {needle!r} not found in {haystack!r}")


def main():
    run_command([
        sys.executable, "-m", "SemanticScript.compiler.semsc",
        str(BUILD_TAPE), "--lint", "--parse-only",
    ], timeout=60)
    print("[OK]  lint clean")

    if DB_PATH.exists():
        DB_PATH.unlink()
    run_command([
        sys.executable, "-m", "SemanticScript.compiler.semsc",
        str(BUILD_TAPE), "--emit-exe", "--quiet",
    ], timeout=300)
    if not EXE_PATH.exists():
        raise TestFailure(f"build did not produce {EXE_PATH}")
    print(f"[OK]  build produced {EXE_PATH.name}")

    if BUILD_ASSET_DIR.exists():
        shutil.rmtree(BUILD_ASSET_DIR)
    shutil.copytree(ASSET_SOURCE_DIR, BUILD_ASSET_DIR)
    print("[OK]  copied static assets")

    server_process = subprocess.Popen(
        [str(EXE_PATH)],
        cwd=str(BUILD_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_for_ready()
        print("[OK]  server reachable")

        # ---- / ----
        status, body, headers = http_request("GET", "/")
        assert_equal(status, 200, "/ status")
        assert_in("Todo Web Pro", body, "/ page title")
        assert_in("/assets/home.js", body, "/ script asset")
        assert_in("text/html", headers.get("content-type", ""), "/ content-type")
        print("[OK]  GET / -> 200 HTML shell")

        # ---- /assets/home.js ----
        status, body, headers = http_request("GET", "/assets/home.js")
        assert_equal(status, 200, "/assets/home.js status")
        assert_in("registerForm", body, "/assets/home.js body")
        assert_in("text/javascript", headers.get("content-type", ""), "/assets/home.js content-type")
        print("[OK]  GET /assets/home.js -> 200 script")

        # ---- /health ----
        status, body, headers = http_request("GET", "/health")
        assert_equal(status, 200, "/health status")
        assert_in('"status":"ok"', body, "/health body")
        assert_in("application/json", headers.get("content-type", ""), "/health content-type")
        print(f"[OK]  GET /health -> 200 {body.strip()}")

        # ---- /api/version ----
        status, body, _ = http_request("GET", "/api/version")
        assert_equal(status, 200, "/api/version status")
        assert_in('"bcryptCost":12', body, "/api/version bcrypt cost")
        print(f"[OK]  GET /api/version -> 200 {body.strip()}")

        # ---- /api/auth/register (FULL flow) ----
        status, body, headers = http_request(
            "POST", "/api/auth/register",
            body='{"username":"alice","password":"correct horse battery staple"}',
            headers={"Content-Type": "application/json"},
        )
        assert_equal(status, 201, "/api/auth/register status")
        assert_in('"username":"alice"', body, "/api/auth/register body username")
        assert_in('"id":1', body, "/api/auth/register body user id")
        set_cookie = headers.get("set-cookie", "")
        assert_in("session=", set_cookie, "/api/auth/register Set-Cookie")
        assert_in("HttpOnly", set_cookie, "/api/auth/register Set-Cookie HttpOnly")
        assert_in("SameSite=Strict", set_cookie, "/api/auth/register Set-Cookie SameSite=Strict")
        assert_in("Max-Age=2592000", set_cookie, "/api/auth/register Set-Cookie Max-Age")
        cookie_value = set_cookie.split(";")[0].split("=", 1)[1]
        if len(cookie_value) != 43:
            raise TestFailure(
                f"session token should be exactly 43 base64url chars; got {len(cookie_value)}")
        print(f"[OK]  POST /api/auth/register -> 201 (user inserted, session minted, cookie set)")

        # ---- DB persistence verification ----
        connection = sqlite3.connect(str(DB_PATH))
        try:
            user_rows = list(connection.execute(
                "SELECT id, username, length(password_hash) FROM users"))
            assert_equal(len(user_rows), 1, "user count after register")
            assert_equal(user_rows[0][1], "alice", "stored username")
            assert_equal(user_rows[0][2], 60, "stored password_hash length")
            session_rows = list(connection.execute(
                "SELECT token, user_id, expires_at_ms FROM sessions"))
            assert_equal(len(session_rows), 1, "session count after register")
            assert_equal(session_rows[0][0], cookie_value, "stored session token matches cookie")
            assert_equal(session_rows[0][1], 1, "session user_id matches inserted user")
        finally:
            connection.close()
        print("[OK]  DB rows persist: 1 user (60-char bcrypt hash), 1 session (token matches cookie)")

        # ---- duplicate register returns 409 ----
        status, body, _ = http_request(
            "POST", "/api/auth/register",
            body='{"username":"alice","password":"another"}',
            headers={"Content-Type": "application/json"},
        )
        assert_equal(status, 409, "duplicate username status")
        print("[OK]  POST /api/auth/register with duplicate username -> 409 conflict")

        # ---- 404 for unknown route ----
        status, _, _ = http_request("GET", "/this-route-does-not-exist")
        assert_equal(status, 404, "unknown route status")
        print("[OK]  GET /unknown -> 404")

        # ---- 401 for session-required routes without cookie ----
        for method, path in [
            ("GET",  "/api/auth/me"),
            ("GET",  "/api/todos"),
            ("POST", "/api/todos"),
        ]:
            status, _, _ = http_request(method, path)
            if status != 401:
                raise TestFailure(
                    f"{method} {path}: expected 401 without session, got {status}"
                )
        print("[OK]  session-required routes return 401 without cookie")

        # ---- 501 stubs ----
        for method, path in [
            ("POST", "/api/auth/login"),
            ("GET",  "/api/todos/42"),
            ("DELETE", "/api/todos/42"),
            ("POST", "/api/todos/42/complete"),
        ]:
            status, _, _ = http_request(method, path)
            if status != 501:
                raise TestFailure(
                    f"{method} {path}: expected 501 (stub), got {status}"
                )
        print("[OK]  v1.1 follow-up routes correctly stub to 501")

        # ---- bcrypt cost-12 timing probe (no DB delete — live server) ----
        start_ms = time.time() * 1000.0
        status, _, _ = http_request(
            "POST", "/api/auth/register",
            body='{"username":"bob","password":"timing-check"}',
            headers={"Content-Type": "application/json"},
        )
        elapsed_ms = (time.time() * 1000.0) - start_ms
        if status != 201:
            raise TestFailure(
                f"second-user register expected 201, got {status}")
        if elapsed_ms < 50:
            raise TestFailure(
                f"register completed too quickly ({elapsed_ms:.1f}ms); "
                f"cost-12 bcrypt should add at least ~50ms"
            )
        print(f"[OK]  POST /api/auth/register (bob) -> 201, bcrypt cost-12 elapsed {elapsed_ms:.0f}ms")

        # ---- second user is also a real DB row ----
        connection = sqlite3.connect(str(DB_PATH))
        try:
            user_count = list(connection.execute("SELECT count(*) FROM users"))[0][0]
            assert_equal(user_count, 2, "user count after second register")
            session_count = list(connection.execute("SELECT count(*) FROM sessions"))[0][0]
            assert_equal(session_count, 2, "session count after second register")
        finally:
            connection.close()
        print("[OK]  two users + two sessions persist in DB")

        print("=" * 60)
        print("todo-web-pro v1.0 test passed")
    finally:
        stop_server(server_process)


if __name__ == "__main__":
    try:
        main()
    except TestFailure as failure:
        print(f"[FAIL] {failure}", file=sys.stderr)
        sys.exit(1)
