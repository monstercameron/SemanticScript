module heap "Memory that grows and is given back piece by piece, from the process heap, and traps whose message is put together from parts"
  path heap
  imports standard.machine standard.system standard.string standard.math standard.compare standard.convert standard.logic standard.test numbers frames
  exports take resize give joinMessage numbersMessage

capability memoryAccess "Authority to keep the process heap's handle in machine.state and to put a trap's message together" use machine.memory none

capability systemCalls "Authority to take memory from the process heap, give it back, and end the process on a trap" use system.calls none

## machine.state bytes 192 to 255 belong to this module: 192 the process heap's handle (0 until it is first asked
## for), 200 to 231 a number's digits.
constant heapAt "Where the process heap's handle is kept, in machine.state" Int64 192

constant digitsAt "Where a number's digits are put together for a trap's message, in machine.state" Int64 200

constant zeroMemory "HEAP_ZERO_MEMORY: what HeapAlloc and HeapReAlloc hand out is zeroed" Int32 8

## ---------------------------------------------------------------- traps

op fail "Report a trap with a message and end the process with exit code 70"
  input text String borrowed
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findText: textAt = machine.addressOfString(text)
  textLength: bytes = string.byteLength(text)
  writeReport: status = frames.report(textAt, bytes)
  exit: system.exitProcess(trapCode=70)
  return

op processHeap "The process heap's handle, asked of the operating system once and kept"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findState: state = machine.state()
  findSlot: slot = machine.offset(state, heapAt)
  readKept: kept = machine.loadAddress(slot)
  nowhere: anywhere = machine.zero()
  missingCheck: missing = machine.equal(kept, anywhere)
  if missing ask known
:ask
  askSystem: fresh = system.getProcessHeap()
  keep: machine.storeAddress(slot, fresh)
  return fresh
:known
  return kept

op take "A zeroed block of memory of a number of bytes (at least one) from the process heap; no memory left traps"
  invariant takesZeroed "Gives a block of at least the bytes asked, every byte zero; a block is never the address 0"
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let size Int64 1 mut
:begin
  bigCheck: big = compare.greaterThanInt64(bytes, one=1)
  if big useBytes allocate
:useBytes
  set size bytes
  goto allocate
:allocate
  findHeap: heapHandle = processHeap()
  takeBlock: block = system.heapAlloc(heapHandle, zeroMemory, size)
  nowhere: anywhere = machine.zero()
  failedCheck: failed = machine.equal(block, anywhere)
  if failed noMemory done
:done
  return block
:noMemory
  stopHere: fail(outOfMemory="out of memory in the runtime")
  return anywhere

op resize "A block of memory grown or shrunk to a number of bytes, its old bytes kept and any new ones zeroed; the address 0 gives a new block"
  invariant keepsBytes "The block keeps its first bytes, up to the smaller of the two sizes; bytes past the old size are zero"
  input block machine.Address copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let size Int64 1 mut
:begin
  nowhere: anywhere = machine.zero()
  freshCheck: fresh = machine.equal(block, anywhere)
  if fresh takeFresh sizeCheck
:takeFresh
  takeBlock: made = take(bytes)
  return made
:sizeCheck
  bigCheck: big = compare.greaterThanInt64(bytes, one=1)
  if big useBytes reallocate
:useBytes
  set size bytes
  goto reallocate
:reallocate
  findHeap: heapHandle = processHeap()
  growBlock: grown = system.heapReAlloc(heapHandle, zeroMemory, block, size)
  failedCheck: failed = machine.equal(grown, anywhere)
  if failed noMemory done
:done
  return grown
:noMemory
  stopHere: fail(outOfMemory="out of memory in the runtime")
  return anywhere

op give "Give a block of memory back to the process heap; the address 0 is nothing to give"
  invariant givesBack "A block taken with `take` or `resize` goes back to the heap; the address 0 is ignored"
  input block machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere: anywhere = machine.zero()
  emptyCheck: empty = machine.equal(block, anywhere)
  if empty done free
:free
  findHeap: heapHandle = processHeap()
  freeBlock: freed = system.heapFree(heapHandle, flags=0, block)
  goto done
:done
  return

op joinMessage "A trap's message put together in a new block from a text, a range of bytes, and another text, one after the other; its length is the three lengths added"
  invariant joinsParts "The block holds the first text, the bytes, and the last text, one after the other"
  input first String borrowed
  input middle machine.Address copied
  input middleBytes Int64 copied
  input last String borrowed
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findFirst: firstAt = machine.addressOfString(first)
  firstLength: firstBytes = string.byteLength(first)
  findLast: lastAt = machine.addressOfString(last)
  lastLength: lastBytes = string.byteLength(last)
  sumFirst: headBytes = math.addInt64(firstBytes, middleBytes)
  sumAll: totalBytes = math.addInt64(headBytes, lastBytes)
  takeMessage: message = take(totalBytes)
  copyFirst: machine.copy(message, firstAt, firstBytes)
  findMiddle: middleTarget = machine.offset(message, firstBytes)
  copyMiddle: machine.copy(middleTarget, middle, middleBytes)
  findTail: lastTarget = machine.offset(message, headBytes)
  copyLast: machine.copy(lastTarget, lastAt, lastBytes)
  return message

op numbersMessage "A trap's message put together in a new block: a text, a number, a text, and a number, `<first><number><middle><other>`; its length is stored at an address"
  invariant writesNumbers "The block holds the first text, the first number in decimal, the middle text, and the second number in decimal, and the length is theirs"
  input first String borrowed
  input number Int64 copied
  input middle String borrowed
  input other Int64 copied
  input lengthAt machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findFirst: firstAt = machine.addressOfString(first)
  firstLength: firstBytes = string.byteLength(first)
  findMiddle: middleAt = machine.addressOfString(middle)
  middleLength: middleBytes = string.byteLength(middle)
  sumText: textBytes = math.addInt64(firstBytes, middleBytes)
  roomOf: room = math.addInt64(textBytes, fortyTwo=42)
  takeMessage: message = take(room)
  copyFirst: machine.copy(message, firstAt, firstBytes)
  findNumber: numberAt = machine.offset(message, firstBytes)
  writeNumber: numberBytes = numbers.formatDecimal(number, numberAt)
  afterNumber: middleOffset = math.addInt64(firstBytes, numberBytes)
  findMiddleTarget: middleTarget = machine.offset(message, middleOffset)
  copyMiddle: machine.copy(middleTarget, middleAt, middleBytes)
  afterMiddle: otherOffset = math.addInt64(middleOffset, middleBytes)
  findOther: otherAt = machine.offset(message, otherOffset)
  writeOther: otherBytes = numbers.formatDecimal(other, otherAt)
  total: totalBytes = math.addInt64(otherOffset, otherBytes)
  storeLength: machine.storeInt64(lengthAt, totalBytes)
  return message

@tests

test takeTest "A block from the heap is zeroed, can be written, grows with its bytes kept, and goes back"
  verifies take takesZeroed
  verifies resize keepsBytes
  verifies give givesBack
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  takeBlock: block = take(sixtyFour=64)
  findLast: lastAt = machine.offset(block, sixtyThree=63)
  readLast: lastByte = machine.loadByte(lastAt)
  widenLast: lastValue = convert.byteToInt64(lastByte)
  expectZeroed: test.assertEqualInt64(zero=0, lastValue)
  writeFirst: machine.storeInt64(block, answer=42)
  growBlock: grown = resize(block, fourThousand=4096)
  readFirst: firstValue = machine.loadInt64(grown)
  expectKept: test.assertEqualInt64(answer, firstValue)
  findFar: farAt = machine.offset(grown, farOffset=4088)
  readFar: farValue = machine.loadInt64(farAt)
  expectFarZeroed: test.assertEqualInt64(zero, farValue)
  nowhere: anywhere = machine.zero()
  takeFresh: fresh = resize(anywhere, eight=8)
  readFresh: freshValue = machine.loadInt64(fresh)
  expectFresh: test.assertEqualInt64(zero, freshValue)
  giveGrown: give(grown)
  giveFresh: give(fresh)
  giveNothing: give(anywhere)
  return

test emptyTakeTest "Asking for no bytes still gives a block of its own"
  verifies take takesZeroed
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  takeNone: block = take(zero=0)
  nowhere: anywhere = machine.zero()
  zeroCheck: isZero = machine.equal(block, anywhere)
  notZero: isBlock = logic.not(isZero)
  expectBlock: test.assertTrue(isBlock)
  giveBlock: give(block)
  return

test messageTest "A trap's message is put together from its parts"
  verifies joinMessage joinsParts
  verifies numbersMessage writesNumbers
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let name String "Map"
  let joined String "a Map handle was used"
  let counted String "a set was read at position -3 of 12"
:begin
  findName: nameAt = machine.addressOfString(name)
  join: message = joinMessage(lead="a ", nameAt, three=3, tail=" handle was used")
  viewJoined: shown = machine.stringAt(message, twentyOne=21)
  expectJoined: test.assertEqualString(joined, shown)
  giveJoined: give(message)
  findState: state = machine.state()
  findLength: lengthAt = machine.offset(state, scratchAt=61440)
  count: numbered = numbersMessage(numberLead="a set was read at position ", minusThree=-3, of=" of ", twelve=12, lengthAt)
  readLength: length = machine.loadInt64(lengthAt)
  viewCounted: countedShown = machine.stringAt(numbered, length)
  expectCounted: test.assertEqualString(counted, countedShown)
  giveCounted: give(numbered)
  return
