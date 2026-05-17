# expect.stdout: 1\n
# expect.exit: 0
project ModuloPrint
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
purpose main "math.moduloI64: 10 % 3 = 1."
invariant main "Modulo emits correct srem-based remainder."
label startMain
const tenInitial I64 10
const threeDivisor I64 3
var counter I64 tenInitial
call modCall math.moduloI64
arg modCall left counter
arg modCall right threeDivisor
run modCall
bind remainderResult I64 modCall
var remainderVar I64 tenInitial
set remainderVar remainderResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value remainderVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
