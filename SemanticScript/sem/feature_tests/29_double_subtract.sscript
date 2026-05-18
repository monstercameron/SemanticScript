# expect.stdout: 0\n
# expect.exit: 0
project DoubleSubtract
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
purpose main "10 - 5 - 5 = 0 via two chained subtracts."
invariant main "Two sequential subtract calls."
label startMain
const tenInitial I64 10
const fiveLit I64 5
var leftOp I64 tenInitial
call firstSubCall math.subtractI64
arg firstSubCall left leftOp
arg firstSubCall right fiveLit
run firstSubCall
bind midResult I64 firstSubCall
call secondSubCall math.subtractI64
arg secondSubCall left midResult
arg secondSubCall right fiveLit
run secondSubCall
bind finalResult I64 secondSubCall
var resultVar I64 tenInitial
set resultVar finalResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value resultVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
