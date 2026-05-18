# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: POSIX errno numbers + message lookup
# ============================================================
#
# # rationale: C's <errno.h> exposes EPERM/ENOENT/etc. as
#   preprocessor `#define`s. The refined surface replaces every
#   zero-arg accessor with a module-scope `domainLiteral` and keeps
#   the `lookupErrnoMessageCString` chain (a real string-mapping
#   operation with branching logic) as an `operation`.
#
# # invariant: every errno value matches the canonical POSIX number.
#   Messages are short English text, ASCII-only, NUL-terminated.
#
# # security: pure value-level mapping; no I/O; no allocation.
#
# # timing: accessors are O(0). The message lookup is O(K) where K
#   is the number of known codes (currently 13); a code that is
#   not in the table maps to the "unknown error" sentinel.
#
# # observability: no logs; callers wrap when needed.

project StdErrno
target console
runtime AgentRuntime 0.1
entry console lookupErrnoMessageCString

# This is a pure-module (library) file: it exports operations and
# domainLiterals consumed by other programs (notably
# stdlib_as/errno.test.as which importModules it and runs the
# smoke). The project / target / runtime / entry block is retained
# so the module can still be linted standalone — the entry just
# points at the first exported operation rather than a `main` smoke.

# section errno.numbers
# rationale: POSIX errno constants.

domainLiteral permissionDeniedErrorNumber CSignedInt32 1
domainLiteralSource permissionDeniedErrorNumber posix.EPERM
domainLiteralTrust permissionDeniedErrorNumber trustedStaticLiteral

domainLiteral fileNotFoundErrorNumber CSignedInt32 2
domainLiteralSource fileNotFoundErrorNumber posix.ENOENT
domainLiteralTrust fileNotFoundErrorNumber trustedStaticLiteral

domainLiteral processNotFoundErrorNumber CSignedInt32 3
domainLiteralSource processNotFoundErrorNumber posix.ESRCH
domainLiteralTrust processNotFoundErrorNumber trustedStaticLiteral

domainLiteral interruptedSystemCallErrorNumber CSignedInt32 4
domainLiteralSource interruptedSystemCallErrorNumber posix.EINTR
domainLiteralTrust interruptedSystemCallErrorNumber trustedStaticLiteral

domainLiteral inputOutputErrorNumber CSignedInt32 5
domainLiteralSource inputOutputErrorNumber posix.EIO
domainLiteralTrust inputOutputErrorNumber trustedStaticLiteral

domainLiteral outOfMemoryErrorNumber CSignedInt32 12
domainLiteralSource outOfMemoryErrorNumber posix.ENOMEM
domainLiteralTrust outOfMemoryErrorNumber trustedStaticLiteral

domainLiteral accessDeniedErrorNumber CSignedInt32 13
domainLiteralSource accessDeniedErrorNumber posix.EACCES
domainLiteralTrust accessDeniedErrorNumber trustedStaticLiteral

domainLiteral badAddressErrorNumber CSignedInt32 14
domainLiteralSource badAddressErrorNumber posix.EFAULT
domainLiteralTrust badAddressErrorNumber trustedStaticLiteral

domainLiteral fileAlreadyExistsErrorNumber CSignedInt32 17
domainLiteralSource fileAlreadyExistsErrorNumber posix.EEXIST
domainLiteralTrust fileAlreadyExistsErrorNumber trustedStaticLiteral

domainLiteral invalidArgumentErrorNumber CSignedInt32 22
domainLiteralSource invalidArgumentErrorNumber posix.EINVAL
domainLiteralTrust invalidArgumentErrorNumber trustedStaticLiteral

domainLiteral noSpaceLeftOnDeviceErrorNumber CSignedInt32 28
domainLiteralSource noSpaceLeftOnDeviceErrorNumber posix.ENOSPC
domainLiteralTrust noSpaceLeftOnDeviceErrorNumber trustedStaticLiteral

domainLiteral brokenPipeErrorNumber CSignedInt32 32
domainLiteralSource brokenPipeErrorNumber posix.EPIPE
domainLiteralTrust brokenPipeErrorNumber trustedStaticLiteral

domainLiteral resultOutOfRangeErrorNumber CSignedInt32 34
domainLiteralSource resultOutOfRangeErrorNumber posix.ERANGE
domainLiteralTrust resultOutOfRangeErrorNumber trustedStaticLiteral

# section errno.messageLookup

operation lookupErrnoMessageCString
input lookupErrnoMessageCString errorNumber CSignedInt32
output lookupErrnoMessageCString CNullTerminatedByteString
memoryHeap lookupErrnoMessageCString no
async lookupErrnoMessageCString no
purpose lookupErrnoMessageCString "Map a POSIX errno number to a short English text description; returns 'unknown error' for codes outside the known set."
invariant lookupErrnoMessageCString "Output is always non-empty NUL-terminated ASCII."
guarantee lookupErrnoMessageCString "Total — every input produces some message."
# rationale: pure-AS comparison chain — no libc strerror dependency
#   (strerror is not thread-safe in all libcs and would pull in extra
#   FFI metadata for one short helper).
label startLookupErrnoMessageCString
const messageForPermissionDenied CNullTerminatedByteString "operation not permitted"
const messageForFileNotFound CNullTerminatedByteString "no such file or directory"
const messageForProcessNotFound CNullTerminatedByteString "no such process"
const messageForInterruptedSystemCall CNullTerminatedByteString "interrupted system call"
const messageForInputOutputError CNullTerminatedByteString "input/output error"
const messageForOutOfMemory CNullTerminatedByteString "out of memory"
const messageForAccessDenied CNullTerminatedByteString "permission denied"
const messageForBadAddress CNullTerminatedByteString "bad address"
const messageForFileAlreadyExists CNullTerminatedByteString "file exists"
const messageForInvalidArgument CNullTerminatedByteString "invalid argument"
const messageForNoSpaceLeftOnDevice CNullTerminatedByteString "no space left on device"
const messageForBrokenPipe CNullTerminatedByteString "broken pipe"
const messageForResultOutOfRange CNullTerminatedByteString "result out of range"
const messageForUnknownErrorCode CNullTerminatedByteString "unknown error"

call detectIsPermissionDeniedCall math.equalI64
arg detectIsPermissionDeniedCall left errorNumber
arg detectIsPermissionDeniedCall right permissionDeniedErrorNumber
run detectIsPermissionDeniedCall
bind isPermissionDenied Bool detectIsPermissionDeniedCall
branchIf isPermissionDenied returnPermissionDeniedMessage
call detectIsFileNotFoundCall math.equalI64
arg detectIsFileNotFoundCall left errorNumber
arg detectIsFileNotFoundCall right fileNotFoundErrorNumber
run detectIsFileNotFoundCall
bind isFileNotFound Bool detectIsFileNotFoundCall
branchIf isFileNotFound returnFileNotFoundMessage
call detectIsProcessNotFoundCall math.equalI64
arg detectIsProcessNotFoundCall left errorNumber
arg detectIsProcessNotFoundCall right processNotFoundErrorNumber
run detectIsProcessNotFoundCall
bind isProcessNotFound Bool detectIsProcessNotFoundCall
branchIf isProcessNotFound returnProcessNotFoundMessage
call detectIsInterruptedSystemCallCall math.equalI64
arg detectIsInterruptedSystemCallCall left errorNumber
arg detectIsInterruptedSystemCallCall right interruptedSystemCallErrorNumber
run detectIsInterruptedSystemCallCall
bind isInterruptedSystemCall Bool detectIsInterruptedSystemCallCall
branchIf isInterruptedSystemCall returnInterruptedSystemCallMessage
call detectIsInputOutputErrorCall math.equalI64
arg detectIsInputOutputErrorCall left errorNumber
arg detectIsInputOutputErrorCall right inputOutputErrorNumber
run detectIsInputOutputErrorCall
bind isInputOutputError Bool detectIsInputOutputErrorCall
branchIf isInputOutputError returnInputOutputErrorMessage
call detectIsOutOfMemoryCall math.equalI64
arg detectIsOutOfMemoryCall left errorNumber
arg detectIsOutOfMemoryCall right outOfMemoryErrorNumber
run detectIsOutOfMemoryCall
bind isOutOfMemory Bool detectIsOutOfMemoryCall
branchIf isOutOfMemory returnOutOfMemoryMessage
call detectIsAccessDeniedCall math.equalI64
arg detectIsAccessDeniedCall left errorNumber
arg detectIsAccessDeniedCall right accessDeniedErrorNumber
run detectIsAccessDeniedCall
bind isAccessDenied Bool detectIsAccessDeniedCall
branchIf isAccessDenied returnAccessDeniedMessage
call detectIsBadAddressCall math.equalI64
arg detectIsBadAddressCall left errorNumber
arg detectIsBadAddressCall right badAddressErrorNumber
run detectIsBadAddressCall
bind isBadAddress Bool detectIsBadAddressCall
branchIf isBadAddress returnBadAddressMessage
call detectIsFileAlreadyExistsCall math.equalI64
arg detectIsFileAlreadyExistsCall left errorNumber
arg detectIsFileAlreadyExistsCall right fileAlreadyExistsErrorNumber
run detectIsFileAlreadyExistsCall
bind isFileAlreadyExists Bool detectIsFileAlreadyExistsCall
branchIf isFileAlreadyExists returnFileAlreadyExistsMessage
call detectIsInvalidArgumentCall math.equalI64
arg detectIsInvalidArgumentCall left errorNumber
arg detectIsInvalidArgumentCall right invalidArgumentErrorNumber
run detectIsInvalidArgumentCall
bind isInvalidArgument Bool detectIsInvalidArgumentCall
branchIf isInvalidArgument returnInvalidArgumentMessage
call detectIsNoSpaceLeftOnDeviceCall math.equalI64
arg detectIsNoSpaceLeftOnDeviceCall left errorNumber
arg detectIsNoSpaceLeftOnDeviceCall right noSpaceLeftOnDeviceErrorNumber
run detectIsNoSpaceLeftOnDeviceCall
bind isNoSpaceLeftOnDevice Bool detectIsNoSpaceLeftOnDeviceCall
branchIf isNoSpaceLeftOnDevice returnNoSpaceLeftOnDeviceMessage
call detectIsBrokenPipeCall math.equalI64
arg detectIsBrokenPipeCall left errorNumber
arg detectIsBrokenPipeCall right brokenPipeErrorNumber
run detectIsBrokenPipeCall
bind isBrokenPipe Bool detectIsBrokenPipeCall
branchIf isBrokenPipe returnBrokenPipeMessage
call detectIsResultOutOfRangeCall math.equalI64
arg detectIsResultOutOfRangeCall left errorNumber
arg detectIsResultOutOfRangeCall right resultOutOfRangeErrorNumber
run detectIsResultOutOfRangeCall
bind isResultOutOfRange Bool detectIsResultOutOfRangeCall
branchIf isResultOutOfRange returnResultOutOfRangeMessage
returnValue messageForUnknownErrorCode
label returnPermissionDeniedMessage
returnValue messageForPermissionDenied
label returnFileNotFoundMessage
returnValue messageForFileNotFound
label returnProcessNotFoundMessage
returnValue messageForProcessNotFound
label returnInterruptedSystemCallMessage
returnValue messageForInterruptedSystemCall
label returnInputOutputErrorMessage
returnValue messageForInputOutputError
label returnOutOfMemoryMessage
returnValue messageForOutOfMemory
label returnAccessDeniedMessage
returnValue messageForAccessDenied
label returnBadAddressMessage
returnValue messageForBadAddress
label returnFileAlreadyExistsMessage
returnValue messageForFileAlreadyExists
label returnInvalidArgumentMessage
returnValue messageForInvalidArgument
label returnNoSpaceLeftOnDeviceMessage
returnValue messageForNoSpaceLeftOnDevice
label returnBrokenPipeMessage
returnValue messageForBrokenPipe
label returnResultOutOfRangeMessage
returnValue messageForResultOutOfRange
