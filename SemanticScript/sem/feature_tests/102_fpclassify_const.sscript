# expect.stdout: 4\n2\n
# expect.exit: 0
project FpclassifyConstTest
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
purpose main "Pass CFloat64 consts to c.fpclassify. 3.14 → 4 (FP_NORMAL), 0.0 → 2 (FP_ZERO)."
invariant main "Exercises the c.fpclassify const-arg path."
label startMain
const triggerSize CByteCount 1
call walkerTriggerCall c.malloc
arg walkerTriggerCall size triggerSize
run walkerTriggerCall
bind triggerBuffer COpaqueMemoryAddress walkerTriggerCall

const normalFloat CFloat64 3.14
const zeroFloat CFloat64 0.0

call normalCall c.fpclassify
arg normalCall value normalFloat
run normalCall
bind normalRes CSignedInt64 normalCall
var normalStore I64 0
set normalStore normalRes
call w1 console.writeIntegerLine
arg w1 console console
arg w1 value normalStore
run w1
ignoreOk w1 Void

call zeroCall c.fpclassify
arg zeroCall value zeroFloat
run zeroCall
bind zeroRes CSignedInt64 zeroCall
var zeroStore I64 0
set zeroStore zeroRes
call w2 console.writeIntegerLine
arg w2 console console
arg w2 value zeroStore
run w2
ignoreOk w2 Void

call freeCall c.free
arg freeCall ptr triggerBuffer
run freeCall
const successfulExitCode ExitCode 0
returnOk successfulExitCode
