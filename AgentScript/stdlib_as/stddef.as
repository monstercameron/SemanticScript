# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <stddef.h>-style type sizing
# ============================================================
#
# # rationale: C's <stddef.h> is mostly typedefs (size_t, ptrdiff_t)
#   plus the NULL macro. AgentScript has those types natively
#   (CByteCount, COpaqueMemoryAddress, etc.) so this module only
#   exposes the few callable surfaces — sizeof-style accessors for
#   the common ABI types — as module-scope domainLiteral constants
#   per the refined-syntax pattern (AST.md §2.12.5). The previous
#   shape (zero-arg operations returning `Result CSignedInt64 Void`)
#   is removed because constants belong in domainLiteral, not in
#   operation bodies.
#
# # invariant: every byte-size constant matches the AgentScript
#   target ABI (x86-64 Windows MSVC under the current bootstrap
#   triple). Width-specific aliases (CSignedInt32 / CSignedInt64 /
#   CFloat64) carry their byte count directly in the name; the
#   module-scope literals are convenience accessors for
#   serialization / FFI code that needs to compute buffer sizes
#   from type categories.
#
# # security: pure constants. No effects. No allocation.
#
# # timing: zero — the LLVM optimizer inlines every reference.
#
# # observability: nothing to observe; consumers see only the
#   raw CSignedInt64 value.

project StdStddefSelfTest
target console
runtime AgentRuntime 0.1
entry console main

error MainError
errorCase MainError StddefSmokeAssertionFailed
errorCase MainError ConsoleWriteFailed

# section capability
# rationale: smoke-test main writes a single OK line to stdout.
capability stdoutWriteCapability console.stdout write

# section stddef.byteSizes
# rationale: byte-size constants per the target ABI (x86-64 Windows).

domainLiteral byteSizeOfOpaquePointer CSignedInt64 8
domainLiteralSource byteSizeOfOpaquePointer abi.x86_64.windows.pointerSize
domainLiteralTrust byteSizeOfOpaquePointer trustedStaticLiteral
domainLiteralValidation byteSizeOfOpaquePointer trustedAbiConstant

domainLiteral byteSizeOfSignedInt32 CSignedInt64 4
domainLiteralSource byteSizeOfSignedInt32 abi.fixedWidth.int32
domainLiteralTrust byteSizeOfSignedInt32 trustedStaticLiteral
domainLiteralValidation byteSizeOfSignedInt32 trustedAbiConstant

domainLiteral byteSizeOfSignedInt64 CSignedInt64 8
domainLiteralSource byteSizeOfSignedInt64 abi.fixedWidth.int64
domainLiteralTrust byteSizeOfSignedInt64 trustedStaticLiteral
domainLiteralValidation byteSizeOfSignedInt64 trustedAbiConstant

domainLiteral byteSizeOfFloat64 CSignedInt64 8
domainLiteralSource byteSizeOfFloat64 abi.ieee754.binary64
domainLiteralTrust byteSizeOfFloat64 trustedStaticLiteral
domainLiteralValidation byteSizeOfFloat64 trustedAbiConstant

domainLiteral byteSizeOfFloat32 CSignedInt64 4
domainLiteralSource byteSizeOfFloat32 abi.ieee754.binary32
domainLiteralTrust byteSizeOfFloat32 trustedStaticLiteral
domainLiteralValidation byteSizeOfFloat32 trustedAbiConstant

domainLiteral byteSizeOfSignedByte CSignedInt64 1
domainLiteralSource byteSizeOfSignedByte abi.fixedWidth.int8
domainLiteralTrust byteSizeOfSignedByte trustedStaticLiteral
domainLiteralValidation byteSizeOfSignedByte trustedAbiConstant

# section stddef.opaquePointers
# rationale: NULL pointer accessor; resolved at runtime via libc.

operation acquireNullOpaquePointer
output acquireNullOpaquePointer COpaqueMemoryAddress
memoryHeap acquireNullOpaquePointer no
async acquireNullOpaquePointer no
purpose acquireNullOpaquePointer "Returns the canonical NULL pointer (i8* 0)."
invariant acquireNullOpaquePointer "Result compares equal to any other NULL produced by libc."
# rationale: AgentScript lacks an explicit null pointer literal in the
#   type system, so we route through c.getenv with a deliberately
#   absent environment variable name. Every reasonable host returns
#   NULL; if a hostile host pre-sets this variable the caller will
#   observe a non-null pointer and the smoke test will fail visibly.
guarantee acquireNullOpaquePointer "Total under normal host environments."
label startAcquireNullOpaquePointer
const deliberatelyAbsentEnvName CNullTerminatedByteString "AGENTSCRIPT_DEFINITELY_NOT_SET_4D7F00"
call probeEnvironmentForNullCall c.getenv
arg probeEnvironmentForNullCall name deliberatelyAbsentEnvName
run probeEnvironmentForNullCall
bind nullPointerValue COpaqueMemoryAddress probeEnvironmentForNullCall
returnValue nullPointerValue

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
purpose main "Verify the stddef sizes resolve to expected ABI values."
invariant main "Pointer is 8 bytes; int32 is 4; int64 is 8; double is 8."

label startMain

# byteSizeOfOpaquePointer == 8
const eightExpected CSignedInt64 8
call checkPointerSizeCall math.equalI64
arg checkPointerSizeCall left byteSizeOfOpaquePointer
arg checkPointerSizeCall right eightExpected
run checkPointerSizeCall
bind pointerSizeOk Bool checkPointerSizeCall
branchIf pointerSizeOk pointerSizeHolds
branch smokeAssertionFailed
label pointerSizeHolds

# byteSizeOfSignedInt32 == 4
const fourExpected CSignedInt64 4
call checkInt32SizeCall math.equalI64
arg checkInt32SizeCall left byteSizeOfSignedInt32
arg checkInt32SizeCall right fourExpected
run checkInt32SizeCall
bind int32SizeOk Bool checkInt32SizeCall
branchIf int32SizeOk int32SizeHolds
branch smokeAssertionFailed
label int32SizeHolds

# byteSizeOfFloat64 == 8
call checkFloat64SizeCall math.equalI64
arg checkFloat64SizeCall left byteSizeOfFloat64
arg checkFloat64SizeCall right eightExpected
run checkFloat64SizeCall
bind float64SizeOk Bool checkFloat64SizeCall
branchIf float64SizeOk float64SizeHolds
branch smokeAssertionFailed
label float64SizeHolds

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
makeError stddefSmokeFailure MainError.StddefSmokeAssertionFailed
returnError stddefSmokeFailure
