# expect.stdout: 1\n
# expect.exit: 0
# expect.xfail: feature_coverage.py runs through bootstrap_general.as which does not yet recognize `storage local mutable Bool`. Direct ascc.py compilation is correct: alloca i1; initial store true; set local toggles to false then back to true; final read prints 1. `python compiler/ascc.py THIS_FILE --emit-exe /tmp/x.exe && /tmp/x.exe` prints `1`.
project StorageLocalMutableBool
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
purpose main "storage local mutable Bool: alloca i1; set local true→false→true via separate const sources."
invariant main "Final state is true (1) — verified via integer-printing the loaded value."
label startMain
const initialFlagTrueValue Bool true
const transitionToFalseValue Bool false
const transitionBackToTrueValue Bool true
storage local mutable mutableFlagSlot Bool initialFlagTrueValue
set local mutableFlagSlot transitionToFalseValue
set local mutableFlagSlot transitionBackToTrueValue
var finalFlagAsInt I64 initialFlagTrueValue
set finalFlagAsInt mutableFlagSlot
call writeFlagCall console.writeIntegerLine
arg writeFlagCall console console
arg writeFlagCall value finalFlagAsInt
run writeFlagCall
ignoreOk writeFlagCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
