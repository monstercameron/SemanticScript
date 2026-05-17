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
#   arraySumBytes(buf, count)     Sum of all byte values.
#   arrayMinByte(buf, count)      Minimum byte value (0..255).
#   arrayMaxByte(buf, count)      Maximum byte value.
#   arrayContainsByte(buf, count, value)
#                                  1 if value occurs, else 0.
#   arrayCountByte(buf, count, value)
#                                  Number of occurrences.
#   arrayReverseInPlace(buf, count)
#                                  Reverse bytes in place. Returns count.
# ============================================================


operation arraySumBytes
input arraySumBytes buf CNullTerminatedByteString
input arraySumBytes count CByteCount
output arraySumBytes Result CSignedInt64 Void
effect arraySumBytes read memory.buffer
memory arraySumBytes heap no
async arraySumBytes no
purpose arraySumBytes "Sum every byte in the first count bytes of buf, treating each as unsigned."
label startArraySumBytes
const zero I64 0
const oneI I64 1
const tFs I64 256
var sum I64 0
var idx I64 0
label loopHead
call doneCall math.greaterThanOrEqualI64
arg doneCall left idx
arg doneCall right count
run doneCall
bind done Bool doneCall
branchIf done sumDone
call loadCall pointer.loadByte
arg loadCall buffer buf
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


operation arrayMinByte
input arrayMinByte buf CNullTerminatedByteString
input arrayMinByte count CByteCount
output arrayMinByte Result CSignedInt64 Void
effect arrayMinByte read memory.buffer
memory arrayMinByte heap no
async arrayMinByte no
purpose arrayMinByte "Smallest unsigned byte. Returns 256 (out-of-range sentinel) for empty arrays."
label startArrayMinByte
const oneI I64 1
const tFs I64 256
const sentinelEmpty I64 256
var minVal I64 256
var idx I64 0
label loopHead
call doneCall math.greaterThanOrEqualI64
arg doneCall left idx
arg doneCall right count
run doneCall
bind done Bool doneCall
branchIf done minDone
call loadCall pointer.loadByte
arg loadCall buffer buf
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


operation arrayMaxByte
input arrayMaxByte buf CNullTerminatedByteString
input arrayMaxByte count CByteCount
output arrayMaxByte Result CSignedInt64 Void
effect arrayMaxByte read memory.buffer
memory arrayMaxByte heap no
async arrayMaxByte no
purpose arrayMaxByte "Largest unsigned byte. Returns -1 for empty arrays."
label startArrayMaxByte
const oneI I64 1
const tFs I64 256
const negSentinel I64 -1
var maxVal I64 -1
var idx I64 0
label loopHead
call doneCall math.greaterThanOrEqualI64
arg doneCall left idx
arg doneCall right count
run doneCall
bind done Bool doneCall
branchIf done maxDone
call loadCall pointer.loadByte
arg loadCall buffer buf
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


operation arrayContainsByte
input arrayContainsByte buf CNullTerminatedByteString
input arrayContainsByte count CByteCount
input arrayContainsByte value CSignedInt32
output arrayContainsByte Result CSignedInt32 Void
effect arrayContainsByte read memory.buffer
memory arrayContainsByte heap no
async arrayContainsByte no
purpose arrayContainsByte "1 if any byte in [0, count) equals value, else 0."
label startArrayContainsByte
const oneI I64 1
const trueR CSignedInt32 1
const falseR CSignedInt32 0
var idx I64 0
label loopHead
call doneCall math.greaterThanOrEqualI64
arg doneCall left idx
arg doneCall right count
run doneCall
bind done Bool doneCall
branchIf done notFound
call loadCall pointer.loadByte
arg loadCall buffer buf
arg loadCall offset idx
run loadCall
bind byteRaw I8 loadCall
call eqCall math.equalI64
arg eqCall left byteRaw
arg eqCall right value
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


operation arrayCountByte
input arrayCountByte buf CNullTerminatedByteString
input arrayCountByte count CByteCount
input arrayCountByte value CSignedInt32
output arrayCountByte Result CSignedInt64 Void
effect arrayCountByte read memory.buffer
memory arrayCountByte heap no
async arrayCountByte no
purpose arrayCountByte "Number of bytes equal to value in [0, count)."
label startArrayCountByte
const oneI I64 1
var counter I64 0
var idx I64 0
label loopHead
call doneCall math.greaterThanOrEqualI64
arg doneCall left idx
arg doneCall right count
run doneCall
bind done Bool doneCall
branchIf done countDone
call loadCall pointer.loadByte
arg loadCall buffer buf
arg loadCall offset idx
run loadCall
bind byteRaw I8 loadCall
call eqCall math.equalI64
arg eqCall left byteRaw
arg eqCall right value
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


operation arrayReverseInPlace
input arrayReverseInPlace buf COpaqueMemoryAddress
input arrayReverseInPlace count CByteCount
output arrayReverseInPlace Result CByteCount Void
effect arrayReverseInPlace read memory.buffer
effect arrayReverseInPlace write memory.buffer
memory arrayReverseInPlace heap no
async arrayReverseInPlace no
purpose arrayReverseInPlace "Reverse the order of the first count bytes of buf in place. Returns count."
label startArrayReverseInPlace
const oneI I64 1
const twoI I64 2
var leftIdx I64 0
var rightIdx I64 0
call rInit math.subtractI64
arg rInit left count
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
arg leftLoadCall buffer buf
arg leftLoadCall offset leftIdx
run leftLoadCall
bind leftByte I8 leftLoadCall
call rightLoadCall pointer.loadByte
arg rightLoadCall buffer buf
arg rightLoadCall offset rightIdx
run rightLoadCall
bind rightByte I8 rightLoadCall

call swapLeftCall pointer.storeByte
arg swapLeftCall buffer buf
arg swapLeftCall offset leftIdx
arg swapLeftCall value rightByte
run swapLeftCall
call swapRightCall pointer.storeByte
arg swapRightCall buffer buf
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
returnOk count


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

# arraySumBytes("hello", 5) == 'h'+'e'+'l'+'l'+'o' = 104+101+108+108+111 = 532
call s1 arraySumBytes
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

# arrayContainsByte("hello", 5, 'l') == 1
const lowerL CSignedInt32 108
call c1 arrayContainsByte
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

# arrayCountByte("hello", 5, 'l') == 2
call cb1 arrayCountByte
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
