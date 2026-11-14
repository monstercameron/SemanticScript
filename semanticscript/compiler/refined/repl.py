"""The REPL: type rows, then check and run them.

    refined repl

Each line that is not a command is a row (or a comment) added to the session's
module. The REPL writes the module header for you: the module is `repl`, it
imports every standard module its rows refer to, and it exports `main` when
there is one. Commands:

    :check          check the rows typed so far
    :run            check, then run `main`
    :show           print the module as it would be checked
    :undo           remove the last row
    :reset          start over
    :load FILE      add the rows of a file
    :quit           leave (end of input does too)
"""
from __future__ import annotations

import os
import re
import sys
import tempfile

from .library import LIBRARY

_REF = re.compile(r"\b([a-z][A-Za-z0-9]*)\.[A-Za-z]")


def module_text(rows: list[str]) -> str:
    body = "\n".join(rows)
    used = sorted({m for m in _REF.findall(body) if m in LIBRARY})
    has_main = any(r.split()[:3] == ["main", "is", "operation"] for r in rows if r.strip())
    header = ["repl is module", 'repl purpose "Rows typed at the REPL"', "repl path repl"]
    header += [f"repl imports standard.{m}" for m in used] or ["repl imports none"]
    header += ["repl exports main" if has_main else "repl exports none"]
    return "\n".join(header) + "\n\n" + body + "\n"


def _project(rows: list[str], directory: str) -> str:
    has_main = any(r.split()[:3] == ["main", "is", "operation"] for r in rows if r.strip())
    with open(os.path.join(directory, "repl.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(module_text(rows))
    build = ["replSession is project", 'replSession purpose "The REPL session"',
             f"replSession target {'console' if has_main else 'library'}", 'replSession version "0.1.0"',
             "replSession language refined-1", "replSession standardLibrary 1", "replSession requires none",
             "replSession module repl",
             f"replSession entry {'repl.main' if has_main else 'none'}"]
    with open(os.path.join(directory, "build.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(build) + "\n")
    return directory


def _say(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def main() -> int:
    from .check import check_path
    rows: list[str] = []
    interactive = sys.stdin.isatty()
    _say("refined repl: type rows; :check, :run, :show, :undo, :reset, :load FILE, :quit")
    while True:
        if interactive:
            sys.stdout.write("> ")
            sys.stdout.flush()
        line = sys.stdin.readline()
        if not line:
            return 0
        line = line.rstrip("\r\n")
        cmd = line.strip()
        if cmd in (":quit", ":q"):
            return 0
        if cmd == ":reset":
            rows = []
            _say("reset")
        elif cmd == ":undo":
            while rows and not rows[-1].strip():
                rows.pop()
            if rows:
                _say(f"removed: {rows.pop()}")
        elif cmd == ":show":
            sys.stdout.write(module_text(rows))
        elif cmd.startswith(":load "):
            path = cmd[6:].strip()
            try:
                with open(path, encoding="utf-8") as fh:
                    rows += fh.read().splitlines()
                _say(f"loaded {path}")
            except OSError as exc:
                _say(f"cannot read {path}: {exc.strerror}")
        elif cmd in (":check", ":run"):
            with tempfile.TemporaryDirectory() as d:
                res = check_path(_project(rows, d))
                for diag in res.diagnostics:
                    _say(f"{os.path.basename(diag.file)}:{diag.line}: {diag.code} {diag.message}")
                if not res.ok:
                    _say(f"{len(res.diagnostics)} error(s)")
                    continue
                if cmd == ":check":
                    _say("ok")
                    continue
                if res.project.value("entry") == "none":
                    _say("nothing to run: define `main is operation`")
                    continue
                import subprocess
                me = os.path.dirname(os.path.abspath(__file__))
                proc = subprocess.run([sys.executable, me, "run", d, "--no-cache"], capture_output=True, text=True,
                                      encoding="utf-8", errors="replace")
                sys.stdout.write(proc.stdout)
                sys.stdout.write(proc.stderr)
                _say(f"exit {proc.returncode}")
        elif cmd.startswith(":"):
            _say("commands: :check, :run, :show, :undo, :reset, :load FILE, :quit")
        else:
            rows.append(line)
