project Tiny
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
purpose main "Minimal: just exit 0 — no string consts, no calls."
invariant main "Self-host smoke test."
label startMain
const successfulExitCode ExitCode 0
returnOk successfulExitCode
