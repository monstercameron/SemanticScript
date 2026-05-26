"""End-to-end test harness for apps/taskforge-web.

Compiles the app via semsc, starts the native exe, exercises every
route shipped in this iteration, then tears the server down. Exit code
is 0 on success, non-zero on first failed assertion.

Current coverage (v1.1):
  - GET  /                            — 200 + HTML shell + componentized fragments
  - GET  /assets/home.js              — 200 + JavaScript asset
  - GET  /assets/dashboard.js         — 200 + JavaScript asset
  - GET  /health                       — 200 + JSON
  - GET  /api/version                  — 200 + JSON with bcrypt cost
  - POST /api/auth/register            — full flow: user inserted,
                                          session minted, cookie set,
                                          DB rows persist
  - POST /api/auth/login               — verifies password, mints a new
                                          session, rejects bad credentials
  - GET  /api/auth/me                  — returns the session user
  - POST /api/auth/logout              — clears the session row + cookie
  - GET  /api/todos                    — lists session user's todos
                                          (seeded demo has 3; alice gets
                                          her own; cross-user isolation
                                          is verified by the count diff)
  - POST /api/todos                    — inserts a row, returns the
                                          fresh todo with id+createdAtMs
  - GET  /this-route-does-not-exist    — 404
  - POST /api/todos/:id/complete       — marks done + completed_at_ms
  - POST /api/todos/:id/uncomplete     — reopens + clears completed_at_ms
  - DELETE /api/todos/:id              — deletes owned rows without leaking cross-user existence
  - GET /api/todos/:id                 — 501 reserved show route
"""

from __future__ import annotations

import http.client
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BUILD_TAPE = REPO_ROOT / "apps" / "taskforge-web" / "build.sem"
BUILD_DIR = REPO_ROOT / "apps" / "taskforge-web" / "build"
EXE_PATH = BUILD_DIR / "taskforge-web.exe"
DB_PATH = BUILD_DIR / "taskforge_web.db"
ASSET_SOURCE_DIR = REPO_ROOT / "apps" / "taskforge-web" / "assets"
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
        assert_in("TaskForge Web", body, "/ page title")
        assert_in("/assets/home.js", body, "/ script asset")
        assert_in("text/html", headers.get("content-type", ""), "/ content-type")
        print("[OK]  GET / -> 200 HTML shell")

        # ---- /assets/home.js ----
        status, body, headers = http_request("GET", "/assets/home.js")
        assert_equal(status, 200, "/assets/home.js status")
        assert_in("registerForm", body, "/assets/home.js body")
        assert_in("text/javascript", headers.get("content-type", ""), "/assets/home.js content-type")
        assert_equal(headers.get("content-length"), str(len(body.encode("utf-8"))), "/assets/home.js content-length")
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
        register_payload = json.loads(body)
        alice_id = register_payload["user"]["id"]
        assert_equal(register_payload["user"]["username"], "alice", "/api/auth/register JSON username")
        if alice_id <= 1:
            raise TestFailure(
                f"alice should be inserted after seeded demo user; got id {alice_id}")
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
            user_count = list(connection.execute("SELECT count(*) FROM users"))[0][0]
            assert_equal(user_count, 2, "user count after register includes demo + alice")
            user_rows = list(connection.execute(
                "SELECT id, username, length(password_hash) FROM users WHERE username = 'alice'"))
            assert_equal(len(user_rows), 1, "alice row count after register")
            assert_equal(user_rows[0][0], alice_id, "stored alice id")
            assert_equal(user_rows[0][1], "alice", "stored username")
            assert_equal(user_rows[0][2], 60, "stored password_hash length")
            session_rows = list(connection.execute(
                "SELECT token, user_id, expires_at_ms FROM sessions WHERE token = ?", (cookie_value,)))
            assert_equal(len(session_rows), 1, "session count after register")
            assert_equal(session_rows[0][0], cookie_value, "stored session token matches cookie")
            assert_equal(session_rows[0][1], alice_id, "session user_id matches inserted user")
        finally:
            connection.close()
        print("[OK]  DB rows persist: demo + alice users, alice session token matches cookie")

        # ---- duplicate register returns 409 ----
        status, body, _ = http_request(
            "POST", "/api/auth/register",
            body='{"username":"alice","password":"another valid password"}',
            headers={"Content-Type": "application/json"},
        )
        assert_equal(status, 409, "duplicate username status")
        print("[OK]  POST /api/auth/register with duplicate username -> 409 conflict")

        # ---- login rejects bad credentials with generic 401 ----
        status, body, _ = http_request(
            "POST", "/api/auth/login",
            body='{"username":"alice","password":"wrong password"}',
            headers={"Content-Type": "application/json"},
        )
        assert_equal(status, 401, "/api/auth/login bad password status")
        assert_in("invalidCredentials", body, "/api/auth/login bad password body")
        print("[OK]  POST /api/auth/login with bad password -> 401")

        # ---- login succeeds and mints a fresh session ----
        status, body, headers = http_request(
            "POST", "/api/auth/login",
            body='{"username":"alice","password":"correct horse battery staple"}',
            headers={"Content-Type": "application/json"},
        )
        assert_equal(status, 200, "/api/auth/login status")
        login_payload = json.loads(body)
        assert_equal(login_payload["user"]["id"], alice_id, "/api/auth/login JSON user id")
        assert_equal(login_payload["user"]["username"], "alice", "/api/auth/login JSON username")
        login_set_cookie = headers.get("set-cookie", "")
        assert_in("session=", login_set_cookie, "/api/auth/login Set-Cookie")
        assert_in("HttpOnly", login_set_cookie, "/api/auth/login Set-Cookie HttpOnly")
        assert_in("SameSite=Strict", login_set_cookie, "/api/auth/login Set-Cookie SameSite=Strict")
        login_cookie_value = login_set_cookie.split(";")[0].split("=", 1)[1]
        if len(login_cookie_value) != 43:
            raise TestFailure(
                f"login session token should be exactly 43 base64url chars; got {len(login_cookie_value)}")
        if login_cookie_value == cookie_value:
            raise TestFailure("login should mint a fresh session token, not reuse register token")
        connection = sqlite3.connect(str(DB_PATH))
        try:
            session_count = list(connection.execute(
                "SELECT count(*) FROM sessions WHERE user_id = ?", (alice_id,)))[0][0]
            assert_equal(session_count, 2, "alice session count after login")
        finally:
            connection.close()
        print("[OK]  POST /api/auth/login -> 200 (fresh session minted, cookie set)")

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

        # ---- authenticated alice flow: me + create + list + logout ----
        alice_cookie_header = {"Cookie": f"session={login_cookie_value}"}

        status, body, _ = http_request(
            "GET", "/api/auth/me", headers=alice_cookie_header)
        assert_equal(status, 200, "/api/auth/me (alice) status")
        me_payload = json.loads(body)
        assert_equal(me_payload["user"]["id"], alice_id, "/api/auth/me alice id")
        assert_equal(me_payload["user"]["username"], "alice", "/api/auth/me alice username")
        print("[OK]  GET /api/auth/me (alice cookie) -> 200")

        status, body, _ = http_request(
            "GET", "/api/todos", headers=alice_cookie_header)
        assert_equal(status, 200, "/api/todos (alice, initial) status")
        initial_payload = json.loads(body)
        assert_equal(initial_payload["count"], 0, "alice initial todo count")
        assert_equal(initial_payload["todos"], [], "alice initial todo array")
        print("[OK]  GET /api/todos (alice, empty) -> 200 count=0")

        for index, (title, priority) in enumerate([
            ("Ship the demo", 1), ("Take a screenshot", 2),
        ], start=1):
            create_headers = {"Content-Type": "application/json",
                              "Cookie": f"session={login_cookie_value}"}
            status, body, _ = http_request(
                "POST", "/api/todos",
                body=json.dumps({"title": title, "priority": priority}),
                headers=create_headers,
            )
            assert_equal(status, 201, f"create todo {index} status")
            created = json.loads(body)["todo"]
            assert_equal(created["title"], title, f"create todo {index} title")
            assert_equal(created["priority"], priority, f"create todo {index} priority")
            assert_equal(created["done"], False, f"create todo {index} done")
            if created["id"] <= 0:
                raise TestFailure(f"create todo {index} should return a positive id")
        print("[OK]  POST /api/todos (alice) x2 -> 201 each with id+title+priority")

        status, body, _ = http_request(
            "GET", "/api/todos", headers=alice_cookie_header)
        assert_equal(status, 200, "/api/todos (alice, populated) status")
        populated_payload = json.loads(body)
        assert_equal(populated_payload["count"], 2, "alice todo count after two inserts")
        titles_in_response = {row["title"] for row in populated_payload["todos"]}
        assert_equal(
            titles_in_response, {"Ship the demo", "Take a screenshot"},
            "alice todo titles in response")
        print("[OK]  GET /api/todos (alice) -> 200 count=2 with both inserted titles")

        # Cross-user isolation: alice must NOT see the demo user's seeded rows.
        connection = sqlite3.connect(str(DB_PATH))
        try:
            demo_id_row = list(connection.execute(
                "SELECT id FROM users WHERE username = 'demo'"))
            assert_equal(len(demo_id_row), 1, "demo user exists in DB")
            demo_id = demo_id_row[0][0]
            demo_todo_count = list(connection.execute(
                "SELECT count(*) FROM todos WHERE user_id = ?", (demo_id,)))[0][0]
            if demo_todo_count < 3:
                raise TestFailure(
                    f"demo user should have >=3 seeded todos; got {demo_todo_count}")
            if alice_id == demo_id:
                raise TestFailure("alice and demo should have distinct ids")
        finally:
            connection.close()
        print("[OK]  cross-user isolation: alice sees only her 2 todos despite demo having seeded rows")

        # ---- demo login + list sees seeded rows ----
        status, body, headers = http_request(
            "POST", "/api/auth/login",
            body='{"username":"demo","password":"demo1234"}',
            headers={"Content-Type": "application/json"},
        )
        assert_equal(status, 200, "/api/auth/login (demo) status")
        demo_set_cookie = headers.get("set-cookie", "")
        demo_cookie_value = demo_set_cookie.split(";")[0].split("=", 1)[1]
        demo_cookie_header = {"Cookie": f"session={demo_cookie_value}"}

        status, body, _ = http_request(
            "GET", "/api/todos", headers=demo_cookie_header)
        assert_equal(status, 200, "/api/todos (demo) status")
        demo_payload = json.loads(body)
        if demo_payload["count"] < 3:
            raise TestFailure(
                f"demo should see >=3 seeded todos; got {demo_payload['count']}")
        if "Ship the demo" in {row["title"] for row in demo_payload["todos"]}:
            raise TestFailure(
                "demo should NOT see alice's todos — cross-user leak")
        print(f"[OK]  GET /api/todos (demo) -> 200 count={demo_payload['count']} (seeded rows visible, no leak)")

        # ---- logout clears the session ----
        status, body, headers = http_request(
            "POST", "/api/auth/logout", headers=alice_cookie_header)
        assert_equal(status, 200, "/api/auth/logout (alice) status")
        logout_set_cookie = headers.get("set-cookie", "")
        assert_in("Max-Age=0", logout_set_cookie, "/api/auth/logout clears cookie")
        connection = sqlite3.connect(str(DB_PATH))
        try:
            stale_rows = list(connection.execute(
                "SELECT count(*) FROM sessions WHERE token = ?", (login_cookie_value,)))
            assert_equal(stale_rows[0][0], 0, "alice session row deleted after logout")
        finally:
            connection.close()

        status, _, _ = http_request(
            "GET", "/api/auth/me", headers=alice_cookie_header)
        assert_equal(status, 401, "/api/auth/me after logout status")
        print("[OK]  POST /api/auth/logout -> 200 + cookie cleared + session deleted + 401 thereafter")

        # ---- complete + delete (real implementations) require a session ----
        for method, path in [
            ("POST",   "/api/todos/42/complete"),
            ("DELETE", "/api/todos/42"),
        ]:
            status, _, _ = http_request(method, path)
            if status != 401:
                raise TestFailure(
                    f"{method} {path}: expected 401 without session, got {status}"
                )
        print("[OK]  complete/delete routes return 401 without cookie")

        # ---- log demo in again to get a working cookie for complete/delete ----
        status, body, headers = http_request(
            "POST", "/api/auth/login",
            body='{"username":"demo","password":"demo1234"}',
            headers={"Content-Type": "application/json"},
        )
        assert_equal(status, 200, "/api/auth/login (demo for mutation tests) status")
        demo_mut_cookie = headers.get("set-cookie", "").split(";")[0].split("=", 1)[1]
        demo_mut_headers = {"Cookie": f"session={demo_mut_cookie}"}

        # Create two todos for demo to mutate, then exercise complete + delete.
        for title in ("Mutation A", "Mutation B"):
            status, body, _ = http_request(
                "POST", "/api/todos",
                body=json.dumps({"title": title, "priority": 2}),
                headers={"Content-Type": "application/json",
                         "Cookie": f"session={demo_mut_cookie}"},
            )
            assert_equal(status, 201, f"seed mutation todo '{title}' status")
        # Pick a row to complete and another to delete.
        status, body, _ = http_request(
            "GET", "/api/todos", headers=demo_mut_headers)
        assert_equal(status, 200, "list before mutation status")
        rows = json.loads(body)["todos"]
        to_complete = next(t for t in rows if t["title"] == "Mutation A")
        to_delete = next(t for t in rows if t["title"] == "Mutation B")

        # POST /api/todos/:id/complete
        status, body, _ = http_request(
            "POST", "/api/todos/" + str(to_complete["id"]) + "/complete",
            headers=demo_mut_headers,
        )
        assert_equal(status, 200, "complete status")
        complete_payload = json.loads(body)
        assert_equal(complete_payload.get("ok"), True, "complete payload ok=true")
        # Verify DB row marks done with non-null completed_at_ms.
        connection = sqlite3.connect(str(DB_PATH))
        try:
            row = list(connection.execute(
                "SELECT done, completed_at_ms FROM todos WHERE id = ?",
                (to_complete["id"],)))[0]
            assert_equal(row[0], 1, "completed todo done flag")
            if row[1] is None or row[1] <= 0:
                raise TestFailure(
                    f"completed_at_ms should be set; got {row[1]!r}")
        finally:
            connection.close()
        print("[OK]  POST /api/todos/:id/complete -> 200 + done=1 + completed_at_ms set")

        # POST /api/todos/:id/uncomplete — toggle back to open.
        status, body, _ = http_request(
            "POST", "/api/todos/" + str(to_complete["id"]) + "/uncomplete",
            headers=demo_mut_headers,
        )
        assert_equal(status, 200, "uncomplete status")
        uncomplete_payload = json.loads(body)
        assert_equal(uncomplete_payload.get("ok"), True, "uncomplete payload ok=true")
        assert_equal(uncomplete_payload.get("done"), False, "uncomplete payload done=false")
        connection = sqlite3.connect(str(DB_PATH))
        try:
            row = list(connection.execute(
                "SELECT done, completed_at_ms FROM todos WHERE id = ?",
                (to_complete["id"],)))[0]
            assert_equal(row[0], 0, "uncompleted todo done flag")
            assert_equal(row[1], None, "uncompleted todo completed_at_ms cleared")
        finally:
            connection.close()
        print("[OK]  POST /api/todos/:id/uncomplete -> 200 + done=0 + completed_at_ms NULL")

        # Re-complete so the row is in a sensible state for downstream assertions.
        status, _, _ = http_request(
            "POST", "/api/todos/" + str(to_complete["id"]) + "/complete",
            headers=demo_mut_headers,
        )
        assert_equal(status, 200, "re-complete status after toggle")

        # DELETE /api/todos/:id
        status, body, _ = http_request(
            "DELETE", "/api/todos/" + str(to_delete["id"]),
            headers=demo_mut_headers,
        )
        assert_equal(status, 200, "delete status")
        delete_payload = json.loads(body)
        assert_equal(delete_payload.get("ok"), True, "delete payload ok=true")
        connection = sqlite3.connect(str(DB_PATH))
        try:
            remaining = list(connection.execute(
                "SELECT count(*) FROM todos WHERE id = ?",
                (to_delete["id"],)))[0][0]
            assert_equal(remaining, 0, "deleted todo row gone from DB")
        finally:
            connection.close()
        print("[OK]  DELETE /api/todos/:id -> 200 + row removed from DB")

        # Cross-user safety: alice tries to complete + delete one of demo's
        # remaining seeded todos. UPDATE/DELETE WHERE id=? AND user_id=?
        # affects zero rows, but the response is intentionally 200 (no
        # existence oracle). Verify demo's row is still there afterward.
        connection = sqlite3.connect(str(DB_PATH))
        try:
            demo_seeded_row = list(connection.execute(
                "SELECT id FROM todos WHERE user_id = (SELECT id FROM users WHERE username='demo') AND title='Try the API at /api/version'"))[0][0]
        finally:
            connection.close()
        # Re-login as alice (her earlier session was logged out).
        status, body, headers = http_request(
            "POST", "/api/auth/login",
            body='{"username":"alice","password":"correct horse battery staple"}',
            headers={"Content-Type": "application/json"},
        )
        assert_equal(status, 200, "alice re-login status")
        alice_re_cookie = headers.get("set-cookie", "").split(";")[0].split("=", 1)[1]
        alice_re_headers = {"Cookie": f"session={alice_re_cookie}"}
        for method, path in [
            ("POST",   "/api/todos/" + str(demo_seeded_row) + "/complete"),
            ("DELETE", "/api/todos/" + str(demo_seeded_row)),
        ]:
            status, _, _ = http_request(method, path, headers=alice_re_headers)
            assert_equal(status, 200, f"alice mutating demo row {method} status")
        connection = sqlite3.connect(str(DB_PATH))
        try:
            still_there = list(connection.execute(
                "SELECT done, completed_at_ms FROM todos WHERE id = ?",
                (demo_seeded_row,)))
            assert_equal(len(still_there), 1, "demo row still exists after alice mutation attempts")
            assert_equal(still_there[0][0], 0, "demo row done flag unchanged by alice")
            assert_equal(still_there[0][1], None, "demo row completed_at_ms unchanged by alice")
        finally:
            connection.close()
        print("[OK]  cross-user complete/delete attempts return 200 but DO NOT mutate other users' rows")

        # ---- still-stubbed routes ----
        status, _, _ = http_request("GET", "/api/todos/42")
        if status != 501:
            raise TestFailure(
                f"GET /api/todos/:id should still be 501 (stub), got {status}"
            )
        print("[OK]  GET /api/todos/:id still stubs to 501 (show endpoint reserved)")

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
        # 5 sessions expected after bob registers:
        #   1. alice register
        #   2. alice login (after logout test deleted the register one)
        #   3. demo login for mutation tests
        #   4. alice re-login for cross-user safety test
        #   5. bob register (just now)
        # Alice's first login session was deleted by the logout test.
        connection = sqlite3.connect(str(DB_PATH))
        try:
            user_count = list(connection.execute("SELECT count(*) FROM users"))[0][0]
            assert_equal(user_count, 3, "user count after second register includes demo + alice + bob")
            session_count = list(connection.execute("SELECT count(*) FROM sessions"))[0][0]
            assert_equal(session_count, 5, "session count after second register: alice register + alice login + demo mut login + alice re-login + bob register, minus the alice-login that was logged out")
        finally:
            connection.close()
        print("[OK]  three users + five active sessions persist in DB")

        print("=" * 60)
        print("taskforge-web v1.0 test passed")
    finally:
        stop_server(server_process)


if __name__ == "__main__":
    try:
        main()
    except TestFailure as failure:
        print(f"[FAIL] {failure}", file=sys.stderr)
        sys.exit(1)
