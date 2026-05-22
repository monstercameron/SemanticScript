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

Active editor tooling. Version `1.0.4` supports highlighting, semantic tokens,
hovers, same-file navigation, completions, lint integration, and direct
`semsc.py` executable builds from VS Code. The package also includes a
SemanticScript gallery icon, language file icon fallback, and selectable
SemanticScript file icon theme.

## Release Readiness

The package is 1.0 local-release oriented. Before a public Marketplace release,
the release owner must decide:

- the real Marketplace `publisher` value to replace `semanticscript-local`.

The extension package is licensed as MIT, matching the root repository license.
Run `npm run check` before packaging. Use `npm run package:vsix` for local VSIX
builds after accepting the publisher metadata constraint for the target release.

## Features

- Language registration for `.sscript` and `.sem`.
- VS Code extension gallery icon and SemanticScript file icons for `.sscript`,
  `.sem`, `build.sscript`, and `build.sem`.
- TextMate highlighting for verbs, types, strings, numbers, comments, symbols,
  qualified paths, error variants, schema values, primitive targets, generated
  targets, domain targets, and embedded `html body template` markup islands.
- Semantic token coloring for declaration, context, action, and control verbs.
- Semantic roles for declared names, immutable values, mutable values, call
  objects, argument names, labels, effect paths, opaque inputs, generated
  targets, schema values, and role suffixes.
- Whole-line segment coloring for declaration, context, action, control,
  comment, and unknown lines.
- Context-aware hovers that explain the concrete line being hovered, including
  actual constant names, types, values, call targets, argument flow, control
  edges, cleanup edges, worker items, and same-file operation metadata.
- Identifier hovers resolve same-file symbols such as constants, variables,
  inputs, storage slots, call objects, labels, bindings, failures, fields,
  groups, collection declarations, and work items.
- Go to Definition for same-file SemanticScript symbols.
- Outline/Breadcrumb support through document symbols for operations, routes,
  records, fields, capabilities, constants, storage, calls, labels, and key
  project declarations.
- Completion suggestions for verbs, primitive/native call targets, and same-file
  symbols, including `html.hydrate.TemplateName` targets declared by local
  `html template` rows.
- Optional diagnostics from the canonical `semlint.py` engine.
- `SemanticScript: Compile Current File` runs `semsc.py --emit-exe` with
  configurable build profile, runtime checks, and LLVM IR persistence.

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
  `responseBodyForwarder`, `rationale`, and explicit `returnVoid` control flow.
- Native web server declarations:
  `webServer`, `serverHost`, `serverPort`, `route`, `routeTimeout`,
  `routeMiddleware`, `routeTimeoutOptOut`, and `routeMiddlewareOptOut`.
- Native HTTP call targets:
  `http.requestMethod`, `http.requestPath`, `http.requestHeader`,
  `http.requestQueryParam`, `http.requestBodyText`, `http.requestBodyBytes`,
  `http.requestBodyLength`, `http.responseText`, `http.responseBytes`,
  `http.responseHeader`, `http.responseSseEvent`, and multipart helpers such as
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
  `html template`, optional `html parameter template`, `html body template`,
  `String`, `HtmlFragment`, `HtmlTrustedFragment`, `HtmlDocument`, embedded
  HTML/SSX highlighting, bare or dotted hole hovers such as `{titleText}` and
  `{profile.title}`, and generated hydration targets such as
  `html.hydrate.TodoDashboardPageTemplate`.
- Module/dependency build tape:
  `import ALIAS MODULE_PATH`, legacy `importModule`, singular imports such as
  `importOperation` and `importType`, plus `dependencyFetch`,
  `dependencyCache`, and `dependencyLock`.
- Memory contracts:
  `memoryHeap`, `memoryArena`, `memoryAllocationSource`, `memoryStackLimit`.
- Trust and literals:
  `trustBoundary*`, `typeParameter`, `typeLiteralEncoding`,
  `typeLiteralTerminator`, `domainLiteral*`, `literal*`.
- Records and builders:
  `recordLayout`, `recordAlign`, `fieldDefault`, `fieldInvariant`,
  `recordBuilder`, `recordSet`, `recordCopy`, `recordBuild`,
  `recordBuildFailure`, `recordConstructor*`, `fieldGet`, `fieldSet`.
- Collections and aggregates:
  `listType`, `arrayType`, `sliceType`, `smallListType`, `mapType`,
  `listLiteral*`, `collectionOperation*`, and typed collection methods such as
  `TaskList.length`, `TaskList.append`, `TaskList.get`, and `TaskMap.insert`.
- Codecs:
  `jsonCodec*`, plus generated targets such as `json.parse.Task` and
  `json.stringify.AccountBalanceResponse`.
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
local module process sharedState
immutable mutable
sourceTape runtimeBinding recordConstructor intrinsic externalDependency
success error
decode encode reject ignore keep none
utf8 nullByte sha256 maximumBytes
validatedRuntimeValue trustedStaticLiteral trustedUtf8Literal
rawPointerToValidatedCString rawUtf8ToValidatedText
row immutableUpdate borrowedView
zeroBasedChecked zeroBasedCheckedRange contiguousUniqueAscending
arena.request arena.process arena.static
returnOk returnError reverseRegistration logAndSuppress
protectedBy ownedBy
continueMiddlewareControl shortCircuitMiddlewareControl
inMemorySqliteOpenMode readWriteCreateSqliteOpenMode
```

Role suffix highlighting is intentionally limited to real user symbols. Fixed
schema values and opaque dependency names are kept atomic, so words like
`sharedState`, `returnError`, and `metricsLock` are not split into misleading
suffix fragments.

## Linting

Linting uses the structured diagnostics from
`../SemanticScript/linter/semlint.py`. The extension
auto-discovers the selected linter from the workspace root, the `SemanticScript`
folder, or ancestors of the open `.sscript` file. Set `semanticScript.linter.path` if
your checkout layout is different.

`semanticScript.linter.skipFutureSyntax` defaults to `false`. When enabled, it
skips linter diagnostics on refinement-only files that are not executable by the
current compiler yet.

## Compiling

`SemanticScript: Compile Current File` runs the current file through `semsc.py`
with `--emit-exe`. The extension auto-discovers the compiler from common repo
layouts:

```text
SemanticScript/compiler/semsc.py
compiler/semsc.py
../SemanticScript/compiler/semsc.py
```

Set `semanticScript.compiler.path` for custom layouts. The emitted executable is
placed in a `build/` directory beside the source file unless
`semanticScript.compiler.outputDirectory` is set. When compiling `build.sem`,
the extension lets `semsc.py` choose the compiler-managed output path from the
build tape.

## Commands

- `SemanticScript: Toggle Segment Colors`
- `SemanticScript: Run Linter`
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
  "semanticScript.linter.engine": "semlint",
  "semanticScript.linter.run": "onSave",
  "semanticScript.linter.pythonPath": "python",
  "semanticScript.linter.path": "",
  "semanticScript.linter.skipFutureSyntax": false,
  "semanticScript.compiler.pythonPath": "python",
  "semanticScript.compiler.path": "",
  "semanticScript.compiler.outputDirectory": "",
  "semanticScript.compiler.buildProfile": "dev",
  "semanticScript.compiler.runtimeChecks": "default",
  "semanticScript.compiler.persistLlvmIr": "auto",
  "semanticScript.compiler.optLevel": "default",
  "semanticScript.compiler.emitLlvmIr": false,
  "semanticScript.compiler.buildDir": "",
  "semanticScript.compiler.buildRoot": "",
  "semanticScript.compiler.buildFolderName": "",
  "semanticScript.compiler.cpuBaseline": "default",
  "semanticScript.compiler.cpuTune": "",
  "semanticScript.compiler.cpuFeatureCheck": "default"
}
```

`semanticScript.segmentColors.colorMode` can be `background`, `overview`, or
`both`.

`semanticScript.linter.engine` currently accepts `semlint`.

`semanticScript.linter.run` can be `onSave`, `onType`, or `manual`.

`semanticScript.compiler.buildProfile` can be `dev` or `prod`.

`semanticScript.compiler.runtimeChecks` can be `default`, `off`, `traps`, or
`panic`.

`semanticScript.compiler.persistLlvmIr` can be `auto`, `yes`, or `no`.

`semanticScript.compiler.optLevel` can be `default`, `0`, `1`, `2`, or `3`.

`semanticScript.compiler.cpuBaseline` can be `default`, `generic`, `native`,
`x86_64_v1`, `x86_64_v2`, `x86_64_v3`, `x86_64_v4`, `arm64_generic`, or
`arm64_v8_2`.

`semanticScript.compiler.cpuTune` passes a non-empty value through to
`--cpu-tune`.

`semanticScript.compiler.cpuFeatureCheck` can be `default`, `auto`, `off`,
`warn`, or `require`.

When a `.sem` file is inside a project, compile and lint commands use the
nearest `build.sem` as the project root. `buildDir`, `buildRoot`, and
`buildFolderName` pass through the matching compiler artifact-directory flags.
CPU settings pass through the matching compiler CPU flags.
