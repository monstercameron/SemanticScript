project StdSignalSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <signal.h>-style signals.
#
# Floor primitives at this layer: c.raise (for signal-self-delivery)
# and c.signal (for handler registration — not exercised here yet
# because AS doesn't have first-class function pointers).
#
# Operations:
#   raiseProcessSignalNumber(signalNumber)       Wrap c.raise. Returns 0 on success.
#   abortSignalNumber, floatingPointExceptionSignalNumber,
#   illegalInstructionSignalNumber, interruptSignalNumber,
#   segmentationViolationSignalNumber, terminationSignalNumber     Standard signal-number accessors.
# ============================================================


operation raiseProcessSignalNumber
input raiseProcessSignalNumber signalNumber CSignedInt32
output raiseProcessSignalNumber Result CSignedInt32 Void
effect raiseProcessSignalNumber write process.signal
memory raiseProcessSignalNumber heap no
async raiseProcessSignalNumber no
purpose raiseProcessSignalNumber "Wrap c.raise. Delivers signalNumber to this process; returns 0 on success and a non-zero result on failure."

label startRaiseProcessSignalNumber
call libcCall c.raise
arg libcCall sig signalNumber
run libcCall
bind raiseResult CSignedInt32 libcCall
returnOk raiseResult


operation abortSignalNumber
output abortSignalNumber Result CSignedInt32 Void
memory abortSignalNumber heap no
async abortSignalNumber no
purpose abortSignalNumber "SIGABRT (6). Abnormal-termination signal raised by abort()."
label startAbortSignalNumber
const v CSignedInt32 6
returnOk v


operation floatingPointExceptionSignalNumber
output floatingPointExceptionSignalNumber Result CSignedInt32 Void
memory floatingPointExceptionSignalNumber heap no
async floatingPointExceptionSignalNumber no
purpose floatingPointExceptionSignalNumber "SIGFPE (8). Erroneous arithmetic (divide by zero, overflow)."
label startFloatingPointExceptionSignalNumber
const v CSignedInt32 8
returnOk v


operation illegalInstructionSignalNumber
output illegalInstructionSignalNumber Result CSignedInt32 Void
memory illegalInstructionSignalNumber heap no
async illegalInstructionSignalNumber no
purpose illegalInstructionSignalNumber "SIGILL (4). Illegal instruction."
label startIllegalInstructionSignalNumber
const v CSignedInt32 4
returnOk v


operation interruptSignalNumber
output interruptSignalNumber Result CSignedInt32 Void
memory interruptSignalNumber heap no
async interruptSignalNumber no
purpose interruptSignalNumber "SIGINT (2). Interactive attention signal (Ctrl-C)."
label startInterruptSignalNumber
const v CSignedInt32 2
returnOk v


operation segmentationViolationSignalNumber
output segmentationViolationSignalNumber Result CSignedInt32 Void
memory segmentationViolationSignalNumber heap no
async segmentationViolationSignalNumber no
purpose segmentationViolationSignalNumber "SIGSEGV (11). Invalid memory reference (segmentation fault)."
label startSegmentationViolationSignalNumber
const v CSignedInt32 11
returnOk v


operation terminationSignalNumber
output terminationSignalNumber Result CSignedInt32 Void
memory terminationSignalNumber heap no
async terminationSignalNumber no
purpose terminationSignalNumber "SIGTERM (15). Termination request."
label startTerminationSignalNumber
const v CSignedInt32 15
returnOk v


# ============================================================
# Smoke test — we only check the constant accessors. We don't
# actually raise any signal because that would terminate the process.
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test signal accessors. Prints OK."

label startMain

call s1 abortSignalNumber
run s1
bindOk s1Res CSignedInt32 s1
const six CSignedInt32 6
call s1Check math.equalI64
arg s1Check left s1Res
arg s1Check right six
run s1Check
bind s1Ok Bool s1Check
branchIf s1Ok s1OkLabel
branch testFailed
label s1OkLabel

call s2 terminationSignalNumber
run s2
bindOk s2Res CSignedInt32 s2
const fifteen CSignedInt32 15
call s2Check math.equalI64
arg s2Check left s2Res
arg s2Check right fifteen
run s2Check
bind s2Ok Bool s2Check
branchIf s2Ok s2OkLabel
branch testFailed
label s2OkLabel

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

label testFailed
const exitFail CSignedInt32 1
makeError testFailure MainError.TestFailed exitFail
returnError testFailure
