# expect.stdout: 24\n
# expect.exit: 0
project ThreeParamUserOp
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation tripleProduct
input tripleProduct a CSignedInt64
input tripleProduct b CSignedInt64
input tripleProduct c CSignedInt64
output tripleProduct Result CSignedInt64 Void
memory tripleProduct heap no
async tripleProduct no
purpose tripleProduct "Return a * b * c."
invariant tripleProduct "Three-param multiply."
label startTripleProduct
call firstMulCall math.multiplyI64
arg firstMulCall left a
arg firstMulCall right b
run firstMulCall
bind firstProduct I64 firstMulCall
call secondMulCall math.multiplyI64
arg secondMulCall left firstProduct
arg secondMulCall right c
run secondMulCall
bind secondProduct I64 secondMulCall
returnOk secondProduct

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "tripleProduct(2,3,4) = 24."
invariant main "Outputs 24."
label startMain
const twoInitial I64 2
const threeInitial I64 3
const fourInitial I64 4
var aValue I64 twoInitial
var bValue I64 threeInitial
var cValue I64 fourInitial
call computeCall tripleProduct
arg computeCall a aValue
arg computeCall b bValue
arg computeCall c cValue
run computeCall
bindOk computeResult I64 computeCall
var outputVar I64 twoInitial
set outputVar computeResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value outputVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
