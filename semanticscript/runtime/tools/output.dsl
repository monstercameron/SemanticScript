module output "Write text and numbers to standard output and standard error"
  path output
  imports standard.machine standard.system standard.math standard.compare standard.convert standard.test numbers
  exports standardHandle writeAll

capability memoryAccess "Authority to read the text to write and to keep the count written in machine.state" use machine.memory none

capability systemCalls "Authority to call the operating system's GetStdHandle, WriteFile, and GetLastError" use system.calls none

## machine.state bytes 0 to 63 belong to this module: 0 the count WriteFile wrote (a DWORD), 16 to 47 the digits
## and line end of a number being written.
constant writtenAt "Where WriteFile puts the count of bytes it wrote, in machine.state" Int64 0

constant digitsAt "Where a number's text is put together before it is written, in machine.state" Int64 16

op standardHandle "The operating system's handle of standard error for stream 2, and of standard output for any other stream"
  invariant namesStream "Stream 2 is standard error (STD_ERROR_HANDLE, -12); every other stream is standard output (STD_OUTPUT_HANDLE, -11)"
  input stream Int32 copied
  output machine.Address
  effect use system.calls
  uses systemCalls
:begin
  errorCheck: isError = compare.equalInt32(stream, two=2)
  if isError errorStream outputStream
:errorStream
  findError: errorHandle = system.getStdHandle(stdError=-12)
  return errorHandle
:outputStream
  findOutput: outputHandle = system.getStdHandle(stdOutput=-11)
  return outputHandle

op writeAll "Write a range of bytes to a handle, as many WriteFile calls as it takes; gives 0, or the system's error code when a write fails"
  invariant reportsFailure "Writing nothing succeeds with 0; a write the system refuses gives its error code, never 0"
  input handle machine.Address copied
  input text machine.Address copied
  input bytes Int64 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let done Int64 0 mut
  let status Int32 0 mut
  let zero Int64 0
  let most Int64 1073741824
  let okStatus Int32 0
  let unknownStatus Int32 1
:begin
  findState: state = machine.state()
  findWritten: written = machine.offset(state, writtenAt)
  noOverlap: nowhere = machine.zero()
  goto eachWrite
:eachWrite loop=while max=bytes
  leftOf: left = math.subtractInt64(bytes, done)
  finishedCheck: finished = compare.lessOrEqualInt64(left, zero)
  if finished succeeded writeSome
:writeSome in=eachWrite
  capCheck: tooMany = compare.greaterThanInt64(left, most)
  if tooMany writeMost writeLeft
:writeMost in=eachWrite
  narrowMost: chunk = convert.int64ToInt32(most)
  findFromMost: fromMost = machine.offset(text, done)
  callMost: wroteMost = system.writeFile(handle, fromMost, chunk, written, nowhere)
  set status wroteMost
  goto checkWrite
:writeLeft in=eachWrite
  narrowLeft: leftChunk = convert.int64ToInt32(left)
  findFromLeft: fromLeft = machine.offset(text, done)
  callLeft: wroteLeft = system.writeFile(handle, fromLeft, leftChunk, written, nowhere)
  set status wroteLeft
  goto checkWrite
:checkWrite in=eachWrite
  refusedCheck: refused = compare.equalInt32(status, failed=0)
  if refused failure countWritten
:countWritten in=eachWrite
  readCount: count = machine.loadInt32(written)
  widenCount: countWide = convert.int32ToInt64(count)
  stuckCheck: stuck = compare.lessOrEqualInt64(countWide, zero)
  if stuck stalled advance
:advance in=eachWrite
  addCount: nextDone = math.addInt64(done, countWide)
  set done nextDone
  goto eachWrite
:succeeded
  return okStatus
:failure
  readError: code = system.getLastError()
  zeroCheck: noCode = compare.equalInt32(code, failed)
  if noCode stalled reportCode
:reportCode
  return code
:stalled
  return unknownStatus

op writeText "Write text to standard output (stream 1) or standard error (stream 2), then a line end when asked; gives 0, or the system's error code"
  invariant writesLine "Writes the text's bytes as they are, then one `\\n` byte when `newline` is not 0"
  input stream Int32 copied
  input text machine.Address copied
  input bytes Int64 copied
  input newline Int32 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_write"
  let lineEnd String "\n"
:begin
  findHandle: handle = standardHandle(stream)
  writeBody: status = writeAll(handle, text, bytes)
  failedCheck: failed = compare.notEqualInt32(status, ok=0)
  if failed done lineCheck
:lineCheck
  wantLine: wanted = compare.notEqualInt32(newline, ok)
  if wanted writeLine done
:writeLine
  findLine: lineAt = machine.addressOfString(lineEnd)
  writeEnd: lineStatus = writeAll(handle, lineAt, one=1)
  return lineStatus
:done
  return status

op writeInteger "Write a whole number in decimal to standard output (stream 1) or standard error (stream 2), then a line end when asked; gives 0, or the system's error code"
  invariant writesDecimalLine "Writes the number as `refined run` prints it, then one `\\n` byte when `newline` is not 0, in one write"
  input stream Int32 copied
  input value Int64 copied
  input newline Int32 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi c "refined_write_int"
  let length Int64 0 mut
:begin
  findState: state = machine.state()
  findDigits: digits = machine.offset(state, digitsAt)
  format: written = numbers.formatDecimal(value, digits)
  set length written
  wantLine: wanted = compare.notEqualInt32(newline, ok=0)
  if wanted addLine write
:addLine
  findEnd: endAt = machine.offset(digits, written)
  putLine: machine.storeByte(endAt, lineEnd=10)
  withLine: lineLength = math.addInt64(written, one=1)
  set length lineLength
  goto write
:write
  findHandle: handle = standardHandle(stream)
  writeDigits: status = writeAll(handle, digits, length)
  return status

@tests

test standardHandleTest "Stream 2 is standard error and every other stream standard output"
  verifies standardHandle namesStream
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findError: errorHandle = standardHandle(two=2)
  findSystemError: systemError = system.getStdHandle(stdError=-12)
  sameError: errorSame = machine.equal(errorHandle, systemError)
  expectError: test.assertTrue(errorSame)
  findOutput: outputHandle = standardHandle(one=1)
  findSystemOutput: systemOutput = system.getStdHandle(stdOutput=-11)
  sameOutput: outputSame = machine.equal(outputHandle, systemOutput)
  expectOutput: test.assertTrue(outputSame)
  return

test writeAllTest "Writing nothing succeeds; writing to no handle at all reports the system's error"
  verifies writeAll reportsFailure
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let text String "never written"
:begin
  findError: errorHandle = standardHandle(two=2)
  findText: textAt = machine.addressOfString(text)
  writeNothing: nothingStatus = writeAll(errorHandle, textAt, zero=0)
  nothingWide: nothingValue = convert.int32ToInt64(nothingStatus)
  expectNothing: test.assertEqualInt64(zero, nothingValue)
  findNowhere: nowhere = machine.zero()
  writeNowhere: nowhereStatus = writeAll(nowhere, textAt, thirteen=13)
  refusedCheck: refused = compare.notEqualInt32(nowhereStatus, ok=0)
  expectRefused: test.assertTrue(refused)
  return

test writeTextTest "Writing an empty text with no line end to standard error succeeds"
  verifies writeText writesLine
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let text String ""
:begin
  findText: textAt = machine.addressOfString(text)
  writeEmpty: status = writeText(two=2, textAt, zero=0, noLine=0)
  statusWide: statusValue = convert.int32ToInt64(status)
  expectWritten: test.assertEqualInt64(zero, statusValue)
  return

test writeIntegerTest "A number written to a stream the system refuses reports a failure"
  verifies writeInteger writesDecimalLine
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  writeNumber: status = writeInteger(two=2, value=0, noLine=0)
  findState: state = machine.state()
  findDigits: digits = machine.offset(state, digitsAt)
  readDigit: digit = machine.loadByte(digits)
  digitWide: digitValue = convert.byteToInt64(digit)
  expectDigit: test.assertEqualInt64(zeroCharacter=48, digitValue)
  statusWide: statusValue = convert.int32ToInt64(status)
  expectWritten: test.assertEqualInt64(zero=0, statusValue)
  return
