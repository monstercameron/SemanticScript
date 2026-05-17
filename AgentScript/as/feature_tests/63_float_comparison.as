# expect.stdout: less\n
# expect.exit: 0
project FloatComparisonTest
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation classifyFloat
input classifyFloat left CFloat64
input classifyFloat right CFloat64
output classifyFloat Result CSignedInt32 Void
memory classifyFloat heap no
async classifyFloat no
purpose classifyFloat "Returns -1 when left < right, 0 when equal, +1 when greater. Uses math.lessThanF64 / math.greaterThanF64."
invariant classifyFloat "Bool result is 0 or 1; map back to a sign by branching."
label startClassifyFloat
const ltResult CSignedInt32 -1
const gtResult CSignedInt32 1
const eqResult CSignedInt32 0
call lessCheckCall math.lessThanF64
arg lessCheckCall left left
arg lessCheckCall right right
run lessCheckCall
bind isLess Bool lessCheckCall
branchIf isLess emitLtResult
call greaterCheckCall math.greaterThanF64
arg greaterCheckCall left left
arg greaterCheckCall right right
run greaterCheckCall
bind isGreater Bool greaterCheckCall
branchIf isGreater emitGtResult
returnOk eqResult
label emitLtResult
returnOk ltResult
label emitGtResult
returnOk gtResult

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Compare 1.5 < 2.5 and print 'less' for negative classification, 'equal' for zero, 'more' for positive."
invariant main "Exercises math.lessThanF64 via classifyFloat user op."
label startMain
const oneAndHalf CFloat64 1.5
const twoAndHalf CFloat64 2.5
call classifyCall classifyFloat
arg classifyCall left oneAndHalf
arg classifyCall right twoAndHalf
run classifyCall
bindOk classification CSignedInt32 classifyCall
var classificationStorage I64 0
set classificationStorage classification
const zeroValue I64 0
call isNegativeCall math.lessThanI64
arg isNegativeCall left classificationStorage
arg isNegativeCall right zeroValue
run isNegativeCall
bind isNegative Bool isNegativeCall
branchIf isNegative printLess
const greetingMore CNullTerminatedByteString "more\n"
call writeMoreCall console.writeLine
arg writeMoreCall console console
arg writeMoreCall text greetingMore
run writeMoreCall
ignoreOk writeMoreCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
label printLess
const greetingLess CNullTerminatedByteString "less"
call writeLessCall console.writeLine
arg writeLessCall console console
arg writeLessCall text greetingLess
run writeLessCall
ignoreOk writeLessCall Void
const lessExitCode ExitCode 0
returnOk lessExitCode
