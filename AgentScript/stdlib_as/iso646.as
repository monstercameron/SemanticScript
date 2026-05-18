# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <iso646.h>-style logical keywords
# ============================================================
#
# # rationale: C's <iso646.h> defines `and`, `or`, `not`, `xor`,
#   `compl`, `bitand`, `bitor`, `not_eq` as macro spellings of C
#   operators. AgentScript has no macro expansion, so this module
#   exposes each as a real operation. The refined surface returns
#   Bool (not CSignedInt32 0/1) and reads its inputs as CSignedInt64
#   integers — the keyword operates on the "truth" of an integer
#   (zero vs non-zero), matching C semantics exactly.
#
# # invariant: every operation here is total. The result of "non-zero
#   integer truth" is encoded in Bool, eliminating the C convention
#   of "any non-zero" for inputs while normalizing the output.
#
# # security: pure value-level math; no allocation; no I/O.
#
# # timing: at most two `icmp` operations and one branch per call.
#
# # observability: no logs or metrics.
#
# Operations exposed:
#   evaluateIso646AndKeyword(leftValue, rightValue)      -> Bool
#   evaluateIso646OrKeyword(leftValue, rightValue)       -> Bool
#   evaluateIso646NotKeyword(inputValue)                 -> Bool
#   evaluateIso646XorKeyword(leftValue, rightValue)      -> Bool
#   evaluateIso646EqualKeyword(leftValue, rightValue)    -> Bool
#   evaluateIso646NotEqualKeyword(leftValue, rightValue) -> Bool

project StdIso646
target console
runtime AgentRuntime 0.1
entry console evaluateIso646AndKeyword

# Pure-module file: smoke + extended tests live in
# stdlib_as/iso646.test.as.


domainLiteral integerZeroBoundaryValue CSignedInt64 0
domainLiteralTrust integerZeroBoundaryValue trustedStaticLiteral

# section iso646.logicalKeywords
# rationale: integer-truth combinators that return Bool.

operation evaluateIso646AndKeyword
input evaluateIso646AndKeyword leftValue CSignedInt64
input evaluateIso646AndKeyword rightValue CSignedInt64
output evaluateIso646AndKeyword Bool
memoryHeap evaluateIso646AndKeyword no
async evaluateIso646AndKeyword no
purpose evaluateIso646AndKeyword "Returns true when both inputs are non-zero (mirrors C's 'and' keyword applied to integers)."
invariant evaluateIso646AndKeyword "Commutative and associative under integer truth semantics."
guarantee evaluateIso646AndKeyword "Total."
label startEvaluateIso646AndKeyword
call detectLeftIsZeroCall math.equalI64
arg detectLeftIsZeroCall left leftValue
arg detectLeftIsZeroCall right integerZeroBoundaryValue
run detectLeftIsZeroCall
bind leftIsZero Bool detectLeftIsZeroCall
branchIf leftIsZero returnAndFalse
call detectRightIsZeroCall math.equalI64
arg detectRightIsZeroCall left rightValue
arg detectRightIsZeroCall right integerZeroBoundaryValue
run detectRightIsZeroCall
bind rightIsZero Bool detectRightIsZeroCall
branchIf rightIsZero returnAndFalse
const andTrueResult Bool true
returnValue andTrueResult
label returnAndFalse
const andFalseResult Bool false
returnValue andFalseResult

operation evaluateIso646OrKeyword
input evaluateIso646OrKeyword leftValue CSignedInt64
input evaluateIso646OrKeyword rightValue CSignedInt64
output evaluateIso646OrKeyword Bool
memoryHeap evaluateIso646OrKeyword no
async evaluateIso646OrKeyword no
purpose evaluateIso646OrKeyword "Returns true when at least one input is non-zero (mirrors C's 'or' keyword)."
invariant evaluateIso646OrKeyword "Commutative and associative under integer truth semantics."
guarantee evaluateIso646OrKeyword "Total."
label startEvaluateIso646OrKeyword
call detectLeftIsNonZeroCall math.notEqualI64
arg detectLeftIsNonZeroCall left leftValue
arg detectLeftIsNonZeroCall right integerZeroBoundaryValue
run detectLeftIsNonZeroCall
bind leftIsNonZero Bool detectLeftIsNonZeroCall
branchIf leftIsNonZero returnOrTrue
call detectRightIsNonZeroCall math.notEqualI64
arg detectRightIsNonZeroCall left rightValue
arg detectRightIsNonZeroCall right integerZeroBoundaryValue
run detectRightIsNonZeroCall
bind rightIsNonZero Bool detectRightIsNonZeroCall
branchIf rightIsNonZero returnOrTrue
const orFalseResult Bool false
returnValue orFalseResult
label returnOrTrue
const orTrueResult Bool true
returnValue orTrueResult

operation evaluateIso646NotKeyword
input evaluateIso646NotKeyword inputValue CSignedInt64
output evaluateIso646NotKeyword Bool
memoryHeap evaluateIso646NotKeyword no
async evaluateIso646NotKeyword no
purpose evaluateIso646NotKeyword "Returns true when the input is zero (mirrors C's 'not' keyword)."
invariant evaluateIso646NotKeyword "Involutive over Bool: evaluateIso646NotKeyword(evaluateIso646NotKeyword(x)) == truthOf(x)."
guarantee evaluateIso646NotKeyword "Total."
label startEvaluateIso646NotKeyword
call detectInputIsZeroCall math.equalI64
arg detectInputIsZeroCall left inputValue
arg detectInputIsZeroCall right integerZeroBoundaryValue
run detectInputIsZeroCall
bind inputIsZero Bool detectInputIsZeroCall
returnValue inputIsZero

operation evaluateIso646XorKeyword
input evaluateIso646XorKeyword leftValue CSignedInt64
input evaluateIso646XorKeyword rightValue CSignedInt64
output evaluateIso646XorKeyword Bool
memoryHeap evaluateIso646XorKeyword no
async evaluateIso646XorKeyword no
purpose evaluateIso646XorKeyword "Returns true when exactly one input is non-zero (logical XOR over integer truth)."
invariant evaluateIso646XorKeyword "Self-inverse: evaluateIso646XorKeyword(x, x) == false for every x."
guarantee evaluateIso646XorKeyword "Total."
label startEvaluateIso646XorKeyword
call leftXorTruthCall math.notEqualI64
arg leftXorTruthCall left leftValue
arg leftXorTruthCall right integerZeroBoundaryValue
run leftXorTruthCall
bind leftXorTruth Bool leftXorTruthCall
call rightXorTruthCall math.notEqualI64
arg rightXorTruthCall left rightValue
arg rightXorTruthCall right integerZeroBoundaryValue
run rightXorTruthCall
bind rightXorTruth Bool rightXorTruthCall
call detectXorOperandsDifferCall math.notEqualI64
arg detectXorOperandsDifferCall left leftXorTruth
arg detectXorOperandsDifferCall right rightXorTruth
run detectXorOperandsDifferCall
bind xorOperandsDiffer Bool detectXorOperandsDifferCall
returnValue xorOperandsDiffer

operation evaluateIso646EqualKeyword
input evaluateIso646EqualKeyword leftValue CSignedInt64
input evaluateIso646EqualKeyword rightValue CSignedInt64
output evaluateIso646EqualKeyword Bool
memoryHeap evaluateIso646EqualKeyword no
async evaluateIso646EqualKeyword no
purpose evaluateIso646EqualKeyword "Returns true when the two integer inputs are bitwise equal."
invariant evaluateIso646EqualKeyword "Symmetric; reflexive."
guarantee evaluateIso646EqualKeyword "Total."
label startEvaluateIso646EqualKeyword
call detectEqualCall math.equalI64
arg detectEqualCall left leftValue
arg detectEqualCall right rightValue
run detectEqualCall
bind valuesEqual Bool detectEqualCall
returnValue valuesEqual

operation evaluateIso646NotEqualKeyword
input evaluateIso646NotEqualKeyword leftValue CSignedInt64
input evaluateIso646NotEqualKeyword rightValue CSignedInt64
output evaluateIso646NotEqualKeyword Bool
memoryHeap evaluateIso646NotEqualKeyword no
async evaluateIso646NotEqualKeyword no
purpose evaluateIso646NotEqualKeyword "Returns true when the two integer inputs differ."
invariant evaluateIso646NotEqualKeyword "Symmetric; irreflexive."
guarantee evaluateIso646NotEqualKeyword "Total."
label startEvaluateIso646NotEqualKeyword
call detectNotEqualCall math.notEqualI64
arg detectNotEqualCall left leftValue
arg detectNotEqualCall right rightValue
run detectNotEqualCall
bind valuesDiffer Bool detectNotEqualCall
returnValue valuesDiffer

