project StdStdioSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError WriteFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: stdio operations.
#
# Every operation here is implemented in pure AgentScript on top of
# ONE bottom-level OS primitive: c.putchar (the only thing that
# actually crosses into the host OS to deliver a byte to stdout).
#
# - putByte(c)         : floor primitive wrapper — one byte to stdout.
# - putLine(s)            : write a NUL-terminated string + newline,
#                        byte-by-byte through putByte.
# - putString(s)   : write a NUL-terminated string, no trailing
#                        newline. (Useful for prompts, partial lines.)
# - putIntegerDecimal(n) : print a signed 64-bit integer in decimal,
#                        followed by a newline, byte-by-byte.
#
# All operations work for the ASCII subset; multibyte / locale handling
# is intentionally out of scope at this layer.
# ============================================================

# ---- putByte(c) ----
# Thin wrapper over the floor primitive c.putchar. Exists so user
# code never names a c.* function directly — every higher level
# bottoms out through this operation.
operation putByte
input putByte c CSignedInt32
output putByte Result CSignedInt32 Void
effect putByte write console.stdout
memory putByte heap no
memory putByte stack max 1KiB
async putByte no
purpose putByte "Write one byte to stdout. The single line of code that ever crosses out to the host OS in the AgentScript stdlib."

label startPutchar
call libcCall c.putchar
arg libcCall c c
run libcCall
bind result CSignedInt32 libcCall
returnOk result


# ---- putString(s) ----
# Walk the string byte by byte, calling putByte for each. Stops at the
# first NUL. Returns the number of bytes written.
operation putString
input putString s CNullTerminatedByteString
output putString Result CByteCount Void
effect putString write console.stdout
effect putString read memory.buffer
memory putString heap no
memory putString stack max 1KiB
async putString no
purpose putString "Write every byte of s to stdout via putByte until a NUL is reached. Returns the byte count. Pure AS — no libc string call."

label startPutsNoNewline
const zeroI64a I64 0
const oneI64a I64 1
var idxA I64 0

label putsNoNewlineLoop
call loadByteCall pointer.loadByte
arg loadByteCall buffer s
arg loadByteCall offset idxA
run loadByteCall
bind currentByte I8 loadByteCall

call isNullCall math.equalI64
arg isNullCall left currentByte
arg isNullCall right zeroI64a
run isNullCall
bind isNull Bool isNullCall
branchIf isNull putsNoNewlineDone

call putCall putByte
arg putCall c currentByte
run putCall
ignoreOk putCall CSignedInt32

call incCall math.addI64
arg incCall left idxA
arg incCall right oneI64a
run incCall
bind nextIdx I64 incCall
set idxA nextIdx
branch putsNoNewlineLoop

label putsNoNewlineDone
returnOk idxA


# ---- putLine(s) ----
# Like libc putLine: write s followed by a newline.
operation putLine
input putLine s CNullTerminatedByteString
output putLine Result CByteCount Void
effect putLine write console.stdout
effect putLine read memory.buffer
memory putLine heap no
memory putLine stack max 1KiB
async putLine no
purpose putLine "Write s + newline to stdout. Delegates the bytes to putString, then emits one LF via putByte."

label startPuts
call bodyCall putString
arg bodyCall s s
run bodyCall
bindOk bodyByteCount CByteCount bodyCall

const newlineCode CSignedInt32 10
call newlineCall putByte
arg newlineCall c newlineCode
run newlineCall
ignoreOk newlineCall CSignedInt32

const oneI64b I64 1
call totalCall math.addI64
arg totalCall left bodyByteCount
arg totalCall right oneI64b
run totalCall
bind totalCount CByteCount totalCall
returnOk totalCount


# ---- putIntegerDecimal(n) ----
# Print a signed 64-bit integer in decimal, then a newline. Pure AS:
# extracts digits via repeated divide-by-10 and mod-10, buffers them
# in reverse order on a stack-allocated byte array, then emits them
# in forward order through putByte. Handles negative numbers by
# emitting a '-' first and printing the absolute value.
operation putIntegerDecimal
input putIntegerDecimal n CSignedInt64
output putIntegerDecimal Result CByteCount Void
effect putIntegerDecimal write console.stdout
memory putIntegerDecimal heap no
memory putIntegerDecimal stack max 4KiB
async putIntegerDecimal no
purpose putIntegerDecimal "Pure-AS itoa-then-print: extract decimal digits from n (handling sign), buffer them in reverse on a 24-byte scratch area, then emit forward through putByte. No sprintf, no printf."

label startWriteIntDecimal

const zeroI64 I64 0
const oneI64 I64 1
const tenI64 I64 10
const negOneI64 I64 -1
const asciiZero I64 48
const asciiMinus CSignedInt32 45
const bufferBytes CByteCount 32
const zeroOffset CByteCount 0
const newlineByte CSignedInt32 10

# Allocate scratch buffer for digits (worst case: 19 digits + sign).
call allocCall c.malloc
arg allocCall size bufferBytes
run allocCall
bind digitBuffer COpaqueMemoryAddress allocCall

# Detect sign; work with the absolute value.
var workingValue I64 0
set workingValue n
var isNegative I64 0

call signCheckCall math.lessThanI64
arg signCheckCall left n
arg signCheckCall right zeroI64
run signCheckCall
bind isNegativeBool Bool signCheckCall
branchIf isNegativeBool flipSign
branch signDone

label flipSign
set isNegative oneI64
call negCall math.multiplyI64
arg negCall left n
arg negCall right negOneI64
run negCall
bind negated I64 negCall
set workingValue negated
branch signDone

label signDone

# Special case: zero. Emit '0' directly and we're done with that path.
call isZeroCall math.equalI64
arg isZeroCall left workingValue
arg isZeroCall right zeroI64
run isZeroCall
bind isZero Bool isZeroCall
branchIf isZero emitZero
branch decomposeDigits

label emitZero
const charZero CSignedInt32 48
call putZero putByte
arg putZero c charZero
run putZero
ignoreOk putZero CSignedInt32
branch emitTrailingNewline

label decomposeDigits

# Loop: repeatedly take workingValue % 10, store digit, then divide.
var digitCount I64 0

label digitLoop
call modCall math.moduloI64
arg modCall left workingValue
arg modCall right tenI64
run modCall
bind digitVal I64 modCall

call digitByteCall math.addI64
arg digitByteCall left digitVal
arg digitByteCall right asciiZero
run digitByteCall
bind digitByteValue CSignedInt32 digitByteCall

call storeDigitCall pointer.storeByte
arg storeDigitCall buffer digitBuffer
arg storeDigitCall offset digitCount
arg storeDigitCall value digitByteValue
run storeDigitCall

call incCountCall math.addI64
arg incCountCall left digitCount
arg incCountCall right oneI64
run incCountCall
bind nextCount I64 incCountCall
set digitCount nextCount

call divCall math.divideI64
arg divCall left workingValue
arg divCall right tenI64
run divCall
bind nextWorking I64 divCall
set workingValue nextWorking

call moreLeftCall math.greaterThanI64
arg moreLeftCall left workingValue
arg moreLeftCall right zeroI64
run moreLeftCall
bind moreLeft Bool moreLeftCall
branchIf moreLeft digitLoop
branch emitSign

label emitSign

# Emit minus sign if negative.
call needsSignCall math.equalI64
arg needsSignCall left isNegative
arg needsSignCall right oneI64
run needsSignCall
bind needsSign Bool needsSignCall
branchIf needsSign emitMinus
branch emitDigitsForward

label emitMinus
call putMinus putByte
arg putMinus c asciiMinus
run putMinus
ignoreOk putMinus CSignedInt32
branch emitDigitsForward

label emitDigitsForward

# digitBuffer has digitCount digit-bytes in REVERSE order (least
# significant first). Walk backwards to print most-significant first.
var emitCursor I64 0
set emitCursor digitCount

label emitNext
call atZeroCall math.equalI64
arg atZeroCall left emitCursor
arg atZeroCall right zeroI64
run atZeroCall
bind atZero Bool atZeroCall
branchIf atZero emitTrailingNewline

call decCursorCall math.subtractI64
arg decCursorCall left emitCursor
arg decCursorCall right oneI64
run decCursorCall
bind decCursor I64 decCursorCall
set emitCursor decCursor

call loadDigitCall pointer.loadByte
arg loadDigitCall buffer digitBuffer
arg loadDigitCall offset decCursor
run loadDigitCall
bind digitToEmit I8 loadDigitCall

call putDigit putByte
arg putDigit c digitToEmit
run putDigit
ignoreOk putDigit CSignedInt32

branch emitNext

label emitTrailingNewline
call putNewline putByte
arg putNewline c newlineByte
run putNewline
ignoreOk putNewline CSignedInt32

call freeCall c.free
arg freeCall ptr digitBuffer
run freeCall

returnOk digitCount


# ============================================================
# Smoke test
# ============================================================

operation putUnsignedDecimal
input putUnsignedDecimal n CSignedInt64
output putUnsignedDecimal Result CByteCount Void
effect putUnsignedDecimal write console.stdout
memory putUnsignedDecimal heap yes
async putUnsignedDecimal no
purpose putUnsignedDecimal "Print n as an unsigned decimal integer (no sign), followed by a newline. For negative n, prints the two's-complement representation as if it were unsigned. Pure AS via digit extraction."

label startPutUnsignedDecimal
const zeroU I64 0
const oneU I64 1
const tenU I64 10
const asciiZeroU I64 48
const newlineU CSignedInt32 10
const scratchU CByteCount 32
const zeroOffU CByteCount 0

# Special case: zero -> print '0\n'
call eqZeroUCall math.equalI64
arg eqZeroUCall left n
arg eqZeroUCall right zeroU
run eqZeroUCall
bind eqZeroU Bool eqZeroUCall
branchIf eqZeroU putUDecZero

call allocBufU c.malloc
arg allocBufU size scratchU
run allocBufU
bind digitBufU COpaqueMemoryAddress allocBufU

var workU I64 0
set workU n
var digCountU I64 0

label putUDecLoop
call modUCall math.moduloI64
arg modUCall left workU
arg modUCall right tenU
run modUCall
bind digValU I64 modUCall
call digByteUCall math.addI64
arg digByteUCall left digValU
arg digByteUCall right asciiZeroU
run digByteUCall
bind digByteU CSignedInt32 digByteUCall
call storeDigUCall pointer.storeByte
arg storeDigUCall buffer digitBufU
arg storeDigUCall offset digCountU
arg storeDigUCall value digByteU
run storeDigUCall
call incCountUCall math.addI64
arg incCountUCall left digCountU
arg incCountUCall right oneU
run incCountUCall
bind nextCountU I64 incCountUCall
set digCountU nextCountU
call divUCall math.divideI64
arg divUCall left workU
arg divUCall right tenU
run divUCall
bind nextWorkU I64 divUCall
set workU nextWorkU
call moreUCall math.greaterThanI64
arg moreUCall left workU
arg moreUCall right zeroU
run moreUCall
bind moreU Bool moreUCall
branchIf moreU putUDecLoop
branch putUDecEmit

label putUDecEmit
var emitCursorU I64 0
set emitCursorU digCountU
label putUDecEmitNext
call atZeroUCall math.equalI64
arg atZeroUCall left emitCursorU
arg atZeroUCall right zeroU
run atZeroUCall
bind atZeroU Bool atZeroUCall
branchIf atZeroU putUDecTrailNewline
call decUCall math.subtractI64
arg decUCall left emitCursorU
arg decUCall right oneU
run decUCall
bind decCurU I64 decUCall
set emitCursorU decCurU
call loadDigUCall pointer.loadByte
arg loadDigUCall buffer digitBufU
arg loadDigUCall offset decCurU
run loadDigUCall
bind digToEmitU I8 loadDigUCall
call putDigU putByte
arg putDigU c digToEmitU
run putDigU
ignoreOk putDigU CSignedInt32
branch putUDecEmitNext

label putUDecTrailNewline
call putNlU putByte
arg putNlU c newlineU
run putNlU
ignoreOk putNlU CSignedInt32
call freeBufU c.free
arg freeBufU ptr digitBufU
run freeBufU
returnOk digCountU

label putUDecZero
const charZeroU CSignedInt32 48
call putZeroU putByte
arg putZeroU c charZeroU
run putZeroU
ignoreOk putZeroU CSignedInt32
call putNlUZ putByte
arg putNlUZ c newlineU
run putNlUZ
ignoreOk putNlUZ CSignedInt32
const oneCB CByteCount 1
returnOk oneCB


operation putHex
input putHex n CSignedInt64
output putHex Result CByteCount Void
effect putHex write console.stdout
memory putHex heap yes
async putHex no
purpose putHex "Print n in hexadecimal (lowercase), no '0x' prefix, no leading zeros except for n == 0. Followed by a newline. Pure AS — extracts nibbles via division by 16."

label startPutHex
const zeroHx I64 0
const oneHx I64 1
const sixteenHx I64 16
const asciiZeroHx I64 48
const lowerAhx I64 87
const tenHxOff I64 10
const newlineHx CSignedInt32 10
const scratchHx CByteCount 32

call eqZeroHxCall math.equalI64
arg eqZeroHxCall left n
arg eqZeroHxCall right zeroHx
run eqZeroHxCall
bind eqZeroHx Bool eqZeroHxCall
branchIf eqZeroHx putHexZero

call allocBufHx c.malloc
arg allocBufHx size scratchHx
run allocBufHx
bind hxBuf COpaqueMemoryAddress allocBufHx

var workHx I64 0
set workHx n
var digCountHx I64 0
var digValHx I64 0

label putHexLoop
call modHxCall math.moduloI64
arg modHxCall left workHx
arg modHxCall right sixteenHx
run modHxCall
bind nibble I64 modHxCall

# Convert nibble (0..15) to ASCII: 0..9 -> '0'..'9', 10..15 -> 'a'..'f'
call below10Call math.lessThanI64
arg below10Call left nibble
arg below10Call right tenHxOff
run below10Call
bind below10 Bool below10Call
branchIf below10 nibbleDigit
branch nibbleLetter
label nibbleDigit
call digCharCall math.addI64
arg digCharCall left nibble
arg digCharCall right asciiZeroHx
run digCharCall
bind digCharHx I64 digCharCall
set digValHx digCharHx
branch nibbleEmit
label nibbleLetter
call letterCharCall math.addI64
arg letterCharCall left nibble
arg letterCharCall right lowerAhx
run letterCharCall
bind letterCharHx I64 letterCharCall
set digValHx letterCharHx
branch nibbleEmit

label nibbleEmit
call storeHxCall pointer.storeByte
arg storeHxCall buffer hxBuf
arg storeHxCall offset digCountHx
arg storeHxCall value digValHx
run storeHxCall
call incHxCall math.addI64
arg incHxCall left digCountHx
arg incHxCall right oneHx
run incHxCall
bind nextCountHx I64 incHxCall
set digCountHx nextCountHx
call divHxCall math.divideI64
arg divHxCall left workHx
arg divHxCall right sixteenHx
run divHxCall
bind nextWorkHx I64 divHxCall
set workHx nextWorkHx
call moreHxCall math.greaterThanI64
arg moreHxCall left workHx
arg moreHxCall right zeroHx
run moreHxCall
bind moreHx Bool moreHxCall
branchIf moreHx putHexLoop
branch putHexEmit

label putHexEmit
var emitCursorHx I64 0
set emitCursorHx digCountHx
label putHexEmitNext
call atZeroHxCall math.equalI64
arg atZeroHxCall left emitCursorHx
arg atZeroHxCall right zeroHx
run atZeroHxCall
bind atZeroHx Bool atZeroHxCall
branchIf atZeroHx putHexTrailNewline
call decHxCall math.subtractI64
arg decHxCall left emitCursorHx
arg decHxCall right oneHx
run decHxCall
bind decCurHx I64 decHxCall
set emitCursorHx decCurHx
call loadHxCall pointer.loadByte
arg loadHxCall buffer hxBuf
arg loadHxCall offset decCurHx
run loadHxCall
bind hxToEmit I8 loadHxCall
call putHxDigit putByte
arg putHxDigit c hxToEmit
run putHxDigit
ignoreOk putHxDigit CSignedInt32
branch putHexEmitNext

label putHexTrailNewline
call putNlHx putByte
arg putNlHx c newlineHx
run putNlHx
ignoreOk putNlHx CSignedInt32
call freeBufHx c.free
arg freeBufHx ptr hxBuf
run freeBufHx
returnOk digCountHx

label putHexZero
const charZeroHx CSignedInt32 48
call putZeroHx putByte
arg putZeroHx c charZeroHx
run putZeroHx
ignoreOk putZeroHx CSignedInt32
call putNlHxZ putByte
arg putNlHxZ c newlineHx
run putNlHxZ
ignoreOk putNlHxZ CSignedInt32
const oneCBhx CByteCount 1
returnOk oneCBhx


operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap yes
memory main stack max 16KiB
async main no
purpose main "Smoke-test the AgentScript stdlib stdio operations: putLine, putString, putIntegerDecimal, putUnsignedDecimal, putHex. Expected stdout (7 lines):\nHello, AgentScript stdlib!\nno-newline-then-putLine\n42\n-1234\n0\n255\nff"

label startMain

const greeting CNullTerminatedByteString "Hello, AgentScript stdlib!"
call putsGreeting putLine
arg putsGreeting s greeting
run putsGreeting
ignoreOk putsGreeting CByteCount

const noNl CNullTerminatedByteString "no-newline-then-putLine"
call putNoNl putString
arg putNoNl s noNl
run putNoNl
ignoreOk putNoNl CByteCount

const emptyMarker CNullTerminatedByteString ""
call putEmpty putLine
arg putEmpty s emptyMarker
run putEmpty
ignoreOk putEmpty CByteCount

const fortyTwo CSignedInt64 42
call put42 putIntegerDecimal
arg put42 n fortyTwo
run put42
ignoreOk put42 CByteCount

const negThing CSignedInt64 -1234
call putNeg putIntegerDecimal
arg putNeg n negThing
run putNeg
ignoreOk putNeg CByteCount

const zeroVal CSignedInt64 0
call put0 putIntegerDecimal
arg put0 n zeroVal
run put0
ignoreOk put0 CByteCount

const u255 CSignedInt64 255
call putU putUnsignedDecimal
arg putU n u255
run putU
ignoreOk putU CByteCount

call putH putHex
arg putH n u255
run putH
ignoreOk putH CByteCount

const exitOk ExitCode 0
returnOk exitOk
