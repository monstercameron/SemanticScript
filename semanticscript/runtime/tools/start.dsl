module start "The process's entry point: set the stack floor, run the program, and exit with its code"
  path start
  imports standard.machine standard.system standard.math
  exports none

capability memoryAccess "Authority to find the stack and keep its floor in machine.state" use machine.memory none

capability systemCalls "Authority to end the process with the program's exit code" use system.calls none

## The stack floor is in machine.state at byte 88 (frames' part of it). An executable's main thread has a stack of
## 256 MiB (native.py links it so); a recursive operation traps when its frame lies more than 248 MiB below the
## entry's, which leaves 8 MiB for the runtime and the operating system, as the C runtime's entry does.
constant floorAt "Where the stack floor is kept, in machine.state" Int64 88

constant stackBudget "How far below the entry's frame the stack floor is: 256 MiB less 8 MiB" Int64 260046848

op entry "Start the process: set the stack floor, run the program's entry operation, and end the process with its exit code: refined_entry"
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_entry"
:begin
  findHere: here = machine.stackAddress()
  hereValue: hereAt = machine.toInt64(here)
  findFloor: floor = math.subtractInt64(hereAt, stackBudget)
  findState: state = machine.state()
  findFloorSlot: floorSlot = machine.offset(state, floorAt)
  storeFloor: machine.storeInt64(floorSlot, floor)
  run: code = machine.runEntry()
  exit: system.exitProcess(code)
  return
