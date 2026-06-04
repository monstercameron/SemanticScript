# SemanticScript VS Code Extension

Local VS Code extension for SemanticScript `.sscript` and `.sem` files.

This extension is editor tooling. It recognizes the current executable
SemanticScript surface plus the design/spec syntax used across the repository,
including native HTTP server APIs, first-class HTML templates, route metadata,
explicit runtime checks, and refinement-only documentation forms.

## Contents

- `extension.js` implements extension behavior.
- `package.json` defines VS Code contribution points and settings.
- `language-configuration.json` defines editor language behavior.
- `icons/` contains the extension icon, language file icons, and optional file
  icon theme.
- `syntaxes/` contains TextMate grammar assets.
- `.vscode/` contains local extension debugging configuration.

## Current Status

Active editor tooling. The package version follows `version.json` and
`package.json`. It supports highlighting, semantic tokens, hovers, inlay hints,
project-aware navigation, completions, same-file rename, lint integration,
quick-fix access to `fix --plan`, and direct `semanticscript.py` executable
builds from VS Code. The package also includes a
SemanticScript gallery icon, language file icon fallback, and selectable
SemanticScript file icon theme.

## Release Readiness

The initial 1.0 package is local VSIX only. Marketplace publishing is out of
scope until the release owner selects a real Marketplace `publisher` value to
replace `semanticscript-local`.

The extension package is licensed as MIT, matching the root repository license.
Run `npm ci` after a fresh checkout, then use `npm run package:vsix` for local
VSIX builds after accepting the publisher metadata constraint for the target
release.

## Features

- Language registration for `.sscript` and `.sem`.
- VS Code extension gallery icon and SemanticScript file icons for `.sscript`,
  `.sem`, `build.sscript`, and `build.sem`.
- TextMate highlighting for verbs, types, strings, numbers, comments, symbols,
  qualified paths, error variants, schema values, primitive targets, generated
  targets, domain targets, and embedded `html body template`, `jsonBody`, and
  `sql body` islands.
- Semantic token coloring for declaration, context, action, and control verbs.
- Semantic roles for declared names, immutable values, mutable values, call
  objects, argument names, labels, effect paths, opaque inputs, generated
  targets, schema values, and role suffixes.
- Whole-line segment coloring for declaration, context, action, control,
  comment, and unknown lines.
- Context-aware hovers that explain the concrete line being hovered, including
  actual constant names, types, values, call targets, argument flow, control
  edges, cleanup edges, worker items, and same-file operation metadata.
- Identifier hovers resolve same-file symbols such as constants, storage slots,
  inputs, storage slots, call objects, labels, bindings, failures, fields,
  groups, collection declarations, and work items.
- Go to Definition for same-file SemanticScript symbols.
- Go to Definition for build-tape module registrations and project imports,
  including `registerModule ... "path"` rows and `import ... module.path`
  lookups resolved through the nearest `build.sem`.
- Outline/Breadcrumb support through document symbols for operations, routes,
  records, fields, capabilities, constants, storage, calls, labels, and key
  project declarations.
- Completion suggestions for verbs, primitive/native call targets, and same-file
  symbols, including `html.hydrate.TemplateName` targets declared by local
  `html template` rows.
- Same-file Rename Symbol support for declared SemanticScript symbols.
- Inlay hints for input, local binding, result binding, and call-target shape.
- Optional diagnostics from the canonical `semanticscript.py check --json`
  engine, plus quick fixes that open `semanticscript.py fix --plan` for the
  current file.
- `SemanticScript: Compile Current File` runs `semanticscript.py build` with a
  project directory when a nearest `build.sem` exists, or the current file
  otherwise.

## Refined Syntax Coverage

The extension recognizes the recent syntax families from the refined example:

- Sections and explicit storage:
  `section`, `storage`, `sharedState`, `read`, `set local`,
  `set module`, `set sharedState`.
- Program mode:
  `mode capturedOutputReplay`, `languageMode strictExecutable`, and
  `languageMode refinedSyntax`.
- Project metadata:
  `version`, `publisher`, `description`, `copyright`, `productName`,
  `internalName`, `originalFilename`, `trademark`, `comments`, and repeatable
  `metadata "key" "value"` rows used by executable VERSIONINFO emission.
- Operation contracts:
  `operationBody`, `runtimeBinding`, `runtimeBindingPrecondition`,
  `runtimeBindingFailure`, `intrinsicName`, `dependencyPath`,
  `dependencyFailure`, `precondition`, `pinsNullBodyFailurePath`,
  `responseBodyForwarder`, `rationale`, and explicit `return void` control flow.
- Native web server declarations:
  `webServer`, `serverHost`, `serverPort`, `route`, `routeNotFound`,
  `routeMethodNotAllowed`, `routeTimeout`,
  `routeMiddleware`, `routeTimeoutOptOut`, and `routeMiddlewareOptOut`.
- RuntimeBinding async hooks:
  `runtimeBindingAsyncStart` and `runtimeBindingAsyncAwait` for generic
  `start` / `await` lowering on runtime-bound operations.
- Native HTTP call targets:
  `http.requestMethod`, `http.requestPath`, `http.requestHeader`,
  `http.requestQueryParam`, `http.requestBodyText`, `http.requestBodyBytes`,
  `http.requestBodyLength`, `http.requestPathParam`, `http.requestCookie`,
  `http.responseHtml`, `http.responseText`, `http.responseBytes`,
  `http.responseFile`, `http.responseHeader`, `http.responseSseEvent`,
  `http.openSseStream`, `http.writeSseEvent`, `http.writeSseEventWithId`,
  `http.writeSseHeartbeat`, `http.closeSseStream`,
  `http.clientDisconnected`, `http.serverIsShuttingDown`,
  `http.clientGet`, `http.clientPost`, `http.escapeHtml`,
  `http.ensureDirectory`, `http.nowMillis`, and multipart helpers such as
  `http.multipartPartText`, `http.multipartPartBytes`,
  `http.multipartPartLength`, `http.multipartPartFilename`, and
  `http.multipartPartContentType`.
- Windows GUI target support:
  `target windowsGui`, `targetRuntime PROJECT windowsGui`, normal
  `entry console main`, `GuiSession`/`GuiEvent` handler inputs, and
  `standard.gui` `gui.*` call targets such as `gui.applicationCreate`,
  `gui.windowCreate`, `gui.buttonCreate`, `gui.controlOnEvent`,
  `gui.applicationRun`, `gui.textBoxText`, `gui.textLabelSetText`, and
  `gui.windowClose`.
- First-class HTML templates:
  `html template`, `html body template`, `String`, `HtmlFragment`,
  `HtmlTrustedFragment`, `HtmlDocument`, `HtmlSafeUrl`, embedded HTML/SSX
  highlighting, inferred bare or dotted hole hovers such as `{{titleText}}`
  and `{{profile.title}}`, and generated hydration targets such as
  `html.hydrate.TodoDashboardPageTemplate`.
- First-class SQL text islands:
  `sql body`, `sqlBody`, `SqlText`, placeholder highlighting, and storage-target
  hovers for SQL passed to `sqlite.prepareStatement` or `sqlite.exec`.
- Module/dependency build tape:
  `import ALIAS MODULE_PATH`, legacy `importModule`, singular imports such as
  `importOperation` and `importType`, plus `dependencyFetch`,
  `dependencyCache`, `dependencyLock`, `asyncRuntime`, `keepResources`,
  `resourcesDir`, `buildConstant`, `nativeRuntimeSource`, and
  `nativeRuntimeLinkArg`.
- Memory contracts:
  `memoryHeap`, `memoryArena`, `memoryAllocationSource`, `memoryStackLimit`.
- Trust and literals:
  `trustBoundary*`, `typeParameter`, `typeLiteralEncoding`,
  `typeLiteralTerminator`, `domainLiteral*`, `literal*`.
- Records and builders:
  `recordLayout`, `recordAlign`, `fieldDefault`, `fieldInvariant`,
  `recordFieldJsonName`, `recordFieldJsonOmitWhen`,
  `recordBuilder`, `recordSet`, `recordCopy`, `recordBuild`,
  `recordBuildFailure`, `recordConstructor*`, `fieldGet`, `fieldSet`.
- Collections and aggregates:
  `listType`, `arrayType`, `sliceType`, `smallListType`, `mapType`,
  `listLiteral*`, `collectionOperation*`, and typed collection methods such as
  `TaskList.length`, `TaskList.append`, `TaskList.get`, and `TaskMap.insert`.
- Codecs:
  `jsonCodec*`, legacy `json.encode.*` / `json.decode.*`, high-level
  `json.parse.Task` / `json.stringify.AccountBalanceResponse`, and native JSON
  builder/document CRUD targets such as `json.createDocument`,
  `json.cursorAtPath`, `json.setObjectFieldString`, and
  `json.removeArrayElementAt`.
- Standard native targets:
  `net.fetchText`, `net.fetchBytes`, `net.freeTextBody`, expanded SQLite targets
  including `sqlite.finalizeStatement`, `sqlite.resetStatement`,
  `sqlite.columnBlob`, `sqlite.columnByteCount`, `sqlite.execStatus`, JWT
  helpers such as `jwt.hs256VerifyToken` and
  `jwt.formatBearerLoginEnvelope`, and standard exported type/value
  surfaces for `standard.gui`, `standard.json`, `standard.sqlite`,
  `standard.net`, and `standard.bcrypt`.
- Groups, guards, and defers:
  `group*`, `guardToken*`, `deferLog`, `deferLogSink`, `deferRunOn`,
  `deferOrder`, `deferFailurePolicy`, `deferConsumes`, and async defer forms.
- Intervals and worker pools:
  `interval`, `startInterval`, `awaitIntervalTick`, `workerPool`, `work`,
  `workArg`, `submitWork`, and `awaitWork`.

Unknown verbs remain visually distinct through the unknown-line segment color so
syntax drift is easy to spot.

## Schema Values

Fixed schema values are highlighted and hovered as schema tokens rather than
ordinary variables. Examples include:

```text
yes no
strictExecutable refinedSyntax
permissiveExecutable library none libuv
local module process sharedState
immutable mutable
win32 winui3 x86_64_v1 on off
sourceTape runtimeBinding recordConstructor intrinsic externalDependency
success error
decode encode reject ignore keep none
utf8 nullByte sha256 maximumBytes
empty null zero
validatedRuntimeValue trustedStaticLiteral trustedUtf8Literal
rawPointerToValidatedCString rawUtf8ToValidatedText
row immutableUpdate borrowedView
zeroBasedChecked zeroBasedCheckedRange contiguousUniqueAscending
arena.request arena.process arena.static
return value ok error void reverseRegistration logAndSuppress
protectedBy ownedBy
continueMiddlewareControl shortCircuitMiddlewareControl
inMemorySqliteOpenMode readWriteCreateSqliteOpenMode
rowSqliteStepResult doneSqliteStepResult objectJsonValueKind arrayJsonValueKind
defaultGuiWindowLayout clickGuiEventKind okGuiRuntimeStatus
```

Role suffix highlighting is intentionally limited to real user symbols. Fixed
schema values and opaque dependency names are kept atomic, so words like
`sharedState`, `return error`, and `metricsLock` are not split into misleading
suffix fragments.

## Linting

Linting uses the structured diagnostics from
`../SemanticScript/semanticscript/compiler/semanticscript.py check --json`. The
extension auto-discovers the compiler from the workspace root, the
`SemanticScript` folder, or ancestors of the open `.sscript`/`.sem` file. Set
`semanticScript.linter.path` if your checkout layout is different.

`semanticScript.linter.skipFutureSyntax` defaults to `false`. When enabled, it
skips linter diagnostics on refinement-only files that are not executable by the
current compiler yet.

## Compiling

`SemanticScript: Compile Current File` runs the current file or nearest
`build.sem` project through `semanticscript.py build`. The extension
auto-discovers the compiler from common repo layouts:

```text
SemanticScript/semanticscript/compiler/semanticscript.py
semanticscript/compiler/semanticscript.py
../SemanticScript/semanticscript/compiler/semanticscript.py
```

Set `semanticScript.compiler.path` for custom layouts. The emitted executable is
placed in a `build/` directory beside the source file unless
`semanticScript.compiler.outputDirectory` is set.

## Commands

- `SemanticScript: Toggle Segment Colors`
- `SemanticScript: Run Linter`
- `SemanticScript: Run Fix Plan`
- `SemanticScript: Compile Current File`

## Run Locally

Open this folder in VS Code:

```text
vscode-semanticscript
```

Press `F5` to launch an Extension Development Host, then open a SemanticScript
file such as:

```text
../SemanticScript/sem/refined_syntax_demo.sscript
```

or a current executable file such as:

```text
../SemanticScript/sem/countdown.sscript
```

To check the bundled file icon theme in the Extension Development Host, run
`Preferences: File Icon Theme` and choose `SemanticScript Icons`.

## Install Locally

From this repository root, install the packaged VSIX or use the extension folder
directly in your local VS Code extensions directory:

```text
%USERPROFILE%\.vscode\extensions\semanticscript-vscode
```

Then reload VS Code.

## Settings

```json
{
  "semanticScript.segmentColors.enabled": true,
  "semanticScript.segmentColors.colorMode": "background",
  "semanticScript.linter.enabled": true,
  "semanticScript.linter.run": "onSave",
  "semanticScript.linter.pythonPath": "python",
  "semanticScript.linter.path": "",
  "semanticScript.compiler.pythonPath": "python",
  "semanticScript.compiler.path": "",
  "semanticScript.compiler.outputDirectory": "",
  "semanticScript.semanticHighlighting.enabled": false
}
```

`semanticScript.segmentColors.colorMode` can be `background`, `overview`, or
`both`.

`semanticScript.linter.run` can be `onSave`, `onType`, or `manual`.

When a `.sem` file is inside a project, compile and lint commands use the
nearest `build.sem` as the project root.
