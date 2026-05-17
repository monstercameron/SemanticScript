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
#   widenSignedInt32ToSignedInt64(n)             Sign-extend i32 -> i64.
#   narrowSignedInt64ToSignedInt32(n)             Truncate i64 -> i32.
#   convertByteValueToUnsignedInt32(b)        (b + 256) % 256.
#   convertSignedInt64ToFloat64(n)               Wraps math.convertSignedInt64ToFloat64.
#   convertFloat64ToSignedInt64(x)               Wraps math.convertFloat64ToSignedInt64 (toward zero).
#   floatToIntRounded(x)        Round half-away-from-zero, then to i64.
#   calculateCStringPointerOffset(base, p)    p - base (signed i64).
#   advanceOpaquePointerByByteOffset(base, off)   base + off (returns new pointer).
# ============================================================


operation widenSignedInt32ToSignedInt64
input widenSignedInt32ToSignedInt64 inputValue CSignedInt32
output widenSignedInt32ToSignedInt64 Result CSignedInt64 Void
memory widenSignedInt32ToSignedInt64 heap no
async widenSignedInt32ToSignedInt64 no
purpose widenSignedInt32ToSignedInt64 "Sign-extend a 32-bit signed integer to 64 bits."
label startWidenSignedInt32ToSignedInt64
returnOk inputValue


operation narrowSignedInt64ToSignedInt32
input narrowSignedInt64ToSignedInt32 inputValue CSignedInt64
output narrowSignedInt64ToSignedInt32 Result CSignedInt32 Void
memory narrowSignedInt64ToSignedInt32 heap no
async narrowSignedInt64ToSignedInt32 no
purpose narrowSignedInt64ToSignedInt32 "Truncate a 64-bit signed integer to 32 bits. The truncation is handled by the returnOk codegen path which coerces to the operation's declared return type."
label startNarrowSignedInt64ToSignedInt32
returnOk inputValue


operation convertByteValueToUnsignedInt32
input convertByteValueToUnsignedInt32 signExtendedByteValue CSignedInt32
output convertByteValueToUnsignedInt32 Result CSignedInt32 Void
memory convertByteValueToUnsignedInt32 heap no
async convertByteValueToUnsignedInt32 no
purpose convertByteValueToUnsignedInt32 "Treat the low 8 bits of b as an unsigned byte in 0..255. Useful after pointer.loadByte which sign-extends."
label startConvertByteValueToUnsignedInt32
const tFs I64 256
call shift math.addI64
arg shift left signExtendedByteValue
arg shift right tFs
run shift
bind shifted I64 shift
call modCall math.moduloI64
arg modCall left shifted
arg modCall right tFs
run modCall
bind r CSignedInt32 modCall
returnOk r


operation convertSignedInt64ToFloat64
input convertSignedInt64ToFloat64 inputValue CSignedInt64
output convertSignedInt64ToFloat64 Result CFloat64 Void
memory convertSignedInt64ToFloat64 heap no
async convertSignedInt64ToFloat64 no
purpose convertSignedInt64ToFloat64 "Signed i64 to double via math.convertSignedInt64ToFloat64."
label startConvertSignedInt64ToFloat64
call ift math.convertSignedInt64ToFloat64
arg ift value inputValue
run ift
bind r CFloat64 ift
returnOk r


operation convertFloat64ToSignedInt64
input convertFloat64ToSignedInt64 inputValue CFloat64
output convertFloat64ToSignedInt64 Result CSignedInt64 Void
memory convertFloat64ToSignedInt64 heap no
async convertFloat64ToSignedInt64 no
purpose convertFloat64ToSignedInt64 "Double to i64 via math.convertFloat64ToSignedInt64 (truncate toward zero)."
label startConvertFloat64ToSignedInt64
call fti math.convertFloat64ToSignedInt64
arg fti value inputValue
run fti
bind r CSignedInt64 fti
returnOk r


operation calculateCStringPointerOffset
input calculateCStringPointerOffset baseValue CNullTerminatedByteString
input calculateCStringPointerOffset pointerValue CNullTerminatedByteString
output calculateCStringPointerOffset Result CSignedInt64 Void
effect calculateCStringPointerOffset read memory.buffer
memory calculateCStringPointerOffset heap no
async calculateCStringPointerOffset no
purpose calculateCStringPointerOffset "Returns p - base as a signed i64. Both pointers must lie in the same allocation for the result to be meaningful."
label startCalculateCStringPointerOffset
call diff pointer.difference
arg diff left pointerValue
arg diff right baseValue
run diff
bind r CSignedInt64 diff
returnOk r


operation advanceOpaquePointerByByteOffset
input advanceOpaquePointerByByteOffset baseValue COpaqueMemoryAddress
input advanceOpaquePointerByByteOffset byteOffset CByteCount
output advanceOpaquePointerByByteOffset Result COpaqueMemoryAddress Void
effect advanceOpaquePointerByByteOffset read memory.buffer
memory advanceOpaquePointerByByteOffset heap no
async advanceOpaquePointerByByteOffset no
purpose advanceOpaquePointerByByteOffset "Returns base + offset as a new pointer (no dereference)."
label startAdvanceOpaquePointerByByteOffset
call adv pointer.offset
arg adv base baseValue
arg adv offset byteOffset
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

# widenSignedInt32ToSignedInt64(-1) == -1
const negOne32 CSignedInt32 -1
const negOne64 CSignedInt64 -1
call c1 widenSignedInt32ToSignedInt64
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

# convertByteValueToUnsignedInt32(-1) == 255 (the byte 0xFF)
const negOne32b CSignedInt32 -1
const expected255 CSignedInt32 255
call c2 convertByteValueToUnsignedInt32
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

# convertFloat64ToSignedInt64(3.7) == 3
const c37 CFloat64 3.7
const expected3 CSignedInt64 3
call c3 convertFloat64ToSignedInt64
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
