"""run_multilang.py - cross-language algorithm benchmark harness.

Compares the SemanticScript prototype toolchain against C, JavaScript (Node),
and Python on a small set of well-known algorithms. For each algorithm there
are four source files in ``algorithms/`` named ``<algorithm>.{c,js,py,sscript}``.

Contract every program obeys: it runs the algorithm, times only the compute
region with that language's best monotonic clock, and prints a single line:

    checksum=<int> elapsedSeconds=<float>

The harness:
  1. Builds the C source with clang -O2 and the SemanticScript source via
     semsc --emit-exe --opt-level 2 (which also calls clang -O2). JS and Python
     run from source.
  2. Runs each language warmup + N times and records elapsedSeconds + checksum.
  3. Cross-checks that all four languages reported the SAME checksum for the
     algorithm. A mismatch means the implementations diverged and the timings
     are not comparable, so it is flagged loudly.
  4. Reports min / median / relative standard deviation per language and the
     slowdown factor relative to C (median_lang / median_c). Default 9 runs +
     2 warm-ups; raise with --runs for steadier numbers.

Timing note: C, JS, and Python use sub-microsecond clocks. SemanticScript can
only reach libc clock() (1 ms resolution on Windows), so each algorithm is
sized so the SemanticScript runtime stays well above ~100 ms, keeping its
quantization error near or below 1%.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALGO_DIR = HERE / "algorithms"
COMPILER = HERE.parent / "compiler" / "semsc.py"

CLANG = os.environ.get("SEMSC_CLANG") or shutil.which("clang") or r"C:/Program Files/LLVM/bin/clang.exe"
NODE = os.environ.get("NODE") or shutil.which("node") or "node"

# Display order: C baseline first, then the SemanticScript prototype, then the
# two mainstream dynamic languages.
LANGUAGE_ORDER = ["c", "semanticscript", "javascript", "python"]
LANGUAGE_LABELS = {
    "c": "C (clang -O2)",
    "semanticscript": "SemanticScript",
    "javascript": "JavaScript (Node)",
    "python": "Python (CPython)",
}


@dataclass
class Algorithm:
    name: str
    description: str
    runs: int = 9
    warmup_runs: int = 2
    sources: dict = field(default_factory=dict)


ALGORITHMS = [
    Algorithm("fib_recursive",
              "Naive recursive Fibonacci - function-call / recursion overhead."),
    Algorithm("collatz",
              "Sum of Collatz stopping times - integer, branch-heavy loops."),
    Algorithm("sieve",
              "Sieve of Eratosthenes - byte-array memory throughput."),
    Algorithm("mandelbrot",
              "Escape-time Mandelbrot - double-precision float compute."),
]


def source_path(algorithm: str, suffix: str) -> Path:
    return ALGO_DIR / f"{algorithm}.{suffix}"


def build_c(algorithm: str) -> Path:
    src = source_path(algorithm, "c")
    out = ALGO_DIR / f"{algorithm}.c.exe"
    proc = subprocess.run([CLANG, "-O2", "-o", str(out), str(src)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"clang failed for {algorithm}:\n{proc.stderr}")
    return out


def build_semanticscript(algorithm: str) -> Path:
    src = source_path(algorithm, "sscript")
    out = ALGO_DIR / f"{algorithm}.exe"
    proc = subprocess.run(
        [sys.executable, str(COMPILER), str(src),
         "--emit-exe", str(out), "--opt-level", "2"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"semsc failed for {algorithm}:\n{proc.stderr}\n{proc.stdout}")
    return out


def run_commands(algorithm: str) -> dict:
    """Map each language to the command that runs its build/source."""
    return {
        "c": [str(build_c(algorithm))],
        "semanticscript": [str(build_semanticscript(algorithm))],
        "javascript": [NODE, str(source_path(algorithm, "js"))],
        "python": [sys.executable, str(source_path(algorithm, "py"))],
    }


def parse_output(stdout: str) -> tuple[int, float]:
    checksum = None
    elapsed = None
    for token in stdout.split():
        if token.startswith("checksum="):
            checksum = int(token.split("=", 1)[1])
        elif token.startswith("elapsedSeconds="):
            elapsed = float(token.split("=", 1)[1])
    if checksum is None or elapsed is None:
        raise ValueError(f"could not parse benchmark line: {stdout!r}")
    return checksum, elapsed


def measure(command: list[str], runs: int, warmup: int) -> tuple[list[float], int]:
    samples: list[float] = []
    checksums: set[int] = set()
    for _ in range(warmup):
        subprocess.run(command, capture_output=True, text=True, check=True)
    for _ in range(runs):
        proc = subprocess.run(command, capture_output=True, text=True, check=True)
        checksum, elapsed = parse_output(proc.stdout)
        samples.append(elapsed)
        checksums.add(checksum)
    if len(checksums) != 1:
        raise RuntimeError(f"non-deterministic checksum across runs: {checksums}")
    return samples, checksums.pop()


def run_suite(selected: set[str] | None, runs_override: int | None,
              warmup_override: int | None) -> list[dict]:
    results = []
    for algorithm in ALGORITHMS:
        if selected and algorithm.name not in selected:
            continue
        runs = runs_override if runs_override is not None else algorithm.runs
        warmup = warmup_override if warmup_override is not None else algorithm.warmup_runs

        commands = run_commands(algorithm.name)
        per_language = {}
        checksums = {}
        for language in LANGUAGE_ORDER:
            samples, checksum = measure(commands[language], runs, warmup)
            median = statistics.median(samples)
            stddev = statistics.stdev(samples) if len(samples) > 1 else 0.0
            per_language[language] = {
                "samples": samples,
                "min": min(samples),
                "median": median,
                "stddev": stddev,
                "stddevPct": (100.0 * stddev / median) if median else 0.0,
            }
            checksums[language] = checksum

        checksum_values = set(checksums.values())
        checksum_ok = len(checksum_values) == 1
        baseline = per_language["c"]["median"]
        for language in LANGUAGE_ORDER:
            median = per_language[language]["median"]
            per_language[language]["slowdownVsC"] = (
                median / baseline if baseline else float("inf"))

        results.append({
            "algorithm": algorithm.name,
            "description": algorithm.description,
            "runs": runs,
            "warmupRuns": warmup,
            "checksumOk": checksum_ok,
            "checksums": checksums,
            "languages": per_language,
        })
    return results


def print_report(results: list[dict]) -> None:
    print(f"clang: {CLANG}")
    print(f"node:  {NODE}")
    print(f"python: {sys.version.split()[0]}")
    print()
    for result in results:
        status = "checksums match" if result["checksumOk"] else "CHECKSUM MISMATCH"
        print(f"## {result['algorithm']}  ({status})")
        print(f"   {result['description']}")
        if not result["checksumOk"]:
            print(f"   checksums: {result['checksums']}")
        print(f"   {'language':<20} {'min sec':>10} {'median sec':>12} "
              f"{'stddev':>10} {'vs C':>9}")
        print("   " + "-" * 64)
        for language in LANGUAGE_ORDER:
            entry = result["languages"][language]
            label = LANGUAGE_LABELS[language]
            print(f"   {label:<20} {entry['min']:>10.6f} {entry['median']:>12.6f} "
                  f"{entry['stddevPct']:>9.1f}% {entry['slowdownVsC']:>8.2f}x")
        print()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true",
                        help="emit a machine-readable JSON report")
    parser.add_argument("--runs", type=int, help="measured iterations per language")
    parser.add_argument("--warmup", type=int, help="warmup iterations per language")
    parser.add_argument("--algorithm", action="append", default=[],
                        help="algorithm name to run; may be repeated")
    args = parser.parse_args(argv)

    if not Path(CLANG).exists():
        print(f"clang not found at {CLANG}; set SEMSC_CLANG", file=sys.stderr)
        return 1

    selected = set(args.algorithm) if args.algorithm else None
    results = run_suite(selected, args.runs, args.warmup)
    any_mismatch = any(not r["checksumOk"] for r in results)

    if args.json:
        payload = {
            "schemaVersion": "sem.multilang-benchmark.v0",
            "environment": {
                "clang": CLANG,
                "node": NODE,
                "python": sys.version.split()[0],
            },
            "summary": {
                "algorithmCount": len(results),
                "checksumMismatchCount": sum(1 for r in results if not r["checksumOk"]),
            },
            "algorithms": results,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_report(results)

    return 1 if any_mismatch else 0


if __name__ == "__main__":
    raise SystemExit(main())
