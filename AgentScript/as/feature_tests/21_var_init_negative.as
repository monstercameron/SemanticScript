# expect.stdout: -42\n
# expect.exit: 0
project VarInitNegative
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
purpose main "var initialized to a negative const integer."
invariant main "Prints -42 via writeIntegerLine."
label startMain
const negFortyTwoInitial I64 -42
var counter I64 negFortyTwoInitial
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value counter
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
