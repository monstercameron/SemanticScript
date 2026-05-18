# expect.stdout: 7\n
# expect.exit: 0
project PointerDifferenceTest
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
purpose main "Compute the byte distance between two pointer.offset'd positions of the same string-const buffer using pointer.difference."
invariant main "Exercises pointer.difference."
label startMain
const sentence CNullTerminatedByteString "abcdefghij"
const positionTwo I64 2
const positionNine I64 9
call leftPtrCall pointer.offset
arg leftPtrCall base sentence
arg leftPtrCall offset positionTwo
run leftPtrCall
bind leftPointer COpaqueMemoryAddress leftPtrCall
call rightPtrCall pointer.offset
arg rightPtrCall base sentence
arg rightPtrCall offset positionNine
run rightPtrCall
bind rightPointer COpaqueMemoryAddress rightPtrCall
call diffCall pointer.difference
arg diffCall left rightPointer
arg diffCall right leftPointer
run diffCall
bind diffValue CSignedInt64 diffCall
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value diffValue
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
