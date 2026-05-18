# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: extended POSIX signal numbers
# ============================================================
#
# # rationale: POSIX signal numbers beyond the headline six in
#   signal.as. The refined surface replaces accessor operations
#   with module-scope `domainLiteral` constants — the same shape
#   as signal.as / limits.as / constants.as.
#
# # invariant: every value matches IEEE Std 1003.1.
# # security: no effects — pure constants.
# # timing: zero — every reference inlines.
# # observability: nothing to observe at runtime.

project StdSignalMoreSelfTest
target console
runtime AgentRuntime 0.1
entry console main

error MainError
errorCase MainError SignalMoreSmokeAssertionFailed
errorCase MainError ConsoleWriteFailed

# section capability
# rationale: smoke-test main writes a single OK line to stdout.
capability stdoutWriteCapability console.stdout write

# section signalMore.numbers
domainLiteral hangupSignalNumber CSignedInt32 1
domainLiteralSource hangupSignalNumber posix.SIGHUP
domainLiteralTrust hangupSignalNumber trustedStaticLiteral

domainLiteral quitSignalNumber CSignedInt32 3
domainLiteralSource quitSignalNumber posix.SIGQUIT
domainLiteralTrust quitSignalNumber trustedStaticLiteral

domainLiteral traceTrapSignalNumber CSignedInt32 5
domainLiteralSource traceTrapSignalNumber posix.SIGTRAP
domainLiteralTrust traceTrapSignalNumber trustedStaticLiteral

domainLiteral busErrorSignalNumber CSignedInt32 7
domainLiteralSource busErrorSignalNumber posix.SIGBUS
domainLiteralTrust busErrorSignalNumber trustedStaticLiteral

domainLiteral killSignalNumber CSignedInt32 9
domainLiteralSource killSignalNumber posix.SIGKILL
domainLiteralTrust killSignalNumber trustedStaticLiteral

domainLiteral userSignalOneNumber CSignedInt32 10
domainLiteralSource userSignalOneNumber posix.SIGUSR1
domainLiteralTrust userSignalOneNumber trustedStaticLiteral

domainLiteral userSignalTwoNumber CSignedInt32 12
domainLiteralSource userSignalTwoNumber posix.SIGUSR2
domainLiteralTrust userSignalTwoNumber trustedStaticLiteral

domainLiteral brokenPipeSignalNumber CSignedInt32 13
domainLiteralSource brokenPipeSignalNumber posix.SIGPIPE
domainLiteralTrust brokenPipeSignalNumber trustedStaticLiteral

domainLiteral alarmSignalNumber CSignedInt32 14
domainLiteralSource alarmSignalNumber posix.SIGALRM
domainLiteralTrust alarmSignalNumber trustedStaticLiteral

domainLiteral childStatusChangedSignalNumber CSignedInt32 17
domainLiteralSource childStatusChangedSignalNumber posix.SIGCHLD
domainLiteralTrust childStatusChangedSignalNumber trustedStaticLiteral

domainLiteral continueSignalNumber CSignedInt32 18
domainLiteralSource continueSignalNumber posix.SIGCONT
domainLiteralTrust continueSignalNumber trustedStaticLiteral

domainLiteral stopSignalNumber CSignedInt32 19
domainLiteralSource stopSignalNumber posix.SIGSTOP
domainLiteralTrust stopSignalNumber trustedStaticLiteral

domainLiteral terminalStopSignalNumber CSignedInt32 20
domainLiteralSource terminalStopSignalNumber posix.SIGTSTP
domainLiteralTrust terminalStopSignalNumber trustedStaticLiteral

domainLiteral terminalInputSignalNumber CSignedInt32 21
domainLiteralSource terminalInputSignalNumber posix.SIGTTIN
domainLiteralTrust terminalInputSignalNumber trustedStaticLiteral

domainLiteral terminalOutputSignalNumber CSignedInt32 22
domainLiteralSource terminalOutputSignalNumber posix.SIGTTOU
domainLiteralTrust terminalOutputSignalNumber trustedStaticLiteral

# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
useCapability main stdoutWriteCapability
effect main write console.stdout
memoryHeap main no
async main no
purpose main "Verify a representative subset of the extended signal numbers."
invariant main "SIGKILL == 9, SIGHUP == 1, SIGUSR1 == 10."

label startMain

const nineExpected CSignedInt32 9
call checkKillCall math.equalI64
arg checkKillCall left killSignalNumber
arg checkKillCall right nineExpected
run checkKillCall
bind killOk Bool checkKillCall
branchIf killOk killHolds
branch smokeAssertionFailed
label killHolds

const oneExpected CSignedInt32 1
call checkHangupCall math.equalI64
arg checkHangupCall left hangupSignalNumber
arg checkHangupCall right oneExpected
run checkHangupCall
bind hangupOk Bool checkHangupCall
branchIf hangupOk hangupHolds
branch smokeAssertionFailed
label hangupHolds

const successMessageText CNullTerminatedByteString "OK"
call writeSuccessLineCall console.writeLine
arg writeSuccessLineCall console console
arg writeSuccessLineCall text successMessageText
run writeSuccessLineCall
ignoreOk writeSuccessLineCall CSignedInt32
bindError consoleWriteResultError CSignedInt32 writeSuccessLineCall
branchIfError writeSuccessLineCall consoleWriteFailedHandler
const exitOkCode ExitCode 0
returnOk exitOkCode

# Failure leg: surface the raw negative CSignedInt32 from
# console.writeLine as the cause attached to the typed
# MainError.ConsoleWriteFailed variant.
label consoleWriteFailedHandler
makeError consoleWriteFailedFailure MainError.ConsoleWriteFailed consoleWriteResultError
returnError consoleWriteFailedFailure
label smokeAssertionFailed
makeError signalMoreSmokeFailure MainError.SignalMoreSmokeAssertionFailed
returnError signalMoreSmokeFailure
