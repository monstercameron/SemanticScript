module memory "Copy, fill, and compare ranges of memory: the four C functions compiled code calls, and the byte comparisons of the runtime"
  path memory
  imports standard.machine standard.math standard.compare standard.convert standard.bits standard.test
  exports copyForward copyBackward moveBytes fillBytes compareBytes bytesEqual findBytes

capability memoryAccess "Authority to read and write memory by address" use machine.memory none

## ---------------------------------------------------------------- memcpy, memmove, memset, memcmp

op copyForward "Copy a range of bytes to another, first byte first, eight bytes at a time while eight remain: memcpy"
  invariant copiesEveryByte "After the copy, each byte of the target range equals the byte at the same place in the source range"
  input target machine.Address copied
  input source machine.Address copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi c "memcpy"
  let index Int64 0 mut
  let eight Int64 8
:begin
  countWords: words = math.divideInt64(bytes, eight)
  goto eachWord
:eachWord loop=while max=words
  wordsLeft: wordEnd = math.addInt64(index, eight)
  wordsDone: pastWords = compare.greaterThanInt64(wordEnd, bytes)
  if pastWords eachByte copyWord
:copyWord in=eachWord
  findWordFrom: wordFrom = machine.offset(source, index)
  readWord: word = machine.loadInt64(wordFrom)
  findWordTo: wordTo = machine.offset(target, index)
  writeWord: machine.storeInt64(wordTo, word)
  set index wordEnd
  goto eachWord
:eachByte loop=while max=eight
  bytesDone: done = compare.greaterOrEqualInt64(index, bytes)
  if done finish copyByte
:copyByte in=eachByte
  findFrom: from = machine.offset(source, index)
  readByte: value = machine.loadByte(from)
  findTo: to = machine.offset(target, index)
  writeByte: machine.storeByte(to, value)
  advance: nextIndex = math.addInt64(index, 1)
  set index nextIndex
  goto eachByte
:finish
  return target

op copyBackward "Copy a range of bytes to another, last byte first, so a target that overlaps the end of its source is copied whole"
  invariant copiesOverlapping "A target that starts inside its source receives the source's bytes as they were before the copy"
  input target machine.Address copied
  input source machine.Address copied
  input bytes Int64 copied
  effect use machine.memory
  uses memoryAccess
  let index Int64 0 mut
:begin
  set index bytes
  goto eachByte
:eachByte loop=while max=bytes
  bytesDone: done = compare.lessOrEqualInt64(index, zero=0)
  if done finish copyByte
:copyByte in=eachByte
  back: nextIndex = math.subtractInt64(index, one=1)
  set index nextIndex
  findFrom: from = machine.offset(source, nextIndex)
  readByte: value = machine.loadByte(from)
  findTo: to = machine.offset(target, nextIndex)
  writeByte: machine.storeByte(to, value)
  goto eachByte
:finish
  return

op moveBytes "Copy a range of bytes to another that may overlap it: memmove"
  invariant movesOverlapping "The target holds the source's bytes as they were before the move, whichever way the ranges overlap"
  input target machine.Address copied
  input source machine.Address copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi c "memmove"
:begin
  sourceAfter: belowCheck = machine.lessThan(target, source)
  if belowCheck forward checkEnd
:checkEnd
  findSourceEnd: sourceEnd = machine.offset(source, bytes)
  startsInside: inside = machine.lessThan(target, sourceEnd)
  if inside backward forward
:forward
  copyUp: copied = copyForward(target, source, bytes)
  return copied
:backward
  copyDown: copyBackward(target, source, bytes)
  return target

op fillBytes "Set every byte of a range to the low eight bits of a value, eight bytes at a time while eight remain: memset"
  invariant fillsEveryByte "After the fill, every byte of the range is the value's low eight bits, and no byte outside it changed"
  input target machine.Address copied
  input value Int32 copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi c "memset"
  let index Int64 0 mut
  let eight Int64 8
:begin
  lowBits: low = bits.andInt32(value, lowMask=255)
  lowWide: lowValue = convert.int32ToInt64(low)
  toByte: byte = convert.int64ToByte(lowValue)
  widen: wide = convert.byteToUInt64(byte)
  spread: pattern = math.multiplyUInt64(wide, everyByte=72340172838076673)
  countWords: words = math.divideInt64(bytes, eight)
  goto eachWord
:eachWord loop=while max=words
  wordsLeft: wordEnd = math.addInt64(index, eight)
  wordsDone: pastWords = compare.greaterThanInt64(wordEnd, bytes)
  if pastWords eachByte fillWord
:fillWord in=eachWord
  findWordTo: wordTo = machine.offset(target, index)
  writeWord: machine.storeUInt64(wordTo, pattern)
  set index wordEnd
  goto eachWord
:eachByte loop=while max=eight
  bytesDone: done = compare.greaterOrEqualInt64(index, bytes)
  if done finish fillByte
:fillByte in=eachByte
  findTo: to = machine.offset(target, index)
  writeByte: machine.storeByte(to, byte)
  advance: nextIndex = math.addInt64(index, 1)
  set index nextIndex
  goto eachByte
:finish
  return target

op compareBytes "Compare two ranges of the same length byte by byte: memcmp"
  invariant ordersByFirstDifference "Gives -1 or 1 as the first differing byte of the left range is below or above the right's, as unsigned bytes, and 0 when no byte differs"
  input left machine.Address copied
  input right machine.Address copied
  input bytes Int64 copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi c "memcmp"
:begin
  compareRanges: order = machine.compare(left, right, bytes)
  return order

## ---------------------------------------------------------------- the runtime's byte comparisons

op bytesEqual "Whether two ranges hold the same bytes: 1 when their lengths and every byte agree, otherwise 0"
  invariant equalByContent "Two ranges are equal exactly when they have the same length and the same bytes, wherever they are"
  input left machine.Address copied
  input leftBytes Int64 copied
  input right machine.Address copied
  input rightBytes Int64 copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi c "refined_bytes_equal"
  let yes Int32 1
  let no Int32 0
:begin
  lengthCheck: sameLength = compare.equalInt64(leftBytes, rightBytes)
  if sameLength compareRanges different
:compareRanges
  compareContent: order = machine.compare(left, right, leftBytes)
  contentCheck: same = compare.equalInt32(order, no)
  if same equal different
:equal
  return yes
:different
  return no

op findBytes "The offset of the first place a needle's bytes occur in a haystack, 0 for an empty needle, or -1 when they occur nowhere"
  invariant findsFirst "Gives the smallest offset at which the needle occurs, or -1 when it occurs nowhere; an empty needle occurs at 0"
  input haystack machine.Address copied
  input haystackBytes Int64 copied
  input needle machine.Address copied
  input needleBytes Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi c "refined_find"
  let index Int64 0 mut
  let missingAt Int64 -1
:begin
  emptyCheck: empty = compare.lessOrEqualInt64(needleBytes, zero=0)
  if empty found eachPlace
:eachPlace loop=while max=haystackBytes
  findEnd: placeEnd = math.addInt64(index, needleBytes)
  pastCheck: past = compare.greaterThanInt64(placeEnd, haystackBytes)
  if past missing comparePlace
:comparePlace in=eachPlace
  findPlace: place = machine.offset(haystack, index)
  compareHere: order = machine.compare(place, needle, needleBytes)
  sameCheck: same = compare.equalInt32(order, zero32=0)
  if same found nextPlace
:nextPlace in=eachPlace
  advance: nextIndex = math.addInt64(index, 1)
  set index nextIndex
  goto eachPlace
:found
  return index
:missing
  return missingAt

@tests

## Tests write in the last 4 KiB of machine.state (from byte 61440), which the runtime's own state never reaches.

test copyForwardTest "memcpy copies whole words and the bytes after them"
  verifies copyForward copiesEveryByte
  effect use machine.memory
  uses memoryAccess
  let text String "abcdefghijklmnopqrstu"
:begin
  findState: state = machine.state()
  findScratch: scratch = machine.offset(state, scratchAt=61440)
  findText: from = machine.addressOfString(text)
  copyText: copied = copyForward(scratch, from, twentyOne=21)
  viewCopy: view = machine.stringAt(copied, twentyOne)
  expectCopy: test.assertEqualString(text, view)
  return

test copyBackwardTest "Copying last byte first moves a range up over itself intact"
  verifies copyBackward copiesOverlapping
  effect use machine.memory
  uses memoryAccess
  let text String "abcdefgh"
  let expected String "ababcdef"
:begin
  findState: state = machine.state()
  findScratch: scratch = machine.offset(state, scratchAt=61440)
  findText: from = machine.addressOfString(text)
  copyText: copied = copyForward(scratch, from, eight=8)
  findUp: up = machine.offset(scratch, two=2)
  copyUp: copyBackward(up, scratch, six=6)
  viewCopy: view = machine.stringAt(scratch, eight)
  expectCopy: test.assertEqualString(expected, view)
  return

test moveBytesTest "memmove gives the source's old bytes whichever way the ranges overlap"
  verifies moveBytes movesOverlapping
  effect use machine.memory
  uses memoryAccess
  let text String "abcdefgh"
  let movedUp String "ababcdef"
  let movedDown String "cdefghgh"
:begin
  findState: state = machine.state()
  findScratch: scratch = machine.offset(state, scratchAt=61440)
  findText: from = machine.addressOfString(text)
  copyText: copied = copyForward(scratch, from, eight=8)
  findUp: up = machine.offset(scratch, two=2)
  moveUp: movedTo = moveBytes(up, scratch, six=6)
  viewUp: upView = machine.stringAt(scratch, eight)
  expectUp: test.assertEqualString(movedUp, upView)
  copyAgain: copiedAgain = copyForward(scratch, from, eight)
  moveDown: movedBack = moveBytes(scratch, up, six)
  viewDown: downView = machine.stringAt(scratch, eight)
  expectDown: test.assertEqualString(movedDown, downView)
  return

test fillBytesTest "memset sets every byte of its range to the value's low byte and no other byte"
  verifies fillBytes fillsEveryByte
  effect use machine.memory
  uses memoryAccess
  let text String "xxxxxxxxxxxx"
  let expected String "xAAAAAAAAAAx"
:begin
  findState: state = machine.state()
  findScratch: scratch = machine.offset(state, scratchAt=61440)
  findText: from = machine.addressOfString(text)
  copyText: copied = copyForward(scratch, from, twelve=12)
  findInside: inside = machine.offset(scratch, one=1)
  fillInside: filled = fillBytes(inside, letterA=321, ten=10)
  viewFill: view = machine.stringAt(scratch, twelve)
  expectFill: test.assertEqualString(expected, view)
  return

test compareBytesTest "memcmp orders two ranges by their first differing byte, as unsigned bytes"
  verifies compareBytes ordersByFirstDifference
  effect use machine.memory
  uses memoryAccess
  let low String "abc"
  let high String "abd"
  let accented String "é"
  let plain String "e"
:begin
  findLow: lowAt = machine.addressOfString(low)
  findHigh: highAt = machine.addressOfString(high)
  findAccented: accentedAt = machine.addressOfString(accented)
  findPlain: plainAt = machine.addressOfString(plain)
  compareBelow: below = compareBytes(lowAt, highAt, three=3)
  belowWide: belowValue = convert.int32ToInt64(below)
  expectBelow: test.assertEqualInt64(minusOne=-1, belowValue)
  compareAbove: above = compareBytes(highAt, lowAt, three)
  aboveWide: aboveValue = convert.int32ToInt64(above)
  expectAbove: test.assertEqualInt64(one=1, aboveValue)
  compareSame: same = compareBytes(lowAt, lowAt, three)
  sameWide: sameValue = convert.int32ToInt64(same)
  expectSame: test.assertEqualInt64(zero=0, sameValue)
  compareUnsigned: unsigned = compareBytes(accentedAt, plainAt, one)
  unsignedWide: unsignedValue = convert.int32ToInt64(unsigned)
  expectUnsigned: test.assertEqualInt64(one, unsignedValue)
  return

test bytesEqualTest "Two ranges are equal by length and content, not by where they are"
  verifies bytesEqual equalByContent
  effect use machine.memory
  uses memoryAccess
  let text String "abc"
  let other String "abd"
:begin
  findState: state = machine.state()
  findScratch: scratch = machine.offset(state, scratchAt=61440)
  findText: from = machine.addressOfString(text)
  findOther: otherAt = machine.addressOfString(other)
  copyText: copied = copyForward(scratch, from, three=3)
  compareCopy: sameCopy = bytesEqual(from, three, scratch, three)
  copyWide: sameCopyValue = convert.int32ToInt64(sameCopy)
  expectCopy: test.assertEqualInt64(one=1, sameCopyValue)
  compareOther: sameOther = bytesEqual(from, three, otherAt, three)
  otherWide: sameOtherValue = convert.int32ToInt64(sameOther)
  expectOther: test.assertEqualInt64(zero=0, sameOtherValue)
  compareShorter: sameShorter = bytesEqual(from, three, scratch, two=2)
  shorterWide: sameShorterValue = convert.int32ToInt64(sameShorter)
  expectShorter: test.assertEqualInt64(zero, sameShorterValue)
  return

test findBytesTest "The first place a needle occurs, 0 for an empty needle, -1 for one that does not occur"
  verifies findBytes findsFirst
  effect use machine.memory
  uses memoryAccess
  let haystack String "aabaab"
  let needle String "ab"
  let absent String "abb"
:begin
  findHaystack: haystackAt = machine.addressOfString(haystack)
  findNeedle: needleAt = machine.addressOfString(needle)
  findAbsent: absentAt = machine.addressOfString(absent)
  searchFirst: first = findBytes(haystackAt, six=6, needleAt, two=2)
  expectFirst: test.assertEqualInt64(one=1, first)
  searchEmpty: empty = findBytes(haystackAt, six, needleAt, zero=0)
  expectEmpty: test.assertEqualInt64(zero, empty)
  searchAbsent: missing = findBytes(haystackAt, six, absentAt, three=3)
  expectAbsent: test.assertEqualInt64(minusOne=-1, missing)
  return
