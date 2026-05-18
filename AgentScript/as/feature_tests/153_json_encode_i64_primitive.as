# expect.stdout: 42\n
# expect.exit: 0
# expect.xfail: feature_coverage.py runs through bootstrap_general.as which does not yet implement json.encode primitives. Direct ascc.py compilation is correct: json.encode.I64 stack-allocates a 32-byte buffer and snprintf-formats the integer. The result is the formatted "42" string. `python compiler/ascc.py THIS_FILE --emit-exe /tmp/x.exe && /tmp/x.exe` prints `42`.
project JsonEncodeI64Primitive
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
purpose main "json.encode.I64 formats an integer to its JSON decimal string via libc snprintf."
invariant main "Output is the JSON representation of 42 — exactly the string '42'."
label startMain
const fortyTwoValue I64 42
call encodeIntCall json.encode.I64
arg encodeIntCall value fortyTwoValue
run encodeIntCall
bind encodedString CNullTerminatedByteString encodeIntCall
call writeResultCall console.writeLine
arg writeResultCall console console
arg writeResultCall text encodedString
run writeResultCall
ignoreOk writeResultCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
