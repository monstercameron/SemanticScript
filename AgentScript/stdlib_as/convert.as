# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: numeric + pointer conversions
# ============================================================
#
# # rationale: width / sign / pointer conversions between the
#   C-ABI numeric types. Every operation is total — no input
#   produces a failure, so the Result wrapper is dropped.
#
# # invariant: lossy narrowing is documented per-op. Widening
#   preserves value within its representable range.
#
# # security: pure value-level math; no I/O; no allocation;
#   no branches over secret bits.
#
# # timing: O(1) per call.
#
# # observability: no logs; consumers wrap when needed.

project StdConvertSelfTest
target console
runtime AgentRuntime 0.1
entry console main

error MainError
errorCase MainError ConvertSmokeAssertionFailed

domainLiteral byteRoleAdjustmentValue CSignedInt64 256
domainLiteralTrust byteRoleAdjustmentValue trustedStaticLiteral

# section convert.integers

operation widenSignedInt32ToSignedInt64
input widenSignedInt32ToSignedInt64 inputValue CSignedInt32
output widenSignedInt32ToSignedInt64 CSignedInt64
memoryHeap widenSignedInt32ToSignedInt64 no
async widenSignedInt32ToSignedInt64 no
purpose widenSignedInt32ToSignedInt64 "Sign-extend an i32 to i64. Implemented via the return-type coercion that returnValue performs."
invariant widenSignedInt32ToSignedInt64 "Value-preserving: every CSignedInt32 fits in CSignedInt64."
guarantee widenSignedInt32ToSignedInt64 "Total."
label startWidenSignedInt32ToSignedInt64
returnValue inputValue

operation narrowSignedInt64ToSignedInt32
input narrowSignedInt64ToSignedInt32 inputValue CSignedInt64
output narrowSignedInt64ToSignedInt32 CSignedInt32
memoryHeap narrowSignedInt64ToSignedInt32 no
async narrowSignedInt64ToSignedInt32 no
purpose narrowSignedInt64ToSignedInt32 "Truncate an i64 to i32. Discards the high 32 bits."
invariant narrowSignedInt64ToSignedInt32 "For inputs in [-2^31, 2^31-1] the result equals the input."
warning narrowSignedInt64ToSignedInt32 "Inputs outside the i32 range are silently truncated — caller must screen first to avoid surprise."
guarantee narrowSignedInt64ToSignedInt32 "Total."
label startNarrowSignedInt64ToSignedInt32
returnValue inputValue

operation convertByteValueToUnsignedInt32
input convertByteValueToUnsignedInt32 signExtendedByteValue CSignedInt32
output convertByteValueToUnsignedInt32 CSignedInt32
memoryHeap convertByteValueToUnsignedInt32 no
async convertByteValueToUnsignedInt32 no
purpose convertByteValueToUnsignedInt32 "Treat the low 8 bits of signExtendedByteValue as an unsigned byte in [0, 255]."
invariant convertByteValueToUnsignedInt32 "Output always in [0, 255]; (byte + 256) % 256 produces 0..255 for all inputs."
guarantee convertByteValueToUnsignedInt32 "Total."
# rationale: pointer.loadByte sign-extends the loaded byte to i32
#   under the LLVM ABI, so callers consuming the value as an
#   unsigned byte need this conversion. The +256 then mod-256
#   normalizes any sign-extended -1 / -2 / ... back to 255 / 254 / ...
label startConvertByteValueToUnsignedInt32
call shiftByteUpwardCall math.addI64
arg shiftByteUpwardCall left signExtendedByteValue
arg shiftByteUpwardCall right byteRoleAdjustmentValue
run shiftByteUpwardCall
bind shiftedByteUpward I64 shiftByteUpwardCall
call reduceByteModuloCall math.moduloI64
arg reduceByteModuloCall left shiftedByteUpward
arg reduceByteModuloCall right byteRoleAdjustmentValue
run reduceByteModuloCall
bind unsignedByteValue CSignedInt32 reduceByteModuloCall
returnValue unsignedByteValue

# section convert.numericFloats

operation convertSignedInt64ToFloat64
input convertSignedInt64ToFloat64 inputValue CSignedInt64
output convertSignedInt64ToFloat64 CFloat64
memoryHeap convertSignedInt64ToFloat64 no
async convertSignedInt64ToFloat64 no
purpose convertSignedInt64ToFloat64 "Convert a signed 64-bit integer to a double. Wraps math.intToFloat (LLVM sitofp)."
invariant convertSignedInt64ToFloat64 "Loss-of-precision possible for magnitudes >= 2^53; otherwise round-trippable."
guarantee convertSignedInt64ToFloat64 "Total."
label startConvertSignedInt64ToFloat64
call sitoffpCall math.intToFloat
arg sitoffpCall value inputValue
run sitoffpCall
bind asDoubleResult CFloat64 sitoffpCall
returnValue asDoubleResult

operation convertFloat64ToSignedInt64
input convertFloat64ToSignedInt64 inputValue CFloat64
output convertFloat64ToSignedInt64 CSignedInt64
memoryHeap convertFloat64ToSignedInt64 no
async convertFloat64ToSignedInt64 no
purpose convertFloat64ToSignedInt64 "Convert a double to a signed 64-bit integer by rounding toward zero. Wraps math.floatToInt (LLVM fptosi)."
invariant convertFloat64ToSignedInt64 "For inputs in [-2^63, 2^63) the conversion is well-defined; outside that range the result is implementation-defined (LLVM fptosi)."
warning convertFloat64ToSignedInt64 "NaN inputs produce an unspecified i64 — caller must screen with c.isnan when defined behavior is required."
guarantee convertFloat64ToSignedInt64 "Total over the in-range CFloat64 domain."
label startConvertFloat64ToSignedInt64
call fptosiCall math.floatToInt
arg fptosiCall value inputValue
run fptosiCall
bind asIntegerResult CSignedInt64 fptosiCall
returnValue asIntegerResult

# section convert.pointers

operation calculateCStringPointerOffset
input calculateCStringPointerOffset baseValue CNullTerminatedByteString
input calculateCStringPointerOffset pointerValue CNullTerminatedByteString
output calculateCStringPointerOffset CSignedInt64
effect calculateCStringPointerOffset read baseValue
effect calculateCStringPointerOffset read pointerValue
memoryHeap calculateCStringPointerOffset no
async calculateCStringPointerOffset no
purpose calculateCStringPointerOffset "Returns pointerValue - baseValue as a signed CSignedInt64 byte offset."
invariant calculateCStringPointerOffset "Result is meaningful only when both pointers point into the same allocation."
warning calculateCStringPointerOffset "Subtracting pointers from different allocations yields undefined values."
guarantee calculateCStringPointerOffset "Total — never traps on valid CNullTerminatedByteString inputs."
label startCalculateCStringPointerOffset
call computePointerDifferenceCall pointer.difference
arg computePointerDifferenceCall left pointerValue
arg computePointerDifferenceCall right baseValue
run computePointerDifferenceCall
bind pointerDifferenceResult CSignedInt64 computePointerDifferenceCall
returnValue pointerDifferenceResult

operation advanceOpaquePointerByByteOffset
input advanceOpaquePointerByByteOffset baseValue COpaqueMemoryAddress
input advanceOpaquePointerByByteOffset byteOffset CByteCount
output advanceOpaquePointerByByteOffset COpaqueMemoryAddress
effect advanceOpaquePointerByByteOffset read baseValue
memoryHeap advanceOpaquePointerByByteOffset no
async advanceOpaquePointerByByteOffset no
purpose advanceOpaquePointerByByteOffset "Returns baseValue + byteOffset as a new COpaqueMemoryAddress (no dereference)."
invariant advanceOpaquePointerByByteOffset "Pointer arithmetic only; the result is guaranteed not to dereference the input pointer."
warning advanceOpaquePointerByByteOffset "Caller is responsible for the result lying within an allocation before any subsequent load/store."
guarantee advanceOpaquePointerByByteOffset "Total."
label startAdvanceOpaquePointerByByteOffset
call applyPointerOffsetCall pointer.offset
arg applyPointerOffsetCall base baseValue
arg applyPointerOffsetCall offset byteOffset
run applyPointerOffsetCall
bind offsetPointerResult COpaqueMemoryAddress applyPointerOffsetCall
returnValue offsetPointerResult

# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memoryHeap main no
async main no
purpose main "Smoke-test the conversion operations."
invariant main "widen(-1) == -1; convertByteValueToUnsignedInt32(-1) == 255; convertFloat64ToSignedInt64(3.7) == 3."

label startMain

# widenSignedInt32ToSignedInt64(-1) == -1
const negativeOneAsSignedInt32 CSignedInt32 -1
const negativeOneAsSignedInt64 CSignedInt64 -1
call assertWidenCall widenSignedInt32ToSignedInt64
arg assertWidenCall inputValue negativeOneAsSignedInt32
run assertWidenCall
bind widenResult CSignedInt64 assertWidenCall
call checkWidenCall math.equalI64
arg checkWidenCall left widenResult
arg checkWidenCall right negativeOneAsSignedInt64
run checkWidenCall
bind widenOk Bool checkWidenCall
branchIf widenOk widenHolds
branch smokeAssertionFailed
label widenHolds

# convertByteValueToUnsignedInt32(-1) == 255
const expectedTwoHundredFiftyFive CSignedInt32 255
call assertByteConversionCall convertByteValueToUnsignedInt32
arg assertByteConversionCall signExtendedByteValue negativeOneAsSignedInt32
run assertByteConversionCall
bind byteConversionResult CSignedInt32 assertByteConversionCall
call checkByteConversionCall math.equalI64
arg checkByteConversionCall left byteConversionResult
arg checkByteConversionCall right expectedTwoHundredFiftyFive
run checkByteConversionCall
bind byteConversionOk Bool checkByteConversionCall
branchIf byteConversionOk byteConversionHolds
branch smokeAssertionFailed
label byteConversionHolds

# convertFloat64ToSignedInt64(3.7) == 3 (truncate toward zero)
const threePointSevenFloat CFloat64 3.7
const expectedThree CSignedInt64 3
call assertFloatToIntCall convertFloat64ToSignedInt64
arg assertFloatToIntCall inputValue threePointSevenFloat
run assertFloatToIntCall
bind floatToIntResult CSignedInt64 assertFloatToIntCall
call checkFloatToIntCall math.equalI64
arg checkFloatToIntCall left floatToIntResult
arg checkFloatToIntCall right expectedThree
run checkFloatToIntCall
bind floatToIntOk Bool checkFloatToIntCall
branchIf floatToIntOk floatToIntHolds
branch smokeAssertionFailed
label floatToIntHolds

const successMessageText CNullTerminatedByteString "OK"
call writeSuccessLineCall console.writeLine
arg writeSuccessLineCall console console
arg writeSuccessLineCall text successMessageText
run writeSuccessLineCall
ignoreOk writeSuccessLineCall Void
const exitOkCode ExitCode 0
returnOk exitOkCode

label smokeAssertionFailed
makeError convertSmokeFailure MainError.ConvertSmokeAssertionFailed
returnError convertSmokeFailure
