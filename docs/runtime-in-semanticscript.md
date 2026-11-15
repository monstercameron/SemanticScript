# The runtime in SemanticScript, without libc (2026-11-14)

Standalone executables linked `semanticscript/compiler/refined/native_runtime.c`
when this plan began: about 2,500 lines of C that implemented regions, traps,
text and number conversion, the host library (files, processes, maps, sets,
buffers, time), and tasks, on top of the C library. This plan moved all of it
into SemanticScript and links executables with no C library at all: the
program and its runtime are compiled from SemanticScript to one object, and
the only code not written in SemanticScript is the operating system's own
interface (kernel32, ws2_32, and bcrypt on Windows, system calls on x86_64 and
AArch64 Linux) and a few instructions of assembly that switch stacks, start the
process, and return from a signal on Linux. All six stages are done;
`native_runtime.c` is deleted, and every module of the standard library works
in an executable on Windows and on Linux: `ffi` too, since the runtime has a C
library of its own, written in SemanticScript, and on Linux a loader of shared
libraries (D-153 to D-155).

## The bar

1. `semanticscript/runtime/` is a SemanticScript project that implements
   every function the LLVM backend calls (`refined_trap`, `refined_host`, the
   region, text, number, task, and test functions) and every host target in
   today's `TARGETS` table, plus `memcpy`, `memset`, `memmove`, `memcmp`.
2. `refined build --kind executable` compiles the program together with that
   runtime and links with `-nostdlib`: no CRT start files, no libc, no libm.
   On Windows the executable imports from `KERNEL32.dll` only (checked by a
   test reading its import table).
3. Every test that runs a program as an executable (the conformance suite,
   tests/test_native.py, the stage0 samples and bootstrap) passes with the
   new runtime, with the same output, exit codes, and trap messages as
   `refined run`.
4. `native_runtime.c` is deleted. stage0's emitted C links the runtime
   object built from SemanticScript instead.

## The primitive layer (D-120 to D-124)

The language deliberately has no raw memory and no system calls. The
runtime needs both, so they come in as two standard modules that only a
project granted the capability can use, approved like any authority (D-53).
No other program can reach them.

- **`machine` (D-121)**: `machine.Address` (a 64-bit address), arithmetic
  on it, loads and stores of `Byte`, `Int32`, `Int64`, `UInt64`, `Float64`,
  and `Address`, `copy`, `fill`, and `compare` of address ranges, the address
  and length of a `String` or `Bytes` and a view back from them, one zeroed
  static block for process-wide state (`machine.state`), and a call through
  an address with one address argument (task thunks). Capability
  `use machine.memory`.
- **`system` (D-122)**: one typed target per operating-system entry point
  the runtime uses (Windows: `GetStdHandle`, `WriteFile`, `ReadFile`,
  `CreateFileW`, `CloseHandle`, `VirtualAlloc`, `VirtualFree`, `ExitProcess`,
  `GetCommandLineW`, `CreateProcessW`, `CreatePipe`, `WaitForSingleObject`,
  `GetExitCodeProcess`, `GetFileInformationByHandle`, `GetFullPathNameW`,
  `FindFirstFileW`, `FindNextFileW`, `CreateDirectoryW`, `DeleteFileW`,
  `GetEnvironmentVariableW`, `Sleep`, `GetSystemTimePreciseAsFileTime`,
  `QueryPerformanceCounter`, `SetFilePointerEx`, `SetEndOfFile`, and the like),
  lowered to direct calls of the imported function. Capability
  `use system.calls`. Linux, through raw system calls, came at stage 5
  (D-138): one row per system call, `LINUX_CALLS`, and `system.linux()`.
- **`abi c "<symbol>"` (D-123)**: a row on an operation that exports it
  under that exact symbol with the C calling convention; its inputs and
  output are `Int64`, `Int32`, `Byte`, `Bool`, `Float64`, or
  `machine.Address`. This is how compiled programs reach the runtime.
- **Linking (D-124)**: `-nostdlib -nostartfiles`, an entry operation in the
  runtime that reads the command line, runs the program's `main`, flushes,
  and calls `ExitProcess`; libraries `kernel32` (and the compiler's own
  support library for stack probes, which is not libc).

## Conversions (D-125, D-129)

Floating-point text matches `refined run` exactly, which is Python's: a
Float64 is written as `repr` writes it (the fewest digits that read back as
the same value, the nearest of them, `100.0`, `1e+16`, `5e-324`, `nan`), and
text is read correctly rounded, both computed exactly with arbitrary-precision
integers written in SemanticScript. (D-125 first named the C runtime's `%g`
layout, which was wrong for values like `100.0`; D-129 corrects both.)

## Stages

| Stage | Work | State |
| --- | --- | --- |
| 1 | The primitive layer in the compiler; a runtime slice (entry, write, trap, exit, regions) that links `hello` with no libc | Done |
| 2 | Text, numbers, bytes, buffers; maps, sets; the host dispatch | Done |
| 3 | Files, identity and claims, directories, processes and pipes, environment, arguments, time | Done |
| 4 | Tasks, groups, channels, test assertions | Done |
| 5 | Linux through system calls; switch every executable to the new runtime; delete `native_runtime.c`; stage0 links it | Done |
| 6 | The rest of the library: random, http, json, signal, net; AArch64 Linux | Done |
| 7 | `ffi` everywhere: the runtime's own C library, and an ELF loader for Linux | Done |

## Stage 1 (done)

The compiler has the primitive layer: the `use` effect verb, the `machine`
and `system` standard modules (library.py: `_machine()`, `SYSTEM_CALLS`,
`STATE_BYTES`), the `abi c "<symbol>"` row (shapes.py, semantics.py), and
their lowering (codegen.py: `machine`, `system_function`, `machine_state`).
Under `refined run` and `refined test` the `machine` targets work as
compiled and the `system` targets call the functions already loaded in the
process, so the runtime's own tests run there.

`semanticscript/runtime` is a library project of six modules, written as
DSL files in `tools/` that stage0's generator expands
(`python semanticscript/runtime/tools/build.py`):

| Module | Provides |
| --- | --- |
| `memory` | `memcpy`, `memmove`, `memset`, `memcmp`, `refined_bytes_equal`, `refined_find` |
| `numbers` | decimal text of an `Int64`; `refined_parse_int` |
| `output` | `refined_write`, `refined_write_int` (WriteFile, unbuffered) |
| `frames` | `refined_frame_push`, `refined_frame_pop`, `refined_recursion_enter`, `refined_recursion_leave`, `refined_trap` (the report `refined run` prints, exit 70) |
| `regions` | `refined_region_new`, `refined_region_alloc`, `refined_region_remaining`, `refined_region_free` (64 KiB chunks from VirtualAlloc, 64 kept for reuse), `refined_format_int` |
| `start` | `refined_entry`: the stack floor, the program's entry, `ExitProcess` |

`refined build --kind executable --runtime semanticscript` links a program
with it and no C library (D-124); the C runtime stays the default. 42 of the
suite's 76 running programs link this way and behave exactly as under
`refined run`, traps and stack traces included, and the rest are refused
when built, naming what they need (tests/test_runtime_nolibc.py). `hello`
is a 34 KB executable that imports from KERNEL32.dll alone.

## Stage 2 (done)

Six more modules (D-126 to D-130), generated from their DSL like the rest:

| Module | Provides |
| --- | --- |
| `heap` | memory from the process heap (`take`, `resize`, `give`) and trap messages put together from parts |
| `tables` | rows in first-put order found through an open-addressing index by a hash of the key: maps and sets |
| `handles` | the handle table (numbered from 1, never reused, use after close traps naming the kind), each region's list of the objects it owns, `refined_handle_region` |
| `bignum` | whole numbers of up to 6,400 bits: compare, add, subtract, multiply by a small factor or a power of ten, shift |
| `floats` | `refined_write_float`, `refined_format_float`, `refined_parse_float`: shortest repr digits (Steele and White, Burger and Dybvig) and correctly rounded reading, exactly |
| `host` | `refined_host`: a key's shape worked out once and kept by its address, then a branch on the target's number to buffers, maps, sets, `string.fromBytes`, and log lines (the `hostTargets` table) |

`regions` now drops the host objects a region owns when it is released. The
compiler gained `convert.float64BitsToUInt64` and `uint64BitsToFloat64`
(D-127) and `system` rows for the process heap (D-128); the dispatch needs
no call through an address (D-126). native.py reads `hostTargets` and
refuses (R901) a program that calls any other host target.

49 of the suite's 76 running programs now link with no C library and behave
exactly as under `refined run`: stage 1's 42 and `02-types/floats`,
`03-operators/integer-types`, `08-strings-collections/text-and-bytes`,
`collections`, `text-sets`, `trees`, and `19-stdlib/log`. tests/floattable.py
writes and reads back a table of thousands of doubles and texts (random bits,
subnormals, powers of two and ten, exact halfway points and texts a hair off
them, long significands) and the executable prints exactly what Python
prints; tests/hosttour.py uses every target and prints exactly what
`refined run` prints. The runtime's own tests number 41. `hello` is now a
145 KB executable (34 KB at stage 1): the runtime is one object and the
linker keeps all of it, which separate function sections would fix.

Writing this showed the C runtime was wrong about floating-point text
(D-129); it now writes what `refined run` writes. Channels are not in the C
runtime's table either, and the programs that use them need tasks, so they
move to stage 4.

What stage 3 needs: `system` rows for `CreateFileW`, `CloseHandle`,
`SetFilePointerEx`, `GetFileInformationByHandle`, `GetFullPathNameW`,
`GetFinalPathNameByHandleW`, `FindFirstFileW`, `FindNextFileW`, `FindClose`,
`CreateDirectoryW`, `RemoveDirectoryW`, `DeleteFileW`, `LockFileEx`,
`UnlockFileEx`, `GetEnvironmentVariableW`, `CreateProcessW`, `CreatePipe`,
`PeekNamedPipe`, `WaitForSingleObject`, `GetExitCodeProcess`,
`TerminateProcess`, `GetTickCount64`, `GetSystemTimeAsFileTime`, and `Sleep`;
UTF-8 to UTF-16 and back (in SemanticScript, or `MultiByteToWideChar`), the
command line split into arguments in SemanticScript (`CommandLineToArgvW` is
shell32's, not kernel32's) and lower-casing paths without user32
(`CharLowerBuffW`) for the scope checks; the scope check of D-38 in
`refined_host` (the `scoped` column is there, all -1 today), the claims of
D-52 and D-109, Windows errors mapped as Python maps them, and the release of
open files at a trap (D-51), which `frames` reaches before `host` exists, so
through a count in `machine.state` or a module above both.

What stage 4 needs: the task and group functions (a task runs when started,
through `machine.callWithAddress`, with its own frame base and depth
counters, which live in `machine.state` and must be saved and restored or
moved per task), a group's first error copied out at `join`, channels as
host targets, and the test assertions (`refined_assert_*`, `refined_fail`)
and `refined_block` for instrumented builds.

## Stages 3 and 4 (done)

Six more modules (D-131 to D-137), generated from their DSL like the rest,
and additions to `frames` (the resources a trap releases, D-51; each task's
call stack and depth counters; the test callbacks) and `handles` (listings,
argument lists, channels, and lists of names):

| Module | Provides |
| --- | --- |
| `slots` | a host call's slots: where each parameter's slots are, reading them, putting text into a region and an error's payload |
| `wide` | UTF-8 to UTF-16 and back, lower case as Python's `normcase` gives it (`LCMapStringEx`), builders, text order |
| `tasks` | tasks on fibers and the scheduler (waits, generations, deadlines, deadlocks, cancellation), groups and their first error, `refined_task_*` and `refined_group_*`, deadlines, clocks, sleep, channels |
| `files` | paths resolved as `normcase(realpath())`, the scope check of D-38 that `refined_host` runs for scoped targets, claims (D-52, D-109), every `fs` target |
| `processes` | the command line split as `CommandLineToArgvW` splits it, the environment, `console.readLine`, argument lists, `process.run` and `runCaptured` (list2cmdline quoting, pipes pumped between tasks), secrets, foreign libraries (`LoadLibraryW`, `GetProcAddress`) |
| `hashes` | SHA-256, HMAC-SHA-256, hex text, constant-time equality: the `crypto` targets |

A task runs on a fiber of its own, started when the task starts and run until
it waits or ends (D-133): what the C runtime ran to its end when started still
runs that way, and a task that waits lets the others run, so channels, groups
that wait for room, a sibling's failure cutting a sleep short, and deadlock
traps all behave as under `refined run`. The compiler gained
`machine.taskEntry` (D-131), where a fiber starts, and 40 `system` rows, all
kernel32 (D-132).

An executable is now one LLVM module, the runtime's bitcode (kept in the
temporary directory) with the program linked in, every function internal but
the entry, and what the entry never reaches dropped (D-135): `hello` is 23 KB
(145 KB at stage 2, 344 KB had the whole runtime of stage 4 been linked), the
warehouse example 272 KB, and stage0 (the compiler in SemanticScript) 6.4 MB.

What links with no C library and behaves exactly as under `refined run`
(tests/test_runtime_nolibc.py): 71 of the suite's 76 running programs; every
conformance program that runs (`group-first-failure` included, which the C
runtime cannot run); every stage0 sample; the warehouse example on its good
path and its four failure paths; and stage0 itself, which compiles samples to
the same C as stage0 built with the C runtime. `secret`, `crypto`, and `ffi`,
which the C runtime refuses, are there too (D-137). The five programs still
refused need what this runtime does not have (D-137): `net`
(12-io/network-connect: Winsock is not kernel32), `http` (19-stdlib/library-tour)
and `json` (not written yet), `random` (the system's secure generator is
outside kernel32), and `signal` (an interrupt handler's address). The
runtime's own tests number 57.

What stage 5 needs:

- `--runtime semanticscript` the default for `--kind executable`, and the C
  path (`native.executable`, `native_targets`, `_runtime_object`) removed with
  `native_runtime.c`. Tests that read the C runtime (test_native.py's
  error-number and target checks, test_tooling's ERR_ constants,
  `test_runtime_host_targets_are_the_c_runtimes`) move to the `hostTargets`
  table and the runtime's variant constants; test_conformance's executable
  test drops `SEQUENTIAL_TASKS`.
- Executables are Windows-only with this runtime (D-122): Linux and macOS need
  the `system` layer as raw system calls, or stay on the C runtime until they
  have it.
- stage0's C links the runtime built from SemanticScript instead of
  `native_runtime.c`: `refined` writes the runtime as a standalone object (every
  `abi c` operation external, not the one-module build of D-135), stage0's
  `emitc` writes `refined_program_main` where it writes `main(argc, argv)` and
  `refined_start` today (the runtime's `refined_entry` reads the command line
  itself), and stage0 links with `-nostdlib -nostartfiles -Wl,-e,refined_entry
  -lkernel32 -lgcc`, which needs the emitted C to call no C library function
  (it must use the runtime's `memcpy` and the like only). tests/test_stage0.py,
  test_bootstrap.py, and test_selfhost_suite.py's `LINK` change with it.
- D-80 to D-85 are superseded where they describe the C runtime (tasks run when
  started without waiting, D-83's thread pumps); the safety-guarantees text
  generated by tests/suite/conformance.py says channels are refused in
  executables, which stays true only for the C runtime.

## Stage 5 (done)

The runtime in SemanticScript is the only runtime of standalone executables, on Windows and on x86_64 Linux, and
`native_runtime.c` is gone (D-138 to D-143).

- **Linux** (D-138, D-139, D-140): `system` has a row per Linux system call the runtime makes (`LINUX_CALLS` in
  library.py), each a `syscall` instruction; `system.linux()` is a constant of the target, and every module that
  reaches the system takes the Windows or the Linux path on it, with the same behaviour and messages. A new module,
  `kernel`, holds what the paths share (memory from the system, errno, Linux's clocks, the start-up words). On
  Linux the process starts at a `_start` of module assembly that hands `refined_entry` the kernel's stack; the
  program runs on a stack of 256 MiB of its own, tasks on stacks of 64 MiB switched by `machine.switchStack` and
  `machine.startStack`, and waits on descriptors with `poll` (a child's pidfd, standard input); the heap is the
  runtime's own over mmap; files are `openat`, `getdents64`, `flock` and the like, paths resolved as
  `posixpath.realpath`; children start as `_posixsubprocess` starts them (`fork`, `execve` along PATH, the error
  back on a close-on-exec pipe). `ffi` is refused on Linux: it needs the C library's dynamic loader. Executables
  link with `-nostdlib -nostartfiles -static`.
- **The only runtime** (D-141): `refined build --kind executable` links the runtime in SemanticScript; `--runtime
  semanticscript` is accepted and changes nothing. macOS is refused with R901: there is no CI to validate a system
  layer for it.
- **stage0** (D-142): `refined build semanticscript/runtime --kind runtime --output runtime.o` writes the runtime as
  a standalone object; stage0's C defines `refined_program_main` and calls no C library function, and links with
  `runtime.o -nostdlib -nostartfiles -Wl,-e,refined_entry -Wl,--stack,268435456 -lkernel32 -lgcc` on Windows and
  `runtime.o -nostdlib -nostartfiles -static -fno-stack-protector -lgcc` on Linux. The bootstrap fixed point holds.
- **Tests** (D-143): what read the C file reads the runtime: host targets from `hostTargets`, error numbers from
  its `numbered from 1` constants.

## The bar, met

1. **Every function the backend calls and every host target**: `semanticscript/runtime` (19 modules) defines every
   callback in codegen's `CALLBACKS` and every host target the C runtime had, and channels, secrets, crypto, and
   (on Windows) foreign libraries besides; `memcpy`, `memset`, `memmove`, `memcmp` are its `memory` module's.
   Evidence: `test_runtime_host_targets_cover_the_library`, the runtime's own tests (60, under `refined test` on
   Windows and on Linux CI), and native.py refusing (R901) any program that needs a callback or target it lacks.
2. **No C library**: every executable links with `-nostdlib -nostartfiles`. Windows: its import table names
   KERNEL32.dll alone; Linux: it is static, with no dynamic section or interpreter and nothing of the C library in
   it. Evidence: `assert_no_libc` on every executable test_runtime_nolibc.py builds, and
   `test_executables_link_no_c_library` (both systems).
3. **Every test that runs an executable passes with the same output, exit codes, and trap messages as `refined
   run`**: the conformance suite, tests/test_native.py, the suite programs, the stage0 samples and bootstrap, on
   Windows locally and on Linux in CI. Evidence: the full suite, green in CI run 43681807203 (2f68b58) on Linux (Python 3.12: 751 passed, 1 skipped) and on Windows (Python 3.11 and 3.12), and here on Windows (751 passed, 1 skipped); on Linux every executable test goes through the system-call layer. (Run 43679981725, on 786b0e5, had one failure, the floor of linked suite programs, which is 70 on Linux, where `ffi` is refused.)
4. **`native_runtime.c` is deleted**, and stage0's emitted C links the runtime object built from SemanticScript:
   tests/test_stage0.py, test_bootstrap.py, and test_selfhost_suite.py link with it, and stage0b compiles every
   sample to C byte-identical to stage0's.

## Stage 6: the rest of the library (done)

The five modules stage 4 left to `refined run` move into the runtime (D-144 onward), each exactly as `refined run`
behaves, and the Linux system layer gains AArch64.

| Module | Provides | State |
| --- | --- | --- |
| `generators` | `random`: CPython's Mersenne Twister for seeded generators, the system's secure source (BCryptGenRandom, getrandom) for `int64Between` (D-146) | Done |
| `requests` | `http`: requests read and responses written as host.py does (D-152) | Done |
| `values`, `documents` | `json`: shared, counted values; CPython's scanner (errors and positions) and encoder (D-151) | Done |
| `interrupts` | `signal`: SetConsoleCtrlHandler, rt_sigaction for SIGINT (D-147) | Done |
| `sockets` | `net`: IPv4 TCP through Winsock and socket system calls, a resolver for Linux (D-148, D-149) | Done |
| AArch64 Linux | `svc #0`, the generic system call numbers; ppoll, clone, dup3; struct stat and O_DIRECTORY (D-150) | Done |

### What "no C library" means (D-144)

No C library or C runtime of any kind: no msvcrt, ucrt, vcruntime, glibc, or musl, no CRT start files, and on Linux
no dynamic loader. What an executable links besides the program and the runtime is the operating system's own
interface where the system gives no other: on Windows `KERNEL32.dll`, `WS2_32.dll` (Winsock, the only interface to
Windows's TCP/IP stack), and `bcrypt.dll` (the system's random number generator); on Linux the system calls. A DLL
is in the import table when the program's code can reach it: `hello` imports KERNEL32.dll alone, and a program that
calls any host target reaches `refined_host`'s dispatch over all of them, so it imports the other two as well. `assert_no_libc` checks every
executable the tests build: Windows imports are KERNEL32.dll and a subset of {WS2_32.dll, bcrypt.dll}, never a CRT
DLL; Linux executables are static, with no PT_DYNAMIC or PT_INTERP and no trace of the C library.

### Platform limits (D-145)

- **`ffi` on Linux** was refused (R901): `ffi.open("c")` asks for the C library itself, and a static process with no
  C library cannot host glibc, whose start-up only its dynamic loader performs. This is no longer a limit: stage 7
  gives the runtime a C library of its own and a loader (D-153, D-154).
- **macOS** stays refused (R901), and is the next to try. Apple's kernel interface is private and changes between
  releases, and every macOS executable must link libSystem, which is the C library: there is no macOS executable
  without a C library to build today.

## Stage 7: `ffi` everywhere (done)

| Module | Provides | State |
| --- | --- | --- |
| `clibrary` | The C standard library in SemanticScript, as glibc behaves in the C locale: ctype.h with glibc's class bits and tables, string.h, stdlib.h (the `strto*` and `ato*` readers, `malloc` and its kin, `qsort`, `bsearch`, `getenv`, `exit`, `abort`, `div`), math.h's basics (`fabs`, `floor`, `ceil`, `trunc`, `round`, `fmod`, `sqrt`, `copysign`), stdio.h's writes to streams 1 and 2, `__errno_location`, the stack protector's names (D-153) | Done |
| `loader` | ELF shared libraries on Linux as `dlopen(RTLD_NOW)` maps them: the search path, PT_LOAD segments, RELR, RELA, and JMPREL relocations bound at once, DT_GNU_HASH and DT_HASH, DT_NEEDED breadth first, the runtime's C library for C imports, DT_INIT and DT_INIT_ARRAY; thread-local storage, ifuncs, and text relocations trap saying why (D-154) | Done |

- **The C library** (D-153). `ffi.open("c")` binds the runtime's own C library in an executable on Windows and on
  Linux alike (on Linux `libc.so.6`, `libm.so.6`, and the other parts of glibc too), so a program's foreign calls give
  the same results on both; `ffi.Function.bind` finds a name in its table, and a name it does not have is
  `symbolMissing` as under `refined run`. Its functions are `abi library` operations (D-155), named
  `refined.c.<name>` in LLVM and reached only through the table the compiler builds (`machine.cLibrary`), so an
  executable that does not reach `ffi` holds none of it. On Windows `c` no longer means ucrtbase: a function the
  runtime's library lacks is `symbolMissing` there, where `refined run` finds it in ucrtbase.
- **The loader** (D-154). Any other name on Linux is found as dlopen finds it (a path, LD_LIBRARY_PATH, RUNPATH with
  `$ORIGIN`, the system's library directories), mapped, relocated, and initialized; a library linked against glibc
  binds its C imports to the runtime's C library. What it cannot load right traps, never loading a library wrongly:
  ``trap: `ffi.open` cannot load `./libtls.so` in an executable with no C library: it has thread-local variables
  (PT_TLS), which only the C library's dynamic loader sets up (D-154); run the program with `refined run` ``. On
  x86_64 the thread pointer is set to a block of the runtime's own, so a library's stack protector reads a canary at
  `%fs:0x28`; on AArch64 the canary is `__stack_chk_guard`.
- **Evidence.** All 76 of the suite's running programs link on Windows and on Linux (`18-interop/foreign` matches
  `refined run`), and the no-C-library assertions hold for every executable. tests/ctour.py calls the scalar
  functions and builds strings in memory the library gave, and prints what glibc gives (on Linux exactly what
  `refined run` prints, which calls glibc). tests/loadtour.py compiles a probe library on the Linux runner and every
  one of thousands of probes (strtol and its kin in every base, strtod, ctype and its tables, the string functions,
  malloc and its kin, math, qsort, bsearch, getenv, div) gives exactly what the same library gives calling glibc
  through ctypes; a library linked with no C library calls strlen through the loader; thread-local storage, an
  ifunc, and a missing function trap with their reasons. The runtime's own tests number 76.

## Stage 8: the whole C library (in progress)

The runtime's C library grows toward all of ISO C's (C11/C17 hosted), behaving as glibc does in the C locale, proved
two ways: through `ffi` (tests/ctour.py, checked against glibc's behaviour on every system and against `refined run`,
which calls glibc, on Linux) and, on Linux, as the C library of C programs.

| Header | Provides | State |
| --- | --- | --- |
| stdio.h | FILE streams buffered as glibc's, the printf family (`cformat`: every conversion, exact digits), the scanf family and glibc's `__isoc99_` names, remove, rename, tmpfile, tmpnam, perror (D-156 to D-160) | Done |
| string.h | strerror: `Unknown error N` for every number (glibc's messages are a known gap) | Gap |

- **stdio** (D-159, D-160). `printf` and its kin read their arguments from the system's own `va_list` (x86_64 Linux,
  AArch64 Linux, Windows), every one first, then write each conversion as glibc does; a floating value's digits are
  exact (m * 5^-e kept in base 10^9) and rounded as glibc rounds them. Streams are buffered as glibc's are, and
  every stream is flushed by exit and when a program of SemanticScript that used one ends. D-153's streams 1 and 2,
  written at once, are replaced: the data symbols `stdin`, `stdout`, and `stderr` point at FILE blocks.
- **Evidence.** tests/ctour.py prints through `ffi`'s printf (each line flushed, so C's lines and the program's keep
  their order) 14 floating formats over 29 doubles (zeros, halves, subnormals, the largest double, infinities, NaN)
  and 8 integer formats over 6 pairs (the limits of int and long), and sscanf's stored values compared byte for byte:
  all 6,527 lines are what glibc prints (here on Windows; on Linux also exactly what `refined run` prints). The
  runtime's tests (cformat's formatTest, cstreams' streamTest: a temporary file written, flushed, read back, and
  scanned) number 80.
- **C programs** (D-161). `refined build semanticscript/runtime --kind clibrary` writes the library as an object with a
  `_start` of its own; a C program compiled with glibc's headers and linked `cc -nostdlib -static program.o
  <object> -lgcc` is static, with nothing of glibc in it. tests/test_cprograms.py builds every program in
  tests/cprograms both ways on Linux (x86_64 and AArch64 in CI) and requires the same output, error output, and exit
  code: stdio_printf.c (17 formats over 15 doubles, every integer length, `%n`, `%n$`, `*`, long double, snprintf),
  stdio_files.c (writing, reading, positions, pushback, end of file, errors, r+ and a, rename, remove, tmpfile,
  setvbuf and setbuf), stdio_scanf.c (sscanf's conversions, scansets, widths, and scanf with getchar on standard
  input).

