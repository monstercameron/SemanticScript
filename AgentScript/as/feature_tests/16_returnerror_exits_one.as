# expect.stdout:
# expect.exit: 1
project ReturnErrorOne
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError IntentionalFailure CSignedInt32
operation main
input main console Console
output main Result ExitCode MainError
memory main heap no
async main no
purpose main "branchIf to a returnError leg; verifies exit code 1."
invariant main "Always takes the error path."
label startMain
const oneCount I64 1
const oneCompare I64 1
var leftOp I64 oneCount
call eqCall math.equalI64
arg eqCall left leftOp
arg eqCall right oneCompare
run eqCall
bind alwaysTrue Bool eqCall
branchIf alwaysTrue errorLeg
branch successLeg
label errorLeg
const intentionalFailureCode CSignedInt32 1
makeError intentionalFailure MainError.IntentionalFailure intentionalFailureCode
returnError intentionalFailure
label successLeg
const successfulExitCode ExitCode 0
returnOk successfulExitCode
