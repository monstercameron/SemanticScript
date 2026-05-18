# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: POSIX signal numbers + raise
# ============================================================
#
# # rationale: C's <signal.h> exposes SIGABRT, SIGFPE, SIGILL,
#   SIGINT, SIGSEGV, SIGTERM as preprocessor `#define`s plus
#   raise(int) for self-delivery. The refined surface replaces the
#   zero-arg accessor operations with module-scope `domainLiteral`
#   constants and keeps `raiseProcessSignalNumber` as a real
#   operation (it has an effect: write process.signal).
#
# # invariant: every signal number matches the canonical POSIX
#   value as documented in IEEE Std 1003.1.
#
# # security: raising a signal can terminate the process. The
#   effect declaration on raiseProcessSignalNumber surfaces that
#   risk so the lint can flag any unauthorized call site.
#
# # timing: signal accessors are O(0) (constant-folded);
#   raiseProcessSignalNumber yields to the OS scheduler.
#
# # observability: c.raise return value is propagated as a typed
#   SignalDeliveryError variant rather than the C convention of
#   "non-zero means failure".

project StdSignalSelfTest
target console
runtime AgentRuntime 0.1
entry console main

# Typed error domain for signal delivery.
error SignalDeliveryError
errorCase SignalDeliveryError DeliveryFailed
errorCase SignalDeliveryError UnknownSignalNumber

error MainError
errorCase MainError SignalSmokeAssertionFailed

# section signal.numbers
# rationale: POSIX signal-number constants.

domainLiteral abortSignalNumber CSignedInt32 6
domainLiteralSource abortSignalNumber posix.SIGABRT
domainLiteralTrust abortSignalNumber trustedStaticLiteral
domainLiteralValidation abortSignalNumber trustedAbiConstant

domainLiteral floatingPointExceptionSignalNumber CSignedInt32 8
domainLiteralSource floatingPointExceptionSignalNumber posix.SIGFPE
domainLiteralTrust floatingPointExceptionSignalNumber trustedStaticLiteral

domainLiteral illegalInstructionSignalNumber CSignedInt32 4
domainLiteralSource illegalInstructionSignalNumber posix.SIGILL
domainLiteralTrust illegalInstructionSignalNumber trustedStaticLiteral

domainLiteral interruptSignalNumber CSignedInt32 2
domainLiteralSource interruptSignalNumber posix.SIGINT
domainLiteralTrust interruptSignalNumber trustedStaticLiteral

domainLiteral segmentationViolationSignalNumber CSignedInt32 11
domainLiteralSource segmentationViolationSignalNumber posix.SIGSEGV
domainLiteralTrust segmentationViolationSignalNumber trustedStaticLiteral

domainLiteral terminationSignalNumber CSignedInt32 15
domainLiteralSource terminationSignalNumber posix.SIGTERM
domainLiteralTrust terminationSignalNumber trustedStaticLiteral

# section signal.raise
# rationale: deliver a signal to the current process.

operation raiseProcessSignalNumber
input raiseProcessSignalNumber signalNumber CSignedInt32
output raiseProcessSignalNumber Result CSignedInt32 SignalDeliveryError
effect raiseProcessSignalNumber write process.signal
memoryHeap raiseProcessSignalNumber no
async raiseProcessSignalNumber no
purpose raiseProcessSignalNumber "Deliver the given POSIX signal to this process via libc raise()."
invariant raiseProcessSignalNumber "On success returns 0; on failure returns SignalDeliveryError.DeliveryFailed."
failure raiseProcessSignalNumber DeliveryFailed "Returned when libc raise() reports a non-zero status — typically when signalNumber is out of range."
warning raiseProcessSignalNumber "May terminate the process if the signal's default disposition is fatal and no handler is installed via c.signal."
guarantee raiseProcessSignalNumber "Always returns OR terminates; never hangs."

label startRaiseProcessSignalNumber
call deliverSignalCall c.raise
arg deliverSignalCall sig signalNumber
run deliverSignalCall
bind raiseLibcResultCode CSignedInt32 deliverSignalCall
const zeroSuccessCode CSignedInt32 0
call detectRaiseSuccessCall math.equalI64
arg detectRaiseSuccessCall left raiseLibcResultCode
arg detectRaiseSuccessCall right zeroSuccessCode
run detectRaiseSuccessCall
bind raiseSucceeded Bool detectRaiseSuccessCall
branchIf raiseSucceeded returnRaiseSuccess
makeError signalDeliveryFailure SignalDeliveryError.DeliveryFailed
returnError signalDeliveryFailure
label returnRaiseSuccess
returnOk zeroSuccessCode

# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memoryHeap main no
async main no
purpose main "Verify signal-number constants resolve to expected POSIX values."
invariant main "SIGINT == 2, SIGTERM == 15."

label startMain

const interruptExpectedValue CSignedInt32 2
call checkInterruptCall math.equalI64
arg checkInterruptCall left interruptSignalNumber
arg checkInterruptCall right interruptExpectedValue
run checkInterruptCall
bind interruptOk Bool checkInterruptCall
branchIf interruptOk interruptHolds
branch smokeAssertionFailed
label interruptHolds

const terminationExpectedValue CSignedInt32 15
call checkTerminationCall math.equalI64
arg checkTerminationCall left terminationSignalNumber
arg checkTerminationCall right terminationExpectedValue
run checkTerminationCall
bind terminationOk Bool checkTerminationCall
branchIf terminationOk terminationHolds
branch smokeAssertionFailed
label terminationHolds

const successMessageText CNullTerminatedByteString "OK"
call writeSuccessLineCall console.writeLine
arg writeSuccessLineCall console console
arg writeSuccessLineCall text successMessageText
run writeSuccessLineCall
ignoreOk writeSuccessLineCall Void
const exitOkCode ExitCode 0
returnOk exitOkCode

label smokeAssertionFailed
makeError signalSmokeFailure MainError.SignalSmokeAssertionFailed
returnError signalSmokeFailure
