# SemanticScript

Primary language implementation workspace.

## Contents

- `bench/` contains benchmark programs and runners.
- `compiler/` contains the Python reference compiler and C ABI registry.
- `linter/` contains standalone source linters and linter tests.
- `formatter/` contains the canonical formatter for revised `.sem` syntax.
- `runtime/` contains native adapter libraries for async futures/timers, HTTP,
  SQLite, JSON, bcrypt, logging, terminal I/O, and desktop GUI work.
- `sem/` contains runnable SemanticScript sample programs and feature tests.
- `shared/` contains small source-of-truth modules used by multiple tools.
- `std/` contains executable SemanticScript standard-library modules.
- `tests/` contains Python test harnesses and tiny compiler fixtures.

## Standard Library

`std/` is the official standard-library tree. It is intentionally not a
build-tape project and should not contain `build.sem`.

```text
std/
  module.sem              # top-level `standard` relay
  event/main.sem          # imported as standard.event
  html/main.sem           # imported as standard.html
  json/main.sem           # imported as standard.json
  sqlite/main.sem         # imported as standard.sqlite
  <module>/main.test.sem  # colocated self-test
```

Apps import std modules by namespace:

```semanticscript
importModule html standard.html
importModule json standard.json
importModule sqlite standard.sqlite
```

Std discovery is flexible enough for apps outside this repository. The compiler
tries `--std-path`, then `SEMANTICSCRIPT_STD_PATH` / `SEMSC_STD_PATH`, then
vendored ancestor `std/` folders, then current-working-directory std roots, then
the std bundled beside the compiler at `compiler/../std`.

## Current Status

This tree is active and mid-evolution. The compiler, linter, stdlib, docs, and
sample apps are moving toward a clearer split between app-facing SemanticScript
APIs and low-level runtime implementation details.

## 1.0 Support Snapshot

| Area | Status |
|---|---|
| Python reference compiler | Supported 1.0 compiler for `.sscript` and `.sem`, console entry, parse/lint, LLVM IR, JIT run, and clang-linked executables. |
| VS Code extension | Supported editor tooling in `../vscode-semanticscript/`; highlighting refined syntax does not imply runtime support. |
| Refined and partial syntax | Parseable or lowered only where documented in `../SYNTAX.md` and `../docs/toolchain/compiler.md`. Use `--parse-only` for metadata-heavy forms. |
| Web / HTTP runtime | Preview native HTTP/1.1 listener for routed `target webServer` programs with path params, middleware, request readers, response writers, file responses, and curated app coverage. HTTP/2/H2O remains future work. |
| Runtime flags | `--build-profile`, `--runtime-checks`, `--persist-llvm-ir`, `--diagnostics-format`, and `--opt-level` are supported compiler flags. |

## Maintenance

Prefer narrow changes in the owning subfolder. Update docs and tests when a
compiler, linter, stdlib, or syntax behavior changes.
