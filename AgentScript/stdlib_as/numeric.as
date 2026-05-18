# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: integer numeric helpers
# ============================================================
#
# # rationale: small total CSignedInt64 helpers plus a few
#   closed-form aggregate computations. Most are one-liners over
#   math.* primitives; the LCM helper folds a real gcd loop with
#   typed-error handling for the divide-by-zero edge case.
#
# # invariant: total CSignedInt64 -> CSignedInt64 ops drop the
#   Result wrapper. reciprocalFloat64 is total over non-zero
#   doubles; with x = 0 it returns the IEEE-754 infinity. LCM
#   surfaces a typed NumericError.LeastCommonMultipleOfZero
#   variant when either input is 0.
#
# # security: pure value-level math; no allocation; no I/O.
# # timing: constant for the one-liners; O(log min(|a|, |b|)) for
#   leastCommonMultipleSignedInt64 (gcd loop).

project StdNumericSelfTest
target console
runtime AgentRuntime 0.1
entry console main

error NumericError
errorCase NumericError LeastCommonMultipleOfZero

error MainError
errorCase MainError NumericSmokeAssertionFailed
errorCase MainError ConsoleWriteFailed

# section capability
# rationale: smoke-test main writes a single OK line to stdout.
capability stdoutWriteCapability console.stdout write

domainLiteral integerOneStepValue CSignedInt64 1
domainLiteralTrust integerOneStepValue trustedStaticLiteral
domainLiteral integerTwoBaseValue CSignedInt64 2
domainLiteralTrust integerTwoBaseValue trustedStaticLiteral
domainLiteral integerSixDivisor CSignedInt64 6
domainLiteralTrust integerSixDivisor trustedStaticLiteral
domainLiteral integerNegativeOneMultiplier CSignedInt64 -1
domainLiteralTrust integerNegativeOneMultiplier trustedStaticLiteral
domainLiteral integerZeroBoundaryForNumeric CSignedInt64 0
domainLiteralTrust integerZeroBoundaryForNumeric trustedStaticLiteral
domainLiteral floatOneIdentity CFloat64 1.0
domainLiteralTrust floatOneIdentity trustedStaticLiteral

# section numeric.unary

operation incrementSignedInt64
input incrementSignedInt64 inputValue CSignedInt64
output incrementSignedInt64 CSignedInt64
memoryHeap incrementSignedInt64 no
async incrementSignedInt64 no
purpose incrementSignedInt64 "Returns inputValue + 1."
invariant incrementSignedInt64 "Wraps modulo 2^64 at INT64_MAX."
guarantee incrementSignedInt64 "Total."
label startIncrementSignedInt64
call addOneToInputCall math.addI64
arg addOneToInputCall left inputValue
arg addOneToInputCall right integerOneStepValue
run addOneToInputCall
bind incrementedValue CSignedInt64 addOneToInputCall
returnValue incrementedValue

operation decrementSignedInt64
input decrementSignedInt64 inputValue CSignedInt64
output decrementSignedInt64 CSignedInt64
memoryHeap decrementSignedInt64 no
async decrementSignedInt64 no
purpose decrementSignedInt64 "Returns inputValue - 1."
invariant decrementSignedInt64 "Wraps modulo 2^64 at INT64_MIN."
guarantee decrementSignedInt64 "Total."
label startDecrementSignedInt64
call subtractOneFromInputCall math.subtractI64
arg subtractOneFromInputCall left inputValue
arg subtractOneFromInputCall right integerOneStepValue
run subtractOneFromInputCall
bind decrementedValue CSignedInt64 subtractOneFromInputCall
returnValue decrementedValue

operation doubleSignedInt64
input doubleSignedInt64 inputValue CSignedInt64
output doubleSignedInt64 CSignedInt64
memoryHeap doubleSignedInt64 no
async doubleSignedInt64 no
purpose doubleSignedInt64 "Returns inputValue * 2."
guarantee doubleSignedInt64 "Total."
label startDoubleSignedInt64
call multiplyByTwoCall math.multiplyI64
arg multiplyByTwoCall left inputValue
arg multiplyByTwoCall right integerTwoBaseValue
run multiplyByTwoCall
bind doubledValue CSignedInt64 multiplyByTwoCall
returnValue doubledValue

operation halveSignedInt64
input halveSignedInt64 inputValue CSignedInt64
output halveSignedInt64 CSignedInt64
memoryHeap halveSignedInt64 no
async halveSignedInt64 no
purpose halveSignedInt64 "Returns inputValue / 2 (floor toward zero)."
guarantee halveSignedInt64 "Total."
label startHalveSignedInt64
call divideByTwoCall math.divideI64
arg divideByTwoCall left inputValue
arg divideByTwoCall right integerTwoBaseValue
run divideByTwoCall
bind halvedValue CSignedInt64 divideByTwoCall
returnValue halvedValue

operation negateSignedInt64
input negateSignedInt64 inputValue CSignedInt64
output negateSignedInt64 CSignedInt64
memoryHeap negateSignedInt64 no
async negateSignedInt64 no
purpose negateSignedInt64 "Returns -inputValue."
warning negateSignedInt64 "INT64_MIN negated is still INT64_MIN (two's-complement wraparound)."
guarantee negateSignedInt64 "Total."
label startNegateSignedInt64
call multiplyByNegativeOneForNegateCall math.multiplyI64
arg multiplyByNegativeOneForNegateCall left inputValue
arg multiplyByNegativeOneForNegateCall right integerNegativeOneMultiplier
run multiplyByNegativeOneForNegateCall
bind negatedValue CSignedInt64 multiplyByNegativeOneForNegateCall
returnValue negatedValue

operation reciprocalFloat64
input reciprocalFloat64 inputValue CFloat64
output reciprocalFloat64 CFloat64
memoryHeap reciprocalFloat64 no
async reciprocalFloat64 no
purpose reciprocalFloat64 "Returns 1.0 / inputValue."
warning reciprocalFloat64 "Division by zero produces an IEEE-754 infinity; NaN inputs propagate."
guarantee reciprocalFloat64 "Total over CFloat64."
label startReciprocalFloat64
call divideOneByInputCall math.divideF64
arg divideOneByInputCall left floatOneIdentity
arg divideOneByInputCall right inputValue
run divideOneByInputCall
bind reciprocalResult CFloat64 divideOneByInputCall
returnValue reciprocalResult

# section numeric.aggregateSums

operation sumSignedInt64OneThroughN
input sumSignedInt64OneThroughN inputValue CSignedInt64
output sumSignedInt64OneThroughN CSignedInt64
memoryHeap sumSignedInt64OneThroughN no
async sumSignedInt64OneThroughN no
purpose sumSignedInt64OneThroughN "Returns 1+2+...+inputValue via the Gauss closed form n*(n+1)/2."
invariant sumSignedInt64OneThroughN "Equals the nth triangular number for non-negative inputs."
warning sumSignedInt64OneThroughN "Overflows silently for inputValue beyond ~2^31."
guarantee sumSignedInt64OneThroughN "Total."
label startSumSignedInt64OneThroughN
call addOneToInputForSumCall math.addI64
arg addOneToInputForSumCall left inputValue
arg addOneToInputForSumCall right integerOneStepValue
run addOneToInputForSumCall
bind inputPlusOne I64 addOneToInputForSumCall
call multiplyForGaussSumCall math.multiplyI64
arg multiplyForGaussSumCall left inputValue
arg multiplyForGaussSumCall right inputPlusOne
run multiplyForGaussSumCall
bind productForGaussSum I64 multiplyForGaussSumCall
call divideByTwoForGaussSumCall math.divideI64
arg divideByTwoForGaussSumCall left productForGaussSum
arg divideByTwoForGaussSumCall right integerTwoBaseValue
run divideByTwoForGaussSumCall
bind gaussSumResult CSignedInt64 divideByTwoForGaussSumCall
returnValue gaussSumResult

operation sumSignedInt64SquaresOneThroughN
input sumSignedInt64SquaresOneThroughN inputValue CSignedInt64
output sumSignedInt64SquaresOneThroughN CSignedInt64
memoryHeap sumSignedInt64SquaresOneThroughN no
async sumSignedInt64SquaresOneThroughN no
purpose sumSignedInt64SquaresOneThroughN "Returns 1^2+...+inputValue^2 via the closed form n*(n+1)*(2n+1)/6."
warning sumSignedInt64SquaresOneThroughN "Overflows silently for inputValue beyond ~2^21."
guarantee sumSignedInt64SquaresOneThroughN "Total."
label startSumSignedInt64SquaresOneThroughN
call computeNPlusOneCall math.addI64
arg computeNPlusOneCall left inputValue
arg computeNPlusOneCall right integerOneStepValue
run computeNPlusOneCall
bind squareNPlusOne I64 computeNPlusOneCall
call computeTwoNCall math.multiplyI64
arg computeTwoNCall left inputValue
arg computeTwoNCall right integerTwoBaseValue
run computeTwoNCall
bind squareTwoN I64 computeTwoNCall
call computeTwoNPlusOneCall math.addI64
arg computeTwoNPlusOneCall left squareTwoN
arg computeTwoNPlusOneCall right integerOneStepValue
run computeTwoNPlusOneCall
bind squareTwoNPlusOne I64 computeTwoNPlusOneCall
call firstSquareProductCall math.multiplyI64
arg firstSquareProductCall left inputValue
arg firstSquareProductCall right squareNPlusOne
run firstSquareProductCall
bind firstSquareProductValue I64 firstSquareProductCall
call secondSquareProductCall math.multiplyI64
arg secondSquareProductCall left firstSquareProductValue
arg secondSquareProductCall right squareTwoNPlusOne
run secondSquareProductCall
bind secondSquareProductValue I64 secondSquareProductCall
call divideBySixForSquareSumCall math.divideI64
arg divideBySixForSquareSumCall left secondSquareProductValue
arg divideBySixForSquareSumCall right integerSixDivisor
run divideBySixForSquareSumCall
bind sumOfSquaresResult CSignedInt64 divideBySixForSquareSumCall
returnValue sumOfSquaresResult

operation sumSignedInt64CubesOneThroughN
input sumSignedInt64CubesOneThroughN inputValue CSignedInt64
output sumSignedInt64CubesOneThroughN CSignedInt64
memoryHeap sumSignedInt64CubesOneThroughN no
async sumSignedInt64CubesOneThroughN no
purpose sumSignedInt64CubesOneThroughN "Returns 1^3+...+inputValue^3 via the identity (sum 1..n)^2."
guarantee sumSignedInt64CubesOneThroughN "Total."
label startSumSignedInt64CubesOneThroughN
call delegateToTriangularSumCall sumSignedInt64OneThroughN
arg delegateToTriangularSumCall inputValue inputValue
run delegateToTriangularSumCall
bind triangularSumValue CSignedInt64 delegateToTriangularSumCall
call squareTriangularSumCall math.multiplyI64
arg squareTriangularSumCall left triangularSumValue
arg squareTriangularSumCall right triangularSumValue
run squareTriangularSumCall
bind sumOfCubesResult CSignedInt64 squareTriangularSumCall
returnValue sumOfCubesResult

operation triangularNumberSignedInt64
input triangularNumberSignedInt64 inputValue CSignedInt64
output triangularNumberSignedInt64 CSignedInt64
memoryHeap triangularNumberSignedInt64 no
async triangularNumberSignedInt64 no
purpose triangularNumberSignedInt64 "Returns the nth triangular number — alias for sumSignedInt64OneThroughN."
guarantee triangularNumberSignedInt64 "Total."
label startTriangularNumberSignedInt64
call delegateToSumOneToNCall sumSignedInt64OneThroughN
arg delegateToSumOneToNCall inputValue inputValue
run delegateToSumOneToNCall
bind triangularResultValue CSignedInt64 delegateToSumOneToNCall
returnValue triangularResultValue

# section numeric.gcdLcm

operation leastCommonMultipleSignedInt64
input leastCommonMultipleSignedInt64 leftValue CSignedInt64
input leastCommonMultipleSignedInt64 rightValue CSignedInt64
output leastCommonMultipleSignedInt64 Result CSignedInt64 NumericError
memoryHeap leastCommonMultipleSignedInt64 no
async leastCommonMultipleSignedInt64 no
purpose leastCommonMultipleSignedInt64 "Returns |leftValue * rightValue| / gcd(leftValue, rightValue). Surfaces NumericError.LeastCommonMultipleOfZero when either input is zero."
invariant leastCommonMultipleSignedInt64 "Result is non-negative when defined."
failure leastCommonMultipleSignedInt64 LeastCommonMultipleOfZero "Returned when either input is 0 (LCM is undefined for zero operands)."
guarantee leastCommonMultipleSignedInt64 "Defined for every (non-zero, non-zero) input pair."
label startLeastCommonMultipleSignedInt64
call detectLeftIsZeroForLcmCall math.equalI64
arg detectLeftIsZeroForLcmCall left leftValue
arg detectLeftIsZeroForLcmCall right integerZeroBoundaryForNumeric
run detectLeftIsZeroForLcmCall
bind leftIsZeroForLcm Bool detectLeftIsZeroForLcmCall
branchIf leftIsZeroForLcm raiseLcmOfZero
call detectRightIsZeroForLcmCall math.equalI64
arg detectRightIsZeroForLcmCall left rightValue
arg detectRightIsZeroForLcmCall right integerZeroBoundaryForNumeric
run detectRightIsZeroForLcmCall
bind rightIsZeroForLcm Bool detectRightIsZeroForLcmCall
branchIf rightIsZeroForLcm raiseLcmOfZero

# Compute gcd via Euclid using absolute values.
# Initialize working dividend/divisor to the input values, then
# conditionally overwrite with the negated value when the input is
# negative. The intermediate read of gcdRunningDividend /
# gcdRunningDivisor inside the negation call's arg keeps the
# linter's flow-insensitive dead-store check satisfied on the
# negative branch.
var gcdRunningDividend I64 0
set gcdRunningDividend leftValue
var gcdRunningDivisor I64 0
set gcdRunningDivisor rightValue
call detectLeftIsNegativeForLcmCall math.lessThanI64
arg detectLeftIsNegativeForLcmCall left leftValue
arg detectLeftIsNegativeForLcmCall right integerZeroBoundaryForNumeric
run detectLeftIsNegativeForLcmCall
bind leftIsNegativeForLcm Bool detectLeftIsNegativeForLcmCall
branchIf leftIsNegativeForLcm negateLeftForLcm
branch checkRightForLcmAbs
label negateLeftForLcm
call negateLeftForLcmCall math.multiplyI64
arg negateLeftForLcmCall left gcdRunningDividend
arg negateLeftForLcmCall right integerNegativeOneMultiplier
run negateLeftForLcmCall
bind absoluteLeftForLcm I64 negateLeftForLcmCall
set gcdRunningDividend absoluteLeftForLcm
branch checkRightForLcmAbs
label checkRightForLcmAbs
call detectRightIsNegativeForLcmCall math.lessThanI64
arg detectRightIsNegativeForLcmCall left rightValue
arg detectRightIsNegativeForLcmCall right integerZeroBoundaryForNumeric
run detectRightIsNegativeForLcmCall
bind rightIsNegativeForLcm Bool detectRightIsNegativeForLcmCall
branchIf rightIsNegativeForLcm negateRightForLcm
branch enterGcdLoop
label negateRightForLcm
call negateRightForLcmCall math.multiplyI64
arg negateRightForLcmCall left gcdRunningDivisor
arg negateRightForLcmCall right integerNegativeOneMultiplier
run negateRightForLcmCall
bind absoluteRightForLcm I64 negateRightForLcmCall
set gcdRunningDivisor absoluteRightForLcm
branch enterGcdLoop
label enterGcdLoop
label gcdEuclidLoop
call detectGcdDivisorIsZeroCall math.equalI64
arg detectGcdDivisorIsZeroCall left gcdRunningDivisor
arg detectGcdDivisorIsZeroCall right integerZeroBoundaryForNumeric
run detectGcdDivisorIsZeroCall
bind gcdDivisorIsZero Bool detectGcdDivisorIsZeroCall
branchIf gcdDivisorIsZero gcdLoopComplete
call computeGcdRemainderCall math.moduloI64
arg computeGcdRemainderCall left gcdRunningDividend
arg computeGcdRemainderCall right gcdRunningDivisor
run computeGcdRemainderCall
bind gcdRemainderValue I64 computeGcdRemainderCall
set gcdRunningDividend gcdRunningDivisor
set gcdRunningDivisor gcdRemainderValue
branch gcdEuclidLoop
label gcdLoopComplete

# product / gcd
call computeLcmProductCall math.multiplyI64
arg computeLcmProductCall left leftValue
arg computeLcmProductCall right rightValue
run computeLcmProductCall
bind lcmProductValue I64 computeLcmProductCall
call divideLcmProductByGcdCall math.divideI64
arg divideLcmProductByGcdCall left lcmProductValue
arg divideLcmProductByGcdCall right gcdRunningDividend
run divideLcmProductByGcdCall
bind rawLcmValue I64 divideLcmProductByGcdCall

# Take absolute value of result.
call detectLcmNegativeCall math.lessThanI64
arg detectLcmNegativeCall left rawLcmValue
arg detectLcmNegativeCall right integerZeroBoundaryForNumeric
run detectLcmNegativeCall
bind lcmIsNegative Bool detectLcmNegativeCall
branchIf lcmIsNegative absoluteLcmFromNegation
returnOk rawLcmValue
label absoluteLcmFromNegation
call negateRawLcmCall math.multiplyI64
arg negateRawLcmCall left rawLcmValue
arg negateRawLcmCall right integerNegativeOneMultiplier
run negateRawLcmCall
bind absoluteLcmValue CSignedInt64 negateRawLcmCall
returnOk absoluteLcmValue

label raiseLcmOfZero
makeError lcmOfZeroFailure NumericError.LeastCommonMultipleOfZero
returnError lcmOfZeroFailure

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
