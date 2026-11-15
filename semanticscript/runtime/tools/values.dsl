module values "JSON values as the json targets keep them: nodes shared by the handles and containers that hold them, counted, and given back when the last one lets go"
  path values
  imports standard.machine standard.math standard.compare standard.convert standard.bits standard.logic standard.string standard.test kernel heap tables
  exports newValue retain release appendItem putField findField decodeAt

capability memoryAccess "Authority to keep JSON values in memory" use machine.memory none

capability systemCalls "Authority to take memory for JSON values from the process heap and give it back" use system.calls none

## As under `refined run`, where a json.Value is a Python object: an array or object is shared, so a value read
## from it with `field` or `item`, or stored in another with `setValue`, is the same value, and a change to it is
## seen through every handle and container that holds it. A value is a heap block of nodeBytes, counted: every
## handle and every container that holds it is one reference, and the last to let go gives it back with what it
## holds (handles.drop, as a handle is closed or its region released). At 0 how many hold it, 8 its kind (1 null, 2
## a boolean, 3 a whole number that fits an Int64, 4 a larger whole number kept as its decimal text, 5 a Float64,
## 6 text, 7 an array, 8 an object), 16 its value (0 or 1, the number, the float's bits, or the address of a heap
## block of its bytes or of its items), 24 its bytes or how many items, 32 how many items the block holds, from 40
## an object's table (tables): text keys (a heap copy of the bytes) in the order first put, each with its value;
## at 128 whether `json.stringify` is writing the value (to find a value that holds itself).
## Text is kept as Python's str is, in UTF-8 that may hold surrogates (the bytes that were not UTF-8 are U+DC80 to
## U+DCFF, as surrogateescape reads them), so equal keys are equal strings.
## machine.state bytes 1056 to 1071 belong to this module: a key's two slots while it is looked up.
constant nodeBytes "The bytes of a JSON value" Int64 136

constant keySlotsAt "Where a key's two slots are put while it is looked up, in machine.state" Int64 1056

constant kindNull "A null value's kind" Int64 1

constant kindBig "The kind of a whole number too large for an Int64, kept as its decimal text" Int64 4

constant kindText "A text value's kind" Int64 6

constant kindArray "An array's kind" Int64 7

constant kindObject "An object's kind" Int64 8

op word "A whole number of a value at an offset"
  input node machine.Address copied
  input offset Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findPart: at = machine.offset(node, offset)
  readField: value = machine.loadInt64(at)
  return value

op setWord "Store a whole number of a value at an offset"
  input node machine.Address copied
  input offset Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  findPart: at = machine.offset(node, offset)
  storePart: machine.storeInt64(at, value)
  return

op newValue "A new value of a kind, held once: an object starts with an empty table of text keys"
  invariant startsHeld "A new value is held once and has its kind, no bytes, and no items"
  input kind Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  takeNode: node = heap.take(nodeBytes)
  storeRefs: setWord(node, zero=0, one=1)
  storeKind: setWord(node, eight=8, kind)
  objectCheck: isObject = compare.equalInt64(kind, kindObject)
  if isObject prepareTable done
:prepareTable
  findTable: table = machine.offset(node, forty=40)
  prepareIt: tables.prepare(table, one, two=2, one)
  return node
:done
  return node

op retain "Hold a value once more"
  invariant countsHolder "The value is held one more time"
  input node machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  readRefs: refs = word(node, zero=0)
  moreRefs: more = math.addInt64(refs, one=1)
  storeRefs: setWord(node, zero, more)
  return

op push "Push a value on a list of values to let go of: a heap block, at 0 how many, 8 how many it holds, then the values; gives the list, grown when full"
  input list machine.Address copied
  input node machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let grown machine.Address unset mut
:begin
  set grown list
  readCount: count = word(list, zero=0)
  readCapacity: capacity = word(list, eight=8)
  fullCheck: full = compare.greaterOrEqualInt64(count, capacity)
  if full grow store
:grow
  twice: doubled = math.multiplyInt64(capacity, two=2)
  slotsOf: slots = math.addInt64(doubled, two)
  bytesOf: bytes = math.multiplyInt64(slots, eight)
  resizeIt: resized = heap.resize(list, bytes)
  set grown resized
  storeCapacity: setWord(resized, eight, doubled)
  goto store
:store
  slotOf: slot = math.addInt64(count, two)
  offsetOf: offset = math.multiplyInt64(slot, eight)
  findSlot: at = machine.offset(grown, offset)
  storeNode: machine.storeAddress(at, node)
  moreCount: after = math.addInt64(count, one=1)
  storeCount: setWord(grown, zero, after)
  return grown

op release "Let go of a value once; when nothing holds it any more give it back, with its bytes, and let go of each value it holds, in turn; gives how many values were given back"
  invariant givesBackLast "A value held n times is given back by the n-th release, with every value only it held; the others stay"
  input node machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let list machine.Address unset mut
  let freed Int64 0 mut
  let at Int64 0 mut
  let forever Int64 9223372036854775807
:begin
  takeList: first = heap.take(listBytes=144)
  storeCapacity: setWord(first, eight=8, sixteen=16)
  set list first
  pushFirst: started = push(first, node)
  set list started
  goto eachValue
:eachValue loop=while max=forever
  readCount: count = word(list, zero=0)
  emptyCheck: empty = compare.equalInt64(count, zero)
  if empty finish popOne
:popOne in=eachValue
  lessCount: last = math.subtractInt64(count, one=1)
  storeCount: setWord(list, zero, last)
  slotOf: slot = math.addInt64(last, two=2)
  offsetOf: offset = math.multiplyInt64(slot, eight)
  findSlot: slotAt = machine.offset(list, offset)
  readNode: current = machine.loadAddress(slotAt)
  readRefs: refs = word(current, zero)
  lessRefs: fewer = math.subtractInt64(refs, one)
  storeRefs: setWord(current, zero, fewer)
  heldCheck: held = compare.greaterThanInt64(fewer, zero)
  if held eachValue giveBack
:giveBack in=eachValue
  moreFreed: freedAfter = math.addInt64(freed, one)
  set freed freedAfter
  readKind: kind = word(current, eight)
  bigCheck: isBig = compare.equalInt64(kind, kindBig)
  textCheck: isText = compare.equalInt64(kind, kindText)
  bytesCheck: hasBytes = logic.or(isBig, isText)
  if hasBytes giveBytes arrayCheck
:giveBytes in=eachValue
  readBytes: bytesAt = word(current, sixteen=16)
  bytesAddress: bytesBlock = machine.fromInt64(bytesAt)
  giveBytesBlock: heap.give(bytesBlock)
  goto giveNode
:arrayCheck in=eachValue
  checkArray: isArray = compare.equalInt64(kind, kindArray)
  if isArray startItems objectCheck
:startItems in=eachValue
  set at zero
  readItemCount: itemCount = word(current, twentyFour=24)
  readItems: itemsAt = word(current, sixteen)
  itemsAddress: items = machine.fromInt64(itemsAt)
  goto eachItem
:eachItem loop=while max=itemCount in=eachValue
  itemsDone: allItems = compare.greaterOrEqualInt64(at, itemCount)
  if allItems giveItems pushItem
:pushItem in=eachItem
  itemOffset: itemPlace = math.multiplyInt64(at, eight)
  findItem: itemSlot = machine.offset(items, itemPlace)
  readItem: item = machine.loadAddress(itemSlot)
  pushIt: pushedItem = push(list, item)
  set list pushedItem
  nextItem: afterItem = math.addInt64(at, one)
  set at afterItem
  goto eachItem
:giveItems in=eachValue
  giveItemsBlock: heap.give(items)
  goto giveNode
:objectCheck in=eachValue
  checkObject: isObject = compare.equalInt64(kind, kindObject)
  if isObject startRows giveNode
:startRows in=eachValue
  set at zero
  findTable: table = machine.offset(current, forty=40)
  readRows: rowCount = word(table, forty)
  goto eachRow
:eachRow loop=while max=rowCount in=eachValue
  rowsDone: allRows = compare.greaterOrEqualInt64(at, rowCount)
  if allRows giveTable pushRow
:pushRow in=eachRow
  findRow: row = tables.rowAddress(table, at)
  findKey: keySlot = machine.offset(row, sixteen)
  readKey: key = machine.loadAddress(keySlot)
  giveKey: heap.give(key)
  findChild: childSlot = machine.offset(row, thirtyTwo=32)
  readChild: child = machine.loadAddress(childSlot)
  pushChild: pushedChild = push(list, child)
  set list pushedChild
  nextRow: afterRow = math.addInt64(at, one)
  set at afterRow
  goto eachRow
:giveTable in=eachValue
  releaseTable: tables.release(table)
  goto giveNode
:giveNode in=eachValue
  giveIt: heap.give(current)
  goto eachValue
:finish
  giveList: heap.give(list)
  return freed

op appendItem "Add a value to the end of an array, which takes over the caller's hold on it; the items' block doubles (from 8) when full"
  invariant appendsLast "The array holds one item more, the value last"
  input array machine.Address copied
  input item machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readCount: count = word(array, twentyFour=24)
  readCapacity: capacity = word(array, thirtyTwo=32)
  readItems: itemsAt = word(array, sixteen=16)
  fullCheck: full = compare.greaterOrEqualInt64(count, capacity)
  if full grow store
:grow
  twice: doubled = math.multiplyInt64(capacity, two=2)
  more: grown = math.addInt64(doubled, eight=8)
  bytesOf: bytes = math.multiplyInt64(grown, eight)
  itemsAddress: oldItems = machine.fromInt64(itemsAt)
  resizeIt: resized = heap.resize(oldItems, bytes)
  newAt: resizedAt = machine.toInt64(resized)
  storeItems: setWord(array, sixteen, resizedAt)
  storeCapacity: setWord(array, thirtyTwo, grown)
  goto store
:store
  readNow: nowAt = word(array, sixteen)
  nowAddress: items = machine.fromInt64(nowAt)
  offsetOf: offset = math.multiplyInt64(count, eight)
  findSlot: slot = machine.offset(items, offset)
  storeItem: machine.storeAddress(slot, item)
  moreCount: after = math.addInt64(count, one=1)
  storeCount: setWord(array, twentyFour, after)
  return

op keySlots "Put a key's address and length in the two slots a table reads it from, and give their address"
  input key machine.Address copied
  input keyBytes Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  findSlots: slots = machine.offset(state, keySlotsAt)
  storeKey: machine.storeAddress(slots, key)
  findLength: lengthSlot = machine.offset(slots, eight=8)
  storeLength: machine.storeInt64(lengthSlot, keyBytes)
  return slots

op findField "The value of an object's key (the bytes of a range), or the address 0 when it has none"
  invariant findsKey "Gives the value last put with the key's bytes, or the address 0"
  input object machine.Address copied
  input key machine.Address copied
  input keyBytes Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findTable: table = machine.offset(object, forty=40)
  slotsOf: slots = keySlots(key, keyBytes)
  hashIt: hash = tables.hashKey(table, slots)
  findIt: row = tables.find(table, slots, hash)
  missingCheck: missing = compare.lessThanInt64(row, zero=0)
  if missing giveNone readValue
:giveNone
  nowhere: anywhere = machine.zero()
  return anywhere
:readValue
  findRow: rowAt = tables.rowAddress(table, row)
  findChild: childSlot = machine.offset(rowAt, thirtyTwo=32)
  readChild: child = machine.loadAddress(childSlot)
  return child

op putField "Set an object's key to a value, which takes over the caller's hold on it: a new key goes last, with a copy of its bytes; a key it has keeps its place and lets go of its old value"
  invariant putsKey "The key's value is the new one, a new key last in order and a key put before in its first place"
  input object machine.Address copied
  input key machine.Address copied
  input keyBytes Int64 copied
  input value machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findTable: table = machine.offset(object, forty=40)
  slotsOf: slots = keySlots(key, keyBytes)
  hashIt: hash = tables.hashKey(table, slots)
  findIt: row = tables.find(table, slots, hash)
  missingCheck: missing = compare.lessThanInt64(row, zero=0)
  if missing insertKey replace
:replace
  findRow: rowAt = tables.rowAddress(table, row)
  findChild: childSlot = machine.offset(rowAt, thirtyTwo=32)
  readChild: old = machine.loadAddress(childSlot)
  storeChild: machine.storeAddress(childSlot, value)
  letGo: freed = release(old)
  return
:insertKey
  sizeOf: copyBytes = math.addInt64(keyBytes, one=1)
  takeCopy: copy = heap.take(copyBytes)
  copyIn: machine.copy(copy, key, keyBytes)
  copySlots: copied = keySlots(copy, keyBytes)
  insertIt: newRow = tables.insert(table, copied, hash)
  findNewChild: newSlot = machine.offset(newRow, thirtyTwo)
  storeNew: machine.storeAddress(newSlot, value)
  findCount: countSlot = machine.offset(object, twentyFour=24)
  readCount: count = machine.loadInt64(countSlot)
  moreCount: after = math.addInt64(count, one)
  storeCount: machine.storeInt64(countSlot, after)
  return

## ---------------------------------------------------------------- UTF-8

op continuation "Whether the byte at a position of a range is a continuation byte within bounds (low to high, inclusive)"
  input text machine.Address copied
  input bytes Int64 copied
  input at Int64 copied
  input low Int64 copied
  input high Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let no Bool false
:begin
  insideCheck: inside = compare.lessThanInt64(at, bytes)
  if inside readIt outside
:outside
  return no
:readIt
  findByte: place = machine.offset(text, at)
  readByte: byte = machine.loadByte(place)
  widen: value = convert.byteToInt64(byte)
  lowCheck: aboveLow = compare.greaterOrEqualInt64(value, low)
  highCheck: belowHigh = compare.lessOrEqualInt64(value, high)
  bothCheck: within = logic.and(aboveLow, belowHigh)
  return within

op decodeAt "Read the character UTF-8 encodes at a position as Python's strict decoder reads it: store its code point (or -1 when the bytes there are not UTF-8) and give how many bytes it took (for bytes that are not UTF-8, the longest start of a valid sequence, at least 1)"
  invariant decodesStrictly "Valid sequences give their code point and length; overlong forms, surrogates, code points past U+10FFFF, and cut sequences give -1 and the bytes of the valid start"
  input text machine.Address copied
  input bytes Int64 copied
  input at Int64 copied
  input out machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let need Int64 0 mut
  let low Int64 128 mut
  let high Int64 191 mut
  let value Int64 0 mut
  let taken Int64 1 mut
  let invalid Int64 -1
  let one Int64 1
  let n160 Int64 160
  let n159 Int64 159
  let twoMore Int64 2
  let threeMore Int64 3
  let n144 Int64 144
  let n143 Int64 143
  let n191 Int64 191
:begin
  findByte: place = machine.offset(text, at)
  readByte: byte = machine.loadByte(place)
  widen: first = convert.byteToInt64(byte)
  asciiCheck: ascii = compare.lessThanInt64(first, n128=128)
  if ascii giveAscii twoCheck
:giveAscii
  storeAscii: machine.storeInt64(out, first)
  return one
:twoCheck
  lowTwo: atLeastTwo = compare.greaterOrEqualInt64(first, n194=194)
  highTwo: atMostTwo = compare.lessOrEqualInt64(first, n223=223)
  isTwo: two = logic.and(atLeastTwo, atMostTwo)
  if two startTwo threeCheck
:startTwo
  set need one
  maskTwo: bitsTwo = bits.andInt64(first, n31=31)
  set value bitsTwo
  goto eachMore
:threeCheck
  lowThree: atLeastThree = compare.greaterOrEqualInt64(first, n224=224)
  highThree: atMostThree = compare.lessOrEqualInt64(first, n239=239)
  isThree: three = logic.and(atLeastThree, atMostThree)
  if three startThree fourCheck
:startThree
  set need twoMore
  maskThree: bitsThree = bits.andInt64(first, n15=15)
  set value bitsThree
  e0Check: isE0 = compare.equalInt64(first, n224)
  if isE0 lowE0 edCheck
:lowE0
  set low n160
  goto eachMore
:edCheck
  checkEd: isEd = compare.equalInt64(first, n237=237)
  if isEd highEd eachMore
:highEd
  set high n159
  goto eachMore
:fourCheck
  lowFour: atLeastFour = compare.greaterOrEqualInt64(first, n240=240)
  highFour: atMostFour = compare.lessOrEqualInt64(first, n244=244)
  isFour: four = logic.and(atLeastFour, atMostFour)
  if four startFour bad
:startFour
  set need threeMore
  maskFour: bitsFour = bits.andInt64(first, n7=7)
  set value bitsFour
  f0Check: isF0 = compare.equalInt64(first, n240)
  if isF0 lowF0 f4Check
:lowF0
  set low n144
  goto eachMore
:f4Check
  checkF4: isF4 = compare.equalInt64(first, n244)
  if isF4 highF4 eachMore
:highF4
  set high n143
  goto eachMore
:eachMore loop=while max=4
  doneCheck: done = compare.equalInt64(need, zero=0)
  if done give readMore
:readMore in=eachMore
  nextAt: position = math.addInt64(at, taken)
  validCheck: valid = continuation(text, bytes, position, low, high)
  if valid addMore bad
:addMore in=eachMore
  findNext: nextPlace = machine.offset(text, position)
  readNext: nextByte = machine.loadByte(nextPlace)
  widenNext: next = convert.byteToInt64(nextByte)
  lowBits: six = bits.andInt64(next, n63=63)
  shiftValue: shifted = bits.shiftLeftInt64(value, sixBits=6)
  joinValue: joined = bits.orInt64(shifted, six)
  set value joined
  moreTaken: afterTaken = math.addInt64(taken, one)
  set taken afterTaken
  lessNeed: afterNeed = math.subtractInt64(need, one)
  set need afterNeed
  set low n128
  set high n191
  goto eachMore
:give
  storeValue: machine.storeInt64(out, value)
  return taken
:bad
  storeBad: machine.storeInt64(out, invalid)
  return taken

@tests

test valuesTest "Values are held and given back with what they hold; arrays keep their items in order; objects keep their keys in first-put order, their last values, and find them by their bytes"
  verifies newValue startsHeld
  verifies retain countsHolder
  verifies release givesBackLast
  verifies appendItem appendsLast
  verifies findField findsKey
  verifies putField putsKey
  verifies decodeAt decodesStrictly
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let hundred Int64 100
  let keyA String "a"
  let keyB String "bb"
  let keyAgain String "a"
  let mixed String "A\xc3\xa9\xf0\x9f\x98\x80"
  let bad String "\xe2\x82A\xed\xa0\x80\xc0\xaf"
  let three Int64 3
  let six Int64 6
  let zero Int64 0
:begin
  makeArray: array = newValue(kindArray)
  makeShared: shared = newValue(kindText)
  holdShared: retain(shared)
  addShared: appendItem(array, shared)
  goto eachItem
:eachItem loop=while max=hundred
  itemsDone: done = compare.greaterOrEqualInt64(at, hundred)
  if done checkItems addItem
:addItem in=eachItem
  makeItem: item = newValue(kindNull)
  addIt: appendItem(array, item)
  nextItem: after = math.addInt64(at, one=1)
  set at after
  goto eachItem
:checkItems
  readCount: count = word(array, twentyFour=24)
  expectCount: test.assertEqualInt64(n101=101, count)
  makeObject: object = newValue(kindObject)
  findA: aAt = machine.addressOfString(keyA)
  findB: bAt = machine.addressOfString(keyB)
  findAgain: againAt = machine.addressOfString(keyAgain)
  makeFirst: first = newValue(kindNull)
  putA: putField(object, aAt, one, first)
  makeSecond: second = newValue(kindNull)
  putB: putField(object, bAt, two=2, second)
  holdArray: retain(array)
  putAgain: putField(object, againAt, one, array)
  readFound: found = findField(object, againAt, one)
  sameCheck: same = machine.equal(found, array)
  test.assertTrue(same)
  readMissing: missing = findField(object, bAt, one)
  nowhere: anywhere = machine.zero()
  missingCheck: isMissing = machine.equal(missing, anywhere)
  test.assertTrue(isMissing)
  readFields: fields = word(object, twentyFour)
  expectFields: test.assertEqualInt64(two, fields)
  dropObject: objectFreed = release(object)
  expectObject: test.assertEqualInt64(two, objectFreed)
  dropArray: arrayFreed = release(array)
  expectArray: test.assertEqualInt64(n101, arrayFreed)
  dropShared: sharedFreed = release(shared)
  expectShared: test.assertEqualInt64(one, sharedFreed)
  findCode: codeAt = kernel.stateAt(codeOffset=61440)
  findMixed: mixedAt = machine.addressOfString(mixed)
  mixedLength: mixedBytes = string.byteLength(mixed)
  decodeAscii: asciiTaken = decodeAt(mixedAt, mixedBytes, zero, codeAt)
  expectAsciiTaken: test.assertEqualInt64(one, asciiTaken)
  readAscii: asciiCode = machine.loadInt64(codeAt)
  expectAscii: test.assertEqualInt64(n65=65, asciiCode)
  decodeTwo: twoTaken = decodeAt(mixedAt, mixedBytes, one, codeAt)
  expectTwoTaken: test.assertEqualInt64(two, twoTaken)
  readTwo: twoCode = machine.loadInt64(codeAt)
  expectTwo: test.assertEqualInt64(n233=233, twoCode)
  decodeFour: fourTaken = decodeAt(mixedAt, mixedBytes, three, codeAt)
  expectFourTaken: test.assertEqualInt64(four=4, fourTaken)
  readFour: fourCode = machine.loadInt64(codeAt)
  expectFour: test.assertEqualInt64(n128512=128512, fourCode)
  findBad: badAt = machine.addressOfString(bad)
  badLength: badBytes = string.byteLength(bad)
  decodeCut: cutTaken = decodeAt(badAt, badBytes, zero, codeAt)
  expectCutTaken: test.assertEqualInt64(two, cutTaken)
  readCut: cutCode = machine.loadInt64(codeAt)
  expectCut: test.assertEqualInt64(minusOne=-1, cutCode)
  decodeSurrogate: surrogateTaken = decodeAt(badAt, badBytes, three, codeAt)
  expectSurrogateTaken: test.assertEqualInt64(one, surrogateTaken)
  decodeOverlong: overlongTaken = decodeAt(badAt, badBytes, six, codeAt)
  expectOverlongTaken: test.assertEqualInt64(one, overlongTaken)
  readOverlong: overlongCode = machine.loadInt64(codeAt)
  expectOverlong: test.assertEqualInt64(minusOne, overlongCode)
  return
