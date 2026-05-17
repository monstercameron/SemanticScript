# expect.stdout:
# expect.exit: 4294967295
project ExitCodeNegative
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
purpose main "Negative ExitCode: -1 should produce exit 255 (wrap mod 256)."
invariant main "Negative integer parsing works for const decls."
label startMain
const negativeOneExitCode ExitCode -1
returnOk negativeOneExitCode
