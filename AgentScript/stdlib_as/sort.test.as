# ============================================================
# AGENTSCRIPT STANDARD LIBRARY TESTS: byte-buffer sort algorithms
# ============================================================
#
# # rationale: companion test file for stdlib_as/sort.as. Imports
#   the sort module and exercises every operation it exports —
#   bubble sort / insertion sort / sorted predicate — across the
#   happy path, the empty / single-byte trivial cases, and a
#   reverse-sorted input that needs an actual sort pass.
#
# # invariant: success prints "OK\n" and exits 0; assertion failures
#   surface MainError.SortSmokeAssertionFailed; heap allocation
#   failure surfaces MainError.MemoryAllocationFailed.
#
# # pattern: this is the canonical foo.test.as form — same directory
#   as foo.as, importModule foo, project block local to the test,
#   entry console main. The implementation file stdlib_as/sort.as
#   carries no smoke main itself.

project StdSortTest
target console
runtime AgentRuntime 0.1
entry console main

importModule sort

error MainError
errorCase MainError SortSmokeAssertionFailed
errorCase MainError ConsoleWriteFailed
errorCase MainError MemoryAllocationFailed

# section capability
# rationale: smoke-test main writes a single OK line to stdout.
capability stdoutWriteCapability console.stdout write
# Smoke-test main allocates and frees a working buffer via libc.
capability heapAllocationCapability heap allocate
capability heapFreeCapability heap free

# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
useCapability main stdoutWriteCapability
useCapability main heapAllocationCapability
useCapability main heapFreeCapability
effect main allocate heap
effect main free heap
effect main write console.stdout
memoryHeap main yes
memoryAllocationSource main allocateBufferCall
async main no
purpose main "Allocate an 8-byte buffer, fill {5,2,8,1,9}, bubble-sort, verify sorted-ascending."
invariant main "Smoke fails closed: malloc failure surfaces MemoryAllocationFailed; out-of-order result surfaces SortSmokeAssertionFailed."

label startMain

const allocationByteSize CByteCount 8
call allocateBufferCall c.malloc
arg allocateBufferCall size allocationByteSize
run allocateBufferCall
bind workBuffer COpaqueMemoryAddress allocateBufferCall
bindError allocationFailureError CSignedInt32 allocateBufferCall
branchIfError allocateBufferCall heapAllocationFailedHandler
defer releaseAllocateBufferCall c.free workBuffer

const byteFiveValue CSignedInt32 5
const byteTwoValue CSignedInt32 2
const byteEightValue CSignedInt32 8
const byteOneValue CSignedInt32 1
const byteNineValue CSignedInt32 9
const offsetZero CByteCount 0
const offsetOne CByteCount 1
const offsetTwo CByteCount 2
const offsetThree CByteCount 3
const offsetFour CByteCount 4
const totalByteLength CByteCount 5

call storeByteAtOffsetZeroCall pointer.storeByte
arg storeByteAtOffsetZeroCall buffer workBuffer
arg storeByteAtOffsetZeroCall offset offsetZero
arg storeByteAtOffsetZeroCall value byteFiveValue
run storeByteAtOffsetZeroCall
call storeByteAtOffsetOneCall pointer.storeByte
arg storeByteAtOffsetOneCall buffer workBuffer
arg storeByteAtOffsetOneCall offset offsetOne
arg storeByteAtOffsetOneCall value byteTwoValue
run storeByteAtOffsetOneCall
call storeByteAtOffsetTwoCall pointer.storeByte
arg storeByteAtOffsetTwoCall buffer workBuffer
arg storeByteAtOffsetTwoCall offset offsetTwo
arg storeByteAtOffsetTwoCall value byteEightValue
run storeByteAtOffsetTwoCall
call storeByteAtOffsetThreeCall pointer.storeByte
arg storeByteAtOffsetThreeCall buffer workBuffer
arg storeByteAtOffsetThreeCall offset offsetThree
arg storeByteAtOffsetThreeCall value byteOneValue
run storeByteAtOffsetThreeCall
call storeByteAtOffsetFourCall pointer.storeByte
arg storeByteAtOffsetFourCall buffer workBuffer
arg storeByteAtOffsetFourCall offset offsetFour
arg storeByteAtOffsetFourCall value byteNineValue
run storeByteAtOffsetFourCall

call runBubbleSortCall sortBytesWithBubbleSortInPlace
arg runBubbleSortCall byteBuffer workBuffer
arg runBubbleSortCall byteCount totalByteLength
run runBubbleSortCall
ignoreValue runBubbleSortCall CByteCount

call checkSortedCall areBytesSortedAscending
arg checkSortedCall byteBuffer workBuffer
arg checkSortedCall byteCount totalByteLength
run checkSortedCall
bind sortedAscendingResult Bool checkSortedCall
branchIf sortedAscendingResult sortedHolds
branch smokeAssertionFailed
label sortedHolds

# ============================================================
# Extended unit tests: insertion sort coverage + predicate
# boundary cases (empty buffer, single byte, reverse-sorted).
# Reuses workBuffer (already sorted by bubble sort above) plus
# fresh writes for the insertion-sort + reverse-sort scenarios.
# ============================================================

const byteSevenValue CSignedInt32 7
const byteThreeValue CSignedInt32 3
const byteFourValue CSignedInt32 4
const byteSixValue CSignedInt32 6
const emptyCount CByteCount 0
const oneCount CByteCount 1

# Predicate: empty buffer is trivially sorted (byteCount=0 returns true).
call sortedEmptyCall areBytesSortedAscending
arg sortedEmptyCall byteBuffer workBuffer
arg sortedEmptyCall byteCount emptyCount
run sortedEmptyCall
bind sortedEmptyResult Bool sortedEmptyCall
branchIf sortedEmptyResult sortedEmptyHolds
branch smokeAssertionFailed
label sortedEmptyHolds

# Predicate: single-byte buffer is trivially sorted.
call sortedSingleCall areBytesSortedAscending
arg sortedSingleCall byteBuffer workBuffer
arg sortedSingleCall byteCount oneCount
run sortedSingleCall
bind sortedSingleResult Bool sortedSingleCall
branchIf sortedSingleResult sortedSingleHolds
branch smokeAssertionFailed
label sortedSingleHolds

# Refill workBuffer with reverse-sorted {9,7,6,4,3} and verify the
# predicate correctly returns FALSE.
call refillReverseAtZeroCall pointer.storeByte
arg refillReverseAtZeroCall buffer workBuffer
arg refillReverseAtZeroCall offset offsetZero
arg refillReverseAtZeroCall value byteNineValue
run refillReverseAtZeroCall
call refillReverseAtOneCall pointer.storeByte
arg refillReverseAtOneCall buffer workBuffer
arg refillReverseAtOneCall offset offsetOne
arg refillReverseAtOneCall value byteSevenValue
run refillReverseAtOneCall
call refillReverseAtTwoCall pointer.storeByte
arg refillReverseAtTwoCall buffer workBuffer
arg refillReverseAtTwoCall offset offsetTwo
arg refillReverseAtTwoCall value byteSixValue
run refillReverseAtTwoCall
call refillReverseAtThreeCall pointer.storeByte
arg refillReverseAtThreeCall buffer workBuffer
arg refillReverseAtThreeCall offset offsetThree
arg refillReverseAtThreeCall value byteFourValue
run refillReverseAtThreeCall
call refillReverseAtFourCall pointer.storeByte
arg refillReverseAtFourCall buffer workBuffer
arg refillReverseAtFourCall offset offsetFour
arg refillReverseAtFourCall value byteThreeValue
run refillReverseAtFourCall

# Predicate on reverse-sorted should return false.
call sortedReverseCall areBytesSortedAscending
arg sortedReverseCall byteBuffer workBuffer
arg sortedReverseCall byteCount totalByteLength
run sortedReverseCall
bind sortedReverseResult Bool sortedReverseCall
branchIf sortedReverseResult smokeAssertionFailed
# fell through: false as expected
branch reverseDetected
label reverseDetected

# Now insertion-sort the reverse-sorted buffer and verify it becomes ascending.
call runInsertionSortCall sortBytesWithInsertionSortInPlace
arg runInsertionSortCall byteBuffer workBuffer
arg runInsertionSortCall byteCount totalByteLength
run runInsertionSortCall
ignoreValue runInsertionSortCall CByteCount

call checkInsertionSortedCall areBytesSortedAscending
arg checkInsertionSortedCall byteBuffer workBuffer
arg checkInsertionSortedCall byteCount totalByteLength
run checkInsertionSortedCall
bind insertionSortedResult Bool checkInsertionSortedCall
branchIf insertionSortedResult insertionSortedHolds
branch smokeAssertionFailed
label insertionSortedHolds

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
makeError sortSmokeFailure MainError.SortSmokeAssertionFailed
returnError sortSmokeFailure

# Heap-allocation failure leg: c.malloc returned NULL. We surface
# the raw negative status as the cause attached to the typed
# MainError.MemoryAllocationFailed variant.
label heapAllocationFailedHandler
makeError heapAllocationFailure MainError.MemoryAllocationFailed allocationFailureError
returnError heapAllocationFailure
