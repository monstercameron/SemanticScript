# ============================================================
# AGENTSCRIPT STDLIB TESTS: time
# ============================================================
#
# Companion smoke + extended unit tests for stdlib_as/time.as.
# Exercises the deterministic conversions and Gregorian leap-year
# predicate. The OS-time wrappers (readProcessCpuClockTicks,
# readCurrentUnixEpochSeconds) are invoked but not value-asserted
# (non-deterministic across runs); they exist to verify the
# capability + heap-slot plumbing still wires correctly across the
# importModule boundary.
#
# Pattern: stdlib_as/foo.as ships pure-module operations only;
# stdlib_as/foo.test.as carries every smoke / unit test for it.

project StdTimeTest
target console
runtime AgentRuntime 0.1
entry console main

importModule time

error MainError
errorCase MainError TimeSmokeAssertionFailed
errorCase MainError ConsoleWriteFailed

# section capability
# rationale: smoke-test main writes a single OK line to stdout
#   and also exercises the OS-time wrappers, so it needs the
#   clock + heap capabilities those wrappers require.
capability stdoutWriteCapability console.stdout write
capability clockCpuReadCapability clock.cpu read
capability clockRealTimeReadCapability clock.realTime read
capability heapAllocationCapability heap allocate
capability heapFreeCapability heap free

# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
useCapability main stdoutWriteCapability
useCapability main clockCpuReadCapability
useCapability main clockRealTimeReadCapability
useCapability main heapAllocationCapability
useCapability main heapFreeCapability
effect main write console.stdout
effect main read clock.cpu
effect main read clock.realTime
effect main allocate heap
effect main free heap
memoryHeap main yes
memoryAllocationSource main exerciseUnixTimeCall
async main no
purpose main "Smoke-test the deterministic time helpers (conversions + leap-year). The clock readers are exercised but their values are not asserted (non-deterministic)."
invariant main "convertSecondsToWholeHours(3661) == 1; convertHoursToSeconds(2) == 7200; isGregorianLeapYear(2000) == true; isGregorianLeapYear(1900) == false; isGregorianLeapYear(2024) == true."

label startMain

# convertSecondsToWholeHours(3661) == 1
const threeThousandSixHundredSixtyOne CSignedInt64 3661
const oneHourCount CSignedInt64 1
call assertHoursCall convertSecondsToWholeHours
arg assertHoursCall secondCount threeThousandSixHundredSixtyOne
run assertHoursCall
bind hoursResult CSignedInt64 assertHoursCall
call checkHoursCall math.equalI64
arg checkHoursCall left hoursResult
arg checkHoursCall right oneHourCount
run checkHoursCall
bind hoursOk Bool checkHoursCall
branchIf hoursOk hoursHolds
branch smokeAssertionFailed
label hoursHolds

# convertHoursToSeconds(2) == 7200
const twoHourCount CSignedInt64 2
const sevenThousandTwoHundredValue CSignedInt64 7200
call assertHoursToSecondsCall convertHoursToSeconds
arg assertHoursToSecondsCall hourCount twoHourCount
run assertHoursToSecondsCall
bind hoursToSecondsResult CSignedInt64 assertHoursToSecondsCall
call checkHoursToSecondsCall math.equalI64
arg checkHoursToSecondsCall left hoursToSecondsResult
arg checkHoursToSecondsCall right sevenThousandTwoHundredValue
run checkHoursToSecondsCall
bind hoursToSecondsOk Bool checkHoursToSecondsCall
branchIf hoursToSecondsOk hoursToSecondsHolds
branch smokeAssertionFailed
label hoursToSecondsHolds

# isGregorianLeapYear(2000) == true
const yearTwoThousand CSignedInt64 2000
call assertLeapYear2000Call isGregorianLeapYear
arg assertLeapYear2000Call candidateYear yearTwoThousand
run assertLeapYear2000Call
bind leap2000Result Bool assertLeapYear2000Call
branchIf leap2000Result leap2000Holds
branch smokeAssertionFailed
label leap2000Holds

# isGregorianLeapYear(1900) == false
const yearNineteenHundred CSignedInt64 1900
call assertLeapYear1900Call isGregorianLeapYear
arg assertLeapYear1900Call candidateYear yearNineteenHundred
run assertLeapYear1900Call
bind leap1900Result Bool assertLeapYear1900Call
branchIf leap1900Result smokeAssertionFailed

# isGregorianLeapYear(2024) == true
const yearTwoThousandTwentyFour CSignedInt64 2024
call assertLeapYear2024Call isGregorianLeapYear
arg assertLeapYear2024Call candidateYear yearTwoThousandTwentyFour
run assertLeapYear2024Call
bind leap2024Result Bool assertLeapYear2024Call
branchIf leap2024Result leap2024Holds
branch smokeAssertionFailed
label leap2024Holds

# ============================================================
# Extended unit tests: coverage for the 3 ops the smoke previously
# omitted (convertSecondsToWholeMinutes, convertMinutesToSeconds,
# convertUnixEpochSecondsToDays) plus boundary leap-year cases.
# ============================================================

const zeroSecondsValue CSignedInt64 0
const oneTwentySeconds CSignedInt64 120
const twoMinutes CSignedInt64 2
const fiftyNineSeconds CSignedInt64 59
const threeMinutes CSignedInt64 3
const oneEightyValue CSignedInt64 180
const oneFullDaySeconds CSignedInt64 86400
const oneDayCount CSignedInt64 1
const yearTwentyTwentyThree CSignedInt64 2023
const yearTwoFourHundred CSignedInt64 2400

# convertSecondsToWholeMinutes(120) == 2
call minFromSecCall convertSecondsToWholeMinutes
arg minFromSecCall secondCount oneTwentySeconds
run minFromSecCall
bind minFromSecResult CSignedInt64 minFromSecCall
call checkMinFromSecCall math.equalI64
arg checkMinFromSecCall left minFromSecResult
arg checkMinFromSecCall right twoMinutes
run checkMinFromSecCall
bind minFromSecOk Bool checkMinFromSecCall
branchIf minFromSecOk minFromSecHolds
branch smokeAssertionFailed
label minFromSecHolds

# convertSecondsToWholeMinutes(59) == 0 (truncation boundary)
call minFromSecZeroCall convertSecondsToWholeMinutes
arg minFromSecZeroCall secondCount fiftyNineSeconds
run minFromSecZeroCall
bind minFromSecZeroResult CSignedInt64 minFromSecZeroCall
call checkMinFromSecZeroCall math.equalI64
arg checkMinFromSecZeroCall left minFromSecZeroResult
arg checkMinFromSecZeroCall right zeroSecondsValue
run checkMinFromSecZeroCall
bind minFromSecZeroOk Bool checkMinFromSecZeroCall
branchIf minFromSecZeroOk minFromSecZeroHolds
branch smokeAssertionFailed
label minFromSecZeroHolds

# convertMinutesToSeconds(3) == 180
call secFromMinCall convertMinutesToSeconds
arg secFromMinCall minuteCount threeMinutes
run secFromMinCall
bind secFromMinResult CSignedInt64 secFromMinCall
call checkSecFromMinCall math.equalI64
arg checkSecFromMinCall left secFromMinResult
arg checkSecFromMinCall right oneEightyValue
run checkSecFromMinCall
bind secFromMinOk Bool checkSecFromMinCall
branchIf secFromMinOk secFromMinHolds
branch smokeAssertionFailed
label secFromMinHolds

# convertMinutesToSeconds(0) == 0
call secFromZeroMinCall convertMinutesToSeconds
arg secFromZeroMinCall minuteCount zeroSecondsValue
run secFromZeroMinCall
bind secFromZeroMinResult CSignedInt64 secFromZeroMinCall
call checkSecFromZeroMinCall math.equalI64
arg checkSecFromZeroMinCall left secFromZeroMinResult
arg checkSecFromZeroMinCall right zeroSecondsValue
run checkSecFromZeroMinCall
bind secFromZeroMinOk Bool checkSecFromZeroMinCall
branchIf secFromZeroMinOk secFromZeroMinHolds
branch smokeAssertionFailed
label secFromZeroMinHolds

# convertUnixEpochSecondsToDays(86400) == 1
call daysCall convertUnixEpochSecondsToDays
arg daysCall unixEpochSeconds oneFullDaySeconds
run daysCall
bind daysResult CSignedInt64 daysCall
call checkDaysCall math.equalI64
arg checkDaysCall left daysResult
arg checkDaysCall right oneDayCount
run checkDaysCall
bind daysOk Bool checkDaysCall
branchIf daysOk daysHolds
branch smokeAssertionFailed
label daysHolds

# convertSecondsToWholeHours(0) == 0
call hoursZeroCall convertSecondsToWholeHours
arg hoursZeroCall secondCount zeroSecondsValue
run hoursZeroCall
bind hoursZeroResult CSignedInt64 hoursZeroCall
call checkHoursZeroCall math.equalI64
arg checkHoursZeroCall left hoursZeroResult
arg checkHoursZeroCall right zeroSecondsValue
run checkHoursZeroCall
bind hoursZeroOk Bool checkHoursZeroCall
branchIf hoursZeroOk hoursZeroHolds
branch smokeAssertionFailed
label hoursZeroHolds

# isGregorianLeapYear(2023) == false (typical non-leap)
call leap2023Call isGregorianLeapYear
arg leap2023Call candidateYear yearTwentyTwentyThree
run leap2023Call
bind leap2023Result Bool leap2023Call
branchIf leap2023Result smokeAssertionFailed
branch leap2023Holds
label leap2023Holds

# isGregorianLeapYear(2400) == true (divisible by 400, the century leap rule)
call leap2400Call isGregorianLeapYear
arg leap2400Call candidateYear yearTwoFourHundred
run leap2400Call
bind leap2400Result Bool leap2400Call
branchIf leap2400Result leap2400Holds
branch smokeAssertionFailed
label leap2400Holds

# Exercise the OS-time wrappers. We don't assert their values
# (non-deterministic across runs), but we DO branchIf on each
# returned value so the bind is "used" — the linter would otherwise
# flag the bind as dead. Either branch lands at the same label.
call exerciseCpuClockCall readProcessCpuClockTicks
run exerciseCpuClockCall
bind cpuClockTicksObserved CSignedInt64 exerciseCpuClockCall
branchIf cpuClockTicksObserved cpuClockExercised
branch cpuClockExercised
label cpuClockExercised

call exerciseUnixTimeCall readCurrentUnixEpochSeconds
run exerciseUnixTimeCall
bind unixEpochSecondsObserved CSignedInt64 exerciseUnixTimeCall
branchIf unixEpochSecondsObserved unixTimeExercised
branch unixTimeExercised
label unixTimeExercised

const successMessageText CNullTerminatedByteString "OK"
call writeSuccessLineCall console.writeLine
arg writeSuccessLineCall console console
arg writeSuccessLineCall text successMessageText
run writeSuccessLineCall
ignoreOk writeSuccessLineCall CSignedInt32
bindError consoleWriteResultError CSignedInt32 writeSuccessLineCall
branchIfError writeSuccessLineCall consoleWriteFailedHandler
const exitOkCode ExitCode 0
returnOk exitOkCode

# Failure leg: surface the raw negative CSignedInt32 from
# console.writeLine as the cause attached to the typed
# MainError.ConsoleWriteFailed variant.
label consoleWriteFailedHandler
makeError consoleWriteFailedFailure MainError.ConsoleWriteFailed consoleWriteResultError
returnError consoleWriteFailedFailure
label smokeAssertionFailed
makeError timeSmokeFailure MainError.TimeSmokeAssertionFailed
returnError timeSmokeFailure
