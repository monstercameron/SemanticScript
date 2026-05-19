"""
Run every canonical stdlib self-test under
std/<module>/main.test.sem.

Each file is compiled via compiler/semsc.py and JIT-executed. Per-test
wall-clock timing is recorded and flagged when it exceeds the performance
budget. The budget is intentionally generous because the JIT path includes IR
generation, LLVM lowering, and program execution for each test.
"""

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SEMSC = ROOT / "compiler" / "semsc.py"
STDLIB_DIR = ROOT / "std"

PERFORMANCE_BUDGET_SECONDS = 5.0


OK_MODULES = [
    "gui", "html", "http", "json", "sqlite",
    "string", "ctype", "stdlib", "memory", "math", "math_float",
    "assert", "limits", "errno", "time", "signal", "process", "bool",
    "random", "stddef", "iso646", "inttypes", "bit", "constants",
    "compare", "convert", "array", "sort", "char", "numeric",
    "signal_more", "errno_more",
]

EXPECTED_STDIO_OUTPUT = (
    "Hello, SemanticScript stdlib!\n"
    "no-newline-then-writeCStringLineToStandardOutput\n"
    "42\n"
    "-1234\n"
    "0\n"
    "255\n"
    "ff\n"
    "A\n"
)


def test_path(module_name: str) -> Path:
    return STDLIB_DIR / module_name / "main.test.sem"


def run(as_file: Path, expected: str) -> tuple[bool, float, bool]:
    started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, str(SEMSC), str(as_file), "--run", "--quiet"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    elapsed = time.perf_counter() - started
    actual = proc.stdout.replace("\r\n", "\n")
    within_budget = elapsed <= PERFORMANCE_BUDGET_SECONDS
    label = str(as_file.relative_to(STDLIB_DIR))
    if proc.returncode != 0 or actual != expected:
        print(f"[FAIL] {label} ({elapsed:.2f}s): rc={proc.returncode}")
        print(f"   expected: {expected!r}")
        print(f"   got:      {actual!r}")
        if proc.stderr:
            print(f"   stderr:\n{proc.stderr.strip()}")
        return (False, elapsed, within_budget)
    flag = "" if within_budget else f" [SLOW: {elapsed:.2f}s > {PERFORMANCE_BUDGET_SECONDS}s]"
    print(f"[OK  ] {label} ({elapsed:.2f}s){flag}")
    return (True, elapsed, within_budget)


def main() -> None:
    failures = 0
    over_budget = 0
    total_elapsed = 0.0
    slowest_name = None
    slowest_elapsed = 0.0

    for module_name in OK_MODULES:
        target = test_path(module_name)
        ok, elapsed, within_budget = run(target, "OK\n")
        total_elapsed += elapsed
        if elapsed > slowest_elapsed:
            slowest_elapsed = elapsed
            slowest_name = str(target.relative_to(STDLIB_DIR))
        if not ok:
            failures += 1
        if not within_budget:
            over_budget += 1

    stdio_target = test_path("stdio")
    ok, elapsed, within_budget = run(stdio_target, EXPECTED_STDIO_OUTPUT)
    total_elapsed += elapsed
    if elapsed > slowest_elapsed:
        slowest_elapsed = elapsed
        slowest_name = str(stdio_target.relative_to(STDLIB_DIR))
    if not ok:
        failures += 1
    if not within_budget:
        over_budget += 1

    print()
    total = len(OK_MODULES) + 1
    print(
        f"Total wall-clock: {total_elapsed:.2f}s across {total} tests "
        f"(avg {total_elapsed / total:.2f}s, slowest {slowest_name} "
        f"@ {slowest_elapsed:.2f}s)."
    )
    if failures:
        print(f"FAILED: {failures}/{total}")
        sys.exit(1)
    if over_budget:
        print(
            f"PERF: {over_budget} test(s) exceeded "
            f"{PERFORMANCE_BUDGET_SECONDS}s budget."
        )
        sys.exit(2)
    print(f"All {total} stdlib self-tests passed.")


if __name__ == "__main__":
    main()
