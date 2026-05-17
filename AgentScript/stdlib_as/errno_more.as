project StdErrnoMoreSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: extended POSIX errno values.
#
# Operations:
#   tryAgainErrorNumber, badFileDescriptorErrorNumber, resourceBusyErrorNumber, noChildProcessErrorNumber, deadlockWouldOccurErrorNumber,
#   mathDomainErrorNumber, illegalByteSequenceErrorNumber, tooManySymbolicLinksErrorNumber, tooManyLinksErrorNumber, nameTooLongErrorNumber,
#   noSuchDeviceErrorNumber, execFormatErrorNumber, noLockAvailableErrorNumber, functionNotImplementedErrorNumber, errENOTBLK,
#   directoryNotEmptyErrorNumber, errENOTSOCK, inappropriateIoctlErrorNumber, readOnlyFileSystemErrorNumber, errEWOULDBLOCK,
#   crossDeviceLinkErrorNumber, errEMSGSIZE, errENETUNREACH, operationTimedOutErrorNumber.
# ============================================================

operation tryAgainErrorNumber
output tryAgainErrorNumber Result CSignedInt32 Void
memory tryAgainErrorNumber heap no
async tryAgainErrorNumber no
purpose tryAgainErrorNumber "EAGAIN (11)."
label start
const v CSignedInt32 11
returnOk v

operation badFileDescriptorErrorNumber
output badFileDescriptorErrorNumber Result CSignedInt32 Void
memory badFileDescriptorErrorNumber heap no
async badFileDescriptorErrorNumber no
purpose badFileDescriptorErrorNumber "EBADF (9)."
label start
const v CSignedInt32 9
returnOk v

operation resourceBusyErrorNumber
output resourceBusyErrorNumber Result CSignedInt32 Void
memory resourceBusyErrorNumber heap no
async resourceBusyErrorNumber no
purpose resourceBusyErrorNumber "EBUSY (16)."
label start
const v CSignedInt32 16
returnOk v

operation noChildProcessErrorNumber
output noChildProcessErrorNumber Result CSignedInt32 Void
memory noChildProcessErrorNumber heap no
async noChildProcessErrorNumber no
purpose noChildProcessErrorNumber "ECHILD (10)."
label start
const v CSignedInt32 10
returnOk v

operation deadlockWouldOccurErrorNumber
output deadlockWouldOccurErrorNumber Result CSignedInt32 Void
memory deadlockWouldOccurErrorNumber heap no
async deadlockWouldOccurErrorNumber no
purpose deadlockWouldOccurErrorNumber "EDEADLK (35)."
label start
const v CSignedInt32 35
returnOk v

operation mathDomainErrorNumber
output mathDomainErrorNumber Result CSignedInt32 Void
memory mathDomainErrorNumber heap no
async mathDomainErrorNumber no
purpose mathDomainErrorNumber "EDOM (33)."
label start
const v CSignedInt32 33
returnOk v

operation illegalByteSequenceErrorNumber
output illegalByteSequenceErrorNumber Result CSignedInt32 Void
memory illegalByteSequenceErrorNumber heap no
async illegalByteSequenceErrorNumber no
purpose illegalByteSequenceErrorNumber "EILSEQ (84)."
label start
const v CSignedInt32 84
returnOk v

operation tooManySymbolicLinksErrorNumber
output tooManySymbolicLinksErrorNumber Result CSignedInt32 Void
memory tooManySymbolicLinksErrorNumber heap no
async tooManySymbolicLinksErrorNumber no
purpose tooManySymbolicLinksErrorNumber "ELOOP (40)."
label start
const v CSignedInt32 40
returnOk v

operation tooManyLinksErrorNumber
output tooManyLinksErrorNumber Result CSignedInt32 Void
memory tooManyLinksErrorNumber heap no
async tooManyLinksErrorNumber no
purpose tooManyLinksErrorNumber "EMLINK (31)."
label start
const v CSignedInt32 31
returnOk v

operation nameTooLongErrorNumber
output nameTooLongErrorNumber Result CSignedInt32 Void
memory nameTooLongErrorNumber heap no
async nameTooLongErrorNumber no
purpose nameTooLongErrorNumber "ENAMETOOLONG (36)."
label start
const v CSignedInt32 36
returnOk v

operation noSuchDeviceErrorNumber
output noSuchDeviceErrorNumber Result CSignedInt32 Void
memory noSuchDeviceErrorNumber heap no
async noSuchDeviceErrorNumber no
purpose noSuchDeviceErrorNumber "ENODEV (19)."
label start
const v CSignedInt32 19
returnOk v

operation execFormatErrorNumber
output execFormatErrorNumber Result CSignedInt32 Void
memory execFormatErrorNumber heap no
async execFormatErrorNumber no
purpose execFormatErrorNumber "ENOEXEC (8)."
label start
const v CSignedInt32 8
returnOk v

operation noLockAvailableErrorNumber
output noLockAvailableErrorNumber Result CSignedInt32 Void
memory noLockAvailableErrorNumber heap no
async noLockAvailableErrorNumber no
purpose noLockAvailableErrorNumber "ENOLCK (37)."
label start
const v CSignedInt32 37
returnOk v

operation functionNotImplementedErrorNumber
output functionNotImplementedErrorNumber Result CSignedInt32 Void
memory functionNotImplementedErrorNumber heap no
async functionNotImplementedErrorNumber no
purpose functionNotImplementedErrorNumber "ENOSYS (38)."
label start
const v CSignedInt32 38
returnOk v

operation directoryNotEmptyErrorNumber
output directoryNotEmptyErrorNumber Result CSignedInt32 Void
memory directoryNotEmptyErrorNumber heap no
async directoryNotEmptyErrorNumber no
purpose directoryNotEmptyErrorNumber "ENOTEMPTY (39)."
label start
const v CSignedInt32 39
returnOk v

operation notDirectoryErrorNumber
output notDirectoryErrorNumber Result CSignedInt32 Void
memory notDirectoryErrorNumber heap no
async notDirectoryErrorNumber no
purpose notDirectoryErrorNumber "ENOTDIR (20)."
label start
const v CSignedInt32 20
returnOk v

operation isDirectoryErrorNumber
output isDirectoryErrorNumber Result CSignedInt32 Void
memory isDirectoryErrorNumber heap no
async isDirectoryErrorNumber no
purpose isDirectoryErrorNumber "EISDIR (21)."
label start
const v CSignedInt32 21
returnOk v

operation tooManyOpenFilesErrorNumber
output tooManyOpenFilesErrorNumber Result CSignedInt32 Void
memory tooManyOpenFilesErrorNumber heap no
async tooManyOpenFilesErrorNumber no
purpose tooManyOpenFilesErrorNumber "EMFILE (24)."
label start
const v CSignedInt32 24
returnOk v

operation inappropriateIoctlErrorNumber
output inappropriateIoctlErrorNumber Result CSignedInt32 Void
memory inappropriateIoctlErrorNumber heap no
async inappropriateIoctlErrorNumber no
purpose inappropriateIoctlErrorNumber "ENOTTY (25)."
label start
const v CSignedInt32 25
returnOk v

operation readOnlyFileSystemErrorNumber
output readOnlyFileSystemErrorNumber Result CSignedInt32 Void
memory readOnlyFileSystemErrorNumber heap no
async readOnlyFileSystemErrorNumber no
purpose readOnlyFileSystemErrorNumber "EROFS (30)."
label start
const v CSignedInt32 30
returnOk v

operation crossDeviceLinkErrorNumber
output crossDeviceLinkErrorNumber Result CSignedInt32 Void
memory crossDeviceLinkErrorNumber heap no
async crossDeviceLinkErrorNumber no
purpose crossDeviceLinkErrorNumber "EXDEV (18)."
label start
const v CSignedInt32 18
returnOk v

operation operationTimedOutErrorNumber
output operationTimedOutErrorNumber Result CSignedInt32 Void
memory operationTimedOutErrorNumber heap no
async operationTimedOutErrorNumber no
purpose operationTimedOutErrorNumber "ETIMEDOUT (110)."
label start
const v CSignedInt32 110
returnOk v

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test extra errno accessors. Prints OK."
label startMain
call s1 tryAgainErrorNumber
run s1
bindOk s1Res CSignedInt32 s1
const eleven CSignedInt32 11
call s1Check math.equalI64
arg s1Check left s1Res
arg s1Check right eleven
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
