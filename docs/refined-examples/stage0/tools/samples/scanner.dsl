## A stage0 sample: operations as values, positions in text, a list changed
## in place, and an operation that raises a standard library error. It steps
## through UTF-8 text a character at a time with `string.advancePosition`,
## choosing what to step over by a value of an `operationType` (called with
## `invokesReference`), counts vowels the same way, changes a list's items
## with `set` (branching on a position past its end), and exits with code 0:
##
##   word ends at 6, line 1, column 6
##   next word at 7, line 1, column 7
##   line 2 starts at 14
##   vowels: 5
##   counts: 1 5 3
##   no slot 7
##   byte after: 195
##   nothing after the end
module scanner "Step through text by rules passed as values, and change a list in place"
  path scanner
  imports standard.console standard.math standard.compare standard.string standard.byte standard.list standard.logic standard.convert
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

optype ByteTest "A test of one byte"
  input value Byte copied
  output Bool

instance Counts "A few numbers changed in place" list.List Int64

op isWordByte "Decide whether a byte belongs to a word: anything but a space or a newline"
  input value Byte copied
  output Bool
:begin
  spaceCheck: isSpace = byte.isSpace(value)
  wordCheck: isWord = logic.not(isSpace)
  return isWord

op isBlankByte "Decide whether a byte is a space"
  input value Byte copied
  output Bool
  let space Byte 32
:begin
  sameCheck: isBlank = compare.equalByte(value, space)
  return isBlank

op isVowel "Decide whether a byte is a lowercase ASCII vowel"
  input value Byte copied
  output Bool
  let a Byte 97
  let e Byte 101
  let i Byte 105
  let o Byte 111
  let u Byte 117
:begin
  aCheck: isA = compare.equalByte(value, a)
  eCheck: isE = compare.equalByte(value, e)
  iCheck: isI = compare.equalByte(value, i)
  oCheck: isO = compare.equalByte(value, o)
  uCheck: isU = compare.equalByte(value, u)
  ae: eitherAE = logic.or(isA, isE)
  io: eitherIO = logic.or(isI, isO)
  aeio: anyAEIO = logic.or(eitherAE, eitherIO)
  all: isVowelByte = logic.or(anyAEIO, isU)
  return isVowelByte

op skipWhile "Step past every character from a position on that a test accepts"
  input text String borrowed
  input start string.Position copied
  input test ByteTest copied
  output string.Position
  let position string.Position start mut
:begin
  measure: length = string.byteLength(text)
  goto advance
:advance loop=while max=length
  readOffset: offset = string.Position.offset(position)
  readByte: current = string.byteAt(text, offset) ? finish
  judge: accepted = *test(current)
  if accepted step finish
:step in=advance
  stepOver: nextPosition = string.advancePosition(text, position) ? finish
  set position nextPosition
  goto advance
:finish
  return position

op countMatching "Count the bytes of a text a test accepts"
  input text String borrowed
  input test ByteTest copied
  output Int64
  let index Int64 0 mut
  let total Int64 0 mut
:begin
  measure: length = string.byteLength(text)
  goto eachByte
:eachByte loop=while max=length
  doneCheck: allRead = compare.greaterOrEqualInt64(index, length)
  if allRead done readByte
:readByte in=eachByte
  fetch: current = string.byteAtOrTrap(text, index)
  stepIndex: nextIndex = math.addInt64(index, 1)
  set index nextIndex
  judge: accepted = *test(current)
  if accepted countIt eachByte
:countIt in=eachByte
  addOne: nextTotal = math.addInt64(total, 1)
  set total nextTotal
  goto eachByte
:done
  return total

op byteAfter "The first byte of the character after a position's, or the standard library's error when there is none"
  input text String borrowed
  input position string.Position copied
  output Byte
  raises string.StringIndexError
:begin
  stepOver: moved = string.advancePosition(text, position) ?^
  readOffset: offset = string.Position.offset(moved)
  readByte: value = string.byteAt(text, offset) ?^
  return value

op main "Step through text by rules, count vowels, and change a list in place"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  region store 1048576
  let text String "héllo wörld\nsecond line"
  let wordTest ByteTest isWordByte
  let blankTest ByteTest isBlankByte
  let vowelTest ByteTest isVowel
  let okCode ExitCode 0
:begin
  makeStart: start = string.Position.new(0, 1, 1)
  skipWord: wordEnd = skipWhile(text, start, wordTest)
  describeWordEnd: describePosition(wordText="word ends at ", wordEnd)
  skipBlank: nextWord = skipWhile(text, wordEnd, blankTest)
  describeNextWord: describePosition(nextText="next word at ", nextWord)
  skipSecond: secondEnd = skipWhile(text, nextWord, wordTest)
  stepLine: lineStart = string.advancePosition(text, secondEnd) ? noLine
  readLineStart: lineOffset = string.Position.offset(lineStart)
  readLineNumber: lineNumber = string.Position.line(lineStart)
  lineText: lineDigits = string.fromInt64(lineNumber, store)
  joinLine: lineLead = string.concat(lineWord="line ", lineDigits, store)
  joinStarts: lineLabel = string.concat(lineLead, startsText=" starts at ", store)
  writeLineLabel: console.write(lineLabel) ~
  writeLineOffset: console.writeIntegerLine(lineOffset) ~
  countVowels: vowels = countMatching(text, vowelTest)
  writeVowels: console.write(vowelsText="vowels: ") ~
  writeVowelCount: console.writeIntegerLine(vowels) ~
  makeCounts: counts = Counts.new(store)
  addFirst: Counts.append(counts, one=1)
  addSecond: Counts.append(counts, two=2)
  addThird: Counts.append(counts, three=3)
  setSecond: Counts.set(counts, one, five=5) ? noSlot
  setSeventh: Counts.set(counts, seven=7, nine=9) ? noSeventh
  goto printCounts
:noSeventh
  writeCountsLabel: console.write(countsText="counts:") ~
  countItems: itemCount = Counts.length(counts)
  goto eachCount
:eachCount loop=forEach max=itemCount over=counts
  next counts item printItem countsDone
:printItem in=eachCount
  writeSpace: console.write(space=" ") ~
  itemText: itemDigits = string.fromInt64(item, store)
  writeItem: console.write(itemDigits) ~
  goto eachCount
:countsDone
  writeEnd: console.writeLine(empty="") ~
  writeNoSlot: console.writeLine(noSlotText="no slot 7") ~
  readAfter: after = byteAfter(text, start) ? noAfter
  readAfterValue: afterNumber = convert.byteToInt64(after)
  writeAfter: console.write(afterText="byte after: ") ~
  writeAfterValue: console.writeIntegerLine(afterNumber) ~
  makeEnd: endPosition = string.Position.new(twentySix=26, two, three)
  readAfterEnd: afterEnd = byteAfter(text, endPosition) ? nothingAfter
  goto finished
:nothingAfter
  writeNothing: console.writeLine(nothingText="nothing after the end") ~
  goto finished
:printCounts
  writeOops: console.writeLine(oopsText="position 7 was set") ~
  goto finished
:noSlot
  writeNoSecond: console.writeLine(noSecondText="no slot 1") ~
  goto finished
:noLine
  writeNoLine: console.writeLine(noLineText="no second line") ~
  goto finished
:noAfter
  writeNoAfter: console.writeLine(noAfterText="no byte after the start") ~
  goto finished
:finished
  return okCode

op describePosition "Print a label, then a position as `<offset>, line <line>, column <column>`"
  input label String borrowed
  input position string.Position copied
  effect write console.stdout
  uses stdoutWriter
  region scratch 65536
:begin
  readOffset: offset = string.Position.offset(position)
  readLine: line = string.Position.line(position)
  readColumn: column = string.Position.column(position)
  offsetText: offsetDigits = string.fromInt64(offset, scratch)
  lineText: lineDigits = string.fromInt64(line, scratch)
  columnText: columnDigits = string.fromInt64(column, scratch)
  joinLabel: withOffset = string.concat(label, offsetDigits, scratch)
  joinLineWord: withLineWord = string.concat(withOffset, lineWord=", line ", scratch)
  joinLine: withLine = string.concat(withLineWord, lineDigits, scratch)
  joinColumnWord: withColumnWord = string.concat(withLine, columnWord=", column ", scratch)
  joinColumn: described = string.concat(withColumnWord, columnDigits, scratch)
  writeIt: console.writeLine(described) ~
  return
