# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: byte-buffer array helpers
# ============================================================
#
# # rationale: scans and in-place mutations over byte buffers.
#   The refined surface treats predicates as Bool (does the
#   buffer contain a byte? returns Bool, not 0/1) and lifts the
#   total scans (sum / min / max / count / reverse) out of the
#   Result wrapper. Byte normalization through (raw + 256) % 256
#   stays — pointer.loadByte sign-extends so this is needed for
#   "unsigned byte" semantics.
#
# # invariant: every operation reads at most `byteCount` bytes
#   from byteBuffer. The caller is responsible for ensuring
#   that range is in-bounds — there is no capacity argument or
#   bounds enforcement here.
#
# # security: all operations are read-only except
#   reverseBytesInBufferInPlace, which both reads and writes.
#   Out-of-bounds bytes are undefined behavior; the caller's
#   byteCount must match the actual allocation.
#
# # timing: every operation is O(byteCount). No allocation.
#
# # observability: no logs; consumers wrap when needed.

project StdArraySelfTest
target console
runtime AgentRuntime 0.1
entry console main

error MainError
errorCase MainError ArraySmokeAssertionFailed
errorCase MainError ConsoleWriteFailed
errorCase MainError MemoryAllocationFailed

# section capability
# rationale: smoke-test main writes a single OK line to stdout.
capability stdoutWriteCapability console.stdout write
capability heapAllocationCapability heap allocate
capability heapFreeCapability heap free

domainLiteral integerOneStepValue CSignedInt64 1
domainLiteralTrust integerOneStepValue trustedStaticLiteral
domainLiteral byteRoleAdjustmentValue CSignedInt64 256
domainLiteralTrust byteRoleAdjustmentValue trustedStaticLiteral
domainLiteral emptyBufferMinimumSentinel CSignedInt64 256
domainLiteralTrust emptyBufferMinimumSentinel trustedStaticLiteral
domainLiteral emptyBufferMaximumSentinel CSignedInt64 -1
domainLiteralTrust emptyBufferMaximumSentinel trustedStaticLiteral

# section array.aggregateScans

operation sumSignedByteValuesInBuffer
input sumSignedByteValuesInBuffer byteBuffer CNullTerminatedByteString
input sumSignedByteValuesInBuffer byteCount CByteCount
output sumSignedByteValuesInBuffer CSignedInt64
memoryHeap sumSignedByteValuesInBuffer no
async sumSignedByteValuesInBuffer no
purpose sumSignedByteValuesInBuffer "Returns the sum of byte values in the first byteCount bytes of byteBuffer (each byte treated as an unsigned 0..255 value)."
invariant sumSignedByteValuesInBuffer "Result is non-negative when byteCount fits within the buffer's allocation."
warning sumSignedByteValuesInBuffer "Overflows silently when byteCount * 255 exceeds CSignedInt64 (~3.6×10^16 bytes)."
guarantee sumSignedByteValuesInBuffer "Total."
label startSumSignedByteValuesInBuffer
var bufferRunningSum I64 0
var bufferReadCursor I64 0
label sumLoop
call detectSumDoneCall math.greaterThanOrEqualI64
arg detectSumDoneCall left bufferReadCursor
arg detectSumDoneCall right byteCount
run detectSumDoneCall
bind sumLoopDone Bool detectSumDoneCall
branchIf sumLoopDone sumDone
call loadByteForSumCall pointer.loadByte
arg loadByteForSumCall buffer byteBuffer
arg loadByteForSumCall offset bufferReadCursor
run loadByteForSumCall
bind rawSignExtendedByte I8 loadByteForSumCall
call shiftByteForUnsignedSumCall math.addI64
arg shiftByteForUnsignedSumCall left rawSignExtendedByte
arg shiftByteForUnsignedSumCall right byteRoleAdjustmentValue
run shiftByteForUnsignedSumCall
bind shiftedByteForSum I64 shiftByteForUnsignedSumCall
call moduloByteForUnsignedSumCall math.moduloI64
arg moduloByteForUnsignedSumCall left shiftedByteForSum
arg moduloByteForUnsignedSumCall right byteRoleAdjustmentValue
run moduloByteForUnsignedSumCall
bind unsignedByteValue I64 moduloByteForUnsignedSumCall
call addByteToRunningSumCall math.addI64
arg addByteToRunningSumCall left bufferRunningSum
arg addByteToRunningSumCall right unsignedByteValue
run addByteToRunningSumCall
bind updatedRunningSum I64 addByteToRunningSumCall
set bufferRunningSum updatedRunningSum
call advanceSumCursorCall math.addI64
arg advanceSumCursorCall left bufferReadCursor
arg advanceSumCursorCall right integerOneStepValue
run advanceSumCursorCall
bind nextSumCursorPosition I64 advanceSumCursorCall
set bufferReadCursor nextSumCursorPosition
branch sumLoop
label sumDone
returnValue bufferRunningSum

operation findMinimumSignedByteInBuffer
input findMinimumSignedByteInBuffer byteBuffer CNullTerminatedByteString
input findMinimumSignedByteInBuffer byteCount CByteCount
output findMinimumSignedByteInBuffer CSignedInt64
memoryHeap findMinimumSignedByteInBuffer no
async findMinimumSignedByteInBuffer no
purpose findMinimumSignedByteInBuffer "Returns the smallest unsigned-byte value in [0, byteCount). For an empty buffer returns 256 (an out-of-byte-range sentinel)."
invariant findMinimumSignedByteInBuffer "Result is in [0, 255] for non-empty input; 256 for empty input."
guarantee findMinimumSignedByteInBuffer "Total."
label startFindMinimumSignedByteInBuffer
var runningMinimumValue I64 256
var minSearchCursor I64 0
label minSearchLoop
call detectMinSearchDoneCall math.greaterThanOrEqualI64
arg detectMinSearchDoneCall left minSearchCursor
arg detectMinSearchDoneCall right byteCount
run detectMinSearchDoneCall
bind minSearchDone Bool detectMinSearchDoneCall
branchIf minSearchDone minSearchComplete
call loadByteForMinSearchCall pointer.loadByte
arg loadByteForMinSearchCall buffer byteBuffer
arg loadByteForMinSearchCall offset minSearchCursor
run loadByteForMinSearchCall
bind minSearchRawByte I8 loadByteForMinSearchCall
call shiftByteForMinSearchCall math.addI64
arg shiftByteForMinSearchCall left minSearchRawByte
arg shiftByteForMinSearchCall right byteRoleAdjustmentValue
run shiftByteForMinSearchCall
bind shiftedMinSearchByte I64 shiftByteForMinSearchCall
call normalizeMinSearchByteCall math.moduloI64
arg normalizeMinSearchByteCall left shiftedMinSearchByte
arg normalizeMinSearchByteCall right byteRoleAdjustmentValue
run normalizeMinSearchByteCall
bind normalizedMinSearchByte I64 normalizeMinSearchByteCall
call compareForNewMinimumCall math.lessThanI64
arg compareForNewMinimumCall left normalizedMinSearchByte
arg compareForNewMinimumCall right runningMinimumValue
run compareForNewMinimumCall
bind newMinimumDiscovered Bool compareForNewMinimumCall
branchIf newMinimumDiscovered recordNewMinimum
branch advanceMinSearchCursor
label recordNewMinimum
set runningMinimumValue normalizedMinSearchByte
branch advanceMinSearchCursor
label advanceMinSearchCursor
call advanceMinSearchCursorCall math.addI64
arg advanceMinSearchCursorCall left minSearchCursor
arg advanceMinSearchCursorCall right integerOneStepValue
run advanceMinSearchCursorCall
bind nextMinSearchCursor I64 advanceMinSearchCursorCall
set minSearchCursor nextMinSearchCursor
branch minSearchLoop
label minSearchComplete
returnValue runningMinimumValue

operation findMaximumSignedByteInBuffer
input findMaximumSignedByteInBuffer byteBuffer CNullTerminatedByteString
input findMaximumSignedByteInBuffer byteCount CByteCount
output findMaximumSignedByteInBuffer CSignedInt64
memoryHeap findMaximumSignedByteInBuffer no
async findMaximumSignedByteInBuffer no
purpose findMaximumSignedByteInBuffer "Returns the largest unsigned-byte value in [0, byteCount). For an empty buffer returns -1 (an out-of-byte-range sentinel)."
invariant findMaximumSignedByteInBuffer "Result is in [0, 255] for non-empty input; -1 for empty input."
guarantee findMaximumSignedByteInBuffer "Total."
label startFindMaximumSignedByteInBuffer
var runningMaximumValue I64 -1
var maxSearchCursor I64 0
label maxSearchLoop
call detectMaxSearchDoneCall math.greaterThanOrEqualI64
arg detectMaxSearchDoneCall left maxSearchCursor
arg detectMaxSearchDoneCall right byteCount
run detectMaxSearchDoneCall
bind maxSearchDone Bool detectMaxSearchDoneCall
branchIf maxSearchDone maxSearchComplete
call loadByteForMaxSearchCall pointer.loadByte
arg loadByteForMaxSearchCall buffer byteBuffer
arg loadByteForMaxSearchCall offset maxSearchCursor
run loadByteForMaxSearchCall
bind maxSearchRawByte I8 loadByteForMaxSearchCall
call shiftByteForMaxSearchCall math.addI64
arg shiftByteForMaxSearchCall left maxSearchRawByte
arg shiftByteForMaxSearchCall right byteRoleAdjustmentValue
run shiftByteForMaxSearchCall
bind shiftedMaxSearchByte I64 shiftByteForMaxSearchCall
call normalizeMaxSearchByteCall math.moduloI64
arg normalizeMaxSearchByteCall left shiftedMaxSearchByte
arg normalizeMaxSearchByteCall right byteRoleAdjustmentValue
run normalizeMaxSearchByteCall
bind normalizedMaxSearchByte I64 normalizeMaxSearchByteCall
call compareForNewMaximumCall math.greaterThanI64
arg compareForNewMaximumCall left normalizedMaxSearchByte
arg compareForNewMaximumCall right runningMaximumValue
run compareForNewMaximumCall
bind newMaximumDiscovered Bool compareForNewMaximumCall
branchIf newMaximumDiscovered recordNewMaximum
branch advanceMaxSearchCursor
label recordNewMaximum
set runningMaximumValue normalizedMaxSearchByte
branch advanceMaxSearchCursor
label advanceMaxSearchCursor
call advanceMaxSearchCursorCall math.addI64
arg advanceMaxSearchCursorCall left maxSearchCursor
arg advanceMaxSearchCursorCall right integerOneStepValue
run advanceMaxSearchCursorCall
bind nextMaxSearchCursor I64 advanceMaxSearchCursorCall
set maxSearchCursor nextMaxSearchCursor
branch maxSearchLoop
label maxSearchComplete
returnValue runningMaximumValue

# section array.searches

operation bufferContainsSignedByteValue
input bufferContainsSignedByteValue byteBuffer CNullTerminatedByteString
input bufferContainsSignedByteValue byteCount CByteCount
input bufferContainsSignedByteValue targetValue CSignedInt32
output bufferContainsSignedByteValue Bool
memoryHeap bufferContainsSignedByteValue no
async bufferContainsSignedByteValue no
purpose bufferContainsSignedByteValue "Returns true if any byte in [0, byteCount) of byteBuffer equals targetValue."
invariant bufferContainsSignedByteValue "Short-circuits on the first match; never scans past byteCount."
guarantee bufferContainsSignedByteValue "Total."
label startBufferContainsSignedByteValue
var containsSearchCursor I64 0
label containsSearchLoop
call detectContainsDoneCall math.greaterThanOrEqualI64
arg detectContainsDoneCall left containsSearchCursor
arg detectContainsDoneCall right byteCount
run detectContainsDoneCall
bind containsSearchDone Bool detectContainsDoneCall
branchIf containsSearchDone containsNotFound
call loadByteForContainsCall pointer.loadByte
arg loadByteForContainsCall buffer byteBuffer
arg loadByteForContainsCall offset containsSearchCursor
run loadByteForContainsCall
bind containsRawByte I8 loadByteForContainsCall
call detectContainsMatchCall math.equalI64
arg detectContainsMatchCall left containsRawByte
arg detectContainsMatchCall right targetValue
run detectContainsMatchCall
bind containsMatchFound Bool detectContainsMatchCall
branchIf containsMatchFound containsFoundTarget
call advanceContainsCursorCall math.addI64
arg advanceContainsCursorCall left containsSearchCursor
arg advanceContainsCursorCall right integerOneStepValue
run advanceContainsCursorCall
bind nextContainsCursor I64 advanceContainsCursorCall
set containsSearchCursor nextContainsCursor
branch containsSearchLoop
label containsFoundTarget
const containsTrueResult Bool true
returnValue containsTrueResult
label containsNotFound
const containsFalseResult Bool false
returnValue containsFalseResult

operation countSignedByteValueInBuffer
input countSignedByteValueInBuffer byteBuffer CNullTerminatedByteString
input countSignedByteValueInBuffer byteCount CByteCount
input countSignedByteValueInBuffer targetValue CSignedInt32
output countSignedByteValueInBuffer CSignedInt64
memoryHeap countSignedByteValueInBuffer no
async countSignedByteValueInBuffer no
purpose countSignedByteValueInBuffer "Returns the number of bytes in [0, byteCount) that equal targetValue."
invariant countSignedByteValueInBuffer "Result is in [0, byteCount]."
guarantee countSignedByteValueInBuffer "Total."
label startCountSignedByteValueInBuffer
var matchCounter I64 0
var countSearchCursor I64 0
label countSearchLoop
call detectCountDoneCall math.greaterThanOrEqualI64
arg detectCountDoneCall left countSearchCursor
arg detectCountDoneCall right byteCount
run detectCountDoneCall
bind countSearchDone Bool detectCountDoneCall
branchIf countSearchDone countSearchComplete
call loadByteForCountCall pointer.loadByte
arg loadByteForCountCall buffer byteBuffer
arg loadByteForCountCall offset countSearchCursor
run loadByteForCountCall
bind countSearchRawByte I8 loadByteForCountCall
call detectCountMatchCall math.equalI64
arg detectCountMatchCall left countSearchRawByte
arg detectCountMatchCall right targetValue
run detectCountMatchCall
bind countMatchFound Bool detectCountMatchCall
branchIf countMatchFound incrementMatchCounter
branch advanceCountCursor
label incrementMatchCounter
call incrementMatchCounterCall math.addI64
arg incrementMatchCounterCall left matchCounter
arg incrementMatchCounterCall right integerOneStepValue
run incrementMatchCounterCall
bind updatedMatchCounter I64 incrementMatchCounterCall
set matchCounter updatedMatchCounter
branch advanceCountCursor
label advanceCountCursor
call advanceCountCursorCall math.addI64
arg advanceCountCursorCall left countSearchCursor
arg advanceCountCursorCall right integerOneStepValue
run advanceCountCursorCall
bind nextCountCursor I64 advanceCountCursorCall
set countSearchCursor nextCountCursor
branch countSearchLoop
label countSearchComplete
returnValue matchCounter

# section array.mutations

operation reverseBytesInBufferInPlace
input reverseBytesInBufferInPlace byteBuffer COpaqueMemoryAddress
input reverseBytesInBufferInPlace byteCount CByteCount
output reverseBytesInBufferInPlace CByteCount
memoryHeap reverseBytesInBufferInPlace no
async reverseBytesInBufferInPlace no
purpose reverseBytesInBufferInPlace "Reverses the order of the first byteCount bytes of byteBuffer in place. Returns byteCount."
invariant reverseBytesInBufferInPlace "Self-inverse: reverseBytesInBufferInPlace(reverseBytesInBufferInPlace(buf, n), n) restores buf."
guarantee reverseBytesInBufferInPlace "Total."
label startReverseBytesInBufferInPlace
var reverseLeftCursor I64 0
var reverseRightCursor I64 0
call computeInitialRightCursorCall math.subtractI64
arg computeInitialRightCursorCall left byteCount
arg computeInitialRightCursorCall right integerOneStepValue
run computeInitialRightCursorCall
bind initialRightCursorValue I64 computeInitialRightCursorCall
set reverseRightCursor initialRightCursorValue
label reverseLoop
call detectReverseDoneCall math.greaterThanOrEqualI64
arg detectReverseDoneCall left reverseLeftCursor
arg detectReverseDoneCall right reverseRightCursor
run detectReverseDoneCall
bind reverseDone Bool detectReverseDoneCall
branchIf reverseDone reverseComplete
call loadLeftByteForReverseCall pointer.loadByte
arg loadLeftByteForReverseCall buffer byteBuffer
arg loadLeftByteForReverseCall offset reverseLeftCursor
run loadLeftByteForReverseCall
bind leftByteForReverse I8 loadLeftByteForReverseCall
call loadRightByteForReverseCall pointer.loadByte
arg loadRightByteForReverseCall buffer byteBuffer
arg loadRightByteForReverseCall offset reverseRightCursor
run loadRightByteForReverseCall
bind rightByteForReverse I8 loadRightByteForReverseCall
call storeRightAtLeftCall pointer.storeByte
arg storeRightAtLeftCall buffer byteBuffer
arg storeRightAtLeftCall offset reverseLeftCursor
arg storeRightAtLeftCall value rightByteForReverse
run storeRightAtLeftCall
call storeLeftAtRightCall pointer.storeByte
arg storeLeftAtRightCall buffer byteBuffer
arg storeLeftAtRightCall offset reverseRightCursor
arg storeLeftAtRightCall value leftByteForReverse
run storeLeftAtRightCall
call advanceLeftCursorCall math.addI64
arg advanceLeftCursorCall left reverseLeftCursor
arg advanceLeftCursorCall right integerOneStepValue
run advanceLeftCursorCall
bind nextLeftCursorPosition I64 advanceLeftCursorCall
set reverseLeftCursor nextLeftCursorPosition
call retreatRightCursorCall math.subtractI64
arg retreatRightCursorCall left reverseRightCursor
arg retreatRightCursorCall right integerOneStepValue
run retreatRightCursorCall
bind nextRightCursorPosition I64 retreatRightCursorCall
set reverseRightCursor nextRightCursorPosition
branch reverseLoop
label reverseComplete
returnValue byteCount

# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
useCapability main stdoutWriteCapability
useCapability main heapAllocationCapability
useCapability main heapFreeCapability
effect main write console.stdout
effect main allocate heap
effect main free heap
memoryHeap main yes
memoryAllocationSource main reverseAllocCall
async main no
purpose main "Smoke-test every byte-buffer array helper on the static literal 'hello'; reverseBytesInBufferInPlace is exercised against a fresh heap copy."

label startMain

const fiveByteCount CByteCount 5
const helloLiteral CNullTerminatedByteString "hello"

# sumSignedByteValuesInBuffer("hello", 5) == 532  ('h'+'e'+'l'+'l'+'o')
call assertSumCall sumSignedByteValuesInBuffer
arg assertSumCall byteBuffer helloLiteral
arg assertSumCall byteCount fiveByteCount
run assertSumCall
bind sumResult CSignedInt64 assertSumCall
const expectedSumValue CSignedInt64 532
call checkSumCall math.equalI64
arg checkSumCall left sumResult
arg checkSumCall right expectedSumValue
run checkSumCall
bind sumOk Bool checkSumCall
branchIf sumOk sumHolds
branch smokeAssertionFailed
label sumHolds

# bufferContainsSignedByteValue("hello", 5, 'l') == true
const lowercaseLCode CSignedInt32 108
call assertContainsCall bufferContainsSignedByteValue
arg assertContainsCall byteBuffer helloLiteral
arg assertContainsCall byteCount fiveByteCount
arg assertContainsCall targetValue lowercaseLCode
run assertContainsCall
bind containsResult Bool assertContainsCall
branchIf containsResult containsHolds
branch smokeAssertionFailed
label containsHolds

# countSignedByteValueInBuffer("hello", 5, 'l') == 2
call assertCountCall countSignedByteValueInBuffer
arg assertCountCall byteBuffer helloLiteral
arg assertCountCall byteCount fiveByteCount
arg assertCountCall targetValue lowercaseLCode
run assertCountCall
bind countResult CSignedInt64 assertCountCall
const expectedTwoMatches CSignedInt64 2
call checkCountCall math.equalI64
arg checkCountCall left countResult
arg checkCountCall right expectedTwoMatches
run checkCountCall
bind countOk Bool checkCountCall
branchIf countOk countHolds
branch smokeAssertionFailed
label countHolds

# ============================================================
# Extended unit tests: coverage for find-min, find-max, reverse;
# plus boundary cases for sum / count / contains (empty buffer
# and not-found scenarios).
# ============================================================

const zeroByteCount CByteCount 0
const zeroSigned CSignedInt64 0
const lowercaseHCode CSignedInt32 104
const lowercaseECode CSignedInt32 101
const lowercaseOCode CSignedInt32 111
const lowercaseZCode CSignedInt32 122

# findMinimumSignedByteInBuffer("hello", 5) == 'e' (101)
const expectedMinValue CSignedInt64 101
call findMinCall findMinimumSignedByteInBuffer
arg findMinCall byteBuffer helloLiteral
arg findMinCall byteCount fiveByteCount
run findMinCall
bind findMinResult CSignedInt64 findMinCall
call checkMinCall math.equalI64
arg checkMinCall left findMinResult
arg checkMinCall right expectedMinValue
run checkMinCall
bind findMinOk Bool checkMinCall
branchIf findMinOk findMinHolds
branch smokeAssertionFailed
label findMinHolds

# findMaximumSignedByteInBuffer("hello", 5) == 'o' (111)
const expectedMaxValue CSignedInt64 111
call findMaxCall findMaximumSignedByteInBuffer
arg findMaxCall byteBuffer helloLiteral
arg findMaxCall byteCount fiveByteCount
run findMaxCall
bind findMaxResult CSignedInt64 findMaxCall
call checkMaxCall math.equalI64
arg checkMaxCall left findMaxResult
arg checkMaxCall right expectedMaxValue
run checkMaxCall
bind findMaxOk Bool checkMaxCall
branchIf findMaxOk findMaxHolds
branch smokeAssertionFailed
label findMaxHolds

# bufferContainsSignedByteValue("hello", 5, 'z') == false (not present)
call notContainsCall bufferContainsSignedByteValue
arg notContainsCall byteBuffer helloLiteral
arg notContainsCall byteCount fiveByteCount
arg notContainsCall targetValue lowercaseZCode
run notContainsCall
bind notContainsResult Bool notContainsCall
branchIf notContainsResult smokeAssertionFailed
# fell through: false as expected, continue
branch notContainsHolds
label notContainsHolds

# countSignedByteValueInBuffer("hello", 5, 'z') == 0 (zero matches)
call zeroCountCall countSignedByteValueInBuffer
arg zeroCountCall byteBuffer helloLiteral
arg zeroCountCall byteCount fiveByteCount
arg zeroCountCall targetValue lowercaseZCode
run zeroCountCall
bind zeroCountResult CSignedInt64 zeroCountCall
call checkZeroCountCall math.equalI64
arg checkZeroCountCall left zeroCountResult
arg checkZeroCountCall right zeroSigned
run checkZeroCountCall
bind zeroCountOk Bool checkZeroCountCall
branchIf zeroCountOk zeroCountHolds
branch smokeAssertionFailed
label zeroCountHolds

# sumSignedByteValuesInBuffer("hello", 0) == 0 (empty buffer)
call emptySumCall sumSignedByteValuesInBuffer
arg emptySumCall byteBuffer helloLiteral
arg emptySumCall byteCount zeroByteCount
run emptySumCall
bind emptySumResult CSignedInt64 emptySumCall
call checkEmptySumCall math.equalI64
arg checkEmptySumCall left emptySumResult
arg checkEmptySumCall right zeroSigned
run checkEmptySumCall
bind emptySumOk Bool checkEmptySumCall
branchIf emptySumOk emptySumHolds
branch smokeAssertionFailed
label emptySumHolds

# reverseBytesInBufferInPlace: copy "hello" to a heap buffer, reverse,
# then verify by reading individual bytes (first should be 'o', last 'h').
const reverseAllocByteSize CByteCount 5
call reverseAllocCall c.malloc
arg reverseAllocCall size reverseAllocByteSize
run reverseAllocCall
bind reverseBuffer COpaqueMemoryAddress reverseAllocCall
bindError reverseAllocError CSignedInt32 reverseAllocCall
branchIfError reverseAllocCall heapAllocationFailedHandler
defer releaseReverseAllocCall c.free reverseBuffer

# Copy 'h','e','l','l','o' into the heap buffer at offsets 0..4.
const offsetZero CByteCount 0
const offsetOne CByteCount 1
const offsetTwo CByteCount 2
const offsetThree CByteCount 3
const offsetFour CByteCount 4
call storeH pointer.storeByte
arg storeH buffer reverseBuffer
arg storeH offset offsetZero
arg storeH value lowercaseHCode
run storeH
call storeE pointer.storeByte
arg storeE buffer reverseBuffer
arg storeE offset offsetOne
arg storeE value lowercaseECode
run storeE
call storeL1 pointer.storeByte
arg storeL1 buffer reverseBuffer
arg storeL1 offset offsetTwo
arg storeL1 value lowercaseLCode
run storeL1
call storeL2 pointer.storeByte
arg storeL2 buffer reverseBuffer
arg storeL2 offset offsetThree
arg storeL2 value lowercaseLCode
run storeL2
call storeO pointer.storeByte
arg storeO buffer reverseBuffer
arg storeO offset offsetFour
arg storeO value lowercaseOCode
run storeO

# Reverse the 5 bytes in place.
call runReverseCall reverseBytesInBufferInPlace
arg runReverseCall byteBuffer reverseBuffer
arg runReverseCall byteCount reverseAllocByteSize
run runReverseCall
ignoreValue runReverseCall CByteCount

# After reverse, byte at offset 0 should be 'o' (111).
call loadFirstAfterReverseCall pointer.loadByte
arg loadFirstAfterReverseCall buffer reverseBuffer
arg loadFirstAfterReverseCall offset offsetZero
run loadFirstAfterReverseCall
bind firstByteAfterReverse I8 loadFirstAfterReverseCall
# normalize to unsigned for comparison
const twoFiveSixCount CSignedInt64 256
call shiftFirstByteCall math.addI64
arg shiftFirstByteCall left firstByteAfterReverse
arg shiftFirstByteCall right twoFiveSixCount
run shiftFirstByteCall
bind shiftedFirstByte CSignedInt64 shiftFirstByteCall
call moduloFirstByteCall math.moduloI64
arg moduloFirstByteCall left shiftedFirstByte
arg moduloFirstByteCall right twoFiveSixCount
run moduloFirstByteCall
bind firstByteUnsigned CSignedInt64 moduloFirstByteCall
call checkFirstByteCall math.equalI64
arg checkFirstByteCall left firstByteUnsigned
arg checkFirstByteCall right expectedMaxValue
run checkFirstByteCall
bind firstByteOk Bool checkFirstByteCall
branchIf firstByteOk reversedFirstHolds
branch smokeAssertionFailed
label reversedFirstHolds

# After reverse, byte at offset 4 should be 'h' (104).
call loadLastAfterReverseCall pointer.loadByte
arg loadLastAfterReverseCall buffer reverseBuffer
arg loadLastAfterReverseCall offset offsetFour
run loadLastAfterReverseCall
bind lastByteAfterReverse I8 loadLastAfterReverseCall
call shiftLastByteCall math.addI64
arg shiftLastByteCall left lastByteAfterReverse
arg shiftLastByteCall right twoFiveSixCount
run shiftLastByteCall
bind shiftedLastByte CSignedInt64 shiftLastByteCall
call moduloLastByteCall math.moduloI64
arg moduloLastByteCall left shiftedLastByte
arg moduloLastByteCall right twoFiveSixCount
run moduloLastByteCall
bind lastByteUnsigned CSignedInt64 moduloLastByteCall
const expectedHValue CSignedInt64 104
call checkLastByteCall math.equalI64
arg checkLastByteCall left lastByteUnsigned
arg checkLastByteCall right expectedHValue
run checkLastByteCall
bind lastByteOk Bool checkLastByteCall
branchIf lastByteOk reversedLastHolds
branch smokeAssertionFailed
label reversedLastHolds

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
makeError arraySmokeFailure MainError.ArraySmokeAssertionFailed
returnError arraySmokeFailure

label heapAllocationFailedHandler
makeError reverseAllocFailure MainError.MemoryAllocationFailed reverseAllocError
returnError reverseAllocFailure
