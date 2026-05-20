# Bench

Benchmark programs for comparing SemanticScript lowering against small C
baselines.

## Contents

- `bench_*.sscript` files are SemanticScript benchmark sources.
- `bench_*.c` files are comparable C baselines.
- `run_benchmarks.py` builds/runs benchmark cases.
- `probe_clocks.c` is a small timing support probe.

## Current Status

Performance investigation area. These benchmarks are useful for optimizer and
backend work, but they should not be treated as language conformance tests.

## Maintenance

Keep benchmark pairs small and focused. When changing codegen or optimization,
run the benchmark runner only after correctness tests pass.

## Baseline Storage

Local benchmark captures belong outside normal source history unless a change is
intentionally adding a reviewed baseline. Use ignored scratch paths such as
`SemanticScript/bench/baselines.local/` or `.semcache/bench/` for investigation
runs.

Committed baselines, if added later, should live under
`SemanticScript/bench/baselines/` with the benchmark name, compiler/toolchain
versions, host platform, run count, and rationale in the same review.
