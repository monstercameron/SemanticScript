"""Command line for the refined compiler.

    refined check   PATH [--json] [--no-cache]
    refined run     PATH [--json] [--no-cache] [--trace] [--coverage] [--profile]
                         [--debug [--break MODULE.OP[:LABEL]]...] [-- ARGUMENTS...]
    refined test    PATH [--json]
    refined bench   PATH [--runs N] [--json]
    refined emit-ir PATH [--test MODULE.TEST]
    refined build   PATH --output FILE [--target TRIPLE] [--kind object|assembly|wasm|executable]
                         [--runtime c|semanticscript]
    refined fmt     PATH... [--check]
    refined repl
    refined lsp
    refined stale   PATH --base REF [--json]
    refined grammar [--textmate] [--output FILE]

PATH is a module file, a project's build.sem, or a directory holding build.sem.
`run`, `test`, `bench`, `emit-ir`, and `build` need a project. (`refined` is
`python semanticscript/compiler/refined`.)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from . import cache
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


def _compile(res, roots, options=None):
    from .codegen import compile_roots
    return compile_roots(res.world, roots, options)


def _tests(res) -> list[tuple[str, str]]:
    return [(m.short, name) for m in res.world.modules.values() for name in m.tests]


def _checked(path: str, command: str, as_json: bool):
    """The check result when the program is clean and is a project; otherwise None after reporting why."""
    res = check_path(path)
    # `run`, `test`, and `emit-ir` need a project; say so first, since a lone module's other
    # diagnostics (an exported `main` that is no project's entry, say) follow from that
    diags = _need_project(res, path)
    if diags:
        _emit(diags, as_json, f"refined.{command}.v1")
        return None
    if not res.ok:
        _emit(res.diagnostics, as_json, f"refined.{command}.v1")
        return None
    return res


def _entry_ir(path: str, options: dict, as_json: bool, use_cache: bool, surface: str):
    """(IR text, block names, entry name) for the project's entry, from the cache when nothing changed."""
    if use_cache:
        cached = cache.load(path, {"command": "run", **options}, "json")
        if cached is not None:
            data = json.loads(cached)
            return data["ir"], data["blocks"], data["entry"]
    res = _checked(path, surface, as_json)
    if res is None:
        return None
    entry = res.project.value("entry")
    if entry == "none":
        _emit([Diagnostic("R601", "a library project has no entry to run; use `test`", path, 1)], as_json,
              f"refined.{surface}.v1")
        return None
    mod, op = entry.split(".", 1)
    module, diags = _compile(res, [(mod, op)], options)
    if diags:
        _emit(diags, as_json, f"refined.{surface}.v1")
        return None
    ir_text, blocks = str(module), list(getattr(module, "refined_blocks", []))
    if use_cache:
        cache.store(path, {"command": "run", **options}, "json", json.dumps({"ir": ir_text, "blocks": blocks,
                                                                            "entry": f"{mod}.{op}"}))
    return ir_text, blocks, f"{mod}.{op}"


def _unapproved(path: str) -> int:
    """D-53: a program runs only with authority someone approved. Exit 3, naming what is missing, otherwise 0."""
    from .check import find_build, unapproved_authority
    build_path = find_build(path)
    if build_path is None:
        return 0
    missing = unapproved_authority(build_path)
    if not missing:
        return 0
    sys.stderr.write("build.sem asks for authority that was not approved:\n"
                     + "".join(f"  allows {r}\n" for r in missing)
                     + f"review these rows, then run `refined approve {path}`\n")
    return 3


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="refined", description="Refined SemanticScript compiler")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check")
    p.add_argument("path")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-cache", action="store_true")
    p = sub.add_parser("run")
    p.add_argument("path")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--trace", action="store_true", help="print every block entered, on stderr")
    p.add_argument("--coverage", action="store_true", help="report which blocks ran, on stderr")
    p.add_argument("--profile", action="store_true", help="report calls, time, and region peaks, on stderr")
    p.add_argument("--debug", action="store_true", help="stop at breakpoints and read debugger commands from stdin")
    p.add_argument("--break", dest="breakpoints", action="append", default=[], metavar="MODULE.OP[:LABEL]")
    p.add_argument("arguments", nargs="*", help="after `--`: what the program reads with process.argument")
    p = sub.add_parser("test")
    p.add_argument("path")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("bench", help="run the entry several times and report how long each run took")
    p.add_argument("path")
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("approve", help="review a project's `allows` rows and approve them (D-53)")
    p.add_argument("path")
    p = sub.add_parser("emit-ir")
    p.add_argument("path")
    p.add_argument("--test", default=None, help="emit the IR for one test, MODULE.TEST")
    p = sub.add_parser("build", help="compile the entry ahead of time to an object, assembly, or WebAssembly file")
    p.add_argument("path")
    p.add_argument("--output", required=True)
    p.add_argument("--target", default=None, help="an LLVM target triple; the host's when omitted")
    p.add_argument("--kind", choices=("object", "assembly", "wasm", "executable"), default="object")
    p.add_argument("--runtime", choices=("c", "semanticscript"), default="c",
                   help="for an executable: the C runtime (native_runtime.c), or the runtime in SemanticScript linked "
                        "with no C library (D-124)")
    p = sub.add_parser("stale")
    p.add_argument("path")
    p.add_argument("--base", required=True)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("run-one-test")  # internal: the test runner runs each test in its own process
    p.add_argument("path")
    p.add_argument("test")
    p = sub.add_parser("fmt", help="format .sem files in place (or check that they are formatted)")
    p.add_argument("paths", nargs="+")
    p.add_argument("--check", action="store_true", help="change nothing; exit 1 if a file would change")
    sub.add_parser("repl", help="type rows, then check and run them")
    sub.add_parser("lsp", help="a Language Server Protocol server on stdin and stdout")
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
    if args.command == "fmt":
        from .fmt import main as fmt_main
        return fmt_main(args.paths, args.check)
    if args.command == "repl":
        from .repl import main as repl_main
        return repl_main()
    if args.command == "lsp":
        from .lsp import main as lsp_main
        return lsp_main()
    if args.command == "stale":
        from .stale import stale
        diags = stale(args.path, args.base)
        _emit(diags, args.json, "refined.stale.v1")
        return 0 if not diags else 1

    if args.command == "approve":
        from .check import approve_authority, find_build
        build_path = find_build(args.path)
        if build_path is None:
            sys.stderr.write(f"{args.path} is not a project (no build.sem)\n")
            return 2
        rows = approve_authority(build_path)
        sys.stdout.write("approved:\n" + "".join(f"  allows {r}\n" for r in rows) if rows else
                         "approved: nothing (the project allows none)\n")
        return 0
    if args.command in ("run", "bench", "test", "run-one-test") or (args.command == "build" and args.kind == "executable"):
        refused = _unapproved(args.path)
        if refused:
            return refused

    if args.command == "check":
        if not args.no_cache:
            cached = cache.load(args.path, {"command": "check"}, "json")
            if cached is not None:
                diags = [Diagnostic(**d) for d in json.loads(cached)]
                _emit(diags, args.json, "refined.check.v1", {"cached": True} if args.json else None)
                return 0 if not diags else 1
        res = check_path(args.path)
        if not args.no_cache:
            cache.store(args.path, {"command": "check"}, "json",
                        json.dumps([{"code": d.code, "message": d.message, "file": d.file, "line": d.line}
                                    for d in res.diagnostics]))
        _emit(res.diagnostics, args.json, "refined.check.v1", {"cached": False} if args.json else None)
        return 0 if res.ok else 1

    if args.command == "run":
        from . import instrument, runtime, tasks
        options = {k: True for k in ("trace", "coverage", "debug") if getattr(args, k)}
        built = _entry_ir(args.path, options, args.json, not args.no_cache, "run")
        if built is None:
            return 1
        ir_text, blocks, entry = built
        instrument.STATE.update(trace=args.trace, coverage=args.coverage, debug=args.debug, profile=args.profile)
        instrument.BREAKPOINTS.update(args.breakpoints)
        instrument.ALL_BLOCKS[:] = blocks
        tasks.PROFILING[0] = args.profile
        runtime.PROGRAM_ARGUMENTS[:] = args.arguments
        engine = runtime.Engine(ir_text)
        code, out = engine.run_entry(entry, capture=args.json)
        instrument.report()
        if args.json:
            sys.stdout.write(json.dumps({"surface": "refined.run.v1", "ok": True, "exitCode": code,
                                         "stdout": out.decode("utf-8", "replace")}, indent=2) + "\n")
        return code

    if args.command == "bench":
        import statistics
        import time
        from . import runtime
        built = _entry_ir(args.path, {}, args.json, True, "bench")
        if built is None:
            return 1
        ir_text, _blocks, entry = built
        engine = runtime.Engine(ir_text)
        times, code = [], 0
        for _ in range(max(1, args.runs)):
            start = time.perf_counter()
            code, _out = engine.run_entry(entry, capture=True)
            times.append((time.perf_counter() - start) * 1000.0)
        summary = {"surface": "refined.bench.v1", "entry": entry, "runs": len(times), "exitCode": code,
                   "minMs": min(times), "medianMs": statistics.median(times), "maxMs": max(times)}
        if args.json:
            sys.stdout.write(json.dumps(summary, indent=2) + "\n")
        else:
            sys.stdout.write(f"{entry}: {len(times)} runs, min {summary['minMs']:.3f} ms, "
                             f"median {summary['medianMs']:.3f} ms, max {summary['maxMs']:.3f} ms\n")
        return 0

    res = _checked(args.path, args.command, getattr(args, "json", False))
    if res is None:
        return 1

    if args.command in ("emit-ir", "build"):
        if getattr(args, "test", None):
            roots = [tuple(args.test.split(".", 1))]
        else:
            entry = res.project.value("entry")
            roots = [tuple(entry.split(".", 1))] if entry != "none" else \
                [(m.short, op) for m in res.world.modules.values() for op, i in m.op_infos.items() if not i.tparams]
        module, diags = _compile(res, roots)
        if diags:
            _emit(diags, False, f"refined.{args.command}.v1")
            return 1
        if args.command == "emit-ir":
            sys.stdout.write(str(module))
            return 0
        from .native import build
        entry = res.project.value("entry")
        return build(str(module), args.output, args.target, args.kind, None if entry == "none" else entry,
                     getattr(args, "runtime", "c"))

    if args.command == "run-one-test":
        mod, _dot, test = args.test.partition(".")
        known = res.world.modules.get(mod)
        if known is None or test not in known.tests:
            sys.stderr.write(f"there is no test `{args.test}` in this project\n")
            return 2
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
