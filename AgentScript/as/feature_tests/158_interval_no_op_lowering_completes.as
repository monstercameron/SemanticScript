# expect.stdout: completedAfterInterval\n
# expect.exit: 0
project IntervalNoOpCompletes
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
purpose main "interval + startInterval + awaitIntervalTick must not infinite-loop or crash under single-thread no-op lowering."
invariant main "Code after awaitIntervalTick runs and prints the completion message."
label startMain
interval heartbeatTicker maxRate 60
startInterval heartbeatTicker
awaitIntervalTick heartbeatTicker
awaitIntervalTick heartbeatTicker
const completionMessage CNullTerminatedByteString "completedAfterInterval"
call writeCompletionCall console.writeLine
arg writeCompletionCall console console
arg writeCompletionCall text completionMessage
run writeCompletionCall
ignoreOk writeCompletionCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
