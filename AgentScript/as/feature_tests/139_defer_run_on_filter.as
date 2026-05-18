# expect.stdout: cleanupOnError\n
# expect.exit: 1
# expect.xfail: feature_coverage.py runs through bootstrap_general.as which does not yet honor `deferRunOn` path filtering. Direct ascc.py compilation is correct: the returnError path runs only the deferOnErrorOnly cleanup, not the deferOnOkOnly cleanup. `python compiler/ascc.py THIS_FILE --emit-exe /tmp/x.exe && /tmp/x.exe` prints `cleanupOnError` and exits 1. Closing means teaching bootstrap_general to collect deferRunOn lines and filter cleanup at each exit path.
project DeferRunOnFilter
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError DeliberateFailureForTest CSignedInt32
operation printCleanupOnOk
input printCleanupOnOk console Console
output printCleanupOnOk I32
const okCleanupMessage CNullTerminatedByteString "cleanupOnOk"
call writeOkCleanupCall console.writeLine
arg writeOkCleanupCall console console
arg writeOkCleanupCall text okCleanupMessage
run writeOkCleanupCall
ignoreOk writeOkCleanupCall Void
const okCleanupExit I32 0
returnValue okCleanupExit
operation printCleanupOnError
input printCleanupOnError console Console
output printCleanupOnError I32
const errorCleanupMessage CNullTerminatedByteString "cleanupOnError"
call writeErrorCleanupCall console.writeLine
arg writeErrorCleanupCall console console
arg writeErrorCleanupCall text errorCleanupMessage
run writeErrorCleanupCall
ignoreOk writeErrorCleanupCall Void
const errorCleanupExit I32 0
returnValue errorCleanupExit
operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "deferRunOn returnOk and returnError filter which exit path runs which defer."
invariant main "On returnError path: only deferOnErrorOnly fires; deferOnOkOnly is skipped. Output is exactly 'cleanupOnError' (one line)."
label startMain
defer deferOnOkOnly printCleanupOnOk console
deferRunOn deferOnOkOnly returnOk
defer deferOnErrorOnly printCleanupOnError console
deferRunOn deferOnErrorOnly returnError
makeError deliberateFailure MainError.DeliberateFailureForTest
returnError deliberateFailure
