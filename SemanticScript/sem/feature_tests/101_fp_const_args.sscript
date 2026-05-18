# expect.stdout: 1\n0\n1\n
# expect.exit: 0
project FpConstArgsTest
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
purpose main "Pass CFloat64 consts directly to c.signbit, c.isfinite, and c.isinf — exercising the const-arg path on all four FP classifiers."
invariant main "Output: signbit(-1.5)=1, isinf(2.0)=0 (finite), isfinite(2.5)=1."
label startMain
const triggerSize CByteCount 1
call walkerTriggerCall c.malloc
arg walkerTriggerCall size triggerSize
run walkerTriggerCall
bind triggerBuffer COpaqueMemoryAddress walkerTriggerCall

const negOnePtFive CFloat64 -1.5
const twoVal CFloat64 2.0
const twoPtFiveVal CFloat64 2.5

call sbCall c.signbit
arg sbCall value negOnePtFive
run sbCall
bind sbRes CSignedInt64 sbCall
var sbStore I64 0
set sbStore sbRes
call w1 console.writeIntegerLine
arg w1 console console
arg w1 value sbStore
run w1
ignoreOk w1 Void

call iiCall c.isinf
arg iiCall value twoVal
run iiCall
bind iiRes CSignedInt64 iiCall
var iiStore I64 0
set iiStore iiRes
call w2 console.writeIntegerLine
arg w2 console console
arg w2 value iiStore
run w2
ignoreOk w2 Void

call ifCall c.isfinite
arg ifCall value twoPtFiveVal
run ifCall
bind ifRes CSignedInt64 ifCall
var ifStore I64 0
set ifStore ifRes
call w3 console.writeIntegerLine
arg w3 console console
arg w3 value ifStore
run w3
ignoreOk w3 Void

call freeCall c.free
arg freeCall ptr triggerBuffer
run freeCall
const successfulExitCode ExitCode 0
returnOk successfulExitCode
