'use strict';

const childProcess = require('child_process');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

const declarationVerbs = new Set([
  'section',
  'project', 'target', 'runtime', 'entry', 'module', 'dependency', 'dependencyEffect',
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
]);

const actionVerbs = new Set([
  'set', 'call', 'arg', 'run', 'start', 'await', 'bind', 'bindOk',
  'bindError', 'ignoreOk', 'ignoreValue', 'declareFailure', 'makeError',
  'new', 'fieldGet', 'fieldSet', 'recordBuilder', 'recordSet', 'recordCopy',
  'recordBuild', 'read', 'timeout', 'cancelOn',
  'defer', 'deferLog', 'deferAwaitLog', 'deferWhenExitLog', 'select', 'selectCase',
  'runSelect', 'taskGroup', 'startInGroup', 'awaitGroup', 'bindGroupError',
  'send', 'receive', 'lock', 'unlock', 'useRetry', 'useCapability',
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
  ['math.equalCSignedInt32', 'C signed 32-bit equality comparison returning Bool.'],
  ['math.greaterThanOrEqualCByteCount', 'C byte-count greater-than-or-equal comparison returning Bool.'],
  ['math.checkedMultiplyI64', 'i64 signed multiply with overflow detection. Fallible target; use bindOk, bindError, and branchIfError.'],
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

const generatedTargetHoverText = (text) => {
  if (text.startsWith('json.decode.')) {
    return 'Generated JSON decode target. It should be declared by jsonCodecDecodeTarget and backed by jsonCodec input, output, failure, strictness, and limit metadata.';
  }

  if (text.startsWith('json.encode.')) {
    return 'Generated JSON encode target. It should be declared by jsonCodecEncodeTarget and backed by jsonCodec input, output, failure, strictness, and limit metadata.';
  }

  return 'Generated AgentScript target declared by metadata.';
};

const schemaValues = new Map([
  ['yes', 'Boolean schema value.'],
  ['no', 'Boolean schema value.'],
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
  ['rawPointerToValidatedCString', 'Trust-boundary kind: raw pointer becomes validated C string.'],
  ['rawUtf8ToValidatedText', 'Trust-boundary kind: raw UTF-8 becomes validated text.'],
  ['row', 'Record layout kind: row layout.'],
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
  ['ExitCode', '32-bit process exit code.'],
  ['Bool', 'Boolean value.'],
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
  ['CSignedInt32', 'C ABI signed 32-bit integer.'],
  ['CSignedInt64', 'C ABI signed 64-bit integer.'],
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

const namedDeclarationVerbs = new Set([
  'project', 'operation', 'webServer', 'record', 'enum', 'error', 'codec',
  'jsonCodec', 'validator', 'mapper', 'adapter', 'boundary', 'policy',
  'errorPolicy', 'retryPolicy', 'timeoutBudget', 'resource', 'capability',
  'mutex', 'shared', 'channel', 'section', 'domainLiteral', 'literal',
  'listLiteral', 'listType', 'arrayType', 'sliceType', 'smallListType',
  'mapType', 'collectionOperation',
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

const candidateLinterPaths = (document) => {
  const candidates = [];
  const workspaceFolder = document ? vscode.workspace.getWorkspaceFolder(document.uri) : null;
  const addAncestorCandidates = (startPath) => {
    let currentPath = path.resolve(startPath);
    const rootPath = path.parse(currentPath).root;

    while (currentPath && currentPath !== rootPath) {
      candidates.push(path.join(currentPath, 'AgentScript', 'linter', 'aslint.py'));
      candidates.push(path.join(currentPath, 'linter', 'aslint.py'));
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
    candidates.push(path.join(folder.uri.fsPath, 'AgentScript', 'linter', 'aslint.py'));
    candidates.push(path.join(folder.uri.fsPath, 'linter', 'aslint.py'));
    candidates.push(path.join(folder.uri.fsPath, '..', 'AgentScript', 'linter', 'aslint.py'));
    addAncestorCandidates(folder.uri.fsPath);
  });

  if (document && document.fileName) {
    addAncestorCandidates(path.dirname(document.fileName));
  }

  candidates.push(path.join(__dirname, 'tools', 'aslint.py'));

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

const parseLinterDiagnostics = (document, stdout) => {
  let records;

  try {
    records = JSON.parse(stdout || '[]');
  } catch (_error) {
    return [
      new vscode.Diagnostic(
        new vscode.Range(0, 0, 0, Math.max(1, document.lineAt(0).text.length)),
        'aslint returned invalid JSON diagnostics.',
        vscode.DiagnosticSeverity.Error
      ),
    ];
  }

  if (!Array.isArray(records)) {
    return [];
  }

  return records.map((record) => {
    const diagnostic = new vscode.Diagnostic(
      diagnosticRange(document, record.line, record.column),
      record.message || String(record.rule || 'AgentScript lint diagnostic'),
      severityFromLinter(record.severity)
    );
    diagnostic.source = 'aslint';
    diagnostic.code = record.rule || undefined;
    return diagnostic;
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
    setLinterStatus('$(info) AgentScript future syntax', 'Current aslint is skipped for refined future syntax.');
    clearLinterStatusLater();
    return;
  }

  const linterPath = findLinterPath(document);

  if (!linterPath) {
    diagnosticCollection.delete(document.uri);

    if (showMissingLinterMessage) {
      vscode.window.showWarningMessage(
        'AgentScript linter not found. Set agentScript.linter.path or open the AgentScript repo root.'
      );
    }

    return;
  }

  setLinterStatus('$(sync~spin) AgentScript lint', document.fileName);

  const lintProcess = childProcess.spawn(
    linterPythonPath,
    [linterPath, document.fileName, '--format', 'json', '--fail-on', 'none'],
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
        `Failed to run aslint with ${linterPythonPath}: ${error.message}`,
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
