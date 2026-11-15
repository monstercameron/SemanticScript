module kernel "The operating system as the runtime reaches it: Windows through kernel32, Linux through system calls; memory from the system, Linux's clocks, and what a Linux process is started with"
  path kernel
  imports standard.machine standard.system standard.math standard.compare standard.logic standard.test
  exports stateAt initialStack argumentCount argumentVector environmentVector failed errnoOf mapMemory mapStack unmapMemory monotonic wallClock sleepFor

capability memoryAccess "Authority to keep what the process was started with in machine.state" use machine.memory none

capability systemCalls "Authority to take memory from the operating system, give it back, read its clocks, and sleep" use system.calls none

## D-138: every module that reaches the operating system asks `system.linux()`, a constant of the target, and takes
## the Windows path (kernel32's functions) or the Linux path (system calls); the backend drops the other. The calls
## many modules share are here. A Linux system call gives a negative errno when it fails (from -4095 to -1).
## machine.state bytes 832 to 895 belong to this module: 832 the address the Linux process started with its stack
## at (0 under `refined run`, and on Windows), 840 argc, 848 argv, 856 envp, 864 to 879 a struct timespec.
constant stackAt "Where the address of the stack the Linux process started with is kept, in machine.state" Int64 832

constant argcAt "Where argc is kept, in machine.state" Int64 840

constant argvAt "Where argv is kept, in machine.state" Int64 848

constant envpAt "Where envp is kept, in machine.state" Int64 856

constant timeAt "Where a struct timespec is put, in machine.state" Int64 864

## ---------------------------------------------------------------- state

op stateAt "The address of a byte of machine.state"
  invariant offsetsState "Gives machine.state's first byte moved on by the offset"
  input offset Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  findPlace: place = machine.offset(state, offset)
  return place

op initialStack "Keep what a Linux process was started with: the address of its stack, which holds argc, then argv's words and a 0, then envp's words and a 0"
  invariant keepsStart "argc, argv, and envp are read back as the stack holds them"
  input stack machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  findStack: stackSlot = stateAt(stackAt)
  storeStack: machine.storeAddress(stackSlot, stack)
  readCount: count = machine.loadInt64(stack)
  findCount: countSlot = stateAt(argcAt)
  storeCount: machine.storeInt64(countSlot, count)
  findVector: vector = machine.offset(stack, eight=8)
  findVectorSlot: vectorSlot = stateAt(argvAt)
  storeVector: machine.storeAddress(vectorSlot, vector)
  withEnd: words = math.addInt64(count, one=1)
  wordBytes: skip = math.multiplyInt64(words, eight)
  findEnvironment: environment = machine.offset(vector, skip)
  findEnvironmentSlot: environmentSlot = stateAt(envpAt)
  storeEnvironment: machine.storeAddress(environmentSlot, environment)
  return

op argumentCount "argc, as the Linux process was started (0 when it was not started by refined_entry)"
  invariant readsArgc "Gives the argc initialStack kept"
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findCount: countSlot = stateAt(argcAt)
  readCount: count = machine.loadInt64(countSlot)
  return count

op argumentVector "argv, as the Linux process was started (the address 0 when it was not started by refined_entry)"
  invariant readsArgv "Gives the argv initialStack kept"
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findVector: vectorSlot = stateAt(argvAt)
  readVector: vector = machine.loadAddress(vectorSlot)
  return vector

op environmentVector "envp, as the Linux process was started (the address 0 when it was not started by refined_entry)"
  invariant readsEnvp "Gives the envp initialStack kept"
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findEnvironment: environmentSlot = stateAt(envpAt)
  readEnvironment: environment = machine.loadAddress(environmentSlot)
  return environment

## ---------------------------------------------------------------- results

op failed "Whether a Linux system call's result is a failure: from -4095 to -1"
  invariant spotsFailure "-4095 to -1 fail; 0, positive results, and addresses do not"
  input result Int64 copied
  output Bool
:begin
  negativeCheck: negative = compare.lessThanInt64(result, zero=0)
  rangeCheck: inRange = compare.greaterThanInt64(result, lowest=-4096)
  bothCheck: isFailure = logic.and(negative, inRange)
  return isFailure

op errnoOf "The errno of a Linux system call's result: 0 when it did not fail"
  invariant givesErrno "A failed result gives its errno, any other 0"
  input result Int64 copied
  output Int64
  let noErrno Int64 0
:begin
  failedCheck: isFailure = failed(result)
  if isFailure giveErrno giveNone
:giveErrno
  negateIt: errno = math.negateInt64(result)
  return errno
:giveNone
  return noErrno

## ---------------------------------------------------------------- memory

op mapMemory "Zeroed memory of a number of bytes from the operating system, readable and writable (VirtualAlloc, or an anonymous mmap); the address 0 when there is none"
  invariant mapsZeroed "Gives zeroed memory that can be written, or the address 0"
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere: anywhere = machine.zero()
  osCheck: onLinux = system.linux()
  if onLinux linuxMap windowsMap
:linuxMap
  mapIt: mapped = system.mmap(anywhere, bytes, readWrite=3, privateAnonymous=34, noFile=-1, zero=0)
  failedCheck: refused = failed(mapped)
  if refused giveNothing giveMapped
:giveNothing
  return anywhere
:giveMapped
  addressOf: address = machine.fromInt64(mapped)
  return address
:windowsMap
  allocate: fresh = system.virtualAlloc(anywhere, bytes, commitAndReserve=12288, readWriteWindows=4)
  return fresh

op mapStack "Memory for a stack of a number of bytes on Linux, given pages only as they are touched (MAP_NORESERVE, MAP_STACK); the address 0 when there is none"
  invariant mapsStack "Gives memory that can be written at both ends, or the address 0"
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere: anywhere = machine.zero()
  mapIt: mapped = system.mmap(anywhere, bytes, readWrite=3, stackFlags=147490, noFile=-1, zero=0)
  failedCheck: refused = failed(mapped)
  if refused giveNothing giveMapped
:giveNothing
  return anywhere
:giveMapped
  addressOf: address = machine.fromInt64(mapped)
  return address

op unmapMemory "Give memory back to the operating system: all VirtualAlloc gave on Windows, the bytes from the address on Linux"
  invariant givesBack "The memory goes back to the operating system"
  input address machine.Address copied
  input bytes Int64 copied
  effect use system.calls
  uses systemCalls
:begin
  osCheck: onLinux = system.linux()
  if onLinux linuxUnmap windowsFree
:linuxUnmap
  unmapIt: unmapped = system.munmap(address, bytes)
  return
:windowsFree
  freeIt: freed = system.virtualFree(address, zero=0, releaseMemory=32768)
  return

## ---------------------------------------------------------------- Linux clocks and sleep

op readClock "Milliseconds on a Linux clock (CLOCK_REALTIME 0, CLOCK_MONOTONIC 1)"
  input clock Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findTime: time = stateAt(timeAt)
  readIt: status = system.clockGettime(clock, time)
  readSeconds: seconds = machine.loadInt64(time)
  findNanoseconds: nanosecondsSlot = machine.offset(time, eight=8)
  readNanoseconds: nanoseconds = machine.loadInt64(nanosecondsSlot)
  toMilliseconds: secondsPart = math.multiplyInt64(seconds, thousand=1000)
  fraction: nanosecondsPart = math.divideInt64(nanoseconds, million=1000000)
  sum: milliseconds = math.addInt64(secondsPart, nanosecondsPart)
  return milliseconds

op monotonic "Milliseconds on Linux's monotonic clock, which never goes back"
  invariant neverBack "A later reading is never smaller"
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readIt: milliseconds = readClock(monotonicClock=1)
  return milliseconds

op wallClock "Milliseconds since 1970 on Linux's real-time clock"
  invariant readsWall "Gives a time after 2020"
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readIt: milliseconds = readClock(realtimeClock=0)
  return milliseconds

op sleepFor "Sleep on Linux for a number of milliseconds (nanosleep)"
  invariant sleeps "The monotonic clock has moved on by at least the milliseconds when it returns"
  input milliseconds Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findTime: time = stateAt(timeAt)
  wholeSeconds: seconds = math.divideInt64(milliseconds, thousand=1000)
  leftOver: rest = math.remainderInt64(milliseconds, thousand)
  toNanoseconds: nanoseconds = math.multiplyInt64(rest, million=1000000)
  storeSeconds: machine.storeInt64(time, seconds)
  findNanoseconds: nanosecondsSlot = machine.offset(time, eight=8)
  storeNanoseconds: machine.storeInt64(nanosecondsSlot, nanoseconds)
  nowhere: anywhere = machine.zero()
  sleepIt: slept = system.nanosleep(time, anywhere)
  return

@tests

## Tests write in the last 4 KiB of machine.state (from byte 61440), which the runtime's own state never reaches.

test startTest "What a Linux process starts with is kept and read back: argc, argv after it, envp after argv's 0"
  verifies stateAt offsetsState
  verifies initialStack keepsStart
  verifies argumentCount readsArgc
  verifies argumentVector readsArgv
  verifies environmentVector readsEnvp
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  findScratch: scratch = stateAt(scratchAt=61440)
  findSame: same = machine.offset(state, scratchAt)
  sameCheck: isSame = machine.equal(scratch, same)
  expectSame: test.assertTrue(isSame)
  readOldStack: oldStack = stateAt(stackAt)
  findSaved: saved = stateAt(savedAt=61952)
  keepOld: machine.copy(saved, oldStack, thirtyTwo=32)
  storeCount: machine.storeInt64(scratch, two=2)
  keepIt: initialStack(scratch)
  readCount: count = argumentCount()
  expectCount: test.assertEqualInt64(two, count)
  readVector: vector = argumentVector()
  findVector: wantVector = machine.offset(scratch, eight=8)
  vectorCheck: vectorSame = machine.equal(vector, wantVector)
  expectVector: test.assertTrue(vectorSame)
  readEnvironment: environment = environmentVector()
  findEnvironment: wantEnvironment = machine.offset(scratch, thirtyTwo)
  environmentCheck: environmentSame = machine.equal(environment, wantEnvironment)
  expectEnvironment: test.assertTrue(environmentSame)
  restoreOld: machine.copy(oldStack, saved, thirtyTwo)
  return

test resultTest "A Linux system call's result fails from -4095 to -1, with its errno; others do not"
  verifies failed spotsFailure
  verifies errnoOf givesErrno
:begin
  failedTwo: twoFailed = failed(minusTwo=-2)
  expectTwo: test.assertTrue(twoFailed)
  failedLast: lastFailed = failed(minusLast=-4095)
  expectLast: test.assertTrue(lastFailed)
  failedBeyond: beyond = failed(minusBeyond=-4096)
  notBeyond: notIt = logic.not(beyond)
  expectBeyond: test.assertTrue(notIt)
  failedZero: zeroFailed = failed(zero=0)
  notZero: notZeroFailed = logic.not(zeroFailed)
  expectZero: test.assertTrue(notZeroFailed)
  errnoTwo: errno = errnoOf(minusTwo)
  expectErrno: test.assertEqualInt64(two=2, errno)
  errnoNone: noErrno = errnoOf(seven=7)
  expectNone: test.assertEqualInt64(zero, noErrno)
  return

test memoryTest "Memory from the system is zeroed and writable, and goes back; on Linux a stack's memory too, and the clocks and sleep"
  verifies mapMemory mapsZeroed
  verifies unmapMemory givesBack
  verifies mapStack mapsStack
  verifies monotonic neverBack
  verifies wallClock readsWall
  verifies sleepFor sleeps
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  mapIt: block = mapMemory(sixtyFourK=65536)
  findLast: lastAt = machine.offset(block, lastOffset=65528)
  readLast: lastValue = machine.loadInt64(lastAt)
  expectZeroed: test.assertEqualInt64(zero=0, lastValue)
  writeLast: machine.storeInt64(lastAt, answer=42)
  readAgain: again = machine.loadInt64(lastAt)
  expectWritten: test.assertEqualInt64(answer, again)
  giveIt: unmapMemory(block, sixtyFourK)
  osCheck: onLinux = system.linux()
  if onLinux linuxOnly done
:linuxOnly
  mapStackIt: stack = mapStack(sixtyFourK)
  writeFirst: machine.storeInt64(stack, answer)
  findStackLast: stackLast = machine.offset(stack, lastOffset)
  writeStackLast: machine.storeInt64(stackLast, answer)
  giveStack: unmapMemory(stack, sixtyFourK)
  readBefore: before = monotonic()
  sleepIt: sleepFor(twenty=20)
  readAfter: after = monotonic()
  waited: elapsed = math.subtractInt64(after, before)
  enoughCheck: enough = compare.greaterOrEqualInt64(elapsed, twenty)
  expectSlept: test.assertTrue(enough)
  readWall: wall = wallClock()
  recentCheck: recent = compare.greaterThanInt64(wall, year2020=1577836800000)
  expectRecent: test.assertTrue(recent)
  goto done
:done
  return
