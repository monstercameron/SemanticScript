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
effect stringByteLength read memory.buffer
memoryHeap stringByteLength no
memoryStackLimit stringByteLength 1024
async stringByteLength no
purpose stringByteLength "Pure-AS stringByteLength: walk bytes from s until a NUL, return the count."

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
effect compareCString read memory.buffer
memoryHeap compareCString no
memoryStackLimit compareCString 1024
async compareCString no
purpose compareCString "Pure-AS compareCString: returns 0 on equal C-strings, signed diff of first mismatching byte otherwise."

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
effect compareCStringPrefixBytes read memory.buffer
memoryHeap compareCStringPrefixBytes no
memoryStackLimit compareCStringPrefixBytes 1024
async compareCStringPrefixBytes no
purpose compareCStringPrefixBytes "Pure-AS compareCStringPrefixBytes: compare up to n bytes of a and b. Returns 0 if equal-in-first-n-or-both-NUL, signed diff at first mismatch, 0 if n==0."

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
effect findFirstCharacterInCString read memory.buffer
memoryHeap findFirstCharacterInCString no
memoryStackLimit findFirstCharacterInCString 1024
async findFirstCharacterInCString no
purpose findFirstCharacterInCString "Pure-AS findFirstCharacterInCString: find first byte equal to c; return offset or -1 if not found before NUL."

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
effect findLastCharacterInCString read memory.buffer
memoryHeap findLastCharacterInCString no
memoryStackLimit findLastCharacterInCString 1024
async findLastCharacterInCString no
purpose findLastCharacterInCString "Pure-AS findLastCharacterInCString: track the last-seen offset of c while walking; return it (or -1)."

label startFindLastCharacterInCString
const zeroI64d I64 0
const oneI64d I64 1
const negOneI64d I64 -1
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
effect findSubstringInCString read memory.buffer
memoryHeap findSubstringInCString no
memoryStackLimit findSubstringInCString 1024
async findSubstringInCString no
purpose findSubstringInCString "Pure-AS naive substring search. Returns offset of needle in haystack, or -1 if absent. Special case: needle empty -> 0."

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
effect countInitialCStringBytesInAcceptSet read memory.buffer
memoryHeap countInitialCStringBytesInAcceptSet no
memoryStackLimit countInitialCStringBytesInAcceptSet 1024
async countInitialCStringBytesInAcceptSet no
purpose countInitialCStringBytesInAcceptSet "Length of the longest prefix of s consisting entirely of bytes that appear somewhere in accept. Pure AS: O(len(s) * len(accept))."

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
effect copyCStringToDestinationBuffer read memory.buffer
effect copyCStringToDestinationBuffer write memory.buffer
memoryHeap copyCStringToDestinationBuffer no
memoryStackLimit copyCStringToDestinationBuffer 1024
async copyCStringToDestinationBuffer no
purpose copyCStringToDestinationBuffer "Pure-AS strcpy: copy each byte of src to dest including the terminating NUL. Returns count of bytes written (= stringByteLength(src) + 1). Caller is responsible for dest being large enough."

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
effect appendCStringToDestinationBuffer read memory.buffer
effect appendCStringToDestinationBuffer write memory.buffer
memoryHeap appendCStringToDestinationBuffer no
memoryStackLimit appendCStringToDestinationBuffer 1024
async appendCStringToDestinationBuffer no
purpose appendCStringToDestinationBuffer "Pure-AS appendCStringToDestinationBuffer: find the NUL in dest, then copy src (including its NUL) starting at that offset. Returns the resulting length (= stringByteLength(dest)+stringByteLength(src))."

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
effect copyCStringPrefixToDestinationBuffer read memory.buffer
effect copyCStringPrefixToDestinationBuffer write memory.buffer
memoryHeap copyCStringPrefixToDestinationBuffer no
memoryStackLimit copyCStringPrefixToDestinationBuffer 1024
async copyCStringPrefixToDestinationBuffer no
purpose copyCStringPrefixToDestinationBuffer "Pure-AS copyCStringPrefixToDestinationBuffer. Up to n bytes copied from src to dest; remainder NUL-padded. Returns n."

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
effect countInitialCStringBytesNotInRejectSet read memory.buffer
memoryHeap countInitialCStringBytesNotInRejectSet no
async countInitialCStringBytesNotInRejectSet no
purpose countInitialCStringBytesNotInRejectSet "Length of leading prefix of s NOT containing any byte in reject. Pure AS: O(len(s) * len(reject))."

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
effect findFirstCStringByteInAcceptSet read memory.buffer
memoryHeap findFirstCStringByteInAcceptSet no
async findFirstCStringByteInAcceptSet no
purpose findFirstCStringByteInAcceptSet "Offset of the first byte of s that appears anywhere in accept, or -1 if absent before the NUL."

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
effect duplicateCStringIntoOwnedMemory read memory.buffer
effect duplicateCStringIntoOwnedMemory allocate heap
memoryHeap duplicateCStringIntoOwnedMemory yes
async duplicateCStringIntoOwnedMemory no
purpose duplicateCStringIntoOwnedMemory "Allocate a heap copy of s. Caller owns the returned pointer (must c.free). Returns NULL on allocation failure."

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

# If malloc returned NULL, return NULL.
call nullCheckCall pointer.isNull
arg nullCheckCall pointer dest
run nullCheckCall
bind isNull Bool nullCheckCall
branchIf isNull strdupNull

# Otherwise copy via copyCStringToDestinationBuffer.
call copyCall copyCStringToDestinationBuffer
arg copyCall dest dest
arg copyCall src inputText
run copyCall
ignoreOk copyCall CByteCount

returnValue dest

label strdupNull
returnValue dest


operation appendCStringPrefixToDestinationBuffer
input appendCStringPrefixToDestinationBuffer destinationBuffer COpaqueMemoryAddress
input appendCStringPrefixToDestinationBuffer sourceBuffer CNullTerminatedByteString
input appendCStringPrefixToDestinationBuffer maxByteCount CByteCount
output appendCStringPrefixToDestinationBuffer CByteCount
effect appendCStringPrefixToDestinationBuffer read memory.buffer
effect appendCStringPrefixToDestinationBuffer write memory.buffer
memoryHeap appendCStringPrefixToDestinationBuffer no
async appendCStringPrefixToDestinationBuffer no
purpose appendCStringPrefixToDestinationBuffer "Append at most n bytes from src to dest's existing NUL-terminated content. Always writes a NUL terminator after the appended bytes."
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
call ncSrcLoad pointer.loadByte
arg ncSrcLoad buffer sourceBuffer
arg ncSrcLoad offset srcIdx
run ncSrcLoad
bind ncSrcByte I8 ncSrcLoad
call ncSrcEnd math.equalI64
arg ncSrcEnd left ncSrcByte
arg ncSrcEnd right zeroNc
run ncSrcEnd
bind ncSrcAtEnd Bool ncSrcEnd
branchIf ncSrcAtEnd ncWriteNul
call ncWriteOff math.addI64
arg ncWriteOff left dEnd
arg ncWriteOff right srcIdx
run ncWriteOff
bind writeOff I64 ncWriteOff
call ncStore pointer.storeByte
arg ncStore buffer destinationBuffer
arg ncStore offset writeOff
arg ncStore value ncSrcByte
run ncStore
call ncIdxInc math.addI64
arg ncIdxInc left srcIdx
arg ncIdxInc right oneNc
run ncIdxInc
bind ncIdxNext I64 ncIdxInc
set srcIdx ncIdxNext
branch ncCopyLoop
label ncWriteNul
call ncNulOff math.addI64
arg ncNulOff left dEnd
arg ncNulOff right srcIdx
run ncNulOff
bind nulOff I64 ncNulOff
call ncNulStore pointer.storeByte
arg ncNulStore buffer destinationBuffer
arg ncNulStore offset nulOff
arg ncNulStore value zeroNc
run ncNulStore
call ncTotal math.addI64
arg ncTotal left dEnd
arg ncTotal right srcIdx
run ncTotal
bind ncTotalRes CByteCount ncTotal
returnValue ncTotalRes


operation cstringBeginsWithPrefix
input cstringBeginsWithPrefix inputText CNullTerminatedByteString
input cstringBeginsWithPrefix prefixText CNullTerminatedByteString
output cstringBeginsWithPrefix CSignedInt32
effect cstringBeginsWithPrefix read memory.buffer
memoryHeap cstringBeginsWithPrefix no
async cstringBeginsWithPrefix no
purpose cstringBeginsWithPrefix "1 if s starts with prefix; 0 otherwise. Pure AS via byte-by-byte compare."
label startCstringBeginsWithPrefix
const zeroBw I64 0
const oneBw I64 1
const trueBw CSignedInt32 1
const falseBw CSignedInt32 0
var bwIdx I64 0
label bwLoop
call bwPrefLoad pointer.loadByte
arg bwPrefLoad buffer prefixText
arg bwPrefLoad offset bwIdx
run bwPrefLoad
bind bwPrefByte I8 bwPrefLoad
call bwPrefEnd math.equalI64
arg bwPrefEnd left bwPrefByte
arg bwPrefEnd right zeroBw
run bwPrefEnd
bind bwPrefAtEnd Bool bwPrefEnd
branchIf bwPrefAtEnd bwAllMatched
call bwSLoad pointer.loadByte
arg bwSLoad buffer inputText
arg bwSLoad offset bwIdx
run bwSLoad
bind bwSByte I8 bwSLoad
call bwSEnd math.equalI64
arg bwSEnd left bwSByte
arg bwSEnd right zeroBw
run bwSEnd
bind bwSAtEnd Bool bwSEnd
branchIf bwSAtEnd bwMismatch
call bwEq math.equalI64
arg bwEq left bwPrefByte
arg bwEq right bwSByte
run bwEq
bind bwEqB Bool bwEq
branchIf bwEqB bwAdvance
branch bwMismatch
label bwAdvance
call bwInc math.addI64
arg bwInc left bwIdx
arg bwInc right oneBw
run bwInc
bind bwNext I64 bwInc
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
effect cstringEndsWithSuffix read memory.buffer
memoryHeap cstringEndsWithSuffix no
async cstringEndsWithSuffix no
purpose cstringEndsWithSuffix "1 if s ends with suffix; 0 otherwise. Implemented as: stringByteLength(suffix) <= stringByteLength(s), then compare last stringByteLength(suffix) bytes of s with suffix."
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
call startOff math.subtractI64
arg startOff left sLen
arg startOff right suffLen
run startOff
bind ewStart I64 startOff

var ewIdx I64 0
label ewLoop
call ewDone math.greaterThanOrEqualI64
arg ewDone left ewIdx
arg ewDone right suffLen
run ewDone
bind ewDoneB Bool ewDone
branchIf ewDoneB ewTrue

call ewSuffLoad pointer.loadByte
arg ewSuffLoad buffer suffixText
arg ewSuffLoad offset ewIdx
run ewSuffLoad
bind ewSuffByte I8 ewSuffLoad
call ewSOffCall math.addI64
arg ewSOffCall left ewStart
arg ewSOffCall right ewIdx
run ewSOffCall
bind ewSOff I64 ewSOffCall
call ewSLoad pointer.loadByte
arg ewSLoad buffer inputText
arg ewSLoad offset ewSOff
run ewSLoad
bind ewSByte I8 ewSLoad
call ewEq math.equalI64
arg ewEq left ewSuffByte
arg ewEq right ewSByte
run ewEq
bind ewEqB Bool ewEq
branchIf ewEqB ewAdv
branch ewFalse
label ewAdv
call ewInc math.addI64
arg ewInc left ewIdx
arg ewInc right oneEw
run ewInc
bind ewNext I64 ewInc
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
effect main allocate heap
effect main write console.stdout
memoryHeap main yes
async main no
purpose main "Smoke-test every string operation. Prints OK on success."

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
call l1 stringByteLength
arg l1 s hello
run l1
bindOk l1Res CByteCount l1
call l1Check math.equalI64
arg l1Check left l1Res
arg l1Check right fiveLen
run l1Check
bind l1Ok Bool l1Check
branchIf l1Ok l1OkLabel
branch testFailed
label l1OkLabel

# compareCString("Hello", "Hello") == 0
call c1 compareCString
arg c1 a hello
arg c1 b helloCopy
run c1
bindOk c1Res CSignedInt32 c1
call c1Check math.equalI64
arg c1Check left c1Res
arg c1Check right zeroI32
run c1Check
bind c1Ok Bool c1Check
branchIf c1Ok c1OkLabel
branch testFailed
label c1OkLabel

# compareCStringPrefixBytes("Hello, World", "Hello", 5) == 0
call nc1 compareCStringPrefixBytes
arg nc1 a helloComma
arg nc1 b hello
arg nc1 n fiveLen
run nc1
bindOk nc1Res CSignedInt32 nc1
call nc1Check math.equalI64
arg nc1Check left nc1Res
arg nc1Check right zeroI32
run nc1Check
bind nc1Ok Bool nc1Check
branchIf nc1Ok nc1OkLabel
branch testFailed
label nc1OkLabel

# findFirstCharacterInCString("Hello", 'l') == 2
const lowerL CSignedInt32 108
call ch1 findFirstCharacterInCString
arg ch1 s hello
arg ch1 c lowerL
run ch1
bindOk ch1Res CSignedInt64 ch1
call ch1Check math.equalI64
arg ch1Check left ch1Res
arg ch1Check right twoI64
run ch1Check
bind ch1Ok Bool ch1Check
branchIf ch1Ok ch1OkLabel
branch testFailed
label ch1OkLabel

# findLastCharacterInCString("Hello", 'l') == 3
call rch1 findLastCharacterInCString
arg rch1 s hello
arg rch1 c lowerL
run rch1
bindOk rch1Res CSignedInt64 rch1
call rch1Check math.equalI64
arg rch1Check left rch1Res
arg rch1Check right threeI64
run rch1Check
bind rch1Ok Bool rch1Check
branchIf rch1Ok rch1OkLabel
branch testFailed
label rch1OkLabel

# findSubstringInCString("Hello, World", "lo,") == 3
call ss1 findSubstringInCString
arg ss1 haystack helloComma
arg ss1 needle lo
run ss1
bindOk ss1Res CSignedInt64 ss1
call ss1Check math.equalI64
arg ss1Check left ss1Res
arg ss1Check right threeI64
run ss1Check
bind ss1Ok Bool ss1Check
branchIf ss1Ok ss1OkLabel
branch testFailed
label ss1OkLabel

# findSubstringInCString("Hello, World", "xyz") == -1
call ss2 findSubstringInCString
arg ss2 haystack helloComma
arg ss2 needle xyz
run ss2
bindOk ss2Res CSignedInt64 ss2
call ss2Check math.equalI64
arg ss2Check left ss2Res
arg ss2Check right negOneI64test
run ss2Check
bind ss2Ok Bool ss2Check
branchIf ss2Ok ss2OkLabel
branch testFailed
label ss2OkLabel

# countInitialCStringBytesInAcceptSet("12345abc", "0123456789") == 5
call sp1 countInitialCStringBytesInAcceptSet
arg sp1 s justDigits
arg sp1 accept digits
run sp1
bindOk sp1Res CByteCount sp1
call sp1Check math.equalI64
arg sp1Check left sp1Res
arg sp1Check right fiveLen
run sp1Check
bind sp1Ok Bool sp1Check
branchIf sp1Ok sp1OkLabel
branch testFailed
label sp1OkLabel

# copyCStringToDestinationBuffer hello -> heap buffer, then compareCString it
const bufSize CByteCount 16
call alloc1 c.malloc
arg alloc1 size bufSize
run alloc1
bind dest1 COpaqueMemoryAddress alloc1

call cc1 copyCStringToDestinationBuffer
arg cc1 dest dest1
arg cc1 src hello
run cc1
bindOk cc1Res CByteCount cc1

call cc1Cmp compareCString
arg cc1Cmp a dest1
arg cc1Cmp b hello
run cc1Cmp
bindOk cc1CmpRes CSignedInt32 cc1Cmp
call cc1Check math.equalI64
arg cc1Check left cc1CmpRes
arg cc1Check right zeroI32
run cc1Check
bind cc1Ok Bool cc1Check
branchIf cc1Ok cc1OkLabel
branch testFailed
label cc1OkLabel

call free1 c.free
arg free1 ptr dest1
run free1

# appendCStringToDestinationBuffer into a buffer that already has "Hello"; append "!" -> "Hello!"
const bufSize2 CByteCount 32
const helloExc CNullTerminatedByteString "Hello!"
const exclSuffix CNullTerminatedByteString "!"
call alloc2 c.malloc
arg alloc2 size bufSize2
run alloc2
bind dest2 COpaqueMemoryAddress alloc2
call seed2 copyCStringToDestinationBuffer
arg seed2 dest dest2
arg seed2 src hello
run seed2
ignoreOk seed2 CByteCount
call cat2 appendCStringToDestinationBuffer
arg cat2 dest dest2
arg cat2 src exclSuffix
run cat2
ignoreOk cat2 CByteCount
call catCmp compareCString
arg catCmp a dest2
arg catCmp b helloExc
run catCmp
bindOk catCmpRes CSignedInt32 catCmp
call catCheckCall math.equalI64
arg catCheckCall left catCmpRes
arg catCheckCall right zeroI32
run catCheckCall
bind catOk Bool catCheckCall
branchIf catOk catOkLabel
branch testFailed
label catOkLabel
call free2 c.free
arg free2 ptr dest2
run free2

# copyCStringPrefixToDestinationBuffer hello -> 16-byte buffer, pad rest with zeros.
const sixteenLen CByteCount 16
call alloc3 c.malloc
arg alloc3 size sixteenLen
run alloc3
bind dest3 COpaqueMemoryAddress alloc3
call ncp1 copyCStringPrefixToDestinationBuffer
arg ncp1 dest dest3
arg ncp1 src hello
arg ncp1 n sixteenLen
run ncp1
ignoreOk ncp1 CByteCount
# Verify first 5 bytes are "Hello", rest are NUL.
call ncpCmp compareCStringPrefixBytes
arg ncpCmp a dest3
arg ncpCmp b hello
arg ncpCmp n fiveLen
run ncpCmp
bindOk ncpCmpRes CSignedInt32 ncpCmp
call ncpCheckCall math.equalI64
arg ncpCheckCall left ncpCmpRes
arg ncpCheckCall right zeroI32
run ncpCheckCall
bind ncpOk Bool ncpCheckCall
branchIf ncpOk ncpOkLabel
branch testFailed
label ncpOkLabel
call free3 c.free
arg free3 ptr dest3
run free3

# countInitialCStringBytesNotInRejectSet("hello,world", ",") == 5 (the comma is at index 5)
const helloWorld CNullTerminatedByteString "hello,world"
const commaStr CNullTerminatedByteString ","
call csn1 countInitialCStringBytesNotInRejectSet
arg csn1 s helloWorld
arg csn1 reject commaStr
run csn1
bindOk csn1Res CByteCount csn1
call csn1Check math.equalI64
arg csn1Check left csn1Res
arg csn1Check right fiveLen
run csn1Check
bind csn1Ok Bool csn1Check
branchIf csn1Ok csn1OkLabel
branch testFailed
label csn1OkLabel

# findFirstCStringByteInAcceptSet("hello,world", ",.;") == 5
const punctSet CNullTerminatedByteString ",.;"
call pbk1 findFirstCStringByteInAcceptSet
arg pbk1 s helloWorld
arg pbk1 accept punctSet
run pbk1
bindOk pbk1Res CSignedInt64 pbk1
call pbk1Check math.equalI64
arg pbk1Check left pbk1Res
arg pbk1Check right fiveLen
run pbk1Check
bind pbk1Ok Bool pbk1Check
branchIf pbk1Ok pbk1OkLabel
branch testFailed
label pbk1OkLabel

# duplicateCStringIntoOwnedMemory("Hello") returns a heap copy that compareCString's equal to original
call sd1 duplicateCStringIntoOwnedMemory
arg sd1 s hello
run sd1
bindOk sd1Res COpaqueMemoryAddress sd1
call sd1NullCheck pointer.isNull
arg sd1NullCheck pointer sd1Res
run sd1NullCheck
bind sd1IsNull Bool sd1NullCheck
branchIf sd1IsNull testFailed
call sd1Cmp compareCString
arg sd1Cmp a sd1Res
arg sd1Cmp b hello
run sd1Cmp
bindOk sd1CmpRes CSignedInt32 sd1Cmp
call sd1Check math.equalI64
arg sd1Check left sd1CmpRes
arg sd1Check right zeroI32
run sd1Check
bind sd1Ok Bool sd1Check
branchIf sd1Ok sd1OkLabel
branch testFailed
label sd1OkLabel
call sd1Free c.free
arg sd1Free ptr sd1Res
run sd1Free

# cstringBeginsWithPrefix("Hello, World", "Hello") == 1
const oneI32trueChk CSignedInt32 1
call bw1 cstringBeginsWithPrefix
arg bw1 s helloComma
arg bw1 prefix hello
run bw1
bindOk bw1Res CSignedInt32 bw1
call bw1Check math.equalI64
arg bw1Check left bw1Res
arg bw1Check right oneI32trueChk
run bw1Check
bind bw1Ok Bool bw1Check
branchIf bw1Ok bw1OkLabel
branch testFailed
label bw1OkLabel

# cstringEndsWithSuffix("Hello, World", "World") - need an actual "World" string
const worldOnly CNullTerminatedByteString "World"
call ew1 cstringEndsWithSuffix
arg ew1 s helloComma
arg ew1 suffix worldOnly
run ew1
bindOk ew1Res CSignedInt32 ew1
call ew1Check math.equalI64
arg ew1Check left ew1Res
arg ew1Check right oneI32trueChk
run ew1Check
bind ew1Ok Bool ew1Check
branchIf ew1Ok ew1OkLabel
branch testFailed
label ew1OkLabel

# appendCStringPrefixToDestinationBuffer: seed with "Hi", append "there!" max 4 -> "Hithere"
const bufSizeNc CByteCount 32
const hi CNullTerminatedByteString "Hi"
const thereMore CNullTerminatedByteString "there!"
const expectedHiThere CNullTerminatedByteString "Hither"
const fourNc CByteCount 4
call allocNc c.malloc
arg allocNc size bufSizeNc
run allocNc
bind destNc COpaqueMemoryAddress allocNc
call seedNc copyCStringToDestinationBuffer
arg seedNc dest destNc
arg seedNc src hi
run seedNc
ignoreOk seedNc CByteCount
call ncatCall appendCStringPrefixToDestinationBuffer
arg ncatCall dest destNc
arg ncatCall src thereMore
arg ncatCall n fourNc
run ncatCall
ignoreOk ncatCall CByteCount
call ncCmp compareCString
arg ncCmp a destNc
arg ncCmp b expectedHiThere
run ncCmp
bindOk ncCmpRes CSignedInt32 ncCmp
call ncCheckCall math.equalI64
arg ncCheckCall left ncCmpRes
arg ncCheckCall right zeroI32
run ncCheckCall
bind ncOk Bool ncCheckCall
branchIf ncOk ncOkLabel
branch testFailed
label ncOkLabel
call freeNc c.free
arg freeNc ptr destNc
run freeNc

# Print OK
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
makeError testFailure MainError.StringSmokeAssertionFailed exitFail
returnError testFailure
