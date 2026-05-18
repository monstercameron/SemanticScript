# expect.stdout: 1\n3\n5\n7\n
# expect.exit: 0
project TwoVarLoop
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
purpose main "Two simultaneous loop vars: counter and value (odd numbers 1,3,5,7)."
invariant main "Counter bounded; value increments by 2 each step."
label startMain
const oneInitial I64 1
const oneStep I64 1
const twoStep I64 2
const fourBound I64 4
const zeroInitial I64 0
var counter I64 zeroInitial
var oddValue I64 oneInitial
label loopHead
call checkCall math.lessThanI64
arg checkCall left counter
arg checkCall right fourBound
run checkCall
bind shouldContinue Bool checkCall
branchIf shouldContinue loopBody
branch loopExit
label loopBody
call printCall console.writeIntegerLine
arg printCall console console
arg printCall value oddValue
run printCall
ignoreOk printCall Void
call incCounterCall math.addI64
arg incCounterCall left counter
arg incCounterCall right oneStep
run incCounterCall
bind nextCounter I64 incCounterCall
set counter nextCounter
call incOddCall math.addI64
arg incOddCall left oddValue
arg incOddCall right twoStep
run incOddCall
bind nextOdd I64 incOddCall
set oddValue nextOdd
branch loopHead
label loopExit
const successfulExitCode ExitCode 0
returnOk successfulExitCode
