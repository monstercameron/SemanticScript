module handles "Handles: the small numbers a program holds for the host's objects, the region that owns each, and what is given back when an object is closed or its region released"
  path handles
  imports standard.machine standard.system standard.string standard.math standard.compare standard.convert standard.logic standard.test frames heap tables values
  exports newHandle objectOf kindOf regionOf drop dropRegion addName nameAt nameCount

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
## its table at 0; a Listing or an Arguments list, a list of names: at 0 how many, 8 how many its block holds, 16 the
## block, two slots a name (the address of a heap block holding its bytes, and how many); a Channel, at 56 the block
## of its items (the rest is the tasks module's); a Secret, at 0 its bytes (a heap block) and 8 how many; a
## Generator, a heap block of its own; a Library, nothing to give back (the library stays loaded).
constant tableAt "Where the address of the table of handles is kept, in machine.state" Int64 256

constant capacityAt "Where the number of entries the table holds is kept, in machine.state" Int64 264

constant nextAt "Where the next handle is kept, in machine.state" Int64 272

constant entryBytes "The bytes of an entry of the table of handles" Int64 24

constant kindBuffer "The kind of a byte buffer" Int64 3

constant kindMap "The kind of a map" Int64 4

constant kindSet "The kind of a set" Int64 5

constant kindListing "The kind of a directory's listing" Int64 2

constant kindArguments "The kind of a child process's list of arguments" Int64 6

constant kindChannel "The kind of a channel" Int64 7

constant kindSecret "The kind of a secret" Int64 8

constant kindGenerator "The kind of a random number generator" Int64 9

constant kindLibrary "The kind of a foreign library" Int64 10

constant kindJson "The kind of a JSON value (values)" Int64 11

constant kindResponse "The kind of an HTTP response: a heap block, at 0 its status, 8 its body (a heap block), 16 how many bytes" Int64 12

constant kindListener "The kind of a TCP listener: a heap block of the sockets module's" Int64 13

constant kindConnection "The kind of a TCP connection: a heap block of the sockets module's" Int64 14

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
  exit: endProcess(trapCode=70)
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
  if isArguments staleArguments channelCheck
:staleArguments
  failArguments: failText(argumentsText="a Arguments handle was used after it was closed or its region was released")
  return
:channelCheck
  checkChannel: isChannel = compare.equalInt64(kind, kindChannel)
  if isChannel staleChannel secretCheck
:staleChannel
  failChannel: failText(channelText="a Channel handle was used after it was closed or its region was released")
  return
:secretCheck
  checkSecret: isSecret = compare.equalInt64(kind, kindSecret)
  if isSecret staleSecret generatorCheck
:staleSecret
  failSecret: failText(secretText="a Secret handle was used after it was closed or its region was released")
  return
:generatorCheck
  checkGenerator: isGenerator = compare.equalInt64(kind, kindGenerator)
  if isGenerator staleGenerator libraryCheck
:staleGenerator
  failGenerator: failText(generatorText="a Generator handle was used after it was closed or its region was released")
  return
:libraryCheck
  checkLibrary: isLibrary = compare.equalInt64(kind, kindLibrary)
  if isLibrary staleLibrary jsonCheck
:staleLibrary
  failLibrary: failText(libraryText="a Library handle was used after it was closed or its region was released")
  return
:jsonCheck
  checkJson: isJson = compare.equalInt64(kind, kindJson)
  if isJson staleJson responseCheck
:staleJson
  failJson: failText(jsonText="a Json handle was used after it was closed or its region was released")
  return
:responseCheck
  checkResponse: isResponse = compare.equalInt64(kind, kindResponse)
  if isResponse staleResponse listenerCheck
:staleResponse
  failResponse: failText(responseText="a Response handle was used after it was closed or its region was released")
  return
:listenerCheck
  checkListener: isListener = compare.equalInt64(kind, kindListener)
  if isListener staleListener connectionCheck
:staleListener
  failListener: failText(listenerText="a Listener handle was used after it was closed or its region was released")
  return
:connectionCheck
  checkConnection: isConnection = compare.equalInt64(kind, kindConnection)
  if isConnection staleConnection staleOther
:staleConnection
  failConnection: failText(connectionText="a Connection handle was used after it was closed or its region was released")
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

op dropNames "Give back a list of names: each name's bytes, the block of names, and the list itself"
  input object machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  readCount: count = machine.loadInt64(object)
  findBlock: blockSlot = machine.offset(object, sixteen=16)
  readBlock: block = machine.loadAddress(blockSlot)
  goto eachName
:eachName loop=while max=count
  namesDone: done = compare.greaterOrEqualInt64(at, count)
  if done finish giveName
:giveName in=eachName
  nameOffset: offset = math.multiplyInt64(at, sixteen)
  findName: nameSlot = machine.offset(block, offset)
  readName: name = machine.loadAddress(nameSlot)
  giveIt: heap.give(name)
  nextName: after = math.addInt64(at, one=1)
  set at after
  goto eachName
:finish
  giveBlock: heap.give(block)
  giveObject: heap.give(object)
  return

## ---------------------------------------------------------------- lists of names (listings, arguments)

op addName "Add a copy of some bytes to the end of a list of names, doubling its block (from 8 names) when it is full"
  invariant addsName "The list holds one name more, the last a copy of the bytes"
  input names machine.Address copied
  input data machine.Address copied
  input bytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let capacity Int64 0 mut
:begin
  readCount: count = machine.loadInt64(names)
  findCapacity: capacitySlot = machine.offset(names, eight=8)
  readCapacity: held = machine.loadInt64(capacitySlot)
  findBlock: blockSlot = machine.offset(names, sixteen=16)
  roomCheck: room = compare.lessThanInt64(count, held)
  if room append grow
:grow
  twice: doubled = math.multiplyInt64(held, two=2)
  more: grown = math.addInt64(doubled, eight)
  set capacity grown
  readOld: old = machine.loadAddress(blockSlot)
  sizeOf: size = math.multiplyInt64(capacity, sixteen)
  resizeBlock: block = heap.resize(old, size)
  storeBlock: machine.storeAddress(blockSlot, block)
  storeCapacity: machine.storeInt64(capacitySlot, capacity)
  goto append
:append
  takeCopy: copy = heap.take(bytes)
  copyIn: machine.copy(copy, data, bytes)
  readBlockNow: blockNow = machine.loadAddress(blockSlot)
  nameOffset: offset = math.multiplyInt64(count, sixteen)
  findName: nameSlot = machine.offset(blockNow, offset)
  storeName: machine.storeAddress(nameSlot, copy)
  findLength: lengthSlot = machine.offset(nameSlot, eight)
  storeLength: machine.storeInt64(lengthSlot, bytes)
  addOne: nextCount = math.addInt64(count, one=1)
  storeCount: machine.storeInt64(names, nextCount)
  return

op nameCount "How many names a list holds"
  invariant countsNames "Gives how many names were added to the list"
  input names machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  readCount: count = machine.loadInt64(names)
  return count

op nameAt "The address of a name of a list by its position: two slots, the address of its bytes and how many"
  invariant findsName "Gives the slots of the name added at that position"
  input names machine.Address copied
  input position Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findBlock: blockSlot = machine.offset(names, sixteen=16)
  readBlock: block = machine.loadAddress(blockSlot)
  nameOffset: offset = math.multiplyInt64(position, sixteen)
  findName: nameSlot = machine.offset(block, offset)
  return nameSlot

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
  if isSet giveSet listingCheck
:giveSet
  releaseSet: tables.release(object)
  giveSetObject: heap.give(object)
  goto close
:listingCheck
  checkListing: isListing = compare.equalInt64(kind, kindListing)
  checkArguments: isArguments = compare.equalInt64(kind, kindArguments)
  namesCheck: isNames = logic.or(isListing, isArguments)
  if isNames giveNames channelCheck
:giveNames
  dropNamesIt: dropNames(object)
  goto close
:channelCheck
  checkChannel: isChannel = compare.equalInt64(kind, kindChannel)
  if isChannel giveChannel secretCheck
:giveChannel
  findItems: itemsSlot = machine.offset(object, fiftySix=56)
  readItems: items = machine.loadAddress(itemsSlot)
  giveItems: heap.give(items)
  giveChannelObject: heap.give(object)
  goto close
:secretCheck
  checkSecret: isSecret = compare.equalInt64(kind, kindSecret)
  if isSecret giveSecret generatorCheck
:giveSecret
  readSecretBytes: secretBytes = machine.loadAddress(object)
  giveSecretBytes: heap.give(secretBytes)
  giveSecretObject: heap.give(object)
  goto close
:generatorCheck
  checkGenerator: isGenerator = compare.equalInt64(kind, kindGenerator)
  checkListener: isListener = compare.equalInt64(kind, kindListener)
  checkConnection: isConnection = compare.equalInt64(kind, kindConnection)
  socketCheck: isSocket = logic.or(isListener, isConnection)
  plainCheck: isPlain = logic.or(isGenerator, isSocket)
  if isPlain giveGenerator jsonCheck
:giveGenerator
  giveGeneratorObject: heap.give(object)
  goto close
:jsonCheck
  checkJson: isJson = compare.equalInt64(kind, kindJson)
  if isJson giveJson responseCheck
:giveJson
  releaseJson: freed = values.release(object)
  goto close
:responseCheck
  checkResponse: isResponse = compare.equalInt64(kind, kindResponse)
  if isResponse giveResponse close
:giveResponse
  findBody: bodySlot = machine.offset(object, eight)
  readBody: body = machine.loadAddress(bodySlot)
  giveBody: heap.give(body)
  giveResponseObject: heap.give(object)
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

test namesTest "A list of names keeps copies of the names added, in order, and is given back with its region"
  verifies addName addsName
  verifies nameCount countsNames
  verifies nameAt findsName
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let first String "first"
  let second String "second name"
:begin
  findState: state = machine.state()
  findRegion: region = machine.offset(state, regionAt=61440)
  clearRegion: machine.fill(region, zeroByte=0, sixtyFour=64)
  takeNames: names = heap.take(twentyFour=24)
  makeNames: handle = newHandle(kindListing, names, region)
  findFirst: firstAt = machine.addressOfString(first)
  addFirst: addName(names, firstAt, five=5)
  findSecond: secondAt = machine.addressOfString(second)
  addSecond: addName(names, secondAt, eleven=11)
  readCount: count = nameCount(names)
  expectCount: test.assertEqualInt64(two=2, count)
  findName: nameSlot = nameAt(names, one=1)
  readName: name = machine.loadAddress(nameSlot)
  findLength: lengthSlot = machine.offset(nameSlot, eight=8)
  readLength: length = machine.loadInt64(lengthSlot)
  expectLength: test.assertEqualInt64(eleven, length)
  compareName: order = machine.compare(name, secondAt, eleven)
  orderWide: orderValue = convert.int32ToInt64(order)
  expectName: test.assertEqualInt64(zero=0, orderValue)
  copyCheck: copied = machine.equal(name, secondAt)
  notSame: notCopied = logic.not(copied)
  expectCopied: test.assertTrue(notCopied)
  release: dropRegion(region)
  readDropped: droppedKind = kindOf(handle)
  expectDropped: test.assertEqualInt64(zero, droppedKind)
  return
