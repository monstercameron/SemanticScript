# expect.stdout: x=10, y=20\n
# expect.exit: 0
project CPrintfThreeArgs
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation makeTen
output makeTen Result CSignedInt64 Void
memory makeTen heap no
async makeTen no
purpose makeTen "Return 10 as a bind. Used to make the printf arg a bind rather than const."
invariant makeTen "Returns 10."
label startMakeTen
const tenValue CSignedInt64 10
returnOk tenValue

operation main
input main console Console
output main Result ExitCode MainError
effect main read memory.buffer
effect main write console.stdout
memory main heap auto
async main no
purpose main "Exercise c.printf with 3 args: format + 2 i64 args. One arg is a bind, the other is a const."
invariant main "Output is 'x=10, y=20\\n'."
label startMain
const triggerSize CByteCount 1
call walkerTriggerCall c.malloc
arg walkerTriggerCall size triggerSize
run walkerTriggerCall
bind triggerBuffer COpaqueMemoryAddress walkerTriggerCall

const xyFormat CNullTerminatedByteString "x=%lld, y=%lld\n"
const twentyValue CSignedInt64 20

call makeTenCall makeTen
run makeTenCall
bindOk xValue CSignedInt64 makeTenCall

call printfCall c.printf
arg printfCall format xyFormat
arg printfCall first xValue
arg printfCall second twentyValue
run printfCall
ignoreOk printfCall CSignedInt32

call freeCall c.free
arg freeCall ptr triggerBuffer
run freeCall
const successfulExitCode ExitCode 0
returnOk successfulExitCode
