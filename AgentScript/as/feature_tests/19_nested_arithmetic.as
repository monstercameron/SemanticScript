# expect.stdout: 25\n
# expect.exit: 0
project NestedArithmetic
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
purpose main "(3 + 2) * 5 = 25 via chained binds."
invariant main "Bind result of first op feeds second op."
label startMain
const threeInitial I64 3
const twoLit I64 2
const fiveLit I64 5
var leftOp I64 threeInitial
call addCall math.addI64
arg addCall left leftOp
arg addCall right twoLit
run addCall
bind sumResult I64 addCall
call mulCall math.multiplyI64
arg mulCall left sumResult
arg mulCall right fiveLit
run mulCall
bind productResult I64 mulCall
var resultVar I64 threeInitial
set resultVar productResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value resultVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
