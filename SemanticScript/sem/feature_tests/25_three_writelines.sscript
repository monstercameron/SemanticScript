# expect.stdout: first\nsecond\nthird\n
# expect.exit: 0
project ThreeWriteLines
target console
runtime AgentRuntime 0.1
mode capturedOutputReplay
entry console main
error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError
operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Three writeLine calls with three distinct string consts."
invariant main "Order matches source."
label startMain
const firstText CNullTerminatedByteString "first"
const secondText CNullTerminatedByteString "second"
const thirdText CNullTerminatedByteString "third"
call writeFirstCall console.writeLine
arg writeFirstCall console console
arg writeFirstCall text firstText
run writeFirstCall
ignoreOk writeFirstCall Void
call writeSecondCall console.writeLine
arg writeSecondCall console console
arg writeSecondCall text secondText
run writeSecondCall
ignoreOk writeSecondCall Void
call writeThirdCall console.writeLine
arg writeThirdCall console console
arg writeThirdCall text thirdText
run writeThirdCall
ignoreOk writeThirdCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
