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
#   asciiNullCharacterCode, asciiHorizontalTabCharacterCode, asciiNewlineCharacterCode, asciiCarriageReturnCharacterCode, asciiSpaceCharacterCode,
#   asciiBellCharacterCode, asciiBackspaceCharacterCode, asciiEscapeCharacterCode, asciiDeleteCharacterCode, asciiDoubleQuoteCharacterCode,
#   asciiSingleQuoteCharacterCode, asciiBackslashCharacterCode, asciiPeriodCharacterCode, asciiCommaCharacterCode, asciiColonCharacterCode,
#   asciiSemicolonCharacterCode, asciiSlashCharacterCode, asciiAsteriskCharacterCode.
# ============================================================

operation asciiNullCharacterCode
output asciiNullCharacterCode Result CSignedInt32 Void
memory asciiNullCharacterCode heap no
async asciiNullCharacterCode no
purpose asciiNullCharacterCode "NUL byte (0)."
label startAsciiNullCharacterCode
const v CSignedInt32 0
returnOk v

operation asciiHorizontalTabCharacterCode
output asciiHorizontalTabCharacterCode Result CSignedInt32 Void
memory asciiHorizontalTabCharacterCode heap no
async asciiHorizontalTabCharacterCode no
purpose asciiHorizontalTabCharacterCode "Horizontal tab (9)."
label startAsciiHorizontalTabCharacterCode
const v CSignedInt32 9
returnOk v

operation asciiNewlineCharacterCode
output asciiNewlineCharacterCode Result CSignedInt32 Void
memory asciiNewlineCharacterCode heap no
async asciiNewlineCharacterCode no
purpose asciiNewlineCharacterCode "Line feed (10)."
label startAsciiNewlineCharacterCode
const v CSignedInt32 10
returnOk v

operation asciiCarriageReturnCharacterCode
output asciiCarriageReturnCharacterCode Result CSignedInt32 Void
memory asciiCarriageReturnCharacterCode heap no
async asciiCarriageReturnCharacterCode no
purpose asciiCarriageReturnCharacterCode "Carriage return (13)."
label startAsciiCarriageReturnCharacterCode
const v CSignedInt32 13
returnOk v

operation asciiSpaceCharacterCode
output asciiSpaceCharacterCode Result CSignedInt32 Void
memory asciiSpaceCharacterCode heap no
async asciiSpaceCharacterCode no
purpose asciiSpaceCharacterCode "Space (32)."
label startAsciiSpaceCharacterCode
const v CSignedInt32 32
returnOk v

operation asciiBellCharacterCode
output asciiBellCharacterCode Result CSignedInt32 Void
memory asciiBellCharacterCode heap no
async asciiBellCharacterCode no
purpose asciiBellCharacterCode "BEL (7)."
label startAsciiBellCharacterCode
const v CSignedInt32 7
returnOk v

operation asciiBackspaceCharacterCode
output asciiBackspaceCharacterCode Result CSignedInt32 Void
memory asciiBackspaceCharacterCode heap no
async asciiBackspaceCharacterCode no
purpose asciiBackspaceCharacterCode "BS (8)."
label startAsciiBackspaceCharacterCode
const v CSignedInt32 8
returnOk v

operation asciiEscapeCharacterCode
output asciiEscapeCharacterCode Result CSignedInt32 Void
memory asciiEscapeCharacterCode heap no
async asciiEscapeCharacterCode no
purpose asciiEscapeCharacterCode "ESC (27)."
label startAsciiEscapeCharacterCode
const v CSignedInt32 27
returnOk v

operation asciiDeleteCharacterCode
output asciiDeleteCharacterCode Result CSignedInt32 Void
memory asciiDeleteCharacterCode heap no
async asciiDeleteCharacterCode no
purpose asciiDeleteCharacterCode "DEL (127)."
label startAsciiDeleteCharacterCode
const v CSignedInt32 127
returnOk v

operation asciiDoubleQuoteCharacterCode
output asciiDoubleQuoteCharacterCode Result CSignedInt32 Void
memory asciiDoubleQuoteCharacterCode heap no
async asciiDoubleQuoteCharacterCode no
purpose asciiDoubleQuoteCharacterCode "\" (34)."
label startAsciiDoubleQuoteCharacterCode
const v CSignedInt32 34
returnOk v

operation asciiSingleQuoteCharacterCode
output asciiSingleQuoteCharacterCode Result CSignedInt32 Void
memory asciiSingleQuoteCharacterCode heap no
async asciiSingleQuoteCharacterCode no
purpose asciiSingleQuoteCharacterCode "' (39)."
label startAsciiSingleQuoteCharacterCode
const v CSignedInt32 39
returnOk v

operation asciiBackslashCharacterCode
output asciiBackslashCharacterCode Result CSignedInt32 Void
memory asciiBackslashCharacterCode heap no
async asciiBackslashCharacterCode no
purpose asciiBackslashCharacterCode "\\ (92)."
label startAsciiBackslashCharacterCode
const v CSignedInt32 92
returnOk v

operation asciiPeriodCharacterCode
output asciiPeriodCharacterCode Result CSignedInt32 Void
memory asciiPeriodCharacterCode heap no
async asciiPeriodCharacterCode no
purpose asciiPeriodCharacterCode ". (46)."
label startAsciiPeriodCharacterCode
const v CSignedInt32 46
returnOk v

operation asciiCommaCharacterCode
output asciiCommaCharacterCode Result CSignedInt32 Void
memory asciiCommaCharacterCode heap no
async asciiCommaCharacterCode no
purpose asciiCommaCharacterCode ", (44)."
label startAsciiCommaCharacterCode
const v CSignedInt32 44
returnOk v

operation asciiColonCharacterCode
output asciiColonCharacterCode Result CSignedInt32 Void
memory asciiColonCharacterCode heap no
async asciiColonCharacterCode no
purpose asciiColonCharacterCode ": (58)."
label startAsciiColonCharacterCode
const v CSignedInt32 58
returnOk v

operation asciiSemicolonCharacterCode
output asciiSemicolonCharacterCode Result CSignedInt32 Void
memory asciiSemicolonCharacterCode heap no
async asciiSemicolonCharacterCode no
purpose asciiSemicolonCharacterCode "; (59)."
label startAsciiSemicolonCharacterCode
const v CSignedInt32 59
returnOk v

operation asciiSlashCharacterCode
output asciiSlashCharacterCode Result CSignedInt32 Void
memory asciiSlashCharacterCode heap no
async asciiSlashCharacterCode no
purpose asciiSlashCharacterCode "/ (47)."
label startAsciiSlashCharacterCode
const v CSignedInt32 47
returnOk v

operation asciiAsteriskCharacterCode
output asciiAsteriskCharacterCode Result CSignedInt32 Void
memory asciiAsteriskCharacterCode heap no
async asciiAsteriskCharacterCode no
purpose asciiAsteriskCharacterCode "* (42)."
label startAsciiAsteriskCharacterCode
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
call s1 asciiNewlineCharacterCode
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
