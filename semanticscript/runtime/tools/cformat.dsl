module cformat "printf's engine for the runtime's C library: every conversion as glibc writes it in the C locale, a floating value's digits exact (D-159)"
  path cformat
  imports standard.machine standard.system standard.string standard.math standard.compare standard.convert standard.bits standard.logic standard.test heap wide clibrary clong
  exports cursorNew cursorFree formatAll formatAllAs addUnit decimalDigits roundingMode readWord parseLongAs scanLong

capability memoryAccess "Authority to read the format, the arguments, and the memory C callers hand the library" use machine.memory none

capability systemCalls "Authority to take memory for the text being written" use system.calls none

## D-159: `formatAll` writes a format and its arguments into a builder (wide.builderNew), and the stdio functions copy
## the builder where they write: a stream, a string, or a block of their own. The arguments are read from a cursor
## over the caller's `va_list`, laid out as the system lays it out: x86_64 Linux (gp_offset, fp_offset,
## overflow_arg_area, reg_save_area), AArch64 Linux (__stack, __gr_top, __vr_top, __gr_offs, __vr_offs), and Windows
## (one pointer, eight bytes an argument, a double in its integer slot). Every argument is read before anything is
## written, in the order the format names them (positional `%n$` ones by their number), so `*` widths and `%n$`
## conversions read what they name. Floating values are written from their exact decimal digits: a double is
## m * 2^e, which is m * 5^-e / 10^-e when e is negative, so its digits are those of a whole number (kept in base
## 10^9), rounded as the current rounding mode rounds (to nearest, ties to even, by default), as glibc's printf_fp
## does. A cursor (a heap block of 16 bytes): 0 the layout (1 x86_64 Linux, 2 AArch64 Linux, 3 one slot of eight
## bytes an argument: Windows, and the tests), 8 the address of the va_list. A spec (a heap block of 96 bytes): 0 the
## flags (1 `-`, 2 `+`, 4 ` `, 8 `#`, 16 `0`), 8 the width, 16 the width's argument (0 when none), 24 the precision
## (-1 when none), 32 the precision's argument, 40 the length (0 none, 1 hh, 2 h, 3 l, 4 ll, 5 L, 6 j, 7 z, 8 t),
## 48 the conversion's byte, 56 its argument, 64 where the spec ends, 72 whether its argument numbers were written
## (`%n$`). The arguments read (a heap block): 0 how many, then 16 bytes each from 16, a word, a double, or a long
## double's 16 bytes.
constant forever "The bound of a loop over text that ends at its 0 byte" Int64 9223372036854775807

constant billion "The base of the decimal limbs: 10^9" UInt64 1000000000

constant flagMinus "The `-` flag" Int64 1

constant flagPlus "The `+` flag" Int64 2

constant flagSpace "The ` ` flag" Int64 4

constant flagHash "The `#` flag" Int64 8

constant flagZero "The `0` flag" Int64 16

constant overflowError "EOVERFLOW: the text written passes INT_MAX bytes" Int32 75

constant invalidError "EINVAL: a format that ends inside a conversion" Int32 22

## ---------------------------------------------------------------- the arguments

op cursorNew "A cursor over a va_list: the system's layout, and the va_list's address"
  invariant readsInOrder "A cursor reads a va_list laid out as this system lays it out: 3 on Windows, 1 on x86_64 Linux, 2 on AArch64 Linux"
  input list machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let layout Int64 3 mut
:begin
  cursor = heap.take(16)
  onLinux = system.linux()
  if onLinux linux store
:linux
  set layout 1
  onArm = system.aarch64()
  if onArm arm store
:arm
  set layout 2
  goto store
:store
  machine.storeInt64(cursor, layout)
  listCell = machine.offset(cursor, 8)
  machine.storeAddress(listCell, list)
  return cursor

op cursorFree "Give a cursor's block back"
  invariant releasesCursor "The cursor's block goes back to the heap"
  input cursor machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  heap.give(cursor)
  return

op readWord "The next argument of the integer class (an int, a long, a pointer: eight bytes, of which an int's are the low four)"
  invariant readsWords "Each call gives the next eight-byte argument and moves past it"
  input cursor machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  layout = machine.loadInt64(cursor)
  listCell = machine.offset(cursor, 8)
  list = machine.loadAddress(listCell)
  when layout == 1 sysv notSysv
:notSysv
  when layout == 2 arm slot
:sysv
  used = machine.loadInt32(list)
  when used < 48 sysvRegister sysvStack
:sysvRegister
  saveCell = machine.offset(list, 16)
  saveArea = machine.loadAddress(saveCell)
  calc usedWide = convert.int32ToInt64(used)
  calc sysvAt = saveArea + usedWide
  sysvValue = machine.loadInt64(sysvAt)
  calc usedNext = used + 8
  machine.storeInt32(list, usedNext)
  return sysvValue
:sysvStack
  stackCell = machine.offset(list, 8)
  stack = machine.loadAddress(stackCell)
  stackValue = machine.loadInt64(stack)
  calc stackNext = stack + 8
  machine.storeAddress(stackCell, stackNext)
  return stackValue
:arm
  offsetCell = machine.offset(list, 24)
  offset = machine.loadInt32(offsetCell)
  when offset < 0 armRegister armStack
:armRegister
  topCell = machine.offset(list, 8)
  top = machine.loadAddress(topCell)
  calc offsetWide = convert.int32ToInt64(offset)
  calc armAt = top + offsetWide
  armValue = machine.loadInt64(armAt)
  calc offsetNext = offset + 8
  machine.storeInt32(offsetCell, offsetNext)
  return armValue
:armStack
  armStackPlace = machine.loadAddress(list)
  armStackValue = machine.loadInt64(armStackPlace)
  calc armStackNext = armStackPlace + 8
  machine.storeAddress(list, armStackNext)
  return armStackValue
:slot
  place = machine.loadAddress(list)
  slotValue = machine.loadInt64(place)
  calc placeNext = place + 8
  machine.storeAddress(list, placeNext)
  return slotValue

op readReal "The next argument of the floating class: a double"
  input cursor machine.Address copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  layout = machine.loadInt64(cursor)
  listCell = machine.offset(cursor, 8)
  list = machine.loadAddress(listCell)
  when layout == 1 sysv notSysv
:notSysv
  when layout == 2 arm slot
:sysv
  usedCell = machine.offset(list, 4)
  used = machine.loadInt32(usedCell)
  when used < 176 sysvRegister sysvStack
:sysvRegister
  saveCell = machine.offset(list, 16)
  saveArea = machine.loadAddress(saveCell)
  calc usedWide = convert.int32ToInt64(used)
  calc sysvAt = saveArea + usedWide
  sysvValue = machine.loadFloat64(sysvAt)
  calc usedNext = used + 16
  machine.storeInt32(usedCell, usedNext)
  return sysvValue
:sysvStack
  stackCell = machine.offset(list, 8)
  stack = machine.loadAddress(stackCell)
  stackValue = machine.loadFloat64(stack)
  calc stackNext = stack + 8
  machine.storeAddress(stackCell, stackNext)
  return stackValue
:arm
  offsetCell = machine.offset(list, 28)
  offset = machine.loadInt32(offsetCell)
  when offset < 0 armRegister armStack
:armRegister
  topCell = machine.offset(list, 16)
  top = machine.loadAddress(topCell)
  calc offsetWide = convert.int32ToInt64(offset)
  calc armAt = top + offsetWide
  armValue = machine.loadFloat64(armAt)
  calc offsetNext = offset + 16
  machine.storeInt32(offsetCell, offsetNext)
  return armValue
:armStack
  armStackPlace = machine.loadAddress(list)
  armStackValue = machine.loadFloat64(armStackPlace)
  calc armStackNext = armStackPlace + 8
  machine.storeAddress(list, armStackNext)
  return armStackValue
:slot
  place = machine.loadAddress(list)
  slotValue = machine.loadFloat64(place)
  calc placeNext = place + 8
  machine.storeAddress(list, placeNext)
  return slotValue

op alignUp "An address moved up to the next multiple of 16"
  input address machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  calc value = machine.toInt64(address)
  calc rounded = (value + 15) & -16
  calc moved = machine.fromInt64(rounded)
  return moved

op readLong "The next long double argument, its 16 bytes copied to an address: x87's 80 bits in memory on x86_64 Linux, binary128 in a vector register or memory on AArch64; on Windows, where long double is double, a double in its 8 bytes"
  input cursor machine.Address copied
  input out machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  layout = machine.loadInt64(cursor)
  listCell = machine.offset(cursor, 8)
  list = machine.loadAddress(listCell)
  when layout == 1 sysv notSysv
:notSysv
  when layout == 2 arm slot
:sysv
  stackCell = machine.offset(list, 8)
  stack = machine.loadAddress(stackCell)
  aligned = alignUp(stack)
  machine.copy(out, aligned, 16)
  calc stackNext = aligned + 16
  machine.storeAddress(stackCell, stackNext)
  return
:arm
  offsetCell = machine.offset(list, 28)
  offset = machine.loadInt32(offsetCell)
  when offset < 0 armRegister armStack
:armRegister
  topCell = machine.offset(list, 16)
  top = machine.loadAddress(topCell)
  calc offsetWide = convert.int32ToInt64(offset)
  calc armAt = top + offsetWide
  machine.copy(out, armAt, 16)
  calc offsetNext = offset + 16
  machine.storeInt32(offsetCell, offsetNext)
  return
:armStack
  armStackPlace = machine.loadAddress(list)
  armAligned = alignUp(armStackPlace)
  machine.copy(out, armAligned, 16)
  calc armStackNext = armAligned + 16
  machine.storeAddress(list, armStackNext)
  return
:slot
  place = machine.loadAddress(list)
  machine.copy(out, place, 8)
  calc placeNext = place + 8
  machine.storeAddress(list, placeNext)
  return

## ---------------------------------------------------------------- reading a conversion

op digitValue "The value of an ASCII digit, or -1 for any other byte"
  input value Byte copied
  output Int64
  let notDigit Int64 -1
:begin
  when value >= 48 && value <= 57 digit other
:digit
  calc found = convert.byteToInt64(value) - 48
  return found
:other
  return notDigit

op readNumber "Read a run of decimal digits at a position of a format into a cell (saturating at 2^31) and give the position after them"
  input format machine.Address copied
  input at Int64 copied
  input cell machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let place Int64 0 mut
  let value Int64 0 mut
:begin
  set place at
  goto eachDigit
:eachDigit loop=while max=forever
  current = clibrary.byteAt(format, place)
  digit = digitValue(current)
  when digit < 0 finish add
:add in=eachDigit
  when value > 214748364 saturate grow
:saturate in=eachDigit
  calc value := 2147483648
  goto advance
:grow in=eachDigit
  calc value := value * 10 + digit
  goto advance
:advance in=eachDigit
  calc place := place + 1
  goto eachDigit
:finish
  machine.storeInt64(cell, value)
  return place

op parseSpec "Read the conversion that starts after a `%` at a position of a format into a spec: its argument number (`n$`), flags, width (a number, `*`, or `*n$`), precision, length, and conversion; arguments without numbers are numbered from a counter, which is given back moved on"
  input format machine.Address copied
  input at Int64 copied
  input spec machine.Address copied
  input counter Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let place Int64 0 mut
  let next Int64 0 mut
  let flags Int64 0 mut
  let length Int64 0 mut
  let valueArgument Int64 0 mut
:begin
  set place at
  set next counter
  machine.fill(spec, 0, 96)
  precisionCell = machine.offset(spec, 24)
  machine.storeInt64(precisionCell, -1)
  numberCell = machine.offset(spec, 88)
  first = clibrary.byteAt(format, place)
  firstDigit = digitValue(first)
  when firstDigit > 0 positional flagLoop
:positional
  afterDigits = readNumber(format, place, numberCell)
  dollar = clibrary.byteAt(format, afterDigits)
  when dollar == 36 takePosition flagLoop
:takePosition
  calc valueArgument := machine.loadInt64(numberCell)
  calc place := afterDigits + 1
  numberedCell = machine.offset(spec, 72)
  machine.storeInt64(numberedCell, 1)
  goto flagLoop
:flagLoop loop=while max=forever
  flag = clibrary.byteAt(format, place)
  when flag == 45 minusFlag notMinus
:notMinus in=flagLoop
  when flag == 43 plusFlag notPlus
:notPlus in=flagLoop
  when flag == 32 spaceFlag notSpace
:notSpace in=flagLoop
  when flag == 35 hashFlag notHash
:notHash in=flagLoop
  when flag == 48 zeroFlag notZero
:notZero in=flagLoop
  when flag == 39 || flag == 73 skipFlag width
:minusFlag in=flagLoop
  calc flags := flags | flagMinus
  goto skipFlag
:plusFlag in=flagLoop
  calc flags := flags | flagPlus
  goto skipFlag
:spaceFlag in=flagLoop
  calc flags := flags | flagSpace
  goto skipFlag
:hashFlag in=flagLoop
  calc flags := flags | flagHash
  goto skipFlag
:zeroFlag in=flagLoop
  calc flags := flags | flagZero
  goto skipFlag
:skipFlag in=flagLoop
  calc place := place + 1
  goto flagLoop
:width
  widthByte = clibrary.byteAt(format, place)
  when widthByte == 42 widthStar widthDigits
:widthDigits
  widthCell = machine.offset(spec, 8)
  calc place := readNumber(format, place, widthCell)
  goto precision
:widthStar
  calc place := place + 1
  starFirst = clibrary.byteAt(format, place)
  starDigit = digitValue(starFirst)
  when starDigit > 0 widthNumbered widthNext
:widthNumbered
  afterStar = readNumber(format, place, numberCell)
  starDollar = clibrary.byteAt(format, afterStar)
  when starDollar == 36 widthTake widthNext
:widthTake
  widthArgumentCell = machine.offset(spec, 16)
  starNumber = machine.loadInt64(numberCell)
  machine.storeInt64(widthArgumentCell, starNumber)
  calc place := afterStar + 1
  goto precision
:widthNext
  calc next := next + 1
  widthNextCell = machine.offset(spec, 16)
  machine.storeInt64(widthNextCell, next)
  goto precision
:precision
  dot = clibrary.byteAt(format, place)
  when dot == 46 precisionStart lengths
:precisionStart
  calc place := place + 1
  precisionByte = clibrary.byteAt(format, place)
  when precisionByte == 42 precisionStar precisionDigits
:precisionDigits
  calc place := readNumber(format, place, precisionCell)
  goto lengths
:precisionStar
  calc place := place + 1
  pStarFirst = clibrary.byteAt(format, place)
  pStarDigit = digitValue(pStarFirst)
  when pStarDigit > 0 precisionNumbered precisionNext
:precisionNumbered
  afterPStar = readNumber(format, place, numberCell)
  pStarDollar = clibrary.byteAt(format, afterPStar)
  when pStarDollar == 36 precisionTake precisionNext
:precisionTake
  precisionArgumentCell = machine.offset(spec, 32)
  pStarNumber = machine.loadInt64(numberCell)
  machine.storeInt64(precisionArgumentCell, pStarNumber)
  calc place := afterPStar + 1
  goto lengths
:precisionNext
  calc next := next + 1
  precisionNextCell = machine.offset(spec, 32)
  machine.storeInt64(precisionNextCell, next)
  goto lengths
:lengths
  lengthByte = clibrary.byteAt(format, place)
  when lengthByte == 104 shortLength notShort
:shortLength
  calc place := place + 1
  secondH = clibrary.byteAt(format, place)
  when secondH == 104 charLength shortOnly
:charLength
  calc length := 1
  calc place := place + 1
  goto conversion
:shortOnly
  calc length := 2
  goto conversion
:notShort
  when lengthByte == 108 longLength notLong
:longLength
  calc place := place + 1
  secondL = clibrary.byteAt(format, place)
  when secondL == 108 longLongLength longOnly
:longLongLength
  calc length := 4
  calc place := place + 1
  goto conversion
:longOnly
  calc length := 3
  goto conversion
:notLong
  when lengthByte == 76 longDouble notLongDouble
:longDouble
  calc length := 5
  calc place := place + 1
  goto conversion
:notLongDouble
  when lengthByte == 113 quad notQuad
:quad
  calc length := 4
  calc place := place + 1
  goto conversion
:notQuad
  when lengthByte == 106 intmax notIntmax
:intmax
  calc length := 6
  calc place := place + 1
  goto conversion
:notIntmax
  when lengthByte == 122 || lengthByte == 90 size notSize
:size
  calc length := 7
  calc place := place + 1
  goto conversion
:notSize
  when lengthByte == 116 difference conversion
:difference
  calc length := 8
  calc place := place + 1
  goto conversion
:conversion
  machine.storeInt64(spec, flags)
  lengthCell = machine.offset(spec, 40)
  machine.storeInt64(lengthCell, length)
  conversionByte = clibrary.byteAt(format, place)
  conversionCell = machine.offset(spec, 48)
  calc conversionWide = convert.byteToInt64(conversionByte)
  machine.storeInt64(conversionCell, conversionWide)
  endCell = machine.offset(spec, 64)
  calc ending = place + 1
  machine.storeInt64(endCell, ending)
  kind = argumentKind(spec)
  when kind == 0 noArgument hasArgument
:hasArgument
  when valueArgument > 0 keepArgument countArgument
:countArgument
  calc next := next + 1
  calc valueArgument := next
  goto keepArgument
:keepArgument
  argumentCell = machine.offset(spec, 56)
  machine.storeInt64(argumentCell, valueArgument)
  return next
:noArgument
  return next

op argumentKind "What a spec's conversion reads: 0 nothing (`%%`, `%m`, a conversion glibc does not know, the format's end), 1 a word (an integer or a pointer), 3 a double, 4 a long double"
  input spec machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let nothing Int64 0
  let word Int64 1
  let real Int64 3
  let longReal Int64 4
:begin
  conversionCell = machine.offset(spec, 48)
  conversion = machine.loadInt64(conversionCell)
  isWord = isWordConversion(conversion)
  if isWord giveWord notWord
:giveWord
  return word
:notWord
  isReal = isRealConversion(conversion)
  if isReal realKind giveNothing
:realKind
  lengthCell = machine.offset(spec, 40)
  length = machine.loadInt64(lengthCell)
  when length == 5 giveLong giveReal
:giveLong
  return longReal
:giveReal
  return real
:giveNothing
  return nothing

op isWordConversion "Whether a conversion takes an integer or a pointer: d i o u x X c s p n C S"
  input conversion Int64 copied
  output Bool
:begin
  calc signedOrOctal = conversion == 100 || conversion == 105 || conversion == 111 || conversion == 117
  calc hexOrChar = conversion == 120 || conversion == 88 || conversion == 99 || conversion == 115
  calc others = conversion == 112 || conversion == 110 || conversion == 67 || conversion == 83
  calc any = signedOrOctal || hexOrChar || others
  return any

op isRealConversion "Whether a conversion takes a floating value: f F e E g G a A"
  input conversion Int64 copied
  output Bool
:begin
  calc fixedOrExponent = conversion == 102 || conversion == 70 || conversion == 101 || conversion == 69
  calc generalOrHex = conversion == 103 || conversion == 71 || conversion == 97 || conversion == 65
  calc any = fixedOrExponent || generalOrHex
  return any

## ---------------------------------------------------------------- reading every argument first

op specCount "How many arguments a format reads: the highest argument number its conversions name or count to"
  input format machine.Address copied
  input spec machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let place Int64 0 mut
  let counter Int64 0 mut
  let most Int64 0 mut
:begin
  goto eachByte
:eachByte loop=while max=forever
  current = clibrary.byteAt(format, place)
  when current == 0 finish notEnd
:notEnd in=eachByte
  when current == 37 conversion plain
:plain in=eachByte
  calc place := place + 1
  goto eachByte
:conversion in=eachByte
  calc start = place + 1
  second = clibrary.byteAt(format, start)
  when second == 37 percent parse
:percent in=eachByte
  calc place := place + 2
  goto eachByte
:parse in=eachByte
  calc counter := parseSpec(format, start, spec, counter)
  endCell = machine.offset(spec, 64)
  calc place := machine.loadInt64(endCell)
  conversionCell = machine.offset(spec, 48)
  conversionByte = machine.loadInt64(conversionCell)
  when conversionByte == 0 finish keep
:keep in=eachByte
  widthArgumentCell = machine.offset(spec, 16)
  widthArgument = machine.loadInt64(widthArgumentCell)
  precisionArgumentCell = machine.offset(spec, 32)
  precisionArgument = machine.loadInt64(precisionArgumentCell)
  valueArgumentCell = machine.offset(spec, 56)
  valueArgument = machine.loadInt64(valueArgumentCell)
  calc most := highest(most, widthArgument)
  calc most := highest(most, precisionArgument)
  calc most := highest(most, valueArgument)
  calc most := highest(most, counter)
  goto eachByte
:finish
  return most

op highest "The larger of two whole numbers"
  input left Int64 copied
  input right Int64 copied
  output Int64
:begin
  when left >= right giveLeft giveRight
:giveLeft
  return left
:giveRight
  return right

op recordKinds "Note what each argument a format reads is (1 a word, 3 a double, 4 a long double) in a block of one Int64 per argument number"
  input format machine.Address copied
  input spec machine.Address copied
  input kinds machine.Address copied
  effect use machine.memory
  uses memoryAccess
  let place Int64 0 mut
  let counter Int64 0 mut
:begin
  goto eachByte
:eachByte loop=while max=forever
  current = clibrary.byteAt(format, place)
  when current == 0 finish notEnd
:notEnd in=eachByte
  when current == 37 conversion plain
:plain in=eachByte
  calc place := place + 1
  goto eachByte
:conversion in=eachByte
  calc start = place + 1
  second = clibrary.byteAt(format, start)
  when second == 37 percent parse
:percent in=eachByte
  calc place := place + 2
  goto eachByte
:parse in=eachByte
  calc counter := parseSpec(format, start, spec, counter)
  endCell = machine.offset(spec, 64)
  calc place := machine.loadInt64(endCell)
  conversionCell = machine.offset(spec, 48)
  conversionByte = machine.loadInt64(conversionCell)
  when conversionByte == 0 finish note
:note in=eachByte
  widthArgumentCell = machine.offset(spec, 16)
  widthArgument = machine.loadInt64(widthArgumentCell)
  noteKind(kinds, widthArgument, 1)
  precisionArgumentCell = machine.offset(spec, 32)
  precisionArgument = machine.loadInt64(precisionArgumentCell)
  noteKind(kinds, precisionArgument, 1)
  valueArgumentCell = machine.offset(spec, 56)
  valueArgument = machine.loadInt64(valueArgumentCell)
  kind = argumentKind(spec)
  noteKind(kinds, valueArgument, kind)
  goto eachByte
:finish
  return

op noteKind "Note an argument number's kind, when the number is one (1 or more)"
  input kinds machine.Address copied
  input number Int64 copied
  input kind Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  when number > 0 note skip
:note
  calc at = kinds + number * 8
  machine.storeInt64(at, kind)
  return
:skip
  return

op readArguments "Read a format's arguments from a cursor, in order, into a new block: 16 bytes each from 16, by argument number; an argument no conversion names is read as a word"
  input format machine.Address copied
  input cursor machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let number Int64 1 mut
:begin
  spec = heap.take(96)
  count = specCount(format, spec)
  calc kindsBytes = count * 8 + 16
  kinds = heap.take(kindsBytes)
  recordKinds(format, spec, kinds)
  calc valuesBytes = count * 16 + 32
  values = heap.take(valuesBytes)
  machine.storeInt64(values, count)
  goto eachArgument
:eachArgument loop=while max=count
  when number > count finish read
:read in=eachArgument
  calc kindAt = kinds + number * 8
  kind = machine.loadInt64(kindAt)
  calc valueAt = values + number * 16
  when kind == 3 real notReal
:notReal in=eachArgument
  when kind == 4 longReal wordCase
:real in=eachArgument
  realValue = readReal(cursor)
  machine.storeFloat64(valueAt, realValue)
  goto advance
:longReal in=eachArgument
  readLong(cursor, valueAt)
  goto advance
:wordCase in=eachArgument
  wordValue = readWord(cursor)
  machine.storeInt64(valueAt, wordValue)
  goto advance
:advance in=eachArgument
  calc number := number + 1
  goto eachArgument
:finish
  heap.give(spec)
  heap.give(kinds)
  return values

op argumentAt "The address of an argument's 16 bytes, by its number; a number past those read is the last slot, zeroed"
  input values machine.Address copied
  input number Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  count = machine.loadInt64(values)
  when number >= 1 && number <= count inside outside
:inside
  calc at = values + number * 16
  return at
:outside
  calc spare = values + 16
  return spare

## ---------------------------------------------------------------- writing

op putByte "Add a byte to the text being written"
  input builder machine.Address copied
  input value Byte copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  wide.builderAddByte(builder, value)
  return

op putRepeated "Add a byte to the text being written a number of times (none when the number is 0 or less)"
  input builder machine.Address copied
  input value Byte copied
  input count Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  when count <= 0 nothingToAdd some
:nothingToAdd
  return
:some
  block = heap.take(count)
  machine.fill(block, value, count)
  wide.builderAdd(builder, block, count)
  heap.give(block)
  return

op putText "Add a text's bytes to the text being written"
  input builder machine.Address copied
  input text String borrowed
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  at = machine.addressOfString(text)
  bytes = string.byteLength(text)
  wide.builderAdd(builder, at, bytes)
  return

op emitPadded "Write a conversion's parts padded to its width: sign (0 for none), a prefix, then the body; `-` pads after them with spaces, `0` (when allowed) pads after the sign and prefix with zeros, and otherwise spaces come first"
  input builder machine.Address copied
  input flags Int64 copied
  input width Int64 copied
  input sign Byte copied
  input prefix machine.Address copied
  input prefixBytes Int64 copied
  input body machine.Address copied
  input bodyBytes Int64 copied
  input zeroAllowed Bool copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let signBytes Int64 0 mut
:begin
  when sign != 0 hasSign measure
:hasSign
  calc signBytes := 1
  goto measure
:measure
  calc pad = width - signBytes - prefixBytes - bodyBytes
  calc left = (flags & flagMinus) != 0
  calc zeros = (flags & flagZero) != 0 && zeroAllowed
  if left leftAligned notLeft
:leftAligned
  emitSign(builder, sign)
  wide.builderAdd(builder, prefix, prefixBytes)
  wide.builderAdd(builder, body, bodyBytes)
  putRepeated(builder, 32, pad)
  return
:notLeft
  if zeros zeroPadded spacePadded
:zeroPadded
  emitSign(builder, sign)
  wide.builderAdd(builder, prefix, prefixBytes)
  putRepeated(builder, 48, pad)
  wide.builderAdd(builder, body, bodyBytes)
  return
:spacePadded
  putRepeated(builder, 32, pad)
  emitSign(builder, sign)
  wide.builderAdd(builder, prefix, prefixBytes)
  wide.builderAdd(builder, body, bodyBytes)
  return

op emitSign "Write a sign byte, when there is one"
  input builder machine.Address copied
  input sign Byte copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  when sign != 0 write skip
:write
  wide.builderAddByte(builder, sign)
  return
:skip
  return

op signFor "The sign byte a signed conversion writes: `-` when negative, else `+` with that flag, ` ` with that one, or 0"
  input negative Bool copied
  input flags Int64 copied
  output Byte
  let minus Byte 45
  let plus Byte 43
  let blank Byte 32
  let noSign Byte 0
:begin
  if negative giveMinus positive
:giveMinus
  return minus
:positive
  when (flags & flagPlus) != 0 givePlus notPlus
:givePlus
  return plus
:notPlus
  when (flags & flagSpace) != 0 giveBlank giveNone
:giveBlank
  return blank
:giveNone
  return noSign

## ---------------------------------------------------------------- integers

op formatInteger "Write an integer conversion (d i u o x X p): its digits in its base, at least `precision` of them (no digit for 0 at precision 0), `#`'s `0` or `0x`, the sign, padded"
  input builder machine.Address copied
  input flags Int64 copied
  input width Int64 copied
  input precision Int64 copied
  input conversion Int64 copied
  input negative Bool copied
  input magnitude UInt64 copied
  input signed Bool copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let base UInt64 10 mut
  let rest UInt64 0 mut
  let place Int64 0 mut
  let prefixBytes Int64 0 mut
  let sign Byte 0 mut
:begin
  calc room = highest(precision, 0) + 72
  scratch = heap.take(room)
  prefix = heap.take(8)
  set place room
  set rest magnitude
  when conversion == 111 octal notOctal
:octal
  calc base := 8
  goto digits
:notOctal
  when conversion == 120 || conversion == 88 || conversion == 112 hex digits
:hex
  calc base := 16
  goto digits
:digits
  when magnitude == 0 && precision == 0 precisionZeros eachDigit
:eachDigit loop=while max=forever
  calc digit = rest % base
  calc rest := rest / base
  calc place := place - 1
  calc letter = digitByte(digit, conversion)
  calc digitAt = scratch + place
  machine.storeByte(digitAt, letter)
  when rest == 0 precisionZeros eachDigit
:precisionZeros
  calc digitsKept = room - place
  calc wanted = precision - digitsKept
  when wanted > 0 addZeros alternate
:addZeros
  calc place := place - wanted
  calc zerosAt = scratch + place
  machine.fill(zerosAt, 48, wanted)
  goto alternate
:alternate
  calc hash = (flags & flagHash) != 0 || conversion == 112
  if hash alternateKind signs
:alternateKind
  when base == 8 octalAlternate hexAlternate
:octalAlternate
  when place < room octalFirst octalZero
:octalFirst
  calc firstAt = scratch + place
  first = machine.loadByte(firstAt)
  when first == 48 signs octalZero
:octalZero
  calc place := place - 1
  calc octalAt = scratch + place
  machine.storeByte(octalAt, 48)
  goto signs
:hexAlternate
  when base == 16 && magnitude != 0 hexPrefix signs
:hexPrefix
  machine.storeByte(prefix, 48)
  calc xAt = prefix + 1
  calc xByte = conversionCase(conversion)
  machine.storeByte(xAt, xByte)
  calc prefixBytes := 2
  goto signs
:signs
  when signed || conversion == 112 signedSign emit
:signedSign
  calc sign := signFor(negative, flags)
  goto emit
:emit
  calc bodyAt = scratch + place
  calc bodyBytes = room - place
  calc zeroAllowed = precision < 0
  emitPadded(builder, flags, width, sign, prefix, prefixBytes, bodyAt, bodyBytes, zeroAllowed)
  heap.give(scratch)
  heap.give(prefix)
  return

op conversionCase "`x` for a lower-case conversion (x, p, a), `X` for an upper-case one"
  input conversion Int64 copied
  output Byte
  let small Byte 120
  let capital Byte 88
:begin
  when conversion == 88 || conversion == 65 giveCapital giveSmall
:giveCapital
  return capital
:giveSmall
  return small

op digitByte "The ASCII digit for a value below 16, upper case for X and A"
  input digit UInt64 copied
  input conversion Int64 copied
  output Byte
:begin
  calc small = convert.uint64ToByte(digit)
  when digit < 10 decimal letter
:decimal
  calc decimalByte = small + 48
  return decimalByte
:letter
  when conversion == 88 || conversion == 65 capital lower
:capital
  calc capitalByte = small + 55
  return capitalByte
:lower
  calc lowerByte = small + 87
  return lowerByte

op formatString "Write a string conversion: at most `precision` bytes of a C string, `(null)` for the address 0 (nothing when the precision is below 6), padded with spaces"
  input builder machine.Address copied
  input flags Int64 copied
  input width Int64 copied
  input precision Int64 copied
  input text machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let nullText String "(null)"
  let source machine.Address unset mut
  let length Int64 0 mut
:begin
  set source text
  nowhere = machine.zero()
  calc isNull = text == nowhere
  if isNull nullCase measure
:nullCase
  when precision < 0 || precision >= 6 showNull empty
:showNull
  calc source := machine.addressOfString(nullText)
  calc length := 6
  goto emit
:empty
  calc length := 0
  goto emit
:measure
  when precision < 0 whole bounded
:whole
  calc length := clibrary.cStringLength(text)
  goto emit
:bounded
  calc length := clibrary.boundedLength(text, precision)
  goto emit
:emit
  emitPadded(builder, flags, width, 0, nowhere, 0, source, length, false)
  return

op formatChar "Write a character conversion: one byte, padded with spaces"
  input builder machine.Address copied
  input flags Int64 copied
  input width Int64 copied
  input value Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  cell = heap.take(8)
  calc low = convert.int64ToByte(value & 255)
  machine.storeByte(cell, low)
  nowhere = machine.zero()
  emitPadded(builder, flags, width, 0, nowhere, 0, cell, 1, false)
  heap.give(cell)
  return

## ---------------------------------------------------------------- the exact digits of a floating value

op multiplyLimbs "Multiply a whole number in base 10^9 limbs (lowest first) by a factor below 2^31 in place, and give how many limbs it uses"
  input limbs machine.Address copied
  input count Int64 copied
  input factor UInt64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let carry UInt64 0 mut
  let used Int64 0 mut
:begin
  set used count
  goto eachLimb
:eachLimb loop=while max=count
  when at >= count spill multiply
:multiply in=eachLimb
  calc limbAt = limbs + at * 8
  limb = machine.loadUInt64(limbAt)
  calc product = limb * factor + carry
  calc kept = product % billion
  machine.storeUInt64(limbAt, kept)
  calc carry := product / billion
  calc at := at + 1
  goto eachLimb
:spill loop=while max=forever
  when carry == 0 finish append
:append in=spill
  calc spillAt = limbs + used * 8
  calc spillKept = carry % billion
  machine.storeUInt64(spillAt, spillKept)
  calc carry := carry / billion
  calc used := used + 1
  goto spill
:finish
  return used

op powerOfTwo "2 to a power from 0 to 30"
  input power Int64 copied
  output UInt64
:begin
  calc value = convert.int64ToUInt64(1) << power
  return value

op decimalDigits "The exact decimal digits of (high * 2^64 + low) * 2^exponent, as ASCII without leading zeros (`0` for 0) in a new heap block, with the count and how many of them follow the decimal point stored at an address: 0 the block, 8 the count, 16 the digits after the point"
  invariant exactDigits "The digits are exactly those of the value, 0.1 being 55 digits all after the point"
  input high UInt64 copied
  input low UInt64 copied
  input exponent Int64 copied
  input result machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let bitCount Int64 0 mut
  let count Int64 0 mut
  let w3 UInt64 0 mut
  let w2 UInt64 0 mut
  let w1 UInt64 0 mut
  let w0 UInt64 0 mut
  let rounds Int64 0 mut
  let remaining Int64 0 mut
  let fraction Int64 0 mut
  let at Int64 0 mut
  let out Int64 0 mut
  let value UInt64 0 mut
  let place Int64 0 mut
:begin
  when exponent < 0 negativeSize positiveSize
:negativeSize
  calc bitCount := 140 - exponent * 233 / 100
  calc fraction := 0 - exponent
  goto sized
:positiveSize
  calc bitCount := 140 + exponent
  goto sized
:sized
  calc capacity = bitCount / 29 + 8
  limbs = heap.take(capacity * 8)
  calc w3 := high >> 32
  calc w2 := high & 4294967295
  calc w1 := low >> 32
  calc w0 := low & 4294967295
  goto split
:split loop=while max=forever
  when w3 == 0 && w2 == 0 && w1 == 0 && w0 == 0 scaled divide
:divide in=split
  calc r3 = w3 % billion
  calc w3 := w3 / billion
  calc c2 = (r3 << 32) | w2
  calc r2 = c2 % billion
  calc w2 := c2 / billion
  calc c1 = (r2 << 32) | w1
  calc r1 = c1 % billion
  calc w1 := c1 / billion
  calc c0 = (r1 << 32) | w0
  calc r0 = c0 % billion
  calc w0 := c0 / billion
  calc limbAt = limbs + count * 8
  machine.storeUInt64(limbAt, r0)
  calc count := count + 1
  goto split
:scaled
  when count == 0 zeroValue scale
:zeroValue
  zeroBlock = heap.take(2)
  machine.storeByte(zeroBlock, 48)
  machine.storeAddress(result, zeroBlock)
  calc zeroCountAt = result + 8
  machine.storeInt64(zeroCountAt, 1)
  calc zeroFractionAt = result + 16
  machine.storeInt64(zeroFractionAt, 0)
  heap.give(limbs)
  return
:scale
  when exponent < 0 fives twos
:twos
  set remaining exponent
  goto twoLoop
:twoLoop loop=while max=forever
  when remaining <= 0 toText twoStep
:twoStep in=twoLoop
  calc chunk = lowest(remaining, 29)
  calc factor = powerOfTwo(chunk)
  calc count := multiplyLimbs(limbs, count, factor)
  calc remaining := remaining - chunk
  goto twoLoop
:fives
  calc remaining := 0 - exponent
  goto fiveLoop
:fiveLoop loop=while max=forever
  when remaining < 13 lastFives fiveStep
:fiveStep in=fiveLoop
  calc count := multiplyLimbs(limbs, count, 1220703125)
  calc remaining := remaining - 13
  goto fiveLoop
:lastFives
  calc lastFactor = powerOfFive(remaining)
  calc count := multiplyLimbs(limbs, count, lastFactor)
  goto toText
:toText
  text = heap.take(count * 9 + 2)
  calc topAt = limbs + (count - 1) * 8
  top = machine.loadUInt64(topAt)
  calc topDigits = digitCount(top)
  calc out := topDigits
  set value top
  set place topDigits
  goto topLoop
:topLoop loop=while max=forever
  when place <= 0 rest topDigit
:topDigit in=topLoop
  calc place := place - 1
  calc topByte = convert.uint64ToByte(value % 10) + 48
  calc topByteAt = text + place
  machine.storeByte(topByteAt, topByte)
  calc value := value / 10
  goto topLoop
:rest
  calc at := count - 2
  goto limbLoop
:limbLoop loop=while max=forever
  when at < 0 finish limbDigits
:limbDigits in=limbLoop
  calc restAt = limbs + at * 8
  calc value := machine.loadUInt64(restAt)
  calc place := out + 9
  goto nineLoop
:nineLoop loop=while max=forever in=limbLoop
  when place <= out nextLimb nineDigit
:nineDigit in=nineLoop
  calc place := place - 1
  calc nineByte = convert.uint64ToByte(value % 10) + 48
  calc nineByteAt = text + place
  machine.storeByte(nineByteAt, nineByte)
  calc value := value / 10
  goto nineLoop
:nextLimb in=limbLoop
  calc out := out + 9
  calc at := at - 1
  goto limbLoop
:finish
  machine.storeAddress(result, text)
  calc countAt = result + 8
  machine.storeInt64(countAt, out)
  calc fractionAt = result + 16
  machine.storeInt64(fractionAt, fraction)
  heap.give(limbs)
  return

op lowest "The smaller of two whole numbers"
  input left Int64 copied
  input right Int64 copied
  output Int64
:begin
  when left <= right giveLeft giveRight
:giveLeft
  return left
:giveRight
  return right

op powerOfFive "5 to a power from 0 to 12"
  input power Int64 copied
  output UInt64
  let value UInt64 1 mut
  let left Int64 0 mut
:begin
  set left power
  goto eachPower
:eachPower loop=while max=power
  when left <= 0 finish step
:step in=eachPower
  calc value := value * 5
  calc left := left - 1
  goto eachPower
:finish
  return value

op digitCount "How many decimal digits a value has: 1 for 0"
  input value UInt64 copied
  output Int64
  let count Int64 1 mut
  let rest UInt64 0 mut
:begin
  calc rest := value / 10
  goto eachDigit
:eachDigit loop=while max=forever
  when rest == 0 finish step
:step in=eachDigit
  calc count := count + 1
  calc rest := rest / 10
  goto eachDigit
:finish
  return count

## ---------------------------------------------------------------- rounding digits

op roundingMode "The rounding mode floating values are written under: 0 to nearest, 1 downward, 2 upward, 3 toward zero, as fesetround set it (D-159, D-174)"
  invariant nearestByDefault "Gives 0, to nearest, until the rounding mode is changed"
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  mode = clong.roundingMode()
  return mode

op anyNonzeroDigit "Whether a range of ASCII digits holds one that is not `0`"
  input digits machine.Address copied
  input from Int64 copied
  input to Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let yes Bool true
  let no Bool false
:begin
  set at from
  goto eachDigit
:eachDigit loop=while max=forever
  when at >= to noneFound check
:check in=eachDigit
  current = clibrary.byteAt(digits, at)
  when current != 48 found step
:step in=eachDigit
  calc at := at + 1
  goto eachDigit
:found
  return yes
:noneFound
  return no

op roundDigits "Round ASCII digits to their first `keep` (1 or more, below the count) as the rounding mode rounds a value of that sign, in place: gives 1 when the carry passes the first digit (the digits are then all `0` and a `1` goes before them), else 0"
  input digits machine.Address copied
  input count Int64 copied
  input keep Int64 copied
  input negative Bool copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let up Bool false mut
  let at Int64 0 mut
  let carried Int64 1
  let noCarry Int64 0
  effect use system.calls
  uses systemCalls
:begin
  mode = roundingMode()
  restNonzero = anyNonzeroDigit(digits, keep, count)
  when mode == 0 nearest notNearest
:notNearest
  when mode == 1 downward notDownward
:notDownward
  when mode == 2 upward finish
:downward
  calc up := negative && restNonzero
  goto apply
:upward
  calc up := !negative && restNonzero
  goto apply
:nearest
  nextByte = clibrary.byteAt(digits, keep)
  when nextByte > 53 roundUp notAbove
:notAbove
  when nextByte < 53 finish halfway
:halfway
  calc afterHalf = keep + 1
  beyondHalf = anyNonzeroDigit(digits, afterHalf, count)
  if beyondHalf roundUp tie
:tie
  calc lastAt = keep - 1
  last = clibrary.byteAt(digits, lastAt)
  calc odd = (last & 1) == 1
  if odd roundUp finish
:roundUp
  calc up := true
  goto apply
:apply
  if up increment finish
:increment
  calc at := keep - 1
  goto carry
:carry loop=while max=forever
  when at < 0 overflow digit
:digit in=carry
  calc digitAt = digits + at
  current = machine.loadByte(digitAt)
  when current == 57 wrap bump
:wrap in=carry
  machine.storeByte(digitAt, 48)
  calc at := at - 1
  goto carry
:bump
  calc bumped = current + 1
  machine.storeByte(digitAt, bumped)
  return noCarry
:overflow
  return carried
:finish
  return noCarry

## ---------------------------------------------------------------- %f, %e, %g

op formatFixed "Write a value's digits (value = digits * 10^-fraction) in %f's form with a precision into a builder: the whole part (at least one digit), then `.` and `precision` digits (the `.` only with digits after it or `#`)"
  input body machine.Address copied
  input digits machine.Address copied
  input count Int64 copied
  input fraction Int64 copied
  input precision Int64 copied
  input hash Bool copied
  input negative Bool copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let lead Int64 0 mut
  let whole Int64 0 mut
  let length Int64 0 mut
  let start Int64 0 mut
:begin
  calc whole := count - fraction
  when whole < 1 leading noLeading
:leading
  calc lead := 1 - whole
  calc whole := 1
  goto build
:noLeading
  goto build
:build
  calc total = lead + count + precision + 2
  work = heap.take(total)
  calc workEnd = work + 1
  machine.fill(workEnd, 48, lead)
  calc digitsAt = work + 1 + lead
  machine.copy(digitsAt, digits, count)
  calc length := lead + count
  calc keep = whole + precision
  when keep < length round pad
:round
  calc workDigits = work + 1
  carry = roundDigits(workDigits, length, keep, negative)
  calc length := keep
  calc start := 1
  when carry == 1 carried emit
:carried
  machine.storeByte(work, 49)
  calc start := 0
  calc length := length + 1
  calc whole := whole + 1
  goto emit
:pad
  calc padAt = work + 1 + length
  calc padCount = keep - length
  machine.fill(padAt, 48, padCount)
  calc length := keep
  calc start := 1
  goto emit
:emit
  calc wholeAt = work + start
  wide.builderAdd(body, wholeAt, whole)
  calc point = precision > 0 || hash
  if point dot done
:dot
  wide.builderAddByte(body, 46)
  calc fractionAt = wholeAt + whole
  wide.builderAdd(body, fractionAt, precision)
  goto done
:done
  heap.give(work)
  return

op formatExponent "Write a value's digits in %e's form: one digit, `.` and `precision` digits (the `.` only with digits after it or `#`), then `e` or `E`, the exponent's sign, and at least two of its digits"
  input body machine.Address copied
  input digits machine.Address copied
  input count Int64 copied
  input fraction Int64 copied
  input precision Int64 copied
  input hash Bool copied
  input negative Bool copied
  input upper Bool copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let exponent Int64 0 mut
  let length Int64 0 mut
  let magnitude Int64 0 mut
:begin
  calc total = count + precision + 4
  work = heap.take(total)
  machine.copy(work, digits, count)
  set length count
  calc exponent := count - fraction - 1
  first = machine.loadByte(digits)
  when first == 48 zeroValue keepCheck
:zeroValue
  calc exponent := 0
  goto keepCheck
:keepCheck
  calc keep = precision + 1
  when keep < length round pad
:round
  carry = roundDigits(work, length, keep, negative)
  when carry == 1 carried emit
:carried
  machine.storeByte(work, 49)
  calc exponent := exponent + 1
  goto emit
:pad
  calc padAt = work + length
  calc padCount = keep - length
  machine.fill(padAt, 48, padCount)
  goto emit
:emit
  wide.builderAdd(body, work, 1)
  calc point = precision > 0 || hash
  if point dot mark
:dot
  wide.builderAddByte(body, 46)
  calc restAt = work + 1
  wide.builderAdd(body, restAt, precision)
  goto mark
:mark
  if upper capital small
:capital
  wide.builderAddByte(body, 69)
  goto exponentSign
:small
  wide.builderAddByte(body, 101)
  goto exponentSign
:exponentSign
  when exponent < 0 minus plus
:minus
  wide.builderAddByte(body, 45)
  calc magnitude := 0 - exponent
  goto exponentDigits
:plus
  wide.builderAddByte(body, 43)
  set magnitude exponent
  goto exponentDigits
:exponentDigits
  when magnitude < 10 leadingZero digitsOnly
:leadingZero
  wide.builderAddByte(body, 48)
  goto digitsOnly
:digitsOnly
  putWhole(body, magnitude)
  heap.give(work)
  return

op putWhole "Write a whole number 0 or more in decimal"
  input builder machine.Address copied
  input value Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let rest Int64 0 mut
  let place Int64 24 mut
:begin
  scratch = heap.take(24)
  set rest value
  goto eachDigit
:eachDigit loop=while max=forever
  calc place := place - 1
  calc digit = convert.int64ToByte(rest % 10) + 48
  calc digitAt = scratch + place
  machine.storeByte(digitAt, digit)
  calc rest := rest / 10
  when rest == 0 finish eachDigit
:finish
  calc startAt = scratch + place
  calc bytes = 24 - place
  wide.builderAdd(builder, startAt, bytes)
  heap.give(scratch)
  return

op formatGeneral "Write a value's digits in %g's form: P significant digits (6 by default, 1 for 0); %e's form when the exponent X after rounding is below -4 or P or more, else %f's with P-1-X digits after the point; trailing zeros (and a `.` left alone) dropped unless `#`"
  input body machine.Address copied
  input digits machine.Address copied
  input count Int64 copied
  input fraction Int64 copied
  input precision Int64 copied
  input hash Bool copied
  input negative Bool copied
  input upper Bool copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let significant Int64 6 mut
  let exponent Int64 0 mut
  let trailing Int64 0 mut
  let at Int64 0 mut
  let kept Int64 0 mut
  let places Int64 0 mut
:begin
  when precision == 0 oneDigit notOne
:oneDigit
  calc significant := 1
  goto measure
:notOne
  when precision > 0 given measure
:given
  set significant precision
  goto measure
:measure
  calc total = count + significant + 4
  work = heap.take(total)
  machine.copy(work, digits, count)
  calc exponent := count - fraction - 1
  first = machine.loadByte(digits)
  when first == 48 zeroValue roundCheck
:zeroValue
  calc exponent := 0
  goto roundCheck
:roundCheck
  set kept count
  when significant < count round padded
:round
  carry = roundDigits(work, count, significant, negative)
  set kept significant
  when carry == 1 carried trailingZeros
:carried
  machine.storeByte(work, 49)
  calc exponent := exponent + 1
  goto trailingZeros
:padded
  calc padAt = work + count
  calc padCount = significant - count
  machine.fill(padAt, 48, padCount)
  set kept significant
  goto trailingZeros
:trailingZeros
  calc at := kept - 1
  goto countZeros
:countZeros loop=while max=forever
  when at < 0 choose zeroCheck
:zeroCheck in=countZeros
  current = clibrary.byteAt(work, at)
  when current == 48 isZero choose
:isZero in=countZeros
  calc trailing := trailing + 1
  calc at := at - 1
  goto countZeros
:choose
  heap.give(work)
  when exponent < -4 || exponent >= significant exponentForm fixedForm
:fixedForm
  calc places := significant - 1 - exponent
  if hash fixedWrite fixedStrip
:fixedStrip
  calc places := places - lowest(trailing, places)
  goto fixedWrite
:fixedWrite
  formatFixed(body, digits, count, fraction, places, hash, negative)
  return
:exponentForm
  calc places := significant - 1
  if hash exponentWrite exponentStrip
:exponentStrip
  calc places := places - lowest(trailing, places)
  goto exponentWrite
:exponentWrite
  formatExponent(body, digits, count, fraction, places, hash, negative, upper)
  return

## ---------------------------------------------------------------- a floating value

op formatReal "Write a floating conversion (f F e E g G a A) of a value given as its sign, its kind (0 finite, 1 infinite, 2 NaN), and m * 2^e with m = high * 2^64 + low; `hexLead` is the bits of m before the point in %a's form (1 for a double, 4 for x87's long double, 1 for binary128) and `hexBits` those after it"
  input builder machine.Address copied
  input flags Int64 copied
  input width Int64 copied
  input precision Int64 copied
  input conversion Int64 copied
  input negative Bool copied
  input kind Int64 copied
  input high UInt64 copied
  input low UInt64 copied
  input exponent Int64 copied
  input hexBits Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let places Int64 6 mut
  let infinity String "inf"
  let infinityCapital String "INF"
  let notNumber String "nan"
  let notNumberCapital String "NAN"
:begin
  calc upper = conversion == 70 || conversion == 69 || conversion == 71 || conversion == 65
  calc hash = (flags & flagHash) != 0
  sign = signFor(negative, flags)
  body = wide.builderNew()
  nowhere = machine.zero()
  when kind == 1 infinite notInfinite
:infinite
  if upper infiniteCapital infiniteSmall
:infiniteCapital
  putText(body, infinityCapital)
  goto special
:infiniteSmall
  putText(body, infinity)
  goto special
:notInfinite
  when kind == 2 nan finite
:nan
  if upper nanCapital nanSmall
:nanCapital
  putText(body, notNumberCapital)
  goto special
:nanSmall
  putText(body, notNumber)
  goto special
:special
  specialText = wide.builderText(body)
  specialBytes = wide.builderLength(body)
  emitPadded(builder, flags, width, sign, nowhere, 0, specialText, specialBytes, false)
  goto done
:finite
  when conversion == 97 || conversion == 65 hexForm decimalForm
:hexForm
  prefix = heap.take(8)
  machine.storeByte(prefix, 48)
  calc xAt = prefix + 1
  calc xByte = conversionCase(conversion)
  machine.storeByte(xAt, xByte)
  formatHex(body, high, low, exponent, hexBits, precision, hash, negative, conversion)
  hexText = wide.builderText(body)
  hexBytes = wide.builderLength(body)
  emitPadded(builder, flags, width, sign, prefix, 2, hexText, hexBytes, true)
  heap.give(prefix)
  goto done
:decimalForm
  when precision >= 0 givenPlaces digitsOf
:givenPlaces
  set places precision
  goto digitsOf
:digitsOf
  result = heap.take(24)
  decimalDigits(high, low, exponent, result)
  digits = machine.loadAddress(result)
  calc countAt = result + 8
  count = machine.loadInt64(countAt)
  calc fractionAt = result + 16
  fraction = machine.loadInt64(fractionAt)
  when conversion == 102 || conversion == 70 fixed notFixed
:fixed
  formatFixed(body, digits, count, fraction, places, hash, negative)
  goto emitDecimal
:notFixed
  when conversion == 101 || conversion == 69 exponentForm general
:exponentForm
  formatExponent(body, digits, count, fraction, places, hash, negative, upper)
  goto emitDecimal
:general
  formatGeneral(body, digits, count, fraction, precision, hash, negative, upper)
  goto emitDecimal
:emitDecimal
  decimalText = wide.builderText(body)
  decimalBytes = wide.builderLength(body)
  emitPadded(builder, flags, width, sign, nowhere, 0, decimalText, decimalBytes, true)
  heap.give(digits)
  heap.give(result)
  goto done
:done
  bodyText = wide.builderText(body)
  heap.give(bodyText)
  heap.give(body)
  return

op formatHex "Write m * 2^e in %a's form without its `0x`: the digit before the point (the top `lead` bits of m, m holding lead + hexBits bits), `.` and the hexadecimal digits after it (as many as needed when there is no precision, else rounded to `precision`), `p`, and the binary exponent with its sign"
  input body machine.Address copied
  input high UInt64 copied
  input low UInt64 copied
  input exponent Int64 copied
  input hexBits Int64 copied
  input precision Int64 copied
  input hash Bool copied
  input negative Bool copied
  input conversion Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let digitsKept Int64 0 mut
  let places Int64 0 mut
  let power Int64 0 mut
  let at Int64 0 mut
  let leadValue UInt64 0 mut
  let magnitude Int64 0 mut
:begin
  calc digitsKept := (hexBits + 3) / 4
  calc shiftUp = digitsKept * 4 - hexBits
  digits = heap.take(digitsKept + 2)
  calc zeroMantissa = high == 0 && low == 0
  calc power := exponent + hexBits
  if zeroMantissa zeroPower fillDigits
:zeroPower
  calc power := 0
  goto fillDigits
:fillDigits
  goto eachDigit
:eachDigit loop=while max=forever
  when at >= digitsKept lead nibble
:nibble in=eachDigit
  calc bitFromTop = (at + 1) * 4 - shiftUp
  calc value = nibbleAt(high, low, hexBits - bitFromTop)
  calc nibbleByte = digitByte(value, conversion)
  calc nibbleSpot = digits + at
  machine.storeByte(nibbleSpot, nibbleByte)
  calc at := at + 1
  goto eachDigit
:lead
  calc leadValue := topBits(high, low, hexBits)
  when precision < 0 trimmed rounded
:trimmed
  set places digitsKept
  goto trimLoop
:trimLoop loop=while max=forever
  when places == 0 emit trimCheck
:trimCheck in=trimLoop
  calc lastAt = places - 1
  last = clibrary.byteAt(digits, lastAt)
  when last == 48 trimOne emit
:trimOne in=trimLoop
  calc places := places - 1
  goto trimLoop
:rounded
  set places precision
  when precision < digitsKept roundHex emit
:roundHex
  up = hexRoundsUp(digits, digitsKept, precision, leadValue, negative)
  if up carryHex emit
:carryHex
  calc carryOut = hexIncrement(digits, precision, conversion)
  calc leadValue := leadValue + carryOut
  goto emit
:emit
  calc leadByte = digitByte(leadValue, conversion)
  wide.builderAddByte(body, leadByte)
  calc point = places > 0 || hash
  if point dot exponentPart
:dot
  wide.builderAddByte(body, 46)
  calc shown = lowest(places, digitsKept)
  wide.builderAdd(body, digits, shown)
  calc extra = places - shown
  putRepeated(body, 48, extra)
  goto exponentPart
:exponentPart
  calc pByte = conversionCase(conversion) - 8
  wide.builderAddByte(body, pByte)
  when power < 0 minus plus
:minus
  wide.builderAddByte(body, 45)
  calc magnitude := 0 - power
  goto writeExponent
:plus
  wide.builderAddByte(body, 43)
  set magnitude power
  goto writeExponent
:writeExponent
  putWhole(body, magnitude)
  heap.give(digits)
  return

op nibbleAt "The four bits of m = high * 2^64 + low whose lowest is at a bit position (bits below 0 read as 0)"
  input high UInt64 copied
  input low UInt64 copied
  input position Int64 copied
  output UInt64
  let value UInt64 0 mut
:begin
  when position < 0 below notBelow
:below
  calc shift = 0 - position
  calc lowPart = low & 15
  calc value := (lowPart << shift) & 15
  return value
:notBelow
  when position >= 64 fromHigh notHigh
:fromHigh
  calc value := (high >> (position - 64)) & 15
  return value
:notHigh
  when position > 60 straddle fromLow
:straddle
  calc lowBits = low >> position
  calc highBits = high << (64 - position)
  calc value := (lowBits | highBits) & 15
  return value
:fromLow
  calc value := (low >> position) & 15
  return value

op topBits "The bits of m = high * 2^64 + low above its lowest `count`, which number 4 at most"
  input high UInt64 copied
  input low UInt64 copied
  input count Int64 copied
  output UInt64
  let value UInt64 0 mut
:begin
  when count >= 64 fromHigh fromLow
:fromHigh
  calc value := high >> (count - 64)
  return value
:fromLow
  calc lowPart = low >> count
  calc highPart = high << (64 - count)
  calc value := lowPart | highPart
  return value

op hexRoundsUp "Whether hexadecimal digits rounded to their first `keep` go up, as the rounding mode rounds a value of that sign: to nearest, ties to the even digit (the digit before the point when none is kept)"
  input digits machine.Address copied
  input count Int64 copied
  input keep Int64 copied
  input lead UInt64 copied
  input negative Bool copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let up Bool false mut
  let lastValue UInt64 0 mut
  effect use system.calls
  uses systemCalls
:begin
  mode = roundingMode()
  restNonzero = anyNonzeroDigit(digits, keep, count)
  when mode == 0 nearest notNearest
:notNearest
  when mode == 1 downward notDownward
:notDownward
  when mode == 2 upward finish
:downward
  calc up := negative && restNonzero
  return up
:upward
  calc up := !negative && restNonzero
  return up
:nearest
  nextByte = clibrary.byteAt(digits, keep)
  calc nextValue = hexValue(nextByte)
  when nextValue > 8 goesUp notAbove
:notAbove
  when nextValue < 8 finish halfway
:halfway
  calc afterHalf = keep + 1
  beyond = anyNonzeroDigit(digits, afterHalf, count)
  if beyond goesUp tie
:tie
  when keep == 0 leadDigit keptDigit
:leadDigit
  set lastValue lead
  goto parity
:keptDigit
  calc lastAt = keep - 1
  last = clibrary.byteAt(digits, lastAt)
  calc lastValue := hexValue(last)
  goto parity
:parity
  calc up := (lastValue & 1) == 1
  return up
:goesUp
  calc up := true
  return up
:finish
  return up

op hexValue "The value of an ASCII hexadecimal digit"
  input digit Byte copied
  output UInt64
:begin
  calc wide = convert.byteToUInt64(digit)
  when digit >= 97 small notSmall
:small
  calc smallValue = wide - 87
  return smallValue
:notSmall
  when digit >= 65 capital decimal
:capital
  calc capitalValue = wide - 55
  return capitalValue
:decimal
  calc decimalValue = wide - 48
  return decimalValue

op hexIncrement "Add one to the last of the first `keep` hexadecimal digits, carrying: gives 1 when the carry passes the first"
  input digits machine.Address copied
  input keep Int64 copied
  input conversion Int64 copied
  output UInt64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let carried UInt64 1
  let noCarry UInt64 0
:begin
  calc at := keep - 1
  goto carry
:carry loop=while max=forever
  when at < 0 overflow digit
:digit in=carry
  calc digitAt = digits + at
  current = machine.loadByte(digitAt)
  calc value = hexValue(current)
  when value == 15 wrap bump
:wrap in=carry
  machine.storeByte(digitAt, 48)
  calc at := at - 1
  goto carry
:bump
  calc bumped = digitByte(value + 1, conversion)
  machine.storeByte(digitAt, bumped)
  return noCarry
:overflow
  return carried

## ---------------------------------------------------------------- the whole format

op formatAll "printf's engine: write a format and the arguments a cursor reads into a builder, every conversion as glibc writes it in the C locale; gives the bytes written, or -1 (errno EOVERFLOW past INT_MAX bytes)"
  invariant writesLikeGlibc "Every conversion, flag, width, precision, and length writes what glibc's printf writes in the C locale"
  input format machine.Address copied
  input cursor machine.Address copied
  input builder machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  count = formatAllAs(format, cursor, builder, false)
  return count

op formatAllAs "printf's engine, for bytes or (wide mode) for wprintf: in wide mode the format is a wide format made bytes by unitText, %c %s %lc %ls write wide characters (unitText's bytes) padded and cut by characters, and %n and the count are in characters"
  invariant writesWideCharacters "In wide mode %lc and %ls keep characters past 255, padded and cut by characters, and the count is of characters"
  input format machine.Address copied
  input cursor machine.Address copied
  input builder machine.Address copied
  input wideMode Bool copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let place Int64 0 mut
  let counter Int64 0 mut
  let flags Int64 0 mut
  let width Int64 0 mut
  let precision Int64 0 mut
  let failed Int64 -1
  let runStart Int64 0 mut
:begin
  values = readArguments(format, cursor)
  spec = heap.take(96)
  goto eachByte
:eachByte loop=while max=forever
  current = clibrary.byteAt(format, place)
  when current == 0 finish notEnd
:notEnd in=eachByte
  when current == 37 percentSign plain
:plain in=eachByte
  set runStart place
  goto plainRun
:plainRun loop=while max=forever in=eachByte
  calc place := place + 1
  following = clibrary.byteAt(format, place)
  when following == 0 || following == 37 plainWrite plainRun
:plainWrite in=eachByte
  calc runAt = format + runStart
  calc runBytes = place - runStart
  wide.builderAdd(builder, runAt, runBytes)
  goto eachByte
:percentSign in=eachByte
  calc start = place + 1
  second = clibrary.byteAt(format, start)
  when second == 37 percent parse
:percent in=eachByte
  wide.builderAddByte(builder, 37)
  calc place := place + 2
  goto eachByte
:parse in=eachByte
  calc counter := parseSpec(format, start, spec, counter)
  endCell = machine.offset(spec, 64)
  calc place := machine.loadInt64(endCell)
  calc flags := machine.loadInt64(spec)
  widthCell = machine.offset(spec, 8)
  calc width := machine.loadInt64(widthCell)
  precisionCell = machine.offset(spec, 24)
  calc precision := machine.loadInt64(precisionCell)
  widthArgumentCell = machine.offset(spec, 16)
  widthArgument = machine.loadInt64(widthArgumentCell)
  when widthArgument > 0 starWidth precisionStar
:starWidth in=eachByte
  widthAt = argumentAt(values, widthArgument)
  widthWord = machine.loadInt64(widthAt)
  calc widthValue = convert.int32ToInt64(clibrary.lowInt32(widthWord))
  when widthValue < 0 negativeWidth positiveWidth
:negativeWidth in=eachByte
  calc flags := flags | flagMinus
  calc width := 0 - widthValue
  goto precisionStar
:positiveWidth in=eachByte
  set width widthValue
  goto precisionStar
:precisionStar in=eachByte
  precisionArgumentCell = machine.offset(spec, 32)
  precisionArgument = machine.loadInt64(precisionArgumentCell)
  when precisionArgument > 0 starPrecision convertIt
:starPrecision in=eachByte
  precisionAt = argumentAt(values, precisionArgument)
  precisionWord = machine.loadInt64(precisionAt)
  calc precisionValue = convert.int32ToInt64(clibrary.lowInt32(precisionWord))
  when precisionValue < 0 noPrecision givenPrecision
:noPrecision in=eachByte
  calc precision := -1
  goto convertIt
:givenPrecision in=eachByte
  set precision precisionValue
  goto convertIt
:convertIt in=eachByte
  conversionCell = machine.offset(spec, 48)
  conversion = machine.loadInt64(conversionCell)
  when conversion == 0 truncated known
:known in=eachByte
  argumentCell = machine.offset(spec, 56)
  argument = machine.loadInt64(argumentCell)
  valueAt = argumentAt(values, argument)
  lengthCell = machine.offset(spec, 40)
  length = machine.loadInt64(lengthCell)
  written = countWritten(builder, wideMode)
  convertOne(builder, conversion, flags, width, precision, length, valueAt, written, format, start, place, wideMode)
  goto eachByte
:truncated
  heap.give(values)
  heap.give(spec)
  clibrary.setErrno(invalidError)
  return failed
:finish
  heap.give(values)
  heap.give(spec)
  total = countWritten(builder, wideMode)
  when total > 2147483647 tooLong done
:tooLong
  clibrary.setErrno(overflowError)
  return failed
:done
  return total

op convertOne "Write one conversion of an argument (its 16 bytes at an address) into a builder; `written` is how many bytes came before it, which %n stores; a conversion glibc does not know is written as it stands in the format, from its `%`"
  input builder machine.Address copied
  input conversion Int64 copied
  input flags Int64 copied
  input width Int64 copied
  input precision Int64 copied
  input length Int64 copied
  input valueAt machine.Address copied
  input written Int64 copied
  input format machine.Address copied
  input start Int64 copied
  input end Int64 copied
  input wideMode Bool copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let nilWord String "(nil)"
:begin
  if wideMode wideCheck notWideMode
:wideCheck
  when conversion == 99 && length != 3 unitByte wideStringCheck
:unitByte
  formatUnits(builder, flags, width, 1, valueAt, 1)
  return
:wideStringCheck
  when conversion == 115 && length != 3 unitBytes wideCharacterCheck
:unitBytes
  calc byteText = machine.fromInt64(machine.loadInt64(valueAt))
  formatUnitString(builder, flags, width, precision, byteText, 1)
  return
:wideCharacterCheck
  when conversion == 99 || conversion == 67 unitWide wideTextCheck
:unitWide
  formatUnits(builder, flags, width, 1, valueAt, 4)
  return
:wideTextCheck
  when conversion == 115 || conversion == 83 unitWideText notWideMode
:unitWideText
  calc unitText = machine.fromInt64(machine.loadInt64(valueAt))
  formatUnitString(builder, flags, width, precision, unitText, 4)
  return
:notWideMode
  word = machine.loadInt64(valueAt)
  when conversion == 100 || conversion == 105 signedInteger notSigned
:signedInteger
  calc signedValue = signedWord(word, length)
  calc negative = signedValue < 0
  calc magnitude = magnitudeOf(signedValue)
  formatInteger(builder, flags, width, precision, conversion, negative, magnitude, true)
  return
:notSigned
  when conversion == 117 || conversion == 111 || conversion == 120 || conversion == 88 unsignedInteger notUnsigned
:unsignedInteger
  calc unsignedValue = unsignedWord(word, length)
  formatInteger(builder, flags, width, precision, conversion, false, unsignedValue, false)
  return
:notUnsigned
  when conversion == 112 pointer notPointer
:pointer
  when word == 0 nilPointer realPointer
:nilPointer
  nilText = machine.addressOfString(nilWord)
  nowhere = machine.zero()
  emitPadded(builder, flags, width, 0, nowhere, 0, nilText, 5, false)
  return
:realPointer
  calc pointerValue = convert.int64BitsToUInt64(word)
  formatInteger(builder, flags, width, precision, conversion, false, pointerValue, false)
  return
:notPointer
  when conversion == 99 && length != 3 character notCharacter
:character
  formatChar(builder, flags, width, word)
  return
:notCharacter
  when conversion == 115 && length != 3 stringConversion notString
:stringConversion
  calc text = machine.fromInt64(word)
  formatString(builder, flags, width, precision, text)
  return
:notString
  when conversion == 110 countConversion notCount
:countConversion
  storeCount(word, length, written)
  return
:notCount
  isReal = isRealConversion(conversion)
  if isReal realConversion notReal
:realConversion
  formatRealArgument(builder, flags, width, precision, conversion, length, valueAt)
  return
:notReal
  when conversion == 109 errorConversion notErrorConversion
:errorConversion
  errorAt = clibrary.errorMessage()
  formatString(builder, flags, width, precision, errorAt)
  return
:notErrorConversion
  when conversion == 99 || conversion == 67 wideCharacter notWideCharacter
:wideCharacter
  formatWideChar(builder, flags, width, word)
  return
:notWideCharacter
  when conversion == 115 || conversion == 83 wideString unknown
:wideString
  calc wideText = machine.fromInt64(word)
  formatWideString(builder, flags, width, precision, wideText)
  return
:unknown
  when conversion == 37 percent notPercent
:percent
  wide.builderAddByte(builder, 37)
  return
:notPercent
  calc percentAt = format + start - 1
  calc unknownBytes = end - start + 1
  wide.builderAdd(builder, percentAt, unknownBytes)
  return

op signedWord "An argument word as the signed integer its length gives: hh a signed char, h a short, none an int, the rest 64 bits"
  input word Int64 copied
  input length Int64 copied
  output Int64
:begin
  when length == 1 charCase notChar
:charCase
  calc asChar = (word << 56) >> 56
  return asChar
:notChar
  when length == 2 shortCase notShort
:shortCase
  calc asShort = (word << 48) >> 48
  return asShort
:notShort
  when length == 0 intCase longCase
:intCase
  calc asInt = (word << 32) >> 32
  return asInt
:longCase
  return word

op unsignedWord "An argument word as the unsigned integer its length gives: hh an unsigned char, h an unsigned short, none an unsigned int, the rest 64 bits"
  input word Int64 copied
  input length Int64 copied
  output UInt64
:begin
  calc bitsOf = convert.int64BitsToUInt64(word)
  when length == 1 charCase notChar
:charCase
  calc asChar = bitsOf & 255
  return asChar
:notChar
  when length == 2 shortCase notShort
:shortCase
  calc asShort = bitsOf & 65535
  return asShort
:notShort
  when length == 0 intCase longCase
:intCase
  calc asInt = bitsOf & 4294967295
  return asInt
:longCase
  return bitsOf

op magnitudeOf "The magnitude of a signed whole number as a UInt64 (the most negative one's included)"
  input value Int64 copied
  output UInt64
:begin
  calc bitsOf = convert.int64BitsToUInt64(value)
  when value < 0 negative positive
:negative
  calc flipped = math.wrappingSubtractUInt64(0, bitsOf)
  return flipped
:positive
  return bitsOf

op storeCount "%n: store how many bytes were written so far where the argument points, in the size its length gives"
  input word Int64 copied
  input length Int64 copied
  input written Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  target = machine.fromInt64(word)
  when length == 1 charCase notChar
:charCase
  calc low = convert.int64ToByte(written & 255)
  machine.storeByte(target, low)
  return
:notChar
  when length == 2 shortCase notShort
:shortCase
  calc lowByte = convert.int64ToByte(written & 255)
  machine.storeByte(target, lowByte)
  calc highAt = target + 1
  calc highByte = convert.int64ToByte((written >> 8) & 255)
  machine.storeByte(highAt, highByte)
  return
:notShort
  when length == 0 intCase longCase
:intCase
  calc asInt = clibrary.lowInt32(written)
  machine.storeInt32(target, asInt)
  return
:longCase
  machine.storeInt64(target, written)
  return

op formatRealArgument "Write a floating conversion of an argument: a double, or with L a long double (x87's 80 bits on x86_64 Linux, binary128 on AArch64 Linux, a double on Windows)"
  input builder machine.Address copied
  input flags Int64 copied
  input width Int64 copied
  input precision Int64 copied
  input conversion Int64 copied
  input length Int64 copied
  input valueAt machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let kind Int64 0 mut
  let mantissa UInt64 0 mut
  let power Int64 0 mut
:begin
  onLinux = system.linux()
  calc longForm = length == 5 && onLinux
  if longForm longReal double
:double
  bitsOf = machine.loadUInt64(valueAt)
  calc negative = (bitsOf >> 63) == 1
  calc biased = convert.uint64ToInt64((bitsOf >> 52) & 2047)
  calc fractionBits = bitsOf & 4503599627370495
  when biased == 2047 doubleSpecial doubleFinite
:doubleSpecial
  when fractionBits == 0 doubleInfinite doubleNan
:doubleInfinite
  calc kind := 1
  goto doubleWrite
:doubleNan
  calc kind := 2
  goto doubleWrite
:doubleFinite
  when biased == 0 subnormal normal
:subnormal
  set mantissa fractionBits
  calc power := -1074
  goto doubleWrite
:normal
  calc mantissa := fractionBits | 4503599627370496
  calc power := biased - 1075
  goto doubleWrite
:doubleWrite
  formatReal(builder, flags, width, precision, conversion, negative, kind, 0, mantissa, power, 52)
  return
:longReal
  onArm = system.aarch64()
  if onArm quad extended
:extended
  significand = machine.loadUInt64(valueAt)
  calc topAt = valueAt + 8
  top = machine.loadUInt64(topAt)
  calc extendedNegative = ((top >> 15) & 1) == 1
  calc extendedBiased = convert.uint64ToInt64(top & 32767)
  when extendedBiased == 32767 extendedSpecial extendedFinite
:extendedSpecial
  calc extendedFraction = significand & 9223372036854775807
  when extendedFraction == 0 extendedInfinite extendedNan
:extendedInfinite
  calc kind := 1
  goto extendedWrite
:extendedNan
  calc kind := 2
  goto extendedWrite
:extendedFinite
  set mantissa significand
  when extendedBiased == 0 extendedSubnormal extendedNormal
:extendedSubnormal
  calc power := -16445
  goto extendedWrite
:extendedNormal
  calc power := extendedBiased - 16446
  goto extendedWrite
:extendedWrite
  formatReal(builder, flags, width, precision, conversion, extendedNegative, kind, 0, mantissa, power, 60)
  return
:quad
  lowBits = machine.loadUInt64(valueAt)
  calc highAt = valueAt + 8
  highBits = machine.loadUInt64(highAt)
  calc quadNegative = (highBits >> 63) == 1
  calc quadBiased = convert.uint64ToInt64((highBits >> 48) & 32767)
  calc quadFraction = highBits & 281474976710655
  when quadBiased == 32767 quadSpecial quadFinite
:quadSpecial
  when quadFraction == 0 && lowBits == 0 quadInfinite quadNan
:quadInfinite
  calc kind := 1
  goto quadWrite
:quadNan
  calc kind := 2
  goto quadWrite
:quadFinite
  when quadBiased == 0 quadSubnormal quadNormal
:quadSubnormal
  set mantissa quadFraction
  calc power := -16494
  goto quadWrite
:quadNormal
  calc mantissa := quadFraction | 281474976710656
  calc power := quadBiased - 16495
  goto quadWrite
:quadWrite
  formatReal(builder, flags, width, precision, conversion, quadNegative, kind, mantissa, lowBits, power, 112)
  return

op formatWideChar "Write %lc: a wide character as the C locale's one byte (ASCII), padded; a character outside ASCII writes nothing (glibc fails the call with EILSEQ)"
  input builder machine.Address copied
  input flags Int64 copied
  input width Int64 copied
  input value Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc code = value & 4294967295
  when code < 128 ascii other
:ascii
  formatChar(builder, flags, width, code)
  return
:other
  return

op formatWideString "Write %ls: a wide string's characters as the C locale's bytes, at most `precision` of them, padded"
  input builder machine.Address copied
  input flags Int64 copied
  input width Int64 copied
  input precision Int64 copied
  input text machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let nullWord String "(null)"
:begin
  narrow = wide.builderNew()
  nowhere = machine.zero()
  calc isNull = text == nowhere
  if isNull nullCase eachUnit
:nullCase
  nullAt = machine.addressOfString(nullWord)
  formatString(builder, flags, width, precision, nullAt)
  heap.give(narrow)
  return
:eachUnit loop=while max=forever
  calc unitAt = text + at * 4
  unit = machine.loadInt32(unitAt)
  when unit == 0 emit limit
:limit in=eachUnit
  when precision >= 0 && at >= precision emit add
:add in=eachUnit
  calc low = convert.int64ToByte(convert.int32ToInt64(unit) & 255)
  wide.builderAddByte(narrow, low)
  calc at := at + 1
  goto eachUnit
:emit
  narrowText = wide.builderText(narrow)
  narrowBytes = wide.builderLength(narrow)
  emitPadded(builder, flags, width, 0, nowhere, 0, narrowText, narrowBytes, false)
  heap.give(narrowText)
  heap.give(narrow)
  return

## ---------------------------------------------------------------- wide mode (D-176)
##
## The wide printf family runs this engine in wide mode over its wide format made bytes: a wide character below 255
## is its byte, any other is 255 and six bytes of 0x80 plus six of its bits each (highest first), bytes no format
## reads as anything but text; the wide functions turn the result back into wide characters the same way.

op addUnit "Add a wide character to a wide mode text: its byte below 255, else 255 and six bytes of its bits"
  invariant escapesPastByte "Adds one byte below 255, seven bytes from 255 up"
  input builder machine.Address copied
  input code Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let shift Int64 30 mut
:begin
  calc unsigned = code & 4294967295
  when unsigned < 255 single escaped
:single
  wide.builderAddByte(builder, convert.int64ToByte(unsigned))
  return
:escaped
  wide.builderAddByte(builder, convert.int64ToByte(255))
  goto eachPiece
:eachPiece loop=while max=forever
  when shift < 0 done addPiece
:addPiece in=eachPiece
  calc piece = 128 | ((unsigned >> shift) & 63)
  wide.builderAddByte(builder, convert.int64ToByte(piece))
  calc shift := shift - 6
  goto eachPiece
:done
  return

op countWritten "How much a text being written holds: its bytes, or in wide mode its wide characters (an escape of seven bytes counts one)"
  input builder machine.Address copied
  input wideMode Bool copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let count Int64 0 mut
:begin
  length = wide.builderLength(builder)
  if wideMode measure plain
:plain
  return length
:measure
  text = wide.builderText(builder)
  goto eachByte
:eachByte loop=while max=forever
  when at >= length counted step
:step in=eachByte
  current = clibrary.byteAt(text, at)
  calc count := count + 1
  when current == 255 skipEscape skipOne
:skipEscape in=eachByte
  calc at := at + 7
  goto eachByte
:skipOne in=eachByte
  calc at := at + 1
  goto eachByte
:counted
  return count

op formatUnits "Write wide characters (bytes of 1 or wchar_t of 4 at an address) padded with spaces to a width (after them for `-`)"
  input builder machine.Address copied
  input flags Int64 copied
  input width Int64 copied
  input count Int64 copied
  input units machine.Address copied
  input unitBytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  calc left = (flags & flagMinus) != 0
  calc padding = width - count
  if left eachUnit padFirst
:padFirst
  putRepeated(builder, convert.int64ToByte(32), padding)
  goto eachUnit
:eachUnit loop=while max=forever
  when at >= count padded addOne
:addOne in=eachUnit
  calc unitAt = units + at * unitBytes
  when unitBytes == 1 readByte readWide
:readByte in=eachUnit
  calc byteCode = convert.byteToInt64(machine.loadByte(unitAt))
  addUnit(builder, byteCode)
  goto advance
:readWide in=eachUnit
  calc wideCode = convert.int32ToInt64(machine.loadInt32(unitAt))
  addUnit(builder, wideCode)
  goto advance
:advance in=eachUnit
  calc at := at + 1
  goto eachUnit
:padded
  if left padAfter done
:padAfter
  putRepeated(builder, convert.int64ToByte(32), padding)
  return
:done
  return

op formatUnitString "Write %s or %ls in wide mode: a string of bytes (1) or wchar_t (4), at most `precision` characters of it, `(null)` for the address 0 (nothing when the precision is below 6), padded with spaces"
  input builder machine.Address copied
  input flags Int64 copied
  input width Int64 copied
  input precision Int64 copied
  input text machine.Address copied
  input unitBytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let count Int64 0 mut
  let nullText String "(null)"
:begin
  nowhere = machine.zero()
  calc isNull = text == nowhere
  if isNull nullCase eachUnit
:nullCase
  when precision < 0 || precision >= 6 showNull showNothing
:showNull
  nullAt = machine.addressOfString(nullText)
  formatUnits(builder, flags, width, 6, nullAt, 1)
  return
:showNothing
  formatUnits(builder, flags, width, 0, text, 1)
  return
:eachUnit loop=while max=forever
  when precision >= 0 && count >= precision measured readUnit
:readUnit in=eachUnit
  calc unitAt = text + count * unitBytes
  when unitBytes == 1 byteUnit wideUnit
:byteUnit in=eachUnit
  calc byteCode = convert.byteToInt64(machine.loadByte(unitAt))
  when byteCode == 0 measured countIt
:wideUnit in=eachUnit
  calc wideCode = convert.int32ToInt64(machine.loadInt32(unitAt))
  when wideCode == 0 measured countIt
:countIt in=eachUnit
  calc count := count + 1
  goto eachUnit
:measured
  formatUnits(builder, flags, width, count, text, unitBytes)
  return

## ---------------------------------------------------------------- strtold (D-174)
##
## strtold reads the syntax strtod reads (clibrary.parseReal finds where it ends and what an infinity or NaN is) and
## makes the long double nearest the text's value without long double arithmetic. A decimal number's significant
## digits and power of ten are compared, exactly, with the decimal digits decimalDigits gives for a candidate
## m * 2^e: first the power of two at or below the value, then the significand's bits one at a time from the top,
## two bits more than the format keeps, then whether anything is left below them; clong.settleAs rounds that as the
## rounding mode rounds, among the subnormals too. A hexadecimal number's digits are its bits already. ERANGE comes
## with an infinity (or the largest value, rounding toward zero) past the largest, and with a subnormal or a zero
## that is not exactly the text's value.

op textDigits "The significant digits of a decimal text (white space, a sign, digits with a point, an exponent) as ASCII without leading or trailing zeros in a new block, and the power of ten P with value = 0.digits * 10^P: stored at an address, 0 the block, 8 the count, 16 P; the count is 0 for a zero"
  input text machine.Address copied
  input result machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let count Int64 0 mut
  let power Int64 0 mut
  let seenPoint Bool false mut
  let exponent Int64 0 mut
  let exponentSign Int64 1 mut
:begin
  length = clibrary.cStringLength(text)
  calc digits = heap.take(length + 1)
  machine.storeAddress(result, digits)
  goto spaces
:spaces loop=while max=forever
  current = clibrary.byteAt(text, at)
  space = clibrary.isSpaceByte(current)
  if space skipSpace sign
:skipSpace in=spaces
  calc at := at + 1
  goto spaces
:sign
  signByte = clibrary.byteAt(text, at)
  when signByte == 43 || signByte == 45 skipSign zeros
:skipSign
  calc at := at + 1
  goto zeros
:zeros loop=while max=forever
  zeroByte = clibrary.byteAt(text, at)
  when zeroByte == 48 skipZero pointCheck
:skipZero in=zeros
  calc at := at + 1
  when seenPoint afterPointZero zeros
:afterPointZero in=zeros
  calc power := power - 1
  goto zeros
:pointCheck in=zeros
  when zeroByte == 46 && !seenPoint takeLeadingPoint mantissa
:takeLeadingPoint in=zeros
  calc seenPoint := true
  calc at := at + 1
  goto zeros
:mantissa loop=while max=forever
  digit = clibrary.byteAt(text, at)
  when digit >= 48 && digit <= 57 keepDigit mantissaPoint
:keepDigit in=mantissa
  calc digitAt = digits + count
  machine.storeByte(digitAt, digit)
  calc count := count + 1
  when seenPoint advanceDigit wholeDigit
:wholeDigit in=mantissa
  calc power := power + 1
  goto advanceDigit
:advanceDigit in=mantissa
  calc at := at + 1
  goto mantissa
:mantissaPoint in=mantissa
  when digit == 46 && !seenPoint takePoint exponentCheck
:takePoint in=mantissa
  calc seenPoint := true
  calc at := at + 1
  goto mantissa
:exponentCheck
  marker = clibrary.byteAt(text, at)
  when (marker | 32) == 101 exponentStart trim
:exponentStart
  calc exponentAt = at + 1
  exponentFirst = clibrary.byteAt(text, exponentAt)
  when exponentFirst == 45 negativeExponent positiveExponent
:negativeExponent
  calc exponentSign := -1
  calc at := exponentAt + 1
  goto exponentDigits
:positiveExponent
  when exponentFirst == 43 skipPlus noSign
:skipPlus
  calc at := exponentAt + 1
  goto exponentDigits
:noSign
  set at exponentAt
  goto exponentDigits
:exponentDigits loop=while max=forever
  exponentDigit = clibrary.byteAt(text, at)
  when exponentDigit >= 48 && exponentDigit <= 57 addExponent applyExponent
:addExponent in=exponentDigits
  when exponent < 100000 grow skipExponentDigit
:grow in=exponentDigits
  calc exponent := exponent * 10 + convert.byteToInt64(exponentDigit) - 48
  goto skipExponentDigit
:skipExponentDigit in=exponentDigits
  calc at := at + 1
  goto exponentDigits
:applyExponent
  calc power := power + exponent * exponentSign
  goto trim
:trim loop=while max=forever
  when count == 0 store trimCheck
:trimCheck in=trim
  calc lastAt = digits + count - 1
  last = machine.loadByte(lastAt)
  when last == 48 dropZero store
:dropZero in=trim
  calc count := count - 1
  goto trim
:store
  calc countAt = result + 8
  machine.storeInt64(countAt, count)
  calc powerAt = result + 16
  machine.storeInt64(powerAt, power)
  return

op compareDigits "How 0.left * 10^leftPower compares with 0.right * 10^rightPower, both with no leading zero digit and some digit: -1, 0, or 1"
  input left machine.Address copied
  input leftCount Int64 copied
  input leftPower Int64 copied
  input right machine.Address copied
  input rightCount Int64 copied
  input rightPower Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let less Int64 -1
  let same Int64 0
  let more Int64 1
:begin
  when leftPower < rightPower giveLess powerSame
:powerSame
  when leftPower > rightPower giveMore eachDigit
:eachDigit loop=while max=forever
  when at >= leftCount && at >= rightCount giveSame compareOne
:compareOne in=eachDigit
  calc leftDigit = digitOrZero(left, leftCount, at)
  calc rightDigit = digitOrZero(right, rightCount, at)
  when leftDigit < rightDigit giveLess notLess
:notLess in=eachDigit
  when leftDigit > rightDigit giveMore advance
:advance in=eachDigit
  calc at := at + 1
  goto eachDigit
:giveLess
  return less
:giveMore
  return more
:giveSame
  return same

op digitOrZero "The ASCII digit at a position of digits, or `0` past their count"
  input digits machine.Address copied
  input count Int64 copied
  input at Int64 copied
  output Byte
  effect use machine.memory
  uses memoryAccess
  let zeroDigit Byte 48
:begin
  when at < count read pad
:read
  value = clibrary.byteAt(digits, at)
  return value
:pad
  return zeroDigit

op sideOf "How (high * 2^64 + low) * 2^exponent, nonzero, compares with a text's value 0.digits * 10^power: -1 below it, 0 equal, 1 above"
  input high UInt64 copied
  input low UInt64 copied
  input exponent Int64 copied
  input digits machine.Address copied
  input count Int64 copied
  input power Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  made = heap.take(24)
  decimalDigits(high, low, exponent, made)
  candidate = machine.loadAddress(made)
  calc candidateCountAt = made + 8
  candidateCount = machine.loadInt64(candidateCountAt)
  calc candidateFractionAt = made + 16
  candidateFraction = machine.loadInt64(candidateFractionAt)
  calc side = compareDigits(candidate, candidateCount, candidateCount - candidateFraction, digits, count, power)
  heap.give(candidate)
  heap.give(made)
  return side

op decimalParts "Put a decimal value 0.digits * 10^power (nonzero) in parts for a layout: the value's bits from its leading one down to two past the layout's precision, cut toward zero, and its power of two; gives 1 when the cut dropped something, else 0. A value far past the largest or below the least subnormal is put as a power of two past it"
  input digits machine.Address copied
  input count Int64 copied
  input power Int64 copied
  input parts machine.Address copied
  input layout Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let top Int64 0 mut
  let bit Int64 0 mut
  let high UInt64 0 mut
  let low UInt64 0 mut
  let trialHigh UInt64 0 mut
  let trialLow UInt64 0 mut
  let dropped Int64 1 mut
  let exactly Int64 0
  let oneBit UInt64 1
  let noBits UInt64 0
:begin
  precision = clong.precisionOf(layout)
  least = clong.leastPower(layout)
  greatest = clong.greatestPower(layout)
  calc width = precision + 2
  calc above = (power - 1) * 3321928 / 1000000
  when above > greatest + precision + 4 huge notHuge
:huge
  clong.setSignificand(parts, noBits, oneBit)
  clong.setPart(parts, 16, greatest + precision + 8)
  return dropped
:notHuge
  calc below = power * 3321928 / 1000000
  when below < least - 4 tiny search
:tiny
  clong.setSignificand(parts, noBits, oneBit)
  clong.setPart(parts, 16, least - 8)
  return dropped
:search
  set top above
  goto lower
:lower loop=while max=forever
  calc downSide = sideOf(noBits, oneBit, top, digits, count, power)
  when downSide > 0 stepDown raise
:stepDown in=lower
  calc top := top - 1
  goto lower
:raise loop=while max=forever
  calc upSide = sideOf(noBits, oneBit, top + 1, digits, count, power)
  when upSide <= 0 stepUp found
:stepUp in=raise
  calc top := top + 1
  goto raise
:found
  calc scale = top - (width - 1)
  calc bit := width - 2
  when width - 1 >= 64 topHigh topLow
:topHigh
  calc high := oneBit << (width - 65)
  goto eachBit
:topLow
  calc low := oneBit << (width - 1)
  goto eachBit
:eachBit loop=while max=forever
  when bit < 0 cutDone tryBit
:tryBit in=eachBit
  when bit >= 64 bitHigh bitLow
:bitHigh in=eachBit
  calc trialHigh := high | (oneBit << (bit - 64))
  set trialLow low
  goto compareTrial
:bitLow in=eachBit
  set trialHigh high
  calc trialLow := low | (oneBit << bit)
  goto compareTrial
:compareTrial in=eachBit
  calc side = sideOf(trialHigh, trialLow, scale, digits, count, power)
  when side <= 0 keepBit nextBit
:keepBit in=eachBit
  set high trialHigh
  set low trialLow
  when side == 0 exactCut nextBit
:nextBit in=eachBit
  calc bit := bit - 1
  goto eachBit
:exactCut
  set dropped exactly
  goto cutDone
:cutDone
  clong.setSignificand(parts, high, low)
  clong.setPart(parts, 16, scale)
  when bit < 0 lastCheck give
:lastCheck
  calc lastSide = sideOf(high, low, scale, digits, count, power)
  when lastSide == 0 exactLast give
:exactLast
  set dropped exactly
  goto give
:give
  return dropped

op hexDigitOf "The value of an ASCII hexadecimal digit, or -1 for any other byte"
  input value Byte copied
  output Int64
  let notHex Int64 -1
:begin
  calc code = convert.byteToInt64(value)
  calc folded = code | 32
  when code >= 48 && code <= 57 decimalDigit letterCheck
:decimalDigit
  calc decimalValue = code - 48
  return decimalValue
:letterCheck
  when folded >= 97 && folded <= 102 letterDigit other
:letterDigit
  calc letterValue = folded - 87
  return letterValue
:other
  return notHex

op hexParts "Put the hexadecimal number after a `0x` (hex digits with a point, then p, a sign, and decimal digits) in parts: its first 120 or so bits and its power of two; gives 1 when a nonzero digit did not fit, else 0"
  input text machine.Address copied
  input start Int64 copied
  input parts machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let place Int64 0 mut
  let high UInt64 0 mut
  let low UInt64 0 mut
  let power Int64 0 mut
  let dropped Int64 0 mut
  let seenPoint Bool false mut
  let scaled Int64 0 mut
  let scaleSign Int64 1 mut
  let digitsFrom Int64 0 mut
:begin
  set place start
  goto eachDigit
:eachDigit loop=while max=forever
  current = clibrary.byteAt(text, place)
  digit = hexDigitOf(current)
  when digit >= 0 takeDigit notDigit
:takeDigit in=eachDigit
  when (high >> 56) == 0 roomy crowded
:roomy in=eachDigit
  calc high := (high << 4) | (low >> 60)
  calc low := (low << 4) | convert.int64ToUInt64(digit)
  when seenPoint fractionDigit advance
:fractionDigit in=eachDigit
  calc power := power - 4
  goto advance
:crowded in=eachDigit
  when digit != 0 sticky afterSticky
:sticky in=eachDigit
  calc dropped := 1
  goto afterSticky
:afterSticky in=eachDigit
  when seenPoint advance wholeDigit
:wholeDigit in=eachDigit
  calc power := power + 4
  goto advance
:advance in=eachDigit
  calc place := place + 1
  goto eachDigit
:notDigit in=eachDigit
  when current == 46 && !seenPoint takePoint powerCheck
:takePoint in=eachDigit
  calc seenPoint := true
  calc place := place + 1
  goto eachDigit
:powerCheck
  when (current | 32) == 112 powerSign finish
:powerSign
  calc signAt = place + 1
  signByte = clibrary.byteAt(text, signAt)
  set digitsFrom signAt
  when signByte == 45 minusPower plusCheck
:minusPower
  calc scaleSign := -1
  calc digitsFrom := signAt + 1
  goto powerDigits
:plusCheck
  when signByte == 43 plusPower powerDigits
:plusPower
  calc digitsFrom := signAt + 1
  goto powerDigits
:powerDigits loop=while max=forever
  powerByte = clibrary.byteAt(text, digitsFrom)
  when powerByte >= 48 && powerByte <= 57 addPower applyPower
:addPower in=powerDigits
  when scaled < 1000000 growPower skipPower
:growPower in=powerDigits
  calc scaled := scaled * 10 + convert.byteToInt64(powerByte) - 48
  goto skipPower
:skipPower in=powerDigits
  calc digitsFrom := digitsFrom + 1
  goto powerDigits
:applyPower
  calc power := power + scaled * scaleSign
  goto finish
:finish
  clong.setSignificand(parts, high, low)
  clong.setPart(parts, 16, power)
  return dropped

op parseLongAs "strtold's work for a layout (0 double, 1 x87, 2 binary128, 3 float): the value of a C string's leading number, correctly rounded as the rounding mode rounds, written in the layout's bytes at an address, the end of what was read stored at `endAt` unless it is the address 0; ERANGE past the largest value and for a subnormal or zero that is not the text's exact value"
  invariant readsLikeStrtold "Reads what strtod reads, rounded once to the layout's precision"
  input text machine.Address copied
  input endAt machine.Address copied
  input layout Int64 copied
  input target machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let negative Int64 0 mut
  let dropped Int64 0 mut
  let rangeError Int32 34
:begin
  errnoAt = clibrary.errnoCell()
  saved = machine.loadInt32(errnoAt)
  endCell = heap.take(8)
  double = clibrary.parseReal(text, endCell)
  machine.storeInt32(errnoAt, saved)
  endPlace = machine.loadAddress(endCell)
  heap.give(endCell)
  nowhere = machine.zero()
  noEnd = machine.equal(endAt, nowhere)
  if noEnd measured storeEnd
:storeEnd
  machine.storeAddress(endAt, endPlace)
  goto measured
:measured
  consumed = machine.difference(endPlace, text)
  parts = clong.partsNew()
  when consumed == 0 packed spaces
:spaces loop=while max=forever
  leading = clibrary.byteAt(text, at)
  space = clibrary.isSpaceByte(leading)
  if space skipSpace signCheck
:skipSpace in=spaces
  calc at := at + 1
  goto spaces
:signCheck
  when leading == 45 minus plusCheck
:minus
  calc negative := 1
  calc at := at + 1
  goto classify
:plusCheck
  when leading == 43 plus classify
:plus
  calc at := at + 1
  goto classify
:classify
  clong.setPart(parts, 0, negative)
  first = clibrary.byteAt(text, at)
  calc folded = first | 32
  when folded == 105 || folded == 110 special numeric
:special
  doubleCell = heap.take(8)
  machine.storeFloat64(doubleCell, double)
  clong.unpackAs(doubleCell, parts, 0)
  heap.give(doubleCell)
  goto packed
:numeric
  calc second = clibrary.byteAt(text, at + 1)
  when first == 48 && (second | 32) == 120 && consumed > at + 1 hexadecimal decimal
:hexadecimal
  calc dropped := hexParts(text, at + 2, parts)
  goto rounded
:decimal
  info = heap.take(24)
  textDigits(text, info)
  digits = machine.loadAddress(info)
  calc countAt = info + 8
  count = machine.loadInt64(countAt)
  calc powerAt = info + 16
  power = machine.loadInt64(powerAt)
  heap.give(info)
  when count == 0 zeroDigits someDigits
:zeroDigits
  heap.give(digits)
  goto packed
:someDigits
  calc dropped := decimalParts(digits, count, power, parts, layout)
  heap.give(digits)
  goto rounded
:rounded
  clong.setPart(parts, 8, 1)
  high = clong.highOf(parts)
  low = clong.lowOf(parts)
  scale = clong.getPart(parts, 16)
  length = clong.bitLength(high, low)
  when length == 0 && dropped == 0 zeroValue settling
:zeroValue
  clong.setPart(parts, 8, 0)
  goto packed
:settling
  precision = clong.precisionOf(layout)
  greatest = clong.greatestPower(layout)
  clong.settleAs(parts, dropped, layout)
  kind = clong.getPart(parts, 8)
  when kind == 2 || length + scale - 1 >= greatest + precision overflowed tinyCheck
:overflowed
  clibrary.setErrno(rangeError)
  goto packed
:tinyCheck
  settledHigh = clong.highOf(parts)
  settledLow = clong.lowOf(parts)
  settledLength = clong.bitLength(settledHigh, settledLow)
  when kind == 0 || settledLength < precision tiny packed
:tiny
  settledPower = clong.getPart(parts, 16)
  calc cut = lowestOf(highestOf(settledPower - scale, 0), 128)
  calc inexact = dropped != 0 || kind == 0 || clong.lowBitsSet(high, low, cut)
  when inexact underflowed packed
:underflowed
  clibrary.setErrno(rangeError)
  goto packed
:packed
  clong.packAs(parts, target, layout)
  heap.give(parts)
  return

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

op highestOf "The larger of two whole numbers"
  input left Int64 copied
  input right Int64 copied
  output Int64
:begin
  when left > right giveLeft giveRight
:giveLeft
  return left
:giveRight
  return right

op parseLong "strtold: a C string's leading number as a long double, correctly rounded, with where it ends"
  input text machine.Address copied
  input endAt machine.Address copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "strtold"
:begin
  cell = heap.take(16)
  layout = clong.format()
  parseLongAs(text, endAt, layout, cell)
  value = machine.loadLongDouble(cell)
  heap.give(cell)
  return value

op scanLong "scanf's %Lf (and %Le %Lg %La): the text it collected read as strtold reads it, stored as a long double where the argument points"
  invariant storesLikeStrtold "Stores the bytes strtold's reading gives"
  input text machine.Address copied
  input target machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere = machine.zero()
  layout = clong.format()
  parseLongAs(text, nowhere, layout, target)
  return

op parseWideLong "wcstold: a wide string's leading number as a long double, as strtold reads its ASCII characters, with the end stored as a wide place"
  input text machine.Address copied
  input endAt machine.Address copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "wcstold"
  let units Int64 0 mut
  let copied Int64 0 mut
  let zeroByte Byte 0
:begin
  goto measure
:measure loop=while max=forever
  calc unitAt = text + units * 4
  unit = machine.loadInt32(unitAt)
  when unit > 0 && unit < 128 countUnit copyOut
:countUnit in=measure
  calc units := units + 1
  goto measure
:copyOut
  calc block = heap.take(units + 1)
  goto copyEach
:copyEach loop=while max=forever
  when copied >= units copyDone copyOne
:copyOne in=copyEach
  calc sourceAt = text + copied * 4
  wideUnit = machine.loadInt32(sourceAt)
  calc placeAt = block + copied
  machine.storeByte(placeAt, convert.int64ToByte(convert.int32ToInt64(wideUnit)))
  calc copied := copied + 1
  goto copyEach
:copyDone
  calc endByteAt = block + units
  machine.storeByte(endByteAt, zeroByte)
  endCell = heap.take(8)
  cell = heap.take(16)
  layout = clong.format()
  parseLongAs(block, endCell, layout, cell)
  value = machine.loadLongDouble(cell)
  endPlace = machine.loadAddress(endCell)
  consumed = machine.difference(endPlace, block)
  nowhere = machine.zero()
  noEnd = machine.equal(endAt, nowhere)
  heap.give(cell)
  heap.give(endCell)
  heap.give(block)
  if noEnd done storeEnd
:storeEnd
  calc wideEnd = text + consumed * 4
  machine.storeAddress(endAt, wideEnd)
  goto done
:done
  return value

@tests

op formatsTo "Whether formatAll writes a format with up to five argument slots (doubles as their bits) as expected"
  input format String borrowed
  input first UInt64 copied
  input second UInt64 copied
  input third UInt64 copied
  input fourth UInt64 copied
  input fifth UInt64 copied
  input expected String borrowed
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  formatBytes = string.byteLength(format)
  calc formatBlock = heap.take(formatBytes + 1)
  formatAt = machine.addressOfString(format)
  machine.copy(formatBlock, formatAt, formatBytes)
  slots = heap.take(48)
  machine.storeUInt64(slots, first)
  calc secondAt = slots + 8
  machine.storeUInt64(secondAt, second)
  calc thirdAt = slots + 16
  machine.storeUInt64(thirdAt, third)
  calc fourthAt = slots + 24
  machine.storeUInt64(fourthAt, fourth)
  calc fifthAt = slots + 32
  machine.storeUInt64(fifthAt, fifth)
  cell = heap.take(8)
  machine.storeAddress(cell, slots)
  cursor = heap.take(16)
  machine.storeInt64(cursor, 3)
  calc listAt = cursor + 8
  machine.storeAddress(listAt, cell)
  builder = wide.builderNew()
  count = formatAll(formatBlock, cursor, builder)
  text = wide.builderText(builder)
  length = wide.builderLength(builder)
  test.assertEqualInt64(length, count)
  written = machine.stringAt(text, length)
  test.assertEqualString(expected, written)
  heap.give(text)
  heap.give(builder)
  heap.give(cursor)
  heap.give(cell)
  heap.give(slots)
  heap.give(formatBlock)
  return

test formatTest "Integers, strings of digits, and floating values are written as glibc writes them: flags, widths, precisions, lengths, `*`, `%n$`, exact digits rounded to even, %a, infinities and NaN"
  verifies formatAll writesLikeGlibc
  verifies decimalDigits exactDigits
  verifies roundingMode nearestByDefault
  verifies cursorNew readsInOrder
  verifies cursorFree releasesCursor
  verifies readWord readsWords
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let format0 String "[%d] [%5d] [%-5d] [%05d]"
  let expected0 String "[42] [  -42] [42   ] [-0042]"
  let format1 String "[%x] [%#X] [%#o] [%.0d]"
  let expected1 String "[ff] [0XFF] [010] []"
  let format2 String "[%.3f] [%e] [%g] [%a]"
  let expected2 String "[3.142] [1.234560e-04] [1e-05] [0x1p+0]"
  let format3 String "[%.0f] [%.0f] [%g] [%G]"
  let expected3 String "[0] [2] [100000] [1E+20]"
  let format4 String "[%.10e] [%.20f]"
  let expected4 String "[4.9406564584e-324] [0.10000000000000000555]"
  let format5 String "%-10.4a|%lld %hhd %hu"
  let expected5 String "0x1.5555p-2|-1 44 4464"
  let format6 String "[%*d] [%.*f] %lu"
  let expected6 String "[     7] [1.00] 18446744073709551615"
  let format7 String "%2$d %1$d %%|%5%|%y"
  let expected7 String "2 1 %|%|%y"
  let format8 String "%f %F %e %+g"
  let expected8 String "inf -INF nan -nan"
  let format9 String "%08.3f|%-8.2e|%+.3g"
  let expected9 String "-003.142|1.23e+04|+0.000123"
  let format10 String "%#.3g|%#x|%#.0f|%.3a"
  let expected10 String "1.00|0|3.|0x1.000p+0"
  let format11 String "%a %A %.0e %g"
  let expected11 String "0x0.0000000000001p-1022 -0X0P+0 2e+01 0"
  let format12 String "%.17g %.0f %5.1f|%x"
  let expected12 String "0.10000000000000001 10000000000000000000000  -0.0|deadbeef"
:begin
  formatsTo(format0, 42, 18446744073709551574, 42, 18446744073709551574, 0, expected0)
  formatsTo(format1, 255, 255, 8, 0, 0, expected1)
  formatsTo(format2, 4614256650576692846, 4548686746489558237, 4532020583610935537, 4607182418800017408, 0, expected2)
  formatsTo(format3, 4602678819172646912, 4612811918334230528, 4681608360884174848, 4906019910204099648, 0, expected3)
  formatsTo(format4, 1, 4591870180066957722, 0, 0, 0, expected4)
  formatsTo(format5, 4599676419421066581, 18446744073709551615, 300, 70000, 0, expected5)
  formatsTo(format6, 6, 7, 2, 4607204936798154260, 18446744073709551615, expected6)
  formatsTo(format7, 1, 2, 0, 0, 0, expected7)
  formatsTo(format8, 9218868437227405312, 18442240474082181120, 9221120237041090560, 18444492273895866368, 0, expected8)
  formatsTo(format9, 13837628687431468654, 4668012722585352536, 4548684680454221981, 0, 0, expected9)
  formatsTo(format10, 4607182418800017408, 0, 4613937818241073152, 4607182418800017408, 0, expected10)
  formatsTo(format11, 1, 9223372036854775808, 4624633867356078080, 0, 0, expected11)
  formatsTo(format12, 4591870180066957722, 4936209963552724370, 13809297465413604475, 3735928559, 0, expected12)
  directFormat = heap.take(8)
  machine.storeByte(directFormat, 120)
  directCursor = cursorNew(directFormat)
  directBuilder = wide.builderNew()
  directCount = formatAll(directFormat, directCursor, directBuilder)
  test.assertEqualInt64(1, directCount)
  directText = wide.builderText(directBuilder)
  heap.give(directText)
  heap.give(directBuilder)
  cursorFree(directCursor)
  heap.give(directFormat)
  wordSlots = heap.take(16)
  calc secondSlot = wordSlots + 8
  machine.storeInt64(secondSlot, 77)
  wordCell = heap.take(8)
  machine.storeAddress(wordCell, wordSlots)
  wordCursor = heap.take(16)
  machine.storeInt64(wordCursor, 3)
  calc wordListAt = wordCursor + 8
  machine.storeAddress(wordListAt, wordCell)
  firstWord = readWord(wordCursor)
  test.assertEqualInt64(0, firstWord)
  secondWord = readWord(wordCursor)
  test.assertEqualInt64(77, secondWord)
  heap.give(wordCursor)
  heap.give(wordCell)
  heap.give(wordSlots)
  result = heap.take(24)
  decimalDigits(0, 3602879701896397, -55, result)
  calc countAt = result + 8
  digitsCount = machine.loadInt64(countAt)
  test.assertEqualInt64(55, digitsCount)
  calc fractionAt = result + 16
  fractionCount = machine.loadInt64(fractionAt)
  test.assertEqualInt64(55, fractionCount)
  digitsBlock = machine.loadAddress(result)
  heap.give(digitsBlock)
  heap.give(result)
  mode = roundingMode()
  test.assertEqualInt64(0, mode)
  nowhere = machine.zero()
  made = cursorNew(nowhere)
  layout = machine.loadInt64(made)
  onLinux = system.linux()
  onArm = system.aarch64()
  calc expectedLayout = layoutFor(onLinux, onArm)
  test.assertEqualInt64(expectedLayout, layout)
  cursorFree(made)
  return

op layoutFor "The va_list layout this system has: 3 on Windows, 1 on x86_64 Linux, 2 on AArch64 Linux"
  input onLinux Bool copied
  input onArm Bool copied
  output Int64
  let windowsLayout Int64 3
  let sysvLayout Int64 1
  let armLayout Int64 2
:begin
  if onLinux linux windows
:windows
  return windowsLayout
:linux
  if onArm arm sysv
:arm
  return armLayout
:sysv
  return sysvLayout

op cTextOf "A text as a C string in a new heap block"
  input text String borrowed
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let nul Byte 0
:begin
  bytes = string.byteLength(text)
  calc block = heap.take(bytes + 1)
  textAt = machine.addressOfString(text)
  machine.copy(block, textAt, bytes)
  calc endAt = block + bytes
  machine.storeByte(endAt, nul)
  return block

op sameAsDouble "Assert strtold's reading for the double layout is strtod's: the same bits, end, and errno"
  input text String borrowed
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let cleared Int32 0
:begin
  block = cTextOf(text)
  errnoAt = clibrary.errnoCell()
  machine.storeInt32(errnoAt, cleared)
  wantedEndCell = heap.take(8)
  wanted = clibrary.parseReal(block, wantedEndCell)
  wantedErrno = machine.loadInt32(errnoAt)
  machine.storeInt32(errnoAt, cleared)
  endCell = heap.take(8)
  cell = heap.take(16)
  parseLongAs(block, endCell, 0, cell)
  gotErrno = machine.loadInt32(errnoAt)
  gotBits = machine.loadUInt64(cell)
  test.assertTrue(gotBits == convert.float64BitsToUInt64(wanted))
  wantedEnd = machine.loadAddress(wantedEndCell)
  gotEnd = machine.loadAddress(endCell)
  sameEnd = machine.equal(wantedEnd, gotEnd)
  test.assertTrue(sameEnd)
  test.assertTrue(gotErrno == wantedErrno)
  heap.give(cell)
  heap.give(endCell)
  heap.give(wantedEndCell)
  heap.give(block)
  return

op expectParts "Assert strtold's reading of a text for a layout is the finite value (high * 2^64 + low) * 2^power with a sign, in the layout's bytes"
  input text String borrowed
  input layout Int64 copied
  input high UInt64 copied
  input low UInt64 copied
  input power Int64 copied
  input negative Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  block = cTextOf(text)
  nowhere = machine.zero()
  got = heap.take(16)
  parseLongAs(block, nowhere, layout, got)
  parts = clong.partsNew()
  clong.setPart(parts, 0, negative)
  clong.setPart(parts, 8, 1)
  clong.setPart(parts, 16, power)
  clong.setSignificand(parts, high, low)
  wanted = heap.take(16)
  clong.packAs(parts, wanted, layout)
  order = machine.compare(got, wanted, 16)
  test.assertEqualInt64(0, convert.int32ToInt64(order))
  heap.give(wanted)
  heap.give(parts)
  heap.give(got)
  heap.give(block)
  return

op expectKind "Assert strtold's reading of a text for a layout is a kind of value (0 zero, 1 finite, 2 infinite, 3 NaN) with a sign, and sets errno to a value"
  input text String borrowed
  input layout Int64 copied
  input kind Int64 copied
  input negative Int64 copied
  input expectedErrno Int32 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let cleared Int32 0
:begin
  block = cTextOf(text)
  nowhere = machine.zero()
  errnoAt = clibrary.errnoCell()
  machine.storeInt32(errnoAt, cleared)
  got = heap.take(16)
  parseLongAs(block, nowhere, layout, got)
  gotErrno = machine.loadInt32(errnoAt)
  test.assertTrue(gotErrno == expectedErrno)
  parts = clong.partsNew()
  clong.unpackAs(got, parts, layout)
  gotKind = clong.getPart(parts, 8)
  test.assertEqualInt64(kind, gotKind)
  gotSign = clong.getPart(parts, 0)
  test.assertEqualInt64(negative, gotSign)
  heap.give(parts)
  heap.give(got)
  heap.give(block)
  return

test longTextTest "strtold reads as strtod for the double layout (bits, end, errno), and gives the nearest x87, binary128, and float values: 0.1 on each, ties to even, exact whole numbers, the least x87 subnormal, x87 overflow, hexadecimal digits past the precision"
  verifies parseLongAs readsLikeStrtold
  verifies scanLong storesLikeStrtold
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  sameAsDouble("0.1")
  sameAsDouble("1e23")
  sameAsDouble("  -2.2250738585072011e-308xyz")
  sameAsDouble("4.9e-324")
  sameAsDouble("2.4703282292062328e-324")
  sameAsDouble("2.4703282292062327e-324")
  sameAsDouble("1.7976931348623157e308")
  sameAsDouble("1.7976931348623159e308")
  sameAsDouble("123456789012345678901234567890")
  sameAsDouble("9007199254740993")
  sameAsDouble("9007199254740993.0000000001")
  sameAsDouble("-0.0e5x")
  sameAsDouble("0x1.8p1")
  sameAsDouble("0x1.fffffffffffff8p0")
  sameAsDouble("0x1.00000000000008p0")
  sameAsDouble("0x1.000000000000081p0")
  sameAsDouble("0x.8p-1073")
  sameAsDouble("0x")
  sameAsDouble("infinity")
  sameAsDouble("-nan(12)")
  sameAsDouble("1e-400")
  sameAsDouble("1e309")
  sameAsDouble(".e5")
  expectParts("0.1", 1, 0, 14757395258967641293, -67, 0)
  expectParts("18446744073709551617", 1, 0, 9223372036854775808, 1, 0)
  expectParts("18446744073709551615", 1, 0, 18446744073709551615, 0, 0)
  expectParts("0x1.00000000000000018p0", 1, 0, 9223372036854775809, -63, 0)
  expectParts("-0.1", 2, 450359962737049, 11068046444225730970, -116, 1)
  expectParts("0.1", 3, 0, 13421773, -27, 0)
  expectParts("16777217", 3, 0, 8388608, 1, 0)
  expectParts("3.6451995318824746025e-4951", 1, 0, 1, -16445, 0)
  expectKind("1.2e4932", 1, 2, 0, 34)
  expectKind("-1.18e4932", 1, 1, 1, 0)
  expectKind("1e-5000", 1, 0, 0, 34)
  expectKind("-0", 2, 0, 1, 0)
  text = cTextOf("2.5e-1")
  scanned = heap.take(16)
  scanLong(text, scanned)
  wanted = heap.take(16)
  nowhere = machine.zero()
  layout = clong.format()
  parseLongAs(text, nowhere, layout, wanted)
  order = machine.compare(scanned, wanted, 16)
  test.assertTrue(order == 0)
  heap.give(wanted)
  heap.give(scanned)
  heap.give(text)
  return

test wideModeTest "Wide mode keeps a character past 255 as an escape, pads and cuts %lc, %s, and %ls by characters, takes %c's byte as a character, and counts characters"
  verifies formatAllAs writesWideCharacters
  verifies addUnit escapesPastByte
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  format = cTextOf("[%3lc|%-4s|%.2ls|%c]")
  bytes = cTextOf("ab")
  units = heap.take(16)
  machine.storeInt32(units, clibrary.lowInt32(65))
  calc secondUnit = units + 4
  machine.storeInt32(secondUnit, clibrary.lowInt32(128512))
  calc thirdUnit = units + 8
  machine.storeInt32(thirdUnit, clibrary.lowInt32(66))
  slots = heap.take(32)
  machine.storeInt64(slots, 20013)
  calc bytesSlot = slots + 8
  machine.storeInt64(bytesSlot, machine.toInt64(bytes))
  calc unitsSlot = slots + 16
  machine.storeInt64(unitsSlot, machine.toInt64(units))
  calc byteSlot = slots + 24
  machine.storeInt64(byteSlot, 233)
  cell = heap.take(8)
  machine.storeAddress(cell, slots)
  cursor = heap.take(16)
  machine.storeInt64(cursor, 3)
  calc listAt = cursor + 8
  machine.storeAddress(listAt, cell)
  builder = wide.builderNew()
  count = formatAllAs(format, cursor, builder, true)
  test.assertEqualInt64(15, count)
  length = wide.builderLength(builder)
  test.assertEqualInt64(27, length)
  text = wide.builderText(builder)
  calc escapeAt = text + 3
  escapeStart = machine.loadByte(escapeAt)
  test.assertTrue(escapeStart == 255)
  calc lastPieceAt = text + 9
  lastPiece = machine.loadByte(lastPieceAt)
  test.assertEqualInt64(173, convert.byteToInt64(lastPiece))
  calc fourthPieceAt = text + 7
  fourthPiece = machine.loadByte(fourthPieceAt)
  test.assertEqualInt64(132, convert.byteToInt64(fourthPiece))
  calc closingAt = text + 26
  closing = machine.loadByte(closingAt)
  test.assertTrue(closing == 93)
  calc accentAt = text + 25
  accent = machine.loadByte(accentAt)
  test.assertTrue(accent == 233)
  heap.give(text)
  heap.give(builder)
  units2 = wide.builderNew()
  addUnit(units2, 254)
  addUnit(units2, 255)
  unitsLength = wide.builderLength(units2)
  test.assertEqualInt64(8, unitsLength)
  heap.give(units2)
  heap.give(cursor)
  heap.give(cell)
  heap.give(slots)
  heap.give(units)
  heap.give(bytes)
  heap.give(format)
  return
