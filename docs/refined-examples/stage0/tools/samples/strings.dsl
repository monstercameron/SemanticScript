## A stage0 sample: text. It slices a word out of a sentence, reads a byte,
## joins texts and a number in a region, compares texts, finds a word (and
## branches when a word is missing), and reads constants of several types. It
## exits with code 0:
##
##   brown
##   byte: 113
##   length: 19
##   quick brown fox 42
##   equal: true
##   fox at 16
##   no cat
##   limit: 3
module strings "Slice, search, join, and compare text"
  path strings
  imports standard.console standard.string standard.convert
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

constant sentence "The text the sample reads" String "the quick brown fox"

constant limit "A whole number" Int64 3

constant verbose "Whether the sample prints its limit" Bool true

op main "Read and build text, printing what is found"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  region scratch 65536
  let okCode ExitCode 0
  let failCode ExitCode 1
:begin
  cutBrown: brown = string.slice(sentence, ten=10, five=5) ? failed
  printBrown: console.writeLine(brown) ~
  readByte: second = string.byteAt(sentence, four=4) ? failed
  widen: secondNumber = convert.byteToInt64(second)
  writeByteLead: console.write(byteText="byte: ") ~
  printByte: console.writeIntegerLine(secondNumber) ~
  measure: length = string.byteLength(sentence)
  writeLengthLead: console.write(lengthText="length: ") ~
  printLength: console.writeIntegerLine(length) ~
  cutTail: tail = string.slice(sentence, four, fifteen=15) ? failed
  joinSpace: spaced = string.concat(tail, space=" ", scratch)
  numberText: digits = string.fromInt64(fortyTwo=42, scratch)
  joinNumber: joined = string.concat(spaced, digits, scratch)
  printJoined: console.writeLine(joined) ~
  compareTexts: same = string.equals(brown, brownText="brown")
  writeEqualLead: console.write(equalText="equal: ") ~
  if same printTrue printFalse
:printTrue
  writeTrue: console.writeLine(trueText="true") ~
  goto findFox
:printFalse
  writeFalse: console.writeLine(falseText="false") ~
  goto findFox
:findFox
  findIt: foxAt = string.find(sentence, fox="fox") ? failed
  writeFoxLead: console.write(foxText="fox at ") ~
  printFox: console.writeIntegerLine(foxAt) ~
  findCat: catAt = string.find(sentence, cat="cat") ? noCat
  printCat: console.writeIntegerLine(catAt) ~
  goto constants
:noCat
  writeNoCat: console.writeLine(noCatText="no cat") ~
  goto constants
:constants
  if verbose printLimit done
:printLimit
  writeLimitLead: console.write(limitText="limit: ") ~
  printLimitValue: console.writeIntegerLine(limit) ~
  goto done
:done
  return okCode
:failed
  return failCode
