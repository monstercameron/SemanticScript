project StdMathSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: integer math.
#
# Pure AS — every operation lowers to math.* primitives + branching,
# no libc math.h dependency.
#
# Operations:
#   intSqrt(n)         - floor(sqrt(n)) via Newton's method on integers.
#   factorial(n)       - n! by repeated multiplication (n <= 20 fits i64).
#   isPrime(n)         - 1 if prime, 0 otherwise; trial division up to sqrt(n).
#   isPowerOfTwo(n)    - 1 if n is a positive power of 2, else 0.
#   nextPowerOfTwo(n)  - smallest power of 2 >= n (1 for n <= 1).
#   countDecimalDigits(n) - decimal digit count of |n| (1 for 0).
#   isEven(n) / isOdd(n)  - parity helpers using modulo 2.
# ============================================================


operation intSqrt
input intSqrt n CSignedInt64
output intSqrt Result CSignedInt64 Void
memory intSqrt heap no
memory intSqrt stack max 1KiB
async intSqrt no
purpose intSqrt "Integer square root: floor(sqrt(n)) for n >= 0. Newton iteration: x_{k+1} = (x_k + n/x_k) / 2. Terminates when the iterate stops improving. Returns 0 for n <= 0."

label startIntSqrt
const zeroI64 I64 0
const oneI64 I64 1
const twoI64 I64 2

# n <= 0 -> 0
call leZeroCall math.lessThanOrEqualI64
arg leZeroCall left n
arg leZeroCall right zeroI64
run leZeroCall
bind leZero Bool leZeroCall
branchIf leZero intSqrtZero

# Initial guess: n itself.
var guess I64 0
set guess n

label sqrtLoop
# next = (guess + n/guess) / 2
call divCall math.divideI64
arg divCall left n
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
returnOk guess

label intSqrtZero
returnOk zeroI64


operation factorial
input factorial n CSignedInt64
output factorial Result CSignedInt64 Void
memory factorial heap no
memory factorial stack max 1KiB
async factorial no
purpose factorial "n! for n in 0..20. Returns 1 for n <= 0. For n > 20 the result overflows signed 64-bit; we accept the wrap (matching standard C with -fwrapv)."

label startFactorial
const zeroFac I64 0
const oneFac I64 1

call nLeZeroCall math.lessThanOrEqualI64
arg nLeZeroCall left n
arg nLeZeroCall right zeroFac
run nLeZeroCall
bind nLeZero Bool nLeZeroCall
branchIf nLeZero factorialOne

var product I64 1
var i I64 1
label factorialLoop
call doneCall math.greaterThanI64
arg doneCall left i
arg doneCall right n
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
returnOk product
label factorialOne
returnOk oneFac


operation isPrime
input isPrime n CSignedInt64
output isPrime Result CSignedInt32 Void
memory isPrime heap no
memory isPrime stack max 1KiB
async isPrime no
purpose isPrime "Returns 1 if n is prime, 0 otherwise. n <= 1 -> 0. Tests divisibility by 2 then odd numbers up to floor(sqrt(n))."

label startIsPrime
const zeroP I64 0
const oneP I64 1
const twoP I64 2
const threeP I64 3
const truePr CSignedInt32 1
const falsePr CSignedInt32 0

call leOneCall math.lessThanOrEqualI64
arg leOneCall left n
arg leOneCall right oneP
run leOneCall
bind leOne Bool leOneCall
branchIf leOne isPrimeFalse

call eqTwoCall math.equalI64
arg eqTwoCall left n
arg eqTwoCall right twoP
run eqTwoCall
bind eqTwo Bool eqTwoCall
branchIf eqTwo isPrimeTrue

# Even (other than 2) -> composite.
call modTwoCall math.moduloI64
arg modTwoCall left n
arg modTwoCall right twoP
run modTwoCall
bind nMod2 I64 modTwoCall
call isEvenCall math.equalI64
arg isEvenCall left nMod2
arg isEvenCall right zeroP
run isEvenCall
bind isEven Bool isEvenCall
branchIf isEven isPrimeFalse

# Trial divide by odd i from 3 up to floor(sqrt(n)).
call limitCall intSqrt
arg limitCall n n
run limitCall
bindOk limit CSignedInt64 limitCall

var i I64 3
label trialLoop
call beyondCall math.greaterThanI64
arg beyondCall left i
arg beyondCall right limit
run beyondCall
bind beyond Bool beyondCall
branchIf beyond isPrimeTrue
call rCall math.moduloI64
arg rCall left n
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
returnOk falsePr
label isPrimeTrue
returnOk truePr


operation isPowerOfTwo
input isPowerOfTwo n CSignedInt64
output isPowerOfTwo Result CSignedInt32 Void
memory isPowerOfTwo heap no
memory isPowerOfTwo stack max 1KiB
async isPowerOfTwo no
purpose isPowerOfTwo "Returns 1 if n is a positive power of 2 (1, 2, 4, 8, ...), else 0. Halves n repeatedly while it's even; if result is exactly 1, original was a power of 2."

label startIsPowerOfTwo
const zeroPt I64 0
const oneCount I64 1
const twoPt I64 2
const truePt CSignedInt32 1
const falsePt CSignedInt32 0

call leZeroPtCall math.lessThanOrEqualI64
arg leZeroPtCall left n
arg leZeroPtCall right zeroPt
run leZeroPtCall
bind leZeroPt Bool leZeroPtCall
branchIf leZeroPt isPowerOfTwoFalse

var x I64 0
set x n

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
returnOk falsePt
label isPowerOfTwoTrue
returnOk truePt


operation nextPowerOfTwo
input nextPowerOfTwo n CSignedInt64
output nextPowerOfTwo Result CSignedInt64 Void
memory nextPowerOfTwo heap no
memory nextPowerOfTwo stack max 1KiB
async nextPowerOfTwo no
purpose nextPowerOfTwo "Smallest power of 2 that is >= n. Returns 1 for n <= 1. Doubles 1 until result >= n."

label startNextPowerOfTwo
const zeroNp I64 0
const oneNp I64 1
const twoNp I64 2

call leOneNpCall math.lessThanOrEqualI64
arg leOneNpCall left n
arg leOneNpCall right oneNp
run leOneNpCall
bind leOneNp Bool leOneNpCall
branchIf leOneNp nextPowOne

var p I64 1
label doubleLoop
call gePCall math.greaterThanOrEqualI64
arg gePCall left p
arg gePCall right n
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
returnOk p
label nextPowOne
returnOk oneNp


operation countDecimalDigits
input countDecimalDigits n CSignedInt64
output countDecimalDigits Result CSignedInt64 Void
memory countDecimalDigits heap no
memory countDecimalDigits stack max 1KiB
async countDecimalDigits no
purpose countDecimalDigits "Number of decimal digits in |n|. Returns 1 for n==0. Works for negative n by counting digits of -n."

label startCountDecimalDigits
const zeroCd I64 0
const oneCd I64 1
const tenCd I64 10
const negOneCd I64 -1

call eqZeroCdCall math.equalI64
arg eqZeroCdCall left n
arg eqZeroCdCall right zeroCd
run eqZeroCdCall
bind eqZeroCd Bool eqZeroCdCall
branchIf eqZeroCd countDigitsOne

var v I64 0
set v n
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
returnOk count

label countDigitsOne
returnOk oneCd


operation isEven
input isEven n CSignedInt64
output isEven Result CSignedInt32 Void
memory isEven heap no
memory isEven stack max 1KiB
async isEven no
purpose isEven "1 if n % 2 == 0, else 0."
label startIsEven
const zeroE I64 0
const twoE I64 2
const trueE CSignedInt32 1
const falseE CSignedInt32 0
call modECall math.moduloI64
arg modECall left n
arg modECall right twoE
run modECall
bind modE I64 modECall
call eqZeroECall math.equalI64
arg eqZeroECall left modE
arg eqZeroECall right zeroE
run eqZeroECall
bind eqZeroE Bool eqZeroECall
branchIf eqZeroE isEvenTrue
returnOk falseE
label isEvenTrue
returnOk trueE


operation isOdd
input isOdd n CSignedInt64
output isOdd Result CSignedInt32 Void
memory isOdd heap no
memory isOdd stack max 1KiB
async isOdd no
purpose isOdd "1 if n % 2 != 0, else 0."
label startIsOdd
const zeroO I64 0
const twoO I64 2
const trueO CSignedInt32 1
const falseO CSignedInt32 0
call modOCall math.moduloI64
arg modOCall left n
arg modOCall right twoO
run modOCall
bind modO I64 modOCall
call neZeroOCall math.notEqualI64
arg neZeroOCall left modO
arg neZeroOCall right zeroO
run neZeroOCall
bind neZeroO Bool neZeroOCall
branchIf neZeroO isOddTrue
returnOk falseO
label isOddTrue
returnOk trueO


operation countSetBits
input countSetBits n CSignedInt64
output countSetBits Result CSignedInt64 Void
memory countSetBits heap no
async countSetBits no
purpose countSetBits "Population count of n (number of 1-bits). Uses mod-2 / div-2 since AS doesn't have bitwise primitives. Works on non-negative n; negative inputs work modulo 2's-complement representation."
label startCountSetBits
const zeroPc I64 0
const onePc I64 1
const twoPc I64 2
const limitPc I64 64
var pcVal I64 0
set pcVal n
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
returnOk pcCount


operation countTrailingZeros
input countTrailingZeros n CSignedInt64
output countTrailingZeros Result CSignedInt64 Void
memory countTrailingZeros heap no
async countTrailingZeros no
purpose countTrailingZeros "Trailing zero bits of n. Returns 64 for n == 0 (matching the GCC __builtin_ctzll convention for zero)."
label startCountTrailingZeros
const zeroTz I64 0
const oneTz I64 1
const twoTz I64 2
const sixtyFourTz I64 64
# Special case n == 0
call eqZeroTz math.equalI64
arg eqZeroTz left n
arg eqZeroTz right zeroTz
run eqZeroTz
bind nIsZero Bool eqZeroTz
branchIf nIsZero tzReturn64
var tzVal I64 0
set tzVal n
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
returnOk tzCount
label tzReturn64
returnOk sixtyFourTz


operation signumInt
input signumInt n CSignedInt64
output signumInt Result CSignedInt64 Void
memory signumInt heap no
async signumInt no
purpose signumInt "Returns -1 if n < 0, +1 if n > 0, 0 if n == 0."
label startSignumInt
const zeroSi I64 0
const oneSi I64 1
const negOneSi I64 -1
call ltCheck math.lessThanI64
arg ltCheck left n
arg ltCheck right zeroSi
run ltCheck
bind isNg Bool ltCheck
branchIf isNg siNeg
call gtCheck math.greaterThanI64
arg gtCheck left n
arg gtCheck right zeroSi
run gtCheck
bind isPs Bool gtCheck
branchIf isPs siPos
returnOk zeroSi
label siNeg
returnOk negOneSi
label siPos
returnOk oneSi


operation absDiffInt
input absDiffInt a CSignedInt64
input absDiffInt b CSignedInt64
output absDiffInt Result CSignedInt64 Void
memory absDiffInt heap no
async absDiffInt no
purpose absDiffInt "Absolute difference |a - b|. Inlines the absolute-value flip rather than depending on stdlib.as#absoluteInt (each stdlib_as file is self-contained today; cross-file operation calls aren't wired up yet)."
label startAbsDiffInt
const zeroAdi I64 0
const negOneAdi I64 -1
call diffCall math.subtractI64
arg diffCall left a
arg diffCall right b
run diffCall
bind diff I64 diffCall
call lt0 math.lessThanI64
arg lt0 left diff
arg lt0 right zeroAdi
run lt0
bind diffNeg Bool lt0
branchIf diffNeg flipDiff
returnOk diff
label flipDiff
call flip math.multiplyI64
arg flip left diff
arg flip right negOneAdi
run flip
bind absDiff CSignedInt64 flip
returnOk absDiff


operation countLeadingZeros
input countLeadingZeros n CSignedInt64
output countLeadingZeros Result CSignedInt64 Void
memory countLeadingZeros heap no
async countLeadingZeros no
purpose countLeadingZeros "Number of leading zero bits of n in its 64-bit representation. Returns 64 for n == 0. Pure AS: doubles a probe bit until it's > n."
label startCountLeadingZeros
const zeroClz I64 0
const oneClz I64 1
const twoClz I64 2
const sixtyFourClz I64 64
call eqZeroClzCall math.equalI64
arg eqZeroClzCall left n
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
arg probeLe right n
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
returnOk clzCount
label clzReturn64
returnOk sixtyFourClz


operation squareInt
input squareInt x CSignedInt64
output squareInt Result CSignedInt64 Void
memory squareInt heap no
async squareInt no
purpose squareInt "x * x."
label startSquareInt
call sqCall math.multiplyI64
arg sqCall left x
arg sqCall right x
run sqCall
bind r CSignedInt64 sqCall
returnOk r


operation cubeInt
input cubeInt x CSignedInt64
output cubeInt Result CSignedInt64 Void
memory cubeInt heap no
async cubeInt no
purpose cubeInt "x * x * x."
label startCubeInt
call sq1 math.multiplyI64
arg sq1 left x
arg sq1 right x
run sq1
bind sq CSignedInt64 sq1
call cb math.multiplyI64
arg cb left sq
arg cb right x
run cb
bind r CSignedInt64 cb
returnOk r


operation isInRangeInt
input isInRangeInt x CSignedInt64
input isInRangeInt lo CSignedInt64
input isInRangeInt hi CSignedInt64
output isInRangeInt Result CSignedInt32 Void
memory isInRangeInt heap no
async isInRangeInt no
purpose isInRangeInt "1 if lo <= x <= hi, else 0."
label startIsInRangeInt
const trueIR CSignedInt32 1
const falseIR CSignedInt32 0
call belowLo math.lessThanI64
arg belowLo left x
arg belowLo right lo
run belowLo
bind below Bool belowLo
branchIf below irFalse
call aboveHi math.greaterThanI64
arg aboveHi left x
arg aboveHi right hi
run aboveHi
bind above Bool aboveHi
branchIf above irFalse
returnOk trueIR
label irFalse
returnOk falseIR


# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test integer math ports. Prints OK."

label startMain
const oneE I64 1
const trueChk CSignedInt32 1
const falseChk CSignedInt32 0

# intSqrt(144) == 12
const c144 CSignedInt64 144
const c12 CSignedInt64 12
call s1 intSqrt
arg s1 n c144
run s1
bindOk s1Res CSignedInt64 s1
call s1Check math.equalI64
arg s1Check left s1Res
arg s1Check right c12
run s1Check
bind s1Ok Bool s1Check
branchIf s1Ok s1OkLabel
branch testFailed
label s1OkLabel

# factorial(5) == 120
const c5 CSignedInt64 5
const c120 CSignedInt64 120
call f1 factorial
arg f1 n c5
run f1
bindOk f1Res CSignedInt64 f1
call f1Check math.equalI64
arg f1Check left f1Res
arg f1Check right c120
run f1Check
bind f1Ok Bool f1Check
branchIf f1Ok f1OkLabel
branch testFailed
label f1OkLabel

# isPrime(17) == 1
const c17 CSignedInt64 17
call pr1 isPrime
arg pr1 n c17
run pr1
bindOk pr1Res CSignedInt32 pr1
call pr1Check math.equalI64
arg pr1Check left pr1Res
arg pr1Check right trueChk
run pr1Check
bind pr1Ok Bool pr1Check
branchIf pr1Ok pr1OkLabel
branch testFailed
label pr1OkLabel

# isPrime(15) == 0
const c15 CSignedInt64 15
call pr2 isPrime
arg pr2 n c15
run pr2
bindOk pr2Res CSignedInt32 pr2
call pr2Check math.equalI64
arg pr2Check left pr2Res
arg pr2Check right falseChk
run pr2Check
bind pr2Ok Bool pr2Check
branchIf pr2Ok pr2OkLabel
branch testFailed
label pr2OkLabel

# isPowerOfTwo(64) == 1
const c64 CSignedInt64 64
call pt1 isPowerOfTwo
arg pt1 n c64
run pt1
bindOk pt1Res CSignedInt32 pt1
call pt1Check math.equalI64
arg pt1Check left pt1Res
arg pt1Check right trueChk
run pt1Check
bind pt1Ok Bool pt1Check
branchIf pt1Ok pt1OkLabel
branch testFailed
label pt1OkLabel

# isPowerOfTwo(48) == 0
const c48 CSignedInt64 48
call pt2 isPowerOfTwo
arg pt2 n c48
run pt2
bindOk pt2Res CSignedInt32 pt2
call pt2Check math.equalI64
arg pt2Check left pt2Res
arg pt2Check right falseChk
run pt2Check
bind pt2Ok Bool pt2Check
branchIf pt2Ok pt2OkLabel
branch testFailed
label pt2OkLabel

# nextPowerOfTwo(100) == 128
const c100 CSignedInt64 100
const c128 CSignedInt64 128
call np1 nextPowerOfTwo
arg np1 n c100
run np1
bindOk np1Res CSignedInt64 np1
call np1Check math.equalI64
arg np1Check left np1Res
arg np1Check right c128
run np1Check
bind np1Ok Bool np1Check
branchIf np1Ok np1OkLabel
branch testFailed
label np1OkLabel

# countDecimalDigits(12345) == 5
const c12345 CSignedInt64 12345
const c5lim CSignedInt64 5
call cd1 countDecimalDigits
arg cd1 n c12345
run cd1
bindOk cd1Res CSignedInt64 cd1
call cd1Check math.equalI64
arg cd1Check left cd1Res
arg cd1Check right c5lim
run cd1Check
bind cd1Ok Bool cd1Check
branchIf cd1Ok cd1OkLabel
branch testFailed
label cd1OkLabel

# isEven(10) == 1, isOdd(10) == 0
const c10 CSignedInt64 10
call ev1 isEven
arg ev1 n c10
run ev1
bindOk ev1Res CSignedInt32 ev1
call ev1Check math.equalI64
arg ev1Check left ev1Res
arg ev1Check right trueChk
run ev1Check
bind ev1Ok Bool ev1Check
branchIf ev1Ok ev1OkLabel
branch testFailed
label ev1OkLabel

call od1 isOdd
arg od1 n c10
run od1
bindOk od1Res CSignedInt32 od1
call od1Check math.equalI64
arg od1Check left od1Res
arg od1Check right falseChk
run od1Check
bind od1Ok Bool od1Check
branchIf od1Ok od1OkLabel
branch testFailed
label od1OkLabel

# countSetBits(0b1101) = countSetBits(13) == 3
const c13 CSignedInt64 13
const c3 CSignedInt64 3
call pc1 countSetBits
arg pc1 n c13
run pc1
bindOk pc1Res CSignedInt64 pc1
call pc1Check math.equalI64
arg pc1Check left pc1Res
arg pc1Check right c3
run pc1Check
bind pc1Ok Bool pc1Check
branchIf pc1Ok pc1OkLabel
branch testFailed
label pc1OkLabel

# countTrailingZeros(16) == 4
const c16ct CSignedInt64 16
const c4ct CSignedInt64 4
call ctz1 countTrailingZeros
arg ctz1 n c16ct
run ctz1
bindOk ctz1Res CSignedInt64 ctz1
call ctz1Check math.equalI64
arg ctz1Check left ctz1Res
arg ctz1Check right c4ct
run ctz1Check
bind ctz1Ok Bool ctz1Check
branchIf ctz1Ok ctz1OkLabel
branch testFailed
label ctz1OkLabel

# signumInt(-5) == -1
const cNeg5 CSignedInt64 -5
const cNeg1 CSignedInt64 -1
call sgn1 signumInt
arg sgn1 n cNeg5
run sgn1
bindOk sgn1Res CSignedInt64 sgn1
call sgn1Check math.equalI64
arg sgn1Check left sgn1Res
arg sgn1Check right cNeg1
run sgn1Check
bind sgn1Ok Bool sgn1Check
branchIf sgn1Ok sgn1OkLabel
branch testFailed
label sgn1OkLabel

# absDiffInt(10, 3) == 7
const c10ad CSignedInt64 10
const c3ad CSignedInt64 3
const c7ad CSignedInt64 7
call ad1 absDiffInt
arg ad1 a c10ad
arg ad1 b c3ad
run ad1
bindOk ad1Res CSignedInt64 ad1
call ad1Check math.equalI64
arg ad1Check left ad1Res
arg ad1Check right c7ad
run ad1Check
bind ad1Ok Bool ad1Check
branchIf ad1Ok ad1OkLabel
branch testFailed
label ad1OkLabel

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
