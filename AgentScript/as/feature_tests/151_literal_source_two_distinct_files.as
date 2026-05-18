# expect.stdout: alpha greeting from disk\nbeta greeting from disk\n
# expect.exit: 0
# expect.xfail: feature_coverage.py runs through bootstrap_general.as which does not yet inline the bytes of `literalSource` paths into `literal` consts. Direct ascc.py compilation is correct: both files are loaded; each literal const carries its own bytes. `python compiler/ascc.py THIS_FILE --emit-exe /tmp/x.exe && /tmp/x.exe` prints both lines.
project LiteralSourceTwoFiles
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32
literal externalAlphaLiteral CNullTerminatedByteString
literalSource externalAlphaLiteral "_modules/external_greeting_alpha.txt"
literal externalBetaLiteral CNullTerminatedByteString
literalSource externalBetaLiteral "_modules/external_greeting_beta.txt"
operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Two literals from two distinct files; each must carry its own bytes."
invariant main "Output is alpha line then beta line (no bleed)."
label startMain
call writeAlphaCall console.writeLine
arg writeAlphaCall console console
arg writeAlphaCall text externalAlphaLiteral
run writeAlphaCall
ignoreOk writeAlphaCall Void
call writeBetaCall console.writeLine
arg writeBetaCall console console
arg writeBetaCall text externalBetaLiteral
run writeBetaCall
ignoreOk writeBetaCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
