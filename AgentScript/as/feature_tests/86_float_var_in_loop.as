# expect.stdout: 16.000000\n
# expect.exit: 0
project FloatVarInLoop
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32
operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Loop that doubles a CFloat64 var four times: 1.0 -> 2 -> 4 -> 8 -> 16. Exercises a CFloat64 var modified inside a branchIf-driven loop alongside an i64 counter."
invariant main "Uses both float and int math.* primitives in the same operation."
label startMain
const oneFloat CFloat64 1.0
const twoFloat CFloat64 2.0
const oneStep CSignedInt64 1
const zeroInitial CSignedInt64 0
const fourTimes CSignedInt64 4
var accumulator CFloat64 oneFloat
var iterationIndex CSignedInt64 zeroInitial
label loopHead
call doneCheckCall math.greaterThanOrEqualI64
arg doneCheckCall left iterationIndex
arg doneCheckCall right fourTimes
run doneCheckCall
bind isDone Bool doneCheckCall
branchIf isDone loopExit
call doubleCall math.multiplyF64
arg doubleCall left accumulator
arg doubleCall right twoFloat
run doubleCall
bind doubledValue CFloat64 doubleCall
set accumulator doubledValue
call incCall math.addI64
arg incCall left iterationIndex
arg incCall right oneStep
run incCall
bind nextIterationIndex CSignedInt64 incCall
set iterationIndex nextIterationIndex
branch loopHead
label loopExit
call writeCall console.writeFloatLine
arg writeCall console console
arg writeCall value accumulator
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
