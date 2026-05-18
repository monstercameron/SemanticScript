# expect.stdout: 11.000000\n
# expect.exit: 0
project FloatUserOp
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation doubleFloat
input doubleFloat x CFloat64
output doubleFloat Result CFloat64 Void
memory doubleFloat heap no
async doubleFloat no
purpose doubleFloat "Return 2x as CFloat64."
invariant doubleFloat "Float-typed user op."
label startDoubleFloat
const twoFloatLit CFloat64 2.0
call mulCall math.multiplyF64
arg mulCall left x
arg mulCall right twoFloatLit
run mulCall
bind doubled CFloat64 mulCall
returnOk doubled

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "doubleFloat(5.5) = 11.0."
invariant main "Tests float user-op signature."
label startMain
const fiveHalfFloat CFloat64 5.5
var x CFloat64 fiveHalfFloat
call dblCall doubleFloat
arg dblCall x x
run dblCall
bindOk dblResult CFloat64 dblCall
call writeCall console.writeFloatLine
arg writeCall console console
arg writeCall value dblResult
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
