project StdInttypesSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <inttypes.h>-style helpers.
#
# Operations:
#   absoluteMaxWidthSignedInt(n)             Like libc absoluteMaxWidthSignedInt: absolute value of n.
#   divideMaxWidthSignedIntQuotient(a, b)          Returns quotient (the remainder is dropped
#                          at this layer; AS doesn't support struct
#                          returns from user-operations yet).
#   divideMaxWidthSignedIntRemainder(a, b)      Returns remainder.
#   parsePositiveBinaryCStringToSignedInt64(s) Parse a base-2 string of '0'/'1'.
#   parsePositiveOctalCStringToSignedInt64(s)  Parse a base-8 string of '0'..'7'.
# ============================================================


operation absoluteMaxWidthSignedInt
input absoluteMaxWidthSignedInt inputValue CSignedInt64
output absoluteMaxWidthSignedInt Result CSignedInt64 Void
memory absoluteMaxWidthSignedInt heap no
async absoluteMaxWidthSignedInt no
purpose absoluteMaxWidthSignedInt "Absolute value of intmax_t."
label startAbsoluteMaxWidthSignedInt
const zeroI I64 0
const negOneI I64 -1
call ltz math.lessThanI64
arg ltz left inputValue
arg ltz right zeroI
run ltz
bind isN Bool ltz
branchIf isN flip
returnOk inputValue
label flip
call neg math.multiplyI64
arg neg left inputValue
arg neg right negOneI
run neg
bind flipped CSignedInt64 neg
returnOk flipped


operation divideMaxWidthSignedIntQuotient
input divideMaxWidthSignedIntQuotient leftValue CSignedInt64
input divideMaxWidthSignedIntQuotient rightValue CSignedInt64
output divideMaxWidthSignedIntQuotient Result CSignedInt64 Void
memory divideMaxWidthSignedIntQuotient heap no
async divideMaxWidthSignedIntQuotient no
purpose divideMaxWidthSignedIntQuotient "Integer quotient a/b. Note: real libc divideMaxWidthSignedIntQuotient returns a struct with both quotient and remainder; AS user-operations can't return tuples yet, so we expose this and divideMaxWidthSignedIntRemainder separately."
label startDivideMaxWidthSignedIntQuotient
call divCall math.divideI64
arg divCall left leftValue
arg divCall right rightValue
run divCall
bind q CSignedInt64 divCall
returnOk q


operation divideMaxWidthSignedIntRemainder
input divideMaxWidthSignedIntRemainder leftValue CSignedInt64
input divideMaxWidthSignedIntRemainder rightValue CSignedInt64
output divideMaxWidthSignedIntRemainder Result CSignedInt64 Void
memory divideMaxWidthSignedIntRemainder heap no
async divideMaxWidthSignedIntRemainder no
purpose divideMaxWidthSignedIntRemainder "Integer remainder a%b."
label startDivideMaxWidthSignedIntRemainder
call modCall math.moduloI64
arg modCall left leftValue
arg modCall right rightValue
run modCall
bind r CSignedInt64 modCall
returnOk r


operation parsePositiveBinaryCStringToSignedInt64
input parsePositiveBinaryCStringToSignedInt64 inputText CNullTerminatedByteString
output parsePositiveBinaryCStringToSignedInt64 Result CSignedInt64 Void
effect parsePositiveBinaryCStringToSignedInt64 read memory.buffer
memory parsePositiveBinaryCStringToSignedInt64 heap no
async parsePositiveBinaryCStringToSignedInt64 no
purpose parsePositiveBinaryCStringToSignedInt64 "Parse a non-empty C-string of '0' and '1' bytes as a base-2 unsigned integer. Stops at the first non-'0'/'1' byte. Returns 0 if the first byte is non-binary."
label startParsePositiveBinaryCStringToSignedInt64
const zeroPb I64 0
const onePb I64 1
const twoPb I64 2
const zeroChar I64 48
const oneChar I64 49
var pbAccum I64 0
var pbCursor I64 0
label pbLoop
call pbLoad pointer.loadByte
arg pbLoad buffer inputText
arg pbLoad offset pbCursor
run pbLoad
bind pbByte I8 pbLoad
call pbIsZero math.equalI64
arg pbIsZero left pbByte
arg pbIsZero right zeroChar
run pbIsZero
bind pbZ Bool pbIsZero
branchIf pbZ pbBit0
call pbIsOne math.equalI64
arg pbIsOne left pbByte
arg pbIsOne right oneChar
run pbIsOne
bind pbO Bool pbIsOne
branchIf pbO pbBit1
branch pbDone
label pbBit0
call pb0Mul math.multiplyI64
arg pb0Mul left pbAccum
arg pb0Mul right twoPb
run pb0Mul
bind pb0Next I64 pb0Mul
set pbAccum pb0Next
branch pbAdv
label pbBit1
call pb1Mul math.multiplyI64
arg pb1Mul left pbAccum
arg pb1Mul right twoPb
run pb1Mul
bind pb1Shifted I64 pb1Mul
call pb1Add math.addI64
arg pb1Add left pb1Shifted
arg pb1Add right onePb
run pb1Add
bind pb1Next I64 pb1Add
set pbAccum pb1Next
branch pbAdv
label pbAdv
call pbInc math.addI64
arg pbInc left pbCursor
arg pbInc right onePb
run pbInc
bind pbNext I64 pbInc
set pbCursor pbNext
branch pbLoop
label pbDone
returnOk pbAccum


operation parsePositiveOctalCStringToSignedInt64
input parsePositiveOctalCStringToSignedInt64 inputText CNullTerminatedByteString
output parsePositiveOctalCStringToSignedInt64 Result CSignedInt64 Void
effect parsePositiveOctalCStringToSignedInt64 read memory.buffer
memory parsePositiveOctalCStringToSignedInt64 heap no
async parsePositiveOctalCStringToSignedInt64 no
purpose parsePositiveOctalCStringToSignedInt64 "Parse a non-empty C-string of '0'..'7' as a base-8 unsigned integer."
label startParsePositiveOctalCStringToSignedInt64
const zeroOc I64 0
const oneOc I64 1
const eightOc I64 8
const zeroCharOc I64 48
const sevenCharOc I64 55
var ocAccum I64 0
var ocCursor I64 0
label ocLoop
call ocLoad pointer.loadByte
arg ocLoad buffer inputText
arg ocLoad offset ocCursor
run ocLoad
bind ocByte I8 ocLoad
call ocBelow math.lessThanI64
arg ocBelow left ocByte
arg ocBelow right zeroCharOc
run ocBelow
bind ocB Bool ocBelow
branchIf ocB ocDone
call ocAbove math.greaterThanI64
arg ocAbove left ocByte
arg ocAbove right sevenCharOc
run ocAbove
bind ocA Bool ocAbove
branchIf ocA ocDone
call ocDigit math.subtractI64
arg ocDigit left ocByte
arg ocDigit right zeroCharOc
run ocDigit
bind ocD I64 ocDigit
call ocShift math.multiplyI64
arg ocShift left ocAccum
arg ocShift right eightOc
run ocShift
bind ocS I64 ocShift
call ocAdd math.addI64
arg ocAdd left ocS
arg ocAdd right ocD
run ocAdd
bind ocNew I64 ocAdd
set ocAccum ocNew
call ocInc math.addI64
arg ocInc left ocCursor
arg ocInc right oneOc
run ocInc
bind ocNext I64 ocInc
set ocCursor ocNext
branch ocLoop
label ocDone
returnOk ocAccum


# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test inttypes ports. Prints OK."
label startMain

# parsePositiveBinaryCStringToSignedInt64("1101") == 13
const binStr CNullTerminatedByteString "1101"
const expected13 CSignedInt64 13
call b1 parsePositiveBinaryCStringToSignedInt64
arg b1 s binStr
run b1
bindOk b1Res CSignedInt64 b1
call b1Chk math.equalI64
arg b1Chk left b1Res
arg b1Chk right expected13
run b1Chk
bind b1Ok Bool b1Chk
branchIf b1Ok b1Lbl
branch testFailed
label b1Lbl

# parsePositiveOctalCStringToSignedInt64("755") == 493
const octStr CNullTerminatedByteString "755"
const expected493 CSignedInt64 493
call o1 parsePositiveOctalCStringToSignedInt64
arg o1 s octStr
run o1
bindOk o1Res CSignedInt64 o1
call o1Chk math.equalI64
arg o1Chk left o1Res
arg o1Chk right expected493
run o1Chk
bind o1Ok Bool o1Chk
branchIf o1Ok o1Lbl
branch testFailed
label o1Lbl

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
