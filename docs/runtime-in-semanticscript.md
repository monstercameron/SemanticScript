# The runtime in SemanticScript, without libc (2026-11-14)

Standalone executables link `semanticscript/compiler/refined/native_runtime.c`
today: about 2,500 lines of C that implement regions, traps, text and number
conversion, the host library (files, processes, maps, sets, buffers, time),
and tasks, on top of the C library. This plan moves all of it into
SemanticScript and links executables with no C library at all: the program
and its runtime are compiled from SemanticScript to one object, and the only
code not written in SemanticScript is the operating system's own interface.

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
  `use system.calls`. Linux, through raw system calls, comes after Windows.
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
| 3 | Files, identity and claims, directories, processes and pipes, environment, arguments, time | Planned |
| 4 | Tasks, groups, channels, test assertions | Planned |
| 5 | Switch every executable to the new runtime; delete `native_runtime.c`; stage0 links it | Planned |

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
