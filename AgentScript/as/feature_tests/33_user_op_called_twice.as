# expect.stdout: 6\n10\n
# expect.exit: 0
project UserOpCalledTwice
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation doubleIt
input doubleIt x CSignedInt64
output doubleIt Result CSignedInt64 Void
memory doubleIt heap no
async doubleIt no
purpose doubleIt "Doubles x."
invariant doubleIt "Returns 2x."
label startDoubleIt
const twoLit I64 2
call mulCall math.multiplyI64
arg mulCall left x
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
purpose main "Call doubleIt twice; print both results."
invariant main "Outputs 6 then 10."
label startMain
const threeInitial I64 3
const fiveInitial I64 5
var firstInput I64 threeInitial
var secondInput I64 fiveInitial
call firstCallCall doubleIt
arg firstCallCall x firstInput
run firstCallCall
bindOk firstResult I64 firstCallCall
var firstResultVar I64 threeInitial
set firstResultVar firstResult
call writeFirstCall console.writeIntegerLine
arg writeFirstCall console console
arg writeFirstCall value firstResultVar
run writeFirstCall
ignoreOk writeFirstCall Void
call secondCallCall doubleIt
arg secondCallCall x secondInput
run secondCallCall
bindOk secondResult I64 secondCallCall
var secondResultVar I64 fiveInitial
set secondResultVar secondResult
call writeSecondCall console.writeIntegerLine
arg writeSecondCall console console
arg writeSecondCall value secondResultVar
run writeSecondCall
ignoreOk writeSecondCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
