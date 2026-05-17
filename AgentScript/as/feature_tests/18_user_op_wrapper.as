# expect.stdout: hello via helper\n
# expect.exit: 0
project UserOpWrapper
target console
runtime AgentRuntime 0.1
mode capturedOutputReplay
entry console main
error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError

operation writeStandardOutputLine
input writeStandardOutputLine text String
output writeStandardOutputLine Result Void ConsoleWriteError
effect writeStandardOutputLine write console.stdout
memory writeStandardOutputLine heap no
async writeStandardOutputLine no
purpose writeStandardOutputLine "Helper that delegates to console.writeLine."
invariant writeStandardOutputLine "Passes through the text argument."
label startWriteStandardOutputLine
call innerWriteCall console.writeLine
arg innerWriteCall console console
arg innerWriteCall text text
run innerWriteCall
ignoreOk innerWriteCall Void
bindError innerWriteError ConsoleWriteError innerWriteCall
branchIfError innerWriteCall innerWriteFailed
const innerSuccessfulExitCode ExitCode 0
returnOk innerSuccessfulExitCode
label innerWriteFailed
returnError innerWriteError

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Call user-defined helper; expect string emitted exactly once."
invariant main "Output is the helper's argument."
label startMain
const helloText CNullTerminatedByteString "hello via helper"
call writeMainCall writeStandardOutputLine
arg writeMainCall text helloText
run writeMainCall
ignoreOk writeMainCall Void
bindError writeMainError ConsoleWriteError writeMainCall
branchIfError writeMainCall mainWriteFailed
const successfulExitCode ExitCode 0
returnOk successfulExitCode
label mainWriteFailed
makeError consoleWriteFailure MainError.ConsoleWriteFailed writeMainError
returnError consoleWriteFailure
