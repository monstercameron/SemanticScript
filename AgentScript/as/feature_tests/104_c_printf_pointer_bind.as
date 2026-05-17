# expect.stdout: msg=val=99\n
# expect.exit: 0
project CPrintfPointerBindTest
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
purpose main "Pass a pointer-typed bind (i8*) as the %s arg to c.printf. Exercises the new pointer-bind path in emitCprintfPlusBind: the emitter must classify the bind as pointer and emit `i8* %arg` instead of `i64 %arg`."
invariant main "Output is 'msg=val=99\\n'."
label startMain
const bufferCap CByteCount 32
const formatString CNullTerminatedByteString "val=%lld"
const finalFormat CNullTerminatedByteString "msg=%s\n"
const ninetyNine CSignedInt64 99
call mallocCall c.malloc
arg mallocCall size bufferCap
run mallocCall
bind heapBuffer COpaqueMemoryAddress mallocCall

call snprCall c.snprintf
arg snprCall buffer heapBuffer
arg snprCall size bufferCap
arg snprCall format formatString
arg snprCall value ninetyNine
run snprCall
ignoreOk snprCall CSignedInt32

call printCall c.printf
arg printCall format finalFormat
arg printCall value heapBuffer
run printCall
ignoreOk printCall CSignedInt32

call freeCall c.free
arg freeCall ptr heapBuffer
run freeCall
const successfulExitCode ExitCode 0
returnOk successfulExitCode
