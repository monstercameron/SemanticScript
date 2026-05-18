# expect.stdout: The quick brown fox jumps over the lazy dog.\n
# expect.exit: 0
project LongString
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError
operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Long string literal with spaces and punctuation."
invariant main "Output is the literal verbatim plus newline."
label startMain
const pangramText CNullTerminatedByteString "The quick brown fox jumps over the lazy dog."
call writeCall console.writeLine
arg writeCall console console
arg writeCall text pangramText
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
