project StdSortSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: byte-sort helpers.
#
# Each sort operates on a buffer of unsigned bytes (after the +256/256
# normalization applied during compare).
#
# Operations:
#   sortBytesWithBubbleSortInPlace(buf, count)   In-place bubble sort.
#   sortBytesWithInsertionSortInPlace(buf, count) In-place insertion sort.
#   areBytesSortedAscending(buf, count)     1 if monotonically non-decreasing.
#   selectionSortBytes(buf, count) Selection sort.
# ============================================================


operation sortBytesWithBubbleSortInPlace
input sortBytesWithBubbleSortInPlace byteBuffer COpaqueMemoryAddress
input sortBytesWithBubbleSortInPlace byteCount CByteCount
output sortBytesWithBubbleSortInPlace Result CByteCount Void
effect sortBytesWithBubbleSortInPlace read memory.buffer
effect sortBytesWithBubbleSortInPlace write memory.buffer
memory sortBytesWithBubbleSortInPlace heap no
async sortBytesWithBubbleSortInPlace no
purpose sortBytesWithBubbleSortInPlace "Bubble-sort the first count bytes of buf in non-decreasing order. O(n^2). Returns count."
label startSortBytesWithBubbleSortInPlace
const oneI I64 1
const tFs I64 256
var i I64 0
var n I64 0
set n byteCount
label outerHead
call outerDone math.greaterThanOrEqualI64
arg outerDone left i
arg outerDone right n
run outerDone
bind oDone Bool outerDone
branchIf oDone bsDone
var j I64 0
label innerHead
# bound = n - i - 1
call ni math.subtractI64
arg ni left n
arg ni right i
run ni
bind nMinusI I64 ni
call ub math.subtractI64
arg ub left nMinusI
arg ub right oneI
run ub
bind innerBound I64 ub
call innerDone math.greaterThanOrEqualI64
arg innerDone left j
arg innerDone right innerBound
run innerDone
bind iDone Bool innerDone
branchIf iDone outerAdvance

# Load buf[j], buf[j+1]
call leftLoadCall pointer.loadByte
arg leftLoadCall buffer byteBuffer
arg leftLoadCall offset j
run leftLoadCall
bind leftRaw I8 leftLoadCall
call jPlus1 math.addI64
arg jPlus1 left j
arg jPlus1 right oneI
run jPlus1
bind jp1 I64 jPlus1
call rightLoadCall pointer.loadByte
arg rightLoadCall buffer byteBuffer
arg rightLoadCall offset jp1
run rightLoadCall
bind rightRaw I8 rightLoadCall

# Normalize both via +256 mod 256
call shiftL math.addI64
arg shiftL left leftRaw
arg shiftL right tFs
run shiftL
bind sL I64 shiftL
call modL math.moduloI64
arg modL left sL
arg modL right tFs
run modL
bind leftU I64 modL

call shiftR math.addI64
arg shiftR left rightRaw
arg shiftR right tFs
run shiftR
bind sR I64 shiftR
call modR math.moduloI64
arg modR left sR
arg modR right tFs
run modR
bind rightU I64 modR

# If left > right swap
call cmpCall math.greaterThanI64
arg cmpCall left leftU
arg cmpCall right rightU
run cmpCall
bind outOfOrder Bool cmpCall
branchIf outOfOrder swap
branch innerAdvance

label swap
call swapL pointer.storeByte
arg swapL buffer byteBuffer
arg swapL offset j
arg swapL value rightRaw
run swapL
call swapR pointer.storeByte
arg swapR buffer byteBuffer
arg swapR offset jp1
arg swapR value leftRaw
run swapR
branch innerAdvance

label innerAdvance
call incJ math.addI64
arg incJ left j
arg incJ right oneI
run incJ
bind jNext I64 incJ
set j jNext
branch innerHead

label outerAdvance
call incI math.addI64
arg incI left i
arg incI right oneI
run incI
bind iNext I64 incI
set i iNext
branch outerHead

label bsDone
returnOk byteCount


operation areBytesSortedAscending
input areBytesSortedAscending byteBuffer CNullTerminatedByteString
input areBytesSortedAscending byteCount CByteCount
output areBytesSortedAscending Result CSignedInt32 Void
effect areBytesSortedAscending read memory.buffer
memory areBytesSortedAscending heap no
async areBytesSortedAscending no
purpose areBytesSortedAscending "1 if every adjacent pair satisfies buf[i] <= buf[i+1], else 0. Empty / single-element arrays are sorted."
label startAreBytesSortedAscending
const oneI I64 1
const tFs I64 256
const trueR CSignedInt32 1
const falseR CSignedInt32 0
# count <= 1 -> sorted
call leOneCall math.lessThanOrEqualI64
arg leOneCall left byteCount
arg leOneCall right oneI
run leOneCall
bind leOne Bool leOneCall
branchIf leOne sortedTrue
var idx I64 0
call boundCall math.subtractI64
arg boundCall left byteCount
arg boundCall right oneI
run boundCall
bind innerBound I64 boundCall
label loopHead
call doneCall math.greaterThanOrEqualI64
arg doneCall left idx
arg doneCall right innerBound
run doneCall
bind done Bool doneCall
branchIf done sortedTrue
call leftLoad pointer.loadByte
arg leftLoad buffer byteBuffer
arg leftLoad offset idx
run leftLoad
bind leftRaw I8 leftLoad
call idxPlus1 math.addI64
arg idxPlus1 left idx
arg idxPlus1 right oneI
run idxPlus1
bind ip1 I64 idxPlus1
call rightLoad pointer.loadByte
arg rightLoad buffer byteBuffer
arg rightLoad offset ip1
run rightLoad
bind rightRaw I8 rightLoad

call shiftL math.addI64
arg shiftL left leftRaw
arg shiftL right tFs
run shiftL
bind sL I64 shiftL
call modL math.moduloI64
arg modL left sL
arg modL right tFs
run modL
bind leftU I64 modL
call shiftR math.addI64
arg shiftR left rightRaw
arg shiftR right tFs
run shiftR
bind sR I64 shiftR
call modR math.moduloI64
arg modR left sR
arg modR right tFs
run modR
bind rightU I64 modR

call cmpCall math.greaterThanI64
arg cmpCall left leftU
arg cmpCall right rightU
run cmpCall
bind outOfOrder Bool cmpCall
branchIf outOfOrder sortedFalse

call incCall math.addI64
arg incCall left idx
arg incCall right oneI
run incCall
bind idxNext I64 incCall
set idx idxNext
branch loopHead

label sortedTrue
returnOk trueR
label sortedFalse
returnOk falseR


operation sortBytesWithInsertionSortInPlace
input sortBytesWithInsertionSortInPlace byteBuffer COpaqueMemoryAddress
input sortBytesWithInsertionSortInPlace byteCount CByteCount
output sortBytesWithInsertionSortInPlace Result CByteCount Void
effect sortBytesWithInsertionSortInPlace read memory.buffer
effect sortBytesWithInsertionSortInPlace write memory.buffer
memory sortBytesWithInsertionSortInPlace heap no
async sortBytesWithInsertionSortInPlace no
purpose sortBytesWithInsertionSortInPlace "In-place insertion sort. O(n^2) worst case, O(n) on nearly-sorted input."
label startSortBytesWithInsertionSortInPlace
const oneI I64 1
const tFs I64 256
var i I64 1
label outerHead
call outerDone math.greaterThanOrEqualI64
arg outerDone left i
arg outerDone right byteCount
run outerDone
bind oDone Bool outerDone
branchIf oDone isDone

# Load key = buf[i] (we shift smaller elements right and re-store key)
call keyLoad pointer.loadByte
arg keyLoad buffer byteBuffer
arg keyLoad offset i
run keyLoad
bind keyRaw I8 keyLoad
call keyShift math.addI64
arg keyShift left keyRaw
arg keyShift right tFs
run keyShift
bind keyS I64 keyShift
call keyMod math.moduloI64
arg keyMod left keyS
arg keyMod right tFs
run keyMod
bind keyU I64 keyMod

var j I64 0
call jInit math.subtractI64
arg jInit left i
arg jInit right oneI
run jInit
bind j0 I64 jInit
set j j0

# While j >= 0 and buf[j] > key: buf[j+1] = buf[j]; j--
label shiftLoop
const zeroI64 I64 0
call jNegCall math.lessThanI64
arg jNegCall left j
arg jNegCall right zeroI64
run jNegCall
bind jNeg Bool jNegCall
branchIf jNeg shiftDone
call sLoad pointer.loadByte
arg sLoad buffer byteBuffer
arg sLoad offset j
run sLoad
bind sRaw I8 sLoad
call sShift math.addI64
arg sShift left sRaw
arg sShift right tFs
run sShift
bind sS I64 sShift
call sMod math.moduloI64
arg sMod left sS
arg sMod right tFs
run sMod
bind sU I64 sMod
call cmpKey math.greaterThanI64
arg cmpKey left sU
arg cmpKey right keyU
run cmpKey
bind sGreater Bool cmpKey
branchIf sGreater shiftRight
branch shiftDone

label shiftRight
call jPlus1 math.addI64
arg jPlus1 left j
arg jPlus1 right oneI
run jPlus1
bind jp1 I64 jPlus1
call storeShift pointer.storeByte
arg storeShift buffer byteBuffer
arg storeShift offset jp1
arg storeShift value sRaw
run storeShift
call decJ math.subtractI64
arg decJ left j
arg decJ right oneI
run decJ
bind jNext I64 decJ
set j jNext
branch shiftLoop

label shiftDone
# Insert key at j+1
call insertAt math.addI64
arg insertAt left j
arg insertAt right oneI
run insertAt
bind insertOff I64 insertAt
call insertStore pointer.storeByte
arg insertStore buffer byteBuffer
arg insertStore offset insertOff
arg insertStore value keyRaw
run insertStore

call incI math.addI64
arg incI left i
arg incI right oneI
run incI
bind iNext I64 incI
set i iNext
branch outerHead

label isDone
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
purpose main "Smoke-test sort ops. Prints OK."
label startMain

const bufSize CByteCount 8
call alloc c.malloc
arg alloc size bufSize
run alloc
bind buf COpaqueMemoryAddress alloc

# Fill with {5, 2, 8, 1, 9}
const five CSignedInt32 5
const two CSignedInt32 2
const eight CSignedInt32 8
const one CSignedInt32 1
const nine CSignedInt32 9
const o0 CByteCount 0
const o1 CByteCount 1
const o2 CByteCount 2
const o3 CByteCount 3
const o4 CByteCount 4
const lenCB CByteCount 5

call s0 pointer.storeByte
arg s0 buffer buf
arg s0 offset o0
arg s0 value five
run s0
call s1 pointer.storeByte
arg s1 buffer buf
arg s1 offset o1
arg s1 value two
run s1
call s2 pointer.storeByte
arg s2 buffer buf
arg s2 offset o2
arg s2 value eight
run s2
call s3 pointer.storeByte
arg s3 buffer buf
arg s3 offset o3
arg s3 value one
run s3
call s4 pointer.storeByte
arg s4 buffer buf
arg s4 offset o4
arg s4 value nine
run s4

call bs sortBytesWithBubbleSortInPlace
arg bs buf buf
arg bs count lenCB
run bs
ignoreOk bs CByteCount

call chk areBytesSortedAscending
arg chk buf buf
arg chk count lenCB
run chk
bindOk chkRes CSignedInt32 chk
const trueChk CSignedInt32 1
call chkOk math.equalI64
arg chkOk left chkRes
arg chkOk right trueChk
run chkOk
bind isOk Bool chkOk
branchIf isOk testPassed
branch testFailed

label testPassed
call f c.free
arg f ptr buf
run f

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
