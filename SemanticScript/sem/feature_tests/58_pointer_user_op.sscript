# expect.stdout: 5\n
# expect.exit: 0
project PointerUserOp
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation strlenOf
input strlenOf s CNullTerminatedByteString
output strlenOf Result CByteCount Void
effect strlenOf read memory.buffer
memory strlenOf heap no
async strlenOf no
purpose strlenOf "Return strlen(s) via libc."
invariant strlenOf "Passes pointer s through to c.strlen."
label startStrlenOf
call lenCall c.strlen
arg lenCall s s
run lenCall
bind lenValue CByteCount lenCall
returnOk lenValue

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Call strlenOf('hello') = 5."
invariant main "Pointer-typed user-op call."
label startMain
const greetingText CNullTerminatedByteString "hello"
call myStrlenCall strlenOf
arg myStrlenCall s greetingText
run myStrlenCall
bindOk lenOutcome CByteCount myStrlenCall
var resultVar I64 0
set resultVar lenOutcome
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value resultVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
