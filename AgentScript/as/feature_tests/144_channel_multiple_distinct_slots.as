# expect.stdout: 11\n22\n
# expect.exit: 0
# expect.xfail: feature_coverage.py runs through bootstrap_general.as which does not yet alloca per-channel slots for send/receive. Direct ascc.py compilation is correct: each channel has its own alloca, so values don't bleed across channels. `python compiler/ascc.py THIS_FILE --emit-exe /tmp/x.exe && /tmp/x.exe` prints `11` then `22`.
project ChannelMultipleDistinctSlots
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
purpose main "Two distinct channels do not share storage."
invariant main "channelAlpha carries 11, channelBeta carries 22; reads of each see their own value."
label startMain
const elevenValue I64 11
const twentyTwoValue I64 22
send channelAlpha elevenValue
send channelBeta twentyTwoValue
receive receivedFromAlpha I64 channelAlpha
receive receivedFromBeta I64 channelBeta
call writeFirstCall console.writeIntegerLine
arg writeFirstCall console console
arg writeFirstCall value receivedFromAlpha
run writeFirstCall
ignoreOk writeFirstCall Void
call writeSecondCall console.writeIntegerLine
arg writeSecondCall console console
arg writeSecondCall value receivedFromBeta
run writeSecondCall
ignoreOk writeSecondCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
