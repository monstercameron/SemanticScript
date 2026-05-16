project Bootstrap4
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError ConsoleWriteFailed CSignedInt32
errorCase MainError InputOpenFailed CSignedInt32
errorCase MainError AllocationFailed CSignedInt32
errorCase MainError GreetingMarkerNotFound CSignedInt32
errorCase MainError GreetingCloseQuoteNotFound CSignedInt32
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

purpose main "Self-host stage 4: read an AgentScript source file, extract its greeting string (first `... CNullTerminatedByteString \"...\"` declaration) and its first `ExitCode <N>` integer, and emit a complete LLVM module that puts the greeting to stdout and returns N from main."
invariant main "The emitted module declares puts, allocates a single private string for the greeting, and returns the parsed integer exit code"
invariant main "The greeting bytes are taken verbatim from the input file (no escape processing) between the marker and the next double-quote byte"

label startMain

const inputPath CNullTerminatedByteString "C:/Users/Cam/Desktop/AgentScript/AgentScript/bootstrap/input4.as"
const readMode CNullTerminatedByteString "r"
const bufferCapacity CByteCount 8192
const readChunkCapacity CByteCount 8191
const oneByte CByteCount 1
const zeroByteOffset CByteCount 0
const zeroByteValue CSignedInt32 0

const greetingMarker CNullTerminatedByteString "CNullTerminatedByteString \""
const greetingMarkerLength CByteCount 27
const quoteCharCode CSignedInt32 34

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

# ---- 5. find first "ExitCode " followed by a digit ----
#
# This MUST run before the greeting parser null-terminates the buffer
# mid-stream: if we replaced the closing-quote byte with NUL first,
# c.strstr would stop scanning at that NUL and miss any ExitCode that
# appears later in the file.

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
branch exitCodeFound

label markerNotADigit
set searchCursor markerDigitOffset
branch markerSearchLoopHead

label exitCodeFound

# ---- 9. parse the integer one digit at a time ----
var digitCursor I64 0
set digitCursor firstDigitOffset
var exitCodeAccumulator I64 0

label exitDigitLoopHead

call exitDigitLoadCall pointer.loadByte
arg exitDigitLoadCall buffer readBuffer
arg exitDigitLoadCall offset digitCursor
run exitDigitLoadCall
bind exitDigitByte I8 exitDigitLoadCall

call exitDigitBelowZeroCall math.lessThanI64
arg exitDigitBelowZeroCall left exitDigitByte
arg exitDigitBelowZeroCall right asciiDigitZero
run exitDigitBelowZeroCall
bind exitDigitBelowZero Bool exitDigitBelowZeroCall
branchIf exitDigitBelowZero exitDigitLoopExit

call exitDigitAboveNineCall math.greaterThanI64
arg exitDigitAboveNineCall left exitDigitByte
arg exitDigitAboveNineCall right asciiDigitNine
run exitDigitAboveNineCall
bind exitDigitAboveNine Bool exitDigitAboveNineCall
branchIf exitDigitAboveNine exitDigitLoopExit

call exitDigitValueCall math.subtractI64
arg exitDigitValueCall left exitDigitByte
arg exitDigitValueCall right asciiDigitZero
run exitDigitValueCall
bind exitDigitValue I64 exitDigitValueCall

call exitAccumulatorScaledCall math.multiplyI64
arg exitAccumulatorScaledCall left exitCodeAccumulator
arg exitAccumulatorScaledCall right tenValue
run exitAccumulatorScaledCall
bind exitAccumulatorScaled I64 exitAccumulatorScaledCall

call exitAccumulatorNextCall math.addI64
arg exitAccumulatorNextCall left exitAccumulatorScaled
arg exitAccumulatorNextCall right exitDigitValue
run exitAccumulatorNextCall
bind exitAccumulatorNext I64 exitAccumulatorNextCall
set exitCodeAccumulator exitAccumulatorNext

call nextExitDigitCursorCall math.addI64
arg nextExitDigitCursorCall left digitCursor
arg nextExitDigitCursorCall right oneOffset
run nextExitDigitCursorCall
bind nextExitDigitCursor I64 nextExitDigitCursorCall
set digitCursor nextExitDigitCursor

branch exitDigitLoopHead

label exitDigitLoopExit

# ---- 10. find the greeting marker (`CNullTerminatedByteString "`) ----
call greetingMarkerSearchCall c.strstr
arg greetingMarkerSearchCall haystack readBuffer
arg greetingMarkerSearchCall needle greetingMarker
run greetingMarkerSearchCall
bind greetingMarkerPointer COpaqueMemoryAddress greetingMarkerSearchCall

call greetingMarkerNullCheckCall pointer.isNull
arg greetingMarkerNullCheckCall pointer greetingMarkerPointer
run greetingMarkerNullCheckCall
bind greetingMarkerMissing Bool greetingMarkerNullCheckCall
branchIf greetingMarkerMissing greetingMarkerNotFound
branch greetingMarkerFound

label greetingMarkerFound

# Advance past the marker to the first byte of the greeting.
call greetingStartPointerCall pointer.offset
arg greetingStartPointerCall base greetingMarkerPointer
arg greetingStartPointerCall offset greetingMarkerLength
run greetingStartPointerCall
bind greetingStartPointer COpaqueMemoryAddress greetingStartPointerCall

# Find the closing double-quote.
call greetingEndSearchCall c.strchr
arg greetingEndSearchCall haystack greetingStartPointer
arg greetingEndSearchCall needle quoteCharCode
run greetingEndSearchCall
bind greetingEndPointer COpaqueMemoryAddress greetingEndSearchCall

call greetingEndNullCheckCall pointer.isNull
arg greetingEndNullCheckCall pointer greetingEndPointer
run greetingEndNullCheckCall
bind greetingEndMissing Bool greetingEndNullCheckCall
branchIf greetingEndMissing greetingCloseQuoteNotFound
branch greetingEndFound

label greetingEndFound

call greetingByteCountCall pointer.difference
arg greetingByteCountCall left greetingEndPointer
arg greetingByteCountCall right greetingStartPointer
run greetingByteCountCall
bind greetingByteCount CSignedInt64 greetingByteCountCall

# Replace closing quote with NUL so `%s` prints exactly the greeting.
call greetingNullTerminateCall pointer.storeByte
arg greetingNullTerminateCall buffer greetingEndPointer
arg greetingNullTerminateCall offset zeroByteOffset
arg greetingNullTerminateCall value zeroByteValue
run greetingNullTerminateCall

call greetingArrayLengthCall math.addI64
arg greetingArrayLengthCall left greetingByteCount
arg greetingArrayLengthCall right oneOffset
run greetingArrayLengthCall
bind greetingArrayLength CSignedInt64 greetingArrayLengthCall

# ---- 11. emit the LLVM IR module ----

const irModuleBanner CNullTerminatedByteString "; ModuleID = 'AgentScriptStage4SelfHosted'"
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

# @.greetingText = private constant [N x i8] c"<bytes>\00"
const greetingConstantOpenFormat CNullTerminatedByteString "@.greetingText = private constant [%lld x i8] c\""
call writeGreetingConstantOpenCall c.printf
arg writeGreetingConstantOpenCall format greetingConstantOpenFormat
arg writeGreetingConstantOpenCall length greetingArrayLength
run writeGreetingConstantOpenCall
ignoreOk writeGreetingConstantOpenCall Void
bindError writeGreetingConstantOpenError CSignedInt32 writeGreetingConstantOpenCall
branchIfError writeGreetingConstantOpenCall consoleWriteFailed

const greetingPrintFormat CNullTerminatedByteString "%s"
call writeGreetingBytesCall c.printf
arg writeGreetingBytesCall format greetingPrintFormat
arg writeGreetingBytesCall text greetingStartPointer
run writeGreetingBytesCall
ignoreOk writeGreetingBytesCall Void
bindError writeGreetingBytesError CSignedInt32 writeGreetingBytesCall
branchIfError writeGreetingBytesCall consoleWriteFailed

const irGreetingConstantClose CNullTerminatedByteString "\\00\""
call writeGreetingConstantCloseCall c.puts
arg writeGreetingConstantCloseCall text irGreetingConstantClose
run writeGreetingConstantCloseCall
ignoreOk writeGreetingConstantCloseCall Void
bindError writeGreetingConstantCloseError CSignedInt32 writeGreetingConstantCloseCall
branchIfError writeGreetingConstantCloseCall consoleWriteFailed

const irExternPuts CNullTerminatedByteString "declare i32 @puts(i8*)"
call writeIrExternPutsCall c.puts
arg writeIrExternPutsCall text irExternPuts
run writeIrExternPutsCall
ignoreOk writeIrExternPutsCall Void
bindError writeIrExternPutsError CSignedInt32 writeIrExternPutsCall
branchIfError writeIrExternPutsCall consoleWriteFailed

const irMainHeader CNullTerminatedByteString "define i32 @main() {"
call writeIrMainHeaderCall c.puts
arg writeIrMainHeaderCall text irMainHeader
run writeIrMainHeaderCall
ignoreOk writeIrMainHeaderCall Void
bindError writeIrMainHeaderError CSignedInt32 writeIrMainHeaderCall
branchIfError writeIrMainHeaderCall consoleWriteFailed

const irPutsCallFormat CNullTerminatedByteString "  %%r = call i32 @puts(i8* getelementptr inbounds ([%lld x i8], [%lld x i8]* @.greetingText, i32 0, i32 0))"
call writeIrPutsCallCall c.printf
arg writeIrPutsCallCall format irPutsCallFormat
arg writeIrPutsCallCall length1 greetingArrayLength
arg writeIrPutsCallCall length2 greetingArrayLength
run writeIrPutsCallCall
ignoreOk writeIrPutsCallCall Void
bindError writeIrPutsCallError CSignedInt32 writeIrPutsCallCall
branchIfError writeIrPutsCallCall consoleWriteFailed

const irNewline CNullTerminatedByteString ""
call writeIrPutsCallNewlineCall c.puts
arg writeIrPutsCallNewlineCall text irNewline
run writeIrPutsCallNewlineCall
ignoreOk writeIrPutsCallNewlineCall Void
bindError writeIrPutsCallNewlineError CSignedInt32 writeIrPutsCallNewlineCall
branchIfError writeIrPutsCallNewlineCall consoleWriteFailed

const irReturnFormat CNullTerminatedByteString "  ret i32 %lld"
call writeIrReturnCall c.printf
arg writeIrReturnCall format irReturnFormat
arg writeIrReturnCall value exitCodeAccumulator
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

# ---- 11. close input file ----
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

label greetingMarkerNotFound
const greetingMarkerNotFoundExitCode CSignedInt32 3
makeError greetingMarkerNotFoundFailure MainError.GreetingMarkerNotFound greetingMarkerNotFoundExitCode
returnError greetingMarkerNotFoundFailure

label greetingCloseQuoteNotFound
const greetingCloseQuoteNotFoundExitCode CSignedInt32 4
makeError greetingCloseQuoteNotFoundFailure MainError.GreetingCloseQuoteNotFound greetingCloseQuoteNotFoundExitCode
returnError greetingCloseQuoteNotFoundFailure

label exitCodeMarkerNotFound
const exitCodeMarkerNotFoundExitCode CSignedInt32 5
makeError exitCodeMarkerNotFoundFailure MainError.ExitCodeMarkerNotFound exitCodeMarkerNotFoundExitCode
returnError exitCodeMarkerNotFoundFailure

label consoleWriteFailed
const consoleWriteFailedSentinel CSignedInt32 6
makeError consoleWriteFailedFailure MainError.ConsoleWriteFailed consoleWriteFailedSentinel
returnError consoleWriteFailedFailure
