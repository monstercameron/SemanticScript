"""
test_stdlib.py — run every stdlib_as/*.as self-test and verify it
exits 0 with stdout 'OK'. Each file is compiled via the trusted
Python reference compiler (compiler/ascc.py) and JIT-executed.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ASCC = ROOT / "compiler" / "ascc.py"
STDLIB_DIR = ROOT / "stdlib_as"


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
    # putString prints "no-newline-then-putLine" with no trailing
    # newline; the immediately-following putLine("") supplies the
    # single LF that ends the line, so the next line starts cleanly.
    "no-newline-then-putLine\n"
    "42\n"
    "-1234\n"
    "0\n"
    "255\n"
    "ff\n"
)


def run(as_file: Path, expected: str) -> bool:
    proc = subprocess.run(
        [sys.executable, str(ASCC), str(as_file), "--run", "--quiet"],
        capture_output=True, text=True, timeout=20,
    )
    actual = proc.stdout.replace("\r\n", "\n")
    if proc.returncode != 0 or actual != expected:
        print(f"[FAIL] {as_file.name}: rc={proc.returncode}")
        print(f"   expected: {expected!r}")
        print(f"   got:      {actual!r}")
        if proc.stderr:
            print(f"   stderr:\n{proc.stderr.strip()}")
        return False
    print(f"[OK  ] {as_file.name}")
    return True


def main():
    failures = 0
    for name in OK_PROGRAMS:
        ok = run(STDLIB_DIR / name, "OK\n")
        if not ok:
            failures += 1
    ok = run(STDLIB_DIR / "stdio.as", EXPECTED_STDIO_OUTPUT)
    if not ok:
        failures += 1
    print()
    total = len(OK_PROGRAMS) + 1
    if failures:
        print(f"FAILED: {failures}/{total}")
        sys.exit(1)
    print(f"All {total} stdlib self-tests passed.")


if __name__ == "__main__":
    main()
