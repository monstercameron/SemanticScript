# expect.stdout:
# expect.exit: 0
# Tests: const ExitCode 0 + returnOk produces exit 0
project ExitZero
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
purpose main "Minimal program: exit 0, no output."
invariant main "Returns zero with no stdout."
label startMain
const successfulExitCode ExitCode 0
returnOk successfulExitCode
