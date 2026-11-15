module floats "Floating-point numbers as text and text as floating-point numbers, exactly as `refined run` writes and reads them (D-125, D-129)"
  path floats
  imports standard.machine standard.string standard.math standard.compare standard.convert standard.bits standard.logic standard.test numbers output regions bignum
  exports formatFloat parseFloat

capability memoryAccess "Authority to keep the numbers and digits of a conversion in machine.state and to write text by address" use machine.memory none

capability systemCalls "Authority to write a number to standard output or standard error and to take a region's memory" use system.calls none

## machine.state bytes 40960 to 49151 belong to this module: five numbers of the bignum module (1,608 bytes each)
## from 40960, a float's digits at 49008, its text at 49040, and what reading text found at 49104 (how many
## significant digits) and 49112 (the bits of the result).
## Writing a Float64 is Python's repr, which `refined run` uses: the shortest digits that read back as the same
## value, the nearest of them to it, an exact tie going to the even digit (Steele and White's free-format method as
## Burger and Dybvig give it, computed exactly with bignums); laid out with an exponent (`1e+16`, `1.5e-07`) when
## the decimal point is 4 or more places left of the first digit or more than 16 right of it, and otherwise as
## digits with a point and at least one digit after it (`100.0`, `0.001`); `nan`, `inf`, and `-inf` for the rest.
## Reading text is correctly rounded, ties to even, as strtod and Python read it: the significand's digits (at
## most 800 kept, and one more standing for any that are dropped and not zero) over a power of ten, divided
## exactly to 54 bits and a remainder.
constant numbersAt "Where the five numbers start, in machine.state" Int64 40960

constant digitsAt "Where a float's digits are put, in machine.state" Int64 49008

constant textAt "Where a float's text is put together, in machine.state" Int64 49040

constant keptAt "Where reading text leaves how many significant digits it kept, in machine.state" Int64 49104

constant bitsAt "Where reading text leaves the bits of the result, in machine.state" Int64 49112

constant numberBytes "The bytes of one of the bignum module's numbers" Int64 1608

constant mostKept "How many significant digits of a text are kept exactly; more than any double's halfway point needs" Int64 800

## ---------------------------------------------------------------- helpers

op numberAt "The address of one of the module's five numbers, 0 to 4"
  input slot Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  bytesOf: offset = math.multiplyInt64(slot, numberBytes)
  startOf: start = math.addInt64(numbersAt, offset)
  findNumber: number = machine.offset(state, start)
  return number

op stateAt "The address of a byte of machine.state"
  input offset Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  findPlace: place = machine.offset(state, offset)
  return place

op putByte "Write a byte at a position of a text and give the position after it"
  input target machine.Address copied
  input at Int64 copied
  input value Byte copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findPlace: place = machine.offset(target, at)
  storeIt: machine.storeByte(place, value)
  advance: after = math.addInt64(at, one=1)
  return after

op putRange "Copy bytes to a position of a text and give the position after them"
  input target machine.Address copied
  input at Int64 copied
  input source machine.Address copied
  input bytes Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findPlace: place = machine.offset(target, at)
  copyIt: machine.copy(place, source, bytes)
  advance: after = math.addInt64(at, bytes)
  return after

op putZeros "Write a number of `0` digits at a position of a text and give the position after them"
  input target machine.Address copied
  input at Int64 copied
  input count Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findPlace: place = machine.offset(target, at)
  fillIt: machine.fill(place, zeroDigit=48, count)
  advance: after = math.addInt64(at, count)
  return after

op widthOf "How many bits a 64-bit value takes: 0 for 0"
  input value UInt64 copied
  output Int64
  let rest UInt64 0 mut
  let count Int64 0 mut
  let sixtyFour Int64 64
:begin
  set rest value
  goto eachBit
:eachBit loop=while max=sixtyFour
  doneCheck: done = compare.equalUInt64(rest, zeroWide=0)
  if done finish countBit
:countBit in=eachBit
  halve: halved = bits.shiftRightUInt64(rest, one=1)
  set rest halved
  addBit: counted = math.addInt64(count, one)
  set count counted
  goto eachBit
:finish
  return count

op beyond "Whether a comparison (-1, 0, 1) is past a bound: above it, or at it when the bound is included"
  input order Int64 copied
  input included Bool copied
  output Bool
:begin
  aboveCheck: above = compare.greaterThanInt64(order, zero=0)
  atCheck: at = compare.equalInt64(order, zero)
  atIncluded: atBound = logic.and(at, included)
  eitherCheck: past = logic.or(above, atBound)
  return past

## ---------------------------------------------------------------- writing: the shortest digits

op shortestDigits "The shortest digits that read back as f times 2^e, the nearest to it, ties to the even digit, as ASCII at an address with their count stored at another; gives the decimal exponent k, the value being 0.d1d2... times 10^k"
  input f UInt64 copied
  input e Int64 copied
  input digits machine.Address copied
  input countAt machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let k Int64 0 mut
  let count Int64 0 mut
  let digit Int64 0 mut
  let hiddenBit UInt64 4503599627370496
  let leastExponent Int64 -1074
  let tenWide UInt64 10
  let eight Int64 8
  let twenty Int64 20
  let ten Int64 10
:begin
  findR: r = numberAt(zero=0)
  findS: s = numberAt(one=1)
  findPlus: plus = numberAt(two=2)
  findMinus: minus = numberAt(three=3)
  findT: t = numberAt(four=4)
  lowBitOf: lowBit = bits.andUInt64(f, oneWide=1)
  evenCheck: even = compare.equalUInt64(lowBit, zeroWide=0)
  powerCheck: isPower = compare.equalUInt64(f, hiddenBit)
  normalCheck: aboveLeast = compare.greaterThanInt64(e, leastExponent)
  unequalCheck: unequal = logic.and(isPower, aboveLeast)
  setR: bignum.setSmall(r, f)
  signCheck: nonNegative = compare.greaterOrEqualInt64(e, zero)
  if nonNegative positiveExponent negativeExponent
:positiveExponent
  if unequal positiveUnequal positiveEqual
:positiveEqual
  rShift: rBits = math.addInt64(e, one)
  shiftR: bignum.shiftLeft(r, rBits)
  setS: bignum.setSmall(s, twoWide=2)
  setPlus: bignum.setSmall(plus, oneWide)
  shiftPlus: bignum.shiftLeft(plus, e)
  copyMinus: bignum.copyNumber(minus, plus)
  goto estimate
:positiveUnequal
  rShiftWide: rBitsWide = math.addInt64(e, two)
  shiftRWide: bignum.shiftLeft(r, rBitsWide)
  setSWide: bignum.setSmall(s, fourWide=4)
  setPlusWide: bignum.setSmall(plus, oneWide)
  plusShift: plusBits = math.addInt64(e, one)
  shiftPlusWide: bignum.shiftLeft(plus, plusBits)
  setMinusWide: bignum.setSmall(minus, oneWide)
  shiftMinusWide: bignum.shiftLeft(minus, e)
  goto estimate
:negativeExponent
  if unequal negativeUnequal negativeEqual
:negativeEqual
  shiftRNegative: bignum.shiftLeft(r, one)
  setSNegative: bignum.setSmall(s, oneWide)
  sShift: sBits = math.subtractInt64(one, e)
  shiftSNegative: bignum.shiftLeft(s, sBits)
  setPlusNegative: bignum.setSmall(plus, oneWide)
  setMinusNegative: bignum.setSmall(minus, oneWide)
  goto estimate
:negativeUnequal
  shiftRBoth: bignum.shiftLeft(r, two)
  setSBoth: bignum.setSmall(s, oneWide)
  sShiftBoth: sBitsBoth = math.subtractInt64(two, e)
  shiftSBoth: bignum.shiftLeft(s, sBitsBoth)
  setPlusBoth: bignum.setSmall(plus, twoWide)
  setMinusBoth: bignum.setSmall(minus, oneWide)
  goto estimate
:estimate
  widthOfF: width = widthOf(f)
  topBit: below = math.subtractInt64(width, one)
  logTwo: lowLog = math.addInt64(below, e)
  scaleLog: scaled = math.multiplyInt64(lowLog, log10Of2=78913)
  shiftLog: guess = bits.shiftRightInt64(scaled, eighteen=18)
  lowerGuess: estimated = math.subtractInt64(guess, one)
  set k estimated
  scaleCheck: upward = compare.greaterOrEqualInt64(k, zero)
  if upward scaleS scaleR
:scaleS
  scaleDenominator: bignum.multiplyPowerOfTen(s, k)
  goto fixup
:scaleR
  negateK: power = math.negateInt64(k)
  scaleNumerator: bignum.multiplyPowerOfTen(r, power)
  scalePlus: bignum.multiplyPowerOfTen(plus, power)
  scaleMinus: bignum.multiplyPowerOfTen(minus, power)
  goto fixup
:fixup loop=while max=eight
  copyHigh: bignum.copyNumber(t, r)
  addHigh: bignum.addNumber(t, plus)
  orderHigh: highOrder = bignum.compareNumbers(t, s)
  highCheck: tooLow = beyond(highOrder, even)
  if tooLow raise generate
:raise in=fixup
  raiseS: bignum.multiplySmall(s, tenWide)
  raiseK: raised = math.addInt64(k, one)
  set k raised
  goto fixup
:generate loop=while max=twenty
  roomCheck: room = compare.lessThanInt64(count, twenty)
  if room step lowDone
:step in=generate
  timesTenR: bignum.multiplySmall(r, tenWide)
  timesTenPlus: bignum.multiplySmall(plus, tenWide)
  timesTenMinus: bignum.multiplySmall(minus, tenWide)
  set digit zero
  goto eachSubtract
:eachSubtract loop=while max=ten in=generate
  orderDigit: digitOrder = bignum.compareNumbers(r, s)
  subtractCheck: canSubtract = compare.greaterOrEqualInt64(digitOrder, zero)
  if canSubtract subtractOnce tests
:subtractOnce in=eachSubtract
  takeS: bignum.subtractNumber(r, s)
  countDigit: nextDigit = math.addInt64(digit, one)
  set digit nextDigit
  goto eachSubtract
:tests in=generate
  orderLow: lowOrder = bignum.compareNumbers(minus, r)
  lowCheck: lowClose = beyond(lowOrder, even)
  copyRest: bignum.copyNumber(t, r)
  addRest: bignum.addNumber(t, plus)
  orderRest: restOrder = bignum.compareNumbers(t, s)
  highNearCheck: highClose = beyond(restOrder, even)
  if lowClose lowEnds onlyHigh
:onlyHigh in=generate
  if highClose highDone emit
:emit in=generate
  digitByte: emitted = convert.int64ToByte(digit)
  digitCharacter: character = math.addByte(emitted, zeroCharacter=48)
  findDigit: place = machine.offset(digits, count)
  storeDigit: machine.storeByte(place, character)
  moreDigits: counted = math.addInt64(count, one)
  set count counted
  goto generate
:lowEnds
  if highClose both lowDone
:both
  copyTwice: bignum.copyNumber(t, r)
  doubleRest: bignum.shiftLeft(t, one)
  orderHalf: halfOrder = bignum.compareNumbers(t, s)
  belowHalf: lower = compare.lessThanInt64(halfOrder, zero)
  if lower lowDone halfCheck
:halfCheck
  aboveHalf: higher = compare.greaterThanInt64(halfOrder, zero)
  if higher highDone tie
:tie
  parityOf: parity = math.remainderInt64(digit, two)
  oddCheck: odd = compare.equalInt64(parity, one)
  if odd highDone lowDone
:highDone
  bumpDigit: bumped = math.addInt64(digit, one)
  set digit bumped
  goto lowDone
:lowDone
  lastByte: lastEmitted = convert.int64ToByte(digit)
  lastCharacter: lastChar = math.addByte(lastEmitted, zeroCharacter)
  findLast: lastPlace = machine.offset(digits, count)
  storeLast: machine.storeByte(lastPlace, lastChar)
  finalCount: total = math.addInt64(count, one)
  storeCount: machine.storeInt64(countAt, total)
  return k

## ---------------------------------------------------------------- writing: the layout

op layout "Lay digits out as Python's repr does, at a position of a text, and give the position after them: with an exponent when the decimal exponent is -4 or less or above 16, otherwise with a point"
  input target machine.Address copied
  input start Int64 copied
  input digits machine.Address copied
  input count Int64 copied
  input point Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let power Int64 0 mut
  let sixteen Int64 16
  let minusFour Int64 -4
  let dot Byte 46
  let zeroByte Byte 48
:begin
  set at start
  smallCheck: small = compare.lessOrEqualInt64(point, minusFour)
  largeCheck: large = compare.greaterThanInt64(point, sixteen)
  exponentCheck: useExponent = logic.or(small, large)
  if useExponent exponentForm fixedForm
:exponentForm
  firstDigit: afterFirst = putRange(target, at, digits, one=1)
  set at afterFirst
  moreCheck: more = compare.greaterThanInt64(count, one)
  if more fraction exponent
:fraction
  writeDot: afterDot = putByte(target, at, dot)
  findRest: rest = machine.offset(digits, one)
  restCount: restBytes = math.subtractInt64(count, one)
  writeRest: afterRest = putRange(target, afterDot, rest, restBytes)
  set at afterRest
  goto exponent
:exponent
  writeE: afterE = putByte(target, at, letterE=101)
  set at afterE
  powerOf: decimalPower = math.subtractInt64(point, one)
  set power decimalPower
  negativeCheck: negative = compare.lessThanInt64(decimalPower, zero=0)
  if negative minusSign plusSign
:minusSign
  writeMinus: afterMinus = putByte(target, at, minusByte=45)
  set at afterMinus
  flip: flipped = math.negateInt64(decimalPower)
  set power flipped
  goto twoDigits
:plusSign
  writePlus: afterPlus = putByte(target, at, plusByte=43)
  set at afterPlus
  goto twoDigits
:twoDigits
  oneDigitCheck: oneDigit = compare.lessThanInt64(power, ten=10)
  if oneDigit leadingZero powerDigits
:leadingZero
  writeLeading: afterLeading = putByte(target, at, zeroByte)
  set at afterLeading
  goto powerDigits
:powerDigits
  findPower: powerAt = machine.offset(target, at)
  writePower: powerBytes = numbers.formatDecimal(power, powerAt)
  afterPower: ended = math.addInt64(at, powerBytes)
  return ended
:fixedForm
  leadCheck: noWhole = compare.lessOrEqualInt64(point, zero)
  if noWhole leadingFraction wholeDigits
:leadingFraction
  writeZero: afterZero = putByte(target, at, zeroByte)
  writePoint: afterPoint = putByte(target, afterZero, dot)
  zerosOf: zeros = math.negateInt64(point)
  writeZeros: afterZeros = putZeros(target, afterPoint, zeros)
  writeAll: afterAll = putRange(target, afterZeros, digits, count)
  return afterAll
:wholeDigits
  insideCheck: inside = compare.lessThanInt64(point, count)
  if inside splitDigits trailingZeros
:splitDigits
  writeWhole: afterWhole = putRange(target, at, digits, point)
  writeSplit: afterSplit = putByte(target, afterWhole, dot)
  findFraction: fractionAt = machine.offset(digits, point)
  fractionCount: fractionBytes = math.subtractInt64(count, point)
  writeFraction: afterFraction = putRange(target, afterSplit, fractionAt, fractionBytes)
  return afterFraction
:trailingZeros
  writeDigits: afterDigits = putRange(target, at, digits, count)
  zerosNeeded: padding = math.subtractInt64(point, count)
  writePadding: afterPadding = putZeros(target, afterDigits, padding)
  writeTailDot: afterTailDot = putByte(target, afterPadding, dot)
  writeTailZero: afterTail = putByte(target, afterTailDot, zeroByte)
  return afterTail

op formatFloat "Write a Float64 as `refined run` writes it (Python's repr) at an address and give the number of bytes, at most 24"
  invariant writesRepr "The text is the shortest that reads back as the value, laid out as Python's repr: `0.1`, `100.0`, `1e+16`, `5e-324`, `-0.0`, `nan`, `inf`, `-inf`"
  input value Float64 copied
  input target machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let f UInt64 0 mut
  let e Int64 0 mut
  let fractionMask UInt64 4503599627370495
  let exponentMask UInt64 2047
  let hiddenBit UInt64 4503599627370496
  let nanText String "nan"
  let infinityText String "inf"
  let negativeInfinityText String "-inf"
  let zeroText String "0.0"
  let leastExponent Int64 -1074
:begin
  bitsOf: raw = convert.float64BitsToUInt64(value)
  signOf: signBit = bits.shiftRightUInt64(raw, sixtyThree=63)
  negativeCheck: negative = compare.notEqualUInt64(signBit, zeroWide=0)
  exponentShift: shifted = bits.shiftRightUInt64(raw, fiftyTwo=52)
  exponentOf: field = bits.andUInt64(shifted, exponentMask)
  fractionOf: fraction = bits.andUInt64(raw, fractionMask)
  specialCheck: special = compare.equalUInt64(field, exponentMask)
  if special specialValue sign
:specialValue
  nanCheck: isNan = compare.notEqualUInt64(fraction, zeroWide)
  if isNan writeNan infinity
:writeNan
  findNan: nanAt = machine.addressOfString(nanText)
  nanWritten: nanEnd = putRange(target, zero=0, nanAt, three=3)
  return nanEnd
:infinity
  if negative writeNegativeInfinity writeInfinity
:writeNegativeInfinity
  findNegative: negativeAt = machine.addressOfString(negativeInfinityText)
  negativeWritten: negativeEnd = putRange(target, zero, negativeAt, four=4)
  return negativeEnd
:writeInfinity
  findInfinity: infinityAt = machine.addressOfString(infinityText)
  infinityWritten: infinityEnd = putRange(target, zero, infinityAt, three)
  return infinityEnd
:sign
  if negative writeSign zeroCheck
:writeSign
  signWritten: afterSign = putByte(target, zero, minusByte=45)
  set at afterSign
  goto zeroCheck
:zeroCheck
  zeroFieldCheck: zeroField = compare.equalUInt64(field, zeroWide)
  zeroFractionCheck: zeroFraction = compare.equalUInt64(fraction, zeroWide)
  bothZero: isZero = logic.and(zeroField, zeroFraction)
  if isZero writeZero split
:writeZero
  findZero: zeroAt = machine.addressOfString(zeroText)
  zeroWritten: zeroEnd = putRange(target, at, zeroAt, three)
  return zeroEnd
:split
  if zeroField subnormal normal
:subnormal
  set f fraction
  set e leastExponent
  goto digitsOf
:normal
  withHidden: full = bits.orUInt64(fraction, hiddenBit)
  set f full
  fieldWide: fieldValue = convert.uint64ToInt64(field)
  unbias: unbiased = math.subtractInt64(fieldValue, bias=1075)
  set e unbiased
  goto digitsOf
:digitsOf
  findDigits: digits = stateAt(digitsAt)
  findCount: countAt = stateAt(keptAt)
  shortest: point = shortestDigits(f, e, digits, countAt)
  readCount: count = machine.loadInt64(countAt)
  lay: ended = layout(target, at, digits, count, point)
  return ended

op formatFloatInRegion "A Float64 as `refined run` writes it, in a block of a region; its length is stored at an address: refined_format_float"
  invariant formatsIntoRegion "The text is the value's repr, in a block of the region, and its length is stored at the address given"
  input value Float64 copied
  input region machine.Address copied
  input lengthAt machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_format_float"
:begin
  findText: text = stateAt(textAt)
  format: length = formatFloat(value, text)
  take: block = regions.allocate(region, length)
  copyText: machine.copy(block, text, length)
  storeLength: machine.storeInt64(lengthAt, length)
  return block

op writeFloat "Write a Float64 as `refined run` writes it to standard output (stream 1) or standard error (stream 2), then a line end when asked; gives 0, or the system's error code: refined_write_float"
  invariant writesReprLine "Writes the value's repr, then one `\\n` byte when `newline` is not 0, in one write"
  input stream Int32 copied
  input value Float64 copied
  input newline Int32 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_write_float"
  let length Int64 0 mut
:begin
  findText: text = stateAt(textAt)
  format: written = formatFloat(value, text)
  set length written
  wantLine: wanted = compare.notEqualInt32(newline, ok=0)
  if wanted addLine write
:addLine
  withLine: lineLength = putByte(text, written, lineEnd=10)
  set length lineLength
  goto write
:write
  findHandle: handle = output.standardHandle(stream)
  writeText: status = output.writeAll(handle, text, length)
  return status

## ---------------------------------------------------------------- reading

op isDigitByte "Whether a byte is an ASCII digit, 0 to 9"
  input value Byte copied
  output Bool
:begin
  lowCheck: aboveLow = compare.greaterOrEqualByte(value, zeroCharacter=48)
  highCheck: belowHigh = compare.lessOrEqualByte(value, nineCharacter=57)
  bothCheck: digit = logic.and(aboveLow, belowHigh)
  return digit

op digitAt "Whether the byte at a position of a text is an ASCII digit; a position past the end is not"
  input text machine.Address copied
  input bytes Int64 copied
  input at Int64 copied
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
  findByte: place = machine.offset(text, at)
  readByte: byte = machine.loadByte(place)
  digitCheck: digit = isDigitByte(byte)
  return digit

op byteIs "Whether the byte at a position of a text is a given byte; a position past the end is not"
  input text machine.Address copied
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
  findByte: place = machine.offset(text, at)
  readByte: byte = machine.loadByte(place)
  sameCheck: same = compare.equalByte(byte, wanted)
  return same

op skipDigits "The position after the run of ASCII digits that starts at a position"
  input text machine.Address copied
  input bytes Int64 copied
  input start Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  set at start
  goto eachDigit
:eachDigit loop=while max=bytes
  digitCheck: digit = digitAt(text, bytes, at)
  if digit nextDigit done
:nextDigit in=eachDigit
  advance: after = math.addInt64(at, one=1)
  set at after
  goto eachDigit
:done
  return at

op validText "Whether a text is a number as `refined run` reads one: `-`? digits (`.` digits)? ([eE] [+-]? digits)?, nothing else"
  input text machine.Address copied
  input bytes Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let yes Bool true
  let no Bool false
  let one Int64 1
:begin
  minusCheck: minus = byteIs(text, bytes, zero=0, minusByte=45)
  if minus skipMinus whole
:skipMinus
  set at one
  goto whole
:whole
  skipWhole: afterWhole = skipDigits(text, bytes, at)
  wholeCheck: noWhole = compare.equalInt64(afterWhole, at)
  if noWhole refuse pointCheck
:pointCheck
  set at afterWhole
  dotCheck: dot = byteIs(text, bytes, at, dotByte=46)
  if dot fraction exponentCheck
:fraction
  afterDot: fractionStart = math.addInt64(at, one)
  skipFraction: afterFraction = skipDigits(text, bytes, fractionStart)
  fractionCheck: noFraction = compare.equalInt64(afterFraction, fractionStart)
  if noFraction refuse fractionDone
:fractionDone
  set at afterFraction
  goto exponentCheck
:exponentCheck
  lowerCheck: lowerE = byteIs(text, bytes, at, lowerByte=101)
  upperCheck: upperE = byteIs(text, bytes, at, upperByte=69)
  eitherCheck: exponent = logic.or(lowerE, upperE)
  if exponent exponentSign ending
:exponentSign
  afterE: signAt = math.addInt64(at, one)
  set at signAt
  plusCheck: plus = byteIs(text, bytes, signAt, plusByte=43)
  minusSignCheck: minusSign = byteIs(text, bytes, signAt, minusByte)
  signCheck: signed = logic.or(plus, minusSign)
  if signed skipSign exponentDigits
:skipSign
  afterSign: digitsStart = math.addInt64(signAt, one)
  set at digitsStart
  goto exponentDigits
:exponentDigits
  skipExponent: afterExponent = skipDigits(text, bytes, at)
  exponentDigitsCheck: noExponent = compare.equalInt64(afterExponent, at)
  if noExponent refuse exponentDone
:exponentDone
  set at afterExponent
  goto ending
:ending
  endCheck: atEnd = compare.equalInt64(at, bytes)
  if atEnd accept refuse
:accept
  return yes
:refuse
  return no

op significand "Read a valid text's significant digits into a number (at most 800 exactly, and a last 1 standing for any dropped that are not zero); stores how many it kept and gives the power of ten the number is to be multiplied by"
  input text machine.Address copied
  input bytes Int64 copied
  input number machine.Address copied
  input keptTarget machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let kept Int64 0 mut
  let dropped Int64 0 mut
  let fractionDigits Int64 0 mut
  let inFraction Bool false mut
  let sticky Bool false mut
  let chunk UInt64 0 mut
  let chunkDigits Int64 0 mut
  let power Int64 0 mut
  let exponent Int64 0 mut
  let exponentNegative Bool false mut
  let yes Bool true
  let saturated Int64 1000000000000000
  let one Int64 1
  let zero Int64 0
  let zeroWide UInt64 0
:begin
  clearNumber: bignum.setSmall(number, zeroWide)
  minusCheck: minus = byteIs(text, bytes, zero, minusByte=45)
  if minus skipMinus eachByte
:skipMinus
  set at one
  goto eachByte
:eachByte loop=while max=bytes
  endCheck: atEnd = compare.greaterOrEqualInt64(at, bytes)
  if atEnd flush readByte
:readByte in=eachByte
  findByte: place = machine.offset(text, at)
  loadIt: byte = machine.loadByte(place)
  dotCheck: dot = compare.equalByte(byte, dotByte=46)
  if dot startFraction digitCheck
:startFraction in=eachByte
  set inFraction yes
  goto nextByte
:digitCheck in=eachByte
  isDigitCheck: digit = isDigitByte(byte)
  if digit useDigit exponentStart
:useDigit in=eachByte
  if inFraction countFraction significant
:countFraction in=eachByte
  moreFraction: fractionMore = math.addInt64(fractionDigits, one)
  set fractionDigits fractionMore
  goto significant
:significant in=eachByte
  valueOf: digitByte = math.subtractByte(byte, zeroCharacter=48)
  widenDigit: digitValue = convert.byteToUInt64(digitByte)
  noneKept: noneYet = compare.equalInt64(kept, zero)
  zeroDigitCheck: zeroDigit = compare.equalUInt64(digitValue, zeroWide)
  leadingCheck: leading = logic.and(noneYet, zeroDigit)
  if leading nextByte roomCheck
:roomCheck in=eachByte
  roomOf: room = compare.lessThanInt64(kept, mostKept)
  if room keep drop
:keep in=eachByte
  shiftChunk: shiftedChunk = math.multiplyUInt64(chunk, tenWide=10)
  addDigit: grownChunk = math.addUInt64(shiftedChunk, digitValue)
  set chunk grownChunk
  moreChunk: chunkMore = math.addInt64(chunkDigits, one)
  set chunkDigits chunkMore
  moreKept: keptMore = math.addInt64(kept, one)
  set kept keptMore
  fullCheck: full = compare.equalInt64(chunkMore, nine=9)
  if full flushChunk nextByte
:flushChunk in=eachByte
  scaleChunk: bignum.multiplyPowerOfTen(number, nine)
  addChunk: bignum.addSmall(number, chunk)
  set chunk zeroWide
  set chunkDigits zero
  goto nextByte
:drop in=eachByte
  moreDropped: droppedMore = math.addInt64(dropped, one)
  set dropped droppedMore
  if zeroDigit nextByte markSticky
:markSticky in=eachByte
  set sticky yes
  goto nextByte
:nextByte in=eachByte
  advance: after = math.addInt64(at, one)
  set at after
  goto eachByte
:exponentStart
  afterE: signAt = math.addInt64(at, one)
  set at signAt
  negativeCheck: negativeSign = byteIs(text, bytes, signAt, minusByte)
  plusCheck: plusSign = byteIs(text, bytes, signAt, plusByte=43)
  if negativeSign negativeExponent plusCheckStep
:negativeExponent
  set exponentNegative yes
  skipNegative: afterNegative = math.addInt64(signAt, one)
  set at afterNegative
  goto eachExponent
:plusCheckStep
  if plusSign skipPlus eachExponent
:skipPlus
  skipPlusSign: afterPlus = math.addInt64(signAt, one)
  set at afterPlus
  goto eachExponent
:eachExponent loop=while max=bytes
  exponentEnd: exponentDone = compare.greaterOrEqualInt64(at, bytes)
  if exponentDone signExponent exponentDigit
:exponentDigit in=eachExponent
  findExponentByte: exponentPlace = machine.offset(text, at)
  loadExponentByte: exponentByte = machine.loadByte(exponentPlace)
  exponentValueOf: exponentDigitByte = math.subtractByte(exponentByte, zeroCharacter)
  widenExponent: exponentDigitValue = convert.byteToInt64(exponentDigitByte)
  saturationCheck: below = compare.lessThanInt64(exponent, saturated)
  if below growExponent nextExponent
:growExponent in=eachExponent
  shiftExponent: shiftedExponent = math.multiplyInt64(exponent, ten=10)
  addExponent: grownExponent = math.addInt64(shiftedExponent, exponentDigitValue)
  set exponent grownExponent
  goto nextExponent
:nextExponent in=eachExponent
  advanceExponent: afterExponent = math.addInt64(at, one)
  set at afterExponent
  goto eachExponent
:signExponent
  if exponentNegative flipExponent flush
:flipExponent
  flipped: negated = math.negateInt64(exponent)
  set exponent negated
  goto flush
:flush
  partCheck: part = compare.greaterThanInt64(chunkDigits, zero)
  if part flushPart stickyCheck
:flushPart
  scalePart: bignum.multiplyPowerOfTen(number, chunkDigits)
  addPart: bignum.addSmall(number, chunk)
  goto stickyCheck
:stickyCheck
  lessFraction: withoutFraction = math.subtractInt64(exponent, fractionDigits)
  withDropped: powerOf = math.addInt64(withoutFraction, dropped)
  set power powerOf
  if sticky addSticky finish
:addSticky
  scaleSticky: bignum.multiplySmall(number, tenWide)
  addOne: bignum.addSmall(number, oneWide=1)
  keptSticky: keptWithSticky = math.addInt64(kept, one)
  set kept keptWithSticky
  lowerPower: stickyPower = math.subtractInt64(power, one)
  set power stickyPower
  goto finish
:finish
  storeKept: machine.storeInt64(keptTarget, kept)
  return power

op toBits "The bits of the double nearest the number in the module's first number times 10 to a power, ties to even, signed; 0 when it is a double, 2 when it is too large for one; the bits are stored at an address"
  input negative Bool copied
  input kept Int64 copied
  input power Int64 copied
  input bitsTarget machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let shift Int64 0 mut
  let quotient UInt64 0 mut
  let mantissa UInt64 0 mut
  let exponent Int64 0 mut
  let result UInt64 0 mut
  let subnormal Bool false mut
  let yes Bool true
  let round Int64 0 mut
  let parsed Int32 0
  let tooLarge Int32 2
  let signBit UInt64 9223372036854775808
  let hiddenBit UInt64 4503599627370496
  let carried UInt64 9007199254740992
  let largest Int64 1023
  let smallest Int64 -1022
  let subnormalShift Int64 1075
  let fiftyFour Int64 54
  let zeroWide UInt64 0
:begin
  numberOf: number = numberAt(zero=0)
  denominatorOf: denominator = numberAt(one=1)
  workOf: work = numberAt(two=2)
  divisorOf: divisor = numberAt(three=3)
  emptyCheck: empty = compare.equalInt64(kept, zero)
  if empty signedZero magnitude
:magnitude
  magnitudeOf: digitsPower = math.addInt64(kept, power)
  hugeCheck: huge = compare.greaterThanInt64(digitsPower, threeTen=310)
  if huge overflow tinyCheck
:tinyCheck
  checkTiny: tiny = compare.lessThanInt64(digitsPower, minusThreeTwentyFour=-324)
  if tiny signedZero ratio
:ratio
  setDenominator: bignum.setSmall(denominator, oneWide=1)
  positiveCheck: positivePower = compare.greaterOrEqualInt64(power, zero)
  if positivePower scaleNumber scaleDenominator
:scaleNumber
  multiplyNumber: bignum.multiplyPowerOfTen(number, power)
  goto estimate
:scaleDenominator
  negatePower: inverse = math.negateInt64(power)
  multiplyDenominator: bignum.multiplyPowerOfTen(denominator, inverse)
  goto estimate
:estimate
  numberWidth: a = bignum.bitLength(number)
  denominatorWidth: b = bignum.bitLength(denominator)
  widthGap: gap = math.subtractInt64(a, b)
  firstShift: guess = math.subtractInt64(fiftyFour, gap)
  set shift guess
  shapeWork: shapeQuotient(number, denominator, work, divisor, guess, zero)
  orderCheck: order = bignum.compareNumbers(work, divisor)
  tooBig: over = compare.greaterOrEqualInt64(order, zero)
  if over lowerShift exponentOf
:lowerShift
  lessShift: lowered = math.subtractInt64(shift, one)
  set shift lowered
  goto exponentOf
:exponentOf
  exponentValue: binary = math.subtractInt64(fiftyThree=53, shift)
  set exponent binary
  overflowCheck: overflowing = compare.greaterThanInt64(binary, largest)
  if overflowing overflow underflowCheck
:underflowCheck
  belowCheck: belowNormal = compare.lessThanInt64(binary, smallest)
  if belowNormal makeSubnormal divide
:makeSubnormal
  set subnormal yes
  set shift subnormalShift
  goto divide
:divide
  shapeFinal: shapeQuotient(number, denominator, work, divisor, shift, minusOne=-1)
  set quotient zeroWide
  goto eachBit
:eachBit loop=while max=fiftyFour
  bitsDone: doneBits = compare.greaterOrEqualInt64(round, fiftyFour)
  if doneBits rounding nextBit
:nextBit in=eachBit
  doubleQuotient: doubled = bits.shiftLeftUInt64(quotient, one)
  set quotient doubled
  bitOrder: bitCompare = bignum.compareNumbers(work, divisor)
  bitCheck: setBit = compare.greaterOrEqualInt64(bitCompare, zero)
  if setBit takeDivisor halveDivisor
:takeDivisor in=eachBit
  subtractDivisor: bignum.subtractNumber(work, divisor)
  addBit: withBit = bits.orUInt64(quotient, oneWide)
  set quotient withBit
  goto halveDivisor
:halveDivisor in=eachBit
  halve: bignum.shiftRightOne(divisor)
  countBit: roundNext = math.addInt64(round, one)
  set round roundNext
  goto eachBit
:rounding
  mantissaOf: half = bits.shiftRightUInt64(quotient, one)
  set mantissa half
  roundBitOf: roundBit = bits.andUInt64(quotient, oneWide)
  roundCheck: roundSet = compare.equalUInt64(roundBit, oneWide)
  restCheck: restZero = bignum.isZero(work)
  stickyOf: sticky = logic.not(restZero)
  lowBitOf: lowBit = bits.andUInt64(half, oneWide)
  oddCheck: odd = compare.equalUInt64(lowBit, oneWide)
  eitherCheck: tieBreak = logic.or(sticky, odd)
  upCheck: up = logic.and(roundSet, tieBreak)
  if up roundUp encode
:roundUp
  bump: bumped = math.addUInt64(half, oneWide)
  set mantissa bumped
  goto encode
:encode
  if subnormal encodeSubnormal carryCheck
:encodeSubnormal
  set result mantissa
  goto sign
:carryCheck
  carryOf: carriedOver = compare.equalUInt64(mantissa, carried)
  if carriedOver renormalize encodeNormal
:renormalize
  set mantissa hiddenBit
  higher: raised = math.addInt64(exponent, one)
  set exponent raised
  raisedCheck: raisedOverflow = compare.greaterThanInt64(raised, largest)
  if raisedOverflow overflow encodeNormal
:encodeNormal
  biasOf: biased = math.addInt64(exponent, largest)
  biasWide: biasedWide = convert.int64ToUInt64(biased)
  fieldOf: field = bits.shiftLeftUInt64(biasedWide, fiftyTwo=52)
  fractionOf: fraction = math.subtractUInt64(mantissa, hiddenBit)
  joinField: joined = bits.orUInt64(field, fraction)
  set result joined
  goto sign
:sign
  if negative addSign store
:addSign
  withSign: signed = bits.orUInt64(result, signBit)
  set result signed
  goto store
:store
  storeBits: machine.storeUInt64(bitsTarget, result)
  return parsed
:signedZero
  if negative negativeZero positiveZero
:negativeZero
  storeNegative: machine.storeUInt64(bitsTarget, signBit)
  return parsed
:positiveZero
  storePositive: machine.storeUInt64(bitsTarget, zeroWide)
  return parsed
:overflow
  return tooLarge

op shapeQuotient "Set up a division: the work number is the number times 2^shift when shift is 0 or more, and the divisor the denominator times 2^-shift otherwise, then times 2^54 (for the check) or 2^53 (for the division, `last` -1)"
  input number machine.Address copied
  input denominator machine.Address copied
  input work machine.Address copied
  input divisor machine.Address copied
  input shift Int64 copied
  input last Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let divisorShift Int64 54 mut
  let fiftyThree Int64 53
:begin
  copyWork: bignum.copyNumber(work, number)
  copyDivisor: bignum.copyNumber(divisor, denominator)
  lastCheck: forDivision = compare.lessThanInt64(last, zero=0)
  if forDivision divisionShift signCheck
:divisionShift
  set divisorShift fiftyThree
  goto signCheck
:signCheck
  upCheck: up = compare.greaterOrEqualInt64(shift, zero)
  if up shiftWork shiftDivisor
:shiftWork
  workShift: bignum.shiftLeft(work, shift)
  goto scaleDivisor
:shiftDivisor
  flip: inverse = math.negateInt64(shift)
  addInverse: total = math.addInt64(divisorShift, inverse)
  set divisorShift total
  goto scaleDivisor
:scaleDivisor
  divisorScale: bignum.shiftLeft(divisor, divisorShift)
  return

op parseFloat "Read text as a Float64 as `refined run` reads it into an address: 0 when it is a number, 1 when it is not, 2 when it is too large for a Float64; the value stored is 0 unless it is read: refined_parse_float"
  invariant readsCorrectlyRounded "Accepts `-`? digits (`.` digits)? ([eE] [+-]? digits)? only, and reads it as the nearest Float64, ties to even; past the largest Float64 is too large, below the smallest rounds to zero"
  input text machine.Address copied
  input bytes Int64 copied
  input out machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_parse_float"
  let notNumber Int32 1
  let parsed Int32 0
:begin
  zeroBits: zeroValue = convert.uint64BitsToFloat64(zeroWide=0)
  clear: machine.storeFloat64(out, zeroValue)
  validCheck: valid = validText(text, bytes)
  if valid read refuse
:refuse
  return notNumber
:read
  negativeCheck: negative = byteIs(text, bytes, zero=0, minusByte=45)
  findNumber: number = numberAt(zero)
  findKept: keptPlace = stateAt(keptAt)
  readSignificand: power = significand(text, bytes, number, keptPlace)
  readKept: kept = machine.loadInt64(keptPlace)
  findBits: bitsPlace = stateAt(bitsAt)
  convertIt: status = toBits(negative, kept, power, bitsPlace)
  okCheck: ok = compare.equalInt32(status, parsed)
  if ok store failed
:failed
  return status
:store
  readBits: resultBits = machine.loadUInt64(bitsPlace)
  asFloat: value = convert.uint64BitsToFloat64(resultBits)
  storeValue: machine.storeFloat64(out, value)
  return parsed

@tests

## Tests write text in the last 4 KiB of machine.state (from byte 61440), which the runtime's own state never
## reaches. The expected texts and bits are Python's repr and float().

op expectFormat "Write the Float64 with the given bits and compare the text with what is expected"
  input bitsValue UInt64 copied
  input expected String borrowed
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findState: state = machine.state()
  findScratch: scratch = machine.offset(state, scratchAt=61440)
  asFloat: value = convert.uint64BitsToFloat64(bitsValue)
  format: length = formatFloat(value, scratch)
  viewText: text = machine.stringAt(scratch, length)
  expectText: test.assertEqualString(expected, text)
  return

op expectParse "Read a text and compare the status and the bits of the value with what is expected"
  input text String borrowed
  input status Int64 copied
  input bitsValue UInt64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findState: state = machine.state()
  findScratch: scratch = machine.offset(state, scratchAt=61440)
  findText: textPlace = machine.addressOfString(text)
  measure: bytes = string.byteLength(text)
  parse: got = parseFloat(textPlace, bytes, scratch)
  widenStatus: gotStatus = convert.int32ToInt64(got)
  expectStatus: test.assertEqualInt64(status, gotStatus)
  readValue: gotBits = machine.loadUInt64(scratch)
  sameCheck: same = compare.equalUInt64(gotBits, bitsValue)
  expectBits: test.assertTrue(same)
  return

test formatInRegionTest "A float's text is put in a region and its length beside it"
  verifies formatFloatInRegion formatsIntoRegion
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let label String "region `numbers` of `formatInRegionTest`"
  let expected String "-2.5e-07"
:begin
  findLabel: labelAt = machine.addressOfString(label)
  labelLength: labelBytes = string.byteLength(label)
  make: region = regions.newRegion(capacity=64, labelAt, labelBytes)
  findState: state = machine.state()
  findLength: lengthAt = machine.offset(state, scratchAt=61440)
  asFloat: value = convert.uint64BitsToFloat64(minusQuarterMicro=13731694030708141453)
  format: text = formatFloatInRegion(value, region, lengthAt)
  readLength: length = machine.loadInt64(lengthAt)
  viewText: shown = machine.stringAt(text, length)
  expectText: test.assertEqualString(expected, shown)
  readLeft: left = regions.remaining(region)
  expectLeft: test.assertEqualInt64(fiftySix=56, left)
  free: regions.release(region)
  return

test writeFloatTest "A float written to standard error with no line end is its repr, and the write succeeds"
  verifies writeFloat writesReprLine
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let expected String "0.5"
:begin
  asFloat: value = convert.uint64BitsToFloat64(half=4602678819172646912)
  writeNumber: status = writeFloat(two=2, value, noLine=0)
  findText: text = stateAt(textAt)
  viewText: shown = machine.stringAt(text, three=3)
  expectText: test.assertEqualString(expected, shown)
  statusWide: statusValue = convert.int32ToInt64(status)
  expectWritten: test.assertEqualInt64(zero=0, statusValue)
  return

## ---------------------------------------------------------------- generated cases

test formatTest1 "Floats are written as `refined run` writes them (Python's repr), part 1"
  verifies formatFloat writesRepr
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findState: state = machine.state()
  findScratch: scratch = machine.offset(state, scratchAt=61440)
  asFloat: first = convert.uint64BitsToFloat64(0)
  formatFirst: length = formatFloat(first, scratch)
  viewFirst: text = machine.stringAt(scratch, length)
  expectFirst: test.assertEqualString("0.0", text)
  case1: expectFormat(9223372036854775808, "-0.0")
  case2: expectFormat(4607182418800017408, "1.0")
  case3: expectFormat(4591870180066957722, "0.1")
  case4: expectFormat(4636737291354636288, "100.0")
  case5: expectFormat(4831355200913801216, "1000000000000000.0")
  case6: expectFormat(4846369599423283200, "1e+16")
  case7: expectFormat(4532020583610935537, "1e-05")
  case8: expectFormat(4547007122018943789, "0.0001")
  case9: expectFormat(1, "5e-324")
  case10: expectFormat(4503599627370496, "2.2250738585072014e-308")
  case11: expectFormat(9218868437227405311, "1.7976931348623157e+308")
  case12: expectFormat(4599075939470750516, "0.30000000000000004")
  case13: expectFormat(4862596447618666293, "1.2345678901234568e+17")
  case14: expectFormat(9221120237041090560, "nan")
  return

test formatTest2 "Floats are written as `refined run` writes them (Python's repr), part 2"
  verifies formatFloat writesRepr
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findState: state = machine.state()
  findScratch: scratch = machine.offset(state, scratchAt=61440)
  asFloat: first = convert.uint64BitsToFloat64(9218868437227405312)
  formatFirst: length = formatFloat(first, scratch)
  viewFirst: text = machine.stringAt(scratch, length)
  expectFirst: test.assertEqualString("inf", text)
  case1: expectFormat(18442240474082181120, "-inf")
  case2: expectFormat(13832806255468478464, "-1.5")
  case3: expectFormat(103582791429521408, "9.332636185032189e-302")
  case4: expectFormat(4877398396442247168, "1.152921504606847e+18")
  case5: expectFormat(4503599627370496, "2.2250738585072014e-308")
  case6: expectFormat(9007199254740992, "4.450147717014403e-308")
  case7: expectFormat(4599676419421066581, "0.3333333333333333")
  case8: expectFormat(4604180019048437077, "0.6666666666666666")
  case9: expectFormat(4950912855330343670, "1e+23")
  case10: expectFormat(4504762867522569078, "1.5e-07")
  case11: expectFormat(9214364837600034816, "8.98846567431158e+307")
  case12: expectFormat(4616583683022153318, "4.35")
  case13: expectFormat(4602678819172646912, "0.5")
  case14: expectFormat(4612811918334230528, "2.5")
  return

test formatTest3 "Floats are written as `refined run` writes them (Python's repr), part 3"
  verifies formatFloat writesRepr
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findState: state = machine.state()
  findScratch: scratch = machine.offset(state, scratchAt=61440)
  asFloat: first = convert.uint64BitsToFloat64(6103021453049119613)
  formatFirst: length = formatFloat(first, scratch)
  viewFirst: text = machine.stringAt(scratch, length)
  expectFirst: test.assertEqualString("1e+100", text)
  case1: expectFormat(4653144502051863213, "1234.5678")
  case2: expectFormat(4950912855330343670, "1e+23")
  case3: expectFormat(4936209963552724370, "1e+22")
  case4: expectFormat(4841369599423283200, "4503599627370496.0")
  case5: expectFormat(4845873199050653697, "9007199254740994.0")
  case6: expectFormat(3, "1.5e-323")
  case7: expectFormat(4607182418800017409, "1.0000000000000002")
  case8: expectFormat(4607182418800017407, "0.9999999999999999")
  case9: expectFormat(4547007122018943789, "0.0001")
  case10: expectFormat(4517110426252607488, "9.5367431640625e-07")
  case11: expectFormat(9223372036854788153, "-6.099e-320")
  case12: expectFormat(4503599627370496, "2.2250738585072014e-308")
  case13: expectFormat(9214364837600034816, "8.98846567431158e+307")
  return

test parseTest1 "Text is read as `refined run` reads it, correctly rounded, part 1"
  verifies parseFloat readsCorrectlyRounded
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findState: state = machine.state()
  findScratch: scratch = machine.offset(state, scratchAt=61440)
  findFirst: firstAt = machine.addressOfString("0")
  parseFirst: got = parseFloat(firstAt, 1, scratch)
  widenFirst: gotStatus = convert.int32ToInt64(got)
  expectFirst: test.assertEqualInt64(0, gotStatus)
  case1: expectParse("-0", 0, 9223372036854775808)
  case2: expectParse("1", 0, 4607182418800017408)
  case3: expectParse("1.5", 0, 4609434218613702656)
  case4: expectParse("0.1", 0, 4591870180066957722)
  case5: expectParse("1e10", 0, 4756540486875873280)
  case6: expectParse("1E-5", 0, 4532020583610935537)
  case7: expectParse("2.5e+3", 0, 4657715973212602368)
  case8: expectParse("-123.456", 0, 13861759897472843383)
  case9: expectParse("1.7976931348623157e308", 0, 9218868437227405311)
  case10: expectParse("1.7976931348623158e308", 0, 9218868437227405311)
  case11: expectParse("1.7976931348623159e308", 2, 0)
  case12: expectParse("1e309", 2, 0)
  case13: expectParse("-1e309", 2, 0)
  case14: expectParse("1e-400", 0, 0)
  case15: expectParse("-1e-400", 0, 9223372036854775808)
  return

test parseTest2 "Text is read as `refined run` reads it, correctly rounded, part 2"
  verifies parseFloat readsCorrectlyRounded
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findState: state = machine.state()
  findScratch: scratch = machine.offset(state, scratchAt=61440)
  findFirst: firstAt = machine.addressOfString("2.4703282292062328e-324")
  parseFirst: got = parseFloat(firstAt, 23, scratch)
  widenFirst: gotStatus = convert.int32ToInt64(got)
  expectFirst: test.assertEqualInt64(0, gotStatus)
  case1: expectParse("2.4703282292062327e-324", 0, 0)
  case2: expectParse("4.9406564584124654e-324", 0, 1)
  case3: expectParse("2.2250738585072011e-308", 0, 4503599627370495)
  case4: expectParse("2.2250738585072012e-308", 0, 4503599627370496)
  case5: expectParse("9007199254740993", 0, 4845873199050653696)
  case6: expectParse("9007199254740995", 0, 4845873199050653698)
  case7: expectParse("0.000000000000000000000000000000000001", 0, 4068233174594694770)
  case8: expectParse("123456789012345678901234567890", 0, 5042042089369253694)
  case9: expectParse("00012", 0, 4622945017495814144)
  case10: expectParse("0.30000000000000004", 0, 4599075939470750516)
  case11: expectParse("1000000000000000000000000000000e-30", 0, 4607182418800017408)
  case12: expectParse("0.00000000001111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111111", 0, 4442923077622635117)
  case13: expectParse("9999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999999e-820", 0, 4607182418800017408)
  case14: expectParse("7e-10000000000000000000000", 0, 0)
  case15: expectParse("1e99999999999999999999", 2, 0)
  return

test parseTest3 "Text is read as `refined run` reads it, correctly rounded, part 3"
  verifies parseFloat readsCorrectlyRounded
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findState: state = machine.state()
  findScratch: scratch = machine.offset(state, scratchAt=61440)
  findFirst: firstAt = machine.addressOfString("0e99999999999999999999")
  parseFirst: got = parseFloat(firstAt, 22, scratch)
  widenFirst: gotStatus = convert.int32ToInt64(got)
  expectFirst: test.assertEqualInt64(0, gotStatus)
  case1: expectParse("+1", 1, 0)
  case2: expectParse("1.", 1, 0)
  case3: expectParse(".5", 1, 0)
  case4: expectParse("1e", 1, 0)
  case5: expectParse("abc", 1, 0)
  case6: expectParse("", 1, 0)
  case7: expectParse("-", 1, 0)
  case8: expectParse("1.5e+", 1, 0)
  case9: expectParse("1_0", 1, 0)
  case10: expectParse(" 1", 1, 0)
  case11: expectParse("1e+-5", 1, 0)
  case12: expectParse("--1", 1, 0)
  case13: expectParse("1.2.3", 1, 0)
  case14: expectParse("nan", 1, 0)
  case15: expectParse("inf", 1, 0)
  return
