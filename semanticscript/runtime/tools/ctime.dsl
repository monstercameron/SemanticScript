module ctime "time.h for the runtime's C library: the clocks, struct tm, gmtime, localtime with the time zone as glibc finds it, mktime, asctime, ctime, and strftime, all as glibc behaves in the C locale"
  path ctime
  imports standard.machine standard.system standard.string standard.math standard.compare standard.convert standard.logic standard.test kernel heap clibrary
  exports none

capability memoryAccess "Authority to read and write the memory C callers hand the library and the module's own state" use machine.memory none

capability systemCalls "Authority to read the clocks and the time zone files, and to take memory for what they hold" use system.calls none

## Decided by delegation (D-n assigned by the coordinator). time_t is a 64-bit `long`, as on LP64 glibc, on Windows too.
## `struct tm` is glibc's x86_64 and AArch64 layout of 56 bytes: nine ints (tm_sec 0, tm_min 4, tm_hour 8, tm_mday 12,
## tm_mon 16, tm_year 20, tm_wday 24, tm_yday 28, tm_isdst 32), tm_gmtoff (a long) at 40, tm_zone (a pointer) at 48.
## gmtime and localtime give one static struct tm, ctime and asctime one static 26-byte buffer.
##
## machine.state bytes 25600 to 26623 belong to this module: 0 the static struct tm, 64 asctime's buffer, 96 `TZ`, 100
## `UTC`, 104 `GMT` (each with its 0 byte), 128 a timespec, 144 four FILETIMEs, 176 the offset mktime guessed last (as
## glibc keeps it, since it decides the answer inside a spring-forward gap), 192 the time zone (below), 448 what a
## zone gives for a time (UTC offset, isdst, the address of the abbreviation), 472 the year, month, and day
## civilFromDays gives, 504 and 560 two scratch struct tm, 616 strftime's state (616 the output's address, 624 its
## size, 632 the bytes written, 640 whether it ran out, 648 the struct tm, 656 the pad flag, 664 upper case, 672 lower
## case, 680 the width, 688 the modifier), 704 the digits of a number, 752 a byte strftime adds, 760 whether a zone is being read on Windows. Everything else is on the heap or the stack.
## The time zone, from 192: 0 the kind (0 a POSIX rule, 1 a TZif table), 8 the file's block, 16 how many transitions,
## 24 how many types, 32 the transitions, 40 their types, 48 the types' records, 56 the abbreviations, 64 whether a
## POSIX rule follows the table, 72 and 80 tzname[0] and tzname[1], 88 the bytes of a transition time (4 or 8); from 96 the rule: 0 the standard UTC offset, 8 the
## daylight one, 16 whether there is daylight time, 24 the start rule and 64 the end rule (type 0 `Mm.w.d`, 1 `Jn`, 2
## `n`; then month or day, week, weekday, seconds), 104 and 120 the two names (16 bytes each).
## The zone is read once and again only when TZ changes: byte 760 holds 1 while a zone is read on Windows, 432 holds a copy of the TZ text it was read from (the address 0
## for TZ unset), 440 whether it was read, and 424 the block of TZ's text on Windows; the file's block stays loaded, so a
## struct tm's tm_zone stays valid.
constant stateBase "Where this module's bytes begin in machine.state" Int64 25600

constant zoneAt "Where the time zone is kept, from the module's base" Int64 192

constant overflowError "EOVERFLOW: a time whose year does not fit an int" Int32 75

constant rangeError "ERANGE: strftime's buffer is too small" Int32 34

constant forever "The bound of a loop over text that ends at its 0 byte" Int64 9223372036854775807

## ---------------------------------------------------------------- small pieces

op workspace "The module's bytes of machine.state"
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  base = kernel.stateAt(stateBase)
  return base

op fetch "The byte at an address moved on by an offset, as a whole number"
  input base machine.Address copied
  input at Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  value = clibrary.byteAt(base, at)
  wide = convert.byteToInt64(value)
  return wide

op floorDivide "A quotient rounded toward minus infinity"
  input numerator Int64 copied
  input divisor Int64 copied
  output Int64
  let quotient Int64 0 mut
:begin
  calc quotient := numerator / divisor
  calc remainder = numerator % divisor
  calc lower = (remainder < 0 && divisor > 0) || (remainder > 0 && divisor < 0)
  when lower down done
:down
  calc quotient := quotient - 1
  goto done
:done
  return quotient

op floorModulo "A remainder with the sign of the divisor"
  input numerator Int64 copied
  input divisor Int64 copied
  output Int64
  let remainder Int64 0 mut
:begin
  calc remainder := numerator % divisor
  calc lower = (remainder < 0 && divisor > 0) || (remainder > 0 && divisor < 0)
  when lower up done
:up
  calc remainder := remainder + divisor
  goto done
:done
  return remainder

op isLeapYear "Whether a year of the Gregorian calendar (the full year, 2000 for 2000) is a leap year"
  input year Int64 copied
  output Bool
:begin
  calc leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)
  return leap

op monthLength "The days of a month (1 to 12) of a year"
  input year Int64 copied
  input month Int64 copied
  output Int64
  let days Int64 31 mut
:begin
  when month == 2 february other
:february
  leap = isLeapYear(year)
  when leap leapYear plainYear
:leapYear
  calc days := 29
  goto done
:plainYear
  calc days := 28
  goto done
:other
  calc short = month == 4 || month == 6 || month == 9 || month == 11
  when short thirty done
:thirty
  calc days := 30
  goto done
:done
  return days

op daysFromCivil "The days from 1970-01-01 to a day of the Gregorian calendar (the month 1 to 12): Howard Hinnant's days_from_civil, public domain"
  input year Int64 copied
  input month Int64 copied
  input day Int64 copied
  output Int64
  let shifted Int64 0 mut
  let counted Int64 0 mut
:begin
  calc shifted := year
  when month <= 2 early late
:early
  calc shifted := year - 1
  calc counted := month + 9
  goto join
:late
  calc counted := month - 3
  goto join
:join
  era = floorDivide(shifted, 400)
  calc yearOfEra = shifted - era * 400
  calc dayOfYear = (153 * counted + 2) / 5 + day - 1
  calc dayOfEra = yearOfEra * 365 + yearOfEra / 4 - yearOfEra / 100 + dayOfYear
  calc days = era * 146097 + dayOfEra - 719468
  return days

op civilFromDays "The year, month (1 to 12), and day of a day counted from 1970-01-01, stored as three longs at an address (Hinnant's civil_from_days, public domain)"
  input days Int64 copied
  input out machine.Address copied
  effect use machine.memory
  uses memoryAccess
  let month Int64 0 mut
  let year Int64 0 mut
:begin
  calc shifted = days + 719468
  era = floorDivide(shifted, 146097)
  calc dayOfEra = shifted - era * 146097
  calc yearOfEra = (dayOfEra - dayOfEra / 1460 + dayOfEra / 36524 - dayOfEra / 146096) / 365
  calc dayOfYear = dayOfEra - (365 * yearOfEra + yearOfEra / 4 - yearOfEra / 100)
  calc monthIndex = (5 * dayOfYear + 2) / 153
  calc day = dayOfYear - (153 * monthIndex + 2) / 5 + 1
  calc year := yearOfEra + era * 400
  when monthIndex < 10 spring autumn
:spring
  calc month := monthIndex + 3
  goto join
:autumn
  calc month := monthIndex - 9
  goto join
:join
  when month <= 2 nextYear store
:nextYear
  calc year := year + 1
  goto store
:store
  machine.storeInt64(out, year)
  machine.storeInt64(out + 8, month)
  machine.storeInt64(out + 16, day)
  return

op bigEndian32 "Four bytes at an offset, most significant first, as an unsigned whole number"
  input base machine.Address copied
  input at Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  first = fetch(base, at)
  second = fetch(base, at + 1)
  third = fetch(base, at + 2)
  fourth = fetch(base, at + 3)
  calc value = ((first * 256 + second) * 256 + third) * 256 + fourth
  return value

op signed32 "A number below 2^32 read as a signed 32-bit number"
  input value Int64 copied
  output Int64
  let result Int64 0 mut
:begin
  calc result := value
  when value >= 2147483648 negative done
:negative
  calc result := value - 4294967296
  goto done
:done
  return result

op bigEndian64 "Eight bytes at an offset, most significant first, as a signed whole number"
  input base machine.Address copied
  input at Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  high = bigEndian32(base, at)
  low = bigEndian32(base, at + 4)
  signedHigh = signed32(high)
  calc value = signedHigh * 4294967296 + low
  return value

## ---------------------------------------------------------------- the clocks

op readWall "Store the real-time clock's seconds since 1970 and nanoseconds as two longs at an address"
  input out machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  onLinux = system.linux()
  when onLinux linux windows
:linux
  system.clockGettime(0, out)
  return
:windows
  space = workspace()
  system.getSystemTimeAsFileTime(space + 144)
  ticks = machine.loadInt64(space + 144)
  calc seconds = ticks / 10000000 - 11644473600
  calc nanoseconds = ticks % 10000000 * 100
  machine.storeInt64(out, seconds)
  machine.storeInt64(out + 8, nanoseconds)
  return

op wallTime "time: the seconds since 1970-01-01 00:00:00 UTC, also stored where the argument points unless it is NULL"
  input result machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "time"
:begin
  space = workspace()
  readWall(space + 128)
  seconds = machine.loadInt64(space + 128)
  nowhere = machine.zero()
  when result == nowhere finish store
:store
  machine.storeInt64(result, seconds)
  goto finish
:finish
  return seconds

op processorTime "clock: the processor time the process has used, in millionths of a second (CLOCKS_PER_SEC is 1000000): CLOCK_PROCESS_CPUTIME_ID on Linux, the kernel and user times of GetProcessTimes on Windows"
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "clock"
:begin
  space = workspace()
  onLinux = system.linux()
  when onLinux linux windows
:linux
  system.clockGettime(2, space + 128)
  seconds = machine.loadInt64(space + 128)
  nanoseconds = machine.loadInt64(space + 136)
  calc micro = seconds * 1000000 + nanoseconds / 1000
  return micro
:windows
  process = system.getCurrentProcess()
  system.getProcessTimes(process, space + 144, space + 152, space + 160, space + 168)
  kernelTicks = machine.loadInt64(space + 160)
  userTicks = machine.loadInt64(space + 168)
  calc windowsMicro = (kernelTicks + userTicks) / 10
  return windowsMicro

op timeSpecification "timespec_get: the real-time clock's seconds and nanoseconds stored in a timespec for TIME_UTC (1), which it gives; 0 for any other base"
  input spec machine.Address copied
  input base Int32 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "timespec_get"
:begin
  when base == 1 utc other
:utc
  readWall(spec)
  return 1
:other
  return 0

op timeDifference "difftime: the seconds from the second time to the first, as a double"
  input later Int64 copied
  input earlier Int64 copied
  output Float64
  abi library "difftime"
:begin
  calc difference = convert.int64ToFloat64(later) - convert.int64ToFloat64(earlier)
  return difference

## ---------------------------------------------------------------- struct tm

op breakDown "Fill a struct tm's nine ints from a time and a UTC offset (seconds, days, and the calendar of the Gregorian rules, extended to every year); 1, or 0 with EOVERFLOW when the year does not fit tm_year"
  input t Int64 copied
  input offset Int64 copied
  input tm machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  when t > 4611686018427387904 overflow lowCheck
:lowCheck
  when t < -4611686018427387904 overflow convert
:overflow
  clibrary.setErrno(overflowError)
  return 0
:convert
  space = workspace()
  calc local = t + offset
  days = floorDivide(local, 86400)
  calc rest = local - days * 86400
  weekday = floorModulo(days + 4, 7)
  civilFromDays(days, space + 472)
  year = machine.loadInt64(space + 472)
  month = machine.loadInt64(space + 480)
  day = machine.loadInt64(space + 488)
  calc yearField = year - 1900
  calc tooLow = yearField < -2147483648
  calc tooHigh = yearField > 2147483647
  calc outside = tooLow || tooHigh
  when outside overflow store
:store
  yearStart = daysFromCivil(year, 1, 1)
  machine.storeInt32(tm, convert.int64ToInt32(rest % 60))
  machine.storeInt32(tm + 4, convert.int64ToInt32(rest % 3600 / 60))
  machine.storeInt32(tm + 8, convert.int64ToInt32(rest / 3600))
  machine.storeInt32(tm + 12, convert.int64ToInt32(day))
  machine.storeInt32(tm + 16, convert.int64ToInt32(month - 1))
  machine.storeInt32(tm + 20, convert.int64ToInt32(yearField))
  machine.storeInt32(tm + 24, convert.int64ToInt32(weekday))
  machine.storeInt32(tm + 28, convert.int64ToInt32(days - yearStart))
  return 1

op gmtimeInto "Break a time down in UTC into a struct tm (isdst 0, gmtoff 0, the zone `GMT`); the struct tm, or the address 0 with EOVERFLOW"
  invariant breaksDownUtc "Gives the struct tm of the time in UTC, or the address 0 when the year does not fit an int"
  input t Int64 copied
  input tm machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  nowhere = machine.zero()
  done = breakDown(t, 0, tm)
  when done == 0 failed good
:failed
  return nowhere
:good
  space = workspace()
  machine.storeInt32(tm + 32, 0)
  machine.storeInt64(tm + 40, 0)
  machine.storeInt32(space + 104, 5524807)
  machine.storeAddress(tm + 48, space + 104)
  return tm

op gmtimeStatic "gmtime: a time broken down in UTC into the one static struct tm"
  input timer machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "gmtime"
:begin
  space = workspace()
  t = machine.loadInt64(timer)
  result = gmtimeInto(t, space)
  return result

op gmtimeResult "gmtime_r: a time broken down in UTC into the caller's struct tm"
  input timer machine.Address copied
  input result machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "gmtime_r"
:begin
  t = machine.loadInt64(timer)
  broken = gmtimeInto(t, result)
  return broken

## ---------------------------------------------------------------- POSIX time zone strings

op parseNumber "Read the decimal digits at an offset of a C string into a long at an address (a value past 10^9 stays near it); the offset after them, or -1 when there is no digit"
  input s machine.Address copied
  input at Int64 copied
  input cell machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let position Int64 0 mut
  let value Int64 0 mut
:begin
  calc position := at
  goto each
:each loop=while max=forever
  c = fetch(s, position)
  calc digit = c >= 48 && c <= 57
  when digit take finish
:take in=each
  when value < 100000000 grow next
:grow in=each
  calc value := value * 10 + c - 48
  goto next
:next in=each
  calc position := position + 1
  goto each
:finish
  machine.storeInt64(cell, value)
  when position == at absent present
:absent
  return -1
:present
  return position

op parseName "Read a zone name at an offset of a C string, three or more letters or `<` and `>` around letters, digits, plus, and minus; its first 15 bytes and a 0 go to an address; the offset after it, or -1"
  input s machine.Address copied
  input at Int64 copied
  input dest machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let position Int64 0 mut
  let start Int64 0 mut
  let length Int64 0 mut
  let after Int64 0 mut
  let kept Int64 0 mut
:begin
  first = fetch(s, at)
  when first == 60 quoted plain
:quoted
  calc start := at + 1
  calc position := at + 1
  goto quotedEach
:quotedEach loop=while max=forever
  c = fetch(s, position)
  calc ok = (c >= 48 && c <= 57) || (c >= 65 && c <= 90) || (c >= 97 && c <= 122) || c == 43 || c == 45
  when ok quotedNext quotedEnd
:quotedNext in=quotedEach
  calc position := position + 1
  goto quotedEach
:quotedEnd
  closing = fetch(s, position)
  when closing == 62 quotedClose bad
:quotedClose
  calc length := position - start
  calc after := position + 1
  goto measured
:plain
  calc start := at
  calc position := at
  goto plainEach
:plainEach loop=while max=forever
  letter = fetch(s, position)
  calc isLetter = (letter >= 65 && letter <= 90) || (letter >= 97 && letter <= 122)
  when isLetter plainNext plainEnd
:plainNext in=plainEach
  calc position := position + 1
  goto plainEach
:plainEnd
  calc length := position - start
  calc after := position
  goto measured
:measured
  when length < 3 bad copy
:copy
  calc kept := length
  when length > 15 shorten place
:shorten
  calc kept := 15
  goto place
:place
  machine.copy(dest, s + start, kept)
  machine.storeByte(dest + kept, 0)
  return after
:bad
  return -1

op parseOffset "Read [+-]hh[:mm[:ss]] at an offset of a C string as seconds, signed as written, into a long at an address; the offset after it, or -1 when there is no digit"
  input s machine.Address copied
  input at Int64 copied
  input cell machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let position Int64 0 mut
  let sign Int64 1 mut
  let total Int64 0 mut
:begin
  c = fetch(s, at)
  calc position := at
  when c == 45 minus plusCheck
:minus
  calc sign := -1
  calc position := at + 1
  goto hours
:plusCheck
  when c == 43 plus hours
:plus
  calc position := at + 1
  goto hours
:hours
  afterHours = parseNumber(s, position, cell)
  when afterHours < 0 bad hoursRead
:hoursRead
  hh = machine.loadInt64(cell)
  calc total := hh * 3600
  calc position := afterHours
  colon = fetch(s, position)
  when colon == 58 minutes done
:minutes
  afterMinutes = parseNumber(s, position + 1, cell)
  when afterMinutes < 0 done minutesRead
:minutesRead
  mm = machine.loadInt64(cell)
  calc total := total + mm * 60
  calc position := afterMinutes
  secondColon = fetch(s, position)
  when secondColon == 58 seconds done
:seconds
  afterSeconds = parseNumber(s, position + 1, cell)
  when afterSeconds < 0 done secondsRead
:secondsRead
  ss = machine.loadInt64(cell)
  calc total := total + ss
  calc position := afterSeconds
  goto done
:done
  machine.storeInt64(cell, sign * total)
  return position
:bad
  return -1

op parseRuleDate "Read a daylight-saving rule's date at an offset of a C string into five longs at an address (type 0 for Mm.w.d, 1 for Jn, 2 for n; then the month or day, the week, the weekday, and the seconds, 7200 unless /time follows); the offset after it, or -1"
  input s machine.Address copied
  input at Int64 copied
  input rule machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let position Int64 0 mut
:begin
  space = workspace()
  calc cell = space + 496
  c = fetch(s, at)
  when c == 77 monthRule notMonth
:monthRule
  afterMonth = parseNumber(s, at + 1, cell)
  when afterMonth < 0 bad monthRead
:monthRead
  month = machine.loadInt64(cell)
  dotOne = fetch(s, afterMonth)
  when dotOne == 46 weekPart bad
:weekPart
  afterWeek = parseNumber(s, afterMonth + 1, cell)
  when afterWeek < 0 bad weekRead
:weekRead
  week = machine.loadInt64(cell)
  dotTwo = fetch(s, afterWeek)
  when dotTwo == 46 dayPart bad
:dayPart
  afterDay = parseNumber(s, afterWeek + 1, cell)
  when afterDay < 0 bad dayRead
:dayRead
  day = machine.loadInt64(cell)
  calc valid = month >= 1 && month <= 12 && week >= 1 && week <= 5 && day >= 0 && day <= 6
  when valid storeMonth bad
:storeMonth
  machine.storeInt64(rule, 0)
  machine.storeInt64(rule + 8, month)
  machine.storeInt64(rule + 16, week)
  machine.storeInt64(rule + 24, day)
  calc position := afterDay
  goto timePart
:notMonth
  when c == 74 julian plainDay
:julian
  afterJulian = parseNumber(s, at + 1, cell)
  when afterJulian < 0 bad julianRead
:julianRead
  julianDay = machine.loadInt64(cell)
  calc julianValid = julianDay >= 1 && julianDay <= 365
  when julianValid storeJulian bad
:storeJulian
  machine.storeInt64(rule, 1)
  machine.storeInt64(rule + 8, julianDay)
  calc position := afterJulian
  goto timePart
:plainDay
  afterPlain = parseNumber(s, at, cell)
  when afterPlain < 0 bad plainRead
:plainRead
  zeroDay = machine.loadInt64(cell)
  calc plainValid = zeroDay >= 0 && zeroDay <= 365
  when plainValid storePlain bad
:storePlain
  machine.storeInt64(rule, 2)
  machine.storeInt64(rule + 8, zeroDay)
  calc position := afterPlain
  goto timePart
:timePart
  slash = fetch(s, position)
  when slash == 47 readTime noTime
:readTime
  afterTime = parseOffset(s, position + 1, cell)
  when afterTime < 0 bad timeRead
:timeRead
  seconds = machine.loadInt64(cell)
  machine.storeInt64(rule + 32, seconds)
  return afterTime
:noTime
  machine.storeInt64(rule + 32, 7200)
  return position
:bad
  return -1

op useUtc "Make the time zone UTC: no daylight time, both names UTC"
  effect use machine.memory
  uses memoryAccess
:begin
  space = workspace()
  calc rule = space + 288
  machine.fill(rule, 0, 136)
  machine.storeInt32(rule + 104, 4412501)
  machine.storeInt32(rule + 120, 4412501)
  machine.storeInt64(space + 192, 0)
  return

op parsePosix "Read a POSIX TZ string (std offset [dst [offset] [,start[/time],end[/time]]]) into the zone's rule: 1, or 0 for one whose name is missing, which leaves the empty names and a zero offset as glibc does, and a name with no offset after it keeps its offset 0 and, on Linux, an empty daylight name (on Windows, where no file would have named the zone, the standard name); daylight time with no rules follows the United States's (M3.2.0, M11.1.0)"
  invariant readsRule "Reads the standard and daylight names, offsets, and rules of a POSIX TZ string"
  input s machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  space = workspace()
  calc rule = space + 288
  calc cell = space + 496
  machine.fill(rule, 0, 136)
  machine.storeInt64(space + 192, 0)
  afterName = parseName(s, 0, rule + 104)
  when afterName < 0 failed named
:failed
  return 0
:named
  afterStd = parseOffset(s, afterName, cell)
  when afterStd < 0 bare standardRead
:bare
  windows = machine.loadInt64(space + 760)
  when windows == 1 copyDaylightName bareDone
:copyDaylightName
  machine.copy(rule + 120, rule + 104, 16)
  return 1
:bareDone
  return 1
:standardRead
  value = machine.loadInt64(cell)
  calc standardOffset = 0 - value
  machine.storeInt64(rule, standardOffset)
  machine.storeInt64(rule + 8, standardOffset)
  more = fetch(s, afterStd)
  when more == 0 noDaylight daylightName
:noDaylight
  machine.copy(rule + 120, rule + 104, 16)
  return 1
:daylightName
  afterDaylight = parseName(s, afterStd, rule + 120)
  when afterDaylight < 0 withoutDaylight daylightOffset
:withoutDaylight
  machine.copy(rule + 120, rule + 104, 16)
  return 1
:daylightOffset
  afterDaylightOffset = parseOffset(s, afterDaylight, cell)
  when afterDaylightOffset < 0 guessOffset readOffset
:guessOffset
  calc guessedDaylight = standardOffset + 3600
  machine.storeInt64(rule + 8, guessedDaylight)
  machine.storeInt64(space + 504, afterDaylight)
  goto defaults
:readOffset
  daylightValue = machine.loadInt64(cell)
  calc daylightRead = 0 - daylightValue
  machine.storeInt64(rule + 8, daylightRead)
  machine.storeInt64(space + 504, afterDaylightOffset)
  goto defaults
:defaults
  machine.storeInt64(rule + 16, 1)
  machine.storeInt64(rule + 24, 0)
  machine.storeInt64(rule + 32, 3)
  machine.storeInt64(rule + 40, 2)
  machine.storeInt64(rule + 48, 0)
  machine.storeInt64(rule + 56, 7200)
  machine.storeInt64(rule + 64, 0)
  machine.storeInt64(rule + 72, 11)
  machine.storeInt64(rule + 80, 1)
  machine.storeInt64(rule + 88, 0)
  machine.storeInt64(rule + 96, 7200)
  resume = machine.loadInt64(space + 504)
  comma = fetch(s, resume)
  when comma == 44 startRule done
:startRule
  afterStart = parseRuleDate(s, resume + 1, rule + 24)
  when afterStart < 0 done endComma
:endComma
  secondComma = fetch(s, afterStart)
  when secondComma == 44 endRule done
:endRule
  parseRuleDate(s, afterStart + 1, rule + 64)
  goto done
:done
  return 1

## ---------------------------------------------------------------- time zone files

constant zoneDirectoryBytes "The bytes of /usr/share/zoneinfo/" Int64 20

op readWholeFile "Read a file (at most 128 KiB) into a block of the heap, its length stored at byte 184 of the module's bytes; the block, or the address 0 when it cannot be opened (Linux)"
  input path machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let total Int64 0 mut
:begin
  space = workspace()
  nowhere = machine.zero()
  descriptor = system.openat(-100, path, 0, 0)
  when descriptor < 0 failed opened
:failed
  return nowhere
:opened
  block = heap.take(131072)
  goto each
:each loop=while max=forever
  calc room = 131071 - total
  when room <= 0 finish ask
:ask in=each
  got = system.read(descriptor, block + total, room)
  when got <= 0 finish add
:add in=each
  calc total := total + got
  goto each
:finish
  system.close(descriptor)
  machine.storeInt64(space + 184, total)
  return block

op pathFor "A zone file's path in a block of the heap: a name that starts with / as it is, any other under /usr/share/zoneinfo/"
  input name machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let directory String "/usr/share/zoneinfo/"
:begin
  bytes = clibrary.cStringLength(name)
  first = fetch(name, 0)
  block = heap.take(bytes + 32)
  when first == 47 absolute relative
:absolute
  machine.copy(block, name, bytes)
  return block
:relative
  prefix = machine.addressOfString(directory)
  machine.copy(block, prefix, zoneDirectoryBytes)
  machine.copy(block + zoneDirectoryBytes, name, bytes)
  return block

op parseTable "Read a TZif file (version 1, or the 64-bit block of version 2 and later with its POSIX string footer) into the zone: 1, or 0 when the file is not one"
  invariant readsTable "Reads a TZif file into the zone: its transitions, types, names, and the footer rule"
  input buf machine.Address copied
  input bytes Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let header Int64 0 mut
  let width Int64 4 mut
  let hasRule Int64 0 mut
  let first0 Int64 0 mut
  let first1 Int64 0 mut
  let index Int64 0 mut
:begin
  space = workspace()
  calc zone = space + 192
  when bytes < 44 bad sized
:sized
  magic = bigEndian32(buf, 0)
  when magic == 1415211366 magicOk bad
:magicOk
  version = fetch(buf, 4)
  isutCount = bigEndian32(buf, 20)
  isstdCount = bigEndian32(buf, 24)
  leapCount = bigEndian32(buf, 28)
  timeCount = bigEndian32(buf, 32)
  typeCount = bigEndian32(buf, 36)
  charCount = bigEndian32(buf, 40)
  calc versionOneBytes = timeCount * 5 + typeCount * 6 + charCount + leapCount * 8 + isstdCount + isutCount
  when version >= 50 secondBlock counts
:secondBlock
  calc second = 44 + versionOneBytes
  when bytes < second + 44 bad secondRead
:secondRead
  secondMagic = bigEndian32(buf, second)
  when secondMagic == 1415211366 useSecond bad
:useSecond
  calc header := second
  calc width := 8
  goto counts
:counts
  isut = bigEndian32(buf, header + 20)
  isstd = bigEndian32(buf, header + 24)
  leaps = bigEndian32(buf, header + 28)
  times = bigEndian32(buf, header + 32)
  types = bigEndian32(buf, header + 36)
  chars = bigEndian32(buf, header + 40)
  calc transitionsAt = header + 44
  calc indicesAt = transitionsAt + times * width
  calc recordsAt = indicesAt + times
  calc namesAt = recordsAt + types * 6
  calc leapsAt = namesAt + chars
  calc endAt = leapsAt + leaps * (width + 4) + isstd + isut
  calc enough = endAt <= bytes && types >= 1 && chars >= 1
  when enough footer bad
:footer
  when width == 8 footerCheck finishTable
:footerCheck
  newline = fetch(buf, endAt)
  when newline == 10 footerFind finishTable
:footerFind
  calc footerStart = endAt + 1
  calc index := footerStart
  goto footerEach
:footerEach loop=while max=forever
  c = fetch(buf, index)
  calc notEnd = index < bytes && c != 10 && c != 0
  when notEnd footerNext footerEnd
:footerNext in=footerEach
  calc index := index + 1
  goto footerEach
:footerEnd
  machine.storeByte(buf + index, 0)
  calc footerLength = index - footerStart
  when footerLength > 0 footerParse finishTable
:footerParse
  parsed = parsePosix(buf + footerStart)
  calc hasRule := parsed
  goto finishTable
:finishTable
  machine.storeInt64(zone, 1)
  machine.storeInt64(zone + 16, times)
  machine.storeInt64(zone + 24, types)
  machine.storeAddress(zone + 32, buf + transitionsAt)
  machine.storeAddress(zone + 40, buf + indicesAt)
  machine.storeAddress(zone + 48, buf + recordsAt)
  machine.storeAddress(zone + 56, buf + namesAt)
  machine.storeInt64(zone + 64, hasRule)
  machine.storeInt64(zone + 88, width)
  calc index := times
  goto nameEach
:nameEach loop=while max=forever
  calc more = index > 0 && (first0 == 0 || first1 == 0)
  when more nameStep nameDone
:nameStep in=nameEach
  calc index := index - 1
  typeIndex = fetch(buf, indicesAt + index)
  calc record = recordsAt + typeIndex * 6
  daylight = fetch(buf, record + 4)
  nameIndex = fetch(buf, record + 5)
  calc nameAddress = namesAt + nameIndex
  when daylight == 0 standardName daylightName
:standardName in=nameEach
  when first0 == 0 setStandard nameEach
:setStandard in=nameEach
  calc first0 := nameAddress
  goto nameEach
:daylightName in=nameEach
  when first1 == 0 setDaylight nameEach
:setDaylight in=nameEach
  calc first1 := nameAddress
  goto nameEach
:nameDone
  when first0 == 0 fallback named
:fallback
  nameZero = fetch(buf, recordsAt + 5)
  calc first0 := namesAt + nameZero
  goto named
:named
  when first1 == 0 sameName store
:sameName
  calc first1 := first0
  goto store
:store
  machine.storeAddress(zone + 72, buf + first0)
  machine.storeAddress(zone + 80, buf + first1)
  return 1
:bad
  return 0

op tryFile "Read the zone from a file that TZ or the system names (Linux): 1 when the file is a TZif file"
  input name machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  space = workspace()
  path = pathFor(name)
  data = readWholeFile(path)
  heap.give(path)
  nowhere = machine.zero()
  when data == nowhere absent read
:absent
  return 0
:read
  length = machine.loadInt64(space + 184)
  parsed = parseTable(data, length)
  when parsed == 1 kept dropped
:kept
  machine.storeAddress(space + 200, data)
  return 1
:dropped
  heap.give(data)
  return 0

## ---------------------------------------------------------------- the zone at a time

op changeTime "The UTC time of a daylight-saving change in a year: the rule (five longs), the year, and the UTC offset in force before the change"
  input rule machine.Address copied
  input year Int64 copied
  input before Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let day Int64 0 mut
:begin
  kind = machine.loadInt64(rule)
  a = machine.loadInt64(rule + 8)
  week = machine.loadInt64(rule + 16)
  weekdayWanted = machine.loadInt64(rule + 24)
  seconds = machine.loadInt64(rule + 32)
  yearStart = daysFromCivil(year, 1, 1)
  when kind == 0 monthly notMonthly
:monthly
  first = daysFromCivil(year, a, 1)
  weekday = floorModulo(first + 4, 7)
  shift = floorModulo(weekdayWanted - weekday, 7)
  calc offset = shift + (week - 1) * 7
  length = monthLength(year, a)
  calc past = offset >= length
  when past back place
:back
  calc day := first + offset - 7
  goto done
:place
  calc day := first + offset
  goto done
:notMonthly
  when kind == 1 julian zeroBased
:julian
  leap = isLeapYear(year)
  calc afterLeapDay = leap && a >= 60
  calc day := yearStart + a - 1
  when afterLeapDay bump done
:bump
  calc day := day + 1
  goto done
:zeroBased
  calc day := yearStart + a
  goto done
:done
  calc change = day * 86400 + seconds - before
  return change

op storeZone "Store what the zone gives for a time: the UTC offset, whether it is daylight time, and the address of the abbreviation"
  input offset Int64 copied
  input daylight Int64 copied
  input name machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  space = workspace()
  machine.storeInt64(space + 448, offset)
  machine.storeInt64(space + 456, daylight)
  machine.storeAddress(space + 464, name)
  return

op ruleZone "What the zone's POSIX rule gives for a time: standard time unless daylight time is in force in the time's UTC year"
  input t Int64 copied
  effect use machine.memory
  uses memoryAccess
  let isDaylight Bool false mut
:begin
  space = workspace()
  calc rule = space + 288
  standardOffset = machine.loadInt64(rule)
  daylightOffset = machine.loadInt64(rule + 8)
  hasDaylight = machine.loadInt64(rule + 16)
  when hasDaylight == 0 standard checked
:standard
  storeZone(standardOffset, 0, rule + 104)
  return
:checked
  days = floorDivide(t, 86400)
  civilFromDays(days, space + 472)
  year = machine.loadInt64(space + 472)
  starts = changeTime(rule + 24, year, standardOffset)
  ends = changeTime(rule + 64, year, daylightOffset)
  when starts > ends southern northern
:southern
  calc isDaylight := t < ends || t >= starts
  goto decided
:northern
  calc isDaylight := t >= starts && t < ends
  goto decided
:decided
  when isDaylight daylight plain
:daylight
  storeZone(daylightOffset, 1, rule + 120)
  return
:plain
  storeZone(standardOffset, 0, rule + 104)
  return

op transitionAt "A transition time of the zone's table, in seconds since 1970"
  input index Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  space = workspace()
  width = machine.loadInt64(space + 280)
  transitions = machine.loadAddress(space + 224)
  when width == 8 wide narrow
:wide
  big = bigEndian64(transitions, index * 8)
  return big
:narrow
  small = bigEndian32(transitions, index * 4)
  value = signed32(small)
  return value

op tableZone "What the zone's TZif table gives for a time: before the first transition the first type that is not daylight time, from the last transition on the POSIX rule that follows the table (or the last type), between them the type of the latest transition"
  input t Int64 copied
  effect use machine.memory
  uses memoryAccess
  let kind Int64 0 mut
  let low Int64 0 mut
  let high Int64 0 mut
:begin
  space = workspace()
  calc zone = space + 192
  count = machine.loadInt64(zone + 16)
  types = machine.loadInt64(zone + 24)
  indices = machine.loadAddress(zone + 40)
  records = machine.loadAddress(zone + 48)
  names = machine.loadAddress(zone + 56)
  hasRule = machine.loadInt64(zone + 64)
  when count == 0 early transitions
:transitions
  firstTime = transitionAt(0)
  when t < firstTime early notEarly
:notEarly
  lastTime = transitionAt(count - 1)
  when t >= lastTime atEnd inside
:atEnd
  when hasRule == 1 followRule lastType
:followRule
  ruleZone(t)
  return
:lastType
  lastIndex = fetch(indices, count - 1)
  calc kind := lastIndex
  goto fill
:early
  calc kind := 0
  goto earlyEach
:earlyEach loop=while max=forever
  calc more = kind < types
  when more earlyCheck earlyDone
:earlyCheck in=earlyEach
  daylightFlag = fetch(records, kind * 6 + 4)
  when daylightFlag == 0 earlyDone earlyNext
:earlyNext in=earlyEach
  calc kind := kind + 1
  goto earlyEach
:earlyDone
  when kind >= types earlyFirst fill
:earlyFirst
  calc kind := 0
  goto fill
:inside
  calc low := 0
  calc high := count - 1
  goto searchEach
:searchEach loop=while max=forever
  when low < high searchStep searchDone
:searchStep in=searchEach
  calc middle = (low + high + 1) / 2
  middleTime = transitionAt(middle)
  when middleTime <= t searchUp searchDown
:searchUp in=searchEach
  calc low := middle
  goto searchEach
:searchDown in=searchEach
  calc high := middle - 1
  goto searchEach
:searchDone
  foundType = fetch(indices, low)
  calc kind := foundType
  goto fill
:fill
  offsetBits = bigEndian32(records, kind * 6)
  offset = signed32(offsetBits)
  daylight = fetch(records, kind * 6 + 4)
  nameIndex = fetch(records, kind * 6 + 5)
  storeZone(offset, daylight, names + nameIndex)
  return

op zoneFor "What the zone gives for a time, stored for storeZone's reader: the UTC offset at byte 448 of the module's bytes, whether it is daylight time at 456, the abbreviation's address at 464"
  input t Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  space = workspace()
  kind = machine.loadInt64(space + 192)
  when kind == 1 table rule
:table
  tableZone(t)
  return
:rule
  ruleZone(t)
  return

## ---------------------------------------------------------------- finding the zone

op textBlock "A C string in a new block of the heap"
  input text String borrowed
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  bytes = string.byteLength(text)
  block = heap.take(bytes + 1)
  at = machine.addressOfString(text)
  machine.copy(block, at, bytes)
  return block

op narrowAscii "Copy UTF-16 text to bytes (the low byte of each unit) and add a 0"
  input utf16 machine.Address copied
  input dest machine.Address copied
  input count Int64 copied
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  goto each
:each loop=while max=count
  when at >= count finish next
:next in=each
  unit = fetch(utf16, at * 2)
  machine.storeByte(dest + at, convert.int64ToByte(unit))
  calc at := at + 1
  goto each
:finish
  machine.storeByte(dest + count, 0)
  return

op tzValue "The value of the environment variable TZ as a C string, or the address 0: on Linux in the environment the process started with, on Windows a copy as ASCII that the next call replaces"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  space = workspace()
  nowhere = machine.zero()
  onLinux = system.linux()
  when onLinux linuxLookUp windowsLookUp
:linuxLookUp
  vector = kernel.environmentVector()
  when vector == nowhere absent eachEntry
:eachEntry loop=while max=forever
  entry = machine.loadAddress(vector + at * 8)
  when entry == nowhere absent compare
:compare in=eachEntry
  first = fetch(entry, 0)
  second = fetch(entry, 1)
  third = fetch(entry, 2)
  calc named = first == 84 && second == 90 && third == 61
  when named present advance
:advance in=eachEntry
  calc at := at + 1
  goto eachEntry
:present
  calc value = entry + 3
  return value
:absent
  return nowhere
:windowsLookUp
  machine.storeInt32(space + 112, 5898324)
  machine.storeInt32(space + 116, 0)
  previous = machine.loadAddress(space + 424)
  heap.give(previous)
  machine.storeAddress(space + 424, nowhere)
  units32 = system.getEnvironmentVariableW(space + 112, nowhere, 0)
  units = convert.int32ToInt64(units32)
  when units == 0 absent read
:read
  buffer = heap.take(units * 2 + 2)
  read32 = system.getEnvironmentVariableW(space + 112, buffer, units32)
  unitsRead = convert.int32ToInt64(read32)
  text = heap.take(unitsRead + 1)
  narrowAscii(buffer, text, unitsRead)
  heap.give(buffer)
  machine.storeAddress(space + 424, text)
  return text

op sameZoneText "Whether two values of TZ are the same: both unset, or both set to the same text"
  input left machine.Address copied
  input right machine.Address copied
  output Bool
  effect use machine.memory
  uses memoryAccess
:begin
  nowhere = machine.zero()
  calc bothUnset = left == nowhere && right == nowhere
  calc oneUnset = left == nowhere || right == nowhere
  when bothUnset equal checkOne
:equal
  return true
:checkOne
  when oneUnset different compareText
:different
  return false
:compareText
  leftBytes = clibrary.cStringLength(left)
  rightBytes = clibrary.cStringLength(right)
  when leftBytes == rightBytes compareBytes different
:compareBytes
  order = machine.compare(left, right, leftBytes)
  calc same = order == 0
  return same

op loadZone "Find the time zone as glibc's tzset does: TZ if it is set (empty means UTC; a leading colon is skipped; a file under /usr/share/zoneinfo, or an absolute path, on Linux, else a POSIX string), else /etc/localtime on Linux and the system's zone on Windows; UTC when nothing is found"
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let skip Int64 0 mut
  let localtimePath String "/etc/localtime"
:begin
  space = workspace()
  calc zone = space + 192
  tz = tzValue()
  nowhere = machine.zero()
  loaded = machine.loadInt64(space + 440)
  key = machine.loadAddress(space + 432)
  same = sameZoneText(tz, key)
  calc fresh = loaded == 1 && same
  when fresh unchanged reload
:unchanged
  return
:reload
  old = machine.loadAddress(zone + 8)
  heap.give(old)
  machine.fill(zone, 0, 96)
  heap.give(key)
  machine.storeAddress(space + 432, nowhere)
  machine.storeInt64(space + 440, 1)
  when tz == nowhere keyDone copyKey
:copyKey
  keyBytes = clibrary.cStringLength(tz)
  keyCopy = heap.take(keyBytes + 1)
  machine.copy(keyCopy, tz, keyBytes)
  machine.storeAddress(space + 432, keyCopy)
  goto keyDone
:keyDone
  machine.storeInt32(space + 96, 23124)
  machine.storeInt32(space + 100, 4412501)
  useUtc()
  onLinux = system.linux()
  when onLinux markLinux markWindows
:markLinux
  machine.storeInt64(space + 760, 0)
  goto marked
:markWindows
  machine.storeInt64(space + 760, 1)
  goto marked
:marked
  when tz == nowhere noValue given
:noValue
  when onLinux unsetLinux unsetWindows
:unsetLinux
  path = textBlock(localtimePath)
  tryFile(path)
  heap.give(path)
  return
:unsetWindows
  systemZone()
  return
:given
  first = fetch(tz, 0)
  when first == 0 empty named
:empty
  return
:named
  when first == 58 colon plain
:colon
  calc skip := 1
  goto plain
:plain
  calc spec = tz + skip
  when onLinux tryLinux parseOnly
:tryLinux
  found = tryFile(spec)
  when found == 1 finished parseOnly
:finished
  return
:parseOnly
  parsePosix(spec)
  return

op systemZone "The system's time zone on Windows, as GetDynamicTimeZoneInformation gives it: the offsets from the bias and its two adjustments, the names, and the month, week, and weekday rules of daylight time that start and end each year"
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  onLinux = system.linux()
  when onLinux nothing ask
:nothing
  return
:ask
  space = workspace()
  calc rule = space + 288
  info = heap.take(432)
  system.getDynamicTimeZoneInformation(info)
  bias = machine.loadInt32(info)
  standardBias = machine.loadInt32(info + 84)
  daylightBias = machine.loadInt32(info + 168)
  calc standardOffset = convert.int32ToInt64(0 - bias - standardBias) * 60
  calc daylightOffset = convert.int32ToInt64(0 - bias - daylightBias) * 60
  machine.storeInt64(rule, standardOffset)
  machine.storeInt64(rule + 8, standardOffset)
  copyName(info + 4, rule + 104)
  copyName(info + 88, rule + 120)
  endMonth = fetch(info, 70)
  when endMonth == 0 single some
:single
  machine.copy(rule + 120, rule + 104, 16)
  heap.give(info)
  return
:some
  startMonth = fetch(info, 154)
  machine.storeInt64(rule + 8, daylightOffset)
  machine.storeInt64(rule + 16, 1)
  machine.storeInt64(rule + 24, 0)
  machine.storeInt64(rule + 32, startMonth)
  startWeek = fetch(info, 158)
  machine.storeInt64(rule + 40, startWeek)
  startDay = fetch(info, 156)
  machine.storeInt64(rule + 48, startDay)
  startHour = fetch(info, 160)
  startMinute = fetch(info, 162)
  startSecond = fetch(info, 164)
  calc startSeconds = startHour * 3600 + startMinute * 60 + startSecond
  machine.storeInt64(rule + 56, startSeconds)
  machine.storeInt64(rule + 64, 0)
  machine.storeInt64(rule + 72, endMonth)
  endWeek = fetch(info, 74)
  machine.storeInt64(rule + 80, endWeek)
  endDay = fetch(info, 72)
  machine.storeInt64(rule + 88, endDay)
  endHour = fetch(info, 76)
  endMinute = fetch(info, 78)
  endSecond = fetch(info, 80)
  calc endSeconds = endHour * 3600 + endMinute * 60 + endSecond
  machine.storeInt64(rule + 96, endSeconds)
  heap.give(info)
  return

op copyName "Copy a zone name from UTF-16 (its low bytes) to a 16-byte buffer: at most 15 characters and a 0; a name of more than five characters with spaces in it (Windows names its zones `Eastern Standard Time`) is written as the capitals that start its words (EST), as the C library's abbreviations are"
  invariant abbreviates "A name with words becomes the capitals that start them, any other name is copied up to 15 characters"
  input wideName machine.Address copied
  input dest machine.Address copied
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let kept Int64 0 mut
  let length Int64 0 mut
  let spaces Int64 0 mut
:begin
  goto measureEach
:measureEach loop=while max=64
  unit = fetch(wideName, length * 2)
  when unit == 0 measured measureNext
:measureNext in=measureEach
  when unit == 32 countSpace stepMeasure
:countSpace in=measureEach
  calc spaces := spaces + 1
  goto stepMeasure
:stepMeasure in=measureEach
  calc length := length + 1
  goto measureEach
:measured
  calc abbreviate = length > 5 && spaces > 0
  when abbreviate initialsStart copyEach
:initialsStart
  calc at := 0
  goto initialsEach
:initialsEach loop=while max=64
  when at >= length finish initialsLetter
:initialsLetter in=initialsEach
  letter = fetch(wideName, at * 2)
  previous = fetch(wideName, at * 2 - 2)
  calc starts = at == 0 || previous == 32
  calc capital = letter >= 65 && letter <= 90
  calc takes = starts && capital && kept < 15
  when takes initialsTake initialsNext
:initialsTake in=initialsEach
  machine.storeByte(dest + kept, convert.int64ToByte(letter))
  calc kept := kept + 1
  goto initialsNext
:initialsNext in=initialsEach
  calc at := at + 1
  goto initialsEach
:copyEach
  calc at := 0
  goto plainEach
:plainEach loop=while max=16
  plainUnit = fetch(wideName, at * 2)
  calc stop = at >= 15 || plainUnit == 0
  when stop plainDone plainStore
:plainStore in=plainEach
  machine.storeByte(dest + at, convert.int64ToByte(plainUnit))
  calc at := at + 1
  goto plainEach
:plainDone
  calc kept := at
  goto finish
:finish
  machine.storeByte(dest + kept, 0)
  return

## ---------------------------------------------------------------- localtime and mktime

op convertLocal "Break a time down in the zone loaded last into a struct tm, with isdst, gmtoff, and the zone's abbreviation; 1, or 0 with EOVERFLOW when the year does not fit"
  input t Int64 copied
  input tm machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  calc outside = t > 4611686018427387904 || t < -4611686018427387904
  when outside overflow inside
:overflow
  clibrary.setErrno(overflowError)
  return 0
:inside
  space = workspace()
  zoneFor(t)
  offset = machine.loadInt64(space + 448)
  daylight = machine.loadInt64(space + 456)
  name = machine.loadAddress(space + 464)
  done = breakDown(t, offset, tm)
  when done == 0 overflow good
:good
  machine.storeInt32(tm + 32, convert.int64ToInt32(daylight))
  machine.storeInt64(tm + 40, offset)
  machine.storeAddress(tm + 48, name)
  return 1

op localtimeInto "Find the zone, then break a time down in it into a struct tm; the struct tm, or the address 0 with EOVERFLOW"
  input t Int64 copied
  input tm machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere = machine.zero()
  loadZone()
  done = convertLocal(t, tm)
  when done == 0 failed good
:failed
  return nowhere
:good
  return tm

op localtimeStatic "localtime: a time broken down in the local zone into the one static struct tm"
  input timer machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "localtime"
:begin
  space = workspace()
  t = machine.loadInt64(timer)
  result = localtimeInto(t, space)
  return result

op localtimeResult "localtime_r: a time broken down in the local zone into the caller's struct tm"
  input timer machine.Address copied
  input result machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "localtime_r"
:begin
  t = machine.loadInt64(timer)
  broken = localtimeInto(t, result)
  return broken

op fieldAt "An int field of a struct tm as a whole number"
  input tm machine.Address copied
  input offset Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  value = machine.loadInt32(tm + offset)
  wide = convert.int32ToInt64(value)
  return wide

op daylightDiffers "Whether a requested tm_isdst (negative for no request) and a converted one are both known and differ"
  input requested Int64 copied
  input actual Int64 copied
  output Bool
:begin
  calc differs = requested >= 0 && actual >= 0 && ((requested == 0 && actual != 0) || (requested != 0 && actual == 0))
  return differs

op makeTimeIn "mktime for the zone already loaded: the time of a struct tm in it, which is made to hold the normalized fields with tm_wday, tm_yday, tm_isdst, tm_gmtoff, and tm_zone; the search is glibc's (gnulib's mktime): it guesses from the offset the last call found, converges on the time whose fields match, looks for a nearby time of the requested tm_isdst, and in a spring-forward gap chooses between the two times it oscillates between; -1 with EOVERFLOW when no time fits"
  invariant normalizes "Gives the time whose local fields are the struct tm's, and rewrites the struct tm normalized"
  input tm machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let t Int64 0 mut
  let firstBefore Int64 0 mut
  let secondBefore Int64 0 mut
  let daylightBefore Int64 0 mut
  let probes Int64 6 mut
  let step Int64 0 mut
  let secondsClamped Int64 0 mut
:begin
  space = workspace()
  isdst = fieldAt(tm, 32)
  sec = fieldAt(tm, 0)
  minute = fieldAt(tm, 4)
  hour = fieldAt(tm, 8)
  mday = fieldAt(tm, 12)
  mon = fieldAt(tm, 16)
  year = fieldAt(tm, 20)
  monthYears = floorDivide(mon, 12)
  monthRest = floorModulo(mon, 12)
  calc fullYear = year + 1900 + monthYears
  days = daysFromCivil(fullYear, monthRest + 1, 1)
  calc secondsClamped := sec
  when sec < 0 low highCheck
:low
  calc secondsClamped := 0
  goto clamped
:highCheck
  when sec > 59 high clamped
:high
  calc secondsClamped := 59
  goto clamped
:clamped
  calc requested = (days + mday - 1) * 86400 + hour * 3600 + minute * 60 + secondsClamped
  guess = machine.loadInt64(space + 176)
  calc t := requested + guess
  calc firstBefore := t
  calc secondBefore := t
  goto attempt
:attempt loop=while max=forever
  converted = convertLocal(t, space + 504)
  when converted == 0 failed convertedOk
:convertedOk in=attempt
  offset = machine.loadInt64(space + 544)
  dayFlag = fieldAt(space, 536)
  calc candidate = requested - offset
  when candidate == t matched oscillation
:oscillation in=attempt
  calc unknownRequest = isdst < 0 && daylightBefore <= dayFlag
  calc knownRequest = isdst >= 0 && ((isdst == 0 && dayFlag != 0) || (isdst != 0 && dayFlag == 0))
  calc oscillating = t == firstBefore && t != secondBefore && (unknownRequest || knownRequest)
  when oscillating found countDown
:countDown in=attempt
  calc probes := probes - 1
  when probes == 0 failed shift
:shift in=attempt
  calc firstBefore := secondBefore
  calc secondBefore := t
  calc t := candidate
  calc daylightBefore := dayFlag
  goto attempt
:matched
  differs = daylightDiffers(isdst, dayFlag)
  when differs search found
:search
  goto probeEach
:probeEach loop=while max=forever
  calc delta = (step / 2 + 1) * 601200
  when delta >= 268828200 exhausted probe
:probe in=probeEach
  calc direction = (step % 2) * 2 - 1
  calc other = t + delta * direction
  converted2 = convertLocal(other, space + 560)
  when converted2 == 0 failed probeCheck
:probeCheck in=probeEach
  otherOffset = machine.loadInt64(space + 600)
  otherFlag = fieldAt(space, 592)
  differs2 = daylightDiffers(isdst, otherFlag)
  when differs2 probeNext probeFound
:probeNext in=probeEach
  calc step := step + 1
  goto probeEach
:probeFound in=probeEach
  calc extrapolated = requested - otherOffset
  converted3 = convertLocal(extrapolated, space + 504)
  when converted3 == 0 probeNext probeAdopt
:probeAdopt in=probeEach
  calc t := extrapolated
  goto found
:exhausted
  clibrary.setErrno(overflowError)
  return -1
:found
  calc newGuess = t - requested
  machine.storeInt64(space + 176, newGuess)
  calc adjustment = sec - secondsClamped
  when adjustment == 0 finish adjust
:adjust
  calc t := t + adjustment
  goto finish
:finish
  final = convertLocal(t, tm)
  when final == 0 failed done
:done
  return t
:failed
  clibrary.setErrno(overflowError)
  return -1


op makeTime "mktime: the time of a struct tm in the local zone, with the struct tm made to hold the normalized fields (see makeTimeIn)"
  input tm machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "mktime"
:begin
  loadZone()
  t = makeTimeIn(tm)
  return t

## ---------------------------------------------------------------- asctime and ctime

op putNumber "Write a whole number as printf writes %<width>.<minDigits>d: spaces to the width, a minus sign, zeros to the digits, and the digits; the bytes written"
  input dest machine.Address copied
  input value Int64 copied
  input minDigits Int64 copied
  input width Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let magnitude Int64 0 mut
  let count Int64 0 mut
  let zeros Int64 0 mut
  let spaces Int64 0 mut
  let negative Int64 0 mut
:begin
  space = workspace()
  calc magnitude := value
  when value < 0 flip scan
:flip
  calc magnitude := 0 - value
  calc negative := 1
  goto scan
:scan
  goto digitEach
:digitEach loop=while max=24
  calc finished = count >= 1 && magnitude == 0
  when finished digitsDone digitBody
:digitBody in=digitEach
  calc place = space + 743 - count
  machine.storeByte(place, convert.int64ToByte(magnitude % 10 + 48))
  calc magnitude := magnitude / 10
  calc count := count + 1
  goto digitEach
:digitsDone
  when count < minDigits needZeros sized
:needZeros
  calc zeros := minDigits - count
  goto sized
:sized
  calc total = negative + zeros + count
  when width > total needSpaces layout
:needSpaces
  calc spaces := width - total
  machine.fill(dest, 32, spaces)
  goto layout
:layout
  when negative == 1 minus digitsOut
:minus
  machine.storeByte(dest + spaces, 45)
  goto digitsOut
:digitsOut
  machine.fill(dest + spaces + negative, 48, zeros)
  machine.copy(dest + spaces + negative + zeros, space + 744 - count, count)
  calc written = spaces + negative + zeros + count
  return written

op asctimeInto "asctime_r's text for a struct tm, with its 0 byte, in a buffer of a size: weekday and month names, the day in 3 columns, hour, minute, and second in 2 digits, the year, and a line feed; the buffer, or the address 0 with EOVERFLOW when the text would not fit (a weekday or month out of range is ???)"
  invariant writesText "Writes the 25 characters and a line feed asctime gives, or gives the address 0 when they do not fit"
  input tm machine.Address copied
  input buffer machine.Address copied
  input size Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let days String "SunMonTueWedThuFriSat"
  let months String "JanFebMarAprMayJunJulAugSepOctNovDec"
  let unknown String "???"
  let at Int64 0 mut
:begin
  nowhere = machine.zero()
  temp = heap.take(256)
  weekday = fieldAt(tm, 24)
  month = fieldAt(tm, 16)
  mday = fieldAt(tm, 12)
  hour = fieldAt(tm, 8)
  minute = fieldAt(tm, 4)
  sec = fieldAt(tm, 0)
  year = fieldAt(tm, 20)
  dayNames = machine.addressOfString(days)
  monthNames = machine.addressOfString(months)
  unknownName = machine.addressOfString(unknown)
  calc weekdayBad = weekday < 0 || weekday > 6
  when weekdayBad weekdayUnknown weekdayKnown
:weekdayUnknown
  machine.copy(temp, unknownName, 3)
  goto weekdayDone
:weekdayKnown
  machine.copy(temp, dayNames + weekday * 3, 3)
  goto weekdayDone
:weekdayDone
  machine.storeByte(temp + 3, 32)
  calc monthBad = month < 0 || month > 11
  when monthBad monthUnknown monthKnown
:monthUnknown
  machine.copy(temp + 4, unknownName, 3)
  goto monthDone
:monthKnown
  machine.copy(temp + 4, monthNames + month * 3, 3)
  goto monthDone
:monthDone
  calc at := 7
  written = putNumber(temp + at, mday, 1, 3)
  calc at := at + written
  machine.storeByte(temp + at, 32)
  calc at := at + 1
  hourWritten = putNumber(temp + at, hour, 2, 0)
  calc at := at + hourWritten
  machine.storeByte(temp + at, 58)
  calc at := at + 1
  minuteWritten = putNumber(temp + at, minute, 2, 0)
  calc at := at + minuteWritten
  machine.storeByte(temp + at, 58)
  calc at := at + 1
  secondWritten = putNumber(temp + at, sec, 2, 0)
  calc at := at + secondWritten
  machine.storeByte(temp + at, 32)
  calc at := at + 1
  shownYear32 = clibrary.lowInt32(year + 1900)
  shownYear = convert.int32ToInt64(shownYear32)
  yearWritten = putNumber(temp + at, shownYear, 1, 0)
  calc at := at + yearWritten
  machine.storeByte(temp + at, 10)
  calc at := at + 1
  when at >= size overflow fits
:overflow
  heap.give(temp)
  clibrary.setErrno(overflowError)
  return nowhere
:fits
  machine.copy(buffer, temp, at)
  machine.storeByte(buffer + at, 0)
  heap.give(temp)
  return buffer

op asctimeStatic "asctime: the text of a struct tm in the one static buffer"
  input tm machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "asctime"
:begin
  space = workspace()
  text = asctimeInto(tm, space + 64, 26)
  return text

op asctimeResult "asctime_r: the text of a struct tm in the caller's buffer of 26 bytes"
  input tm machine.Address copied
  input buffer machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "asctime_r"
:begin
  text = asctimeInto(tm, buffer, 26)
  return text

op ctimeStatic "ctime: asctime of localtime, in the one static buffer; the address 0 when the time does not fit"
  input timer machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "ctime"
:begin
  space = workspace()
  nowhere = machine.zero()
  t = machine.loadInt64(timer)
  broken = localtimeInto(t, space)
  when broken == nowhere failed good
:failed
  return nowhere
:good
  text = asctimeInto(space, space + 64, 26)
  return text

op ctimeResult "ctime_r: asctime_r of localtime_r, in the caller's buffer"
  input timer machine.Address copied
  input buffer machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "ctime_r"
:begin
  space = workspace()
  nowhere = machine.zero()
  t = machine.loadInt64(timer)
  broken = localtimeInto(t, space + 504)
  when broken == nowhere failed good
:failed
  return nowhere
:good
  text = asctimeInto(space + 504, buffer, 26)
  return text

## ---------------------------------------------------------------- strftime: writing

## strftime's state is in machine.state (see the top): the output, its size, the bytes written, whether it ran out, the
## struct tm, and the flags and width of the conversion being written. A piece of output is added as glibc adds it:
## it fits only when its bytes and its padding are fewer than the room left (one byte stays for the 0), and a piece
## that does not fit stops the whole call at once, leaving what was written before it.

op copyFolded "Copy bytes, with a to z made A to Z or A to Z made a to z when asked"
  input dest machine.Address copied
  input source machine.Address copied
  input count Int64 copied
  input upper Int64 copied
  input lower Int64 copied
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  goto each
:each loop=while max=count
  when at >= count finish next
:next in=each
  letter = fetch(source, at)
  calc isLower = letter >= 97 && letter <= 122
  calc isUpper = letter >= 65 && letter <= 90
  calc makeUpper = upper == 1 && isLower
  calc makeLower = lower == 1 && isUpper
  when makeUpper toUpper lowerCheck
:toUpper in=each
  machine.storeByte(dest + at, convert.int64ToByte(letter - 32))
  calc at := at + 1
  goto each
:lowerCheck in=each
  when makeLower toLower keep
:toLower in=each
  machine.storeByte(dest + at, convert.int64ToByte(letter + 32))
  calc at := at + 1
  goto each
:keep in=each
  machine.storeByte(dest + at, convert.int64ToByte(letter))
  calc at := at + 1
  goto each
:finish
  return

op emitBytes "Add bytes to strftime's output, padded on the left to the width (with zeros for the 0 flag, else spaces) and with the case change asked: 1, or 0 when it does not fit, which stops strftime (ERANGE)"
  input source machine.Address copied
  input count Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let fill Int64 0 mut
:begin
  space = workspace()
  dst = machine.loadAddress(space + 616)
  limit = machine.loadInt64(space + 624)
  written = machine.loadInt64(space + 632)
  pad = machine.loadInt64(space + 656)
  upper = machine.loadInt64(space + 664)
  lower = machine.loadInt64(space + 672)
  width = machine.loadInt64(space + 680)
  calc delta = width - count
  when delta > 0 padded plain
:padded
  calc fill := delta
  goto sized
:plain
  calc fill := 0
  goto sized
:sized
  calc increase = count + fill
  calc room = limit - written
  when increase >= room overflow fits
:overflow
  machine.storeInt64(space + 640, 1)
  clibrary.setErrno(rangeError)
  return 0
:fits
  when pad == 48 zeros spaces
:zeros
  machine.fill(dst + written, 48, fill)
  goto copy
:spaces
  machine.fill(dst + written, 32, fill)
  goto copy
:copy
  copyFolded(dst + written + fill, source, count, upper, lower)
  machine.storeInt64(space + 632, written + increase)
  return 1

op emitChar "Add one byte to strftime's output"
  input letter Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  space = workspace()
  machine.storeByte(space + 752, convert.int64ToByte(letter))
  status = emitBytes(space + 752, 1)
  return status

op emitNumber "Add a whole number to strftime's output as glibc's DO_NUMBER does: at least `digits` characters (the sign counts) or the width, padded with zeros after the sign, or with spaces before it for the _ flag (always for the spacepad conversions unless 0 or - was given), not at all for -"
  input value Int64 copied
  input digits Int64 copied
  input spacePad Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let pad Int64 0 mut
  let wanted Int64 0 mut
  let length Int64 0 mut
:begin
  space = workspace()
  calc pad := 0
  stored = machine.loadInt64(space + 656)
  width = machine.loadInt64(space + 680)
  calc pad := stored
  calc spaced = spacePad == 1 && stored != 48 && stored != 45
  when spaced forceSpace sizeIt
:forceSpace
  calc pad := 95
  goto sizeIt
:sizeIt
  calc wanted := digits
  when width > digits wider block
:wider
  calc wanted := width
  goto block
:block
  text = heap.take(wanted + 48)
  when pad == 45 minimal paddedCheck
:minimal
  calc length := putNumber(text, value, 1, 0)
  goto emit
:paddedCheck
  when pad == 95 spaces zeros
:spaces
  calc length := putNumber(text, value, 1, wanted)
  goto emit
:zeros
  when value < 0 negativeZeros positiveZeros
:negativeZeros
  calc length := putNumber(text, value, wanted - 1, 0)
  goto emit
:positiveZeros
  calc length := putNumber(text, value, wanted, 0)
  goto emit
:emit
  status = emitBytes(text, length)
  heap.give(text)
  return status

op nameLength "The length of a name in a table of cells of ten bytes, where each name ends at a space"
  input cells machine.Address copied
  input index Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  goto each
:each loop=while max=10
  letter = fetch(cells, index * 10 + at)
  calc stop = at >= 10 || letter == 32
  when stop finish next
:next in=each
  calc at := at + 1
  goto each
:finish
  return at

op emitName "Add a weekday's or month's name: kind 0 a weekday in full, 1 abbreviated, 2 a month in full, 3 abbreviated; a number out of range is a ?"
  input kind Int64 copied
  input index Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let weekdays String "Sunday    Monday    Tuesday   Wednesday Thursday  Friday    Saturday  "
  let months String "January   February  March     April     May       June      July      August    September October   November  December  "
  let weekdaysShort String "SunMonTueWedThuFriSat"
  let monthsShort String "JanFebMarAprMayJunJulAugSepOctNovDec"
  let question String "?"
:begin
  mark = machine.addressOfString(question)
  calc weekdayBad = kind < 2 && (index < 0 || index > 6)
  calc monthBad = kind >= 2 && (index < 0 || index > 11)
  calc bad = weekdayBad || monthBad
  when bad unknown known
:unknown
  status = emitBytes(mark, 1)
  return status
:known
  when kind == 0 longWeekday notLongWeekday
:longWeekday
  base = machine.addressOfString(weekdays)
  size = nameLength(base, index)
  status0 = emitBytes(base + index * 10, size)
  return status0
:notLongWeekday
  when kind == 1 shortWeekday notShortWeekday
:shortWeekday
  shortBase = machine.addressOfString(weekdaysShort)
  status1 = emitBytes(shortBase + index * 3, 3)
  return status1
:notShortWeekday
  when kind == 2 longMonth shortMonth
:longMonth
  monthBase = machine.addressOfString(months)
  monthSize = nameLength(monthBase, index)
  status2 = emitBytes(monthBase + index * 10, monthSize)
  return status2
:shortMonth
  shortMonthBase = machine.addressOfString(monthsShort)
  status3 = emitBytes(shortMonthBase + index * 3, 3)
  return status3

## ---------------------------------------------------------------- strftime: the conversions

op isoDays "The days of the ISO week-numbering year's weeks (glibc's iso_week_days): week 1 is the week with the year's first Thursday, and weeks start on Monday"
  input yday Int64 copied
  input wday Int64 copied
  output Int64
:begin
  calc days = yday - (yday - wday + 4 + 378) % 7 + 4 - 1
  return days

op isoCompute "A struct tm's ISO 8601 year (which 0) or week number (which 1)"
  input tm machine.Address copied
  input which Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let year Int64 0 mut
  let days Int64 0 mut
  let nextDays Int64 0 mut
:begin
  fieldYear = fieldAt(tm, 20)
  yday = fieldAt(tm, 28)
  wday = fieldAt(tm, 24)
  calc year := fieldYear + 1900
  calc days := isoDays(yday, wday)
  when days < 0 previous following
:previous
  calc year := year - 1
  leapPrevious = isLeapYear(year)
  when leapPrevious previousLeap previousPlain
:previousLeap
  calc days := isoDays(yday + 366, wday)
  goto result
:previousPlain
  calc days := isoDays(yday + 365, wday)
  goto result
:following
  leapThis = isLeapYear(year)
  when leapThis thisLeap thisPlain
:thisLeap
  calc nextDays := isoDays(yday - 366, wday)
  goto nextCheck
:thisPlain
  calc nextDays := isoDays(yday - 365, wday)
  goto nextCheck
:nextCheck
  when nextDays >= 0 nextYear result
:nextYear
  calc year := year + 1
  calc days := nextDays
  goto result
:result
  when which == 0 giveYear giveWeek
:giveYear
  return year
:giveWeek
  calc week = days / 7 + 1
  return week

op hashCase "Apply the # flag to the conversion being written: upper case for names (mode 0), lower case for the others (mode 1)"
  input mode Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  space = workspace()
  hash = machine.loadInt64(space + 696)
  when hash == 1 apply nothing
:apply
  when mode == 0 upper lower
:upper
  machine.storeInt64(space + 664, 1)
  machine.storeInt64(space + 672, 0)
  return
:lower
  machine.storeInt64(space + 664, 0)
  machine.storeInt64(space + 672, 1)
  return
:nothing
  return

op hourOfTwelve "The hour on a 12-hour clock as glibc computes it: above 12 less 12, 0 as 12, any other as it is"
  input hour Int64 copied
  output Int64
  let result Int64 0 mut
:begin
  calc result := hour
  when hour > 12 over zeroCheck
:over
  calc result := hour - 12
  goto done
:zeroCheck
  when hour == 0 midnight done
:midnight
  calc result := 12
  goto done
:done
  return result

op emitZone "Add the zone's abbreviation for %Z: tm_zone, or when that is NULL or empty and tm_isdst is not negative, the standard or daylight name of the zone TZ says"
  input tm machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  space = workspace()
  zone = machine.loadAddress(tm + 48)
  nowhere = machine.zero()
  isdst = fieldAt(tm, 32)
  when zone == nowhere searchName checkEmpty
:checkEmpty
  first = fetch(zone, 0)
  when first == 0 searchName give
:searchName
  when isdst < 0 giveEmpty lookUp
:giveEmpty
  status0 = emitBytes(space + 98, 0)
  return status0
:lookUp
  loadZone()
  kind = machine.loadInt64(space + 192)
  when kind == 1 tableName ruleName
:tableName
  when isdst == 0 tableStandard tableDaylight
:tableStandard
  standard = machine.loadAddress(space + 264)
  length1 = clibrary.cStringLength(standard)
  status1 = emitBytes(standard, length1)
  return status1
:tableDaylight
  daylight = machine.loadAddress(space + 272)
  length2 = clibrary.cStringLength(daylight)
  status2 = emitBytes(daylight, length2)
  return status2
:ruleName
  when isdst == 0 ruleStandard ruleDaylight
:ruleStandard
  length3 = clibrary.cStringLength(space + 392)
  status3 = emitBytes(space + 392, length3)
  return status3
:ruleDaylight
  length4 = clibrary.cStringLength(space + 408)
  status4 = emitBytes(space + 408, length4)
  return status4
:give
  length5 = clibrary.cStringLength(zone)
  status5 = emitBytes(zone, length5)
  return status5

op emitEpoch "Add %s: the seconds since 1970 of the struct tm read as local time (mktime of a copy), nothing when mktime fails"
  input tm machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let value Int64 0 mut
:begin
  copy = heap.take(64)
  machine.copy(copy, tm, 56)
  t = makeTime(copy)
  calc value := t
  when t == -1 verify show
:verify
  again = heap.take(64)
  converted = convertLocal(-1, again)
  when converted == 0 failed compare
:compare
  same = machine.compare(copy, again, 24)
  dst1 = fieldAt(copy, 32)
  dst2 = fieldAt(again, 32)
  calc matches = same == 0 && dst1 == dst2
  heap.give(again)
  when matches show failed
:failed
  heap.give(copy)
  return 1
:show
  heap.give(copy)
  status = emitNumber(value, 1, 0)
  return status

op emitSimple "Add one conversion that is not a composite of others, as glibc writes it in the C locale: 1 when written, 0 when it did not fit, 2 when the character is no conversion"
  input conv Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let value Int64 0 mut
  let digits Int64 2 mut
  let spacePad Int64 0 mut
  let meridiem String "AMPM"
:begin
  space = workspace()
  tm = machine.loadAddress(space + 648)
  when conv == 97 weekdayShort checkLongWeekday
:weekdayShort
  hashCase(0)
  wdayA = fieldAt(tm, 24)
  statusA = emitName(1, wdayA)
  return statusA
:checkLongWeekday
  when conv == 65 weekdayLong checkMonthShort
:weekdayLong
  hashCase(0)
  wdayB = fieldAt(tm, 24)
  statusB = emitName(0, wdayB)
  return statusB
:checkMonthShort
  calc isMonthShort = conv == 98 || conv == 104
  when isMonthShort monthShort checkMonthLong
:monthShort
  hashCase(0)
  monthA = fieldAt(tm, 16)
  statusC = emitName(3, monthA)
  return statusC
:checkMonthLong
  when conv == 66 monthLong checkCentury
:monthLong
  hashCase(0)
  monthB = fieldAt(tm, 16)
  statusD = emitName(2, monthB)
  return statusD
:checkCentury
  when conv == 67 century checkDay
:century
  yearC = fieldAt(tm, 20)
  calc fullC = yearC + 1900
  calc adjust = fullC % 100 < 0
  when adjust centuryDown centuryUp
:centuryDown
  calc value := fullC / 100 - 1
  calc digits := 1
  goto number
:centuryUp
  calc value := fullC / 100
  calc digits := 1
  goto number
:checkDay
  when conv == 100 dayOfMonth checkSpaceDay
:dayOfMonth
  dayD = fieldAt(tm, 12)
  calc value := dayD
  goto number
:checkSpaceDay
  when conv == 101 spaceDay checkIsoYear
:spaceDay
  dayE = fieldAt(tm, 12)
  calc value := dayE
  calc spacePad := 1
  goto number
:checkIsoYear
  when conv == 71 isoYear checkShortIsoYear
:isoYear
  yearG = isoCompute(tm, 0)
  calc value := yearG
  calc digits := 1
  goto number
:checkShortIsoYear
  when conv == 103 shortIsoYear checkHour
:shortIsoYear
  yearSmall = isoCompute(tm, 0)
  calc value := (yearSmall % 100 + 100) % 100
  goto number
:checkHour
  when conv == 72 hour24 checkHour12
:hour24
  hourH = fieldAt(tm, 8)
  calc value := hourH
  goto number
:checkHour12
  when conv == 73 hour12 checkYearDay
:hour12
  hourI = fieldAt(tm, 8)
  twelveI = hourOfTwelve(hourI)
  calc value := twelveI
  goto number
:checkYearDay
  when conv == 106 yearDay checkSpaceHour
:yearDay
  ydayJ = fieldAt(tm, 28)
  calc value := ydayJ + 1
  calc digits := 3
  goto number
:checkSpaceHour
  when conv == 107 spaceHour checkSpaceHour12
:spaceHour
  hourK = fieldAt(tm, 8)
  calc value := hourK
  calc spacePad := 1
  goto number
:checkSpaceHour12
  when conv == 108 spaceHour12 checkMonth
:spaceHour12
  hourL = fieldAt(tm, 8)
  twelveL = hourOfTwelve(hourL)
  calc value := twelveL
  calc spacePad := 1
  goto number
:checkMonth
  when conv == 109 month checkMinute
:month
  monthM = fieldAt(tm, 16)
  calc value := monthM + 1
  goto number
:checkMinute
  when conv == 77 minute checkNewline
:minute
  minuteM = fieldAt(tm, 4)
  calc value := minuteM
  goto number
:checkNewline
  when conv == 110 newline checkMeridiem
:newline
  statusN = emitChar(10)
  return statusN
:checkMeridiem
  when conv == 112 meridiemUpper checkMeridiemLower
:meridiemUpper
  hashCase(1)
  goto meridiemText
:checkMeridiemLower
  when conv == 80 meridiemLower checkEpoch
:meridiemLower
  machine.storeInt64(space + 664, 0)
  machine.storeInt64(space + 672, 1)
  goto meridiemText
:meridiemText
  hourP = fieldAt(tm, 8)
  base = machine.addressOfString(meridiem)
  when hourP > 11 afternoon morning
:afternoon
  statusP = emitBytes(base + 2, 2)
  return statusP
:morning
  statusQ = emitBytes(base, 2)
  return statusQ
:checkEpoch
  when conv == 115 epoch checkSecond
:epoch
  statusS = emitEpoch(tm)
  return statusS
:checkSecond
  when conv == 83 second checkTab
:second
  secondS = fieldAt(tm, 0)
  calc value := secondS
  goto number
:checkTab
  when conv == 116 tab checkMondayDay
:tab
  statusT = emitChar(9)
  return statusT
:checkMondayDay
  when conv == 117 mondayDay checkSundayWeek
:mondayDay
  wdayU = fieldAt(tm, 24)
  calc value := (wdayU - 1 + 7) % 7 + 1
  calc digits := 1
  goto number
:checkSundayWeek
  when conv == 85 sundayWeek checkIsoWeek
:sundayWeek
  ydayW = fieldAt(tm, 28)
  wdayW = fieldAt(tm, 24)
  calc value := (ydayW - wdayW + 7) / 7
  goto number
:checkIsoWeek
  when conv == 86 isoWeek checkWeekday
:isoWeek
  weekV = isoCompute(tm, 1)
  calc value := weekV
  goto number
:checkWeekday
  when conv == 119 weekday checkMondayWeek
:weekday
  wdayX = fieldAt(tm, 24)
  calc value := wdayX
  calc digits := 1
  goto number
:checkMondayWeek
  when conv == 87 mondayWeek checkShortYear
:mondayWeek
  ydayY = fieldAt(tm, 28)
  wdayY = fieldAt(tm, 24)
  calc value := (ydayY - (wdayY - 1 + 7) % 7 + 7) / 7
  goto number
:checkShortYear
  when conv == 121 shortYear checkYear
:shortYear
  yearY = fieldAt(tm, 20)
  calc value := (yearY % 100 + 100) % 100
  goto number
:checkYear
  when conv == 89 year checkOffset
:year
  yearZ = fieldAt(tm, 20)
  calc value := yearZ + 1900
  calc digits := 1
  goto number
:checkOffset
  when conv == 122 offset checkZone
:offset
  isdstO = fieldAt(tm, 32)
  when isdstO < 0 offsetNothing offsetKnown
:offsetNothing
  return 1
:offsetKnown
  gmtoff = machine.loadInt64(tm + 40)
  when gmtoff < 0 offsetMinus offsetPlus
:offsetMinus
  statusM = emitChar(45)
  when statusM == 0 offsetFailed offsetNegative
:offsetFailed
  return 0
:offsetNegative
  calc minutesNegative = (0 - gmtoff) / 60
  calc value := minutesNegative / 60 * 100 + minutesNegative % 60
  calc digits := 4
  goto number
:offsetPlus
  statusPlus = emitChar(43)
  when statusPlus == 0 offsetFailed offsetPositive
:offsetPositive
  calc minutesPositive = gmtoff / 60
  calc value := minutesPositive / 60 * 100 + minutesPositive % 60
  calc digits := 4
  goto number
:checkZone
  when conv == 90 zone checkPercent
:zone
  hashCase(1)
  statusZ = emitZone(tm)
  return statusZ
:checkPercent
  when conv == 37 percent unknown
:percent
  statusPercent = emitChar(37)
  return statusPercent
:unknown
  return 2
:number
  status = emitNumber(value, digits, spacePad)
  return status

op emitComposite "Add a conversion that stands for others (c D F r R T x X): the others are written into a block first, as glibc does, so the width pads the whole; 1, 0 when it did not fit, 2 when the character is no composite"
  input conv Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let templates String "%a %b %e %H:%M:%S %Y%m/%d/%y%Y-%m-%d%I:%M:%S %p%H:%M%H:%M:%S"
  let start Int64 0 mut
  let length Int64 0 mut
  let at Int64 0 mut
:begin
  space = workspace()
  when conv == 99 dateTime checkDate
:dateTime
  calc start := 0
  calc length := 20
  goto write
:checkDate
  calc isDate = conv == 68 || conv == 120
  when isDate date checkIso
:date
  calc start := 20
  calc length := 8
  goto write
:checkIso
  when conv == 70 iso checkClock
:iso
  calc start := 28
  calc length := 8
  goto write
:checkClock
  when conv == 114 clock12 checkShort
:clock12
  calc start := 36
  calc length := 11
  goto write
:checkShort
  when conv == 82 shortClock checkLong
:shortClock
  calc start := 47
  calc length := 5
  goto write
:checkLong
  calc isLong = conv == 84 || conv == 88
  when isLong longClock unknown
:longClock
  calc start := 52
  calc length := 8
  goto write
:unknown
  return 2
:write
  savedDst = machine.loadAddress(space + 616)
  savedLimit = machine.loadInt64(space + 624)
  savedWritten = machine.loadInt64(space + 632)
  savedPad = machine.loadInt64(space + 656)
  savedUpper = machine.loadInt64(space + 664)
  savedLower = machine.loadInt64(space + 672)
  savedWidth = machine.loadInt64(space + 680)
  savedHash = machine.loadInt64(space + 696)
  block = heap.take(512)
  machine.storeAddress(space + 616, block)
  machine.storeInt64(space + 624, 512)
  machine.storeInt64(space + 632, 0)
  machine.storeInt64(space + 656, 0)
  machine.storeInt64(space + 664, 0)
  machine.storeInt64(space + 672, 0)
  machine.storeInt64(space + 680, -1)
  machine.storeInt64(space + 696, 0)
  base = machine.addressOfString(templates)
  goto each
:each loop=while max=forever
  when at >= length expanded next
:next in=each
  letter = fetch(base, start + at)
  when letter == 37 conversion literal
:conversion in=each
  inner = fetch(base, start + at + 1)
  innerStatus = emitSimple(inner)
  calc at := at + 2
  goto each
:literal in=each
  literalStatus = emitChar(letter)
  calc at := at + 1
  goto each
:expanded
  produced = machine.loadInt64(space + 632)
  machine.storeAddress(space + 616, savedDst)
  machine.storeInt64(space + 624, savedLimit)
  machine.storeInt64(space + 632, savedWritten)
  machine.storeInt64(space + 656, savedPad)
  machine.storeInt64(space + 664, savedUpper)
  machine.storeInt64(space + 672, savedLower)
  machine.storeInt64(space + 680, savedWidth)
  machine.storeInt64(space + 696, savedHash)
  status = emitBytes(block, produced)
  heap.give(block)
  return status

op modifierAllows "Whether a conversion takes the E or O modifier glibc accepts: E before c C x X y Y, O before d e H I m M S u U V w W y (the modifier 0 is always accepted)"
  input conv Int64 copied
  input modifier Int64 copied
  output Bool
  let eList String "cCxXyY"
  let oList String "deHImMSuUVwWy"
  effect use machine.memory
  uses memoryAccess
:begin
  conv32 = convert.int64ToInt32(conv)
  when modifier == 0 plainModifier checkE
:plainModifier
  return true
:checkE
  when modifier == 69 searchE searchO
:searchE
  listE = machine.addressOfString(eList)
  foundE = clibrary.memoryFind(listE, conv32, 6)
  nowhereE = machine.zero()
  calc allowedE = foundE != nowhereE
  return allowedE
:searchO
  listO = machine.addressOfString(oList)
  foundO = clibrary.memoryFind(listO, conv32, 13)
  nowhereO = machine.zero()
  calc allowedO = foundO != nowhereO
  return allowedO

## ---------------------------------------------------------------- strftime: the format

op resetSpec "Clear the flags, the width (-1 for none), and the modifier of the conversion being written"
  effect use machine.memory
  uses memoryAccess
:begin
  space = workspace()
  machine.storeInt64(space + 656, 0)
  machine.storeInt64(space + 664, 0)
  machine.storeInt64(space + 672, 0)
  machine.storeInt64(space + 680, -1)
  machine.storeInt64(space + 688, 0)
  machine.storeInt64(space + 696, 0)
  return

op readSpec "Read the flags (_ - 0 ^ #), the width, and the E or O modifier after a % at an offset of the format into strftime's state; the offset of the conversion character"
  input fmt machine.Address copied
  input at Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let position Int64 0 mut
  let width Int64 0 mut
  let seen Int64 0 mut
:begin
  resetSpec()
  space = workspace()
  calc position := at + 1
  goto flagEach
:flagEach loop=while max=forever
  c = fetch(fmt, position)
  calc padFlag = c == 95 || c == 45 || c == 48
  when padFlag setPad upperCheck
:setPad in=flagEach
  machine.storeInt64(space + 656, c)
  calc position := position + 1
  goto flagEach
:upperCheck in=flagEach
  when c == 94 setUpper hashCheck
:setUpper in=flagEach
  machine.storeInt64(space + 664, 1)
  calc position := position + 1
  goto flagEach
:hashCheck in=flagEach
  when c == 35 setHash flagsDone
:setHash in=flagEach
  machine.storeInt64(space + 696, 1)
  calc position := position + 1
  goto flagEach
:flagsDone
  goto digitEach
:digitEach loop=while max=forever
  d = fetch(fmt, position)
  calc isDigit = d >= 48 && d <= 57
  when isDigit takeDigit digitsDone
:takeDigit in=digitEach
  calc seen := 1
  when width < 1000000000 grow skip
:grow in=digitEach
  calc width := width * 10 + d - 48
  goto skip
:skip in=digitEach
  calc position := position + 1
  goto digitEach
:digitsDone
  when seen == 1 storeWidth modifierPart
:storeWidth
  machine.storeInt64(space + 680, width)
  goto modifierPart
:modifierPart
  m = fetch(fmt, position)
  calc isModifier = m == 69 || m == 79
  when isModifier takeModifier done
:takeModifier
  machine.storeInt64(space + 688, m)
  calc position := position + 1
  goto done
:done
  return position

op formatLoop "Write a format and its conversions into strftime's output: ordinary characters as they are, and each % sequence as glibc writes it, or as it stands when it is no conversion; 1, or 0 when the output ran out"
  input fmt machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let status Int64 0 mut
:begin
  space = workspace()
  goto each
:each loop=while max=forever
  c = fetch(fmt, at)
  when c == 0 finished body
:body in=each
  when c == 37 spec literal
:literal in=each
  resetSpec()
  literalStatus = emitChar(c)
  when literalStatus == 0 failed nextChar
:nextChar in=each
  calc at := at + 1
  goto each
:spec in=each
  conversionAt = readSpec(fmt, at)
  conv = fetch(fmt, conversionAt)
  modifier = machine.loadInt64(space + 688)
  allowed = modifierAllows(conv, modifier)
  when allowed convertIt bad
:convertIt in=each
  calc composite = conv == 99 || conv == 68 || conv == 70 || conv == 114 || conv == 82 || conv == 84 || conv == 120 || conv == 88
  when composite compositeOne simpleOne
:compositeOne in=each
  compositeStatus = emitComposite(conv)
  calc status := compositeStatus
  goto judge
:simpleOne in=each
  simpleStatus = emitSimple(conv)
  calc status := simpleStatus
  goto judge
:judge in=each
  when status == 1 advance notOne
:advance in=each
  calc at := conversionAt + 1
  goto each
:notOne in=each
  when status == 0 failed bad
:bad in=each
  when conv == 0 badEnd badChar
:badChar in=each
  calc badLength = conversionAt - at + 1
  badStatus = emitBytes(fmt + at, badLength)
  when badStatus == 0 failed badNext
:badNext in=each
  calc at := conversionAt + 1
  goto each
:badEnd
  calc endLength = conversionAt - at
  endStatus = emitBytes(fmt + at, endLength)
  when endStatus == 0 failed finished
:finished
  return 1
:failed
  return 0

op formatTime "strftime: a struct tm written as a format says into a buffer of a size: the characters written without the 0 byte, or 0 when they and the 0 do not fit (ERANGE), what was written before the one that did not fit staying in the buffer"
  invariant formatsLikeGlibc "Writes the format's text as glibc's strftime does, or gives 0 when it does not fit"
  input buffer machine.Address copied
  input size Int64 copied
  input format machine.Address copied
  input tm machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "strftime"
  let limit Int64 0 mut
:begin
  space = workspace()
  calc limit := size
  when size < 0 hugeSize bounded
:hugeSize
  calc limit := 9223372036854775807
  goto bounded
:bounded
  machine.storeAddress(space + 616, buffer)
  machine.storeInt64(space + 624, limit)
  machine.storeInt64(space + 632, 0)
  machine.storeInt64(space + 640, 0)
  machine.storeAddress(space + 648, tm)
  done = formatLoop(format)
  when done == 0 failed finish
:failed
  return 0
:finish
  written = machine.loadInt64(space + 632)
  when limit > 0 terminate ending
:terminate
  machine.storeByte(buffer + written, 0)
  goto ending
:ending
  return written

@tests

## Tests write C strings in the heap and read the module's state directly. The zone is installed with parsePosix (a
## POSIX string) or parseTable (a TZif image built here from the model's transitions), so no test depends on the
## machine's own time zone, and their expected values are the models' of tests/ctimetour.py.

op cText "A C string in a new heap block: a text's bytes and a 0"
  input text String borrowed
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  bytes = string.byteLength(text)
  block = heap.take(bytes + 1)
  at = machine.addressOfString(text)
  machine.copy(block, at, bytes)
  return block

op hexValue "The value of a hexadecimal digit's character"
  input letter Int64 copied
  output Int64
  let value Int64 0 mut
:begin
  calc value := letter - 48
  when letter >= 97 lowerCase done
:lowerCase
  calc value := letter - 87
  goto done
:done
  return value

op putHex "Write the bytes a text of hexadecimal digit pairs names into a new heap block: the block"
  input text String borrowed
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  length = string.byteLength(text)
  block = heap.take(length / 2 + 1)
  goto each
:each loop=while max=length
  when at >= length finish next
:next in=each
  high = string.byteAtOrTrap(text, at)
  low = string.byteAtOrTrap(text, at + 1)
  highValue = hexValue(convert.byteToInt64(high))
  lowValue = hexValue(convert.byteToInt64(low))
  machine.storeByte(block + at / 2, convert.int64ToByte(highValue * 16 + lowValue))
  calc at := at + 2
  goto each
:finish
  return block

op tmIs "Whether a struct tm holds these nine ints"
  input tm machine.Address copied
  input sec Int64 copied
  input minute Int64 copied
  input hour Int64 copied
  input mday Int64 copied
  input mon Int64 copied
  input year Int64 copied
  input wday Int64 copied
  input yday Int64 copied
  input isdst Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
:begin
  a = fieldAt(tm, 0)
  b = fieldAt(tm, 4)
  c = fieldAt(tm, 8)
  d = fieldAt(tm, 12)
  e = fieldAt(tm, 16)
  f = fieldAt(tm, 20)
  g = fieldAt(tm, 24)
  h = fieldAt(tm, 28)
  i = fieldAt(tm, 32)
  calc same = a == sec && b == minute && c == hour && d == mday && e == mon && f == year && g == wday && h == yday && i == isdst
  return same

op gmtimeIs "Whether gmtime of a time gives these ints, the zone GMT, and gmtoff 0"
  input t Int64 copied
  input sec Int64 copied
  input minute Int64 copied
  input hour Int64 copied
  input mday Int64 copied
  input mon Int64 copied
  input year Int64 copied
  input wday Int64 copied
  input yday Int64 copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  tm = heap.take(64)
  result = gmtimeInto(t, tm)
  same = tmIs(tm, sec, minute, hour, mday, mon, year, wday, yday, 0)
  offset = machine.loadInt64(tm + 40)
  zone = machine.loadAddress(tm + 48)
  length = clibrary.cStringLength(zone)
  first = fetch(zone, 0)
  calc ok = result == tm && same && offset == 0 && length == 3 && first == 71
  heap.give(tm)
  return ok

op localIs "Whether the zone installed gives these ints, UTC offset, and abbreviation (by its length and first letter) for a time"
  input t Int64 copied
  input sec Int64 copied
  input minute Int64 copied
  input hour Int64 copied
  input mday Int64 copied
  input mon Int64 copied
  input year Int64 copied
  input wday Int64 copied
  input yday Int64 copied
  input isdst Int64 copied
  input gmtoff Int64 copied
  input abbrLength Int64 copied
  input abbrFirst Int64 copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  tm = heap.take(64)
  done = convertLocal(t, tm)
  same = tmIs(tm, sec, minute, hour, mday, mon, year, wday, yday, isdst)
  offset = machine.loadInt64(tm + 40)
  zone = machine.loadAddress(tm + 48)
  length = clibrary.cStringLength(zone)
  first = fetch(zone, 0)
  calc ok = done == 1 && same && offset == gmtoff && length == abbrLength && first == abbrFirst
  heap.give(tm)
  return ok

op makeGives "Whether mktime (for the zone installed, its memory of offsets cleared) of these fields gives a time and normalizes them"
  input sec Int64 copied
  input minute Int64 copied
  input hour Int64 copied
  input mday Int64 copied
  input mon Int64 copied
  input year Int64 copied
  input isdst Int64 copied
  input expected Int64 copied
  input resultHour Int64 copied
  input resultMday Int64 copied
  input resultMon Int64 copied
  input resultYear Int64 copied
  input resultWday Int64 copied
  input resultYday Int64 copied
  input resultIsdst Int64 copied
  input resultOffset Int64 copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  space = workspace()
  machine.storeInt64(space + 176, 0)
  tm = heap.take(64)
  machine.storeInt32(tm, convert.int64ToInt32(sec))
  machine.storeInt32(tm + 4, convert.int64ToInt32(minute))
  machine.storeInt32(tm + 8, convert.int64ToInt32(hour))
  machine.storeInt32(tm + 12, convert.int64ToInt32(mday))
  machine.storeInt32(tm + 16, convert.int64ToInt32(mon))
  machine.storeInt32(tm + 20, convert.int64ToInt32(year))
  machine.storeInt32(tm + 32, convert.int64ToInt32(isdst))
  t = makeTimeIn(tm)
  hourNow = fieldAt(tm, 8)
  mdayNow = fieldAt(tm, 12)
  monNow = fieldAt(tm, 16)
  yearNow = fieldAt(tm, 20)
  wdayNow = fieldAt(tm, 24)
  ydayNow = fieldAt(tm, 28)
  isdstNow = fieldAt(tm, 32)
  offsetNow = machine.loadInt64(tm + 40)
  calc ok = t == expected && hourNow == resultHour && mdayNow == resultMday && monNow == resultMon && yearNow == resultYear && wdayNow == resultWday && ydayNow == resultYday && isdstNow == resultIsdst && offsetNow == resultOffset
  heap.give(tm)
  return ok

op formatIs "Whether strftime of a format, for a struct tm, in a buffer of a size, writes exactly the expected text and its 0 byte (the buffer is filled with X first)"
  input tm machine.Address copied
  input format String borrowed
  input expected String borrowed
  input size Int64 copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  buffer = heap.take(size + 16)
  machine.fill(buffer, 88, size + 8)
  formatText = cText(format)
  written = formatTime(buffer, size, formatText, tm)
  expectedBytes = string.byteLength(expected)
  expectedAt = machine.addressOfString(expected)
  same = machine.compare(buffer, expectedAt, expectedBytes)
  terminator = fetch(buffer, expectedBytes)
  calc ok = written == expectedBytes && same == 0 && terminator == 0
  heap.give(buffer)
  heap.give(formatText)
  return ok

op formatOverflows "Whether strftime gives 0 for a buffer too small for a format and leaves what it wrote before the piece that did not fit"
  input tm machine.Address copied
  input format String borrowed
  input size Int64 copied
  input kept String borrowed
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  buffer = heap.take(size + 16)
  machine.fill(buffer, 88, size + 8)
  formatText = cText(format)
  written = formatTime(buffer, size, formatText, tm)
  keptBytes = string.byteLength(kept)
  keptAt = machine.addressOfString(kept)
  same = machine.compare(buffer, keptAt, keptBytes)
  following = fetch(buffer, keptBytes)
  calc ok = written == 0 && same == 0 && following == 88
  heap.give(buffer)
  heap.give(formatText)
  return ok

test gmtimeTest "gmtime breaks times down in UTC for leap days, the epoch, 2038, 1900, and years 1 and 9999 as Python calendar does, and a year that does not fit an int gives NULL"
  verifies gmtimeInto breaksDownUtc
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  verdict1 = gmtimeIs(0, 0, 0, 0, 1, 0, 70, 4, 0)
  test.assertTrue(verdict1)
  verdict2 = gmtimeIs(-1, 59, 59, 23, 31, 11, 69, 3, 364)
  test.assertTrue(verdict2)
  verdict3 = gmtimeIs(1, 1, 0, 0, 1, 0, 70, 4, 0)
  test.assertTrue(verdict3)
  verdict4 = gmtimeIs(951782400, 0, 0, 0, 29, 1, 100, 2, 59)
  test.assertTrue(verdict4)
  verdict5 = gmtimeIs(951868800, 0, 0, 0, 1, 2, 100, 3, 60)
  test.assertTrue(verdict5)
  verdict6 = gmtimeIs(2147483647, 7, 14, 3, 19, 0, 138, 2, 18)
  test.assertTrue(verdict6)
  verdict7 = gmtimeIs(2147483648, 8, 14, 3, 19, 0, 138, 2, 18)
  test.assertTrue(verdict7)
  verdict8 = gmtimeIs(-2208988800, 0, 0, 0, 1, 0, 0, 1, 0)
  test.assertTrue(verdict8)
  verdict9 = gmtimeIs(4102444800, 0, 0, 0, 1, 0, 200, 5, 0)
  test.assertTrue(verdict9)
  verdict10 = gmtimeIs(1709164800, 0, 0, 0, 29, 1, 124, 4, 59)
  test.assertTrue(verdict10)
  verdict11 = gmtimeIs(253402300799, 59, 59, 23, 31, 11, 8099, 5, 364)
  test.assertTrue(verdict11)
  verdict12 = gmtimeIs(-62135596800, 0, 0, 0, 1, 0, -1899, 1, 0)
  test.assertTrue(verdict12)
  verdict13 = gmtimeIs(1700000000, 20, 13, 22, 14, 10, 123, 2, 317)
  test.assertTrue(verdict13)
  verdict14 = gmtimeIs(-86400, 0, 0, 0, 31, 11, 69, 3, 364)
  test.assertTrue(verdict14)
  verdict15 = gmtimeIs(86399, 59, 59, 23, 1, 0, 70, 4, 0)
  test.assertTrue(verdict15)
  verdict16 = gmtimeIs(31535999, 59, 59, 23, 31, 11, 70, 4, 364)
  test.assertTrue(verdict16)
  verdict17 = gmtimeIs(1230768000, 0, 0, 0, 1, 0, 109, 4, 0)
  test.assertTrue(verdict17)
  verdict18 = gmtimeIs(4107542400, 0, 0, 0, 1, 2, 200, 1, 59)
  test.assertTrue(verdict18)
  verdict19 = gmtimeIs(1583020800, 0, 0, 0, 1, 2, 120, 0, 60)
  test.assertTrue(verdict19)
  tmBig = heap.take(64)
  nowhere = machine.zero()
  huge = gmtimeInto(9223372036854775807, tmBig)
  test.assertTrue(huge == nowhere)
  hugeNegative = gmtimeInto(-9223372036854775807, tmBig)
  test.assertTrue(hugeNegative == nowhere)
  lastYear = gmtimeInto(67768036191676799, tmBig)
  test.assertTrue(lastYear == tmBig)
  pastYear = gmtimeInto(67768036191676800, tmBig)
  test.assertTrue(pastYear == nowhere)
  heap.give(tmBig)
  return

test ruleZoneTest "A POSIX rule gives the standard and the daylight offset on either side of each change, in the northern and the southern hemisphere, and reads a quoted name and an offset with minutes"
  verifies parsePosix readsRule
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let northern String "EST5EDT,M3.2.0,M11.1.0"
  let southern String "AEST-10AEDT,M10.1.0,M4.1.0/3"
  let quoted String "<+0530>-5:30"
:begin
  northernText = cText(northern)
  parsePosix(northernText)
  verdict20 = localIs(1710053999, 59, 59, 1, 10, 2, 124, 0, 69, 0, -18000, 3, 69)
  test.assertTrue(verdict20)
  verdict21 = localIs(1710054000, 0, 0, 3, 10, 2, 124, 0, 69, 1, -14400, 3, 69)
  test.assertTrue(verdict21)
  verdict22 = localIs(1730613599, 59, 59, 1, 3, 10, 124, 0, 307, 1, -14400, 3, 69)
  test.assertTrue(verdict22)
  verdict23 = localIs(1730613600, 0, 0, 1, 3, 10, 124, 0, 307, 0, -18000, 3, 69)
  test.assertTrue(verdict23)
  verdict24 = localIs(0, 0, 0, 19, 31, 11, 69, 3, 364, 0, -18000, 3, 69)
  test.assertTrue(verdict24)
  verdict25 = localIs(1700000000, 20, 13, 17, 14, 10, 123, 2, 317, 0, -18000, 3, 69)
  test.assertTrue(verdict25)
  verdict26 = localIs(1720000000, 40, 46, 5, 3, 6, 124, 3, 184, 1, -14400, 3, 69)
  test.assertTrue(verdict26)
  verdict27 = localIs(-1, 59, 59, 18, 31, 11, 69, 3, 364, 0, -18000, 3, 69)
  test.assertTrue(verdict27)
  verdict28 = localIs(1262304000, 0, 0, 19, 31, 11, 109, 4, 364, 0, -18000, 3, 69)
  test.assertTrue(verdict28)
  verdict29 = localIs(1783000000, 40, 46, 9, 2, 6, 126, 4, 182, 1, -14400, 3, 69)
  test.assertTrue(verdict29)
  southernText = cText(southern)
  parsePosix(southernText)
  verdict30 = localIs(1712419199, 59, 59, 2, 7, 3, 124, 0, 97, 1, 39600, 4, 65)
  test.assertTrue(verdict30)
  verdict31 = localIs(1712419200, 0, 0, 2, 7, 3, 124, 0, 97, 0, 36000, 4, 65)
  test.assertTrue(verdict31)
  verdict32 = localIs(1712419201, 1, 0, 2, 7, 3, 124, 0, 97, 0, 36000, 4, 65)
  test.assertTrue(verdict32)
  verdict33 = localIs(1727542799, 59, 59, 2, 29, 8, 124, 0, 272, 0, 36000, 4, 65)
  test.assertTrue(verdict33)
  verdict34 = localIs(1727542800, 0, 0, 3, 29, 8, 124, 0, 272, 0, 36000, 4, 65)
  test.assertTrue(verdict34)
  verdict35 = localIs(1700000000, 20, 13, 9, 15, 10, 123, 3, 318, 1, 39600, 4, 65)
  test.assertTrue(verdict35)
  verdict36 = localIs(1720000000, 40, 46, 19, 3, 6, 124, 3, 184, 0, 36000, 4, 65)
  test.assertTrue(verdict36)
  verdict37 = localIs(0, 0, 0, 11, 1, 0, 70, 4, 0, 1, 39600, 4, 65)
  test.assertTrue(verdict37)
  verdict38 = localIs(1735603200, 0, 0, 11, 31, 11, 124, 2, 365, 1, 39600, 4, 65)
  test.assertTrue(verdict38)
  verdict39 = localIs(1704067200, 0, 0, 11, 1, 0, 124, 1, 0, 1, 39600, 4, 65)
  test.assertTrue(verdict39)
  quotedText = cText(quoted)
  parsePosix(quotedText)
  verdict40 = localIs(0, 0, 30, 5, 1, 0, 70, 4, 0, 0, 19800, 5, 43)
  test.assertTrue(verdict40)
  verdict41 = localIs(1700000000, 20, 43, 3, 15, 10, 123, 3, 318, 0, 19800, 5, 43)
  test.assertTrue(verdict41)
  verdict42 = localIs(-2208988800, 0, 30, 5, 1, 0, 0, 1, 0, 0, 19800, 5, 43)
  test.assertTrue(verdict42)
  heap.give(northernText)
  heap.give(southernText)
  heap.give(quotedText)
  return

test makeTimeTest "mktime normalizes out-of-range fields and sets tm_wday, tm_yday, tm_isdst, and tm_gmtoff as the model of gnulib search does, for EST5EDT"
  verifies makeTimeIn normalizes
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let northern String "EST5EDT,M3.2.0,M11.1.0"
:begin
  northernText = cText(northern)
  parsePosix(northernText)
  verdict43 = makeGives(0, 0, 12, 15, 5, 124, -1, 1718467200, 12, 15, 5, 124, 6, 166, 1, -14400)
  test.assertTrue(verdict43)
  verdict44 = makeGives(30, 59, 23, 31, 11, 99, -1, 946702770, 23, 31, 11, 99, 5, 364, 0, -18000)
  test.assertTrue(verdict44)
  verdict45 = makeGives(0, 0, 0, 1, 0, 70, -1, 18000, 0, 1, 0, 70, 4, 0, 0, -18000)
  test.assertTrue(verdict45)
  verdict46 = makeGives(59, 59, 23, 29, 1, 124, -1, 1709269199, 23, 29, 1, 124, 4, 59, 0, -18000)
  test.assertTrue(verdict46)
  verdict47 = makeGives(0, 0, 0, 32, 0, 124, -1, 1706763600, 0, 1, 1, 124, 4, 31, 0, -18000)
  test.assertTrue(verdict47)
  verdict48 = makeGives(0, 0, 0, 0, 2, 124, -1, 1709182800, 0, 29, 1, 124, 4, 59, 0, -18000)
  test.assertTrue(verdict48)
  verdict49 = makeGives(0, 0, 25, 28, 1, 123, -1, 1677650400, 1, 1, 2, 123, 3, 59, 0, -18000)
  test.assertTrue(verdict49)
  verdict50 = makeGives(70, 70, 70, 1, 13, 100, -1, 981259870, 23, 3, 1, 101, 6, 33, 0, -18000)
  test.assertTrue(verdict50)
  verdict51 = makeGives(0, 0, 0, 1, -1, 100, -1, 944024400, 0, 1, 11, 99, 3, 334, 0, -18000)
  test.assertTrue(verdict51)
  verdict52 = makeGives(-1, 0, 0, 1, 0, 100, -1, 946702799, 23, 31, 11, 99, 5, 364, 0, -18000)
  test.assertTrue(verdict52)
  verdict53 = makeGives(0, -1, 0, 1, 0, 100, -1, 946702740, 23, 31, 11, 99, 5, 364, 0, -18000)
  test.assertTrue(verdict53)
  verdict54 = makeGives(0, 0, 0, 1, 24, 100, -1, 1009861200, 0, 1, 0, 102, 2, 0, 0, -18000)
  test.assertTrue(verdict54)
  verdict55 = makeGives(0, 0, 12, 10, 2, 124, -1, 1710086400, 12, 10, 2, 124, 0, 69, 1, -14400)
  test.assertTrue(verdict55)
  verdict56 = makeGives(0, 0, 12, 3, 10, 124, -1, 1730653200, 12, 3, 10, 124, 0, 307, 0, -18000)
  test.assertTrue(verdict56)
  verdict57 = makeGives(0, 0, 12, 1, 0, 0, -1, -2208927600, 12, 1, 0, 0, 1, 0, 0, -18000)
  test.assertTrue(verdict57)
  verdict58 = makeGives(59, 59, 23, 31, 11, 137, -1, 2145934799, 23, 31, 11, 137, 4, 364, 0, -18000)
  test.assertTrue(verdict58)
  verdict59 = makeGives(0, 0, 12, 15, 0, 124, 1, 1705334400, 11, 15, 0, 124, 1, 14, 0, -18000)
  test.assertTrue(verdict59)
  verdict60 = makeGives(0, 0, 12, 15, 6, 124, 0, 1721062800, 13, 15, 6, 124, 1, 196, 1, -14400)
  test.assertTrue(verdict60)
  verdict61 = makeGives(0, 30, 2, 10, 2, 124, -1, 1710055800, 3, 10, 2, 124, 0, 69, 1, -14400)
  test.assertTrue(verdict61)
  verdict62 = makeGives(0, 30, 2, 10, 2, 124, 0, 1710055800, 3, 10, 2, 124, 0, 69, 1, -14400)
  test.assertTrue(verdict62)
  verdict63 = makeGives(0, 30, 2, 10, 2, 124, 1, 1710052200, 1, 10, 2, 124, 0, 69, 0, -18000)
  test.assertTrue(verdict63)
  verdict64 = makeGives(0, 30, 1, 3, 10, 124, 1, 1730611800, 1, 3, 10, 124, 0, 307, 1, -14400)
  test.assertTrue(verdict64)
  verdict65 = makeGives(0, 30, 1, 3, 10, 124, 0, 1730615400, 1, 3, 10, 124, 0, 307, 0, -18000)
  test.assertTrue(verdict65)
  direct = heap.take(64)
  machine.storeInt32(direct + 8, 12)
  machine.storeInt32(direct + 12, 1)
  machine.storeInt32(direct + 20, 124)
  madeDirect = makeTimeIn(direct)
  test.assertEqualInt64(1704128400, madeDirect)
  heap.give(direct)
  heap.give(northernText)
  return

test asctimeTest "asctime writes glibc 25 characters, pads the day to three columns, writes ??? for a weekday or month out of range, and gives NULL when 26 bytes do not hold the text"
  verifies asctimeInto writesText
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  tm = heap.take(64)
  buffer = heap.take(64)
  nowhere = machine.zero()
  machine.storeInt32(tm + 0, 0)
  machine.storeInt32(tm + 4, 0)
  machine.storeInt32(tm + 8, 0)
  machine.storeInt32(tm + 12, 1)
  machine.storeInt32(tm + 16, 0)
  machine.storeInt32(tm + 20, 70)
  machine.storeInt32(tm + 24, 4)
  machine.storeInt32(tm + 28, 0)
  machine.storeInt32(tm + 32, 0)
  result0 = asctimeInto(tm, buffer, 26)
  test.assertTrue(result0 == buffer)
  length0 = clibrary.cStringLength(buffer)
  test.assertEqualInt64(25, length0)
  expected0 = machine.addressOfString("Thu Jan  1 00:00:00 1970")
  same0 = machine.compare(buffer, expected0, 24)
  test.assertTrue(same0 == 0)
  last0 = fetch(buffer, 24)
  test.assertEqualInt64(10, last0)
  machine.storeInt32(tm + 0, 59)
  machine.storeInt32(tm + 4, 59)
  machine.storeInt32(tm + 8, 23)
  machine.storeInt32(tm + 12, 31)
  machine.storeInt32(tm + 16, 11)
  machine.storeInt32(tm + 20, 99)
  machine.storeInt32(tm + 24, 5)
  machine.storeInt32(tm + 28, 364)
  machine.storeInt32(tm + 32, 0)
  result1 = asctimeInto(tm, buffer, 26)
  test.assertTrue(result1 == buffer)
  length1 = clibrary.cStringLength(buffer)
  test.assertEqualInt64(25, length1)
  expected1 = machine.addressOfString("Fri Dec 31 23:59:59 1999")
  same1 = machine.compare(buffer, expected1, 24)
  test.assertTrue(same1 == 0)
  last1 = fetch(buffer, 24)
  test.assertEqualInt64(10, last1)
  machine.storeInt32(tm + 0, 5)
  machine.storeInt32(tm + 4, 4)
  machine.storeInt32(tm + 8, 3)
  machine.storeInt32(tm + 12, 9)
  machine.storeInt32(tm + 16, 5)
  machine.storeInt32(tm + 20, 124)
  machine.storeInt32(tm + 24, 0)
  machine.storeInt32(tm + 28, 160)
  machine.storeInt32(tm + 32, 0)
  result2 = asctimeInto(tm, buffer, 26)
  test.assertTrue(result2 == buffer)
  length2 = clibrary.cStringLength(buffer)
  test.assertEqualInt64(25, length2)
  expected2 = machine.addressOfString("Sun Jun  9 03:04:05 2024")
  same2 = machine.compare(buffer, expected2, 24)
  test.assertTrue(same2 == 0)
  last2 = fetch(buffer, 24)
  test.assertEqualInt64(10, last2)
  machine.storeInt32(tm + 0, 0)
  machine.storeInt32(tm + 4, 0)
  machine.storeInt32(tm + 8, 0)
  machine.storeInt32(tm + 12, 1)
  machine.storeInt32(tm + 16, 0)
  machine.storeInt32(tm + 20, 70)
  machine.storeInt32(tm + 24, 7)
  machine.storeInt32(tm + 28, 0)
  machine.storeInt32(tm + 32, 0)
  result3 = asctimeInto(tm, buffer, 26)
  test.assertTrue(result3 == buffer)
  length3 = clibrary.cStringLength(buffer)
  test.assertEqualInt64(25, length3)
  expected3 = machine.addressOfString("??? Jan  1 00:00:00 1970")
  same3 = machine.compare(buffer, expected3, 24)
  test.assertTrue(same3 == 0)
  last3 = fetch(buffer, 24)
  test.assertEqualInt64(10, last3)
  machine.storeInt32(tm + 0, 0)
  machine.storeInt32(tm + 4, 0)
  machine.storeInt32(tm + 8, 0)
  machine.storeInt32(tm + 12, 1)
  machine.storeInt32(tm + 16, 12)
  machine.storeInt32(tm + 20, 70)
  machine.storeInt32(tm + 24, -1)
  machine.storeInt32(tm + 28, 0)
  machine.storeInt32(tm + 32, 0)
  result4 = asctimeInto(tm, buffer, 26)
  test.assertTrue(result4 == buffer)
  length4 = clibrary.cStringLength(buffer)
  test.assertEqualInt64(25, length4)
  expected4 = machine.addressOfString("??? ???  1 00:00:00 1970")
  same4 = machine.compare(buffer, expected4, 24)
  test.assertTrue(same4 == 0)
  last4 = fetch(buffer, 24)
  test.assertEqualInt64(10, last4)
  machine.storeInt32(tm + 0, -5)
  machine.storeInt32(tm + 4, 0)
  machine.storeInt32(tm + 8, 0)
  machine.storeInt32(tm + 12, 1)
  machine.storeInt32(tm + 16, 0)
  machine.storeInt32(tm + 20, 70)
  machine.storeInt32(tm + 24, 4)
  machine.storeInt32(tm + 28, 0)
  machine.storeInt32(tm + 32, 0)
  result5 = asctimeInto(tm, buffer, 26)
  test.assertTrue(result5 == nowhere)
  machine.storeInt32(tm + 0, 0)
  machine.storeInt32(tm + 4, 0)
  machine.storeInt32(tm + 8, 0)
  machine.storeInt32(tm + 12, 1)
  machine.storeInt32(tm + 16, 0)
  machine.storeInt32(tm + 20, 8100)
  machine.storeInt32(tm + 24, 4)
  machine.storeInt32(tm + 28, 0)
  machine.storeInt32(tm + 32, 0)
  result6 = asctimeInto(tm, buffer, 26)
  test.assertTrue(result6 == nowhere)
  machine.storeInt32(tm + 0, 0)
  machine.storeInt32(tm + 4, 0)
  machine.storeInt32(tm + 8, 0)
  machine.storeInt32(tm + 12, 1)
  machine.storeInt32(tm + 16, 0)
  machine.storeInt32(tm + 20, -2000)
  machine.storeInt32(tm + 24, 4)
  machine.storeInt32(tm + 28, 0)
  machine.storeInt32(tm + 32, 0)
  result7 = asctimeInto(tm, buffer, 26)
  test.assertTrue(result7 == buffer)
  length7 = clibrary.cStringLength(buffer)
  test.assertEqualInt64(25, length7)
  expected7 = machine.addressOfString("Thu Jan  1 00:00:00 -100")
  same7 = machine.compare(buffer, expected7, 24)
  test.assertTrue(same7 == 0)
  last7 = fetch(buffer, 24)
  test.assertEqualInt64(10, last7)
  heap.give(tm)
  heap.give(buffer)
  return

test formatTest "strftime writes every conversion glibc has in the C locale, the flags _ - 0 ^ #, widths, and the E and O modifiers; text that does not fit stops it with 0 and what was written before stays"
  verifies formatTime formatsLikeGlibc
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  tm = heap.take(64)
  gmt = gmtimeInto(1710055800, tm)
  verdict66 = formatIs(tm, "%Y-%m-%d %H:%M:%S", "2024-03-10 07:30:00", 4096)
  test.assertTrue(verdict66)
  verdict67 = formatIs(tm, "%a %A %b %B %h", "Sun Sunday Mar March Mar", 4096)
  test.assertTrue(verdict67)
  verdict68 = formatIs(tm, "%c", "Sun Mar 10 07:30:00 2024", 4096)
  test.assertTrue(verdict68)
  verdict69 = formatIs(tm, "%D|%F|%r|%R|%T|%x|%X", "03/10/24|2024-03-10|07:30:00 AM|07:30|07:30:00|03/10/24|07:30:00", 4096)
  test.assertTrue(verdict69)
  verdict70 = formatIs(tm, "%C %y %g %G %V %U %W %u %w %j", "20 24 24 2024 10 10 10 7 0 070", 4096)
  test.assertTrue(verdict70)
  verdict71 = formatIs(tm, "%e|%k|%l|%I|%p|%P", "10| 7| 7|07|AM|am", 4096)
  test.assertTrue(verdict71)
  verdict72 = formatIs(tm, "%Z %z", "GMT +0000", 4096)
  test.assertTrue(verdict72)
  verdict73 = formatIs(tm, "%%", "%", 4096)
  test.assertTrue(verdict73)
  verdict74 = formatIs(tm, "%-d|%_d|%^a|%#b|%05e|%_5m|%10Y|%-H", "10|10|SUN|MAR|00010|    3|0000002024|7", 4096)
  test.assertTrue(verdict74)
  verdict75 = formatIs(tm, "%Ey %Od %EY %OH %Ec", "24 10 2024 07 Sun Mar 10 07:30:00 2024", 4096)
  test.assertTrue(verdict75)
  verdict76 = formatIs(tm, "%Q %E %Ed %", "%Q %E %Ed %", 4096)
  test.assertTrue(verdict76)
  verdict77 = formatIs(tm, "plain text", "plain text", 4096)
  test.assertTrue(verdict77)
  verdict78 = formatIs(tm, "", "", 4096)
  test.assertTrue(verdict78)
  verdict79 = formatIs(tm, "%10a|%-10a|%^B|%#Z|%^p|%#p", "       Sun|       Sun|MARCH|gmt|AM|am", 4096)
  test.assertTrue(verdict79)
  verdict80 = formatIs(tm, "%12c", "Sun Mar 10 07:30:00 2024", 4096)
  test.assertTrue(verdict80)
  verdict81 = formatOverflows(tm, "%Y-%m-%d", 8, "2024-03")
  test.assertTrue(verdict81)
  verdict82 = formatOverflows(tm, "ab%Yzz", 5, "ab")
  test.assertTrue(verdict82)
  verdict83 = formatOverflows(tm, "%Y", 4, "")
  test.assertTrue(verdict83)
  verdict84 = formatIs(tm, "%Y", "2024", 5)
  test.assertTrue(verdict84)
  verdict85 = formatOverflows(tm, "%A %B", 9, "Sunday ")
  test.assertTrue(verdict85)
  directBuffer = heap.take(64)
  directFormat = cText("%Y")
  writtenDirect = formatTime(directBuffer, 64, directFormat, tm)
  test.assertEqualInt64(4, writtenDirect)
  heap.give(tm)
  return

op tableAt "Whether the zone parsed from the TZif image gives an offset, a daylight flag, and an abbreviation of a length for a time"
  input t Int64 copied
  input offset Int64 copied
  input daylight Int64 copied
  input abbrLength Int64 copied
  input abbrFirst Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
:begin
  space = workspace()
  tableZone(t)
  gotOffset = machine.loadInt64(space + 448)
  gotDaylight = machine.loadInt64(space + 456)
  name = machine.loadAddress(space + 464)
  length = clibrary.cStringLength(name)
  first = fetch(name, 0)
  calc ok = gotOffset == offset && gotDaylight == daylight && length == abbrLength && first == abbrFirst
  return ok

test tableZoneTest "A TZif file (version 2, a few years of transitions and a POSIX footer) gives the type of the latest transition, the first standard type before the first, and the footer rule after the last"
  verifies parseTable readsTable
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let image String "545a696632000000000000000000000000000000000000000000000000000000000000000000000100000004ffffb9b0000045535400545a6966320000000000000000000000000000000000000000000000000000000000000a0000000200000008000000005e6497f0000000005f9e4ee000000000604db4700000000061876b6000000000622d96700000000063674d6000000000640d78700000000065472f600000000065ed5a70000000006727116001000100010001000100ffffb9b00000ffffc7c0010445535400454454000a455354354544542c4d332e322e302c4d31312e312e300a"
:begin
  data = putHex(image)
  parsed = parseTable(data, 232)
  test.assertEqualInt64(1, parsed)
  verdict86 = tableAt(0, -18000, 0, 3, 69)
  test.assertTrue(verdict86)
  verdict87 = tableAt(1583650799, -18000, 0, 3, 69)
  test.assertTrue(verdict87)
  verdict88 = tableAt(1583650800, -14400, 1, 3, 69)
  test.assertTrue(verdict88)
  verdict89 = tableAt(1604210399, -14400, 1, 3, 69)
  test.assertTrue(verdict89)
  verdict90 = tableAt(1604210400, -18000, 0, 3, 69)
  test.assertTrue(verdict90)
  verdict91 = tableAt(1615705200, -14400, 1, 3, 69)
  test.assertTrue(verdict91)
  verdict92 = tableAt(1586000000, -14400, 1, 3, 69)
  test.assertTrue(verdict92)
  verdict93 = tableAt(1730613599, -14400, 1, 3, 69)
  test.assertTrue(verdict93)
  verdict94 = tableAt(1730613600, -18000, 0, 3, 69)
  test.assertTrue(verdict94)
  verdict95 = tableAt(1730613601, -18000, 0, 3, 69)
  test.assertTrue(verdict95)
  verdict96 = tableAt(1900000000, -14400, 1, 3, 69)
  test.assertTrue(verdict96)
  verdict97 = tableAt(2100000000, -14400, 1, 3, 69)
  test.assertTrue(verdict97)
  verdict98 = tableAt(4102444800, -18000, 0, 3, 69)
  test.assertTrue(verdict98)
  verdict99 = tableAt(-2208988800, -18000, 0, 3, 69)
  test.assertTrue(verdict99)
  return


op wideText "A text as UTF-16 in a new heap block"
  input text String borrowed
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  length = string.byteLength(text)
  block = heap.take(length * 2 + 2)
  goto each
:each loop=while max=length
  when at >= length finish next
:next in=each
  letter = string.byteAtOrTrap(text, at)
  machine.storeByte(block + at * 2, letter)
  calc at := at + 1
  goto each
:finish
  return block

op nameBecomes "Whether copyName writes a zone name as the text expected"
  input text String borrowed
  input expected String borrowed
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  wide = wideText(text)
  dest = heap.take(16)
  copyName(wide, dest)
  length = clibrary.cStringLength(dest)
  expectedBytes = string.byteLength(expected)
  expectedAt = machine.addressOfString(expected)
  same = machine.compare(dest, expectedAt, expectedBytes)
  calc ok = length == expectedBytes && same == 0
  heap.give(wide)
  heap.give(dest)
  return ok

test nameTest "A Windows zone name is written as the capitals that start its words, and a short one as it is"
  verifies copyName abbreviates
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  wideDirect = wideText("Central Standard Time")
  buffer = heap.take(16)
  copyName(wideDirect, buffer)
  directLength = clibrary.cStringLength(buffer)
  test.assertEqualInt64(3, directLength)
  eastern = nameBecomes("Eastern Standard Time", "EST")
  test.assertTrue(eastern)
  daylight = nameBecomes("Eastern Daylight Time", "EDT")
  test.assertTrue(daylight)
  coordinated = nameBecomes("Coordinated Universal Time", "CUT")
  test.assertTrue(coordinated)
  short = nameBecomes("UTC", "UTC")
  test.assertTrue(short)
  single = nameBecomes("Greenwich", "Greenwich")
  test.assertTrue(single)
  long = nameBecomes("Abcdefghijklmnopqrstuvwxyz", "Abcdefghijklmno")
  test.assertTrue(long)
  return
