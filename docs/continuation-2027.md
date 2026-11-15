# Where we left off (2026-11-15), and where to pick up

This note is the hand-over for the next stretch of work. It records what is done, what was paused and exactly
where each paused thread stopped, and the order to resume in. Everything it names is on `main` at the commit below
unless it says otherwise.

- **Last commit:** `3af4326` (runtime: complex.h's long double forms on Windows; aligned blocks that free gives back)
- **Last decision recorded:** D-194 (docs/language-refinement.md). Next free number: **D-195**.
- **CI at that commit** (run 43742352297): Windows Python 3.11 and 3.12 green (788 passed, 36 skipped, 0 failed);
  Linux x86_64 10 failed of 818; Linux AArch64 8 failed of 818; macOS job failed (a survey, see below).

## The state of the project

| Area | State |
| --- | --- |
| Language, checker, conformance suite | Done (D-1 to D-194; docs/safety-guarantees.md is generated) |
| Main compiler (Python, LLVM): check, run, build, test | Done |
| 1.0 self-hosting: stage0 compiles itself to a byte-identical fixed point | Done (tag v1.0.0, tests/test_bootstrap.py) |
| Runtime in SemanticScript, no libc, Windows | **Done.** Executables import KERNEL32 only (plus WS2_32, bcrypt when used) |
| Runtime in SemanticScript, no libc, Linux x86_64 and AArch64 | Done for the language runtime; the C library's Linux CI is not yet green (below) |
| The whole ISO C library in SemanticScript | **Done on Windows**; written for Linux, a few glibc differences left |
| macOS (arm64) without libSystem | Experiment started, **paused** |
| stage0 widened past 14 of the 52 single-file suite programs | Not started (self-hosting-plan.md, stage 5) |
| The safety checker written in SemanticScript | Not started |

## Why work stopped where it did

On 2026-11-15 the owner said: "pause all mac osx and linux work, focus only on windows". Windows was then finished
(D-190 to D-194) and its CI went green. The goal "move the entire c stdlib to semantic script and compile it so it
doesnt need libc" was cleared by the owner with Windows complete; Linux and macOS are the open remainder.

## The C library (stage 8 of docs/runtime-in-semanticscript.md)

Modules, all generated from `semanticscript/runtime/tools/<module>.dsl` by `tools/build.py` (never hand-edit a
generated `.sem`): clibrary, clong, cformat, cstreams, cstart, cprocess, cthreads, cextra, cwide, cwidetime,
cmathbits, cmathexp, cmathtrig, cmathspecial, cmathcomplex, cmathlong, ctime. Some have Python generators beside
them (cmath*gen.py, cmathlong*.py, floatcases.py).

Proof is two-fold: every function is called through `ffi.open("c")` from an executable with no C library and
compared with exact references (tests/test_c_*.py and the `*tour.py` files beside them), and on Linux, real C
programs in tests/cprograms are linked against our library (`refined build semanticscript/runtime --kind clibrary`)
and against glibc, and their output compared (tests/test_cprograms.py).

## Linux: the failures left at 3af4326 (resume here first)

x86_64 (job "Validate compiler (Linux, Python 3.12)") and AArch64 (job "... Linux AArch64 ...") share most of them:

1. **cmathcomplex, csin/csinf at infinities** (both arches): `csin(inf - i inf)`, `csin(-inf - i inf)`,
   `csin(NaN - i inf)` give an imaginary part of `-inf` where glibc gives `+inf`. The sign of the infinite imaginary
   part in csin/csinh's Annex G cases; csin comes from csinh by identity (D-187).
2. **complex_math.c line 642** (both): `ctan` prints `(nan, 0)` where glibc differs; the same family as 1.
3. **cmathspecial, lgamma_r's sign at negative integers is architecture-dependent in glibc:** x86_64 glibc stores
   -1 (ours now matches there), AArch64 glibc stores 1 at -1, -2, -3, -27, -28, ... and -1e15. Make the rule
   per-architecture (`system.aarch64()`), as cmathbits does for ilogb.
4. **ctime against glibc** (both): test_time_functions_match_the_models in all three zones, and
   test_zone_files_and_the_system_zone_match_glibc ("TZ=None"). The test now prints up to 400 lines of diff; read
   them in the job log. Suspects named by its author: strftime width and flag cases (%05e, %_5m, %10Y, %3d) and mktime
   history.
5. **cmathbits, x86_64 only:** the tour still differs from glibc after the remainder NaN fix (4e8f41d); read the
   diff lines in the job log (`test_exact_math_matches_the_models`).
6. **long_math.c, x86_64 only:** `log10l(1000)` ours "ok" where glibc's own result is "BAD" (glibc's x87 log10l is
   not exactly 3 there). The C program should hold glibc to glibc's documented error, not to exactness, or compare
   against the exact value only for ours.

Already fixed by the work before the pause and confirmed green on the last run: the x86 thread start's assembly,
thread joins, mutexes on AArch64, the JIT's libgcc_s, wide characters in the C locale, C23 scanf, strtof's errno,
fortify, localeconv, tan and cos near huge arguments (glibc's own error, D-181's test allows it).

Not yet written for Linux: **complex.h's long double forms** (cabsl ... catanhl). On Windows they are the double
functions (D-193, rows marked `abi library "<name>" windows`); on Linux they need a C ABI for a pair of x87 values
(x86_64: in memory) and of binary128 values (AArch64: an HFA in q registers), as D-175 gave pairs of doubles.

## macOS: where the experiment stopped

- Committed (d6d6516, D-189): `system.posix()` and `system.darwin()`; every Linux branch asks for POSIX; Darwin
  system calls lower to `svc #0x80` with Darwin's numbers; Mach-O for arm64-apple-macosx11; a macOS CI job (now on
  macos-15, 5066d65) running tests/test_macos_nolibc.py, which probes two link modes and surveys the suite.
- **What the first real run showed** (macOS 15.8, Apple clang 17):
  - the **static** link (LC_UNIXTHREAD, no dyld) builds and signs, but the kernel kills it at once (exit -9): arm64
    macOS refuses static executables, as expected;
  - the **dyld** link runs hello correctly, but `otool -L` lists `/usr/lib/libSystem.B.dylib`: the `-lSystem
    -dead_strip_dylibs` link did not drop it, so that executable still loads libSystem. Making dyld load no library
    at all (and checking that the kernel and dyld accept an executable with LC_LOAD_DYLINKER but no LC_LOAD_DYLIB) is
    the next experiment; if Apple refuses it, macOS stays refused (R901) with this evidence recorded.
  - the survey: 75 suite programs built with the static link all exit -9, as the static mode is the test's default.
- **Parked work in progress:** docs/parked/macos-piece2-wip.patch (also in .git/parked-macos-piece2-wip.patch on the
  machine where it was made). It applies cleanly on 3af4326 (checked with `git apply --check`); it touches kernel,
  files, sockets, interrupts and codegen.py: a Darwin signal trampoline and the next modules' Darwin branches. Check
  again before applying; later commits may need it rebased by hand. It also wanted a Darwin `st_blksize` offset in cstreams.dsl's blockSize.

## Order to resume in

1. Linux CI to green: items 1 to 6 above (each small, each with its log), then complex.h's long double forms on
   Linux.
2. macOS: the dyld-with-no-library experiment; then widen with the parked patch; or record macOS as refused.
3. Self-hosting beyond 1.0 (docs/self-hosting-plan.md stage 5): widen stage0 past 14 of 52 programs, have stage0
   build the runtime itself, port the checker into SemanticScript, and optionally emit machine code instead of C so
   no C compiler is needed.

## How the work was run (so the next stretch can run the same way)

- The owner's rules: decide design questions and record them as D-n without asking; syntax stays explicit; commit
  and push directly on `main`; **no branches and no git worktrees, ever**; nothing downloaded or installed without
  asking; git author "Earl Cameron" with the owner's address, commits ending with the Co-Authored-By line.
- Parallel agents worked in the one checkout, each owning its own module files and registering itself with one line
  in tools/build.py and build.sem; only the coordinator committed, staging each piece so build.py and build.sem
  carried only the registrations of modules in that commit, then exporting the staged tree (`git checkout-index -a
  --prefix=<dir>/`) to check it regenerates byte for byte, checks, and passes its tests before committing.
- Never write code containing `$` through a bash heredoc: a shell once expanded `$0x3d0f00` in an assembly routine
  and broke every x86_64 Linux executable (dd3baab).
- Writing glibc's message text out verbatim trips the API's content filter; tables of glibc text are built at build
  time from the host instead (strerror, D-172 and D-190).
- `refined test` runs its tests in parallel (b8e2302); the full local suite takes about 23 minutes on Windows.
- Under `refined run` on Linux, Python has set the locale from the environment, so tours that compare with glibc call
  `setlocale(LC_ALL, "C")` first, and errno read across ctypes calls is not reliable (compare it only in the
  executable-against-model checks).
