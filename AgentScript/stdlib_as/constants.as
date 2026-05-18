# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: mathematical / numeric constants
# ============================================================
#
# # rationale: C's <math.h> exposes M_PI, M_E, M_LN2, M_SQRT2, etc.
#   as preprocessor `#define`s. AgentScript has no macros, so the
#   pre-refined version exposed each constant as a zero-arg
#   operation returning `Result CFloat64 Void`. The refined surface
#   replaces every operation with a module-scope `domainLiteral`
#   (AST §2.12.5) so constants are typed compile-time values, not
#   callable operations. Every reference is constant-folded by LLVM.
#
# # invariant: every CFloat64 literal is the double-precision
#   IEEE-754 nearest representable value of the named constant.
#   Some constants (e.g. golden ratio) are mathematically irrational
#   and are approximated to 17 significant decimal digits — the
#   round-trip representation of an IEEE-754 binary64.
#
# # security: pure constants. No effects. No allocation.
#
# # timing: zero — every reference inlines.
#
# # observability: nothing to observe at runtime.

project StdConstantsSelfTest
target console
runtime AgentRuntime 0.1
entry console main

error MainError
errorCase MainError ConstantsSmokeAssertionFailed

# section constants.circle
domainLiteral mathematicalPiFloat64 CFloat64 3.141592653589793
domainLiteralSource mathematicalPiFloat64 mathematics.pi.iso80000
domainLiteralTrust mathematicalPiFloat64 trustedStaticLiteral

domainLiteral mathematicalTwoPiFloat64 CFloat64 6.283185307179586
domainLiteralSource mathematicalTwoPiFloat64 mathematics.tau.iso80000
domainLiteralTrust mathematicalTwoPiFloat64 trustedStaticLiteral

domainLiteral mathematicalHalfPiFloat64 CFloat64 1.5707963267948966
domainLiteralSource mathematicalHalfPiFloat64 mathematics.piOverTwo
domainLiteralTrust mathematicalHalfPiFloat64 trustedStaticLiteral

domainLiteral mathematicalQuarterPiFloat64 CFloat64 0.7853981633974483
domainLiteralSource mathematicalQuarterPiFloat64 mathematics.piOverFour
domainLiteralTrust mathematicalQuarterPiFloat64 trustedStaticLiteral

domainLiteral mathematicalPiSquaredFloat64 CFloat64 9.869604401089358
domainLiteralSource mathematicalPiSquaredFloat64 mathematics.piSquared
domainLiteralTrust mathematicalPiSquaredFloat64 trustedStaticLiteral

# section constants.exponential
domainLiteral mathematicalEulerNumberFloat64 CFloat64 2.718281828459045
domainLiteralSource mathematicalEulerNumberFloat64 mathematics.eulerNumber
domainLiteralTrust mathematicalEulerNumberFloat64 trustedStaticLiteral

domainLiteral naturalLogOfTwoFloat64 CFloat64 0.6931471805599453
domainLiteralSource naturalLogOfTwoFloat64 mathematics.naturalLog.two
domainLiteralTrust naturalLogOfTwoFloat64 trustedStaticLiteral

domainLiteral naturalLogOfTenFloat64 CFloat64 2.302585092994046
domainLiteralSource naturalLogOfTenFloat64 mathematics.naturalLog.ten
domainLiteralTrust naturalLogOfTenFloat64 trustedStaticLiteral

domainLiteral logBaseTwoOfEulerNumberFloat64 CFloat64 1.4426950408889634
domainLiteralSource logBaseTwoOfEulerNumberFloat64 mathematics.logBase2.eulerNumber
domainLiteralTrust logBaseTwoOfEulerNumberFloat64 trustedStaticLiteral

domainLiteral logBaseTenOfEulerNumberFloat64 CFloat64 0.4342944819032518
domainLiteralSource logBaseTenOfEulerNumberFloat64 mathematics.logBase10.eulerNumber
domainLiteralTrust logBaseTenOfEulerNumberFloat64 trustedStaticLiteral

# section constants.roots
domainLiteral squareRootOfTwoFloat64 CFloat64 1.4142135623730951
domainLiteralSource squareRootOfTwoFloat64 mathematics.squareRoot.two
domainLiteralTrust squareRootOfTwoFloat64 trustedStaticLiteral

domainLiteral squareRootOfOneHalfFloat64 CFloat64 0.7071067811865476
domainLiteralSource squareRootOfOneHalfFloat64 mathematics.squareRoot.oneHalf
domainLiteralTrust squareRootOfOneHalfFloat64 trustedStaticLiteral

# section constants.special
domainLiteral eulerMascheroniFloat64 CFloat64 0.5772156649015329
domainLiteralSource eulerMascheroniFloat64 mathematics.eulerMascheroniGamma
domainLiteralTrust eulerMascheroniFloat64 trustedStaticLiteral

domainLiteral goldenRatioFloat64 CFloat64 1.618033988749895
domainLiteralSource goldenRatioFloat64 mathematics.goldenRatio
domainLiteralTrust goldenRatioFloat64 trustedStaticLiteral

# section constants.identities
domainLiteral zeroFloat64 CFloat64 0.0
domainLiteralSource zeroFloat64 mathematics.additiveIdentity
domainLiteralTrust zeroFloat64 trustedStaticLiteral

domainLiteral oneFloat64 CFloat64 1.0
domainLiteralSource oneFloat64 mathematics.multiplicativeIdentity
domainLiteralTrust oneFloat64 trustedStaticLiteral

domainLiteral negativeOneFloat64 CFloat64 -1.0
domainLiteralSource negativeOneFloat64 mathematics.additiveInverse.one
domainLiteralTrust negativeOneFloat64 trustedStaticLiteral

# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memoryHeap main no
async main no
purpose main "Verify the headline constants round-trip to expected literals."
invariant main "Pi resolves to 3.141592653589793; Euler's number to 2.718281828459045."

label startMain

const piExpectedValue CFloat64 3.141592653589793
call checkPiCall math.equalF64
arg checkPiCall left mathematicalPiFloat64
arg checkPiCall right piExpectedValue
run checkPiCall
bind piOk Bool checkPiCall
branchIf piOk piHolds
branch smokeAssertionFailed
label piHolds

const eulerExpectedValue CFloat64 2.718281828459045
call checkEulerCall math.equalF64
arg checkEulerCall left mathematicalEulerNumberFloat64
arg checkEulerCall right eulerExpectedValue
run checkEulerCall
bind eulerOk Bool checkEulerCall
branchIf eulerOk eulerHolds
branch smokeAssertionFailed
label eulerHolds

const successMessageText CNullTerminatedByteString "OK"
call writeSuccessLineCall console.writeLine
arg writeSuccessLineCall console console
arg writeSuccessLineCall text successMessageText
run writeSuccessLineCall
ignoreOk writeSuccessLineCall Void
const exitOkCode ExitCode 0
returnOk exitOkCode

label smokeAssertionFailed
makeError constantsSmokeFailure MainError.ConstantsSmokeAssertionFailed
returnError constantsSmokeFailure
