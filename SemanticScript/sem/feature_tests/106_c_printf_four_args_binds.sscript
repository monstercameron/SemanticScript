# expect.stdout: 10 20 30 40\n
# expect.exit: 0
project CPrintfFourArgsBindsTest
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32
operation main
input main console Console
output main Result ExitCode MainError
effect main read memory.buffer
effect main write memory.buffer
effect main write console.stdout
memory main heap auto
async main no
purpose main "Exercise 4-arg c.printf (format + 4 trailing args) where every trailing arg is an i64 SSA bind. Hits the new emitCprintfFmtPlusThree decomposition path."
invariant main "Output is '10 20 30 40\\n'."
label startMain
const triggerSize CByteCount 1
call walkerTriggerCall c.malloc
arg walkerTriggerCall size triggerSize
run walkerTriggerCall
bind walkerTriggerBuffer COpaqueMemoryAddress walkerTriggerCall

const tenValue CSignedInt64 10
const twentyValue CSignedInt64 20
const thirtyValue CSignedInt64 30
const fortyValue CSignedInt64 40

call idTenCall identityI64
arg idTenCall input tenValue
run idTenCall
bind tenBind CSignedInt64 idTenCall

call idTwentyCall identityI64
arg idTwentyCall input twentyValue
run idTwentyCall
bind twentyBind CSignedInt64 idTwentyCall

call idThirtyCall identityI64
arg idThirtyCall input thirtyValue
run idThirtyCall
bind thirtyBind CSignedInt64 idThirtyCall

call idFortyCall identityI64
arg idFortyCall input fortyValue
run idFortyCall
bind fortyBind CSignedInt64 idFortyCall

const fourArgFormat CNullTerminatedByteString "%lld %lld %lld %lld\n"

call printCall c.printf
arg printCall format fourArgFormat
arg printCall a tenBind
arg printCall b twentyBind
arg printCall c thirtyBind
arg printCall d fortyBind
run printCall
ignoreOk printCall CSignedInt32

call freeCall c.free
arg freeCall ptr walkerTriggerBuffer
run freeCall
const successfulExitCode ExitCode 0
returnOk successfulExitCode

operation identityI64
input identityI64 input CSignedInt64
output identityI64 Result CSignedInt64 Void
purpose identityI64 "Wrap a const integer in a bind so the test exercises the bind-arg path."
label startIdentityI64
returnOk input
