# expect.stdout: 0\n
# expect.exit: 0
project IsnanConstArg
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
purpose main "Pass a CFloat64 const directly to c.isnan (no user-op indirection). 3.14 is not NaN, so result is 0."
invariant main "Exercises the FP classifier const-arg path."
label startMain
const triggerSize CByteCount 1
call walkerTriggerCall c.malloc
arg walkerTriggerCall size triggerSize
run walkerTriggerCall
bind triggerBuffer COpaqueMemoryAddress walkerTriggerCall

const piApprox CFloat64 3.14
call isnanCall c.isnan
arg isnanCall value piApprox
run isnanCall
bind isnanResult CSignedInt64 isnanCall
var resultStorage I64 0
set resultStorage isnanResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value resultStorage
run writeCall
ignoreOk writeCall Void

call freeCall c.free
arg freeCall ptr triggerBuffer
run freeCall
const successfulExitCode ExitCode 0
returnOk successfulExitCode
