# Agent Notes - SemanticScript

This is the repo-level agent guide for SemanticScript. Keep this file and
`CLAUDE.md` in sync when the agent contract changes.

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

MCP-capable agents can reach the same JSON surfaces through the built-in MCP
server instead of shelling out: run `sem mcp` (stdio) and call the matching
tool (`check`, `readiness`, `graph`, `slice`, `fix`, `patch`, `test`, etc.).
The tools are thin wrappers over these same subcommands, so the loop below
applies unchanged. See `docs/toolchain/compiler.md` ("MCP server").

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
`sem.docsIndex.v1`, `sem.docsSearch.v1`, `sem.explain.v1`,
`sem.fixPlan.v1`, `sem.patch.v1`, `sem.dev.v1`, `sem.test.v1`,
`sem.deps.v1`, and provisional `sem.doctor.v0`.

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
import document standard.document
```

`standard.document` is the browser DOM namespace and targets wasm only: its
`ss_dom_*` runtimeBinding externs resolve against the emscripten js-library
adapter (`std/document/native/ss_dom_runtime.js`), not a native build. Build and
run DOM programs with `SemanticScript/tools/build_wasm.py` (it links the adapter
and enables Asyncify for `document.nextEvent`); see
`docs/toolchain/wasm-emscripten.md`.

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
For lookup over user/generated code, run `docs index --path PATH --db DB --json`
and query it with `docs search QUERY --db DB --json`; MCP mode exposes the same
docs list/get/search surfaces and can keep the path-scoped SQLite index fresh
with its background docs worker. Docs indexing uses real sentence-transformer
embeddings by default; install `requirements-docs.txt` before indexing. When
creating a new project, suggest `sem new --enable-docs-index PATH` if the user
wants local semantic API search; otherwise leave it off. Treat `docs search`
results as discovery candidates and use `docs get`, `slice`, or `--include-docs`
before generating calls.

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

## Dense Language Reference

== core ==
SemanticScript = flat semantic tape. One line = one record. First token = verb.
No expressions, infix ops, parens calls, commas, braces, semicolons, generic
angles, indentation blocks, exceptions, implicit async, dynamic object/array
literals. Context is source data: names, effects, failures, memory, time,
cleanup, authority.

Status: lowered = LLVM now; metadata = parsed/indexed only; sync-fallback =
single-thread lowering; partial = mixed; refined = future/tooling surface.

== stable tool loop ==
Use the `sem` wrapper as the public agent contract before falling back to raw
compiler/linter internals.

Load matching rules:
  python SemanticScript\tools\sem.py --version --json
  python SemanticScript\tools\sem.py skills list --json
  python SemanticScript\tools\sem.py skills get sem sem-agent --json

`skills get --json` is summary-first; add `--full` when raw skill bodies are
actually needed.

On large project surfaces, `check`, `fix`, `graph`, and `slice` are compact by
default. Add `--full` when you explicitly need the full machine payload.

Iteration roles:
  skills get          load version-matched rules before editing
  check               prove current semantic state before/after edits
  graph summary/routes cheap map of the surface before deeper retrieval
  slice               one local semantic neighborhood to edit
  docs                standard-library API guidance before generating calls
  explain             why a rule exists and what safe repairs look like
  fix --plan          derive candidate edits without mutating source
  patch               preview/apply a reviewed plan with stale-file protection
  fmt --check         keep diffs normalized and repair landings stable
  test                behavior validation after semantic preflight is clean
  dev                 watch/restart contract after the surface is close to runnable
  readiness           separate source blockers from environment blockers
  size                cheap footprint probe before expensive graph/detail hops

Check and inspect:
  python SemanticScript\tools\sem.py check --json PATH
  python SemanticScript\tools\sem.py check --json --with-readiness PATH
  python SemanticScript\tools\sem.py readiness --json PATH
  python SemanticScript\tools\sem.py graph --kind summary --json PATH
  python SemanticScript\tools\sem.py graph --kind routes --json PATH
  python SemanticScript\tools\sem.py slice --operation NAME --json PATH
  python SemanticScript\tools\sem.py docs list --module MODULE --json
  python SemanticScript\tools\sem.py docs get OPERATION --json
  python SemanticScript\tools\sem.py explain SS3104 --json

Lower-level fallback surfaces:
  python SemanticScript\tools\sem.py context --json PATH   # lower-level project envelope
  python SemanticScript\tools\sem.py symbols --json PATH   # lower-level full source graph

Repair and verify:
  python SemanticScript\tools\sem.py fix --plan --json PATH | Out-File plan.json -Encoding utf8
  python SemanticScript\tools\sem.py patch --dry-run --json PLAN.json
  python SemanticScript\tools\sem.py patch --apply --json PLAN.json
  python SemanticScript\tools\sem.py fmt --check PATH
  python SemanticScript\tools\sem.py check --json PATH

Only auto-apply a plan when the fix payload reports `status: "actionable"` and
`planUsable: true`. A `mixed` plan still contains useful edits, but it should
start with `sem patch --dry-run`, not blind apply. A `suggestions-only` plan
has no machine-applicable patch, and a compact fix payload is not valid patch
input.

Harness loop, only after semantic preflight is clean:
  python SemanticScript\tools\sem.py test --json PATH
  python SemanticScript\tools\sem.py dev --json PATH

`sem test --json PATH` can execute Python harnesses and app processes when PATH
points at a project surface. Use `--skip-python-harnesses` when the goal is to
skip process-level harness work, not when the goal is project-surface semantic
validation; for that, use `sem check --json PATH`. Skipping Python harnesses
does not hide preflight source diagnostics on project surfaces, and project
Python harnesses are deferred until semantic preflight is clean. Use
`--allow-red-preflight-harnesses` when runtime signal is still worth gathering
on a semantic-red project; in that mode the runtime harnesses are prioritized
and project-surface semantic contract files are deferred. Project test
discovery now includes `tests\*.py`, not only `test_*.py`. Read
`preflightStatus`, `runtimeHarnessStatus`, and `compositeStatus` together
before deciding whether the surface is blocked by source debt, runtime
failures, or both.

`sem check --json` now reports the source lane as one of
`ok`, `ok-with-warnings`, `lint-diagnostics`, `compiler-error`, or
`tool-error`. `sem readiness --json` is the environment lane and exits
nonzero unless the payload is actually `ok`. `sem fix --plan --json` is
blocker-first by default; use `--include-warnings` only when a buildable
surface still needs cleanup guidance. A `mixed` fix plan with
`planUsable: true` is still a valid machine step.

`nextCommands` entries are machine-facing. Prefer `argv` over `command`, honor
`cwd`, and only auto-replay entries where `replayable` is true. When
`replayable` is false, use `requiredArgs` or `artifactInputs` to supply the
missing project path or saved plan file.

Current JSON surfaces:
  sem.version.v1
  sem.skills.v1
  sem.readiness.v1
  sem.context.v1
  sem.symbols.v1
  sem.check.v1
  sem.graph.v1
  sem.slice.v1
  sem.size.v1
  sem.docs.v1
  sem.docsIndex.v1
  sem.docsSearch.v1
  sem.explain.v1
  sem.fixPlan.v1
  sem.patch.v1
  sem.dev.v1
  sem.test.v1
  sem.deps.v1
  sem.doctor.v0  # provisional environment surface

Good:
  call totalCall math.addInt64
  argument totalCall left Int64 subtotalAmount
  argument totalCall right Int64 taxAmount
  run totalCall
  bind value totalAmount Int64 totalCall

Bad:
  total = subtotal + tax

== lex/name ==
Line: trim; empty ignored; # comment; # rationale: typed comment; quoted
strings keep spaces; escapes \n \t \r \\ \" \0; whitespace splits tokens.
Typed comments: rationale invariant warning agent memory concurrency timing
failure security dependency observability test todo.

Names:
  camelCaseValue             ops values calls labels
  PascalCaseType             types records enums errors
  dot.path.target            call/dependency path
  ErrorDomain.ErrorVariant   error variant
Avoid: tmp res data value item x y i handler helper doThing.
Prefer: accountLookupCall validatedTaskTitle consoleStdoutWriter.

== skeleton ==
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
  purpose main "Do the thing exactly"
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

No entry => library mode: compile all ops + stub main returns 0, except routed
`target webServer` programs, which emit a native HTTP entrypoint. Reserved
`target windowsGui` should also be a no-entry target, but only through the
small native GUI bridge described below.

Top:
  project NAME
  target NAME
  runtime NAME VERSION
  module DOTTED.PATH
  mode capturedOutputReplay
  entry console OPERATION
  import ALIAS DOTTED.PATH
  section NAME

== std imports ==
Std is a library tree, not a build project. Do not add `std/build.sem`.
Root relay: `SemanticScript/std/module.sem`.
Module entries: `SemanticScript/std/<module>/main.sem`.
Self-tests: `SemanticScript/std/<module>/main.test.sem`.

Preferred imports:
  import html standard.html
  import http standard.http
  import json standard.json
  import sqlite standard.sqlite
  import gui standard.gui

Std resolution order:
  --std-path PATH
  SEMANTICSCRIPT_STD_PATH or SEMSC_STD_PATH
  vendored ancestor std/
  current-working-directory std/
  compiler-bundled compiler/../std

This means apps outside the repo can still import `standard.*` when compiled by
the installed compiler, or when the std root is passed explicitly.

== windows gui ==
Compiler-owned GUI surface should stay minimal:
  target windowsGui
  targetRuntime PROJECT windowsGui
  guiBackend PROJECT win32|winui3  # win32 default; winui3 scaffold is blocked until Windows App SDK build integration
  native GUI runtime link/codegen bridge
  preserve GuiSession and GuiEvent handler ABI inputs
  lower explicit standard.gui gui.* calls

Do not add `entry windowsGui OPERATION`. Do not move control/event validation
into a giant compiler grammar. `standard.gui` owns GUI functions,
contracts, capabilities, and most validation. Preferred import:
  import gui standard.gui

Do not implement WinUI by adding C# / XAML app sidecars under `apps/`. The app
UI source remains SemanticScript; WinUI belongs behind `guiBackend winui3` as a
native backend adapter exporting the existing `ss_gui_*` ABI.

Standard GUI source shape:
  entry console main
  operation main
  call createApp gui.applicationCreate
  argument createApp title GuiText titleText
  run createApp
  bind value app GuiApplication createApp
  call createWindow gui.windowCreate
  ...
  call runApp gui.applicationRun

GUI handler ABI:
  input saveClicked session GuiSession
  input saveClicked event GuiEvent
  output saveClicked Int32

Reserved gui.* targets live under standard.gui contracts:
  gui.applicationCreate gui.windowCreate gui.buttonCreate
  gui.windowAddControl gui.applicationSetMainWindow gui.applicationRun
  gui.textBoxText gui.textBoxSetText
  gui.listBoxSelectedIndex gui.listBoxAppendItem gui.listBoxClear
  gui.windowClose
  gui.eventKeyCode gui.eventSelectedIndex
  gui.eventWindowWidth gui.eventWindowHeight

== operation ==
  operation OP
  input operation OP NAME TYPE
  output operation OP TYPE...
  output operation OP Result OK_TYPE ERR_TYPE
  effect OP ACTION PATH
  memory OP POLICY...
  async OP yes|no
  purpose OP "text"
  invariant OP "text"
  warning OP "text"
  guarantee OP "text"
  failure OP NAME "text"
  security OP "text"
  timing OP "text"
  observability OP "text"

Owner argument must match current op. Opaque inputs are context, not LLVM params:
console environment process httpRequest databaseClient clock. Do not add
`argument callName console Console console` to built-in console.writeLine; it
only needs `argument callName text String valueName`.

Minimum useful metadata:
  purpose opName "specific intent"
  invariant opName "condition preserved by edits"
  memory opName noHeapAllocation
  async opName no

Effect rule: declare effect only for external/observable resources (console,
filesystem, network, database, heap, shared state, process). Pure arithmetic or
formatting helper ops should omit effect; do not invent `effect OP compute
score`. Any declared effect needs useCapability or authority.

== types/values ==
  Bool -> i1
  Int8/UInt8 -> i8
  Int16/UInt16 -> i16
  Int32/ExitCode/UInt32 -> i32
  Int64/UInt64 -> i64
  Float32 -> f32
  Float64 -> f64
  String -> i8*
  OpaquePointer/FileHandle -> i8*
  Void -> void where valid

  type AccountId String
  type LookupResult Result AccountBalance LookupError
  typeInvariant AccountId "non-empty"
  typeRepresentation AccountId String utf8 nullByte
  typeTrust AccountId trustedInternal
  typeMemory AccountId inline
  typeLayout AccountId packed
  typeParameter LookupResult 0 AccountBalance
  typeLiteralEncoding AccountId utf8
  typeLiteralTerminator AccountId nullByte

  storage local immutable retryLimit Int64 3
  storage local immutable greetingText String "hello"
  storage local immutable strictMode Bool true
  storage local mutable runningTotal Int64 0
Bool tokens: true false yes no 1 0.

  domainLiteral signalKillNumber Int32 9
  domainLiteralSource signalKillNumber posix.SIGKILL
  domainLiteralTrust signalKillNumber trustedStaticLiteral
  literal templateText String
  literalSource templateText "fixtures/template.txt"
  literalBytes templateText 128
  literalDigest templateText sha256 DIGEST
  literalPreview templateText "preview"
  literalTrust templateText trustedStaticLiteral

== state/memory ==
  storage module immutable zeroValue Int64 0
  storage module mutable lastRevision Int64 zeroValue
  storage local immutable stepValue Int64 1
  storage local mutable currentRevision Int64 lastRevision
  set local currentRevision nextRevision
  set module lastRevision nextRevision ownedBy moduleStateOwner

Module mutable => LLVM global. Local mutable => alloca. Owner/protected tails
metadata today.

  sharedState process mutable failureCount Int64 zeroValue
  sharedStateOwner failureCount metricsRuntime
  sharedStateGuard failureCount failureCountGuardToken
  read sharedState currentFailureCount Int64 failureCount protectedBy failureCountGuardToken
  set sharedState failureCount nextFailureCount protectedBy failureCountGuardToken
  guardTokenSource failureCountGuardToken acquireLockCall
  guardTokenOwner failureCountGuardToken metricsRuntime
  guardTokenProtects failureCountGuardToken failureCount
  guardTokenRelease failureCountGuardToken releaseLock

Pointer:
  pointer.loadByte     buffer offset -> byte
  pointer.storeByte    buffer offset value -> void
  pointer.offset       base offset -> ptr
  pointer.difference   left right -> Int64
  pointer.isNull       ptr -> bool/int

== calls ==
Infallible:
  call totalCall math.addInt64
  argument totalCall left Int64 subtotalAmount
  argument totalCall right Int64 taxAmount
  run totalCall
  bind value totalAmount Int64 totalCall

Fallible:
  call writeCall console.writeLine
  argument writeCall text String outputText
  run writeCall
  ignore ok source writeCall type Void
  bind error writeError ConsoleWriteError writeCall
  branch error source writeCall target writeFailed
  storage local immutable successExitCode ExitCode 0
  return value successExitCode
  label writeFailed
  makeError writeFailure ConsoleWriteError.ConsoleWriteFailed writeError
  storage local immutable writeFailedExitCode ExitCode 1
  return value writeFailedExitCode

Async/sync-fallback:
  start fetchCall
  await fetchCall
  bind ok fetchedValue ValueType fetchCall
  bind error fetchError FetchError fetchCall

Attach/discard:
  timeout CALL BUDGET
  cancelOn CALL TOKEN
  useRetry CALL POLICY
  ignore ok source CALL type TYPE
  ignore value source CALL type TYPE

User op:
  operation addTwoValues
  input operation addTwoValues leftValue Int64
  input operation addTwoValues rightValue Int64
  output operation addTwoValues Int64
  call sumCall math.addInt64
  argument sumCall left Int64 leftValue
  argument sumCall right Int64 rightValue
  run sumCall
  bind value sumValue Int64 sumCall
  return value sumValue

  operation main
  output operation main ExitCode
  storage local immutable leftInput Int64 40
  storage local immutable rightInput Int64 2
  call answerCall addTwoValues
  argument answerCall leftValue Int64 leftInput
  argument answerCall rightValue Int64 rightInput
  run answerCall
  bind value answerValue Int64 answerCall
  return value answerValue

Argument names should match callee inputs. Dispatch by callee input order after
dropping opaque inputs.

== control ==
  label NAME
  jump target LABEL
  branch if condition CONDITION target LABEL
  branch error source CALL target LABEL
  branch else target LABEL
  return ok VALUE
  return error VALUE
  return value VALUE
  return void

Loop:
  storage local mutable currentIndex Int64 0
  storage local immutable finalIndex Int64 10
  storage local immutable indexStep Int64 1
  label loopStart
  call doneCall math.greaterThanOrEqualInt64
  argument doneCall left Int64 currentIndex
  argument doneCall right Int64 finalIndex
  run doneCall
  bind value loopDone Bool doneCall
  branch if condition loopDone target loopEnd
  call nextIndexCall math.addInt64
  argument nextIndexCall left Int64 currentIndex
  argument nextIndexCall right Int64 indexStep
  run nextIndexCall
  bind value nextIndex Int64 nextIndexCall
  set local currentIndex nextIndex
  jump target loopStart
  label loopEnd

== error/effect/auth/deps ==
  error ConsoleWriteError
  errorCase ConsoleWriteError ConsoleWriteFailed Int32
  makeError validationFailure RequestError.InvalidJson rawDecodeError
  declareFailure timeoutFailure RequestError.TimedOut timeoutCall

  effect opName write console.stdout
  capability stdoutWriter console.stdout write
  useCapability opName stdoutWriter
  authority opName console.stdout write

  dependency databaseClient kind externalService
  dependencyEffect databaseClient read database.account
  dependencyFunction databaseClient.lookupAccount
  dependencyFunctionInput databaseClient.lookupAccount accountId AccountId
  dependencyFunctionOutput databaseClient.lookupAccount Result AccountBalance LookupError
  dependencyFunctionEffect databaseClient.lookupAccount read database.account
  dependencyFunctionAsync databaseClient.lookupAccount yes

== targets ==
Console:
  console.writeLine argument text only; no argument console console
  console.writeIntegerLine argument value
  console.writeFloatLine argument value

Int64:
  math.addInt64 subtractInt64 multiplyInt64 divideInt64 moduloInt64
  math.equalInt64 notEqualInt64 lessThanInt64 lessThanOrEqualInt64
  math.greaterThanInt64 greaterThanOrEqualInt64 checkedMultiplyInt64

Float64:
  math.addFloat64 subtractFloat64 multiplyFloat64 divideFloat64
  math.equalFloat64 notEqualFloat64 lessThanFloat64 lessThanOrEqualFloat64
  math.greaterThanFloat64 greaterThanOrEqualFloat64
  math.convertInt64ToFloat64 math.convertFloat64ToInt64

c.*:
  call allocateCall c.malloc
  argument allocateCall size ByteCount requestedByteCount
  run allocateCall
  bind value allocatedBuffer OpaquePointer allocateCall

c.* signatures: compiler/libc_registry.py. Prefer SemanticScript camelCase aliases for C
names with underscores.

Heap edge: avoid c.malloc/c.free in demo apps unless the user asks for heap.
If used, declare effect allocate heap, effect free heap, memoryHeap OP yes,
memoryAllocationSource OP ALLOC_CALL, capabilities for heap allocate/free, and
handle c.malloc as fallible with `bind error` + `branch error`. For executable code,
emit an explicit `call ... c.free` cleanup on every ownership path. A
`defer NAME c.free allocatedPointer` row is useful cleanup metadata, but current
compiler lowering treats non-user-op defer targets as metadata, so do not claim
that row alone proves runtime leak freedom. Linters should accept either a
defer row or an explicit cleanup call that consumes the bound allocation.
There is no general stdlib free wrapper today; std/README explicitly says
c.free is one of the host C calls with no useful pure-SemanticScript substitute. Prefer a
domain-specific stdlib release op when the matching allocator provides one
(example: createDeterministicRandomState -> releaseDeterministicRandomState).
For generic heap buffers or duplicateCStringIntoOwnedMemory output, current
stdlib examples still use c.free / defer NAME c.free POINTER.

Domain method:
  type CountdownValue Int64
  call nextCall CountdownValue.subtractPositiveStep
  argument nextCall left CountdownValue currentCountdownValue
  argument nextCall right CountdownValue decrementStep
  run nextCall
  bind value nextCountdownValue CountdownValue nextCall

== records/codecs/bounds ==
Edge rule: record/json/trust lines are safe as schema/metadata context. Do not
rely on record fieldGet values for executable output unless you are explicitly
testing record lowering. For demo apps, keep runtime dataflow scalar and print
the scalar values; use record/json/trust as adjacent metadata only.

  record Task
  recordLayout Task packed
  recordAlign Task 8
  field Task taskId TaskId
  field Task title ValidatedText
  field Task completed Bool
  # metadata/schema above; scalar runtime values below are still the print path
  storage local immutable taskId TaskId 1001
  storage local immutable taskTitle ValidatedText "demo task"

Record field ops are edge/runtime-specific:
  new taskValue Task
  fieldSet taskValue title validatedTitle
  fieldSet taskValue completed false
  fieldGet taskTitle ValidatedText taskValue title

  recordBuilder taskBuilder Task
  recordSet taskBuilder title validatedTitle
  recordSet taskBuilder completed false
  recordBuild buildTaskCall taskBuilder
  recordBuildFailure buildTaskCall TaskError.InvalidTitle

  jsonCodec taskJsonCodec
  jsonCodecStrict taskJsonCodec yes
  jsonCodecUnknownFields taskJsonCodec reject
  jsonCodecInput taskJsonCodec RawJson
  jsonCodecOutput taskJsonCodec Task
  jsonCodecDecodeTarget taskJsonCodec json.parse.Task
  jsonCodecEncodeTarget taskJsonCodec json.stringify.Task
  jsonCodecRequiredField taskJsonCodec title
  jsonCodecDecodeFailure taskJsonCodec TaskDecodeError.MissingTitle
  jsonCodecLimit taskJsonCodec maximumBytes 65536

  trustBoundary ValidatedText
  trustBoundaryKind ValidatedText rawUtf8ToValidatedText
  trustBoundaryInput ValidatedText RawText
  trustBoundaryOutput ValidatedText TrustedText
  trustBoundaryValidator ValidatedText validateText
  trustBoundarySource ValidatedText httpRequest.body

== retry/cleanup/concurrency ==
  retryPolicy lookupRetryPolicy
  retryMaxAttempts lookupRetryPolicy 3
  retryInitialDelay lookupRetryPolicy 50ms
  retryMaximumDelay lookupRetryPolicy 500ms
  retryJitter lookupRetryPolicy yes
  useRetry lookupCall lookupRetryPolicy

  defer releaseDefer releaseLock guardToken
  deferRunOn releaseDefer all
  deferOrder releaseDefer reverseRegistration
  deferFailurePolicy releaseDefer logAndSuppress
  deferConsumes releaseDefer guardToken

Compiler emits user-op defers before returns, reverse registration.

  taskGroup childWorkGroup
  startInGroup childCall childWorkGroup
  awaitGroup childWorkGroup
  bindGroupError childError ChildError childWorkGroup
  branchIfGroupError childWorkGroup childFailed

  workerPool hashWorkerPool size 4
  work hashWork target hashFile
  workArg hashWork path inputFilePath
  submitWork hashWork hashWorkerPool
  awaitWork hashWork

  channel taskChannel Task bounded 1
  send taskChannel builtTask
  receive receivedTask Task taskChannel
  branchIfChannelClosed taskChannel channelClosed

  mutex metricsLock
  lock metricsLock
  unlock metricsLock

  select eventSelect
  selectCase eventSelect taskReady taskReadyBranch
  runSelect eventSelect
  branchSelected eventSelect taskReadyBranch handleTask

  interval heartbeatInterval every 1000ms
  startInterval heartbeatInterval
  awaitIntervalTick heartbeatInterval

Single-thread backend: groups/workers direct-dispatch; channels single slot;
locks/select/interval no-op/fallthrough.

== bindings/intrinsics ==
  operation compareCString
  operationBody compareCString runtimeBinding
  runtimeBinding compareCString runtime.cstring.compare
  runtimeBindingPrecondition compareCString "inputs are null-terminated"
  runtimeBindingFailure compareCString CStringError.InvalidInput

  operation addSignedInt64
  operationBody addSignedInt64 intrinsic
  intrinsicName addSignedInt64 arithmetic.addInt64

Pure ABI names lower directly. Policy-bearing runtime bindings such as retry
delay, metrics increment, metrics lock token sentinels, scheduler sleep,
calendar predicates, and UTF-8 validation must be normal SemanticScript
operation bodies or explicit native runtime calls; known legacy targets are
compile-blocking.

== linter ==
semlint checks and guardrails: unknown verbs; vague names; missing op metadata; hidden
failures; effects without capability; unresolved refs; argument arity/type; dead
stores; unused calls/labels/consts/inputs/binds/caps/error cases/storage;
allocation in loop; heap contradiction; missing allocation source; unpaired
alloc/free; unclosed file; guard source without release; partial retry/trust/
json codec; raw JSON `%s`; fixed-offset parser invariant; width drift; bad
printf width; Result/Void helper shape; file open/close effects; terminal
state cleanup; record align; zero array length; unawaited group/work; lock
without cleanup; duplicate decls; metadata drift; circular type aliases.
T0/T1/T2 correctness. T3 design debt. T4 style.

== internals only / compiler debugging ==
  python SemanticScript/compiler/semsc.py file.sscript --parse-only
  python SemanticScript/compiler/semsc.py file.sscript --run
  python SemanticScript/compiler/semsc.py file.sscript --emit-ir out.ll
  python SemanticScript/compiler/semsc.py file.sscript --emit-exe out.exe
  python SemanticScript/linter/semlint.py file.sscript --format json
  python SemanticScript/linter/semlint.py file.sscript --format human
  python SemanticScript/linter/semlint.py file.sscript --format json
  python SemanticScript/linter/semlint.py file.sscript --tier T3 --code SS0101

== change protocol ==
  1 docs/reference/syntax-inventory.md schema/status
  2 semsc.py parser + lowering or metadata/sync behavior
  3 feature_tests minimal executable case
  4 semlint known verbs/checks
  5 vscode grammar + semantic roles + hover + symbol index
  6 docs narrow topic + AGENTS.md / CLAUDE.md if relevant
  7 run compiler/linter/editor checks

Never add only highlighting. Parser/linter/docs must move with editor support.
