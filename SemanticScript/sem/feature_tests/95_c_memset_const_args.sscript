# expect.stdout: XXX\n
# expect.exit: 0
project CMemsetConstArgs
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
purpose main "Allocate 4 bytes, memset to 'X' (88), null-terminate, print. Uses CONST args for byteValue and n."
invariant main "Exercises c.memset's const-arg path."
label startMain
const bufferSize CByteCount 4
const xByteValue CSignedInt64 88
const threeBytes CSignedInt64 3
call mallocCall c.malloc
arg mallocCall size bufferSize
run mallocCall
bind targetBuffer COpaqueMemoryAddress mallocCall
call memsetCall c.memset
arg memsetCall dst targetBuffer
arg memsetCall byteValue xByteValue
arg memsetCall n threeBytes
run memsetCall
const lastPos CSignedInt64 3
const nullByte CSignedInt32 0
call nullStoreCall pointer.storeByte
arg nullStoreCall buffer targetBuffer
arg nullStoreCall offset lastPos
arg nullStoreCall value nullByte
run nullStoreCall
call putsCall c.puts
arg putsCall text targetBuffer
run putsCall
ignoreOk putsCall CSignedInt32
call freeCall c.free
arg freeCall ptr targetBuffer
run freeCall
const successfulExitCode ExitCode 0
returnOk successfulExitCode
