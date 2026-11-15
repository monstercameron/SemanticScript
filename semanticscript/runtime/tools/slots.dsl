module slots "A host call's slots: where each parameter's slots are, reading them, and putting results and errors"
  path slots
  imports standard.machine standard.math standard.compare standard.string standard.convert standard.test regions
  exports slotOf argOf addressArg countOf shapeField flagArg putText failWith

capability memoryAccess "Authority to read a host call's slots and write its results" use machine.memory none

capability systemCalls "Authority to take a region's memory for a result's copy" use system.calls none

## A host call's shape (the host module works it out from the key): at 16 the target's number, 24 how many
## parameters, 32 how many result slots, from 40 each parameter's slot count, from 232 each parameter's first slot.
## The arguments are 64-bit slots; a `String` or `Bytes` is two, its address and its length.

op slotOf "The address of a parameter's first slot among a call's argument slots"
  invariant findsSlot "Gives the argument slot where the parameter's slots start, as the shape places it"
  input shape machine.Address copied
  input args machine.Address copied
  input parameter Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  parameterOffset: place = math.multiplyInt64(parameter, eight=8)
  startOffset: startSlotOffset = math.addInt64(place, twoThirtyTwo=232)
  findStart: startSlot = machine.offset(shape, startSlotOffset)
  readStart: start = machine.loadInt64(startSlot)
  startBytes: offset = math.multiplyInt64(start, eight)
  findSlot: slot = machine.offset(args, offset)
  return slot

op argOf "A parameter's first slot as a number"
  invariant readsNumber "Gives the parameter's first slot as a whole number"
  input shape machine.Address copied
  input args machine.Address copied
  input parameter Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findSlot: slot = slotOf(shape, args, parameter)
  readSlot: value = machine.loadInt64(slot)
  return value

op addressArg "A parameter's first slot as an address"
  invariant readsAddress "Gives the parameter's first slot as an address"
  input shape machine.Address copied
  input args machine.Address copied
  input parameter Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findSlot: slot = slotOf(shape, args, parameter)
  readSlot: value = machine.loadAddress(slot)
  return value

op countOf "How many slots a parameter takes"
  invariant countsSlots "Gives how many slots the shape gives the parameter"
  input shape machine.Address copied
  input parameter Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  parameterOffset: place = math.multiplyInt64(parameter, eight=8)
  countOffset: countSlotOffset = math.addInt64(place, forty=40)
  findCount: countSlot = machine.offset(shape, countSlotOffset)
  readCount: count = machine.loadInt64(countSlot)
  return count

op shapeField "A whole number of a shape at an offset: 16 its target, 24 its parameters, 32 its result slots"
  invariant readsShape "Gives the shape's whole number at the offset"
  input shape machine.Address copied
  input offset Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findField: field = machine.offset(shape, offset)
  readField: value = machine.loadInt64(field)
  return value

op flagArg "Whether a call has a parameter at a position and its slot is not 0 (the flags the compiler adds to `new`)"
  invariant readsFlag "Gives 1 when the parameter exists and its slot is not 0, otherwise 0"
  input shape machine.Address copied
  input args machine.Address copied
  input parameter Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let no Int64 0
  let yes Int64 1
:begin
  readParams: params = shapeField(shape, twentyFour=24)
  presentCheck: present = compare.lessThanInt64(parameter, params)
  if present readFlag absent
:absent
  return no
:readFlag
  readValue: value = argOf(shape, args, parameter)
  setCheck: flagged = compare.notEqualInt64(value, no)
  if flagged giveYes absent
:giveYes
  return yes

op putText "Copy bytes into a region and store the copy's address and length in two slots"
  invariant copiesText "The two slots hold the address of a copy of the bytes in the region, and their length"
  input region machine.Address copied
  input data machine.Address copied
  input bytes Int64 copied
  input out machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  take: block = regions.allocate(region, bytes)
  copyIn: machine.copy(block, data, bytes)
  storeAddress: machine.storeAddress(out, block)
  findLength: lengthSlot = machine.offset(out, eight=8)
  storeLength: machine.storeInt64(lengthSlot, bytes)
  return

op failWith "Store an error's payload and give its variant's number"
  invariant storesPayload "The payload slot holds the value and the variant's number is given back"
  input payload machine.Address copied
  input status Int32 copied
  input value Int64 copied
  output Int32
  effect use machine.memory
  uses memoryAccess
:begin
  storePayload: machine.storeInt64(payload, value)
  return status

@tests

## Tests build a shape and a call's slots in the last 4 KiB of machine.state: the shape from byte 61440, the
## arguments from 61952, the results from 62016, the payload at 62080.

test slotsTest "A shape places each parameter's slots, which read back as numbers, addresses, and flags; text goes into a region; an error stores its payload"
  verifies slotOf findsSlot
  verifies argOf readsNumber
  verifies addressArg readsAddress
  verifies countOf countsSlots
  verifies shapeField readsShape
  verifies flagArg readsFlag
  verifies putText copiesText
  verifies failWith storesPayload
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let label String "slots test"
  let word String "word"
:begin
  findState: state = machine.state()
  findShape: shape = machine.offset(state, shapeAt=61440)
  findArgs: args = machine.offset(state, argsAt=61952)
  findResults: results = machine.offset(state, resultsAt=62016)
  findPayload: payload = machine.offset(state, payloadAt=62080)
  findParams: paramsSlot = machine.offset(shape, twentyFour=24)
  storeParams: machine.storeInt64(paramsSlot, two=2)
  findFirstCount: firstCount = machine.offset(shape, forty=40)
  storeFirstCount: machine.storeInt64(firstCount, two)
  findSecondCount: secondCount = machine.offset(shape, fortyEight=48)
  storeSecondCount: machine.storeInt64(secondCount, one=1)
  findFirstStart: firstStart = machine.offset(shape, twoThirtyTwo=232)
  storeFirstStart: machine.storeInt64(firstStart, zero=0)
  findSecondStart: secondStart = machine.offset(shape, twoForty=240)
  storeSecondStart: machine.storeInt64(secondStart, two)
  findWord: wordAt = machine.addressOfString(word)
  storeWord: machine.storeAddress(args, wordAt)
  findLength: lengthSlot = machine.offset(args, eight=8)
  storeLength: machine.storeInt64(lengthSlot, four=4)
  findValue: valueSlot = machine.offset(args, sixteen=16)
  storeValue: machine.storeInt64(valueSlot, seven=7)
  readCount: count = countOf(shape, zero)
  expectCount: test.assertEqualInt64(two, count)
  readParamCount: params = shapeField(shape, twentyFour)
  expectParams: test.assertEqualInt64(two, params)
  readSlot: second = slotOf(shape, args, one)
  sameSlot: sameAddress = machine.equal(second, valueSlot)
  expectSlot: test.assertTrue(sameAddress)
  readValue: value = argOf(shape, args, one)
  expectValue: test.assertEqualInt64(seven, value)
  readAddress: textAt = addressArg(shape, args, zero)
  sameText: sameWord = machine.equal(textAt, wordAt)
  expectText: test.assertTrue(sameWord)
  readFlag: flag = flagArg(shape, args, one)
  expectFlag: test.assertEqualInt64(one, flag)
  readMissing: missing = flagArg(shape, args, two)
  expectMissing: test.assertEqualInt64(zero, missing)
  findLabel: labelAt = machine.addressOfString(label)
  labelLength: labelBytes = string.byteLength(label)
  make: region = regions.newRegion(capacity=4096, labelAt, labelBytes)
  copy: putText(region, wordAt, four, results)
  readCopy: copied = machine.loadAddress(results)
  findCopyLength: copyLengthSlot = machine.offset(results, eight)
  readCopyLength: copyLength = machine.loadInt64(copyLengthSlot)
  expectCopyLength: test.assertEqualInt64(four, copyLength)
  compareCopy: same = machine.compare(copied, wordAt, four)
  sameWide: sameValue = convert.int32ToInt64(same)
  expectCopy: test.assertEqualInt64(zero, sameValue)
  free: regions.release(region)
  failIt: status = failWith(payload, three32=3, value)
  statusWide: statusValue = convert.int32ToInt64(status)
  expectStatus: test.assertEqualInt64(three=3, statusValue)
  readPayload: stored = machine.loadInt64(payload)
  expectPayload: test.assertEqualInt64(seven, stored)
  return
