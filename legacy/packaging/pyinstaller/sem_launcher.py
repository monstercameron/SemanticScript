"""Frozen executable entry point for the SemanticScript toolchain."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Sequence


SCRIPT_ROUTES = {
    "SemanticScript/compiler/semsc.py": ("SemanticScript.compiler.semsc", False),
    "SemanticScript/linter/semlint.py": ("SemanticScript.linter.semlint", True),
    "SemanticScript/formatter/semfmt.py": ("SemanticScript.formatter.semfmt", False),
    "SemanticScript/bench/run_benchmarks.py": ("SemanticScript.bench.run_benchmarks", True),
    "SemanticScript/tools/syntax_migration.py": ("SemanticScript.tools.syntax_migration", True),
    "SemanticScript/tools/sem.py": ("SemanticScript.tools.sem", True),
}


def _bundle_root() -> Path:
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[2]


def _add_import_roots() -> None:
    root = _bundle_root()
    for path in (root, root / "SemanticScript"):
        path_text = str(path)
        if path_text not in sys.path:
            sys.path.insert(0, path_text)


def _normalized_path(value: str) -> str:
    return value.replace("\\", "/").lower()


def _script_route(value: str) -> tuple[str, bool] | None:
    normalized = _normalized_path(value)
    for suffix, route in SCRIPT_ROUTES.items():
        if normalized.endswith(suffix.lower()):
            return route
    return None


def _coerce_return_code(result: object) -> int:
    if result is None:
        return 0
    if isinstance(result, int):
        return result
    return int(result)


def _run_module_main(module: ModuleType, argv: Sequence[str], *, passes_argv: bool) -> int:
    old_argv = sys.argv[:]
    sys.argv = [getattr(module, "__file__", module.__name__), *argv]
    try:
        if passes_argv:
            return _coerce_return_code(module.main(list(argv)))
        return _coerce_return_code(module.main())
    finally:
        sys.argv = old_argv


def main(argv: Sequence[str] | None = None) -> int:
    _add_import_roots()
    args = list(sys.argv[1:] if argv is None else argv)

    if args:
        route = _script_route(args[0])
        if route is not None:
            module_name, passes_argv = route
            module = importlib.import_module(module_name)
            return _run_module_main(module, args[1:], passes_argv=passes_argv)

    from SemanticScript.tools import sem

    return sem.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
