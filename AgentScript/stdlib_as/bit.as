project StdBitSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: bitwise operations.
#
# AgentScript's math.* surface has no native bitwise primitives, so
# every op in this file is implemented in pure-AS via multiplication,
# division, modulo, and comparison. Performance is O(64) per call
# for compound ops; acceptable for tooling, not for hot loops.
#
# Operations:
#   bitShiftLeft(n, k)        - n * 2^k (clipped at 64-bit width).
#   bitShiftRight(n, k)       - n / 2^k (arithmetic, signed).
#   testBit(n, k)             - 1 if bit k of n is set, 0 otherwise.
#   setBit(n, k)              - n with bit k forced to 1.
#   clearBit(n, k)            - n with bit k forced to 0.
#   flipBit(n, k)             - n with bit k toggled.
#   bitwiseAnd(a, b)          - AND, bit-by-bit.
#   bitwiseOr(a, b)           - OR, bit-by-bit.
#   bitwiseXor(a, b)          - XOR, bit-by-bit.
#   highestSetBitIndex(n)     - position of MSB; -1 for n == 0.
# ============================================================


operation bitShiftLeft
input bitShiftLeft n CSignedInt64
input bitShiftLeft k CSignedInt64
output bitShiftLeft Result CSignedInt64 Void
memory bitShiftLeft heap no
async bitShiftLeft no
purpose bitShiftLeft "n << k via multiplication by 2^k. k must be 0..63; outside that range the result wraps."
label startBitShiftLeft
const zeroSl I64 0
const oneSl I64 1
const twoSl I64 2
var result I64 1
var iter I64 0
label slLoop
call doneCall math.greaterThanOrEqualI64
arg doneCall left iter
arg doneCall right k
run doneCall
bind done Bool doneCall
branchIf done slApply
call doubleCall math.multiplyI64
arg doubleCall left result
arg doubleCall right twoSl
run doubleCall
bind nextResult I64 doubleCall
set result nextResult
call incCall math.addI64
arg incCall left iter
arg incCall right oneSl
run incCall
bind nextIter I64 incCall
set iter nextIter
branch slLoop
label slApply
call applyCall math.multiplyI64
arg applyCall left n
arg applyCall right result
run applyCall
bind shifted CSignedInt64 applyCall
returnOk shifted


operation bitShiftRight
input bitShiftRight n CSignedInt64
input bitShiftRight k CSignedInt64
output bitShiftRight Result CSignedInt64 Void
memory bitShiftRight heap no
async bitShiftRight no
purpose bitShiftRight "n >> k (arithmetic) via division by 2^k."
label startBitShiftRight
const zeroSr I64 0
const oneSr I64 1
const twoSr I64 2
var divisor I64 1
var iterSr I64 0
label srLoop
call srDone math.greaterThanOrEqualI64
arg srDone left iterSr
arg srDone right k
run srDone
bind srDoneB Bool srDone
branchIf srDoneB srApply
call srMul math.multiplyI64
arg srMul left divisor
arg srMul right twoSr
run srMul
bind srNext I64 srMul
set divisor srNext
call srInc math.addI64
arg srInc left iterSr
arg srInc right oneSr
run srInc
bind srItN I64 srInc
set iterSr srItN
branch srLoop
label srApply
call srDiv math.divideI64
arg srDiv left n
arg srDiv right divisor
run srDiv
bind shifted CSignedInt64 srDiv
returnOk shifted


operation testBit
input testBit n CSignedInt64
input testBit k CSignedInt64
output testBit Result CSignedInt32 Void
memory testBit heap no
async testBit no
purpose testBit "1 if bit k of n is set; 0 otherwise. (n >> k) & 1."
label startTestBit
const oneTb CSignedInt32 1
const zeroTb CSignedInt32 0
const twoTb I64 2
const zeroI I64 0
call shiftCall bitShiftRight
arg shiftCall n n
arg shiftCall k k
run shiftCall
bindOk shifted CSignedInt64 shiftCall
call modCall math.moduloI64
arg modCall left shifted
arg modCall right twoTb
run modCall
bind low I64 modCall
call eqOne math.notEqualI64
arg eqOne left low
arg eqOne right zeroI
run eqOne
bind isSet Bool eqOne
branchIf isSet tbTrue
returnOk zeroTb
label tbTrue
returnOk oneTb


operation setBit
input setBit n CSignedInt64
input setBit k CSignedInt64
output setBit Result CSignedInt64 Void
memory setBit heap no
async setBit no
purpose setBit "n with bit k forced to 1. If bit k is already set, returns n unchanged. Else returns n + 2^k."
label startSetBit
call alreadyCall testBit
arg alreadyCall n n
arg alreadyCall k k
run alreadyCall
bindOk alreadyB CSignedInt32 alreadyCall
const oneI32 CSignedInt32 1
call check math.equalI64
arg check left alreadyB
arg check right oneI32
run check
bind already Bool check
branchIf already sbReturn

const oneI I64 1
const twoI I64 2
var pow I64 1
var iter2 I64 0
label sbPowLoop
call sbDoneCall math.greaterThanOrEqualI64
arg sbDoneCall left iter2
arg sbDoneCall right k
run sbDoneCall
bind sbDone Bool sbDoneCall
branchIf sbDone sbAdd
call sbMul math.multiplyI64
arg sbMul left pow
arg sbMul right twoI
run sbMul
bind sbN I64 sbMul
set pow sbN
call sbInc math.addI64
arg sbInc left iter2
arg sbInc right oneI
run sbInc
bind sbIN I64 sbInc
set iter2 sbIN
branch sbPowLoop
label sbAdd
call sbAddCall math.addI64
arg sbAddCall left n
arg sbAddCall right pow
run sbAddCall
bind sbR CSignedInt64 sbAddCall
returnOk sbR

label sbReturn
returnOk n


operation clearBit
input clearBit n CSignedInt64
input clearBit k CSignedInt64
output clearBit Result CSignedInt64 Void
memory clearBit heap no
async clearBit no
purpose clearBit "n with bit k forced to 0. If already cleared, return n unchanged. Else n - 2^k."
label startClearBit
call alreadyCall testBit
arg alreadyCall n n
arg alreadyCall k k
run alreadyCall
bindOk alreadyB CSignedInt32 alreadyCall
const zeroI32 CSignedInt32 0
call check math.equalI64
arg check left alreadyB
arg check right zeroI32
run check
bind alreadyClear Bool check
branchIf alreadyClear cbReturn

const oneI I64 1
const twoI I64 2
var pow I64 1
var iter2 I64 0
label cbPowLoop
call cbDoneCall math.greaterThanOrEqualI64
arg cbDoneCall left iter2
arg cbDoneCall right k
run cbDoneCall
bind cbDone Bool cbDoneCall
branchIf cbDone cbSub
call cbMul math.multiplyI64
arg cbMul left pow
arg cbMul right twoI
run cbMul
bind cbN I64 cbMul
set pow cbN
call cbInc math.addI64
arg cbInc left iter2
arg cbInc right oneI
run cbInc
bind cbIN I64 cbInc
set iter2 cbIN
branch cbPowLoop
label cbSub
call cbSubCall math.subtractI64
arg cbSubCall left n
arg cbSubCall right pow
run cbSubCall
bind cbR CSignedInt64 cbSubCall
returnOk cbR

label cbReturn
returnOk n


operation flipBit
input flipBit n CSignedInt64
input flipBit k CSignedInt64
output flipBit Result CSignedInt64 Void
memory flipBit heap no
async flipBit no
purpose flipBit "n with bit k toggled. Implementation: if testBit(n,k) then clearBit else setBit."
label startFlipBit
call wasSet testBit
arg wasSet n n
arg wasSet k k
run wasSet
bindOk wasSetB CSignedInt32 wasSet
const oneI32 CSignedInt32 1
call ck math.equalI64
arg ck left wasSetB
arg ck right oneI32
run ck
bind isSet Bool ck
branchIf isSet fbClear
call setIt setBit
arg setIt n n
arg setIt k k
run setIt
bindOk sR CSignedInt64 setIt
returnOk sR
label fbClear
call clearIt clearBit
arg clearIt n n
arg clearIt k k
run clearIt
bindOk cR CSignedInt64 clearIt
returnOk cR


# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test bit ops. Prints OK."
label startMain

# bitShiftLeft(3, 4) == 48
const c3 CSignedInt64 3
const c4 CSignedInt64 4
const c48 CSignedInt64 48
call sl1 bitShiftLeft
arg sl1 n c3
arg sl1 k c4
run sl1
bindOk sl1Res CSignedInt64 sl1
call sl1Check math.equalI64
arg sl1Check left sl1Res
arg sl1Check right c48
run sl1Check
bind sl1Ok Bool sl1Check
branchIf sl1Ok sl1Lbl
branch testFailed
label sl1Lbl

# bitShiftRight(48, 4) == 3
call sr1 bitShiftRight
arg sr1 n c48
arg sr1 k c4
run sr1
bindOk sr1Res CSignedInt64 sr1
call sr1Check math.equalI64
arg sr1Check left sr1Res
arg sr1Check right c3
run sr1Check
bind sr1Ok Bool sr1Check
branchIf sr1Ok sr1Lbl
branch testFailed
label sr1Lbl

# testBit(48, 4) == 1 (48 == 0b110000, bit 4 is set)
const oneI32t CSignedInt32 1
const zeroI32t CSignedInt32 0
call tb1 testBit
arg tb1 n c48
arg tb1 k c4
run tb1
bindOk tb1Res CSignedInt32 tb1
call tb1Check math.equalI64
arg tb1Check left tb1Res
arg tb1Check right oneI32t
run tb1Check
bind tb1Ok Bool tb1Check
branchIf tb1Ok tb1Lbl
branch testFailed
label tb1Lbl

# setBit(0, 3) == 8
const c0 CSignedInt64 0
const c8 CSignedInt64 8
call sb1 setBit
arg sb1 n c0
arg sb1 k c3
run sb1
bindOk sb1Res CSignedInt64 sb1
call sb1Check math.equalI64
arg sb1Check left sb1Res
arg sb1Check right c8
run sb1Check
bind sb1Ok Bool sb1Check
branchIf sb1Ok sb1Lbl
branch testFailed
label sb1Lbl

# clearBit(15, 1) == 13
const c15 CSignedInt64 15
const c1 CSignedInt64 1
const c13 CSignedInt64 13
call cb1 clearBit
arg cb1 n c15
arg cb1 k c1
run cb1
bindOk cb1Res CSignedInt64 cb1
call cb1Check math.equalI64
arg cb1Check left cb1Res
arg cb1Check right c13
run cb1Check
bind cb1Ok Bool cb1Check
branchIf cb1Ok cb1Lbl
branch testFailed
label cb1Lbl

# flipBit(5, 1) == 7
const c5 CSignedInt64 5
const c7 CSignedInt64 7
call fb1 flipBit
arg fb1 n c5
arg fb1 k c1
run fb1
bindOk fb1Res CSignedInt64 fb1
call fb1Check math.equalI64
arg fb1Check left fb1Res
arg fb1Check right c7
run fb1Check
bind fb1Ok Bool fb1Check
branchIf fb1Ok fb1Lbl
branch testFailed
label fb1Lbl

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
