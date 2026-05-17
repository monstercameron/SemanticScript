project StdStdlibSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError WriteFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <stdlib.h>-style numeric ops.
#
# Operations:
#   parseDecimalCStringToSignedInt64(s)     - like atol/atoll. Decimal C-string -> i64.
#   parseHexCStringToSignedInt64(s)         - like strtol(s, NULL, 16). Hex C-string -> i64.
#   absoluteSignedInt64(n)         - like abs/labs/llabs. |n|.
#   minimumSignedInt64(a, b)           - min of two signed 64-bit ints.
#   maximumSignedInt64(a, b)           - max of two signed 64-bit ints.
#   powerSignedInt64(base, exp)    - integer power base^exp via repeated multiplication.
#   greatestCommonDivisorSignedInt64(a, b)           - greatest common divisor (Euclidean algorithm).
#   clampSignedInt64ToInclusiveRange(x, lo, hi)    - clamp x into [lo, hi].
# ============================================================


operation parseDecimalCStringToSignedInt64
input parseDecimalCStringToSignedInt64 inputText CNullTerminatedByteString
output parseDecimalCStringToSignedInt64 Result CSignedInt64 Void
effect parseDecimalCStringToSignedInt64 read memory.buffer
memory parseDecimalCStringToSignedInt64 heap no
memory parseDecimalCStringToSignedInt64 stack max 1KiB
async parseDecimalCStringToSignedInt64 no
purpose parseDecimalCStringToSignedInt64 "AS-native atoi/atol. Skips ASCII whitespace, accepts optional sign, accumulates decimal digits until a non-digit byte."

label startParseDecimalCStringToSignedInt64
const zeroI64a I64 0
const oneI64a I64 1
const negOneI64a I64 -1
const tenI64a I64 10
const asciiZeroI64 I64 48
const asciiNineI64 I64 57
const asciiSpaceI64 I64 32
const asciiTabI64 I64 9
const asciiPlusI64 I64 43
const asciiMinusI64 I64 45
var cursor I64 0
label skipWs
call wsLoadCall pointer.loadByte
arg wsLoadCall buffer inputText
arg wsLoadCall offset cursor
run wsLoadCall
bind wsByte I8 wsLoadCall
call wsIsSpaceCall math.equalI64
arg wsIsSpaceCall left wsByte
arg wsIsSpaceCall right asciiSpaceI64
run wsIsSpaceCall
bind wsIsSpace Bool wsIsSpaceCall
branchIf wsIsSpace consumeWs
call wsIsTabCall math.equalI64
arg wsIsTabCall left wsByte
arg wsIsTabCall right asciiTabI64
run wsIsTabCall
bind wsIsTab Bool wsIsTabCall
branchIf wsIsTab consumeWs
branch checkSign
label consumeWs
call wsIncCall math.addI64
arg wsIncCall left cursor
arg wsIncCall right oneI64a
run wsIncCall
bind wsNext I64 wsIncCall
set cursor wsNext
branch skipWs
label checkSign
var signMultiplier I64 1
call signLoadCall pointer.loadByte
arg signLoadCall buffer inputText
arg signLoadCall offset cursor
run signLoadCall
bind signByte I8 signLoadCall
call isPlusCall math.equalI64
arg isPlusCall left signByte
arg isPlusCall right asciiPlusI64
run isPlusCall
bind isPlus Bool isPlusCall
branchIf isPlus consumePlus
call isMinusCall math.equalI64
arg isMinusCall left signByte
arg isMinusCall right asciiMinusI64
run isMinusCall
bind isMinus Bool isMinusCall
branchIf isMinus consumeMinus
branch parseDigits
label consumePlus
call plusIncCall math.addI64
arg plusIncCall left cursor
arg plusIncCall right oneI64a
run plusIncCall
bind plusNext I64 plusIncCall
set cursor plusNext
branch parseDigits
label consumeMinus
set signMultiplier negOneI64a
call minusIncCall math.addI64
arg minusIncCall left cursor
arg minusIncCall right oneI64a
run minusIncCall
bind minusNext I64 minusIncCall
set cursor minusNext
branch parseDigits
label parseDigits
var accumulator I64 0
label digitStep
call digLoadCall pointer.loadByte
arg digLoadCall buffer inputText
arg digLoadCall offset cursor
run digLoadCall
bind digByte I8 digLoadCall
call belowZeroCall math.lessThanI64
arg belowZeroCall left digByte
arg belowZeroCall right asciiZeroI64
run belowZeroCall
bind isBelowZero Bool belowZeroCall
branchIf isBelowZero parseDone
call aboveNineCall math.greaterThanI64
arg aboveNineCall left digByte
arg aboveNineCall right asciiNineI64
run aboveNineCall
bind isAboveNine Bool aboveNineCall
branchIf isAboveNine parseDone
call digitValueCall math.subtractI64
arg digitValueCall left digByte
arg digitValueCall right asciiZeroI64
run digitValueCall
bind digitValue I64 digitValueCall
call shiftLeftCall math.multiplyI64
arg shiftLeftCall left accumulator
arg shiftLeftCall right tenI64a
run shiftLeftCall
bind shifted I64 shiftLeftCall
call addDigitCall math.addI64
arg addDigitCall left shifted
arg addDigitCall right digitValue
run addDigitCall
bind nextAccum I64 addDigitCall
set accumulator nextAccum
call digIncCall math.addI64
arg digIncCall left cursor
arg digIncCall right oneI64a
run digIncCall
bind digNext I64 digIncCall
set cursor digNext
branch digitStep
label parseDone
call signApplyCall math.multiplyI64
arg signApplyCall left accumulator
arg signApplyCall right signMultiplier
run signApplyCall
bind signedResult CSignedInt64 signApplyCall
returnOk signedResult


operation parseHexCStringToSignedInt64
input parseHexCStringToSignedInt64 inputText CNullTerminatedByteString
output parseHexCStringToSignedInt64 Result CSignedInt64 Void
effect parseHexCStringToSignedInt64 read memory.buffer
memory parseHexCStringToSignedInt64 heap no
memory parseHexCStringToSignedInt64 stack max 1KiB
async parseHexCStringToSignedInt64 no
purpose parseHexCStringToSignedInt64 "AS-native strtol(s, NULL, 16). Skips whitespace, accepts optional sign and optional 0x/0X prefix, then accumulates hex digits."

label startParseHexCStringToSignedInt64
const zeroH I64 0
const oneH I64 1
const negOneH I64 -1
const sixteenH I64 16
const asciiZeroH I64 48
const asciiNineH I64 57
const upperAH I64 65
const upperFH I64 70
const lowerAH I64 97
const lowerFH I64 102
const spaceH I64 32
const tabH I64 9
const plusH I64 43
const minusH I64 45
const zeroChar I64 48
const lowerX I64 120
const upperX I64 88
const tenOffset I64 10
const aOffset I64 87
const upperAOffset I64 55

var hxCursor I64 0
label hxSkipWs
call hxWsLoadCall pointer.loadByte
arg hxWsLoadCall buffer inputText
arg hxWsLoadCall offset hxCursor
run hxWsLoadCall
bind hxWsByte I8 hxWsLoadCall
call hxWsSpCall math.equalI64
arg hxWsSpCall left hxWsByte
arg hxWsSpCall right spaceH
run hxWsSpCall
bind hxWsSp Bool hxWsSpCall
branchIf hxWsSp hxConsumeWs
call hxWsTbCall math.equalI64
arg hxWsTbCall left hxWsByte
arg hxWsTbCall right tabH
run hxWsTbCall
bind hxWsTb Bool hxWsTbCall
branchIf hxWsTb hxConsumeWs
branch hxCheckSign
label hxConsumeWs
call hxWsIncCall math.addI64
arg hxWsIncCall left hxCursor
arg hxWsIncCall right oneH
run hxWsIncCall
bind hxWsNext I64 hxWsIncCall
set hxCursor hxWsNext
branch hxSkipWs

label hxCheckSign
var hxSignMul I64 1
call hxSignLoadCall pointer.loadByte
arg hxSignLoadCall buffer inputText
arg hxSignLoadCall offset hxCursor
run hxSignLoadCall
bind hxSignByte I8 hxSignLoadCall
call hxIsPlusCall math.equalI64
arg hxIsPlusCall left hxSignByte
arg hxIsPlusCall right plusH
run hxIsPlusCall
bind hxIsPlus Bool hxIsPlusCall
branchIf hxIsPlus hxConsumePlus
call hxIsMinusCall math.equalI64
arg hxIsMinusCall left hxSignByte
arg hxIsMinusCall right minusH
run hxIsMinusCall
bind hxIsMinus Bool hxIsMinusCall
branchIf hxIsMinus hxConsumeMinus
branch hxCheckPrefix
label hxConsumePlus
call hxPlusIncCall math.addI64
arg hxPlusIncCall left hxCursor
arg hxPlusIncCall right oneH
run hxPlusIncCall
bind hxPlusNext I64 hxPlusIncCall
set hxCursor hxPlusNext
branch hxCheckPrefix
label hxConsumeMinus
set hxSignMul negOneH
call hxMinusIncCall math.addI64
arg hxMinusIncCall left hxCursor
arg hxMinusIncCall right oneH
run hxMinusIncCall
bind hxMinusNext I64 hxMinusIncCall
set hxCursor hxMinusNext
branch hxCheckPrefix

label hxCheckPrefix
# Optional 0x or 0X prefix
call hxPrefLoadCall pointer.loadByte
arg hxPrefLoadCall buffer inputText
arg hxPrefLoadCall offset hxCursor
run hxPrefLoadCall
bind hxPrefByte I8 hxPrefLoadCall
call hxIsZeroCall math.equalI64
arg hxIsZeroCall left hxPrefByte
arg hxIsZeroCall right zeroChar
run hxIsZeroCall
bind hxIsZero Bool hxIsZeroCall
branchIf hxIsZero hxMaybePrefix
branch hxParseHex

label hxMaybePrefix
call hxIncPref1Call math.addI64
arg hxIncPref1Call left hxCursor
arg hxIncPref1Call right oneH
run hxIncPref1Call
bind hxIncPref1 I64 hxIncPref1Call
call hxLoadPrefX pointer.loadByte
arg hxLoadPrefX buffer inputText
arg hxLoadPrefX offset hxIncPref1
run hxLoadPrefX
bind hxPrefXByte I8 hxLoadPrefX
call hxIsLowerXCall math.equalI64
arg hxIsLowerXCall left hxPrefXByte
arg hxIsLowerXCall right lowerX
run hxIsLowerXCall
bind hxIsLowerX Bool hxIsLowerXCall
branchIf hxIsLowerX hxConsumePrefix
call hxIsUpperXCall math.equalI64
arg hxIsUpperXCall left hxPrefXByte
arg hxIsUpperXCall right upperX
run hxIsUpperXCall
bind hxIsUpperX Bool hxIsUpperXCall
branchIf hxIsUpperX hxConsumePrefix
branch hxParseHex
label hxConsumePrefix
call hxAdv2real math.addI64
arg hxAdv2real left hxCursor
arg hxAdv2real right oneH
run hxAdv2real
bind hxA1 I64 hxAdv2real
call hxAdv2real2 math.addI64
arg hxAdv2real2 left hxA1
arg hxAdv2real2 right oneH
run hxAdv2real2
bind hxA2 I64 hxAdv2real2
set hxCursor hxA2
branch hxParseHex

label hxParseHex
var hxAccum I64 0
var hxDecValue I64 0
label hxDigitStep
call hxDigLoadCall pointer.loadByte
arg hxDigLoadCall buffer inputText
arg hxDigLoadCall offset hxCursor
run hxDigLoadCall
bind hxDigByte I8 hxDigLoadCall

# Is digit 0-9?
call hxIsDecBelowCall math.lessThanI64
arg hxIsDecBelowCall left hxDigByte
arg hxIsDecBelowCall right asciiZeroH
run hxIsDecBelowCall
bind hxIsDecBelow Bool hxIsDecBelowCall
branchIf hxIsDecBelow hxCheckUpperHex
call hxIsDecAboveCall math.greaterThanI64
arg hxIsDecAboveCall left hxDigByte
arg hxIsDecAboveCall right asciiNineH
run hxIsDecAboveCall
bind hxIsDecAbove Bool hxIsDecAboveCall
branchIf hxIsDecAbove hxCheckUpperHex
call hxDecValueCall math.subtractI64
arg hxDecValueCall left hxDigByte
arg hxDecValueCall right asciiZeroH
run hxDecValueCall
bind hxDecRaw I64 hxDecValueCall
set hxDecValue hxDecRaw
branch hxAccumDigit

label hxCheckUpperHex
call hxIsUABelowCall math.lessThanI64
arg hxIsUABelowCall left hxDigByte
arg hxIsUABelowCall right upperAH
run hxIsUABelowCall
bind hxIsUABelow Bool hxIsUABelowCall
branchIf hxIsUABelow hxCheckLowerHex
call hxIsUAAboveCall math.greaterThanI64
arg hxIsUAAboveCall left hxDigByte
arg hxIsUAAboveCall right upperFH
run hxIsUAAboveCall
bind hxIsUAAbove Bool hxIsUAAboveCall
branchIf hxIsUAAbove hxCheckLowerHex
call hxUAValueCall math.subtractI64
arg hxUAValueCall left hxDigByte
arg hxUAValueCall right upperAOffset
run hxUAValueCall
bind hxDecValueU I64 hxUAValueCall
set hxDecValue hxDecValueU
branch hxAccumDigit

label hxCheckLowerHex
call hxIsLABelowCall math.lessThanI64
arg hxIsLABelowCall left hxDigByte
arg hxIsLABelowCall right lowerAH
run hxIsLABelowCall
bind hxIsLABelow Bool hxIsLABelowCall
branchIf hxIsLABelow hxDone
call hxIsLAAboveCall math.greaterThanI64
arg hxIsLAAboveCall left hxDigByte
arg hxIsLAAboveCall right lowerFH
run hxIsLAAboveCall
bind hxIsLAAbove Bool hxIsLAAboveCall
branchIf hxIsLAAbove hxDone
call hxLAValueCall math.subtractI64
arg hxLAValueCall left hxDigByte
arg hxLAValueCall right aOffset
run hxLAValueCall
bind hxDecValueL I64 hxLAValueCall
set hxDecValue hxDecValueL
branch hxAccumDigit

label hxAccumDigit
call hxShiftCall math.multiplyI64
arg hxShiftCall left hxAccum
arg hxShiftCall right sixteenH
run hxShiftCall
bind hxShifted I64 hxShiftCall
call hxAddCall math.addI64
arg hxAddCall left hxShifted
arg hxAddCall right hxDecValue
run hxAddCall
bind hxNextAccum I64 hxAddCall
set hxAccum hxNextAccum
call hxIncCall math.addI64
arg hxIncCall left hxCursor
arg hxIncCall right oneH
run hxIncCall
bind hxNext I64 hxIncCall
set hxCursor hxNext
branch hxDigitStep

label hxDone
call hxSignApplyCall math.multiplyI64
arg hxSignApplyCall left hxAccum
arg hxSignApplyCall right hxSignMul
run hxSignApplyCall
bind hxFinal CSignedInt64 hxSignApplyCall
returnOk hxFinal


operation absoluteSignedInt64
input absoluteSignedInt64 inputValue CSignedInt64
output absoluteSignedInt64 Result CSignedInt64 Void
memory absoluteSignedInt64 heap no
memory absoluteSignedInt64 stack max 1KiB
async absoluteSignedInt64 no
purpose absoluteSignedInt64 "Return |n|. Mirrors libc abs/labs/llabs semantics."
label startAbsoluteSignedInt64
const zeroI64b I64 0
const negOneI64b I64 -1
call isNegCall math.lessThanI64
arg isNegCall left inputValue
arg isNegCall right zeroI64b
run isNegCall
bind isNeg Bool isNegCall
branchIf isNeg flipIt
branch alreadyPositive
label flipIt
call flipCall math.multiplyI64
arg flipCall left inputValue
arg flipCall right negOneI64b
run flipCall
bind flipped CSignedInt64 flipCall
returnOk flipped
label alreadyPositive
returnOk inputValue


operation minimumSignedInt64
input minimumSignedInt64 leftValue CSignedInt64
input minimumSignedInt64 rightValue CSignedInt64
output minimumSignedInt64 Result CSignedInt64 Void
memory minimumSignedInt64 heap no
memory minimumSignedInt64 stack max 1KiB
async minimumSignedInt64 no
purpose minimumSignedInt64 "Smaller of a and b."
label startMinimumSignedInt64
call cmpCall math.lessThanI64
arg cmpCall left leftValue
arg cmpCall right rightValue
run cmpCall
bind aLessThan Bool cmpCall
branchIf aLessThan returnA
returnOk rightValue
label returnA
returnOk leftValue


operation maximumSignedInt64
input maximumSignedInt64 leftValue CSignedInt64
input maximumSignedInt64 rightValue CSignedInt64
output maximumSignedInt64 Result CSignedInt64 Void
memory maximumSignedInt64 heap no
memory maximumSignedInt64 stack max 1KiB
async maximumSignedInt64 no
purpose maximumSignedInt64 "Larger of a and b."
label startMaximumSignedInt64
call cmpMaxCall math.greaterThanI64
arg cmpMaxCall left leftValue
arg cmpMaxCall right rightValue
run cmpMaxCall
bind aGreater Bool cmpMaxCall
branchIf aGreater returnAmax
returnOk rightValue
label returnAmax
returnOk leftValue


operation powerSignedInt64
input powerSignedInt64 baseValue CSignedInt64
input powerSignedInt64 exponentValue CSignedInt64
output powerSignedInt64 Result CSignedInt64 Void
memory powerSignedInt64 heap no
memory powerSignedInt64 stack max 1KiB
async powerSignedInt64 no
purpose powerSignedInt64 "Integer pow: returns base^exponent by repeated multiplication. exponent must be >= 0. Returns 1 if exponent == 0; returns 0 if exponent < 0 (no fractional results)."
label startPowerSignedInt64
const zeroP I64 0
const oneP I64 1
call exNegCall math.lessThanI64
arg exNegCall left exponentValue
arg exNegCall right zeroP
run exNegCall
bind exNeg Bool exNegCall
branchIf exNeg powerZero
var product I64 1
var counter I64 0
label powLoop
call powDoneCall math.greaterThanOrEqualI64
arg powDoneCall left counter
arg powDoneCall right exponentValue
run powDoneCall
bind powDone Bool powDoneCall
branchIf powDone powReturn
call powMulCall math.multiplyI64
arg powMulCall left product
arg powMulCall right baseValue
run powMulCall
bind nextProd I64 powMulCall
set product nextProd
call powIncCall math.addI64
arg powIncCall left counter
arg powIncCall right oneP
run powIncCall
bind nextCount I64 powIncCall
set counter nextCount
branch powLoop
label powReturn
returnOk product
label powerZero
returnOk zeroP


operation greatestCommonDivisorSignedInt64
input greatestCommonDivisorSignedInt64 leftValue CSignedInt64
input greatestCommonDivisorSignedInt64 rightValue CSignedInt64
output greatestCommonDivisorSignedInt64 Result CSignedInt64 Void
memory greatestCommonDivisorSignedInt64 heap no
memory greatestCommonDivisorSignedInt64 stack max 1KiB
async greatestCommonDivisorSignedInt64 no
purpose greatestCommonDivisorSignedInt64 "Greatest common divisor via Euclidean algorithm. gcd(a, 0) = |a|; gcd handles either argument being negative by working on the absolute values."
label startGreatestCommonDivisorSignedInt64
call absACall absoluteSignedInt64
arg absACall n leftValue
run absACall
bindOk absA CSignedInt64 absACall
call absBCall absoluteSignedInt64
arg absBCall n rightValue
run absBCall
bindOk absB CSignedInt64 absBCall
var x I64 0
var y I64 0
set x absA
set y absB
const zeroG I64 0
label gcdLoop
call yZeroCall math.equalI64
arg yZeroCall left y
arg yZeroCall right zeroG
run yZeroCall
bind yIsZero Bool yZeroCall
branchIf yIsZero gcdReturn
call rCall math.moduloI64
arg rCall left x
arg rCall right y
run rCall
bind r I64 rCall
set x y
set y r
branch gcdLoop
label gcdReturn
returnOk x


operation clampSignedInt64ToInclusiveRange
input clampSignedInt64ToInclusiveRange inputValue CSignedInt64
input clampSignedInt64ToInclusiveRange lowerBound CSignedInt64
input clampSignedInt64ToInclusiveRange upperBound CSignedInt64
output clampSignedInt64ToInclusiveRange Result CSignedInt64 Void
memory clampSignedInt64ToInclusiveRange heap no
memory clampSignedInt64ToInclusiveRange stack max 1KiB
async clampSignedInt64ToInclusiveRange no
purpose clampSignedInt64ToInclusiveRange "Clamp x into [lo, hi]: return lo if x<lo, hi if x>hi, else x."
label startClampSignedInt64ToInclusiveRange
call belowLoCall math.lessThanI64
arg belowLoCall left inputValue
arg belowLoCall right lowerBound
run belowLoCall
bind belowLo Bool belowLoCall
branchIf belowLo returnLo
call aboveHiCall math.greaterThanI64
arg aboveHiCall left inputValue
arg aboveHiCall right upperBound
run aboveHiCall
bind aboveHi Bool aboveHiCall
branchIf aboveHi returnHi
returnOk inputValue
label returnLo
returnOk lowerBound
label returnHi
returnOk upperBound


# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test parseDecimalCStringToSignedInt64 / parseHexCStringToSignedInt64 / absoluteSignedInt64 / minimumSignedInt64 / maximumSignedInt64 / powerSignedInt64 / greatestCommonDivisorSignedInt64 / clampSignedInt64ToInclusiveRange. Prints OK."

label startMain

const numStr CNullTerminatedByteString "12345"
const expected1 CSignedInt64 12345
call p1 parseDecimalCStringToSignedInt64
arg p1 s numStr
run p1
bindOk p1Res CSignedInt64 p1
call p1CheckCall math.equalI64
arg p1CheckCall left p1Res
arg p1CheckCall right expected1
run p1CheckCall
bind p1Ok Bool p1CheckCall
branchIf p1Ok p1OkLabel
branch testFailed
label p1OkLabel

const negStr CNullTerminatedByteString "  -42"
const expected2 CSignedInt64 -42
call p2 parseDecimalCStringToSignedInt64
arg p2 s negStr
run p2
bindOk p2Res CSignedInt64 p2
call p2CheckCall math.equalI64
arg p2CheckCall left p2Res
arg p2CheckCall right expected2
run p2CheckCall
bind p2Ok Bool p2CheckCall
branchIf p2Ok p2OkLabel
branch testFailed
label p2OkLabel

# parseHexCStringToSignedInt64("0x1F") == 31
const hexStr CNullTerminatedByteString "0x1F"
const expectedHex CSignedInt64 31
call h1 parseHexCStringToSignedInt64
arg h1 s hexStr
run h1
bindOk h1Res CSignedInt64 h1
call h1CheckCall math.equalI64
arg h1CheckCall left h1Res
arg h1CheckCall right expectedHex
run h1CheckCall
bind h1Ok Bool h1CheckCall
branchIf h1Ok h1OkLabel
branch testFailed
label h1OkLabel

# parseHexCStringToSignedInt64("-ff") == -255
const negHexStr CNullTerminatedByteString "-ff"
const expectedNegHex CSignedInt64 -255
call h2 parseHexCStringToSignedInt64
arg h2 s negHexStr
run h2
bindOk h2Res CSignedInt64 h2
call h2CheckCall math.equalI64
arg h2CheckCall left h2Res
arg h2CheckCall right expectedNegHex
run h2CheckCall
bind h2Ok Bool h2CheckCall
branchIf h2Ok h2OkLabel
branch testFailed
label h2OkLabel

const negNinetyNine CSignedInt64 -99
const ninetyNine CSignedInt64 99
call a1 absoluteSignedInt64
arg a1 n negNinetyNine
run a1
bindOk a1Res CSignedInt64 a1
call a1CheckCall math.equalI64
arg a1CheckCall left a1Res
arg a1CheckCall right ninetyNine
run a1CheckCall
bind a1Ok Bool a1CheckCall
branchIf a1Ok a1OkLabel
branch testFailed
label a1OkLabel

const sevenInt CSignedInt64 7
const threeInt CSignedInt64 3
call m1 minimumSignedInt64
arg m1 a sevenInt
arg m1 b threeInt
run m1
bindOk m1Res CSignedInt64 m1
call m1CheckCall math.equalI64
arg m1CheckCall left m1Res
arg m1CheckCall right threeInt
run m1CheckCall
bind m1Ok Bool m1CheckCall
branchIf m1Ok m1OkLabel
branch testFailed
label m1OkLabel

call m2 maximumSignedInt64
arg m2 a sevenInt
arg m2 b threeInt
run m2
bindOk m2Res CSignedInt64 m2
call m2CheckCall math.equalI64
arg m2CheckCall left m2Res
arg m2CheckCall right sevenInt
run m2CheckCall
bind m2Ok Bool m2CheckCall
branchIf m2Ok m2OkLabel
branch testFailed
label m2OkLabel

# powerSignedInt64(2, 10) == 1024
const twoBase CSignedInt64 2
const tenExp CSignedInt64 10
const expected1024 CSignedInt64 1024
call pw1 powerSignedInt64
arg pw1 base twoBase
arg pw1 exponent tenExp
run pw1
bindOk pw1Res CSignedInt64 pw1
call pw1CheckCall math.equalI64
arg pw1CheckCall left pw1Res
arg pw1CheckCall right expected1024
run pw1CheckCall
bind pw1Ok Bool pw1CheckCall
branchIf pw1Ok pw1OkLabel
branch testFailed
label pw1OkLabel

# greatestCommonDivisorSignedInt64(54, 24) == 6
const fiftyFour CSignedInt64 54
const twentyFour CSignedInt64 24
const sixI64 CSignedInt64 6
call g1 greatestCommonDivisorSignedInt64
arg g1 a fiftyFour
arg g1 b twentyFour
run g1
bindOk g1Res CSignedInt64 g1
call g1CheckCall math.equalI64
arg g1CheckCall left g1Res
arg g1CheckCall right sixI64
run g1CheckCall
bind g1Ok Bool g1CheckCall
branchIf g1Ok g1OkLabel
branch testFailed
label g1OkLabel

# clampSignedInt64ToInclusiveRange(50, 0, 10) == 10
const fiftyI64 CSignedInt64 50
const zeroI64Lo CSignedInt64 0
const tenI64Hi CSignedInt64 10
call cl1 clampSignedInt64ToInclusiveRange
arg cl1 x fiftyI64
arg cl1 lo zeroI64Lo
arg cl1 hi tenI64Hi
run cl1
bindOk cl1Res CSignedInt64 cl1
call cl1CheckCall math.equalI64
arg cl1CheckCall left cl1Res
arg cl1CheckCall right tenI64Hi
run cl1CheckCall
bind cl1Ok Bool cl1CheckCall
branchIf cl1Ok cl1OkLabel
branch testFailed
label cl1OkLabel

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
makeError testFailure MainError.WriteFailed exitFail
returnError testFailure
