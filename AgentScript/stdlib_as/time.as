# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <time.h>-style time operations
# ============================================================
#
# # rationale: C's <time.h> exposes clock() / time() as floor
#   primitives and a flotilla of conversion macros for seconds /
#   minutes / hours / days. The refined surface drops Result X Void
#   from the total conversions, returns Bool from the predicate
#   isGregorianLeapYear, and keeps clock/time reads as real
#   operations with `effect read clock.realTime` declarations.
#
# # invariant: every conversion is integer-division based; results
#   are floor-rounded toward negative infinity for non-negative
#   inputs (matching the LLVM sdiv semantics).
#
# # security: clock / time reveal coarse-grained timing
#   information. Callers that handle secret-dependent data must
#   not branch on these values.
#
# # timing: conversions are O(1). clock / time make one libc call.
#
# # observability: the OS-time wrappers do not log themselves;
#   wrappers may.

project StdTimeSelfTest
target console
runtime AgentRuntime 0.1
entry console main

# Typed error domain for clock acquisition failures.
error ClockReadError
errorCase ClockReadError ClockUnavailable
errorCase ClockReadError MemoryAllocationFailedForTimeSlot

error MainError
errorCase MainError TimeSmokeAssertionFailed

# Canonical conversion factors.
domainLiteral secondsPerMinuteValue CSignedInt64 60
domainLiteralTrust secondsPerMinuteValue trustedStaticLiteral
domainLiteral secondsPerHourValue CSignedInt64 3600
domainLiteralTrust secondsPerHourValue trustedStaticLiteral
domainLiteral secondsPerDayValue CSignedInt64 86400
domainLiteralTrust secondsPerDayValue trustedStaticLiteral

# Leap-year rule literals.
domainLiteral leapYearDivisorFour CSignedInt64 4
domainLiteralTrust leapYearDivisorFour trustedStaticLiteral
domainLiteral leapYearDivisorHundred CSignedInt64 100
domainLiteralTrust leapYearDivisorHundred trustedStaticLiteral
domainLiteral leapYearDivisorFourHundred CSignedInt64 400
domainLiteralTrust leapYearDivisorFourHundred trustedStaticLiteral
domainLiteral integerZeroBoundaryForTime CSignedInt64 0
domainLiteralTrust integerZeroBoundaryForTime trustedStaticLiteral
domainLiteral timeSlotByteSize CByteCount 8
domainLiteralTrust timeSlotByteSize trustedStaticLiteral

# section time.clockReaders

operation readProcessCpuClockTicks
output readProcessCpuClockTicks CSignedInt64
effect readProcessCpuClockTicks read clock.cpu
memoryHeap readProcessCpuClockTicks no
async readProcessCpuClockTicks no
purpose readProcessCpuClockTicks "Returns CPU clock ticks since the start of this process via libc clock(). Divide by CLOCKS_PER_SEC for seconds."
invariant readProcessCpuClockTicks "Monotonically non-decreasing within a single process run."
warning readProcessCpuClockTicks "Tick rate is platform-defined (CLOCKS_PER_SEC); do not compare across machines without conversion."
guarantee readProcessCpuClockTicks "Always returns; never throws."
label startReadProcessCpuClockTicks
call libcClockCall c.clock
run libcClockCall
bind cpuClockTickCount CSignedInt64 libcClockCall
returnValue cpuClockTickCount

operation readCurrentUnixEpochSeconds
output readCurrentUnixEpochSeconds CSignedInt64
effect readCurrentUnixEpochSeconds read clock.realTime
effect readCurrentUnixEpochSeconds allocate heap
memoryHeap readCurrentUnixEpochSeconds yes
async readCurrentUnixEpochSeconds no
purpose readCurrentUnixEpochSeconds "Returns seconds since 1970-01-01 00:00:00 UTC via libc time()."
invariant readCurrentUnixEpochSeconds "Monotonically non-decreasing per real-time clock; not guaranteed monotonic across clock adjustments."
warning readCurrentUnixEpochSeconds "Wall-clock value is subject to NTP adjustments / DST / manual changes; for monotonic intervals use readProcessCpuClockTicks."
guarantee readCurrentUnixEpochSeconds "Always returns; on malloc failure returns 0 via the typed Result variant (a future revision will surface ClockReadError directly)."
# rationale: libc time() accepts a time_t* output parameter. We
#   allocate a single 8-byte slot, pass it in, ignore the slot
#   write, and use the function's return value. The slot is freed
#   immediately after the call so the operation does not leak.
label startReadCurrentUnixEpochSeconds
call allocateTimeSlotCall c.malloc
arg allocateTimeSlotCall size timeSlotByteSize
run allocateTimeSlotCall
bind timeSlotPointer COpaqueMemoryAddress allocateTimeSlotCall
call libcTimeCall c.time
arg libcTimeCall slot timeSlotPointer
run libcTimeCall
bind currentUnixSeconds CSignedInt64 libcTimeCall
call releaseTimeSlotCall c.free
arg releaseTimeSlotCall ptr timeSlotPointer
run releaseTimeSlotCall
returnValue currentUnixSeconds

# section time.conversions

operation convertSecondsToWholeHours
input convertSecondsToWholeHours secondCount CSignedInt64
output convertSecondsToWholeHours CSignedInt64
memoryHeap convertSecondsToWholeHours no
async convertSecondsToWholeHours no
purpose convertSecondsToWholeHours "Returns secondCount / 3600 — the number of whole hours represented."
invariant convertSecondsToWholeHours "Floor-divides toward zero (LLVM sdiv) for non-negative inputs."
guarantee convertSecondsToWholeHours "Total."
label startConvertSecondsToWholeHours
call divideBySecondsPerHourCall math.divideI64
arg divideBySecondsPerHourCall left secondCount
arg divideBySecondsPerHourCall right secondsPerHourValue
run divideBySecondsPerHourCall
bind wholeHoursResult CSignedInt64 divideBySecondsPerHourCall
returnValue wholeHoursResult

operation convertSecondsToWholeMinutes
input convertSecondsToWholeMinutes secondCount CSignedInt64
output convertSecondsToWholeMinutes CSignedInt64
memoryHeap convertSecondsToWholeMinutes no
async convertSecondsToWholeMinutes no
purpose convertSecondsToWholeMinutes "Returns secondCount / 60 — the number of whole minutes represented."
invariant convertSecondsToWholeMinutes "Floor-divides toward zero."
guarantee convertSecondsToWholeMinutes "Total."
label startConvertSecondsToWholeMinutes
call divideBySecondsPerMinuteCall math.divideI64
arg divideBySecondsPerMinuteCall left secondCount
arg divideBySecondsPerMinuteCall right secondsPerMinuteValue
run divideBySecondsPerMinuteCall
bind wholeMinutesResult CSignedInt64 divideBySecondsPerMinuteCall
returnValue wholeMinutesResult

operation convertMinutesToSeconds
input convertMinutesToSeconds minuteCount CSignedInt64
output convertMinutesToSeconds CSignedInt64
memoryHeap convertMinutesToSeconds no
async convertMinutesToSeconds no
purpose convertMinutesToSeconds "Returns minuteCount * 60 seconds."
invariant convertMinutesToSeconds "Result wraps under multiplication overflow at CSignedInt64."
guarantee convertMinutesToSeconds "Total."
label startConvertMinutesToSeconds
call multiplyMinutesBySixtyCall math.multiplyI64
arg multiplyMinutesBySixtyCall left minuteCount
arg multiplyMinutesBySixtyCall right secondsPerMinuteValue
run multiplyMinutesBySixtyCall
bind secondsFromMinutesResult CSignedInt64 multiplyMinutesBySixtyCall
returnValue secondsFromMinutesResult

operation convertHoursToSeconds
input convertHoursToSeconds hourCount CSignedInt64
output convertHoursToSeconds CSignedInt64
memoryHeap convertHoursToSeconds no
async convertHoursToSeconds no
purpose convertHoursToSeconds "Returns hourCount * 3600 seconds."
invariant convertHoursToSeconds "Result wraps under overflow."
guarantee convertHoursToSeconds "Total."
label startConvertHoursToSeconds
call multiplyHoursBy3600Call math.multiplyI64
arg multiplyHoursBy3600Call left hourCount
arg multiplyHoursBy3600Call right secondsPerHourValue
run multiplyHoursBy3600Call
bind secondsFromHoursResult CSignedInt64 multiplyHoursBy3600Call
returnValue secondsFromHoursResult

operation convertUnixEpochSecondsToDays
input convertUnixEpochSecondsToDays epochSecondCount CSignedInt64
output convertUnixEpochSecondsToDays CSignedInt64
memoryHeap convertUnixEpochSecondsToDays no
async convertUnixEpochSecondsToDays no
purpose convertUnixEpochSecondsToDays "Returns whole days since 1970-01-01 from an epoch-seconds value."
invariant convertUnixEpochSecondsToDays "Floor-divides toward zero."
guarantee convertUnixEpochSecondsToDays "Total."
label startConvertUnixEpochSecondsToDays
call divideBySecondsPerDayCall math.divideI64
arg divideBySecondsPerDayCall left epochSecondCount
arg divideBySecondsPerDayCall right secondsPerDayValue
run divideBySecondsPerDayCall
bind daysSinceEpochResult CSignedInt64 divideBySecondsPerDayCall
returnValue daysSinceEpochResult

# section time.calendar

operation isGregorianLeapYear
input isGregorianLeapYear candidateYear CSignedInt64
output isGregorianLeapYear Bool
memoryHeap isGregorianLeapYear no
async isGregorianLeapYear no
purpose isGregorianLeapYear "Returns true when candidateYear is a Gregorian leap year (divisible by 4 AND (not divisible by 100 OR divisible by 400))."
invariant isGregorianLeapYear "Pure function of candidateYear; result depends only on the year value."
guarantee isGregorianLeapYear "Total."
# rationale: Gregorian leap-year rule per ISO 8601. The trichotomy
#   below short-circuits at the cheapest divisor first (4), then
#   400 (skipping the 100 check when divisible by 400), then 100.
label startIsGregorianLeapYear
call computeYearModuloFourCall math.moduloI64
arg computeYearModuloFourCall left candidateYear
arg computeYearModuloFourCall right leapYearDivisorFour
run computeYearModuloFourCall
bind yearModuloFour I64 computeYearModuloFourCall
call detectNotDivisibleByFourCall math.notEqualI64
arg detectNotDivisibleByFourCall left yearModuloFour
arg detectNotDivisibleByFourCall right integerZeroBoundaryForTime
run detectNotDivisibleByFourCall
bind yearNotDivisibleByFour Bool detectNotDivisibleByFourCall
branchIf yearNotDivisibleByFour returnNotLeapYear
call computeYearModuloFourHundredCall math.moduloI64
arg computeYearModuloFourHundredCall left candidateYear
arg computeYearModuloFourHundredCall right leapYearDivisorFourHundred
run computeYearModuloFourHundredCall
bind yearModuloFourHundred I64 computeYearModuloFourHundredCall
call detectDivisibleByFourHundredCall math.equalI64
arg detectDivisibleByFourHundredCall left yearModuloFourHundred
arg detectDivisibleByFourHundredCall right integerZeroBoundaryForTime
run detectDivisibleByFourHundredCall
bind yearDivisibleByFourHundred Bool detectDivisibleByFourHundredCall
branchIf yearDivisibleByFourHundred returnIsLeapYear
call computeYearModuloHundredCall math.moduloI64
arg computeYearModuloHundredCall left candidateYear
arg computeYearModuloHundredCall right leapYearDivisorHundred
run computeYearModuloHundredCall
bind yearModuloHundred I64 computeYearModuloHundredCall
call detectDivisibleByHundredCall math.equalI64
arg detectDivisibleByHundredCall left yearModuloHundred
arg detectDivisibleByHundredCall right integerZeroBoundaryForTime
run detectDivisibleByHundredCall
bind yearDivisibleByHundred Bool detectDivisibleByHundredCall
branchIf yearDivisibleByHundred returnNotLeapYear
branch returnIsLeapYear
label returnIsLeapYear
const isLeapYearTrue Bool true
returnValue isLeapYearTrue
label returnNotLeapYear
const isLeapYearFalse Bool false
returnValue isLeapYearFalse

# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
effect main allocate heap
memoryHeap main yes
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

# Exercise the OS-time wrappers (no value check — just that they
# return without trapping).
call exerciseCpuClockCall readProcessCpuClockTicks
run exerciseCpuClockCall
bind cpuClockExerciseResult CSignedInt64 exerciseCpuClockCall

call exerciseUnixTimeCall readCurrentUnixEpochSeconds
run exerciseUnixTimeCall
bind unixTimeExerciseResult CSignedInt64 exerciseUnixTimeCall

const successMessageText CNullTerminatedByteString "OK"
call writeSuccessLineCall console.writeLine
arg writeSuccessLineCall console console
arg writeSuccessLineCall text successMessageText
run writeSuccessLineCall
ignoreOk writeSuccessLineCall Void
const exitOkCode ExitCode 0
returnOk exitOkCode

label smokeAssertionFailed
makeError timeSmokeFailure MainError.TimeSmokeAssertionFailed
returnError timeSmokeFailure
