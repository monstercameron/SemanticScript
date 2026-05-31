#!/usr/bin/env python3
"""End-to-end app runner (APP-RUN wave).

Each entry JIT-runs one apps/<name> project through the compiler and asserts it
produces real output / behavior — proving the app actually *runs*, not just that
it lints. Apps are added here as their runtime/codegen lands (see docs/todos.md
APP-RUN-0..6). Exit 0 iff every registered app behaves as expected.

Separate from run_examples (single-file examples/) and the protocol-level
integration tests (test_http_server/gui/wasm/dom).
"""
import http.server
import os
import socketserver
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))          # tests/
ROOT = os.path.dirname(HERE)                               # repo root
SEMANTICSCRIPT = os.path.join(ROOT, "semanticscript", "compiler", "semanticscript.py")


class _Router(http.server.BaseHTTPRequestHandler):
    routes = {}

    def do_GET(self):
        body = self.routes.get(self.path, b"not-found")
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Type", "text/plain")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def _serving(port, routes):
    """Context-manager-ish: returns a TCPServer serving `routes` on a daemon
    thread; caller must .shutdown() it."""
    handler = type("H", (_Router,), {"routes": routes})
    srv = socketserver.TCPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _run_console(app, must_contain, stdin=None):
    """Run a console app to completion; return (ok, detail)."""
    proc = subprocess.run(
        [sys.executable, SEMANTICSCRIPT, "run", os.path.join("apps", app)],
        capture_output=True, text=True, cwd=ROOT, input=stdin, timeout=120,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return False, "exit=%d: %s" % (proc.returncode, out.strip()[-160:])
    missing = [s for s in must_contain if s not in out]
    if missing:
        return False, "output missing %r" % missing[:3]
    return True, "exit=0, %d expected markers present" % len(must_contain)


# Console apps: (name, [substrings that must appear in output], optional stdin).
CONSOLE_APPS = [
    ("html-template-lab", [
        "<!doctype html>",
        "TaskForge TUI HTML Template Lab",
        '<ol class="todo-list">',
        "Wire native webserver",
        "</html>",
    ], None),
    ("event-stream-smoke", [
        "listener-one handled smoke.event.created",
        "listener-two handled smoke.event.created",
    ], None),
]


def _run_server_backed(app, port, routes, must_contain):
    """Stand up a local HTTP server on `port` serving `routes`, run the app
    (which fetches from it), assert its output, then tear the server down."""
    srv = _serving(port, routes)
    try:
        return _run_console(app, must_contain)
    finally:
        srv.shutdown()
        srv.server_close()


# Apps that fetch from a local server: (name, port, {path: body}, [markers]).
SERVER_BACKED_APPS = [
    ("taskforge-api-client", 18090, {
        "/health": b"health-ok-42",
        "/api/version": b"version-0.3.1",
        "/api/todos": b"todos-none-yet",
    }, ["started TaskForge fetches", "health-ok-42", "version-0.3.1", "todos-none-yet"]),
]


def main():
    failures = 0
    total = 0
    for name, markers, stdin in CONSOLE_APPS:
        total += 1
        ok, detail = _run_console(name, markers, stdin)
        print("app %-24s -> %s  (%s)" % (name, "PASS" if ok else "FAIL", detail))
        if not ok:
            failures += 1
    for name, port, routes, markers in SERVER_BACKED_APPS:
        total += 1
        ok, detail = _run_server_backed(name, port, routes, markers)
        print("app %-24s -> %s  (%s)" % (name, "PASS" if ok else "FAIL", detail))
        if not ok:
            failures += 1
    print("---- %d app(s), %d failed ----" % (total, failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
