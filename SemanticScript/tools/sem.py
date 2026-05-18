#!/usr/bin/env python3
"""SemanticScript tool driver.

This is intentionally thin for 1.0: it discovers a project build tape and
delegates to the reference tools without inventing a second build engine.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

VERSION = "0.1.0"
ROOT = Path(__file__).resolve().parents[1]


def _find_build_tape(start: Path) -> Path | None:
    candidate = start.resolve()
    if candidate.is_file():
        if candidate.name.lower() in {"build.sem", "build.sscript"}:
            return candidate
        candidate = candidate.parent

    for directory in (candidate, *candidate.parents):
        for build_name in ("build.sem", "build.sscript"):
            build_path = directory / build_name
            if build_path.is_file():
                return build_path
    return None


def _strip_separator(args: list[str]) -> list[str]:
    if args and args[0] == "--":
        return args[1:]
    return args


def _has_compiler_action(args: list[str]) -> bool:
    action_flags = {
        "--emit-exe",
        "--emit-ir",
        "--run",
        "--parse-only",
        "--lint",
        "--strict",
    }
    return any(arg in action_flags for arg in args)


def _run_compiler(source: Path, compiler_args: list[str]) -> int:
    semsc_path = ROOT / "compiler" / "semsc.py"
    command = [sys.executable, str(semsc_path), str(source), *compiler_args]
    return subprocess.call(command)


def command_build(args: argparse.Namespace) -> int:
    build_tape = _find_build_tape(Path(args.path))
    if build_tape is None:
        print(f"sem: no build.sem found from {args.path}", file=sys.stderr)
        return 2

    compiler_args = _strip_separator(list(args.compiler_args))
    if not _has_compiler_action(compiler_args):
        compiler_args = ["--emit-exe", *compiler_args]
    return _run_compiler(build_tape, compiler_args)


def command_run(args: argparse.Namespace) -> int:
    build_tape = _find_build_tape(Path(args.path))
    source = build_tape if build_tape is not None else Path(args.path)
    return _run_compiler(source, ["--run", *_strip_separator(list(args.compiler_args))])


def command_check(args: argparse.Namespace) -> int:
    build_tape = _find_build_tape(Path(args.path))
    source = build_tape if build_tape is not None else Path(args.path)
    return _run_compiler(source, ["--parse-only", "--lint", *_strip_separator(list(args.compiler_args))])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sem",
        description="SemanticScript project tool driver",
    )
    parser.add_argument("--version", action="version", version=f"sem {VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser(
        "build",
        help="discover build.sem and compile the project",
    )
    build.add_argument("path", nargs="?", default=".")
    build.add_argument("compiler_args", nargs=argparse.REMAINDER)
    build.set_defaults(func=command_build)

    run = subparsers.add_parser(
        "run",
        help="discover build.sem or use a source file and run it through the JIT",
    )
    run.add_argument("path", nargs="?", default=".")
    run.add_argument("compiler_args", nargs=argparse.REMAINDER)
    run.set_defaults(func=command_run)

    check = subparsers.add_parser(
        "check",
        help="parse and lint a build.sem project or source file",
    )
    check.add_argument("path", nargs="?", default=".")
    check.add_argument("compiler_args", nargs=argparse.REMAINDER)
    check.set_defaults(func=command_check)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
