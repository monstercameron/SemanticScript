# expect.stdout: hello\nworld\n
# expect.exit: 0
project WriteLineWithBindString
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation pickGreeting
input pickGreeting useFirst CSignedInt64
output pickGreeting Result CNullTerminatedByteString Void
memory pickGreeting heap no
async pickGreeting no
purpose pickGreeting "Return one of two compile-time string constants based on the flag. Used to verify that console.writeLine can consume an i8* bind (rather than a direct const reference) when written via c.putchar bytes for now (string-replay path doesn't survive walker mode)."
invariant pickGreeting "Returns 'hello' or 'world' as a pointer."
label startPickGreeting
const helloMessage CNullTerminatedByteString "hello"
const worldMessage CNullTerminatedByteString "world"
const zeroPivot CSignedInt64 0
call useFirstBoolCall math.greaterThanI64
arg useFirstBoolCall left useFirst
arg useFirstBoolCall right zeroPivot
run useFirstBoolCall
bind chooseFirst Bool useFirstBoolCall
branchIf chooseFirst pickHello
returnOk worldMessage
label pickHello
returnOk helloMessage

operation putString
input putString message CNullTerminatedByteString
output putString Result CByteCount Void
effect putString read memory.buffer
effect putString write console.stdout
memory putString heap no
async putString no
purpose putString "Walk the message byte by byte writing each via c.putchar until the NUL terminator. Returns the byte count."
invariant putString "Stops at the first zero byte."
label startPutString
const zeroIndex CSignedInt64 0
const oneIncrement CSignedInt64 1
const nullByte CSignedInt64 0
var positionIndex CSignedInt64 zeroIndex
label loopTop
call byteLoadCall pointer.loadByte
arg byteLoadCall buffer message
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
arg advanceCall right oneIncrement
run advanceCall
bind nextPosition CSignedInt64 advanceCall
set positionIndex nextPosition
branch loopTop
label finishWriting
returnOk positionIndex

operation putLine
input putLine message CNullTerminatedByteString
output putLine Result CByteCount Void
effect putLine read memory.buffer
effect putLine write console.stdout
memory putLine heap no
async putLine no
purpose putLine "Write message via putString then emit a trailing newline."
invariant putLine "Returns the byte count of message (not including the newline)."
label startPutLine
call bodyCall putString
arg bodyCall message message
run bodyCall
bindOk byteCount CByteCount bodyCall
const newlineByte CSignedInt32 10
call newlineCall c.putchar
arg newlineCall c newlineByte
run newlineCall
returnOk byteCount

operation main
input main console Console
output main Result ExitCode MainError
effect main read memory.buffer
effect main write console.stdout
memory main heap no
async main no
purpose main "Pick and emit two greetings: pickGreeting(1) -> 'hello\n', pickGreeting(0) -> 'world\n'. Exercises pointer-returning user op, pointer-typed arg to a sibling user op, and putString loop using pointer.loadByte/c.putchar."
invariant main "Output is 'hello\nworld\n'."
label startMain
const oneSelector CSignedInt64 1
const zeroSelector CSignedInt64 0
call pickHelloCall pickGreeting
arg pickHelloCall useFirst oneSelector
run pickHelloCall
bindOk helloPointer CNullTerminatedByteString pickHelloCall
call writeHelloCall putLine
arg writeHelloCall message helloPointer
run writeHelloCall
ignoreOk writeHelloCall CByteCount
call pickWorldCall pickGreeting
arg pickWorldCall useFirst zeroSelector
run pickWorldCall
bindOk worldPointer CNullTerminatedByteString pickWorldCall
call writeWorldCall putLine
arg writeWorldCall message worldPointer
run writeWorldCall
ignoreOk writeWorldCall CByteCount
const successfulExitCode ExitCode 0
returnOk successfulExitCode
