from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class TestCommand:
    key: str
    label: str
    lane: str
    args: tuple[str, ...]


def py(*args: str) -> tuple[str, ...]:
    return (sys.executable, *args)


def npm(*args: str) -> tuple[str, ...]:
    npm_path = shutil.which("npm") or "npm"
    return (npm_path, *args)


COMMANDS: tuple[TestCommand, ...] = (
    TestCommand(
        "python.compileall",
        "Compile Python sources",
        "unit",
        py("-m", "compileall", "-q", "SemanticScript", "apps", "experiments"),
    ),
    TestCommand(
        "release.versions",
        "Print release version matrix",
        "component",
        py("SemanticScript/tools/release_versions.py"),
    ),
    TestCommand(
        "formatter.unit",
        "Formatter unit tests",
        "unit",
        py("-m", "unittest", "SemanticScript/formatter/test_semfmt.py", "-v"),
    ),
    TestCommand(
        "formatter.tiny-check",
        "Formatter fixture check",
        "component",
        py("SemanticScript/formatter/semfmt.py", "--check", "SemanticScript/tests/tiny.sem"),
    ),
    TestCommand(
        "linter.unit",
        "Linter unit tests",
        "unit",
        py("-m", "unittest", "SemanticScript/linter/test_semlint.py", "-v"),
    ),
    TestCommand(
        "sem-cli.unit",
        "sem CLI unit tests",
        "unit",
        py("-m", "unittest", "SemanticScript.tests.test_sem_cli", "-v"),
    ),
    TestCommand(
        "sem-contracts.unit",
        "sem command-contract tests",
        "unit",
        py("-m", "unittest", "SemanticScript.tests.test_command_contracts", "-v"),
    ),
    TestCommand(
        "sem-mcp.unit",
        "sem mcp subcommand, MCP server wrapper, and distribution manifest tests",
        "unit",
        py("-m", "unittest", "SemanticScript.tests.test_sem_mcp", "-v"),
    ),
    TestCommand(
        "sem-clean.unit",
        "sem clean artifact-discovery/removal tests",
        "unit",
        py("-m", "unittest", "SemanticScript.tests.test_sem_clean", "-v"),
    ),
    TestCommand(
        "cli-errors.unit",
        "semsc/sem CLI error contracts (missing file, bad flag, unknown subcommand)",
        "unit",
        py("-m", "unittest", "SemanticScript.tests.test_cli_errors", "-v"),
    ),
    TestCommand(
        "release-versions.unit",
        "Release version-matrix tool tests",
        "unit",
        py("-m", "unittest", "SemanticScript.tests.test_release_versions", "-v"),
    ),
    TestCommand(
        "compiler.cli-flags",
        "Compiler CLI flag coverage (emit-optimized-ir, cpu-baseline)",
        "component",
        py("-m", "unittest", "SemanticScript.tests.test_compiler_cli_flags", "-v"),
    ),
    TestCommand(
        "stdlib.coverage-guard",
        "Stdlib coverage guard: every std/* module parses + is registered in an integration harness",
        "component",
        py("-m", "unittest", "SemanticScript.tests.test_stdlib_coverage_guard", "-v"),
    ),
    TestCommand(
        "compiler.feature-corpus",
        "Compile-gate the 168 feature_tests to IR (XFAIL-tracked); no C compiler needed",
        "component",
        py("SemanticScript/tests/feature_corpus.py"),
    ),
    TestCommand(
        "tooling.corpus-smoke",
        "semlint (no-crash) + semfmt (idempotent) over every shipped stdlib/sample source",
        "component",
        py("-m", "unittest", "SemanticScript.tests.test_tooling_corpus_smoke", "-v"),
    ),
    TestCommand(
        "parser.fuzz",
        "Parser never-crash fuzzer (deterministic mutation; no Python traceback on garbage)",
        "component",
        py("SemanticScript/tests/fuzz_parser.py"),
    ),
    TestCommand(
        "spec.inventory",
        "Spec-conformance: syntax-inventory table integrity + headline Impl'd features compile",
        "component",
        py("-m", "unittest", "SemanticScript.tests.test_spec_inventory", "-v"),
    ),
    TestCommand(
        "compiler.differential",
        "Opt-level differential: every sample is O0=O1=O2=O3 invariant (JIT)",
        "component",
        py("SemanticScript/tests/differential.py"),
    ),
    TestCommand(
        "parser.tiny-sscript",
        "Parse .sscript smoke fixture",
        "component",
        py("SemanticScript/compiler/semsc.py", "SemanticScript/tests/tiny.sscript", "--parse-only"),
    ),
    TestCommand(
        "parser.tiny-sem",
        "Parse .sem smoke fixture",
        "component",
        py("SemanticScript/compiler/semsc.py", "SemanticScript/tests/tiny.sem", "--parse-only"),
    ),
    TestCommand(
        "linter.tiny-sscript",
        "Lint .sscript smoke fixture",
        "component",
        py("SemanticScript/linter/semlint.py", "SemanticScript/tests/tiny.sscript", "--summary"),
    ),
    TestCommand(
        "linter.tiny-sem",
        "Lint .sem smoke fixture",
        "component",
        py("SemanticScript/linter/semlint.py", "SemanticScript/tests/tiny.sem", "--summary"),
    ),
    TestCommand(
        "sem.version-json",
        "sem version JSON smoke",
        "component",
        py("SemanticScript/tools/sem.py", "--version", "--json"),
    ),
    TestCommand(
        "sem.skills-json",
        "sem skills JSON smoke",
        "component",
        py("SemanticScript/tools/sem.py", "skills", "list", "--json"),
    ),
    TestCommand(
        "sem.green-check",
        "sem check green fixture",
        "component",
        py("SemanticScript/tools/sem.py", "check", "--json", "SemanticScript/tests/agent_cli_demo.test.sem"),
    ),
    TestCommand(
        "sem.green-fmt",
        "sem fmt green fixture",
        "component",
        py("SemanticScript/tools/sem.py", "fmt", "--check", "SemanticScript/tests/agent_cli_demo.test.sem"),
    ),
    TestCommand(
        "sem.green-test",
        "sem test green fixture",
        "component",
        py(
            "SemanticScript/tools/sem.py",
            "test",
            "--json",
            "SemanticScript/tests/agent_cli_demo.test.sem",
            "--skip-python-harnesses",
        ),
    ),
    TestCommand(
        "async.lowering",
        "Async lowering tests",
        "component",
        py("SemanticScript/tests/test_async_wait_sets.py"),
    ),
    TestCommand(
        "syntax.migration",
        "Syntax migration tests",
        "component",
        py("SemanticScript/tests/test_syntax_migration.py"),
    ),
    TestCommand(
        "app.syntax-cutover",
        "App syntax cutover tests",
        "component",
        py("-m", "unittest", "SemanticScript.tests.test_app_syntax_cutover", "-v"),
    ),
    TestCommand(
        "vscode.check",
        "VS Code extension check",
        "component",
        npm("--prefix", "vscode-semanticscript", "run", "check"),
    ),
    TestCommand(
        "app.runtime-smoke",
        "App runtime smoke tests",
        "integration",
        py("-m", "unittest", "SemanticScript.tests.test_app_runtime_smoke", "-v"),
    ),
    TestCommand(
        "compiler.full",
        "Compiler release tests",
        "integration",
        py("SemanticScript/tests/test_compiler.py"),
    ),
    TestCommand(
        "stdlib.full",
        "Standard library tests (JIT smoke; http quarantined)",
        "integration",
        py("SemanticScript/tests/test_stdlib.py"),
    ),
    TestCommand(
        "stdlib.native-smoke",
        "Native-exe stdlib smokes (log, bcrypt, jwt, net)",
        "integration",
        py("-m", "unittest", "SemanticScript.tests.test_native_stdlib_smoke", "-v"),
    ),
    TestCommand(
        "event-runtime.native",
        "Event/async native C runtime tests",
        "integration",
        py("-m", "unittest", "SemanticScript.tests.test_event_runtime_native", "-v"),
    ),
    TestCommand(
        "async-runtime.native",
        "Native async C runtime (sem_async_runtime.c) direct harness tests",
        "integration",
        py("-m", "unittest", "SemanticScript.tests.test_native_async_runtime", "-v"),
    ),
    TestCommand(
        "compiler.feature-runtime",
        "Run feature_tests natively, assert stdout/exit match their declared # expect oracles",
        "integration",
        py("SemanticScript/tests/feature_runtime.py"),
    ),
    TestCommand(
        "runtime.asan",
        "AddressSanitizer/UBSan over the hand-written C runtime demos (skips if toolchain lacks ASan)",
        "integration",
        py("-m", "unittest", "SemanticScript.tests.test_asan", "-v"),
    ),
    TestCommand(
        "golden.e2e",
        "E2E golden-output: compile programs to native exe + assert verified expected stdout",
        "e2e",
        py("SemanticScript/tests/golden_e2e.py"),
    ),
    TestCommand(
        "native.parity",
        "E2E JIT<->native parity: sample programs + every JIT-able stdlib self-test",
        "e2e",
        py("SemanticScript/tests/native_parity.py"),
    ),
    TestCommand(
        "reference.parity",
        "Reference parity tests (optional JS oracle corpus; skips when absent)",
        "e2e",
        py("SemanticScript/tests/compare.py"),
    ),
    TestCommand(
        "sem-alias.parity",
        ".sem alias source/parity tests",
        "e2e",
        py("SemanticScript/tests/sem_alias_parity.py"),
    ),
)


COMMAND_BY_KEY = {command.key: command for command in COMMANDS}


SUITE_DESCRIPTIONS = {
    "unit": "Python unit-level checks for formatter, linter, sem CLI, and command contracts.",
    "component": "Tooling component checks, parser/linter smoke fixtures, syntax migration, and editor checks.",
    "integration": "Compiler, stdlib, and app runtime integration checks that build or run artifacts.",
    "stdlib": "Standard library only: JIT module smokes (http quarantined), native-exe smokes (log/bcrypt/jwt/net), and the event/async native runtime.",
    "e2e": "End-to-end parity checks for reference output and .sem source alias behavior.",
    "editor": "VS Code extension validation only.",
    "ci-fast": "Windows GitHub Python validation lane.",
    "ci-release": "Windows GitHub release validation lane.",
    "all": "All project lanes: unit, component, integration, and e2e.",
}


SUITES: dict[str, tuple[str, ...]] = {
    "unit": tuple(command.key for command in COMMANDS if command.lane == "unit"),
    "component": tuple(command.key for command in COMMANDS if command.lane == "component"),
    "integration": tuple(command.key for command in COMMANDS if command.lane == "integration"),
    "e2e": tuple(command.key for command in COMMANDS if command.lane == "e2e"),
    "stdlib": (
        "stdlib.coverage-guard",
        "stdlib.full",
        "stdlib.native-smoke",
        "event-runtime.native",
    ),
    "editor": ("vscode.check",),
    "ci-fast": (
        "python.compileall",
        "release.versions",
        "formatter.unit",
        "formatter.tiny-check",
        "linter.unit",
        "sem-cli.unit",
        "sem-contracts.unit",
        "sem-mcp.unit",
        "sem-clean.unit",
        "cli-errors.unit",
        "release-versions.unit",
        "stdlib.coverage-guard",
        "compiler.feature-corpus",
        "parser.fuzz",
        "spec.inventory",
        "compiler.differential",
        "parser.tiny-sscript",
        "parser.tiny-sem",
        "linter.tiny-sscript",
        "linter.tiny-sem",
        "sem.version-json",
        "sem.skills-json",
        "sem.green-check",
        "sem.green-fmt",
        "sem.green-test",
    ),
    "ci-release": (
        "async.lowering",
        "syntax.migration",
        "app.syntax-cutover",
        "tooling.corpus-smoke",
        "compiler.cli-flags",
        "app.runtime-smoke",
        "compiler.full",
        "stdlib.full",
        "stdlib.native-smoke",
        "event-runtime.native",
        "async-runtime.native",
        "compiler.feature-runtime",
        "golden.e2e",
        "native.parity",
        "reference.parity",
        "sem-alias.parity",
    ),
}
SUITES["all"] = SUITES["unit"] + SUITES["component"] + SUITES["integration"] + SUITES["e2e"]


ALIASES = {
    "fast": "ci-fast",
    "release": "ci-release",
    "full": "all",
    "std": "stdlib",
}


def format_command(args: tuple[str, ...]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(list(args))
    return " ".join(shlex_quote(arg) for arg in args)


def shlex_quote(value: str) -> str:
    if not value:
        return "''"
    safe_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_@%+=:,./-"
    if all(char in safe_chars for char in value):
        return value
    return "'" + value.replace("'", "'\\''") + "'"


def expand_selections(selections: list[str]) -> list[TestCommand]:
    selected_keys: list[str] = []
    unknown: list[str] = []
    for raw_name in selections:
        name = ALIASES.get(raw_name, raw_name)
        if name in SUITES:
            selected_keys.extend(SUITES[name])
        elif name in COMMAND_BY_KEY:
            selected_keys.append(name)
        else:
            unknown.append(raw_name)
    if unknown:
        available = ", ".join(sorted([*SUITES.keys(), *COMMAND_BY_KEY.keys(), *ALIASES.keys()]))
        raise SystemExit(f"unknown suite or command: {', '.join(unknown)}\navailable: {available}")

    deduped: list[TestCommand] = []
    seen: set[str] = set()
    for key in selected_keys:
        if key in seen:
            continue
        seen.add(key)
        deduped.append(COMMAND_BY_KEY[key])
    return deduped


def list_suites() -> None:
    print("Suites:")
    for suite_name in sorted(SUITES):
        print(f"  {suite_name:12} {SUITE_DESCRIPTIONS.get(suite_name, '')}")
        for key in SUITES[suite_name]:
            command = COMMAND_BY_KEY[key]
            print(f"    {command.key:24} {command.label}")
    print("\nAliases:")
    for alias, target in sorted(ALIASES.items()):
        print(f"  {alias:12} {target}")


def run_command(command: TestCommand, *, dry_run: bool) -> int:
    print(f"\n== {command.key}: {command.label} ==", flush=True)
    print(f"$ {format_command(command.args)}", flush=True)
    if dry_run:
        return 0
    started = time.perf_counter()
    try:
        completed = subprocess.run(command.args, cwd=REPO_ROOT)
    except FileNotFoundError:
        elapsed = time.perf_counter() - started
        print(f"== failed rc=127: executable not found: {command.args[0]} ({elapsed:.1f}s) ==", flush=True)
        return 127
    elapsed = time.perf_counter() - started
    status = "passed" if completed.returncode == 0 else f"failed rc={completed.returncode}"
    print(f"== {status}: {command.key} ({elapsed:.1f}s) ==", flush=True)
    return completed.returncode


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run central SemanticScript project test suites. Defaults to ci-fast.",
    )
    parser.add_argument(
        "selections",
        nargs="*",
        help="Suite names or command keys. Use --list to inspect available entries.",
    )
    parser.add_argument("--list", action="store_true", help="List suites and commands without running tests.")
    parser.add_argument("--dry-run", action="store_true", help="Print selected commands without running them.")
    parser.add_argument("--keep-going", action="store_true", help="Continue after failures and report all failed commands.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.list:
        list_suites()
        return 0

    selections = args.selections or ["ci-fast"]
    commands = expand_selections(selections)
    if not commands:
        print("No test commands selected.")
        return 0

    print(f"SemanticScript test selections: {', '.join(selections)}")
    print(f"Repository root: {REPO_ROOT}")

    failures: list[tuple[TestCommand, int]] = []
    started = time.perf_counter()
    for command in commands:
        return_code = run_command(command, dry_run=args.dry_run)
        if return_code != 0:
            failures.append((command, return_code))
            if not args.keep_going:
                break
    elapsed = time.perf_counter() - started

    if failures:
        print("\nFailed commands:")
        for command, return_code in failures:
            print(f"  {command.key}: rc={return_code}")
        print(f"Selected test run failed in {elapsed:.1f}s.")
        return failures[0][1] or 1

    print(f"\nSelected test run passed in {elapsed:.1f}s.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
