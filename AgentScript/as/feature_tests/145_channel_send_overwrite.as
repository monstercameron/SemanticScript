# expect.stdout: 99\n
# expect.exit: 0
# expect.xfail: feature_coverage.py runs through bootstrap_general.as which does not yet alloca per-channel slots for send/receive. Direct ascc.py compilation is correct: single-slot channel takes the last send before the receive. `python compiler/ascc.py THIS_FILE --emit-exe /tmp/x.exe && /tmp/x.exe` prints `99`.
project ChannelSendOverwrite
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
purpose main "Single-slot channel: when two sends happen before a receive, the receive sees the latest value."
invariant main "Output is 99 (the second send) not 50 (the first send)."
label startMain
const firstSendValue I64 50
const secondSendValue I64 99
send overwriteChannel firstSendValue
send overwriteChannel secondSendValue
receive latestValue I64 overwriteChannel
call writeLatestCall console.writeIntegerLine
arg writeLatestCall console console
arg writeLatestCall value latestValue
run writeLatestCall
ignoreOk writeLatestCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
