module host "The host library of a standalone executable: refined_host and its targets (byte buffers, maps, sets, string.fromBytes, log lines)"
  path host
  imports standard.machine standard.system standard.string standard.math standard.compare standard.convert standard.bits standard.logic standard.list standard.test memory numbers output frames heap tables handles regions slots tasks files processes hashes generators requests documents
  exports hostCall utf8InvalidAt

capability memoryAccess "Authority to read a host call's slots and keep the host's objects and call shapes in memory" use machine.memory none

capability systemCalls "Authority to take memory for the host's objects, write log lines, and end the process on a trap" use system.calls none

## Compiled code calls every host target through refined_host with a key `<target>|<slots per parameter>|<result
## slots>`, its arguments' 64-bit slots, room for the result's slots, and a slot for an error's payload (codegen's
## host_call). The key is a constant of the program, so its address names it: its shape (the target's number in
## hostTargets, how many slots each parameter takes and where they start, how many result slots) is worked out once
## and kept by that address. A target gives 0, or an error's variant numbered from 1 with its payload stored.
## machine.state bytes 320 to 383 belong to this module: 320 the address of the table of shapes, 328 how many
## entries it has (a power of two, 0 before the first), 336 how many are taken, 344 to 359 a text key's copy, 360 a
## byte being appended, 368 to 383 unused; bytes 7936 to 8191 the digits of a number being appended.
## A shape is a heap block of shapeBytes: at 0 the key's address, 8 its length, 16 the target's number, 24 how many
## parameters, 32 how many result slots, from 40 each parameter's slot count, from 232 each parameter's first slot.
constant shapesAt "Where the address of the table of shapes is kept, in machine.state" Int64 320

constant shapesCapacityAt "Where the number of entries of the table of shapes is kept, in machine.state" Int64 328

constant shapesCountAt "Where the number of shapes kept is kept, in machine.state" Int64 336

constant keyCopyAt "Where a text key's copy in a collection's region is put together, in machine.state" Int64 344

constant byteAt "Where a byte being appended to a buffer is put, in machine.state" Int64 360

constant digitsAt "Where the digits of a number being appended to a buffer are put, in machine.state" Int64 7936

constant shapeBytes "The bytes of a shape" Int64 424

constant mostParameters "How many parameters a host call may have" Int64 24

constant kindBuffer "The kind of a byte buffer's handle" Int64 3

constant kindMap "The kind of a map's handle" Int64 4

constant kindSet "The kind of a set's handle" Int64 5

constant utf8Invalid "string.Utf8Error.invalidAt, numbered from 1" Int32 1

constant keyMissing "map.KeyMissing.missing, numbered from 1" Int32 1

constant logFailed "log.LogError.failed, numbered from 1" Int32 1

record HostTarget "A host target this runtime implements: its name, and the parameter a capability's scope limits (D-38), or -1"
  field name String
  field scoped Int64

## The host targets an executable linked with this runtime may call, numbered by their rows; native.py reads this
## table and refuses (R901) a program that calls any other. Keep one `row` per target.
table hostTargets "The host targets this runtime implements, numbered from 1" HostTarget
  row bufferAppendByte name="buffer.appendByte" scoped=-1
  row bufferAppendInt64 name="buffer.appendInt64" scoped=-1
  row bufferAppendString name="buffer.appendString" scoped=-1
  row bufferLength name="buffer.length" scoped=-1
  row bufferNew name="buffer.new" scoped=-1
  row bufferToBytes name="buffer.toBytes" scoped=-1
  row bufferToString name="buffer.toString" scoped=-1
  row logDebug name="log.debug" scoped=-1
  row logError name="log.error" scoped=-1
  row logInfo name="log.info" scoped=-1
  row logWarn name="log.warn" scoped=-1
  row mapContains name="map.Map.contains" scoped=-1
  row mapGet name="map.Map.get" scoped=-1
  row mapKeyAt name="map.Map.keyAt" scoped=-1
  row mapLength name="map.Map.length" scoped=-1
  row mapNew name="map.Map.new" scoped=-1
  row mapPut name="map.Map.put" scoped=-1
  row mapRemove name="map.Map.remove" scoped=-1
  row setAdd name="set.Set.add" scoped=-1
  row setContains name="set.Set.contains" scoped=-1
  row setItemAt name="set.Set.itemAt" scoped=-1
  row setLength name="set.Set.length" scoped=-1
  row setNew name="set.Set.new" scoped=-1
  row setRemove name="set.Set.remove" scoped=-1
  row stringFromBytes name="string.fromBytes" scoped=-1
  row deadlineNever name="time.Deadline.never" scoped=-1
  row deadlineAfter name="time.Deadline.after" scoped=-1
  row timeSleep name="time.sleep" scoped=-1
  row clockNow name="clock.now" scoped=-1
  row clockMonotonic name="clock.monotonic" scoped=-1
  row channelNew name="channel.Channel.new" scoped=-1
  row channelSend name="channel.Channel.send" scoped=-1
  row channelReceive name="channel.Channel.receive" scoped=-1
  row channelClose name="channel.Channel.close" scoped=-1
  row fsClose name="fs.close" scoped=-1
  row fsCreate name="fs.create" scoped=0
  row fsCreateDirectory name="fs.createDirectory" scoped=0
  row fsEntryCount name="fs.entryCount" scoped=-1
  row fsEntryName name="fs.entryName" scoped=-1
  row fsExists name="fs.exists" scoped=0
  row fsListDirectory name="fs.listDirectory" scoped=0
  row fsLock name="fs.lock" scoped=-1
  row fsOpenAppend name="fs.openAppend" scoped=0
  row fsOpenRead name="fs.openRead" scoped=0
  row fsOpenWrite name="fs.openWrite" scoped=0
  row fsRead name="fs.read" scoped=-1
  row fsReadAll name="fs.readAll" scoped=0
  row fsRemove name="fs.remove" scoped=0
  row fsRemoveDirectory name="fs.removeDirectory" scoped=0
  row fsUnlock name="fs.unlock" scoped=-1
  row fsWrite name="fs.write" scoped=-1
  row fsWriteAll name="fs.writeAll" scoped=0
  row consoleReadLine name="console.readLine" scoped=-1
  row environmentGet name="environment.get" scoped=-1
  row processAddArgument name="process.addArgument" scoped=-1
  row processArgument name="process.argument" scoped=-1
  row processArgumentCount name="process.argumentCount" scoped=-1
  row processNewArguments name="process.newArguments" scoped=-1
  row processRun name="process.run" scoped=0
  row processRunCaptured name="process.runCaptured" scoped=0
  row secretFromEnvironment name="secret.fromEnvironment" scoped=-1
  row secretFromText name="secret.fromText" scoped=-1
  row secretLength name="secret.length" scoped=-1
  row secretMatches name="secret.matches" scoped=-1
  row secretReveal name="secret.reveal" scoped=-1
  row cryptoConstantTimeEquals name="crypto.constantTimeEquals" scoped=-1
  row cryptoHmacSha256 name="crypto.hmacSha256" scoped=-1
  row cryptoSha256 name="crypto.sha256" scoped=-1
  row cryptoToHex name="crypto.toHex" scoped=-1
  row ffiBind name="ffi.Function.bind" scoped=1
  row ffiClose name="ffi.close" scoped=-1
  row ffiOpen name="ffi.open" scoped=0
  row randomInt64Between name="random.int64Between" scoped=-1
  row randomNewGenerator name="random.newGenerator" scoped=-1
  row randomNextInt64 name="random.nextInt64" scoped=-1
  row httpParseRequest name="http.parseRequest" scoped=-1
  row httpHeader name="http.header" scoped=-1
  row httpResponse name="http.response" scoped=-1
  row httpSerializeResponse name="http.serializeResponse" scoped=-1
  row jsonParse name="json.parse" scoped=-1
  row jsonKind name="json.kind" scoped=-1
  row jsonAsInt64 name="json.asInt64" scoped=-1
  row jsonAsBool name="json.asBool" scoped=-1
  row jsonAsText name="json.asText" scoped=-1
  row jsonLength name="json.length" scoped=-1
  row jsonItem name="json.item" scoped=-1
  row jsonField name="json.field" scoped=-1
  row jsonNewObject name="json.newObject" scoped=-1
  row jsonNewArray name="json.newArray" scoped=-1
  row jsonSetInt64 name="json.setInt64" scoped=-1
  row jsonSetText name="json.setText" scoped=-1
  row jsonSetBool name="json.setBool" scoped=-1
  row jsonSetValue name="json.setValue" scoped=-1
  row jsonAppendInt64 name="json.appendInt64" scoped=-1
  row jsonAppendText name="json.appendText" scoped=-1
  row jsonStringify name="json.stringify" scoped=-1

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

op failAt "Report a trap whose message is in a block of a length, and end the process with exit code 70"
  input message machine.Address copied
  input bytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  writeReport: status = frames.report(message, bytes)
  exit: endProcess(trapCode=70)
  return

op failPosition "Trap because a collection was read at a position outside it: `a <kind> was read at position <n> of <length>`"
  input lead String borrowed
  input position Int64 copied
  input length Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findState: state = machine.state()
  findLength: lengthAt = machine.offset(state, keyCopyAt)
  compose: message = heap.numbersMessage(lead, position, of=" of ", length, lengthAt)
  readLength: bytes = machine.loadInt64(lengthAt)
  report: failAt(message, bytes)
  return

## ---------------------------------------------------------------- shapes

op stateAt "The address of a byte of machine.state"
  input offset Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  findPlace: place = machine.offset(state, offset)
  return place

op readDigits "Read the run of ASCII digits of a key from a position as a whole number; stores the position after them at an address"
  input key machine.Address copied
  input bytes Int64 copied
  input start Int64 copied
  input endAt machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let value Int64 0 mut
:begin
  set at start
  goto eachDigit
:eachDigit loop=while max=bytes
  endCheck: atEnd = compare.greaterOrEqualInt64(at, bytes)
  if atEnd done readByte
:readByte in=eachDigit
  findByte: place = machine.offset(key, at)
  loadIt: byte = machine.loadByte(place)
  lowCheck: aboveLow = compare.greaterOrEqualByte(byte, zeroCharacter=48)
  highCheck: belowHigh = compare.lessOrEqualByte(byte, nineCharacter=57)
  digitCheck: digit = logic.and(aboveLow, belowHigh)
  if digit addDigit done
:addDigit in=eachDigit
  valueOf: digitByte = math.subtractByte(byte, zeroCharacter)
  widenDigit: digitValue = convert.byteToInt64(digitByte)
  shiftValue: shifted = math.multiplyInt64(value, ten=10)
  addValue: grown = math.addInt64(shifted, digitValue)
  set value grown
  advance: after = math.addInt64(at, one=1)
  set at after
  goto eachDigit
:done
  storeEnd: machine.storeInt64(endAt, at)
  return value

op targetNumber "The number of the host target a key names (its name is the key up to its first `|`), or 0 when this runtime does not implement it"
  invariant findsTarget "Gives the row of hostTargets whose name is the key's first part, or 0 for a name no row has"
  input key machine.Address copied
  input nameBytes Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 1 mut
  let notFound Int64 0
:begin
  countTargets: total = hostTargets.length()
  goto eachTarget
:eachTarget loop=while max=total
  doneCheck: done = compare.greaterThanInt64(at, total)
  if done missing readTarget
:readTarget in=eachTarget
  readRow: row = hostTargets.rowAt(at) ? missing
  readName: name = HostTarget.name(row)
  findName: nameAt = machine.addressOfString(name)
  nameLength: length = string.byteLength(name)
  compareName: same = memory.bytesEqual(nameAt, length, key, nameBytes)
  sameCheck: found = compare.notEqualInt32(same, zero32=0)
  if found give nextTarget
:nextTarget in=eachTarget
  advance: after = math.addInt64(at, one=1)
  set at after
  goto eachTarget
:give
  return at
:missing
  return notFound

op parseShape "Work out a key's shape in a new block: its target's number, each parameter's slots and where they start, and the result's slots; a target this runtime does not implement traps"
  invariant readsKey "A key `<target>|<n1>,<n2>,...|<r>` gives the target's number, the parameters' slot counts n1, n2, ... starting at 0, n1, n1 + n2, ..., and r result slots"
  input key machine.Address copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let bar Int64 0 mut
  let at Int64 0 mut
  let params Int64 0 mut
  let offset Int64 0 mut
  let barByte Byte 124
  let commaByte Byte 44
:begin
  goto eachByte
:eachByte loop=while max=bytes
  endCheck: atEnd = compare.greaterOrEqualInt64(bar, bytes)
  if atEnd named checkBar
:checkBar in=eachByte
  findByte: place = machine.offset(key, bar)
  loadIt: byte = machine.loadByte(place)
  barCheck: isBar = compare.equalByte(byte, barByte)
  if isBar named nextByte
:nextByte in=eachByte
  advance: after = math.addInt64(bar, one=1)
  set bar after
  goto eachByte
:named
  findTarget: number = targetNumber(key, bar)
  knownCheck: unknown = compare.equalInt64(number, zero=0)
  if unknown notHere makeShape
:notHere
  compose: message = heap.joinMessage(quote="`", key, bar, tail="` needs the host library, which standalone executables do not include; run this program with `refined run`")
  tailLength: tailBytes = string.byteLength(tail)
  headLength: headBytes = math.addInt64(bar, one)
  totalLength: messageBytes = math.addInt64(headBytes, tailBytes)
  report: failAt(message, messageBytes)
  nowhere: anywhere = machine.zero()
  return anywhere
:makeShape
  takeShape: shape = heap.take(shapeBytes)
  storeKey: machine.storeAddress(shape, key)
  findKeyLength: keyLengthSlot = machine.offset(shape, eight=8)
  storeKeyLength: machine.storeInt64(keyLengthSlot, bytes)
  findNumber: numberSlot = machine.offset(shape, sixteen=16)
  storeNumber: machine.storeInt64(numberSlot, number)
  afterBar: first = math.addInt64(bar, one)
  set at first
  findEnd: endAt = stateAt(keyCopyAt)
  goto eachParameter
:eachParameter loop=while max=bytes
  paramsEnd: endOfKey = compare.greaterOrEqualInt64(at, bytes)
  if endOfKey results checkParameter
:checkParameter in=eachParameter
  findParameter: parameterPlace = machine.offset(key, at)
  loadParameter: parameterByte = machine.loadByte(parameterPlace)
  resultsCheck: atResults = compare.equalByte(parameterByte, barByte)
  if atResults results roomCheck
:roomCheck in=eachParameter
  fullCheck: full = compare.greaterOrEqualInt64(params, mostParameters)
  if full tooMany readCount
:readCount in=eachParameter
  readSlots: slots = readDigits(key, bytes, at, endAt)
  readAfter: afterCount = machine.loadInt64(endAt)
  countOffset: countPlace = math.multiplyInt64(params, eight)
  countStart: countSlotOffset = math.addInt64(countPlace, forty=40)
  findCount: countSlot = machine.offset(shape, countSlotOffset)
  storeCount: machine.storeInt64(countSlot, slots)
  startOffset: startSlotOffset = math.addInt64(countPlace, twoThirtyTwo=232)
  findStart: startSlot = machine.offset(shape, startSlotOffset)
  storeStart: machine.storeInt64(startSlot, offset)
  addOffset: nextOffset = math.addInt64(offset, slots)
  set offset nextOffset
  addParameter: nextParams = math.addInt64(params, one)
  set params nextParams
  set at afterCount
  commaCheck: comma = byteMatches(key, bytes, afterCount, commaByte)
  if comma skipComma eachParameter
:skipComma in=eachParameter
  pastComma: afterComma = math.addInt64(afterCount, one)
  set at afterComma
  goto eachParameter
:tooMany
  failMany: failText(manyText="a host call has too many parameters")
  return shape
:results
  storeParamsTarget: paramsSlot = machine.offset(shape, twentyFour=24)
  storeParams: machine.storeInt64(paramsSlot, params)
  afterResultsBar: resultsStart = math.addInt64(at, one)
  readResults: resultSlots = readDigits(key, bytes, resultsStart, endAt)
  findResults: resultsSlot = machine.offset(shape, thirtyTwo=32)
  storeResults: machine.storeInt64(resultsSlot, resultSlots)
  return shape

op byteMatches "Whether the byte at a position of a key is a given byte; a position past the end is not"
  input key machine.Address copied
  input bytes Int64 copied
  input at Int64 copied
  input wanted Byte copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let no Bool false
:begin
  insideCheck: inside = compare.lessThanInt64(at, bytes)
  if inside read outside
:outside
  return no
:read
  findByte: place = machine.offset(key, at)
  loadIt: byte = machine.loadByte(place)
  sameCheck: same = compare.equalByte(byte, wanted)
  return same

op slotFor "Where an address goes in the table of shapes: its bits mixed, within the table's entries"
  input key machine.Address copied
  input capacity Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let golden UInt64 11400714819323198485
:begin
  keyValue: raw = machine.toInt64(key)
  keyBits: wide = convert.int64BitsToUInt64(raw)
  dropLow: shifted = bits.shiftRightUInt64(wide, four=4)
  spread: mixed = math.wrappingMultiplyUInt64(shifted, golden)
  takeHigh: high = bits.shiftRightUInt64(mixed, thirtyTwo=32)
  capacityWide: capacityBits = convert.int64ToUInt64(capacity)
  maskOf: mask = math.subtractUInt64(capacityBits, oneWide=1)
  within: slot = bits.andUInt64(high, mask)
  narrow: slotValue = convert.uint64ToInt64(slot)
  return slotValue

op placeShape "Put a shape in the first free entry of a table of shapes after its key's slot"
  input table machine.Address copied
  input capacity Int64 copied
  input shape machine.Address copied
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  readKey: key = machine.loadAddress(shape)
  slotFind: first = slotFor(key, capacity)
  set at first
  nowhere: anywhere = machine.zero()
  maskOf: mask = math.subtractInt64(capacity, one=1)
  goto eachEntry
:eachEntry loop=while max=capacity
  entryOffset: offset = math.multiplyInt64(at, eight=8)
  findEntry: entry = machine.offset(table, offset)
  readEntry: held = machine.loadAddress(entry)
  emptyCheck: empty = machine.equal(held, anywhere)
  if empty store nextEntry
:nextEntry in=eachEntry
  advance: after = math.addInt64(at, one)
  wrap: wrapped = bits.andInt64(after, mask)
  set at wrapped
  goto eachEntry
:store
  storeShape: machine.storeAddress(entry, shape)
  return

op shapeOf "The shape of a key, worked out the first time its address is seen and kept by it"
  invariant keepsShapes "The same key's address gives the same shape every time"
  input key machine.Address copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let capacity Int64 0 mut
  let from Int64 0 mut
  let sixtyFour Int64 64
:begin
  findTableSlot: tableSlot = stateAt(shapesAt)
  readTable: table = machine.loadAddress(tableSlot)
  findCapacitySlot: capacitySlot = stateAt(shapesCapacityAt)
  readCapacity: held = machine.loadInt64(capacitySlot)
  nowhere: anywhere = machine.zero()
  emptyCheck: empty = compare.equalInt64(held, zero=0)
  if empty make search
:search
  slotFind: first = slotFor(key, held)
  set at first
  maskOf: mask = math.subtractInt64(held, one=1)
  goto eachEntry
:eachEntry loop=while max=held
  entryOffset: offset = math.multiplyInt64(at, eight=8)
  findEntry: entry = machine.offset(table, offset)
  readEntry: shape = machine.loadAddress(entry)
  freeCheck: free = machine.equal(shape, anywhere)
  if free make compareKey
:compareKey in=eachEntry
  readKey: shapeKey = machine.loadAddress(shape)
  sameCheck: same = machine.equal(shapeKey, key)
  if same found nextEntry
:nextEntry in=eachEntry
  advance: after = math.addInt64(at, one)
  wrap: wrapped = bits.andInt64(after, mask)
  set at wrapped
  goto eachEntry
:found
  return shape
:make
  parse: fresh = parseShape(key, bytes)
  findCountSlot: countSlot = stateAt(shapesCountAt)
  readCount: count = machine.loadInt64(countSlot)
  moreCount: nextCount = math.addInt64(count, one)
  twiceCount: needed = math.multiplyInt64(nextCount, two=2)
  roomCheck: tight = compare.greaterThanInt64(needed, held)
  if tight grow insert
:grow
  set capacity sixtyFour
  biggerCheck: bigger = compare.greaterThanInt64(held, zero)
  if bigger doubleIt allocate
:doubleIt
  doubled: twice = math.multiplyInt64(held, two)
  set capacity twice
  goto allocate
:allocate
  tableBytes: freshBytes = math.multiplyInt64(capacity, eight)
  takeTable: freshTable = heap.take(freshBytes)
  set from zero
  goto eachOld
:eachOld loop=while max=held
  oldDone: doneOld = compare.greaterOrEqualInt64(from, held)
  if doneOld swap moveOld
:moveOld in=eachOld
  oldOffset: oldEntryOffset = math.multiplyInt64(from, eight)
  findOld: oldEntry = machine.offset(table, oldEntryOffset)
  readOld: oldShape = machine.loadAddress(oldEntry)
  usedCheck: unused = machine.equal(oldShape, anywhere)
  if unused nextOld moveIt
:moveIt in=eachOld
  placeOld: placeShape(freshTable, capacity, oldShape)
  goto nextOld
:nextOld in=eachOld
  advanceOld: afterOld = math.addInt64(from, one)
  set from afterOld
  goto eachOld
:swap
  giveOld: heap.give(table)
  storeTable: machine.storeAddress(tableSlot, freshTable)
  storeCapacity: machine.storeInt64(capacitySlot, capacity)
  goto insert
:insert
  readTableNow: tableNow = machine.loadAddress(tableSlot)
  readCapacityNow: capacityNow = machine.loadInt64(capacitySlot)
  placeFresh: placeShape(tableNow, capacityNow, fresh)
  storeCount: machine.storeInt64(countSlot, nextCount)
  return fresh

## ---------------------------------------------------------------- a call's slots

## ---------------------------------------------------------------- text

op utf8InvalidAt "The offset of the first byte that does not start a valid UTF-8 sequence, or -1: the strict rules and offset of Python's decoder (no overlong forms, no surrogates, nothing past U+10FFFF)"
  invariant findsInvalid "Gives -1 for valid UTF-8 and otherwise the offset Python's decoder reports"
  input data machine.Address copied
  input bytes Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let need Int64 0 mut
  let low Byte 128 mut
  let high Byte 191 mut
  let k Int64 1 mut
  let valid Int64 -1
  let continuationLow Byte 128
  let continuationHigh Byte 191
  let two Int64 2
  let three Int64 3
  let a0 Byte 160
  let x9f Byte 159
  let x90 Byte 144
  let x8f Byte 143
:begin
  goto eachByte
:eachByte loop=while max=bytes
  endCheck: atEnd = compare.greaterOrEqualInt64(at, bytes)
  if atEnd allValid readLead
:readLead in=eachByte
  findLead: leadPlace = machine.offset(data, at)
  loadLead: lead = machine.loadByte(leadPlace)
  set low continuationLow
  set high continuationHigh
  asciiCheck: ascii = compare.lessThanByte(lead, continuationLow)
  if ascii skipAscii twoCheck
:skipAscii in=eachByte
  afterAscii: nextAscii = math.addInt64(at, one=1)
  set at nextAscii
  goto eachByte
:twoCheck in=eachByte
  twoLow: aboveTwo = compare.greaterOrEqualByte(lead, c2=194)
  twoHigh: belowTwo = compare.lessOrEqualByte(lead, df=223)
  twoBoth: isTwo = logic.and(aboveTwo, belowTwo)
  if isTwo needOne e0Check
:needOne in=eachByte
  set need one
  goto continuations
:e0Check in=eachByte
  e0Is: isE0 = compare.equalByte(lead, e0=224)
  if isE0 needTwoE0 threeCheck
:needTwoE0 in=eachByte
  set need two
  set low a0
  goto continuations
:threeCheck in=eachByte
  threeLow: aboveThree = compare.greaterOrEqualByte(lead, e1=225)
  threeHigh: belowThree = compare.lessOrEqualByte(lead, ec=236)
  threeBoth: plainThree = logic.and(aboveThree, belowThree)
  eeIs: isEE = compare.equalByte(lead, ee=238)
  efIs: isEF = compare.equalByte(lead, ef=239)
  eeOrEf: highThree = logic.or(isEE, isEF)
  threeAny: isThree = logic.or(plainThree, highThree)
  if isThree needTwo edCheck
:needTwo in=eachByte
  set need two
  goto continuations
:edCheck in=eachByte
  edIs: isED = compare.equalByte(lead, ed=237)
  if isED needTwoED f0Check
:needTwoED in=eachByte
  set need two
  set high x9f
  goto continuations
:f0Check in=eachByte
  f0Is: isF0 = compare.equalByte(lead, f0=240)
  if isF0 needThreeF0 fourCheck
:needThreeF0 in=eachByte
  set need three
  set low x90
  goto continuations
:fourCheck in=eachByte
  fourLow: aboveFour = compare.greaterOrEqualByte(lead, f1=241)
  fourHigh: belowFour = compare.lessOrEqualByte(lead, f3=243)
  fourBoth: isFour = logic.and(aboveFour, belowFour)
  if isFour needThree f4Check
:needThree in=eachByte
  set need three
  goto continuations
:f4Check in=eachByte
  f4Is: isF4 = compare.equalByte(lead, f4=244)
  if isF4 needThreeF4 invalid
:needThreeF4 in=eachByte
  set need three
  set high x8f
  goto continuations
:continuations in=eachByte
  set k one
  goto eachContinuation
:eachContinuation loop=while max=three in=eachByte
  continuationsDone: doneContinuations = compare.greaterThanInt64(k, need)
  if doneContinuations advanceSequence checkContinuation
:checkContinuation in=eachContinuation
  placeOf: continuationAt = math.addInt64(at, k)
  pastCheck: past = compare.greaterOrEqualInt64(continuationAt, bytes)
  if past invalid readContinuation
:readContinuation in=eachContinuation
  findContinuation: continuationPlace = machine.offset(data, continuationAt)
  loadContinuation: continuation = machine.loadByte(continuationPlace)
  firstCheck: isFirst = compare.equalInt64(k, one)
  if isFirst firstRange laterRange
:firstRange in=eachContinuation
  firstLow: belowFirst = compare.lessThanByte(continuation, low)
  firstHigh: aboveFirst = compare.greaterThanByte(continuation, high)
  firstBad: badFirst = logic.or(belowFirst, aboveFirst)
  if badFirst invalid nextContinuation
:laterRange in=eachContinuation
  laterLow: belowLater = compare.lessThanByte(continuation, continuationLow)
  laterHigh: aboveLater = compare.greaterThanByte(continuation, continuationHigh)
  laterBad: badLater = logic.or(belowLater, aboveLater)
  if badLater invalid nextContinuation
:nextContinuation in=eachContinuation
  advanceContinuation: nextK = math.addInt64(k, one)
  set k nextK
  goto eachContinuation
:advanceSequence in=eachByte
  sequenceLength: sequence = math.addInt64(need, one)
  afterSequence: nextAt = math.addInt64(at, sequence)
  set at nextAt
  goto eachByte
:invalid
  return at
:allValid
  return valid

op fromBytes "string.fromBytes: bytes as text in a region when they are valid UTF-8, otherwise string.Utf8Error.invalidAt with the offset"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok Int32 0
:begin
  findRaw: raw = slots.slotOf(shape, args, zero=0)
  readData: data = machine.loadAddress(raw)
  findLength: lengthSlot = machine.offset(raw, eight=8)
  readLength: length = machine.loadInt64(lengthSlot)
  check: bad = utf8InvalidAt(data, length)
  badCheck: invalid = compare.greaterOrEqualInt64(bad, zero)
  if invalid refuse copy
:refuse
  failed: status = slots.failWith(payload, utf8Invalid, bad)
  return status
:copy
  readRegion: region = slots.addressArg(shape, args, one=1)
  copyText: slots.putText(region, data, length, results)
  return ok

## ---------------------------------------------------------------- byte buffers

op bufferNew "buffer.new: an empty buffer owned by a region"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  takeBuffer: buffer = heap.take(fortyEight=48)
  readRegion: region = slots.addressArg(shape, args, zero=0)
  makeHandle: handle = handles.newHandle(kindBuffer, buffer, region)
  storeHandle: machine.storeInt64(results, handle)
  return

op bufferAdd "Append bytes to a buffer, doubling its block (from 8 bytes) when they do not fit"
  input buffer machine.Address copied
  input data machine.Address copied
  input bytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let capacity Int64 0 mut
  let sixtyFour Int64 64
:begin
  readBlock: block = machine.loadAddress(buffer)
  findLength: lengthSlot = machine.offset(buffer, eight=8)
  readLength: length = machine.loadInt64(lengthSlot)
  findCapacity: capacitySlot = machine.offset(buffer, sixteen=16)
  readCapacity: held = machine.loadInt64(capacitySlot)
  needOf: needed = math.addInt64(length, bytes)
  fitCheck: fits = compare.lessOrEqualInt64(needed, held)
  if fits append grow
:grow
  set capacity held
  emptyCheck: empty = compare.equalInt64(held, zero=0)
  if empty start eachDouble
:start
  set capacity eight
  goto eachDouble
:eachDouble loop=while max=sixtyFour
  smallCheck: small = compare.lessThanInt64(capacity, needed)
  if small doubleIt resize
:doubleIt in=eachDouble
  doubled: twice = math.multiplyInt64(capacity, two=2)
  set capacity twice
  goto eachDouble
:resize
  growBlock: grown = heap.resize(block, capacity)
  storeBlock: machine.storeAddress(buffer, grown)
  storeCapacity: machine.storeInt64(capacitySlot, capacity)
  goto append
:append
  readBlockNow: blockNow = machine.loadAddress(buffer)
  findEnd: endAt = machine.offset(blockNow, length)
  copyIn: machine.copy(endAt, data, bytes)
  storeLength: machine.storeInt64(lengthSlot, needed)
  return

op bufferAppendString "buffer.appendString: append text's bytes"
  input shape machine.Address copied
  input args machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findBuffer: buffer = handles.objectOf(handle, kindBuffer)
  findText: text = slots.slotOf(shape, args, one=1)
  readData: data = machine.loadAddress(text)
  findLength: lengthSlot = machine.offset(text, eight=8)
  readLength: length = machine.loadInt64(lengthSlot)
  append: bufferAdd(buffer, data, length)
  return

op bufferAppendByte "buffer.appendByte: append the low eight bits of a value"
  input shape machine.Address copied
  input args machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findBuffer: buffer = handles.objectOf(handle, kindBuffer)
  readValue: value = slots.argOf(shape, args, one=1)
  lowBits: low = bits.andInt64(value, byteMask=255)
  narrow: byte = convert.int64ToByte(low)
  findByte: byteSlot = stateAt(byteAt)
  storeByte: machine.storeByte(byteSlot, byte)
  append: bufferAdd(buffer, byteSlot, one)
  return

op bufferAppendInt "buffer.appendInt64: append a whole number's decimal text"
  input shape machine.Address copied
  input args machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findBuffer: buffer = handles.objectOf(handle, kindBuffer)
  readValue: value = slots.argOf(shape, args, one=1)
  findDigits: digits = stateAt(digitsAt)
  format: length = numbers.formatDecimal(value, digits)
  append: bufferAdd(buffer, digits, length)
  return

op bufferLength "buffer.length: how many bytes a buffer holds"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findBuffer: buffer = handles.objectOf(handle, kindBuffer)
  findLength: lengthSlot = machine.offset(buffer, eight=8)
  readLength: length = machine.loadInt64(lengthSlot)
  storeLength: machine.storeInt64(results, length)
  return

op bufferToString "buffer.toString: the bytes as text in a region when they are valid UTF-8, otherwise string.Utf8Error.invalidAt"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok Int32 0
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findBuffer: buffer = handles.objectOf(handle, kindBuffer)
  readData: data = machine.loadAddress(buffer)
  findLength: lengthSlot = machine.offset(buffer, eight=8)
  readLength: length = machine.loadInt64(lengthSlot)
  check: bad = utf8InvalidAt(data, length)
  badCheck: invalid = compare.greaterOrEqualInt64(bad, zero)
  if invalid refuse copy
:refuse
  failed: status = slots.failWith(payload, utf8Invalid, bad)
  return status
:copy
  readRegion: region = slots.addressArg(shape, args, one=1)
  copyText: slots.putText(region, data, length, results)
  return ok

op bufferToBytes "buffer.toBytes: a copy of the bytes that lives as long as the buffer"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findBuffer: buffer = handles.objectOf(handle, kindBuffer)
  readData: data = machine.loadAddress(buffer)
  findLength: lengthSlot = machine.offset(buffer, eight=8)
  readLength: length = machine.loadInt64(lengthSlot)
  takeCopy: copy = heap.take(length)
  copyBytes: machine.copy(copy, data, length)
  findKept: keptSlot = machine.offset(buffer, twentyFour=24)
  readKept: kept = machine.loadAddress(keptSlot)
  findKeptCount: keptCountSlot = machine.offset(buffer, thirtyTwo=32)
  readKeptCount: keptCount = machine.loadInt64(keptCountSlot)
  findKeptCapacity: keptCapacitySlot = machine.offset(buffer, forty=40)
  readKeptCapacity: keptCapacity = machine.loadInt64(keptCapacitySlot)
  roomCheck: room = compare.lessThanInt64(keptCount, keptCapacity)
  if room keep grow
:grow
  doubleKept: doubled = math.multiplyInt64(keptCapacity, two=2)
  moreKept: grownCapacity = math.addInt64(doubled, eight=8)
  keptBytes: grownBytes = math.multiplyInt64(grownCapacity, eight)
  growList: grown = heap.resize(kept, grownBytes)
  storeKept: machine.storeAddress(keptSlot, grown)
  storeKeptCapacity: machine.storeInt64(keptCapacitySlot, grownCapacity)
  goto keep
:keep
  readKeptNow: keptNow = machine.loadAddress(keptSlot)
  keptOffset: offset = math.multiplyInt64(keptCount, eight)
  findSlot: slot = machine.offset(keptNow, offset)
  storeCopy: machine.storeAddress(slot, copy)
  countMore: moreCount = math.addInt64(keptCount, one=1)
  storeKeptCount: machine.storeInt64(keptCountSlot, moreCount)
  storeAddress: machine.storeAddress(results, copy)
  findResultLength: resultLengthSlot = machine.offset(results, eight)
  storeLength: machine.storeInt64(resultLengthSlot, length)
  return

## ---------------------------------------------------------------- log lines

op logLine "Write `[<level>] <text>` and a line end to standard error; a write the system refuses is log.LogError.failed with its code"
  input level String borrowed
  input shape machine.Address copied
  input args machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let status Int32 0 mut
  let open String "["
  let close String "] "
  let lineEnd String "\n"
:begin
  findHandle: handle = output.standardHandle(two=2)
  findOpen: openAt = machine.addressOfString(open)
  writeOpen: openStatus = output.writeAll(handle, openAt, one=1)
  set status openStatus
  openCheck: openFailed = compare.notEqualInt32(openStatus, zero32=0)
  if openFailed failed writeLevel
:writeLevel
  findLevel: levelAt = machine.addressOfString(level)
  levelLength: levelBytes = string.byteLength(level)
  writeLevelText: levelStatus = output.writeAll(handle, levelAt, levelBytes)
  set status levelStatus
  levelCheck: levelFailed = compare.notEqualInt32(levelStatus, zero32)
  if levelFailed failed writeClose
:writeClose
  findClose: closeAt = machine.addressOfString(close)
  writeCloseText: closeStatus = output.writeAll(handle, closeAt, closeBytes=2)
  set status closeStatus
  closeCheck: closeFailed = compare.notEqualInt32(closeStatus, zero32)
  if closeFailed failed writeText
:writeText
  findText: text = slots.slotOf(shape, args, zero=0)
  readData: data = machine.loadAddress(text)
  findLength: lengthSlot = machine.offset(text, eight=8)
  readLength: length = machine.loadInt64(lengthSlot)
  writeBody: bodyStatus = output.writeAll(handle, data, length)
  set status bodyStatus
  bodyCheck: bodyFailed = compare.notEqualInt32(bodyStatus, zero32)
  if bodyFailed failed writeEnd
:writeEnd
  findEnd: endAt = machine.addressOfString(lineEnd)
  writeEndText: endStatus = output.writeAll(handle, endAt, one)
  set status endStatus
  endCheck: endFailed = compare.notEqualInt32(endStatus, zero32)
  if endFailed failed done
:done
  return zero32
:failed
  widen: code = convert.int32ToInt64(status)
  report: result = slots.failWith(payload, logFailed, code)
  return result

## ---------------------------------------------------------------- maps

op mapNew "map.Map.new: an empty map owned by a region; the compiler adds 1 when its keys are `String` (D-61) and 1 when its values are (D-107)"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let keySlots Int64 -1 mut
:begin
  takeMap: map = heap.take(oneNinetyTwo=192)
  readRegion: region = slots.addressArg(shape, args, zero=0)
  storeRegion: machine.storeAddress(map, region)
  readText: text = slots.flagArg(shape, args, one=1)
  readTextValues: textValues = slots.flagArg(shape, args, two=2)
  findTextValues: textValuesSlot = machine.offset(map, eight=8)
  storeTextValues: machine.storeInt64(textValuesSlot, textValues)
  textCheck: textKeys = compare.notEqualInt64(text, zero)
  if textKeys twoSlots prepare
:twoSlots
  set keySlots two
  goto prepare
:prepare
  findTable: table = machine.offset(map, sixteen=16)
  prepareTable: tables.prepare(table, text, keySlots, minusOne=-1)
  findCopies: copies = machine.offset(map, hundredFour=104)
  prepareCopies: tables.prepare(copies, one, two, zero)
  makeHandle: handle = handles.newHandle(kindMap, map, region)
  storeHandle: machine.storeInt64(results, handle)
  return

op mapArg "The map a call's first parameter names, its table's shape learned from the key's slots and a number of value slots (-1 when the call does not show them)"
  input shape machine.Address copied
  input args machine.Address copied
  input valueSlots Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findMap: map = handles.objectOf(handle, kindMap)
  findTable: table = machine.offset(map, sixteen=16)
  keySlots: keyCount = slots.countOf(shape, one=1)
  learn: tables.shape(table, keyCount, valueSlots)
  return map

op keySlotsOf "How many slots a table's keys take"
  input table machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findKeys: keysSlot = machine.offset(table, eight=8)
  readKeys: keys = machine.loadInt64(keysSlot)
  return keys

op valueAddress "Where a row's value slots start"
  input table machine.Address copied
  input row machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  readKeys: keys = keySlotsOf(table)
  slotsOf: slots = math.addInt64(keys, two=2)
  bytesOf: offset = math.multiplyInt64(slots, eight=8)
  findValue: value = machine.offset(row, offset)
  return value

op mapPut "map.Map.put: a text key is copied into the map's region the first time it is put (D-61), a text value every time (D-107)"
  input shape machine.Address copied
  input args machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let key machine.Address unset mut
  let row machine.Address unset mut
:begin
  valueSlots: valueCount = slots.countOf(shape, two=2)
  findMap: map = mapArg(shape, args, valueCount)
  findTable: table = machine.offset(map, sixteen=16)
  findKey: given = slots.slotOf(shape, args, one=1)
  set key given
  hashOf: hash = tables.hashKey(table, given)
  readRegion: region = machine.loadAddress(map)
  readText: text = machine.loadInt64(table)
  textCheck: textKeys = compare.notEqualInt64(text, zero=0)
  if textKeys copyKey place
:copyKey
  findCopies: copies = machine.offset(map, hundredFour=104)
  findCopy: copyRow = tables.find(copies, given, hash)
  findScratch: scratch = stateAt(keyCopyAt)
  newCheck: fresh = compare.lessThanInt64(copyRow, zero)
  if fresh firstCopy oldCopy
:firstCopy
  readData: data = machine.loadAddress(given)
  findLength: lengthSlot = machine.offset(given, eight=8)
  readLength: length = machine.loadInt64(lengthSlot)
  copyText: slots.putText(region, data, length, scratch)
  keepCopy: copied = tables.insert(copies, scratch, hash)
  set key scratch
  goto place
:oldCopy
  findOld: oldRow = tables.rowAddress(copies, copyRow)
  findOldKey: oldKey = machine.offset(oldRow, sixteen)
  copyOld: machine.copy(scratch, oldKey, sixteen)
  set key scratch
  goto place
:place
  findRow: found = tables.find(table, key, hash)
  missingCheck: missing = compare.lessThanInt64(found, zero)
  if missing addRow knownRow
:addRow
  insertRow: inserted = tables.insert(table, key, hash)
  set row inserted
  goto value
:knownRow
  readRow: known = tables.rowAddress(table, found)
  set row known
  goto value
:value
  findValue: valueAt = valueAddress(table, row)
  findGiven: givenValue = slots.slotOf(shape, args, two)
  findTextValues: textValuesSlot = machine.offset(map, eight=8)
  readTextValues: textValues = machine.loadInt64(textValuesSlot)
  textValueCheck: copyValue = compare.notEqualInt64(textValues, zero)
  if copyValue copyTextValue plainValue
:copyTextValue
  readValueData: valueData = machine.loadAddress(givenValue)
  findValueLength: valueLengthSlot = machine.offset(givenValue, eight)
  readValueLength: valueLength = machine.loadInt64(valueLengthSlot)
  copyValueText: slots.putText(region, valueData, valueLength, valueAt)
  return
:plainValue
  findValueSlots: valuesSlot = machine.offset(table, sixteen)
  readValueSlots: values = machine.loadInt64(valuesSlot)
  valueBytes: bytes = math.multiplyInt64(values, eight)
  copyPlain: machine.copy(valueAt, givenValue, bytes)
  return

op mapGet "map.Map.get: the value of a key, or map.KeyMissing.missing"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok Int32 0
:begin
  resultSlots: resultCount = slots.shapeField(shape, thirtyTwo=32)
  findMap: map = mapArg(shape, args, resultCount)
  findTable: table = machine.offset(map, sixteen=16)
  findKey: key = slots.slotOf(shape, args, one=1)
  hashOf: hash = tables.hashKey(table, key)
  findRow: found = tables.find(table, key, hash)
  missingCheck: missing = compare.lessThanInt64(found, zero=0)
  if missing refuse give
:refuse
  failed: status = slots.failWith(payload, keyMissing, zero)
  return status
:give
  readRow: row = tables.rowAddress(table, found)
  findValue: valueAt = valueAddress(table, row)
  findValueSlots: valuesSlot = machine.offset(table, sixteen)
  readValueSlots: values = machine.loadInt64(valuesSlot)
  valueBytes: bytes = math.multiplyInt64(values, eight=8)
  copyOut: machine.copy(results, valueAt, bytes)
  return ok

op mapContains "map.Map.contains: 1 when the map has the key, otherwise 0"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let yes Int64 1
  let no Int64 0
:begin
  findMap: map = mapArg(shape, args, minusOne=-1)
  findTable: table = machine.offset(map, sixteen=16)
  findKey: key = slots.slotOf(shape, args, one=1)
  hashOf: hash = tables.hashKey(table, key)
  findRow: found = tables.find(table, key, hash)
  foundCheck: present = compare.greaterOrEqualInt64(found, no)
  if present giveYes giveNo
:giveYes
  storeYes: machine.storeInt64(results, yes)
  return
:giveNo
  storeNo: machine.storeInt64(results, no)
  return

op mapRemove "map.Map.remove: remove a key, or map.KeyMissing.missing"
  input shape machine.Address copied
  input args machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok Int32 0
:begin
  findMap: map = mapArg(shape, args, minusOne=-1)
  findTable: table = machine.offset(map, sixteen=16)
  findKey: key = slots.slotOf(shape, args, one=1)
  hashOf: hash = tables.hashKey(table, key)
  findRow: found = tables.find(table, key, hash)
  missingCheck: missing = compare.lessThanInt64(found, zero=0)
  if missing refuse take
:refuse
  failed: status = slots.failWith(payload, keyMissing, zero)
  return status
:take
  removeRow: tables.remove(table, found)
  return ok

op mapLength "map.Map.length: how many keys a map has"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findMap: map = handles.objectOf(handle, kindMap)
  findTable: table = machine.offset(map, sixteen=16)
  countLive: count = tables.live(table)
  storeCount: machine.storeInt64(results, count)
  return

op mapKeyAt "map.Map.keyAt: the key at a position in first-put order, for `forEach` over a map (D-62); a position outside the map traps"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findMap: map = handles.objectOf(handle, kindMap)
  findTable: table = machine.offset(map, sixteen=16)
  readPosition: position = slots.argOf(shape, args, one=1)
  countLive: count = tables.live(table)
  lowCheck: below = compare.lessThanInt64(position, zero)
  highCheck: above = compare.greaterOrEqualInt64(position, count)
  outsideCheck: outside = logic.or(below, above)
  if outside refuse give
:refuse
  report: failPosition(lead="a map was read at position ", position, count)
  return
:give
  findKey: keyAt = tables.keyAt(table, position)
  readKeys: keys = keySlotsOf(table)
  keyBytes: bytes = math.multiplyInt64(keys, eight=8)
  copyOut: machine.copy(results, keyAt, bytes)
  return

## ---------------------------------------------------------------- sets

op setNew "set.Set.new: an empty set owned by a region; the compiler adds 1 when its items are `String` (D-93)"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let keySlots Int64 -1 mut
  let two Int64 2
:begin
  takeSet: items = heap.take(eightyEight=88)
  readRegion: region = slots.addressArg(shape, args, zero=0)
  readText: text = slots.flagArg(shape, args, one=1)
  textCheck: textItems = compare.notEqualInt64(text, zero)
  if textItems twoSlots prepare
:twoSlots
  set keySlots two
  goto prepare
:prepare
  prepareTable: tables.prepare(items, text, keySlots, zero)
  makeHandle: handle = handles.newHandle(kindSet, items, region)
  storeHandle: machine.storeInt64(results, handle)
  return

op setArg "The set a call's first parameter names, its table's shape learned from the item's slots"
  input shape machine.Address copied
  input args machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findSet: items = handles.objectOf(handle, kindSet)
  itemSlots: itemCount = slots.countOf(shape, one=1)
  learn: tables.shape(items, itemCount, zero)
  return items

op setAdd "set.Set.add: add an item unless the set has it; a text item is copied into the set's region the first time (D-93)"
  input shape machine.Address copied
  input args machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findSet: items = setArg(shape, args)
  findItem: item = slots.slotOf(shape, args, one=1)
  hashOf: hash = tables.hashKey(items, item)
  findRow: found = tables.find(items, item, hash)
  presentCheck: present = compare.greaterOrEqualInt64(found, zero=0)
  if present done textCheck
:done
  return
:textCheck
  readText: text = machine.loadInt64(items)
  isTextCheck: textItem = compare.notEqualInt64(text, zero)
  if textItem copyItem plainItem
:copyItem
  readHandle: handle = slots.argOf(shape, args, zero)
  readRegion: region = handles.regionOf(handle)
  findScratch: scratch = stateAt(keyCopyAt)
  readData: data = machine.loadAddress(item)
  findLength: lengthSlot = machine.offset(item, eight=8)
  readLength: length = machine.loadInt64(lengthSlot)
  copyText: slots.putText(region, data, length, scratch)
  insertCopy: copied = tables.insert(items, scratch, hash)
  return
:plainItem
  insertItem: inserted = tables.insert(items, item, hash)
  return

op setItemAt "set.Set.itemAt: the item at a position in first-added order, for `forEach` over a set (D-93); a position outside the set traps"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findSet: items = handles.objectOf(handle, kindSet)
  readPosition: position = slots.argOf(shape, args, one=1)
  countLive: count = tables.live(items)
  lowCheck: below = compare.lessThanInt64(position, zero)
  highCheck: above = compare.greaterOrEqualInt64(position, count)
  outsideCheck: outside = logic.or(below, above)
  if outside refuse give
:refuse
  report: failPosition(lead="a set was read at position ", position, count)
  return
:give
  findItem: itemAt = tables.keyAt(items, position)
  readKeys: keys = keySlotsOf(items)
  itemBytes: bytes = math.multiplyInt64(keys, eight=8)
  copyOut: machine.copy(results, itemAt, bytes)
  return

op setContains "set.Set.contains: 1 when the set has the item, otherwise 0"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let yes Int64 1
  let no Int64 0
:begin
  findSet: items = setArg(shape, args)
  findItem: item = slots.slotOf(shape, args, one=1)
  hashOf: hash = tables.hashKey(items, item)
  findRow: found = tables.find(items, item, hash)
  foundCheck: present = compare.greaterOrEqualInt64(found, no)
  if present giveYes giveNo
:giveYes
  storeYes: machine.storeInt64(results, yes)
  return
:giveNo
  storeNo: machine.storeInt64(results, no)
  return

op setRemove "set.Set.remove: remove an item if the set has it"
  input shape machine.Address copied
  input args machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findSet: items = setArg(shape, args)
  findItem: item = slots.slotOf(shape, args, one=1)
  hashOf: hash = tables.hashKey(items, item)
  findRow: found = tables.find(items, item, hash)
  foundCheck: present = compare.greaterOrEqualInt64(found, zero=0)
  if present take done
:take
  removeRow: tables.remove(items, found)
  return
:done
  return

op setLength "set.Set.length: how many items a set has"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findSet: items = handles.objectOf(handle, kindSet)
  countLive: count = tables.live(items)
  storeCount: machine.storeInt64(results, count)
  return

## ---------------------------------------------------------------- dispatch

op dispatch "Run the host target of a number with a call's slots: 0, or an error's variant number with its payload stored"
  input number Int64 copied
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok Int32 0
:begin
  is1: t1 = compare.equalInt64(number, n1=1)
  if t1 do1 check2
:do1
  run1: bufferAppendByte(shape, args)
  return ok
:check2
  is2: t2 = compare.equalInt64(number, n2=2)
  if t2 do2 check3
:do2
  run2: bufferAppendInt(shape, args)
  return ok
:check3
  is3: t3 = compare.equalInt64(number, n3=3)
  if t3 do3 check4
:do3
  run3: bufferAppendString(shape, args)
  return ok
:check4
  is4: t4 = compare.equalInt64(number, n4=4)
  if t4 do4 check5
:do4
  run4: bufferLength(shape, args, results)
  return ok
:check5
  is5: t5 = compare.equalInt64(number, n5=5)
  if t5 do5 check6
:do5
  run5: bufferNew(shape, args, results)
  return ok
:check6
  is6: t6 = compare.equalInt64(number, n6=6)
  if t6 do6 check7
:do6
  run6: bufferToBytes(shape, args, results)
  return ok
:check7
  is7: t7 = compare.equalInt64(number, n7=7)
  if t7 do7 check8
:do7
  run7: status7 = bufferToString(shape, args, results, payload)
  return status7
:check8
  is8: t8 = compare.equalInt64(number, n8=8)
  if t8 do8 check9
:do8
  run8: status8 = logLine(debugLevel="debug", shape, args, payload)
  return status8
:check9
  is9: t9 = compare.equalInt64(number, n9=9)
  if t9 do9 check10
:do9
  run9: status9 = logLine(errorLevel="error", shape, args, payload)
  return status9
:check10
  is10: t10 = compare.equalInt64(number, n10=10)
  if t10 do10 check11
:do10
  run10: status10 = logLine(infoLevel="info", shape, args, payload)
  return status10
:check11
  is11: t11 = compare.equalInt64(number, n11=11)
  if t11 do11 check12
:do11
  run11: status11 = logLine(warnLevel="warn", shape, args, payload)
  return status11
:check12
  is12: t12 = compare.equalInt64(number, n12=12)
  if t12 do12 check13
:do12
  run12: mapContains(shape, args, results)
  return ok
:check13
  is13: t13 = compare.equalInt64(number, n13=13)
  if t13 do13 check14
:do13
  run13: status13 = mapGet(shape, args, results, payload)
  return status13
:check14
  is14: t14 = compare.equalInt64(number, n14=14)
  if t14 do14 check15
:do14
  run14: mapKeyAt(shape, args, results)
  return ok
:check15
  is15: t15 = compare.equalInt64(number, n15=15)
  if t15 do15 check16
:do15
  run15: mapLength(shape, args, results)
  return ok
:check16
  is16: t16 = compare.equalInt64(number, n16=16)
  if t16 do16 check17
:do16
  run16: mapNew(shape, args, results)
  return ok
:check17
  is17: t17 = compare.equalInt64(number, n17=17)
  if t17 do17 check18
:do17
  run17: mapPut(shape, args)
  return ok
:check18
  is18: t18 = compare.equalInt64(number, n18=18)
  if t18 do18 check19
:do18
  run18: status18 = mapRemove(shape, args, payload)
  return status18
:check19
  is19: t19 = compare.equalInt64(number, n19=19)
  if t19 do19 check20
:do19
  run19: setAdd(shape, args)
  return ok
:check20
  is20: t20 = compare.equalInt64(number, n20=20)
  if t20 do20 check21
:do20
  run20: setContains(shape, args, results)
  return ok
:check21
  is21: t21 = compare.equalInt64(number, n21=21)
  if t21 do21 check22
:do21
  run21: setItemAt(shape, args, results)
  return ok
:check22
  is22: t22 = compare.equalInt64(number, n22=22)
  if t22 do22 check23
:do22
  run22: setLength(shape, args, results)
  return ok
:check23
  is23: t23 = compare.equalInt64(number, n23=23)
  if t23 do23 check24
:do23
  run23: setNew(shape, args, results)
  return ok
:check24
  is24: t24 = compare.equalInt64(number, n24=24)
  if t24 do24 check25
:do24
  run24: setRemove(shape, args)
  return ok
:check25
  is25: t25 = compare.equalInt64(number, n25=25)
  if t25 do25 unknown
:do25
  run25: status25 = fromBytes(shape, args, results, payload)
  return status25
:unknown
  runMore: statusMore = dispatchMore(number, shape, args, results, payload)
  return statusMore

op dispatchMore "Run a host target of stage 3 and 4 by its number (26 on): 0, or an error's variant number with its payload stored"
  input number Int64 copied
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok Int32 0
:begin
  goto check26
:check26
  is26: t26 = compare.equalInt64(number, n26=26)
  if t26 do26 check27
:do26
  run26: tasks.deadlineNever(results)
  return ok
:check27
  is27: t27 = compare.equalInt64(number, n27=27)
  if t27 do27 check28
:do27
  run27: tasks.deadlineAfter(shape, args, results)
  return ok
:check28
  is28: t28 = compare.equalInt64(number, n28=28)
  if t28 do28 check29
:do28
  run28: tasks.sleepFor(shape, args)
  return ok
:check29
  is29: t29 = compare.equalInt64(number, n29=29)
  if t29 do29 check30
:do29
  run29: tasks.clockNow(results)
  return ok
:check30
  is30: t30 = compare.equalInt64(number, n30=30)
  if t30 do30 check31
:do30
  run30: tasks.clockMonotonic(results)
  return ok
:check31
  is31: t31 = compare.equalInt64(number, n31=31)
  if t31 do31 check32
:do31
  run31: tasks.channelNew(shape, args, results)
  return ok
:check32
  is32: t32 = compare.equalInt64(number, n32=32)
  if t32 do32 check33
:do32
  run32: status32 = tasks.channelSend(shape, args, payload)
  return status32
:check33
  is33: t33 = compare.equalInt64(number, n33=33)
  if t33 do33 check34
:do33
  run33: status33 = tasks.channelReceive(shape, args, results, payload)
  return status33
:check34
  is34: t34 = compare.equalInt64(number, n34=34)
  if t34 do34 check35
:do34
  run34: tasks.channelClose(shape, args)
  return ok
:check35
  is35: t35 = compare.equalInt64(number, n35=35)
  if t35 do35 check36
:do35
  run35: status35 = files.fsClose(shape, args, payload)
  return status35
:check36
  is36: t36 = compare.equalInt64(number, n36=36)
  if t36 do36 check37
:do36
  run36: status36 = files.fsCreate(shape, args, results, payload)
  return status36
:check37
  is37: t37 = compare.equalInt64(number, n37=37)
  if t37 do37 check38
:do37
  run37: status37 = files.fsCreateDirectory(shape, args, payload)
  return status37
:check38
  is38: t38 = compare.equalInt64(number, n38=38)
  if t38 do38 check39
:do38
  run38: files.fsEntryCount(shape, args, results)
  return ok
:check39
  is39: t39 = compare.equalInt64(number, n39=39)
  if t39 do39 check40
:do39
  run39: status39 = files.fsEntryName(shape, args, results, payload)
  return status39
:check40
  is40: t40 = compare.equalInt64(number, n40=40)
  if t40 do40 check41
:do40
  run40: files.fsExists(shape, args, results)
  return ok
:check41
  is41: t41 = compare.equalInt64(number, n41=41)
  if t41 do41 check42
:do41
  run41: status41 = files.fsListDirectory(shape, args, results, payload)
  return status41
:check42
  is42: t42 = compare.equalInt64(number, n42=42)
  if t42 do42 check43
:do42
  run42: status42 = files.fsLock(shape, args, payload)
  return status42
:check43
  is43: t43 = compare.equalInt64(number, n43=43)
  if t43 do43 check44
:do43
  run43: status43 = files.fsOpenAppend(shape, args, results, payload)
  return status43
:check44
  is44: t44 = compare.equalInt64(number, n44=44)
  if t44 do44 check45
:do44
  run44: status44 = files.fsOpenRead(shape, args, results, payload)
  return status44
:check45
  is45: t45 = compare.equalInt64(number, n45=45)
  if t45 do45 check46
:do45
  run45: status45 = files.fsOpenWrite(shape, args, results, payload)
  return status45
:check46
  is46: t46 = compare.equalInt64(number, n46=46)
  if t46 do46 check47
:do46
  run46: status46 = files.fsRead(shape, args, results, payload)
  return status46
:check47
  is47: t47 = compare.equalInt64(number, n47=47)
  if t47 do47 check48
:do47
  run47: status47 = files.fsReadAll(shape, args, results, payload)
  return status47
:check48
  is48: t48 = compare.equalInt64(number, n48=48)
  if t48 do48 check49
:do48
  run48: status48 = files.fsRemove(shape, args, payload)
  return status48
:check49
  is49: t49 = compare.equalInt64(number, n49=49)
  if t49 do49 check50
:do49
  run49: status49 = files.fsRemoveDirectory(shape, args, payload)
  return status49
:check50
  is50: t50 = compare.equalInt64(number, n50=50)
  if t50 do50 check51
:do50
  run50: status50 = files.fsUnlock(shape, args, payload)
  return status50
:check51
  is51: t51 = compare.equalInt64(number, n51=51)
  if t51 do51 check52
:do51
  run51: status51 = files.fsWrite(shape, args, payload)
  return status51
:check52
  is52: t52 = compare.equalInt64(number, n52=52)
  if t52 do52 check53
:do52
  run52: status52 = files.fsWriteAll(shape, args, payload)
  return status52
:check53
  is53: t53 = compare.equalInt64(number, n53=53)
  if t53 do53 check54
:do53
  run53: status53 = processes.readLine(shape, args, results, payload)
  return status53
:check54
  is54: t54 = compare.equalInt64(number, n54=54)
  if t54 do54 check55
:do54
  run54: status54 = processes.environmentGet(shape, args, results, payload)
  return status54
:check55
  is55: t55 = compare.equalInt64(number, n55=55)
  if t55 do55 check56
:do55
  run55: processes.addArgument(shape, args)
  return ok
:check56
  is56: t56 = compare.equalInt64(number, n56=56)
  if t56 do56 check57
:do56
  run56: status56 = processes.argument(shape, args, results, payload)
  return status56
:check57
  is57: t57 = compare.equalInt64(number, n57=57)
  if t57 do57 check58
:do57
  run57: processes.argumentCount(results)
  return ok
:check58
  is58: t58 = compare.equalInt64(number, n58=58)
  if t58 do58 check59
:do58
  run58: processes.newArguments(shape, args, results)
  return ok
:check59
  is59: t59 = compare.equalInt64(number, n59=59)
  if t59 do59 check60
:do59
  run59: status59 = processes.processRun(shape, args, results, payload)
  return status59
:check60
  is60: t60 = compare.equalInt64(number, n60=60)
  if t60 do60 check61
:do60
  run60: status60 = processes.processRunCaptured(shape, args, results, payload)
  return status60
:check61
  is61: t61 = compare.equalInt64(number, n61=61)
  if t61 do61 check62
:do61
  run61: status61 = processes.secretFromEnvironment(shape, args, results, payload)
  return status61
:check62
  is62: t62 = compare.equalInt64(number, n62=62)
  if t62 do62 check63
:do62
  run62: processes.secretFromText(shape, args, results)
  return ok
:check63
  is63: t63 = compare.equalInt64(number, n63=63)
  if t63 do63 check64
:do63
  run63: processes.secretLength(shape, args, results)
  return ok
:check64
  is64: t64 = compare.equalInt64(number, n64=64)
  if t64 do64 check65
:do64
  run64: processes.secretMatches(shape, args, results)
  return ok
:check65
  is65: t65 = compare.equalInt64(number, n65=65)
  if t65 do65 check66
:do65
  run65: processes.secretReveal(shape, args, results)
  return ok
:check66
  is66: t66 = compare.equalInt64(number, n66=66)
  if t66 do66 check67
:do66
  run66: hashes.cryptoConstantTimeEquals(shape, args, results)
  return ok
:check67
  is67: t67 = compare.equalInt64(number, n67=67)
  if t67 do67 check68
:do67
  run67: hashes.cryptoHmacSha256(shape, args, results)
  return ok
:check68
  is68: t68 = compare.equalInt64(number, n68=68)
  if t68 do68 check69
:do68
  run68: hashes.cryptoSha256(shape, args, results)
  return ok
:check69
  is69: t69 = compare.equalInt64(number, n69=69)
  if t69 do69 check70
:do69
  run69: hashes.cryptoToHex(shape, args, results)
  return ok
:check70
  is70: t70 = compare.equalInt64(number, n70=70)
  if t70 do70 check71
:do70
  run70: status70 = processes.ffiBind(shape, args, results, payload)
  return status70
:check71
  is71: t71 = compare.equalInt64(number, n71=71)
  if t71 do71 check72
:do71
  run71: processes.ffiClose(shape, args)
  return ok
:check72
  is72: t72 = compare.equalInt64(number, n72=72)
  if t72 do72 rest
:do72
  run72: status72 = processes.ffiOpen(shape, args, results, payload)
  return status72
:rest
  runRest: restStatus = dispatchRest(number, shape, args, results, payload)
  return restStatus

op dispatchRest "Run a host target of the modules that came last by its number (73 on): random (73 to 75), http (76 to 79), json (80 to 96); 0, or an error's variant number with its payload stored"
  input number Int64 copied
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok Int32 0
:begin
  randomCheck: isRandom = compare.lessOrEqualInt64(number, n75=75)
  if isRandom runRandom httpCheck
:runRandom
  randomPlace: randomWhich = math.subtractInt64(number, n72=72)
  randomIt: randomStatus = generators.randomCall(randomWhich, shape, args, results, payload)
  return randomStatus
:httpCheck
  checkHttp: isHttp = compare.lessOrEqualInt64(number, n79=79)
  if isHttp runHttp jsonCheck
:runHttp
  httpPlace: httpWhich = math.subtractInt64(number, n75)
  httpIt: httpStatus = requests.httpCall(httpWhich, shape, args, results, payload)
  return httpStatus
:jsonCheck
  checkJson: isJson = compare.lessOrEqualInt64(number, n96=96)
  if isJson runJson unknown
:runJson
  jsonPlace: jsonWhich = math.subtractInt64(number, n79)
  jsonIt: jsonStatus = documents.jsonCall(jsonWhich, shape, args, results, payload)
  return jsonStatus
:unknown
  failUnknown: failText(unknownText="a host call named a target this runtime does not number")
  return ok

op hostCall "Run a host target for compiled code: the key's shape, then its target with the call's slots; gives 0 or an error's variant number, its payload stored: refined_host"
  invariant runsTargets "Each target behaves as its handler in host.py and the C runtime do, its error variants and traps included"
  input key machine.Address copied
  input bytes Int64 copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_host"
:begin
  findShape: shape = shapeOf(key, bytes)
  clearPayload: machine.storeInt64(payload, zero=0)
  readNumber: number = slots.shapeField(shape, sixteen=16)
  readRow: row = hostTargets.rowAt(number) ? run
  readScoped: scoped = HostTarget.scoped(row)
  scopedCheck: isScoped = compare.greaterOrEqualInt64(scoped, zero)
  if isScoped checkScope run
:checkScope
  readName: name = HostTarget.name(row)
  readParams: params = slots.shapeField(shape, twentyFour=24)
  lastOf: last = math.subtractInt64(params, one=1)
  readValue: value = files.textAt(shape, args, scoped)
  readValueBytes: valueBytes = files.textBytes(shape, args, scoped)
  readScopes: scopes = files.textAt(shape, args, last)
  readScopesBytes: scopesBytes = files.textBytes(shape, args, last)
  checkIt: files.checkScope(name, value, valueBytes, scopes, scopesBytes)
  goto run
:run
  runIt: status = dispatch(number, shape, args, results, payload)
  return status

@tests

## Tests keep a call's slots in the last 4 KiB of machine.state: its arguments from byte 61440, its results from
## 61568, its error's payload at 61632, and bytes to read from 61696. Each key is a constant of the test, so its
## address names it as a compiled program's keys do.

op slotAt "The address of a slot of the tests' scratch: arguments from 0, results from 16, the payload at 24, bytes from 32"
  input slot Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  slotBytes: offset = math.multiplyInt64(slot, eight=8)
  startOf: start = math.addInt64(offset, scratchAt=61440)
  findSlot: place = machine.offset(state, start)
  return place

op setArgument "Set an argument slot of the tests' call"
  input slot Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  findSlot: place = slotAt(slot)
  storeIt: machine.storeInt64(place, value)
  return

op setAddress "Set an argument slot of the tests' call to an address"
  input slot Int64 copied
  input value machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  findSlot: place = slotAt(slot)
  storeIt: machine.storeAddress(place, value)
  return

op readResult "A result slot of the tests' call"
  input slot Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  resultSlot: index = math.addInt64(slot, sixteen=16)
  findSlot: place = slotAt(index)
  readIt: value = machine.loadInt64(place)
  return value

op call "Call a host target with the tests' slots and give its status"
  input key String borrowed
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findKey: keyAt = machine.addressOfString(key)
  keyLength: bytes = string.byteLength(key)
  findArgs: args = slotAt(zero=0)
  findResults: results = slotAt(sixteen=16)
  findPayload: payload = slotAt(twentyFour=24)
  run: status = hostCall(keyAt, bytes, args, results, payload)
  widen: wide = convert.int32ToInt64(status)
  return wide

op expectCall "Call a host target and compare its status and first result slot with what is expected"
  input key String borrowed
  input status Int64 copied
  input value Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  run: got = call(key)
  expectStatus: test.assertEqualInt64(status, got)
  readValue: first = readResult(zero=0)
  expectValue: test.assertEqualInt64(value, first)
  return

op expectOk "Call a host target that gives no result and check that it succeeds"
  input key String borrowed
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  run: got = call(key)
  expectStatus: test.assertEqualInt64(zero=0, got)
  return

test shapeTest "A key gives its target's number, its parameters' slots and where they start, and its result slots, once per key"
  verifies targetNumber findsTarget
  verifies parseShape readsKey
  verifies shapeOf keepsShapes
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let key String "map.Map.put|2,1|0"
  let logKey String "log.info|2|0"
  let stranger String "nothing.here"
:begin
  findKey: keyAt = machine.addressOfString(key)
  keyLength: bytes = string.byteLength(key)
  findTarget: number = targetNumber(keyAt, eleven=11)
  expectNumber: test.assertEqualInt64(seventeen=17, number)
  findLog: logAt = machine.addressOfString(logKey)
  findLogTarget: logNumber = targetNumber(logAt, eight=8)
  expectLog: test.assertEqualInt64(ten=10, logNumber)
  findStranger: strangerAt = machine.addressOfString(stranger)
  findNone: noNumber = targetNumber(strangerAt, twelve=12)
  expectNone: test.assertEqualInt64(zero=0, noNumber)
  parse: shape = parseShape(keyAt, bytes)
  readNumber: shapeNumber = slots.shapeField(shape, sixteen=16)
  expectShapeNumber: test.assertEqualInt64(seventeen, shapeNumber)
  readParams: params = slots.shapeField(shape, twentyFour=24)
  expectParams: test.assertEqualInt64(two=2, params)
  readResults: resultSlots = slots.shapeField(shape, thirtyTwo=32)
  expectResults: test.assertEqualInt64(zero, resultSlots)
  readKeyCount: keyCount = slots.countOf(shape, zero)
  expectKeyCount: test.assertEqualInt64(two, keyCount)
  readValueCount: valueCount = slots.countOf(shape, one=1)
  expectValueCount: test.assertEqualInt64(one, valueCount)
  readValueStart: valueStart = slots.shapeField(shape, twoForty=240)
  expectValueStart: test.assertEqualInt64(two, valueStart)
  giveShape: heap.give(shape)
  keep: kept = shapeOf(keyAt, bytes)
  keepAgain: again = shapeOf(keyAt, bytes)
  sameCheck: same = machine.equal(kept, again)
  expectSame: test.assertTrue(same)
  return

op putBytes "Put bytes in the tests' scratch from slot 32, one byte per value given, and give their address"
  input first Int64 copied
  input second Int64 copied
  input third Int64 copied
  input fourth Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findBytes: place = slotAt(thirtyTwo=32)
  narrowFirst: firstByte = convert.int64ToByte(first)
  storeFirst: machine.storeByte(place, firstByte)
  findSecond: secondAt = machine.offset(place, one=1)
  narrowSecond: secondByte = convert.int64ToByte(second)
  storeSecond: machine.storeByte(secondAt, secondByte)
  findThird: thirdAt = machine.offset(place, two=2)
  narrowThird: thirdByte = convert.int64ToByte(third)
  storeThird: machine.storeByte(thirdAt, thirdByte)
  findFourth: fourthAt = machine.offset(place, three=3)
  narrowFourth: fourthByte = convert.int64ToByte(fourth)
  storeFourth: machine.storeByte(fourthAt, fourthByte)
  return place

op expectInvalid "Put four bytes in the scratch and compare where the first `length` of them stop being valid UTF-8 with what is expected"
  input first Int64 copied
  input second Int64 copied
  input third Int64 copied
  input fourth Int64 copied
  input length Int64 copied
  input expected Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  place: data = putBytes(first, second, third, fourth)
  check: bad = utf8InvalidAt(data, length)
  expectBad: test.assertEqualInt64(expected, bad)
  return

test utf8Test "UTF-8 is checked as Python's decoder checks it"
  verifies utf8InvalidAt findsInvalid
  effect use machine.memory
  uses memoryAccess
:begin
  place: data = putBytes(a=97, b=98, eAcute1=195, eAcute2=169)
  check: bad = utf8InvalidAt(data, four=4)
  expectValid: test.assertEqualInt64(minusOne=-1, bad)
  truncated: expectInvalid(a, b, eAcute1, eAcute2, three=3, two=2)
  overlong: expectInvalid(e0=224, x80=128, x80, a, four, zero=0)
  surrogate: expectInvalid(a, ed=237, xa0=160, x80, four, one=1)
  beyond: expectInvalid(f4=244, x90=144, x80, x80, four, zero)
  lone: expectInvalid(a, x80, a, a, four, one)
  fourByte: expectInvalid(f0=240, x9f=159, x98=152, x80, four, minusOne)
  invalidLead: expectInvalid(a, b, c0=192, x80, four, two)
  return

test mapTest "A map keeps its keys in the order they were first put, updates, reports missing keys, and is closed with its region"
  verifies hostCall runsTargets
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let label String "region `scratch` of `mapTest`"
:begin
  findLabel: labelAt = machine.addressOfString(label)
  labelLength: labelBytes = string.byteLength(label)
  make: region = regions.newRegion(capacity=4096, labelAt, labelBytes)
  setRegion: setAddress(zero=0, region)
  setPlainKeys: setArgument(one=1, zero)
  setPlainValues: setArgument(two=2, zero)
  findArgs: args = slotAt(zero)
  findResults: results = slotAt(sixteen=16)
  findPayload: payload = slotAt(twentyFour=24)
  findNewKey: newKeyAt = machine.addressOfString(newKey="map.Map.new|1,1,1|1")
  measureNewKey: newKeyBytes = string.byteLength(newKey)
  makeMap: madeStatus = hostCall(newKeyAt, newKeyBytes, args, results, payload)
  widenMade: made = convert.int32ToInt64(madeStatus)
  expectMade: test.assertEqualInt64(zero, made)
  readHandle: map = readResult(zero)
  setMap: setArgument(zero, map)
  setSeven: setArgument(one, seven=7)
  setSeventy: setArgument(two, seventy=70)
  putSeven: expectOk(putKey="map.Map.put|1,1,1|0")
  setThree: setArgument(one, three=3)
  setThirty: setArgument(two, thirty=30)
  putThree: expectOk(putKey)
  setSevenAgain: setArgument(one, seven)
  setUpdate: setArgument(two, seventySeven=77)
  putAgain: expectOk(putKey)
  getSeven: expectCall(getKey="map.Map.get|1,1|1", zero, seventySeven)
  setMissing: setArgument(one, nine=9)
  getMissing: missingStatus = call(getKey)
  expectMissing: test.assertEqualInt64(one, missingStatus)
  countKeys: expectCall(lengthKey="map.Map.length|1|1", zero, two)
  setFirst: setArgument(one, zero)
  firstKey: expectCall(keyAtKey="map.Map.keyAt|1,1|1", zero, seven)
  setSecond: setArgument(one, one)
  secondKey: expectCall(keyAtKey, zero, three)
  setRemoved: setArgument(one, seven)
  removeSeven: expectOk(removeKey="map.Map.remove|1,1|0")
  removeAgain: againStatus = call(removeKey)
  expectGone: test.assertEqualInt64(one, againStatus)
  setThreeAgain: setArgument(one, three)
  hasThree: expectCall(containsKey="map.Map.contains|1,1|1", zero, one)
  setNowFirst: setArgument(one, zero)
  nowFirst: expectCall(keyAtKey, zero, three)
  free: regions.release(region)
  readClosed: closed = handles.kindOf(map)
  expectClosed: test.assertEqualInt64(zero, closed)
  return

test textMapTest "A map with text keys and values finds keys by their bytes and keeps its own copies of keys and values in its region"
  verifies hostCall runsTargets
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let label String "region `scratch` of `textMapTest`"
  let key String "alpha"
  let otherKey String "xalpha"
  let value String "first"
:begin
  findLabel: labelAt = machine.addressOfString(label)
  labelLength: labelBytes = string.byteLength(label)
  make: region = regions.newRegion(capacity=4096, labelAt, labelBytes)
  setRegion: setAddress(zero=0, region)
  setTextKeys: setArgument(one=1, one)
  setTextValues: setArgument(two=2, one)
  findArgs: args = slotAt(zero)
  findResults: results = slotAt(sixteen=16)
  findPayload: payload = slotAt(twentyFour=24)
  findNewKey: newKeyAt = machine.addressOfString(newKey="map.Map.new|1,1,1|1")
  measureNewKey: newKeyBytes = string.byteLength(newKey)
  makeMap: madeStatus = hostCall(newKeyAt, newKeyBytes, args, results, payload)
  widenMade: made = convert.int32ToInt64(madeStatus)
  expectMadeText: test.assertEqualInt64(zero, made)
  readHandle: map = readResult(zero)
  setMap: setArgument(zero, map)
  findKey: keyAt = machine.addressOfString(key)
  setKey: setAddress(one, keyAt)
  setKeyLength: setArgument(two, five=5)
  findValue: valueAt = machine.addressOfString(value)
  setValue: setAddress(three=3, valueAt)
  setValueLength: setArgument(four=4, five)
  putIt: expectOk(putKey="map.Map.put|1,2,2|0")
  readUsed: left = regions.remaining(region)
  expectCopied: test.assertEqualInt64(fourThousandEightySix=4086, left)
  findOther: otherAt = machine.addressOfString(otherKey)
  findInside: insideAt = machine.offset(otherAt, one)
  setOther: setAddress(one, insideAt)
  getIt: got = call(getKey="map.Map.get|1,2|2")
  expectFound: test.assertEqualInt64(zero, got)
  readCopy: copyValue = readResult(zero)
  asAddress: copyAt = machine.fromInt64(copyValue)
  movedCheck: same = machine.equal(copyAt, valueAt)
  notSame: moved = logic.not(same)
  expectMoved: test.assertTrue(moved)
  readCopyLength: copyLength = readResult(one)
  viewCopy: shown = machine.stringAt(copyAt, copyLength)
  expectText: test.assertEqualString(value, shown)
  putAgain: expectOk(putKey)
  readUsedAgain: leftAgain = regions.remaining(region)
  expectOnlyValue: test.assertEqualInt64(fourThousandEightyOne=4081, leftAgain)
  free: regions.release(region)
  return

test setAndBufferTest "A set adds each item once and reads them in order; a buffer appends text, numbers, and bytes and gives them back as text"
  verifies hostCall runsTargets
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let label String "region `scratch` of `setAndBufferTest`"
  let text String "ab"
  let expected String "ab-42!"
:begin
  findLabel: labelAt = machine.addressOfString(label)
  labelLength: labelBytes = string.byteLength(label)
  make: region = regions.newRegion(capacity=4096, labelAt, labelBytes)
  setRegion: setAddress(zero=0, region)
  setPlain: setArgument(one=1, zero)
  findArgs: args = slotAt(zero)
  findResults: results = slotAt(sixteen=16)
  findPayload: payload = slotAt(twentyFour=24)
  findNewKey: newKeyAt = machine.addressOfString(newKey="set.Set.new|1,1|1")
  measureNewKey: newKeyBytes = string.byteLength(newKey)
  makeSet: madeStatus = hostCall(newKeyAt, newKeyBytes, args, results, payload)
  widenMade: made = convert.int32ToInt64(madeStatus)
  expectMadeSet: test.assertEqualInt64(zero, made)
  readSet: items = readResult(zero)
  setSet: setArgument(zero, items)
  setFive: setArgument(one, five=5)
  addFive: expectOk(addKey="set.Set.add|1,1|0")
  setTwo: setArgument(one, two=2)
  addTwo: expectOk(addKey)
  setFiveAgain: setArgument(one, five)
  addAgain: expectOk(addKey)
  countItems: expectCall(lengthKey="set.Set.length|1|1", zero, two)
  setPosition: setArgument(one, one)
  secondItem: expectCall(itemAtKey="set.Set.itemAt|1,1|1", zero, two)
  setRemoved: setArgument(one, five)
  removeFive: expectOk(removeKey="set.Set.remove|1,1|0")
  hasFive: expectCall(containsKey="set.Set.contains|1,1|1", zero, zero)
  setBufferRegion: setAddress(zero, region)
  makeBuffer: bufferMade = call(bufferKey="buffer.new|1|1")
  readBuffer: buffer = readResult(zero)
  setBuffer: setArgument(zero, buffer)
  findText: textAt = machine.addressOfString(text)
  setText: setAddress(one, textAt)
  setTextLength: setArgument(two, two)
  appendText: expectOk(appendStringKey="buffer.appendString|1,2|0")
  setNumber: setArgument(one, minusFortyTwo=-42)
  appendNumber: expectOk(appendIntKey="buffer.appendInt64|1,1|0")
  setByte: setArgument(one, bang=289)
  appendByte: expectOk(appendByteKey="buffer.appendByte|1,1|0")
  countBytes: expectCall(bufferLengthKey="buffer.length|1|1", zero, six=6)
  setTarget: setAddress(one, region)
  toText: textStatus = call(toStringKey="buffer.toString|1,1|2")
  expectText: test.assertEqualInt64(zero, textStatus)
  readText: textValue = readResult(zero)
  asAddress: shownAt = machine.fromInt64(textValue)
  readLength: shownLength = readResult(one)
  viewText: shown = machine.stringAt(shownAt, shownLength)
  expectShown: test.assertEqualString(expected, shown)
  free: regions.release(region)
  readClosed: closed = handles.kindOf(buffer)
  expectClosed: test.assertEqualInt64(zero, closed)
  return

test fromBytesTest "Bytes become text when they are valid UTF-8, and string.Utf8Error.invalidAt names the first offset that is not"
  verifies hostCall runsTargets
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let label String "region `scratch` of `fromBytesTest`"
:begin
  findLabel: labelAt = machine.addressOfString(label)
  labelLength: labelBytes = string.byteLength(label)
  make: region = regions.newRegion(capacity=64, labelAt, labelBytes)
  place: data = putBytes(a=97, b=98, bad=255, c=99)
  setData: setAddress(zero=0, data)
  setByteCount: setArgument(one=1, two=2)
  setRegion: setAddress(two, region)
  findArgs: args = slotAt(zero)
  findResults: results = slotAt(sixteen=16)
  findPayload: payload = slotAt(twentyFour=24)
  findGoodKey: goodKeyAt = machine.addressOfString(goodKey="string.fromBytes|2,1|2")
  measureGoodKey: goodKeyBytes = string.byteLength(goodKey)
  goodText: goodRaw = hostCall(goodKeyAt, goodKeyBytes, args, results, payload)
  widenGood: goodStatus = convert.int32ToInt64(goodRaw)
  readFromBytesKey: fromBytesLength = string.byteLength(fromBytesKey="string.fromBytes|2,1|2")
  expectGood: test.assertEqualInt64(zero, goodStatus)
  readGoodLength: goodLength = readResult(one)
  expectGoodLength: test.assertEqualInt64(two, goodLength)
  setAll: setArgument(one, four=4)
  badText: badStatus = call(fromBytesKey)
  expectBad: test.assertEqualInt64(one, badStatus)
  findPayloadSlot: payloadAt = slotAt(twentyFour)
  readPayload: payloadValue = machine.loadInt64(payloadAt)
  expectOffset: test.assertEqualInt64(two, payloadValue)
  free: regions.release(region)
  return
