# expect.stdout: taken\n
# expect.exit: 0
project BranchIfTaken
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
purpose main "branchIf with TRUE condition takes the labeled branch."
invariant main "Prints 'taken' when condition holds."
label startMain
const fiveInitial I64 5
const fiveCompare I64 5
var leftOp I64 fiveInitial
call eqCall math.equalI64
arg eqCall left leftOp
arg eqCall right fiveCompare
run eqCall
bind isEqual Bool eqCall
branchIf isEqual takenLabel
branch notTakenLabel
label takenLabel
const takenText CNullTerminatedByteString "taken"
call writeTakenCall console.writeLine
arg writeTakenCall console console
arg writeTakenCall text takenText
run writeTakenCall
ignoreOk writeTakenCall Void
branch endLabel
label notTakenLabel
const notTakenText CNullTerminatedByteString "not-taken"
call writeNotTakenCall console.writeLine
arg writeNotTakenCall console console
arg writeNotTakenCall text notTakenText
run writeNotTakenCall
ignoreOk writeNotTakenCall Void
branch endLabel
label endLabel
const successfulExitCode ExitCode 0
returnOk successfulExitCode
