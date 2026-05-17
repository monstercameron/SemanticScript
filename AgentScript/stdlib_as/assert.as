project StdAssertSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError AssertionFailed CSignedInt32
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <assert.h>-style runtime checks.
#
# Operations:
#   requireConditionTrue(condition)         - if condition == 0, abort with code 1
#                                    (and a message to stdout). Returns 0
#                                    when the assertion holds.
#   requireSignedInt64ValuesEqual(a, b)             - requireConditionTrue(a == b)
#   requireSignedInt64ValuesNotEqual(a, b)          - requireConditionTrue(a != b)
#
# Pure AS atop writeAssertionByteToStandardOutput for the failure-message bytes.
# ============================================================

operation writeAssertionByteToStandardOutput
input writeAssertionByteToStandardOutput characterCode CSignedInt32
output writeAssertionByteToStandardOutput Result CSignedInt32 Void
effect writeAssertionByteToStandardOutput write console.stdout
memory writeAssertionByteToStandardOutput heap no
memory writeAssertionByteToStandardOutput stack max 1KiB
async writeAssertionByteToStandardOutput no
purpose writeAssertionByteToStandardOutput "Single-byte writer used by assertion failure printing. Wraps the floor primitive c.putchar."
label startWriteAssertionByteToStandardOutput
call libcCall c.putchar
arg libcCall c characterCode
run libcCall
bind result CSignedInt32 libcCall
returnOk result


operation requireConditionTrue
input requireConditionTrue conditionValue CSignedInt64
output requireConditionTrue Result CSignedInt32 CSignedInt32
memory requireConditionTrue heap no
memory requireConditionTrue stack max 1KiB
async requireConditionTrue no
purpose requireConditionTrue "Abort the program (returning error code 1) when condition is zero. Returns 0 on success."

label startRequireConditionTrue
const zeroAt I64 0
const okAt CSignedInt32 0
const failCode CSignedInt32 1

call checkCall math.equalI64
arg checkCall left conditionValue
arg checkCall right zeroAt
run checkCall
bind isFalse Bool checkCall
branchIf isFalse assertFail
returnOk okAt

label assertFail
# Print "assert!\n" via writeAssertionByteToStandardOutput.
const charAU CSignedInt32 97
const charSU CSignedInt32 115
const charSU2 CSignedInt32 115
const charEU CSignedInt32 101
const charRU CSignedInt32 114
const charTU CSignedInt32 116
const charBang CSignedInt32 33
const charNlA CSignedInt32 10
call pAa writeAssertionByteToStandardOutput
arg pAa c charAU
run pAa
ignoreOk pAa CSignedInt32
call pAs writeAssertionByteToStandardOutput
arg pAs c charSU
run pAs
ignoreOk pAs CSignedInt32
call pAs2 writeAssertionByteToStandardOutput
arg pAs2 c charSU2
run pAs2
ignoreOk pAs2 CSignedInt32
call pAe writeAssertionByteToStandardOutput
arg pAe c charEU
run pAe
ignoreOk pAe CSignedInt32
call pAr writeAssertionByteToStandardOutput
arg pAr c charRU
run pAr
ignoreOk pAr CSignedInt32
call pAt writeAssertionByteToStandardOutput
arg pAt c charTU
run pAt
ignoreOk pAt CSignedInt32
call pAb writeAssertionByteToStandardOutput
arg pAb c charBang
run pAb
ignoreOk pAb CSignedInt32
call pAnl writeAssertionByteToStandardOutput
arg pAnl c charNlA
run pAnl
ignoreOk pAnl CSignedInt32
returnError failCode


operation requireSignedInt64ValuesEqual
input requireSignedInt64ValuesEqual leftValue CSignedInt64
input requireSignedInt64ValuesEqual rightValue CSignedInt64
output requireSignedInt64ValuesEqual Result CSignedInt32 CSignedInt32
memory requireSignedInt64ValuesEqual heap no
memory requireSignedInt64ValuesEqual stack max 1KiB
async requireSignedInt64ValuesEqual no
purpose requireSignedInt64ValuesEqual "Assert a == b. Delegates to requireConditionTrue."
label startRequireSignedInt64ValuesEqual
call eqCall math.equalI64
arg eqCall left leftValue
arg eqCall right rightValue
run eqCall
bind eqB Bool eqCall
var asInt I64 0
branchIf eqB aeMakeTrue
branch aeMakeFalse
label aeMakeTrue
const oneAe I64 1
set asInt oneAe
branch aeCall
label aeMakeFalse
const zeroAe I64 0
set asInt zeroAe
branch aeCall
label aeCall
call asCall requireConditionTrue
arg asCall condition asInt
run asCall
bindOk asOkRes CSignedInt32 asCall
bindError asErrRes CSignedInt32 asCall
branchIfError asCall aePropagateErr
const okAe CSignedInt32 0
returnOk okAe
label aePropagateErr
returnError asErrRes


operation requireSignedInt64ValuesNotEqual
input requireSignedInt64ValuesNotEqual leftValue CSignedInt64
input requireSignedInt64ValuesNotEqual rightValue CSignedInt64
output requireSignedInt64ValuesNotEqual Result CSignedInt32 CSignedInt32
memory requireSignedInt64ValuesNotEqual heap no
memory requireSignedInt64ValuesNotEqual stack max 1KiB
async requireSignedInt64ValuesNotEqual no
purpose requireSignedInt64ValuesNotEqual "Assert a != b."
label startRequireSignedInt64ValuesNotEqual
call neCall math.notEqualI64
arg neCall left leftValue
arg neCall right rightValue
run neCall
bind neB Bool neCall
var asInt2 I64 0
branchIf neB anMakeTrue
branch anMakeFalse
label anMakeTrue
const oneAn I64 1
set asInt2 oneAn
branch anCall
label anMakeFalse
const zeroAn I64 0
set asInt2 zeroAn
branch anCall
label anCall
call asCall2 requireConditionTrue
arg asCall2 condition asInt2
run asCall2
bindOk asOk2 CSignedInt32 asCall2
bindError asErr2 CSignedInt32 asCall2
branchIfError asCall2 anPropagateErr
const okAn CSignedInt32 0
returnOk okAn
label anPropagateErr
returnError asErr2


operation requireSignedInt64LeftGreaterThanRight
input requireSignedInt64LeftGreaterThanRight leftValue CSignedInt64
input requireSignedInt64LeftGreaterThanRight rightValue CSignedInt64
output requireSignedInt64LeftGreaterThanRight Result CSignedInt32 CSignedInt32
memory requireSignedInt64LeftGreaterThanRight heap no
async requireSignedInt64LeftGreaterThanRight no
purpose requireSignedInt64LeftGreaterThanRight "Assert a > b. Returns 0 on success; error code 1 (via requireConditionTrue) on failure."
label startRequireSignedInt64LeftGreaterThanRight
call cmp math.greaterThanI64
arg cmp left leftValue
arg cmp right rightValue
run cmp
bind r Bool cmp
var asInt I64 0
branchIf r agtMakeTrue
branch agtMakeFalse
label agtMakeTrue
const one I64 1
set asInt one
branch agtCall
label agtMakeFalse
const zero I64 0
set asInt zero
branch agtCall
label agtCall
call asCall requireConditionTrue
arg asCall condition asInt
run asCall
bindOk asOkRes CSignedInt32 asCall
bindError asErrRes CSignedInt32 asCall
branchIfError asCall agtPropErr
const okAgt CSignedInt32 0
returnOk okAgt
label agtPropErr
returnError asErrRes


operation requireSignedInt64LeftLessThanRight
input requireSignedInt64LeftLessThanRight leftValue CSignedInt64
input requireSignedInt64LeftLessThanRight rightValue CSignedInt64
output requireSignedInt64LeftLessThanRight Result CSignedInt32 CSignedInt32
memory requireSignedInt64LeftLessThanRight heap no
async requireSignedInt64LeftLessThanRight no
purpose requireSignedInt64LeftLessThanRight "Assert a < b."
label startRequireSignedInt64LeftLessThanRight
call cmp math.lessThanI64
arg cmp left leftValue
arg cmp right rightValue
run cmp
bind r Bool cmp
var asInt I64 0
branchIf r altMakeTrue
branch altMakeFalse
label altMakeTrue
const one I64 1
set asInt one
branch altCall
label altMakeFalse
const zero I64 0
set asInt zero
branch altCall
label altCall
call asCall requireConditionTrue
arg asCall condition asInt
run asCall
bindOk asOkRes CSignedInt32 asCall
bindError asErrRes CSignedInt32 asCall
branchIfError asCall altPropErr
const okAlt CSignedInt32 0
returnOk okAlt
label altPropErr
returnError asErrRes


operation requireSignedInt64ValueWithinInclusiveRange
input requireSignedInt64ValueWithinInclusiveRange inputValue CSignedInt64
input requireSignedInt64ValueWithinInclusiveRange lowerBound CSignedInt64
input requireSignedInt64ValueWithinInclusiveRange upperBound CSignedInt64
output requireSignedInt64ValueWithinInclusiveRange Result CSignedInt32 CSignedInt32
memory requireSignedInt64ValueWithinInclusiveRange heap no
async requireSignedInt64ValueWithinInclusiveRange no
purpose requireSignedInt64ValueWithinInclusiveRange "Assert lo <= x <= hi."
label startRequireSignedInt64ValueWithinInclusiveRange
call belowLo math.lessThanI64
arg belowLo left inputValue
arg belowLo right lowerBound
run belowLo
bind below Bool belowLo
branchIf below airFalseBranch
call aboveHi math.greaterThanI64
arg aboveHi left inputValue
arg aboveHi right upperBound
run aboveHi
bind above Bool aboveHi
branchIf above airFalseBranch
var asInt I64 1
branch airCall
label airFalseBranch
var asInt2 I64 0
branch airCallFalse
label airCall
call asCall requireConditionTrue
arg asCall condition asInt
run asCall
bindOk asOkRes CSignedInt32 asCall
bindError asErrRes CSignedInt32 asCall
branchIfError asCall airPropErr
const okAir CSignedInt32 0
returnOk okAir
label airCallFalse
call asCall2 requireConditionTrue
arg asCall2 condition asInt2
run asCall2
bindOk asOkRes2 CSignedInt32 asCall2
bindError asErrRes2 CSignedInt32 asCall2
returnError asErrRes2
label airPropErr
returnError asErrRes


operation requireOpaquePointerNotNull
input requireOpaquePointerNotNull pointerValue COpaqueMemoryAddress
output requireOpaquePointerNotNull Result CSignedInt32 CSignedInt32
memory requireOpaquePointerNotNull heap no
async requireOpaquePointerNotNull no
purpose requireOpaquePointerNotNull "Assert that p is not the NULL pointer."
label startRequireOpaquePointerNotNull
call np pointer.isNull
arg np pointer pointerValue
run np
bind isNull Bool np
var asInt I64 1
branchIf isNull annSetZero
branch annCall
label annSetZero
const zeroAnn I64 0
set asInt zeroAnn
branch annCall
label annCall
call asCall requireConditionTrue
arg asCall condition asInt
run asCall
bindOk asOkRes CSignedInt32 asCall
bindError asErrRes CSignedInt32 asCall
branchIfError asCall annPropErr
const okAnn CSignedInt32 0
returnOk okAnn
label annPropErr
returnError asErrRes


# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test assertion ports."

label startMain

# requireSignedInt64ValuesEqual(2 + 2, 4)
const twoTest CSignedInt64 2
const fourTest CSignedInt64 4
call sumCall math.addI64
arg sumCall left twoTest
arg sumCall right twoTest
run sumCall
bind sumRes I64 sumCall
call a1 requireSignedInt64ValuesEqual
arg a1 a sumRes
arg a1 b fourTest
run a1
bindOk a1Ok CSignedInt32 a1
bindError a1Err CSignedInt32 a1
branchIfError a1 testFailed

# requireSignedInt64ValuesNotEqual(1, 2)
const oneT CSignedInt64 1
const twoT CSignedInt64 2
call a2 requireSignedInt64ValuesNotEqual
arg a2 a oneT
arg a2 b twoT
run a2
bindOk a2Ok CSignedInt32 a2
bindError a2Err CSignedInt32 a2
branchIfError a2 testFailed

const charO CSignedInt32 79
const charK CSignedInt32 75
const charNl CSignedInt32 10
call putOmain c.putchar
arg putOmain c charO
run putOmain
call putKmain c.putchar
arg putKmain c charK
run putKmain
call putNlmain c.putchar
arg putNlmain c charNl
run putNlmain

const exitOk ExitCode 0
returnOk exitOk

label testFailed
const exitFail CSignedInt32 1
makeError testFailure MainError.TestFailed exitFail
returnError testFailure
