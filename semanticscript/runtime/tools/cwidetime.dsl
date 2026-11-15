module cwidetime "wcsftime for the runtime's C library: strftime's text as wide characters (D-176)"
  path cwidetime
  imports standard.machine standard.string standard.math standard.compare standard.convert standard.bits standard.logic standard.test heap wide clibrary cformat ctime
  exports none

capability memoryAccess "Authority to read and write the memory C callers hand the library" use machine.memory none

capability systemCalls "Authority to take memory for the text strftime writes" use system.calls none

## D-176: wcsftime writes what strftime writes, as wide characters. Its wide format is made bytes as the wide printf
## family makes its formats (cformat.addUnit: a character past 254 as 255 and six bytes of its bits), strftime
## (ctime.formatTime) copies those bytes through as ordinary characters, and the text is read back into wide
## characters; every conversion writes ASCII in the C locale. Like strftime it gives 0 when the characters and their
## 0 do not fit.

constant forever "The bound of a loop that ends by its own test" Int64 9223372036854775807

op wideTimeFormat "A wide format made bytes, a wide character past 254 as 255 and six bytes of its bits, in a new block ending with 0"
  input text machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  builder = wide.builderNew()
  goto eachUnit
:eachUnit loop=while max=forever
  calc unitAt = text + at * 4
  calc code = convert.int32ToInt64(machine.loadInt32(unitAt))
  when code == 0 finish addIt
:addIt in=eachUnit
  cformat.addUnit(builder, code)
  calc at := at + 1
  goto eachUnit
:finish
  wide.builderAddByte(builder, convert.int64ToByte(0))
  bytes = wide.builderText(builder)
  heap.give(builder)
  return bytes

op wideTime "wcsftime: a struct tm written as a wide format says into a buffer of a size in wide characters: the characters written without the 0, or 0 when they and the 0 do not fit"
  invariant formatsWide "Writes strftime's text as wide characters, keeping the format's characters past 255, or gives 0 when it does not fit"
  input target machine.Address copied
  input size Int64 copied
  input format machine.Address copied
  input tm machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "wcsftime"
  let at Int64 0 mut
  let count Int64 0 mut
  let code Int64 0 mut
  let piece Int64 0 mut
  let nothing Int64 0
:begin
  when size <= 0 refuse prepare
:prepare
  formatBytes = wideTimeFormat(format)
  calc most = lowestOf(size, 1048576)
  calc room = most * 7 + 1
  calc bytes = heap.take(room)
  written = ctime.formatTime(bytes, room, formatBytes, tm)
  heap.give(formatBytes)
  goto eachByte
:eachByte loop=while max=forever
  when at >= written decoded readOne
:readOne in=eachByte
  calc first = convert.byteToInt64(clibrary.byteAt(bytes, at))
  calc at := at + 1
  when first == 255 escape plain
:plain in=eachByte
  set code first
  goto store
:escape in=eachByte
  calc code := 0
  calc piece := 0
  goto pieces
:pieces loop=while max=forever in=eachByte
  when piece >= 6 store addPiece
:addPiece in=pieces
  calc bits = convert.byteToInt64(clibrary.byteAt(bytes, at)) & 63
  calc code := (code << 6) | bits
  calc at := at + 1
  calc piece := piece + 1
  goto pieces
:store in=eachByte
  when count >= size - 1 tooLong keep
:keep in=eachByte
  calc unitAt = target + count * 4
  machine.storeInt32(unitAt, clibrary.lowInt32(code))
  calc count := count + 1
  goto eachByte
:decoded
  heap.give(bytes)
  calc endAt = target + count * 4
  machine.storeInt32(endAt, clibrary.lowInt32(0))
  return count
:tooLong
  heap.give(bytes)
  return nothing
:refuse
  return nothing

op lowestOf "The smaller of two whole numbers"
  input left Int64 copied
  input right Int64 copied
  output Int64
:begin
  when left < right giveLeft giveRight
:giveLeft
  return left
:giveRight
  return right

@tests

op wideOf "An ASCII text as a wide string in a new block, with one character replaced by a code at an index (-1 for none)"
  input text String borrowed
  input index Int64 copied
  input code Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  bytes = string.byteLength(text)
  textAt = machine.addressOfString(text)
  calc block = heap.take(bytes * 4 + 4)
  goto eachByte
:eachByte loop=while max=forever
  when at >= bytes replace copyOne
:copyOne in=eachByte
  calc sourceAt = textAt + at
  calc value = convert.byteToInt64(machine.loadByte(sourceAt))
  calc unitAt = block + at * 4
  machine.storeInt32(unitAt, clibrary.lowInt32(value))
  calc at := at + 1
  goto eachByte
:replace
  when index >= 0 put done
:put
  calc replaceAt = block + index * 4
  machine.storeInt32(replaceAt, clibrary.lowInt32(code))
  goto done
:done
  return block

op unitIs "Whether the wide character at an index of a wide string is a code"
  input text machine.Address copied
  input index Int64 copied
  input code Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
:begin
  calc unitAt = text + index * 4
  unit = machine.loadInt32(unitAt)
  calc same = convert.int32ToInt64(unit) == code
  return same

test wideTimeTest "wcsftime writes strftime's text as wide characters, a format character past 255 kept, and gives 0 for a buffer too small"
  verifies wideTime formatsWide
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  tm = heap.take(64)
  machine.storeInt32(tm, clibrary.lowInt32(9))
  calc minuteAt = tm + 4
  machine.storeInt32(minuteAt, clibrary.lowInt32(7))
  calc hourAt = tm + 8
  machine.storeInt32(hourAt, clibrary.lowInt32(13))
  calc dayAt = tm + 12
  machine.storeInt32(dayAt, clibrary.lowInt32(5))
  calc monthAt = tm + 16
  machine.storeInt32(monthAt, clibrary.lowInt32(2))
  calc yearAt = tm + 20
  machine.storeInt32(yearAt, clibrary.lowInt32(124))
  calc weekdayAt = tm + 24
  machine.storeInt32(weekdayAt, clibrary.lowInt32(2))
  calc yearDayAt = tm + 28
  machine.storeInt32(yearDayAt, clibrary.lowInt32(64))
  format = wideOf("%Y-%m-%d %H:%M:%S X%a", 18, 20013)
  target = heap.take(256)
  written = wideTime(target, 64, format, tm)
  test.assertEqualInt64(24, written)
  test.assertTrue(unitIs(target, 0, 50) && unitIs(target, 10, 32) && unitIs(target, 20, 20013) && unitIs(target, 21, 84) && unitIs(target, 23, 101) && unitIs(target, 24, 0))
  small = wideTime(target, 24, format, tm)
  test.assertEqualInt64(0, small)
  heap.give(target)
  heap.give(format)
  heap.give(tm)
  return
