# expect.stdout: len=2 word=hi\n
# expect.exit: 0
project CPrintfThreeArgPtrBindTest
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32
operation main
input main console Console
output main Result ExitCode MainError
effect main read memory.buffer
effect main write memory.buffer
effect main write console.stdout
memory main heap auto
async main no
purpose main "Exercise 3-arg c.printf with two binds where arg2 is i64 (length) and arg3 is i8* (heap buffer). Hits the BBip emitter that emits `i64 %v, i8* %v`."
invariant main "Output is 'len=2 word=hi\\n'."
label startMain
const bufferCap CByteCount 8
const wordFormat CNullTerminatedByteString "hi"
const finalFormat CNullTerminatedByteString "len=%lld word=%s\n"
const twoValue CSignedInt64 2
call mallocCall c.malloc
arg mallocCall size bufferCap
run mallocCall
bind wordBuffer COpaqueMemoryAddress mallocCall

call snprCall c.snprintf
arg snprCall buffer wordBuffer
arg snprCall size bufferCap
arg snprCall format wordFormat
run snprCall
ignoreOk snprCall CSignedInt32

var lengthStorage I64 0
set lengthStorage twoValue
call strlenLoadCall c.strlen
arg strlenLoadCall text wordBuffer
run strlenLoadCall
bind lengthFromBuffer CSignedInt64 strlenLoadCall

call printCall c.printf
arg printCall format finalFormat
arg printCall length lengthFromBuffer
arg printCall word wordBuffer
run printCall
ignoreOk printCall CSignedInt32

call freeCall c.free
arg freeCall ptr wordBuffer
run freeCall
const successfulExitCode ExitCode 0
returnOk successfulExitCode
