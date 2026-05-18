# expect.stdout: 10\n
# expect.exit: 0
project UserOpNameCollision
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation doubleIt
input doubleIt n CSignedInt64
output doubleIt Result CSignedInt64 Void
memory doubleIt heap no
async doubleIt no
purpose doubleIt "Doubles input. Param name `n` collides with main's `var n`."
invariant doubleIt "Result is 2n."
label startDoubleIt
const twoLit I64 2
call mulCall math.multiplyI64
arg mulCall left n
arg mulCall right twoLit
run mulCall
bind productResult I64 mulCall
returnOk productResult

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Call doubleIt(5) and print."
invariant main "Outputs 10."
label startMain
const fiveInitial I64 5
var n I64 fiveInitial
call dblCall doubleIt
arg dblCall n n
run dblCall
bindOk dblResult I64 dblCall
var resultVar I64 fiveInitial
set resultVar dblResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value resultVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
