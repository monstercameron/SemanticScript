# expect.stdout: 7\n42\n
# expect.exit: 0
project ConstScoping
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation getSeven
output getSeven Result CSignedInt64 Void
label startGetSeven
const answer CSignedInt64 7
returnOk answer

operation getFortyTwo
output getFortyTwo Result CSignedInt64 Void
label startGetFortyTwo
const answer CSignedInt64 42
returnOk answer

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Two user ops each declare `const answer` with different values. Print both."
invariant main "Output: 7 then 42."
label startMain
call sevenCall getSeven
run sevenCall
bindOk sevenResult CSignedInt64 sevenCall
var s1 I64 0
set s1 sevenResult
call w1 console.writeIntegerLine
arg w1 console console
arg w1 value s1
run w1
ignoreOk w1 Void

call fortytwoCall getFortyTwo
run fortytwoCall
bindOk fortytwoResult CSignedInt64 fortytwoCall
var s2 I64 0
set s2 fortytwoResult
call w2 console.writeIntegerLine
arg w2 console console
arg w2 value s2
run w2
ignoreOk w2 Void

const okExit ExitCode 0
returnOk okExit
