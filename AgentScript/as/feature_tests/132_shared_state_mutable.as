# expect.stdout: 0\n9\n
# expect.exit: 0
# expect.xfail: feature_coverage.py runs through bootstrap_general.as which does not yet recognize `sharedState process mutable` / `set sharedState`. Direct ascc.py compilation works correctly (`python compiler/ascc.py THIS_FILE --emit-exe /tmp/x.exe && /tmp/x.exe` prints `0\n9\n` and exits 0). Closing means teaching bootstrap_general to emit a module-scope global with load/store for the sharedState mutable form.
project SharedStateMutable
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError
const zeroCount I64 0
const failureIncrementValue I64 9
sharedState process mutable accountLookupFailureCount I64 zeroCount
operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "sharedState process mutable holds a real LLVM global."
invariant main "Print 0 (initial), set, then print 9 (new value)."
label startMain
call writeInitialCall console.writeIntegerLine
arg writeInitialCall console console
arg writeInitialCall value accountLookupFailureCount
run writeInitialCall
ignoreOk writeInitialCall Void
set sharedState accountLookupFailureCount failureIncrementValue
call writeUpdatedCall console.writeIntegerLine
arg writeUpdatedCall console console
arg writeUpdatedCall value accountLookupFailureCount
run writeUpdatedCall
ignoreOk writeUpdatedCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
