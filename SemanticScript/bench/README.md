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
