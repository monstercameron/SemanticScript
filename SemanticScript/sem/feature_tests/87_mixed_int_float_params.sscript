# expect.stdout: 6.500000\n
# expect.exit: 0
project MixedIntFloatParams
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation scaleByInt
input scaleByInt baseValue CFloat64
input scaleByInt multiplier CSignedInt64
output scaleByInt Result CFloat64 Void
memory scaleByInt heap no
async scaleByInt no
purpose scaleByInt "Convert the i64 multiplier to a CFloat64 and multiply baseValue by it. Exercises a user op whose first param is float, second is int, and which mixes math.intToFloat with math.multiplyF64."
invariant scaleByInt "Returns baseValue * (CFloat64) multiplier."
label startScaleByInt
call multiplierAsFloatCall math.intToFloat
arg multiplierAsFloatCall value multiplier
run multiplierAsFloatCall
bind multiplierAsFloat CFloat64 multiplierAsFloatCall
call productCall math.multiplyF64
arg productCall left baseValue
arg productCall right multiplierAsFloat
run productCall
bind scaledResult CFloat64 productCall
returnOk scaledResult

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "scaleByInt(3.25, 2) == 6.5. Mixed-typed user-op signature."
invariant main "Output is 6.500000."
label startMain
const baseValue CFloat64 3.25
const multiplierValue CSignedInt64 2
call scaleCall scaleByInt
arg scaleCall baseValue baseValue
arg scaleCall multiplier multiplierValue
run scaleCall
bindOk scaledOutcome CFloat64 scaleCall
call writeCall console.writeFloatLine
arg writeCall console console
arg writeCall value scaledOutcome
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
