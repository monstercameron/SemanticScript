module tasks "Tasks on fibers, task groups, cancellation, waits and deadlocks, deadlines and clocks, and channels"
  path tasks
  imports standard.machine standard.system standard.string standard.math standard.compare standard.convert standard.bits standard.logic standard.test kernel numbers frames heap handles regions slots
  exports now wait cancelled notify deadlineNever deadlineAfter sleepFor clockNow clockMonotonic channelNew channelSend channelReceive channelClose

capability memoryAccess "Authority to keep the tasks, groups, and channels in memory and switch the call stack between tasks" use machine.memory none

capability systemCalls "Authority to make and switch fibers, read the clocks, sleep, wait for handles, and end the process on a trap" use system.calls none

## D-133: a task runs on a fiber of its own (a stack of 64 MiB reserved), started when the task is started and run
## until it waits or ends; then the next task that can go on runs, in the order the tasks were started, the main
## program first. Only one runs at a time, on the program's one thread, so the runtime's state needs no locks. A
## task that waits (a join, an `awaitSlot`, a channel, a sleep, a child process, a lock, standard input) notes what
## it waits for; it can go on when something changed since it last looked (the generation, counted up by every
## send, receive, close, cancel, start, and end of a task), when its deadline has passed, when it is cancelled and
## the wait is cancellable, or when the operating-system handle it waits on is signalled. When no task can go on,
## the program sleeps until the nearest deadline or handle; with neither, nothing can ever change, and that is a
## deadlock, which traps naming every wait as `refined run` does.
##
## machine.state bytes 448 to 639 belong to this module: 448 the running task (0 before the first wait or start),
## 456 the main program's task, 464 the first task of the list, 472 the generation, 480 not 0 once the main thread
## is a fiber, 488 the last task of the list, 496 a FILETIME, 504 how many tasks are listed, 512 to 543 a number's
## digits; bytes 49152 to 49663 the handles a sleep waits on.
## A task (a heap block of taskBytes): 0 its thunk, 8 its frame, 16 its fiber, 24 its state (0 running or ready, 1
## waiting, 2 ended), 32 its group (0 for none), 40 whether it is cancelled, 48 the task that started it (0 for the
## main program), 56 the next task in the list, 64 to 111 its part of machine.state while another runs (the call
## stack's table, its count and room, the stack floor, whether it is a task, its depth counters), 112 what it waits
## for (address and length), 128 its deadline, 136 whether the wait is cancellable, 144 the handle it waits on, 152
## the generation it last looked at, 160 the next task of its group.
## A group (a heap block of groupBytes): 0 its limit, 8 how many of its tasks run, 16 whether it is cancelled, 24 the
## first error one of its tasks reported (a heap block) and 32 its bytes, 40 its first task.
## A channel (a heap block of channelBytes): 0 its capacity, 8 how many items it holds, 16 the first item's place,
## 24 whether it is closed, 32 its region, 40 whether its items are text, 48 the slots of an item (-1 until the
## first send), 56 the block of items.
constant currentAt "Where the running task is kept, in machine.state" Int64 448

constant mainAt "Where the main program's task is kept, in machine.state" Int64 456

constant headAt "Where the first task of the list is kept, in machine.state" Int64 464

constant generationAt "Where the generation is kept, in machine.state" Int64 472

constant fibersAt "Where whether the main thread is a fiber is kept, in machine.state" Int64 480

constant tailAt "Where the last task of the list is kept, in machine.state" Int64 488

constant fileTimeAt "Where the system time is put, in machine.state" Int64 496

constant countAt "Where the number of tasks listed is kept, in machine.state" Int64 504

constant digitsAt "Where a number's digits are put together, in machine.state" Int64 512

constant waitHandlesAt "Where the handles a sleep waits on are put, in machine.state" Int64 49152

constant interruptEventAt "Where the interrupts module keeps the Windows event an interrupt sets, in machine.state (D-147)" Int64 1232

constant mostHandles "How many handles one sleep waits on at most" Int64 64

constant never "time.Deadline.never: a deadline that never passes" Int64 -1

constant forever "The bound of a loop that waits as long as it takes" Int64 9223372036854775807

constant taskBytes "The bytes of a task" Int64 176

constant fiberBytes "The bytes of a fiber on Linux: 0 its stack pointer while another runs, 8 its stack's base (0 for the main program's), 16 its stack's bytes, 24 whether it has started" Int64 32

constant groupBytes "The bytes of a group" Int64 48

constant channelBytes "The bytes of a channel" Int64 64

constant depthBytes "The bytes of a task's depth counters: one Int64 for each of 4096 recursive operations" Int64 32768

constant stackCommit "The bytes of a task's stack committed when it starts" Int64 65536

constant stackReserve "The bytes of a task's stack: 64 MiB, as a task's thread has under `refined run`" Int64 67108864

constant stackBudget "How far below a task's first frame its stack floor is: 64 MiB less 8 MiB" Int64 58720256

constant ofThunk "Where a task's thunk is" Int64 0

constant ofFrame "Where a task's frame is" Int64 8

constant ofFiber "Where a task's fiber is" Int64 16

constant ofState "Where a task's state is" Int64 24

constant ofGroup "Where a task's group is" Int64 32

constant ofCancelled "Where whether a task is cancelled is" Int64 40

constant ofParent "Where the task that started a task is" Int64 48

constant ofNext "Where the next task of the list is" Int64 56

constant ofSaved "Where a task's part of machine.state is kept while another runs" Int64 64

constant ofInTask "Where a task's saved word that says it is a task is" Int64 96

constant ofDepths "Where a task's saved address of its depth counters is" Int64 104

constant ofWhat "Where the address of what a task waits for is" Int64 112

constant ofWhatBytes "Where the length of what a task waits for is" Int64 120

constant ofDeadline "Where a waiting task's deadline is" Int64 128

constant ofCancellable "Where whether a task's wait is cancellable is" Int64 136

constant ofExternal "Where the handle a task waits on is" Int64 144

constant ofSeen "Where the generation a waiting task last looked at is" Int64 152

constant ofMember "Where the next task of a task's group is" Int64 160

constant running "A task's state while it runs or is ready to" Int64 0

constant waiting "A task's state while it waits" Int64 1

constant ended "A task's state once it has ended" Int64 2

constant ofLimit "Where a group's limit is" Int64 0

constant ofRunning "Where how many of a group's tasks run is" Int64 8

constant ofGroupCancelled "Where whether a group is cancelled is" Int64 16

constant ofError "Where a group's first error is" Int64 24

constant ofErrorBytes "Where the bytes of a group's first error are" Int64 32

constant ofFirst "Where a group's first task is" Int64 40

constant ofCapacity "Where a channel's capacity is" Int64 0

constant ofCount "Where how many items a channel holds is" Int64 8

constant ofHead "Where a channel's first item's place is" Int64 16

constant ofClosed "Where whether a channel is closed is" Int64 24

constant ofRegion "Where a channel's region is" Int64 32

constant ofText "Where whether a channel's items are text is" Int64 40

constant ofSlots "Where the slots of a channel's item are" Int64 48

constant ofItems "Where a channel's block of items is" Int64 56

constant kindChannel "The kind of a channel's handle" Int64 7

constant channelClosed "channel.ChannelError.closed, numbered from 1" Int32 1

constant channelTimedOut "channel.ChannelError.timedOut, numbered from 1" Int32 2

constant channelCancelled "channel.ChannelError.cancelled, numbered from 1" Int32 3

op endProcess "End the process with an exit code: ExitProcess on Windows, exit_group on Linux (D-138)"
  input code Int32 copied
  effect use system.calls
  uses systemCalls
:begin
  osCheck: onLinux = system.posix()
  if onLinux linuxExit windowsExit
:linuxExit
  widenCode: wideCode = convert.int32ToInt64(code)
  callExit: exitResult = system.exitGroup(wideCode)
  return
:windowsExit
  callExitProcess: system.exitProcess(code)
  return

## ---------------------------------------------------------------- fields and traps

op field "A whole number of a block at an offset"
  input block machine.Address copied
  input offset Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findField: place = machine.offset(block, offset)
  readField: value = machine.loadInt64(place)
  return value

op setField "Store a whole number in a block at an offset"
  input block machine.Address copied
  input offset Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  findField: place = machine.offset(block, offset)
  storeField: machine.storeInt64(place, value)
  return

op link "An address kept in a block at an offset"
  input block machine.Address copied
  input offset Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findField: place = machine.offset(block, offset)
  readField: value = machine.loadAddress(place)
  return value

op setLink "Store an address in a block at an offset"
  input block machine.Address copied
  input offset Int64 copied
  input value machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  findField: place = machine.offset(block, offset)
  storeField: machine.storeAddress(place, value)
  return

op wordOf "A whole number of a block named by its address as a number"
  input block Int64 copied
  input offset Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  blockOf: address = machine.fromInt64(block)
  readIt: value = field(address, offset)
  return value

op setWordOf "Store a whole number in a block named by its address as a number"
  input block Int64 copied
  input offset Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  blockOf: address = machine.fromInt64(block)
  storeIt: setField(address, offset, value)
  return

op stateWord "A whole number of machine.state"
  input offset Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  readWord: value = field(state, offset)
  return value

op setStateWord "Store a whole number in machine.state"
  input offset Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  storeWord: setField(state, offset, value)
  return

op stateLink "An address kept in machine.state"
  input offset Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  readLink: value = link(state, offset)
  return value

op setStateLink "Store an address in machine.state"
  input offset Int64 copied
  input value machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  storeLink: setLink(state, offset, value)
  return

op failText "Report a trap with a message and end the process with exit code 70"
  input text String borrowed
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findText: textAt = machine.addressOfString(text)
  textLength: bytes = string.byteLength(text)
  writeReport: status = frames.report(textAt, bytes)
  exit: endProcess(trapCode=70)
  return

op failNumber "Trap with a message of a text, a whole number in decimal, and another text"
  input lead String borrowed
  input number Int64 copied
  input tail String borrowed
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findState: state = machine.state()
  findDigits: digits = machine.offset(state, digitsAt)
  format: length = numbers.formatDecimal(number, digits)
  compose: message = heap.joinMessage(lead, digits, length, tail)
  leadLength: leadBytes = string.byteLength(lead)
  tailLength: tailBytes = string.byteLength(tail)
  headLength: headBytes = math.addInt64(leadBytes, length)
  totalLength: bytes = math.addInt64(headBytes, tailBytes)
  writeReport: status = frames.report(message, bytes)
  exit: endProcess(trapCode=70)
  return

## ---------------------------------------------------------------- time

op now "Milliseconds since the system started (GetTickCount64): the clock deadlines are read against"
  invariant readsClock "Gives a number that never goes down"
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  osCheck: onLinux = system.posix()
  if onLinux linuxClock windowsClock
:linuxClock
  readMonotonic: milliseconds = kernel.monotonic()
  return milliseconds
:windowsClock
  readClock: ticks = system.getTickCount64()
  return ticks

op duration "A duration of milliseconds, which is zero or more; a negative one traps naming who was given it"
  input milliseconds Int64 copied
  input who String borrowed
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  negativeCheck: negative = compare.lessThanInt64(milliseconds, zero=0)
  if negative refuse give
:refuse
  failIt: failNumber(who, milliseconds, tail=" milliseconds; a duration is zero or more")
  return milliseconds
:give
  return milliseconds

op passed "Whether a deadline has passed: never for time.Deadline.never"
  input deadline Int64 copied
  input at Int64 copied
  output Bool
  let no Bool false
:begin
  neverCheck: isNever = compare.equalInt64(deadline, never)
  if isNever notYet compareIt
:notYet
  return no
:compareIt
  pastCheck: past = compare.greaterOrEqualInt64(at, deadline)
  return past

## ---------------------------------------------------------------- the list of tasks

op mainTask "The main program's task, made the first time it is asked for"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readMain: main = stateLink(mainAt)
  nowhere: anywhere = machine.zero()
  missingCheck: missing = machine.equal(main, anywhere)
  if missing make give
:make
  takeTask: task = heap.take(taskBytes)
  storeMain: setStateLink(mainAt, task)
  storeCurrent: setStateLink(currentAt, task)
  storeHead: setStateLink(headAt, task)
  storeTail: setStateLink(tailAt, task)
  storeCount: setStateWord(countAt, one=1)
  return task
:give
  return main

op currentTask "The task that is running: the main program's until a task starts"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  ensureMain: main = mainTask()
  readCurrent: current = stateLink(currentAt)
  return current

op nextOf "The task after a task in the list, the first after the last"
  input task machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  readNext: next = link(task, ofNext)
  nowhere: anywhere = machine.zero()
  lastCheck: last = machine.equal(next, anywhere)
  if last wrap give
:wrap
  readHead: head = stateLink(headAt)
  return head
:give
  return next

op append "Put a task at the end of the list"
  input task machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  readTail: tail = stateLink(tailAt)
  linkTail: setLink(tail, ofNext, task)
  storeTail: setStateLink(tailAt, task)
  readCount: count = stateWord(countAt)
  addOne: more = math.addInt64(count, one=1)
  storeCount: setStateWord(countAt, more)
  return

op unlink "Take a task out of the list (never the main program's, which is first)"
  input task machine.Address copied
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  taskValue: target = machine.toInt64(task)
  readCount: count = stateWord(countAt)
  readHead: head = stateWord(headAt)
  set at head
  goto eachTask
:eachTask loop=while max=count
  readNext: next = wordOf(at, ofNext)
  endCheck: atEnd = compare.equalInt64(next, zero=0)
  if atEnd done compareNext
:compareNext in=eachTask
  foundCheck: found = compare.equalInt64(next, target)
  if found remove advance
:advance in=eachTask
  set at next
  goto eachTask
:remove
  readAfter: after = wordOf(target, ofNext)
  skipIt: setWordOf(at, ofNext, after)
  readTail: tail = stateWord(tailAt)
  tailCheck: wasTail = compare.equalInt64(tail, target)
  if wasTail moveTail counted
:moveTail
  storeTail: setStateWord(tailAt, at)
  goto counted
:counted
  lessOne: fewer = math.subtractInt64(count, one=1)
  storeCount: setStateWord(countAt, fewer)
  goto done
:done
  return

op generation "How many times something a waiting task may wait for has changed"
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  readGeneration: value = stateWord(generationAt)
  return value

op notify "Count a change a waiting task may be waiting for: a send, a receive, a close, a cancel, a start, an end"
  invariant countsChange "The generation is one more than before"
  effect use machine.memory
  uses memoryAccess
:begin
  readGeneration: value = stateWord(generationAt)
  addOne: next = math.addInt64(value, one=1)
  storeGeneration: setStateWord(generationAt, next)
  return

op cancelled "Whether the running task has been cancelled (never the main program)"
  invariant readsCancelled "Gives whether cancel reached the running task or a task that started it"
  output Bool
  effect use machine.memory
  uses memoryAccess
  let no Bool false
:begin
  readCurrent: current = stateWord(currentAt)
  noTaskCheck: noTask = compare.equalInt64(current, zero=0)
  if noTask notCancelled readFlag
:notCancelled
  return no
:readFlag
  readCancelled: flag = wordOf(current, ofCancelled)
  setCheck: isCancelled = compare.notEqualInt64(flag, zero)
  return isCancelled

## ---------------------------------------------------------------- switching

op saveTo "Keep the running task's part of machine.state in its task: the call stack, the stack floor, whether it is a task, its depth counters"
  input task machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  findSaved: saved = machine.offset(task, ofSaved)
  findFrames: frames = machine.offset(state, sixtyFour=64)
  copyFrames: machine.copy(saved, frames, thirtyTwo=32)
  findSavedTask: savedTask = machine.offset(task, ofInTask)
  findTaskWords: taskWords = machine.offset(state, threeEightyFour=384)
  copyTask: machine.copy(savedTask, taskWords, sixteen=16)
  return

op loadFrom "Put a task's part of machine.state back as it starts to run"
  input task machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  findSaved: saved = machine.offset(task, ofSaved)
  findFrames: frames = machine.offset(state, sixtyFour=64)
  copyFrames: machine.copy(frames, saved, thirtyTwo=32)
  findSavedTask: savedTask = machine.offset(task, ofInTask)
  findTaskWords: taskWords = machine.offset(state, threeEightyFour=384)
  copyTask: machine.copy(taskWords, savedTask, sixteen=16)
  return

op switchTo "Run another task: keep the running one's state, put the other's back, and switch to its fiber"
  input next machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readCurrent: me = currentTask()
  sameCheck: same = machine.equal(me, next)
  if same done switch
:switch
  keep: saveTo(me)
  restore: loadFrom(next)
  storeCurrent: setStateLink(currentAt, next)
  readFiber: fiber = link(next, ofFiber)
  osCheck: onLinux = system.posix()
  if onLinux linuxSwitch windowsSwitch
:linuxSwitch
  readMine: mine = link(me, ofFiber)
  readStarted: started = field(fiber, twentyFour=24)
  startedCheck: isStarted = compare.notEqualInt64(started, zero=0)
  if isStarted resume startFiber
:startFiber
  markStarted: setField(fiber, twentyFour, one=1)
  readBase: base = link(fiber, eight=8)
  readStackBytes: stackBytes = field(fiber, sixteen=16)
  findTop: top = machine.offset(base, stackBytes)
  findEntry: entryAt = machine.taskEntry()
  startIt: machine.startStack(mine, top, entryAt, next)
  goto done
:resume
  readResumeAt: resumeAt = machine.loadAddress(fiber)
  resumeIt: machine.switchStack(mine, resumeAt)
  goto done
:windowsSwitch
  jump: system.switchToFiber(fiber)
  goto done
:done
  return

op pollEntry "Fill a pollfd for what a task waits on, its descriptor plus one: for reading (POLLIN), or for writing (POLLOUT) when 2^32 is added too"
  input entry machine.Address copied
  input plusOne Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  lowOf: low = bits.andInt64(plusOne, lowWord=4294967295)
  descriptorOf: fd = math.subtractInt64(low, one=1)
  narrowFd: fd32 = convert.int64ToInt32(fd)
  storeFd: machine.storeInt32(entry, fd32)
  findEvents: eventsAt = machine.offset(entry, four=4)
  highOf: high = bits.shiftRightInt64(plusOne, thirtyTwo=32)
  writeCheck: writing = compare.notEqualInt64(high, zero=0)
  if writing forWriting forReading
:forWriting
  storeOut: machine.storeInt32(eventsAt, pollOut=4)
  return
:forReading
  storeIn: machine.storeInt32(eventsAt, pollIn=1)
  return

op canGoOn "Whether a task can run: ready, or waiting while something changed, its deadline passed, it was cancelled in a cancellable wait, or its handle is signalled"
  input task machine.Address copied
  input at Int64 copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let yes Bool true
  let no Bool false
:begin
  readState: state = field(task, ofState)
  endedCheck: isEnded = compare.equalInt64(state, ended)
  if isEnded cannot readyCheck
:readyCheck
  checkReady: isReady = compare.equalInt64(state, running)
  if isReady can changedCheck
:changedCheck
  readSeen: seen = field(task, ofSeen)
  readGeneration: current = generation()
  checkChanged: changed = compare.notEqualInt64(seen, current)
  if changed can deadlineCheck
:deadlineCheck
  readDeadline: deadline = field(task, ofDeadline)
  checkPassed: isPast = passed(deadline, at)
  if isPast can cancelCheck
:cancelCheck
  readCancellable: cancellable = field(task, ofCancellable)
  readCancelled: flag = field(task, ofCancelled)
  cancellableCheck: canCancel = compare.notEqualInt64(cancellable, zero=0)
  flagCheck: isCancelled = compare.notEqualInt64(flag, zero)
  bothCheck: stopped = logic.and(canCancel, isCancelled)
  if stopped can handleCheck
:handleCheck
  readHandle: handle = link(task, ofExternal)
  nowhere: anywhere = machine.zero()
  noHandleCheck: noHandle = machine.equal(handle, anywhere)
  if noHandle cannot pollHandle
:pollHandle
  osCheck: onLinux = system.posix()
  if onLinux pollLinux pollWindows
:pollLinux
  handleValue: plusOne = machine.toInt64(handle)
  findPoll: pollAt = kernel.stateAt(fileTimeAt)
  fillPoll: pollEntry(pollAt, plusOne)
  pollIt: ready = system.poll(pollAt, onePoll=1, zero=0)
  pollReadyCheck: isPollReady = compare.greaterThanInt64(ready, zero)
  if isPollReady can cannot
:pollWindows
  poll: signalled = system.waitForSingleObject(handle, noWait=0)
  signalledCheck: isSignalled = compare.equalInt32(signalled, noWait)
  if isSignalled can cannot
:can
  return yes
:cannot
  return no

op pickAfter "The next task after one, in the list's order and coming round to it last, that can run; the address 0 when none can"
  input me machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  readNow: moment = now()
  readCount: count = stateWord(countAt)
  bound: rounds = math.addInt64(count, one=1)
  meValue: mine = machine.toInt64(me)
  first: start = nextOf(me)
  startValue: startAt = machine.toInt64(start)
  set at startAt
  goto eachTask
:eachTask loop=while max=rounds
  meCheck: isMe = compare.equalInt64(at, mine)
  if isMe lastChance tryTask
:tryTask in=eachTask
  taskOf: task = machine.fromInt64(at)
  checkTask: ready = canGoOn(task, moment)
  if ready give advance
:advance in=eachTask
  after: next = nextOf(task)
  nextValue: nextAt = machine.toInt64(next)
  set at nextAt
  goto eachTask
:give
  return task
:lastChance
  checkMe: meReady = canGoOn(me, moment)
  if meReady giveMe nobody
:giveMe
  return me
:nobody
  nowhere: anywhere = machine.zero()
  return anywhere

op firstLive "The first task in the list that has not ended (the main program's never does)"
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  readCount: count = stateWord(countAt)
  readHead: head = stateWord(headAt)
  set at head
  goto eachTask
:eachTask loop=while max=count
  readState: state = wordOf(at, ofState)
  liveCheck: live = compare.notEqualInt64(state, ended)
  if live give advance
:advance in=eachTask
  readNext: next = wordOf(at, ofNext)
  set at next
  goto eachTask
:give
  taskOf: task = machine.fromInt64(at)
  return task

## ---------------------------------------------------------------- waiting

op textOrder "How two texts compare byte by byte: -1, 0, or 1"
  input left machine.Address copied
  input leftBytes Int64 copied
  input right machine.Address copied
  input rightBytes Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let shorter Int64 0 mut
  let less Int64 -1
  let greater Int64 1
:begin
  set shorter rightBytes
  leftShorter: leftLess = compare.lessThanInt64(leftBytes, rightBytes)
  if leftLess useLeft compareBytes
:useLeft
  set shorter leftBytes
  goto compareBytes
:compareBytes
  compareThem: order = machine.compare(left, right, shorter)
  widen: orderValue = convert.int32ToInt64(order)
  differCheck: differ = compare.notEqualInt64(orderValue, zero=0)
  if differ give byLength
:give
  return orderValue
:byLength
  lessCheck: isLess = compare.lessThanInt64(leftBytes, rightBytes)
  if isLess giveLess moreCheck
:giveLess
  return less
:moreCheck
  checkMore: more = compare.greaterThanInt64(leftBytes, rightBytes)
  if more giveMore giveSame
:giveMore
  return greater
:giveSame
  return zero

op appendText "Copy bytes to the end of a message being put together; gives the message's new length"
  input message machine.Address copied
  input length Int64 copied
  input data machine.Address copied
  input bytes Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findEnd: endAt = machine.offset(message, length)
  copyIn: machine.copy(endAt, data, bytes)
  total: after = math.addInt64(length, bytes)
  return after

op deadlock "Trap because every task waits for another and nothing can change: `deadlock: every task is waiting on another: <this wait>; <the other waits, each once, in order>`"
  input me machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let room Int64 64 mut
  let length Int64 0 mut
  let at Int64 0 mut
  let last Int64 0 mut
  let lastBytes Int64 -1 mut
  let pick Int64 0 mut
  let pickBytes Int64 -1 mut
  let noBytes Int64 -1
  let lead String "deadlock: every task is waiting on another: "
  let separator String "; "
:begin
  readCount: count = stateWord(countAt)
  rounds: bound = math.addInt64(count, one=1)
  readHead: head = stateWord(headAt)
  set at head
  goto eachSize
:eachSize loop=while max=count
  readSizeBytes: sizeBytes = wordOf(at, ofWhatBytes)
  addSize: withSize = math.addInt64(room, sizeBytes)
  addSeparator: withSeparator = math.addInt64(withSize, two=2)
  set room withSeparator
  readSizeNext: sizeNext = wordOf(at, ofNext)
  sizeEndCheck: sizeEnd = compare.equalInt64(sizeNext, zero=0)
  if sizeEnd startMessage nextSize
:nextSize in=eachSize
  set at sizeNext
  goto eachSize
:startMessage
  takeMessage: message = heap.take(room)
  findLead: leadAt = machine.addressOfString(lead)
  leadLength: leadBytes = string.byteLength(lead)
  writeLead: afterLead = appendText(message, zero, leadAt, leadBytes)
  readMine: mine = link(me, ofWhat)
  readMineBytes: mineBytes = field(me, ofWhatBytes)
  writeMine: afterMine = appendText(message, afterLead, mine, mineBytes)
  set length afterMine
  goto eachOther
:eachOther loop=while max=bound
  set pick zero
  set pickBytes noBytes
  set at head
  goto startCandidates
:startCandidates in=eachOther
  goto eachCandidate
:eachCandidate loop=while max=count in=eachOther
  readState: state = wordOf(at, ofState)
  waitingCheck: isWaiting = compare.equalInt64(state, waiting)
  if isWaiting readWhat nextCandidate
:readWhat in=eachCandidate
  readTextValue: textValue = wordOf(at, ofWhat)
  textOf: text = machine.fromInt64(textValue)
  readTextBytes: textBytes = wordOf(at, ofWhatBytes)
  mineOrder: againstMine = textOrder(text, textBytes, mine, mineBytes)
  mineCheck: isMine = compare.equalInt64(againstMine, zero)
  if isMine nextCandidate afterLastCheck
:afterLastCheck in=eachCandidate
  noLastCheck: noLast = compare.lessThanInt64(lastBytes, zero)
  if noLast pickCheck compareLast
:compareLast in=eachCandidate
  lastOf: lastText = machine.fromInt64(last)
  lastOrder: againstLast = textOrder(text, textBytes, lastText, lastBytes)
  pastLastCheck: pastLast = compare.greaterThanInt64(againstLast, zero)
  if pastLast pickCheck nextCandidate
:pickCheck in=eachCandidate
  noPickCheck: noPick = compare.lessThanInt64(pickBytes, zero)
  if noPick takeIt comparePick
:comparePick in=eachCandidate
  pickOf: pickText = machine.fromInt64(pick)
  pickOrder: againstPick = textOrder(text, textBytes, pickText, pickBytes)
  beforePickCheck: beforePick = compare.lessThanInt64(againstPick, zero)
  if beforePick takeIt nextCandidate
:takeIt in=eachCandidate
  set pick textValue
  set pickBytes textBytes
  goto nextCandidate
:nextCandidate in=eachCandidate
  readNext: next = wordOf(at, ofNext)
  endCheck: atEnd = compare.equalInt64(next, zero)
  if atEnd candidatesDone moveOn
:moveOn in=eachCandidate
  set at next
  goto eachCandidate
:candidatesDone in=eachOther
  foundCheck: found = compare.greaterOrEqualInt64(pickBytes, zero)
  if found writeOther report
:writeOther in=eachOther
  findSeparator: separatorAt = machine.addressOfString(separator)
  writeSeparator: afterSeparator = appendText(message, length, separatorAt, two)
  pickedOf: picked = machine.fromInt64(pick)
  writePick: afterPick = appendText(message, afterSeparator, picked, pickBytes)
  set length afterPick
  set last pick
  set lastBytes pickBytes
  goto eachOther
:report
  writeReport: status = frames.report(message, length)
  exit: endProcess(trapCode=70)
  return

op idle "Sleep until the nearest deadline of a waiting task or a handle one waits on is signalled; with neither, trap: a deadlock"
  input me machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let earliest Int64 -1 mut
  let handles Int64 0 mut
  let at Int64 0 mut
  let timeout Int64 0 mut
  let infinite Int32 -1
:begin
  readCount: count = stateWord(countAt)
  readHead: head = stateWord(headAt)
  findState: state = machine.state()
  findHandles: handleList = machine.offset(state, waitHandlesAt)
  set at head
  goto eachTask
:eachTask loop=while max=count
  readState: taskState = wordOf(at, ofState)
  waitingCheck: isWaiting = compare.equalInt64(taskState, waiting)
  if isWaiting readDeadline nextTask
:readDeadline in=eachTask
  readTaskDeadline: deadline = wordOf(at, ofDeadline)
  neverCheck: isNever = compare.equalInt64(deadline, never)
  if isNever readHandle compareDeadline
:compareDeadline in=eachTask
  noneYetCheck: noneYet = compare.equalInt64(earliest, never)
  sooner: isSooner = compare.lessThanInt64(deadline, earliest)
  takeCheck: takeIt = logic.or(noneYet, isSooner)
  if takeIt keepDeadline readHandle
:keepDeadline in=eachTask
  set earliest deadline
  goto readHandle
:readHandle in=eachTask
  readTaskHandle: handleValue = wordOf(at, ofExternal)
  noHandleCheck: noHandle = compare.equalInt64(handleValue, zero=0)
  roomCheck: full = compare.greaterOrEqualInt64(handles, mostHandles)
  skipCheck: skip = logic.or(noHandle, full)
  if skip nextTask keepHandle
:keepHandle in=eachTask
  handleOffset: offset = math.multiplyInt64(handles, eight=8)
  findSlot: slot = machine.offset(handleList, offset)
  storeHandle: machine.storeInt64(slot, handleValue)
  moreHandles: moreCount = math.addInt64(handles, one=1)
  set handles moreCount
  goto nextTask
:nextTask in=eachTask
  readNext: next = wordOf(at, ofNext)
  endCheck: atEnd = compare.equalInt64(next, zero)
  if atEnd decide moveOn
:moveOn in=eachTask
  set at next
  goto eachTask
:decide
  noDeadlineCheck: noDeadline = compare.equalInt64(earliest, never)
  noHandlesCheck: noHandles = compare.equalInt64(handles, zero)
  stuckCheck: stuck = logic.and(noDeadline, noHandles)
  if stuck locked interruptCheck
:interruptCheck
  osInterrupt: onLinuxInterrupt = system.posix()
  if onLinuxInterrupt timing readInterrupt
:readInterrupt
  findInterrupt: interruptSlot = kernel.stateAt(interruptEventAt)
  readEvent: interruptEvent = machine.loadInt64(interruptSlot)
  eventCheck: hasEvent = compare.notEqualInt64(interruptEvent, zero)
  roomForEvent: eventRoom = compare.lessThanInt64(handles, mostHandles)
  addCheck: addEvent = logic.and(hasEvent, eventRoom)
  if addEvent addInterrupt timing
:addInterrupt
  eventOffset: eventPlace = math.multiplyInt64(handles, eight)
  findEventSlot: eventSlot = machine.offset(handleList, eventPlace)
  storeEvent: machine.storeInt64(eventSlot, interruptEvent)
  moreEvents: withEvent = math.addInt64(handles, one)
  set handles withEvent
  goto timing
:locked
  trapIt: deadlock(me)
  return
:timing
  if noDeadline foreverCheck countDown
:foreverCheck
  osCheckForever: onLinuxForever = system.posix()
  if onLinuxForever sleepOrWait waitForHandles
:countDown
  readNow: moment = now()
  leftOf: left = math.subtractInt64(earliest, moment)
  set timeout left
  negativeCheck: negative = compare.lessThanInt64(left, zero)
  if negative clampLow capCheck
:clampLow
  set timeout zero
  goto capCheck
:capCheck
  tooLongCheck: tooLong = compare.greaterThanInt64(timeout, most=2147483646)
  if tooLong clampHigh sleepOrWait
:clampHigh
  set timeout most
  goto sleepOrWait
:sleepOrWait
  osCheck: onLinux = system.posix()
  if onLinux linuxWait windowsWait
:linuxWait
  set at zero
  countHandles: handleTotal = math.addInt64(handles, zero)
  goto eachHandle
:eachHandle loop=while max=handleTotal
  handlesDone: allMade = compare.greaterOrEqualInt64(at, handles)
  if allMade linuxPoll makePollEntry
:makePollEntry in=eachHandle
  entryOffset: entryAt = math.multiplyInt64(at, eight)
  findEntry: entry = machine.offset(handleList, entryAt)
  readPlusOne: plusOne = machine.loadInt64(entry)
  fillEntry: pollEntry(entry, plusOne)
  nextHandle: afterHandle = math.addInt64(at, one)
  set at afterHandle
  goto eachHandle
:linuxPoll
  if noDeadline linuxForever linuxTimed
:linuxForever
  pollForever: wokenForever = system.poll(handleList, handles, minusOne=-1)
  return
:linuxTimed
  pollTimed: wokenTimed = system.poll(handleList, handles, timeout)
  return
:windowsWait
  narrowTimeout: milliseconds = convert.int64ToInt32(timeout)
  noneNowCheck: noHandlesNow = compare.equalInt64(handles, zero)
  if noHandlesNow justSleep waitTimed
:justSleep
  pause: system.sleep(milliseconds)
  return
:waitTimed
  narrowCount: countWide = convert.int64ToInt32(handles)
  waitSome: woken = system.waitForMultipleObjects(countWide, handleList, any=0, milliseconds)
  return
:waitForHandles
  narrowForever: countAll = convert.int64ToInt32(handles)
  waitForever: wokenAny = system.waitForMultipleObjects(countAll, handleList, any, infinite)
  return

op wait "Wait once for something, when what the caller waits for is not there yet: 2 when the task is cancelled (and the wait is cancellable), 1 when the deadline has passed, otherwise 0 after other tasks ran or time passed, and the caller looks again"
  invariant waitsOnce "Gives 2 for a cancelled task in a cancellable wait, else 1 past the deadline, else 0 once the task may go on; traps when no task can ever go on"
  input what String borrowed
  input deadline Int64 copied
  input cancellable Int64 copied
  input external machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let cancelledOutcome Int64 2
  let timedOutcome Int64 1
:begin
  readMe: me = currentTask()
  cancellableCheck: canCancel = compare.notEqualInt64(cancellable, zero=0)
  if canCancel cancelCheck deadlineCheck
:cancelCheck
  readCancelled: flag = field(me, ofCancelled)
  flagCheck: isCancelled = compare.notEqualInt64(flag, zero)
  if isCancelled giveCancelled deadlineCheck
:giveCancelled
  return cancelledOutcome
:deadlineCheck
  readNow: moment = now()
  pastCheck: isPast = passed(deadline, moment)
  if isPast giveTimedOut note
:giveTimedOut
  return timedOutcome
:note
  findWhat: whatAt = machine.addressOfString(what)
  whatLength: whatBytes = string.byteLength(what)
  storeWhat: setLink(me, ofWhat, whatAt)
  storeWhatBytes: setField(me, ofWhatBytes, whatBytes)
  storeDeadline: setField(me, ofDeadline, deadline)
  storeCancellable: setField(me, ofCancellable, cancellable)
  storeExternal: setLink(me, ofExternal, external)
  readGeneration: seen = generation()
  storeSeen: setField(me, ofSeen, seen)
  storeState: setField(me, ofState, waiting)
  goto eachTry
:eachTry loop=while max=forever
  findNext: next = pickAfter(me)
  meCheck: isMe = machine.equal(next, me)
  if isMe resume otherCheck
:otherCheck in=eachTry
  nowhere: anywhere = machine.zero()
  nobodyCheck: nobody = machine.equal(next, anywhere)
  if nobody sleepAWhile runOther
:sleepAWhile in=eachTry
  sleepIt: idle(me)
  goto eachTry
:runOther
  switchIt: switchTo(next)
  goto resume
:resume
  storeRunning: setField(me, ofState, running)
  return zero

## ---------------------------------------------------------------- cancelling

op descends "Whether a task is another or was started by it, however deep"
  input task Int64 copied
  input ancestor Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let yes Bool true
  let no Bool false
:begin
  readCount: count = stateWord(countAt)
  bound: rounds = math.addInt64(count, one=1)
  set at task
  goto eachStep
:eachStep loop=while max=rounds
  sameCheck: same = compare.equalInt64(at, ancestor)
  if same give upward
:upward in=eachStep
  readParent: parent = wordOf(at, ofParent)
  topCheck: atTop = compare.equalInt64(parent, zero=0)
  if atTop notIt climb
:climb in=eachStep
  set at parent
  goto eachStep
:give
  return yes
:notIt
  return no

op cancelTree "Mark a task cancelled, and every task it started that has not ended, however deep"
  input target machine.Address copied
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  targetValue: targetAt = machine.toInt64(target)
  readCount: count = stateWord(countAt)
  readHead: head = stateWord(headAt)
  set at head
  goto eachTask
:eachTask loop=while max=count
  readState: state = wordOf(at, ofState)
  liveCheck: live = compare.notEqualInt64(state, ended)
  if live checkTree nextTask
:checkTree in=eachTask
  treeCheck: inTree = descends(at, targetAt)
  if inTree mark nextTask
:mark in=eachTask
  storeCancelled: setWordOf(at, ofCancelled, one=1)
  goto nextTask
:nextTask in=eachTask
  readNext: next = wordOf(at, ofNext)
  endCheck: atEnd = compare.equalInt64(next, zero=0)
  if atEnd done moveOn
:moveOn in=eachTask
  set at next
  goto eachTask
:done
  return

## ---------------------------------------------------------------- tasks (what compiled code calls)

op taskFrame "Memory for a task's frame of arguments and results, zeroed: refined_task_frame"
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_task_frame"
:begin
  takeFrame: frame = heap.take(bytes)
  return frame

op spawn "Start a task on a fiber of its own and run it until it waits or ends; its handle, or 0 for a task of a group: refined_task_spawn"
  input thunk machine.Address copied
  input frame machine.Address copied
  input group Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_task_spawn"
:begin
  readMe: me = currentTask()
  readFibers: fibers = stateWord(fibersAt)
  fibersCheck: noFibers = compare.equalInt64(fibers, zero=0)
  if noFibers convert make
:convert
  nowhere: anywhere = machine.zero()
  osCheck: onLinux = system.posix()
  if onLinux convertLinux convertWindows
:convertLinux
  takeMainFiber: linuxMainFiber = heap.take(fiberBytes)
  markMainStarted: setField(linuxMainFiber, twentyFour=24, one=1)
  storeLinuxMainFiber: setLink(me, ofFiber, linuxMainFiber)
  storeLinuxFibers: setStateWord(fibersAt, one=1)
  goto make
:convertWindows
  becomeFiber: mainFiber = system.convertThreadToFiber(anywhere)
  storeMainFiber: setLink(me, ofFiber, mainFiber)
  storeFibers: setStateWord(fibersAt, one=1)
  goto make
:make
  takeTask: task = heap.take(taskBytes)
  storeThunk: setLink(task, ofThunk, thunk)
  storeFrame: setLink(task, ofFrame, frame)
  groupCheck: inGroup = compare.notEqualInt64(group, zero)
  if inGroup joinGroup parentCheck
:joinGroup
  groupOf: owner = machine.fromInt64(group)
  readRunning: runningCount = field(owner, ofRunning)
  readLimit: limit = field(owner, ofLimit)
  fullCheck: full = compare.greaterOrEqualInt64(runningCount, limit)
  if full refuseFull addMember
:refuseFull
  failFull: failNumber(fullLead="a task was started into a full task group (limit ", limit, fullTail="); `awaitSlot` waits for room")
  return zero
:addMember
  oneMore: moreRunning = math.addInt64(runningCount, one)
  storeRunning: setField(owner, ofRunning, moreRunning)
  readFirst: first = link(owner, ofFirst)
  storeMember: setLink(task, ofMember, first)
  storeFirst: setLink(owner, ofFirst, task)
  storeGroup: setLink(task, ofGroup, owner)
  readGroupCancelled: groupCancelled = field(owner, ofGroupCancelled)
  storeCancelled: setField(task, ofCancelled, groupCancelled)
  goto parentCheck
:parentCheck
  readMain: main = mainTask()
  mainCheck: fromMain = machine.equal(me, main)
  if fromMain prepare inherit
:inherit
  storeParent: setLink(task, ofParent, me)
  readParentCancelled: parentCancelled = field(me, ofCancelled)
  parentCancelledCheck: isParentCancelled = compare.notEqualInt64(parentCancelled, zero)
  if isParentCancelled markCancelled prepare
:markCancelled
  storeInherited: setField(task, ofCancelled, one)
  goto prepare
:prepare
  takeDepths: depths = heap.take(depthBytes)
  storeDepths: setLink(task, ofDepths, depths)
  storeInTask: setField(task, ofInTask, one)
  nothing: noFiber = machine.zero()
  osFiberCheck: onLinuxFiber = system.posix()
  if onLinuxFiber linuxFiber windowsFiber
:linuxFiber
  mapTaskStack: stack = kernel.mapStack(stackReserve)
  stackFailed: noStack = machine.equal(stack, noFiber)
  if noStack refuseStack keepStack
:keepStack
  takeFiber: linuxFiberBlock = heap.take(fiberBytes)
  storeBase: setLink(linuxFiberBlock, eight=8, stack)
  storeStackBytes: setField(linuxFiberBlock, sixteen=16, stackReserve)
  storeLinuxFiber: setLink(task, ofFiber, linuxFiberBlock)
  goto started
:windowsFiber
  findEntry: entryAt = machine.taskEntry()
  makeFiber: fiber = system.createFiberEx(stackCommit, stackReserve, floatSwitch=1, entryAt, task)
  failedCheck: failed = machine.equal(fiber, noFiber)
  if failed refuseStack start
:refuseStack
  failStack: failText(stackText="the runtime could not make a stack for a task")
  return zero
:start
  storeFiber: setLink(task, ofFiber, fiber)
  goto started
:started
  listIt: append(task)
  changed: notify()
  runIt: switchTo(task)
  if inGroup giveNone giveHandle
:giveNone
  return zero
:giveHandle
  handleOf: handle = machine.toInt64(task)
  return handle

op finishTask "End the running task: give back its call stack and depth counters, mark it ended, and count it out of its group"
  input task machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readTable: table = stateLink(sixtyFour=64)
  nowhere: anywhere = machine.zero()
  noTableCheck: noTable = machine.equal(table, anywhere)
  if noTable depths freeTable
:freeTable
  readRoom: room = stateWord(eighty=80)
  tableBytes: size = math.multiplyInt64(room, sixteen=16)
  freeIt: kernel.unmapMemory(table, size)
  clearTable: setStateLink(sixtyFour, anywhere)
  clearCount: setStateWord(seventyTwo=72, zero=0)
  clearRoom: setStateWord(eighty, zero)
  goto depths
:depths
  readDepths: depthTable = stateLink(threeNinetyTwo=392)
  giveDepths: heap.give(depthTable)
  clearDepths: setStateLink(threeNinetyTwo, anywhere)
  storeEnded: setField(task, ofState, ended)
  readGroup: group = link(task, ofGroup)
  noGroupCheck: noGroup = machine.equal(group, anywhere)
  if noGroup done countOut
:countOut
  readRunning: runningCount = field(group, ofRunning)
  oneLess: fewer = math.subtractInt64(runningCount, one=1)
  storeRunning: setField(group, ofRunning, fewer)
  goto done
:done
  changed: notify()
  return

op taskEntry "Where a task's fiber starts: set its stack floor, run its thunk with its frame, end it, and run the next task; it never returns: refined_task_entry"
  input task machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_task_entry"
:begin
  findHere: here = machine.stackAddress()
  hereValue: hereAt = machine.toInt64(here)
  findFloor: floor = math.subtractInt64(hereAt, stackBudget)
  storeFloor: setStateWord(eightyEight=88, floor)
  readThunk: thunk = link(task, ofThunk)
  readFrame: frame = link(task, ofFrame)
  runIt: machine.callWithAddress(thunk, frame)
  endIt: finishTask(task)
  findNext: next = pickAfter(task)
  nowhere: anywhere = machine.zero()
  nobodyCheck: nobody = machine.equal(next, anywhere)
  if nobody anyLive switch
:anyLive
  findLive: live = firstLive()
  switchLive: switchTo(live)
  goto lost
:switch
  switchNext: switchTo(next)
  goto lost
:lost
  failLost: failText(lostText="a task that ended was run again")
  return

op dropTask "Give back an ended task: its fiber, its place in the list, its frame, and itself"
  input task machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readFiber: fiber = link(task, ofFiber)
  osCheck: onLinux = system.posix()
  if onLinux dropLinux dropWindows
:dropLinux
  readBase: base = link(fiber, eight=8)
  readStackBytes: stackBytes = field(fiber, sixteen=16)
  unmapStack: kernel.unmapMemory(base, stackBytes)
  giveFiber: heap.give(fiber)
  goto unlistIt
:dropWindows
  deleteIt: system.deleteFiber(fiber)
  goto unlistIt
:unlistIt
  unlistTask: unlink(task)
  readFrame: frame = link(task, ofFrame)
  giveFrame: heap.give(frame)
  giveTask: heap.give(task)
  return

op join "Wait until a task has ended: refined_task_join"
  input handle Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_task_join"
:begin
  noTaskCheck: noTask = compare.equalInt64(handle, zero=0)
  if noTask done findTask
:findTask
  taskOf: task = machine.fromInt64(handle)
  goto eachTry
:eachTry loop=while max=forever
  readState: state = field(task, ofState)
  endedCheck: isEnded = compare.equalInt64(state, ended)
  if isEnded done waitMore
:waitMore in=eachTry
  nowhere: anywhere = machine.zero()
  waitIt: outcome = wait(joinText="a `join` waits for a task", never, zero, anywhere)
  goto eachTry
:done
  return

op releaseTask "Give back a task after its join has read its results: refined_task_release"
  input handle Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_task_release"
:begin
  noTaskCheck: noTask = compare.equalInt64(handle, zero=0)
  if noTask done drop
:drop
  taskOf: task = machine.fromInt64(handle)
  dropIt: dropTask(task)
  goto done
:done
  return

op cancelTask "Cancel a task and the tasks it started; its next cancellable wait ends with `cancelled`: refined_task_cancel"
  input handle Int64 copied
  effect use machine.memory
  uses memoryAccess
  abi c "refined_task_cancel"
:begin
  noTaskCheck: noTask = compare.equalInt64(handle, zero=0)
  if noTask done mark
:mark
  taskOf: task = machine.fromInt64(handle)
  markIt: cancelTree(task)
  changed: notify()
  goto done
:done
  return

## ---------------------------------------------------------------- groups

op groupNew "A task group with a limit on how many of its tasks run at once: refined_group_new"
  input limit Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_group_new"
:begin
  takeGroup: group = heap.take(groupBytes)
  storeLimit: setField(group, ofLimit, limit)
  handleOf: handle = machine.toInt64(group)
  return handle

op groupAwait "Wait until a group has room for another task: refined_group_await"
  input handle Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_group_await"
:begin
  groupOf: group = machine.fromInt64(handle)
  goto eachTry
:eachTry loop=while max=forever
  readRunning: runningCount = field(group, ofRunning)
  readLimit: limit = field(group, ofLimit)
  roomCheck: room = compare.lessThanInt64(runningCount, limit)
  if room done waitMore
:waitMore in=eachTry
  nowhere: anywhere = machine.zero()
  waitIt: outcome = wait(awaitText="an `awaitSlot` waits for room in a task group", never, zero=0, anywhere)
  goto eachTry
:done
  return

op allEnded "Whether every task of a group has ended"
  input group machine.Address copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let yes Bool true
  let no Bool false
:begin
  readCount: count = stateWord(countAt)
  readFirst: first = field(group, ofFirst)
  set at first
  goto eachMember
:eachMember loop=while max=count
  endCheck: atEnd = compare.equalInt64(at, zero=0)
  if atEnd allDone checkMember
:checkMember in=eachMember
  readState: state = wordOf(at, ofState)
  endedCheck: isEnded = compare.equalInt64(state, ended)
  if isEnded nextMember notDone
:nextMember in=eachMember
  readNext: next = wordOf(at, ofMember)
  set at next
  goto eachMember
:allDone
  return yes
:notDone
  return no

op groupJoin "Wait until every task of a group has ended, give them back, and start the group afresh: refined_group_join"
  input handle Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_group_join"
  let at Int64 0 mut
:begin
  groupOf: group = machine.fromInt64(handle)
  goto eachTry
:eachTry loop=while max=forever
  doneCheck: done = allEnded(group)
  if done giveBack waitMore
:waitMore in=eachTry
  nowhere: anywhere = machine.zero()
  waitIt: outcome = wait(joinText="a `join` waits for a task group", never, zero=0, anywhere)
  goto eachTry
:giveBack
  readCount: count = stateWord(countAt)
  readFirst: first = field(group, ofFirst)
  set at first
  goto eachMember
:eachMember loop=while max=count
  endCheck: atEnd = compare.equalInt64(at, zero)
  if atEnd fresh dropMember
:dropMember in=eachMember
  readNext: next = wordOf(at, ofMember)
  memberOf: member = machine.fromInt64(at)
  dropIt: dropTask(member)
  set at next
  goto eachMember
:fresh
  clearFirst: setField(group, ofFirst, zero)
  clearCancelled: setField(group, ofGroupCancelled, zero)
  return

op groupCancel "Cancel every task of a group and the tasks they started: refined_group_cancel"
  input handle Int64 copied
  effect use machine.memory
  uses memoryAccess
  abi c "refined_group_cancel"
  let at Int64 0 mut
:begin
  groupOf: group = machine.fromInt64(handle)
  storeCancelled: setField(group, ofGroupCancelled, one=1)
  readCount: count = stateWord(countAt)
  readFirst: first = field(group, ofFirst)
  set at first
  goto eachMember
:eachMember loop=while max=count
  endCheck: atEnd = compare.equalInt64(at, zero=0)
  if atEnd done cancelMember
:cancelMember in=eachMember
  memberOf: member = machine.fromInt64(at)
  markIt: cancelTree(member)
  readNext: next = wordOf(at, ofMember)
  set at next
  goto eachMember
:done
  changed: notify()
  return

op groupFree "Give back a group and any error it still holds: refined_group_free"
  input handle Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_group_free"
:begin
  groupOf: group = machine.fromInt64(handle)
  readError: error = link(group, ofError)
  giveError: heap.give(error)
  giveGroup: heap.give(group)
  return

op taskFail "D-48: the running task of a group failed: the group keeps the first error and cancels its other tasks; outside a group nothing happens: refined_task_fail"
  input error machine.Address copied
  input bytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_task_fail"
  let at Int64 0 mut
:begin
  readMe: me = stateWord(currentAt)
  noTaskCheck: noTask = compare.equalInt64(me, zero=0)
  if noTask done readGroup
:readGroup
  findGroup: groupValue = wordOf(me, ofGroup)
  noGroupCheck: noGroup = compare.equalInt64(groupValue, zero)
  if noGroup done firstCheck
:firstCheck
  groupOf: group = machine.fromInt64(groupValue)
  readError: kept = field(group, ofError)
  keptCheck: noError = compare.equalInt64(kept, zero)
  if noError keep changed
:keep
  takeError: copy = heap.take(bytes)
  copyError: machine.copy(copy, error, bytes)
  storeError: setLink(group, ofError, copy)
  storeBytes: setField(group, ofErrorBytes, bytes)
  storeCancelled: setField(group, ofGroupCancelled, one=1)
  readCount: count = stateWord(countAt)
  readFirst: first = field(group, ofFirst)
  set at first
  goto eachMember
:eachMember loop=while max=count
  endCheck: atEnd = compare.equalInt64(at, zero)
  if atEnd changed otherCheck
:otherCheck in=eachMember
  meCheck: isMe = compare.equalInt64(at, me)
  if isMe nextMember cancelMember
:cancelMember in=eachMember
  memberOf: member = machine.fromInt64(at)
  markIt: cancelTree(member)
  goto nextMember
:nextMember in=eachMember
  readNext: next = wordOf(at, ofMember)
  set at next
  goto eachMember
:changed
  noteIt: notify()
  goto done
:done
  return

op groupError "Copy a group's first error out for its join and forget it: 1 when there was one, otherwise 0: refined_group_error"
  input handle Int64 copied
  input out machine.Address copied
  input bytes Int64 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_group_error"
  let size Int64 0 mut
  let none32 Int32 0
  let one32 Int32 1
:begin
  groupOf: group = machine.fromInt64(handle)
  readError: error = link(group, ofError)
  nowhere: anywhere = machine.zero()
  noErrorCheck: noError = machine.equal(error, anywhere)
  if noError giveNone copy
:giveNone
  return none32
:copy
  readBytes: kept = field(group, ofErrorBytes)
  set size kept
  smallerCheck: smaller = compare.lessThanInt64(bytes, kept)
  if smaller useAsked copyOut
:useAsked
  set size bytes
  goto copyOut
:copyOut
  copyIt: machine.copy(out, error, size)
  giveIt: heap.give(error)
  clearError: setLink(group, ofError, anywhere)
  return one32

## ---------------------------------------------------------------- host targets: deadlines, clocks, sleep

op deadlineNever "time.Deadline.never: a deadline that never passes"
  invariant givesNever "The result slot holds -1"
  input results machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  storeNever: machine.storeInt64(results, never)
  return

op deadlineAfter "time.Deadline.after: the clock now plus a duration of milliseconds; a negative duration traps"
  invariant addsDuration "The result slot holds the clock's milliseconds now plus the duration"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readMilliseconds: milliseconds = slots.argOf(shape, args, zero=0)
  checkIt: span = duration(milliseconds, who="`time.Deadline.after` was given ")
  readNow: moment = now()
  addIt: deadline = math.addInt64(moment, span)
  storeDeadline: machine.storeInt64(results, deadline)
  return

op sleepFor "time.sleep: let other tasks run for a duration of milliseconds; a cancelled task wakes early; a negative duration traps"
  invariant sleeps "Returns once the duration has passed or the task is cancelled"
  input shape machine.Address copied
  input args machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readMilliseconds: milliseconds = slots.argOf(shape, args, zero=0)
  checkIt: span = duration(milliseconds, who="`time.sleep` was given ")
  readNow: moment = now()
  addIt: deadline = math.addInt64(moment, span)
  goto eachTry
:eachTry loop=while max=forever
  nowhere: anywhere = machine.zero()
  waitIt: outcome = wait(sleepText="a sleep", deadline, one=1, anywhere)
  wokeCheck: woke = compare.equalInt64(outcome, zero)
  if woke eachTry done
:done
  return

op clockNow "clock.now: milliseconds since 1970 on the system's clock"
  invariant readsWallClock "The result slot holds the system time in milliseconds since 1970"
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  osCheck: onLinux = system.posix()
  if onLinux linuxWall windowsWall
:linuxWall
  readWall: wall = kernel.wallClock()
  storeWall: machine.storeInt64(results, wall)
  return
:windowsWall
  findState: state = machine.state()
  findTime: timeAt = machine.offset(state, fileTimeAt)
  readTime: system.getSystemTimeAsFileTime(timeAt)
  loadTime: ticks = machine.loadInt64(timeAt)
  toMilliseconds: since1601 = math.divideInt64(ticks, tenThousand=10000)
  toEpoch: since1970 = math.subtractInt64(since1601, epochOffset=11644473600000)
  storeTime: machine.storeInt64(results, since1970)
  return

op clockMonotonic "clock.monotonic: milliseconds on a clock that never goes back"
  invariant readsMonotonic "The result slot holds the clock deadlines are read against"
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readNow: moment = now()
  storeTime: machine.storeInt64(results, moment)
  return

## ---------------------------------------------------------------- host targets: channels

op channelNew "channel.Channel.new: an empty channel of a capacity, owned by a region; the compiler adds 1 when its items are `String` (D-107); a capacity below 1 traps"
  invariant makesChannel "The result slot holds a new channel's handle, of the capacity, with no items"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readCapacity: capacity = slots.argOf(shape, args, zero=0)
  smallCheck: tooSmall = compare.lessThanInt64(capacity, one=1)
  if tooSmall refuse make
:refuse
  failIt: failNumber(smallLead="a channel needs a capacity of at least 1, not ", capacity, nothingText="")
  return
:make
  takeChannel: channel = heap.take(channelBytes)
  storeCapacity: setField(channel, ofCapacity, capacity)
  readRegion: region = slots.addressArg(shape, args, one)
  storeRegion: setLink(channel, ofRegion, region)
  readText: text = slots.flagArg(shape, args, two=2)
  storeText: setField(channel, ofText, text)
  storeSlots: setField(channel, ofSlots, minusOne=-1)
  makeHandle: handle = handles.newHandle(kindChannel, channel, region)
  storeHandle: machine.storeInt64(results, handle)
  return

op itemPlace "The address of the place of a channel's items at a position"
  input channel machine.Address copied
  input position Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  readSlots: itemSlots = field(channel, ofSlots)
  itemBytes: bytes = math.multiplyInt64(itemSlots, eight=8)
  placeOffset: offset = math.multiplyInt64(position, bytes)
  readItems: items = link(channel, ofItems)
  findPlace: place = machine.offset(items, offset)
  return place

op channelSend "channel.Channel.send: wait until the channel has room, then add an item (text copied into its region); closed, timedOut, or cancelled"
  invariant sendsItem "An open channel with room holds the item last; a closed one gives closed"
  input shape machine.Address copied
  input args machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok Int32 0
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findChannel: channel = handles.objectOf(handle, kindChannel)
  readItemSlots: itemSlots = slots.countOf(shape, one=1)
  readKnown: known = field(channel, ofSlots)
  unknownCheck: unknown = compare.lessThanInt64(known, zero)
  if unknown makeItems waitRoom
:makeItems
  storeSlots: setField(channel, ofSlots, itemSlots)
  readCapacity: capacity = field(channel, ofCapacity)
  slotBytes: itemBytes = math.multiplyInt64(itemSlots, eight=8)
  allBytes: bytes = math.multiplyInt64(capacity, itemBytes)
  takeItems: items = heap.take(bytes)
  storeItems: setLink(channel, ofItems, items)
  goto waitRoom
:waitRoom
  readDeadline: deadline = slots.argOf(shape, args, two=2)
  goto eachTry
:eachTry loop=while max=forever
  readClosed: closed = field(channel, ofClosed)
  closedCheck: isClosed = compare.notEqualInt64(closed, zero)
  if isClosed refuseClosed roomCheck
:roomCheck in=eachTry
  readCount: count = field(channel, ofCount)
  readRoom: room = field(channel, ofCapacity)
  checkRoom: hasRoom = compare.lessThanInt64(count, room)
  if hasRoom add waitMore
:waitMore in=eachTry
  nowhere: anywhere = machine.zero()
  waitIt: outcome = wait(sendText="a send waits on a full channel", deadline, one, anywhere)
  cancelledCheck: isCancelled = compare.equalInt64(outcome, two)
  if isCancelled refuseCancelled timedCheck
:timedCheck in=eachTry
  checkTimed: isTimed = compare.equalInt64(outcome, one)
  if isTimed refuseTimed eachTry
:refuseClosed
  failClosed: closedStatus = slots.failWith(payload, channelClosed, zero)
  return closedStatus
:refuseCancelled
  failCancelled: cancelledStatus = slots.failWith(payload, channelCancelled, zero)
  return cancelledStatus
:refuseTimed
  failTimed: timedStatus = slots.failWith(payload, channelTimedOut, zero)
  return timedStatus
:add
  readHead: head = field(channel, ofHead)
  endOf: end = math.addInt64(head, count)
  wrapIt: position = math.remainderInt64(end, room)
  findPlace: place = itemPlace(channel, position)
  findItem: item = slots.slotOf(shape, args, one)
  readText: text = field(channel, ofText)
  textCheck: isText = compare.notEqualInt64(text, zero)
  if isText copyText copySlots
:copyText
  readData: data = machine.loadAddress(item)
  findLength: lengthSlot = machine.offset(item, eight)
  readLength: length = machine.loadInt64(lengthSlot)
  readRegion: region = link(channel, ofRegion)
  putIt: slots.putText(region, data, length, place)
  goto counted
:copySlots
  slotBytes2: itemBytes2 = math.multiplyInt64(itemSlots, eight)
  copyIt: machine.copy(place, item, itemBytes2)
  goto counted
:counted
  oneMore: more = math.addInt64(count, one)
  storeCount: setField(channel, ofCount, more)
  changed: notify()
  return ok

op channelReceive "channel.Channel.receive: wait until the channel has an item, then take the first; closed (once it is empty), timedOut, or cancelled"
  invariant receivesItem "Gives the items in the order they were sent; a closed, empty channel gives closed"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok Int32 0
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findChannel: channel = handles.objectOf(handle, kindChannel)
  readDeadline: deadline = slots.argOf(shape, args, one=1)
  goto eachTry
:eachTry loop=while max=forever
  readCount: count = field(channel, ofCount)
  itemCheck: hasItem = compare.greaterThanInt64(count, zero)
  if hasItem take closedCheck
:closedCheck in=eachTry
  readClosed: closed = field(channel, ofClosed)
  checkClosed: isClosed = compare.notEqualInt64(closed, zero)
  if isClosed refuseClosed waitMore
:waitMore in=eachTry
  nowhere: anywhere = machine.zero()
  waitIt: outcome = wait(receiveText="a receive waits on an empty channel", deadline, one, anywhere)
  cancelledCheck: isCancelled = compare.equalInt64(outcome, two=2)
  if isCancelled refuseCancelled timedCheck
:timedCheck in=eachTry
  checkTimed: isTimed = compare.equalInt64(outcome, one)
  if isTimed refuseTimed eachTry
:refuseClosed
  failClosed: closedStatus = slots.failWith(payload, channelClosed, zero)
  return closedStatus
:refuseCancelled
  failCancelled: cancelledStatus = slots.failWith(payload, channelCancelled, zero)
  return cancelledStatus
:refuseTimed
  failTimed: timedStatus = slots.failWith(payload, channelTimedOut, zero)
  return timedStatus
:take
  readHead: head = field(channel, ofHead)
  findPlace: place = itemPlace(channel, head)
  readSlots: itemSlots = field(channel, ofSlots)
  slotBytes: itemBytes = math.multiplyInt64(itemSlots, eight=8)
  copyOut: machine.copy(results, place, itemBytes)
  nextHead: after = math.addInt64(head, one)
  readCapacity: capacity = field(channel, ofCapacity)
  wrapIt: wrapped = math.remainderInt64(after, capacity)
  storeHead: setField(channel, ofHead, wrapped)
  oneLess: fewer = math.subtractInt64(count, one)
  storeCount: setField(channel, ofCount, fewer)
  changed: notify()
  return ok

op channelClose "channel.Channel.close: close a channel; its items can still be received, and a send fails"
  invariant closesChannel "The channel is closed"
  input shape machine.Address copied
  input args machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findChannel: channel = handles.objectOf(handle, kindChannel)
  storeClosed: setField(channel, ofClosed, one=1)
  changed: notify()
  return

@tests

## Tests build a call's shape and slots in the last 4 KiB of machine.state: the shape from byte 61440, the
## arguments from 61952, the results from 62016, the payload at 62080. They run on the main program's task: nothing
## here starts a fiber.

op prepareShape "Make the tests' shape: a number of parameters, each of one slot but the one at a position, which has two"
  input params Int64 copied
  input wide Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let start Int64 0 mut
:begin
  findState: state = machine.state()
  findShape: shape = machine.offset(state, shapeAt=61440)
  storeParams: setField(shape, twentyFour=24, params)
  goto eachParam
:eachParam loop=while max=params
  doneCheck: done = compare.greaterOrEqualInt64(at, params)
  if done finish setParam
:setParam in=eachParam
  wideCheck: isWide = compare.equalInt64(at, wide)
  if isWide twoSlots oneSlot
:twoSlots in=eachParam
  storeTwo: storeParamSlots(shape, at, start, two=2)
  goto advance
:oneSlot in=eachParam
  storeOne: storeParamSlots(shape, at, start, one=1)
  goto advance
:advance in=eachParam
  readCount: count = slots.countOf(shape, at)
  moveStart: nextStart = math.addInt64(start, count)
  set start nextStart
  nextParam: after = math.addInt64(at, one)
  set at after
  goto eachParam
:finish
  return shape

op storeParamSlots "Store a parameter's slot count and first slot in the tests' shape"
  input shape machine.Address copied
  input parameter Int64 copied
  input first Int64 copied
  input count Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  parameterOffset: place = math.multiplyInt64(parameter, eight=8)
  countOffset: countPlace = math.addInt64(place, forty=40)
  storeSlots: setField(shape, countPlace, count)
  startOffset: startPlace = math.addInt64(place, twoThirtyTwo=232)
  storeStart: setField(shape, startPlace, first)
  return

op testSlot "The address of the tests' scratch at an offset from byte 61952 (arguments from 0, results from 64, the payload at 128)"
  input offset Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  findArgs: args = machine.offset(state, argsAt=61952)
  findSlot: slot = machine.offset(args, offset)
  return slot

test clockTest "Deadlines are the clock plus a duration, never is -1, the clocks read the time, and the generation counts changes"
  verifies now readsClock
  verifies deadlineNever givesNever
  verifies deadlineAfter addsDuration
  verifies clockNow readsWallClock
  verifies clockMonotonic readsMonotonic
  verifies notify countsChange
  verifies cancelled readsCancelled
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readBefore: before = now()
  findArgs: args = testSlot(zero=0)
  findResults: results = testSlot(sixtyFour=64)
  shapeOf: shape = prepareShape(one=1, minusOne=-1)
  storeDuration: machine.storeInt64(args, thousand=1000)
  after: deadlineAfter(shape, args, results)
  readDeadline: deadline = machine.loadInt64(results)
  readAfter: later = now()
  lowest: low = math.addInt64(before, thousand)
  highest: high = math.addInt64(later, thousand)
  lowCheck: aboveLow = compare.greaterOrEqualInt64(deadline, low)
  expectLow: test.assertTrue(aboveLow)
  highCheck: belowHigh = compare.lessOrEqualInt64(deadline, high)
  expectHigh: test.assertTrue(belowHigh)
  neverIt: deadlineNever(results)
  readNever: neverValue = machine.loadInt64(results)
  expectNever: test.assertEqualInt64(minusOne, neverValue)
  wall: clockNow(results)
  readWall: wallTime = machine.loadInt64(results)
  wallCheck: after2020 = compare.greaterThanInt64(wallTime, year2020=1577836800000)
  expectWall: test.assertTrue(after2020)
  monotonic: clockMonotonic(results)
  readMonotonic: monotonicTime = machine.loadInt64(results)
  monotonicCheck: notBefore = compare.greaterOrEqualInt64(monotonicTime, before)
  expectMonotonic: test.assertTrue(notBefore)
  readGeneration: generationBefore = generation()
  change: notify()
  readGenerationAfter: generationAfter = generation()
  wantGeneration: wanted = math.addInt64(generationBefore, one)
  expectGeneration: test.assertEqualInt64(wanted, generationAfter)
  readCancelled: isCancelled = cancelled()
  notCancelled: notIt = logic.not(isCancelled)
  expectNotCancelled: test.assertTrue(notIt)
  return

test sleepTest "A sleep with no other task waits out its duration, and a wait past its deadline gives 1"
  verifies sleepFor sleeps
  verifies wait waitsOnce
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readBefore: before = now()
  findArgs: args = testSlot(zero=0)
  shapeOf: shape = prepareShape(one=1, minusOne=-1)
  storeDuration: machine.storeInt64(args, thirty=30)
  sleepIt: sleepFor(shape, args)
  readAfter: after = now()
  elapsedOf: elapsed = math.subtractInt64(after, before)
  longEnough: waited = compare.greaterOrEqualInt64(elapsed, twenty=20)
  expectWaited: test.assertTrue(waited)
  nowhere: anywhere = machine.zero()
  waitPast: outcome = wait(what="a test's wait", before, one, anywhere)
  expectPast: test.assertEqualInt64(one, outcome)
  return

test channelTest "A channel gives its items back in order, keeps text in its region, refuses to send once closed, and still gives what it holds"
  verifies channelNew makesChannel
  verifies channelSend sendsItem
  verifies channelReceive receivesItem
  verifies channelClose closesChannel
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let label String "channel test"
  let word String "word"
:begin
  findLabel: labelAt = machine.addressOfString(label)
  labelLength: labelBytes = string.byteLength(label)
  make: region = regions.newRegion(capacity=4096, labelAt, labelBytes)
  findArgs: args = testSlot(zero=0)
  findResults: results = testSlot(sixtyFour=64)
  findPayload: payload = testSlot(oneTwentyEight=128)
  newShape: shapeNew = prepareShape(three=3, minusOne=-1)
  storeCapacity: machine.storeInt64(args, two=2)
  findRegionSlot: regionSlot = machine.offset(args, eight=8)
  storeRegion: machine.storeAddress(regionSlot, region)
  findTextSlot: textSlot = machine.offset(args, sixteen=16)
  storeText: machine.storeInt64(textSlot, one=1)
  newIt: channelNew(shapeNew, args, results)
  readHandle: handle = machine.loadInt64(results)
  sendShape: shapeSend = prepareShape(three, one)
  storeHandle: machine.storeInt64(args, handle)
  findWord: wordAt = machine.addressOfString(word)
  storeWord: machine.storeAddress(regionSlot, wordAt)
  storeLength: machine.storeInt64(textSlot, four=4)
  findDeadlineSlot: deadlineSlot = machine.offset(args, twentyFour=24)
  storeDeadline: machine.storeInt64(deadlineSlot, minusOne)
  sendIt: sent = channelSend(shapeSend, args, payload)
  sentWide: sentValue = convert.int32ToInt64(sent)
  expectSent: test.assertEqualInt64(zero, sentValue)
  closeShape: shapeClose = prepareShape(one, minusOne)
  closeIt: channelClose(shapeClose, args)
  sendAgain: refused = channelSend(shapeSend, args, payload)
  refusedWide: refusedValue = convert.int32ToInt64(refused)
  expectRefused: test.assertEqualInt64(one, refusedValue)
  receiveShape: shapeReceive = prepareShape(two, minusOne)
  findReceiveDeadline: receiveDeadline = machine.offset(args, eight)
  storeReceiveDeadline: machine.storeInt64(receiveDeadline, minusOne)
  receiveIt: received = channelReceive(shapeReceive, args, results, payload)
  receivedWide: receivedValue = convert.int32ToInt64(received)
  expectReceived: test.assertEqualInt64(zero, receivedValue)
  readItem: item = machine.loadAddress(results)
  findItemLength: itemLengthSlot = machine.offset(results, eight)
  readItemLength: itemLength = machine.loadInt64(itemLengthSlot)
  expectItemLength: test.assertEqualInt64(four, itemLength)
  compareItem: order = machine.compare(item, wordAt, four)
  orderWide: orderValue = convert.int32ToInt64(order)
  expectItem: test.assertEqualInt64(zero, orderValue)
  copiedCheck: same = machine.equal(item, wordAt)
  notSame: copied = logic.not(same)
  expectCopied: test.assertTrue(copied)
  receiveEmpty: emptied = channelReceive(shapeReceive, args, results, payload)
  emptiedWide: emptiedValue = convert.int32ToInt64(emptied)
  expectClosed: test.assertEqualInt64(one, emptiedValue)
  free: regions.release(region)
  return
