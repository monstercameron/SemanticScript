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
#   assertTrue(condition)         - if condition == 0, abort with code 1
#                                    (and a message to stdout). Returns 0
#                                    when the assertion holds.
#   assertEqual(a, b)             - assertTrue(a == b)
#   assertNotEqual(a, b)          - assertTrue(a != b)
#
# Pure AS atop putByte for the failure-message bytes.
# ============================================================

operation putByte
input putByte c CSignedInt32
output putByte Result CSignedInt32 Void
effect putByte write console.stdout
memory putByte heap no
memory putByte stack max 1KiB
async putByte no
purpose putByte "Single-byte writer used by assertion failure printing. Wraps the floor primitive c.putchar."
label startPutByte
call libcCall c.putchar
arg libcCall c c
run libcCall
bind result CSignedInt32 libcCall
returnOk result


operation assertTrue
input assertTrue condition CSignedInt64
output assertTrue Result CSignedInt32 CSignedInt32
memory assertTrue heap no
memory assertTrue stack max 1KiB
async assertTrue no
purpose assertTrue "Abort the program (returning error code 1) when condition is zero. Returns 0 on success."

label startAssertTrue
const zeroAt I64 0
const okAt CSignedInt32 0
const failCode CSignedInt32 1

call checkCall math.equalI64
arg checkCall left condition
arg checkCall right zeroAt
run checkCall
bind isFalse Bool checkCall
branchIf isFalse assertFail
returnOk okAt

label assertFail
# Print "assert!\n" via putByte.
const charAU CSignedInt32 97
const charSU CSignedInt32 115
const charSU2 CSignedInt32 115
const charEU CSignedInt32 101
const charRU CSignedInt32 114
const charTU CSignedInt32 116
const charBang CSignedInt32 33
const charNlA CSignedInt32 10
call pAa putByte
arg pAa c charAU
run pAa
ignoreOk pAa CSignedInt32
call pAs putByte
arg pAs c charSU
run pAs
ignoreOk pAs CSignedInt32
call pAs2 putByte
arg pAs2 c charSU2
run pAs2
ignoreOk pAs2 CSignedInt32
call pAe putByte
arg pAe c charEU
run pAe
ignoreOk pAe CSignedInt32
call pAr putByte
arg pAr c charRU
run pAr
ignoreOk pAr CSignedInt32
call pAt putByte
arg pAt c charTU
run pAt
ignoreOk pAt CSignedInt32
call pAb putByte
arg pAb c charBang
run pAb
ignoreOk pAb CSignedInt32
call pAnl putByte
arg pAnl c charNlA
run pAnl
ignoreOk pAnl CSignedInt32
returnError failCode


operation assertEqual
input assertEqual a CSignedInt64
input assertEqual b CSignedInt64
output assertEqual Result CSignedInt32 CSignedInt32
memory assertEqual heap no
memory assertEqual stack max 1KiB
async assertEqual no
purpose assertEqual "Assert a == b. Delegates to assertTrue."
label startAssertEqual
call eqCall math.equalI64
arg eqCall left a
arg eqCall right b
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
call asCall assertTrue
arg asCall condition asInt
run asCall
bindOk asOkRes CSignedInt32 asCall
bindError asErrRes CSignedInt32 asCall
branchIfError asCall aePropagateErr
const okAe CSignedInt32 0
returnOk okAe
label aePropagateErr
returnError asErrRes


operation assertNotEqual
input assertNotEqual a CSignedInt64
input assertNotEqual b CSignedInt64
output assertNotEqual Result CSignedInt32 CSignedInt32
memory assertNotEqual heap no
memory assertNotEqual stack max 1KiB
async assertNotEqual no
purpose assertNotEqual "Assert a != b."
label startAssertNotEqual
call neCall math.notEqualI64
arg neCall left a
arg neCall right b
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
call asCall2 assertTrue
arg asCall2 condition asInt2
run asCall2
bindOk asOk2 CSignedInt32 asCall2
bindError asErr2 CSignedInt32 asCall2
branchIfError asCall2 anPropagateErr
const okAn CSignedInt32 0
returnOk okAn
label anPropagateErr
returnError asErr2


operation assertGreaterThan
input assertGreaterThan a CSignedInt64
input assertGreaterThan b CSignedInt64
output assertGreaterThan Result CSignedInt32 CSignedInt32
memory assertGreaterThan heap no
async assertGreaterThan no
purpose assertGreaterThan "Assert a > b. Returns 0 on success; error code 1 (via assertTrue) on failure."
label startAssertGreaterThan
call cmp math.greaterThanI64
arg cmp left a
arg cmp right b
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
call asCall assertTrue
arg asCall condition asInt
run asCall
bindOk asOkRes CSignedInt32 asCall
bindError asErrRes CSignedInt32 asCall
branchIfError asCall agtPropErr
const okAgt CSignedInt32 0
returnOk okAgt
label agtPropErr
returnError asErrRes


operation assertLessThan
input assertLessThan a CSignedInt64
input assertLessThan b CSignedInt64
output assertLessThan Result CSignedInt32 CSignedInt32
memory assertLessThan heap no
async assertLessThan no
purpose assertLessThan "Assert a < b."
label startAssertLessThan
call cmp math.lessThanI64
arg cmp left a
arg cmp right b
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
call asCall assertTrue
arg asCall condition asInt
run asCall
bindOk asOkRes CSignedInt32 asCall
bindError asErrRes CSignedInt32 asCall
branchIfError asCall altPropErr
const okAlt CSignedInt32 0
returnOk okAlt
label altPropErr
returnError asErrRes


operation assertInRange
input assertInRange x CSignedInt64
input assertInRange lo CSignedInt64
input assertInRange hi CSignedInt64
output assertInRange Result CSignedInt32 CSignedInt32
memory assertInRange heap no
async assertInRange no
purpose assertInRange "Assert lo <= x <= hi."
label startAssertInRange
call belowLo math.lessThanI64
arg belowLo left x
arg belowLo right lo
run belowLo
bind below Bool belowLo
branchIf below airFalseBranch
call aboveHi math.greaterThanI64
arg aboveHi left x
arg aboveHi right hi
run aboveHi
bind above Bool aboveHi
branchIf above airFalseBranch
var asInt I64 1
branch airCall
label airFalseBranch
var asInt2 I64 0
branch airCallFalse
label airCall
call asCall assertTrue
arg asCall condition asInt
run asCall
bindOk asOkRes CSignedInt32 asCall
bindError asErrRes CSignedInt32 asCall
branchIfError asCall airPropErr
const okAir CSignedInt32 0
returnOk okAir
label airCallFalse
call asCall2 assertTrue
arg asCall2 condition asInt2
run asCall2
bindOk asOkRes2 CSignedInt32 asCall2
bindError asErrRes2 CSignedInt32 asCall2
returnError asErrRes2
label airPropErr
returnError asErrRes


operation assertNotNull
input assertNotNull p COpaqueMemoryAddress
output assertNotNull Result CSignedInt32 CSignedInt32
memory assertNotNull heap no
async assertNotNull no
purpose assertNotNull "Assert that p is not the NULL pointer."
label startAssertNotNull
call np pointer.isNull
arg np pointer p
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
call asCall assertTrue
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

# assertEqual(2 + 2, 4)
const twoTest CSignedInt64 2
const fourTest CSignedInt64 4
call sumCall math.addI64
arg sumCall left twoTest
arg sumCall right twoTest
run sumCall
bind sumRes I64 sumCall
call a1 assertEqual
arg a1 a sumRes
arg a1 b fourTest
run a1
bindOk a1Ok CSignedInt32 a1
bindError a1Err CSignedInt32 a1
branchIfError a1 testFailed

# assertNotEqual(1, 2)
const oneT CSignedInt64 1
const twoT CSignedInt64 2
call a2 assertNotEqual
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
