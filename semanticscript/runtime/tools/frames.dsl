module frames "The call stack a trap prints, recursion depth and the stack floor, and traps"
  path frames
  imports standard.machine standard.system standard.string standard.math standard.compare standard.convert standard.logic standard.test memory numbers output
  exports pushFrame popFrame report holdResource letGoResource

capability memoryAccess "Authority to keep the call stack and the depth counters in memory" use machine.memory none

capability systemCalls "Authority to write a trap's report, take memory for the call stack, and end the process" use system.calls none

## machine.state bytes 64 to 127 belong to this module: 64 the address of the call stack's table, 72 how many
## frames are on it, 80 how many the table holds, 88 the stack floor (set by `start`), 96 to 127 the digits of a
## count being written; bytes 8192 to 40959 are the depth counters of 4096 recursive operations (the main
## program's: a task's are in a heap block of the same size, whose address the tasks module puts at 392 while the
## task runs); bytes 384 to 447: 384 not 0 while a task runs, 392 the address of the running task's depth counters
## (0 for the main program's), 400 the address of the table of resources a trap releases (D-51), 408 how many it
## holds, 416 how many it has room for. A resource is 16 bytes: its kind (1 an open file, 2 a running child
## process), then the operating system's handle.
constant framesAt "Where the address of the call stack's table is kept, in machine.state" Int64 64

constant countAt "Where the number of frames on the call stack is kept, in machine.state" Int64 72

constant capacityAt "Where the number of frames the table holds is kept, in machine.state" Int64 80

constant floorAt "Where the stack floor is kept, in machine.state: an address below which a recursive operation traps, or 0" Int64 88

constant digitsAt "Where a count's digits are put together, in machine.state" Int64 96

constant depthsAt "Where the depth counters start, in machine.state: one Int64 per recursive operation, by the number the compiler gives it" Int64 8192

constant depthCount "How many recursive operations have a depth counter" Int64 4096

constant inTaskAt "Where whether a task is running is kept, in machine.state: not 0 while one is" Int64 384

constant depthTableAt "Where the address of the running task's depth counters is kept, in machine.state: 0 for the main program's" Int64 392

constant resourcesAt "Where the address of the table of resources a trap releases is kept, in machine.state" Int64 400

constant resourceCountAt "Where the number of resources held is kept, in machine.state" Int64 408

constant resourceCapacityAt "Where the number of resources the table has room for is kept, in machine.state" Int64 416

constant frameBytes "The size of a frame in the table: the address of the operation's name, then the name's length" Int64 16

constant firstCapacity "How many frames the table holds when it is first made; it doubles when full" Int64 4096

constant shownRuns "How many lines of the call stack a trap prints before saying how many more there are" Int64 12

## ---------------------------------------------------------------- the call stack

op pushFrame "Put an operation's name on the call stack, as each compiled operation does when it starts"
  invariant keepsName "The frame is the top of the call stack and holds the name's address and length; the table grows when full"
  input name machine.Address copied
  input bytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_frame_push"
  let capacity Int64 0 mut
:begin
  findState: state = machine.state()
  findCount: countSlot = machine.offset(state, countAt)
  readCount: count = machine.loadInt64(countSlot)
  findCapacity: capacitySlot = machine.offset(state, capacityAt)
  readCapacity: held = machine.loadInt64(capacitySlot)
  findTable: tableSlot = machine.offset(state, framesAt)
  fullCheck: full = compare.greaterOrEqualInt64(count, held)
  if full grow keep
:grow
  emptyCheck: empty = compare.equalInt64(held, zero=0)
  if empty first double
:first
  set capacity firstCapacity
  goto allocate
:double
  twice: doubled = math.multiplyInt64(held, two=2)
  set capacity doubled
  goto allocate
:allocate
  sizeOf: size = math.multiplyInt64(capacity, frameBytes)
  nowhere: anywhere = machine.zero()
  takeMemory: table = system.virtualAlloc(anywhere, size, commitAndReserve=12288, readWrite=4)
  failedCheck: failed = machine.equal(table, anywhere)
  if failed counted move
:move
  readOld: old = machine.loadAddress(tableSlot)
  usedOf: used = math.multiplyInt64(held, frameBytes)
  copyOld: machine.copy(table, old, used)
  storeTable: machine.storeAddress(tableSlot, table)
  storeCapacity: machine.storeInt64(capacitySlot, capacity)
  hadCheck: hadTable = compare.greaterThanInt64(held, zero)
  if hadTable release keep
:release
  freeOld: freed = system.virtualFree(old, zero, releaseMemory=32768)
  goto keep
:keep
  readTable: current = machine.loadAddress(tableSlot)
  findOffset: offset = math.multiplyInt64(count, frameBytes)
  findFrame: frame = machine.offset(current, offset)
  storeName: machine.storeAddress(frame, name)
  findLength: lengthSlot = machine.offset(frame, eight=8)
  storeLength: machine.storeInt64(lengthSlot, bytes)
  goto counted
:counted
  addFrame: nextCount = math.addInt64(count, one=1)
  storeCount: machine.storeInt64(countSlot, nextCount)
  return

op popFrame "Take the top frame off the call stack, as each compiled operation does when it returns"
  invariant dropsTop "The call stack holds one frame fewer, and never fewer than none"
  effect use machine.memory
  uses memoryAccess
  abi c "refined_frame_pop"
:begin
  findState: state = machine.state()
  findCount: countSlot = machine.offset(state, countAt)
  readCount: count = machine.loadInt64(countSlot)
  anyCheck: any = compare.greaterThanInt64(count, zero=0)
  if any drop done
:drop
  dropFrame: fewer = math.subtractInt64(count, one=1)
  storeCount: machine.storeInt64(countSlot, fewer)
  goto done
:done
  return

op sameFrame "Whether two frames of the call stack name the same operation"
  input table machine.Address copied
  input left Int64 copied
  input right Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
:begin
  findLeftOffset: leftOffset = math.multiplyInt64(left, frameBytes)
  findLeft: leftFrame = machine.offset(table, leftOffset)
  readLeftName: leftName = machine.loadAddress(leftFrame)
  findLeftLength: leftLengthSlot = machine.offset(leftFrame, eight=8)
  readLeftLength: leftLength = machine.loadInt64(leftLengthSlot)
  findRightOffset: rightOffset = math.multiplyInt64(right, frameBytes)
  findRight: rightFrame = machine.offset(table, rightOffset)
  readRightName: rightName = machine.loadAddress(rightFrame)
  findRightLength: rightLengthSlot = machine.offset(rightFrame, eight)
  readRightLength: rightLength = machine.loadInt64(rightLengthSlot)
  compareNames: equal = memory.bytesEqual(leftName, leftLength, rightName, rightLength)
  sameCheck: same = compare.notEqualInt32(equal, zero=0)
  return same

## ---------------------------------------------------------------- recursion depth and the stack floor

op depthSlot "The address of a recursive operation's depth counter, or the address 0 for a number outside the counters"
  input operation Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  lowCheck: aboveLow = compare.greaterOrEqualInt64(operation, zero=0)
  highCheck: belowHigh = compare.lessThanInt64(operation, depthCount)
  bothCheck: inside = logic.and(aboveLow, belowHigh)
  if inside find outside
:find
  findState: state = machine.state()
  findTable: tableSlot = machine.offset(state, depthTableAt)
  readTable: table = machine.loadAddress(tableSlot)
  nowhere: zeroAddress = machine.zero()
  mainCheck: isMain = machine.equal(table, zeroAddress)
  if isMain mainCounters taskCounters
:mainCounters
  findDepths: depths = machine.offset(state, depthsAt)
  findOffset: offset = math.multiplyInt64(operation, eight=8)
  findSlot: slot = machine.offset(depths, offset)
  return slot
:taskCounters
  findTaskOffset: taskOffset = math.multiplyInt64(operation, eight)
  findTaskSlot: taskSlot = machine.offset(table, taskOffset)
  return taskSlot
:outside
  nowhereOutside: outsideAddress = machine.zero()
  return outsideAddress

op enterRecursion "Count one more call of a recursive operation: 0 to go on, 1 when it is deeper than its bound, 2 when its frame lies below the stack floor"
  invariant countsDepth "Each call counts one deeper; past the operation's bound it gives 1, below a stack floor that is set it gives 2, otherwise 0"
  input operation Int64 copied
  input limit Int64 copied
  input here Int64 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_recursion_enter"
  let goOn Int32 0
  let tooDeep Int32 1
  let outOfStack Int32 2
  let noCounter String "a recursive operation has no depth counter"
:begin
  findSlot: slot = depthSlot(operation)
  nowhere: zeroAddress = machine.zero()
  missingCheck: missing = machine.equal(slot, zeroAddress)
  if missing noSlot count
:count
  readDepth: depth = machine.loadInt64(slot)
  deeper: nextDepth = math.addInt64(depth, one=1)
  storeDepth: machine.storeInt64(slot, nextDepth)
  boundCheck: past = compare.greaterThanInt64(nextDepth, limit)
  if past overBound floorCheck
:overBound
  return tooDeep
:floorCheck
  findState: state = machine.state()
  findFloor: floorSlot = machine.offset(state, floorAt)
  readFloor: floor = machine.loadInt64(floorSlot)
  setCheck: floorSet = compare.notEqualInt64(floor, zero=0)
  belowCheck: below = compare.lessThanInt64(here, floor)
  bothCheck: underFloor = logic.and(floorSet, below)
  if underFloor overStack fine
:overStack
  return outOfStack
:fine
  return goOn
:noSlot
  findText: textAt = machine.addressOfString(noCounter)
  textLength: textBytes = string.byteLength(noCounter)
  stop: trap(textAt, textBytes)
  return goOn

op leaveRecursion "Count one call fewer of a recursive operation, as it returns: refined_recursion_leave"
  invariant countsBack "The operation's depth is one less than before the call; a number outside the counters changes nothing"
  input operation Int64 copied
  effect use machine.memory
  uses memoryAccess
  abi c "refined_recursion_leave"
:begin
  findSlot: slot = depthSlot(operation)
  nowhere: zeroAddress = machine.zero()
  missingCheck: missing = machine.equal(slot, zeroAddress)
  if missing done count
:count
  readDepth: depth = machine.loadInt64(slot)
  shallower: nextDepth = math.subtractInt64(depth, one=1)
  storeDepth: machine.storeInt64(slot, nextDepth)
  goto done
:done
  return

## ---------------------------------------------------------------- traps

op lesser "The smaller of two whole numbers"
  input left Int64 copied
  input right Int64 copied
  output Int64
:begin
  orderCheck: leftSmaller = compare.lessThanInt64(left, right)
  if leftSmaller giveLeft giveRight
:giveLeft
  return left
:giveRight
  return right

op writeString "Write text to a handle; gives 0, or the system's error code"
  input handle machine.Address copied
  input text String borrowed
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findText: textAt = machine.addressOfString(text)
  textLength: bytes = string.byteLength(text)
  write: status = output.writeAll(handle, textAt, bytes)
  return status

op writeCount "Write a whole number in decimal to a handle; gives 0, or the system's error code"
  input handle machine.Address copied
  input value Int64 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findState: state = machine.state()
  findDigits: digits = machine.offset(state, digitsAt)
  format: length = numbers.formatDecimal(value, digits)
  write: status = output.writeAll(handle, digits, length)
  return status

op writeFrame "Write one line of the call stack: `  in <operation>`, with `(<count> calls deep)` after a run of the same operation"
  input handle machine.Address copied
  input table machine.Address copied
  input frame Int64 copied
  input calls Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  writeIn: inStatus = writeString(handle, inText="  in ")
  findOffset: offset = math.multiplyInt64(frame, frameBytes)
  findFrame: entry = machine.offset(table, offset)
  readName: name = machine.loadAddress(entry)
  findLength: lengthSlot = machine.offset(entry, eight=8)
  readLength: length = machine.loadInt64(lengthSlot)
  writeName: nameStatus = output.writeAll(handle, name, length)
  runCheck: run = compare.greaterThanInt64(calls, one=1)
  if run writeRun finish
:writeRun
  writeOpen: openStatus = writeString(handle, openText=" (")
  writeCalls: callsStatus = writeCount(handle, calls)
  writeClose: closeStatus = writeString(handle, closeText=" calls deep)")
  goto finish
:finish
  writeEnd: endStatus = writeString(handle, lineEnd="\n")
  return

op report "Write a trap's report to standard error as `refined run` writes it: `trap: <message>`, then the call stack, innermost first, a run of the same operation as one line with its count, at most 12 lines and then how many more"
  invariant writesReport "Writes `trap: ` and the message on a line of its own, then a line per run of the call stack's frames from the top, at most 12, then `  ... and <n> more` when there are more; gives the status of writing the message"
  input text machine.Address copied
  input bytes Int64 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let same Int64 0 mut
  let calls Int64 0 mut
  let runs Int64 0 mut
:begin
  findHandle: handle = output.standardHandle(two=2)
  writeLead: leadStatus = writeString(handle, lead="trap: ")
  writeMessage: messageStatus = output.writeAll(handle, text, bytes)
  writeEnd: endStatus = writeString(handle, lineEnd="\n")
  findState: state = machine.state()
  findCount: countSlot = machine.offset(state, countAt)
  readCount: count = machine.loadInt64(countSlot)
  findCapacity: capacitySlot = machine.offset(state, capacityAt)
  readCapacity: held = machine.loadInt64(capacitySlot)
  findTableSlot: tableSlot = machine.offset(state, framesAt)
  readTable: table = machine.loadAddress(tableSlot)
  shownFrames: frameCount = lesser(count, held)
  topOf: top = math.subtractInt64(frameCount, one=1)
  set at top
  goto eachRun
:eachRun loop=while max=frameCount
  doneCheck: done = compare.lessThanInt64(at, zero=0)
  if done more startRun
:startRun in=eachRun
  set same at
  set calls zero
  goto eachSame
:eachSame loop=while max=frameCount in=eachRun
  sameDone: below = compare.lessThanInt64(same, zero)
  if below counted compareSame
:compareSame in=eachSame
  matchCheck: matches = sameFrame(table, same, at)
  if matches countSame counted
:countSame in=eachSame
  downOne: lower = math.subtractInt64(same, one)
  set same lower
  addCall: moreCalls = math.addInt64(calls, one)
  set calls moreCalls
  goto eachSame
:counted in=eachRun
  shownCheck: shown = compare.lessThanInt64(runs, shownRuns)
  if shown writeRun nextRun
:writeRun in=eachRun
  writeLine: writeFrame(handle, table, at, calls)
  goto nextRun
:nextRun in=eachRun
  addRun: moreRuns = math.addInt64(runs, one)
  set runs moreRuns
  set at same
  goto eachRun
:more
  hiddenCheck: hidden = compare.greaterThanInt64(runs, shownRuns)
  if hidden writeMore finish
:writeMore
  countHidden: hiddenRuns = math.subtractInt64(runs, shownRuns)
  writeAnd: andStatus = writeString(handle, andText="  ... and ")
  writeHidden: hiddenStatus = writeCount(handle, hiddenRuns)
  writeTail: tailStatus = writeString(handle, moreText=" more\n")
  goto finish
:finish
  findInTask: inTaskSlot = machine.offset(state, inTaskAt)
  readInTask: inTask = machine.loadInt64(inTaskSlot)
  taskCheck: isTask = compare.notEqualInt64(inTask, zero)
  if isTask writeTask release
:writeTask
  writeTaskLine: taskStatus = writeString(handle, taskText="  (in a task started with `start`)\n")
  goto release
:release
  releaseAll: released = releaseHeld()
  anyCheck: any = compare.greaterThanInt64(released, zero)
  if any writeReleased reported
:writeReleased
  writeLeadReleased: releasedStatus = writeString(handle, releasedText="the runtime released ")
  writeReleasedCount: countStatus = writeCount(handle, released)
  oneCheck: justOne = compare.equalInt64(released, one)
  if justOne writeSingular writePlural
:writeSingular
  writeOne: oneStatus = writeString(handle, singularText=" resource")
  goto writeRest
:writePlural
  writeMany: manyStatus = writeString(handle, pluralText=" resources")
  goto writeRest
:writeRest
  writeTailReleased: restStatus = writeString(handle, restText=" the program still held (files flushed and closed, connections closed, child processes stopped); deferred cleanups do not run after a trap\n")
  goto reported
:reported
  return messageStatus

## ---------------------------------------------------------------- resources a trap releases (D-51)

op holdResource "Note an open file (kind 1) or a running child process (kind 2) by its operating-system handle, for a trap to release"
  invariant notesResource "The resource is in the table until it is let go; the table grows when full"
  input kind Int64 copied
  input handle machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let capacity Int64 0 mut
:begin
  findState: state = machine.state()
  findCount: countSlot = machine.offset(state, resourceCountAt)
  readCount: count = machine.loadInt64(countSlot)
  findCapacity: capacitySlot = machine.offset(state, resourceCapacityAt)
  readCapacity: held = machine.loadInt64(capacitySlot)
  findTable: tableSlot = machine.offset(state, resourcesAt)
  fullCheck: full = compare.greaterOrEqualInt64(count, held)
  if full grow keep
:grow
  twice: doubled = math.multiplyInt64(held, two=2)
  more: grown = math.addInt64(doubled, sixtyFour=64)
  set capacity grown
  sizeOf: size = math.multiplyInt64(capacity, sixteen=16)
  nowhere: anywhere = machine.zero()
  takeMemory: table = system.virtualAlloc(anywhere, size, commitAndReserve=12288, readWrite=4)
  failedCheck: failed = machine.equal(table, anywhere)
  if failed done move
:move
  readOld: old = machine.loadAddress(tableSlot)
  usedOf: used = math.multiplyInt64(held, sixteen)
  copyOld: machine.copy(table, old, used)
  storeTable: machine.storeAddress(tableSlot, table)
  storeCapacity: machine.storeInt64(capacitySlot, capacity)
  hadCheck: hadTable = compare.greaterThanInt64(held, zero=0)
  if hadTable releaseOld keep
:releaseOld
  freeOld: freed = system.virtualFree(old, zero, releaseMemory=32768)
  goto keep
:keep
  readTableNow: current = machine.loadAddress(tableSlot)
  findOffset: offset = math.multiplyInt64(count, sixteen)
  findEntry: entry = machine.offset(current, offset)
  storeKind: machine.storeInt64(entry, kind)
  findHandle: handleSlot = machine.offset(entry, eight=8)
  storeHandle: machine.storeAddress(handleSlot, handle)
  addOne: nextCount = math.addInt64(count, one=1)
  storeCount: machine.storeInt64(countSlot, nextCount)
  goto done
:done
  return

op letGoResource "Take a resource out of the table, as its file is closed or its child process has ended; one not in it is left alone"
  invariant forgetsResource "The handle is no longer in the table; the last entry takes its place"
  input handle machine.Address copied
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  findState: state = machine.state()
  findCount: countSlot = machine.offset(state, resourceCountAt)
  readCount: count = machine.loadInt64(countSlot)
  findTable: tableSlot = machine.offset(state, resourcesAt)
  readTable: table = machine.loadAddress(tableSlot)
  goto eachResource
:eachResource loop=while max=count
  doneCheck: done = compare.greaterOrEqualInt64(at, count)
  if done finish compareOne
:compareOne in=eachResource
  findOffset: offset = math.multiplyInt64(at, sixteen=16)
  findEntry: entry = machine.offset(table, offset)
  findHandle: handleSlot = machine.offset(entry, eight=8)
  readHandle: held = machine.loadAddress(handleSlot)
  sameCheck: same = machine.equal(held, handle)
  if same remove nextOne
:nextOne in=eachResource
  advance: after = math.addInt64(at, one=1)
  set at after
  goto eachResource
:remove
  lastOf: last = math.subtractInt64(count, one)
  lastOffset: lastAt = math.multiplyInt64(last, sixteen)
  findLast: lastEntry = machine.offset(table, lastAt)
  moveLast: machine.copy(entry, lastEntry, sixteen)
  storeCount: machine.storeInt64(countSlot, last)
  goto finish
:finish
  return

op releaseHeld "Release every resource still held, as a trap does (D-51): close each open file, stop and close each running child process; gives how many there were"
  invariant releasesAll "Every resource in the table is released and the table is empty"
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  findState: state = machine.state()
  findCount: countSlot = machine.offset(state, resourceCountAt)
  readCount: count = machine.loadInt64(countSlot)
  findTable: tableSlot = machine.offset(state, resourcesAt)
  readTable: table = machine.loadAddress(tableSlot)
  goto eachResource
:eachResource loop=while max=count
  doneCheck: done = compare.greaterOrEqualInt64(at, count)
  if done finish releaseOne
:releaseOne in=eachResource
  findOffset: offset = math.multiplyInt64(at, sixteen=16)
  findEntry: entry = machine.offset(table, offset)
  readKind: kind = machine.loadInt64(entry)
  findHandle: handleSlot = machine.offset(entry, eight=8)
  readHandle: handle = machine.loadAddress(handleSlot)
  childCheck: isChild = compare.equalInt64(kind, two=2)
  if isChild stopChild closeIt
:stopChild in=eachResource
  stop: stopped = system.terminateProcess(handle, exitOne=1)
  goto closeIt
:closeIt in=eachResource
  close: closed = system.closeHandle(handle)
  advance: after = math.addInt64(at, one=1)
  set at after
  goto eachResource
:finish
  storeCount: machine.storeInt64(countSlot, zero=0)
  return count

op trap "Report a trap and end the process with exit code 70, as `refined run` does: refined_trap"
  input text machine.Address copied
  input bytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_trap"
:begin
  writeReport: status = report(text, bytes)
  stop: system.exitProcess(trapCode=70)
  return


## ---------------------------------------------------------------- test assertions and instrumentation (not part of an executable's run)

op assertInt "A test's assertion of two whole numbers in an executable: when they differ it traps, as the C runtime does: refined_assert_int"
  input expected Int64 copied
  input actual Int64 copied
  input context machine.Address copied
  input contextBytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_assert_int"
  let message String "an assertion failed (tests run with `refined test`)"
:begin
  sameCheck: same = compare.equalInt64(expected, actual)
  if same done failIt
:failIt
  findText: textAt = machine.addressOfString(message)
  textLength: bytes = string.byteLength(message)
  stop: trap(textAt, bytes)
  goto done
:done
  return

op assertTrue "A test's assertion that a value is true, in an executable: when it is not it traps: refined_assert_true"
  input value Int32 copied
  input context machine.Address copied
  input contextBytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_assert_true"
  let message String "an assertion failed (tests run with `refined test`)"
:begin
  falseCheck: isFalse = compare.equalInt32(value, zero32=0)
  if isFalse failIt done
:failIt
  findText: textAt = machine.addressOfString(message)
  textLength: bytes = string.byteLength(message)
  stop: trap(textAt, bytes)
  goto done
:done
  return

op assertText "A test's assertion that two texts are the same, in an executable: when they differ it traps: refined_assert_str"
  input left machine.Address copied
  input leftBytes Int64 copied
  input right machine.Address copied
  input rightBytes Int64 copied
  input context machine.Address copied
  input contextBytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_assert_str"
  let message String "an assertion failed (tests run with `refined test`)"
:begin
  compareIt: same = memory.bytesEqual(left, leftBytes, right, rightBytes)
  sameCheck: isSame = compare.notEqualInt32(same, zero32=0)
  if isSame done failIt
:failIt
  findText: textAt = machine.addressOfString(message)
  textLength: bytes = string.byteLength(message)
  stop: trap(textAt, bytes)
  goto done
:done
  return

op failTest "A test's `test.fail` in an executable: it traps with its message: refined_fail"
  input text machine.Address copied
  input bytes Int64 copied
  input context machine.Address copied
  input contextBytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_fail"
:begin
  stop: trap(text, bytes)
  return

op block "Entering a block of an instrumented build (--trace, --coverage, --debug): an executable keeps no trace, so nothing happens: refined_block"
  input name machine.Address copied
  input nameBytes Int64 copied
  input values machine.Address copied
  input count Int64 copied
  input description machine.Address copied
  input descriptionBytes Int64 copied
  abi c "refined_block"
:begin
  return

@tests

test pushFrameTest "Pushing a frame puts its name on top of the call stack; popping takes it off"
  verifies pushFrame keepsName
  verifies popFrame dropsTop
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let name String "demo.main (demo.sem:9)"
:begin
  findState: state = machine.state()
  findCount: countSlot = machine.offset(state, countAt)
  readBefore: before = machine.loadInt64(countSlot)
  findName: nameAt = machine.addressOfString(name)
  nameLength: nameBytes = string.byteLength(name)
  push: pushFrame(nameAt, nameBytes)
  readAfter: after = machine.loadInt64(countSlot)
  expectedAfter: wanted = math.addInt64(before, one=1)
  expectPushed: test.assertEqualInt64(wanted, after)
  findTableSlot: tableSlot = machine.offset(state, framesAt)
  readTable: table = machine.loadAddress(tableSlot)
  findOffset: offset = math.multiplyInt64(before, frameBytes)
  findFrame: frame = machine.offset(table, offset)
  readName: kept = machine.loadAddress(frame)
  sameName: sameAddress = machine.equal(kept, nameAt)
  expectName: test.assertTrue(sameAddress)
  pop: popFrame()
  readPopped: popped = machine.loadInt64(countSlot)
  expectPopped: test.assertEqualInt64(before, popped)
  popEmpty: popFrame()
  readEmpty: empty = machine.loadInt64(countSlot)
  expectEmpty: test.assertEqualInt64(zero=0, empty)
  return

test recursionTest "Each call counts one deeper until the bound, a stack floor stops a frame below it, and leaving counts back"
  verifies enterRecursion countsDepth
  verifies leaveRecursion countsBack
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  enterFirst: first = enterRecursion(operation=7, limit=2, here=1000)
  firstWide: firstValue = convert.int32ToInt64(first)
  expectFirst: test.assertEqualInt64(zero=0, firstValue)
  enterSecond: second = enterRecursion(operation, limit, here)
  secondWide: secondValue = convert.int32ToInt64(second)
  expectSecond: test.assertEqualInt64(zero, secondValue)
  enterThird: third = enterRecursion(operation, limit, here)
  thirdWide: thirdValue = convert.int32ToInt64(third)
  expectThird: test.assertEqualInt64(one=1, thirdValue)
  leaveThird: leaveRecursion(operation)
  leaveSecond: leaveRecursion(operation)
  findState: state = machine.state()
  findFloor: floorSlot = machine.offset(state, floorAt)
  setFloor: machine.storeInt64(floorSlot, floor=2000)
  enterBelow: belowFloor = enterRecursion(operation, limit, here)
  belowWide: belowValue = convert.int32ToInt64(belowFloor)
  expectBelow: test.assertEqualInt64(two=2, belowValue)
  clearFloor: machine.storeInt64(floorSlot, zero)
  leaveBelow: leaveRecursion(operation)
  leaveFirst: leaveRecursion(operation)
  findDepths: depths = machine.offset(state, depthsAt)
  findDepth: depthAt = machine.offset(depths, fiftySix=56)
  readDepth: depth = machine.loadInt64(depthAt)
  expectBack: test.assertEqualInt64(zero, depth)
  return

test reportTest "Writing a report succeeds and leaves the call stack as it was"
  verifies report writesReport
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let message String "a test of the trap report (not a trap)"
  let name String "demo.main (demo.sem:9)"
:begin
  findName: nameAt = machine.addressOfString(name)
  nameLength: nameBytes = string.byteLength(name)
  pushOuter: pushFrame(nameAt, nameBytes)
  pushInner: pushFrame(nameAt, nameBytes)
  findMessage: messageAt = machine.addressOfString(message)
  messageLength: messageBytes = string.byteLength(message)
  write: status = report(messageAt, messageBytes)
  statusWide: statusValue = convert.int32ToInt64(status)
  expectWritten: test.assertEqualInt64(zero=0, statusValue)
  findState: state = machine.state()
  findCount: countSlot = machine.offset(state, countAt)
  readCount: count = machine.loadInt64(countSlot)
  expectKept: test.assertEqualInt64(two=2, count)
  popInner: popFrame()
  popOuter: popFrame()
  return

test resourceTest "A held resource stays in the table until it is let go, and a trap's release closes the rest and counts them"
  verifies holdResource notesResource
  verifies letGoResource forgetsResource
  verifies releaseHeld releasesAll
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findState: state = machine.state()
  findEnds: ends = machine.offset(state, sixtyOneK=61440)
  findWriteEnd: writeEnd = machine.offset(ends, eight=8)
  nowhere: anywhere = machine.zero()
  makePipe: made = system.createPipe(ends, writeEnd, anywhere, zero32=0)
  readRead: readHandle = machine.loadAddress(ends)
  readWrite: writeHandle = machine.loadAddress(writeEnd)
  findCount: countSlot = machine.offset(state, resourceCountAt)
  readBefore: before = machine.loadInt64(countSlot)
  holdRead: holdResource(one=1, readHandle)
  holdWrite: holdResource(one, writeHandle)
  readHeld: held = machine.loadInt64(countSlot)
  wantHeld: wanted = math.addInt64(before, two=2)
  expectHeld: test.assertEqualInt64(wanted, held)
  forget: letGoResource(writeHandle)
  closeWrite: closed = system.closeHandle(writeHandle)
  readLeft: left = machine.loadInt64(countSlot)
  wantLeft: wantedLeft = math.addInt64(before, one)
  expectLeft: test.assertEqualInt64(wantedLeft, left)
  release: released = releaseHeld()
  expectReleased: test.assertEqualInt64(wantedLeft, released)
  readAfter: after = machine.loadInt64(countSlot)
  expectEmpty: test.assertEqualInt64(zero=0, after)
  return
