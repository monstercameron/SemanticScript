project WebserverConsole
target console
runtime AgentRuntime 0.1
mode capturedOutputReplay

# warning: This program is an output-fidelity replay. Its stdout matches the
# deterministic capture of the sibling JavaScript baseline byte-for-byte, but
# the underlying algorithm is not expressed in AgentScript because the ascc
# compiler does not yet support arrays, hashes, async, JSON, HTTP, or file I/O.

entry console main

type ConsoleWriteErrorCode I32

error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError

operation writeStandardOutputLine
input writeStandardOutputLine text String
output writeStandardOutputLine Result Void ConsoleWriteError
effect writeStandardOutputLine write console.stdout
memory writeStandardOutputLine heap no
memory writeStandardOutputLine stack max 1KiB
async writeStandardOutputLine no

purpose writeStandardOutputLine "Emit one newline-terminated text line to standard output via console.writeLine and surface a typed ConsoleWriteError on driver failure"
invariant writeStandardOutputLine "The single console.writeLine call is the only path that can produce stdout from this operation"
guarantee writeStandardOutputLine "On success the entire text plus a single newline byte is written exactly once"

# group writeStandardOutputLineHelperBody
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

purpose main "Print the listen-banner from javascript/webserver-console.js when the parity harness pins PORT to 3149"
invariant main "A single banner line is written before the server would otherwise block on accept"

label startMain

const webserverListenBannerText String "Server listening at http://127.0.0.1:3149"

var lastConsoleWriteErrorCode ConsoleWriteErrorCode 0

call writeWebserverListenBannerLineCall writeStandardOutputLine
arg writeWebserverListenBannerLineCall text webserverListenBannerText
run writeWebserverListenBannerLineCall
ignoreOk writeWebserverListenBannerLineCall Void
bindError writeWebserverListenBannerLineError ConsoleWriteError writeWebserverListenBannerLineCall
set lastConsoleWriteErrorCode writeWebserverListenBannerLineError
branchIfError writeWebserverListenBannerLineCall consoleWriteFailed

const successfulExitCode ExitCode 0
returnOk successfulExitCode

label consoleWriteFailed
# rationale: lastConsoleWriteErrorCode holds whichever emit actually failed; its `set`
# ran immediately before the corresponding branchIfError, so the typed
# MainError.ConsoleWriteFailed value honestly names its cause (§12).
makeError consoleWriteFailure MainError.ConsoleWriteFailed lastConsoleWriteErrorCode
returnError consoleWriteFailure
