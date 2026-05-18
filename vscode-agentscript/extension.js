'use strict';

const childProcess = require('child_process');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

const declarationVerbs = new Set([
  'section',
  'project', 'target', 'runtime', 'entry', 'module', 'mode', 'dependency', 'dependencyEffect',
  'dependencyExports', 'dependencyFunction', 'dependencyFunctionInput',
  'dependencyFunctionOutput', 'dependencyFunctionEffect', 'dependencyFunctionAsync',
  'importModule', 'type', 'typeParameter', 'typeInvariant', 'typeRepresentation', 'typeTrust',
  'typeMemory', 'typeLayout', 'typeLiteralEncoding', 'typeLiteralTerminator',
  'record', 'recordLayout', 'recordAlign', 'field', 'fieldDefault', 'fieldInvariant',
  'enum', 'enumCase', 'error',
  'errorCase', 'operation', 'webServer', 'serverHost', 'serverPort', 'route',
  'routeTimeout', 'routeMiddleware', 'storage', 'sharedState', 'domainLiteral',
  'literal', 'listLiteral', 'jsonCodec', 'policy', 'errorPolicy',
  'validator', 'codec', 'schema', 'unknownFields', 'resource', 'resourceKey',
  'resourceValue', 'resourceKind', 'adapter', 'boundary', 'mapper', 'retryPolicy',
  'timeoutBudget', 'capability', 'authority', 'mutex', 'shared', 'channel',
  'listType', 'arrayType', 'sliceType', 'smallListType', 'mapType',
  'interval', 'workerPool', 'work',
  'const', 'var', 'testCovers',
]);

const contextVerbs = new Set([
  'input', 'output', 'effect', 'memory', 'memoryHeap', 'memoryArena',
  'memoryAllocationSource', 'memoryStackLimit', 'async', 'operationBody',
  'purpose', 'invariant', 'warning', 'failure', 'guarantee', 'security',
  'timing', 'observability',
  'dependencyPath', 'dependencyFailure', 'intrinsicName',
  'runtimeBinding', 'runtimeBindingPrecondition', 'runtimeBindingFailure',
  'recordConstructor', 'recordConstructorFailure', 'recordBuildFailure',
  'jsonCodecStrict', 'jsonCodecUnknownFields', 'jsonCodecDecodeTarget',
  'jsonCodecEncodeTarget', 'jsonCodecRequiredField', 'jsonCodecInput',
  'jsonCodecOutput', 'jsonCodecDecodeFailure', 'jsonCodecEncodeFailure',
  'jsonCodecLimit',
  'trustBoundary', 'trustBoundaryKind', 'trustBoundaryInput',
  'trustBoundaryOutput', 'trustBoundaryValidator', 'trustBoundarySource',
  'domainLiteralSource', 'domainLiteralTrust', 'domainLiteralValidation',
  'literalBytes', 'literalDigest', 'literalPreview', 'literalSource', 'literalTrust',
  'sharedStateOwner', 'sharedStateGuard',
  'guardTokenSource', 'guardTokenOwner', 'guardTokenProtects', 'guardTokenRelease',
  'listAllocator', 'arrayLength', 'smallListInlineCapacity', 'smallListSpillAllocator',
  'mapKey', 'mapValue', 'mapAllocator',
  'listLiteralLength', 'listLiteralIndexBase', 'listLiteralIndexPolicy', 'listLiteralItem',
  'collectionOperation', 'collectionOperationArg', 'collectionOperationOutput',
  'collectionOperationFailure', 'collectionOperationEffect', 'collectionOperationAllocation',
  'collectionOperationMutation', 'collectionOperationIndexPolicy',
  'collectionOperationLengthSource', 'collectionOperationBorrowSource',
  'collectionOperationCapacitySource', 'collectionOperationSpillAllocator',
  'collectionOperationSpillFailure',
  'retryMaxAttempts', 'retryInitialDelay', 'retryMaximumDelay', 'retryJitter',
  'group', 'groupPurpose', 'groupInput', 'groupOutput', 'groupError',
  'groupFailure', 'groupTiming',
  'deferLogSink', 'deferRunOn', 'deferOrder', 'deferFailurePolicy',
  'deferConsumes', 'deferAwaitLogSink', 'deferAwaitTimeout', 'deferWhenExitLogSink',
  'workArg',
]);

const actionVerbs = new Set([
  'set', 'call', 'arg', 'run', 'start', 'await', 'bind', 'bindOk',
  'bindError', 'ignoreOk', 'ignoreValue', 'declareFailure', 'makeError',
  'new', 'fieldGet', 'fieldSet', 'recordBuilder', 'recordSet', 'recordCopy',
  'recordBuild', 'read', 'timeout', 'cancelOn',
  'defer', 'deferLog', 'deferAwaitLog', 'deferWhenExitLog', 'select', 'selectCase',
  'runSelect', 'taskGroup', 'startInGroup', 'awaitGroup', 'bindGroupError',
  'send', 'receive', 'lock', 'unlock', 'useRetry', 'useCapability',
  'startInterval', 'awaitIntervalTick', 'submitWork', 'awaitWork',
]);

const controlVerbs = new Set([
  'label', 'branch', 'branchIf', 'branchIfError', 'branchSelected',
  'branchIfGroupError', 'branchIfChannelClosed', 'returnOk', 'returnError',
  'returnValue',
]);

const roleSuffixPattern = /(Call|Error|Failed|Failure|Result|Option|Request|Response|Token|Timeout|Deadline|Defer|Group|Policy|Codec|Validator|Mapper|Adapter|Boundary|Resource|Capability|Authority|Channel|Mutex|Lock|Guard|State|Storage|Select|Record|Builder|Field|Enum|Variant|Value|Counter|Count|Index|Length|Capacity|Allocator|Source|Target|Step|Accumulator|Divisor|Remainder|Span|Metric|Trace)$/;

const primitiveTargets = new Map([
  ['console.writeLine', 'puts(text) -> i32. Writes one text line.'],
  ['console.writeIntegerLine', 'printf("%lld\\n", value) -> i32. Writes one integer line.'],
  ['console.writeInteger', 'Alias for console.writeIntegerLine.'],
  ['console.writeFloatLine', 'printf("%f\\n", value) -> i32. Writes one floating-point line.'],
  ['math.addI64', 'i64 addition. Infallible math target; use bind.'],
  ['math.subtractI64', 'i64 subtraction. Infallible math target; use bind.'],
  ['math.multiplyI64', 'i64 multiplication. Infallible math target; use bind.'],
  ['math.divideI64', 'i64 signed division. Infallible in the current AST model; use bind.'],
  ['math.moduloI64', 'i64 signed remainder. Infallible in the current AST model; use bind.'],
  ['math.equalI64', 'i64 equality comparison returning Bool.'],
  ['math.notEqualI64', 'i64 inequality comparison returning Bool.'],
  ['math.lessThanI64', 'i64 less-than comparison returning Bool.'],
  ['math.lessThanOrEqualI64', 'i64 less-than-or-equal comparison returning Bool.'],
  ['math.greaterThanI64', 'i64 greater-than comparison returning Bool.'],
  ['math.greaterThanOrEqualI64', 'i64 greater-than-or-equal comparison returning Bool.'],
  ['math.addF64', 'F64 addition. Infallible math target; use bind.'],
  ['math.subtractF64', 'F64 subtraction. Infallible math target; use bind.'],
  ['math.multiplyF64', 'F64 multiplication. Infallible math target; use bind.'],
  ['math.divideF64', 'F64 division. Infallible math target; use bind.'],
  ['math.equalF64', 'F64 equality comparison returning Bool.'],
  ['math.notEqualF64', 'F64 inequality comparison returning Bool.'],
  ['math.lessThanF64', 'F64 less-than comparison returning Bool.'],
  ['math.lessThanOrEqualF64', 'F64 less-than-or-equal comparison returning Bool.'],
  ['math.greaterThanF64', 'F64 greater-than comparison returning Bool.'],
  ['math.greaterThanOrEqualF64', 'F64 greater-than-or-equal comparison returning Bool.'],
  ['math.intToFloat', 'Signed integer to F64 conversion.'],
  ['math.floatToInt', 'F64 to signed integer conversion, rounding toward zero.'],
  ['math.convertSignedInt64ToFloat64', 'Alias for math.intToFloat.'],
  ['math.convertFloat64ToSignedInt64', 'Alias for math.floatToInt.'],
  ['math.equalCSignedInt32', 'C signed 32-bit equality comparison returning Bool.'],
  ['math.greaterThanOrEqualCByteCount', 'C byte-count greater-than-or-equal comparison returning Bool.'],
  ['math.checkedMultiplyI64', 'i64 signed multiply with overflow detection. Fallible target; use bindOk, bindError, and branchIfError.'],
  ['pointer.loadByte', 'Reads one byte from buffer + offset. Requires declared memory read effects for checked lint paths.'],
  ['pointer.storeByte', 'Writes one byte to buffer + offset. Requires declared memory write effects for checked lint paths.'],
  ['pointer.offset', 'Returns buffer + offset without dereferencing.'],
  ['pointer.difference', 'Returns pointer distance as a signed integer.'],
  ['pointer.isNull', 'Returns Bool indicating whether a pointer is null.'],
  ['scheduler.sleep', 'Async typed-duration sleep target. Use cancelOn, start, await, bindError, and branchIfError.'],
  ['retryPolicy.delayForAttempt', 'Retry-policy delay calculation target. Fallible when policy or attempt state is invalid.'],
  ['metrics.computeIncrementI64', 'Metrics-owned counter increment calculation. Fallible target; bind success and error explicitly.'],
  ['math.subI64', 'Alias for math.subtractI64.'],
  ['math.mulI64', 'Alias for math.multiplyI64.'],
  ['math.divI64', 'Alias for math.divideI64.'],
  ['math.modI64', 'Alias for math.moduloI64.'],
  ['math.eqI64', 'Alias for math.equalI64.'],
  ['math.neI64', 'Alias for math.notEqualI64.'],
  ['math.ltI64', 'Alias for math.lessThanI64.'],
  ['math.leI64', 'Alias for math.lessThanOrEqualI64.'],
  ['math.gtI64', 'Alias for math.greaterThanI64.'],
  ['math.geI64', 'Alias for math.greaterThanOrEqualI64.'],
]);

const generatedTargetPattern = /^(?:json\.(?:decode|encode)\.[A-Z][A-Za-z0-9_]*)$/;
const cRuntimeTargetPattern = /^c\.[A-Za-z_][A-Za-z0-9_]*$/;
const jsonPrimitiveTargetTypes = new Set([
  'I64', 'CSignedInt64', 'CSignedInt32', 'CUnsignedInt32',
  'CSignedInt16', 'CUnsignedInt16', 'CSignedByte', 'CUnsignedByte',
  'DurationMilliseconds', 'MonotonicMilliseconds', 'UtcMilliseconds',
  'Bool', 'F64', 'CFloat64', 'CFloat32', 'String', 'CNullTerminatedByteString',
]);

const generatedTargetHoverText = (text) => {
  const targetType = text.split('.').pop();

  if (jsonPrimitiveTargetTypes.has(targetType)) {
    if (text.startsWith('json.decode.')) {
      return 'Reference compiler primitive JSON decode target. Numeric values use libc parsing, Bool compares against true, and malformed inputs return the libc default.';
    }

    if (text.startsWith('json.encode.')) {
      return 'Reference compiler primitive JSON encode target. Numerics and Bool use direct formatting; strings are quoted with full escaping deferred to the codec runtime.';
    }
  }

  if (text.startsWith('json.decode.')) {
    return 'Generated JSON decode target. It should be declared by jsonCodecDecodeTarget and backed by jsonCodec input, output, failure, strictness, and limit metadata.';
  }

  if (text.startsWith('json.encode.')) {
    return 'Generated JSON encode target. It should be declared by jsonCodecEncodeTarget and backed by jsonCodec input, output, failure, strictness, and limit metadata.';
  }

  return 'Generated AgentScript target declared by metadata.';
};

const schemaValues = new Map([
  ['true', 'Boolean literal token.'],
  ['false', 'Boolean literal token.'],
  ['yes', 'Boolean schema value.'],
  ['no', 'Boolean schema value.'],
  ['capturedOutputReplay', 'Mode marker for programs that replay captured output.'],
  ['local', 'Storage scope for operation-local storage.'],
  ['module', 'Storage scope for module-owned storage.'],
  ['process', 'Storage scope for process-shared state.'],
  ['sharedState', 'Shared-state storage scope. Reads and writes require guard-token authority.'],
  ['immutable', 'Storage mutability: value cannot be changed after declaration.'],
  ['mutable', 'Storage mutability: value can change through explicit set lines.'],
  ['read', 'Effect or collection role mode: read.'],
  ['write', 'Effect or collection role mode: write.'],
  ['log', 'Effect mode: log/observability output.'],
  ['sourceTape', 'operationBody kind for normal explicit AgentScript source tape.'],
  ['runtimeBinding', 'operationBody kind for a semantic signature implemented by runtime binding metadata.'],
  ['recordConstructor', 'operationBody kind for an operation-backed record constructor.'],
  ['intrinsic', 'operationBody kind for a primitive intrinsic with intrinsicName metadata.'],
  ['externalDependency', 'operationBody kind for an injected external dependency with dependencyPath metadata.'],
  ['codecDecode', 'operationBody kind reserved for generated codec decode bodies.'],
  ['codecEncode', 'operationBody kind reserved for generated codec encode bodies.'],
  ['collectionOperation', 'operationBody kind reserved for generated collection operation bodies.'],
  ['success', 'Generic/result type parameter role for the success value.'],
  ['error', 'Generic/result type parameter role for the error value.'],
  ['decode', 'Codec direction: bytes into typed record.'],
  ['encode', 'Codec direction: typed record into bytes.'],
  ['reject', 'Codec unknown-field policy: reject unknown fields.'],
  ['ignore', 'Codec unknown-field policy: ignore unknown fields.'],
  ['keep', 'Codec unknown-field policy: preserve unknown fields.'],
  ['none', 'Explicit no-failure marker for an infallible contract.'],
  ['maximumBytes', 'Codec or literal byte limit kind.'],
  ['sha256', 'Digest algorithm.'],
  ['utf8', 'UTF-8 string literal encoding.'],
  ['nullByte', 'C-string null terminator rule.'],
  ['validatedRuntimeValue', 'Trust-boundary source: value produced by validator at runtime.'],
  ['trustedStaticLiteral', 'Trust-boundary source: static literal accepted by type literal rules.'],
  ['trustedUtf8Literal', 'Trust-boundary source: static UTF-8 literal accepted by validation rules.'],
  ['trustedExternalCNullTerminatedUtf8Source', 'Trust-boundary source: externally stored C-null-terminated UTF-8 data with digest/source metadata.'],
  ['trustedInternal', 'Trust marker for internally trusted data.'],
  ['trustedSessionContext', 'Trust marker for values supplied by trusted session context.'],
  ['trustedStaticAsset', 'Trust marker for committed/static assets.'],
  ['rawPointerToValidatedCString', 'Trust-boundary kind: raw pointer becomes validated C string.'],
  ['rawUtf8ToValidatedText', 'Trust-boundary kind: raw UTF-8 becomes validated text.'],
  ['row', 'Record layout kind: row layout.'],
  ['column', 'Record layout kind: column layout.'],
  ['packed', 'Record layout kind: packed layout.'],
  ['heap', 'Heap allocator or memory policy marker.'],
  ['inPlace', 'Collection mutation mode: mutates existing storage.'],
  ['boundsChecked', 'Collection index policy: bounds checked.'],
  ['denseZeroIndexed', 'List literal index policy: dense zero-based indexes.'],
  ['all', 'Defer lifecycle trigger for every operation exit path.'],
  ['immutableUpdate', 'Collection mutation mode: returns a new collection value.'],
  ['borrowedView', 'Collection mutation/view mode: returns a borrowed view.'],
  ['zeroBasedChecked', 'Collection index policy: zero-based and checked.'],
  ['zeroBasedCheckedRange', 'Collection range policy: zero-based and checked.'],
  ['contiguousUniqueAscending', 'List literal index policy: indices must be contiguous, unique, and ascending.'],
  ['arena.request', 'Named request arena allocator.'],
  ['arena.process', 'Named process arena allocator.'],
  ['arena.static', 'Named static arena allocator.'],
  ['returnOk', 'Defer lifecycle trigger for success returns.'],
  ['returnError', 'Defer lifecycle trigger for error returns.'],
  ['reverseRegistration', 'Defer ordering policy: cleanup runs in reverse registration order.'],
  ['logAndSuppress', 'Defer failure policy: log cleanup failure and preserve the original return.'],
  ['protectedBy', 'Authority marker: following token is the guard token protecting the operation.'],
  ['ownedBy', 'Authority marker: following token owns the module mutation.'],
]);

const domainMethods = new Set([
  'add', 'addPositiveStep', 'subtract', 'subtractStep', 'subtractPositiveStep',
  'multiply', 'multiplyByStep', 'multiplyByCounter', 'divide', 'modulo', 'moduloBy',
  'equal', 'notEqual',
  'lessThan', 'lessThanOrEqual', 'greaterThan', 'greaterThanOrEqual',
  'square', 'checkedMultiply', 'checkedMultiplyByCounter', 'checkedMultiplyByStep',
  'length', 'append', 'get', 'set', 'slice', 'insert', 'update', 'remove',
]);

const primitiveTypes = new Map([
  ['I64', '64-bit integer.'],
  ['I32', '32-bit integer.'],
  ['I16', '16-bit integer.'],
  ['I8', '8-bit integer.'],
  ['ExitCode', '32-bit process exit code.'],
  ['Bool', 'Boolean value.'],
  ['F64', '64-bit floating-point value.'],
  ['F32', '32-bit floating-point value.'],
  ['String', 'Null-terminated UTF-8 string.'],
  ['Bytes', 'Byte sequence.'],
  ['Utf8Text', 'UTF-8 text value.'],
  ['RawUtf8Text', 'Unvalidated UTF-8 text bytes.'],
  ['RawJsonBytes', 'Untrusted JSON byte input.'],
  ['JsonBytes', 'Validated/generated JSON bytes.'],
  ['CNullTerminatedByteString', 'Validated null-terminated C byte string.'],
  ['RawCStringPointer', 'Raw C string pointer before trust-boundary validation.'],
  ['COpaqueMemoryAddress', 'Opaque memory address value.'],
  ['CByteCount', 'C ABI byte-count value.'],
  ['CSignedByteCount', 'C ABI signed byte-count value.'],
  ['CAddressOffset', 'C ABI pointer offset value.'],
  ['CUnixSecondsSinceEpoch', 'C ABI Unix timestamp seconds value.'],
  ['CCpuClockTicks', 'C ABI CPU clock tick value.'],
  ['CFileByteOffset', 'C ABI file byte offset value.'],
  ['CSignedByte', 'C ABI signed 8-bit byte.'],
  ['CUnsignedByte', 'C ABI unsigned 8-bit byte.'],
  ['CSignedInt16', 'C ABI signed 16-bit integer.'],
  ['CUnsignedInt16', 'C ABI unsigned 16-bit integer.'],
  ['CSignedInt32', 'C ABI signed 32-bit integer.'],
  ['CUnsignedInt32', 'C ABI unsigned 32-bit integer.'],
  ['CSignedInt64', 'C ABI signed 64-bit integer.'],
  ['CUnsignedInt64', 'C ABI unsigned 64-bit integer.'],
  ['CFloat32', 'C ABI 32-bit floating-point value.'],
  ['CFloat64', 'C ABI 64-bit floating-point value.'],
  ['CFileHandle', 'Opaque C file handle pointer.'],
  ['CDecomposedTimeAddress', 'Opaque C decomposed-time pointer.'],
  ['CSetjmpRegisterBuffer', 'Opaque C setjmp buffer pointer.'],
  ['Console', 'Opaque console dependency token.'],
  ['Process', 'Opaque process dependency token.'],
  ['Environment', 'Opaque environment dependency token.'],
  ['HttpRequest', 'Opaque HTTP request dependency token.'],
  ['DatabaseClient', 'Opaque database client dependency token.'],
  ['Clock', 'Opaque clock dependency token.'],
  ['Void', 'No useful success value. Used with ignoreOk/ignoreValue to make explicit discards visible.'],
  ['DurationMilliseconds', '64-bit duration in milliseconds.'],
  ['MonotonicMilliseconds', '64-bit monotonic timestamp in milliseconds.'],
  ['UtcMilliseconds', '64-bit UTC timestamp in milliseconds.'],
]);

const opaqueInputs = new Set([
  'console', 'process', 'environment', 'httpRequest', 'databaseClient', 'clock',
  'accountRepository', 'metricsRuntime', 'scheduler', 'metricsLock',
]);

const verbHoverText = new Map([
  ['project', 'Top-level declaration: project NAME.'],
  ['target', 'Top-level declaration: target NAME.'],
  ['runtime', 'Top-level declaration: runtime NAME VERSION.'],
  ['entry', 'Top-level declaration: entry MODE OPERATION.'],
  ['module', 'Top-level module declaration. Parsed as project context by the current compiler.'],
  ['mode', 'Top-level mode declaration such as mode capturedOutputReplay.'],
  ['dependency', 'Dependency declaration. Dependency contract metadata is parsed for tooling context.'],
  ['dependencyEffect', 'Dependency effect declaration.'],
  ['dependencyExports', 'Dependency export declaration.'],
  ['dependencyFunction', 'Dependency function declaration metadata.'],
  ['dependencyFunctionInput', 'Dependency function input metadata.'],
  ['dependencyFunctionOutput', 'Dependency function output metadata.'],
  ['dependencyFunctionEffect', 'Dependency function effect metadata.'],
  ['dependencyFunctionAsync', 'Dependency function async metadata.'],
  ['importModule', 'Import declaration: importModule DOTTED.PATH as ALIAS.'],
  ['type', 'Type alias declaration: type ALIAS UNDERLYING [extra-tokens].'],
  ['typeInvariant', 'Type metadata: typeInvariant TYPE "text". Multi-valued invariant context for a type.'],
  ['typeRepresentation', 'Type metadata: typeRepresentation TYPE UNDERLYING ARGS...'],
  ['typeTrust', 'Type metadata: typeTrust TYPE untrusted|trusted|sanitized|internal|public.'],
  ['typeMemory', 'Type metadata: typeMemory TYPE inline|heap|arena.'],
  ['typeLayout', 'Type metadata: typeLayout TYPE row|column|packed.'],
  ['record', 'Record declaration: record NAME [layout KIND] [align N]. Parsed by the current compiler.'],
  ['field', 'Record field declaration: field RECORD_NAME FIELD_NAME FIELD_TYPE.'],
  ['enum', 'Enum declaration: enum NAME [repr TYPE]. Parsed by the current compiler.'],
  ['enumCase', 'Enum case declaration: enumCase ENUM_NAME CASE_NAME [VALUE].'],
  ['error', 'Error type declaration: error NAME.'],
  ['errorCase', 'Error variant declaration: errorCase ERROR_TYPE VARIANT [CAUSE_TYPE].'],
  ['operation', 'Operation declaration. Header/context lines attach to this operation.'],
  ['webServer', 'Web server declaration: webServer NAME. Parsed as metadata.'],
  ['serverHost', 'Web server metadata: serverHost SERVER_NAME "host".'],
  ['serverPort', 'Web server metadata: serverPort SERVER_NAME PORT.'],
  ['route', 'Web server route: route SERVER METHOD PATH HANDLER_OPERATION.'],
  ['routeTimeout', 'Web server route timeout metadata.'],
  ['routeMiddleware', 'Web server route middleware metadata.'],
  ['jsonCodec', 'Contract-heavy JSON codec declaration.'],
  ['codec', 'Contract-heavy codec declaration.'],
  ['schema', 'Codec schema attachment: schema CODEC_NAME RECORD_NAME.'],
  ['unknownFields', 'Codec unknown-field policy: unknownFields CODEC_NAME reject|keep|ignore.'],
  ['validator', 'Contract-heavy validator declaration.'],
  ['mapper', 'Contract-heavy mapper declaration.'],
  ['adapter', 'Contract-heavy adapter declaration.'],
  ['boundary', 'Contract-heavy boundary declaration.'],
  ['policy', 'Policy declaration. Policies are semantic nodes, not casual helpers.'],
  ['errorPolicy', 'Error policy declaration for mapping failures to domain/public outcomes.'],
  ['retryPolicy', 'Retry policy declaration. Parsed as policy metadata.'],
  ['timeoutBudget', 'Timeout budget declaration. Parsed as policy metadata.'],
  ['resource', 'Resource declaration: resource NAME kind KIND.'],
  ['resourceKey', 'Resource key metadata.'],
  ['resourceValue', 'Resource value metadata.'],
  ['resourceKind', 'Resource kind metadata.'],
  ['capability', 'Capability declaration: capability NAME EFFECT_PATH ACCESS.'],
  ['authority', 'Authority metadata: authority OPERATION EFFECT_PATH ACCESS.'],
  ['mutex', 'Top-level mutex declaration. Parsed as metadata.'],
  ['shared', 'Top-level shared-state declaration. Parsed as metadata.'],
  ['channel', 'Top-level channel declaration. Parsed as metadata.'],
  ['interval', 'Typed interval declaration. Single-thread compiler lowering treats start/await ticks as no-ops.'],
  ['workerPool', 'Worker-pool declaration. Single-thread compiler lowering runs submitted work inline.'],
  ['work', 'Worker-pool work item declaration: work NAME target OPERATION.'],
  ['testCovers', 'Top-level coverage metadata: testCovers TEST_NAME TARGET_NAME.'],
  ['input', 'Operation metadata: input OPERATION PARAM_NAME PARAM_TYPE.'],
  ['output', 'Operation metadata: output OPERATION TYPE_EXPR.'],
  ['effect', 'Operation metadata: declares an external effect.'],
  ['memory', 'Operation metadata: declares memory behavior.'],
  ['async', 'Operation metadata: async yes|no.'],
  ['purpose', 'Hard metadata: declares what an operation or abstraction is for.'],
  ['invariant', 'Hard metadata: declares a condition future edits must preserve.'],
  ['warning', 'Hard metadata: declares a hazard future agents must read before editing.'],
  ['failure', 'Hard metadata: declares a named failure and explanation.'],
  ['guarantee', 'Hard metadata: declares a guarantee attached to an operation or abstraction.'],
  ['security', 'Hard metadata: declares security context agents must preserve.'],
  ['timing', 'Hard metadata: declares timing behavior or constraints.'],
  ['observability', 'Hard metadata: declares trace/log/metric context.'],
  ['const', 'Body declaration statement: const NAME TYPE VALUE.'],
  ['var', 'Body declaration statement: var NAME TYPE INITIAL_VALUE.'],
  ['label', 'Control-flow statement: label NAME. Labels are first-class basic blocks.'],
  ['call', 'Call lifecycle statement: call CALL_NAME TARGET_PATH.'],
  ['arg', 'Call lifecycle statement: arg CALL_NAME ARG_NAME VALUE_NAME.'],
  ['timeout', 'Call lifecycle statement: timeout CALL_NAME DURATION_VALUE.'],
  ['cancelOn', 'Call lifecycle statement: cancelOn CALL_NAME CANCELLATION_TOKEN.'],
  ['run', 'Call lifecycle statement: execute call immediately.'],
  ['start', 'Call lifecycle statement: begin async work. Parsed by current compiler.'],
  ['await', 'Call lifecycle statement: wait for started async work. Parsed by current compiler.'],
  ['bind', 'Binding statement for infallible calls: bind VALUE TYPE CALL_NAME.'],
  ['bindOk', 'Binding statement for success leg: bindOk VALUE TYPE CALL_NAME.'],
  ['bindError', 'Binding statement for failure leg: bindError ERROR ERROR_TYPE CALL_NAME. Must pair with branchIfError.'],
  ['ignoreOk', 'Binding statement: ignoreOk CALL_NAME TYPE explicitly discards a fallible call success value.'],
  ['ignoreValue', 'Binding statement: ignoreValue CALL_NAME TYPE explicitly discards an infallible call result.'],
  ['makeError', 'Error construction: makeError NAME ERROR_TYPE.VARIANT [SOURCE_VALUE].'],
  ['new', 'Reserved record I/O statement: new VALUE_NAME RECORD_NAME. Parsed, not lowered by current compiler.'],
  ['fieldGet', 'Reserved record I/O statement: fieldGet OUT_NAME TYPE RECORD_VALUE FIELD_NAME.'],
  ['fieldSet', 'Reserved record I/O statement: fieldSet RECORD_VALUE FIELD_NAME VALUE_NAME.'],
  ['taskGroup', 'Reserved structured-concurrency statement: taskGroup NAME [maxTasks N] [cancelOnFirstError yes|no].'],
  ['startInGroup', 'Reserved structured-concurrency statement: startInGroup CALL_NAME GROUP_NAME.'],
  ['awaitGroup', 'Reserved structured-concurrency statement: awaitGroup GROUP_NAME.'],
  ['bindGroupError', 'Reserved structured-concurrency statement: bindGroupError ERROR TYPE GROUP_NAME.'],
  ['branchIfGroupError', 'Reserved structured-concurrency control statement.'],
  ['defer', 'Reserved cleanup statement: defer NAME TARGET_PATH ARGS...'],
  ['deferLog', 'Reserved cleanup statement that logs cleanup failure.'],
  ['deferAwaitLog', 'Reserved async cleanup statement that awaits and logs cleanup failure.'],
  ['deferWhenExitLog', 'Reserved conditional cleanup statement.'],
  ['send', 'Reserved channel statement: send CHANNEL_NAME VALUE.'],
  ['receive', 'Reserved channel statement: receive OUT_NAME TYPE CHANNEL_NAME.'],
  ['lock', 'Reserved lock statement: lock MUTEX_NAME.'],
  ['unlock', 'Reserved lock statement: unlock MUTEX_NAME.'],
  ['select', 'Reserved select declaration statement.'],
  ['selectCase', 'Reserved select case statement.'],
  ['runSelect', 'Reserved select execution statement.'],
  ['startInterval', 'Interval lifecycle statement: startInterval NAME. Single-thread lowering is a no-op.'],
  ['awaitIntervalTick', 'Interval lifecycle statement: awaitIntervalTick NAME. Single-thread lowering falls through.'],
  ['workArg', 'Worker-pool argument edge: workArg WORK ARG VALUE.'],
  ['submitWork', 'Worker-pool dispatch: submitWork WORK POOL. Single-thread lowering calls the work target inline.'],
  ['awaitWork', 'Worker-pool await: awaitWork WORK. The direct-dispatch lowering has already run the work item.'],
  ['useRetry', 'Reserved policy attachment: useRetry CALL_NAME RETRY_POLICY_NAME.'],
  ['useCapability', 'Reserved policy attachment: useCapability OPERATION_OR_CALL CAPABILITY_NAME.'],
  ['set', 'Mutation statement: set VAR_NAME VALUE_NAME.'],
  ['branch', 'Control-flow statement: branch LABEL_NAME.'],
  ['branchIf', 'Control-flow statement: branchIf BOOL_VALUE LABEL_NAME. False leg falls through.'],
  ['branchIfError', 'Control-flow statement: branchIfError CALL_NAME LABEL_NAME.'],
  ['branchIfChannelClosed', 'Reserved control-flow statement for closed channel branch.'],
  ['branchSelected', 'Reserved control-flow statement for select result branch.'],
  ['returnOk', 'Return success value from Result operation.'],
  ['returnError', 'Return typed error value from Result operation.'],
  ['returnValue', 'Return plain value.'],
]);

const refinedVerbHoverText = new Map([
  ['section', 'Attention anchor: section lowerCamel.dot.path. Sections do not create scope.'],
  ['storage', 'Refined storage declaration: storage scope mutability name Type value. Makes local/module and mutable/immutable explicit.'],
  ['sharedState', 'Exceptional shared mutable state declaration. Requires owner, guard, and guard-token protected reads/writes.'],
  ['read', 'Refined guarded read action, such as read sharedState value Type slot protectedBy guardToken.'],
  ['typeParameter', 'Split generic/type argument metadata: typeParameter Alias role Type. Avoids overloaded type tails.'],
  ['operationBody', 'Operation body source contract. Use sourceTape for normal tape, or runtimeBinding, recordConstructor, intrinsic, externalDependency for bodyless targets.'],
  ['runtimeBinding', 'Runtime target metadata for a semantic operation signature. This is not an alias.'],
  ['runtimeBindingPrecondition', 'Runtime binding safety precondition. Use one line per precondition.'],
  ['runtimeBindingFailure', 'Runtime binding failure edge. Use one line per typed failure origin.'],
  ['intrinsicName', 'Intrinsic binding metadata required when operationBody is intrinsic.'],
  ['dependencyPath', 'External dependency binding metadata required when operationBody is externalDependency.'],
  ['dependencyFailure', 'External dependency failure edge.'],
  ['recordLayout', 'Record layout metadata. Split from record so layout is independently addressable.'],
  ['recordAlign', 'Record alignment metadata. Split from record so memory layout is explicit.'],
  ['recordConstructor', 'Record-constructor body metadata for a semantic constructor operation.'],
  ['recordConstructorFailure', 'Failure edge for an operation-backed record constructor.'],
  ['recordBuilder', 'Executable record builder creation. Use for large records instead of object literals.'],
  ['recordSet', 'Executable builder field assignment. Sets exactly one field in one builder.'],
  ['recordCopy', 'Executable immutable-update builder creation from an existing record.'],
  ['recordBuild', 'Executable builder finalization call. Must be run and bound like a call object.'],
  ['recordBuildFailure', 'Failure edge for one recordBuild call.'],
  ['memoryHeap', 'Memory contract: whether general heap allocation is allowed.'],
  ['memoryArena', 'Memory contract: named arena allocation allowed for this operation.'],
  ['memoryAllocationSource', 'Memory contract: names the call that justifies dynamic allocation.'],
  ['memoryStackLimit', 'Memory contract: stack bound for an operation.'],
  ['domainLiteral', 'Named typed domain literal. Prefer this for reused domain constants and platform values.'],
  ['domainLiteralSource', 'Provenance edge for platform or external literal values.'],
  ['domainLiteralTrust', 'Trust edge explaining why a domain literal may carry a trust-boundary type.'],
  ['domainLiteralValidation', 'Validation edge explaining why a domain literal may carry a validated app type.'],
  ['literal', 'Long literal declaration. Pair with size, digest, preview, source, and trust lines.'],
  ['literalBytes', 'Long literal byte-size metadata.'],
  ['literalDigest', 'Long literal digest metadata.'],
  ['literalPreview', 'Short recoverability preview for a long literal.'],
  ['literalSource', 'Source path or provenance for a long literal.'],
  ['literalTrust', 'Trust edge for a long literal.'],
  ['trustBoundary', 'Marks a type that requires validation or trusted provenance before use.'],
  ['trustBoundaryKind', 'Names the kind of trust transition.'],
  ['trustBoundaryInput', 'Names the raw input type for a trust boundary.'],
  ['trustBoundaryOutput', 'Names the trusted output type for a trust boundary.'],
  ['trustBoundaryValidator', 'Names the operation that can cross a trust boundary.'],
  ['trustBoundarySource', 'Names one allowed trusted source kind.'],
  ['typeLiteralEncoding', 'String-literal encoding contract for a type.'],
  ['typeLiteralTerminator', 'String-literal terminator contract for a type.'],
  ['jsonCodecStrict', 'JSON codec strictness edge. Split from jsonCodec to keep one fact per line.'],
  ['jsonCodecUnknownFields', 'JSON codec unknown-field policy edge.'],
  ['jsonCodecDecodeTarget', 'Generated JSON decode target for a record codec.'],
  ['jsonCodecEncodeTarget', 'Generated JSON encode target for a record codec.'],
  ['jsonCodecRequiredField', 'One required field for strict codec decoding.'],
  ['jsonCodecInput', 'Input role and type for generated codec direction.'],
  ['jsonCodecOutput', 'Output shape for generated codec direction.'],
  ['jsonCodecDecodeFailure', 'One generated decode failure edge.'],
  ['jsonCodecEncodeFailure', 'One generated encode failure edge.'],
  ['jsonCodecLimit', 'One codec limit edge such as maximumBytes or maxDepth.'],
  ['listType', 'Typed dynamic-length value collection declaration.'],
  ['listAllocator', 'Allocator metadata for a list type.'],
  ['arrayType', 'Typed fixed-length array declaration.'],
  ['arrayLength', 'Fixed array length metadata.'],
  ['sliceType', 'Borrowed view collection declaration.'],
  ['smallListType', 'Small-buffer collection declaration.'],
  ['smallListInlineCapacity', 'Inline-capacity metadata for a small list.'],
  ['smallListSpillAllocator', 'Spill allocator metadata for a small list.'],
  ['mapType', 'Typed dictionary declaration.'],
  ['mapKey', 'Map key type metadata.'],
  ['mapValue', 'Map value type metadata.'],
  ['mapAllocator', 'Map allocator metadata.'],
  ['collectionOperation', 'Collection operation contract declaration.'],
  ['collectionOperationArg', 'Required argument role for a collection operation.'],
  ['collectionOperationOutput', 'Result shape for a collection operation.'],
  ['collectionOperationFailure', 'Failure edge for a collection operation.'],
  ['collectionOperationEffect', 'Effect edge for a collection operation role.'],
  ['collectionOperationAllocation', 'Allocator edge for a collection operation.'],
  ['collectionOperationMutation', 'Mutation mode edge for a collection operation.'],
  ['collectionOperationIndexPolicy', 'Index origin and bounds policy for indexed collection operations.'],
  ['collectionOperationLengthSource', 'Length source for indexed collection operations.'],
  ['collectionOperationBorrowSource', 'Borrow source for view-producing collection operations.'],
  ['collectionOperationCapacitySource', 'Capacity source for fixed/small collection operations.'],
  ['collectionOperationSpillAllocator', 'Spill allocator edge for small collection operations.'],
  ['collectionOperationSpillFailure', 'Spill failure edge for small collection operations.'],
  ['listLiteral', 'Named literal collection declaration.'],
  ['listLiteralLength', 'Literal collection length metadata.'],
  ['listLiteralIndexBase', 'Literal collection index base metadata.'],
  ['listLiteralIndexPolicy', 'Literal collection completeness/index policy.'],
  ['listLiteralItem', 'One item in a literal collection.'],
  ['sharedStateOwner', 'Owner metadata for shared mutable state.'],
  ['sharedStateGuard', 'Guard metadata for shared mutable state.'],
  ['guardTokenSource', 'Connects a guard token to the acquire call that produced it.'],
  ['guardTokenOwner', 'Owner metadata for a guard token.'],
  ['guardTokenProtects', 'Names the shared-state slot protected by a guard token.'],
  ['guardTokenRelease', 'Connects a guard token to the cleanup that releases it.'],
  ['deferLogSink', 'Log sink metadata required for deferLog cleanup failures.'],
  ['deferRunOn', 'Cleanup lifecycle metadata: returnOk and/or returnError.'],
  ['deferOrder', 'Cleanup ordering metadata.'],
  ['deferFailurePolicy', 'Cleanup failure policy, usually logAndSuppress.'],
  ['deferConsumes', 'Resource or guard token consumed at cleanup execution.'],
  ['deferAwaitLogSink', 'Log sink metadata for awaited async cleanup.'],
  ['deferAwaitTimeout', 'Timeout bound for awaited async cleanup.'],
  ['deferWhenExitLogSink', 'Log sink metadata for conditional cleanup.'],
  ['retryMaxAttempts', 'Retry policy max-attempts edge.'],
  ['retryInitialDelay', 'Retry policy initial-delay edge.'],
  ['retryMaximumDelay', 'Retry policy maximum-delay edge.'],
  ['retryJitter', 'Retry policy jitter edge.'],
  ['group', 'Symbolic attention group. Groups are metadata, not lexical blocks or scopes.'],
  ['groupPurpose', 'Purpose metadata for a symbolic group.'],
  ['groupInput', 'Value consumed by a symbolic group.'],
  ['groupOutput', 'Value produced by a symbolic group.'],
  ['groupError', 'Raw error value produced by bindError inside a group.'],
  ['groupFailure', 'Domain failure value produced by declareFailure or makeError inside a group.'],
  ['groupTiming', 'Timing policy or duration related to a group.'],
  ['declareFailure', 'Create a no-payload domain failure value before returnError.'],
]);

refinedVerbHoverText.forEach((text, verb) => {
  verbHoverText.set(verb, text);
});

const semanticLegend = new vscode.SemanticTokensLegend([
  'agentscriptDeclarationVerb',
  'agentscriptContextVerb',
  'agentscriptActionVerb',
  'agentscriptControlVerb',
  'agentscriptRoleSuffix',
  'agentscriptPrimitiveTarget',
  'agentscriptGeneratedTarget',
  'agentscriptDomainTarget',
  'agentscriptErrorVariant',
  'agentscriptSchemaValue',
  'agentscriptOpaqueInput',
  'agentscriptDeclaredName',
  'agentscriptConstName',
  'agentscriptMutableName',
  'agentscriptCallObject',
  'agentscriptArgumentName',
  'agentscriptLabelName',
  'agentscriptEffectPath',
  'type',
  'namespace',
  'variable',
  'string',
  'number',
  'comment',
], []);

let activeDecorations = [];
let segmentColoringEnabled = true;
let segmentColorMode = 'background';
let decorationUpdateTimeout = null;
let linterEnabled = true;
let linterRunMode = 'onSave';
let linterPythonPath = 'python';
let linterConfiguredPath = '';
let linterSkipFutureSyntax = true;
let linterEngine = 'aslint';
let diagnosticCollection = null;
let lintStatusBarItem = null;
const lintUpdateTimeouts = new Map();
const runningLintProcesses = new Map();

const futureSyntaxLinterSkipVerbs = new Set([
  'section',
  'storage',
  'sharedState',
  'operationBody',
  'memoryHeap',
  'memoryArena',
  'memoryAllocationSource',
  'memoryStackLimit',
  'runtimeBinding',
  'runtimeBindingPrecondition',
  'runtimeBindingFailure',
  'intrinsicName',
  'dependencyPath',
  'dependencyFailure',
  'recordConstructor',
  'recordConstructorFailure',
  'recordBuildFailure',
  'typeParameter',
  'typeLiteralEncoding',
  'typeLiteralTerminator',
  'trustBoundary',
  'trustBoundaryKind',
  'trustBoundaryInput',
  'trustBoundaryOutput',
  'trustBoundaryValidator',
  'trustBoundarySource',
  'domainLiteral',
  'domainLiteralSource',
  'domainLiteralTrust',
  'domainLiteralValidation',
  'literal',
  'literalBytes',
  'literalDigest',
  'literalPreview',
  'literalSource',
  'literalTrust',
  'jsonCodec',
  'jsonCodecStrict',
  'jsonCodecUnknownFields',
  'jsonCodecDecodeTarget',
  'jsonCodecEncodeTarget',
  'jsonCodecRequiredField',
  'jsonCodecInput',
  'jsonCodecOutput',
  'jsonCodecDecodeFailure',
  'jsonCodecEncodeFailure',
  'jsonCodecLimit',
  'recordBuilder',
  'recordSet',
  'recordCopy',
  'recordBuild',
  'listType',
  'listAllocator',
  'arrayType',
  'arrayLength',
  'sliceType',
  'smallListType',
  'smallListInlineCapacity',
  'smallListSpillAllocator',
  'mapType',
  'mapKey',
  'mapValue',
  'mapAllocator',
  'listLiteral',
  'listLiteralLength',
  'listLiteralIndexBase',
  'listLiteralIndexPolicy',
  'listLiteralItem',
  'collectionOperation',
  'collectionOperationArg',
  'collectionOperationOutput',
  'collectionOperationFailure',
  'collectionOperationEffect',
  'collectionOperationAllocation',
  'collectionOperationMutation',
  'collectionOperationIndexPolicy',
  'collectionOperationLengthSource',
  'collectionOperationBorrowSource',
  'collectionOperationCapacitySource',
  'collectionOperationSpillAllocator',
  'collectionOperationSpillFailure',
  'group',
  'groupPurpose',
  'groupInput',
  'groupOutput',
  'groupError',
  'groupFailure',
  'groupTiming',
  'guardTokenSource',
  'guardTokenOwner',
  'guardTokenProtects',
  'guardTokenRelease',
  'deferLog',
  'deferLogSink',
  'deferRunOn',
  'deferOrder',
  'deferFailurePolicy',
  'deferConsumes',
  'deferAwaitLog',
  'deferAwaitLogSink',
  'deferAwaitTimeout',
  'deferWhenExitLog',
  'deferWhenExitLogSink',
  'interval',
  'startInterval',
  'awaitIntervalTick',
  'workerPool',
  'work',
  'workArg',
  'submitWork',
  'awaitWork',
  'read',
]);

const verbStyles = {
  declaration: { color: '#FF7B72', fontWeight: '600' },
  context: { color: '#7EE787', fontWeight: '600' },
  action: { color: '#DCDCAA', fontWeight: '600' },
  control: { color: '#79C0FF', fontWeight: '600' },
  unknown: {
    color: '#FF6B6B',
    fontWeight: '700',
    textDecoration: 'underline wavy #FF6B6B',
  },
};

const classifyVerb = (verb) => {
  if (declarationVerbs.has(verb)) {
    return 'declaration';
  }

  if (contextVerbs.has(verb)) {
    return 'context';
  }

  if (actionVerbs.has(verb)) {
    return 'action';
  }

  if (controlVerbs.has(verb)) {
    return 'control';
  }

  return 'unknown';
};

const classifyLine = (lineText) => {
  const trimmedLine = lineText.trim();

  if (trimmedLine.length === 0) {
    return null;
  }

  if (trimmedLine.startsWith('#')) {
    return 'comment';
  }

  const verb = trimmedLine.split(/\s+/, 1)[0];
  return classifyVerb(verb);
};

const createDecorationOptions = (backgroundColor, overviewRulerColor) => {
  const options = {
    isWholeLine: true,
  };

  if (segmentColorMode === 'background' || segmentColorMode === 'both') {
    options.backgroundColor = backgroundColor;
  }

  if (segmentColorMode === 'overview' || segmentColorMode === 'both') {
    options.overviewRulerColor = overviewRulerColor;
    options.overviewRulerLane = vscode.OverviewRulerLane.Left;
  }

  return options;
};

const createDecorations = () => ({
  declaration: vscode.window.createTextEditorDecorationType(createDecorationOptions(
    'rgba(197, 134, 192, 0.045)',
    'rgba(197, 134, 192, 0.90)'
  )),
  context: vscode.window.createTextEditorDecorationType(createDecorationOptions(
    'rgba(78, 201, 176, 0.050)',
    'rgba(78, 201, 176, 0.90)'
  )),
  action: vscode.window.createTextEditorDecorationType(createDecorationOptions(
    'rgba(220, 220, 170, 0.040)',
    'rgba(220, 220, 170, 0.90)'
  )),
  control: vscode.window.createTextEditorDecorationType(createDecorationOptions(
    'rgba(86, 156, 214, 0.055)',
    'rgba(86, 156, 214, 0.90)'
  )),
  comment: vscode.window.createTextEditorDecorationType(createDecorationOptions(
    'rgba(106, 153, 85, 0.040)',
    'rgba(106, 153, 85, 0.80)'
  )),
  unknown: vscode.window.createTextEditorDecorationType(createDecorationOptions(
    'rgba(244, 71, 71, 0.095)',
    'rgba(244, 71, 71, 0.90)'
  )),
});

let decorations = createDecorations();

const createVerbDecorations = () => ({
  declaration: vscode.window.createTextEditorDecorationType(verbStyles.declaration),
  context: vscode.window.createTextEditorDecorationType(verbStyles.context),
  action: vscode.window.createTextEditorDecorationType(verbStyles.action),
  control: vscode.window.createTextEditorDecorationType(verbStyles.control),
  unknown: vscode.window.createTextEditorDecorationType(verbStyles.unknown),
});

let verbDecorations = createVerbDecorations();

const disposeDecorations = () => {
  Object.keys(decorations).forEach((key) => {
    decorations[key].dispose();
  });

  Object.keys(verbDecorations).forEach((key) => {
    verbDecorations[key].dispose();
  });
};

const clearDecorations = (editor) => {
  Object.keys(decorations).forEach((key) => {
    editor.setDecorations(decorations[key], []);
  });

  Object.keys(verbDecorations).forEach((key) => {
    editor.setDecorations(verbDecorations[key], []);
  });
};

const updateSegmentDecorations = (editor) => {
  if (!editor || editor.document.languageId !== 'agentscript') {
    return;
  }

  if (!segmentColoringEnabled) {
    clearDecorations(editor);
    return;
  }

  const rangesByKind = {
    declaration: [],
    context: [],
    action: [],
    control: [],
    comment: [],
    unknown: [],
  };
  const verbRangesByKind = {
    declaration: [],
    context: [],
    action: [],
    control: [],
    unknown: [],
  };

  for (let lineIndex = 0; lineIndex < editor.document.lineCount; lineIndex += 1) {
    const line = editor.document.lineAt(lineIndex);
    const kind = classifyLine(line.text);

    if (!kind || !rangesByKind[kind]) {
      continue;
    }

    rangesByKind[kind].push(line.range);

    if (kind !== 'comment') {
      const verbStart = line.firstNonWhitespaceCharacterIndex;
      const verbText = line.text.slice(verbStart).split(/\s+/, 1)[0];

      if (verbText && verbRangesByKind[kind]) {
        verbRangesByKind[kind].push(new vscode.Range(
          lineIndex,
          verbStart,
          lineIndex,
          verbStart + verbText.length
        ));
      }
    }
  }

  Object.keys(rangesByKind).forEach((kind) => {
    editor.setDecorations(decorations[kind], rangesByKind[kind]);
  });

  Object.keys(verbRangesByKind).forEach((kind) => {
    editor.setDecorations(verbDecorations[kind], verbRangesByKind[kind]);
  });
};

const scheduleDecorationUpdate = (editor) => {
  if (decorationUpdateTimeout) {
    clearTimeout(decorationUpdateTimeout);
  }

  decorationUpdateTimeout = setTimeout(() => {
    updateSegmentDecorations(editor || vscode.window.activeTextEditor);
  }, 75);
};

const tokenizeLine = (lineText) => {
  const tokens = [];
  const tokenPattern = /"([^"\\]|\\.)*"|#.*$|\S+/g;
  let match;

  while ((match = tokenPattern.exec(lineText)) !== null) {
    tokens.push({
      text: match[0],
      start: match.index,
      length: match[0].length,
    });
  }

  return tokens;
};

const isDomainTarget = (text) => {
  const parts = text.split('.');
  return parts.length === 2
    && /^[A-Z][A-Za-z0-9_]*$/.test(parts[0])
    && domainMethods.has(parts[1]);
};

const operationReferenceVerbs = new Set([
  'input', 'output', 'effect', 'memory', 'memoryHeap', 'memoryArena',
  'memoryAllocationSource', 'memoryStackLimit', 'async', 'operationBody',
  'purpose', 'invariant', 'warning', 'failure', 'guarantee', 'security',
  'timing', 'observability', 'authority', 'runtimeBinding',
  'runtimeBindingPrecondition', 'runtimeBindingFailure', 'intrinsicName',
  'dependencyPath', 'dependencyFailure', 'recordConstructor',
  'recordConstructorFailure', 'jsonCodecStrict', 'jsonCodecUnknownFields',
  'jsonCodecDecodeTarget', 'jsonCodecEncodeTarget', 'jsonCodecRequiredField',
  'jsonCodecInput', 'jsonCodecOutput', 'jsonCodecDecodeFailure',
  'jsonCodecEncodeFailure', 'jsonCodecLimit', 'typeParameter',
  'typeLiteralEncoding', 'typeLiteralTerminator', 'trustBoundary',
  'trustBoundaryKind', 'trustBoundaryInput', 'trustBoundaryOutput',
  'trustBoundaryValidator', 'trustBoundarySource', 'domainLiteralSource',
  'domainLiteralTrust', 'domainLiteralValidation', 'literalBytes',
  'literalDigest', 'literalPreview', 'literalSource', 'literalTrust',
  'sharedStateOwner', 'sharedStateGuard', 'guardTokenSource',
  'guardTokenOwner', 'guardTokenProtects', 'guardTokenRelease',
  'listAllocator', 'arrayLength', 'smallListInlineCapacity',
  'smallListSpillAllocator', 'mapKey', 'mapValue', 'mapAllocator',
  'listLiteralLength', 'listLiteralIndexBase', 'listLiteralIndexPolicy',
  'listLiteralItem', 'collectionOperationArg', 'collectionOperationOutput',
  'collectionOperationFailure', 'collectionOperationEffect',
  'collectionOperationAllocation', 'collectionOperationMutation',
  'collectionOperationIndexPolicy', 'collectionOperationLengthSource',
  'collectionOperationBorrowSource', 'collectionOperationCapacitySource',
  'collectionOperationSpillAllocator', 'collectionOperationSpillFailure',
  'retryMaxAttempts', 'retryInitialDelay', 'retryMaximumDelay', 'retryJitter',
  'groupPurpose', 'groupInput', 'groupOutput', 'groupError', 'groupFailure',
  'groupTiming', 'deferLogSink', 'deferRunOn', 'deferOrder',
  'deferFailurePolicy', 'deferConsumes', 'deferAwaitLogSink',
  'deferAwaitTimeout', 'deferWhenExitLogSink',
]);

const operationMetadataVerbs = new Set([
  'input', 'output', 'effect', 'memory', 'memoryHeap', 'memoryArena',
  'memoryAllocationSource', 'memoryStackLimit', 'async', 'operationBody',
  'purpose', 'invariant', 'warning', 'failure', 'guarantee', 'security',
  'timing', 'observability', 'authority', 'runtimeBinding',
  'runtimeBindingPrecondition', 'runtimeBindingFailure', 'intrinsicName',
  'dependencyPath', 'dependencyFailure', 'recordConstructor',
  'recordConstructorFailure', 'recordBuildFailure',
]);

const operationHoverReferencePositions = new Map([
  ['operation', 1],
  ['entry', 2],
  ['route', 4],
  ['routeMiddleware', 3],
  ['trustBoundaryValidator', 2],
  ['jsonCodecDecodeTarget', 2],
  ['jsonCodecEncodeTarget', 2],
  ['guardTokenRelease', 2],
  ['defer', 2],
  ['deferLog', 2],
  ['deferAwaitLog', 2],
  ['deferWhenExitLog', 3],
  ['testCovers', 2],
]);

const namedDeclarationVerbs = new Set([
  'project', 'operation', 'webServer', 'record', 'enum', 'error', 'codec',
  'jsonCodec', 'validator', 'mapper', 'adapter', 'boundary', 'policy',
  'errorPolicy', 'retryPolicy', 'timeoutBudget', 'resource', 'capability',
  'mutex', 'shared', 'channel', 'section', 'domainLiteral', 'literal',
  'listLiteral', 'listType', 'arrayType', 'sliceType', 'smallListType',
  'mapType', 'collectionOperation', 'interval', 'workerPool', 'work',
]);

const singleCallReferenceVerbs = new Set([
  'run', 'start', 'await', 'timeout', 'cancelOn', 'ignoreOk', 'ignoreValue',
  'useRetry', 'recordBuild',
]);

const branchLabelPositions = new Map([
  ['branch', 1],
  ['branchIf', 2],
  ['branchIfError', 2],
  ['branchIfGroupError', 2],
  ['branchIfChannelClosed', 2],
  ['branchSelected', 3],
]);

const isLowerQualifiedName = (text) => /^[a-z][A-Za-z0-9_]*(?:\.[a-zA-Z_][A-Za-z0-9_]*)+$/.test(text);

const operationMetadataCache = new WeakMap();
const symbolIndexCache = new WeakMap();

const ensureOperationMetadataEntry = (operations, name) => {
  if (!operations.has(name)) {
    operations.set(name, {
      name,
      section: null,
      declarationLine: null,
      declarationText: null,
      metadata: [],
    });
  }

  return operations.get(name);
};

const buildOperationMetadataIndex = (document) => {
  const operations = new Map();
  let currentSection = null;

  for (let lineIndex = 0; lineIndex < document.lineCount; lineIndex += 1) {
    const lineText = document.lineAt(lineIndex).text;
    const tokens = tokenizeLine(lineText);

    if (tokens.length === 0 || tokens[0].text.startsWith('#')) {
      continue;
    }

    const verb = tokens[0].text;

    if (verb === 'section' && tokens[1]) {
      currentSection = tokens.slice(1).map((token) => token.text).join(' ');
      continue;
    }

    if (verb === 'operation' && tokens[1]) {
      const entry = ensureOperationMetadataEntry(operations, tokens[1].text);
      entry.section = currentSection;
      entry.declarationLine = lineIndex + 1;
      entry.declarationText = lineText.trim();
      continue;
    }

    if (operationMetadataVerbs.has(verb) && tokens[1]) {
      const entry = ensureOperationMetadataEntry(operations, tokens[1].text);

      if (!entry.section) {
        entry.section = currentSection;
      }

      entry.metadata.push({
        line: lineIndex + 1,
        text: lineText.trim(),
      });
    }
  }

  return operations;
};

const getOperationMetadataIndex = (document) => {
  const cached = operationMetadataCache.get(document);

  if (cached && cached.version === document.version) {
    return cached.operations;
  }

  const operations = buildOperationMetadataIndex(document);
  operationMetadataCache.set(document, {
    version: document.version,
    operations,
  });
  return operations;
};

const isSymbolLike = (text) => (
  /^[A-Za-z_][A-Za-z0-9_.]*$/.test(text)
  && !text.startsWith('c.')
  && !primitiveTargets.has(text)
  && !generatedTargetPattern.test(text)
  && !cRuntimeTargetPattern.test(text)
);

const ensureSymbolEntry = (symbols, name) => {
  if (!symbols.has(name)) {
    symbols.set(name, {
      name,
      declarations: [],
    });
  }

  return symbols.get(name);
};

const addSymbolDeclaration = (symbols, name, declaration) => {
  if (!name || name === '?' || name.startsWith('"') || /^-?\d+$/.test(name)) {
    return null;
  }

  const entry = ensureSymbolEntry(symbols, name);
  entry.declarations.push(declaration);
  return declaration;
};

const buildDocumentSymbolIndex = (document) => {
  const symbols = new Map();
  const calls = new Map();
  const lineOperations = new Map();
  let currentOperation = null;

  const declarationBase = (kind, tokens, lineIndex, extra = {}) => ({
    kind,
    line: lineIndex + 1,
    lineIndex,
    text: document.lineAt(lineIndex).text.trim(),
    operation: currentOperation,
    ...extra,
  });

  for (let lineIndex = 0; lineIndex < document.lineCount; lineIndex += 1) {
    const lineText = document.lineAt(lineIndex).text;
    const tokens = tokenizeLine(lineText);

    if (tokens.length === 0 || tokens[0].text.startsWith('#')) {
      lineOperations.set(lineIndex, currentOperation);
      continue;
    }

    const verb = tokens[0].text;

    if (verb === 'operation' && tokens[1]) {
      currentOperation = tokens[1].text;
    }

    lineOperations.set(lineIndex, currentOperation);

    switch (verb) {
      case 'operation':
        addSymbolDeclaration(symbols, tokenText(tokens, 1), declarationBase('operation', tokens, lineIndex, {
          name: tokenText(tokens, 1),
        }));
        break;

      case 'input':
        addSymbolDeclaration(symbols, tokenText(tokens, 2), declarationBase('input parameter', tokens, lineIndex, {
          name: tokenText(tokens, 2),
          owner: tokenText(tokens, 1),
          type: tokenText(tokens, 3),
        }));
        break;

      case 'const':
        addSymbolDeclaration(symbols, tokenText(tokens, 1), declarationBase('constant', tokens, lineIndex, {
          name: tokenText(tokens, 1),
          type: tokenText(tokens, 2),
          value: tokenTailText(tokens, 3),
          mutability: 'immutable',
        }));
        break;

      case 'var':
        addSymbolDeclaration(symbols, tokenText(tokens, 1), declarationBase('mutable variable', tokens, lineIndex, {
          name: tokenText(tokens, 1),
          type: tokenText(tokens, 2),
          value: tokenTailText(tokens, 3),
          mutability: 'mutable',
        }));
        break;

      case 'storage':
        addSymbolDeclaration(symbols, tokenText(tokens, 3), declarationBase('storage binding', tokens, lineIndex, {
          name: tokenText(tokens, 3),
          scope: tokenText(tokens, 1),
          mutability: tokenText(tokens, 2),
          type: tokenText(tokens, 4),
          value: tokenTailText(tokens, 5),
        }));
        break;

      case 'sharedState':
        addSymbolDeclaration(symbols, tokenText(tokens, 3), declarationBase('shared state', tokens, lineIndex, {
          name: tokenText(tokens, 3),
          scope: tokenText(tokens, 1),
          mutability: tokenText(tokens, 2),
          type: tokenText(tokens, 4),
          value: tokenTailText(tokens, 5),
        }));
        break;

      case 'domainLiteral':
      case 'literal':
      case 'listLiteral':
        addSymbolDeclaration(symbols, tokenText(tokens, 1), declarationBase(readableVerbName(verb).toLowerCase(), tokens, lineIndex, {
          name: tokenText(tokens, 1),
          type: tokenText(tokens, 2),
          value: tokenTailText(tokens, 3),
        }));
        break;

      case 'type':
      case 'record':
      case 'enum':
      case 'error':
      case 'dependency':
      case 'codec':
      case 'jsonCodec':
      case 'validator':
      case 'mapper':
      case 'adapter':
      case 'boundary':
      case 'policy':
      case 'errorPolicy':
      case 'retryPolicy':
      case 'timeoutBudget':
      case 'resource':
      case 'capability':
      case 'webServer':
      case 'interval':
      case 'workerPool':
      case 'group':
      case 'listType':
      case 'arrayType':
      case 'sliceType':
      case 'smallListType':
      case 'mapType':
      case 'collectionOperation':
      case 'mutex':
      case 'shared':
      case 'channel':
        addSymbolDeclaration(symbols, tokenText(tokens, 1), declarationBase(readableVerbName(verb).toLowerCase(), tokens, lineIndex, {
          name: tokenText(tokens, 1),
          details: tokenTailText(tokens, 2),
        }));
        break;

      case 'field':
        addSymbolDeclaration(symbols, tokenText(tokens, 2), declarationBase('record field', tokens, lineIndex, {
          name: tokenText(tokens, 2),
          owner: tokenText(tokens, 1),
          type: tokenText(tokens, 3),
        }));
        break;

      case 'enumCase':
      case 'errorCase':
        addSymbolDeclaration(symbols, tokenText(tokens, 2), declarationBase(readableVerbName(verb).toLowerCase(), tokens, lineIndex, {
          name: tokenText(tokens, 2),
          owner: tokenText(tokens, 1),
          value: tokenTailText(tokens, 3),
        }));
        break;

      case 'label':
        addSymbolDeclaration(symbols, tokenText(tokens, 1), declarationBase('label', tokens, lineIndex, {
          name: tokenText(tokens, 1),
        }));
        break;

      case 'call': {
        const callDeclaration = addSymbolDeclaration(symbols, tokenText(tokens, 1), declarationBase('call object', tokens, lineIndex, {
          name: tokenText(tokens, 1),
          target: tokenText(tokens, 2),
          args: [],
          resultBindings: [],
        }));

        if (callDeclaration) {
          calls.set(callDeclaration.name, callDeclaration);
        }
        break;
      }

      case 'arg': {
        const callDeclaration = calls.get(tokenText(tokens, 1));

        if (callDeclaration) {
          callDeclaration.args.push({
            role: tokenText(tokens, 2),
            value: tokenText(tokens, 3),
            line: lineIndex + 1,
          });
        }
        break;
      }

      case 'bind':
      case 'bindOk':
      case 'bindError': {
        const bindingKind = verb === 'bindError' ? 'bound error' : 'bound value';
        addSymbolDeclaration(symbols, tokenText(tokens, 1), declarationBase(bindingKind, tokens, lineIndex, {
          name: tokenText(tokens, 1),
          type: tokenText(tokens, 2),
          sourceCall: tokenText(tokens, 3),
        }));

        const callDeclaration = calls.get(tokenText(tokens, 3));

        if (callDeclaration) {
          callDeclaration.resultBindings.push({
            verb,
            name: tokenText(tokens, 1),
            type: tokenText(tokens, 2),
            line: lineIndex + 1,
          });
        }
        break;
      }

      case 'fieldGet':
        addSymbolDeclaration(symbols, tokenText(tokens, 1), declarationBase('derived value', tokens, lineIndex, {
          name: tokenText(tokens, 1),
          type: tokenText(tokens, 2),
          value: tokenTailText(tokens, 3),
        }));
        break;

      case 'read':
        if (tokens[1] && tokens[1].text === 'sharedState') {
          addSymbolDeclaration(symbols, tokenText(tokens, 2), declarationBase('derived value', tokens, lineIndex, {
            name: tokenText(tokens, 2),
            type: tokenText(tokens, 3),
            value: tokenText(tokens, 4),
          }));
        }
        break;

      case 'recordBuilder':
      case 'recordCopy':
        addSymbolDeclaration(symbols, tokenText(tokens, 1), declarationBase('record builder', tokens, lineIndex, {
          name: tokenText(tokens, 1),
          type: tokenText(tokens, 2),
          value: tokenTailText(tokens, 3),
        }));
        break;

      case 'recordBuild': {
        const buildDeclaration = addSymbolDeclaration(symbols, tokenText(tokens, 1), declarationBase('record build call', tokens, lineIndex, {
          name: tokenText(tokens, 1),
          target: 'recordBuild',
          value: tokenText(tokens, 2),
          args: [],
          resultBindings: [],
        }));

        if (buildDeclaration) {
          calls.set(buildDeclaration.name, buildDeclaration);
        }
        break;
      }

      case 'makeError':
      case 'declareFailure':
        addSymbolDeclaration(symbols, tokenText(tokens, 1), declarationBase('failure value', tokens, lineIndex, {
          name: tokenText(tokens, 1),
          type: tokenText(tokens, 2).split('.')[0],
          value: tokenTailText(tokens, 2),
        }));
        break;

      case 'work':
        addSymbolDeclaration(symbols, tokenText(tokens, 1), declarationBase('work item', tokens, lineIndex, {
          name: tokenText(tokens, 1),
          target: tokenText(tokens, 3),
        }));
        break;

      default:
        break;
    }
  }

  return {
    symbols,
    lineOperations,
  };
};

const getDocumentSymbolIndex = (document) => {
  const cached = symbolIndexCache.get(document);

  if (cached && cached.version === document.version) {
    return cached.index;
  }

  const index = buildDocumentSymbolIndex(document);
  symbolIndexCache.set(document, {
    version: document.version,
    index,
  });
  return index;
};

const operationHoverNameForToken = (text, tokenIndex, tokens) => {
  if (tokenIndex === 0 || text.startsWith('#') || text.startsWith('"')) {
    return null;
  }

  const verb = tokens && tokens[0] ? tokens[0].text : '';

  if (operationMetadataVerbs.has(verb) && tokenIndex === 1) {
    return text;
  }

  if (verb === 'call' && tokenIndex === 2) {
    return text;
  }

  if (verb === 'work' && tokenIndex === 3 && tokens[2] && tokens[2].text === 'target') {
    return text;
  }

  if (operationHoverReferencePositions.get(verb) === tokenIndex) {
    return text;
  }

  return null;
};

const contextTokenTypeForSymbol = (text, index, tokens) => {
  const verb = tokens && tokens[0] ? tokens[0].text : '';

  if (index === 0) {
    return null;
  }

  if (verb === 'const' && index === 1) {
    return 'agentscriptConstName';
  }

  if (verb === 'var' && index === 1) {
    return 'agentscriptMutableName';
  }

  if (verb === 'type' && index === 1) {
    return 'agentscriptDeclaredName';
  }

  if ((verb === 'enumCase' || verb === 'errorCase') && index === 2) {
    return 'agentscriptDeclaredName';
  }

  if ((verb === 'field' || verb === 'fieldDefault' || verb === 'fieldInvariant') && index === 2) {
    return 'agentscriptArgumentName';
  }

  if (verb === 'typeParameter' && index === 2 && (text === 'success' || text === 'error')) {
    return 'agentscriptSchemaValue';
  }

  if (verb === 'storage' && index === 3) {
    return tokens[2] && tokens[2].text === 'mutable'
      ? 'agentscriptMutableName'
      : 'agentscriptConstName';
  }

  if (verb === 'sharedState' && index === 3) {
    return 'agentscriptMutableName';
  }

  if (verb === 'set' && index === 1 && !['local', 'module', 'sharedState'].includes(text)) {
    return 'agentscriptMutableName';
  }

  if (verb === 'set' && index === 2 && tokens[1] && ['local', 'module', 'sharedState'].includes(tokens[1].text)) {
    return 'agentscriptMutableName';
  }

  if (verb === 'read' && index === 2 && tokens[1] && tokens[1].text === 'sharedState') {
    return 'agentscriptDeclaredName';
  }

  if (verb === 'label' && index === 1) {
    return 'agentscriptLabelName';
  }

  if (branchLabelPositions.get(verb) === index) {
    return 'agentscriptLabelName';
  }

  if (verb === 'call' && index === 1) {
    return 'agentscriptCallObject';
  }

  if (verb === 'recordBuild' && index === 1) {
    return 'agentscriptCallObject';
  }

  if (verb === 'recordBuildFailure' && index === 1) {
    return 'agentscriptCallObject';
  }

  if (verb === 'memoryAllocationSource' && index === 2) {
    return 'agentscriptCallObject';
  }

  if (verb === 'recordBuilder' && index === 1) {
    return 'agentscriptDeclaredName';
  }

  if (verb === 'arg' && index === 1) {
    return 'agentscriptCallObject';
  }

  if (verb === 'arg' && index === 2) {
    return 'agentscriptArgumentName';
  }

  if (singleCallReferenceVerbs.has(verb) && index === 1) {
    return 'agentscriptCallObject';
  }

  if ((verb === 'bind' || verb === 'bindOk' || verb === 'bindError') && index === 3) {
    return 'agentscriptCallObject';
  }

  if ((verb === 'bind' || verb === 'bindOk') && index === 1) {
    return 'agentscriptConstName';
  }

  if (verb === 'bindError' && index === 1) {
    return 'agentscriptMutableName';
  }

  if ((verb === 'makeError' || verb === 'declareFailure') && index === 1) {
    return 'agentscriptMutableName';
  }

  if (verb === 'input' && index === 2) {
    return 'agentscriptArgumentName';
  }

  if (verb === 'fieldGet' && index === 1) {
    return 'agentscriptConstName';
  }

  if (verb === 'fieldGet' && index === 4) {
    return 'agentscriptArgumentName';
  }

  if (verb === 'fieldSet' && index === 1) {
    return 'agentscriptConstName';
  }

  if (verb === 'fieldSet' && index === 4) {
    return 'agentscriptArgumentName';
  }

  if (verb === 'recordCopy' && index === 1) {
    return 'agentscriptDeclaredName';
  }

  if (verb === 'workArg' && index === 1) {
    return 'agentscriptDeclaredName';
  }

  if (verb === 'workArg' && index === 2) {
    return 'agentscriptArgumentName';
  }

  if (verb === 'work' && index === 2 && text === 'target') {
    return 'agentscriptSchemaValue';
  }

  if (verb === 'work' && index === 3 && tokens[2] && tokens[2].text === 'target') {
    return 'agentscriptDeclaredName';
  }

  if ((verb === 'startInterval' || verb === 'awaitIntervalTick' || verb === 'awaitWork') && index === 1) {
    return 'agentscriptDeclaredName';
  }

  if (verb === 'submitWork' && (index === 1 || index === 2)) {
    return 'agentscriptDeclaredName';
  }

  if (verb === 'recordSet' && index === 2) {
    return 'agentscriptArgumentName';
  }

  if (verb === 'guardTokenSource' && index === 2) {
    return 'agentscriptCallObject';
  }

  if (verb === 'guardTokenRelease' && index === 2) {
    return 'agentscriptDeclaredName';
  }

  if (namedDeclarationVerbs.has(verb) && index === 1) {
    return 'agentscriptDeclaredName';
  }

  if (operationReferenceVerbs.has(verb) && index === 1) {
    return 'agentscriptDeclaredName';
  }

  if (verb === 'collectionOperationArg' && index === 2) {
    return 'agentscriptArgumentName';
  }

  if (verb === 'jsonCodecInput' && index === 3) {
    return 'agentscriptArgumentName';
  }

  if (verb === 'jsonCodecRequiredField' && index === 2) {
    return 'agentscriptArgumentName';
  }

  if (verb.startsWith('group') && index === 1) {
    return 'agentscriptDeclaredName';
  }

  if ((verb.startsWith('defer') || verb === 'guardTokenRelease') && index === 1) {
    return 'agentscriptDeclaredName';
  }

  if ((verb === 'deferLog' || verb === 'deferAwaitLog') && index === 2) {
    return 'agentscriptDeclaredName';
  }

  if (verb === 'deferWhenExitLog' && index === 3) {
    return 'agentscriptDeclaredName';
  }

  if ((verb === 'deferLogSink' || verb === 'deferAwaitLogSink' || verb === 'deferWhenExitLogSink') && index === 2 && isLowerQualifiedName(text)) {
    return 'agentscriptEffectPath';
  }

  if ((verb === 'effect' || verb === 'dependencyEffect') && index >= 3 && /^[a-z][A-Za-z0-9_]*(?:\.[a-zA-Z_][A-Za-z0-9_]*)*$/.test(text)) {
    return 'agentscriptEffectPath';
  }

  if ((verb === 'runtimeBinding' || verb === 'dependencyPath' || verb === 'intrinsicName') && index === 2 && isLowerQualifiedName(text)) {
    return 'agentscriptEffectPath';
  }

  if (verb === 'collectionOperationEffect' && index === 3 && /^[a-z][A-Za-z0-9_]*(?:\.[a-zA-Z_][A-Za-z0-9_]*)*$/.test(text)) {
    return 'agentscriptEffectPath';
  }

  if ((verb === 'capability' || verb === 'authority') && index === 2 && isLowerQualifiedName(text)) {
    return 'agentscriptEffectPath';
  }

  return null;
};

const domainTargetHoverText = (text) => {
  const methodName = text.split('.')[1];

  if (methodName && methodName.startsWith('checkedMultiply')) {
    return 'AST.md: checked domain multiply lowers to `math.checkedMultiplyI64`; it is fallible and should use `bindOk`, `bindError`, and `branchIfError`.';
  }

  if (methodName === 'square') {
    return 'AST.md: domain `square` is a semantic method for multiplying a value by itself while keeping the source domain context visible.';
  }

  return 'AST.md: `TypeName.methodName` lowers to an underlying primitive based on the alias type while preserving domain context in source.';
};

const tokenTypeForSymbol = (text, index, tokens) => {
  if (index === 0) {
    const classification = classifyVerb(text);

    if (classification === 'declaration') {
      return 'agentscriptDeclarationVerb';
    }

    if (classification === 'context') {
      return 'agentscriptContextVerb';
    }

    if (classification === 'action') {
      return 'agentscriptActionVerb';
    }

    if (classification === 'control') {
      return 'agentscriptControlVerb';
    }
  }

  if (text.startsWith('#')) {
    return 'comment';
  }

  if (text.startsWith('"')) {
    return 'string';
  }

  if (/^-?\d+$/.test(text)) {
    return 'number';
  }

  const contextTokenType = contextTokenTypeForSymbol(text, index, tokens);

  if (contextTokenType) {
    return contextTokenType;
  }

  if (schemaValues.has(text)) {
    return 'agentscriptSchemaValue';
  }

  if (opaqueInputs.has(text)) {
    return 'agentscriptOpaqueInput';
  }

  if (primitiveTargets.has(text)) {
    return 'agentscriptPrimitiveTarget';
  }

  if (cRuntimeTargetPattern.test(text)) {
    return 'agentscriptPrimitiveTarget';
  }

  if (generatedTargetPattern.test(text)) {
    return 'agentscriptGeneratedTarget';
  }

  if (isDomainTarget(text)) {
    return 'agentscriptDomainTarget';
  }

  if (/^[A-Z][A-Za-z0-9_]*\.[A-Z][A-Za-z0-9_]*$/.test(text)) {
    return 'agentscriptErrorVariant';
  }

  if (tokens && tokens[0] && tokens[0].text === 'call' && index === 2) {
    return 'namespace';
  }

  if (/^[A-Z][A-Za-z0-9_]*$/.test(text)) {
    return 'type';
  }

  if (/^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$/.test(text)) {
    return 'namespace';
  }

  if (/^[a-z][A-Za-z0-9_]*$/.test(text)) {
    return 'variable';
  }

  return null;
};

const roleSuffixBaseTokenTypes = new Set([
  'agentscriptDeclaredName',
  'agentscriptConstName',
  'agentscriptMutableName',
  'agentscriptCallObject',
  'agentscriptArgumentName',
  'agentscriptLabelName',
  'variable',
]);

const canSplitRoleSuffix = (tokenType) => roleSuffixBaseTokenTypes.has(tokenType);

const provideDocumentSemanticTokens = (document) => {
  const builder = new vscode.SemanticTokensBuilder(semanticLegend);

  for (let lineIndex = 0; lineIndex < document.lineCount; lineIndex += 1) {
    const lineText = document.lineAt(lineIndex).text;
    const tokens = tokenizeLine(lineText);

    tokens.forEach((token, tokenIndex) => {
      const tokenType = tokenTypeForSymbol(token.text, tokenIndex, tokens);
      const suffixMatch = token.text.match(roleSuffixPattern);

      if (
        tokenIndex > 0
        && suffixMatch
        && /^[a-z][A-Za-z0-9_]*$/.test(token.text)
        && canSplitRoleSuffix(tokenType)
      ) {
        const suffixStart = token.start + token.text.length - suffixMatch[0].length;

        if (suffixStart > token.start) {
          builder.push(lineIndex, token.start, suffixStart - token.start, tokenType || 'variable', []);
        }

        builder.push(lineIndex, suffixStart, suffixMatch[0].length, 'agentscriptRoleSuffix', []);
        return;
      }

      if (tokenType) {
        builder.push(lineIndex, token.start, token.length, tokenType, []);
      }
    });
  }

  return builder.build();
};

const registerSemanticTokens = (context) => {
  const provider = {
    provideDocumentSemanticTokens,
  };

  context.subscriptions.push(
    vscode.languages.registerDocumentSemanticTokensProvider(
      { language: 'agentscript' },
      provider,
      semanticLegend
    )
  );
};

const getTokenAtPosition = (document, position) => {
  const lineText = document.lineAt(position.line).text;
  const tokens = tokenizeLine(lineText);

  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    const tokenEnd = token.start + token.length;

    if (position.character >= token.start && position.character <= tokenEnd) {
      return {
        token,
        tokenIndex: index,
        tokens,
      };
    }
  }

  return null;
};

const markdownHover = (title, body) => {
  const markdown = new vscode.MarkdownString();
  markdown.appendMarkdown(`**${title}**\n\n`);
  markdown.appendMarkdown(body);
  return new vscode.Hover(markdown);
};

const inlineCode = (value) => {
  const text = value === undefined || value === null || value === '' ? '?' : String(value);
  return `\`${text.replace(/`/g, "'")}\``;
};

const tokenText = (tokens, index, fallback = '?') => (
  tokens[index] ? tokens[index].text : fallback
);

const tokenTailText = (tokens, startIndex) => (
  tokens.slice(startIndex).map((token) => token.text).join(' ') || '?'
);

const readableVerbName = (verb) => (
  verb
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/^\w/, (first) => first.toUpperCase())
);

const detailHover = (title, lines) => (
  markdownHover(title, lines.filter(Boolean).join('\n\n'))
);

const humanReadableLineHover = (tokens, tokenIndex) => {
  if (tokenIndex !== 0 || !tokens[0]) {
    return null;
  }

  const verb = tokens[0].text;

  switch (verb) {
    case 'const':
      return detailHover(`Constant: ${tokenText(tokens, 1)}`, [
        `Declares ${inlineCode(tokenText(tokens, 1))} as an immutable value.`,
        `Type: ${inlineCode(tokenText(tokens, 2))}`,
        `Initial value: ${inlineCode(tokenTailText(tokens, 3))}`,
        'Later lines can read this binding; it is not a storage slot and cannot be updated with `set`.',
      ]);

    case 'var':
      return detailHover(`Mutable variable: ${tokenText(tokens, 1)}`, [
        `Declares ${inlineCode(tokenText(tokens, 1))} as an operation-local mutable value.`,
        `Type: ${inlineCode(tokenText(tokens, 2))}`,
        `Initial value: ${inlineCode(tokenTailText(tokens, 3))}`,
        'Later `set` lines may replace this value inside the current operation.',
      ]);

    case 'storage':
      return detailHover(`Storage binding: ${tokenText(tokens, 3)}`, [
        `Declares ${inlineCode(tokenText(tokens, 3))} in ${inlineCode(tokenText(tokens, 1))} storage.`,
        `Mutability: ${inlineCode(tokenText(tokens, 2))}`,
        `Type: ${inlineCode(tokenText(tokens, 4))}`,
        `Initial value: ${inlineCode(tokenTailText(tokens, 5))}`,
      ]);

    case 'sharedState':
      return detailHover(`Shared state: ${tokenText(tokens, 3)}`, [
        `Declares process-visible mutable state ${inlineCode(tokenText(tokens, 3))}.`,
        `Scope: ${inlineCode(tokenText(tokens, 1))}`,
        `Mutability: ${inlineCode(tokenText(tokens, 2))}`,
        `Type: ${inlineCode(tokenText(tokens, 4))}`,
        `Initial value: ${inlineCode(tokenTailText(tokens, 5))}`,
        'Reads and writes should name the guard token with `protectedBy`.',
      ]);

    case 'operation':
      return detailHover(`Operation: ${tokenText(tokens, 1)}`, [
        `Starts the executable operation ${inlineCode(tokenText(tokens, 1))}.`,
        'Its `input`, `output`, `effect`, memory, async, and narrative metadata lines attach to this operation name.',
      ]);

    case 'input':
      return detailHover(`Input: ${tokenText(tokens, 2)}`, [
        `Adds parameter ${inlineCode(tokenText(tokens, 2))} to operation ${inlineCode(tokenText(tokens, 1))}.`,
        `Type: ${inlineCode(tokenText(tokens, 3))}`,
      ]);

    case 'output':
      return detailHover(`Output contract: ${tokenText(tokens, 1)}`, [
        `Declares what ${inlineCode(tokenText(tokens, 1))} returns.`,
        `Return shape: ${inlineCode(tokenTailText(tokens, 2))}`,
      ]);

    case 'effect':
      return detailHover(`Effect: ${tokenText(tokens, 1)}`, [
        `Operation ${inlineCode(tokenText(tokens, 1))} declares an external effect.`,
        `Action: ${inlineCode(tokenText(tokens, 2))}`,
        `Path: ${inlineCode(tokenTailText(tokens, 3))}`,
      ]);

    case 'memory':
    case 'memoryHeap':
    case 'memoryArena':
    case 'memoryAllocationSource':
    case 'memoryStackLimit':
    case 'async':
    case 'operationBody':
      return detailHover(`${readableVerbName(verb)}: ${tokenText(tokens, 1)}`, [
        `Attaches ${inlineCode(verb)} metadata to ${inlineCode(tokenText(tokens, 1))}.`,
        `Value: ${inlineCode(tokenTailText(tokens, 2))}`,
      ]);

    case 'purpose':
    case 'invariant':
    case 'warning':
    case 'failure':
    case 'guarantee':
    case 'security':
    case 'timing':
    case 'observability':
      return detailHover(`${readableVerbName(verb)}: ${tokenText(tokens, 1)}`, [
        `Human context attached to ${inlineCode(tokenText(tokens, 1))}.`,
        `Text: ${inlineCode(tokenTailText(tokens, 2))}`,
      ]);

    case 'call':
      return detailHover(`Call: ${tokenText(tokens, 1)}`, [
        `Creates call object ${inlineCode(tokenText(tokens, 1))}.`,
        `Target: ${inlineCode(tokenText(tokens, 2))}`,
        'Add `arg` lines, execute with `run` or `start`, then bind or ignore the result explicitly.',
      ]);

    case 'arg':
      return detailHover(`Argument: ${tokenText(tokens, 2)}`, [
        `Passes ${inlineCode(tokenText(tokens, 3))} into call ${inlineCode(tokenText(tokens, 1))}.`,
        `Argument role: ${inlineCode(tokenText(tokens, 2))}`,
      ]);

    case 'run':
      return detailHover(`Run call: ${tokenText(tokens, 1)}`, [
        `Executes prepared call ${inlineCode(tokenText(tokens, 1))} synchronously.`,
        'A later `bind`, `bindOk`, `bindError`, `ignoreOk`, or `ignoreValue` line should dispose of the result.',
      ]);

    case 'start':
      return detailHover(`Start async call: ${tokenText(tokens, 1)}`, [
        `Starts prepared call ${inlineCode(tokenText(tokens, 1))}.`,
        'The current single-thread lowering runs it immediately, but the source keeps the async lifecycle explicit.',
      ]);

    case 'await':
      return detailHover(`Await call: ${tokenText(tokens, 1)}`, [
        `Waits for started call ${inlineCode(tokenText(tokens, 1))}.`,
        'Under current synchronous lowering this is a no-op after `start`, but the contract remains visible.',
      ]);

    case 'bind':
      return detailHover(`Bind result: ${tokenText(tokens, 1)}`, [
        `Stores the infallible result of ${inlineCode(tokenText(tokens, 3))} into ${inlineCode(tokenText(tokens, 1))}.`,
        `Type: ${inlineCode(tokenText(tokens, 2))}`,
      ]);

    case 'bindOk':
      return detailHover(`Bind success: ${tokenText(tokens, 1)}`, [
        `Stores the success value from fallible call ${inlineCode(tokenText(tokens, 3))}.`,
        `Name: ${inlineCode(tokenText(tokens, 1))}`,
        `Type: ${inlineCode(tokenText(tokens, 2))}`,
      ]);

    case 'bindError':
      return detailHover(`Bind error: ${tokenText(tokens, 1)}`, [
        `Stores the error value from fallible call ${inlineCode(tokenText(tokens, 3))}.`,
        `Name: ${inlineCode(tokenText(tokens, 1))}`,
        `Type: ${inlineCode(tokenText(tokens, 2))}`,
        'Pair this with `branchIfError` so the failure path is explicit.',
      ]);

    case 'ignoreOk':
    case 'ignoreValue':
      return detailHover(`${readableVerbName(verb)}: ${tokenText(tokens, 1)}`, [
        `Explicitly discards the value from ${inlineCode(tokenText(tokens, 1))}.`,
        `Discarded type: ${inlineCode(tokenText(tokens, 2))}`,
      ]);

    case 'label':
      return detailHover(`Label: ${tokenText(tokens, 1)}`, [
        `Declares branch target ${inlineCode(tokenText(tokens, 1))}.`,
        'Control-flow lines can jump here by name.',
      ]);

    case 'branch':
      return detailHover(`Branch: ${tokenText(tokens, 1)}`, [
        `Always jumps to ${inlineCode(tokenText(tokens, 1))}.`,
      ]);

    case 'branchIf':
      return detailHover(`Conditional branch: ${tokenText(tokens, 2)}`, [
        `Jumps to ${inlineCode(tokenText(tokens, 2))} when ${inlineCode(tokenText(tokens, 1))} is true.`,
        'The false path continues to the next line.',
      ]);

    case 'branchIfError':
      return detailHover(`Error branch: ${tokenText(tokens, 2)}`, [
        `Jumps to ${inlineCode(tokenText(tokens, 2))} if call ${inlineCode(tokenText(tokens, 1))} failed.`,
      ]);

    case 'returnOk':
      return detailHover(`Return success: ${tokenText(tokens, 1)}`, [
        `Returns ${inlineCode(tokenText(tokens, 1))} through the operation success path.`,
      ]);

    case 'returnError':
      return detailHover(`Return error: ${tokenText(tokens, 1)}`, [
        `Returns ${inlineCode(tokenText(tokens, 1))} through the operation error path.`,
      ]);

    case 'returnValue':
      return detailHover(`Return value: ${tokenText(tokens, 1)}`, [
        `Returns raw value ${inlineCode(tokenText(tokens, 1))}.`,
      ]);

    case 'makeError':
      return detailHover(`Construct error: ${tokenText(tokens, 1)}`, [
        `Creates typed failure value ${inlineCode(tokenText(tokens, 1))}.`,
        `Variant: ${inlineCode(tokenText(tokens, 2))}`,
        `Source value: ${inlineCode(tokenTailText(tokens, 3))}`,
      ]);

    case 'declareFailure':
      return detailHover(`Declare failure: ${tokenText(tokens, 1)}`, [
        `Declares named failure value ${inlineCode(tokenText(tokens, 1))}.`,
        `Variant: ${inlineCode(tokenText(tokens, 2))}`,
        `Source value: ${inlineCode(tokenTailText(tokens, 3))}`,
      ]);

    case 'set':
      if (tokens[1] && ['local', 'module', 'sharedState'].includes(tokens[1].text)) {
        return detailHover(`Set ${tokens[1].text}: ${tokenText(tokens, 2)}`, [
          `Updates ${inlineCode(tokenText(tokens, 2))} in ${inlineCode(tokenText(tokens, 1))} storage.`,
          `New value: ${inlineCode(tokenText(tokens, 3))}`,
          tokens.length > 4 ? `Authority clause: ${inlineCode(tokenTailText(tokens, 4))}` : '',
        ]);
      }

      return detailHover(`Set variable: ${tokenText(tokens, 1)}`, [
        `Updates mutable value ${inlineCode(tokenText(tokens, 1))}.`,
        `New value: ${inlineCode(tokenTailText(tokens, 2))}`,
      ]);

    case 'read':
      return detailHover(`Read: ${tokenText(tokens, 2)}`, [
        `Reads ${inlineCode(tokenText(tokens, 4))} into ${inlineCode(tokenText(tokens, 2))}.`,
        `Scope: ${inlineCode(tokenText(tokens, 1))}`,
        `Type: ${inlineCode(tokenText(tokens, 3))}`,
        tokens.length > 5 ? `Authority clause: ${inlineCode(tokenTailText(tokens, 5))}` : '',
      ]);

    case 'timeout':
    case 'cancelOn':
    case 'useRetry':
      return detailHover(`${readableVerbName(verb)}: ${tokenText(tokens, 1)}`, [
        `Attaches ${inlineCode(verb)} to call ${inlineCode(tokenText(tokens, 1))}.`,
        `Value: ${inlineCode(tokenTailText(tokens, 2))}`,
      ]);

    case 'useCapability':
      return detailHover(`Capability use: ${tokenText(tokens, 2)}`, [
        `Attaches capability ${inlineCode(tokenText(tokens, 2))} to ${inlineCode(tokenText(tokens, 1))}.`,
      ]);

    case 'new':
      return detailHover(`New record: ${tokenText(tokens, 1)}`, [
        `Creates record value ${inlineCode(tokenText(tokens, 1))}.`,
        `Record type: ${inlineCode(tokenText(tokens, 2))}`,
      ]);

    case 'fieldGet':
      return detailHover(`Read field: ${tokenText(tokens, 4)}`, [
        `Reads field ${inlineCode(tokenText(tokens, 4))} from ${inlineCode(tokenText(tokens, 3))}.`,
        `Output: ${inlineCode(tokenText(tokens, 1))}`,
        `Type: ${inlineCode(tokenText(tokens, 2))}`,
      ]);

    case 'fieldSet':
      return detailHover(`Write field: ${tokenText(tokens, 2)}`, [
        `Writes ${inlineCode(tokenText(tokens, 3))} into field ${inlineCode(tokenText(tokens, 2))}.`,
        `Record value: ${inlineCode(tokenText(tokens, 1))}`,
      ]);

    case 'recordBuilder':
      return detailHover(`Record builder: ${tokenText(tokens, 1)}`, [
        `Creates builder ${inlineCode(tokenText(tokens, 1))}.`,
        `Record type: ${inlineCode(tokenText(tokens, 2))}`,
      ]);

    case 'recordSet':
      return detailHover(`Builder field: ${tokenText(tokens, 2)}`, [
        `Sets field ${inlineCode(tokenText(tokens, 2))} on builder ${inlineCode(tokenText(tokens, 1))}.`,
        `Value: ${inlineCode(tokenText(tokens, 3))}`,
      ]);

    case 'recordBuild':
      return detailHover(`Build record call: ${tokenText(tokens, 1)}`, [
        `Creates fallible build call ${inlineCode(tokenText(tokens, 1))}.`,
        `Builder: ${inlineCode(tokenText(tokens, 2))}`,
      ]);

    case 'defer':
    case 'deferLog':
    case 'deferAwaitLog':
      return detailHover(`${readableVerbName(verb)}: ${tokenText(tokens, 1)}`, [
        `Registers cleanup ${inlineCode(tokenText(tokens, 1))}.`,
        `Target operation: ${inlineCode(tokenText(tokens, 2))}`,
        `Arguments: ${inlineCode(tokenTailText(tokens, 3))}`,
      ]);

    case 'deferWhenExitLog':
      return detailHover(`Conditional cleanup: ${tokenText(tokens, 1)}`, [
        `Registers cleanup ${inlineCode(tokenText(tokens, 1))}.`,
        `Guard value: ${inlineCode(tokenText(tokens, 2))}`,
        `Target operation: ${inlineCode(tokenText(tokens, 3))}`,
        `Arguments: ${inlineCode(tokenTailText(tokens, 4))}`,
      ]);

    case 'deferLogSink':
    case 'deferAwaitLogSink':
    case 'deferWhenExitLogSink':
    case 'deferRunOn':
    case 'deferOrder':
    case 'deferFailurePolicy':
    case 'deferConsumes':
    case 'deferAwaitTimeout':
      return detailHover(`${readableVerbName(verb)}: ${tokenText(tokens, 1)}`, [
        `Attaches ${inlineCode(verb)} metadata to cleanup ${inlineCode(tokenText(tokens, 1))}.`,
        `Value: ${inlineCode(tokenTailText(tokens, 2))}`,
      ]);

    case 'workerPool':
      return detailHover(`Worker pool: ${tokenText(tokens, 1)}`, [
        `Declares worker pool ${inlineCode(tokenText(tokens, 1))}.`,
        `Options: ${inlineCode(tokenTailText(tokens, 2))}`,
        'The current single-thread lowering runs submitted work inline.',
      ]);

    case 'work':
      return detailHover(`Work item: ${tokenText(tokens, 1)}`, [
        `Declares work item ${inlineCode(tokenText(tokens, 1))}.`,
        `Target operation: ${inlineCode(tokenText(tokens, 3))}`,
      ]);

    case 'workArg':
      return detailHover(`Work argument: ${tokenText(tokens, 2)}`, [
        `Passes ${inlineCode(tokenText(tokens, 3))} into work item ${inlineCode(tokenText(tokens, 1))}.`,
        `Argument role: ${inlineCode(tokenText(tokens, 2))}`,
      ]);

    case 'submitWork':
      return detailHover(`Submit work: ${tokenText(tokens, 1)}`, [
        `Submits work item ${inlineCode(tokenText(tokens, 1))} to pool ${inlineCode(tokenText(tokens, 2))}.`,
        'Current lowering dispatches the target operation immediately on the same thread.',
      ]);

    case 'awaitWork':
      return detailHover(`Await work: ${tokenText(tokens, 1)}`, [
        `Waits for work item ${inlineCode(tokenText(tokens, 1))}.`,
        'Current lowering has already completed the work at `submitWork`.',
      ]);

    case 'interval':
      return detailHover(`Interval: ${tokenText(tokens, 1)}`, [
        `Declares interval ${inlineCode(tokenText(tokens, 1))}.`,
        `Options: ${inlineCode(tokenTailText(tokens, 2))}`,
      ]);

    case 'startInterval':
    case 'awaitIntervalTick':
      return detailHover(`${readableVerbName(verb)}: ${tokenText(tokens, 1)}`, [
        `Uses interval ${inlineCode(tokenText(tokens, 1))}.`,
        'Current single-thread lowering treats interval waiting as a no-op.',
      ]);

    case 'project':
    case 'target':
    case 'runtime':
    case 'entry':
    case 'module':
    case 'mode':
    case 'importModule':
    case 'type':
    case 'record':
    case 'field':
    case 'enum':
    case 'enumCase':
    case 'error':
    case 'errorCase':
    case 'webServer':
    case 'route':
    case 'routeTimeout':
    case 'routeMiddleware':
    case 'capability':
    case 'authority':
    case 'resource':
    case 'codec':
    case 'jsonCodec':
    case 'schema':
    case 'unknownFields':
    case 'retryPolicy':
    case 'timeoutBudget':
    case 'trustBoundary':
    case 'guardTokenSource':
    case 'guardTokenOwner':
    case 'guardTokenProtects':
    case 'guardTokenRelease':
      return detailHover(`${readableVerbName(verb)} line`, [
        `Declares ${inlineCode(tokenText(tokens, 1))} with ${inlineCode(verb)}.`,
        tokens.length > 2 ? `Details: ${inlineCode(tokenTailText(tokens, 2))}` : '',
      ]);

    default:
      if (verbHoverText.has(verb)) {
        return detailHover(`${readableVerbName(verb)} line`, [
          verbHoverText.get(verb),
          tokens.length > 1 ? `Parsed fields: ${inlineCode(tokenTailText(tokens, 1))}` : '',
        ]);
      }

      return null;
  }
};

const declarationKindTitle = (declaration) => (
  declaration.kind
    ? declaration.kind.replace(/^\w/, (first) => first.toUpperCase())
    : 'Symbol'
);

const declarationSummaryLines = (declaration) => {
  const lines = [];

  if (declaration.operation) {
    lines.push(`Scope: operation ${inlineCode(declaration.operation)}`);
  } else {
    lines.push('Scope: module level');
  }

  lines.push(`Declared on line ${declaration.line}.`);

  if (declaration.owner) {
    lines.push(`Owner: ${inlineCode(declaration.owner)}`);
  }

  if (declaration.scope) {
    lines.push(`Storage scope: ${inlineCode(declaration.scope)}`);
  }

  if (declaration.mutability) {
    lines.push(`Mutability: ${inlineCode(declaration.mutability)}`);
  }

  if (declaration.type) {
    lines.push(`Type: ${inlineCode(declaration.type)}`);
  }

  if (declaration.value && declaration.value !== '?') {
    lines.push(`Value/source: ${inlineCode(declaration.value)}`);
  }

  if (declaration.target) {
    lines.push(`Target: ${inlineCode(declaration.target)}`);
  }

  if (declaration.details && declaration.details !== '?') {
    lines.push(`Details: ${inlineCode(declaration.details)}`);
  }

  if (declaration.args && declaration.args.length > 0) {
    lines.push(`Arguments: ${declaration.args.map((arg) => (
      `${inlineCode(arg.role)} <- ${inlineCode(arg.value)}`
    )).join(', ')}`);
  }

  if (declaration.resultBindings && declaration.resultBindings.length > 0) {
    lines.push(`Result handling: ${declaration.resultBindings.map((binding) => (
      `${inlineCode(binding.verb)} ${inlineCode(binding.name)} as ${inlineCode(binding.type)}`
    )).join(', ')}`);
  }

  return lines;
};

const tokenUseDescription = (tokens, tokenIndex, declaration) => {
  const verb = tokens[0] ? tokens[0].text : '';
  const text = tokenText(tokens, tokenIndex);

  switch (verb) {
    case 'const':
    case 'var':
      if (tokenIndex === 1) {
        return `This token declares ${inlineCode(text)}.`;
      }
      if (tokenIndex === 2) {
        return `This token is the declared type for ${inlineCode(tokenText(tokens, 1))}.`;
      }
      if (tokenIndex >= 3) {
        return `This token contributes to the initial value of ${inlineCode(tokenText(tokens, 1))}.`;
      }
      break;

    case 'storage':
    case 'sharedState':
      if (tokenIndex === 3) {
        return `This token declares the storage slot ${inlineCode(text)}.`;
      }
      if (tokenIndex === 4) {
        return `This token is the storage value type for ${inlineCode(tokenText(tokens, 3))}.`;
      }
      if (tokenIndex >= 5) {
        return `This token contributes to the initial storage value for ${inlineCode(tokenText(tokens, 3))}.`;
      }
      break;

    case 'input':
      if (tokenIndex === 2) {
        return `This token declares input parameter ${inlineCode(text)} for ${inlineCode(tokenText(tokens, 1))}.`;
      }
      if (tokenIndex === 3) {
        return `This token is the parameter type for ${inlineCode(tokenText(tokens, 2))}.`;
      }
      break;

    case 'call':
      if (tokenIndex === 1) {
        return `This token declares call object ${inlineCode(text)}.`;
      }
      if (tokenIndex === 2) {
        return `This token is the target invoked by ${inlineCode(tokenText(tokens, 1))}.`;
      }
      break;

    case 'arg':
      if (tokenIndex === 1) {
        return `This token selects call object ${inlineCode(text)}.`;
      }
      if (tokenIndex === 2) {
        return `This token is the target argument role on ${inlineCode(tokenText(tokens, 1))}.`;
      }
      if (tokenIndex === 3) {
        return `This value flows into ${inlineCode(tokenText(tokens, 2))} on call ${inlineCode(tokenText(tokens, 1))}.`;
      }
      break;

    case 'run':
    case 'start':
    case 'await':
    case 'ignoreOk':
    case 'ignoreValue':
    case 'timeout':
    case 'cancelOn':
    case 'useRetry':
      if (tokenIndex === 1) {
        return `This token references call object ${inlineCode(text)}.`;
      }
      if (tokenIndex >= 2) {
        return `This token configures ${inlineCode(tokenText(tokens, 1))}.`;
      }
      break;

    case 'bind':
    case 'bindOk':
    case 'bindError':
      if (tokenIndex === 1) {
        return `This token declares ${inlineCode(text)} from call ${inlineCode(tokenText(tokens, 3))}.`;
      }
      if (tokenIndex === 2) {
        return `This token is the declared type for ${inlineCode(tokenText(tokens, 1))}.`;
      }
      if (tokenIndex === 3) {
        return `This token is the call object whose result is being bound.`;
      }
      break;

    case 'set':
      if (tokens[1] && ['local', 'module', 'sharedState'].includes(tokens[1].text)) {
        if (tokenIndex === 2) {
          return `This token is the storage slot being updated.`;
        }
        if (tokenIndex === 3) {
          return `This value is written into ${inlineCode(tokenText(tokens, 2))}.`;
        }
      } else if (tokenIndex === 1) {
        return `This token is the mutable value being updated.`;
      } else if (tokenIndex >= 2) {
        return `This value is assigned to ${inlineCode(tokenText(tokens, 1))}.`;
      }
      break;

    case 'read':
      if (tokenIndex === 2) {
        return `This token declares the value loaded from shared state.`;
      }
      if (tokenIndex === 4) {
        return `This token is the shared-state slot being read.`;
      }
      break;

    case 'label':
      if (tokenIndex === 1) {
        return `This token declares branch target ${inlineCode(text)}.`;
      }
      break;

    case 'branch':
      if (tokenIndex === 1) {
        return `This token is the label jumped to unconditionally.`;
      }
      break;

    case 'branchIf':
      if (tokenIndex === 1) {
        return `This token is the condition being tested.`;
      }
      if (tokenIndex === 2) {
        return `This token is the label used when the condition is true.`;
      }
      break;

    case 'branchIfError':
      if (tokenIndex === 1) {
        return `This token is the call object checked for failure.`;
      }
      if (tokenIndex === 2) {
        return `This token is the label used when the call failed.`;
      }
      break;

    case 'returnOk':
      if (tokenIndex === 1) {
        return `This token is returned through the success path.`;
      }
      break;

    case 'returnError':
      if (tokenIndex === 1) {
        return `This token is returned through the error path.`;
      }
      break;

    case 'returnValue':
      if (tokenIndex === 1) {
        return `This token is returned as the raw operation value.`;
      }
      break;

    case 'makeError':
    case 'declareFailure':
      if (tokenIndex === 1) {
        return `This token declares a named failure value.`;
      }
      if (tokenIndex === 2) {
        return `This token names the error variant.`;
      }
      if (tokenIndex >= 3) {
        return `This token is the source value attached to the failure.`;
      }
      break;

    default:
      if (declaration) {
        return `This line uses ${inlineCode(text)} as a ${declaration.kind}.`;
      }
      break;
  }

  return null;
};

const chooseSymbolDeclaration = (entry, currentOperation) => {
  if (!entry || entry.declarations.length === 0) {
    return null;
  }

  return entry.declarations.find((declaration) => declaration.operation === currentOperation)
    || entry.declarations.find((declaration) => !declaration.operation)
    || entry.declarations[0];
};

const symbolHover = (document, position, token, tokenIndex, tokens) => {
  const text = token.text;

  if (tokenIndex === 0 || !isSymbolLike(text) || schemaValues.has(text)) {
    return null;
  }

  const index = getDocumentSymbolIndex(document);
  const currentOperation = index.lineOperations.get(position.line) || null;
  const entry = index.symbols.get(text);
  const declaration = chooseSymbolDeclaration(entry, currentOperation);

  if (!declaration) {
    return null;
  }

  const useDescription = tokenUseDescription(tokens, tokenIndex, declaration);
  const markdown = new vscode.MarkdownString();
  markdown.appendMarkdown(`**${declarationKindTitle(declaration)}: ${text}**\n\n`);

  if (useDescription) {
    markdown.appendMarkdown(`${useDescription}\n\n`);
  }

  declarationSummaryLines(declaration).forEach((line) => {
    markdown.appendMarkdown(`${line}\n\n`);
  });

  if (entry.declarations.length > 1) {
    markdown.appendMarkdown(`Other declarations with this name: ${entry.declarations.length - 1}.\n\n`);
  }

  if (declaration.text) {
    markdown.appendCodeblock(declaration.text, 'agentscript');
  }

  return new vscode.Hover(markdown);
};

const operationMetadataHover = (operation) => {
  const markdown = new vscode.MarkdownString();
  markdown.appendMarkdown(`**Operation metadata: ${operation.name}**\n\n`);

  if (operation.section) {
    markdown.appendMarkdown(`Section: \`${operation.section}\`\n\n`);
  }

  if (operation.declarationLine) {
    markdown.appendMarkdown(`Declared on line ${operation.declarationLine}.\n\n`);
  } else {
    markdown.appendMarkdown('No `operation` declaration was found in this file; showing metadata references only.\n\n');
  }

  const codeLines = [];

  if (operation.declarationText) {
    codeLines.push(operation.declarationText);
  }

  const maxMetadataLines = 30;
  operation.metadata.slice(0, maxMetadataLines).forEach((record) => {
    codeLines.push(record.text);
  });

  if (operation.metadata.length > maxMetadataLines) {
    codeLines.push(`# ... ${operation.metadata.length - maxMetadataLines} more metadata line(s)`);
  }

  if (codeLines.length > 0) {
    markdown.appendCodeblock(codeLines.join('\n'), 'agentscript');
  }

  return new vscode.Hover(markdown);
};

const roleSuffixHover = (token, character) => {
  const suffixMatch = token.text.match(roleSuffixPattern);

  if (!suffixMatch) {
    return null;
  }

  const suffix = suffixMatch[0];
  const suffixStart = token.start + token.text.length - suffix.length;

  if (character < suffixStart) {
    return null;
  }

  return markdownHover(
    `Role suffix: ${suffix}`,
    'AgentScript role suffixes are context markers. They tell agents and tools what semantic kind a symbol represents.'
  );
};

const provideHover = (document, position) => {
  const found = getTokenAtPosition(document, position);

  if (!found) {
    return null;
  }

  const { token, tokenIndex, tokens } = found;
  const text = token.text;

  const operationHoverName = operationHoverNameForToken(text, tokenIndex, tokens);

  if (operationHoverName) {
    const operation = getOperationMetadataIndex(document).get(operationHoverName);

    if (operation) {
      return operationMetadataHover(operation);
    }
  }

  const lineHover = humanReadableLineHover(tokens, tokenIndex);

  if (lineHover) {
    return lineHover;
  }

  const resolvedSymbolHover = symbolHover(document, position, token, tokenIndex, tokens);

  if (resolvedSymbolHover) {
    return resolvedSymbolHover;
  }

  const tokenType = tokenTypeForSymbol(text, tokenIndex, tokens);
  const suffixHover = roleSuffixHover(token, position.character);

  if (suffixHover && tokenIndex > 0 && canSplitRoleSuffix(tokenType)) {
    return suffixHover;
  }

  if (tokenIndex === 0 && verbHoverText.has(text)) {
    return markdownHover(`AgentScript verb: ${text}`, verbHoverText.get(text));
  }

  if (primitiveTargets.has(text)) {
    return markdownHover(`Primitive call target: ${text}`, primitiveTargets.get(text));
  }

  if (cRuntimeTargetPattern.test(text)) {
    return markdownHover(
      `C runtime call target: ${text}`,
      'Calls a registered C standard-library function through the reference compiler libc registry. Declare matching operation effects for lint coverage.'
    );
  }

  if (generatedTargetPattern.test(text)) {
    return markdownHover(`Generated target: ${text}`, generatedTargetHoverText(text));
  }

  if (isDomainTarget(text)) {
    return markdownHover(
      `Domain-typed method: ${text}`,
      domainTargetHoverText(text)
    );
  }

  if (/^[A-Z][A-Za-z0-9_]*\.[A-Z][A-Za-z0-9_]*$/.test(text)) {
    return markdownHover(
      `Error variant: ${text}`,
      '`makeError NAME ErrorType.Variant [source]` creates a typed error value for `returnError`.'
    );
  }

  if (primitiveTypes.has(text)) {
    return markdownHover(`Primitive type: ${text}`, primitiveTypes.get(text));
  }

  if (schemaValues.has(text)) {
    return markdownHover(`Schema value: ${text}`, schemaValues.get(text));
  }

  if (opaqueInputs.has(text)) {
    return markdownHover(
      `Opaque input: ${text}`,
      'AST.md: opaque dependency inputs may appear in `arg` lines to preserve dependency context, but they do not flow into computation.'
    );
  }

  if (tokens[0] && tokens[0].text === 'call' && tokenIndex === 1) {
    return markdownHover(
      `Call object: ${text}`,
      'A call object is a named semantic node. Related `arg`, `run`, `bind*`, `ignoreOk`, `ignoreValue`, and `branchIfError` lines should reference this name.'
    );
  }

  return null;
};

const registerHovers = (context) => {
  context.subscriptions.push(
    vscode.languages.registerHoverProvider(
      { language: 'agentscript' },
      { provideHover }
    )
  );
};

const syncConfiguration = () => {
  const segmentConfig = vscode.workspace.getConfiguration('agentScript.segmentColors');
  segmentColoringEnabled = segmentConfig.get('enabled', true);
  segmentColorMode = segmentConfig.get('colorMode', 'background');

  const linterConfig = vscode.workspace.getConfiguration('agentScript.linter');
  linterEnabled = linterConfig.get('enabled', true);
  linterRunMode = linterConfig.get('run', 'onSave');
  linterPythonPath = linterConfig.get('pythonPath', 'python');
  linterConfiguredPath = linterConfig.get('path', '');
  linterSkipFutureSyntax = linterConfig.get('skipFutureSyntax', true);
  linterEngine = linterConfig.get('engine', 'aslint');
};

const isAgentScriptDocument = (document) => (
  document && document.languageId === 'agentscript' && document.uri.scheme === 'file'
);

const documentUsesFutureSyntax = (document) => {
  const text = document.getText();

  if (
    text.includes('future refined syntax')
    || text.includes('not current executable AgentScript')
  ) {
    return true;
  }

  return text.split(/\r?\n/).some((line) => {
    const trimmedLine = line.trim();

    if (!trimmedLine || trimmedLine.startsWith('#')) {
      return false;
    }

    const verb = trimmedLine.split(/\s+/, 1)[0];
    return futureSyntaxLinterSkipVerbs.has(verb);
  });
};

const linterScriptName = () => (linterEngine === 'aslint2' ? 'aslint2.py' : 'aslint.py');

const candidateLinterPaths = (document) => {
  const candidates = [];
  const workspaceFolder = document ? vscode.workspace.getWorkspaceFolder(document.uri) : null;
  const scriptName = linterScriptName();
  const addAncestorCandidates = (startPath) => {
    let currentPath = path.resolve(startPath);
    const rootPath = path.parse(currentPath).root;

    while (currentPath && currentPath !== rootPath) {
      candidates.push(path.join(currentPath, 'AgentScript', 'linter', scriptName));
      candidates.push(path.join(currentPath, 'linter', scriptName));
      currentPath = path.dirname(currentPath);
    }
  };

  if (linterConfiguredPath) {
    if (path.isAbsolute(linterConfiguredPath)) {
      candidates.push(linterConfiguredPath);
    } else if (workspaceFolder) {
      candidates.push(path.join(workspaceFolder.uri.fsPath, linterConfiguredPath));
    }
  }

  const workspaceFolders = vscode.workspace.workspaceFolders || [];
  workspaceFolders.forEach((folder) => {
    candidates.push(path.join(folder.uri.fsPath, 'AgentScript', 'linter', scriptName));
    candidates.push(path.join(folder.uri.fsPath, 'linter', scriptName));
    candidates.push(path.join(folder.uri.fsPath, '..', 'AgentScript', 'linter', scriptName));
    addAncestorCandidates(folder.uri.fsPath);
  });

  if (document && document.fileName) {
    addAncestorCandidates(path.dirname(document.fileName));
  }

  candidates.push(path.join(__dirname, 'tools', scriptName));

  return candidates;
};

const findLinterPath = (document) => {
  const seen = new Set();
  const candidates = candidateLinterPaths(document);

  for (const candidate of candidates) {
    const normalized = path.normalize(candidate);

    if (seen.has(normalized)) {
      continue;
    }

    seen.add(normalized);

    if (fs.existsSync(normalized)) {
      return normalized;
    }
  }

  return null;
};

const severityFromLinter = (severity) => {
  if (severity === 'error') {
    return vscode.DiagnosticSeverity.Error;
  }

  if (severity === 'warning') {
    return vscode.DiagnosticSeverity.Warning;
  }

  return vscode.DiagnosticSeverity.Information;
};

const diagnosticRange = (document, lineNumber, columnNumber) => {
  const lineIndex = Math.max(0, Math.min(document.lineCount - 1, (lineNumber || 1) - 1));
  const line = document.lineAt(lineIndex);
  const startCharacter = Math.max(0, Math.min(line.text.length, (columnNumber || 1) - 1));
  const wordRange = document.getWordRangeAtPosition(new vscode.Position(lineIndex, startCharacter));

  if (wordRange) {
    return wordRange;
  }

  return new vscode.Range(
    lineIndex,
    startCharacter,
    lineIndex,
    Math.min(line.text.length, startCharacter + 1)
  );
};

const aslint2Message = (record) => {
  const parts = [];

  if (record.code || record.kind) {
    parts.push([record.code, record.kind].filter(Boolean).join(' '));
  }

  if (record.intentSlogan) {
    parts.push(record.intentSlogan);
  } else if (record.invariantRule) {
    parts.push(record.invariantRule);
  }

  if (record.subjectName) {
    parts.push(`${record.subjectKind || 'subject'}: ${record.subjectName}`);
  }

  if (record.gapEdge) {
    parts.push(`gap: ${record.gapEdge}`);
  }

  return parts.join(' - ') || 'AgentScript lint diagnostic';
};

const diagnosticFromAslint2Record = (document, record) => {
  const primary = record.primary || {};
  const diagnostic = new vscode.Diagnostic(
    diagnosticRange(document, primary.line, primary.column),
    aslint2Message(record),
    severityFromLinter(record.severity)
  );
  diagnostic.source = 'aslint2';
  diagnostic.code = record.code || undefined;
  return diagnostic;
};

const diagnosticFromAslintRecord = (document, record) => {
  const diagnostic = new vscode.Diagnostic(
    diagnosticRange(document, record.line, record.column),
    record.message || String(record.rule || 'AgentScript lint diagnostic'),
    severityFromLinter(record.severity)
  );
  diagnostic.source = 'aslint';
  diagnostic.code = record.rule || undefined;
  return diagnostic;
};

const parseLinterDiagnostics = (document, stdout) => {
  let records;

  try {
    records = JSON.parse(stdout || '[]');
  } catch (_error) {
    return [
      new vscode.Diagnostic(
        new vscode.Range(0, 0, 0, Math.max(1, document.lineAt(0).text.length)),
        `${linterEngine} returned invalid JSON diagnostics.`,
        vscode.DiagnosticSeverity.Error
      ),
    ];
  }

  if (!Array.isArray(records)) {
    return [];
  }

  return records.map((record) => {
    if (record && record.primary) {
      return diagnosticFromAslint2Record(document, record);
    }

    return diagnosticFromAslintRecord(document, record || {});
  });
};

const setLinterStatus = (text, tooltip) => {
  if (!lintStatusBarItem) {
    return;
  }

  lintStatusBarItem.text = text;
  lintStatusBarItem.tooltip = tooltip || '';
  lintStatusBarItem.show();
};

const clearLinterStatusLater = () => {
  if (!lintStatusBarItem) {
    return;
  }

  setTimeout(() => {
    if (lintStatusBarItem) {
      lintStatusBarItem.hide();
    }
  }, 2500);
};

const runLinterForDocument = (document, showMissingLinterMessage = false) => {
  if (!diagnosticCollection || !isAgentScriptDocument(document)) {
    return;
  }

  if (!linterEnabled) {
    diagnosticCollection.delete(document.uri);
    return;
  }

  const documentKey = document.uri.toString();
  const existingProcess = runningLintProcesses.get(documentKey);

  if (existingProcess) {
    existingProcess.kill();
    runningLintProcesses.delete(documentKey);
  }

  if (linterSkipFutureSyntax && documentUsesFutureSyntax(document)) {
    diagnosticCollection.delete(document.uri);
    setLinterStatus('$(info) AgentScript future syntax', `${linterEngine} is skipped for refined future syntax.`);
    clearLinterStatusLater();
    return;
  }

  const linterPath = findLinterPath(document);

  if (!linterPath) {
    diagnosticCollection.delete(document.uri);

    if (showMissingLinterMessage) {
      vscode.window.showWarningMessage(
        `AgentScript ${linterEngine} linter not found. Set agentScript.linter.path or open the AgentScript repo root.`
      );
    }

    return;
  }

  setLinterStatus('$(sync~spin) AgentScript lint', document.fileName);
  const linterArgs = linterEngine === 'aslint2'
    ? [linterPath, document.fileName, '--format', 'json']
    : [linterPath, document.fileName, '--format', 'json', '--fail-on', 'none'];

  const lintProcess = childProcess.spawn(
    linterPythonPath,
    linterArgs,
    {
      cwd: vscode.workspace.getWorkspaceFolder(document.uri)?.uri.fsPath || path.dirname(document.fileName),
      windowsHide: true,
    }
  );

  runningLintProcesses.set(documentKey, lintProcess);

  let stdout = '';
  let stderr = '';

  lintProcess.stdout.on('data', (chunk) => {
    stdout += chunk.toString();
  });

  lintProcess.stderr.on('data', (chunk) => {
    stderr += chunk.toString();
  });

  lintProcess.on('error', (error) => {
    runningLintProcesses.delete(documentKey);
    diagnosticCollection.set(document.uri, [
      new vscode.Diagnostic(
        new vscode.Range(0, 0, 0, Math.max(1, document.lineAt(0).text.length)),
        `Failed to run ${linterEngine} with ${linterPythonPath}: ${error.message}`,
        vscode.DiagnosticSeverity.Error
      ),
    ]);
    setLinterStatus('$(error) AgentScript lint failed', error.message);
    clearLinterStatusLater();
  });

  lintProcess.on('close', () => {
    if (runningLintProcesses.get(documentKey) !== lintProcess) {
      return;
    }

    runningLintProcesses.delete(documentKey);

    if (stderr.trim() && !stdout.trim()) {
      diagnosticCollection.set(document.uri, [
        new vscode.Diagnostic(
          new vscode.Range(0, 0, 0, Math.max(1, document.lineAt(0).text.length)),
          stderr.trim(),
          vscode.DiagnosticSeverity.Error
        ),
      ]);
      setLinterStatus('$(error) AgentScript lint failed', stderr.trim());
      clearLinterStatusLater();
      return;
    }

    const diagnostics = parseLinterDiagnostics(document, stdout);
    diagnosticCollection.set(document.uri, diagnostics);

    if (diagnostics.length > 0) {
      setLinterStatus(`$(warning) AgentScript lint ${diagnostics.length}`, `${diagnostics.length} diagnostic(s)`);
    } else {
      setLinterStatus('$(check) AgentScript lint clean', document.fileName);
    }

    clearLinterStatusLater();
  });
};

const scheduleLinterRun = (document, delayMilliseconds = 350) => {
  if (!isAgentScriptDocument(document)) {
    return;
  }

  const key = document.uri.toString();
  const existingTimeout = lintUpdateTimeouts.get(key);

  if (existingTimeout) {
    clearTimeout(existingTimeout);
  }

  lintUpdateTimeouts.set(key, setTimeout(() => {
    lintUpdateTimeouts.delete(key);
    runLinterForDocument(document);
  }, delayMilliseconds));
};

const registerLinter = (context) => {
  diagnosticCollection = vscode.languages.createDiagnosticCollection('aslint');
  lintStatusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  lintStatusBarItem.command = 'agentscript.runLinter';

  context.subscriptions.push(diagnosticCollection, lintStatusBarItem);

  context.subscriptions.push(
    vscode.commands.registerCommand('agentscript.runLinter', () => {
      const editor = vscode.window.activeTextEditor;

      if (!editor || !isAgentScriptDocument(editor.document)) {
        vscode.window.showInformationMessage('Open an AgentScript file to run the linter.');
        return;
      }

      runLinterForDocument(editor.document, true);
    })
  );

  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((document) => {
      if (linterRunMode === 'onSave') {
        runLinterForDocument(document);
      }
    })
  );

  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument((document) => {
      if (linterRunMode !== 'manual') {
        scheduleLinterRun(document, 100);
      }
    })
  );

  context.subscriptions.push(
    vscode.workspace.onDidCloseTextDocument((document) => {
      diagnosticCollection.delete(document.uri);
      const key = document.uri.toString();
      const existingTimeout = lintUpdateTimeouts.get(key);

      if (existingTimeout) {
        clearTimeout(existingTimeout);
        lintUpdateTimeouts.delete(key);
      }
    })
  );

  vscode.workspace.textDocuments.forEach((document) => {
    if (linterRunMode !== 'manual') {
      scheduleLinterRun(document, 100);
    }
  });
};

const activate = (context) => {
  syncConfiguration();
  disposeDecorations();
  decorations = createDecorations();
  verbDecorations = createVerbDecorations();
  registerSemanticTokens(context);
  registerHovers(context);
  registerLinter(context);

  context.subscriptions.push({
    dispose: disposeDecorations,
  });

  context.subscriptions.push(
    vscode.commands.registerCommand('agentscript.toggleSegmentColors', () => {
      segmentColoringEnabled = !segmentColoringEnabled;
      vscode.window.visibleTextEditors.forEach(updateSegmentDecorations);
      vscode.window.showInformationMessage(`AgentScript segment colors ${segmentColoringEnabled ? 'enabled' : 'disabled'}.`);
    })
  );

  context.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor((editor) => {
      scheduleDecorationUpdate(editor);
    })
  );

  context.subscriptions.push(
    vscode.workspace.onDidChangeTextDocument((event) => {
      const editor = vscode.window.visibleTextEditors.find((candidate) => (
        candidate.document === event.document
      ));
      scheduleDecorationUpdate(editor);

      if (linterRunMode === 'onType') {
        scheduleLinterRun(event.document);
      }
    })
  );

  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration('agentScript.segmentColors') || event.affectsConfiguration('agentScript.linter')) {
        disposeDecorations();
        syncConfiguration();
        decorations = createDecorations();
        verbDecorations = createVerbDecorations();
        vscode.window.visibleTextEditors.forEach(updateSegmentDecorations);

        if (!linterEnabled && diagnosticCollection) {
          diagnosticCollection.clear();
        } else if (linterRunMode !== 'manual') {
          vscode.workspace.textDocuments.forEach((document) => scheduleLinterRun(document, 100));
        }
      }
    })
  );

  vscode.window.visibleTextEditors.forEach(updateSegmentDecorations);
};

const deactivate = () => {
  activeDecorations.forEach((decoration) => decoration.dispose());
  activeDecorations = [];
  runningLintProcesses.forEach((lintProcess) => lintProcess.kill());
  runningLintProcesses.clear();
  lintUpdateTimeouts.forEach((timeoutHandle) => clearTimeout(timeoutHandle));
  lintUpdateTimeouts.clear();
  disposeDecorations();
};

module.exports = {
  activate,
  deactivate,
};
