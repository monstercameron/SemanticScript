## A stage0 sample: the host library. It builds a line in a byte buffer
## (text, a number, and a byte), turns it back into text, parses a number out
## of text, classifies bytes, and turns text into bytes and back, all through
## the runtime's `refined_host` and inline targets, as an executable built by
## `refined build` does. It exits with code 0:
##
##   total: 42!
##   length: 10
##   parsed: 1234
##   not a number
##   digit, letter
##   round trip: abc
module buffers "Build text in a byte buffer, parse numbers, and classify bytes"
  path buffers
  imports standard.console standard.buffer standard.string standard.byte standard.logic
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

op main "Build a line in a buffer, then parse, classify, and convert text"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  region scratch 65536
  let okCode ExitCode 0
  let failCode ExitCode 1
:begin
  makeBuffer: line = buffer.new(scratch)
  addText: buffer.appendString(line, totalText="total: ")
  addNumber: buffer.appendInt64(line, fortyTwo=42)
  addMark: buffer.appendByte(line, bang=33)
  readBack: text = buffer.toString(line, scratch) ? failed
  printText: console.writeLine(text) ~
  measure: size = buffer.length(line)
  writeLengthLead: console.write(lengthText="length: ") ~
  printLength: console.writeIntegerLine(size) ~
  parse: parsed = string.toInt64(digits="1234") ? failed
  writeParsedLead: console.write(parsedText="parsed: ") ~
  printParsed: console.writeIntegerLine(parsed) ~
  parseBad: notParsed = string.toInt64(word="12a") ? notNumber
  printNotParsed: console.writeIntegerLine(notParsed) ~
  goto classify
:notNumber
  writeNotNumber: console.writeLine(notNumberText="not a number") ~
  goto classify
:classify
  readDigit: firstDigit = string.byteAt(digits, 0) ? failed
  digitCheck: isDigit = byte.isDigit(firstDigit)
  readLetter: firstLetter = string.byteAt(word, two=2) ? failed
  letterCheck: isLetter = byte.isLetter(firstLetter)
  bothCheck: both = logic.and(isDigit, isLetter)
  if both printBoth failed
:printBoth
  writeBoth: console.writeLine(bothText="digit, letter") ~
  toBytes: raw = string.toBytes(abc="abc")
  fromBytes: back = string.fromBytes(raw, scratch) ? failed
  writeRoundLead: console.write(roundText="round trip: ") ~
  writeRound: console.writeLine(back) ~
  return okCode
:failed
  return failCode
