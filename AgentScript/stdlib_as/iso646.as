project StdIso646SelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <iso646.h>-style operator-keyword
# aliases.
#
# C's <iso646.h> defines `and`, `or`, `not`, `xor`, `compl`, `bitand`,
# `bitor`, `not_eq` as token aliases for the C operators. AgentScript
# doesn't have macro expansion, so we expose each as an operation
# that operates on integers.
#
# Operations:
#   keywordAnd(a, b)      - same as boolAnd
#   keywordOr(a, b)       - same as boolOr
#   keywordNot(x)         - same as boolNot
#   keywordXor(a, b)      - same as boolXor
#   keywordEq(a, b)       - 1 if a == b, else 0
#   keywordNotEq(a, b)    - 1 if a != b, else 0
# ============================================================


operation keywordAnd
input keywordAnd a CSignedInt64
input keywordAnd b CSignedInt64
output keywordAnd Result CSignedInt32 Void
memory keywordAnd heap no
async keywordAnd no
purpose keywordAnd "C's 'and' operator-keyword on two ints. 1 if both non-zero."
label startKeywordAnd
const zeroAn I64 0
const oneAn CSignedInt32 1
const zeroAnOut CSignedInt32 0
call aEqZ math.equalI64
arg aEqZ left a
arg aEqZ right zeroAn
run aEqZ
bind aZ Bool aEqZ
branchIf aZ retFalseA
call bEqZ math.equalI64
arg bEqZ left b
arg bEqZ right zeroAn
run bEqZ
bind bZ Bool bEqZ
branchIf bZ retFalseA
returnOk oneAn
label retFalseA
returnOk zeroAnOut


operation keywordOr
input keywordOr a CSignedInt64
input keywordOr b CSignedInt64
output keywordOr Result CSignedInt32 Void
memory keywordOr heap no
async keywordOr no
purpose keywordOr "C's 'or' on two ints."
label startKeywordOr
const zeroOr I64 0
const oneOr CSignedInt32 1
const zeroOrOut CSignedInt32 0
call aNz math.notEqualI64
arg aNz left a
arg aNz right zeroOr
run aNz
bind aN Bool aNz
branchIf aN retTrueO
call bNz math.notEqualI64
arg bNz left b
arg bNz right zeroOr
run bNz
bind bN Bool bNz
branchIf bN retTrueO
returnOk zeroOrOut
label retTrueO
returnOk oneOr


operation keywordNot
input keywordNot x CSignedInt64
output keywordNot Result CSignedInt32 Void
memory keywordNot heap no
async keywordNot no
purpose keywordNot "C's 'not' (logical NOT) on an int. 1 if x == 0."
label startKeywordNot
const zeroNt I64 0
const oneNt CSignedInt32 1
const zeroNtOut CSignedInt32 0
call eqZ math.equalI64
arg eqZ left x
arg eqZ right zeroNt
run eqZ
bind isZ Bool eqZ
branchIf isZ retTrueN
returnOk zeroNtOut
label retTrueN
returnOk oneNt


operation keywordXor
input keywordXor a CSignedInt64
input keywordXor b CSignedInt64
output keywordXor Result CSignedInt32 Void
memory keywordXor heap no
async keywordXor no
purpose keywordXor "C's 'xor' (logical xor) on two ints. 1 if exactly one is non-zero."
label startKeywordXor
const zeroXor I64 0
const oneXor CSignedInt32 1
const zeroXorOut CSignedInt32 0
call aNzx math.notEqualI64
arg aNzx left a
arg aNzx right zeroXor
run aNzx
bind aNX Bool aNzx
call bNzx math.notEqualI64
arg bNzx left b
arg bNzx right zeroXor
run bNzx
bind bNX Bool bNzx
branchIf aNX checkB
branchIf bNX retTrueX
returnOk zeroXorOut
label checkB
branchIf bNX retFalseX
returnOk oneXor
label retTrueX
returnOk oneXor
label retFalseX
returnOk zeroXorOut


operation keywordEq
input keywordEq a CSignedInt64
input keywordEq b CSignedInt64
output keywordEq Result CSignedInt32 Void
memory keywordEq heap no
async keywordEq no
purpose keywordEq "Returns 1 if a == b, else 0."
label startKeywordEq
const trueEq CSignedInt32 1
const falseEq CSignedInt32 0
call cmp math.equalI64
arg cmp left a
arg cmp right b
run cmp
bind eq Bool cmp
branchIf eq retTrueEq
returnOk falseEq
label retTrueEq
returnOk trueEq


operation keywordNotEq
input keywordNotEq a CSignedInt64
input keywordNotEq b CSignedInt64
output keywordNotEq Result CSignedInt32 Void
memory keywordNotEq heap no
async keywordNotEq no
purpose keywordNotEq "Returns 1 if a != b, else 0."
label startKeywordNotEq
const trueNe CSignedInt32 1
const falseNe CSignedInt32 0
call cmpNe math.notEqualI64
arg cmpNe left a
arg cmpNe right b
run cmpNe
bind ne Bool cmpNe
branchIf ne retTrueNe
returnOk falseNe
label retTrueNe
returnOk trueNe


# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test ISO 646 keyword operations. Prints OK."
label startMain
const oneI CSignedInt64 1
const twoI CSignedInt64 2
const expectedTrue CSignedInt32 1
const expectedFalse CSignedInt32 0

call t1 keywordAnd
arg t1 a oneI
arg t1 b oneI
run t1
bindOk t1Res CSignedInt32 t1
call t1Chk math.equalI64
arg t1Chk left t1Res
arg t1Chk right expectedTrue
run t1Chk
bind t1Ok Bool t1Chk
branchIf t1Ok t1Lbl
branch testFailed
label t1Lbl

call t2 keywordEq
arg t2 a oneI
arg t2 b twoI
run t2
bindOk t2Res CSignedInt32 t2
call t2Chk math.equalI64
arg t2Chk left t2Res
arg t2Chk right expectedFalse
run t2Chk
bind t2Ok Bool t2Chk
branchIf t2Ok t2Lbl
branch testFailed
label t2Lbl

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
