# expect.stdout: -3.500000\n
# expect.exit: 0
project NegativeFloatConstInOp
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation flipSign
input flipSign value CFloat64
output flipSign Result CFloat64 Void
memory flipSign heap no
async flipSign no
purpose flipSign "Multiply a CFloat64 by -1.0. Exercises a negative float const passed as an arg in a user-op body."
invariant flipSign "Returns -value."
label startFlipSign
const negativeOne CFloat64 -1.0
call multCall math.multiplyF64
arg multCall left value
arg multCall right negativeOne
run multCall
bind flipped CFloat64 multCall
returnOk flipped

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "flipSign(3.5) == -3.5. Exercises negative float const + float user op + writeFloatLine."
invariant main "Output is -3.500000."
label startMain
const startValue CFloat64 3.5
call flipCall flipSign
arg flipCall value startValue
run flipCall
bindOk flippedValue CFloat64 flipCall
call writeCall console.writeFloatLine
arg writeCall console console
arg writeCall value flippedValue
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
