# expect.stdout: counting:\n1\n2\n3\ndone\n
# expect.exit: 0
project LoopWithUserOpAndString
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError

operation identity
input identity x CSignedInt64
output identity Result CSignedInt64 Void
memory identity heap no
async identity no
purpose identity "Return input unchanged."
invariant identity "Identity function."
label startIdentity
returnOk x

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Print 'counting:', 1,2,3, then 'done'."
invariant main "Mixes writeLine, writeIntegerLine, user op call, loop."
label startMain
const oneInitial I64 1
const threeBound I64 3
const oneStep I64 1
const countingText CNullTerminatedByteString "counting:"
const doneText CNullTerminatedByteString "done"
var counter I64 oneInitial
call writeCountingCall console.writeLine
arg writeCountingCall console console
arg writeCountingCall text countingText
run writeCountingCall
ignoreOk writeCountingCall Void
label loopHead
call checkCall math.lessThanOrEqualI64
arg checkCall left counter
arg checkCall right threeBound
run checkCall
bind shouldContinue Bool checkCall
branchIf shouldContinue loopBody
branch loopExit
label loopBody
call idCall identity
arg idCall x counter
run idCall
bindOk idResult I64 idCall
var idVar I64 oneInitial
set idVar idResult
call printCall console.writeIntegerLine
arg printCall console console
arg printCall value idVar
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
call writeDoneCall console.writeLine
arg writeDoneCall console console
arg writeDoneCall text doneText
run writeDoneCall
ignoreOk writeDoneCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
