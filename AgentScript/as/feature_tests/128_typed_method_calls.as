# expect.stdout: ok\n
# expect.exit: 0
# Dotted typed-method call targets (TaskList.append, TaskMap.get, json.decode.X,
# json.encode.X) compile cleanly: ascc.py routes them through the
# external-module fallback in _emit_run; bootstrap_general.exe lowers them
# through its runUnhandled dummy-SSA path. Both produce well-typed IR.
project TypedMethodCallsCompile
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test that dotted typed-method calls (TaskList.append, TaskMap.get, json.decode.X, json.encode.X) compile to valid IR via the external-module fallback."
invariant main "Output is 'ok\\n'."
label startMain

# These calls have no real implementation — they hit the external-module
# fallback in _emit_run that emits zero results. We bind each so the
# emit path exercises both call+arg+run+bind.
const triggerSize CByteCount 1
call walkerTriggerCall c.malloc
arg walkerTriggerCall size triggerSize
run walkerTriggerCall
bind triggerBuffer COpaqueMemoryAddress walkerTriggerCall

const fakeList I64 0
const fakeItem I64 0
call listAppendCall TaskList.append
arg listAppendCall list fakeList
arg listAppendCall item fakeItem
run listAppendCall
bindOk newList I64 listAppendCall

const fakeMap I64 0
const fakeKey I64 0
call mapGetCall TaskMap.get
arg mapGetCall map fakeMap
arg mapGetCall key fakeKey
run mapGetCall
bindOk taskValue I64 mapGetCall

const fakeJson I64 0
call jsonDecodeCall json.decode.Task
arg jsonDecodeCall bytes fakeJson
run jsonDecodeCall
bindOk decodedTask I64 jsonDecodeCall

call jsonEncodeCall json.encode.Task
arg jsonEncodeCall value decodedTask
run jsonEncodeCall
bindOk encodedBytes I64 jsonEncodeCall

call freeCall c.free
arg freeCall ptr triggerBuffer
run freeCall

const okText CNullTerminatedByteString "ok"
call writeCall console.writeLine
arg writeCall console console
arg writeCall text okText
run writeCall
ignoreOk writeCall Void

const successfulExitCode ExitCode 0
returnOk successfulExitCode
