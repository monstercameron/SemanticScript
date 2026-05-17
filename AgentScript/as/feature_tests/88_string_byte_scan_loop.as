# expect.stdout: 14\n
# expect.exit: 0
project StringByteScanLoop
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation findChar
input findChar haystack CNullTerminatedByteString
input findChar needleByte CSignedInt32
output findChar Result CSignedInt64 Void
effect findChar read memory.buffer
memory findChar heap no
async findChar no
purpose findChar "Walk haystack byte-by-byte; return the zero-based offset of the first match or -1 when not found. Exercises pointer.loadByte in a recursion-free loop with multiple branchIf branches sharing a single counter var."
invariant findChar "Stops at the first NUL terminator if no match."
label startFindChar
const zeroPos CSignedInt64 0
const oneStep CSignedInt64 1
const negOneInitial CSignedInt64 -1
const nullByte CSignedInt64 0
var cursor CSignedInt64 zeroPos
label scanLoopFc
call probeByteCall pointer.loadByte
arg probeByteCall buffer haystack
arg probeByteCall offset cursor
run probeByteCall
bind probedByte I8 probeByteCall
call hitNulCall math.equalI64
arg hitNulCall left probedByte
arg hitNulCall right nullByte
run hitNulCall
bind hitNul Bool hitNulCall
branchIf hitNul fcReportNotFound
call matchCheckCall math.equalI64
arg matchCheckCall left probedByte
arg matchCheckCall right needleByte
run matchCheckCall
bind matched Bool matchCheckCall
branchIf matched fcReportFound
call advanceCall math.addI64
arg advanceCall left cursor
arg advanceCall right oneStep
run advanceCall
bind nextCursor CSignedInt64 advanceCall
set cursor nextCursor
branch scanLoopFc
label fcReportFound
returnOk cursor
label fcReportNotFound
returnOk negOneInitial

operation main
input main console Console
output main Result ExitCode MainError
effect main read memory.buffer
effect main write console.stdout
memory main heap no
async main no
purpose main "Search 'hello, agentscript' for the letter 'r' starting at position 0. The 'r' lives at offset 14."
invariant main "Output is 14 (offset of 'r')."
label startMain
const phrase CNullTerminatedByteString "hello, agentscript"
const letterR CSignedInt32 114
call locateCall findChar
arg locateCall haystack phrase
arg locateCall needleByte letterR
run locateCall
bindOk locatedOffset CSignedInt64 locateCall
var offsetStorage I64 0
set offsetStorage locatedOffset
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value offsetStorage
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
