# expect.stdout: 12345\n
# expect.exit: 0
project CAtoiTest
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
purpose main "Parse a numeric string literal via c.atoi and echo it back through console.writeIntegerLine."
invariant main "Exercises the c.atoi libc passthrough with a string-const buffer."
label startMain
const numericText CNullTerminatedByteString "12345"
call parseCall c.atoi
arg parseCall s numericText
run parseCall
bind parsedValue CSignedInt32 parseCall
var parsedStorage I64 0
set parsedStorage parsedValue
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value parsedStorage
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
