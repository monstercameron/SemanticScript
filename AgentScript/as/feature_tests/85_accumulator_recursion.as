# expect.stdout: 55\n
# expect.exit: 0
project AccumulatorRecursion
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation sumTo
input sumTo accumulator CSignedInt64
input sumTo remaining CSignedInt64
output sumTo Result CSignedInt64 Void
memory sumTo heap no
async sumTo no
purpose sumTo "Tail-recursive accumulator: when `remaining` reaches 0, return `accumulator`; otherwise sumTo(accumulator + remaining, remaining - 1)."
invariant sumTo "Computes sum(1..n) in O(n) recursion depth."
label startSumTo
const zeroBase CSignedInt64 0
const oneStep CSignedInt64 1
call doneCheckCall math.equalI64
arg doneCheckCall left remaining
arg doneCheckCall right zeroBase
run doneCheckCall
bind isDone Bool doneCheckCall
branchIf isDone baseCaseSumTo
call newAccumCall math.addI64
arg newAccumCall left accumulator
arg newAccumCall right remaining
run newAccumCall
bind newAccumulator CSignedInt64 newAccumCall
call decRemainingCall math.subtractI64
arg decRemainingCall left remaining
arg decRemainingCall right oneStep
run decRemainingCall
bind nextRemaining CSignedInt64 decRemainingCall
call recurseCall sumTo
arg recurseCall accumulator newAccumulator
arg recurseCall remaining nextRemaining
run recurseCall
bindOk recursiveResult CSignedInt64 recurseCall
returnOk recursiveResult
label baseCaseSumTo
returnOk accumulator

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "sumTo(0, 10) == 0+10+9+...+1 == 55."
invariant main "Verifies a 2-arg recursive accumulator can reach a base case 10 levels deep."
label startMain
const zeroAccum CSignedInt64 0
const tenInitial CSignedInt64 10
call computeCall sumTo
arg computeCall accumulator zeroAccum
arg computeCall remaining tenInitial
run computeCall
bindOk computedSum CSignedInt64 computeCall
var sumStorage I64 0
set sumStorage computedSum
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value sumStorage
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
