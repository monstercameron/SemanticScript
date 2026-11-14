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

## Conversions (D-125)

Floating-point text matches `refined run` exactly: the shortest `%g`-style
digits that read back to the same value, and correctly rounded parsing,
both computed exactly with arbitrary-precision integers written in
SemanticScript.

## Stages

| Stage | Work | State |
| --- | --- | --- |
| 1 | The primitive layer in the compiler; a runtime slice (entry, write, trap, exit, regions) that links `hello` with no libc | Done |
| 2 | Text, numbers, bytes, buffers; maps, sets, channels; the host dispatch | Planned |
| 3 | Files, identity and claims, directories, processes and pipes, environment, arguments, time | Planned |
| 4 | Tasks, groups, recursion depth, frames and stack traces, test assertions | Planned |
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

What stage 2 needs from the compiler: nothing new for text, numbers, and
bytes (`machine` and `abi c` cover them). The host dispatch
(`refined_host`) takes a key and slot arrays, which an `abi c` operation
already receives as addresses; its many targets want a table from key to
operation, so either an operation reference (D-118) that may be stored and
called with addresses, or a `machine` target that calls an address with
several arguments. Floating-point text (D-125) needs `Float64` bits as
`UInt64` (`machine.storeFloat64` then `loadUInt64` does it today, through
`machine.state`). Stage 3 adds `system` rows for each kernel32 function the
plan lists; stage 4 calls task thunks with `machine.callWithAddress`.

