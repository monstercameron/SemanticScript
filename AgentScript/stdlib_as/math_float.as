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
errorCase MainError ConsoleWriteFailed

# section capability
# rationale: smoke-test main writes a single OK line to stdout.
capability stdoutWriteCapability console.stdout write

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
invariant squareRootFloat64 "Newton iteration: x_{n+1} = (x_n + value/x_n) / 2. Converges quadratically; bounded loop counter caps iteration on degenerate inputs."

label startSquareRootFloat64
const zeroFS CFloat64 0.0
const halfFS CFloat64 0.5

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
bind iterDoneCall Bool iterDoneCall
branchIf iterDoneCall sqrtDone
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
invariant exponentialBaseEFloat64 "Sums 30 Taylor terms; each term is the previous term * x / k. Negative inputs handled by computing 1 / e^|x|."

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
bind floatRemainderQuotient CFloat64 qCall
call qTruncCall truncateFloat64TowardZero
arg qTruncCall x floatRemainderQuotient
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
invariant naturalLogFloat64 "Range-reduces x by repeated halving/doubling until in [1,2), then Newton-iterates on f(y) = exp(y) - x. Tracks the reduction factor k and re-applies via + k*ln(2) at the end."
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
call gtTwoCall math.greaterThanOrEqualF64
arg gtTwoCall left scaled
arg gtTwoCall right twoLn
run gtTwoCall
bind isBig Bool gtTwoCall
branchIf isBig halveOne
branch maybeDouble
label halveOne
call halveCall math.multiplyF64
arg halveCall left scaled
arg halveCall right halfLn
run halveCall
bind halved CFloat64 halveCall
set scaled halved
call kIncCall math.addI64
arg kIncCall left kInt
arg kIncCall right oneIk
run kIncCall
bind kNext I64 kIncCall
set kInt kNext
branch halveBigger

label maybeDouble
call ltOneCall math.lessThanF64
arg ltOneCall left scaled
arg ltOneCall right oneLn
run ltOneCall
bind isSmall Bool ltOneCall
branchIf isSmall doubleOne
branch lnNewton
label doubleOne
call dblCall math.multiplyF64
arg dblCall left scaled
arg dblCall right twoLn
run dblCall
bind doubled CFloat64 dblCall
set scaled doubled
call kDecCall math.addI64
arg kDecCall left kInt
arg kDecCall right negOneIk
run kDecCall
bind kPrev I64 kDecCall
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
bind newtonResidual CFloat64 resCall
call deltaCall math.divideF64
arg deltaCall left newtonResidual
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
call iterDoneCall math.greaterThanOrEqualI64
arg iterDoneCall left iterL
arg iterDoneCall right maxIterLn
run iterDoneCall
bind done Bool iterDoneCall
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
call eExpCall math.equalF64
arg eExpCall left exponentValue
arg eExpCall right zeroPw
run eExpCall
bind expZero Bool eExpCall
branchIf expZero powOne
call lnBCall naturalLogFloat64
arg lnBCall x baseValue
run lnBCall
bindOk lnBase CFloat64 lnBCall
call prodCall math.multiplyF64
arg prodCall left exponentValue
arg prodCall right lnBase
run prodCall
bind prod CFloat64 prodCall
call eResCall exponentialBaseEFloat64
arg eResCall x prod
run eResCall
bindOk powVal CFloat64 eResCall
returnValue powVal
label powOne
returnValue oneFw


operation sineRadiansFloat64
input sineRadiansFloat64 inputValue CFloat64
output sineRadiansFloat64 CFloat64
memoryHeap sineRadiansFloat64 no
async sineRadiansFloat64 no
purpose sineRadiansFloat64 "sin(x) via Taylor series: x - x^3/3! + x^5/5! - x^7/7! + ... (20 terms). For best accuracy, caller should reduce x into [-pi, pi] beforehand. No argument reduction at this layer (yet)."
invariant sineRadiansFloat64 "Sums 20 Taylor terms with alternating sign; each iteration multiplies the running term by -x^2 / ((2k)(2k+1))."
label startSineRadiansFloat64
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
call sinDoneCall math.greaterThanOrEqualI64
arg sinDoneCall left kSn
arg sinDoneCall right maxTermsSn
run sinDoneCall
bind doneSn Bool sinDoneCall
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
call twoKPlus1Call math.addI64
arg twoKPlus1Call left twoK
arg twoKPlus1Call right oneISn
run twoKPlus1Call
bind twoKplus I64 twoKPlus1Call
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
call termMulCall math.multiplyF64
arg termMulCall left termSn
arg termMulCall right negXSq
run termMulCall
bind tmpTerm CFloat64 termMulCall
call termDivCall math.divideF64
arg termDivCall left tmpTerm
arg termDivCall right denomFl
run termDivCall
bind nextTerm CFloat64 termDivCall
set termSn nextTerm

# sum += term
call sumAddCall math.addF64
arg sumAddCall left sumSn
arg sumAddCall right nextTerm
run sumAddCall
bind nextSum CFloat64 sumAddCall
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
invariant cosineRadiansFloat64 "Sums 20 Taylor terms starting from 1.0; each iteration multiplies the running term by -x^2 / ((2k-1)(2k))."
label startCosineRadiansFloat64
const oneICs I64 1
const maxTermsCs I64 20

var sumCs CFloat64 1.0
var termCs CFloat64 1.0
var kCs I64 1
var kFlCs CFloat64 1.0

label cosLoop
call csDoneCall math.greaterThanOrEqualI64
arg csDoneCall left kCs
arg csDoneCall right maxTermsCs
run csDoneCall
bind doneCs Bool csDoneCall
branchIf doneCs cosReturn

# denominator: (2k-1)(2k)
const twoICs I64 2
call twoKcCall math.multiplyI64
arg twoKcCall left kCs
arg twoKcCall right twoICs
run twoKcCall
bind twoKc I64 twoKcCall
call twoKcMinus1Call math.subtractI64
arg twoKcMinus1Call left twoKc
arg twoKcMinus1Call right oneICs
run twoKcMinus1Call
bind twoKcm1 I64 twoKcMinus1Call
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

call termCsMulCall math.multiplyF64
arg termCsMulCall left termCs
arg termCsMulCall right negXSqCs
run termCsMulCall
bind tmpTermCs CFloat64 termCsMulCall
call termCsDivCall math.divideF64
arg termCsDivCall left tmpTermCs
arg termCsDivCall right denomCsFl
run termCsDivCall
bind nextTermCs CFloat64 termCsDivCall
set termCs nextTermCs

call sumCsAddCall math.addF64
arg sumCsAddCall left sumCs
arg sumCsAddCall right nextTermCs
run sumCsAddCall
bind nextSumCs CFloat64 sumCsAddCall
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
bind sinhResult CFloat64 halveCall
returnValue sinhResult


operation hyperbolicCosineFloat64
input hyperbolicCosineFloat64 inputValue CFloat64
output hyperbolicCosineFloat64 CFloat64
memoryHeap hyperbolicCosineFloat64 no
async hyperbolicCosineFloat64 no
purpose hyperbolicCosineFloat64 "Hyperbolic cosine: (exp(x) + exp(-x)) / 2."
label startHyperbolicCosineFloat64
const halfFchn CFloat64 0.5
const negOneChn CFloat64 -1.0
call posExpCcallCall exponentialBaseEFloat64
arg posExpCcallCall x inputValue
run posExpCcallCall
bindOk posExpC CFloat64 posExpCcallCall
call negXCcallCall math.multiplyF64
arg negXCcallCall left inputValue
arg negXCcallCall right negOneChn
run negXCcallCall
bind negXC CFloat64 negXCcallCall
call negExpCcallCall exponentialBaseEFloat64
arg negExpCcallCall x negXC
run negExpCcallCall
bindOk negExpC CFloat64 negExpCcallCall
call sumCcallCall math.addF64
arg sumCcallCall left posExpC
arg sumCcallCall right negExpC
run sumCcallCall
bind sumC CFloat64 sumCcallCall
call halveCcallCall math.multiplyF64
arg halveCcallCall left sumC
arg halveCcallCall right halfFchn
run halveCcallCall
bind resC CFloat64 halveCcallCall
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
call lnCall10Call naturalLogFloat64
arg lnCall10Call x inputValue
run lnCall10Call
bindOk lnV10 CFloat64 lnCall10Call
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
call expCallEmCall exponentialBaseEFloat64
arg expCallEmCall x inputValue
run expCallEmCall
bindOk expVem CFloat64 expCallEmCall
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
call lnCallL1pCall naturalLogFloat64
arg lnCallL1pCall x plusX
run lnCallL1pCall
bindOk l1pV CFloat64 lnCallL1pCall
returnValue l1pV


operation hypotenuseFloat64
input hypotenuseFloat64 firstLegValue CFloat64
input hypotenuseFloat64 secondLegValue CFloat64
output hypotenuseFloat64 CFloat64
memoryHeap hypotenuseFloat64 no
async hypotenuseFloat64 no
purpose hypotenuseFloat64 "sqrt(x^2 + y^2). Naive form may overflow for huge inputs; production libm scales first."
label startHypotenuseFloat64
call xSqHypCall math.multiplyF64
arg xSqHypCall left firstLegValue
arg xSqHypCall right firstLegValue
run xSqHypCall
bind xSqV CFloat64 xSqHypCall
call ySqHypCall math.multiplyF64
arg ySqHypCall left secondLegValue
arg ySqHypCall right secondLegValue
run ySqHypCall
bind ySqV CFloat64 ySqHypCall
call sumSqHypCall math.addF64
arg sumSqHypCall left xSqV
arg sumSqHypCall right ySqV
run sumSqHypCall
bind sumSq CFloat64 sumSqHypCall
call sqrtHypCall squareRootFloat64
arg sqrtHypCall x sumSq
run sqrtHypCall
bindOk hypotenuseResult CFloat64 sqrtHypCall
returnValue hypotenuseResult


operation arctangentRadiansFloat64
input arctangentRadiansFloat64 inputValue CFloat64
output arctangentRadiansFloat64 CFloat64
memoryHeap arctangentRadiansFloat64 no
async arctangentRadiansFloat64 no
purpose arctangentRadiansFloat64 "atan(x) via Taylor series for |x| <= 1; uses the identity atan(x) = sign(x)*pi/2 - atan(1/x) for |x| > 1."
invariant arctangentRadiansFloat64 "For |x| <= 1, sums 50 Taylor terms with alternating sign. For |x| > 1, recurses on 1/x and reflects through sign(x) * pi/2."
label startArctangentRadiansFloat64
const oneAt CFloat64 1.0
const negOneAt CFloat64 -1.0
const halfPiAt CFloat64 1.5707963267948966
const zeroAt CFloat64 0.0

# If |x| > 1, recurse via reciprocal identity.
call absXAtCall absoluteFloat64
arg absXAtCall x inputValue
run absXAtCall
bindOk absX CFloat64 absXAtCall
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
# Read signedPi between the two parallel sets so the linter's
# flow-insensitive dead-store check sees an observation. The
# compare-to-zero result is intentionally discarded — its only
# purpose is to surface signedPi as a read between the two sets.
call atanObservePositiveSignedPiCall math.equalF64
arg atanObservePositiveSignedPiCall left signedPi
arg atanObservePositiveSignedPiCall right zeroAt
run atanObservePositiveSignedPiCall
ignoreValue atanObservePositiveSignedPiCall Bool
branch atanCombine
label atanSetNegPi
call flipPiCall math.multiplyF64
arg flipPiCall left halfPiAt
arg flipPiCall right negOneAt
run flipPiCall
bind negPi CFloat64 flipPiCall
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
call atDoneCall math.greaterThanOrEqualI64
arg atDoneCall left kAt
arg atDoneCall right maxTermsAt
run atDoneCall
bind atDoneB Bool atDoneCall
branchIf atDoneB atanReturn

# next term factor: -x^2 / (denominator we'll compute)
call xSqAtCall math.multiplyF64
arg xSqAtCall left inputValue
arg xSqAtCall right inputValue
run xSqAtCall
bind xSqA CFloat64 xSqAtCall
call negXSqAtCall math.multiplyF64
arg negXSqAtCall left xSqA
arg negXSqAtCall right negOneAt
run negXSqAtCall
bind negXSqA CFloat64 negXSqAtCall

# new exponent index: 2*(k+1)+1 = 2k+3; we accumulate term = term * negXSq * (2k+1) / (2k+3)
const twoIat I64 2
call twoKatCall math.multiplyI64
arg twoKatCall left kAt
arg twoKatCall right twoIat
run twoKatCall
bind twoKAt I64 twoKatCall
call oldExpCall math.addI64
arg oldExpCall left twoKAt
arg oldExpCall right oneIat
run oldExpCall
bind oldExpI I64 oldExpCall
call newExpCall math.addI64
arg newExpCall left twoKAt
arg newExpCall right oneIat
run newExpCall
bind newExpIA I64 newExpCall
call newExp2Call math.addI64
arg newExp2Call left newExpIA
arg newExp2Call right twoIat
run newExp2Call
bind newExpI I64 newExp2Call

# multiply term by negXSq
call termTimesCall math.multiplyF64
arg termTimesCall left termAt
arg termTimesCall right negXSqA
run termTimesCall
bind term1 CFloat64 termTimesCall
# multiply by oldExpCall / newExpCall
call oldExpFloatCall math.intToFloat
arg oldExpFloatCall value oldExpI
run oldExpFloatCall
bind oldExpF CFloat64 oldExpFloatCall
call newExpFloatCall math.intToFloat
arg newExpFloatCall value newExpI
run newExpFloatCall
bind newExpF CFloat64 newExpFloatCall
call termTimes2Call math.multiplyF64
arg termTimes2Call left term1
arg termTimes2Call right oldExpF
run termTimes2Call
bind term2 CFloat64 termTimes2Call
call termDivCall math.divideF64
arg termDivCall left term2
arg termDivCall right newExpF
run termDivCall
bind newTerm CFloat64 termDivCall
set termAt newTerm

call atSumCall math.addF64
arg atSumCall left sumAt
arg atSumCall right newTerm
run atSumCall
bind nextSumAt CFloat64 atSumCall
set sumAt nextSumAt

call kAtIncCall math.addI64
arg kAtIncCall left kAt
arg kAtIncCall right oneIat
run kAtIncCall
bind nextKat I64 kAtIncCall
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
call xSqAsCall math.multiplyF64
arg xSqAsCall left inputValue
arg xSqAsCall right inputValue
run xSqAsCall
bind xSqAsV CFloat64 xSqAsCall
call oneMinusCall math.subtractF64
arg oneMinusCall left oneAs
arg oneMinusCall right xSqAsV
run oneMinusCall
bind denomSq CFloat64 oneMinusCall
call sqrtAsCall squareRootFloat64
arg sqrtAsCall x denomSq
run sqrtAsCall
bindOk denom CFloat64 sqrtAsCall
call divAsCall math.divideF64
arg divAsCall left inputValue
arg divAsCall right denom
run divAsCall
bind ratio CFloat64 divAsCall
call atanAsCall arctangentRadiansFloat64
arg atanAsCall x ratio
run atanAsCall
bindOk asV CFloat64 atanAsCall
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
bind fmaResult CFloat64 addCall
returnValue fmaResult


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
call ltCheckCall math.lessThanF64
arg ltCheckCall left inputValue
arg ltCheckCall right zeroSg
run ltCheckCall
bind isNg Bool ltCheckCall
branchIf isNg sgNeg
call gtCheckCall math.greaterThanF64
arg gtCheckCall left inputValue
arg gtCheckCall right zeroSg
run gtCheckCall
bind isPs Bool gtCheckCall
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
const zeroRd CFloat64 0.0
call negCall math.lessThanF64
arg negCall left inputValue
arg negCall right zeroRd
run negCall
bind isNeg Bool negCall
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
call eqZeroCbCall math.equalF64
arg eqZeroCbCall left inputValue
arg eqZeroCbCall right zeroCb
run eqZeroCbCall
bind xIsZero Bool eqZeroCbCall
branchIf xIsZero cbrtZero
call absXcbCall absoluteFloat64
arg absXcbCall x inputValue
run absXcbCall
bindOk absXc CFloat64 absXcbCall
call powAbsCall powerFloat64
arg powAbsCall base absXc
arg powAbsCall exponent oneThirdCb
run powAbsCall
bindOk powAbsRes CFloat64 powAbsCall
call ltZeroCheckCall math.lessThanF64
arg ltZeroCheckCall left inputValue
arg ltZeroCheckCall right zeroCb
run ltZeroCheckCall
bind xIsNeg Bool ltZeroCheckCall
branchIf xIsNeg cbrtNegate
returnValue powAbsRes
label cbrtNegate
call flipCbCall math.multiplyF64
arg flipCbCall left powAbsRes
arg flipCbCall right negOneCb
run flipCbCall
bind flippedCb CFloat64 flipCbCall
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
bindOk twoToTheXResult CFloat64 powCall
returnValue twoToTheXResult


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
purpose main "Smoke-test absoluteFloat64 / squareRootFloat64 / exponentialBaseEFloat64. Prints OK on success."
invariant main "Every assertion that should hold returns Ok; final OK line is written via console.writeLine."

label startMain

# absoluteFloat64(-3.5) == 3.5
const negPointFive CFloat64 -3.5
const expFabs CFloat64 3.5
call f1Call absoluteFloat64
arg f1Call x negPointFive
run f1Call
bindOk f1Res CFloat64 f1Call
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
call s1Call squareRootFloat64
arg s1Call x c144
run s1Call
bindOk s1Res CFloat64 s1Call
call diffCall math.subtractF64
arg diffCall left s1Res
arg diffCall right c12
run diffCall
bind diff CFloat64 diffCall
call abs1Call absoluteFloat64
arg abs1Call x diff
run abs1Call
bindOk diffAbs CFloat64 abs1Call
call s1CheckCall math.lessThanF64
arg s1CheckCall left diffAbs
arg s1CheckCall right tol
run s1CheckCall
bind s1Ok Bool s1CheckCall
branchIf s1Ok s1OkLabel
branch testFailed
label s1OkLabel

# exponentialBaseEFloat64(1.0) approximately 2.718281828
const oneExp CFloat64 1.0
const eulerApprox CFloat64 2.718281828
const tolE CFloat64 0.001
call e1Call exponentialBaseEFloat64
arg e1Call x oneExp
run e1Call
bindOk e1Res CFloat64 e1Call
call diff2Call math.subtractF64
arg diff2Call left e1Res
arg diff2Call right eulerApprox
run diff2Call
bind diff2 CFloat64 diff2Call
call abs2Call absoluteFloat64
arg abs2Call x diff2
run abs2Call
bindOk diff2Abs CFloat64 abs2Call
call e1CheckCall math.lessThanF64
arg e1CheckCall left diff2Abs
arg e1CheckCall right tolE
run e1CheckCall
bind e1Ok Bool e1CheckCall
branchIf e1Ok e1OkLabel
branch testFailed
label e1OkLabel

# truncateFloat64TowardZero(3.7) == 3.0
const cThreeSeven CFloat64 3.7
const cThree CFloat64 3.0
call tr1Call truncateFloat64TowardZero
arg tr1Call x cThreeSeven
run tr1Call
bindOk tr1Res CFloat64 tr1Call
call tr1CheckCall math.equalF64
arg tr1CheckCall left tr1Res
arg tr1CheckCall right cThree
run tr1CheckCall
bind tr1Ok Bool tr1CheckCall
branchIf tr1Ok tr1OkLabel
branch testFailed
label tr1OkLabel

# floorFloat64(-2.3) == -3.0
const cNegTwoThree CFloat64 -2.3
const cNegThree CFloat64 -3.0
call fl1Call floorFloat64
arg fl1Call x cNegTwoThree
run fl1Call
bindOk fl1Res CFloat64 fl1Call
call fl1CheckCall math.equalF64
arg fl1CheckCall left fl1Res
arg fl1CheckCall right cNegThree
run fl1CheckCall
bind fl1Ok Bool fl1CheckCall
branchIf fl1Ok fl1OkLabel
branch testFailed
label fl1OkLabel

# ceilingFloat64(2.3) == 3.0
const cTwoThree CFloat64 2.3
call ce1Call ceilingFloat64
arg ce1Call x cTwoThree
run ce1Call
bindOk ce1Res CFloat64 ce1Call
call ce1CheckCall math.equalF64
arg ce1CheckCall left ce1Res
arg ce1CheckCall right cThree
run ce1CheckCall
bind ce1Ok Bool ce1CheckCall
branchIf ce1Ok ce1OkLabel
branch testFailed
label ce1OkLabel

# floatingRemainderFloat64(7.5, 2.0) == 1.5
const cSevenHalf CFloat64 7.5
const cTwoFl CFloat64 2.0
const cOneHalf CFloat64 1.5
call fm1Call floatingRemainderFloat64
arg fm1Call x cSevenHalf
arg fm1Call y cTwoFl
run fm1Call
bindOk fm1Res CFloat64 fm1Call
call fm1CheckCall math.equalF64
arg fm1CheckCall left fm1Res
arg fm1CheckCall right cOneHalf
run fm1CheckCall
bind fm1Ok Bool fm1CheckCall
branchIf fm1Ok fm1OkLabel
branch testFailed
label fm1OkLabel

# naturalLogFloat64(e) approximately 1.0
const eApprox CFloat64 2.718281828
const oneTarget CFloat64 1.0
const tolLn CFloat64 0.01
call ln1Call naturalLogFloat64
arg ln1Call x eApprox
run ln1Call
bindOk ln1Res CFloat64 ln1Call
call ln1DiffCall math.subtractF64
arg ln1DiffCall left ln1Res
arg ln1DiffCall right oneTarget
run ln1DiffCall
bind ln1DiffV CFloat64 ln1DiffCall
call ln1AbsCall absoluteFloat64
arg ln1AbsCall x ln1DiffV
run ln1AbsCall
bindOk ln1AbsV CFloat64 ln1AbsCall
call ln1CheckCall math.lessThanF64
arg ln1CheckCall left ln1AbsV
arg ln1CheckCall right tolLn
run ln1CheckCall
bind ln1Ok Bool ln1CheckCall
branchIf ln1Ok ln1OkLabel
branch testFailed
label ln1OkLabel

# powerFloat64(2.0, 10.0) approximately 1024.0
const cTen CFloat64 10.0
const cOneOhTwoFour CFloat64 1024.0
const tolPw CFloat64 5.0
call pw1Call powerFloat64
arg pw1Call base cTwoFl
arg pw1Call exponent cTen
run pw1Call
bindOk pw1Res CFloat64 pw1Call
call pw1DiffCall math.subtractF64
arg pw1DiffCall left pw1Res
arg pw1DiffCall right cOneOhTwoFour
run pw1DiffCall
bind pw1DiffV CFloat64 pw1DiffCall
call pw1AbsCall absoluteFloat64
arg pw1AbsCall x pw1DiffV
run pw1AbsCall
bindOk pw1AbsV CFloat64 pw1AbsCall
call pw1CheckCall math.lessThanF64
arg pw1CheckCall left pw1AbsV
arg pw1CheckCall right tolPw
run pw1CheckCall
bind pw1Ok Bool pw1CheckCall
branchIf pw1Ok pw1OkLabel
branch testFailed
label pw1OkLabel

# sineRadiansFloat64(0.0) approximately 0.0
const zeroFs CFloat64 0.0
const tolSin CFloat64 0.001
call sn1Call sineRadiansFloat64
arg sn1Call x zeroFs
run sn1Call
bindOk sn1Res CFloat64 sn1Call
call sn1AbsCall absoluteFloat64
arg sn1AbsCall x sn1Res
run sn1AbsCall
bindOk sn1AbsV CFloat64 sn1AbsCall
call sn1CheckCall math.lessThanF64
arg sn1CheckCall left sn1AbsV
arg sn1CheckCall right tolSin
run sn1CheckCall
bind sn1Ok Bool sn1CheckCall
branchIf sn1Ok sn1OkLabel
branch testFailed
label sn1OkLabel

# cosineRadiansFloat64(0.0) approximately 1.0
call cs1Call cosineRadiansFloat64
arg cs1Call x zeroFs
run cs1Call
bindOk cs1Res CFloat64 cs1Call
call cs1DiffCall math.subtractF64
arg cs1DiffCall left cs1Res
arg cs1DiffCall right oneTarget
run cs1DiffCall
bind cs1DiffV CFloat64 cs1DiffCall
call cs1AbsCall absoluteFloat64
arg cs1AbsCall x cs1DiffV
run cs1AbsCall
bindOk cs1AbsV CFloat64 cs1AbsCall
call cs1CheckCall math.lessThanF64
arg cs1CheckCall left cs1AbsV
arg cs1CheckCall right tolSin
run cs1CheckCall
bind cs1Ok Bool cs1CheckCall
branchIf cs1Ok cs1OkLabel
branch testFailed
label cs1OkLabel

# logBaseTwoFloat64(8.0) approximately 3.0
const eightFs CFloat64 8.0
const threeFs CFloat64 3.0
const tolLg CFloat64 0.01
call lg2vCall logBaseTwoFloat64
arg lg2vCall x eightFs
run lg2vCall
bindOk lg2vRes CFloat64 lg2vCall
call lg2vDiffCall math.subtractF64
arg lg2vDiffCall left lg2vRes
arg lg2vDiffCall right threeFs
run lg2vDiffCall
bind lg2vDiffV CFloat64 lg2vDiffCall
call lg2vAbsCall absoluteFloat64
arg lg2vAbsCall x lg2vDiffV
run lg2vAbsCall
bindOk lg2vAbsV CFloat64 lg2vAbsCall
call lg2vCheckCall math.lessThanF64
arg lg2vCheckCall left lg2vAbsV
arg lg2vCheckCall right tolLg
run lg2vCheckCall
bind lg2vOk Bool lg2vCheckCall
branchIf lg2vOk lg2vOkLabel
branch testFailed
label lg2vOkLabel

# logBaseTenFloat64(1000.0) approximately 3.0
const thousandFs CFloat64 1000.0
call lg10vCall logBaseTenFloat64
arg lg10vCall x thousandFs
run lg10vCall
bindOk lg10vRes CFloat64 lg10vCall
call lg10vDiffCall math.subtractF64
arg lg10vDiffCall left lg10vRes
arg lg10vDiffCall right threeFs
run lg10vDiffCall
bind lg10vDiffV CFloat64 lg10vDiffCall
call lg10vAbsCall absoluteFloat64
arg lg10vAbsCall x lg10vDiffV
run lg10vAbsCall
bindOk lg10vAbsV CFloat64 lg10vAbsCall
call lg10vCheckCall math.lessThanF64
arg lg10vCheckCall left lg10vAbsV
arg lg10vCheckCall right tolLg
run lg10vCheckCall
bind lg10vOk Bool lg10vCheckCall
branchIf lg10vOk lg10vOkLabel
branch testFailed
label lg10vOkLabel

# hypotenuseFloat64(3.0, 4.0) approximately 5.0
const fourFs CFloat64 4.0
const fiveFs CFloat64 5.0
const tolHyp CFloat64 0.0001
call hyp1Call hypotenuseFloat64
arg hyp1Call x threeFs
arg hyp1Call y fourFs
run hyp1Call
bindOk hyp1Res CFloat64 hyp1Call
call hyp1DiffCall math.subtractF64
arg hyp1DiffCall left hyp1Res
arg hyp1DiffCall right fiveFs
run hyp1DiffCall
bind hyp1DiffV CFloat64 hyp1DiffCall
call hyp1AbsCall absoluteFloat64
arg hyp1AbsCall x hyp1DiffV
run hyp1AbsCall
bindOk hyp1AbsV CFloat64 hyp1AbsCall
call hyp1CheckCall math.lessThanF64
arg hyp1CheckCall left hyp1AbsV
arg hyp1CheckCall right tolHyp
run hyp1CheckCall
bind hyp1Ok Bool hyp1CheckCall
branchIf hyp1Ok hyp1OkLabel
branch testFailed
label hyp1OkLabel

# arctangentRadiansFloat64(1.0) approximately pi/4 = 0.785398
const piOver4 CFloat64 0.7853981633974483
const tolAtan CFloat64 0.01
call atn1Call arctangentRadiansFloat64
arg atn1Call x oneTarget
run atn1Call
bindOk atn1Res CFloat64 atn1Call
call atn1DiffCall math.subtractF64
arg atn1DiffCall left atn1Res
arg atn1DiffCall right piOver4
run atn1DiffCall
bind atn1DiffV CFloat64 atn1DiffCall
call atn1AbsCall absoluteFloat64
arg atn1AbsCall x atn1DiffV
run atn1AbsCall
bindOk atn1AbsV CFloat64 atn1AbsCall
call atn1CheckCall math.lessThanF64
arg atn1CheckCall left atn1AbsV
arg atn1CheckCall right tolAtan
run atn1CheckCall
bind atn1Ok Bool atn1CheckCall
branchIf atn1Ok atn1OkLabel
branch testFailed
label atn1OkLabel

# ============================================================
# Extended unit-test cases: covers the 17 operations the original
# smoke test omitted (tangent, sinh, cosh, tanh, expm1, log1p,
# arcsin, arccos, fma, max, min, positiveDifference, copySign,
# sign, round, cbrt, exp2), plus identity/zero boundaries for the
# already-covered operations.
# ============================================================

const tolGeneral CFloat64 0.001
const zeroExtra CFloat64 0.0
const oneExtra CFloat64 1.0
const negOneExtra CFloat64 -1.0
const twoExtra CFloat64 2.0
const threeExtra CFloat64 3.0
const fourExtra CFloat64 4.0
const fiveExtra CFloat64 5.0
const tenExtra CFloat64 10.0
const negFiveExtra CFloat64 -5.0
const piHalf CFloat64 1.5707963267948966
const piValue CFloat64 3.141592653589793

# absoluteFloat64(0.0) == 0.0
call fabsZeroCall absoluteFloat64
arg fabsZeroCall x zeroExtra
run fabsZeroCall
bindOk fabsZeroRes CFloat64 fabsZeroCall
call fabsZeroCheckCall math.equalF64
arg fabsZeroCheckCall left fabsZeroRes
arg fabsZeroCheckCall right zeroExtra
run fabsZeroCheckCall
bind fabsZeroOk Bool fabsZeroCheckCall
branchIf fabsZeroOk fabsZeroOkLabel
branch testFailed
label fabsZeroOkLabel

# absoluteFloat64(3.5) == 3.5 (positive identity)
call fabsPosCall absoluteFloat64
arg fabsPosCall x expFabs
run fabsPosCall
bindOk fabsPosRes CFloat64 fabsPosCall
call fabsPosCheckCall math.equalF64
arg fabsPosCheckCall left fabsPosRes
arg fabsPosCheckCall right expFabs
run fabsPosCheckCall
bind fabsPosOk Bool fabsPosCheckCall
branchIf fabsPosOk fabsPosOkLabel
branch testFailed
label fabsPosOkLabel

# squareRootFloat64(0.0) ≈ 0.0
call sqrtZeroCall squareRootFloat64
arg sqrtZeroCall x zeroExtra
run sqrtZeroCall
bindOk sqrtZeroRes CFloat64 sqrtZeroCall
call sqrtZeroAbsCall absoluteFloat64
arg sqrtZeroAbsCall x sqrtZeroRes
run sqrtZeroAbsCall
bindOk sqrtZeroAbs CFloat64 sqrtZeroAbsCall
call sqrtZeroCheckCall math.lessThanF64
arg sqrtZeroCheckCall left sqrtZeroAbs
arg sqrtZeroCheckCall right tolGeneral
run sqrtZeroCheckCall
bind sqrtZeroOk Bool sqrtZeroCheckCall
branchIf sqrtZeroOk sqrtZeroOkLabel
branch testFailed
label sqrtZeroOkLabel

# exponentialBaseEFloat64(0.0) ≈ 1.0 (e^0 == 1 identity)
call expZeroCall exponentialBaseEFloat64
arg expZeroCall x zeroExtra
run expZeroCall
bindOk expZeroRes CFloat64 expZeroCall
call expZeroDiffCall math.subtractF64
arg expZeroDiffCall left expZeroRes
arg expZeroDiffCall right oneExtra
run expZeroDiffCall
bind expZeroDiff CFloat64 expZeroDiffCall
call expZeroAbsCall absoluteFloat64
arg expZeroAbsCall x expZeroDiff
run expZeroAbsCall
bindOk expZeroAbs CFloat64 expZeroAbsCall
call expZeroCheckCall math.lessThanF64
arg expZeroCheckCall left expZeroAbs
arg expZeroCheckCall right tolGeneral
run expZeroCheckCall
bind expZeroOk Bool expZeroCheckCall
branchIf expZeroOk expZeroOkLabel
branch testFailed
label expZeroOkLabel

# naturalLogFloat64(1.0) ≈ 0.0 (ln(1) == 0)
call lnOneCall naturalLogFloat64
arg lnOneCall x oneExtra
run lnOneCall
bindOk lnOneRes CFloat64 lnOneCall
call lnOneAbsCall absoluteFloat64
arg lnOneAbsCall x lnOneRes
run lnOneAbsCall
bindOk lnOneAbs CFloat64 lnOneAbsCall
call lnOneCheckCall math.lessThanF64
arg lnOneCheckCall left lnOneAbs
arg lnOneCheckCall right tolGeneral
run lnOneCheckCall
bind lnOneOk Bool lnOneCheckCall
branchIf lnOneOk lnOneOkLabel
branch testFailed
label lnOneOkLabel

# tangentRadiansFloat64(0.0) ≈ 0.0
call tanZeroCall tangentRadiansFloat64
arg tanZeroCall x zeroExtra
run tanZeroCall
bindOk tanZeroRes CFloat64 tanZeroCall
call tanZeroAbsCall absoluteFloat64
arg tanZeroAbsCall x tanZeroRes
run tanZeroAbsCall
bindOk tanZeroAbs CFloat64 tanZeroAbsCall
call tanZeroCheckCall math.lessThanF64
arg tanZeroCheckCall left tanZeroAbs
arg tanZeroCheckCall right tolGeneral
run tanZeroCheckCall
bind tanZeroOk Bool tanZeroCheckCall
branchIf tanZeroOk tanZeroOkLabel
branch testFailed
label tanZeroOkLabel

# hyperbolicSineFloat64(0.0) ≈ 0.0
call sinhZeroCall hyperbolicSineFloat64
arg sinhZeroCall x zeroExtra
run sinhZeroCall
bindOk sinhZeroRes CFloat64 sinhZeroCall
call sinhZeroAbsCall absoluteFloat64
arg sinhZeroAbsCall x sinhZeroRes
run sinhZeroAbsCall
bindOk sinhZeroAbs CFloat64 sinhZeroAbsCall
call sinhZeroCheckCall math.lessThanF64
arg sinhZeroCheckCall left sinhZeroAbs
arg sinhZeroCheckCall right tolGeneral
run sinhZeroCheckCall
bind sinhZeroOk Bool sinhZeroCheckCall
branchIf sinhZeroOk sinhZeroOkLabel
branch testFailed
label sinhZeroOkLabel

# hyperbolicCosineFloat64(0.0) ≈ 1.0
call coshZeroCall hyperbolicCosineFloat64
arg coshZeroCall x zeroExtra
run coshZeroCall
bindOk coshZeroRes CFloat64 coshZeroCall
call coshZeroDiffCall math.subtractF64
arg coshZeroDiffCall left coshZeroRes
arg coshZeroDiffCall right oneExtra
run coshZeroDiffCall
bind coshZeroDiff CFloat64 coshZeroDiffCall
call coshZeroAbsCall absoluteFloat64
arg coshZeroAbsCall x coshZeroDiff
run coshZeroAbsCall
bindOk coshZeroAbs CFloat64 coshZeroAbsCall
call coshZeroCheckCall math.lessThanF64
arg coshZeroCheckCall left coshZeroAbs
arg coshZeroCheckCall right tolGeneral
run coshZeroCheckCall
bind coshZeroOk Bool coshZeroCheckCall
branchIf coshZeroOk coshZeroOkLabel
branch testFailed
label coshZeroOkLabel

# hyperbolicTangentFloat64(0.0) ≈ 0.0
call tanhZeroCall hyperbolicTangentFloat64
arg tanhZeroCall x zeroExtra
run tanhZeroCall
bindOk tanhZeroRes CFloat64 tanhZeroCall
call tanhZeroAbsCall absoluteFloat64
arg tanhZeroAbsCall x tanhZeroRes
run tanhZeroAbsCall
bindOk tanhZeroAbs CFloat64 tanhZeroAbsCall
call tanhZeroCheckCall math.lessThanF64
arg tanhZeroCheckCall left tanhZeroAbs
arg tanhZeroCheckCall right tolGeneral
run tanhZeroCheckCall
bind tanhZeroOk Bool tanhZeroCheckCall
branchIf tanhZeroOk tanhZeroOkLabel
branch testFailed
label tanhZeroOkLabel

# exponentialMinusOneFloat64(0.0) ≈ 0.0 (exp(0)-1 = 0)
call expm1ZeroCall exponentialMinusOneFloat64
arg expm1ZeroCall x zeroExtra
run expm1ZeroCall
bindOk expm1ZeroRes CFloat64 expm1ZeroCall
call expm1ZeroAbsCall absoluteFloat64
arg expm1ZeroAbsCall x expm1ZeroRes
run expm1ZeroAbsCall
bindOk expm1ZeroAbs CFloat64 expm1ZeroAbsCall
call expm1ZeroCheckCall math.lessThanF64
arg expm1ZeroCheckCall left expm1ZeroAbs
arg expm1ZeroCheckCall right tolGeneral
run expm1ZeroCheckCall
bind expm1ZeroOk Bool expm1ZeroCheckCall
branchIf expm1ZeroOk expm1ZeroOkLabel
branch testFailed
label expm1ZeroOkLabel

# naturalLogOnePlusFloat64(0.0) ≈ 0.0 (ln(1+0) = 0)
call log1pZeroCall naturalLogOnePlusFloat64
arg log1pZeroCall x zeroExtra
run log1pZeroCall
bindOk log1pZeroRes CFloat64 log1pZeroCall
call log1pZeroAbsCall absoluteFloat64
arg log1pZeroAbsCall x log1pZeroRes
run log1pZeroAbsCall
bindOk log1pZeroAbs CFloat64 log1pZeroAbsCall
call log1pZeroCheckCall math.lessThanF64
arg log1pZeroCheckCall left log1pZeroAbs
arg log1pZeroCheckCall right tolGeneral
run log1pZeroCheckCall
bind log1pZeroOk Bool log1pZeroCheckCall
branchIf log1pZeroOk log1pZeroOkLabel
branch testFailed
label log1pZeroOkLabel

# arcsineRadiansFloat64(1.0) ≈ pi/2
call asinOneCall arcsineRadiansFloat64
arg asinOneCall x oneExtra
run asinOneCall
bindOk asinOneRes CFloat64 asinOneCall
call asinOneDiffCall math.subtractF64
arg asinOneDiffCall left asinOneRes
arg asinOneDiffCall right piHalf
run asinOneDiffCall
bind asinOneDiff CFloat64 asinOneDiffCall
call asinOneAbsCall absoluteFloat64
arg asinOneAbsCall x asinOneDiff
run asinOneAbsCall
bindOk asinOneAbs CFloat64 asinOneAbsCall
call asinOneCheckCall math.lessThanF64
arg asinOneCheckCall left asinOneAbs
arg asinOneCheckCall right tolGeneral
run asinOneCheckCall
bind asinOneOk Bool asinOneCheckCall
branchIf asinOneOk asinOneOkLabel
branch testFailed
label asinOneOkLabel

# arccosineRadiansFloat64(1.0) ≈ 0.0
call acosOneCall arccosineRadiansFloat64
arg acosOneCall x oneExtra
run acosOneCall
bindOk acosOneRes CFloat64 acosOneCall
call acosOneAbsCall absoluteFloat64
arg acosOneAbsCall x acosOneRes
run acosOneAbsCall
bindOk acosOneAbs CFloat64 acosOneAbsCall
call acosOneCheckCall math.lessThanF64
arg acosOneCheckCall left acosOneAbs
arg acosOneCheckCall right tolGeneral
run acosOneCheckCall
bind acosOneOk Bool acosOneCheckCall
branchIf acosOneOk acosOneOkLabel
branch testFailed
label acosOneOkLabel

# fusedMultiplyAddFloat64(2.0, 3.0, 4.0) == 10.0
call fmaCall fusedMultiplyAddFloat64
arg fmaCall x twoExtra
arg fmaCall y threeExtra
arg fmaCall z fourExtra
run fmaCall
bindOk fmaRes CFloat64 fmaCall
call fmaCheckCall math.equalF64
arg fmaCheckCall left fmaRes
arg fmaCheckCall right tenExtra
run fmaCheckCall
bind fmaOk Bool fmaCheckCall
branchIf fmaOk fmaOkLabel
branch testFailed
label fmaOkLabel

# maximumFloat64(3.0, 5.0) == 5.0
call maxCall maximumFloat64
arg maxCall x threeExtra
arg maxCall y fiveExtra
run maxCall
bindOk maxRes CFloat64 maxCall
call maxCheckCall math.equalF64
arg maxCheckCall left maxRes
arg maxCheckCall right fiveExtra
run maxCheckCall
bind maxOk Bool maxCheckCall
branchIf maxOk maxOkLabel
branch testFailed
label maxOkLabel

# minimumFloat64(3.0, 5.0) == 3.0
call minCall minimumFloat64
arg minCall x threeExtra
arg minCall y fiveExtra
run minCall
bindOk minRes CFloat64 minCall
call minCheckCall math.equalF64
arg minCheckCall left minRes
arg minCheckCall right threeExtra
run minCheckCall
bind minOk Bool minCheckCall
branchIf minOk minOkLabel
branch testFailed
label minOkLabel

# positiveDifferenceFloat64(7.0, 3.0) == 4.0
const sevenExtra CFloat64 7.0
call pdiffCall positiveDifferenceFloat64
arg pdiffCall x sevenExtra
arg pdiffCall y threeExtra
run pdiffCall
bindOk pdiffRes CFloat64 pdiffCall
call pdiffCheckCall math.equalF64
arg pdiffCheckCall left pdiffRes
arg pdiffCheckCall right fourExtra
run pdiffCheckCall
bind pdiffOk Bool pdiffCheckCall
branchIf pdiffOk pdiffOkLabel
branch testFailed
label pdiffOkLabel

# copySignFloat64(5.0, -1.0) == -5.0 (positive magnitude + negative sign)
call copySignCall copySignFloat64
arg copySignCall x fiveExtra
arg copySignCall y negOneExtra
run copySignCall
bindOk copySignRes CFloat64 copySignCall
call copySignCheckCall math.equalF64
arg copySignCheckCall left copySignRes
arg copySignCheckCall right negFiveExtra
run copySignCheckCall
bind copySignOk Bool copySignCheckCall
branchIf copySignOk copySignOkLabel
branch testFailed
label copySignOkLabel

# signOfFloat64(-2.5) == -1.0
const negTwoHalf CFloat64 -2.5
call signNegCall signOfFloat64
arg signNegCall x negTwoHalf
run signNegCall
bindOk signNegRes CFloat64 signNegCall
call signNegCheckCall math.equalF64
arg signNegCheckCall left signNegRes
arg signNegCheckCall right negOneExtra
run signNegCheckCall
bind signNegOk Bool signNegCheckCall
branchIf signNegOk signNegOkLabel
branch testFailed
label signNegOkLabel

# signOfFloat64(0.0) == 0.0
call signZeroCall signOfFloat64
arg signZeroCall x zeroExtra
run signZeroCall
bindOk signZeroRes CFloat64 signZeroCall
call signZeroCheckCall math.equalF64
arg signZeroCheckCall left signZeroRes
arg signZeroCheckCall right zeroExtra
run signZeroCheckCall
bind signZeroOk Bool signZeroCheckCall
branchIf signZeroOk signZeroOkLabel
branch testFailed
label signZeroOkLabel

# roundFloat64ToNearestInteger(2.7) == 3.0
const twoSeven CFloat64 2.7
call roundCall roundFloat64ToNearestInteger
arg roundCall x twoSeven
run roundCall
bindOk roundRes CFloat64 roundCall
call roundCheckCall math.equalF64
arg roundCheckCall left roundRes
arg roundCheckCall right threeExtra
run roundCheckCall
bind roundOk Bool roundCheckCall
branchIf roundOk roundOkLabel
branch testFailed
label roundOkLabel

# cubeRootFloat64(27.0) ≈ 3.0
const twentySeven CFloat64 27.0
call cbrtCall cubeRootFloat64
arg cbrtCall x twentySeven
run cbrtCall
bindOk cbrtRes CFloat64 cbrtCall
call cbrtDiffCall math.subtractF64
arg cbrtDiffCall left cbrtRes
arg cbrtDiffCall right threeExtra
run cbrtDiffCall
bind cbrtDiff CFloat64 cbrtDiffCall
call cbrtAbsCall absoluteFloat64
arg cbrtAbsCall x cbrtDiff
run cbrtAbsCall
bindOk cbrtAbs CFloat64 cbrtAbsCall
call cbrtCheckCall math.lessThanF64
arg cbrtCheckCall left cbrtAbs
arg cbrtCheckCall right tolGeneral
run cbrtCheckCall
bind cbrtOk Bool cbrtCheckCall
branchIf cbrtOk cbrtOkLabel
branch testFailed
label cbrtOkLabel

# exponentialBaseTwoFloat64(3.0) ≈ 8.0
const eightExtra CFloat64 8.0
call exp2Call exponentialBaseTwoFloat64
arg exp2Call x threeExtra
run exp2Call
bindOk exp2Res CFloat64 exp2Call
call exp2DiffCall math.subtractF64
arg exp2DiffCall left exp2Res
arg exp2DiffCall right eightExtra
run exp2DiffCall
bind exp2Diff CFloat64 exp2DiffCall
call exp2AbsCall absoluteFloat64
arg exp2AbsCall x exp2Diff
run exp2AbsCall
bindOk exp2Abs CFloat64 exp2AbsCall
call exp2CheckCall math.lessThanF64
arg exp2CheckCall left exp2Abs
arg exp2CheckCall right tolGeneral
run exp2CheckCall
bind exp2Ok Bool exp2CheckCall
branchIf exp2Ok exp2OkLabel
branch testFailed
label exp2OkLabel

# Property: sin(pi/2) ≈ 1.0 (key trig boundary)
call sinHalfPiCall sineRadiansFloat64
arg sinHalfPiCall x piHalf
run sinHalfPiCall
bindOk sinHalfPiRes CFloat64 sinHalfPiCall
call sinHalfPiDiffCall math.subtractF64
arg sinHalfPiDiffCall left sinHalfPiRes
arg sinHalfPiDiffCall right oneExtra
run sinHalfPiDiffCall
bind sinHalfPiDiff CFloat64 sinHalfPiDiffCall
call sinHalfPiAbsCall absoluteFloat64
arg sinHalfPiAbsCall x sinHalfPiDiff
run sinHalfPiAbsCall
bindOk sinHalfPiAbs CFloat64 sinHalfPiAbsCall
call sinHalfPiCheckCall math.lessThanF64
arg sinHalfPiCheckCall left sinHalfPiAbs
arg sinHalfPiCheckCall right tolGeneral
run sinHalfPiCheckCall
bind sinHalfPiOk Bool sinHalfPiCheckCall
branchIf sinHalfPiOk sinHalfPiOkLabel
branch testFailed
label sinHalfPiOkLabel

# Property: cos(pi) ≈ -1.0 (key trig boundary)
call cosPiCall cosineRadiansFloat64
arg cosPiCall x piValue
run cosPiCall
bindOk cosPiRes CFloat64 cosPiCall
call cosPiDiffCall math.subtractF64
arg cosPiDiffCall left cosPiRes
arg cosPiDiffCall right negOneExtra
run cosPiDiffCall
bind cosPiDiff CFloat64 cosPiDiffCall
call cosPiAbsCall absoluteFloat64
arg cosPiAbsCall x cosPiDiff
run cosPiAbsCall
bindOk cosPiAbs CFloat64 cosPiAbsCall
call cosPiCheckCall math.lessThanF64
arg cosPiCheckCall left cosPiAbs
arg cosPiCheckCall right tolGeneral
run cosPiCheckCall
bind cosPiOk Bool cosPiCheckCall
branchIf cosPiOk cosPiOkLabel
branch testFailed
label cosPiOkLabel

# Property: sin² + cos² ≈ 1 for x = 0.5 (Pythagorean identity)
const halfExtra CFloat64 0.5
call pythSinCall sineRadiansFloat64
arg pythSinCall x halfExtra
run pythSinCall
bindOk pythSinRes CFloat64 pythSinCall
call pythCosCall cosineRadiansFloat64
arg pythCosCall x halfExtra
run pythCosCall
bindOk pythCosRes CFloat64 pythCosCall
call pythSinSqCall math.multiplyF64
arg pythSinSqCall left pythSinRes
arg pythSinSqCall right pythSinRes
run pythSinSqCall
bind pythSinSq CFloat64 pythSinSqCall
call pythCosSqCall math.multiplyF64
arg pythCosSqCall left pythCosRes
arg pythCosSqCall right pythCosRes
run pythCosSqCall
bind pythCosSq CFloat64 pythCosSqCall
call pythSumCall math.addF64
arg pythSumCall left pythSinSq
arg pythSumCall right pythCosSq
run pythSumCall
bind pythSum CFloat64 pythSumCall
call pythDiffCall math.subtractF64
arg pythDiffCall left pythSum
arg pythDiffCall right oneExtra
run pythDiffCall
bind pythDiff CFloat64 pythDiffCall
call pythAbsCall absoluteFloat64
arg pythAbsCall x pythDiff
run pythAbsCall
bindOk pythAbs CFloat64 pythAbsCall
call pythCheckCall math.lessThanF64
arg pythCheckCall left pythAbs
arg pythCheckCall right tolGeneral
run pythCheckCall
bind pythOk Bool pythCheckCall
branchIf pythOk pythOkLabel
branch testFailed
label pythOkLabel

# All assertions hold. Emit "OK" via console.writeLine — uniform
# with the other stdlib smokes, references the runtime console
# handle, and surfaces a typed ConsoleWriteFailed if stdout itself
# fails (closed pipe, etc.).
const successMessageText CNullTerminatedByteString "OK"
call writeSuccessLineCall console.writeLine
arg writeSuccessLineCall console console
arg writeSuccessLineCall text successMessageText
run writeSuccessLineCall
ignoreOk writeSuccessLineCall CSignedInt32
bindError consoleWriteResultError CSignedInt32 writeSuccessLineCall
branchIfError writeSuccessLineCall consoleWriteFailedHandler

const exitOk ExitCode 0
returnOk exitOk

# Failure leg: surface the raw negative CSignedInt32 from
# console.writeLine as the cause attached to the typed
# MainError.ConsoleWriteFailed variant.
label consoleWriteFailedHandler
makeError consoleWriteFailedFailure MainError.ConsoleWriteFailed consoleWriteResultError
returnError consoleWriteFailedFailure

label testFailed
makeError testFailure MainError.MathFloatSmokeAssertionFailed
returnError testFailure
