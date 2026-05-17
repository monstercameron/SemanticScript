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
#   incrementSignedInt64(n), decrementSignedInt64(n), doubleSignedInt64(n), halveSignedInt64(n)
#   negateSignedInt64(n), reciprocalFloat64(x)
#   sumSignedInt64OneThroughN(n)           - 1+2+...+n  via Gauss formula
#   sumSignedInt64SquaresOneThroughN(n)    - 1^2+...+n^2 via closed form
#   sumSignedInt64CubesOneThroughN(n)      - 1^3+...+n^3 via closed form
#   triangularNumberSignedInt64(n)    - alias for sumSignedInt64OneThroughN
#   leastCommonMultipleSignedInt64(a, b)           - least common multiple via gcd
#   modPower(base, exp, m) - (base^exp) mod m, iterative
# ============================================================


operation incrementSignedInt64
input incrementSignedInt64 inputValue CSignedInt64
output incrementSignedInt64 Result CSignedInt64 Void
memory incrementSignedInt64 heap no
async incrementSignedInt64 no
purpose incrementSignedInt64 "n + 1."
label startIncrementSignedInt64
const one I64 1
call addCall math.addI64
arg addCall left inputValue
arg addCall right one
run addCall
bind r CSignedInt64 addCall
returnOk r


operation decrementSignedInt64
input decrementSignedInt64 inputValue CSignedInt64
output decrementSignedInt64 Result CSignedInt64 Void
memory decrementSignedInt64 heap no
async decrementSignedInt64 no
purpose decrementSignedInt64 "n - 1."
label startDecrementSignedInt64
const one I64 1
call subCall math.subtractI64
arg subCall left inputValue
arg subCall right one
run subCall
bind r CSignedInt64 subCall
returnOk r


operation doubleSignedInt64
input doubleSignedInt64 inputValue CSignedInt64
output doubleSignedInt64 Result CSignedInt64 Void
memory doubleSignedInt64 heap no
async doubleSignedInt64 no
purpose doubleSignedInt64 "n * 2."
label startDoubleSignedInt64
const two I64 2
call mulCall math.multiplyI64
arg mulCall left inputValue
arg mulCall right two
run mulCall
bind r CSignedInt64 mulCall
returnOk r


operation halveSignedInt64
input halveSignedInt64 inputValue CSignedInt64
output halveSignedInt64 Result CSignedInt64 Void
memory halveSignedInt64 heap no
async halveSignedInt64 no
purpose halveSignedInt64 "n / 2 (integer division)."
label startHalveSignedInt64
const two I64 2
call divCall math.divideI64
arg divCall left inputValue
arg divCall right two
run divCall
bind r CSignedInt64 divCall
returnOk r


operation negateSignedInt64
input negateSignedInt64 inputValue CSignedInt64
output negateSignedInt64 Result CSignedInt64 Void
memory negateSignedInt64 heap no
async negateSignedInt64 no
purpose negateSignedInt64 "n * -1."
label startNegateSignedInt64
const negOne I64 -1
call mulCall math.multiplyI64
arg mulCall left inputValue
arg mulCall right negOne
run mulCall
bind r CSignedInt64 mulCall
returnOk r


operation reciprocalFloat64
input reciprocalFloat64 inputValue CFloat64
output reciprocalFloat64 Result CFloat64 Void
memory reciprocalFloat64 heap no
async reciprocalFloat64 no
purpose reciprocalFloat64 "1.0 / x."
label startReciprocalFloat64
const oneF CFloat64 1.0
call divCall math.divideF64
arg divCall left oneF
arg divCall right inputValue
run divCall
bind r CFloat64 divCall
returnOk r


operation sumSignedInt64OneThroughN
input sumSignedInt64OneThroughN inputValue CSignedInt64
output sumSignedInt64OneThroughN Result CSignedInt64 Void
memory sumSignedInt64OneThroughN heap no
async sumSignedInt64OneThroughN no
purpose sumSignedInt64OneThroughN "1+2+...+n via the closed-form n*(n+1)/2."
label startSumSignedInt64OneThroughN
const one I64 1
const two I64 2
call addCall math.addI64
arg addCall left inputValue
arg addCall right one
run addCall
bind nPlus1 I64 addCall
call mulCall math.multiplyI64
arg mulCall left inputValue
arg mulCall right nPlus1
run mulCall
bind product I64 mulCall
call divCall math.divideI64
arg divCall left product
arg divCall right two
run divCall
bind r CSignedInt64 divCall
returnOk r


operation sumSignedInt64SquaresOneThroughN
input sumSignedInt64SquaresOneThroughN inputValue CSignedInt64
output sumSignedInt64SquaresOneThroughN Result CSignedInt64 Void
memory sumSignedInt64SquaresOneThroughN heap no
async sumSignedInt64SquaresOneThroughN no
purpose sumSignedInt64SquaresOneThroughN "1^2+2^2+...+n^2 via n*(n+1)*(2n+1)/6."
label startSumSignedInt64SquaresOneThroughN
const one I64 1
const two I64 2
const six I64 6
call np1 math.addI64
arg np1 left inputValue
arg np1 right one
run np1
bind nP1 I64 np1
call twoN math.multiplyI64
arg twoN left inputValue
arg twoN right two
run twoN
bind twoNv I64 twoN
call twoNp1 math.addI64
arg twoNp1 left twoNv
arg twoNp1 right one
run twoNp1
bind twoNp1v I64 twoNp1
call m1 math.multiplyI64
arg m1 left inputValue
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


operation sumSignedInt64CubesOneThroughN
input sumSignedInt64CubesOneThroughN inputValue CSignedInt64
output sumSignedInt64CubesOneThroughN Result CSignedInt64 Void
memory sumSignedInt64CubesOneThroughN heap no
async sumSignedInt64CubesOneThroughN no
purpose sumSignedInt64CubesOneThroughN "1^3+2^3+...+n^3 via (n*(n+1)/2)^2."
label startSumSignedInt64CubesOneThroughN
call triCall sumSignedInt64OneThroughN
arg triCall n inputValue
run triCall
bindOk tri CSignedInt64 triCall
call sqCall math.multiplyI64
arg sqCall left tri
arg sqCall right tri
run sqCall
bind r CSignedInt64 sqCall
returnOk r


operation triangularNumberSignedInt64
input triangularNumberSignedInt64 inputValue CSignedInt64
output triangularNumberSignedInt64 Result CSignedInt64 Void
memory triangularNumberSignedInt64 heap no
async triangularNumberSignedInt64 no
purpose triangularNumberSignedInt64 "Alias for sumSignedInt64OneThroughN(n) — the nth triangular number."
label startTriangularNumberSignedInt64
call call sumSignedInt64OneThroughN
arg call n inputValue
run call
bindOk r CSignedInt64 call
returnOk r


operation leastCommonMultipleSignedInt64
input leastCommonMultipleSignedInt64 leftValue CSignedInt64
input leastCommonMultipleSignedInt64 rightValue CSignedInt64
output leastCommonMultipleSignedInt64 Result CSignedInt64 Void
memory leastCommonMultipleSignedInt64 heap no
async leastCommonMultipleSignedInt64 no
purpose leastCommonMultipleSignedInt64 "Least common multiple = |a*b|/gcd(a,b). Returns 0 if either input is 0."
label startLeastCommonMultipleSignedInt64
const zeroL I64 0
const negOneL I64 -1
call aEqZ math.equalI64
arg aEqZ left leftValue
arg aEqZ right zeroL
run aEqZ
bind aZ Bool aEqZ
branchIf aZ lcmZero
call bEqZ math.equalI64
arg bEqZ left rightValue
arg bEqZ right zeroL
run bEqZ
bind bZ Bool bEqZ
branchIf bZ lcmZero

# Inline gcd
var x I64 0
var y I64 0
# Take absolute values
call aLt math.lessThanI64
arg aLt left leftValue
arg aLt right zeroL
run aLt
bind aNeg Bool aLt
branchIf aNeg flipA
set x leftValue
branch checkB
label flipA
call negA math.multiplyI64
arg negA left leftValue
arg negA right negOneL
run negA
bind aAbs I64 negA
set x aAbs
branch checkB
label checkB
call bLt math.lessThanI64
arg bLt left rightValue
arg bLt right zeroL
run bLt
bind bNeg Bool bLt
branchIf bNeg flipB
set y rightValue
branch gcdSetup
label flipB
call negB math.multiplyI64
arg negB left rightValue
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
arg prod left leftValue
arg prod right rightValue
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

# sumSignedInt64OneThroughN(100) == 5050
const c100 CSignedInt64 100
const c5050 CSignedInt64 5050
call s1 sumSignedInt64OneThroughN
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

# leastCommonMultipleSignedInt64(12, 18) == 36
const c12 CSignedInt64 12
const c18 CSignedInt64 18
const c36 CSignedInt64 36
call l1 leastCommonMultipleSignedInt64
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
