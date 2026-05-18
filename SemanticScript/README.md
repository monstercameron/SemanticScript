# SemanticScript

Primary language implementation workspace.

## Contents

- `AST.md` records the language and AST design notes.
- `bench/` contains benchmark programs and runners.
- `bootstrap/` contains staged compiler/bootstrap SemanticScript programs.
- `compiler/` contains the Python reference compiler and C ABI registry.
- `linter/` contains standalone source linters and linter tests.
- `sem/` contains runnable SemanticScript sample programs and feature tests.
- `sem_python/` is a placeholder/notes area for Python-oriented SemanticScript work.
- `stdlib_sem/` contains executable SemanticScript standard-library modules.
- `tests/` contains Python test harnesses and tiny compiler fixtures.

## Current Status

This tree is active and mid-evolution. The compiler, linter, stdlib, docs, and
sample apps are moving toward a clearer split between app-facing SemanticScript
APIs and low-level bootstrap/runtime implementation details.

## 1.0 Support Snapshot

| Area | Status |
|---|---|
| Python reference compiler | Supported 1.0 compiler for `.sscript` and `.sem`, console entry, parse/lint, LLVM IR, JIT run, and clang-linked executables. |
| Bootstrap / self-hosting | Preview. The chain and parity harness are release checks, but the SemanticScript-written compiler is not the production compiler. |
| VS Code extension | Supported editor tooling in `../vscode-semanticscript/`; highlighting refined syntax does not imply runtime support. |
| Refined and partial syntax | Parseable or lowered only where documented in `../SYNTAX.md` and `../docs/toolchain/compiler.md`. Use `--parse-only` for metadata-heavy forms. |
| Web / HTTP runtime | Route metadata and handler functions can compile, but no 1.0 HTTP listener/runtime is shipped. |
| Runtime flags | `--build-profile`, `--runtime-checks`, `--persist-llvm-ir`, `--diagnostics-format`, and `--opt-level` are supported compiler flags. |

## Maintenance

Prefer narrow changes in the owning subfolder. Update docs and tests when a
compiler, linter, stdlib, or syntax behavior changes.
