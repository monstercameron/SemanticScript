# expect.stdout: 14\n
# expect.exit: 0
project TwoUserOps
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation addThree
input addThree x CSignedInt64
output addThree Result CSignedInt64 Void
memory addThree heap no
async addThree no
purpose addThree "Returns x + 3."
invariant addThree "Constant offset."
label startAddThree
const threeLit I64 3
call addCall math.addI64
arg addCall left x
arg addCall right threeLit
run addCall
bind addResult I64 addCall
returnOk addResult

operation doubleIt
input doubleIt y CSignedInt64
output doubleIt Result CSignedInt64 Void
memory doubleIt heap no
async doubleIt no
purpose doubleIt "Returns y * 2."
invariant doubleIt "Doubles its input."
label startDoubleIt
const twoLit I64 2
call mulCall math.multiplyI64
arg mulCall left y
arg mulCall right twoLit
run mulCall
bind mulResult I64 mulCall
returnOk mulResult

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Chain user ops: doubleIt(addThree(4)) = (4+3)*2 = 14."
invariant main "Outputs 14."
label startMain
const fourInitial I64 4
var inputValue I64 fourInitial
call addOpCall addThree
arg addOpCall x inputValue
run addOpCall
bindOk addOpResult I64 addOpCall
call dblOpCall doubleIt
arg dblOpCall y addOpResult
run dblOpCall
bindOk dblOpResult I64 dblOpCall
var resultVar I64 fourInitial
set resultVar dblOpResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value resultVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
