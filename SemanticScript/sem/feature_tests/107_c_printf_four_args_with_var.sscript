# expect.stdout: 7 11 13 17\n
# expect.exit: 0
project CPrintfFourArgsWithVarTest
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
purpose main "Exercise 4-arg c.printf where the first trailing arg is a *var* (alloca) and the remaining three are binds. The emitter must emit a `load` before the call and reference the loaded SSA name in the operand list."
invariant main "Output is '7 11 13 17\\n'."
label startMain
const triggerSize CByteCount 1
call walkerTriggerCall c.malloc
arg walkerTriggerCall size triggerSize
run walkerTriggerCall
bind walkerTriggerBuffer COpaqueMemoryAddress walkerTriggerCall

const sevenValue CSignedInt64 7
const elevenValue CSignedInt64 11
const thirteenValue CSignedInt64 13
const seventeenValue CSignedInt64 17

# Var for first trailing arg
var sevenStorage I64 0
set sevenStorage sevenValue

# Binds for remaining three
call idElevenCall identityI64
arg idElevenCall input elevenValue
run idElevenCall
bind elevenBind CSignedInt64 idElevenCall

call idThirteenCall identityI64
arg idThirteenCall input thirteenValue
run idThirteenCall
bind thirteenBind CSignedInt64 idThirteenCall

call idSeventeenCall identityI64
arg idSeventeenCall input seventeenValue
run idSeventeenCall
bind seventeenBind CSignedInt64 idSeventeenCall

const fourArgFormat CNullTerminatedByteString "%lld %lld %lld %lld\n"

call printCall c.printf
arg printCall format fourArgFormat
arg printCall a sevenStorage
arg printCall b elevenBind
arg printCall c thirteenBind
arg printCall d seventeenBind
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
purpose identityI64 "Wrap a const integer in a bind."
label startIdentityI64
returnOk input
