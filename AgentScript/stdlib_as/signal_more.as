project StdSignalMoreSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: extended signal numbers.
#
# Standard POSIX signals beyond the core six exposed in signal.as.
#
# Operations:
#   sigSIGHUP, sigSIGQUIT, sigSIGTRAP, sigSIGBUS, sigSIGKILL,
#   sigSIGUSR1, sigSIGUSR2, sigSIGPIPE, sigSIGALRM, sigSIGCHLD,
#   sigSIGCONT, sigSIGSTOP, sigSIGTSTP, sigSIGTTIN, sigSIGTTOU.
# ============================================================

operation sigSIGHUP
output sigSIGHUP Result CSignedInt32 Void
memory sigSIGHUP heap no
async sigSIGHUP no
purpose sigSIGHUP "SIGHUP (1)."
label start
const v CSignedInt32 1
returnOk v

operation sigSIGQUIT
output sigSIGQUIT Result CSignedInt32 Void
memory sigSIGQUIT heap no
async sigSIGQUIT no
purpose sigSIGQUIT "SIGQUIT (3)."
label start
const v CSignedInt32 3
returnOk v

operation sigSIGTRAP
output sigSIGTRAP Result CSignedInt32 Void
memory sigSIGTRAP heap no
async sigSIGTRAP no
purpose sigSIGTRAP "SIGTRAP (5)."
label start
const v CSignedInt32 5
returnOk v

operation sigSIGBUS
output sigSIGBUS Result CSignedInt32 Void
memory sigSIGBUS heap no
async sigSIGBUS no
purpose sigSIGBUS "SIGBUS (7)."
label start
const v CSignedInt32 7
returnOk v

operation sigSIGKILL
output sigSIGKILL Result CSignedInt32 Void
memory sigSIGKILL heap no
async sigSIGKILL no
purpose sigSIGKILL "SIGKILL (9)."
label start
const v CSignedInt32 9
returnOk v

operation sigSIGUSR1
output sigSIGUSR1 Result CSignedInt32 Void
memory sigSIGUSR1 heap no
async sigSIGUSR1 no
purpose sigSIGUSR1 "SIGUSR1 (10)."
label start
const v CSignedInt32 10
returnOk v

operation sigSIGUSR2
output sigSIGUSR2 Result CSignedInt32 Void
memory sigSIGUSR2 heap no
async sigSIGUSR2 no
purpose sigSIGUSR2 "SIGUSR2 (12)."
label start
const v CSignedInt32 12
returnOk v

operation sigSIGPIPE
output sigSIGPIPE Result CSignedInt32 Void
memory sigSIGPIPE heap no
async sigSIGPIPE no
purpose sigSIGPIPE "SIGPIPE (13)."
label start
const v CSignedInt32 13
returnOk v

operation sigSIGALRM
output sigSIGALRM Result CSignedInt32 Void
memory sigSIGALRM heap no
async sigSIGALRM no
purpose sigSIGALRM "SIGALRM (14)."
label start
const v CSignedInt32 14
returnOk v

operation sigSIGCHLD
output sigSIGCHLD Result CSignedInt32 Void
memory sigSIGCHLD heap no
async sigSIGCHLD no
purpose sigSIGCHLD "SIGCHLD (17)."
label start
const v CSignedInt32 17
returnOk v

operation sigSIGCONT
output sigSIGCONT Result CSignedInt32 Void
memory sigSIGCONT heap no
async sigSIGCONT no
purpose sigSIGCONT "SIGCONT (18)."
label start
const v CSignedInt32 18
returnOk v

operation sigSIGSTOP
output sigSIGSTOP Result CSignedInt32 Void
memory sigSIGSTOP heap no
async sigSIGSTOP no
purpose sigSIGSTOP "SIGSTOP (19)."
label start
const v CSignedInt32 19
returnOk v

operation sigSIGTSTP
output sigSIGTSTP Result CSignedInt32 Void
memory sigSIGTSTP heap no
async sigSIGTSTP no
purpose sigSIGTSTP "SIGTSTP (20)."
label start
const v CSignedInt32 20
returnOk v

operation sigSIGTTIN
output sigSIGTTIN Result CSignedInt32 Void
memory sigSIGTTIN heap no
async sigSIGTTIN no
purpose sigSIGTTIN "SIGTTIN (21)."
label start
const v CSignedInt32 21
returnOk v

operation sigSIGTTOU
output sigSIGTTOU Result CSignedInt32 Void
memory sigSIGTTOU heap no
async sigSIGTTOU no
purpose sigSIGTTOU "SIGTTOU (22)."
label start
const v CSignedInt32 22
returnOk v

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test extra signal accessors. Prints OK."
label startMain
call s1 sigSIGKILL
run s1
bindOk s1Res CSignedInt32 s1
const nine CSignedInt32 9
call s1Check math.equalI64
arg s1Check left s1Res
arg s1Check right nine
run s1Check
bind s1Ok Bool s1Check
branchIf s1Ok s1Lbl
branch testFailed
label s1Lbl
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
