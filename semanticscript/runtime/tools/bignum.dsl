module bignum "Whole numbers of any size up to 6,400 bits, in memory, with exact arithmetic: what floating-point text is computed with (D-125)"
  path bignum
  imports standard.machine standard.system standard.string standard.math standard.compare standard.bits standard.logic standard.test frames
  exports setSmall copyNumber isZero compareNumbers addNumber subtractNumber multiplySmall addSmall shiftLeft shiftRightOne bitLength multiplyPowerOfTen lowLimbs

capability memoryAccess "Authority to keep numbers in memory by address" use machine.memory none

capability systemCalls "Authority to end the process when a number would not fit" use system.calls none

## A number is a block of numberBytes: at 0 how many 32-bit limbs it uses (0 for zero; the highest used limb is
## never 0), then the limbs from the lowest, each in 8 bytes as a UInt64 below 2^32, so a limb times a limb plus a
## carry fits in 64 bits. The caller gives the block; nothing here allocates.
constant limbCapacity "How many limbs a number holds" Int64 200

constant numberBytes "The bytes of a number's block: its length and its limbs" Int64 1608

constant limbMask "The bits of one limb" UInt64 4294967295

## ---------------------------------------------------------------- limbs

op limbAddress "The address of a number's limb, by its position from the lowest"
  input number machine.Address copied
  input position Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  slotOf: slot = math.addInt64(position, one=1)
  bytesOf: offset = math.multiplyInt64(slot, eight=8)
  findLimb: at = machine.offset(number, offset)
  return at

op readLimb "A number's limb at a position, 0 past its length or below 0"
  input number machine.Address copied
  input position Int64 copied
  output UInt64
  effect use machine.memory
  uses memoryAccess
  let zeroWide UInt64 0
:begin
  readLength: length = machine.loadInt64(number)
  lowCheck: below = compare.lessThanInt64(position, zero=0)
  highCheck: above = compare.greaterOrEqualInt64(position, length)
  outsideCheck: outside = logic.or(below, above)
  if outside giveZero read
:giveZero
  return zeroWide
:read
  findLimb: at = limbAddress(number, position)
  readValue: value = machine.loadUInt64(at)
  return value

op writeLimb "Set a number's limb at a position, which is below its capacity"
  input number machine.Address copied
  input position Int64 copied
  input value UInt64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  findLimb: at = limbAddress(number, position)
  storeValue: machine.storeUInt64(at, value)
  return

op fits "Trap unless a number of limbs fits a number's block (the runtime's arithmetic never needs more)"
  input length Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let message String "a number is too long for the runtime's arithmetic"
:begin
  fitCheck: fitting = compare.lessOrEqualInt64(length, limbCapacity)
  if fitting done tooLong
:done
  return
:tooLong
  findText: textAt = machine.addressOfString(message)
  textLength: bytes = string.byteLength(message)
  writeReport: status = frames.report(textAt, bytes)
  exit: system.exitProcess(trapCode=70)
  return

op trim "Drop a number's highest limbs while they are 0, so its length counts only what is used"
  input number machine.Address copied
  input length Int64 copied
  effect use machine.memory
  uses memoryAccess
  let used Int64 0 mut
:begin
  set used length
  goto eachLimb
:eachLimb loop=while max=length
  emptyCheck: empty = compare.lessOrEqualInt64(used, zero=0)
  if empty store checkTop
:checkTop in=eachLimb
  topOf: top = math.subtractInt64(used, one=1)
  readTop: topValue = readLimbRaw(number, top)
  zeroCheck: isZeroLimb = compare.equalUInt64(topValue, zeroWide=0)
  if isZeroLimb shorten store
:shorten in=eachLimb
  set used top
  goto eachLimb
:store
  storeLength: machine.storeInt64(number, used)
  return

op readLimbRaw "A number's limb at a position below its capacity, whatever its length says"
  input number machine.Address copied
  input position Int64 copied
  output UInt64
  effect use machine.memory
  uses memoryAccess
:begin
  findLimb: at = limbAddress(number, position)
  readValue: value = machine.loadUInt64(at)
  return value

## ---------------------------------------------------------------- setting and comparing

op setSmall "Set a number to a 64-bit value"
  invariant holdsValue "The number is the value given: one or two limbs, or none for 0"
  input number machine.Address copied
  input value UInt64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  lowOf: low = bits.andUInt64(value, limbMask)
  highOf: high = bits.shiftRightUInt64(value, thirtyTwo=32)
  writeLow: writeLimb(number, zero=0, low)
  writeHigh: writeLimb(number, one=1, high)
  trimIt: trim(number, two=2)
  return

op copyNumber "Make a number the same as another"
  invariant copiesValue "The target holds the source's value"
  input target machine.Address copied
  input source machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  readLength: length = machine.loadInt64(source)
  slotsOf: slots = math.addInt64(length, one=1)
  bytesOf: bytes = math.multiplyInt64(slots, eight=8)
  copyAll: machine.copy(target, source, bytes)
  return

op isZero "Whether a number is 0"
  invariant zeroHasNoLimbs "A number is 0 exactly when it uses no limbs"
  input number machine.Address copied
  output Bool
  effect use machine.memory
  uses memoryAccess
:begin
  readLength: length = machine.loadInt64(number)
  zeroCheck: zeroValue = compare.equalInt64(length, zero=0)
  return zeroValue

op compareNumbers "How one number compares with another: -1 when it is smaller, 0 when they are equal, 1 when it is larger"
  invariant ordersNumbers "Orders numbers by value: by their lengths, then by their limbs from the highest"
  input left machine.Address copied
  input right machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let less Int64 -1
  let same Int64 0
  let more Int64 1
:begin
  readLeft: leftLength = machine.loadInt64(left)
  readRight: rightLength = machine.loadInt64(right)
  shorterCheck: shorter = compare.lessThanInt64(leftLength, rightLength)
  if shorter giveLess longerCheck
:longerCheck
  checkLonger: longer = compare.greaterThanInt64(leftLength, rightLength)
  if longer giveMore limbs
:limbs
  set at leftLength
  goto eachLimb
:eachLimb loop=while max=leftLength
  doneCheck: done = compare.lessOrEqualInt64(at, same)
  if done giveSame compareLimb
:compareLimb in=eachLimb
  downOne: below = math.subtractInt64(at, more)
  readLeftLimb: leftLimb = readLimbRaw(left, below)
  readRightLimb: rightLimb = readLimbRaw(right, below)
  lessCheck: smaller = compare.lessThanUInt64(leftLimb, rightLimb)
  if smaller giveLess greaterCheck
:greaterCheck in=eachLimb
  checkGreater: larger = compare.greaterThanUInt64(leftLimb, rightLimb)
  if larger giveMore nextLimb
:nextLimb in=eachLimb
  set at below
  goto eachLimb
:giveLess
  return less
:giveMore
  return more
:giveSame
  return same

## ---------------------------------------------------------------- arithmetic

op addNumber "Add a number to another in place: target becomes target plus addend"
  invariant addsExactly "The target becomes the exact sum, carrying into a new limb when it must"
  input target machine.Address copied
  input addend machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let carry UInt64 0 mut
  let length Int64 0 mut
:begin
  readTarget: targetLength = machine.loadInt64(target)
  readAddend: addendLength = machine.loadInt64(addend)
  set length targetLength
  longerCheck: longer = compare.greaterThanInt64(addendLength, targetLength)
  if longer useAddend sum
:useAddend
  set length addendLength
  goto sum
:sum
  spanOf: span = math.addInt64(length, zero=0)
  goto eachLimb
:eachLimb loop=while max=span
  doneCheck: done = compare.greaterOrEqualInt64(at, length)
  if done finish addLimb
:addLimb in=eachLimb
  readTargetLimb: targetLimb = readLimb(target, at)
  readAddendLimb: addendLimb = readLimb(addend, at)
  sumLimbs: limbSum = math.addUInt64(targetLimb, addendLimb)
  sumCarry: total = math.addUInt64(limbSum, carry)
  lowOf: low = bits.andUInt64(total, limbMask)
  writeSum: writeLimb(target, at, low)
  carryOf: nextCarry = bits.shiftRightUInt64(total, thirtyTwo=32)
  set carry nextCarry
  advance: nextAt = math.addInt64(at, one=1)
  set at nextAt
  goto eachLimb
:finish
  carryCheck: carried = compare.notEqualUInt64(carry, zeroWide=0)
  if carried extend store
:extend
  longerLength: extended = math.addInt64(length, one)
  roomCheck: fits(extended)
  writeCarry: writeLimb(target, length, carry)
  set length extended
  goto store
:store
  storeLength: machine.storeInt64(target, length)
  return

op subtractNumber "Subtract a number from another in place: target becomes target less subtrahend, which is not larger"
  invariant subtractsExactly "The target becomes the exact difference when the subtrahend is not larger than it"
  input target machine.Address copied
  input subtrahend machine.Address copied
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let borrow UInt64 0 mut
  let base UInt64 4294967296
  let zeroWide UInt64 0
  let oneWide UInt64 1
:begin
  readTarget: length = machine.loadInt64(target)
  goto eachLimb
:eachLimb loop=while max=length
  doneCheck: done = compare.greaterOrEqualInt64(at, length)
  if done finish subtractLimb
:subtractLimb in=eachLimb
  readTargetLimb: targetLimb = readLimbRaw(target, at)
  readOther: otherLimb = readLimb(subtrahend, at)
  takeAway: owed = math.addUInt64(otherLimb, borrow)
  enoughCheck: enough = compare.greaterOrEqualUInt64(targetLimb, owed)
  if enough plain borrowed
:plain in=eachLimb
  difference: plainLimb = math.subtractUInt64(targetLimb, owed)
  writePlain: writeLimb(target, at, plainLimb)
  set borrow zeroWide
  goto nextLimb
:borrowed in=eachLimb
  lifted: liftedLimb = math.addUInt64(targetLimb, base)
  borrowedDifference: borrowedLimb = math.subtractUInt64(liftedLimb, owed)
  writeBorrowed: writeLimb(target, at, borrowedLimb)
  set borrow oneWide
  goto nextLimb
:nextLimb in=eachLimb
  advance: nextAt = math.addInt64(at, one=1)
  set at nextAt
  goto eachLimb
:finish
  trimIt: trim(target, length)
  return

op multiplySmall "Multiply a number in place by a factor below 2^32"
  invariant multipliesExactly "The number becomes the exact product, carrying into a new limb when it must"
  input number machine.Address copied
  input factor UInt64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let carry UInt64 0 mut
:begin
  readLength: length = machine.loadInt64(number)
  goto eachLimb
:eachLimb loop=while max=length
  doneCheck: done = compare.greaterOrEqualInt64(at, length)
  if done finish multiplyLimb
:multiplyLimb in=eachLimb
  readNumberLimb: limb = readLimbRaw(number, at)
  product: limbProduct = math.multiplyUInt64(limb, factor)
  withCarry: total = math.addUInt64(limbProduct, carry)
  lowOf: low = bits.andUInt64(total, limbMask)
  writeProduct: writeLimb(number, at, low)
  carryOf: nextCarry = bits.shiftRightUInt64(total, thirtyTwo=32)
  set carry nextCarry
  advance: nextAt = math.addInt64(at, one=1)
  set at nextAt
  goto eachLimb
:finish
  carryCheck: carried = compare.notEqualUInt64(carry, zeroWide=0)
  if carried extend settle
:extend
  longerLength: extended = math.addInt64(length, one)
  roomCheck: fits(extended)
  writeCarry: writeLimb(number, length, carry)
  storeLength: machine.storeInt64(number, extended)
  return
:settle
  trimIt: trim(number, length)
  return

op addSmall "Add a value below 2^32 to a number in place"
  invariant addsSmall "The number becomes the exact sum"
  input number machine.Address copied
  input value UInt64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let carry UInt64 0 mut
:begin
  set carry value
  readLength: length = machine.loadInt64(number)
  goto eachLimb
:eachLimb loop=while max=length
  carryCheck: noCarry = compare.equalUInt64(carry, zeroWide=0)
  doneCheck: atEnd = compare.greaterOrEqualInt64(at, length)
  stopCheck: stop = logic.or(noCarry, atEnd)
  if stop finish addLimb
:addLimb in=eachLimb
  readNumberLimb: limb = readLimbRaw(number, at)
  sumLimb: total = math.addUInt64(limb, carry)
  lowOf: low = bits.andUInt64(total, limbMask)
  writeSum: writeLimb(number, at, low)
  carryOf: nextCarry = bits.shiftRightUInt64(total, thirtyTwo=32)
  set carry nextCarry
  advance: nextAt = math.addInt64(at, one=1)
  set at nextAt
  goto eachLimb
:finish
  leftCheck: carried = compare.notEqualUInt64(carry, zeroWide)
  if carried extend done
:extend
  longerLength: extended = math.addInt64(length, one)
  roomCheck: fits(extended)
  writeCarry: writeLimb(number, length, carry)
  storeLength: machine.storeInt64(number, extended)
  return
:done
  return

op shiftLeft "Multiply a number in place by 2 to a power of bits, 0 or more"
  invariant shiftsLeft "The number becomes itself times 2 to the amount"
  input number machine.Address copied
  input amount Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  readLength: length = machine.loadInt64(number)
  emptyCheck: empty = compare.equalInt64(length, zero=0)
  if empty done shift
:shift
  limbsOf: limbShift = math.divideInt64(amount, thirtyTwo=32)
  bitsOf: bitShift = math.remainderInt64(amount, thirtyTwo)
  otherOf: otherShift = math.subtractInt64(thirtyTwo, bitShift)
  growOf: grown = math.addInt64(length, limbShift)
  newOf: newLength = math.addInt64(grown, one=1)
  roomCheck: fits(newLength)
  set at newLength
  goto eachLimb
:eachLimb loop=while max=newLength
  doneCheck: finished = compare.lessOrEqualInt64(at, zero)
  if finished settle moveLimb
:moveLimb in=eachLimb
  downOne: target = math.subtractInt64(at, one)
  highFrom: highPosition = math.subtractInt64(target, limbShift)
  lowFrom: lowPosition = math.subtractInt64(highPosition, one)
  readHigh: highLimb = readLimb(number, highPosition)
  readLow: lowLimb = readLimb(number, lowPosition)
  shiftHigh: highPart = bits.shiftLeftUInt64(highLimb, bitShift)
  shiftLow: lowPart = bits.shiftRightUInt64(lowLimb, otherShift)
  joinParts: joined = bits.orUInt64(highPart, lowPart)
  maskOf: limb = bits.andUInt64(joined, limbMask)
  writeMoved: writeLimb(number, target, limb)
  set at target
  goto eachLimb
:settle
  trimIt: trim(number, newLength)
  goto done
:done
  return

op shiftRightOne "Halve a number in place, dropping the bit it loses"
  invariant halves "The number becomes itself divided by 2, rounded down"
  input number machine.Address copied
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  readLength: length = machine.loadInt64(number)
  goto eachLimb
:eachLimb loop=while max=length
  doneCheck: done = compare.greaterOrEqualInt64(at, length)
  if done finish moveLimb
:moveLimb in=eachLimb
  readHere: limb = readLimbRaw(number, at)
  nextOf: nextPosition = math.addInt64(at, one=1)
  readNext: nextLimb = readLimb(number, nextPosition)
  halfOf: half = bits.shiftRightUInt64(limb, one)
  carryBit: lowBit = bits.andUInt64(nextLimb, oneWide=1)
  carryUp: carried = bits.shiftLeftUInt64(lowBit, thirtyOne=31)
  joinParts: joined = bits.orUInt64(half, carried)
  writeHalf: writeLimb(number, at, joined)
  set at nextPosition
  goto eachLimb
:finish
  trimIt: trim(number, length)
  return

op bitLength "How many bits a number takes: 0 for 0, otherwise one more than the position of its highest set bit"
  invariant countsBits "A number of n bits is at least 2^(n-1) and below 2^n"
  input number machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let count Int64 0 mut
  let top UInt64 0 mut
:begin
  readLength: length = machine.loadInt64(number)
  emptyCheck: empty = compare.equalInt64(length, zero=0)
  if empty giveZero measure
:giveZero
  return zero
:measure
  topOf: topPosition = math.subtractInt64(length, one=1)
  readTop: topLimb = readLimbRaw(number, topPosition)
  set top topLimb
  lowerBits: lower = math.multiplyInt64(topPosition, thirtyTwo=32)
  set count lower
  goto eachBit
:eachBit loop=while max=thirtyTwo
  doneCheck: done = compare.equalUInt64(top, zeroWide=0)
  if done finish countBit
:countBit in=eachBit
  halve: halved = bits.shiftRightUInt64(top, one)
  set top halved
  addBit: counted = math.addInt64(count, one)
  set count counted
  goto eachBit
:finish
  return count

op multiplyPowerOfTen "Multiply a number in place by 10 to a power, 0 or more"
  invariant scalesByTen "The number becomes itself times 10^power"
  input number machine.Address copied
  input power Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let left Int64 0 mut
  let factor UInt64 1 mut
  let billion UInt64 1000000000
  let ten UInt64 10
:begin
  set left power
  goto eachBillion
:eachBillion loop=while max=power
  bigCheck: big = compare.greaterOrEqualInt64(left, nine=9)
  if big byBillion rest
:byBillion in=eachBillion
  multiplyBillion: multiplySmall(number, billion)
  lessLeft: fewer = math.subtractInt64(left, nine)
  set left fewer
  goto eachBillion
:rest
  goto eachTen
:eachTen loop=while max=nine
  restCheck: more = compare.greaterThanInt64(left, zero=0)
  if more byTen finish
:byTen in=eachTen
  tenTimes: larger = math.multiplyUInt64(factor, ten)
  set factor larger
  lessTen: fewerTens = math.subtractInt64(left, one=1)
  set left fewerTens
  goto eachTen
:finish
  multiplyRest: multiplySmall(number, factor)
  return

op lowLimbs "A number's lowest 64 bits"
  invariant readsLow "Gives the number itself when it is below 2^64"
  input number machine.Address copied
  output UInt64
  effect use machine.memory
  uses memoryAccess
:begin
  readLow: low = readLimb(number, zero=0)
  readHigh: high = readLimb(number, one=1)
  shiftHigh: highPart = bits.shiftLeftUInt64(high, thirtyTwo=32)
  joinParts: joined = bits.orUInt64(highPart, low)
  return joined

@tests

## Tests keep their numbers in the last 4 KiB of machine.state, from byte 61440 (two numbers of 1,608 bytes).

op expectNumber "A number's lowest 64 bits and its length are what is expected"
  input number machine.Address copied
  input value UInt64 copied
  input limbs Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  readValue: low = lowLimbs(number)
  sameCheck: same = compare.equalUInt64(low, value)
  expectValue: test.assertTrue(same)
  readLength: length = machine.loadInt64(number)
  expectLength: test.assertEqualInt64(limbs, length)
  return

test arithmeticTest "Small values are set, added, subtracted, multiplied, shifted, compared, and measured exactly"
  verifies setSmall holdsValue
  verifies copyNumber copiesValue
  verifies isZero zeroHasNoLimbs
  verifies compareNumbers ordersNumbers
  verifies addNumber addsExactly
  verifies subtractNumber subtractsExactly
  verifies multiplySmall multipliesExactly
  verifies addSmall addsSmall
  verifies shiftLeft shiftsLeft
  verifies shiftRightOne halves
  verifies bitLength countsBits
  verifies multiplyPowerOfTen scalesByTen
  verifies lowLimbs readsLow
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findState: state = machine.state()
  findLeft: left = machine.offset(state, leftAt=61440)
  findRight: right = machine.offset(state, rightAt=63048)
  setLeft: setSmall(left, big=18446744073709551615)
  expectBig: expectNumber(left, big, two=2)
  setRight: setSmall(right, oneWide=1)
  addOne: addNumber(left, right)
  expectCarried: expectNumber(left, zeroWide=0, three=3)
  readBits: width = bitLength(left)
  expectWidth: test.assertEqualInt64(sixtyFive=65, width)
  orderCheck: order = compareNumbers(left, right)
  expectLarger: test.assertEqualInt64(one=1, order)
  backOrder: reverse = compareNumbers(right, left)
  expectSmaller: test.assertEqualInt64(minusOne=-1, reverse)
  takeOne: subtractNumber(left, right)
  expectBack: expectNumber(left, big, two)
  copyBack: copyNumber(right, left)
  sameOrder: same = compareNumbers(right, left)
  expectSame: test.assertEqualInt64(zero=0, same)
  subtractAll: subtractNumber(left, right)
  zeroCheck: empty = isZero(left)
  expectZero: test.assertTrue(empty)
  setTen: setSmall(left, tenWide=10)
  scale: multiplyPowerOfTen(left, eighteen=18)
  expectScaled: expectNumber(left, nineteenZeros=10000000000000000000, two)
  timesThree: multiplySmall(left, threeWide=3)
  readTripled: tripledWidth = bitLength(left)
  expectTripledWidth: test.assertEqualInt64(sixtyFive, tripledWidth)
  setSeven: setSmall(right, sevenWide=7)
  shiftUp: shiftLeft(right, hundred=100)
  readShifted: shiftedWidth = bitLength(right)
  expectShiftedWidth: test.assertEqualInt64(hundredThree=103, shiftedWidth)
  halve: shiftRightOne(right)
  readHalved: halvedWidth = bitLength(right)
  expectHalvedWidth: test.assertEqualInt64(hundredTwo=102, halvedWidth)
  setNine: setSmall(left, nineWide=9)
  addSome: addSmall(left, fourBillion=4294967295)
  expectAdded: expectNumber(left, sumWide=4294967304, two)
  readLow: low = lowLimbs(left)
  lowCheck: lowSame = compare.equalUInt64(low, sumWide)
  expectLow: test.assertTrue(lowSame)
  return

test powerTest "10^30 less 1 is thirty nines: carries and borrows run through every limb"
  verifies multiplyPowerOfTen scalesByTen
  verifies subtractNumber subtractsExactly
  verifies addSmall addsSmall
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findState: state = machine.state()
  findLeft: left = machine.offset(state, leftAt=61440)
  findRight: right = machine.offset(state, rightAt=63048)
  setOne: setSmall(left, oneWide=1)
  scale: multiplyPowerOfTen(left, thirty=30)
  setUnit: setSmall(right, oneWide)
  takeUnit: subtractNumber(left, right)
  readWidth: width = bitLength(left)
  expectWidth: test.assertEqualInt64(hundred=100, width)
  addBack: addSmall(left, oneWide)
  setPower: setSmall(right, oneWide)
  shiftPower: multiplyPowerOfTen(right, thirty)
  compareBack: order = compareNumbers(left, right)
  expectEqual: test.assertEqualInt64(zero=0, order)
  return
