# SemanticScript VS Code Extension

Local VS Code extension for SemanticScript `.sscript` and `.sem` files.

This extension is editor tooling. It recognizes both the current executable
SemanticScript surface and the refined future syntax used in
`../SemanticScript/sem/refined_syntax_demo.sscript`. The refined syntax support is for
highlighting, hovers, semantic roles, and drift detection; it does not make the
current compiler accept those future forms.

## Features

- Language registration for `.sscript` and `.sem`.
- TextMate highlighting for verbs, types, strings, numbers, comments, symbols,
  qualified paths, error variants, schema values, primitive targets, generated
  targets, and domain targets.
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
- Optional diagnostics from `semlint.py`, with current-linter diagnostics skipped
  by default for refined future syntax files.
- Optional structured diagnostics from `semlint2.py` via
  `semanticScript.linter.engine`.

## Refined Syntax Coverage

The extension recognizes the recent syntax families from the refined example:

- Sections and explicit storage:
  `section`, `storage`, `sharedState`, `read`, `set local`,
  `set module`, `set sharedState`.
- Program mode:
  `mode capturedOutputReplay`.
- Operation contracts:
  `operationBody`, `runtimeBinding`, `runtimeBindingPrecondition`,
  `runtimeBindingFailure`, `intrinsicName`, `dependencyPath`,
  `dependencyFailure`.
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
  `jsonCodec*`, plus generated targets such as `json.decode.Task` and
  `json.encode.AccountBalanceResponse`.
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
```

Role suffix highlighting is intentionally limited to real user symbols. Fixed
schema values and opaque dependency names are kept atomic, so words like
`sharedState`, `returnError`, and `metricsLock` are not split into misleading
suffix fragments.

## Linting

Linting uses `../SemanticScript/linter/semlint.py` by default. Set
`semanticScript.linter.engine` to `semlint2` to use the structured refinement
diagnostics from `../SemanticScript/linter/semlint2.py`. The extension
auto-discovers the selected linter from the workspace root, the `SemanticScript`
folder, or ancestors of the open `.sscript` file. Set `semanticScript.linter.path` if
your checkout layout is different.

Files using the refined future syntax are skipped by the current linter by
default because that syntax is a mock/spec showcase and is not current
executable SemanticScript. Turn off `semanticScript.linter.skipFutureSyntax` if you
want to force current `semlint.py` diagnostics anyway.

## Commands

- `SemanticScript: Toggle Segment Colors`
- `SemanticScript: Run Linter`

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
  "semanticScript.linter.skipFutureSyntax": true
}
```

`semanticScript.segmentColors.colorMode` can be `background`, `overview`, or
`both`.

`semanticScript.linter.engine` can be `semlint` or `semlint2`.

`semanticScript.linter.run` can be `onSave`, `onType`, or `manual`.
