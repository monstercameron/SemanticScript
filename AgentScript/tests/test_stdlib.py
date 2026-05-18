"""
test_stdlib.py — run every stdlib_as/*.as self-test and verify it
exits 0 with stdout 'OK'. Each file is compiled via the trusted
Python reference compiler (compiler/ascc.py) and JIT-executed.

Per-test wall-clock timing is recorded and flagged when it exceeds
the PERFORMANCE_BUDGET_SECONDS budget. The budget is generous because
the JIT path includes IR generation, LLVM IR-to-native lowering, and
program execution for each test — typical times are well under 1s,
so a 5s budget catches genuine regressions.
"""

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ASCC = ROOT / "compiler" / "ascc.py"
STDLIB_DIR = ROOT / "stdlib_as"

# Per-test wall-clock budget. Any test that takes longer than this
# is flagged as a performance regression. The smoke tests are pure
# JIT runs of short programs — none should approach this number.
PERFORMANCE_BUDGET_SECONDS = 5.0


# Self-tests expected to print exactly 'OK\n' and exit 0.
OK_PROGRAMS = ["string.as", "ctype.as", "stdlib.as", "memory.as",
               "math.as", "math_float.as", "assert.as",
               "limits.as", "errno.as", "time.as",
               "signal.as", "process.as", "bool.as",
               "random.as", "stddef.as", "iso646.as",
               "inttypes.as", "bit.as", "constants.as",
               "compare.as", "convert.as", "array.as",
               "sort.as", "char.as", "numeric.as",
               "signal_more.as", "errno_more.as"]
# stdio's smoke test prints multiple lines (the demo output of every
# operation), not just OK.
EXPECTED_STDIO_OUTPUT = (
    "Hello, AgentScript stdlib!\n"
    # writeCStringToStandardOutput prints the literal without a trailing
    # newline; the immediately-following writeCStringLineToStandardOutput("")
    # supplies the single LF that ends the line, so the next line starts
    # cleanly. (Pre-rename, the operations were named putString and putLine.)
    "no-newline-then-writeCStringLineToStandardOutput\n"
    "42\n"
    "-1234\n"
    "0\n"
    "255\n"
    "ff\n"
    # writeByteToStandardOutput is exercised at the end: byte 65 ('A')
    # followed by byte 10 (LF). This was the one stdio op the previous
    # smoke didn't cover.
    "A\n"
)


def run(as_file: Path, expected: str) -> tuple[bool, float, bool]:
    """Returns (passed, elapsed_seconds, within_budget)."""
    started = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, str(ASCC), str(as_file), "--run", "--quiet"],
        capture_output=True, text=True, timeout=20,
    )
    elapsed = time.perf_counter() - started
    actual = proc.stdout.replace("\r\n", "\n")
    within_budget = elapsed <= PERFORMANCE_BUDGET_SECONDS
    if proc.returncode != 0 or actual != expected:
        print(f"[FAIL] {as_file.name} ({elapsed:.2f}s): rc={proc.returncode}")
        print(f"   expected: {expected!r}")
        print(f"   got:      {actual!r}")
        if proc.stderr:
            print(f"   stderr:\n{proc.stderr.strip()}")
        return (False, elapsed, within_budget)
    flag = "" if within_budget else f" [SLOW: {elapsed:.2f}s > {PERFORMANCE_BUDGET_SECONDS}s]"
    print(f"[OK  ] {as_file.name} ({elapsed:.2f}s){flag}")
    return (True, elapsed, within_budget)


def main():
    failures = 0
    over_budget = 0
    total_elapsed = 0.0
    slowest_name = None
    slowest_elapsed = 0.0
    for name in OK_PROGRAMS:
        ok, elapsed, within_budget = run(STDLIB_DIR / name, "OK\n")
        total_elapsed += elapsed
        if elapsed > slowest_elapsed:
            slowest_elapsed = elapsed
            slowest_name = name
        if not ok:
            failures += 1
        if not within_budget:
            over_budget += 1
    ok, elapsed, within_budget = run(STDLIB_DIR / "stdio.as", EXPECTED_STDIO_OUTPUT)
    total_elapsed += elapsed
    if elapsed > slowest_elapsed:
        slowest_elapsed = elapsed
        slowest_name = "stdio.as"
    if not ok:
        failures += 1
    if not within_budget:
        over_budget += 1
    print()
    total = len(OK_PROGRAMS) + 1
    print(f"Total wall-clock: {total_elapsed:.2f}s across {total} tests "
          f"(avg {total_elapsed / total:.2f}s, slowest {slowest_name} "
          f"@ {slowest_elapsed:.2f}s).")
    if failures:
        print(f"FAILED: {failures}/{total}")
        sys.exit(1)
    if over_budget:
        print(f"PERF: {over_budget} test(s) exceeded "
              f"{PERFORMANCE_BUDGET_SECONDS}s budget.")
        sys.exit(2)
    print(f"All {total} stdlib self-tests passed.")


if __name__ == "__main__":
    main()
