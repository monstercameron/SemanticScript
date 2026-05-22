# SemanticScript Developer Documentation

This folder is the maintainable RTFM documentation set for SemanticScript. It is
technical on purpose: the audience is compiler, linter, editor, stdlib, and
runtime developers who need exact line shapes, lowering behavior, and update
rules.

The docs here should not replace source-of-truth implementation files. They
organize them:

```text
SYNTAX.md                         complete syntax inventory and status table
docs/ast.md                       language and AST design notes
SemanticScript/compiler/semsc.py       reference parser, AST, lowering, CLI
SemanticScript/linter/semlint.py       canonical standalone structured linter
SemanticScript/compiler/libc_registry.py
                                  c.* ABI registry
SemanticScript/shared/call_contracts.py
                                  shared call and route contract facts
STDLIB.md                         stdlib module inventory
vscode-semanticscript/                editor syntax, hovers, semantic tokens
```

When behavior changes, update the implementation first, then update the narrow
doc file that owns that behavior. Avoid giant catch-all edits.

## Contents

- `agents.md` is the compact agent-facing guide.
- `ast.md` records the language and AST design notes.
- `optimization-guide.md` records optimization and app-boundary rules.
- `language/` explains the language model and schemas.
- `reference/` contains target, verb, and maintenance references.
- `toolchain/` documents compiler, linter, and editor tooling.

## Current Status

Active documentation set. Some docs describe executable behavior, while others
mark refined or future runtime work explicitly.

## 1.0 Support Boundary

Use [toolchain/compiler.md](toolchain/compiler.md) as the detailed support
matrix. The release-level boundary is:

| Surface | 1.0 support level | Source of truth |
|---|---|---|
| Python reference compiler | Supported release compiler for `.sscript` and `.sem`, console entry, LLVM IR, JIT run, and clang-linked executables. | `SemanticScript/compiler/semsc.py`, [toolchain/compiler.md](toolchain/compiler.md) |
| VS Code extension | Supported editor tooling for `.sscript` / `.sem`; syntax visibility is not executable support. | [toolchain/vscode-extension.md](toolchain/vscode-extension.md) |
| Refined syntax and partial rows | Inspectable and documented as metadata, fallback, partial, or implemented. | `SYNTAX.md`, [toolchain/compiler.md](toolchain/compiler.md) |
| Web / HTTP runtime | Preview native HTTP/1.1 listener for exact routed `target webServer` programs; HTTP/2/H2O and richer request/response APIs remain future work. | [toolchain/compiler.md](toolchain/compiler.md) |
| Runtime flags | Supported compiler interface for build profile, runtime checks, diagnostics format, IR persistence, and optimization level. | [toolchain/compiler.md](toolchain/compiler.md) |

## Reading Order

| File | Purpose |
|---|---|
| [agents.md](agents.md) | Compact agent-facing language guide with dense schemas and examples. |
| [optimization-guide.md](optimization-guide.md) | Optimization rules that preserve semantic return and failure contracts. |
| [language/README.md](language/README.md) | Language model, executable vs refined surfaces, minimal program. |
| [language/lexical-model.md](language/lexical-model.md) | Tokenization, comments, strings, identifiers, rejected syntax. |
| [language/program-structure.md](language/program-structure.md) | Project headers, imports, entries, operations, ownership. |
| [language/project-layout-build-sem.md](language/project-layout-build-sem.md) | Folder layout, `build.sem` rules, module registry, explicit exports. |
| [language/types-values.md](language/types-values.md) | Primitive types, aliases, constants, literals, records, enums. |
| [language/operations-dataflow.md](language/operations-dataflow.md) | Operation contracts, calls, bindings, variables, control flow. |
| [language/errors-effects-capabilities.md](language/errors-effects-capabilities.md) | Result flow, typed errors, effects, capabilities, authority. |
| [language/memory-state.md](language/memory-state.md) | Storage, shared state, mutation, guard tokens, pointer primitives. |
| [language/records-codecs-boundaries.md](language/records-codecs-boundaries.md) | Records, builders, JSON codecs, trust boundaries. |
| [language/concurrency-time-cleanup.md](language/concurrency-time-cleanup.md) | Cleanup, retry, async, groups, channels, locks, worker pools. |
| [language/native-http-api.md](language/native-http-api.md) | Planned native HTTP server API and route-handler ABI. |
| [language/strict-syntax-research.md](language/strict-syntax-research.md) | Candidate stricter syntax and compile-blocking rules for recurring bug classes. |
| [reference/call-targets.md](reference/call-targets.md) | Built-in call targets, domain methods, c.* calls. |
| [reference/install-policy.md](reference/install-policy.md) | Initial archive install shape and future version-manager plan. |
| [reference/verb-index.md](reference/verb-index.md) | Verb families and schema index. |
| [reference/release-hygiene.md](reference/release-hygiene.md) | Release repository-state, package-metadata, and mirror-file policy. |
| [reference/package-management.md](reference/package-management.md) | Package layout, dependency syntax, and registry deferral policy. |
| [toolchain/compiler.md](toolchain/compiler.md) | semsc.py CLI, parsing, import resolution, codegen modes. |
| [toolchain/linter.md](toolchain/linter.md) | semlint.py commands, diagnostics, tiers. |
| [toolchain/vscode-extension.md](toolchain/vscode-extension.md) | Extension behavior, hover expectations, packaging. |
| [reference/maintenance.md](reference/maintenance.md) | How to keep language, compiler, linter, docs, and extension in sync. |

## Documentation Rules

- Keep one semantic topic per file.
- Put exact line schemas in fenced `semanticscript` or `text` blocks.
- Mark runtime behavior explicitly: parsed metadata, lowered synchronously,
  lowered to real LLVM, or future runtime work.
- Prefer examples from `SemanticScript/sem/feature_tests/` when possible.
- Keep `SYNTAX.md` as the broad inventory; keep these docs as the explanation
  layer developers actually read while implementing.
