# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <stdlib.h>-style numeric utilities
# ============================================================
#
# # rationale: small numeric helpers (parsing, abs, min/max, integer
#   power, gcd, clamp). The refined surface returns natural values
#   (CSignedInt64 / Bool) and reserves a `NumericParseError` /
#   `NumericArithmeticError` domain for the operations that actually
#   have failure cases — negative exponents on integer power, and
#   degenerate-input gcd. Most ops are total.
#
# # invariant: parsers walk the input byte-by-byte and stop at the
#   first non-matching byte; empty / junk inputs return 0 from the
#   parsers. abs / min / max / clamp are total.
#
# # security: pure value-level computation; no allocation; no I/O.
#
# # timing: parsers are O(byteLength); abs / min / max / clamp are
#   O(1); power is O(exponent); gcd is O(log min(|a|, |b|)).

project StdStdlibSelfTest
target console
runtime AgentRuntime 0.1
entry console main

# Typed error domain for stdlib arithmetic failures.
error NumericArithmeticError
errorCase NumericArithmeticError NegativeExponentNotSupported
errorCase NumericArithmeticError GreatestCommonDivisorOfTwoZeros

error MainError
errorCase MainError StdlibSmokeAssertionFailed

# section stdlib.parseConstants
domainLiteral asciiZeroByteCode CSignedInt64 48
domainLiteralTrust asciiZeroByteCode trustedStaticLiteral
domainLiteral asciiNineByteCode CSignedInt64 57
domainLiteralTrust asciiNineByteCode trustedStaticLiteral
domainLiteral asciiSpaceByteCode CSignedInt64 32
domainLiteralTrust asciiSpaceByteCode trustedStaticLiteral
domainLiteral asciiTabByteCode CSignedInt64 9
domainLiteralTrust asciiTabByteCode trustedStaticLiteral
domainLiteral asciiPlusByteCode CSignedInt64 43
domainLiteralTrust asciiPlusByteCode trustedStaticLiteral
domainLiteral asciiMinusByteCode CSignedInt64 45
domainLiteralTrust asciiMinusByteCode trustedStaticLiteral
domainLiteral asciiUppercaseAByteCode CSignedInt64 65
domainLiteralTrust asciiUppercaseAByteCode trustedStaticLiteral
domainLiteral asciiUppercaseFByteCode CSignedInt64 70
domainLiteralTrust asciiUppercaseFByteCode trustedStaticLiteral
domainLiteral asciiLowercaseAByteCode CSignedInt64 97
domainLiteralTrust asciiLowercaseAByteCode trustedStaticLiteral
domainLiteral asciiLowercaseFByteCode CSignedInt64 102
domainLiteralTrust asciiLowercaseFByteCode trustedStaticLiteral
domainLiteral asciiLowercaseXByteCode CSignedInt64 120
domainLiteralTrust asciiLowercaseXByteCode trustedStaticLiteral
domainLiteral asciiUppercaseXByteCode CSignedInt64 88
domainLiteralTrust asciiUppercaseXByteCode trustedStaticLiteral
domainLiteral hexLowercaseOffsetForLetters CSignedInt64 87
domainLiteralTrust hexLowercaseOffsetForLetters trustedStaticLiteral
domainLiteral hexUppercaseOffsetForLetters CSignedInt64 55
domainLiteralTrust hexUppercaseOffsetForLetters trustedStaticLiteral
domainLiteral decimalBase CSignedInt64 10
domainLiteralTrust decimalBase trustedStaticLiteral
domainLiteral hexadecimalBase CSignedInt64 16
domainLiteralTrust hexadecimalBase trustedStaticLiteral
domainLiteral integerOneStepValue CSignedInt64 1
domainLiteralTrust integerOneStepValue trustedStaticLiteral
domainLiteral integerNegativeOneMultiplier CSignedInt64 -1
domainLiteralTrust integerNegativeOneMultiplier trustedStaticLiteral
domainLiteral integerZeroBoundary CSignedInt64 0
domainLiteralTrust integerZeroBoundary trustedStaticLiteral

# section stdlib.parsers

operation parseDecimalCStringToSignedInt64
input parseDecimalCStringToSignedInt64 inputText CNullTerminatedByteString
output parseDecimalCStringToSignedInt64 CSignedInt64
effect parseDecimalCStringToSignedInt64 read inputText
memoryHeap parseDecimalCStringToSignedInt64 no
memoryStackLimit parseDecimalCStringToSignedInt64 1024
async parseDecimalCStringToSignedInt64 no
purpose parseDecimalCStringToSignedInt64 "Parse a NUL-terminated decimal numeric string into an i64 (atoi/atol shape). Skips ASCII whitespace, accepts optional sign, accumulates digits until a non-digit byte."
invariant parseDecimalCStringToSignedInt64 "Empty / junk inputs return 0; trailing non-digit text is silently discarded."
warning parseDecimalCStringToSignedInt64 "No overflow detection — inputs longer than 18 decimal digits silently wrap CSignedInt64."
guarantee parseDecimalCStringToSignedInt64 "Total."
label startParseDecimalCStringToSignedInt64
var decimalParseCursor I64 0
label decimalSkipWhitespace
call loadByteForDecimalWsCall pointer.loadByte
arg loadByteForDecimalWsCall buffer inputText
arg loadByteForDecimalWsCall offset decimalParseCursor
run loadByteForDecimalWsCall
bind currentDecimalWsByte I8 loadByteForDecimalWsCall
call detectDecimalWsSpaceCall math.equalI64
arg detectDecimalWsSpaceCall left currentDecimalWsByte
arg detectDecimalWsSpaceCall right asciiSpaceByteCode
run detectDecimalWsSpaceCall
bind decimalWsIsSpace Bool detectDecimalWsSpaceCall
branchIf decimalWsIsSpace consumeDecimalWhitespaceByte
call detectDecimalWsTabCall math.equalI64
arg detectDecimalWsTabCall left currentDecimalWsByte
arg detectDecimalWsTabCall right asciiTabByteCode
run detectDecimalWsTabCall
bind decimalWsIsTab Bool detectDecimalWsTabCall
branchIf decimalWsIsTab consumeDecimalWhitespaceByte
branch decimalCheckSign
label consumeDecimalWhitespaceByte
call advanceDecimalWsCursorCall math.addI64
arg advanceDecimalWsCursorCall left decimalParseCursor
arg advanceDecimalWsCursorCall right integerOneStepValue
run advanceDecimalWsCursorCall
bind nextDecimalWsCursor I64 advanceDecimalWsCursorCall
set decimalParseCursor nextDecimalWsCursor
branch decimalSkipWhitespace
label decimalCheckSign
var decimalSignMultiplier I64 1
call loadByteForDecimalSignCall pointer.loadByte
arg loadByteForDecimalSignCall buffer inputText
arg loadByteForDecimalSignCall offset decimalParseCursor
run loadByteForDecimalSignCall
bind currentDecimalSignByte I8 loadByteForDecimalSignCall
call detectDecimalPlusSignCall math.equalI64
arg detectDecimalPlusSignCall left currentDecimalSignByte
arg detectDecimalPlusSignCall right asciiPlusByteCode
run detectDecimalPlusSignCall
bind decimalSignIsPlus Bool detectDecimalPlusSignCall
branchIf decimalSignIsPlus consumeDecimalPlusSign
call detectDecimalMinusSignCall math.equalI64
arg detectDecimalMinusSignCall left currentDecimalSignByte
arg detectDecimalMinusSignCall right asciiMinusByteCode
run detectDecimalMinusSignCall
bind decimalSignIsMinus Bool detectDecimalMinusSignCall
branchIf decimalSignIsMinus consumeDecimalMinusSign
branch parseDecimalDigits
label consumeDecimalPlusSign
call advanceDecimalPlusCursorCall math.addI64
arg advanceDecimalPlusCursorCall left decimalParseCursor
arg advanceDecimalPlusCursorCall right integerOneStepValue
run advanceDecimalPlusCursorCall
bind nextDecimalPlusCursor I64 advanceDecimalPlusCursorCall
set decimalParseCursor nextDecimalPlusCursor
branch parseDecimalDigits
label consumeDecimalMinusSign
set decimalSignMultiplier integerNegativeOneMultiplier
call advanceDecimalMinusCursorCall math.addI64
arg advanceDecimalMinusCursorCall left decimalParseCursor
arg advanceDecimalMinusCursorCall right integerOneStepValue
run advanceDecimalMinusCursorCall
bind nextDecimalMinusCursor I64 advanceDecimalMinusCursorCall
set decimalParseCursor nextDecimalMinusCursor
branch parseDecimalDigits
label parseDecimalDigits
var decimalAccumulator I64 0
label decimalDigitStep
call loadDecimalDigitByteCall pointer.loadByte
arg loadDecimalDigitByteCall buffer inputText
arg loadDecimalDigitByteCall offset decimalParseCursor
run loadDecimalDigitByteCall
bind currentDecimalDigitByte I8 loadDecimalDigitByteCall
call detectDecimalDigitBelowZeroCall math.lessThanI64
arg detectDecimalDigitBelowZeroCall left currentDecimalDigitByte
arg detectDecimalDigitBelowZeroCall right asciiZeroByteCode
run detectDecimalDigitBelowZeroCall
bind decimalDigitBelowZero Bool detectDecimalDigitBelowZeroCall
branchIf decimalDigitBelowZero decimalParseComplete
call detectDecimalDigitAboveNineCall math.greaterThanI64
arg detectDecimalDigitAboveNineCall left currentDecimalDigitByte
arg detectDecimalDigitAboveNineCall right asciiNineByteCode
run detectDecimalDigitAboveNineCall
bind decimalDigitAboveNine Bool detectDecimalDigitAboveNineCall
branchIf decimalDigitAboveNine decimalParseComplete
call computeDecimalDigitValueCall math.subtractI64
arg computeDecimalDigitValueCall left currentDecimalDigitByte
arg computeDecimalDigitValueCall right asciiZeroByteCode
run computeDecimalDigitValueCall
bind currentDecimalDigitValue I64 computeDecimalDigitValueCall
call shiftDecimalAccumulatorCall math.multiplyI64
arg shiftDecimalAccumulatorCall left decimalAccumulator
arg shiftDecimalAccumulatorCall right decimalBase
run shiftDecimalAccumulatorCall
bind shiftedDecimalAccumulator I64 shiftDecimalAccumulatorCall
call addDecimalDigitCall math.addI64
arg addDecimalDigitCall left shiftedDecimalAccumulator
arg addDecimalDigitCall right currentDecimalDigitValue
run addDecimalDigitCall
bind decimalAccumulatorAfterDigit I64 addDecimalDigitCall
set decimalAccumulator decimalAccumulatorAfterDigit
call advanceDecimalDigitCursorCall math.addI64
arg advanceDecimalDigitCursorCall left decimalParseCursor
arg advanceDecimalDigitCursorCall right integerOneStepValue
run advanceDecimalDigitCursorCall
bind nextDecimalDigitCursor I64 advanceDecimalDigitCursorCall
set decimalParseCursor nextDecimalDigitCursor
branch decimalDigitStep
label decimalParseComplete
call applyDecimalSignCall math.multiplyI64
arg applyDecimalSignCall left decimalAccumulator
arg applyDecimalSignCall right decimalSignMultiplier
run applyDecimalSignCall
bind signedDecimalResult CSignedInt64 applyDecimalSignCall
returnValue signedDecimalResult

operation parseHexCStringToSignedInt64
input parseHexCStringToSignedInt64 inputText CNullTerminatedByteString
output parseHexCStringToSignedInt64 CSignedInt64
effect parseHexCStringToSignedInt64 read inputText
memoryHeap parseHexCStringToSignedInt64 no
memoryStackLimit parseHexCStringToSignedInt64 1024
async parseHexCStringToSignedInt64 no
purpose parseHexCStringToSignedInt64 "Parse a NUL-terminated hex numeric string into an i64 (strtol(s, NULL, 16) shape). Skips whitespace, accepts optional sign, accepts optional 0x / 0X prefix, accumulates hex digits."
invariant parseHexCStringToSignedInt64 "Empty / junk inputs return 0; trailing non-hex text is silently discarded."
warning parseHexCStringToSignedInt64 "No overflow detection — inputs longer than 15 hex digits silently wrap CSignedInt64."
guarantee parseHexCStringToSignedInt64 "Total."
label startParseHexCStringToSignedInt64
var hexParseCursor I64 0
label hexSkipWhitespace
call loadByteForHexWsCall pointer.loadByte
arg loadByteForHexWsCall buffer inputText
arg loadByteForHexWsCall offset hexParseCursor
run loadByteForHexWsCall
bind currentHexWsByte I8 loadByteForHexWsCall
call detectHexWsSpaceCall math.equalI64
arg detectHexWsSpaceCall left currentHexWsByte
arg detectHexWsSpaceCall right asciiSpaceByteCode
run detectHexWsSpaceCall
bind hexWsIsSpace Bool detectHexWsSpaceCall
branchIf hexWsIsSpace consumeHexWhitespaceByte
call detectHexWsTabCall math.equalI64
arg detectHexWsTabCall left currentHexWsByte
arg detectHexWsTabCall right asciiTabByteCode
run detectHexWsTabCall
bind hexWsIsTab Bool detectHexWsTabCall
branchIf hexWsIsTab consumeHexWhitespaceByte
branch hexCheckSign
label consumeHexWhitespaceByte
call advanceHexWsCursorCall math.addI64
arg advanceHexWsCursorCall left hexParseCursor
arg advanceHexWsCursorCall right integerOneStepValue
run advanceHexWsCursorCall
bind nextHexWsCursor I64 advanceHexWsCursorCall
set hexParseCursor nextHexWsCursor
branch hexSkipWhitespace
label hexCheckSign
var hexSignMultiplier I64 1
call loadByteForHexSignCall pointer.loadByte
arg loadByteForHexSignCall buffer inputText
arg loadByteForHexSignCall offset hexParseCursor
run loadByteForHexSignCall
bind currentHexSignByte I8 loadByteForHexSignCall
call detectHexPlusSignCall math.equalI64
arg detectHexPlusSignCall left currentHexSignByte
arg detectHexPlusSignCall right asciiPlusByteCode
run detectHexPlusSignCall
bind hexSignIsPlus Bool detectHexPlusSignCall
branchIf hexSignIsPlus consumeHexPlusSign
call detectHexMinusSignCall math.equalI64
arg detectHexMinusSignCall left currentHexSignByte
arg detectHexMinusSignCall right asciiMinusByteCode
run detectHexMinusSignCall
bind hexSignIsMinus Bool detectHexMinusSignCall
branchIf hexSignIsMinus consumeHexMinusSign
branch hexCheckPrefix
label consumeHexPlusSign
call advanceHexPlusCursorCall math.addI64
arg advanceHexPlusCursorCall left hexParseCursor
arg advanceHexPlusCursorCall right integerOneStepValue
run advanceHexPlusCursorCall
bind nextHexPlusCursor I64 advanceHexPlusCursorCall
set hexParseCursor nextHexPlusCursor
branch hexCheckPrefix
label consumeHexMinusSign
set hexSignMultiplier integerNegativeOneMultiplier
call advanceHexMinusCursorCall math.addI64
arg advanceHexMinusCursorCall left hexParseCursor
arg advanceHexMinusCursorCall right integerOneStepValue
run advanceHexMinusCursorCall
bind nextHexMinusCursor I64 advanceHexMinusCursorCall
set hexParseCursor nextHexMinusCursor
branch hexCheckPrefix
label hexCheckPrefix
call loadHexPrefixZeroCall pointer.loadByte
arg loadHexPrefixZeroCall buffer inputText
arg loadHexPrefixZeroCall offset hexParseCursor
run loadHexPrefixZeroCall
bind hexPrefixZeroByte I8 loadHexPrefixZeroCall
call detectHexPrefixZeroCall math.equalI64
arg detectHexPrefixZeroCall left hexPrefixZeroByte
arg detectHexPrefixZeroCall right asciiZeroByteCode
run detectHexPrefixZeroCall
bind hexPrefixStartsWithZero Bool detectHexPrefixZeroCall
branchIf hexPrefixStartsWithZero hexInspectPrefixX
branch parseHexDigits
label hexInspectPrefixX
call computeHexPrefixXOffsetCall math.addI64
arg computeHexPrefixXOffsetCall left hexParseCursor
arg computeHexPrefixXOffsetCall right integerOneStepValue
run computeHexPrefixXOffsetCall
bind hexPrefixXCursor I64 computeHexPrefixXOffsetCall
call loadHexPrefixXCall pointer.loadByte
arg loadHexPrefixXCall buffer inputText
arg loadHexPrefixXCall offset hexPrefixXCursor
run loadHexPrefixXCall
bind hexPrefixXByte I8 loadHexPrefixXCall
call detectHexPrefixLowerXCall math.equalI64
arg detectHexPrefixLowerXCall left hexPrefixXByte
arg detectHexPrefixLowerXCall right asciiLowercaseXByteCode
run detectHexPrefixLowerXCall
bind hexPrefixIsLowerX Bool detectHexPrefixLowerXCall
branchIf hexPrefixIsLowerX consumeHexPrefix
call detectHexPrefixUpperXCall math.equalI64
arg detectHexPrefixUpperXCall left hexPrefixXByte
arg detectHexPrefixUpperXCall right asciiUppercaseXByteCode
run detectHexPrefixUpperXCall
bind hexPrefixIsUpperX Bool detectHexPrefixUpperXCall
branchIf hexPrefixIsUpperX consumeHexPrefix
branch parseHexDigits
label consumeHexPrefix
call consumePrefixStepOneCall math.addI64
arg consumePrefixStepOneCall left hexParseCursor
arg consumePrefixStepOneCall right integerOneStepValue
run consumePrefixStepOneCall
bind hexCursorAfterPrefixStepOne I64 consumePrefixStepOneCall
call consumePrefixStepTwoCall math.addI64
arg consumePrefixStepTwoCall left hexCursorAfterPrefixStepOne
arg consumePrefixStepTwoCall right integerOneStepValue
run consumePrefixStepTwoCall
bind hexCursorAfterPrefixStepTwo I64 consumePrefixStepTwoCall
set hexParseCursor hexCursorAfterPrefixStepTwo
branch parseHexDigits
label parseHexDigits
var hexAccumulator I64 0
var currentHexDigitValue I64 0
label hexDigitStep
call loadHexDigitByteCall pointer.loadByte
arg loadHexDigitByteCall buffer inputText
arg loadHexDigitByteCall offset hexParseCursor
run loadHexDigitByteCall
bind currentHexDigitByte I8 loadHexDigitByteCall
call detectHexDecBelowZeroCall math.lessThanI64
arg detectHexDecBelowZeroCall left currentHexDigitByte
arg detectHexDecBelowZeroCall right asciiZeroByteCode
run detectHexDecBelowZeroCall
bind hexDigitBelowDecZero Bool detectHexDecBelowZeroCall
branchIf hexDigitBelowDecZero hexInspectUppercaseRange
call detectHexDecAboveNineCall math.greaterThanI64
arg detectHexDecAboveNineCall left currentHexDigitByte
arg detectHexDecAboveNineCall right asciiNineByteCode
run detectHexDecAboveNineCall
bind hexDigitAboveDecNine Bool detectHexDecAboveNineCall
branchIf hexDigitAboveDecNine hexInspectUppercaseRange
call computeHexDecValueCall math.subtractI64
arg computeHexDecValueCall left currentHexDigitByte
arg computeHexDecValueCall right asciiZeroByteCode
run computeHexDecValueCall
bind hexDigitDecValue I64 computeHexDecValueCall
set currentHexDigitValue hexDigitDecValue
branch hexAccumulateDigit
label hexInspectUppercaseRange
call detectHexUpperABelowCall math.lessThanI64
arg detectHexUpperABelowCall left currentHexDigitByte
arg detectHexUpperABelowCall right asciiUppercaseAByteCode
run detectHexUpperABelowCall
bind hexDigitBelowUpperA Bool detectHexUpperABelowCall
branchIf hexDigitBelowUpperA hexInspectLowercaseRange
call detectHexUpperFAboveCall math.greaterThanI64
arg detectHexUpperFAboveCall left currentHexDigitByte
arg detectHexUpperFAboveCall right asciiUppercaseFByteCode
run detectHexUpperFAboveCall
bind hexDigitAboveUpperF Bool detectHexUpperFAboveCall
branchIf hexDigitAboveUpperF hexInspectLowercaseRange
call computeHexUpperValueCall math.subtractI64
arg computeHexUpperValueCall left currentHexDigitByte
arg computeHexUpperValueCall right hexUppercaseOffsetForLetters
run computeHexUpperValueCall
bind hexDigitUpperValue I64 computeHexUpperValueCall
set currentHexDigitValue hexDigitUpperValue
branch hexAccumulateDigit
label hexInspectLowercaseRange
call detectHexLowerABelowCall math.lessThanI64
arg detectHexLowerABelowCall left currentHexDigitByte
arg detectHexLowerABelowCall right asciiLowercaseAByteCode
run detectHexLowerABelowCall
bind hexDigitBelowLowerA Bool detectHexLowerABelowCall
branchIf hexDigitBelowLowerA hexParseComplete
call detectHexLowerFAboveCall math.greaterThanI64
arg detectHexLowerFAboveCall left currentHexDigitByte
arg detectHexLowerFAboveCall right asciiLowercaseFByteCode
run detectHexLowerFAboveCall
bind hexDigitAboveLowerF Bool detectHexLowerFAboveCall
branchIf hexDigitAboveLowerF hexParseComplete
call computeHexLowerValueCall math.subtractI64
arg computeHexLowerValueCall left currentHexDigitByte
arg computeHexLowerValueCall right hexLowercaseOffsetForLetters
run computeHexLowerValueCall
bind hexDigitLowerValue I64 computeHexLowerValueCall
set currentHexDigitValue hexDigitLowerValue
branch hexAccumulateDigit
label hexAccumulateDigit
call shiftHexAccumulatorCall math.multiplyI64
arg shiftHexAccumulatorCall left hexAccumulator
arg shiftHexAccumulatorCall right hexadecimalBase
run shiftHexAccumulatorCall
bind shiftedHexAccumulator I64 shiftHexAccumulatorCall
call addHexDigitCall math.addI64
arg addHexDigitCall left shiftedHexAccumulator
arg addHexDigitCall right currentHexDigitValue
run addHexDigitCall
bind hexAccumulatorAfterDigit I64 addHexDigitCall
set hexAccumulator hexAccumulatorAfterDigit
call advanceHexDigitCursorCall math.addI64
arg advanceHexDigitCursorCall left hexParseCursor
arg advanceHexDigitCursorCall right integerOneStepValue
run advanceHexDigitCursorCall
bind nextHexDigitCursor I64 advanceHexDigitCursorCall
set hexParseCursor nextHexDigitCursor
branch hexDigitStep
label hexParseComplete
call applyHexSignCall math.multiplyI64
arg applyHexSignCall left hexAccumulator
arg applyHexSignCall right hexSignMultiplier
run applyHexSignCall
bind signedHexResult CSignedInt64 applyHexSignCall
returnValue signedHexResult

# section stdlib.totalIntegerHelpers

operation absoluteSignedInt64
input absoluteSignedInt64 inputValue CSignedInt64
output absoluteSignedInt64 CSignedInt64
memoryHeap absoluteSignedInt64 no
async absoluteSignedInt64 no
purpose absoluteSignedInt64 "Returns |inputValue|."
warning absoluteSignedInt64 "INT64_MIN negation overflows back to INT64_MIN (two's-complement)."
guarantee absoluteSignedInt64 "Total."
label startAbsoluteSignedInt64
call detectAbsoluteInputNegativeCall math.lessThanI64
arg detectAbsoluteInputNegativeCall left inputValue
arg detectAbsoluteInputNegativeCall right integerZeroBoundary
run detectAbsoluteInputNegativeCall
bind absoluteInputIsNegative Bool detectAbsoluteInputNegativeCall
branchIf absoluteInputIsNegative negateAbsoluteInput
returnValue inputValue
label negateAbsoluteInput
call negateAbsoluteInputCall math.multiplyI64
arg negateAbsoluteInputCall left inputValue
arg negateAbsoluteInputCall right integerNegativeOneMultiplier
run negateAbsoluteInputCall
bind negatedAbsoluteValue CSignedInt64 negateAbsoluteInputCall
returnValue negatedAbsoluteValue

operation minimumSignedInt64
input minimumSignedInt64 leftValue CSignedInt64
input minimumSignedInt64 rightValue CSignedInt64
output minimumSignedInt64 CSignedInt64
memoryHeap minimumSignedInt64 no
async minimumSignedInt64 no
purpose minimumSignedInt64 "Returns the smaller of leftValue and rightValue."
invariant minimumSignedInt64 "Commutative."
guarantee minimumSignedInt64 "Total."
label startMinimumSignedInt64
call detectLeftLessForMinCall math.lessThanI64
arg detectLeftLessForMinCall left leftValue
arg detectLeftLessForMinCall right rightValue
run detectLeftLessForMinCall
bind leftLessThanRightForMin Bool detectLeftLessForMinCall
branchIf leftLessThanRightForMin returnMinLeft
returnValue rightValue
label returnMinLeft
returnValue leftValue

operation maximumSignedInt64
input maximumSignedInt64 leftValue CSignedInt64
input maximumSignedInt64 rightValue CSignedInt64
output maximumSignedInt64 CSignedInt64
memoryHeap maximumSignedInt64 no
async maximumSignedInt64 no
purpose maximumSignedInt64 "Returns the larger of leftValue and rightValue."
invariant maximumSignedInt64 "Commutative."
guarantee maximumSignedInt64 "Total."
label startMaximumSignedInt64
call detectLeftGreaterForMaxCall math.greaterThanI64
arg detectLeftGreaterForMaxCall left leftValue
arg detectLeftGreaterForMaxCall right rightValue
run detectLeftGreaterForMaxCall
bind leftGreaterThanRightForMax Bool detectLeftGreaterForMaxCall
branchIf leftGreaterThanRightForMax returnMaxLeft
returnValue rightValue
label returnMaxLeft
returnValue leftValue

operation powerSignedInt64
input powerSignedInt64 baseValue CSignedInt64
input powerSignedInt64 exponentValue CSignedInt64
output powerSignedInt64 Result CSignedInt64 NumericArithmeticError
memoryHeap powerSignedInt64 no
async powerSignedInt64 no
purpose powerSignedInt64 "Returns baseValue^exponentValue via repeated multiplication."
invariant powerSignedInt64 "exponent == 0 always returns 1 (including 0^0)."
failure powerSignedInt64 NegativeExponentNotSupported "Returned for exponent < 0 (integer arithmetic can't represent fractions)."
warning powerSignedInt64 "Wraps modulo 2^64 on overflow."
guarantee powerSignedInt64 "Defined for every (base, non-negative exponent) pair."
label startPowerSignedInt64
call detectExponentNegativeCall math.lessThanI64
arg detectExponentNegativeCall left exponentValue
arg detectExponentNegativeCall right integerZeroBoundary
run detectExponentNegativeCall
bind exponentIsNegative Bool detectExponentNegativeCall
branchIf exponentIsNegative raiseNegativeExponentError
var powerProduct I64 1
var powerCounter I64 0
label powerLoop
call detectPowerDoneCall math.greaterThanOrEqualI64
arg detectPowerDoneCall left powerCounter
arg detectPowerDoneCall right exponentValue
run detectPowerDoneCall
bind powerLoopDone Bool detectPowerDoneCall
branchIf powerLoopDone returnPowerProduct
call multiplyPowerProductByBaseCall math.multiplyI64
arg multiplyPowerProductByBaseCall left powerProduct
arg multiplyPowerProductByBaseCall right baseValue
run multiplyPowerProductByBaseCall
bind nextPowerProduct I64 multiplyPowerProductByBaseCall
set powerProduct nextPowerProduct
call advancePowerCounterCall math.addI64
arg advancePowerCounterCall left powerCounter
arg advancePowerCounterCall right integerOneStepValue
run advancePowerCounterCall
bind nextPowerCounter I64 advancePowerCounterCall
set powerCounter nextPowerCounter
branch powerLoop
label returnPowerProduct
returnOk powerProduct
label raiseNegativeExponentError
makeError negativeExponentFailure NumericArithmeticError.NegativeExponentNotSupported
returnError negativeExponentFailure

operation greatestCommonDivisorSignedInt64
input greatestCommonDivisorSignedInt64 leftValue CSignedInt64
input greatestCommonDivisorSignedInt64 rightValue CSignedInt64
output greatestCommonDivisorSignedInt64 CSignedInt64
memoryHeap greatestCommonDivisorSignedInt64 no
async greatestCommonDivisorSignedInt64 no
purpose greatestCommonDivisorSignedInt64 "Greatest common divisor via the Euclidean algorithm. Works on absolute values, so signs of inputs don't matter."
invariant greatestCommonDivisorSignedInt64 "gcd(a, 0) == |a|; gcd(0, b) == |b|; gcd(0, 0) == 0 (mathematical convention)."
guarantee greatestCommonDivisorSignedInt64 "Total over CSignedInt64."
label startGreatestCommonDivisorSignedInt64
call resolveLeftAbsCall absoluteSignedInt64
arg resolveLeftAbsCall inputValue leftValue
run resolveLeftAbsCall
bind gcdLeftAbsolute CSignedInt64 resolveLeftAbsCall
call resolveRightAbsCall absoluteSignedInt64
arg resolveRightAbsCall inputValue rightValue
run resolveRightAbsCall
bind gcdRightAbsolute CSignedInt64 resolveRightAbsCall
var gcdDividend I64 0
var gcdDivisor I64 0
set gcdDividend gcdLeftAbsolute
set gcdDivisor gcdRightAbsolute
label gcdEuclidLoop
call detectGcdDivisorZeroCall math.equalI64
arg detectGcdDivisorZeroCall left gcdDivisor
arg detectGcdDivisorZeroCall right integerZeroBoundary
run detectGcdDivisorZeroCall
bind gcdDivisorIsZero Bool detectGcdDivisorZeroCall
branchIf gcdDivisorIsZero returnGcd
call computeGcdRemainderCall math.moduloI64
arg computeGcdRemainderCall left gcdDividend
arg computeGcdRemainderCall right gcdDivisor
run computeGcdRemainderCall
bind gcdRemainder I64 computeGcdRemainderCall
set gcdDividend gcdDivisor
set gcdDivisor gcdRemainder
branch gcdEuclidLoop
label returnGcd
returnValue gcdDividend

operation clampSignedInt64ToInclusiveRange
input clampSignedInt64ToInclusiveRange inputValue CSignedInt64
input clampSignedInt64ToInclusiveRange lowerBound CSignedInt64
input clampSignedInt64ToInclusiveRange upperBound CSignedInt64
output clampSignedInt64ToInclusiveRange CSignedInt64
memoryHeap clampSignedInt64ToInclusiveRange no
async clampSignedInt64ToInclusiveRange no
purpose clampSignedInt64ToInclusiveRange "Returns lowerBound if inputValue < lowerBound, upperBound if inputValue > upperBound, else inputValue."
invariant clampSignedInt64ToInclusiveRange "Output is always in [lowerBound, upperBound] when lowerBound <= upperBound."
warning clampSignedInt64ToInclusiveRange "If lowerBound > upperBound, the result is either bound depending on input — caller should pre-check."
guarantee clampSignedInt64ToInclusiveRange "Total."
label startClampSignedInt64ToInclusiveRange
call detectInputBelowLowerCall math.lessThanI64
arg detectInputBelowLowerCall left inputValue
arg detectInputBelowLowerCall right lowerBound
run detectInputBelowLowerCall
bind inputBelowLowerBoundForClamp Bool detectInputBelowLowerCall
branchIf inputBelowLowerBoundForClamp returnClampLower
call detectInputAboveUpperCall math.greaterThanI64
arg detectInputAboveUpperCall left inputValue
arg detectInputAboveUpperCall right upperBound
run detectInputAboveUpperCall
bind inputAboveUpperBoundForClamp Bool detectInputAboveUpperCall
branchIf inputAboveUpperBoundForClamp returnClampUpper
returnValue inputValue
label returnClampLower
returnValue lowerBound
label returnClampUpper
returnValue upperBound

# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memoryHeap main no
async main no
purpose main "Smoke-test the stdlib numeric ops."

label startMain

# parseDecimalCStringToSignedInt64("12345") == 12345
const decimalSampleText CNullTerminatedByteString "12345"
const expectedDecimalSample CSignedInt64 12345
call assertParseDecimalCall parseDecimalCStringToSignedInt64
arg assertParseDecimalCall inputText decimalSampleText
run assertParseDecimalCall
bind decimalParseResult CSignedInt64 assertParseDecimalCall
call checkParseDecimalCall math.equalI64
arg checkParseDecimalCall left decimalParseResult
arg checkParseDecimalCall right expectedDecimalSample
run checkParseDecimalCall
bind parseDecimalOk Bool checkParseDecimalCall
branchIf parseDecimalOk parseDecimalHolds
branch smokeAssertionFailed
label parseDecimalHolds

# parseDecimalCStringToSignedInt64("  -42") == -42
const decimalNegativeSampleText CNullTerminatedByteString "  -42"
const expectedDecimalNegativeSample CSignedInt64 -42
call assertParseDecimalNegativeCall parseDecimalCStringToSignedInt64
arg assertParseDecimalNegativeCall inputText decimalNegativeSampleText
run assertParseDecimalNegativeCall
bind decimalNegativeParseResult CSignedInt64 assertParseDecimalNegativeCall
call checkParseDecimalNegativeCall math.equalI64
arg checkParseDecimalNegativeCall left decimalNegativeParseResult
arg checkParseDecimalNegativeCall right expectedDecimalNegativeSample
run checkParseDecimalNegativeCall
bind parseDecimalNegativeOk Bool checkParseDecimalNegativeCall
branchIf parseDecimalNegativeOk parseDecimalNegativeHolds
branch smokeAssertionFailed
label parseDecimalNegativeHolds

# parseHexCStringToSignedInt64("0x1F") == 31
const hexSampleText CNullTerminatedByteString "0x1F"
const expectedHexSample CSignedInt64 31
call assertParseHexCall parseHexCStringToSignedInt64
arg assertParseHexCall inputText hexSampleText
run assertParseHexCall
bind hexParseResult CSignedInt64 assertParseHexCall
call checkParseHexCall math.equalI64
arg checkParseHexCall left hexParseResult
arg checkParseHexCall right expectedHexSample
run checkParseHexCall
bind parseHexOk Bool checkParseHexCall
branchIf parseHexOk parseHexHolds
branch smokeAssertionFailed
label parseHexHolds

# absoluteSignedInt64(-99) == 99
const negativeNinetyNine CSignedInt64 -99
const ninetyNine CSignedInt64 99
call assertAbsoluteCall absoluteSignedInt64
arg assertAbsoluteCall inputValue negativeNinetyNine
run assertAbsoluteCall
bind absoluteResult CSignedInt64 assertAbsoluteCall
call checkAbsoluteCall math.equalI64
arg checkAbsoluteCall left absoluteResult
arg checkAbsoluteCall right ninetyNine
run checkAbsoluteCall
bind absoluteOk Bool checkAbsoluteCall
branchIf absoluteOk absoluteHolds
branch smokeAssertionFailed
label absoluteHolds

# minimumSignedInt64(7, 3) == 3
const sevenInt CSignedInt64 7
const threeInt CSignedInt64 3
call assertMinimumCall minimumSignedInt64
arg assertMinimumCall leftValue sevenInt
arg assertMinimumCall rightValue threeInt
run assertMinimumCall
bind minimumResult CSignedInt64 assertMinimumCall
call checkMinimumCall math.equalI64
arg checkMinimumCall left minimumResult
arg checkMinimumCall right threeInt
run checkMinimumCall
bind minimumOk Bool checkMinimumCall
branchIf minimumOk minimumHolds
branch smokeAssertionFailed
label minimumHolds

# maximumSignedInt64(7, 3) == 7
call assertMaximumCall maximumSignedInt64
arg assertMaximumCall leftValue sevenInt
arg assertMaximumCall rightValue threeInt
run assertMaximumCall
bind maximumResult CSignedInt64 assertMaximumCall
call checkMaximumCall math.equalI64
arg checkMaximumCall left maximumResult
arg checkMaximumCall right sevenInt
run checkMaximumCall
bind maximumOk Bool checkMaximumCall
branchIf maximumOk maximumHolds
branch smokeAssertionFailed
label maximumHolds

# powerSignedInt64(2, 10) == 1024
const twoBaseValue CSignedInt64 2
const tenExponentValue CSignedInt64 10
const expectedTenTwentyFour CSignedInt64 1024
call assertPowerCall powerSignedInt64
arg assertPowerCall baseValue twoBaseValue
arg assertPowerCall exponentValue tenExponentValue
run assertPowerCall
bindOk powerResult CSignedInt64 assertPowerCall
call checkPowerCall math.equalI64
arg checkPowerCall left powerResult
arg checkPowerCall right expectedTenTwentyFour
run checkPowerCall
bind powerOk Bool checkPowerCall
branchIf powerOk powerHolds
branch smokeAssertionFailed
label powerHolds

# greatestCommonDivisorSignedInt64(54, 24) == 6
const fiftyFourValue CSignedInt64 54
const twentyFourValue CSignedInt64 24
const expectedGcdSix CSignedInt64 6
call assertGcdCall greatestCommonDivisorSignedInt64
arg assertGcdCall leftValue fiftyFourValue
arg assertGcdCall rightValue twentyFourValue
run assertGcdCall
bind gcdResult CSignedInt64 assertGcdCall
call checkGcdCall math.equalI64
arg checkGcdCall left gcdResult
arg checkGcdCall right expectedGcdSix
run checkGcdCall
bind gcdOk Bool checkGcdCall
branchIf gcdOk gcdHolds
branch smokeAssertionFailed
label gcdHolds

# clampSignedInt64ToInclusiveRange(50, 0, 10) == 10
const fiftyValueForClamp CSignedInt64 50
const zeroLowerBoundForClamp CSignedInt64 0
const tenUpperBoundForClamp CSignedInt64 10
call assertClampCall clampSignedInt64ToInclusiveRange
arg assertClampCall inputValue fiftyValueForClamp
arg assertClampCall lowerBound zeroLowerBoundForClamp
arg assertClampCall upperBound tenUpperBoundForClamp
run assertClampCall
bind clampResult CSignedInt64 assertClampCall
call checkClampCall math.equalI64
arg checkClampCall left clampResult
arg checkClampCall right tenUpperBoundForClamp
run checkClampCall
bind clampOk Bool checkClampCall
branchIf clampOk clampHolds
branch smokeAssertionFailed
label clampHolds

const successMessageText CNullTerminatedByteString "OK"
call writeSuccessLineCall console.writeLine
arg writeSuccessLineCall console console
arg writeSuccessLineCall text successMessageText
run writeSuccessLineCall
ignoreOk writeSuccessLineCall Void
const exitOkCode ExitCode 0
returnOk exitOkCode

label smokeAssertionFailed
makeError stdlibSmokeFailure MainError.StdlibSmokeAssertionFailed
returnError stdlibSmokeFailure
