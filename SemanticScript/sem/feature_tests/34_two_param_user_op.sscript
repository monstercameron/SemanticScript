# expect.stdout: 15\n
# expect.exit: 0
project TwoParamUserOp
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation addTwo
input addTwo a CSignedInt64
input addTwo b CSignedInt64
output addTwo Result CSignedInt64 Void
memory addTwo heap no
async addTwo no
purpose addTwo "Return a + b."
invariant addTwo "Two-parameter user op."
label startAddTwo
call addCall math.addI64
arg addCall left a
arg addCall right b
run addCall
bind sumResult I64 addCall
returnOk sumResult

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Call addTwo(7, 8) = 15."
invariant main "Two-arg call into user op."
label startMain
const sevenInitial I64 7
const eightInitial I64 8
var leftValue I64 sevenInitial
var rightValue I64 eightInitial
call sumCall addTwo
arg sumCall a leftValue
arg sumCall b rightValue
run sumCall
bindOk sumOutcome I64 sumCall
var resultVar I64 sevenInitial
set resultVar sumOutcome
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value resultVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
