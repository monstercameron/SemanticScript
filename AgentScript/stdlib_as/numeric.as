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
var gcdRunningDividend I64 0
var gcdRunningDivisor I64 0
call detectLeftIsNegativeForLcmCall math.lessThanI64
arg detectLeftIsNegativeForLcmCall left leftValue
arg detectLeftIsNegativeForLcmCall right integerZeroBoundaryForNumeric
run detectLeftIsNegativeForLcmCall
bind leftIsNegativeForLcm Bool detectLeftIsNegativeForLcmCall
branchIf leftIsNegativeForLcm negateLeftForLcm
set gcdRunningDividend leftValue
branch checkRightForLcmAbs
label negateLeftForLcm
call negateLeftForLcmCall math.multiplyI64
arg negateLeftForLcmCall left leftValue
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
set gcdRunningDivisor rightValue
branch enterGcdLoop
label negateRightForLcm
call negateRightForLcmCall math.multiplyI64
arg negateRightForLcmCall left rightValue
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

const successMessageText CNullTerminatedByteString "OK"
call writeSuccessLineCall console.writeLine
arg writeSuccessLineCall console console
arg writeSuccessLineCall text successMessageText
run writeSuccessLineCall
ignoreOk writeSuccessLineCall Void
const exitOkCode ExitCode 0
returnOk exitOkCode

label smokeAssertionFailed
makeError numericSmokeFailure MainError.NumericSmokeAssertionFailed
returnError numericSmokeFailure
