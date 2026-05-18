# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <ctype.h>-style ASCII classifiers
# ============================================================
#
# # rationale: C's <ctype.h> returns nonzero/zero CSignedInt32 to model
#   truth. AgentScript has Bool, so every classifier here returns Bool
#   directly. The two case-mapping ops (`convertAsciiLetterCodeToUppercase`,
#   `convertAsciiLetterCodeToLowercase`) still return CSignedInt32 because
#   the output is an ASCII codepoint, not a truth value.
#
# # invariant: every operation is total. Predicates produce Bool with
#   no error path; case mappers produce CSignedInt32 in [0, 127] when
#   the input is a valid ASCII byte, and pass non-ASCII bytes through
#   unchanged so callers can decode without surprises.
#
# # security: pure value-level math; no allocation; no I/O; no
#   table lookups against attacker-controlled indices.
#
# # timing: at most a constant number of `icmp` + `add`/`sub`
#   operations per call. No data-dependent branches over secret bytes
#   beyond the standard ASCII range test.
#
# # observability: no logs, no metrics. Callers are responsible for
#   tracing high-frequency classification loops if needed.
#
# # warning: ASCII-only by design. Bytes >= 0x80 are not letters,
#   digits, etc. regardless of locale. UTF-8 callers must decode to
#   codepoints first.
#
# Predicate operations (all return Bool):
#   isAsciiDecimalDigitCode(characterCode)
#   isAsciiLowercaseLetterCode(characterCode)
#   isAsciiUppercaseLetterCode(characterCode)
#   isAsciiLetterCode(characterCode)
#   isAsciiLetterOrDigitCode(characterCode)
#   isAsciiHexDigitCode(characterCode)
#   isAsciiWhitespaceCode(characterCode)
#   isAsciiBlankCode(characterCode)
#   isAsciiControlCode(characterCode)
#   isAsciiPrintableCode(characterCode)
#   isAsciiGraphicalCode(characterCode)
#   isAsciiPunctuationCode(characterCode)
#
# Case-mapping operations (all return CSignedInt32):
#   convertAsciiLetterCodeToUppercase(characterCode)
#   convertAsciiLetterCodeToLowercase(characterCode)

project StdCtypeSelfTest
target console
runtime AgentRuntime 0.1
entry console main

error MainError
errorCase MainError CtypeSmokeAssertionFailed
errorCase MainError ConsoleWriteFailed

# section capability
# rationale: smoke-test main writes a single OK line to stdout.
capability stdoutWriteCapability console.stdout write

# Canonical ASCII boundary literals — declared once at module scope so
# every classifier references the same trusted source of truth.
domainLiteral asciiDigitZeroCode CSignedInt32 48
domainLiteralTrust asciiDigitZeroCode trustedStaticLiteral
domainLiteral asciiDigitNineCode CSignedInt32 57
domainLiteralTrust asciiDigitNineCode trustedStaticLiteral
domainLiteral asciiUppercaseACode CSignedInt32 65
domainLiteralTrust asciiUppercaseACode trustedStaticLiteral
domainLiteral asciiUppercaseFCode CSignedInt32 70
domainLiteralTrust asciiUppercaseFCode trustedStaticLiteral
domainLiteral asciiUppercaseZCode CSignedInt32 90
domainLiteralTrust asciiUppercaseZCode trustedStaticLiteral
domainLiteral asciiLowercaseACode CSignedInt32 97
domainLiteralTrust asciiLowercaseACode trustedStaticLiteral
domainLiteral asciiLowercaseFCode CSignedInt32 102
domainLiteralTrust asciiLowercaseFCode trustedStaticLiteral
domainLiteral asciiLowercaseZCode CSignedInt32 122
domainLiteralTrust asciiLowercaseZCode trustedStaticLiteral
domainLiteral asciiSpaceCode CSignedInt32 32
domainLiteralTrust asciiSpaceCode trustedStaticLiteral
domainLiteral asciiTabCode CSignedInt32 9
domainLiteralTrust asciiTabCode trustedStaticLiteral
domainLiteral asciiLineFeedCode CSignedInt32 10
domainLiteralTrust asciiLineFeedCode trustedStaticLiteral
domainLiteral asciiVerticalTabCode CSignedInt32 11
domainLiteralTrust asciiVerticalTabCode trustedStaticLiteral
domainLiteral asciiFormFeedCode CSignedInt32 12
domainLiteralTrust asciiFormFeedCode trustedStaticLiteral
domainLiteral asciiCarriageReturnCode CSignedInt32 13
domainLiteralTrust asciiCarriageReturnCode trustedStaticLiteral
domainLiteral asciiHighestControlCode CSignedInt32 31
domainLiteralTrust asciiHighestControlCode trustedStaticLiteral
domainLiteral asciiDeleteCode CSignedInt32 127
domainLiteralTrust asciiDeleteCode trustedStaticLiteral
domainLiteral asciiLowestPrintableCode CSignedInt32 32
domainLiteralTrust asciiLowestPrintableCode trustedStaticLiteral
domainLiteral asciiHighestPrintableCode CSignedInt32 126
domainLiteralTrust asciiHighestPrintableCode trustedStaticLiteral
domainLiteral asciiLowestGraphicalCode CSignedInt32 33
domainLiteralTrust asciiLowestGraphicalCode trustedStaticLiteral
domainLiteral asciiUppercaseLowercaseGap CSignedInt32 32
domainLiteralTrust asciiUppercaseLowercaseGap trustedStaticLiteral

# section ctype.digit
# rationale: numeric classifiers.

operation isAsciiDecimalDigitCode
input isAsciiDecimalDigitCode characterCode CSignedInt32
output isAsciiDecimalDigitCode Bool
memoryHeap isAsciiDecimalDigitCode no
memoryStackLimit isAsciiDecimalDigitCode 1024
async isAsciiDecimalDigitCode no
purpose isAsciiDecimalDigitCode "Returns true when characterCode is an ASCII decimal digit (0x30..0x39)."
invariant isAsciiDecimalDigitCode "Holds iff 48 <= characterCode <= 57."
guarantee isAsciiDecimalDigitCode "Total over the CSignedInt32 domain."
label startIsAsciiDecimalDigitCode
call detectBelowDigitRangeCall math.lessThanI64
arg detectBelowDigitRangeCall left characterCode
arg detectBelowDigitRangeCall right asciiDigitZeroCode
run detectBelowDigitRangeCall
bind belowDigitRange Bool detectBelowDigitRangeCall
branchIf belowDigitRange returnNotDigit
call detectAboveDigitRangeCall math.greaterThanI64
arg detectAboveDigitRangeCall left characterCode
arg detectAboveDigitRangeCall right asciiDigitNineCode
run detectAboveDigitRangeCall
bind aboveDigitRange Bool detectAboveDigitRangeCall
branchIf aboveDigitRange returnNotDigit
const isDigitTrue Bool true
returnValue isDigitTrue
label returnNotDigit
const isDigitFalse Bool false
returnValue isDigitFalse

# section ctype.letter
# rationale: alphabetic classifiers and case-aware variants.

operation isAsciiLowercaseLetterCode
input isAsciiLowercaseLetterCode characterCode CSignedInt32
output isAsciiLowercaseLetterCode Bool
memoryHeap isAsciiLowercaseLetterCode no
memoryStackLimit isAsciiLowercaseLetterCode 1024
async isAsciiLowercaseLetterCode no
purpose isAsciiLowercaseLetterCode "Returns true when characterCode is an ASCII lowercase letter (0x61..0x7A)."
invariant isAsciiLowercaseLetterCode "Holds iff 97 <= characterCode <= 122."
guarantee isAsciiLowercaseLetterCode "Total."
label startIsAsciiLowercaseLetterCode
call detectBelowLowercaseRangeCall math.lessThanI64
arg detectBelowLowercaseRangeCall left characterCode
arg detectBelowLowercaseRangeCall right asciiLowercaseACode
run detectBelowLowercaseRangeCall
bind belowLowercaseRange Bool detectBelowLowercaseRangeCall
branchIf belowLowercaseRange returnNotLowercase
call detectAboveLowercaseRangeCall math.greaterThanI64
arg detectAboveLowercaseRangeCall left characterCode
arg detectAboveLowercaseRangeCall right asciiLowercaseZCode
run detectAboveLowercaseRangeCall
bind aboveLowercaseRange Bool detectAboveLowercaseRangeCall
branchIf aboveLowercaseRange returnNotLowercase
const isLowercaseTrue Bool true
returnValue isLowercaseTrue
label returnNotLowercase
const isLowercaseFalse Bool false
returnValue isLowercaseFalse

operation isAsciiUppercaseLetterCode
input isAsciiUppercaseLetterCode characterCode CSignedInt32
output isAsciiUppercaseLetterCode Bool
memoryHeap isAsciiUppercaseLetterCode no
memoryStackLimit isAsciiUppercaseLetterCode 1024
async isAsciiUppercaseLetterCode no
purpose isAsciiUppercaseLetterCode "Returns true when characterCode is an ASCII uppercase letter (0x41..0x5A)."
invariant isAsciiUppercaseLetterCode "Holds iff 65 <= characterCode <= 90."
guarantee isAsciiUppercaseLetterCode "Total."
label startIsAsciiUppercaseLetterCode
call detectBelowUppercaseRangeCall math.lessThanI64
arg detectBelowUppercaseRangeCall left characterCode
arg detectBelowUppercaseRangeCall right asciiUppercaseACode
run detectBelowUppercaseRangeCall
bind belowUppercaseRange Bool detectBelowUppercaseRangeCall
branchIf belowUppercaseRange returnNotUppercase
call detectAboveUppercaseRangeCall math.greaterThanI64
arg detectAboveUppercaseRangeCall left characterCode
arg detectAboveUppercaseRangeCall right asciiUppercaseZCode
run detectAboveUppercaseRangeCall
bind aboveUppercaseRange Bool detectAboveUppercaseRangeCall
branchIf aboveUppercaseRange returnNotUppercase
const isUppercaseTrue Bool true
returnValue isUppercaseTrue
label returnNotUppercase
const isUppercaseFalse Bool false
returnValue isUppercaseFalse

operation isAsciiLetterCode
input isAsciiLetterCode characterCode CSignedInt32
output isAsciiLetterCode Bool
memoryHeap isAsciiLetterCode no
memoryStackLimit isAsciiLetterCode 1024
async isAsciiLetterCode no
purpose isAsciiLetterCode "Returns true when characterCode is an ASCII letter (upper or lower case)."
invariant isAsciiLetterCode "Equivalent to isAsciiUppercaseLetterCode(c) OR isAsciiLowercaseLetterCode(c)."
guarantee isAsciiLetterCode "Total."
label startIsAsciiLetterCode
call detectUppercaseCall isAsciiUppercaseLetterCode
arg detectUppercaseCall characterCode characterCode
run detectUppercaseCall
bind characterIsUppercase Bool detectUppercaseCall
branchIf characterIsUppercase returnIsLetter
call detectLowercaseCall isAsciiLowercaseLetterCode
arg detectLowercaseCall characterCode characterCode
run detectLowercaseCall
bind characterIsLowercase Bool detectLowercaseCall
branchIf characterIsLowercase returnIsLetter
const isLetterFalse Bool false
returnValue isLetterFalse
label returnIsLetter
const isLetterTrue Bool true
returnValue isLetterTrue

operation isAsciiLetterOrDigitCode
input isAsciiLetterOrDigitCode characterCode CSignedInt32
output isAsciiLetterOrDigitCode Bool
memoryHeap isAsciiLetterOrDigitCode no
memoryStackLimit isAsciiLetterOrDigitCode 1024
async isAsciiLetterOrDigitCode no
purpose isAsciiLetterOrDigitCode "Returns true when characterCode is an ASCII letter or decimal digit."
invariant isAsciiLetterOrDigitCode "Equivalent to isAsciiLetterCode(c) OR isAsciiDecimalDigitCode(c)."
guarantee isAsciiLetterOrDigitCode "Total."
label startIsAsciiLetterOrDigitCode
call detectLetterCall isAsciiLetterCode
arg detectLetterCall characterCode characterCode
run detectLetterCall
bind characterIsLetter Bool detectLetterCall
branchIf characterIsLetter returnIsLetterOrDigit
call detectDigitCall isAsciiDecimalDigitCode
arg detectDigitCall characterCode characterCode
run detectDigitCall
bind characterIsDigit Bool detectDigitCall
branchIf characterIsDigit returnIsLetterOrDigit
const isLetterOrDigitFalse Bool false
returnValue isLetterOrDigitFalse
label returnIsLetterOrDigit
const isLetterOrDigitTrue Bool true
returnValue isLetterOrDigitTrue

operation isAsciiHexDigitCode
input isAsciiHexDigitCode characterCode CSignedInt32
output isAsciiHexDigitCode Bool
memoryHeap isAsciiHexDigitCode no
memoryStackLimit isAsciiHexDigitCode 1024
async isAsciiHexDigitCode no
purpose isAsciiHexDigitCode "Returns true when characterCode is an ASCII hexadecimal digit (0-9, A-F, a-f)."
invariant isAsciiHexDigitCode "Equivalent to digit OR uppercase A..F OR lowercase a..f."
guarantee isAsciiHexDigitCode "Total."
label startIsAsciiHexDigitCode
call hexDigitDigitCall isAsciiDecimalDigitCode
arg hexDigitDigitCall characterCode characterCode
run hexDigitDigitCall
bind hexDigitIsDigit Bool hexDigitDigitCall
branchIf hexDigitIsDigit returnIsHexDigit
call detectBelowUppercaseHexCall math.lessThanI64
arg detectBelowUppercaseHexCall left characterCode
arg detectBelowUppercaseHexCall right asciiUppercaseACode
run detectBelowUppercaseHexCall
bind belowUppercaseHex Bool detectBelowUppercaseHexCall
branchIf belowUppercaseHex checkLowercaseHexRange
call detectAboveUppercaseHexCall math.greaterThanI64
arg detectAboveUppercaseHexCall left characterCode
arg detectAboveUppercaseHexCall right asciiUppercaseFCode
run detectAboveUppercaseHexCall
bind aboveUppercaseHex Bool detectAboveUppercaseHexCall
branchIf aboveUppercaseHex checkLowercaseHexRange
branch returnIsHexDigit
label checkLowercaseHexRange
call detectBelowLowercaseHexCall math.lessThanI64
arg detectBelowLowercaseHexCall left characterCode
arg detectBelowLowercaseHexCall right asciiLowercaseACode
run detectBelowLowercaseHexCall
bind belowLowercaseHex Bool detectBelowLowercaseHexCall
branchIf belowLowercaseHex returnNotHexDigit
call detectAboveLowercaseHexCall math.greaterThanI64
arg detectAboveLowercaseHexCall left characterCode
arg detectAboveLowercaseHexCall right asciiLowercaseFCode
run detectAboveLowercaseHexCall
bind aboveLowercaseHex Bool detectAboveLowercaseHexCall
branchIf aboveLowercaseHex returnNotHexDigit
branch returnIsHexDigit
label returnIsHexDigit
const isHexDigitTrue Bool true
returnValue isHexDigitTrue
label returnNotHexDigit
const isHexDigitFalse Bool false
returnValue isHexDigitFalse

# section ctype.whitespace
# rationale: whitespace and blank classification per ASCII conventions.

operation isAsciiWhitespaceCode
input isAsciiWhitespaceCode characterCode CSignedInt32
output isAsciiWhitespaceCode Bool
memoryHeap isAsciiWhitespaceCode no
memoryStackLimit isAsciiWhitespaceCode 1024
async isAsciiWhitespaceCode no
purpose isAsciiWhitespaceCode "Returns true for space, tab, LF, VT, FF, or CR (the standard ASCII whitespace set)."
invariant isAsciiWhitespaceCode "Same membership as C's isspace() on ASCII inputs."
guarantee isAsciiWhitespaceCode "Total."
label startIsAsciiWhitespaceCode
call detectEqualsSpaceCall math.equalI64
arg detectEqualsSpaceCall left characterCode
arg detectEqualsSpaceCall right asciiSpaceCode
run detectEqualsSpaceCall
bind characterEqualsSpace Bool detectEqualsSpaceCall
branchIf characterEqualsSpace returnIsWhitespace
call detectEqualsTabCall math.equalI64
arg detectEqualsTabCall left characterCode
arg detectEqualsTabCall right asciiTabCode
run detectEqualsTabCall
bind characterEqualsTab Bool detectEqualsTabCall
branchIf characterEqualsTab returnIsWhitespace
call detectEqualsLineFeedCall math.equalI64
arg detectEqualsLineFeedCall left characterCode
arg detectEqualsLineFeedCall right asciiLineFeedCode
run detectEqualsLineFeedCall
bind characterEqualsLineFeed Bool detectEqualsLineFeedCall
branchIf characterEqualsLineFeed returnIsWhitespace
call detectEqualsVerticalTabCall math.equalI64
arg detectEqualsVerticalTabCall left characterCode
arg detectEqualsVerticalTabCall right asciiVerticalTabCode
run detectEqualsVerticalTabCall
bind characterEqualsVerticalTab Bool detectEqualsVerticalTabCall
branchIf characterEqualsVerticalTab returnIsWhitespace
call detectEqualsFormFeedCall math.equalI64
arg detectEqualsFormFeedCall left characterCode
arg detectEqualsFormFeedCall right asciiFormFeedCode
run detectEqualsFormFeedCall
bind characterEqualsFormFeed Bool detectEqualsFormFeedCall
branchIf characterEqualsFormFeed returnIsWhitespace
call detectEqualsCarriageReturnCall math.equalI64
arg detectEqualsCarriageReturnCall left characterCode
arg detectEqualsCarriageReturnCall right asciiCarriageReturnCode
run detectEqualsCarriageReturnCall
bind characterEqualsCarriageReturn Bool detectEqualsCarriageReturnCall
branchIf characterEqualsCarriageReturn returnIsWhitespace
const isWhitespaceFalse Bool false
returnValue isWhitespaceFalse
label returnIsWhitespace
const isWhitespaceTrue Bool true
returnValue isWhitespaceTrue

operation isAsciiBlankCode
input isAsciiBlankCode characterCode CSignedInt32
output isAsciiBlankCode Bool
memoryHeap isAsciiBlankCode no
memoryStackLimit isAsciiBlankCode 1024
async isAsciiBlankCode no
purpose isAsciiBlankCode "Returns true only for space or horizontal tab."
invariant isAsciiBlankCode "Strict subset of isAsciiWhitespaceCode — excludes LF, VT, FF, CR."
guarantee isAsciiBlankCode "Total."
label startIsAsciiBlankCode
call detectBlankSpaceCall math.equalI64
arg detectBlankSpaceCall left characterCode
arg detectBlankSpaceCall right asciiSpaceCode
run detectBlankSpaceCall
bind characterIsBlankSpace Bool detectBlankSpaceCall
branchIf characterIsBlankSpace returnIsBlank
call detectBlankTabCall math.equalI64
arg detectBlankTabCall left characterCode
arg detectBlankTabCall right asciiTabCode
run detectBlankTabCall
bind characterIsBlankTab Bool detectBlankTabCall
branchIf characterIsBlankTab returnIsBlank
const isBlankFalse Bool false
returnValue isBlankFalse
label returnIsBlank
const isBlankTrue Bool true
returnValue isBlankTrue

# section ctype.control
# rationale: control / printable / graphical / punctuation classification.

operation isAsciiControlCode
input isAsciiControlCode characterCode CSignedInt32
output isAsciiControlCode Bool
memoryHeap isAsciiControlCode no
memoryStackLimit isAsciiControlCode 1024
async isAsciiControlCode no
purpose isAsciiControlCode "Returns true for control characters (0x00..0x1F or 0x7F)."
invariant isAsciiControlCode "Holds iff 0 <= c <= 31 OR c == 127."
guarantee isAsciiControlCode "Total."
label startIsAsciiControlCode
call detectLowControlRangeCall math.lessThanOrEqualI64
arg detectLowControlRangeCall left characterCode
arg detectLowControlRangeCall right asciiHighestControlCode
run detectLowControlRangeCall
bind characterInLowControlRange Bool detectLowControlRangeCall
branchIf characterInLowControlRange returnIsControl
call detectEqualsDeleteCall math.equalI64
arg detectEqualsDeleteCall left characterCode
arg detectEqualsDeleteCall right asciiDeleteCode
run detectEqualsDeleteCall
bind characterEqualsDelete Bool detectEqualsDeleteCall
branchIf characterEqualsDelete returnIsControl
const isControlFalse Bool false
returnValue isControlFalse
label returnIsControl
const isControlTrue Bool true
returnValue isControlTrue

operation isAsciiPrintableCode
input isAsciiPrintableCode characterCode CSignedInt32
output isAsciiPrintableCode Bool
memoryHeap isAsciiPrintableCode no
memoryStackLimit isAsciiPrintableCode 1024
async isAsciiPrintableCode no
purpose isAsciiPrintableCode "Returns true for printable characters (0x20..0x7E)."
invariant isAsciiPrintableCode "Holds iff 32 <= c <= 126 (space through tilde)."
guarantee isAsciiPrintableCode "Total."
label startIsAsciiPrintableCode
call detectBelowPrintableRangeCall math.lessThanI64
arg detectBelowPrintableRangeCall left characterCode
arg detectBelowPrintableRangeCall right asciiLowestPrintableCode
run detectBelowPrintableRangeCall
bind belowPrintableRange Bool detectBelowPrintableRangeCall
branchIf belowPrintableRange returnNotPrintable
call detectAbovePrintableRangeCall math.greaterThanI64
arg detectAbovePrintableRangeCall left characterCode
arg detectAbovePrintableRangeCall right asciiHighestPrintableCode
run detectAbovePrintableRangeCall
bind abovePrintableRange Bool detectAbovePrintableRangeCall
branchIf abovePrintableRange returnNotPrintable
const isPrintableTrue Bool true
returnValue isPrintableTrue
label returnNotPrintable
const isPrintableFalse Bool false
returnValue isPrintableFalse

operation isAsciiGraphicalCode
input isAsciiGraphicalCode characterCode CSignedInt32
output isAsciiGraphicalCode Bool
memoryHeap isAsciiGraphicalCode no
memoryStackLimit isAsciiGraphicalCode 1024
async isAsciiGraphicalCode no
purpose isAsciiGraphicalCode "Returns true for printable characters that are not space (0x21..0x7E)."
invariant isAsciiGraphicalCode "Holds iff 33 <= c <= 126."
guarantee isAsciiGraphicalCode "Total."
label startIsAsciiGraphicalCode
call detectBelowGraphicalRangeCall math.lessThanI64
arg detectBelowGraphicalRangeCall left characterCode
arg detectBelowGraphicalRangeCall right asciiLowestGraphicalCode
run detectBelowGraphicalRangeCall
bind belowGraphicalRange Bool detectBelowGraphicalRangeCall
branchIf belowGraphicalRange returnNotGraphical
call detectAboveGraphicalRangeCall math.greaterThanI64
arg detectAboveGraphicalRangeCall left characterCode
arg detectAboveGraphicalRangeCall right asciiHighestPrintableCode
run detectAboveGraphicalRangeCall
bind aboveGraphicalRange Bool detectAboveGraphicalRangeCall
branchIf aboveGraphicalRange returnNotGraphical
const isGraphicalTrue Bool true
returnValue isGraphicalTrue
label returnNotGraphical
const isGraphicalFalse Bool false
returnValue isGraphicalFalse

operation isAsciiPunctuationCode
input isAsciiPunctuationCode characterCode CSignedInt32
output isAsciiPunctuationCode Bool
memoryHeap isAsciiPunctuationCode no
memoryStackLimit isAsciiPunctuationCode 1024
async isAsciiPunctuationCode no
purpose isAsciiPunctuationCode "Returns true for printable characters that are not space or alphanumeric."
invariant isAsciiPunctuationCode "Equivalent to isAsciiGraphicalCode AND NOT isAsciiLetterOrDigitCode."
guarantee isAsciiPunctuationCode "Total."
label startIsAsciiPunctuationCode
call punctGraphicalCall isAsciiGraphicalCode
arg punctGraphicalCall characterCode characterCode
run punctGraphicalCall
bind characterIsGraphical Bool punctGraphicalCall
branchIf characterIsGraphical checkPunctuationAlnum
const isPunctuationFalseFromNonGraphical Bool false
returnValue isPunctuationFalseFromNonGraphical
label checkPunctuationAlnum
call punctAlnumCall isAsciiLetterOrDigitCode
arg punctAlnumCall characterCode characterCode
run punctAlnumCall
bind characterIsAlphanumeric Bool punctAlnumCall
branchIf characterIsAlphanumeric returnNotPunctuation
const isPunctuationTrue Bool true
returnValue isPunctuationTrue
label returnNotPunctuation
const isPunctuationFalse Bool false
returnValue isPunctuationFalse

# section ctype.case
# rationale: case-mapping operations that preserve out-of-range bytes.

operation convertAsciiLetterCodeToUppercase
input convertAsciiLetterCodeToUppercase characterCode CSignedInt32
output convertAsciiLetterCodeToUppercase CSignedInt32
memoryHeap convertAsciiLetterCodeToUppercase no
memoryStackLimit convertAsciiLetterCodeToUppercase 1024
async convertAsciiLetterCodeToUppercase no
purpose convertAsciiLetterCodeToUppercase "Maps ASCII lowercase letters (0x61..0x7A) to uppercase; passes every other byte through unchanged."
invariant convertAsciiLetterCodeToUppercase "For characterCode in 97..122, output == characterCode - 32. Otherwise output == characterCode."
guarantee convertAsciiLetterCodeToUppercase "Total. Idempotent on already-uppercase or non-letter bytes."
label startConvertAsciiLetterCodeToUppercase
call detectBelowLowercaseLetterCall math.lessThanI64
arg detectBelowLowercaseLetterCall left characterCode
arg detectBelowLowercaseLetterCall right asciiLowercaseACode
run detectBelowLowercaseLetterCall
bind belowLowercaseLetter Bool detectBelowLowercaseLetterCall
branchIf belowLowercaseLetter passThroughCharacterForUppercase
call detectAboveLowercaseLetterCall math.greaterThanI64
arg detectAboveLowercaseLetterCall left characterCode
arg detectAboveLowercaseLetterCall right asciiLowercaseZCode
run detectAboveLowercaseLetterCall
bind aboveLowercaseLetter Bool detectAboveLowercaseLetterCall
branchIf aboveLowercaseLetter passThroughCharacterForUppercase
call subtractCaseShiftCall math.subtractI64
arg subtractCaseShiftCall left characterCode
arg subtractCaseShiftCall right asciiUppercaseLowercaseGap
run subtractCaseShiftCall
bind shiftedUppercaseCharacter CSignedInt32 subtractCaseShiftCall
returnValue shiftedUppercaseCharacter
label passThroughCharacterForUppercase
returnValue characterCode

operation convertAsciiLetterCodeToLowercase
input convertAsciiLetterCodeToLowercase characterCode CSignedInt32
output convertAsciiLetterCodeToLowercase CSignedInt32
memoryHeap convertAsciiLetterCodeToLowercase no
memoryStackLimit convertAsciiLetterCodeToLowercase 1024
async convertAsciiLetterCodeToLowercase no
purpose convertAsciiLetterCodeToLowercase "Maps ASCII uppercase letters (0x41..0x5A) to lowercase; passes every other byte through unchanged."
invariant convertAsciiLetterCodeToLowercase "For characterCode in 65..90, output == characterCode + 32. Otherwise output == characterCode."
guarantee convertAsciiLetterCodeToLowercase "Total. Idempotent on already-lowercase or non-letter bytes."
label startConvertAsciiLetterCodeToLowercase
call detectBelowUppercaseLetterCall math.lessThanI64
arg detectBelowUppercaseLetterCall left characterCode
arg detectBelowUppercaseLetterCall right asciiUppercaseACode
run detectBelowUppercaseLetterCall
bind belowUppercaseLetter Bool detectBelowUppercaseLetterCall
branchIf belowUppercaseLetter passThroughCharacterForLowercase
call detectAboveUppercaseLetterCall math.greaterThanI64
arg detectAboveUppercaseLetterCall left characterCode
arg detectAboveUppercaseLetterCall right asciiUppercaseZCode
run detectAboveUppercaseLetterCall
bind aboveUppercaseLetter Bool detectAboveUppercaseLetterCall
branchIf aboveUppercaseLetter passThroughCharacterForLowercase
call addCaseShiftCall math.addI64
arg addCaseShiftCall left characterCode
arg addCaseShiftCall right asciiUppercaseLowercaseGap
run addCaseShiftCall
bind shiftedLowercaseCharacter CSignedInt32 addCaseShiftCall
returnValue shiftedLowercaseCharacter
label passThroughCharacterForLowercase
returnValue characterCode

# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
useCapability main stdoutWriteCapability
effect main write console.stdout
memoryHeap main no
memoryStackLimit main 1024
async main no
purpose main "Smoke-test every classifier and case mapper; print OK on success, returnError otherwise."
invariant main "Every predicate asserted is satisfied or the assertion-failure path runs."
label startMain

const digit5Code CSignedInt32 53
const lowerHCode CSignedInt32 104
const upperHCode CSignedInt32 72
const exclamationMarkCode CSignedInt32 33
const upperFHexCode CSignedInt32 70
const nullByteCode CSignedInt32 0
const tabByteCode CSignedInt32 9
const lineFeedByteCode CSignedInt32 10
const spaceByteCode CSignedInt32 32

# isAsciiDecimalDigitCode('5') == true
call assertDigit5Call isAsciiDecimalDigitCode
arg assertDigit5Call characterCode digit5Code
run assertDigit5Call
bind digit5IsDigit Bool assertDigit5Call
branchIf digit5IsDigit digit5Holds
branch smokeAssertionFailed
label digit5Holds

# isAsciiLetterCode('h') == true
call assertLetterHCall isAsciiLetterCode
arg assertLetterHCall characterCode lowerHCode
run assertLetterHCall
bind lowerHIsLetter Bool assertLetterHCall
branchIf lowerHIsLetter letterHHolds
branch smokeAssertionFailed
label letterHHolds

# isAsciiLetterOrDigitCode('5') == true
call assertAlnumDigitCall isAsciiLetterOrDigitCode
arg assertAlnumDigitCall characterCode digit5Code
run assertAlnumDigitCall
bind digit5IsAlnum Bool assertAlnumDigitCall
branchIf digit5IsAlnum alnumDigitHolds
branch smokeAssertionFailed
label alnumDigitHolds

# isAsciiLetterOrDigitCode('!') == false
call assertAlnumPunctCall isAsciiLetterOrDigitCode
arg assertAlnumPunctCall characterCode exclamationMarkCode
run assertAlnumPunctCall
bind exclamationIsAlnum Bool assertAlnumPunctCall
branchIf exclamationIsAlnum smokeAssertionFailed

# isAsciiHexDigitCode('F') == true
call assertHexCall isAsciiHexDigitCode
arg assertHexCall characterCode upperFHexCode
run assertHexCall
bind upperFIsHexDigit Bool assertHexCall
branchIf upperFIsHexDigit hexHolds
branch smokeAssertionFailed
label hexHolds

# isAsciiWhitespaceCode(' ') == true
call assertWhitespaceSpaceCall isAsciiWhitespaceCode
arg assertWhitespaceSpaceCall characterCode spaceByteCode
run assertWhitespaceSpaceCall
bind spaceIsWhitespace Bool assertWhitespaceSpaceCall
branchIf spaceIsWhitespace whitespaceSpaceHolds
branch smokeAssertionFailed
label whitespaceSpaceHolds

# isAsciiBlankCode('\t') == true
call assertBlankTabCall isAsciiBlankCode
arg assertBlankTabCall characterCode tabByteCode
run assertBlankTabCall
bind tabIsBlank Bool assertBlankTabCall
branchIf tabIsBlank blankTabHolds
branch smokeAssertionFailed
label blankTabHolds

# isAsciiBlankCode('\n') == false
call assertBlankLineFeedCall isAsciiBlankCode
arg assertBlankLineFeedCall characterCode lineFeedByteCode
run assertBlankLineFeedCall
bind lineFeedIsBlank Bool assertBlankLineFeedCall
branchIf lineFeedIsBlank smokeAssertionFailed

# isAsciiControlCode(0) == true
call assertControlNullCall isAsciiControlCode
arg assertControlNullCall characterCode nullByteCode
run assertControlNullCall
bind nullIsControl Bool assertControlNullCall
branchIf nullIsControl controlNullHolds
branch smokeAssertionFailed
label controlNullHolds

# isAsciiPrintableCode(' ') == true
call assertPrintableSpaceCall isAsciiPrintableCode
arg assertPrintableSpaceCall characterCode spaceByteCode
run assertPrintableSpaceCall
bind spaceIsPrintable Bool assertPrintableSpaceCall
branchIf spaceIsPrintable printableSpaceHolds
branch smokeAssertionFailed
label printableSpaceHolds

# isAsciiGraphicalCode(' ') == false (space is not graphical)
call assertGraphicalSpaceCall isAsciiGraphicalCode
arg assertGraphicalSpaceCall characterCode spaceByteCode
run assertGraphicalSpaceCall
bind spaceIsGraphical Bool assertGraphicalSpaceCall
branchIf spaceIsGraphical smokeAssertionFailed

# isAsciiPunctuationCode('!') == true
call assertPunctuationExclamationCall isAsciiPunctuationCode
arg assertPunctuationExclamationCall characterCode exclamationMarkCode
run assertPunctuationExclamationCall
bind exclamationIsPunctuation Bool assertPunctuationExclamationCall
branchIf exclamationIsPunctuation punctuationExclamationHolds
branch smokeAssertionFailed
label punctuationExclamationHolds

# convertAsciiLetterCodeToUppercase('h') == 'H'
call assertToUpperCall convertAsciiLetterCodeToUppercase
arg assertToUpperCall characterCode lowerHCode
run assertToUpperCall
bind upperConversionResult CSignedInt32 assertToUpperCall
call checkToUpperCall math.equalI64
arg checkToUpperCall left upperConversionResult
arg checkToUpperCall right upperHCode
run checkToUpperCall
bind toUpperOk Bool checkToUpperCall
branchIf toUpperOk toUpperHolds
branch smokeAssertionFailed
label toUpperHolds

# convertAsciiLetterCodeToLowercase('H') == 'h'
call assertToLowerCall convertAsciiLetterCodeToLowercase
arg assertToLowerCall characterCode upperHCode
run assertToLowerCall
bind lowerConversionResult CSignedInt32 assertToLowerCall
call checkToLowerCall math.equalI64
arg checkToLowerCall left lowerConversionResult
arg checkToLowerCall right lowerHCode
run checkToLowerCall
bind toLowerOk Bool checkToLowerCall
branchIf toLowerOk toLowerHolds
branch smokeAssertionFailed
label toLowerHolds

# ============================================================
# Extended unit tests: coverage for the 2 untested ops
# (isAsciiLowercaseLetterCode, isAsciiUppercaseLetterCode) plus
# negative-case boundaries for each predicate (off-by-one is the
# most common ctype bug, so each range gets both an inside and
# outside check).
# ============================================================

const lowerACode CSignedInt32 97
const upperACode CSignedInt32 65
const lowerFHexCode CSignedInt32 102
const letterGNotHexCode CSignedInt32 71
const digit0Code CSignedInt32 48
const tildeCode CSignedInt32 126
const deleteCode CSignedInt32 127

# isAsciiLowercaseLetterCode('a') == true
call lowerATrueCall isAsciiLowercaseLetterCode
arg lowerATrueCall characterCode lowerACode
run lowerATrueCall
bind lowerATrueResult Bool lowerATrueCall
branchIf lowerATrueResult lowerATrueHolds
branch smokeAssertionFailed
label lowerATrueHolds

# isAsciiLowercaseLetterCode('A') == false
call lowerAFalseCall isAsciiLowercaseLetterCode
arg lowerAFalseCall characterCode upperACode
run lowerAFalseCall
bind lowerAFalseResult Bool lowerAFalseCall
branchIf lowerAFalseResult smokeAssertionFailed
branch lowerAFalseHolds
label lowerAFalseHolds

# isAsciiUppercaseLetterCode('A') == true
call upperATrueCall isAsciiUppercaseLetterCode
arg upperATrueCall characterCode upperACode
run upperATrueCall
bind upperATrueResult Bool upperATrueCall
branchIf upperATrueResult upperATrueHolds
branch smokeAssertionFailed
label upperATrueHolds

# isAsciiUppercaseLetterCode('a') == false
call upperAFalseCall isAsciiUppercaseLetterCode
arg upperAFalseCall characterCode lowerACode
run upperAFalseCall
bind upperAFalseResult Bool upperAFalseCall
branchIf upperAFalseResult smokeAssertionFailed
branch upperAFalseHolds
label upperAFalseHolds

# isAsciiDecimalDigitCode('a') == false (letter outside digit range)
call digitNonCall isAsciiDecimalDigitCode
arg digitNonCall characterCode lowerACode
run digitNonCall
bind digitNonResult Bool digitNonCall
branchIf digitNonResult smokeAssertionFailed
branch digitNonHolds
label digitNonHolds

# isAsciiDecimalDigitCode('0') == true (boundary)
call digitZeroCall isAsciiDecimalDigitCode
arg digitZeroCall characterCode digit0Code
run digitZeroCall
bind digitZeroResult Bool digitZeroCall
branchIf digitZeroResult digitZeroHolds
branch smokeAssertionFailed
label digitZeroHolds

# isAsciiLetterCode('5') == false (digit not letter)
call letterNonCall isAsciiLetterCode
arg letterNonCall characterCode digit5Code
run letterNonCall
bind letterNonResult Bool letterNonCall
branchIf letterNonResult smokeAssertionFailed
branch letterNonHolds
label letterNonHolds

# isAsciiHexDigitCode('f') == true (lowercase hex digit)
call hexLowerCall isAsciiHexDigitCode
arg hexLowerCall characterCode lowerFHexCode
run hexLowerCall
bind hexLowerResult Bool hexLowerCall
branchIf hexLowerResult hexLowerHolds
branch smokeAssertionFailed
label hexLowerHolds

# isAsciiHexDigitCode('G') == false (just past F)
call hexGFalseCall isAsciiHexDigitCode
arg hexGFalseCall characterCode letterGNotHexCode
run hexGFalseCall
bind hexGFalseResult Bool hexGFalseCall
branchIf hexGFalseResult smokeAssertionFailed
branch hexGFalseHolds
label hexGFalseHolds

# isAsciiControlCode(' ') == false (space is not control)
call controlSpaceCall isAsciiControlCode
arg controlSpaceCall characterCode spaceByteCode
run controlSpaceCall
bind controlSpaceResult Bool controlSpaceCall
branchIf controlSpaceResult smokeAssertionFailed
branch controlSpaceHolds
label controlSpaceHolds

# isAsciiControlCode(127) == true (DEL is control)
call controlDelCall isAsciiControlCode
arg controlDelCall characterCode deleteCode
run controlDelCall
bind controlDelResult Bool controlDelCall
branchIf controlDelResult controlDelHolds
branch smokeAssertionFailed
label controlDelHolds

# isAsciiPrintableCode(0) == false (NUL not printable)
call printNonCall isAsciiPrintableCode
arg printNonCall characterCode nullByteCode
run printNonCall
bind printNonResult Bool printNonCall
branchIf printNonResult smokeAssertionFailed
branch printNonHolds
label printNonHolds

# isAsciiPrintableCode('~') == true (last printable)
call printTildeCall isAsciiPrintableCode
arg printTildeCall characterCode tildeCode
run printTildeCall
bind printTildeResult Bool printTildeCall
branchIf printTildeResult printTildeHolds
branch smokeAssertionFailed
label printTildeHolds

# convertAsciiLetterCodeToUppercase('H') == 'H' (already upper, identity)
call upperIdCall convertAsciiLetterCodeToUppercase
arg upperIdCall characterCode upperHCode
run upperIdCall
bind upperIdResult CSignedInt32 upperIdCall
call upperIdCheckCall math.equalI64
arg upperIdCheckCall left upperIdResult
arg upperIdCheckCall right upperHCode
run upperIdCheckCall
bind upperIdOk Bool upperIdCheckCall
branchIf upperIdOk upperIdHolds
branch smokeAssertionFailed
label upperIdHolds

# convertAsciiLetterCodeToLowercase('5') == '5' (non-letter identity)
call lowerNonLetterCall convertAsciiLetterCodeToLowercase
arg lowerNonLetterCall characterCode digit5Code
run lowerNonLetterCall
bind lowerNonLetterResult CSignedInt32 lowerNonLetterCall
call lowerNonLetterCheckCall math.equalI64
arg lowerNonLetterCheckCall left lowerNonLetterResult
arg lowerNonLetterCheckCall right digit5Code
run lowerNonLetterCheckCall
bind lowerNonLetterOk Bool lowerNonLetterCheckCall
branchIf lowerNonLetterOk lowerNonLetterHolds
branch smokeAssertionFailed
label lowerNonLetterHolds

# Property: convertToUpper(convertToLower('H')) == 'H' (round-trip)
call propLowerCall convertAsciiLetterCodeToLowercase
arg propLowerCall characterCode upperHCode
run propLowerCall
bind propLowerResult CSignedInt32 propLowerCall
call propUpperCall convertAsciiLetterCodeToUppercase
arg propUpperCall characterCode propLowerResult
run propUpperCall
bind propUpperResult CSignedInt32 propUpperCall
call propRoundTripCheckCall math.equalI64
arg propRoundTripCheckCall left propUpperResult
arg propRoundTripCheckCall right upperHCode
run propRoundTripCheckCall
bind propRoundTripOk Bool propRoundTripCheckCall
branchIf propRoundTripOk propRoundTripHolds
branch smokeAssertionFailed
label propRoundTripHolds

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
makeError ctypeSmokeFailure MainError.CtypeSmokeAssertionFailed
returnError ctypeSmokeFailure
