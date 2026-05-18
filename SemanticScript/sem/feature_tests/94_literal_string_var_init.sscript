# expect.stdout: hi\n
# expect.exit: 0
project LiteralStringVarInit
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32
operation main
input main console Console
output main Result ExitCode MainError
effect main read memory.buffer
effect main write console.stdout
memory main heap no
async main no
purpose main "Declare a var with a literal-string init `var greeting CNullTerminatedByteString \"hi\"` and print it via c.puts. Exercises pass1 string-const slot allocation for var literal inits."
invariant main "Output is 'hi\\n'. No supporting const declaration is needed."
label startMain
var greeting CNullTerminatedByteString "hi"
call putsCall c.puts
arg putsCall text greeting
run putsCall
ignoreOk putsCall CSignedInt32
const successfulExitCode ExitCode 0
returnOk successfulExitCode
