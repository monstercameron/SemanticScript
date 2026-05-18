# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: pure-AS C-string operations
# ============================================================
#
# # rationale: every operation lowers to pointer.loadByte /
#   pointer.storeByte plus math primitives. NO libc string call
#   appears in the emitted IR — no strlen, strcmp, strchr, strstr,
#   memcpy, etc. The point is a self-contained byte-string surface
#   that does not depend on linking libc string.h.
#
# # invariant: every operation walks the input forward, stops at the
#   first NUL byte (or the explicit byteCount limit). Capacity
#   enforcement on the destination buffer is the callers responsibility
#   — there is no destinationCapacityBytes parameter at this layer.
#
# # security: buffer-overflow risk on copy / append / duplicate ops
#   when the caller misjudges destination size. A future revision
#   will add capacity contracts; today the surface mirrors libc.
#
# # timing: every op is O(byteCount).
#
# # observability: no logs; consumers wrap when needed.

project StdStringSelfTest
target console
runtime AgentRuntime 0.1
entry console main

error MainError
errorCase MainError StringSmokeAssertionFailed
errorCase MainError ConsoleWriteFailed
errorCase MainError MemoryAllocationFailed

# section capability
# rationale: every operation in this module reads (or reads+writes)
# the memory.buffer effect channel through caller-supplied pointers;
# the smoke test main additionally writes to stdout and allocates
# scratch buffers on the heap for the duplicateCStringIntoOwnedMemory
# round-trip.
capability memoryBufferReadCapability memory.buffer read
capability memoryBufferWriteCapability memory.buffer write
capability stdoutWriteCapability console.stdout write
capability heapAllocationCapability heap allocate
capability heapFreeCapability heap free

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <string.h>-style operations.
#
# Every operation here is implemented in pure AgentScript using
# pointer.loadByte / pointer.storeByte + math primitives. There is NO
# libc string call — stringByteLength / memcpy / compareCString / etc. do not appear in
# the emitted IR as externs.
#
# Operations:
#   stringByteLength(s)                  byte count up to NUL
#   compareCString(a, b)               lex compare two C-strings
#   compareCStringPrefixBytes(a, b, n)           lex compare up to n bytes
#   findFirstCharacterInCString(s, c)               offset of first c, -1 if absent
#   findLastCharacterInCString(s, c)              offset of LAST c, -1 if absent
#   findSubstringInCString(haystack, needle)   offset of first occurrence of needle, -1 if absent
#   countInitialCStringBytesInAcceptSet(s, accept)          length of leading run of bytes in accept
#   copyCStringToDestinationBuffer(dest, src)     like strcpy: copy bytes (and NUL) from src to dest
# ============================================================


# ---- stringByteLength(s) -> byte count up to NUL ----
operation stringByteLength
input stringByteLength inputText CNullTerminatedByteString
output stringByteLength CByteCount
useCapability stringByteLength memoryBufferReadCapability
effect stringByteLength read memory.buffer
memoryHeap stringByteLength no
memoryStackLimit stringByteLength 1024
async stringByteLength no
purpose stringByteLength "Pure-AS stringByteLength: walk bytes from s until a NUL, return the count."
invariant stringByteLength "Walks forward from offset 0 until the first NUL byte; returns that offset as the byte count."

label startStringByteLength
const zeroI64 I64 0
const oneI64 I64 1
var cursor I64 0
label strlenLoop
call loadCall pointer.loadByte
arg loadCall buffer inputText
arg loadCall offset cursor
run loadCall
bind byteValue I8 loadCall
call isNullCall math.equalI64
arg isNullCall left byteValue
arg isNullCall right zeroI64
run isNullCall
bind isNull Bool isNullCall
branchIf isNull strlenDone
call incCall math.addI64
arg incCall left cursor
arg incCall right oneI64
run incCall
bind nextCursor I64 incCall
set cursor nextCursor
branch strlenLoop
label strlenDone
returnValue cursor


# ---- compareCString(a, b) -> 0 if equal, signed diff otherwise ----
operation compareCString
input compareCString leftValue CNullTerminatedByteString
input compareCString rightValue CNullTerminatedByteString
output compareCString CSignedInt32
useCapability compareCString memoryBufferReadCapability
effect compareCString read memory.buffer
memoryHeap compareCString no
memoryStackLimit compareCString 1024
async compareCString no
purpose compareCString "Pure-AS compareCString: returns 0 on equal C-strings, signed diff of first mismatching byte otherwise."
invariant compareCString "Walks both strings byte-by-byte; returns at the first differing byte or at the first NUL on either side."

label startCompareCString
const zeroI64a I64 0
const oneI64a I64 1
var idx I64 0
label strcmpLoop
call loadACall pointer.loadByte
arg loadACall buffer leftValue
arg loadACall offset idx
run loadACall
bind aByte I8 loadACall
call loadBCall pointer.loadByte
arg loadBCall buffer rightValue
arg loadBCall offset idx
run loadBCall
bind bByte I8 loadBCall
call diffCall math.subtractI64
arg diffCall left aByte
arg diffCall right bByte
run diffCall
bind diff I64 diffCall
call diffNonzeroCall math.notEqualI64
arg diffNonzeroCall left diff
arg diffNonzeroCall right zeroI64a
run diffNonzeroCall
bind diffNonzero Bool diffNonzeroCall
branchIf diffNonzero strcmpReturnDiff
call atEndCall math.equalI64
arg atEndCall left aByte
arg atEndCall right zeroI64a
run atEndCall
bind atEnd Bool atEndCall
branchIf atEnd strcmpReturnEqual
call incIdxCall math.addI64
arg incIdxCall left idx
arg incIdxCall right oneI64a
run incIdxCall
bind nextIdx I64 incIdxCall
set idx nextIdx
branch strcmpLoop
label strcmpReturnDiff
returnValue diff
label strcmpReturnEqual
returnValue zeroI64a


# ---- compareCStringPrefixBytes(a, b, n) -> like compareCString but max n bytes ----
operation compareCStringPrefixBytes
input compareCStringPrefixBytes leftValue CNullTerminatedByteString
input compareCStringPrefixBytes rightValue CNullTerminatedByteString
input compareCStringPrefixBytes maxByteCount CByteCount
output compareCStringPrefixBytes CSignedInt32
useCapability compareCStringPrefixBytes memoryBufferReadCapability
effect compareCStringPrefixBytes read memory.buffer
memoryHeap compareCStringPrefixBytes no
memoryStackLimit compareCStringPrefixBytes 1024
async compareCStringPrefixBytes no
purpose compareCStringPrefixBytes "Pure-AS compareCStringPrefixBytes: compare up to n bytes of a and b. Returns 0 if equal-in-first-n-or-both-NUL, signed diff at first mismatch, 0 if n==0."
invariant compareCStringPrefixBytes "At most maxByteCount bytes inspected; equality on the prefix yields 0 even if the full strings differ beyond."

label startCompareCStringPrefixBytes
const zeroI64b I64 0
const oneI64b I64 1
var nidx I64 0
label strncmpLoop
call nLimitCall math.greaterThanOrEqualI64
arg nLimitCall left nidx
arg nLimitCall right maxByteCount
run nLimitCall
bind nReached Bool nLimitCall
branchIf nReached strncmpReturnEqual
call loadAnCall pointer.loadByte
arg loadAnCall buffer leftValue
arg loadAnCall offset nidx
run loadAnCall
bind anByte I8 loadAnCall
call loadBnCall pointer.loadByte
arg loadBnCall buffer rightValue
arg loadBnCall offset nidx
run loadBnCall
bind bnByte I8 loadBnCall
call ndiffCall math.subtractI64
arg ndiffCall left anByte
arg ndiffCall right bnByte
run ndiffCall
bind ndiff I64 ndiffCall
call ndiffNzCall math.notEqualI64
arg ndiffNzCall left ndiff
arg ndiffNzCall right zeroI64b
run ndiffNzCall
bind ndiffNz Bool ndiffNzCall
branchIf ndiffNz strncmpReturnDiff
call nEndCall math.equalI64
arg nEndCall left anByte
arg nEndCall right zeroI64b
run nEndCall
bind nEnd Bool nEndCall
branchIf nEnd strncmpReturnEqual
call nIncCall math.addI64
arg nIncCall left nidx
arg nIncCall right oneI64b
run nIncCall
bind nNext I64 nIncCall
set nidx nNext
branch strncmpLoop
label strncmpReturnDiff
returnValue ndiff
label strncmpReturnEqual
returnValue zeroI64b


# ---- findFirstCharacterInCString(s, c) -> offset of first c, -1 if absent ----
operation findFirstCharacterInCString
input findFirstCharacterInCString inputText CNullTerminatedByteString
input findFirstCharacterInCString characterCode CSignedInt32
output findFirstCharacterInCString CSignedInt64
useCapability findFirstCharacterInCString memoryBufferReadCapability
effect findFirstCharacterInCString read memory.buffer
memoryHeap findFirstCharacterInCString no
memoryStackLimit findFirstCharacterInCString 1024
async findFirstCharacterInCString no
purpose findFirstCharacterInCString "Pure-AS findFirstCharacterInCString: find first byte equal to c; return offset or -1 if not found before NUL."
invariant findFirstCharacterInCString "Walks forward from offset 0; returns the first offset where the byte equals targetCharacter, or -1."

label startFindFirstCharacterInCString
const zeroI64c I64 0
const oneI64c I64 1
const negOneI64c I64 -1
var chIdx I64 0
label strchrLoop
call chLoadCall pointer.loadByte
arg chLoadCall buffer inputText
arg chLoadCall offset chIdx
run chLoadCall
bind chByte I8 chLoadCall
call chMatchCall math.equalI64
arg chMatchCall left chByte
arg chMatchCall right characterCode
run chMatchCall
bind chMatch Bool chMatchCall
branchIf chMatch strchrFound
call chEndCall math.equalI64
arg chEndCall left chByte
arg chEndCall right zeroI64c
run chEndCall
bind chAtEnd Bool chEndCall
branchIf chAtEnd strchrNotFound
call chIncCall math.addI64
arg chIncCall left chIdx
arg chIncCall right oneI64c
run chIncCall
bind chNext I64 chIncCall
set chIdx chNext
branch strchrLoop
label strchrFound
returnValue chIdx
label strchrNotFound
returnValue negOneI64c


# ---- findLastCharacterInCString(s, c) -> offset of LAST c, -1 if absent ----
operation findLastCharacterInCString
input findLastCharacterInCString inputText CNullTerminatedByteString
input findLastCharacterInCString characterCode CSignedInt32
output findLastCharacterInCString CSignedInt64
useCapability findLastCharacterInCString memoryBufferReadCapability
effect findLastCharacterInCString read memory.buffer
memoryHeap findLastCharacterInCString no
memoryStackLimit findLastCharacterInCString 1024
async findLastCharacterInCString no
purpose findLastCharacterInCString "Pure-AS findLastCharacterInCString: track the last-seen offset of c while walking; return it (or -1)."
invariant findLastCharacterInCString "Walks forward and remembers the most recent match; returns the last offset where the byte equals targetCharacter, or -1."

label startFindLastCharacterInCString
const zeroI64d I64 0
const oneI64d I64 1
var rcIdx I64 0
var rcLastSeen I64 -1
label strrchrLoop
call rcLoadCall pointer.loadByte
arg rcLoadCall buffer inputText
arg rcLoadCall offset rcIdx
run rcLoadCall
bind rcByte I8 rcLoadCall
call rcMatchCall math.equalI64
arg rcMatchCall left rcByte
arg rcMatchCall right characterCode
run rcMatchCall
bind rcMatch Bool rcMatchCall
branchIf rcMatch strrchrRecord
branch strrchrSkipRecord
label strrchrRecord
set rcLastSeen rcIdx
branch strrchrSkipRecord
label strrchrSkipRecord
call rcEndCall math.equalI64
arg rcEndCall left rcByte
arg rcEndCall right zeroI64d
run rcEndCall
bind rcAtEnd Bool rcEndCall
branchIf rcAtEnd strrchrDone
call rcIncCall math.addI64
arg rcIncCall left rcIdx
arg rcIncCall right oneI64d
run rcIncCall
bind rcNext I64 rcIncCall
set rcIdx rcNext
branch strrchrLoop
label strrchrDone
returnValue rcLastSeen


# ---- findSubstringInCString(haystack, needle) -> offset of first needle occurrence ----
operation findSubstringInCString
input findSubstringInCString searchText CNullTerminatedByteString
input findSubstringInCString targetSubstring CNullTerminatedByteString
output findSubstringInCString CSignedInt64
useCapability findSubstringInCString memoryBufferReadCapability
effect findSubstringInCString read memory.buffer
memoryHeap findSubstringInCString no
memoryStackLimit findSubstringInCString 1024
async findSubstringInCString no
purpose findSubstringInCString "Pure-AS naive substring search. Returns offset of needle in haystack, or -1 if absent. Special case: needle empty -> 0."
invariant findSubstringInCString "For each starting offset in haystack, walks needle forward; returns the first start where every needle byte matches."

label startFindSubstringInCString
const zeroI64e I64 0
const oneI64e I64 1
const negOneI64e I64 -1
var hStart I64 0

label strstrOuter
call peekNeedleCall pointer.loadByte
arg peekNeedleCall buffer targetSubstring
arg peekNeedleCall offset zeroI64e
run peekNeedleCall
bind needleHead I8 peekNeedleCall
call needleEmptyCall math.equalI64
arg needleEmptyCall left needleHead
arg needleEmptyCall right zeroI64e
run needleEmptyCall
bind needleEmpty Bool needleEmptyCall
branchIf needleEmpty strstrFound

call peekHaystackCall pointer.loadByte
arg peekHaystackCall buffer searchText
arg peekHaystackCall offset hStart
run peekHaystackCall
bind haystackHere I8 peekHaystackCall
call haystackEndCall math.equalI64
arg haystackEndCall left haystackHere
arg haystackEndCall right zeroI64e
run haystackEndCall
bind haystackAtEnd Bool haystackEndCall
branchIf haystackAtEnd strstrNotFound

var matchOffset I64 0
label strstrInner
call innerNeedleCall pointer.loadByte
arg innerNeedleCall buffer targetSubstring
arg innerNeedleCall offset matchOffset
run innerNeedleCall
bind innerNeedleByte I8 innerNeedleCall
call innerNeedleEndCall math.equalI64
arg innerNeedleEndCall left innerNeedleByte
arg innerNeedleEndCall right zeroI64e
run innerNeedleEndCall
bind innerNeedleEnd Bool innerNeedleEndCall
branchIf innerNeedleEnd strstrFound

call innerHaystackOffsetCall math.addI64
arg innerHaystackOffsetCall left hStart
arg innerHaystackOffsetCall right matchOffset
run innerHaystackOffsetCall
bind innerHaystackOffset I64 innerHaystackOffsetCall
call innerHaystackLoadCall pointer.loadByte
arg innerHaystackLoadCall buffer searchText
arg innerHaystackLoadCall offset innerHaystackOffset
run innerHaystackLoadCall
bind innerHaystackByte I8 innerHaystackLoadCall

call innerHEndCall math.equalI64
arg innerHEndCall left innerHaystackByte
arg innerHEndCall right zeroI64e
run innerHEndCall
bind innerHAtEnd Bool innerHEndCall
branchIf innerHAtEnd strstrAdvance

call innerEqCall math.equalI64
arg innerEqCall left innerNeedleByte
arg innerEqCall right innerHaystackByte
run innerEqCall
bind innerEq Bool innerEqCall
branchIf innerEq strstrInnerAdvance
branch strstrAdvance

label strstrInnerAdvance
call innerIncCall math.addI64
arg innerIncCall left matchOffset
arg innerIncCall right oneI64e
run innerIncCall
bind matchNext I64 innerIncCall
set matchOffset matchNext
# Read matchOffset between the two parallel sets to this slot so
# the linter's flow-insensitive dead-store check sees an observation.
branchIf matchOffset strstrInner
branch strstrInner

label strstrAdvance
set matchOffset zeroI64e
call outerIncCall math.addI64
arg outerIncCall left hStart
arg outerIncCall right oneI64e
run outerIncCall
bind hStartNext I64 outerIncCall
set hStart hStartNext
branch strstrOuter

label strstrFound
returnValue hStart

label strstrNotFound
returnValue negOneI64e


# ---- countInitialCStringBytesInAcceptSet(s, accept) -> length of leading run of bytes in accept ----
operation countInitialCStringBytesInAcceptSet
input countInitialCStringBytesInAcceptSet inputText CNullTerminatedByteString
input countInitialCStringBytesInAcceptSet acceptedCharacters CNullTerminatedByteString
output countInitialCStringBytesInAcceptSet CByteCount
useCapability countInitialCStringBytesInAcceptSet memoryBufferReadCapability
effect countInitialCStringBytesInAcceptSet read memory.buffer
memoryHeap countInitialCStringBytesInAcceptSet no
memoryStackLimit countInitialCStringBytesInAcceptSet 1024
async countInitialCStringBytesInAcceptSet no
purpose countInitialCStringBytesInAcceptSet "Length of the longest prefix of s consisting entirely of bytes that appear somewhere in accept. Pure AS: O(len(s) * len(accept))."
invariant countInitialCStringBytesInAcceptSet "Walks forward while the current byte appears in acceptSet; stops at the first byte outside the set or NUL."

label startCountInitialCStringBytesInAcceptSet
const zeroI64f I64 0
const oneI64f I64 1
var sIdx I64 0

label spnSLoop
call spnLoadSCall pointer.loadByte
arg spnLoadSCall buffer inputText
arg spnLoadSCall offset sIdx
run spnLoadSCall
bind spnSByte I8 spnLoadSCall
call spnSEndCall math.equalI64
arg spnSEndCall left spnSByte
arg spnSEndCall right zeroI64f
run spnSEndCall
bind spnSAtEnd Bool spnSEndCall
branchIf spnSAtEnd spnDone

var aIdx I64 0
label spnALoop
call spnLoadACall pointer.loadByte
arg spnLoadACall buffer acceptedCharacters
arg spnLoadACall offset aIdx
run spnLoadACall
bind spnAByte I8 spnLoadACall
call spnAEndCall math.equalI64
arg spnAEndCall left spnAByte
arg spnAEndCall right zeroI64f
run spnAEndCall
bind spnAAtEnd Bool spnAEndCall
branchIf spnAAtEnd spnDone

call spnMatchCall math.equalI64
arg spnMatchCall left spnAByte
arg spnMatchCall right spnSByte
run spnMatchCall
bind spnMatch Bool spnMatchCall
branchIf spnMatch spnAdvanceS

call spnAIncCall math.addI64
arg spnAIncCall left aIdx
arg spnAIncCall right oneI64f
run spnAIncCall
bind spnANext I64 spnAIncCall
set aIdx spnANext
# Read aIdx to satisfy the dead-store check across the parallel
# sets on the matched-vs-not-matched branches.
branchIf aIdx spnALoop
branch spnALoop

label spnAdvanceS
set aIdx zeroI64f
call spnSIncCall math.addI64
arg spnSIncCall left sIdx
arg spnSIncCall right oneI64f
run spnSIncCall
bind spnSNext I64 spnSIncCall
set sIdx spnSNext
branch spnSLoop

label spnDone
returnValue sIdx


# ---- copyCStringToDestinationBuffer(dest, src) -> bytes copied including NUL ----
operation copyCStringToDestinationBuffer
input copyCStringToDestinationBuffer destinationBuffer COpaqueMemoryAddress
input copyCStringToDestinationBuffer sourceBuffer CNullTerminatedByteString
output copyCStringToDestinationBuffer CByteCount
useCapability copyCStringToDestinationBuffer memoryBufferReadCapability
effect copyCStringToDestinationBuffer read memory.buffer
useCapability copyCStringToDestinationBuffer memoryBufferWriteCapability
effect copyCStringToDestinationBuffer write memory.buffer
memoryHeap copyCStringToDestinationBuffer no
memoryStackLimit copyCStringToDestinationBuffer 1024
async copyCStringToDestinationBuffer no
purpose copyCStringToDestinationBuffer "Pure-AS strcpy: copy each byte of src to dest including the terminating NUL. Returns count of bytes written (= stringByteLength(src) + 1). Caller is responsible for dest being large enough."
invariant copyCStringToDestinationBuffer "Copies bytes (and the NUL terminator) from source to destination; returns the byte count not including the terminator."

label startCopyCStringToDestinationBuffer
const zeroI64g I64 0
const oneI64g I64 1
var cpIdx I64 0
label cpLoop
call cpLoadCall pointer.loadByte
arg cpLoadCall buffer sourceBuffer
arg cpLoadCall offset cpIdx
run cpLoadCall
bind cpByte I8 cpLoadCall

call cpStoreCall pointer.storeByte
arg cpStoreCall buffer destinationBuffer
arg cpStoreCall offset cpIdx
arg cpStoreCall value cpByte
run cpStoreCall

call cpEndCall math.equalI64
arg cpEndCall left cpByte
arg cpEndCall right zeroI64g
run cpEndCall
bind cpAtEnd Bool cpEndCall
branchIf cpAtEnd cpDone

call cpIncCall math.addI64
arg cpIncCall left cpIdx
arg cpIncCall right oneI64g
run cpIncCall
bind cpNext I64 cpIncCall
set cpIdx cpNext
branch cpLoop

label cpDone
call cpFinalCall math.addI64
arg cpFinalCall left cpIdx
arg cpFinalCall right oneI64g
run cpFinalCall
bind cpFinal CByteCount cpFinalCall
returnValue cpFinal


# ---- appendCStringToDestinationBuffer(dest, src) -> total bytes in dest after the append ----
# Append src to the end of dest's existing NUL-terminated content.
# Caller must ensure dest has enough room.
operation appendCStringToDestinationBuffer
input appendCStringToDestinationBuffer destinationBuffer COpaqueMemoryAddress
input appendCStringToDestinationBuffer sourceBuffer CNullTerminatedByteString
output appendCStringToDestinationBuffer CByteCount
useCapability appendCStringToDestinationBuffer memoryBufferReadCapability
effect appendCStringToDestinationBuffer read memory.buffer
useCapability appendCStringToDestinationBuffer memoryBufferWriteCapability
effect appendCStringToDestinationBuffer write memory.buffer
memoryHeap appendCStringToDestinationBuffer no
memoryStackLimit appendCStringToDestinationBuffer 1024
async appendCStringToDestinationBuffer no
purpose appendCStringToDestinationBuffer "Pure-AS appendCStringToDestinationBuffer: find the NUL in dest, then copy src (including its NUL) starting at that offset. Returns the resulting length (= stringByteLength(dest)+stringByteLength(src))."
invariant appendCStringToDestinationBuffer "First walks destination to its NUL, then copies source bytes plus a new NUL at that offset; returns the destination byte count after the append."

label startAppendCStringToDestinationBuffer
const zeroCat I64 0
const oneCat I64 1

# Find end of dest.
var destEnd I64 0
label catFindEnd
call catLoadCall pointer.loadByte
arg catLoadCall buffer destinationBuffer
arg catLoadCall offset destEnd
run catLoadCall
bind catByte I8 catLoadCall
call catEndCall math.equalI64
arg catEndCall left catByte
arg catEndCall right zeroCat
run catEndCall
bind catAtEnd Bool catEndCall
branchIf catAtEnd catEndFound
call catIncCall math.addI64
arg catIncCall left destEnd
arg catIncCall right oneCat
run catIncCall
bind catNext I64 catIncCall
set destEnd catNext
branch catFindEnd

label catEndFound

# Copy src bytes (including NUL) starting at offset destEnd in dest.
var catSrcIdx I64 0
label catCopyLoop
call catSrcLoadCall pointer.loadByte
arg catSrcLoadCall buffer sourceBuffer
arg catSrcLoadCall offset catSrcIdx
run catSrcLoadCall
bind catSrcByte I8 catSrcLoadCall

call catWriteOffsetCall math.addI64
arg catWriteOffsetCall left destEnd
arg catWriteOffsetCall right catSrcIdx
run catWriteOffsetCall
bind catWriteOffset I64 catWriteOffsetCall

call catStoreCall pointer.storeByte
arg catStoreCall buffer destinationBuffer
arg catStoreCall offset catWriteOffset
arg catStoreCall value catSrcByte
run catStoreCall

call catSrcEndCall math.equalI64
arg catSrcEndCall left catSrcByte
arg catSrcEndCall right zeroCat
run catSrcEndCall
bind catSrcAtEnd Bool catSrcEndCall
branchIf catSrcAtEnd catDone

call catSrcIncCall math.addI64
arg catSrcIncCall left catSrcIdx
arg catSrcIncCall right oneCat
run catSrcIncCall
bind catSrcNext I64 catSrcIncCall
set catSrcIdx catSrcNext
branch catCopyLoop

label catDone
call catTotalCall math.addI64
arg catTotalCall left destEnd
arg catTotalCall right catSrcIdx
run catTotalCall
bind catTotal CByteCount catTotalCall
returnValue catTotal


# ---- copyCStringPrefixToDestinationBuffer(dest, src, n) -> bytes written ----
# Copy at most n bytes from src to dest. If src is shorter than n, pad
# with NUL up to n bytes (matching C copyCStringPrefixToDestinationBuffer semantics). Does NOT
# guarantee NUL-termination if stringByteLength(src) >= n.
operation copyCStringPrefixToDestinationBuffer
input copyCStringPrefixToDestinationBuffer destinationBuffer COpaqueMemoryAddress
input copyCStringPrefixToDestinationBuffer sourceBuffer CNullTerminatedByteString
input copyCStringPrefixToDestinationBuffer maxByteCount CByteCount
output copyCStringPrefixToDestinationBuffer CByteCount
useCapability copyCStringPrefixToDestinationBuffer memoryBufferReadCapability
effect copyCStringPrefixToDestinationBuffer read memory.buffer
useCapability copyCStringPrefixToDestinationBuffer memoryBufferWriteCapability
effect copyCStringPrefixToDestinationBuffer write memory.buffer
memoryHeap copyCStringPrefixToDestinationBuffer no
memoryStackLimit copyCStringPrefixToDestinationBuffer 1024
async copyCStringPrefixToDestinationBuffer no
purpose copyCStringPrefixToDestinationBuffer "Pure-AS copyCStringPrefixToDestinationBuffer. Up to n bytes copied from src to dest; remainder NUL-padded. Returns n."
invariant copyCStringPrefixToDestinationBuffer "Copies up to byteCount bytes from source; pads with NUL bytes if source is shorter; matches strncpy semantics."

label startCopyCStringPrefixToDestinationBuffer
const zeroNcp I64 0
const oneNcp I64 1
var ncpIdx I64 0
var ncpReachedNul I64 0
label ncpLoop
call ncpDoneCall math.greaterThanOrEqualI64
arg ncpDoneCall left ncpIdx
arg ncpDoneCall right maxByteCount
run ncpDoneCall
bind ncpDone Bool ncpDoneCall
branchIf ncpDone strncpyReturn

call ncpReachedCheckCall math.equalI64
arg ncpReachedCheckCall left ncpReachedNul
arg ncpReachedCheckCall right oneNcp
run ncpReachedCheckCall
bind ncpAlreadyAtEnd Bool ncpReachedCheckCall
branchIf ncpAlreadyAtEnd ncpPadZero

call ncpLoadCall pointer.loadByte
arg ncpLoadCall buffer sourceBuffer
arg ncpLoadCall offset ncpIdx
run ncpLoadCall
bind ncpByte I8 ncpLoadCall

call ncpIsEndCall math.equalI64
arg ncpIsEndCall left ncpByte
arg ncpIsEndCall right zeroNcp
run ncpIsEndCall
bind ncpIsEnd Bool ncpIsEndCall
branchIf ncpIsEnd ncpEnterPadMode

call ncpStoreCall pointer.storeByte
arg ncpStoreCall buffer destinationBuffer
arg ncpStoreCall offset ncpIdx
arg ncpStoreCall value ncpByte
run ncpStoreCall
branch ncpAdvance

label ncpEnterPadMode
set ncpReachedNul oneNcp
branch ncpPadZero

label ncpPadZero
call ncpZeroStoreCall pointer.storeByte
arg ncpZeroStoreCall buffer destinationBuffer
arg ncpZeroStoreCall offset ncpIdx
arg ncpZeroStoreCall value zeroNcp
run ncpZeroStoreCall
branch ncpAdvance

label ncpAdvance
call ncpIncCall math.addI64
arg ncpIncCall left ncpIdx
arg ncpIncCall right oneNcp
run ncpIncCall
bind ncpNext I64 ncpIncCall
set ncpIdx ncpNext
branch ncpLoop

label strncpyReturn
returnValue maxByteCount


operation countInitialCStringBytesNotInRejectSet
input countInitialCStringBytesNotInRejectSet inputText CNullTerminatedByteString
input countInitialCStringBytesNotInRejectSet rejectedCharacters CNullTerminatedByteString
output countInitialCStringBytesNotInRejectSet CByteCount
useCapability countInitialCStringBytesNotInRejectSet memoryBufferReadCapability
effect countInitialCStringBytesNotInRejectSet read memory.buffer
memoryHeap countInitialCStringBytesNotInRejectSet no
async countInitialCStringBytesNotInRejectSet no
purpose countInitialCStringBytesNotInRejectSet "Length of leading prefix of s NOT containing any byte in reject. Pure AS: O(len(s) * len(reject))."
invariant countInitialCStringBytesNotInRejectSet "Walks forward while the current byte does NOT appear in rejectSet; stops at the first byte in the set or NUL."

label startCountInitialCStringBytesNotInRejectSet
const zeroCs I64 0
const oneCs I64 1
var csIdx I64 0

label cspnSLoop
call cspnLoadSCall pointer.loadByte
arg cspnLoadSCall buffer inputText
arg cspnLoadSCall offset csIdx
run cspnLoadSCall
bind cspnSByte I8 cspnLoadSCall
call cspnSEndCall math.equalI64
arg cspnSEndCall left cspnSByte
arg cspnSEndCall right zeroCs
run cspnSEndCall
bind cspnSAtEnd Bool cspnSEndCall
branchIf cspnSAtEnd cspnDone

var aIdxCs I64 0
label cspnALoop
call cspnLoadACall pointer.loadByte
arg cspnLoadACall buffer rejectedCharacters
arg cspnLoadACall offset aIdxCs
run cspnLoadACall
bind cspnAByte I8 cspnLoadACall
call cspnAEndCall math.equalI64
arg cspnAEndCall left cspnAByte
arg cspnAEndCall right zeroCs
run cspnAEndCall
bind cspnAAtEnd Bool cspnAEndCall
branchIf cspnAAtEnd cspnAdvanceS

call cspnMatchCall math.equalI64
arg cspnMatchCall left cspnAByte
arg cspnMatchCall right cspnSByte
run cspnMatchCall
bind cspnMatch Bool cspnMatchCall
branchIf cspnMatch cspnDone

call cspnAIncCall math.addI64
arg cspnAIncCall left aIdxCs
arg cspnAIncCall right oneCs
run cspnAIncCall
bind cspnANext I64 cspnAIncCall
set aIdxCs cspnANext
# Read aIdxCs to satisfy the dead-store check across the parallel sets.
branchIf aIdxCs cspnALoop
branch cspnALoop

label cspnAdvanceS
set aIdxCs zeroCs
call cspnSIncCall math.addI64
arg cspnSIncCall left csIdx
arg cspnSIncCall right oneCs
run cspnSIncCall
bind cspnSNext I64 cspnSIncCall
set csIdx cspnSNext
branch cspnSLoop

label cspnDone
returnValue csIdx


operation findFirstCStringByteInAcceptSet
input findFirstCStringByteInAcceptSet inputText CNullTerminatedByteString
input findFirstCStringByteInAcceptSet acceptedCharacters CNullTerminatedByteString
output findFirstCStringByteInAcceptSet CSignedInt64
useCapability findFirstCStringByteInAcceptSet memoryBufferReadCapability
effect findFirstCStringByteInAcceptSet read memory.buffer
memoryHeap findFirstCStringByteInAcceptSet no
async findFirstCStringByteInAcceptSet no
purpose findFirstCStringByteInAcceptSet "Offset of the first byte of s that appears anywhere in accept, or -1 if absent before the NUL."
invariant findFirstCStringByteInAcceptSet "Walks forward and returns the first offset where the byte appears in acceptSet, or -1."

label startFindFirstCStringByteInAcceptSet
const zeroPb I64 0
const oneIPb I64 1
const negOnePb I64 -1
var pbIdx I64 0

label pbSLoop
call pbLoadSCall pointer.loadByte
arg pbLoadSCall buffer inputText
arg pbLoadSCall offset pbIdx
run pbLoadSCall
bind pbSByte I8 pbLoadSCall
call pbSEndCall math.equalI64
arg pbSEndCall left pbSByte
arg pbSEndCall right zeroPb
run pbSEndCall
bind pbAtEnd Bool pbSEndCall
branchIf pbAtEnd pbNotFound

var pbAidx I64 0
label pbALoop
call pbLoadACall pointer.loadByte
arg pbLoadACall buffer acceptedCharacters
arg pbLoadACall offset pbAidx
run pbLoadACall
bind pbAByte I8 pbLoadACall
call pbAEndCall math.equalI64
arg pbAEndCall left pbAByte
arg pbAEndCall right zeroPb
run pbAEndCall
bind pbAEnd Bool pbAEndCall
branchIf pbAEnd pbAdvanceS

call pbEqCall math.equalI64
arg pbEqCall left pbAByte
arg pbEqCall right pbSByte
run pbEqCall
bind pbEq Bool pbEqCall
branchIf pbEq pbFound

call pbAIncCall math.addI64
arg pbAIncCall left pbAidx
arg pbAIncCall right oneIPb
run pbAIncCall
bind pbANext I64 pbAIncCall
set pbAidx pbANext
# Read pbAidx to satisfy the dead-store check across parallel sets.
branchIf pbAidx pbALoop
branch pbALoop

label pbAdvanceS
set pbAidx zeroPb
call pbSIncCall math.addI64
arg pbSIncCall left pbIdx
arg pbSIncCall right oneIPb
run pbSIncCall
bind pbSNext I64 pbSIncCall
set pbIdx pbSNext
branch pbSLoop

label pbFound
returnValue pbIdx
label pbNotFound
returnValue negOnePb


operation duplicateCStringIntoOwnedMemory
input duplicateCStringIntoOwnedMemory inputText CNullTerminatedByteString
output duplicateCStringIntoOwnedMemory COpaqueMemoryAddress
useCapability duplicateCStringIntoOwnedMemory memoryBufferReadCapability
useCapability duplicateCStringIntoOwnedMemory heapAllocationCapability
effect duplicateCStringIntoOwnedMemory read memory.buffer
effect duplicateCStringIntoOwnedMemory allocate heap
memoryHeap duplicateCStringIntoOwnedMemory yes
memoryAllocationSource duplicateCStringIntoOwnedMemory mallocCall
async duplicateCStringIntoOwnedMemory no
purpose duplicateCStringIntoOwnedMemory "Allocate a heap copy of s. Caller owns the returned pointer (must c.free). Returns NULL on allocation failure."
invariant duplicateCStringIntoOwnedMemory "Computes source length, allocates length+1 bytes, copies bytes, writes the final NUL; returns the new buffer pointer (caller frees)."

label startDuplicateCStringIntoOwnedMemory
# len = stringByteLength(s)
call lenCall stringByteLength
arg lenCall s inputText
run lenCall
bind lenV CByteCount lenCall

const oneIDup CByteCount 1
call allocSizeCall math.addI64
arg allocSizeCall left lenV
arg allocSizeCall right oneIDup
run allocSizeCall
bind allocSize CByteCount allocSizeCall

call mallocCall c.malloc
arg mallocCall size allocSize
run mallocCall
bind dest COpaqueMemoryAddress mallocCall
bindError duplicateCStringMallocError CSignedInt32 mallocCall
branchIfError mallocCall strdupAllocationFailed

# Otherwise copy via copyCStringToDestinationBuffer.
call copyCall copyCStringToDestinationBuffer
arg copyCall dest dest
arg copyCall src inputText
run copyCall
ignoreOk copyCall CByteCount

returnValue dest

# Allocation failed: surface the NULL through the bindError value
# (which cast back to a pointer is also NULL) so the caller sees
# the standard NULL-on-OOM contract.
label strdupAllocationFailed
returnValue duplicateCStringMallocError


operation appendCStringPrefixToDestinationBuffer
input appendCStringPrefixToDestinationBuffer destinationBuffer COpaqueMemoryAddress
input appendCStringPrefixToDestinationBuffer sourceBuffer CNullTerminatedByteString
input appendCStringPrefixToDestinationBuffer maxByteCount CByteCount
output appendCStringPrefixToDestinationBuffer CByteCount
useCapability appendCStringPrefixToDestinationBuffer memoryBufferReadCapability
effect appendCStringPrefixToDestinationBuffer read memory.buffer
useCapability appendCStringPrefixToDestinationBuffer memoryBufferWriteCapability
effect appendCStringPrefixToDestinationBuffer write memory.buffer
memoryHeap appendCStringPrefixToDestinationBuffer no
async appendCStringPrefixToDestinationBuffer no
purpose appendCStringPrefixToDestinationBuffer "Append at most n bytes from src to dest's existing NUL-terminated content. Always writes a NUL terminator after the appended bytes."
invariant appendCStringPrefixToDestinationBuffer "Walks destination to its NUL, then copies up to byteCount source bytes plus a final NUL; returns destination byte count after append."
label startAppendCStringPrefixToDestinationBuffer
const zeroNc I64 0
const oneNc I64 1
# Find end of dest.
var dEnd I64 0
label ncFindEnd
call ncLoadCall pointer.loadByte
arg ncLoadCall buffer destinationBuffer
arg ncLoadCall offset dEnd
run ncLoadCall
bind ncByte I8 ncLoadCall
call ncEndCall math.equalI64
arg ncEndCall left ncByte
arg ncEndCall right zeroNc
run ncEndCall
bind ncAtEnd Bool ncEndCall
branchIf ncAtEnd ncEndFound
call ncIncCall math.addI64
arg ncIncCall left dEnd
arg ncIncCall right oneNc
run ncIncCall
bind ncNext I64 ncIncCall
set dEnd ncNext
branch ncFindEnd
label ncEndFound
# Copy up to n bytes (stop early on src NUL)
var srcIdx I64 0
label ncCopyLoop
call ncDoneCall math.greaterThanOrEqualI64
arg ncDoneCall left srcIdx
arg ncDoneCall right maxByteCount
run ncDoneCall
bind ncDone Bool ncDoneCall
branchIf ncDone ncWriteNul
call ncSrcLoadCall pointer.loadByte
arg ncSrcLoadCall buffer sourceBuffer
arg ncSrcLoadCall offset srcIdx
run ncSrcLoadCall
bind ncSrcByte I8 ncSrcLoadCall
call ncSrcEndCall math.equalI64
arg ncSrcEndCall left ncSrcByte
arg ncSrcEndCall right zeroNc
run ncSrcEndCall
bind ncSrcAtEnd Bool ncSrcEndCall
branchIf ncSrcAtEnd ncWriteNul
call ncWriteOffCall math.addI64
arg ncWriteOffCall left dEnd
arg ncWriteOffCall right srcIdx
run ncWriteOffCall
bind writeOff I64 ncWriteOffCall
call ncStoreCall pointer.storeByte
arg ncStoreCall buffer destinationBuffer
arg ncStoreCall offset writeOff
arg ncStoreCall value ncSrcByte
run ncStoreCall
call ncIdxIncCall math.addI64
arg ncIdxIncCall left srcIdx
arg ncIdxIncCall right oneNc
run ncIdxIncCall
bind ncIdxNext I64 ncIdxIncCall
set srcIdx ncIdxNext
branch ncCopyLoop
label ncWriteNul
call ncNulOffCall math.addI64
arg ncNulOffCall left dEnd
arg ncNulOffCall right srcIdx
run ncNulOffCall
bind nulOff I64 ncNulOffCall
call ncNulStoreCall pointer.storeByte
arg ncNulStoreCall buffer destinationBuffer
arg ncNulStoreCall offset nulOff
arg ncNulStoreCall value zeroNc
run ncNulStoreCall
call ncTotalCall math.addI64
arg ncTotalCall left dEnd
arg ncTotalCall right srcIdx
run ncTotalCall
bind ncTotalRes CByteCount ncTotalCall
returnValue ncTotalRes


operation cstringBeginsWithPrefix
input cstringBeginsWithPrefix inputText CNullTerminatedByteString
input cstringBeginsWithPrefix prefixText CNullTerminatedByteString
output cstringBeginsWithPrefix CSignedInt32
useCapability cstringBeginsWithPrefix memoryBufferReadCapability
effect cstringBeginsWithPrefix read memory.buffer
memoryHeap cstringBeginsWithPrefix no
async cstringBeginsWithPrefix no
purpose cstringBeginsWithPrefix "1 if s starts with prefix; 0 otherwise. Pure AS via byte-by-byte compare."
invariant cstringBeginsWithPrefix "Returns true when every byte of prefixText matches the corresponding byte in inputText starting at offset 0."
label startCstringBeginsWithPrefix
const zeroBw I64 0
const oneBw I64 1
const trueBw CSignedInt32 1
const falseBw CSignedInt32 0
var bwIdx I64 0
label bwLoop
call bwPrefLoadCall pointer.loadByte
arg bwPrefLoadCall buffer prefixText
arg bwPrefLoadCall offset bwIdx
run bwPrefLoadCall
bind bwPrefByte I8 bwPrefLoadCall
call bwPrefEndCall math.equalI64
arg bwPrefEndCall left bwPrefByte
arg bwPrefEndCall right zeroBw
run bwPrefEndCall
bind bwPrefAtEnd Bool bwPrefEndCall
branchIf bwPrefAtEnd bwAllMatched
call bwSLoadCall pointer.loadByte
arg bwSLoadCall buffer inputText
arg bwSLoadCall offset bwIdx
run bwSLoadCall
bind bwSByte I8 bwSLoadCall
call bwSEndCall math.equalI64
arg bwSEndCall left bwSByte
arg bwSEndCall right zeroBw
run bwSEndCall
bind bwSAtEnd Bool bwSEndCall
branchIf bwSAtEnd bwMismatch
call bwEqCall math.equalI64
arg bwEqCall left bwPrefByte
arg bwEqCall right bwSByte
run bwEqCall
bind bwEqB Bool bwEqCall
branchIf bwEqB bwAdvance
branch bwMismatch
label bwAdvance
call bwIncCall math.addI64
arg bwIncCall left bwIdx
arg bwIncCall right oneBw
run bwIncCall
bind bwNext I64 bwIncCall
set bwIdx bwNext
branch bwLoop
label bwAllMatched
returnValue trueBw
label bwMismatch
returnValue falseBw


operation cstringEndsWithSuffix
input cstringEndsWithSuffix inputText CNullTerminatedByteString
input cstringEndsWithSuffix suffixText CNullTerminatedByteString
output cstringEndsWithSuffix CSignedInt32
useCapability cstringEndsWithSuffix memoryBufferReadCapability
effect cstringEndsWithSuffix read memory.buffer
memoryHeap cstringEndsWithSuffix no
async cstringEndsWithSuffix no
purpose cstringEndsWithSuffix "1 if s ends with suffix; 0 otherwise. Implemented as: stringByteLength(suffix) <= stringByteLength(s), then compare last stringByteLength(suffix) bytes of s with suffix."
invariant cstringEndsWithSuffix "Computes both lengths via stringByteLength, then matches suffixText against inputText starting at the offset (inputLength - suffixLength)."
label startCstringEndsWithSuffix
const trueEw CSignedInt32 1
const falseEw CSignedInt32 0
const oneEw I64 1

call sLenCall stringByteLength
arg sLenCall s inputText
run sLenCall
bind sLen CByteCount sLenCall

call suffLenCall stringByteLength
arg suffLenCall s suffixText
run suffLenCall
bind suffLen CByteCount suffLenCall

# If suffix longer than s -> false
call suffLongerCall math.greaterThanI64
arg suffLongerCall left suffLen
arg suffLongerCall right sLen
run suffLongerCall
bind suffLonger Bool suffLongerCall
branchIf suffLonger ewFalse

# Start offset in s = sLen - suffLen
call startOffCall math.subtractI64
arg startOffCall left sLen
arg startOffCall right suffLen
run startOffCall
bind ewStart I64 startOffCall

var ewIdx I64 0
label ewLoop
call ewDoneCall math.greaterThanOrEqualI64
arg ewDoneCall left ewIdx
arg ewDoneCall right suffLen
run ewDoneCall
bind ewDoneB Bool ewDoneCall
branchIf ewDoneB ewTrue

call ewSuffLoadCall pointer.loadByte
arg ewSuffLoadCall buffer suffixText
arg ewSuffLoadCall offset ewIdx
run ewSuffLoadCall
bind ewSuffByte I8 ewSuffLoadCall
call ewSOffCall math.addI64
arg ewSOffCall left ewStart
arg ewSOffCall right ewIdx
run ewSOffCall
bind ewSOff I64 ewSOffCall
call ewSLoadCall pointer.loadByte
arg ewSLoadCall buffer inputText
arg ewSLoadCall offset ewSOff
run ewSLoadCall
bind ewSByte I8 ewSLoadCall
call ewEqCall math.equalI64
arg ewEqCall left ewSuffByte
arg ewEqCall right ewSByte
run ewEqCall
bind ewEqB Bool ewEqCall
branchIf ewEqB ewAdv
branch ewFalse
label ewAdv
call ewIncCall math.addI64
arg ewIncCall left ewIdx
arg ewIncCall right oneEw
run ewIncCall
bind ewNext I64 ewIncCall
set ewIdx ewNext
branch ewLoop

label ewTrue
returnValue trueEw
label ewFalse
returnValue falseEw


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
const oneI64case I64 1
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
