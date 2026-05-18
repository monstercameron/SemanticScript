# ============================================================
# AGENTSCRIPT STANDARD LIBRARY TESTS: bulk memory operations
# ============================================================
#
# # rationale: companion test file for stdlib_as/memory.as. Imports
#   the memory module and exercises every operation it exports —
#   copy / move / fill / zero / compare / find / hash — including
#   boundary cases (empty buffer, not-found, overlap, determinism).
#
# # invariant: success prints "OK\n" and exits 0; assertion failures
#   surface MainError.MemorySmokeAssertionFailed; heap allocation
#   failure surfaces MainError.MemoryAllocationFailed.
#
# # pattern: this is the canonical foo.test.as form — same directory
#   as foo.as, importModule foo, project block local to the test,
#   entry console main. The implementation file stdlib_as/memory.as
#   carries no smoke main itself.

project StdMemoryTest
target console
runtime AgentRuntime 0.1
entry console main

importModule memory

error MainError
errorCase MainError MemorySmokeAssertionFailed
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
memoryStackLimit main 4096
memoryAllocationSource main allocateBufferCall
async main no
purpose main "Smoke-test copy / fill / compare / find on a heap-allocated buffer."
invariant main "Smoke fails closed: malloc failure surfaces MemoryAllocationFailed; any assertion failure surfaces MemorySmokeAssertionFailed."

label startMain
const allocSize CByteCount 16
call allocateBufferCall c.malloc
arg allocateBufferCall size allocSize
run allocateBufferCall
bind workBuffer COpaqueMemoryAddress allocateBufferCall
bindError heapAllocationError CSignedInt32 allocateBufferCall
branchIfError allocateBufferCall heapAllocationFailedHandler
defer releaseAllocateBufferCall c.free workBuffer

const upperALetterCode CSignedInt32 65
const fiveByteCount CByteCount 5
const fiveAsAscii CNullTerminatedByteString "AAAAA"
const helloLiteralForMemory CNullTerminatedByteString "hello"
const integerZeroBoundaryForMemoryLocal CSignedInt64 0

call runFillCall fillMemoryBytesWithValue
arg runFillCall byteBuffer workBuffer
arg runFillCall targetValue upperALetterCode
arg runFillCall byteCount fiveByteCount
run runFillCall
ignoreValue runFillCall CByteCount

call assertFillCompareCall compareMemoryByteRanges
arg assertFillCompareCall leftBuffer workBuffer
arg assertFillCompareCall rightBuffer fiveAsAscii
arg assertFillCompareCall byteCount fiveByteCount
run assertFillCompareCall
bind fillCompareResult CSignedInt64 assertFillCompareCall
call checkFillCompareCall math.equalI64
arg checkFillCompareCall left fillCompareResult
arg checkFillCompareCall right integerZeroBoundaryForMemoryLocal
run checkFillCompareCall
bind fillCompareOk Bool checkFillCompareCall
branchIf fillCompareOk fillCompareHolds
branch smokeAssertionFailed
label fillCompareHolds

call runCopyCall copyMemoryBytes
arg runCopyCall destinationBuffer workBuffer
arg runCopyCall sourceBuffer helloLiteralForMemory
arg runCopyCall byteCount fiveByteCount
run runCopyCall
ignoreValue runCopyCall CByteCount

call assertCopyCompareCall compareMemoryByteRanges
arg assertCopyCompareCall leftBuffer workBuffer
arg assertCopyCompareCall rightBuffer helloLiteralForMemory
arg assertCopyCompareCall byteCount fiveByteCount
run assertCopyCompareCall
bind copyCompareResult CSignedInt64 assertCopyCompareCall
call checkCopyCompareCall math.equalI64
arg checkCopyCompareCall left copyCompareResult
arg checkCopyCompareCall right integerZeroBoundaryForMemoryLocal
run checkCopyCompareCall
bind copyCompareOk Bool checkCopyCompareCall
branchIf copyCompareOk copyCompareHolds
branch smokeAssertionFailed
label copyCompareHolds

# findByteValueInMemoryRange: 'l' in "hello" at offset 2
const lowercaseLForMemory CSignedInt32 108
const expectedFindOffset CSignedInt64 2
call assertFindCall findByteValueInMemoryRange
arg assertFindCall byteBuffer workBuffer
arg assertFindCall targetValue lowercaseLForMemory
arg assertFindCall byteCount fiveByteCount
run assertFindCall
bind findResult CSignedInt64 assertFindCall
call checkFindCall math.equalI64
arg checkFindCall left findResult
arg checkFindCall right expectedFindOffset
run checkFindCall
bind findOk Bool checkFindCall
branchIf findOk findHolds
branch smokeAssertionFailed
label findHolds

# ============================================================
# Extended unit tests: covers the 3 ops the smoke previously
# omitted (moveMemoryBytesAllowOverlap, zeroMemoryBytes,
# hashMemoryBytesWithFnv1a) plus boundary / property cases.
# ============================================================

const zeroByteCountMem CByteCount 0
const helloAgainLiteral CNullTerminatedByteString "hello"
const lowercaseZForMem CSignedInt32 122

# zeroMemoryBytes: zero out the first 5 bytes of the buffer, then
# verify byte at offset 0 is 0 via findByteValueInMemoryRange.
call runZeroCall zeroMemoryBytes
arg runZeroCall byteBuffer workBuffer
arg runZeroCall byteCount fiveByteCount
run runZeroCall
ignoreValue runZeroCall CByteCount

const nullByteCodeMem CSignedInt32 0
const zeroOffset CSignedInt64 0
call findZeroCall findByteValueInMemoryRange
arg findZeroCall byteBuffer workBuffer
arg findZeroCall targetValue nullByteCodeMem
arg findZeroCall byteCount fiveByteCount
run findZeroCall
bind findZeroResult CSignedInt64 findZeroCall
call checkFindZeroCall math.equalI64
arg checkFindZeroCall left findZeroResult
arg checkFindZeroCall right zeroOffset
run checkFindZeroCall
bind findZeroOk Bool checkFindZeroCall
branchIf findZeroOk findZeroHolds
branch smokeAssertionFailed
label findZeroHolds

# Re-copy "hello" into the buffer, then test moveMemoryBytesAllowOverlap.
# After move from buffer[0..5] to buffer[2..7] (overlapping right), the
# 5-byte content at offset 2 should be "hello".
call refillCopyCall copyMemoryBytes
arg refillCopyCall destinationBuffer workBuffer
arg refillCopyCall sourceBuffer helloAgainLiteral
arg refillCopyCall byteCount fiveByteCount
run refillCopyCall
ignoreValue refillCopyCall CByteCount

# Compute destination = workBuffer + 2 via pointer arithmetic.
const twoByteOffset CByteCount 2
call advanceForMoveCall pointer.offset
arg advanceForMoveCall base workBuffer
arg advanceForMoveCall offset twoByteOffset
run advanceForMoveCall
bind moveDestPtr COpaqueMemoryAddress advanceForMoveCall

call runMoveCall moveMemoryBytesAllowOverlap
arg runMoveCall destinationBuffer moveDestPtr
arg runMoveCall sourceBuffer workBuffer
arg runMoveCall byteCount fiveByteCount
run runMoveCall
ignoreValue runMoveCall CByteCount

# After overlapping move, bytes at offset 2..7 should be "hello".
call moveCompareCall compareMemoryByteRanges
arg moveCompareCall leftBuffer moveDestPtr
arg moveCompareCall rightBuffer helloAgainLiteral
arg moveCompareCall byteCount fiveByteCount
run moveCompareCall
bind moveCompareResult CSignedInt64 moveCompareCall
call checkMoveCompareCall math.equalI64
arg checkMoveCompareCall left moveCompareResult
arg checkMoveCompareCall right integerZeroBoundaryForMemoryLocal
run checkMoveCompareCall
bind moveCompareOk Bool checkMoveCompareCall
branchIf moveCompareOk moveCompareHolds
branch smokeAssertionFailed
label moveCompareHolds

# hashMemoryBytesWithFnv1a: hash of zero-length buffer == initial offset basis.
const expectedZeroHashBasis CSignedInt64 -3750763034362895579
call hashZeroCall hashMemoryBytesWithFnv1a
arg hashZeroCall byteBuffer helloAgainLiteral
arg hashZeroCall byteCount zeroByteCountMem
run hashZeroCall
bind hashZeroResult CSignedInt64 hashZeroCall
call hashZeroCheckCall math.equalI64
arg hashZeroCheckCall left hashZeroResult
arg hashZeroCheckCall right expectedZeroHashBasis
run hashZeroCheckCall
bind hashZeroOk Bool hashZeroCheckCall
branchIf hashZeroOk hashZeroHolds
branch smokeAssertionFailed
label hashZeroHolds

# Property: hash is deterministic — same input always produces same output.
call hashFirstCall hashMemoryBytesWithFnv1a
arg hashFirstCall byteBuffer helloAgainLiteral
arg hashFirstCall byteCount fiveByteCount
run hashFirstCall
bind hashFirstResult CSignedInt64 hashFirstCall
call hashSecondCall hashMemoryBytesWithFnv1a
arg hashSecondCall byteBuffer helloAgainLiteral
arg hashSecondCall byteCount fiveByteCount
run hashSecondCall
bind hashSecondResult CSignedInt64 hashSecondCall
call hashDeterministicCheckCall math.equalI64
arg hashDeterministicCheckCall left hashFirstResult
arg hashDeterministicCheckCall right hashSecondResult
run hashDeterministicCheckCall
bind hashDeterministicOk Bool hashDeterministicCheckCall
branchIf hashDeterministicOk hashDeterministicHolds
branch smokeAssertionFailed
label hashDeterministicHolds

# Property: distinct inputs produce distinct hashes — hash("hello") != hash("world").
const worldLiteralMem CNullTerminatedByteString "world"
call hashWorldCall hashMemoryBytesWithFnv1a
arg hashWorldCall byteBuffer worldLiteralMem
arg hashWorldCall byteCount fiveByteCount
run hashWorldCall
bind hashWorldResult CSignedInt64 hashWorldCall
call hashDistinctCheckCall math.notEqualI64
arg hashDistinctCheckCall left hashFirstResult
arg hashDistinctCheckCall right hashWorldResult
run hashDistinctCheckCall
bind hashDistinctOk Bool hashDistinctCheckCall
branchIf hashDistinctOk hashDistinctHolds
branch smokeAssertionFailed
label hashDistinctHolds

# findByteValueInMemoryRange: 'z' not in "hello" -> -1
const negativeOneFindResult CSignedInt64 -1
call findNotFoundCall findByteValueInMemoryRange
arg findNotFoundCall byteBuffer helloAgainLiteral
arg findNotFoundCall targetValue lowercaseZForMem
arg findNotFoundCall byteCount fiveByteCount
run findNotFoundCall
bind findNotFoundResult CSignedInt64 findNotFoundCall
call checkFindNotFoundCall math.equalI64
arg checkFindNotFoundCall left findNotFoundResult
arg checkFindNotFoundCall right negativeOneFindResult
run checkFindNotFoundCall
bind findNotFoundOk Bool checkFindNotFoundCall
branchIf findNotFoundOk findNotFoundHolds
branch smokeAssertionFailed
label findNotFoundHolds

# Property: comparing buffer to itself returns 0
call selfCompareCall compareMemoryByteRanges
arg selfCompareCall leftBuffer helloAgainLiteral
arg selfCompareCall rightBuffer helloAgainLiteral
arg selfCompareCall byteCount fiveByteCount
run selfCompareCall
bind selfCompareResult CSignedInt64 selfCompareCall
call checkSelfCompareCall math.equalI64
arg checkSelfCompareCall left selfCompareResult
arg checkSelfCompareCall right integerZeroBoundaryForMemoryLocal
run checkSelfCompareCall
bind selfCompareOk Bool checkSelfCompareCall
branchIf selfCompareOk selfCompareHolds
branch smokeAssertionFailed
label selfCompareHolds

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
makeError memorySmokeFailure MainError.MemorySmokeAssertionFailed
returnError memorySmokeFailure

# Heap-allocation failure leg: c.malloc returned NULL. Surface the
# typed MemoryAllocationFailed variant with the raw negative status
# as the cause. The deferred c.free does not fire here because the
# defer was registered AFTER this branch's branchIfError.
label heapAllocationFailedHandler
makeError heapAllocationFailure MainError.MemoryAllocationFailed heapAllocationError
returnError heapAllocationFailure
