project HelloViaHelper
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError

operation writeStandardOutputLine
# group writeStandardOutputLineHelperBody
input writeStandardOutputLine text String
output writeStandardOutputLine Result Void ConsoleWriteError
effect writeStandardOutputLine write console.stdout
memory writeStandardOutputLine heap no
memory writeStandardOutputLine stack max 1KiB
async writeStandardOutputLine no

purpose writeStandardOutputLine "Emit one newline-terminated text line to standard output via console.writeLine and surface a typed ConsoleWriteError on driver failure"
invariant writeStandardOutputLine "The single console.writeLine call is the only path that can produce stdout from this operation"
guarantee writeStandardOutputLine "On success the entire text plus a single newline byte is written exactly once"

label startWriteStandardOutputLine

call writeStandardOutputLineConsoleWriteCall console.writeLine
arg writeStandardOutputLineConsoleWriteCall console console
arg writeStandardOutputLineConsoleWriteCall text text
run writeStandardOutputLineConsoleWriteCall
ignoreOk writeStandardOutputLineConsoleWriteCall Void
bindError writeStandardOutputLineConsoleWriteError ConsoleWriteError writeStandardOutputLineConsoleWriteCall
branchIfError writeStandardOutputLineConsoleWriteCall writeStandardOutputLineConsoleWriteFailed

const writeStandardOutputLineSuccessSentinel ExitCode 0
returnOk writeStandardOutputLineSuccessSentinel

label writeStandardOutputLineConsoleWriteFailed
returnError writeStandardOutputLineConsoleWriteError
# endGroup writeStandardOutputLineHelperBody

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
memory main stack max 4KiB
async main no

purpose main "Smoke-test the writeStandardOutputLine helper by emitting the canonical greeting through it"
invariant main "Exactly one helper call runs; its success leg returns ExitCode.Ok and its failure leg surfaces MainError.ConsoleWriteFailed"

label startMain

const helloGreetingText String "Hello, World!"

call writeHelloGreetingLineCall writeStandardOutputLine
arg writeHelloGreetingLineCall text helloGreetingText
run writeHelloGreetingLineCall
ignoreOk writeHelloGreetingLineCall Void
bindError writeHelloGreetingLineError ConsoleWriteError writeHelloGreetingLineCall
branchIfError writeHelloGreetingLineCall helloGreetingLineWriteFailed

const successfulExitCode ExitCode 0
returnOk successfulExitCode

label helloGreetingLineWriteFailed
makeError helloGreetingLineWriteFailure MainError.ConsoleWriteFailed writeHelloGreetingLineError
returnError helloGreetingLineWriteFailure
