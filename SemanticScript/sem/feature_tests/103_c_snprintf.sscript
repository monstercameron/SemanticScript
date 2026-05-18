# expect.stdout: val=42\n
# expect.exit: 0
project CSnprintfTest
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
purpose main "Format an integer into a heap buffer via c.snprintf, then print the buffer via c.puts. Exercises 4-arg snprintf with all const args."
invariant main "Output is 'val=42\\n'."
label startMain
const bufferCap CByteCount 32
const fmtString CNullTerminatedByteString "val=%lld"
const fortyTwo CSignedInt64 42
call mallocCall c.malloc
arg mallocCall size bufferCap
run mallocCall
bind targetBuffer COpaqueMemoryAddress mallocCall

call snprCall c.snprintf
arg snprCall buffer targetBuffer
arg snprCall size bufferCap
arg snprCall format fmtString
arg snprCall value fortyTwo
run snprCall
ignoreOk snprCall CSignedInt32

call putsCall c.puts
arg putsCall text targetBuffer
run putsCall
ignoreOk putsCall CSignedInt32

call freeCall c.free
arg freeCall ptr targetBuffer
run freeCall
const successfulExitCode ExitCode 0
returnOk successfulExitCode
