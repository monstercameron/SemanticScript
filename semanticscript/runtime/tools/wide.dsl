module wide "Text for the operating system: UTF-8 to UTF-16 and back, lower case as Python's normcase, text put together piece by piece, and text in order"
  path wide
  imports standard.machine standard.system standard.string standard.math standard.compare standard.convert standard.logic standard.test heap
  exports widen narrow wideUnits lowercase builderNew builderAdd builderAddByte builderText builderLength textOrder

capability memoryAccess "Authority to read and write text in memory" use machine.memory none

capability systemCalls "Authority to convert text with MultiByteToWideChar, WideCharToMultiByte, and LCMapStringEx, and take memory for it" use system.calls none

## The operating system's names (paths, the environment, command lines) are UTF-16; the program's text is UTF-8.
## Both conversions are kernel32's (code page 65001), and lower case is LCMapStringEx with the invariant locale,
## which is what Python's os.path.normcase uses on Windows.
## machine.state bytes 640 to 703 belong to this module: 640 the invariant locale's name, the empty text (always 0).
## A builder (a heap block of 24 bytes): 0 the address of its bytes (a heap block), 8 how many, 16 how many the
## block holds.
constant localeAt "Where the invariant locale's name, the empty UTF-16 text, is, in machine.state" Int64 640

constant utf8 "The UTF-8 code page" Int32 65001

constant lowercaseFlag "LCMAP_LOWERCASE" Int32 256

## ---------------------------------------------------------------- UTF-8 and UTF-16

op widen "UTF-8 text as UTF-16 with a 0 after it, in a new heap block"
  invariant widensText "The block holds the text's characters as UTF-16 units, then a 0 unit"
  input text machine.Address copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let units Int64 0 mut
:begin
  nowhere: anywhere = machine.zero()
  anyCheck: some = compare.greaterThanInt64(bytes, zero=0)
  if some measure make
:measure
  narrowBytes: bytes32 = convert.int64ToInt32(bytes)
  count: counted = system.multiByteToWideChar(utf8, flags=0, text, bytes32, anywhere, none32=0)
  widenCount: countedWide = convert.int32ToInt64(counted)
  set units countedWide
  goto make
:make
  withEnd: unitsAndEnd = math.addInt64(units, one=1)
  sizeOf: size = math.multiplyInt64(unitsAndEnd, two=2)
  takeBlock: block = heap.take(size)
  anyUnits: hasUnits = compare.greaterThanInt64(units, zero)
  if hasUnits convert done
:convert
  narrowAgain: againBytes = convert.int64ToInt32(bytes)
  narrowUnits: units32 = convert.int64ToInt32(units)
  convertIt: written = system.multiByteToWideChar(utf8, flags, text, againBytes, block, units32)
  goto done
:done
  return block

op wideUnits "How many UTF-16 units come before the first 0 unit"
  invariant countsUnits "Gives the number of units before the terminating 0"
  input wide machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let most Int64 1073741824
:begin
  goto eachUnit
:eachUnit loop=while max=most
  offsetOf: offset = math.multiplyInt64(at, two=2)
  findLow: low = machine.offset(wide, offset)
  readLow: lowByte = machine.loadByte(low)
  findHigh: high = machine.offset(low, one=1)
  readHigh: highByte = machine.loadByte(high)
  lowZero: lowIsZero = compare.equalByte(lowByte, zeroByte=0)
  highZero: highIsZero = compare.equalByte(highByte, zeroByte)
  endCheck: atEnd = logic.and(lowIsZero, highIsZero)
  if atEnd done advance
:advance in=eachUnit
  nextUnit: after = math.addInt64(at, one)
  set at after
  goto eachUnit
:done
  return at

op narrow "UTF-16 units as UTF-8 text in a new heap block, with a 0 byte after it; its length (without the 0) is stored at an address"
  invariant narrowsText "The block holds the units' characters as UTF-8 and the length stored is its bytes"
  input wide machine.Address copied
  input units Int64 copied
  input lengthAt machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let bytes Int64 0 mut
:begin
  nowhere: anywhere = machine.zero()
  anyCheck: some = compare.greaterThanInt64(units, zero=0)
  if some measure make
:measure
  narrowUnits: units32 = convert.int64ToInt32(units)
  count: counted = system.wideCharToMultiByte(utf8, flags=0, wide, units32, anywhere, none32=0, anywhere, anywhere)
  widenCount: countedWide = convert.int32ToInt64(counted)
  set bytes countedWide
  goto make
:make
  withEnd: size = math.addInt64(bytes, one=1)
  takeBlock: block = heap.take(size)
  anyBytes: hasBytes = compare.greaterThanInt64(bytes, zero)
  if hasBytes convert done
:convert
  narrowAgain: againUnits = convert.int64ToInt32(units)
  narrowBytes: bytes32 = convert.int64ToInt32(bytes)
  convertIt: written = system.wideCharToMultiByte(utf8, flags, wide, againUnits, block, bytes32, anywhere, anywhere)
  goto done
:done
  storeLength: machine.storeInt64(lengthAt, bytes)
  return block

op lowercase "Text in lower case as Python's normcase gives it on Windows (LCMapStringEx, the invariant locale), every `/` made `\\`, in a new heap block; its length is stored at an address. On Linux normcase changes nothing: a copy"
  invariant lowersText "The block holds the text in lower case with `\\` for `/`"
  input text machine.Address copied
  input bytes Int64 copied
  input lengthAt machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let slash Byte 47
  let backslash Byte 92
:begin
  osCheck: onLinux = system.posix()
  if onLinux copyLinux lowerWindows
:copyLinux
  withNul: room = math.addInt64(bytes, one=1)
  takeCopy: copied = heap.take(room)
  copyText: machine.copy(copied, text, bytes)
  storeCopyLength: machine.storeInt64(lengthAt, bytes)
  return copied
:lowerWindows
  wideText: source = widen(text, bytes)
  countUnits: units = wideUnits(source)
  withEnd: unitsAndEnd = math.addInt64(units, one=1)
  sizeOf: size = math.multiplyInt64(unitsAndEnd, two=2)
  takeTarget: target = heap.take(size)
  anyCheck: some = compare.greaterThanInt64(units, zero=0)
  if some lower narrowIt
:lower
  findState: state = machine.state()
  findLocale: locale = machine.offset(state, localeAt)
  narrowUnits: units32 = convert.int64ToInt32(units)
  nowhere: anywhere = machine.zero()
  mapIt: mapped = system.lcMapStringEx(locale, lowercaseFlag, source, units32, target, units32, anywhere, anywhere, noSort=0)
  goto narrowIt
:narrowIt
  makeText: result = narrow(target, units, lengthAt)
  giveSource: heap.give(source)
  giveTarget: heap.give(target)
  readLength: length = machine.loadInt64(lengthAt)
  goto eachByte
:eachByte loop=while max=length
  doneCheck: done = compare.greaterOrEqualInt64(at, length)
  if done finish checkByte
:checkByte in=eachByte
  findByte: place = machine.offset(result, at)
  readByte: byte = machine.loadByte(place)
  slashCheck: isSlash = compare.equalByte(byte, slash)
  if isSlash swap advance
:swap in=eachByte
  storeBackslash: machine.storeByte(place, backslash)
  goto advance
:advance in=eachByte
  nextByte: after = math.addInt64(at, one)
  set at after
  goto eachByte
:finish
  return result

## ---------------------------------------------------------------- builders

op builderNew "An empty builder, to put text together piece by piece"
  invariant startsEmpty "The builder holds no bytes"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  takeBuilder: builder = heap.take(twentyFour=24)
  return builder

op builderAdd "Add bytes to the end of a builder, doubling its block (from 64 bytes) when they do not fit"
  invariant addsBytes "The builder holds its bytes, then the new ones"
  input builder machine.Address copied
  input data machine.Address copied
  input bytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let capacity Int64 0 mut
:begin
  findLength: lengthSlot = machine.offset(builder, eight=8)
  readLength: length = machine.loadInt64(lengthSlot)
  findCapacity: capacitySlot = machine.offset(builder, sixteen=16)
  readCapacity: held = machine.loadInt64(capacitySlot)
  needOf: needed = math.addInt64(length, bytes)
  fitCheck: fits = compare.lessOrEqualInt64(needed, held)
  if fits append grow
:grow
  doubleIt: doubled = math.multiplyInt64(held, two=2)
  moreRoom: room = math.addInt64(doubled, sixtyFour=64)
  set capacity room
  smallCheck: small = compare.lessThanInt64(room, needed)
  if small useNeeded resize
:useNeeded
  set capacity needed
  goto resize
:resize
  readBlock: block = machine.loadAddress(builder)
  growBlock: grown = heap.resize(block, capacity)
  storeBlock: machine.storeAddress(builder, grown)
  storeCapacity: machine.storeInt64(capacitySlot, capacity)
  goto append
:append
  readBlockNow: blockNow = machine.loadAddress(builder)
  findEnd: endAt = machine.offset(blockNow, length)
  copyIn: machine.copy(endAt, data, bytes)
  storeLength: machine.storeInt64(lengthSlot, needed)
  return

op builderAddByte "Add one byte to the end of a builder"
  invariant addsByte "The builder holds its bytes, then the byte"
  input builder machine.Address copied
  input byte Byte copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findState: state = machine.state()
  findScratch: scratch = machine.offset(state, scratchAt=648)
  storeByte: machine.storeByte(scratch, byte)
  addIt: builderAdd(builder, scratch, one=1)
  return

op builderText "The address of a builder's bytes"
  invariant givesBytes "Gives the address of the bytes added so far"
  input builder machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  readBlock: block = machine.loadAddress(builder)
  return block

op builderLength "How many bytes a builder holds"
  invariant givesLength "Gives how many bytes were added"
  input builder machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findLength: lengthSlot = machine.offset(builder, eight=8)
  readLength: length = machine.loadInt64(lengthSlot)
  return length

## ---------------------------------------------------------------- order

op textOrder "How two texts compare byte by byte, as Python orders `str` (UTF-8 keeps code-point order): -1, 0, or 1"
  invariant ordersText "Gives -1 when the left text sorts first, 1 when the right does, 0 when they are the same"
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
  widenOrder: orderValue = convert.int32ToInt64(order)
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

@tests

test wideTest "Text goes to UTF-16 and back unchanged, lower case is the invariant locale's with `\\` for `/`, a builder puts text together, and texts are ordered by their bytes"
  verifies widen widensText
  verifies wideUnits countsUnits
  verifies narrow narrowsText
  verifies lowercase lowersText
  verifies builderNew startsEmpty
  verifies builderAdd addsBytes
  verifies builderAddByte addsByte
  verifies builderText givesBytes
  verifies builderLength givesLength
  verifies textOrder ordersText
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let mixed String "C:/Données/ÉTÉ"
  let lowered String "c:\\données\\été"
  let shorter String "abc"
  let longer String "abd"
:begin
  findState: state = machine.state()
  findLength: lengthAt = machine.offset(state, scratchAt=61440)
  findMixed: mixedAt = machine.addressOfString(mixed)
  mixedLength: mixedBytes = string.byteLength(mixed)
  osCheck: onLinux = system.posix()
  if onLinux linuxLower windowsWide
:linuxLower
  copyIt: copied = lowercase(mixedAt, mixedBytes, lengthAt)
  readCopied: copiedBytes = machine.loadInt64(lengthAt)
  expectCopiedLength: test.assertEqualInt64(mixedBytes, copiedBytes)
  compareCopied: sameCopied = machine.compare(copied, mixedAt, mixedBytes)
  sameCopiedWide: sameCopiedValue = convert.int32ToInt64(sameCopied)
  expectCopied: test.assertEqualInt64(zero=0, sameCopiedValue)
  giveCopied: heap.give(copied)
  goto builders
:windowsWide
  wideIt: wideText = widen(mixedAt, mixedBytes)
  countIt: units = wideUnits(wideText)
  expectUnits: test.assertEqualInt64(fourteen=14, units)
  backIt: back = narrow(wideText, units, lengthAt)
  readBack: backBytes = machine.loadInt64(lengthAt)
  expectBackLength: test.assertEqualInt64(mixedBytes, backBytes)
  compareBack: same = machine.compare(back, mixedAt, mixedBytes)
  sameWide: sameValue = convert.int32ToInt64(same)
  expectBack: test.assertEqualInt64(zero, sameValue)
  lowerIt: lower = lowercase(mixedAt, mixedBytes, lengthAt)
  readLower: lowerBytes = machine.loadInt64(lengthAt)
  findLowered: loweredAt = machine.addressOfString(lowered)
  loweredLength: loweredBytes = string.byteLength(lowered)
  expectLowerLength: test.assertEqualInt64(loweredBytes, lowerBytes)
  compareLower: sameLower = machine.compare(lower, loweredAt, loweredBytes)
  sameLowerWide: sameLowerValue = convert.int32ToInt64(sameLower)
  expectLower: test.assertEqualInt64(zero, sameLowerValue)
  giveWide: heap.give(wideText)
  giveBack: heap.give(back)
  giveLower: heap.give(lower)
  goto builders
:builders
  makeBuilder: builder = builderNew()
  readEmpty: emptyLength = builderLength(builder)
  expectEmpty: test.assertEqualInt64(zero, emptyLength)
  findShorter: shorterAt = machine.addressOfString(shorter)
  addShorter: builderAdd(builder, shorterAt, three=3)
  addByte: builderAddByte(builder, byteD=100)
  readBuilt: builtLength = builderLength(builder)
  expectBuilt: test.assertEqualInt64(four=4, builtLength)
  readBuiltText: built = builderText(builder)
  findLonger: longerAt = machine.addressOfString(longer)
  orderBuilt: builtOrder = textOrder(built, three, shorterAt, three)
  expectBuiltOrder: test.assertEqualInt64(zero, builtOrder)
  orderLess: lessOrder = textOrder(shorterAt, three, longerAt, three)
  expectLess: test.assertEqualInt64(minusOne=-1, lessOrder)
  orderPrefix: prefixOrder = textOrder(built, four, shorterAt, three)
  expectPrefix: test.assertEqualInt64(one=1, prefixOrder)
  return
