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
#   maximumSignedInt8Value         - 127
#   minimumSignedInt8Value         - -128
#   maximumUnsignedInt8Value       - 255
#   maximumSignedInt16Value        - 32767
#   minimumSignedInt16Value        - -32768
#   maximumUnsignedInt16Value      - 65535
#   maximumSignedInt32Value        - 2147483647
#   minimumSignedInt32Value        - -2147483648
#   maximumUnsignedInt32Value      - 4294967295
#   maximumSignedInt64Value        - 9223372036854775807
#   minSignedInt64        - -9223372036854775808 (wraps at I64 boundary)
#   bitCountPerByte           - 8
# ============================================================

operation maximumSignedInt8Value
output maximumSignedInt8Value Result CSignedInt64 Void
memory maximumSignedInt8Value heap no
memory maximumSignedInt8Value stack max 1KiB
async maximumSignedInt8Value no
purpose maximumSignedInt8Value "Largest value of a signed 8-bit integer (INT8_MAX)."
label startMaximumSignedInt8Value
const v CSignedInt64 127
returnOk v


operation minimumSignedInt8Value
output minimumSignedInt8Value Result CSignedInt64 Void
memory minimumSignedInt8Value heap no
memory minimumSignedInt8Value stack max 1KiB
async minimumSignedInt8Value no
purpose minimumSignedInt8Value "Smallest value of a signed 8-bit integer (INT8_MIN)."
label startMinimumSignedInt8Value
const v CSignedInt64 -128
returnOk v


operation maximumUnsignedInt8Value
output maximumUnsignedInt8Value Result CSignedInt64 Void
memory maximumUnsignedInt8Value heap no
memory maximumUnsignedInt8Value stack max 1KiB
async maximumUnsignedInt8Value no
purpose maximumUnsignedInt8Value "UINT8_MAX = 255."
label startMaximumUnsignedInt8Value
const v CSignedInt64 255
returnOk v


operation maximumSignedInt16Value
output maximumSignedInt16Value Result CSignedInt64 Void
memory maximumSignedInt16Value heap no
memory maximumSignedInt16Value stack max 1KiB
async maximumSignedInt16Value no
purpose maximumSignedInt16Value "INT16_MAX = 32767."
label startMaximumSignedInt16Value
const v CSignedInt64 32767
returnOk v


operation minimumSignedInt16Value
output minimumSignedInt16Value Result CSignedInt64 Void
memory minimumSignedInt16Value heap no
memory minimumSignedInt16Value stack max 1KiB
async minimumSignedInt16Value no
purpose minimumSignedInt16Value "INT16_MIN = -32768."
label startMinimumSignedInt16Value
const v CSignedInt64 -32768
returnOk v


operation maximumUnsignedInt16Value
output maximumUnsignedInt16Value Result CSignedInt64 Void
memory maximumUnsignedInt16Value heap no
memory maximumUnsignedInt16Value stack max 1KiB
async maximumUnsignedInt16Value no
purpose maximumUnsignedInt16Value "UINT16_MAX = 65535."
label startMaximumUnsignedInt16Value
const v CSignedInt64 65535
returnOk v


operation maximumSignedInt32Value
output maximumSignedInt32Value Result CSignedInt64 Void
memory maximumSignedInt32Value heap no
memory maximumSignedInt32Value stack max 1KiB
async maximumSignedInt32Value no
purpose maximumSignedInt32Value "INT32_MAX = 2147483647."
label startMaximumSignedInt32Value
const v CSignedInt64 2147483647
returnOk v


operation minimumSignedInt32Value
output minimumSignedInt32Value Result CSignedInt64 Void
memory minimumSignedInt32Value heap no
memory minimumSignedInt32Value stack max 1KiB
async minimumSignedInt32Value no
purpose minimumSignedInt32Value "INT32_MIN = -2147483648."
label startMinimumSignedInt32Value
const v CSignedInt64 -2147483648
returnOk v


operation maximumUnsignedInt32Value
output maximumUnsignedInt32Value Result CSignedInt64 Void
memory maximumUnsignedInt32Value heap no
memory maximumUnsignedInt32Value stack max 1KiB
async maximumUnsignedInt32Value no
purpose maximumUnsignedInt32Value "UINT32_MAX = 4294967295."
label startMaximumUnsignedInt32Value
const v CSignedInt64 4294967295
returnOk v


operation maximumSignedInt64Value
output maximumSignedInt64Value Result CSignedInt64 Void
memory maximumSignedInt64Value heap no
memory maximumSignedInt64Value stack max 1KiB
async maximumSignedInt64Value no
purpose maximumSignedInt64Value "INT64_MAX = 9223372036854775807."
label startMaximumSignedInt64Value
const v CSignedInt64 9223372036854775807
returnOk v


operation bitCountPerByte
output bitCountPerByte Result CSignedInt64 Void
memory bitCountPerByte heap no
memory bitCountPerByte stack max 1KiB
async bitCountPerByte no
purpose bitCountPerByte "CHAR_BIT (always 8 in C99+)."
label startBitCountPerByte
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

call l1 maximumSignedInt32Value
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

call l2 bitCountPerByte
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
