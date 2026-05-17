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
#   exitWithCode(code)   - clean exit, runs atexit/static dtors then
#                          dies with the given exit code.
#   abortProcess         - raise SIGABRT, no cleanup.
#
# We don't smoke-test the terminators themselves (since they'd kill
# the test) — the smoke test simply verifies the wrappers compile.
# ============================================================


operation exitWithCode
input exitWithCode code CSignedInt32
output exitWithCode Result CSignedInt32 Void
effect exitWithCode read clock.cpu
memory exitWithCode heap no
async exitWithCode no
purpose exitWithCode "Terminate the process cleanly with the given exit code. Does not return; the returnOk path is reachable only on the (impossible) failure of c.exit."

label startExitWithCode
call libcCall c.exit
arg libcCall code code
run libcCall
const okCode CSignedInt32 0
returnOk okCode


operation abortProcess
output abortProcess Result CSignedInt32 Void
effect abortProcess read clock.cpu
memory abortProcess heap no
async abortProcess no
purpose abortProcess "Terminate the process immediately by raising SIGABRT. Does not return."

label startAbortProcess
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
purpose main "Print OK. We don't actually invoke exitWithCode/abortProcess because they'd terminate the test process."

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
