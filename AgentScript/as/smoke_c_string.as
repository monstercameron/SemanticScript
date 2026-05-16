project SmokeCString
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError ConsoleWriteFailed CSignedInt32

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
memory main stack max 4KiB
async main no

purpose main "Exercise c.strlen and c.strcmp against printf to confirm pointer-typed args round-trip correctly"
invariant main "Each c.* string call lowers to a direct extern with no AgentScript-side wrapping"

label startMain

const inputProbeText CNullTerminatedByteString "AgentScript"
const inputReferenceText CNullTerminatedByteString "AgentScript"
const inputDistinctText CNullTerminatedByteString "Distinct"
const formatStrlenText CNullTerminatedByteString "strlen(\"%s\") = %lld\n"
const formatStrcmpText CNullTerminatedByteString "strcmp(\"%s\", \"%s\") = %d\n"

call strlenProbeCall c.strlen
arg strlenProbeCall text inputProbeText
run strlenProbeCall
bind probeTextLengthInBytes CByteCount strlenProbeCall

call printStrlenCall c.printf
arg printStrlenCall format formatStrlenText
arg printStrlenCall input inputProbeText
arg printStrlenCall length probeTextLengthInBytes
run printStrlenCall
ignoreOk printStrlenCall Void
bindError printStrlenError CSignedInt32 printStrlenCall
branchIfError printStrlenCall strlenWriteFailed

call strcmpEqualCall c.strcmp
arg strcmpEqualCall left inputProbeText
arg strcmpEqualCall right inputReferenceText
run strcmpEqualCall
bind probeEqualToReferenceComparison CSignedInt32 strcmpEqualCall

call printStrcmpEqualCall c.printf
arg printStrcmpEqualCall format formatStrcmpText
arg printStrcmpEqualCall left inputProbeText
arg printStrcmpEqualCall right inputReferenceText
arg printStrcmpEqualCall comparison probeEqualToReferenceComparison
run printStrcmpEqualCall
ignoreOk printStrcmpEqualCall Void
bindError printStrcmpEqualError CSignedInt32 printStrcmpEqualCall
branchIfError printStrcmpEqualCall strcmpEqualWriteFailed

call strcmpDifferentCall c.strcmp
arg strcmpDifferentCall left inputProbeText
arg strcmpDifferentCall right inputDistinctText
run strcmpDifferentCall
bind probeDifferentFromDistinctComparison CSignedInt32 strcmpDifferentCall

call printStrcmpDifferentCall c.printf
arg printStrcmpDifferentCall format formatStrcmpText
arg printStrcmpDifferentCall left inputProbeText
arg printStrcmpDifferentCall right inputDistinctText
arg printStrcmpDifferentCall comparison probeDifferentFromDistinctComparison
run printStrcmpDifferentCall
ignoreOk printStrcmpDifferentCall Void
bindError printStrcmpDifferentError CSignedInt32 printStrcmpDifferentCall
branchIfError printStrcmpDifferentCall strcmpDifferentWriteFailed

const successfulExitCode ExitCode 0
returnOk successfulExitCode

label strlenWriteFailed
makeError strlenWriteFailure MainError.ConsoleWriteFailed printStrlenError
returnError strlenWriteFailure

label strcmpEqualWriteFailed
makeError strcmpEqualWriteFailure MainError.ConsoleWriteFailed printStrcmpEqualError
returnError strcmpEqualWriteFailure

label strcmpDifferentWriteFailed
makeError strcmpDifferentWriteFailure MainError.ConsoleWriteFailed printStrcmpDifferentError
returnError strcmpDifferentWriteFailure
