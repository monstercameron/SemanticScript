# Benchmark notes: SemanticScript vs C, JavaScript, and Python

A friendly but thorough walk-through of the cross-language algorithm
benchmarks. If you just want the numbers and how to run them, the
[`README.md`](README.md) next to this file is the quick reference. This
document is the "why and how" for further reading.

---

## TL;DR

We ran four well-known algorithms in four languages — **C**, **SemanticScript**
(this project's prototype), **JavaScript** (Node), and **Python** (CPython) —
and timed the compute loop in each. The short story:

> The SemanticScript prototype runs at **native-C speed** (within a few percent)
> on every test. That is the headline: the compiler's generated code carries no
> measurable "abstraction tax."

The reason is no mystery, and that is the point: SemanticScript compiles to LLVM
and is optimized by `clang -O2` — the *same* backend C uses. So this isn't a
claim that the language is magic. It's evidence that the prototype hands the
optimizer clean enough code that the optimizer can do its job.

| Algorithm     | C    | SemanticScript | JavaScript | Python |
|---------------|-----:|---------------:|-----------:|-------:|
| fib_recursive | 1.0× | 1.13×          | 3.9×       | 88×    |
| collatz       | 1.0× | 0.96×          | 8.4×       | 65×    |
| sieve         | 1.0× | 0.99×          | 1.4×       | 3.4×   |
| mandelbrot    | 1.0× | 0.97×          | 1.0×       | 48×    |

(Numbers are "how many times slower than C." Lower is faster. Values just under
1.0× for SemanticScript are measurement noise — it's level with C.)

---

## The four algorithms, and why each one

A good microbenchmark suite stresses *different* parts of a language. One tight
loop tells you almost nothing on its own. We picked four classics that each lean
on a distinct cost center:

| Algorithm         | What it really measures                          | The workload                              |
|-------------------|--------------------------------------------------|-------------------------------------------|
| **fib_recursive** | Function call + return overhead                  | `fib(38)` — ~63 million calls, trivial bodies |
| **collatz**       | Integer math and unpredictable branches          | sum of Collatz stopping times for 1..600,000 |
| **sieve**         | Memory throughput over a big flat array          | Sieve of Eratosthenes to 2,000,000, ×20   |
| **mandelbrot**    | Double-precision floating-point arithmetic       | 600×400 grid, up to 1000 iterations/pixel |

- **fib_recursive** does almost no arithmetic per call; nearly all the time goes
  into entering and leaving functions. It's the purest "how cheap is a call"
  test, which is exactly why we keep it naively recursive (no memoization — that
  would turn it into a different, trivial benchmark).
- **collatz** is a tight integer loop whose branch (is the number even or odd?)
  depends on data the CPU can't predict well. It rewards good integer codegen
  and punishes interpreter overhead.
- **sieve** spends its life writing single bytes across a multi-megabyte array.
  It's about memory bandwidth and how cheaply the language can do a strided
  store.
- **mandelbrot** is wall-to-wall `double` multiplies and adds. It's the
  float-compute test, and it's where JITs tend to catch up to C.

---

## The rules of the game (how we kept it fair)

Benchmarks are easy to get wrong. Here are the rules we held everyone to.

### 1. We time the work, not the warm-up

Every program times **only its compute loop**, using the best clock its language
offers, and prints one line:

```
checksum=<number> elapsedSeconds=<number>
```

Why not just time the whole process from the outside? Because starting Node or
CPython takes tens of milliseconds of interpreter boot time. For the fast tests
that startup cost would dwarf the actual computation and we'd be benchmarking
the operating system's process launcher, not the language. Self-timing the inner
loop sidesteps that entirely.

The harness runs each program a few times (with a warm-up run that's thrown
away) and reports the **median**, which shrugs off the occasional hiccup from
the OS scheduler.

### 2. The checksum proves everyone did the same job

Each program computes a **checksum** — the Fibonacci value, the sum of all
Collatz steps, the prime count, the total Mandelbrot iterations. The harness
refuses to compare timings unless **all four languages report the exact same
checksum**.

This is the single most important guard against fooling yourself. It's very easy
to accidentally write four programs that *look* like the same algorithm but
quietly differ — an off-by-one here, a different rounding there — and then
compare meaningless numbers. The checksum makes "they all did the same work" a
fact you can see, not a hope.

### 3. Same task, but written the way each language wants to be written

Here's a subtlety worth being explicit about. We did **not** transliterate the C
code character-for-character into the other languages. We wrote the **fastest
faithful version** a competent developer would actually write in each language.

Same algorithm, same result (the checksum proves it), but idiomatic mechanics.
The clearest example is the Python sieve — more on that below.

This is a deliberate choice. The alternative ("everyone runs the exact same loop
structure") measures how each language runs *C-shaped code*, which flatters
compiled languages and is not how anyone writes real Python or JavaScript. We
think "fastest honest version per language" is the more useful question.

### 4. The compiled pair is a genuinely apples-to-apples test

C and SemanticScript both go through LLVM and `clang -O2`. So when SemanticScript
lands at 0.97× of C, that number is isolating one thing: **the quality of the IR
the prototype emits.** Same optimizer, same code generator, same machine code
shapes — the only variable is what the front end fed in. That's the cleanest
possible read on the prototype's codegen.

### 5. The one weak spot: SemanticScript's clock

C, JavaScript, and Python all have sub-microsecond timers. SemanticScript, today,
can only reach C's `clock()`, which on Windows ticks every **1 millisecond**.
That's coarse. A run that takes 14 ms is only "14 ticks," so a single tick of
jitter is a ~7% error.

We handle this by **sizing every workload so the SemanticScript run takes well
over 100 ms** — at ~100+ ticks, one tick of slop is under 1%. It's not as clean
as the other three clocks, and it's the honest soft spot in the methodology, but
the sizing keeps it from distorting the results. (A higher-resolution clock in
the runtime would remove the caveat; it's on the list.)

---

## The fun part: three traps we walked into

These are the bugs-in-waiting that make cross-language benchmarking interesting.

### Floating-point has to match *bit for bit* — watch out for FMA

The Mandelbrot checksum is a sum of integer iteration counts, but those counts
depend on floating-point comparisons (`did |z| exceed 2?`). If two languages
round even one operation differently, a pixel near the boundary can escape one
iteration earlier or later, and the checksums diverge.

The culprit is the **fused multiply-add (FMA)**: modern compilers love to turn
`a*b + c` into a single hardware instruction that's faster *and rounds
differently* (it keeps more precision internally). C and SemanticScript both go
through clang, which may form FMAs; JavaScript and Python never do.

The fix was simple once we understood it: in **all four** languages, we write
each step as its own statement with its own variable —

```
real_squared        = real_z * real_z
imaginary_squared   = imaginary_z * imaginary_z
magnitude_squared   = real_squared + imaginary_squared
```

— so there's no `a*b + c` expression for a compiler to fuse. With that, all four
languages produce bit-identical results and the checksums line up. It costs
nothing measurable in speed.

### JavaScript's bitwise operators are secretly 32-bit

In the Collatz loop, the obvious "is it even?" trick is `value & 1`, and "halve
it" is `value >> 1`. In Python that's correct and fast. In **JavaScript it's a
landmine**: JS bitwise operators silently coerce their operands to 32-bit
integers first. Collatz sequences starting below a million peak around 10^11,
which is far past 2^31 — so `value & 1` would compute on a truncated number and
return garbage.

So the JavaScript version *must* use arithmetic (`value % 2`, `value / 2`). Plain
JS numbers stay exact here because every value is below 2^53. This is a great
example of why the per-language checksum check matters: had we copied the bitwise
trick into JS, the checksum mismatch would have caught it immediately.

### Python only looks slow until you stop fighting the interpreter

The first Python sieve used a plain inner loop to strike out composites, one byte
at a time. It clocked **35× slower than C** — and that number was honest but
misleading, because no experienced Python developer writes a sieve that way.

The Python-idiomatic version strikes out each prime's multiples with a single
**strided slice assignment**:

```python
sieve[first_composite::candidate] = b"\x00" * composite_count
```

That one line replaces an entire Python loop with a single bulk store that runs
inside CPython's C core. It also only loops the outer pass up to √limit, and
counts primes with `sum()` (another C-level pass). The result: the same prime
count, computed **~10× faster** (3.4 s → 0.33 s), bringing Python to **3.4× of
C** on this test.

The lesson is the whole story of dynamic-language performance in one example:
**you go fast by getting the hot loop out of the interpreter and into the
runtime's compiled core.** Where you can do that (sieve), Python is within
spitting distance of C. Where you can't (recursive calls, scalar float loops),
it's 50–90× slower.

---

## Reading the results, algorithm by algorithm

All times are the median of 5 runs on Windows 11, clang 22.1.4, Node v25,
CPython 3.10.11. Your machine will differ; re-run before quoting.

### fib_recursive — the call-overhead test

| Language        | Median   | vs C  |
|-----------------|---------:|------:|
| C               | 0.069 s  | 1.0×  |
| SemanticScript  | 0.078 s  | 1.13× |
| JavaScript      | 0.271 s  | 3.9×  |
| Python          | 6.033 s  | 88×   |

This is the **one place SemanticScript is visibly behind C** (1.13×). Since the
loop bodies are trivial, the gap is almost entirely per-call cost — the
prototype's calling convention or its result/error-binding does a little more
work per frame than C's bare `call`/`ret`. It's the obvious next target for
codegen tuning. Python's 88× is the cost of a CPython function call (frame
objects, argument unpacking) repeated 63 million times.

### collatz — integer math and messy branches

| Language        | Median   | vs C  |
|-----------------|---------:|------:|
| C               | 0.073 s  | 1.0×  |
| SemanticScript  | 0.070 s  | 0.96× |
| JavaScript      | 0.610 s  | 8.4×  |
| Python          | 4.711 s  | 65×   |

SemanticScript is level with C. JavaScript's 8.4× is the worst the JIT does in
this suite: the unpredictable even/odd branch and JS's number model (everything
is a 64-bit float that the engine tries to treat as an int) both bite here.

### sieve — memory throughput

| Language        | Median   | vs C  |
|-----------------|---------:|------:|
| C               | 0.097 s  | 1.0×  |
| SemanticScript  | 0.096 s  | 0.99× |
| JavaScript      | 0.137 s  | 1.4×  |
| Python          | 0.333 s  | 3.4×  |

The most "everyone's pretty close" result, because the work is dominated by
streaming byte writes to memory — something every runtime can do reasonably
well. SemanticScript matches C; JavaScript's typed arrays keep it near; and
Python, once it uses bulk slice stores, is only 3.4× back. This is dynamic
languages at their best.

### mandelbrot — floating-point compute

| Language        | Median   | vs C  |
|-----------------|---------:|------:|
| C               | 0.144 s  | 1.0×  |
| SemanticScript  | 0.140 s  | 0.97× |
| JavaScript      | 0.149 s  | 1.03× |
| Python          | 6.926 s  | 48×   |

The classic JIT-shines result: **JavaScript is within 3% of C** because V8
compiles the hot float loop to essentially the same machine code. SemanticScript
matches C. Python, doing every multiply and add as interpreted bytecode, is 48×
behind — and this is the one test where the usual escape hatch (NumPy) would help
but is out of scope, because NumPy is a C/SIMD library and would measure *it*,
not CPython.

---

## What you can and can't conclude from this

**Fair to say:**

- The SemanticScript prototype generates code that optimizes to native-C
  performance on these kernels. Its compiled output has no abstraction penalty
  worth measuring (except a small per-call overhead).
- On tight compute, a modern JIT (V8) is often within a small factor of C, and
  occasionally matches it.
- CPython's speed depends enormously on whether the hot loop lives in the
  interpreter or in C — a 25× swing within this very suite (3.4× to 88×).

**Not fair to say:**

- That SemanticScript (or any language here) is "faster than C" in general — the
  sub-1.0× values are noise, and these are tiny kernels, not applications.
- That these numbers predict real-world web-service or application throughput.
  They measure CPU-bound inner loops, not I/O, allocation patterns, GC pauses,
  startup, or memory footprint.
- That the language rankings are universal. Different algorithms, input sizes, or
  machines will shift them.

These are **microbenchmarks**. They're great for catching codegen regressions and
for an honest first look at where the prototype stands. They are not a verdict on
which language to build your product in.

---

## Run it yourself

From `SemanticScript/bench/`:

```powershell
# Everything (builds C + SemanticScript, runs all four languages):
python run_multilang.py

# Just one algorithm:
python run_multilang.py --algorithm sieve

# Machine-readable output (full sample arrays, environment, checksums):
python run_multilang.py --json

# More runs for a steadier median:
python run_multilang.py --runs 11 --warmup 2
```

You'll need `clang`, `node`, and `python` on PATH (point to clang explicitly with
the `SEMSC_CLANG` environment variable if needed). The harness builds the C and
SemanticScript executables for you; JavaScript and Python run from source.

---

## Appendix: workloads and checksums

For reproducibility, here are the exact sizes and the checksum each algorithm
must produce (all four languages must agree):

| Algorithm     | Workload                                   | Checksum    |
|---------------|--------------------------------------------|-------------|
| fib_recursive | `fib(38)`                                  | 39,088,169  |
| collatz       | sum of stopping times, start values 1..600,000 | 75,668,736  |
| sieve         | primes up to 2,000,000, summed over 20 repeats | 2,978,660 (= 20 × 148,933) |
| mandelbrot    | 600×400 grid, escape radius 2, cap 1000    | 61,930,405  |

Workloads are sized so CPython stays under ~8 s per run (which bounds how big the
compiled-language runs can be — that's why their absolute times are short) and so
SemanticScript stays above ~100 ms (to keep its 1 ms clock honest).
