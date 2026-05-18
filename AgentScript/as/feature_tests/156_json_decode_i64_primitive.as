# expect.stdout: 12345\n
# expect.exit: 0
# expect.xfail: feature_coverage.py runs through bootstrap_general.as which does not yet implement json.decode primitives. Direct ascc.py compilation is correct: the call lowers to libc atoll on the null-terminated input. `python compiler/ascc.py THIS_FILE --emit-exe /tmp/x.exe && /tmp/x.exe` prints `12345`.
project JsonDecodeI64Primitive
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
purpose main "json.decode.I64 parses a JSON integer string into an i64."
invariant main "Input '12345' decodes to integer 12345."
label startMain
const integerTextLiteral CNullTerminatedByteString "12345"
call decodeIntCall json.decode.I64
arg decodeIntCall value integerTextLiteral
run decodeIntCall
bind decodedInteger I64 decodeIntCall
call writeDecodedCall console.writeIntegerLine
arg writeDecodedCall console console
arg writeDecodedCall value decodedInteger
run writeDecodedCall
ignoreOk writeDecodedCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
