# expect.stdout: different\n
# expect.exit: 0
project NotEqualBranch
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
purpose main "math.notEqualI64 returns true when args differ."
invariant main "Picks 'different' branch."
label startMain
const aInitial I64 1
const bCompare I64 2
var leftOp I64 aInitial
call neCall math.notEqualI64
arg neCall left leftOp
arg neCall right bCompare
run neCall
bind isDifferent Bool neCall
branchIf isDifferent diffLabel
branch sameLabel
label diffLabel
const diffText CNullTerminatedByteString "different"
call writeDiffCall console.writeLine
arg writeDiffCall console console
arg writeDiffCall text diffText
run writeDiffCall
ignoreOk writeDiffCall Void
branch endLabel
label sameLabel
const sameText CNullTerminatedByteString "same"
call writeSameCall console.writeLine
arg writeSameCall console console
arg writeSameCall text sameText
run writeSameCall
ignoreOk writeSameCall Void
branch endLabel
label endLabel
const successfulExitCode ExitCode 0
returnOk successfulExitCode
