project Bootstrap6
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError ConsoleWriteFailed CSignedInt32
errorCase MainError InputOpenFailed CSignedInt32
errorCase MainError AllocationFailed CSignedInt32
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

purpose main "Self-host stage 6: the first AS-written compiler whose output IR size scales with the input. Reads an AgentScript source file, finds every `CNullTerminatedByteString \"...\"` literal in the body, and emits LLVM IR containing one @.s<i> private constant and one @print<i> helper function per literal. The emitted main() then calls each helper in source order before returning the parsed ExitCode integer. This is the stage at which `removing one greeting from the input` produces a measurably different output IR."
invariant main "Greeting count is determined by parsing, not hard-coded; main emits exactly stringCount calls to @print<i>"
invariant main "The closing-quote NUL substitution advances the search cursor so subsequent strstr calls do not get short-circuited"

label startMain

const inputPath CNullTerminatedByteString "C:/Users/Cam/Desktop/AgentScript/AgentScript/bootstrap/input6.as"
const readMode CNullTerminatedByteString "r"
const bufferCapacity CByteCount 16384
const readChunkCapacity CByteCount 16383
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

# ---- 4. null-terminate the buffer at end-of-data ----
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

# ---- 5. parse ExitCode FIRST (before greeting null-terminate writes) ----
var exitSearchCursor I64 0
var exitFirstDigitOffset I64 0

label exitSearchLoopHead

call exitSearchPointerCall pointer.offset
arg exitSearchPointerCall base readBuffer
arg exitSearchPointerCall offset exitSearchCursor
run exitSearchPointerCall
bind exitSearchStart COpaqueMemoryAddress exitSearchPointerCall

call exitStrstrCall c.strstr
arg exitStrstrCall haystack exitSearchStart
arg exitStrstrCall needle exitCodeMarker
run exitStrstrCall
bind exitHitPointer COpaqueMemoryAddress exitStrstrCall

call exitHitNullCheckCall pointer.isNull
arg exitHitNullCheckCall pointer exitHitPointer
run exitHitNullCheckCall
bind exitHitMissing Bool exitHitNullCheckCall
branchIf exitHitMissing exitCodeMarkerNotFound

call exitDigitPointerCall pointer.offset
arg exitDigitPointerCall base exitHitPointer
arg exitDigitPointerCall offset exitCodeMarkerLength
run exitDigitPointerCall
bind exitDigitPointer COpaqueMemoryAddress exitDigitPointerCall

call exitDigitOffsetCall pointer.difference
arg exitDigitOffsetCall left exitDigitPointer
arg exitDigitOffsetCall right readBuffer
run exitDigitOffsetCall
bind exitDigitOffset CSignedInt64 exitDigitOffsetCall

call exitByteLoadCall pointer.loadByte
arg exitByteLoadCall buffer readBuffer
arg exitByteLoadCall offset exitDigitOffset
run exitByteLoadCall
bind exitByte I8 exitByteLoadCall

call exitByteBelowZeroCall math.lessThanI64
arg exitByteBelowZeroCall left exitByte
arg exitByteBelowZeroCall right asciiDigitZero
run exitByteBelowZeroCall
bind exitByteBelowZero Bool exitByteBelowZeroCall
branchIf exitByteBelowZero exitByteNotADigit

call exitByteAboveNineCall math.greaterThanI64
arg exitByteAboveNineCall left exitByte
arg exitByteAboveNineCall right asciiDigitNine
run exitByteAboveNineCall
bind exitByteAboveNine Bool exitByteAboveNineCall
branchIf exitByteAboveNine exitByteNotADigit

set exitFirstDigitOffset exitDigitOffset
branch exitDigitFound

label exitByteNotADigit
set exitSearchCursor exitDigitOffset
branch exitSearchLoopHead

label exitDigitFound

var exitDigitCursor I64 0
set exitDigitCursor exitFirstDigitOffset
var exitAccumulator I64 0

label exitDigitLoopHead

call exitParseLoadCall pointer.loadByte
arg exitParseLoadCall buffer readBuffer
arg exitParseLoadCall offset exitDigitCursor
run exitParseLoadCall
bind exitParseByte I8 exitParseLoadCall

call exitParseBelowZeroCall math.lessThanI64
arg exitParseBelowZeroCall left exitParseByte
arg exitParseBelowZeroCall right asciiDigitZero
run exitParseBelowZeroCall
bind exitParseBelowZero Bool exitParseBelowZeroCall
branchIf exitParseBelowZero exitDigitLoopExit

call exitParseAboveNineCall math.greaterThanI64
arg exitParseAboveNineCall left exitParseByte
arg exitParseAboveNineCall right asciiDigitNine
run exitParseAboveNineCall
bind exitParseAboveNine Bool exitParseAboveNineCall
branchIf exitParseAboveNine exitDigitLoopExit

call exitParseDigitValueCall math.subtractI64
arg exitParseDigitValueCall left exitParseByte
arg exitParseDigitValueCall right asciiDigitZero
run exitParseDigitValueCall
bind exitParseDigitValue I64 exitParseDigitValueCall

call exitParseAccumScaledCall math.multiplyI64
arg exitParseAccumScaledCall left exitAccumulator
arg exitParseAccumScaledCall right tenValue
run exitParseAccumScaledCall
bind exitParseAccumScaled I64 exitParseAccumScaledCall

call exitParseAccumNextCall math.addI64
arg exitParseAccumNextCall left exitParseAccumScaled
arg exitParseAccumNextCall right exitParseDigitValue
run exitParseAccumNextCall
bind exitParseAccumNext I64 exitParseAccumNextCall
set exitAccumulator exitParseAccumNext

call exitParseNextCursorCall math.addI64
arg exitParseNextCursorCall left exitDigitCursor
arg exitParseNextCursorCall right oneOffset
run exitParseNextCursorCall
bind exitParseNextCursor I64 exitParseNextCursorCall
set exitDigitCursor exitParseNextCursor

branch exitDigitLoopHead

label exitDigitLoopExit

# ---- 6. emit the IR header ----
const irModuleBanner CNullTerminatedByteString "; ModuleID = 'AgentScriptStage6SelfHosted'"
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

const irExternPuts CNullTerminatedByteString "declare i32 @puts(i8*)"
call writeIrExternPutsCall c.puts
arg writeIrExternPutsCall text irExternPuts
run writeIrExternPutsCall
ignoreOk writeIrExternPutsCall Void
bindError writeIrExternPutsError CSignedInt32 writeIrExternPutsCall
branchIfError writeIrExternPutsCall consoleWriteFailed

# ---- 7. main greeting loop: find every CNullTerminatedByteString
#         literal and emit @.s<i> + @print<i> for it ----

var greetingSearchCursor I64 0
var stringCount I64 0

label greetingLoopHead

call greetingSearchPointerCall pointer.offset
arg greetingSearchPointerCall base readBuffer
arg greetingSearchPointerCall offset greetingSearchCursor
run greetingSearchPointerCall
bind greetingSearchStart COpaqueMemoryAddress greetingSearchPointerCall

call greetingStrstrCall c.strstr
arg greetingStrstrCall haystack greetingSearchStart
arg greetingStrstrCall needle greetingMarker
run greetingStrstrCall
bind greetingMarkerPointer COpaqueMemoryAddress greetingStrstrCall

call greetingMarkerNullCheckCall pointer.isNull
arg greetingMarkerNullCheckCall pointer greetingMarkerPointer
run greetingMarkerNullCheckCall
bind greetingMarkerMissing Bool greetingMarkerNullCheckCall
branchIf greetingMarkerMissing greetingLoopExit

call greetingStartPointerCall pointer.offset
arg greetingStartPointerCall base greetingMarkerPointer
arg greetingStartPointerCall offset greetingMarkerLength
run greetingStartPointerCall
bind greetingStartPointer COpaqueMemoryAddress greetingStartPointerCall

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

call greetingByteCountCall pointer.difference
arg greetingByteCountCall left greetingEndPointer
arg greetingByteCountCall right greetingStartPointer
run greetingByteCountCall
bind greetingByteCount CSignedInt64 greetingByteCountCall

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

# Emit `@.s<i> = private constant [<L> x i8] c"<bytes>\00"`
const constantHeaderFormat CNullTerminatedByteString "@.s%lld = private constant [%lld x i8] c\""
call emitConstantHeaderCall c.printf
arg emitConstantHeaderCall format constantHeaderFormat
arg emitConstantHeaderCall index stringCount
arg emitConstantHeaderCall length greetingArrayLength
run emitConstantHeaderCall
ignoreOk emitConstantHeaderCall Void
bindError emitConstantHeaderError CSignedInt32 emitConstantHeaderCall
branchIfError emitConstantHeaderCall consoleWriteFailed

const greetingPrintFormat CNullTerminatedByteString "%s"
call emitGreetingBytesCall c.printf
arg emitGreetingBytesCall format greetingPrintFormat
arg emitGreetingBytesCall text greetingStartPointer
run emitGreetingBytesCall
ignoreOk emitGreetingBytesCall Void
bindError emitGreetingBytesError CSignedInt32 emitGreetingBytesCall
branchIfError emitGreetingBytesCall consoleWriteFailed

const constantTailLiteral CNullTerminatedByteString "\\00\""
call emitConstantTailCall c.puts
arg emitConstantTailCall text constantTailLiteral
run emitConstantTailCall
ignoreOk emitConstantTailCall Void
bindError emitConstantTailError CSignedInt32 emitConstantTailCall
branchIfError emitConstantTailCall consoleWriteFailed

# Emit `define void @print<i>() {`
const printHeaderFormat CNullTerminatedByteString "define void @print%lld() {\n"
call emitPrintHeaderCall c.printf
arg emitPrintHeaderCall format printHeaderFormat
arg emitPrintHeaderCall index stringCount
run emitPrintHeaderCall
ignoreOk emitPrintHeaderCall Void
bindError emitPrintHeaderError CSignedInt32 emitPrintHeaderCall
branchIfError emitPrintHeaderCall consoleWriteFailed

# Emit `  %r = call i32 @puts(i8* getelementptr inbounds ([L x i8], [L x i8]* @.s<i>, i32 0, i32 0))`
const printCallFormat CNullTerminatedByteString "  %%r = call i32 @puts(i8* getelementptr inbounds ([%lld x i8], [%lld x i8]* @.s%lld, i32 0, i32 0))\n"
call emitPrintCallCall c.printf
arg emitPrintCallCall format printCallFormat
arg emitPrintCallCall length1 greetingArrayLength
arg emitPrintCallCall length2 greetingArrayLength
arg emitPrintCallCall index stringCount
run emitPrintCallCall
ignoreOk emitPrintCallCall Void
bindError emitPrintCallError CSignedInt32 emitPrintCallCall
branchIfError emitPrintCallCall consoleWriteFailed

const printRetVoid CNullTerminatedByteString "  ret void"
call emitPrintRetCall c.puts
arg emitPrintRetCall text printRetVoid
run emitPrintRetCall
ignoreOk emitPrintRetCall Void
bindError emitPrintRetError CSignedInt32 emitPrintRetCall
branchIfError emitPrintRetCall consoleWriteFailed

const printCloseBrace CNullTerminatedByteString "}"
call emitPrintCloseCall c.puts
arg emitPrintCloseCall text printCloseBrace
run emitPrintCloseCall
ignoreOk emitPrintCloseCall Void
bindError emitPrintCloseError CSignedInt32 emitPrintCloseCall
branchIfError emitPrintCloseCall consoleWriteFailed

# Advance search cursor PAST the null we just stored at the closing
# quote, otherwise the next strstr would immediately hit that NUL and
# treat the buffer as ending here.
call greetingEndOffsetCall pointer.difference
arg greetingEndOffsetCall left greetingEndPointer
arg greetingEndOffsetCall right readBuffer
run greetingEndOffsetCall
bind greetingEndOffset CSignedInt64 greetingEndOffsetCall

call nextGreetingSearchCall math.addI64
arg nextGreetingSearchCall left greetingEndOffset
arg nextGreetingSearchCall right oneOffset
run nextGreetingSearchCall
bind nextGreetingSearch I64 nextGreetingSearchCall
set greetingSearchCursor nextGreetingSearch

# Increment string counter.
call nextStringCountCall math.addI64
arg nextStringCountCall left stringCount
arg nextStringCountCall right oneOffset
run nextStringCountCall
bind nextStringCount I64 nextStringCountCall
set stringCount nextStringCount

branch greetingLoopHead

label greetingLoopExit

# ---- 8. emit main: call every @print<i> in order, return ExitCode ----

const mainHeader CNullTerminatedByteString "define i32 @main() {"
call emitMainHeaderCall c.puts
arg emitMainHeaderCall text mainHeader
run emitMainHeaderCall
ignoreOk emitMainHeaderCall Void
bindError emitMainHeaderError CSignedInt32 emitMainHeaderCall
branchIfError emitMainHeaderCall consoleWriteFailed

var callEmitCursor I64 0

label callEmitLoopHead

call callEmitDoneCall math.greaterThanOrEqualI64
arg callEmitDoneCall left callEmitCursor
arg callEmitDoneCall right stringCount
run callEmitDoneCall
bind callEmitDone Bool callEmitDoneCall
branchIf callEmitDone callEmitLoopExit

const mainCallFormat CNullTerminatedByteString "  call void @print%lld()\n"
call emitMainCallCall c.printf
arg emitMainCallCall format mainCallFormat
arg emitMainCallCall index callEmitCursor
run emitMainCallCall
ignoreOk emitMainCallCall Void
bindError emitMainCallError CSignedInt32 emitMainCallCall
branchIfError emitMainCallCall consoleWriteFailed

call nextCallEmitCursorCall math.addI64
arg nextCallEmitCursorCall left callEmitCursor
arg nextCallEmitCursorCall right oneOffset
run nextCallEmitCursorCall
bind nextCallEmitCursor I64 nextCallEmitCursorCall
set callEmitCursor nextCallEmitCursor

branch callEmitLoopHead

label callEmitLoopExit

const mainRetFormat CNullTerminatedByteString "  ret i32 %lld\n"
call emitMainRetCall c.printf
arg emitMainRetCall format mainRetFormat
arg emitMainRetCall value exitAccumulator
run emitMainRetCall
ignoreOk emitMainRetCall Void
bindError emitMainRetError CSignedInt32 emitMainRetCall
branchIfError emitMainRetCall consoleWriteFailed

const mainCloseBrace CNullTerminatedByteString "}"
call emitMainCloseCall c.puts
arg emitMainCloseCall text mainCloseBrace
run emitMainCloseCall
ignoreOk emitMainCloseCall Void
bindError emitMainCloseError CSignedInt32 emitMainCloseCall
branchIfError emitMainCloseCall consoleWriteFailed

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

label greetingCloseQuoteNotFound
const greetingCloseQuoteNotFoundExitCode CSignedInt32 4
makeError greetingCloseQuoteNotFoundFailure MainError.GreetingCloseQuoteNotFound greetingCloseQuoteNotFoundExitCode
returnError greetingCloseQuoteNotFoundFailure

label consoleWriteFailed
const consoleWriteFailedSentinel CSignedInt32 5
makeError consoleWriteFailedFailure MainError.ConsoleWriteFailed consoleWriteFailedSentinel
returnError consoleWriteFailedFailure
