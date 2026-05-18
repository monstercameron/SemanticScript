# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: typed comparison helpers
# ============================================================
#
# # rationale: C's three-way comparison convention (-1 / 0 / +1) is a
#   compact convention but hides ordering meaning behind an arbitrary
#   integer. This module exposes a typed `Ordering` alias so callers
#   can refer to canonical results by name (`comparisonResultLessThan`,
#   `comparisonResultEqual`, `comparisonResultGreaterThan`) and a set
#   of Bool predicates so binary tests no longer round-trip through
#   CSignedInt32.
#
# # invariant: every operation here is total. The compareXOrdering ops
#   return exactly one of the three canonical Ordering values; the
#   isXxx predicates return Bool.
#
# # security: pure value-level computation; no effects; no allocation.
#
# # timing: every operation is O(1) — at most two LLVM comparisons
#   plus one branch.
#
# # observability: no logs or metrics. Callers wrap with their own
#   tracing when needed.
#
# Operations:
#   compareSignedInt64Ordering(leftValue, rightValue)         -> Ordering
#   areSignedInt64ValuesEqual(leftValue, rightValue)          -> Bool
#   isSignedInt64LeftLessThanRight(leftValue, rightValue)     -> Bool
#   isSignedInt64LeftLessThanOrEqualRight(left, right)        -> Bool
#   isSignedInt64LeftGreaterThanRight(leftValue, rightValue)  -> Bool
#   isSignedInt64LeftGreaterThanOrEqualRight(left, right)     -> Bool
#   compareFloat64Ordering(leftValue, rightValue)             -> Ordering
#   areFloat64ValuesWithinTolerance(left, right, tolerance)   -> Bool

project StdCompareSelfTest
target console
runtime AgentRuntime 0.1
entry console main

error MainError
errorCase MainError CompareSmokeAssertionFailed
errorCase MainError ConsoleWriteFailed

# section capability
# rationale: smoke-test main writes a single OK line to stdout.
capability stdoutWriteCapability console.stdout write

# Typed Ordering alias. Width-explicit so callers can pass results to
# C-ABI consumers when they need to; the AgentScript surface should
# prefer Bool predicates for binary tests.
type Ordering CSignedInt32
typeInvariant Ordering "Only -1, 0, or +1 are reachable values."
typeTrust Ordering trustedInternal
typeRepresentation Ordering CSignedInt32

domainLiteral comparisonResultLessThan Ordering -1
domainLiteralTrust comparisonResultLessThan trustedStaticLiteral
domainLiteral comparisonResultEqual Ordering 0
domainLiteralTrust comparisonResultEqual trustedStaticLiteral
domainLiteral comparisonResultGreaterThan Ordering 1
domainLiteralTrust comparisonResultGreaterThan trustedStaticLiteral

# section compare.signedInt64
# rationale: 3-way + binary predicates over CSignedInt64.

# ----- compareSignedInt64Ordering -----
operation compareSignedInt64Ordering
input compareSignedInt64Ordering leftValue CSignedInt64
input compareSignedInt64Ordering rightValue CSignedInt64
output compareSignedInt64Ordering Ordering
memoryHeap compareSignedInt64Ordering no
async compareSignedInt64Ordering no
purpose compareSignedInt64Ordering "Three-way ordering: comparisonResultLessThan when left<right, comparisonResultGreaterThan when left>right, comparisonResultEqual when left==right."
invariant compareSignedInt64Ordering "Trichotomy: exactly one of the three Ordering values is returned for every input pair."
invariant compareSignedInt64Ordering "Anti-symmetric: compareSignedInt64Ordering(a,b) == comparisonResultLessThan iff compareSignedInt64Ordering(b,a) == comparisonResultGreaterThan."
guarantee compareSignedInt64Ordering "Total over the CSignedInt64 domain."
label startCompareSignedInt64Ordering
call detectLeftLessThanCall math.lessThanI64
arg detectLeftLessThanCall left leftValue
arg detectLeftLessThanCall right rightValue
run detectLeftLessThanCall
bind leftIsLess Bool detectLeftLessThanCall
branchIf leftIsLess returnLessThan
call detectLeftGreaterThanCall math.greaterThanI64
arg detectLeftGreaterThanCall left leftValue
arg detectLeftGreaterThanCall right rightValue
run detectLeftGreaterThanCall
bind leftIsGreater Bool detectLeftGreaterThanCall
branchIf leftIsGreater returnGreaterThan
returnValue comparisonResultEqual
label returnLessThan
returnValue comparisonResultLessThan
label returnGreaterThan
returnValue comparisonResultGreaterThan

# ----- areSignedInt64ValuesEqual -----
operation areSignedInt64ValuesEqual
input areSignedInt64ValuesEqual leftValue CSignedInt64
input areSignedInt64ValuesEqual rightValue CSignedInt64
output areSignedInt64ValuesEqual Bool
memoryHeap areSignedInt64ValuesEqual no
async areSignedInt64ValuesEqual no
purpose areSignedInt64ValuesEqual "Returns true when leftValue and rightValue have the same CSignedInt64 bit pattern."
invariant areSignedInt64ValuesEqual "Reflexive: areSignedInt64ValuesEqual(x, x) == true for every x."
invariant areSignedInt64ValuesEqual "Symmetric: areSignedInt64ValuesEqual(a, b) == areSignedInt64ValuesEqual(b, a)."
guarantee areSignedInt64ValuesEqual "Total: defined for every (CSignedInt64, CSignedInt64) input pair."
label startAreSignedInt64ValuesEqual
call detectEqualCall math.equalI64
arg detectEqualCall left leftValue
arg detectEqualCall right rightValue
run detectEqualCall
bind valuesAreEqual Bool detectEqualCall
returnValue valuesAreEqual

# ----- isSignedInt64LeftLessThanRight -----
operation isSignedInt64LeftLessThanRight
input isSignedInt64LeftLessThanRight leftValue CSignedInt64
input isSignedInt64LeftLessThanRight rightValue CSignedInt64
output isSignedInt64LeftLessThanRight Bool
memoryHeap isSignedInt64LeftLessThanRight no
async isSignedInt64LeftLessThanRight no
purpose isSignedInt64LeftLessThanRight "Returns true when leftValue is strictly less than rightValue (signed)."
invariant isSignedInt64LeftLessThanRight "Irreflexive: isSignedInt64LeftLessThanRight(x, x) == false for every x."
guarantee isSignedInt64LeftLessThanRight "Total over the CSignedInt64 domain."
label startIsSignedInt64LeftLessThanRight
call detectLessThanCall math.lessThanI64
arg detectLessThanCall left leftValue
arg detectLessThanCall right rightValue
run detectLessThanCall
bind leftLessThanRight Bool detectLessThanCall
returnValue leftLessThanRight

# ----- isSignedInt64LeftLessThanOrEqualRight -----
operation isSignedInt64LeftLessThanOrEqualRight
input isSignedInt64LeftLessThanOrEqualRight leftValue CSignedInt64
input isSignedInt64LeftLessThanOrEqualRight rightValue CSignedInt64
output isSignedInt64LeftLessThanOrEqualRight Bool
memoryHeap isSignedInt64LeftLessThanOrEqualRight no
async isSignedInt64LeftLessThanOrEqualRight no
purpose isSignedInt64LeftLessThanOrEqualRight "Returns true when leftValue is less than or equal to rightValue (signed)."
invariant isSignedInt64LeftLessThanOrEqualRight "Reflexive: holds when leftValue == rightValue."
guarantee isSignedInt64LeftLessThanOrEqualRight "Total over the CSignedInt64 domain."
label startIsSignedInt64LeftLessThanOrEqualRight
call detectLessThanOrEqualCall math.lessThanOrEqualI64
arg detectLessThanOrEqualCall left leftValue
arg detectLessThanOrEqualCall right rightValue
run detectLessThanOrEqualCall
bind leftLessThanOrEqualRight Bool detectLessThanOrEqualCall
returnValue leftLessThanOrEqualRight

# ----- isSignedInt64LeftGreaterThanRight -----
operation isSignedInt64LeftGreaterThanRight
input isSignedInt64LeftGreaterThanRight leftValue CSignedInt64
input isSignedInt64LeftGreaterThanRight rightValue CSignedInt64
output isSignedInt64LeftGreaterThanRight Bool
memoryHeap isSignedInt64LeftGreaterThanRight no
async isSignedInt64LeftGreaterThanRight no
purpose isSignedInt64LeftGreaterThanRight "Returns true when leftValue is strictly greater than rightValue (signed)."
invariant isSignedInt64LeftGreaterThanRight "Irreflexive: isSignedInt64LeftGreaterThanRight(x, x) == false for every x."
guarantee isSignedInt64LeftGreaterThanRight "Total over the CSignedInt64 domain."
label startIsSignedInt64LeftGreaterThanRight
call detectGreaterThanCall math.greaterThanI64
arg detectGreaterThanCall left leftValue
arg detectGreaterThanCall right rightValue
run detectGreaterThanCall
bind leftGreaterThanRight Bool detectGreaterThanCall
returnValue leftGreaterThanRight

# ----- isSignedInt64LeftGreaterThanOrEqualRight -----
operation isSignedInt64LeftGreaterThanOrEqualRight
input isSignedInt64LeftGreaterThanOrEqualRight leftValue CSignedInt64
input isSignedInt64LeftGreaterThanOrEqualRight rightValue CSignedInt64
output isSignedInt64LeftGreaterThanOrEqualRight Bool
memoryHeap isSignedInt64LeftGreaterThanOrEqualRight no
async isSignedInt64LeftGreaterThanOrEqualRight no
purpose isSignedInt64LeftGreaterThanOrEqualRight "Returns true when leftValue is greater than or equal to rightValue (signed)."
invariant isSignedInt64LeftGreaterThanOrEqualRight "Reflexive: holds when leftValue == rightValue."
guarantee isSignedInt64LeftGreaterThanOrEqualRight "Total over the CSignedInt64 domain."
label startIsSignedInt64LeftGreaterThanOrEqualRight
call detectGreaterThanOrEqualCall math.greaterThanOrEqualI64
arg detectGreaterThanOrEqualCall left leftValue
arg detectGreaterThanOrEqualCall right rightValue
run detectGreaterThanOrEqualCall
bind leftGreaterThanOrEqualRight Bool detectGreaterThanOrEqualCall
returnValue leftGreaterThanOrEqualRight

# section compare.float64
# rationale: ordering + tolerance-aware equality for CFloat64.
# warning: float comparisons do not currently model IEEE-754 NaN; a
#   NaN input compares "not less, not greater, not equal" and yields
#   comparisonResultEqual via the trichotomy fallthrough. Callers that
#   need NaN-safe behavior should pre-screen with `c.isnan`.

# ----- compareFloat64Ordering -----
operation compareFloat64Ordering
input compareFloat64Ordering leftValue CFloat64
input compareFloat64Ordering rightValue CFloat64
output compareFloat64Ordering Ordering
memoryHeap compareFloat64Ordering no
async compareFloat64Ordering no
purpose compareFloat64Ordering "Three-way ordering for double-precision floats; returns Ordering."
invariant compareFloat64Ordering "Anti-symmetric for non-NaN pairs."
warning compareFloat64Ordering "NaN inputs collapse to comparisonResultEqual under the current lowering — use c.isnan upstream when NaN-safe ordering is required."
guarantee compareFloat64Ordering "Total over the non-NaN CFloat64 domain."
label startCompareFloat64Ordering
call detectFloatLessThanCall math.lessThanF64
arg detectFloatLessThanCall left leftValue
arg detectFloatLessThanCall right rightValue
run detectFloatLessThanCall
bind floatLeftLessThan Bool detectFloatLessThanCall
branchIf floatLeftLessThan returnFloatLessThan
call detectFloatGreaterThanCall math.greaterThanF64
arg detectFloatGreaterThanCall left leftValue
arg detectFloatGreaterThanCall right rightValue
run detectFloatGreaterThanCall
bind floatLeftGreaterThan Bool detectFloatGreaterThanCall
branchIf floatLeftGreaterThan returnFloatGreaterThan
returnValue comparisonResultEqual
label returnFloatLessThan
returnValue comparisonResultLessThan
label returnFloatGreaterThan
returnValue comparisonResultGreaterThan

# ----- areFloat64ValuesWithinTolerance -----
operation areFloat64ValuesWithinTolerance
input areFloat64ValuesWithinTolerance leftValue CFloat64
input areFloat64ValuesWithinTolerance rightValue CFloat64
input areFloat64ValuesWithinTolerance tolerance CFloat64
output areFloat64ValuesWithinTolerance Bool
memoryHeap areFloat64ValuesWithinTolerance no
async areFloat64ValuesWithinTolerance no
purpose areFloat64ValuesWithinTolerance "Returns true when the absolute difference between leftValue and rightValue is less than or equal to tolerance."
invariant areFloat64ValuesWithinTolerance "Symmetric: result is independent of left/right ordering."
warning areFloat64ValuesWithinTolerance "Caller is responsible for choosing a sensible tolerance; a negative tolerance always returns false."
guarantee areFloat64ValuesWithinTolerance "Total over the non-NaN CFloat64 domain."
label startAreFloat64ValuesWithinTolerance
const zeroFloat CFloat64 0.0
const negativeOneFloat CFloat64 -1.0
call computeDifferenceCall math.subtractF64
arg computeDifferenceCall left leftValue
arg computeDifferenceCall right rightValue
run computeDifferenceCall
bind rawDifference CFloat64 computeDifferenceCall
var absoluteDifferenceAccumulator CFloat64 zeroFloat
set absoluteDifferenceAccumulator rawDifference
call detectDifferenceIsNegativeCall math.lessThanF64
arg detectDifferenceIsNegativeCall left absoluteDifferenceAccumulator
arg detectDifferenceIsNegativeCall right zeroFloat
run detectDifferenceIsNegativeCall
bind differenceIsNegative Bool detectDifferenceIsNegativeCall
branchIf differenceIsNegative negateAccumulator
branch compareAgainstTolerance
label negateAccumulator
call negateDifferenceCall math.multiplyF64
arg negateDifferenceCall left absoluteDifferenceAccumulator
arg negateDifferenceCall right negativeOneFloat
run negateDifferenceCall
bind negatedDifference CFloat64 negateDifferenceCall
set absoluteDifferenceAccumulator negatedDifference
branch compareAgainstTolerance
label compareAgainstTolerance
call detectWithinToleranceCall math.lessThanOrEqualF64
arg detectWithinToleranceCall left absoluteDifferenceAccumulator
arg detectWithinToleranceCall right tolerance
run detectWithinToleranceCall
bind isWithinTolerance Bool detectWithinToleranceCall
returnValue isWithinTolerance

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
purpose main "Smoke-test the comparison ops. Prints OK and exits 0."
invariant main "All assertions pass."

label startMain
const fiveInt CSignedInt64 5
const tenInt CSignedInt64 10
const tenIntCopy CSignedInt64 10

# compareSignedInt64Ordering(5, 10) == comparisonResultLessThan (-1)
call assertCompareLessThanCall compareSignedInt64Ordering
arg assertCompareLessThanCall leftValue fiveInt
arg assertCompareLessThanCall rightValue tenInt
run assertCompareLessThanCall
bind compareLessResult Ordering assertCompareLessThanCall
const expectedNegativeOne CSignedInt32 -1
call checkCompareLessCall math.equalI64
arg checkCompareLessCall left compareLessResult
arg checkCompareLessCall right expectedNegativeOne
run checkCompareLessCall
bind compareLessOk Bool checkCompareLessCall
branchIf compareLessOk compareLessHolds
branch smokeAssertionFailed
label compareLessHolds

# isSignedInt64LeftLessThanRight(5, 10) == true
call assertIsLessThanCall isSignedInt64LeftLessThanRight
arg assertIsLessThanCall leftValue fiveInt
arg assertIsLessThanCall rightValue tenInt
run assertIsLessThanCall
bind isLessResult Bool assertIsLessThanCall
branchIf isLessResult isLessHolds
branch smokeAssertionFailed
label isLessHolds

# areSignedInt64ValuesEqual(10, 10) == true
call assertEqualsCall areSignedInt64ValuesEqual
arg assertEqualsCall leftValue tenInt
arg assertEqualsCall rightValue tenIntCopy
run assertEqualsCall
bind equalsResult Bool assertEqualsCall
branchIf equalsResult equalsHolds
branch smokeAssertionFailed
label equalsHolds

# isSignedInt64LeftGreaterThanOrEqualRight(10, 5) == true
call assertGreaterOrEqualCall isSignedInt64LeftGreaterThanOrEqualRight
arg assertGreaterOrEqualCall leftValue tenInt
arg assertGreaterOrEqualCall rightValue fiveInt
run assertGreaterOrEqualCall
bind greaterOrEqualResult Bool assertGreaterOrEqualCall
branchIf greaterOrEqualResult greaterOrEqualHolds
branch smokeAssertionFailed
label greaterOrEqualHolds

# compareFloat64Ordering(1.0, 2.0) == comparisonResultLessThan
const oneFloat CFloat64 1.0
const twoFloat CFloat64 2.0
call assertCompareFloatCall compareFloat64Ordering
arg assertCompareFloatCall leftValue oneFloat
arg assertCompareFloatCall rightValue twoFloat
run assertCompareFloatCall
bind compareFloatResult Ordering assertCompareFloatCall
call checkCompareFloatCall math.equalI64
arg checkCompareFloatCall left compareFloatResult
arg checkCompareFloatCall right expectedNegativeOne
run checkCompareFloatCall
bind compareFloatOk Bool checkCompareFloatCall
branchIf compareFloatOk compareFloatHolds
branch smokeAssertionFailed
label compareFloatHolds

# areFloat64ValuesWithinTolerance(1.0, 1.05, 0.1) == true
const smallTolerance CFloat64 0.1
const slightlyLargerFloat CFloat64 1.05
call assertToleranceCall areFloat64ValuesWithinTolerance
arg assertToleranceCall leftValue oneFloat
arg assertToleranceCall rightValue slightlyLargerFloat
arg assertToleranceCall tolerance smallTolerance
run assertToleranceCall
bind toleranceResult Bool assertToleranceCall
branchIf toleranceResult toleranceHolds
branch smokeAssertionFailed
label toleranceHolds

# ============================================================
# Extended unit tests: covers the 2 untested ops
# (isSignedInt64LeftLessThanOrEqualRight, isSignedInt64LeftGreaterThanRight)
# plus reflexive / irreflexive / inverse-ordering cases that the
# single-direction smoke above can't catch.
# ============================================================

const expectedZero CSignedInt32 0
const expectedPositiveOne CSignedInt32 1

# compareSignedInt64Ordering(10, 5) == comparisonResultGreaterThan (+1)
call cmpGreaterCall compareSignedInt64Ordering
arg cmpGreaterCall leftValue tenInt
arg cmpGreaterCall rightValue fiveInt
run cmpGreaterCall
bind cmpGreaterResult Ordering cmpGreaterCall
call cmpGreaterCheckCall math.equalI64
arg cmpGreaterCheckCall left cmpGreaterResult
arg cmpGreaterCheckCall right expectedPositiveOne
run cmpGreaterCheckCall
bind cmpGreaterOk Bool cmpGreaterCheckCall
branchIf cmpGreaterOk cmpGreaterHolds
branch smokeAssertionFailed
label cmpGreaterHolds

# compareSignedInt64Ordering(10, 10) == comparisonResultEqual (0)
call cmpEqCall compareSignedInt64Ordering
arg cmpEqCall leftValue tenInt
arg cmpEqCall rightValue tenIntCopy
run cmpEqCall
bind cmpEqResult Ordering cmpEqCall
call cmpEqCheckCall math.equalI64
arg cmpEqCheckCall left cmpEqResult
arg cmpEqCheckCall right expectedZero
run cmpEqCheckCall
bind cmpEqOk Bool cmpEqCheckCall
branchIf cmpEqOk cmpEqHolds
branch smokeAssertionFailed
label cmpEqHolds

# areSignedInt64ValuesEqual(5, 10) == false (inequality leg)
call notEqualCall areSignedInt64ValuesEqual
arg notEqualCall leftValue fiveInt
arg notEqualCall rightValue tenInt
run notEqualCall
bind notEqualResult Bool notEqualCall
branchIf notEqualResult smokeAssertionFailed
branch notEqualHolds
label notEqualHolds

# isSignedInt64LeftLessThanOrEqualRight(5, 5) == true (reflexive)
call leReflexiveCall isSignedInt64LeftLessThanOrEqualRight
arg leReflexiveCall leftValue fiveInt
arg leReflexiveCall rightValue fiveInt
run leReflexiveCall
bind leReflexiveResult Bool leReflexiveCall
branchIf leReflexiveResult leReflexiveHolds
branch smokeAssertionFailed
label leReflexiveHolds

# isSignedInt64LeftLessThanOrEqualRight(10, 5) == false
call leFalseCall isSignedInt64LeftLessThanOrEqualRight
arg leFalseCall leftValue tenInt
arg leFalseCall rightValue fiveInt
run leFalseCall
bind leFalseResult Bool leFalseCall
branchIf leFalseResult smokeAssertionFailed
branch leFalseHolds
label leFalseHolds

# isSignedInt64LeftGreaterThanRight(10, 5) == true
call gtTrueCall isSignedInt64LeftGreaterThanRight
arg gtTrueCall leftValue tenInt
arg gtTrueCall rightValue fiveInt
run gtTrueCall
bind gtTrueResult Bool gtTrueCall
branchIf gtTrueResult gtTrueHolds
branch smokeAssertionFailed
label gtTrueHolds

# isSignedInt64LeftGreaterThanRight(5, 5) == false (irreflexive)
call gtIrreflexiveCall isSignedInt64LeftGreaterThanRight
arg gtIrreflexiveCall leftValue fiveInt
arg gtIrreflexiveCall rightValue fiveInt
run gtIrreflexiveCall
bind gtIrreflexiveResult Bool gtIrreflexiveCall
branchIf gtIrreflexiveResult smokeAssertionFailed
branch gtIrreflexiveHolds
label gtIrreflexiveHolds

# isSignedInt64LeftLessThanRight(10, 5) == false (false leg)
call ltFalseCall isSignedInt64LeftLessThanRight
arg ltFalseCall leftValue tenInt
arg ltFalseCall rightValue fiveInt
run ltFalseCall
bind ltFalseResult Bool ltFalseCall
branchIf ltFalseResult smokeAssertionFailed
branch ltFalseHolds
label ltFalseHolds

# compareFloat64Ordering(2.0, 1.0) == greaterThan (inverse)
call cmpFloatGreaterCall compareFloat64Ordering
arg cmpFloatGreaterCall leftValue twoFloat
arg cmpFloatGreaterCall rightValue oneFloat
run cmpFloatGreaterCall
bind cmpFloatGreaterResult Ordering cmpFloatGreaterCall
call cmpFloatGreaterCheckCall math.equalI64
arg cmpFloatGreaterCheckCall left cmpFloatGreaterResult
arg cmpFloatGreaterCheckCall right expectedPositiveOne
run cmpFloatGreaterCheckCall
bind cmpFloatGreaterOk Bool cmpFloatGreaterCheckCall
branchIf cmpFloatGreaterOk cmpFloatGreaterHolds
branch smokeAssertionFailed
label cmpFloatGreaterHolds

# compareFloat64Ordering(1.0, 1.0) == equal
call cmpFloatEqCall compareFloat64Ordering
arg cmpFloatEqCall leftValue oneFloat
arg cmpFloatEqCall rightValue oneFloat
run cmpFloatEqCall
bind cmpFloatEqResult Ordering cmpFloatEqCall
call cmpFloatEqCheckCall math.equalI64
arg cmpFloatEqCheckCall left cmpFloatEqResult
arg cmpFloatEqCheckCall right expectedZero
run cmpFloatEqCheckCall
bind cmpFloatEqOk Bool cmpFloatEqCheckCall
branchIf cmpFloatEqOk cmpFloatEqHolds
branch smokeAssertionFailed
label cmpFloatEqHolds

# areFloat64ValuesWithinTolerance(1.0, 2.0, 0.1) == false (outside tolerance)
call tolFalseCall areFloat64ValuesWithinTolerance
arg tolFalseCall leftValue oneFloat
arg tolFalseCall rightValue twoFloat
arg tolFalseCall tolerance smallTolerance
run tolFalseCall
bind tolFalseResult Bool tolFalseCall
branchIf tolFalseResult smokeAssertionFailed
branch tolFalseHolds
label tolFalseHolds

# Symmetry: withinTolerance(1.05, 1.0, 0.1) == true (reverse args)
call tolSymCall areFloat64ValuesWithinTolerance
arg tolSymCall leftValue slightlyLargerFloat
arg tolSymCall rightValue oneFloat
arg tolSymCall tolerance smallTolerance
run tolSymCall
bind tolSymResult Bool tolSymCall
branchIf tolSymResult tolSymHolds
branch smokeAssertionFailed
label tolSymHolds

# Emit "OK\n" and exit 0.
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
makeError compareSmokeFailure MainError.CompareSmokeAssertionFailed
returnError compareSmokeFailure
