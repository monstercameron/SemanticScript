# ============================================================
# Third stdlib import smoke (metadata-cluster modules)
# ============================================================
#
# # rationale: the constants-style modules (char / constants /
#   stddef / errno / errno_more / signal_more) expose their surface
#   primarily through module-scope `domainLiteral` declarations, not
#   operations. This file proves those literals are reachable
#   through `importModule` and resolve to the right values. Two
#   small total-op modules (iso646 / bit) round out the sample.
#
# # invariant: every imported constant matches its canonical
#   spec value; the two operations (evaluateIso646NotKeyword and
#   isSignedInt64BitSet) return the documented Bool outcome.
#
# # security: pure value-level checks; no I/O beyond writing OK.
#
# # timing: every check is O(1); whole test runs in microseconds.
#
# # observability: prints `OK\n` on full pass.

project StdlibImportSmokeMetadata
target console
runtime AgentRuntime 0.1
entry console stdlibImportSmokeMetadataMain

error MainError
errorCase MainError StdlibImportMetadataSmokeAssertionFailed
errorCase MainError ConsoleWriteFailed

# section capability
# rationale: smoke writes a single OK line to stdout.
capability stdoutWriteCapability console.stdout write

# ----- imports under test (eight metadata-cluster modules) -----
importModule char
importModule constants
importModule stddef
importModule errno
importModule errno_more
importModule signal_more
importModule iso646
importModule bit

operation stdlibImportSmokeMetadataMain
input stdlibImportSmokeMetadataMain console Console
output stdlibImportSmokeMetadataMain Result ExitCode MainError
useCapability stdlibImportSmokeMetadataMain stdoutWriteCapability
effect stdlibImportSmokeMetadataMain write console.stdout
memoryHeap stdlibImportSmokeMetadataMain no
async stdlibImportSmokeMetadataMain no
purpose stdlibImportSmokeMetadataMain "Verify char / constants / stddef / errno / errno_more / signal_more / iso646 / bit domainLiterals and operations resolve correctly through importModule."
invariant stdlibImportSmokeMetadataMain "Every imported value equals its expected literal; final exit 0; stdout is 'OK\\n'."

label startStdlibImportSmokeMetadataMain

# ---- char: asciiNewlineCharacterCode == 10 ----
const tenExpectedForNewlineImport CSignedInt32 10
call checkAsciiNewlineCall math.equalI64
arg checkAsciiNewlineCall left asciiNewlineCharacterCode
arg checkAsciiNewlineCall right tenExpectedForNewlineImport
run checkAsciiNewlineCall
bind asciiNewlineOk Bool checkAsciiNewlineCall
branchIf asciiNewlineOk asciiNewlineHolds
branch stdlibImportMetadataAssertionFailed
label asciiNewlineHolds

# ---- char: asciiDeleteCharacterCode == 127 ----
const oneHundredTwentySevenExpectedImport CSignedInt32 127
call checkAsciiDeleteCall math.equalI64
arg checkAsciiDeleteCall left asciiDeleteCharacterCode
arg checkAsciiDeleteCall right oneHundredTwentySevenExpectedImport
run checkAsciiDeleteCall
bind asciiDeleteOk Bool checkAsciiDeleteCall
branchIf asciiDeleteOk asciiDeleteHolds
branch stdlibImportMetadataAssertionFailed
label asciiDeleteHolds

# ---- constants: mathematicalPiFloat64 == 3.141592653589793 ----
const piLiteralExpectedImport CFloat64 3.141592653589793
call checkPiConstantCall math.equalF64
arg checkPiConstantCall left mathematicalPiFloat64
arg checkPiConstantCall right piLiteralExpectedImport
run checkPiConstantCall
bind piConstantOk Bool checkPiConstantCall
branchIf piConstantOk piConstantHolds
branch stdlibImportMetadataAssertionFailed
label piConstantHolds

# ---- constants: mathematicalEulerNumberFloat64 == 2.718281828459045 ----
const eulerNumberExpectedImport CFloat64 2.718281828459045
call checkEulerConstantCall math.equalF64
arg checkEulerConstantCall left mathematicalEulerNumberFloat64
arg checkEulerConstantCall right eulerNumberExpectedImport
run checkEulerConstantCall
bind eulerConstantOk Bool checkEulerConstantCall
branchIf eulerConstantOk eulerConstantHolds
branch stdlibImportMetadataAssertionFailed
label eulerConstantHolds

# ---- stddef: byteSizeOfOpaquePointer == 8 (x86-64 ABI) ----
const eightExpectedForPointerByteSizeImport CSignedInt64 8
call checkPointerByteSizeCall math.equalI64
arg checkPointerByteSizeCall left byteSizeOfOpaquePointer
arg checkPointerByteSizeCall right eightExpectedForPointerByteSizeImport
run checkPointerByteSizeCall
bind pointerByteSizeOk Bool checkPointerByteSizeCall
branchIf pointerByteSizeOk pointerByteSizeHolds
branch stdlibImportMetadataAssertionFailed
label pointerByteSizeHolds

# ---- stddef: byteSizeOfFloat64 == 8 ----
call checkFloat64ByteSizeCall math.equalI64
arg checkFloat64ByteSizeCall left byteSizeOfFloat64
arg checkFloat64ByteSizeCall right eightExpectedForPointerByteSizeImport
run checkFloat64ByteSizeCall
bind float64ByteSizeOk Bool checkFloat64ByteSizeCall
branchIf float64ByteSizeOk float64ByteSizeHolds
branch stdlibImportMetadataAssertionFailed
label float64ByteSizeHolds

# ---- errno: fileNotFoundErrorNumber == 2 (POSIX ENOENT) ----
const twoExpectedForEnoentImport CSignedInt32 2
call checkEnoentCall math.equalI64
arg checkEnoentCall left fileNotFoundErrorNumber
arg checkEnoentCall right twoExpectedForEnoentImport
run checkEnoentCall
bind enoentOk Bool checkEnoentCall
branchIf enoentOk enoentHolds
branch stdlibImportMetadataAssertionFailed
label enoentHolds

# ---- errno: lookupErrnoMessageCString(2) returns a non-empty string ----
call lookupEnoentMessageCall lookupErrnoMessageCString
arg lookupEnoentMessageCall errorNumber fileNotFoundErrorNumber
run lookupEnoentMessageCall
bind enoentMessageText CNullTerminatedByteString lookupEnoentMessageCall
const zeroByteOffsetForMessageImport CByteCount 0
call peekFirstMessageByteCall pointer.loadByte
arg peekFirstMessageByteCall buffer enoentMessageText
arg peekFirstMessageByteCall offset zeroByteOffsetForMessageImport
run peekFirstMessageByteCall
bind enoentFirstByteValue I8 peekFirstMessageByteCall
const nullByteForEnoentMessageImport CSignedInt64 0
call detectEnoentMessageNonEmptyCall math.notEqualI64
arg detectEnoentMessageNonEmptyCall left enoentFirstByteValue
arg detectEnoentMessageNonEmptyCall right nullByteForEnoentMessageImport
run detectEnoentMessageNonEmptyCall
bind enoentMessageNonEmpty Bool detectEnoentMessageNonEmptyCall
branchIf enoentMessageNonEmpty enoentMessageHolds
branch stdlibImportMetadataAssertionFailed
label enoentMessageHolds

# ---- errno_more: tryAgainErrorNumber == 11 (POSIX EAGAIN) ----
const elevenExpectedForEagainImport CSignedInt32 11
call checkEagainCall math.equalI64
arg checkEagainCall left tryAgainErrorNumber
arg checkEagainCall right elevenExpectedForEagainImport
run checkEagainCall
bind eagainOk Bool checkEagainCall
branchIf eagainOk eagainHolds
branch stdlibImportMetadataAssertionFailed
label eagainHolds

# ---- errno_more: operationTimedOutErrorNumber == 110 (POSIX ETIMEDOUT) ----
const oneHundredTenExpectedForEtimedoutImport CSignedInt32 110
call checkEtimedoutCall math.equalI64
arg checkEtimedoutCall left operationTimedOutErrorNumber
arg checkEtimedoutCall right oneHundredTenExpectedForEtimedoutImport
run checkEtimedoutCall
bind etimedoutOk Bool checkEtimedoutCall
branchIf etimedoutOk etimedoutHolds
branch stdlibImportMetadataAssertionFailed
label etimedoutHolds

# ---- signal_more: killSignalNumber == 9 (POSIX SIGKILL) ----
const nineExpectedForSigkillImport CSignedInt32 9
call checkSigkillCall math.equalI64
arg checkSigkillCall left killSignalNumber
arg checkSigkillCall right nineExpectedForSigkillImport
run checkSigkillCall
bind sigkillOk Bool checkSigkillCall
branchIf sigkillOk sigkillHolds
branch stdlibImportMetadataAssertionFailed
label sigkillHolds

# ---- signal_more: hangupSignalNumber == 1 (POSIX SIGHUP) ----
const oneExpectedForSighupImport CSignedInt32 1
call checkSighupCall math.equalI64
arg checkSighupCall left hangupSignalNumber
arg checkSighupCall right oneExpectedForSighupImport
run checkSighupCall
bind sighupOk Bool checkSighupCall
branchIf sighupOk sighupHolds
branch stdlibImportMetadataAssertionFailed
label sighupHolds

# ---- iso646: evaluateIso646NotKeyword(0) == true ----
const integerZeroForIso646Import CSignedInt64 0
call assertIso646NotZeroCall evaluateIso646NotKeyword
arg assertIso646NotZeroCall inputValue integerZeroForIso646Import
run assertIso646NotZeroCall
bind iso646NotZeroResult Bool assertIso646NotZeroCall
branchIf iso646NotZeroResult iso646NotZeroHolds
branch stdlibImportMetadataAssertionFailed
label iso646NotZeroHolds

# ---- iso646: evaluateIso646NotEqualKeyword(1, 2) == true ----
const integerOneForIso646Import CSignedInt64 1
const integerTwoForIso646Import CSignedInt64 2
call assertIso646NotEqualCall evaluateIso646NotEqualKeyword
arg assertIso646NotEqualCall leftValue integerOneForIso646Import
arg assertIso646NotEqualCall rightValue integerTwoForIso646Import
run assertIso646NotEqualCall
bind iso646NotEqualResult Bool assertIso646NotEqualCall
branchIf iso646NotEqualResult iso646NotEqualHolds
branch stdlibImportMetadataAssertionFailed
label iso646NotEqualHolds

# ---- bit: isSignedInt64BitSet(48, 4) == true (48 == 0b110000, bit 4 set) ----
const fortyEightForBitImport CSignedInt64 48
const fourthBitIndexForBitImport CSignedInt64 4
call assertBitSetImportCall isSignedInt64BitSet
arg assertBitSetImportCall inputValue fortyEightForBitImport
arg assertBitSetImportCall bitIndex fourthBitIndexForBitImport
run assertBitSetImportCall
bind bitSetImportResult Bool assertBitSetImportCall
branchIf bitSetImportResult bitSetImportHolds
branch stdlibImportMetadataAssertionFailed
label bitSetImportHolds

# ---- bit: shiftSignedInt64BitsLeft(3, 4) == 48 ----
const threeForShiftLeftImport CSignedInt64 3
const fortyEightExpectedForShiftLeftImport CSignedInt64 48
call assertShiftLeftImportCall shiftSignedInt64BitsLeft
arg assertShiftLeftImportCall inputValue threeForShiftLeftImport
arg assertShiftLeftImportCall bitIndex fourthBitIndexForBitImport
run assertShiftLeftImportCall
bind shiftLeftImportResult CSignedInt64 assertShiftLeftImportCall
call checkShiftLeftImportCall math.equalI64
arg checkShiftLeftImportCall left shiftLeftImportResult
arg checkShiftLeftImportCall right fortyEightExpectedForShiftLeftImport
run checkShiftLeftImportCall
bind shiftLeftImportOk Bool checkShiftLeftImportCall
branchIf shiftLeftImportOk shiftLeftImportHolds
branch stdlibImportMetadataAssertionFailed
label shiftLeftImportHolds

# All metadata-cluster checks held.
const metadataImportSuccessMessage CNullTerminatedByteString "OK"
call writeMetadataImportSuccessCall console.writeLine
arg writeMetadataImportSuccessCall console console
arg writeMetadataImportSuccessCall text metadataImportSuccessMessage
run writeMetadataImportSuccessCall
ignoreOk writeMetadataImportSuccessCall CSignedInt32
bindError metadataImportConsoleWriteError CSignedInt32 writeMetadataImportSuccessCall
branchIfError writeMetadataImportSuccessCall metadataImportConsoleWriteFailed
const metadataImportExitOk ExitCode 0
returnOk metadataImportExitOk

label metadataImportConsoleWriteFailed
makeError metadataImportConsoleWriteFailure MainError.ConsoleWriteFailed metadataImportConsoleWriteError
returnError metadataImportConsoleWriteFailure

label stdlibImportMetadataAssertionFailed
makeError stdlibImportMetadataFailure MainError.StdlibImportMetadataSmokeAssertionFailed
returnError stdlibImportMetadataFailure
