# expect.stdout: hello\nfirstCleanup\nsecondCleanup\n
# expect.exit: 0
# expect.xfail: feature_coverage.py runs through bootstrap_general.as which does not yet lower `defer`/`deferLog` to a real cleanup call sequence at op exits. Direct ascc.py compilation works correctly (`python compiler/ascc.py THIS_FILE --emit-exe /tmp/x.exe && /tmp/x.exe` prints the three lines in reverse-registration order and exits 0). Closing means teaching bootstrap_general to collect defers and emit them in reverse-registration order before each return.
project DeferReverseOrder
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError
operation printSecondCleanup
input printSecondCleanup console Console
output printSecondCleanup I32
const secondCleanupMessage CNullTerminatedByteString "secondCleanup"
call writeSecondCall console.writeLine
arg writeSecondCall console console
arg writeSecondCall text secondCleanupMessage
run writeSecondCall
ignoreOk writeSecondCall Void
const successfulInnerExit I32 0
returnValue successfulInnerExit
operation printFirstCleanup
input printFirstCleanup console Console
output printFirstCleanup I32
const firstCleanupMessage CNullTerminatedByteString "firstCleanup"
call writeFirstCall console.writeLine
arg writeFirstCall console console
arg writeFirstCall text firstCleanupMessage
run writeFirstCall
ignoreOk writeFirstCall Void
const innerExitSuccess I32 0
returnValue innerExitSuccess
operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Defers run in reverse registration order on every exit path."
invariant main "After 'hello', firstCleanup prints (because secondCleanup registered first, runs second)."
label startMain
defer secondCleanupDefer printSecondCleanup console
defer firstCleanupDefer printFirstCleanup console
const helloMessage CNullTerminatedByteString "hello"
call writeHelloCall console.writeLine
arg writeHelloCall console console
arg writeHelloCall text helloMessage
run writeHelloCall
ignoreOk writeHelloCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
