# expect.stdout: hi\nbye\n
# expect.exit: 0
project PointerTypedVar
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation putString
input putString s CNullTerminatedByteString
output putString Result CByteCount Void
effect putString read memory.buffer
effect putString write console.stdout
memory putString heap no
async putString no
purpose putString "Write every byte of s to stdout via c.putchar until a NUL terminator."
invariant putString "Stops at the first zero byte."
label startPutString
const zeroIndex CSignedInt64 0
const oneStep CSignedInt64 1
const nullByte CSignedInt64 0
var positionIndex CSignedInt64 zeroIndex
label loopTop
call byteLoadCall pointer.loadByte
arg byteLoadCall buffer s
arg byteLoadCall offset positionIndex
run byteLoadCall
bind currentByte I8 byteLoadCall
call isTerminatorCall math.equalI64
arg isTerminatorCall left currentByte
arg isTerminatorCall right nullByte
run isTerminatorCall
bind isTerminator Bool isTerminatorCall
branchIf isTerminator finishWriting
call writeByteCall c.putchar
arg writeByteCall c currentByte
run writeByteCall
call advanceCall math.addI64
arg advanceCall left positionIndex
arg advanceCall right oneStep
run advanceCall
bind nextPosition CSignedInt64 advanceCall
set positionIndex nextPosition
branch loopTop
label finishWriting
returnOk positionIndex

operation main
input main console Console
output main Result ExitCode MainError
effect main read memory.buffer
effect main write console.stdout
memory main heap no
async main no
purpose main "Initialize a CNullTerminatedByteString var to 'hi', print it via putString + newline, then SET it to 'bye' and print again. Exercises pointer-typed var alloca + init + set + load + arg passing."
invariant main "Output is 'hi\nbye\n'."
label startMain
const helloMsg CNullTerminatedByteString "hi"
const byeMsg CNullTerminatedByteString "bye"
const newlineByte CSignedInt32 10
var greeting CNullTerminatedByteString helloMsg
call putGreetingCall putString
arg putGreetingCall s greeting
run putGreetingCall
ignoreOk putGreetingCall CByteCount
call newlineCall1 c.putchar
arg newlineCall1 c newlineByte
run newlineCall1
set greeting byeMsg
call putByeCall putString
arg putByeCall s greeting
run putByeCall
ignoreOk putByeCall CByteCount
call newlineCall2 c.putchar
arg newlineCall2 c newlineByte
run newlineCall2
const successfulExitCode ExitCode 0
returnOk successfulExitCode
