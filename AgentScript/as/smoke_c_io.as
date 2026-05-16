project SmokeCIo
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError ConsoleWriteFailed CSignedInt32

operation main
input main console Console
output main Result ExitCode MainError
effect main read clock.cpu
effect main read process.arguments
effect main read process.environment
effect main write console.stdout
memory main heap no
memory main stack max 4KiB
async main no

purpose main "Demonstrate c.puts / c.printf / c.getenv from AgentScript and confirm the libc surface is reachable beyond writeLine"
invariant main "Each c.* call writes a single observable line of stdout output"

label startMain

const smokeIoBannerText CNullTerminatedByteString "=== smoke_c_io ==="
const smokeIoPutsDemoLineText CNullTerminatedByteString "via c.puts: hello from puts"
const smokeIoPrintfFiveCharFormatText CNullTerminatedByteString "via c.printf: %c%c%c%c%c\n"
const smokeIoGetenvProbeName CNullTerminatedByteString "PATH"
const smokeIoGetenvReportFormatText CNullTerminatedByteString "via c.getenv: PATH is reachable (sentinel=%d)\n"

# ASCII code points spelling "Hello" — printed individually through printf %c
# to demonstrate that variadic CSignedInt32 args round-trip through the c.* ABI.
const helloAsciiCapitalH CSignedInt32 72
const helloAsciiLowercaseE CSignedInt32 101
const helloAsciiLowercaseLFirst CSignedInt32 108
const helloAsciiLowercaseLSecond CSignedInt32 108
const helloAsciiLowercaseO CSignedInt32 111

# c.puts — direct libc invocation, no console.* wrapper.
call writeBannerPutsCall c.puts
arg writeBannerPutsCall text smokeIoBannerText
run writeBannerPutsCall
ignoreOk writeBannerPutsCall Void
bindError writeBannerPutsError CSignedInt32 writeBannerPutsCall
branchIfError writeBannerPutsCall writeBannerPutsFailed

call writePutsDemoLineCall c.puts
arg writePutsDemoLineCall text smokeIoPutsDemoLineText
run writePutsDemoLineCall
ignoreOk writePutsDemoLineCall Void
bindError writePutsDemoLineError CSignedInt32 writePutsDemoLineCall
branchIfError writePutsDemoLineCall writePutsDemoLineFailed

# c.printf with five %c args — emits the string "Hello" one char at a time.
call writeHelloByCharsCall c.printf
arg writeHelloByCharsCall format smokeIoPrintfFiveCharFormatText
arg writeHelloByCharsCall firstChar helloAsciiCapitalH
arg writeHelloByCharsCall secondChar helloAsciiLowercaseE
arg writeHelloByCharsCall thirdChar helloAsciiLowercaseLFirst
arg writeHelloByCharsCall fourthChar helloAsciiLowercaseLSecond
arg writeHelloByCharsCall fifthChar helloAsciiLowercaseO
run writeHelloByCharsCall
ignoreOk writeHelloByCharsCall Void
bindError writeHelloByCharsError CSignedInt32 writeHelloByCharsCall
branchIfError writeHelloByCharsCall writeHelloByCharsFailed

# c.getenv — confirms the runtime resolves the symbol and returns a pointer.
# The returned char* is not deref'd here (would need pointer.loadByte); we
# only confirm the call shape works by printing a sentinel value of 1.
call getenvPathCall c.getenv
arg getenvPathCall name smokeIoGetenvProbeName
run getenvPathCall
bind environmentPathPointer COpaqueMemoryAddress getenvPathCall

const getenvCallReachedSentinel CSignedInt32 1
call writeGetenvReportCall c.printf
arg writeGetenvReportCall format smokeIoGetenvReportFormatText
arg writeGetenvReportCall sentinel getenvCallReachedSentinel
run writeGetenvReportCall
ignoreOk writeGetenvReportCall Void
bindError writeGetenvReportError CSignedInt32 writeGetenvReportCall
branchIfError writeGetenvReportCall writeGetenvReportFailed

const successfulExitCode ExitCode 0
returnOk successfulExitCode

label writeBannerPutsFailed
makeError writeBannerPutsFailure MainError.ConsoleWriteFailed writeBannerPutsError
returnError writeBannerPutsFailure

label writePutsDemoLineFailed
makeError writePutsDemoLineFailure MainError.ConsoleWriteFailed writePutsDemoLineError
returnError writePutsDemoLineFailure

label writeHelloByCharsFailed
makeError writeHelloByCharsFailure MainError.ConsoleWriteFailed writeHelloByCharsError
returnError writeHelloByCharsFailure

label writeGetenvReportFailed
makeError writeGetenvReportFailure MainError.ConsoleWriteFailed writeGetenvReportError
returnError writeGetenvReportFailure
