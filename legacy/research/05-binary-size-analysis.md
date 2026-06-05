# Experiment 5: Binary Output Size

Preservation note: this document is the durable extraction from a binary-size
investigation prompted by a competitor claim. The scratch executables, logs, and
intermediate `.exe` files are not required to understand or reuse the finding.
The measurements, methodology, and conclusions are recorded here so they stand on
their own after the scratch artifacts are deleted.

## Research Intent

A competing agent-oriented language, **Zero** ("zerolang", Vercel Labs), markets
**sub-10 KiB native binaries** as a headline property, framed as a consequence of
*not using LLVM*. A reasonable observer then asks the obvious question about
SemanticScript:

```text
Why are our binaries larger? Is that a defect, and does it say anything about
the compiler or the backend choice?
```

This experiment answers that question with direct measurement rather than
argument. The goal is not to win a size contest. SemanticScript competes on
application-layer expressiveness for AI agents, not on artifact size. The goal is
to know *exactly* where every byte comes from, so the size number is explained
rather than mysterious.

## Decision-Grade Finding

```text
SemanticScript binaries are byte-for-byte the size of the equivalent clang -O2
C binary. The size is dominated by the platform C runtime, not by LLVM and not
by anything SemanticScript adds. The same LLVM backend produces a 2 KiB working
binary when the C runtime is removed.
```

Three claims fall out of that, each backed by a measurement below:

1. SemanticScript adds essentially nothing over C. Same backend, same output.
2. LLVM is not the source of size. The C runtime linkage is.
3. The competitor's sub-10 KiB number is real, but it is a *runtime and target*
   decision, not a *backend* decision. It is orthogonal to LLVM-vs-not.

## Methodology

All numbers were produced on the development host:

- Toolchain: clang / LLVM 22.1.4, target `x86_64-pc-windows-msvc`.
- C baselines: `clang -O2 -o out.exe source.c`.
- SemanticScript: `semsc source.sscript --emit-exe out.exe --opt-level 2`.
- Sizes: raw on-disk PE byte count, cross-checked with `llvm-size` section
  totals. Stripping was attempted with `llvm-strip`.

The four benchmark pairs in `SemanticScript/bench/` were used because each has a
hand-written C baseline and a SemanticScript source that compute the same result,
so the comparison is genuinely like-for-like.

## Measurement 1 — SemanticScript vs C, same program

Whole-binary on-disk size, `-O2` / `--opt-level 2`:

```text
benchmark        C (.exe)      SemanticScript (.exe)     delta
arith             144,896             144,896             0 bytes
memset            144,896             144,896             0 bytes
strlen            144,896             144,896             0 bytes
math              155,136             154,624          -512 bytes (SS smaller)
```

`llvm-size` section breakdown confirms the machine code itself is equivalent:

```text
              text     data    bss
arith.c      89,613   52,476    0
arith.sem    89,661   52,384    0      (.text +48, .data -92)
```

A ~48-byte difference on a ~90 KB code section is noise from instruction
selection and constant layout. There is no SemanticScript-shaped tax in the
binary. `llvm-strip` changed nothing on either side, because these PE binaries
carry no separable symbol table to remove.

Conclusion: **SemanticScript = C** for size, because `semsc` is a thin frontend.
The lowering path is `.sem`/`.sscript` -> semantic IR -> LLVM IR -> the same
clang/LLVM optimizer at the same opt level -> the same linker -> the same C
runtime. For these programs `runtimeBinding` maps operations such as
`math.addInt64`, `c.printf`, and `c.clock` straight to native ops and libc, so no
SemanticScript runtime blob is linked in. There is nothing for SemanticScript to
add or remove relative to C; the artifact *is* the C artifact.

## Measurement 2 — where the bytes actually live

```text
program                                 size
int main(void){ return 0; }  (-O2)    111,104 bytes
   same, -Oz (optimize for size)       111,104 bytes  (no change)
printf("hi")                           114,688 bytes
bench_arith (real loop + printf)       144,896 bytes
```

An empty `main` is already ~111 KB, and `-Oz` does not move it. That floor is the
statically pulled MSVC UCRT startup. Everything above the floor is the program's
own logic, which SemanticScript emits at the same density as C. So the "large
binary" is ~111 KB of C runtime plus a few tens of KB of actual program.

## Measurement 3 — is LLVM the cause? No.

The critical control. Compile with the *same* clang/LLVM, but remove the C
runtime: freestanding, no stdlib, custom entry point, exit via a direct
`ExitProcess` call.

```text
build (identical LLVM backend)                         size
clang -O2, -nostdlib -ffreestanding, direct syscall    2,048 bytes  (runs, exit ok)
clang -O2, normal CRT-linked empty main              111,104 bytes
```

A **54x reduction from the same compiler**. This is the result that reframes the
whole question. LLVM does not bloat binaries. The decision to link the standard C
runtime does. A backend that emits machine code "without LLVM" is not smaller
*because* it skipped LLVM; it is smaller because it links little or no runtime and
talks to the OS directly.

## Why Zero's sub-10 KiB number is true and not contradictory

Zero reaches sub-10 KiB through choices that are all about the runtime and the
target, not the backend:

- Target `linux-musl-x64`: static musl is the lightest mainstream libc, and a
  Linux ELF has a far smaller floor than a Windows MSVC PE. The numbers in this
  document are Windows MSVC; they are **not apples-to-apples** with a Linux musl
  build of anything, C included.
- No mandatory GC, no hidden allocator, no implicit async, static dispatch: there
  is simply less runtime to link.
- Direct syscalls instead of a full libc startup, the same lever that produced
  the 2 KiB binary in Measurement 3.

All of that is real and well-engineered. None of it depends on avoiding LLVM.
SemanticScript could approach the same order of magnitude by building against a
minimal/static libc target with `-nostdlib`-style linkage, without changing
backend at all. We have not done so because, per the project constitution, binary
size is not a SemanticScript axis.

## Why SemanticScript keeps the larger artifact on purpose

The current toolchain links the full clang/LLVM pipeline and the platform C
runtime deliberately:

- Maximal native interop: `runtimeBinding` can reach any libc/native symbol,
  which is what lets the standard library stay small and push logic into `.sem`
  modules instead of the C runtime.
- Mature codegen quality: the perf harness in `SemanticScript/bench/` holds
  SemanticScript at or above 90% of native C speed, which comes from reusing
  LLVM's optimizer.
- Portability of the frontend: one lowering path, many targets, because the
  backend is a known quantity.

The trade is explicit. We accept a large baseline artifact to get native speed,
native interop, and a thin compiler. Zero made the opposite trade: a minimal
runtime and size-as-a-tracked-metric, accepting a more constrained execution
model. Both positions are internally consistent; they optimize different things.

## Caveats To Keep The Claim Honest

- All numbers are Windows MSVC PE. A Linux ELF, a static musl build, or a
  `-nostdlib` freestanding build would all show different and smaller floors, for
  C and SemanticScript alike. The relative result (SemanticScript = C) is what
  travels across platforms; the absolute floor does not.
- The benchmark programs are small and do not exercise the `.sem` standard
  library heavily. A program that links JSON, http, or collection modules links
  more code, but that code is also LLVM-compiled and compares to equivalent C
  library code rather than inflating relative to it.
- "Sub-10 KiB" claims should always be read with their target and runtime model
  attached. The headline number without `--target` and runtime context is not a
  comparable measurement.

## Reproduction

```text
# C baseline
clang -O2 -o arith.c.exe   SemanticScript/bench/bench_arith.c

# SemanticScript, same opt level
python SemanticScript/compiler/semsc.py SemanticScript/bench/bench_arith.sscript \
    --emit-exe arith.sem.exe --opt-level 2

# sizes and sections
llvm-size arith.c.exe arith.sem.exe

# the no-runtime control (Windows): freestanding, direct ExitProcess
clang -O2 -nostdlib -ffreestanding -Wl,-subsystem:console -lkernel32 \
    -o free.exe free.c   # ~2 KiB
```

A `--size` mode could be added to `SemanticScript/bench/run_benchmarks.py` to make
this comparison reproducible in CI alongside the existing performance harness, if
binary size ever becomes something worth guarding against regressions.
