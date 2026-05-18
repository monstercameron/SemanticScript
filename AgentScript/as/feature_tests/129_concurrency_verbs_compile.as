# expect.stdout: ok\n
# expect.exit: 0
project ConcurrencyVerbsCompile
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke: every channel / lock / interval / select / worker-pool body verb compiles to runnable IR (synchronous no-op lowering)."
invariant main "Exits 0 and prints 'ok'."
label startMain

const zeroVal I64 0

# Channels (spec §22): synchronous-only no-op lowering. `receive` registers
# its OUT name as a zero bind.
send myChannel zeroVal
receive recvVal I64 myChannel
branchIfChannelClosed myChannel done

# Locks (spec §22): drop.
lock myMutex
unlock myMutex

# Intervals (spec §23): drop / no-op.
interval ticker maxRate 60
startInterval ticker
awaitIntervalTick ticker

# Worker pools (spec §22): declarative; `awaitWork` registers its name.
workerPool myPool maxWorkers 4
work myJob target myJobOp
workArg myJob input zeroVal
submitWork myJob myPool
awaitWork myJob

# Select / race (spec §20): drop. `branchSelected` falls through.
select chooser
selectCase chooser foo barBranch
runSelect chooser
branchSelected chooser foo barBranch

branch done

label barBranch
branch done

label done
const okText CNullTerminatedByteString "ok"
call writeCall console.writeLine
arg writeCall console console
arg writeCall text okText
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
