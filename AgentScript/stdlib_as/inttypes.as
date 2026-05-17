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
#   imaxabs(n)             Like libc imaxabs: absolute value of n.
#   imaxdiv(a, b)          Returns quotient (the remainder is dropped
#                          at this layer; AS doesn't support struct
#                          returns from user-operations yet).
#   imaxmodulus(a, b)      Returns remainder.
#   parsePositiveBinary(s) Parse a base-2 string of '0'/'1'.
#   parsePositiveOctal(s)  Parse a base-8 string of '0'..'7'.
# ============================================================


operation imaxabs
input imaxabs n CSignedInt64
output imaxabs Result CSignedInt64 Void
memory imaxabs heap no
async imaxabs no
purpose imaxabs "Absolute value of intmax_t."
label startImaxabs
const zeroI I64 0
const negOneI I64 -1
call ltz math.lessThanI64
arg ltz left n
arg ltz right zeroI
run ltz
bind isN Bool ltz
branchIf isN flip
returnOk n
label flip
call neg math.multiplyI64
arg neg left n
arg neg right negOneI
run neg
bind flipped CSignedInt64 neg
returnOk flipped


operation imaxdiv
input imaxdiv a CSignedInt64
input imaxdiv b CSignedInt64
output imaxdiv Result CSignedInt64 Void
memory imaxdiv heap no
async imaxdiv no
purpose imaxdiv "Integer quotient a/b. Note: real libc imaxdiv returns a struct with both quotient and remainder; AS user-operations can't return tuples yet, so we expose this and imaxmodulus separately."
label startImaxdiv
call divCall math.divideI64
arg divCall left a
arg divCall right b
run divCall
bind q CSignedInt64 divCall
returnOk q


operation imaxmodulus
input imaxmodulus a CSignedInt64
input imaxmodulus b CSignedInt64
output imaxmodulus Result CSignedInt64 Void
memory imaxmodulus heap no
async imaxmodulus no
purpose imaxmodulus "Integer remainder a%b."
label startImaxmodulus
call modCall math.moduloI64
arg modCall left a
arg modCall right b
run modCall
bind r CSignedInt64 modCall
returnOk r


operation parsePositiveBinary
input parsePositiveBinary s CNullTerminatedByteString
output parsePositiveBinary Result CSignedInt64 Void
effect parsePositiveBinary read memory.buffer
memory parsePositiveBinary heap no
async parsePositiveBinary no
purpose parsePositiveBinary "Parse a non-empty C-string of '0' and '1' bytes as a base-2 unsigned integer. Stops at the first non-'0'/'1' byte. Returns 0 if the first byte is non-binary."
label startParsePositiveBinary
const zeroPb I64 0
const onePb I64 1
const twoPb I64 2
const zeroChar I64 48
const oneChar I64 49
var pbAccum I64 0
var pbCursor I64 0
label pbLoop
call pbLoad pointer.loadByte
arg pbLoad buffer s
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


operation parsePositiveOctal
input parsePositiveOctal s CNullTerminatedByteString
output parsePositiveOctal Result CSignedInt64 Void
effect parsePositiveOctal read memory.buffer
memory parsePositiveOctal heap no
async parsePositiveOctal no
purpose parsePositiveOctal "Parse a non-empty C-string of '0'..'7' as a base-8 unsigned integer."
label startParsePositiveOctal
const zeroOc I64 0
const oneOc I64 1
const eightOc I64 8
const zeroCharOc I64 48
const sevenCharOc I64 55
var ocAccum I64 0
var ocCursor I64 0
label ocLoop
call ocLoad pointer.loadByte
arg ocLoad buffer s
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

# parsePositiveBinary("1101") == 13
const binStr CNullTerminatedByteString "1101"
const expected13 CSignedInt64 13
call b1 parsePositiveBinary
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

# parsePositiveOctal("755") == 493
const octStr CNullTerminatedByteString "755"
const expected493 CSignedInt64 493
call o1 parsePositiveOctal
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
