project StdLimitsSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <limits.h>-style accessors.
#
# C's <limits.h> is a header full of #define constants; AgentScript
# doesn't have macros, so we expose each limit as an `operation` that
# returns the value. Inlining-aware codegen makes this zero-cost.
#
# Operations:
#   maxSignedInt8         - 127
#   minSignedInt8         - -128
#   maxUnsignedInt8       - 255
#   maxSignedInt16        - 32767
#   minSignedInt16        - -32768
#   maxUnsignedInt16      - 65535
#   maxSignedInt32        - 2147483647
#   minSignedInt32        - -2147483648
#   maxUnsignedInt32      - 4294967295
#   maxSignedInt64        - 9223372036854775807
#   minSignedInt64        - -9223372036854775808 (wraps at I64 boundary)
#   bitsPerByte           - 8
# ============================================================

operation maxSignedInt8
output maxSignedInt8 Result CSignedInt64 Void
memory maxSignedInt8 heap no
memory maxSignedInt8 stack max 1KiB
async maxSignedInt8 no
purpose maxSignedInt8 "Largest value of a signed 8-bit integer (INT8_MAX)."
label startMaxSignedInt8
const v CSignedInt64 127
returnOk v


operation minSignedInt8
output minSignedInt8 Result CSignedInt64 Void
memory minSignedInt8 heap no
memory minSignedInt8 stack max 1KiB
async minSignedInt8 no
purpose minSignedInt8 "Smallest value of a signed 8-bit integer (INT8_MIN)."
label startMinSignedInt8
const v CSignedInt64 -128
returnOk v


operation maxUnsignedInt8
output maxUnsignedInt8 Result CSignedInt64 Void
memory maxUnsignedInt8 heap no
memory maxUnsignedInt8 stack max 1KiB
async maxUnsignedInt8 no
purpose maxUnsignedInt8 "UINT8_MAX = 255."
label startMaxUnsignedInt8
const v CSignedInt64 255
returnOk v


operation maxSignedInt16
output maxSignedInt16 Result CSignedInt64 Void
memory maxSignedInt16 heap no
memory maxSignedInt16 stack max 1KiB
async maxSignedInt16 no
purpose maxSignedInt16 "INT16_MAX = 32767."
label startMaxSignedInt16
const v CSignedInt64 32767
returnOk v


operation minSignedInt16
output minSignedInt16 Result CSignedInt64 Void
memory minSignedInt16 heap no
memory minSignedInt16 stack max 1KiB
async minSignedInt16 no
purpose minSignedInt16 "INT16_MIN = -32768."
label startMinSignedInt16
const v CSignedInt64 -32768
returnOk v


operation maxUnsignedInt16
output maxUnsignedInt16 Result CSignedInt64 Void
memory maxUnsignedInt16 heap no
memory maxUnsignedInt16 stack max 1KiB
async maxUnsignedInt16 no
purpose maxUnsignedInt16 "UINT16_MAX = 65535."
label startMaxUnsignedInt16
const v CSignedInt64 65535
returnOk v


operation maxSignedInt32
output maxSignedInt32 Result CSignedInt64 Void
memory maxSignedInt32 heap no
memory maxSignedInt32 stack max 1KiB
async maxSignedInt32 no
purpose maxSignedInt32 "INT32_MAX = 2147483647."
label startMaxSignedInt32
const v CSignedInt64 2147483647
returnOk v


operation minSignedInt32
output minSignedInt32 Result CSignedInt64 Void
memory minSignedInt32 heap no
memory minSignedInt32 stack max 1KiB
async minSignedInt32 no
purpose minSignedInt32 "INT32_MIN = -2147483648."
label startMinSignedInt32
const v CSignedInt64 -2147483648
returnOk v


operation maxUnsignedInt32
output maxUnsignedInt32 Result CSignedInt64 Void
memory maxUnsignedInt32 heap no
memory maxUnsignedInt32 stack max 1KiB
async maxUnsignedInt32 no
purpose maxUnsignedInt32 "UINT32_MAX = 4294967295."
label startMaxUnsignedInt32
const v CSignedInt64 4294967295
returnOk v


operation maxSignedInt64
output maxSignedInt64 Result CSignedInt64 Void
memory maxSignedInt64 heap no
memory maxSignedInt64 stack max 1KiB
async maxSignedInt64 no
purpose maxSignedInt64 "INT64_MAX = 9223372036854775807."
label startMaxSignedInt64
const v CSignedInt64 9223372036854775807
returnOk v


operation bitsPerByte
output bitsPerByte Result CSignedInt64 Void
memory bitsPerByte heap no
memory bitsPerByte stack max 1KiB
async bitsPerByte no
purpose bitsPerByte "CHAR_BIT (always 8 in C99+)."
label startBitsPerByte
const v CSignedInt64 8
returnOk v


# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test limits accessors. Prints OK."

label startMain

call l1 maxSignedInt32
run l1
bindOk l1Res CSignedInt64 l1
const exp32 CSignedInt64 2147483647
call l1Check math.equalI64
arg l1Check left l1Res
arg l1Check right exp32
run l1Check
bind l1Ok Bool l1Check
branchIf l1Ok l1OkLabel
branch testFailed
label l1OkLabel

call l2 bitsPerByte
run l2
bindOk l2Res CSignedInt64 l2
const eight CSignedInt64 8
call l2Check math.equalI64
arg l2Check left l2Res
arg l2Check right eight
run l2Check
bind l2Ok Bool l2Check
branchIf l2Ok l2OkLabel
branch testFailed
label l2OkLabel

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
