# expect.stdout: 7.500000\n
# expect.exit: 0
# expect.xfail: feature_coverage.py runs through bootstrap_general.as which does not yet recognize `storage local mutable` of CFloat64. Direct ascc.py compilation is correct: alloca double; initial store 3.5; add 4.0; store back; load and print. `python compiler/ascc.py THIS_FILE --emit-exe /tmp/x.exe && /tmp/x.exe` prints `7.500000`.
project StorageLocalMutableFloat
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
purpose main "storage local mutable of CFloat64: alloca double, real store/load, math.addF64 result flows through."
invariant main "Output is 7.5 (3.5 + 4.0) using double arithmetic, not int."
label startMain
const initialFloatValue CFloat64 3.5
const incrementFloatValue CFloat64 4.0
storage local mutable mutableFloatSlot CFloat64 initialFloatValue
call addFloatCall math.addF64
arg addFloatCall left mutableFloatSlot
arg addFloatCall right incrementFloatValue
run addFloatCall
bind floatSumResult CFloat64 addFloatCall
set local mutableFloatSlot floatSumResult
call writeFloatCall console.writeFloatLine
arg writeFloatCall console console
arg writeFloatCall value mutableFloatSlot
run writeFloatCall
ignoreOk writeFloatCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
