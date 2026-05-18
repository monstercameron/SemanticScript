# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <inttypes.h>-style helpers
# ============================================================
#
# # rationale: C's <inttypes.h> provides intmax_t arithmetic helpers
#   (imaxabs, imaxdiv) plus base-2 / base-8 parsing utilities. The
#   pre-refined version returned `Result CSignedInt64 Void` from
#   every operation, hiding real fallibility (division by zero) and
#   real partiality (parsing). The refined surface separates the
#   total ops (abs) from the fallible ones (divide-by-zero), and
#   keeps the parsers total — they stop scanning at the first
#   non-matching byte and return whatever has accumulated so far.
#
# # invariant: integer arithmetic is two's-complement; division
#   rounds toward zero (LLVM's sdiv); modulo carries the sign of
#   the dividend (LLVM's srem).
#
# # security: parsers walk a null-terminated input byte by byte and
#   stop at the first byte outside the digit set OR the NUL
#   terminator (byte == 0 stops because '0' is byte 48, not 0).
#   No bounds check needed; the NUL terminator is the boundary.
#
# # timing: arithmetic ops are O(1); parsers are O(byteLength).
#
# # observability: no logs; parsers do not signal "junk after the
#   digits were consumed" — that contract belongs to a stricter
#   variant in stdlib.as.

project StdInttypesSelfTest
target console
runtime AgentRuntime 0.1
entry console main

# Typed error domain for integer arithmetic. AgentScript-style errors
# replace the previous "negative return = failure" C convention. The
# only currently-detected failure is divide-by-zero — overflow is not
# detected here because LLVM's sdiv/srem wrap silently and we accept
# that as the documented behavior in the operation warnings below.
error IntegerArithmeticError
errorCase IntegerArithmeticError DivisionByZeroAttempted

error MainError
errorCase MainError InttypesSmokeAssertionFailed
errorCase MainError ConsoleWriteFailed

# section capability
# rationale: smoke-test main writes a single OK line to stdout.
capability stdoutWriteCapability console.stdout write

domainLiteral integerZeroComparisonValue CSignedInt64 0
domainLiteralTrust integerZeroComparisonValue trustedStaticLiteral
domainLiteral integerNegativeOneMultiplier CSignedInt64 -1
domainLiteralTrust integerNegativeOneMultiplier trustedStaticLiteral
domainLiteral asciiDigitZeroByte CSignedInt64 48
domainLiteralTrust asciiDigitZeroByte trustedStaticLiteral
domainLiteral asciiDigitOneByte CSignedInt64 49
domainLiteralTrust asciiDigitOneByte trustedStaticLiteral
domainLiteral asciiDigitSevenByte CSignedInt64 55
domainLiteralTrust asciiDigitSevenByte trustedStaticLiteral
domainLiteral binaryBase CSignedInt64 2
domainLiteralTrust binaryBase trustedStaticLiteral
domainLiteral octalBase CSignedInt64 8
domainLiteralTrust octalBase trustedStaticLiteral
domainLiteral integerOneStep CSignedInt64 1
domainLiteralTrust integerOneStep trustedStaticLiteral

# section inttypes.absoluteValue

operation absoluteMaxWidthSignedInt
input absoluteMaxWidthSignedInt inputValue CSignedInt64
output absoluteMaxWidthSignedInt CSignedInt64
memoryHeap absoluteMaxWidthSignedInt no
async absoluteMaxWidthSignedInt no
purpose absoluteMaxWidthSignedInt "Returns |inputValue| over the CSignedInt64 domain."
invariant absoluteMaxWidthSignedInt "Non-negative result for every input except INT64_MIN."
warning absoluteMaxWidthSignedInt "INT64_MIN negated overflows back to INT64_MIN (no positive representation exists in two's complement)."
guarantee absoluteMaxWidthSignedInt "Total — every input produces some CSignedInt64 result."
label startAbsoluteMaxWidthSignedInt
call detectInputIsNegativeCall math.lessThanI64
arg detectInputIsNegativeCall left inputValue
arg detectInputIsNegativeCall right integerZeroComparisonValue
run detectInputIsNegativeCall
bind inputIsNegative Bool detectInputIsNegativeCall
branchIf inputIsNegative negateInputForAbsoluteValue
returnValue inputValue
label negateInputForAbsoluteValue
call multiplyByNegativeOneCall math.multiplyI64
arg multiplyByNegativeOneCall left inputValue
arg multiplyByNegativeOneCall right integerNegativeOneMultiplier
run multiplyByNegativeOneCall
bind negatedAbsoluteValue CSignedInt64 multiplyByNegativeOneCall
returnValue negatedAbsoluteValue

# section inttypes.division

operation divideMaxWidthSignedIntQuotient
input divideMaxWidthSignedIntQuotient dividendValue CSignedInt64
input divideMaxWidthSignedIntQuotient divisorValue CSignedInt64
output divideMaxWidthSignedIntQuotient Result CSignedInt64 IntegerArithmeticError
memoryHeap divideMaxWidthSignedIntQuotient no
async divideMaxWidthSignedIntQuotient no
purpose divideMaxWidthSignedIntQuotient "Integer quotient dividendValue / divisorValue, rounded toward zero. Fails when divisorValue is zero."
invariant divideMaxWidthSignedIntQuotient "Quotient sign is dividend sign XOR divisor sign."
failure divideMaxWidthSignedIntQuotient DivisionByZeroAttempted "Returned when divisorValue equals zero — caller must screen first."
guarantee divideMaxWidthSignedIntQuotient "Defined for every (dividendValue, nonZeroDivisorValue) input pair."
label startDivideMaxWidthSignedIntQuotient
call detectDivisorIsZeroCall math.equalI64
arg detectDivisorIsZeroCall left divisorValue
arg detectDivisorIsZeroCall right integerZeroComparisonValue
run detectDivisorIsZeroCall
bind divisorIsZero Bool detectDivisorIsZeroCall
branchIf divisorIsZero raiseDivisionByZeroForQuotient
call computeSignedQuotientCall math.divideI64
arg computeSignedQuotientCall left dividendValue
arg computeSignedQuotientCall right divisorValue
run computeSignedQuotientCall
bind computedQuotient CSignedInt64 computeSignedQuotientCall
returnOk computedQuotient
label raiseDivisionByZeroForQuotient
makeError quotientDivisionByZeroFailure IntegerArithmeticError.DivisionByZeroAttempted
returnError quotientDivisionByZeroFailure

operation divideMaxWidthSignedIntRemainder
input divideMaxWidthSignedIntRemainder dividendValue CSignedInt64
input divideMaxWidthSignedIntRemainder divisorValue CSignedInt64
output divideMaxWidthSignedIntRemainder Result CSignedInt64 IntegerArithmeticError
memoryHeap divideMaxWidthSignedIntRemainder no
async divideMaxWidthSignedIntRemainder no
purpose divideMaxWidthSignedIntRemainder "Integer remainder dividendValue % divisorValue. Fails when divisorValue is zero."
invariant divideMaxWidthSignedIntRemainder "Remainder sign carries the dividend sign (LLVM srem semantics)."
failure divideMaxWidthSignedIntRemainder DivisionByZeroAttempted "Returned when divisorValue equals zero."
guarantee divideMaxWidthSignedIntRemainder "Defined for every (dividendValue, nonZeroDivisorValue) input pair."
label startDivideMaxWidthSignedIntRemainder
call detectDivisorIsZeroForRemainderCall math.equalI64
arg detectDivisorIsZeroForRemainderCall left divisorValue
arg detectDivisorIsZeroForRemainderCall right integerZeroComparisonValue
run detectDivisorIsZeroForRemainderCall
bind divisorIsZeroForRemainder Bool detectDivisorIsZeroForRemainderCall
branchIf divisorIsZeroForRemainder raiseDivisionByZeroForRemainder
call computeSignedRemainderCall math.moduloI64
arg computeSignedRemainderCall left dividendValue
arg computeSignedRemainderCall right divisorValue
run computeSignedRemainderCall
bind computedRemainder CSignedInt64 computeSignedRemainderCall
returnOk computedRemainder
label raiseDivisionByZeroForRemainder
makeError remainderDivisionByZeroFailure IntegerArithmeticError.DivisionByZeroAttempted
returnError remainderDivisionByZeroFailure

# section inttypes.parsers

operation parsePositiveBinaryCStringToSignedInt64
input parsePositiveBinaryCStringToSignedInt64 inputText CNullTerminatedByteString
output parsePositiveBinaryCStringToSignedInt64 CSignedInt64
memoryHeap parsePositiveBinaryCStringToSignedInt64 no
async parsePositiveBinaryCStringToSignedInt64 no
purpose parsePositiveBinaryCStringToSignedInt64 "Parse a null-terminated C string of '0' / '1' bytes as an unsigned base-2 integer. Stops at the first byte that is neither '0' nor '1' and returns the partial accumulator."
invariant parsePositiveBinaryCStringToSignedInt64 "Empty or junk inputs return 0; otherwise the prefix of valid binary digits is consumed left-to-right."
warning parsePositiveBinaryCStringToSignedInt64 "No overflow detection — inputs longer than 63 binary digits silently wrap around CSignedInt64."
guarantee parsePositiveBinaryCStringToSignedInt64 "Total (no error path); always terminates at the NUL terminator or first invalid byte."
label startParsePositiveBinaryCStringToSignedInt64
var binaryAccumulator I64 0
var binaryByteCursor I64 0
label binaryParseLoop
call loadBinaryByteCall pointer.loadByte
arg loadBinaryByteCall buffer inputText
arg loadBinaryByteCall offset binaryByteCursor
run loadBinaryByteCall
bind currentBinaryByte I8 loadBinaryByteCall
call detectBinaryByteIsZeroCall math.equalI64
arg detectBinaryByteIsZeroCall left currentBinaryByte
arg detectBinaryByteIsZeroCall right asciiDigitZeroByte
run detectBinaryByteIsZeroCall
bind binaryByteIsZeroChar Bool detectBinaryByteIsZeroCall
branchIf binaryByteIsZeroChar shiftAccumulatorForZeroBit
call detectBinaryByteIsOneCall math.equalI64
arg detectBinaryByteIsOneCall left currentBinaryByte
arg detectBinaryByteIsOneCall right asciiDigitOneByte
run detectBinaryByteIsOneCall
bind binaryByteIsOneChar Bool detectBinaryByteIsOneCall
branchIf binaryByteIsOneChar shiftAccumulatorForOneBit
branch binaryParseDone
label shiftAccumulatorForZeroBit
call doubleAccumulatorForZeroCall math.multiplyI64
arg doubleAccumulatorForZeroCall left binaryAccumulator
arg doubleAccumulatorForZeroCall right binaryBase
run doubleAccumulatorForZeroCall
bind accumulatorAfterZeroBit I64 doubleAccumulatorForZeroCall
set binaryAccumulator accumulatorAfterZeroBit
branch advanceBinaryCursor
label shiftAccumulatorForOneBit
call doubleAccumulatorForOneCall math.multiplyI64
arg doubleAccumulatorForOneCall left binaryAccumulator
arg doubleAccumulatorForOneCall right binaryBase
run doubleAccumulatorForOneCall
bind shiftedAccumulatorForOneBit I64 doubleAccumulatorForOneCall
call addOneBitCall math.addI64
arg addOneBitCall left shiftedAccumulatorForOneBit
arg addOneBitCall right integerOneStep
run addOneBitCall
bind accumulatorAfterOneBit I64 addOneBitCall
set binaryAccumulator accumulatorAfterOneBit
branch advanceBinaryCursor
label advanceBinaryCursor
call advanceBinaryCursorCall math.addI64
arg advanceBinaryCursorCall left binaryByteCursor
arg advanceBinaryCursorCall right integerOneStep
run advanceBinaryCursorCall
bind nextBinaryCursorPosition I64 advanceBinaryCursorCall
set binaryByteCursor nextBinaryCursorPosition
branch binaryParseLoop
label binaryParseDone
returnValue binaryAccumulator

operation parsePositiveOctalCStringToSignedInt64
input parsePositiveOctalCStringToSignedInt64 inputText CNullTerminatedByteString
output parsePositiveOctalCStringToSignedInt64 CSignedInt64
memoryHeap parsePositiveOctalCStringToSignedInt64 no
async parsePositiveOctalCStringToSignedInt64 no
purpose parsePositiveOctalCStringToSignedInt64 "Parse a null-terminated C string of '0'..'7' bytes as an unsigned base-8 integer. Stops at the first byte outside that range."
invariant parsePositiveOctalCStringToSignedInt64 "Empty or junk inputs return 0; otherwise the prefix of valid octal digits is consumed left-to-right."
warning parsePositiveOctalCStringToSignedInt64 "No overflow detection — inputs longer than 21 octal digits silently wrap around CSignedInt64."
guarantee parsePositiveOctalCStringToSignedInt64 "Total."
label startParsePositiveOctalCStringToSignedInt64
var octalAccumulator I64 0
var octalByteCursor I64 0
label octalParseLoop
call loadOctalByteCall pointer.loadByte
arg loadOctalByteCall buffer inputText
arg loadOctalByteCall offset octalByteCursor
run loadOctalByteCall
bind currentOctalByte I8 loadOctalByteCall
call detectOctalByteBelowRangeCall math.lessThanI64
arg detectOctalByteBelowRangeCall left currentOctalByte
arg detectOctalByteBelowRangeCall right asciiDigitZeroByte
run detectOctalByteBelowRangeCall
bind octalByteBelowRange Bool detectOctalByteBelowRangeCall
branchIf octalByteBelowRange octalParseDone
call detectOctalByteAboveRangeCall math.greaterThanI64
arg detectOctalByteAboveRangeCall left currentOctalByte
arg detectOctalByteAboveRangeCall right asciiDigitSevenByte
run detectOctalByteAboveRangeCall
bind octalByteAboveRange Bool detectOctalByteAboveRangeCall
branchIf octalByteAboveRange octalParseDone
call computeOctalDigitValueCall math.subtractI64
arg computeOctalDigitValueCall left currentOctalByte
arg computeOctalDigitValueCall right asciiDigitZeroByte
run computeOctalDigitValueCall
bind currentOctalDigitValue I64 computeOctalDigitValueCall
call shiftAccumulatorForOctalCall math.multiplyI64
arg shiftAccumulatorForOctalCall left octalAccumulator
arg shiftAccumulatorForOctalCall right octalBase
run shiftAccumulatorForOctalCall
bind shiftedOctalAccumulator I64 shiftAccumulatorForOctalCall
call addOctalDigitCall math.addI64
arg addOctalDigitCall left shiftedOctalAccumulator
arg addOctalDigitCall right currentOctalDigitValue
run addOctalDigitCall
bind octalAccumulatorAfterDigit I64 addOctalDigitCall
set octalAccumulator octalAccumulatorAfterDigit
call advanceOctalCursorCall math.addI64
arg advanceOctalCursorCall left octalByteCursor
arg advanceOctalCursorCall right integerOneStep
run advanceOctalCursorCall
bind nextOctalCursorPosition I64 advanceOctalCursorCall
set octalByteCursor nextOctalCursorPosition
branch octalParseLoop
label octalParseDone
returnValue octalAccumulator

# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
useCapability main stdoutWriteCapability
effect main write console.stdout
memoryHeap main no
async main no
purpose main "Smoke-test the inttypes helpers end-to-end."
invariant main "All assertions hold or the failure path runs."

label startMain

# absoluteMaxWidthSignedInt(-7) == 7
const negativeSevenValue CSignedInt64 -7
call assertAbsCall absoluteMaxWidthSignedInt
arg assertAbsCall inputValue negativeSevenValue
run assertAbsCall
bind absResult CSignedInt64 assertAbsCall
const sevenValue CSignedInt64 7
call checkAbsCall math.equalI64
arg checkAbsCall left absResult
arg checkAbsCall right sevenValue
run checkAbsCall
bind absOk Bool checkAbsCall
branchIf absOk absHolds
branch smokeAssertionFailed
label absHolds

# parsePositiveBinaryCStringToSignedInt64("1101") == 13
const binaryThirteenText CNullTerminatedByteString "1101"
call assertParseBinaryCall parsePositiveBinaryCStringToSignedInt64
arg assertParseBinaryCall inputText binaryThirteenText
run assertParseBinaryCall
bind parseBinaryResult CSignedInt64 assertParseBinaryCall
const thirteenValue CSignedInt64 13
call checkParseBinaryCall math.equalI64
arg checkParseBinaryCall left parseBinaryResult
arg checkParseBinaryCall right thirteenValue
run checkParseBinaryCall
bind parseBinaryOk Bool checkParseBinaryCall
branchIf parseBinaryOk parseBinaryHolds
branch smokeAssertionFailed
label parseBinaryHolds

# parsePositiveOctalCStringToSignedInt64("755") == 493
const octal755Text CNullTerminatedByteString "755"
call assertParseOctalCall parsePositiveOctalCStringToSignedInt64
arg assertParseOctalCall inputText octal755Text
run assertParseOctalCall
bind parseOctalResult CSignedInt64 assertParseOctalCall
const fourNinetyThreeValue CSignedInt64 493
call checkParseOctalCall math.equalI64
arg checkParseOctalCall left parseOctalResult
arg checkParseOctalCall right fourNinetyThreeValue
run checkParseOctalCall
bind parseOctalOk Bool checkParseOctalCall
branchIf parseOctalOk parseOctalHolds
branch smokeAssertionFailed
label parseOctalHolds

# ============================================================
# Extended unit tests: covers the 2 ops the smoke previously
# omitted (divideMaxWidthSignedIntQuotient + Remainder).
# ============================================================

const numeratorTwentyThree CSignedInt64 23
const denominatorFour CSignedInt64 4
const expectedQuotientFive CSignedInt64 5
const expectedRemainderThree CSignedInt64 3

# divideMaxWidthSignedIntQuotient(23, 4) == 5
call divQuotientCall divideMaxWidthSignedIntQuotient
arg divQuotientCall numeratorValue numeratorTwentyThree
arg divQuotientCall denominatorValue denominatorFour
run divQuotientCall
bindOk divQuotientResult CSignedInt64 divQuotientCall
call checkDivQuotientCall math.equalI64
arg checkDivQuotientCall left divQuotientResult
arg checkDivQuotientCall right expectedQuotientFive
run checkDivQuotientCall
bind divQuotientOk Bool checkDivQuotientCall
branchIf divQuotientOk divQuotientHolds
branch smokeAssertionFailed
label divQuotientHolds

# divideMaxWidthSignedIntRemainder(23, 4) == 3
call divRemainderCall divideMaxWidthSignedIntRemainder
arg divRemainderCall numeratorValue numeratorTwentyThree
arg divRemainderCall denominatorValue denominatorFour
run divRemainderCall
bindOk divRemainderResult CSignedInt64 divRemainderCall
call checkDivRemainderCall math.equalI64
arg checkDivRemainderCall left divRemainderResult
arg checkDivRemainderCall right expectedRemainderThree
run checkDivRemainderCall
bind divRemainderOk Bool checkDivRemainderCall
branchIf divRemainderOk divRemainderHolds
branch smokeAssertionFailed
label divRemainderHolds

# Property: quotient * denominator + remainder == numerator
# (5 * 4 + 3 == 23)
call propMulCall math.multiplyI64
arg propMulCall left divQuotientResult
arg propMulCall right denominatorFour
run propMulCall
bind propMulResult CSignedInt64 propMulCall
call propAddCall math.addI64
arg propAddCall left propMulResult
arg propAddCall right divRemainderResult
run propAddCall
bind propAddResult CSignedInt64 propAddCall
call propCheckCall math.equalI64
arg propCheckCall left propAddResult
arg propCheckCall right numeratorTwentyThree
run propCheckCall
bind propCheckOk Bool propCheckCall
branchIf propCheckOk propCheckHolds
branch smokeAssertionFailed
label propCheckHolds

# divideMaxWidthSignedIntQuotient(0, 5) == 0 (zero dividend)
const zeroNumerator CSignedInt64 0
const fiveDenominator CSignedInt64 5
call divZeroQuotientCall divideMaxWidthSignedIntQuotient
arg divZeroQuotientCall numeratorValue zeroNumerator
arg divZeroQuotientCall denominatorValue fiveDenominator
run divZeroQuotientCall
bindOk divZeroQuotientResult CSignedInt64 divZeroQuotientCall
call checkDivZeroQuotientCall math.equalI64
arg checkDivZeroQuotientCall left divZeroQuotientResult
arg checkDivZeroQuotientCall right zeroNumerator
run checkDivZeroQuotientCall
bind divZeroQuotientOk Bool checkDivZeroQuotientCall
branchIf divZeroQuotientOk divZeroQuotientHolds
branch smokeAssertionFailed
label divZeroQuotientHolds

# parsePositiveBinaryCStringToSignedInt64("0") == 0 (boundary)
const binaryZeroText CNullTerminatedByteString "0"
call parseZeroBinaryCall parsePositiveBinaryCStringToSignedInt64
arg parseZeroBinaryCall inputText binaryZeroText
run parseZeroBinaryCall
bind parseZeroBinaryResult CSignedInt64 parseZeroBinaryCall
call checkParseZeroBinaryCall math.equalI64
arg checkParseZeroBinaryCall left parseZeroBinaryResult
arg checkParseZeroBinaryCall right zeroNumerator
run checkParseZeroBinaryCall
bind parseZeroBinaryOk Bool checkParseZeroBinaryCall
branchIf parseZeroBinaryOk parseZeroBinaryHolds
branch smokeAssertionFailed
label parseZeroBinaryHolds

# absoluteMaxWidthSignedInt(0) == 0 (boundary)
call absZeroCall absoluteMaxWidthSignedInt
arg absZeroCall inputValue zeroNumerator
run absZeroCall
bind absZeroResult CSignedInt64 absZeroCall
call checkAbsZeroCall math.equalI64
arg checkAbsZeroCall left absZeroResult
arg checkAbsZeroCall right zeroNumerator
run checkAbsZeroCall
bind absZeroOk Bool checkAbsZeroCall
branchIf absZeroOk absZeroHolds
branch smokeAssertionFailed
label absZeroHolds

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
makeError inttypesSmokeFailure MainError.InttypesSmokeAssertionFailed
returnError inttypesSmokeFailure
