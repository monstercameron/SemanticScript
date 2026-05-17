project StdBoolSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <stdbool.h>-style helpers.
#
# C's <stdbool.h> is just #defines of `true`, `false`, and the
# `bool` typedef. AgentScript has Bool natively, so this file exposes
# the constants as accessor operations and adds logical-ops that take
# integers (0 / non-zero) and return canonical 0/1.
#
# Operations:
#   signedInt32BooleanTrueValue, signedInt32BooleanFalseValue       - 1 / 0 accessors
#   negateSignedInt32Boolean(x)                  - 1 if x == 0, else 0
#   combineSignedInt32BooleansWithAnd(a, b), combineSignedInt32BooleansWithOr(a, b) - canonical and/or with short-circuit
#                                 evaluation isn't possible at this
#                                 layer (no closures), so both args
#                                 are evaluated by the caller.
#   combineSignedInt32BooleansWithExclusiveOr(a, b)               - exclusive-or, returns 0 or 1
#   compareSignedInt32BooleansEquivalent(a, b)             - logical equivalence, returns 0 or 1
# ============================================================


operation signedInt32BooleanTrueValue
output signedInt32BooleanTrueValue Result CSignedInt32 Void
memory signedInt32BooleanTrueValue heap no
async signedInt32BooleanTrueValue no
purpose signedInt32BooleanTrueValue "Canonical 1."
label startSignedInt32BooleanTrueValue
const t CSignedInt32 1
returnOk t


operation signedInt32BooleanFalseValue
output signedInt32BooleanFalseValue Result CSignedInt32 Void
memory signedInt32BooleanFalseValue heap no
async signedInt32BooleanFalseValue no
purpose signedInt32BooleanFalseValue "Canonical 0."
label startSignedInt32BooleanFalseValue
const f CSignedInt32 0
returnOk f


operation negateSignedInt32Boolean
input negateSignedInt32Boolean inputValue CSignedInt32
output negateSignedInt32Boolean Result CSignedInt32 Void
memory negateSignedInt32Boolean heap no
async negateSignedInt32Boolean no
purpose negateSignedInt32Boolean "1 if x == 0, else 0."
label startNegateSignedInt32Boolean
const zeroBn I64 0
const oneBn CSignedInt32 1
const zeroOut CSignedInt32 0
call eqCall math.equalI64
arg eqCall left inputValue
arg eqCall right zeroBn
run eqCall
bind isZero Bool eqCall
branchIf isZero notTrue
returnOk zeroOut
label notTrue
returnOk oneBn


operation combineSignedInt32BooleansWithAnd
input combineSignedInt32BooleansWithAnd leftValue CSignedInt32
input combineSignedInt32BooleansWithAnd rightValue CSignedInt32
output combineSignedInt32BooleansWithAnd Result CSignedInt32 Void
memory combineSignedInt32BooleansWithAnd heap no
async combineSignedInt32BooleansWithAnd no
purpose combineSignedInt32BooleansWithAnd "Logical AND. Returns 1 if both args are non-zero, else 0."
label startCombineSignedInt32BooleansWithAnd
const zeroAn I64 0
const oneAn CSignedInt32 1
const zeroAnOut CSignedInt32 0
call aEqZero math.equalI64
arg aEqZero left leftValue
arg aEqZero right zeroAn
run aEqZero
bind aIsZero Bool aEqZero
branchIf aIsZero andFalse
call bEqZero math.equalI64
arg bEqZero left rightValue
arg bEqZero right zeroAn
run bEqZero
bind bIsZero Bool bEqZero
branchIf bIsZero andFalse
returnOk oneAn
label andFalse
returnOk zeroAnOut


operation combineSignedInt32BooleansWithOr
input combineSignedInt32BooleansWithOr leftValue CSignedInt32
input combineSignedInt32BooleansWithOr rightValue CSignedInt32
output combineSignedInt32BooleansWithOr Result CSignedInt32 Void
memory combineSignedInt32BooleansWithOr heap no
async combineSignedInt32BooleansWithOr no
purpose combineSignedInt32BooleansWithOr "Logical OR. Returns 1 if either arg is non-zero, else 0."
label startCombineSignedInt32BooleansWithOr
const zeroOr I64 0
const oneOr CSignedInt32 1
const zeroOrOut CSignedInt32 0
call aNeZero math.notEqualI64
arg aNeZero left leftValue
arg aNeZero right zeroOr
run aNeZero
bind aNz Bool aNeZero
branchIf aNz orTrue
call bNeZero math.notEqualI64
arg bNeZero left rightValue
arg bNeZero right zeroOr
run bNeZero
bind bNz Bool bNeZero
branchIf bNz orTrue
returnOk zeroOrOut
label orTrue
returnOk oneOr


operation combineSignedInt32BooleansWithExclusiveOr
input combineSignedInt32BooleansWithExclusiveOr leftValue CSignedInt32
input combineSignedInt32BooleansWithExclusiveOr rightValue CSignedInt32
output combineSignedInt32BooleansWithExclusiveOr Result CSignedInt32 Void
memory combineSignedInt32BooleansWithExclusiveOr heap no
async combineSignedInt32BooleansWithExclusiveOr no
purpose combineSignedInt32BooleansWithExclusiveOr "Logical XOR. Returns 1 if exactly one arg is non-zero, else 0."
label startCombineSignedInt32BooleansWithExclusiveOr
# Compute via (a or b) and not(a and b).
call aOrB combineSignedInt32BooleansWithOr
arg aOrB a leftValue
arg aOrB b rightValue
run aOrB
bindOk aOrBres CSignedInt32 aOrB
call aAndB combineSignedInt32BooleansWithAnd
arg aAndB a leftValue
arg aAndB b rightValue
run aAndB
bindOk aAndBres CSignedInt32 aAndB
call notAandBcall negateSignedInt32Boolean
arg notAandBcall x aAndBres
run notAandBcall
bindOk notAandB CSignedInt32 notAandBcall
call finalCall combineSignedInt32BooleansWithAnd
arg finalCall a aOrBres
arg finalCall b notAandB
run finalCall
bindOk xorRes CSignedInt32 finalCall
returnOk xorRes


operation compareSignedInt32BooleansEquivalent
input compareSignedInt32BooleansEquivalent leftValue CSignedInt32
input compareSignedInt32BooleansEquivalent rightValue CSignedInt32
output compareSignedInt32BooleansEquivalent Result CSignedInt32 Void
memory compareSignedInt32BooleansEquivalent heap no
async compareSignedInt32BooleansEquivalent no
purpose compareSignedInt32BooleansEquivalent "Logical equivalence (a iff b). Returns 1 if both args are zero or both are non-zero, else 0."
label startCompareSignedInt32BooleansEquivalent
call xorCall combineSignedInt32BooleansWithExclusiveOr
arg xorCall a leftValue
arg xorCall b rightValue
run xorCall
bindOk xorRes CSignedInt32 xorCall
call notCall negateSignedInt32Boolean
arg notCall x xorRes
run notCall
bindOk eqRes CSignedInt32 notCall
returnOk eqRes


# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test boolean ports. Prints OK."

label startMain
const oneI32 CSignedInt32 1
const zeroI32 CSignedInt32 0

# negateSignedInt32Boolean(0) == 1
call n1 negateSignedInt32Boolean
arg n1 x zeroI32
run n1
bindOk n1Res CSignedInt32 n1
call n1Check math.equalI64
arg n1Check left n1Res
arg n1Check right oneI32
run n1Check
bind n1Ok Bool n1Check
branchIf n1Ok n1OkLabel
branch testFailed
label n1OkLabel

# combineSignedInt32BooleansWithAnd(1, 1) == 1
call a1 combineSignedInt32BooleansWithAnd
arg a1 a oneI32
arg a1 b oneI32
run a1
bindOk a1Res CSignedInt32 a1
call a1Check math.equalI64
arg a1Check left a1Res
arg a1Check right oneI32
run a1Check
bind a1Ok Bool a1Check
branchIf a1Ok a1OkLabel
branch testFailed
label a1OkLabel

# combineSignedInt32BooleansWithOr(0, 1) == 1
call o1 combineSignedInt32BooleansWithOr
arg o1 a zeroI32
arg o1 b oneI32
run o1
bindOk o1Res CSignedInt32 o1
call o1Check math.equalI64
arg o1Check left o1Res
arg o1Check right oneI32
run o1Check
bind o1Ok Bool o1Check
branchIf o1Ok o1OkLabel
branch testFailed
label o1OkLabel

# combineSignedInt32BooleansWithExclusiveOr(1, 0) == 1
call x1 combineSignedInt32BooleansWithExclusiveOr
arg x1 a oneI32
arg x1 b zeroI32
run x1
bindOk x1Res CSignedInt32 x1
call x1Check math.equalI64
arg x1Check left x1Res
arg x1Check right oneI32
run x1Check
bind x1Ok Bool x1Check
branchIf x1Ok x1OkLabel
branch testFailed
label x1OkLabel

# compareSignedInt32BooleansEquivalent(1, 1) == 1
call eq1 compareSignedInt32BooleansEquivalent
arg eq1 a oneI32
arg eq1 b oneI32
run eq1
bindOk eq1Res CSignedInt32 eq1
call eq1Check math.equalI64
arg eq1Check left eq1Res
arg eq1Check right oneI32
run eq1Check
bind eq1Ok Bool eq1Check
branchIf eq1Ok eq1OkLabel
branch testFailed
label eq1OkLabel

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
