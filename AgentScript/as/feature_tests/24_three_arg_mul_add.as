# expect.stdout: 23\n
# expect.exit: 0
project ThreeArgMulAdd
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
purpose main "Compute (4 * 5) + 3 = 23 via two sequential ops."
invariant main "First mul, then add, then print."
label startMain
const fourLit I64 4
const fiveLit I64 5
const threeLit I64 3
var leftMul I64 fourLit
call mulCall math.multiplyI64
arg mulCall left leftMul
arg mulCall right fiveLit
run mulCall
bind mulResult I64 mulCall
call addCall math.addI64
arg addCall left mulResult
arg addCall right threeLit
run addCall
bind addResult I64 addCall
var resultVar I64 fourLit
set resultVar addResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value resultVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
