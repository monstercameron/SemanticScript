# SemanticScript Developer Documentation

This folder is the maintainable RTFM documentation set for SemanticScript. It is
technical on purpose: the audience is compiler, linter, editor, stdlib, and
runtime developers who need exact line shapes, lowering behavior, and update
rules.

The docs here should not replace source-of-truth implementation files. They
organize them:

```text
SYNTAX.md                         complete syntax inventory and status table
SemanticScript/compiler/semsc.py       reference parser, AST, lowering, CLI
SemanticScript/linter/semlint.py       current standalone source linter
SemanticScript/linter/semlint2.py      structured refinement linter
SemanticScript/compiler/libc_registry.py
                                  c.* ABI registry
STDLIB.md                         stdlib module inventory
vscode-semanticscript/                editor syntax, hovers, semantic tokens
```

When behavior changes, update the implementation first, then update the narrow
doc file that owns that behavior. Avoid giant catch-all edits.

## Reading Order

| File | Purpose |
|---|---|
| [agents.md](agents.md) | Compact agent-facing language guide with dense schemas and examples. |
| [language/README.md](language/README.md) | Language model, executable vs refined surfaces, minimal program. |
| [language/lexical-model.md](language/lexical-model.md) | Tokenization, comments, strings, identifiers, rejected syntax. |
| [language/program-structure.md](language/program-structure.md) | Project headers, imports, entries, operations, ownership. |
| [language/types-values.md](language/types-values.md) | Primitive types, aliases, constants, literals, records, enums. |
| [language/operations-dataflow.md](language/operations-dataflow.md) | Operation contracts, calls, bindings, variables, control flow. |
| [language/errors-effects-capabilities.md](language/errors-effects-capabilities.md) | Result flow, typed errors, effects, capabilities, authority. |
| [language/memory-state.md](language/memory-state.md) | Storage, shared state, mutation, guard tokens, pointer primitives. |
| [language/records-codecs-boundaries.md](language/records-codecs-boundaries.md) | Records, builders, JSON codecs, trust boundaries. |
| [language/concurrency-time-cleanup.md](language/concurrency-time-cleanup.md) | Cleanup, retry, async, groups, channels, locks, worker pools. |
| [reference/call-targets.md](reference/call-targets.md) | Built-in call targets, domain methods, c.* calls. |
| [reference/verb-index.md](reference/verb-index.md) | Verb families and schema index. |
| [toolchain/compiler.md](toolchain/compiler.md) | semsc.py CLI, parsing, import resolution, codegen modes. |
| [toolchain/linter.md](toolchain/linter.md) | semlint.py and semlint2.py commands, diagnostics, tiers. |
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
