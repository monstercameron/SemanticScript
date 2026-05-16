project Bootstrap3
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError ConsoleWriteFailed CSignedInt32
errorCase MainError InputOpenFailed CSignedInt32
errorCase MainError AllocationFailed CSignedInt32
errorCase MainError ExitCodeMarkerNotFound CSignedInt32

operation main
input main console Console
output main Result ExitCode MainError
effect main read filesystem
effect main write console.stdout
effect main allocate heap
effect main read memory.buffer
effect main write memory.buffer
memory main heap yes
memory main stack max 8KiB
async main no

purpose main "Self-host stage 3: read an AgentScript source file, find the first `ExitCode <N>` token, parse the integer literal that follows, and emit a complete LLVM module that returns N from main. Supports the constant-return AgentScript subset (input3.as)."
invariant main "The emitted IR is self-contained: defines main and returns the parsed integer literal"
invariant main "The integer literal is the contiguous decimal-digit byte sequence immediately after the `ExitCode ` marker in the input file"

label startMain

const inputPath CNullTerminatedByteString "C:/Users/Cam/Desktop/AgentScript/AgentScript/bootstrap/input3.as"
const readMode CNullTerminatedByteString "r"
const bufferCapacity CByteCount 8192
const readChunkCapacity CByteCount 8191
const oneByte CByteCount 1
const zeroByteOffset CByteCount 0
const zeroByteValue CSignedInt32 0

const exitCodeMarker CNullTerminatedByteString "ExitCode "
const exitCodeMarkerLength CByteCount 9
const oneOffset I64 1
const tenValue I64 10
const asciiDigitZero I64 48
const asciiDigitNine I64 57

# ---- 1. open the input file ----
call inputOpenCall c.fopen
arg inputOpenCall path inputPath
arg inputOpenCall mode readMode
run inputOpenCall
bind inputFileHandle CFileHandle inputOpenCall

call inputOpenNullCheckCall pointer.isNull
arg inputOpenNullCheckCall pointer inputFileHandle
run inputOpenNullCheckCall
bind inputFileIsNull Bool inputOpenNullCheckCall
branchIf inputFileIsNull inputOpenFailed
branch inputOpened

label inputOpened

# ---- 2. allocate a read buffer ----
call readBufferAllocCall c.malloc
arg readBufferAllocCall size bufferCapacity
run readBufferAllocCall
bind readBuffer COpaqueMemoryAddress readBufferAllocCall

call readBufferNullCheckCall pointer.isNull
arg readBufferNullCheckCall pointer readBuffer
run readBufferNullCheckCall
bind readBufferIsNull Bool readBufferNullCheckCall
branchIf readBufferIsNull readBufferAllocationFailed
branch readBufferAllocated

label readBufferAllocated

# ---- 3. read up to (capacity - 1) bytes ----
call inputReadCall c.fread
arg inputReadCall buffer readBuffer
arg inputReadCall size oneByte
arg inputReadCall count readChunkCapacity
arg inputReadCall stream inputFileHandle
run inputReadCall
bind inputBytesRead CByteCount inputReadCall

# ---- 4. null-terminate the buffer at position bytesRead ----
call inputNullTerminatePointerCall pointer.offset
arg inputNullTerminatePointerCall base readBuffer
arg inputNullTerminatePointerCall offset inputBytesRead
run inputNullTerminatePointerCall
bind inputNullTerminatePointer COpaqueMemoryAddress inputNullTerminatePointerCall

call inputNullTerminateStoreCall pointer.storeByte
arg inputNullTerminateStoreCall buffer inputNullTerminatePointer
arg inputNullTerminateStoreCall offset zeroByteOffset
arg inputNullTerminateStoreCall value zeroByteValue
run inputNullTerminateStoreCall

# ---- 5. locate first "ExitCode " whose next byte is a decimal digit ----
# The file's header and comments often contain non-declaration uses of
# "ExitCode " (e.g. `output main Result ExitCode MainError`). The
# declaration form we want has the literal value as the very next byte:
# `const X ExitCode 42`. So we walk forward through strstr matches and
# stop on the first one whose follow-byte is in '0'..'9'.
var searchCursor I64 0
var firstDigitOffset I64 0

label markerSearchLoopHead

call markerSearchPointerCall pointer.offset
arg markerSearchPointerCall base readBuffer
arg markerSearchPointerCall offset searchCursor
run markerSearchPointerCall
bind markerSearchStart COpaqueMemoryAddress markerSearchPointerCall

call markerStrstrCall c.strstr
arg markerStrstrCall haystack markerSearchStart
arg markerStrstrCall needle exitCodeMarker
run markerStrstrCall
bind markerHitPointer COpaqueMemoryAddress markerStrstrCall

call markerHitNullCheckCall pointer.isNull
arg markerHitNullCheckCall pointer markerHitPointer
run markerHitNullCheckCall
bind markerHitMissing Bool markerHitNullCheckCall
branchIf markerHitMissing exitCodeMarkerNotFound

call markerDigitPointerCall pointer.offset
arg markerDigitPointerCall base markerHitPointer
arg markerDigitPointerCall offset exitCodeMarkerLength
run markerDigitPointerCall
bind markerDigitPointer COpaqueMemoryAddress markerDigitPointerCall

call markerDigitOffsetCall pointer.difference
arg markerDigitOffsetCall left markerDigitPointer
arg markerDigitOffsetCall right readBuffer
run markerDigitOffsetCall
bind markerDigitOffset CSignedInt64 markerDigitOffsetCall

call markerByteLoadCall pointer.loadByte
arg markerByteLoadCall buffer readBuffer
arg markerByteLoadCall offset markerDigitOffset
run markerByteLoadCall
bind markerByte I8 markerByteLoadCall

call markerByteBelowZeroCall math.lessThanI64
arg markerByteBelowZeroCall left markerByte
arg markerByteBelowZeroCall right asciiDigitZero
run markerByteBelowZeroCall
bind markerByteBelowZero Bool markerByteBelowZeroCall
branchIf markerByteBelowZero markerNotADigit

call markerByteAboveNineCall math.greaterThanI64
arg markerByteAboveNineCall left markerByte
arg markerByteAboveNineCall right asciiDigitNine
run markerByteAboveNineCall
bind markerByteAboveNine Bool markerByteAboveNineCall
branchIf markerByteAboveNine markerNotADigit

set firstDigitOffset markerDigitOffset
branch exitCodeMarkerFound

label markerNotADigit

set searchCursor markerDigitOffset
branch markerSearchLoopHead

label exitCodeMarkerFound

# ---- 7. parse the integer one digit at a time ----
var digitCursor I64 0
set digitCursor firstDigitOffset
var accumulator I64 0

label digitLoopHead

call digitLoadCall pointer.loadByte
arg digitLoadCall buffer readBuffer
arg digitLoadCall offset digitCursor
run digitLoadCall
bind digitByte I8 digitLoadCall

call digitBelowZeroCall math.lessThanI64
arg digitBelowZeroCall left digitByte
arg digitBelowZeroCall right asciiDigitZero
run digitBelowZeroCall
bind digitBelowZero Bool digitBelowZeroCall
branchIf digitBelowZero digitLoopExit

call digitAboveNineCall math.greaterThanI64
arg digitAboveNineCall left digitByte
arg digitAboveNineCall right asciiDigitNine
run digitAboveNineCall
bind digitAboveNine Bool digitAboveNineCall
branchIf digitAboveNine digitLoopExit

call digitValueCall math.subtractI64
arg digitValueCall left digitByte
arg digitValueCall right asciiDigitZero
run digitValueCall
bind digitValue I64 digitValueCall

call accumulatorScaledCall math.multiplyI64
arg accumulatorScaledCall left accumulator
arg accumulatorScaledCall right tenValue
run accumulatorScaledCall
bind accumulatorScaled I64 accumulatorScaledCall

call accumulatorNextCall math.addI64
arg accumulatorNextCall left accumulatorScaled
arg accumulatorNextCall right digitValue
run accumulatorNextCall
bind accumulatorNext I64 accumulatorNextCall
set accumulator accumulatorNext

call nextDigitCursorCall math.addI64
arg nextDigitCursorCall left digitCursor
arg nextDigitCursorCall right oneOffset
run nextDigitCursorCall
bind nextDigitCursor I64 nextDigitCursorCall
set digitCursor nextDigitCursor

branch digitLoopHead

label digitLoopExit

# ---- 8. emit the LLVM IR module ----
const irModuleBanner CNullTerminatedByteString "; ModuleID = 'AgentScriptStage3SelfHosted'"
call writeIrModuleBannerCall c.puts
arg writeIrModuleBannerCall text irModuleBanner
run writeIrModuleBannerCall
ignoreOk writeIrModuleBannerCall Void
bindError writeIrModuleBannerError CSignedInt32 writeIrModuleBannerCall
branchIfError writeIrModuleBannerCall consoleWriteFailed

const irTargetTriple CNullTerminatedByteString "target triple = \"x86_64-pc-windows-msvc\""
call writeIrTargetTripleCall c.puts
arg writeIrTargetTripleCall text irTargetTriple
run writeIrTargetTripleCall
ignoreOk writeIrTargetTripleCall Void
bindError writeIrTargetTripleError CSignedInt32 writeIrTargetTripleCall
branchIfError writeIrTargetTripleCall consoleWriteFailed

const irMainHeader CNullTerminatedByteString "define i32 @main() {"
call writeIrMainHeaderCall c.puts
arg writeIrMainHeaderCall text irMainHeader
run writeIrMainHeaderCall
ignoreOk writeIrMainHeaderCall Void
bindError writeIrMainHeaderError CSignedInt32 writeIrMainHeaderCall
branchIfError writeIrMainHeaderCall consoleWriteFailed

const irReturnFormat CNullTerminatedByteString "  ret i32 %lld"
call writeIrReturnCall c.printf
arg writeIrReturnCall format irReturnFormat
arg writeIrReturnCall value accumulator
run writeIrReturnCall
ignoreOk writeIrReturnCall Void
bindError writeIrReturnError CSignedInt32 writeIrReturnCall
branchIfError writeIrReturnCall consoleWriteFailed

const irReturnNewline CNullTerminatedByteString ""
call writeIrReturnNewlineCall c.puts
arg writeIrReturnNewlineCall text irReturnNewline
run writeIrReturnNewlineCall
ignoreOk writeIrReturnNewlineCall Void
bindError writeIrReturnNewlineError CSignedInt32 writeIrReturnNewlineCall
branchIfError writeIrReturnNewlineCall consoleWriteFailed

const irMainFooter CNullTerminatedByteString "}"
call writeIrMainFooterCall c.puts
arg writeIrMainFooterCall text irMainFooter
run writeIrMainFooterCall
ignoreOk writeIrMainFooterCall Void
bindError writeIrMainFooterError CSignedInt32 writeIrMainFooterCall
branchIfError writeIrMainFooterCall consoleWriteFailed

# ---- 9. close input file (best effort) ----
call inputCloseCall c.fclose
arg inputCloseCall stream inputFileHandle
run inputCloseCall
bind inputCloseResult CSignedInt32 inputCloseCall

const successfulExitCode ExitCode 0
returnOk successfulExitCode

label inputOpenFailed
const inputOpenFailedExitCode CSignedInt32 1
makeError inputOpenFailedFailure MainError.InputOpenFailed inputOpenFailedExitCode
returnError inputOpenFailedFailure

label readBufferAllocationFailed
const readBufferAllocationFailedExitCode CSignedInt32 2
makeError readBufferAllocationFailedFailure MainError.AllocationFailed readBufferAllocationFailedExitCode
returnError readBufferAllocationFailedFailure

label exitCodeMarkerNotFound
const exitCodeMarkerNotFoundExitCode CSignedInt32 3
makeError exitCodeMarkerNotFoundFailure MainError.ExitCodeMarkerNotFound exitCodeMarkerNotFoundExitCode
returnError exitCodeMarkerNotFoundFailure

label consoleWriteFailed
const consoleWriteFailedSentinel CSignedInt32 4
makeError consoleWriteFailedFailure MainError.ConsoleWriteFailed consoleWriteFailedSentinel
returnError consoleWriteFailedFailure
