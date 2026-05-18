# expect.stdout: 1\n
# expect.exit: 0
project MutualRecursion
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation isEven
input isEven n CSignedInt64
output isEven Result CSignedInt64 Void
memory isEven heap no
async isEven no
purpose isEven "Mutually-recursive even test: 0 is even; n even iff isOdd(n-1)."
invariant isEven "Calls isOdd on decrement."
label startIsEven
const zeroLit I64 0
const oneLit I64 1
call atZeroCall math.equalI64
arg atZeroCall left n
arg atZeroCall right zeroLit
run atZeroCall
bind atZero Bool atZeroCall
branchIf atZero evenBase
branch evenRecurse
label evenBase
returnOk oneLit
label evenRecurse
call decCall math.subtractI64
arg decCall left n
arg decCall right oneLit
run decCall
bind decremented I64 decCall
call recCall isOdd
arg recCall n decremented
run recCall
bindOk recResult I64 recCall
returnOk recResult

operation isOdd
input isOdd n CSignedInt64
output isOdd Result CSignedInt64 Void
memory isOdd heap no
async isOdd no
purpose isOdd "Mutually-recursive odd test."
invariant isOdd "Calls isEven on decrement."
label startIsOdd
const zeroLit I64 0
const oneLit I64 1
call atZeroOddCall math.equalI64
arg atZeroOddCall left n
arg atZeroOddCall right zeroLit
run atZeroOddCall
bind atZeroOdd Bool atZeroOddCall
branchIf atZeroOdd oddBase
branch oddRecurse
label oddBase
returnOk zeroLit
label oddRecurse
call decCall math.subtractI64
arg decCall left n
arg decCall right oneLit
run decCall
bind decremented I64 decCall
call recCall isEven
arg recCall n decremented
run recCall
bindOk recResult I64 recCall
returnOk recResult

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "isEven(8) should be 1."
invariant main "8 is even."
label startMain
const eightInitial I64 8
var input I64 eightInitial
call evenCall isEven
arg evenCall n input
run evenCall
bindOk evenResult I64 evenCall
var outputVar I64 eightInitial
set outputVar evenResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value outputVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
