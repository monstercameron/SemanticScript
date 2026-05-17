# expect.stdout: opened\n
# expect.exit: 0
project CFopenFcloseTest
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32
operation main
input main console Console
output main Result ExitCode MainError
effect main read filesystem
effect main write console.stdout
memory main heap no
async main no
purpose main "Open a real existing file (this very test file) via c.fopen, then close it via c.fclose. Print 'opened' on success."
invariant main "Exercises c.fopen, pointer.isNull on its result, and c.fclose."
label startMain
const filePath CNullTerminatedByteString "as/feature_tests/92_c_fopen_fclose.as"
const readMode CNullTerminatedByteString "r"
const okMessage CNullTerminatedByteString "opened"
call openCall c.fopen
arg openCall path filePath
arg openCall mode readMode
run openCall
bind fileHandle COpaqueMemoryAddress openCall
call nullCheckCall pointer.isNull
arg nullCheckCall p fileHandle
run nullCheckCall
bind handleIsNull Bool nullCheckCall
branchIf handleIsNull openFailed
call putsCall c.puts
arg putsCall text okMessage
run putsCall
ignoreOk putsCall CSignedInt32
call closeCall c.fclose
arg closeCall stream fileHandle
run closeCall
ignoreOk closeCall CSignedInt32
const successfulExitCode ExitCode 0
returnOk successfulExitCode
label openFailed
const failedExit CSignedInt32 1
makeError openFailure MainError.Placeholder failedExit
returnError openFailure
