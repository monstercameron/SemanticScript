# expect.stdout: l\n
# expect.exit: 0
project ChainedPointerOffset
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
purpose main "Apply pointer.offset twice (1 byte then 1 more byte) to reach index 2 ('l') of 'hello' and print it."
invariant main "Exercises pointer.offset where the BASE is itself a bind from a prior pointer.offset."
label startMain
const greeting CNullTerminatedByteString "hello"
const oneStep I64 1
call shiftOnceCall pointer.offset
arg shiftOnceCall base greeting
arg shiftOnceCall offset oneStep
run shiftOnceCall
bind oneShifted COpaqueMemoryAddress shiftOnceCall
call shiftTwiceCall pointer.offset
arg shiftTwiceCall base oneShifted
arg shiftTwiceCall offset oneStep
run shiftTwiceCall
bind twoShifted COpaqueMemoryAddress shiftTwiceCall
const zeroOffset I64 0
call loadCall pointer.loadByte
arg loadCall buffer twoShifted
arg loadCall offset zeroOffset
run loadCall
bind byteValue I8 loadCall
call writeByteCall c.putchar
arg writeByteCall c byteValue
run writeByteCall
const newlineByte CSignedInt32 10
call writeNewlineCall c.putchar
arg writeNewlineCall c newlineByte
run writeNewlineCall
const successfulExitCode ExitCode 0
returnOk successfulExitCode
