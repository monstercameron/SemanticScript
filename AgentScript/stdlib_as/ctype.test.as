# ============================================================
# AGENTSCRIPT STDLIB TESTS: ctype
# ============================================================
#
# Companion smoke + extended unit tests for stdlib_as/ctype.as.
# Imports the ctype module and exercises every classifier and
# both case-mapping operations end-to-end, including boundary and
# off-by-one cases that are the most common <ctype.h> bugs.
#
# Pattern: stdlib_as/foo.as ships pure-module operations only;
# stdlib_as/foo.test.as carries every smoke / unit test for it.

project StdCtypeTest
target console
runtime AgentRuntime 0.1
entry console main

importModule ctype

error MainError
errorCase MainError CtypeSmokeAssertionFailed
errorCase MainError ConsoleWriteFailed

# section capability
# rationale: smoke-test main writes a single OK line to stdout.
capability stdoutWriteCapability console.stdout write

# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
useCapability main stdoutWriteCapability
effect main write console.stdout
memoryHeap main no
memoryStackLimit main 1024
async main no
purpose main "Smoke-test every classifier and case mapper; print OK on success, returnError otherwise."
invariant main "Every predicate asserted is satisfied or the assertion-failure path runs."
label startMain

const digit5Code CSignedInt32 53
const lowerHCode CSignedInt32 104
const upperHCode CSignedInt32 72
const exclamationMarkCode CSignedInt32 33
const upperFHexCode CSignedInt32 70
const nullByteCode CSignedInt32 0
const tabByteCode CSignedInt32 9
const lineFeedByteCode CSignedInt32 10
const spaceByteCode CSignedInt32 32

# isAsciiDecimalDigitCode('5') == true
call assertDigit5Call isAsciiDecimalDigitCode
arg assertDigit5Call characterCode digit5Code
run assertDigit5Call
bind digit5IsDigit Bool assertDigit5Call
branchIf digit5IsDigit digit5Holds
branch smokeAssertionFailed
label digit5Holds

# isAsciiLetterCode('h') == true
call assertLetterHCall isAsciiLetterCode
arg assertLetterHCall characterCode lowerHCode
run assertLetterHCall
bind lowerHIsLetter Bool assertLetterHCall
branchIf lowerHIsLetter letterHHolds
branch smokeAssertionFailed
label letterHHolds

# isAsciiLetterOrDigitCode('5') == true
call assertAlnumDigitCall isAsciiLetterOrDigitCode
arg assertAlnumDigitCall characterCode digit5Code
run assertAlnumDigitCall
bind digit5IsAlnum Bool assertAlnumDigitCall
branchIf digit5IsAlnum alnumDigitHolds
branch smokeAssertionFailed
label alnumDigitHolds

# isAsciiLetterOrDigitCode('!') == false
call assertAlnumPunctCall isAsciiLetterOrDigitCode
arg assertAlnumPunctCall characterCode exclamationMarkCode
run assertAlnumPunctCall
bind exclamationIsAlnum Bool assertAlnumPunctCall
branchIf exclamationIsAlnum smokeAssertionFailed

# isAsciiHexDigitCode('F') == true
call assertHexCall isAsciiHexDigitCode
arg assertHexCall characterCode upperFHexCode
run assertHexCall
bind upperFIsHexDigit Bool assertHexCall
branchIf upperFIsHexDigit hexHolds
branch smokeAssertionFailed
label hexHolds

# isAsciiWhitespaceCode(' ') == true
call assertWhitespaceSpaceCall isAsciiWhitespaceCode
arg assertWhitespaceSpaceCall characterCode spaceByteCode
run assertWhitespaceSpaceCall
bind spaceIsWhitespace Bool assertWhitespaceSpaceCall
branchIf spaceIsWhitespace whitespaceSpaceHolds
branch smokeAssertionFailed
label whitespaceSpaceHolds

# isAsciiBlankCode('\t') == true
call assertBlankTabCall isAsciiBlankCode
arg assertBlankTabCall characterCode tabByteCode
run assertBlankTabCall
bind tabIsBlank Bool assertBlankTabCall
branchIf tabIsBlank blankTabHolds
branch smokeAssertionFailed
label blankTabHolds

# isAsciiBlankCode('\n') == false
call assertBlankLineFeedCall isAsciiBlankCode
arg assertBlankLineFeedCall characterCode lineFeedByteCode
run assertBlankLineFeedCall
bind lineFeedIsBlank Bool assertBlankLineFeedCall
branchIf lineFeedIsBlank smokeAssertionFailed

# isAsciiControlCode(0) == true
call assertControlNullCall isAsciiControlCode
arg assertControlNullCall characterCode nullByteCode
run assertControlNullCall
bind nullIsControl Bool assertControlNullCall
branchIf nullIsControl controlNullHolds
branch smokeAssertionFailed
label controlNullHolds

# isAsciiPrintableCode(' ') == true
call assertPrintableSpaceCall isAsciiPrintableCode
arg assertPrintableSpaceCall characterCode spaceByteCode
run assertPrintableSpaceCall
bind spaceIsPrintable Bool assertPrintableSpaceCall
branchIf spaceIsPrintable printableSpaceHolds
branch smokeAssertionFailed
label printableSpaceHolds

# isAsciiGraphicalCode(' ') == false (space is not graphical)
call assertGraphicalSpaceCall isAsciiGraphicalCode
arg assertGraphicalSpaceCall characterCode spaceByteCode
run assertGraphicalSpaceCall
bind spaceIsGraphical Bool assertGraphicalSpaceCall
branchIf spaceIsGraphical smokeAssertionFailed

# isAsciiPunctuationCode('!') == true
call assertPunctuationExclamationCall isAsciiPunctuationCode
arg assertPunctuationExclamationCall characterCode exclamationMarkCode
run assertPunctuationExclamationCall
bind exclamationIsPunctuation Bool assertPunctuationExclamationCall
branchIf exclamationIsPunctuation punctuationExclamationHolds
branch smokeAssertionFailed
label punctuationExclamationHolds

# convertAsciiLetterCodeToUppercase('h') == 'H'
call assertToUpperCall convertAsciiLetterCodeToUppercase
arg assertToUpperCall characterCode lowerHCode
run assertToUpperCall
bind upperConversionResult CSignedInt32 assertToUpperCall
call checkToUpperCall math.equalI64
arg checkToUpperCall left upperConversionResult
arg checkToUpperCall right upperHCode
run checkToUpperCall
bind toUpperOk Bool checkToUpperCall
branchIf toUpperOk toUpperHolds
branch smokeAssertionFailed
label toUpperHolds

# convertAsciiLetterCodeToLowercase('H') == 'h'
call assertToLowerCall convertAsciiLetterCodeToLowercase
arg assertToLowerCall characterCode upperHCode
run assertToLowerCall
bind lowerConversionResult CSignedInt32 assertToLowerCall
call checkToLowerCall math.equalI64
arg checkToLowerCall left lowerConversionResult
arg checkToLowerCall right lowerHCode
run checkToLowerCall
bind toLowerOk Bool checkToLowerCall
branchIf toLowerOk toLowerHolds
branch smokeAssertionFailed
label toLowerHolds

# ============================================================
# Extended unit tests: coverage for the 2 untested ops
# (isAsciiLowercaseLetterCode, isAsciiUppercaseLetterCode) plus
# negative-case boundaries for each predicate (off-by-one is the
# most common ctype bug, so each range gets both an inside and
# outside check).
# ============================================================

const lowerACode CSignedInt32 97
const upperACode CSignedInt32 65
const lowerFHexCode CSignedInt32 102
const letterGNotHexCode CSignedInt32 71
const digit0Code CSignedInt32 48
const tildeCode CSignedInt32 126
const deleteCode CSignedInt32 127

# isAsciiLowercaseLetterCode('a') == true
call lowerATrueCall isAsciiLowercaseLetterCode
arg lowerATrueCall characterCode lowerACode
run lowerATrueCall
bind lowerATrueResult Bool lowerATrueCall
branchIf lowerATrueResult lowerATrueHolds
branch smokeAssertionFailed
label lowerATrueHolds

# isAsciiLowercaseLetterCode('A') == false
call lowerAFalseCall isAsciiLowercaseLetterCode
arg lowerAFalseCall characterCode upperACode
run lowerAFalseCall
bind lowerAFalseResult Bool lowerAFalseCall
branchIf lowerAFalseResult smokeAssertionFailed
branch lowerAFalseHolds
label lowerAFalseHolds

# isAsciiUppercaseLetterCode('A') == true
call upperATrueCall isAsciiUppercaseLetterCode
arg upperATrueCall characterCode upperACode
run upperATrueCall
bind upperATrueResult Bool upperATrueCall
branchIf upperATrueResult upperATrueHolds
branch smokeAssertionFailed
label upperATrueHolds

# isAsciiUppercaseLetterCode('a') == false
call upperAFalseCall isAsciiUppercaseLetterCode
arg upperAFalseCall characterCode lowerACode
run upperAFalseCall
bind upperAFalseResult Bool upperAFalseCall
branchIf upperAFalseResult smokeAssertionFailed
branch upperAFalseHolds
label upperAFalseHolds

# isAsciiDecimalDigitCode('a') == false (letter outside digit range)
call digitNonCall isAsciiDecimalDigitCode
arg digitNonCall characterCode lowerACode
run digitNonCall
bind digitNonResult Bool digitNonCall
branchIf digitNonResult smokeAssertionFailed
branch digitNonHolds
label digitNonHolds

# isAsciiDecimalDigitCode('0') == true (boundary)
call digitZeroCall isAsciiDecimalDigitCode
arg digitZeroCall characterCode digit0Code
run digitZeroCall
bind digitZeroResult Bool digitZeroCall
branchIf digitZeroResult digitZeroHolds
branch smokeAssertionFailed
label digitZeroHolds

# isAsciiLetterCode('5') == false (digit not letter)
call letterNonCall isAsciiLetterCode
arg letterNonCall characterCode digit5Code
run letterNonCall
bind letterNonResult Bool letterNonCall
branchIf letterNonResult smokeAssertionFailed
branch letterNonHolds
label letterNonHolds

# isAsciiHexDigitCode('f') == true (lowercase hex digit)
call hexLowerCall isAsciiHexDigitCode
arg hexLowerCall characterCode lowerFHexCode
run hexLowerCall
bind hexLowerResult Bool hexLowerCall
branchIf hexLowerResult hexLowerHolds
branch smokeAssertionFailed
label hexLowerHolds

# isAsciiHexDigitCode('G') == false (just past F)
call hexGFalseCall isAsciiHexDigitCode
arg hexGFalseCall characterCode letterGNotHexCode
run hexGFalseCall
bind hexGFalseResult Bool hexGFalseCall
branchIf hexGFalseResult smokeAssertionFailed
branch hexGFalseHolds
label hexGFalseHolds

# isAsciiControlCode(' ') == false (space is not control)
call controlSpaceCall isAsciiControlCode
arg controlSpaceCall characterCode spaceByteCode
run controlSpaceCall
bind controlSpaceResult Bool controlSpaceCall
branchIf controlSpaceResult smokeAssertionFailed
branch controlSpaceHolds
label controlSpaceHolds

# isAsciiControlCode(127) == true (DEL is control)
call controlDelCall isAsciiControlCode
arg controlDelCall characterCode deleteCode
run controlDelCall
bind controlDelResult Bool controlDelCall
branchIf controlDelResult controlDelHolds
branch smokeAssertionFailed
label controlDelHolds

# isAsciiPrintableCode(0) == false (NUL not printable)
call printNonCall isAsciiPrintableCode
arg printNonCall characterCode nullByteCode
run printNonCall
bind printNonResult Bool printNonCall
branchIf printNonResult smokeAssertionFailed
branch printNonHolds
label printNonHolds

# isAsciiPrintableCode('~') == true (last printable)
call printTildeCall isAsciiPrintableCode
arg printTildeCall characterCode tildeCode
run printTildeCall
bind printTildeResult Bool printTildeCall
branchIf printTildeResult printTildeHolds
branch smokeAssertionFailed
label printTildeHolds

# convertAsciiLetterCodeToUppercase('H') == 'H' (already upper, identity)
call upperIdCall convertAsciiLetterCodeToUppercase
arg upperIdCall characterCode upperHCode
run upperIdCall
bind upperIdResult CSignedInt32 upperIdCall
call upperIdCheckCall math.equalI64
arg upperIdCheckCall left upperIdResult
arg upperIdCheckCall right upperHCode
run upperIdCheckCall
bind upperIdOk Bool upperIdCheckCall
branchIf upperIdOk upperIdHolds
branch smokeAssertionFailed
label upperIdHolds

# convertAsciiLetterCodeToLowercase('5') == '5' (non-letter identity)
call lowerNonLetterCall convertAsciiLetterCodeToLowercase
arg lowerNonLetterCall characterCode digit5Code
run lowerNonLetterCall
bind lowerNonLetterResult CSignedInt32 lowerNonLetterCall
call lowerNonLetterCheckCall math.equalI64
arg lowerNonLetterCheckCall left lowerNonLetterResult
arg lowerNonLetterCheckCall right digit5Code
run lowerNonLetterCheckCall
bind lowerNonLetterOk Bool lowerNonLetterCheckCall
branchIf lowerNonLetterOk lowerNonLetterHolds
branch smokeAssertionFailed
label lowerNonLetterHolds

# Property: convertToUpper(convertToLower('H')) == 'H' (round-trip)
call propLowerCall convertAsciiLetterCodeToLowercase
arg propLowerCall characterCode upperHCode
run propLowerCall
bind propLowerResult CSignedInt32 propLowerCall
call propUpperCall convertAsciiLetterCodeToUppercase
arg propUpperCall characterCode propLowerResult
run propUpperCall
bind propUpperResult CSignedInt32 propUpperCall
call propRoundTripCheckCall math.equalI64
arg propRoundTripCheckCall left propUpperResult
arg propRoundTripCheckCall right upperHCode
run propRoundTripCheckCall
bind propRoundTripOk Bool propRoundTripCheckCall
branchIf propRoundTripOk propRoundTripHolds
branch smokeAssertionFailed
label propRoundTripHolds

const successMessageText CNullTerminatedByteString "OK"
call writeSuccessLineCall console.writeLine
arg writeSuccessLineCall console console
arg writeSuccessLineCall text successMessageText
run writeSuccessLineCall
ignoreOk writeSuccessLineCall CSignedInt32
bindError consoleWriteResultError CSignedInt32 writeSuccessLineCall
branchIfError writeSuccessLineCall consoleWriteFailedHandler
const exitOkCode ExitCode 0
returnOk exitOkCode

# Failure leg: surface the raw negative CSignedInt32 from
# console.writeLine as the cause attached to the typed
# MainError.ConsoleWriteFailed variant.
label consoleWriteFailedHandler
makeError consoleWriteFailedFailure MainError.ConsoleWriteFailed consoleWriteResultError
returnError consoleWriteFailedFailure
label smokeAssertionFailed
makeError ctypeSmokeFailure MainError.CtypeSmokeAssertionFailed
returnError ctypeSmokeFailure
