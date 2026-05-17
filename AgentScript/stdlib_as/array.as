project StdArraySelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: byte-array helpers.
#
# Treats a COpaqueMemoryAddress + length as an array of unsigned
# bytes. Each value is normalized through (b + 256) % 256 to avoid
# I8 sign-extension.
#
# Operations:
#   sumSignedByteValuesInBuffer(buf, count)     Sum of all byte values.
#   findMinimumSignedByteInBuffer(buf, count)      Minimum byte value (0..255).
#   findMaximumSignedByteInBuffer(buf, count)      Maximum byte value.
#   bufferContainsSignedByteValue(buf, count, value)
#                                  1 if value occurs, else 0.
#   countSignedByteValueInBuffer(buf, count, value)
#                                  Number of occurrences.
#   reverseBytesInBufferInPlace(buf, count)
#                                  Reverse bytes in place. Returns count.
# ============================================================


operation sumSignedByteValuesInBuffer
input sumSignedByteValuesInBuffer byteBuffer CNullTerminatedByteString
input sumSignedByteValuesInBuffer byteCount CByteCount
output sumSignedByteValuesInBuffer Result CSignedInt64 Void
effect sumSignedByteValuesInBuffer read memory.buffer
memory sumSignedByteValuesInBuffer heap no
async sumSignedByteValuesInBuffer no
purpose sumSignedByteValuesInBuffer "Sum every byte in the first count bytes of buf, treating each as unsigned."
label startSumSignedByteValuesInBuffer
const zero I64 0
const oneI I64 1
const tFs I64 256
var sum I64 0
var idx I64 0
label loopHead
call doneCall math.greaterThanOrEqualI64
arg doneCall left idx
arg doneCall right byteCount
run doneCall
bind done Bool doneCall
branchIf done sumDone
call loadCall pointer.loadByte
arg loadCall buffer byteBuffer
arg loadCall offset idx
run loadCall
bind byteRaw I8 loadCall
call shift math.addI64
arg shift left byteRaw
arg shift right tFs
run shift
bind sh I64 shift
call modCall math.moduloI64
arg modCall left sh
arg modCall right tFs
run modCall
bind byteU I64 modCall
call addCall math.addI64
arg addCall left sum
arg addCall right byteU
run addCall
bind newSum I64 addCall
set sum newSum
call incCall math.addI64
arg incCall left idx
arg incCall right oneI
run incCall
bind nextIdx I64 incCall
set idx nextIdx
branch loopHead
label sumDone
returnOk sum


operation findMinimumSignedByteInBuffer
input findMinimumSignedByteInBuffer byteBuffer CNullTerminatedByteString
input findMinimumSignedByteInBuffer byteCount CByteCount
output findMinimumSignedByteInBuffer Result CSignedInt64 Void
effect findMinimumSignedByteInBuffer read memory.buffer
memory findMinimumSignedByteInBuffer heap no
async findMinimumSignedByteInBuffer no
purpose findMinimumSignedByteInBuffer "Smallest unsigned byte. Returns 256 (out-of-range sentinel) for empty arrays."
label startFindMinimumSignedByteInBuffer
const oneI I64 1
const tFs I64 256
const sentinelEmpty I64 256
var minVal I64 256
var idx I64 0
label loopHead
call doneCall math.greaterThanOrEqualI64
arg doneCall left idx
arg doneCall right byteCount
run doneCall
bind done Bool doneCall
branchIf done minDone
call loadCall pointer.loadByte
arg loadCall buffer byteBuffer
arg loadCall offset idx
run loadCall
bind byteRaw I8 loadCall
call shift math.addI64
arg shift left byteRaw
arg shift right tFs
run shift
bind sh I64 shift
call modCall math.moduloI64
arg modCall left sh
arg modCall right tFs
run modCall
bind byteU I64 modCall
call cmpCall math.lessThanI64
arg cmpCall left byteU
arg cmpCall right minVal
run cmpCall
bind isNewMin Bool cmpCall
branchIf isNewMin updateMin
branch advanceMin
label updateMin
set minVal byteU
branch advanceMin
label advanceMin
call incCall math.addI64
arg incCall left idx
arg incCall right oneI
run incCall
bind nextIdx I64 incCall
set idx nextIdx
branch loopHead
label minDone
returnOk minVal


operation findMaximumSignedByteInBuffer
input findMaximumSignedByteInBuffer byteBuffer CNullTerminatedByteString
input findMaximumSignedByteInBuffer byteCount CByteCount
output findMaximumSignedByteInBuffer Result CSignedInt64 Void
effect findMaximumSignedByteInBuffer read memory.buffer
memory findMaximumSignedByteInBuffer heap no
async findMaximumSignedByteInBuffer no
purpose findMaximumSignedByteInBuffer "Largest unsigned byte. Returns -1 for empty arrays."
label startFindMaximumSignedByteInBuffer
const oneI I64 1
const tFs I64 256
const negSentinel I64 -1
var maxVal I64 -1
var idx I64 0
label loopHead
call doneCall math.greaterThanOrEqualI64
arg doneCall left idx
arg doneCall right byteCount
run doneCall
bind done Bool doneCall
branchIf done maxDone
call loadCall pointer.loadByte
arg loadCall buffer byteBuffer
arg loadCall offset idx
run loadCall
bind byteRaw I8 loadCall
call shift math.addI64
arg shift left byteRaw
arg shift right tFs
run shift
bind sh I64 shift
call modCall math.moduloI64
arg modCall left sh
arg modCall right tFs
run modCall
bind byteU I64 modCall
call cmpCall math.greaterThanI64
arg cmpCall left byteU
arg cmpCall right maxVal
run cmpCall
bind isNewMax Bool cmpCall
branchIf isNewMax updateMax
branch advanceMax
label updateMax
set maxVal byteU
branch advanceMax
label advanceMax
call incCall math.addI64
arg incCall left idx
arg incCall right oneI
run incCall
bind nextIdx I64 incCall
set idx nextIdx
branch loopHead
label maxDone
returnOk maxVal


operation bufferContainsSignedByteValue
input bufferContainsSignedByteValue byteBuffer CNullTerminatedByteString
input bufferContainsSignedByteValue byteCount CByteCount
input bufferContainsSignedByteValue targetValue CSignedInt32
output bufferContainsSignedByteValue Result CSignedInt32 Void
effect bufferContainsSignedByteValue read memory.buffer
memory bufferContainsSignedByteValue heap no
async bufferContainsSignedByteValue no
purpose bufferContainsSignedByteValue "1 if any byte in [0, count) equals value, else 0."
label startBufferContainsSignedByteValue
const oneI I64 1
const trueR CSignedInt32 1
const falseR CSignedInt32 0
var idx I64 0
label loopHead
call doneCall math.greaterThanOrEqualI64
arg doneCall left idx
arg doneCall right byteCount
run doneCall
bind done Bool doneCall
branchIf done notFound
call loadCall pointer.loadByte
arg loadCall buffer byteBuffer
arg loadCall offset idx
run loadCall
bind byteRaw I8 loadCall
call eqCall math.equalI64
arg eqCall left byteRaw
arg eqCall right targetValue
run eqCall
bind eq Bool eqCall
branchIf eq found
call incCall math.addI64
arg incCall left idx
arg incCall right oneI
run incCall
bind nextIdx I64 incCall
set idx nextIdx
branch loopHead
label found
returnOk trueR
label notFound
returnOk falseR


operation countSignedByteValueInBuffer
input countSignedByteValueInBuffer byteBuffer CNullTerminatedByteString
input countSignedByteValueInBuffer byteCount CByteCount
input countSignedByteValueInBuffer targetValue CSignedInt32
output countSignedByteValueInBuffer Result CSignedInt64 Void
effect countSignedByteValueInBuffer read memory.buffer
memory countSignedByteValueInBuffer heap no
async countSignedByteValueInBuffer no
purpose countSignedByteValueInBuffer "Number of bytes equal to value in [0, count)."
label startCountSignedByteValueInBuffer
const oneI I64 1
var counter I64 0
var idx I64 0
label loopHead
call doneCall math.greaterThanOrEqualI64
arg doneCall left idx
arg doneCall right byteCount
run doneCall
bind done Bool doneCall
branchIf done countDone
call loadCall pointer.loadByte
arg loadCall buffer byteBuffer
arg loadCall offset idx
run loadCall
bind byteRaw I8 loadCall
call eqCall math.equalI64
arg eqCall left byteRaw
arg eqCall right targetValue
run eqCall
bind eq Bool eqCall
branchIf eq incCounter
branch advanceCount
label incCounter
call incCounterCall math.addI64
arg incCounterCall left counter
arg incCounterCall right oneI
run incCounterCall
bind newCounter I64 incCounterCall
set counter newCounter
branch advanceCount
label advanceCount
call incCall math.addI64
arg incCall left idx
arg incCall right oneI
run incCall
bind nextIdx I64 incCall
set idx nextIdx
branch loopHead
label countDone
returnOk counter


operation reverseBytesInBufferInPlace
input reverseBytesInBufferInPlace byteBuffer COpaqueMemoryAddress
input reverseBytesInBufferInPlace byteCount CByteCount
output reverseBytesInBufferInPlace Result CByteCount Void
effect reverseBytesInBufferInPlace read memory.buffer
effect reverseBytesInBufferInPlace write memory.buffer
memory reverseBytesInBufferInPlace heap no
async reverseBytesInBufferInPlace no
purpose reverseBytesInBufferInPlace "Reverse the order of the first count bytes of buf in place. Returns count."
label startReverseBytesInBufferInPlace
const oneI I64 1
const twoI I64 2
var leftIdx I64 0
var rightIdx I64 0
call rInit math.subtractI64
arg rInit left byteCount
arg rInit right oneI
run rInit
bind rIdx0 I64 rInit
set rightIdx rIdx0

label loopHead
call doneCall math.greaterThanOrEqualI64
arg doneCall left leftIdx
arg doneCall right rightIdx
run doneCall
bind done Bool doneCall
branchIf done revDone

call leftLoadCall pointer.loadByte
arg leftLoadCall buffer byteBuffer
arg leftLoadCall offset leftIdx
run leftLoadCall
bind leftByte I8 leftLoadCall
call rightLoadCall pointer.loadByte
arg rightLoadCall buffer byteBuffer
arg rightLoadCall offset rightIdx
run rightLoadCall
bind rightByte I8 rightLoadCall

call swapLeftCall pointer.storeByte
arg swapLeftCall buffer byteBuffer
arg swapLeftCall offset leftIdx
arg swapLeftCall value rightByte
run swapLeftCall
call swapRightCall pointer.storeByte
arg swapRightCall buffer byteBuffer
arg swapRightCall offset rightIdx
arg swapRightCall value leftByte
run swapRightCall

call incLeft math.addI64
arg incLeft left leftIdx
arg incLeft right oneI
run incLeft
bind nextLeft I64 incLeft
set leftIdx nextLeft
call decRight math.subtractI64
arg decRight left rightIdx
arg decRight right oneI
run decRight
bind nextRight I64 decRight
set rightIdx nextRight
branch loopHead

label revDone
returnOk byteCount


# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main allocate heap
effect main write console.stdout
memory main heap yes
async main no
purpose main "Smoke-test array byte operations. Prints OK."
label startMain

const fiveCount CByteCount 5
const hello CNullTerminatedByteString "hello"

# sumSignedByteValuesInBuffer("hello", 5) == 'h'+'e'+'l'+'l'+'o' = 104+101+108+108+111 = 532
call s1 sumSignedByteValuesInBuffer
arg s1 buf hello
arg s1 count fiveCount
run s1
bindOk s1Res CSignedInt64 s1
const expectedSum CSignedInt64 532
call s1Check math.equalI64
arg s1Check left s1Res
arg s1Check right expectedSum
run s1Check
bind s1Ok Bool s1Check
branchIf s1Ok s1Lbl
branch testFailed
label s1Lbl

# bufferContainsSignedByteValue("hello", 5, 'l') == 1
const lowerL CSignedInt32 108
call c1 bufferContainsSignedByteValue
arg c1 buf hello
arg c1 count fiveCount
arg c1 value lowerL
run c1
bindOk c1Res CSignedInt32 c1
const oneI32 CSignedInt32 1
call c1Check math.equalI64
arg c1Check left c1Res
arg c1Check right oneI32
run c1Check
bind c1Ok Bool c1Check
branchIf c1Ok c1Lbl
branch testFailed
label c1Lbl

# countSignedByteValueInBuffer("hello", 5, 'l') == 2
call cb1 countSignedByteValueInBuffer
arg cb1 buf hello
arg cb1 count fiveCount
arg cb1 value lowerL
run cb1
bindOk cb1Res CSignedInt64 cb1
const expectedTwo CSignedInt64 2
call cb1Check math.equalI64
arg cb1Check left cb1Res
arg cb1Check right expectedTwo
run cb1Check
bind cb1Ok Bool cb1Check
branchIf cb1Ok cb1Lbl
branch testFailed
label cb1Lbl

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
