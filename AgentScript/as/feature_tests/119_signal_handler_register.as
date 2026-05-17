# expect.stdout: ok\n
# expect.exit: 0
project SignalHandlerRegister
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

# A signal handler operation. The C ABI wants `void (int)` — we model it
# as an operation whose result is ignored (CSignedInt32 placeholder).
operation myHandler
input myHandler signum CSignedInt32
output myHandler Result CSignedInt32 Void
purpose myHandler "Stub handler that does nothing. Just needs to exist as a function pointer."
label startHandler
const zero CSignedInt32 0
returnOk zero

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Register myHandler for SIGINT via c.signal, then print 'ok' (we never actually raise the signal)."
invariant main "Output: 'ok\\n'."
label startMain
const sigint CSignedInt32 2
call regCall c.signal
arg regCall sig sigint
arg regCall handler myHandler
run regCall
ignoreOk regCall COpaqueMemoryAddress

const okStr CNullTerminatedByteString "ok"
call w console.writeLine
arg w console console
arg w text okStr
run w
ignoreOk w Void

const okExit ExitCode 0
returnOk okExit
