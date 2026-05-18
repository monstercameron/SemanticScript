# expect.stdout: 30\n
# expect.exit: 0
# expect.xfail: feature_coverage.py runs through bootstrap_general.as which does not yet honor mutable sharedState within a lock/unlock pair. Direct ascc.py compilation is correct: single-thread lock is a no-op; the counter walks 0→10→20→30. `python compiler/ascc.py THIS_FILE --emit-exe /tmp/x.exe && /tmp/x.exe` prints `30`.
project LockCriticalSectionState
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32
const zeroInitial I64 0
const tenIncrement I64 10
sharedState process mutable lockedRegionTotal I64 zeroInitial
operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Three lock/unlock pairs around state increments; final value reflects all three updates."
invariant main "Output is 30 (10+10+10), not 0 or 10."
label startMain
lock totalMutex
call addOnceCall math.addI64
arg addOnceCall left lockedRegionTotal
arg addOnceCall right tenIncrement
run addOnceCall
bind firstSum I64 addOnceCall
set sharedState lockedRegionTotal firstSum
unlock totalMutex
lock totalMutex
call addTwiceCall math.addI64
arg addTwiceCall left lockedRegionTotal
arg addTwiceCall right tenIncrement
run addTwiceCall
bind secondSum I64 addTwiceCall
set sharedState lockedRegionTotal secondSum
unlock totalMutex
lock totalMutex
call addThriceCall math.addI64
arg addThriceCall left lockedRegionTotal
arg addThriceCall right tenIncrement
run addThriceCall
bind thirdSum I64 addThriceCall
set sharedState lockedRegionTotal thirdSum
unlock totalMutex
call writeTotalCall console.writeIntegerLine
arg writeTotalCall console console
arg writeTotalCall value lockedRegionTotal
run writeTotalCall
ignoreOk writeTotalCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
