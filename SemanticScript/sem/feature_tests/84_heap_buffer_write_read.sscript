# expect.stdout: HELLO\n
# expect.exit: 0
project HeapBufferWriteRead
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation writeAt
input writeAt buffer COpaqueMemoryAddress
input writeAt position CSignedInt64
input writeAt byteValue CSignedInt32
output writeAt Result CSignedInt32 Void
effect writeAt write memory.buffer
memory writeAt heap no
async writeAt no
purpose writeAt "Store a single byte at buffer[position]. Encapsulates pointer.storeByte so the test exercises a user op that returns void-like int."
invariant writeAt "Returns 0 to match CSignedInt32 contract."
label startWriteAt
call doStoreCall pointer.storeByte
arg doStoreCall buffer buffer
arg doStoreCall offset position
arg doStoreCall value byteValue
run doStoreCall
const writeOk CSignedInt32 0
returnOk writeOk

operation main
input main console Console
output main Result ExitCode MainError
effect main read memory.buffer
effect main write memory.buffer
effect main write console.stdout
memory main heap auto
async main no
purpose main "Allocate a 6-byte buffer, write 'HELLO\\0' via writeAt() calls, then print it via console.writeLine."
invariant main "Validates pointer-typed user op param + repeated pointer.storeByte calls + console.writeLine over a heap-allocated buffer."
label startMain
const bufferSize CByteCount 6
call mallocCall c.malloc
arg mallocCall size bufferSize
run mallocCall
bind bufferPointer COpaqueMemoryAddress mallocCall

const pos0 CSignedInt64 0
const pos1 CSignedInt64 1
const pos2 CSignedInt64 2
const pos3 CSignedInt64 3
const pos4 CSignedInt64 4
const pos5 CSignedInt64 5
const byteH CSignedInt32 72
const byteE CSignedInt32 69
const byteL CSignedInt32 76
const byteOLetter CSignedInt32 79
const byteNul CSignedInt32 0

call write0 writeAt
arg write0 buffer bufferPointer
arg write0 position pos0
arg write0 byteValue byteH
run write0
ignoreOk write0 CSignedInt32

call write1 writeAt
arg write1 buffer bufferPointer
arg write1 position pos1
arg write1 byteValue byteE
run write1
ignoreOk write1 CSignedInt32

call write2 writeAt
arg write2 buffer bufferPointer
arg write2 position pos2
arg write2 byteValue byteL
run write2
ignoreOk write2 CSignedInt32

call write3 writeAt
arg write3 buffer bufferPointer
arg write3 position pos3
arg write3 byteValue byteL
run write3
ignoreOk write3 CSignedInt32

call write4 writeAt
arg write4 buffer bufferPointer
arg write4 position pos4
arg write4 byteValue byteOLetter
run write4
ignoreOk write4 CSignedInt32

call write5 writeAt
arg write5 buffer bufferPointer
arg write5 position pos5
arg write5 byteValue byteNul
run write5
ignoreOk write5 CSignedInt32

call writeLineCall console.writeLine
arg writeLineCall console console
arg writeLineCall text bufferPointer
run writeLineCall
ignoreOk writeLineCall Void

call freeCall c.free
arg freeCall ptr bufferPointer
run freeCall
const successfulExitCode ExitCode 0
returnOk successfulExitCode
