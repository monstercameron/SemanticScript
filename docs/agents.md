# SemanticScript agents.md

Dense agent context. ASCII only. Truth: SYNTAX.md, semsc.py, semlint.py,
vscode-semanticscript/extension.js. Editor support != compiler support.

== core ==
SemanticScript = flat semantic tape. One line = one record. First token = verb.
No expressions, infix ops, parens calls, commas, braces, semicolons, generic
angles, indentation blocks, exceptions, implicit async, dynamic object/array
literals. Context is source data: names, effects, failures, memory, time,
cleanup, authority.

Status: lowered = LLVM now; metadata = parsed/indexed only; sync-fallback =
single-thread lowering; partial = mixed; refined = future/tooling surface.

Good:
  call totalCall math.addI64
  arg totalCall left subtotalAmount
  arg totalCall right taxAmount
  run totalCall
  bind totalAmount I64 totalCall

Bad:
  total = subtotal + tax

== lex/name ==
Line: trim; empty ignored; # comment; # rationale: typed comment; quoted
strings keep spaces; escapes \n \t \r \\ \" \0; whitespace splits tokens.
Typed comments: rationale invariant warning agent memory concurrency timing
failure security dependency observability test todo.

Names:
  camelCaseValue             ops values calls labels
  PascalCaseType             types records enums errors
  dot.path.target            call/dependency path
  ErrorDomain.ErrorVariant   error variant
Avoid: tmp res data value item x y i handler helper doThing.
Prefer: accountLookupCall validatedTaskTitle consoleStdoutWriter.

== skeleton ==
  project ProgramName
  target console
  runtime native 1
  module examples.programName
  entry console main

  error ConsoleWriteError
  errorCase ConsoleWriteError ConsoleWriteFailed CSignedInt32
  capability stdoutWriter console.stdout write

  operation main
  output main ExitCode
  effect main write console.stdout
  memory main noHeapAllocation
  async main no
  purpose main "Do the thing exactly"
  useCapability main stdoutWriter
  const outputText CNullTerminatedByteString "hello world"
  call outputWriteCall console.writeLine
  arg outputWriteCall text outputText
  run outputWriteCall
  ignoreOk outputWriteCall Void
  bindError outputWriteError ConsoleWriteError outputWriteCall
  branchIfError outputWriteCall outputWriteFailed
  const successExitCode ExitCode 0
  returnValue successExitCode
  label outputWriteFailed
  makeError outputWriteFailure ConsoleWriteError.ConsoleWriteFailed outputWriteError
  const writeFailedExitCode ExitCode 1
  returnValue writeFailedExitCode

No entry => library mode: compile all ops + stub main returns 0, except routed
`target webServer` programs, which emit a native HTTP entrypoint.

Top:
  project NAME
  target NAME
  runtime NAME VERSION
  module DOTTED.PATH
  mode capturedOutputReplay
  entry console OPERATION
  importModule DOTTED.PATH [as ALIAS]
  section NAME

== operation ==
  operation OP
  input OP NAME TYPE
  output OP TYPE...
  output OP Result OK_TYPE ERR_TYPE
  effect OP ACTION PATH
  memory OP POLICY...
  async OP yes|no
  purpose OP "text"
  invariant OP "text"
  warning OP "text"
  guarantee OP "text"
  failure OP NAME "text"
  security OP "text"
  timing OP "text"
  observability OP "text"

Owner arg must match current op. Opaque inputs are context, not LLVM params:
console environment process httpRequest databaseClient clock. Do not add
`arg callName console console` to built-in console.writeLine; it only needs
`arg callName text valueName`.

Minimum useful metadata:
  purpose opName "specific intent"
  invariant opName "condition preserved by edits"
  memory opName noHeapAllocation
  async opName no

Effect rule: declare effect only for external/observable resources (console,
filesystem, network, database, heap, shared state, process). Pure arithmetic or
formatting helper ops should omit effect; do not invent `effect OP compute
score`. Any declared effect needs useCapability or authority.

== types/values ==
  Bool -> i1
  I8/CSignedByte/CUnsignedByte -> i8
  I16/CSignedInt16/CUnsignedInt16 -> i16
  I32/ExitCode/CSignedInt32/CUnsignedInt32 -> i32
  I64/CSignedInt64/CUnsignedInt64 -> i64
  F32/CFloat32 -> f32
  F64/CFloat64 -> f64
  String/CNullTerminatedByteString -> i8*
  COpaqueMemoryAddress/CFileHandle/VoidPtr -> i8*
  Void/CVoid -> void where valid

  type AccountId CNullTerminatedByteString
  type LookupResult Result AccountBalance LookupError
  typeInvariant AccountId "non-empty"
  typeRepresentation AccountId CNullTerminatedByteString utf8 nullByte
  typeTrust AccountId trustedInternal
  typeMemory AccountId inline
  typeLayout AccountId packed
  typeParameter LookupResult 0 AccountBalance
  typeLiteralEncoding AccountId utf8
  typeLiteralTerminator AccountId nullByte

  const retryLimit I64 3
  const greetingText String "hello"
  const strictMode Bool true
  var runningTotal I64 0
Bool tokens: true false yes no 1 0.

  domainLiteral signalKillNumber CSignedInt32 9
  domainLiteralSource signalKillNumber posix.SIGKILL
  domainLiteralTrust signalKillNumber trustedStaticLiteral
  literal templateText CNullTerminatedByteString
  literalSource templateText "fixtures/template.txt"
  literalBytes templateText 128
  literalDigest templateText sha256 DIGEST
  literalPreview templateText "preview"
  literalTrust templateText trustedStaticLiteral

== state/memory ==
  storage module immutable zeroValue I64 0
  storage module mutable lastRevision I64 zeroValue
  storage local immutable stepValue I64 1
  storage local mutable currentRevision I64 lastRevision
  set local currentRevision nextRevision
  set module lastRevision nextRevision ownedBy moduleStateOwner

Module mutable => LLVM global. Local mutable => alloca. Owner/protected tails
metadata today.

  sharedState process mutable failureCount I64 zeroValue
  sharedStateOwner failureCount metricsRuntime
  sharedStateGuard failureCount failureCountGuardToken
  read sharedState currentFailureCount I64 failureCount protectedBy failureCountGuardToken
  set sharedState failureCount nextFailureCount protectedBy failureCountGuardToken
  guardTokenSource failureCountGuardToken acquireLockCall
  guardTokenOwner failureCountGuardToken metricsRuntime
  guardTokenProtects failureCountGuardToken failureCount
  guardTokenRelease failureCountGuardToken releaseLock

Pointer:
  pointer.loadByte     buffer offset -> byte
  pointer.storeByte    buffer offset value -> void
  pointer.offset       base offset -> ptr
  pointer.difference   left right -> I64
  pointer.isNull       ptr -> bool/int

== calls ==
Infallible:
  call totalCall math.addI64
  arg totalCall left subtotalAmount
  arg totalCall right taxAmount
  run totalCall
  bind totalAmount I64 totalCall

Fallible:
  call writeCall console.writeLine
  arg writeCall text outputText
  run writeCall
  ignoreOk writeCall Void
  bindError writeError ConsoleWriteError writeCall
  branchIfError writeCall writeFailed
  const successExitCode ExitCode 0
  returnValue successExitCode
  label writeFailed
  makeError writeFailure ConsoleWriteError.ConsoleWriteFailed writeError
  const writeFailedExitCode ExitCode 1
  returnValue writeFailedExitCode

Async/sync-fallback:
  start fetchCall
  await fetchCall
  bindOk fetchedValue ValueType fetchCall
  bindError fetchError FetchError fetchCall

Attach/discard:
  timeout CALL BUDGET
  cancelOn CALL TOKEN
  useRetry CALL POLICY
  ignoreOk CALL TYPE
  ignoreValue CALL TYPE

User op:
  operation addTwoValues
  input addTwoValues leftValue I64
  input addTwoValues rightValue I64
  output addTwoValues I64
  call sumCall math.addI64
  arg sumCall left leftValue
  arg sumCall right rightValue
  run sumCall
  bind sumValue I64 sumCall
  returnValue sumValue

  operation main
  output main ExitCode
  const leftInput I64 40
  const rightInput I64 2
  call answerCall addTwoValues
  arg answerCall leftValue leftInput
  arg answerCall rightValue rightInput
  run answerCall
  bind answerValue I64 answerCall
  returnValue answerValue

Arg names should match callee inputs. Dispatch by callee input order after
dropping opaque inputs.

== control ==
  label NAME
  branch LABEL
  branchIf CONDITION LABEL
  branchIfError CALL LABEL
  returnOk VALUE
  returnError VALUE
  returnValue VALUE

Loop:
  var currentIndex I64 0
  const finalIndex I64 10
  const indexStep I64 1
  label loopStart
  call doneCall math.greaterThanOrEqualI64
  arg doneCall left currentIndex
  arg doneCall right finalIndex
  run doneCall
  bind loopDone Bool doneCall
  branchIf loopDone loopEnd
  call nextIndexCall math.addI64
  arg nextIndexCall left currentIndex
  arg nextIndexCall right indexStep
  run nextIndexCall
  bind nextIndex I64 nextIndexCall
  set local currentIndex nextIndex
  branch loopStart
  label loopEnd

== error/effect/auth/deps ==
  error ConsoleWriteError
  errorCase ConsoleWriteError ConsoleWriteFailed CSignedInt32
  makeError validationFailure RequestError.InvalidJson rawDecodeError
  declareFailure timeoutFailure RequestError.TimedOut timeoutCall

  effect opName write console.stdout
  capability stdoutWriter console.stdout write
  useCapability opName stdoutWriter
  authority opName console.stdout write

  dependency databaseClient kind externalService
  dependencyEffect databaseClient read database.account
  dependencyFunction databaseClient.lookupAccount
  dependencyFunctionInput databaseClient.lookupAccount accountId AccountId
  dependencyFunctionOutput databaseClient.lookupAccount Result AccountBalance LookupError
  dependencyFunctionEffect databaseClient.lookupAccount read database.account
  dependencyFunctionAsync databaseClient.lookupAccount yes

== targets ==
Console:
  console.writeLine arg text only; no arg console console
  console.writeIntegerLine arg value
  console.writeFloatLine arg value

I64:
  math.addI64 subtractI64 multiplyI64 divideI64 moduloI64
  math.equalI64 notEqualI64 lessThanI64 lessThanOrEqualI64
  math.greaterThanI64 greaterThanOrEqualI64 checkedMultiplyI64

F64:
  math.addF64 subtractF64 multiplyF64 divideF64
  math.equalF64 notEqualF64 lessThanF64 lessThanOrEqualF64
  math.greaterThanF64 greaterThanOrEqualF64
  math.intToFloat math.floatToInt

c.*:
  call allocateCall c.malloc
  arg allocateCall size requestedByteCount
  run allocateCall
  bind allocatedBuffer COpaqueMemoryAddress allocateCall

c.* signatures: compiler/libc_registry.py. Prefer SemanticScript camelCase aliases for C
names with underscores.

Heap edge: avoid c.malloc/c.free in demo apps unless the user asks for heap.
If used, declare effect allocate heap, effect free heap, memoryHeap OP yes,
memoryAllocationSource OP ALLOC_CALL, capabilities for heap allocate/free, and
handle c.malloc as fallible with bindError + branchIfError. For executable code,
emit an explicit `call ... c.free` cleanup on every ownership path. A
`defer NAME c.free allocatedPointer` row is useful cleanup metadata, but current
compiler lowering treats non-user-op defer targets as metadata, so do not claim
that row alone proves runtime leak freedom. Linters should accept either a
defer row or an explicit cleanup call that consumes the bound allocation.
There is no general stdlib free wrapper today; stdlib_sem/README explicitly says
c.free is one of the host C calls with no useful pure-SemanticScript substitute. Prefer a
domain-specific stdlib release op when the matching allocator provides one
(example: createDeterministicRandomState -> releaseDeterministicRandomState).
For generic heap buffers or duplicateCStringIntoOwnedMemory output, current
stdlib examples still use c.free / defer NAME c.free POINTER.

Domain method:
  type CountdownValue I64
  call nextCall CountdownValue.subtractPositiveStep
  arg nextCall left currentCountdownValue
  arg nextCall right decrementStep
  run nextCall
  bind nextCountdownValue CountdownValue nextCall

== records/codecs/bounds ==
Edge rule: record/json/trust lines are safe as schema/metadata context. Do not
rely on record fieldGet values for executable output unless you are explicitly
testing record lowering. For demo apps, keep runtime dataflow scalar and print
the scalar values; use record/json/trust as adjacent metadata only.

  record Task
  recordLayout Task packed
  recordAlign Task 8
  field Task taskId TaskId
  field Task title ValidatedText
  field Task completed Bool
  # metadata/schema above; scalar runtime values below are still the print path
  const taskId TaskId 1001
  const taskTitle ValidatedText "demo task"

Record field ops are edge/runtime-specific:
  new taskValue Task
  fieldSet taskValue title validatedTitle
  fieldSet taskValue completed false
  fieldGet taskTitle ValidatedText taskValue title

  recordBuilder taskBuilder Task
  recordSet taskBuilder title validatedTitle
  recordSet taskBuilder completed false
  recordBuild buildTaskCall taskBuilder
  recordBuildFailure buildTaskCall TaskError.InvalidTitle

  jsonCodec taskJsonCodec
  jsonCodecStrict taskJsonCodec yes
  jsonCodecUnknownFields taskJsonCodec reject
  jsonCodecInput taskJsonCodec RawJson
  jsonCodecOutput taskJsonCodec Task
  jsonCodecDecodeTarget taskJsonCodec json.decode.Task
  jsonCodecEncodeTarget taskJsonCodec json.encode.Task
  jsonCodecRequiredField taskJsonCodec title
  jsonCodecDecodeFailure taskJsonCodec TaskDecodeError.MissingTitle
  jsonCodecLimit taskJsonCodec maximumBytes 65536

  trustBoundary ValidatedText
  trustBoundaryKind ValidatedText rawUtf8ToValidatedText
  trustBoundaryInput ValidatedText RawText
  trustBoundaryOutput ValidatedText TrustedText
  trustBoundaryValidator ValidatedText validateText
  trustBoundarySource ValidatedText httpRequest.body

== retry/cleanup/concurrency ==
  retryPolicy lookupRetryPolicy
  retryMaxAttempts lookupRetryPolicy 3
  retryInitialDelay lookupRetryPolicy 50ms
  retryMaximumDelay lookupRetryPolicy 500ms
  retryJitter lookupRetryPolicy yes
  useRetry lookupCall lookupRetryPolicy

  defer releaseDefer releaseLock guardToken
  deferRunOn releaseDefer all
  deferOrder releaseDefer reverseRegistration
  deferFailurePolicy releaseDefer logAndSuppress
  deferConsumes releaseDefer guardToken

Compiler emits user-op defers before returns, reverse registration.

  taskGroup childWorkGroup
  startInGroup childCall childWorkGroup
  awaitGroup childWorkGroup
  bindGroupError childError ChildError childWorkGroup
  branchIfGroupError childWorkGroup childFailed

  workerPool hashWorkerPool size 4
  work hashWork target hashFile
  workArg hashWork path inputFilePath
  submitWork hashWork hashWorkerPool
  awaitWork hashWork

  channel taskChannel Task bounded 1
  send taskChannel builtTask
  receive receivedTask Task taskChannel
  branchIfChannelClosed taskChannel channelClosed

  mutex metricsLock
  lock metricsLock
  unlock metricsLock

  select eventSelect
  selectCase eventSelect taskReady taskReadyBranch
  runSelect eventSelect
  branchSelected eventSelect taskReadyBranch handleTask

  interval heartbeatInterval every 1000ms
  startInterval heartbeatInterval
  awaitIntervalTick heartbeatInterval

Single-thread backend: groups/workers direct-dispatch; channels single slot;
locks/select/interval no-op/fallthrough.

== bindings/intrinsics ==
  operation compareCString
  operationBody compareCString runtimeBinding
  runtimeBinding compareCString runtime.cstring.compare
  runtimeBindingPrecondition compareCString "inputs are null-terminated"
  runtimeBindingFailure compareCString CStringError.InvalidInput

  operation addSignedInt64
  operationBody addSignedInt64 intrinsic
  intrinsicName addSignedInt64 arithmetic.addI64

Selected names lower directly. Unknown runtime binding => normal body.

== linter ==
semlint checks and guardrails: unknown verbs; vague names; missing op metadata; hidden
failures; effects without capability; unresolved refs; arg arity/type; dead
stores; unused calls/labels/consts/inputs/binds/caps/error cases/storage;
allocation in loop; heap contradiction; missing allocation source; unpaired
alloc/free; unclosed file; guard source without release; partial retry/trust/
json codec; raw JSON `%s`; fixed-offset parser invariant; width drift; bad
printf width; Result/Void helper shape; file open/close effects; terminal
state cleanup; record align; zero array length; unawaited group/work; lock
without cleanup; duplicate decls; metadata drift; circular type aliases.
T0/T1/T2 correctness. T3 design debt. T4 style.

== commands ==
  python SemanticScript/compiler/semsc.py file.sscript --parse-only
  python SemanticScript/compiler/semsc.py file.sscript --run
  python SemanticScript/compiler/semsc.py file.sscript --emit-ir out.ll
  python SemanticScript/compiler/semsc.py file.sscript --emit-exe out.exe
  python SemanticScript/linter/semlint.py file.sscript --format json
  python SemanticScript/linter/semlint.py file.sscript --format human
  python SemanticScript/linter/semlint.py file.sscript --format json
  python SemanticScript/linter/semlint.py file.sscript --tier T3 --code SS0101

== change protocol ==
  1 SYNTAX.md schema/status
  2 semsc.py parser + lowering or metadata/sync behavior
  3 feature_tests minimal executable case
  4 semlint known verbs/checks
  5 vscode grammar + semantic roles + hover + symbol index
  6 docs narrow topic + docs/agents.md if relevant
  7 run compiler/linter/editor checks

Never add only highlighting. Parser/linter/docs must move with editor support.
