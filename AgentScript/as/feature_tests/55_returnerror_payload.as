# expect.stdout:
# expect.exit: 42
project ReturnErrorPayload
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError CustomCode CSignedInt32
operation main
input main console Console
output main Result ExitCode MainError
memory main heap no
async main no
purpose main "returnError should propagate the makeError payload value as exit code."
invariant main "Exit code reflects the actual payload, not a hardcoded 1."
label startMain
const oneCount I64 1
const oneCompare I64 1
var x I64 oneCount
call eqCall math.equalI64
arg eqCall left x
arg eqCall right oneCompare
run eqCall
bind alwaysTrue Bool eqCall
branchIf alwaysTrue errorLeg
branch successLeg
label errorLeg
const customExitCode CSignedInt32 42
makeError customFailure MainError.CustomCode customExitCode
returnError customFailure
label successLeg
const successfulExitCode ExitCode 0
returnOk successfulExitCode
