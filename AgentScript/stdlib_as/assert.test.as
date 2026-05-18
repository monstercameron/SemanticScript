# ============================================================
# AGENTSCRIPT STDLIB TESTS: assert
# ============================================================
#
# Companion smoke + extended unit tests for stdlib_as/assert.as.
# Imports the assert module and asserts every require* operation
# (Equal / NotEqual / Greater / Less / WithinRange / NotNull /
# ConditionTrue). The diagnostic writers
# (emitAssertionFailureBanner / writeAssertionByteToStandardOutput)
# are NOT exercised — they would corrupt the expected "OK\n" stdout.
#
# Pattern: stdlib_as/foo.as ships pure-module operations only;
# stdlib_as/foo.test.as carries every smoke / unit test for it.

project StdAssertTest
target console
runtime AgentRuntime 0.1
entry console main

importModule assert

error MainError
errorCase MainError AssertSmokeFailed
errorCase MainError ConsoleWriteFailed

# section capability
# rationale: smoke-test main writes a single OK line to stdout.
capability stdoutWriteCapability console.stdout write

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
purpose main "Smoke-test the typed-error assertion ports."
invariant main "Every assertion that should hold returns Ok; final exit is 0."

label startMain

# requireSignedInt64ValuesEqual(2 + 2, 4)
const twoInt CSignedInt64 2
const fourInt CSignedInt64 4
call addTwoPlusTwoCall math.addI64
arg addTwoPlusTwoCall left twoInt
arg addTwoPlusTwoCall right twoInt
run addTwoPlusTwoCall
bind twoPlusTwo I64 addTwoPlusTwoCall
call assertEqualCall requireSignedInt64ValuesEqual
arg assertEqualCall leftValue twoPlusTwo
arg assertEqualCall rightValue fourInt
run assertEqualCall
branchIfError assertEqualCall smokeAssertionFailed

# requireSignedInt64ValuesNotEqual(1, 2)
const oneInt CSignedInt64 1
call assertNotEqualCall requireSignedInt64ValuesNotEqual
arg assertNotEqualCall leftValue oneInt
arg assertNotEqualCall rightValue twoInt
run assertNotEqualCall
branchIfError assertNotEqualCall smokeAssertionFailed

# ============================================================
# Extended unit tests: covers the 5 require* ops the smoke
# previously omitted (requireConditionTrue,
# requireSignedInt64LeftGreaterThanRight,
# requireSignedInt64LeftLessThanRight,
# requireSignedInt64ValueWithinInclusiveRange,
# requireOpaquePointerNotNull). The diagnostic writers
# (emitAssertionFailureBanner / writeAssertionByteToStandardOutput)
# are NOT exercised in this smoke because they would corrupt the
# expected "OK\n" stdout — they're indirectly verified by the
# requireX failure paths.
# ============================================================

const trueBoolForAssert Bool true
const tenIntForAssert CSignedInt64 10
const fiveIntForAssert CSignedInt64 5
const zeroIntForAssert CSignedInt64 0
const helloPtrLiteral CNullTerminatedByteString "hello"

# requireConditionTrue(true) — should succeed
call assertConditionTrueCall requireConditionTrue
arg assertConditionTrueCall conditionValue trueBoolForAssert
run assertConditionTrueCall
branchIfError assertConditionTrueCall smokeAssertionFailed

# requireSignedInt64LeftGreaterThanRight(10, 5) — should succeed
call assertLeftGreaterCall requireSignedInt64LeftGreaterThanRight
arg assertLeftGreaterCall leftValue tenIntForAssert
arg assertLeftGreaterCall rightValue fiveIntForAssert
run assertLeftGreaterCall
branchIfError assertLeftGreaterCall smokeAssertionFailed

# requireSignedInt64LeftLessThanRight(5, 10) — should succeed
call assertLeftLessCall requireSignedInt64LeftLessThanRight
arg assertLeftLessCall leftValue fiveIntForAssert
arg assertLeftLessCall rightValue tenIntForAssert
run assertLeftLessCall
branchIfError assertLeftLessCall smokeAssertionFailed

# requireSignedInt64ValueWithinInclusiveRange(5, 0, 10) — should succeed
call assertWithinRangeCall requireSignedInt64ValueWithinInclusiveRange
arg assertWithinRangeCall inputValue fiveIntForAssert
arg assertWithinRangeCall lowerBound zeroIntForAssert
arg assertWithinRangeCall upperBound tenIntForAssert
run assertWithinRangeCall
branchIfError assertWithinRangeCall smokeAssertionFailed

# requireSignedInt64ValueWithinInclusiveRange boundary: lowerBound itself ok
call assertBoundaryLowerCall requireSignedInt64ValueWithinInclusiveRange
arg assertBoundaryLowerCall inputValue zeroIntForAssert
arg assertBoundaryLowerCall lowerBound zeroIntForAssert
arg assertBoundaryLowerCall upperBound tenIntForAssert
run assertBoundaryLowerCall
branchIfError assertBoundaryLowerCall smokeAssertionFailed

# requireSignedInt64ValueWithinInclusiveRange boundary: upperBound itself ok
call assertBoundaryUpperCall requireSignedInt64ValueWithinInclusiveRange
arg assertBoundaryUpperCall inputValue tenIntForAssert
arg assertBoundaryUpperCall lowerBound zeroIntForAssert
arg assertBoundaryUpperCall upperBound tenIntForAssert
run assertBoundaryUpperCall
branchIfError assertBoundaryUpperCall smokeAssertionFailed

# requireOpaquePointerNotNull on a literal string pointer — should succeed
call assertNotNullCall requireOpaquePointerNotNull
arg assertNotNullCall pointerValue helloPtrLiteral
run assertNotNullCall
branchIfError assertNotNullCall smokeAssertionFailed

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
makeError assertSmokeFailure MainError.AssertSmokeFailed
returnError assertSmokeFailure
