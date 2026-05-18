# expect.stdout: 7.500000\n
# expect.exit: 0
project TypeAliasFloat
target console
runtime AgentRuntime 0.1
type Distance CFloat64
type DistanceDelta CFloat64
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32
operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Type alias to CFloat64 should be treated as double."
invariant main "Aliased float types print correctly."
label startMain
const fiveFloat Distance 5.0
const twoHalfFloat DistanceDelta 2.5
var current Distance fiveFloat
call addCall math.addF64
arg addCall left current
arg addCall right twoHalfFloat
run addCall
bind sumResult Distance addCall
call writeCall console.writeFloatLine
arg writeCall console console
arg writeCall value sumResult
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
