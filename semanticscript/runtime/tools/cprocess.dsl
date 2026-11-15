module cprocess "setjmp.h, signal.h, abort, and system for the runtime's C library: jumps back to a setjmp, signal handlers, raise, and commands run by the shell (D-163, D-164)"
  path cprocess
  imports standard.machine standard.system standard.string standard.math standard.compare standard.convert standard.bits standard.logic standard.test kernel heap wide clibrary
  exports none

capability memoryAccess "Authority to read and write jump buffers, handler tables, and the memory C callers hand the library" use machine.memory none

capability systemCalls "Authority to install signal handlers, send signals, run the shell, and end the process" use system.calls none

## D-164: signal installs a handler with rt_sigaction on Linux, as glibc's signal does (BSD semantics: SA_RESTART, the
## handler stays installed, the signal is blocked while its handler runs), returning through the runtime's restorer;
## raise is kill(getpid(), sig), so a handler runs before raise returns. Windows has no such signals: there the library
## keeps a table of handlers (glibc's signal numbers), and raise calls the signal's handler, ignores it for SIG_IGN, and
## for SIG_DFL ends the process with exit code 3, as the Microsoft C runtime's raise does; nothing outside raise and
## abort delivers a signal on Windows. abort raises SIGABRT, so a handler runs; if it returns, the default action is
## taken. machine.state bytes 27952 to 28479 belong to this module: from 27960 the Windows handler of each signal, 1 to 64.
constant handlersAt "Where the Windows handler of signal 0 would be, in machine.state; signal n's is 8n bytes on" Int64 27952

constant forever "The bound of a loop that ends when its work does" Int64 9223372036854775807

constant invalidError "EINVAL: an argument the function does not take" Int32 22

op endProcess "End the process with an exit code: ExitProcess on Windows, exit_group on Linux (D-138)"
  input code Int32 copied
  effect use system.calls
  uses systemCalls
:begin
  onLinux = system.linux()
  if onLinux linuxExit windowsExit
:linuxExit
  calc wideCode = convert.int32ToInt64(code)
  system.exitGroup(wideCode)
  return
:windowsExit
  system.exitProcess(code)
  return

## ---------------------------------------------------------------- setjmp.h (D-163)

op saveJump "setjmp: keep where its caller is, to come back by longjmp; 0 now (the compiler emits this operation as the routine itself)"
  input buffer machine.Address copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "setjmp"
:begin
  result = machine.saveContext(buffer)
  return result

op saveJumpBare "_setjmp: setjmp, the name glibc's setjmp macro calls"
  input buffer machine.Address copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "_setjmp"
:begin
  result = machine.saveContext(buffer)
  return result

op saveJumpMasked "__sigsetjmp: setjmp, the name sigsetjmp calls; the signal mask is not kept (D-163)"
  input buffer machine.Address copied
  input saveMask Int32 copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "__sigsetjmp"
:begin
  result = machine.saveContext(buffer)
  return result

op jump "longjmp: return from the setjmp that filled a buffer again, with a value (1 for 0)"
  input buffer machine.Address copied
  input value Int32 copied
  effect use machine.memory
  uses memoryAccess
  abi library "longjmp"
:begin
  machine.resumeContext(buffer, value)
  return

op jumpBare "_longjmp: longjmp"
  input buffer machine.Address copied
  input value Int32 copied
  effect use machine.memory
  uses memoryAccess
  abi library "_longjmp"
:begin
  machine.resumeContext(buffer, value)
  return

op jumpMasked "siglongjmp: longjmp (no signal mask was kept)"
  input buffer machine.Address copied
  input value Int32 copied
  effect use machine.memory
  uses memoryAccess
  abi library "siglongjmp"
:begin
  machine.resumeContext(buffer, value)
  return

op jumpChecked "__longjmp_chk: longjmp, the name glibc's headers call under _FORTIFY_SOURCE"
  input buffer machine.Address copied
  input value Int32 copied
  effect use machine.memory
  uses memoryAccess
  abi library "__longjmp_chk"
:begin
  machine.resumeContext(buffer, value)
  return

## ---------------------------------------------------------------- signal.h (D-164)

op handlerCell "The cell of a signal's Windows handler"
  input signalNumber Int32 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  calc cell = kernel.stateAt(handlersAt + convert.int32ToInt64(signalNumber) * 8)
  return cell

op setHandler "signal: install a handler for a signal (SIG_DFL 0, SIG_IGN 1, or a function), giving the one before it; SIG_ERR (-1) with EINVAL for a signal that has none (below 1, above 64, SIGKILL, SIGSTOP)"
  invariant installsHandlers "The handler given is the one the next call gives back"
  input signalNumber Int32 copied
  input handler machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "signal"
:begin
  calc refused = machine.fromInt64(-1)
  when signalNumber < 1 || signalNumber > 64 || signalNumber == 9 || signalNumber == 19 refuse install
:refuse
  clibrary.setErrno(invalidError)
  return refused
:install
  onLinux = system.linux()
  if onLinux linux windows
:windows
  cell = handlerCell(signalNumber)
  previous = machine.loadAddress(cell)
  machine.storeAddress(cell, handler)
  return previous
:linux
  action = heap.take(32)
  old = heap.take(32)
  machine.storeAddress(action, handler)
  calc flagsAt = action + 8
  machine.storeInt64(flagsAt, 335544320)
  calc restorerAt = action + 16
  restorer = machine.signalRestorer()
  machine.storeAddress(restorerAt, restorer)
  calc wideSignal = convert.int32ToInt64(signalNumber)
  result = system.rtSigaction(wideSignal, action, old, 8)
  oldHandler = machine.loadAddress(old)
  heap.give(action)
  heap.give(old)
  when result < 0 failed done
:failed
  clibrary.setErrno(clibrary.lowInt32(0 - result))
  return refused
:done
  return oldHandler

op raiseSignal "raise: send a signal to the process, so its handler runs before raise returns (on Windows, the table's handler, SIG_IGN nothing, SIG_DFL the end of the process with exit code 3); 0, or -1 with EINVAL for a number that is no signal"
  invariant raisesSignals "A handler installed for the signal runs, with the signal's number"
  input signalNumber Int32 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "raise"
  let fine Int32 0
  let failure Int32 -1
:begin
  when signalNumber < 1 || signalNumber > 64 refuse send
:refuse
  clibrary.setErrno(invalidError)
  return failure
:send
  onLinux = system.linux()
  if onLinux linux windows
:linux
  self = system.getpid()
  calc wideSignal = convert.int32ToInt64(signalNumber)
  result = system.kill(self, wideSignal)
  when result < 0 failed sent
:failed
  clibrary.setErrno(clibrary.lowInt32(0 - result))
  return failure
:sent
  return fine
:windows
  cell = handlerCell(signalNumber)
  handler = machine.loadAddress(cell)
  calc handlerValue = machine.toInt64(handler)
  when handlerValue == 1 ignored notIgnored
:ignored
  return fine
:notIgnored
  when handlerValue == 0 defaultAction call
:defaultAction
  endProcess(3)
  return fine
:call
  calc argument = machine.fromInt64(convert.int32ToInt64(signalNumber))
  machine.callWithAddress(handler, argument)
  return fine

op abortProcess "abort: raise SIGABRT, so a handler runs; if it returns, SIGABRT's default action: the end of the process by the signal on Linux, exit code 3 on Windows"
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "abort"
:begin
  raiseSignal(6)
  onLinux = system.linux()
  if onLinux linux windows
:linux
  action = heap.take(32)
  nowhere = machine.zero()
  system.rtSigaction(6, action, nowhere, 8)
  self = system.getpid()
  system.kill(self, 6)
  endProcess(134)
  return
:windows
  endProcess(3)
  return

## ---------------------------------------------------------------- system (D-162)

op runCommand "system: run a command with the system's shell and wait for it: /bin/sh -c on Linux (the wait status, as glibc gives it; 127 << 8 when the shell cannot run), cmd.exe /c on Windows (its exit code << 8, the same form); NULL asks whether there is a shell: 1 when /bin/sh exists on Linux, 1 on Windows"
  invariant runsShell "A command's exit code comes back in the wait status's second byte"
  input command machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "system"
  let shellPath String "/bin/sh"
  let shellName String "sh"
  let dashC String "-c"
  let windowsPrefix String "cmd.exe /c "
  let failure Int32 -1
  let present Int32 1
  let absent Int32 0
:begin
  nowhere = machine.zero()
  onLinux = system.linux()
  when command == nowhere ask run
:ask
  if onLinux askLinux hasShell
:askLinux
  path = cTextOf(shellPath)
  statBlock = heap.take(160)
  found = system.newfstatat(-100, path, statBlock, 0)
  heap.give(statBlock)
  heap.give(path)
  when found == 0 hasShell noShell
:hasShell
  return present
:noShell
  return absent
:run
  if onLinux linux windows
:linux
  shell = cTextOf(shellPath)
  name = cTextOf(shellName)
  flag = cTextOf(dashC)
  arguments = heap.take(32)
  machine.storeAddress(arguments, name)
  calc secondAt = arguments + 8
  machine.storeAddress(secondAt, flag)
  calc thirdAt = arguments + 16
  machine.storeAddress(thirdAt, command)
  environment = kernel.environmentVector()
  child = system.fork()
  when child == 0 inChild parent
:inChild
  system.execve(shell, arguments, environment)
  system.exit(127)
  return failure
:parent
  heap.give(shell)
  heap.give(name)
  heap.give(flag)
  heap.give(arguments)
  when child < 0 forkFailed wait
:forkFailed
  clibrary.setErrno(clibrary.lowInt32(0 - child))
  return failure
:wait
  statusCell = heap.take(8)
  goto waiting
:waiting loop=while max=forever
  waited = system.wait4(child, statusCell, 0, nowhere)
  when waited == -4 waiting waitDone
:waitDone
  status = machine.loadInt32(statusCell)
  heap.give(statusCell)
  when waited < 0 waitFailed reported
:waitFailed
  clibrary.setErrno(clibrary.lowInt32(0 - waited))
  return failure
:reported
  return status
:windows
  prefixAt = machine.addressOfString(windowsPrefix)
  commandLength = clibrary.cStringLength(command)
  calc lineBytes = 11 + commandLength
  line = heap.take(lineBytes + 1)
  machine.copy(line, prefixAt, 11)
  calc commandAt = line + 11
  machine.copy(commandAt, command, commandLength)
  wideLine = wide.widen(line, lineBytes)
  heap.give(line)
  startup = heap.take(104)
  machine.storeInt32(startup, 104)
  information = heap.take(24)
  created = system.createProcessW(nowhere, wideLine, nowhere, nowhere, 1, 0, nowhere, nowhere, startup, information)
  heap.give(wideLine)
  heap.give(startup)
  when created == 0 createFailed waitWindows
:createFailed
  heap.give(information)
  clibrary.setErrno(2)
  return failure
:waitWindows
  process = machine.loadAddress(information)
  calc threadAt = information + 8
  thread = machine.loadAddress(threadAt)
  system.waitForSingleObject(process, -1)
  codeCell = heap.take(8)
  system.getExitCodeProcess(process, codeCell)
  code = machine.loadInt32(codeCell)
  heap.give(codeCell)
  system.closeHandle(process)
  system.closeHandle(thread)
  heap.give(information)
  calc shifted = clibrary.lowInt32((convert.int32ToInt64(code) & 255) << 8)
  return shifted

op cTextOf "A text as a C string in a new heap block"
  input text String borrowed
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  bytes = string.byteLength(text)
  calc block = heap.take(bytes + 1)
  at = machine.addressOfString(text)
  machine.copy(block, at, bytes)
  return block

@tests

test signalTest "signal gives back the handler it replaced, and raise of an ignored signal returns 0; system(NULL) finds a shell"
  verifies setHandler installsHandlers
  verifies raiseSignal raisesSignals
  verifies runCommand runsShell
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  ignore = machine.fromInt64(1)
  first = setHandler(10, ignore)
  second = setHandler(10, ignore)
  test.assertTrue(second == ignore)
  raised = raiseSignal(10)
  test.assertTrue(raised == 0)
  setHandler(10, first)
  nowhere = machine.zero()
  shell = runCommand(nowhere)
  test.assertTrue(shell == 1)
  bad = raiseSignal(0)
  test.assertTrue(bad == -1)
  return
