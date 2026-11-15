module tables "Tables of rows kept in the order their keys were first put, found by hashing: what maps and sets are made of"
  path tables
  imports standard.machine standard.math standard.compare standard.convert standard.bits standard.logic standard.test memory heap
  exports prepare shape rowAddress hashKey find insert remove release keyAt live

capability memoryAccess "Authority to keep a table's rows and index in memory" use machine.memory none

capability systemCalls "Authority to take memory for a table's rows and index from the process heap" use system.calls none

## A table is 88 bytes inside the object that holds it: at 0 whether its keys are text (1) or not (0), 8 how many
## 64-bit slots a key takes and 16 a value (-1 until a call shows it), 24 the slots of a row (2 + key + value, 0
## until both are known), 32 the address of its rows, 40 how many rows it has, 48 how many slots the rows' block
## holds, 56 how many rows are live, 64 the address of its index, 72 how many entries the index has (a power of
## two), 80 how many of them are taken. A row is [live, hash, key slots..., value slots...]; a removed row stays,
## not live, until the rows are compacted. An index entry is a row's number plus one, 0 when empty, -1 when its row
## was removed. A text key (D-61) is two slots, an address and a length, compared by its bytes.
constant tableBytes "The bytes of a table" Int64 88

## ---------------------------------------------------------------- shape

op prepare "Start a table: whether its keys are text, and the slots of a key and of a value when they are known (-1 when not)"
  invariant startsEmpty "A prepared table has no rows and states its keys' kind and whatever slots it was given"
  input table machine.Address copied
  input text Int64 copied
  input keySlots Int64 copied
  input valueSlots Int64 copied
  effect use machine.memory
  uses memoryAccess
  let unknown Int64 -1
:begin
  storeText: machine.storeInt64(table, text)
  findKeys: keysSlot = machine.offset(table, eight=8)
  storeKeys: machine.storeInt64(keysSlot, unknown)
  findValues: valuesSlot = machine.offset(table, sixteen=16)
  storeValues: machine.storeInt64(valuesSlot, unknown)
  findStride: strideSlot = machine.offset(table, twentyFour=24)
  storeStride: machine.storeInt64(strideSlot, zero=0)
  learn: shape(table, keySlots, valueSlots)
  return

op shape "Learn a table's key and value slots from a call, each only while it is unknown; the row's slots follow once both are known"
  invariant learnsOnce "A key's or value's slots are set by the first call that knows them and never change; the row is 2 slots more than the two"
  input table machine.Address copied
  input keySlots Int64 copied
  input valueSlots Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  findKeys: keysSlot = machine.offset(table, eight=8)
  readKeys: keys = machine.loadInt64(keysSlot)
  keysUnknown: noKeys = compare.lessThanInt64(keys, zero=0)
  keysGiven: haveKeys = compare.greaterOrEqualInt64(keySlots, zero)
  keysLearn: learnKeys = logic.and(noKeys, haveKeys)
  if learnKeys storeKeys valueSlotsOf
:storeKeys
  setKeys: machine.storeInt64(keysSlot, keySlots)
  goto valueSlotsOf
:valueSlotsOf
  findValues: valuesSlot = machine.offset(table, sixteen=16)
  readValues: values = machine.loadInt64(valuesSlot)
  valuesUnknown: noValues = compare.lessThanInt64(values, zero)
  valuesGiven: haveValues = compare.greaterOrEqualInt64(valueSlots, zero)
  valuesLearn: learnValues = logic.and(noValues, haveValues)
  if learnValues storeValues strideOf
:storeValues
  setValues: machine.storeInt64(valuesSlot, valueSlots)
  goto strideOf
:strideOf
  readKeysNow: keysNow = machine.loadInt64(keysSlot)
  readValuesNow: valuesNow = machine.loadInt64(valuesSlot)
  keysKnown: knownKeys = compare.greaterOrEqualInt64(keysNow, zero)
  valuesKnown: knownValues = compare.greaterOrEqualInt64(valuesNow, zero)
  bothKnown: known = logic.and(knownKeys, knownValues)
  if known storeStride done
:storeStride
  sumSlots: slots = math.addInt64(keysNow, valuesNow)
  rowSlots: stride = math.addInt64(slots, two=2)
  findStride: strideSlot = machine.offset(table, twentyFour=24)
  setStride: machine.storeInt64(strideSlot, stride)
  goto done
:done
  return

op rowAddress "The address of a row of a table, by its number"
  invariant findsRow "Row n starts n rows' slots after the first row"
  input table machine.Address copied
  input row Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findStride: strideSlot = machine.offset(table, twentyFour=24)
  readStride: stride = machine.loadInt64(strideSlot)
  findRows: rowsSlot = machine.offset(table, thirtyTwo=32)
  readRows: rows = machine.loadAddress(rowsSlot)
  slotsBefore: slots = math.multiplyInt64(row, stride)
  bytesBefore: bytes = math.multiplyInt64(slots, eight=8)
  findRow: at = machine.offset(rows, bytes)
  return at

## ---------------------------------------------------------------- hashing

op finish "Mix a hash's bits so every bit of it depends on every bit of what was hashed"
  input hash UInt64 copied
  output UInt64
  let first UInt64 18397679294719823053
  let second UInt64 14181476777654086739
:begin
  shiftOne: highOne = bits.shiftRightUInt64(hash, thirtyThree=33)
  mixOne: mixedOne = bits.xorUInt64(hash, highOne)
  spreadOne: spreadFirst = math.wrappingMultiplyUInt64(mixedOne, first)
  shiftTwo: highTwo = bits.shiftRightUInt64(spreadFirst, thirtyThree)
  mixTwo: mixedTwo = bits.xorUInt64(spreadFirst, highTwo)
  spreadTwo: spreadSecond = math.wrappingMultiplyUInt64(mixedTwo, second)
  shiftThree: highThree = bits.shiftRightUInt64(spreadSecond, thirtyThree)
  mixThree: mixed = bits.xorUInt64(spreadSecond, highThree)
  return mixed

op hashKey "A key's hash: a text key's bytes, or every slot of another key with its position, then mixed"
  invariant hashesContent "Keys with the same bytes (text) or the same slots (any other key) have the same hash, wherever they are"
  input table machine.Address copied
  input key machine.Address copied
  output UInt64
  effect use machine.memory
  uses memoryAccess
  let hash UInt64 1469598103934665603 mut
  let prime UInt64 1099511628211
  let at Int64 0 mut
:begin
  readText: text = machine.loadInt64(table)
  textCheck: isText = compare.notEqualInt64(text, zero=0)
  if isText textBytes slotsOf
:textBytes
  readAddress: bytesAt = machine.loadAddress(key)
  findLength: lengthSlot = machine.offset(key, eight=8)
  readLength: length = machine.loadInt64(lengthSlot)
  goto eachByte
:eachByte loop=while max=length
  bytesDone: doneBytes = compare.greaterOrEqualInt64(at, length)
  if doneBytes mix hashByte
:hashByte in=eachByte
  findByte: byteAt = machine.offset(bytesAt, at)
  readByte: byte = machine.loadByte(byteAt)
  widenByte: byteValue = convert.byteToUInt64(byte)
  mixByte: mixedByte = bits.xorUInt64(hash, byteValue)
  spreadByte: spread = math.wrappingMultiplyUInt64(mixedByte, prime)
  set hash spread
  nextByte: afterByte = math.addInt64(at, one=1)
  set at afterByte
  goto eachByte
:slotsOf
  findKeys: keysSlot = machine.offset(table, eight=8)
  readKeys: keys = machine.loadInt64(keysSlot)
  goto eachSlot
:eachSlot loop=while max=keys
  slotsDone: doneSlots = compare.greaterOrEqualInt64(at, keys)
  if doneSlots mix hashSlot
:hashSlot in=eachSlot
  slotBytes: slotOffset = math.multiplyInt64(at, eight=8)
  findSlot: slotAt = machine.offset(key, slotOffset)
  readSlot: slot = machine.loadUInt64(slotAt)
  mixSlot: mixedSlot = bits.xorUInt64(hash, slot)
  spreadSlot: spreadValue = math.wrappingMultiplyUInt64(mixedSlot, prime)
  widenAt: atValue = convert.int64ToUInt64(at)
  addAt: withAt = math.wrappingAddUInt64(spreadValue, atValue)
  set hash withAt
  nextSlot: afterSlot = math.addInt64(at, one)
  set at afterSlot
  goto eachSlot
:mix
  finishHash: mixed = finish(hash)
  return mixed

op sameKey "Whether two keys of a table are the same: text by its bytes, any other key slot by slot"
  input table machine.Address copied
  input left machine.Address copied
  input right machine.Address copied
  output Bool
  effect use machine.memory
  uses memoryAccess
:begin
  readText: text = machine.loadInt64(table)
  textCheck: isText = compare.notEqualInt64(text, zero=0)
  if isText compareText compareSlots
:compareText
  readLeft: leftAt = machine.loadAddress(left)
  findLeftLength: leftLengthSlot = machine.offset(left, eight=8)
  readLeftLength: leftLength = machine.loadInt64(leftLengthSlot)
  readRight: rightAt = machine.loadAddress(right)
  findRightLength: rightLengthSlot = machine.offset(right, eight)
  readRightLength: rightLength = machine.loadInt64(rightLengthSlot)
  compareBytes: equal = memory.bytesEqual(leftAt, leftLength, rightAt, rightLength)
  equalCheck: same = compare.notEqualInt32(equal, zero32=0)
  return same
:compareSlots
  findKeys: keysSlot = machine.offset(table, eight)
  readKeys: keys = machine.loadInt64(keysSlot)
  keyBytes: bytes = math.multiplyInt64(keys, eight)
  compareRange: order = machine.compare(left, right, bytes)
  slotsCheck: sameSlots = compare.equalInt32(order, zero32)
  return sameSlots

## ---------------------------------------------------------------- finding, placing, and removing rows

op find "The number of the live row with a key, or -1 when no row has it"
  invariant findsLive "Gives the row a key was inserted in until it is removed; -1 for a key never inserted or removed since"
  input table machine.Address copied
  input key machine.Address copied
  input hash UInt64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at UInt64 0 mut
  let missing Int64 -1
:begin
  findCap: capSlot = machine.offset(table, seventyTwo=72)
  readCap: cap = machine.loadInt64(capSlot)
  findStride: strideSlot = machine.offset(table, twentyFour=24)
  readStride: stride = machine.loadInt64(strideSlot)
  noIndexCheck: noIndex = compare.equalInt64(cap, zero=0)
  noShapeCheck: noShape = compare.equalInt64(stride, zero)
  emptyCheck: empty = logic.or(noIndex, noShape)
  if empty notFound search
:search
  findIndex: indexSlot = machine.offset(table, sixtyFour=64)
  readIndex: index = machine.loadAddress(indexSlot)
  capOf: capWide = convert.int64ToUInt64(cap)
  maskOf: mask = math.subtractUInt64(capWide, oneWide=1)
  firstAt: start = bits.andUInt64(hash, mask)
  set at start
  goto eachEntry
:eachEntry loop=while max=cap
  entryOffset: entryNumber = convert.uint64ToInt64(at)
  entryBytes: entryOffsetBytes = math.multiplyInt64(entryNumber, eight=8)
  findEntry: entryAt = machine.offset(index, entryOffsetBytes)
  readEntry: entry = machine.loadInt64(entryAt)
  emptyEntryCheck: emptyEntry = compare.equalInt64(entry, zero)
  if emptyEntry notFound liveCheck
:liveCheck in=eachEntry
  liveEntryCheck: liveEntry = compare.greaterThanInt64(entry, zero)
  if liveEntry compareRow nextEntry
:compareRow in=eachEntry
  rowOf: row = math.subtractInt64(entry, one=1)
  findRow: rowAt = rowAddress(table, row)
  findHash: hashAt = machine.offset(rowAt, eight)
  readHash: rowHash = machine.loadUInt64(hashAt)
  hashCheck: sameHash = compare.equalUInt64(rowHash, hash)
  if sameHash compareKey nextEntry
:compareKey in=eachEntry
  findKey: keyPlace = machine.offset(rowAt, sixteen=16)
  keyCheck: sameRowKey = sameKey(table, keyPlace, key)
  if sameRowKey found nextEntry
:found
  return row
:nextEntry in=eachEntry
  stepAt: stepped = math.addUInt64(at, oneWide)
  wrapAt: wrapped = bits.andUInt64(stepped, mask)
  set at wrapped
  goto eachEntry
:notFound
  return missing

op place "Put a row's number in the first free entry of the index after its hash"
  input table machine.Address copied
  input row Int64 copied
  input hash UInt64 copied
  effect use machine.memory
  uses memoryAccess
  let at UInt64 0 mut
:begin
  findCap: capSlot = machine.offset(table, seventyTwo=72)
  readCap: cap = machine.loadInt64(capSlot)
  findIndex: indexSlot = machine.offset(table, sixtyFour=64)
  readIndex: index = machine.loadAddress(indexSlot)
  capOf: capWide = convert.int64ToUInt64(cap)
  maskOf: mask = math.subtractUInt64(capWide, oneWide=1)
  firstAt: start = bits.andUInt64(hash, mask)
  set at start
  goto eachEntry
:eachEntry loop=while max=cap
  entryOffset: entryNumber = convert.uint64ToInt64(at)
  entryBytes: entryOffsetBytes = math.multiplyInt64(entryNumber, eight=8)
  findEntry: entryAt = machine.offset(index, entryOffsetBytes)
  readEntry: entry = machine.loadInt64(entryAt)
  takenCheck: taken = compare.greaterThanInt64(entry, zero=0)
  if taken nextEntry fill
:nextEntry in=eachEntry
  stepAt: stepped = math.addUInt64(at, oneWide)
  wrapAt: wrapped = bits.andUInt64(stepped, mask)
  set at wrapped
  goto eachEntry
:fill
  emptyCheck: wasEmpty = compare.equalInt64(entry, zero)
  if wasEmpty countUsed store
:countUsed
  findUsed: usedSlot = machine.offset(table, eighty=80)
  readUsed: used = machine.loadInt64(usedSlot)
  moreUsed: nowUsed = math.addInt64(used, one=1)
  storeUsed: machine.storeInt64(usedSlot, nowUsed)
  goto store
:store
  entryOf: value = math.addInt64(row, one)
  storeEntry: machine.storeInt64(entryAt, value)
  return

op rebuild "Drop removed rows, keeping the order of the rest, and index them again in an index of at least a number of entries"
  input table machine.Address copied
  input want Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let from Int64 0 mut
  let to Int64 0 mut
  let cap Int64 16 mut
  let sixtyFour Int64 64
:begin
  findStride: strideSlot = machine.offset(table, twentyFour=24)
  readStride: stride = machine.loadInt64(strideSlot)
  strideBytes: rowBytes = math.multiplyInt64(stride, eight=8)
  findCount: countSlot = machine.offset(table, forty=40)
  readCount: count = machine.loadInt64(countSlot)
  goto eachRow
:eachRow loop=while max=count
  rowsDone: doneRows = compare.greaterOrEqualInt64(from, count)
  if doneRows sized checkRow
:checkRow in=eachRow
  findFrom: fromAt = rowAddress(table, from)
  readLive: liveMark = machine.loadInt64(fromAt)
  liveCheck: isLive = compare.notEqualInt64(liveMark, zero=0)
  if isLive keepRow nextRow
:keepRow in=eachRow
  movedCheck: moved = compare.notEqualInt64(from, to)
  if moved moveRow keptRow
:moveRow in=eachRow
  findTo: toAt = rowAddress(table, to)
  moveBytes: machine.copy(toAt, fromAt, rowBytes)
  goto keptRow
:keptRow in=eachRow
  advanceTo: nextTo = math.addInt64(to, one=1)
  set to nextTo
  goto nextRow
:nextRow in=eachRow
  advanceFrom: nextFrom = math.addInt64(from, one)
  set from nextFrom
  goto eachRow
:sized
  storeCount: machine.storeInt64(countSlot, to)
  keepCount: kept = math.addInt64(to, zero)
  findLive: liveSlot = machine.offset(table, fiftySix=56)
  readLiveCount: liveCount = machine.loadInt64(liveSlot)
  moreLive: liveMore = math.addInt64(liveCount, one)
  roomOf: room = math.multiplyInt64(liveMore, two=2)
  goto eachSize
:eachSize loop=while max=sixtyFour
  wantCheck: belowWant = compare.lessThanInt64(cap, want)
  roomCheck: belowRoom = compare.lessThanInt64(cap, room)
  smallCheck: small = logic.or(belowWant, belowRoom)
  if small doubleCap index
:doubleCap in=eachSize
  doubled: twice = math.multiplyInt64(cap, two)
  set cap twice
  goto eachSize
:index
  findIndex: indexSlot = machine.offset(table, sixtyFour=64)
  readIndex: oldIndex = machine.loadAddress(indexSlot)
  giveIndex: heap.give(oldIndex)
  indexBytes: freshBytes = math.multiplyInt64(cap, eight)
  takeIndex: fresh = heap.take(freshBytes)
  storeIndex: machine.storeAddress(indexSlot, fresh)
  findCap: capSlot = machine.offset(table, seventyTwo=72)
  storeCap: machine.storeInt64(capSlot, cap)
  findUsed: usedSlot = machine.offset(table, eighty=80)
  storeUsed: machine.storeInt64(usedSlot, zero)
  set from zero
  goto eachPlace
:eachPlace loop=while max=kept
  placedCheck: placed = compare.greaterOrEqualInt64(from, kept)
  if placed done placeRow
:placeRow in=eachPlace
  findPlaced: placedAt = rowAddress(table, from)
  findHash: hashAt = machine.offset(placedAt, eight)
  readHash: hash = machine.loadUInt64(hashAt)
  putRow: place(table, from, hash)
  advancePlace: nextPlace = math.addInt64(from, one)
  set from nextPlace
  goto eachPlace
:done
  return

op insert "A new live row for a key the table does not have, its value slots zero; gives the row's address"
  invariant insertsLast "The new row is the last, live, holds the key and its hash, and is found by the key"
  input table machine.Address copied
  input key machine.Address copied
  input hash UInt64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let rowCap Int64 0 mut
  let eight Int64 8
  let sixtyFour Int64 64
:begin
  findUsed: usedSlot = machine.offset(table, eighty=80)
  readUsed: used = machine.loadInt64(usedSlot)
  findCap: capSlot = machine.offset(table, seventyTwo=72)
  readCap: cap = machine.loadInt64(capSlot)
  usedMore: nextUsed = math.addInt64(used, one=1)
  usedTwice: needed = math.multiplyInt64(nextUsed, two=2)
  fullCheck: full = compare.greaterThanInt64(needed, cap)
  if full reindex appendRow
:reindex
  findLive: liveSlot = machine.offset(table, fiftySix=56)
  readLive: liveNumber = machine.loadInt64(liveSlot)
  wantOf: want = math.multiplyInt64(liveNumber, four=4)
  again: rebuild(table, want)
  goto appendRow
:appendRow
  findStride: strideSlot = machine.offset(table, twentyFour=24)
  readStride: stride = machine.loadInt64(strideSlot)
  findCount: countSlot = machine.offset(table, forty=40)
  readCount: count = machine.loadInt64(countSlot)
  countMore: nextCount = math.addInt64(count, one)
  slotsNeeded: neededSlots = math.multiplyInt64(nextCount, stride)
  findRowCap: rowCapSlot = machine.offset(table, fortyEight=48)
  readRowCap: heldSlots = machine.loadInt64(rowCapSlot)
  roomCheck: enough = compare.lessOrEqualInt64(neededSlots, heldSlots)
  if enough fill growRows
:growRows
  set rowCap heldSlots
  noneCheck: noRows = compare.equalInt64(heldSlots, zero=0)
  if noRows startRows eachDouble
:startRows
  set rowCap eight
  goto eachDouble
:eachDouble loop=while max=sixtyFour
  smallCheck: small = compare.lessThanInt64(rowCap, neededSlots)
  if small doubleRows resizeRows
:doubleRows in=eachDouble
  doubled: twice = math.multiplyInt64(rowCap, two)
  set rowCap twice
  goto eachDouble
:resizeRows
  findRows: rowsSlot = machine.offset(table, thirtyTwo=32)
  readRows: rows = machine.loadAddress(rowsSlot)
  rowsBytes: newBytes = math.multiplyInt64(rowCap, eight)
  growBlock: grown = heap.resize(rows, newBytes)
  storeRows: machine.storeAddress(rowsSlot, grown)
  storeRowCap: machine.storeInt64(rowCapSlot, rowCap)
  goto fill
:fill
  storeCount: machine.storeInt64(countSlot, nextCount)
  findRow: rowAt = rowAddress(table, count)
  strideBytes: rowBytes = math.multiplyInt64(stride, eight)
  clearRow: machine.fill(rowAt, zeroByte=0, rowBytes)
  markLive: machine.storeInt64(rowAt, one)
  findHash: hashAt = machine.offset(rowAt, eight)
  storeHash: machine.storeUInt64(hashAt, hash)
  findKeys: keysSlot = machine.offset(table, eight)
  readKeys: keys = machine.loadInt64(keysSlot)
  keyBytes: keyLength = math.multiplyInt64(keys, eight)
  findKey: keyPlace = machine.offset(rowAt, sixteen=16)
  copyKey: machine.copy(keyPlace, key, keyLength)
  placeRow: place(table, count, hash)
  findLiveNow: liveNowSlot = machine.offset(table, fiftySix)
  readLiveNow: liveNow = machine.loadInt64(liveNowSlot)
  moreLive: liveMore = math.addInt64(liveNow, one)
  storeLive: machine.storeInt64(liveNowSlot, liveMore)
  return rowAt

op remove "Remove a live row: its index entry is marked removed and the row is no longer live"
  invariant removesRow "A removed row's key is no longer found and the table has one live row fewer"
  input table machine.Address copied
  input row Int64 copied
  effect use machine.memory
  uses memoryAccess
  let at UInt64 0 mut
  let removed Int64 -1
:begin
  findRow: rowAt = rowAddress(table, row)
  findHash: hashAt = machine.offset(rowAt, eight=8)
  readHash: hash = machine.loadUInt64(hashAt)
  findCap: capSlot = machine.offset(table, seventyTwo=72)
  readCap: cap = machine.loadInt64(capSlot)
  findIndex: indexSlot = machine.offset(table, sixtyFour=64)
  readIndex: index = machine.loadAddress(indexSlot)
  capOf: capWide = convert.int64ToUInt64(cap)
  maskOf: mask = math.subtractUInt64(capWide, oneWide=1)
  firstAt: start = bits.andUInt64(hash, mask)
  set at start
  entryOf: wanted = math.addInt64(row, one=1)
  goto eachEntry
:eachEntry loop=while max=cap
  entryOffset: entryNumber = convert.uint64ToInt64(at)
  entryBytes: entryOffsetBytes = math.multiplyInt64(entryNumber, eight)
  findEntry: entryAt = machine.offset(index, entryOffsetBytes)
  readEntry: entry = machine.loadInt64(entryAt)
  matchCheck: matches = compare.equalInt64(entry, wanted)
  if matches mark nextEntry
:nextEntry in=eachEntry
  stepAt: stepped = math.addUInt64(at, oneWide)
  wrapAt: wrapped = bits.andUInt64(stepped, mask)
  set at wrapped
  goto eachEntry
:mark
  markEntry: machine.storeInt64(entryAt, removed)
  clearLive: machine.storeInt64(rowAt, zero=0)
  findLive: liveSlot = machine.offset(table, fiftySix=56)
  readLive: liveNumber = machine.loadInt64(liveSlot)
  fewerLive: liveLess = math.subtractInt64(liveNumber, one)
  storeLive: machine.storeInt64(liveSlot, liveLess)
  return

op live "How many live rows a table has"
  invariant countsLive "Each insert counts one more and each remove one fewer"
  input table machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findLive: liveSlot = machine.offset(table, fiftySix=56)
  readLive: count = machine.loadInt64(liveSlot)
  return count

op keyAt "The address of the key of the live row at a position in first-put order, compacting the rows first when some were removed; the position is below the live count"
  invariant keysInOrder "Position n is the key of the n-th live row in the order the rows were inserted"
  input table machine.Address copied
  input position Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findCount: countSlot = machine.offset(table, forty=40)
  readCount: count = machine.loadInt64(countSlot)
  findLive: liveSlot = machine.offset(table, fiftySix=56)
  readLive: liveCount = machine.loadInt64(liveSlot)
  removedCheck: anyRemoved = compare.notEqualInt64(count, liveCount)
  if anyRemoved compact read
:compact
  findCap: capSlot = machine.offset(table, seventyTwo=72)
  readCap: cap = machine.loadInt64(capSlot)
  again: rebuild(table, cap)
  goto read
:read
  findRow: rowAt = rowAddress(table, position)
  findKey: keyPlace = machine.offset(rowAt, sixteen=16)
  return keyPlace

op release "Give back a table's rows and index"
  invariant givesBack "The rows' block and the index go back to the heap and the table has no rows"
  input table machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findRows: rowsSlot = machine.offset(table, thirtyTwo=32)
  readRows: rows = machine.loadAddress(rowsSlot)
  giveRows: heap.give(rows)
  findIndex: indexSlot = machine.offset(table, sixtyFour=64)
  readIndex: index = machine.loadAddress(indexSlot)
  giveIndex: heap.give(index)
  nowhere: anywhere = machine.zero()
  clearRows: machine.storeAddress(rowsSlot, anywhere)
  clearIndex: machine.storeAddress(indexSlot, anywhere)
  findCount: countSlot = machine.offset(table, forty=40)
  clearCount: machine.storeInt64(countSlot, zero=0)
  findRowCap: rowCapSlot = machine.offset(table, fortyEight=48)
  clearRowCap: machine.storeInt64(rowCapSlot, zero)
  findLive: liveSlot = machine.offset(table, fiftySix=56)
  clearLive: machine.storeInt64(liveSlot, zero)
  findCap: capSlot = machine.offset(table, seventyTwo=72)
  clearCap: machine.storeInt64(capSlot, zero)
  findUsed: usedSlot = machine.offset(table, eighty=80)
  clearUsed: machine.storeInt64(usedSlot, zero)
  return

@tests

## Tests keep their table in the last 4 KiB of machine.state (from byte 61440), which the runtime's own state never
## reaches, and their keys after it, from byte 61568.

op putNumber "Insert a one-slot key into the test table unless it is there, and give its row"
  input table machine.Address copied
  input number Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findState: state = machine.state()
  findKey: key = machine.offset(state, keyScratch=61568)
  storeKey: machine.storeInt64(key, number)
  hashOf: hash = hashKey(table, key)
  findRow: row = find(table, key, hash)
  missingCheck: missing = compare.lessThanInt64(row, zero=0)
  if missing add known
:add
  addRow: rowAt = insert(table, key, hash)
  countOf: count = live(table)
  lastOf: last = math.subtractInt64(count, one=1)
  return last
:known
  return row

op findNumber "The row of a one-slot key in the test table, or -1"
  input table machine.Address copied
  input number Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  findKey: key = machine.offset(state, keyScratch=61568)
  storeKey: machine.storeInt64(key, number)
  hashOf: hash = hashKey(table, key)
  findRow: row = find(table, key, hash)
  return row

op keyNumber "The one-slot key at a position of the test table"
  input table machine.Address copied
  input position Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findKey: key = keyAt(table, position)
  readKey: number = machine.loadInt64(key)
  return number

test numberTableTest "Keys are found after they are inserted and not after they are removed, read back in the order they were first inserted, and survive the index growing"
  verifies prepare startsEmpty
  verifies shape learnsOnce
  verifies rowAddress findsRow
  verifies hashKey hashesContent
  verifies find findsLive
  verifies insert insertsLast
  verifies remove removesRow
  verifies live countsLive
  verifies keyAt keysInOrder
  verifies release givesBack
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let n Int64 0 mut
  let hundred Int64 100
:begin
  findState: state = machine.state()
  findTable: table = machine.offset(state, tableAt=61440)
  clearTable: machine.fill(table, zeroByte=0, tableBytes)
  start: prepare(table, zero=0, minusOne=-1, zero)
  learn: shape(table, one=1, zero)
  learnAgain: shape(table, two=2, two)
  findStride: strideSlot = machine.offset(table, twentyFour=24)
  readStride: stride = machine.loadInt64(strideSlot)
  expectStride: test.assertEqualInt64(three=3, stride)
  goto eachPut
:eachPut loop=while max=hundred
  putsDone: donePuts = compare.greaterOrEqualInt64(n, hundred)
  if donePuts checkPuts putOne
:putOne in=eachPut
  timesSeven: seventh = math.multiplyInt64(n, seven=7)
  putKey: row = putNumber(table, seventh)
  expectRow: test.assertEqualInt64(n, row)
  nextPut: afterPut = math.addInt64(n, one)
  set n afterPut
  goto eachPut
:checkPuts
  countPuts: count = live(table)
  expectCount: test.assertEqualInt64(hundred, count)
  putAgain: againRow = putNumber(table, fourteen=14)
  expectSame: test.assertEqualInt64(two, againRow)
  findMissing: missingRow = findNumber(table, fifteen=15)
  expectMissing: test.assertEqualInt64(minusOne, missingRow)
  findSeventy: seventyRow = findNumber(table, seventy=70)
  expectSeventy: test.assertEqualInt64(ten=10, seventyRow)
  dropSeventy: remove(table, seventyRow)
  findGone: goneRow = findNumber(table, seventy)
  expectGone: test.assertEqualInt64(minusOne, goneRow)
  countLeft: left = live(table)
  expectLeft: test.assertEqualInt64(ninetyNine=99, left)
  readTenth: tenth = keyNumber(table, ten)
  expectTenth: test.assertEqualInt64(seventySeven=77, tenth)
  readNinth: ninth = keyNumber(table, nine=9)
  expectNinth: test.assertEqualInt64(sixtyThree=63, ninth)
  putBack: backRow = putNumber(table, seventy)
  expectBackLast: test.assertEqualInt64(ninetyNine, backRow)
  readLast: last = keyNumber(table, ninetyNine)
  expectLast: test.assertEqualInt64(seventy, last)
  findFourteen: fourteenRow = findNumber(table, fourteen)
  expectFourteen: test.assertEqualInt64(two, fourteenRow)
  findKey: key = machine.offset(state, keyScratch=61568)
  storeKey: machine.storeInt64(key, fiveHundred=500)
  hashOf: hash = hashKey(table, key)
  findNone: noRow = find(table, key, hash)
  expectNone: test.assertEqualInt64(minusOne, noRow)
  addRow: rowAt = insert(table, key, hash)
  findAdded: addedRow = find(table, key, hash)
  expectAdded: test.assertEqualInt64(hundred, addedRow)
  findRowAt: sameAt = rowAddress(table, addedRow)
  sameCheck: sameRow = machine.equal(rowAt, sameAt)
  expectSameRow: test.assertTrue(sameRow)
  findFirstKey: firstKey = keyAt(table, zero)
  readFirstKey: firstNumber = machine.loadInt64(firstKey)
  expectFirstKey: test.assertEqualInt64(zero, firstNumber)
  free: release(table)
  countFreed: freed = live(table)
  expectFreed: test.assertEqualInt64(zero, freed)
  return

test textTableTest "Text keys are found by their bytes, wherever the text is"
  verifies hashKey hashesContent
  verifies find findsLive
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let first String "alpha"
  let again String "xalpha"
:begin
  findState: state = machine.state()
  findTable: table = machine.offset(state, tableAt=61440)
  clearTable: machine.fill(table, zeroByte=0, tableBytes)
  start: prepare(table, one=1, two=2, zero=0)
  findKey: key = machine.offset(state, keyScratch=61568)
  findText: textAt = machine.addressOfString(first)
  storeText: machine.storeAddress(key, textAt)
  findLength: lengthSlot = machine.offset(key, eight=8)
  storeLength: machine.storeInt64(lengthSlot, five=5)
  hashOf: hash = hashKey(table, key)
  addRow: rowAt = insert(table, key, hash)
  findOther: otherKey = machine.offset(state, otherAt=61584)
  findAgain: againAt = machine.addressOfString(again)
  findInside: insideAt = machine.offset(againAt, one)
  storeOther: machine.storeAddress(otherKey, insideAt)
  findOtherLength: otherLengthSlot = machine.offset(otherKey, eight)
  storeOtherLength: machine.storeInt64(otherLengthSlot, five)
  hashOther: otherHash = hashKey(table, otherKey)
  findOtherRow: row = find(table, otherKey, otherHash)
  expectFound: test.assertEqualInt64(zero, row)
  storeShort: machine.storeInt64(otherLengthSlot, four=4)
  hashShort: shortHash = hashKey(table, otherKey)
  findShort: shortRow = find(table, otherKey, shortHash)
  expectShortMissing: test.assertEqualInt64(minusOne=-1, shortRow)
  free: release(table)
  return
