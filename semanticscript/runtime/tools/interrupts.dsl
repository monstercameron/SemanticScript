module interrupts "Interrupts for a standalone executable: the signal targets, and the handler the operating system calls on an interrupt"
  path interrupts
  imports standard.machine standard.system standard.math standard.compare standard.convert standard.test kernel heap slots tasks
  exports signalCall

capability memoryAccess "Authority to keep whether an interrupt came in machine.state and read a call's slots" use machine.memory none

capability systemCalls "Authority to install the interrupt handler, wake the scheduler, and end the process on a second interrupt" use system.calls none

## D-147: as `refined run` handles SIGINT for a program that reads `signal`: the first interrupt sets a flag the
## program reads (`signal.interrupted`) and ends a `signal.waitForInterrupt`, the second ends the process with exit
## code 130. A program that calls a signal target installs the handler before its entry runs (native.py calls
## `refined_signals_start` first, as the JIT installs its handler before it runs the program): on Windows a console
## control handler (SetConsoleCtrlHandler) for CTRL_C_EVENT only, as Python maps CTRL+C alone to SIGINT, called on a
## thread the system makes; on Linux an rt_sigaction handler for SIGINT, with SA_RESTART so reads and writes go on,
## and SA_RESTORER, its return through the runtime's rt_sigreturn trampoline. The handler counts a change in the
## scheduler's generation, so a task waiting for the interrupt goes on, and on Windows sets an event the scheduler's
## sleep also waits on (an interrupt cuts a Linux sleep short by itself, as the signal ends `poll`).
## machine.state bytes 1216 to 1247 belong to this module: 1216 whether an interrupt came, 1224 whether the handler
## is installed, 1232 the Windows event the scheduler waits on (tasks reads it there).
constant interruptedAt "Where whether an interrupt came is kept, in machine.state" Int64 1216

constant installedAt "Where whether the handler is installed is kept, in machine.state" Int64 1224

constant eventAt "Where the Windows event an interrupt sets is kept, in machine.state" Int64 1232

constant generationAt "Where the scheduler's generation is kept, in machine.state (the tasks module's)" Int64 472

constant timedOut "signal.SignalError.timedOut, numbered from 1" Int32 1

constant cancelledError "signal.SignalError.cancelled, numbered from 1" Int32 2

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

op stateWord "A whole number of machine.state"
  input offset Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findSlot: slot = kernel.stateAt(offset)
  readSlot: value = machine.loadInt64(slot)
  return value

op setStateWord "Store a whole number in machine.state"
  input offset Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  findSlot: slot = kernel.stateAt(offset)
  storeSlot: machine.storeInt64(slot, value)
  return

op interruptHandler "What the operating system calls on an interrupt: CTRL_C_EVENT on Windows, SIGINT on Linux. The first sets the flag, counts a change for the scheduler, and on Windows sets its event; the second ends the process with exit code 130. Any other console event is left to the system: refined_interrupt_handler"
  input which Int32 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_interrupt_handler"
  let handled Int32 1
  let notHandled Int32 0
:begin
  osCheck: onLinux = system.posix()
  if onLinux interrupt eventCheck
:eventCheck
  ctrlCCheck: isCtrlC = compare.equalInt32(which, notHandled)
  if isCtrlC interrupt leave
:leave
  return notHandled
:interrupt
  readFlag: flag = stateWord(interruptedAt)
  secondCheck: second = compare.notEqualInt64(flag, zero=0)
  if second exit first
:exit
  exitIt: endProcess(interruptedCode=130)
  return handled
:first
  storeFlag: setStateWord(interruptedAt, one=1)
  readGeneration: generation = stateWord(generationAt)
  moreGeneration: next = math.addInt64(generation, one)
  storeGeneration: setStateWord(generationAt, next)
  wakeCheck: onWindows = system.posix()
  if onWindows done wake
:wake
  findEvent: eventSlot = kernel.stateAt(eventAt)
  readEvent: event = machine.loadAddress(eventSlot)
  setIt: wasSet = system.setEvent(event)
  return handled
:done
  return handled

op installInterrupts "Install the interrupt handler before the program's entry runs, as `refined run` installs its handler for a program that reads `signal`: SetConsoleCtrlHandler on Windows (with the event the scheduler's sleep waits on), rt_sigaction for SIGINT on Linux: refined_signals_start"
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_signals_start"
  let sigint Int64 2
  let flags Int64 335544320
:begin
  storeInstalled: setStateWord(installedAt, one=1)
  findHandler: handler = machine.interruptHandler()
  osCheck: onLinux = system.posix()
  if onLinux linuxInstall windowsInstall
:windowsInstall
  nowhere: anywhere = machine.zero()
  makeEvent: event = system.createEventW(anywhere, autoReset=0, noSignal=0, anywhere)
  findEvent: eventSlot = kernel.stateAt(eventAt)
  storeEvent: machine.storeAddress(eventSlot, event)
  addHandler: added = system.setConsoleCtrlHandler(handler, addIt=1)
  return
:linuxInstall
  takeAction: block = heap.take(thirtyTwo=32)
  storeHandler: machine.storeAddress(block, handler)
  findFlags: flagsSlot = machine.offset(block, eight=8)
  storeFlags: machine.storeInt64(flagsSlot, flags)
  findRestorer: restorerSlot = machine.offset(block, sixteen=16)
  restorerOf: restorer = machine.signalRestorer()
  storeRestorer: machine.storeAddress(restorerSlot, restorer)
  noOld: noAddress = machine.zero()
  installIt: installed = system.rtSigaction(sigint, block, noAddress, eight)
  return

## ---------------------------------------------------------------- targets

op interruptedTarget "signal.interrupted: whether the first interrupt has come"
  input results machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  readFlag: flag = stateWord(interruptedAt)
  storeIt: machine.storeInt64(results, flag)
  return

op waitTarget "signal.waitForInterrupt: wait until the first interrupt comes; timedOut at the deadline, cancelled when the task is, a wait no interrupt could end (no deadline, nothing else to wait for) a deadlock, as under `refined run`"
  input shape machine.Address copied
  input args machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok Int32 0
  let forever Int64 9223372036854775807
:begin
  readDeadline: deadline = slots.argOf(shape, args, zero=0)
  nowhere: anywhere = machine.zero()
  goto eachTry
:eachTry loop=while max=forever
  readFlag: flag = stateWord(interruptedAt)
  cameCheck: came = compare.notEqualInt64(flag, zero)
  if came done waitIt
:waitIt in=eachTry
  waitOnce: outcome = tasks.wait(waitText="a wait for an interrupt", deadline, one=1, anywhere)
  cancelledCheck: isCancelled = compare.equalInt64(outcome, two=2)
  if isCancelled giveCancelled timedCheck
:timedCheck in=eachTry
  checkTimed: isTimed = compare.equalInt64(outcome, one)
  if isTimed giveTimedOut eachTry
:giveTimedOut
  timedStatus: status1 = slots.failWith(payload, timedOut, zero)
  return status1
:giveCancelled
  cancelledStatus: status2 = slots.failWith(payload, cancelledError, zero)
  return status2
:done
  return ok

op signalCall "Run a signal target by its place among them (1 interrupted, 2 waitForInterrupt): 0, or an error's variant number with its payload stored"
  invariant runsSignal "interrupted gives whether the first interrupt came; waitForInterrupt ends when it comes, at its deadline, or when its task is cancelled"
  input which Int64 copied
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
  readCheck: isRead = compare.equalInt64(which, one=1)
  if isRead runRead runWait
:runRead
  readIt: interruptedTarget(results)
  return ok
:runWait
  waitIt: status = waitTarget(shape, args, payload)
  return status

@tests

test signalTest "No interrupt has come in a test, so interrupted is false and a wait with a passed deadline times out; the handler leaves every console event but CTRL+C to the system"
  verifies signalCall runsSignal
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findShape: shape = kernel.stateAt(shapeAt=61440)
  findArgs: args = kernel.stateAt(argsOffset=61952)
  findResults: results = kernel.stateAt(resultsOffset=62016)
  findPayload: payload = kernel.stateAt(payloadOffset=62080)
  findCounts: counts = machine.offset(shape, forty=40)
  storeCount: machine.storeInt64(counts, one=1)
  findStarts: starts = machine.offset(shape, twoThirtyTwo=232)
  storeStart: machine.storeInt64(starts, zero=0)
  findParams: paramsAt = machine.offset(shape, twentyFour=24)
  storeParams: machine.storeInt64(paramsAt, one)
  readIt: readStatus = signalCall(one, shape, args, results, payload)
  readFlag: flag = machine.loadInt64(results)
  test.assertEqualInt64(zero, flag)
  storeDeadline: machine.storeInt64(args, zero)
  waitIt: waitStatus = signalCall(two=2, shape, args, results, payload)
  widenWait: waitValue = convert.int32ToInt64(waitStatus)
  test.assertEqualInt64(one, waitValue)
  onLinux: linux = system.posix()
  if linux done breakEvent
:breakEvent
  leaveIt: left = interruptHandler(ctrlBreak=1)
  widenLeft: leftValue = convert.int32ToInt64(left)
  test.assertEqualInt64(zero, leftValue)
  goto done
:done
  return
