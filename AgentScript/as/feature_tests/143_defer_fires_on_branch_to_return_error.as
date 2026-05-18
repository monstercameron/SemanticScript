# expect.stdout: cleanupBeforeError\n
# expect.exit: 1
# expect.xfail: feature_coverage.py runs through bootstrap_general.as which does not yet emit defer cleanup before returnError. Direct ascc.py compilation is correct: branchIfError jumps to the failure label, the defer fires before returnError, output is `cleanupBeforeError`. `python compiler/ascc.py THIS_FILE --emit-exe /tmp/x.exe && /tmp/x.exe` prints `cleanupBeforeError` and exits 1.
project DeferFiresOnBranchToReturnError
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError ForcedFailureForTest CSignedInt32
operation printCleanupBeforeError
input printCleanupBeforeError console Console
output printCleanupBeforeError I32
const cleanupBeforeErrorMessage CNullTerminatedByteString "cleanupBeforeError"
call writeCleanupCall console.writeLine
arg writeCleanupCall console console
arg writeCleanupCall text cleanupBeforeErrorMessage
run writeCleanupCall
ignoreOk writeCleanupCall Void
const cleanupExitValue I32 0
returnValue cleanupExitValue
operation alwaysReturnsNegative
input alwaysReturnsNegative trigger I64
output alwaysReturnsNegative Result I64 MainError
makeError alwaysFailValue MainError.ForcedFailureForTest
returnError alwaysFailValue
operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "branchIfError jumps to failure label; the defer cleanup fires before returnError."
invariant main "Output is exactly one line of 'cleanupBeforeError'; exit code is the variant index (1)."
label startMain
const zeroTrigger I64 0
defer earlyReturnCleanup printCleanupBeforeError console
call failingHelperCall alwaysReturnsNegative
arg failingHelperCall trigger zeroTrigger
run failingHelperCall
bindOk failingHelperOk I64 failingHelperCall
bindError failingHelperErrorVal I64 failingHelperCall
branchIfError failingHelperCall handleEarlyFailure
const successfulExitCode ExitCode 0
returnOk successfulExitCode
label handleEarlyFailure
returnError failingHelperErrorVal
