# expect.stdout: label\n42\nend\n
# expect.exit: 0
project IntermixedWrites
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError
operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Interleaved writeLine and writeIntegerLine."
invariant main "Mixed string and integer output."
label startMain
const labelText CNullTerminatedByteString "label"
const fortyTwoInitial I64 42
const endText CNullTerminatedByteString "end"
var counter I64 fortyTwoInitial
call writeLabelCall console.writeLine
arg writeLabelCall console console
arg writeLabelCall text labelText
run writeLabelCall
ignoreOk writeLabelCall Void
call writeNumCall console.writeIntegerLine
arg writeNumCall console console
arg writeNumCall value counter
run writeNumCall
ignoreOk writeNumCall Void
call writeEndCall console.writeLine
arg writeEndCall console console
arg writeEndCall text endText
run writeEndCall
ignoreOk writeEndCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
