# expect.stdout: 6\n
# expect.exit: 0
project TwoParamGcd
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation gcdOf
input gcdOf a CSignedInt64
input gcdOf b CSignedInt64
output gcdOf Result CSignedInt64 Void
memory gcdOf heap no
async gcdOf no
purpose gcdOf "Euclidean GCD: if b == 0, a; else gcdOf(b, a mod b)."
invariant gcdOf "Terminates when b reaches zero."
label startGcdOf
const zeroLit I64 0
call atBaseCall math.equalI64
arg atBaseCall left b
arg atBaseCall right zeroLit
run atBaseCall
bind atBase Bool atBaseCall
branchIf atBase gcdBase
branch gcdRecurse
label gcdBase
returnOk a
label gcdRecurse
call modCall math.moduloI64
arg modCall left a
arg modCall right b
run modCall
bind remainder I64 modCall
call recCall gcdOf
arg recCall a b
arg recCall b remainder
run recCall
bindOk recResult I64 recCall
returnOk recResult

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "gcdOf(48, 18) = 6."
invariant main "Two-param recursion."
label startMain
const fortyEightInitial I64 48
const eighteenInitial I64 18
var aValue I64 fortyEightInitial
var bValue I64 eighteenInitial
call gcdCall gcdOf
arg gcdCall a aValue
arg gcdCall b bValue
run gcdCall
bindOk gcdResult I64 gcdCall
var outputVar I64 fortyEightInitial
set outputVar gcdResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value outputVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
