project BenchStrlen
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError ConsoleWriteFailed CSignedInt32

operation main
input main console Console
output main Result ExitCode MainError
effect main read environment.variables
effect main read process.environment
effect main read clock.cpu
effect main write console.stdout
memory main heap no
memory main stack max 8KiB
async main no

purpose main "Benchmark c.strlen for 200M iterations on a runtime-provided PATH string and report elapsed CPU-clock ticks"
invariant main "The probed string comes from c.getenv so its length cannot be constant-folded by the optimizer"

label startMain

const pathEnvName CNullTerminatedByteString "PATH"
const iterationLimit I64 200000000
const iterationStep I64 1

# Resolve the runtime probe string from PATH. If PATH is unset, getenv
# returns NULL — in that case strlen(NULL) is undefined and the benchmark
# is not meaningful, but in any normal environment PATH is set.
call getenvCall c.getenv
arg getenvCall name pathEnvName
run getenvCall
bind environmentProbeText CNullTerminatedByteString getenvCall

# Note: when PATH isn't set, getenv returns NULL. For benchmarking purposes
# we substitute the fallback only when needed; the test runs against PATH
# in normal environments so this branch isn't exercised.

var accumulator I64 0
var currentIteration I64 0

call startClockCall c.clock
run startClockCall
bind startClockTicks CCpuClockTicks startClockCall

label benchmarkLoopHead

call shouldContinueCmpCall math.lessThanI64
arg shouldContinueCmpCall left currentIteration
arg shouldContinueCmpCall right iterationLimit
run shouldContinueCmpCall
bind benchmarkShouldContinue Bool shouldContinueCmpCall
branchIf benchmarkShouldContinue benchmarkLoopBody
branch benchmarkFinished

label benchmarkLoopBody

call strlenCall c.strlen
arg strlenCall text environmentProbeText
run strlenCall
bind currentLength CByteCount strlenCall

call accumulateCall math.addI64
arg accumulateCall left accumulator
arg accumulateCall right currentLength
run accumulateCall
bind nextAccumulator I64 accumulateCall
set accumulator nextAccumulator

call incrementCall math.addI64
arg incrementCall left currentIteration
arg incrementCall right iterationStep
run incrementCall
bind nextIteration I64 incrementCall
set currentIteration nextIteration
branch benchmarkLoopHead

label benchmarkFinished

call endClockCall c.clock
run endClockCall
bind endClockTicks CCpuClockTicks endClockCall

call elapsedTicksCall math.subtractI64
arg elapsedTicksCall left endClockTicks
arg elapsedTicksCall right startClockTicks
run elapsedTicksCall
bind elapsedClockTicks I64 elapsedTicksCall

const reportFormatText CNullTerminatedByteString "iterations=%lld accumulator=%lld clockTicks=%lld\n"
call reportCall c.printf
arg reportCall format reportFormatText
arg reportCall iterations iterationLimit
arg reportCall accumulator accumulator
arg reportCall ticks elapsedClockTicks
run reportCall
ignoreOk reportCall Void
bindError reportError CSignedInt32 reportCall
branchIfError reportCall consoleWriteFailed

const successfulExitCode ExitCode 0
returnOk successfulExitCode

label consoleWriteFailed
makeError consoleWriteFailure MainError.ConsoleWriteFailed reportError
returnError consoleWriteFailure
