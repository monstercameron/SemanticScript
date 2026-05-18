# expect.stdout: 1\n
# expect.exit: 0
# expect.xfail: feature_coverage.py runs through bootstrap_general.as which does not yet wrap `run CALL` in a retry loop. Direct ascc.py compilation is correct: `retryMaxAttempts 1` means the call runs exactly once even when it fails. After the run, shared state holds 1 attempt. `python compiler/ascc.py THIS_FILE --emit-exe /tmp/x.exe && /tmp/x.exe` prints `1`.
project UseRetryMaxAttemptsBoundary
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32
const oneStep I64 1
const zeroInitial I64 0
const failureMarker I64 -7
sharedState process mutable singleAttemptCounter I64 zeroInitial
retryPolicy singleAttemptOnlyPolicy
retryMaxAttempts singleAttemptOnlyPolicy 1
operation singleAttemptFailingOperation
input singleAttemptFailingOperation trigger I64
output singleAttemptFailingOperation I64
call recordCall math.addI64
arg recordCall left singleAttemptCounter
arg recordCall right oneStep
run recordCall
bind nextCount I64 recordCall
set sharedState singleAttemptCounter nextCount
returnValue failureMarker
operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "retryMaxAttempts of 1 produces exactly one attempt — proves the loop honors the boundary even though the call always fails."
invariant main "Counter must equal 1 after the run, not 0 (didn't run) or 2+ (over-retried)."
label startMain
useRetry singleAttemptCall singleAttemptOnlyPolicy
call singleAttemptCall singleAttemptFailingOperation
arg singleAttemptCall trigger zeroInitial
run singleAttemptCall
bind boundedResult I64 singleAttemptCall
call writeBoundaryCall console.writeIntegerLine
arg writeBoundaryCall console console
arg writeBoundaryCall value singleAttemptCounter
run writeBoundaryCall
ignoreOk writeBoundaryCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
