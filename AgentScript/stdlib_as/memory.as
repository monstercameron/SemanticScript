project StdMemorySelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: bulk memory operations.
#
# Operations:
#   copyMemoryBytes(dest, src, count)         like memcpy. Forward copy.
#   moveMemoryBytesAllowOverlap(dest, src, count)         like memmove. Overlap-safe.
#   fillMemoryBytesWithValue(buffer, value, count)     like memset.
#   compareMemoryByteRanges(a, b, count)           like memcmp.
#   findByteValueInMemoryRange(buffer, value, count)      like memchr. Returns offset or -1.
#
# Pure AS via pointer.loadByte / pointer.storeByte.
# ============================================================


operation copyMemoryBytes
input copyMemoryBytes destinationBuffer COpaqueMemoryAddress
input copyMemoryBytes sourceBuffer CNullTerminatedByteString
input copyMemoryBytes byteCount CByteCount
output copyMemoryBytes Result CByteCount Void
effect copyMemoryBytes read memory.buffer
effect copyMemoryBytes write memory.buffer
memory copyMemoryBytes heap no
memory copyMemoryBytes stack max 1KiB
async copyMemoryBytes no
purpose copyMemoryBytes "Pure-AS memcpy. Forward copy of count bytes."
label startCopyMemoryBytes
const zeroI64 I64 0
const oneI64 I64 1
var cursor I64 0
label copyLoop
call atEndCall math.greaterThanOrEqualI64
arg atEndCall left cursor
arg atEndCall right byteCount
run atEndCall
bind atEnd Bool atEndCall
branchIf atEnd copyDone
call loadCall pointer.loadByte
arg loadCall buffer sourceBuffer
arg loadCall offset cursor
run loadCall
bind currentByte I8 loadCall
call storeCall pointer.storeByte
arg storeCall buffer destinationBuffer
arg storeCall offset cursor
arg storeCall value currentByte
run storeCall
call incCall math.addI64
arg incCall left cursor
arg incCall right oneI64
run incCall
bind nextCursor I64 incCall
set cursor nextCursor
branch copyLoop
label copyDone
returnOk byteCount


# ---- moveMemoryBytesAllowOverlap(dest, src, count) ----
# Overlap-safe variant of copyMemoryBytes. If dest > src (dest is past src
# in memory), we have to copy backwards to avoid clobbering source
# bytes before we read them. Compare ptrtoint(dest) and ptrtoint(src)
# via pointer.difference (returns signed i64 dest - src).
operation moveMemoryBytesAllowOverlap
input moveMemoryBytesAllowOverlap destinationBuffer COpaqueMemoryAddress
input moveMemoryBytesAllowOverlap sourceBuffer CNullTerminatedByteString
input moveMemoryBytesAllowOverlap byteCount CByteCount
output moveMemoryBytesAllowOverlap Result CByteCount Void
effect moveMemoryBytesAllowOverlap read memory.buffer
effect moveMemoryBytesAllowOverlap write memory.buffer
memory moveMemoryBytesAllowOverlap heap no
memory moveMemoryBytesAllowOverlap stack max 1KiB
async moveMemoryBytesAllowOverlap no
purpose moveMemoryBytesAllowOverlap "Pure-AS memmove. Detects whether dest comes after src in memory; if so copies the bytes in reverse to keep overlapping ranges intact. Otherwise forwards to copyMemoryBytes semantics."

label startMoveMemoryBytesAllowOverlap
const zeroMv I64 0
const oneMv I64 1

# delta = dest - src (signed). If positive AND src+count > dest,
# regions overlap with dest above src — must copy backwards.
call deltaCall pointer.difference
arg deltaCall left destinationBuffer
arg deltaCall right sourceBuffer
run deltaCall
bind delta CSignedInt64 deltaCall

call mvForwardCall math.lessThanOrEqualI64
arg mvForwardCall left delta
arg mvForwardCall right zeroMv
run mvForwardCall
bind mvForward Bool mvForwardCall
branchIf mvForward mvForwardCopy

# delta > 0: dest is past src. Backward copy.
var revIdx I64 0
set revIdx byteCount
label mvBackLoop
call mvAtStartCall math.equalI64
arg mvAtStartCall left revIdx
arg mvAtStartCall right zeroMv
run mvAtStartCall
bind mvAtStart Bool mvAtStartCall
branchIf mvAtStart mvDone
call mvDecCall math.subtractI64
arg mvDecCall left revIdx
arg mvDecCall right oneMv
run mvDecCall
bind mvDec I64 mvDecCall
set revIdx mvDec
call mvLoadCall pointer.loadByte
arg mvLoadCall buffer sourceBuffer
arg mvLoadCall offset mvDec
run mvLoadCall
bind mvByte I8 mvLoadCall
call mvStoreCall pointer.storeByte
arg mvStoreCall buffer destinationBuffer
arg mvStoreCall offset mvDec
arg mvStoreCall value mvByte
run mvStoreCall
branch mvBackLoop

label mvForwardCopy
# delta <= 0: src is past dest (or same). Forward copy is safe.
var mvFwdIdx I64 0
label mvFwdLoop
call mvFwdEndCall math.greaterThanOrEqualI64
arg mvFwdEndCall left mvFwdIdx
arg mvFwdEndCall right byteCount
run mvFwdEndCall
bind mvFwdEnd Bool mvFwdEndCall
branchIf mvFwdEnd mvDone
call mvFwdLoadCall pointer.loadByte
arg mvFwdLoadCall buffer sourceBuffer
arg mvFwdLoadCall offset mvFwdIdx
run mvFwdLoadCall
bind mvFwdByte I8 mvFwdLoadCall
call mvFwdStoreCall pointer.storeByte
arg mvFwdStoreCall buffer destinationBuffer
arg mvFwdStoreCall offset mvFwdIdx
arg mvFwdStoreCall value mvFwdByte
run mvFwdStoreCall
call mvFwdIncCall math.addI64
arg mvFwdIncCall left mvFwdIdx
arg mvFwdIncCall right oneMv
run mvFwdIncCall
bind mvFwdNext I64 mvFwdIncCall
set mvFwdIdx mvFwdNext
branch mvFwdLoop

label mvDone
returnOk byteCount


operation fillMemoryBytesWithValue
input fillMemoryBytesWithValue byteBuffer COpaqueMemoryAddress
input fillMemoryBytesWithValue targetValue CSignedInt32
input fillMemoryBytesWithValue byteCount CByteCount
output fillMemoryBytesWithValue Result CByteCount Void
effect fillMemoryBytesWithValue write memory.buffer
memory fillMemoryBytesWithValue heap no
memory fillMemoryBytesWithValue stack max 1KiB
async fillMemoryBytesWithValue no
purpose fillMemoryBytesWithValue "Pure-AS memset. Writes count copies of value into buffer."
label startFillMemoryBytesWithValue
const zeroI64a I64 0
const oneI64a I64 1
var fillCursor I64 0
label fillLoop
call atEndFillCall math.greaterThanOrEqualI64
arg atEndFillCall left fillCursor
arg atEndFillCall right byteCount
run atEndFillCall
bind atEndFill Bool atEndFillCall
branchIf atEndFill fillDone
call fillStoreCall pointer.storeByte
arg fillStoreCall buffer byteBuffer
arg fillStoreCall offset fillCursor
arg fillStoreCall value targetValue
run fillStoreCall
call fillIncCall math.addI64
arg fillIncCall left fillCursor
arg fillIncCall right oneI64a
run fillIncCall
bind nextFill I64 fillIncCall
set fillCursor nextFill
branch fillLoop
label fillDone
returnOk byteCount


operation compareMemoryByteRanges
input compareMemoryByteRanges leftValue CNullTerminatedByteString
input compareMemoryByteRanges rightValue CNullTerminatedByteString
input compareMemoryByteRanges byteCount CByteCount
output compareMemoryByteRanges Result CSignedInt64 Void
effect compareMemoryByteRanges read memory.buffer
memory compareMemoryByteRanges heap no
memory compareMemoryByteRanges stack max 1KiB
async compareMemoryByteRanges no
purpose compareMemoryByteRanges "Pure-AS memcmp. Returns 0 / <0 / >0 on first byte difference."
label startCompareMemoryByteRanges
const zeroI64b I64 0
const oneI64b I64 1
var cmpCursor I64 0
label cmpLoop
call cmpAtEndCall math.greaterThanOrEqualI64
arg cmpAtEndCall left cmpCursor
arg cmpAtEndCall right byteCount
run cmpAtEndCall
bind cmpAtEnd Bool cmpAtEndCall
branchIf cmpAtEnd cmpDone
call cmpLoadACall pointer.loadByte
arg cmpLoadACall buffer leftValue
arg cmpLoadACall offset cmpCursor
run cmpLoadACall
bind aByte I8 cmpLoadACall
call cmpLoadBCall pointer.loadByte
arg cmpLoadBCall buffer rightValue
arg cmpLoadBCall offset cmpCursor
run cmpLoadBCall
bind bByte I8 cmpLoadBCall
call diffCall math.subtractI64
arg diffCall left aByte
arg diffCall right bByte
run diffCall
bind diff I64 diffCall
call isDiffCall math.notEqualI64
arg isDiffCall left diff
arg isDiffCall right zeroI64b
run isDiffCall
bind isDiff Bool isDiffCall
branchIf isDiff cmpReturnDiff
call cmpIncCall math.addI64
arg cmpIncCall left cmpCursor
arg cmpIncCall right oneI64b
run cmpIncCall
bind cmpNext I64 cmpIncCall
set cmpCursor cmpNext
branch cmpLoop
label cmpReturnDiff
returnOk diff
label cmpDone
returnOk zeroI64b


operation findByteValueInMemoryRange
input findByteValueInMemoryRange byteBuffer CNullTerminatedByteString
input findByteValueInMemoryRange targetValue CSignedInt32
input findByteValueInMemoryRange byteCount CByteCount
output findByteValueInMemoryRange Result CSignedInt64 Void
effect findByteValueInMemoryRange read memory.buffer
memory findByteValueInMemoryRange heap no
memory findByteValueInMemoryRange stack max 1KiB
async findByteValueInMemoryRange no
purpose findByteValueInMemoryRange "Pure-AS memchr. Walks the first count bytes of buffer looking for value; returns the offset, or -1 if not found."
label startFindByteValueInMemoryRange
const zeroI64c I64 0
const oneI64c I64 1
const negOneI64c I64 -1
var fbIdx I64 0
label fbLoop
call fbAtEndCall math.greaterThanOrEqualI64
arg fbAtEndCall left fbIdx
arg fbAtEndCall right byteCount
run fbAtEndCall
bind fbAtEnd Bool fbAtEndCall
branchIf fbAtEnd fbNotFound
call fbLoadCall pointer.loadByte
arg fbLoadCall buffer byteBuffer
arg fbLoadCall offset fbIdx
run fbLoadCall
bind fbByte I8 fbLoadCall
call fbMatchCall math.equalI64
arg fbMatchCall left fbByte
arg fbMatchCall right targetValue
run fbMatchCall
bind fbMatch Bool fbMatchCall
branchIf fbMatch fbFound
call fbIncCall math.addI64
arg fbIncCall left fbIdx
arg fbIncCall right oneI64c
run fbIncCall
bind fbNext I64 fbIncCall
set fbIdx fbNext
branch fbLoop
label fbFound
returnOk fbIdx
label fbNotFound
returnOk negOneI64c


operation zeroMemoryBytes
input zeroMemoryBytes byteBuffer COpaqueMemoryAddress
input zeroMemoryBytes byteCount CByteCount
output zeroMemoryBytes Result CByteCount Void
effect zeroMemoryBytes write memory.buffer
memory zeroMemoryBytes heap no
async zeroMemoryBytes no
purpose zeroMemoryBytes "Like bzero. Writes count zeros into buffer. Returns count."
label startZeroMemoryBytes
const zeroZb I64 0
call fillCall fillMemoryBytesWithValue
arg fillCall buffer byteBuffer
arg fillCall value zeroZb
arg fillCall count byteCount
run fillCall
bindOk r CByteCount fillCall
returnOk r


operation hashMemoryBytesWithFnv1a
input hashMemoryBytesWithFnv1a byteBuffer CNullTerminatedByteString
input hashMemoryBytesWithFnv1a byteCount CByteCount
output hashMemoryBytesWithFnv1a Result CSignedInt64 Void
effect hashMemoryBytesWithFnv1a read memory.buffer
memory hashMemoryBytesWithFnv1a heap no
async hashMemoryBytesWithFnv1a no
purpose hashMemoryBytesWithFnv1a "FNV-1a 64-bit hash. Walk every byte of buffer (count bytes), XOR into a 64-bit accumulator initialized to 0xCBF29CE484222325, then multiply by 0x100000001B3. Pure AS: XOR is simulated as a + b - 2*(a*b)/(a OR b)... actually, AS has no bitwise. We approximate XOR via (a + b) mod 256 for individual bytes since for the FNV bias a single mismatched bit is fine. This isn't bit-exact FNV-1a, but produces a deterministic per-input hash useful for tests / dispatch tables."

label startHashMemoryBytesWithFnv1a
const oneOff I64 1
const twoFiveSix I64 256
const fnvPrime I64 1099511628211
# FNV offset basis is 0xCBF29CE484222325 == 14695981039346656037 (unsigned).
# As signed i64 that's -3750763034362895579. We use the signed form.
const fnvOffset CSignedInt64 -3750763034362895579

var hash I64 0
set hash fnvOffset
var idx I64 0

label hashLoop
call doneCall math.greaterThanOrEqualI64
arg doneCall left idx
arg doneCall right byteCount
run doneCall
bind done Bool doneCall
branchIf done hashDone

# byte = (loadByte + 256) % 256 (unsigned)
call loadCall pointer.loadByte
arg loadCall buffer byteBuffer
arg loadCall offset idx
run loadCall
bind byteRaw I8 loadCall
call normCall math.addI64
arg normCall left byteRaw
arg normCall right twoFiveSix
run normCall
bind normed I64 normCall
call modCall math.moduloI64
arg modCall left normed
arg modCall right twoFiveSix
run modCall
bind byteU I64 modCall

# Approximate XOR: hash = (hash + byteU * 257) for irregularity.
call mixCall math.multiplyI64
arg mixCall left byteU
arg mixCall right twoFiveSix
run mixCall
bind mixed I64 mixCall
call addByte math.addI64
arg addByte left hash
arg addByte right mixed
run addByte
bind addedByte I64 addByte
call addByte2 math.addI64
arg addByte2 left addedByte
arg addByte2 right byteU
run addByte2
bind addedByte2 I64 addByte2

# Multiply by FNV prime
call primeMul math.multiplyI64
arg primeMul left addedByte2
arg primeMul right fnvPrime
run primeMul
bind newHash I64 primeMul
set hash newHash

call idxInc math.addI64
arg idxInc left idx
arg idxInc right oneOff
run idxInc
bind idxNext I64 idxInc
set idx idxNext
branch hashLoop

label hashDone
returnOk hash


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
purpose main "Smoke-test copyMemoryBytes / moveMemoryBytesAllowOverlap / fillMemoryBytesWithValue / compareMemoryByteRanges / findByteValueInMemoryRange on a heap buffer. Prints OK."

label startMain

const allocSize CByteCount 16
call allocCall c.malloc
arg allocCall size allocSize
run allocCall
bind buf COpaqueMemoryAddress allocCall

const charA CSignedInt32 65
const fiveCount CByteCount 5
const aaaaa CNullTerminatedByteString "AAAAA"
const hello CNullTerminatedByteString "hello"
const zeroExp I64 0

call fillRun fillMemoryBytesWithValue
arg fillRun buffer buf
arg fillRun value charA
arg fillRun count fiveCount
run fillRun
bindOk fillRet CByteCount fillRun

call cmpRun compareMemoryByteRanges
arg cmpRun a buf
arg cmpRun b aaaaa
arg cmpRun count fiveCount
run cmpRun
bindOk cmpResult CSignedInt64 cmpRun
call cmpCheckCall math.equalI64
arg cmpCheckCall left cmpResult
arg cmpCheckCall right zeroExp
run cmpCheckCall
bind cmpOk Bool cmpCheckCall
branchIf cmpOk fillCheckPassed
branch testFailed
label fillCheckPassed

call copyRun copyMemoryBytes
arg copyRun dest buf
arg copyRun src hello
arg copyRun count fiveCount
run copyRun
bindOk copyRet CByteCount copyRun

call cmpRun2 compareMemoryByteRanges
arg cmpRun2 a buf
arg cmpRun2 b hello
arg cmpRun2 count fiveCount
run cmpRun2
bindOk cmp2Result CSignedInt64 cmpRun2
call cmp2CheckCall math.equalI64
arg cmp2CheckCall left cmp2Result
arg cmp2CheckCall right zeroExp
run cmp2CheckCall
bind cmp2Ok Bool cmp2CheckCall
branchIf cmp2Ok copyCheckPassed
branch testFailed
label copyCheckPassed

# findByteValueInMemoryRange: "hello" find 'l' returns 2.
const lowerL CSignedInt32 108
const twoExp I64 2
call findRun findByteValueInMemoryRange
arg findRun buffer buf
arg findRun value lowerL
arg findRun count fiveCount
run findRun
bindOk findRes CSignedInt64 findRun
call findCheckCall math.equalI64
arg findCheckCall left findRes
arg findCheckCall right twoExp
run findCheckCall
bind findOk Bool findCheckCall
branchIf findOk findCheckPassed
branch testFailed
label findCheckPassed

# moveMemoryBytesAllowOverlap with overlap: shift "hello" right by 1 inside buf.
# After: buf[0..5] = "hhello" (truncated to first 6 bytes only relevant)
# To verify, we'll just compare the moved range to "hello" at offset 1.
call addrOneCall pointer.offset
arg addrOneCall base buf
arg addrOneCall offset zeroExp
run addrOneCall
bind buf0 COpaqueMemoryAddress addrOneCall
const oneOff CByteCount 1
call addrOneShifted pointer.offset
arg addrOneShifted base buf
arg addrOneShifted offset oneOff
run addrOneShifted
bind buf1 COpaqueMemoryAddress addrOneShifted
call moveRun moveMemoryBytesAllowOverlap
arg moveRun dest buf1
arg moveRun src buf0
arg moveRun count fiveCount
run moveRun
bindOk moveRet CByteCount moveRun
# After: buf[1..6] should still equal "hello"
call cmpRun3 compareMemoryByteRanges
arg cmpRun3 a buf1
arg cmpRun3 b hello
arg cmpRun3 count fiveCount
run cmpRun3
bindOk cmp3Result CSignedInt64 cmpRun3
call cmp3CheckCall math.equalI64
arg cmp3CheckCall left cmp3Result
arg cmp3CheckCall right zeroExp
run cmp3CheckCall
bind cmp3Ok Bool cmp3CheckCall
branchIf cmp3Ok moveCheckPassed
branch testFailed
label moveCheckPassed

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

call freeCall c.free
arg freeCall ptr buf
run freeCall

const exitOk ExitCode 0
returnOk exitOk

label testFailed
const exitFail CSignedInt32 1
makeError testFailure MainError.TestFailed exitFail
returnError testFailure
