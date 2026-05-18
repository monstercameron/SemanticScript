# ============================================================
# Second stdlib import-and-use smoke (buffer/array/sort/memory tier)
# ============================================================
#
# # rationale: companion to stdlib_import_smoke.as. Where that file
#   samples the value-level tiers (logic / ordering / math / time /
#   strings), this file samples the buffer-touching tiers: array
#   scans, in-place sort, raw memory ops, deterministic random,
#   plus a representative metadata-cluster check from the constants
#   modules.
#
# # invariant: every imported buffer-touching operation must run
#   correctly on a heap allocation we manage from inside this
#   smoke. If any import didn't actually wire through, the call
#   site would fail to typecheck.
#
# # security: allocates one 8-byte scratch buffer via c.malloc,
#   exercises imported byte-array ops on it, frees it. No I/O
#   beyond writing "OK" / failure marker on stdout.
#
# # timing: dominated by the imported deterministic-random LCG
#   reseed + step (constant cost ~50 i64 ops).
#
# # observability: prints "OK\n" on full pass.

project StdlibImportSmokeBuffers
target console
runtime AgentRuntime 0.1
entry console stdlibImportSmokeBuffersMain

error MainError
errorCase MainError StdlibImportBuffersSmokeAssertionFailed

# ----- imports under test (different stochastic sample of seven modules) -----
importModule array
importModule sort
importModule memory
importModule inttypes
importModule stdlib
importModule random
importModule limits
importModule signal

operation stdlibImportSmokeBuffersMain
input stdlibImportSmokeBuffersMain console Console
output stdlibImportSmokeBuffersMain Result ExitCode MainError
effect stdlibImportSmokeBuffersMain write console.stdout
effect stdlibImportSmokeBuffersMain allocate heap
memoryHeap stdlibImportSmokeBuffersMain yes
async stdlibImportSmokeBuffersMain no
purpose stdlibImportSmokeBuffersMain "Exercise one operation from each of array, sort, memory, inttypes, stdlib, random, limits, signal — proving the buffer-and-runtime tier of stdlib_as is importable."
invariant stdlibImportSmokeBuffersMain "Every imported assertion holds; final exit 0; stdout is 'OK\\n'."

label startStdlibImportSmokeBuffersMain

# ---- array: bufferContainsSignedByteValue("hello", 5, 'l') == true ----
const helloLiteralForArrayImport CNullTerminatedByteString "hello"
const fiveByteCountForArrayImport CByteCount 5
const lowercaseLByteCodeForArrayImport CSignedInt32 108
call assertContainsLowercaseLCall bufferContainsSignedByteValue
arg assertContainsLowercaseLCall byteBuffer helloLiteralForArrayImport
arg assertContainsLowercaseLCall byteCount fiveByteCountForArrayImport
arg assertContainsLowercaseLCall targetValue lowercaseLByteCodeForArrayImport
run assertContainsLowercaseLCall
bind containsLowercaseLResult Bool assertContainsLowercaseLCall
branchIf containsLowercaseLResult containsLowercaseLHolds
branch stdlibImportBuffersAssertionFailed
label containsLowercaseLHolds

# ---- array: countSignedByteValueInBuffer("hello", 5, 'l') == 2 ----
const expectedTwoLowercaseLs CSignedInt64 2
call assertCountLowercaseLCall countSignedByteValueInBuffer
arg assertCountLowercaseLCall byteBuffer helloLiteralForArrayImport
arg assertCountLowercaseLCall byteCount fiveByteCountForArrayImport
arg assertCountLowercaseLCall targetValue lowercaseLByteCodeForArrayImport
run assertCountLowercaseLCall
bind countLowercaseLResult CSignedInt64 assertCountLowercaseLCall
call checkCountLowercaseLCall math.equalI64
arg checkCountLowercaseLCall left countLowercaseLResult
arg checkCountLowercaseLCall right expectedTwoLowercaseLs
run checkCountLowercaseLCall
bind countLowercaseLOk Bool checkCountLowercaseLCall
branchIf countLowercaseLOk countLowercaseLHolds
branch stdlibImportBuffersAssertionFailed
label countLowercaseLHolds

# ---- memory + sort: allocate buffer, fill with {5,2,8,1,9}, bubble-sort, verify ascending ----
const eightBytesAllocImport CByteCount 8
call allocateSortBufferImport c.malloc
arg allocateSortBufferImport size eightBytesAllocImport
run allocateSortBufferImport
bind sortBufferImport COpaqueMemoryAddress allocateSortBufferImport

const byteFiveLiteralImport CSignedInt32 5
const byteTwoLiteralImport CSignedInt32 2
const byteEightLiteralImport CSignedInt32 8
const byteOneLiteralImport CSignedInt32 1
const byteNineLiteralImport CSignedInt32 9
const offsetZeroByte CByteCount 0
const offsetOneByte CByteCount 1
const offsetTwoByte CByteCount 2
const offsetThreeByte CByteCount 3
const offsetFourByte CByteCount 4
const totalSortLength CByteCount 5

call storeByteZeroForSortImport pointer.storeByte
arg storeByteZeroForSortImport buffer sortBufferImport
arg storeByteZeroForSortImport offset offsetZeroByte
arg storeByteZeroForSortImport value byteFiveLiteralImport
run storeByteZeroForSortImport
call storeByteOneForSortImport pointer.storeByte
arg storeByteOneForSortImport buffer sortBufferImport
arg storeByteOneForSortImport offset offsetOneByte
arg storeByteOneForSortImport value byteTwoLiteralImport
run storeByteOneForSortImport
call storeByteTwoForSortImport pointer.storeByte
arg storeByteTwoForSortImport buffer sortBufferImport
arg storeByteTwoForSortImport offset offsetTwoByte
arg storeByteTwoForSortImport value byteEightLiteralImport
run storeByteTwoForSortImport
call storeByteThreeForSortImport pointer.storeByte
arg storeByteThreeForSortImport buffer sortBufferImport
arg storeByteThreeForSortImport offset offsetThreeByte
arg storeByteThreeForSortImport value byteOneLiteralImport
run storeByteThreeForSortImport
call storeByteFourForSortImport pointer.storeByte
arg storeByteFourForSortImport buffer sortBufferImport
arg storeByteFourForSortImport offset offsetFourByte
arg storeByteFourForSortImport value byteNineLiteralImport
run storeByteFourForSortImport

call runImportedBubbleSortCall sortBytesWithBubbleSortInPlace
arg runImportedBubbleSortCall byteBuffer sortBufferImport
arg runImportedBubbleSortCall byteCount totalSortLength
run runImportedBubbleSortCall
ignoreValue runImportedBubbleSortCall CByteCount

call checkSortedAfterImportedSortCall areBytesSortedAscending
arg checkSortedAfterImportedSortCall byteBuffer sortBufferImport
arg checkSortedAfterImportedSortCall byteCount totalSortLength
run checkSortedAfterImportedSortCall
bind sortedAfterImportResult Bool checkSortedAfterImportedSortCall
branchIf sortedAfterImportResult sortedAfterImportHolds
branch stdlibImportBuffersAssertionFailed
label sortedAfterImportHolds

# ---- memory: compareMemoryByteRanges of the just-sorted buffer against the byte sequence {1,2,5,8,9} should return 0 ----
# The expected literal is built byte-by-byte because the sorted buffer
# contains raw byte values (0x01..0x09), NOT ASCII characters '1'..'9'.
const memoryComparisonExpectedBuffer COpaqueMemoryAddress 0
call allocateExpectedSortedImport c.malloc
arg allocateExpectedSortedImport size eightBytesAllocImport
run allocateExpectedSortedImport
bind expectedSortedBufferImport COpaqueMemoryAddress allocateExpectedSortedImport
call storeExpectedByteZero pointer.storeByte
arg storeExpectedByteZero buffer expectedSortedBufferImport
arg storeExpectedByteZero offset offsetZeroByte
arg storeExpectedByteZero value byteOneLiteralImport
run storeExpectedByteZero
call storeExpectedByteOne pointer.storeByte
arg storeExpectedByteOne buffer expectedSortedBufferImport
arg storeExpectedByteOne offset offsetOneByte
arg storeExpectedByteOne value byteTwoLiteralImport
run storeExpectedByteOne
call storeExpectedByteTwo pointer.storeByte
arg storeExpectedByteTwo buffer expectedSortedBufferImport
arg storeExpectedByteTwo offset offsetTwoByte
arg storeExpectedByteTwo value byteFiveLiteralImport
run storeExpectedByteTwo
call storeExpectedByteThree pointer.storeByte
arg storeExpectedByteThree buffer expectedSortedBufferImport
arg storeExpectedByteThree offset offsetThreeByte
arg storeExpectedByteThree value byteEightLiteralImport
run storeExpectedByteThree
call storeExpectedByteFour pointer.storeByte
arg storeExpectedByteFour buffer expectedSortedBufferImport
arg storeExpectedByteFour offset offsetFourByte
arg storeExpectedByteFour value byteNineLiteralImport
run storeExpectedByteFour
const zeroSentinelForCompareImport CSignedInt64 0
call assertCompareAfterSortCall compareMemoryByteRanges
arg assertCompareAfterSortCall leftBuffer sortBufferImport
arg assertCompareAfterSortCall rightBuffer expectedSortedBufferImport
arg assertCompareAfterSortCall byteCount totalSortLength
run assertCompareAfterSortCall
bind compareAfterSortResult CSignedInt64 assertCompareAfterSortCall
call checkCompareAfterSortCall math.equalI64
arg checkCompareAfterSortCall left compareAfterSortResult
arg checkCompareAfterSortCall right zeroSentinelForCompareImport
run checkCompareAfterSortCall
bind compareAfterSortOk Bool checkCompareAfterSortCall
branchIf compareAfterSortOk compareAfterSortHolds
branch stdlibImportBuffersAssertionFailed
label compareAfterSortHolds

call releaseSortBufferImport c.free
arg releaseSortBufferImport ptr sortBufferImport
run releaseSortBufferImport
call releaseExpectedSortedImport c.free
arg releaseExpectedSortedImport ptr expectedSortedBufferImport
run releaseExpectedSortedImport

# ---- inttypes: absoluteMaxWidthSignedInt(-9) == 9 ----
const negativeNineForAbsImport CSignedInt64 -9
const nineExpectedForAbsImport CSignedInt64 9
call assertImportedAbsCall absoluteMaxWidthSignedInt
arg assertImportedAbsCall inputValue negativeNineForAbsImport
run assertImportedAbsCall
bind importedAbsResult CSignedInt64 assertImportedAbsCall
call checkImportedAbsCall math.equalI64
arg checkImportedAbsCall left importedAbsResult
arg checkImportedAbsCall right nineExpectedForAbsImport
run checkImportedAbsCall
bind importedAbsOk Bool checkImportedAbsCall
branchIf importedAbsOk importedAbsHolds
branch stdlibImportBuffersAssertionFailed
label importedAbsHolds

# ---- stdlib: parseDecimalCStringToSignedInt64("  -42") == -42 ----
const negativeFortyTwoTextImport CNullTerminatedByteString "  -42"
const negativeFortyTwoExpectedImport CSignedInt64 -42
call assertParseDecimalImportCall parseDecimalCStringToSignedInt64
arg assertParseDecimalImportCall inputText negativeFortyTwoTextImport
run assertParseDecimalImportCall
bind parseDecimalImportResult CSignedInt64 assertParseDecimalImportCall
call checkParseDecimalImportCall math.equalI64
arg checkParseDecimalImportCall left parseDecimalImportResult
arg checkParseDecimalImportCall right negativeFortyTwoExpectedImport
run checkParseDecimalImportCall
bind parseDecimalImportOk Bool checkParseDecimalImportCall
branchIf parseDecimalImportOk parseDecimalImportHolds
branch stdlibImportBuffersAssertionFailed
label parseDecimalImportHolds

# ---- random: seed with 1, draw, verify 48271 (MINSTD canonical) ----
const seedOneForLcgImport CSignedInt64 1
call createLcgStateImport createDeterministicRandomState
arg createLcgStateImport randomSeed seedOneForLcgImport
run createLcgStateImport
bindOk lcgStateSlotImport COpaqueMemoryAddress createLcgStateImport
call drawFromLcgImport nextDeterministicRandomSignedInt64
arg drawFromLcgImport randomState lcgStateSlotImport
run drawFromLcgImport
bind lcgFirstDrawImport CSignedInt64 drawFromLcgImport
const minstdFirstDrawExpected CSignedInt64 48271
call checkLcgDrawImportCall math.equalI64
arg checkLcgDrawImportCall left lcgFirstDrawImport
arg checkLcgDrawImportCall right minstdFirstDrawExpected
run checkLcgDrawImportCall
bind lcgDrawImportOk Bool checkLcgDrawImportCall
branchIf lcgDrawImportOk lcgDrawImportHolds
branch stdlibImportBuffersAssertionFailed
label lcgDrawImportHolds

call releaseLcgStateImport releaseDeterministicRandomState
arg releaseLcgStateImport randomState lcgStateSlotImport
run releaseLcgStateImport
ignoreValue releaseLcgStateImport CSignedInt32

# ---- limits: maximumSignedInt32Value == 2147483647 ----
const expectedMaximumSignedInt32 CSignedInt64 2147483647
call checkImportedLimitMaxInt32Call math.equalI64
arg checkImportedLimitMaxInt32Call left maximumSignedInt32Value
arg checkImportedLimitMaxInt32Call right expectedMaximumSignedInt32
run checkImportedLimitMaxInt32Call
bind importedLimitMaxInt32Ok Bool checkImportedLimitMaxInt32Call
branchIf importedLimitMaxInt32Ok importedLimitMaxInt32Holds
branch stdlibImportBuffersAssertionFailed
label importedLimitMaxInt32Holds

# ---- signal: interruptSignalNumber == 2 ----
const expectedInterruptSignalNumber CSignedInt32 2
call checkImportedInterruptCall math.equalI64
arg checkImportedInterruptCall left interruptSignalNumber
arg checkImportedInterruptCall right expectedInterruptSignalNumber
run checkImportedInterruptCall
bind importedInterruptOk Bool checkImportedInterruptCall
branchIf importedInterruptOk importedInterruptHolds
branch stdlibImportBuffersAssertionFailed
label importedInterruptHolds

# All imported assertions held.
const buffersImportSuccessMessage CNullTerminatedByteString "OK"
call writeBuffersImportSuccessCall console.writeLine
arg writeBuffersImportSuccessCall console console
arg writeBuffersImportSuccessCall text buffersImportSuccessMessage
run writeBuffersImportSuccessCall
ignoreOk writeBuffersImportSuccessCall Void
const buffersImportExitOk ExitCode 0
returnOk buffersImportExitOk

label stdlibImportBuffersAssertionFailed
makeError stdlibImportBuffersFailure MainError.StdlibImportBuffersSmokeAssertionFailed
returnError stdlibImportBuffersFailure
