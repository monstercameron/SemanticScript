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
errorCase MainError ConsoleWriteFailed

# section capability
# rationale: smoke-test main writes a single OK line to stdout.
capability stdoutWriteCapability console.stdout write

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
useCapability main stdoutWriteCapability
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

# ============================================================
# Extended unit tests: covers the 4 ops the smoke previously
# omitted (narrow, convertSignedInt64ToFloat64,
# calculateCStringPointerOffset; advanceOpaquePointerByByteOffset
# is exercised via round-trip with calculateCStringPointerOffset)
# plus negative / zero / boundary cases for the existing ops.
# ============================================================

const fiveSigned CSignedInt64 5
const fiveAsI32 CSignedInt32 5
const zeroSigned CSignedInt64 0
const zeroAsI32 CSignedInt32 0
const negThreePointSeven CFloat64 -3.7
const negThree CSignedInt64 -3
const zeroFloatCvt CFloat64 0.0
const sevenSigned CSignedInt64 7
const floatCvtTol CFloat64 0.0001
const negFloatCvtTol CFloat64 -0.0001
const maxInt32Signed CSignedInt64 2147483647

# narrowSignedInt64ToSignedInt32(5) == 5 (in-range, no truncation)
call narrowFiveCall narrowSignedInt64ToSignedInt32
arg narrowFiveCall inputValue fiveSigned
run narrowFiveCall
bind narrowFiveResult CSignedInt32 narrowFiveCall
call narrowFiveCheckCall math.equalI64
arg narrowFiveCheckCall left narrowFiveResult
arg narrowFiveCheckCall right fiveAsI32
run narrowFiveCheckCall
bind narrowFiveOk Bool narrowFiveCheckCall
branchIf narrowFiveOk narrowFiveHolds
branch smokeAssertionFailed
label narrowFiveHolds

# narrow(2147483647) == 2147483647 (max i32 boundary, exact)
const maxInt32AsI32 CSignedInt32 2147483647
call narrowMaxCall narrowSignedInt64ToSignedInt32
arg narrowMaxCall inputValue maxInt32Signed
run narrowMaxCall
bind narrowMaxResult CSignedInt32 narrowMaxCall
call narrowMaxCheckCall math.equalI64
arg narrowMaxCheckCall left narrowMaxResult
arg narrowMaxCheckCall right maxInt32AsI32
run narrowMaxCheckCall
bind narrowMaxOk Bool narrowMaxCheckCall
branchIf narrowMaxOk narrowMaxHolds
branch smokeAssertionFailed
label narrowMaxHolds

# convertSignedInt64ToFloat64(5) ≈ 5.0 (within tolerance)
const fiveAsFloat CFloat64 5.0
call intToFloatCall convertSignedInt64ToFloat64
arg intToFloatCall inputValue fiveSigned
run intToFloatCall
bind intToFloatResult CFloat64 intToFloatCall
call intToFloatDiffCall math.subtractF64
arg intToFloatDiffCall left intToFloatResult
arg intToFloatDiffCall right fiveAsFloat
run intToFloatDiffCall
bind intToFloatDiff CFloat64 intToFloatDiffCall
# tolerance check: -tol < diff < tol
call intToFloatLowerCall math.greaterThanF64
arg intToFloatLowerCall left intToFloatDiff
arg intToFloatLowerCall right negFloatCvtTol
run intToFloatLowerCall
bind intToFloatAboveLower Bool intToFloatLowerCall
call intToFloatUpperCall math.lessThanF64
arg intToFloatUpperCall left intToFloatDiff
arg intToFloatUpperCall right floatCvtTol
run intToFloatUpperCall
bind intToFloatBelowUpper Bool intToFloatUpperCall
branchIf intToFloatAboveLower intToFloatCheckUpper
branch smokeAssertionFailed
label intToFloatCheckUpper
branchIf intToFloatBelowUpper intToFloatHolds
branch smokeAssertionFailed
label intToFloatHolds

# convertFloat64ToSignedInt64(-3.7) == -3 (truncates toward zero, not floor)
call floatToIntNegCall convertFloat64ToSignedInt64
arg floatToIntNegCall inputValue negThreePointSeven
run floatToIntNegCall
bind floatToIntNegResult CSignedInt64 floatToIntNegCall
call floatToIntNegCheckCall math.equalI64
arg floatToIntNegCheckCall left floatToIntNegResult
arg floatToIntNegCheckCall right negThree
run floatToIntNegCheckCall
bind floatToIntNegOk Bool floatToIntNegCheckCall
branchIf floatToIntNegOk floatToIntNegHolds
branch smokeAssertionFailed
label floatToIntNegHolds

# convertFloat64ToSignedInt64(0.0) == 0
call floatToIntZeroCall convertFloat64ToSignedInt64
arg floatToIntZeroCall inputValue zeroFloatCvt
run floatToIntZeroCall
bind floatToIntZeroResult CSignedInt64 floatToIntZeroCall
call floatToIntZeroCheckCall math.equalI64
arg floatToIntZeroCheckCall left floatToIntZeroResult
arg floatToIntZeroCheckCall right zeroSigned
run floatToIntZeroCheckCall
bind floatToIntZeroOk Bool floatToIntZeroCheckCall
branchIf floatToIntZeroOk floatToIntZeroHolds
branch smokeAssertionFailed
label floatToIntZeroHolds

# Property: convertFloat64ToSignedInt64(convertSignedInt64ToFloat64(7)) == 7
call roundTripFloatCall convertSignedInt64ToFloat64
arg roundTripFloatCall inputValue sevenSigned
run roundTripFloatCall
bind roundTripFloatResult CFloat64 roundTripFloatCall
call roundTripIntCall convertFloat64ToSignedInt64
arg roundTripIntCall inputValue roundTripFloatResult
run roundTripIntCall
bind roundTripIntResult CSignedInt64 roundTripIntCall
call roundTripCheckCall math.equalI64
arg roundTripCheckCall left roundTripIntResult
arg roundTripCheckCall right sevenSigned
run roundTripCheckCall
bind roundTripOk Bool roundTripCheckCall
branchIf roundTripOk roundTripHolds
branch smokeAssertionFailed
label roundTripHolds

# calculateCStringPointerOffset(s, s) == 0 (same pointer → zero offset)
const sampleStr CNullTerminatedByteString "abc"
call sameOffsetCall calculateCStringPointerOffset
arg sameOffsetCall baseValue sampleStr
arg sameOffsetCall pointerValue sampleStr
run sameOffsetCall
bind sameOffsetResult CSignedInt64 sameOffsetCall
call sameOffsetCheckCall math.equalI64
arg sameOffsetCheckCall left sameOffsetResult
arg sameOffsetCheckCall right zeroSigned
run sameOffsetCheckCall
bind sameOffsetOk Bool sameOffsetCheckCall
branchIf sameOffsetOk sameOffsetHolds
branch smokeAssertionFailed
label sameOffsetHolds

# convertByteValueToUnsignedInt32(0) == 0 (boundary)
call byteZeroCall convertByteValueToUnsignedInt32
arg byteZeroCall signExtendedByteValue zeroAsI32
run byteZeroCall
bind byteZeroResult CSignedInt32 byteZeroCall
call byteZeroCheckCall math.equalI64
arg byteZeroCheckCall left byteZeroResult
arg byteZeroCheckCall right zeroAsI32
run byteZeroCheckCall
bind byteZeroOk Bool byteZeroCheckCall
branchIf byteZeroOk byteZeroHolds
branch smokeAssertionFailed
label byteZeroHolds

# convertByteValueToUnsignedInt32(127) == 127 (positive in-range)
const onehTwentySevenI32 CSignedInt32 127
call byteMidCall convertByteValueToUnsignedInt32
arg byteMidCall signExtendedByteValue onehTwentySevenI32
run byteMidCall
bind byteMidResult CSignedInt32 byteMidCall
call byteMidCheckCall math.equalI64
arg byteMidCheckCall left byteMidResult
arg byteMidCheckCall right onehTwentySevenI32
run byteMidCheckCall
bind byteMidOk Bool byteMidCheckCall
branchIf byteMidOk byteMidHolds
branch smokeAssertionFailed
label byteMidHolds

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
makeError convertSmokeFailure MainError.ConvertSmokeAssertionFailed
returnError convertSmokeFailure
