# ============================================================
# AGENTSCRIPT STDLIB TESTS: math
# ============================================================
#
# Companion smoke + extended unit tests for stdlib_as/math.as.
# Imports the math module and asserts every exported integer
# helper (sqrt / factorial / isPrime / isPowerOfTwo / nextPowerOfTwo /
# digit count / parity / popcount / leading & trailing zero counts /
# sign / abs-diff / square / cube / range check) plus boundary +
# round-trip property tests (sqrt∘square, etc.).
#
# Pattern: stdlib_as/foo.as ships pure-module operations only;
# stdlib_as/foo.test.as carries every smoke / unit test for it.

project StdMathTest
target console
runtime AgentRuntime 0.1
entry console main

importModule math

error MainError
errorCase MainError MathSmokeAssertionFailed
errorCase MainError ConsoleWriteFailed

# section capability
# rationale: smoke-test main writes a single OK line to stdout.
capability stdoutWriteCapability console.stdout write

# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
useCapability main stdoutWriteCapability
effect main write console.stdout
memoryHeap main no
async main no
purpose main "Smoke-test the integer math helpers."
invariant main "Every named check holds, or the failure path runs."

label startMain

# integerSquareRootSignedInt64(144) == 12
const oneHundredFortyFour CSignedInt64 144
const twelveExpected CSignedInt64 12
call assertSqrtCall integerSquareRootSignedInt64
arg assertSqrtCall inputValue oneHundredFortyFour
run assertSqrtCall
bind sqrtResult CSignedInt64 assertSqrtCall
call checkSqrtCall math.equalI64
arg checkSqrtCall left sqrtResult
arg checkSqrtCall right twelveExpected
run checkSqrtCall
bind sqrtOk Bool checkSqrtCall
branchIf sqrtOk sqrtHolds
branch smokeAssertionFailed
label sqrtHolds

# factorialSignedInt64(5) == 120
const fiveInputForFactorial CSignedInt64 5
const oneHundredTwentyExpected CSignedInt64 120
call assertFactorialCall factorialSignedInt64
arg assertFactorialCall inputValue fiveInputForFactorial
run assertFactorialCall
bind factorialResult CSignedInt64 assertFactorialCall
call checkFactorialCall math.equalI64
arg checkFactorialCall left factorialResult
arg checkFactorialCall right oneHundredTwentyExpected
run checkFactorialCall
bind factorialOk Bool checkFactorialCall
branchIf factorialOk factorialHolds
branch smokeAssertionFailed
label factorialHolds

# isSignedInt64Prime(17) == true
const seventeen CSignedInt64 17
call assertPrime17Call isSignedInt64Prime
arg assertPrime17Call inputValue seventeen
run assertPrime17Call
bind prime17Result Bool assertPrime17Call
branchIf prime17Result prime17Holds
branch smokeAssertionFailed
label prime17Holds

# isSignedInt64Prime(15) == false
const fifteen CSignedInt64 15
call assertPrime15Call isSignedInt64Prime
arg assertPrime15Call inputValue fifteen
run assertPrime15Call
bind prime15Result Bool assertPrime15Call
branchIf prime15Result smokeAssertionFailed

# isSignedInt64PowerOfTwo(64) == true
const sixtyFour CSignedInt64 64
call assertPow64Call isSignedInt64PowerOfTwo
arg assertPow64Call inputValue sixtyFour
run assertPow64Call
bind pow64Result Bool assertPow64Call
branchIf pow64Result pow64Holds
branch smokeAssertionFailed
label pow64Holds

# isSignedInt64PowerOfTwo(48) == false
const fortyEight CSignedInt64 48
call assertPow48Call isSignedInt64PowerOfTwo
arg assertPow48Call inputValue fortyEight
run assertPow48Call
bind pow48Result Bool assertPow48Call
branchIf pow48Result smokeAssertionFailed

# nextPowerOfTwoForSignedInt64(100) == 128
const oneHundred CSignedInt64 100
const oneHundredTwentyEight CSignedInt64 128
call assertNextPow2Call nextPowerOfTwoForSignedInt64
arg assertNextPow2Call inputValue oneHundred
run assertNextPow2Call
bind nextPow2Result CSignedInt64 assertNextPow2Call
call checkNextPow2Call math.equalI64
arg checkNextPow2Call left nextPow2Result
arg checkNextPow2Call right oneHundredTwentyEight
run checkNextPow2Call
bind nextPow2Ok Bool checkNextPow2Call
branchIf nextPow2Ok nextPow2Holds
branch smokeAssertionFailed
label nextPow2Holds

# countDecimalDigitsInSignedInt64(12345) == 5
const twelveThousandThreeHundredFortyFive CSignedInt64 12345
const fiveDigitsExpected CSignedInt64 5
call assertDigitCountCall countDecimalDigitsInSignedInt64
arg assertDigitCountCall inputValue twelveThousandThreeHundredFortyFive
run assertDigitCountCall
bind digitCountResult CSignedInt64 assertDigitCountCall
call checkDigitCountCall math.equalI64
arg checkDigitCountCall left digitCountResult
arg checkDigitCountCall right fiveDigitsExpected
run checkDigitCountCall
bind digitCountOk Bool checkDigitCountCall
branchIf digitCountOk digitCountHolds
branch smokeAssertionFailed
label digitCountHolds

# isSignedInt64Even(10) == true
const tenInteger CSignedInt64 10
call assertEvenCall isSignedInt64Even
arg assertEvenCall inputValue tenInteger
run assertEvenCall
bind evenResult Bool assertEvenCall
branchIf evenResult evenHolds
branch smokeAssertionFailed
label evenHolds

# isSignedInt64Odd(10) == false
call assertOddCall isSignedInt64Odd
arg assertOddCall inputValue tenInteger
run assertOddCall
bind oddResult Bool assertOddCall
branchIf oddResult smokeAssertionFailed

# countSetBitsInSignedInt64(13) == 3  (0b1101)
const thirteen CSignedInt64 13
const threeBits CSignedInt64 3
call assertPopcountCall countSetBitsInSignedInt64
arg assertPopcountCall inputValue thirteen
run assertPopcountCall
bind popcountResult CSignedInt64 assertPopcountCall
call checkPopcountCall math.equalI64
arg checkPopcountCall left popcountResult
arg checkPopcountCall right threeBits
run checkPopcountCall
bind popcountOk Bool checkPopcountCall
branchIf popcountOk popcountHolds
branch smokeAssertionFailed
label popcountHolds

# countTrailingZeroBitsInSignedInt64(16) == 4
const sixteenInteger CSignedInt64 16
const fourTrailingZeros CSignedInt64 4
call assertCtzCall countTrailingZeroBitsInSignedInt64
arg assertCtzCall inputValue sixteenInteger
run assertCtzCall
bind ctzResult CSignedInt64 assertCtzCall
call checkCtzCall math.equalI64
arg checkCtzCall left ctzResult
arg checkCtzCall right fourTrailingZeros
run checkCtzCall
bind ctzOk Bool checkCtzCall
branchIf ctzOk ctzHolds
branch smokeAssertionFailed
label ctzHolds

# signOfSignedInt64(-5) == -1
const negativeFive CSignedInt64 -5
const negativeOne CSignedInt64 -1
call assertSignCall signOfSignedInt64
arg assertSignCall inputValue negativeFive
run assertSignCall
bind signResult CSignedInt64 assertSignCall
call checkSignCall math.equalI64
arg checkSignCall left signResult
arg checkSignCall right negativeOne
run checkSignCall
bind signOk Bool checkSignCall
branchIf signOk signHolds
branch smokeAssertionFailed
label signHolds

# absoluteDifferenceBetweenSignedInt64Values(10, 3) == 7
const threeForAbsDiff CSignedInt64 3
const sevenExpected CSignedInt64 7
call assertAbsDiffCall absoluteDifferenceBetweenSignedInt64Values
arg assertAbsDiffCall leftValue tenInteger
arg assertAbsDiffCall rightValue threeForAbsDiff
run assertAbsDiffCall
bind absDiffResult CSignedInt64 assertAbsDiffCall
call checkAbsDiffCall math.equalI64
arg checkAbsDiffCall left absDiffResult
arg checkAbsDiffCall right sevenExpected
run checkAbsDiffCall
bind absDiffOk Bool checkAbsDiffCall
branchIf absDiffOk absDiffHolds
branch smokeAssertionFailed
label absDiffHolds

# ============================================================
# Per-operation extended unit tests: covers ops the original smoke
# test omitted (countLeadingZeroBitsInSignedInt64, squareSignedInt64,
# cubeSignedInt64, isSignedInt64WithinInclusiveRange) plus boundary
# cases (zero, one, two) and property invariants (commutativity,
# round-trip) for ops already covered.
# ============================================================

const zeroSm CSignedInt64 0
const oneSm CSignedInt64 1
const twoSm CSignedInt64 2
const sixSm CSignedInt64 6
const negTenSm CSignedInt64 -10
const negTwoSm CSignedInt64 -2
const sixtyTwoSm CSignedInt64 62
const sixtyThreeSm CSignedInt64 63
const minusOneSm CSignedInt64 -1
const oneHundredFortyFourEx CSignedInt64 144

# integerSquareRoot boundary: sqrt(0) == 0
call sqrtZeroCall integerSquareRootSignedInt64
arg sqrtZeroCall inputValue zeroSm
run sqrtZeroCall
bind sqrtZeroResult CSignedInt64 sqrtZeroCall
call checkSqrtZeroCall math.equalI64
arg checkSqrtZeroCall left sqrtZeroResult
arg checkSqrtZeroCall right zeroSm
run checkSqrtZeroCall
bind sqrtZeroOk Bool checkSqrtZeroCall
branchIf sqrtZeroOk sqrtZeroHolds
branch smokeAssertionFailed
label sqrtZeroHolds

# integerSquareRoot boundary: sqrt(1) == 1
call sqrtOneCall integerSquareRootSignedInt64
arg sqrtOneCall inputValue oneSm
run sqrtOneCall
bind sqrtOneResult CSignedInt64 sqrtOneCall
call checkSqrtOneCall math.equalI64
arg checkSqrtOneCall left sqrtOneResult
arg checkSqrtOneCall right oneSm
run checkSqrtOneCall
bind sqrtOneOk Bool checkSqrtOneCall
branchIf sqrtOneOk sqrtOneHolds
branch smokeAssertionFailed
label sqrtOneHolds

# integerSquareRoot negative: sqrt(-10) == 0 (clamps to zero)
call sqrtNegCall integerSquareRootSignedInt64
arg sqrtNegCall inputValue negTenSm
run sqrtNegCall
bind sqrtNegResult CSignedInt64 sqrtNegCall
call checkSqrtNegCall math.equalI64
arg checkSqrtNegCall left sqrtNegResult
arg checkSqrtNegCall right zeroSm
run checkSqrtNegCall
bind sqrtNegOk Bool checkSqrtNegCall
branchIf sqrtNegOk sqrtNegHolds
branch smokeAssertionFailed
label sqrtNegHolds

# factorial(0) == 1 (convention)
call facZeroCall factorialSignedInt64
arg facZeroCall inputValue zeroSm
run facZeroCall
bind facZeroResult CSignedInt64 facZeroCall
call checkFacZeroCall math.equalI64
arg checkFacZeroCall left facZeroResult
arg checkFacZeroCall right oneSm
run checkFacZeroCall
bind facZeroOk Bool checkFacZeroCall
branchIf facZeroOk facZeroHolds
branch smokeAssertionFailed
label facZeroHolds

# factorial(1) == 1
call facOneCall factorialSignedInt64
arg facOneCall inputValue oneSm
run facOneCall
bind facOneResult CSignedInt64 facOneCall
call checkFacOneCall math.equalI64
arg checkFacOneCall left facOneResult
arg checkFacOneCall right oneSm
run checkFacOneCall
bind facOneOk Bool checkFacOneCall
branchIf facOneOk facOneHolds
branch smokeAssertionFailed
label facOneHolds

# factorial(3) == 6
call facThreeCall factorialSignedInt64
arg facThreeCall inputValue threeForAbsDiff
run facThreeCall
bind facThreeResult CSignedInt64 facThreeCall
call checkFacThreeCall math.equalI64
arg checkFacThreeCall left facThreeResult
arg checkFacThreeCall right sixSm
run checkFacThreeCall
bind facThreeOk Bool checkFacThreeCall
branchIf facThreeOk facThreeHolds
branch smokeAssertionFailed
label facThreeHolds

# isPrime(2) == true (smallest prime)
call primeTwoCall isSignedInt64Prime
arg primeTwoCall inputValue twoSm
run primeTwoCall
bind primeTwoResult Bool primeTwoCall
branchIf primeTwoResult primeTwoHolds
branch smokeAssertionFailed
label primeTwoHolds

# isPrime(1) == false
call primeOneCall isSignedInt64Prime
arg primeOneCall inputValue oneSm
run primeOneCall
bind primeOneResult Bool primeOneCall
branchIf primeOneResult smokeAssertionFailed

# isPrime(0) == false
call primeZeroCall isSignedInt64Prime
arg primeZeroCall inputValue zeroSm
run primeZeroCall
bind primeZeroResult Bool primeZeroCall
branchIf primeZeroResult smokeAssertionFailed

# isPowerOfTwo(1) == true (2^0)
call powOneCall isSignedInt64PowerOfTwo
arg powOneCall inputValue oneSm
run powOneCall
bind powOneResult Bool powOneCall
branchIf powOneResult powOneHolds
branch smokeAssertionFailed
label powOneHolds

# isPowerOfTwo(0) == false
call powZeroCall isSignedInt64PowerOfTwo
arg powZeroCall inputValue zeroSm
run powZeroCall
bind powZeroResult Bool powZeroCall
branchIf powZeroResult smokeAssertionFailed

# isPowerOfTwo(-4) == false (negatives are never powers of two)
call powNegCall isSignedInt64PowerOfTwo
arg powNegCall inputValue negTenSm
run powNegCall
bind powNegResult Bool powNegCall
branchIf powNegResult smokeAssertionFailed

# nextPowerOfTwo(1) == 1 (already power of 2)
call nextPow1Call nextPowerOfTwoForSignedInt64
arg nextPow1Call inputValue oneSm
run nextPow1Call
bind nextPow1Result CSignedInt64 nextPow1Call
call checkNextPow1Call math.equalI64
arg checkNextPow1Call left nextPow1Result
arg checkNextPow1Call right oneSm
run checkNextPow1Call
bind nextPow1Ok Bool checkNextPow1Call
branchIf nextPow1Ok nextPow1Holds
branch smokeAssertionFailed
label nextPow1Holds

# nextPowerOfTwo(0) == 1
call nextPow0Call nextPowerOfTwoForSignedInt64
arg nextPow0Call inputValue zeroSm
run nextPow0Call
bind nextPow0Result CSignedInt64 nextPow0Call
call checkNextPow0Call math.equalI64
arg checkNextPow0Call left nextPow0Result
arg checkNextPow0Call right oneSm
run checkNextPow0Call
bind nextPow0Ok Bool checkNextPow0Call
branchIf nextPow0Ok nextPow0Holds
branch smokeAssertionFailed
label nextPow0Holds

# countDecimalDigits(0) == 1
call digitsZeroCall countDecimalDigitsInSignedInt64
arg digitsZeroCall inputValue zeroSm
run digitsZeroCall
bind digitsZeroResult CSignedInt64 digitsZeroCall
call checkDigitsZeroCall math.equalI64
arg checkDigitsZeroCall left digitsZeroResult
arg checkDigitsZeroCall right oneSm
run checkDigitsZeroCall
bind digitsZeroOk Bool checkDigitsZeroCall
branchIf digitsZeroOk digitsZeroHolds
branch smokeAssertionFailed
label digitsZeroHolds

# countDecimalDigits(-99) == 2 (negatives count by absolute value)
const negNinetyNineSm CSignedInt64 -99
call digitsNegCall countDecimalDigitsInSignedInt64
arg digitsNegCall inputValue negNinetyNineSm
run digitsNegCall
bind digitsNegResult CSignedInt64 digitsNegCall
call checkDigitsNegCall math.equalI64
arg checkDigitsNegCall left digitsNegResult
arg checkDigitsNegCall right twoSm
run checkDigitsNegCall
bind digitsNegOk Bool checkDigitsNegCall
branchIf digitsNegOk digitsNegHolds
branch smokeAssertionFailed
label digitsNegHolds

# isEven(0) == true
call evenZeroCall isSignedInt64Even
arg evenZeroCall inputValue zeroSm
run evenZeroCall
bind evenZeroResult Bool evenZeroCall
branchIf evenZeroResult evenZeroHolds
branch smokeAssertionFailed
label evenZeroHolds

# isOdd(7) == true
call oddSevenCall isSignedInt64Odd
arg oddSevenCall inputValue sevenExpected
run oddSevenCall
bind oddSevenResult Bool oddSevenCall
branchIf oddSevenResult oddSevenHolds
branch smokeAssertionFailed
label oddSevenHolds

# countSetBits(0) == 0
call popcountZeroCall countSetBitsInSignedInt64
arg popcountZeroCall inputValue zeroSm
run popcountZeroCall
bind popcountZeroResult CSignedInt64 popcountZeroCall
call checkPopcountZeroCall math.equalI64
arg checkPopcountZeroCall left popcountZeroResult
arg checkPopcountZeroCall right zeroSm
run checkPopcountZeroCall
bind popcountZeroOk Bool checkPopcountZeroCall
branchIf popcountZeroOk popcountZeroHolds
branch smokeAssertionFailed
label popcountZeroHolds

# countSetBits(1) == 1
call popcountOneCall countSetBitsInSignedInt64
arg popcountOneCall inputValue oneSm
run popcountOneCall
bind popcountOneResult CSignedInt64 popcountOneCall
call checkPopcountOneCall math.equalI64
arg checkPopcountOneCall left popcountOneResult
arg checkPopcountOneCall right oneSm
run checkPopcountOneCall
bind popcountOneOk Bool checkPopcountOneCall
branchIf popcountOneOk popcountOneHolds
branch smokeAssertionFailed
label popcountOneHolds

# countTrailingZeros(0) == 64 (matches __builtin_ctzll)
const sixtyFourSm CSignedInt64 64
call ctzZeroCall countTrailingZeroBitsInSignedInt64
arg ctzZeroCall inputValue zeroSm
run ctzZeroCall
bind ctzZeroResult CSignedInt64 ctzZeroCall
call checkCtzZeroCall math.equalI64
arg checkCtzZeroCall left ctzZeroResult
arg checkCtzZeroCall right sixtyFourSm
run checkCtzZeroCall
bind ctzZeroOk Bool checkCtzZeroCall
branchIf ctzZeroOk ctzZeroHolds
branch smokeAssertionFailed
label ctzZeroHolds

# countTrailingZeros(1) == 0
call ctzOneCall countTrailingZeroBitsInSignedInt64
arg ctzOneCall inputValue oneSm
run ctzOneCall
bind ctzOneResult CSignedInt64 ctzOneCall
call checkCtzOneCall math.equalI64
arg checkCtzOneCall left ctzOneResult
arg checkCtzOneCall right zeroSm
run checkCtzOneCall
bind ctzOneOk Bool checkCtzOneCall
branchIf ctzOneOk ctzOneHolds
branch smokeAssertionFailed
label ctzOneHolds

# sign(0) == 0
call signZeroCall signOfSignedInt64
arg signZeroCall inputValue zeroSm
run signZeroCall
bind signZeroResult CSignedInt64 signZeroCall
call checkSignZeroCall math.equalI64
arg checkSignZeroCall left signZeroResult
arg checkSignZeroCall right zeroSm
run checkSignZeroCall
bind signZeroOk Bool checkSignZeroCall
branchIf signZeroOk signZeroHolds
branch smokeAssertionFailed
label signZeroHolds

# sign(42) == 1
const fortyTwoSm CSignedInt64 42
call signPosCall signOfSignedInt64
arg signPosCall inputValue fortyTwoSm
run signPosCall
bind signPosResult CSignedInt64 signPosCall
call checkSignPosCall math.equalI64
arg checkSignPosCall left signPosResult
arg checkSignPosCall right oneSm
run checkSignPosCall
bind signPosOk Bool checkSignPosCall
branchIf signPosOk signPosHolds
branch smokeAssertionFailed
label signPosHolds

# absDiff symmetry: absDiff(3, 10) == absDiff(10, 3)
call absDiffSymCall absoluteDifferenceBetweenSignedInt64Values
arg absDiffSymCall leftValue threeForAbsDiff
arg absDiffSymCall rightValue tenInteger
run absDiffSymCall
bind absDiffSymResult CSignedInt64 absDiffSymCall
call checkAbsDiffSymCall math.equalI64
arg checkAbsDiffSymCall left absDiffSymResult
arg checkAbsDiffSymCall right sevenExpected
run checkAbsDiffSymCall
bind absDiffSymOk Bool checkAbsDiffSymCall
branchIf absDiffSymOk absDiffSymHolds
branch smokeAssertionFailed
label absDiffSymHolds

# === countLeadingZeroBitsInSignedInt64 (was untested) ===
# clz(0) == 64
call clzZeroCall countLeadingZeroBitsInSignedInt64
arg clzZeroCall inputValue zeroSm
run clzZeroCall
bind clzZeroResult CSignedInt64 clzZeroCall
call checkClzZeroCall math.equalI64
arg checkClzZeroCall left clzZeroResult
arg checkClzZeroCall right sixtyFourSm
run checkClzZeroCall
bind clzZeroOk Bool checkClzZeroCall
branchIf clzZeroOk clzZeroHolds
branch smokeAssertionFailed
label clzZeroHolds

# clz(1) == 63 (one bit set in position 0; 63 zeros above it)
call clzOneCall countLeadingZeroBitsInSignedInt64
arg clzOneCall inputValue oneSm
run clzOneCall
bind clzOneResult CSignedInt64 clzOneCall
call checkClzOneCall math.equalI64
arg checkClzOneCall left clzOneResult
arg checkClzOneCall right sixtyThreeSm
run checkClzOneCall
bind clzOneOk Bool checkClzOneCall
branchIf clzOneOk clzOneHolds
branch smokeAssertionFailed
label clzOneHolds

# clz(2) == 62
call clzTwoCall countLeadingZeroBitsInSignedInt64
arg clzTwoCall inputValue twoSm
run clzTwoCall
bind clzTwoResult CSignedInt64 clzTwoCall
call checkClzTwoCall math.equalI64
arg checkClzTwoCall left clzTwoResult
arg checkClzTwoCall right sixtyTwoSm
run checkClzTwoCall
bind clzTwoOk Bool checkClzTwoCall
branchIf clzTwoOk clzTwoHolds
branch smokeAssertionFailed
label clzTwoHolds

# === squareSignedInt64 (was untested) ===
# square(0) == 0
call sqZeroCall squareSignedInt64
arg sqZeroCall inputValue zeroSm
run sqZeroCall
bind sqZeroResult CSignedInt64 sqZeroCall
call checkSqZeroCall math.equalI64
arg checkSqZeroCall left sqZeroResult
arg checkSqZeroCall right zeroSm
run checkSqZeroCall
bind sqZeroOk Bool checkSqZeroCall
branchIf sqZeroOk sqZeroHolds
branch smokeAssertionFailed
label sqZeroHolds

# square(12) == 144 (round-trip with sqrt above)
call sqTwelveCall squareSignedInt64
arg sqTwelveCall inputValue twelveExpected
run sqTwelveCall
bind sqTwelveResult CSignedInt64 sqTwelveCall
call checkSqTwelveCall math.equalI64
arg checkSqTwelveCall left sqTwelveResult
arg checkSqTwelveCall right oneHundredFortyFourEx
run checkSqTwelveCall
bind sqTwelveOk Bool checkSqTwelveCall
branchIf sqTwelveOk sqTwelveHolds
branch smokeAssertionFailed
label sqTwelveHolds

# square(-5) == 25 (sign-insensitive)
const twentyFiveSm CSignedInt64 25
call sqNegCall squareSignedInt64
arg sqNegCall inputValue negativeFive
run sqNegCall
bind sqNegResult CSignedInt64 sqNegCall
call checkSqNegCall math.equalI64
arg checkSqNegCall left sqNegResult
arg checkSqNegCall right twentyFiveSm
run checkSqNegCall
bind sqNegOk Bool checkSqNegCall
branchIf sqNegOk sqNegHolds
branch smokeAssertionFailed
label sqNegHolds

# === cubeSignedInt64 (was untested) ===
# cube(0) == 0
call cubeZeroCall cubeSignedInt64
arg cubeZeroCall inputValue zeroSm
run cubeZeroCall
bind cubeZeroResult CSignedInt64 cubeZeroCall
call checkCubeZeroCall math.equalI64
arg checkCubeZeroCall left cubeZeroResult
arg checkCubeZeroCall right zeroSm
run checkCubeZeroCall
bind cubeZeroOk Bool checkCubeZeroCall
branchIf cubeZeroOk cubeZeroHolds
branch smokeAssertionFailed
label cubeZeroHolds

# cube(3) == 27
const twentySevenSm CSignedInt64 27
call cubeThreeCall cubeSignedInt64
arg cubeThreeCall inputValue threeForAbsDiff
run cubeThreeCall
bind cubeThreeResult CSignedInt64 cubeThreeCall
call checkCubeThreeCall math.equalI64
arg checkCubeThreeCall left cubeThreeResult
arg checkCubeThreeCall right twentySevenSm
run checkCubeThreeCall
bind cubeThreeOk Bool checkCubeThreeCall
branchIf cubeThreeOk cubeThreeHolds
branch smokeAssertionFailed
label cubeThreeHolds

# cube(-2) == -8 (sign-preserving)
const negEightSm CSignedInt64 -8
call cubeNegCall cubeSignedInt64
arg cubeNegCall inputValue negTwoSm
run cubeNegCall
bind cubeNegResult CSignedInt64 cubeNegCall
call checkCubeNegCall math.equalI64
arg checkCubeNegCall left cubeNegResult
arg checkCubeNegCall right negEightSm
run checkCubeNegCall
bind cubeNegOk Bool checkCubeNegCall
branchIf cubeNegOk cubeNegHolds
branch smokeAssertionFailed
label cubeNegHolds

# === isSignedInt64WithinInclusiveRange (was untested) ===
# 5 in [0, 10] == true
call rangeInsideCall isSignedInt64WithinInclusiveRange
arg rangeInsideCall inputValue fiveInputForFactorial
arg rangeInsideCall lowerBound zeroSm
arg rangeInsideCall upperBound tenInteger
run rangeInsideCall
bind rangeInsideResult Bool rangeInsideCall
branchIf rangeInsideResult rangeInsideHolds
branch smokeAssertionFailed
label rangeInsideHolds

# 0 in [0, 10] == true (lower boundary inclusive)
call rangeLowerCall isSignedInt64WithinInclusiveRange
arg rangeLowerCall inputValue zeroSm
arg rangeLowerCall lowerBound zeroSm
arg rangeLowerCall upperBound tenInteger
run rangeLowerCall
bind rangeLowerResult Bool rangeLowerCall
branchIf rangeLowerResult rangeLowerHolds
branch smokeAssertionFailed
label rangeLowerHolds

# 10 in [0, 10] == true (upper boundary inclusive)
call rangeUpperCall isSignedInt64WithinInclusiveRange
arg rangeUpperCall inputValue tenInteger
arg rangeUpperCall lowerBound zeroSm
arg rangeUpperCall upperBound tenInteger
run rangeUpperCall
bind rangeUpperResult Bool rangeUpperCall
branchIf rangeUpperResult rangeUpperHolds
branch smokeAssertionFailed
label rangeUpperHolds

# -1 in [0, 10] == false (below lower)
call rangeBelowCall isSignedInt64WithinInclusiveRange
arg rangeBelowCall inputValue minusOneSm
arg rangeBelowCall lowerBound zeroSm
arg rangeBelowCall upperBound tenInteger
run rangeBelowCall
bind rangeBelowResult Bool rangeBelowCall
branchIf rangeBelowResult smokeAssertionFailed

# 11 in [0, 10] == false (above upper)
const elevenSm CSignedInt64 11
call rangeAboveCall isSignedInt64WithinInclusiveRange
arg rangeAboveCall inputValue elevenSm
arg rangeAboveCall lowerBound zeroSm
arg rangeAboveCall upperBound tenInteger
run rangeAboveCall
bind rangeAboveResult Bool rangeAboveCall
branchIf rangeAboveResult smokeAssertionFailed

# Property: sqrt(square(x)) == x for x >= 0
call squareForRoundTripCall squareSignedInt64
arg squareForRoundTripCall inputValue twelveExpected
run squareForRoundTripCall
bind squareForRoundTripResult CSignedInt64 squareForRoundTripCall
call sqrtAfterSquareCall integerSquareRootSignedInt64
arg sqrtAfterSquareCall inputValue squareForRoundTripResult
run sqrtAfterSquareCall
bind sqrtAfterSquareResult CSignedInt64 sqrtAfterSquareCall
call checkRoundTripSquareSqrtCall math.equalI64
arg checkRoundTripSquareSqrtCall left sqrtAfterSquareResult
arg checkRoundTripSquareSqrtCall right twelveExpected
run checkRoundTripSquareSqrtCall
bind roundTripSquareSqrtOk Bool checkRoundTripSquareSqrtCall
branchIf roundTripSquareSqrtOk roundTripSquareSqrtHolds
branch smokeAssertionFailed
label roundTripSquareSqrtHolds

const successMessageText CNullTerminatedByteString "OK"
call writeSuccessLineCall console.writeLine
arg writeSuccessLineCall console console
arg writeSuccessLineCall text successMessageText
run writeSuccessLineCall
ignoreOk writeSuccessLineCall CSignedInt32
bindError consoleWriteResultError CSignedInt32 writeSuccessLineCall
branchIfError writeSuccessLineCall consoleWriteFailedHandler
const exitOkCode ExitCode 0
returnOk exitOkCode

# Failure leg: surface the raw negative CSignedInt32 from
# console.writeLine as the cause attached to the typed
# MainError.ConsoleWriteFailed variant.
label consoleWriteFailedHandler
makeError consoleWriteFailedFailure MainError.ConsoleWriteFailed consoleWriteResultError
returnError consoleWriteFailedFailure
label smokeAssertionFailed
makeError mathSmokeFailure MainError.MathSmokeAssertionFailed
returnError mathSmokeFailure
