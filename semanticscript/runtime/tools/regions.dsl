module regions "Regions: memory taken from the operating system in chunks, handed out by bumping, and returned all at once"
  path regions
  imports standard.machine standard.system standard.string standard.math standard.compare standard.convert standard.bits standard.logic standard.test kernel numbers frames handles
  exports newRegion allocate remaining release formatInteger

capability memoryAccess "Authority to keep regions and their chunks in memory" use machine.memory none

capability systemCalls "Authority to take memory from the operating system and give it back, and to end the process on a trap" use system.calls none

## A chunk is memory from VirtualAlloc: at 0 the next chunk of its region, 8 its size, 16 how many of its bytes are
## used, its own 32 bytes included; what it hands out starts at 32 and is zeroed. A region's header lives in its
## first chunk, after the chunk's own: at 0 its capacity, 8 the bytes asked of it (as `refined run` counts them),
## 16 the chunk being filled, 24 the address and 32 the length of its label, 40 how many chunks it has, 48 and 56
## the host objects it owns (the handles module's).
## A region's chunks of the standard size go back to a list of free chunks, zeroed, when it is released.
## machine.state bytes 128 to 191 belong to this module: 128 the first free chunk, 136 how many are free, 144 to
## 175 a number's digits.
constant chunkBytes "The standard size of a chunk: VirtualAlloc's granularity" Int64 65536

constant chunkHead "The bytes at the start of a chunk that describe it" Int64 32

constant regionHead "The bytes of a region's header, in its first chunk" Int64 64

constant keptChunks "How many free chunks are kept for the next regions" Int64 64

constant freeAt "Where the first free chunk is kept, in machine.state" Int64 128

constant freeCountAt "Where the number of free chunks is kept, in machine.state" Int64 136

constant digitsAt "Where a number's digits are put together, in machine.state" Int64 144

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

## ---------------------------------------------------------------- chunks

op stop "Report a trap and end the process with exit code 70"
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

op takeChunk "A zeroed chunk of a size: a free one when the size is standard and one is free, otherwise fresh from VirtualAlloc; the address 0 when there is no memory"
  input size Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findState: state = machine.state()
  findFree: freeSlot = machine.offset(state, freeAt)
  findFreeCount: freeCountSlot = machine.offset(state, freeCountAt)
  readFreeCount: freeCount = machine.loadInt64(freeCountSlot)
  standardCheck: standard = compare.equalInt64(size, chunkBytes)
  anyCheck: any = compare.greaterThanInt64(freeCount, zero=0)
  reuseCheck: reuse = logic.and(standard, any)
  if reuse reuseFree freshChunk
:reuseFree
  readFree: chunk = machine.loadAddress(freeSlot)
  readNext: next = machine.loadAddress(chunk)
  storeFree: machine.storeAddress(freeSlot, next)
  fewer: fewerFree = math.subtractInt64(freeCount, one=1)
  storeFreeCount: machine.storeInt64(freeCountSlot, fewerFree)
  return chunk
:freshChunk
  nowhere: anywhere = machine.zero()
  take: fresh = kernel.mapMemory(size)
  return fresh

op dropChunk "Give a chunk back: zeroed onto the free list when it is of the standard size and the list has room, otherwise to the operating system"
  input chunk machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findSize: sizeSlot = machine.offset(chunk, eight=8)
  readSize: size = machine.loadInt64(sizeSlot)
  findUsed: usedSlot = machine.offset(chunk, sixteen=16)
  readUsed: used = machine.loadInt64(usedSlot)
  findState: state = machine.state()
  findFree: freeSlot = machine.offset(state, freeAt)
  findFreeCount: freeCountSlot = machine.offset(state, freeCountAt)
  readFreeCount: freeCount = machine.loadInt64(freeCountSlot)
  standardCheck: standard = compare.equalInt64(size, chunkBytes)
  roomCheck: room = compare.lessThanInt64(freeCount, keptChunks)
  keepCheck: keep = logic.and(standard, room)
  if keep keepChunk giveBack
:keepChunk
  clear: machine.fill(chunk, zeroByte=0, used)
  readFree: first = machine.loadAddress(freeSlot)
  link: machine.storeAddress(chunk, first)
  storeFree: machine.storeAddress(freeSlot, chunk)
  more: moreFree = math.addInt64(freeCount, one=1)
  storeFreeCount: machine.storeInt64(freeCountSlot, moreFree)
  return
:giveBack
  giveToSystem: kernel.unmapMemory(chunk, size)
  return

## ---------------------------------------------------------------- regions

op newRegion "Make a region that may hand out a capacity of bytes, named by a label for its traps: refined_region_new"
  invariant startsEmpty "A new region has its whole capacity remaining"
  input capacity Int64 copied
  input label machine.Address copied
  input labelBytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_region_new"
:begin
  take: chunk = takeChunk(chunkBytes)
  nowhere: anywhere = machine.zero()
  failedCheck: failed = machine.equal(chunk, anywhere)
  if failed noMemory describe
:describe
  storeNext: machine.storeAddress(chunk, anywhere)
  findSize: sizeSlot = machine.offset(chunk, eight=8)
  storeSize: machine.storeInt64(sizeSlot, chunkBytes)
  findUsed: usedSlot = machine.offset(chunk, sixteen=16)
  headBytes: used = math.addInt64(chunkHead, regionHead)
  storeUsed: machine.storeInt64(usedSlot, used)
  findRegion: region = machine.offset(chunk, chunkHead)
  storeCapacity: machine.storeInt64(region, capacity)
  findAsked: askedSlot = machine.offset(region, eight)
  storeAsked: machine.storeInt64(askedSlot, zero=0)
  findChunks: chunksSlot = machine.offset(region, sixteen)
  storeChunks: machine.storeAddress(chunksSlot, chunk)
  findLabel: labelSlot = machine.offset(region, twentyFour=24)
  storeLabel: machine.storeAddress(labelSlot, label)
  findLabelBytes: labelBytesSlot = machine.offset(region, thirtyTwo=32)
  storeLabelBytes: machine.storeInt64(labelBytesSlot, labelBytes)
  findChunkCount: chunkCountSlot = machine.offset(region, forty=40)
  storeChunkCount: machine.storeInt64(chunkCountSlot, one=1)
  return region
:noMemory
  stopHere: stop(outOfMemory="out of memory creating a region")
  return anywhere

op exceeded "Trap because a region was asked for more than its capacity: `<label> exceeded its capacity of <capacity> bytes`"
  input region machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let middle String " exceeded its capacity of "
  let tail String " bytes"
:begin
  readCapacity: capacity = machine.loadInt64(region)
  findLabel: labelSlot = machine.offset(region, twentyFour=24)
  readLabel: label = machine.loadAddress(labelSlot)
  findLabelBytes: labelBytesSlot = machine.offset(region, thirtyTwo=32)
  readLabelBytes: labelBytes = machine.loadInt64(labelBytesSlot)
  roomOf: room = math.addInt64(labelBytes, sixtyFour=64)
  nowhere: anywhere = machine.zero()
  take: message = kernel.mapMemory(room)
  failedCheck: failed = machine.equal(message, anywhere)
  if failed labelOnly compose
:compose
  copyLabel: machine.copy(message, label, labelBytes)
  findMiddle: middleAt = machine.offset(message, labelBytes)
  readMiddle: middleText = machine.addressOfString(middle)
  middleLength: middleBytes = string.byteLength(middle)
  copyMiddle: machine.copy(middleAt, middleText, middleBytes)
  afterMiddle: digitsOffset = math.addInt64(labelBytes, middleBytes)
  findDigits: digits = machine.offset(message, digitsOffset)
  format: digitCount = numbers.formatDecimal(capacity, digits)
  afterDigits: tailOffset = math.addInt64(digitsOffset, digitCount)
  findTail: tailAt = machine.offset(message, tailOffset)
  readTail: tailText = machine.addressOfString(tail)
  tailLength: tailBytes = string.byteLength(tail)
  copyTail: machine.copy(tailAt, tailText, tailBytes)
  total: messageBytes = math.addInt64(tailOffset, tailBytes)
  writeReport: status = frames.report(message, messageBytes)
  exit: endProcess(trapCode=70)
  return
:labelOnly
  writeLabel: labelStatus = frames.report(label, labelBytes)
  exitLabel: endProcess(trapCode)
  return

op allocate "Hand out a zeroed block of bytes from a region, sixteen-byte aligned; a request past the region's capacity traps: refined_region_alloc"
  invariant handsOutZeroed "Each block is zeroed, aligned to 16 bytes, apart from every other block of the region, and counted against its capacity as asked"
  input region machine.Address copied
  input size Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_region_alloc"
  let need Int64 0 mut
  let freshSize Int64 0 mut
  let eight Int64 8
  let sixteen Int64 16
:begin
  readCapacity: capacity = machine.loadInt64(region)
  findAsked: askedSlot = machine.offset(region, eight)
  readAsked: asked = machine.loadInt64(askedSlot)
  roomOf: room = math.subtractInt64(capacity, asked)
  negativeCheck: negative = compare.lessThanInt64(size, zero=0)
  overCheck: over = compare.greaterThanInt64(size, room)
  badCheck: bad = logic.or(negative, over)
  if bad tooMuch count
:count
  addAsked: nowAsked = math.addInt64(asked, size)
  storeAsked: machine.storeInt64(askedSlot, nowAsked)
  emptyCheck: empty = compare.lessThanInt64(size, one=1)
  if empty needOne needSize
:needOne
  set need sixteen
  goto place
:needSize
  roundUp: padded = math.addInt64(size, fifteen=15)
  align: aligned = bits.andInt64(padded, minusSixteen=-16)
  set need aligned
  goto place
:place
  findChunks: chunksSlot = machine.offset(region, sixteen)
  readChunk: chunk = machine.loadAddress(chunksSlot)
  findChunkSize: chunkSizeSlot = machine.offset(chunk, eight)
  readChunkSize: chunkSize = machine.loadInt64(chunkSizeSlot)
  findUsed: usedSlot = machine.offset(chunk, sixteen)
  readUsed: used = machine.loadInt64(usedSlot)
  leftOf: left = math.subtractInt64(chunkSize, used)
  fitCheck: fits = compare.lessOrEqualInt64(need, left)
  if fits handOut grow
:handOut
  findBlock: block = machine.offset(chunk, used)
  addUsed: nowUsed = math.addInt64(used, need)
  storeUsed: machine.storeInt64(usedSlot, nowUsed)
  return block
:grow
  wantOf: want = math.addInt64(need, chunkHead)
  standardCheck: standard = compare.lessOrEqualInt64(want, chunkBytes)
  if standard standardChunk largeChunk
:standardChunk
  set freshSize chunkBytes
  goto newChunk
:largeChunk
  roundChunk: paddedChunk = math.addInt64(want, granule=65535)
  alignChunk: alignedChunk = bits.andInt64(paddedChunk, chunkMask=-65536)
  set freshSize alignedChunk
  goto newChunk
:newChunk
  take: fresh = takeChunk(freshSize)
  nowhere: anywhere = machine.zero()
  failedCheck: failed = machine.equal(fresh, anywhere)
  if failed noMemory link
:link
  storeNext: machine.storeAddress(fresh, chunk)
  findFreshSize: freshSizeSlot = machine.offset(fresh, eight)
  storeFreshSize: machine.storeInt64(freshSizeSlot, freshSize)
  findFreshUsed: freshUsedSlot = machine.offset(fresh, sixteen)
  freshUsedOf: freshUsed = math.addInt64(chunkHead, need)
  storeFreshUsed: machine.storeInt64(freshUsedSlot, freshUsed)
  storeChunk: machine.storeAddress(chunksSlot, fresh)
  findChunkCount: chunkCountSlot = machine.offset(region, forty=40)
  readChunkCount: chunkCount = machine.loadInt64(chunkCountSlot)
  moreChunks: nextChunkCount = math.addInt64(chunkCount, one)
  storeChunkCount: machine.storeInt64(chunkCountSlot, nextChunkCount)
  findFreshBlock: freshBlock = machine.offset(fresh, chunkHead)
  return freshBlock
:noMemory
  stopHere: stop(outOfMemory="out of memory in a region")
  return anywhere
:tooMuch
  trapHere: exceeded(region)
  nothing: nowhere2 = machine.zero()
  return nowhere2

op remaining "How many of a region's bytes are still free to ask for: refined_region_remaining"
  invariant countsAsked "A region's remaining bytes are its capacity less every size it was asked for"
  input region machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi c "refined_region_remaining"
:begin
  readCapacity: capacity = machine.loadInt64(region)
  findAsked: askedSlot = machine.offset(region, eight=8)
  readAsked: asked = machine.loadInt64(askedSlot)
  leftOf: left = math.subtractInt64(capacity, asked)
  return left

op release "Give back every chunk of a region at once: refined_region_free"
  invariant reusesChunks "Every host object the region owns is closed and every chunk of the region is given back; a chunk of the standard size is kept, zeroed, for the next region while 64 are not yet kept"
  input region machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_region_free"
  let chunk machine.Address unset mut
:begin
  dropHandles: handles.dropRegion(region)
  findChunks: chunksSlot = machine.offset(region, sixteen=16)
  readChunk: first = machine.loadAddress(chunksSlot)
  set chunk first
  findChunkCount: chunkCountSlot = machine.offset(region, forty=40)
  readChunkCount: chunkCount = machine.loadInt64(chunkCountSlot)
  nowhere: anywhere = machine.zero()
  goto eachChunk
:eachChunk loop=while max=chunkCount
  endCheck: atEnd = machine.equal(chunk, anywhere)
  if atEnd done dropOne
:dropOne in=eachChunk
  readNext: next = machine.loadAddress(chunk)
  drop: dropChunk(chunk)
  set chunk next
  goto eachChunk
:done
  return

## ---------------------------------------------------------------- text

op formatInteger "A whole number as decimal text in a region; its length is written at an address: refined_format_int"
  invariant formatsIntoRegion "The text is the number as `refined run` prints it, in a block of the region, and its length is stored at the address given"
  input value Int64 copied
  input region machine.Address copied
  input lengthAt machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_format_int"
:begin
  findState: state = machine.state()
  findDigits: digits = machine.offset(state, digitsAt)
  format: length = numbers.formatDecimal(value, digits)
  take: block = allocate(region, length)
  copyDigits: machine.copy(block, digits, length)
  storeLength: machine.storeInt64(lengthAt, length)
  return block

@tests

test regionTest "A region hands out zeroed, aligned, separate blocks, counts what it was asked for, and gives its chunks back"
  verifies newRegion startsEmpty
  verifies allocate handsOutZeroed
  verifies remaining countsAsked
  verifies release reusesChunks
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let label String "region `scratch` of `regionTest`"
:begin
  findLabel: labelAt = machine.addressOfString(label)
  labelLength: labelBytes = string.byteLength(label)
  make: region = newRegion(capacity=100000, labelAt, labelBytes)
  readFresh: fresh = remaining(region)
  expectFresh: test.assertEqualInt64(capacity, fresh)
  takeFirst: first = allocate(region, three=3)
  takeSecond: second = allocate(region, five=5)
  readLeft: left = remaining(region)
  expectLeft: test.assertEqualInt64(left99992=99992, left)
  apart: gap = machine.difference(second, first)
  expectApart: test.assertEqualInt64(sixteen=16, gap)
  firstValue: firstAt = machine.toInt64(first)
  alignOf: misaligned = math.remainderInt64(firstAt, sixteen)
  expectAligned: test.assertEqualInt64(zero=0, misaligned)
  readZero: firstByte = machine.loadByte(second)
  zeroWide: firstByteValue = convert.byteToInt64(firstByte)
  expectZeroed: test.assertEqualInt64(zero, firstByteValue)
  writeSome: machine.storeByte(second, sevenByte=7)
  takeLarge: large = allocate(region, ninetyThousand=90000)
  readLarge: largeByte = machine.loadByte(large)
  largeWide: largeValue = convert.byteToInt64(largeByte)
  expectLargeZeroed: test.assertEqualInt64(zero, largeValue)
  findChunkCount: chunkCountSlot = machine.offset(region, forty=40)
  readChunkCount: chunkCount = machine.loadInt64(chunkCountSlot)
  expectTwoChunks: test.assertEqualInt64(two=2, chunkCount)
  free: release(region)
  findState: state = machine.state()
  findFreeCount: freeCountSlot = machine.offset(state, freeCountAt)
  readFreeCount: freeCount = machine.loadInt64(freeCountSlot)
  expectKept: test.assertEqualInt64(one=1, freeCount)
  makeAgain: again = newRegion(capacity, labelAt, labelBytes)
  takeAgain: block = allocate(again, five)
  readAgain: againByte = machine.loadByte(block)
  againWide: againValue = convert.byteToInt64(againByte)
  expectReused: test.assertEqualInt64(zero, againValue)
  readReusedCount: reusedCount = machine.loadInt64(freeCountSlot)
  expectTaken: test.assertEqualInt64(zero, reusedCount)
  freeAgain: release(again)
  return

test formatIntegerTest "A number's text is put in the region and its length beside it"
  verifies formatInteger formatsIntoRegion
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let label String "region `numbers` of `formatIntegerTest`"
  let expected String "-4096"
:begin
  findLabel: labelAt = machine.addressOfString(label)
  labelLength: labelBytes = string.byteLength(label)
  make: region = newRegion(capacity=64, labelAt, labelBytes)
  findState: state = machine.state()
  findLength: lengthAt = machine.offset(state, scratchAt=61440)
  format: text = formatInteger(minus4096=-4096, region, lengthAt)
  readLength: length = machine.loadInt64(lengthAt)
  viewText: shown = machine.stringAt(text, length)
  expectText: test.assertEqualString(expected, shown)
  readLeft: left = remaining(region)
  expectLeft: test.assertEqualInt64(fiftyNine=59, left)
  free: release(region)
  return
