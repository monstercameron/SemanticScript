# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: native Bool helpers
# ============================================================
#
# # rationale: C's <stdbool.h> existed because C added Bool late and
#   needed an integer compatibility layer. AgentScript has Bool as a
#   first-class primitive (`Bool` = LLVM i1, see AST.md §5), so this
#   module exposes total Boolean combinators returning Bool directly.
#   Two ABI-bridge ops translate between Bool and CSignedInt32 0/1
#   for FFI calls that still expect the C contract.
#
# # invariant: every operation in this module is total — no input
#   combination produces a failure. That property is encoded in the
#   `output op Bool` shape (no Result wrapper) and the absence of any
#   `*Error` domain.
#
# # security: pure value-level computation; no effects; no allocation;
#   no observable side channel beyond execution time, which is constant
#   per call (no branches over secret-dependent data).
#
# # timing: each combinator is O(1) — at most two LLVM `xor`/`and`/`or`
#   instructions on i1.
#
# # observability: callers are responsible for any tracing; this module
#   emits no logs, no metrics.
#
# Operations exposed:
#   negateBoolean(valueToNegate)                              -> Bool
#   andBooleans(firstOperand, secondOperand)                  -> Bool
#   orBooleans(firstOperand, secondOperand)                   -> Bool
#   exclusiveOrBooleans(firstOperand, secondOperand)          -> Bool
#   areBooleansEquivalent(firstOperand, secondOperand)        -> Bool
#
# ABI bridges (only for C-FFI callers):
#   convertBooleanToCSignedInt32(sourceBoolean)               -> CSignedInt32
#   convertCSignedInt32ToBoolean(sourceCSignedInt32Value)     -> Bool

project StdBoolSelfTest
target console
runtime AgentRuntime 0.1
entry console main

# Typed error domain used only by the smoke test below. The library
# operations themselves are total and declare no errors.
error MainError
errorCase MainError BooleanSmokeAssertionFailed
errorCase MainError ConsoleWriteFailed

# section capability
# rationale: smoke-test main writes a single OK line to stdout.
capability stdoutWriteCapability console.stdout write

# Canonical Bool literal accessors declared as domain literals so
# downstream code can `arg X value canonicalBooleanTrue` without
# repeating the literal text. Kept at module scope per spec §11.
domainLiteral canonicalBooleanTrue Bool true
domainLiteralTrust canonicalBooleanTrue trustedStaticLiteral
domainLiteral canonicalBooleanFalse Bool false
domainLiteralTrust canonicalBooleanFalse trustedStaticLiteral

# section bool.core
# rationale: total Bool→Bool functions; no errors, no allocation.

# ----- negateBoolean -----
operation negateBoolean
input negateBoolean valueToNegate Bool
output negateBoolean Bool
memoryHeap negateBoolean no
async negateBoolean no
purpose negateBoolean "Returns the logical negation of valueToNegate (true→false, false→true)."
invariant negateBoolean "Involutive: negateBoolean(negateBoolean(x)) == x for every Bool x."
guarantee negateBoolean "Total: defined for every Bool input."
# rationale: implemented as equality test against false, which the
#   compiler lowers to a single `icmp eq i1 %v, 0` — the cheapest
#   i1-level negation without branching on a secret-dependent bit.
label startNegateBoolean
const falseSentinel Bool false
call detectInputIsFalseCall math.equalI64
arg detectInputIsFalseCall left valueToNegate
arg detectInputIsFalseCall right falseSentinel
run detectInputIsFalseCall
bind isInputCurrentlyFalse Bool detectInputIsFalseCall
returnValue isInputCurrentlyFalse

# ----- andBooleans -----
operation andBooleans
input andBooleans firstOperand Bool
input andBooleans secondOperand Bool
output andBooleans Bool
memoryHeap andBooleans no
async andBooleans no
purpose andBooleans "Logical AND of two Bool operands."
invariant andBooleans "Commutative: andBooleans(a, b) == andBooleans(b, a)."
invariant andBooleans "Associative: andBooleans(andBooleans(a, b), c) == andBooleans(a, andBooleans(b, c))."
guarantee andBooleans "Total: defined for every (Bool, Bool) input pair."
# warning: this lowering evaluates both operands. There is no
#   short-circuit form at this layer — callers that need lazy
#   evaluation should branch explicitly via `branchIf`.
label startAndBooleans
const falseShortCircuit Bool false
branchIf firstOperand bothOperandsLiveBranch
returnValue falseShortCircuit
label bothOperandsLiveBranch
returnValue secondOperand

# ----- orBooleans -----
operation orBooleans
input orBooleans firstOperand Bool
input orBooleans secondOperand Bool
output orBooleans Bool
memoryHeap orBooleans no
async orBooleans no
purpose orBooleans "Logical OR of two Bool operands."
invariant orBooleans "Commutative: orBooleans(a, b) == orBooleans(b, a)."
invariant orBooleans "Associative: orBooleans(orBooleans(a, b), c) == orBooleans(a, orBooleans(b, c))."
guarantee orBooleans "Total: defined for every (Bool, Bool) input pair."
# warning: both operands are always evaluated (see andBooleans rationale).
label startOrBooleans
const trueShortCircuit Bool true
branchIf firstOperand firstOperandTrueBranch
returnValue secondOperand
label firstOperandTrueBranch
returnValue trueShortCircuit

# ----- exclusiveOrBooleans -----
operation exclusiveOrBooleans
input exclusiveOrBooleans firstOperand Bool
input exclusiveOrBooleans secondOperand Bool
output exclusiveOrBooleans Bool
memoryHeap exclusiveOrBooleans no
async exclusiveOrBooleans no
purpose exclusiveOrBooleans "Returns true when exactly one operand is true (logical XOR)."
invariant exclusiveOrBooleans "Self-inverse: exclusiveOrBooleans(x, x) == false."
invariant exclusiveOrBooleans "Identity over false: exclusiveOrBooleans(x, false) == x."
guarantee exclusiveOrBooleans "Total: defined for every (Bool, Bool) input pair."
label startExclusiveOrBooleans
call detectDistinctOperandsCall math.notEqualI64
arg detectDistinctOperandsCall left firstOperand
arg detectDistinctOperandsCall right secondOperand
run detectDistinctOperandsCall
bind operandsDiffer Bool detectDistinctOperandsCall
returnValue operandsDiffer

# ----- areBooleansEquivalent -----
operation areBooleansEquivalent
input areBooleansEquivalent firstOperand Bool
input areBooleansEquivalent secondOperand Bool
output areBooleansEquivalent Bool
memoryHeap areBooleansEquivalent no
async areBooleansEquivalent no
purpose areBooleansEquivalent "Returns true when both operands hold the same value (logical equivalence / XNOR)."
invariant areBooleansEquivalent "Reflexive: areBooleansEquivalent(x, x) == true."
invariant areBooleansEquivalent "Symmetric: areBooleansEquivalent(a, b) == areBooleansEquivalent(b, a)."
guarantee areBooleansEquivalent "Total: defined for every (Bool, Bool) input pair."
label startAreBooleansEquivalent
call detectMatchingOperandsCall math.equalI64
arg detectMatchingOperandsCall left firstOperand
arg detectMatchingOperandsCall right secondOperand
run detectMatchingOperandsCall
bind operandsMatch Bool detectMatchingOperandsCall
returnValue operandsMatch

# section bool.abiBridge
# rationale: convert between Bool and the C-style 0/1 CSignedInt32 contract.

# ----- convertBooleanToCSignedInt32 -----
operation convertBooleanToCSignedInt32
input convertBooleanToCSignedInt32 sourceBoolean Bool
output convertBooleanToCSignedInt32 CSignedInt32
memoryHeap convertBooleanToCSignedInt32 no
async convertBooleanToCSignedInt32 no
purpose convertBooleanToCSignedInt32 "Widen a Bool (i1) to the canonical C 0/1 CSignedInt32 result FFI callers expect."
invariant convertBooleanToCSignedInt32 "Output is exactly 0 or 1; no other bit pattern is reachable."
guarantee convertBooleanToCSignedInt32 "Total: defined for every Bool input."
# security: zero-extension (not sign-extension) so a true Bool widens
#   to 1 not -1 — matches C `_Bool` ABI exactly and avoids the
#   sign-extension trap that bit a refined-syntax demo earlier in the
#   project.
label startConvertBooleanToCSignedInt32
const zeroCSignedInt32 CSignedInt32 0
const oneCSignedInt32 CSignedInt32 1
branchIf sourceBoolean returnCanonicalOne
returnValue zeroCSignedInt32
label returnCanonicalOne
returnValue oneCSignedInt32

# ----- convertCSignedInt32ToBoolean -----
operation convertCSignedInt32ToBoolean
input convertCSignedInt32ToBoolean sourceCSignedInt32Value CSignedInt32
output convertCSignedInt32ToBoolean Bool
memoryHeap convertCSignedInt32ToBoolean no
async convertCSignedInt32ToBoolean no
purpose convertCSignedInt32ToBoolean "Narrow a C-style 0/non-zero CSignedInt32 to Bool; any non-zero input yields true."
invariant convertCSignedInt32ToBoolean "Output is true iff sourceCSignedInt32Value is not equal to zero."
guarantee convertCSignedInt32ToBoolean "Total: defined for every CSignedInt32 input."
label startConvertCSignedInt32ToBoolean
const zeroComparisonOperand I64 0
call detectNonZeroInputCall math.notEqualI64
arg detectNonZeroInputCall left sourceCSignedInt32Value
arg detectNonZeroInputCall right zeroComparisonOperand
run detectNonZeroInputCall
bind sourceIsNonZero Bool detectNonZeroInputCall
returnValue sourceIsNonZero

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
