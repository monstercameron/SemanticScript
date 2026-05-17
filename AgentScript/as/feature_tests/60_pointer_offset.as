# expect.stdout: o\n
# expect.exit: 0
project PointerOffsetTest
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32
operation main
input main console Console
output main Result ExitCode MainError
effect main read memory.buffer
effect main write console.stdout
memory main heap no
async main no
purpose main "Use pointer.offset to GEP past the first 4 bytes of a string const and load the 5th byte ('o' from 'hello')."
invariant main "Exercises pointer.offset + pointer.loadByte chain."
label startMain
const greeting CNullTerminatedByteString "hello"
const fourOffset I64 4
call shiftCall pointer.offset
arg shiftCall base greeting
arg shiftCall offset fourOffset
run shiftCall
bind shiftedPointer COpaqueMemoryAddress shiftCall
const zeroOffset I64 0
call loadCall pointer.loadByte
arg loadCall buffer shiftedPointer
arg loadCall offset zeroOffset
run loadCall
bind byteValue I8 loadCall
call writeByteCall c.putchar
arg writeByteCall c byteValue
run writeByteCall
const newlineChar CSignedInt32 10
call writeNewlineCall c.putchar
arg writeNewlineCall c newlineChar
run writeNewlineCall
const successfulExitCode ExitCode 0
returnOk successfulExitCode
