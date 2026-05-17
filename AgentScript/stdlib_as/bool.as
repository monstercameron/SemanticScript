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
#   trueValue, falseValue       - 1 / 0 accessors
#   boolNot(x)                  - 1 if x == 0, else 0
#   boolAnd(a, b), boolOr(a, b) - canonical and/or with short-circuit
#                                 evaluation isn't possible at this
#                                 layer (no closures), so both args
#                                 are evaluated by the caller.
#   boolXor(a, b)               - exclusive-or, returns 0 or 1
#   boolEquiv(a, b)             - logical equivalence, returns 0 or 1
# ============================================================


operation trueValue
output trueValue Result CSignedInt32 Void
memory trueValue heap no
async trueValue no
purpose trueValue "Canonical 1."
label startTrueValue
const t CSignedInt32 1
returnOk t


operation falseValue
output falseValue Result CSignedInt32 Void
memory falseValue heap no
async falseValue no
purpose falseValue "Canonical 0."
label startFalseValue
const f CSignedInt32 0
returnOk f


operation boolNot
input boolNot x CSignedInt32
output boolNot Result CSignedInt32 Void
memory boolNot heap no
async boolNot no
purpose boolNot "1 if x == 0, else 0."
label startBoolNot
const zeroBn I64 0
const oneBn CSignedInt32 1
const zeroOut CSignedInt32 0
call eqCall math.equalI64
arg eqCall left x
arg eqCall right zeroBn
run eqCall
bind isZero Bool eqCall
branchIf isZero notTrue
returnOk zeroOut
label notTrue
returnOk oneBn


operation boolAnd
input boolAnd a CSignedInt32
input boolAnd b CSignedInt32
output boolAnd Result CSignedInt32 Void
memory boolAnd heap no
async boolAnd no
purpose boolAnd "Logical AND. Returns 1 if both args are non-zero, else 0."
label startBoolAnd
const zeroAn I64 0
const oneAn CSignedInt32 1
const zeroAnOut CSignedInt32 0
call aEqZero math.equalI64
arg aEqZero left a
arg aEqZero right zeroAn
run aEqZero
bind aIsZero Bool aEqZero
branchIf aIsZero andFalse
call bEqZero math.equalI64
arg bEqZero left b
arg bEqZero right zeroAn
run bEqZero
bind bIsZero Bool bEqZero
branchIf bIsZero andFalse
returnOk oneAn
label andFalse
returnOk zeroAnOut


operation boolOr
input boolOr a CSignedInt32
input boolOr b CSignedInt32
output boolOr Result CSignedInt32 Void
memory boolOr heap no
async boolOr no
purpose boolOr "Logical OR. Returns 1 if either arg is non-zero, else 0."
label startBoolOr
const zeroOr I64 0
const oneOr CSignedInt32 1
const zeroOrOut CSignedInt32 0
call aNeZero math.notEqualI64
arg aNeZero left a
arg aNeZero right zeroOr
run aNeZero
bind aNz Bool aNeZero
branchIf aNz orTrue
call bNeZero math.notEqualI64
arg bNeZero left b
arg bNeZero right zeroOr
run bNeZero
bind bNz Bool bNeZero
branchIf bNz orTrue
returnOk zeroOrOut
label orTrue
returnOk oneOr


operation boolXor
input boolXor a CSignedInt32
input boolXor b CSignedInt32
output boolXor Result CSignedInt32 Void
memory boolXor heap no
async boolXor no
purpose boolXor "Logical XOR. Returns 1 if exactly one arg is non-zero, else 0."
label startBoolXor
# Compute via (a or b) and not(a and b).
call aOrB boolOr
arg aOrB a a
arg aOrB b b
run aOrB
bindOk aOrBres CSignedInt32 aOrB
call aAndB boolAnd
arg aAndB a a
arg aAndB b b
run aAndB
bindOk aAndBres CSignedInt32 aAndB
call notAandBcall boolNot
arg notAandBcall x aAndBres
run notAandBcall
bindOk notAandB CSignedInt32 notAandBcall
call finalCall boolAnd
arg finalCall a aOrBres
arg finalCall b notAandB
run finalCall
bindOk xorRes CSignedInt32 finalCall
returnOk xorRes


operation boolEquiv
input boolEquiv a CSignedInt32
input boolEquiv b CSignedInt32
output boolEquiv Result CSignedInt32 Void
memory boolEquiv heap no
async boolEquiv no
purpose boolEquiv "Logical equivalence (a iff b). Returns 1 if both args are zero or both are non-zero, else 0."
label startBoolEquiv
call xorCall boolXor
arg xorCall a a
arg xorCall b b
run xorCall
bindOk xorRes CSignedInt32 xorCall
call notCall boolNot
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

# boolNot(0) == 1
call n1 boolNot
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

# boolAnd(1, 1) == 1
call a1 boolAnd
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

# boolOr(0, 1) == 1
call o1 boolOr
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

# boolXor(1, 0) == 1
call x1 boolXor
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

# boolEquiv(1, 1) == 1
call eq1 boolEquiv
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
