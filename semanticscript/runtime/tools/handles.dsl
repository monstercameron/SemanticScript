module handles "Handles: the small numbers a program holds for the host's objects, the region that owns each, and what is given back when an object is closed or its region released"
  path handles
  imports standard.machine standard.system standard.string standard.math standard.compare standard.logic standard.test frames heap tables
  exports newHandle objectOf kindOf regionOf drop dropRegion

capability memoryAccess "Authority to keep the table of handles and each region's list of them in memory" use machine.memory none

capability systemCalls "Authority to take memory for the handles and give their objects back, and to end the process on a trap" use system.calls none

## As in host.py and the C runtime: handles are numbered from 1 into one table and never reused, so a handle used
## after it was closed, or after the region that owns it was released, is caught and traps naming its kind.
## machine.state bytes 256 to 319 belong to this module: 256 the address of the table, 264 how many entries it
## holds, 272 the next handle (0 before the first). An entry is 24 bytes: at 0 its kind (0 when closed), 8 the
## address of its object, 16 the region that owns it (0 for none).
## A region's header (regions) keeps its handles at 48, the address of a list (at 0 how many it holds, then the
## handles), and at 56 how many are on it.
## The objects (heap blocks): a Buffer, at 0 its bytes, 8 how many, 16 how many the block holds, 24 a list of the
## copies `toBytes` handed out, 32 how many, 40 how many the list holds; a Map, at 0 its region, 8 whether its
## values are text, 16 its table of keys and values, 104 its table of the text keys copied into its region; a Set,
## its table at 0.
constant tableAt "Where the address of the table of handles is kept, in machine.state" Int64 256

constant capacityAt "Where the number of entries the table holds is kept, in machine.state" Int64 264

constant nextAt "Where the next handle is kept, in machine.state" Int64 272

constant entryBytes "The bytes of an entry of the table of handles" Int64 24

constant kindBuffer "The kind of a byte buffer" Int64 3

constant kindMap "The kind of a map" Int64 4

constant kindSet "The kind of a set" Int64 5

## ---------------------------------------------------------------- the table

op nextHandle "The number the next handle gets: 1 before any was made"
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  findNext: nextSlot = machine.offset(state, nextAt)
  readNext: next = machine.loadInt64(nextSlot)
  firstCheck: first = compare.lessThanInt64(next, one=1)
  if first giveOne giveNext
:giveOne
  return one
:giveNext
  return next

op entryOf "The address of a handle's entry in the table, or the address 0 for a number that never was a handle"
  input handle Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  nowhere: anywhere = machine.zero()
  readNext: next = nextHandle()
  lowCheck: low = compare.lessThanInt64(handle, one=1)
  highCheck: high = compare.greaterOrEqualInt64(handle, next)
  outsideCheck: outside = logic.or(low, high)
  if outside outsideTable found
:outsideTable
  return anywhere
:found
  findState: state = machine.state()
  findTable: tableSlot = machine.offset(state, tableAt)
  readTable: table = machine.loadAddress(tableSlot)
  entryOffset: offset = math.multiplyInt64(handle, entryBytes)
  findEntry: entry = machine.offset(table, offset)
  return entry

op failText "Report a trap with a message and end the process with exit code 70"
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

op failStale "Trap because a handle of a kind was used after it was closed or its region was released, naming the kind"
  input kind Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  fileCheck: isFile = compare.equalInt64(kind, one=1)
  if isFile staleFile listingCheck
:staleFile
  failFile: failText(fileText="a File handle was used after it was closed or its region was released")
  return
:listingCheck
  checkListing: isListing = compare.equalInt64(kind, two=2)
  if isListing staleListing bufferCheck
:staleListing
  failListing: failText(listingText="a Listing handle was used after it was closed or its region was released")
  return
:bufferCheck
  checkBuffer: isBuffer = compare.equalInt64(kind, kindBuffer)
  if isBuffer staleBuffer mapCheck
:staleBuffer
  failBuffer: failText(bufferText="a Buffer handle was used after it was closed or its region was released")
  return
:mapCheck
  checkMap: isMap = compare.equalInt64(kind, kindMap)
  if isMap staleMap setCheck
:staleMap
  failMap: failText(mapText="a Map handle was used after it was closed or its region was released")
  return
:setCheck
  checkSet: isSet = compare.equalInt64(kind, kindSet)
  if isSet staleSet argumentsCheck
:staleSet
  failSet: failText(setText="a Set handle was used after it was closed or its region was released")
  return
:argumentsCheck
  checkArguments: isArguments = compare.equalInt64(kind, six=6)
  if isArguments staleArguments staleOther
:staleArguments
  failArguments: failText(argumentsText="a Arguments handle was used after it was closed or its region was released")
  return
:staleOther
  failOther: failText(otherText="a  handle was used after it was closed or its region was released")
  return

op newHandle "A new handle for an object of a kind, owned by a region (or by none, the address 0), which lists it to give it back when it is released"
  invariant numbersHandles "Handles are numbered 1, 2, 3, ... in the order they are made; each names its object and kind until it is dropped, and its region lists it"
  input kind Int64 copied
  input object machine.Address copied
  input region machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let capacity Int64 0 mut
  let listCapacity Int64 0 mut
  let zero Int64 0
  let sixtyFour Int64 64
:begin
  handleOf: handle = nextHandle()
  afterHandle: next = math.addInt64(handle, one=1)
  findState: state = machine.state()
  findNext: nextSlot = machine.offset(state, nextAt)
  storeNext: machine.storeInt64(nextSlot, next)
  findCapacity: capacitySlot = machine.offset(state, capacityAt)
  readCapacity: held = machine.loadInt64(capacitySlot)
  findTable: tableSlot = machine.offset(state, tableAt)
  roomCheck: room = compare.lessThanInt64(handle, held)
  if room record growTable
:growTable
  set capacity held
  emptyCheck: empty = compare.lessThanInt64(held, eight=8)
  if empty startTable eachDouble
:startTable
  set capacity eight
  goto eachDouble
:eachDouble loop=while max=sixtyFour
  smallCheck: small = compare.lessOrEqualInt64(capacity, handle)
  if small doubleTable resizeTable
:doubleTable in=eachDouble
  doubled: twice = math.multiplyInt64(capacity, two=2)
  set capacity twice
  goto eachDouble
:resizeTable
  readTable: oldTable = machine.loadAddress(tableSlot)
  tableBytes: newBytes = math.multiplyInt64(capacity, entryBytes)
  growBlock: grown = heap.resize(oldTable, newBytes)
  storeTable: machine.storeAddress(tableSlot, grown)
  storeCapacity: machine.storeInt64(capacitySlot, capacity)
  goto record
:record
  findEntry: entry = entryOf(handle)
  storeKind: machine.storeInt64(entry, kind)
  findObject: objectSlot = machine.offset(entry, eight)
  storeObject: machine.storeAddress(objectSlot, object)
  findRegion: regionSlot = machine.offset(entry, sixteen=16)
  storeRegion: machine.storeAddress(regionSlot, region)
  nowhere: anywhere = machine.zero()
  ownedCheck: unowned = machine.equal(region, anywhere)
  if unowned done list
:list
  findList: listSlot = machine.offset(region, fortyEight=48)
  readList: oldList = machine.loadAddress(listSlot)
  findCount: countSlot = machine.offset(region, fiftySix=56)
  readCount: count = machine.loadInt64(countSlot)
  listCheck: noList = machine.equal(oldList, anywhere)
  if noList startList readListCapacity
:startList
  set listCapacity zero
  goto listRoom
:readListCapacity
  readHeld: listHeld = machine.loadInt64(oldList)
  set listCapacity listHeld
  goto listRoom
:listRoom
  listRoomCheck: listFits = compare.lessThanInt64(count, listCapacity)
  if listFits append growList
:growList
  doubleList: doubledList = math.multiplyInt64(listCapacity, two)
  moreList: grownCapacity = math.addInt64(doubledList, eight)
  set listCapacity grownCapacity
  slotsOf: listSlots = math.addInt64(grownCapacity, one)
  listBytes: listByteCount = math.multiplyInt64(listSlots, eight)
  growListBlock: grownList = heap.resize(oldList, listByteCount)
  storeListCapacity: machine.storeInt64(grownList, grownCapacity)
  storeList: machine.storeAddress(listSlot, grownList)
  goto append
:append
  readListNow: listNow = machine.loadAddress(listSlot)
  slotOf: slot = math.addInt64(count, one)
  slotBytes: slotOffset = math.multiplyInt64(slot, eight)
  findSlot: slotAt = machine.offset(listNow, slotOffset)
  storeHandle: machine.storeInt64(slotAt, handle)
  countMore: moreCount = math.addInt64(count, one)
  storeCount: machine.storeInt64(countSlot, moreCount)
  goto done
:done
  return handle

op kindOf "The kind of the object a handle names, or 0 when it was dropped or never was a handle"
  invariant knowsKind "A handle's kind is the kind it was made with until it is dropped, then 0; any other number is 0"
  input handle Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let zero Int64 0
:begin
  findEntry: entry = entryOf(handle)
  nowhere: anywhere = machine.zero()
  noneCheck: missingEntry = machine.equal(entry, anywhere)
  if missingEntry giveNone readKind
:giveNone
  return zero
:readKind
  readEntryKind: kind = machine.loadInt64(entry)
  return kind

op objectOf "The object a handle of a kind names; a handle that was closed, whose region was released, or of another kind traps"
  invariant givesObject "A live handle of the kind gives the object it was made with"
  input handle Int64 copied
  input kind Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readKind: actual = kindOf(handle)
  kindCheck: same = compare.equalInt64(actual, kind)
  if same give stale
:give
  findEntry: entry = entryOf(handle)
  findObject: objectSlot = machine.offset(entry, eight=8)
  readObject: object = machine.loadAddress(objectSlot)
  return object
:stale
  failHere: failStale(kind)
  nowhere: anywhere = machine.zero()
  return anywhere

## ---------------------------------------------------------------- the region a value is stored in

op regionOf "D-107: the region a host value lives in, where text stored in it is copied; a handle with no region traps: refined_handle_region"
  invariant givesRegion "A live handle made with a region gives that region"
  input handle Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_handle_region"
  let message String "a value was stored in a collection that is not in any region"
:begin
  readKind: kind = kindOf(handle)
  closedCheck: closed = compare.equalInt64(kind, zero=0)
  if closed stray readRegion
:readRegion
  findEntry: entry = entryOf(handle)
  findRegion: regionSlot = machine.offset(entry, sixteen=16)
  readOwner: region = machine.loadAddress(regionSlot)
  nowhere: anywhere = machine.zero()
  unownedCheck: unowned = machine.equal(region, anywhere)
  if unowned stray give
:give
  return region
:stray
  failHere: failText(message)
  nothing: noRegion = machine.zero()
  return noRegion

## ---------------------------------------------------------------- giving objects back

op dropBuffer "Give back a buffer's bytes, every copy `toBytes` handed out, and the buffer itself"
  input object machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  readData: data = machine.loadAddress(object)
  giveData: heap.give(data)
  findKept: keptSlot = machine.offset(object, twentyFour=24)
  readKept: kept = machine.loadAddress(keptSlot)
  findKeptCount: keptCountSlot = machine.offset(object, thirtyTwo=32)
  readKeptCount: keptCount = machine.loadInt64(keptCountSlot)
  goto eachCopy
:eachCopy loop=while max=keptCount
  copiesDone: done = compare.greaterOrEqualInt64(at, keptCount)
  if done finish giveCopy
:giveCopy in=eachCopy
  copyOffset: offset = math.multiplyInt64(at, eight=8)
  findCopy: copySlot = machine.offset(kept, offset)
  readCopy: copy = machine.loadAddress(copySlot)
  giveIt: heap.give(copy)
  nextCopy: after = math.addInt64(at, one=1)
  set at after
  goto eachCopy
:finish
  giveKept: heap.give(kept)
  giveObject: heap.give(object)
  return

op drop "Give back the object a handle names and mark the handle closed; a closed handle or another number is left as it is"
  invariant closesHandle "After a drop the handle's kind is 0 and its object has been given back"
  input handle Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readKind: kind = kindOf(handle)
  closedCheck: closed = compare.equalInt64(kind, zero=0)
  if closed done readObject
:readObject
  findEntry: entry = entryOf(handle)
  findObject: objectSlot = machine.offset(entry, eight=8)
  readEntryObject: object = machine.loadAddress(objectSlot)
  bufferCheck: isBuffer = compare.equalInt64(kind, kindBuffer)
  if isBuffer giveBuffer mapCheck
:giveBuffer
  dropIt: dropBuffer(object)
  goto close
:mapCheck
  checkMap: isMap = compare.equalInt64(kind, kindMap)
  if isMap giveMap setCheck
:giveMap
  findTable: mapTable = machine.offset(object, sixteen=16)
  releaseTable: tables.release(mapTable)
  findCopies: copiesTable = machine.offset(object, hundredFour=104)
  releaseCopies: tables.release(copiesTable)
  giveMapObject: heap.give(object)
  goto close
:setCheck
  checkSet: isSet = compare.equalInt64(kind, kindSet)
  if isSet giveSet close
:giveSet
  releaseSet: tables.release(object)
  giveSetObject: heap.give(object)
  goto close
:close
  clearKind: machine.storeInt64(entry, zero)
  nowhere: anywhere = machine.zero()
  clearObject: machine.storeAddress(objectSlot, anywhere)
  goto done
:done
  return

op dropRegion "Drop every handle a region owns, as it is released, and give back its list of them"
  invariant dropsOwned "Every handle made with the region is closed after it is released"
  input region machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  findList: listSlot = machine.offset(region, fortyEight=48)
  readList: list = machine.loadAddress(listSlot)
  findCount: countSlot = machine.offset(region, fiftySix=56)
  readCount: count = machine.loadInt64(countSlot)
  goto eachHandle
:eachHandle loop=while max=count
  handlesDone: done = compare.greaterOrEqualInt64(at, count)
  if done finish dropOne
:dropOne in=eachHandle
  slotOf: slot = math.addInt64(at, one=1)
  slotBytes: offset = math.multiplyInt64(slot, eight=8)
  findSlot: slotAt = machine.offset(list, offset)
  readHandle: handle = machine.loadInt64(slotAt)
  dropIt: drop(handle)
  set at slot
  goto eachHandle
:finish
  giveList: heap.give(list)
  nowhere: anywhere = machine.zero()
  clearList: machine.storeAddress(listSlot, anywhere)
  clearCount: machine.storeInt64(countSlot, zero=0)
  return

@tests

## Tests keep a region's header in the last 4 KiB of machine.state (from byte 61440), which the runtime's own state
## never reaches.

test handleTest "Handles are numbered in order, name their objects and kinds, are listed by their region, and are closed when it is released"
  verifies newHandle numbersHandles
  verifies kindOf knowsKind
  verifies objectOf givesObject
  verifies drop closesHandle
  verifies dropRegion dropsOwned
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findState: state = machine.state()
  findRegion: region = machine.offset(state, regionAt=61440)
  clearRegion: machine.fill(region, zeroByte=0, sixtyFour=64)
  takeBuffer: buffer = heap.take(fortyEight=48)
  makeBuffer: bufferHandle = newHandle(kindBuffer, buffer, region)
  takeSet: setObject = heap.take(tableBytes=88)
  prepareSet: tables.prepare(setObject, zero=0, minusOne=-1, zero)
  nowhere: anywhere = machine.zero()
  makeSet: setHandle = newHandle(kindSet, setObject, anywhere)
  nextOf: expectedSet = math.addInt64(bufferHandle, one=1)
  expectNumbered: test.assertEqualInt64(expectedSet, setHandle)
  readBufferKind: bufferKind = kindOf(bufferHandle)
  expectBufferKind: test.assertEqualInt64(kindBuffer, bufferKind)
  readObject: object = objectOf(setHandle, kindSet)
  sameCheck: same = machine.equal(object, setObject)
  expectObject: test.assertTrue(same)
  findCount: countSlot = machine.offset(region, fiftySix=56)
  readCount: count = machine.loadInt64(countSlot)
  expectListed: test.assertEqualInt64(one, count)
  release: dropRegion(region)
  readDropped: droppedKind = kindOf(bufferHandle)
  expectDropped: test.assertEqualInt64(zero, droppedKind)
  readKept: keptKind = kindOf(setHandle)
  expectKept: test.assertEqualInt64(kindSet, keptKind)
  dropSet: drop(setHandle)
  readClosed: closedKind = kindOf(setHandle)
  expectClosed: test.assertEqualInt64(zero, closedKind)
  dropAgain: drop(setHandle)
  readNever: neverKind = kindOf(minusOne)
  expectNever: test.assertEqualInt64(zero, neverKind)
  return

test regionOfTest "A handle made with a region gives it back as the place its stored text goes"
  verifies regionOf givesRegion
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findState: state = machine.state()
  findRegion: region = machine.offset(state, regionAt=61440)
  clearRegion: machine.fill(region, zeroByte=0, sixtyFour=64)
  takeBuffer: buffer = heap.take(fortyEight=48)
  makeBuffer: bufferHandle = newHandle(kindBuffer, buffer, region)
  readOwner: owner = regionOf(bufferHandle)
  sameCheck: same = machine.equal(owner, region)
  expectOwner: test.assertTrue(same)
  release: dropRegion(region)
  return
