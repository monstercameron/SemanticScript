# Cross-language algorithm benchmarks

Head-to-head performance of the **SemanticScript prototype toolchain** against
**C**, **JavaScript (Node)**, and **Python (CPython)** on well-known algorithms.

Each algorithm has four implementations of the same logic:

```
<algorithm>.c        C baseline       (clang -O2)
<algorithm>.sscript  SemanticScript   (semsc --emit-exe --opt-level 2 -> clang -O2)
<algorithm>.js       JavaScript       (Node)
<algorithm>.py       Python           (CPython)
```

Run everything with `python ../run_multilang.py` (add `--json` for a
machine-readable report, `--algorithm <name>` to select one).

> For the full narrative write-up — methodology rationale, the floating-point
> and 32-bit-bitwise gotchas, per-algorithm analysis, and how to read the
> results responsibly — see [`BENCHMARK_NOTES.md`](BENCHMARK_NOTES.md).

## Algorithms

| Algorithm        | Stresses                                     | Workload                                  | Checksum (all four agree) |
|------------------|----------------------------------------------|-------------------------------------------|---------------------------|
| `fib_recursive`  | Function-call / recursion overhead           | `fib(39)`                                 | `63245986`                |
| `collatz`        | Integer arithmetic + data-dependent branches | sum of stopping times, starts 1..1 000 000 | `131434424`              |
| `sieve`          | Byte-array memory throughput                 | Sieve to 2 000 000, ×40 repeats           | `5957320` (40 × 148 933)  |
| `mandelbrot`     | Double-precision float compute               | 600×400 grid, 1000 iteration cap          | `61930405`                |

## Methodology

**Self-timed compute regions.** Each program times only its compute loop with
the best monotonic clock available to that language and prints one line:

```
checksum=<int> elapsedSeconds=<float>
```

This deliberately excludes process startup and JIT warm-up of the interpreter
process (Node/CPython launch cost would otherwise dominate the fast cases and
measure the OS, not the language). The harness runs each program `warmup + N`
times (default 9 measured, 2 warm-up) and reports **min, median, and relative
standard deviation**, so "tied with C" can be judged against the actual spread.

**Clocks.**

| Language       | Timer                       | Resolution        |
|----------------|-----------------------------|-------------------|
| C              | `QueryPerformanceCounter`   | sub-microsecond   |
| JavaScript     | `performance.now()`         | sub-millisecond   |
| Python         | `time.perf_counter()`       | sub-microsecond   |
| SemanticScript | libc `clock()`              | **1 ms** (Windows)|

SemanticScript can only reach libc `clock()` today, so it is the one coarse
timer. Every algorithm is therefore sized so the SemanticScript run stays well
above ~100 ms, holding its quantization error at or below ~1%. The 1 ms
conversion uses Windows `CLOCKS_PER_SEC = 1000`, hard-coded in the `.sscript`
sources (documented in each file's invariants).

**Correctness cross-check.** The harness asserts that all four languages report
the **same checksum** for each algorithm. If they diverge, the run is flagged
and the timings are not comparable. This is what makes the comparison
trustworthy: every language is verified to compute the same result, not just
"a benchmark by the same name." For `mandelbrot` this required writing each
floating-point step as a separate temporary in all four languages so no
compiler fuses a multiply-add (FMA) and changes the rounding — with that, all
four produce bit-identical escape counts.

**Same task, idiomatic per language.** Each implementation is the *fastest
faithful* version a competent developer would write in that language, not a
mechanical transliteration of the C source. They run the same algorithm and
produce the same checksum, but the in-language mechanics differ where idiom
matters for speed (see "Per-language implementation notes" below). The most
visible case is the Python sieve, which strikes out composites with strided
slice assignment instead of a Python-level loop.

**Fairness for the compiled pair.** Both C and SemanticScript are lowered to
LLVM IR and compiled with `clang -O2`. The C-vs-SemanticScript ratio therefore
isolates the quality of the IR the prototype generates — and for loop bodies the
generated machine code is *instruction-identical* to C (see the assembly
walk-through in [`BENCHMARK_NOTES.md`](BENCHMARK_NOTES.md#the-proof-identical-machine-code)).

## Results

Host: Windows 11, clang 22.1.4, Node v25, CPython 3.10.11, otherwise idle.
Median of 9 runs (2 warm-ups), with JS and Python in their optimized idiomatic
form. Numbers will vary by machine; regenerate with `run_multilang.py`.

| Algorithm       | C          | SemanticScript | JavaScript | Python      |
|-----------------|-----------:|---------------:|-----------:|------------:|
| `fib_recursive` | 1.00×      | **1.16×**      | 3.87×      | 83.7×       |
| `collatz`       | 1.00×      | **0.98×**      | 8.75×      | 65.1×       |
| `sieve`         | 1.00×      | **1.00×**      | 1.41×      | 5.54×       |
| `mandelbrot`    | 1.00×      | **0.98×**      | 1.04×      | 48.2×       |

(× = slowdown relative to C; lower is faster. The compiled-pair std-devs are
~0.5–2.6%, so collatz/sieve/mandelbrot are statistically tied with C; fib is a
real gap.)

Absolute medians (seconds) with relative standard deviation:

| Algorithm       | C (rsd)      | SemanticScript | JavaScript | Python        |
|-----------------|-------------:|---------------:|-----------:|--------------:|
| `fib_recursive` | 0.110 (0.5%) | 0.128 (1.2%)   | 0.427      | 9.223         |
| `collatz`       | 0.125 (0.6%) | 0.122 (0.8%)   | 1.094      | 8.133         |
| `sieve`         | 0.120 (0.7%) | 0.119 (2.6%)   | 0.168      | 0.662         |
| `mandelbrot`    | 0.142 (0.5%) | 0.139 (0.8%)   | 0.148      | 6.853         |

## What the numbers say

- **No abstraction tax in compiled loops — proven, not just timed.** On collatz,
  sieve, and mandelbrot SemanticScript is statistically tied with C, and the
  reason is concrete: `clang -O2` emits the *same inner-loop machine code* for
  SemanticScript and C (instruction-identical modulo register allocation; see the
  assembly section in the notes). Safety checks the language inserts are proven
  unnecessary and hoisted out of hot loops at zero cost.

- **The one real gap is recursion** (`fib_recursive`, 1.16×). This is outside the
  measurement noise (SemanticScript 0.125–0.128 s vs C 0.109–0.110 s, no overlap),
  so it's a genuine finding: with trivial loop bodies, the ~16% is per-call
  overhead — the prototype's calling convention or result/error binding does more
  work per frame than C's bare `call`/`ret`. The most actionable codegen target.

- **JIT vs interpreter.** Node is within ~4% of C on float-heavy `mandelbrot` and
  ~1.4× on memory-bound `sieve`, but pays 4–9× on tight integer/recursion loops
  where number-boxing and call overhead show. CPython ranges from 5.5× to 84× —
  the spread is the story: it is ~80× slower when work stays in the bytecode
  interpreter (`fib_recursive`), but only ~5.5× on `sieve` once the hot path is
  bulk C-level operations. The lesson for dynamic languages: speed comes from
  pushing the inner loop out of the interpreter and into the runtime's C core.

## Per-language implementation notes

Each language uses the fastest faithful form of the algorithm. The notable
choices, and the optimizations deliberately *not* taken:

- **`fib_recursive` (all):** kept genuinely recursive. Memoization or an
  iterative rewrite would be faster but would defeat the benchmark, whose
  entire purpose is to measure function-call overhead.
- **`sieve` (all):** identical structure in every language — start all-prime,
  strike out composites for primes up to √limit, then count survivors. The only
  difference is the bulk primitive: C/JS/SemanticScript walk each prime's
  multiples in a loop, while Python uses a strided slice assignment
  (`sieve[start::step] = b"\x00" * count`) and `sum()`, its idiomatic C-level
  way to do the same passes (~10× faster than the per-element Python loop it
  replaced).
- **Python `collatz`:** uses bitwise `value & 1` / `value >> 1`, which is correct
  for Python's arbitrary-precision ints and faster than `% 2` / `// 2`.
- **JavaScript `collatz`:** must use arithmetic (`% 2`, `/ 2`), *not* bitwise
  operators — JS bitwise ops truncate to 32 bits and Collatz peaks exceed 2³¹,
  so a bitwise version would silently produce wrong values. Plain numbers are
  exact here because every value stays below 2⁵³.
- **JavaScript (all):** hot code is wrapped in a `main()` function so V8 reliably
  JIT-optimizes it; `sieve` uses a `Uint8Array`. These were already near-optimal,
  so JS times barely moved after optimization.
- **`mandelbrot` (all):** every float operation is a separate statement in a
  fixed order so no compiler fuses a multiply-add; this is required for
  bit-identical checksums and costs nothing measurable. Python is left as pure
  scalar CPython — NumPy would be faster but measures a C/SIMD library, not the
  language, so it is out of scope (as are PyPy and other alternative runtimes).

## Caveats

- These are **microbenchmarks**, not a language conformance suite or a verdict
  on real-world throughput. They measure tight compute kernels only.
- SemanticScript's 1 ms timer is the weakest link in the methodology; workloads
  are sized to ~120–140 ms so quantization stays ~1%, but it is coarser than the
  other three clocks (and shows up as its slightly higher std-dev).
- Workloads are sized so SemanticScript stays above ~100 ms, which in turn keeps
  CPython's slowest tests (~6–9 s) from making the suite tediously long.
- Results are single-host. Re-run on the target machine before quoting numbers.
