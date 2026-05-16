project Countdown
target console
runtime AgentRuntime 0.1

entry console main

type CountdownValue I64
type PositiveCountdownStep I64

error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
memory main stack max 16KiB
async main no

purpose main "Print countdown values from countdownStartValue down to countdownEndValue, one value per output line"
invariant main "The loop terminates because currentCountdownValue decreases by countdownStepValue every iteration"
invariant main "The loop body runs only while currentCountdownValue is greater than or equal to countdownEndValue"
invariant main "countdownStepValue is strictly greater than zero"

label startMain

const countdownStartValue CountdownValue 5
const countdownEndValue CountdownValue 1
const countdownStepValue PositiveCountdownStep 1
var currentCountdownValue CountdownValue countdownStartValue

label countdownLoopHead

# rationale: Continue while currentCountdownValue is greater than or equal to countdownEndValue.
call countdownRangeCheckCall CountdownValue.greaterThanOrEqual
arg countdownRangeCheckCall left currentCountdownValue
arg countdownRangeCheckCall right countdownEndValue
run countdownRangeCheckCall
bind countdownShouldContinue Bool countdownRangeCheckCall

branchIf countdownShouldContinue countdownLoopBody
branch countdownFinished

label countdownLoopBody

# rationale: Print the current countdown value with a newline; pass console explicitly.
call printCurrentCountdownValueCall console.writeIntegerLine
arg printCurrentCountdownValueCall console console
arg printCurrentCountdownValueCall value currentCountdownValue
run printCurrentCountdownValueCall
ignoreOk printCurrentCountdownValueCall Void
bindError printCurrentCountdownValueError ConsoleWriteError printCurrentCountdownValueCall
branchIfError printCurrentCountdownValueCall consoleWriteFailed

# rationale: Decrement after successful printing so failed output does not advance progress.
call countdownValueDecrementCall CountdownValue.subtractPositiveStep
arg countdownValueDecrementCall value currentCountdownValue
arg countdownValueDecrementCall step countdownStepValue
run countdownValueDecrementCall
bind nextCountdownValue CountdownValue countdownValueDecrementCall

set currentCountdownValue nextCountdownValue
branch countdownLoopHead

label countdownFinished
const successfulExitCode ExitCode 0
returnOk successfulExitCode

label consoleWriteFailed
makeError consoleWriteFailure MainError.ConsoleWriteFailed printCurrentCountdownValueError
returnError consoleWriteFailure
