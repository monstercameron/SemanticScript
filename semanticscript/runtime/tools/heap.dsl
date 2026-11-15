module heap "Memory that grows and is given back piece by piece, from the process heap, and traps whose message is put together from parts"
  path heap
  imports standard.machine standard.system standard.string standard.math standard.compare standard.convert standard.logic standard.test kernel numbers frames
  exports take resize give joinMessage numbersMessage startThreads threaded

capability memoryAccess "Authority to keep the process heap's handle in machine.state and to put a trap's message together" use machine.memory none

capability systemCalls "Authority to take memory from the process heap, give it back, and end the process on a trap" use system.calls none

## machine.state bytes 192 to 255 belong to this module: 192 the process heap's handle (0 until it is first asked
## for), 200 to 231 a number's digits; on Linux, bytes 896 to 991: from 896 the first free block of each of nine
## sizes (16 bytes to 4 KiB), 976 the chunk small blocks are cut from and 984 how many of its bytes are left.
## D-140: Linux has no process heap, so the runtime keeps its own: a block has 32 bytes before it (0 how many bytes
## it holds, 8 how many bytes its mapping has, 0 for a small block, 16 how many bytes are in use); a small block of
## up to 4 KiB with its header is cut from a 64 KiB chunk of an anonymous mmap and goes back to the free list of
## its size; a larger one is a mapping of its own, unmapped when it is given back.
constant heapAt "Where the process heap's handle is kept, in machine.state" Int64 192

constant digitsAt "Where a number's digits are put together for a trap's message, in machine.state" Int64 200

constant zeroMemory "HEAP_ZERO_MEMORY: what HeapAlloc and HeapReAlloc hand out is zeroed" Int32 8

constant freeListsAt "Where the first free block of each size is kept on Linux, in machine.state" Int64 896

constant chunkAt "Where the chunk small blocks are cut from is kept on Linux, in machine.state" Int64 976

constant chunkLeftAt "Where how many bytes of that chunk are left is kept, in machine.state" Int64 984

constant blockHead "The bytes before a block on Linux" Int64 32

constant largestSmall "The largest small block on Linux, its header included" Int64 4096

constant chunkSize "The bytes of a chunk small blocks are cut from on Linux" Int64 65536

constant pageBytes "The bytes of a page" Int64 4096

op endProcess "End the process with an exit code: ExitProcess on Windows, exit_group on Linux (D-138)"
  input code Int32 copied
  effect use system.calls
  uses systemCalls
:begin
  osCheck: onLinux = system.linux()
  if onLinux linuxExit windowsExit
:linuxExit
  widenCode: wideCode = convert.int32ToInt64(code)
  callExit: exitResult = system.exitGroup(wideCode)
  return
:windowsExit
  callExitProcess: system.exitProcess(code)
  return

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
  exit: endProcess(trapCode=70)
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
  osCheck: onLinux = system.linux()
  if onLinux linuxTake windowsTake
:linuxTake
  lockHeap()
  takeLinuxBlock: linuxBlock = takeLinux(size)
  unlockHeap()
  return linuxBlock
:windowsTake
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
  osCheck: onLinux = system.linux()
  if onLinux linuxResize windowsResize
:linuxResize
  lockHeap()
  resizeLinuxBlock: linuxBlock = resizeLinux(block, size)
  unlockHeap()
  return linuxBlock
:windowsResize
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
  osCheck: onLinux = system.linux()
  if onLinux linuxGive windowsGive
:linuxGive
  lockHeap()
  giveLinuxBlock: giveLinux(block)
  unlockHeap()
  goto done
:windowsGive
  findHeap: heapHandle = processHeap()
  freeBlock: freed = system.heapFree(heapHandle, flags=0, block)
  goto done
:done
  return

## ---------------------------------------------------------------- the runtime's own heap on Linux (D-140)

op freeListAt "The address of the free list of a size of small block on Linux, by its number (0 for 16 bytes up to 8 for 4 KiB)"
  input index Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  offsetOf: offset = math.multiplyInt64(index, eight=8)
  fromLists: place = math.addInt64(freeListsAt, offset)
  findPlace: slot = kernel.stateAt(place)
  return slot

op cutSmall "A fresh small block of a size (its header included), cut from the current chunk, or from a new one when too few of its bytes are left; the address 0 when there is no memory"
  input size Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findChunk: chunkSlot = kernel.stateAt(chunkAt)
  findLeft: leftSlot = kernel.stateAt(chunkLeftAt)
  readLeft: left = machine.loadInt64(leftSlot)
  roomCheck: room = compare.greaterOrEqualInt64(left, size)
  if room cut fresh
:fresh
  mapChunk: chunk = kernel.mapMemory(chunkSize)
  nowhere: anywhere = machine.zero()
  failedCheck: refused = machine.equal(chunk, anywhere)
  if refused giveNothing keepChunk
:giveNothing
  return anywhere
:keepChunk
  storeChunk: machine.storeAddress(chunkSlot, chunk)
  storeLeft: machine.storeInt64(leftSlot, chunkSize)
  goto cut
:cut
  readChunk: current = machine.loadAddress(chunkSlot)
  readLeftNow: leftNow = machine.loadInt64(leftSlot)
  usedOf: used = math.subtractInt64(chunkSize, leftNow)
  findBlock: block = machine.offset(current, used)
  fewerLeft: stillLeft = math.subtractInt64(leftNow, size)
  storeStillLeft: machine.storeInt64(leftSlot, stillLeft)
  return block

op takeLinux "A zeroed block of at least one byte on Linux, from the runtime's own heap; no memory left traps"
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let size Int64 16 mut
  let index Int64 0 mut
  let header Int64 0 mut
  let noMapping Int64 0
  let rounds Int64 9
:begin
  needOf: need = math.addInt64(bytes, blockHead)
  smallCheck: small = compare.lessOrEqualInt64(need, largestSmall)
  if small eachSize large
:eachSize loop=while max=rounds
  fitsCheck: fits = compare.greaterOrEqualInt64(size, need)
  if fits found grow
:grow in=eachSize
  doubled: twice = math.multiplyInt64(size, two=2)
  set size twice
  nextIndex: following = math.addInt64(index, one=1)
  set index following
  goto eachSize
:found
  findList: listSlot = freeListAt(index)
  readFirst: first = machine.loadAddress(listSlot)
  nowhere: anywhere = machine.zero()
  emptyCheck: empty = machine.equal(first, anywhere)
  if empty cutOne reuse
:reuse
  readNext: next = machine.loadAddress(first)
  storeNext: machine.storeAddress(listSlot, next)
  machineFirst: firstValue = machine.toInt64(first)
  set header firstValue
  goto describeSmall
:cutOne
  cutIt: cut = cutSmall(size)
  cutFailed: noCut = machine.equal(cut, anywhere)
  if noCut noMemory keepCut
:keepCut
  cutValue: cutAt = machine.toInt64(cut)
  set header cutAt
  goto describeSmall
:describeSmall
  headerOf: head = machine.fromInt64(header)
  capacityOf: capacity = math.subtractInt64(size, blockHead)
  findBlock: block = machine.offset(head, blockHead)
  clear: machine.fill(block, zeroByte=0, capacity)
  storeCapacity: machine.storeInt64(head, capacity)
  findMapping: mappingSlot = machine.offset(head, eight=8)
  storeMapping: machine.storeInt64(mappingSlot, noMapping)
  findUsed: usedSlot = machine.offset(head, sixteen=16)
  storeUsed: machine.storeInt64(usedSlot, bytes)
  return block
:large
  pagesOf: pages = math.addInt64(need, pageLess=4095)
  wholePages: count = math.divideInt64(pages, pageBytes)
  roundedOf: mapped = math.multiplyInt64(count, pageBytes)
  mapIt: mapping = kernel.mapMemory(mapped)
  nothing: noBlock = machine.zero()
  mapFailed: noMapped = machine.equal(mapping, noBlock)
  if noMapped noMemory describeLarge
:describeLarge
  largeCapacity: largeHolds = math.subtractInt64(mapped, blockHead)
  storeLargeCapacity: machine.storeInt64(mapping, largeHolds)
  findLargeMapping: largeMappingSlot = machine.offset(mapping, eight)
  storeLargeMapping: machine.storeInt64(largeMappingSlot, mapped)
  findLargeUsed: largeUsedSlot = machine.offset(mapping, sixteen)
  storeLargeUsed: machine.storeInt64(largeUsedSlot, bytes)
  findLargeBlock: largeBlock = machine.offset(mapping, blockHead)
  return largeBlock
:noMemory
  stopHere: fail(outOfMemory="out of memory in the runtime")
  nowhereAgain: noBlockAgain = machine.zero()
  return noBlockAgain

op giveLinux "Give a block back to the runtime's own heap on Linux: a small one onto the free list of its size, a large one's mapping to the system"
  input block machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let size Int64 16 mut
  let index Int64 0 mut
  let rounds Int64 9
:begin
  headerOf: head = machine.offset(block, minusHead=-32)
  findMapping: mappingSlot = machine.offset(head, eight=8)
  readMapping: mapped = machine.loadInt64(mappingSlot)
  largeCheck: large = compare.greaterThanInt64(mapped, zero=0)
  if large unmap small
:unmap
  unmapIt: kernel.unmapMemory(head, mapped)
  return
:small
  readCapacity: capacity = machine.loadInt64(head)
  sizeOf: whole = math.addInt64(capacity, blockHead)
  goto eachSize
:eachSize loop=while max=rounds
  sameCheck: same = compare.greaterOrEqualInt64(size, whole)
  if same found grow
:grow in=eachSize
  doubled: twice = math.multiplyInt64(size, two=2)
  set size twice
  nextIndex: following = math.addInt64(index, one=1)
  set index following
  goto eachSize
:found
  findList: listSlot = freeListAt(index)
  readFirst: first = machine.loadAddress(listSlot)
  link: machine.storeAddress(head, first)
  storeFirst: machine.storeAddress(listSlot, head)
  return

op resizeLinux "A block of the runtime's own heap on Linux grown or shrunk to a number of bytes, its old bytes kept and any new ones zero"
  input block machine.Address copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  headerOf: head = machine.offset(block, minusHead=-32)
  readCapacity: capacity = machine.loadInt64(head)
  findUsed: usedSlot = machine.offset(head, sixteen=16)
  readUsed: used = machine.loadInt64(usedSlot)
  fitsCheck: fits = compare.lessOrEqualInt64(bytes, capacity)
  if fits inPlace move
:inPlace
  shrinkCheck: shrinks = compare.lessThanInt64(bytes, used)
  if shrinks clearTail keep
:clearTail
  findTail: tail = machine.offset(block, bytes)
  tailOf: tailBytes = math.subtractInt64(used, bytes)
  clearIt: machine.fill(tail, zeroByte=0, tailBytes)
  goto keep
:keep
  storeUsed: machine.storeInt64(usedSlot, bytes)
  return block
:move
  takeNew: fresh = takeLinux(bytes)
  copyOld: machine.copy(fresh, block, used)
  giveOld: giveLinux(block)
  return fresh

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

## ---------------------------------------------------------------- threads (D-166)
##
## The runtime's heap on Linux is one free list for the whole process; once a C program starts a thread
## (threads.h's thrd_create), every take, give, and resize holds a lock: a futex word at machine.state byte 28960
## (0 free, 1 held, 2 held with waiters), switched on by byte 28968.

constant spinBound "The bound of the loop that waits for the heap's lock" Int64 9223372036854775807

constant lockAt "Where the heap's lock word is, in machine.state" Int64 28960

constant threadedAt "Where whether threads were started is kept, in machine.state" Int64 28968

op startThreads "Note that the process has more than one thread, so the heap locks from now on"
  invariant locksFromNow "After it, the heap takes and gives blocks under its lock"
  effect use machine.memory
  uses memoryAccess
:begin
  flag = kernel.stateAt(threadedAt)
  machine.storeInt64(flag, 1)
  return

op threaded "Whether the process has more than one thread (threads.h started one)"
  invariant saysThreaded "Gives whether startThreads was called"
  output Bool
  effect use machine.memory
  uses memoryAccess
:begin
  flag = kernel.stateAt(threadedAt)
  value = machine.loadInt64(flag)
  calc started = value != 0
  return started

op lockHeap "Take the heap's lock, when threads were started (waiting on the futex while another thread holds it)"
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  started = threaded()
  if started acquire done
:acquire
  word = kernel.stateAt(lockAt)
  first = machine.compareExchange32(word, 0, 1)
  when first == 0 done contended
:contended loop=while max=spinBound
  previous = machine.compareExchange32(word, 1, 2)
  when previous == 0 retake wait
:wait in=contended
  nowhere = machine.zero()
  system.futex(word, 128, 2, nowhere, nowhere, 0)
  goto retake
:retake in=contended
  taken = machine.compareExchange32(word, 0, 2)
  when taken == 0 done contended
:done
  return

op unlockHeap "Give the heap's lock back, waking a waiter"
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  started = threaded()
  if started release done
:release
  word = kernel.stateAt(lockAt)
  previous = machine.compareExchange32(word, 1, 0)
  when previous == 1 done wake
:wake
  machine.storeInt32(word, 0)
  nowhere = machine.zero()
  system.futex(word, 129, 1, nowhere, nowhere, 0)
  return
:done
  return

@tests

test takeTest "A block from the heap is zeroed, can be written, grows with its bytes kept, and goes back"
  verifies take takesZeroed
  verifies resize keepsBytes
  verifies give givesBack
  verifies startThreads locksFromNow
  verifies threaded saysThreaded
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  before = threaded()
  test.assertTrue(!before)
  startThreads()
  after = threaded()
  test.assertTrue(after)
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
