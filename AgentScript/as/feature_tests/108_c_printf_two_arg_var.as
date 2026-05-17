# expect.stdout: counter=42\n
# expect.exit: 0
project CPrintfTwoArgVarTest
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32
operation main
input main console Console
output main Result ExitCode MainError
effect main read memory.buffer
effect main write console.stdout
memory main heap auto
async main no
purpose main "Exercise 2-arg c.printf where the trailing arg is a *var* (alloca). The emitter must emit a `load` before the call and reference the loaded SSA name."
invariant main "Output is 'counter=42\\n'."
label startMain
const triggerSize CByteCount 1
call walkerTriggerCall c.malloc
arg walkerTriggerCall size triggerSize
run walkerTriggerCall
bind walkerTriggerBuffer COpaqueMemoryAddress walkerTriggerCall

const fortyTwo CSignedInt64 42
var counterStorage I64 0
set counterStorage fortyTwo

const formatStr CNullTerminatedByteString "counter=%lld\n"
call printCall c.printf
arg printCall format formatStr
arg printCall value counterStorage
run printCall
ignoreOk printCall CSignedInt32

call freeCall c.free
arg freeCall ptr walkerTriggerBuffer
run freeCall
const successfulExitCode ExitCode 0
returnOk successfulExitCode
