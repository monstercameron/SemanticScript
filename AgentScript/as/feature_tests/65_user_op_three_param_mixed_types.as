# expect.stdout: 9\n
# expect.exit: 0
project UserOpThreeParamMixed
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation indexCharInPair
input indexCharInPair leftBuffer CNullTerminatedByteString
input indexCharInPair rightBuffer CNullTerminatedByteString
input indexCharInPair preferRight CSignedInt64
output indexCharInPair Result CSignedInt64 Void
memory indexCharInPair heap no
async indexCharInPair no
purpose indexCharInPair "Take two strings and a selector. When selector is non-zero return the length of rightBuffer; otherwise the length of leftBuffer. Exercises mixed-type param signatures (i8*, i8*, i64) and pointer-typed arg2 emission at call sites."
invariant indexCharInPair "Calls c.strlen on the chosen buffer."
label startIndexCharInPair
const zeroSelectorThreshold CSignedInt64 0
call selectorPositiveCall math.greaterThanI64
arg selectorPositiveCall left preferRight
arg selectorPositiveCall right zeroSelectorThreshold
run selectorPositiveCall
bind selectorPositive Bool selectorPositiveCall
branchIf selectorPositive measureRightBuffer
call leftLenCall c.strlen
arg leftLenCall s leftBuffer
run leftLenCall
bind leftLength CByteCount leftLenCall
returnOk leftLength
label measureRightBuffer
call rightLenCall c.strlen
arg rightLenCall s rightBuffer
run rightLenCall
bind rightLength CByteCount rightLenCall
returnOk rightLength

operation main
input main console Console
output main Result ExitCode MainError
effect main read memory.buffer
effect main write console.stdout
memory main heap no
async main no
purpose main "Call indexCharInPair('short', 'something', 1) which returns length 9 (length of 'something')."
invariant main "Exercises three-param user op with mixed i8*/i8*/i64 args."
label startMain
const shortBuffer CNullTerminatedByteString "short"
const longBuffer CNullTerminatedByteString "something"
const useRightSelector CSignedInt64 1
call measureCall indexCharInPair
arg measureCall leftBuffer shortBuffer
arg measureCall rightBuffer longBuffer
arg measureCall preferRight useRightSelector
run measureCall
bindOk measuredLength CSignedInt64 measureCall
var measuredStorage I64 0
set measuredStorage measuredLength
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value measuredStorage
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
