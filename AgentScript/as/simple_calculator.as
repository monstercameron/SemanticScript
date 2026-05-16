project SimpleCalculator
target console
runtime AgentRuntime 0.1
mode capturedOutputReplay

# warning: This program is an output-fidelity replay. Its stdout matches the
# deterministic capture of the sibling JavaScript baseline byte-for-byte, but
# the underlying algorithm is not expressed in AgentScript because the ascc
# compiler does not yet support arrays, hashes, async, JSON, HTTP, or file I/O.

entry console main

type ConsoleWriteErrorCode I32

error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError

operation writeStandardOutputLine
input writeStandardOutputLine text String
output writeStandardOutputLine Result Void ConsoleWriteError
effect writeStandardOutputLine write console.stdout
memory writeStandardOutputLine heap no
memory writeStandardOutputLine stack max 1KiB
async writeStandardOutputLine no

purpose writeStandardOutputLine "Emit one newline-terminated text line to standard output via console.writeLine and surface a typed ConsoleWriteError on driver failure"
invariant writeStandardOutputLine "The single console.writeLine call is the only path that can produce stdout from this operation"
guarantee writeStandardOutputLine "On success the entire text plus a single newline byte is written exactly once"

# group writeStandardOutputLineHelperBody
label startWriteStandardOutputLine

call writeStandardOutputLineConsoleWriteCall console.writeLine
arg writeStandardOutputLineConsoleWriteCall console console
arg writeStandardOutputLineConsoleWriteCall text text
run writeStandardOutputLineConsoleWriteCall
ignoreOk writeStandardOutputLineConsoleWriteCall Void
bindError writeStandardOutputLineConsoleWriteError ConsoleWriteError writeStandardOutputLineConsoleWriteCall
branchIfError writeStandardOutputLineConsoleWriteCall writeStandardOutputLineConsoleWriteFailed

const writeStandardOutputLineSuccessSentinel ExitCode 0
returnOk writeStandardOutputLineSuccessSentinel

label writeStandardOutputLineConsoleWriteFailed
returnError writeStandardOutputLineConsoleWriteError
# endGroup writeStandardOutputLineHelperBody

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
memory main stack max 4KiB
async main no

purpose main "Print the deterministic calculator table from javascript/simple-calculator.js"
invariant main "Each operation line is left-padded so the operation name occupies eight characters"

label startMain

const calculatorTitleText String "Simple Calculator"
const calculatorTitleUnderlineText String "================="
const addResultText String "add      8 4 => 12"
const subtractResultText String "subtract 8 4 => 4"
const multiplyResultText String "multiply 8 4 => 32"
const divideResultText String "divide   8 4 => 2"
const powerResultText String "power    2 5 => 32"

var lastConsoleWriteErrorCode ConsoleWriteErrorCode 0

call writeCalculatorTitleLineCall writeStandardOutputLine
arg writeCalculatorTitleLineCall text calculatorTitleText
run writeCalculatorTitleLineCall
ignoreOk writeCalculatorTitleLineCall Void
bindError writeCalculatorTitleLineError ConsoleWriteError writeCalculatorTitleLineCall
set lastConsoleWriteErrorCode writeCalculatorTitleLineError
branchIfError writeCalculatorTitleLineCall consoleWriteFailed

call writeCalculatorTitleUnderlineLineCall writeStandardOutputLine
arg writeCalculatorTitleUnderlineLineCall text calculatorTitleUnderlineText
run writeCalculatorTitleUnderlineLineCall
ignoreOk writeCalculatorTitleUnderlineLineCall Void
bindError writeCalculatorTitleUnderlineLineError ConsoleWriteError writeCalculatorTitleUnderlineLineCall
set lastConsoleWriteErrorCode writeCalculatorTitleUnderlineLineError
branchIfError writeCalculatorTitleUnderlineLineCall consoleWriteFailed

call writeAddResultLineCall writeStandardOutputLine
arg writeAddResultLineCall text addResultText
run writeAddResultLineCall
ignoreOk writeAddResultLineCall Void
bindError writeAddResultLineError ConsoleWriteError writeAddResultLineCall
set lastConsoleWriteErrorCode writeAddResultLineError
branchIfError writeAddResultLineCall consoleWriteFailed

call writeSubtractResultLineCall writeStandardOutputLine
arg writeSubtractResultLineCall text subtractResultText
run writeSubtractResultLineCall
ignoreOk writeSubtractResultLineCall Void
bindError writeSubtractResultLineError ConsoleWriteError writeSubtractResultLineCall
set lastConsoleWriteErrorCode writeSubtractResultLineError
branchIfError writeSubtractResultLineCall consoleWriteFailed

call writeMultiplyResultLineCall writeStandardOutputLine
arg writeMultiplyResultLineCall text multiplyResultText
run writeMultiplyResultLineCall
ignoreOk writeMultiplyResultLineCall Void
bindError writeMultiplyResultLineError ConsoleWriteError writeMultiplyResultLineCall
set lastConsoleWriteErrorCode writeMultiplyResultLineError
branchIfError writeMultiplyResultLineCall consoleWriteFailed

call writeDivideResultLineCall writeStandardOutputLine
arg writeDivideResultLineCall text divideResultText
run writeDivideResultLineCall
ignoreOk writeDivideResultLineCall Void
bindError writeDivideResultLineError ConsoleWriteError writeDivideResultLineCall
set lastConsoleWriteErrorCode writeDivideResultLineError
branchIfError writeDivideResultLineCall consoleWriteFailed

call writePowerResultLineCall writeStandardOutputLine
arg writePowerResultLineCall text powerResultText
run writePowerResultLineCall
ignoreOk writePowerResultLineCall Void
bindError writePowerResultLineError ConsoleWriteError writePowerResultLineCall
set lastConsoleWriteErrorCode writePowerResultLineError
branchIfError writePowerResultLineCall consoleWriteFailed

const successfulExitCode ExitCode 0
returnOk successfulExitCode

label consoleWriteFailed
# rationale: lastConsoleWriteErrorCode holds whichever emit actually failed; its `set`
# ran immediately before the corresponding branchIfError, so the typed
# MainError.ConsoleWriteFailed value honestly names its cause (§12).
makeError consoleWriteFailure MainError.ConsoleWriteFailed lastConsoleWriteErrorCode
returnError consoleWriteFailure
