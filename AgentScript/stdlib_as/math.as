# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: integer math helpers
# ============================================================
#
# # rationale: pure-AS integer math — sqrt, factorial, primality,
#   power-of-two tests, bit counts. Every operation lowers to math.*
#   primitives plus branching; no libc math.h dependency.
#
# # invariant: every operation is total over its declared CSignedInt64
#   domain. Predicates (isSignedInt64Prime / IsPowerOfTwo / IsEven /
#   IsOdd / IsWithinInclusiveRange) return Bool directly — no more
#   round-trips through "0 or 1 in a CSignedInt32".
#
# # security: pure value-level computation. No I/O. No allocation.
#
# # timing: integerSquareRoot is O(log n) (Newton iterations);
#   factorial is O(n); isSignedInt64Prime is O(sqrt(n)); bit counts
#   are O(64) — acceptable for tooling, not for hot loops.
#
# # observability: no logs; consumers wrap when needed.

project StdMathSelfTest
target console
runtime AgentRuntime 0.1
entry console main

error MainError
errorCase MainError MathSmokeAssertionFailed
errorCase MainError ConsoleWriteFailed

# section capability
# rationale: smoke-test main writes a single OK line to stdout.
capability stdoutWriteCapability console.stdout write


operation integerSquareRootSignedInt64
input integerSquareRootSignedInt64 inputValue CSignedInt64
output integerSquareRootSignedInt64 CSignedInt64
memoryHeap integerSquareRootSignedInt64 no
memoryStackLimit integerSquareRootSignedInt64 1024
async integerSquareRootSignedInt64 no
purpose integerSquareRootSignedInt64 "Returns floor(sqrt(inputValue)) for inputValue >= 0 via Newton iteration; returns 0 for inputValue <= 0."
invariant integerSquareRootSignedInt64 "For n >= 0, result*result <= n < (result+1)*(result+1)."
guarantee integerSquareRootSignedInt64 "Total."

label startIntegerSquareRootSignedInt64
const zeroI64 I64 0
const twoI64 I64 2

# n <= 0 -> 0
call leZeroCall math.lessThanOrEqualI64
arg leZeroCall left inputValue
arg leZeroCall right zeroI64
run leZeroCall
bind leZero Bool leZeroCall
branchIf leZero intSqrtZero

# Initial guess: n itself.
var guess I64 0
set guess inputValue

label sqrtLoop
# next = (guess + n/guess) / 2
call divCall math.divideI64
arg divCall left inputValue
arg divCall right guess
run divCall
bind quot I64 divCall

call sumCall math.addI64
arg sumCall left guess
arg sumCall right quot
run sumCall
bind sumGuess I64 sumCall

call halveCall math.divideI64
arg halveCall left sumGuess
arg halveCall right twoI64
run halveCall
bind nextGuess I64 halveCall

# Stop when next >= guess (no further improvement).
call notImprovingCall math.greaterThanOrEqualI64
arg notImprovingCall left nextGuess
arg notImprovingCall right guess
run notImprovingCall
bind notImproving Bool notImprovingCall
branchIf notImproving intSqrtDone

set guess nextGuess
branch sqrtLoop

label intSqrtDone
returnValue guess

label intSqrtZero
returnValue zeroI64


operation factorialSignedInt64
input factorialSignedInt64 inputValue CSignedInt64
output factorialSignedInt64 CSignedInt64
memoryHeap factorialSignedInt64 no
memoryStackLimit factorialSignedInt64 1024
async factorialSignedInt64 no
purpose factorialSignedInt64 "Returns inputValue! by repeated multiplication. Defined for inputValue in [0, 20]; n > 20 overflows CSignedInt64 silently."
invariant factorialSignedInt64 "factorialSignedInt64(0) == 1 (convention)."
warning factorialSignedInt64 "Wraps silently above 20! — no overflow error surfaced."
guarantee factorialSignedInt64 "Total over the CSignedInt64 domain (with overflow wrap)."

label startFactorialSignedInt64
const zeroFac I64 0
const oneFac I64 1

call nLeZeroCall math.lessThanOrEqualI64
arg nLeZeroCall left inputValue
arg nLeZeroCall right zeroFac
run nLeZeroCall
bind nLeZero Bool nLeZeroCall
branchIf nLeZero factorialOne

var product I64 1
var i I64 1
label factorialLoop
call doneCall math.greaterThanI64
arg doneCall left i
arg doneCall right inputValue
run doneCall
bind done Bool doneCall
branchIf done factorialReturn
call mulCall math.multiplyI64
arg mulCall left product
arg mulCall right i
run mulCall
bind nextProd I64 mulCall
set product nextProd
call incCall math.addI64
arg incCall left i
arg incCall right oneFac
run incCall
bind nextI I64 incCall
set i nextI
branch factorialLoop
label factorialReturn
returnValue product
label factorialOne
returnValue oneFac


operation isSignedInt64Prime
input isSignedInt64Prime inputValue CSignedInt64
output isSignedInt64Prime Bool
memoryHeap isSignedInt64Prime no
memoryStackLimit isSignedInt64Prime 1024
async isSignedInt64Prime no
purpose isSignedInt64Prime "Returns true when inputValue is prime; n <= 1 returns false. Tests divisibility by 2 then odd numbers up to floor(sqrt(n))."
invariant isSignedInt64Prime "Exact for inputValue in [2, INT64_MAX/2]; uses integerSquareRootSignedInt64 to bound the trial-division loop."
guarantee isSignedInt64Prime "Total."

label startIsSignedInt64Prime
const zeroP I64 0
const oneP I64 1
const twoP I64 2
const truePr Bool true
const falsePr Bool false

call leOneCall math.lessThanOrEqualI64
arg leOneCall left inputValue
arg leOneCall right oneP
run leOneCall
bind leOne Bool leOneCall
branchIf leOne isPrimeFalse

call eqTwoCall math.equalI64
arg eqTwoCall left inputValue
arg eqTwoCall right twoP
run eqTwoCall
bind eqTwo Bool eqTwoCall
branchIf eqTwo isPrimeTrue

# Even (other than 2) -> composite.
call modTwoCall math.moduloI64
arg modTwoCall left inputValue
arg modTwoCall right twoP
run modTwoCall
bind nMod2 I64 modTwoCall
call isEvenCall math.equalI64
arg isEvenCall left nMod2
arg isEvenCall right zeroP
run isEvenCall
bind isSignedInt64Even Bool isEvenCall
branchIf isSignedInt64Even isPrimeFalse

# Trial divide by odd i from 3 up to floor(sqrt(n)).
call limitCall integerSquareRootSignedInt64
arg limitCall inputValue inputValue
run limitCall
bind limit CSignedInt64 limitCall

var i I64 3
label trialLoop
call beyondCall math.greaterThanI64
arg beyondCall left i
arg beyondCall right limit
run beyondCall
bind beyond Bool beyondCall
branchIf beyond isPrimeTrue
call primeRemainderCall math.moduloI64
arg primeRemainderCall left inputValue
arg primeRemainderCall right i
run primeRemainderCall
bind trialDivisionRemainder I64 primeRemainderCall
call divCheckCall math.equalI64
arg divCheckCall left trialDivisionRemainder
arg divCheckCall right zeroP
run divCheckCall
bind divides Bool divCheckCall
branchIf divides isPrimeFalse
call iIncCall math.addI64
arg iIncCall left i
arg iIncCall right twoP
run iIncCall
bind nextI I64 iIncCall
set i nextI
branch trialLoop

label isPrimeFalse
returnValue falsePr
label isPrimeTrue
returnValue truePr


operation isSignedInt64PowerOfTwo
input isSignedInt64PowerOfTwo inputValue CSignedInt64
output isSignedInt64PowerOfTwo Bool
memoryHeap isSignedInt64PowerOfTwo no
async isSignedInt64PowerOfTwo no
purpose isSignedInt64PowerOfTwo "Returns true when inputValue is a positive power of 2 (1, 2, 4, 8, ...)."
invariant isSignedInt64PowerOfTwo "Halves inputValue until 1 (power-of-two) or an odd intermediate (not). Zero / negative inputs return false."
guarantee isSignedInt64PowerOfTwo "Total."

label startIsSignedInt64PowerOfTwo
const zeroPt I64 0
const oneCount I64 1
const twoPt I64 2
const truePt Bool true
const falsePt Bool false

call leZeroPtCall math.lessThanOrEqualI64
arg leZeroPtCall left inputValue
arg leZeroPtCall right zeroPt
run leZeroPtCall
bind leZeroPt Bool leZeroPtCall
branchIf leZeroPt isPowerOfTwoFalse

var x I64 0
set x inputValue

label halveLoop
call eqOneCall math.equalI64
arg eqOneCall left x
arg eqOneCall right oneCount
run eqOneCall
bind eqOne Bool eqOneCall
branchIf eqOne isPowerOfTwoTrue
call ptMod2Call math.moduloI64
arg ptMod2Call left x
arg ptMod2Call right twoPt
run ptMod2Call
bind ptMod2 I64 ptMod2Call
call ptIsOddCall math.notEqualI64
arg ptIsOddCall left ptMod2
arg ptIsOddCall right zeroPt
run ptIsOddCall
bind ptIsOdd Bool ptIsOddCall
branchIf ptIsOdd isPowerOfTwoFalse
call halveXCall math.divideI64
arg halveXCall left x
arg halveXCall right twoPt
run halveXCall
bind xHalved I64 halveXCall
set x xHalved
branch halveLoop

label isPowerOfTwoFalse
returnValue falsePt
label isPowerOfTwoTrue
returnValue truePt


operation nextPowerOfTwoForSignedInt64
input nextPowerOfTwoForSignedInt64 inputValue CSignedInt64
output nextPowerOfTwoForSignedInt64 CSignedInt64
memoryHeap nextPowerOfTwoForSignedInt64 no
async nextPowerOfTwoForSignedInt64 no
purpose nextPowerOfTwoForSignedInt64 "Returns the smallest power of 2 >= inputValue (1 for inputValue <= 1)."
invariant nextPowerOfTwoForSignedInt64 "Doubles a 1-seeded accumulator until it reaches or exceeds inputValue; inputs <= 1 short-circuit to 1."
guarantee nextPowerOfTwoForSignedInt64 "Total."

label startNextPowerOfTwoForSignedInt64
const oneNp I64 1
const twoNp I64 2

call leOneNpCall math.lessThanOrEqualI64
arg leOneNpCall left inputValue
arg leOneNpCall right oneNp
run leOneNpCall
bind leOneNp Bool leOneNpCall
branchIf leOneNp nextPowOne

var p I64 1
label doubleLoop
call gePCall math.greaterThanOrEqualI64
arg gePCall left p
arg gePCall right inputValue
run gePCall
bind gep Bool gePCall
branchIf gep nextPowDone
call doubleCall math.multiplyI64
arg doubleCall left p
arg doubleCall right twoNp
run doubleCall
bind nextP I64 doubleCall
set p nextP
branch doubleLoop

label nextPowDone
returnValue p
label nextPowOne
returnValue oneNp


operation countDecimalDigitsInSignedInt64
input countDecimalDigitsInSignedInt64 inputValue CSignedInt64
output countDecimalDigitsInSignedInt64 CSignedInt64
memoryHeap countDecimalDigitsInSignedInt64 no
async countDecimalDigitsInSignedInt64 no
purpose countDecimalDigitsInSignedInt64 "Returns the count of decimal digits in |inputValue|. Returns 1 for inputValue == 0."
invariant countDecimalDigitsInSignedInt64 "Divides the absolute value by 10 until the quotient is zero, counting iterations. Negative inputs are absolute-valued via multiplication by -1 first."
guarantee countDecimalDigitsInSignedInt64 "Total."

label startCountDecimalDigitsInSignedInt64
const zeroCd I64 0
const oneCd I64 1
const tenCd I64 10
const negOneCd I64 -1

call eqZeroCdCall math.equalI64
arg eqZeroCdCall left inputValue
arg eqZeroCdCall right zeroCd
run eqZeroCdCall
bind eqZeroCd Bool eqZeroCdCall
branchIf eqZeroCd countDigitsOne

var v I64 0
set v inputValue
call negCdCall math.lessThanI64
arg negCdCall left v
arg negCdCall right zeroCd
run negCdCall
bind isNegCd Bool negCdCall
branchIf isNegCd flipCd
branch countDigitsLoop

label flipCd
call flipCdCall math.multiplyI64
arg flipCdCall left v
arg flipCdCall right negOneCd
run flipCdCall
bind vFlipped I64 flipCdCall
set v vFlipped
branch countDigitsLoop

label countDigitsLoop
var count I64 0
label cdStep
call doneCdCall math.equalI64
arg doneCdCall left v
arg doneCdCall right zeroCd
run doneCdCall
bind doneCd Bool doneCdCall
branchIf doneCd countDigitsReturn
call cdDivCall math.divideI64
arg cdDivCall left v
arg cdDivCall right tenCd
run cdDivCall
bind vNext I64 cdDivCall
set v vNext
call cdIncCall math.addI64
arg cdIncCall left count
arg cdIncCall right oneCd
run cdIncCall
bind nextCount I64 cdIncCall
set count nextCount
branch cdStep

label countDigitsReturn
returnValue count

label countDigitsOne
returnValue oneCd


operation isSignedInt64Even
input isSignedInt64Even inputValue CSignedInt64
output isSignedInt64Even Bool
memoryHeap isSignedInt64Even no
async isSignedInt64Even no
purpose isSignedInt64Even "Returns true when inputValue % 2 == 0."
guarantee isSignedInt64Even "Total."
label startIsSignedInt64Even
const zeroE I64 0
const twoE I64 2
const trueE Bool true
const falseE Bool false
call modECall math.moduloI64
arg modECall left inputValue
arg modECall right twoE
run modECall
bind modE I64 modECall
call eqZeroECall math.equalI64
arg eqZeroECall left modE
arg eqZeroECall right zeroE
run eqZeroECall
bind eqZeroE Bool eqZeroECall
branchIf eqZeroE isEvenTrue
returnValue falseE
label isEvenTrue
returnValue trueE


operation isSignedInt64Odd
input isSignedInt64Odd inputValue CSignedInt64
output isSignedInt64Odd Bool
memoryHeap isSignedInt64Odd no
async isSignedInt64Odd no
purpose isSignedInt64Odd "Returns true when inputValue % 2 != 0."
guarantee isSignedInt64Odd "Total."
label startIsSignedInt64Odd
const zeroO I64 0
const twoO I64 2
const trueO Bool true
const falseO Bool false
call modOCall math.moduloI64
arg modOCall left inputValue
arg modOCall right twoO
run modOCall
bind modO I64 modOCall
call neZeroOCall math.notEqualI64
arg neZeroOCall left modO
arg neZeroOCall right zeroO
run neZeroOCall
bind neZeroO Bool neZeroOCall
branchIf neZeroO isOddTrue
returnValue falseO
label isOddTrue
returnValue trueO


operation countSetBitsInSignedInt64
input countSetBitsInSignedInt64 inputValue CSignedInt64
output countSetBitsInSignedInt64 CSignedInt64
memoryHeap countSetBitsInSignedInt64 no
async countSetBitsInSignedInt64 no
purpose countSetBitsInSignedInt64 "Returns the population count of inputValue (number of 1-bits in its 64-bit representation)."
invariant countSetBitsInSignedInt64 "Inspects each of the 64 bits via modulo-2 on a halving working value; increments the counter for every odd remainder."
guarantee countSetBitsInSignedInt64 "Total — in [0, 64]."
label startCountSetBitsInSignedInt64
const zeroPc I64 0
const onePc I64 1
const twoPc I64 2
const limitPc I64 64
var pcVal I64 0
set pcVal inputValue
var pcCount I64 0
var pcIter I64 0
label pcLoop
call popcountDoneCall math.greaterThanOrEqualI64
arg popcountDoneCall left pcIter
arg popcountDoneCall right limitPc
run popcountDoneCall
bind popcountDoneCallB Bool popcountDoneCall
branchIf popcountDoneCallB pcReturn
call popcountModCall math.moduloI64
arg popcountModCall left pcVal
arg popcountModCall right twoPc
run popcountModCall
bind pcBit I64 popcountModCall
call popcountBitNonzeroCall math.notEqualI64
arg popcountBitNonzeroCall left pcBit
arg popcountBitNonzeroCall right zeroPc
run popcountBitNonzeroCall
bind pcSet Bool popcountBitNonzeroCall
branchIf pcSet popcountIncrementBranch
branch pcAdvance
label popcountIncrementBranch
call popcountIncrementCall math.addI64
arg popcountIncrementCall left pcCount
arg popcountIncrementCall right onePc
run popcountIncrementCall
bind pcNext I64 popcountIncrementCall
set pcCount pcNext
branch pcAdvance
label pcAdvance
call popcountDivideCall math.divideI64
arg popcountDivideCall left pcVal
arg popcountDivideCall right twoPc
run popcountDivideCall
bind pcHalved I64 popcountDivideCall
set pcVal pcHalved
call popcountIterIncrementCall math.addI64
arg popcountIterIncrementCall left pcIter
arg popcountIterIncrementCall right onePc
run popcountIterIncrementCall
bind pcIterNext I64 popcountIterIncrementCall
set pcIter pcIterNext
branch pcLoop
label pcReturn
returnValue pcCount


operation countTrailingZeroBitsInSignedInt64
input countTrailingZeroBitsInSignedInt64 inputValue CSignedInt64
output countTrailingZeroBitsInSignedInt64 CSignedInt64
memoryHeap countTrailingZeroBitsInSignedInt64 no
async countTrailingZeroBitsInSignedInt64 no
purpose countTrailingZeroBitsInSignedInt64 "Returns the count of trailing zero bits in inputValue's 64-bit representation. Returns 64 for inputValue == 0 (matching GCC __builtin_ctzll)."
invariant countTrailingZeroBitsInSignedInt64 "Halves the value while the low bit is zero, counting iterations. Zero input short-circuits to 64."
guarantee countTrailingZeroBitsInSignedInt64 "Total."
label startCountTrailingZeroBitsInSignedInt64
const zeroTz I64 0
const oneTz I64 1
const twoTz I64 2
const sixtyFourTz I64 64
# Special case n == 0
call ctzEqualZeroCall math.equalI64
arg ctzEqualZeroCall left inputValue
arg ctzEqualZeroCall right zeroTz
run ctzEqualZeroCall
bind nIsZero Bool ctzEqualZeroCall
branchIf nIsZero tzReturn64
var tzVal I64 0
set tzVal inputValue
var tzCount I64 0
label tzLoop
call tzModCall math.moduloI64
arg tzModCall left tzVal
arg tzModCall right twoTz
run tzModCall
bind tzMod I64 tzModCall
call ctzBitSetCall math.notEqualI64
arg ctzBitSetCall left tzMod
arg ctzBitSetCall right zeroTz
run ctzBitSetCall
bind tzSet Bool ctzBitSetCall
branchIf tzSet tzReturn
call tzDivCall math.divideI64
arg tzDivCall left tzVal
arg tzDivCall right twoTz
run tzDivCall
bind tzNext I64 tzDivCall
set tzVal tzNext
call tzIncCall math.addI64
arg tzIncCall left tzCount
arg tzIncCall right oneTz
run tzIncCall
bind tzCountNext I64 tzIncCall
set tzCount tzCountNext
branch tzLoop
label tzReturn
returnValue tzCount
label tzReturn64
returnValue sixtyFourTz


operation signOfSignedInt64
input signOfSignedInt64 inputValue CSignedInt64
output signOfSignedInt64 CSignedInt64
memoryHeap signOfSignedInt64 no
async signOfSignedInt64 no
purpose signOfSignedInt64 "Returns -1 when inputValue is negative, 1 when positive, 0 when zero."
guarantee signOfSignedInt64 "Total — result is always exactly -1, 0, or 1."
label startSignOfSignedInt64
const zeroSi I64 0
const oneSi I64 1
const negOneSi I64 -1
call absDiffLessThanCall math.lessThanI64
arg absDiffLessThanCall left inputValue
arg absDiffLessThanCall right zeroSi
run absDiffLessThanCall
bind isNg Bool absDiffLessThanCall
branchIf isNg siNeg
call absDiffGreaterThanCall math.greaterThanI64
arg absDiffGreaterThanCall left inputValue
arg absDiffGreaterThanCall right zeroSi
run absDiffGreaterThanCall
bind isPs Bool absDiffGreaterThanCall
branchIf isPs siPos
returnValue zeroSi
label siNeg
returnValue negOneSi
label siPos
returnValue oneSi


operation absoluteDifferenceBetweenSignedInt64Values
input absoluteDifferenceBetweenSignedInt64Values leftValue CSignedInt64
input absoluteDifferenceBetweenSignedInt64Values rightValue CSignedInt64
output absoluteDifferenceBetweenSignedInt64Values CSignedInt64
memoryHeap absoluteDifferenceBetweenSignedInt64Values no
async absoluteDifferenceBetweenSignedInt64Values no
purpose absoluteDifferenceBetweenSignedInt64Values "Returns |leftValue - rightValue|."
invariant absoluteDifferenceBetweenSignedInt64Values "Symmetric and non-negative."
guarantee absoluteDifferenceBetweenSignedInt64Values "Total (modulo two's-complement INT64_MIN wraparound)."
label startAbsoluteDifferenceBetweenSignedInt64Values
const zeroAdi I64 0
const negOneAdi I64 -1
call diffCall math.subtractI64
arg diffCall left leftValue
arg diffCall right rightValue
run diffCall
bind diff I64 diffCall
call absDiffLessThanZeroCall math.lessThanI64
arg absDiffLessThanZeroCall left diff
arg absDiffLessThanZeroCall right zeroAdi
run absDiffLessThanZeroCall
bind diffNeg Bool absDiffLessThanZeroCall
branchIf diffNeg flipDiff
returnValue diff
label flipDiff
call absDiffFlipSignCall math.multiplyI64
arg absDiffFlipSignCall left diff
arg absDiffFlipSignCall right negOneAdi
run absDiffFlipSignCall
bind absDiff CSignedInt64 absDiffFlipSignCall
returnValue absDiff


operation countLeadingZeroBitsInSignedInt64
input countLeadingZeroBitsInSignedInt64 inputValue CSignedInt64
output countLeadingZeroBitsInSignedInt64 CSignedInt64
memoryHeap countLeadingZeroBitsInSignedInt64 no
async countLeadingZeroBitsInSignedInt64 no
purpose countLeadingZeroBitsInSignedInt64 "Returns the count of leading zero bits in inputValue's 64-bit representation. Returns 64 for inputValue == 0; returns 0 for negative values (sign bit 63 is set)."
invariant countLeadingZeroBitsInSignedInt64 "Probe descends from 2^62 (the largest power of two representable as a positive CSignedInt64). For positive inputs we add 1 to account for the unrepresentable sign bit 63 above the probe range."
guarantee countLeadingZeroBitsInSignedInt64 "Total — in [0, 64]."
label startCountLeadingZeroBitsInSignedInt64
const zeroClz I64 0
const oneClz I64 1
const twoClz I64 2
const sixtyFourClz I64 64
# Negative inputs have bit 63 set, so zero leading zeros.
call clzIsNegativeCall math.lessThanI64
arg clzIsNegativeCall left inputValue
arg clzIsNegativeCall right zeroClz
run clzIsNegativeCall
bind clzIsNegativeResult Bool clzIsNegativeCall
branchIf clzIsNegativeResult clzReturnZero
call eqZeroClzCall math.equalI64
arg eqZeroClzCall left inputValue
arg eqZeroClzCall right zeroClz
run eqZeroClzCall
bind nIsZero Bool eqZeroClzCall
branchIf nIsZero clzReturn64
# Probe = high bit shift down until we find the topmost set bit.
# Start with highest power of two we can represent without overflow.
const probeStart I64 4611686018427387904
var probe I64 0
set probe probeStart
var clzCount I64 0
label clzLoop
call clzProbeLessEqualCall math.lessThanOrEqualI64
arg clzProbeLessEqualCall left probe
arg clzProbeLessEqualCall right inputValue
run clzProbeLessEqualCall
bind clzProbeLessEqualCallN Bool clzProbeLessEqualCall
branchIf clzProbeLessEqualCallN clzDone
call clzIncrementCall math.addI64
arg clzIncrementCall left clzCount
arg clzIncrementCall right oneClz
run clzIncrementCall
bind clzNext I64 clzIncrementCall
set clzCount clzNext
call clzProbeHalfCall math.divideI64
arg clzProbeHalfCall left probe
arg clzProbeHalfCall right twoClz
run clzProbeHalfCall
bind probeNext I64 clzProbeHalfCall
set probe probeNext
call clzProbeZeroCall math.equalI64
arg clzProbeZeroCall left probe
arg clzProbeZeroCall right zeroClz
run clzProbeZeroCall
bind probeIsZero Bool clzProbeZeroCall
branchIf probeIsZero clzReturn64
branch clzLoop
label clzDone
# Add 1 to count for the unrepresentable bit 63 above probeStart's bit 62.
call clzAdjustCall math.addI64
arg clzAdjustCall left clzCount
arg clzAdjustCall right oneClz
run clzAdjustCall
bind clzCountAdjusted I64 clzAdjustCall
returnValue clzCountAdjusted
label clzReturn64
returnValue sixtyFourClz
label clzReturnZero
returnValue zeroClz


operation squareSignedInt64
input squareSignedInt64 inputValue CSignedInt64
output squareSignedInt64 CSignedInt64
memoryHeap squareSignedInt64 no
async squareSignedInt64 no
purpose squareSignedInt64 "Returns inputValue * inputValue."
warning squareSignedInt64 "Wraps modulo 2^64 on overflow."
guarantee squareSignedInt64 "Total."
label startSquareSignedInt64
call sqCall math.multiplyI64
arg sqCall left inputValue
arg sqCall right inputValue
run sqCall
bind squareResult CSignedInt64 sqCall
returnValue squareResult


operation cubeSignedInt64
input cubeSignedInt64 inputValue CSignedInt64
output cubeSignedInt64 CSignedInt64
memoryHeap cubeSignedInt64 no
async cubeSignedInt64 no
purpose cubeSignedInt64 "Returns inputValue * inputValue * inputValue."
warning cubeSignedInt64 "Wraps modulo 2^64 on overflow."
guarantee cubeSignedInt64 "Total."
label startCubeSignedInt64
call cubeSquareStepCall math.multiplyI64
arg cubeSquareStepCall left inputValue
arg cubeSquareStepCall right inputValue
run cubeSquareStepCall
bind squareIntermediate CSignedInt64 cubeSquareStepCall
call cubeMultiplyStepCall math.multiplyI64
arg cubeMultiplyStepCall left squareIntermediate
arg cubeMultiplyStepCall right inputValue
run cubeMultiplyStepCall
bind cubeResult CSignedInt64 cubeMultiplyStepCall
returnValue cubeResult


operation isSignedInt64WithinInclusiveRange
input isSignedInt64WithinInclusiveRange inputValue CSignedInt64
input isSignedInt64WithinInclusiveRange lowerBound CSignedInt64
input isSignedInt64WithinInclusiveRange upperBound CSignedInt64
output isSignedInt64WithinInclusiveRange Bool
memoryHeap isSignedInt64WithinInclusiveRange no
async isSignedInt64WithinInclusiveRange no
purpose isSignedInt64WithinInclusiveRange "Returns true when lowerBound <= inputValue <= upperBound."
guarantee isSignedInt64WithinInclusiveRange "Total."
label startIsSignedInt64WithinInclusiveRange
const trueIR Bool true
const falseIR Bool false
call clampBelowLowerCall math.lessThanI64
arg clampBelowLowerCall left inputValue
arg clampBelowLowerCall right lowerBound
run clampBelowLowerCall
bind belowLowerBound Bool clampBelowLowerCall
branchIf belowLowerBound irFalse
call clampAboveUpperCall math.greaterThanI64
arg clampAboveUpperCall left inputValue
arg clampAboveUpperCall right upperBound
run clampAboveUpperCall
bind aboveUpperBound Bool clampAboveUpperCall
branchIf aboveUpperBound irFalse
returnValue trueIR
label irFalse
returnValue falseIR


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
purpose main "Smoke-test the integer math helpers."
invariant main "Every named check holds, or the failure path runs."

label startMain

# integerSquareRootSignedInt64(144) == 12
const oneHundredFortyFour CSignedInt64 144
const twelveExpected CSignedInt64 12
call assertSqrtCall integerSquareRootSignedInt64
arg assertSqrtCall inputValue oneHundredFortyFour
run assertSqrtCall
bind sqrtResult CSignedInt64 assertSqrtCall
call checkSqrtCall math.equalI64
arg checkSqrtCall left sqrtResult
arg checkSqrtCall right twelveExpected
run checkSqrtCall
bind sqrtOk Bool checkSqrtCall
branchIf sqrtOk sqrtHolds
branch smokeAssertionFailed
label sqrtHolds

# factorialSignedInt64(5) == 120
const fiveInputForFactorial CSignedInt64 5
const oneHundredTwentyExpected CSignedInt64 120
call assertFactorialCall factorialSignedInt64
arg assertFactorialCall inputValue fiveInputForFactorial
run assertFactorialCall
bind factorialResult CSignedInt64 assertFactorialCall
call checkFactorialCall math.equalI64
arg checkFactorialCall left factorialResult
arg checkFactorialCall right oneHundredTwentyExpected
run checkFactorialCall
bind factorialOk Bool checkFactorialCall
branchIf factorialOk factorialHolds
branch smokeAssertionFailed
label factorialHolds

# isSignedInt64Prime(17) == true
const seventeen CSignedInt64 17
call assertPrime17Call isSignedInt64Prime
arg assertPrime17Call inputValue seventeen
run assertPrime17Call
bind prime17Result Bool assertPrime17Call
branchIf prime17Result prime17Holds
branch smokeAssertionFailed
label prime17Holds

# isSignedInt64Prime(15) == false
const fifteen CSignedInt64 15
call assertPrime15Call isSignedInt64Prime
arg assertPrime15Call inputValue fifteen
run assertPrime15Call
bind prime15Result Bool assertPrime15Call
branchIf prime15Result smokeAssertionFailed

# isSignedInt64PowerOfTwo(64) == true
const sixtyFour CSignedInt64 64
call assertPow64Call isSignedInt64PowerOfTwo
arg assertPow64Call inputValue sixtyFour
run assertPow64Call
bind pow64Result Bool assertPow64Call
branchIf pow64Result pow64Holds
branch smokeAssertionFailed
label pow64Holds

# isSignedInt64PowerOfTwo(48) == false
const fortyEight CSignedInt64 48
call assertPow48Call isSignedInt64PowerOfTwo
arg assertPow48Call inputValue fortyEight
run assertPow48Call
bind pow48Result Bool assertPow48Call
branchIf pow48Result smokeAssertionFailed

# nextPowerOfTwoForSignedInt64(100) == 128
const oneHundred CSignedInt64 100
const oneHundredTwentyEight CSignedInt64 128
call assertNextPow2Call nextPowerOfTwoForSignedInt64
arg assertNextPow2Call inputValue oneHundred
run assertNextPow2Call
bind nextPow2Result CSignedInt64 assertNextPow2Call
call checkNextPow2Call math.equalI64
arg checkNextPow2Call left nextPow2Result
arg checkNextPow2Call right oneHundredTwentyEight
run checkNextPow2Call
bind nextPow2Ok Bool checkNextPow2Call
branchIf nextPow2Ok nextPow2Holds
branch smokeAssertionFailed
label nextPow2Holds

# countDecimalDigitsInSignedInt64(12345) == 5
const twelveThousandThreeHundredFortyFive CSignedInt64 12345
const fiveDigitsExpected CSignedInt64 5
call assertDigitCountCall countDecimalDigitsInSignedInt64
arg assertDigitCountCall inputValue twelveThousandThreeHundredFortyFive
run assertDigitCountCall
bind digitCountResult CSignedInt64 assertDigitCountCall
call checkDigitCountCall math.equalI64
arg checkDigitCountCall left digitCountResult
arg checkDigitCountCall right fiveDigitsExpected
run checkDigitCountCall
bind digitCountOk Bool checkDigitCountCall
branchIf digitCountOk digitCountHolds
branch smokeAssertionFailed
label digitCountHolds

# isSignedInt64Even(10) == true
const tenInteger CSignedInt64 10
call assertEvenCall isSignedInt64Even
arg assertEvenCall inputValue tenInteger
run assertEvenCall
bind evenResult Bool assertEvenCall
branchIf evenResult evenHolds
branch smokeAssertionFailed
label evenHolds

# isSignedInt64Odd(10) == false
call assertOddCall isSignedInt64Odd
arg assertOddCall inputValue tenInteger
run assertOddCall
bind oddResult Bool assertOddCall
branchIf oddResult smokeAssertionFailed

# countSetBitsInSignedInt64(13) == 3  (0b1101)
const thirteen CSignedInt64 13
const threeBits CSignedInt64 3
call assertPopcountCall countSetBitsInSignedInt64
arg assertPopcountCall inputValue thirteen
run assertPopcountCall
bind popcountResult CSignedInt64 assertPopcountCall
call checkPopcountCall math.equalI64
arg checkPopcountCall left popcountResult
arg checkPopcountCall right threeBits
run checkPopcountCall
bind popcountOk Bool checkPopcountCall
branchIf popcountOk popcountHolds
branch smokeAssertionFailed
label popcountHolds

# countTrailingZeroBitsInSignedInt64(16) == 4
const sixteenInteger CSignedInt64 16
const fourTrailingZeros CSignedInt64 4
call assertCtzCall countTrailingZeroBitsInSignedInt64
arg assertCtzCall inputValue sixteenInteger
run assertCtzCall
bind ctzResult CSignedInt64 assertCtzCall
call checkCtzCall math.equalI64
arg checkCtzCall left ctzResult
arg checkCtzCall right fourTrailingZeros
run checkCtzCall
bind ctzOk Bool checkCtzCall
branchIf ctzOk ctzHolds
branch smokeAssertionFailed
label ctzHolds

# signOfSignedInt64(-5) == -1
const negativeFive CSignedInt64 -5
const negativeOne CSignedInt64 -1
call assertSignCall signOfSignedInt64
arg assertSignCall inputValue negativeFive
run assertSignCall
bind signResult CSignedInt64 assertSignCall
call checkSignCall math.equalI64
arg checkSignCall left signResult
arg checkSignCall right negativeOne
run checkSignCall
bind signOk Bool checkSignCall
branchIf signOk signHolds
branch smokeAssertionFailed
label signHolds

# absoluteDifferenceBetweenSignedInt64Values(10, 3) == 7
const threeForAbsDiff CSignedInt64 3
const sevenExpected CSignedInt64 7
call assertAbsDiffCall absoluteDifferenceBetweenSignedInt64Values
arg assertAbsDiffCall leftValue tenInteger
arg assertAbsDiffCall rightValue threeForAbsDiff
run assertAbsDiffCall
bind absDiffResult CSignedInt64 assertAbsDiffCall
call checkAbsDiffCall math.equalI64
arg checkAbsDiffCall left absDiffResult
arg checkAbsDiffCall right sevenExpected
run checkAbsDiffCall
bind absDiffOk Bool checkAbsDiffCall
branchIf absDiffOk absDiffHolds
branch smokeAssertionFailed
label absDiffHolds

# ============================================================
# Per-operation extended unit tests: covers ops the original smoke
# test omitted (countLeadingZeroBitsInSignedInt64, squareSignedInt64,
# cubeSignedInt64, isSignedInt64WithinInclusiveRange) plus boundary
# cases (zero, one, two) and property invariants (commutativity,
# round-trip) for ops already covered.
# ============================================================

const zeroSm CSignedInt64 0
const oneSm CSignedInt64 1
const twoSm CSignedInt64 2
const sixSm CSignedInt64 6
const negTenSm CSignedInt64 -10
const negTwoSm CSignedInt64 -2
const sixtyTwoSm CSignedInt64 62
const sixtyThreeSm CSignedInt64 63
const minusOneSm CSignedInt64 -1
const oneHundredFortyFourEx CSignedInt64 144

# integerSquareRoot boundary: sqrt(0) == 0
call sqrtZeroCall integerSquareRootSignedInt64
arg sqrtZeroCall inputValue zeroSm
run sqrtZeroCall
bind sqrtZeroResult CSignedInt64 sqrtZeroCall
call checkSqrtZeroCall math.equalI64
arg checkSqrtZeroCall left sqrtZeroResult
arg checkSqrtZeroCall right zeroSm
run checkSqrtZeroCall
bind sqrtZeroOk Bool checkSqrtZeroCall
branchIf sqrtZeroOk sqrtZeroHolds
branch smokeAssertionFailed
label sqrtZeroHolds

# integerSquareRoot boundary: sqrt(1) == 1
call sqrtOneCall integerSquareRootSignedInt64
arg sqrtOneCall inputValue oneSm
run sqrtOneCall
bind sqrtOneResult CSignedInt64 sqrtOneCall
call checkSqrtOneCall math.equalI64
arg checkSqrtOneCall left sqrtOneResult
arg checkSqrtOneCall right oneSm
run checkSqrtOneCall
bind sqrtOneOk Bool checkSqrtOneCall
branchIf sqrtOneOk sqrtOneHolds
branch smokeAssertionFailed
label sqrtOneHolds

# integerSquareRoot negative: sqrt(-10) == 0 (clamps to zero)
call sqrtNegCall integerSquareRootSignedInt64
arg sqrtNegCall inputValue negTenSm
run sqrtNegCall
bind sqrtNegResult CSignedInt64 sqrtNegCall
call checkSqrtNegCall math.equalI64
arg checkSqrtNegCall left sqrtNegResult
arg checkSqrtNegCall right zeroSm
run checkSqrtNegCall
bind sqrtNegOk Bool checkSqrtNegCall
branchIf sqrtNegOk sqrtNegHolds
branch smokeAssertionFailed
label sqrtNegHolds

# factorial(0) == 1 (convention)
call facZeroCall factorialSignedInt64
arg facZeroCall inputValue zeroSm
run facZeroCall
bind facZeroResult CSignedInt64 facZeroCall
call checkFacZeroCall math.equalI64
arg checkFacZeroCall left facZeroResult
arg checkFacZeroCall right oneSm
run checkFacZeroCall
bind facZeroOk Bool checkFacZeroCall
branchIf facZeroOk facZeroHolds
branch smokeAssertionFailed
label facZeroHolds

# factorial(1) == 1
call facOneCall factorialSignedInt64
arg facOneCall inputValue oneSm
run facOneCall
bind facOneResult CSignedInt64 facOneCall
call checkFacOneCall math.equalI64
arg checkFacOneCall left facOneResult
arg checkFacOneCall right oneSm
run checkFacOneCall
bind facOneOk Bool checkFacOneCall
branchIf facOneOk facOneHolds
branch smokeAssertionFailed
label facOneHolds

# factorial(3) == 6
call facThreeCall factorialSignedInt64
arg facThreeCall inputValue threeForAbsDiff
run facThreeCall
bind facThreeResult CSignedInt64 facThreeCall
call checkFacThreeCall math.equalI64
arg checkFacThreeCall left facThreeResult
arg checkFacThreeCall right sixSm
run checkFacThreeCall
bind facThreeOk Bool checkFacThreeCall
branchIf facThreeOk facThreeHolds
branch smokeAssertionFailed
label facThreeHolds

# isPrime(2) == true (smallest prime)
call primeTwoCall isSignedInt64Prime
arg primeTwoCall inputValue twoSm
run primeTwoCall
bind primeTwoResult Bool primeTwoCall
branchIf primeTwoResult primeTwoHolds
branch smokeAssertionFailed
label primeTwoHolds

# isPrime(1) == false
call primeOneCall isSignedInt64Prime
arg primeOneCall inputValue oneSm
run primeOneCall
bind primeOneResult Bool primeOneCall
branchIf primeOneResult smokeAssertionFailed

# isPrime(0) == false
call primeZeroCall isSignedInt64Prime
arg primeZeroCall inputValue zeroSm
run primeZeroCall
bind primeZeroResult Bool primeZeroCall
branchIf primeZeroResult smokeAssertionFailed

# isPowerOfTwo(1) == true (2^0)
call powOneCall isSignedInt64PowerOfTwo
arg powOneCall inputValue oneSm
run powOneCall
bind powOneResult Bool powOneCall
branchIf powOneResult powOneHolds
branch smokeAssertionFailed
label powOneHolds

# isPowerOfTwo(0) == false
call powZeroCall isSignedInt64PowerOfTwo
arg powZeroCall inputValue zeroSm
run powZeroCall
bind powZeroResult Bool powZeroCall
branchIf powZeroResult smokeAssertionFailed

# isPowerOfTwo(-4) == false (negatives are never powers of two)
call powNegCall isSignedInt64PowerOfTwo
arg powNegCall inputValue negTenSm
run powNegCall
bind powNegResult Bool powNegCall
branchIf powNegResult smokeAssertionFailed

# nextPowerOfTwo(1) == 1 (already power of 2)
call nextPow1Call nextPowerOfTwoForSignedInt64
arg nextPow1Call inputValue oneSm
run nextPow1Call
bind nextPow1Result CSignedInt64 nextPow1Call
call checkNextPow1Call math.equalI64
arg checkNextPow1Call left nextPow1Result
arg checkNextPow1Call right oneSm
run checkNextPow1Call
bind nextPow1Ok Bool checkNextPow1Call
branchIf nextPow1Ok nextPow1Holds
branch smokeAssertionFailed
label nextPow1Holds

# nextPowerOfTwo(0) == 1
call nextPow0Call nextPowerOfTwoForSignedInt64
arg nextPow0Call inputValue zeroSm
run nextPow0Call
bind nextPow0Result CSignedInt64 nextPow0Call
call checkNextPow0Call math.equalI64
arg checkNextPow0Call left nextPow0Result
arg checkNextPow0Call right oneSm
run checkNextPow0Call
bind nextPow0Ok Bool checkNextPow0Call
branchIf nextPow0Ok nextPow0Holds
branch smokeAssertionFailed
label nextPow0Holds

# countDecimalDigits(0) == 1
call digitsZeroCall countDecimalDigitsInSignedInt64
arg digitsZeroCall inputValue zeroSm
run digitsZeroCall
bind digitsZeroResult CSignedInt64 digitsZeroCall
call checkDigitsZeroCall math.equalI64
arg checkDigitsZeroCall left digitsZeroResult
arg checkDigitsZeroCall right oneSm
run checkDigitsZeroCall
bind digitsZeroOk Bool checkDigitsZeroCall
branchIf digitsZeroOk digitsZeroHolds
branch smokeAssertionFailed
label digitsZeroHolds

# countDecimalDigits(-99) == 2 (negatives count by absolute value)
const negNinetyNineSm CSignedInt64 -99
call digitsNegCall countDecimalDigitsInSignedInt64
arg digitsNegCall inputValue negNinetyNineSm
run digitsNegCall
bind digitsNegResult CSignedInt64 digitsNegCall
call checkDigitsNegCall math.equalI64
arg checkDigitsNegCall left digitsNegResult
arg checkDigitsNegCall right twoSm
run checkDigitsNegCall
bind digitsNegOk Bool checkDigitsNegCall
branchIf digitsNegOk digitsNegHolds
branch smokeAssertionFailed
label digitsNegHolds

# isEven(0) == true
call evenZeroCall isSignedInt64Even
arg evenZeroCall inputValue zeroSm
run evenZeroCall
bind evenZeroResult Bool evenZeroCall
branchIf evenZeroResult evenZeroHolds
branch smokeAssertionFailed
label evenZeroHolds

# isOdd(7) == true
call oddSevenCall isSignedInt64Odd
arg oddSevenCall inputValue sevenExpected
run oddSevenCall
bind oddSevenResult Bool oddSevenCall
branchIf oddSevenResult oddSevenHolds
branch smokeAssertionFailed
label oddSevenHolds

# countSetBits(0) == 0
call popcountZeroCall countSetBitsInSignedInt64
arg popcountZeroCall inputValue zeroSm
run popcountZeroCall
bind popcountZeroResult CSignedInt64 popcountZeroCall
call checkPopcountZeroCall math.equalI64
arg checkPopcountZeroCall left popcountZeroResult
arg checkPopcountZeroCall right zeroSm
run checkPopcountZeroCall
bind popcountZeroOk Bool checkPopcountZeroCall
branchIf popcountZeroOk popcountZeroHolds
branch smokeAssertionFailed
label popcountZeroHolds

# countSetBits(1) == 1
call popcountOneCall countSetBitsInSignedInt64
arg popcountOneCall inputValue oneSm
run popcountOneCall
bind popcountOneResult CSignedInt64 popcountOneCall
call checkPopcountOneCall math.equalI64
arg checkPopcountOneCall left popcountOneResult
arg checkPopcountOneCall right oneSm
run checkPopcountOneCall
bind popcountOneOk Bool checkPopcountOneCall
branchIf popcountOneOk popcountOneHolds
branch smokeAssertionFailed
label popcountOneHolds

# countTrailingZeros(0) == 64 (matches __builtin_ctzll)
const sixtyFourSm CSignedInt64 64
call ctzZeroCall countTrailingZeroBitsInSignedInt64
arg ctzZeroCall inputValue zeroSm
run ctzZeroCall
bind ctzZeroResult CSignedInt64 ctzZeroCall
call checkCtzZeroCall math.equalI64
arg checkCtzZeroCall left ctzZeroResult
arg checkCtzZeroCall right sixtyFourSm
run checkCtzZeroCall
bind ctzZeroOk Bool checkCtzZeroCall
branchIf ctzZeroOk ctzZeroHolds
branch smokeAssertionFailed
label ctzZeroHolds

# countTrailingZeros(1) == 0
call ctzOneCall countTrailingZeroBitsInSignedInt64
arg ctzOneCall inputValue oneSm
run ctzOneCall
bind ctzOneResult CSignedInt64 ctzOneCall
call checkCtzOneCall math.equalI64
arg checkCtzOneCall left ctzOneResult
arg checkCtzOneCall right zeroSm
run checkCtzOneCall
bind ctzOneOk Bool checkCtzOneCall
branchIf ctzOneOk ctzOneHolds
branch smokeAssertionFailed
label ctzOneHolds

# sign(0) == 0
call signZeroCall signOfSignedInt64
arg signZeroCall inputValue zeroSm
run signZeroCall
bind signZeroResult CSignedInt64 signZeroCall
call checkSignZeroCall math.equalI64
arg checkSignZeroCall left signZeroResult
arg checkSignZeroCall right zeroSm
run checkSignZeroCall
bind signZeroOk Bool checkSignZeroCall
branchIf signZeroOk signZeroHolds
branch smokeAssertionFailed
label signZeroHolds

# sign(42) == 1
const fortyTwoSm CSignedInt64 42
call signPosCall signOfSignedInt64
arg signPosCall inputValue fortyTwoSm
run signPosCall
bind signPosResult CSignedInt64 signPosCall
call checkSignPosCall math.equalI64
arg checkSignPosCall left signPosResult
arg checkSignPosCall right oneSm
run checkSignPosCall
bind signPosOk Bool checkSignPosCall
branchIf signPosOk signPosHolds
branch smokeAssertionFailed
label signPosHolds

# absDiff symmetry: absDiff(3, 10) == absDiff(10, 3)
call absDiffSymCall absoluteDifferenceBetweenSignedInt64Values
arg absDiffSymCall leftValue threeForAbsDiff
arg absDiffSymCall rightValue tenInteger
run absDiffSymCall
bind absDiffSymResult CSignedInt64 absDiffSymCall
call checkAbsDiffSymCall math.equalI64
arg checkAbsDiffSymCall left absDiffSymResult
arg checkAbsDiffSymCall right sevenExpected
run checkAbsDiffSymCall
bind absDiffSymOk Bool checkAbsDiffSymCall
branchIf absDiffSymOk absDiffSymHolds
branch smokeAssertionFailed
label absDiffSymHolds

# === countLeadingZeroBitsInSignedInt64 (was untested) ===
# clz(0) == 64
call clzZeroCall countLeadingZeroBitsInSignedInt64
arg clzZeroCall inputValue zeroSm
run clzZeroCall
bind clzZeroResult CSignedInt64 clzZeroCall
call checkClzZeroCall math.equalI64
arg checkClzZeroCall left clzZeroResult
arg checkClzZeroCall right sixtyFourSm
run checkClzZeroCall
bind clzZeroOk Bool checkClzZeroCall
branchIf clzZeroOk clzZeroHolds
branch smokeAssertionFailed
label clzZeroHolds

# clz(1) == 63 (one bit set in position 0; 63 zeros above it)
call clzOneCall countLeadingZeroBitsInSignedInt64
arg clzOneCall inputValue oneSm
run clzOneCall
bind clzOneResult CSignedInt64 clzOneCall
call checkClzOneCall math.equalI64
arg checkClzOneCall left clzOneResult
arg checkClzOneCall right sixtyThreeSm
run checkClzOneCall
bind clzOneOk Bool checkClzOneCall
branchIf clzOneOk clzOneHolds
branch smokeAssertionFailed
label clzOneHolds

# clz(2) == 62
call clzTwoCall countLeadingZeroBitsInSignedInt64
arg clzTwoCall inputValue twoSm
run clzTwoCall
bind clzTwoResult CSignedInt64 clzTwoCall
call checkClzTwoCall math.equalI64
arg checkClzTwoCall left clzTwoResult
arg checkClzTwoCall right sixtyTwoSm
run checkClzTwoCall
bind clzTwoOk Bool checkClzTwoCall
branchIf clzTwoOk clzTwoHolds
branch smokeAssertionFailed
label clzTwoHolds

# === squareSignedInt64 (was untested) ===
# square(0) == 0
call sqZeroCall squareSignedInt64
arg sqZeroCall inputValue zeroSm
run sqZeroCall
bind sqZeroResult CSignedInt64 sqZeroCall
call checkSqZeroCall math.equalI64
arg checkSqZeroCall left sqZeroResult
arg checkSqZeroCall right zeroSm
run checkSqZeroCall
bind sqZeroOk Bool checkSqZeroCall
branchIf sqZeroOk sqZeroHolds
branch smokeAssertionFailed
label sqZeroHolds

# square(12) == 144 (round-trip with sqrt above)
call sqTwelveCall squareSignedInt64
arg sqTwelveCall inputValue twelveExpected
run sqTwelveCall
bind sqTwelveResult CSignedInt64 sqTwelveCall
call checkSqTwelveCall math.equalI64
arg checkSqTwelveCall left sqTwelveResult
arg checkSqTwelveCall right oneHundredFortyFourEx
run checkSqTwelveCall
bind sqTwelveOk Bool checkSqTwelveCall
branchIf sqTwelveOk sqTwelveHolds
branch smokeAssertionFailed
label sqTwelveHolds

# square(-5) == 25 (sign-insensitive)
const twentyFiveSm CSignedInt64 25
call sqNegCall squareSignedInt64
arg sqNegCall inputValue negativeFive
run sqNegCall
bind sqNegResult CSignedInt64 sqNegCall
call checkSqNegCall math.equalI64
arg checkSqNegCall left sqNegResult
arg checkSqNegCall right twentyFiveSm
run checkSqNegCall
bind sqNegOk Bool checkSqNegCall
branchIf sqNegOk sqNegHolds
branch smokeAssertionFailed
label sqNegHolds

# === cubeSignedInt64 (was untested) ===
# cube(0) == 0
call cubeZeroCall cubeSignedInt64
arg cubeZeroCall inputValue zeroSm
run cubeZeroCall
bind cubeZeroResult CSignedInt64 cubeZeroCall
call checkCubeZeroCall math.equalI64
arg checkCubeZeroCall left cubeZeroResult
arg checkCubeZeroCall right zeroSm
run checkCubeZeroCall
bind cubeZeroOk Bool checkCubeZeroCall
branchIf cubeZeroOk cubeZeroHolds
branch smokeAssertionFailed
label cubeZeroHolds

# cube(3) == 27
const twentySevenSm CSignedInt64 27
call cubeThreeCall cubeSignedInt64
arg cubeThreeCall inputValue threeForAbsDiff
run cubeThreeCall
bind cubeThreeResult CSignedInt64 cubeThreeCall
call checkCubeThreeCall math.equalI64
arg checkCubeThreeCall left cubeThreeResult
arg checkCubeThreeCall right twentySevenSm
run checkCubeThreeCall
bind cubeThreeOk Bool checkCubeThreeCall
branchIf cubeThreeOk cubeThreeHolds
branch smokeAssertionFailed
label cubeThreeHolds

# cube(-2) == -8 (sign-preserving)
const negEightSm CSignedInt64 -8
call cubeNegCall cubeSignedInt64
arg cubeNegCall inputValue negTwoSm
run cubeNegCall
bind cubeNegResult CSignedInt64 cubeNegCall
call checkCubeNegCall math.equalI64
arg checkCubeNegCall left cubeNegResult
arg checkCubeNegCall right negEightSm
run checkCubeNegCall
bind cubeNegOk Bool checkCubeNegCall
branchIf cubeNegOk cubeNegHolds
branch smokeAssertionFailed
label cubeNegHolds

# === isSignedInt64WithinInclusiveRange (was untested) ===
# 5 in [0, 10] == true
call rangeInsideCall isSignedInt64WithinInclusiveRange
arg rangeInsideCall inputValue fiveInputForFactorial
arg rangeInsideCall lowerBound zeroSm
arg rangeInsideCall upperBound tenInteger
run rangeInsideCall
bind rangeInsideResult Bool rangeInsideCall
branchIf rangeInsideResult rangeInsideHolds
branch smokeAssertionFailed
label rangeInsideHolds

# 0 in [0, 10] == true (lower boundary inclusive)
call rangeLowerCall isSignedInt64WithinInclusiveRange
arg rangeLowerCall inputValue zeroSm
arg rangeLowerCall lowerBound zeroSm
arg rangeLowerCall upperBound tenInteger
run rangeLowerCall
bind rangeLowerResult Bool rangeLowerCall
branchIf rangeLowerResult rangeLowerHolds
branch smokeAssertionFailed
label rangeLowerHolds

# 10 in [0, 10] == true (upper boundary inclusive)
call rangeUpperCall isSignedInt64WithinInclusiveRange
arg rangeUpperCall inputValue tenInteger
arg rangeUpperCall lowerBound zeroSm
arg rangeUpperCall upperBound tenInteger
run rangeUpperCall
bind rangeUpperResult Bool rangeUpperCall
branchIf rangeUpperResult rangeUpperHolds
branch smokeAssertionFailed
label rangeUpperHolds

# -1 in [0, 10] == false (below lower)
call rangeBelowCall isSignedInt64WithinInclusiveRange
arg rangeBelowCall inputValue minusOneSm
arg rangeBelowCall lowerBound zeroSm
arg rangeBelowCall upperBound tenInteger
run rangeBelowCall
bind rangeBelowResult Bool rangeBelowCall
branchIf rangeBelowResult smokeAssertionFailed

# 11 in [0, 10] == false (above upper)
const elevenSm CSignedInt64 11
call rangeAboveCall isSignedInt64WithinInclusiveRange
arg rangeAboveCall inputValue elevenSm
arg rangeAboveCall lowerBound zeroSm
arg rangeAboveCall upperBound tenInteger
run rangeAboveCall
bind rangeAboveResult Bool rangeAboveCall
branchIf rangeAboveResult smokeAssertionFailed

# Property: sqrt(square(x)) == x for x >= 0
call squareForRoundTripCall squareSignedInt64
arg squareForRoundTripCall inputValue twelveExpected
run squareForRoundTripCall
bind squareForRoundTripResult CSignedInt64 squareForRoundTripCall
call sqrtAfterSquareCall integerSquareRootSignedInt64
arg sqrtAfterSquareCall inputValue squareForRoundTripResult
run sqrtAfterSquareCall
bind sqrtAfterSquareResult CSignedInt64 sqrtAfterSquareCall
call checkRoundTripSquareSqrtCall math.equalI64
arg checkRoundTripSquareSqrtCall left sqrtAfterSquareResult
arg checkRoundTripSquareSqrtCall right twelveExpected
run checkRoundTripSquareSqrtCall
bind roundTripSquareSqrtOk Bool checkRoundTripSquareSqrtCall
branchIf roundTripSquareSqrtOk roundTripSquareSqrtHolds
branch smokeAssertionFailed
label roundTripSquareSqrtHolds

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
makeError mathSmokeFailure MainError.MathSmokeAssertionFailed
returnError mathSmokeFailure
