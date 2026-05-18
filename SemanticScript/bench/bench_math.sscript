project BenchMath
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError ConsoleWriteFailed CSignedInt32

operation main
input main console Console
output main Result ExitCode MainError
effect main read clock.cpu
effect main write console.stdout
memory main heap no
memory main stack max 8KiB
async main no

purpose main "Benchmark c.sqrt + c.log + c.sin for 5M iterations and print elapsed CPU-clock ticks"
invariant main "Each loop iteration calls all three transcendental libc routines exactly once"

label startMain

const iterationLimit I64 5000000
const iterationStep I64 1
const accumulatorInitial CFloat64 0.0
var currentIteration I64 1
var accumulator CFloat64 accumulatorInitial

call startClockCall c.clock
run startClockCall
bind startClockTicks CCpuClockTicks startClockCall

label benchmarkLoopHead

call shouldContinueCmpCall math.lessThanOrEqualI64
arg shouldContinueCmpCall left currentIteration
arg shouldContinueCmpCall right iterationLimit
run shouldContinueCmpCall
bind benchmarkShouldContinue Bool shouldContinueCmpCall

branchIf benchmarkShouldContinue benchmarkLoopBody
branch benchmarkFinished

label benchmarkLoopBody

# Compute sqrt(iteration) + log(iteration) + sin(iteration).
call sqrtCall c.sqrt
arg sqrtCall x currentIteration
run sqrtCall
bind sqrtResult CFloat64 sqrtCall

call logCall c.log
arg logCall x currentIteration
run logCall
bind logResult CFloat64 logCall

call sinCall c.sin
arg sinCall x currentIteration
run sinCall
bind sinResult CFloat64 sinCall

call partialSumCall math.addF64
arg partialSumCall left sqrtResult
arg partialSumCall right logResult
run partialSumCall
bind sqrtLogSum CFloat64 partialSumCall

call iterationValueCall math.addF64
arg iterationValueCall left sqrtLogSum
arg iterationValueCall right sinResult
run iterationValueCall
bind iterationValue CFloat64 iterationValueCall

call accumulateCall math.addF64
arg accumulateCall left accumulator
arg accumulateCall right iterationValue
run accumulateCall
bind nextAccumulator CFloat64 accumulateCall
set accumulator nextAccumulator

# i = i + 1
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

const reportFormatText CNullTerminatedByteString "iterations=%lld accumulator=%.6f clockTicks=%lld\n"
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
