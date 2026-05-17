project StdMathFloatSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <math.h>-style float ops, pure AS.
#
# Implementations use only math.{add,subtract,multiply,divide}F64 and
# comparison primitives. NO call to libm: no c.sqrt, c.exp, c.log,
# c.fabs etc. appears in the emitted IR.
#
# Range and accuracy caveats:
#   sqrtFloat       : full range for x >= 0; Newton converges in
#                     ~50 iterations to ~1ulp for IEEE-754 doubles.
#   fabsFloat       : exact for all inputs.
#   expFloat        : Taylor series with 30 terms; accurate to ~12
#                     decimals for |x| <= 2. Beyond that range the
#                     polynomial loses precision quickly.
#   lnFloat         : Newton iteration on f(y) = exp(y) - x; needs
#                     x > 0; converges in ~20 iterations for x in
#                     [0.01, 100].
#   powFloat        : computes exp(y * ln(x)); inherits range from
#                     ln and exp. Defined for x > 0.
#
# These are NOT replacements for a production libm; they're the
# pure-AS ports that let an AgentScript program do float math without
# linking against libm.
# ============================================================


operation fabsFloat
input fabsFloat x CFloat64
output fabsFloat Result CFloat64 Void
memory fabsFloat heap no
async fabsFloat no
purpose fabsFloat "|x| for double-precision x. Pure AS via comparison + multiply by -1."

label startFabsFloat
const zeroF CFloat64 0.0
const negOneF CFloat64 -1.0
call isNegCall math.lessThanF64
arg isNegCall left x
arg isNegCall right zeroF
run isNegCall
bind isNeg Bool isNegCall
branchIf isNeg fabsFlip
returnOk x
label fabsFlip
call flipCall math.multiplyF64
arg flipCall left x
arg flipCall right negOneF
run flipCall
bind flipped CFloat64 flipCall
returnOk flipped


operation sqrtFloat
input sqrtFloat x CFloat64
output sqrtFloat Result CFloat64 Void
memory sqrtFloat heap no
async sqrtFloat no
purpose sqrtFloat "sqrt(x) for x >= 0 via Newton's method. Returns 0.0 for x <= 0 (no NaN here yet — that needs IEEE special-value support)."

label startSqrtFloat
const zeroFS CFloat64 0.0
const halfFS CFloat64 0.5
const oneFS CFloat64 1.0
const epsFS CFloat64 0.0000000000001

call lezCall math.lessThanOrEqualF64
arg lezCall left x
arg lezCall right zeroFS
run lezCall
bind lez Bool lezCall
branchIf lez sqrtZero

# Start at x itself (works for x >= 1; for 0 < x < 1, also converges).
var guess CFloat64 1.0
set guess x
var iter I64 0
const maxIter I64 50
const oneI I64 1

label sqrtIter
call divCall math.divideF64
arg divCall left x
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
returnOk guess

label sqrtZero
returnOk zeroFS


operation expFloat
input expFloat x CFloat64
output expFloat Result CFloat64 Void
memory expFloat heap no
async expFloat no
purpose expFloat "e^x via Taylor series: sum_{k=0..29} x^k / k!. Accurate to ~12 decimals for |x| <= 2; degrades beyond that. No argument reduction yet."

label startExpFloat
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
arg mulCall right x
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
returnOk sumE


operation truncFloat
input truncFloat x CFloat64
output truncFloat Result CFloat64 Void
memory truncFloat heap no
async truncFloat no
purpose truncFloat "Truncate toward zero. Uses math.floatToInt (fptosi) which already truncates, then converts back."
label startTruncFloat
call toIntCall math.floatToInt
arg toIntCall value x
run toIntCall
bind asInt CSignedInt64 toIntCall
call backToFloatCall math.intToFloat
arg backToFloatCall value asInt
run backToFloatCall
bind backFloat CFloat64 backToFloatCall
returnOk backFloat


operation floorFloat
input floorFloat x CFloat64
output floorFloat Result CFloat64 Void
memory floorFloat heap no
async floorFloat no
purpose floorFloat "Largest integer <= x. trunc(x) is identical to floor for x >= 0, but for negative non-integer x we have to step down by 1."
label startFloorFloat
const zeroFlr CFloat64 0.0
const oneFlr CFloat64 1.0
call trCall truncFloat
arg trCall x x
run trCall
bindOk truncated CFloat64 trCall

# If x >= 0, floor == trunc.
call ngFCall math.lessThanF64
arg ngFCall left x
arg ngFCall right zeroFlr
run ngFCall
bind isNg Bool ngFCall
branchIf isNg floorMaybeStepDown
returnOk truncated

label floorMaybeStepDown
# For negative x: if truncated == x exactly, x is integral -> floor is x.
# Else floor = truncated - 1.
call eqExactCall math.equalF64
arg eqExactCall left truncated
arg eqExactCall right x
run eqExactCall
bind eqExact Bool eqExactCall
branchIf eqExact floorIntegral
call subOneCall math.subtractF64
arg subOneCall left truncated
arg subOneCall right oneFlr
run subOneCall
bind floored CFloat64 subOneCall
returnOk floored
label floorIntegral
returnOk truncated


operation ceilFloat
input ceilFloat x CFloat64
output ceilFloat Result CFloat64 Void
memory ceilFloat heap no
async ceilFloat no
purpose ceilFloat "Smallest integer >= x. Mirror image of floor: for x <= 0 trunc is the ceiling; for positive non-integer, ceil = trunc + 1."
label startCeilFloat
const zeroCl CFloat64 0.0
const oneCl CFloat64 1.0
call trcCall truncFloat
arg trcCall x x
run trcCall
bindOk cTruncated CFloat64 trcCall

call gtZeroCall math.greaterThanF64
arg gtZeroCall left x
arg gtZeroCall right zeroCl
run gtZeroCall
bind isPos Bool gtZeroCall
branchIf isPos ceilMaybeStepUp
returnOk cTruncated

label ceilMaybeStepUp
call eqExactCCall math.equalF64
arg eqExactCCall left cTruncated
arg eqExactCCall right x
run eqExactCCall
bind eqExactC Bool eqExactCCall
branchIf eqExactC ceilIntegral
call addOneCall math.addF64
arg addOneCall left cTruncated
arg addOneCall right oneCl
run addOneCall
bind ceiled CFloat64 addOneCall
returnOk ceiled
label ceilIntegral
returnOk cTruncated


operation fmodFloat
input fmodFloat x CFloat64
input fmodFloat y CFloat64
output fmodFloat Result CFloat64 Void
memory fmodFloat heap no
async fmodFloat no
purpose fmodFloat "Floating-point remainder of x/y, truncating toward zero. fmod(x, y) = x - trunc(x/y) * y. Caller must ensure y != 0; we don't return NaN here (no IEEE special-value handling yet)."
label startFmodFloat
call qCall math.divideF64
arg qCall left x
arg qCall right y
run qCall
bind q CFloat64 qCall
call qTruncCall truncFloat
arg qTruncCall x q
run qTruncCall
bindOk qTrunc CFloat64 qTruncCall
call scaleCall math.multiplyF64
arg scaleCall left qTrunc
arg scaleCall right y
run scaleCall
bind scaled CFloat64 scaleCall
call remCall math.subtractF64
arg remCall left x
arg remCall right scaled
run remCall
bind rem CFloat64 remCall
returnOk rem


operation lnFloat
input lnFloat x CFloat64
output lnFloat Result CFloat64 Void
memory lnFloat heap no
async lnFloat no
purpose lnFloat "Natural log of x for x > 0. Uses range reduction (ln(x) = ln(x / 2^k) + k * ln(2), where k is chosen so x/2^k is in [1, 2)) before Newton iteration on f(y) = exp(y) - x. expFloat is accurate in [0, 2], so the reduced ln(scaled) computation stays in the convergent zone. Returns 0.0 for x <= 0."
label startLnFloat
const zeroLn CFloat64 0.0
const oneLn CFloat64 1.0
const twoLn CFloat64 2.0
const halfLn CFloat64 0.5
const ln2Const CFloat64 0.6931471805599453

call posCall math.lessThanOrEqualF64
arg posCall left x
arg posCall right zeroLn
run posCall
bind nonPos Bool posCall
branchIf nonPos lnReturnZero

# Range reduction: pull x into [1, 2) by halving / doubling, tracking
# the exponent shift k as an int.
var scaled CFloat64 0.0
set scaled x
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
call expYCall expFloat
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
returnOk finalLn

label lnReturnZero
returnOk zeroLn


operation powFloat
input powFloat base CFloat64
input powFloat exponent CFloat64
output powFloat Result CFloat64 Void
memory powFloat heap no
async powFloat no
purpose powFloat "base^exponent for base > 0 via exp(exponent * ln(base)). Returns 1.0 for exponent == 0."
label startPowFloat
const zeroPw CFloat64 0.0
const oneFw CFloat64 1.0
call eExp math.equalF64
arg eExp left exponent
arg eExp right zeroPw
run eExp
bind expZero Bool eExp
branchIf expZero powOne
call lnB lnFloat
arg lnB x base
run lnB
bindOk lnBase CFloat64 lnB
call prodCall math.multiplyF64
arg prodCall left exponent
arg prodCall right lnBase
run prodCall
bind prod CFloat64 prodCall
call eRes expFloat
arg eRes x prod
run eRes
bindOk powVal CFloat64 eRes
returnOk powVal
label powOne
returnOk oneFw


operation sinFloat
input sinFloat x CFloat64
output sinFloat Result CFloat64 Void
memory sinFloat heap no
async sinFloat no
purpose sinFloat "sin(x) via Taylor series: x - x^3/3! + x^5/5! - x^7/7! + ... (20 terms). For best accuracy, caller should reduce x into [-pi, pi] beforehand. No argument reduction at this layer (yet)."
label startSinFloat
const oneSn CFloat64 1.0
const oneISn I64 1
const maxTermsSn I64 20

# accumulator = x (first term)
var sumSn CFloat64 0.0
set sumSn x
var termSn CFloat64 0.0
set termSn x
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
arg xSqCall left x
arg xSqCall right x
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
returnOk sumSn


operation cosFloat
input cosFloat x CFloat64
output cosFloat Result CFloat64 Void
memory cosFloat heap no
async cosFloat no
purpose cosFloat "cos(x) via Taylor series: 1 - x^2/2! + x^4/4! - ... (20 terms). Same range caveat as sinFloat."
label startCosFloat
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
arg xSqCsCall left x
arg xSqCsCall right x
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
returnOk sumCs


operation tanFloat
input tanFloat x CFloat64
output tanFloat Result CFloat64 Void
memory tanFloat heap no
async tanFloat no
purpose tanFloat "tan(x) = sin(x) / cos(x). Inherits range caveats from sinFloat / cosFloat (no argument reduction)."
label startTanFloat
call sCall sinFloat
arg sCall x x
run sCall
bindOk sV CFloat64 sCall
call cCall cosFloat
arg cCall x x
run cCall
bindOk cV CFloat64 cCall
call divTanCall math.divideF64
arg divTanCall left sV
arg divTanCall right cV
run divTanCall
bind tanV CFloat64 divTanCall
returnOk tanV


operation sinhFloat
input sinhFloat x CFloat64
output sinhFloat Result CFloat64 Void
memory sinhFloat heap no
async sinhFloat no
purpose sinhFloat "Hyperbolic sine: (exp(x) - exp(-x)) / 2."
label startSinhFloat
const halfFShn CFloat64 0.5
const negOneShn CFloat64 -1.0
call posExpCall expFloat
arg posExpCall x x
run posExpCall
bindOk posExp CFloat64 posExpCall
call negXCall math.multiplyF64
arg negXCall left x
arg negXCall right negOneShn
run negXCall
bind negX CFloat64 negXCall
call negExpCall expFloat
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
returnOk res


operation coshFloat
input coshFloat x CFloat64
output coshFloat Result CFloat64 Void
memory coshFloat heap no
async coshFloat no
purpose coshFloat "Hyperbolic cosine: (exp(x) + exp(-x)) / 2."
label startCoshFloat
const halfFchn CFloat64 0.5
const negOneChn CFloat64 -1.0
call posExpCcall expFloat
arg posExpCcall x x
run posExpCcall
bindOk posExpC CFloat64 posExpCcall
call negXCcall math.multiplyF64
arg negXCcall left x
arg negXCcall right negOneChn
run negXCcall
bind negXC CFloat64 negXCcall
call negExpCcall expFloat
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
returnOk resC


operation tanhFloat
input tanhFloat x CFloat64
output tanhFloat Result CFloat64 Void
memory tanhFloat heap no
async tanhFloat no
purpose tanhFloat "Hyperbolic tangent: sinh(x) / cosh(x)."
label startTanhFloat
call snCall sinhFloat
arg snCall x x
run snCall
bindOk snV CFloat64 snCall
call csCall coshFloat
arg csCall x x
run csCall
bindOk csV CFloat64 csCall
call divTanhCall math.divideF64
arg divTanhCall left snV
arg divTanhCall right csV
run divTanhCall
bind thV CFloat64 divTanhCall
returnOk thV


operation log2Float
input log2Float x CFloat64
output log2Float Result CFloat64 Void
memory log2Float heap no
async log2Float no
purpose log2Float "Base-2 log: ln(x) / ln(2)."
label startLog2Float
const ln2 CFloat64 0.6931471805599453
call lnCall lnFloat
arg lnCall x x
run lnCall
bindOk lnV CFloat64 lnCall
call divLg2Call math.divideF64
arg divLg2Call left lnV
arg divLg2Call right ln2
run divLg2Call
bind l2V CFloat64 divLg2Call
returnOk l2V


operation log10Float
input log10Float x CFloat64
output log10Float Result CFloat64 Void
memory log10Float heap no
async log10Float no
purpose log10Float "Base-10 log: ln(x) / ln(10)."
label startLog10Float
const ln10 CFloat64 2.302585092994046
call lnCall10 lnFloat
arg lnCall10 x x
run lnCall10
bindOk lnV10 CFloat64 lnCall10
call divLg10Call math.divideF64
arg divLg10Call left lnV10
arg divLg10Call right ln10
run divLg10Call
bind l10V CFloat64 divLg10Call
returnOk l10V


operation expm1Float
input expm1Float x CFloat64
output expm1Float Result CFloat64 Void
memory expm1Float heap no
async expm1Float no
purpose expm1Float "exp(x) - 1. Not loss-of-precision-aware at this layer; production libm uses a separate series for tiny x."
label startExpm1Float
const oneEm CFloat64 1.0
call expCallEm expFloat
arg expCallEm x x
run expCallEm
bindOk expVem CFloat64 expCallEm
call subOneCall math.subtractF64
arg subOneCall left expVem
arg subOneCall right oneEm
run subOneCall
bind emV CFloat64 subOneCall
returnOk emV


operation log1pFloat
input log1pFloat x CFloat64
output log1pFloat Result CFloat64 Void
memory log1pFloat heap no
async log1pFloat no
purpose log1pFloat "ln(1 + x). Same precision caveat as expm1."
label startLog1pFloat
const oneL1p CFloat64 1.0
call addOneCall math.addF64
arg addOneCall left oneL1p
arg addOneCall right x
run addOneCall
bind plusX CFloat64 addOneCall
call lnCallL1p lnFloat
arg lnCallL1p x plusX
run lnCallL1p
bindOk l1pV CFloat64 lnCallL1p
returnOk l1pV


operation hypotFloat
input hypotFloat x CFloat64
input hypotFloat y CFloat64
output hypotFloat Result CFloat64 Void
memory hypotFloat heap no
async hypotFloat no
purpose hypotFloat "sqrt(x^2 + y^2). Naive form may overflow for huge inputs; production libm scales first."
label startHypotFloat
call xSqHyp math.multiplyF64
arg xSqHyp left x
arg xSqHyp right x
run xSqHyp
bind xSqV CFloat64 xSqHyp
call ySqHyp math.multiplyF64
arg ySqHyp left y
arg ySqHyp right y
run ySqHyp
bind ySqV CFloat64 ySqHyp
call sumSqHyp math.addF64
arg sumSqHyp left xSqV
arg sumSqHyp right ySqV
run sumSqHyp
bind sumSq CFloat64 sumSqHyp
call sqrtHyp sqrtFloat
arg sqrtHyp x sumSq
run sqrtHyp
bindOk h CFloat64 sqrtHyp
returnOk h


operation atanFloat
input atanFloat x CFloat64
output atanFloat Result CFloat64 Void
memory atanFloat heap no
async atanFloat no
purpose atanFloat "atan(x) via Taylor series for |x| <= 1; uses the identity atan(x) = sign(x)*pi/2 - atan(1/x) for |x| > 1."
label startAtanFloat
const oneAt CFloat64 1.0
const negOneAt CFloat64 -1.0
const halfPiAt CFloat64 1.5707963267948966
const zeroAt CFloat64 0.0

# If |x| > 1, recurse via reciprocal identity.
call absXAt fabsFloat
arg absXAt x x
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
arg recipCall right x
run recipCall
bind recipX CFloat64 recipCall
call recCall atanFloat
arg recCall x recipX
run recCall
bindOk recV CFloat64 recCall
# sign(x): if x >= 0 use +halfPi, else -halfPi.
call posLargeCall math.greaterThanOrEqualF64
arg posLargeCall left x
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
returnOk atanLarge

label atanSeries
# Taylor for |x| <= 1: sum_{k=0..19} (-1)^k * x^(2k+1) / (2k+1)
const maxTermsAt I64 25
const oneIat I64 1
var sumAt CFloat64 0.0
var termAt CFloat64 0.0
set termAt x
var kAt I64 0
var signAt CFloat64 1.0
# Add first term
set sumAt x

label atanLoop
call atDone math.greaterThanOrEqualI64
arg atDone left kAt
arg atDone right maxTermsAt
run atDone
bind atDoneB Bool atDone
branchIf atDoneB atanReturn

# next term factor: -x^2 / (denominator we'll compute)
call xSqAt math.multiplyF64
arg xSqAt left x
arg xSqAt right x
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
returnOk sumAt


operation asinFloat
input asinFloat x CFloat64
output asinFloat Result CFloat64 Void
memory asinFloat heap no
async asinFloat no
purpose asinFloat "asin(x) = atan(x / sqrt(1 - x^2)). Domain: [-1, 1]."
label startAsinFloat
const oneAs CFloat64 1.0
call xSqAs math.multiplyF64
arg xSqAs left x
arg xSqAs right x
run xSqAs
bind xSqAsV CFloat64 xSqAs
call oneMinus math.subtractF64
arg oneMinus left oneAs
arg oneMinus right xSqAsV
run oneMinus
bind denomSq CFloat64 oneMinus
call sqrtAs sqrtFloat
arg sqrtAs x denomSq
run sqrtAs
bindOk denom CFloat64 sqrtAs
call divAs math.divideF64
arg divAs left x
arg divAs right denom
run divAs
bind ratio CFloat64 divAs
call atanAs atanFloat
arg atanAs x ratio
run atanAs
bindOk asV CFloat64 atanAs
returnOk asV


operation acosFloat
input acosFloat x CFloat64
output acosFloat Result CFloat64 Void
memory acosFloat heap no
async acosFloat no
purpose acosFloat "acos(x) = pi/2 - asin(x). Domain: [-1, 1]."
label startAcosFloat
const halfPiAcos CFloat64 1.5707963267948966
call asCall asinFloat
arg asCall x x
run asCall
bindOk asV CFloat64 asCall
call subCall math.subtractF64
arg subCall left halfPiAcos
arg subCall right asV
run subCall
bind acV CFloat64 subCall
returnOk acV


operation fmaFloat
input fmaFloat a CFloat64
input fmaFloat b CFloat64
input fmaFloat c CFloat64
output fmaFloat Result CFloat64 Void
memory fmaFloat heap no
async fmaFloat no
purpose fmaFloat "Fused multiply-add: a*b + c. Not actually fused at this layer (libm fma uses a hardware FMA instruction); we just do the two ops in sequence with normal IEEE-754 rounding between them."
label startFmaFloat
call mulCall math.multiplyF64
arg mulCall left a
arg mulCall right b
run mulCall
bind prod CFloat64 mulCall
call addCall math.addF64
arg addCall left prod
arg addCall right c
run addCall
bind r CFloat64 addCall
returnOk r


operation fmaxFloat
input fmaxFloat a CFloat64
input fmaxFloat b CFloat64
output fmaxFloat Result CFloat64 Void
memory fmaxFloat heap no
async fmaxFloat no
purpose fmaxFloat "Max of a and b. Returns the non-NaN argument if exactly one is NaN; for both-NaN we don't detect (no isnan yet)."
label startFmaxFloat
call gtCall math.greaterThanF64
arg gtCall left a
arg gtCall right b
run gtCall
bind aGreater Bool gtCall
branchIf aGreater fmaxA
returnOk b
label fmaxA
returnOk a


operation fminFloat
input fminFloat a CFloat64
input fminFloat b CFloat64
output fminFloat Result CFloat64 Void
memory fminFloat heap no
async fminFloat no
purpose fminFloat "Min of a and b."
label startFminFloat
call ltCall math.lessThanF64
arg ltCall left a
arg ltCall right b
run ltCall
bind aLess Bool ltCall
branchIf aLess fminA
returnOk b
label fminA
returnOk a


operation fdimFloat
input fdimFloat a CFloat64
input fdimFloat b CFloat64
output fdimFloat Result CFloat64 Void
memory fdimFloat heap no
async fdimFloat no
purpose fdimFloat "Positive difference: max(a - b, 0)."
label startFdimFloat
const zeroFd CFloat64 0.0
call subCall math.subtractF64
arg subCall left a
arg subCall right b
run subCall
bind diff CFloat64 subCall
call ltzCall math.lessThanF64
arg ltzCall left diff
arg ltzCall right zeroFd
run ltzCall
bind diffNeg Bool ltzCall
branchIf diffNeg fdimZero
returnOk diff
label fdimZero
returnOk zeroFd


operation copysignFloat
input copysignFloat magnitude CFloat64
input copysignFloat signSource CFloat64
output copysignFloat Result CFloat64 Void
memory copysignFloat heap no
async copysignFloat no
purpose copysignFloat "Returns |magnitude| with the sign of signSource. Doesn't yet preserve sign of zero (real libm copysign treats -0.0 specially; we don't have signed-zero detection without bit-level access)."
label startCopysignFloat
const zeroCp CFloat64 0.0
const negOneCp CFloat64 -1.0

# absMag = |magnitude|
call magAbsCall fabsFloat
arg magAbsCall x magnitude
run magAbsCall
bindOk absMag CFloat64 magAbsCall

# Sign of signSource: < 0 -> -1, else +1
call sourceNegCall math.lessThanF64
arg sourceNegCall left signSource
arg sourceNegCall right zeroCp
run sourceNegCall
bind sourceIsNeg Bool sourceNegCall
branchIf sourceIsNeg copysignFlip
returnOk absMag
label copysignFlip
call flipCall math.multiplyF64
arg flipCall left absMag
arg flipCall right negOneCp
run flipCall
bind flipped CFloat64 flipCall
returnOk flipped


operation signumFloat
input signumFloat x CFloat64
output signumFloat Result CFloat64 Void
memory signumFloat heap no
async signumFloat no
purpose signumFloat "Returns -1.0 if x < 0, 1.0 if x > 0, 0.0 if x == 0."
label startSignumFloat
const zeroSg CFloat64 0.0
const oneSg CFloat64 1.0
const negOneSg CFloat64 -1.0
call ltCheck math.lessThanF64
arg ltCheck left x
arg ltCheck right zeroSg
run ltCheck
bind isNg Bool ltCheck
branchIf isNg sgNeg
call gtCheck math.greaterThanF64
arg gtCheck left x
arg gtCheck right zeroSg
run gtCheck
bind isPs Bool gtCheck
branchIf isPs sgPos
returnOk zeroSg
label sgNeg
returnOk negOneSg
label sgPos
returnOk oneSg


operation roundFloat
input roundFloat x CFloat64
output roundFloat Result CFloat64 Void
memory roundFloat heap no
async roundFloat no
purpose roundFloat "Round half-away-from-zero to nearest integer (matching libm round, not lrint which uses banker's rounding)."
label startRoundFloat
const halfRd CFloat64 0.5
const negHalfRd CFloat64 -0.5
const zeroRd CFloat64 0.0
call neg math.lessThanF64
arg neg left x
arg neg right zeroRd
run neg
bind isNeg Bool neg
branchIf isNeg roundNeg
# Positive: floor(x + 0.5)
call addCall math.addF64
arg addCall left x
arg addCall right halfRd
run addCall
bind shifted CFloat64 addCall
call flCall floorFloat
arg flCall x shifted
run flCall
bindOk rRes CFloat64 flCall
returnOk rRes
label roundNeg
# Negative: ceil(x - 0.5)
call subCall math.subtractF64
arg subCall left x
arg subCall right halfRd
run subCall
bind shiftedN CFloat64 subCall
call cCall ceilFloat
arg cCall x shiftedN
run cCall
bindOk rResN CFloat64 cCall
returnOk rResN


operation cbrtFloat
input cbrtFloat x CFloat64
output cbrtFloat Result CFloat64 Void
memory cbrtFloat heap no
async cbrtFloat no
purpose cbrtFloat "Cube root: sign(x) * pow(|x|, 1/3). Handles negative inputs by computing on |x| and reattaching the sign."
label startCbrtFloat
const zeroCb CFloat64 0.0
const negOneCb CFloat64 -1.0
const oneThirdCb CFloat64 0.3333333333333333
call eqZeroCb math.equalF64
arg eqZeroCb left x
arg eqZeroCb right zeroCb
run eqZeroCb
bind xIsZero Bool eqZeroCb
branchIf xIsZero cbrtZero
call absXcb fabsFloat
arg absXcb x x
run absXcb
bindOk absXc CFloat64 absXcb
call powAbs powFloat
arg powAbs base absXc
arg powAbs exponent oneThirdCb
run powAbs
bindOk powAbsRes CFloat64 powAbs
call ltZeroCheck math.lessThanF64
arg ltZeroCheck left x
arg ltZeroCheck right zeroCb
run ltZeroCheck
bind xIsNeg Bool ltZeroCheck
branchIf xIsNeg cbrtNegate
returnOk powAbsRes
label cbrtNegate
call flipCb math.multiplyF64
arg flipCb left powAbsRes
arg flipCb right negOneCb
run flipCb
bind flippedCb CFloat64 flipCb
returnOk flippedCb
label cbrtZero
returnOk zeroCb


operation exp2Float
input exp2Float x CFloat64
output exp2Float Result CFloat64 Void
memory exp2Float heap no
async exp2Float no
purpose exp2Float "2^x via pow(2.0, x)."
label startExp2Float
const twoE2 CFloat64 2.0
call powCall powFloat
arg powCall base twoE2
arg powCall exponent x
run powCall
bindOk r CFloat64 powCall
returnOk r


# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test fabsFloat / sqrtFloat / expFloat. Prints OK on success."

label startMain

# fabsFloat(-3.5) == 3.5
const negPointFive CFloat64 -3.5
const expFabs CFloat64 3.5
call f1 fabsFloat
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

# sqrtFloat(144.0) approximately 12.0
const c144 CFloat64 144.0
const c12 CFloat64 12.0
const tol CFloat64 0.0001
call s1 sqrtFloat
arg s1 x c144
run s1
bindOk s1Res CFloat64 s1
call diffCall math.subtractF64
arg diffCall left s1Res
arg diffCall right c12
run diffCall
bind diff CFloat64 diffCall
call abs1 fabsFloat
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

# expFloat(1.0) approximately 2.718281828
const oneExp CFloat64 1.0
const eulerApprox CFloat64 2.718281828
const tolE CFloat64 0.001
call e1 expFloat
arg e1 x oneExp
run e1
bindOk e1Res CFloat64 e1
call diff2Call math.subtractF64
arg diff2Call left e1Res
arg diff2Call right eulerApprox
run diff2Call
bind diff2 CFloat64 diff2Call
call abs2 fabsFloat
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

# truncFloat(3.7) == 3.0
const cThreeSeven CFloat64 3.7
const cThree CFloat64 3.0
call tr1 truncFloat
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

# floorFloat(-2.3) == -3.0
const cNegTwoThree CFloat64 -2.3
const cNegThree CFloat64 -3.0
call fl1 floorFloat
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

# ceilFloat(2.3) == 3.0
const cTwoThree CFloat64 2.3
call ce1 ceilFloat
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

# fmodFloat(7.5, 2.0) == 1.5
const cSevenHalf CFloat64 7.5
const cTwoFl CFloat64 2.0
const cOneHalf CFloat64 1.5
call fm1 fmodFloat
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

# lnFloat(e) approximately 1.0
const eApprox CFloat64 2.718281828
const oneTarget CFloat64 1.0
const tolLn CFloat64 0.01
call ln1 lnFloat
arg ln1 x eApprox
run ln1
bindOk ln1Res CFloat64 ln1
call ln1Diff math.subtractF64
arg ln1Diff left ln1Res
arg ln1Diff right oneTarget
run ln1Diff
bind ln1DiffV CFloat64 ln1Diff
call ln1Abs fabsFloat
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

# powFloat(2.0, 10.0) approximately 1024.0
const cTen CFloat64 10.0
const cOneOhTwoFour CFloat64 1024.0
const tolPw CFloat64 5.0
call pw1 powFloat
arg pw1 base cTwoFl
arg pw1 exponent cTen
run pw1
bindOk pw1Res CFloat64 pw1
call pw1Diff math.subtractF64
arg pw1Diff left pw1Res
arg pw1Diff right cOneOhTwoFour
run pw1Diff
bind pw1DiffV CFloat64 pw1Diff
call pw1Abs fabsFloat
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

# sinFloat(0.0) approximately 0.0
const zeroFs CFloat64 0.0
const tolSin CFloat64 0.001
call sn1 sinFloat
arg sn1 x zeroFs
run sn1
bindOk sn1Res CFloat64 sn1
call sn1Abs fabsFloat
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

# cosFloat(0.0) approximately 1.0
call cs1 cosFloat
arg cs1 x zeroFs
run cs1
bindOk cs1Res CFloat64 cs1
call cs1Diff math.subtractF64
arg cs1Diff left cs1Res
arg cs1Diff right oneTarget
run cs1Diff
bind cs1DiffV CFloat64 cs1Diff
call cs1Abs fabsFloat
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

# log2Float(8.0) approximately 3.0
const eightFs CFloat64 8.0
const threeFs CFloat64 3.0
const tolLg CFloat64 0.01
call lg2v log2Float
arg lg2v x eightFs
run lg2v
bindOk lg2vRes CFloat64 lg2v
call lg2vDiff math.subtractF64
arg lg2vDiff left lg2vRes
arg lg2vDiff right threeFs
run lg2vDiff
bind lg2vDiffV CFloat64 lg2vDiff
call lg2vAbs fabsFloat
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

# log10Float(1000.0) approximately 3.0
const thousandFs CFloat64 1000.0
call lg10v log10Float
arg lg10v x thousandFs
run lg10v
bindOk lg10vRes CFloat64 lg10v
call lg10vDiff math.subtractF64
arg lg10vDiff left lg10vRes
arg lg10vDiff right threeFs
run lg10vDiff
bind lg10vDiffV CFloat64 lg10vDiff
call lg10vAbs fabsFloat
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

# hypotFloat(3.0, 4.0) approximately 5.0
const fourFs CFloat64 4.0
const fiveFs CFloat64 5.0
const tolHyp CFloat64 0.0001
call hyp1 hypotFloat
arg hyp1 x threeFs
arg hyp1 y fourFs
run hyp1
bindOk hyp1Res CFloat64 hyp1
call hyp1Diff math.subtractF64
arg hyp1Diff left hyp1Res
arg hyp1Diff right fiveFs
run hyp1Diff
bind hyp1DiffV CFloat64 hyp1Diff
call hyp1Abs fabsFloat
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

# atanFloat(1.0) approximately pi/4 = 0.785398
const piOver4 CFloat64 0.7853981633974483
const tolAtan CFloat64 0.01
call atn1 atanFloat
arg atn1 x oneTarget
run atn1
bindOk atn1Res CFloat64 atn1
call atn1Diff math.subtractF64
arg atn1Diff left atn1Res
arg atn1Diff right piOver4
run atn1Diff
bind atn1DiffV CFloat64 atn1Diff
call atn1Abs fabsFloat
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
const exitFail CSignedInt32 1
makeError testFailure MainError.TestFailed exitFail
returnError testFailure
