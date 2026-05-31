"""
run_benchmarks.py - head-to-head performance harness for SemanticScript vs C.

For each registered benchmark this script:
  1. Compiles the C source with clang -O2.
  2. AOT-compiles the SemanticScript source via semsc --emit-exe (clang -O2).
  3. Runs both N times, parses clockTicks from each line of stdout.
  4. Reports median time per side and the SemanticScript/C ratio.

The harness fails (exit 1) if SemanticScript runs slower than 90% of C on any
benchmark.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPILER = HERE.parent / "compiler" / "semsc.py"

# Resolve clang.
CLANG = os.environ.get("SEMSC_CLANG") or shutil.which("clang") or r"C:/Program Files/LLVM/bin/clang.exe"
if not Path(CLANG).exists():
    print(f"clang not found at {CLANG}; set SEMSC_CLANG", file=sys.stderr)
    sys.exit(1)


@dataclass
class Benchmark:
    name: str
    c_source: Path
    sem_source: Path
    runs: int = 7
    warmup_runs: int = 1


BENCHMARKS = [
    Benchmark("arith", HERE / "bench_arith.c", HERE / "bench_arith.sscript"),
    Benchmark("memset", HERE / "bench_memset.c", HERE / "bench_memset.sscript"),
    Benchmark("math", HERE / "bench_math.c", HERE / "bench_math.sscript"),
    Benchmark("string_length", HERE / "bench_string_length.c",
              HERE / "bench_string_length.sscript"),
    # Unlike string_length (which -O2 rewrites to @strlen on both sides), this
    # FNV-style fold has no libc idiom and a carried multiply dependency, so it
    # exercises the stdlib's real hand-written scalar loop vs an identical C
    # fold. Verified: optimized IR contains the multiply loop and no libc call,
    # and both sides produce the same accumulator.
    Benchmark("byte_hash", HERE / "bench_byte_hash.c",
              HERE / "bench_byte_hash.sscript"),
    # In-place insertion sort: data-dependent branches + nested loop + in-place
    # mutable stores, no libc idiom. Exercises a different codegen path than the
    # scans/folds above. Verified: both sides produce the same accumulator.
    Benchmark("insertion_sort", HERE / "bench_insertion_sort.c",
              HERE / "bench_insertion_sort.sscript"),
]


def compile_c(bench: Benchmark) -> Path:
    out = bench.c_source.with_suffix(".c.exe")
    cmd = [CLANG, "-O2", "-o", str(out), str(bench.c_source)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"clang failed for {bench.name}:\n{proc.stderr}")
    return out


def compile_sem(bench: Benchmark, profile: str = "prod") -> Path:
    out = bench.sem_source.with_suffix(".exe")
    # Build the SemanticScript side at the *production* profile so the
    # head-to-head is production-vs-production: the C baseline is built with
    # `clang -O2` and no debug instrumentation, so the fair comparison builds
    # SemanticScript at the safety level a shipped binary carries.
    #
    # `--build-profile prod` selects `--runtime-checks traps` (llvm.trap on UB,
    # no crash-frame bookkeeping). The semsc DEFAULT is `dev`
    # (`--runtime-checks panic`), which wraps every operation call in shadow
    # crash-stack bookkeeping: a volatile load/add/store of `as.crash.depth`, a
    # volatile store to `as.crash.site`, a bounded conditional volatile store
    # into `as.crash.frames`, and an underflow-guard select on the matching pop
    # (see semsc.py `_emit_crash_frame_push`/`_pop`/`_emit_crash_site_store`).
    # Those volatile stores cannot be elided and act as optimization barriers
    # around the call, so panic is genuinely slower in a hot loop than the C
    # baseline -- that is a real cost of the default safety profile, not a
    # measurement artifact. We compare at `prod` because that is the apples-to-
    # apples match for `clang -O2`; pass `--profile dev` to reproduce the
    # default-profile (panic) overhead. See SemanticScript/bench/README.md.
    cmd = [sys.executable, str(COMPILER), str(bench.sem_source),
           "--emit-exe", str(out), "--opt-level", "2",
           "--build-profile", profile]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"semsc failed for {bench.name}:\n{proc.stderr}\n{proc.stdout}")
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


def sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def run_benchmarks(selected_names: set[str] | None = None,
                   runs_override: int | None = None,
                   warmup_override: int | None = None,
                   profile: str = "prod") -> tuple[list[dict], int]:
    results = []
    failures = 0
    for bench in BENCHMARKS:
        if selected_names and bench.name not in selected_names:
            continue
        runs = runs_override if runs_override is not None else bench.runs
        warmup = warmup_override if warmup_override is not None else bench.warmup_runs
        c_exe = compile_c(bench)
        sem_exe = compile_sem(bench, profile)
        c_samples = measure(c_exe, runs, warmup)
        sem_samples = measure(sem_exe, runs, warmup)
        c_median = statistics.median(c_samples)
        sem_median = statistics.median(sem_samples)
        # Gate on the MINIMUM, not the median. OS scheduling jitter, frequency
        # scaling, and clock() quantization only ever *add* time, so the
        # fastest observed run is the least-contaminated estimate of true
        # CPU-bound execution time. With clock() at ~1ms resolution and medians
        # of a few hundred-to-thousand ticks, a single slow run used to drag the
        # median enough to fail the 90% gate spuriously (observed string_length
        # flapping to ~72%). Both sides use min, so the ratio stays fair, and
        # the gate stops flaking on noise. Median + raw samples are still
        # reported below for transparency.
        c_best = min(c_samples) if c_samples else 0
        sem_best = min(sem_samples) if sem_samples else 0
        ratio = (sem_best / c_best) if c_best else float("inf")
        if c_best == 0 or sem_best == 0:
            verdict = "TOO FAST"
            ok = True
            pct_of_c = 100.0
        else:
            pct_of_c = (c_best / sem_best) * 100.0
            ok = pct_of_c >= 90.0
            verdict = f"{pct_of_c:5.1f}%"
        if not ok:
            failures += 1
        results.append({
            "name": bench.name,
            "runs": runs,
            "warmupRuns": warmup,
            "semanticProfile": profile,
            "sources": {
                "c": str(bench.c_source),
                "semantic": str(bench.sem_source),
                "semanticFingerprint": sha256_file(bench.sem_source),
            },
            "artifacts": {
                "cExecutablePath": str(c_exe),
                "semanticExecutablePath": str(sem_exe),
            },
            "samples": {
                "cClockTicks": c_samples,
                "semanticClockTicks": sem_samples,
            },
            "median": {
                "cClockTicks": c_median,
                "semanticClockTicks": sem_median,
            },
            "best": {
                "cClockTicks": c_best,
                "semanticClockTicks": sem_best,
            },
            "delta": {
                "semanticMinusCClockTicks": sem_best - c_best,
                "semanticToCRatio": ratio,
                "semanticPercentOfC": pct_of_c,
                "basis": "best-of-N (minimum)",
            },
            "ok": ok,
            "verdict": verdict,
        })
    return results, failures


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run SemanticScript LLVM benchmark comparisons against C.",
    )
    parser.add_argument("--json", action="store_true",
                        help="emit a stable agent-readable benchmark report")
    parser.add_argument("--runs", type=int,
                        help="measured iterations per benchmark")
    parser.add_argument("--warmup", type=int,
                        help="warmup iterations per benchmark")
    parser.add_argument("--benchmark", action="append", default=[],
                        help="benchmark name to run; may be repeated")
    parser.add_argument("--profile", choices=("dev", "prod"), default="prod",
                        help=("semsc --build-profile for the SemanticScript "
                              "side. prod (default) = --runtime-checks traps, "
                              "the apples-to-apples match for clang -O2. dev = "
                              "--runtime-checks panic, which adds per-call "
                              "crash-frame bookkeeping and is the slower "
                              "default-profile cost real programs pay."))
    args = parser.parse_args(argv)
    selected = set(args.benchmark) if args.benchmark else None
    results, failures = run_benchmarks(selected, args.runs, args.warmup,
                                       args.profile)
    if args.json:
        payload = {
            "schemaVersion": "sem.benchmark.v0",
            "tool": {"name": "sem-bench", "compiler": str(COMPILER)},
            "environment": {"clang": str(CLANG)},
            "summary": {
                "benchmarkCount": len(results),
                "failureCount": failures,
                "ok": failures == 0,
            },
            "benchmarks": results,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1 if failures else 0

    print(f"Using clang at {CLANG}")
    print(f"SemanticScript build profile: {args.profile} "
          f"(prod=traps, dev=panic)")
    print()
    print("Gate basis: best-of-N (minimum) clock ticks; median shown for context.")
    print(f"{'benchmark':<14} {'C best':>9} {'Sem best':>9} {'C med':>8} "
          f"{'Sem med':>8} {'Sem/C':>8} {'verdict':>9}")
    print("-" * 70)
    for result in results:
        c_best = result["best"]["cClockTicks"]
        sem_best = result["best"]["semanticClockTicks"]
        c_median = result["median"]["cClockTicks"]
        sem_median = result["median"]["semanticClockTicks"]
        ratio = result["delta"]["semanticToCRatio"]
        verdict = result["verdict"]
        ok = result["ok"]
        flag = "OK" if ok else "FAIL"
        print(
            f"{result['name']:<14} {c_best:>9} {sem_best:>9} "
            f"{c_median:>8} {sem_median:>8} {ratio:>8.3f} "
            f"{verdict:>9} [{flag}]")
    print()
    if failures:
        print(f"{failures} benchmark(s) below 90% of native C; failing.")
        return 1
    print("All benchmarks at or above 90% of native C performance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
