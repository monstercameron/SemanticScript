# webserver_console_refined.as
#
# Migration of as/webserver_console.as to refined syntax. Same behavior —
# print the listen-banner that matches the sibling JavaScript baseline.

section program.webserverConsoleRefined

project WebserverConsoleRefined
target console
runtime AgentRuntime 0.1
mode capturedOutputReplay
entry console main

section program.webserverConsoleRefined.types

type ConsoleWriteErrorCode I32

section program.webserverConsoleRefined.errors

error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError

section program.webserverConsoleRefined.literals

domainLiteral webserverListenBannerText String "Server listening at http://127.0.0.1:3149"
storage module immutable successfulExitCode ExitCode 0
storage module immutable writeStandardOutputLineSuccessSentinel ExitCode 0

section program.webserverConsoleRefined.operations

operation writeStandardOutputLine
input writeStandardOutputLine text String
output writeStandardOutputLine Result Void ConsoleWriteError
effect writeStandardOutputLine write console.stdout
memoryHeap writeStandardOutputLine no
memoryStackLimit writeStandardOutputLine 1KiB
async writeStandardOutputLine no
operationBody writeStandardOutputLine sourceTape

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

returnOk writeStandardOutputLineSuccessSentinel

label writeStandardOutputLineConsoleWriteFailed
returnError writeStandardOutputLineConsoleWriteError

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memoryHeap main no
memoryStackLimit main 4KiB
async main no
operationBody main sourceTape

purpose main "Print the listen-banner from javascript/webserver-console.js when the parity harness pins PORT to 3149"
invariant main "A single banner line is written before the server would otherwise block on accept"

label startMain

var lastConsoleWriteErrorCode ConsoleWriteErrorCode 0

call writeWebserverListenBannerLineCall writeStandardOutputLine
arg writeWebserverListenBannerLineCall text webserverListenBannerText
run writeWebserverListenBannerLineCall
ignoreOk writeWebserverListenBannerLineCall Void
bindError writeWebserverListenBannerLineError ConsoleWriteError writeWebserverListenBannerLineCall
set lastConsoleWriteErrorCode writeWebserverListenBannerLineError
branchIfError writeWebserverListenBannerLineCall consoleWriteFailed

returnOk successfulExitCode

label consoleWriteFailed
# rationale: lastConsoleWriteErrorCode holds whichever emit actually failed; its `set`
# ran immediately before the corresponding branchIfError, so the typed
# MainError.ConsoleWriteFailed value honestly names its cause (§12).
makeError consoleWriteFailure MainError.ConsoleWriteFailed lastConsoleWriteErrorCode
returnError consoleWriteFailure
