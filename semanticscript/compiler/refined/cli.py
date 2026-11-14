"""Command line for the refined compiler.

    python semanticscript/compiler/refined check   PATH [--json]
    python semanticscript/compiler/refined run     PATH [--json]
    python semanticscript/compiler/refined test    PATH [--json]
    python semanticscript/compiler/refined emit-ir PATH [--test MODULE.TEST]
    python semanticscript/compiler/refined stale   PATH --base REF [--json]
    python semanticscript/compiler/refined grammar [--textmate] [--output FILE]

PATH is a module file, a project's build.sem, or a directory holding build.sem.
`run` and `test` need a project.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from .check import check_path
from .diagnostics import Diagnostic
from .shapes import grammar_markdown, textmate_grammar


def _emit(diags: list[Diagnostic], as_json: bool, surface: str, extra: dict | None = None) -> None:
    if as_json:
        payload = {"surface": surface, "ok": not diags, "errorCount": len(diags),
                   "diagnostics": [d.to_json() for d in diags]}
        payload.update(extra or {})
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        return
    for d in diags:
        sys.stdout.write(d.format() + "\n")
    sys.stdout.write(("ok" if not diags else f"{len(diags)} error(s)") + "\n")


def _need_project(res, path: str) -> list[Diagnostic]:
    if res.project is None:
        return [Diagnostic("R601", "this command needs a project: pass build.sem or the directory holding it", path, 1)]
    return []


def _compile(res, roots):
    from .codegen import compile_roots
    return compile_roots(res.world, roots)


def _tests(res) -> list[tuple[str, str]]:
    return [(m.short, name) for m in res.world.modules.values() for name in m.tests]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="refined", description="Refined SemanticScript compiler")
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("check", "run", "test"):
        p = sub.add_parser(name)
        p.add_argument("path")
        p.add_argument("--json", action="store_true")
        if name == "run":
            p.add_argument("arguments", nargs="*", help="after `--`: what the program reads with process.argument")
    p = sub.add_parser("emit-ir")
    p.add_argument("path")
    p.add_argument("--test", default=None, help="emit the IR for one test, MODULE.TEST")
    p = sub.add_parser("stale")
    p.add_argument("path")
    p.add_argument("--base", required=True)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("run-one-test")  # internal: the test runner runs each test in its own process
    p.add_argument("path")
    p.add_argument("test")
    p = sub.add_parser("grammar")
    p.add_argument("--textmate", action="store_true", help="emit the editor grammar instead of the Markdown reference")
    p.add_argument("--output", default=None, help="write to this file (LF line endings) instead of stdout")
    args = ap.parse_args(argv)

    if args.command == "grammar":
        text = (json.dumps(textmate_grammar(), indent=2) if args.textmate else grammar_markdown()) + "\n"
        if args.output:
            with open(args.output, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        else:
            sys.stdout.write(text)
        return 0
    if args.command == "stale":
        from .stale import stale
        diags = stale(args.path, args.base)
        _emit(diags, args.json, "refined.stale.v1")
        return 0 if not diags else 1

    res = check_path(args.path)
    if args.command == "check":
        _emit(res.diagnostics, args.json, "refined.check.v1")
        return 0 if res.ok else 1
    # `run`, `test`, and `emit-ir` need a project; say so first, since a lone module's other
    # diagnostics (an exported `main` that is no project's entry, say) follow from that
    diags = _need_project(res, args.path)
    if diags:
        _emit(diags, getattr(args, "json", False), f"refined.{args.command}.v1")
        return 1
    if not res.ok:
        _emit(res.diagnostics, getattr(args, "json", False), f"refined.{args.command}.v1")
        return 1

    if args.command == "emit-ir":
        if args.test:
            roots = [tuple(args.test.split(".", 1))]
        else:
            entry = res.project.value("entry")
            roots = [tuple(entry.split(".", 1))] if entry != "none" else []
        module, diags = _compile(res, roots)
        if diags:
            _emit(diags, False, "refined.emit-ir.v1")
            return 1
        sys.stdout.write(str(module))
        return 0

    if args.command == "run":
        entry = res.project.value("entry")
        if entry == "none":
            _emit([Diagnostic("R601", "a library project has no entry to run; use `test`", args.path, 1)],
                  args.json, "refined.run.v1")
            return 1
        mod, op = entry.split(".", 1)
        module, diags = _compile(res, [(mod, op)])
        if diags:
            _emit(diags, args.json, "refined.run.v1")
            return 1
        from . import runtime
        from .runtime import Engine
        runtime.PROGRAM_ARGUMENTS[:] = args.arguments
        engine = Engine(str(module))
        code, out = engine.run_entry(f"{mod}.{op}", capture=args.json)
        if args.json:
            sys.stdout.write(json.dumps({"surface": "refined.run.v1", "ok": True, "exitCode": code,
                                         "stdout": out.decode("utf-8", "replace")}, indent=2) + "\n")
        return code

    if args.command == "run-one-test":
        mod, test = args.test.split(".", 1)
        module, diags = _compile(res, [(mod, test)])
        if diags:
            sys.stdout.write(json.dumps({"status": "unsupported", "diagnostics": [d.to_json() for d in diags]}) + "\n")
            return 0
        from .runtime import Engine
        failures, _out = Engine(str(module)).run_test(f"{mod}.{test}")
        sys.stdout.write(json.dumps({"status": "fail" if failures else "pass", "failures": failures}) + "\n")
        return 0

    # test: each test runs in its own process, so a trap ends only that test
    results = []
    me = os.path.dirname(os.path.abspath(__file__))
    for mod, test in _tests(res):
        proc = subprocess.run([sys.executable, me, "run-one-test", args.path, f"{mod}.{test}"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        try:
            r = json.loads(line)
        except ValueError:
            r = {"status": "trapped", "failures": [proc.stderr.strip()]}
        if proc.returncode not in (0,) and r.get("status") not in ("pass", "fail", "unsupported"):
            r = {"status": "trapped", "failures": [proc.stderr.strip()]}
        r["test"] = f"{mod}.{test}"
        results.append(r)
    ok = all(r["status"] == "pass" for r in results)
    if args.json:
        sys.stdout.write(json.dumps({"surface": "refined.test.v1", "ok": ok, "results": results}, indent=2) + "\n")
    else:
        for r in results:
            sys.stdout.write(f"{r['status'].upper():11} {r['test']}\n")
            for f in r.get("failures", []):
                sys.stdout.write(f"    {f}\n")
            for d in r.get("diagnostics", []):
                sys.stdout.write(f"    {d['file']}:{d['line']}: {d['code']} {d['message']}\n")
        passed = sum(r["status"] == "pass" for r in results)
        sys.stdout.write(f"{passed} of {len(results)} tests passed\n")
    return 0 if ok else 1
