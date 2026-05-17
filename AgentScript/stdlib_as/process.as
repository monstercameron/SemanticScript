project StdProcessSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: process-lifecycle ops.
#
# Floor primitives at this layer: c.exit (clean process exit) and
# c.abort (raise SIGABRT and die). Both are unconditional terminators
# — they don't return.
#
# Operations:
#   exitProcessWithStatusCode(exitStatusCode)
#                          - clean exit, runs atexit/static dtors then
#                            dies with the given exit code.
#   abortCurrentProcess    - raise SIGABRT, no cleanup.
#
# We don't smoke-test the terminators themselves (since they'd kill
# the test) — the smoke test simply verifies the wrappers compile.
# ============================================================


operation exitProcessWithStatusCode
input exitProcessWithStatusCode exitStatusCode CSignedInt32
output exitProcessWithStatusCode Result CSignedInt32 Void
effect exitProcessWithStatusCode read clock.cpu
memory exitProcessWithStatusCode heap no
async exitProcessWithStatusCode no
purpose exitProcessWithStatusCode "Terminate the process cleanly with the given exit status code. Does not return; the returnOk path is reachable only on the (impossible) failure of c.exit."

label startExitProcessWithStatusCode
call libcCall c.exit
arg libcCall code exitStatusCode
run libcCall
const okCode CSignedInt32 0
returnOk okCode


operation abortCurrentProcess
output abortCurrentProcess Result CSignedInt32 Void
effect abortCurrentProcess read clock.cpu
memory abortCurrentProcess heap no
async abortCurrentProcess no
purpose abortCurrentProcess "Terminate the process immediately by raising SIGABRT. Does not return."

label startAbortCurrentProcess
call libcCall c.abort
run libcCall
const okCode CSignedInt32 0
returnOk okCode


# ============================================================
# Smoke test — just verifies the file compiles. We do NOT actually
# call the terminators (that would kill the test).
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Print OK. We don't actually invoke exitProcessWithStatusCode/abortCurrentProcess because they'd terminate the test process."

label startMain

const charO CSignedInt32 79
const charK CSignedInt32 75
const charNl CSignedInt32 10
call putO c.putchar
arg putO c charO
run putO
call putK c.putchar
arg putK c charK
run putK
call putNl c.putchar
arg putNl c charNl
run putNl

const exitOk ExitCode 0
returnOk exitOk
