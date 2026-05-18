# expect.stdout: 16\n
# expect.exit: 0
project NestedUserOp
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation square
input square x CSignedInt64
output square Result CSignedInt64 Void
memory square heap no
async square no
purpose square "Return x squared."
invariant square "x * x."
label startSquare
call mulCall math.multiplyI64
arg mulCall left x
arg mulCall right x
run mulCall
bind productValue I64 mulCall
returnOk productValue

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "square(square(2)) = 16."
invariant main "Nested op application."
label startMain
const twoInitial I64 2
var x I64 twoInitial
call innerCall square
arg innerCall x x
run innerCall
bindOk innerResult I64 innerCall
call outerCall square
arg outerCall x innerResult
run outerCall
bindOk outerResult I64 outerCall
var outputVar I64 twoInitial
set outputVar outerResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value outputVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
