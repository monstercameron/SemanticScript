# expect.stdout:
# expect.exit: 0
project LiteralSourceMissingPathGraceful
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32
literal nonExistentAssetLiteral CNullTerminatedByteString
literalSource nonExistentAssetLiteral "_modules/this_file_does_not_exist_anywhere.bin"
operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Missing literalSource path must not crash compilation; const stays empty."
invariant main "Exit code 0; compile completes; stdout is empty (the literal's stub value)."
label startMain
const successfulExitCode ExitCode 0
returnOk successfulExitCode
