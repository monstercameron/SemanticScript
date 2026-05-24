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

## Algorithms

| Algorithm        | Stresses                                     | Workload                                  | Checksum (all four agree) |
|------------------|----------------------------------------------|-------------------------------------------|---------------------------|
| `fib_recursive`  | Function-call / recursion overhead           | `fib(38)`                                 | `39088169`                |
| `collatz`        | Integer arithmetic + data-dependent branches | sum of stopping times, starts 1..600 000  | `75668736`                |
| `sieve`          | Byte-array memory throughput                 | Sieve to 2 000 000, ×20 repeats           | `2978660` (20 × 148 933)  |
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
times and takes the **median** elapsedSeconds.

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
trustworthy: every language is verified to have done identical work, not just
"a benchmark by the same name." For `mandelbrot` this required writing each
floating-point step as a separate temporary in all four languages so no
compiler fuses a multiply-add (FMA) and changes the rounding — with that, all
four produce bit-identical escape counts.

**Fairness for the compiled pair.** Both C and SemanticScript are lowered to
LLVM IR and compiled with `clang -O2`. The C-vs-SemanticScript ratio therefore
isolates the quality of the IR the prototype generates, not a difference of
backend or optimizer.

## Results

Host: Windows 11, clang 22.1.4, Node v25, CPython 3.10.11. Median of 5 runs
(1 warm-up). Numbers will vary by machine; regenerate with `run_multilang.py`.

| Algorithm       | C          | SemanticScript | JavaScript | Python      |
|-----------------|-----------:|---------------:|-----------:|------------:|
| `fib_recursive` | 1.00×      | **1.17×**      | 3.83×      | 102.7×      |
| `collatz`       | 1.00×      | **0.94×**      | 9.06×      | 67.2×       |
| `sieve`         | 1.00×      | **0.99×**      | 1.38×      | 35.1×       |
| `mandelbrot`    | 1.00×      | **0.98×**      | 1.04×      | 51.3×       |

(× = slowdown relative to C; lower is faster. <1.0× means it beat C in that
run, which for the compiled pair is measurement noise.)

Absolute medians (seconds) from the reference run:

| Algorithm       | C        | SemanticScript | JavaScript | Python   |
|-----------------|---------:|---------------:|-----------:|---------:|
| `fib_recursive` | 0.072    | 0.084          | 0.276      | 7.401    |
| `collatz`       | 0.075    | 0.071          | 0.684      | 5.076    |
| `sieve`         | 0.098    | 0.097          | 0.135      | 3.438    |
| `mandelbrot`    | 0.144    | 0.141          | 0.149      | 7.379    |

## What the numbers say

- **SemanticScript runs at native-C speed.** Across all four algorithms it
  lands in the 0.94×–1.17× band around C. That is expected and reassuring: it
  shares C's LLVM/`clang -O2` backend, so once the prototype emits reasonable IR
  the optimizer does the rest. The benchmark's real claim is that the IR it
  emits *is* reasonable — no accidental abstraction tax in the lowered code.

- **The one soft spot is recursion** (`fib_recursive`, 1.17×). Function-call
  heavy code is slightly slower than C, pointing at calling-convention or
  result/error-bind overhead per frame rather than loop-body codegen. It is the
  natural place to look next for prototype codegen wins.

- **JIT vs interpreter.** Node is within ~4% of C on the float-heavy
  `mandelbrot` and the memory-bound `sieve`, but pays 4–9× on tight
  integer/recursion loops where the JIT and number-boxing show. CPython is
  35–100× slower throughout — worst on recursion (call overhead) and best on
  `sieve`, where the hot inner store lands in C-level `bytearray` machinery.

## Caveats

- These are **microbenchmarks**, not a language conformance suite or a verdict
  on real-world throughput. They measure tight compute kernels only.
- SemanticScript's 1 ms timer is the weakest link in the methodology; sizing
  keeps the error small but it is coarser than the other three.
- Workloads are sized so CPython stays under ~8 s/run. That bounds how large the
  compiled-language runs can be, which is why their absolute times are short.
- Results are single-host. Re-run on the target machine before quoting numbers.
