# expect.stdout: 4.000000\n2.500000\n
# expect.exit: 0
project CSqrtFabsTest
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
purpose main "c.sqrt(16.0) == 4.0 and c.fabs(-2.5) == 2.5. Exercises math libc passthroughs from user code (with c.malloc as a walker trigger)."
invariant main "Output is '4.000000\\n2.500000\\n'."
label startMain
const sixteenFloat CFloat64 16.0
const negTwoAndHalf CFloat64 -2.5
const triggerSize CByteCount 1
call walkerTriggerCall c.malloc
arg walkerTriggerCall size triggerSize
run walkerTriggerCall
bind triggerBuffer COpaqueMemoryAddress walkerTriggerCall
call sqrtCall c.sqrt
arg sqrtCall value sixteenFloat
run sqrtCall
bind sqrtResult CFloat64 sqrtCall
call write1Call console.writeFloatLine
arg write1Call console console
arg write1Call value sqrtResult
run write1Call
ignoreOk write1Call Void
call fabsCall c.fabs
arg fabsCall value negTwoAndHalf
run fabsCall
bind fabsResult CFloat64 fabsCall
call write2Call console.writeFloatLine
arg write2Call console console
arg write2Call value fabsResult
run write2Call
ignoreOk write2Call Void
call freeCall c.free
arg freeCall ptr triggerBuffer
run freeCall
const successfulExitCode ExitCode 0
returnOk successfulExitCode
