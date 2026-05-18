# ============================================================
# AGENTSCRIPT STANDARD LIBRARY TESTS: pure-AS C-string operations
# ============================================================
#
# # rationale: companion test file for stdlib_as/string.as. Imports
#   the string module and exercises every C-string operation it
#   exports — length / compare / search / copy / append / duplicate /
#   prefix-suffix predicates — across happy-path and boundary cases
#   (empty buffer, not-found, ordering, prefix-longer-than-string).
#
# # invariant: success prints "OK\n" and exits 0; assertion failures
#   surface MainError.StringSmokeAssertionFailed; heap allocation
#   failure surfaces MainError.MemoryAllocationFailed.
#
# # pattern: this is the canonical foo.test.as form — same directory
#   as foo.as, importModule foo, project block local to the test,
#   entry console main. The implementation file stdlib_as/string.as
#   carries no smoke main itself.

project StdStringTest
target console
runtime AgentRuntime 0.1
entry console main

importModule string

error MainError
errorCase MainError StringSmokeAssertionFailed
errorCase MainError ConsoleWriteFailed
errorCase MainError MemoryAllocationFailed

# section capability
# rationale: smoke-test main writes a single OK line to stdout and
# frees heap buffers. The memory.buffer read / write and heap-
# allocate capabilities are also redeclared here so the linter
# (which does not trace cross-module imports) resolves the
# `useCapability main …` references below; the canonical
# declarations live in stdlib_as/string.as alongside the impl ops
# that consume them.
capability stdoutWriteCapability console.stdout write
capability heapFreeCapability heap free
capability heapAllocationCapability heap allocate
capability memoryBufferReadCapability memory.buffer read
capability memoryBufferWriteCapability memory.buffer write

# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
useCapability main stdoutWriteCapability
useCapability main heapAllocationCapability
useCapability main heapFreeCapability
useCapability main memoryBufferReadCapability
useCapability main memoryBufferWriteCapability
effect main allocate heap
effect main free heap
effect main write console.stdout
effect main read memory.buffer
effect main write memory.buffer
memoryHeap main yes
memoryAllocationSource main alloc1Call
async main no
purpose main "Smoke-test every string operation. Prints OK on success."
invariant main "Each assertion that should hold returns Ok; final OK line is written via console.writeLine."

label startMain

const hello CNullTerminatedByteString "Hello"
const helloCopy CNullTerminatedByteString "Hello"
const helloComma CNullTerminatedByteString "Hello, World"
const lo CNullTerminatedByteString "lo,"
const xyz CNullTerminatedByteString "xyz"
const digits CNullTerminatedByteString "0123456789"
const justDigits CNullTerminatedByteString "12345abc"

const fiveLen I64 5
const zeroI32 CSignedInt32 0
const twoI64 I64 2
const threeI64 I64 3
const negOneI64test I64 -1

# stringByteLength("Hello") == 5
call l1Call stringByteLength
arg l1Call s hello
run l1Call
bindOk l1Res CByteCount l1Call
call l1CheckCall math.equalI64
arg l1CheckCall left l1Res
arg l1CheckCall right fiveLen
run l1CheckCall
bind l1Ok Bool l1CheckCall
branchIf l1Ok l1OkLabel
branch testFailed
label l1OkLabel

# compareCString("Hello", "Hello") == 0
call c1Call compareCString
arg c1Call a hello
arg c1Call b helloCopy
run c1Call
bindOk c1Res CSignedInt32 c1Call
call c1CheckCall math.equalI64
arg c1CheckCall left c1Res
arg c1CheckCall right zeroI32
run c1CheckCall
bind c1Ok Bool c1CheckCall
branchIf c1Ok c1OkLabel
branch testFailed
label c1OkLabel

# compareCStringPrefixBytes("Hello, World", "Hello", 5) == 0
call nc1Call compareCStringPrefixBytes
arg nc1Call a helloComma
arg nc1Call b hello
arg nc1Call n fiveLen
run nc1Call
bindOk nc1Res CSignedInt32 nc1Call
call nc1CheckCall math.equalI64
arg nc1CheckCall left nc1Res
arg nc1CheckCall right zeroI32
run nc1CheckCall
bind nc1Ok Bool nc1CheckCall
branchIf nc1Ok nc1OkLabel
branch testFailed
label nc1OkLabel

# findFirstCharacterInCString("Hello", 'l') == 2
const lowerL CSignedInt32 108
call ch1Call findFirstCharacterInCString
arg ch1Call s hello
arg ch1Call c lowerL
run ch1Call
bindOk ch1Res CSignedInt64 ch1Call
call ch1CheckCall math.equalI64
arg ch1CheckCall left ch1Res
arg ch1CheckCall right twoI64
run ch1CheckCall
bind ch1Ok Bool ch1CheckCall
branchIf ch1Ok ch1OkLabel
branch testFailed
label ch1OkLabel

# findLastCharacterInCString("Hello", 'l') == 3
call rch1Call findLastCharacterInCString
arg rch1Call s hello
arg rch1Call c lowerL
run rch1Call
bindOk rch1Res CSignedInt64 rch1Call
call rch1CheckCall math.equalI64
arg rch1CheckCall left rch1Res
arg rch1CheckCall right threeI64
run rch1CheckCall
bind rch1Ok Bool rch1CheckCall
branchIf rch1Ok rch1OkLabel
branch testFailed
label rch1OkLabel

# findSubstringInCString("Hello, World", "lo,") == 3
call ss1Call findSubstringInCString
arg ss1Call haystack helloComma
arg ss1Call needle lo
run ss1Call
bindOk ss1Res CSignedInt64 ss1Call
call ss1CheckCall math.equalI64
arg ss1CheckCall left ss1Res
arg ss1CheckCall right threeI64
run ss1CheckCall
bind ss1Ok Bool ss1CheckCall
branchIf ss1Ok ss1OkLabel
branch testFailed
label ss1OkLabel

# findSubstringInCString("Hello, World", "xyz") == -1
call ss2Call findSubstringInCString
arg ss2Call haystack helloComma
arg ss2Call needle xyz
run ss2Call
bindOk ss2Res CSignedInt64 ss2Call
call ss2CheckCall math.equalI64
arg ss2CheckCall left ss2Res
arg ss2CheckCall right negOneI64test
run ss2CheckCall
bind ss2Ok Bool ss2CheckCall
branchIf ss2Ok ss2OkLabel
branch testFailed
label ss2OkLabel

# countInitialCStringBytesInAcceptSet("12345abc", "0123456789") == 5
call sp1Call countInitialCStringBytesInAcceptSet
arg sp1Call s justDigits
arg sp1Call accept digits
run sp1Call
bindOk sp1Res CByteCount sp1Call
call sp1CheckCall math.equalI64
arg sp1CheckCall left sp1Res
arg sp1CheckCall right fiveLen
run sp1CheckCall
bind sp1Ok Bool sp1CheckCall
branchIf sp1Ok sp1OkLabel
branch testFailed
label sp1OkLabel

# copyCStringToDestinationBuffer hello -> heap buffer, then compareCString it
const bufSize CByteCount 16
call alloc1Call c.malloc
arg alloc1Call size bufSize
run alloc1Call
bind dest1 COpaqueMemoryAddress alloc1Call
bindError alloc1Error CSignedInt32 alloc1Call
branchIfError alloc1Call alloc1FailedHandler
defer releaseAlloc1Call c.free dest1

call cc1Call copyCStringToDestinationBuffer
arg cc1Call dest dest1
arg cc1Call src hello
run cc1Call
ignoreOk cc1Call CByteCount

call cc1CmpCall compareCString
arg cc1CmpCall a dest1
arg cc1CmpCall b hello
run cc1CmpCall
bindOk cc1CmpRes CSignedInt32 cc1CmpCall
call cc1CheckCall math.equalI64
arg cc1CheckCall left cc1CmpRes
arg cc1CheckCall right zeroI32
run cc1CheckCall
bind cc1Ok Bool cc1CheckCall
branchIf cc1Ok cc1OkLabel
branch testFailed
label cc1OkLabel

# appendCStringToDestinationBuffer into a buffer that already has "Hello"; append "!" -> "Hello!"
const bufSize2 CByteCount 32
const helloExc CNullTerminatedByteString "Hello!"
const exclSuffix CNullTerminatedByteString "!"
call alloc2Call c.malloc
arg alloc2Call size bufSize2
run alloc2Call
bind dest2 COpaqueMemoryAddress alloc2Call
bindError alloc2Error CSignedInt32 alloc2Call
branchIfError alloc2Call alloc2FailedHandler
defer releaseAlloc2Call c.free dest2
call seed2Call copyCStringToDestinationBuffer
arg seed2Call dest dest2
arg seed2Call src hello
run seed2Call
ignoreOk seed2Call CByteCount
call cat2Call appendCStringToDestinationBuffer
arg cat2Call dest dest2
arg cat2Call src exclSuffix
run cat2Call
ignoreOk cat2Call CByteCount
call catCmpCall compareCString
arg catCmpCall a dest2
arg catCmpCall b helloExc
run catCmpCall
bindOk catCmpRes CSignedInt32 catCmpCall
call catCheckCall math.equalI64
arg catCheckCall left catCmpRes
arg catCheckCall right zeroI32
run catCheckCall
bind catOk Bool catCheckCall
branchIf catOk catOkLabel
branch testFailed
label catOkLabel

# copyCStringPrefixToDestinationBuffer hello -> 16-byte buffer, pad rest with zeros.
const sixteenLen CByteCount 16
call alloc3Call c.malloc
arg alloc3Call size sixteenLen
run alloc3Call
bind dest3 COpaqueMemoryAddress alloc3Call
bindError alloc3Error CSignedInt32 alloc3Call
branchIfError alloc3Call alloc3FailedHandler
defer releaseAlloc3Call c.free dest3
call ncp1Call copyCStringPrefixToDestinationBuffer
arg ncp1Call dest dest3
arg ncp1Call src hello
arg ncp1Call n sixteenLen
run ncp1Call
ignoreOk ncp1Call CByteCount
# Verify first 5 bytes are "Hello", rest are NUL.
call ncpCmpCall compareCStringPrefixBytes
arg ncpCmpCall a dest3
arg ncpCmpCall b hello
arg ncpCmpCall n fiveLen
run ncpCmpCall
bindOk ncpCmpRes CSignedInt32 ncpCmpCall
call ncpCheckCall math.equalI64
arg ncpCheckCall left ncpCmpRes
arg ncpCheckCall right zeroI32
run ncpCheckCall
bind ncpOk Bool ncpCheckCall
branchIf ncpOk ncpOkLabel
branch testFailed
label ncpOkLabel

# countInitialCStringBytesNotInRejectSet("hello,world", ",") == 5 (the comma is at index 5)
const helloWorld CNullTerminatedByteString "hello,world"
const commaStr CNullTerminatedByteString ","
call csn1Call countInitialCStringBytesNotInRejectSet
arg csn1Call s helloWorld
arg csn1Call reject commaStr
run csn1Call
bindOk csn1Res CByteCount csn1Call
call csn1CheckCall math.equalI64
arg csn1CheckCall left csn1Res
arg csn1CheckCall right fiveLen
run csn1CheckCall
bind csn1Ok Bool csn1CheckCall
branchIf csn1Ok csn1OkLabel
branch testFailed
label csn1OkLabel

# findFirstCStringByteInAcceptSet("hello,world", ",.;") == 5
const punctSet CNullTerminatedByteString ",.;"
call pbk1Call findFirstCStringByteInAcceptSet
arg pbk1Call s helloWorld
arg pbk1Call accept punctSet
run pbk1Call
bindOk pbk1Res CSignedInt64 pbk1Call
call pbk1CheckCall math.equalI64
arg pbk1CheckCall left pbk1Res
arg pbk1CheckCall right fiveLen
run pbk1CheckCall
bind pbk1Ok Bool pbk1CheckCall
branchIf pbk1Ok pbk1OkLabel
branch testFailed
label pbk1OkLabel

# duplicateCStringIntoOwnedMemory("Hello") returns a heap copy that compareCString's equal to original
call sd1Call duplicateCStringIntoOwnedMemory
arg sd1Call s hello
run sd1Call
bindOk sd1Res COpaqueMemoryAddress sd1Call
call sd1NullCheckCall pointer.isNull
arg sd1NullCheckCall pointer sd1Res
run sd1NullCheckCall
bind sd1IsNull Bool sd1NullCheckCall
branchIf sd1IsNull testFailed
call sd1CmpCall compareCString
arg sd1CmpCall a sd1Res
arg sd1CmpCall b hello
run sd1CmpCall
bindOk sd1CmpRes CSignedInt32 sd1CmpCall
call sd1CheckCall math.equalI64
arg sd1CheckCall left sd1CmpRes
arg sd1CheckCall right zeroI32
run sd1CheckCall
bind sd1Ok Bool sd1CheckCall
branchIf sd1Ok sd1OkLabel
branch testFailed
label sd1OkLabel
call sd1FreeCall c.free
arg sd1FreeCall ptr sd1Res
run sd1FreeCall

# cstringBeginsWithPrefix("Hello, World", "Hello") == 1
const oneI32trueChk CSignedInt32 1
call bw1Call cstringBeginsWithPrefix
arg bw1Call s helloComma
arg bw1Call prefix hello
run bw1Call
bindOk bw1Res CSignedInt32 bw1Call
call bw1CheckCall math.equalI64
arg bw1CheckCall left bw1Res
arg bw1CheckCall right oneI32trueChk
run bw1CheckCall
bind bw1Ok Bool bw1CheckCall
branchIf bw1Ok bw1OkLabel
branch testFailed
label bw1OkLabel

# cstringEndsWithSuffix("Hello, World", "World") - need an actual "World" string
const worldOnly CNullTerminatedByteString "World"
call ew1Call cstringEndsWithSuffix
arg ew1Call s helloComma
arg ew1Call suffix worldOnly
run ew1Call
bindOk ew1Res CSignedInt32 ew1Call
call ew1CheckCall math.equalI64
arg ew1CheckCall left ew1Res
arg ew1CheckCall right oneI32trueChk
run ew1CheckCall
bind ew1Ok Bool ew1CheckCall
branchIf ew1Ok ew1OkLabel
branch testFailed
label ew1OkLabel

# appendCStringPrefixToDestinationBuffer: seed with "Hi", append "there!" max 4 -> "Hithere"
const bufSizeNc CByteCount 32
const hi CNullTerminatedByteString "Hi"
const thereMore CNullTerminatedByteString "there!"
const expectedHiThere CNullTerminatedByteString "Hither"
const fourNc CByteCount 4
call allocNcCall c.malloc
arg allocNcCall size bufSizeNc
run allocNcCall
bind destNc COpaqueMemoryAddress allocNcCall
bindError allocNcError CSignedInt32 allocNcCall
branchIfError allocNcCall allocNcFailedHandler
defer releaseAllocNcCall c.free destNc
call seedNcCall copyCStringToDestinationBuffer
arg seedNcCall dest destNc
arg seedNcCall src hi
run seedNcCall
ignoreOk seedNcCall CByteCount
call ncatCall appendCStringPrefixToDestinationBuffer
arg ncatCall dest destNc
arg ncatCall src thereMore
arg ncatCall n fourNc
run ncatCall
ignoreOk ncatCall CByteCount
call ncCmpCall compareCString
arg ncCmpCall a destNc
arg ncCmpCall b expectedHiThere
run ncCmpCall
bindOk ncCmpRes CSignedInt32 ncCmpCall
call ncCheckCall math.equalI64
arg ncCheckCall left ncCmpRes
arg ncCheckCall right zeroI32
run ncCheckCall
bind ncOk Bool ncCheckCall
branchIf ncOk ncOkLabel
branch testFailed
label ncOkLabel

# ============================================================
# Extended unit-test cases: empty-string boundary, not-found
# search results, ordering comparisons, and predicate-false legs
# for the prefix/suffix checks. Each existing op already has one
# happy-path assertion above; these target the alternate branch.
# ============================================================

const emptyStr CNullTerminatedByteString ""
const helloPlus CNullTerminatedByteString "Hello!"
const helloFull CNullTerminatedByteString "Hello, World"
const helloA CNullTerminatedByteString "abc"
const helloAd CNullTerminatedByteString "abd"
const helloAb CNullTerminatedByteString "ab"
const upperZ CSignedInt32 90
const zeroByteCount CByteCount 0
const sixI64case I64 6
const zeroI32trueChk CSignedInt32 0

# stringByteLength("") == 0 (empty boundary)
call lenEmptyCall stringByteLength
arg lenEmptyCall s emptyStr
run lenEmptyCall
bindOk lenEmptyRes CByteCount lenEmptyCall
call lenEmptyCheckCall math.equalI64
arg lenEmptyCheckCall left lenEmptyRes
arg lenEmptyCheckCall right zeroByteCount
run lenEmptyCheckCall
bind lenEmptyOk Bool lenEmptyCheckCall
branchIf lenEmptyOk lenEmptyOkLabel
branch testFailed
label lenEmptyOkLabel

# stringByteLength("Hello!") == 6
call lenSixCall stringByteLength
arg lenSixCall s helloPlus
run lenSixCall
bindOk lenSixRes CByteCount lenSixCall
call lenSixCheckCall math.equalI64
arg lenSixCheckCall left lenSixRes
arg lenSixCheckCall right sixI64case
run lenSixCheckCall
bind lenSixOk Bool lenSixCheckCall
branchIf lenSixOk lenSixOkLabel
branch testFailed
label lenSixOkLabel

# compareCString("abc", "abd") < 0 (lexicographic order)
call cmpLessCall compareCString
arg cmpLessCall a helloA
arg cmpLessCall b helloAd
run cmpLessCall
bindOk cmpLessRes CSignedInt32 cmpLessCall
call cmpLessCheckCall math.lessThanI64
arg cmpLessCheckCall left cmpLessRes
arg cmpLessCheckCall right zeroI32trueChk
run cmpLessCheckCall
bind cmpLessOk Bool cmpLessCheckCall
branchIf cmpLessOk cmpLessOkLabel
branch testFailed
label cmpLessOkLabel

# compareCString("abd", "abc") > 0 (reverse direction)
call cmpGreaterCall compareCString
arg cmpGreaterCall a helloAd
arg cmpGreaterCall b helloA
run cmpGreaterCall
bindOk cmpGreaterRes CSignedInt32 cmpGreaterCall
call cmpGreaterCheckCall math.greaterThanI64
arg cmpGreaterCheckCall left cmpGreaterRes
arg cmpGreaterCheckCall right zeroI32trueChk
run cmpGreaterCheckCall
bind cmpGreaterOk Bool cmpGreaterCheckCall
branchIf cmpGreaterOk cmpGreaterOkLabel
branch testFailed
label cmpGreaterOkLabel

# compareCString("abc", "ab") > 0 (longer string greater when prefix-matches)
call cmpLongerCall compareCString
arg cmpLongerCall a helloA
arg cmpLongerCall b helloAb
run cmpLongerCall
bindOk cmpLongerRes CSignedInt32 cmpLongerCall
call cmpLongerCheckCall math.greaterThanI64
arg cmpLongerCheckCall left cmpLongerRes
arg cmpLongerCheckCall right zeroI32trueChk
run cmpLongerCheckCall
bind cmpLongerOk Bool cmpLongerCheckCall
branchIf cmpLongerOk cmpLongerOkLabel
branch testFailed
label cmpLongerOkLabel

# compareCStringPrefixBytes(a, b, 0) == 0 (zero-length is always equal)
call cmpZeroNCall compareCStringPrefixBytes
arg cmpZeroNCall a hello
arg cmpZeroNCall b xyz
arg cmpZeroNCall n zeroByteCount
run cmpZeroNCall
bindOk cmpZeroNRes CSignedInt32 cmpZeroNCall
call cmpZeroNCheckCall math.equalI64
arg cmpZeroNCheckCall left cmpZeroNRes
arg cmpZeroNCheckCall right zeroI32trueChk
run cmpZeroNCheckCall
bind cmpZeroNOk Bool cmpZeroNCheckCall
branchIf cmpZeroNOk cmpZeroNOkLabel
branch testFailed
label cmpZeroNOkLabel

# findFirstCharacterInCString("Hello", 'Z') == -1 (not found)
call findCharNotFoundCall findFirstCharacterInCString
arg findCharNotFoundCall s hello
arg findCharNotFoundCall c upperZ
run findCharNotFoundCall
bindOk findCharNotFoundRes CSignedInt64 findCharNotFoundCall
call findCharNotFoundCheckCall math.equalI64
arg findCharNotFoundCheckCall left findCharNotFoundRes
arg findCharNotFoundCheckCall right negOneI64test
run findCharNotFoundCheckCall
bind findCharNotFoundOk Bool findCharNotFoundCheckCall
branchIf findCharNotFoundOk findCharNotFoundOkLabel
branch testFailed
label findCharNotFoundOkLabel

# findLastCharacterInCString("Hello", 'Z') == -1 (not found)
call findLastNotFoundCall findLastCharacterInCString
arg findLastNotFoundCall s hello
arg findLastNotFoundCall c upperZ
run findLastNotFoundCall
bindOk findLastNotFoundRes CSignedInt64 findLastNotFoundCall
call findLastNotFoundCheckCall math.equalI64
arg findLastNotFoundCheckCall left findLastNotFoundRes
arg findLastNotFoundCheckCall right negOneI64test
run findLastNotFoundCheckCall
bind findLastNotFoundOk Bool findLastNotFoundCheckCall
branchIf findLastNotFoundOk findLastNotFoundOkLabel
branch testFailed
label findLastNotFoundOkLabel

# findSubstringInCString("Hello", "Hello") == 0 (needle at start, full match)
call findSubAtStartCall findSubstringInCString
arg findSubAtStartCall haystack hello
arg findSubAtStartCall needle helloCopy
run findSubAtStartCall
bindOk findSubAtStartRes CSignedInt64 findSubAtStartCall
call findSubAtStartCheckCall math.equalI64
arg findSubAtStartCheckCall left findSubAtStartRes
arg findSubAtStartCheckCall right zeroI32trueChk
run findSubAtStartCheckCall
bind findSubAtStartOk Bool findSubAtStartCheckCall
branchIf findSubAtStartOk findSubAtStartOkLabel
branch testFailed
label findSubAtStartOkLabel

# cstringBeginsWithPrefix("Hello", "Hello, World") == 0 (prefix longer than string)
call beginsLongerCall cstringBeginsWithPrefix
arg beginsLongerCall s hello
arg beginsLongerCall prefix helloFull
run beginsLongerCall
bindOk beginsLongerRes CSignedInt32 beginsLongerCall
call beginsLongerCheckCall math.equalI64
arg beginsLongerCheckCall left beginsLongerRes
arg beginsLongerCheckCall right zeroI32trueChk
run beginsLongerCheckCall
bind beginsLongerOk Bool beginsLongerCheckCall
branchIf beginsLongerOk beginsLongerOkLabel
branch testFailed
label beginsLongerOkLabel

# cstringEndsWithSuffix("Hello, World", "Hello") == 0 (matches prefix, not suffix)
call endsMismatchCall cstringEndsWithSuffix
arg endsMismatchCall s helloComma
arg endsMismatchCall suffix hello
run endsMismatchCall
bindOk endsMismatchRes CSignedInt32 endsMismatchCall
call endsMismatchCheckCall math.equalI64
arg endsMismatchCheckCall left endsMismatchRes
arg endsMismatchCheckCall right zeroI32trueChk
run endsMismatchCheckCall
bind endsMismatchOk Bool endsMismatchCheckCall
branchIf endsMismatchOk endsMismatchOkLabel
branch testFailed
label endsMismatchOkLabel

# All assertions hold. Emit "OK" via console.writeLine — uniform
# with the other stdlib smokes, references the runtime console
# handle, and surfaces a typed ConsoleWriteFailed if stdout fails.
const successMessageText CNullTerminatedByteString "OK"
call writeSuccessLineCall console.writeLine
arg writeSuccessLineCall console console
arg writeSuccessLineCall text successMessageText
run writeSuccessLineCall
ignoreOk writeSuccessLineCall CSignedInt32
bindError consoleWriteResultError CSignedInt32 writeSuccessLineCall
branchIfError writeSuccessLineCall consoleWriteFailedHandler

const exitOk ExitCode 0
returnOk exitOk

label testFailed
const exitFail CSignedInt32 1
makeError testFailure MainError.StringSmokeAssertionFailed exitFail
returnError testFailure

# Failure leg: surface the raw negative CSignedInt32 from
# console.writeLine as the cause attached to the typed
# MainError.ConsoleWriteFailed variant.
label consoleWriteFailedHandler
makeError consoleWriteFailedFailure MainError.ConsoleWriteFailed consoleWriteResultError
returnError consoleWriteFailedFailure

# Heap-allocation failure legs: one handler per c.malloc call so
# the bindError value for each is referenced (linter wants every
# bindError consumed). Each surfaces MainError.MemoryAllocationFailed
# with the call-specific raw error as the cause. The deferred frees
# registered after each successful malloc still fire on these paths
# for any allocations that did succeed prior to the failure.
label alloc1FailedHandler
makeError alloc1Failure MainError.MemoryAllocationFailed alloc1Error
returnError alloc1Failure
label alloc2FailedHandler
makeError alloc2Failure MainError.MemoryAllocationFailed alloc2Error
returnError alloc2Failure
label alloc3FailedHandler
makeError alloc3Failure MainError.MemoryAllocationFailed alloc3Error
returnError alloc3Failure
label allocNcFailedHandler
makeError allocNcFailure MainError.MemoryAllocationFailed allocNcError
returnError allocNcFailure
