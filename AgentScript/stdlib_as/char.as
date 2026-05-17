project StdCharSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: character-value accessors.
#
# Each operation returns a canonical ASCII byte value, useful when AS
# programs need to spell a control byte without embedding a literal
# string. They're zero-cost (constant-folded by the LLVM optimizer).
#
# Operations:
#   nullChar, tabChar, newlineChar, carriageReturnChar, spaceChar,
#   bellChar, backspaceChar, escapeChar, deleteChar, doubleQuoteChar,
#   singleQuoteChar, backslashChar, periodChar, commaChar, colonChar,
#   semicolonChar, slashChar, asteriskChar.
# ============================================================

operation nullChar
output nullChar Result CSignedInt32 Void
memory nullChar heap no
async nullChar no
purpose nullChar "NUL byte (0)."
label startNullChar
const v CSignedInt32 0
returnOk v

operation tabChar
output tabChar Result CSignedInt32 Void
memory tabChar heap no
async tabChar no
purpose tabChar "Horizontal tab (9)."
label startTabChar
const v CSignedInt32 9
returnOk v

operation newlineChar
output newlineChar Result CSignedInt32 Void
memory newlineChar heap no
async newlineChar no
purpose newlineChar "Line feed (10)."
label startNewlineChar
const v CSignedInt32 10
returnOk v

operation carriageReturnChar
output carriageReturnChar Result CSignedInt32 Void
memory carriageReturnChar heap no
async carriageReturnChar no
purpose carriageReturnChar "Carriage return (13)."
label startCarriageReturnChar
const v CSignedInt32 13
returnOk v

operation spaceChar
output spaceChar Result CSignedInt32 Void
memory spaceChar heap no
async spaceChar no
purpose spaceChar "Space (32)."
label startSpaceChar
const v CSignedInt32 32
returnOk v

operation bellChar
output bellChar Result CSignedInt32 Void
memory bellChar heap no
async bellChar no
purpose bellChar "BEL (7)."
label startBellChar
const v CSignedInt32 7
returnOk v

operation backspaceChar
output backspaceChar Result CSignedInt32 Void
memory backspaceChar heap no
async backspaceChar no
purpose backspaceChar "BS (8)."
label startBackspaceChar
const v CSignedInt32 8
returnOk v

operation escapeChar
output escapeChar Result CSignedInt32 Void
memory escapeChar heap no
async escapeChar no
purpose escapeChar "ESC (27)."
label startEscapeChar
const v CSignedInt32 27
returnOk v

operation deleteChar
output deleteChar Result CSignedInt32 Void
memory deleteChar heap no
async deleteChar no
purpose deleteChar "DEL (127)."
label startDeleteChar
const v CSignedInt32 127
returnOk v

operation doubleQuoteChar
output doubleQuoteChar Result CSignedInt32 Void
memory doubleQuoteChar heap no
async doubleQuoteChar no
purpose doubleQuoteChar "\" (34)."
label startDoubleQuoteChar
const v CSignedInt32 34
returnOk v

operation singleQuoteChar
output singleQuoteChar Result CSignedInt32 Void
memory singleQuoteChar heap no
async singleQuoteChar no
purpose singleQuoteChar "' (39)."
label startSingleQuoteChar
const v CSignedInt32 39
returnOk v

operation backslashChar
output backslashChar Result CSignedInt32 Void
memory backslashChar heap no
async backslashChar no
purpose backslashChar "\\ (92)."
label startBackslashChar
const v CSignedInt32 92
returnOk v

operation periodChar
output periodChar Result CSignedInt32 Void
memory periodChar heap no
async periodChar no
purpose periodChar ". (46)."
label startPeriodChar
const v CSignedInt32 46
returnOk v

operation commaChar
output commaChar Result CSignedInt32 Void
memory commaChar heap no
async commaChar no
purpose commaChar ", (44)."
label startCommaChar
const v CSignedInt32 44
returnOk v

operation colonChar
output colonChar Result CSignedInt32 Void
memory colonChar heap no
async colonChar no
purpose colonChar ": (58)."
label startColonChar
const v CSignedInt32 58
returnOk v

operation semicolonChar
output semicolonChar Result CSignedInt32 Void
memory semicolonChar heap no
async semicolonChar no
purpose semicolonChar "; (59)."
label startSemicolonChar
const v CSignedInt32 59
returnOk v

operation slashChar
output slashChar Result CSignedInt32 Void
memory slashChar heap no
async slashChar no
purpose slashChar "/ (47)."
label startSlashChar
const v CSignedInt32 47
returnOk v

operation asteriskChar
output asteriskChar Result CSignedInt32 Void
memory asteriskChar heap no
async asteriskChar no
purpose asteriskChar "* (42)."
label startAsteriskChar
const v CSignedInt32 42
returnOk v

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test char accessors. Prints OK."
label startMain
call s1 newlineChar
run s1
bindOk s1Res CSignedInt32 s1
const ten CSignedInt32 10
call s1Check math.equalI64
arg s1Check left s1Res
arg s1Check right ten
run s1Check
bind s1Ok Bool s1Check
branchIf s1Ok s1Lbl
branch testFailed
label s1Lbl
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
