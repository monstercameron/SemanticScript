# expect.stdout: hello from c.puts\n
# expect.exit: 0
project CPutsTest
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32
operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Emit a string-const through c.puts directly. Exercises the c.puts libc passthrough with a string-const arg."
invariant main "puts appends a newline automatically."
label startMain
const greeting CNullTerminatedByteString "hello from c.puts"
call putsCall c.puts
arg putsCall text greeting
run putsCall
ignoreOk putsCall CSignedInt32
const successfulExitCode ExitCode 0
returnOk successfulExitCode
