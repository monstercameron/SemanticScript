# expect.stdout: 3\n2\n1\n
# expect.exit: 0
project LoopCount3to1
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
purpose main "Simple decrement loop 3..1 via var/set/icmp sge/sub."
invariant main "Loop terminates when counter falls below 1."
label startMain
const startValue I64 3
const lowerBound I64 1
const oneStep I64 1
var counter I64 startValue
label loopHead
call checkCall math.greaterThanOrEqualI64
arg checkCall left counter
arg checkCall right lowerBound
run checkCall
bind shouldContinue Bool checkCall
branchIf shouldContinue loopBody
branch loopExit
label loopBody
call printCall console.writeIntegerLine
arg printCall console console
arg printCall value counter
run printCall
ignoreOk printCall Void
call decCall math.subtractI64
arg decCall left counter
arg decCall right oneStep
run decCall
bind nextCounter I64 decCall
set counter nextCounter
branch loopHead
label loopExit
const successfulExitCode ExitCode 0
returnOk successfulExitCode
