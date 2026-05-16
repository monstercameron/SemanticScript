project HelloWorld
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
memory main stack max 4KiB
async main no

purpose main "Write the canonical greeting Hello, World! to standard output as a single line"
invariant main "The success path is taken only when the console write call reports a non-negative return value"
warning main "Never expose raw console-write driver errors in the operation output; map them through MainError"

label startMain

const helloGreetingText String "Hello, World!"

# rationale: Build the console write as a named call so the success and failure
# legs are inspectable, and pass the console dependency explicitly.
call writeHelloGreetingCall console.writeLine
arg writeHelloGreetingCall console console
arg writeHelloGreetingCall text helloGreetingText
run writeHelloGreetingCall
ignoreOk writeHelloGreetingCall Void
bindError writeHelloGreetingError ConsoleWriteError writeHelloGreetingCall
branchIfError writeHelloGreetingCall consoleWriteFailed

const successfulExitCode ExitCode 0
returnOk successfulExitCode

label consoleWriteFailed
# failure: Convert the raw ConsoleWriteError into a typed MainError variant so the
# operation output contract Result ExitCode MainError is satisfied.
makeError consoleWriteFailure MainError.ConsoleWriteFailed writeHelloGreetingError
returnError consoleWriteFailure
