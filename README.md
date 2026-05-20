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
input createTodoHandler request HttpRequest
input createTodoHandler response HttpResponse
output createTodoHandler CSignedInt32
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

### Todo Web Pro

`app/todo-web-pro/` is a multi-user web app backed by native HTTP, SQLite, JSON,
and bcrypt runtime adapters.

It currently covers:

- HTML landing and dashboard pages through `standard.html`.
- Static assets served by the HTTP runtime.
- Register and login with bcrypt cost-12 password hashing.
- Session cookies with HttpOnly and SameSite settings.
- SQLite schema bootstrap with seeded demo data.
- Authenticated todo create, list, complete, uncomplete, and delete flows.
- Cross-user isolation checks in the end-to-end test harness.

Run the verification harness:

```powershell
python app\todo-web-pro\scripts\test_todo_web_pro.py
```

### Kilo Port

`app/Kilo_port/` is a native executable SemanticScript port of antirez/kilo.

It demonstrates:

- Native Windows terminal handling through a generic runtime adapter.
- File load/save.
- Row storage and long-line handling.
- Cursor movement, scrolling, Page Up/Down, Home/End.
- Tab insertion and Kilo-style tab rendering.
- Search with live match traversal.
- JavaScript-oriented syntax highlighting.
- Dirty quit behavior matching Kilo's warning flow.

Run the port smoke tests:

```powershell
python SemanticScript\compiler\semsc.py app\Kilo_port\build.sem --emit-exe --quiet
python app\Kilo_port\scripts\test_kilo_port.py
```

## Syntax Tour

SemanticScript source is a tape of records. There is no expression soup hidden
inside a line. Each row has one job.

### Project Tape

`build.sem` declares the project, registered modules, runtime target, artifacts,
and build-wide constants.

```semanticscript
buildProject todoWebPro
project TodoWebPro
modulePath todoWebPro github.com/monstercameron/SemanticScript/app/todo-web-pro
languageVersion todoWebPro "1.0"
projectVersion todoWebPro "1.0.0"
projectLicense todoWebPro MIT

sourceRoot todoWebPro "."
registerModule todoWebPro app.todo_web_pro "."
registerModule todoWebPro app.todo_web_pro.components "components"
registerModule todoWebPro app.todo_web_pro.pages "pages"

buildConstant todoWebPro serverHostText CNullTerminatedByteString "127.0.0.1"
buildConstant todoWebPro serverPortNumber CSignedInt32 18090
buildConstant todoWebPro databasePath CNullTerminatedByteString "todo_web_pro.db"

mainFile todoWebPro "main.sem"
mainOperation todoWebPro main
targetRuntime todoWebPro nativeExe
nativeOutput todoWebPro "todo_web_pro.exe"

importModule app.todo_web_pro
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
todo-web/
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
input moveCursorRight currentColumn CSignedInt64
output moveCursorRight CSignedInt64
memory moveCursorRight noHeapAllocation
async moveCursorRight no
purpose moveCursorRight "Return the next cursor column."

storage local immutable oneColumn CSignedInt64 1
call nextColumnCall math.addI64
arg nextColumnCall left currentColumn
arg nextColumnCall right oneColumn
run nextColumnCall
bind nextColumn CSignedInt64 nextColumnCall
returnValue nextColumn
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
arg renderedCursorColumnCall rowPointer cursorRowPointer
arg renderedCursorColumnCall rowLength cursorRowLength
arg renderedCursorColumnCall leftVisibleColumn leftVisibleColumn
arg renderedCursorColumnCall fileColumn cursorFileColumn
run renderedCursorColumnCall
bind cursorRenderedColumn CSignedInt64 renderedCursorColumnCall
```

That shape is verbose, but it gives tools a precise patch target. A formatter,
linter, editor action, or agent can change one argument without reconstructing a
whole expression.

### Failure Is Named Dataflow

Fallible calls expose both the success and error edge.

```semanticscript
call openDatabaseCall sqlite.openDatabase
arg openDatabaseCall path databasePath
arg openDatabaseCall mode readWriteCreateSqliteOpenMode
run openDatabaseCall
bindOk openedDatabase SqliteDatabase openDatabaseCall
bindError openDatabaseError SqliteOpenFailure openDatabaseCall
branchIfError openDatabaseCall openDatabaseFailed

defer closeDatabaseDefer sqlite.closeDatabase openedDatabase
```

The cleanup is beside the acquisition. The failure label is named. The error
value is a value. Review tools can see the whole shape.

### HTTP Routes Are Source Facts

Routes are not hidden inside a framework registration callback.

```semanticscript
webServer todoWebProServer
purpose todoWebProServer "Host the Todo Web Pro JSON REST API on localhost:18090."
serverHost todoWebProServer "127.0.0.1"
serverPort todoWebProServer 18090

route todoWebProServer GET "/" homePageHandler
route todoWebProServer GET "/dashboard" dashboardPageHandler
route todoWebProServer POST "/api/auth/login" loginHandler
route todoWebProServer GET "/api/todos" listTodosHandler
route todoWebProServer POST "/api/todos" createTodoHandler
route todoWebProServer POST "/api/todos/:id/complete" completeTodoHandler
route todoWebProServer POST "/api/todos/:id/uncomplete" uncompleteTodoHandler
route todoWebProServer GET "*" notFoundPageHandler
```

That route table is easy to index, diff, lint, and summarize.

### HTML Has Typed Holes

`standard.html` templates declare their holes and the allowed trust context.

```semanticscript
htmlTemplate StatusCardComponent
htmlArg StatusCardComponent apiBaseUrlText HtmlText
htmlArg StatusCardComponent statusBadgeClass HtmlClass
htmlBody StatusCardComponent
  <section class="rounded-xl border border-ink-200 bg-white p-4">
  <div class="{htmlArg.statusBadgeClass}">Server online</div>
  <p>API base: {htmlArg.apiBaseUrlText}</p>
  </section>

operation renderStatusCard
input renderStatusCard apiBaseUrlText HtmlText
input renderStatusCard statusBadgeClass HtmlClass
output renderStatusCard HtmlFragment
memory renderStatusCard arena request
async renderStatusCard no
purpose renderStatusCard "Render the status card with typed HTML holes."

call hydrateStatusCardCall html.hydrate.StatusCardComponent
arg hydrateStatusCardCall apiBaseUrlText apiBaseUrlText
arg hydrateStatusCardCall statusBadgeClass statusBadgeClass
run hydrateStatusCardCall
bind statusCardFragment HtmlFragment hydrateStatusCardCall
returnValue statusCardFragment
```

Text, class, URL, fragment, and document values are different roles. That is the
point: the trust boundary is in the source, not just in a helper function name.

### Native Runtime Boundaries Stay Small

App behavior belongs in SemanticScript or runtime libraries. The compiler only
links generic runtime surfaces.

```semanticscript
call rawModeCall c.terminalEnableRaw
run rawModeCall
bind rawModeStatus CSignedInt32 rawModeCall

call keyCall c.terminalReadKey
run keyCall
bind keyCode KiloKeyCode keyCall
```

The Kilo editor behavior is not embedded in the compiler. The compiler sees
generic terminal calls; the editor logic lives in `app/Kilo_port/main.sem`.

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
- `app/todo-web-pro/`: native web application.
- `app/Kilo_port/`: native terminal editor port.
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

Run a small compiler smoke:

```powershell
python SemanticScript\compiler\semsc.py SemanticScript\tests\tiny.sem --parse-only
python SemanticScript\linter\semlint.py SemanticScript\tests\tiny.sem --summary
```

Build and test Kilo:

```powershell
python SemanticScript\compiler\semsc.py app\Kilo_port\build.sem --parse-only --lint --quiet
python SemanticScript\compiler\semsc.py app\Kilo_port\build.sem --emit-exe --quiet
python app\Kilo_port\scripts\test_kilo_port.py
```

Build and test Todo Web Pro:

```powershell
python app\todo-web-pro\scripts\test_todo_web_pro.py
```

Run broader validation:

```powershell
python -m compileall -q SemanticScript python samples
python -m unittest SemanticScript/linter/test_semlint.py -v
python SemanticScript/tests/test_compiler.py
python SemanticScript/tests/test_stdlib.py
python SemanticScript/tests/feature_coverage.py
python SemanticScript/bootstrap/run_bootstrap_chain.py
npm --prefix vscode-semanticscript run check
```

## Repository Layout

```text
SemanticScript.md                  Root language/specification document
SYNTAX.md                          Syntax inventory and implementation status
CHANGELOG.md                       Repository changelog
docs/                              Maintained developer documentation

SemanticScript/
  compiler/semsc.py                Python reference compiler
  linter/semlint.py                Structured diagnostics linter
  runtime/                         Native runtime adapters
  std/                             SemanticScript standard library
  bootstrap/                       SemanticScript-written compiler stages
  tests/                           Compiler, parity, bootstrap, and stdlib tests

app/
  Kilo_port/                       SemanticScript port of antirez/kilo
  todo-web-pro/                    Native web app with HTTP, SQLite, JSON, bcrypt
  todo/                            Console todo sample

samples/javascript/                JavaScript comparison programs
samples/python/                    Python comparison programs
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
- `docs/toolchain/formatter.md`: formatter CLI and canonical source style.
- `docs/toolchain/linter.md`: linter CLI and diagnostic formats.
- `docs/reference/compatibility.md`: public 1.0 compatibility contract.
- `SYNTAX.md`: complete syntax inventory and implementation status table.
- `SemanticScript.md`: language specification and design intent.
- `CHANGELOG.md`: dated repository history.
- `app/Kilo_port/README.md`: Kilo port notes and parity commands.
- `app/todo-web-pro/README.md`: Todo Web Pro architecture and test commands.

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
- `samples/python/` is canonical; top-level `python/` is a compatibility mirror.
- `.sem` files directly under `SemanticScript/sem/` are tracked alias fixtures
  and should stay aligned with their `.sscript` counterparts.
- `vscode-semanticscript/package.json` uses `semanticscript-local` for local
  VSIX builds; choose a real Marketplace publisher before public publishing.
