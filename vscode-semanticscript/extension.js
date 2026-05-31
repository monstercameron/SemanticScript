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
  'targetRuntime', 'guiBackend', 'buildProfile', 'runtimeChecks', 'asyncRuntime', 'optLevel', 'persistLlvmIr',
  'emitLlvmIr', 'llvmIrOutput', 'emitOptimizedLlvmIr', 'optimizedLlvmIrOutput',
  'buildDir', 'buildRoot', 'buildFolderName',
  'cpuBaseline', 'cpuTune', 'cpuFeature', 'cpuFeatureCheck', 'nativeOutput',
  'keepResources', 'resourcesDir', 'nativeHttpHost', 'nativeHttpPort',
  'formatterSetting', 'linterSetting', 'docsOutput', 'buildConstant',
  'iconRoleDefinition', 'icon', 'iconRole', 'iconPurpose',
  'iconImage', 'iconImageGroup', 'iconImagePath', 'iconImageFormat',
  'iconImageWidth', 'iconImageHeight', 'iconImageScale',
  'iconImageDepth', 'iconImagePlatform', 'iconImagePurpose',
  'comptimeOperation', 'moduleFolder', 'modulePurpose', 'moduleOwns',
  'moduleDoesNotOwn', 'moduleDependency', 'moduleWarning', 'moduleInvariant',
  'moduleSecurity', 'moduleObservability', 'nativeRuntimeSource',
  'nativeRuntimeLinkArg', 'exportType', 'exportError',
  'exportOperation', 'exportCapability', 'exportConstant',
  'version', 'publisher', 'description', 'copyright', 'productName',
  'internalName', 'originalFilename', 'trademark', 'comments', 'metadata',
  'import', 'importModule', 'importOperation', 'importType', 'importError',
  'importCapability', 'importConstant',
  'type', 'typeParameter', 'typeInvariant', 'typeRepresentation', 'typeTrust',
  'typeMemory', 'typeLayout', 'typeLiteralEncoding', 'typeLiteralTerminator',
  'record', 'recordLayout', 'recordAlign', 'field', 'fieldDefault', 'fieldInvariant',
  'recordFieldJsonName', 'recordFieldJsonOmitWhen',
  'enum', 'enumCase', 'error',
  'errorCase', 'operation', 'webServer', 'serverHost', 'serverPort', 'route',
  'routeNotFound', 'routeMethodNotAllowed',
  'webServerStartup', 'webServerShutdown',
  'routeTimeout', 'routeMiddleware', 'routeTimeoutOptOut', 'routeMiddlewareOptOut',
  'storage', 'sharedState', 'domainLiteral', 'json', 'jsonBody', 'sql', 'sqlBody',
  'literal', 'listLiteral', 'html', 'htmlTemplate', 'jsonCodec', 'policy', 'errorPolicy',
  'validator', 'codec', 'schema', 'unknownFields', 'resource', 'resourceKey',
  'resourceValue', 'resourceKind', 'adapter', 'boundary', 'mapper', 'retryPolicy',
  'timeoutBudget', 'capability', 'authority', 'mutex', 'shared', 'channel',
  'listType', 'arrayType', 'sliceType', 'smallListType', 'mapType',
  'interval', 'workerPool', 'work',
  'const', 'var', 'let', 'testCovers',
]);

const contextVerbs = new Set([
  'input', 'output', 'effect', 'memory', 'memoryHeap', 'memoryArena',
  'memoryAllocationSource', 'memoryStackLimit', 'async', 'operationBody',
  'purpose', 'invariant', 'warning', 'precondition', 'failure', 'guarantee', 'security',
  'timing', 'observability',
  'pinsNullBodyFailurePath', 'responseBodyForwarder', 'htmlArg', 'htmlBody', 'rationale',
  'dependencyPath', 'dependencyFailure', 'intrinsicName',
  'runtimeBinding', 'runtimeBindingPrecondition', 'runtimeBindingFailure',
  'runtimeBindingAsyncStart', 'runtimeBindingAsyncAwait',
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
  'set', 'call', 'arg', 'argument', 'run', 'runChecked', 'start', 'await', 'case', 'done', 'bind', 'bindOk',
  'bindError', 'bindOwned', 'bindOkOwned', 'ignore', 'ignoreOk', 'ignoreValue', 'ignoreError',
  'declareFailure', 'makeError', 'requireNonNull',
  'new', 'fieldGet', 'fieldSet', 'recordBuilder', 'recordSet', 'recordCopy',
  'recordBuild', 'read', 'timeout', 'cancelOn',
  'defer', 'deferLog', 'deferAwaitLog', 'deferWhenExitLog', 'select', 'selectCase',
  'runSelect', 'taskGroup', 'startInGroup', 'awaitGroup', 'bindGroupError',
  'send', 'receive', 'lock', 'unlock', 'useRetry', 'useCapability',
  'startInterval', 'awaitIntervalTick', 'submitWork', 'awaitWork',
]);

const controlVerbs = new Set([
  'label', 'branch', 'jump', 'branchIf', 'branchIfError', 'branchSelected',
  'branchIfGroupError', 'branchIfChannelClosed', 'return', 'returnOk', 'returnError',
  'returnValue', 'returnVoid',
]);

const roleSuffixPattern = /(Call|Error|Failed|Failure|Result|Option|Request|Response|Token|Timeout|Deadline|Defer|Group|Policy|Codec|Validator|Mapper|Adapter|Boundary|Resource|Capability|Authority|Channel|Mutex|Lock|Guard|State|Storage|Select|Record|Builder|Field|Enum|Variant|Template|Html|Document|Fragment|Class|Value|Counter|Count|Index|Length|Capacity|Allocator|Source|Target|Step|Accumulator|Divisor|Remainder|Span|Metric|Trace)$/;

const primitiveTargets = new Map([
  ['console.writeLine', 'puts(text) -> Int32. Writes one text line.'],
  ['console.writeIntegerLine', 'printf("%lld\\n", value) -> Int32. Writes one integer line.'],
  ['console.writeInteger', 'Alias for console.writeIntegerLine.'],
  ['console.writeFloatLine', 'printf("%f\\n", value) -> Int32. Writes one floating-point line.'],
  ['math.addInt64', 'Int64 addition. Infallible math target; use bind.'],
  ['math.subtractInt64', 'Int64 subtraction. Infallible math target; use bind.'],
  ['math.multiplyInt64', 'Int64 multiplication. Infallible math target; use bind.'],
  ['math.divideInt64', 'Int64 signed division. Infallible in the current AST model; use bind.'],
  ['math.moduloInt64', 'Int64 signed remainder. Infallible in the current AST model; use bind.'],
  ['math.equalInt64', 'Int64 equality comparison returning Bool.'],
  ['math.notEqualInt64', 'Int64 inequality comparison returning Bool.'],
  ['math.lessThanInt64', 'Int64 less-than comparison returning Bool.'],
  ['math.lessThanOrEqualInt64', 'Int64 less-than-or-equal comparison returning Bool.'],
  ['math.greaterThanInt64', 'Int64 greater-than comparison returning Bool.'],
  ['math.greaterThanOrEqualInt64', 'Int64 greater-than-or-equal comparison returning Bool.'],
  ['math.addFloat64', 'Float64 addition. Infallible math target; use bind.'],
  ['math.subtractFloat64', 'Float64 subtraction. Infallible math target; use bind.'],
  ['math.multiplyFloat64', 'Float64 multiplication. Infallible math target; use bind.'],
  ['math.divideFloat64', 'Float64 division. Infallible math target; use bind.'],
  ['math.equalFloat64', 'Float64 equality comparison returning Bool.'],
  ['math.notEqualFloat64', 'Float64 inequality comparison returning Bool.'],
  ['math.lessThanFloat64', 'Float64 less-than comparison returning Bool.'],
  ['math.lessThanOrEqualFloat64', 'Float64 less-than-or-equal comparison returning Bool.'],
  ['math.greaterThanFloat64', 'Float64 greater-than comparison returning Bool.'],
  ['math.greaterThanOrEqualFloat64', 'Float64 greater-than-or-equal comparison returning Bool.'],
  ['math.intToFloat', 'Signed integer to Float64 conversion.'],
  ['math.floatToInt', 'Float64 to signed integer conversion, rounding toward zero.'],
  ['math.convertSignedInt64ToFloat64', 'Alias for math.intToFloat.'],
  ['math.convertFloat64ToSignedInt64', 'Alias for math.floatToInt.'],
  ['math.convertSignedInt32ToSignedInt64', 'Alias for math.signExtendInt32ToInt64.'],
  ['math.convertSignedInt64ToSignedInt32', 'Alias for math.truncateInt64ToInt32.'],
  ['math.signExtendInt32ToInt64', 'Explicit signed Int32 to Int64 conversion.'],
  ['math.truncateInt64ToInt32', 'Explicit signed Int64 to Int32 truncation. Caller owns range safety.'],
  ['math.equalInt32', 'Signed Int32 equality comparison returning Bool.'],
  ['math.notEqualInt32', 'Signed Int32 inequality comparison returning Bool.'],
  ['math.lessThanInt32', 'Signed Int32 less-than comparison returning Bool.'],
  ['math.lessThanOrEqualInt32', 'Signed Int32 less-than-or-equal comparison returning Bool.'],
  ['math.greaterThanInt32', 'Signed Int32 greater-than comparison returning Bool.'],
  ['math.greaterThanOrEqualInt32', 'Signed Int32 greater-than-or-equal comparison returning Bool.'],
  ['math.greaterThanOrEqualByteCount', 'C byte-count greater-than-or-equal comparison returning Bool.'],
  ['math.checkedMultiplyInt64', 'Int64 signed multiply with overflow detection. Fallible target; use bindOk, bindError, and branchIfError.'],
  ['pointer.loadByte', 'Reads one byte from buffer + offset. Requires declared memory read effects for checked lint paths.'],
  ['pointer.storeByte', 'Writes one byte to buffer + offset. Requires declared memory write effects for checked lint paths.'],
  ['pointer.offset', 'Returns buffer + offset without dereferencing.'],
  ['pointer.difference', 'Returns pointer distance as a signed integer.'],
  ['pointer.isNull', 'Returns Bool indicating whether a pointer is null.'],
  ['scheduler.sleep', 'Async typed-duration sleep target. Use cancelOn, start, await, bind error, and branch error.'],
  ['retryPolicy.delayForAttempt', 'Retry-policy delay calculation target. Fallible when policy or attempt state is invalid.'],
  ['metrics.computeIncrementInt64', 'Metrics-owned counter increment calculation. Fallible target; bind success and error explicitly.'],
  ['net.fetchText', 'Native HTTP client text fetch. Accepts either request HttpGetRequest or url/timeoutMillis/maxBodyBytes args and returns borrowed response text that must be freed with net.freeTextBody.'],
  ['net.fetchBytes', 'Native HTTP client byte fetch MVP. Shares the text-fetch buffer and should be paired with net.freeTextBody.'],
  ['net.freeTextBody', 'Native HTTP client cleanup target for bodies returned by net.fetchText/net.fetchBytes.'],
  ['http.responseHtml', 'Native HTTP HTML writer: response, status, body -> Int32. Uses fixed text/html; charset=utf-8 and rejects null body pointers.'],
  ['http.responseText', 'Native HTTP writer: response, status, body, optional contentType -> Int32. Body must be non-null.'],
  ['http.responseBytes', 'Native HTTP binary writer: response, status, body, bodyLength, optional contentType -> Int32. Preserves embedded NUL bytes.'],
  ['http.responseSseEvent', 'Native one-shot SSE writer: response, status, event, data -> Int32. Emits text/event-stream and closes the response.'],
  ['http.responseHeader', 'Native HTTP header writer: response, name, value -> Int32. Must run before the response body is sent.'],
  ['http.requestMethod', 'Native HTTP request reader: request -> non-null method string.'],
  ['http.requestPath', 'Native HTTP request reader: request -> non-null path string without query.'],
  ['http.requestHeader', 'Native nullable HTTP request header reader: request, name -> string or NULL. Guard before response body use.'],
  ['http.requestQueryParam', 'Native nullable query reader: request, name -> raw first matching value or NULL. Percent decoding is future work.'],
  ['http.requestBodyText', 'Native nullable body-text reader for bounded request bodies. Guard missing/empty bodies explicitly.'],
  ['http.requestBodyBytes', 'Native nullable body-bytes reader for bounded request bodies. Pair with http.requestBodyLength.'],
  ['http.requestBodyLength', 'Native body length reader: request -> ByteCount. Zero means no bytes.'],
  ['http.requestCookie', 'Native nullable cookie reader: request, name -> string or NULL.'],
  ['http.requestPathParam', 'Native route path-parameter reader: request, name -> string or NULL.'],
  ['http.responseFile', 'Native static-file response writer.'],
  ['http.ensureDirectory', 'Native helper for ensuring a filesystem directory exists.'],
  ['http.nowMillis', 'Native helper returning current wall-clock milliseconds.'],
  ['http.openSseStream', 'standard.http SSE opener: response, status -> Int32. Opens a text/event-stream response with standard headers.'],
  ['http.writeSseEvent', 'standard.http SSE writer: response, event, data -> Int32. Writes one event frame to an open stream.'],
  ['http.writeSseEventWithId', 'standard.http SSE writer: response, id, event, data -> Int32. Writes one id-bearing event frame to an open stream.'],
  ['http.writeSseHeartbeat', 'standard.http SSE heartbeat writer: response, comment -> Int32. Writes one comment heartbeat frame.'],
  ['http.closeSseStream', 'standard.http SSE closer: response -> Int32. Marks the stream complete for the native adapter.'],
  ['http.clientDisconnected', 'standard.http stream-state reader: response -> Bool. True after the native writer observed a disconnect or write failure.'],
  ['http.serverIsShuttingDown', 'standard.http server-state reader: Bool. True once the native HTTP server entered graceful-shutdown drain mode.'],
  ['http.clientGet', 'standard.http blocking HTTP GET: host, port, path, optional headerLine -> HttpClientResponseBody. Returns the 2xx body or null.'],
  ['http.clientPost', 'standard.http blocking HTTP POST: host, port, path, optional headerLine, body -> HttpClientResponseBody. Returns the 2xx body or null.'],
  ['http.escapeHtml', 'standard.http HTML escaper: input, scratch, capacity -> escaped text in caller-owned buffer.'],
  ['http.multipartPartText', 'Native nullable multipart text-part reader: request, name -> string or NULL.'],
  ['http.multipartPartBytes', 'Native nullable multipart binary-part reader: request, name -> pointer or NULL. Pair with http.multipartPartLength.'],
  ['http.multipartPartLength', 'Native multipart part length reader: request, name -> ByteCount.'],
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
  ['document.bodyElement', 'standard.document: -> DomHandle for document.body (wasm/browser only). Requires read document.dom.'],
  ['document.documentElement', 'standard.document: -> DomHandle for the root html element. Requires read document.dom.'],
  ['document.getElementById', 'standard.document: elementId -> DomHandle, or domHandleNone when no element matches. Requires read document.dom.'],
  ['document.querySelector', 'standard.document: selector -> DomHandle for the first match, or domHandleNone. Requires read document.dom.'],
  ['document.createElement', 'standard.document: tagName -> DomHandle for a detached element. Requires write document.dom.'],
  ['document.createTextNode', 'standard.document: text -> DomHandle for a detached text node. Requires write document.dom.'],
  ['document.appendChild', 'standard.document: parent, child -> DomStatus. Requires write document.dom.'],
  ['document.removeChild', 'standard.document: parent, child -> DomStatus. Requires write document.dom.'],
  ['document.setTextContent', 'standard.document: node, text -> DomStatus. Requires write document.dom.'],
  ['document.getTextContentInto', 'standard.document: node, outText, outTextCapacity -> DomByteCount (or domStatusBufferTooSmall). Requires read document.dom + write memory.buffer.'],
  ['document.setValue', 'standard.document: node, text -> DomStatus on a form control. Requires write document.dom.'],
  ['document.getValueInto', 'standard.document: node, outText, outTextCapacity -> DomByteCount. Requires read document.dom + write memory.buffer.'],
  ['document.setInnerHtml', 'standard.document: node, markup -> DomStatus. Caller owns markup sanitization. Requires write document.dom.'],
  ['document.setAttribute', 'standard.document: node, name, value -> DomStatus. Requires write document.dom.'],
  ['document.getAttributeInto', 'standard.document: node, name, outValue, outValueCapacity -> DomByteCount (domStatusNotFound when absent). Requires read document.dom + write memory.buffer.'],
  ['document.removeAttribute', 'standard.document: node, name -> DomStatus. Requires write document.dom.'],
  ['document.classListAdd', 'standard.document: node, className -> DomStatus. Requires write document.dom.'],
  ['document.classListRemove', 'standard.document: node, className -> DomStatus. Requires write document.dom.'],
  ['document.classListToggle', 'standard.document: node, className -> 1 present / 0 absent / negative status. Requires write document.dom.'],
  ['document.setStyleProperty', 'standard.document: node, property, value -> DomStatus. Requires write document.dom.'],
  ['document.addEventListener', 'standard.document: node, eventName -> DomEventStreamHandle. Drain with document.nextEvent; release with document.removeEventListener. Requires read document.event.'],
  ['document.nextEvent', 'standard.document: stream -> DomStatus. Blocks until the next event; suspends the wasm stack via emcc Asyncify (no SemanticScript async-future runtime). Requires an Asyncify/JSPI build.'],
  ['document.eventTarget', 'standard.document: stream -> DomHandle of the most recent event target. Requires read document.event.'],
  ['document.eventDetailInto', 'standard.document: stream, property, outValue, outValueCapacity -> DomByteCount of an event string property (type/key/inputType/data). Requires read document.event + write memory.buffer.'],
  ['document.removeEventListener', 'standard.document: stream -> DomStatus. Detaches the listener and releases the queue. Requires close document.event.'],
  ['document.releaseHandle', 'standard.document: node -> DomStatus. Drops a wasm-side handle (does not remove the DOM node) to bound the handle table. Requires read document.dom.'],
  ['document.evalScript', 'standard.document: script -> DomStatus. JavaScript escape hatch evaluated in page global scope; caller owns trust. Requires execute document.script.'],
  ['math.subInt64', 'Alias for math.subtractInt64.'],
  ['math.mulInt64', 'Alias for math.multiplyInt64.'],
  ['math.divInt64', 'Alias for math.divideInt64.'],
  ['math.modInt64', 'Alias for math.moduloInt64.'],
  ['math.eqInt64', 'Alias for math.equalInt64.'],
  ['math.neInt64', 'Alias for math.notEqualInt64.'],
  ['math.ltInt64', 'Alias for math.lessThanInt64.'],
  ['math.leInt64', 'Alias for math.lessThanOrEqualInt64.'],
  ['math.gtInt64', 'Alias for math.greaterThanInt64.'],
  ['math.geInt64', 'Alias for math.greaterThanOrEqualInt64.'],
  ['bcrypt.hashPassword', 'Native bcrypt password hashing target from standard.bcrypt.'],
  ['bcrypt.verifyPassword', 'Native bcrypt password verification target from standard.bcrypt.'],
  ['bcrypt.randomBytes', 'Native cryptographic random byte generation target from standard.bcrypt.'],
  ['bcrypt.base64UrlEncode', 'Native base64url encoder target from standard.bcrypt.'],
  ['sqlite.openDatabase', 'Native sqlite database open target.'],
  ['sqlite.closeDatabase', 'Native sqlite database close target.'],
  ['sqlite.errorMessage', 'Native sqlite database error-message reader. Returns SQLite-owned text.'],
  ['sqlite.lastInsertRowId', 'Native sqlite last insert rowid target.'],
  ['sqlite.changedRowCount', 'Native sqlite changed-row-count reader target.'],
  ['sqlite.exec', 'Native sqlite statement execution target.'],
  ['sqlite.prepareStatement', 'Native sqlite prepared statement target.'],
  ['sqlite.finalizeStatement', 'Native sqlite prepared-statement finalizer target.'],
  ['sqlite.resetStatement', 'Native sqlite statement reset target.'],
  ['sqlite.stepStatement', 'Native sqlite statement step target returning SqliteStepResult on success.'],
  ['sqlite.bindInt64', 'Native sqlite int64 binding target.'],
  ['sqlite.bindDouble', 'Native sqlite floating-point binding target.'],
  ['sqlite.bindText', 'Native sqlite text binding target.'],
  ['sqlite.bindBlob', 'Native sqlite blob binding target.'],
  ['sqlite.bindNull', 'Native sqlite null binding target.'],
  ['sqlite.columnCount', 'Native sqlite column-count reader target.'],
  ['sqlite.columnType', 'Native sqlite column-type reader target.'],
  ['sqlite.columnName', 'Native sqlite column-name reader target. Returns SQLite-owned text.'],
  ['sqlite.columnInt64', 'Native sqlite int64 column reader target.'],
  ['sqlite.columnDouble', 'Native sqlite floating-point column reader target.'],
  ['sqlite.columnText', 'Native sqlite text column reader target.'],
  ['sqlite.columnBlob', 'Native sqlite blob column reader target. Returns SQLite-owned bytes.'],
  ['sqlite.columnByteCount', 'Native sqlite column byte-count reader target.'],
  ['sqlite.libraryVersion', 'Native sqlite library version reader target.'],
  ['sqlite.execStatus', 'standard.sqlite direct script execution target: database, sql -> Int32. Returns the native SQLite adapter status code.'],
  ['jwt.hs256SignJsonPayloadWithRandomJti', 'standard.jwt signer: secret, payloadTemplate, outBuffer, outCapacity -> Int32. Writes an HS256 JWT with a generated jti.'],
  ['jwt.hs256VerifyToken', 'standard.jwt verifier: token, secret -> Int32. Returns jwtStatusMatch only when the compact JWT signature matches.'],
  ['jwt.readStringClaim', 'standard.jwt claim reader: token, claimName, outBuffer, outCapacity -> string claim text after caller-verified signature trust.'],
  ['jwt.readInt64Claim', 'standard.jwt claim reader: token, claimName, missingDefault -> Int64. Returns the caller-supplied default on missing or malformed claims.'],
  ['jwt.formatBearerLoginEnvelope', 'standard.jwt formatter for access-token login envelopes using caller-supplied user fields, scopes JSON, and output buffer.'],
  ['jwt.formatBearerRefreshEnvelope', 'standard.jwt formatter for rotated bearer refresh envelopes using caller-supplied tokens and output buffer.'],
  ['json.createBuilder', 'Native JSON builder creation target. Deprecated in favor of the document CRUD API for new code.'],
  ['json.destroyBuilder', 'Native JSON builder cleanup target.'],
  ['json.objectOpen', 'Native JSON builder object-open target.'],
  ['json.objectClose', 'Native JSON builder object-close target.'],
  ['json.arrayOpen', 'Native JSON builder array-open target.'],
  ['json.arrayClose', 'Native JSON builder array-close target.'],
  ['json.fieldInt64', 'Native JSON builder object int64 field writer.'],
  ['json.fieldDouble', 'Native JSON builder object double field writer.'],
  ['json.fieldBool', 'Native JSON builder object bool field writer.'],
  ['json.fieldString', 'Native JSON builder object string field writer.'],
  ['json.fieldNull', 'Native JSON builder object null field writer.'],
  ['json.elementInt64', 'Native JSON builder array int64 element writer.'],
  ['json.elementDouble', 'Native JSON builder array double element writer.'],
  ['json.elementBool', 'Native JSON builder array bool element writer.'],
  ['json.elementString', 'Native JSON builder array string element writer.'],
  ['json.elementNull', 'Native JSON builder array null element writer.'],
  ['json.finishBuilder', 'Native JSON builder finish target returning serialized text.'],
  ['json.builderLength', 'Native JSON builder serialized-length reader.'],
  ['json.hasField', 'Deprecated flat JSON field-presence finder. Prefer document cursors for nested JSON.'],
  ['json.findString', 'Deprecated flat JSON string-field finder. Prefer document cursors for nested JSON.'],
  ['json.findInt64', 'Deprecated flat JSON int64-field finder. Prefer document cursors for nested JSON.'],
  ['json.findDouble', 'Deprecated flat JSON double-field finder. Prefer document cursors for nested JSON.'],
  ['json.findBool', 'Deprecated flat JSON bool-field finder. Prefer document cursors for nested JSON.'],
  ['json.createDocument', 'Native JSON document creation target.'],
  ['json.createEmptyDocument', 'Native empty JSON document creation target.'],
  ['json.destroyDocument', 'Native JSON document cleanup target.'],
  ['json.documentRoot', 'Native JSON document root cursor target.'],
  ['json.serializeDocument', 'Native JSON document serialization target.'],
  ['json.documentLength', 'Native JSON document serialized-length target.'],
  ['json.objectFieldAt', 'Native JSON object field cursor target.'],
  ['json.arrayElementAt', 'Native JSON array element cursor target.'],
  ['json.cursorParent', 'Native JSON parent cursor target.'],
  ['json.cursorAtPath', 'Native JSON path cursor target using .field and [index] syntax.'],
  ['json.cursorKind', 'Native JSON cursor kind reader target.'],
  ['json.cursorIsNull', 'Native JSON cursor null-check target.'],
  ['json.cursorString', 'Native JSON cursor string reader target.'],
  ['json.cursorInt64', 'Native JSON cursor int64 reader target.'],
  ['json.cursorDouble', 'Native JSON cursor double reader target.'],
  ['json.cursorBool', 'Native JSON cursor bool reader target.'],
  ['json.cursorArrayLength', 'Native JSON cursor array-length reader target.'],
  ['json.cursorObjectFieldCount', 'Native JSON cursor object-field-count reader target.'],
  ['json.cursorObjectFieldNameAt', 'Native JSON cursor object-field-name reader target.'],
  ['json.cursorObjectFieldValueAt', 'Native JSON cursor object-field-value reader target.'],
  ['json.setObjectFieldString', 'Native JSON object string setter target.'],
  ['json.setObjectFieldInt64', 'Native JSON object int64 setter target.'],
  ['json.setObjectFieldDouble', 'Native JSON object double setter target.'],
  ['json.setObjectFieldBool', 'Native JSON object bool setter target.'],
  ['json.setObjectFieldNull', 'Native JSON object null setter target.'],
  ['json.setObjectFieldObject', 'Native JSON object child-object setter target.'],
  ['json.setObjectFieldArray', 'Native JSON object child-array setter target.'],
  ['json.setObjectFieldJsonText', 'Native JSON object raw JsonText setter target.'],
  ['json.appendArrayElementString', 'Native JSON array string append target.'],
  ['json.appendArrayElementInt64', 'Native JSON array int64 append target.'],
  ['json.appendArrayElementDouble', 'Native JSON array double append target.'],
  ['json.appendArrayElementBool', 'Native JSON array bool append target.'],
  ['json.appendArrayElementNull', 'Native JSON array null append target.'],
  ['json.appendArrayElementObject', 'Native JSON array object append target.'],
  ['json.appendArrayElementArray', 'Native JSON array child-array append target.'],
  ['json.appendArrayElementJsonText', 'Native JSON array raw JsonText append target.'],
  ['json.insertArrayElementString', 'Native JSON array string insert target.'],
  ['json.insertArrayElementInt64', 'Native JSON array int64 insert target.'],
  ['json.insertArrayElementDouble', 'Native JSON array double insert target.'],
  ['json.insertArrayElementBool', 'Native JSON array bool insert target.'],
  ['json.insertArrayElementNull', 'Native JSON array null insert target.'],
  ['json.insertArrayElementObject', 'Native JSON array object insert target.'],
  ['json.insertArrayElementArray', 'Native JSON array child-array insert target.'],
  ['json.insertArrayElementJsonText', 'Native JSON array raw JsonText insert target.'],
  ['json.replaceArrayElementString', 'Native JSON array string replace target.'],
  ['json.replaceArrayElementInt64', 'Native JSON array int64 replace target.'],
  ['json.replaceArrayElementDouble', 'Native JSON array double replace target.'],
  ['json.replaceArrayElementBool', 'Native JSON array bool replace target.'],
  ['json.replaceArrayElementNull', 'Native JSON array null replace target.'],
  ['json.replaceArrayElementObject', 'Native JSON array object replace target.'],
  ['json.replaceArrayElementArray', 'Native JSON array child-array replace target.'],
  ['json.replaceArrayElementJsonText', 'Native JSON array raw JsonText replace target.'],
  ['json.removeObjectField', 'Native JSON object-field removal target.'],
  ['json.removeArrayElementAt', 'Native JSON array element removal target.'],
  ['json.clearObject', 'Native JSON object clear target.'],
  ['json.clearArray', 'Native JSON array clear target.'],
]);

const generatedTargetPattern = /^(?:json\.(?:encode|decode|parse|stringify)\.[A-Z][A-Za-z0-9_]*|html\.hydrate\.[A-Z][A-Za-z0-9_]*)$/;
const cRuntimeTargetPattern = /^c\.[A-Za-z_][A-Za-z0-9_]*$/;
const jsonDecodePrimitiveTargetTypes = new Set([
  'Int64', 'Int64', 'Int32', 'UInt32',
  'Int16', 'UInt16', 'Int8', 'UInt8',
  'DurationMilliseconds', 'MonotonicMilliseconds', 'UtcMilliseconds',
  'Bool', 'Float64', 'Float64', 'Float32',
]);
const jsonEncodePrimitiveTargetTypes = new Set([
  ...jsonDecodePrimitiveTargetTypes,
  'String', 'String',
]);
const jsonParsePrimitiveTargetTypes = new Set([
  ...jsonDecodePrimitiveTargetTypes,
  'JsonText',
]);
const jsonStringifyPrimitiveTargetTypes = new Set([
  ...jsonEncodePrimitiveTargetTypes,
  'JsonText',
]);

const generatedTargetHoverText = (text) => {
  const targetType = text.split('.').pop();

  if (text.startsWith('json.decode.') && jsonDecodePrimitiveTargetTypes.has(targetType)) {
    return 'Legacy primitive JSON decode target. Numeric values use libc parsing, Bool compares against true, and malformed inputs return the libc default.';
  }

  if (text.startsWith('json.encode.') && jsonEncodePrimitiveTargetTypes.has(targetType)) {
    return 'Legacy primitive JSON encode target. Numerics and Bool use direct formatting; strings are quoted with full escaping deferred to the codec runtime.';
  }

  if (jsonParsePrimitiveTargetTypes.has(targetType)) {
    if (text.startsWith('json.parse.')) {
      return 'High-level primitive JSON parse target. It lowers through native_json strict token parsing for primitives and validates JsonText syntax.';
    }
  }

  if (jsonStringifyPrimitiveTargetTypes.has(targetType)) {
    if (text.startsWith('json.stringify.')) {
      return 'High-level primitive JSON stringify target. Strings and JsonText lower through native_json escaping/copy paths; numeric and Bool values use bounded formatting.';
    }
  }

  if (text.startsWith('json.decode.')) {
    return 'Legacy generated JSON decode target for record metadata. It remains partial while json.parse.* is the preferred high-level surface.';
  }

  if (text.startsWith('json.encode.')) {
    return 'Legacy generated JSON encode target for record metadata. It remains partial while json.stringify.* is the preferred high-level surface.';
  }

  if (text.startsWith('json.parse.')) {
    return 'Generated JSON parse target backed by record metadata and the native document runtime.';
  }

  if (text.startsWith('json.stringify.')) {
    return 'Generated JSON stringify target backed by record metadata and the native document runtime.';
  }

  if (text.startsWith('html.hydrate.')) {
    return 'Generated HTML template hydration target. It is declared by `html template` and `html body template` rows and lowers explicit `argument` rows into one hydrated HtmlDocument or HtmlFragment value.';
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
  ['operation', 'Qualifier for operation-owned metadata such as input operation NAME ARG TYPE.'],
  ['template', 'Qualifier for HTML template declarations and body islands.'],
  ['parameter', 'Qualifier for explicit HTML template parameter metadata.'],
  ['body', 'Qualifier for HTML template body islands.'],
  ['memory', 'Mutation target for operation-local memory slots.'],
  ['storage', 'Mutation target for module or process storage slots.'],
  ['source', 'Keyword naming a source call or value in phrase-shaped rows.'],
  ['target', 'Keyword naming a branch, jump, work, or operation target.'],
  ['condition', 'Keyword naming the boolean value in `branch if condition ...`.'],
  ['type', 'Keyword naming an explicit type in phrase-shaped rows.'],
  ['value', 'Keyword naming a plain result or returned value in phrase-shaped rows.'],
  ['ok', 'Result success leg keyword.'],
  ['if', 'Conditional branch keyword.'],
  ['else', 'Fallback branch keyword.'],
  ['void', 'Void result keyword.'],
  ['process', 'Storage scope for process-shared state.'],
  ['sharedState', 'Shared-state storage scope. Reads and writes require guard-token authority.'],
  ['immutable', 'Storage mutability: value cannot be changed after declaration.'],
  ['mutable', 'Storage mutability: value can change through explicit set lines.'],
  ['read', 'Effect or collection role mode: read.'],
  ['write', 'Effect or collection role mode: write.'],
  ['append', 'Effect or authority mode: append.'],
  ['open', 'Effect or authority mode: open.'],
  ['close', 'Effect or authority mode: close.'],
  ['allocate', 'Effect or authority mode: allocate.'],
  ['free', 'Effect or authority mode: free.'],
  ['observe', 'Effect or authority mode: observe.'],
  ['execute', 'Effect or authority mode: execute.'],
  ['connect', 'Effect or authority mode: connect.'],
  ['send', 'Effect or authority mode: send.'],
  ['receive', 'Effect or authority mode: receive.'],
  ['delete', 'Effect or authority mode: delete.'],
  ['configure', 'Effect or authority mode: configure.'],
  ['create', 'Effect or authority mode: create.'],
  ['update', 'Effect or authority mode: update.'],
  ['network', 'Effect or authority mode: network.'],
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
  ['as', 'Legacy importModule alias separator. Prefer import ALIAS MODULE_PATH in new code.'],
  ['dev', 'Build profile that keeps development diagnostics visible.'],
  ['prod', 'Build profile that hides source context and favors release defaults.'],
  ['auto', 'Toolchain policy: let the compiler choose from build.sem and platform context.'],
  ['nativeExe', 'Native executable target runtime.'],
  ['webServer', 'Native web server target runtime.'],
  ['windowsGui', 'Windows desktop GUI target runtime. Use entry console plus standard.gui gui.* calls.'],
  ['applicationPrimary', 'Icon role for the primary application icon.'],
  ['applicationSecondary', 'Icon role for secondary shell or notification surfaces.'],
  ['documentType', 'Icon role for a registered document type.'],
  ['png', 'Icon image format token: PNG source image.'],
  ['ico', 'Icon image format token: ICO source image.'],
  ['bits32', 'Icon image color depth token: 32-bit RGBA.'],
  ['bits24', 'Icon image color depth token: 24-bit color.'],
  ['bits8', 'Icon image color depth token: 8-bit indexed color.'],
  ['any', 'Platform selector token: applies to every supported target platform.'],
  ['windows', 'Platform selector token for Windows-specific resources.'],
  ['macos', 'Platform selector token for macOS-specific resources.'],
  ['linux', 'Platform selector token for Linux-specific resources.'],
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
  ['rawPointerToValidatedCString', 'Trust-boundary kind: raw pointer becomes a validated null-terminated string.'],
  ['rawUtf8ToValidatedText', 'Trust-boundary kind: raw UTF-8 becomes validated text.'],
  ['row', 'Record layout kind: row layout.'],
  ['column', 'Record layout kind: column layout.'],
  ['packed', 'Record layout kind: packed layout.'],
  ['heap', 'Heap allocator or memory policy marker.'],
  ['arena', 'Arena allocator or memory policy marker.'],
  ['request', 'Request-scoped arena or policy marker.'],
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
  ['permissiveExecutable', 'Language mode that explicitly opts out of the strict executable wall.'],
  ['library', 'Project target runtime for library-style builds.'],
  ['none', 'Explicit no-failure marker or asyncRuntime value that preserves synchronous start/await lowering.'],
  ['libuv', 'Experimental asyncRuntime backend selector for the native async runtime.'],
  ['on', 'Boolean-ish build option value, commonly used by cpuFeature.'],
  ['off', 'Boolean-ish build option value, runtime-check mode, or CPU feature-check opt-out.'],
  ['path', 'Dependency source kind for a local filesystem dependency path.'],
  ['x86_64_v1', 'Portable x86-64 baseline CPU feature level.'],
  ['win32', 'Native Windows GUI backend selector.'],
  ['winui3', 'Recognized but currently blocked Windows App SDK GUI backend selector.'],
  ['cursor', 'Icon role token for cursor assets.'],
  ['notification', 'Icon role token for notification assets.'],
  ['splash', 'Icon role token for splash-screen assets.'],
  ['empty', 'recordFieldJsonOmitWhen policy for omitted or empty string fields.'],
  ['null', 'JSON null literal or recordFieldJsonOmitWhen policy for explicit null values.'],
  ['zero', 'recordFieldJsonOmitWhen policy for absent numeric zero defaults.'],
  ['rowSqliteStepResult', 'SqliteStepResult enum value for a row being available.'],
  ['doneSqliteStepResult', 'SqliteStepResult enum value for statement completion.'],
  ['integerSqliteColumnType', 'SqliteColumnType enum value for integer columns.'],
  ['floatSqliteColumnType', 'SqliteColumnType enum value for floating-point columns.'],
  ['textSqliteColumnType', 'SqliteColumnType enum value for text columns.'],
  ['blobSqliteColumnType', 'SqliteColumnType enum value for blob columns.'],
  ['nullSqliteColumnType', 'SqliteColumnType enum value for null columns.'],
  ['objectJsonValueKind', 'JsonValueKind enum value for object cursors.'],
  ['arrayJsonValueKind', 'JsonValueKind enum value for array cursors.'],
  ['stringJsonValueKind', 'JsonValueKind enum value for string cursors.'],
  ['integerJsonValueKind', 'JsonValueKind enum value for integer cursors.'],
  ['doubleJsonValueKind', 'JsonValueKind enum value for double cursors.'],
  ['booleanJsonValueKind', 'JsonValueKind enum value for boolean cursors.'],
  ['nullJsonValueKind', 'JsonValueKind enum value for null cursors.'],
  ['windowGuiTargetKind', 'GuiTargetKind enum value for windows.'],
  ['controlGuiTargetKind', 'GuiTargetKind enum value for controls.'],
  ['defaultGuiWindowLayout', 'GuiWindowLayout enum default value.'],
  ['verticalStackGuiWindowLayout', 'GuiWindowLayout enum value for vertical stacks.'],
  ['horizontalStackGuiWindowLayout', 'GuiWindowLayout enum value for horizontal stacks.'],
  ['gridGuiWindowLayout', 'GuiWindowLayout enum value for grid layout.'],
  ['absoluteGuiWindowLayout', 'GuiWindowLayout enum value for absolute positioning.'],
  ['buttonGuiControlKind', 'GuiControlKind enum value for buttons.'],
  ['textBoxGuiControlKind', 'GuiControlKind enum value for text boxes.'],
  ['listBoxGuiControlKind', 'GuiControlKind enum value for list boxes.'],
  ['checkBoxGuiControlKind', 'GuiControlKind enum value for check boxes.'],
  ['menuItemGuiControlKind', 'GuiControlKind enum value for menu items.'],
  ['statusBarGuiControlKind', 'GuiControlKind enum value for status bars.'],
  ['textLabelGuiControlKind', 'GuiControlKind enum value for text labels.'],
  ['defaultGuiListBoxSelectionMode', 'GuiListBoxSelectionMode default enum value.'],
  ['singleGuiListBoxSelectionMode', 'GuiListBoxSelectionMode single-selection value.'],
  ['multipleGuiListBoxSelectionMode', 'GuiListBoxSelectionMode multi-selection value.'],
  ['clickGuiEventKind', 'GuiEventKind enum value for clicks.'],
  ['valueChangedGuiEventKind', 'GuiEventKind enum value for value changes.'],
  ['selectionChangedGuiEventKind', 'GuiEventKind enum value for selection changes.'],
  ['enterPressedGuiEventKind', 'GuiEventKind enum value for Enter key events.'],
  ['keyPressedGuiEventKind', 'GuiEventKind enum value for key events.'],
  ['focusGainedGuiEventKind', 'GuiEventKind enum value for focus gained.'],
  ['focusLostGuiEventKind', 'GuiEventKind enum value for focus lost.'],
  ['closeRequestedGuiEventKind', 'GuiEventKind enum value for close requests.'],
  ['resizedGuiEventKind', 'GuiEventKind enum value for resize events.'],
  ['shownGuiEventKind', 'GuiEventKind enum value for shown events.'],
  ['hiddenGuiEventKind', 'GuiEventKind enum value for hidden events.'],
  ['okGuiRuntimeStatus', 'GuiRuntimeStatus enum success value.'],
  ['configGuiRuntimeStatus', 'GuiRuntimeStatus enum config error value.'],
  ['runtimeUnavailableGuiRuntimeStatus', 'GuiRuntimeStatus enum runtime-unavailable value.'],
  ['allocationGuiRuntimeStatus', 'GuiRuntimeStatus enum allocation failure value.'],
  ['platformGuiRuntimeStatus', 'GuiRuntimeStatus enum platform failure value.'],
  ['notFoundGuiRuntimeStatus', 'GuiRuntimeStatus enum not-found value.'],
  ['wrongKindGuiRuntimeStatus', 'GuiRuntimeStatus enum wrong-kind value.'],
  ['handlerGuiRuntimeStatus', 'GuiRuntimeStatus enum handler failure value.'],
  ['unsupportedGuiRuntimeStatus', 'GuiRuntimeStatus enum unsupported operation value.'],
  ['threadGuiRuntimeStatus', 'GuiRuntimeStatus enum thread-policy failure value.'],
]);

const domainMethods = new Set([
  'add', 'addPositiveStep', 'subtract', 'subtractStep', 'subtractPositiveStep',
  'multiply', 'multiplyByStep', 'multiplyByCounter', 'divide', 'modulo', 'moduloBy',
  'equal', 'notEqual',
  'lessThan', 'lessThanOrEqual', 'greaterThan', 'greaterThanOrEqual',
  'square', 'checkedMultiply', 'checkedMultiplyByCounter', 'checkedMultiplyByStep',
  'length', 'append', 'get', 'set', 'slice', 'insert', 'update', 'remove',
  'clear', 'contains', 'borrow', 'capacity', 'reserve',
]);

const primitiveTypes = new Map([
  ['Int64', '64-bit integer.'],
  ['Int32', '32-bit integer.'],
  ['Int16', '16-bit integer.'],
  ['Int8', '8-bit integer.'],
  ['ExitCode', '32-bit process exit code.'],
  ['Bool', 'Boolean value.'],
  ['Float64', '64-bit floating-point value.'],
  ['Float32', '32-bit floating-point value.'],
  ['String', 'Null-terminated UTF-8 string.'],
  ['Bytes', 'Byte sequence.'],
  ['Utf8Text', 'UTF-8 text value.'],
  ['RawUtf8Text', 'Unvalidated UTF-8 text bytes.'],
  ['RawJsonBytes', 'Untrusted JSON byte input.'],
  ['JsonBytes', 'Validated/generated JSON bytes.'],
  ['JsonBuilder', 'Opaque native JSON builder handle.'],
  ['JsonDocument', 'Opaque native JSON document handle.'],
  ['JsonCursor', 'Stable per-document JSON cursor index.'],
  ['JsonText', 'Validated JSON text value.'],
  ['JsonFieldName', 'JSON object field-name text.'],
  ['JsonPath', 'JSON document path using .field and [index] steps.'],
  ['JsonStringValue', 'JSON string payload value.'],
  ['JsonScratchBuffer', 'Caller-owned JSON scratch buffer.'],
  ['JsonCapacityBytes', 'JSON runtime capacity in bytes.'],
  ['JsonValueKind', 'JSON cursor kind enum.'],
  ['HtmlSafeUrl', 'Trusted URL value required for URL-bearing HTML attributes such as href, src, action, formaction, and poster.'],
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
  ['GuiWindowId', 'standard.gui role alias for emitted window identifiers.'],
  ['GuiControlId', 'standard.gui role alias for emitted control identifiers.'],
  ['GuiText', 'standard.gui text payload alias.'],
  ['GuiApplicationTitle', 'standard.gui application-title alias.'],
  ['GuiWindowTitle', 'standard.gui window-title alias.'],
  ['GuiControlText', 'standard.gui control-text alias.'],
  ['GuiPlaceholderText', 'standard.gui placeholder-text alias.'],
  ['GuiAccessibleName', 'standard.gui accessible-name alias.'],
  ['GuiListBoxItemText', 'standard.gui list-box item text alias.'],
  ['GuiIconGroupName', 'standard.gui icon-group name alias.'],
  ['GuiPixels', 'standard.gui pixel measurement alias.'],
  ['GuiMinimumPixels', 'standard.gui minimum pixel measurement alias.'],
  ['GuiTabIndex', 'standard.gui tab-index alias.'],
  ['GuiKeyCode', 'standard.gui key-code alias.'],
  ['GuiSelectedIndex', 'standard.gui selected-index alias.'],
  ['GuiEventDimensionPixels', 'standard.gui event dimension alias.'],
  ['GuiHandlerStatus', 'standard.gui GUI handler status alias.'],
  ['GuiRuntimeStatusCode', 'standard.gui runtime status-code alias.'],
  ['GuiDeclarationVerb', 'standard.gui declaration verb token alias.'],
  ['GuiKeywordToken', 'standard.gui keyword token alias.'],
  ['GuiRuntimeTarget', 'standard.gui runtime target token alias.'],
  ['GuiTargetKind', 'standard.gui target-kind enum.'],
  ['GuiWindowLayout', 'standard.gui window-layout enum.'],
  ['GuiControlKind', 'standard.gui control-kind enum.'],
  ['GuiListBoxSelectionMode', 'standard.gui list-box selection enum.'],
  ['GuiEventKind', 'standard.gui event-kind enum.'],
  ['GuiRuntimeStatus', 'standard.gui runtime-status enum.'],
  ['String', 'Canonical string primitive.'],
  ['RawStringPointer', 'Raw null-terminated string pointer before trust-boundary validation.'],
  ['OpaquePointer', 'Opaque memory address value.'],
  ['OpaquePointer', 'Opaque C void pointer alias.'],
  ['OpaquePointer', 'Opaque C void pointer alias.'],
  ['ByteCount', 'C ABI byte-count value.'],
  ['SignedByteCount', 'C ABI signed byte-count value.'],
  ['AddressOffset', 'C ABI pointer offset value.'],
  ['UnixSecondsSinceEpoch', 'C ABI Unix timestamp seconds value.'],
  ['CpuClockTicks', 'C ABI CPU clock tick value.'],
  ['FileByteOffset', 'C ABI file byte offset value.'],
  ['Int8', 'C ABI signed 8-bit byte.'],
  ['UInt8', 'C ABI unsigned 8-bit byte.'],
  ['Int16', 'C ABI signed 16-bit integer.'],
  ['UInt16', 'C ABI unsigned 16-bit integer.'],
  ['Int32', 'C ABI signed 32-bit integer.'],
  ['UInt32', 'C ABI unsigned 32-bit integer.'],
  ['Int64', 'C ABI signed 64-bit integer.'],
  ['UInt64', 'C ABI unsigned 64-bit integer.'],
  ['Float32', 'C ABI 32-bit floating-point value.'],
  ['Float64', 'C ABI 64-bit floating-point value.'],
  ['Void', 'C ABI void result marker.'],
  ['CFile', 'C ABI FILE object marker.'],
  ['FileHandle', 'Opaque C FILE* pointer.'],
  ['FileHandle', 'Opaque C file handle pointer.'],
  ['DecomposedTimeAddress', 'C ABI decomposed-time object marker.'],
  ['DecomposedTimeAddress', 'Opaque C tm* pointer.'],
  ['SetjmpRegisterBuffer', 'Opaque C jmp_buf pointer.'],
  ['DecomposedTimeAddress', 'Opaque C decomposed-time pointer.'],
  ['SetjmpRegisterBuffer', 'Opaque C setjmp buffer pointer.'],
  ['SqliteDatabase', 'Opaque standard.sqlite database handle.'],
  ['SqliteStatement', 'Opaque standard.sqlite prepared statement handle.'],
  ['SqliteRowId', 'standard.sqlite rowid alias.'],
  ['SqlText', 'standard.sqlite SQL source text for prepareStatement or exec.'],
  ['SqliteText', 'standard.sqlite text alias.'],
  ['SqliteBlob', 'standard.sqlite blob pointer alias.'],
  ['SqliteByteCount', 'standard.sqlite byte-count alias.'],
  ['SqliteOpenMode', 'standard.sqlite database-open mode enum.'],
  ['SqliteStepResult', 'standard.sqlite step result enum.'],
  ['SqliteColumnType', 'standard.sqlite column type enum.'],
  ['Url', 'standard.net URL alias.'],
  ['NetworkTimeoutMilliseconds', 'standard.net timeout alias.'],
  ['ResponseBodyLimitBytes', 'standard.net response body limit alias.'],
  ['HttpRedirectLimit', 'standard.net redirect-limit alias.'],
  ['HttpClientStatusCode', 'standard.net HTTP client status-code alias.'],
  ['HttpClientResponse', 'standard.net HTTP client response record.'],
  ['HttpClientBodyText', 'standard.net owned response body text.'],
  ['HttpClientBodyBytes', 'standard.net owned response body bytes.'],
  ['HttpClientBodyLength', 'standard.net response body length alias.'],
  ['HttpClientErrorCode', 'standard.net HTTP client error-code alias.'],
  ['HttpFetchPolicy', 'standard.net fetch policy record.'],
  ['HttpGetRequest', 'standard.net GET request record.'],
  ['HttpTextResponse', 'standard.net text response record.'],
  ['HttpStatusCode', 'standard.http status-code alias used by HTTP response and SSE helpers.'],
  ['HttpHeaderName', 'standard.http header-name alias.'],
  ['HttpHeaderValue', 'standard.http header-value alias.'],
  ['HttpContentType', 'standard.http content-type alias.'],
  ['HttpTextBody', 'standard.http text-body alias.'],
  ['HttpByteBody', 'standard.http byte-body alias.'],
  ['HttpBodyLength', 'standard.http body-length alias.'],
  ['HttpRequestValue', 'standard.http request-derived string alias.'],
  ['SseEventName', 'standard.http server-sent event-name alias.'],
  ['SseEventId', 'standard.http server-sent event id alias.'],
  ['SseEventData', 'standard.http server-sent event payload alias.'],
  ['SseHeartbeatComment', 'standard.http SSE heartbeat-comment alias.'],
  ['HttpClientResponseBody', 'standard.http owned outbound-HTTP response body. Free with c.free after use.'],
  ['JwtAccessToken', 'standard.jwt trusted compact JWT access-token text.'],
  ['JwtSecret', 'standard.jwt server-side HMAC secret alias.'],
  ['JwtPayloadTemplate', 'standard.jwt JSON payload template containing exactly one literal %s placeholder for jti.'],
  ['JwtClaimName', 'standard.jwt top-level claim-name alias.'],
  ['JwtOutputBuffer', 'standard.jwt caller-owned output buffer for compact JWT text.'],
  ['JwtClaimBuffer', 'standard.jwt caller-owned scratch buffer for decoded string claims.'],
  ['AuthEnvelopeBuffer', 'standard.jwt caller-owned output buffer for JSON auth envelopes.'],
  ['BcryptPlaintextPassword', 'standard.bcrypt plaintext password alias; explicitly untrusted.'],
  ['BcryptPasswordHash', 'standard.bcrypt trusted bcrypt hash alias.'],
  ['BcryptHashBuffer', 'standard.bcrypt caller-owned hash output buffer.'],
  ['BcryptRandomBuffer', 'standard.bcrypt caller-owned random byte buffer.'],
  ['SessionToken', 'standard.bcrypt session token text alias.'],
  ['SessionTokenBuffer', 'standard.bcrypt session-token output buffer.'],
  ['Base64UrlBuffer', 'standard.bcrypt base64url output buffer.'],
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
  ['languageMode', 'Top-level language mode declaration: languageMode strictExecutable, refinedSyntax, or permissiveExecutable.'],
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
  ['guiBackend', 'Build tape GUI backend: guiBackend PROJECT win32|winui3. win32 is active/default; winui3 is blocked until Windows App SDK integration lands.'],
  ['buildProfile', 'Build tape profile: buildProfile PROJECT dev|prod.'],
  ['runtimeChecks', 'Build tape runtime checks: runtimeChecks PROJECT off|traps|panic.'],
  ['asyncRuntime', 'Build tape async backend: asyncRuntime PROJECT none|libuv. none preserves 1.0 synchronous lowering; libuv is experimental.'],
  ['optLevel', 'Build tape LLVM optimization level: optLevel PROJECT 0|1|2|3.'],
  ['persistLlvmIr', 'Build tape LLVM IR persistence: persistLlvmIr PROJECT auto|yes|no.'],
  ['emitLlvmIr', 'Build tape pre-optimization LLVM IR switch: emitLlvmIr PROJECT auto|yes|no.'],
  ['llvmIrOutput', 'Build tape pre-optimization LLVM IR output path. Basenames use the managed build folder.'],
  ['emitOptimizedLlvmIr', 'Build tape optimized LLVM IR switch for run/JIT: emitOptimizedLlvmIr PROJECT yes|no.'],
  ['optimizedLlvmIrOutput', 'Build tape optimized LLVM IR output path. Basenames use the managed build folder.'],
  ['buildDir', 'Build tape exact artifact directory: buildDir PROJECT "PATH".'],
  ['buildRoot', 'Build tape artifact parent directory: buildRoot PROJECT "PATH".'],
  ['buildFolderName', 'Build tape managed artifact folder name: buildFolderName PROJECT NAME.'],
  ['cpuBaseline', 'Build tape CPU baseline: cpuBaseline PROJECT generic|native|x86_64_v1|x86_64_v2|x86_64_v3|x86_64_v4|arm64_generic|arm64_v8_2.'],
  ['cpuTune', 'Build tape CPU tune token: cpuTune PROJECT generic|native|CPU_NAME.'],
  ['cpuFeature', 'Build tape CPU feature override: cpuFeature PROJECT FEATURE on|off.'],
  ['cpuFeatureCheck', 'Build tape host CPU check policy: cpuFeatureCheck PROJECT auto|off|warn|require.'],
  ['nativeOutput', 'Build tape native executable output: nativeOutput PROJECT "PATH". Basenames use the managed build folder.'],
  ['keepResources', 'Build tape Windows resource retention switch: keepResources PROJECT yes|no.'],
  ['resourcesDir', 'Build tape Windows resource scratch directory: resourcesDir PROJECT "PATH". Implies keepResources yes.'],
  ['nativeHttpHost', 'Build tape native webserver host metadata: nativeHttpHost PROJECT "HOST".'],
  ['nativeHttpPort', 'Build tape native webserver port metadata: nativeHttpPort PROJECT PORT.'],
  ['formatterSetting', 'Build tape formatter setting: formatterSetting PROJECT KEY VALUE.'],
  ['linterSetting', 'Build tape linter setting: linterSetting PROJECT KEY VALUE.'],
  ['docsOutput', 'Build tape documentation output: docsOutput PROJECT "PATH".'],
  ['buildConstant', 'Build tape constant injection: buildConstant PROJECT NAME TYPE VALUE. Exposes shared build config as module immutable storage.'],
  ['iconRoleDefinition', 'Icon role taxonomy entry: iconRoleDefinition ROLE "text".'],
  ['icon', 'Icon group declaration: icon GROUP.'],
  ['iconRole', 'Icon group role assignment: iconRole GROUP ROLE.'],
  ['iconPurpose', 'Icon group documentation: iconPurpose GROUP "text".'],
  ['iconImage', 'Icon image declaration: iconImage IMAGE.'],
  ['iconImageGroup', 'Icon image group edge: iconImageGroup IMAGE GROUP.'],
  ['iconImagePath', 'Icon image source path: iconImagePath IMAGE "PATH".'],
  ['iconImageFormat', 'Icon image format: iconImageFormat IMAGE png|ico.'],
  ['iconImageWidth', 'Icon image width in pixels: iconImageWidth IMAGE PIXELS.'],
  ['iconImageHeight', 'Icon image height in pixels: iconImageHeight IMAGE PIXELS.'],
  ['iconImageScale', 'Icon image display scale: iconImageScale IMAGE SCALE.'],
  ['iconImageDepth', 'Icon image color depth: iconImageDepth IMAGE bits32|bits24|bits8.'],
  ['iconImagePlatform', 'Icon image platform selector: iconImagePlatform IMAGE any|windows|macos|linux.'],
  ['iconImagePurpose', 'Icon image documentation: iconImagePurpose IMAGE "text".'],
  ['moduleFolder', 'Compatibility module registry alias. Prefer registerModule PROJECT MODULE_PATH "PATH".'],
  ['nativeRuntimeSource', 'Standard-library native adapter source metadata: nativeRuntimeSource MODULE "path.c".'],
  ['nativeRuntimeLinkArg', 'Standard-library native adapter link metadata: nativeRuntimeLinkArg MODULE any|windows|posix "ARG".'],
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
  ['import', 'Module import declaration: import LOCAL_ALIAS MODULE_PATH.'],
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
  ['recordFieldJsonName', 'Record JSON key override: recordFieldJsonName RECORD FIELD "jsonKey".'],
  ['recordFieldJsonOmitWhen', 'Record JSON omission policy: recordFieldJsonOmitWhen RECORD FIELD empty|null|false|zero.'],
  ['enum', 'Enum declaration: enum NAME [repr TYPE]. Parsed by the current compiler.'],
  ['enumCase', 'Enum case declaration: enumCase ENUM_NAME CASE_NAME [VALUE].'],
  ['error', 'Error type declaration: error NAME.'],
  ['errorCase', 'Error variant declaration: errorCase ERROR_TYPE VARIANT [CAUSE_TYPE].'],
  ['operation', 'Operation declaration. Header/context lines attach to this operation.'],
  ['webServer', 'Web server declaration: webServer NAME. Native codegen can lower this target into an HTTP/1.1 executable.'],
  ['serverHost', 'Web server metadata: serverHost SERVER_NAME "host".'],
  ['serverPort', 'Web server metadata: serverPort SERVER_NAME PORT.'],
  ['route', 'Web server route: route SERVER METHOD PATH HANDLER_OPERATION.'],
  ['routeNotFound', 'Web server fallback handler: routeNotFound SERVER HANDLER_OPERATION. Runs when no declared route matches the request path.'],
  ['routeMethodNotAllowed', 'Web server method fallback: routeMethodNotAllowed SERVER HANDLER_OPERATION. Runs when a path matches but the HTTP method does not.'],
  ['webServerStartup', 'Web server startup hook: webServerStartup SERVER HANDLER_OPERATION. Runs once before the native listener starts; handler has no inputs and returns Int32.'],
  ['webServerShutdown', 'Web server shutdown hook: webServerShutdown SERVER HANDLER_OPERATION. Runs once after the native listener returns; handler has no inputs and returns Int32.'],
  ['routeTimeout', 'Web server route timeout metadata keyed by exact route path. Parsed today; preemptive enforcement is future runtime work.'],
  ['routeMiddleware', 'Web server route middleware metadata keyed by exact route path. Native codegen invokes the middleware before the handler.'],
  ['routeTimeoutOptOut', 'Web server route timeout opt-out: routeTimeoutOptOut SERVER PATH "rationale". Used by semlint route coverage checks.'],
  ['routeMiddlewareOptOut', 'Web server route middleware opt-out: routeMiddlewareOptOut SERVER PATH "rationale". Used by semlint route coverage checks.'],
  ['html', 'HTML template syntax family: html template NAME, html parameter template TEMPLATE NAME TYPE, or html body template TEMPLATE.'],
  ['htmlTemplate', 'First-class HTML/SSX template declaration: htmlTemplate NAME. The body starts at htmlBody NAME.'],
  ['htmlArg', 'Legacy HTML template hydration input. Current templates infer holes from `{{name}}` / `{{record.field}}` and pass values with hydrate `argument` rows.'],
  ['htmlBody', 'Starts the indentation-sensitive HTML/SSX body island for a template. The island ends at the next non-empty column-0 SemanticScript line.'],
  ['json', 'JSON syntax family: json body NAME starts an indentation-sensitive JSON literal island.'],
  ['jsonBody', 'Starts an indentation-sensitive JSON literal island bound to a preceding immutable storage binding with the same name.'],
  ['sql', 'SQL syntax family: sql body NAME starts an indentation-sensitive SQL source island.'],
  ['sqlBody', 'Starts an indentation-sensitive SQL source island bound to a preceding immutable SqlText storage binding with the same name.'],
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
  ['runtimeBindingAsyncStart', 'Operation metadata: native async-start symbol paired with runtimeBindingAsyncAwait for generic start CALL lowering.'],
  ['runtimeBindingAsyncAwait', 'Operation metadata: native async-await symbol paired with runtimeBindingAsyncStart for generic await CALL lowering.'],
  ['const', 'Body declaration statement: const NAME TYPE VALUE.'],
  ['var', 'Body declaration statement: var NAME TYPE INITIAL_VALUE.'],
  ['let', 'Legacy body declaration statement: let NAME TYPE INITIAL_VALUE. Prefer explicit storage rows in new executable code.'],
  ['label', 'Control-flow statement: label NAME. Labels are first-class basic blocks.'],
  ['call', 'Call lifecycle statement: call CALL_NAME TARGET_PATH.'],
  ['argument', 'Call argument edge: argument CALL_NAME ARG_NAME ARG_TYPE VALUE_NAME.'],
  ['arg', 'Call lifecycle statement: arg CALL_NAME ARG_NAME VALUE_NAME.'],
  ['timeout', 'Call lifecycle statement: timeout CALL_NAME DURATION_VALUE.'],
  ['cancelOn', 'Call lifecycle statement: cancelOn CALL_NAME CANCELLATION_TOKEN.'],
  ['run', 'Call lifecycle statement: execute call immediately.'],
  ['runChecked', 'Strict checked-call statement: runChecked CALL ok VALUE TYPE error ERROR TYPE else LABEL. Current compiler support is limited to the committed checked-call lowering/tests.'],
  ['start', 'Call lifecycle statement: begin async work. Parsed by current compiler.'],
  ['await', 'Call lifecycle statement: wait for started async work, or introduce an await/case/done wait set. Parsed by current compiler.'],
  ['case', 'Await wait-set statement: case CALL_NAME LABEL_NAME. Must immediately follow await WAIT_SET and materializes the selected call before branching.'],
  ['done', 'Await wait-set terminator: done LABEL_NAME. Branches after all wait-set cases are consumed.'],
  ['bind', 'Binding statement for infallible calls: bind VALUE TYPE CALL_NAME.'],
  ['bindOk', 'Binding statement for success leg: bindOk VALUE TYPE CALL_NAME.'],
  ['bindError', 'Binding statement for failure leg: bindError ERROR ERROR_TYPE CALL_NAME. Must pair with branchIfError.'],
  ['bindOwned', 'Reserved strict ownership statement: bindOwned VALUE TYPE CALL cleanup TARGET. Do not use until parser and ownership-table support are committed.'],
  ['bindOkOwned', 'Reserved strict ownership statement for fallible calls: bindOkOwned VALUE TYPE CALL cleanup TARGET. Do not use until parser and ownership-table support are committed.'],
  ['ignoreOk', 'Binding statement: ignoreOk CALL_NAME TYPE explicitly discards a fallible call success value.'],
  ['ignoreValue', 'Binding statement: ignoreValue CALL_NAME TYPE explicitly discards an infallible call result.'],
  ['ignore', 'Phrase-shaped discard: ignore value|ok|error|void source CALL_NAME [type TYPE].'],
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
  ['jump', 'Unconditional branch statement: jump target LABEL_NAME.'],
  ['branch', 'Control-flow statement: branch LABEL_NAME.'],
  ['branchIf', 'Control-flow statement: branchIf BOOL_VALUE LABEL_NAME. False leg falls through.'],
  ['branchIfError', 'Control-flow statement: branchIfError CALL_NAME LABEL_NAME.'],
  ['branchIfChannelClosed', 'Reserved control-flow statement for closed channel branch.'],
  ['branchSelected', 'Reserved control-flow statement for select result branch.'],
  ['returnOk', 'Return success value from Result operation.'],
  ['returnError', 'Return typed error value from Result operation.'],
  ['returnValue', 'Return plain value.'],
  ['returnVoid', 'Return from a Void/Void operation without exposing the ABI zero sentinel.'],
  ['return', 'Phrase-shaped return: return value VALUE, return ok VALUE, return error ERROR, or return void.'],
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
let compilerEmitOptimizedLlvmIr = false;
let compilerBuildDir = '';
let compilerBuildRoot = '';
let compilerBuildFolderName = '';
let compilerKeepResources = false;
let compilerResourceDir = '';
let compilerCpuBaseline = 'default';
let compilerCpuTune = '';
let compilerCpuFeatureCheck = 'default';
let diagnosticCollection = null;
let lintStatusBarItem = null;
let compilerOutputChannel = null;
const lintUpdateTimeouts = new Map();
const runningLintProcesses = new Map();
const lintRecordCache = new Map();

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
const indentedIslandVerbs = new Set(['htmlBody', 'jsonBody', 'sqlBody']);

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

      if (startsIndentedIsland(tokenizeLine(line.text))) {
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

const tokenAt = (tokens, index) => (tokens[index] ? tokens[index].text : '');

const isHtmlTemplateDeclaration = (tokens) => (
  tokenAt(tokens, 0) === 'html' && tokenAt(tokens, 1) === 'template'
);

const isHtmlParameterDeclaration = (tokens) => (
  tokenAt(tokens, 0) === 'html' && tokenAt(tokens, 1) === 'parameter' && tokenAt(tokens, 2) === 'template'
);

const isHtmlBodyDeclaration = (tokens) => (
  (tokenAt(tokens, 0) === 'html' && tokenAt(tokens, 1) === 'body' && tokenAt(tokens, 2) === 'template')
  || tokenAt(tokens, 0) === 'htmlBody'
);

const isJsonBodyDeclaration = (tokens) => (
  tokenAt(tokens, 0) === 'jsonBody'
  || (tokenAt(tokens, 0) === 'json' && tokenAt(tokens, 1) === 'body')
);

const isSqlBodyDeclaration = (tokens) => (
  tokenAt(tokens, 0) === 'sqlBody'
  || (tokenAt(tokens, 0) === 'sql' && tokenAt(tokens, 1) === 'body')
);

const htmlTemplateNameIndex = (tokens) => {
  if (isHtmlTemplateDeclaration(tokens)) {
    return 2;
  }

  if (isHtmlParameterDeclaration(tokens) || isHtmlBodyDeclaration(tokens)) {
    return 3;
  }

  return 1;
};

const jsonBodyNameIndex = (tokens) => (
  tokenAt(tokens, 0) === 'json' && tokenAt(tokens, 1) === 'body' ? 2 : 1
);

const sqlBodyNameIndex = (tokens) => (
  tokenAt(tokens, 0) === 'sql' && tokenAt(tokens, 1) === 'body' ? 2 : 1
);

const startsIndentedIsland = (tokens) => (
  isJsonBodyDeclaration(tokens) || isSqlBodyDeclaration(tokens) || isHtmlBodyDeclaration(tokens)
);

const operationOwnerIndex = (tokens) => {
  if (tokenAt(tokens, 1) === 'operation') {
    return 2;
  }

  if (tokenAt(tokens, 1) === 'module') {
    return null;
  }

  return 1;
};

const operationOwnerName = (tokens) => {
  const index = operationOwnerIndex(tokens);
  return index === null ? '' : tokenAt(tokens, index);
};

const inputParts = (tokens) => {
  const ownerIndex = operationOwnerIndex(tokens);
  const nameIndex = ownerIndex === null ? 2 : ownerIndex + 1;
  return { ownerIndex, nameIndex, typeIndex: nameIndex + 1 };
};

const outputParts = (tokens) => {
  const ownerIndex = operationOwnerIndex(tokens);
  const typeIndex = ownerIndex === null ? 2 : ownerIndex + 1;
  return { ownerIndex, typeIndex };
};

const narrativeParts = (tokens) => {
  if (tokenAt(tokens, 1) === 'module' || tokenAt(tokens, 1) === 'operation') {
    return { subjectKindIndex: 1, subjectIndex: 2, textIndex: 3 };
  }

  return { subjectKindIndex: null, subjectIndex: 1, textIndex: 2 };
};

const branchLabelIndex = (tokens) => {
  if (tokenAt(tokens, 0) === 'jump' && tokenAt(tokens, 1) === 'target') {
    return 2;
  }

  if (tokenAt(tokens, 0) !== 'branch') {
    return null;
  }

  if (tokenAt(tokens, 1) === 'if' && tokenAt(tokens, 2) === 'condition' && tokenAt(tokens, 4) === 'target') {
    return 5;
  }

  if (tokenAt(tokens, 1) === 'error' && tokenAt(tokens, 2) === 'source' && tokenAt(tokens, 4) === 'target') {
    return 5;
  }

  if (tokenAt(tokens, 1) === 'else' && tokenAt(tokens, 2) === 'target') {
    return 3;
  }

  return 1;
};

const argumentParts = (tokens) => {
  if (tokenAt(tokens, 0) === 'argument') {
    return { callIndex: 1, roleIndex: 2, typeIndex: 3, valueIndex: 4 };
  }

  if (tokenAt(tokens, 0) === 'arg') {
    return { callIndex: 1, roleIndex: 2, typeIndex: null, valueIndex: 3 };
  }

  return null;
};

const bindParts = (tokens) => {
  const verb = tokenAt(tokens, 0);

  if (verb === 'bind' && ['value', 'ok', 'error'].includes(tokenAt(tokens, 1))) {
    return {
      kind: tokenAt(tokens, 1) === 'error' ? 'bound error' : 'bound value',
      nameIndex: 2,
      typeIndex: 3,
      callIndex: 4,
    };
  }

  if (verb === 'bind' || verb === 'bindOk' || verb === 'bindError') {
    return {
      kind: verb === 'bindError' ? 'bound error' : 'bound value',
      nameIndex: 1,
      typeIndex: 2,
      callIndex: 3,
    };
  }

  return null;
};

const returnParts = (tokens) => {
  const verb = tokenAt(tokens, 0);

  if (verb === 'return') {
    const mode = tokenAt(tokens, 1) || 'value';
    return {
      mode,
      valueIndex: mode === 'void' ? null : 2,
    };
  }

  if (verb === 'returnOk') {
    return { mode: 'ok', valueIndex: 1 };
  }

  if (verb === 'returnError') {
    return { mode: 'error', valueIndex: 1 };
  }

  if (verb === 'returnValue') {
    return { mode: 'value', valueIndex: 1 };
  }

  if (verb === 'returnVoid') {
    return { mode: 'void', valueIndex: null };
  }

  return null;
};

const ignoreCallIndex = (tokens) => {
  if (tokenAt(tokens, 0) === 'ignore' && tokenAt(tokens, 2) === 'source') {
    return 3;
  }

  if (tokenAt(tokens, 0) === 'ignoreOk' || tokenAt(tokens, 0) === 'ignoreValue' || tokenAt(tokens, 0) === 'ignoreError') {
    return 1;
  }

  return null;
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
  ['webServerStartup', 2],
  ['webServerShutdown', 2],
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
  'mutex', 'shared', 'channel', 'section', 'domainLiteral', 'literal', 'json', 'jsonBody', 'sql', 'sqlBody',
  'listLiteral', 'htmlTemplate', 'listType', 'arrayType', 'sliceType', 'smallListType',
  'mapType', 'collectionOperation', 'interval', 'workerPool', 'work',
  'buildProject', 'registerModule', 'modulePath', 'mainFile', 'mainOperation',
  'targetRuntime', 'guiBackend', 'buildProfile', 'runtimeChecks', 'asyncRuntime', 'optLevel',
  'cpuBaseline', 'cpuTune', 'cpuFeature', 'cpuFeatureCheck', 'nativeOutput',
  'keepResources', 'resourcesDir', 'nativeHttpHost', 'nativeHttpPort',
  'formatterSetting', 'linterSetting', 'docsOutput', 'nativeRuntimeSource',
  'nativeRuntimeLinkArg',
  'iconRoleDefinition', 'icon', 'iconImage',
]);

const singleCallReferenceVerbs = new Set([
  'run', 'start', 'await', 'case', 'timeout', 'cancelOn', 'ignoreOk', 'ignoreValue',
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

    if (operationMetadataVerbs.has(verb) && operationOwnerName(tokens)) {
      const entry = ensureOperationMetadataEntry(operations, operationOwnerName(tokens));

      if (!entry.section) {
        entry.section = currentSection;
      }

      entry.metadata.push({
        line: lineIndex + 1,
        text: lineText.trim(),
      });
    }

    if (startsIndentedIsland(tokens)) {
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
        {
          const { ownerIndex, nameIndex, typeIndex } = inputParts(tokens);
          addSymbolDeclaration(symbols, tokenText(tokens, nameIndex), declarationBase('input parameter', tokens, lineIndex, {
            name: tokenText(tokens, nameIndex),
            owner: ownerIndex === null ? '?' : tokenText(tokens, ownerIndex),
            type: tokenText(tokens, typeIndex),
          }));
        }
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
      case 'let':
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

      case 'memory':
        if (tokens[2] && ['mutable', 'immutable'].includes(tokens[2].text)) {
          addSymbolDeclaration(symbols, tokenText(tokens, 3), declarationBase('memory binding', tokens, lineIndex, {
            name: tokenText(tokens, 3),
            owner: tokenText(tokens, 1),
            mutability: tokenText(tokens, 2),
            type: tokenText(tokens, 4),
            value: tokenTailText(tokens, 5),
          }));
        }
        break;

      case 'domainLiteral':
      case 'literal':
      case 'jsonBody':
      case 'sqlBody':
      case 'listLiteral':
        addSymbolDeclaration(symbols, tokenText(tokens, 1), declarationBase(readableVerbName(verb).toLowerCase(), tokens, lineIndex, {
          name: tokenText(tokens, 1),
          type: tokenText(tokens, 2),
          value: tokenTailText(tokens, 3),
        }));
        break;

      case 'json':
        if (isJsonBodyDeclaration(tokens)) {
          addSymbolDeclaration(symbols, tokenText(tokens, jsonBodyNameIndex(tokens)), declarationBase('json body', tokens, lineIndex, {
            name: tokenText(tokens, jsonBodyNameIndex(tokens)),
            type: 'JsonText island',
            value: 'indented JSON',
          }));
        }
        break;

      case 'sql':
        if (isSqlBodyDeclaration(tokens)) {
          addSymbolDeclaration(symbols, tokenText(tokens, sqlBodyNameIndex(tokens)), declarationBase('sql body', tokens, lineIndex, {
            name: tokenText(tokens, sqlBodyNameIndex(tokens)),
            type: 'SqlText island',
            value: 'indented SQL',
          }));
        }
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

      case 'import':
        addSymbolDeclaration(symbols, tokenText(tokens, 1), declarationBase('module import', tokens, lineIndex, {
          name: tokenText(tokens, 1),
          details: tokenText(tokens, 2),
        }));
        break;

      case 'dependencyFetch':
        addSymbolDeclaration(symbols, tokenText(tokens, 2), declarationBase('dependency fetch', tokens, lineIndex, {
          name: tokenText(tokens, 2),
          owner: tokenText(tokens, 1),
          details: tokenTailText(tokens, 3),
        }));
        break;

      case 'dependencyCache':
      case 'dependencyLock':
      case 'asyncRuntime':
      case 'keepResources':
      case 'resourcesDir':
      case 'nativeRuntimeSource':
      case 'nativeRuntimeLinkArg':
        addSymbolDeclaration(symbols, tokenText(tokens, 1), declarationBase(readableVerbName(verb).toLowerCase(), tokens, lineIndex, {
          name: tokenText(tokens, 1),
          details: tokenTailText(tokens, 2),
        }));
        break;

      case 'buildConstant':
        addSymbolDeclaration(symbols, tokenText(tokens, 2), declarationBase('build constant', tokens, lineIndex, {
          name: tokenText(tokens, 2),
          owner: tokenText(tokens, 1),
          type: tokenText(tokens, 3),
          value: tokenTailText(tokens, 4),
          mutability: 'immutable',
        }));
        break;

      case 'iconRoleDefinition':
      case 'icon':
      case 'iconImage':
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

      case 'recordFieldJsonName':
      case 'recordFieldJsonOmitWhen':
        addSymbolDeclaration(symbols, tokenText(tokens, 2), declarationBase('record field JSON metadata', tokens, lineIndex, {
          name: tokenText(tokens, 2),
          owner: tokenText(tokens, 1),
          details: tokenTailText(tokens, 3),
        }));
        break;

      case 'htmlArg':
        addSymbolDeclaration(symbols, tokenText(tokens, 2), declarationBase('html template argument', tokens, lineIndex, {
          name: tokenText(tokens, 2),
          owner: tokenText(tokens, 1),
          type: tokenText(tokens, 3),
        }));
        break;

      case 'html':
        if (isHtmlTemplateDeclaration(tokens)) {
          addSymbolDeclaration(symbols, tokenText(tokens, 2), declarationBase('html template', tokens, lineIndex, {
            name: tokenText(tokens, 2),
            details: 'html template',
          }));
        } else if (isHtmlParameterDeclaration(tokens)) {
          addSymbolDeclaration(symbols, tokenText(tokens, 4), declarationBase('html template argument', tokens, lineIndex, {
            name: tokenText(tokens, 4),
            owner: tokenText(tokens, 3),
            type: tokenText(tokens, 5),
          }));
        }
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

      case 'arg':
      case 'argument': {
        const parts = argumentParts(tokens);
        const callDeclaration = parts ? calls.get(tokenText(tokens, parts.callIndex)) : null;

        if (callDeclaration) {
          callDeclaration.args.push({
            role: tokenText(tokens, parts.roleIndex),
            type: parts.typeIndex === null ? '' : tokenText(tokens, parts.typeIndex),
            value: tokenText(tokens, parts.valueIndex),
            line: lineIndex + 1,
          });
        }
        break;
      }

      case 'bind':
      case 'bindOk':
      case 'bindError': {
        const parts = bindParts(tokens);
        addSymbolDeclaration(symbols, tokenText(tokens, parts.nameIndex), declarationBase(parts.kind, tokens, lineIndex, {
          name: tokenText(tokens, parts.nameIndex),
          type: tokenText(tokens, parts.typeIndex),
          sourceCall: tokenText(tokens, parts.callIndex),
        }));

        const callDeclaration = calls.get(tokenText(tokens, parts.callIndex));

        if (callDeclaration) {
          callDeclaration.resultBindings.push({
            verb,
            name: tokenText(tokens, parts.nameIndex),
            type: tokenText(tokens, parts.typeIndex),
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

    if (startsIndentedIsland(tokens)) {
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

  if (operationMetadataVerbs.has(verb) && operationOwnerIndex(tokens) === tokenIndex) {
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

  if ((verb === 'var' || verb === 'let') && index === 1) {
    return 'semanticscriptMutableName';
  }

  if (verb === 'buildConstant' && index === 2) {
    return 'semanticscriptConstName';
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

  if (verb === 'html') {
    if (isHtmlTemplateDeclaration(tokens) && index === 2) {
      return 'semanticscriptDeclaredName';
    }

    if (isHtmlBodyDeclaration(tokens) && index === htmlTemplateNameIndex(tokens)) {
      return 'semanticscriptDeclaredName';
    }

    if (isHtmlParameterDeclaration(tokens)) {
      if (index === 3) {
        return 'semanticscriptDeclaredName';
      }

      if (index === 4) {
        return 'semanticscriptArgumentName';
      }
    }
  }

  if (isJsonBodyDeclaration(tokens) && index === jsonBodyNameIndex(tokens)) {
    return 'semanticscriptConstName';
  }

  if (isSqlBodyDeclaration(tokens) && index === sqlBodyNameIndex(tokens)) {
    return 'semanticscriptConstName';
  }

  const returnInfo = returnParts(tokens);
  if (returnInfo && index === returnInfo.valueIndex) {
    return returnInfo.mode === 'error' ? 'semanticscriptErrorVariant' : 'semanticscriptConstName';
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

  if (verb === 'import') {
    if (index === 1) {
      return 'semanticscriptDeclaredName';
    }

    if (index === 2) {
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

  if ((
    verb === 'field'
    || verb === 'fieldDefault'
    || verb === 'fieldInvariant'
    || verb === 'recordFieldJsonName'
    || verb === 'recordFieldJsonOmitWhen'
  ) && index === 2) {
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

  if (verb === 'memory' && index === 3 && tokens[2] && ['mutable', 'immutable'].includes(tokens[2].text)) {
    return tokens[2].text === 'mutable'
      ? 'semanticscriptMutableName'
      : 'semanticscriptConstName';
  }

  if (verb === 'set' && index === 1 && !['local', 'module', 'sharedState', 'memory', 'storage'].includes(text)) {
    return 'semanticscriptMutableName';
  }

  if (verb === 'set' && index === 2 && tokens[1] && ['local', 'module', 'sharedState', 'memory', 'storage'].includes(tokens[1].text)) {
    return 'semanticscriptMutableName';
  }

  if (verb === 'read' && index === 2 && tokens[1] && tokens[1].text === 'sharedState') {
    return 'semanticscriptDeclaredName';
  }

  if (verb === 'label' && index === 1) {
    return 'semanticscriptLabelName';
  }

  if (branchLabelIndex(tokens) === index) {
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

  if ((verb === 'arg' || verb === 'argument') && argumentParts(tokens) && index === argumentParts(tokens).callIndex) {
    return 'semanticscriptCallObject';
  }

  if ((verb === 'arg' || verb === 'argument') && argumentParts(tokens) && index === argumentParts(tokens).roleIndex) {
    return 'semanticscriptArgumentName';
  }

  if (ignoreCallIndex(tokens) === index) {
    return 'semanticscriptCallObject';
  }

  if (singleCallReferenceVerbs.has(verb) && index === 1) {
    return 'semanticscriptCallObject';
  }

  if (bindParts(tokens) && index === bindParts(tokens).callIndex) {
    return 'semanticscriptCallObject';
  }

  if (bindParts(tokens) && index === bindParts(tokens).nameIndex && bindParts(tokens).kind === 'bound value') {
    return 'semanticscriptConstName';
  }

  if (bindParts(tokens) && index === bindParts(tokens).nameIndex && bindParts(tokens).kind === 'bound error') {
    return 'semanticscriptMutableName';
  }

  if ((verb === 'makeError' || verb === 'declareFailure') && index === 1) {
    return 'semanticscriptMutableName';
  }

  if (verb === 'input' && index === inputParts(tokens).nameIndex) {
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

  if (operationReferenceVerbs.has(verb) && operationOwnerIndex(tokens) === index) {
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

  if (verb === 'authority' && (
    (index === 2 && isLowerQualifiedName(text))
    || (index === 3 && isLowerQualifiedName(text))
  )) {
    return 'semanticscriptEffectPath';
  }

  if (verb === 'capability' && index === 2 && isLowerQualifiedName(text)) {
    return 'semanticscriptEffectPath';
  }

  return null;
};

const domainTargetHoverText = (text) => {
  const methodName = text.split('.')[1];

  if (methodName && methodName.startsWith('checkedMultiply')) {
    return 'docs/ast.md: checked domain multiply lowers to `math.checkedMultiplyInt64`; it is fallible and should use `bindOk`, `bindError`, and `branchIfError`.';
  }

  if (methodName === 'square') {
    return 'docs/ast.md: domain `square` is a semantic method for multiplying a value by itself while keeping the source domain context visible.';
  }

  if (['equal', 'notEqual', 'lessThan', 'lessThanOrEqual', 'greaterThan', 'greaterThanOrEqual'].includes(methodName)) {
    return 'docs/reference/syntax-inventory.md: enum/domain comparison methods preserve the declared type in source. For repr-backed enums the compiler resolves this to the matching width-specific math target, with no implicit widening at the call site.';
  }

  return 'docs/ast.md: `TypeName.methodName` lowers to an underlying primitive based on the alias type while preserving domain context in source.';
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

    if (startsIndentedIsland(tokens)) {
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
  const referencePattern = /\{\{\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*\}\}/g;
  let match;

  while ((match = referencePattern.exec(lineText)) !== null) {
    const start = match.index;
    const end = match.index + match[0].length;

    if (position.character >= start && position.character <= end) {
      return {
        text: match[0],
        rootText: match[1].split('.')[0],
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

    if (isHtmlBodyDeclaration(tokens)) {
      insideHtmlBody = true;
      templateName = tokenText(tokens, htmlTemplateNameIndex(tokens));

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
    case 'let':
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

    case 'import':
      return detailHover(`Module import: ${tokenText(tokens, 1)}`, [
        `Local alias: ${inlineCode(tokenText(tokens, 1))}`,
        `Module path: ${inlineCode(tokenText(tokens, 2))}`,
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

    case 'asyncRuntime':
    case 'keepResources':
    case 'resourcesDir':
      return detailHover(`${readableVerbName(verb)}: ${tokenText(tokens, 1)}`, [
        `Project: ${inlineCode(tokenText(tokens, 1))}`,
        `Value: ${inlineCode(tokenTailText(tokens, 2))}`,
      ]);

    case 'buildConstant':
      return detailHover(`Build constant: ${tokenText(tokens, 2)}`, [
        `Project: ${inlineCode(tokenText(tokens, 1))}`,
        `Name: ${inlineCode(tokenText(tokens, 2))}`,
        `Type: ${inlineCode(tokenText(tokens, 3))}`,
        `Value: ${inlineCode(tokenTailText(tokens, 4))}`,
      ]);

    case 'nativeRuntimeSource':
    case 'nativeRuntimeLinkArg':
      return detailHover(`${readableVerbName(verb)}: ${tokenText(tokens, 1)}`, [
        `Module: ${inlineCode(tokenText(tokens, 1))}`,
        `Value: ${inlineCode(tokenTailText(tokens, 2))}`,
      ]);

    case 'htmlTemplate':
      return detailHover(`HTML template: ${tokenText(tokens, 1)}`, [
        `Declares first-class HTML/SSX template ${inlineCode(tokenText(tokens, 1))}.`,
        'Follow with exactly one `htmlBody` island for the same template name. Dynamic holes are inferred from `{{name}}` / `{{record.field}}`.',
      ]);

    case 'htmlArg':
      return detailHover(`HTML argument: ${tokenText(tokens, 2)}`, [
        `Template: ${inlineCode(tokenText(tokens, 1))}`,
        `Argument: ${inlineCode(tokenText(tokens, 2))}`,
        `Type: ${inlineCode(tokenText(tokens, 3))}`,
        'Legacy row: current templates infer dynamic holes from `{{name}}` / `{{record.field}}` and receive values through hydrate `argument` rows.',
      ]);

    case 'htmlBody':
      return detailHover(`HTML body: ${tokenText(tokens, 1)}`, [
        `Starts the HTML/SSX body for template ${inlineCode(tokenText(tokens, 1))}.`,
        'Indented following lines are parsed as markup until the next non-empty column-0 SemanticScript line.',
      ]);

    case 'html':
      if (isHtmlTemplateDeclaration(tokens)) {
        return detailHover(`HTML template: ${tokenText(tokens, 2)}`, [
          `Declares first-class HTML/SSX template ${inlineCode(tokenText(tokens, 2))}.`,
          'Follow with one `html body template` island for the same template name.',
        ]);
      }

      if (isHtmlParameterDeclaration(tokens)) {
        return detailHover(`HTML parameter: ${tokenText(tokens, 4)}`, [
          `Template: ${inlineCode(tokenText(tokens, 3))}`,
          `Parameter: ${inlineCode(tokenText(tokens, 4))}`,
          `Type: ${inlineCode(tokenText(tokens, 5))}`,
        ]);
      }

      if (isHtmlBodyDeclaration(tokens)) {
        return detailHover(`HTML body: ${tokenText(tokens, htmlTemplateNameIndex(tokens))}`, [
          `Starts the HTML/SSX body for template ${inlineCode(tokenText(tokens, htmlTemplateNameIndex(tokens)))}.`,
          'Indented following lines are parsed as markup until the next non-empty column-0 SemanticScript line.',
        ]);
      }

      break;

    case 'json':
    case 'jsonBody':
      if (!isJsonBodyDeclaration(tokens)) {
        break;
      }

      return detailHover(`JSON body: ${tokenText(tokens, jsonBodyNameIndex(tokens))}`, [
        `Binds validated JSON text to immutable storage ${inlineCode(tokenText(tokens, jsonBodyNameIndex(tokens)))}.`,
        'Indented following lines are parsed as strict JSON until the next non-empty column-0 SemanticScript line.',
      ]);

    case 'sql':
    case 'sqlBody':
      if (!isSqlBodyDeclaration(tokens)) {
        break;
      }

      return detailHover(`SQL body: ${tokenText(tokens, sqlBodyNameIndex(tokens))}`, [
        `Binds validated SQL source text to immutable SqlText storage ${inlineCode(tokenText(tokens, sqlBodyNameIndex(tokens)))}.`,
        'Dynamic values use ? placeholders plus sqlite.bind* rows; interpolation holes are not allowed.',
      ]);

    case 'operation':
      return detailHover(`Operation: ${tokenText(tokens, 1)}`, [
        `Starts the executable operation ${inlineCode(tokenText(tokens, 1))}.`,
        'Its `input`, `output`, `effect`, memory, async, and narrative metadata lines attach to this operation name.',
      ]);

    case 'input':
      {
        const { ownerIndex, nameIndex, typeIndex } = inputParts(tokens);
        return detailHover(`Input: ${tokenText(tokens, nameIndex)}`, [
          `Adds parameter ${inlineCode(tokenText(tokens, nameIndex))} to operation ${inlineCode(tokenText(tokens, ownerIndex))}.`,
          `Type: ${inlineCode(tokenText(tokens, typeIndex))}`,
        ]);
      }

    case 'output':
      {
        const { ownerIndex, typeIndex } = outputParts(tokens);
        return detailHover(`Output contract: ${tokenText(tokens, ownerIndex)}`, [
          `Declares what ${inlineCode(tokenText(tokens, ownerIndex))} returns.`,
          `Return shape: ${inlineCode(tokenTailText(tokens, typeIndex))}`,
        ]);
      }

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
    case 'runtimeBindingAsyncStart':
    case 'runtimeBindingAsyncAwait':
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
      {
        const { subjectKindIndex, subjectIndex, textIndex } = narrativeParts(tokens);
        return detailHover(`${readableVerbName(verb)}: ${tokenText(tokens, subjectIndex)}`, [
          subjectKindIndex === null ? '' : `Subject kind: ${inlineCode(tokenText(tokens, subjectKindIndex))}`,
          `Human context attached to ${inlineCode(tokenText(tokens, subjectIndex))}.`,
          `Text: ${inlineCode(tokenTailText(tokens, textIndex))}`,
        ]);
      }

    case 'call':
      return detailHover(`Call: ${tokenText(tokens, 1)}`, [
        `Creates call object ${inlineCode(tokenText(tokens, 1))}.`,
        `Target: ${inlineCode(tokenText(tokens, 2))}`,
        'Add `arg` lines, execute with `run` or `start`, then bind or ignore the result explicitly.',
      ]);

    case 'arg':
    case 'argument': {
      const parts = argumentParts(tokens);
      return detailHover(`Argument: ${tokenText(tokens, 2)}`, [
        `Passes ${inlineCode(tokenText(tokens, parts.valueIndex))} into call ${inlineCode(tokenText(tokens, parts.callIndex))}.`,
        `Argument role: ${inlineCode(tokenText(tokens, parts.roleIndex))}`,
        parts.typeIndex === null ? '' : `Type: ${inlineCode(tokenText(tokens, parts.typeIndex))}`,
      ]);
    }

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
        'When followed by `case` rows and `done`, this introduces a wait set, materializes whichever case is ready next, and branches to that case label.',
      ]);

    case 'case':
      return detailHover(`Await case: ${tokenText(tokens, 1)}`, [
        `Adds started call ${inlineCode(tokenText(tokens, 1))} to the current wait set.`,
        `Branches to ${inlineCode(tokenText(tokens, 2))} when this future is selected.`,
      ]);

    case 'done':
      return detailHover(`Wait set done: ${tokenText(tokens, 1)}`, [
        `Branches to ${inlineCode(tokenText(tokens, 1))} after every wait-set case has been consumed.`,
      ]);

    case 'bind':
      {
        const parts = bindParts(tokens);
        return detailHover(`Bind result: ${tokenText(tokens, parts.nameIndex)}`, [
          `Stores the result of ${inlineCode(tokenText(tokens, parts.callIndex))} into ${inlineCode(tokenText(tokens, parts.nameIndex))}.`,
          `Type: ${inlineCode(tokenText(tokens, parts.typeIndex))}`,
        ]);
      }

    case 'ignore':
      return detailHover(`Ignore ${tokenText(tokens, 1)}: ${tokenText(tokens, ignoreCallIndex(tokens))}`, [
        `Explicitly discards ${inlineCode(tokenText(tokens, 1))} from ${inlineCode(tokenText(tokens, ignoreCallIndex(tokens)))}.`,
        tokenText(tokens, 4) === 'type' ? `Discarded type: ${inlineCode(tokenText(tokens, 5))}` : '',
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
      if (tokenText(tokens, 1) === 'if') {
        return detailHover(`Conditional branch: ${tokenText(tokens, 5)}`, [
          `Jumps to ${inlineCode(tokenText(tokens, 5))} when ${inlineCode(tokenText(tokens, 3))} is true.`,
          'The false path continues to the next line unless followed by `branch else target ...`.',
        ]);
      }

      if (tokenText(tokens, 1) === 'error') {
        return detailHover(`Error branch: ${tokenText(tokens, 5)}`, [
          `Jumps to ${inlineCode(tokenText(tokens, 5))} if call ${inlineCode(tokenText(tokens, 3))} failed.`,
        ]);
      }

      if (tokenText(tokens, 1) === 'else') {
        return detailHover(`Else branch: ${tokenText(tokens, 3)}`, [
          `Jumps to ${inlineCode(tokenText(tokens, 3))} as the paired fallback path.`,
        ]);
      }

      return detailHover(`Branch: ${tokenText(tokens, 1)}`, [
        `Always jumps to ${inlineCode(tokenText(tokens, 1))}.`,
      ]);

    case 'jump':
      return detailHover(`Jump: ${tokenText(tokens, 2)}`, [
        `Always jumps to ${inlineCode(tokenText(tokens, 2))}.`,
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
        'Returns from an operation declared `output OP Void` or `output OP Void`.',
        'Codegen lowers this to the internal zero sentinel, but the source stays semantically explicit.',
      ]);

    case 'return': {
      const info = returnParts(tokens);
      return detailHover(`Return ${info.mode}`, [
        info.valueIndex === null
          ? 'Returns from a Void/Void operation.'
          : `Returns ${inlineCode(tokenText(tokens, info.valueIndex))} through the ${inlineCode(info.mode)} path.`,
      ]);
    }

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

    case 'recordFieldJsonName':
      return detailHover(`Record JSON field name: ${tokenText(tokens, 2)}`, [
        `Record: ${inlineCode(tokenText(tokens, 1))}`,
        `Field: ${inlineCode(tokenText(tokens, 2))}`,
        `JSON key: ${inlineCode(tokenText(tokens, 3))}`,
      ]);

    case 'recordFieldJsonOmitWhen':
      return detailHover(`Record JSON omit policy: ${tokenText(tokens, 2)}`, [
        `Record: ${inlineCode(tokenText(tokens, 1))}`,
        `Field: ${inlineCode(tokenText(tokens, 2))}`,
        `Policy: ${inlineCode(tokenText(tokens, 3))}`,
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
    case 'webServerStartup':
    case 'webServerShutdown':
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
    case 'let':
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

    case 'json':
    case 'jsonBody':
      if (isJsonBodyDeclaration(tokens) && tokenIndex === jsonBodyNameIndex(tokens)) {
        return `This token selects the immutable storage slot that receives the validated JSON literal.`;
      }
      break;

    case 'sql':
    case 'sqlBody':
      if (isSqlBodyDeclaration(tokens) && tokenIndex === sqlBodyNameIndex(tokens)) {
        return `This token selects the immutable SqlText storage slot that receives the SQL source literal.`;
      }
      break;

    case 'input':
      if (tokenIndex === inputParts(tokens).nameIndex) {
        return `This token declares input parameter ${inlineCode(text)} for ${inlineCode(tokenText(tokens, inputParts(tokens).ownerIndex))}.`;
      }
      if (tokenIndex === inputParts(tokens).typeIndex) {
        return `This token is the parameter type for ${inlineCode(tokenText(tokens, inputParts(tokens).nameIndex))}.`;
      }
      break;

    case 'buildConstant':
      if (tokenIndex === 2) {
        return `This token declares a build-injected immutable constant.`;
      }
      if (tokenIndex === 3) {
        return `This token is the declared type for ${inlineCode(tokenText(tokens, 2))}.`;
      }
      if (tokenIndex >= 4) {
        return `This token contributes to the build constant value for ${inlineCode(tokenText(tokens, 2))}.`;
      }
      break;

    case 'recordFieldJsonName':
    case 'recordFieldJsonOmitWhen':
      if (tokenIndex === 1) {
        return `This token names the record whose JSON mapping metadata is being configured.`;
      }
      if (tokenIndex === 2) {
        return `This token names the record field receiving JSON metadata.`;
      }
      if (tokenIndex >= 3) {
        return `This token configures the JSON mapping metadata for ${inlineCode(tokenText(tokens, 2))}.`;
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

    case 'case':
      if (tokenIndex === 1) {
        return `This token references a started call in the current wait set.`;
      }
      if (tokenIndex === 2) {
        return `This token is the label selected when the call is ready.`;
      }
      break;

    case 'done':
      if (tokenIndex === 1) {
        return `This token is the label selected after all wait-set cases are consumed.`;
      }
      break;

    case 'ignoreOk':
    case 'ignoreValue':
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
        return `Explicit Void/Void return form.`;
      }
      break;

    case 'return': {
      const info = returnParts(tokens);
      if (tokenIndex === 1) {
        return `This token selects the ${inlineCode(info.mode)} return path.`;
      }
      if (tokenIndex === info.valueIndex) {
        return `This token is returned through the ${inlineCode(info.mode)} path.`;
      }
      break;
    }

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
    const declaration = chooseHtmlArgDeclaration(document, htmlArgReference.rootText, position.line);
    const templateName = declaration ? declaration.owner : htmlBodyTemplateAtLine(document, position.line);

    return markdownHover(
      `HTML hole: ${htmlArgReference.text}`,
      [
        templateName ? `Template: ${inlineCode(templateName)}` : '',
        declaration && declaration.type ? `Declared type: ${inlineCode(declaration.type)}` : '',
        'Dynamic HTML holes resolve through hydrate `argument` rows. Bare names and dotted record-field paths are checked by sink context before lowering hydration.',
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
      'docs/ast.md: opaque dependency inputs may appear in `arg` lines to preserve dependency context, but they do not flow into computation.'
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
    const declaration = chooseHtmlArgDeclaration(document, htmlArgReference.rootText, position.line)
      || chooseSymbolDeclaration(getDocumentSymbolIndex(document).symbols.get(htmlArgReference.rootText), null);

    if (declaration) {
      return new vscode.Location(document.uri, declarationRange(document, declaration));
    }
  }

  const tokenInfo = getTokenAtPosition(document, position);

  if (tokenInfo) {
    const buildTapeDefinition = buildTapeDefinitionForToken(document, tokenInfo.tokens, tokenInfo.tokenIndex);

    if (buildTapeDefinition) {
      return buildTapeDefinition;
    }
  }

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
  if (verb === 'html') {
    if (isHtmlTemplateDeclaration(tokens) || isHtmlBodyDeclaration(tokens)) {
      return htmlTemplateNameIndex(tokens);
    }

    if (isHtmlParameterDeclaration(tokens)) {
      return 4;
    }
  }

  switch (verb) {
    case 'input':
      return inputParts(tokens).nameIndex;
    case 'buildConstant':
      return 2;
    case 'json':
      return isJsonBodyDeclaration(tokens) ? jsonBodyNameIndex(tokens) : 1;
    case 'sql':
      return isSqlBodyDeclaration(tokens) ? sqlBodyNameIndex(tokens) : 1;
    case 'htmlArg':
      return 2;
    case 'dependencyFetch':
      return 2;
    case 'importModule':
      return importModuleAliasIndex(tokens);
    case 'import':
      return 1;
    case 'field':
    case 'recordFieldJsonName':
    case 'recordFieldJsonOmitWhen':
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
    case 'html':
    case 'htmlTemplate':
      return vscode.SymbolKind.Class;
    case 'htmlArg':
      return vscode.SymbolKind.Field;
    case 'importModule':
    case 'import':
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
    case 'recordFieldJsonName':
    case 'recordFieldJsonOmitWhen':
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
    case 'buildConstant':
    case 'json':
    case 'jsonBody':
    case 'sql':
    case 'sqlBody':
      return vscode.SymbolKind.Constant;
    case 'var':
    case 'let':
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

  if (verb === 'html') {
    if (isHtmlParameterDeclaration(tokens)) {
      return `${tokenText(tokens, 3)}: ${tokenText(tokens, 5)}`;
    }

    if (isHtmlBodyDeclaration(tokens)) {
      return 'HTML island';
    }

    return 'HTML template';
  }

  if (verb === 'importModule') {
    return tokenText(tokens, importModulePathIndex(tokens));
  }

  if (verb === 'import') {
    return tokenText(tokens, 2);
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
    const { ownerIndex, typeIndex } = inputParts(tokens);
    return `${ownerIndex === null ? '?' : tokenText(tokens, ownerIndex)}: ${tokenText(tokens, typeIndex)}`;
  }

  if (verb === 'const' || verb === 'var' || verb === 'let') {
    return tokenText(tokens, 2);
  }

  if (verb === 'buildConstant') {
    return `${tokenText(tokens, 1)}: ${tokenText(tokens, 3)}`;
  }

  if (verb === 'recordFieldJsonName' || verb === 'recordFieldJsonOmitWhen') {
    return `${tokenText(tokens, 1)} ${tokenTailText(tokens, 3)}`;
  }

  if (isJsonBodyDeclaration(tokens)) {
    return 'JsonText island';
  }

  if (isSqlBodyDeclaration(tokens)) {
    return 'SqlText island';
  }

  return tokenTailText(tokens, 2);
};

const provideDocumentSymbols = (document) => {
  const symbols = [];
  const symbolVerbs = new Set([
    'section', 'project', 'target', 'runtime', 'entry', 'module',
    'buildProject', 'modulePath', 'projectVersion', 'projectLicense',
    'sourceRoot', 'registerModule', 'mainFile', 'mainOperation',
    'targetRuntime', 'guiBackend', 'buildProfile', 'runtimeChecks', 'asyncRuntime', 'optLevel',
    'persistLlvmIr', 'emitLlvmIr', 'llvmIrOutput', 'buildDir',
    'buildRoot', 'buildFolderName', 'cpuBaseline', 'cpuTune',
    'cpuFeature', 'cpuFeatureCheck', 'nativeOutput', 'keepResources',
    'resourcesDir', 'nativeHttpHost', 'nativeHttpPort', 'docsOutput',
    'buildConstant', 'dependencyFetch', 'dependencyCache', 'dependencyLock',
    'nativeRuntimeSource', 'nativeRuntimeLinkArg',
    'import', 'importModule', 'importOperation', 'importType', 'importError',
    'importCapability', 'importConstant',
    'iconRoleDefinition', 'icon', 'iconRole', 'iconPurpose',
    'iconImage', 'iconImageGroup', 'iconImagePath', 'iconImageFormat',
    'iconImageWidth', 'iconImageHeight', 'iconImageScale',
    'iconImageDepth', 'iconImagePlatform', 'iconImagePurpose',
    'exportOperation', 'exportType',
    'exportError', 'exportCapability', 'exportConstant',
    'operation', 'input', 'webServer', 'route', 'record', 'field',
    'recordFieldJsonName', 'recordFieldJsonOmitWhen',
    'enum', 'enumCase', 'error', 'errorCase', 'type', 'capability',
    'authority', 'timeoutBudget', 'storage', 'sharedState', 'const',
    'var', 'let', 'call', 'label', 'jsonCodec', 'json', 'jsonBody', 'policy', 'retryPolicy',
    'workerPool', 'work', 'interval', 'html', 'htmlTemplate', 'htmlArg',
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

    if (startsIndentedIsland(tokens)) {
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
    } else if (isHtmlTemplateDeclaration(tokens) && tokens[2]) {
      const target = `html.hydrate.${tokens[2].text}`;
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
  compilerEmitOptimizedLlvmIr = compilerConfig.get('emitOptimizedLlvmIr', false);
  compilerBuildDir = compilerConfig.get('buildDir', '');
  compilerBuildRoot = compilerConfig.get('buildRoot', '');
  compilerBuildFolderName = compilerConfig.get('buildFolderName', '');
  compilerKeepResources = compilerConfig.get('keepResources', false);
  compilerResourceDir = compilerConfig.get('resourceDir', '');
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

const unquoteToken = (text) => {
  if (!text || text.length < 2 || text[0] !== '"' || text[text.length - 1] !== '"') {
    return text;
  }

  try {
    return JSON.parse(text);
  } catch (_error) {
    return text.slice(1, -1);
  }
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

const buildTapeModuleRegistry = (buildTapePath) => {
  const registry = new Map();

  if (!buildTapePath || !fs.existsSync(buildTapePath)) {
    return registry;
  }

  const buildTapeDirectory = path.dirname(buildTapePath);
  const lines = fs.readFileSync(buildTapePath, 'utf8').split(/\r?\n/);

  lines.forEach((lineText) => {
    const tokens = tokenizeLine(lineText);
    const verb = tokenAt(tokens, 0);

    if ((verb === 'registerModule' || verb === 'moduleFolder') && tokens[2] && tokens[3]) {
      registry.set(
        tokenText(tokens, 2),
        path.resolve(buildTapeDirectory, unquoteToken(tokenText(tokens, 3)))
      );
    }
  });

  return registry;
};

const semanticScriptFileLocation = (filePath) => {
  if (!filePath || !fs.existsSync(filePath)) {
    return null;
  }

  let targetLine = 0;

  try {
    const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/);
    const declarationLine = lines.findIndex((lineText) => {
      const trimmed = lineText.trim();
      return trimmed.startsWith('module ') || trimmed.startsWith('project ') || trimmed.startsWith('buildProject ');
    });

    if (declarationLine >= 0) {
      targetLine = declarationLine;
    }
  } catch (_error) {
    targetLine = 0;
  }

  return new vscode.Location(vscode.Uri.file(filePath), new vscode.Position(targetLine, 0));
};

const buildTapeDefinitionForToken = (document, tokens, tokenIndex) => {
  const buildTapePath = findNearestBuildTapePath(document.fileName);

  if (!buildTapePath) {
    return null;
  }

  const verb = tokenAt(tokens, 0);
  const buildTapeDirectory = path.dirname(buildTapePath);
  const moduleRegistry = buildTapeModuleRegistry(buildTapePath);

  if ((verb === 'registerModule' || verb === 'moduleFolder') && tokens[2] && tokens[3]) {
    const sourcePath = path.resolve(buildTapeDirectory, unquoteToken(tokenText(tokens, 3)));

    if (tokenIndex === 2 || tokenIndex === 3) {
      return semanticScriptFileLocation(sourcePath);
    }
  }

  if (verb === 'mainFile' && tokenIndex === 2) {
    const sourcePath = path.resolve(buildTapeDirectory, unquoteToken(tokenText(tokens, 2)));
    return semanticScriptFileLocation(sourcePath);
  }

  if ((verb === 'import' || verb === 'importModule') && tokenIndex === importModulePathIndex(tokens)) {
    return semanticScriptFileLocation(moduleRegistry.get(tokenText(tokens, importModulePathIndex(tokens))));
  }

  return null;
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

// The compiler IS the linter now: `semanticscript check --json` is the
// structured-diagnostics surface, so the linter resolves the same script.
const findLinterPath = (document) => findCompilerPath(document);

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

const linterRecordKey = (record) => {
  const primary = record && record.primary ? record.primary : {};
  return [
    record.code || '',
    record.kind || '',
    primary.path || '',
    primary.line || 0,
    primary.column || 0,
  ].join(':');
};

const resolveLinterRecordPath = (document, lintCwd, recordPath) => {
  if (!recordPath) {
    return null;
  }

  if (path.isAbsolute(recordPath)) {
    return recordPath;
  }

  const workspaceFolder = vscode.workspace.getWorkspaceFolder(document.uri);
  const candidates = [
    lintCwd ? path.resolve(lintCwd, recordPath) : null,
    workspaceFolder ? path.resolve(workspaceFolder.uri.fsPath, recordPath) : null,
    path.resolve(path.dirname(document.fileName), recordPath),
  ].filter(Boolean);

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }

  return candidates[0] || null;
};

const relatedInformationFromSemlintRecord = (document, record, lintCwd) => {
  const relatedSpans = Array.isArray(record.related) ? record.related : [];

  return relatedSpans.map((span) => {
    const absolutePath = resolveLinterRecordPath(document, lintCwd, span.path);

    if (!absolutePath || !fs.existsSync(absolutePath)) {
      return null;
    }

    const lineIndex = Math.max(0, (span.line || 1) - 1);
    const characterIndex = Math.max(0, (span.column || 1) - 1);
    const location = new vscode.Location(
      vscode.Uri.file(absolutePath),
      new vscode.Position(lineIndex, characterIndex)
    );

    return new vscode.DiagnosticRelatedInformation(
      location,
      span.role || 'related SemanticScript source'
    );
  }).filter(Boolean);
};

const diagnosticFromSemlintRecord = (document, record, lintCwd) => {
  const primary = record.primary || {};
  const diagnostic = new vscode.Diagnostic(
    diagnosticRange(document, primary.line, primary.column),
    semlintMessage(record),
    severityFromLinter(record.severity)
  );
  diagnostic.source = 'semlint';
  diagnostic.code = record.code || undefined;
  diagnostic.relatedInformation = relatedInformationFromSemlintRecord(document, record, lintCwd);
  diagnostic._semanticScriptRecordKey = linterRecordKey(record);
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

const parseLinterDiagnostics = (document, stdout, _lintCwd) => {
  let payload;

  try {
    payload = JSON.parse(stdout || '{}');
  } catch (_error) {
    return {
      diagnostics: [
        new vscode.Diagnostic(
          new vscode.Range(0, 0, 0, Math.max(1, document.lineAt(0).text.length)),
          'semanticscript check returned invalid JSON diagnostics.',
          vscode.DiagnosticSeverity.Error
        ),
      ],
      recordsByKey: new Map(),
    };
  }

  // sem.check.v1: { ok, diagnostics: [{ code, severity, line, message, entity }] }.
  // Tolerate a bare array too. The surface has no column/related/fix data, so
  // diagnostics anchor to the reported line and carry no quick-fix records.
  const records = Array.isArray(payload)
    ? payload
    : (Array.isArray(payload.diagnostics) ? payload.diagnostics : []);

  const diagnostics = records.map((record) => {
    const diagnostic = new vscode.Diagnostic(
      diagnosticRange(document, record.line, record.column),
      record.message || record.rendered || 'SemanticScript diagnostic',
      severityFromLinter(record.severity)
    );
    diagnostic.source = 'semanticscript';
    diagnostic.code = record.code || undefined;
    return diagnostic;
  });

  return { diagnostics, recordsByKey: new Map() };
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

  const documentKey = document.uri.toString();

  if (!linterEnabled) {
    diagnosticCollection.delete(document.uri);
    lintRecordCache.delete(documentKey);
    return;
  }
  const existingProcess = runningLintProcesses.get(documentKey);

  if (existingProcess) {
    existingProcess.kill();
    runningLintProcesses.delete(documentKey);
  }

  if (linterSkipFutureSyntax && linterEngine === 'semlint' && documentUsesFutureSyntax(document)) {
    diagnosticCollection.delete(document.uri);
    lintRecordCache.delete(documentKey);
    setLinterStatus('$(info) SemanticScript future syntax', 'stable semlint is skipped for refined future syntax.');
    clearLinterStatusLater();
    return;
  }

  const linterPath = findLinterPath(document);

  if (!linterPath) {
    diagnosticCollection.delete(document.uri);
    lintRecordCache.delete(documentKey);

    if (showMissingLinterMessage) {
      vscode.window.showWarningMessage(
        `SemanticScript ${linterEngine} linter not found. Set semanticScript.linter.path or open the SemanticScript repo root.`
      );
    }

    return;
  }

  setLinterStatus('$(sync~spin) SemanticScript lint', document.fileName);
  // New compiler: `semanticscript check --json <file>` emits the sem.check.v1
  // structured-diagnostics surface.
  const linterArgs = [linterPath, 'check', '--json', document.fileName];
  const linterCwd = projectRootForDocument(document)
    || vscode.workspace.getWorkspaceFolder(document.uri)?.uri.fsPath
    || path.dirname(document.fileName);

  const lintProcess = childProcess.spawn(
    linterPythonPath,
    linterArgs,
    {
      cwd: linterCwd,
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
    lintRecordCache.delete(documentKey);
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
      lintRecordCache.delete(documentKey);
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

    const { diagnostics, recordsByKey } = parseLinterDiagnostics(document, stdout, linterCwd);
    lintRecordCache.set(documentKey, { cwd: linterCwd, recordsByKey });
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

const codeActionsFromSemlintDiagnostic = (document, diagnostic) => {
  const cacheEntry = lintRecordCache.get(document.uri.toString());

  if (!cacheEntry || !diagnostic || diagnostic.source !== 'semlint' || !diagnostic._semanticScriptRecordKey) {
    return [];
  }

  const record = cacheEntry.recordsByKey.get(diagnostic._semanticScriptRecordKey);

  if (!record || !record.primary || !Array.isArray(record.fixCandidates)) {
    return [];
  }

  const primaryPath = resolveLinterRecordPath(document, cacheEntry.cwd, record.primary.path);

  if (
    !primaryPath
    || path.normalize(primaryPath).toLowerCase() !== path.normalize(document.fileName).toLowerCase()
  ) {
    return [];
  }

  const lineIndex = Math.max(0, Math.min(document.lineCount - 1, (record.primary.line || 1) - 1));
  const line = document.lineAt(lineIndex);
  const indentation = line.text.match(/^\s*/)?.[0] || '';
  let preferredAssigned = false;

  return record.fixCandidates.flatMap((fixCandidate) => {
    if (!fixCandidate.autoApplicable || typeof fixCandidate.shape !== 'string' || fixCandidate.shape.includes('\n')) {
      return [];
    }

    const action = new vscode.CodeAction(
      `SemanticScript: ${fixCandidate.name}`,
      vscode.CodeActionKind.QuickFix
    );
    const edit = new vscode.WorkspaceEdit();
    edit.replace(document.uri, line.range, `${indentation}${fixCandidate.shape.trim()}`);
    action.edit = edit;
    action.diagnostics = [diagnostic];

    if (!preferredAssigned) {
      action.isPreferred = true;
      preferredAssigned = true;
    }

    return [action];
  });
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
    vscode.languages.registerCodeActionsProvider(
      { language: 'semanticscript' },
      {
        provideCodeActions(document, _range, contextForActions) {
          return contextForActions.diagnostics.flatMap((diagnostic) => (
            codeActionsFromSemlintDiagnostic(document, diagnostic)
          ));
        },
      },
      {
        providedCodeActionKinds: [vscode.CodeActionKind.QuickFix],
      }
    )
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
      lintRecordCache.delete(key);
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
      candidates.push(path.join(currentPath, 'semanticscript', 'compiler', 'semanticscript.py'));
      candidates.push(path.join(currentPath, 'compiler', 'semanticscript.py'));
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
    candidates.push(path.join(folder.uri.fsPath, 'semanticscript', 'compiler', 'semanticscript.py'));
    candidates.push(path.join(folder.uri.fsPath, 'compiler', 'semanticscript.py'));
    candidates.push(path.join(folder.uri.fsPath, '..', 'semanticscript', 'compiler', 'semanticscript.py'));
    addAncestorCandidates(folder.uri.fsPath);
  });

  if (document && document.fileName) {
    addAncestorCandidates(path.dirname(document.fileName));
  }

  // Fallback: the compiler shipped beside this extension in the repo tree.
  candidates.push(path.join(__dirname, '..', 'semanticscript', 'compiler', 'semanticscript.py'));

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
  // The new compiler builds a project directory (when a build.sem is present)
  // or a single source file. Its `build` takes only `<path> [-o OUT] [--platform]`
  // — the legacy --build-profile/--opt-level/--cpu-* flags no longer exist.
  const compileSourcePath = buildTapePath ? path.dirname(buildTapePath) : document.fileName;
  const outputPath = compilerOutputPath(document);
  const cwd = buildTapePath
    ? path.dirname(buildTapePath)
    : (vscode.workspace.getWorkspaceFolder(document.uri)?.uri.fsPath || path.dirname(document.fileName));
  const args = [compilerPath, 'build', compileSourcePath, '-o', outputPath];

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
          lintRecordCache.clear();
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
  lintRecordCache.clear();
  disposeDecorations();
};

module.exports = {
  activate,
  deactivate,
};
