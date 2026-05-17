# expect.stdout: 42\n
# expect.exit: 0
project MultiplyVarVar
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
purpose main "var * var: 6*7=42 via math.multiplyI64."
invariant main "Both operands are vars; result printed."
label startMain
const sixInitial I64 6
const sevenInitial I64 7
var leftOp I64 sixInitial
var rightOp I64 sevenInitial
call mulCall math.multiplyI64
arg mulCall left leftOp
arg mulCall right rightOp
run mulCall
bind productResult I64 mulCall
var productVar I64 sixInitial
set productVar productResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value productVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
