# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: extended POSIX errno numbers
# ============================================================
#
# # rationale: errno codes beyond the headline thirteen in errno.as,
#   exposed as module-scope `domainLiteral` constants per the
#   refined-syntax pattern.
# # invariant: every value matches POSIX.
# # security: pure constants. # timing: zero. # observability: none.

project StdErrnoMoreSelfTest
target console
runtime AgentRuntime 0.1
entry console main

error MainError
errorCase MainError ErrnoMoreSmokeAssertionFailed

# section errnoMore.numbers
domainLiteral tryAgainErrorNumber CSignedInt32 11
domainLiteralSource tryAgainErrorNumber posix.EAGAIN
domainLiteralTrust tryAgainErrorNumber trustedStaticLiteral

domainLiteral badFileDescriptorErrorNumber CSignedInt32 9
domainLiteralSource badFileDescriptorErrorNumber posix.EBADF
domainLiteralTrust badFileDescriptorErrorNumber trustedStaticLiteral

domainLiteral resourceBusyErrorNumber CSignedInt32 16
domainLiteralSource resourceBusyErrorNumber posix.EBUSY
domainLiteralTrust resourceBusyErrorNumber trustedStaticLiteral

domainLiteral noChildProcessErrorNumber CSignedInt32 10
domainLiteralSource noChildProcessErrorNumber posix.ECHILD
domainLiteralTrust noChildProcessErrorNumber trustedStaticLiteral

domainLiteral deadlockWouldOccurErrorNumber CSignedInt32 35
domainLiteralSource deadlockWouldOccurErrorNumber posix.EDEADLK
domainLiteralTrust deadlockWouldOccurErrorNumber trustedStaticLiteral

domainLiteral mathDomainErrorNumber CSignedInt32 33
domainLiteralSource mathDomainErrorNumber posix.EDOM
domainLiteralTrust mathDomainErrorNumber trustedStaticLiteral

domainLiteral illegalByteSequenceErrorNumber CSignedInt32 84
domainLiteralSource illegalByteSequenceErrorNumber posix.EILSEQ
domainLiteralTrust illegalByteSequenceErrorNumber trustedStaticLiteral

domainLiteral tooManySymbolicLinksErrorNumber CSignedInt32 40
domainLiteralSource tooManySymbolicLinksErrorNumber posix.ELOOP
domainLiteralTrust tooManySymbolicLinksErrorNumber trustedStaticLiteral

domainLiteral tooManyLinksErrorNumber CSignedInt32 31
domainLiteralSource tooManyLinksErrorNumber posix.EMLINK
domainLiteralTrust tooManyLinksErrorNumber trustedStaticLiteral

domainLiteral nameTooLongErrorNumber CSignedInt32 36
domainLiteralSource nameTooLongErrorNumber posix.ENAMETOOLONG
domainLiteralTrust nameTooLongErrorNumber trustedStaticLiteral

domainLiteral noSuchDeviceErrorNumber CSignedInt32 19
domainLiteralSource noSuchDeviceErrorNumber posix.ENODEV
domainLiteralTrust noSuchDeviceErrorNumber trustedStaticLiteral

domainLiteral execFormatErrorNumber CSignedInt32 8
domainLiteralSource execFormatErrorNumber posix.ENOEXEC
domainLiteralTrust execFormatErrorNumber trustedStaticLiteral

domainLiteral noLockAvailableErrorNumber CSignedInt32 37
domainLiteralSource noLockAvailableErrorNumber posix.ENOLCK
domainLiteralTrust noLockAvailableErrorNumber trustedStaticLiteral

domainLiteral functionNotImplementedErrorNumber CSignedInt32 38
domainLiteralSource functionNotImplementedErrorNumber posix.ENOSYS
domainLiteralTrust functionNotImplementedErrorNumber trustedStaticLiteral

domainLiteral directoryNotEmptyErrorNumber CSignedInt32 39
domainLiteralSource directoryNotEmptyErrorNumber posix.ENOTEMPTY
domainLiteralTrust directoryNotEmptyErrorNumber trustedStaticLiteral

domainLiteral notDirectoryErrorNumber CSignedInt32 20
domainLiteralSource notDirectoryErrorNumber posix.ENOTDIR
domainLiteralTrust notDirectoryErrorNumber trustedStaticLiteral

domainLiteral isDirectoryErrorNumber CSignedInt32 21
domainLiteralSource isDirectoryErrorNumber posix.EISDIR
domainLiteralTrust isDirectoryErrorNumber trustedStaticLiteral

domainLiteral tooManyOpenFilesErrorNumber CSignedInt32 24
domainLiteralSource tooManyOpenFilesErrorNumber posix.EMFILE
domainLiteralTrust tooManyOpenFilesErrorNumber trustedStaticLiteral

domainLiteral inappropriateIoctlErrorNumber CSignedInt32 25
domainLiteralSource inappropriateIoctlErrorNumber posix.ENOTTY
domainLiteralTrust inappropriateIoctlErrorNumber trustedStaticLiteral

domainLiteral readOnlyFileSystemErrorNumber CSignedInt32 30
domainLiteralSource readOnlyFileSystemErrorNumber posix.EROFS
domainLiteralTrust readOnlyFileSystemErrorNumber trustedStaticLiteral

domainLiteral crossDeviceLinkErrorNumber CSignedInt32 18
domainLiteralSource crossDeviceLinkErrorNumber posix.EXDEV
domainLiteralTrust crossDeviceLinkErrorNumber trustedStaticLiteral

domainLiteral operationTimedOutErrorNumber CSignedInt32 110
domainLiteralSource operationTimedOutErrorNumber posix.ETIMEDOUT
domainLiteralTrust operationTimedOutErrorNumber trustedStaticLiteral

# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memoryHeap main no
async main no
purpose main "Verify the extended errno constants."
invariant main "EAGAIN == 11, EROFS == 30, ETIMEDOUT == 110."

label startMain

const eagainExpected CSignedInt32 11
call checkEagainCall math.equalI64
arg checkEagainCall left tryAgainErrorNumber
arg checkEagainCall right eagainExpected
run checkEagainCall
bind eagainOk Bool checkEagainCall
branchIf eagainOk eagainHolds
branch smokeAssertionFailed
label eagainHolds

const erofsExpected CSignedInt32 30
call checkErofsCall math.equalI64
arg checkErofsCall left readOnlyFileSystemErrorNumber
arg checkErofsCall right erofsExpected
run checkErofsCall
bind erofsOk Bool checkErofsCall
branchIf erofsOk erofsHolds
branch smokeAssertionFailed
label erofsHolds

const successMessageText CNullTerminatedByteString "OK"
call writeSuccessLineCall console.writeLine
arg writeSuccessLineCall console console
arg writeSuccessLineCall text successMessageText
run writeSuccessLineCall
ignoreOk writeSuccessLineCall Void
const exitOkCode ExitCode 0
returnOk exitOkCode

label smokeAssertionFailed
makeError errnoMoreSmokeFailure MainError.ErrnoMoreSmokeAssertionFailed
returnError errnoMoreSmokeFailure
