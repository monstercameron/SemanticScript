project Bootstrap2
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError ConsoleWriteFailed CSignedInt32
errorCase MainError InputOpenFailed CSignedInt32
errorCase MainError AllocationFailed CSignedInt32
errorCase MainError NoQuotedStringFound CSignedInt32

operation main
input main console Console
output main Result ExitCode MainError
effect main read filesystem
effect main write filesystem
effect main write console.stdout
effect main allocate heap
effect main read memory.buffer
effect main write memory.buffer
memory main heap yes
memory main stack max 8KiB
async main no

purpose main "Self-host stage 2: read an AgentScript source file, locate its first quoted string literal, and emit LLVM IR that prints exactly those bytes when compiled. The output is a complete LLVM module ready for `clang -O2 -x ir`."
invariant main "The greeting is the byte sequence between the first and second double-quote characters in the input file"
invariant main "The emitted IR is self-contained: declares puts, defines main, exits zero on success"

label startMain

const inputPath CNullTerminatedByteString "C:/Users/Cam/Desktop/AgentScript/AgentScript/bootstrap/input.as"
const readMode CNullTerminatedByteString "r"
const bufferCapacity CByteCount 8192
const readChunkCapacity CByteCount 8191
const oneByte CByteCount 1
const zeroByteOffset CByteCount 0
const zeroByteValue CSignedInt32 0
const quoteCharCode CSignedInt32 34

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

# ---- 5. find the first double-quote ----
call firstQuoteSearchCall c.strchr
arg firstQuoteSearchCall haystack readBuffer
arg firstQuoteSearchCall needle quoteCharCode
run firstQuoteSearchCall
bind firstQuotePointer COpaqueMemoryAddress firstQuoteSearchCall

call firstQuoteNullCheckCall pointer.isNull
arg firstQuoteNullCheckCall pointer firstQuotePointer
run firstQuoteNullCheckCall
bind firstQuoteMissing Bool firstQuoteNullCheckCall
branchIf firstQuoteMissing noQuotedStringFound
branch firstQuoteFound

label firstQuoteFound

# ---- 6. advance past the first quote to the greeting's first byte ----
call greetingStartPointerCall pointer.offset
arg greetingStartPointerCall base firstQuotePointer
arg greetingStartPointerCall offset oneByte
run greetingStartPointerCall
bind greetingStartPointer COpaqueMemoryAddress greetingStartPointerCall

# ---- 7. find the second double-quote ----
call secondQuoteSearchCall c.strchr
arg secondQuoteSearchCall haystack greetingStartPointer
arg secondQuoteSearchCall needle quoteCharCode
run secondQuoteSearchCall
bind secondQuotePointer COpaqueMemoryAddress secondQuoteSearchCall

call secondQuoteNullCheckCall pointer.isNull
arg secondQuoteNullCheckCall pointer secondQuotePointer
run secondQuoteNullCheckCall
bind secondQuoteMissing Bool secondQuoteNullCheckCall
branchIf secondQuoteMissing noQuotedStringFound
branch secondQuoteFound

label secondQuoteFound

# ---- 8. compute greeting byte length = secondQuote - greetingStart ----
call greetingLengthCall pointer.difference
arg greetingLengthCall left secondQuotePointer
arg greetingLengthCall right greetingStartPointer
run greetingLengthCall
bind greetingByteCount CSignedInt64 greetingLengthCall

# Replace the second quote with a null byte so the greeting becomes a
# null-terminated string that we can pass directly to printf("%s", …).
call greetingNullTerminateCall pointer.storeByte
arg greetingNullTerminateCall buffer secondQuotePointer
arg greetingNullTerminateCall offset zeroByteOffset
arg greetingNullTerminateCall value zeroByteValue
run greetingNullTerminateCall

# ---- 9. compute the LLVM constant array length = greetingByteCount + 1 ----
call greetingArrayLengthCall math.addI64
arg greetingArrayLengthCall left greetingByteCount
arg greetingArrayLengthCall right oneByte
run greetingArrayLengthCall
bind greetingArrayLength CSignedInt64 greetingArrayLengthCall

# ---- 10. emit the IR module header and target triple ----
const irModuleBanner CNullTerminatedByteString "; ModuleID = 'AgentScriptStage2SelfHosted'"
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

# ---- 11. emit @.greetingText = private constant [N x i8] c" ----
const greetingConstantOpenFormat CNullTerminatedByteString "@.greetingText = private constant [%lld x i8] c\""
call writeGreetingConstantOpenCall c.printf
arg writeGreetingConstantOpenCall format greetingConstantOpenFormat
arg writeGreetingConstantOpenCall length greetingArrayLength
run writeGreetingConstantOpenCall
ignoreOk writeGreetingConstantOpenCall Void
bindError writeGreetingConstantOpenError CSignedInt32 writeGreetingConstantOpenCall
branchIfError writeGreetingConstantOpenCall consoleWriteFailed

# ---- 12. emit the greeting bytes verbatim (null-terminated %s) ----
const greetingPrintFormat CNullTerminatedByteString "%s"
call writeGreetingBytesCall c.printf
arg writeGreetingBytesCall format greetingPrintFormat
arg writeGreetingBytesCall text greetingStartPointer
run writeGreetingBytesCall
ignoreOk writeGreetingBytesCall Void
bindError writeGreetingBytesError CSignedInt32 writeGreetingBytesCall
branchIfError writeGreetingBytesCall consoleWriteFailed

# ---- 13. close the c"…" literal and emit the rest of the IR ----
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

# Build the puts call line using printf so we can substitute the array length.
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

const irReturnZero CNullTerminatedByteString "  ret i32 0"
call writeIrReturnZeroCall c.puts
arg writeIrReturnZeroCall text irReturnZero
run writeIrReturnZeroCall
ignoreOk writeIrReturnZeroCall Void
bindError writeIrReturnZeroError CSignedInt32 writeIrReturnZeroCall
branchIfError writeIrReturnZeroCall consoleWriteFailed

const irMainFooter CNullTerminatedByteString "}"
call writeIrMainFooterCall c.puts
arg writeIrMainFooterCall text irMainFooter
run writeIrMainFooterCall
ignoreOk writeIrMainFooterCall Void
bindError writeIrMainFooterError CSignedInt32 writeIrMainFooterCall
branchIfError writeIrMainFooterCall consoleWriteFailed

# ---- 14. close the input file ----
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

label noQuotedStringFound
const noQuotedStringFoundExitCode CSignedInt32 3
makeError noQuotedStringFoundFailure MainError.NoQuotedStringFound noQuotedStringFoundExitCode
returnError noQuotedStringFoundFailure

label consoleWriteFailed
const consoleWriteFailedSentinel CSignedInt32 4
makeError consoleWriteFailedFailure MainError.ConsoleWriteFailed consoleWriteFailedSentinel
returnError consoleWriteFailedFailure
