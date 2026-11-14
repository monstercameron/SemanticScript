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

## Fair Comparison: Build At The Production Profile

`run_benchmarks.py` builds the SemanticScript side with `--build-profile prod`
on purpose. The C baselines are `clang -O2` with no debug instrumentation, so a
fair head-to-head must compile SemanticScript at the safety level a shipped
binary actually carries.

The default semsc profile is `dev`, which sets `--runtime-checks panic`. Panic
mode wraps **every operation call** in shadow crash-stack bookkeeping: a
volatile load/add/store of `as.crash.depth`, a volatile store to
`as.crash.site`, a bounded conditional volatile store into `as.crash.frames`,
and an underflow-guard select on the matching pop (see semsc.py
`_emit_crash_frame_push` / `_emit_crash_frame_pop` / `_emit_crash_site_store`).
Those volatile stores cannot be elided and act as optimization barriers around
the call. (Any `llvm.stacksave` / `llvm.stackrestore` you see in panic IR are
LLVM inlining artifacts, not semsc-injected per-call bookkeeping.)

This overhead is **real**, not a measurement artifact: it is the cost of the
default safety profile that dev builds actually ship. We benchmark at `prod`
only because that is the apples-to-apples match for `clang -O2`. Pass
`--profile dev` to `run_benchmarks.py` to measure the default-profile cost (for
`string_length`, ~82% of C under `panic` vs ~95-100% under `prod`/`traps`).

When adding a benchmark, do not "optimize" the SemanticScript source to chase a
number that is really a profile mismatch — first confirm both sides are built at
comparable safety levels.

### What `string_length` actually measures (and a caveat)

At `--opt-level 2`, LLVM's loop-idiom pass rewrites `stringByteLength`'s scalar
byte scan into a `tail call @strlen`, and the C side calls `strlen` directly.
So `string_length` measures **call/inline/profile parity between equivalent
stdlib and C calls that both become `@strlen`** — it does *not* exercise the
stdlib's hand-written scalar loop on the CPU. That parity is worth tracking on
its own.

The `byte_hash` benchmark is the companion that *does* exercise real stdlib
scalar codegen: it times `standard.memory.hashMemoryBytesWithFnv1a` (an FNV-style
per-byte fold) against an identical C fold. An FNV fold has no libc idiom and a
carried `hash = hash * prime` dependency, so LLVM cannot rewrite it into a
library call and cannot vectorize it — both sides run the same scalar loop. This
was verified: the optimized SemanticScript IR's **timed hot loop** contains the
`mul i64` fold and *no* `strlen`/`strspn` (or any libc string) call rewriting it
— the scan runs as a real scalar loop. (The module still contains a `llvm.memcpy`
for the one-time buffer seed and `llvm.memset` inside unrelated stdlib ops, both
*outside* the `clock()`-timed region.) Both binaries print the same accumulator,
proving identical work. It lands at ~98% of C, i.e. the stdlib's scalar lowering
is at parity with hand-written C.

`insertion_sort` is a third real-codegen benchmark covering a different path:
`standard.sort.sortBytesWithInsertionSortInPlace` (data-dependent branches, a
nested loop, in-place mutable stores) vs an identical C insertion sort. It also
has no libc idiom, both sides produce the same accumulator, and it lands at
~98-102% of C. Together with `byte_hash` this shows the stdlib's scan, fold, and
branchy-mutate codegen are all at parity with hand-written C.

### Timer resolution caveat

The benchmarks time with `clock()`. On this Windows host `CLOCKS_PER_SEC=1000`
(1 ms ticks), and tick counts land in the hundreds-to-low-thousands, so a single
slow run carries a few percent of noise. To keep the gate from flaking on that,
the harness gates on the **minimum** (best-of-N) ticks, not the median: OS
jitter and clock quantization only ever add time, so the fastest run is the
least-contaminated estimate and a slow outlier can no longer fail the build.
Both sides use the minimum, so the ratio stays fair; median and raw samples are
still reported for context. Treat sub-~10% differences as noise regardless.

**TODO (proper fix):** switch to a high-resolution monotonic timer
(`QueryPerformanceCounter` / `clock_gettime(CLOCK_MONOTONIC)`) and/or raise
iteration counts so even the median reaches the 10⁴–10⁵-tick range, and report
variance. Best-of-N hardens the gate against jitter but does not improve the
underlying 1 ms resolution.

### Retired: `bench_strlen`

The old `bench_strlen` reported `clockTicks=0` on both sides — it called
`c.strlen` on a loop-invariant `getenv("PATH")` string, which `-O2` hoisted out
of the loop, so it measured nothing while the harness scored `0/0` as a passing
`TOO FAST` and inflated apparent coverage. It has been retired (removed from
`BENCHMARKS` and deleted); `string_length` is the meaningful, hoist-resistant
strlen comparison that replaces it.

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
