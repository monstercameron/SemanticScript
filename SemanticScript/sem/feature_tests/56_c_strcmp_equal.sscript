# expect.stdout: 0\n
# expect.exit: 0
project CStrcmpEqual
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
memory main heap no
async main no
purpose main "c.strcmp of two identical strings returns 0."
invariant main "Tests c.strcmp passthrough."
label startMain
const leftText CNullTerminatedByteString "hello"
const rightText CNullTerminatedByteString "hello"
call cmpCall c.strcmp
arg cmpCall left leftText
arg cmpCall right rightText
run cmpCall
bind cmpResult CSignedInt32 cmpCall
var cmpVar I64 0
set cmpVar cmpResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value cmpVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
