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
const oneI64 I64 1
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
const threeP I64 3
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
call rCall math.moduloI64
arg rCall left inputValue
arg rCall right i
run rCall
bind r I64 rCall
call divCallCheck math.equalI64
arg divCallCheck left r
arg divCallCheck right zeroP
run divCallCheck
bind divides Bool divCallCheck
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
guarantee nextPowerOfTwoForSignedInt64 "Total."

label startNextPowerOfTwoForSignedInt64
const zeroNp I64 0
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
call pcDone math.greaterThanOrEqualI64
arg pcDone left pcIter
arg pcDone right limitPc
run pcDone
bind pcDoneB Bool pcDone
branchIf pcDoneB pcReturn
call pcMod math.moduloI64
arg pcMod left pcVal
arg pcMod right twoPc
run pcMod
bind pcBit I64 pcMod
call pcBitNz math.notEqualI64
arg pcBitNz left pcBit
arg pcBitNz right zeroPc
run pcBitNz
bind pcSet Bool pcBitNz
branchIf pcSet pcIncrement
branch pcAdvance
label pcIncrement
call pcInc math.addI64
arg pcInc left pcCount
arg pcInc right onePc
run pcInc
bind pcNext I64 pcInc
set pcCount pcNext
branch pcAdvance
label pcAdvance
call pcDiv math.divideI64
arg pcDiv left pcVal
arg pcDiv right twoPc
run pcDiv
bind pcHalved I64 pcDiv
set pcVal pcHalved
call pcIterInc math.addI64
arg pcIterInc left pcIter
arg pcIterInc right onePc
run pcIterInc
bind pcIterNext I64 pcIterInc
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
guarantee countTrailingZeroBitsInSignedInt64 "Total."
label startCountTrailingZeroBitsInSignedInt64
const zeroTz I64 0
const oneTz I64 1
const twoTz I64 2
const sixtyFourTz I64 64
# Special case n == 0
call eqZeroTz math.equalI64
arg eqZeroTz left inputValue
arg eqZeroTz right zeroTz
run eqZeroTz
bind nIsZero Bool eqZeroTz
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
call tzBitSet math.notEqualI64
arg tzBitSet left tzMod
arg tzBitSet right zeroTz
run tzBitSet
bind tzSet Bool tzBitSet
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
call ltCheck math.lessThanI64
arg ltCheck left inputValue
arg ltCheck right zeroSi
run ltCheck
bind isNg Bool ltCheck
branchIf isNg siNeg
call gtCheck math.greaterThanI64
arg gtCheck left inputValue
arg gtCheck right zeroSi
run gtCheck
bind isPs Bool gtCheck
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
call lt0 math.lessThanI64
arg lt0 left diff
arg lt0 right zeroAdi
run lt0
bind diffNeg Bool lt0
branchIf diffNeg flipDiff
returnValue diff
label flipDiff
call flip math.multiplyI64
arg flip left diff
arg flip right negOneAdi
run flip
bind absDiff CSignedInt64 flip
returnValue absDiff


operation countLeadingZeroBitsInSignedInt64
input countLeadingZeroBitsInSignedInt64 inputValue CSignedInt64
output countLeadingZeroBitsInSignedInt64 CSignedInt64
memoryHeap countLeadingZeroBitsInSignedInt64 no
async countLeadingZeroBitsInSignedInt64 no
purpose countLeadingZeroBitsInSignedInt64 "Returns the count of leading zero bits in inputValue's 64-bit representation. Returns 64 for inputValue == 0."
guarantee countLeadingZeroBitsInSignedInt64 "Total — in [0, 64]."
label startCountLeadingZeroBitsInSignedInt64
const zeroClz I64 0
const oneClz I64 1
const twoClz I64 2
const sixtyFourClz I64 64
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
call probeLe math.lessThanOrEqualI64
arg probeLe left probe
arg probeLe right inputValue
run probeLe
bind probeLeN Bool probeLe
branchIf probeLeN clzDone
call clzInc math.addI64
arg clzInc left clzCount
arg clzInc right oneClz
run clzInc
bind clzNext I64 clzInc
set clzCount clzNext
call probeHalf math.divideI64
arg probeHalf left probe
arg probeHalf right twoClz
run probeHalf
bind probeNext I64 probeHalf
set probe probeNext
call probeZero math.equalI64
arg probeZero left probe
arg probeZero right zeroClz
run probeZero
bind probeIsZero Bool probeZero
branchIf probeIsZero clzReturn64
branch clzLoop
label clzDone
returnValue clzCount
label clzReturn64
returnValue sixtyFourClz


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
call sq1 math.multiplyI64
arg sq1 left inputValue
arg sq1 right inputValue
run sq1
bind sq CSignedInt64 sq1
call cb math.multiplyI64
arg cb left sq
arg cb right inputValue
run cb
bind cubeResult CSignedInt64 cb
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
call belowLo math.lessThanI64
arg belowLo left inputValue
arg belowLo right lowerBound
run belowLo
bind below Bool belowLo
branchIf below irFalse
call aboveHi math.greaterThanI64
arg aboveHi left inputValue
arg aboveHi right upperBound
run aboveHi
bind above Bool aboveHi
branchIf above irFalse
returnValue trueIR
label irFalse
returnValue falseIR


# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
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

const successMessageText CNullTerminatedByteString "OK"
call writeSuccessLineCall console.writeLine
arg writeSuccessLineCall console console
arg writeSuccessLineCall text successMessageText
run writeSuccessLineCall
ignoreOk writeSuccessLineCall Void
const exitOkCode ExitCode 0
returnOk exitOkCode

label smokeAssertionFailed
makeError mathSmokeFailure MainError.MathSmokeAssertionFailed
returnError mathSmokeFailure
