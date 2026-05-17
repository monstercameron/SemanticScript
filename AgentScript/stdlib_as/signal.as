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
#   raiseSignal(signum)       Wrap c.raise. Returns 0 on success.
#   sigSIGABRT, sigSIGFPE,
#   sigSIGILL, sigSIGINT,
#   sigSIGSEGV, sigSIGTERM     Standard signal-number accessors.
# ============================================================


operation raiseSignal
input raiseSignal signum CSignedInt32
output raiseSignal Result CSignedInt32 Void
effect raiseSignal write process.signal
memory raiseSignal heap no
async raiseSignal no
purpose raiseSignal "Wrap c.raise. Delivers signum to this process; returns 0 on success and a non-zero result on failure."

label startRaiseSignal
call libcCall c.raise
arg libcCall sig signum
run libcCall
bind raiseResult CSignedInt32 libcCall
returnOk raiseResult


operation sigSIGABRT
output sigSIGABRT Result CSignedInt32 Void
memory sigSIGABRT heap no
async sigSIGABRT no
purpose sigSIGABRT "SIGABRT (6). Abnormal-termination signal raised by abort()."
label startSigSIGABRT
const v CSignedInt32 6
returnOk v


operation sigSIGFPE
output sigSIGFPE Result CSignedInt32 Void
memory sigSIGFPE heap no
async sigSIGFPE no
purpose sigSIGFPE "SIGFPE (8). Erroneous arithmetic (divide by zero, overflow)."
label startSigSIGFPE
const v CSignedInt32 8
returnOk v


operation sigSIGILL
output sigSIGILL Result CSignedInt32 Void
memory sigSIGILL heap no
async sigSIGILL no
purpose sigSIGILL "SIGILL (4). Illegal instruction."
label startSigSIGILL
const v CSignedInt32 4
returnOk v


operation sigSIGINT
output sigSIGINT Result CSignedInt32 Void
memory sigSIGINT heap no
async sigSIGINT no
purpose sigSIGINT "SIGINT (2). Interactive attention signal (Ctrl-C)."
label startSigSIGINT
const v CSignedInt32 2
returnOk v


operation sigSIGSEGV
output sigSIGSEGV Result CSignedInt32 Void
memory sigSIGSEGV heap no
async sigSIGSEGV no
purpose sigSIGSEGV "SIGSEGV (11). Invalid memory reference (segmentation fault)."
label startSigSIGSEGV
const v CSignedInt32 11
returnOk v


operation sigSIGTERM
output sigSIGTERM Result CSignedInt32 Void
memory sigSIGTERM heap no
async sigSIGTERM no
purpose sigSIGTERM "SIGTERM (15). Termination request."
label startSigSIGTERM
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

call s1 sigSIGABRT
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

call s2 sigSIGTERM
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
