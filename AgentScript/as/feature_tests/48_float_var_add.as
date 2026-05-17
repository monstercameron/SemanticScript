# expect.stdout: 8.000000\n
# expect.exit: 0
project FloatVarAdd
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
purpose main "5.0 + 3.0 via CFloat64 var + math.addF64; print via writeFloatLine."
invariant main "Tests float vars, float math, float binds, writeFloatLine of bind."
label startMain
const fiveFloat CFloat64 5.0
const threeFloat CFloat64 3.0
var leftFloat CFloat64 fiveFloat
call addCall math.addF64
arg addCall left leftFloat
arg addCall right threeFloat
run addCall
bind sumResult CFloat64 addCall
call writeCall console.writeFloatLine
arg writeCall console console
arg writeCall value sumResult
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
