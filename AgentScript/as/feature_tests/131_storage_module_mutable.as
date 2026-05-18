# expect.stdout: 5\n12\n
# expect.exit: 0
# expect.xfail: feature_coverage.py runs through bootstrap_general.as which does not yet recognize `storage module mutable` / `set module`. Direct ascc.py compilation works correctly (`python compiler/ascc.py THIS_FILE --emit-exe /tmp/x.exe && /tmp/x.exe` prints `5\n12\n` and exits 0). Closing means teaching bootstrap_general to emit a module-scope global with load/store for the module-mutable form.
project StorageModuleMutable
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError
const initialModuleCounterValue I64 5
const moduleIncrementStepValue I64 7
storage module mutable persistentCounterValue I64 initialModuleCounterValue
operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "storage module mutable persists across set/read within the same op."
invariant main "Initial print is 5; after set the print is 12."
label startMain
call writeInitialCall console.writeIntegerLine
arg writeInitialCall console console
arg writeInitialCall value persistentCounterValue
run writeInitialCall
ignoreOk writeInitialCall Void
call addStepCall math.addI64
arg addStepCall left persistentCounterValue
arg addStepCall right moduleIncrementStepValue
run addStepCall
bind addStepResult I64 addStepCall
set module persistentCounterValue addStepResult
call writeUpdatedCall console.writeIntegerLine
arg writeUpdatedCall console console
arg writeUpdatedCall value persistentCounterValue
run writeUpdatedCall
ignoreOk writeUpdatedCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
