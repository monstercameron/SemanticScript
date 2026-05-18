# expect.stdout: 5\n
# expect.exit: 0
project PointerUserOpChain
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation skipFirstCharacter
input skipFirstCharacter buffer CNullTerminatedByteString
output skipFirstCharacter Result CNullTerminatedByteString Void
memory skipFirstCharacter heap no
async skipFirstCharacter no
purpose skipFirstCharacter "Return a pointer to the second byte of `buffer` (skip one byte forward)."
invariant skipFirstCharacter "Used to demonstrate that pointer-returning user ops chain — `c.strlen(skipFirstCharacter(s))` should compute strlen(s) - 1 for non-empty input."
label startSkipFirstCharacter
const oneByte CSignedInt64 1
call advanceCall pointer.offset
arg advanceCall base buffer
arg advanceCall offset oneByte
run advanceCall
bind advancedPointer COpaqueMemoryAddress advanceCall
returnOk advancedPointer

operation main
input main console Console
output main Result ExitCode MainError
effect main read memory.buffer
effect main write console.stdout
memory main heap no
async main no
purpose main "Take 'shello' (6 chars), skip the first, c.strlen the result == 5. Verifies pointer-returning user op + pointer arg to libc."
invariant main "Output is 5."
label startMain
const fullText CNullTerminatedByteString "shello"
call shortenCall skipFirstCharacter
arg shortenCall buffer fullText
run shortenCall
bindOk shortenedPointer CNullTerminatedByteString shortenCall
call lengthCall c.strlen
arg lengthCall s shortenedPointer
run lengthCall
bind measuredLength CByteCount lengthCall
var measurementStorage I64 0
set measurementStorage measuredLength
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value measurementStorage
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
