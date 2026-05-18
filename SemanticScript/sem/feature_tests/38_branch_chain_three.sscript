# expect.stdout: medium\n
# expect.exit: 0
project BranchChainThree
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
purpose main "Three-way branch on a value's range."
invariant main "Picks medium for 50."
label startMain
const valueInitial I64 50
const lowThreshold I64 10
const highThreshold I64 100
var value I64 valueInitial
call lowCheckCall math.lessThanI64
arg lowCheckCall left value
arg lowCheckCall right lowThreshold
run lowCheckCall
bind isLow Bool lowCheckCall
branchIf isLow lowBranch
call highCheckCall math.greaterThanI64
arg highCheckCall left value
arg highCheckCall right highThreshold
run highCheckCall
bind isHigh Bool highCheckCall
branchIf isHigh highBranch
branch mediumBranch
label lowBranch
const lowText CNullTerminatedByteString "low"
call lowWriteCall console.writeLine
arg lowWriteCall console console
arg lowWriteCall text lowText
run lowWriteCall
ignoreOk lowWriteCall Void
branch endLabel
label mediumBranch
const mediumText CNullTerminatedByteString "medium"
call mediumWriteCall console.writeLine
arg mediumWriteCall console console
arg mediumWriteCall text mediumText
run mediumWriteCall
ignoreOk mediumWriteCall Void
branch endLabel
label highBranch
const highText CNullTerminatedByteString "high"
call highWriteCall console.writeLine
arg highWriteCall console console
arg highWriteCall text highText
run highWriteCall
ignoreOk highWriteCall Void
branch endLabel
label endLabel
const successfulExitCode ExitCode 0
returnOk successfulExitCode
