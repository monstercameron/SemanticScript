# expect.stdout: 4\n
# expect.exit: 0
project DivideInt
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
purpose main "math.divideI64: 20 / 5 = 4."
invariant main "Integer division emits sdiv."
label startMain
const twentyInitial I64 20
const fiveDivisor I64 5
var dividend I64 twentyInitial
call divCall math.divideI64
arg divCall left dividend
arg divCall right fiveDivisor
run divCall
bind quotientResult I64 divCall
var quotientVar I64 twentyInitial
set quotientVar quotientResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value quotientVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
