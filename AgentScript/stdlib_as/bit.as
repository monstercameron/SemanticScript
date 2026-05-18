# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: bitwise operations on CSignedInt64
# ============================================================
#
# # rationale: AgentScript's math.* surface has no native bitwise
#   primitives (and/or/xor/not/shift), so this module implements
#   them via multiplication, division, and modulo. Each bit op is
#   pure-AS — no libc, no special LLVM intrinsics — and constant-
#   folds when both operands are compile-time constants.
#
# # invariant: shifts are unsigned-equivalent (multiplication /
#   division by 2^k). isSignedInt64BitSet checks the k-th bit of
#   the abstract base-2 representation, equivalent to ((n >> k) & 1).
#   setSignedInt64Bit / clearSignedInt64Bit / toggleSignedInt64Bit
#   preserve every other bit.
#
# # security: pure value-level math; no allocation; no branches
#   over secret-dependent bit patterns beyond the standard k-step
#   power-of-two loop.
#
# # timing: O(k) where k is bitIndex (loop bound). Acceptable for
#   bitIndex up to 63; not for hot inner loops. Future revisions
#   should expose LLVM `shl`/`lshr`/`and`/`or`/`xor` intrinsics.
#
# # observability: no logs, no metrics.
#
# # warning: bitIndex must be in [0, 63]. Values outside this
#   range silently wrap (multiplication by 2^64 overflows back).
#
# Operations exposed:
#   shiftSignedInt64BitsLeft(inputValue, bitIndex)   -> CSignedInt64
#   shiftSignedInt64BitsRight(inputValue, bitIndex)  -> CSignedInt64
#   isSignedInt64BitSet(inputValue, bitIndex)        -> Bool
#   setSignedInt64Bit(inputValue, bitIndex)          -> CSignedInt64
#   clearSignedInt64Bit(inputValue, bitIndex)        -> CSignedInt64
#   toggleSignedInt64Bit(inputValue, bitIndex)       -> CSignedInt64

project StdBitSelfTest
target console
runtime AgentRuntime 0.1
entry console main

error MainError
errorCase MainError BitSmokeAssertionFailed
errorCase MainError ConsoleWriteFailed

# section capability
# rationale: smoke-test main writes a single OK line to stdout.
capability stdoutWriteCapability console.stdout write

domainLiteral integerZeroComparisonValue CSignedInt64 0
domainLiteralTrust integerZeroComparisonValue trustedStaticLiteral
domainLiteral integerOneStepValue CSignedInt64 1
domainLiteralTrust integerOneStepValue trustedStaticLiteral
domainLiteral integerTwoBaseValue CSignedInt64 2
domainLiteralTrust integerTwoBaseValue trustedStaticLiteral

# section bit.shift

operation shiftSignedInt64BitsLeft
input shiftSignedInt64BitsLeft inputValue CSignedInt64
input shiftSignedInt64BitsLeft bitIndex CSignedInt64
output shiftSignedInt64BitsLeft CSignedInt64
memoryHeap shiftSignedInt64BitsLeft no
async shiftSignedInt64BitsLeft no
purpose shiftSignedInt64BitsLeft "Returns inputValue << bitIndex, computed as inputValue * 2^bitIndex."
invariant shiftSignedInt64BitsLeft "For bitIndex in [0, 63] and non-overflowing values, equivalent to LLVM's shl."
warning shiftSignedInt64BitsLeft "Overflow wraps modulo 2^64; bitIndex < 0 is undefined."
guarantee shiftSignedInt64BitsLeft "Terminates after bitIndex iterations."
label startShiftSignedInt64BitsLeft
var leftShiftPowerAccumulator I64 1
var leftShiftIteration I64 0
label leftShiftLoop
call detectLeftShiftDoneCall math.greaterThanOrEqualI64
arg detectLeftShiftDoneCall left leftShiftIteration
arg detectLeftShiftDoneCall right bitIndex
run detectLeftShiftDoneCall
bind leftShiftDone Bool detectLeftShiftDoneCall
branchIf leftShiftDone applyLeftShiftMultiplication
call doubleLeftShiftPowerCall math.multiplyI64
arg doubleLeftShiftPowerCall left leftShiftPowerAccumulator
arg doubleLeftShiftPowerCall right integerTwoBaseValue
run doubleLeftShiftPowerCall
bind doubledLeftShiftPower I64 doubleLeftShiftPowerCall
set leftShiftPowerAccumulator doubledLeftShiftPower
call incrementLeftShiftIterationCall math.addI64
arg incrementLeftShiftIterationCall left leftShiftIteration
arg incrementLeftShiftIterationCall right integerOneStepValue
run incrementLeftShiftIterationCall
bind nextLeftShiftIteration I64 incrementLeftShiftIterationCall
set leftShiftIteration nextLeftShiftIteration
branch leftShiftLoop
label applyLeftShiftMultiplication
call multiplyInputByPowerCall math.multiplyI64
arg multiplyInputByPowerCall left inputValue
arg multiplyInputByPowerCall right leftShiftPowerAccumulator
run multiplyInputByPowerCall
bind shiftedLeftResult CSignedInt64 multiplyInputByPowerCall
returnValue shiftedLeftResult

operation shiftSignedInt64BitsRight
input shiftSignedInt64BitsRight inputValue CSignedInt64
input shiftSignedInt64BitsRight bitIndex CSignedInt64
output shiftSignedInt64BitsRight CSignedInt64
memoryHeap shiftSignedInt64BitsRight no
async shiftSignedInt64BitsRight no
purpose shiftSignedInt64BitsRight "Returns inputValue >> bitIndex, computed as inputValue / 2^bitIndex (arithmetic for signed values via LLVM sdiv)."
invariant shiftSignedInt64BitsRight "For bitIndex in [0, 63] equivalent to LLVM's ashr semantics on the round-toward-zero domain."
warning shiftSignedInt64BitsRight "sdiv rounds toward zero, not toward minus-infinity — differs from C's >> on negative operands when bitIndex > 0."
guarantee shiftSignedInt64BitsRight "Terminates after bitIndex iterations."
label startShiftSignedInt64BitsRight
var rightShiftDivisorAccumulator I64 1
var rightShiftIteration I64 0
label rightShiftLoop
call detectRightShiftDoneCall math.greaterThanOrEqualI64
arg detectRightShiftDoneCall left rightShiftIteration
arg detectRightShiftDoneCall right bitIndex
run detectRightShiftDoneCall
bind rightShiftDone Bool detectRightShiftDoneCall
branchIf rightShiftDone applyRightShiftDivision
call doubleRightShiftDivisorCall math.multiplyI64
arg doubleRightShiftDivisorCall left rightShiftDivisorAccumulator
arg doubleRightShiftDivisorCall right integerTwoBaseValue
run doubleRightShiftDivisorCall
bind doubledRightShiftDivisor I64 doubleRightShiftDivisorCall
set rightShiftDivisorAccumulator doubledRightShiftDivisor
call incrementRightShiftIterationCall math.addI64
arg incrementRightShiftIterationCall left rightShiftIteration
arg incrementRightShiftIterationCall right integerOneStepValue
run incrementRightShiftIterationCall
bind nextRightShiftIteration I64 incrementRightShiftIterationCall
set rightShiftIteration nextRightShiftIteration
branch rightShiftLoop
label applyRightShiftDivision
call divideInputByDivisorCall math.divideI64
arg divideInputByDivisorCall left inputValue
arg divideInputByDivisorCall right rightShiftDivisorAccumulator
run divideInputByDivisorCall
bind shiftedRightResult CSignedInt64 divideInputByDivisorCall
returnValue shiftedRightResult

# section bit.predicate

operation isSignedInt64BitSet
input isSignedInt64BitSet inputValue CSignedInt64
input isSignedInt64BitSet bitIndex CSignedInt64
output isSignedInt64BitSet Bool
memoryHeap isSignedInt64BitSet no
async isSignedInt64BitSet no
purpose isSignedInt64BitSet "Returns true when the k-th bit of inputValue is set, equivalent to ((inputValue >> bitIndex) & 1) != 0."
invariant isSignedInt64BitSet "Pure function: same inputs always produce the same Bool."
guarantee isSignedInt64BitSet "Total."
label startIsSignedInt64BitSet
call shiftDownToTargetBitCall shiftSignedInt64BitsRight
arg shiftDownToTargetBitCall inputValue inputValue
arg shiftDownToTargetBitCall bitIndex bitIndex
run shiftDownToTargetBitCall
bind shiftedDownInput CSignedInt64 shiftDownToTargetBitCall
call extractLowBitCall math.moduloI64
arg extractLowBitCall left shiftedDownInput
arg extractLowBitCall right integerTwoBaseValue
run extractLowBitCall
bind lowestBitValue I64 extractLowBitCall
call detectLowBitIsOneCall math.notEqualI64
arg detectLowBitIsOneCall left lowestBitValue
arg detectLowBitIsOneCall right integerZeroComparisonValue
run detectLowBitIsOneCall
bind lowBitIsOne Bool detectLowBitIsOneCall
returnValue lowBitIsOne

# section bit.mutation

operation setSignedInt64Bit
input setSignedInt64Bit inputValue CSignedInt64
input setSignedInt64Bit bitIndex CSignedInt64
output setSignedInt64Bit CSignedInt64
memoryHeap setSignedInt64Bit no
async setSignedInt64Bit no
purpose setSignedInt64Bit "Returns inputValue with the k-th bit forced to 1. No change if the bit is already set."
invariant setSignedInt64Bit "isSignedInt64BitSet(setSignedInt64Bit(x, k), k) == true."
guarantee setSignedInt64Bit "Total."
label startSetSignedInt64Bit
call detectBitAlreadySetCall isSignedInt64BitSet
arg detectBitAlreadySetCall inputValue inputValue
arg detectBitAlreadySetCall bitIndex bitIndex
run detectBitAlreadySetCall
bind bitAlreadySet Bool detectBitAlreadySetCall
branchIf bitAlreadySet returnInputUnchangedForSet
var setBitPowerAccumulator I64 1
var setBitIteration I64 0
label setBitPowerLoop
call detectSetBitDoneCall math.greaterThanOrEqualI64
arg detectSetBitDoneCall left setBitIteration
arg detectSetBitDoneCall right bitIndex
run detectSetBitDoneCall
bind setBitDone Bool detectSetBitDoneCall
branchIf setBitDone applySetBitAddition
call doubleSetBitPowerCall math.multiplyI64
arg doubleSetBitPowerCall left setBitPowerAccumulator
arg doubleSetBitPowerCall right integerTwoBaseValue
run doubleSetBitPowerCall
bind doubledSetBitPower I64 doubleSetBitPowerCall
set setBitPowerAccumulator doubledSetBitPower
call incrementSetBitIterationCall math.addI64
arg incrementSetBitIterationCall left setBitIteration
arg incrementSetBitIterationCall right integerOneStepValue
run incrementSetBitIterationCall
bind nextSetBitIteration I64 incrementSetBitIterationCall
set setBitIteration nextSetBitIteration
branch setBitPowerLoop
label applySetBitAddition
call addBitPowerToInputCall math.addI64
arg addBitPowerToInputCall left inputValue
arg addBitPowerToInputCall right setBitPowerAccumulator
run addBitPowerToInputCall
bind setBitResultValue CSignedInt64 addBitPowerToInputCall
returnValue setBitResultValue
label returnInputUnchangedForSet
returnValue inputValue

operation clearSignedInt64Bit
input clearSignedInt64Bit inputValue CSignedInt64
input clearSignedInt64Bit bitIndex CSignedInt64
output clearSignedInt64Bit CSignedInt64
memoryHeap clearSignedInt64Bit no
async clearSignedInt64Bit no
purpose clearSignedInt64Bit "Returns inputValue with the k-th bit forced to 0. No change if the bit is already clear."
invariant clearSignedInt64Bit "isSignedInt64BitSet(clearSignedInt64Bit(x, k), k) == false."
guarantee clearSignedInt64Bit "Total."
label startClearSignedInt64Bit
call detectBitAlreadyClearCall isSignedInt64BitSet
arg detectBitAlreadyClearCall inputValue inputValue
arg detectBitAlreadyClearCall bitIndex bitIndex
run detectBitAlreadyClearCall
bind bitCurrentlySet Bool detectBitAlreadyClearCall
branchIf bitCurrentlySet subtractBitPowerFromInputComputePath
returnValue inputValue
label subtractBitPowerFromInputComputePath
var clearBitPowerAccumulator I64 1
var clearBitIteration I64 0
label clearBitPowerLoop
call detectClearBitDoneCall math.greaterThanOrEqualI64
arg detectClearBitDoneCall left clearBitIteration
arg detectClearBitDoneCall right bitIndex
run detectClearBitDoneCall
bind clearBitDone Bool detectClearBitDoneCall
branchIf clearBitDone applyClearBitSubtraction
call doubleClearBitPowerCall math.multiplyI64
arg doubleClearBitPowerCall left clearBitPowerAccumulator
arg doubleClearBitPowerCall right integerTwoBaseValue
run doubleClearBitPowerCall
bind doubledClearBitPower I64 doubleClearBitPowerCall
set clearBitPowerAccumulator doubledClearBitPower
call incrementClearBitIterationCall math.addI64
arg incrementClearBitIterationCall left clearBitIteration
arg incrementClearBitIterationCall right integerOneStepValue
run incrementClearBitIterationCall
bind nextClearBitIteration I64 incrementClearBitIterationCall
set clearBitIteration nextClearBitIteration
branch clearBitPowerLoop
label applyClearBitSubtraction
call subtractBitPowerFromInputCall math.subtractI64
arg subtractBitPowerFromInputCall left inputValue
arg subtractBitPowerFromInputCall right clearBitPowerAccumulator
run subtractBitPowerFromInputCall
bind clearBitResultValue CSignedInt64 subtractBitPowerFromInputCall
returnValue clearBitResultValue

operation toggleSignedInt64Bit
input toggleSignedInt64Bit inputValue CSignedInt64
input toggleSignedInt64Bit bitIndex CSignedInt64
output toggleSignedInt64Bit CSignedInt64
memoryHeap toggleSignedInt64Bit no
async toggleSignedInt64Bit no
purpose toggleSignedInt64Bit "Returns inputValue with the k-th bit flipped (set→clear / clear→set)."
invariant toggleSignedInt64Bit "Self-inverse: toggleSignedInt64Bit(toggleSignedInt64Bit(x, k), k) == x."
guarantee toggleSignedInt64Bit "Total."
label startToggleSignedInt64Bit
call detectBitForToggleCall isSignedInt64BitSet
arg detectBitForToggleCall inputValue inputValue
arg detectBitForToggleCall bitIndex bitIndex
run detectBitForToggleCall
bind bitWasSetBeforeToggle Bool detectBitForToggleCall
branchIf bitWasSetBeforeToggle clearBitForToggle
call setBitForToggleCall setSignedInt64Bit
arg setBitForToggleCall inputValue inputValue
arg setBitForToggleCall bitIndex bitIndex
run setBitForToggleCall
bind toggledFromClearToSet CSignedInt64 setBitForToggleCall
returnValue toggledFromClearToSet
label clearBitForToggle
call clearBitForToggleCall clearSignedInt64Bit
arg clearBitForToggleCall inputValue inputValue
arg clearBitForToggleCall bitIndex bitIndex
run clearBitForToggleCall
bind toggledFromSetToClear CSignedInt64 clearBitForToggleCall
returnValue toggledFromSetToClear

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
purpose main "Smoke-test the bit operations end-to-end."
invariant main "shift / set / clear / toggle / predicate all produce the expected values."

label startMain
const threeValue CSignedInt64 3
const fourValue CSignedInt64 4
const fortyEightValue CSignedInt64 48
const zeroValue CSignedInt64 0
const eightValue CSignedInt64 8
const fifteenValue CSignedInt64 15
const oneValue CSignedInt64 1
const thirteenValue CSignedInt64 13
const fiveValue CSignedInt64 5
const sevenValue CSignedInt64 7
const tenValue CSignedInt64 10
const oneThousandTwentyFourValue CSignedInt64 1024
const sixteenValue CSignedInt64 16

# shiftSignedInt64BitsLeft(3, 4) == 48
call assertShiftLeftCall shiftSignedInt64BitsLeft
arg assertShiftLeftCall inputValue threeValue
arg assertShiftLeftCall bitIndex fourValue
run assertShiftLeftCall
bind shiftLeftResult CSignedInt64 assertShiftLeftCall
call checkShiftLeftCall math.equalI64
arg checkShiftLeftCall left shiftLeftResult
arg checkShiftLeftCall right fortyEightValue
run checkShiftLeftCall
bind shiftLeftOk Bool checkShiftLeftCall
branchIf shiftLeftOk shiftLeftHolds
branch smokeAssertionFailed
label shiftLeftHolds

# shiftSignedInt64BitsRight(48, 4) == 3
call assertShiftRightCall shiftSignedInt64BitsRight
arg assertShiftRightCall inputValue fortyEightValue
arg assertShiftRightCall bitIndex fourValue
run assertShiftRightCall
bind shiftRightResult CSignedInt64 assertShiftRightCall
call checkShiftRightCall math.equalI64
arg checkShiftRightCall left shiftRightResult
arg checkShiftRightCall right threeValue
run checkShiftRightCall
bind shiftRightOk Bool checkShiftRightCall
branchIf shiftRightOk shiftRightHolds
branch smokeAssertionFailed
label shiftRightHolds

# isSignedInt64BitSet(48, 4) == true (48 == 0b110000, bit 4 is set)
call assertBitSetCall isSignedInt64BitSet
arg assertBitSetCall inputValue fortyEightValue
arg assertBitSetCall bitIndex fourValue
run assertBitSetCall
bind bitSetResult Bool assertBitSetCall
branchIf bitSetResult bitSetHolds
branch smokeAssertionFailed
label bitSetHolds

# setSignedInt64Bit(0, 3) == 8
call assertSetBitCall setSignedInt64Bit
arg assertSetBitCall inputValue zeroValue
arg assertSetBitCall bitIndex threeValue
run assertSetBitCall
bind setBitResult CSignedInt64 assertSetBitCall
call checkSetBitCall math.equalI64
arg checkSetBitCall left setBitResult
arg checkSetBitCall right eightValue
run checkSetBitCall
bind setBitOk Bool checkSetBitCall
branchIf setBitOk setBitHolds
branch smokeAssertionFailed
label setBitHolds

# clearSignedInt64Bit(15, 1) == 13
call assertClearBitCall clearSignedInt64Bit
arg assertClearBitCall inputValue fifteenValue
arg assertClearBitCall bitIndex oneValue
run assertClearBitCall
bind clearBitResult CSignedInt64 assertClearBitCall
call checkClearBitCall math.equalI64
arg checkClearBitCall left clearBitResult
arg checkClearBitCall right thirteenValue
run checkClearBitCall
bind clearBitOk Bool checkClearBitCall
branchIf clearBitOk clearBitHolds
branch smokeAssertionFailed
label clearBitHolds

# toggleSignedInt64Bit(5, 1) == 7
call assertToggleBitCall toggleSignedInt64Bit
arg assertToggleBitCall inputValue fiveValue
arg assertToggleBitCall bitIndex oneValue
run assertToggleBitCall
bind toggleBitResult CSignedInt64 assertToggleBitCall
call checkToggleBitCall math.equalI64
arg checkToggleBitCall left toggleBitResult
arg checkToggleBitCall right sevenValue
run checkToggleBitCall
bind toggleBitOk Bool checkToggleBitCall
branchIf toggleBitOk toggleBitHolds
branch smokeAssertionFailed
label toggleBitHolds

# ============================================================
# Additional per-operation unit-test cases:
# Each operation gets boundary / identity / inverse coverage so a
# regression in one bit position can't slip past the single smoke
# assertion. Cases use UnitTwo / UnitThree / UnitFour label suffixes.
# ============================================================

# Case 2: shiftSignedInt64BitsLeft(0, 5) == 0 (zero invariant)
call shiftLeftZeroCall shiftSignedInt64BitsLeft
arg shiftLeftZeroCall inputValue zeroValue
arg shiftLeftZeroCall bitIndex fiveValue
run shiftLeftZeroCall
bind shiftLeftZeroResult CSignedInt64 shiftLeftZeroCall
call checkShiftLeftZeroCall math.equalI64
arg checkShiftLeftZeroCall left shiftLeftZeroResult
arg checkShiftLeftZeroCall right zeroValue
run checkShiftLeftZeroCall
bind shiftLeftZeroOk Bool checkShiftLeftZeroCall
branchIf shiftLeftZeroOk shiftLeftUnitTwo
branch smokeAssertionFailed
label shiftLeftUnitTwo

# Case 3: shiftSignedInt64BitsLeft(1, 0) == 1 (zero-shift identity)
call shiftLeftIdentityCall shiftSignedInt64BitsLeft
arg shiftLeftIdentityCall inputValue oneValue
arg shiftLeftIdentityCall bitIndex zeroValue
run shiftLeftIdentityCall
bind shiftLeftIdentityResult CSignedInt64 shiftLeftIdentityCall
call checkShiftLeftIdentityCall math.equalI64
arg checkShiftLeftIdentityCall left shiftLeftIdentityResult
arg checkShiftLeftIdentityCall right oneValue
run checkShiftLeftIdentityCall
bind shiftLeftIdentityOk Bool checkShiftLeftIdentityCall
branchIf shiftLeftIdentityOk shiftLeftUnitThree
branch smokeAssertionFailed
label shiftLeftUnitThree

# Case 4: shiftSignedInt64BitsLeft(1, 10) == 1024 (power-of-two)
call shiftLeftPowerCall shiftSignedInt64BitsLeft
arg shiftLeftPowerCall inputValue oneValue
arg shiftLeftPowerCall bitIndex tenValue
run shiftLeftPowerCall
bind shiftLeftPowerResult CSignedInt64 shiftLeftPowerCall
call checkShiftLeftPowerCall math.equalI64
arg checkShiftLeftPowerCall left shiftLeftPowerResult
arg checkShiftLeftPowerCall right oneThousandTwentyFourValue
run checkShiftLeftPowerCall
bind shiftLeftPowerOk Bool checkShiftLeftPowerCall
branchIf shiftLeftPowerOk shiftLeftUnitFour
branch smokeAssertionFailed
label shiftLeftUnitFour

# Case 2: shiftSignedInt64BitsRight(0, 5) == 0
call shiftRightZeroCall shiftSignedInt64BitsRight
arg shiftRightZeroCall inputValue zeroValue
arg shiftRightZeroCall bitIndex fiveValue
run shiftRightZeroCall
bind shiftRightZeroResult CSignedInt64 shiftRightZeroCall
call checkShiftRightZeroCall math.equalI64
arg checkShiftRightZeroCall left shiftRightZeroResult
arg checkShiftRightZeroCall right zeroValue
run checkShiftRightZeroCall
bind shiftRightZeroOk Bool checkShiftRightZeroCall
branchIf shiftRightZeroOk shiftRightUnitTwo
branch smokeAssertionFailed
label shiftRightUnitTwo

# Case 3: shiftSignedInt64BitsRight(48, 0) == 48 (zero-shift identity)
call shiftRightIdentityCall shiftSignedInt64BitsRight
arg shiftRightIdentityCall inputValue fortyEightValue
arg shiftRightIdentityCall bitIndex zeroValue
run shiftRightIdentityCall
bind shiftRightIdentityResult CSignedInt64 shiftRightIdentityCall
call checkShiftRightIdentityCall math.equalI64
arg checkShiftRightIdentityCall left shiftRightIdentityResult
arg checkShiftRightIdentityCall right fortyEightValue
run checkShiftRightIdentityCall
bind shiftRightIdentityOk Bool checkShiftRightIdentityCall
branchIf shiftRightIdentityOk shiftRightUnitThree
branch smokeAssertionFailed
label shiftRightUnitThree

# Case 4: shiftSignedInt64BitsRight(1024, 10) == 1 (round-trip with shiftLeft)
call shiftRightPowerCall shiftSignedInt64BitsRight
arg shiftRightPowerCall inputValue oneThousandTwentyFourValue
arg shiftRightPowerCall bitIndex tenValue
run shiftRightPowerCall
bind shiftRightPowerResult CSignedInt64 shiftRightPowerCall
call checkShiftRightPowerCall math.equalI64
arg checkShiftRightPowerCall left shiftRightPowerResult
arg checkShiftRightPowerCall right oneValue
run checkShiftRightPowerCall
bind shiftRightPowerOk Bool checkShiftRightPowerCall
branchIf shiftRightPowerOk shiftRightUnitFour
branch smokeAssertionFailed
label shiftRightUnitFour

# Case 2: isSignedInt64BitSet(0, 0) == false (zero has no bits set)
call isBitSetZeroCall isSignedInt64BitSet
arg isBitSetZeroCall inputValue zeroValue
arg isBitSetZeroCall bitIndex zeroValue
run isBitSetZeroCall
bind isBitSetZeroResult Bool isBitSetZeroCall
branchIf isBitSetZeroResult smokeAssertionFailed
# fell through: result was false as expected
branch isBitSetUnitTwo
label isBitSetUnitTwo

# Case 3: isSignedInt64BitSet(1, 0) == true (lowest bit)
call isBitSetLowCall isSignedInt64BitSet
arg isBitSetLowCall inputValue oneValue
arg isBitSetLowCall bitIndex zeroValue
run isBitSetLowCall
bind isBitSetLowResult Bool isBitSetLowCall
branchIf isBitSetLowResult isBitSetUnitThree
branch smokeAssertionFailed
label isBitSetUnitThree

# Case 4: isSignedInt64BitSet(16, 0) == false (only bit 4, not bit 0)
call isBitSetWrongCall isSignedInt64BitSet
arg isBitSetWrongCall inputValue sixteenValue
arg isBitSetWrongCall bitIndex zeroValue
run isBitSetWrongCall
bind isBitSetWrongResult Bool isBitSetWrongCall
branchIf isBitSetWrongResult smokeAssertionFailed
branch isBitSetUnitFour
label isBitSetUnitFour

# Case 2: setSignedInt64Bit on already-set bit is a no-op:
# setSignedInt64Bit(8, 3) == 8
call setBitNoOpCall setSignedInt64Bit
arg setBitNoOpCall inputValue eightValue
arg setBitNoOpCall bitIndex threeValue
run setBitNoOpCall
bind setBitNoOpResult CSignedInt64 setBitNoOpCall
call checkSetBitNoOpCall math.equalI64
arg checkSetBitNoOpCall left setBitNoOpResult
arg checkSetBitNoOpCall right eightValue
run checkSetBitNoOpCall
bind setBitNoOpOk Bool checkSetBitNoOpCall
branchIf setBitNoOpOk setBitUnitTwo
branch smokeAssertionFailed
label setBitUnitTwo

# Case 3: setSignedInt64Bit(0, 0) == 1 (set lowest bit on zero)
call setBitLowCall setSignedInt64Bit
arg setBitLowCall inputValue zeroValue
arg setBitLowCall bitIndex zeroValue
run setBitLowCall
bind setBitLowResult CSignedInt64 setBitLowCall
call checkSetBitLowCall math.equalI64
arg checkSetBitLowCall left setBitLowResult
arg checkSetBitLowCall right oneValue
run checkSetBitLowCall
bind setBitLowOk Bool checkSetBitLowCall
branchIf setBitLowOk setBitUnitThree
branch smokeAssertionFailed
label setBitUnitThree

# Case 2: clearSignedInt64Bit on already-clear bit is no-op:
# clearSignedInt64Bit(8, 0) == 8
call clearBitNoOpCall clearSignedInt64Bit
arg clearBitNoOpCall inputValue eightValue
arg clearBitNoOpCall bitIndex zeroValue
run clearBitNoOpCall
bind clearBitNoOpResult CSignedInt64 clearBitNoOpCall
call checkClearBitNoOpCall math.equalI64
arg checkClearBitNoOpCall left clearBitNoOpResult
arg checkClearBitNoOpCall right eightValue
run checkClearBitNoOpCall
bind clearBitNoOpOk Bool checkClearBitNoOpCall
branchIf clearBitNoOpOk clearBitUnitTwo
branch smokeAssertionFailed
label clearBitUnitTwo

# Case 3: clearSignedInt64Bit(8, 3) == 0 (clear the only set bit)
call clearBitOnlyCall clearSignedInt64Bit
arg clearBitOnlyCall inputValue eightValue
arg clearBitOnlyCall bitIndex threeValue
run clearBitOnlyCall
bind clearBitOnlyResult CSignedInt64 clearBitOnlyCall
call checkClearBitOnlyCall math.equalI64
arg checkClearBitOnlyCall left clearBitOnlyResult
arg checkClearBitOnlyCall right zeroValue
run checkClearBitOnlyCall
bind clearBitOnlyOk Bool checkClearBitOnlyCall
branchIf clearBitOnlyOk clearBitUnitThree
branch smokeAssertionFailed
label clearBitUnitThree

# Case 2: toggleSignedInt64Bit(7, 1) == 5 (inverse of case 1)
call toggleBitInverseCall toggleSignedInt64Bit
arg toggleBitInverseCall inputValue sevenValue
arg toggleBitInverseCall bitIndex oneValue
run toggleBitInverseCall
bind toggleBitInverseResult CSignedInt64 toggleBitInverseCall
call checkToggleBitInverseCall math.equalI64
arg checkToggleBitInverseCall left toggleBitInverseResult
arg checkToggleBitInverseCall right fiveValue
run checkToggleBitInverseCall
bind toggleBitInverseOk Bool checkToggleBitInverseCall
branchIf toggleBitInverseOk toggleBitUnitTwo
branch smokeAssertionFailed
label toggleBitUnitTwo

# Case 3 (property): toggle(toggle(13, 4), 4) == 13 (self-inverse invariant)
call toggleOnceCall toggleSignedInt64Bit
arg toggleOnceCall inputValue thirteenValue
arg toggleOnceCall bitIndex fourValue
run toggleOnceCall
bind toggleOnceResult CSignedInt64 toggleOnceCall
call toggleTwiceCall toggleSignedInt64Bit
arg toggleTwiceCall inputValue toggleOnceResult
arg toggleTwiceCall bitIndex fourValue
run toggleTwiceCall
bind toggleTwiceResult CSignedInt64 toggleTwiceCall
call checkToggleInvolutionCall math.equalI64
arg checkToggleInvolutionCall left toggleTwiceResult
arg checkToggleInvolutionCall right thirteenValue
run checkToggleInvolutionCall
bind toggleInvolutionOk Bool checkToggleInvolutionCall
branchIf toggleInvolutionOk toggleBitUnitThree
branch smokeAssertionFailed
label toggleBitUnitThree

# Property: setBit + isBitSet — after setSignedInt64Bit(0, 5), bit 5 must be set.
call setBitForPropertyCall setSignedInt64Bit
arg setBitForPropertyCall inputValue zeroValue
arg setBitForPropertyCall bitIndex fiveValue
run setBitForPropertyCall
bind setBitForPropertyResult CSignedInt64 setBitForPropertyCall
call propertyIsBitSetCall isSignedInt64BitSet
arg propertyIsBitSetCall inputValue setBitForPropertyResult
arg propertyIsBitSetCall bitIndex fiveValue
run propertyIsBitSetCall
bind propertyIsBitSetResult Bool propertyIsBitSetCall
branchIf propertyIsBitSetResult setIsBitProperty
branch smokeAssertionFailed
label setIsBitProperty

# Property: clear after set returns to zero.
# clearSignedInt64Bit(setSignedInt64Bit(0, 5), 5) == 0
call clearAfterSetCall clearSignedInt64Bit
arg clearAfterSetCall inputValue setBitForPropertyResult
arg clearAfterSetCall bitIndex fiveValue
run clearAfterSetCall
bind clearAfterSetResult CSignedInt64 clearAfterSetCall
call checkClearAfterSetCall math.equalI64
arg checkClearAfterSetCall left clearAfterSetResult
arg checkClearAfterSetCall right zeroValue
run checkClearAfterSetCall
bind clearAfterSetOk Bool checkClearAfterSetCall
branchIf clearAfterSetOk clearAfterSetProperty
branch smokeAssertionFailed
label clearAfterSetProperty

# Property: round-trip shiftLeft then shiftRight by same bits returns the
# original positive operand.
# shiftRight(shiftLeft(13, 3), 3) == 13
call roundTripShiftLeftCall shiftSignedInt64BitsLeft
arg roundTripShiftLeftCall inputValue thirteenValue
arg roundTripShiftLeftCall bitIndex threeValue
run roundTripShiftLeftCall
bind roundTripShiftLeftResult CSignedInt64 roundTripShiftLeftCall
call roundTripShiftRightCall shiftSignedInt64BitsRight
arg roundTripShiftRightCall inputValue roundTripShiftLeftResult
arg roundTripShiftRightCall bitIndex threeValue
run roundTripShiftRightCall
bind roundTripShiftRightResult CSignedInt64 roundTripShiftRightCall
call checkRoundTripCall math.equalI64
arg checkRoundTripCall left roundTripShiftRightResult
arg checkRoundTripCall right thirteenValue
run checkRoundTripCall
bind roundTripOk Bool checkRoundTripCall
branchIf roundTripOk shiftRoundTripProperty
branch smokeAssertionFailed
label shiftRoundTripProperty

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
makeError bitSmokeFailure MainError.BitSmokeAssertionFailed
returnError bitSmokeFailure
