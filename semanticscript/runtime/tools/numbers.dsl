module numbers "Write whole numbers as decimal text into memory, and read them back"
  path numbers
  imports standard.machine standard.string standard.math standard.compare standard.convert standard.logic standard.test
  exports formatDecimal parseDecimal

capability memoryAccess "Authority to write digits by address" use machine.memory none

op formatDecimal "Write a whole number as decimal text at an address: a minus sign when it is negative, then its digits with no leading zeros; gives how many bytes it wrote, at most 20"
  invariant writesDecimal "Writes the number as `refined run` prints it, `-` and digits with no leading zeros (0 is `0`), the most negative Int64 included, and gives the number of bytes written"
  input value Int64 copied
  input target machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let magnitude UInt64 0 mut
  let rest UInt64 0 mut
  let start Int64 0 mut
  let length Int64 0 mut
  let at Int64 0 mut
  let one Int64 1
  let twenty Int64 20
  let ten UInt64 10
  let zeroWide UInt64 0
:begin
  bitsOf: raw = convert.int64BitsToUInt64(value)
  set magnitude raw
  negativeCheck: negative = compare.lessThanInt64(value, zero=0)
  if negative sign count
:sign
  flip: flipped = math.wrappingSubtractUInt64(zeroWide, raw)
  set magnitude flipped
  writeMinus: machine.storeByte(target, minusSign=45)
  set start one
  goto count
:count
  firstDigit: afterFirst = math.divideUInt64(magnitude, ten)
  set rest afterFirst
  countFirst: withFirst = math.addInt64(start, one)
  set length withFirst
  goto eachDigit
:eachDigit loop=while max=twenty
  moreCheck: more = compare.greaterThanUInt64(rest, zeroWide)
  if more countDigit write
:countDigit in=eachDigit
  shrink: smaller = math.divideUInt64(rest, ten)
  set rest smaller
  grow: longer = math.addInt64(length, one)
  set length longer
  goto eachDigit
:write
  set at length
  set rest magnitude
  goto eachWrite
:eachWrite loop=while max=twenty
  writtenCheck: written = compare.lessOrEqualInt64(at, start)
  if written done writeDigit
:writeDigit in=eachWrite
  back: before = math.subtractInt64(at, one)
  set at before
  digitOf: digit = math.remainderUInt64(rest, ten)
  narrow: digitByte = convert.uint64ToByte(digit)
  toCharacter: character = math.addByte(digitByte, zeroCharacter=48)
  findPlace: place = machine.offset(target, before)
  writeCharacter: machine.storeByte(place, character)
  shrinkWritten: remaining = math.divideUInt64(rest, ten)
  set rest remaining
  goto eachWrite
:done
  return length

op isDigit "Whether a byte is an ASCII digit, 0 to 9"
  input value Byte copied
  output Bool
:begin
  lowCheck: aboveLow = compare.greaterOrEqualByte(value, zeroCharacter=48)
  highCheck: belowHigh = compare.lessOrEqualByte(value, nineCharacter=57)
  bothCheck: digit = logic.and(aboveLow, belowHigh)
  return digit

op parseDecimal "Read decimal text as a whole number into an address: 0 when it is one, 1 when it is not a number, 2 when it is out of the range of Int64; the number stored is 0 unless it is read: refined_parse_int"
  invariant readsDecimal "Accepts an optional `-` and one or more ASCII digits, as `refined run` does; any other text is not a number, even when it is also too long, and a number past Int64 is out of range"
  input text machine.Address copied
  input bytes Int64 copied
  input result machine.Address copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  let start Int64 0 mut
  let at Int64 0 mut
  let value UInt64 0 mut
  let limit UInt64 9223372036854775807 mut
  let mostNegative UInt64 9223372036854775808
  let negative Bool false mut
  let yes Bool true
  let one Int64 1
  let ten UInt64 10
  let parsed Int32 0
  let notNumber Int32 1
  let outOfRange Int32 2
  abi c "refined_parse_int"
:begin
  clear: machine.storeInt64(result, zero=0)
  emptyCheck: empty = compare.lessThanInt64(bytes, one)
  if empty refuse signCheck
:signCheck
  readFirst: first = machine.loadByte(text)
  minusCheck: minus = compare.equalByte(first, minusSign=45)
  if minus takeSign body
:takeSign
  set start one
  set negative yes
  set limit mostNegative
  goto body
:body
  bodyCheck: noDigits = compare.greaterOrEqualInt64(start, bytes)
  if noDigits refuse scan
:scan
  set at start
  goto eachByte
:eachByte loop=while max=bytes
  scannedCheck: scanned = compare.greaterOrEqualInt64(at, bytes)
  if scanned read checkByte
:checkByte in=eachByte
  findByte: place = machine.offset(text, at)
  readByte: byte = machine.loadByte(place)
  digitCheck: digit = isDigit(byte)
  if digit nextByte refuse
:nextByte in=eachByte
  advanceScan: afterByte = math.addInt64(at, one)
  set at afterByte
  goto eachByte
:read
  set at start
  goto eachDigit
:eachDigit loop=while max=bytes
  readCheck: done = compare.greaterOrEqualInt64(at, bytes)
  if done finish addDigit
:addDigit in=eachDigit
  findDigit: digitPlace = machine.offset(text, at)
  readDigit: character = machine.loadByte(digitPlace)
  toDigit: digitByte = math.subtractByte(character, zeroCharacter=48)
  widenDigit: digitValue = convert.byteToUInt64(digitByte)
  roomOf: room = math.subtractUInt64(limit, digitValue)
  mostOf: most = math.divideUInt64(room, ten)
  overCheck: over = compare.greaterThanUInt64(value, most)
  if over tooLarge accumulate
:accumulate in=eachDigit
  shiftUp: shifted = math.multiplyUInt64(value, ten)
  addOn: added = math.addUInt64(shifted, digitValue)
  set value added
  advanceRead: afterDigit = math.addInt64(at, one)
  set at afterDigit
  goto eachDigit
:finish
  if negative makeNegative makePositive
:makeNegative
  flip: flipped = math.wrappingSubtractUInt64(zeroWide=0, value)
  negativeBits: negativeValue = convert.uint64BitsToInt64(flipped)
  storeNegative: machine.storeInt64(result, negativeValue)
  return parsed
:makePositive
  positiveBits: positiveValue = convert.uint64BitsToInt64(value)
  storePositive: machine.storeInt64(result, positiveValue)
  return parsed
:refuse
  return notNumber
:tooLarge
  return outOfRange

@tests

## Tests write in the last 4 KiB of machine.state (from byte 61440), which the runtime's own state never reaches.

op expectDecimal "Format a number in the tests' scratch bytes and compare the text with what is expected"
  input value Int64 copied
  input expected String borrowed
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  findScratch: scratch = machine.offset(state, scratchAt=61440)
  format: length = formatDecimal(value, scratch)
  viewText: text = machine.stringAt(scratch, length)
  expectText: test.assertEqualString(expected, text)
  return

test formatDecimalTest "Numbers are written as `refined run` prints them"
  verifies formatDecimal writesDecimal
  effect use machine.memory
  uses memoryAccess
:begin
  formatZero: expectDecimal(zero=0, zeroText="0")
  formatSmall: expectDecimal(seven=7, sevenText="7")
  formatLarge: expectDecimal(large=1234567890, largeText="1234567890")
  formatNegative: expectDecimal(minusTwelve=-12, minusTwelveText="-12")
  formatMost: expectDecimal(most=9223372036854775807, mostText="9223372036854775807")
  formatLeast: expectDecimal(least=-9223372036854775808, leastText="-9223372036854775808")
  findState: state = machine.state()
  findScratch: scratch = machine.offset(state, scratchAt=61440)
  countLeast: leastLength = formatDecimal(least, scratch)
  expectLength: test.assertEqualInt64(twenty=20, leastLength)
  return

op expectRead "Read a text, the number going to the tests' scratch bytes, and compare the status and the number with what is expected"
  input text String borrowed
  input status Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  findScratch: scratch = machine.offset(state, scratchAt=61440)
  findText: textAt = machine.addressOfString(text)
  measure: bytes = string.byteLength(text)
  parse: got = parseDecimal(textAt, bytes, scratch)
  widenStatus: gotStatus = convert.int32ToInt64(got)
  expectStatus: test.assertEqualInt64(status, gotStatus)
  readValue: gotValue = machine.loadInt64(scratch)
  expectValue: test.assertEqualInt64(value, gotValue)
  return

test parseDecimalTest "Decimal text is read as `refined run` reads it"
  verifies parseDecimal readsDecimal
  effect use machine.memory
  uses memoryAccess
:begin
  checkZero: expectRead(zeroText="0", parsedStatus=0, zero=0)
  checkNegative: expectRead(negativeText="-42", parsedStatus, minusFortyTwo=-42)
  checkMost: expectRead(mostText="9223372036854775807", parsedStatus, most=9223372036854775807)
  checkLeast: expectRead(leastText="-9223372036854775808", parsedStatus, least=-9223372036854775808)
  checkPast: expectRead(pastText="9223372036854775808", rangeStatus=2, zero)
  checkPastLeast: expectRead(pastLeastText="-9223372036854775809", rangeStatus, zero)
  checkEmpty: expectRead(emptyText="", notNumberStatus=1, zero)
  checkSign: expectRead(signText="-", notNumberStatus, zero)
  checkPlus: expectRead(plusText="+1", notNumberStatus, zero)
  checkSpace: expectRead(spaceText=" 1", notNumberStatus, zero)
  checkLongWord: expectRead(longWordText="99999999999999999999x", notNumberStatus, zero)
  findState: state = machine.state()
  findScratch: scratch = machine.offset(state, scratchAt=61440)
  findText: textAt = machine.addressOfString(mostText)
  parseDirect: got = parseDecimal(textAt, nineteen=19, scratch)
  widenGot: gotStatus = convert.int32ToInt64(got)
  expectDirect: test.assertEqualInt64(parsedStatus, gotStatus)
  return
