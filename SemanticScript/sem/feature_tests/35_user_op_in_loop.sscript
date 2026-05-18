# expect.stdout: 2\n4\n6\n8\n10\n
# expect.exit: 0
project UserOpInLoop
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
purpose doubleIt "Return 2x."
invariant doubleIt "Doubles input."
label startDoubleIt
const twoLit I64 2
call mulCall math.multiplyI64
arg mulCall left x
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
purpose main "Loop counter 1..5 and print doubleIt(counter) each iteration."
invariant main "Outputs 2,4,6,8,10."
label startMain
const oneInitial I64 1
const fiveBound I64 5
const oneStep I64 1
var counter I64 oneInitial
label loopHead
call checkCall math.lessThanOrEqualI64
arg checkCall left counter
arg checkCall right fiveBound
run checkCall
bind shouldContinue Bool checkCall
branchIf shouldContinue loopBody
branch loopExit
label loopBody
call dblCall doubleIt
arg dblCall x counter
run dblCall
bindOk doubledValue I64 dblCall
var doubledVar I64 oneInitial
set doubledVar doubledValue
call printCall console.writeIntegerLine
arg printCall console console
arg printCall value doubledVar
run printCall
ignoreOk printCall Void
call incCall math.addI64
arg incCall left counter
arg incCall right oneStep
run incCall
bind nextCounter I64 incCall
set counter nextCounter
branch loopHead
label loopExit
const successfulExitCode ExitCode 0
returnOk successfulExitCode
