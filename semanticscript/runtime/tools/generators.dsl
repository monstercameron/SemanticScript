module generators "Random numbers: the operating system's secure source, and seeded generators that give exactly what Python's random.Random gives"
  path generators
  imports standard.machine standard.system standard.string standard.math standard.compare standard.convert standard.bits standard.test kernel frames heap handles regions slots
  exports randomCall

capability memoryAccess "Authority to keep a generator's state in memory and read a host call's slots" use machine.memory none

capability systemCalls "Authority to read random bytes from the operating system and take memory for a generator" use system.calls none

## `random.int64Between` reads the system's secure source as Python's `secrets.randbelow` does: Windows's
## BCryptGenRandom with the system's preferred generator (bcrypt.dll, D-146), Linux's getrandom. A seeded generator
## is CPython's Mersenne Twister (MT19937): `init_genrand(19650218)`, then `init_by_array` with the seed's magnitude
## in 32-bit words, least significant first, as `random.Random(seed)` seeds it; `random.nextInt64` is
## `randint(low, high)`, which takes `getrandbits(k)` of the range's bit length until a number falls inside it.
## A generator is a heap block of generatorBytes: its 624 words at 0 (one per 8 bytes) and the next word's place at
## 4992. machine.state bytes 1024 to 1047 belong to this module: 1024 the seed's words, 1040 random bytes as they are read.
constant generatorBytes "The bytes of a generator: 624 words and the next word's place" Int64 5000

constant keyAt "Where the seed's words are put, in machine.state" Int64 1024

constant kindGenerator "The kind of a random number generator's handle" Int64 9

constant wordMask "The 32 low bits of a whole number" Int64 4294967295

constant emptyRange "random.RangeError.emptyRange, numbered from 1" Int32 1

op endProcess "End the process with an exit code: ExitProcess on Windows, exit_group on Linux (D-138)"
  input code Int32 copied
  effect use system.calls
  uses systemCalls
:begin
  osCheck: onLinux = system.posix()
  if onLinux linuxExit windowsExit
:linuxExit
  widenCode: wideCode = convert.int32ToInt64(code)
  callExit: exitResult = system.exitGroup(wideCode)
  return
:windowsExit
  callExitProcess: system.exitProcess(code)
  return

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

## ---------------------------------------------------------------- the system's secure source

op secureBytes "Fill memory with bytes from the operating system's secure random source; a source that fails traps"
  input target machine.Address copied
  input bytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let filled Int64 0 mut
  let forever Int64 9223372036854775807
:begin
  osCheck: onLinux = system.posix()
  if onLinux eachRead windowsRead
:windowsRead
  nowhere: anywhere = machine.zero()
  narrowBytes: bytes32 = convert.int64ToInt32(bytes)
  generate: status = system.bCryptGenRandom(anywhere, target, bytes32, systemPreferred=2)
  failedCheck: refused = compare.notEqualInt32(status, zero32=0)
  if refused fail done
:eachRead loop=while max=forever
  allCheck: all = compare.greaterOrEqualInt64(filled, bytes)
  if all done readSome
:readSome in=eachRead
  findPlace: place = machine.offset(target, filled)
  leftOf: left = math.subtractInt64(bytes, filled)
  readIt: got = system.getrandom(place, left, noFlags=0)
  failedRead: refusedLinux = kernel.failed(got)
  if refusedLinux interruptedCheck count
:interruptedCheck in=eachRead
  errnoOf: errno = kernel.errnoOf(got)
  againCheck: again = compare.equalInt64(errno, eintr=4)
  if again eachRead fail
:count in=eachRead
  moreDone: after = math.addInt64(filled, got)
  set filled after
  goto eachRead
:fail
  failIt: failText(failedText="the operating system's random number generator failed")
  return
:done
  return

op secureWord "64 bits from the operating system's secure random source"
  output UInt64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findPlace: place = kernel.stateAt(randomAt=1040)
  fillIt: secureBytes(place, eight=8)
  readIt: value = machine.loadUInt64(place)
  return value

op bitLength "How many bits a whole number needs: 0 for 0"
  input value UInt64 copied
  output Int64
  let left UInt64 0 mut
  let count Int64 0 mut
  let noBits UInt64 0
:begin
  set left value
  goto eachBit
:eachBit loop=while max=65
  zeroCheck: empty = compare.equalUInt64(left, noBits)
  if empty finish shift
:shift in=eachBit
  shiftIt: shifted = bits.shiftRightUInt64(left, one=1)
  set left shifted
  countIt: more = math.addInt64(count, one)
  set count more
  goto eachBit
:finish
  return count

op lowMask "The whole number whose k low bits are ones, for k from 1 to 64"
  input k Int64 copied
  output UInt64
  let ones UInt64 18446744073709551615
:begin
  fullCheck: full = compare.greaterOrEqualInt64(k, sixtyFour=64)
  if full giveOnes shiftIt
:giveOnes
  return ones
:shiftIt
  dropOf: drop = math.subtractInt64(sixtyFour, k)
  shifted: mask = bits.shiftRightUInt64(ones, drop)
  return mask

op widthOf "How many whole numbers lie from low to high (low not above high), 0 standing for all 2^64"
  input low Int64 copied
  input high Int64 copied
  output UInt64
:begin
  lowBits: lowWide = convert.int64BitsToUInt64(low)
  highBits: highWide = convert.int64BitsToUInt64(high)
  span: difference = math.wrappingSubtractUInt64(highWide, lowWide)
  count: width = math.wrappingAddUInt64(difference, oneWide=1)
  return width

op offsetFrom "low plus an offset below the range's width, as a whole number"
  input low Int64 copied
  input offset UInt64 copied
  output Int64
:begin
  lowBits: lowWide = convert.int64BitsToUInt64(low)
  addIt: sum = math.wrappingAddUInt64(lowWide, offset)
  backIt: value = convert.uint64BitsToInt64(sum)
  return value

op secureBelow "A number below a width (0 for all 2^64) from the secure source, every one equally likely: as secrets.randbelow, its bits taken until one falls inside"
  input width UInt64 copied
  output UInt64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let forever Int64 9223372036854775807
  let noBits UInt64 0
:begin
  fullCheck: full = compare.equalUInt64(width, noBits)
  if full anyWord sized
:anyWord
  readAny: value = secureWord()
  return value
:sized
  lengthOf: k = bitLength(width)
  maskOf: mask = lowMask(k)
  goto eachTry
:eachTry loop=while max=forever
  readWord: raw = secureWord()
  keepBits: candidate = bits.andUInt64(raw, mask)
  insideCheck: inside = compare.lessThanUInt64(candidate, width)
  if inside give eachTry
:give
  return candidate

## ---------------------------------------------------------------- the Mersenne Twister, as CPython has it

op word "A word of a generator by its place"
  input state machine.Address copied
  input place Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  offsetOf: offset = math.multiplyInt64(place, eight=8)
  findWord: at = machine.offset(state, offset)
  readWord: value = machine.loadInt64(at)
  return value

op setWord "Store a word of a generator by its place"
  input state machine.Address copied
  input place Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  offsetOf: offset = math.multiplyInt64(place, eight=8)
  findWord: at = machine.offset(state, offset)
  storeWord: machine.storeInt64(at, value)
  return

op scramble "A word mixed with the bits above its 30th: w ^ (w >> 30)"
  input value Int64 copied
  output Int64
:begin
  shiftIt: high = bits.shiftRightInt64(value, thirty=30)
  mixIt: mixed = bits.xorInt64(value, high)
  return mixed

op seedState "Seed a generator as CPython's init_genrand(19650218) and init_by_array seed it, from up to two 32-bit key words in machine.state"
  input state machine.Address copied
  input keyLength Int64 copied
  effect use machine.memory
  uses memoryAccess
  let i Int64 1 mut
  let j Int64 0 mut
  let k Int64 0 mut
  let n624 Int64 624
:begin
  storeFirst: setWord(state, zero=0, start=19650218)
  goto eachInit
:eachInit loop=while max=n624
  initDone: initFinished = compare.greaterOrEqualInt64(i, n624)
  if initFinished mixKey initWord
:initWord in=eachInit
  beforeOf: before = math.subtractInt64(i, one=1)
  readBefore: previous = word(state, before)
  scrambleIt: scrambled = scramble(previous)
  multiplyIt: product = math.multiplyInt64(scrambled, initFactor=1812433253)
  addPlace: summed = math.addInt64(product, i)
  maskIt: initValue = bits.andInt64(summed, wordMask)
  storeInit: setWord(state, i, initValue)
  nextInit: afterInit = math.addInt64(i, one)
  set i afterInit
  goto eachInit
:mixKey
  set i one
  set j zero
  set k zero
  findKey: key = kernel.stateAt(keyAt)
  goto eachKey
:eachKey loop=while max=n624
  keyDone: keyFinished = compare.greaterOrEqualInt64(k, n624)
  if keyFinished mixRest keyWord
:keyWord in=eachKey
  beforeKey: keyBefore = math.subtractInt64(i, one)
  readPrevious: previousKey = word(state, keyBefore)
  scrambleKey: scrambledKey = scramble(previousKey)
  multiplyKey: keyProduct = math.multiplyInt64(scrambledKey, keyFactor=1664525)
  readOwn: own = word(state, i)
  mixOwn: mixedKey = bits.xorInt64(own, keyProduct)
  keyOffset: keyPlace = math.multiplyInt64(j, eight=8)
  findKeyWord: keyWordAt = machine.offset(key, keyPlace)
  readKeyWord: keyValue = machine.loadInt64(keyWordAt)
  addKeyWord: withKey = math.addInt64(mixedKey, keyValue)
  addJ: withJ = math.addInt64(withKey, j)
  maskKey: keyResult = bits.andInt64(withJ, wordMask)
  storeKey: setWord(state, i, keyResult)
  nextI: afterI = math.addInt64(i, one)
  set i afterI
  nextJ: afterJ = math.addInt64(j, one)
  set j afterJ
  nextK: afterK = math.addInt64(k, one)
  set k afterK
  wrapICheck: wrapI = compare.greaterOrEqualInt64(i, n624)
  if wrapI wrapKeyI wrapJCheck
:wrapKeyI in=eachKey
  readLast: lastWord = word(state, n623=623)
  storeLast: setWord(state, zero, lastWord)
  set i one
  goto wrapJCheck
:wrapJCheck in=eachKey
  checkJ: wrapJ = compare.greaterOrEqualInt64(j, keyLength)
  if wrapJ resetJ eachKey
:resetJ in=eachKey
  set j zero
  goto eachKey
:mixRest
  set k zero
  goto eachRest
:eachRest loop=while max=n624
  restDone: restFinished = compare.greaterOrEqualInt64(k, n623)
  if restFinished finish restWord
:restWord in=eachRest
  beforeRest: restBefore = math.subtractInt64(i, one)
  readRestPrevious: previousRest = word(state, restBefore)
  scrambleRest: scrambledRest = scramble(previousRest)
  multiplyRest: restProduct = math.multiplyInt64(scrambledRest, restFactor=1566083941)
  readRestOwn: restOwn = word(state, i)
  mixRestOwn: mixedRest = bits.xorInt64(restOwn, restProduct)
  takeI: lessI = math.subtractInt64(mixedRest, i)
  maskRest: restResult = bits.andInt64(lessI, wordMask)
  storeRest: setWord(state, i, restResult)
  nextRestI: afterRestI = math.addInt64(i, one)
  set i afterRestI
  nextRestK: afterRestK = math.addInt64(k, one)
  set k afterRestK
  wrapRestCheck: wrapRest = compare.greaterOrEqualInt64(i, n624)
  if wrapRest wrapRestI eachRest
:wrapRestI in=eachRest
  readRestLast: restLast = word(state, n623)
  storeRestLast: setWord(state, zero, restLast)
  set i one
  goto eachRest
:finish
  storeTop: setWord(state, zero, top=2147483648)
  storePlace: setWord(state, n624, n624)
  return

op mix "One step of the twist: word `at` from its own upper bit, the next word's lower bits, and a word further on"
  input state machine.Address copied
  input at Int64 copied
  input next Int64 copied
  input far Int64 copied
  effect use machine.memory
  uses memoryAccess
  let matrix Int64 2567483615
  let noBit Int64 0
:begin
  readAt: own = word(state, at)
  upperOf: upper = bits.andInt64(own, upperMask=2147483648)
  readNext: following = word(state, next)
  lowerOf: lower = bits.andInt64(following, lowerMask=2147483647)
  joinIt: y = bits.orInt64(upper, lower)
  readFar: further = word(state, far)
  halfOf: half = bits.shiftRightInt64(y, one=1)
  mixHalf: mixed = bits.xorInt64(further, half)
  oddOf: odd = bits.andInt64(y, one)
  oddCheck: isOdd = compare.notEqualInt64(odd, noBit)
  if isOdd withMatrix store
:withMatrix
  mixMatrix: twisted = bits.xorInt64(mixed, matrix)
  storeTwisted: setWord(state, at, twisted)
  return
:store
  storeMixed: setWord(state, at, mixed)
  return

op nextWord "The generator's next 32-bit word, as CPython's genrand_uint32 gives it: the 624 words twisted when all were used, then tempered"
  input state machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let kk Int64 0 mut
  let n624 Int64 624
  let zero Int64 0
:begin
  readPlace: place = word(state, n624)
  fullCheck: used = compare.greaterOrEqualInt64(place, n624)
  if used twist temper
:twist
  set kk zero
  goto eachFirst
:eachFirst loop=while max=n624
  firstDone: firstFinished = compare.greaterOrEqualInt64(kk, n227=227)
  if firstFinished eachSecond mixFirst
:mixFirst in=eachFirst
  nextFirst: afterFirst = math.addInt64(kk, one=1)
  farFirst: furtherFirst = math.addInt64(kk, n397=397)
  mixIt: mix(state, kk, afterFirst, furtherFirst)
  set kk afterFirst
  goto eachFirst
:eachSecond loop=while max=n624
  secondDone: secondFinished = compare.greaterOrEqualInt64(kk, n623=623)
  if secondFinished mixLast mixSecond
:mixSecond in=eachSecond
  nextSecond: afterSecond = math.addInt64(kk, one)
  farSecond: furtherSecond = math.subtractInt64(kk, n227)
  mixAgain: mix(state, kk, afterSecond, furtherSecond)
  set kk afterSecond
  goto eachSecond
:mixLast
  mixEnd: mix(state, n623, zero, n396=396)
  resetPlace: setWord(state, n624, zero)
  goto temper
:temper
  readNow: at = word(state, n624)
  readWord: y0 = word(state, at)
  advance: afterAt = math.addInt64(at, one)
  storePlace: setWord(state, n624, afterAt)
  shift11: s11 = bits.shiftRightInt64(y0, eleven=11)
  temper1: y1 = bits.xorInt64(y0, s11)
  shift7: s7 = bits.shiftLeftInt64(y1, seven=7)
  mask7: m7 = bits.andInt64(s7, temperB=2636928640)
  temper2: y2 = bits.xorInt64(y1, m7)
  shift15: s15 = bits.shiftLeftInt64(y2, fifteen=15)
  mask15: m15 = bits.andInt64(s15, temperC=4022730752)
  temper3: y3 = bits.xorInt64(y2, m15)
  shift18: s18 = bits.shiftRightInt64(y3, eighteen=18)
  temper4: y4 = bits.xorInt64(y3, s18)
  return y4

op wideWord "The generator's next word as a UInt64"
  input state machine.Address copied
  output UInt64
  effect use machine.memory
  uses memoryAccess
:begin
  readIt: value = nextWord(state)
  widen: wide = convert.int64BitsToUInt64(value)
  return wide

op randomBits "CPython's getrandbits(k) for k from 1 to 64: one word shifted down for 32 bits or fewer, else two words, the first the low half and the second shifted down"
  input state machine.Address copied
  input k Int64 copied
  output UInt64
  effect use machine.memory
  uses memoryAccess
:begin
  smallCheck: small = compare.lessOrEqualInt64(k, thirtyTwo=32)
  if small oneWord twoWords
:oneWord
  readOne: single = wideWord(state)
  dropOf: drop = math.subtractInt64(thirtyTwo, k)
  shiftOne: shifted = bits.shiftRightUInt64(single, drop)
  return shifted
:twoWords
  readLow: low = wideWord(state)
  readHigh: high = wideWord(state)
  highDropOf: highDrop = math.subtractInt64(sixtyFour=64, k)
  shiftHigh: highShifted = bits.shiftRightUInt64(high, highDrop)
  moveHigh: highPart = bits.shiftLeftUInt64(highShifted, thirtyTwo)
  joinIt: joined = bits.orUInt64(highPart, low)
  return joined

op generatorBelow "A number below a width (0 for all 2^64) from a generator, as CPython's _randbelow_with_getrandbits takes it: getrandbits of the width's bit length until a number falls below it"
  input state machine.Address copied
  input width UInt64 copied
  output UInt64
  effect use machine.memory
  uses memoryAccess
  let forever Int64 9223372036854775807
  let noBits UInt64 0
:begin
  fullCheck: full = compare.equalUInt64(width, noBits)
  if full eachFull sized
:eachFull loop=while max=forever
  readLow: low = wideWord(state)
  readHigh: high = wideWord(state)
  readTop: top = wideWord(state)
  topBit: topShifted = bits.shiftRightUInt64(top, thirtyOne=31)
  insideCheck: inside = compare.equalUInt64(topShifted, noBits)
  if inside giveFull eachFull
:giveFull
  moveHigh: highPart = bits.shiftLeftUInt64(high, thirtyTwo=32)
  joinIt: joined = bits.orUInt64(highPart, low)
  return joined
:sized
  lengthOf: k = bitLength(width)
  goto eachTry
:eachTry loop=while max=forever
  readBits: candidate = randomBits(state, k)
  belowCheck: below = compare.lessThanUInt64(candidate, width)
  if below give eachTry
:give
  return candidate

op seedGenerator "A new generator seeded from a whole number as random.Random(seed) seeds one: its magnitude's 32-bit words, least significant first (one word for 0)"
  input seed Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let magnitude UInt64 0 mut
  let length Int64 1 mut
  let two Int64 2
  let noBits UInt64 0
:begin
  takeState: state = heap.take(generatorBytes)
  wideSeed: raw = convert.int64BitsToUInt64(seed)
  set magnitude raw
  negativeCheck: negative = compare.lessThanInt64(seed, zero=0)
  if negative flip words
:flip
  flipIt: flipped = math.wrappingSubtractUInt64(noBits, raw)
  set magnitude flipped
  goto words
:words
  lowOf: lowWide = bits.andUInt64(magnitude, wordMaskWide=4294967295)
  highOf: highWide = bits.shiftRightUInt64(magnitude, thirtyTwo=32)
  lowNarrow: low = convert.uint64BitsToInt64(lowWide)
  highNarrow: high = convert.uint64BitsToInt64(highWide)
  findKey: key = kernel.stateAt(keyAt)
  storeLow: machine.storeInt64(key, low)
  findHigh: highAt = machine.offset(key, eight=8)
  storeHigh: machine.storeInt64(highAt, high)
  highCheck: hasHigh = compare.notEqualInt64(high, zero)
  if hasHigh twoWords seedIt
:twoWords
  set length two
  goto seedIt
:seedIt
  seedItNow: seedState(state, length)
  return state

## ---------------------------------------------------------------- targets

op betweenTarget "random.int64Between: a number from low to high, both included, from the secure source; low above high is emptyRange"
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
  readLow: low = slots.argOf(shape, args, zero=0)
  readHigh: high = slots.argOf(shape, args, one=1)
  emptyCheck: empty = compare.greaterThanInt64(low, high)
  if empty giveEmpty pick
:giveEmpty
  emptyStatus: status = slots.failWith(payload, emptyRange, zero)
  return status
:pick
  widthIt: width = widthOf(low, high)
  pickIt: offset = secureBelow(width)
  addIt: value = offsetFrom(low, offset)
  storeIt: machine.storeInt64(results, value)
  return ok

op newGeneratorTarget "random.newGenerator: a generator seeded from a whole number, owned by a region"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readSeed: seed = slots.argOf(shape, args, zero=0)
  readRegion: region = slots.addressArg(shape, args, one=1)
  makeIt: state = seedGenerator(seed)
  makeHandle: handle = handles.newHandle(kindGenerator, state, region)
  storeIt: machine.storeInt64(results, handle)
  return

op nextTarget "random.nextInt64: a generator's next number from low to high, as randint(low, high) gives it; low above high is emptyRange and takes nothing from the generator"
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
  findState: state = handles.objectOf(handle, kindGenerator)
  readLow: low = slots.argOf(shape, args, one=1)
  readHigh: high = slots.argOf(shape, args, two=2)
  emptyCheck: empty = compare.greaterThanInt64(low, high)
  if empty giveEmpty pick
:giveEmpty
  emptyStatus: status = slots.failWith(payload, emptyRange, zero=0)
  return status
:pick
  widthIt: width = widthOf(low, high)
  pickIt: offset = generatorBelow(state, width)
  addIt: value = offsetFrom(low, offset)
  storeIt: machine.storeInt64(results, value)
  return ok

op randomCall "Run a random target by its place among them (1 int64Between, 2 newGenerator, 3 nextInt64): 0, or an error's variant number with its payload stored"
  invariant runsRandom "int64Between gives a number of its range or emptyRange; a generator gives what random.Random(seed).randint gives, in the same order"
  input which Int64 copied
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
  isBetween: between = compare.equalInt64(which, one=1)
  if between runBetween newCheck
:runBetween
  betweenIt: betweenStatus = betweenTarget(shape, args, results, payload)
  return betweenStatus
:newCheck
  isNew: makeNew = compare.equalInt64(which, two=2)
  if makeNew runNew runNext
:runNew
  newIt: newGeneratorTarget(shape, args, results)
  return ok
:runNext
  nextIt: nextStatus = nextTarget(shape, args, results, payload)
  return nextStatus

@tests

## Tests build a shape and a call's slots in the last 4 KiB of machine.state: the shape from byte 61440, the
## arguments from 61952, the results from 62016, the payload at 62080, the slot counts at 62208.

op setArg "Set an argument slot of the tests' call to a number"
  input slot Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  offsetOf: offset = math.multiplyInt64(slot, eight=8)
  withBase: place = math.addInt64(offset, argsOffset=61952)
  findSlot: address = kernel.stateAt(place)
  storeIt: machine.storeInt64(address, value)
  return

op callRandom "Call a random target with the tests' slots, each parameter one slot, and give its status"
  input which Int64 copied
  input params Int64 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  findShape: shape = kernel.stateAt(shapeAt=61440)
  findParams: paramsAt = machine.offset(shape, twentyFour=24)
  storeParams: machine.storeInt64(paramsAt, params)
  goto eachParam
:eachParam loop=while max=params
  doneCheck: done = compare.greaterOrEqualInt64(at, params)
  if done call setParam
:setParam in=eachParam
  placeOf: place = math.multiplyInt64(at, eight=8)
  countOffset: countPlace = math.addInt64(place, forty=40)
  findCount: countAt = machine.offset(shape, countPlace)
  storeCount: machine.storeInt64(countAt, one=1)
  startOffset: startPlace = math.addInt64(place, twoThirtyTwo=232)
  findStart: startAt = machine.offset(shape, startPlace)
  storeStart: machine.storeInt64(startAt, at)
  nextParam: after = math.addInt64(at, one)
  set at after
  goto eachParam
:call
  findArgs: args = kernel.stateAt(argsOffset=61952)
  findResults: results = kernel.stateAt(resultsOffset=62016)
  findPayload: payload = kernel.stateAt(payloadOffset=62080)
  callIt: status = randomCall(which, shape, args, results, payload)
  return status

op result "The first result slot of the tests' call"
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findResults: results = kernel.stateAt(resultsOffset=62016)
  readIt: value = machine.loadInt64(results)
  return value

op expectStatus "Compare a call's status with what is expected"
  input wanted Int64 copied
  input status Int32 copied
:begin
  widenStatus: statusValue = convert.int32ToInt64(status)
  compareIt: test.assertEqualInt64(wanted, statusValue)
  return

op newGenerator "A generator seeded from a whole number, in a region"
  input seed Int64 copied
  input region machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  setSeed: setArg(zero=0, seed)
  findRegionSlot: regionSlot = kernel.stateAt(regionOffset=61960)
  setRegion: machine.storeAddress(regionSlot, region)
  callIt: status = callRandom(two=2, two)
  expectOk: expectStatus(zero, status)
  readIt: handle = result()
  return handle

op expectNext "Draw a generator's next number from a range and compare it with what Python's randint gives"
  input handle Int64 copied
  input low Int64 copied
  input high Int64 copied
  input wanted Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  setHandle: setArg(zero=0, handle)
  setLow: setArg(one=1, low)
  setHigh: setArg(two=2, high)
  callIt: status = callRandom(three=3, three)
  expectOk: expectStatus(zero, status)
  readIt: value = result()
  expectIt: test.assertEqualInt64(wanted, value)
  return

op expectBetween "Draw a number from the secure source and check it lies in its range"
  input low Int64 copied
  input high Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  setLow: setArg(zero=0, low)
  setHigh: setArg(one=1, high)
  callIt: status = callRandom(one, two=2)
  expectOk: expectStatus(zero, status)
  readIt: value = result()
  lowCheck: above = compare.greaterOrEqualInt64(value, low)
  test.assertTrue(above)
  highCheck: below = compare.lessOrEqualInt64(value, high)
  test.assertTrue(below)
  return

test randomTest "Seeded generators give what random.Random(seed).randint gives; the secure source stays in its range; an empty range is emptyRange"
  verifies randomCall runsRandom
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let label String "random test"
  let round Int64 0 mut
  let least Int64 -9223372036854775808
  let most Int64 9223372036854775807
:begin
  findLabel: labelAt = machine.addressOfString(label)
  labelLength: labelBytes = string.byteLength(label)
  make: region = regions.newRegion(capacity=65536, labelAt, labelBytes)
  makeFirst: first = newGenerator(seed42=42, region)
  next1: expectNext(first, one=1, six=6, six)
  next2: expectNext(first, one, six, one)
  next3: expectNext(first, zero=0, twoTo32=4294967296, got3=1181241943)
  next4: expectNext(first, least, most, got4=836864915349561680)
  next5: expectNext(first, seven=7, seven, seven)
  next6: expectNext(first, five=5, twoTo40=1099511627776, got6=30201276664)
  next7: expectNext(first, minusThousand=-1000, thousand=1000, got7=-809)
  makeSecond: second = newGenerator(minusSeven=-7, region)
  next8: expectNext(second, one, hundred=100, got8=42)
  next9: expectNext(second, one, hundred, got9=20)
  makeThird: third = newGenerator(zero, region)
  next10: expectNext(third, zero, nine=9, six)
  makeFourth: fourth = newGenerator(least, region)
  next11: expectNext(fourth, zero, twoTo62=4611686018427387904, got11=3633012915649368328)
  setHandle: setArg(zero, first)
  setLow: setArg(one, five)
  setHigh: setArg(two=2, four=4)
  emptyIt: emptyStatus = callRandom(three=3, three)
  expectEmpty: expectStatus(one, emptyStatus)
  setBetweenLow: setArg(zero, five)
  setBetweenHigh: setArg(one, four)
  findShape: shape = kernel.stateAt(shapeAt=61440)
  findArgs: args = kernel.stateAt(argsOffset=61952)
  findResults: results = kernel.stateAt(resultsOffset=62016)
  findPayload: payload = kernel.stateAt(payloadOffset=62080)
  emptyBetween: betweenStatus = randomCall(one, shape, args, results, payload)
  widenBetween: betweenValue = convert.int32ToInt64(betweenStatus)
  expectEmptyBetween: test.assertEqualInt64(one, betweenValue)
  goto eachRound
:eachRound loop=while max=hundred
  roundsDone: done = compare.greaterOrEqualInt64(round, hundred)
  if done finish draw
:draw in=eachRound
  drawSmall: expectBetween(minusThree=-3, three)
  drawAll: expectBetween(least, most)
  drawOne: expectBetween(seven, seven)
  nextRound: after = math.addInt64(round, one)
  set round after
  goto eachRound
:finish
  free: regions.release(region)
  return
