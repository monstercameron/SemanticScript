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
#   mathematicalPiFloat64, mathematicalTwoPiFloat64, mathematicalHalfPiFloat64, mathematicalQuarterPiFloat64,
#   mathematicalPiSquaredFloat64, mathematicalEulerNumberFloat64, naturalLogOfTwoFloat64, naturalLogOfTenFloat64,
#   logBaseTwoOfEulerNumberFloat64, logBaseTenOfEulerNumberFloat64, squareRootOfTwoFloat64, squareRootOfOneHalfFloat64,
#   eulerMascheroniFloat64, goldenRatioFloat64, plankConstantSI.
# ============================================================


operation mathematicalPiFloat64
output mathematicalPiFloat64 Result CFloat64 Void
memory mathematicalPiFloat64 heap no
async mathematicalPiFloat64 no
purpose mathematicalPiFloat64 "M_PI = 3.141592653589793."
label startPi
const v CFloat64 3.141592653589793
returnOk v


operation mathematicalTwoPiFloat64
output mathematicalTwoPiFloat64 Result CFloat64 Void
memory mathematicalTwoPiFloat64 heap no
async mathematicalTwoPiFloat64 no
purpose mathematicalTwoPiFloat64 "M_TAU = 2*pi = 6.283185307179586."
label startTwoPi
const v CFloat64 6.283185307179586
returnOk v


operation mathematicalHalfPiFloat64
output mathematicalHalfPiFloat64 Result CFloat64 Void
memory mathematicalHalfPiFloat64 heap no
async mathematicalHalfPiFloat64 no
purpose mathematicalHalfPiFloat64 "M_PI_2 = pi/2."
label startHalfPi
const v CFloat64 1.5707963267948966
returnOk v


operation mathematicalQuarterPiFloat64
output mathematicalQuarterPiFloat64 Result CFloat64 Void
memory mathematicalQuarterPiFloat64 heap no
async mathematicalQuarterPiFloat64 no
purpose mathematicalQuarterPiFloat64 "M_PI_4 = pi/4."
label startQuarterPi
const v CFloat64 0.7853981633974483
returnOk v


operation mathematicalPiSquaredFloat64
output mathematicalPiSquaredFloat64 Result CFloat64 Void
memory mathematicalPiSquaredFloat64 heap no
async mathematicalPiSquaredFloat64 no
purpose mathematicalPiSquaredFloat64 "pi^2."
label startPiSquared
const v CFloat64 9.869604401089358
returnOk v


operation mathematicalEulerNumberFloat64
output mathematicalEulerNumberFloat64 Result CFloat64 Void
memory mathematicalEulerNumberFloat64 heap no
async mathematicalEulerNumberFloat64 no
purpose mathematicalEulerNumberFloat64 "M_E = Euler's number = 2.718281828459045."
label startE
const v CFloat64 2.718281828459045
returnOk v


operation naturalLogOfTwoFloat64
output naturalLogOfTwoFloat64 Result CFloat64 Void
memory naturalLogOfTwoFloat64 heap no
async naturalLogOfTwoFloat64 no
purpose naturalLogOfTwoFloat64 "M_LN2 = ln(2) = 0.6931471805599453."
label startLn2
const v CFloat64 0.6931471805599453
returnOk v


operation naturalLogOfTenFloat64
output naturalLogOfTenFloat64 Result CFloat64 Void
memory naturalLogOfTenFloat64 heap no
async naturalLogOfTenFloat64 no
purpose naturalLogOfTenFloat64 "M_LN10 = ln(10) = 2.302585092994046."
label startLn10
const v CFloat64 2.302585092994046
returnOk v


operation logBaseTwoOfEulerNumberFloat64
output logBaseTwoOfEulerNumberFloat64 Result CFloat64 Void
memory logBaseTwoOfEulerNumberFloat64 heap no
async logBaseTwoOfEulerNumberFloat64 no
purpose logBaseTwoOfEulerNumberFloat64 "M_LOG2E = log2(e) = 1.4426950408889634."
label startLog2E
const v CFloat64 1.4426950408889634
returnOk v


operation logBaseTenOfEulerNumberFloat64
output logBaseTenOfEulerNumberFloat64 Result CFloat64 Void
memory logBaseTenOfEulerNumberFloat64 heap no
async logBaseTenOfEulerNumberFloat64 no
purpose logBaseTenOfEulerNumberFloat64 "M_LOG10E = log10(e) = 0.4342944819032518."
label startLog10E
const v CFloat64 0.4342944819032518
returnOk v


operation squareRootOfTwoFloat64
output squareRootOfTwoFloat64 Result CFloat64 Void
memory squareRootOfTwoFloat64 heap no
async squareRootOfTwoFloat64 no
purpose squareRootOfTwoFloat64 "M_SQRT2 = sqrt(2) = 1.4142135623730951."
label startSqrtTwo
const v CFloat64 1.4142135623730951
returnOk v


operation squareRootOfOneHalfFloat64
output squareRootOfOneHalfFloat64 Result CFloat64 Void
memory squareRootOfOneHalfFloat64 heap no
async squareRootOfOneHalfFloat64 no
purpose squareRootOfOneHalfFloat64 "M_SQRT1_2 = sqrt(0.5) = 0.7071067811865476."
label startSqrtHalf
const v CFloat64 0.7071067811865476
returnOk v


operation eulerMascheroniFloat64
output eulerMascheroniFloat64 Result CFloat64 Void
memory eulerMascheroniFloat64 heap no
async eulerMascheroniFloat64 no
purpose eulerMascheroniFloat64 "Euler-Mascheroni constant = 0.5772156649015329."
label startEulerMasch
const v CFloat64 0.5772156649015329
returnOk v


operation goldenRatioFloat64
output goldenRatioFloat64 Result CFloat64 Void
memory goldenRatioFloat64 heap no
async goldenRatioFloat64 no
purpose goldenRatioFloat64 "(1 + sqrt(5)) / 2 = 1.618033988749895."
label startGolden
const v CFloat64 1.618033988749895
returnOk v


operation zeroFloat64
output zeroFloat64 Result CFloat64 Void
memory zeroFloat64 heap no
async zeroFloat64 no
purpose zeroFloat64 "0.0."
label startZeroFloat
const v CFloat64 0.0
returnOk v


operation oneFloat64
output oneFloat64 Result CFloat64 Void
memory oneFloat64 heap no
async oneFloat64 no
purpose oneFloat64 "1.0."
label startOneFloat
const v CFloat64 1.0
returnOk v


operation negativeOneFloat64
output negativeOneFloat64 Result CFloat64 Void
memory negativeOneFloat64 heap no
async negativeOneFloat64 no
purpose negativeOneFloat64 "-1.0."
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

call p mathematicalPiFloat64
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

call e mathematicalEulerNumberFloat64
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
