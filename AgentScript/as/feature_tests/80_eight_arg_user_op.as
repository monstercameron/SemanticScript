# expect.stdout: 36\n
# expect.exit: 0
project EightArgUserOp
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation sumEight
input sumEight a CSignedInt64
input sumEight b CSignedInt64
input sumEight c CSignedInt64
input sumEight d CSignedInt64
input sumEight e CSignedInt64
input sumEight f CSignedInt64
input sumEight g CSignedInt64
input sumEight h CSignedInt64
output sumEight Result CSignedInt64 Void
memory sumEight heap no
async sumEight no
purpose sumEight "Add eight CSignedInt64 inputs. Exercises the slot 4-8 emission path at its widest."
invariant sumEight "All eight params are i64."
label startSumEight
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
bind s5 CSignedInt64 s5Call
call s6Call math.addI64
arg s6Call left s5
arg s6Call right g
run s6Call
bind s6 CSignedInt64 s6Call
call s7Call math.addI64
arg s7Call left s6
arg s7Call right h
run s7Call
bind total CSignedInt64 s7Call
returnOk total

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "sumEight(1..8) == 36."
invariant main "Exercises 8-arg user-op call from main."
label startMain
const v1 CSignedInt64 1
const v2 CSignedInt64 2
const v3 CSignedInt64 3
const v4 CSignedInt64 4
const v5 CSignedInt64 5
const v6 CSignedInt64 6
const v7 CSignedInt64 7
const v8 CSignedInt64 8
call sumCall sumEight
arg sumCall a v1
arg sumCall b v2
arg sumCall c v3
arg sumCall d v4
arg sumCall e v5
arg sumCall f v6
arg sumCall g v7
arg sumCall h v8
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
