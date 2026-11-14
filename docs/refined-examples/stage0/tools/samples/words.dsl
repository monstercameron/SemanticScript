## A stage0 sample from the audit: words split with byte tests, a reversed
## sentence built in a buffer, and numbers parsed from text.
module words "Split a sentence into words with byte tests, build a reversed sentence in a buffer, and parse numbers"
  path words
  imports standard.console standard.math standard.compare standard.list standard.string standard.byte standard.buffer standard.convert
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

instance Texts "The words of a sentence, in order" list.List String

op splitWords "The words of a text, split at spaces"
  input text String borrowed
  input region Region borrowed
  output Texts
  owner region
  let index Int64 0 mut
  let start Int64 0 mut
  let inWord Bool false mut
  let yes Bool true
  let no Bool false
:begin
  makeList: found = Texts.new(region)
  measure: length = string.byteLength(text)
  goto scan
:scan loop=while max=length
  endCheck: atEnd = compare.greaterOrEqualInt64(index, length)
  if atEnd finish readOne
:readOne in=scan
  fetch: b = string.byteAtOrTrap(text, index)
  spaceCheck: isSpace = byte.isSpace(b)
  if isSpace onSpace onOther
:onSpace in=scan
  if inWord closeWord advance
:closeWord in=scan
  wordLength: len = math.subtractInt64(index, start)
  cut: word = string.slice(text, start, len) ? advance
  copyWord: owned = string.concat(word, empty="", region)
  keep: Texts.append(found, owned)
  set inWord no
  goto advance
:onOther in=scan
  if inWord advance openWord
:openWord in=scan
  set start index
  set inWord yes
  goto advance
:advance in=scan
  step: nextIndex = math.addInt64(index, 1)
  set index nextIndex
  goto scan
:finish
  if inWord lastWord done
:lastWord
  lastLength: len2 = math.subtractInt64(index, start)
  cutLast: word2 = string.slice(text, start, len2) ? done
  copyLast: owned2 = string.concat(word2, empty, region)
  keepLast: Texts.append(found, owned2)
  goto done
:done
  return found

op main "Split, reverse, and parse"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  region scratch 1048576
  let position Int64 0 mut
  let total Int64 0 mut
  let digits Int64 0 mut
  let okCode ExitCode 0
:begin
  split: parts = splitWords(sentence="  seven  apples and 12 pears, 30 plums ", scratch)
  countParts: partCount = Texts.length(parts)
  writeCountLead: console.write(countText="words: ") ~
  writeCount: console.writeIntegerLine(partCount) ~
  makeBuffer: out = buffer.new(scratch)
  set position partCount
  goto backwards
:backwards loop=while max=partCount
  zeroCheck: atZero = compare.lessOrEqualInt64(position, 0)
  if atZero reversed takeOne
:takeOne in=backwards
  down: lower = math.subtractInt64(position, 1)
  set position lower
  readPart: part = Texts.getOrTrap(parts, position)
  addPart: buffer.appendString(out, part)
  addSpace: buffer.appendByte(out, dash=45)
  parse: number = string.toInt64(part) ? backwards
  addTotal: nextTotal = math.addInt64(total, number)
  set total nextTotal
  goto backwards
:reversed
  addTotalText: buffer.appendInt64(out, total)
  toText: joined = buffer.toString(out, scratch) ? broken
  writeJoined: console.writeLine(joined) ~
  bufferLength: blen = buffer.length(out)
  writeLenLead: console.write(lenText="buffer: ") ~
  writeLen: console.writeIntegerLine(blen) ~
  findApples: at = string.find(joined, apples="apples") ? noApples
  writeAtLead: console.write(atText="apples at ") ~
  writeAt: console.writeIntegerLine(at) ~
  goto prefixes
:noApples
  writeNo: console.writeLine(noText="no apples") ~
  goto prefixes
:prefixes
  prefixCheck: starts = string.startsWith(joined, plums="plums")
  if starts yesPrefix noPrefix
:yesPrefix
  writeYes: console.writeLine(yesText="starts with plums") ~
  goto bytes
:noPrefix
  writeNoP: console.writeLine(noPText="does not start with plums") ~
  goto bytes
:bytes
  readByte: first = string.byteAt(joined, zero=0) ? broken
  asNumber: firstNumber = convert.byteToInt64(first)
  writeByteLead: console.write(byteText="first byte: ") ~
  writeByte: console.writeIntegerLine(firstNumber) ~
  equalCheck: same = string.equals(joined, joined)
  if same sameText broken
:sameText
  joinText: both = string.concat(eqText="equal ", joined, scratch)
  writeBoth: console.writeLine(both) ~
  return okCode
:broken
  writeBroken: console.writeLine(brokenText="broken") ~
  return okCode
