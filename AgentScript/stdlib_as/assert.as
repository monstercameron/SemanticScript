# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: typed assertions
# ============================================================
#
# # rationale: C's <assert.h> macro raises SIGABRT on failure with
#   no structured information. The refined surface defines a typed
#   AssertionError domain (ConditionWasFalse / ValuesWereNotEqual /
#   ValuesShouldNotMatch / OrderingViolated / OutOfRange /
#   PointerWasNull) so a failing assertion surfaces in the typed
#   error system rather than terminating the process. Callers that
#   want the abort-on-failure shape can wrap any require* op with
#   `branchIfError ... -> c.abort`.
#
# # invariant: every require* operation returns Result Void
#   AssertionError. Success path is a clean `returnOk` with no
#   side effect; failure path writes a short message via
#   writeAssertionByteToStandardOutput and returns an AssertionError
#   variant carrying the structured failure reason.
#
# # security: assertion messages are written to stdout — keep
#   sensitive values out of conditions when assertions might
#   trigger in production.
#
# # timing: each assertion is O(1) on the success path; failure
#   adds ~8 putchar calls for the "assert!\n" diagnostic.

project StdAssertSelfTest
target console
runtime AgentRuntime 0.1
entry console main

# Typed error domain for failed assertions.
error AssertionError
errorCase AssertionError ConditionWasFalse
errorCase AssertionError ValuesWereNotEqual
errorCase AssertionError ValuesShouldNotMatch
errorCase AssertionError OrderingViolated
errorCase AssertionError OutOfRange
errorCase AssertionError PointerWasNull

error MainError
errorCase MainError AssertSmokeFailed

# section assert.diagnosticBytes

operation writeAssertionByteToStandardOutput
input writeAssertionByteToStandardOutput characterCode CSignedInt32
output writeAssertionByteToStandardOutput CSignedInt32
effect writeAssertionByteToStandardOutput write console.stdout
memoryHeap writeAssertionByteToStandardOutput no
memoryStackLimit writeAssertionByteToStandardOutput 1024
async writeAssertionByteToStandardOutput no
purpose writeAssertionByteToStandardOutput "Single-byte writer wrapping c.putchar for assertion-failure diagnostics."
invariant writeAssertionByteToStandardOutput "Writes exactly one byte; returns the libc putchar return value (typically the character itself or EOF on error)."
guarantee writeAssertionByteToStandardOutput "Always returns."
label startWriteAssertionByteToStandardOutput
call libcPutcharCall c.putchar
arg libcPutcharCall c characterCode
run libcPutcharCall
bind libcPutcharResult CSignedInt32 libcPutcharCall
returnValue libcPutcharResult

# section assert.diagnosticHelpers

operation emitAssertionFailureBanner
output emitAssertionFailureBanner CSignedInt32
effect emitAssertionFailureBanner write console.stdout
memoryHeap emitAssertionFailureBanner no
memoryStackLimit emitAssertionFailureBanner 1024
async emitAssertionFailureBanner no
purpose emitAssertionFailureBanner "Emit the literal 'assert!\\n' on stdout. Internal helper used by every assertion-failure path."
invariant emitAssertionFailureBanner "Exactly eight bytes written: 'a', 's', 's', 'e', 'r', 't', '!', '\\n'."
guarantee emitAssertionFailureBanner "Always returns."
label startEmitAssertionFailureBanner
const asciiLowerA CSignedInt32 97
const asciiLowerS CSignedInt32 115
const asciiLowerE CSignedInt32 101
const asciiLowerR CSignedInt32 114
const asciiLowerT CSignedInt32 116
const asciiExclamation CSignedInt32 33
const asciiNewline CSignedInt32 10
call wA writeAssertionByteToStandardOutput
arg wA characterCode asciiLowerA
run wA
ignoreValue wA CSignedInt32
call wS1 writeAssertionByteToStandardOutput
arg wS1 characterCode asciiLowerS
run wS1
ignoreValue wS1 CSignedInt32
call wS2 writeAssertionByteToStandardOutput
arg wS2 characterCode asciiLowerS
run wS2
ignoreValue wS2 CSignedInt32
call wE writeAssertionByteToStandardOutput
arg wE characterCode asciiLowerE
run wE
ignoreValue wE CSignedInt32
call wR writeAssertionByteToStandardOutput
arg wR characterCode asciiLowerR
run wR
ignoreValue wR CSignedInt32
call wT writeAssertionByteToStandardOutput
arg wT characterCode asciiLowerT
run wT
ignoreValue wT CSignedInt32
call wEx writeAssertionByteToStandardOutput
arg wEx characterCode asciiExclamation
run wEx
ignoreValue wEx CSignedInt32
call wNl writeAssertionByteToStandardOutput
arg wNl characterCode asciiNewline
run wNl
ignoreValue wNl CSignedInt32
const bannerReturnCode CSignedInt32 0
returnValue bannerReturnCode

# section assert.predicates

operation requireConditionTrue
input requireConditionTrue conditionValue Bool
output requireConditionTrue Result CSignedInt32 AssertionError
effect requireConditionTrue write console.stdout
memoryHeap requireConditionTrue no
memoryStackLimit requireConditionTrue 1024
async requireConditionTrue no
purpose requireConditionTrue "Succeeds when conditionValue is true; emits an 'assert!\\n' banner and returns AssertionError.ConditionWasFalse otherwise."
invariant requireConditionTrue "Success returns 0; failure returns a typed AssertionError variant."
failure requireConditionTrue ConditionWasFalse "Returned when conditionValue is false."
guarantee requireConditionTrue "Total — every input produces either an Ok or an Error."
label startRequireConditionTrue
branchIf conditionValue returnAssertionOk
call emitBannerCall emitAssertionFailureBanner
run emitBannerCall
ignoreValue emitBannerCall CSignedInt32
makeError conditionFailure AssertionError.ConditionWasFalse
returnError conditionFailure
label returnAssertionOk
const assertionOkCode CSignedInt32 0
returnOk assertionOkCode

operation requireSignedInt64ValuesEqual
input requireSignedInt64ValuesEqual leftValue CSignedInt64
input requireSignedInt64ValuesEqual rightValue CSignedInt64
output requireSignedInt64ValuesEqual Result CSignedInt32 AssertionError
effect requireSignedInt64ValuesEqual write console.stdout
memoryHeap requireSignedInt64ValuesEqual no
memoryStackLimit requireSignedInt64ValuesEqual 1024
async requireSignedInt64ValuesEqual no
purpose requireSignedInt64ValuesEqual "Asserts leftValue == rightValue."
failure requireSignedInt64ValuesEqual ValuesWereNotEqual "Returned when the two CSignedInt64 inputs do not match."
guarantee requireSignedInt64ValuesEqual "Total."
label startRequireSignedInt64ValuesEqual
call detectEqualityCall math.equalI64
arg detectEqualityCall left leftValue
arg detectEqualityCall right rightValue
run detectEqualityCall
bind valuesEqual Bool detectEqualityCall
branchIf valuesEqual returnEqualityOk
call emitEqualityBannerCall emitAssertionFailureBanner
run emitEqualityBannerCall
ignoreValue emitEqualityBannerCall CSignedInt32
makeError equalityFailure AssertionError.ValuesWereNotEqual
returnError equalityFailure
label returnEqualityOk
const equalityOkCode CSignedInt32 0
returnOk equalityOkCode

operation requireSignedInt64ValuesNotEqual
input requireSignedInt64ValuesNotEqual leftValue CSignedInt64
input requireSignedInt64ValuesNotEqual rightValue CSignedInt64
output requireSignedInt64ValuesNotEqual Result CSignedInt32 AssertionError
effect requireSignedInt64ValuesNotEqual write console.stdout
memoryHeap requireSignedInt64ValuesNotEqual no
memoryStackLimit requireSignedInt64ValuesNotEqual 1024
async requireSignedInt64ValuesNotEqual no
purpose requireSignedInt64ValuesNotEqual "Asserts leftValue != rightValue."
failure requireSignedInt64ValuesNotEqual ValuesShouldNotMatch "Returned when the two CSignedInt64 inputs are equal."
guarantee requireSignedInt64ValuesNotEqual "Total."
label startRequireSignedInt64ValuesNotEqual
call detectInequalityCall math.notEqualI64
arg detectInequalityCall left leftValue
arg detectInequalityCall right rightValue
run detectInequalityCall
bind valuesDiffer Bool detectInequalityCall
branchIf valuesDiffer returnInequalityOk
call emitInequalityBannerCall emitAssertionFailureBanner
run emitInequalityBannerCall
ignoreValue emitInequalityBannerCall CSignedInt32
makeError inequalityFailure AssertionError.ValuesShouldNotMatch
returnError inequalityFailure
label returnInequalityOk
const inequalityOkCode CSignedInt32 0
returnOk inequalityOkCode

operation requireSignedInt64LeftGreaterThanRight
input requireSignedInt64LeftGreaterThanRight leftValue CSignedInt64
input requireSignedInt64LeftGreaterThanRight rightValue CSignedInt64
output requireSignedInt64LeftGreaterThanRight Result CSignedInt32 AssertionError
effect requireSignedInt64LeftGreaterThanRight write console.stdout
memoryHeap requireSignedInt64LeftGreaterThanRight no
async requireSignedInt64LeftGreaterThanRight no
purpose requireSignedInt64LeftGreaterThanRight "Asserts leftValue > rightValue (strict)."
failure requireSignedInt64LeftGreaterThanRight OrderingViolated "Returned when leftValue is not strictly greater than rightValue."
guarantee requireSignedInt64LeftGreaterThanRight "Total."
label startRequireSignedInt64LeftGreaterThanRight
call detectGreaterThanForAssertCall math.greaterThanI64
arg detectGreaterThanForAssertCall left leftValue
arg detectGreaterThanForAssertCall right rightValue
run detectGreaterThanForAssertCall
bind orderingHoldsGreater Bool detectGreaterThanForAssertCall
branchIf orderingHoldsGreater returnGreaterThanOk
call emitGreaterThanBannerCall emitAssertionFailureBanner
run emitGreaterThanBannerCall
ignoreValue emitGreaterThanBannerCall CSignedInt32
makeError greaterThanFailure AssertionError.OrderingViolated
returnError greaterThanFailure
label returnGreaterThanOk
const greaterThanOkCode CSignedInt32 0
returnOk greaterThanOkCode

operation requireSignedInt64LeftLessThanRight
input requireSignedInt64LeftLessThanRight leftValue CSignedInt64
input requireSignedInt64LeftLessThanRight rightValue CSignedInt64
output requireSignedInt64LeftLessThanRight Result CSignedInt32 AssertionError
effect requireSignedInt64LeftLessThanRight write console.stdout
memoryHeap requireSignedInt64LeftLessThanRight no
async requireSignedInt64LeftLessThanRight no
purpose requireSignedInt64LeftLessThanRight "Asserts leftValue < rightValue (strict)."
failure requireSignedInt64LeftLessThanRight OrderingViolated "Returned when leftValue is not strictly less than rightValue."
guarantee requireSignedInt64LeftLessThanRight "Total."
label startRequireSignedInt64LeftLessThanRight
call detectLessThanForAssertCall math.lessThanI64
arg detectLessThanForAssertCall left leftValue
arg detectLessThanForAssertCall right rightValue
run detectLessThanForAssertCall
bind orderingHoldsLess Bool detectLessThanForAssertCall
branchIf orderingHoldsLess returnLessThanOk
call emitLessThanBannerCall emitAssertionFailureBanner
run emitLessThanBannerCall
ignoreValue emitLessThanBannerCall CSignedInt32
makeError lessThanFailure AssertionError.OrderingViolated
returnError lessThanFailure
label returnLessThanOk
const lessThanOkCode CSignedInt32 0
returnOk lessThanOkCode

operation requireSignedInt64ValueWithinInclusiveRange
input requireSignedInt64ValueWithinInclusiveRange inputValue CSignedInt64
input requireSignedInt64ValueWithinInclusiveRange lowerBound CSignedInt64
input requireSignedInt64ValueWithinInclusiveRange upperBound CSignedInt64
output requireSignedInt64ValueWithinInclusiveRange Result CSignedInt32 AssertionError
effect requireSignedInt64ValueWithinInclusiveRange write console.stdout
memoryHeap requireSignedInt64ValueWithinInclusiveRange no
async requireSignedInt64ValueWithinInclusiveRange no
purpose requireSignedInt64ValueWithinInclusiveRange "Asserts lowerBound <= inputValue <= upperBound (inclusive on both ends)."
failure requireSignedInt64ValueWithinInclusiveRange OutOfRange "Returned when inputValue lies outside the inclusive range."
guarantee requireSignedInt64ValueWithinInclusiveRange "Total."
label startRequireSignedInt64ValueWithinInclusiveRange
call detectBelowLowerBoundCall math.lessThanI64
arg detectBelowLowerBoundCall left inputValue
arg detectBelowLowerBoundCall right lowerBound
run detectBelowLowerBoundCall
bind inputBelowLowerBound Bool detectBelowLowerBoundCall
branchIf inputBelowLowerBound raiseRangeFailure
call detectAboveUpperBoundCall math.greaterThanI64
arg detectAboveUpperBoundCall left inputValue
arg detectAboveUpperBoundCall right upperBound
run detectAboveUpperBoundCall
bind inputAboveUpperBound Bool detectAboveUpperBoundCall
branchIf inputAboveUpperBound raiseRangeFailure
const rangeOkCode CSignedInt32 0
returnOk rangeOkCode
label raiseRangeFailure
call emitRangeBannerCall emitAssertionFailureBanner
run emitRangeBannerCall
ignoreValue emitRangeBannerCall CSignedInt32
makeError rangeFailure AssertionError.OutOfRange
returnError rangeFailure

operation requireOpaquePointerNotNull
input requireOpaquePointerNotNull pointerValue COpaqueMemoryAddress
output requireOpaquePointerNotNull Result CSignedInt32 AssertionError
effect requireOpaquePointerNotNull write console.stdout
memoryHeap requireOpaquePointerNotNull no
async requireOpaquePointerNotNull no
purpose requireOpaquePointerNotNull "Asserts that pointerValue is not NULL."
failure requireOpaquePointerNotNull PointerWasNull "Returned when pointerValue is the NULL pointer."
guarantee requireOpaquePointerNotNull "Total."
label startRequireOpaquePointerNotNull
call detectPointerIsNullCall pointer.isNull
arg detectPointerIsNullCall pointer pointerValue
run detectPointerIsNullCall
bind pointerIsNull Bool detectPointerIsNullCall
branchIf pointerIsNull raisePointerNullFailure
const pointerOkCode CSignedInt32 0
returnOk pointerOkCode
label raisePointerNullFailure
call emitPointerBannerCall emitAssertionFailureBanner
run emitPointerBannerCall
ignoreValue emitPointerBannerCall CSignedInt32
makeError pointerNullFailure AssertionError.PointerWasNull
returnError pointerNullFailure

# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
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
bindOk assertEqualOkSlot CSignedInt32 assertEqualCall
bindError assertEqualErrSlot CSignedInt32 assertEqualCall
branchIfError assertEqualCall smokeAssertionFailed

# requireSignedInt64ValuesNotEqual(1, 2)
const oneInt CSignedInt64 1
call assertNotEqualCall requireSignedInt64ValuesNotEqual
arg assertNotEqualCall leftValue oneInt
arg assertNotEqualCall rightValue twoInt
run assertNotEqualCall
bindOk assertNotEqualOkSlot CSignedInt32 assertNotEqualCall
bindError assertNotEqualErrSlot CSignedInt32 assertNotEqualCall
branchIfError assertNotEqualCall smokeAssertionFailed

const successMessageText CNullTerminatedByteString "OK"
call writeSuccessLineCall console.writeLine
arg writeSuccessLineCall console console
arg writeSuccessLineCall text successMessageText
run writeSuccessLineCall
ignoreOk writeSuccessLineCall Void
const exitOkCode ExitCode 0
returnOk exitOkCode

label smokeAssertionFailed
makeError assertSmokeFailure MainError.AssertSmokeFailed
returnError assertSmokeFailure
