#!/usr/bin/env python3
"""End-to-end app runner (APP-RUN wave).

Each entry JIT-runs one apps/<name> project through the compiler and asserts it
produces real output / behavior — proving the app actually *runs*, not just that
it lints. Apps are added here as their runtime/codegen lands (see docs/todos.md
APP-RUN-0..6). Exit 0 iff every registered app behaves as expected.

Separate from run_examples (single-file examples/) and the protocol-level
integration tests (test_http_server/gui/wasm/dom).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # tests/
ROOT = os.path.dirname(HERE)                               # repo root
SEMANTICSCRIPT = os.path.join(ROOT, "semanticscript", "compiler", "semanticscript.py")


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
]


def main():
    failures = 0
    for name, markers, stdin in CONSOLE_APPS:
        ok, detail = _run_console(name, markers, stdin)
        print("app %-24s -> %s  (%s)" % (name, "PASS" if ok else "FAIL", detail))
        if not ok:
            failures += 1
    print("---- %d app(s), %d failed ----" % (len(CONSOLE_APPS), failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
