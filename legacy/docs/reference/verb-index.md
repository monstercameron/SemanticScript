# Verb Index

This is a grouped index, not the exhaustive status table. Use `syntax-inventory.md` for
the row-by-row implementation inventory. Keep this file stable and readable:
add verbs to the family that owns their semantics.

Status labels used below:

```text
lowered       affects current LLVM/codegen output
metadata      parsed/indexed; no direct current runtime behavior
sync-fallback syntax has runtime meaning but current backend collapses it
partial       mixed behavior; see owning language doc
```

## Project and File Structure

| Verb | Schema | Status |
|---|---|---|
| `project` | `project NAME` | metadata |
| `target` | `target NAME` | partial |
| `runtime` | `runtime NAME VERSION` | metadata |
| `module` | `module DOTTED.PATH` | metadata |
| `mode` | `mode capturedOutputReplay` | metadata |
| `entry` | `entry console OPERATION` | lowered |
| `buildProject` | `buildProject PROJECT` | partial |
| `modulePath` | `modulePath PROJECT MODULE_PATH` | metadata |
| `languageVersion` | `languageVersion PROJECT "VERSION"` | metadata |
| `projectVersion` | `projectVersion PROJECT "VERSION"` | metadata |
| `projectLicense` | `projectLicense PROJECT LICENSE` | metadata |
| `sourceRoot` | `sourceRoot PROJECT "PATH"` | partial |
| `registerModule` | `registerModule PROJECT MODULE_PATH "PATH"` | partial |
| `mainFile` | `mainFile PROJECT "PATH"` | partial |
| `mainOperation` | `mainOperation PROJECT OPERATION` | partial |
| `testRoot` | `testRoot PROJECT "PATH"` | metadata |
| `testPattern` | `testPattern PROJECT "GLOB"` | metadata |
| `targetRuntime` | `targetRuntime PROJECT nativeExe\|webServer\|windowsGui\|library` | partial |
| `guiBackend` | `guiBackend PROJECT win32\|winui3` | partial |
| `buildProfile` | `buildProfile PROJECT dev|prod` | partial |
| `asyncRuntime` | `asyncRuntime PROJECT none|libuv` | partial |
| `runtimeChecks` | `runtimeChecks PROJECT off|traps|panic` | partial |
| `optLevel` | `optLevel PROJECT 0|1|2|3` | partial |
| `persistLlvmIr` | `persistLlvmIr PROJECT auto|yes|no` | partial |
| `emitLlvmIr` | `emitLlvmIr PROJECT auto|yes|no` | partial |
| `llvmIrOutput` | `llvmIrOutput PROJECT "PATH"` | partial |
| `emitOptimizedLlvmIr` | `emitOptimizedLlvmIr PROJECT yes|no` | partial |
| `optimizedLlvmIrOutput` | `optimizedLlvmIrOutput PROJECT "PATH"` | partial |
| `buildDir` | `buildDir PROJECT "PATH"` | partial |
| `buildRoot` | `buildRoot PROJECT "PATH"` | partial |
| `buildFolderName` | `buildFolderName PROJECT NAME` | partial |
| `cpuBaseline` | `cpuBaseline PROJECT generic|native|x86_64_v2|...` | partial |
| `cpuTune` | `cpuTune PROJECT generic|native|CPU_NAME` | partial |
| `cpuFeature` | `cpuFeature PROJECT FEATURE on|off` | partial |
| `cpuFeatureCheck` | `cpuFeatureCheck PROJECT auto|off|warn|require` | partial |
| `dependency` | `dependency PROJECT ALIAS MODULE_PATH VERSION_OR_REF` | implemented |
| `dependencySource` | `dependencySource PROJECT ALIAS [local|path|github|http] SOURCE [REF]` | implemented |
| `dependencyFetch` | `dependencyFetch PROJECT ALIAS github OWNER/REPO REF` or `dependencyFetch PROJECT ALIAS http "https://..."` | implemented |
| `dependencyCache` | `dependencyCache PROJECT "PATH"` | implemented |
| `dependencyLock` | `dependencyLock PROJECT "PATH"` | implemented |
| `dependencyIntegrity` | `dependencyIntegrity PROJECT ALIAS sha256:<64-hex>|commit:<7-40-hex>` | implemented |
| `nativeOutput` | `nativeOutput PROJECT "PATH"` | partial |
| `nativeHttpHost` | `nativeHttpHost PROJECT "HOST"` | metadata |
| `nativeHttpPort` | `nativeHttpPort PROJECT PORT` | metadata |
| `formatterSetting` | `formatterSetting PROJECT KEY VALUE` | metadata |
| `linterSetting` | `linterSetting PROJECT KEY VALUE` | metadata |
| `docsOutput` | `docsOutput PROJECT "PATH"` | metadata |
| `buildConstant` | `buildConstant PROJECT NAME TYPE VALUE` | lowered |
| `nativeRuntimeSource` | `nativeRuntimeSource MODULE "PATH"` | lowered |
| `nativeRuntimeLinkArg` | `nativeRuntimeLinkArg MODULE [any\|windows\|posix] "ARG"` | lowered |
| `import` | `import ALIAS DOTTED.PATH` | lowered pre-parse |
| `importOperation` | `importOperation LOCAL_NAME MODULE_ALIAS EXPORTED_OPERATION` | partial |
| `importType` | `importType LOCAL_NAME MODULE_ALIAS EXPORTED_TYPE` | partial |
| `importError` | `importError LOCAL_NAME MODULE_ALIAS EXPORTED_ERROR` | partial |
| `importCapability` | `importCapability LOCAL_NAME MODULE_ALIAS EXPORTED_CAPABILITY` | partial |
| `importConstant` | `importConstant LOCAL_NAME MODULE_ALIAS EXPORTED_CONSTANT` | partial |
| `section` | `section NAME` | metadata |

Module export rows are module-local metadata: `exportType`, `exportError`,
`exportOperation`, `exportCapability`, and `exportConstant`.

## Types, Records, Enums

| Family | Verbs |
|---|---|
| Type aliases | `type`, `typeParameter` |
| Type metadata | `typeInvariant`, `typeRepresentation`, `typeTrust`, `typeMemory`, `typeLayout`, `typeLiteralEncoding`, `typeLiteralTerminator` |
| Records | `record`, `field`, `recordLayout`, `recordAlign`, `new`, `fieldSet`, `fieldGet` |
| Record builders | `recordConstructor`, `recordConstructorFailure`, `recordBuilder`, `recordSet`, `recordBuild`, `recordBuildFailure` |
| Enums | `enum`, `enumCase` |

## Operations

| Verb | Schema | Status |
|---|---|---|
| `operation` | `operation NAME` | lowered |
| `operationBody` | `operationBody OP KIND` | partial |
| `input` | `input operation OP NAME TYPE` | lowered |
| `output` | `output operation OP TYPE...` | lowered |
| `effect` | `effect OP ACTION PATH` | checked metadata |
| `memory` | `memory OP POLICY...` | checked metadata |
| `async` | `async OP yes/no` | checked metadata |
| `purpose` | `purpose operation OP "text"` | checked metadata |
| `invariant` | `invariant operation OP "text"` | checked metadata |
| `warning` | `warning OP "text"` | checked metadata |
| `guarantee` | `guarantee TARGET "text"` | metadata |
| `failure` | `failure TARGET NAME "text"` | metadata |
| `security` | `security TARGET "text"` | metadata |
| `timing` | `timing TARGET "text"` | metadata |
| `observability` | `observability TARGET "text"` | metadata |

## Values and State

| Verb | Schema | Status |
|---|---|---|
| `storage` | `storage SCOPE MUTABILITY NAME TYPE [VALUE]` | lowered |
| `sharedState` | `sharedState SCOPE MUTABILITY NAME TYPE [INITIAL]` | lowered |
| `set` | `set SCOPE NAME VALUE ...` | lowered |
| `read` | `read sharedState OUT TYPE BACKING ...` | lowered |
| `domainLiteral` | `domainLiteral NAME TYPE VALUE` | lowered as immutable domain value |
| `literal` | `literal NAME TYPE` | lowered as external immutable literal stub |

Metadata families:

```text
sharedStateOwner sharedStateGuard
domainLiteralSource domainLiteralTrust domainLiteralValidation
literalBytes literalDigest literalPreview literalSource literalTrust
```

## Calls and Control Flow

| Family | Verbs |
|---|---|
| Calls | `call`, `argument`, `timeout`, `cancelOn`, `run`, `runChecked`, `start`, `await`, `case`, `done` |
| Binding | `bind value`, `bind ok`, `bind error`, `ignore ok`, `ignore value`, `ignore void` |
| Errors | `makeError`, `declareFailure`, `error`, `errorCase` |
| Labels | `label`, `jump`, `branch if`, `branch error`, `branch else` |
| Returns | `return ok`, `return error`, `return value`, `return void` |

## Effects, Capabilities, Resources

```text
dependency dependencyEffect dependencyExports
dependencyFunction dependencyFunctionInput dependencyFunctionOutput
dependencyFunctionEffect dependencyFunctionAsync dependencyPath dependencyFailure
capability useCapability authority
resource resourceKey resourceValue resourceKind
```

Most of these are metadata in current codegen and first-class input for
linters.

## Codecs and Boundaries

```text
codec schema unknownFields
jsonCodec jsonCodecStrict jsonCodecUnknownFields jsonCodecInput jsonCodecOutput
jsonCodecDecodeTarget jsonCodecEncodeTarget jsonCodecRequiredField
jsonCodecDecodeFailure jsonCodecEncodeFailure jsonCodecLimit
validator mapper adapter boundary
trustBoundary trustBoundaryKind trustBoundaryInput trustBoundaryOutput
trustBoundaryValidator trustBoundarySource
```

Primitive JSON generated targets have some lowering support. Record-level codec
contracts are primarily metadata today.

## JSON

Import `standard.json` with the canonical `json` alias before using the public
JSON surface:

```text
import json standard.json
```

Implemented builder/finder calls remain available while the document CRUD API
lands. Rows marked `proposed` are the public contract shape but do not have
current parser/runtime lowering; rows marked `partial` have some parser or
primitive-alias behavior but not the full intended surface. See `syntax-inventory.md` for
the row-level implementation status before relying on them in executable code.

| Verb | Schema | Status |
|---|---|---|
| `json.createBuilder` | `call NAME json.createBuilder` with `capacityBytes` | lowered |
| `json.destroyBuilder` | `call NAME json.destroyBuilder` with `builder` | lowered |
| `json.objectOpen`, `json.objectClose`, `json.arrayOpen`, `json.arrayClose` | `call NAME json.<target>` with `builder` | lowered |
| `json.fieldInt64`, `json.fieldDouble`, `json.fieldBool`, `json.fieldString`, `json.fieldNull` | `call NAME json.field*` with `builder`, `fieldName`, and value args where needed | lowered |
| `json.elementInt64`, `json.elementDouble`, `json.elementBool`, `json.elementString`, `json.elementNull` | `call NAME json.element*` with `builder` and value args where needed | lowered |
| `json.finishBuilder`, `json.builderLength` | `call NAME json.<target>` with `builder` | lowered |
| `json.hasField`, `json.findString`, `json.findInt64`, `json.findDouble`, `json.findBool` | `call NAME json.<target>` with `jsonText`, `fieldName`, and scratch/default args where needed | lowered |
| `json.createDocument`, `json.createEmptyDocument`, `json.destroyDocument` | Document lifecycle over `JsonDocument` handles and caller-supplied capacity | lowered |
| `json.serializeDocument`, `json.documentLength`, `json.documentRoot` | Document serialization, size query, and root cursor access | lowered |
| `json.objectFieldAt`, `json.arrayElementAt`, `json.cursorParent`, `json.cursorAtPath` | Navigation returning `Result JsonCursor JsonAccessError` | lowered |
| `json.cursorKind`, `json.cursorIsNull`, `json.cursorInt64`, `json.cursorDouble`, `json.cursorBool`, `json.cursorString`, `json.cursorArrayLength`, `json.cursorObjectFieldCount`, `json.cursorObjectFieldNameAt`, `json.cursorObjectFieldValueAt` | Cursor readers over one `JsonDocument` and `JsonCursor` | lowered |
| `json.setObjectFieldString`, `json.setObjectFieldInt64`, `json.setObjectFieldDouble`, `json.setObjectFieldBool`, `json.setObjectFieldNull`, `json.setObjectFieldObject`, `json.setObjectFieldArray`, `json.setObjectFieldJsonText` | Object field mutators with `JsonAccessError` status on failure | lowered |
| `json.appendArrayElement*`, `json.insertArrayElement*`, `json.replaceArrayElement*` | Array mutators for scalar, container, and raw JSON text values | lowered |
| `json.removeObjectField`, `json.removeArrayElementAt`, `json.clearObject`, `json.clearArray` | Delete and clear calls that preserve the owning document handle | lowered |
| `json.stringify.<TypeName>`, `json.parse.<TypeName>` | Typed high-level JSON entry points for primitives and generated record codecs | partial |
| `jsonBody` | `jsonBody NAME` followed by an indented JSON island bound to matching storage | partial |

## SQL

SQL surface:

| Verb | Purpose | Status |
|---|---|---|
| `sql body` / `sqlBody` | `sql body NAME` followed by an indented SQL island bound to `storage module immutable NAME SqlText` | lowered |

`sql body` preserves SQL as source text while keeping dynamic values out of the
literal. Use `?` placeholders and explicit `sqlite.bind*` rows; strict checks
reject multi-statement `sqlite.prepareStatement` inputs and placeholder-bearing
`sqlite.exec` inputs.

## HTML Templates

Standard-library modules are imported through the `standard.*` namespace. The
compiler resolves them through the std search path; the library root contains
`module.sem`, and each child module lives at `<module>/main.sem`.

Import `standard.html` with the canonical `html` alias before using this
surface in app modules:

```text
import html standard.html
```

| Verb | Schema | Status |
|---|---|---|
| `html template` | `html template NAME` | lowered |
| `html body template` | `html body template TEMPLATE` followed by indented HTML/SSX lines | lowered |

`html.hydrate.TemplateName` is a generated call target, not a standalone verb.
It is exposed through the imported `standard.html` namespace and assembles the
template body with `argument` rows whose names match inferred hole roots.
Dynamic holes are bare names or dotted record-field paths, written only as
`{{name}}` or `{{record.field}}`. The old `{name}` form is a hard error with
guidance to use `{{name}}`. Single braces in JavaScript, CSS, and object
literals remain literal unless they are exactly old hole syntax; raw
`<style>`/`<script>` text still rejects actual dynamic holes. Hydration escapes
`String` in text and non-URL quoted attribute sinks. URL-bearing attributes
(`href`, `src`, `action`, `formaction`, and `poster`) require `HtmlSafeUrl`;
plain `String` is rejected there. `HtmlFragment` / `HtmlTrustedFragment` /
`HtmlDocument` values can only hydrate text-content positions where raw markup
is intentional.

## Native Windows GUI

`target windowsGui` and `targetRuntime PROJECT windowsGui` are the
compiler/build bridge. `guiBackend PROJECT win32|winui3` selects the native
adapter; `win32` is the default and `winui3` is currently a recognized-but-blocked
Windows App SDK scaffold. GUI source uses normal `entry console OPERATION`,
`operation`, `call`, `argument`, and `run` rows. The larger GUI vocabulary belongs
to `standard.gui` as function targets, contracts, capabilities, and validation
rules. The compiler should only lower explicit `gui.*` calls and link/start the
selected native GUI runtime. Do not use C# / XAML sidecar apps as a substitute
for `guiBackend winui3`. There is no `entry windowsGui` row. The preferred
standard-library import is:

```text
import gui standard.gui
```

Legacy `importModule` rows are rejected by the compiler; use the alias-first
`import` form above.
Top-level row-centric GUI declarations such as `guiApplication`, `guiWindow`,
and `guiButton` are historical design notes, not committed executable verbs.

| Verb | Schema | Status |
|---|---|---|
| `gui.applicationCreate` | `call NAME gui.applicationCreate` with `title` | lowered |
| `gui.windowCreate` | `call NAME gui.windowCreate` with `title`, `width`, `height`, `layout`, `resizable` | lowered |
| `gui.textLabelCreate` | `call NAME gui.textLabelCreate` with `text` | lowered |
| `gui.textBoxCreate` | `call NAME gui.textBoxCreate` with `placeholder`, `maxLength` | lowered |
| `gui.buttonCreate` | `call NAME gui.buttonCreate` with `text`, `isDefault` | lowered |
| `gui.listBoxCreate` | `call NAME gui.listBoxCreate` with `selectionMode` | lowered |
| `gui.windowAddControl` | `call NAME gui.windowAddControl` with `window`, `control` | lowered |
| `gui.controlOnEvent` | `call NAME gui.controlOnEvent` with `control`, `eventKind`, `handler` | lowered |
| `gui.applicationSetMainWindow` | `call NAME gui.applicationSetMainWindow` with `application`, `window` | lowered |
| `gui.applicationRun` | `call NAME gui.applicationRun` with `application` | lowered |

GUI handler operations use:

```text
input operation HANDLER session GuiSession
input operation HANDLER event GuiEvent
output operation HANDLER Int32
```

Reserved GUI opaque types are `GuiApplication`, `GuiSession`, `GuiEvent`,
`GuiWindow`, `GuiControl`, `GuiButton`, `GuiTextBox`, `GuiListBox`,
`GuiCheckBox`, `GuiMenuItem`, `GuiStatusBar`, and `GuiTextLabel`. Reserved
enum/closed-token types are `GuiWindowLayout`, `GuiListBoxSelectionMode`, and
`GuiEventKind`.

Reserved `gui.*` runtime call targets:

```text
gui.applicationCreate
gui.windowCreate
gui.textLabelCreate
gui.textBoxCreate
gui.buttonCreate
gui.listBoxCreate
gui.windowAddControl
gui.controlOnEvent
gui.applicationSetMainWindow
gui.applicationRun
gui.textBoxText
gui.textBoxSetText
gui.listBoxSelectedIndex
gui.listBoxAppendItem
gui.listBoxClear
gui.textLabelSetText
gui.windowClose
gui.eventKeyCode
gui.eventSelectedIndex
gui.eventWindowWidth
gui.eventWindowHeight
```

No `gui.eventCancelClose` target is committed yet; cancellable close events are
deferred. Runtime calls that touch live GUI state take `session GuiSession` and
a kind-specific handle such as `textBox GuiTextBox`, `listBox GuiListBox`, or
`window GuiWindow`. Event payload readers take `event GuiEvent`.

## Cleanup, Concurrency, Time

| Family | Verbs | Status |
|---|---|---|
| Cleanup | `defer`, `deferLog`, `deferAwaitLog`, `deferWhenExitLog` | partial |
| Cleanup metadata | `deferLogSink`, `deferRunOn`, `deferOrder`, `deferFailurePolicy`, `deferConsumes`, `deferAwaitLogSink`, `deferAwaitTimeout`, `deferWhenExitLogSink` | metadata |
| Guard tokens | `guardTokenSource`, `guardTokenOwner`, `guardTokenProtects`, `guardTokenRelease` | metadata |
| Task groups | `taskGroup`, `startInGroup`, `awaitGroup`, `bindGroupError`, `branchIfGroupError` compatibility rows | sync-fallback |
| Channels | `send`, `receive`, `branchIfChannelClosed` compatibility row | sync-fallback |
| Locks | `mutex`, `lock`, `unlock` | sync-fallback |
| Await wait sets | `await WAIT_SET`, `case CALL LABEL`, `done LABEL` | lowered for libuv console async |
| Legacy select rows | `select`, `selectCase`, `runSelect`, `branchSelected` | sync-fallback |
| Intervals | `interval`, `startInterval`, `awaitIntervalTick` | sync-fallback |
| Worker pools | `workerPool`, `work`, `workArg`, `submitWork`, `awaitWork` | sync-fallback |

## Collections

```text
listType listAllocator
arrayType arrayLength
sliceType
smallListType smallListInlineCapacity smallListSpillAllocator
mapType mapKey mapValue mapAllocator
collectionOperation collectionOperationArg collectionOperationOutput
collectionOperationFailure collectionOperationEffect
collectionOperationAllocation collectionOperationMutation
collectionOperationIndexPolicy collectionOperationLengthSource
collectionOperationCapacitySource collectionOperationBorrowSource
collectionOperationSpillAllocator collectionOperationSpillFailure
listLiteral listLiteralLength listLiteralIndexBase listLiteralIndexPolicy listLiteralItem
```

Collection declarations are metadata/runtime-contract surface today. They do
not create executable methods by themselves: calls like `TaskList.append`,
`TaskMap.get`, or a declared `collectionOperation` target still need an
explicit operation/runtime binding. `semlint.py` reports these as collection
runtime gaps before codegen rejects the unsupported typed collection target.

## Runtime Bindings and Intrinsics

```text
runtimeBinding NAME TARGET
runtimeBindingPrecondition NAME "text"
runtimeBindingFailure NAME ERROR.VARIANT
runtimeBindingAsyncStart NAME native.SYMBOL
runtimeBindingAsyncAwait NAME native.SYMBOL
nativeRuntimeSource MODULE "PATH"
nativeRuntimeLinkArg MODULE [any|windows|posix] "ARG"
intrinsicName NAME arithmetic.addInt64
```

The compiler has direct lowering for selected runtime bindings, generic async
runtimeBinding start/await pairs, module-declared native adapter sources/link
args, and arithmetic intrinsics. Unknown runtime binding names fall back to
normal operation body compilation.
