# expect.stdout: ping\nping\nping\n
# expect.exit: 0
project RepeatedStringPrint
target console
runtime AgentRuntime 0.1
mode capturedOutputReplay
entry console main
error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError
operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Same string const referenced three times in separate calls; verifies per-call (not per-const) puts emission."
invariant main "Output line count equals call count, not unique-const count."
label startMain
const pingText CNullTerminatedByteString "ping"
call writeOneCall console.writeLine
arg writeOneCall console console
arg writeOneCall text pingText
run writeOneCall
ignoreOk writeOneCall Void
call writeTwoCall console.writeLine
arg writeTwoCall console console
arg writeTwoCall text pingText
run writeTwoCall
ignoreOk writeTwoCall Void
call writeThreeCall console.writeLine
arg writeThreeCall console console
arg writeThreeCall text pingText
run writeThreeCall
ignoreOk writeThreeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
