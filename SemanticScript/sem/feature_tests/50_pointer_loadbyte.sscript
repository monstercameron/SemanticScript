# expect.stdout: 72\n
# expect.exit: 0
project PointerLoadByte
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
purpose main "Load first byte of 'Hi!' (ASCII 'H' = 72) and print."
invariant main "Tests pointer.loadByte from user code with string-const buffer."
label startMain
const greetingText CNullTerminatedByteString "Hi!"
const zeroOffset I64 0
call loadCall pointer.loadByte
arg loadCall buffer greetingText
arg loadCall offset zeroOffset
run loadCall
bind firstByte I8 loadCall
var firstByteVar I64 zeroOffset
set firstByteVar firstByte
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value firstByteVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
