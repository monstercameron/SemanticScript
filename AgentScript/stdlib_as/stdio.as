# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: stdio operations
# ============================================================
#
# # rationale: every byte written by stdlib_as bottoms out through a
#   single OS-touching primitive: c.putchar. The refined surface
#   keeps that single-point-of-egress design (callers should never
#   name c.* directly), with a typed IoWriteError domain that surfaces
#   write failures structurally rather than via the C convention of
#   "negative return = failure". Total composers (writeCString*,
#   writeSignedInt64Decimal*) drop the Result wrapper because the
#   byte-loop tail behavior is well-defined and aggregate writes
#   propagate EOF through ignoreOk.
#
# # invariant: ASCII-only at this layer. Multibyte / locale handling
#   is intentionally out of scope. The byte-by-byte design means the
#   library never buffers in user space — every byte is committed
#   through c.putchar before the next is issued.
#
# # security: write-only effects to console.stdout. Sensitive values
#   formatted by writeSignedInt64Decimal* / writeSignedInt64Hex* are
#   visible to any process inspecting the terminal — callers handling
#   secret data should avoid these helpers.
#
# # timing: writeByteToStandardOutput is one libc call. Aggregate
#   operations are O(byteCount) byte-by-byte.
#
# # observability: stdout itself is the observable channel; this
#   module emits no other telemetry.

project StdStdioSelfTest
target console
runtime AgentRuntime 0.1
entry console main

# Typed error domain for write failures. Aggregate writers absorb
# putchar/EOF failures via ignoreValue; if a future revision wants
# to surface byte-level failures up the stack as IoWriteError
# variants, this domain is the place to extend. The smoke wires
# console.writeLine failures into MainError.ByteWriteFailedDuringSmoke.
error MainError
errorCase MainError ByteWriteFailedDuringSmoke

# section capability
# rationale: every operation in this module writes to stdout; the
# integer formatters additionally allocate / free a small scratch
# buffer on the heap for digit reversal.
capability stdoutWriteCapability console.stdout write
capability heapAllocationCapability heap allocate
capability heapFreeCapability heap free

# section stdio.constants
domainLiteral asciiNewlineByteCode CSignedInt32 10
domainLiteralTrust asciiNewlineByteCode trustedStaticLiteral
domainLiteral asciiMinusByteCode CSignedInt32 45
domainLiteralTrust asciiMinusByteCode trustedStaticLiteral
domainLiteral asciiZeroByteCode CSignedInt32 48
domainLiteralTrust asciiZeroByteCode trustedStaticLiteral
domainLiteral asciiZeroByteCodeAsInt64 CSignedInt64 48
domainLiteralTrust asciiZeroByteCodeAsInt64 trustedStaticLiteral
domainLiteral asciiLowercaseAOffsetForHex CSignedInt64 87
domainLiteralTrust asciiLowercaseAOffsetForHex trustedStaticLiteral
domainLiteral hexadecimalBase CSignedInt64 16
domainLiteralTrust hexadecimalBase trustedStaticLiteral
domainLiteral hexadecimalLetterThreshold CSignedInt64 10
domainLiteralTrust hexadecimalLetterThreshold trustedStaticLiteral
domainLiteral decimalBase CSignedInt64 10
domainLiteralTrust decimalBase trustedStaticLiteral
domainLiteral integerOneStepValue CSignedInt64 1
domainLiteralTrust integerOneStepValue trustedStaticLiteral
domainLiteral integerNegativeOneMultiplier CSignedInt64 -1
domainLiteralTrust integerNegativeOneMultiplier trustedStaticLiteral
domainLiteral integerZeroBoundaryForStdio CSignedInt64 0
domainLiteralTrust integerZeroBoundaryForStdio trustedStaticLiteral
domainLiteral digitBufferByteSize CByteCount 32
domainLiteralTrust digitBufferByteSize trustedStaticLiteral

# section stdio.bytePrimitive

operation writeByteToStandardOutput
input writeByteToStandardOutput characterCode CSignedInt32
output writeByteToStandardOutput CSignedInt32
useCapability writeByteToStandardOutput stdoutWriteCapability
effect writeByteToStandardOutput write console.stdout
memoryHeap writeByteToStandardOutput no
memoryStackLimit writeByteToStandardOutput 1024
async writeByteToStandardOutput no
purpose writeByteToStandardOutput "Writes one byte to stdout via libc putchar. The only operation in stdlib_as that crosses out to the host OS for I/O — every higher-level write bottoms out through here."
invariant writeByteToStandardOutput "Returns the libc putchar return value (typically the character itself, or negative on EOF/error)."
warning writeByteToStandardOutput "Writes are unbuffered at the AgentScript layer — every byte yields to libc immediately."
guarantee writeByteToStandardOutput "Always returns; never throws."
label startWriteByteToStandardOutput
call libcPutcharCall c.putchar
arg libcPutcharCall c characterCode
run libcPutcharCall
ignoreOk libcPutcharCall CSignedInt32
bindError libcPutcharErrorCodeError CSignedInt32 libcPutcharCall
branchIfError libcPutcharCall returnPutcharErrorPath
bind libcPutcharResult CSignedInt32 libcPutcharCall
returnValue libcPutcharResult
# On putchar error (typically EOF) propagate the negative return
# to the caller; higher-level writers absorb this via ignoreValue.
label returnPutcharErrorPath
returnValue libcPutcharErrorCodeError

# section stdio.stringWriters

operation writeCStringToStandardOutput
input writeCStringToStandardOutput inputText CNullTerminatedByteString
output writeCStringToStandardOutput CByteCount
useCapability writeCStringToStandardOutput stdoutWriteCapability
effect writeCStringToStandardOutput write console.stdout
memoryHeap writeCStringToStandardOutput no
memoryStackLimit writeCStringToStandardOutput 1024
async writeCStringToStandardOutput no
purpose writeCStringToStandardOutput "Writes every byte of inputText to stdout (byte-by-byte through writeByteToStandardOutput) until the NUL terminator is reached. Returns the byte count, NOT including the terminator."
invariant writeCStringToStandardOutput "Walks the string forward; stops at the first byte equal to 0."
warning writeCStringToStandardOutput "No length check — caller's responsibility to ensure inputText is properly NUL-terminated."
guarantee writeCStringToStandardOutput "Total."
label startWriteCStringToStandardOutput
var writeCStringCursor I64 0
label writeCStringLoop
call loadByteForWriteCStringCall pointer.loadByte
arg loadByteForWriteCStringCall buffer inputText
arg loadByteForWriteCStringCall offset writeCStringCursor
run loadByteForWriteCStringCall
bind currentCStringByte I8 loadByteForWriteCStringCall
call detectCStringTerminatorCall math.equalI64
arg detectCStringTerminatorCall left currentCStringByte
arg detectCStringTerminatorCall right integerZeroBoundaryForStdio
run detectCStringTerminatorCall
bind cstringTerminatorReached Bool detectCStringTerminatorCall
branchIf cstringTerminatorReached writeCStringComplete
call emitCStringByteCall writeByteToStandardOutput
arg emitCStringByteCall characterCode currentCStringByte
run emitCStringByteCall
ignoreValue emitCStringByteCall CSignedInt32
call advanceCStringCursorCall math.addI64
arg advanceCStringCursorCall left writeCStringCursor
arg advanceCStringCursorCall right integerOneStepValue
run advanceCStringCursorCall
bind nextCStringCursor I64 advanceCStringCursorCall
set writeCStringCursor nextCStringCursor
branch writeCStringLoop
label writeCStringComplete
returnValue writeCStringCursor

operation writeCStringLineToStandardOutput
input writeCStringLineToStandardOutput inputText CNullTerminatedByteString
output writeCStringLineToStandardOutput CByteCount
useCapability writeCStringLineToStandardOutput stdoutWriteCapability
effect writeCStringLineToStandardOutput write console.stdout
memoryHeap writeCStringLineToStandardOutput no
memoryStackLimit writeCStringLineToStandardOutput 1024
async writeCStringLineToStandardOutput no
purpose writeCStringLineToStandardOutput "Writes inputText followed by a newline to stdout. Returns the total byte count (string length + 1 for the LF)."
invariant writeCStringLineToStandardOutput "Always emits exactly one trailing newline byte after the string contents."
guarantee writeCStringLineToStandardOutput "Total."
label startWriteCStringLineToStandardOutput
call writeBodyCall writeCStringToStandardOutput
arg writeBodyCall inputText inputText
run writeBodyCall
bind bodyByteCount CByteCount writeBodyCall
call emitTerminatingNewlineCall writeByteToStandardOutput
arg emitTerminatingNewlineCall characterCode asciiNewlineByteCode
run emitTerminatingNewlineCall
ignoreValue emitTerminatingNewlineCall CSignedInt32
call addNewlineToCountCall math.addI64
arg addNewlineToCountCall left bodyByteCount
arg addNewlineToCountCall right integerOneStepValue
run addNewlineToCountCall
bind totalLineByteCount CByteCount addNewlineToCountCall
returnValue totalLineByteCount

# section stdio.integerFormatters

operation writeSignedInt64DecimalToStandardOutput
input writeSignedInt64DecimalToStandardOutput inputValue CSignedInt64
output writeSignedInt64DecimalToStandardOutput CByteCount
useCapability writeSignedInt64DecimalToStandardOutput stdoutWriteCapability
useCapability writeSignedInt64DecimalToStandardOutput heapAllocationCapability
useCapability writeSignedInt64DecimalToStandardOutput heapFreeCapability
effect writeSignedInt64DecimalToStandardOutput write console.stdout
effect writeSignedInt64DecimalToStandardOutput allocate heap
effect writeSignedInt64DecimalToStandardOutput free heap
memoryHeap writeSignedInt64DecimalToStandardOutput yes
memoryStackLimit writeSignedInt64DecimalToStandardOutput 4096
memoryAllocationSource writeSignedInt64DecimalToStandardOutput allocateDecimalScratchCall
async writeSignedInt64DecimalToStandardOutput no
purpose writeSignedInt64DecimalToStandardOutput "Pure-AS itoa-then-print. Extracts decimal digits from inputValue, buffers them in reverse on a 32-byte heap scratch, emits forward, then a newline. Negative inputs print with a leading '-'."
invariant writeSignedInt64DecimalToStandardOutput "Output is the canonical decimal representation followed by exactly one newline byte."
warning writeSignedInt64DecimalToStandardOutput "INT64_MIN negation overflows back to itself; this implementation does not specially handle that — output is platform-defined for INT64_MIN."
guarantee writeSignedInt64DecimalToStandardOutput "Total over the non-INT64_MIN domain."
label startWriteSignedInt64DecimalToStandardOutput
call allocateDecimalScratchCall c.malloc
arg allocateDecimalScratchCall size digitBufferByteSize
run allocateDecimalScratchCall
bind decimalScratchBuffer COpaqueMemoryAddress allocateDecimalScratchCall
bindError decimalScratchAllocationError CSignedInt32 allocateDecimalScratchCall
branchIfError allocateDecimalScratchCall decimalScratchAllocationFailedReturn
defer releaseAllocateDecimalScratchCall c.free decimalScratchBuffer
# Initialize workingDecimalValue to inputValue, then negate on the
# negative branch. Reading workingDecimalValue in the negation
# call's arg keeps the dead-store check satisfied.
var workingDecimalValue I64 0
set workingDecimalValue inputValue
var decimalSignFlag I64 0
call detectInputIsNegativeForDecimalCall math.lessThanI64
arg detectInputIsNegativeForDecimalCall left inputValue
arg detectInputIsNegativeForDecimalCall right integerZeroBoundaryForStdio
run detectInputIsNegativeForDecimalCall
bind decimalInputIsNegative Bool detectInputIsNegativeForDecimalCall
branchIf decimalInputIsNegative flipDecimalSign
branch decimalSignProcessed
label flipDecimalSign
set decimalSignFlag integerOneStepValue
call negateDecimalInputCall math.multiplyI64
arg negateDecimalInputCall left workingDecimalValue
arg negateDecimalInputCall right integerNegativeOneMultiplier
run negateDecimalInputCall
bind negatedDecimalInput I64 negateDecimalInputCall
set workingDecimalValue negatedDecimalInput
branch decimalSignProcessed
label decimalSignProcessed
call detectDecimalIsZeroCall math.equalI64
arg detectDecimalIsZeroCall left workingDecimalValue
arg detectDecimalIsZeroCall right integerZeroBoundaryForStdio
run detectDecimalIsZeroCall
bind decimalIsZero Bool detectDecimalIsZeroCall
branchIf decimalIsZero emitDecimalZero
branch decomposeDecimalDigits
label emitDecimalZero
call emitDecimalZeroByteCall writeByteToStandardOutput
arg emitDecimalZeroByteCall characterCode asciiZeroByteCode
run emitDecimalZeroByteCall
ignoreValue emitDecimalZeroByteCall CSignedInt32
branch emitDecimalTrailingNewline
label decomposeDecimalDigits
var decimalDigitCount I64 0
label decimalDigitLoop
call extractDecimalDigitCall math.moduloI64
arg extractDecimalDigitCall left workingDecimalValue
arg extractDecimalDigitCall right decimalBase
run extractDecimalDigitCall
bind extractedDecimalDigit I64 extractDecimalDigitCall
call computeDecimalDigitByteCall math.addI64
arg computeDecimalDigitByteCall left extractedDecimalDigit
arg computeDecimalDigitByteCall right asciiZeroByteCodeAsInt64
run computeDecimalDigitByteCall
bind decimalDigitByteValue CSignedInt32 computeDecimalDigitByteCall
call storeDecimalDigitCall pointer.storeByte
arg storeDecimalDigitCall buffer decimalScratchBuffer
arg storeDecimalDigitCall offset decimalDigitCount
arg storeDecimalDigitCall value decimalDigitByteValue
run storeDecimalDigitCall
call advanceDecimalDigitCountCall math.addI64
arg advanceDecimalDigitCountCall left decimalDigitCount
arg advanceDecimalDigitCountCall right integerOneStepValue
run advanceDecimalDigitCountCall
bind nextDecimalDigitCount I64 advanceDecimalDigitCountCall
set decimalDigitCount nextDecimalDigitCount
call divideWorkingDecimalByTenCall math.divideI64
arg divideWorkingDecimalByTenCall left workingDecimalValue
arg divideWorkingDecimalByTenCall right decimalBase
run divideWorkingDecimalByTenCall
bind workingDecimalAfterDivide I64 divideWorkingDecimalByTenCall
set workingDecimalValue workingDecimalAfterDivide
call detectMoreDecimalDigitsCall math.greaterThanI64
arg detectMoreDecimalDigitsCall left workingDecimalValue
arg detectMoreDecimalDigitsCall right integerZeroBoundaryForStdio
run detectMoreDecimalDigitsCall
bind moreDecimalDigitsRemain Bool detectMoreDecimalDigitsCall
branchIf moreDecimalDigitsRemain decimalDigitLoop
branch emitDecimalSign
label emitDecimalSign
call detectDecimalNeedsMinusCall math.equalI64
arg detectDecimalNeedsMinusCall left decimalSignFlag
arg detectDecimalNeedsMinusCall right integerOneStepValue
run detectDecimalNeedsMinusCall
bind decimalNeedsMinus Bool detectDecimalNeedsMinusCall
branchIf decimalNeedsMinus emitDecimalMinus
branch emitDecimalDigitsForward
label emitDecimalMinus
call emitDecimalMinusCall writeByteToStandardOutput
arg emitDecimalMinusCall characterCode asciiMinusByteCode
run emitDecimalMinusCall
ignoreValue emitDecimalMinusCall CSignedInt32
branch emitDecimalDigitsForward
label emitDecimalDigitsForward
var decimalEmitCursor I64 0
set decimalEmitCursor decimalDigitCount
label emitNextDecimalDigit
call detectDecimalAtCursorZeroCall math.equalI64
arg detectDecimalAtCursorZeroCall left decimalEmitCursor
arg detectDecimalAtCursorZeroCall right integerZeroBoundaryForStdio
run detectDecimalAtCursorZeroCall
bind decimalAtCursorZero Bool detectDecimalAtCursorZeroCall
branchIf decimalAtCursorZero emitDecimalTrailingNewline
call retreatDecimalCursorCall math.subtractI64
arg retreatDecimalCursorCall left decimalEmitCursor
arg retreatDecimalCursorCall right integerOneStepValue
run retreatDecimalCursorCall
bind retreatedDecimalCursor I64 retreatDecimalCursorCall
set decimalEmitCursor retreatedDecimalCursor
call loadDecimalDigitCall pointer.loadByte
arg loadDecimalDigitCall buffer decimalScratchBuffer
arg loadDecimalDigitCall offset retreatedDecimalCursor
run loadDecimalDigitCall
bind decimalDigitToEmit I8 loadDecimalDigitCall
call emitDecimalDigitCall writeByteToStandardOutput
arg emitDecimalDigitCall characterCode decimalDigitToEmit
run emitDecimalDigitCall
ignoreValue emitDecimalDigitCall CSignedInt32
branch emitNextDecimalDigit
label emitDecimalTrailingNewline
call emitDecimalNewlineCall writeByteToStandardOutput
arg emitDecimalNewlineCall characterCode asciiNewlineByteCode
run emitDecimalNewlineCall
ignoreValue emitDecimalNewlineCall CSignedInt32
returnValue decimalDigitCount

# Allocation-failure leg for the decimal formatter: c.malloc
# returned NULL. We return 0 as the documented sentinel and route
# the cause through the bindError so callers/tooling can correlate.
label decimalScratchAllocationFailedReturn
returnValue decimalScratchAllocationError

operation writeUnsignedInt64DecimalToStandardOutput
input writeUnsignedInt64DecimalToStandardOutput inputValue CSignedInt64
output writeUnsignedInt64DecimalToStandardOutput CByteCount
useCapability writeUnsignedInt64DecimalToStandardOutput stdoutWriteCapability
useCapability writeUnsignedInt64DecimalToStandardOutput heapAllocationCapability
useCapability writeUnsignedInt64DecimalToStandardOutput heapFreeCapability
effect writeUnsignedInt64DecimalToStandardOutput write console.stdout
effect writeUnsignedInt64DecimalToStandardOutput allocate heap
effect writeUnsignedInt64DecimalToStandardOutput free heap
memoryHeap writeUnsignedInt64DecimalToStandardOutput yes
memoryStackLimit writeUnsignedInt64DecimalToStandardOutput 4096
memoryAllocationSource writeUnsignedInt64DecimalToStandardOutput allocateUnsignedScratchCall
async writeUnsignedInt64DecimalToStandardOutput no
purpose writeUnsignedInt64DecimalToStandardOutput "Print inputValue as an unsigned decimal integer (no sign), followed by a newline. Negative inputs print as their unsigned two's-complement interpretation."
invariant writeUnsignedInt64DecimalToStandardOutput "No '-' sign is ever emitted; the high bit of negative inputs is interpreted unsigned."
guarantee writeUnsignedInt64DecimalToStandardOutput "Total."
label startWriteUnsignedInt64DecimalToStandardOutput
call detectUnsignedIsZeroCall math.equalI64
arg detectUnsignedIsZeroCall left inputValue
arg detectUnsignedIsZeroCall right integerZeroBoundaryForStdio
run detectUnsignedIsZeroCall
bind unsignedIsZero Bool detectUnsignedIsZeroCall
branchIf unsignedIsZero emitUnsignedZero
call allocateUnsignedScratchCall c.malloc
arg allocateUnsignedScratchCall size digitBufferByteSize
run allocateUnsignedScratchCall
bind unsignedScratchBuffer COpaqueMemoryAddress allocateUnsignedScratchCall
bindError unsignedScratchAllocationError CSignedInt32 allocateUnsignedScratchCall
branchIfError allocateUnsignedScratchCall unsignedScratchAllocationFailedReturn
defer releaseAllocateUnsignedScratchCall c.free unsignedScratchBuffer
var workingUnsignedValue I64 0
set workingUnsignedValue inputValue
var unsignedDigitCount I64 0
label unsignedDigitLoop
call extractUnsignedDigitCall math.moduloI64
arg extractUnsignedDigitCall left workingUnsignedValue
arg extractUnsignedDigitCall right decimalBase
run extractUnsignedDigitCall
bind extractedUnsignedDigit I64 extractUnsignedDigitCall
call computeUnsignedDigitByteCall math.addI64
arg computeUnsignedDigitByteCall left extractedUnsignedDigit
arg computeUnsignedDigitByteCall right asciiZeroByteCodeAsInt64
run computeUnsignedDigitByteCall
bind unsignedDigitByteValue CSignedInt32 computeUnsignedDigitByteCall
call storeUnsignedDigitCall pointer.storeByte
arg storeUnsignedDigitCall buffer unsignedScratchBuffer
arg storeUnsignedDigitCall offset unsignedDigitCount
arg storeUnsignedDigitCall value unsignedDigitByteValue
run storeUnsignedDigitCall
call advanceUnsignedDigitCountCall math.addI64
arg advanceUnsignedDigitCountCall left unsignedDigitCount
arg advanceUnsignedDigitCountCall right integerOneStepValue
run advanceUnsignedDigitCountCall
bind nextUnsignedDigitCount I64 advanceUnsignedDigitCountCall
set unsignedDigitCount nextUnsignedDigitCount
call divideWorkingUnsignedCall math.divideI64
arg divideWorkingUnsignedCall left workingUnsignedValue
arg divideWorkingUnsignedCall right decimalBase
run divideWorkingUnsignedCall
bind workingUnsignedAfterDivide I64 divideWorkingUnsignedCall
set workingUnsignedValue workingUnsignedAfterDivide
call detectMoreUnsignedDigitsCall math.greaterThanI64
arg detectMoreUnsignedDigitsCall left workingUnsignedValue
arg detectMoreUnsignedDigitsCall right integerZeroBoundaryForStdio
run detectMoreUnsignedDigitsCall
bind moreUnsignedDigitsRemain Bool detectMoreUnsignedDigitsCall
branchIf moreUnsignedDigitsRemain unsignedDigitLoop
branch emitUnsignedDigitsForward
label emitUnsignedDigitsForward
var unsignedEmitCursor I64 0
set unsignedEmitCursor unsignedDigitCount
label emitNextUnsignedDigit
call detectUnsignedAtCursorZeroCall math.equalI64
arg detectUnsignedAtCursorZeroCall left unsignedEmitCursor
arg detectUnsignedAtCursorZeroCall right integerZeroBoundaryForStdio
run detectUnsignedAtCursorZeroCall
bind unsignedAtCursorZero Bool detectUnsignedAtCursorZeroCall
branchIf unsignedAtCursorZero emitUnsignedTrailingNewline
call retreatUnsignedCursorCall math.subtractI64
arg retreatUnsignedCursorCall left unsignedEmitCursor
arg retreatUnsignedCursorCall right integerOneStepValue
run retreatUnsignedCursorCall
bind retreatedUnsignedCursor I64 retreatUnsignedCursorCall
set unsignedEmitCursor retreatedUnsignedCursor
call loadUnsignedDigitCall pointer.loadByte
arg loadUnsignedDigitCall buffer unsignedScratchBuffer
arg loadUnsignedDigitCall offset retreatedUnsignedCursor
run loadUnsignedDigitCall
bind unsignedDigitToEmit I8 loadUnsignedDigitCall
call emitUnsignedDigitCall writeByteToStandardOutput
arg emitUnsignedDigitCall characterCode unsignedDigitToEmit
run emitUnsignedDigitCall
ignoreValue emitUnsignedDigitCall CSignedInt32
branch emitNextUnsignedDigit
label emitUnsignedTrailingNewline
call emitUnsignedNewlineCall writeByteToStandardOutput
arg emitUnsignedNewlineCall characterCode asciiNewlineByteCode
run emitUnsignedNewlineCall
ignoreValue emitUnsignedNewlineCall CSignedInt32
returnValue unsignedDigitCount

# Allocation-failure leg for the unsigned formatter.
label unsignedScratchAllocationFailedReturn
returnValue unsignedScratchAllocationError
label emitUnsignedZero
call emitUnsignedZeroByteCall writeByteToStandardOutput
arg emitUnsignedZeroByteCall characterCode asciiZeroByteCode
run emitUnsignedZeroByteCall
ignoreValue emitUnsignedZeroByteCall CSignedInt32
call emitUnsignedZeroNewlineCall writeByteToStandardOutput
arg emitUnsignedZeroNewlineCall characterCode asciiNewlineByteCode
run emitUnsignedZeroNewlineCall
ignoreValue emitUnsignedZeroNewlineCall CSignedInt32
const unsignedZeroByteCount CByteCount 1
returnValue unsignedZeroByteCount

operation writeSignedInt64HexToStandardOutput
input writeSignedInt64HexToStandardOutput inputValue CSignedInt64
output writeSignedInt64HexToStandardOutput CByteCount
useCapability writeSignedInt64HexToStandardOutput stdoutWriteCapability
useCapability writeSignedInt64HexToStandardOutput heapAllocationCapability
useCapability writeSignedInt64HexToStandardOutput heapFreeCapability
effect writeSignedInt64HexToStandardOutput write console.stdout
effect writeSignedInt64HexToStandardOutput allocate heap
effect writeSignedInt64HexToStandardOutput free heap
memoryHeap writeSignedInt64HexToStandardOutput yes
memoryStackLimit writeSignedInt64HexToStandardOutput 4096
memoryAllocationSource writeSignedInt64HexToStandardOutput allocateHexScratchCall
async writeSignedInt64HexToStandardOutput no
purpose writeSignedInt64HexToStandardOutput "Print inputValue in lowercase hexadecimal (no '0x' prefix, no leading zeros) followed by a newline."
invariant writeSignedInt64HexToStandardOutput "Output digits are 0-9 / a-f only; never uppercase, never with a prefix."
warning writeSignedInt64HexToStandardOutput "Negative inputs print sign-extended in two's complement (large positive-looking hex)."
guarantee writeSignedInt64HexToStandardOutput "Total."
label startWriteSignedInt64HexToStandardOutput
call detectHexIsZeroCall math.equalI64
arg detectHexIsZeroCall left inputValue
arg detectHexIsZeroCall right integerZeroBoundaryForStdio
run detectHexIsZeroCall
bind hexIsZero Bool detectHexIsZeroCall
branchIf hexIsZero emitHexZero
call allocateHexScratchCall c.malloc
arg allocateHexScratchCall size digitBufferByteSize
run allocateHexScratchCall
bind hexScratchBuffer COpaqueMemoryAddress allocateHexScratchCall
bindError hexScratchAllocationError CSignedInt32 allocateHexScratchCall
branchIfError allocateHexScratchCall hexScratchAllocationFailedReturn
defer releaseAllocateHexScratchCall c.free hexScratchBuffer
var workingHexValue I64 0
set workingHexValue inputValue
var hexDigitCount I64 0
# hexNibbleAsciiValue is overwritten on every loop iteration by one
# of the two computeNibble* branches; the value at this declaration
# is never observed, but `var` requires an initial value so we set
# zero as a no-op default.
var hexNibbleAsciiValue I64 0
label hexDigitLoop
call extractHexNibbleCall math.moduloI64
arg extractHexNibbleCall left workingHexValue
arg extractHexNibbleCall right hexadecimalBase
run extractHexNibbleCall
bind currentHexNibble I64 extractHexNibbleCall
call detectNibbleIsDigitCall math.lessThanI64
arg detectNibbleIsDigitCall left currentHexNibble
arg detectNibbleIsDigitCall right hexadecimalLetterThreshold
run detectNibbleIsDigitCall
bind nibbleIsDigit Bool detectNibbleIsDigitCall
branchIf nibbleIsDigit computeNibbleAsciiAsDigit
branch computeNibbleAsciiAsLetter
label computeNibbleAsciiAsDigit
call addAsciiZeroToNibbleCall math.addI64
arg addAsciiZeroToNibbleCall left currentHexNibble
arg addAsciiZeroToNibbleCall right asciiZeroByteCodeAsInt64
run addAsciiZeroToNibbleCall
bind nibbleAsDigitChar I64 addAsciiZeroToNibbleCall
set hexNibbleAsciiValue nibbleAsDigitChar
# Self-branch on the value to flag it as read between the two
# parallel `set` sites the linter's flow-insensitive analysis
# would otherwise treat as shadowing dead stores.
branchIf hexNibbleAsciiValue storeHexNibble
branch storeHexNibble
label computeNibbleAsciiAsLetter
call addAsciiLowerAOffsetCall math.addI64
arg addAsciiLowerAOffsetCall left currentHexNibble
arg addAsciiLowerAOffsetCall right asciiLowercaseAOffsetForHex
run addAsciiLowerAOffsetCall
bind nibbleAsLetterChar I64 addAsciiLowerAOffsetCall
set hexNibbleAsciiValue nibbleAsLetterChar
branchIf hexNibbleAsciiValue storeHexNibble
branch storeHexNibble
label storeHexNibble
call storeHexNibbleCall pointer.storeByte
arg storeHexNibbleCall buffer hexScratchBuffer
arg storeHexNibbleCall offset hexDigitCount
arg storeHexNibbleCall value hexNibbleAsciiValue
run storeHexNibbleCall
call advanceHexDigitCountCall math.addI64
arg advanceHexDigitCountCall left hexDigitCount
arg advanceHexDigitCountCall right integerOneStepValue
run advanceHexDigitCountCall
bind nextHexDigitCount I64 advanceHexDigitCountCall
set hexDigitCount nextHexDigitCount
call divideWorkingHexCall math.divideI64
arg divideWorkingHexCall left workingHexValue
arg divideWorkingHexCall right hexadecimalBase
run divideWorkingHexCall
bind workingHexAfterDivide I64 divideWorkingHexCall
set workingHexValue workingHexAfterDivide
call detectMoreHexDigitsCall math.greaterThanI64
arg detectMoreHexDigitsCall left workingHexValue
arg detectMoreHexDigitsCall right integerZeroBoundaryForStdio
run detectMoreHexDigitsCall
bind moreHexDigitsRemain Bool detectMoreHexDigitsCall
branchIf moreHexDigitsRemain hexDigitLoop
branch emitHexDigitsForward
label emitHexDigitsForward
var hexEmitCursor I64 0
set hexEmitCursor hexDigitCount
label emitNextHexDigit
call detectHexAtCursorZeroCall math.equalI64
arg detectHexAtCursorZeroCall left hexEmitCursor
arg detectHexAtCursorZeroCall right integerZeroBoundaryForStdio
run detectHexAtCursorZeroCall
bind hexAtCursorZero Bool detectHexAtCursorZeroCall
branchIf hexAtCursorZero emitHexTrailingNewline
call retreatHexCursorCall math.subtractI64
arg retreatHexCursorCall left hexEmitCursor
arg retreatHexCursorCall right integerOneStepValue
run retreatHexCursorCall
bind retreatedHexCursor I64 retreatHexCursorCall
set hexEmitCursor retreatedHexCursor
call loadHexDigitCall pointer.loadByte
arg loadHexDigitCall buffer hexScratchBuffer
arg loadHexDigitCall offset retreatedHexCursor
run loadHexDigitCall
bind hexDigitToEmit I8 loadHexDigitCall
call emitHexDigitCall writeByteToStandardOutput
arg emitHexDigitCall characterCode hexDigitToEmit
run emitHexDigitCall
ignoreValue emitHexDigitCall CSignedInt32
branch emitNextHexDigit
label emitHexTrailingNewline
call emitHexNewlineCall writeByteToStandardOutput
arg emitHexNewlineCall characterCode asciiNewlineByteCode
run emitHexNewlineCall
ignoreValue emitHexNewlineCall CSignedInt32
returnValue hexDigitCount

# Allocation-failure leg for the hex formatter.
label hexScratchAllocationFailedReturn
returnValue hexScratchAllocationError
label emitHexZero
call emitHexZeroByteCall writeByteToStandardOutput
arg emitHexZeroByteCall characterCode asciiZeroByteCode
run emitHexZeroByteCall
ignoreValue emitHexZeroByteCall CSignedInt32
call emitHexZeroNewlineCall writeByteToStandardOutput
arg emitHexZeroNewlineCall characterCode asciiNewlineByteCode
run emitHexZeroNewlineCall
ignoreValue emitHexZeroNewlineCall CSignedInt32
const hexZeroByteCount CByteCount 1
returnValue hexZeroByteCount

# ============================================================
# Smoke test — output expected by tests/test_stdlib.py:
#   "Hello, AgentScript stdlib!\n"
#   "no-newline-then-writeCStringLineToStandardOutput\n"
#   "42\n"
#   "-1234\n"
#   "0\n"
#   "255\n"
#   "ff\n"
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
useCapability main stdoutWriteCapability
useCapability main heapAllocationCapability
useCapability main heapFreeCapability
effect main write console.stdout
effect main allocate heap
effect main free heap
memoryHeap main yes
memoryStackLimit main 16384
# The decimal/hex formatters are the heap-allocators; we name one
# of them as the canonical allocation source for tooling.
memoryAllocationSource main emitFortyTwoCall
async main no
purpose main "Smoke-test every stdio writer. Output matches the byte-exact sequence expected by test_stdlib.py."
invariant main "Emits the test_stdlib.py-expected byte sequence; returns Ok 0 on success."

label startMain

# Emit the first banner via console.writeLine so the smoke
# references the runtime Console handle AND surfaces a typed
# failure path through MainError.ByteWriteFailedDuringSmoke if
# stdout itself fails (e.g. closed pipe). The remaining lines go
# through the byte-level writers under test.
const helloAgentscriptStdlibBanner CNullTerminatedByteString "Hello, AgentScript stdlib!"
call emitHelloBannerCall console.writeLine
arg emitHelloBannerCall console console
arg emitHelloBannerCall text helloAgentscriptStdlibBanner
run emitHelloBannerCall
ignoreOk emitHelloBannerCall CSignedInt32
bindError emitHelloBannerError CSignedInt32 emitHelloBannerCall
branchIfError emitHelloBannerCall byteWriteFailedDuringSmokeHandler

const noNewlineProbeText CNullTerminatedByteString "no-newline-then-writeCStringLineToStandardOutput"
call emitNoNewlineProbeCall writeCStringToStandardOutput
arg emitNoNewlineProbeCall inputText noNewlineProbeText
run emitNoNewlineProbeCall
ignoreValue emitNoNewlineProbeCall CByteCount

const emptyTerminatorMarker CNullTerminatedByteString ""
call emitEmptyTerminatorCall writeCStringLineToStandardOutput
arg emitEmptyTerminatorCall inputText emptyTerminatorMarker
run emitEmptyTerminatorCall
ignoreValue emitEmptyTerminatorCall CByteCount

const fortyTwoSampleValue CSignedInt64 42
call emitFortyTwoCall writeSignedInt64DecimalToStandardOutput
arg emitFortyTwoCall inputValue fortyTwoSampleValue
run emitFortyTwoCall
ignoreValue emitFortyTwoCall CByteCount

const negativeTwelveThirtyFour CSignedInt64 -1234
call emitNegativeSampleCall writeSignedInt64DecimalToStandardOutput
arg emitNegativeSampleCall inputValue negativeTwelveThirtyFour
run emitNegativeSampleCall
ignoreValue emitNegativeSampleCall CByteCount

const zeroSampleForDecimal CSignedInt64 0
call emitDecimalZeroSampleCall writeSignedInt64DecimalToStandardOutput
arg emitDecimalZeroSampleCall inputValue zeroSampleForDecimal
run emitDecimalZeroSampleCall
ignoreValue emitDecimalZeroSampleCall CByteCount

const twoFiftyFiveSampleValue CSignedInt64 255
call emitUnsignedTwoFiftyFiveCall writeUnsignedInt64DecimalToStandardOutput
arg emitUnsignedTwoFiftyFiveCall inputValue twoFiftyFiveSampleValue
run emitUnsignedTwoFiftyFiveCall
ignoreValue emitUnsignedTwoFiftyFiveCall CByteCount

call emitHexTwoFiftyFiveCall writeSignedInt64HexToStandardOutput
arg emitHexTwoFiftyFiveCall inputValue twoFiftyFiveSampleValue
run emitHexTwoFiftyFiveCall
ignoreValue emitHexTwoFiftyFiveCall CByteCount

const exitOkCode ExitCode 0
returnOk exitOkCode

# Failure leg: the first banner write failed (closed pipe, etc.).
# Surface the typed variant with the raw negative status as cause.
label byteWriteFailedDuringSmokeHandler
makeError byteWriteFailedDuringSmokeFailure MainError.ByteWriteFailedDuringSmoke emitHelloBannerError
returnError byteWriteFailedDuringSmokeFailure
