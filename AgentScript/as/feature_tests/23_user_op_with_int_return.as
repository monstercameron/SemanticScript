# expect.stdout: 8\n
# expect.exit: 0
project UserOpIntReturn
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
purpose doubleIt "Return n * 2."
invariant doubleIt "Result is twice the input."
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
purpose main "Call user op doubleIt(4) and print result."
invariant main "Outputs 8."
label startMain
const fourInitial I64 4
var nValue I64 fourInitial
call dblCall doubleIt
arg dblCall n nValue
run dblCall
bindOk dblResult I64 dblCall
var resultVar I64 fourInitial
set resultVar dblResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value resultVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
