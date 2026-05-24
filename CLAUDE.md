# Agent Notes - SemanticScript

This is the repo-level agent guide for SemanticScript. Keep this file and
`AGENTS.md` in sync when the agent contract changes.

## Project Overview

SemanticScript is a flat semantic tape language. One line is one record, and
the first token is the verb. The language is intentionally explicit: dataflow,
effects, failures, memory, time, cleanup, and authority are source data instead
of implicit compiler guesses.

Do not treat SemanticScript like Python, JavaScript, Rust, or C with different
syntax. There are no expressions, infix operators, parenthesized calls, comma
argument lists, braces, semicolons, indentation blocks, generic angle syntax,
exceptions, implicit async, or dynamic object/array literals.

Good:

```text
call totalCall math.addInt64
argument totalCall left Int64 subtotalAmount
argument totalCall right Int64 taxAmount
run totalCall
bind value totalAmount Int64 totalCall
```

Bad:

```text
total = subtotal + tax
```

## Main Source Files

- `SemanticScript/compiler/semsc.py` is the reference parser, AST, lowering, and CLI.
- `SemanticScript/linter/semlint.py` is the canonical structured linter.
- `SemanticScript/tools/sem.py` is the stable wrapper and public agent contract.
- `docs/reference/syntax-inventory.md` is the complete syntax inventory and status table.
- `docs/toolchain/compiler.md` documents supported compiler behavior.
- `docs/toolchain/linter.md` documents linter checks and diagnostic tiers.
- `vscode-semanticscript/extension.js` owns editor syntax, hovers, semantic tokens, and symbol indexing.

Editor support is not executable support. Parser, linter, tests, and docs must
move with editor changes.

## Stable Tool Loop

Prefer the `sem` wrapper before using raw compiler or linter internals.

Load version-matched agent rules:

```powershell
python SemanticScript\tools\sem.py --version --json
python SemanticScript\tools\sem.py skills list --json
python SemanticScript\tools\sem.py skills get sem sem-agent --json
```

Inspect before editing:

```powershell
python SemanticScript\tools\sem.py check --json PATH
python SemanticScript\tools\sem.py check --json --with-readiness PATH
python SemanticScript\tools\sem.py readiness --json PATH
python SemanticScript\tools\sem.py deps list --json PATH
python SemanticScript\tools\sem.py graph --kind summary --json PATH
python SemanticScript\tools\sem.py graph --kind routes --json PATH
python SemanticScript\tools\sem.py slice --operation NAME --json PATH
python SemanticScript\tools\sem.py docs get OPERATION --json
python SemanticScript\tools\sem.py explain SS3104 --json
```

Repair and verify:

```powershell
python SemanticScript\tools\sem.py fix --plan --json PATH | Out-File plan.json -Encoding utf8
python SemanticScript\tools\sem.py patch --dry-run --json PLAN.json
python SemanticScript\tools\sem.py patch --apply --json PLAN.json
python SemanticScript\tools\sem.py fmt --check PATH
python SemanticScript\tools\sem.py check --json PATH
python SemanticScript\tools\sem.py test --json PATH
```

Only auto-apply a plan when the fix payload reports `status: "actionable"` and
`planUsable: true`. A `mixed` plan can still be machine-usable, but start with
`sem patch --dry-run`. A `suggestions-only` plan has no machine-applicable
patch.

Use `--full` only when the compact JSON payload is not enough. Compact payloads
from `check`, `fix`, `graph`, and `slice` are usually the right first hop.

## JSON Surface Rules

Current public surfaces include `sem.version.v1`, `sem.skills.v1`,
`sem.readiness.v1`, `sem.context.v1`, `sem.symbols.v1`, `sem.check.v1`,
`sem.graph.v1`, `sem.slice.v1`, `sem.size.v1`, `sem.docs.v1`,
`sem.explain.v1`, `sem.fixPlan.v1`, `sem.patch.v1`, `sem.dev.v1`,
`sem.test.v1`, `sem.deps.v1`, and provisional `sem.doctor.v0`.

Read `nextCommands` as machine-facing instructions. Prefer `argv` over
`command`, honor `cwd`, and replay only entries where `replayable` is true.

## Minimal Program Shape

```text
project ProgramName
target console
runtime native 1
module examples.programName
entry console main

error ConsoleWriteError
errorCase ConsoleWriteError ConsoleWriteFailed Int32
capability stdoutWriter console.stdout write

operation main
output operation main ExitCode
effect main write console.stdout
memory main noHeapAllocation
async main no
purpose main "Write a line and return a process exit code"
useCapability main stdoutWriter
storage local immutable outputText String "hello world"
call outputWriteCall console.writeLine
argument outputWriteCall text String outputText
run outputWriteCall
ignore ok source outputWriteCall type Void
bind error outputWriteError ConsoleWriteError outputWriteCall
branch error source outputWriteCall target outputWriteFailed
storage local immutable successExitCode ExitCode 0
return value successExitCode
label outputWriteFailed
makeError outputWriteFailure ConsoleWriteError.ConsoleWriteFailed outputWriteError
storage local immutable writeFailedExitCode ExitCode 1
return value writeFailedExitCode
```

Operation metadata is not decorative. Prefer specific `purpose`, useful
`invariant` or `warning` text when relevant, `memory` policy, and `async yes|no`.

## Naming And Lexing

- Lines are trimmed; empty lines are ignored.
- `# comment` is a comment; typed comments include `# rationale:`, `# warning:`, `# agent:`, `# memory:`, `# concurrency:`, `# timing:`, `# failure:`, `# security:`, `# dependency:`, `# observability:`, `# test:`, and `# todo:`.
- Quoted strings keep spaces; supported escapes include `\n`, `\t`, `\r`, `\\`, `\"`, and `\0`.
- Use camelCase for values, calls, labels, and operations.
- Use PascalCase for types, records, enums, and errors.
- Use dotted names for call targets and dependency paths.
- Avoid vague names such as `tmp`, `res`, `data`, `value`, `item`, `x`, `i`, `handler`, and `doThing`.

## Effects, Failures, And Authority

Declare effects only for external or observable resources such as console,
filesystem, network, database, heap, shared state, or process. Pure arithmetic
and formatting helpers should omit effects. Any declared effect needs a matching
capability or authority row.

```text
effect main write console.stdout
capability stdoutWriter console.stdout write
useCapability main stdoutWriter
authority main console.stdout write
```

Fallible calls need explicit success/error handling. Do not hide failures.

## Calls And Dataflow

Calls are multi-row records: `call`, `argument`, `run`, and then `bind`,
`ignore`, or branches. Argument names should match callee input names. Opaque
inputs such as `console`, `environment`, `process`, `httpRequest`,
`databaseClient`, and `clock` are context, not normal LLVM parameters.

Do not add `argument callName console Console console` to built-in
`console.writeLine`; it only needs `argument callName text String valueName`.

## Types And Values

Primitive lowering is explicit: `Bool -> i1`, `Int32`/`ExitCode`/`UInt32 -> i32`,
`Int64`/`UInt64 -> i64`, `Float64 -> f64`, `String -> i8*`,
`OpaquePointer`/`FileHandle -> i8*`, and `Void -> void` where valid.

Use `storage local immutable` by default. Use mutable storage only when mutation
is part of the semantic contract.

## Std Imports And Targets

Std is a library tree, not a build project. Do not add `std/build.sem`.

Preferred imports:

```text
import html standard.html
import http standard.http
import json standard.json
import sqlite standard.sqlite
import gui standard.gui
```

Common call targets include `console.writeLine`, `console.writeIntegerLine`,
`math.addInt64`, `math.subtractInt64`, `math.multiplyInt64`, `math.divideInt64`,
`math.equalInt64`, `math.lessThanInt64`, `math.addFloat64`, and `c.*` targets
listed in `SemanticScript/compiler/libc_registry.py`.

Use `python SemanticScript\tools\sem.py docs get OPERATION_OR_TARGET --json`
before generating calls to standard-library APIs or compiler-owned targets whose
effects, capabilities, failure modes, cleanup, or argument names are not already
known. Apply
`usage.failureHandling.rows` and `usage.cleanup.rows` when their `required`
flags are true; satisfy `usage.preconditions` before the call when present.
`usage.call.rows` alone are only the call-and-bind core.
For non-exported std capabilities, use `usage.authorityRows` or the complete
local declaration/use pairs in `usage.localCapabilityRows`; do not blindly copy
std-internal capability names.
Unexported helper operations report `visibility.apiTier: "helper"` and may carry
`agentWarnings`; prefer exported APIs where available.

Avoid `c.malloc`/`c.free` in demo apps unless heap behavior is the point. If
used, declare heap effects and capabilities, handle allocation failure, and emit
explicit cleanup on every ownership path.

## Records, JSON, And Trust Boundaries

Record, JSON codec, and trust-boundary rows are safe as schema and metadata
context. Do not rely on record `fieldGet` values for executable demo output
unless you are specifically testing record lowering. For demos, print scalar
runtime values and keep schema rows adjacent as context.

## Concurrency And Cleanup

SemanticScript has rows for `defer`, retry policies, task groups, worker pools,
channels, mutexes, select, and intervals. The single-thread backend lowers many
of these as direct-dispatch, single-slot, no-op, or fallthrough behavior. Do not
claim runtime parallelism unless the backend path actually supports it.

Compiler-owned user-op defers run before returns in reverse registration order.

## Change Protocol

When adding or changing language behavior, update these surfaces together:

1. `docs/reference/syntax-inventory.md` schema and status.
2. `SemanticScript/compiler/semsc.py` parser plus lowering or metadata behavior.
3. Minimal executable feature tests when behavior is executable.
4. `SemanticScript/linter/semlint.py` known verbs and checks.
5. `vscode-semanticscript/extension.js` grammar, semantic roles, hover, and symbol index.
6. Narrow docs under `docs/` plus `AGENTS.md` and `CLAUDE.md` when agent behavior changes.
7. Run compiler, linter, and editor checks relevant to the surface.

Never add only highlighting. Parser, linter, docs, and tests must move with
editor support.

## Common Gotchas

- No entry means library mode: compile all operations plus a stub main returning 0, except routed `target webServer` programs, which emit a native HTTP entrypoint.
- Do not add `entry windowsGui OPERATION`; GUI programs use the small native GUI bridge and `standard.gui` contracts.
- `sem check --json` reports the source lane; `sem readiness --json` reports the environment lane.
- `sem test --json PATH` runs project semantic preflight before runtime harnesses unless explicitly overridden.
- A compact fix payload is not valid patch input; save and pass the plan JSON to `sem patch`.
- Use raw `semsc.py` and `semlint.py` commands only for compiler debugging or when the wrapper lacks the needed surface.
