# expect.stdout: world\n
# expect.exit: 0
project RecordPtrBind
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

record Greeting layout row align 8
field Greeting text CNullTerminatedByteString

operation getWorld
output getWorld Result CNullTerminatedByteString Void
purpose getWorld "Return a string-const as a pointer-typed bind result."
label startGetWorld
const worldStr CNullTerminatedByteString "world"
returnOk worldStr

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Get a pointer bind from a user op, then fieldSet a string field from it."
invariant main "Print 'world'."
label startMain
call getCall getWorld
run getCall
bindOk strBind CNullTerminatedByteString getCall
new myGreeting Greeting
fieldSet myGreeting text strBind
fieldGet readText CNullTerminatedByteString myGreeting text
call writeCall console.writeLine
arg writeCall console console
arg writeCall text readText
run writeCall
ignoreOk writeCall Void
const okExit ExitCode 0
returnOk okExit
