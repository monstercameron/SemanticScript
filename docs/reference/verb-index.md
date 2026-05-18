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
| `registerModule` | `registerModule PROJECT MODULE_PATH "PATH"` | partial |
| `importModule` | `importModule DOTTED.PATH [as ALIAS]` | lowered pre-parse |
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
