# expect.stdout: hello\n
# expect.exit: 0
project StringRecord113
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

record Greeting layout row align 8
field Greeting text CNullTerminatedByteString

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Store a string-const into a record field, read, print."
invariant main "hello goes in and comes out."
label startMain
const helloStr CNullTerminatedByteString "hello"
new myGreeting Greeting
fieldSet myGreeting text helloStr
fieldGet readText CNullTerminatedByteString myGreeting text
call writeCall console.writeLine
arg writeCall console console
arg writeCall text readText
run writeCall
ignoreOk writeCall Void
const okExit ExitCode 0
returnOk okExit
