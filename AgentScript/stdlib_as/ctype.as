project StdCtypeSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <ctype.h>-style classifiers.
#
# Operations: isAsciiDecimalDigitCode, isAsciiLetterCode, isAsciiLetterOrDigitCode, isAsciiWhitespaceCode, isAsciiBlankCode, isAsciiControlCode,
#             isAsciiUppercaseLetterCode, isAsciiLowercaseLetterCode, isAsciiHexDigitCode, isAsciiPrintableCode, isAsciiGraphicalCode, isAsciiPunctuationCode,
#             convertAsciiLetterCodeToUppercase, convertAsciiLetterCodeToLowercase.
# All ASCII-only; no locale. Pure AS — math comparisons only.
# ============================================================

operation isAsciiDecimalDigitCode
input isAsciiDecimalDigitCode characterCode CSignedInt32
output isAsciiDecimalDigitCode Result CSignedInt32 Void
memory isAsciiDecimalDigitCode heap no
memory isAsciiDecimalDigitCode stack max 1KiB
async isAsciiDecimalDigitCode no
purpose isAsciiDecimalDigitCode "ASCII isAsciiDecimalDigitCode: true if c is in 0x30..0x39 inclusive."
label startIsAsciiDecimalDigitCode
const d0 CSignedInt32 48
const d9 CSignedInt32 57
const trueDigit CSignedInt32 1
const falseDigit CSignedInt32 0
call digBelowCall math.lessThanI64
arg digBelowCall left characterCode
arg digBelowCall right d0
run digBelowCall
bind digBelow Bool digBelowCall
branchIf digBelow isdigitFalse
call digAboveCall math.greaterThanI64
arg digAboveCall left characterCode
arg digAboveCall right d9
run digAboveCall
bind digAbove Bool digAboveCall
branchIf digAbove isdigitFalse
returnOk trueDigit
label isdigitFalse
returnOk falseDigit


operation isAsciiLowercaseLetterCode
input isAsciiLowercaseLetterCode characterCode CSignedInt32
output isAsciiLowercaseLetterCode Result CSignedInt32 Void
memory isAsciiLowercaseLetterCode heap no
memory isAsciiLowercaseLetterCode stack max 1KiB
async isAsciiLowercaseLetterCode no
purpose isAsciiLowercaseLetterCode "ASCII isAsciiLowercaseLetterCode: 0x61..0x7A."
label startIsAsciiLowercaseLetterCode
const la CSignedInt32 97
const lz CSignedInt32 122
const trueLower CSignedInt32 1
const falseLower CSignedInt32 0
call lwBelowCall math.lessThanI64
arg lwBelowCall left characterCode
arg lwBelowCall right la
run lwBelowCall
bind lwBelow Bool lwBelowCall
branchIf lwBelow islowerFalse
call lwAboveCall math.greaterThanI64
arg lwAboveCall left characterCode
arg lwAboveCall right lz
run lwAboveCall
bind lwAbove Bool lwAboveCall
branchIf lwAbove islowerFalse
returnOk trueLower
label islowerFalse
returnOk falseLower


operation isAsciiUppercaseLetterCode
input isAsciiUppercaseLetterCode characterCode CSignedInt32
output isAsciiUppercaseLetterCode Result CSignedInt32 Void
memory isAsciiUppercaseLetterCode heap no
memory isAsciiUppercaseLetterCode stack max 1KiB
async isAsciiUppercaseLetterCode no
purpose isAsciiUppercaseLetterCode "ASCII isAsciiUppercaseLetterCode: 0x41..0x5A."
label startIsAsciiUppercaseLetterCode
const uA CSignedInt32 65
const uZ CSignedInt32 90
const trueUpper CSignedInt32 1
const falseUpper CSignedInt32 0
call upBelowCall math.lessThanI64
arg upBelowCall left characterCode
arg upBelowCall right uA
run upBelowCall
bind upBelow Bool upBelowCall
branchIf upBelow isupperFalse
call upAboveCall math.greaterThanI64
arg upAboveCall left characterCode
arg upAboveCall right uZ
run upAboveCall
bind upAbove Bool upAboveCall
branchIf upAbove isupperFalse
returnOk trueUpper
label isupperFalse
returnOk falseUpper


operation isAsciiLetterCode
input isAsciiLetterCode characterCode CSignedInt32
output isAsciiLetterCode Result CSignedInt32 Void
memory isAsciiLetterCode heap no
memory isAsciiLetterCode stack max 1KiB
async isAsciiLetterCode no
purpose isAsciiLetterCode "ASCII isAsciiLetterCode: returns 1 if c is A..Z or a..z."
label startIsAsciiLetterCode
const oneCSI CSignedInt32 1
call alphaUpCall isAsciiUppercaseLetterCode
arg alphaUpCall c characterCode
run alphaUpCall
bindOk alphaUpRes CSignedInt32 alphaUpCall
call alphaUpEqCall math.equalI64
arg alphaUpEqCall left alphaUpRes
arg alphaUpEqCall right oneCSI
run alphaUpEqCall
bind alphaIsUp Bool alphaUpEqCall
branchIf alphaIsUp isalphaTrue
call alphaLwCall isAsciiLowercaseLetterCode
arg alphaLwCall c characterCode
run alphaLwCall
bindOk alphaLwRes CSignedInt32 alphaLwCall
call alphaLwEqCall math.equalI64
arg alphaLwEqCall left alphaLwRes
arg alphaLwEqCall right oneCSI
run alphaLwEqCall
bind alphaIsLw Bool alphaLwEqCall
branchIf alphaIsLw isalphaTrue
const falseAlpha CSignedInt32 0
returnOk falseAlpha
label isalphaTrue
const trueAlpha CSignedInt32 1
returnOk trueAlpha


operation isAsciiLetterOrDigitCode
input isAsciiLetterOrDigitCode characterCode CSignedInt32
output isAsciiLetterOrDigitCode Result CSignedInt32 Void
memory isAsciiLetterOrDigitCode heap no
memory isAsciiLetterOrDigitCode stack max 1KiB
async isAsciiLetterOrDigitCode no
purpose isAsciiLetterOrDigitCode "ASCII isAsciiLetterOrDigitCode = isAsciiLetterCode OR isAsciiDecimalDigitCode."
label startIsAsciiLetterOrDigitCode
const oneAlnum CSignedInt32 1
call alnumAlphaCall isAsciiLetterCode
arg alnumAlphaCall c characterCode
run alnumAlphaCall
bindOk alnumAlphaRes CSignedInt32 alnumAlphaCall
call alnumAlphaEqCall math.equalI64
arg alnumAlphaEqCall left alnumAlphaRes
arg alnumAlphaEqCall right oneAlnum
run alnumAlphaEqCall
bind alnumIsAlpha Bool alnumAlphaEqCall
branchIf alnumIsAlpha isalnumTrue
call alnumDigCall isAsciiDecimalDigitCode
arg alnumDigCall c characterCode
run alnumDigCall
bindOk alnumDigRes CSignedInt32 alnumDigCall
call alnumDigEqCall math.equalI64
arg alnumDigEqCall left alnumDigRes
arg alnumDigEqCall right oneAlnum
run alnumDigEqCall
bind alnumIsDig Bool alnumDigEqCall
branchIf alnumIsDig isalnumTrue
const falseAlnum CSignedInt32 0
returnOk falseAlnum
label isalnumTrue
returnOk oneAlnum


operation isAsciiHexDigitCode
input isAsciiHexDigitCode characterCode CSignedInt32
output isAsciiHexDigitCode Result CSignedInt32 Void
memory isAsciiHexDigitCode heap no
memory isAsciiHexDigitCode stack max 1KiB
async isAsciiHexDigitCode no
purpose isAsciiHexDigitCode "ASCII isAsciiHexDigitCode: true if c is a hexadecimal digit (0-9, A-F, a-f)."
label startIsAsciiHexDigitCode
const oneHex CSignedInt32 1
const falseHex CSignedInt32 0
call xdDigCall isAsciiDecimalDigitCode
arg xdDigCall c characterCode
run xdDigCall
bindOk xdDigRes CSignedInt32 xdDigCall
call xdDigEqCall math.equalI64
arg xdDigEqCall left xdDigRes
arg xdDigEqCall right oneHex
run xdDigEqCall
bind xdIsDigit Bool xdDigEqCall
branchIf xdIsDigit isxdigitTrue
const uAhex CSignedInt32 65
const uFhex CSignedInt32 70
call xdUpBelowCall math.lessThanI64
arg xdUpBelowCall left characterCode
arg xdUpBelowCall right uAhex
run xdUpBelowCall
bind xdUpBelow Bool xdUpBelowCall
branchIf xdUpBelow checkLowerHex
call xdUpAboveCall math.greaterThanI64
arg xdUpAboveCall left characterCode
arg xdUpAboveCall right uFhex
run xdUpAboveCall
bind xdUpAbove Bool xdUpAboveCall
branchIf xdUpAbove checkLowerHex
branch isxdigitTrue
label checkLowerHex
const laHex CSignedInt32 97
const lfHex CSignedInt32 102
call xdLwBelowCall math.lessThanI64
arg xdLwBelowCall left characterCode
arg xdLwBelowCall right laHex
run xdLwBelowCall
bind xdLwBelow Bool xdLwBelowCall
branchIf xdLwBelow isxdigitFalse
call xdLwAboveCall math.greaterThanI64
arg xdLwAboveCall left characterCode
arg xdLwAboveCall right lfHex
run xdLwAboveCall
bind xdLwAbove Bool xdLwAboveCall
branchIf xdLwAbove isxdigitFalse
branch isxdigitTrue
label isxdigitFalse
returnOk falseHex
label isxdigitTrue
returnOk oneHex


operation isAsciiWhitespaceCode
input isAsciiWhitespaceCode characterCode CSignedInt32
output isAsciiWhitespaceCode Result CSignedInt32 Void
memory isAsciiWhitespaceCode heap no
memory isAsciiWhitespaceCode stack max 1KiB
async isAsciiWhitespaceCode no
purpose isAsciiWhitespaceCode "ASCII isAsciiWhitespaceCode: true for space, tab, LF, VT, FF, CR."
label startIsAsciiWhitespaceCode
const sSpace CSignedInt32 32
const sTab CSignedInt32 9
const sLf CSignedInt32 10
const sVt CSignedInt32 11
const sFf CSignedInt32 12
const sCr CSignedInt32 13
const trueSpace CSignedInt32 1
const falseSpace CSignedInt32 0
call sEqSpaceCall math.equalI64
arg sEqSpaceCall left characterCode
arg sEqSpaceCall right sSpace
run sEqSpaceCall
bind sIsSpaceB Bool sEqSpaceCall
branchIf sIsSpaceB isspaceTrue
call sEqTabCall math.equalI64
arg sEqTabCall left characterCode
arg sEqTabCall right sTab
run sEqTabCall
bind sIsTabB Bool sEqTabCall
branchIf sIsTabB isspaceTrue
call sEqLfCall math.equalI64
arg sEqLfCall left characterCode
arg sEqLfCall right sLf
run sEqLfCall
bind sIsLfB Bool sEqLfCall
branchIf sIsLfB isspaceTrue
call sEqVtCall math.equalI64
arg sEqVtCall left characterCode
arg sEqVtCall right sVt
run sEqVtCall
bind sIsVtB Bool sEqVtCall
branchIf sIsVtB isspaceTrue
call sEqFfCall math.equalI64
arg sEqFfCall left characterCode
arg sEqFfCall right sFf
run sEqFfCall
bind sIsFfB Bool sEqFfCall
branchIf sIsFfB isspaceTrue
call sEqCrCall math.equalI64
arg sEqCrCall left characterCode
arg sEqCrCall right sCr
run sEqCrCall
bind sIsCrB Bool sEqCrCall
branchIf sIsCrB isspaceTrue
returnOk falseSpace
label isspaceTrue
returnOk trueSpace


operation isAsciiBlankCode
input isAsciiBlankCode characterCode CSignedInt32
output isAsciiBlankCode Result CSignedInt32 Void
memory isAsciiBlankCode heap no
memory isAsciiBlankCode stack max 1KiB
async isAsciiBlankCode no
purpose isAsciiBlankCode "ASCII isAsciiBlankCode: true only for space or horizontal tab."
label startIsAsciiBlankCode
const blSpace CSignedInt32 32
const blTab CSignedInt32 9
const trueBlank CSignedInt32 1
const falseBlank CSignedInt32 0
call blSpCall math.equalI64
arg blSpCall left characterCode
arg blSpCall right blSpace
run blSpCall
bind blIsSp Bool blSpCall
branchIf blIsSp isblankTrue
call blTbCall math.equalI64
arg blTbCall left characterCode
arg blTbCall right blTab
run blTbCall
bind blIsTb Bool blTbCall
branchIf blIsTb isblankTrue
returnOk falseBlank
label isblankTrue
returnOk trueBlank


operation isAsciiControlCode
input isAsciiControlCode characterCode CSignedInt32
output isAsciiControlCode Result CSignedInt32 Void
memory isAsciiControlCode heap no
memory isAsciiControlCode stack max 1KiB
async isAsciiControlCode no
purpose isAsciiControlCode "ASCII isAsciiControlCode: 0x00..0x1F or 0x7F."
label startIsAsciiControlCode
const cntrlMax CSignedInt32 31
const cntrlDel CSignedInt32 127
const trueCntrl CSignedInt32 1
const falseCntrl CSignedInt32 0
call cnLeCall math.lessThanOrEqualI64
arg cnLeCall left characterCode
arg cnLeCall right cntrlMax
run cnLeCall
bind cnIsLow Bool cnLeCall
branchIf cnIsLow iscntrlTrue
call cnEqCall math.equalI64
arg cnEqCall left characterCode
arg cnEqCall right cntrlDel
run cnEqCall
bind cnIsDel Bool cnEqCall
branchIf cnIsDel iscntrlTrue
returnOk falseCntrl
label iscntrlTrue
returnOk trueCntrl


operation isAsciiPrintableCode
input isAsciiPrintableCode characterCode CSignedInt32
output isAsciiPrintableCode Result CSignedInt32 Void
memory isAsciiPrintableCode heap no
memory isAsciiPrintableCode stack max 1KiB
async isAsciiPrintableCode no
purpose isAsciiPrintableCode "ASCII isAsciiPrintableCode: 0x20..0x7E."
label startIsAsciiPrintableCode
const prMin CSignedInt32 32
const prMax CSignedInt32 126
const truePr CSignedInt32 1
const falsePr CSignedInt32 0
call prBelowCall math.lessThanI64
arg prBelowCall left characterCode
arg prBelowCall right prMin
run prBelowCall
bind prBelow Bool prBelowCall
branchIf prBelow isprintFalse
call prAboveCall math.greaterThanI64
arg prAboveCall left characterCode
arg prAboveCall right prMax
run prAboveCall
bind prAbove Bool prAboveCall
branchIf prAbove isprintFalse
returnOk truePr
label isprintFalse
returnOk falsePr


operation isAsciiGraphicalCode
input isAsciiGraphicalCode characterCode CSignedInt32
output isAsciiGraphicalCode Result CSignedInt32 Void
memory isAsciiGraphicalCode heap no
memory isAsciiGraphicalCode stack max 1KiB
async isAsciiGraphicalCode no
purpose isAsciiGraphicalCode "ASCII isAsciiGraphicalCode: 0x21..0x7E (printable minus space)."
label startIsAsciiGraphicalCode
const grMin CSignedInt32 33
const grMax CSignedInt32 126
const trueGr CSignedInt32 1
const falseGr CSignedInt32 0
call grBelowCall math.lessThanI64
arg grBelowCall left characterCode
arg grBelowCall right grMin
run grBelowCall
bind grBelow Bool grBelowCall
branchIf grBelow isgraphFalse
call grAboveCall math.greaterThanI64
arg grAboveCall left characterCode
arg grAboveCall right grMax
run grAboveCall
bind grAbove Bool grAboveCall
branchIf grAbove isgraphFalse
returnOk trueGr
label isgraphFalse
returnOk falseGr


operation isAsciiPunctuationCode
input isAsciiPunctuationCode characterCode CSignedInt32
output isAsciiPunctuationCode Result CSignedInt32 Void
memory isAsciiPunctuationCode heap no
memory isAsciiPunctuationCode stack max 1KiB
async isAsciiPunctuationCode no
purpose isAsciiPunctuationCode "ASCII isAsciiPunctuationCode: printable, non-space, non-alphanumeric."
label startIsAsciiPunctuationCode
const onePunct CSignedInt32 1
const zeroPunct CSignedInt32 0
call puGrCall isAsciiGraphicalCode
arg puGrCall c characterCode
run puGrCall
bindOk puGrRes CSignedInt32 puGrCall
call puGrEqCall math.equalI64
arg puGrEqCall left puGrRes
arg puGrEqCall right onePunct
run puGrEqCall
bind puIsGr Bool puGrEqCall
branchIf puIsGr puCheckAlnum
returnOk zeroPunct
label puCheckAlnum
call puAlnumCall isAsciiLetterOrDigitCode
arg puAlnumCall c characterCode
run puAlnumCall
bindOk puAlnumRes CSignedInt32 puAlnumCall
call puAlnumEqCall math.equalI64
arg puAlnumEqCall left puAlnumRes
arg puAlnumEqCall right onePunct
run puAlnumEqCall
bind puIsAlnum Bool puAlnumEqCall
branchIf puIsAlnum ispunctFalse
returnOk onePunct
label ispunctFalse
returnOk zeroPunct


operation convertAsciiLetterCodeToUppercase
input convertAsciiLetterCodeToUppercase characterCode CSignedInt32
output convertAsciiLetterCodeToUppercase Result CSignedInt32 Void
memory convertAsciiLetterCodeToUppercase heap no
memory convertAsciiLetterCodeToUppercase stack max 1KiB
async convertAsciiLetterCodeToUppercase no
purpose convertAsciiLetterCodeToUppercase "Maps 0x61..0x7A down by 32; passes through everything else."
label startConvertAsciiLetterCodeToUppercase
const lAtu CSignedInt32 97
const lZtu CSignedInt32 122
const gapTu CSignedInt32 32
call tuBelowCall math.lessThanI64
arg tuBelowCall left characterCode
arg tuBelowCall right lAtu
run tuBelowCall
bind tuBelow Bool tuBelowCall
branchIf tuBelow toupperPass
call tuAboveCall math.greaterThanI64
arg tuAboveCall left characterCode
arg tuAboveCall right lZtu
run tuAboveCall
bind tuAbove Bool tuAboveCall
branchIf tuAbove toupperPass
call tuShiftCall math.subtractI64
arg tuShiftCall left characterCode
arg tuShiftCall right gapTu
run tuShiftCall
bind tuShifted CSignedInt32 tuShiftCall
returnOk tuShifted
label toupperPass
returnOk characterCode


operation convertAsciiLetterCodeToLowercase
input convertAsciiLetterCodeToLowercase characterCode CSignedInt32
output convertAsciiLetterCodeToLowercase Result CSignedInt32 Void
memory convertAsciiLetterCodeToLowercase heap no
memory convertAsciiLetterCodeToLowercase stack max 1KiB
async convertAsciiLetterCodeToLowercase no
purpose convertAsciiLetterCodeToLowercase "Maps 0x41..0x5A up by 32; passes through everything else."
label startConvertAsciiLetterCodeToLowercase
const uAtl CSignedInt32 65
const uZtl CSignedInt32 90
const gapTl CSignedInt32 32
call tlBelowCall math.lessThanI64
arg tlBelowCall left characterCode
arg tlBelowCall right uAtl
run tlBelowCall
bind tlBelow Bool tlBelowCall
branchIf tlBelow tolowerPass
call tlAboveCall math.greaterThanI64
arg tlAboveCall left characterCode
arg tlAboveCall right uZtl
run tlAboveCall
bind tlAbove Bool tlAboveCall
branchIf tlAbove tolowerPass
call tlShiftCall math.addI64
arg tlShiftCall left characterCode
arg tlShiftCall right gapTl
run tlShiftCall
bind tlShifted CSignedInt32 tlShiftCall
returnOk tlShifted
label tolowerPass
returnOk characterCode


# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test every ctype classifier and case mapper. Prints OK."
label startMain

const oneI32t CSignedInt32 1
const zeroI32t CSignedInt32 0
const digit5 CSignedInt32 53
const lowerH CSignedInt32 104
const upperH CSignedInt32 72
const exclMark CSignedInt32 33
const hexF CSignedInt32 70
const spaceC CSignedInt32 32
const tabC CSignedInt32 9
const lfC CSignedInt32 10
const nullC CSignedInt32 0

call t1 isAsciiDecimalDigitCode
arg t1 c digit5
run t1
bindOk t1Res CSignedInt32 t1
call t1Check math.equalI64
arg t1Check left t1Res
arg t1Check right oneI32t
run t1Check
bind t1Ok Bool t1Check
branchIf t1Ok t1OkLabel
branch testFailed
label t1OkLabel

call t2 isAsciiLetterCode
arg t2 c lowerH
run t2
bindOk t2Res CSignedInt32 t2
call t2Check math.equalI64
arg t2Check left t2Res
arg t2Check right oneI32t
run t2Check
bind t2Ok Bool t2Check
branchIf t2Ok t2OkLabel
branch testFailed
label t2OkLabel

call t3 isAsciiLetterOrDigitCode
arg t3 c digit5
run t3
bindOk t3Res CSignedInt32 t3
call t3Check math.equalI64
arg t3Check left t3Res
arg t3Check right oneI32t
run t3Check
bind t3Ok Bool t3Check
branchIf t3Ok t3OkLabel
branch testFailed
label t3OkLabel

call t4 isAsciiLetterOrDigitCode
arg t4 c exclMark
run t4
bindOk t4Res CSignedInt32 t4
call t4Check math.equalI64
arg t4Check left t4Res
arg t4Check right zeroI32t
run t4Check
bind t4Ok Bool t4Check
branchIf t4Ok t4OkLabel
branch testFailed
label t4OkLabel

call t5 isAsciiHexDigitCode
arg t5 c hexF
run t5
bindOk t5Res CSignedInt32 t5
call t5Check math.equalI64
arg t5Check left t5Res
arg t5Check right oneI32t
run t5Check
bind t5Ok Bool t5Check
branchIf t5Ok t5OkLabel
branch testFailed
label t5OkLabel

call t6 isAsciiWhitespaceCode
arg t6 c spaceC
run t6
bindOk t6Res CSignedInt32 t6
call t6Check math.equalI64
arg t6Check left t6Res
arg t6Check right oneI32t
run t6Check
bind t6Ok Bool t6Check
branchIf t6Ok t6OkLabel
branch testFailed
label t6OkLabel

call t7 isAsciiBlankCode
arg t7 c tabC
run t7
bindOk t7Res CSignedInt32 t7
call t7Check math.equalI64
arg t7Check left t7Res
arg t7Check right oneI32t
run t7Check
bind t7Ok Bool t7Check
branchIf t7Ok t7OkLabel
branch testFailed
label t7OkLabel

call t8 isAsciiBlankCode
arg t8 c lfC
run t8
bindOk t8Res CSignedInt32 t8
call t8Check math.equalI64
arg t8Check left t8Res
arg t8Check right zeroI32t
run t8Check
bind t8Ok Bool t8Check
branchIf t8Ok t8OkLabel
branch testFailed
label t8OkLabel

call t9 isAsciiControlCode
arg t9 c nullC
run t9
bindOk t9Res CSignedInt32 t9
call t9Check math.equalI64
arg t9Check left t9Res
arg t9Check right oneI32t
run t9Check
bind t9Ok Bool t9Check
branchIf t9Ok t9OkLabel
branch testFailed
label t9OkLabel

call t10 isAsciiPrintableCode
arg t10 c spaceC
run t10
bindOk t10Res CSignedInt32 t10
call t10Check math.equalI64
arg t10Check left t10Res
arg t10Check right oneI32t
run t10Check
bind t10Ok Bool t10Check
branchIf t10Ok t10OkLabel
branch testFailed
label t10OkLabel

call t11 isAsciiGraphicalCode
arg t11 c spaceC
run t11
bindOk t11Res CSignedInt32 t11
call t11Check math.equalI64
arg t11Check left t11Res
arg t11Check right zeroI32t
run t11Check
bind t11Ok Bool t11Check
branchIf t11Ok t11OkLabel
branch testFailed
label t11OkLabel

call t12 isAsciiPunctuationCode
arg t12 c exclMark
run t12
bindOk t12Res CSignedInt32 t12
call t12Check math.equalI64
arg t12Check left t12Res
arg t12Check right oneI32t
run t12Check
bind t12Ok Bool t12Check
branchIf t12Ok t12OkLabel
branch testFailed
label t12OkLabel

call t13 convertAsciiLetterCodeToUppercase
arg t13 c lowerH
run t13
bindOk t13Res CSignedInt32 t13
call t13Check math.equalI64
arg t13Check left t13Res
arg t13Check right upperH
run t13Check
bind t13Ok Bool t13Check
branchIf t13Ok t13OkLabel
branch testFailed
label t13OkLabel

call t14 convertAsciiLetterCodeToLowercase
arg t14 c upperH
run t14
bindOk t14Res CSignedInt32 t14
call t14Check math.equalI64
arg t14Check left t14Res
arg t14Check right lowerH
run t14Check
bind t14Ok Bool t14Check
branchIf t14Ok t14OkLabel
branch testFailed
label t14OkLabel

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
