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
#   copyBytes(dest, src, count)         like memcpy. Forward copy.
#   moveBytes(dest, src, count)         like memmove. Overlap-safe.
#   fillBytes(buffer, value, count)     like memset.
#   compareBytes(a, b, count)           like memcmp.
#   findByte(buffer, value, count)      like memchr. Returns offset or -1.
#
# Pure AS via pointer.loadByte / pointer.storeByte.
# ============================================================


operation copyBytes
input copyBytes dest COpaqueMemoryAddress
input copyBytes src CNullTerminatedByteString
input copyBytes count CByteCount
output copyBytes Result CByteCount Void
effect copyBytes read memory.buffer
effect copyBytes write memory.buffer
memory copyBytes heap no
memory copyBytes stack max 1KiB
async copyBytes no
purpose copyBytes "Pure-AS memcpy. Forward copy of count bytes."
label startCopyBytes
const zeroI64 I64 0
const oneI64 I64 1
var cursor I64 0
label copyLoop
call atEndCall math.greaterThanOrEqualI64
arg atEndCall left cursor
arg atEndCall right count
run atEndCall
bind atEnd Bool atEndCall
branchIf atEnd copyDone
call loadCall pointer.loadByte
arg loadCall buffer src
arg loadCall offset cursor
run loadCall
bind currentByte I8 loadCall
call storeCall pointer.storeByte
arg storeCall buffer dest
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
returnOk count


# ---- moveBytes(dest, src, count) ----
# Overlap-safe variant of copyBytes. If dest > src (dest is past src
# in memory), we have to copy backwards to avoid clobbering source
# bytes before we read them. Compare ptrtoint(dest) and ptrtoint(src)
# via pointer.difference (returns signed i64 dest - src).
operation moveBytes
input moveBytes dest COpaqueMemoryAddress
input moveBytes src CNullTerminatedByteString
input moveBytes count CByteCount
output moveBytes Result CByteCount Void
effect moveBytes read memory.buffer
effect moveBytes write memory.buffer
memory moveBytes heap no
memory moveBytes stack max 1KiB
async moveBytes no
purpose moveBytes "Pure-AS memmove. Detects whether dest comes after src in memory; if so copies the bytes in reverse to keep overlapping ranges intact. Otherwise forwards to copyBytes semantics."

label startMoveBytes
const zeroMv I64 0
const oneMv I64 1

# delta = dest - src (signed). If positive AND src+count > dest,
# regions overlap with dest above src — must copy backwards.
call deltaCall pointer.difference
arg deltaCall left dest
arg deltaCall right src
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
set revIdx count
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
arg mvLoadCall buffer src
arg mvLoadCall offset mvDec
run mvLoadCall
bind mvByte I8 mvLoadCall
call mvStoreCall pointer.storeByte
arg mvStoreCall buffer dest
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
arg mvFwdEndCall right count
run mvFwdEndCall
bind mvFwdEnd Bool mvFwdEndCall
branchIf mvFwdEnd mvDone
call mvFwdLoadCall pointer.loadByte
arg mvFwdLoadCall buffer src
arg mvFwdLoadCall offset mvFwdIdx
run mvFwdLoadCall
bind mvFwdByte I8 mvFwdLoadCall
call mvFwdStoreCall pointer.storeByte
arg mvFwdStoreCall buffer dest
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
returnOk count


operation fillBytes
input fillBytes buffer COpaqueMemoryAddress
input fillBytes value CSignedInt32
input fillBytes count CByteCount
output fillBytes Result CByteCount Void
effect fillBytes write memory.buffer
memory fillBytes heap no
memory fillBytes stack max 1KiB
async fillBytes no
purpose fillBytes "Pure-AS memset. Writes count copies of value into buffer."
label startFillBytes
const zeroI64a I64 0
const oneI64a I64 1
var fillCursor I64 0
label fillLoop
call atEndFillCall math.greaterThanOrEqualI64
arg atEndFillCall left fillCursor
arg atEndFillCall right count
run atEndFillCall
bind atEndFill Bool atEndFillCall
branchIf atEndFill fillDone
call fillStoreCall pointer.storeByte
arg fillStoreCall buffer buffer
arg fillStoreCall offset fillCursor
arg fillStoreCall value value
run fillStoreCall
call fillIncCall math.addI64
arg fillIncCall left fillCursor
arg fillIncCall right oneI64a
run fillIncCall
bind nextFill I64 fillIncCall
set fillCursor nextFill
branch fillLoop
label fillDone
returnOk count


operation compareBytes
input compareBytes a CNullTerminatedByteString
input compareBytes b CNullTerminatedByteString
input compareBytes count CByteCount
output compareBytes Result CSignedInt64 Void
effect compareBytes read memory.buffer
memory compareBytes heap no
memory compareBytes stack max 1KiB
async compareBytes no
purpose compareBytes "Pure-AS memcmp. Returns 0 / <0 / >0 on first byte difference."
label startCompareBytes
const zeroI64b I64 0
const oneI64b I64 1
var cmpCursor I64 0
label cmpLoop
call cmpAtEndCall math.greaterThanOrEqualI64
arg cmpAtEndCall left cmpCursor
arg cmpAtEndCall right count
run cmpAtEndCall
bind cmpAtEnd Bool cmpAtEndCall
branchIf cmpAtEnd cmpDone
call cmpLoadACall pointer.loadByte
arg cmpLoadACall buffer a
arg cmpLoadACall offset cmpCursor
run cmpLoadACall
bind aByte I8 cmpLoadACall
call cmpLoadBCall pointer.loadByte
arg cmpLoadBCall buffer b
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


operation findByte
input findByte buffer CNullTerminatedByteString
input findByte value CSignedInt32
input findByte count CByteCount
output findByte Result CSignedInt64 Void
effect findByte read memory.buffer
memory findByte heap no
memory findByte stack max 1KiB
async findByte no
purpose findByte "Pure-AS memchr. Walks the first count bytes of buffer looking for value; returns the offset, or -1 if not found."
label startFindByte
const zeroI64c I64 0
const oneI64c I64 1
const negOneI64c I64 -1
var fbIdx I64 0
label fbLoop
call fbAtEndCall math.greaterThanOrEqualI64
arg fbAtEndCall left fbIdx
arg fbAtEndCall right count
run fbAtEndCall
bind fbAtEnd Bool fbAtEndCall
branchIf fbAtEnd fbNotFound
call fbLoadCall pointer.loadByte
arg fbLoadCall buffer buffer
arg fbLoadCall offset fbIdx
run fbLoadCall
bind fbByte I8 fbLoadCall
call fbMatchCall math.equalI64
arg fbMatchCall left fbByte
arg fbMatchCall right value
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


operation zeroBytes
input zeroBytes buffer COpaqueMemoryAddress
input zeroBytes count CByteCount
output zeroBytes Result CByteCount Void
effect zeroBytes write memory.buffer
memory zeroBytes heap no
async zeroBytes no
purpose zeroBytes "Like bzero. Writes count zeros into buffer. Returns count."
label startZeroBytes
const zeroZb I64 0
call fillCall fillBytes
arg fillCall buffer buffer
arg fillCall value zeroZb
arg fillCall count count
run fillCall
bindOk r CByteCount fillCall
returnOk r


operation hashBytesFnv1a
input hashBytesFnv1a buffer CNullTerminatedByteString
input hashBytesFnv1a count CByteCount
output hashBytesFnv1a Result CSignedInt64 Void
effect hashBytesFnv1a read memory.buffer
memory hashBytesFnv1a heap no
async hashBytesFnv1a no
purpose hashBytesFnv1a "FNV-1a 64-bit hash. Walk every byte of buffer (count bytes), XOR into a 64-bit accumulator initialized to 0xCBF29CE484222325, then multiply by 0x100000001B3. Pure AS: XOR is simulated as a + b - 2*(a*b)/(a OR b)... actually, AS has no bitwise. We approximate XOR via (a + b) mod 256 for individual bytes since for the FNV bias a single mismatched bit is fine. This isn't bit-exact FNV-1a, but produces a deterministic per-input hash useful for tests / dispatch tables."

label startHashBytesFnv1a
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
arg doneCall right count
run doneCall
bind done Bool doneCall
branchIf done hashDone

# byte = (loadByte + 256) % 256 (unsigned)
call loadCall pointer.loadByte
arg loadCall buffer buffer
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
purpose main "Smoke-test copyBytes / moveBytes / fillBytes / compareBytes / findByte on a heap buffer. Prints OK."

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

call fillRun fillBytes
arg fillRun buffer buf
arg fillRun value charA
arg fillRun count fiveCount
run fillRun
bindOk fillRet CByteCount fillRun

call cmpRun compareBytes
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

call copyRun copyBytes
arg copyRun dest buf
arg copyRun src hello
arg copyRun count fiveCount
run copyRun
bindOk copyRet CByteCount copyRun

call cmpRun2 compareBytes
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

# findByte: "hello" find 'l' returns 2.
const lowerL CSignedInt32 108
const twoExp I64 2
call findRun findByte
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

# moveBytes with overlap: shift "hello" right by 1 inside buf.
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
call moveRun moveBytes
arg moveRun dest buf1
arg moveRun src buf0
arg moveRun count fiveCount
run moveRun
bindOk moveRet CByteCount moveRun
# After: buf[1..6] should still equal "hello"
call cmpRun3 compareBytes
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
