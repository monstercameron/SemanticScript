# expect.stdout: 120\n
# expect.exit: 0
project RecursionFactorial
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation factorialOf
input factorialOf n CSignedInt64
output factorialOf Result CSignedInt64 Void
memory factorialOf heap no
async factorialOf no
purpose factorialOf "Recursive factorial: 1 if n <= 1, else n * factorialOf(n-1)."
invariant factorialOf "Standard recursion base case at 1."
label startFactorialOf
const oneLit I64 1
call atBaseCall math.lessThanOrEqualI64
arg atBaseCall left n
arg atBaseCall right oneLit
run atBaseCall
bind atBase Bool atBaseCall
branchIf atBase baseCase
branch recursiveCase
label baseCase
returnOk oneLit
label recursiveCase
call decCall math.subtractI64
arg decCall left n
arg decCall right oneLit
run decCall
bind decremented I64 decCall
call recCall factorialOf
arg recCall n decremented
run recCall
bindOk recResult I64 recCall
call mulCall math.multiplyI64
arg mulCall left n
arg mulCall right recResult
run mulCall
bind multiplied I64 mulCall
returnOk multiplied

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Compute factorialOf(5) = 120 via recursion."
invariant main "Outputs 120."
label startMain
const fiveInitial I64 5
var input I64 fiveInitial
call factCall factorialOf
arg factCall n input
run factCall
bindOk factResult I64 factCall
var outputVar I64 fiveInitial
set outputVar factResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value outputVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
