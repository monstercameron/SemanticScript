# ============================================================
# AgentScript stdlib import-and-use smoke
# ============================================================
#
# # rationale: every stdlib_as/*.as module ships an `operation main`
#   as its self-test. This file goes one step further — it asks
#   whether those operations can be IMPORTED into a separate
#   program via `importModule` and called from outside. It pulls
#   in a stochastic sample of seven modules spanning the major
#   library tiers (logic, ordering, predicates, integer math,
#   float math, byte strings, time) and exercises one operation
#   from each.
#
# # invariant: every imported operation under test must return its
#   declared value (Bool / CSignedInt64 / CFloat64 / CByteCount /
#   etc.) when called from this file. If any imported operation
#   were not actually reachable through the resolver, the call
#   would fail to typecheck at codegen time and this whole file
#   would fail to compile — that's the unit-test pass condition.
#
# # security: no I/O beyond writing "OK" / "FAIL" on stdout.
#
# # timing: dominated by the imported math operations
#   (squareRootFloat64 Newton iteration ~ 50 floating-point
#   instructions). Whole test runs in microseconds.
#
# # observability: prints "OK\n" on full pass, otherwise emits
#   a tag identifying the first failing assertion so a CI diff
#   pinpoints the broken import.

project StdlibImportSmoke
target console
runtime AgentRuntime 0.1
entry console stdlibImportSmokeMain

error MainError
errorCase MainError StdlibImportSmokeAssertionFailed

# ----- imports under test (stochastic sample of seven modules) -----
importModule bool
importModule compare
importModule ctype
importModule numeric
importModule math
importModule math_float
importModule string
importModule time

operation stdlibImportSmokeMain
input stdlibImportSmokeMain console Console
output stdlibImportSmokeMain Result ExitCode MainError
effect stdlibImportSmokeMain write console.stdout
memoryHeap stdlibImportSmokeMain no
async stdlibImportSmokeMain no
purpose stdlibImportSmokeMain "Call one or two operations from each imported stdlib_as module and assert each result. Demonstrates that importModule successfully wires the stdlib surface into a downstream program."
invariant stdlibImportSmokeMain "All eight imported-module assertions hold; final exit code is 0; stdout is exactly 'OK\\n'."

label startStdlibImportSmokeMain

# ---- bool: negateBoolean(false) == true ----
const importedBooleanFalseLiteral Bool false
const importedBooleanTrueLiteral Bool true
call assertNegateBooleanCall negateBoolean
arg assertNegateBooleanCall valueToNegate importedBooleanFalseLiteral
run assertNegateBooleanCall
bind negateBooleanResult Bool assertNegateBooleanCall
branchIf negateBooleanResult negateBooleanHolds
branch stdlibImportAssertionFailed
label negateBooleanHolds

# ---- bool: andBooleans(true, true) == true ----
call assertAndBooleansCall andBooleans
arg assertAndBooleansCall firstOperand importedBooleanTrueLiteral
arg assertAndBooleansCall secondOperand importedBooleanTrueLiteral
run assertAndBooleansCall
bind andBooleansResult Bool assertAndBooleansCall
branchIf andBooleansResult andBooleansHolds
branch stdlibImportAssertionFailed
label andBooleansHolds

# ---- compare: areSignedInt64ValuesEqual(7, 7) == true ----
const sevenForCompareImport CSignedInt64 7
call assertEqualSevenCall areSignedInt64ValuesEqual
arg assertEqualSevenCall leftValue sevenForCompareImport
arg assertEqualSevenCall rightValue sevenForCompareImport
run assertEqualSevenCall
bind equalSevenResult Bool assertEqualSevenCall
branchIf equalSevenResult equalSevenHolds
branch stdlibImportAssertionFailed
label equalSevenHolds

# ---- compare: isSignedInt64LeftLessThanRight(5, 10) == true ----
const fiveForLessThanImport CSignedInt64 5
const tenForLessThanImport CSignedInt64 10
call assertFiveLessThanTenCall isSignedInt64LeftLessThanRight
arg assertFiveLessThanTenCall leftValue fiveForLessThanImport
arg assertFiveLessThanTenCall rightValue tenForLessThanImport
run assertFiveLessThanTenCall
bind fiveLessThanTenResult Bool assertFiveLessThanTenCall
branchIf fiveLessThanTenResult fiveLessThanTenHolds
branch stdlibImportAssertionFailed
label fiveLessThanTenHolds

# ---- ctype: isAsciiDecimalDigitCode('5') == true ----
const asciiFiveCharacterCode CSignedInt32 53
call assertDigitFiveImportCall isAsciiDecimalDigitCode
arg assertDigitFiveImportCall characterCode asciiFiveCharacterCode
run assertDigitFiveImportCall
bind digitFiveImportResult Bool assertDigitFiveImportCall
branchIf digitFiveImportResult digitFiveImportHolds
branch stdlibImportAssertionFailed
label digitFiveImportHolds

# ---- ctype: convertAsciiLetterCodeToUppercase('h') == 'H' ----
const lowercaseHForConvertImport CSignedInt32 104
const uppercaseHExpectedImport CSignedInt32 72
call assertConvertUppercaseCall convertAsciiLetterCodeToUppercase
arg assertConvertUppercaseCall characterCode lowercaseHForConvertImport
run assertConvertUppercaseCall
bind convertUppercaseResult CSignedInt32 assertConvertUppercaseCall
call checkConvertUppercaseCall math.equalI64
arg checkConvertUppercaseCall left convertUppercaseResult
arg checkConvertUppercaseCall right uppercaseHExpectedImport
run checkConvertUppercaseCall
bind convertUppercaseOk Bool checkConvertUppercaseCall
branchIf convertUppercaseOk convertUppercaseHolds
branch stdlibImportAssertionFailed
label convertUppercaseHolds

# ---- numeric: incrementSignedInt64(41) == 42 ----
const fortyOneForIncrementImport CSignedInt64 41
const fortyTwoExpectedImport CSignedInt64 42
call assertIncrementCall incrementSignedInt64
arg assertIncrementCall inputValue fortyOneForIncrementImport
run assertIncrementCall
bind incrementResult CSignedInt64 assertIncrementCall
call checkIncrementCall math.equalI64
arg checkIncrementCall left incrementResult
arg checkIncrementCall right fortyTwoExpectedImport
run checkIncrementCall
bind incrementOk Bool checkIncrementCall
branchIf incrementOk incrementHolds
branch stdlibImportAssertionFailed
label incrementHolds

# ---- numeric: sumSignedInt64OneThroughN(10) == 55 ----
const tenForGaussSumImport CSignedInt64 10
const fiftyFiveExpectedImport CSignedInt64 55
call assertGaussSumCall sumSignedInt64OneThroughN
arg assertGaussSumCall inputValue tenForGaussSumImport
run assertGaussSumCall
bind gaussSumResult CSignedInt64 assertGaussSumCall
call checkGaussSumCall math.equalI64
arg checkGaussSumCall left gaussSumResult
arg checkGaussSumCall right fiftyFiveExpectedImport
run checkGaussSumCall
bind gaussSumOk Bool checkGaussSumCall
branchIf gaussSumOk gaussSumHolds
branch stdlibImportAssertionFailed
label gaussSumHolds

# ---- math: factorialSignedInt64(6) == 720 ----
const sixForFactorialImport CSignedInt64 6
const sevenTwentyExpectedImport CSignedInt64 720
call assertFactorialImportCall factorialSignedInt64
arg assertFactorialImportCall inputValue sixForFactorialImport
run assertFactorialImportCall
bind factorialImportResult CSignedInt64 assertFactorialImportCall
call checkFactorialImportCall math.equalI64
arg checkFactorialImportCall left factorialImportResult
arg checkFactorialImportCall right sevenTwentyExpectedImport
run checkFactorialImportCall
bind factorialImportOk Bool checkFactorialImportCall
branchIf factorialImportOk factorialImportHolds
branch stdlibImportAssertionFailed
label factorialImportHolds

# ---- math: isSignedInt64Prime(19) == true ----
const nineteenPrimeImport CSignedInt64 19
call assertPrimeImportCall isSignedInt64Prime
arg assertPrimeImportCall inputValue nineteenPrimeImport
run assertPrimeImportCall
bind primeImportResult Bool assertPrimeImportCall
branchIf primeImportResult primeImportHolds
branch stdlibImportAssertionFailed
label primeImportHolds

# ---- math_float: absoluteFloat64(-2.5) == 2.5 ----
const negativeTwoPointFiveImport CFloat64 -2.5
const twoPointFiveExpectedImport CFloat64 2.5
call assertAbsoluteFloatCall absoluteFloat64
arg assertAbsoluteFloatCall inputValue negativeTwoPointFiveImport
run assertAbsoluteFloatCall
bind absoluteFloatResult CFloat64 assertAbsoluteFloatCall
call checkAbsoluteFloatCall math.equalF64
arg checkAbsoluteFloatCall left absoluteFloatResult
arg checkAbsoluteFloatCall right twoPointFiveExpectedImport
run checkAbsoluteFloatCall
bind absoluteFloatOk Bool checkAbsoluteFloatCall
branchIf absoluteFloatOk absoluteFloatHolds
branch stdlibImportAssertionFailed
label absoluteFloatHolds

# ---- string: stringByteLength("agentscript") == 11 ----
const agentscriptLiteralForLengthImport CNullTerminatedByteString "agentscript"
const elevenBytesExpectedImport CByteCount 11
call assertStringByteLengthCall stringByteLength
arg assertStringByteLengthCall inputText agentscriptLiteralForLengthImport
run assertStringByteLengthCall
bind stringByteLengthResult CByteCount assertStringByteLengthCall
call checkStringByteLengthCall math.equalI64
arg checkStringByteLengthCall left stringByteLengthResult
arg checkStringByteLengthCall right elevenBytesExpectedImport
run checkStringByteLengthCall
bind stringByteLengthOk Bool checkStringByteLengthCall
branchIf stringByteLengthOk stringByteLengthHolds
branch stdlibImportAssertionFailed
label stringByteLengthHolds

# ---- time: isGregorianLeapYear(2024) == true ----
const twentyTwentyFourYearImport CSignedInt64 2024
call assertLeapYear2024ImportCall isGregorianLeapYear
arg assertLeapYear2024ImportCall candidateYear twentyTwentyFourYearImport
run assertLeapYear2024ImportCall
bind leapYear2024Result Bool assertLeapYear2024ImportCall
branchIf leapYear2024Result leapYear2024Holds
branch stdlibImportAssertionFailed
label leapYear2024Holds

# ---- time: convertSecondsToWholeHours(7200) == 2 ----
const sevenThousandTwoHundredSecondsImport CSignedInt64 7200
const twoHoursExpectedImport CSignedInt64 2
call assertConvertHoursCall convertSecondsToWholeHours
arg assertConvertHoursCall secondCount sevenThousandTwoHundredSecondsImport
run assertConvertHoursCall
bind convertHoursResult CSignedInt64 assertConvertHoursCall
call checkConvertHoursCall math.equalI64
arg checkConvertHoursCall left convertHoursResult
arg checkConvertHoursCall right twoHoursExpectedImport
run checkConvertHoursCall
bind convertHoursOk Bool checkConvertHoursCall
branchIf convertHoursOk convertHoursHolds
branch stdlibImportAssertionFailed
label convertHoursHolds

# All assertions held — emit OK and exit 0.
const stdlibImportSuccessMessage CNullTerminatedByteString "OK"
call writeStdlibImportSuccessCall console.writeLine
arg writeStdlibImportSuccessCall console console
arg writeStdlibImportSuccessCall text stdlibImportSuccessMessage
run writeStdlibImportSuccessCall
ignoreOk writeStdlibImportSuccessCall Void
const stdlibImportExitOk ExitCode 0
returnOk stdlibImportExitOk

label stdlibImportAssertionFailed
makeError stdlibImportSmokeFailure MainError.StdlibImportSmokeAssertionFailed
returnError stdlibImportSmokeFailure
