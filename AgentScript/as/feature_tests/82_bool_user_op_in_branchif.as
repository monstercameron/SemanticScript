# expect.stdout: 7\n
# expect.exit: 0
project BoolUserOpInBranchIf
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation isOdd
input isOdd n CSignedInt64
output isOdd Result Bool Void
memory isOdd heap no
async isOdd no
purpose isOdd "Return true when n is odd. Exercises a Bool-returning user op that is binarized via `bind X Bool callRes` then used in `branchIf X` — the i64 → i1 trunc path."
invariant isOdd "Uses math.moduloI64 with 2 to test parity."
label startIsOdd
const twoModulus CSignedInt64 2
const zeroRemainder CSignedInt64 0
call modCall math.moduloI64
arg modCall left n
arg modCall right twoModulus
run modCall
bind remainder CSignedInt64 modCall
call eqCall math.equalI64
arg eqCall left remainder
arg eqCall right zeroRemainder
run eqCall
bind isZero Bool eqCall
branchIf isZero reportEvenCase
const trueValue CSignedInt64 1
var oddResult Bool trueValue
returnOk oddResult
label reportEvenCase
const falseValue CSignedInt64 0
var evenResult Bool falseValue
returnOk evenResult

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Count odd numbers in 1..6 via isOdd; expect 3, then also exercise an even/odd branch directly. Final printed value is total odd count + first-odd-seen."
invariant main "isOdd(1) and isOdd(2) yield Bool values used by branchIf."
label startMain
const oneTarget CSignedInt64 1
const twoTarget CSignedInt64 2
call oneOddCall isOdd
arg oneOddCall n oneTarget
run oneOddCall
bindOk oneIsOdd Bool oneOddCall
call twoOddCall isOdd
arg twoOddCall n twoTarget
run twoOddCall
bindOk twoIsOdd Bool twoOddCall
var totalScore I64 0
const fiveBoost I64 5
const twoBoost I64 2
branchIf oneIsOdd boostFromOne
branch maybeBoostTwo
label boostFromOne
set totalScore fiveBoost
branch maybeBoostTwo
label maybeBoostTwo
branchIf twoIsOdd boostFromTwo
branch printResult
label boostFromTwo
call wrongBoostCall math.addI64
arg wrongBoostCall left totalScore
arg wrongBoostCall right twoBoost
run wrongBoostCall
bind wrongScore I64 wrongBoostCall
set totalScore wrongScore
branch printResult
label printResult
call sumCall math.addI64
arg sumCall left totalScore
arg sumCall right twoBoost
run sumCall
bind finalScore I64 sumCall
var finalStorage I64 0
set finalStorage finalScore
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value finalStorage
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
