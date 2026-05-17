# expect.stdout: 111\n
# expect.exit: 0
project F64LeGeNe
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
purpose main "Exercise math.lessThanOrEqualF64, math.greaterThanOrEqualF64, and math.notEqualF64. Compose three booleans into a 3-digit binary-as-int: 1.0 <= 2.0 (true), 3.0 >= 2.0 (true), 1.0 != 2.0 (true)."
invariant main "Each comparison contributes one decimal digit (100, 10, 1) when true."
label startMain
const oneFloat CFloat64 1.0
const twoFloat CFloat64 2.0
const threeFloat CFloat64 3.0
const differentFloat CFloat64 2.0
call leCheckCall math.lessThanOrEqualF64
arg leCheckCall left oneFloat
arg leCheckCall right twoFloat
run leCheckCall
bind leResult Bool leCheckCall
call geCheckCall math.greaterThanOrEqualF64
arg geCheckCall left threeFloat
arg geCheckCall right twoFloat
run geCheckCall
bind geResult Bool geCheckCall
call neCheckCall math.notEqualF64
arg neCheckCall left oneFloat
arg neCheckCall right differentFloat
run neCheckCall
bind neResult Bool neCheckCall
var hundredsDigit I64 0
branchIf leResult addHundreds
branch maybeTens
label addHundreds
const oneHundred I64 100
set hundredsDigit oneHundred
branch maybeTens
label maybeTens
var tensDigit I64 0
branchIf geResult addTens
branch maybeOnes
label addTens
const ten I64 10
set tensDigit ten
branch maybeOnes
label maybeOnes
var onesDigit I64 0
branchIf neResult addOnes
branch composeTotal
label addOnes
const oneUnit I64 1
set onesDigit oneUnit
branch composeTotal
label composeTotal
call sumHTCall math.addI64
arg sumHTCall left hundredsDigit
arg sumHTCall right tensDigit
run sumHTCall
bind partialHT I64 sumHTCall
call sumAllCall math.addI64
arg sumAllCall left partialHT
arg sumAllCall right onesDigit
run sumAllCall
bind composedTotal I64 sumAllCall
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value composedTotal
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
