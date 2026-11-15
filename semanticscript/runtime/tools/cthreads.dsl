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
## its block from 0x80. On Windows (D-168) a thread is CreateThread's, its block in a thread-local slot, and a wait
## sleeps a millisecond and looks again.
## machine.state bytes 28480 to 28999 and 29000 to 29007 (the thread-local slot's index plus 1) belong to this module: 28480 the first thread's record, 28488 how many keys
## were made, 28496 the block of each key's destructor (64 keys), 28504 the block of the first thread's values.
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

op futexWait "Wait while a 32-bit cell holds a value, or until woken (FUTEX_WAIT, private) on Linux; on Windows a short sleep, after which the caller looks again (a futex may wake for nothing)"
  input cell machine.Address copied
  input value Int32 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  onLinux = system.linux()
  if onLinux linux windows
:linux
  nowhere = machine.zero()
  calc wideValue = convert.int32ToInt64(value)
  system.futex(cell, 128, wideValue, nowhere, nowhere, 0)
  return
:windows
  system.sleep(1)
  return

op futexWaitShared "Wait while a 32-bit cell holds a value, or until woken, with FUTEX_WAIT not private: the wake the kernel gives a thread's cleared tid (CLONE_CHILD_CLEARTID) is not private, and a private wait never hears it; on Windows a short sleep"
  input cell machine.Address copied
  input value Int32 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  onLinux = system.linux()
  if onLinux linux windows
:linux
  nowhere = machine.zero()
  calc wideValue = convert.int32ToInt64(value)
  system.futex(cell, 0, wideValue, nowhere, nowhere, 0)
  return
:windows
  system.sleep(1)
  return

op futexWake "Wake up to a count of threads waiting on a cell (FUTEX_WAKE, private) on Linux; on Windows the waiters look again on their own"
  input cell machine.Address copied
  input count Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  onLinux = system.linux()
  if onLinux linux done
:linux
  nowhere = machine.zero()
  system.futex(cell, 129, count, nowhere, nowhere, 0)
  return
:done
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
  onLinux = system.linux()
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
  onLinux = system.linux()
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
  onLinux = system.linux()
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
  onLinux = system.linux()
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
  onLinux = system.linux()
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
  onLinux = system.linux()
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
  onLinux = system.linux()
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
  uses memoryAccess
  abi library "mtx_init"
:begin
  machine.fill(mutex, 0, 40)
  calc kindAt = mutex + 24
  machine.storeInt32(kindAt, kind)
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
  previous = exchange32(mutex, 1, 0)
  when previous == 1 done contended
:contended
  machine.storeInt32(mutex, 0)
  futexWake(mutex, 1)
  return success
:done
  return success

op destroyMutex "mtx_destroy: nothing to give back"
  input mutex machine.Address copied
  abi library "mtx_destroy"
:begin
  return

## ---------------------------------------------------------------- condition variables

op initCondition "cnd_init: a condition variable no thread waits on"
  input condition machine.Address copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "cnd_init"
:begin
  machine.fill(condition, 0, 48)
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
  sequence = machine.loadInt32(condition)
  unlockMutex(mutex)
  late = deadlineWait(condition, sequence, deadline)
  lockMutex(mutex)
  if late giveUp done
:giveUp
  return timedOut
:done
  return success

op deadlineWait "Wait while a 32-bit cell holds a value, or until woken, but not past a deadline (a timespec of the real-time clock): on Linux a futex wait on the bitset with CLOCK_REALTIME, which takes the deadline itself; on Windows a millisecond's sleep when the deadline is still ahead. Whether the deadline passed"
  input cell machine.Address copied
  input value Int32 copied
  input deadline machine.Address copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  onLinux = system.linux()
  if onLinux linux windows
:linux
  nowhere = machine.zero()
  calc wideValue = convert.int32ToInt64(value)
  result = system.futex(cell, 393, wideValue, deadline, nowhere, 4294967295)
  calc late = result == -110
  return late
:windows
  clock = heap.take(8)
  system.getSystemTimeAsFileTime(clock)
  ticks = machine.loadInt64(clock)
  heap.give(clock)
  calc now = (ticks - 116444736000000000) * 100
  seconds = machine.loadInt64(deadline)
  calc nanosAt = deadline + 8
  nanos = machine.loadInt64(nanosAt)
  calc due = seconds * 1000000000 + nanos
  when now >= due passed sleep
:passed
  return true
:sleep
  system.sleep(1)
  return false

op signalCondition "cnd_signal: wake one waiter"
  input condition machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "cnd_signal"
:begin
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
  previous = exchange32(flag, 0, 1)
  when previous == 0 call wait
:call
  nowhere = machine.zero()
  machine.callWithAddress(function, nowhere)
  machine.storeInt32(flag, 2)
  futexWake(flag, 2147483647)
  return
:wait loop=while max=forever
  state = machine.loadInt32(flag)
  when state == 2 done sleep
:sleep in=wait
  futexWait(flag, 1)
  goto wait
:done
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
  onLinux = system.linux()
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
  onLinux = system.linux()
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
