module start "The process's entry point: set the stack floor, run the program, and exit with its code"
  path start
  imports standard.machine standard.system standard.convert standard.math kernel heap
  exports none

capability memoryAccess "Authority to find the stack and keep its floor in machine.state" use machine.memory none

capability systemCalls "Authority to end the process with the program's exit code" use system.calls none

## The stack floor is in machine.state at byte 88 (frames' part of it). An executable's main thread has a stack of
## 256 MiB (native.py links it so on Windows); a recursive operation traps when its frame lies more than 248 MiB
## below the entry's, which leaves 8 MiB for the runtime and the operating system. D-139: a Linux process starts on
## the stack the kernel gives it (8 MiB as a rule), so the entry keeps what that stack holds (argc, argv, envp),
## ignores SIGPIPE as Python does (a write to a closed pipe is then EPIPE, not the end of the program), and runs the
## program on a stack of 256 MiB of its own, with the same floor.
constant floorAt "Where the stack floor is kept, in machine.state" Int64 88

constant stackBudget "How far below the entry's frame the stack floor is: 256 MiB less 8 MiB" Int64 260046848

constant stackBytes "The bytes of the program's stack on Linux: 256 MiB" Int64 268435456

## D-160: a program that wrote to the C library's streams (through `ffi`) has them flushed when it ends, as the C
## library's exit flushes them: the stdio module keeps the address of fflush at machine.state byte 2336 once a stream
## is first used, and the entry calls it with NULL before the process ends.
constant flushHookAt "Where the address of the C library's fflush is kept once a C stream was used, in machine.state" Int64 2336

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

op flushStreams "Call the C library's fflush(NULL) when a C stream was used, so what the streams hold is written"
  effect use machine.memory
  uses memoryAccess
:begin
  state = machine.state()
  hookCell = machine.offset(state, flushHookAt)
  hook = machine.loadAddress(hookCell)
  nowhere = machine.zero()
  unused = machine.equal(hook, nowhere)
  if unused done flush
:flush
  machine.callWithAddress(hook, nowhere)
  return
:done
  return

op entry "Start the process: set the stack floor, run the program's entry operation, and end the process with its exit code: refined_entry. On Linux the kernel's stack, with argc, argv, and envp on it, is the input"
  input stack machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_entry"
:begin
  osCheck: onLinux = system.posix()
  if onLinux linuxStart windowsStart
:linuxStart
  keepStart: kernel.initialStack(stack)
  takeAction: action = heap.take(thirtyTwo=32)
  storeIgnore: machine.storeInt64(action, ignoreHandler=1)
  nowhere: anywhere = machine.zero()
  ignorePipe: ignored = system.rtSigaction(brokenPipeSignal=13, action, anywhere, maskBytes=8)
  giveAction: heap.give(action)
  mapIt: programStack = kernel.mapStack(stackBytes)
  failedCheck: noStack = machine.equal(programStack, anywhere)
  if noStack windowsStart runOnStack
:runOnStack
  findTop: top = machine.offset(programStack, stackBytes)
  topValue: topAt = machine.toInt64(top)
  findLinuxFloor: linuxFloor = math.subtractInt64(topAt, stackBudget)
  findLinuxState: linuxState = machine.state()
  findLinuxFloorSlot: linuxFloorSlot = machine.offset(linuxState, floorAt)
  storeLinuxFloor: machine.storeInt64(linuxFloorSlot, linuxFloor)
  runLinux: linuxCode = machine.runEntryOnStack(top)
  flushStreams()
  exitLinux: endProcess(linuxCode)
  return
:windowsStart
  findHere: here = machine.stackAddress()
  hereValue: hereAt = machine.toInt64(here)
  findFloor: floor = math.subtractInt64(hereAt, stackBudget)
  findState: state = machine.state()
  findFloorSlot: floorSlot = machine.offset(state, floorAt)
  storeFloor: machine.storeInt64(floorSlot, floor)
  run: code = machine.runEntry()
  flushStreams()
  exit: endProcess(code)
  return
