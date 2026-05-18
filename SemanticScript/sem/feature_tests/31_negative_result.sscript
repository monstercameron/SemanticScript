# expect.stdout: -7\n
# expect.exit: 0
project NegativeResult
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
purpose main "3 - 10 = -7 prints correctly."
invariant main "Negative arithmetic emits signed sub."
label startMain
const threeInitial I64 3
const tenLit I64 10
var leftOp I64 threeInitial
call subCall math.subtractI64
arg subCall left leftOp
arg subCall right tenLit
run subCall
bind subResult I64 subCall
var resultVar I64 threeInitial
set resultVar subResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value resultVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
