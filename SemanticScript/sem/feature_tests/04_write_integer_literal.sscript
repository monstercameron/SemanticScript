# expect.stdout: 7\n
# expect.exit: 0
project WriteIntegerLiteral
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
purpose main "console.writeIntegerLine of a var initialized to a const 7."
invariant main "Emits the integer 7 followed by newline."
label startMain
const sevenInitialValue I64 7
var sevenValue I64 sevenInitialValue
call writeSevenCall console.writeIntegerLine
arg writeSevenCall console console
arg writeSevenCall value sevenValue
run writeSevenCall
ignoreOk writeSevenCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
