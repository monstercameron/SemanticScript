module hashes "SHA-256, HMAC-SHA-256, hexadecimal text, and constant-time equality: the crypto targets"
  path hashes
  imports standard.machine standard.string standard.math standard.compare standard.convert standard.bits standard.test heap regions slots files
  exports sha256 cryptoSha256 cryptoHmacSha256 cryptoToHex cryptoConstantTimeEquals

capability memoryAccess "Authority to read the bytes to hash and write the digests" use machine.memory none

capability systemCalls "Authority to take memory for the message being hashed" use system.calls none

## SHA-256 as FIPS 180-4 gives it, on whole numbers kept to 32 bits; HMAC as RFC 2104 gives it, with a block of 64
## bytes; both give what Python's hashlib and hmac give, which `refined run` uses.
constant roundConstants "SHA-256's 64 round constants, big-endian" String "\x42\x8a\x2f\x98\x71\x37\x44\x91\xb5\xc0\xfb\xcf\xe9\xb5\xdb\xa5\x39\x56\xc2\x5b\x59\xf1\x11\xf1\x92\x3f\x82\xa4\xab\x1c\x5e\xd5\xd8\x07\xaa\x98\x12\x83\x5b\x01\x24\x31\x85\xbe\x55\x0c\x7d\xc3\x72\xbe\x5d\x74\x80\xde\xb1\xfe\x9b\xdc\x06\xa7\xc1\x9b\xf1\x74\xe4\x9b\x69\xc1\xef\xbe\x47\x86\x0f\xc1\x9d\xc6\x24\x0c\xa1\xcc\x2d\xe9\x2c\x6f\x4a\x74\x84\xaa\x5c\xb0\xa9\xdc\x76\xf9\x88\xda\x98\x3e\x51\x52\xa8\x31\xc6\x6d\xb0\x03\x27\xc8\xbf\x59\x7f\xc7\xc6\xe0\x0b\xf3\xd5\xa7\x91\x47\x06\xca\x63\x51\x14\x29\x29\x67\x27\xb7\x0a\x85\x2e\x1b\x21\x38\x4d\x2c\x6d\xfc\x53\x38\x0d\x13\x65\x0a\x73\x54\x76\x6a\x0a\xbb\x81\xc2\xc9\x2e\x92\x72\x2c\x85\xa2\xbf\xe8\xa1\xa8\x1a\x66\x4b\xc2\x4b\x8b\x70\xc7\x6c\x51\xa3\xd1\x92\xe8\x19\xd6\x99\x06\x24\xf4\x0e\x35\x85\x10\x6a\xa0\x70\x19\xa4\xc1\x16\x1e\x37\x6c\x08\x27\x48\x77\x4c\x34\xb0\xbc\xb5\x39\x1c\x0c\xb3\x4e\xd8\xaa\x4a\x5b\x9c\xca\x4f\x68\x2e\x6f\xf3\x74\x8f\x82\xee\x78\xa5\x63\x6f\x84\xc8\x78\x14\x8c\xc7\x02\x08\x90\xbe\xff\xfa\xa4\x50\x6c\xeb\xbe\xf9\xa3\xf7\xc6\x71\x78\xf2"

constant initialHash "SHA-256's initial hash value, big-endian" String "\x6a\x09\xe6\x67\xbb\x67\xae\x85\x3c\x6e\xf3\x72\xa5\x4f\xf5\x3a\x51\x0e\x52\x7f\x9b\x05\x68\x8c\x1f\x83\xd9\xab\x5b\xe0\xcd\x19"

constant hexDigits "The digits of hexadecimal text" String "0123456789abcdef"

constant lowWord "The 32 low bits of a whole number" Int64 4294967295

## ---------------------------------------------------------------- 32-bit words

op word "A 32-bit word read big-endian at an offset"
  input data machine.Address copied
  input offset Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let value Int64 0 mut
  let at Int64 0 mut
:begin
  goto eachByte
:eachByte loop=while max=four
  doneCheck: done = compare.greaterOrEqualInt64(at, four=4)
  if done finish addByte
:addByte in=eachByte
  placeOf: place = math.addInt64(offset, at)
  findByte: byteAt = machine.offset(data, place)
  readByte: byte = machine.loadByte(byteAt)
  widenByte: byteValue = convert.byteToInt64(byte)
  shiftValue: shifted = bits.shiftLeftInt64(value, eight=8)
  addIt: grown = bits.orInt64(shifted, byteValue)
  set value grown
  nextByte: after = math.addInt64(at, one=1)
  set at after
  goto eachByte
:finish
  return value

op storeWord "Store a 32-bit word big-endian at an offset"
  input data machine.Address copied
  input offset Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  goto eachByte
:eachByte loop=while max=four
  doneCheck: done = compare.greaterOrEqualInt64(at, four=4)
  if done finish storeByte
:storeByte in=eachByte
  backOf: back = math.subtractInt64(three=3, at)
  bitsOf: shift = math.multiplyInt64(back, eight=8)
  shiftIt: shifted = bits.shiftRightInt64(value, shift)
  lowOf: low = bits.andInt64(shifted, mask=255)
  narrowIt: byte = convert.int64ToByte(low)
  placeOf: place = math.addInt64(offset, at)
  findByte: byteAt = machine.offset(data, place)
  storeIt: machine.storeByte(byteAt, byte)
  nextByte: after = math.addInt64(at, one=1)
  set at after
  goto eachByte
:finish
  return

op rotate "A 32-bit word rotated right by a number of bits"
  input value Int64 copied
  input count Int64 copied
  output Int64
:begin
  rightPart: right = bits.shiftRightInt64(value, count)
  leftCount: back = math.subtractInt64(thirtyTwo=32, count)
  leftPart: left = bits.shiftLeftInt64(value, back)
  joinIt: joined = bits.orInt64(right, left)
  maskIt: rotated = bits.andInt64(joined, lowWord)
  return rotated

op add32 "Two 32-bit words added, kept to 32 bits"
  input left Int64 copied
  input right Int64 copied
  output Int64
:begin
  addIt: sum = math.addInt64(left, right)
  maskIt: kept = bits.andInt64(sum, lowWord)
  return kept

op slotWord "A whole number of a block of 8-byte slots by its position"
  input block machine.Address copied
  input position Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  offsetOf: offset = math.multiplyInt64(position, eight=8)
  findSlot: slot = machine.offset(block, offset)
  readSlot: value = machine.loadInt64(slot)
  return value

op setSlotWord "Store a whole number in a block of 8-byte slots by its position"
  input block machine.Address copied
  input position Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  offsetOf: offset = math.multiplyInt64(position, eight=8)
  findSlot: slot = machine.offset(block, offset)
  storeSlot: machine.storeInt64(slot, value)
  return

## ---------------------------------------------------------------- SHA-256

op compressBlock "Mix one 64-byte block into the hash's eight words (in a block of slots), with a block of 64 slots for the schedule"
  input state machine.Address copied
  input data machine.Address copied
  input schedule machine.Address copied
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let a Int64 0 mut
  let b Int64 0 mut
  let c Int64 0 mut
  let d Int64 0 mut
  let e Int64 0 mut
  let f Int64 0 mut
  let g Int64 0 mut
  let h Int64 0 mut
:begin
  goto eachWord
:eachWord loop=while max=sixteen
  wordsDone: done = compare.greaterOrEqualInt64(at, sixteen=16)
  if done expand readWord
:readWord in=eachWord
  offsetOf: offset = math.multiplyInt64(at, four=4)
  readIt: value = word(data, offset)
  storeIt: setSlotWord(schedule, at, value)
  nextWord: after = math.addInt64(at, one=1)
  set at after
  goto eachWord
:expand
  goto eachExpand
:eachExpand loop=while max=sixtyFour
  expandDone: expanded = compare.greaterOrEqualInt64(at, sixtyFour=64)
  if expanded start expandOne
:expandOne in=eachExpand
  back15: at15 = math.subtractInt64(at, fifteen=15)
  read15: w15 = slotWord(schedule, at15)
  r7: s0a = rotate(w15, seven=7)
  r18: s0b = rotate(w15, eighteen=18)
  sh3: s0c = bits.shiftRightInt64(w15, three=3)
  x0: s0ab = bits.xorInt64(s0a, s0b)
  x1: s0 = bits.xorInt64(s0ab, s0c)
  back2: at2 = math.subtractInt64(at, two=2)
  read2: w2 = slotWord(schedule, at2)
  r17: s1a = rotate(w2, seventeen=17)
  r19: s1b = rotate(w2, nineteen=19)
  sh10: s1c = bits.shiftRightInt64(w2, ten=10)
  x2: s1ab = bits.xorInt64(s1a, s1b)
  x3: s1 = bits.xorInt64(s1ab, s1c)
  back16: at16 = math.subtractInt64(at, sixteen)
  read16: w16 = slotWord(schedule, at16)
  back7: at7 = math.subtractInt64(at, seven)
  read7: w7 = slotWord(schedule, at7)
  add1: sumA = add32(w16, s0)
  add2: sumB = add32(sumA, w7)
  add3: sumC = add32(sumB, s1)
  storeExpanded: setSlotWord(schedule, at, sumC)
  nextExpand: afterExpand = math.addInt64(at, one)
  set at afterExpand
  goto eachExpand
:start
  readA: a0 = slotWord(state, zero=0)
  set a a0
  readB: b0 = slotWord(state, one)
  set b b0
  readC: c0 = slotWord(state, two)
  set c c0
  readD: d0 = slotWord(state, three)
  set d d0
  readE: e0 = slotWord(state, four)
  set e e0
  readF: f0 = slotWord(state, five=5)
  set f f0
  readG: g0 = slotWord(state, six=6)
  set g g0
  readH: h0 = slotWord(state, seven)
  set h h0
  set at zero
  findConstants: constants = machine.addressOfString(roundConstants)
  goto eachRound
:eachRound loop=while max=sixtyFour
  roundsDone: finished = compare.greaterOrEqualInt64(at, sixtyFour)
  if finished fold round
:round in=eachRound
  e6: sigmaE1 = rotate(e, six)
  e11: sigmaE2 = rotate(e, eleven=11)
  e25: sigmaE3 = rotate(e, twentyFive=25)
  xe1: sigmaE12 = bits.xorInt64(sigmaE1, sigmaE2)
  xe2: bigSigma1 = bits.xorInt64(sigmaE12, sigmaE3)
  andEF: ef = bits.andInt64(e, f)
  notE: notEWide = bits.xorInt64(e, lowWord)
  andNotEG: neg = bits.andInt64(notEWide, g)
  choose: ch = bits.xorInt64(ef, neg)
  constantOffset: kOffset = math.multiplyInt64(at, four)
  readConstant: k = word(constants, kOffset)
  readSchedule: w = slotWord(schedule, at)
  t1a: t1ha = add32(h, bigSigma1)
  t1b: t1hb = add32(t1ha, ch)
  t1c: t1hc = add32(t1hb, k)
  t1d: t1 = add32(t1hc, w)
  a2: sigmaA1 = rotate(a, two)
  a13: sigmaA2 = rotate(a, thirteen=13)
  a22: sigmaA3 = rotate(a, twentyTwo=22)
  xa1: sigmaA12 = bits.xorInt64(sigmaA1, sigmaA2)
  xa2: bigSigma0 = bits.xorInt64(sigmaA12, sigmaA3)
  andAB: ab = bits.andInt64(a, b)
  andAC: ac = bits.andInt64(a, c)
  andBC: bc = bits.andInt64(b, c)
  majority1: majAB = bits.xorInt64(ab, ac)
  majority2: maj = bits.xorInt64(majAB, bc)
  t2a: t2 = add32(bigSigma0, maj)
  set h g
  set g f
  set f e
  newE: eNext = add32(d, t1)
  set e eNext
  set d c
  set c b
  set b a
  newA: aNext = add32(t1, t2)
  set a aNext
  nextRound: afterRound = math.addInt64(at, one)
  set at afterRound
  goto eachRound
:fold
  foldA: sumHA = add32(a0, a)
  storeA: setSlotWord(state, zero, sumHA)
  foldB: sumHB = add32(b0, b)
  storeB: setSlotWord(state, one, sumHB)
  foldC: sumHC = add32(c0, c)
  storeC: setSlotWord(state, two, sumHC)
  foldD: sumHD = add32(d0, d)
  storeD: setSlotWord(state, three, sumHD)
  foldE: sumHE = add32(e0, e)
  storeE: setSlotWord(state, four, sumHE)
  foldF: sumHF = add32(f0, f)
  storeF: setSlotWord(state, five, sumHF)
  foldG: sumHG = add32(g0, g)
  storeG: setSlotWord(state, six, sumHG)
  foldH: sumHH = add32(h0, h)
  storeH: setSlotWord(state, seven, sumHH)
  return

op sha256 "The SHA-256 digest of some bytes, its 32 bytes written at an address"
  invariant hashesLikeHashlib "Writes the digest hashlib.sha256 gives for the bytes"
  input data machine.Address copied
  input bytes Int64 copied
  input digest machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let zero Int64 0
:begin
  withEnd: withMarker = math.addInt64(bytes, nine=9)
  roundUp: padded = math.addInt64(withMarker, sixtyThree=63)
  blocksOf: blocks = math.divideInt64(padded, sixtyFour=64)
  sizeOf: size = math.multiplyInt64(blocks, sixtyFour)
  takeMessage: message = heap.take(size)
  copyIn: machine.copy(message, data, bytes)
  findMarker: marker = machine.offset(message, bytes)
  storeMarker: machine.storeByte(marker, markerByte=128)
  bitsOf: bitLength = math.multiplyInt64(bytes, eight=8)
  lengthAt: lengthOffset = math.subtractInt64(size, eight)
  highOf: high = bits.shiftRightInt64(bitLength, thirtyTwo=32)
  storeHigh: storeWord(message, lengthOffset, high)
  lowAt: lowOffset = math.addInt64(lengthOffset, four=4)
  lowOf: low = bits.andInt64(bitLength, lowWord)
  storeLow: storeWord(message, lowOffset, low)
  takeState: state = heap.take(sixtyFour)
  takeSchedule: schedule = heap.take(fiveTwelve=512)
  findInitial: initial = machine.addressOfString(initialHash)
  goto eachInitial
:eachInitial loop=while max=eight
  initialDone: initialized = compare.greaterOrEqualInt64(at, eight)
  if initialized blocksStart initialOne
:initialOne in=eachInitial
  initialOffset: offset = math.multiplyInt64(at, four)
  readInitial: value = word(initial, offset)
  storeInitial: setSlotWord(state, at, value)
  nextInitial: afterInitial = math.addInt64(at, one=1)
  set at afterInitial
  goto eachInitial
:blocksStart
  set at zero
  goto eachBlock
:eachBlock loop=while max=blocks
  blocksDone: hashed = compare.greaterOrEqualInt64(at, blocks)
  if hashed output compress
:compress in=eachBlock
  blockOffset: blockAt = math.multiplyInt64(at, sixtyFour)
  findBlock: block = machine.offset(message, blockAt)
  mixIt: compressBlock(state, block, schedule)
  nextBlock: afterBlock = math.addInt64(at, one)
  set at afterBlock
  goto eachBlock
:output
  set at zero
  goto eachOutput
:eachOutput loop=while max=eight
  outputDone: written = compare.greaterOrEqualInt64(at, eight)
  if written finish outputOne
:outputOne in=eachOutput
  readHash: hashWord = slotWord(state, at)
  outputOffset: outAt = math.multiplyInt64(at, four)
  storeHash: storeWord(digest, outAt, hashWord)
  nextOutput: afterOutput = math.addInt64(at, one)
  set at afterOutput
  goto eachOutput
:finish
  giveMessage: heap.give(message)
  giveState: heap.give(state)
  giveSchedule: heap.give(schedule)
  return

## ---------------------------------------------------------------- crypto targets

op cryptoSha256 "crypto.sha256: the SHA-256 digest of bytes, 32 bytes into a region"
  invariant digestsBytes "The result slots hold the 32 bytes hashlib.sha256 gives"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readData: data = files.textAt(shape, args, zero=0)
  readBytes: bytes = files.textBytes(shape, args, zero)
  takeDigest: digest = heap.take(thirtyTwo=32)
  hashIt: sha256(data, bytes, digest)
  readRegion: region = slots.addressArg(shape, args, one=1)
  putIt: slots.putText(region, digest, thirtyTwo, results)
  giveDigest: heap.give(digest)
  return

op cryptoHmacSha256 "crypto.hmacSha256: HMAC with SHA-256 of a message under a key, 32 bytes into a region"
  invariant authenticates "The result slots hold the 32 bytes hmac.new(key, message, sha256) gives"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  readKey: key = files.textAt(shape, args, zero=0)
  readKeyBytes: keyBytes = files.textBytes(shape, args, zero)
  readMessage: message = files.textAt(shape, args, one=1)
  readMessageBytes: messageBytes = files.textBytes(shape, args, one)
  takeBlock: block = heap.take(sixtyFour=64)
  longCheck: long = compare.greaterThanInt64(keyBytes, sixtyFour)
  if long hashKey copyKey
:hashKey
  hashIt: sha256(key, keyBytes, block)
  goto pads
:copyKey
  copyIt: machine.copy(block, key, keyBytes)
  goto pads
:pads
  innerSize: innerBytes = math.addInt64(sixtyFour, messageBytes)
  takeInner: inner = heap.take(innerBytes)
  takeOuter: outer = heap.take(ninetySix=96)
  goto eachPad
:eachPad loop=while max=sixtyFour
  padsDone: done = compare.greaterOrEqualInt64(at, sixtyFour)
  if done innerHash padOne
:padOne in=eachPad
  findKeyByte: keyAt = machine.offset(block, at)
  readKeyByte: keyByte = machine.loadByte(keyAt)
  innerByte: innerValue = bits.xorByte(keyByte, ipad=54)
  findInner: innerAt = machine.offset(inner, at)
  storeInner: machine.storeByte(innerAt, innerValue)
  outerByte: outerValue = bits.xorByte(keyByte, opad=92)
  findOuter: outerAt = machine.offset(outer, at)
  storeOuter: machine.storeByte(outerAt, outerValue)
  nextPad: after = math.addInt64(at, one)
  set at after
  goto eachPad
:innerHash
  findMessageCopy: messageAt = machine.offset(inner, sixtyFour)
  copyMessage: machine.copy(messageAt, message, messageBytes)
  findInnerDigest: innerDigest = machine.offset(outer, sixtyFour)
  hashInner: sha256(inner, innerBytes, innerDigest)
  takeDigest: digest = heap.take(thirtyTwo=32)
  hashOuter: sha256(outer, ninetySix, digest)
  readRegion: region = slots.addressArg(shape, args, two=2)
  putIt: slots.putText(region, digest, thirtyTwo, results)
  giveBlock: heap.give(block)
  giveInner: heap.give(inner)
  giveOuter: heap.give(outer)
  giveDigest: heap.give(digest)
  return

op cryptoToHex "crypto.toHex: bytes as lower-case hexadecimal text, two digits a byte, into a region"
  invariant writesHex "The result slots hold bytes.hex()"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  readData: data = files.textAt(shape, args, zero=0)
  readBytes: bytes = files.textBytes(shape, args, zero)
  twice: textBytes = math.multiplyInt64(bytes, two=2)
  readRegion: region = slots.addressArg(shape, args, one=1)
  take: text = regions.allocate(region, textBytes)
  findDigits: digits = machine.addressOfString(hexDigits)
  goto eachByte
:eachByte loop=while max=bytes
  doneCheck: done = compare.greaterOrEqualInt64(at, bytes)
  if done finish hexOne
:hexOne in=eachByte
  findByte: byteAt = machine.offset(data, at)
  readByte: byte = machine.loadByte(byteAt)
  widenByte: value = convert.byteToInt64(byte)
  highOf: high = bits.shiftRightInt64(value, four=4)
  lowOf: low = bits.andInt64(value, fifteen=15)
  findHigh: highDigit = machine.offset(digits, high)
  readHigh: highByte = machine.loadByte(highDigit)
  findLow: lowDigit = machine.offset(digits, low)
  readLow: lowByte = machine.loadByte(lowDigit)
  outOf: outAt = math.multiplyInt64(at, two)
  findOut: out = machine.offset(text, outAt)
  storeHigh: machine.storeByte(out, highByte)
  findOutLow: outLow = machine.offset(out, one=1)
  storeLow: machine.storeByte(outLow, lowByte)
  nextByte: after = math.addInt64(at, one)
  set at after
  goto eachByte
:finish
  storeText: machine.storeAddress(results, text)
  findLength: lengthSlot = machine.offset(results, eight=8)
  storeLength: machine.storeInt64(lengthSlot, textBytes)
  return

op cryptoConstantTimeEquals "crypto.constantTimeEquals: whether two byte strings are the same, compared in time that depends on their lengths only, as hmac.compare_digest compares"
  invariant comparesEvenly "The result slot holds 1 when the bytes are the same, otherwise 0"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let differ Int64 0 mut
:begin
  readLeft: left = files.textAt(shape, args, zero=0)
  readLeftBytes: leftBytes = files.textBytes(shape, args, zero)
  readRight: right = files.textAt(shape, args, one=1)
  readRightBytes: rightBytes = files.textBytes(shape, args, one)
  sameLength: equalLength = compare.equalInt64(leftBytes, rightBytes)
  if equalLength eachByte different
:eachByte loop=while max=leftBytes
  doneCheck: done = compare.greaterOrEqualInt64(at, leftBytes)
  if done decide compareByte
:compareByte in=eachByte
  findLeft: leftAt = machine.offset(left, at)
  readLeftByte: leftByte = machine.loadByte(leftAt)
  findRight: rightAt = machine.offset(right, at)
  readRightByte: rightByte = machine.loadByte(rightAt)
  widenLeft: leftValue = convert.byteToInt64(leftByte)
  widenRight: rightValue = convert.byteToInt64(rightByte)
  mixIt: mixed = bits.xorInt64(leftValue, rightValue)
  keepIt: kept = bits.orInt64(differ, mixed)
  set differ kept
  nextByte: after = math.addInt64(at, one)
  set at after
  goto eachByte
:decide
  sameCheck: same = compare.equalInt64(differ, zero)
  if same matched different
:matched
  storeYes: machine.storeInt64(results, one)
  return
:different
  storeNo: machine.storeInt64(results, zero)
  return

@tests

## Tests build a call's shape and slots in the last 4 KiB of machine.state: the shape from byte 61440, the
## arguments from 61952, the results from 62016.

op prepareTwo "Make the tests' call two parameters of two slots and one of one, the texts and a region"
  input first String borrowed
  input second String borrowed
  input region machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  findShape: shape = machine.offset(state, shapeAt=61440)
  findParams: paramsSlot = machine.offset(shape, twentyFour=24)
  storeParams: machine.storeInt64(paramsSlot, three=3)
  storeCountA: setSlotWord(shape, five=5, two=2)
  storeCountB: setSlotWord(shape, six=6, two)
  storeCountC: setSlotWord(shape, seven=7, one=1)
  storeStartA: setSlotWord(shape, twentyNine=29, zero=0)
  storeStartB: setSlotWord(shape, thirty=30, two)
  storeStartC: setSlotWord(shape, thirtyOne=31, four=4)
  findArgs: args = machine.offset(state, argsAt=61952)
  findFirst: firstAt = machine.addressOfString(first)
  firstLength: firstBytes = string.byteLength(first)
  storeFirst: setSlotWord(args, zero, firstBytes)
  storeFirstAt: machine.storeAddress(args, firstAt)
  storeFirstBytes: setSlotWord(args, one, firstBytes)
  findSecond: secondAt = machine.addressOfString(second)
  secondLength: secondBytes = string.byteLength(second)
  findSecondSlot: secondSlot = machine.offset(args, sixteen=16)
  storeSecondAt: machine.storeAddress(secondSlot, secondAt)
  storeSecondBytes: setSlotWord(args, three, secondBytes)
  findRegionSlot: regionSlot = machine.offset(args, thirtyTwo=32)
  storeRegion: machine.storeAddress(regionSlot, region)
  return shape

op expectHex "Compare the hexadecimal text of 32 bytes in the result slots with what is expected"
  input wanted String borrowed
  input region machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findState: state = machine.state()
  findResults: results = machine.offset(state, resultsAt=62016)
  readDigest: digest = machine.loadAddress(results)
  findArgs: args = machine.offset(state, argsAt=61952)
  storeDigest: machine.storeAddress(args, digest)
  storeLength: setSlotWord(args, one=1, thirtyTwo=32)
  findRegionSlot: regionSlot = machine.offset(args, sixteen=16)
  storeRegion: machine.storeAddress(regionSlot, region)
  findShape: shape = machine.offset(state, shapeAt=61440)
  findParams: paramsSlot = machine.offset(shape, twentyFour=24)
  storeParams: machine.storeInt64(paramsSlot, two=2)
  storeCountA: setSlotWord(shape, five=5, two)
  storeCountB: setSlotWord(shape, six=6, one)
  storeStartA: setSlotWord(shape, twentyNine=29, zero=0)
  storeStartB: setSlotWord(shape, thirty=30, two)
  hexIt: cryptoToHex(shape, args, results)
  readText: text = machine.loadAddress(results)
  findTextLength: textLengthSlot = machine.offset(results, eight=8)
  readTextLength: textLength = machine.loadInt64(textLengthSlot)
  findWanted: wantedAt = machine.addressOfString(wanted)
  wantedLength: wantedBytes = string.byteLength(wanted)
  compareLength: test.assertEqualInt64(wantedBytes, textLength)
  compareText: order = machine.compare(text, wantedAt, wantedBytes)
  widenOrder: orderValue = convert.int32ToInt64(order)
  compareIt: test.assertEqualInt64(zero, orderValue)
  return

test cryptoTest "SHA-256 and HMAC-SHA-256 give what hashlib and hmac give, hex text is bytes.hex(), and equal bytes compare equal"
  verifies sha256 hashesLikeHashlib
  verifies cryptoSha256 digestsBytes
  verifies cryptoHmacSha256 authenticates
  verifies cryptoToHex writesHex
  verifies cryptoConstantTimeEquals comparesEvenly
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let label String "crypto test"
  let abc String "abc"
  let long String "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
:begin
  findLabel: labelAt = machine.addressOfString(label)
  labelLength: labelBytes = string.byteLength(label)
  make: region = regions.newRegion(capacity=65536, labelAt, labelBytes)
  shapeAbc: shape1 = prepareTwo(abc, abc, region)
  findState: state = machine.state()
  findArgs: args = machine.offset(state, argsAt=61952)
  findResults: results = machine.offset(state, resultsAt=62016)
  storeRegionFirst: setSlotWord(args, two=2, zero=0)
  findRegionSlot: regionSlot = machine.offset(args, sixteen=16)
  storeRegionSlot: machine.storeAddress(regionSlot, region)
  findShape: shape = machine.offset(state, shapeAt=61440)
  findParams: paramsSlot = machine.offset(shape, twentyFour=24)
  storeParams: machine.storeInt64(paramsSlot, two)
  storeCountB: setSlotWord(shape, six=6, one=1)
  hashIt: cryptoSha256(shape, args, results)
  shapeHex: shape7 = prepareTwo(az="Az", az, region)
  storeHexRegion: machine.storeAddress(regionSlot, region)
  storeHexParams: machine.storeInt64(paramsSlot, two)
  storeHexCount: setSlotWord(shape, six, one)
  hexIt: cryptoToHex(shape, args, results)
  readHex: hexText = machine.loadAddress(results)
  findWantedHex: wantedHex = machine.addressOfString(hexAz="417a")
  compareHex: hexOrder = machine.compare(hexText, wantedHex, four=4)
  widenHex: hexValue = convert.int32ToInt64(hexOrder)
  expectHexAz: test.assertEqualInt64(zero, hexValue)
  shapeAgain: shape8 = prepareTwo(abc, abc, region)
  storeAgainRegion: machine.storeAddress(regionSlot, region)
  storeAgainParams: machine.storeInt64(paramsSlot, two)
  storeAgainCount: setSlotWord(shape, six, one)
  hashAgain: cryptoSha256(shape, args, results)
  expectAbc: expectHex(abcDigest="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", region)
  shapeHmac: shape2 = prepareTwo(key="key", message="The quick brown fox", region)
  macIt: cryptoHmacSha256(shape2, args, results)
  expectMac: expectHex(macDigest="203d1e5cedd2d18f8c5a3beff0bd9c1ebcb97097dfcb288c46b00c9227fde2c0", region)
  shapeLong: shape3 = prepareTwo(long, abc, region)
  longMac: cryptoHmacSha256(shape3, args, results)
  expectLong: expectHex(longDigest="343c0393c4ae8ef0398a29a5155358e5cad0b9fcb70afdb8cd9d0e83abdd9378", region)
  shapeSame: shape4 = prepareTwo(abc, abc, region)
  sameIt: cryptoConstantTimeEquals(shape4, args, results)
  readSame: same = machine.loadInt64(results)
  expectSame: test.assertEqualInt64(one, same)
  shapeDiffer: shape5 = prepareTwo(abc, abd="abd", region)
  differIt: cryptoConstantTimeEquals(shape5, args, results)
  readDiffer: differ = machine.loadInt64(results)
  expectDiffer: test.assertEqualInt64(zero, differ)
  shapeLength: shape6 = prepareTwo(abc, ab="ab", region)
  lengthIt: cryptoConstantTimeEquals(shape6, args, results)
  readLength: lengthSame = machine.loadInt64(results)
  expectLength: test.assertEqualInt64(zero, lengthSame)
  findAbc: abcAt = machine.addressOfString(abc)
  takeDigest: digest = heap.take(thirtyTwo=32)
  directIt: sha256(abcAt, three=3, digest)
  readFirst: firstByte = machine.loadByte(digest)
  widenFirst: firstValue = convert.byteToInt64(firstByte)
  expectFirst: test.assertEqualInt64(oneEightySix=186, firstValue)
  giveDigest: heap.give(digest)
  free: regions.release(region)
  return
