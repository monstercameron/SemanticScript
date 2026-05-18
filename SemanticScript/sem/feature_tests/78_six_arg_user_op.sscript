# expect.stdout: 21\n
# expect.exit: 0
project SixArgUserOp
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation sumSix
input sumSix a CSignedInt64
input sumSix b CSignedInt64
input sumSix c CSignedInt64
input sumSix d CSignedInt64
input sumSix e CSignedInt64
input sumSix f CSignedInt64
output sumSix Result CSignedInt64 Void
memory sumSix heap no
async sumSix no
purpose sumSix "Add six CSignedInt64 inputs. Exercises the 6-arg user-op call site emission path."
invariant sumSix "All six params are i64."
label startSumSix
call s1Call math.addI64
arg s1Call left a
arg s1Call right b
run s1Call
bind s1 CSignedInt64 s1Call
call s2Call math.addI64
arg s2Call left s1
arg s2Call right c
run s2Call
bind s2 CSignedInt64 s2Call
call s3Call math.addI64
arg s3Call left s2
arg s3Call right d
run s3Call
bind s3 CSignedInt64 s3Call
call s4Call math.addI64
arg s4Call left s3
arg s4Call right e
run s4Call
bind s4 CSignedInt64 s4Call
call s5Call math.addI64
arg s5Call left s4
arg s5Call right f
run s5Call
bind total CSignedInt64 s5Call
returnOk total

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "sumSix(1,2,3,4,5,6) == 21."
invariant main "Exercises 6-arg user-op call from main."
label startMain
const v1 CSignedInt64 1
const v2 CSignedInt64 2
const v3 CSignedInt64 3
const v4 CSignedInt64 4
const v5 CSignedInt64 5
const v6 CSignedInt64 6
call sumCall sumSix
arg sumCall a v1
arg sumCall b v2
arg sumCall c v3
arg sumCall d v4
arg sumCall e v5
arg sumCall f v6
run sumCall
bindOk total CSignedInt64 sumCall
var totalStorage I64 0
set totalStorage total
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value totalStorage
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
