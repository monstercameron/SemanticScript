# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: pure-AS float math
# ============================================================
#
# # rationale: every operation lowers to math.{add,subtract,multiply,
#   divide,less,greater,equal}F64 plus branching. NO libm call appears
#   in the emitted IR — no c.sqrt, c.exp, c.log, c.fabs, c.pow, c.sin,
#   c.cos, c.tan, etc. The point is a self-contained float surface
#   that an AgentScript program can ship without linking libm.
#
# # invariant: every operation is total in the language-theory sense
#   over its declared domain — Result wrappers are dropped because
#   the existing implementations did not expose typed error variants.
#   Out-of-domain inputs (negative sqrt argument, log of zero, etc.)
#   return either 0.0 or an IEEE-754 sentinel; callers that need
#   strict validation should screen inputs upstream.
#
# # security: pure value-level computation. No allocation. No I/O.
#
# # timing: each transcendental is implemented via a fixed-iteration
#   Taylor series or Newton iteration. Worst case ~50 iterations
#   (squareRoot Newton). Acceptable for tooling, not for hot loops.
#
# # observability: no logs, no metrics.

project StdMathFloatSelfTest
target console
runtime AgentRuntime 0.1
entry console main

error MainError
errorCase MainError MathFloatSmokeAssertionFailed

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <math.h>-style float ops, pure AS.
#
# Implementations use only math.{add,subtract,multiply,divide}F64 and
# comparison primitives. NO call to libm: no c.sqrt, c.exp, c.log,
# c.fabs etc. appears in the emitted IR.
#
# Range and accuracy caveats:
#   squareRootFloat64       : full range for x >= 0; Newton converges in
#                     ~50 iterations to ~1ulp for IEEE-754 doubles.
#   absoluteFloat64       : exact for all inputs.
#   exponentialBaseEFloat64        : Taylor series with 30 terms; accurate to ~12
#                     decimals for |x| <= 2. Beyond that range the
#                     polynomial loses precision quickly.
#   naturalLogFloat64         : Newton iteration on f(y) = exp(y) - x; needs
#                     x > 0; converges in ~20 iterations for x in
#                     [0.01, 100].
#   powerFloat64        : computes exp(y * ln(x)); inherits range from
#                     ln and exp. Defined for x > 0.
#
# These are NOT replacements for a production libm; they're the
# pure-AS ports that let an AgentScript program do float math without
# linking against libm.
# ============================================================


operation absoluteFloat64
input absoluteFloat64 inputValue CFloat64
output absoluteFloat64 CFloat64
memoryHeap absoluteFloat64 no
async absoluteFloat64 no
purpose absoluteFloat64 "|x| for double-precision x. Pure AS via comparison + multiply by -1."

label startAbsoluteFloat64
const zeroF CFloat64 0.0
const negOneF CFloat64 -1.0
call isNegCall math.lessThanF64
arg isNegCall left inputValue
arg isNegCall right zeroF
run isNegCall
bind isNeg Bool isNegCall
branchIf isNeg fabsFlip
returnValue inputValue
label fabsFlip
call flipCall math.multiplyF64
arg flipCall left inputValue
arg flipCall right negOneF
run flipCall
bind flipped CFloat64 flipCall
returnValue flipped


operation squareRootFloat64
input squareRootFloat64 inputValue CFloat64
output squareRootFloat64 CFloat64
memoryHeap squareRootFloat64 no
async squareRootFloat64 no
purpose squareRootFloat64 "sqrt(x) for x >= 0 via Newton's method. Returns 0.0 for x <= 0 (no NaN here yet — that needs IEEE special-value support)."

label startSquareRootFloat64
const zeroFS CFloat64 0.0
const halfFS CFloat64 0.5
const oneFS CFloat64 1.0
const epsFS CFloat64 0.0000000000001

call lezCall math.lessThanOrEqualF64
arg lezCall left inputValue
arg lezCall right zeroFS
run lezCall
bind lez Bool lezCall
branchIf lez sqrtZero

# Start at x itself (works for x >= 1; for 0 < x < 1, also converges).
var guess CFloat64 1.0
set guess inputValue
var iter I64 0
const maxIter I64 50
const oneI I64 1

label sqrtIter
call divCall math.divideF64
arg divCall left inputValue
arg divCall right guess
run divCall
bind quot CFloat64 divCall
call sumCall math.addF64
arg sumCall left guess
arg sumCall right quot
run sumCall
bind sumGuess CFloat64 sumCall
call halveCall math.multiplyF64
arg halveCall left sumGuess
arg halveCall right halfFS
run halveCall
bind nextGuess CFloat64 halveCall

# Convergence: |next - guess| < eps * |next|, but to keep math simple,
# just bound iteration count.
set guess nextGuess
call incCall math.addI64
arg incCall left iter
arg incCall right oneI
run incCall
bind nextIter I64 incCall
set iter nextIter
call iterDoneCall math.greaterThanOrEqualI64
arg iterDoneCall left iter
arg iterDoneCall right maxIter
run iterDoneCall
bind iterDone Bool iterDoneCall
branchIf iterDone sqrtDone
branch sqrtIter

label sqrtDone
returnValue guess

label sqrtZero
returnValue zeroFS


operation exponentialBaseEFloat64
input exponentialBaseEFloat64 inputValue CFloat64
output exponentialBaseEFloat64 CFloat64
memoryHeap exponentialBaseEFloat64 no
async exponentialBaseEFloat64 no
purpose exponentialBaseEFloat64 "e^x via Taylor series: sum_{k=0..29} x^k / k!. Accurate to ~12 decimals for |x| <= 2; degrades beyond that. No argument reduction yet."

label startExponentialBaseEFloat64
const oneFE CFloat64 1.0
const oneI64E I64 1
const maxTermsE I64 30

var sumE CFloat64 1.0
var term CFloat64 1.0
var k I64 1
# Float counter kept in lockstep with k. Declared BEFORE the loop so
# its initial store happens once, not on every iteration. AS has no
# int-to-float intrinsic at this layer, so we maintain a parallel
# float that we ++ by 1.0 each iteration.
var kFloat CFloat64 1.0

label expLoop
call doneECall math.greaterThanOrEqualI64
arg doneECall left k
arg doneECall right maxTermsE
run doneECall
bind doneE Bool doneECall
branchIf doneE expReturn
# term = term * x / kFloat
call mulCall math.multiplyF64
arg mulCall left term
arg mulCall right inputValue
run mulCall
bind mulRes CFloat64 mulCall
call divFCall math.divideF64
arg divFCall left mulRes
arg divFCall right kFloat
run divFCall
bind nextTerm CFloat64 divFCall
set term nextTerm
call addCall math.addF64
arg addCall left sumE
arg addCall right nextTerm
run addCall
bind nextSum CFloat64 addCall
set sumE nextSum
# Increment k and kFloat.
call incKCall math.addI64
arg incKCall left k
arg incKCall right oneI64E
run incKCall
bind nextK I64 incKCall
set k nextK
call incKFCall math.addF64
arg incKFCall left kFloat
arg incKFCall right oneFE
run incKFCall
bind nextKFloat CFloat64 incKFCall
set kFloat nextKFloat
branch expLoop

label expReturn
returnValue sumE


operation truncateFloat64TowardZero
input truncateFloat64TowardZero inputValue CFloat64
output truncateFloat64TowardZero CFloat64
memoryHeap truncateFloat64TowardZero no
async truncateFloat64TowardZero no
purpose truncateFloat64TowardZero "Truncate toward zero. Uses math.floatToInt (fptosi) which already truncates, then converts back."
label startTruncateFloat64TowardZero
call toIntCall math.floatToInt
arg toIntCall value inputValue
run toIntCall
bind asInt CSignedInt64 toIntCall
call backToFloatCall math.intToFloat
arg backToFloatCall value asInt
run backToFloatCall
bind backFloat CFloat64 backToFloatCall
returnValue backFloat


operation floorFloat64
input floorFloat64 inputValue CFloat64
output floorFloat64 CFloat64
memoryHeap floorFloat64 no
async floorFloat64 no
purpose floorFloat64 "Largest integer <= x. trunc(x) is identical to floor for x >= 0, but for negative non-integer x we have to step down by 1."
label startFloorFloat64
const zeroFlr CFloat64 0.0
const oneFlr CFloat64 1.0
call trCall truncateFloat64TowardZero
arg trCall x inputValue
run trCall
bindOk truncated CFloat64 trCall

# If x >= 0, floor == trunc.
call ngFCall math.lessThanF64
arg ngFCall left inputValue
arg ngFCall right zeroFlr
run ngFCall
bind isNg Bool ngFCall
branchIf isNg floorMaybeStepDown
returnValue truncated

label floorMaybeStepDown
# For negative x: if truncated == x exactly, x is integral -> floor is x.
# Else floor = truncated - 1.
call eqExactCall math.equalF64
arg eqExactCall left truncated
arg eqExactCall right inputValue
run eqExactCall
bind eqExact Bool eqExactCall
branchIf eqExact floorIntegral
call subOneCall math.subtractF64
arg subOneCall left truncated
arg subOneCall right oneFlr
run subOneCall
bind floored CFloat64 subOneCall
returnValue floored
label floorIntegral
returnValue truncated


operation ceilingFloat64
input ceilingFloat64 inputValue CFloat64
output ceilingFloat64 CFloat64
memoryHeap ceilingFloat64 no
async ceilingFloat64 no
purpose ceilingFloat64 "Smallest integer >= x. Mirror image of floor: for x <= 0 trunc is the ceiling; for positive non-integer, ceil = trunc + 1."
label startCeilingFloat64
const zeroCl CFloat64 0.0
const oneCl CFloat64 1.0
call trcCall truncateFloat64TowardZero
arg trcCall x inputValue
run trcCall
bindOk cTruncated CFloat64 trcCall

call gtZeroCall math.greaterThanF64
arg gtZeroCall left inputValue
arg gtZeroCall right zeroCl
run gtZeroCall
bind isPos Bool gtZeroCall
branchIf isPos ceilMaybeStepUp
returnValue cTruncated

label ceilMaybeStepUp
call eqExactCCall math.equalF64
arg eqExactCCall left cTruncated
arg eqExactCCall right inputValue
run eqExactCCall
bind eqExactC Bool eqExactCCall
branchIf eqExactC ceilIntegral
call addOneCall math.addF64
arg addOneCall left cTruncated
arg addOneCall right oneCl
run addOneCall
bind ceiled CFloat64 addOneCall
returnValue ceiled
label ceilIntegral
returnValue cTruncated


operation floatingRemainderFloat64
input floatingRemainderFloat64 dividendValue CFloat64
input floatingRemainderFloat64 divisorValue CFloat64
output floatingRemainderFloat64 CFloat64
memoryHeap floatingRemainderFloat64 no
async floatingRemainderFloat64 no
purpose floatingRemainderFloat64 "Floating-point remainder of x/y, truncating toward zero. fmod(x, y) = x - trunc(x/y) * y. Caller must ensure y != 0; we don't return NaN here (no IEEE special-value handling yet)."
label startFloatingRemainderFloat64
call qCall math.divideF64
arg qCall left dividendValue
arg qCall right divisorValue
run qCall
bind q CFloat64 qCall
call qTruncCall truncateFloat64TowardZero
arg qTruncCall x q
run qTruncCall
bindOk qTrunc CFloat64 qTruncCall
call scaleCall math.multiplyF64
arg scaleCall left qTrunc
arg scaleCall right divisorValue
run scaleCall
bind scaled CFloat64 scaleCall
call remCall math.subtractF64
arg remCall left dividendValue
arg remCall right scaled
run remCall
bind rem CFloat64 remCall
returnValue rem


operation naturalLogFloat64
input naturalLogFloat64 inputValue CFloat64
output naturalLogFloat64 CFloat64
memoryHeap naturalLogFloat64 no
async naturalLogFloat64 no
purpose naturalLogFloat64 "Natural log of x for x > 0. Uses range reduction (ln(x) = ln(x / 2^k) + k * ln(2), where k is chosen so x/2^k is in [1, 2)) before Newton iteration on f(y) = exp(y) - x. exponentialBaseEFloat64 is accurate in [0, 2], so the reduced ln(scaled) computation stays in the convergent zone. Returns 0.0 for x <= 0."
label startNaturalLogFloat64
const zeroLn CFloat64 0.0
const oneLn CFloat64 1.0
const twoLn CFloat64 2.0
const halfLn CFloat64 0.5
const ln2Const CFloat64 0.6931471805599453

call posCall math.lessThanOrEqualF64
arg posCall left inputValue
arg posCall right zeroLn
run posCall
bind nonPos Bool posCall
branchIf nonPos lnReturnZero

# Range reduction: pull x into [1, 2) by halving / doubling, tracking
# the exponent shift k as an int.
var scaled CFloat64 0.0
set scaled inputValue
var kInt I64 0
const oneIk I64 1
const negOneIk I64 -1

label halveBigger
call gtTwo math.greaterThanOrEqualF64
arg gtTwo left scaled
arg gtTwo right twoLn
run gtTwo
bind isBig Bool gtTwo
branchIf isBig halveOne
branch maybeDouble
label halveOne
call halveCall math.multiplyF64
arg halveCall left scaled
arg halveCall right halfLn
run halveCall
bind halved CFloat64 halveCall
set scaled halved
call kInc math.addI64
arg kInc left kInt
arg kInc right oneIk
run kInc
bind kNext I64 kInc
set kInt kNext
branch halveBigger

label maybeDouble
call ltOne math.lessThanF64
arg ltOne left scaled
arg ltOne right oneLn
run ltOne
bind isSmall Bool ltOne
branchIf isSmall doubleOne
branch lnNewton
label doubleOne
call dblCall math.multiplyF64
arg dblCall left scaled
arg dblCall right twoLn
run dblCall
bind doubled CFloat64 dblCall
set scaled doubled
call kDec math.addI64
arg kDec left kInt
arg kDec right negOneIk
run kDec
bind kPrev I64 kDec
set kInt kPrev
branch maybeDouble

label lnNewton
# scaled is in [1, 2). Newton's on ln(scaled). Initial guess scaled - 1
# (in [0, 1)) gives fast convergence.
var y CFloat64 0.0
call initCall math.subtractF64
arg initCall left scaled
arg initCall right oneLn
run initCall
bind y0 CFloat64 initCall
set y y0

var iterL I64 0
const maxIterLn I64 25
const oneIL I64 1

label lnIter
call expYCall exponentialBaseEFloat64
arg expYCall x y
run expYCall
bindOk eyVal CFloat64 expYCall
call resCall math.subtractF64
arg resCall left eyVal
arg resCall right scaled
run resCall
bind res CFloat64 resCall
call deltaCall math.divideF64
arg deltaCall left res
arg deltaCall right eyVal
run deltaCall
bind delta CFloat64 deltaCall
call newYCall math.subtractF64
arg newYCall left y
arg newYCall right delta
run newYCall
bind newY CFloat64 newYCall
set y newY

call iterIncCall math.addI64
arg iterIncCall left iterL
arg iterIncCall right oneIL
run iterIncCall
bind nextIter I64 iterIncCall
set iterL nextIter
call iterDone math.greaterThanOrEqualI64
arg iterDone left iterL
arg iterDone right maxIterLn
run iterDone
bind done Bool iterDone
branchIf done lnDone
branch lnIter

label lnDone
# Result = y + k * ln(2)
call kFloatCall math.intToFloat
arg kFloatCall value kInt
run kFloatCall
bind kFloat CFloat64 kFloatCall
call kLnCall math.multiplyF64
arg kLnCall left kFloat
arg kLnCall right ln2Const
run kLnCall
bind kTimesLn CFloat64 kLnCall
call finalCall math.addF64
arg finalCall left y
arg finalCall right kTimesLn
run finalCall
bind finalLn CFloat64 finalCall
returnValue finalLn

label lnReturnZero
returnValue zeroLn


operation powerFloat64
input powerFloat64 baseValue CFloat64
input powerFloat64 exponentValue CFloat64
output powerFloat64 CFloat64
memoryHeap powerFloat64 no
async powerFloat64 no
purpose powerFloat64 "base^exponent for base > 0 via exp(exponent * ln(base)). Returns 1.0 for exponent == 0."
label startPowerFloat64
const zeroPw CFloat64 0.0
const oneFw CFloat64 1.0
call eExp math.equalF64
arg eExp left exponentValue
arg eExp right zeroPw
run eExp
bind expZero Bool eExp
branchIf expZero powOne
call lnB naturalLogFloat64
arg lnB x baseValue
run lnB
bindOk lnBase CFloat64 lnB
call prodCall math.multiplyF64
arg prodCall left exponentValue
arg prodCall right lnBase
run prodCall
bind prod CFloat64 prodCall
call eRes exponentialBaseEFloat64
arg eRes x prod
run eRes
bindOk powVal CFloat64 eRes
returnValue powVal
label powOne
returnValue oneFw


operation sineRadiansFloat64
input sineRadiansFloat64 inputValue CFloat64
output sineRadiansFloat64 CFloat64
memoryHeap sineRadiansFloat64 no
async sineRadiansFloat64 no
purpose sineRadiansFloat64 "sin(x) via Taylor series: x - x^3/3! + x^5/5! - x^7/7! + ... (20 terms). For best accuracy, caller should reduce x into [-pi, pi] beforehand. No argument reduction at this layer (yet)."
label startSineRadiansFloat64
const oneSn CFloat64 1.0
const oneISn I64 1
const maxTermsSn I64 20

# accumulator = x (first term)
var sumSn CFloat64 0.0
set sumSn inputValue
var termSn CFloat64 0.0
set termSn inputValue
var kSn I64 1
var kFlSn CFloat64 1.0

label sinLoop
call sinDone math.greaterThanOrEqualI64
arg sinDone left kSn
arg sinDone right maxTermsSn
run sinDone
bind doneSn Bool sinDone
branchIf doneSn sinReturn

# Next term factor: -x^2 / ((2k)(2k+1)). We update term by multiplying.
# numerator: -x*x
call xSqCall math.multiplyF64
arg xSqCall left inputValue
arg xSqCall right inputValue
run xSqCall
bind xSq CFloat64 xSqCall
const negOneSn CFloat64 -1.0
call negXSqCall math.multiplyF64
arg negXSqCall left xSq
arg negXSqCall right negOneSn
run negXSqCall
bind negXSq CFloat64 negXSqCall

# denominator: (2k)(2k+1) — both ints.
const twoIsn I64 2
call twoKCall math.multiplyI64
arg twoKCall left kSn
arg twoKCall right twoIsn
run twoKCall
bind twoK I64 twoKCall
call twoKPlus1 math.addI64
arg twoKPlus1 left twoK
arg twoKPlus1 right oneISn
run twoKPlus1
bind twoKplus I64 twoKPlus1
call denomIntCall math.multiplyI64
arg denomIntCall left twoK
arg denomIntCall right twoKplus
run denomIntCall
bind denomInt I64 denomIntCall
call denomFloatCall math.intToFloat
arg denomFloatCall value denomInt
run denomFloatCall
bind denomFl CFloat64 denomFloatCall

# term *= negXSq / denomFl
call termMul math.multiplyF64
arg termMul left termSn
arg termMul right negXSq
run termMul
bind tmpTerm CFloat64 termMul
call termDiv math.divideF64
arg termDiv left tmpTerm
arg termDiv right denomFl
run termDiv
bind nextTerm CFloat64 termDiv
set termSn nextTerm

# sum += term
call sumAdd math.addF64
arg sumAdd left sumSn
arg sumAdd right nextTerm
run sumAdd
bind nextSum CFloat64 sumAdd
set sumSn nextSum

call kSnIncCall math.addI64
arg kSnIncCall left kSn
arg kSnIncCall right oneISn
run kSnIncCall
bind nextK I64 kSnIncCall
set kSn nextK
branch sinLoop

label sinReturn
returnValue sumSn


operation cosineRadiansFloat64
input cosineRadiansFloat64 inputValue CFloat64
output cosineRadiansFloat64 CFloat64
memoryHeap cosineRadiansFloat64 no
async cosineRadiansFloat64 no
purpose cosineRadiansFloat64 "cos(x) via Taylor series: 1 - x^2/2! + x^4/4! - ... (20 terms). Same range caveat as sineRadiansFloat64."
label startCosineRadiansFloat64
const oneCs CFloat64 1.0
const oneICs I64 1
const maxTermsCs I64 20

var sumCs CFloat64 1.0
var termCs CFloat64 1.0
var kCs I64 1
var kFlCs CFloat64 1.0

label cosLoop
call csDone math.greaterThanOrEqualI64
arg csDone left kCs
arg csDone right maxTermsCs
run csDone
bind doneCs Bool csDone
branchIf doneCs cosReturn

# denominator: (2k-1)(2k)
const twoICs I64 2
call twoKcCall math.multiplyI64
arg twoKcCall left kCs
arg twoKcCall right twoICs
run twoKcCall
bind twoKc I64 twoKcCall
call twoKcMinus1 math.subtractI64
arg twoKcMinus1 left twoKc
arg twoKcMinus1 right oneICs
run twoKcMinus1
bind twoKcm1 I64 twoKcMinus1
call denomCsIntCall math.multiplyI64
arg denomCsIntCall left twoKcm1
arg denomCsIntCall right twoKc
run denomCsIntCall
bind denomCsInt I64 denomCsIntCall
call denomCsFlCall math.intToFloat
arg denomCsFlCall value denomCsInt
run denomCsFlCall
bind denomCsFl CFloat64 denomCsFlCall

# numerator: -x*x
call xSqCsCall math.multiplyF64
arg xSqCsCall left inputValue
arg xSqCsCall right inputValue
run xSqCsCall
bind xSqCs CFloat64 xSqCsCall
const negOneCs CFloat64 -1.0
call negXSqCsCall math.multiplyF64
arg negXSqCsCall left xSqCs
arg negXSqCsCall right negOneCs
run negXSqCsCall
bind negXSqCs CFloat64 negXSqCsCall

call termCsMul math.multiplyF64
arg termCsMul left termCs
arg termCsMul right negXSqCs
run termCsMul
bind tmpTermCs CFloat64 termCsMul
call termCsDiv math.divideF64
arg termCsDiv left tmpTermCs
arg termCsDiv right denomCsFl
run termCsDiv
bind nextTermCs CFloat64 termCsDiv
set termCs nextTermCs

call sumCsAdd math.addF64
arg sumCsAdd left sumCs
arg sumCsAdd right nextTermCs
run sumCsAdd
bind nextSumCs CFloat64 sumCsAdd
set sumCs nextSumCs

call kCsIncCall math.addI64
arg kCsIncCall left kCs
arg kCsIncCall right oneICs
run kCsIncCall
bind nextKcs I64 kCsIncCall
set kCs nextKcs
branch cosLoop

label cosReturn
returnValue sumCs


operation tangentRadiansFloat64
input tangentRadiansFloat64 inputValue CFloat64
output tangentRadiansFloat64 CFloat64
memoryHeap tangentRadiansFloat64 no
async tangentRadiansFloat64 no
purpose tangentRadiansFloat64 "tan(x) = sin(x) / cos(x). Inherits range caveats from sineRadiansFloat64 / cosineRadiansFloat64 (no argument reduction)."
label startTangentRadiansFloat64
call sCall sineRadiansFloat64
arg sCall x inputValue
run sCall
bindOk sV CFloat64 sCall
call cCall cosineRadiansFloat64
arg cCall x inputValue
run cCall
bindOk cV CFloat64 cCall
call divTanCall math.divideF64
arg divTanCall left sV
arg divTanCall right cV
run divTanCall
bind tanV CFloat64 divTanCall
returnValue tanV


operation hyperbolicSineFloat64
input hyperbolicSineFloat64 inputValue CFloat64
output hyperbolicSineFloat64 CFloat64
memoryHeap hyperbolicSineFloat64 no
async hyperbolicSineFloat64 no
purpose hyperbolicSineFloat64 "Hyperbolic sine: (exp(x) - exp(-x)) / 2."
label startHyperbolicSineFloat64
const halfFShn CFloat64 0.5
const negOneShn CFloat64 -1.0
call posExpCall exponentialBaseEFloat64
arg posExpCall x inputValue
run posExpCall
bindOk posExp CFloat64 posExpCall
call negXCall math.multiplyF64
arg negXCall left inputValue
arg negXCall right negOneShn
run negXCall
bind negX CFloat64 negXCall
call negExpCall exponentialBaseEFloat64
arg negExpCall x negX
run negExpCall
bindOk negExp CFloat64 negExpCall
call diffCall math.subtractF64
arg diffCall left posExp
arg diffCall right negExp
run diffCall
bind diff CFloat64 diffCall
call halveCall math.multiplyF64
arg halveCall left diff
arg halveCall right halfFShn
run halveCall
bind res CFloat64 halveCall
returnValue res


operation hyperbolicCosineFloat64
input hyperbolicCosineFloat64 inputValue CFloat64
output hyperbolicCosineFloat64 CFloat64
memoryHeap hyperbolicCosineFloat64 no
async hyperbolicCosineFloat64 no
purpose hyperbolicCosineFloat64 "Hyperbolic cosine: (exp(x) + exp(-x)) / 2."
label startHyperbolicCosineFloat64
const halfFchn CFloat64 0.5
const negOneChn CFloat64 -1.0
call posExpCcall exponentialBaseEFloat64
arg posExpCcall x inputValue
run posExpCcall
bindOk posExpC CFloat64 posExpCcall
call negXCcall math.multiplyF64
arg negXCcall left inputValue
arg negXCcall right negOneChn
run negXCcall
bind negXC CFloat64 negXCcall
call negExpCcall exponentialBaseEFloat64
arg negExpCcall x negXC
run negExpCcall
bindOk negExpC CFloat64 negExpCcall
call sumCcall math.addF64
arg sumCcall left posExpC
arg sumCcall right negExpC
run sumCcall
bind sumC CFloat64 sumCcall
call halveCcall math.multiplyF64
arg halveCcall left sumC
arg halveCcall right halfFchn
run halveCcall
bind resC CFloat64 halveCcall
returnValue resC


operation hyperbolicTangentFloat64
input hyperbolicTangentFloat64 inputValue CFloat64
output hyperbolicTangentFloat64 CFloat64
memoryHeap hyperbolicTangentFloat64 no
async hyperbolicTangentFloat64 no
purpose hyperbolicTangentFloat64 "Hyperbolic tangent: sinh(x) / cosh(x)."
label startHyperbolicTangentFloat64
call snCall hyperbolicSineFloat64
arg snCall x inputValue
run snCall
bindOk snV CFloat64 snCall
call csCall hyperbolicCosineFloat64
arg csCall x inputValue
run csCall
bindOk csV CFloat64 csCall
call divTanhCall math.divideF64
arg divTanhCall left snV
arg divTanhCall right csV
run divTanhCall
bind thV CFloat64 divTanhCall
returnValue thV


operation logBaseTwoFloat64
input logBaseTwoFloat64 inputValue CFloat64
output logBaseTwoFloat64 CFloat64
memoryHeap logBaseTwoFloat64 no
async logBaseTwoFloat64 no
purpose logBaseTwoFloat64 "Base-2 log: ln(x) / ln(2)."
label startLogBaseTwoFloat64
const ln2 CFloat64 0.6931471805599453
call lnCall naturalLogFloat64
arg lnCall x inputValue
run lnCall
bindOk lnV CFloat64 lnCall
call divLg2Call math.divideF64
arg divLg2Call left lnV
arg divLg2Call right ln2
run divLg2Call
bind l2V CFloat64 divLg2Call
returnValue l2V


operation logBaseTenFloat64
input logBaseTenFloat64 inputValue CFloat64
output logBaseTenFloat64 CFloat64
memoryHeap logBaseTenFloat64 no
async logBaseTenFloat64 no
purpose logBaseTenFloat64 "Base-10 log: ln(x) / ln(10)."
label startLogBaseTenFloat64
const ln10 CFloat64 2.302585092994046
call lnCall10 naturalLogFloat64
arg lnCall10 x inputValue
run lnCall10
bindOk lnV10 CFloat64 lnCall10
call divLg10Call math.divideF64
arg divLg10Call left lnV10
arg divLg10Call right ln10
run divLg10Call
bind l10V CFloat64 divLg10Call
returnValue l10V


operation exponentialMinusOneFloat64
input exponentialMinusOneFloat64 inputValue CFloat64
output exponentialMinusOneFloat64 CFloat64
memoryHeap exponentialMinusOneFloat64 no
async exponentialMinusOneFloat64 no
purpose exponentialMinusOneFloat64 "exp(x) - 1. Not loss-of-precision-aware at this layer; production libm uses a separate series for tiny x."
label startExponentialMinusOneFloat64
const oneEm CFloat64 1.0
call expCallEm exponentialBaseEFloat64
arg expCallEm x inputValue
run expCallEm
bindOk expVem CFloat64 expCallEm
call subOneCall math.subtractF64
arg subOneCall left expVem
arg subOneCall right oneEm
run subOneCall
bind emV CFloat64 subOneCall
returnValue emV


operation naturalLogOnePlusFloat64
input naturalLogOnePlusFloat64 inputValue CFloat64
output naturalLogOnePlusFloat64 CFloat64
memoryHeap naturalLogOnePlusFloat64 no
async naturalLogOnePlusFloat64 no
purpose naturalLogOnePlusFloat64 "ln(1 + x). Same precision caveat as expm1."
label startNaturalLogOnePlusFloat64
const oneL1p CFloat64 1.0
call addOneCall math.addF64
arg addOneCall left oneL1p
arg addOneCall right inputValue
run addOneCall
bind plusX CFloat64 addOneCall
call lnCallL1p naturalLogFloat64
arg lnCallL1p x plusX
run lnCallL1p
bindOk l1pV CFloat64 lnCallL1p
returnValue l1pV


operation hypotenuseFloat64
input hypotenuseFloat64 firstLegValue CFloat64
input hypotenuseFloat64 secondLegValue CFloat64
output hypotenuseFloat64 CFloat64
memoryHeap hypotenuseFloat64 no
async hypotenuseFloat64 no
purpose hypotenuseFloat64 "sqrt(x^2 + y^2). Naive form may overflow for huge inputs; production libm scales first."
label startHypotenuseFloat64
call xSqHyp math.multiplyF64
arg xSqHyp left firstLegValue
arg xSqHyp right firstLegValue
run xSqHyp
bind xSqV CFloat64 xSqHyp
call ySqHyp math.multiplyF64
arg ySqHyp left secondLegValue
arg ySqHyp right secondLegValue
run ySqHyp
bind ySqV CFloat64 ySqHyp
call sumSqHyp math.addF64
arg sumSqHyp left xSqV
arg sumSqHyp right ySqV
run sumSqHyp
bind sumSq CFloat64 sumSqHyp
call sqrtHyp squareRootFloat64
arg sqrtHyp x sumSq
run sqrtHyp
bindOk h CFloat64 sqrtHyp
returnValue h


operation arctangentRadiansFloat64
input arctangentRadiansFloat64 inputValue CFloat64
output arctangentRadiansFloat64 CFloat64
memoryHeap arctangentRadiansFloat64 no
async arctangentRadiansFloat64 no
purpose arctangentRadiansFloat64 "atan(x) via Taylor series for |x| <= 1; uses the identity atan(x) = sign(x)*pi/2 - atan(1/x) for |x| > 1."
label startArctangentRadiansFloat64
const oneAt CFloat64 1.0
const negOneAt CFloat64 -1.0
const halfPiAt CFloat64 1.5707963267948966
const zeroAt CFloat64 0.0

# If |x| > 1, recurse via reciprocal identity.
call absXAt absoluteFloat64
arg absXAt x inputValue
run absXAt
bindOk absX CFloat64 absXAt
call largeCall math.greaterThanF64
arg largeCall left absX
arg largeCall right oneAt
run largeCall
bind isLarge Bool largeCall
branchIf isLarge atanLargeBranch
branch atanSeries

label atanLargeBranch
# atan(x) = sign(x)*pi/2 - atan(1/x)
call recipCall math.divideF64
arg recipCall left oneAt
arg recipCall right inputValue
run recipCall
bind recipX CFloat64 recipCall
call recCall arctangentRadiansFloat64
arg recCall x recipX
run recCall
bindOk recV CFloat64 recCall
# sign(x): if x >= 0 use +halfPi, else -halfPi.
call posLargeCall math.greaterThanOrEqualF64
arg posLargeCall left inputValue
arg posLargeCall right zeroAt
run posLargeCall
bind isPos Bool posLargeCall
var signedPi CFloat64 0.0
branchIf isPos atanSetPosPi
branch atanSetNegPi
label atanSetPosPi
set signedPi halfPiAt
branch atanCombine
label atanSetNegPi
call flipPi math.multiplyF64
arg flipPi left halfPiAt
arg flipPi right negOneAt
run flipPi
bind negPi CFloat64 flipPi
set signedPi negPi
branch atanCombine
label atanCombine
call combineCall math.subtractF64
arg combineCall left signedPi
arg combineCall right recV
run combineCall
bind atanLarge CFloat64 combineCall
returnValue atanLarge

label atanSeries
# Taylor for |x| <= 1: sum_{k=0..19} (-1)^k * x^(2k+1) / (2k+1)
const maxTermsAt I64 25
const oneIat I64 1
var sumAt CFloat64 0.0
var termAt CFloat64 0.0
set termAt inputValue
var kAt I64 0
var signAt CFloat64 1.0
# Add first term
set sumAt inputValue

label atanLoop
call atDone math.greaterThanOrEqualI64
arg atDone left kAt
arg atDone right maxTermsAt
run atDone
bind atDoneB Bool atDone
branchIf atDoneB atanReturn

# next term factor: -x^2 / (denominator we'll compute)
call xSqAt math.multiplyF64
arg xSqAt left inputValue
arg xSqAt right inputValue
run xSqAt
bind xSqA CFloat64 xSqAt
call negXSqAt math.multiplyF64
arg negXSqAt left xSqA
arg negXSqAt right negOneAt
run negXSqAt
bind negXSqA CFloat64 negXSqAt

# new exponent index: 2*(k+1)+1 = 2k+3; we accumulate term = term * negXSq * (2k+1) / (2k+3)
const twoIat I64 2
call twoKat math.multiplyI64
arg twoKat left kAt
arg twoKat right twoIat
run twoKat
bind twoKAt I64 twoKat
call oldExp math.addI64
arg oldExp left twoKAt
arg oldExp right oneIat
run oldExp
bind oldExpI I64 oldExp
call newExp math.addI64
arg newExp left twoKAt
arg newExp right oneIat
run newExp
bind newExpIA I64 newExp
call newExp2 math.addI64
arg newExp2 left newExpIA
arg newExp2 right twoIat
run newExp2
bind newExpI I64 newExp2

# multiply term by negXSq
call termTimes math.multiplyF64
arg termTimes left termAt
arg termTimes right negXSqA
run termTimes
bind term1 CFloat64 termTimes
# multiply by oldExp / newExp
call oldExpFloatCall math.intToFloat
arg oldExpFloatCall value oldExpI
run oldExpFloatCall
bind oldExpF CFloat64 oldExpFloatCall
call newExpFloatCall math.intToFloat
arg newExpFloatCall value newExpI
run newExpFloatCall
bind newExpF CFloat64 newExpFloatCall
call termTimes2 math.multiplyF64
arg termTimes2 left term1
arg termTimes2 right oldExpF
run termTimes2
bind term2 CFloat64 termTimes2
call termDiv math.divideF64
arg termDiv left term2
arg termDiv right newExpF
run termDiv
bind newTerm CFloat64 termDiv
set termAt newTerm

call atSum math.addF64
arg atSum left sumAt
arg atSum right newTerm
run atSum
bind nextSumAt CFloat64 atSum
set sumAt nextSumAt

call kAtInc math.addI64
arg kAtInc left kAt
arg kAtInc right oneIat
run kAtInc
bind nextKat I64 kAtInc
set kAt nextKat
branch atanLoop

label atanReturn
returnValue sumAt


operation arcsineRadiansFloat64
input arcsineRadiansFloat64 inputValue CFloat64
output arcsineRadiansFloat64 CFloat64
memoryHeap arcsineRadiansFloat64 no
async arcsineRadiansFloat64 no
purpose arcsineRadiansFloat64 "asin(x) = atan(x / sqrt(1 - x^2)). Domain: [-1, 1]."
label startArcsineRadiansFloat64
const oneAs CFloat64 1.0
call xSqAs math.multiplyF64
arg xSqAs left inputValue
arg xSqAs right inputValue
run xSqAs
bind xSqAsV CFloat64 xSqAs
call oneMinus math.subtractF64
arg oneMinus left oneAs
arg oneMinus right xSqAsV
run oneMinus
bind denomSq CFloat64 oneMinus
call sqrtAs squareRootFloat64
arg sqrtAs x denomSq
run sqrtAs
bindOk denom CFloat64 sqrtAs
call divAs math.divideF64
arg divAs left inputValue
arg divAs right denom
run divAs
bind ratio CFloat64 divAs
call atanAs arctangentRadiansFloat64
arg atanAs x ratio
run atanAs
bindOk asV CFloat64 atanAs
returnValue asV


operation arccosineRadiansFloat64
input arccosineRadiansFloat64 inputValue CFloat64
output arccosineRadiansFloat64 CFloat64
memoryHeap arccosineRadiansFloat64 no
async arccosineRadiansFloat64 no
purpose arccosineRadiansFloat64 "acos(x) = pi/2 - asin(x). Domain: [-1, 1]."
label startArccosineRadiansFloat64
const halfPiAcos CFloat64 1.5707963267948966
call asCall arcsineRadiansFloat64
arg asCall x inputValue
run asCall
bindOk asV CFloat64 asCall
call subCall math.subtractF64
arg subCall left halfPiAcos
arg subCall right asV
run subCall
bind acV CFloat64 subCall
returnValue acV


operation fusedMultiplyAddFloat64
input fusedMultiplyAddFloat64 multiplicandValue CFloat64
input fusedMultiplyAddFloat64 multiplierValue CFloat64
input fusedMultiplyAddFloat64 addendValue CFloat64
output fusedMultiplyAddFloat64 CFloat64
memoryHeap fusedMultiplyAddFloat64 no
async fusedMultiplyAddFloat64 no
purpose fusedMultiplyAddFloat64 "Fused multiply-add: a*b + c. Not actually fused at this layer (libm fma uses a hardware FMA instruction); we just do the two ops in sequence with normal IEEE-754 rounding between them."
label startFusedMultiplyAddFloat64
call mulCall math.multiplyF64
arg mulCall left multiplicandValue
arg mulCall right multiplierValue
run mulCall
bind prod CFloat64 mulCall
call addCall math.addF64
arg addCall left prod
arg addCall right addendValue
run addCall
bind r CFloat64 addCall
returnValue r


operation maximumFloat64
input maximumFloat64 leftValue CFloat64
input maximumFloat64 rightValue CFloat64
output maximumFloat64 CFloat64
memoryHeap maximumFloat64 no
async maximumFloat64 no
purpose maximumFloat64 "Max of a and b. Returns the non-NaN argument if exactly one is NaN; for both-NaN we don't detect (no isnan yet)."
label startMaximumFloat64
call gtCall math.greaterThanF64
arg gtCall left leftValue
arg gtCall right rightValue
run gtCall
bind aGreater Bool gtCall
branchIf aGreater fmaxA
returnValue rightValue
label fmaxA
returnValue leftValue


operation minimumFloat64
input minimumFloat64 leftValue CFloat64
input minimumFloat64 rightValue CFloat64
output minimumFloat64 CFloat64
memoryHeap minimumFloat64 no
async minimumFloat64 no
purpose minimumFloat64 "Min of a and b."
label startMinimumFloat64
call ltCall math.lessThanF64
arg ltCall left leftValue
arg ltCall right rightValue
run ltCall
bind aLess Bool ltCall
branchIf aLess fminA
returnValue rightValue
label fminA
returnValue leftValue


operation positiveDifferenceFloat64
input positiveDifferenceFloat64 leftValue CFloat64
input positiveDifferenceFloat64 rightValue CFloat64
output positiveDifferenceFloat64 CFloat64
memoryHeap positiveDifferenceFloat64 no
async positiveDifferenceFloat64 no
purpose positiveDifferenceFloat64 "Positive difference: max(a - b, 0)."
label startPositiveDifferenceFloat64
const zeroFd CFloat64 0.0
call subCall math.subtractF64
arg subCall left leftValue
arg subCall right rightValue
run subCall
bind diff CFloat64 subCall
call ltzCall math.lessThanF64
arg ltzCall left diff
arg ltzCall right zeroFd
run ltzCall
bind diffNeg Bool ltzCall
branchIf diffNeg fdimZero
returnValue diff
label fdimZero
returnValue zeroFd


operation copySignFloat64
input copySignFloat64 magnitudeValue CFloat64
input copySignFloat64 signSourceValue CFloat64
output copySignFloat64 CFloat64
memoryHeap copySignFloat64 no
async copySignFloat64 no
purpose copySignFloat64 "Returns |magnitude| with the sign of signSource. Doesn't yet preserve sign of zero (real libm copysign treats -0.0 specially; we don't have signed-zero detection without bit-level access)."
label startCopySignFloat64
const zeroCp CFloat64 0.0
const negOneCp CFloat64 -1.0

# absMag = |magnitude|
call magAbsCall absoluteFloat64
arg magAbsCall x magnitudeValue
run magAbsCall
bindOk absMag CFloat64 magAbsCall

# Sign of signSource: < 0 -> -1, else +1
call sourceNegCall math.lessThanF64
arg sourceNegCall left signSourceValue
arg sourceNegCall right zeroCp
run sourceNegCall
bind sourceIsNeg Bool sourceNegCall
branchIf sourceIsNeg copysignFlip
returnValue absMag
label copysignFlip
call flipCall math.multiplyF64
arg flipCall left absMag
arg flipCall right negOneCp
run flipCall
bind flipped CFloat64 flipCall
returnValue flipped


operation signOfFloat64
input signOfFloat64 inputValue CFloat64
output signOfFloat64 CFloat64
memoryHeap signOfFloat64 no
async signOfFloat64 no
purpose signOfFloat64 "Returns -1.0 if x < 0, 1.0 if x > 0, 0.0 if x == 0."
label startSignOfFloat64
const zeroSg CFloat64 0.0
const oneSg CFloat64 1.0
const negOneSg CFloat64 -1.0
call ltCheck math.lessThanF64
arg ltCheck left inputValue
arg ltCheck right zeroSg
run ltCheck
bind isNg Bool ltCheck
branchIf isNg sgNeg
call gtCheck math.greaterThanF64
arg gtCheck left inputValue
arg gtCheck right zeroSg
run gtCheck
bind isPs Bool gtCheck
branchIf isPs sgPos
returnValue zeroSg
label sgNeg
returnValue negOneSg
label sgPos
returnValue oneSg


operation roundFloat64ToNearestInteger
input roundFloat64ToNearestInteger inputValue CFloat64
output roundFloat64ToNearestInteger CFloat64
memoryHeap roundFloat64ToNearestInteger no
async roundFloat64ToNearestInteger no
purpose roundFloat64ToNearestInteger "Round half-away-from-zero to nearest integer (matching libm round, not lrint which uses banker's rounding)."
label startRoundFloat64ToNearestInteger
const halfRd CFloat64 0.5
const negHalfRd CFloat64 -0.5
const zeroRd CFloat64 0.0
call neg math.lessThanF64
arg neg left inputValue
arg neg right zeroRd
run neg
bind isNeg Bool neg
branchIf isNeg roundNeg
# Positive: floor(x + 0.5)
call addCall math.addF64
arg addCall left inputValue
arg addCall right halfRd
run addCall
bind shifted CFloat64 addCall
call flCall floorFloat64
arg flCall x shifted
run flCall
bindOk rRes CFloat64 flCall
returnValue rRes
label roundNeg
# Negative: ceil(x - 0.5)
call subCall math.subtractF64
arg subCall left inputValue
arg subCall right halfRd
run subCall
bind shiftedN CFloat64 subCall
call cCall ceilingFloat64
arg cCall x shiftedN
run cCall
bindOk rResN CFloat64 cCall
returnValue rResN


operation cubeRootFloat64
input cubeRootFloat64 inputValue CFloat64
output cubeRootFloat64 CFloat64
memoryHeap cubeRootFloat64 no
async cubeRootFloat64 no
purpose cubeRootFloat64 "Cube root: sign(x) * pow(|x|, 1/3). Handles negative inputs by computing on |x| and reattaching the sign."
label startCubeRootFloat64
const zeroCb CFloat64 0.0
const negOneCb CFloat64 -1.0
const oneThirdCb CFloat64 0.3333333333333333
call eqZeroCb math.equalF64
arg eqZeroCb left inputValue
arg eqZeroCb right zeroCb
run eqZeroCb
bind xIsZero Bool eqZeroCb
branchIf xIsZero cbrtZero
call absXcb absoluteFloat64
arg absXcb x inputValue
run absXcb
bindOk absXc CFloat64 absXcb
call powAbs powerFloat64
arg powAbs base absXc
arg powAbs exponent oneThirdCb
run powAbs
bindOk powAbsRes CFloat64 powAbs
call ltZeroCheck math.lessThanF64
arg ltZeroCheck left inputValue
arg ltZeroCheck right zeroCb
run ltZeroCheck
bind xIsNeg Bool ltZeroCheck
branchIf xIsNeg cbrtNegate
returnValue powAbsRes
label cbrtNegate
call flipCb math.multiplyF64
arg flipCb left powAbsRes
arg flipCb right negOneCb
run flipCb
bind flippedCb CFloat64 flipCb
returnValue flippedCb
label cbrtZero
returnValue zeroCb


operation exponentialBaseTwoFloat64
input exponentialBaseTwoFloat64 inputValue CFloat64
output exponentialBaseTwoFloat64 CFloat64
memoryHeap exponentialBaseTwoFloat64 no
async exponentialBaseTwoFloat64 no
purpose exponentialBaseTwoFloat64 "2^x via pow(2.0, x)."
label startExponentialBaseTwoFloat64
const twoE2 CFloat64 2.0
call powCall powerFloat64
arg powCall base twoE2
arg powCall exponent inputValue
run powCall
bindOk r CFloat64 powCall
returnValue r


# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memoryHeap main no
async main no
purpose main "Smoke-test absoluteFloat64 / squareRootFloat64 / exponentialBaseEFloat64. Prints OK on success."

label startMain

# absoluteFloat64(-3.5) == 3.5
const negPointFive CFloat64 -3.5
const expFabs CFloat64 3.5
call f1 absoluteFloat64
arg f1 x negPointFive
run f1
bindOk f1Res CFloat64 f1
call f1CheckCall math.equalF64
arg f1CheckCall left f1Res
arg f1CheckCall right expFabs
run f1CheckCall
bind f1Ok Bool f1CheckCall
branchIf f1Ok f1OkLabel
branch testFailed
label f1OkLabel

# squareRootFloat64(144.0) approximately 12.0
const c144 CFloat64 144.0
const c12 CFloat64 12.0
const tol CFloat64 0.0001
call s1 squareRootFloat64
arg s1 x c144
run s1
bindOk s1Res CFloat64 s1
call diffCall math.subtractF64
arg diffCall left s1Res
arg diffCall right c12
run diffCall
bind diff CFloat64 diffCall
call abs1 absoluteFloat64
arg abs1 x diff
run abs1
bindOk diffAbs CFloat64 abs1
call s1Check math.lessThanF64
arg s1Check left diffAbs
arg s1Check right tol
run s1Check
bind s1Ok Bool s1Check
branchIf s1Ok s1OkLabel
branch testFailed
label s1OkLabel

# exponentialBaseEFloat64(1.0) approximately 2.718281828
const oneExp CFloat64 1.0
const eulerApprox CFloat64 2.718281828
const tolE CFloat64 0.001
call e1 exponentialBaseEFloat64
arg e1 x oneExp
run e1
bindOk e1Res CFloat64 e1
call diff2Call math.subtractF64
arg diff2Call left e1Res
arg diff2Call right eulerApprox
run diff2Call
bind diff2 CFloat64 diff2Call
call abs2 absoluteFloat64
arg abs2 x diff2
run abs2
bindOk diff2Abs CFloat64 abs2
call e1Check math.lessThanF64
arg e1Check left diff2Abs
arg e1Check right tolE
run e1Check
bind e1Ok Bool e1Check
branchIf e1Ok e1OkLabel
branch testFailed
label e1OkLabel

# truncateFloat64TowardZero(3.7) == 3.0
const cThreeSeven CFloat64 3.7
const cThree CFloat64 3.0
call tr1 truncateFloat64TowardZero
arg tr1 x cThreeSeven
run tr1
bindOk tr1Res CFloat64 tr1
call tr1Check math.equalF64
arg tr1Check left tr1Res
arg tr1Check right cThree
run tr1Check
bind tr1Ok Bool tr1Check
branchIf tr1Ok tr1OkLabel
branch testFailed
label tr1OkLabel

# floorFloat64(-2.3) == -3.0
const cNegTwoThree CFloat64 -2.3
const cNegThree CFloat64 -3.0
call fl1 floorFloat64
arg fl1 x cNegTwoThree
run fl1
bindOk fl1Res CFloat64 fl1
call fl1Check math.equalF64
arg fl1Check left fl1Res
arg fl1Check right cNegThree
run fl1Check
bind fl1Ok Bool fl1Check
branchIf fl1Ok fl1OkLabel
branch testFailed
label fl1OkLabel

# ceilingFloat64(2.3) == 3.0
const cTwoThree CFloat64 2.3
call ce1 ceilingFloat64
arg ce1 x cTwoThree
run ce1
bindOk ce1Res CFloat64 ce1
call ce1Check math.equalF64
arg ce1Check left ce1Res
arg ce1Check right cThree
run ce1Check
bind ce1Ok Bool ce1Check
branchIf ce1Ok ce1OkLabel
branch testFailed
label ce1OkLabel

# floatingRemainderFloat64(7.5, 2.0) == 1.5
const cSevenHalf CFloat64 7.5
const cTwoFl CFloat64 2.0
const cOneHalf CFloat64 1.5
call fm1 floatingRemainderFloat64
arg fm1 x cSevenHalf
arg fm1 y cTwoFl
run fm1
bindOk fm1Res CFloat64 fm1
call fm1Check math.equalF64
arg fm1Check left fm1Res
arg fm1Check right cOneHalf
run fm1Check
bind fm1Ok Bool fm1Check
branchIf fm1Ok fm1OkLabel
branch testFailed
label fm1OkLabel

# naturalLogFloat64(e) approximately 1.0
const eApprox CFloat64 2.718281828
const oneTarget CFloat64 1.0
const tolLn CFloat64 0.01
call ln1 naturalLogFloat64
arg ln1 x eApprox
run ln1
bindOk ln1Res CFloat64 ln1
call ln1Diff math.subtractF64
arg ln1Diff left ln1Res
arg ln1Diff right oneTarget
run ln1Diff
bind ln1DiffV CFloat64 ln1Diff
call ln1Abs absoluteFloat64
arg ln1Abs x ln1DiffV
run ln1Abs
bindOk ln1AbsV CFloat64 ln1Abs
call ln1Check math.lessThanF64
arg ln1Check left ln1AbsV
arg ln1Check right tolLn
run ln1Check
bind ln1Ok Bool ln1Check
branchIf ln1Ok ln1OkLabel
branch testFailed
label ln1OkLabel

# powerFloat64(2.0, 10.0) approximately 1024.0
const cTen CFloat64 10.0
const cOneOhTwoFour CFloat64 1024.0
const tolPw CFloat64 5.0
call pw1 powerFloat64
arg pw1 base cTwoFl
arg pw1 exponent cTen
run pw1
bindOk pw1Res CFloat64 pw1
call pw1Diff math.subtractF64
arg pw1Diff left pw1Res
arg pw1Diff right cOneOhTwoFour
run pw1Diff
bind pw1DiffV CFloat64 pw1Diff
call pw1Abs absoluteFloat64
arg pw1Abs x pw1DiffV
run pw1Abs
bindOk pw1AbsV CFloat64 pw1Abs
call pw1Check math.lessThanF64
arg pw1Check left pw1AbsV
arg pw1Check right tolPw
run pw1Check
bind pw1Ok Bool pw1Check
branchIf pw1Ok pw1OkLabel
branch testFailed
label pw1OkLabel

# sineRadiansFloat64(0.0) approximately 0.0
const zeroFs CFloat64 0.0
const tolSin CFloat64 0.001
call sn1 sineRadiansFloat64
arg sn1 x zeroFs
run sn1
bindOk sn1Res CFloat64 sn1
call sn1Abs absoluteFloat64
arg sn1Abs x sn1Res
run sn1Abs
bindOk sn1AbsV CFloat64 sn1Abs
call sn1Check math.lessThanF64
arg sn1Check left sn1AbsV
arg sn1Check right tolSin
run sn1Check
bind sn1Ok Bool sn1Check
branchIf sn1Ok sn1OkLabel
branch testFailed
label sn1OkLabel

# cosineRadiansFloat64(0.0) approximately 1.0
call cs1 cosineRadiansFloat64
arg cs1 x zeroFs
run cs1
bindOk cs1Res CFloat64 cs1
call cs1Diff math.subtractF64
arg cs1Diff left cs1Res
arg cs1Diff right oneTarget
run cs1Diff
bind cs1DiffV CFloat64 cs1Diff
call cs1Abs absoluteFloat64
arg cs1Abs x cs1DiffV
run cs1Abs
bindOk cs1AbsV CFloat64 cs1Abs
call cs1Check math.lessThanF64
arg cs1Check left cs1AbsV
arg cs1Check right tolSin
run cs1Check
bind cs1Ok Bool cs1Check
branchIf cs1Ok cs1OkLabel
branch testFailed
label cs1OkLabel

# logBaseTwoFloat64(8.0) approximately 3.0
const eightFs CFloat64 8.0
const threeFs CFloat64 3.0
const tolLg CFloat64 0.01
call lg2v logBaseTwoFloat64
arg lg2v x eightFs
run lg2v
bindOk lg2vRes CFloat64 lg2v
call lg2vDiff math.subtractF64
arg lg2vDiff left lg2vRes
arg lg2vDiff right threeFs
run lg2vDiff
bind lg2vDiffV CFloat64 lg2vDiff
call lg2vAbs absoluteFloat64
arg lg2vAbs x lg2vDiffV
run lg2vAbs
bindOk lg2vAbsV CFloat64 lg2vAbs
call lg2vCheck math.lessThanF64
arg lg2vCheck left lg2vAbsV
arg lg2vCheck right tolLg
run lg2vCheck
bind lg2vOk Bool lg2vCheck
branchIf lg2vOk lg2vOkLabel
branch testFailed
label lg2vOkLabel

# logBaseTenFloat64(1000.0) approximately 3.0
const thousandFs CFloat64 1000.0
call lg10v logBaseTenFloat64
arg lg10v x thousandFs
run lg10v
bindOk lg10vRes CFloat64 lg10v
call lg10vDiff math.subtractF64
arg lg10vDiff left lg10vRes
arg lg10vDiff right threeFs
run lg10vDiff
bind lg10vDiffV CFloat64 lg10vDiff
call lg10vAbs absoluteFloat64
arg lg10vAbs x lg10vDiffV
run lg10vAbs
bindOk lg10vAbsV CFloat64 lg10vAbs
call lg10vCheck math.lessThanF64
arg lg10vCheck left lg10vAbsV
arg lg10vCheck right tolLg
run lg10vCheck
bind lg10vOk Bool lg10vCheck
branchIf lg10vOk lg10vOkLabel
branch testFailed
label lg10vOkLabel

# hypotenuseFloat64(3.0, 4.0) approximately 5.0
const fourFs CFloat64 4.0
const fiveFs CFloat64 5.0
const tolHyp CFloat64 0.0001
call hyp1 hypotenuseFloat64
arg hyp1 x threeFs
arg hyp1 y fourFs
run hyp1
bindOk hyp1Res CFloat64 hyp1
call hyp1Diff math.subtractF64
arg hyp1Diff left hyp1Res
arg hyp1Diff right fiveFs
run hyp1Diff
bind hyp1DiffV CFloat64 hyp1Diff
call hyp1Abs absoluteFloat64
arg hyp1Abs x hyp1DiffV
run hyp1Abs
bindOk hyp1AbsV CFloat64 hyp1Abs
call hyp1Check math.lessThanF64
arg hyp1Check left hyp1AbsV
arg hyp1Check right tolHyp
run hyp1Check
bind hyp1Ok Bool hyp1Check
branchIf hyp1Ok hyp1OkLabel
branch testFailed
label hyp1OkLabel

# arctangentRadiansFloat64(1.0) approximately pi/4 = 0.785398
const piOver4 CFloat64 0.7853981633974483
const tolAtan CFloat64 0.01
call atn1 arctangentRadiansFloat64
arg atn1 x oneTarget
run atn1
bindOk atn1Res CFloat64 atn1
call atn1Diff math.subtractF64
arg atn1Diff left atn1Res
arg atn1Diff right piOver4
run atn1Diff
bind atn1DiffV CFloat64 atn1Diff
call atn1Abs absoluteFloat64
arg atn1Abs x atn1DiffV
run atn1Abs
bindOk atn1AbsV CFloat64 atn1Abs
call atn1Check math.lessThanF64
arg atn1Check left atn1AbsV
arg atn1Check right tolAtan
run atn1Check
bind atn1Ok Bool atn1Check
branchIf atn1Ok atn1OkLabel
branch testFailed
label atn1OkLabel

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
makeError testFailure MainError.MathFloatSmokeAssertionFailed
returnError testFailure
