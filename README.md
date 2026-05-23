# SemanticScript

SemanticScript is an agent-first application language and toolchain.

It is built around a flat, line-oriented semantic tape where every executable
line is an atomic, named, checkable record. The language does not try to make
source code short. It tries to make source code easy to recover, audit, edit,
and verify inside an agent attention window.

The core idea is simple:

```text
Do not minimize source.
Maximize recoverable context.
```

That is context maxxing: spending source text on names, effects, types,
capabilities, memory behavior, failure paths, cleanup, trust boundaries, route
contracts, and comments so the next maintainer does not have to infer them from
framework magic or runtime convention.

SemanticScript already has a working Python reference compiler. It parses
SemanticScript, resolves modules, emits LLVM IR through `llvmlite`, can JIT-run
programs, and can link native executables through `clang`. The long-term target
is real application development in the same problem space as Node, Python, Bun,
Deno, Express, FastAPI, and Go services, but with source shaped for agentic
maintenance instead of human terseness.

## Start Here

Use the `sem` wrapper first. It is the public agent-facing surface for
validation, retrieval, repair planning, patching, and test orchestration.

```powershell
python -m pip install -r requirements.txt
python SemanticScript\tools\sem.py --version --json
python SemanticScript\tools\sem.py check --json SemanticScript\tests\agent_cli_demo.test.sem
python SemanticScript\tools\sem.py graph --kind summary --json SemanticScript\tests\agent_cli_demo.test.sem
python SemanticScript\tools\sem.py explain SS3104 --json
python SemanticScript\tools\sem.py test --json SemanticScript\tests\agent_cli_demo.test.sem --skip-python-harnesses
```

`SemanticScript\tests\agent_cli_demo.test.sem` is the green validation fixture.
`SemanticScript\tests\tiny.sem` is intentionally diagnostic-heavy and is useful
for repair-plan demos.

On large project surfaces, `check`, `fix`, `graph`, and `slice` JSON output is
compact by default for agent sessions. Use `--full` when you explicitly need
the full payload expansion.

## How The Tools Help In Iteration

These commands are not interchangeable. Each exists to answer one specific
question in an agent edit loop.

- `sem skills get`:
  load version-matched repo guidance before editing so the agent does not guess
  language rules, repair conventions, or app patterns from stale memory.
- `sem check --json`:
  the primary semantic gate. Use it before edits to see what is wrong and after
  edits to verify the source state actually improved. By default it stays on the
  source lane; use `--with-readiness` only when you explicitly want environment
  and runtime-adapter facts embedded into the same payload.
- `sem graph --json`:
  the coarse map. Use `summary` or `routes` first to decide where to drill
  before spending context on detailed source neighborhoods.
- `sem slice --json`:
  the local working set. Use it to pull one operation, route, effect, or
  capability neighborhood into context before making a targeted edit.
- `sem explain CODE --json`:
  the rule explainer. Use it when a diagnostic code is unfamiliar and the agent
  needs the reasoning and safe repair shapes behind that rule.
- `sem fix --plan --json`:
  the proposal step. It turns diagnostics into reviewable candidate edits
  without mutating source. By default it is blocker-first and does not spend
  time synthesizing warning-only repairs; add `--include-warnings` when the
  source is already buildable and you want cleanup guidance. A `mixed` plan is
  still usable when `planUsable: true`, and the command now exits `0` in that
  case so an agent can continue into review or dry-run patching.
- `sem patch --dry-run|--apply`:
  the execution step for an already-reviewed plan. It protects against stale
  files and re-verifies formatting and `check` after apply.
- `sem fmt --check`:
  the diff stabilizer. Use it to make sure the source is normalized before
  trusting a patch or review diff.
- `sem test --json`:
  behavior validation after semantic preflight is clean. This is not the first
  gate on a broken project surface.
- `sem dev --json`:
  the watch/restart contract once the source is close enough to runnable. Use
  it to inspect watch files, restart conditions, and follow-up steps.
- `sem readiness --json`:
  the environment/target separator. Use it when you need to know whether the
  blocker is source code, runtime support, or missing local toolchains.
- `sem size --json`:
  the cheap footprint probe. Use it before heavier graph work when you want a
  quick sense of source volume and helper-family usage.

In practice:

```text
skills -> check -> graph/summary -> slice -> explain -> fix --plan -> patch -> fmt/check -> test/dev
```

Copyable repair loop on a disposable copy:

```powershell
Copy-Item SemanticScript\tests\tiny.sem .\scratch.sem
python SemanticScript\tools\sem.py check --json .\scratch.sem
python SemanticScript\tools\sem.py explain SS3104 --json
python SemanticScript\tools\sem.py slice --operation main --json .\scratch.sem
python SemanticScript\tools\sem.py fix --plan --json .\scratch.sem | Out-File plan.json -Encoding utf8
python SemanticScript\tools\sem.py patch --dry-run --json plan.json
python SemanticScript\tools\sem.py patch --apply --json plan.json
python SemanticScript\tools\sem.py fmt --check .\scratch.sem
python SemanticScript\tools\sem.py check --json .\scratch.sem
```

Only auto-apply a plan when `sem fix --plan --json` returns
`status: "actionable"` and `planUsable: true`. If the payload reports
`status: "mixed"`, the machine edits are only a subset of the remaining work;
use `sem patch --dry-run` first and keep the rest of the diagnostics in view.
If the payload reports `status: "suggestions-only"`, there is no
machine-applicable patch at all. Compact fix payloads are for review only:
generate `--full` before saving a plan for `sem patch`, and `sem patch` now
rejects truncated plans.

## Why This Exists

Modern codebases are increasingly read, patched, reviewed, and migrated by
agents. Conventional languages were optimized for humans writing compact source:
expressions, inference, exceptions, implicit runtime behavior, object shapes,
framework conventions, and dynamic dispatch.

That compactness is expensive for agents. The agent has to reconstruct hidden
context before it can make a safe edit.

SemanticScript moves that context into the source.

- A call has a name.
- Every argument edge has a name.
- Every operation declares effects.
- Failure is dataflow, not ambient exception control.
- Mutable state says where it lives and how it changes.
- Runtime authority is explicit through capabilities.
- HTML, JSON, SQL, HTTP, and native runtime edges have typed surfaces.
- Comments are contract context for tools, not decoration.

The result is source that is longer, but more inspectable. The compiler can
erase redundancy from generated code. The source keeps redundancy where review
tools, linters, indexers, and agents need it.

## The Sell

SemanticScript is for code that should be maintained by humans and agents
without guessing.

It is a bet that the best source format for agent-authored software is not the
smallest one. It is the one where the next correct edit is easiest to infer,
verify, and review.

What you get:

- Local reasoning: an operation carries its own purpose, effects, memory model,
  async model, and invariants.
- Safer edits: call sites are named records, so tools can patch one argument or
  one branch without rewriting a nested expression tree.
- Better reviews: diffs show changed effects, changed failure paths, changed
  routes, changed storage, and changed capabilities as first-class rows.
- Stronger linting: vague names, missing capabilities, hidden effects,
  unresolved values, type drift, route drift, and trust-boundary gaps can be
  diagnosed from source-level facts.
- Runtime clarity: native adapters are explicit. App behavior stays in
  SemanticScript source or runtime libraries, not hidden inside compiler magic.
- Agent ergonomics: source is easy to slice. An agent can retrieve one
  operation, one failure path, one route, or one storage flow and still have the
  context needed to edit it.

In short:

```text
JavaScript/Python: compress intent into syntax, scope, libraries, and runtime behavior.
SemanticScript: preserve intent as explicit, line-addressable facts.
```

## Context Maxxing

Context maxxing is the design discipline behind SemanticScript.

It means every line should carry useful local context, and every important edge
should be named:

```semanticscript
operation createTodoHandler
input operation createTodoHandler request HttpRequest
input operation createTodoHandler response HttpResponse
output operation createTodoHandler CSignedInt32
effect createTodoHandler read http.request.body
effect createTodoHandler readWrite database
effect createTodoHandler write http.response
memory createTodoHandler heap auto
async createTodoHandler no
purpose createTodoHandler "Create one todo owned by the authenticated session user."
invariant createTodoHandler "The user id comes from the session, never from request JSON."
useCapability createTodoHandler httpRequestReader
useCapability createTodoHandler httpResponseWriter
useCapability createTodoHandler sqliteDatabaseReadWriter
```

That header is not boilerplate. It is a compact review packet:

- What resource is read?
- What resource is written?
- Does the operation allocate?
- Can it suspend?
- Which capability authorizes each effect?
- What security invariant must survive refactors?

Traditional code often hides those answers in implementation details. In
SemanticScript, those answers are part of the operation's shape.

## Current Apps

This repo now contains real executable apps, not only toy syntax fixtures.

### TaskForge Web

`apps/taskforge-web/` is a multi-user web app backed by native HTTP, SQLite, JSON,
and bcrypt runtime adapters.

It currently covers:

- HTML landing and dashboard pages through `standard.html`.
- Static assets served by the HTTP runtime.
- Register and login with bcrypt cost-12 password hashing.
- Session cookies with HttpOnly and SameSite settings.
- SQLite schema bootstrap with seeded demo data.
- Authenticated todo create, list, complete, uncomplete, and delete flows.
- Cross-user isolation checks in the end-to-end test harness.
- Known 501 stub for the remaining item show route.

Run the verification harness:

```powershell
python apps\taskforge-web\scripts\test_taskforge_web.py
```

### Curated App Set

`apps/` keeps the maintained demo set:

- `apps/taskforge-tui/`: console todo app with JSON persistence.
- `apps/desktop-window-smoke/`: minimal Windows GUI smoke fixture.
- `apps/html-template-lab/`: first-class HTML/template syntax demo.
- `apps/http-runtime-gauntlet/`: native HTTP conformance harness.
- `apps/taskforge-web/`: flagship web app.

The Kilo port is now parked at `experiments/kilo-port/`. It is still useful as a
large terminal-editor stress port, but it is not part of the polished app demo
set.

## Syntax Tour

SemanticScript source is a tape of records. There is no expression soup hidden
inside a line. Each row has one job.

### Project Tape

`build.sem` declares the project, registered modules, runtime target, artifacts,
and build-wide constants.

```semanticscript
buildProject taskForgeWeb
project TaskForgeWeb
modulePath taskForgeWeb github.com/monstercameron/SemanticScript/apps/taskforge-web
languageVersion taskForgeWeb "1.0"
projectVersion taskForgeWeb "1.0.0"
projectLicense taskForgeWeb MIT

sourceRoot taskForgeWeb "."
registerModule taskForgeWeb app.taskforge_web "."
registerModule taskForgeWeb app.taskforge_web.components "components"
registerModule taskForgeWeb app.taskforge_web.pages "pages"

buildConstant taskForgeWeb serverHostText CNullTerminatedByteString "127.0.0.1"
buildConstant taskForgeWeb serverPortNumber CSignedInt32 18090
buildConstant taskForgeWeb databasePath CNullTerminatedByteString "taskforge_web.db"

mainFile taskForgeWeb "main.sem"
mainOperation taskForgeWeb main
targetRuntime taskForgeWeb nativeExe
nativeOutput taskForgeWeb "taskforge_web.exe"

importModule app.taskforge_web
```

The build tape is intentionally explicit. It gives compilers, editors, CI,
release tooling, and agents the same project facts.

### Project Layout

A minimal console app keeps the build tape and executable source at the project
root:

```text
hello-console/
  build.sem
  main.sem
  main.test.sem
```

A native web app usually keeps route handlers in the root module and supporting
code in registered folders:

```text
taskforge-web/
  build.sem
  main.sem
  routes/
    main.sem
    main.test.sem
  storage/
    main.sem
    main.test.sem
```

A multi-module library registers each module folder in `build.sem`; colocated
`*.test.sem` files live beside the modules they validate:

```text
todo-domain/
  build.sem
  domain/
    main.sem
    main.test.sem
  persistence/
    main.sem
    main.test.sem
  facade/
    main.sem
    main.test.sem
```

Generated artifacts belong in ignored build/cache folders such as `build/` and
`.semcache/`, not beside source modules.

### Module Context

Modules carry ownership and non-ownership context. This is useful for agents:
they know where behavior belongs before editing.

```semanticscript
module app.kiloport
modulePurpose app.kiloport "Kilo-style terminal editor ported to executable SemanticScript."
moduleOwns app.kiloport "Editor row storage, file load/save, ANSI rendering, keyboard handling, search, and mutation flow."
moduleDoesNotOwn app.kiloport "SemanticScript compiler/runtime terminal primitives or the upstream Kilo C source."
moduleInvariant app.kiloport "The edited file path comes from argv[1] when present, then KILO_FILE, otherwise kilo.txt."
```

### Storage, Not Var Or Const

Current SemanticScript uses `storage`, with scope and mutability on the row.

```semanticscript
storage module immutable maxRows CSignedInt64 2048
storage module immutable rowCapacity CSignedInt64 4096
storage module immutable successExitCode ExitCode 0

operation moveCursorRight
input operation moveCursorRight currentColumn CSignedInt64
output operation moveCursorRight CSignedInt64
memory moveCursorRight noHeapAllocation
async moveCursorRight no
purpose moveCursorRight "Return the next cursor column."

storage local immutable oneColumn CSignedInt64 1
call nextColumnCall math.addI64
argument nextColumnCall left CSignedInt64 currentColumn
argument nextColumnCall right CSignedInt64 oneColumn
run nextColumnCall
bind value nextColumn CSignedInt64 nextColumnCall
return value nextColumn
```

Mutable storage is equally explicit:

```semanticscript
storage local mutable cursorColumn CSignedInt64 zeroI64
storage local immutable cursorColumnAfterInsert CSignedInt64 nextCursorColumn
set local cursorColumn cursorColumnAfterInsert
```

The names are deliberately contextual. `cursorColumn` carries more maintenance
value than `x`, `cx`, or `i`.

### Calls Are Dataflow Records

SemanticScript does not hide a call inside an expression. It gives the call a
stable identity, names each argument edge, runs it, and binds the result.

```semanticscript
call renderedCursorColumnCall renderedColumnForFileColumn
argument renderedCursorColumnCall rowPointer EditorRowPointer cursorRowPointer
argument renderedCursorColumnCall rowLength CSignedInt64 cursorRowLength
argument renderedCursorColumnCall leftVisibleColumn CSignedInt64 leftVisibleColumn
argument renderedCursorColumnCall fileColumn CSignedInt64 cursorFileColumn
run renderedCursorColumnCall
bind value cursorRenderedColumn CSignedInt64 renderedCursorColumnCall
```

That shape is verbose, but it gives tools a precise patch target. A formatter,
linter, editor action, or agent can change one argument without reconstructing a
whole expression.

### Failure Is Named Dataflow

Fallible calls expose both the success and error edge.

```semanticscript
call openDatabaseCall sqlite.openDatabase
argument openDatabaseCall path CNullTerminatedByteString databasePath
argument openDatabaseCall mode SqliteOpenMode readWriteCreateSqliteOpenMode
run openDatabaseCall
bind ok openedDatabase SqliteDatabase openDatabaseCall
bind error openDatabaseError SqliteOpenFailure openDatabaseCall
branch error source openDatabaseCall target openDatabaseFailed

defer closeDatabaseDefer sqlite.closeDatabase openedDatabase
```

The cleanup is beside the acquisition. The failure label is named. The error
value is a value. Review tools can see the whole shape.

### HTTP Routes Are Source Facts

Routes are not hidden inside a framework registration callback.

```semanticscript
webServer taskForgeWebServer
purpose operation taskForgeWebServer "Host the TaskForge Web JSON REST API on localhost:18090."
serverHost taskForgeWebServer "127.0.0.1"
serverPort taskForgeWebServer 18090

route taskForgeWebServer GET "/" homePageHandler
route taskForgeWebServer GET "/dashboard" dashboardPageHandler
route taskForgeWebServer GET "/assets/:filename" staticAssetHandler
route taskForgeWebServer GET "/health" healthHandler
route taskForgeWebServer GET "/api/version" versionHandler
route taskForgeWebServer POST "/api/auth/register" registerHandler
route taskForgeWebServer POST "/api/auth/login" loginHandler
route taskForgeWebServer POST "/api/auth/logout" logoutHandler
route taskForgeWebServer GET "/api/auth/me" meHandler
route taskForgeWebServer GET "/api/todos" listTodosHandler
route taskForgeWebServer POST "/api/todos" createTodoHandler
route taskForgeWebServer GET "/api/todos/:id" showTodoHandler
route taskForgeWebServer DELETE "/api/todos/:id" deleteTodoHandler
route taskForgeWebServer POST "/api/todos/:id/complete" completeTodoHandler
route taskForgeWebServer POST "/api/todos/:id/uncomplete" uncompleteTodoHandler
route taskForgeWebServer GET "*" notFoundPageHandler
```

That route table is easy to index, diff, lint, and summarize.

### HTML Infers Hydrate Holes

`standard.html` templates infer hydrate arguments from `{name}` and
`{record.field}` holes in the template body. Plain text/class-like values are
`String`; generated markup stays explicit as `HtmlFragment` or `HtmlDocument`.

```semanticscript
html template StatusCardComponent
html body template StatusCardComponent
  <section class="rounded-xl border border-ink-200 bg-white p-4">
  <div class="{statusBadgeClass}">Server online</div>
  <p>API base: {apiBaseUrlText}</p>
  </section>

operation renderStatusCard
input operation renderStatusCard apiBaseUrlText String
input operation renderStatusCard statusBadgeClass String
output operation renderStatusCard HtmlFragment
memory renderStatusCard arena request
async renderStatusCard no
purpose operation renderStatusCard "Render the status card with inferred HTML holes."

call hydrateStatusCardCall html.hydrate.StatusCardComponent
argument hydrateStatusCardCall apiBaseUrlText String apiBaseUrlText
argument hydrateStatusCardCall statusBadgeClass String statusBadgeClass
run hydrateStatusCardCall
bind value statusCardFragment HtmlFragment hydrateStatusCardCall
return value statusCardFragment
```

String holes are escaped by sink context. Fragment and document values can only
hydrate text-content positions where raw markup composition is intentional.

### Native Runtime Boundaries Stay Small

App behavior belongs in SemanticScript or runtime libraries. The compiler only
links generic runtime surfaces.

```semanticscript
call rawModeCall c.terminalEnableRaw
run rawModeCall
bind value rawModeStatus CSignedInt32 rawModeCall

call keyCall c.terminalReadKey
run keyCall
bind value keyCode KiloKeyCode keyCall
```

The Kilo editor behavior is not embedded in the compiler. The compiler sees
generic terminal calls; the editor logic lives in `experiments/kilo-port/main.sem`.

## Benefits By Role

### For Agents

- Less hidden context to infer before editing.
- More stable names to target in patches.
- Operation slices carry purpose, effects, memory, async, and failure shape.
- Route, SQL, HTML, JSON, and runtime edges are easy to index.
- Linter diagnostics can cite the exact row and the missing contract.

### For Reviewers

- Diffs show semantic changes directly.
- Capability changes are visible.
- Failure-path changes are visible.
- Route and dependency changes are visible.
- Vague naming is easier to reject early.

### For Tooling

- The source is already a fact table.
- Editors can provide line-schema hovers and semantic token roles.
- CI can lint unresolved capabilities, effect drift, missing cleanup, and
  trust-boundary violations.
- Future indexing tools can build call graphs, route maps, failure graphs, and
  memory graphs without framework-specific guessing.

### For Runtime Work

- Native adapters stay explicit.
- Apps call `standard.http`, `standard.sqlite`, `standard.json`,
  `standard.bcrypt`, `standard.html`, and terminal primitives through named
  surfaces.
- The compiler links runtime sources only when the program uses those targets.
- App logic does not get smuggled into compiler lowering.

## Current Implementation

The current repository contains:

- `SemanticScript/compiler/semsc.py`: Python reference compiler.
- `SemanticScript/linter/semlint.py`: structured diagnostics linter.
- `SemanticScript/std/`: standard-library modules.
- `SemanticScript/runtime/`: native runtime adapters.
- `apps/`: curated runnable app demos.
- `experiments/kilo-port/`: native terminal editor stress port.
- `vscode-semanticscript/`: local VS Code language extension.
- `SYNTAX.md`: implementation-status table for the syntax surface.

The compiler supports project tapes, module imports, operation contracts,
storage, calls, branches, typed returns, native executables, native HTTP,
SQLite, JSON, bcrypt, HTML hydration, GUI and terminal runtime adapters, and
many refined metadata rows. `SYNTAX.md` is the source of truth for which rows
are implemented, partial, or design-target syntax.

## Quick Start

Install Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

List and run the central project test suites:

```powershell
python SemanticScript\tests\run_suite.py --list
python SemanticScript\tests\run_suite.py unit
python SemanticScript\tests\run_suite.py component
python SemanticScript\tests\run_suite.py integration
python SemanticScript\tests\run_suite.py e2e
python SemanticScript\tests\run_suite.py all
```

GitHub Actions uses the same runner through the `ci-fast`, `editor`, and
`ci-release` suite aliases.

Run the sem-first quick path:

```powershell
python SemanticScript\tools\sem.py --version --json
python SemanticScript\tools\sem.py skills list --json
python SemanticScript\tools\sem.py check --json SemanticScript\tests\agent_cli_demo.test.sem
python SemanticScript\tools\sem.py fmt --check SemanticScript\tests\agent_cli_demo.test.sem
python SemanticScript\tools\sem.py test --json SemanticScript\tests\agent_cli_demo.test.sem --skip-python-harnesses
```

Run the lower-level component smoke when working on compiler, linter, or
formatter internals:

```powershell
python SemanticScript\compiler\semsc.py SemanticScript\tests\tiny.sem --parse-only
python SemanticScript\linter\semlint.py SemanticScript\tests\tiny.sem --summary
python SemanticScript\formatter\semfmt.py --check SemanticScript\tests\tiny.sem
```

Build and test the app demos:

```powershell
python -m unittest SemanticScript.tests.test_app_runtime_smoke -v
```

Run broader validation:

```powershell
python SemanticScript\tests\run_suite.py ci-fast
python SemanticScript\tests\run_suite.py ci-release
```

## Agent Workflow Interfaces

The `sem` wrapper is the stable agent-facing surface. Use it before dropping to
direct compiler, linter, or runtime internals.

Versioned rule and environment discovery:

```powershell
python SemanticScript\tools\sem.py --version --json
python SemanticScript\tools\sem.py skills list --json
python SemanticScript\tools\sem.py skills get sem sem-agent --json
python SemanticScript\tools\sem.py readiness --json SemanticScript\tests\agent_cli_demo.test.sem
```

`sem skills get ... --json` is summary-first for long agent sessions. Add
`--full` when the raw skill bodies are actually needed.

Structured validation and architecture retrieval:

```powershell
python SemanticScript\tools\sem.py check --json SemanticScript\tests\agent_cli_demo.test.sem
python SemanticScript\tools\sem.py test --json SemanticScript\tests\agent_cli_demo.test.sem --skip-python-harnesses
python SemanticScript\tools\sem.py graph --kind summary --json apps\taskforge-web
python SemanticScript\tools\sem.py graph --kind routes --json apps\taskforge-web
python SemanticScript\tools\sem.py graph --kind effects --json apps\taskforge-web
python SemanticScript\tools\sem.py slice --operation createTodoHandler --json apps\taskforge-web
python SemanticScript\tools\sem.py slice --route POST:/api/todos --json apps\taskforge-web
python SemanticScript\tools\sem.py slice --symbol serverPortNumber --json apps\taskforge-web
python SemanticScript\tools\sem.py explain SS3104 --json
python SemanticScript\tools\sem.py size --json apps\taskforge-web
```

Lower-level fallback surfaces:

```powershell
python SemanticScript\tools\sem.py context --json apps\taskforge-web
python SemanticScript\tools\sem.py symbols --json apps\taskforge-web
```

Use `agent_cli_demo.test.sem` for a clean green-path validation loop. Use
`apps\taskforge-web` for richer graph, slice, readiness, dev, and app-harness
inspection.

Repair, patch, and multi-step loop commands:

```powershell
Copy-Item SemanticScript\tests\tiny.sem .\scratch.sem
python SemanticScript\tools\sem.py check --json .\scratch.sem
python SemanticScript\tools\sem.py explain SS3104 --json
python SemanticScript\tools\sem.py slice --operation main --json .\scratch.sem
python SemanticScript\tools\sem.py fix --plan --json .\scratch.sem | Out-File plan.json -Encoding utf8
python SemanticScript\tools\sem.py patch --dry-run --json plan.json
python SemanticScript\tools\sem.py patch --apply --json plan.json
python SemanticScript\tools\sem.py fmt --check .\scratch.sem
python SemanticScript\tools\sem.py check --json .\scratch.sem
python SemanticScript\tools\sem.py dev --json apps\taskforge-web
python SemanticScript\tools\sem.py test --json apps\taskforge-web
```

Use the semantic loop first:

```powershell
python SemanticScript\tools\sem.py check --json PATH
python SemanticScript\tools\sem.py graph --kind summary --json PATH
python SemanticScript\tools\sem.py slice --operation NAME --json PATH
python SemanticScript\tools\sem.py explain CODE --json
python SemanticScript\tools\sem.py fix --plan --json PATH
python SemanticScript\tools\sem.py patch --dry-run --json PLAN.json
python SemanticScript\tools\sem.py patch --apply --json PLAN.json
python SemanticScript\tools\sem.py check --json PATH
```

Use the harness loop only when semantic preflight is clean:

```powershell
python SemanticScript\tools\sem.py test --json PATH
python SemanticScript\tools\sem.py dev --json PATH
```

`sem test --json apps\taskforge-web` now carries the same preflight semantic
status as `sem check --json apps\taskforge-web`. A passing app harness no
longer masks project-level diagnostics. Use `--skip-python-harnesses` when the
goal is process-free app-harness suppression rather than semantic validation;
for project surfaces, `sem check --json` remains the primary semantic gate.
`sem check --json` now distinguishes source states more explicitly:
`ok`, `ok-with-warnings`, `lint-diagnostics`, `compiler-error`, and
`tool-error`. `sem test --json` still reports top-level `status: "diagnostics"`
when preflight is red, but the nested `preflightStatus` carries the finer
source-lane state. Python harness execution is deferred until semantic
preflight is clean unless you use `--allow-red-preflight-harnesses`; in that
mode the tool prioritizes runtime harnesses and defers project-surface
semantic contract files.

`sem dev --json apps\taskforge-web` currently demonstrates a quality-red watch
plan for the flagship app, not a restart-ready loop. It is useful for
inspecting watch files, scope, and follow-up commands while the project is
still failing semantic quality checks.

Only hand `sem patch --apply` a plan when `sem fix --plan --json` returns
`status: "actionable"` and `planUsable: true`. A `mixed` plan is still useful,
but it is review-first and should start with `sem patch --dry-run`. A compact
fix payload is not a valid patch input; emit `--full` before saving a plan.

Current stable `v1` JSON contracts:

- `sem.version.v1`
- `sem.skills.v1`
- `sem.readiness.v1`
- `sem.context.v1`
- `sem.symbols.v1`
- `sem.check.v1`
- `sem.graph.v1`
- `sem.slice.v1`
- `sem.explain.v1`
- `sem.fixPlan.v1`
- `sem.patch.v1`
- `sem.size.v1`
- `sem.dev.v1`
- `sem.test.v1`

Current provisional machine surface:

- `sem.doctor.v0`

These commands are covered by focused unit and subprocess contract tests in
`SemanticScript/tests/test_sem_cli.py` and
`SemanticScript/tests/test_command_contracts.py`.

The core repair-loop payloads also carry `nextCommands` hints so an agent can
move from check to explain, slice, fix-plan, patch, and test without inventing
the loop from scratch. `context`, `symbols`, and `doctor` are still useful
lower-level retrieval or environment surfaces, but they are not the main repair
navigation path. These follow-ups now carry:

- `argv`: replay-safe argument vectors
- `cwd`: the intended working directory
- `replayable`: whether the step can be executed exactly as emitted
- `requiredArgs` / `artifactInputs`: extra path or artifact requirements for
  non-replayable follow-ups

`sem test --json` also separates source and runtime lanes with
`preflightStatus`, `runtimeHarnessStatus`, and `compositeStatus`.

## Repository Layout

```text
SYNTAX.md                          Syntax inventory and implementation status
CHANGELOG.md                       Repository changelog
docs/                              Maintained developer documentation
docs/semantic-script.md             Root language/specification document

SemanticScript/
  compiler/semsc.py                Python reference compiler
  linter/semlint.py                Structured diagnostics linter
  runtime/                         Native runtime adapters
  std/                             SemanticScript standard library
  tests/                           Compiler, parity, and stdlib tests

apps/
  desktop-window-smoke/            Minimal Windows GUI smoke fixture
  html-template-lab/               HTML/template syntax demo
  http-runtime-gauntlet/            Native HTTP conformance harness
  taskforge-tui/                    Keyboard-driven terminal app with JSON persistence
  taskforge-web/                    Native web app with HTTP, SQLite, JSON, bcrypt

experiments/
  kilo-port/                       SemanticScript port of antirez/kilo

python/                            Python comparison programs
vscode-semanticscript/             Local VS Code extension
third_party/                       Vendored native dependencies and submodules
```

## Documentation Map

- `docs/README.md`: documentation entry point.
- `docs/language/README.md`: language model and executable vs refined surfaces.
- `docs/language/lexical-model.md`: identifiers, comments, strings, and
  rejected syntax.
- `docs/language/memory-state.md`: storage, mutation, shared state, and memory
  behavior.
- `docs/language/errors-effects-capabilities.md`: effects, capabilities, and
  typed failure paths.
- `docs/toolchain/compiler.md`: compiler CLI and backend behavior.
- `docs/toolchain/agent-workflows.md`: stable agent-facing command paths and
  multi-step SemanticScript repair loop.
- `docs/toolchain/formatter.md`: formatter CLI and canonical source style.
- `docs/toolchain/linter.md`: linter CLI and diagnostic formats.
- `docs/reference/compatibility.md`: public 1.0 compatibility contract.
- `SYNTAX.md`: complete syntax inventory and implementation status table.
- `docs/ast.md`: language and AST design notes.
- `docs/semantic-script.md`: language specification and design intent.
- `CHANGELOG.md`: dated repository history.
- `apps/README.md`: curated app demo index.
- `apps/taskforge-web/README.md`: TaskForge Web architecture and test commands.
- `experiments/kilo-port/README.md`: Kilo port notes and parity commands.

## VS Code Extension

The local extension is in `vscode-semanticscript/`. It provides:

- language registration for `.sscript` and `.sem`;
- TextMate and semantic highlighting for current and refined syntax;
- context-aware hovers for line schemas, symbols, operation metadata, call
  objects, primitive targets, generated targets, schema values, and role
  suffixes;
- whole-line segment coloring for declaration, context, action, control, and
  comment rows;
- optional `semlint.py` diagnostics.

Check or package it with:

```powershell
cd vscode-semanticscript
npm run check
npx --yes @vscode/vsce package
```

Generated `.vsix` files are ignored and should be attached outside the repo.

## Design Rules

These are the rules that shape the language:

1. Abstraction must increase context.
2. Every executable line does one semantic thing.
3. Hidden behavior is illegal by default.
4. Failure is explicit dataflow.
5. Cleanup lives next to acquisition.
6. Async is structured, bounded, and cancellable.
7. Types encode intent, trust, memory, and layout.
8. Comments are semantic context.
9. Control flow is graphable.
10. Dependencies expose contracts.
11. Trust boundaries are explicit.
12. Observability is semantic.

That is the practical meaning of context maxxing: source code should be dense
with the facts needed to maintain it safely.

## Release Hygiene

Release policy lives in `docs/reference/release-hygiene.md`.
The public 1.0 compatibility contract lives in
`docs/reference/compatibility.md`.

- First-party SemanticScript source, docs, samples, and tooling are distributed
  under the MIT License in the root `LICENSE`.
- `python/` is the canonical home for Python comparison programs.
- `.sem` files directly under `SemanticScript/sem/` are tracked alias fixtures
  and should stay aligned with their `.sscript` counterparts.
- The initial VS Code extension release is local VSIX only.
  `vscode-semanticscript/package.json` uses `semanticscript-local` for local
  builds; choose a real Marketplace publisher before public publishing.
