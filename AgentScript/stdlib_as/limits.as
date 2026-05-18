# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <limits.h>-style numeric limits
# ============================================================
#
# # rationale: C's <limits.h> is a wall of preprocessor `#define`s
#   for integer-type bounds. AgentScript has no macros, so the
#   pre-refined version exposed each bound as a zero-arg operation
#   returning `Result CSignedInt64 Void`. The refined surface
#   replaces the operations with module-scope `domainLiteral`
#   constants — AST §2.12.5's purpose-built verb for typed
#   compile-time values. Every bound is constant-folded by LLVM
#   and carries a `domainLiteralSource` pointer back to the ISO C
#   spec for provenance.
#
# # invariant: every limit matches ISO C99 §5.2.4.2.1 for its width
#   on a two's-complement target. AgentScript targets two's
#   complement exclusively (LLVM IR does not model sign-magnitude
#   or one's-complement representations).
#
# # security: pure constants. No effects. No allocation.
#
# # timing: zero — every reference inlines.
#
# # observability: nothing to observe at runtime.

project StdLimitsSelfTest
target console
runtime AgentRuntime 0.1
entry console main

error MainError
errorCase MainError LimitsSmokeAssertionFailed
errorCase MainError ConsoleWriteFailed

# section capability
# rationale: smoke-test main writes a single OK line to stdout.
capability stdoutWriteCapability console.stdout write

# section limits.signed8
domainLiteral maximumSignedInt8Value CSignedInt64 127
domainLiteralSource maximumSignedInt8Value isoC99.INT8_MAX
domainLiteralTrust maximumSignedInt8Value trustedStaticLiteral
domainLiteralValidation maximumSignedInt8Value trustedAbiConstant

domainLiteral minimumSignedInt8Value CSignedInt64 -128
domainLiteralSource minimumSignedInt8Value isoC99.INT8_MIN
domainLiteralTrust minimumSignedInt8Value trustedStaticLiteral
domainLiteralValidation minimumSignedInt8Value trustedAbiConstant

domainLiteral maximumUnsignedInt8Value CSignedInt64 255
domainLiteralSource maximumUnsignedInt8Value isoC99.UINT8_MAX
domainLiteralTrust maximumUnsignedInt8Value trustedStaticLiteral
domainLiteralValidation maximumUnsignedInt8Value trustedAbiConstant

# section limits.signed16
domainLiteral maximumSignedInt16Value CSignedInt64 32767
domainLiteralSource maximumSignedInt16Value isoC99.INT16_MAX
domainLiteralTrust maximumSignedInt16Value trustedStaticLiteral
domainLiteralValidation maximumSignedInt16Value trustedAbiConstant

domainLiteral minimumSignedInt16Value CSignedInt64 -32768
domainLiteralSource minimumSignedInt16Value isoC99.INT16_MIN
domainLiteralTrust minimumSignedInt16Value trustedStaticLiteral
domainLiteralValidation minimumSignedInt16Value trustedAbiConstant

domainLiteral maximumUnsignedInt16Value CSignedInt64 65535
domainLiteralSource maximumUnsignedInt16Value isoC99.UINT16_MAX
domainLiteralTrust maximumUnsignedInt16Value trustedStaticLiteral
domainLiteralValidation maximumUnsignedInt16Value trustedAbiConstant

# section limits.signed32
domainLiteral maximumSignedInt32Value CSignedInt64 2147483647
domainLiteralSource maximumSignedInt32Value isoC99.INT32_MAX
domainLiteralTrust maximumSignedInt32Value trustedStaticLiteral
domainLiteralValidation maximumSignedInt32Value trustedAbiConstant

domainLiteral minimumSignedInt32Value CSignedInt64 -2147483648
domainLiteralSource minimumSignedInt32Value isoC99.INT32_MIN
domainLiteralTrust minimumSignedInt32Value trustedStaticLiteral
domainLiteralValidation minimumSignedInt32Value trustedAbiConstant

domainLiteral maximumUnsignedInt32Value CSignedInt64 4294967295
domainLiteralSource maximumUnsignedInt32Value isoC99.UINT32_MAX
domainLiteralTrust maximumUnsignedInt32Value trustedStaticLiteral
domainLiteralValidation maximumUnsignedInt32Value trustedAbiConstant

# section limits.signed64
domainLiteral maximumSignedInt64Value CSignedInt64 9223372036854775807
domainLiteralSource maximumSignedInt64Value isoC99.INT64_MAX
domainLiteralTrust maximumSignedInt64Value trustedStaticLiteral
domainLiteralValidation maximumSignedInt64Value trustedAbiConstant

# # warning: INT64_MIN (-9223372036854775808) cannot be expressed
#   as a positive literal in any base-10 representation that fits
#   inside an i64 — the parser would see 9223372036854775808 first,
#   which overflows. Callers needing INT64_MIN should compute it
#   from maximumSignedInt64Value via `negate(max) - 1`.

# section limits.platform
domainLiteral bitCountPerByte CSignedInt64 8
domainLiteralSource bitCountPerByte isoC99.CHAR_BIT
domainLiteralTrust bitCountPerByte trustedStaticLiteral
domainLiteralValidation bitCountPerByte trustedAbiConstant

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
purpose main "Verify a representative subset of the numeric-limit constants resolves correctly."
invariant main "INT8_MAX == 127, INT32_MAX == 2147483647, CHAR_BIT == 8."

label startMain

const oneHundredTwentySeven CSignedInt64 127
call checkInt8MaxCall math.equalI64
arg checkInt8MaxCall left maximumSignedInt8Value
arg checkInt8MaxCall right oneHundredTwentySeven
run checkInt8MaxCall
bind int8MaxOk Bool checkInt8MaxCall
branchIf int8MaxOk int8MaxHolds
branch smokeAssertionFailed
label int8MaxHolds

const twoToThirtyOneMinusOne CSignedInt64 2147483647
call checkInt32MaxCall math.equalI64
arg checkInt32MaxCall left maximumSignedInt32Value
arg checkInt32MaxCall right twoToThirtyOneMinusOne
run checkInt32MaxCall
bind int32MaxOk Bool checkInt32MaxCall
branchIf int32MaxOk int32MaxHolds
branch smokeAssertionFailed
label int32MaxHolds

const eightBits CSignedInt64 8
call checkCharBitCall math.equalI64
arg checkCharBitCall left bitCountPerByte
arg checkCharBitCall right eightBits
run checkCharBitCall
bind charBitOk Bool checkCharBitCall
branchIf charBitOk charBitHolds
branch smokeAssertionFailed
label charBitHolds

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
makeError limitsSmokeFailure MainError.LimitsSmokeAssertionFailed
returnError limitsSmokeFailure
