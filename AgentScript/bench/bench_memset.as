project BenchMemset
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError AllocationFailed CSignedInt32
errorCase MainError ConsoleWriteFailed CSignedInt32

operation main
input main console Console
output main Result ExitCode MainError
effect main read clock.cpu
effect main write console.stdout
effect main allocate heap
effect main free heap
effect main write memory.buffer
effect main read memory.buffer
memory main heap yes
memory main stack max 8KiB
async main no

purpose main "Benchmark c.memset by writing a 64 KiB buffer 200000 times and printing the elapsed CPU-clock ticks"
invariant main "The loop counter is monotonically increasing and bounded by iterationLimit"
invariant main "The buffer is allocated via c.malloc before the loop and freed via c.free after timing stops"

label startMain

const iterationLimit I64 200000
const iterationStep I64 1
const bufferSize CByteCount 65536
const observationModulus I64 65536
var currentIteration I64 0
var observationAccumulator I64 0

# Allocate the 64 KiB benchmark buffer.
call mallocCall c.malloc
arg mallocCall size bufferSize
run mallocCall
bindOk benchmarkBuffer COpaqueMemoryAddress mallocCall
# c.malloc returns NULL on failure; treat a zero result as the error path.
# (The compiler's branchIfError uses the signed-less-than-zero convention,
# but malloc semantically returns NULL == 0. We branch directly on the bind.)

# Start the CPU-clock counter.
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

call memsetCall c.memset
arg memsetCall buffer benchmarkBuffer
arg memsetCall fillByte currentIteration
arg memsetCall byteCount bufferSize
run memsetCall
bind memsetReturn COpaqueMemoryAddress memsetCall

# Read a varying byte after each memset so the optimizer cannot elide the
# memset calls. The observation accumulator depends on every memset's
# completion and is reported alongside the timing data.
call moduloOffsetCall math.moduloI64
arg moduloOffsetCall left currentIteration
arg moduloOffsetCall right observationModulus
run moduloOffsetCall
bind observationOffset I64 moduloOffsetCall

call observationLoadCall pointer.loadByte
arg observationLoadCall buffer benchmarkBuffer
arg observationLoadCall offset observationOffset
run observationLoadCall
bind observationByte I8 observationLoadCall

call observationAccumulateCall math.addI64
arg observationAccumulateCall left observationAccumulator
arg observationAccumulateCall right observationByte
run observationAccumulateCall
bind nextObservation I64 observationAccumulateCall
set observationAccumulator nextObservation

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

const reportFormatText CNullTerminatedByteString "iterations=%lld bufferSize=%lld accumulator=%lld clockTicks=%lld\n"
call reportCall c.printf
arg reportCall format reportFormatText
arg reportCall iterations iterationLimit
arg reportCall buffer bufferSize
arg reportCall accumulator observationAccumulator
arg reportCall ticks elapsedClockTicks
run reportCall
ignoreOk reportCall Void
bindError reportError CSignedInt32 reportCall
branchIfError reportCall consoleWriteFailed

call freeCall c.free
arg freeCall pointer benchmarkBuffer
run freeCall

const successfulExitCode ExitCode 0
returnOk successfulExitCode

label consoleWriteFailed
makeError consoleWriteFailure MainError.ConsoleWriteFailed reportError
returnError consoleWriteFailure
