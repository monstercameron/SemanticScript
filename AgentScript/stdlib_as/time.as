project StdTimeSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <time.h>-style time ops.
#
# This file adds the OS-time floor primitives (c.clock and c.time) and
# builds pure-AS conversion helpers on top.
#
# Operations:
#   currentClock              - CPU clock ticks since process start.
#   currentEpochSeconds       - seconds since the Unix epoch.
#   secondsToHours(s)         - s / 3600 (integer).
#   secondsToMinutes(s)       - s / 60 (integer).
#   minutesToSeconds(m)       - m * 60.
#   hoursToSeconds(h)         - h * 3600.
#   daysSinceEpoch(s)         - s / 86400.
#   isLeapYear(y)             - 1 if y is a Gregorian leap year, else 0.
# ============================================================


operation currentClock
output currentClock Result CSignedInt64 Void
effect currentClock read clock.cpu
memory currentClock heap no
async currentClock no
purpose currentClock "Wraps c.clock as the only OS-time primitive at this layer. Returns CPU clock ticks since the start of this process (CLOCKS_PER_SEC defines the divisor)."

label startCurrentClock
call libcCall c.clock
run libcCall
bind ticks CSignedInt64 libcCall
returnOk ticks


operation currentEpochSeconds
output currentEpochSeconds Result CSignedInt64 Void
effect currentEpochSeconds read clock.cpu
memory currentEpochSeconds heap no
async currentEpochSeconds no
purpose currentEpochSeconds "Wraps c.time with a NULL out-param. Returns seconds since 1970-01-01 00:00:00 UTC."

label startCurrentEpochSeconds
# Allocate a single 8-byte slot to satisfy the time_t* parameter shape
# without requiring caller storage. We then ignore the indirect write.
const eightBytes CByteCount 8
call allocSlot c.malloc
arg allocSlot size eightBytes
run allocSlot
bind slot COpaqueMemoryAddress allocSlot

call timeCall c.time
arg timeCall slot slot
run timeCall
bind seconds CSignedInt64 timeCall

call freeSlot c.free
arg freeSlot ptr slot
run freeSlot

returnOk seconds


operation secondsToHours
input secondsToHours s CSignedInt64
output secondsToHours Result CSignedInt64 Void
memory secondsToHours heap no
async secondsToHours no
purpose secondsToHours "Floor-divide seconds by 3600 to get whole hours."
label startSecondsToHours
const threeSixHundred CSignedInt64 3600
call divCall math.divideI64
arg divCall left s
arg divCall right threeSixHundred
run divCall
bind hours CSignedInt64 divCall
returnOk hours


operation secondsToMinutes
input secondsToMinutes s CSignedInt64
output secondsToMinutes Result CSignedInt64 Void
memory secondsToMinutes heap no
async secondsToMinutes no
purpose secondsToMinutes "s / 60."
label startSecondsToMinutes
const sixty CSignedInt64 60
call divCall math.divideI64
arg divCall left s
arg divCall right sixty
run divCall
bind minutes CSignedInt64 divCall
returnOk minutes


operation minutesToSeconds
input minutesToSeconds m CSignedInt64
output minutesToSeconds Result CSignedInt64 Void
memory minutesToSeconds heap no
async minutesToSeconds no
purpose minutesToSeconds "m * 60."
label startMinutesToSeconds
const sixty CSignedInt64 60
call mulCall math.multiplyI64
arg mulCall left m
arg mulCall right sixty
run mulCall
bind seconds CSignedInt64 mulCall
returnOk seconds


operation hoursToSeconds
input hoursToSeconds h CSignedInt64
output hoursToSeconds Result CSignedInt64 Void
memory hoursToSeconds heap no
async hoursToSeconds no
purpose hoursToSeconds "h * 3600."
label startHoursToSeconds
const thirtySixHundred CSignedInt64 3600
call mulCall math.multiplyI64
arg mulCall left h
arg mulCall right thirtySixHundred
run mulCall
bind seconds CSignedInt64 mulCall
returnOk seconds


operation daysSinceEpoch
input daysSinceEpoch s CSignedInt64
output daysSinceEpoch Result CSignedInt64 Void
memory daysSinceEpoch heap no
async daysSinceEpoch no
purpose daysSinceEpoch "Whole days since 1970-01-01 from a seconds-since-epoch value."
label startDaysSinceEpoch
const secondsPerDay CSignedInt64 86400
call divCall math.divideI64
arg divCall left s
arg divCall right secondsPerDay
run divCall
bind days CSignedInt64 divCall
returnOk days


operation isLeapYear
input isLeapYear y CSignedInt64
output isLeapYear Result CSignedInt32 Void
memory isLeapYear heap no
async isLeapYear no
purpose isLeapYear "Gregorian leap-year rule: divisible by 4, AND (not divisible by 100 OR divisible by 400)."

label startIsLeapYear
const zeroL I64 0
const fourL CSignedInt64 4
const hundredL CSignedInt64 100
const fourHundredL CSignedInt64 400
const trueL CSignedInt32 1
const falseL CSignedInt32 0

# y % 4 != 0 -> not leap.
call mod4 math.moduloI64
arg mod4 left y
arg mod4 right fourL
run mod4
bind mod4Val I64 mod4
call neZero math.notEqualI64
arg neZero left mod4Val
arg neZero right zeroL
run neZero
bind notDivBy4 Bool neZero
branchIf notDivBy4 leapFalse

# y % 400 == 0 -> leap.
call mod400 math.moduloI64
arg mod400 left y
arg mod400 right fourHundredL
run mod400
bind mod400Val I64 mod400
call eq400 math.equalI64
arg eq400 left mod400Val
arg eq400 right zeroL
run eq400
bind divBy400 Bool eq400
branchIf divBy400 leapTrue

# y % 100 == 0 -> not leap.
call mod100 math.moduloI64
arg mod100 left y
arg mod100 right hundredL
run mod100
bind mod100Val I64 mod100
call eq100 math.equalI64
arg eq100 left mod100Val
arg eq100 right zeroL
run eq100
bind divBy100 Bool eq100
branchIf divBy100 leapFalse

# Else (divisible by 4 but not 100): leap.
branch leapTrue

label leapTrue
returnOk trueL
label leapFalse
returnOk falseL


# ============================================================
# Smoke test (deterministic checks only — no real time involved).
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
effect main allocate heap
memory main heap yes
async main no
purpose main "Smoke-test the deterministic time helpers (conversions and isLeapYear). The OS-time wrappers are exercised but their values aren't checked since they're non-deterministic."

label startMain

# secondsToHours(3661) == 1
const sec3661 CSignedInt64 3661
const oneHour CSignedInt64 1
call h1 secondsToHours
arg h1 s sec3661
run h1
bindOk h1Res CSignedInt64 h1
call h1Check math.equalI64
arg h1Check left h1Res
arg h1Check right oneHour
run h1Check
bind h1Ok Bool h1Check
branchIf h1Ok h1OkLabel
branch testFailed
label h1OkLabel

# hoursToSeconds(2) == 7200
const twoHours CSignedInt64 2
const sec7200 CSignedInt64 7200
call hs1 hoursToSeconds
arg hs1 h twoHours
run hs1
bindOk hs1Res CSignedInt64 hs1
call hs1Check math.equalI64
arg hs1Check left hs1Res
arg hs1Check right sec7200
run hs1Check
bind hs1Ok Bool hs1Check
branchIf hs1Ok hs1OkLabel
branch testFailed
label hs1OkLabel

# isLeapYear(2000) == 1
const y2000 CSignedInt64 2000
const trueChk CSignedInt32 1
const falseChk CSignedInt32 0
call ly1 isLeapYear
arg ly1 y y2000
run ly1
bindOk ly1Res CSignedInt32 ly1
call ly1Check math.equalI64
arg ly1Check left ly1Res
arg ly1Check right trueChk
run ly1Check
bind ly1Ok Bool ly1Check
branchIf ly1Ok ly1OkLabel
branch testFailed
label ly1OkLabel

# isLeapYear(1900) == 0
const y1900 CSignedInt64 1900
call ly2 isLeapYear
arg ly2 y y1900
run ly2
bindOk ly2Res CSignedInt32 ly2
call ly2Check math.equalI64
arg ly2Check left ly2Res
arg ly2Check right falseChk
run ly2Check
bind ly2Ok Bool ly2Check
branchIf ly2Ok ly2OkLabel
branch testFailed
label ly2OkLabel

# isLeapYear(2024) == 1
const y2024 CSignedInt64 2024
call ly3 isLeapYear
arg ly3 y y2024
run ly3
bindOk ly3Res CSignedInt32 ly3
call ly3Check math.equalI64
arg ly3Check left ly3Res
arg ly3Check right trueChk
run ly3Check
bind ly3Ok Bool ly3Check
branchIf ly3Ok ly3OkLabel
branch testFailed
label ly3OkLabel

# Exercise the OS-time wrappers (no value check — just that they
# return without error).
call c1 currentClock
run c1
bindOk c1Res CSignedInt64 c1

call ts1 currentEpochSeconds
run ts1
bindOk ts1Res CSignedInt64 ts1

const charO CSignedInt32 79
const charK CSignedInt32 75
const charNl CSignedInt32 10
call putO c.putchar
arg putO c charO
run putO
call putK c.putchar
arg putK c charK
run putK
call putNl c.putchar
arg putNl c charNl
run putNl

const exitOk ExitCode 0
returnOk exitOk

label testFailed
const exitFail CSignedInt32 1
makeError testFailure MainError.TestFailed exitFail
returnError testFailure
