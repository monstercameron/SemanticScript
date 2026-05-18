# expect.stdout: hello world\n
# expect.exit: 0
project WriteOneLine
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
purpose main "Single console.writeLine of a string const."
invariant main "Emits 'hello world' followed by newline."
label startMain
const greetingText CNullTerminatedByteString "hello world"
call writeGreetingCall console.writeLine
arg writeGreetingCall console console
arg writeGreetingCall text greetingText
run writeGreetingCall
ignoreOk writeGreetingCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
