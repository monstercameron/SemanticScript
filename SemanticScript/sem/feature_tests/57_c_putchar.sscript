# expect.stdout: AB
# expect.exit: 0
project CPutchar
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
purpose main "Emit two bytes via c.putchar (A=65, B=66)."
invariant main "Direct libc passthrough to putchar."
label startMain
const charA CSignedInt32 65
const charB CSignedInt32 66
call writeACall c.putchar
arg writeACall c charA
run writeACall
call writeBCall c.putchar
arg writeBCall c charB
run writeBCall
const successfulExitCode ExitCode 0
returnOk successfulExitCode
