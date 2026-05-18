# expect.stdout:
# expect.exit: 42
project ErrorWithDistinctExit
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError SimulatedFailure CSignedInt32

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Use makeError + returnError to exit with payload value 42, demonstrating that the errorCase payload propagates to the process exit code."
invariant main "Exit code comes from the makeError integer payload."
label startMain
const exitPayload CSignedInt32 42
const branchTriggerOne CSignedInt64 1
const onePivot CSignedInt64 1
call alwaysTrueCall math.equalI64
arg alwaysTrueCall left branchTriggerOne
arg alwaysTrueCall right onePivot
run alwaysTrueCall
bind alwaysTrue Bool alwaysTrueCall
branchIf alwaysTrue raiseFailure
const successfulExitCode ExitCode 0
returnOk successfulExitCode
label raiseFailure
makeError simulatedFailure MainError.SimulatedFailure exitPayload
returnError simulatedFailure
