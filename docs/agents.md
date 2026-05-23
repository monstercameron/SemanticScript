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

== stable tool loop ==
Use the `sem` wrapper as the public agent contract before falling back to raw
compiler/linter internals.

Load matching rules:
  python SemanticScript\tools\sem.py --version --json
  python SemanticScript\tools\sem.py skills list --json
  python SemanticScript\tools\sem.py skills get sem sem-agent --json

Check and inspect:
  python SemanticScript\tools\sem.py check --json PATH
  python SemanticScript\tools\sem.py readiness --json PATH
  python SemanticScript\tools\sem.py graph --kind calls --json PATH
  python SemanticScript\tools\sem.py slice --operation NAME --json PATH
  python SemanticScript\tools\sem.py explain SS3104 --json

Repair and verify:
  python SemanticScript\tools\sem.py fix --plan --json PATH
  python SemanticScript\tools\sem.py patch --dry-run --json PLAN.json
  python SemanticScript\tools\sem.py patch --apply --json PLAN.json
  python SemanticScript\tools\sem.py test --json PATH

Current JSON surfaces:
  sem.version.v1
  sem.skills.v1
  sem.readiness.v1
  sem.context.v1
  sem.symbols.v1
  sem.check.v1
  sem.graph.v1
  sem.slice.v1
  sem.size.v1
  sem.explain.v1
  sem.fixPlan.v1
  sem.patch.v1
  sem.dev.v1
  sem.test.v1

Good:
  call totalCall math.addI64
  argument totalCall left I64 subtotalAmount
  argument totalCall right I64 taxAmount
  run totalCall
  bind value totalAmount I64 totalCall

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
  output operation main ExitCode
  effect main write console.stdout
  memory main noHeapAllocation
  async main no
  purpose main "Do the thing exactly"
  useCapability main stdoutWriter
  storage local immutable outputText CNullTerminatedByteString "hello world"
  call outputWriteCall console.writeLine
  argument outputWriteCall text CNullTerminatedByteString outputText
  run outputWriteCall
  ignore ok source outputWriteCall type Void
  bind error outputWriteError ConsoleWriteError outputWriteCall
  branch error source outputWriteCall target outputWriteFailed
  storage local immutable successExitCode ExitCode 0
  return value successExitCode
  label outputWriteFailed
  makeError outputWriteFailure ConsoleWriteError.ConsoleWriteFailed outputWriteError
  storage local immutable writeFailedExitCode ExitCode 1
  return value writeFailedExitCode

No entry => library mode: compile all ops + stub main returns 0, except routed
`target webServer` programs, which emit a native HTTP entrypoint. Reserved
`target windowsGui` should also be a no-entry target, but only through the
small native GUI bridge described below.

Top:
  project NAME
  target NAME
  runtime NAME VERSION
  module DOTTED.PATH
  mode capturedOutputReplay
  entry console OPERATION
  importModule DOTTED.PATH [as ALIAS]
  section NAME

== std imports ==
Std is a library tree, not a build project. Do not add `std/build.sem`.
Root relay: `SemanticScript/std/module.sem`.
Module entries: `SemanticScript/std/<module>/main.sem`.
Self-tests: `SemanticScript/std/<module>/main.test.sem`.

Preferred imports:
  importModule html standard.html
  importModule http standard.http
  importModule json standard.json
  importModule sqlite standard.sqlite
  importModule gui standard.gui

Std resolution order:
  --std-path PATH
  SEMANTICSCRIPT_STD_PATH or SEMSC_STD_PATH
  vendored ancestor std/
  current-working-directory std/
  compiler-bundled compiler/../std

This means apps outside the repo can still import `standard.*` when compiled by
the installed compiler, or when the std root is passed explicitly.

== windows gui ==
Compiler-owned GUI surface should stay minimal:
  target windowsGui
  targetRuntime PROJECT windowsGui
  guiBackend PROJECT win32|winui3  # win32 default; winui3 scaffold is blocked until Windows App SDK build integration
  native GUI runtime link/codegen bridge
  preserve GuiSession and GuiEvent handler ABI inputs
  lower explicit standard.gui gui.* calls

Do not add `entry windowsGui OPERATION`. Do not move control/event validation
into a giant compiler grammar. `standard.gui` owns GUI functions,
contracts, capabilities, and most validation. Preferred import:
  importModule gui standard.gui

Do not implement WinUI by adding C# / XAML app sidecars under `apps/`. The app
UI source remains SemanticScript; WinUI belongs behind `guiBackend winui3` as a
native backend adapter exporting the existing `ss_gui_*` ABI.

Standard GUI source shape:
  entry console main
  operation main
  call createApp gui.applicationCreate
  argument createApp title GuiText titleText
  run createApp
  bind value app GuiApplication createApp
  call createWindow gui.windowCreate
  ...
  call runApp gui.applicationRun

GUI handler ABI:
  input saveClicked session GuiSession
  input saveClicked event GuiEvent
  output saveClicked CSignedInt32

Reserved gui.* targets live under standard.gui contracts:
  gui.applicationCreate gui.windowCreate gui.buttonCreate
  gui.windowAddControl gui.applicationSetMainWindow gui.applicationRun
  gui.textBoxText gui.textBoxSetText
  gui.listBoxSelectedIndex gui.listBoxAppendItem gui.listBoxClear
  gui.windowClose
  gui.eventKeyCode gui.eventSelectedIndex
  gui.eventWindowWidth gui.eventWindowHeight

== operation ==
  operation OP
  input operation OP NAME TYPE
  output operation OP TYPE...
  output operation OP Result OK_TYPE ERR_TYPE
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

Owner argument must match current op. Opaque inputs are context, not LLVM params:
console environment process httpRequest databaseClient clock. Do not add
`argument callName console Console console` to built-in console.writeLine; it
only needs `argument callName text String valueName`.

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

  storage local immutable retryLimit I64 3
  storage local immutable greetingText String "hello"
  storage local immutable strictMode Bool true
  storage local mutable runningTotal I64 0
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
  argument totalCall left I64 subtotalAmount
  argument totalCall right I64 taxAmount
  run totalCall
  bind value totalAmount I64 totalCall

Fallible:
  call writeCall console.writeLine
  argument writeCall text CNullTerminatedByteString outputText
  run writeCall
  ignore ok source writeCall type Void
  bind error writeError ConsoleWriteError writeCall
  branch error source writeCall target writeFailed
  storage local immutable successExitCode ExitCode 0
  return value successExitCode
  label writeFailed
  makeError writeFailure ConsoleWriteError.ConsoleWriteFailed writeError
  storage local immutable writeFailedExitCode ExitCode 1
  return value writeFailedExitCode

Async/sync-fallback:
  start fetchCall
  await fetchCall
  bind ok fetchedValue ValueType fetchCall
  bind error fetchError FetchError fetchCall

Attach/discard:
  timeout CALL BUDGET
  cancelOn CALL TOKEN
  useRetry CALL POLICY
  ignore ok source CALL type TYPE
  ignore value source CALL type TYPE

User op:
  operation addTwoValues
  input operation addTwoValues leftValue I64
  input operation addTwoValues rightValue I64
  output operation addTwoValues I64
  call sumCall math.addI64
  argument sumCall left I64 leftValue
  argument sumCall right I64 rightValue
  run sumCall
  bind value sumValue I64 sumCall
  return value sumValue

  operation main
  output operation main ExitCode
  storage local immutable leftInput I64 40
  storage local immutable rightInput I64 2
  call answerCall addTwoValues
  argument answerCall leftValue I64 leftInput
  argument answerCall rightValue I64 rightInput
  run answerCall
  bind value answerValue I64 answerCall
  return value answerValue

Argument names should match callee inputs. Dispatch by callee input order after
dropping opaque inputs.

== control ==
  label NAME
  jump target LABEL
  branch if condition CONDITION target LABEL
  branch error source CALL target LABEL
  branch else target LABEL
  return ok VALUE
  return error VALUE
  return value VALUE
  return void

Loop:
  storage local mutable currentIndex I64 0
  storage local immutable finalIndex I64 10
  storage local immutable indexStep I64 1
  label loopStart
  call doneCall math.greaterThanOrEqualI64
  argument doneCall left I64 currentIndex
  argument doneCall right I64 finalIndex
  run doneCall
  bind value loopDone Bool doneCall
  branch if condition loopDone target loopEnd
  call nextIndexCall math.addI64
  argument nextIndexCall left I64 currentIndex
  argument nextIndexCall right I64 indexStep
  run nextIndexCall
  bind value nextIndex I64 nextIndexCall
  set local currentIndex nextIndex
  jump target loopStart
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
  console.writeLine argument text only; no argument console console
  console.writeIntegerLine argument value
  console.writeFloatLine argument value

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
  argument allocateCall size CByteCount requestedByteCount
  run allocateCall
  bind value allocatedBuffer COpaqueMemoryAddress allocateCall

c.* signatures: compiler/libc_registry.py. Prefer SemanticScript camelCase aliases for C
names with underscores.

Heap edge: avoid c.malloc/c.free in demo apps unless the user asks for heap.
If used, declare effect allocate heap, effect free heap, memoryHeap OP yes,
memoryAllocationSource OP ALLOC_CALL, capabilities for heap allocate/free, and
handle c.malloc as fallible with `bind error` + `branch error`. For executable code,
emit an explicit `call ... c.free` cleanup on every ownership path. A
`defer NAME c.free allocatedPointer` row is useful cleanup metadata, but current
compiler lowering treats non-user-op defer targets as metadata, so do not claim
that row alone proves runtime leak freedom. Linters should accept either a
defer row or an explicit cleanup call that consumes the bound allocation.
There is no general stdlib free wrapper today; std/README explicitly says
c.free is one of the host C calls with no useful pure-SemanticScript substitute. Prefer a
domain-specific stdlib release op when the matching allocator provides one
(example: createDeterministicRandomState -> releaseDeterministicRandomState).
For generic heap buffers or duplicateCStringIntoOwnedMemory output, current
stdlib examples still use c.free / defer NAME c.free POINTER.

Domain method:
  type CountdownValue I64
  call nextCall CountdownValue.subtractPositiveStep
  argument nextCall left CountdownValue currentCountdownValue
  argument nextCall right CountdownValue decrementStep
  run nextCall
  bind value nextCountdownValue CountdownValue nextCall

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
  storage local immutable taskId TaskId 1001
  storage local immutable taskTitle ValidatedText "demo task"

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
  jsonCodecDecodeTarget taskJsonCodec json.parse.Task
  jsonCodecEncodeTarget taskJsonCodec json.stringify.Task
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

Pure ABI names lower directly. Policy-bearing runtime bindings such as retry
delay, metrics increment, metrics lock token sentinels, scheduler sleep,
calendar predicates, and UTF-8 validation must be normal SemanticScript
operation bodies or explicit native runtime calls; known legacy targets are
compile-blocking.

== linter ==
semlint checks and guardrails: unknown verbs; vague names; missing op metadata; hidden
failures; effects without capability; unresolved refs; argument arity/type; dead
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
