# SemanticScript Overview

SemanticScript is an agent-first application language and toolchain. It favors
recoverable context over terse syntax: source rows name operations, inputs,
outputs, effects, capabilities, storage, memory behavior, async behavior,
runtime edges, and invariants directly.

## Design Goal

Modern code is increasingly read, patched, reviewed, and migrated by agents.
Conventional languages often hide maintenance-critical facts in expression
nesting, framework convention, dynamic dispatch, implicit exceptions, global
state, and ambient runtime behavior.

SemanticScript moves those facts into explicit source records. The compiler can
erase redundancy from generated code; the source keeps redundancy where review
tools, editors, linters, and agents need it.

## Core Principles

- Every executable row does one semantic thing.
- Effects and runtime authority are declared, not inferred from framework code.
- Failure is typed dataflow, not ambient exception control.
- Cleanup lives near acquisition.
- Routes, SQL, JSON, HTML, and native runtime boundaries are source facts.
- Names should carry review context.
- Tooling should retrieve one operation, route, failure path, or storage flow
  without reconstructing an entire program.

## Current Toolchain

- `SemanticScript/compiler/semsc.py`: reference parser, resolver, LLVM lowering,
  JIT path, native executable path, and CLI.
- `SemanticScript/linter/semlint.py`: structured diagnostics and repair hints.
- `SemanticScript/formatter/semfmt.py`: canonical formatting.
- `SemanticScript/tools/sem.py`: public agent-facing wrapper for validation,
  retrieval, repair planning, patching, readiness, and test orchestration.
- `vscode-semanticscript/`: local VS Code extension.

## Current Runtime Areas

- Console and native executable support.
- Native HTTP server preview with route metadata and request/response helpers.
- SQLite, JSON, bcrypt, and HTML runtime surfaces used by app demos.
- GUI, async, event, and outbound network surfaces in documented preview or
  experimental states.

Use [docs/reference/syntax-inventory.md](reference/syntax-inventory.md) and
[docs/toolchain/compiler.md](toolchain/compiler.md) for exact implementation
status.

## Agent Workflow

The stable workflow starts with source facts and narrows toward an edit:

```text
skills -> check -> graph/slice -> explain -> fix plan -> dry-run patch -> apply -> check -> test
```

Representative commands:

```powershell
python SemanticScript\tools\sem.py check --json PATH
python SemanticScript\tools\sem.py graph --kind summary --json PATH
python SemanticScript\tools\sem.py slice --operation NAME --json PATH
python SemanticScript\tools\sem.py explain CODE --json
python SemanticScript\tools\sem.py fix --plan --json PATH
python SemanticScript\tools\sem.py patch --dry-run --json PLAN.json
python SemanticScript\tools\sem.py test --json PATH
```

## Public Status

SemanticScript is `0.0.1` pre-release software. The repository contains real
compiler, linter, editor, runtime, and app surfaces, but not every documented
syntax row is production-ready. The compatibility boundary is maintained in
[docs/reference/compatibility.md](reference/compatibility.md).
