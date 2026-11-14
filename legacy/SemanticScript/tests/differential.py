"""
differential.py - optimization-level differential testing.

Optimization must never change observable behavior. For each sample program this
runs the JIT at every LLVM optimization level (`--opt-level 0..3`) and asserts
all four produce byte-identical stdout and the same exit code. A divergence means
an optimizer pass miscompiles the program (the classic place codegen bugs hide,
e.g. unsound fast-math on the float-heavy samples, bad GVN/DCE, etc.).

This is the metamorphic complement to `native_parity.py` (JIT vs native at the
default level): here the program is fixed and the *compiler configuration* is
varied. It is JIT-only, so it needs no C compiler and runs in the component /
ci-fast lane.

Run from the repo root:
    python SemanticScript/tests/differential.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SEMSC = ROOT / "compiler" / "semsc.py"
SEM_DIR = ROOT / "sem"

OPT_LEVELS = ("0", "1", "2", "3")
RUN_TIMEOUT = 30

# Reuse the curated deterministic program set from the golden harness so the two
# stay in lockstep (same programs, different invariant).
from golden_e2e import PROGRAMS  # noqa: E402  (sibling module; tests/ on sys.path)


def run_jit(source: Path, stdin_input: str, opt: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(SEMSC), str(source), "--run", "--opt-level", opt],
        input=stdin_input, capture_output=True, text=True, timeout=RUN_TIMEOUT,
    )
    return proc.returncode, proc.stdout.replace("\r\n", "\n")


def main() -> int:
    failures = 0
    total_elapsed = 0.0
    for name, stdin_input in PROGRAMS:
        source = SEM_DIR / (name + ".sscript")
        if not source.exists():
            print(f"[ERR ] missing source: {name}")
            failures += 1
            continue
        started = time.perf_counter()
        results: dict[str, tuple[int, str]] = {}
        try:
            for opt in OPT_LEVELS:
                results[opt] = run_jit(source, stdin_input, opt)
        except subprocess.TimeoutExpired:
            print(f"[ERR ] {name}: timeout")
            failures += 1
            continue
        total_elapsed += time.perf_counter() - started

        baseline = results["0"]
        diverged = {opt: r for opt, r in results.items() if r != baseline}
        if not diverged:
            print(f"[OK  ] {name}: all opt levels agree (rc={baseline[0]})")
            continue
        failures += 1
        print(f"[FAIL] {name}: optimization changed behavior")
        print(f"    O0: rc={baseline[0]} {baseline[1][:80]!r}")
        for opt, (rc, out) in diverged.items():
            print(f"    O{opt}: rc={rc} {out[:80]!r}")

    total = len(PROGRAMS)
    if failures:
        print(f"\n{failures} / {total} programs diverge across opt levels "
              f"({total_elapsed:.1f}s).")
        return 1
    print(f"\nAll {total} programs are opt-level invariant "
          f"(O0=O1=O2=O3) in {total_elapsed:.1f}s.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
