project StdConstantsSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: math/numeric constants.
#
# C's <math.h> defines a host of M_* macros (M_PI, M_E, M_LN2, etc.).
# AgentScript exposes each as an `operation` returning a CFloat64.
#
# Operations:
#   piConstant, twoPiConstant, halfPiConstant, quarterPiConstant,
#   piSquaredConstant, eConstant, ln2Constant, ln10Constant,
#   log2EConstant, log10EConstant, sqrtTwoConstant, sqrtHalfConstant,
#   eulerMascheroniConstant, goldenRatioConstant, plankConstantSI.
# ============================================================


operation piConstant
output piConstant Result CFloat64 Void
memory piConstant heap no
async piConstant no
purpose piConstant "M_PI = 3.141592653589793."
label startPi
const v CFloat64 3.141592653589793
returnOk v


operation twoPiConstant
output twoPiConstant Result CFloat64 Void
memory twoPiConstant heap no
async twoPiConstant no
purpose twoPiConstant "M_TAU = 2*pi = 6.283185307179586."
label startTwoPi
const v CFloat64 6.283185307179586
returnOk v


operation halfPiConstant
output halfPiConstant Result CFloat64 Void
memory halfPiConstant heap no
async halfPiConstant no
purpose halfPiConstant "M_PI_2 = pi/2."
label startHalfPi
const v CFloat64 1.5707963267948966
returnOk v


operation quarterPiConstant
output quarterPiConstant Result CFloat64 Void
memory quarterPiConstant heap no
async quarterPiConstant no
purpose quarterPiConstant "M_PI_4 = pi/4."
label startQuarterPi
const v CFloat64 0.7853981633974483
returnOk v


operation piSquaredConstant
output piSquaredConstant Result CFloat64 Void
memory piSquaredConstant heap no
async piSquaredConstant no
purpose piSquaredConstant "pi^2."
label startPiSquared
const v CFloat64 9.869604401089358
returnOk v


operation eConstant
output eConstant Result CFloat64 Void
memory eConstant heap no
async eConstant no
purpose eConstant "M_E = Euler's number = 2.718281828459045."
label startE
const v CFloat64 2.718281828459045
returnOk v


operation ln2Constant
output ln2Constant Result CFloat64 Void
memory ln2Constant heap no
async ln2Constant no
purpose ln2Constant "M_LN2 = ln(2) = 0.6931471805599453."
label startLn2
const v CFloat64 0.6931471805599453
returnOk v


operation ln10Constant
output ln10Constant Result CFloat64 Void
memory ln10Constant heap no
async ln10Constant no
purpose ln10Constant "M_LN10 = ln(10) = 2.302585092994046."
label startLn10
const v CFloat64 2.302585092994046
returnOk v


operation log2EConstant
output log2EConstant Result CFloat64 Void
memory log2EConstant heap no
async log2EConstant no
purpose log2EConstant "M_LOG2E = log2(e) = 1.4426950408889634."
label startLog2E
const v CFloat64 1.4426950408889634
returnOk v


operation log10EConstant
output log10EConstant Result CFloat64 Void
memory log10EConstant heap no
async log10EConstant no
purpose log10EConstant "M_LOG10E = log10(e) = 0.4342944819032518."
label startLog10E
const v CFloat64 0.4342944819032518
returnOk v


operation sqrtTwoConstant
output sqrtTwoConstant Result CFloat64 Void
memory sqrtTwoConstant heap no
async sqrtTwoConstant no
purpose sqrtTwoConstant "M_SQRT2 = sqrt(2) = 1.4142135623730951."
label startSqrtTwo
const v CFloat64 1.4142135623730951
returnOk v


operation sqrtHalfConstant
output sqrtHalfConstant Result CFloat64 Void
memory sqrtHalfConstant heap no
async sqrtHalfConstant no
purpose sqrtHalfConstant "M_SQRT1_2 = sqrt(0.5) = 0.7071067811865476."
label startSqrtHalf
const v CFloat64 0.7071067811865476
returnOk v


operation eulerMascheroniConstant
output eulerMascheroniConstant Result CFloat64 Void
memory eulerMascheroniConstant heap no
async eulerMascheroniConstant no
purpose eulerMascheroniConstant "Euler-Mascheroni constant = 0.5772156649015329."
label startEulerMasch
const v CFloat64 0.5772156649015329
returnOk v


operation goldenRatioConstant
output goldenRatioConstant Result CFloat64 Void
memory goldenRatioConstant heap no
async goldenRatioConstant no
purpose goldenRatioConstant "(1 + sqrt(5)) / 2 = 1.618033988749895."
label startGolden
const v CFloat64 1.618033988749895
returnOk v


operation zeroFloatConstant
output zeroFloatConstant Result CFloat64 Void
memory zeroFloatConstant heap no
async zeroFloatConstant no
purpose zeroFloatConstant "0.0."
label startZeroFloat
const v CFloat64 0.0
returnOk v


operation oneFloatConstant
output oneFloatConstant Result CFloat64 Void
memory oneFloatConstant heap no
async oneFloatConstant no
purpose oneFloatConstant "1.0."
label startOneFloat
const v CFloat64 1.0
returnOk v


operation negativeOneFloatConstant
output negativeOneFloatConstant Result CFloat64 Void
memory negativeOneFloatConstant heap no
async negativeOneFloatConstant no
purpose negativeOneFloatConstant "-1.0."
label startNegOneFloat
const v CFloat64 -1.0
returnOk v


# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test constants. Prints OK."
label startMain

call p piConstant
run p
bindOk pV CFloat64 p
const piExpected CFloat64 3.141592653589793
call pCheck math.equalF64
arg pCheck left pV
arg pCheck right piExpected
run pCheck
bind pOk Bool pCheck
branchIf pOk pLbl
branch testFailed
label pLbl

call e eConstant
run e
bindOk eV CFloat64 e
const eExpected CFloat64 2.718281828459045
call eCheck math.equalF64
arg eCheck left eV
arg eCheck right eExpected
run eCheck
bind eOk Bool eCheck
branchIf eOk eLbl
branch testFailed
label eLbl

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
