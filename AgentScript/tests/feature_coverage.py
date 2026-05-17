"""
feature_coverage.py — exercise individual AS language features through
the AS-written compiler (bootstrap_general.as) and report pass/fail.

Each test program in as/feature_tests/ has a `# expect:` metadata header
declaring expected stdout (decoded with unicode_escape so newlines are
written `\\n` in the comment) and an optional expected exit code:

    # expect.stdout: hello\\n
    # expect.exit: 0
    # expect.stdin: 1\\n7\\n     (optional)
    # expect.xfail: reason         (optional — marks expected-fail)

Each test is compiled by ascc.py against bootstrap_general.as into IR,
then linked via clang into an exe, then executed. Result is diffed
against expectations. Tests marked xfail must currently fail; if they
unexpectedly pass, the harness reports XPASS so we can remove the
marker.

Exits 0 when every non-xfail test passes AND no xfail test passes.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ASCC = ROOT / "compiler" / "ascc.py"
BOOTSTRAP_GENERAL = ROOT / "bootstrap" / "bootstrap_general.as"
TEST_DIR = ROOT / "as" / "feature_tests"
BUILD_DIR = HERE / "feature_coverage" / "build"
BUILD_DIR.mkdir(parents=True, exist_ok=True)

CLANG = os.environ.get("ASCC_CLANG") or shutil.which("clang") or r"C:\Program Files\LLVM\bin\clang.exe"
if not Path(CLANG).exists():
    print(f"clang not found at {CLANG}; set ASCC_CLANG", file=sys.stderr)
    sys.exit(1)

EXPECT_LINE = re.compile(r"^#\s*expect\.(stdout|exit|stdin|xfail)\s*:\s*(.*)$")


def parse_expectations(src: str) -> dict:
    """Read the file's leading comment block for # expect.* metadata."""
    expectations = {"stdout": "", "exit": 0, "stdin": None, "xfail": None}
    for raw_line in src.splitlines():
        stripped = raw_line.rstrip()
        match = EXPECT_LINE.match(stripped)
        if match:
            key, value = match.group(1), match.group(2)
            if key in ("stdout", "stdin"):
                expectations[key] = value.encode().decode("unicode_escape")
            elif key == "exit":
                expectations[key] = int(value)
            elif key == "xfail":
                expectations[key] = value or "unspecified"
    return expectations


def compile_via_as_compiler(as_path: Path) -> tuple[bool, str, str]:
    """Run bootstrap_general.as via the Python compiler with AS_INPUT set
    to as_path. Returns (success, ir_text, stderr)."""
    env = os.environ.copy()
    env["AS_INPUT"] = str(as_path)
    proc = subprocess.run(
        [sys.executable, str(ASCC), str(BOOTSTRAP_GENERAL), "--run", "--quiet"],
        capture_output=True, text=True, env=env, timeout=20,
    )
    return (proc.returncode == 0, proc.stdout, proc.stderr)


def link_to_exe(ir_text: str, exe_path: Path) -> tuple[bool, str]:
    """Write IR to a temp file, link via clang. Returns (success, stderr)."""
    ir_path = exe_path.with_suffix(".ll")
    ir_path.write_text(ir_text, encoding="utf-8")
    proc = subprocess.run(
        [CLANG, str(ir_path), "-o", str(exe_path)],
        capture_output=True, text=True, timeout=30,
    )
    return (proc.returncode == 0 and exe_path.exists(), proc.stderr)


def execute_exe(exe_path: Path, stdin_text: str | None) -> tuple[int, str]:
    """Execute the AOT-compiled exe with optional stdin."""
    proc = subprocess.run(
        [str(exe_path)],
        input=stdin_text,
        capture_output=True, text=True, timeout=10,
    )
    actual_stdout = proc.stdout.replace("\r\n", "\n")
    return (proc.returncode, actual_stdout)


def evaluate_test(as_path: Path) -> tuple[str, str]:
    """Run one test. Returns (status, detail) where status is one of
    PASS, FAIL, XFAIL, XPASS."""
    src = as_path.read_text(encoding="utf-8", errors="replace")
    expect = parse_expectations(src)
    xfail = expect["xfail"]

    exe_path = BUILD_DIR / (as_path.stem + ".exe")

    ok, ir_text, stderr = compile_via_as_compiler(as_path)
    if not ok or not ir_text:
        if xfail:
            return ("XFAIL", f"as-compile failed: {stderr.strip()[:200]}")
        return ("FAIL", f"as-compile failed: {stderr.strip()[:200]}")

    link_ok, clang_err = link_to_exe(ir_text, exe_path)
    if not link_ok:
        if xfail:
            return ("XFAIL", f"clang-link failed: {clang_err.strip()[:200]}")
        return ("FAIL", f"clang-link failed: {clang_err.strip()[:200]}\nIR:\n{ir_text}")

    actual_rc, actual_stdout = execute_exe(exe_path, expect["stdin"])
    stdout_ok = actual_stdout == expect["stdout"]
    exit_ok = actual_rc == expect["exit"]

    if stdout_ok and exit_ok:
        if xfail:
            return ("XPASS", f"marked xfail ({xfail}) but passed — remove marker")
        return ("PASS", f"stdout={len(actual_stdout)}B exit={actual_rc}")

    if xfail:
        return ("XFAIL", f"{xfail}: stdout_ok={stdout_ok} exit_ok={exit_ok}")
    return ("FAIL", f"stdout_ok={stdout_ok} exit_ok={exit_ok}\n   expected stdout={expect['stdout']!r}\n   actual   stdout={actual_stdout!r}\n   expected exit={expect['exit']} actual exit={actual_rc}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("filter", nargs="?", default=None,
                        help="optional substring filter for test names")
    args = parser.parse_args()

    if not TEST_DIR.exists():
        print(f"test directory missing: {TEST_DIR}", file=sys.stderr)
        sys.exit(2)

    test_files = sorted(TEST_DIR.glob("*.as"))
    if args.filter:
        test_files = [f for f in test_files if args.filter in f.name]

    if not test_files:
        print("no test files found", file=sys.stderr)
        sys.exit(2)

    counts = {"PASS": 0, "FAIL": 0, "XFAIL": 0, "XPASS": 0}
    failures = []

    for as_path in test_files:
        status, detail = evaluate_test(as_path)
        counts[status] += 1
        symbol = {"PASS": "[OK ]", "FAIL": "[FAIL]",
                  "XFAIL": "[xfail]", "XPASS": "[XPASS]"}[status]
        print(f"  {symbol} {as_path.name:<40} {detail if args.verbose or status in ('FAIL','XPASS') else ''}")
        if status in ("FAIL", "XPASS"):
            failures.append((as_path.name, status, detail))

    print()
    total = sum(counts.values())
    print(f"  PASS:  {counts['PASS']:3d} / {total}")
    print(f"  FAIL:  {counts['FAIL']:3d}")
    print(f"  XFAIL: {counts['XFAIL']:3d}  (expected to fail; documents compiler gaps)")
    print(f"  XPASS: {counts['XPASS']:3d}  (xfail markers to remove)")

    coverage_target_pass = counts["PASS"] + counts["XFAIL"]  # known status
    coverage_pct = (counts["PASS"] / total * 100) if total else 0
    print(f"  Real coverage: {counts['PASS']}/{total} ({coverage_pct:.1f}%)")

    sys.exit(0 if (counts["FAIL"] == 0 and counts["XPASS"] == 0) else 1)


if __name__ == "__main__":
    main()
