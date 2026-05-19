# Verb Index

This is a grouped index, not the exhaustive status table. Use `SYNTAX.md` for
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
| `buildProfile` | `buildProfile PROJECT dev|prod` | partial |
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
| `dependency` | `dependency PROJECT ALIAS MODULE_PATH VERSION_OR_REF` | partial |
| `dependencySource` | `dependencySource PROJECT ALIAS [local|path|github|http] SOURCE [REF]` | partial |
| `dependencyFetch` | `dependencyFetch PROJECT ALIAS github OWNER/REPO REF` or `dependencyFetch PROJECT ALIAS http "https://..."` | partial |
| `dependencyCache` | `dependencyCache PROJECT "PATH"` | partial |
| `dependencyLock` | `dependencyLock PROJECT "PATH"` | partial |
| `dependencyIntegrity` | `dependencyIntegrity PROJECT ALIAS sha256:<64-hex>|commit:<7-40-hex>` | partial |
| `nativeOutput` | `nativeOutput PROJECT "PATH"` | partial |
| `nativeHttpHost` | `nativeHttpHost PROJECT "HOST"` | metadata |
| `nativeHttpPort` | `nativeHttpPort PROJECT PORT` | metadata |
| `formatterSetting` | `formatterSetting PROJECT KEY VALUE` | metadata |
| `linterSetting` | `linterSetting PROJECT KEY VALUE` | metadata |
| `docsOutput` | `docsOutput PROJECT "PATH"` | metadata |
| `importModule` | `importModule ALIAS DOTTED.PATH` or `importModule DOTTED.PATH [as ALIAS]` | lowered pre-parse |
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
| `input` | `input OP NAME TYPE` | lowered |
| `output` | `output OP TYPE...` | lowered |
| `effect` | `effect OP ACTION PATH` | checked metadata |
| `memory` | `memory OP POLICY...` | checked metadata |
| `async` | `async OP yes/no` | checked metadata |
| `purpose` | `purpose OP "text"` | checked metadata |
| `invariant` | `invariant OP "text"` | checked metadata |
| `warning` | `warning OP "text"` | checked metadata |
| `guarantee` | `guarantee TARGET "text"` | metadata |
| `failure` | `failure TARGET NAME "text"` | metadata |
| `security` | `security TARGET "text"` | metadata |
| `timing` | `timing TARGET "text"` | metadata |
| `observability` | `observability TARGET "text"` | metadata |

## Values and State

| Verb | Schema | Status |
|---|---|---|
| `const` | `const NAME TYPE VALUE` | lowered |
| `var` | `var NAME TYPE VALUE` | lowered |
| `storage` | `storage SCOPE MUTABILITY NAME TYPE [VALUE]` | lowered |
| `sharedState` | `sharedState SCOPE MUTABILITY NAME TYPE [INITIAL]` | lowered |
| `set` | `set SCOPE NAME VALUE ...` | lowered |
| `read` | `read sharedState OUT TYPE BACKING ...` | lowered |
| `domainLiteral` | `domainLiteral NAME TYPE VALUE` | lowered as const |
| `literal` | `literal NAME TYPE` | lowered as external const stub |

Metadata families:

```text
sharedStateOwner sharedStateGuard
domainLiteralSource domainLiteralTrust domainLiteralValidation
literalBytes literalDigest literalPreview literalSource literalTrust
```

## Calls and Control Flow

| Family | Verbs |
|---|---|
| Calls | `call`, `arg`, `timeout`, `cancelOn`, `run`, `start`, `await` |
| Binding | `bind`, `bindOk`, `bindError`, `ignoreOk`, `ignoreValue` |
| Errors | `makeError`, `declareFailure`, `error`, `errorCase` |
| Labels | `label`, `branch`, `branchIf`, `branchIfError` |
| Returns | `returnOk`, `returnError`, `returnValue` |

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

## HTML Templates

Standard-library modules are imported through the `standard.*` namespace. The
compiler resolves them through the std search path; the library root contains
`module.sem`, and each child module lives at `<module>/main.sem`.

Import `standard.html` with the canonical `html` alias before using this
surface in app modules:

```text
importModule html standard.html
```

| Verb | Schema | Status |
|---|---|---|
| `htmlTemplate` | `htmlTemplate NAME` | lowered |
| `htmlArg` | `htmlArg TEMPLATE ARG_NAME TYPE` | lowered |
| `htmlBody` | `htmlBody TEMPLATE` followed by indented HTML/SSX lines | lowered |

`html.hydrate.TemplateName` is a generated call target, not a standalone verb.
It is exposed through the imported `standard.html` namespace and assembles the
template body with explicit `arg` rows whose names match declared `htmlArg`
inputs. Dynamic holes must be declared `htmlArg` references, written as
`{htmlArg.name}` or the same reference with surrounding whitespace. Other brace
holes are rejected outside raw `<style>` and `<script>` text.
Hydration escapes `HtmlText` in text and quoted attribute sinks. `class`
attributes require `HtmlClass`, URL attributes such as `href` / `src` require
`SafeUrl`, and `HtmlFragment` / `HtmlTrustedFragment` / `HtmlDocument` values
can only hydrate text-content positions where raw markup is intentional.

## Native Windows GUI

`target windowsGui` and `targetRuntime PROJECT windowsGui` are the
compiler/build bridge. GUI source uses normal `entry console OPERATION`,
`operation`, `call`, `arg`, and `run` rows. The larger GUI vocabulary belongs
to `standard.gui` as function targets, contracts, capabilities, and validation
rules. The compiler should only lower explicit `gui.*` calls and link/start the
native GUI runtime. There is no `entry windowsGui` row. The preferred
standard-library import is:

```text
importModule gui standard.gui
```

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
input HANDLER session GuiSession
input HANDLER event GuiEvent
output HANDLER CSignedInt32
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
| Task groups | `taskGroup`, `startInGroup`, `awaitGroup`, `bindGroupError`, `branchIfGroupError` | sync-fallback |
| Channels | `send`, `receive`, `branchIfChannelClosed` | sync-fallback |
| Locks | `mutex`, `lock`, `unlock` | sync-fallback |
| Select | `select`, `selectCase`, `runSelect`, `branchSelected` | sync-fallback |
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
runtime gaps while the compiler would otherwise use the zero-stub external
fallback.

## Runtime Bindings and Intrinsics

```text
runtimeBinding NAME TARGET
runtimeBindingPrecondition NAME "text"
runtimeBindingFailure NAME ERROR.VARIANT
intrinsicName NAME arithmetic.addI64
```

The compiler has direct lowering for selected runtime bindings and arithmetic
intrinsics. Unknown runtime binding names fall back to normal operation body
compilation.
