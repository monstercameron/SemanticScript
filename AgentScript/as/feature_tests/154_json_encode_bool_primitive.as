# expect.stdout: true\nfalse\n
# expect.exit: 0
# expect.xfail: feature_coverage.py runs through bootstrap_general.as which does not yet implement json.encode.Bool. Direct ascc.py compilation is correct: the call lowers to a `select` between two interned strings. `python compiler/ascc.py THIS_FILE --emit-exe /tmp/x.exe && /tmp/x.exe` prints `true` then `false`.
project JsonEncodeBoolPrimitive
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
purpose main "json.encode.Bool returns 'true' for true input, 'false' for false."
invariant main "Output is exactly 'true\\nfalse\\n'."
label startMain
const trueValue Bool true
const falseValue Bool false
call encodeTrueCall json.encode.Bool
arg encodeTrueCall value trueValue
run encodeTrueCall
bind trueEncodedString CNullTerminatedByteString encodeTrueCall
call writeTrueCall console.writeLine
arg writeTrueCall console console
arg writeTrueCall text trueEncodedString
run writeTrueCall
ignoreOk writeTrueCall Void
call encodeFalseCall json.encode.Bool
arg encodeFalseCall value falseValue
run encodeFalseCall
bind falseEncodedString CNullTerminatedByteString encodeFalseCall
call writeFalseCall console.writeLine
arg writeFalseCall console console
arg writeFalseCall text falseEncodedString
run writeFalseCall
ignoreOk writeFalseCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
