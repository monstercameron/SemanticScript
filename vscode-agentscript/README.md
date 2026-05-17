# AgentScript VS Code Extension

Local VS Code extension for AgentScript `.as` and `.agentscript` files.

This extension is editor tooling. It recognizes both the current executable
AgentScript surface and the refined future syntax used in
`../experiments/refined_syntax_example.as`. The refined syntax support is for
highlighting, hovers, semantic roles, and drift detection; it does not make the
current compiler accept those future forms.

## Features

- Language registration for `.as` and `.agentscript`.
- TextMate highlighting for verbs, types, strings, numbers, comments, symbols,
  qualified paths, error variants, schema values, primitive targets, generated
  targets, and domain targets.
- Semantic token coloring for declaration, context, action, and control verbs.
- Semantic roles for declared names, immutable values, mutable values, call
  objects, argument names, labels, effect paths, opaque inputs, generated
  targets, schema values, and role suffixes.
- Whole-line segment coloring for declaration, context, action, control,
  comment, and unknown lines.
- Hovers for AgentScript verbs, refined syntax verbs, primitive targets,
  generated codec targets, domain methods, primitive types, opaque inputs,
  schema values, role suffixes, and call objects.
- Optional diagnostics from `aslint.py`, with current-linter diagnostics skipped
  by default for refined future syntax files.

## Refined Syntax Coverage

The extension recognizes the recent syntax families from the refined example:

- Sections and explicit storage:
  `section`, `storage`, `sharedState`, `read`, `set local`,
  `set module`, `set sharedState`.
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

Linting uses `../AgentScript/linter/aslint.py`. The extension auto-discovers the
linter from the workspace root, the `AgentScript` folder, or ancestors of the
open `.as` file. Set `agentScript.linter.path` if your checkout layout is
different.

Files using the refined future syntax are skipped by the current linter by
default because that syntax is a mock/spec showcase and is not current
executable AgentScript. Turn off `agentScript.linter.skipFutureSyntax` if you
want to force current `aslint.py` diagnostics anyway.

## Commands

- `AgentScript: Toggle Segment Colors`
- `AgentScript: Run Linter`

## Run Locally

Open this folder in VS Code:

```text
vscode-agentscript
```

Press `F5` to launch an Extension Development Host, then open an AgentScript
file such as:

```text
../experiments/refined_syntax_example.as
```

or a current executable file such as:

```text
../AgentScript/as/countdown.as
```

## Install Locally

From this repository root, install the packaged VSIX or use the extension folder
directly in your local VS Code extensions directory:

```text
%USERPROFILE%\.vscode\extensions\agentscript-vscode
```

Then reload VS Code.

## Settings

```json
{
  "agentScript.segmentColors.enabled": true,
  "agentScript.segmentColors.colorMode": "background",
  "agentScript.linter.enabled": true,
  "agentScript.linter.run": "onSave",
  "agentScript.linter.pythonPath": "python",
  "agentScript.linter.path": "",
  "agentScript.linter.skipFutureSyntax": true
}
```

`agentScript.segmentColors.colorMode` can be `background`, `overview`, or
`both`.

`agentScript.linter.run` can be `onSave`, `onType`, or `manual`.
