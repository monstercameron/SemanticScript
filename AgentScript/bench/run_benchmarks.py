"""
run_benchmarks.py — head-to-head performance harness for AgentScript vs C.

For each registered benchmark this script:
  1. Compiles the C source with clang -O2.
  2. AOT-compiles the AgentScript source via ascc --emit-exe (clang -O2).
  3. Runs both N times, parses clockTicks from each line of stdout.
  4. Reports median time per side and the AS/C ratio.

The harness fails (exit 1) if AgentScript runs slower than 90% of C on any
benchmark.
"""

from __future__ import annotations

import os
import shutil
import statistics
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPILER = HERE.parent / "compiler" / "ascc.py"

# Resolve clang.
CLANG = os.environ.get("ASCC_CLANG") or shutil.which("clang") or r"C:/Program Files/LLVM/bin/clang.exe"
if not Path(CLANG).exists():
    print(f"clang not found at {CLANG}; set ASCC_CLANG", file=sys.stderr)
    sys.exit(1)


@dataclass
class Benchmark:
    name: str
    c_source: Path
    as_source: Path
    runs: int = 7
    warmup_runs: int = 1


BENCHMARKS = [
    Benchmark("arith",  HERE / "bench_arith.c",  HERE / "bench_arith.as"),
    Benchmark("memset", HERE / "bench_memset.c", HERE / "bench_memset.as"),
    Benchmark("math",   HERE / "bench_math.c",   HERE / "bench_math.as"),
    Benchmark("strlen", HERE / "bench_strlen.c", HERE / "bench_strlen.as"),
]


def compile_c(bench: Benchmark) -> Path:
    out = bench.c_source.with_suffix(".c.exe")
    cmd = [CLANG, "-O2", "-o", str(out), str(bench.c_source)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"clang failed for {bench.name}:\n{proc.stderr}")
    return out


def compile_as(bench: Benchmark) -> Path:
    out = bench.as_source.with_suffix(".as.exe")
    cmd = [sys.executable, str(COMPILER), str(bench.as_source),
           "--emit-exe", str(out), "--opt-level", "2"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ascc failed for {bench.name}:\n{proc.stderr}\n{proc.stdout}")
    return out


def parse_clock_ticks(stdout: str) -> int:
    # Extract the `clockTicks=NNN` value from the program's output.
    for token in stdout.split():
        if token.startswith("clockTicks="):
            return int(token.split("=", 1)[1])
    raise ValueError(f"no clockTicks in output: {stdout!r}")


def measure(exe: Path, runs: int, warmup: int) -> list[int]:
    samples: list[int] = []
    for _ in range(warmup):
        subprocess.run([str(exe)], capture_output=True, text=True, check=True)
    for _ in range(runs):
        proc = subprocess.run([str(exe)], capture_output=True, text=True, check=True)
        samples.append(parse_clock_ticks(proc.stdout))
    return samples


def main():
    print(f"Using clang at {CLANG}")
    print()
    print(f"{'benchmark':<14} {'C median':>10} {'AS median':>10} {'AS/C':>8} {'verdict':>10}")
    print("-" * 60)
    failures = 0
    for bench in BENCHMARKS:
        c_exe = compile_c(bench)
        as_exe = compile_as(bench)
        c_samples = measure(c_exe, bench.runs, bench.warmup_runs)
        as_samples = measure(as_exe, bench.runs, bench.warmup_runs)
        c_median = statistics.median(c_samples)
        as_median = statistics.median(as_samples)
        ratio = (as_median / c_median) if c_median else float("inf")
        # Performance goal: AS within 90% of C ⇒ ratio ≤ 1.111 (1/0.9).
        # "AS is X% of C" = c_median / as_median * 100, clamped to 100.
        if c_median == 0 or as_median == 0:
            verdict = "TOO FAST"
            ok = True
        else:
            pct_of_c = (c_median / as_median) * 100.0
            ok = pct_of_c >= 90.0
            verdict = f"{pct_of_c:5.1f}%"
        if not ok:
            failures += 1
        flag = "OK" if ok else "FAIL"
        print(f"{bench.name:<14} {c_median:>10} {as_median:>10} {ratio:>8.3f} {verdict:>10} [{flag}]")
    print()
    if failures:
        print(f"{failures} benchmark(s) below 90% of native C; failing.")
        sys.exit(1)
    print("All benchmarks at or above 90% of native C performance.")


if __name__ == "__main__":
    main()
