# expect.stdout:
# expect.exit: 42
project ExitNonZero
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32
operation main
input main console Console
output main Result ExitCode MainError
memory main heap no
async main no
purpose main "Tests: non-zero const ExitCode is honored by ret i32 emission."
invariant main "Returns the declared 42."
label startMain
const fortyTwoExitCode ExitCode 42
returnOk fortyTwoExitCode
