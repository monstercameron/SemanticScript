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
#   evaluateIso646AndKeyword(a, b)      - same as boolAnd
#   evaluateIso646OrKeyword(a, b)       - same as boolOr
#   evaluateIso646NotKeyword(x)         - same as boolNot
#   evaluateIso646XorKeyword(a, b)      - same as boolXor
#   evaluateIso646EqualKeyword(a, b)       - 1 if a == b, else 0
#   evaluateIso646NotEqualKeyword(a, b)    - 1 if a != b, else 0
# ============================================================


operation evaluateIso646AndKeyword
input evaluateIso646AndKeyword leftValue CSignedInt64
input evaluateIso646AndKeyword rightValue CSignedInt64
output evaluateIso646AndKeyword Result CSignedInt32 Void
memory evaluateIso646AndKeyword heap no
async evaluateIso646AndKeyword no
purpose evaluateIso646AndKeyword "C's 'and' operator-keyword on two ints. 1 if both non-zero."
label startEvaluateIso646AndKeyword
const zeroAn I64 0
const oneAn CSignedInt32 1
const zeroAnOut CSignedInt32 0
call aEqZ math.equalI64
arg aEqZ left leftValue
arg aEqZ right zeroAn
run aEqZ
bind aZ Bool aEqZ
branchIf aZ retFalseA
call bEqZ math.equalI64
arg bEqZ left rightValue
arg bEqZ right zeroAn
run bEqZ
bind bZ Bool bEqZ
branchIf bZ retFalseA
returnOk oneAn
label retFalseA
returnOk zeroAnOut


operation evaluateIso646OrKeyword
input evaluateIso646OrKeyword leftValue CSignedInt64
input evaluateIso646OrKeyword rightValue CSignedInt64
output evaluateIso646OrKeyword Result CSignedInt32 Void
memory evaluateIso646OrKeyword heap no
async evaluateIso646OrKeyword no
purpose evaluateIso646OrKeyword "C's 'or' on two ints."
label startEvaluateIso646OrKeyword
const zeroOr I64 0
const oneOr CSignedInt32 1
const zeroOrOut CSignedInt32 0
call aNz math.notEqualI64
arg aNz left leftValue
arg aNz right zeroOr
run aNz
bind aN Bool aNz
branchIf aN retTrueO
call bNz math.notEqualI64
arg bNz left rightValue
arg bNz right zeroOr
run bNz
bind bN Bool bNz
branchIf bN retTrueO
returnOk zeroOrOut
label retTrueO
returnOk oneOr


operation evaluateIso646NotKeyword
input evaluateIso646NotKeyword inputValue CSignedInt64
output evaluateIso646NotKeyword Result CSignedInt32 Void
memory evaluateIso646NotKeyword heap no
async evaluateIso646NotKeyword no
purpose evaluateIso646NotKeyword "C's 'not' (logical NOT) on an int. 1 if x == 0."
label startEvaluateIso646NotKeyword
const zeroNt I64 0
const oneNt CSignedInt32 1
const zeroNtOut CSignedInt32 0
call eqZ math.equalI64
arg eqZ left inputValue
arg eqZ right zeroNt
run eqZ
bind isZ Bool eqZ
branchIf isZ retTrueN
returnOk zeroNtOut
label retTrueN
returnOk oneNt


operation evaluateIso646XorKeyword
input evaluateIso646XorKeyword leftValue CSignedInt64
input evaluateIso646XorKeyword rightValue CSignedInt64
output evaluateIso646XorKeyword Result CSignedInt32 Void
memory evaluateIso646XorKeyword heap no
async evaluateIso646XorKeyword no
purpose evaluateIso646XorKeyword "C's 'xor' (logical xor) on two ints. 1 if exactly one is non-zero."
label startEvaluateIso646XorKeyword
const zeroXor I64 0
const oneXor CSignedInt32 1
const zeroXorOut CSignedInt32 0
call aNzx math.notEqualI64
arg aNzx left leftValue
arg aNzx right zeroXor
run aNzx
bind aNX Bool aNzx
call bNzx math.notEqualI64
arg bNzx left rightValue
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


operation evaluateIso646EqualKeyword
input evaluateIso646EqualKeyword leftValue CSignedInt64
input evaluateIso646EqualKeyword rightValue CSignedInt64
output evaluateIso646EqualKeyword Result CSignedInt32 Void
memory evaluateIso646EqualKeyword heap no
async evaluateIso646EqualKeyword no
purpose evaluateIso646EqualKeyword "Returns 1 if a == b, else 0."
label startEvaluateIso646EqualKeyword
const trueEq CSignedInt32 1
const falseEq CSignedInt32 0
call cmp math.equalI64
arg cmp left leftValue
arg cmp right rightValue
run cmp
bind eq Bool cmp
branchIf eq retTrueEq
returnOk falseEq
label retTrueEq
returnOk trueEq


operation evaluateIso646NotEqualKeyword
input evaluateIso646NotEqualKeyword leftValue CSignedInt64
input evaluateIso646NotEqualKeyword rightValue CSignedInt64
output evaluateIso646NotEqualKeyword Result CSignedInt32 Void
memory evaluateIso646NotEqualKeyword heap no
async evaluateIso646NotEqualKeyword no
purpose evaluateIso646NotEqualKeyword "Returns 1 if a != b, else 0."
label startEvaluateIso646NotEqualKeyword
const trueNe CSignedInt32 1
const falseNe CSignedInt32 0
call cmpNe math.notEqualI64
arg cmpNe left leftValue
arg cmpNe right rightValue
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

call t1 evaluateIso646AndKeyword
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

call t2 evaluateIso646EqualKeyword
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
