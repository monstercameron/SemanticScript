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
#   compareSignedInt64Ordering(a, b)       Returns -1 / 0 / +1 (canonical 3-way).
#   areSignedInt64ValuesEqual(a, b)       1 if a == b, else 0.
#   isSignedInt64LeftLessThanRight(a, b)        1 if a < b, else 0.
#   isSignedInt64LeftLessThanOrEqualRight(a, b)   1 if a <= b, else 0.
#   isSignedInt64LeftGreaterThanRight(a, b)     1 if a > b, else 0.
#   isSignedInt64LeftGreaterThanOrEqualRight(a, b) 1 if a >= b, else 0.
#   compareFloat64Ordering(a, b)     Same for CFloat64.
#   areFloat64ValuesWithinTolerance(a, b, eps) 1 if |a-b| <= eps, else 0.
# ============================================================


operation compareSignedInt64Ordering
input compareSignedInt64Ordering leftValue CSignedInt64
input compareSignedInt64Ordering rightValue CSignedInt64
output compareSignedInt64Ordering Result CSignedInt32 Void
memory compareSignedInt64Ordering heap no
async compareSignedInt64Ordering no
purpose compareSignedInt64Ordering "3-way: -1 if a<b, +1 if a>b, 0 if equal."
label startCompareSignedInt64Ordering
const negOne CSignedInt32 -1
const posOne CSignedInt32 1
const zero CSignedInt32 0
call lt math.lessThanI64
arg lt left leftValue
arg lt right rightValue
run lt
bind aLess Bool lt
branchIf aLess retLt
call gt math.greaterThanI64
arg gt left leftValue
arg gt right rightValue
run gt
bind aGreater Bool gt
branchIf aGreater retGt
returnOk zero
label retLt
returnOk negOne
label retGt
returnOk posOne


operation areSignedInt64ValuesEqual
input areSignedInt64ValuesEqual leftValue CSignedInt64
input areSignedInt64ValuesEqual rightValue CSignedInt64
output areSignedInt64ValuesEqual Result CSignedInt32 Void
memory areSignedInt64ValuesEqual heap no
async areSignedInt64ValuesEqual no
purpose areSignedInt64ValuesEqual "1 if a == b, else 0."
label startAreSignedInt64ValuesEqual
const t CSignedInt32 1
const f CSignedInt32 0
call eq math.equalI64
arg eq left leftValue
arg eq right rightValue
run eq
bind eqB Bool eq
branchIf eqB retT
returnOk f
label retT
returnOk t


operation isSignedInt64LeftLessThanRight
input isSignedInt64LeftLessThanRight leftValue CSignedInt64
input isSignedInt64LeftLessThanRight rightValue CSignedInt64
output isSignedInt64LeftLessThanRight Result CSignedInt32 Void
memory isSignedInt64LeftLessThanRight heap no
async isSignedInt64LeftLessThanRight no
purpose isSignedInt64LeftLessThanRight "1 if a < b, else 0."
label startIsSignedInt64LeftLessThanRight
const t CSignedInt32 1
const f CSignedInt32 0
call lt math.lessThanI64
arg lt left leftValue
arg lt right rightValue
run lt
bind ltB Bool lt
branchIf ltB retT
returnOk f
label retT
returnOk t


operation isSignedInt64LeftLessThanOrEqualRight
input isSignedInt64LeftLessThanOrEqualRight leftValue CSignedInt64
input isSignedInt64LeftLessThanOrEqualRight rightValue CSignedInt64
output isSignedInt64LeftLessThanOrEqualRight Result CSignedInt32 Void
memory isSignedInt64LeftLessThanOrEqualRight heap no
async isSignedInt64LeftLessThanOrEqualRight no
purpose isSignedInt64LeftLessThanOrEqualRight "1 if a <= b, else 0."
label startIsSignedInt64LeftLessThanOrEqualRight
const t CSignedInt32 1
const f CSignedInt32 0
call le math.lessThanOrEqualI64
arg le left leftValue
arg le right rightValue
run le
bind leB Bool le
branchIf leB retT
returnOk f
label retT
returnOk t


operation isSignedInt64LeftGreaterThanRight
input isSignedInt64LeftGreaterThanRight leftValue CSignedInt64
input isSignedInt64LeftGreaterThanRight rightValue CSignedInt64
output isSignedInt64LeftGreaterThanRight Result CSignedInt32 Void
memory isSignedInt64LeftGreaterThanRight heap no
async isSignedInt64LeftGreaterThanRight no
purpose isSignedInt64LeftGreaterThanRight "1 if a > b, else 0."
label startIsSignedInt64LeftGreaterThanRight
const t CSignedInt32 1
const f CSignedInt32 0
call gt math.greaterThanI64
arg gt left leftValue
arg gt right rightValue
run gt
bind gtB Bool gt
branchIf gtB retT
returnOk f
label retT
returnOk t


operation isSignedInt64LeftGreaterThanOrEqualRight
input isSignedInt64LeftGreaterThanOrEqualRight leftValue CSignedInt64
input isSignedInt64LeftGreaterThanOrEqualRight rightValue CSignedInt64
output isSignedInt64LeftGreaterThanOrEqualRight Result CSignedInt32 Void
memory isSignedInt64LeftGreaterThanOrEqualRight heap no
async isSignedInt64LeftGreaterThanOrEqualRight no
purpose isSignedInt64LeftGreaterThanOrEqualRight "1 if a >= b, else 0."
label startIsSignedInt64LeftGreaterThanOrEqualRight
const t CSignedInt32 1
const f CSignedInt32 0
call ge math.greaterThanOrEqualI64
arg ge left leftValue
arg ge right rightValue
run ge
bind geB Bool ge
branchIf geB retT
returnOk f
label retT
returnOk t


operation compareFloat64Ordering
input compareFloat64Ordering leftValue CFloat64
input compareFloat64Ordering rightValue CFloat64
output compareFloat64Ordering Result CSignedInt32 Void
memory compareFloat64Ordering heap no
async compareFloat64Ordering no
purpose compareFloat64Ordering "3-way for doubles. Does not handle NaN specially (no IEEE NaN support in our F64 surface yet)."
label startCompareFloat64Ordering
const negOne CSignedInt32 -1
const posOne CSignedInt32 1
const zero CSignedInt32 0
call lt math.lessThanF64
arg lt left leftValue
arg lt right rightValue
run lt
bind aLess Bool lt
branchIf aLess retLt
call gt math.greaterThanF64
arg gt left leftValue
arg gt right rightValue
run gt
bind aGreater Bool gt
branchIf aGreater retGt
returnOk zero
label retLt
returnOk negOne
label retGt
returnOk posOne


operation areFloat64ValuesWithinTolerance
input areFloat64ValuesWithinTolerance leftValue CFloat64
input areFloat64ValuesWithinTolerance rightValue CFloat64
input areFloat64ValuesWithinTolerance tolerance CFloat64
output areFloat64ValuesWithinTolerance Result CSignedInt32 Void
memory areFloat64ValuesWithinTolerance heap no
async areFloat64ValuesWithinTolerance no
purpose areFloat64ValuesWithinTolerance "1 if |a-b| <= epsilon, else 0."
label startAreFloat64ValuesWithinTolerance
const t CSignedInt32 1
const f CSignedInt32 0
const zeroF CFloat64 0.0
const negOneF CFloat64 -1.0
call diff math.subtractF64
arg diff left leftValue
arg diff right rightValue
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
arg le right tolerance
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

# compareSignedInt64Ordering(5, 10) == -1
call c1 compareSignedInt64Ordering
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

# isSignedInt64LeftLessThanRight(5, 10) == 1
call l1 isSignedInt64LeftLessThanRight
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
