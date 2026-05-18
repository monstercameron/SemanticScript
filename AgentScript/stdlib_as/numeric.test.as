# ============================================================
# AGENTSCRIPT STDLIB TESTS: numeric
# ============================================================
#
# Companion smoke + extended unit tests for stdlib_as/numeric.as.
# Imports the numeric module and asserts every exported helper
# (increment / decrement / double / halve / negate / reciprocal /
# triangular sums / squares / cubes / LCM) plus boundary cases
# and round-trip / symmetry property tests.
#
# Pattern: stdlib_as/foo.as ships pure-module operations only;
# stdlib_as/foo.test.as carries every smoke / unit test for it.

project StdNumericTest
target console
runtime AgentRuntime 0.1
entry console main

importModule numeric

error MainError
errorCase MainError NumericSmokeAssertionFailed
errorCase MainError ConsoleWriteFailed

# section capability
# rationale: smoke-test main writes a single OK line to stdout.
capability stdoutWriteCapability console.stdout write

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
purpose main "Smoke-test the numeric helpers."
invariant main "sumSignedInt64OneThroughN(100) == 5050; LCM(12, 18) == 36."

label startMain

# sumSignedInt64OneThroughN(100) == 5050
const oneHundredInput CSignedInt64 100
const expectedTriangularSumOf100 CSignedInt64 5050
call assertGaussSumCall sumSignedInt64OneThroughN
arg assertGaussSumCall inputValue oneHundredInput
run assertGaussSumCall
bind gaussSumActualResult CSignedInt64 assertGaussSumCall
call checkGaussSumCall math.equalI64
arg checkGaussSumCall left gaussSumActualResult
arg checkGaussSumCall right expectedTriangularSumOf100
run checkGaussSumCall
bind gaussSumOk Bool checkGaussSumCall
branchIf gaussSumOk gaussSumHolds
branch smokeAssertionFailed
label gaussSumHolds

# LCM(12, 18) == 36
const twelveValue CSignedInt64 12
const eighteenValue CSignedInt64 18
const thirtySixExpectedLcm CSignedInt64 36
call assertLcmCall leastCommonMultipleSignedInt64
arg assertLcmCall leftValue twelveValue
arg assertLcmCall rightValue eighteenValue
run assertLcmCall
bindOk lcmActualResult CSignedInt64 assertLcmCall
call checkLcmCall math.equalI64
arg checkLcmCall left lcmActualResult
arg checkLcmCall right thirtySixExpectedLcm
run checkLcmCall
bind lcmOk Bool checkLcmCall
branchIf lcmOk lcmHolds
branch smokeAssertionFailed
label lcmHolds

# ============================================================
# Extended unit tests: covers 9 ops the smoke previously omitted
# (increment / decrement / double / halve / negate / reciprocal /
# sumSquares / sumCubes / triangularNumber), plus boundary cases.
# ============================================================

const zeroNum CSignedInt64 0
const oneNum CSignedInt64 1
const twoNum CSignedInt64 2
const threeNum CSignedInt64 3
const fiveNum CSignedInt64 5
const sixNum CSignedInt64 6
const tenNum CSignedInt64 10
const fourteenNum CSignedInt64 14
const fifteenNum CSignedInt64 15
const fiftyFiveNum CSignedInt64 55
const minusFiveNum CSignedInt64 -5
const minusOneNum CSignedInt64 -1

# increment(5) == 6
call incCall incrementSignedInt64
arg incCall inputValue fiveNum
run incCall
bind incResult CSignedInt64 incCall
call incCheckCall math.equalI64
arg incCheckCall left incResult
arg incCheckCall right sixNum
run incCheckCall
bind incOk Bool incCheckCall
branchIf incOk incHolds
branch smokeAssertionFailed
label incHolds

# increment(-1) == 0 (negative input)
call incNegCall incrementSignedInt64
arg incNegCall inputValue minusOneNum
run incNegCall
bind incNegResult CSignedInt64 incNegCall
call incNegCheckCall math.equalI64
arg incNegCheckCall left incNegResult
arg incNegCheckCall right zeroNum
run incNegCheckCall
bind incNegOk Bool incNegCheckCall
branchIf incNegOk incNegHolds
branch smokeAssertionFailed
label incNegHolds

# decrement(6) == 5 (inverse of increment)
call decCall decrementSignedInt64
arg decCall inputValue sixNum
run decCall
bind decResult CSignedInt64 decCall
call decCheckCall math.equalI64
arg decCheckCall left decResult
arg decCheckCall right fiveNum
run decCheckCall
bind decOk Bool decCheckCall
branchIf decOk decHolds
branch smokeAssertionFailed
label decHolds

# decrement(0) == -1
call decZeroCall decrementSignedInt64
arg decZeroCall inputValue zeroNum
run decZeroCall
bind decZeroResult CSignedInt64 decZeroCall
call decZeroCheckCall math.equalI64
arg decZeroCheckCall left decZeroResult
arg decZeroCheckCall right minusOneNum
run decZeroCheckCall
bind decZeroOk Bool decZeroCheckCall
branchIf decZeroOk decZeroHolds
branch smokeAssertionFailed
label decZeroHolds

# double(5) == 10
call doubleCall doubleSignedInt64
arg doubleCall inputValue fiveNum
run doubleCall
bind doubleResult CSignedInt64 doubleCall
call doubleCheckCall math.equalI64
arg doubleCheckCall left doubleResult
arg doubleCheckCall right tenNum
run doubleCheckCall
bind doubleOk Bool doubleCheckCall
branchIf doubleOk doubleHolds
branch smokeAssertionFailed
label doubleHolds

# double(0) == 0
call doubleZeroCall doubleSignedInt64
arg doubleZeroCall inputValue zeroNum
run doubleZeroCall
bind doubleZeroResult CSignedInt64 doubleZeroCall
call doubleZeroCheckCall math.equalI64
arg doubleZeroCheckCall left doubleZeroResult
arg doubleZeroCheckCall right zeroNum
run doubleZeroCheckCall
bind doubleZeroOk Bool doubleZeroCheckCall
branchIf doubleZeroOk doubleZeroHolds
branch smokeAssertionFailed
label doubleZeroHolds

# halve(10) == 5 (inverse of double)
call halveCall halveSignedInt64
arg halveCall inputValue tenNum
run halveCall
bind halveResult CSignedInt64 halveCall
call halveCheckCall math.equalI64
arg halveCheckCall left halveResult
arg halveCheckCall right fiveNum
run halveCheckCall
bind halveOk Bool halveCheckCall
branchIf halveOk halveHolds
branch smokeAssertionFailed
label halveHolds

# halve(1) == 0 (integer truncation toward zero)
call halveOneCall halveSignedInt64
arg halveOneCall inputValue oneNum
run halveOneCall
bind halveOneResult CSignedInt64 halveOneCall
call halveOneCheckCall math.equalI64
arg halveOneCheckCall left halveOneResult
arg halveOneCheckCall right zeroNum
run halveOneCheckCall
bind halveOneOk Bool halveOneCheckCall
branchIf halveOneOk halveOneHolds
branch smokeAssertionFailed
label halveOneHolds

# negate(5) == -5
call negateCall negateSignedInt64
arg negateCall inputValue fiveNum
run negateCall
bind negateResult CSignedInt64 negateCall
call negateCheckCall math.equalI64
arg negateCheckCall left negateResult
arg negateCheckCall right minusFiveNum
run negateCheckCall
bind negateOk Bool negateCheckCall
branchIf negateOk negateHolds
branch smokeAssertionFailed
label negateHolds

# negate(-5) == 5 (self-inverse on negatives)
call negateNegCall negateSignedInt64
arg negateNegCall inputValue minusFiveNum
run negateNegCall
bind negateNegResult CSignedInt64 negateNegCall
call negateNegCheckCall math.equalI64
arg negateNegCheckCall left negateNegResult
arg negateNegCheckCall right fiveNum
run negateNegCheckCall
bind negateNegOk Bool negateNegCheckCall
branchIf negateNegOk negateNegHolds
branch smokeAssertionFailed
label negateNegHolds

# negate(0) == 0
call negateZeroCall negateSignedInt64
arg negateZeroCall inputValue zeroNum
run negateZeroCall
bind negateZeroResult CSignedInt64 negateZeroCall
call negateZeroCheckCall math.equalI64
arg negateZeroCheckCall left negateZeroResult
arg negateZeroCheckCall right zeroNum
run negateZeroCheckCall
bind negateZeroOk Bool negateZeroCheckCall
branchIf negateZeroOk negateZeroHolds
branch smokeAssertionFailed
label negateZeroHolds

# reciprocal(2.0) ≈ 0.5 (within tolerance)
const twoFloat CFloat64 2.0
const halfFloat CFloat64 0.5
const recipTol CFloat64 0.0001
call reciprocalCall reciprocalFloat64
arg reciprocalCall inputValue twoFloat
run reciprocalCall
bind reciprocalResult CFloat64 reciprocalCall
call reciprocalDiffCall math.subtractF64
arg reciprocalDiffCall left reciprocalResult
arg reciprocalDiffCall right halfFloat
run reciprocalDiffCall
bind reciprocalDiff CFloat64 reciprocalDiffCall
# absolute value of difference: if negative, multiply by -1
var reciprocalAbsAccum CFloat64 0.0
set reciprocalAbsAccum reciprocalDiff
const zeroFloatRecip CFloat64 0.0
const negOneFloatRecip CFloat64 -1.0
call reciprocalNegCheckCall math.lessThanF64
arg reciprocalNegCheckCall left reciprocalAbsAccum
arg reciprocalNegCheckCall right zeroFloatRecip
run reciprocalNegCheckCall
bind reciprocalIsNeg Bool reciprocalNegCheckCall
branchIf reciprocalIsNeg flipReciprocal
branch checkReciprocalTol
label flipReciprocal
call reciprocalFlipCall math.multiplyF64
arg reciprocalFlipCall left reciprocalAbsAccum
arg reciprocalFlipCall right negOneFloatRecip
run reciprocalFlipCall
bind reciprocalFlipped CFloat64 reciprocalFlipCall
set reciprocalAbsAccum reciprocalFlipped
branch checkReciprocalTol
label checkReciprocalTol
call reciprocalCheckCall math.lessThanF64
arg reciprocalCheckCall left reciprocalAbsAccum
arg reciprocalCheckCall right recipTol
run reciprocalCheckCall
bind reciprocalOk Bool reciprocalCheckCall
branchIf reciprocalOk reciprocalHolds
branch smokeAssertionFailed
label reciprocalHolds

# triangularNumberSignedInt64(10) == 55 (1+2+...+10)
call triangularCall triangularNumberSignedInt64
arg triangularCall inputValue tenNum
run triangularCall
bind triangularResult CSignedInt64 triangularCall
call triangularCheckCall math.equalI64
arg triangularCheckCall left triangularResult
arg triangularCheckCall right fiftyFiveNum
run triangularCheckCall
bind triangularOk Bool triangularCheckCall
branchIf triangularOk triangularHolds
branch smokeAssertionFailed
label triangularHolds

# triangularNumberSignedInt64(0) == 0 (boundary)
call triangularZeroCall triangularNumberSignedInt64
arg triangularZeroCall inputValue zeroNum
run triangularZeroCall
bind triangularZeroResult CSignedInt64 triangularZeroCall
call triangularZeroCheckCall math.equalI64
arg triangularZeroCheckCall left triangularZeroResult
arg triangularZeroCheckCall right zeroNum
run triangularZeroCheckCall
bind triangularZeroOk Bool triangularZeroCheckCall
branchIf triangularZeroOk triangularZeroHolds
branch smokeAssertionFailed
label triangularZeroHolds

# sumSignedInt64SquaresOneThroughN(3) == 14 (1+4+9)
call sumSqCall sumSignedInt64SquaresOneThroughN
arg sumSqCall inputValue threeNum
run sumSqCall
bind sumSqResult CSignedInt64 sumSqCall
call sumSqCheckCall math.equalI64
arg sumSqCheckCall left sumSqResult
arg sumSqCheckCall right fourteenNum
run sumSqCheckCall
bind sumSqOk Bool sumSqCheckCall
branchIf sumSqOk sumSqHolds
branch smokeAssertionFailed
label sumSqHolds

# sumSignedInt64CubesOneThroughN(2) == 9 (1+8)
const nineNum CSignedInt64 9
call sumCubesCall sumSignedInt64CubesOneThroughN
arg sumCubesCall inputValue twoNum
run sumCubesCall
bind sumCubesResult CSignedInt64 sumCubesCall
call sumCubesCheckCall math.equalI64
arg sumCubesCheckCall left sumCubesResult
arg sumCubesCheckCall right nineNum
run sumCubesCheckCall
bind sumCubesOk Bool sumCubesCheckCall
branchIf sumCubesOk sumCubesHolds
branch smokeAssertionFailed
label sumCubesHolds

# sumSignedInt64CubesOneThroughN(3) == 36 (1+8+27); also equal to triangular(3)^2 = 6^2
call sumCubes3Call sumSignedInt64CubesOneThroughN
arg sumCubes3Call inputValue threeNum
run sumCubes3Call
bind sumCubes3Result CSignedInt64 sumCubes3Call
call sumCubes3CheckCall math.equalI64
arg sumCubes3CheckCall left sumCubes3Result
arg sumCubes3CheckCall right thirtySixExpectedLcm
run sumCubes3CheckCall
bind sumCubes3Ok Bool sumCubes3CheckCall
branchIf sumCubes3Ok sumCubes3Holds
branch smokeAssertionFailed
label sumCubes3Holds

# Property: increment then decrement is identity. increment(decrement(5)) == 5
call propDecCall decrementSignedInt64
arg propDecCall inputValue fiveNum
run propDecCall
bind propDecResult CSignedInt64 propDecCall
call propIncCall incrementSignedInt64
arg propIncCall inputValue propDecResult
run propIncCall
bind propIncResult CSignedInt64 propIncCall
call propRoundCheckCall math.equalI64
arg propRoundCheckCall left propIncResult
arg propRoundCheckCall right fiveNum
run propRoundCheckCall
bind propRoundOk Bool propRoundCheckCall
branchIf propRoundOk propRoundHolds
branch smokeAssertionFailed
label propRoundHolds

# Property: halve(double(x)) == x for even-friendly x. halve(double(15)) == 15
call propDoubleCall doubleSignedInt64
arg propDoubleCall inputValue fifteenNum
run propDoubleCall
bind propDoubleResult CSignedInt64 propDoubleCall
call propHalveCall halveSignedInt64
arg propHalveCall inputValue propDoubleResult
run propHalveCall
bind propHalveResult CSignedInt64 propHalveCall
call propHalveCheckCall math.equalI64
arg propHalveCheckCall left propHalveResult
arg propHalveCheckCall right fifteenNum
run propHalveCheckCall
bind propHalveOk Bool propHalveCheckCall
branchIf propHalveOk propHalveHolds
branch smokeAssertionFailed
label propHalveHolds

# Property: LCM is symmetric — LCM(18, 12) == LCM(12, 18) == 36
call lcmSymCall leastCommonMultipleSignedInt64
arg lcmSymCall leftValue eighteenValue
arg lcmSymCall rightValue twelveValue
run lcmSymCall
bindOk lcmSymResult CSignedInt64 lcmSymCall
call lcmSymCheckCall math.equalI64
arg lcmSymCheckCall left lcmSymResult
arg lcmSymCheckCall right thirtySixExpectedLcm
run lcmSymCheckCall
bind lcmSymOk Bool lcmSymCheckCall
branchIf lcmSymOk lcmSymHolds
branch smokeAssertionFailed
label lcmSymHolds

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
makeError numericSmokeFailure MainError.NumericSmokeAssertionFailed
returnError numericSmokeFailure
