'use strict';

const childProcess = require('child_process');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

const declarationVerbs = new Set([
  'section',
  'project', 'target', 'runtime', 'entry', 'module', 'mode', 'languageMode', 'dependency', 'dependencyEffect',
  'dependencyExports', 'dependencyFunction', 'dependencyFunctionInput',
  'dependencyFunctionOutput', 'dependencyFunctionEffect', 'dependencyFunctionAsync',
  'buildProject', 'modulePath', 'languageVersion', 'sourceRoot', 'registerModule',
  'projectVersion', 'projectLicense', 'mainFile', 'mainOperation', 'testPattern', 'testRoot',
  'dependencySource', 'dependencyFetch', 'dependencyCache', 'dependencyLock', 'dependencyIntegrity',
  'targetRuntime', 'buildProfile', 'runtimeChecks', 'optLevel', 'persistLlvmIr',
  'emitLlvmIr', 'llvmIrOutput', 'emitOptimizedLlvmIr', 'optimizedLlvmIrOutput',
  'buildDir', 'buildRoot', 'buildFolderName',
  'cpuBaseline', 'cpuTune', 'cpuFeature', 'cpuFeatureCheck', 'nativeOutput',
  'nativeHttpHost', 'nativeHttpPort', 'formatterSetting', 'linterSetting', 'docsOutput',
  'comptimeOperation', 'moduleFolder', 'modulePurpose', 'moduleOwns',
  'moduleDoesNotOwn', 'moduleDependency', 'moduleWarning', 'moduleInvariant',
  'moduleSecurity', 'moduleObservability', 'exportType', 'exportError',
  'exportOperation', 'exportCapability', 'exportConstant',
  'version', 'publisher', 'description', 'copyright', 'productName',
  'internalName', 'originalFilename', 'trademark', 'comments', 'metadata',
  'importModule', 'importOperation', 'importType', 'importError',
  'importCapability', 'importConstant',
  'type', 'typeParameter', 'typeInvariant', 'typeRepresentation', 'typeTrust',
  'typeMemory', 'typeLayout', 'typeLiteralEncoding', 'typeLiteralTerminator',
  'record', 'recordLayout', 'recordAlign', 'field', 'fieldDefault', 'fieldInvariant',
  'enum', 'enumCase', 'error',
  'errorCase', 'operation', 'webServer', 'serverHost', 'serverPort', 'route',
  'routeTimeout', 'routeMiddleware', 'routeTimeoutOptOut', 'routeMiddlewareOptOut',
  'storage', 'sharedState', 'domainLiteral', 'jsonBody',
  'literal', 'listLiteral', 'htmlTemplate', 'jsonCodec', 'policy', 'errorPolicy',
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
  'purpose', 'invariant', 'warning', 'precondition', 'failure', 'guarantee', 'security',
  'timing', 'observability',
  'pinsNullBodyFailurePath', 'responseBodyForwarder', 'htmlArg', 'htmlBody', 'rationale',
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
  'set', 'call', 'arg', 'run', 'runChecked', 'start', 'await', 'bind', 'bindOk',
  'bindError', 'bindOwned', 'bindOkOwned', 'ignoreOk', 'ignoreValue',
  'declareFailure', 'makeError', 'requireNonNull',
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
  'returnValue', 'returnVoid',
]);

const roleSuffixPattern = /(Call|Error|Failed|Failure|Result|Option|Request|Response|Token|Timeout|Deadline|Defer|Group|Policy|Codec|Validator|Mapper|Adapter|Boundary|Resource|Capability|Authority|Channel|Mutex|Lock|Guard|State|Storage|Select|Record|Builder|Field|Enum|Variant|Template|Html|Document|Fragment|Class|Value|Counter|Count|Index|Length|Capacity|Allocator|Source|Target|Step|Accumulator|Divisor|Remainder|Span|Metric|Trace)$/;

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
  ['math.convertSignedInt32ToSignedInt64', 'Alias for math.signExtendCSignedInt32ToCSignedInt64.'],
  ['math.convertSignedInt64ToSignedInt32', 'Alias for math.truncateCSignedInt64ToCSignedInt32.'],
  ['math.signExtendCSignedInt32ToCSignedInt64', 'Explicit signed i32 to i64 conversion.'],
  ['math.truncateCSignedInt64ToCSignedInt32', 'Explicit signed i64 to i32 truncation. Caller owns range safety.'],
  ['math.equalCSignedInt32', 'C signed 32-bit equality comparison returning Bool.'],
  ['math.notEqualCSignedInt32', 'C signed 32-bit inequality comparison returning Bool.'],
  ['math.lessThanCSignedInt32', 'C signed 32-bit less-than comparison returning Bool.'],
  ['math.lessThanOrEqualCSignedInt32', 'C signed 32-bit less-than-or-equal comparison returning Bool.'],
  ['math.greaterThanCSignedInt32', 'C signed 32-bit greater-than comparison returning Bool.'],
  ['math.greaterThanOrEqualCSignedInt32', 'C signed 32-bit greater-than-or-equal comparison returning Bool.'],
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
  ['http.responseText', 'Native HTTP writer: response, status, body, optional contentType -> CSignedInt32. Body must be non-null.'],
  ['http.responseBytes', 'Native HTTP binary writer: response, status, body, bodyLength, optional contentType -> CSignedInt32. Preserves embedded NUL bytes.'],
  ['http.responseSseEvent', 'Native one-shot SSE writer: response, status, event, data -> CSignedInt32. Emits text/event-stream and closes the response.'],
  ['http.responseHeader', 'Native HTTP header writer: response, name, value -> CSignedInt32. Must run before the response body is sent.'],
  ['http.requestMethod', 'Native HTTP request reader: request -> non-null method string.'],
  ['http.requestPath', 'Native HTTP request reader: request -> non-null path string without query.'],
  ['http.requestHeader', 'Native nullable HTTP request header reader: request, name -> string or NULL. Guard before response body use.'],
  ['http.requestQueryParam', 'Native nullable query reader: request, name -> raw first matching value or NULL. Percent decoding is future work.'],
  ['http.requestBodyText', 'Native nullable body-text reader for bounded request bodies. Guard missing/empty bodies explicitly.'],
  ['http.requestBodyBytes', 'Native nullable body-bytes reader for bounded request bodies. Pair with http.requestBodyLength.'],
  ['http.requestBodyLength', 'Native body length reader: request -> CByteCount. Zero means no bytes.'],
  ['http.multipartPartText', 'Native nullable multipart text-part reader: request, name -> string or NULL.'],
  ['http.multipartPartBytes', 'Native nullable multipart binary-part reader: request, name -> pointer or NULL. Pair with http.multipartPartLength.'],
  ['http.multipartPartLength', 'Native multipart part length reader: request, name -> CByteCount.'],
  ['http.multipartPartFilename', 'Native nullable multipart filename reader: request, name -> string or NULL.'],
  ['http.multipartPartContentType', 'Native nullable multipart content-type reader: request, name -> string or NULL.'],
  ['gui.applicationCreate', 'Native GUI builder: title -> GuiApplication. Requires allocate gui.application.'],
  ['gui.windowCreate', 'Native GUI builder: title, width, height, layout, resizable -> GuiWindow. Requires allocate gui.window.'],
  ['gui.textLabelCreate', 'Native GUI builder: text -> GuiTextLabel. Requires allocate gui.control.'],
  ['gui.textBoxCreate', 'Native GUI builder: placeholder, maxLength -> GuiTextBox. Requires allocate gui.control.'],
  ['gui.buttonCreate', 'Native GUI builder: text, isDefault -> GuiButton. Requires allocate gui.control.'],
  ['gui.listBoxCreate', 'Native GUI builder: selectionMode -> GuiListBox. Requires allocate gui.control.'],
  ['gui.windowAddControl', 'Native GUI builder: window, control -> status. Requires write gui.window.'],
  ['gui.controlOnEvent', 'Native GUI event registration: control, eventKind, handler -> status. Requires write gui.control.event.'],
  ['gui.applicationSetMainWindow', 'Native GUI builder: application, window -> status. Requires write gui.window.'],
  ['gui.applicationRun', 'Native GUI runner: application -> status/ExitCode. Requires write gui.window.'],
  ['gui.textBoxText', 'Native GUI reader: session, textBox -> text. Requires read gui.control.textBox.text.'],
  ['gui.textBoxSetText', 'Native GUI writer: session, textBox, text -> status. Requires write gui.control.textBox.text.'],
  ['gui.listBoxSelectedIndex', 'Native GUI reader: session, listBox -> selected index. Requires read gui.control.listBox.selection.'],
  ['gui.listBoxAppendItem', 'Native GUI writer: session, listBox, text -> status. Requires write gui.control.listBox.items.'],
  ['gui.listBoxClear', 'Native GUI writer: session, listBox -> status. Requires write gui.control.listBox.items.'],
  ['gui.textLabelSetText', 'Native GUI writer: session, textLabel, text -> status. Requires write gui.control.textLabel.text.'],
  ['gui.windowClose', 'Native GUI writer: session, window -> status. Requires write gui.window.'],
  ['gui.eventKeyCode', 'Native GUI event reader: event -> key code. Requires read gui.event.'],
  ['gui.eventSelectedIndex', 'Native GUI event reader: event -> selected index. Requires read gui.event.'],
  ['gui.eventWindowWidth', 'Native GUI event reader: event -> window width. Requires read gui.event.'],
  ['gui.eventWindowHeight', 'Native GUI event reader: event -> window height. Requires read gui.event.'],
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

const generatedTargetPattern = /^(?:json\.(?:parse|stringify)\.[A-Z][A-Za-z0-9_]*|html\.hydrate\.[A-Z][A-Za-z0-9_]*)$/;
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
    if (text.startsWith('json.parse.')) {
      return 'Reference compiler primitive JSON parse target. Numeric values use libc parsing, Bool compares against true, and malformed inputs return the libc default.';
    }

    if (text.startsWith('json.stringify.')) {
      return 'Reference compiler primitive JSON stringify target. Numerics and Bool use direct formatting; strings are quoted with full escaping deferred to the codec runtime.';
    }
  }

  if (text.startsWith('json.parse.')) {
    return 'Generated JSON parse target backed by record metadata and the native document runtime.';
  }

  if (text.startsWith('json.stringify.')) {
    return 'Generated JSON stringify target backed by record metadata and the native document runtime.';
  }

  if (text.startsWith('html.hydrate.')) {
    return 'Generated HTML template hydration target. It is declared by htmlTemplate/htmlArg/htmlBody rows and lowers explicit arg rows into one hydrated HtmlDocument or HtmlFragment value.';
  }

  return 'Generated SemanticScript target declared by metadata.';
};

const schemaValues = new Map([
  ['true', 'Boolean literal token.'],
  ['false', 'Boolean literal token.'],
  ['yes', 'Boolean schema value.'],
  ['no', 'Boolean schema value.'],
  ['capturedOutputReplay', 'Mode marker for programs that replay captured output.'],
  ['strictExecutable', 'Language mode that closes unknown lowercase executable verbs.'],
  ['refinedSyntax', 'Language mode for research/metadata files that keep permissive lowercase rows.'],
  ['local', 'Storage scope for operation-local storage.'],
  ['module', 'Storage scope for module-owned storage.'],
  ['process', 'Storage scope for process-shared state.'],
  ['sharedState', 'Shared-state storage scope. Reads and writes require guard-token authority.'],
  ['immutable', 'Storage mutability: value cannot be changed after declaration.'],
  ['mutable', 'Storage mutability: value can change through explicit set lines.'],
  ['read', 'Effect or collection role mode: read.'],
  ['write', 'Effect or collection role mode: write.'],
  ['log', 'Effect mode: log/observability output.'],
  ['sourceTape', 'operationBody kind for normal explicit SemanticScript semantic tape.'],
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
  ['github', 'Dependency fetch kind for a GitHub owner/repo/ref source.'],
  ['http', 'Dependency fetch kind for an HTTPS archive or API source. Plain HTTP URLs are rejected.'],
  ['as', 'Legacy importModule alias separator. Prefer importModule ALIAS MODULE_PATH in new code.'],
  ['dev', 'Build profile that keeps development diagnostics visible.'],
  ['prod', 'Build profile that hides source context and favors release defaults.'],
  ['auto', 'Toolchain policy: let the compiler choose from build.sem and platform context.'],
  ['windowsGui', 'Windows desktop GUI target runtime. Use entry console plus standard.gui gui.* calls.'],
  ['verticalStack', 'GUI window layout token: stack child controls vertically.'],
  ['horizontalStack', 'GUI window layout token: stack child controls horizontally.'],
  ['grid', 'GUI window layout token: arrange controls in a grid.'],
  ['absolute', 'GUI window layout token: use explicit control positions.'],
  ['single', 'GUI list-box selection mode: one selected item.'],
  ['multiple', 'GUI list-box selection mode: multiple selected items.'],
  ['click', 'GUI event token.'],
  ['valueChanged', 'GUI event token.'],
  ['selectionChanged', 'GUI event token.'],
  ['enterPressed', 'GUI event token.'],
  ['keyPressed', 'GUI event token.'],
  ['focusGained', 'GUI event token.'],
  ['focusLost', 'GUI event token.'],
  ['closeRequested', 'GUI event token.'],
  ['resized', 'GUI event token.'],
  ['shown', 'GUI event token.'],
  ['hidden', 'GUI event token.'],
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
  ['HtmlText', 'Escaped HTML text value safe for text content and quoted attributes during template hydration.'],
  ['HtmlClass', 'HTML class attribute value. Template sink checks require this for class attributes.'],
  ['SafeUrl', 'Trusted URL value for URL-bearing HTML attributes such as href, src, action, formaction, and poster.'],
  ['HtmlFragment', 'Hydrated HTML fragment inserted raw only into text-content positions.'],
  ['HtmlTrustedFragment', 'Trusted HTML fragment inserted raw only into text-content positions.'],
  ['HtmlDocument', 'Full hydrated HTML document value produced by html.hydrate.* targets.'],
  ['GuiApplication', 'Opaque Windows GUI application handle returned by gui.applicationCreate.'],
  ['GuiSession', 'Opaque GUI session input passed to GUI event handlers.'],
  ['GuiEvent', 'Opaque GUI event input passed to GUI event handlers.'],
  ['GuiWindow', 'Opaque Windows GUI window handle returned by gui.windowCreate.'],
  ['GuiControl', 'Common opaque GUI control handle.'],
  ['GuiButton', 'Opaque GUI button handle returned by gui.buttonCreate.'],
  ['GuiTextBox', 'Opaque GUI text-box handle returned by gui.textBoxCreate.'],
  ['GuiListBox', 'Opaque GUI list-box handle returned by gui.listBoxCreate.'],
  ['GuiCheckBox', 'Opaque GUI check-box handle reserved for future standard.gui functions.'],
  ['GuiMenuItem', 'Opaque GUI menu-item handle reserved for future standard.gui functions.'],
  ['GuiStatusBar', 'Opaque GUI status-bar handle reserved for future standard.gui functions.'],
  ['GuiTextLabel', 'Opaque GUI text-label handle returned by gui.textLabelCreate.'],
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
  ['HttpResponse', 'Opaque HTTP response dependency token. Native web handlers receive this explicitly.'],
  ['HttpStatus', 'HTTP status value, currently represented by a C signed 32-bit integer in native calls.'],
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
  ['module', 'Top-level module declaration. Validated as a dotted namespace and recorded in compiler metadata.'],
  ['mode', 'Top-level mode declaration such as mode capturedOutputReplay.'],
  ['languageMode', 'Top-level language mode declaration: languageMode strictExecutable or languageMode refinedSyntax.'],
  ['buildProject', 'Build tape declaration: buildProject PROJECT.'],
  ['modulePath', 'Build tape project path: modulePath PROJECT MODULE_PATH.'],
  ['languageVersion', 'Build tape language contract: languageVersion PROJECT "VERSION".'],
  ['projectVersion', 'Build tape release metadata: projectVersion PROJECT "VERSION".'],
  ['projectLicense', 'Build tape license metadata: projectLicense PROJECT LICENSE.'],
  ['sourceRoot', 'Build tape source root: sourceRoot PROJECT "PATH".'],
  ['registerModule', 'Build tape module registry: registerModule PROJECT MODULE_PATH "PATH". Module imports should target registered modules.'],
  ['mainFile', 'Build tape executable source: mainFile PROJECT "main.sem".'],
  ['mainOperation', 'Build tape native executable entry: mainOperation PROJECT OPERATION.'],
  ['testRoot', 'Build tape test root: testRoot PROJECT "PATH".'],
  ['testPattern', 'Build tape test glob: testPattern PROJECT "*.test.sem".'],
  ['targetRuntime', 'Build tape runtime target: targetRuntime PROJECT nativeExe|webServer|library|windowsGui.'],
  ['buildProfile', 'Build tape profile: buildProfile PROJECT dev|prod.'],
  ['runtimeChecks', 'Build tape runtime checks: runtimeChecks PROJECT off|traps|panic.'],
  ['optLevel', 'Build tape LLVM optimization level: optLevel PROJECT 0|1|2|3.'],
  ['persistLlvmIr', 'Build tape LLVM IR persistence: persistLlvmIr PROJECT auto|yes|no.'],
  ['emitLlvmIr', 'Build tape pre-optimization LLVM IR switch: emitLlvmIr PROJECT auto|yes|no.'],
  ['llvmIrOutput', 'Build tape pre-optimization LLVM IR output path. Basenames use the managed build folder.'],
  ['emitOptimizedLlvmIr', 'Build tape optimized LLVM IR switch for run/JIT: emitOptimizedLlvmIr PROJECT yes|no.'],
  ['optimizedLlvmIrOutput', 'Build tape optimized LLVM IR output path. Basenames use the managed build folder.'],
  ['buildDir', 'Build tape exact artifact directory: buildDir PROJECT "PATH".'],
  ['buildRoot', 'Build tape artifact parent directory: buildRoot PROJECT "PATH".'],
  ['buildFolderName', 'Build tape managed artifact folder name: buildFolderName PROJECT NAME.'],
  ['cpuBaseline', 'Build tape CPU baseline: cpuBaseline PROJECT generic|native|x86_64_v2|x86_64_v3|x86_64_v4|arm64_generic|arm64_v8_2.'],
  ['cpuTune', 'Build tape CPU tune token: cpuTune PROJECT generic|native|CPU_NAME.'],
  ['cpuFeature', 'Build tape CPU feature override: cpuFeature PROJECT FEATURE on|off.'],
  ['cpuFeatureCheck', 'Build tape host CPU check policy: cpuFeatureCheck PROJECT auto|off|warn|require.'],
  ['nativeOutput', 'Build tape native executable output: nativeOutput PROJECT "PATH". Basenames use the managed build folder.'],
  ['nativeHttpHost', 'Build tape native webserver host metadata: nativeHttpHost PROJECT "HOST".'],
  ['nativeHttpPort', 'Build tape native webserver port metadata: nativeHttpPort PROJECT PORT.'],
  ['formatterSetting', 'Build tape formatter setting: formatterSetting PROJECT KEY VALUE.'],
  ['linterSetting', 'Build tape linter setting: linterSetting PROJECT KEY VALUE.'],
  ['docsOutput', 'Build tape documentation output: docsOutput PROJECT "PATH".'],
  ['moduleFolder', 'Compatibility module registry alias. Prefer registerModule PROJECT MODULE_PATH "PATH".'],
  ['exportType', 'Module-local export contract: exportType MODULE_PATH TYPE. Belongs in the module source.'],
  ['exportError', 'Module-local export contract: exportError MODULE_PATH ERROR. Belongs in the module source.'],
  ['exportOperation', 'Module-local export contract: exportOperation MODULE_PATH OPERATION. Belongs in the module source.'],
  ['exportCapability', 'Module-local export contract: exportCapability MODULE_PATH CAPABILITY. Belongs in the module source.'],
  ['exportConstant', 'Module-local export contract: exportConstant MODULE_PATH CONSTANT. Belongs in the module source.'],
  ['version', 'Project metadata: version "A.B.C.D". Lowered to OS-native VERSIONINFO when emitting an executable.'],
  ['publisher', 'Project metadata: publisher/company name for executable VERSIONINFO.'],
  ['description', 'Project metadata: file description for executable VERSIONINFO.'],
  ['copyright', 'Project metadata: legal copyright for executable VERSIONINFO.'],
  ['productName', 'Project metadata: product name for executable VERSIONINFO.'],
  ['internalName', 'Project metadata: internal executable name for VERSIONINFO.'],
  ['originalFilename', 'Project metadata: original executable filename for VERSIONINFO.'],
  ['trademark', 'Project metadata: legal trademark for executable VERSIONINFO.'],
  ['comments', 'Project metadata: comments field for executable VERSIONINFO.'],
  ['metadata', 'Project metadata: metadata "key" "value" adds a custom VERSIONINFO string-table entry.'],
  ['dependency', 'Dependency declaration. Dependency contract metadata is parsed for tooling context.'],
  ['dependencySource', 'Build tape dependency source metadata: dependencySource PROJECT ALIAS KIND LOCATION.'],
  ['dependencyFetch', 'Build tape remote dependency fetch edge: dependencyFetch PROJECT ALIAS github OWNER/REPO REF or dependencyFetch PROJECT ALIAS http "https://...".'],
  ['dependencyCache', 'Build tape dependency cache directory: dependencyCache PROJECT ".semcache".'],
  ['dependencyLock', 'Build tape dependency lock tape path: dependencyLock PROJECT "sem.lock".'],
  ['dependencyEffect', 'Dependency effect declaration.'],
  ['dependencyExports', 'Dependency export declaration.'],
  ['dependencyFunction', 'Dependency function declaration metadata.'],
  ['dependencyFunctionInput', 'Dependency function input metadata.'],
  ['dependencyFunctionOutput', 'Dependency function output metadata.'],
  ['dependencyFunctionEffect', 'Dependency function effect metadata.'],
  ['dependencyFunctionAsync', 'Dependency function async metadata.'],
  ['importModule', 'Import declaration: importModule LOCAL_ALIAS MODULE_PATH. The older MODULE_PATH as ALIAS form may exist in legacy samples.'],
  ['importOperation', 'Singular import declaration: importOperation LOCAL_NAME MODULE_ALIAS EXPORTED_OPERATION.'],
  ['importType', 'Singular import declaration: importType LOCAL_NAME MODULE_ALIAS EXPORTED_TYPE.'],
  ['importError', 'Singular import declaration: importError LOCAL_NAME MODULE_ALIAS EXPORTED_ERROR.'],
  ['importCapability', 'Singular import declaration: importCapability LOCAL_NAME MODULE_ALIAS EXPORTED_CAPABILITY.'],
  ['importConstant', 'Singular import declaration: importConstant LOCAL_NAME MODULE_ALIAS EXPORTED_CONSTANT.'],
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
  ['webServer', 'Web server declaration: webServer NAME. Native codegen can lower this target into an HTTP/1.1 executable.'],
  ['serverHost', 'Web server metadata: serverHost SERVER_NAME "host".'],
  ['serverPort', 'Web server metadata: serverPort SERVER_NAME PORT.'],
  ['route', 'Web server route: route SERVER METHOD PATH HANDLER_OPERATION.'],
  ['routeTimeout', 'Web server route timeout metadata keyed by exact route path. Parsed today; preemptive enforcement is future runtime work.'],
  ['routeMiddleware', 'Web server route middleware metadata keyed by exact route path. Native codegen invokes the middleware before the handler.'],
  ['routeTimeoutOptOut', 'Web server route timeout opt-out: routeTimeoutOptOut SERVER PATH "rationale". Used by semlint route coverage checks.'],
  ['routeMiddlewareOptOut', 'Web server route middleware opt-out: routeMiddlewareOptOut SERVER PATH "rationale". Used by semlint route coverage checks.'],
  ['htmlTemplate', 'First-class HTML/SSX template declaration: htmlTemplate NAME. The body starts at htmlBody NAME.'],
  ['htmlArg', 'HTML template hydration input: htmlArg TEMPLATE ARG_NAME TYPE. Body holes must reference declared args as {htmlArg.ARG_NAME}.'],
  ['htmlBody', 'Starts the indentation-sensitive HTML/SSX body island for a template. The island ends at the next non-empty column-0 SemanticScript line.'],
  ['jsonBody', 'Starts an indentation-sensitive JSON literal island bound to a preceding immutable storage binding with the same name.'],
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
  ['precondition', 'Hard metadata: declares a caller-side proof obligation that the operation body does not enforce.'],
  ['failure', 'Hard metadata: declares a named failure and explanation.'],
  ['guarantee', 'Hard metadata: declares a guarantee attached to an operation or abstraction.'],
  ['security', 'Hard metadata: declares security context agents must preserve.'],
  ['timing', 'Hard metadata: declares timing behavior or constraints.'],
  ['observability', 'Hard metadata: declares trace/log/metric context.'],
  ['pinsNullBodyFailurePath', 'Operation metadata: explicit opt-in to the native HTTP null-body failure path. Requires a rationale string.'],
  ['responseBodyForwarder', 'Operation metadata: declares that an operation forwards a named body input into an http.response* writer.'],
  ['rationale', 'Call-site rationale: rationale CALL "text". Attaches context to one call so diagnostics survive refactors.'],
  ['const', 'Body declaration statement: const NAME TYPE VALUE.'],
  ['var', 'Body declaration statement: var NAME TYPE INITIAL_VALUE.'],
  ['label', 'Control-flow statement: label NAME. Labels are first-class basic blocks.'],
  ['call', 'Call lifecycle statement: call CALL_NAME TARGET_PATH.'],
  ['arg', 'Call lifecycle statement: arg CALL_NAME ARG_NAME VALUE_NAME.'],
  ['timeout', 'Call lifecycle statement: timeout CALL_NAME DURATION_VALUE.'],
  ['cancelOn', 'Call lifecycle statement: cancelOn CALL_NAME CANCELLATION_TOKEN.'],
  ['run', 'Call lifecycle statement: execute call immediately.'],
  ['runChecked', 'Strict checked-call statement: runChecked CALL ok VALUE TYPE error ERROR TYPE else LABEL. Current compiler support is limited to the committed checked-call lowering/tests.'],
  ['start', 'Call lifecycle statement: begin async work. Parsed by current compiler.'],
  ['await', 'Call lifecycle statement: wait for started async work. Parsed by current compiler.'],
  ['bind', 'Binding statement for infallible calls: bind VALUE TYPE CALL_NAME.'],
  ['bindOk', 'Binding statement for success leg: bindOk VALUE TYPE CALL_NAME.'],
  ['bindError', 'Binding statement for failure leg: bindError ERROR ERROR_TYPE CALL_NAME. Must pair with branchIfError.'],
  ['bindOwned', 'Reserved strict ownership statement: bindOwned VALUE TYPE CALL cleanup TARGET. Do not use until parser and ownership-table support are committed.'],
  ['bindOkOwned', 'Reserved strict ownership statement for fallible calls: bindOkOwned VALUE TYPE CALL cleanup TARGET. Do not use until parser and ownership-table support are committed.'],
  ['ignoreOk', 'Binding statement: ignoreOk CALL_NAME TYPE explicitly discards a fallible call success value.'],
  ['ignoreValue', 'Binding statement: ignoreValue CALL_NAME TYPE explicitly discards an infallible call result.'],
  ['requireNonNull', 'Reserved strict nullable-refinement statement: requireNonNull OUT TYPE INPUT else LABEL. Do not use until nullable ABI support is committed.'],
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
  ['returnVoid', 'Return from a Void/CVoid operation without exposing the ABI zero sentinel.'],
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
  'semanticscriptDeclarationVerb',
  'semanticscriptContextVerb',
  'semanticscriptActionVerb',
  'semanticscriptControlVerb',
  'semanticscriptRoleSuffix',
  'semanticscriptPrimitiveTarget',
  'semanticscriptGeneratedTarget',
  'semanticscriptDomainTarget',
  'semanticscriptErrorVariant',
  'semanticscriptSchemaValue',
  'semanticscriptOpaqueInput',
  'semanticscriptDeclaredName',
  'semanticscriptConstName',
  'semanticscriptMutableName',
  'semanticscriptCallObject',
  'semanticscriptArgumentName',
  'semanticscriptLabelName',
  'semanticscriptEffectPath',
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
let linterSkipFutureSyntax = false;
let linterEngine = 'semlint';
let compilerPythonPath = 'python';
let compilerConfiguredPath = '';
let compilerOutputDirectory = '';
let compilerBuildProfile = 'dev';
let compilerRuntimeChecks = 'default';
let compilerPersistLlvmIr = 'auto';
let compilerOptLevel = 'default';
let compilerEmitLlvmIr = false;
let compilerBuildDir = '';
let compilerBuildRoot = '';
let compilerBuildFolderName = '';
let compilerCpuBaseline = 'default';
let compilerCpuTune = '';
let compilerCpuFeatureCheck = 'default';
let diagnosticCollection = null;
let lintStatusBarItem = null;
let compilerOutputChannel = null;
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

const isHtmlBodyContentLine = (lineText) => {
  if (lineText.trim().length === 0) {
    return true;
  }

  return lineText.startsWith(' ') || lineText.startsWith('\t');
};

const isIndentedIslandContentLine = isHtmlBodyContentLine;
const indentedIslandVerbs = new Set(['htmlBody', 'jsonBody']);

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
  if (!editor || editor.document.languageId !== 'semanticscript') {
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

  let insideIndentedIsland = false;

  for (let lineIndex = 0; lineIndex < editor.document.lineCount; lineIndex += 1) {
    const line = editor.document.lineAt(lineIndex);

    if (insideIndentedIsland) {
      if (isIndentedIslandContentLine(line.text)) {
        continue;
      }

      insideIndentedIsland = false;
    }

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

      if (indentedIslandVerbs.has(verbText)) {
        insideIndentedIsland = true;
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
  'purpose', 'invariant', 'warning', 'precondition', 'failure', 'guarantee', 'security',
  'timing', 'observability', 'authority', 'runtimeBinding',
  'pinsNullBodyFailurePath', 'responseBodyForwarder',
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
  'purpose', 'invariant', 'warning', 'precondition', 'failure', 'guarantee', 'security',
  'timing', 'observability', 'authority', 'runtimeBinding',
  'pinsNullBodyFailurePath', 'responseBodyForwarder',
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
  'mutex', 'shared', 'channel', 'section', 'domainLiteral', 'literal', 'jsonBody',
  'listLiteral', 'htmlTemplate', 'listType', 'arrayType', 'sliceType', 'smallListType',
  'mapType', 'collectionOperation', 'interval', 'workerPool', 'work',
  'buildProject', 'registerModule', 'modulePath', 'mainFile', 'mainOperation',
  'targetRuntime', 'buildProfile', 'optLevel', 'cpuBaseline', 'cpuTune',
  'cpuFeature', 'cpuFeatureCheck', 'nativeOutput',
]);

const singleCallReferenceVerbs = new Set([
  'run', 'start', 'await', 'timeout', 'cancelOn', 'ignoreOk', 'ignoreValue',
  'useRetry', 'recordBuild', 'rationale',
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
  let insideIndentedIsland = false;

  for (let lineIndex = 0; lineIndex < document.lineCount; lineIndex += 1) {
    const lineText = document.lineAt(lineIndex).text;

    if (insideIndentedIsland) {
      if (isIndentedIslandContentLine(lineText)) {
        continue;
      }

      insideIndentedIsland = false;
    }

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

    if (indentedIslandVerbs.has(verb)) {
      insideIndentedIsland = true;
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
  let insideIndentedIsland = false;

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

    if (insideIndentedIsland) {
      if (isIndentedIslandContentLine(lineText)) {
        lineOperations.set(lineIndex, currentOperation);
        continue;
      }

      insideIndentedIsland = false;
    }

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
      case 'jsonBody':
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
      case 'importOperation':
      case 'importType':
      case 'importError':
      case 'importCapability':
      case 'importConstant':
      case 'codec':
      case 'jsonCodec':
      case 'htmlTemplate':
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

      case 'importModule': {
        const aliasIndex = importModuleAliasIndex(tokens);
        const pathIndex = importModulePathIndex(tokens);
        addSymbolDeclaration(symbols, tokenText(tokens, aliasIndex), declarationBase('module import', tokens, lineIndex, {
          name: tokenText(tokens, aliasIndex),
          details: tokenText(tokens, pathIndex),
        }));
        break;
      }

      case 'dependencyFetch':
        addSymbolDeclaration(symbols, tokenText(tokens, 2), declarationBase('dependency fetch', tokens, lineIndex, {
          name: tokenText(tokens, 2),
          owner: tokenText(tokens, 1),
          details: tokenTailText(tokens, 3),
        }));
        break;

      case 'dependencyCache':
      case 'dependencyLock':
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

      case 'htmlArg':
        addSymbolDeclaration(symbols, tokenText(tokens, 2), declarationBase('html template argument', tokens, lineIndex, {
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

    if (indentedIslandVerbs.has(verb)) {
      insideIndentedIsland = true;
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
    return 'semanticscriptConstName';
  }

  if (verb === 'var' && index === 1) {
    return 'semanticscriptMutableName';
  }

  if (verb === 'type' && index === 1) {
    return 'semanticscriptDeclaredName';
  }

  if (verb === 'htmlTemplate' && index === 1) {
    return 'semanticscriptDeclaredName';
  }

  if ((verb === 'htmlArg' || verb === 'htmlBody') && index === 1) {
    return 'semanticscriptDeclaredName';
  }

  if (verb === 'jsonBody' && index === 1) {
    return 'semanticscriptConstName';
  }

  if (verb === 'htmlArg' && index === 2) {
    return 'semanticscriptArgumentName';
  }

  if (verb === 'importModule') {
    if (index === importModuleAliasIndex(tokens)) {
      return 'semanticscriptDeclaredName';
    }

    if (index === importModulePathIndex(tokens)) {
      return 'namespace';
    }

    return null;
  }

  if (['importOperation', 'importType', 'importError', 'importCapability', 'importConstant'].includes(verb) && index === 1) {
    return 'semanticscriptDeclaredName';
  }

  if (verb === 'dependencyFetch' && index === 2) {
    return 'semanticscriptDeclaredName';
  }

  if ((verb === 'enumCase' || verb === 'errorCase') && index === 2) {
    return 'semanticscriptDeclaredName';
  }

  if ((verb === 'field' || verb === 'fieldDefault' || verb === 'fieldInvariant') && index === 2) {
    return 'semanticscriptArgumentName';
  }

  if (verb === 'typeParameter' && index === 2 && (text === 'success' || text === 'error')) {
    return 'semanticscriptSchemaValue';
  }

  if (verb === 'storage' && index === 3) {
    return tokens[2] && tokens[2].text === 'mutable'
      ? 'semanticscriptMutableName'
      : 'semanticscriptConstName';
  }

  if (verb === 'sharedState' && index === 3) {
    return 'semanticscriptMutableName';
  }

  if (verb === 'set' && index === 1 && !['local', 'module', 'sharedState'].includes(text)) {
    return 'semanticscriptMutableName';
  }

  if (verb === 'set' && index === 2 && tokens[1] && ['local', 'module', 'sharedState'].includes(tokens[1].text)) {
    return 'semanticscriptMutableName';
  }

  if (verb === 'read' && index === 2 && tokens[1] && tokens[1].text === 'sharedState') {
    return 'semanticscriptDeclaredName';
  }

  if (verb === 'label' && index === 1) {
    return 'semanticscriptLabelName';
  }

  if (branchLabelPositions.get(verb) === index) {
    return 'semanticscriptLabelName';
  }

  if (verb === 'call' && index === 1) {
    return 'semanticscriptCallObject';
  }

  if (verb === 'recordBuild' && index === 1) {
    return 'semanticscriptCallObject';
  }

  if (verb === 'recordBuildFailure' && index === 1) {
    return 'semanticscriptCallObject';
  }

  if (verb === 'memoryAllocationSource' && index === 2) {
    return 'semanticscriptCallObject';
  }

  if (verb === 'recordBuilder' && index === 1) {
    return 'semanticscriptDeclaredName';
  }

  if (verb === 'arg' && index === 1) {
    return 'semanticscriptCallObject';
  }

  if (verb === 'arg' && index === 2) {
    return 'semanticscriptArgumentName';
  }

  if (singleCallReferenceVerbs.has(verb) && index === 1) {
    return 'semanticscriptCallObject';
  }

  if ((verb === 'bind' || verb === 'bindOk' || verb === 'bindError') && index === 3) {
    return 'semanticscriptCallObject';
  }

  if ((verb === 'bind' || verb === 'bindOk') && index === 1) {
    return 'semanticscriptConstName';
  }

  if (verb === 'bindError' && index === 1) {
    return 'semanticscriptMutableName';
  }

  if ((verb === 'makeError' || verb === 'declareFailure') && index === 1) {
    return 'semanticscriptMutableName';
  }

  if (verb === 'input' && index === 2) {
    return 'semanticscriptArgumentName';
  }

  if (verb === 'fieldGet' && index === 1) {
    return 'semanticscriptConstName';
  }

  if (verb === 'fieldGet' && index === 4) {
    return 'semanticscriptArgumentName';
  }

  if (verb === 'fieldSet' && index === 1) {
    return 'semanticscriptConstName';
  }

  if (verb === 'fieldSet' && index === 4) {
    return 'semanticscriptArgumentName';
  }

  if (verb === 'recordCopy' && index === 1) {
    return 'semanticscriptDeclaredName';
  }

  if (verb === 'workArg' && index === 1) {
    return 'semanticscriptDeclaredName';
  }

  if (verb === 'workArg' && index === 2) {
    return 'semanticscriptArgumentName';
  }

  if (verb === 'work' && index === 2 && text === 'target') {
    return 'semanticscriptSchemaValue';
  }

  if (verb === 'work' && index === 3 && tokens[2] && tokens[2].text === 'target') {
    return 'semanticscriptDeclaredName';
  }

  if ((verb === 'startInterval' || verb === 'awaitIntervalTick' || verb === 'awaitWork') && index === 1) {
    return 'semanticscriptDeclaredName';
  }

  if (verb === 'submitWork' && (index === 1 || index === 2)) {
    return 'semanticscriptDeclaredName';
  }

  if (verb === 'recordSet' && index === 2) {
    return 'semanticscriptArgumentName';
  }

  if (verb === 'guardTokenSource' && index === 2) {
    return 'semanticscriptCallObject';
  }

  if (verb === 'guardTokenRelease' && index === 2) {
    return 'semanticscriptDeclaredName';
  }

  if (namedDeclarationVerbs.has(verb) && index === 1) {
    return 'semanticscriptDeclaredName';
  }

  if (operationReferenceVerbs.has(verb) && index === 1) {
    return 'semanticscriptDeclaredName';
  }

  if (verb === 'collectionOperationArg' && index === 2) {
    return 'semanticscriptArgumentName';
  }

  if (verb === 'jsonCodecInput' && index === 3) {
    return 'semanticscriptArgumentName';
  }

  if (verb === 'jsonCodecRequiredField' && index === 2) {
    return 'semanticscriptArgumentName';
  }

  if (verb.startsWith('group') && index === 1) {
    return 'semanticscriptDeclaredName';
  }

  if ((verb.startsWith('defer') || verb === 'guardTokenRelease') && index === 1) {
    return 'semanticscriptDeclaredName';
  }

  if ((verb === 'deferLog' || verb === 'deferAwaitLog') && index === 2) {
    return 'semanticscriptDeclaredName';
  }

  if (verb === 'deferWhenExitLog' && index === 3) {
    return 'semanticscriptDeclaredName';
  }

  if ((verb === 'deferLogSink' || verb === 'deferAwaitLogSink' || verb === 'deferWhenExitLogSink') && index === 2 && isLowerQualifiedName(text)) {
    return 'semanticscriptEffectPath';
  }

  if ((verb === 'effect' || verb === 'dependencyEffect') && index >= 3 && /^[a-z][A-Za-z0-9_]*(?:\.[a-zA-Z_][A-Za-z0-9_]*)*$/.test(text)) {
    return 'semanticscriptEffectPath';
  }

  if ((verb === 'runtimeBinding' || verb === 'dependencyPath' || verb === 'intrinsicName') && index === 2 && isLowerQualifiedName(text)) {
    return 'semanticscriptEffectPath';
  }

  if (verb === 'collectionOperationEffect' && index === 3 && /^[a-z][A-Za-z0-9_]*(?:\.[a-zA-Z_][A-Za-z0-9_]*)*$/.test(text)) {
    return 'semanticscriptEffectPath';
  }

  if ((verb === 'capability' || verb === 'authority') && index === 2 && isLowerQualifiedName(text)) {
    return 'semanticscriptEffectPath';
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

  if (['equal', 'notEqual', 'lessThan', 'lessThanOrEqual', 'greaterThan', 'greaterThanOrEqual'].includes(methodName)) {
    return 'SYNTAX.md: enum/domain comparison methods preserve the declared type in source. For repr-backed enums the compiler resolves this to the matching width-specific math target, with no implicit widening at the call site.';
  }

  return 'AST.md: `TypeName.methodName` lowers to an underlying primitive based on the alias type while preserving domain context in source.';
};

const tokenTypeForSymbol = (text, index, tokens) => {
  if (index === 0) {
    const classification = classifyVerb(text);

    if (classification === 'declaration') {
      return 'semanticscriptDeclarationVerb';
    }

    if (classification === 'context') {
      return 'semanticscriptContextVerb';
    }

    if (classification === 'action') {
      return 'semanticscriptActionVerb';
    }

    if (classification === 'control') {
      return 'semanticscriptControlVerb';
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
    return 'semanticscriptSchemaValue';
  }

  if (opaqueInputs.has(text)) {
    return 'semanticscriptOpaqueInput';
  }

  if (primitiveTargets.has(text)) {
    return 'semanticscriptPrimitiveTarget';
  }

  if (cRuntimeTargetPattern.test(text)) {
    return 'semanticscriptPrimitiveTarget';
  }

  if (generatedTargetPattern.test(text)) {
    return 'semanticscriptGeneratedTarget';
  }

  if (isDomainTarget(text)) {
    return 'semanticscriptDomainTarget';
  }

  if (/^[A-Z][A-Za-z0-9_]*\.[A-Z][A-Za-z0-9_]*$/.test(text)) {
    return 'semanticscriptErrorVariant';
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
  'semanticscriptDeclaredName',
  'semanticscriptConstName',
  'semanticscriptMutableName',
  'semanticscriptCallObject',
  'semanticscriptArgumentName',
  'semanticscriptLabelName',
  'variable',
]);

const canSplitRoleSuffix = (tokenType) => roleSuffixBaseTokenTypes.has(tokenType);

const provideDocumentSemanticTokens = (document) => {
  const builder = new vscode.SemanticTokensBuilder(semanticLegend);
  let insideIndentedIsland = false;

  for (let lineIndex = 0; lineIndex < document.lineCount; lineIndex += 1) {
    const lineText = document.lineAt(lineIndex).text;

    if (insideIndentedIsland) {
      if (isIndentedIslandContentLine(lineText)) {
        continue;
      }

      insideIndentedIsland = false;
    }

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

        builder.push(lineIndex, suffixStart, suffixMatch[0].length, 'semanticscriptRoleSuffix', []);
        return;
      }

      if (tokenType) {
        builder.push(lineIndex, token.start, token.length, tokenType, []);
      }
    });

    if (tokens[0] && indentedIslandVerbs.has(tokens[0].text)) {
      insideIndentedIsland = true;
    }
  }

  return builder.build();
};

const registerSemanticTokens = (context) => {
  const provider = {
    provideDocumentSemanticTokens,
  };

  context.subscriptions.push(
    vscode.languages.registerDocumentSemanticTokensProvider(
      { language: 'semanticscript' },
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

const getHtmlArgReferenceAtPosition = (document, position) => {
  const lineText = document.lineAt(position.line).text;
  const referencePattern = /\{\s*htmlArg\.([A-Za-z_][A-Za-z0-9_]*)\s*\}/g;
  let match;

  while ((match = referencePattern.exec(lineText)) !== null) {
    const start = match.index;
    const end = match.index + match[0].length;

    if (position.character >= start && position.character <= end) {
      return {
        text: match[1],
        range: new vscode.Range(position.line, start, position.line, end),
      };
    }
  }

  return null;
};

const htmlBodyTemplateAtLine = (document, targetLine) => {
  let insideHtmlBody = false;
  let templateName = null;

  for (let lineIndex = 0; lineIndex <= targetLine; lineIndex += 1) {
    const lineText = document.lineAt(lineIndex).text;

    if (insideHtmlBody) {
      if (isHtmlBodyContentLine(lineText)) {
        if (lineIndex === targetLine) {
          return templateName;
        }

        continue;
      }

      insideHtmlBody = false;
      templateName = null;
    }

    const tokens = tokenizeLine(lineText);

    if (tokens[0] && tokens[0].text === 'htmlBody' && tokens[1]) {
      insideHtmlBody = true;
      templateName = tokens[1].text;

      if (lineIndex === targetLine) {
        return templateName;
      }
    }
  }

  return null;
};

const chooseHtmlArgDeclaration = (document, argName, lineIndex) => {
  const index = getDocumentSymbolIndex(document);
  const entry = index.symbols.get(argName);

  if (!entry) {
    return null;
  }

  const templateName = htmlBodyTemplateAtLine(document, lineIndex);
  const htmlArgDeclarations = entry.declarations.filter((declaration) => declaration.kind === 'html template argument');

  if (templateName) {
    return htmlArgDeclarations.find((declaration) => declaration.owner === templateName)
      || htmlArgDeclarations[0]
      || null;
  }

  return htmlArgDeclarations[0] || null;
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

const importModuleAliasIndex = (tokens) => (
  tokens[2] && tokens[2].text === 'as' && tokens[3] ? 3 : 1
);

const importModulePathIndex = (tokens) => (
  tokens[2] && tokens[2].text === 'as' && tokens[3] ? 1 : 2
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

    case 'importModule':
      return detailHover(`Module import: ${tokenText(tokens, importModuleAliasIndex(tokens))}`, [
        `Local alias: ${inlineCode(tokenText(tokens, importModuleAliasIndex(tokens)))}`,
        `Module path: ${inlineCode(tokenText(tokens, importModulePathIndex(tokens)))}`,
        'Registered module imports make cross-module references explicit for agents and tooling.',
      ]);

    case 'importOperation':
    case 'importType':
    case 'importError':
    case 'importCapability':
    case 'importConstant':
      return detailHover(`${readableVerbName(verb)}: ${tokenText(tokens, 1)}`, [
        `Local name: ${inlineCode(tokenText(tokens, 1))}`,
        `Provider alias: ${inlineCode(tokenText(tokens, 2))}`,
        `Exported name: ${inlineCode(tokenText(tokens, 3))}`,
        'Singular imports expose only one declared export instead of importing the provider module wholesale.',
      ]);

    case 'dependencyFetch':
      return detailHover(`Dependency fetch: ${tokenText(tokens, 2)}`, [
        `Project: ${inlineCode(tokenText(tokens, 1))}`,
        `Alias: ${inlineCode(tokenText(tokens, 2))}`,
        `Fetch kind: ${inlineCode(tokenText(tokens, 3))}`,
        `Source: ${inlineCode(tokenTailText(tokens, 4))}`,
      ]);

    case 'dependencyCache':
    case 'dependencyLock':
      return detailHover(`${readableVerbName(verb)}: ${tokenText(tokens, 1)}`, [
        `Project: ${inlineCode(tokenText(tokens, 1))}`,
        `Path: ${inlineCode(tokenTailText(tokens, 2))}`,
      ]);

    case 'htmlTemplate':
      return detailHover(`HTML template: ${tokenText(tokens, 1)}`, [
        `Declares first-class HTML/SSX template ${inlineCode(tokenText(tokens, 1))}.`,
        'Follow with explicit `htmlArg` rows and exactly one `htmlBody` island for the same template name.',
      ]);

    case 'htmlArg':
      return detailHover(`HTML argument: ${tokenText(tokens, 2)}`, [
        `Template: ${inlineCode(tokenText(tokens, 1))}`,
        `Argument: ${inlineCode(tokenText(tokens, 2))}`,
        `Type: ${inlineCode(tokenText(tokens, 3))}`,
        'Inside the body, dynamic holes must reference this as `{htmlArg.NAME}`.',
      ]);

    case 'htmlBody':
      return detailHover(`HTML body: ${tokenText(tokens, 1)}`, [
        `Starts the HTML/SSX body for template ${inlineCode(tokenText(tokens, 1))}.`,
        'Indented following lines are parsed as markup until the next non-empty column-0 SemanticScript line.',
      ]);

    case 'jsonBody':
      return detailHover(`JSON body: ${tokenText(tokens, 1)}`, [
        `Binds validated JSON text to immutable storage ${inlineCode(tokenText(tokens, 1))}.`,
        'Indented following lines are parsed as strict JSON until the next non-empty column-0 SemanticScript line.',
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
    case 'precondition':
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

    case 'returnVoid':
      return detailHover('Return void', [
        'Returns from an operation declared `output OP Void` or `output OP CVoid`.',
        'Codegen lowers this to the internal zero sentinel, but the source stays semantically explicit.',
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
    case 'version':
    case 'publisher':
    case 'description':
    case 'copyright':
    case 'productName':
    case 'internalName':
    case 'originalFilename':
    case 'trademark':
    case 'comments':
    case 'metadata':
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

    case 'jsonBody':
      if (tokenIndex === 1) {
        return `This token selects the immutable storage slot that receives the validated JSON literal.`;
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

    case 'returnVoid':
      if (tokenIndex === 0) {
        return `Explicit Void/CVoid return form.`;
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
    markdown.appendCodeblock(declaration.text, 'semanticscript');
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
    markdown.appendCodeblock(codeLines.join('\n'), 'semanticscript');
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
    'SemanticScript role suffixes are context markers. They tell agents and tools what semantic kind a symbol represents.'
  );
};

const provideHover = (document, position) => {
  const htmlArgReference = getHtmlArgReferenceAtPosition(document, position);

  if (htmlArgReference) {
    const declaration = chooseHtmlArgDeclaration(document, htmlArgReference.text, position.line);
    const templateName = declaration ? declaration.owner : htmlBodyTemplateAtLine(document, position.line);

    return markdownHover(
      `HTML arg reference: ${htmlArgReference.text}`,
      [
        templateName ? `Template: ${inlineCode(templateName)}` : '',
        declaration && declaration.type ? `Declared type: ${inlineCode(declaration.type)}` : '',
        'Dynamic HTML holes must resolve to a declared `htmlArg TEMPLATE NAME TYPE` row. The compiler checks sink context before lowering hydration.',
      ].filter(Boolean).join('\n\n')
    );
  }

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
    return markdownHover(`SemanticScript verb: ${text}`, verbHoverText.get(text));
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
      { language: 'semanticscript' },
      { provideHover }
    )
  );
};

const declarationRange = (document, declaration) => {
  const line = document.lineAt(declaration.lineIndex);
  const start = Math.max(0, line.text.indexOf(declaration.name));
  return new vscode.Range(
    declaration.lineIndex,
    start,
    declaration.lineIndex,
    Math.min(line.text.length, start + declaration.name.length)
  );
};

const provideDefinition = (document, position) => {
  const htmlArgReference = getHtmlArgReferenceAtPosition(document, position);

  if (htmlArgReference) {
    const declaration = chooseHtmlArgDeclaration(document, htmlArgReference.text, position.line);

    if (declaration) {
      return new vscode.Location(document.uri, declarationRange(document, declaration));
    }
  }

  const tokenInfo = getTokenAtPosition(document, position);

  if (!tokenInfo || tokenInfo.tokenIndex === 0) {
    return null;
  }

  const text = tokenInfo.token.text;

  if (!isSymbolLike(text) || schemaValues.has(text)) {
    return null;
  }

  const index = getDocumentSymbolIndex(document);
  const currentOperation = index.lineOperations.get(position.line) || null;
  const entry = index.symbols.get(text);
  const declaration = chooseSymbolDeclaration(entry, currentOperation);

  if (!declaration) {
    return null;
  }

  return new vscode.Location(document.uri, declarationRange(document, declaration));
};

const documentSymbolNameIndex = (verb, tokens) => {
  switch (verb) {
    case 'input':
      return 2;
    case 'htmlArg':
      return 2;
    case 'dependencyFetch':
      return 2;
    case 'importModule':
      return importModuleAliasIndex(tokens);
    case 'field':
    case 'enumCase':
    case 'errorCase':
      return 2;
    case 'route':
      return 2;
    case 'storage':
    case 'sharedState':
      return 3;
    default:
      return 1;
  }
};

const documentSymbolKind = (verb) => {
  switch (verb) {
    case 'operation':
      return vscode.SymbolKind.Function;
    case 'htmlTemplate':
      return vscode.SymbolKind.Class;
    case 'htmlArg':
      return vscode.SymbolKind.Field;
    case 'importModule':
      return vscode.SymbolKind.Module;
    case 'importOperation':
      return vscode.SymbolKind.Function;
    case 'importType':
      return vscode.SymbolKind.TypeParameter;
    case 'importError':
      return vscode.SymbolKind.Enum;
    case 'importCapability':
      return vscode.SymbolKind.Key;
    case 'importConstant':
      return vscode.SymbolKind.Constant;
    case 'webServer':
      return vscode.SymbolKind.Namespace;
    case 'route':
      return vscode.SymbolKind.Event;
    case 'record':
      return vscode.SymbolKind.Struct;
    case 'field':
      return vscode.SymbolKind.Field;
    case 'enum':
    case 'enumCase':
      return vscode.SymbolKind.Enum;
    case 'error':
    case 'errorCase':
      return vscode.SymbolKind.EnumMember;
    case 'type':
      return vscode.SymbolKind.TypeParameter;
    case 'capability':
    case 'authority':
      return vscode.SymbolKind.Key;
    case 'const':
    case 'jsonBody':
      return vscode.SymbolKind.Constant;
    case 'var':
    case 'storage':
    case 'sharedState':
      return vscode.SymbolKind.Variable;
    case 'call':
      return vscode.SymbolKind.Object;
    case 'label':
      return vscode.SymbolKind.Boolean;
    case 'section':
      return vscode.SymbolKind.Module;
    default:
      return vscode.SymbolKind.String;
  }
};

const symbolDetailText = (verb, tokens) => {
  if (verb === 'route') {
    return `${tokenText(tokens, 3)} -> ${tokenText(tokens, 4)}`;
  }

  if (verb === 'htmlArg') {
    return `${tokenText(tokens, 1)}: ${tokenText(tokens, 3)}`;
  }

  if (verb === 'importModule') {
    return tokenText(tokens, importModulePathIndex(tokens));
  }

  if (['importOperation', 'importType', 'importError', 'importCapability', 'importConstant'].includes(verb)) {
    return `${tokenText(tokens, 2)}.${tokenText(tokens, 3)}`;
  }

  if (verb === 'dependencyFetch') {
    return `${tokenText(tokens, 3)} ${tokenTailText(tokens, 4)}`;
  }

  if (verb === 'call') {
    return tokenText(tokens, 2);
  }

  if (verb === 'input') {
    return `${tokenText(tokens, 1)}: ${tokenText(tokens, 3)}`;
  }

  if (verb === 'const' || verb === 'var') {
    return tokenText(tokens, 2);
  }

  if (verb === 'jsonBody') {
    return 'JsonText island';
  }

  return tokenTailText(tokens, 2);
};

const provideDocumentSymbols = (document) => {
  const symbols = [];
  const symbolVerbs = new Set([
    'section', 'project', 'target', 'runtime', 'entry', 'module',
    'buildProject', 'modulePath', 'projectVersion', 'projectLicense',
    'sourceRoot', 'registerModule', 'mainFile', 'mainOperation',
    'targetRuntime', 'buildProfile', 'runtimeChecks', 'optLevel',
    'persistLlvmIr', 'emitLlvmIr', 'llvmIrOutput', 'buildDir',
    'buildRoot', 'buildFolderName', 'cpuBaseline', 'cpuTune',
    'cpuFeature', 'cpuFeatureCheck', 'nativeOutput', 'docsOutput',
    'dependencyFetch', 'dependencyCache', 'dependencyLock',
    'importModule', 'importOperation', 'importType', 'importError',
    'importCapability', 'importConstant',
    'exportOperation', 'exportType',
    'exportError', 'exportCapability', 'exportConstant',
    'operation', 'input', 'webServer', 'route', 'record', 'field',
    'enum', 'enumCase', 'error', 'errorCase', 'type', 'capability',
    'authority', 'timeoutBudget', 'storage', 'sharedState', 'const',
    'var', 'call', 'label', 'jsonCodec', 'jsonBody', 'policy', 'retryPolicy',
    'workerPool', 'work', 'interval', 'htmlTemplate', 'htmlArg',
  ]);
  let insideIndentedIsland = false;

  for (let lineIndex = 0; lineIndex < document.lineCount; lineIndex += 1) {
    const line = document.lineAt(lineIndex);

    if (insideIndentedIsland) {
      if (isIndentedIslandContentLine(line.text)) {
        continue;
      }

      insideIndentedIsland = false;
    }

    const tokens = tokenizeLine(line.text);

    if (tokens.length === 0 || tokens[0].text.startsWith('#')) {
      continue;
    }

    const verb = tokens[0].text;

    if (!symbolVerbs.has(verb)) {
      continue;
    }

    const nameToken = verb === 'route' ? tokens[3] : tokens[documentSymbolNameIndex(verb, tokens)];

    if (!nameToken) {
      continue;
    }

    const displayName = verb === 'route'
      ? `${tokenText(tokens, 2)} ${tokenText(tokens, 3)}`
      : nameToken.text;

    const selectionRange = new vscode.Range(
      lineIndex,
      nameToken.start,
      lineIndex,
      nameToken.start + nameToken.length
    );
    symbols.push(new vscode.DocumentSymbol(
      displayName,
      symbolDetailText(verb, tokens),
      documentSymbolKind(verb),
      line.range,
      selectionRange
    ));

    if (indentedIslandVerbs.has(verb)) {
      insideIndentedIsland = true;
    }
  }

  return symbols;
};

const completionItem = (label, kind, detail, documentation = '') => {
  const item = new vscode.CompletionItem(label, kind);
  item.detail = detail;

  if (documentation) {
    item.documentation = documentation;
  }

  return item;
};

const verbCompletionItems = () => {
  const items = [];
  const addVerbs = (verbs, kind, detail) => {
    Array.from(verbs).sort().forEach((verb) => {
      items.push(completionItem(verb, kind, detail, verbHoverText.get(verb) || ''));
    });
  };

  addVerbs(declarationVerbs, vscode.CompletionItemKind.Keyword, 'SemanticScript declaration verb');
  addVerbs(contextVerbs, vscode.CompletionItemKind.Property, 'SemanticScript context verb');
  addVerbs(actionVerbs, vscode.CompletionItemKind.Function, 'SemanticScript action verb');
  addVerbs(controlVerbs, vscode.CompletionItemKind.Event, 'SemanticScript control-flow verb');

  return items;
};

const primitiveCompletionItems = () => (
  Array.from(primitiveTargets.entries()).sort(([left], [right]) => left.localeCompare(right)).map(([target, detail]) => (
    completionItem(target, vscode.CompletionItemKind.Function, 'SemanticScript primitive target', detail)
  ))
);

const generatedCompletionItems = (document) => {
  const targets = new Map();

  for (let lineIndex = 0; lineIndex < document.lineCount; lineIndex += 1) {
    const tokens = tokenizeLine(document.lineAt(lineIndex).text);

    if (tokens[0] && tokens[0].text === 'htmlTemplate' && tokens[1]) {
      const target = `html.hydrate.${tokens[1].text}`;
      targets.set(target, generatedTargetHoverText(target));
    }
  }

  return Array.from(targets.entries()).sort(([left], [right]) => left.localeCompare(right)).map(([target, detail]) => (
    completionItem(target, vscode.CompletionItemKind.Function, 'SemanticScript generated target', detail)
  ));
};

const symbolCompletionItems = (document, position) => {
  const index = getDocumentSymbolIndex(document);
  const currentOperation = index.lineOperations.get(position.line) || null;
  const items = [];

  Array.from(index.symbols.entries()).sort(([left], [right]) => left.localeCompare(right)).forEach(([name, entry]) => {
    const declaration = chooseSymbolDeclaration(entry, currentOperation);

    if (!declaration) {
      return;
    }

    items.push(completionItem(
      name,
      vscode.CompletionItemKind.Variable,
      declarationKindTitle(declaration),
      declaration.text || ''
    ));
  });

  return items;
};

const provideCompletions = (document, position) => {
  const line = document.lineAt(position.line);
  const prefix = line.text.slice(0, position.character);
  const tokens = tokenizeLine(line.text);

  if (/^\s*[A-Za-z_]*$/.test(prefix)) {
    return verbCompletionItems();
  }

  if (tokens[0] && tokens[0].text === 'call' && tokens.length <= 3) {
    return primitiveCompletionItems().concat(generatedCompletionItems(document));
  }

  return symbolCompletionItems(document, position);
};

const registerLanguageNavigation = (context) => {
  const selector = { language: 'semanticscript' };

  context.subscriptions.push(
    vscode.languages.registerDefinitionProvider(selector, { provideDefinition }),
    vscode.languages.registerDocumentSymbolProvider(selector, { provideDocumentSymbols }),
    vscode.languages.registerCompletionItemProvider(selector, { provideCompletionItems: provideCompletions }, '.', '"')
  );
};

const syncConfiguration = () => {
  const segmentConfig = vscode.workspace.getConfiguration('semanticScript.segmentColors');
  segmentColoringEnabled = segmentConfig.get('enabled', true);
  segmentColorMode = segmentConfig.get('colorMode', 'background');

  const linterConfig = vscode.workspace.getConfiguration('semanticScript.linter');
  linterEnabled = linterConfig.get('enabled', true);
  linterRunMode = linterConfig.get('run', 'onSave');
  linterPythonPath = linterConfig.get('pythonPath', 'python');
  linterConfiguredPath = linterConfig.get('path', '');
  linterSkipFutureSyntax = linterConfig.get('skipFutureSyntax', false);
  linterEngine = linterConfig.get('engine', 'semlint');

  const compilerConfig = vscode.workspace.getConfiguration('semanticScript.compiler');
  compilerPythonPath = compilerConfig.get('pythonPath', 'python');
  compilerConfiguredPath = compilerConfig.get('path', '');
  compilerOutputDirectory = compilerConfig.get('outputDirectory', '');
  compilerBuildProfile = compilerConfig.get('buildProfile', 'dev');
  compilerRuntimeChecks = compilerConfig.get('runtimeChecks', 'default');
  compilerPersistLlvmIr = compilerConfig.get('persistLlvmIr', 'auto');
  compilerOptLevel = compilerConfig.get('optLevel', 'default');
  compilerEmitLlvmIr = compilerConfig.get('emitLlvmIr', false);
  compilerBuildDir = compilerConfig.get('buildDir', '');
  compilerBuildRoot = compilerConfig.get('buildRoot', '');
  compilerBuildFolderName = compilerConfig.get('buildFolderName', '');
  compilerCpuBaseline = compilerConfig.get('cpuBaseline', 'default');
  compilerCpuTune = compilerConfig.get('cpuTune', '');
  compilerCpuFeatureCheck = compilerConfig.get('cpuFeatureCheck', 'default');
};

const isSemanticScriptDocument = (document) => (
  document && document.languageId === 'semanticscript' && document.uri.scheme === 'file'
);

const isBuildTapePath = (filePath) => {
  const baseName = path.basename(filePath || '').toLowerCase();
  return baseName === 'build.sem' || baseName === 'build.sscript';
};

const findNearestBuildTapePath = (startPath) => {
  if (!startPath) {
    return null;
  }

  let currentPath = path.resolve(startPath);
  if (fs.existsSync(currentPath) && fs.statSync(currentPath).isFile()) {
    if (isBuildTapePath(currentPath)) {
      return currentPath;
    }
    currentPath = path.dirname(currentPath);
  }

  const rootPath = path.parse(currentPath).root;
  while (currentPath && currentPath !== rootPath) {
    for (const buildName of ['build.sem', 'build.sscript']) {
      const candidate = path.join(currentPath, buildName);
      if (fs.existsSync(candidate)) {
        return candidate;
      }
    }
    currentPath = path.dirname(currentPath);
  }

  return null;
};

const projectRootForDocument = (document) => {
  const buildTapePath = document && document.fileName ? findNearestBuildTapePath(document.fileName) : null;
  if (buildTapePath) {
    return path.dirname(buildTapePath);
  }
  return document && document.fileName ? path.dirname(document.fileName) : undefined;
};

const documentUsesFutureSyntax = (document) => {
  const text = document.getText();

  if (
    text.includes('future refined syntax')
    || text.includes('not current executable SemanticScript')
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

const linterScriptName = () => 'semlint.py';

const candidateLinterPaths = (document) => {
  const candidates = [];
  const workspaceFolder = document ? vscode.workspace.getWorkspaceFolder(document.uri) : null;
  const scriptName = linterScriptName();
  const addAncestorCandidates = (startPath) => {
    let currentPath = path.resolve(startPath);
    const rootPath = path.parse(currentPath).root;

    while (currentPath && currentPath !== rootPath) {
      candidates.push(path.join(currentPath, 'SemanticScript', 'linter', scriptName));
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
    candidates.push(path.join(folder.uri.fsPath, 'SemanticScript', 'linter', scriptName));
    candidates.push(path.join(folder.uri.fsPath, 'linter', scriptName));
    candidates.push(path.join(folder.uri.fsPath, '..', 'SemanticScript', 'linter', scriptName));
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

const semlintMessage = (record) => {
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

  return parts.join(' - ') || 'SemanticScript lint diagnostic';
};

const diagnosticFromSemlintRecord = (document, record) => {
  const primary = record.primary || {};
  const diagnostic = new vscode.Diagnostic(
    diagnosticRange(document, primary.line, primary.column),
    semlintMessage(record),
    severityFromLinter(record.severity)
  );
  diagnostic.source = 'semlint';
  diagnostic.code = record.code || undefined;
  return diagnostic;
};

const diagnosticFromSimpleSemlintRecord = (document, record) => {
  const diagnostic = new vscode.Diagnostic(
    diagnosticRange(document, record.line, record.column),
    record.message || String(record.rule || 'SemanticScript lint diagnostic'),
    severityFromLinter(record.severity)
  );
  diagnostic.source = 'semlint';
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
      return diagnosticFromSemlintRecord(document, record);
    }

    return diagnosticFromSimpleSemlintRecord(document, record || {});
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
  if (!diagnosticCollection || !isSemanticScriptDocument(document)) {
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

  if (linterSkipFutureSyntax && linterEngine === 'semlint' && documentUsesFutureSyntax(document)) {
    diagnosticCollection.delete(document.uri);
    setLinterStatus('$(info) SemanticScript future syntax', 'stable semlint is skipped for refined future syntax.');
    clearLinterStatusLater();
    return;
  }

  const linterPath = findLinterPath(document);

  if (!linterPath) {
    diagnosticCollection.delete(document.uri);

    if (showMissingLinterMessage) {
      vscode.window.showWarningMessage(
        `SemanticScript ${linterEngine} linter not found. Set semanticScript.linter.path or open the SemanticScript repo root.`
      );
    }

    return;
  }

  setLinterStatus('$(sync~spin) SemanticScript lint', document.fileName);
  const linterArgs = [linterPath, document.fileName, '--format', 'json'];

  const lintProcess = childProcess.spawn(
    linterPythonPath,
    linterArgs,
    {
      cwd: projectRootForDocument(document)
        || vscode.workspace.getWorkspaceFolder(document.uri)?.uri.fsPath
        || path.dirname(document.fileName),
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
    setLinterStatus('$(error) SemanticScript lint failed', error.message);
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
      setLinterStatus('$(error) SemanticScript lint failed', stderr.trim());
      clearLinterStatusLater();
      return;
    }

    const diagnostics = parseLinterDiagnostics(document, stdout);
    diagnosticCollection.set(document.uri, diagnostics);

    if (diagnostics.length > 0) {
      setLinterStatus(`$(warning) SemanticScript lint ${diagnostics.length}`, `${diagnostics.length} diagnostic(s)`);
    } else {
      setLinterStatus('$(check) SemanticScript lint clean', document.fileName);
    }

    clearLinterStatusLater();
  });
};

const scheduleLinterRun = (document, delayMilliseconds = 350) => {
  if (!isSemanticScriptDocument(document)) {
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
  diagnosticCollection = vscode.languages.createDiagnosticCollection('semlint');
  lintStatusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  lintStatusBarItem.command = 'semanticscript.runLinter';

  context.subscriptions.push(diagnosticCollection, lintStatusBarItem);

  context.subscriptions.push(
    vscode.commands.registerCommand('semanticscript.runLinter', () => {
      const editor = vscode.window.activeTextEditor;

      if (!editor || !isSemanticScriptDocument(editor.document)) {
        vscode.window.showInformationMessage('Open a SemanticScript file to run the linter.');
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

const candidateCompilerPaths = (document) => {
  const candidates = [];
  const workspaceFolder = document ? vscode.workspace.getWorkspaceFolder(document.uri) : null;
  const addAncestorCandidates = (startPath) => {
    let currentPath = path.resolve(startPath);
    const rootPath = path.parse(currentPath).root;

    while (currentPath && currentPath !== rootPath) {
      candidates.push(path.join(currentPath, 'SemanticScript', 'compiler', 'semsc.py'));
      candidates.push(path.join(currentPath, 'compiler', 'semsc.py'));
      currentPath = path.dirname(currentPath);
    }
  };

  if (compilerConfiguredPath) {
    if (path.isAbsolute(compilerConfiguredPath)) {
      candidates.push(compilerConfiguredPath);
    } else if (workspaceFolder) {
      candidates.push(path.join(workspaceFolder.uri.fsPath, compilerConfiguredPath));
    }
  }

  const workspaceFolders = vscode.workspace.workspaceFolders || [];
  workspaceFolders.forEach((folder) => {
    candidates.push(path.join(folder.uri.fsPath, 'SemanticScript', 'compiler', 'semsc.py'));
    candidates.push(path.join(folder.uri.fsPath, 'compiler', 'semsc.py'));
    candidates.push(path.join(folder.uri.fsPath, '..', 'SemanticScript', 'compiler', 'semsc.py'));
    addAncestorCandidates(folder.uri.fsPath);
  });

  if (document && document.fileName) {
    addAncestorCandidates(path.dirname(document.fileName));
  }

  candidates.push(path.join(__dirname, 'tools', 'semsc.py'));

  return candidates;
};

const findCompilerPath = (document) => {
  const seen = new Set();

  for (const candidate of candidateCompilerPaths(document)) {
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

const compilerOutputPath = (document) => {
  const workspaceFolder = vscode.workspace.getWorkspaceFolder(document.uri);
  const sourceDirectory = path.dirname(document.fileName);
  const outputBase = `${path.basename(document.fileName, path.extname(document.fileName))}${process.platform === 'win32' ? '.exe' : ''}`;
  let outputDirectory = path.join(sourceDirectory, 'build');

  if (compilerOutputDirectory) {
    outputDirectory = path.isAbsolute(compilerOutputDirectory)
      ? compilerOutputDirectory
      : path.join(workspaceFolder ? workspaceFolder.uri.fsPath : sourceDirectory, compilerOutputDirectory);
  }

  fs.mkdirSync(outputDirectory, { recursive: true });
  return path.join(outputDirectory, outputBase);
};

const appendCompilerOutput = (label, text) => {
  if (!compilerOutputChannel || !text.trim()) {
    return;
  }

  compilerOutputChannel.appendLine(label);
  compilerOutputChannel.appendLine(text.trim());
};

const runCompilerForDocument = async (document) => {
  if (!isSemanticScriptDocument(document)) {
    vscode.window.showInformationMessage('Open a SemanticScript file to compile.');
    return;
  }

  syncConfiguration();

  if (document.isDirty) {
    await document.save();
  }

  const compilerPath = findCompilerPath(document);

  if (!compilerPath) {
    vscode.window.showWarningMessage('SemanticScript compiler not found. Set semanticScript.compiler.path or open the SemanticScript repo root.');
    return;
  }

  const buildTapePath = findNearestBuildTapePath(document.fileName);
  const compileSourcePath = buildTapePath || document.fileName;
  const useCompilerManagedOutput = Boolean(buildTapePath) || isBuildTapePath(document.fileName);
  const outputPath = useCompilerManagedOutput ? null : compilerOutputPath(document);
  const cwd = buildTapePath
    ? path.dirname(buildTapePath)
    : (vscode.workspace.getWorkspaceFolder(document.uri)?.uri.fsPath || path.dirname(document.fileName));
  const args = [
    compilerPath,
    compileSourcePath,
    '--emit-exe',
    '--build-profile',
    compilerBuildProfile,
    '--persist-llvm-ir',
    compilerPersistLlvmIr,
  ];

  if (outputPath) {
    args.splice(3, 0, outputPath);
  }

  if (compilerRuntimeChecks !== 'default') {
    args.push('--runtime-checks', compilerRuntimeChecks);
  }

  if (compilerOptLevel !== 'default') {
    args.push('--opt-level', String(compilerOptLevel));
  }

  if (compilerEmitLlvmIr) {
    args.push('--emit-ir');
  }

  if (compilerCpuBaseline !== 'default') {
    args.push('--cpu-baseline', compilerCpuBaseline);
  }

  if (compilerCpuTune) {
    args.push('--cpu-tune', compilerCpuTune);
  }

  if (compilerCpuFeatureCheck !== 'default') {
    args.push('--cpu-feature-check', compilerCpuFeatureCheck);
  }

  if (compilerBuildDir) {
    args.push('--build-dir', compilerBuildDir);
  } else {
    if (compilerBuildRoot) {
      args.push('--build-root', compilerBuildRoot);
    }
    if (compilerBuildFolderName) {
      args.push('--build-folder-name', compilerBuildFolderName);
    }
  }

  compilerOutputChannel.clear();
  compilerOutputChannel.appendLine(`SemanticScript compile: ${compileSourcePath}`);
  if (buildTapePath && buildTapePath !== document.fileName) {
    compilerOutputChannel.appendLine(`project source: ${document.fileName}`);
  }
  compilerOutputChannel.appendLine(`${compilerPythonPath} ${args.map((arg) => (arg.includes(' ') ? `"${arg}"` : arg)).join(' ')}`);

  const compileProcess = childProcess.spawn(
    compilerPythonPath,
    args,
    {
      cwd,
      windowsHide: true,
    }
  );

  let stdout = '';
  let stderr = '';

  compileProcess.stdout.on('data', (chunk) => {
    stdout += chunk.toString();
  });

  compileProcess.stderr.on('data', (chunk) => {
    stderr += chunk.toString();
  });

  compileProcess.on('error', (error) => {
    compilerOutputChannel.show(true);
    appendCompilerOutput('error:', error.message);
    vscode.window.showErrorMessage(`SemanticScript compile failed: ${error.message}`);
  });

  compileProcess.on('close', (code) => {
    appendCompilerOutput('stdout:', stdout);
    appendCompilerOutput('stderr:', stderr);

    if (code === 0) {
      const compiledTarget = outputPath || 'compiler-managed build output';
      compilerOutputChannel.appendLine(`ok: ${compiledTarget}`);
      vscode.window.showInformationMessage(
        outputPath
          ? `SemanticScript compiled: ${path.basename(outputPath)}`
          : 'SemanticScript compiled to build output'
      );
      return;
    }

    compilerOutputChannel.show(true);
    vscode.window.showErrorMessage(`SemanticScript compile failed with exit code ${code}.`);
  });
};

const registerCompiler = (context) => {
  compilerOutputChannel = vscode.window.createOutputChannel('SemanticScript Compiler');
  context.subscriptions.push(compilerOutputChannel);

  context.subscriptions.push(
    vscode.commands.registerCommand('semanticscript.compileCurrentFile', () => {
      const editor = vscode.window.activeTextEditor;

      if (!editor || !isSemanticScriptDocument(editor.document)) {
        vscode.window.showInformationMessage('Open a SemanticScript file to compile.');
        return;
      }

      runCompilerForDocument(editor.document);
    })
  );
};

const activate = (context) => {
  syncConfiguration();
  disposeDecorations();
  decorations = createDecorations();
  verbDecorations = createVerbDecorations();
  registerSemanticTokens(context);
  registerHovers(context);
  registerLanguageNavigation(context);
  registerLinter(context);
  registerCompiler(context);

  context.subscriptions.push({
    dispose: disposeDecorations,
  });

  context.subscriptions.push(
    vscode.commands.registerCommand('semanticscript.toggleSegmentColors', () => {
      segmentColoringEnabled = !segmentColoringEnabled;
      vscode.window.visibleTextEditors.forEach(updateSegmentDecorations);
      vscode.window.showInformationMessage(`SemanticScript segment colors ${segmentColoringEnabled ? 'enabled' : 'disabled'}.`);
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
      if (
        event.affectsConfiguration('semanticScript.segmentColors')
        || event.affectsConfiguration('semanticScript.linter')
        || event.affectsConfiguration('semanticScript.compiler')
      ) {
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
