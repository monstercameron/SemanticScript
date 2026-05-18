# Reference Compiler

The reference compiler is `AgentScript/compiler/ascc.py`. It parses
line-oriented AgentScript, resolves imports and external literals, builds an
AST, emits LLVM IR with `llvmlite`, can JIT-run, and can call `clang` for
native executables.

## Commands

Run from the repository's `AgentScript/` directory unless paths are explicit:

```powershell
python compiler/ascc.py --version
python compiler/ascc.py as/fizzbuzz.as --parse-only
python compiler/ascc.py as/fizzbuzz.as --lint
python compiler/ascc.py as/fizzbuzz.as --run
python compiler/ascc.py as/fizzbuzz.as --emit-ir fizzbuzz.ll
python compiler/ascc.py as/fizzbuzz.as --emit-optimized-ir fizzbuzz.opt.ll --run
python compiler/ascc.py as/fizzbuzz.as --emit-exe fizzbuzz.exe
```

CLI flags:

| Flag | Behavior |
|---|---|
| `--version` | Print compiler version. |
| `--emit-ir PATH` | Write pre-optimization LLVM IR. |
| `--emit-optimized-ir PATH` | Write post-optimization LLVM IR during `--run`. |
| `--run` | JIT-execute `main` and return its exit code. |
| `--emit-exe PATH` | AOT compile with clang. |
| `--lint` | Run built-in compiler lint pass. |
| `--strict` | Treat compiler lint diagnostics as fatal. |
| `--parse-only` | Parse, optionally lint, and stop before codegen. |
| `--opt-level N` | LLVM optimization level `0..3`, default `2`. |
| `--quiet` | Suppress success messages. |

Set `ASCC_CLANG` to override the clang executable used by `--emit-exe`.
Set `ASCC_TRACEBACK=1` to print Python tracebacks for parse/codegen failures.

## Parse Pipeline

1. Read source as UTF-8.
2. Resolve `importModule` lines and inline imported files.
3. Tokenize line by line.
4. Build the `Program` object and current-operation body tapes.
5. Load external literals from `literalSource` metadata.
6. Optionally run compiler lint.
7. Stop for `--parse-only`, otherwise emit LLVM.

## Import Resolution

`importModule DOTTED.PATH [as ALIAS]` is resolved before parsing. The compiler
searches source-relative paths, `stdlib_as/`, and the project root. Imports are
inlined with cycle detection.

The alias is recorded for tools; it is not currently a full namespace boundary.

## Entry and Library Modes

`entry console OPERATION` emits `int main()` from that operation.

Without an `entry`, the compiler:

- declares every operation as a callable function;
- compiles every operation body;
- emits a stub `main` returning zero.

This supports stdlib files, web-server route handlers, and refined syntax
showcases that need parse/codegen inspection without a runtime host.

## User Operation ABI

For each non-entry user operation:

- inputs become function parameters in source order;
- opaque inputs are dropped from the LLVM ABI;
- `output OP Result OK ERR` returns `OK`;
- `output OP TYPE` returns `TYPE`;
- missing or unknown output defaults to `i32`;
- `Void` success currently uses an `i32` zero sentinel where LLVM needs a
  concrete return slot.

Opaque input names:

```text
console environment process httpRequest databaseClient clock
```

## Soft Metadata vs Runtime Features

The compiler accepts many refined verbs so tools can inspect current and future
syntax. The important distinction:

- Soft metadata lines can be safely ignored by codegen because they only
  annotate behavior.
- Runtime-feature lines must either lower correctly or use an explicit
  synchronous fallback.

Examples of synchronous fallbacks:

```text
start/await              start executes immediately; await is no-op
taskGroup                startInGroup executes immediately
channel                  single operation-local slot
lock/unlock              no-op in single-thread runtime
workerPool               direct dispatch on same thread
interval                 no timer runtime; no-op
```

## Codegen Errors

Parse errors exit with code `2`. Codegen errors and unsupported runtime backend
errors exit with code `3`. Native executable linking errors exit with code `4`.

Use `--parse-only` when authoring metadata-heavy syntax whose runtime backend is
not expected to exist yet.

## Tests

Primary compiler test commands:

```powershell
python tests/compare.py
python tests/as_compiler_parity.py
python tests/test_compiler.py
python tests/test_stdlib.py
python bootstrap/run_bootstrap_chain.py
```

Feature programs live in:

```text
AgentScript/as/feature_tests/
```

When adding or changing lowering behavior, add the smallest feature test that
proves the exact line schema and runtime result.

