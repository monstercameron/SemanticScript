project StdNumericSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: more numeric helpers.
#
# Operations:
#   incrementInt(n), decrementInt(n), doubleInt(n), halveInt(n)
#   negateInt(n), reciprocalFloat(x)
#   sumOneToN(n)           - 1+2+...+n  via Gauss formula
#   sumSquaresOneToN(n)    - 1^2+...+n^2 via closed form
#   sumCubesOneToN(n)      - 1^3+...+n^3 via closed form
#   triangularNumber(n)    - alias for sumOneToN
#   lcmInt(a, b)           - least common multiple via gcd
#   modPower(base, exp, m) - (base^exp) mod m, iterative
# ============================================================


operation incrementInt
input incrementInt n CSignedInt64
output incrementInt Result CSignedInt64 Void
memory incrementInt heap no
async incrementInt no
purpose incrementInt "n + 1."
label startIncrementInt
const one I64 1
call addCall math.addI64
arg addCall left n
arg addCall right one
run addCall
bind r CSignedInt64 addCall
returnOk r


operation decrementInt
input decrementInt n CSignedInt64
output decrementInt Result CSignedInt64 Void
memory decrementInt heap no
async decrementInt no
purpose decrementInt "n - 1."
label startDecrementInt
const one I64 1
call subCall math.subtractI64
arg subCall left n
arg subCall right one
run subCall
bind r CSignedInt64 subCall
returnOk r


operation doubleInt
input doubleInt n CSignedInt64
output doubleInt Result CSignedInt64 Void
memory doubleInt heap no
async doubleInt no
purpose doubleInt "n * 2."
label startDoubleInt
const two I64 2
call mulCall math.multiplyI64
arg mulCall left n
arg mulCall right two
run mulCall
bind r CSignedInt64 mulCall
returnOk r


operation halveInt
input halveInt n CSignedInt64
output halveInt Result CSignedInt64 Void
memory halveInt heap no
async halveInt no
purpose halveInt "n / 2 (integer division)."
label startHalveInt
const two I64 2
call divCall math.divideI64
arg divCall left n
arg divCall right two
run divCall
bind r CSignedInt64 divCall
returnOk r


operation negateInt
input negateInt n CSignedInt64
output negateInt Result CSignedInt64 Void
memory negateInt heap no
async negateInt no
purpose negateInt "n * -1."
label startNegateInt
const negOne I64 -1
call mulCall math.multiplyI64
arg mulCall left n
arg mulCall right negOne
run mulCall
bind r CSignedInt64 mulCall
returnOk r


operation reciprocalFloat
input reciprocalFloat x CFloat64
output reciprocalFloat Result CFloat64 Void
memory reciprocalFloat heap no
async reciprocalFloat no
purpose reciprocalFloat "1.0 / x."
label startReciprocalFloat
const oneF CFloat64 1.0
call divCall math.divideF64
arg divCall left oneF
arg divCall right x
run divCall
bind r CFloat64 divCall
returnOk r


operation sumOneToN
input sumOneToN n CSignedInt64
output sumOneToN Result CSignedInt64 Void
memory sumOneToN heap no
async sumOneToN no
purpose sumOneToN "1+2+...+n via the closed-form n*(n+1)/2."
label startSumOneToN
const one I64 1
const two I64 2
call addCall math.addI64
arg addCall left n
arg addCall right one
run addCall
bind nPlus1 I64 addCall
call mulCall math.multiplyI64
arg mulCall left n
arg mulCall right nPlus1
run mulCall
bind product I64 mulCall
call divCall math.divideI64
arg divCall left product
arg divCall right two
run divCall
bind r CSignedInt64 divCall
returnOk r


operation sumSquaresOneToN
input sumSquaresOneToN n CSignedInt64
output sumSquaresOneToN Result CSignedInt64 Void
memory sumSquaresOneToN heap no
async sumSquaresOneToN no
purpose sumSquaresOneToN "1^2+2^2+...+n^2 via n*(n+1)*(2n+1)/6."
label startSumSquaresOneToN
const one I64 1
const two I64 2
const six I64 6
call np1 math.addI64
arg np1 left n
arg np1 right one
run np1
bind nP1 I64 np1
call twoN math.multiplyI64
arg twoN left n
arg twoN right two
run twoN
bind twoNv I64 twoN
call twoNp1 math.addI64
arg twoNp1 left twoNv
arg twoNp1 right one
run twoNp1
bind twoNp1v I64 twoNp1
call m1 math.multiplyI64
arg m1 left n
arg m1 right nP1
run m1
bind m1v I64 m1
call m2 math.multiplyI64
arg m2 left m1v
arg m2 right twoNp1v
run m2
bind m2v I64 m2
call divCall math.divideI64
arg divCall left m2v
arg divCall right six
run divCall
bind r CSignedInt64 divCall
returnOk r


operation sumCubesOneToN
input sumCubesOneToN n CSignedInt64
output sumCubesOneToN Result CSignedInt64 Void
memory sumCubesOneToN heap no
async sumCubesOneToN no
purpose sumCubesOneToN "1^3+2^3+...+n^3 via (n*(n+1)/2)^2."
label startSumCubesOneToN
call triCall sumOneToN
arg triCall n n
run triCall
bindOk tri CSignedInt64 triCall
call sqCall math.multiplyI64
arg sqCall left tri
arg sqCall right tri
run sqCall
bind r CSignedInt64 sqCall
returnOk r


operation triangularNumber
input triangularNumber n CSignedInt64
output triangularNumber Result CSignedInt64 Void
memory triangularNumber heap no
async triangularNumber no
purpose triangularNumber "Alias for sumOneToN(n) — the nth triangular number."
label startTriangularNumber
call call sumOneToN
arg call n n
run call
bindOk r CSignedInt64 call
returnOk r


operation lcmInt
input lcmInt a CSignedInt64
input lcmInt b CSignedInt64
output lcmInt Result CSignedInt64 Void
memory lcmInt heap no
async lcmInt no
purpose lcmInt "Least common multiple = |a*b|/gcd(a,b). Returns 0 if either input is 0."
label startLcmInt
const zeroL I64 0
const negOneL I64 -1
call aEqZ math.equalI64
arg aEqZ left a
arg aEqZ right zeroL
run aEqZ
bind aZ Bool aEqZ
branchIf aZ lcmZero
call bEqZ math.equalI64
arg bEqZ left b
arg bEqZ right zeroL
run bEqZ
bind bZ Bool bEqZ
branchIf bZ lcmZero

# Inline gcd
var x I64 0
var y I64 0
# Take absolute values
call aLt math.lessThanI64
arg aLt left a
arg aLt right zeroL
run aLt
bind aNeg Bool aLt
branchIf aNeg flipA
set x a
branch checkB
label flipA
call negA math.multiplyI64
arg negA left a
arg negA right negOneL
run negA
bind aAbs I64 negA
set x aAbs
branch checkB
label checkB
call bLt math.lessThanI64
arg bLt left b
arg bLt right zeroL
run bLt
bind bNeg Bool bLt
branchIf bNeg flipB
set y b
branch gcdSetup
label flipB
call negB math.multiplyI64
arg negB left b
arg negB right negOneL
run negB
bind bAbs I64 negB
set y bAbs
branch gcdSetup
label gcdSetup
label gcdLoop
call yZeroCall math.equalI64
arg yZeroCall left y
arg yZeroCall right zeroL
run yZeroCall
bind yIsZero Bool yZeroCall
branchIf yIsZero gcdDone
call rCall math.moduloI64
arg rCall left x
arg rCall right y
run rCall
bind r I64 rCall
set x y
set y r
branch gcdLoop
label gcdDone
# product / x
call prod math.multiplyI64
arg prod left a
arg prod right b
run prod
bind product I64 prod
call lcmCall math.divideI64
arg lcmCall left product
arg lcmCall right x
run lcmCall
bind lcmRaw I64 lcmCall
# abs
call lcmLt math.lessThanI64
arg lcmLt left lcmRaw
arg lcmLt right zeroL
run lcmLt
bind lcmNeg Bool lcmLt
branchIf lcmNeg lcmFlip
returnOk lcmRaw
label lcmFlip
call lcmNegCall math.multiplyI64
arg lcmNegCall left lcmRaw
arg lcmNegCall right negOneL
run lcmNegCall
bind lcmAbs CSignedInt64 lcmNegCall
returnOk lcmAbs

label lcmZero
returnOk zeroL


# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test numeric ops. Prints OK."
label startMain

# sumOneToN(100) == 5050
const c100 CSignedInt64 100
const c5050 CSignedInt64 5050
call s1 sumOneToN
arg s1 n c100
run s1
bindOk s1Res CSignedInt64 s1
call s1Check math.equalI64
arg s1Check left s1Res
arg s1Check right c5050
run s1Check
bind s1Ok Bool s1Check
branchIf s1Ok s1Lbl
branch testFailed
label s1Lbl

# lcmInt(12, 18) == 36
const c12 CSignedInt64 12
const c18 CSignedInt64 18
const c36 CSignedInt64 36
call l1 lcmInt
arg l1 a c12
arg l1 b c18
run l1
bindOk l1Res CSignedInt64 l1
call l1Check math.equalI64
arg l1Check left l1Res
arg l1Check right c36
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
