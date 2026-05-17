# expect.stdout: 15\n
# expect.exit: 0
project LoopSum1to5
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
purpose main "Accumulate sum 1+2+3+4+5 via var+add+branchIf loop."
invariant main "Result is 15."
label startMain
const oneInitial I64 1
const fiveBound I64 5
const oneStep I64 1
const zeroInitial I64 0
var counter I64 oneInitial
var accumulator I64 zeroInitial
label loopHead
call checkCall math.lessThanOrEqualI64
arg checkCall left counter
arg checkCall right fiveBound
run checkCall
bind shouldContinue Bool checkCall
branchIf shouldContinue loopBody
branch loopExit
label loopBody
call addAccCall math.addI64
arg addAccCall left accumulator
arg addAccCall right counter
run addAccCall
bind nextAccumulator I64 addAccCall
set accumulator nextAccumulator
call incCall math.addI64
arg incCall left counter
arg incCall right oneStep
run incCall
bind nextCounter I64 incCall
set counter nextCounter
branch loopHead
label loopExit
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value accumulator
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
