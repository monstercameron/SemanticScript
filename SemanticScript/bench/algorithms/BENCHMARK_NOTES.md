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

> The SemanticScript prototype has **no measurable abstraction tax in compiled
> loop bodies** — and we don't just measure that, we *prove* it: the optimizer
> emits **instruction-identical inner loops** for SemanticScript and C (see
> "[The proof](#the-proof-identical-machine-code)"). The one honest exception is
> function-call overhead, where SemanticScript is a real ~16% slower than C.

Why is the loop-body result believable rather than a lucky timing? Because
SemanticScript compiles to LLVM IR and is optimized by `clang -O2` — the *same*
backend C uses. So the interesting question isn't "is it as fast as C" (for
straight-line code, it almost has to be); it's "does the prototype's lowering
hand LLVM clean enough IR that the optimizer fully succeeds?" The assembly says
yes for loops, and the fib result says there's still per-call overhead to win
back.

| Algorithm     | C (median) | SemanticScript | JavaScript | Python |
|---------------|-----------:|---------------:|-----------:|-------:|
| fib_recursive | 1.00×      | **1.16×**      | 3.87×      | 83.7×  |
| collatz       | 1.00×      | 0.98×          | 8.75×      | 65.1×  |
| sieve         | 1.00×      | 1.00×          | 1.41×      | 5.54×  |
| mandelbrot    | 1.00×      | 0.98×          | 1.04×      | 48.2×  |

(Numbers are "times slower than C." Lower is faster. For collatz/sieve/mandelbrot
SemanticScript is statistically tied with C — the sub-1.0× values are within the
run-to-run noise. fib is the one real gap.)

---

## The four algorithms, and why each one

A good microbenchmark suite stresses *different* parts of a language. One tight
loop tells you almost nothing on its own. We picked four classics that each lean
on a distinct cost center:

| Algorithm         | What it really measures                    | The workload                              |
|-------------------|--------------------------------------------|-------------------------------------------|
| **fib_recursive** | Function call + return overhead            | `fib(39)` — ~200 million calls, trivial bodies |
| **collatz**       | Integer math and unpredictable branches    | sum of Collatz stopping times for 1..1,000,000 |
| **sieve**         | Memory throughput over a big flat array    | Sieve of Eratosthenes to 2,000,000, ×40   |
| **mandelbrot**    | Double-precision floating-point arithmetic | 600×400 grid, up to 1000 iterations/pixel |

- **fib_recursive** does almost no arithmetic per call; nearly all the time goes
  into entering and leaving functions. It's the purest "how cheap is a call"
  test, which is why we keep it naively recursive (no memoization — that would
  turn it into a different, trivial benchmark).
- **collatz** is a tight integer loop whose branch (is the number even or odd?)
  depends on data the CPU can't predict. It rewards good integer codegen and
  punishes interpreter overhead.
- **sieve** spends its life writing single bytes across a multi-megabyte array.
  It's about memory bandwidth and how cheaply the language does a strided store.
- **mandelbrot** is wall-to-wall `double` multiplies and adds. It's the
  float-compute test, and where JITs tend to catch up to C.

---

## The proof: identical machine code

Timings can be argued with. Machine code can't. Here is the **inner loop of
`collatz`**, compiled from C and from SemanticScript, both lowered to x86-64 by
`clang -O2` (Intel syntax, comments added):

**C** (`collatz.c`):
```asm
.LBB0_3:
    mov     r8d, edx
    lea     r9, [rdx + 2*rdx]   ; r9 = 3*value
    inc     r9                  ; r9 = 3*value + 1
    sar     rdx                 ; rdx = value / 2
    test    r8b, 1              ; is value odd?
    cmovne  rdx, r9             ; if odd, take 3v+1, else keep v/2
    inc     rcx                 ; steps++
    cmp     rdx, 1
    jne     .LBB0_3
```

**SemanticScript** (`collatz.sscript`):
```asm
.LBB0_5:                        ; label: %after_panic_check_collatzParityCall
    mov     edx, ecx
    lea     r8, [rcx + 2*rcx]   ; r8 = 3*value
    inc     r8                  ; r8 = 3*value + 1
    sar     rcx                 ; rcx = value / 2
    test    dl, 1               ; is value odd?
    cmovne  rcx, r8             ; if odd, take 3v+1, else keep v/2
    inc     rax                 ; steps++
    cmp     rcx, 1
    jne     .LBB0_5
```

These are the **same instructions in the same order** — `mov / lea / inc / sar /
test / cmovne / inc / cmp / jne` — differing only in which registers the
allocator picked. Two details worth noticing:

- Both compilers turned the even/odd branch into a **branchless `cmovne`**, and
  both used `lea [x + 2*x]` to compute `3*value` in one instruction. That's
  identical instruction selection, not just "close."
- The SemanticScript label is `%after_panic_check_collatzParityCall`. The
  language inserts a safety check around the division — but the optimizer
  **proved it could never fire and hoisted it out of the hot loop**. You're
  looking at safety with zero runtime cost.

The float case (`mandelbrot`) tells the same story: both compile to the same
unrolled-by-2 sequence of `mulsd / addsd / subsd / ucomisd` with a compare and
branch (the only difference is the compare operands are swapped, because the C
source breaks on "magnitude > 4" while the SemanticScript source continues on
"magnitude <= 4" — logically identical).

**Reproduce it yourself** (from `SemanticScript/bench/`):
```powershell
# C -> assembly
clang -O2 -S -masm=intel -o collatz.c.s algorithms/collatz.c
# SemanticScript -> LLVM IR -> assembly
python ../compiler/semsc.py algorithms/collatz.sscript --emit-exe out.exe `
    --persist-llvm-ir yes --opt-level 2
clang -O2 -S -masm=intel -o collatz.ss.s <the emitted .ll sidecar>
```

This is the result that should actually interest an engineer: not "trust my
stopwatch," but "the lowered code is the code clang would have written anyway."

---

## The rules of the game (how we kept it fair)

Benchmarks are easy to get wrong. Here are the rules we held everyone to.

### 1. We time the work, not the warm-up

Every program times **only its compute loop**, using the best clock its language
offers, and prints one line:

```
checksum=<number> elapsedSeconds=<number>
```

Why not time the whole process from the outside? Because starting Node or
CPython costs tens of milliseconds of interpreter boot time. For the fast tests
that startup would dwarf the actual computation, and we'd be benchmarking the
OS process launcher, not the language. Self-timing the inner loop sidesteps that.

### 2. We report the spread, not just one number

The harness runs each program 9 times (after 2 discarded warm-ups) and reports
**min, median, and relative standard deviation**. The std-devs are small
(mostly under 1%, see the tables below), which is what lets us say
"statistically tied" honestly: when SemanticScript's median is 0.98× of C but
both vary by ~0.6%, they're the same to within measurement. Raise the count with
`--runs` for an even steadier read; `--json` dumps every raw sample.

### 3. The checksum proves everyone computed the same answer

Each program computes a **checksum** — the Fibonacci value, the sum of all
Collatz steps, the prime count, the total Mandelbrot iterations. The harness
refuses to compare timings unless **all four languages report the exact same
checksum**. This catches the classic trap of writing four programs that *look*
like the same algorithm but quietly differ (an off-by-one, a rounding mismatch)
and then comparing meaningless numbers.

Note the precise claim: the checksum proves the same *result*, and we use the
same *algorithm* everywhere. It does not by itself prove identical instruction
counts — see the next rule.

### 4. Same algorithm, but written the way each language wants to be written

We did **not** transliterate the C code character-for-character. We wrote the
**fastest faithful version** a competent developer would actually write in each
language: same algorithm, same result, idiomatic mechanics. For example, all
four sieve versions use the identical structure (start all-prime, strike out
composites for primes up to √limit, then count), but Python strikes out each
prime's multiples with one bulk **strided slice assignment** while C, JS, and
SemanticScript walk the multiples in a loop — both are the natural fast form in
their language. This is a deliberate choice: forcing everyone to run C-shaped
code measures how each language runs *C*, which flatters compiled languages and
is not how anyone writes real Python or JavaScript.

### 5. The compiled pair is genuinely apples-to-apples

C and SemanticScript both go through LLVM and `clang -O2`. So when SemanticScript
lands at 0.98× of C, that number isolates one thing: **the quality of the IR the
prototype emits.** Same optimizer, same code generator — the only variable is
what the front end fed in. (And as the assembly section shows, for loops the
answer is "the same thing.")

### 6. The honest soft spot: SemanticScript's clock

C, JavaScript, and Python all have sub-microsecond timers. SemanticScript, today,
can only reach C's `clock()`, which on Windows ticks every **1 millisecond**.
That's coarse, so we **size every workload to take >100 ms in SemanticScript**
(here ~120–140 ms ≈ 120–140 ticks), keeping quantization under ~1%. You can see
this working in the tables: SemanticScript's std-dev is a bit higher than the
others (it's partly quantization), but small enough that the conclusions hold. A
higher-resolution clock in the runtime would remove the caveat entirely; it's on
the list.

---

## The fun part: three traps we walked into

These are the bugs-in-waiting that make cross-language benchmarking interesting.

### Floating-point has to match *bit for bit* — watch out for FMA

The Mandelbrot checksum is a sum of integer iteration counts, but those counts
depend on floating-point comparisons (`did |z| exceed 2?`). If two languages
round even one operation differently, a boundary pixel can escape one iteration
early or late, and the checksums diverge.

The culprit is the **fused multiply-add (FMA)**: modern compilers love to turn
`a*b + c` into one hardware instruction that's faster *and rounds differently*
(it keeps more internal precision). C and SemanticScript both go through clang,
which may form FMAs; JavaScript and Python never do.

The fix: in **all four** languages, write each step as its own statement with its
own variable, so there's no `a*b + c` expression to fuse. With that, all four
produce bit-identical results and the checksums line up. It costs nothing
measurable in speed.

### JavaScript's bitwise operators are secretly 32-bit

In the Collatz loop, the obvious "is it even?" trick is `value & 1` and "halve
it" is `value >> 1`. In Python that's correct and fast. In **JavaScript it's a
landmine**: JS bitwise operators silently coerce their operands to 32-bit
integers first. Collatz sequences below a million peak around 10^11, far past
2^31 — so `value & 1` would compute on a truncated number and return garbage.

So the JavaScript version *must* use arithmetic (`value % 2`, `value / 2`). Plain
JS numbers stay exact here because every value is below 2^53. Great example of
why the per-language checksum check matters: had we copied the bitwise trick into
JS, the mismatch would have caught it immediately.

### Python only looks slow until you stop fighting the interpreter

The first Python sieve struck out composites with a plain inner loop, one byte at
a time, and clocked **~35× slower than C** — an honest number, but not how an
experienced Python developer writes a sieve. The idiomatic version strikes out
each prime's multiples with a single **strided slice assignment**:

```python
sieve[first_composite::candidate] = b"\x00" * composite_count
```

That one line replaces a Python loop with a bulk store inside CPython's C core.
The result: same prime count, and Python drops to **5.5× of C** on this test.
The lesson is the whole story of dynamic-language performance: **you go fast by
getting the hot loop out of the interpreter and into the runtime's compiled
core.** Where you can (sieve), Python is within a small factor of C. Where you
can't (recursive calls, scalar float loops), it's 50–80× slower.

---

## Reading the results, algorithm by algorithm

All runs: Windows 11, clang 22.1.4, Node v25, CPython 3.10.11, on an otherwise
idle machine. Median of 9 runs after 2 warm-ups; "rsd" is relative standard
deviation. Your machine will differ; re-run before quoting.

### fib_recursive — the call-overhead test

| Language        | Median   | rsd   | vs C  |
|-----------------|---------:|------:|------:|
| C               | 0.110 s  | 0.5%  | 1.00× |
| SemanticScript  | 0.128 s  | 1.2%  | 1.16× |
| JavaScript      | 0.427 s  | 0.5%  | 3.87× |
| Python          | 9.223 s  | 2.1%  | 83.7× |

This is the **one place SemanticScript is genuinely behind C**, and the gap is
real, not noise: 0.125–0.128 s versus C's 0.109–0.110 s, with no overlap in the
ranges. Since the loop bodies are trivial, the ~16% is almost entirely per-call
cost — the prototype's calling convention or its result/error binding does a bit
more work per frame than C's bare `call`/`ret`. That makes it the clearest,
most actionable target for codegen work, and it's the kind of honest finding a
benchmark exists to surface. Python's 84× is the cost of a CPython function call
(frame setup, argument unpacking) repeated ~200 million times.

### collatz — integer math and messy branches

| Language        | Median   | rsd   | vs C  |
|-----------------|---------:|------:|------:|
| C               | 0.125 s  | 0.6%  | 1.00× |
| SemanticScript  | 0.122 s  | 0.8%  | 0.98× |
| JavaScript      | 1.094 s  | 0.4%  | 8.75× |
| Python          | 8.133 s  | 2.0%  | 65.1× |

SemanticScript is tied with C (and the assembly section shows why — same inner
loop). JavaScript's 8.75× is the worst the JIT does here: the unpredictable
even/odd branch and JS's number model (every value is a float the engine tries
to treat as an int) both bite.

### sieve — memory throughput

| Language        | Median   | rsd   | vs C  |
|-----------------|---------:|------:|------:|
| C               | 0.120 s  | 0.7%  | 1.00× |
| SemanticScript  | 0.119 s  | 2.6%  | 1.00× |
| JavaScript      | 0.168 s  | 0.5%  | 1.41× |
| Python          | 0.662 s  | 1.2%  | 5.54× |

The "everyone's close" result, because the work is streaming byte writes to
memory — something every runtime does reasonably well. SemanticScript matches C;
JS's typed arrays keep it near; and Python, using bulk slice stores, is only
5.5× back. Dynamic languages at their best. (SemanticScript's higher rsd here is
the 1 ms clock's quantization showing through on the shortest-bodied test.)

### mandelbrot — floating-point compute

| Language        | Median   | rsd   | vs C  |
|-----------------|---------:|------:|------:|
| C               | 0.142 s  | 0.5%  | 1.00× |
| SemanticScript  | 0.139 s  | 0.8%  | 0.98× |
| JavaScript      | 0.148 s  | 0.7%  | 1.04× |
| Python          | 6.853 s  | 5.2%  | 48.2× |

The classic JIT-shines result: **JavaScript is within ~4% of C** because V8
compiles the hot float loop to essentially the same machine code. SemanticScript
matches C. Python, doing every multiply and add as interpreted bytecode, is 48×
behind — the one test where NumPy would help but is out of scope, because NumPy
is a C/SIMD library and would measure *it*, not CPython.

---

## What you can and can't conclude

**Fair to say:**

- The SemanticScript prototype's compiled loop bodies have **no abstraction
  penalty** — demonstrably the same machine code as C, not just similar timings.
- It has a **real, specific, ~16% per-call overhead** worth optimizing — the
  benchmark did its job by finding it.
- On tight compute, a modern JIT (V8) is often within a small factor of C, and
  occasionally matches it; CPython's speed swings ~15× across this very suite
  (5.5× to 84×) depending on whether the hot loop lives in the interpreter or in
  C.

**Not fair to say:**

- That SemanticScript (or anything here) is "faster than C" — the sub-1.0× values
  are within noise, and these are tiny kernels, not applications.
- That these numbers predict real-world web-service or app throughput. They
  measure CPU-bound inner loops, not I/O, allocation, GC pauses, startup, or
  memory footprint.
- That the rankings are universal. Different algorithms, input sizes, or machines
  will shift them.

These are **microbenchmarks**. They're great for catching codegen regressions and
for an honest first look at where the prototype stands. They are not a verdict on
which language to build your product in.

---

## Run it yourself

From `SemanticScript/bench/`:

```powershell
python run_multilang.py                 # everything
python run_multilang.py --algorithm sieve
python run_multilang.py --json          # full samples + environment
python run_multilang.py --runs 25 --warmup 3   # steadier medians
```

You'll need `clang`, `node`, and `python` on PATH (point to clang with the
`SEMSC_CLANG` environment variable if needed). The harness builds the C and
SemanticScript executables for you; JavaScript and Python run from source.

---

## Appendix: workloads and checksums

For reproducibility — every language must produce the checksum shown:

| Algorithm     | Workload                                          | Checksum     |
|---------------|---------------------------------------------------|--------------|
| fib_recursive | `fib(39)`                                         | 63,245,986   |
| collatz       | sum of stopping times, start values 1..1,000,000  | 131,434,424  |
| sieve         | primes up to 2,000,000, summed over 40 repeats    | 5,957,320 (= 40 × 148,933) |
| mandelbrot    | 600×400 grid, escape radius 2, cap 1000           | 61,930,405   |

Workloads are sized so SemanticScript stays above ~100 ms (to keep its 1 ms clock
honest), which in turn bounds how big the runs can be before CPython's slowest
tests get tediously long.
