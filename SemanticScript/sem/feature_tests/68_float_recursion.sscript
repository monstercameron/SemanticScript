# expect.stdout: 8.000000\n
# expect.exit: 0
project FloatRecursion
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation accumulateFloatDoubled
input accumulateFloatDoubled value CFloat64
input accumulateFloatDoubled remainingSteps CSignedInt64
output accumulateFloatDoubled Result CFloat64 Void
memory accumulateFloatDoubled heap no
async accumulateFloatDoubled no
purpose accumulateFloatDoubled "Recursive: when remainingSteps == 0 return value; otherwise return accumulateFloatDoubled(value * 2.0, remainingSteps - 1). Exercises recursion with CFloat64 return."
invariant accumulateFloatDoubled "Doubles value `remainingSteps` times."
label startAccumulateFloatDoubled
const zeroSteps CSignedInt64 0
call doneCheckCall math.equalI64
arg doneCheckCall left remainingSteps
arg doneCheckCall right zeroSteps
run doneCheckCall
bind isDone Bool doneCheckCall
branchIf isDone returnValueAsIs
const twoFactor CFloat64 2.0
call doubleValueCall math.multiplyF64
arg doubleValueCall left value
arg doubleValueCall right twoFactor
run doubleValueCall
bind doubledValue CFloat64 doubleValueCall
const oneStep CSignedInt64 1
call subtractStepCall math.subtractI64
arg subtractStepCall left remainingSteps
arg subtractStepCall right oneStep
run subtractStepCall
bind nextRemaining CSignedInt64 subtractStepCall
call recurseCall accumulateFloatDoubled
arg recurseCall value doubledValue
arg recurseCall remainingSteps nextRemaining
run recurseCall
bindOk recursiveResult CFloat64 recurseCall
returnOk recursiveResult
label returnValueAsIs
returnOk value

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Compute 1.0 doubled 3 times == 8.0 via recursion."
invariant main "Exercises CFloat64 recursion plus writeFloatLine."
label startMain
const startingValue CFloat64 1.0
const stepCount CSignedInt64 3
call runIterationCall accumulateFloatDoubled
arg runIterationCall value startingValue
arg runIterationCall remainingSteps stepCount
run runIterationCall
bindOk finalValue CFloat64 runIterationCall
call writeCall console.writeFloatLine
arg writeCall console console
arg writeCall value finalValue
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
