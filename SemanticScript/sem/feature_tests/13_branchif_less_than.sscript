# expect.stdout: less\n
# expect.exit: 0
project BranchIfLessThan
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
purpose main "math.lessThanI64 + branchIf picks the less branch."
invariant main "3 < 7 evaluates true."
label startMain
const threeInitial I64 3
const sevenCompare I64 7
var leftOp I64 threeInitial
call ltCall math.lessThanI64
arg ltCall left leftOp
arg ltCall right sevenCompare
run ltCall
bind isLessThan Bool ltCall
branchIf isLessThan lessLabel
branch greaterEqualLabel
label lessLabel
const lessText CNullTerminatedByteString "less"
call writeLessCall console.writeLine
arg writeLessCall console console
arg writeLessCall text lessText
run writeLessCall
ignoreOk writeLessCall Void
branch endLabel
label greaterEqualLabel
const geText CNullTerminatedByteString "ge"
call writeGeCall console.writeLine
arg writeGeCall console console
arg writeGeCall text geText
run writeGeCall
ignoreOk writeGeCall Void
branch endLabel
label endLabel
const successfulExitCode ExitCode 0
returnOk successfulExitCode
