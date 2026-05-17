# expect.stdout: 1\n1\n0\n
# expect.exit: 0
project FpClassificationTest
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation makeNegOnePtFive
output makeNegOnePtFive Result CFloat64 Void
memory makeNegOnePtFive heap no
async makeNegOnePtFive no
purpose makeNegOnePtFive "Return -1.5 as a bind, since FP classification emitters expect bind/var/param args (not raw consts)."
invariant makeNegOnePtFive "Returns -1.5."
label startMakeNegOnePtFive
const negOnePtFive CFloat64 -1.5
returnOk negOnePtFive

operation makePiApprox
output makePiApprox Result CFloat64 Void
memory makePiApprox heap no
async makePiApprox no
purpose makePiApprox "Return 3.14 as a bind."
invariant makePiApprox "Returns 3.14."
label startMakePiApprox
const piApprox CFloat64 3.14
returnOk piApprox

operation makePosTwoPtFive
output makePosTwoPtFive Result CFloat64 Void
memory makePosTwoPtFive heap no
async makePosTwoPtFive no
purpose makePosTwoPtFive "Return 2.5 as a bind."
invariant makePosTwoPtFive "Returns 2.5."
label startMakePosTwoPtFive
const posTwoPtFive CFloat64 2.5
returnOk posTwoPtFive

operation main
input main console Console
output main Result ExitCode MainError
effect main read memory.buffer
effect main write console.stdout
memory main heap auto
async main no
purpose main "Exercise c.signbit (1 for negative, 0 for positive) and c.isfinite (1 for finite). Inputs come from user ops to ensure they're binds at the call site."
invariant main "Output: signbit(-1.5)=1, isfinite(3.14)=1, signbit(2.5)=0."
label startMain
const triggerSize CByteCount 1
call walkerTriggerCall c.malloc
arg walkerTriggerCall size triggerSize
run walkerTriggerCall
bind triggerBuffer COpaqueMemoryAddress walkerTriggerCall

call makeNegCall makeNegOnePtFive
run makeNegCall
bindOk negValue CFloat64 makeNegCall
call signbitNeg c.signbit
arg signbitNeg value negValue
run signbitNeg
bind signbitNegRes CSignedInt64 signbitNeg
var sbNegStore I64 0
set sbNegStore signbitNegRes
call write1Call console.writeIntegerLine
arg write1Call console console
arg write1Call value sbNegStore
run write1Call
ignoreOk write1Call Void

call makePiCall makePiApprox
run makePiCall
bindOk piValue CFloat64 makePiCall
call isfiniteCall c.isfinite
arg isfiniteCall value piValue
run isfiniteCall
bind isfiniteRes CSignedInt64 isfiniteCall
var ifStore I64 0
set ifStore isfiniteRes
call write2Call console.writeIntegerLine
arg write2Call console console
arg write2Call value ifStore
run write2Call
ignoreOk write2Call Void

call makePosCall makePosTwoPtFive
run makePosCall
bindOk posValue CFloat64 makePosCall
call signbitPos c.signbit
arg signbitPos value posValue
run signbitPos
bind signbitPosRes CSignedInt64 signbitPos
var sbPosStore I64 0
set sbPosStore signbitPosRes
call write3Call console.writeIntegerLine
arg write3Call console console
arg write3Call value sbPosStore
run write3Call
ignoreOk write3Call Void

call freeCall c.free
arg freeCall ptr triggerBuffer
run freeCall
const successfulExitCode ExitCode 0
returnOk successfulExitCode
