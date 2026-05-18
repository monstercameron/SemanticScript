# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: process lifecycle terminators
# ============================================================
#
# # rationale: C's <stdlib.h> exposes exit(int) and abort(void) —
#   two unconditional process terminators. The refined surface keeps
#   them as real operations (they have observable effects: write
#   process.lifecycle) but removes the misleading `Result X Void`
#   return contract. Neither operation can return at the source
#   level — control flow exits the process — so the output type is
#   `Void` with a fall-through ret only there to keep the LLVM IR
#   well-formed.
#
# # invariant: both operations are partial in the language-theory
#   sense: control never returns to the caller. We model that with
#   `Void` output plus an effect declaration so the linter can
#   surface unauthorized use.
#
# # security: terminating the process can lose pending I/O. exit()
#   flushes stdio buffers and runs atexit handlers; abort() does
#   neither. Callers must choose deliberately.
#
# # timing: yields to the OS scheduler immediately. exit() may run
#   user atexit handlers; abort() takes the SIGABRT fast path.
#
# # observability: both are externally observable via the process
#   exit code reported to the parent shell.

project StdProcessSelfTest
target console
runtime AgentRuntime 0.1
entry console main

error MainError
errorCase MainError ProcessSmokeAssertionFailed

# section process.terminators

operation exitProcessWithStatusCode
input exitProcessWithStatusCode exitStatusCode CSignedInt32
output exitProcessWithStatusCode Void
effect exitProcessWithStatusCode write process.lifecycle
memoryHeap exitProcessWithStatusCode no
async exitProcessWithStatusCode no
purpose exitProcessWithStatusCode "Terminate the process cleanly with the given exit status code. Flushes stdio and runs atexit handlers, then exits. Does not return."
invariant exitProcessWithStatusCode "Control flow terminates at this call site; the fall-through return statement is unreachable in well-formed programs."
warning exitProcessWithStatusCode "Pending I/O on file streams other than stdio (e.g. mmap'd buffers) is the caller's responsibility — exit() does not flush them."
guarantee exitProcessWithStatusCode "Always terminates the process."
label startExitProcessWithStatusCode
call libcExitCall c.exit
arg libcExitCall code exitStatusCode
run libcExitCall
# Fall-through is unreachable; the codegen emits an i32 0 ret to
# keep LLVM happy.

operation abortCurrentProcess
output abortCurrentProcess Void
effect abortCurrentProcess write process.lifecycle
memoryHeap abortCurrentProcess no
async abortCurrentProcess no
purpose abortCurrentProcess "Terminate the process immediately by raising SIGABRT. Does NOT flush stdio. Does not return."
invariant abortCurrentProcess "Control flow terminates at this call site."
warning abortCurrentProcess "No buffer flushing, no atexit handlers — use exitProcessWithStatusCode unless the failure is so severe that flushing would propagate corrupted state."
guarantee abortCurrentProcess "Always terminates the process."
label startAbortCurrentProcess
call libcAbortCall c.abort
run libcAbortCall

# ============================================================
# Smoke test
# ============================================================
# We deliberately do NOT call the terminators in the smoke test
# because they'd kill the test runner. This file's smoke verifies
# only that the operations compile and the metadata parses.

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memoryHeap main no
async main no
purpose main "Verify process.as compiles and metadata parses; do NOT actually invoke the terminators."

label startMain
const successMessageText CNullTerminatedByteString "OK"
call writeSuccessLineCall console.writeLine
arg writeSuccessLineCall console console
arg writeSuccessLineCall text successMessageText
run writeSuccessLineCall
ignoreOk writeSuccessLineCall Void
const exitOkCode ExitCode 0
returnOk exitOkCode
