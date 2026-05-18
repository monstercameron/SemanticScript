# expect.stdout: 3\n
# expect.exit: 0
# expect.xfail: feature_coverage.py runs through bootstrap_general.as which does not yet wrap `run CALL` in a retry loop. Direct ascc.py compilation is correct: the policy allows 3 attempts; the helper always returns a negative value; each attempt increments shared state; after exhaustion, shared state holds 3. `python compiler/ascc.py THIS_FILE --emit-exe /tmp/x.exe && /tmp/x.exe` prints `3`. Verifies retry loop runs exactly retryMaxAttempts times when call always fails.
project UseRetryExhaustionCounts
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32
const oneStep I64 1
const zeroInitial I64 0
const negativeOneAlwaysFails I64 -1
sharedState process mutable totalAttemptsObserved I64 zeroInitial
retryPolicy threeAttemptOnlyPolicy
retryMaxAttempts threeAttemptOnlyPolicy 3
operation alwaysFailWithAttemptCount
input alwaysFailWithAttemptCount trigger I64
output alwaysFailWithAttemptCount I64
call incrementAttemptsCall math.addI64
arg incrementAttemptsCall left totalAttemptsObserved
arg incrementAttemptsCall right oneStep
run incrementAttemptsCall
bind nextAttempts I64 incrementAttemptsCall
set sharedState totalAttemptsObserved nextAttempts
returnValue negativeOneAlwaysFails
operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Retry policy allows 3 attempts; helper always fails; verify exactly 3 attempts ran by reading attempt counter from shared state."
invariant main "After retry exhaustion, totalAttemptsObserved must equal retryMaxAttempts (3)."
label startMain
useRetry alwaysFailingCall threeAttemptOnlyPolicy
call alwaysFailingCall alwaysFailWithAttemptCount
arg alwaysFailingCall trigger zeroInitial
run alwaysFailingCall
bind finalAttemptResult I64 alwaysFailingCall
call writeCountCall console.writeIntegerLine
arg writeCountCall console console
arg writeCountCall value totalAttemptsObserved
run writeCountCall
ignoreOk writeCountCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
