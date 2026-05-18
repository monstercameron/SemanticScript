# expect.stdout: between\n
# expect.exit: 0
project ChainedBranchIf
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
purpose main "Two-tier branching: x>0 AND x<10."
invariant main "5 falls into the between range."
label startMain
const fiveInitial I64 5
const zeroCompare I64 0
const tenCompare I64 10
var value I64 fiveInitial
call posCheckCall math.greaterThanI64
arg posCheckCall left value
arg posCheckCall right zeroCompare
run posCheckCall
bind isPositive Bool posCheckCall
branchIf isPositive checkUpperBound
branch outOfRangeLabel
label checkUpperBound
call upperCheckCall math.lessThanI64
arg upperCheckCall left value
arg upperCheckCall right tenCompare
run upperCheckCall
bind isUnderTen Bool upperCheckCall
branchIf isUnderTen betweenLabel
branch outOfRangeLabel
label betweenLabel
const betweenText CNullTerminatedByteString "between"
call writeBetweenCall console.writeLine
arg writeBetweenCall console console
arg writeBetweenCall text betweenText
run writeBetweenCall
ignoreOk writeBetweenCall Void
branch endLabel
label outOfRangeLabel
const oorText CNullTerminatedByteString "out-of-range"
call writeOorCall console.writeLine
arg writeOorCall console console
arg writeOorCall text oorText
run writeOorCall
ignoreOk writeOorCall Void
branch endLabel
label endLabel
const successfulExitCode ExitCode 0
returnOk successfulExitCode
