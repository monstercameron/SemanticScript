# expect.stdout: 9.000000\n
# expect.exit: 0
project MultiLevelFloatAlias
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

# Multi-level type alias chain. Distance is an alias of Metric, which
# is an alias of CFloat64. The compiler must resolve through both
# levels to detect that Distance values should be emitted as `double`.
type Metric CFloat64
type Distance Metric
type Velocity Distance

operation tripleVelocity
input tripleVelocity speed Velocity
output tripleVelocity Result Velocity Void
memory tripleVelocity heap no
async tripleVelocity no
purpose tripleVelocity "Multiply a Velocity (== Distance == Metric == CFloat64) by 3.0."
invariant tripleVelocity "Verifies the alias chain resolves to double for both the param and the result."
label startTripleVelocity
const threeFactor Velocity 3.0
call multCall math.multiplyF64
arg multCall left speed
arg multCall right threeFactor
run multCall
bind tripled Velocity multCall
returnOk tripled

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "tripleVelocity(3.0) == 9.0. Exercises 3-level type-alias resolution to CFloat64."
invariant main "Output is 9.000000."
label startMain
const startSpeed Velocity 3.0
call computeCall tripleVelocity
arg computeCall speed startSpeed
run computeCall
bindOk finalSpeed Velocity computeCall
call writeCall console.writeFloatLine
arg writeCall console console
arg writeCall value finalSpeed
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
