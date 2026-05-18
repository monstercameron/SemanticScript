# expect.stdout: 0\n
# expect.exit: 0
project LoopPrintZero
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
purpose main "Print zero (edge case: writeIntegerLine of 0)."
invariant main "Outputs '0'."
label startMain
const zeroInitial I64 0
var counter I64 zeroInitial
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value counter
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
