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
#   hangupSignalNumber, quitSignalNumber, traceTrapSignalNumber, busErrorSignalNumber, killSignalNumber,
#   userSignalOneNumber, userSignalTwoNumber, brokenPipeSignalNumber, alarmSignalNumber, childStatusChangedSignalNumber,
#   continueSignalNumber, stopSignalNumber, terminalStopSignalNumber, terminalInputSignalNumber, terminalOutputSignalNumber.
# ============================================================

operation hangupSignalNumber
output hangupSignalNumber Result CSignedInt32 Void
memory hangupSignalNumber heap no
async hangupSignalNumber no
purpose hangupSignalNumber "SIGHUP (1)."
label start
const v CSignedInt32 1
returnOk v

operation quitSignalNumber
output quitSignalNumber Result CSignedInt32 Void
memory quitSignalNumber heap no
async quitSignalNumber no
purpose quitSignalNumber "SIGQUIT (3)."
label start
const v CSignedInt32 3
returnOk v

operation traceTrapSignalNumber
output traceTrapSignalNumber Result CSignedInt32 Void
memory traceTrapSignalNumber heap no
async traceTrapSignalNumber no
purpose traceTrapSignalNumber "SIGTRAP (5)."
label start
const v CSignedInt32 5
returnOk v

operation busErrorSignalNumber
output busErrorSignalNumber Result CSignedInt32 Void
memory busErrorSignalNumber heap no
async busErrorSignalNumber no
purpose busErrorSignalNumber "SIGBUS (7)."
label start
const v CSignedInt32 7
returnOk v

operation killSignalNumber
output killSignalNumber Result CSignedInt32 Void
memory killSignalNumber heap no
async killSignalNumber no
purpose killSignalNumber "SIGKILL (9)."
label start
const v CSignedInt32 9
returnOk v

operation userSignalOneNumber
output userSignalOneNumber Result CSignedInt32 Void
memory userSignalOneNumber heap no
async userSignalOneNumber no
purpose userSignalOneNumber "SIGUSR1 (10)."
label start
const v CSignedInt32 10
returnOk v

operation userSignalTwoNumber
output userSignalTwoNumber Result CSignedInt32 Void
memory userSignalTwoNumber heap no
async userSignalTwoNumber no
purpose userSignalTwoNumber "SIGUSR2 (12)."
label start
const v CSignedInt32 12
returnOk v

operation brokenPipeSignalNumber
output brokenPipeSignalNumber Result CSignedInt32 Void
memory brokenPipeSignalNumber heap no
async brokenPipeSignalNumber no
purpose brokenPipeSignalNumber "SIGPIPE (13)."
label start
const v CSignedInt32 13
returnOk v

operation alarmSignalNumber
output alarmSignalNumber Result CSignedInt32 Void
memory alarmSignalNumber heap no
async alarmSignalNumber no
purpose alarmSignalNumber "SIGALRM (14)."
label start
const v CSignedInt32 14
returnOk v

operation childStatusChangedSignalNumber
output childStatusChangedSignalNumber Result CSignedInt32 Void
memory childStatusChangedSignalNumber heap no
async childStatusChangedSignalNumber no
purpose childStatusChangedSignalNumber "SIGCHLD (17)."
label start
const v CSignedInt32 17
returnOk v

operation continueSignalNumber
output continueSignalNumber Result CSignedInt32 Void
memory continueSignalNumber heap no
async continueSignalNumber no
purpose continueSignalNumber "SIGCONT (18)."
label start
const v CSignedInt32 18
returnOk v

operation stopSignalNumber
output stopSignalNumber Result CSignedInt32 Void
memory stopSignalNumber heap no
async stopSignalNumber no
purpose stopSignalNumber "SIGSTOP (19)."
label start
const v CSignedInt32 19
returnOk v

operation terminalStopSignalNumber
output terminalStopSignalNumber Result CSignedInt32 Void
memory terminalStopSignalNumber heap no
async terminalStopSignalNumber no
purpose terminalStopSignalNumber "SIGTSTP (20)."
label start
const v CSignedInt32 20
returnOk v

operation terminalInputSignalNumber
output terminalInputSignalNumber Result CSignedInt32 Void
memory terminalInputSignalNumber heap no
async terminalInputSignalNumber no
purpose terminalInputSignalNumber "SIGTTIN (21)."
label start
const v CSignedInt32 21
returnOk v

operation terminalOutputSignalNumber
output terminalOutputSignalNumber Result CSignedInt32 Void
memory terminalOutputSignalNumber heap no
async terminalOutputSignalNumber no
purpose terminalOutputSignalNumber "SIGTTOU (22)."
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
call s1 killSignalNumber
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
