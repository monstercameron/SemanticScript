# expect.stdout: 13\n
# expect.exit: 0
project CStrlen
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
purpose main "c.strlen of 'Hello, World!' should be 13."
invariant main "Tests c.strlen passthrough."
label startMain
const greetingText CNullTerminatedByteString "Hello, World!"
call lenCall c.strlen
arg lenCall s greetingText
run lenCall
bind lenValue CByteCount lenCall
var lenVar I64 0
set lenVar lenValue
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value lenVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
