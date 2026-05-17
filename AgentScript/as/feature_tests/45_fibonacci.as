# expect.stdout: 55\n
# expect.exit: 0
project Fibonacci
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation fibOf
input fibOf n CSignedInt64
output fibOf Result CSignedInt64 Void
memory fibOf heap no
async fibOf no
purpose fibOf "Naive recursive Fibonacci."
invariant fibOf "fib(0)=0, fib(1)=1, fib(n)=fib(n-1)+fib(n-2)."
label startFibOf
const zeroLit I64 0
const oneLit I64 1
const twoLit I64 2
call atBaseCall math.lessThanI64
arg atBaseCall left n
arg atBaseCall right twoLit
run atBaseCall
bind atBase Bool atBaseCall
branchIf atBase fibBase
branch fibRecurse
label fibBase
returnOk n
label fibRecurse
call decOneCall math.subtractI64
arg decOneCall left n
arg decOneCall right oneLit
run decOneCall
bind nMinusOne I64 decOneCall
call recAOneCall fibOf
arg recAOneCall n nMinusOne
run recAOneCall
bindOk fibAOne I64 recAOneCall
call decTwoCall math.subtractI64
arg decTwoCall left n
arg decTwoCall right twoLit
run decTwoCall
bind nMinusTwo I64 decTwoCall
call recBTwoCall fibOf
arg recBTwoCall n nMinusTwo
run recBTwoCall
bindOk fibBTwo I64 recBTwoCall
call sumCall math.addI64
arg sumCall left fibAOne
arg sumCall right fibBTwo
run sumCall
bind fibTotal I64 sumCall
returnOk fibTotal

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Compute fib(10) = 55."
invariant main "Two recursive calls per frame."
label startMain
const tenInitial I64 10
var input I64 tenInitial
call fibCall fibOf
arg fibCall n input
run fibCall
bindOk fibResult I64 fibCall
var outputVar I64 tenInitial
set outputVar fibResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value outputVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
