module cthreads "threads.h for the runtime's C library: C11 threads on Linux's own threads (clone), mutexes, condition variables, thread-specific storage, and call_once, on futexes (D-166)"
  path cthreads
  imports standard.machine standard.system standard.math standard.compare standard.convert standard.bits standard.logic standard.test kernel heap clibrary
  exports none

capability memoryAccess "Authority to read and write threads' records, mutexes, and condition variables" use machine.memory none

capability systemCalls "Authority to start threads, wait on futexes, sleep, and yield" use system.calls none

## D-166: a thread (thrd_t, the address of its record: a heap block of 64 bytes: 0 its thread id, which the kernel
## clears and wakes when the thread ends (CLONE_CHILD_CLEARTID), 8 what it gave, 16 its stack, 24 the stack's size, 32
## its thread block, 40 whether it is detached, 48 the function, 56 its argument) runs on a stack of 8 MiB and a thread
## block of its own (the thread pointer: on x86_64 the stack protector's canary at 0x28, copied from the first
## thread's, and errno at 0x40). A mutex (mtx_t, glibc's 40 bytes) is 0 its state (0 free, 1 held, 2 held with
## waiters), 8 its owner's thread id, 16 how many times a recursive one is held, 24 its kind; a condition variable
## (cnd_t, 48 bytes) is 0 a sequence the waiters wait on. Thread-specific storage keeps 64 keys, each thread's values in
## its block from 0x80. On Windows (D-168) a thread is CreateThread's, its block in a thread-local slot, and waits
## block in the system (D-191): a mutex is 0 an SRW lock that guards it, 8 its owner, 16 its count, 24 its kind, 28
## its state (0 free, 1 held, 2 held with waiters), and 32 a condition variable its waiters sleep on; a condition
## variable is 0 a Windows condition variable, slept on with the mutex's guard; call_once's flags share one SRW lock
## and one condition variable.
## machine.state bytes 28480 to 28999 and 29000 to 29007 (the thread-local slot's index plus 1) belong to this module: 28480 the first thread's record, 28488 how many keys
## were made, 28496 the block of each key's destructor (64 keys), 28504 the block of the first thread's values, 28512
## call_once's SRW lock and 28520 its condition variable on Windows.
constant success "thrd_success: the call did what it was asked" Int32 0

constant busy "thrd_busy: another thread holds the mutex" Int32 1

constant error "thrd_error: the call could not do what it was asked" Int32 2

constant timedOut "thrd_timedout: the deadline passed first" Int32 4

constant stackBytes "A thread's stack: 8 MiB" Int64 8388608

constant forever "The bound of a loop that ends when its work does" Int64 9223372036854775807

constant firstRecordAt "Where the first thread's record is kept, in machine.state (0 until thrd_current asks)" Int64 28480

constant keysAt "Where how many thread-specific keys were made is kept, in machine.state" Int64 28488

constant destructorsAt "Where the block of each key's destructor is kept, in machine.state" Int64 28496

constant firstValuesAt "Where the block of the first thread's thread-specific values is kept, in machine.state" Int64 28504

## ---------------------------------------------------------------- futexes

op futexWait "Wait while a 32-bit cell holds a value, or until woken (FUTEX_WAIT, private); Linux only: Windows waits on SRW locks and condition variables (D-191)"
  input cell machine.Address copied
  input value Int32 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere = machine.zero()
  calc wideValue = convert.int32ToInt64(value)
  system.futex(cell, 128, wideValue, nowhere, nowhere, 0)
  return

op futexWaitShared "Wait while a 32-bit cell holds a value, or until woken, with FUTEX_WAIT not private: the wake the kernel gives a thread's cleared tid (CLONE_CHILD_CLEARTID) is not private, and a private wait never hears it; Linux only"
  input cell machine.Address copied
  input value Int32 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere = machine.zero()
  calc wideValue = convert.int32ToInt64(value)
  system.futex(cell, 0, wideValue, nowhere, nowhere, 0)
  return

op futexWake "Wake up to a count of threads waiting on a cell (FUTEX_WAKE, private); Linux only"
  input cell machine.Address copied
  input count Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere = machine.zero()
  system.futex(cell, 129, count, nowhere, nowhere, 0)
  return

op exchange32 "Compare and exchange a 32-bit cell's value (seq_cst): the value it held"
  input cell machine.Address copied
  input expected Int32 copied
  input desired Int32 copied
  output Int32
  effect use machine.memory
  uses memoryAccess
:begin
  old = machine.compareExchange32(cell, expected, desired)
  return old

## ---------------------------------------------------------------- threads

op currentRecord "The running thread's record: from its thread block (D-166, D-168), the first thread's (made when first asked) for a thread with none"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  firstCell = kernel.stateAt(firstRecordAt)
  first = machine.loadAddress(firstCell)
  nowhere = machine.zero()
  when first == nowhere makeFirst known
:makeFirst
  made = heap.take(64)
  machine.storeAddress(firstCell, made)
  goto known
:known
  block = ownBlock()
  when block == nowhere firstThread fromBlock
:firstThread
  firstNow = machine.loadAddress(firstCell)
  return firstNow
:fromBlock
  calc recordAt = block + 56
  record = machine.loadAddress(recordAt)
  when record == nowhere firstThread own
:own
  return record

op threadMain "Where a new thread starts: on Windows its block goes in the thread-local slot first; then its function runs with its argument, what it gives is kept, and its thread-specific values' destructors run; on Linux the routine then ends the thread, on Windows returning ends it"
  input record machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_c_thread_main"
:begin
  onLinux = system.posix()
  if onLinux run slot
:slot
  slotCell = kernel.stateAt(29000)
  index = machine.loadInt64(slotCell)
  calc blockAt = record + 32
  block = machine.loadAddress(blockAt)
  system.tlsSetValue(clibrary.lowInt32(index - 1), block)
  goto run
:run
  calc functionAt = record + 48
  function = machine.loadAddress(functionAt)
  calc argumentAt = record + 56
  argument = machine.loadAddress(argumentAt)
  result = machine.callComparison(function, argument, argument)
  calc resultAt = record + 8
  machine.storeInt32(resultAt, result)
  runDestructors()
  return

op createThread "thrd_create: start a thread running func(arg) with a thread block of its own: on Linux by clone on a stack of 8 MiB, on Windows by CreateThread; thrd_success with the thread stored, thrd_nomem with no memory, thrd_error when the system refuses"
  invariant startsThreads "The function runs in a thread of its own, with its argument"
  input thread machine.Address copied
  input function machine.Address copied
  input argument machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "thrd_create"
  let noMemory Int32 3
:begin
  heap.startThreads()
  record = heap.take(64)
  nowhere = machine.zero()
  block = heap.take(640)
  machine.storeAddress(block, block)
  calc selfAt = block + 16
  machine.storeAddress(selfAt, block)
  calc recordAt = block + 56
  machine.storeAddress(recordAt, record)
  calc blockAt = record + 32
  machine.storeAddress(blockAt, block)
  calc functionAt = record + 48
  machine.storeAddress(functionAt, function)
  calc argumentAt = record + 56
  machine.storeAddress(argumentAt, argument)
  onLinux = system.posix()
  if onLinux linux windows
:windows
  slotCell = kernel.stateAt(29000)
  slot = machine.loadInt64(slotCell)
  when slot == 0 allocateSlot startWindows
:allocateSlot
  index = system.tlsAlloc()
  calc stored = convert.int32ToInt64(index) + 1
  machine.storeInt64(slotCell, stored)
  goto startWindows
:startWindows
  entry = machine.threadEntry()
  handle = system.createThread(nowhere, stackBytes, entry, record, 0, nowhere)
  when handle == nowhere windowsFailed windowsMade
:windowsFailed
  heap.give(block)
  heap.give(record)
  return error
:windowsMade
  calc handleAt = record + 16
  machine.storeAddress(handleAt, handle)
  machine.storeAddress(thread, record)
  return success
:linux
  stack = kernel.mapStack(stackBytes)
  when stack == nowhere noStack made
:noStack
  heap.give(block)
  heap.give(record)
  return noMemory
:made
  firstBlockCell = kernel.stateAt(2352)
  firstBlock = machine.loadAddress(firstBlockCell)
  when firstBlock == nowhere fill canary
:canary
  calc fromAt = firstBlock + 40
  calc toAt = block + 40
  machine.copy(toAt, fromAt, 8)
  goto fill
:fill
  calc stackAt = record + 16
  machine.storeAddress(stackAt, stack)
  calc sizeAt = record + 24
  machine.storeInt64(sizeAt, stackBytes)
  calc top = stack + stackBytes
  started = machine.startThread(top, block, record, record)
  when started < 0 failed done
:failed
  kernel.unmapMemory(stack, stackBytes)
  heap.give(block)
  heap.give(record)
  return error
:done
  machine.storeAddress(thread, record)
  return success

op joinThread "thrd_join: wait for a thread to end (its id cleared on Linux, its handle signalled on Windows), store what it gave, and free its stack, block, and record"
  invariant givesResult "Waits for the thread and gives what its function gave"
  input thread machine.Address copied
  input result machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "thrd_join"
:begin
  onLinux = system.posix()
  if onLinux waiting windows
:windows
  calc handleAt = thread + 16
  handle = machine.loadAddress(handleAt)
  system.waitForSingleObject(handle, -1)
  system.closeHandle(handle)
  goto ended
:waiting loop=while max=forever
  tid = machine.loadInt32(thread)
  when tid == 0 linuxEnded wait
:wait in=waiting
  futexWaitShared(thread, tid)
  goto waiting
:linuxEnded
  calc stackAt = thread + 16
  stack = machine.loadAddress(stackAt)
  kernel.unmapMemory(stack, stackBytes)
  goto ended
:ended
  nowhere = machine.zero()
  when result == nowhere release store
:store
  calc resultAt = thread + 8
  value = machine.loadInt32(resultAt)
  machine.storeInt32(result, value)
  goto release
:release
  calc blockAt = thread + 32
  block = machine.loadAddress(blockAt)
  heap.give(block)
  heap.give(thread)
  return success

op exitThread "thrd_exit: run the running thread's thread-specific destructors and end it, giving a result to thrd_join"
  input result Int32 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "thrd_exit"
:begin
  record = currentRecord()
  calc resultAt = record + 8
  machine.storeInt32(resultAt, result)
  runDestructors()
  onLinux = system.posix()
  if onLinux linux windows
:linux
  system.exit(0)
  return
:windows
  system.exitThread(0)
  return

op currentThread "thrd_current: the running thread"
  invariant knowsItself "Gives the same thread each time a thread asks"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "thrd_current"
:begin
  record = currentRecord()
  return record

op sameThread "thrd_equal: nonzero when two threads are one"
  input left machine.Address copied
  input right machine.Address copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "thrd_equal"
  let yes Int32 1
  let no Int32 0
:begin
  when left == right same differ
:same
  return yes
:differ
  return no

op detachThread "thrd_detach: the thread's stack and record are not freed by a join (they stay until the process ends)"
  input thread machine.Address copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "thrd_detach"
:begin
  calc detachedAt = thread + 40
  machine.storeInt64(detachedAt, 1)
  return success

op yieldThread "thrd_yield: let another thread run (sched_yield, SwitchToThread)"
  effect use system.calls
  uses systemCalls
  abi library "thrd_yield"
:begin
  onLinux = system.posix()
  if onLinux linux windows
:linux
  system.schedYield()
  return
:windows
  system.switchToThread()
  return

op sleepThread "thrd_sleep: sleep for a timespec: 0, or -1 when interrupted (the time left stored), -2 for another failure"
  input duration machine.Address copied
  input remaining machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "thrd_sleep"
  let interrupted Int32 -1
  let other Int32 -2
:begin
  onLinux = system.posix()
  if onLinux linux windows
:linux
  result = system.nanosleep(duration, remaining)
  when result == 0 slept notSlept
:notSlept
  when result == -4 stopped failed
:stopped
  return interrupted
:failed
  return other
:windows
  seconds = machine.loadInt64(duration)
  calc nanosAt = duration + 8
  nanos = machine.loadInt64(nanosAt)
  calc milliseconds = clibrary.lowInt32(seconds * 1000 + nanos / 1000000)
  system.sleep(milliseconds)
  goto slept
:slept
  return success

## ---------------------------------------------------------------- mutexes

op threadId "The running thread's id: gettid on Linux, GetCurrentThreadId on Windows"
  output Int64
  effect use system.calls
  uses systemCalls
:begin
  onLinux = system.posix()
  if onLinux linux windows
:linux
  id = system.gettid()
  return id
:windows
  windowsId = system.getCurrentThreadId()
  calc wideId = convert.int32ToInt64(windowsId)
  return wideId

op initMutex "mtx_init: a free mutex of a kind (mtx_plain 0, mtx_recursive 1, mtx_timed 2, or recursive and timed)"
  input mutex machine.Address copied
  input kind Int32 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "mtx_init"
:begin
  machine.fill(mutex, 0, 40)
  calc kindAt = mutex + 24
  machine.storeInt32(kindAt, kind)
  onLinux = system.posix()
  if onLinux done windows
:windows
  system.initializeSRWLock(mutex)
  calc freedAt = mutex + 32
  system.initializeConditionVariable(freedAt)
  goto done
:done
  return success

op lockMutex "mtx_lock: take a mutex, waiting while another thread holds it; a recursive one its holder takes again"
  invariant excludesOthers "While one holds a plain mutex no other take succeeds; a recursive one is taken again by its holder"
  input mutex machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "mtx_lock"
:begin
  self = threadId()
  calc ownerAt = mutex + 8
  calc countAt = mutex + 16
  calc kindAt = mutex + 24
  kind = machine.loadInt32(kindAt)
  holder = machine.loadInt64(ownerAt)
  when (kind & 1) == 1 && holder == self again take
:again
  count = machine.loadInt64(countAt)
  machine.storeInt64(countAt, count + 1)
  return success
:take
  onLinux = system.posix()
  if onLinux linux windows
:windows
  nowhere = machine.zero()
  windowsLock(mutex, nowhere)
  goto held
:linux
  first = exchange32(mutex, 0, 1)
  when first == 0 held contended
:contended loop=while max=forever
  previous = exchange32(mutex, 1, 2)
  when previous == 0 retake waitTurn
:waitTurn in=contended
  futexWait(mutex, 2)
  goto retake
:retake in=contended
  taken = exchange32(mutex, 0, 2)
  when taken == 0 held contended
:held
  machine.storeInt64(ownerAt, self)
  machine.storeInt64(countAt, 1)
  return success

op tryLockMutex "mtx_trylock: take a mutex if no other thread holds it: thrd_success, or thrd_busy"
  input mutex machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "mtx_trylock"
:begin
  self = threadId()
  calc ownerAt = mutex + 8
  calc countAt = mutex + 16
  calc kindAt = mutex + 24
  kind = machine.loadInt32(kindAt)
  holder = machine.loadInt64(ownerAt)
  when (kind & 1) == 1 && holder == self again take
:again
  count = machine.loadInt64(countAt)
  machine.storeInt64(countAt, count + 1)
  return success
:take
  onLinux = system.posix()
  if onLinux linux windows
:windows
  got = windowsTryLock(mutex)
  if got held taken
:linux
  first = exchange32(mutex, 0, 1)
  when first == 0 held taken
:taken
  return busy
:held
  machine.storeInt64(ownerAt, self)
  machine.storeInt64(countAt, 1)
  return success

op timedLockMutex "mtx_timedlock: take a mutex, waiting while another thread holds it until a deadline (a timespec of TIME_UTC): thrd_success, or thrd_timedout when the deadline passes first"
  invariant stopsAtDeadline "A mutex held elsewhere is given up on once the deadline has passed"
  input mutex machine.Address copied
  input deadline machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "mtx_timedlock"
:begin
  self = threadId()
  calc ownerAt = mutex + 8
  calc countAt = mutex + 16
  calc kindAt = mutex + 24
  kind = machine.loadInt32(kindAt)
  holder = machine.loadInt64(ownerAt)
  when (kind & 1) == 1 && holder == self again take
:again
  count = machine.loadInt64(countAt)
  machine.storeInt64(countAt, count + 1)
  return success
:take
  onLinux = system.posix()
  if onLinux linux windows
:windows
  got = windowsLock(mutex, deadline)
  if got held giveUp
:linux
  first = exchange32(mutex, 0, 1)
  when first == 0 held contended
:contended loop=while max=forever
  previous = exchange32(mutex, 1, 2)
  when previous == 0 retake waitTurn
:waitTurn in=contended
  late = deadlineWait(mutex, 2, deadline)
  if late giveUp retake
:retake in=contended
  taken = exchange32(mutex, 0, 2)
  when taken == 0 held contended
:giveUp
  return timedOut
:held
  machine.storeInt64(ownerAt, self)
  machine.storeInt64(countAt, 1)
  return success

op unlockMutex "mtx_unlock: give a mutex back (a recursive one when its count comes to 0), waking a waiter"
  input mutex machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "mtx_unlock"
:begin
  calc ownerAt = mutex + 8
  calc countAt = mutex + 16
  count = machine.loadInt64(countAt)
  when count > 1 down free
:down
  machine.storeInt64(countAt, count - 1)
  return success
:free
  machine.storeInt64(countAt, 0)
  machine.storeInt64(ownerAt, 0)
  onLinux = system.posix()
  if onLinux linux windows
:windows
  windowsUnlock(mutex)
  return success
:linux
  previous = exchange32(mutex, 1, 0)
  when previous == 1 done contended
:contended
  exchange32(mutex, 2, 0)
  futexWake(mutex, 1)
  return success
:done
  return success

op destroyMutex "mtx_destroy: nothing to give back"
  input mutex machine.Address copied
  abi library "mtx_destroy"
:begin
  return

op windowsLock "Take a mutex on Windows (D-191): under its guard (the SRW lock at 0), sleep on its condition variable (at 32) while it is held (28: 0 free, 1 held, 2 held with waiters), then mark it held; with a deadline (a TIME_UTC timespec, or the address 0 for none) give up once the deadline has passed. Whether it was taken"
  invariant waitsBlocked "Takes a free mutex at once; one held elsewhere is taken when given back, or given up on at the deadline"
  input mutex machine.Address copied
  input deadline machine.Address copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let mark Int32 1 mut
:begin
  calc heldAt = mutex + 28
  calc freedAt = mutex + 32
  nowhere = machine.zero()
  system.acquireSRWLockExclusive(mutex)
  goto look
:look loop=while max=forever
  state = machine.loadInt32(heldAt)
  when state == 0 take wait
:wait in=look
  machine.storeInt32(heldAt, 2)
  set mark 2
  when deadline == nowhere sleep timed
:sleep in=look
  system.sleepConditionVariableSRW(freedAt, mutex, -1, 0)
  goto look
:timed in=look
  left = waitMilliseconds(deadline)
  when left <= 0 late sleepTimed
:sleepTimed in=look
  system.sleepConditionVariableSRW(freedAt, mutex, clibrary.lowInt32(left), 0)
  goto look
:late
  system.releaseSRWLockExclusive(mutex)
  return false
:take
  machine.storeInt32(heldAt, mark)
  system.releaseSRWLockExclusive(mutex)
  return true

op windowsTryLock "Take a mutex on Windows if it is free (D-191), under its guard. Whether it was taken"
  input mutex machine.Address copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc heldAt = mutex + 28
  system.acquireSRWLockExclusive(mutex)
  state = machine.loadInt32(heldAt)
  when state == 0 take busyNow
:take
  machine.storeInt32(heldAt, 1)
  system.releaseSRWLockExclusive(mutex)
  return true
:busyNow
  system.releaseSRWLockExclusive(mutex)
  return false

op windowsUnlock "Give a mutex back on Windows (D-191): under its guard mark it free, then wake one of its waiters when it has any"
  input mutex machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc heldAt = mutex + 28
  calc freedAt = mutex + 32
  system.acquireSRWLockExclusive(mutex)
  state = machine.loadInt32(heldAt)
  machine.storeInt32(heldAt, 0)
  system.releaseSRWLockExclusive(mutex)
  when state == 2 wake done
:wake
  system.wakeConditionVariable(freedAt)
  return
:done
  return

op windowsNow "The real-time clock on Windows: nanoseconds since 1970 (GetSystemTimeAsFileTime)"
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  clock = heap.take(8)
  system.getSystemTimeAsFileTime(clock)
  ticks = machine.loadInt64(clock)
  heap.give(clock)
  calc now = (ticks - 116444736000000000) * 100
  return now

op waitMilliseconds "How long a Windows wait may sleep before a deadline (a TIME_UTC timespec): the milliseconds left rounded up, at most 2147483647, and 0 once it has passed (D-191)"
  invariant roundsUp "Gives 0 for a deadline passed and at least one millisecond for one still ahead"
  input deadline machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  seconds = machine.loadInt64(deadline)
  when seconds > 9000000000 far near
:far
  return 2147483647
:near
  when seconds < 0 passed known
:known
  calc nanosAt = deadline + 8
  nanos = machine.loadInt64(nanosAt)
  now = windowsNow()
  calc left = seconds * 1000000000 + nanos - now
  when left <= 0 passed ahead
:passed
  return 0
:ahead
  calc millis = (left + 999999) / 1000000
  when millis > 2147483647 far fits
:fits
  return millis

## ---------------------------------------------------------------- condition variables

op initCondition "cnd_init: a condition variable no thread waits on"
  input condition machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "cnd_init"
:begin
  machine.fill(condition, 0, 48)
  onLinux = system.posix()
  if onLinux done windows
:windows
  system.initializeConditionVariable(condition)
  goto done
:done
  return success

op waitCondition "cnd_wait: give a mutex back, wait until signalled, and take it again"
  input condition machine.Address copied
  input mutex machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "cnd_wait"
:begin
  onLinux = system.posix()
  if onLinux linux windows
:windows
  nowhere = machine.zero()
  windowsWait(condition, mutex, nowhere)
  return success
:linux
  sequence = machine.loadInt32(condition)
  unlockMutex(mutex)
  futexWait(condition, sequence)
  lockMutex(mutex)
  return success

op timedWaitCondition "cnd_timedwait: give a mutex back, wait until signalled or a deadline (a timespec of TIME_UTC) passes, and take it again: thrd_success, or thrd_timedout"
  invariant waitsUntilDeadline "A wait no signal ends gives thrd_timedout once the deadline has passed"
  input condition machine.Address copied
  input mutex machine.Address copied
  input deadline machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "cnd_timedwait"
:begin
  onLinux = system.posix()
  if onLinux linux windows
:windows
  windowsLate = windowsWait(condition, mutex, deadline)
  if windowsLate giveUp done
:linux
  sequence = machine.loadInt32(condition)
  unlockMutex(mutex)
  late = deadlineWait(condition, sequence, deadline)
  lockMutex(mutex)
  if late giveUp done
:giveUp
  return timedOut
:done
  return success

op deadlineWait "Wait while a 32-bit cell holds a value, or until woken, but not past a deadline (a timespec of the real-time clock): a futex wait on the bitset with CLOCK_REALTIME, which takes the deadline itself. Whether the deadline passed; Linux only"
  input cell machine.Address copied
  input value Int32 copied
  input deadline machine.Address copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere = machine.zero()
  calc wideValue = convert.int32ToInt64(value)
  result = system.futex(cell, 393, wideValue, deadline, nowhere, 4294967295)
  calc late = result == -110
  return late

op windowsWait "cnd_wait and cnd_timedwait on Windows (D-191): under the mutex's guard, give the mutex back (waking one of its waiters), sleep on the condition variable, which lets the guard go while asleep, so no signal given after the mutex is taken again is missed, then take the mutex again; with a deadline (a TIME_UTC timespec, or the address 0 for none) the sleep ends by then. A recursive mutex is given back whole and its count restored. Whether the deadline passed"
  invariant givesBackAndWaits "Gives the mutex back while asleep and holds it again when it returns; a deadline that passes unsignalled gives true"
  input condition machine.Address copied
  input mutex machine.Address copied
  input deadline machine.Address copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let late Bool false mut
:begin
  calc ownerAt = mutex + 8
  calc countAt = mutex + 16
  calc heldAt = mutex + 28
  calc freedAt = mutex + 32
  holder = machine.loadInt64(ownerAt)
  count = machine.loadInt64(countAt)
  machine.storeInt64(countAt, 0)
  machine.storeInt64(ownerAt, 0)
  nowhere = machine.zero()
  system.acquireSRWLockExclusive(mutex)
  state = machine.loadInt32(heldAt)
  machine.storeInt32(heldAt, 0)
  when state == 2 wakeOne asleep
:wakeOne
  system.wakeConditionVariable(freedAt)
  goto asleep
:asleep
  when deadline == nowhere untimed timed
:untimed
  system.sleepConditionVariableSRW(condition, mutex, -1, 0)
  goto look
:timed loop=while max=forever
  left = waitMilliseconds(deadline)
  when left <= 0 passed sleepTimed
:sleepTimed in=timed
  woke = system.sleepConditionVariableSRW(condition, mutex, clibrary.lowInt32(left), 0)
  when woke == 0 timed look
:passed
  set late true
  goto look
:look loop=while max=forever
  now = machine.loadInt32(heldAt)
  when now == 0 take waitMutex
:waitMutex in=look
  machine.storeInt32(heldAt, 2)
  system.sleepConditionVariableSRW(freedAt, mutex, -1, 0)
  goto look
:take
  machine.storeInt32(heldAt, 2)
  system.releaseSRWLockExclusive(mutex)
  machine.storeInt64(ownerAt, holder)
  machine.storeInt64(countAt, count)
  return late

op signalCondition "cnd_signal: wake one waiter"
  input condition machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "cnd_signal"
:begin
  onLinux = system.posix()
  if onLinux linux windows
:windows
  system.wakeConditionVariable(condition)
  return success
:linux
  bumpSequence(condition)
  futexWake(condition, 1)
  return success

op broadcastCondition "cnd_broadcast: wake every waiter"
  input condition machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "cnd_broadcast"
:begin
  onLinux = system.posix()
  if onLinux linux windows
:windows
  system.wakeAllConditionVariable(condition)
  return success
:linux
  bumpSequence(condition)
  futexWake(condition, 2147483647)
  return success

op bumpSequence "Move a condition variable's sequence on, atomically"
  input condition machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  goto attempt
:attempt loop=while max=forever
  current = machine.loadInt32(condition)
  calc next = clibrary.lowInt32(convert.int32ToInt64(current) + 1)
  previous = exchange32(condition, current, next)
  when previous == current done attempt
:done
  return

op destroyCondition "cnd_destroy: nothing to give back"
  input condition machine.Address copied
  abi library "cnd_destroy"
:begin
  return

## ---------------------------------------------------------------- once

op callOnce "call_once: call a function the first time a flag is passed, the other callers waiting until it returns"
  input flag machine.Address copied
  input function machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "call_once"
:begin
  onLinux = system.posix()
  if onLinux linux windows
:windows
  windowsOnce(flag, function)
  return
:linux
  previous = exchange32(flag, 0, 1)
  when previous == 0 call wait
:call
  nowhere = machine.zero()
  machine.callWithAddress(function, nowhere)
  exchange32(flag, 1, 2)
  futexWake(flag, 2147483647)
  return
:wait loop=while max=forever
  state = exchange32(flag, 2, 2)
  when state == 2 done sleep
:sleep in=wait
  futexWait(flag, 1)
  goto wait
:done
  return

op windowsOnce "call_once on Windows (D-191): a flag that is not done yet is looked at under one SRW lock all flags share (machine.state 28512); the first caller marks it running and calls the function without the lock, the others sleep on one condition variable (28520) until a caller marks it done and wakes them all"
  invariant callsOnce "Calls the function the first time a flag is passed; a later caller returns once it has returned"
  input flag machine.Address copied
  input function machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  first = exchange32(flag, 2, 2)
  when first == 2 finished guard
:guard
  lockAt = kernel.stateAt(28512)
  wakeAt = kernel.stateAt(28520)
  system.acquireSRWLockExclusive(lockAt)
  goto look
:look loop=while max=forever
  state = machine.loadInt32(flag)
  when state == 0 claim notFirst
:notFirst in=look
  when state == 2 doneAlready sleep
:sleep in=look
  system.sleepConditionVariableSRW(wakeAt, lockAt, -1, 0)
  goto look
:claim
  machine.storeInt32(flag, 1)
  system.releaseSRWLockExclusive(lockAt)
  nowhere = machine.zero()
  machine.callWithAddress(function, nowhere)
  system.acquireSRWLockExclusive(lockAt)
  exchange32(flag, 1, 2)
  system.releaseSRWLockExclusive(lockAt)
  system.wakeAllConditionVariable(wakeAt)
  return
:doneAlready
  system.releaseSRWLockExclusive(lockAt)
  return
:finished
  return

## ---------------------------------------------------------------- thread-specific storage

op keyBlock "A block of 64 cells kept at a place of machine.state, made zeroed the first time"
  input cellAt Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  cell = kernel.stateAt(cellAt)
  block = machine.loadAddress(cell)
  nowhere = machine.zero()
  when block == nowhere make done
:make
  made = heap.take(512)
  machine.storeAddress(cell, made)
  return made
:done
  return block

op valuesOf "Where the running thread's thread-specific values are: from 0x80 of its thread block, or a block of the first thread's when it has none"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  block = ownBlock()
  nowhere = machine.zero()
  when block == nowhere fromState fromBlock
:fromState
  values = keyBlock(firstValuesAt)
  return values
:fromBlock
  calc blockValues = block + 128
  return blockValues

op ownBlock "The running thread's block, or the address 0 when there are none: on Linux the thread pointer once a C program's first block was made, on Windows the thread-local slot"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere = machine.zero()
  onLinux = system.posix()
  if onLinux linux windows
:linux
  blockCell = kernel.stateAt(2352)
  first = machine.loadAddress(blockCell)
  when first == nowhere noBlock pointer
:pointer
  current = machine.threadPointer()
  return current
:noBlock
  return nowhere
:windows
  slotCell = kernel.stateAt(29000)
  slot = machine.loadInt64(slotCell)
  when slot == 0 noBlock read
:read
  windowsBlock = system.tlsGetValue(clibrary.lowInt32(slot - 1))
  return windowsBlock

op createKey "tss_create: a new key (64 at most), with the destructor a thread's value of it gets when the thread ends: thrd_success, or thrd_error when all are taken"
  input key machine.Address copied
  input destructor machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "tss_create"
:begin
  countCell = kernel.stateAt(keysAt)
  count = machine.loadInt64(countCell)
  when count >= 64 full make
:full
  return error
:make
  machine.storeInt64(countCell, count + 1)
  destructors = keyBlock(destructorsAt)
  calc destructorCell = destructors + count * 8
  machine.storeAddress(destructorCell, destructor)
  machine.storeInt32(key, clibrary.lowInt32(count))
  return success

op keyValue "tss_get: the running thread's value of a key"
  invariant keepsValues "Gives the value the running thread set for the key"
  input key Int32 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "tss_get"
:begin
  values = valuesOf()
  calc at = values + convert.int32ToInt64(key & 63) * 8
  value = machine.loadAddress(at)
  return value

op setKeyValue "tss_set: set the running thread's value of a key"
  input key Int32 copied
  input value machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "tss_set"
:begin
  values = valuesOf()
  calc at = values + convert.int32ToInt64(key & 63) * 8
  machine.storeAddress(at, value)
  return success

op deleteKey "tss_delete: forget a key's destructor (values stay where they are, as C allows)"
  input key Int32 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "tss_delete"
:begin
  destructors = keyBlock(destructorsAt)
  calc destructorCell = destructors + convert.int32ToInt64(key & 63) * 8
  nowhere = machine.zero()
  machine.storeAddress(destructorCell, nowhere)
  return

op runDestructors "When a thread ends: call each key's destructor with the thread's value when both are there, once"
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  values = valuesOf()
  destructors = keyBlock(destructorsAt)
  countCell = kernel.stateAt(keysAt)
  count = machine.loadInt64(countCell)
  nowhere = machine.zero()
  goto eachKey
:eachKey loop=while max=forever
  when at >= count done check
:check in=eachKey
  calc valueAt = values + at * 8
  value = machine.loadAddress(valueAt)
  calc destructorCell = destructors + at * 8
  destructor = machine.loadAddress(destructorCell)
  when value != nowhere && destructor != nowhere call next
:call in=eachKey
  machine.storeAddress(valueAt, nowhere)
  machine.callWithAddress(destructor, value)
  goto next
:next in=eachKey
  calc at := at + 1
  goto eachKey
:done
  return

op floatControl "The running thread's floating-point control and status (D-167: MXCSR on x86_64, FPCR | FPSR << 32 on AArch64); a thread threads.h starts begins with its creator's, which clone copies"
  invariant startsAsCreator "Reads the control and status the thread runs with"
  output UInt64
  effect use machine.memory
  uses memoryAccess
:begin
  control = machine.loadFloatControl()
  return control

@tests

test mutexTest "A plain mutex is taken, refused to a second try, and given back; a recursive one is taken twice by its holder; storage keeps a value; thrd_current is equal to itself"
  verifies lockMutex excludesOthers
  verifies keyValue keepsValues
  verifies currentThread knowsItself
  verifies timedLockMutex stopsAtDeadline
  verifies timedWaitCondition waitsUntilDeadline
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  mutex = heap.take(40)
  initMutex(mutex, 0)
  first = lockMutex(mutex)
  test.assertTrue(first == 0)
  second = tryLockMutex(mutex)
  test.assertTrue(second == 1)
  unlockMutex(mutex)
  third = tryLockMutex(mutex)
  test.assertTrue(third == 0)
  unlockMutex(mutex)
  initMutex(mutex, 1)
  lockMutex(mutex)
  again = tryLockMutex(mutex)
  test.assertTrue(again == 0)
  unlockMutex(mutex)
  unlockMutex(mutex)
  free = tryLockMutex(mutex)
  test.assertTrue(free == 0)
  key = heap.take(8)
  nowhere = machine.zero()
  made = createKey(key, nowhere)
  test.assertTrue(made == 0)
  keyNumber = machine.loadInt32(key)
  setKeyValue(keyNumber, mutex)
  value = keyValue(keyNumber)
  test.assertTrue(value == mutex)
  current = currentThread()
  same = sameThread(current, current)
  test.assertTrue(same == 1)
  past = heap.take(16)
  machine.storeInt64(past, 1)
  plain = heap.take(40)
  initMutex(plain, 0)
  lockMutex(plain)
  late = timedLockMutex(plain, past)
  test.assertTrue(late == 4)
  condition = heap.take(48)
  initCondition(condition)
  waited = timedWaitCondition(condition, plain, past)
  test.assertTrue(waited == 4)
  unlockMutex(plain)
  return

test floatControlTest "The floating-point control reads back what was stored, and a fused multiply-add rounds once"
  verifies floatControl startsAsCreator
  effect use machine.memory
  uses memoryAccess
:begin
  control = floatControl()
  machine.storeFloatControl(control)
  again = machine.loadFloatControl()
  test.assertTrue(again == control)
  fused = machine.fusedMultiplyAdd(0.1, 10.0, -1.0)
  bitsOf = convert.float64BitsToUInt64(fused)
  test.assertTrue(bitsOf == 4363988038922010624)
  calc single = convert.float64ToFloat32(0.5)
  fusedSingle = machine.fusedMultiplyAdd32(single, single, single)
  test.assertTrue(convert.float32ToFloat64(fusedSingle) == 0.75)
  return

test threadTest "On Windows a thread runs a C function (strlen) on its argument and thrd_join gives what it returned (Linux's threads are proved by tests/cprograms/threads_c11.c, since the JIT's own process is glibc's there)"
  verifies createThread startsThreads
  verifies joinThread givesResult
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let strlenName String "strlen"
  let hello String "hello"
:begin
  onLinux = system.posix()
  if onLinux skip run
:run
  nameAt = machine.addressOfString(strlenName)
  function = clibrary.lookup(nameAt, 6)
  text = heap.take(8)
  helloAt = machine.addressOfString(hello)
  machine.copy(text, helloAt, 5)
  cell = heap.take(8)
  status = createThread(cell, function, text)
  test.assertTrue(status == 0)
  thread = machine.loadAddress(cell)
  resultCell = heap.take(8)
  joinThread(thread, resultCell)
  result = machine.loadInt32(resultCell)
  test.assertTrue(result == 5)
  return
:skip
  return

## D-191: the threads contentionTest starts run this operation, which `machine.testThreadEntry` gives the address of.
## Its work block: 0 a mutex, 8 a counter cell, 16 how many rounds, 24 what to do, 32 a condition variable, 40 a flag
## cell, 48 a deadline, 56 a C function.
op workerThread "A test thread (D-191): by the work block's mode, 0 adds 1 to the counter in each round under mtx_lock, 1 the same under mtx_timedlock, a read and its write a yield apart; 2 waits under the mutex for the flag, answers on the counter, and signals back; 3 times out locking the mutex another thread holds; 4 times out waiting on a condition variable no one signals and still holds the mutex after; 5 passes call_once the flag and the function; 6 flushes every stream in each round. Gives 7, the timeouts 4 once the deadline has passed, and 99 for anything wrong"
  input work machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_c_test_thread"
  let done Int64 0 mut
  let wrong Int32 99
  let fine Int32 7
:begin
  mutex = machine.loadAddress(work)
  calc counterAt = work + 8
  counter = machine.loadAddress(counterAt)
  calc timesAt = work + 16
  times = machine.loadInt64(timesAt)
  calc modeAt = work + 24
  mode = machine.loadInt64(modeAt)
  calc conditionAt = work + 32
  condition = machine.loadAddress(conditionAt)
  calc flagAt = work + 40
  flag = machine.loadAddress(flagAt)
  calc deadlineAt = work + 48
  deadline = machine.loadAddress(deadlineAt)
  calc functionAt = work + 56
  function = machine.loadAddress(functionAt)
  nowhere = machine.zero()
  when mode == 2 handoff notHandoff
:notHandoff
  when mode == 3 lateLock notLateLock
:notLateLock
  when mode == 4 lateWait notLateWait
:notLateWait
  when mode == 5 once notOnce
:notOnce
  when mode == 6 flushing count
:count loop=while max=forever
  when done >= times counted step
:step in=count
  when mode == 1 timedTake plainTake
:timedTake in=count
  got = timedLockMutex(mutex, deadline)
  when got == 0 add failed
:plainTake in=count
  lockMutex(mutex)
  goto add
:add in=count
  value = machine.loadInt64(counter)
  system.switchToThread()
  machine.storeInt64(counter, value + 1)
  unlockMutex(mutex)
  calc done := done + 1
  goto count
:counted
  return fine
:failed
  return wrong
:handoff
  lockMutex(mutex)
  goto waitFlag
:waitFlag loop=while max=forever
  seen = machine.loadInt64(flag)
  when seen == 0 sleepFlag signalled
:sleepFlag in=waitFlag
  waitCondition(condition, mutex)
  goto waitFlag
:signalled
  machine.storeInt64(counter, 1)
  signalCondition(condition)
  unlockMutex(mutex)
  return fine
:lateLock
  lockResult = timedLockMutex(mutex, deadline)
  lockLeft = waitMilliseconds(deadline)
  when lockResult == 4 && lockLeft == 0 timedOutRight failed
:timedOutRight
  return lockResult
:lateWait
  lockMutex(mutex)
  waitResult = timedWaitCondition(condition, mutex, deadline)
  waitLeft = waitMilliseconds(deadline)
  stillHeld = tryLockMutex(mutex)
  unlockMutex(mutex)
  when waitResult == 4 && waitLeft == 0 && stillHeld == 1 waitedRight failed
:waitedRight
  return waitResult
:once
  callOnce(flag, function)
  return fine
:flushing loop=while max=forever
  when done >= times counted flushOnce
:flushOnce in=flushing
  flushed = machine.callComparison(function, nowhere, nowhere)
  calc done := done + 1
  when flushed == 0 flushing failed

op runWorkers "Start a number of threads (at most 8) on one work block and join them all: how many gave 7, or -1 when one could not start"
  input work machine.Address copied
  input count Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let started Int64 0 mut
  let joined Int64 0 mut
  let good Int64 0 mut
:begin
  cells = heap.take(64)
  resultCell = heap.take(8)
  entry = machine.testThreadEntry()
  goto start
:start loop=while max=forever
  when started >= count joinAll startOne
:startOne in=start
  calc cell = cells + started * 8
  status = createThread(cell, entry, work)
  calc started := started + 1
  when status == 0 start refused
:refused
  return -1
:joinAll loop=while max=forever
  when joined >= count finished joinOne
:joinOne in=joinAll
  calc cellAt = cells + joined * 8
  thread = machine.loadAddress(cellAt)
  joinThread(thread, resultCell)
  result = machine.loadInt32(resultCell)
  calc joined := joined + 1
  when result == 7 counted joinAll
:counted in=joinAll
  calc good := good + 1
  goto joinAll
:finished
  heap.give(cells)
  heap.give(resultCell)
  return good

op deadlineIn "A TIME_UTC timespec a number of milliseconds from now, in a new heap block"
  input milliseconds Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  now = windowsNow()
  calc due = now + milliseconds * 1000000
  block = heap.take(16)
  machine.storeInt64(block, due / 1000000000)
  calc nanosAt = block + 8
  machine.storeInt64(nanosAt, due % 1000000000)
  return block

op countUnder "Four workers add 2000 each to a counter set to 0 under a mutex made of a kind, in a mode: whether all four gave 7 and the counter is 8000"
  input work machine.Address copied
  input kind Int32 copied
  input mode Int64 copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  mutex = machine.loadAddress(work)
  initMutex(mutex, kind)
  calc counterAt = work + 8
  counter = machine.loadAddress(counterAt)
  machine.storeInt64(counter, 0)
  calc modeAt = work + 24
  machine.storeInt64(modeAt, mode)
  good = runWorkers(work, 4)
  total = machine.loadInt64(counter)
  calc right = good == 4 && total == 8000
  return right

test contentionTest "On Windows (D-191) threads block in the system: four threads add 1 to a counter 2000 times each, a read and its write a yield apart, under a plain, a recursive, and a timed mutex (that one through mtx_timedlock), and the counter is 8000 each time; a condition variable hands a flag to a waiting thread and its answer back; a timed lock of a mutex another thread holds and a timed wait no one signals each give thrd_timedout once their deadline, 30 ms ahead, has passed, the wait holding its mutex again; four threads' call_once calls rand once; four threads flush every stream 500 times each under the streams' lock"
  verifies windowsLock waitsBlocked
  verifies windowsWait givesBackAndWaits
  verifies waitMilliseconds roundsUp
  verifies windowsOnce callsOnce
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let randName String "rand"
  let srandName String "srand"
  let flushName String "fflush"
:begin
  onLinux = system.posix()
  if onLinux skip run
:run
  work = heap.take(64)
  mutex = heap.take(40)
  counter = heap.take(8)
  condition = heap.take(48)
  flag = heap.take(8)
  machine.storeAddress(work, mutex)
  calc counterAt = work + 8
  machine.storeAddress(counterAt, counter)
  calc timesAt = work + 16
  machine.storeInt64(timesAt, 2000)
  calc modeAt = work + 24
  calc conditionAt = work + 32
  machine.storeAddress(conditionAt, condition)
  calc flagAt = work + 40
  machine.storeAddress(flagAt, flag)
  calc deadlineAt = work + 48
  far = deadlineIn(600000)
  machine.storeAddress(deadlineAt, far)
  calc functionAt = work + 56
  plain = countUnder(work, 0, 0)
  test.assertTrue(plain)
  recursive = countUnder(work, 1, 0)
  test.assertTrue(recursive)
  timed = countUnder(work, 2, 1)
  test.assertTrue(timed)
  initMutex(mutex, 0)
  initCondition(condition)
  machine.storeInt64(counter, 0)
  machine.storeInt64(flag, 0)
  machine.storeInt64(modeAt, 2)
  cell = heap.take(8)
  resultCell = heap.take(8)
  entry = machine.testThreadEntry()
  started = createThread(cell, entry, work)
  test.assertTrue(started == 0)
  system.sleep(20)
  nowhere = machine.zero()
  windowsLock(mutex, nowhere)
  machine.storeInt64(flag, 1)
  signalCondition(condition)
  goto awaitAnswer
:awaitAnswer loop=while max=forever
  answer = machine.loadInt64(counter)
  when answer == 0 sleepAnswer answered
:sleepAnswer in=awaitAnswer
  windowsWait(condition, mutex, nowhere)
  goto awaitAnswer
:answered
  windowsUnlock(mutex)
  farLeft = waitMilliseconds(far)
  test.assertTrue(farLeft > 590000)
  past = heap.take(16)
  machine.storeInt64(past, 1)
  pastLeft = waitMilliseconds(past)
  test.assertTrue(pastLeft == 0)
  waiter = machine.loadAddress(cell)
  joinThread(waiter, resultCell)
  handed = machine.loadInt32(resultCell)
  test.assertTrue(handed == 7)
  lockMutex(mutex)
  soon = deadlineIn(30)
  machine.storeAddress(deadlineAt, soon)
  machine.storeInt64(modeAt, 3)
  createThread(cell, entry, work)
  lateLocker = machine.loadAddress(cell)
  joinThread(lateLocker, resultCell)
  lockedOut = machine.loadInt32(resultCell)
  test.assertTrue(lockedOut == 4)
  unlockMutex(mutex)
  soonAgain = deadlineIn(30)
  machine.storeAddress(deadlineAt, soonAgain)
  machine.storeInt64(modeAt, 4)
  createThread(cell, entry, work)
  lateWaiter = machine.loadAddress(cell)
  joinThread(lateWaiter, resultCell)
  waitedOut = machine.loadInt32(resultCell)
  test.assertTrue(waitedOut == 4)
  randAt = machine.addressOfString(randName)
  randFn = clibrary.lookup(randAt, 4)
  srandAt = machine.addressOfString(srandName)
  srandFn = clibrary.lookup(srandAt, 5)
  seed = machine.fromInt64(5)
  machine.callComparison(srandFn, seed, nowhere)
  machine.callComparison(randFn, nowhere, nowhere)
  second = machine.callComparison(randFn, nowhere, nowhere)
  machine.callComparison(srandFn, seed, nowhere)
  machine.storeInt64(flag, 0)
  machine.storeAddress(functionAt, randFn)
  machine.storeInt64(modeAt, 5)
  onceGood = runWorkers(work, 4)
  test.assertTrue(onceGood == 4)
  windowsOnce(flag, randFn)
  afterOnce = machine.callComparison(randFn, nowhere, nowhere)
  test.assertTrue(afterOnce == second)
  onceState = machine.loadInt32(flag)
  test.assertTrue(onceState == 2)
  flushAt = machine.addressOfString(flushName)
  flushFn = clibrary.lookup(flushAt, 6)
  machine.storeAddress(functionAt, flushFn)
  machine.storeInt64(timesAt, 500)
  machine.storeInt64(modeAt, 6)
  flushGood = runWorkers(work, 4)
  test.assertTrue(flushGood == 4)
  return
:skip
  return
