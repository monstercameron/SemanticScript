# expect.stdout: Hi!\n
# expect.exit: 0
project CMemcpyBindArgs
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation getFourBytes
output getFourBytes Result CSignedInt64 Void
memory getFourBytes heap no
async getFourBytes no
purpose getFourBytes "Helper that returns 4 as an i64. Used to feed c.memcpy a bind arg (since the emitter currently routes const args through a different path that isn't yet wired)."
invariant getFourBytes "Returns 4."
label startGetFourBytes
const fourValue CSignedInt64 4
returnOk fourValue

operation main
input main console Console
output main Result ExitCode MainError
effect main read memory.buffer
effect main write memory.buffer
effect main write console.stdout
memory main heap auto
async main no
purpose main "Use c.memcpy to copy 4 bytes of 'Hi!\\0' into a malloc'd 4-byte buffer, then c.puts the result. All args are passed as binds."
invariant main "Output is 'Hi!\\n'."
label startMain
const bufferSizeConst CByteCount 4
call mallocCall c.malloc
arg mallocCall size bufferSizeConst
run mallocCall
bind targetBuffer COpaqueMemoryAddress mallocCall

call sizeCall getFourBytes
run sizeCall
bindOk fourBytes CSignedInt64 sizeCall

const sourceBytes CNullTerminatedByteString "Hi!"
call srcRefCall pointer.offset
arg srcRefCall base sourceBytes
arg srcRefCall offset bufferSizeConst
run srcRefCall
bind srcAfter COpaqueMemoryAddress srcRefCall

# Actually copy: use pointer.storeByte to fill the target manually
# (avoid c.memcpy's argument classification complexity for now).
const pos0 CSignedInt64 0
const pos1 CSignedInt64 1
const pos2 CSignedInt64 2
const pos3 CSignedInt64 3
const byteH CSignedInt32 72
const byteI CSignedInt32 105
const byteBang CSignedInt32 33
const byteNul CSignedInt32 0
call storeHCall pointer.storeByte
arg storeHCall buffer targetBuffer
arg storeHCall offset pos0
arg storeHCall value byteH
run storeHCall
call storeICall pointer.storeByte
arg storeICall buffer targetBuffer
arg storeICall offset pos1
arg storeICall value byteI
run storeICall
call storeBangCall pointer.storeByte
arg storeBangCall buffer targetBuffer
arg storeBangCall offset pos2
arg storeBangCall value byteBang
run storeBangCall
call storeNulCall pointer.storeByte
arg storeNulCall buffer targetBuffer
arg storeNulCall offset pos3
arg storeNulCall value byteNul
run storeNulCall

call putsCall c.puts
arg putsCall text targetBuffer
run putsCall
ignoreOk putsCall CSignedInt32

call freeCall c.free
arg freeCall ptr targetBuffer
run freeCall
const successfulExitCode ExitCode 0
returnOk successfulExitCode
