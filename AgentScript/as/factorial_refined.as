# factorial_refined.as
#
# Migration of as/factorial.as to refined syntax. Same behavior — compute
# factorial(10) = 3628800 and print as a single line.
#
# Verify identical behavior to as/factorial.as via:
#   python compiler/ascc.py as/factorial_refined.as --emit-ir /tmp/f.ll
#   clang /tmp/f.ll -o /tmp/f.exe && /tmp/f.exe   # prints `3628800\n`

section program.factorialRefined

project FactorialRefined
target console
runtime AgentRuntime 0.1
entry console main

section program.factorialRefined.types

type FactorialCounter I64
type FactorialAccumulator I64
type PositiveFactorialStep I64

section program.factorialRefined.errors

error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError
errorCase MainError FactorialUpperLimitTooLarge
errorCase MainError FactorialAccumulatorOverflowed FactorialOverflowError

section program.factorialRefined.literals

domainLiteral factorialLowerLimit FactorialCounter 1
domainLiteral factorialUpperLimit FactorialCounter 10
domainLiteral factorialOverflowSafeUpperLimit FactorialCounter 20
storage module immutable factorialStepValue PositiveFactorialStep 1
domainLiteral factorialAccumulatorInitial FactorialAccumulator 1
storage module immutable successfulExitCode ExitCode 0

section program.factorialRefined.operations

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memoryHeap main no
memoryStackLimit main 16KiB
async main no
operationBody main sourceTape

purpose main "Compute the factorial of factorialUpperLimit and print the result as a single line"
invariant main "At factorialLoopHead, currentFactorialAccumulator equals factorial(currentFactorialCounter - 1)"
invariant main "factorialUpperLimit must be less than or equal to factorialOverflowSafeUpperLimit before the loop runs"
invariant main "factorialStepValue is strictly greater than zero"

label startMain

var currentFactorialCounter FactorialCounter factorialLowerLimit
var currentFactorialAccumulator FactorialAccumulator factorialAccumulatorInitial

# rationale: Confirm factorialUpperLimit stays inside the range where I64 factorial accumulation is provably safe.
call factorialUpperLimitSafetyCheckCall FactorialCounter.lessThanOrEqual
arg factorialUpperLimitSafetyCheckCall left factorialUpperLimit
arg factorialUpperLimitSafetyCheckCall right factorialOverflowSafeUpperLimit
run factorialUpperLimitSafetyCheckCall
bind factorialUpperLimitIsOverflowSafe Bool factorialUpperLimitSafetyCheckCall

branchIf factorialUpperLimitIsOverflowSafe factorialLoopHead
branch factorialUpperLimitRejected

label factorialLoopHead

# rationale: Continue while currentFactorialCounter is less than or equal to factorialUpperLimit.
call factorialRangeCheckCall FactorialCounter.lessThanOrEqual
arg factorialRangeCheckCall left currentFactorialCounter
arg factorialRangeCheckCall right factorialUpperLimit
run factorialRangeCheckCall
bind factorialShouldContinue Bool factorialRangeCheckCall

branchIf factorialShouldContinue factorialLoopBody
branch factorialFinished

label factorialLoopBody

# rationale: Multiply currentFactorialAccumulator by currentFactorialCounter using checked arithmetic.
call factorialAccumulatorMultiplyCall FactorialAccumulator.checkedMultiplyByCounter
arg factorialAccumulatorMultiplyCall accumulator currentFactorialAccumulator
arg factorialAccumulatorMultiplyCall counter currentFactorialCounter
run factorialAccumulatorMultiplyCall
bindOk nextFactorialAccumulator FactorialAccumulator factorialAccumulatorMultiplyCall
bindError factorialAccumulatorOverflowError FactorialOverflowError factorialAccumulatorMultiplyCall
branchIfError factorialAccumulatorMultiplyCall factorialAccumulatorOverflowed

set currentFactorialAccumulator nextFactorialAccumulator

# rationale: Advance the counter by exactly factorialStepValue.
call factorialCounterIncrementCall FactorialCounter.addPositiveStep
arg factorialCounterIncrementCall counter currentFactorialCounter
arg factorialCounterIncrementCall step factorialStepValue
run factorialCounterIncrementCall
bind nextFactorialCounter FactorialCounter factorialCounterIncrementCall

set currentFactorialCounter nextFactorialCounter
branch factorialLoopHead

label factorialFinished

# rationale: Emit the final accumulator as a single line of standard output.
call writeFinalFactorialAccumulatorCall console.writeIntegerLine
arg writeFinalFactorialAccumulatorCall console console
arg writeFinalFactorialAccumulatorCall value currentFactorialAccumulator
run writeFinalFactorialAccumulatorCall
ignoreOk writeFinalFactorialAccumulatorCall Void
bindError writeFinalFactorialAccumulatorError ConsoleWriteError writeFinalFactorialAccumulatorCall
branchIfError writeFinalFactorialAccumulatorCall consoleWriteFailed

returnOk successfulExitCode

label factorialUpperLimitRejected
# failure: The configured factorialUpperLimit exceeds the I64 overflow-safe limit.
makeError factorialUpperLimitRejectedFailure MainError.FactorialUpperLimitTooLarge
returnError factorialUpperLimitRejectedFailure

label factorialAccumulatorOverflowed
# failure: The checked multiplication reported overflow.
makeError factorialAccumulatorOverflowFailure MainError.FactorialAccumulatorOverflowed factorialAccumulatorOverflowError
returnError factorialAccumulatorOverflowFailure

label consoleWriteFailed
# failure: The console write failed after the factorial value was already computed.
makeError consoleWriteFailure MainError.ConsoleWriteFailed writeFinalFactorialAccumulatorError
returnError consoleWriteFailure
