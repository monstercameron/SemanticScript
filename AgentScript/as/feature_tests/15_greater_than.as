# expect.stdout: yes\n
# expect.exit: 0
project GreaterThan
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
purpose main "math.greaterThanI64: 9 > 3."
invariant main "Strict > selects yes."
label startMain
const nineInitial I64 9
const threeCompare I64 3
var leftOp I64 nineInitial
call gtCall math.greaterThanI64
arg gtCall left leftOp
arg gtCall right threeCompare
run gtCall
bind isGreater Bool gtCall
branchIf isGreater yesLabel
branch noLabel
label yesLabel
const yesText CNullTerminatedByteString "yes"
call writeYesCall console.writeLine
arg writeYesCall console console
arg writeYesCall text yesText
run writeYesCall
ignoreOk writeYesCall Void
branch endLabel
label noLabel
const noText CNullTerminatedByteString "no"
call writeNoCall console.writeLine
arg writeNoCall console console
arg writeNoCall text noText
run writeNoCall
ignoreOk writeNoCall Void
branch endLabel
label endLabel
const successfulExitCode ExitCode 0
returnOk successfulExitCode
