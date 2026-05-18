# AgentScript

AgentScript is an experimental language and toolchain for writing programs as a
flat, explicit semantic tape. The current implementation is a real compiler
that emits LLVM IR through `llvmlite`, can JIT-run programs, and can link native
executables through `clang`.

The repository also contains active syntax research in `experiments/`. Those
files explore a refined AgentScript surface designed for agent-generated code:
atomic lines, fixed schemas, explicit dataflow, high-context names, typed
failure edges, guarded mutation, and syntax that is easier for transformer
attention to recover and edit.

## Current vs Proposed Syntax

There are two important surfaces in this repo:

- Current executable AgentScript lives under `AgentScript/` and is documented by
  `AgentScript/AST.md`. This is what `compiler/ascc.py`, `linter/aslint.py`,
  tests, and bootstrap programs use today.
- Refined future syntax lives under `experiments/`, especially
  `experiments/refined_syntax_example.as`. This is a syntax showcase and design
  target. It is not current executable AgentScript.

The VS Code extension understands both surfaces for highlighting, hovers, and
semantic roles. The compiler should not be assumed to accept refined future
syntax until that work is explicitly implemented.

## Repository Layout

```text
AgentScript.md                  Root language/specification document
CHANGELOG.md                    Repository-level changelog
docs/                           Maintainable developer documentation

AgentScript/
  README.md                     Current implementation guide
  AST.md                        Implemented compiler syntax and codegen surface
  compiler/ascc.py              Python reference compiler
  compiler/libc_registry.py     C standard-library signature registry
  linter/aslint.py              Standalone linter
  as/                           Executable AgentScript examples and smoke files
  as/feature_tests/             Focused compiler feature programs
  stdlib_as/                    AgentScript-shaped standard-library modules
  bootstrap/                    AS-written compiler bootstrap stages
  tests/                        Compiler, parity, bootstrap, and stdlib tests

experiments/
  whatsneeded.md                Research and syntax refinement notes
  refined_syntax_example.as     Broad refined syntax showcase
  refined_syntax_graph.md       Mermaid graph of refined sample edges

javascript/                     JavaScript oracle programs
python/                         Python comparison programs
vscode-agentscript/             Local VS Code extension
```

## Current Implementation

The Python reference compiler currently supports the implemented surface in
`AgentScript/AST.md`, including:

- top-level project/runtime/entry metadata;
- operation contracts with `input`, `output`, `effect`, `memory`, `async`, and
  hard-context metadata;
- constants, variables, mutation, labels, branches, and returns;
- named call objects with `call`, `arg`, `run`, `bind`, `bindOk`, `bindError`,
  `ignoreOk`, and `branchIfError`;
- same-file user operation calls with typed returns;
- integer and floating-point math primitives;
- stdout helpers;
- direct `c.*` calls through the libc registry;
- pointer primitives and C-compatible types.

Use `AgentScript/README.md` for the exact current status, command matrix, and
bootstrap notes.

## Refined Syntax Direction

The refined syntax work is aimed at making AgentScript easier for agents and
humans to inspect, patch, and verify. The current design direction favors:

- One semantic action per line.
- Fixed verb schemas instead of overloaded English.
- Explicit storage forms such as `storage local immutable`,
  `storage local mutable`, `storage module mutable`, and guarded
  `sharedState`.
- Operation body contracts such as `operationBody sourceTape`,
  `operationBody runtimeBinding`, `operationBody intrinsic`, and
  `operationBody externalDependency`.
- Runtime binding contracts with `runtimeBindingPrecondition` and
  `runtimeBindingFailure`.
- Trust-boundary metadata for raw-to-validated transitions.
- Records and typed collections instead of dynamic objects and arrays.
- Builders such as `recordBuilder`, `recordSet`, and `recordBuild` instead of
  object literals.
- Collection operation contracts such as `collectionOperationOutput`,
  `collectionOperationFailure`, `collectionOperationEffect`, and
  `collectionOperationMutation`.
- JSON codecs through schema metadata and generated targets like
  `json.decode.Task` and `json.encode.AccountBalanceResponse`.
- Explicit guard-token and defer lifecycle lines for shared-state mutation.

The design rule is simple: syntax should preserve atomic lines, explicit
dataflow, recoverable context, and checkable edges.

## Quick Start

Run current compiler commands from `AgentScript/`:

```powershell
cd AgentScript
python compiler/ascc.py --version
python compiler/ascc.py as/fizzbuzz.as --run
python compiler/ascc.py as/fizzbuzz.as --emit-ir fizzbuzz.ll
python compiler/ascc.py as/fizzbuzz.as --emit-exe fizzbuzz.exe
python linter/aslint.py as/fizzbuzz.as --summary
```

Run the main test groups:

```powershell
cd AgentScript
python tests/compare.py
python tests/as_compiler_parity.py
python tests/test_compiler.py
python tests/test_stdlib.py
python bootstrap/run_bootstrap_chain.py
```

## VS Code Extension

The local extension is in `vscode-agentscript/`. It provides:

- language registration for `.as` and `.agentscript`;
- TextMate and semantic highlighting for current and refined syntax;
- context-aware hovers for concrete line schemas, same-file symbols,
  operation metadata, primitive targets, generated targets, schema values,
  primitive types, opaque inputs, call objects, and role suffixes;
- whole-line segment coloring for declaration/context/action/control/comment
  lines and unknown verbs;
- optional `aslint.py` or `aslint2.py` diagnostics.

The extension skips current-linter diagnostics for refined future syntax by
default because `experiments/refined_syntax_example.as` is not current
executable AgentScript.

Package the extension with:

```powershell
cd vscode-agentscript
npm run check
npx --yes @vscode/vsce package
```

The current packaged artifact is `vscode-agentscript/agentscript-vscode-0.1.9.vsix`.

## Documentation Map

- `docs/README.md` - maintainable developer documentation entry point.
- `SYNTAX.md` - complete syntax inventory and implementation status table.
- `AgentScript.md` - language specification and design intent.
- `AgentScript/AST.md` - implemented compiler syntax and lowering behavior.
- `AgentScript/README.md` - reference implementation guide.
- `AgentScript/CHANGELOG.md` - toolchain release notes.
- `STDLIB.md` - standard-library module and operation inventory.
- `experiments/whatsneeded.md` - refined syntax research and recommendations.
- `experiments/refined_syntax_example.as` - full syntax showcase.
- `experiments/refined_syntax_graph.md` - graph of the showcase dataflow.
- `vscode-agentscript/README.md` - extension-specific usage notes.

## Development Notes

- Treat `AgentScript/` as the executable implementation track.
- Treat `experiments/` as the syntax research track.
- Do not confuse plugin syntax recognition with compiler support.
- Keep refined syntax lines atomic: one verb, one schema, one edge.
- Prefer explicit names and typed failure paths over compact expression syntax.
