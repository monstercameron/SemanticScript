# ============================================================
# AGENTSCRIPT STDLIB TESTS: bool
# ============================================================
#
# Companion smoke + extended unit tests for stdlib_as/bool.as.
# Imports the bool module and asserts every exported combinator
# (negate / and / or / xor / equivalent / convertToCInt /
# convertFromCInt) plus involution / commutativity / de Morgan /
# round-trip property tests.
#
# Pattern: stdlib_as/foo.as ships pure-module operations only;
# stdlib_as/foo.test.as carries every smoke / unit test for it.

project StdBoolTest
target console
runtime AgentRuntime 0.1
entry console main

importModule bool

# Typed error domain used only by this smoke test. The library
# operations themselves are total and declare no errors.
error MainError
errorCase MainError BooleanSmokeAssertionFailed
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
purpose main "Smoke-test refined Bool combinators end-to-end. Prints OK then exits 0."
invariant main "Exit 0 when every assertion holds; returnError with BooleanSmokeAssertionFailed otherwise."
# observability: the success path writes the literal "OK\n" so a CI
#   diff can pin the expected output; the failure path is observable
#   through the non-zero exit code only.

label startMain

# Verify negateBoolean(false) == true.
call assertNegateFalseCall negateBoolean
arg assertNegateFalseCall valueToNegate canonicalBooleanFalse
run assertNegateFalseCall
bind negateFalseResult Bool assertNegateFalseCall
branchIf negateFalseResult negateFalseHolds
branch smokeAssertionFailed
label negateFalseHolds

# Verify andBooleans(true, true) == true.
call assertAndTrueTrueCall andBooleans
arg assertAndTrueTrueCall firstOperand canonicalBooleanTrue
arg assertAndTrueTrueCall secondOperand canonicalBooleanTrue
run assertAndTrueTrueCall
bind andTrueTrueResult Bool assertAndTrueTrueCall
branchIf andTrueTrueResult andTrueTrueHolds
branch smokeAssertionFailed
label andTrueTrueHolds

# Verify andBooleans(true, false) == false.
call assertAndTrueFalseCall andBooleans
arg assertAndTrueFalseCall firstOperand canonicalBooleanTrue
arg assertAndTrueFalseCall secondOperand canonicalBooleanFalse
run assertAndTrueFalseCall
bind andTrueFalseResult Bool assertAndTrueFalseCall
branchIf andTrueFalseResult smokeAssertionFailed

# Verify orBooleans(false, true) == true.
call assertOrFalseTrueCall orBooleans
arg assertOrFalseTrueCall firstOperand canonicalBooleanFalse
arg assertOrFalseTrueCall secondOperand canonicalBooleanTrue
run assertOrFalseTrueCall
bind orFalseTrueResult Bool assertOrFalseTrueCall
branchIf orFalseTrueResult orFalseTrueHolds
branch smokeAssertionFailed
label orFalseTrueHolds

# Verify exclusiveOrBooleans(true, false) == true.
call assertXorTrueFalseCall exclusiveOrBooleans
arg assertXorTrueFalseCall firstOperand canonicalBooleanTrue
arg assertXorTrueFalseCall secondOperand canonicalBooleanFalse
run assertXorTrueFalseCall
bind xorTrueFalseResult Bool assertXorTrueFalseCall
branchIf xorTrueFalseResult xorTrueFalseHolds
branch smokeAssertionFailed
label xorTrueFalseHolds

# Verify exclusiveOrBooleans(true, true) == false.
call assertXorTrueTrueCall exclusiveOrBooleans
arg assertXorTrueTrueCall firstOperand canonicalBooleanTrue
arg assertXorTrueTrueCall secondOperand canonicalBooleanTrue
run assertXorTrueTrueCall
bind xorTrueTrueResult Bool assertXorTrueTrueCall
branchIf xorTrueTrueResult smokeAssertionFailed

# Verify areBooleansEquivalent(true, true) == true.
call assertEquivTrueTrueCall areBooleansEquivalent
arg assertEquivTrueTrueCall firstOperand canonicalBooleanTrue
arg assertEquivTrueTrueCall secondOperand canonicalBooleanTrue
run assertEquivTrueTrueCall
bind equivTrueTrueResult Bool assertEquivTrueTrueCall
branchIf equivTrueTrueResult equivTrueTrueHolds
branch smokeAssertionFailed
label equivTrueTrueHolds

# Verify convertBooleanToCSignedInt32(true) == 1.
call convertTrueToIntCall convertBooleanToCSignedInt32
arg convertTrueToIntCall sourceBoolean canonicalBooleanTrue
run convertTrueToIntCall
bind trueAsCInt CSignedInt32 convertTrueToIntCall
const oneI32Expected CSignedInt32 1
call checkConvertTrueCall math.equalI64
arg checkConvertTrueCall left trueAsCInt
arg checkConvertTrueCall right oneI32Expected
run checkConvertTrueCall
bind convertTrueOk Bool checkConvertTrueCall
branchIf convertTrueOk convertTrueHolds
branch smokeAssertionFailed
label convertTrueHolds

# Verify convertCSignedInt32ToBoolean(0) == false.
const zeroI32Input CSignedInt32 0
call convertZeroToBoolCall convertCSignedInt32ToBoolean
arg convertZeroToBoolCall sourceCSignedInt32Value zeroI32Input
run convertZeroToBoolCall
bind zeroAsBool Bool convertZeroToBoolCall
branchIf zeroAsBool smokeAssertionFailed

# ============================================================
# Extended unit tests: missing cases (negate(true), and(false,false),
# convertBack(1)) plus involution, commutativity, and de Morgan
# property tests over the four Bool combinations.
# ============================================================

# negate(true) == false
call negateTrueCall negateBoolean
arg negateTrueCall valueToNegate canonicalBooleanTrue
run negateTrueCall
bind negateTrueResult Bool negateTrueCall
branchIf negateTrueResult smokeAssertionFailed
branch negateTrueHolds
label negateTrueHolds

# Involution: negate(negate(true)) == true
call invStep1Call negateBoolean
arg invStep1Call valueToNegate canonicalBooleanTrue
run invStep1Call
bind invStep1Result Bool invStep1Call
call invStep2Call negateBoolean
arg invStep2Call valueToNegate invStep1Result
run invStep2Call
bind invStep2Result Bool invStep2Call
branchIf invStep2Result invHolds
branch smokeAssertionFailed
label invHolds

# and(false, false) == false
call andFalseFalseCall andBooleans
arg andFalseFalseCall firstOperand canonicalBooleanFalse
arg andFalseFalseCall secondOperand canonicalBooleanFalse
run andFalseFalseCall
bind andFalseFalseResult Bool andFalseFalseCall
branchIf andFalseFalseResult smokeAssertionFailed
branch andFalseFalseHolds
label andFalseFalseHolds

# or(false, false) == false
call orFalseFalseCall orBooleans
arg orFalseFalseCall firstOperand canonicalBooleanFalse
arg orFalseFalseCall secondOperand canonicalBooleanFalse
run orFalseFalseCall
bind orFalseFalseResult Bool orFalseFalseCall
branchIf orFalseFalseResult smokeAssertionFailed
branch orFalseFalseHolds
label orFalseFalseHolds

# or(true, true) == true
call orTrueTrueCall orBooleans
arg orTrueTrueCall firstOperand canonicalBooleanTrue
arg orTrueTrueCall secondOperand canonicalBooleanTrue
run orTrueTrueCall
bind orTrueTrueResult Bool orTrueTrueCall
branchIf orTrueTrueResult orTrueTrueHolds
branch smokeAssertionFailed
label orTrueTrueHolds

# Commutativity: xor(true, false) == xor(false, true)
call xorTFCall exclusiveOrBooleans
arg xorTFCall firstOperand canonicalBooleanTrue
arg xorTFCall secondOperand canonicalBooleanFalse
run xorTFCall
bind xorTFResult Bool xorTFCall
call xorFTCall exclusiveOrBooleans
arg xorFTCall firstOperand canonicalBooleanFalse
arg xorFTCall secondOperand canonicalBooleanTrue
run xorFTCall
bind xorFTResult Bool xorFTCall
call xorCommutativeCall areBooleansEquivalent
arg xorCommutativeCall firstOperand xorTFResult
arg xorCommutativeCall secondOperand xorFTResult
run xorCommutativeCall
bind xorCommutativeResult Bool xorCommutativeCall
branchIf xorCommutativeResult xorCommHolds
branch smokeAssertionFailed
label xorCommHolds

# De Morgan: negate(and(true, false)) == or(negate(true), negate(false))
# = negate(false) == or(false, true)
# = true == true
call deMorganAndCall andBooleans
arg deMorganAndCall firstOperand canonicalBooleanTrue
arg deMorganAndCall secondOperand canonicalBooleanFalse
run deMorganAndCall
bind deMorganAndResult Bool deMorganAndCall
call deMorganLhsCall negateBoolean
arg deMorganLhsCall valueToNegate deMorganAndResult
run deMorganLhsCall
bind deMorganLhsResult Bool deMorganLhsCall
call deMorganNegFirstCall negateBoolean
arg deMorganNegFirstCall valueToNegate canonicalBooleanTrue
run deMorganNegFirstCall
bind deMorganNegFirstResult Bool deMorganNegFirstCall
call deMorganNegSecondCall negateBoolean
arg deMorganNegSecondCall valueToNegate canonicalBooleanFalse
run deMorganNegSecondCall
bind deMorganNegSecondResult Bool deMorganNegSecondCall
call deMorganRhsCall orBooleans
arg deMorganRhsCall firstOperand deMorganNegFirstResult
arg deMorganRhsCall secondOperand deMorganNegSecondResult
run deMorganRhsCall
bind deMorganRhsResult Bool deMorganRhsCall
call deMorganEquivCall areBooleansEquivalent
arg deMorganEquivCall firstOperand deMorganLhsResult
arg deMorganEquivCall secondOperand deMorganRhsResult
run deMorganEquivCall
bind deMorganEquivResult Bool deMorganEquivCall
branchIf deMorganEquivResult deMorganHolds
branch smokeAssertionFailed
label deMorganHolds

# convertBooleanToCSignedInt32(false) == 0
call convertFalseToIntCall convertBooleanToCSignedInt32
arg convertFalseToIntCall sourceBoolean canonicalBooleanFalse
run convertFalseToIntCall
bind falseAsCInt CSignedInt32 convertFalseToIntCall
call checkConvertFalseCall math.equalI64
arg checkConvertFalseCall left falseAsCInt
arg checkConvertFalseCall right zeroI32Input
run checkConvertFalseCall
bind convertFalseOk Bool checkConvertFalseCall
branchIf convertFalseOk convertFalseHolds
branch smokeAssertionFailed
label convertFalseHolds

# convertCSignedInt32ToBoolean(1) == true
call convertOneToBoolCall convertCSignedInt32ToBoolean
arg convertOneToBoolCall sourceCSignedInt32Value oneI32Expected
run convertOneToBoolCall
bind oneAsBool Bool convertOneToBoolCall
branchIf oneAsBool oneAsBoolHolds
branch smokeAssertionFailed
label oneAsBoolHolds

# Round trip: convertCSignedInt32ToBoolean(convertBooleanToCSignedInt32(true)) == true
call roundTripBoolToIntCall convertBooleanToCSignedInt32
arg roundTripBoolToIntCall sourceBoolean canonicalBooleanTrue
run roundTripBoolToIntCall
bind roundTripIntValue CSignedInt32 roundTripBoolToIntCall
call roundTripIntToBoolCall convertCSignedInt32ToBoolean
arg roundTripIntToBoolCall sourceCSignedInt32Value roundTripIntValue
run roundTripIntToBoolCall
bind roundTripBoolResult Bool roundTripIntToBoolCall
branchIf roundTripBoolResult roundTripBoolHolds
branch smokeAssertionFailed
label roundTripBoolHolds

# All assertions hold. Emit OK\n and exit 0.
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
makeError booleanSmokeFailure MainError.BooleanSmokeAssertionFailed
returnError booleanSmokeFailure
