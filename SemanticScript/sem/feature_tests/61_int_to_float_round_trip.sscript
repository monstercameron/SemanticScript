# expect.stdout: 42\n
# expect.exit: 0
project IntFloatRoundTrip
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32
operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Round-trip an int through math.intToFloat and math.floatToInt: 42 -> 42.0 -> 42."
invariant main "Exercises both conversion primitives."
label startMain
const fortyTwo I64 42
call toFloatCall math.intToFloat
arg toFloatCall value fortyTwo
run toFloatCall
bind asFloat CFloat64 toFloatCall
call backToIntCall math.floatToInt
arg backToIntCall value asFloat
run backToIntCall
bind asIntAgain I64 backToIntCall
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value asIntAgain
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
