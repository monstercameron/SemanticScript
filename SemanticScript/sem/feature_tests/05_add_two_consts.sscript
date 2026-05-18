# expect.stdout: 15\n
# expect.exit: 0
project AddTwoConsts
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
purpose main "Add 8+7 via math.addI64, print result."
invariant main "Computes 15 and emits it."
label startMain
const eightInitial I64 8
var leftOperand I64 eightInitial
const sevenAdd I64 7
call addCall math.addI64
arg addCall left leftOperand
arg addCall right sevenAdd
run addCall
bind sumResult I64 addCall
var sumVar I64 eightInitial
set sumVar sumResult
call writeSumCall console.writeIntegerLine
arg writeSumCall console console
arg writeSumCall value sumVar
run writeSumCall
ignoreOk writeSumCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
