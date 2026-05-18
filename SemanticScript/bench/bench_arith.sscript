project BenchArith
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
memory main stack max 4KiB
async main no

purpose main "Pure-codegen benchmark with a Fibonacci-style data-dependency chain; each iteration depends on the previous two values so the loop cannot be folded"
invariant main "Each iteration performs exactly one addition and two register-to-register moves"

label startMain

const iterationLimit I64 200000000
const iterationStep I64 1
const fibonacciInitialPreviousValue I64 1
const fibonacciInitialCurrentValue I64 1

var currentIteration I64 0
var fibonacciPreviousValue I64 fibonacciInitialPreviousValue
var fibonacciCurrentValue I64 fibonacciInitialCurrentValue

call startClockCall c.clock
run startClockCall
bind startClockTicks CCpuClockTicks startClockCall

label arithLoopHead

call shouldContinueCmpCall math.lessThanI64
arg shouldContinueCmpCall left currentIteration
arg shouldContinueCmpCall right iterationLimit
run shouldContinueCmpCall
bind arithShouldContinue Bool shouldContinueCmpCall
branchIf arithShouldContinue arithLoopBody
branch arithFinished

label arithLoopBody

# next = a + b
call fibonacciAdvanceCall math.addI64
arg fibonacciAdvanceCall left fibonacciPreviousValue
arg fibonacciAdvanceCall right fibonacciCurrentValue
run fibonacciAdvanceCall
bind fibonacciNextValue I64 fibonacciAdvanceCall

# a = b
set fibonacciPreviousValue fibonacciCurrentValue
# b = next
set fibonacciCurrentValue fibonacciNextValue

# i = i + 1
call incrementCall math.addI64
arg incrementCall left currentIteration
arg incrementCall right iterationStep
run incrementCall
bind nextIteration I64 incrementCall
set currentIteration nextIteration
branch arithLoopHead

label arithFinished

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
arg reportCall accumulator fibonacciCurrentValue
arg reportCall ticks elapsedClockTicks
run reportCall
ignoreOk reportCall Void
bindError reportError CSignedInt32 reportCall
branchIfError reportCall reportWriteFailed

const successfulExitCode ExitCode 0
returnOk successfulExitCode

label reportWriteFailed
makeError reportWriteFailure MainError.ConsoleWriteFailed reportError
returnError reportWriteFailure
