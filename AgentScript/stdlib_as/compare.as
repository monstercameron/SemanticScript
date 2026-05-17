project StdCompareSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: comparison helpers.
#
# Operations:
#   compareInt(a, b)       Returns -1 / 0 / +1 (canonical 3-way).
#   isEqualInt(a, b)       1 if a == b, else 0.
#   isLessInt(a, b)        1 if a < b, else 0.
#   isLessEqualInt(a, b)   1 if a <= b, else 0.
#   isGreaterInt(a, b)     1 if a > b, else 0.
#   isGreaterEqualInt(a, b) 1 if a >= b, else 0.
#   compareFloat(a, b)     Same for CFloat64.
#   isCloseFloat(a, b, eps) 1 if |a-b| <= eps, else 0.
# ============================================================


operation compareInt
input compareInt a CSignedInt64
input compareInt b CSignedInt64
output compareInt Result CSignedInt32 Void
memory compareInt heap no
async compareInt no
purpose compareInt "3-way: -1 if a<b, +1 if a>b, 0 if equal."
label startCompareInt
const negOne CSignedInt32 -1
const posOne CSignedInt32 1
const zero CSignedInt32 0
call lt math.lessThanI64
arg lt left a
arg lt right b
run lt
bind aLess Bool lt
branchIf aLess retLt
call gt math.greaterThanI64
arg gt left a
arg gt right b
run gt
bind aGreater Bool gt
branchIf aGreater retGt
returnOk zero
label retLt
returnOk negOne
label retGt
returnOk posOne


operation isEqualInt
input isEqualInt a CSignedInt64
input isEqualInt b CSignedInt64
output isEqualInt Result CSignedInt32 Void
memory isEqualInt heap no
async isEqualInt no
purpose isEqualInt "1 if a == b, else 0."
label startIsEqualInt
const t CSignedInt32 1
const f CSignedInt32 0
call eq math.equalI64
arg eq left a
arg eq right b
run eq
bind eqB Bool eq
branchIf eqB retT
returnOk f
label retT
returnOk t


operation isLessInt
input isLessInt a CSignedInt64
input isLessInt b CSignedInt64
output isLessInt Result CSignedInt32 Void
memory isLessInt heap no
async isLessInt no
purpose isLessInt "1 if a < b, else 0."
label startIsLessInt
const t CSignedInt32 1
const f CSignedInt32 0
call lt math.lessThanI64
arg lt left a
arg lt right b
run lt
bind ltB Bool lt
branchIf ltB retT
returnOk f
label retT
returnOk t


operation isLessEqualInt
input isLessEqualInt a CSignedInt64
input isLessEqualInt b CSignedInt64
output isLessEqualInt Result CSignedInt32 Void
memory isLessEqualInt heap no
async isLessEqualInt no
purpose isLessEqualInt "1 if a <= b, else 0."
label startIsLessEqualInt
const t CSignedInt32 1
const f CSignedInt32 0
call le math.lessThanOrEqualI64
arg le left a
arg le right b
run le
bind leB Bool le
branchIf leB retT
returnOk f
label retT
returnOk t


operation isGreaterInt
input isGreaterInt a CSignedInt64
input isGreaterInt b CSignedInt64
output isGreaterInt Result CSignedInt32 Void
memory isGreaterInt heap no
async isGreaterInt no
purpose isGreaterInt "1 if a > b, else 0."
label startIsGreaterInt
const t CSignedInt32 1
const f CSignedInt32 0
call gt math.greaterThanI64
arg gt left a
arg gt right b
run gt
bind gtB Bool gt
branchIf gtB retT
returnOk f
label retT
returnOk t


operation isGreaterEqualInt
input isGreaterEqualInt a CSignedInt64
input isGreaterEqualInt b CSignedInt64
output isGreaterEqualInt Result CSignedInt32 Void
memory isGreaterEqualInt heap no
async isGreaterEqualInt no
purpose isGreaterEqualInt "1 if a >= b, else 0."
label startIsGreaterEqualInt
const t CSignedInt32 1
const f CSignedInt32 0
call ge math.greaterThanOrEqualI64
arg ge left a
arg ge right b
run ge
bind geB Bool ge
branchIf geB retT
returnOk f
label retT
returnOk t


operation compareFloat
input compareFloat a CFloat64
input compareFloat b CFloat64
output compareFloat Result CSignedInt32 Void
memory compareFloat heap no
async compareFloat no
purpose compareFloat "3-way for doubles. Does not handle NaN specially (no IEEE NaN support in our F64 surface yet)."
label startCompareFloat
const negOne CSignedInt32 -1
const posOne CSignedInt32 1
const zero CSignedInt32 0
call lt math.lessThanF64
arg lt left a
arg lt right b
run lt
bind aLess Bool lt
branchIf aLess retLt
call gt math.greaterThanF64
arg gt left a
arg gt right b
run gt
bind aGreater Bool gt
branchIf aGreater retGt
returnOk zero
label retLt
returnOk negOne
label retGt
returnOk posOne


operation isCloseFloat
input isCloseFloat a CFloat64
input isCloseFloat b CFloat64
input isCloseFloat epsilon CFloat64
output isCloseFloat Result CSignedInt32 Void
memory isCloseFloat heap no
async isCloseFloat no
purpose isCloseFloat "1 if |a-b| <= epsilon, else 0."
label startIsCloseFloat
const t CSignedInt32 1
const f CSignedInt32 0
const zeroF CFloat64 0.0
const negOneF CFloat64 -1.0
call diff math.subtractF64
arg diff left a
arg diff right b
run diff
bind dRaw CFloat64 diff
var d CFloat64 zeroF
set d dRaw
call lt math.lessThanF64
arg lt left d
arg lt right zeroF
run lt
bind isNeg Bool lt
branchIf isNeg flip
branch checkAbs
label flip
call neg math.multiplyF64
arg neg left d
arg neg right negOneF
run neg
bind dPos CFloat64 neg
set d dPos
branch checkAbs
label checkAbs
call le math.lessThanOrEqualF64
arg le left d
arg le right epsilon
run le
bind ok Bool le
branchIf ok retT
returnOk f
label retT
returnOk t


# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test comparison helpers. Prints OK."
label startMain

const c5 CSignedInt64 5
const c10 CSignedInt64 10
const negOne32 CSignedInt32 -1
const trueChk CSignedInt32 1

# compareInt(5, 10) == -1
call c1 compareInt
arg c1 a c5
arg c1 b c10
run c1
bindOk c1Res CSignedInt32 c1
call c1Check math.equalI64
arg c1Check left c1Res
arg c1Check right negOne32
run c1Check
bind c1Ok Bool c1Check
branchIf c1Ok c1Lbl
branch testFailed
label c1Lbl

# isLessInt(5, 10) == 1
call l1 isLessInt
arg l1 a c5
arg l1 b c10
run l1
bindOk l1Res CSignedInt32 l1
call l1Check math.equalI64
arg l1Check left l1Res
arg l1Check right trueChk
run l1Check
bind l1Ok Bool l1Check
branchIf l1Ok l1Lbl
branch testFailed
label l1Lbl

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
