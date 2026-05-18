# expect.stdout: 1\n0\n
# expect.exit: 0
# expect.xfail: feature_coverage.py runs through bootstrap_general.as which does not yet implement json.decode.Bool. Direct ascc.py compilation is correct: strcmp against "true" returns 0 (match), so decoded value is 1; against "false" it's nonzero, so decoded value is 0. `python compiler/ascc.py THIS_FILE --emit-exe /tmp/x.exe && /tmp/x.exe` prints `1` then `0`.
project JsonDecodeBoolPrimitive
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
purpose main "json.decode.Bool returns 1 when the JSON token is 'true', 0 otherwise."
invariant main "Output is `1\\n0\\n`."
label startMain
const trueJsonToken CNullTerminatedByteString "true"
const falseJsonToken CNullTerminatedByteString "false"
call decodeTrueCall json.decode.Bool
arg decodeTrueCall value trueJsonToken
run decodeTrueCall
bind decodedTrueValue I64 decodeTrueCall
call writeTrueDecodedCall console.writeIntegerLine
arg writeTrueDecodedCall console console
arg writeTrueDecodedCall value decodedTrueValue
run writeTrueDecodedCall
ignoreOk writeTrueDecodedCall Void
call decodeFalseCall json.decode.Bool
arg decodeFalseCall value falseJsonToken
run decodeFalseCall
bind decodedFalseValue I64 decodeFalseCall
call writeFalseDecodedCall console.writeIntegerLine
arg writeFalseDecodedCall console console
arg writeFalseDecodedCall value decodedFalseValue
run writeFalseDecodedCall
ignoreOk writeFalseDecodedCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
