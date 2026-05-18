# expect.stdout: 88\n
# expect.exit: 0
project MallocStoreLoad
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
effect main allocate heap
effect main free heap
effect main write console.stdout
memory main heap yes
async main no
purpose main "Allocate 4 bytes, write 'X' (88) at offset 0, read it back, print."
invariant main "Tests c.malloc + pointer.storeByte + pointer.loadByte + c.free."
label startMain
const bufferBytes CByteCount 4
const zeroOffset I64 0
const xByteValue CSignedInt32 88
call mallocCall c.malloc
arg mallocCall size bufferBytes
run mallocCall
bind heapBuffer COpaqueMemoryAddress mallocCall
call storeCall pointer.storeByte
arg storeCall buffer heapBuffer
arg storeCall offset zeroOffset
arg storeCall value xByteValue
run storeCall
call loadCall pointer.loadByte
arg loadCall buffer heapBuffer
arg loadCall offset zeroOffset
run loadCall
bind loadedByte I8 loadCall
var loadedVar I64 zeroOffset
set loadedVar loadedByte
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value loadedVar
run writeCall
ignoreOk writeCall Void
call freeCall c.free
arg freeCall ptr heapBuffer
run freeCall
const successfulExitCode ExitCode 0
returnOk successfulExitCode
