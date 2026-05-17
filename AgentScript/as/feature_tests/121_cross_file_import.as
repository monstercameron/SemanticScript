# expect.stdout: 42\n
# expect.exit: 0
# Cross-file import: pulls the `addSeven` operation from
# as/feature_tests/_modules/helper_lib.as and calls it from main.
project CrossFileImport
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError

importModule as.feature_tests._modules.helper_lib

operation main
input main console Console
output main Result ExitCode MainError
effect main read memory.buffer
effect main write console.stdout
memory main heap auto
async main no
purpose main "Call addSeven (defined in an imported module) with 35 and print the i64 result. Demonstrates that importModule resolves a relative module path, inlines the operation, and the operation is callable from the importing file."
invariant main "Output is '42\\n'."
label startMain
const baseValue I64 35
call addSevenCall addSeven
arg addSevenCall base baseValue
run addSevenCall
bind resultValue I64 addSevenCall
var resultVar I64 baseValue
set resultVar resultValue
call writeResultCall console.writeIntegerLine
arg writeResultCall console console
arg writeResultCall value resultVar
run writeResultCall
ignoreOk writeResultCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
