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
| 1 | The primitive layer in the compiler; a runtime slice (entry, write, trap, exit, regions) that links `hello` with no libc | Planned |
| 2 | Text, numbers, bytes, buffers; maps, sets, channels; the host dispatch | Planned |
| 3 | Files, identity and claims, directories, processes and pipes, environment, arguments, time | Planned |
| 4 | Tasks, groups, recursion depth, frames and stack traces, test assertions | Planned |
| 5 | Switch every executable to the new runtime; delete `native_runtime.c`; stage0 links it | Planned |
