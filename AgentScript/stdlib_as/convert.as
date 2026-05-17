project StdConvertSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: numeric / pointer conversions.
#
# Operations:
#   int32ToInt64(n)             Sign-extend i32 -> i64.
#   int64ToInt32(n)             Truncate i64 -> i32.
#   byteToUnsignedInt(b)        (b + 256) % 256.
#   intToFloat(n)               Wraps math.intToFloat.
#   floatToInt(x)               Wraps math.floatToInt (toward zero).
#   floatToIntRounded(x)        Round half-away-from-zero, then to i64.
#   pointerToOffset(base, p)    p - base (signed i64).
#   pointerAdvance(base, off)   base + off (returns new pointer).
# ============================================================


operation int32ToInt64
input int32ToInt64 n CSignedInt32
output int32ToInt64 Result CSignedInt64 Void
memory int32ToInt64 heap no
async int32ToInt64 no
purpose int32ToInt64 "Sign-extend a 32-bit signed integer to 64 bits."
label startInt32ToInt64
returnOk n


operation int64ToInt32
input int64ToInt32 n CSignedInt64
output int64ToInt32 Result CSignedInt32 Void
memory int64ToInt32 heap no
async int64ToInt32 no
purpose int64ToInt32 "Truncate a 64-bit signed integer to 32 bits. The truncation is handled by the returnOk codegen path which coerces to the operation's declared return type."
label startInt64ToInt32
returnOk n


operation byteToUnsignedInt
input byteToUnsignedInt b CSignedInt32
output byteToUnsignedInt Result CSignedInt32 Void
memory byteToUnsignedInt heap no
async byteToUnsignedInt no
purpose byteToUnsignedInt "Treat the low 8 bits of b as an unsigned byte in 0..255. Useful after pointer.loadByte which sign-extends."
label startByteToUnsignedInt
const tFs I64 256
call shift math.addI64
arg shift left b
arg shift right tFs
run shift
bind shifted I64 shift
call modCall math.moduloI64
arg modCall left shifted
arg modCall right tFs
run modCall
bind r CSignedInt32 modCall
returnOk r


operation intToFloat
input intToFloat n CSignedInt64
output intToFloat Result CFloat64 Void
memory intToFloat heap no
async intToFloat no
purpose intToFloat "Signed i64 to double via math.intToFloat."
label startIntToFloat
call ift math.intToFloat
arg ift value n
run ift
bind r CFloat64 ift
returnOk r


operation floatToInt
input floatToInt x CFloat64
output floatToInt Result CSignedInt64 Void
memory floatToInt heap no
async floatToInt no
purpose floatToInt "Double to i64 via math.floatToInt (truncate toward zero)."
label startFloatToInt
call fti math.floatToInt
arg fti value x
run fti
bind r CSignedInt64 fti
returnOk r


operation pointerToOffset
input pointerToOffset base CNullTerminatedByteString
input pointerToOffset p CNullTerminatedByteString
output pointerToOffset Result CSignedInt64 Void
effect pointerToOffset read memory.buffer
memory pointerToOffset heap no
async pointerToOffset no
purpose pointerToOffset "Returns p - base as a signed i64. Both pointers must lie in the same allocation for the result to be meaningful."
label startPointerToOffset
call diff pointer.difference
arg diff left p
arg diff right base
run diff
bind r CSignedInt64 diff
returnOk r


operation pointerAdvance
input pointerAdvance base COpaqueMemoryAddress
input pointerAdvance offset CByteCount
output pointerAdvance Result COpaqueMemoryAddress Void
effect pointerAdvance read memory.buffer
memory pointerAdvance heap no
async pointerAdvance no
purpose pointerAdvance "Returns base + offset as a new pointer (no dereference)."
label startPointerAdvance
call adv pointer.offset
arg adv base base
arg adv offset offset
run adv
bind r COpaqueMemoryAddress adv
returnOk r


# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test conversion ports. Prints OK."
label startMain

# int32ToInt64(-1) == -1
const negOne32 CSignedInt32 -1
const negOne64 CSignedInt64 -1
call c1 int32ToInt64
arg c1 n negOne32
run c1
bindOk c1Res CSignedInt64 c1
call c1Check math.equalI64
arg c1Check left c1Res
arg c1Check right negOne64
run c1Check
bind c1Ok Bool c1Check
branchIf c1Ok c1Lbl
branch testFailed
label c1Lbl

# byteToUnsignedInt(-1) == 255 (the byte 0xFF)
const negOne32b CSignedInt32 -1
const expected255 CSignedInt32 255
call c2 byteToUnsignedInt
arg c2 b negOne32b
run c2
bindOk c2Res CSignedInt32 c2
call c2Check math.equalI64
arg c2Check left c2Res
arg c2Check right expected255
run c2Check
bind c2Ok Bool c2Check
branchIf c2Ok c2Lbl
branch testFailed
label c2Lbl

# floatToInt(3.7) == 3
const c37 CFloat64 3.7
const expected3 CSignedInt64 3
call c3 floatToInt
arg c3 x c37
run c3
bindOk c3Res CSignedInt64 c3
call c3Check math.equalI64
arg c3Check left c3Res
arg c3Check right expected3
run c3Check
bind c3Ok Bool c3Check
branchIf c3Ok c3Lbl
branch testFailed
label c3Lbl

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
