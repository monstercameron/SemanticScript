# expect.stdout: -2.500000\n
# expect.exit: 0
project NegativeFloatLiteral
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
purpose main "Initialize a CFloat64 var directly from a negative literal (-2.5) and print it."
invariant main "Exercises the literal-init detection path that accepts the minus sign as first character."
label startMain
var negativeHalfPlusTwo CFloat64 -2.5
call writeCall console.writeFloatLine
arg writeCall console console
arg writeCall value negativeHalfPlusTwo
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
