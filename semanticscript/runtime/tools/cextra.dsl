module cextra "The C library's remaining headers in SemanticScript: string.h's strtok family and glibc's extras, stdlib.h's strtof, rand, and aligned allocation, locale.h, assert.h, and inttypes.h, as glibc behaves in the C locale"
  path cextra
  imports standard.machine standard.system standard.string standard.math standard.compare standard.convert standard.bits standard.logic standard.test kernel output heap bignum wide clibrary
  exports none

capability memoryAccess "Authority to read and write the memory C callers hand the library, and this module's part of machine.state" use machine.memory none

capability systemCalls "Authority to take memory, write to standard error, and end the process" use system.calls none

## This module's functions are `abi library "<name>"` operations like clibrary's (D-153). machine.state bytes 26880 to
## 27903 belong to it: 26880 strtok's save pointer, 26888 whether rand's state is made, 26896 the place of rand's front
## word, 26904 the cell strtof reads its end into, 26912 to 27159 rand's 31 words (each a UInt64 holding 32 bits),
## 27168 to 27263 the static struct lconv localeconv gives (glibc's x86_64 layout, 96 bytes), 27264 the texts `.`,
## and the empty text, and `C` (setlocale's result), 27296 to 27327 the digits __assert_fail writes.
constant saveAt "Where strtok keeps its save pointer, in machine.state" Int64 26880

constant madeAt "Where whether rand's state is made is kept, in machine.state" Int64 26888

constant frontAt "Where the place of rand's front word is kept, in machine.state" Int64 26896

constant endCellAt "Where strtof reads the end of its number into, in machine.state" Int64 26904

constant wordsAt "Where rand's 31 words are kept, in machine.state" Int64 26912

constant lconvAt "Where the static struct lconv is kept, in machine.state" Int64 27168

constant dotAt "Where the text `.` is kept, in machine.state" Int64 27264

constant emptyAt "Where the empty text is kept, in machine.state" Int64 27266

constant localeNameAt "Where the text `C` is kept, in machine.state" Int64 27268

constant posixAt "Where the text `POSIX` is kept, in machine.state" Int64 27272

constant digitsAt "Where __assert_fail puts a number's digits, in machine.state" Int64 27296

constant rangeError "ERANGE: a result past what its type holds" Int32 34

constant invalidError "EINVAL: an argument the function does not take" Int32 22

constant memoryError "ENOMEM: no memory for the block asked" Int32 12

## ---------------------------------------------------------------- small pieces

op memberOf "Whether a byte is one of the bytes of a C string (the 0 byte never is)"
  invariant findsMember "True exactly when the byte is nonzero and appears in the set"
  input value Byte copied
  input set machine.Address copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  goto eachByte
:eachByte loop=while max=9223372036854775807
  member = clibrary.byteAt(set, at)
  when member == 0 absent check
:check in=eachByte
  when member == value present advance
:advance in=eachByte
  calc at := at + 1
  goto eachByte
:present
  return true
:absent
  return false

op spanBytes "How many bytes a C string starts with that are in a set (or, with `outside`, are not in it and not 0)"
  invariant countsSpan "Counts the leading bytes that are (or are not) set members"
  input text machine.Address copied
  input set machine.Address copied
  input outside Bool copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  goto eachByte
:eachByte loop=while max=9223372036854775807
  byte = clibrary.byteAt(text, at)
  when byte == 0 done look
:look in=eachByte
  member = memberOf(byte, set)
  calc stop = (member && outside) || (!member && !outside)
  when stop done advance
:advance in=eachByte
  calc at := at + 1
  goto eachByte
:done
  return at

op compareText "The difference of the first differing bytes of two C strings as unsigned chars, 0 when they are the same"
  input left machine.Address copied
  input right machine.Address copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  goto eachByte
:eachByte loop=while max=9223372036854775807
  a = clibrary.byteAt(left, at)
  b = clibrary.byteAt(right, at)
  when a != b differ same
:same in=eachByte
  when a == 0 equal advance
:advance in=eachByte
  calc at := at + 1
  goto eachByte
:equal
  return 0
:differ
  wideA = convert.byteToInt64(a)
  wideB = convert.byteToInt64(b)
  calc difference = wideA - wideB
  narrow = convert.int64ToInt32(difference)
  return narrow

## ---------------------------------------------------------------- string.h

op tokenize "strtok and strtok_r: the next token of a C string split at any of a set of bytes, its end (or the end of the string) kept in a cell"
  input text machine.Address copied
  input delimiters machine.Address copied
  input cell machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  nowhere = machine.zero()
  when text == nowhere fromCell fromText
:fromText
  fresh = tokenizeFrom(text, delimiters, cell)
  return fresh
:fromCell
  saved = machine.loadAddress(cell)
  when saved == nowhere nothing fromSaved
:nothing
  return nowhere
:fromSaved
  token = tokenizeFrom(saved, delimiters, cell)
  return token

op tokenizeFrom "The next token of a C string from a place, split at any of a set of bytes; the cell keeps where to go on"
  input place machine.Address copied
  input delimiters machine.Address copied
  input cell machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  nowhere = machine.zero()
  skip = spanBytes(place, delimiters, false)
  calc start = place + skip
  first = machine.loadByte(start)
  when first == 0 empty token
:empty
  machine.storeAddress(cell, start)
  return nowhere
:token
  length = spanBytes(start, delimiters, true)
  calc end = start + length
  last = machine.loadByte(end)
  when last == 0 final split
:final
  machine.storeAddress(cell, end)
  return start
:split
  machine.storeByte(end, 0)
  calc after = end + 1
  machine.storeAddress(cell, after)
  return start

op nextToken "strtok: the next token of a C string split at any of a set of bytes; NULL continues the last string"
  invariant tokenizes "Gives each token in turn and then NULL"
  input text machine.Address copied
  input delimiters machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "strtok"
:begin
  cell = kernel.stateAt(saveAt)
  token = tokenize(text, delimiters, cell)
  return token

op nextTokenSaved "strtok_r: strtok keeping its place where the caller says"
  input text machine.Address copied
  input delimiters machine.Address copied
  input save machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "strtok_r"
:begin
  token = tokenize(text, delimiters, save)
  return token

op separate "strsep: the token of a C string that ends at the first of a set of bytes (which becomes a 0), moving the caller's pointer past it, or to NULL at the end"
  input cell machine.Address copied
  input delimiters machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "strsep"
:begin
  nowhere = machine.zero()
  text = machine.loadAddress(cell)
  when text == nowhere nothing scan
:nothing
  return nowhere
:scan
  length = spanBytes(text, delimiters, true)
  calc end = text + length
  last = machine.loadByte(end)
  when last == 0 final split
:final
  machine.storeAddress(cell, nowhere)
  return text
:split
  machine.storeByte(end, 0)
  calc after = end + 1
  machine.storeAddress(cell, after)
  return text

op collate "strcoll: strcmp, which is what comparing in the C locale is"
  input left machine.Address copied
  input right machine.Address copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "strcoll"
:begin
  order = compareText(left, right)
  return order

op transform "strxfrm: in the C locale the string copied (at most a number of bytes, the 0 byte included when it fits); gives the string's length"
  input target machine.Address copied
  input source machine.Address copied
  input most Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "strxfrm"
:begin
  length = clibrary.cStringLength(source)
  when most > 0 copy done
:copy
  calc whole = length + 1
  when whole < most fits clip
:fits
  machine.copy(target, source, whole)
  return length
:clip
  machine.copy(target, source, most)
  return length
:done
  return length

op copyUntil "memccpy: copy bytes until the first one equal to a value has been copied, or a number of bytes; the place after that byte in the target, or NULL"
  input target machine.Address copied
  input source machine.Address copied
  input value Int32 copied
  input count Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  nowhere = machine.zero()
  wanted = clibrary.charOf(value)
  goto eachByte
:eachByte loop=while max=count
  when at >= count nothing step
:step in=eachByte
  byte = clibrary.byteAt(source, at)
  calc place = target + at
  machine.storeByte(place, byte)
  calc at := at + 1
  when byte == wanted found eachByte
:found
  calc end = target + at
  return end
:nothing
  return nowhere

op copyPlace "mempcpy: memcpy giving the place after the last byte written"
  input target machine.Address copied
  input source machine.Address copied
  input count Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "mempcpy"
:begin
  machine.copy(target, source, count)
  calc end = target + count
  return end

op copyUntilZero "stpcpy: strcpy giving the place of the 0 byte written"
  input target machine.Address copied
  input source machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "stpcpy"
:begin
  length = clibrary.cStringLength(source)
  calc whole = length + 1
  machine.copy(target, source, whole)
  calc end = target + length
  return end

op copyBoundedPlace "stpncpy: strncpy giving the place after the string copied (the target's end when the string filled it)"
  input target machine.Address copied
  input source machine.Address copied
  input most Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "stpncpy"
:begin
  length = clibrary.boundedLength(source, most)
  machine.copy(target, source, length)
  calc rest = most - length
  calc restAt = target + length
  machine.fill(restAt, 0, rest)
  return restAt

op memccpyC "memccpy, as the C library names it"
  input target machine.Address copied
  input source machine.Address copied
  input value Int32 copied
  input count Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "memccpy"
:begin
  end = copyUntil(target, source, value, count)
  return end

op findOrEnd "strchrnul: the first place of a character in a C string, or the place of its 0 byte"
  input text machine.Address copied
  input value Int32 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "strchrnul"
  let at Int64 0 mut
:begin
  wanted = clibrary.charOf(value)
  goto eachByte
:eachByte loop=while max=9223372036854775807
  byte = clibrary.byteAt(text, at)
  when byte == wanted found other
:other in=eachByte
  when byte == 0 found advance
:advance in=eachByte
  calc at := at + 1
  goto eachByte
:found
  calc place = text + at
  return place

op findLast "memrchr: the last place in a number of bytes of a byte equal to a value, or NULL"
  input block machine.Address copied
  input value Int32 copied
  input count Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "memrchr"
  let at Int64 0 mut
:begin
  nowhere = machine.zero()
  wanted = clibrary.charOf(value)
  set at count
  goto eachByte
:eachByte loop=while max=count
  when at <= 0 nothing look
:look in=eachByte
  calc at := at - 1
  byte = clibrary.byteAt(block, at)
  when byte == wanted found eachByte
:found
  calc place = block + at
  return place
:nothing
  return nowhere

## ---------------------------------------------------------------- locale.h

op setLocale "setlocale: the C locale answers to `C`, `POSIX`, and the empty name (read as C here) and to NULL, giving `C`; any other name gives NULL"
  invariant onlyC "Gives `C` for C, POSIX, the empty name, and NULL, else NULL"
  input category Int32 copied
  input name machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "setlocale"
:begin
  nowhere = machine.zero()
  when category < 0 invalid categoryHigh
:categoryHigh
  when category > 12 invalid fillName
:invalid
  clibrary.setErrno(invalidError)
  return nowhere
:fillName
  nameCell = kernel.stateAt(localeNameAt)
  machine.storeByte(nameCell, 67)
  calc zeroAt = nameCell + 1
  machine.storeByte(zeroAt, 0)
  posixCell = kernel.stateAt(posixAt)
  machine.storeByte(posixCell, 80)
  machine.storeByte(posixCell + 1, 79)
  machine.storeByte(posixCell + 2, 83)
  machine.storeByte(posixCell + 3, 73)
  machine.storeByte(posixCell + 4, 88)
  machine.storeByte(posixCell + 5, 0)
  when name == nowhere answer named
:named
  first = machine.loadByte(name)
  when first == 0 answer plainCheck
:plainCheck
  isC = compareText(name, nameCell)
  when isC == 0 answer posixCheck
:posixCheck
  isPosix = compareText(name, posixCell)
  when isPosix == 0 answer refuse
:refuse
  return nowhere
:answer
  return nameCell

op localeConventions "localeconv: the static struct lconv of the C locale: the decimal point `.`, every other text empty, every number CHAR_MAX (127)"
  invariant givesC "Gives glibc's C-locale struct lconv"
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "localeconv"
  let at Int64 0 mut
:begin
  block = kernel.stateAt(lconvAt)
  dot = kernel.stateAt(dotAt)
  empty = kernel.stateAt(emptyAt)
  machine.storeByte(dot, 46)
  calc dotEnd = dot + 1
  machine.storeByte(dotEnd, 0)
  machine.storeByte(empty, 0)
  machine.fill(block, 0, 96)
  machine.storeAddress(block, dot)
  goto eachText
:eachText loop=while max=9
  calc place = at * 8
  calc slot = block + 8
  calc field = slot + place
  machine.storeAddress(field, empty)
  calc at := at + 1
  when at >= 9 numbers eachText
:numbers
  calc numbersAt = block + 80
  machine.fill(numbersAt, 127, 14)
  return block

## ---------------------------------------------------------------- stdlib.h: rand

op seedWords "Make rand's 31 words from a seed as glibc's TYPE_3 generator does: the seed (1 for 0), then each word 16807 times the one before modulo 2^31 - 1, the front word at 3, and 310 words thrown away"
  input seed Int32 copied
  effect use machine.memory
  uses memoryAccess
  let word Int64 0 mut
  let value Int64 0 mut
  let at Int64 1 mut
  let thrown Int64 0 mut
:begin
  made = kernel.stateAt(madeAt)
  machine.storeInt64(made, 1)
  widened = convert.int32ToInt64(seed)
  set word widened
  when word == 0 zeroSeed fill
:zeroSeed
  calc word := 1
  goto fill
:fill
  words = kernel.stateAt(wordsAt)
  machine.storeUInt64(words, convert.int64BitsToUInt64(word & 4294967295))
  goto eachWord
:eachWord loop=while max=31
  when at >= 31 discard compute
:compute in=eachWord
  calc high = word / 127773
  calc low = word % 127773
  calc raw = 16807 * low - 2836 * high
  set value raw
  when raw < 0 wrap store
:wrap in=eachWord
  calc value := raw + 2147483647
  goto store
:store in=eachWord
  set word value
  calc slot = words + at * 8
  machine.storeUInt64(slot, convert.int64BitsToUInt64(value & 4294967295))
  calc at := at + 1
  goto eachWord
:discard
  frontCell = kernel.stateAt(frontAt)
  machine.storeInt64(frontCell, 3)
  goto eachThrown
:eachThrown loop=while max=310
  when thrown >= 310 finish throw
:throw in=eachThrown
  ignored = stepRandom()
  calc thrown := thrown + 1
  goto eachThrown
:finish
  return

op nextRandom "The next number of rand's generator, which is made from the seed 1 when no seed was given"
  output Int32
  effect use machine.memory
  uses memoryAccess
:begin
  made = kernel.stateAt(madeAt)
  flag = machine.loadInt64(made)
  when flag == 0 seed ready
:seed
  seedWords(1)
  goto ready
:ready
  number = stepRandom()
  return number

op stepRandom "The next word of rand's generator: the front word becomes itself plus the word three behind it (modulo 2^32), and the result is that sum shifted right once"
  output Int32
  effect use machine.memory
  uses memoryAccess
:begin
  words = kernel.stateAt(wordsAt)
  frontCell = kernel.stateAt(frontAt)
  front = machine.loadInt64(frontCell)
  calc rear = (front + 28) % 31
  calc frontSlot = words + front * 8
  calc rearSlot = words + rear * 8
  a = machine.loadUInt64(frontSlot)
  b = machine.loadUInt64(rearSlot)
  calc sum = (a + b) & 4294967295
  machine.storeUInt64(frontSlot, sum)
  calc nextFront = (front + 1) % 31
  machine.storeInt64(frontCell, nextFront)
  calc half = sum >> 1
  wide = convert.uint64ToInt64(half)
  narrow = convert.int64ToInt32(wide)
  return narrow

op randomNumber "rand: the next number from 0 to 2^31 - 1 of glibc's generator, which starts as srand(1) does"
  invariant followsGlibc "Gives glibc's TYPE_3 sequence for the seed"
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "rand"
:begin
  number = nextRandom()
  return number

op seedRandom "srand: start glibc's generator over from a seed"
  input seed Int32 copied
  effect use machine.memory
  uses memoryAccess
  abi library "srand"
:begin
  seedWords(seed)
  return

op randomReentrant "rand_r: glibc's three steps of x * 1103515245 + 12345 modulo 2^32 on the caller's seed, which give 11, 10, and 10 bits"
  input seed machine.Address copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "rand_r"
:begin
  start = machine.loadInt32(seed)
  wide = convert.int32ToInt64(start)
  first = convert.int64BitsToUInt64(wide & 4294967295)
  calc one = (first * 1103515245 + 12345) & 4294967295
  calc high = (one >> 16) % 2048
  calc two = (one * 1103515245 + 12345) & 4294967295
  calc middle = (high << 10) ^ ((two >> 16) % 1024)
  calc three = (two * 1103515245 + 12345) & 4294967295
  calc result = (middle << 10) ^ ((three >> 16) % 1024)
  keep = convert.uint64ToInt64(three)
  machine.storeInt32(seed, clibrary.lowInt32(keep))
  answer = convert.uint64ToInt64(result)
  narrow = convert.int64ToInt32(answer)
  return narrow

## ---------------------------------------------------------------- inttypes.h

op absoluteMax "imaxabs: the magnitude of an intmax_t (a long); the most negative one is itself"
  input value Int64 copied
  output Int64
  abi library "imaxabs"
:begin
  when value < 0 negate keep
:negate
  negated = math.wrappingSubtractInt64(0, value)
  return negated
:keep
  return value

op toMax "strtoimax: strtol, as intmax_t is a long"
  input text machine.Address copied
  input endAt machine.Address copied
  input base Int32 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "strtoimax"
:begin
  value = clibrary.parseWhole(text, endAt, base, false)
  return value

op toUnsignedMax "strtoumax: strtoul, as uintmax_t is an unsigned long"
  input text machine.Address copied
  input endAt machine.Address copied
  input base Int32 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "strtoumax"
:begin
  value = clibrary.parseWhole(text, endAt, base, true)
  return value

op parseWide "wcstol and its kin over wide characters (32-bit wchar_t): the leading characters from 1 to 127 are read as the bytes strtol reads, and the end is moved on by four bytes for each"
  input text machine.Address copied
  input endAt machine.Address copied
  input base Int32 copied
  input unsigned Bool copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let count Int64 0 mut
  let copied Int64 0 mut
:begin
  goto eachCharacter
:eachCharacter loop=while max=9223372036854775807
  calc place = text + count * 4
  character = machine.loadInt32(place)
  when character <= 0 measured checkHigh
:checkHigh in=eachCharacter
  when character > 127 measured advance
:advance in=eachCharacter
  calc count := count + 1
  goto eachCharacter
:measured
  calc size = count + 1
  buffer = heap.take(size)
  goto eachCopy
:eachCopy loop=while max=9223372036854775807
  when copied >= count parse move
:move in=eachCopy
  calc from = text + copied * 4
  code = machine.loadInt32(from)
  wide = convert.int32ToInt64(code)
  calc to = buffer + copied
  machine.storeByte(to, convert.int64ToByte(wide))
  calc copied := copied + 1
  goto eachCopy
:parse
  cell = kernel.stateAt(endCellAt)
  machine.storeAddress(cell, buffer)
  value = clibrary.parseWhole(buffer, cell, base, unsigned)
  end = machine.loadAddress(cell)
  read = machine.difference(end, buffer)
  heap.give(buffer)
  nowhere = machine.zero()
  when endAt == nowhere finish store
:store
  calc stop = text + read * 4
  machine.storeAddress(endAt, stop)
  goto finish
:finish
  return value

op wideToMax "wcstoimax: strtoimax over wide characters"
  input text machine.Address copied
  input endAt machine.Address copied
  input base Int32 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "wcstoimax"
:begin
  value = parseWide(text, endAt, base, false)
  return value

op wideToUnsignedMax "wcstoumax: strtoumax over wide characters"
  input text machine.Address copied
  input endAt machine.Address copied
  input base Int32 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "wcstoumax"
:begin
  value = parseWide(text, endAt, base, true)
  return value

## ---------------------------------------------------------------- stdlib.h: aligned allocation

op alignedBlock "A zeroed block of a size whose address is a multiple of a power of two; the address 0 when there is none. Alignments the runtime's heap gives anyway (16 bytes, 32 on Linux) take a plain block. On Linux a larger one is cut from a block of its own with the header a small block has, so free puts it back on the free list of its size (a large one's munmap fails and its mapping is left); on Windows HeapAlloc cannot align, so blocks are taken together until one is aligned and the others given back"
  input alignment Int64 copied
  input size Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let classSize Int64 64 mut
:begin
  nowhere = machine.zero()
  when size < 0 refuse sizeCheck
:sizeCheck
  when size > 1099511627776 refuse alignmentCheck
:alignmentCheck
  when alignment > 1099511627776 refuse systemCheck
:systemCheck
  onLinux = system.linux()
  when onLinux linuxLimit windowsLimit
:linuxLimit
  when alignment <= 32 plain linuxSmall
:windowsLimit
  when alignment <= 16 plain probing
:plain
  block = heap.take(size)
  return block
:refuse
  return nowhere
:probing
  found = probeAligned(alignment, size)
  return found
:linuxSmall
  calc need = size + 32
  when need <= 4096 sizing large
:sizing
  goto eachClass
:eachClass loop=while max=8
  when classSize >= need classFound grow
:grow in=eachClass
  calc classSize := classSize * 2
  goto eachClass
:classFound
  calc total = classSize + alignment
  base = heap.take(total)
  baseValue = machine.toInt64(base)
  calc first = baseValue + 32
  calc mask = 0 - alignment
  calc aligned = (first + alignment - 1) & mask
  place = machine.fromInt64(aligned)
  calc head = place - 32
  calc capacity = classSize - 32
  machine.storeInt64(head, capacity)
  calc mappingSlot = head + 8
  machine.storeInt64(mappingSlot, 0)
  calc usedSlot = head + 16
  machine.storeInt64(usedSlot, size)
  return place
:large
  calc raw = size + alignment + 4128
  calc pages = (raw + 4095) / 4096
  calc mapped = pages * 4096
  mapping = kernel.mapMemory(mapped)
  when mapping == nowhere refuse mappedOk
:mappedOk
  mappingValue = machine.toInt64(mapping)
  calc firstLarge = mappingValue + 32
  calc maskLarge = 0 - alignment
  calc alignedLarge = (firstLarge + alignment - 1) & maskLarge
  placeLarge = machine.fromInt64(alignedLarge)
  calc headLarge = placeLarge - 32
  machine.storeInt64(headLarge, size)
  calc mappingLarge = headLarge + 8
  machine.storeInt64(mappingLarge, mapped)
  calc usedLarge = headLarge + 16
  machine.storeInt64(usedLarge, size)
  return placeLarge

op probeAligned "On Windows: take blocks of about a size, all held at once, until one has an aligned address, then give the others back; the address 0 when none of up to 2048 (fewer for a large size) does"
  input alignment Int64 copied
  input size Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let foundValue Int64 0 mut
  let limit Int64 0 mut
  let clearing Int64 0 mut
  let room Int64 0 mut
:begin
  nowhere = machine.zero()
  calc wanted = alignment / 16 * 4 + 16
  calc room := 67108864 / (size + 512)
  set limit wanted
  when limit > 2048 capLimit roomCheck
:capLimit
  calc limit := 2048
  goto roomCheck
:roomCheck
  when room < 1 minimumRoom roomApply
:minimumRoom
  calc room := 1
  goto roomApply
:roomApply
  when limit > room trimLimit start
:trimLimit
  set limit room
  goto start
:start
  calc listBytes = limit * 8
  list = heap.take(listBytes)
  calc mask = alignment - 1
  goto eachProbe
:eachProbe loop=while max=2048
  when at >= limit gather probe
:probe in=eachProbe
  calc extra = (at * 7) % 17 * 16
  calc probeSize = size + extra
  block = heap.take(probeSize)
  value = machine.toInt64(block)
  calc low = value & mask
  when low == 0 aligned keep
:aligned in=eachProbe
  set foundValue value
  goto gather
:keep in=eachProbe
  calc slot = list + at * 8
  machine.storeInt64(slot, value)
  calc at := at + 1
  goto eachProbe
:gather
  goto eachClear
:eachClear loop=while max=2048
  when clearing >= at release give
:give in=eachClear
  calc clearSlot = list + clearing * 8
  held = machine.loadInt64(clearSlot)
  heldBlock = machine.fromInt64(held)
  heap.give(heldBlock)
  calc clearing := clearing + 1
  goto eachClear
:release
  heap.give(list)
  result = machine.fromInt64(foundValue)
  return result

op alignedAllocate "aligned_alloc: a block of a size aligned to a power of two, or NULL with EINVAL for another alignment and ENOMEM for no memory"
  input alignment Int64 copied
  input size Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "aligned_alloc"
:begin
  nowhere = machine.zero()
  when alignment <= 0 invalid positive
:positive
  calc rest = alignment & (alignment - 1)
  when rest == 0 take invalid
:invalid
  clibrary.setErrno(invalidError)
  return nowhere
:take
  block = alignedBlock(alignment, size)
  when block == nowhere refuse found
:refuse
  clibrary.setErrno(memoryError)
  return nowhere
:found
  return block

op alignedPosix "posix_memalign: store a block of a size aligned to a power of two that is a multiple of eight at the caller's pointer and give 0; EINVAL for another alignment, ENOMEM for no memory (errno is not set)"
  input where machine.Address copied
  input alignment Int64 copied
  input size Int64 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "posix_memalign"
:begin
  nowhere = machine.zero()
  when alignment < 8 invalid sizeCheck
:sizeCheck
  calc rest = alignment & (alignment - 1)
  when rest == 0 take invalid
:invalid
  return 22
:take
  block = alignedBlock(alignment, size)
  when block == nowhere refuse found
:refuse
  return 12
:found
  machine.storeAddress(where, block)
  return 0

## ---------------------------------------------------------------- assert.h

op addProgramName "Add the program's short name, argv[0] after its last `/` (and on Windows the command line's first word after its last `\` or `/`), to a builder"
  input builder machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let lastSlash Int64 0 mut
  let stop Int64 0 mut
  let quoted Bool false mut
:begin
  nowhere = machine.zero()
  onLinux = system.linux()
  when onLinux linuxName windowsName
:linuxName
  count = kernel.argumentCount()
  vector = kernel.argumentVector()
  when vector == nowhere finish haveVector
:haveVector
  when count <= 0 finish haveArgument
:haveArgument
  program = machine.loadAddress(vector)
  when program == nowhere finish measure
:measure
  length = clibrary.cStringLength(program)
  set stop length
  goto eachByte
:eachByte loop=while max=9223372036854775807
  when at >= stop addName look
:look in=eachByte
  byte = clibrary.byteAt(program, at)
  calc after = at + 1
  when byte == 47 mark advance
:mark in=eachByte
  set lastSlash after
  goto advance
:advance in=eachByte
  set at after
  goto eachByte
:addName
  calc rest = stop - lastSlash
  calc start = program + lastSlash
  wide.builderAdd(builder, start, rest)
  return
:windowsName
  line = system.getCommandLineW()
  firstUnit = machine.loadByte(line)
  when firstUnit == 34 openQuote scanUnits
:openQuote
  set quoted true
  calc at := 1
  set lastSlash 1
  goto scanUnits
:scanUnits
  goto eachUnit
:eachUnit loop=while max=9223372036854775807
  calc unitAt = line + at * 2
  low = machine.loadByte(unitAt)
  calc highAt = unitAt + 1
  high = machine.loadByte(highAt)
  when high != 0 unitOther unitLow
:unitLow in=eachUnit
  when low == 0 endUnits checkQuote
:checkQuote in=eachUnit
  when quoted quoteStop spaceStop
:quoteStop in=eachUnit
  when low == 34 endUnits slashes
:spaceStop in=eachUnit
  when low == 32 endUnits slashes
:slashes in=eachUnit
  calc afterUnit = at + 1
  when low == 92 markUnit slashForward
:slashForward in=eachUnit
  when low == 47 markUnit unitOther
:markUnit in=eachUnit
  set lastSlash afterUnit
  goto unitOther
:unitOther in=eachUnit
  calc at := at + 1
  goto eachUnit
:endUnits
  set stop at
  goto eachCopy
:eachCopy loop=while max=9223372036854775807
  when lastSlash >= stop finish copyUnit
:copyUnit in=eachCopy
  calc copyAt = line + lastSlash * 2
  letter = machine.loadByte(copyAt)
  wide.builderAddByte(builder, letter)
  calc lastSlash := lastSlash + 1
  goto eachCopy
:finish
  return

op addText "Add a C string to a builder"
  input builder machine.Address copied
  input text machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  length = clibrary.cStringLength(text)
  wide.builderAdd(builder, text, length)
  return

op addNumber "Add an unsigned number's decimal digits to a builder"
  input builder machine.Address copied
  input number Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let rest Int64 0 mut
  let place Int64 20 mut
:begin
  set rest number
  digits = kernel.stateAt(digitsAt)
  goto eachDigit
:eachDigit loop=while max=20
  calc place := place - 1
  calc digit = rest % 10
  calc letter = digit + 48
  calc slot = digits + place
  machine.storeByte(slot, convert.int64ToByte(letter))
  calc rest := rest / 10
  when rest == 0 emit eachDigit
:emit
  calc count = 20 - place
  calc start = digits + place
  wide.builderAdd(builder, start, count)
  return

op assertionFailed "__assert_fail: write glibc's message to standard error, `<program>: <file>:<line>: <function>: Assertion `<assertion>' failed.` and a line end (the function and its `: ` left out when NULL), then abort"
  input assertion machine.Address copied
  input file machine.Address copied
  input line Int32 copied
  input function machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__assert_fail"
  let colon String ": "
  let single String ":"
  let opening String "Assertion `"
  let closing String "' failed.\n"
:begin
  nowhere = machine.zero()
  builder = wide.builderNew()
  addProgramName(builder)
  colonAt = machine.addressOfString(colon)
  colonBytes = string.byteLength(colon)
  wide.builderAdd(builder, colonAt, colonBytes)
  addText(builder, file)
  singleAt = machine.addressOfString(single)
  wide.builderAdd(builder, singleAt, 1)
  wideLine = convert.int32ToInt64(line)
  calc unsignedLine = wideLine & 4294967295
  addNumber(builder, unsignedLine)
  wide.builderAdd(builder, colonAt, colonBytes)
  when function == nowhere assertionText withFunction
:withFunction
  addText(builder, function)
  wide.builderAdd(builder, colonAt, colonBytes)
  goto assertionText
:assertionText
  openingAt = machine.addressOfString(opening)
  openingBytes = string.byteLength(opening)
  wide.builderAdd(builder, openingAt, openingBytes)
  addText(builder, assertion)
  closingAt = machine.addressOfString(closing)
  closingBytes = string.byteLength(closing)
  wide.builderAdd(builder, closingAt, closingBytes)
  message = wide.builderText(builder)
  messageBytes = wide.builderLength(builder)
  handle = output.standardHandle(2)
  status = output.writeAll(handle, message, messageBytes)
  onLinux = system.linux()
  when onLinux linuxAbort windowsAbort
:linuxAbort
  action = heap.take(32)
  reset = system.rtSigaction(6, action, nowhere, 8)
  self = system.getpid()
  killed = system.kill(self, 6)
  system.exitGroup(134)
  return
:windowsAbort
  system.exitProcess(3)
  return

## ---------------------------------------------------------------- stdlib.h: strtof

## D-164: strtof reads the number as strtod does (clibrary's parseReal, correctly rounded to a double), then rounds
## that double to a float on integer bits, so no float operation can trap or double-round wrongly. A double rounded
## to a float differs from the number rounded to a float only when the double lies exactly halfway between two
## floats and the number does not; then the number's digits are compared with that halfway value exactly, in
## bignum. parseReal sets ERANGE for what overflows or underflows as a double (all of which does so as a float); this module sets it, through setErrno, for the rest, as glibc does for a float: a result past the largest float (an infinity from a finite
## text), and a decimal number that reads as a subnormal float or as 0 (a hexadecimal one only when inexact).
constant errnoAt "Where errno is read by the tests (clibrary's cell, the first thread's); the library sets it only through clibrary.setErrno" Int64 1536

constant inexactAt "Where roundToSingle says whether the float differs from the double, in machine.state" Int64 27280

op looksHex "Whether a C string, after white space and a sign, starts with 0x or 0X"
  input text machine.Address copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  goto eachSpace
:eachSpace loop=while max=9223372036854775807
  byte = clibrary.byteAt(text, at)
  space = clibrary.isSpaceByte(byte)
  when space skipSpace signCheck
:skipSpace in=eachSpace
  calc at := at + 1
  goto eachSpace
:signCheck
  when byte == 45 skipSign plusCheck
:plusCheck
  when byte == 43 skipSign prefixCheck
:skipSign
  calc at := at + 1
  goto prefixCheck
:prefixCheck
  first = clibrary.byteAt(text, at)
  calc nextAt = at + 1
  second = clibrary.byteAt(text, nextAt)
  calc lowSecond = second | 32
  calc answer = first == 48 && lowSecond == 120
  return answer

op exactCompare "How the number a C string starts with compares with a double given as mantissa times 2 to an exponent: -1 below it, 0 equal, 1 above; the text's digits are kept to 700 decimal (400 hexadecimal) places with a last 1 standing for any dropped that are not zero, and both sides are made whole numbers in bignum"
  input text machine.Address copied
  input mantissa UInt64 copied
  input exponent Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let started Bool false mut
  let sticky Bool false mut
  let seenPoint Bool false mut
  let kept Int64 0 mut
  let scale Int64 0 mut
  let radix UInt64 10 mut
  let digitLimit Int64 700 mut
  let power Int64 0 mut
  let powerNegative Bool false mut
  let hexForm Bool false mut
  let signed Int64 0 mut
  let decimalPower Int64 0 mut
  let binaryPower Int64 0 mut
:begin
  numbers = heap.take(3300)
  calc right = numbers + 1608
  bignum.setSmall(numbers, 0)
  goto eachSpace
:eachSpace loop=while max=9223372036854775807
  byte = clibrary.byteAt(text, at)
  space = clibrary.isSpaceByte(byte)
  when space skipSpace signCheck
:skipSpace in=eachSpace
  calc at := at + 1
  goto eachSpace
:signCheck
  when byte == 45 skipSign plusCheck
:plusCheck
  when byte == 43 skipSign prefixCheck
:skipSign
  calc at := at + 1
  goto prefixCheck
:prefixCheck
  first = clibrary.byteAt(text, at)
  calc nextAt = at + 1
  second = clibrary.byteAt(text, nextAt)
  calc lowSecond = second | 32
  calc isHexPrefix = first == 48 && lowSecond == 120
  when isHexPrefix hexMode digits
:hexMode
  calc radix := 16
  calc digitLimit := 400
  set hexForm true
  calc at := at + 2
  goto digits
:digits
  goto eachCharacter
:eachCharacter loop=while max=9223372036854775807
  character = clibrary.byteAt(text, at)
  digitValue = clibrary.digitOf(character)
  calc isDigit = digitValue < radix
  when isDigit digit pointCheck
:pointCheck in=eachCharacter
  calc isPoint = character == 46
  calc canPoint = isPoint && !seenPoint
  when canPoint point exponentCheck
:point in=eachCharacter
  set seenPoint true
  calc at := at + 1
  goto eachCharacter
:digit in=eachCharacter
  calc leading = !started && digitValue == 0
  when leading leadingZero significant
:leadingZero in=eachCharacter
  when seenPoint leadingScale advanceDigit
:leadingScale in=eachCharacter
  calc scale := scale - 1
  goto advanceDigit
:significant in=eachCharacter
  set started true
  when kept < digitLimit keep dropped
:keep in=eachCharacter
  bignum.multiplySmall(numbers, radix)
  bignum.addSmall(numbers, digitValue)
  calc kept := kept + 1
  when seenPoint keepScale advanceDigit
:keepScale in=eachCharacter
  calc scale := scale - 1
  goto advanceDigit
:dropped in=eachCharacter
  when digitValue != 0 markSticky droppedInteger
:markSticky in=eachCharacter
  set sticky true
  goto droppedInteger
:droppedInteger in=eachCharacter
  when seenPoint advanceDigit droppedScale
:droppedScale in=eachCharacter
  calc scale := scale + 1
  goto advanceDigit
:advanceDigit in=eachCharacter
  calc at := at + 1
  goto eachCharacter
:exponentCheck
  calc lowCharacter = character | 32
  calc decimalMarker = lowCharacter == 101 && !hexForm
  calc hexMarker = lowCharacter == 112 && hexForm
  calc hasMarker = decimalMarker || hexMarker
  when hasMarker readExponent finish
:readExponent
  calc signAt = at + 1
  signByte = clibrary.byteAt(text, signAt)
  set at signAt
  when signByte == 45 negativeExponent plusSign
:negativeExponent
  set powerNegative true
  calc at := at + 1
  goto exponentDigits
:plusSign
  when signByte == 43 skipPlus exponentDigits
:skipPlus
  calc at := at + 1
  goto exponentDigits
:exponentDigits
  goto eachExponent
:eachExponent loop=while max=9223372036854775807
  exponentByte = clibrary.byteAt(text, at)
  exponentValue = clibrary.digitOf(exponentByte)
  calc isExponentDigit = exponentValue < 10
  when isExponentDigit accumulate finish
:accumulate in=eachExponent
  when power > 100000 skipExponentDigit growPower
:growPower in=eachExponent
  calc power := power * 10 + convert.uint64ToInt64(exponentValue)
  goto skipExponentDigit
:skipExponentDigit in=eachExponent
  calc at := at + 1
  goto eachExponent
:finish
  when sticky addSticky total
:addSticky
  bignum.multiplySmall(numbers, radix)
  bignum.addSmall(numbers, 1)
  calc scale := scale - 1
  goto total
:total
  when powerNegative negatePower positivePower
:negatePower
  calc signed := 0 - power
  goto powers
:positivePower
  set signed power
  goto powers
:powers
  when hexForm hexTotal decimalTotal
:hexTotal
  calc binaryPower := scale * 4 + signed
  goto compare
:decimalTotal
  calc decimalPower := scale + signed
  goto compare
:compare
  bignum.setSmall(right, mantissa)
  when decimalPower > 0 scaleLeft rightCheck
:scaleLeft
  bignum.multiplyPowerOfTen(numbers, decimalPower)
  goto binaryCheck
:rightCheck
  when decimalPower < 0 scaleRight binaryCheck
:scaleRight
  calc negated = 0 - decimalPower
  bignum.multiplyPowerOfTen(right, negated)
  goto binaryCheck
:binaryCheck
  calc shiftBy = binaryPower - exponent
  when shiftBy > 0 shiftLeftSide shiftRightCheck
:shiftLeftSide
  bignum.shiftLeft(numbers, shiftBy)
  goto ordered
:shiftRightCheck
  when shiftBy < 0 shiftRightSide ordered
:shiftRightSide
  calc negatedShift = 0 - shiftBy
  bignum.shiftLeft(right, negatedShift)
  goto ordered
:ordered
  order = bignum.compareNumbers(numbers, right)
  heap.give(numbers)
  return order

op roundToSingle "The bits of the float nearest a positive finite double (ties to even), judged by the number the text gives when the double is exactly halfway between two floats; the cell inexactAt holds 1 unless the float is the double itself"
  input text machine.Address copied
  input magnitude UInt64 copied
  output UInt64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let rounded UInt64 0 mut
  let shift Int64 29 mut
  let bitOne UInt64 1
:begin
  flagCell = kernel.stateAt(inexactAt)
  machine.storeInt64(flagCell, 1)
  calc field = magnitude >> 52
  when field == 0 tiny fieldCheck
:tiny
  return 0
:fieldCheck
  fieldInt = convert.uint64ToInt64(field)
  calc unbiased = fieldInt - 1023
  when unbiased >= 128 overflow lowCheck
:overflow
  return 2139095040
:lowCheck
  when unbiased < -150 tiny subnormalCheck
:subnormalCheck
  when unbiased < -126 subnormal setup
:subnormal
  calc shift := 29 + (-126 - unbiased)
  goto setup
:setup
  calc significand = (magnitude & 4503599627370495) | 4503599627370496
  calc kept = significand >> shift
  calc unit = bitOne << shift
  calc remainder = significand & (unit - bitOne)
  calc half = bitOne << (shift - 1)
  when remainder == 0 exactFloat decide
:exactFloat
  machine.storeInt64(flagCell, 0)
  goto decide
:decide
  when remainder > half roundUp tieCheck
:tieCheck
  when remainder < half roundDown tie
:tie
  calc q = unbiased - 52
  order = exactCompare(text, significand, q)
  when order > 0 roundUp orderLow
:orderLow
  when order < 0 roundDown evenCheck
:evenCheck
  calc low = kept & 1
  when low == 1 roundUp roundDown
:roundUp
  calc rounded := kept + 1
  goto assemble
:roundDown
  set rounded kept
  goto assemble
:assemble
  when unbiased < -126 subnormalBits normalBits
:subnormalBits
  return rounded
:normalBits
  exponentBits = convert.int64BitsToUInt64(unbiased + 127)
  calc bits = (exponentBits << 23) + rounded - 8388608
  return bits

op toSingle "strtof: a C string's leading number as a float, correctly rounded, with where it ends; ERANGE as glibc sets it"
  invariant roundsToFloat "Gives the float nearest the number the text holds, for decimal and hexadecimal numbers, infinities, and NaN"
  input text machine.Address copied
  input endAt machine.Address copied
  output Float32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "strtof"
  let singleBits UInt64 0 mut
  let doubleBits UInt64 0 mut
:begin
  nowhere = machine.zero()
  endCell = kernel.stateAt(endCellAt)
  parsedValue = clibrary.parseReal(text, endCell)
  end = machine.loadAddress(endCell)
  when endAt == nowhere measured storeEnd
:storeEnd
  machine.storeAddress(endAt, end)
  goto measured
:measured
  bits = convert.float64BitsToUInt64(parsedValue)
  calc sign = bits & 9223372036854775808
  calc magnitude = bits & 9223372036854775807
  calc field = magnitude >> 52
  calc signPart = sign >> 32
  when field == 2047 special finite
:special
  when magnitude > 9218868437227405312 notANumber infinite
:notANumber
  calc singleBits := signPart | 2143289344
  goto build
:infinite
  calc singleBits := signPart | 2139095040
  goto build
:finite
  singleMagnitude = roundToSingle(text, magnitude)
  inexactCell = kernel.stateAt(inexactAt)
  inexact = machine.loadInt64(inexactCell)
  calc singleBits := signPart | singleMagnitude
  when singleMagnitude >= 2139095040 setRange tinyCheck
:setRange
  clibrary.setErrno(rangeError)
  goto build
:tinyCheck
  when singleMagnitude < 8388608 tiny build
:tiny
  when magnitude == 0 zeroValue nonzeroTiny
:zeroValue
  goto build
:nonzeroTiny
  isHexText = looksHex(text)
  when isHexText hexTiny setRange
:hexTiny
  when inexact != 0 setRange build
:build
  calc exponentField = (singleBits >> 23) & 255
  calc fraction = singleBits & 8388607
  calc doubleSign = (singleBits & 2147483648) << 32
  when exponentField == 255 specialBuild numberBuild
:specialBuild
  when fraction == 0 infinityBuild nanBuild
:infinityBuild
  calc doubleBits := doubleSign | 9218868437227405312
  goto convertBack
:nanBuild
  calc doubleBits := doubleSign | 9221120237041090560 | (fraction << 29)
  goto convertBack
:numberBuild
  when exponentField == 0 subnormalBuild normalBuild
:subnormalBuild
  when fraction == 0 zeroBuild subnormalValue
:zeroBuild
  calc doubleBits := doubleSign
  goto convertBack
:subnormalValue
  fractionInt = convert.uint64ToInt64(fraction)
  scaled = convert.int64ToFloat64(fractionInt)
  calc subnormalReal = scaled * 0x1p-149
  realBits = convert.float64BitsToUInt64(subnormalReal)
  calc doubleBits := realBits | doubleSign
  goto convertBack
:normalBuild
  calc biased = (exponentField + 896) << 52
  calc doubleBits := doubleSign | biased | (fraction << 29)
  goto convertBack
:convertBack
  real = convert.uint64BitsToFloat64(doubleBits)
  answer = convert.float64ToFloat32(real)
  return answer

@tests

op textOf "A C string made from a String, in a new heap block"
  input text String borrowed
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  at = machine.addressOfString(text)
  bytes = string.byteLength(text)
  calc size = bytes + 1
  block = heap.take(size)
  machine.copy(block, at, bytes)
  return block

op textIs "Whether a C string is exactly a String"
  input address machine.Address copied
  input text String borrowed
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  copy = textOf(text)
  order = compareText(address, copy)
  calc answer = order == 0
  return answer

op floatBitsOf "The bits, as a Float64, of the float strtof gives for a String; errno is cleared first"
  input text String borrowed
  output UInt64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  clibrary.setErrno(0)
  block = textOf(text)
  nowhere = machine.zero()
  value = toSingle(block, nowhere)
  wide = convert.float32ToFloat64(value)
  bits = convert.float64BitsToUInt64(wide)
  return bits

op currentErrno "The value errno holds now, read from its cell"
  output Int32
  effect use machine.memory
  uses memoryAccess
:begin
  errnoCell = kernel.stateAt(errnoAt)
  value = machine.loadInt32(errnoCell)
  return value

op randomIs "Whether rand gives a number"
  input expected Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
:begin
  number = randomNumber()
  wide = convert.int32ToInt64(number)
  calc answer = wide == expected
  return answer

test tokenTest "strtok gives each token in turn and then NULL, a span counts the bytes in or out of a set, strsep cuts at a set"
  verifies memberOf findsMember
  verifies spanBytes countsSpan
  verifies nextToken tokenizes
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere = machine.zero()
  text = textOf("a,b;;c")
  delimiters = textOf(",;")
  first = nextToken(text, delimiters)
  firstIs = textIs(first, "a")
  test.assertTrue(firstIs)
  second = nextToken(nowhere, delimiters)
  secondIs = textIs(second, "b")
  test.assertTrue(secondIs)
  third = nextToken(nowhere, delimiters)
  thirdIs = textIs(third, "c")
  test.assertTrue(thirdIs)
  fourth = nextToken(nowhere, delimiters)
  test.assertTrue(fourth == nowhere)
  letters = textOf("aabxc")
  members = textOf("ab")
  isMember = memberOf(98, members)
  test.assertTrue(isMember)
  inside = spanBytes(letters, members, false)
  test.assertEqualInt64(3, inside)
  stops = textOf("x")
  outside = spanBytes(letters, stops, true)
  test.assertEqualInt64(3, outside)
  cell = heap.take(8)
  words = textOf("one two")
  machine.storeAddress(cell, words)
  spaces = textOf(" ")
  word = separate(cell, spaces)
  wordIs = textIs(word, "one")
  test.assertTrue(wordIs)
  rest = machine.loadAddress(cell)
  restIs = textIs(rest, "two")
  test.assertTrue(restIs)
  last = separate(cell, spaces)
  lastIs = textIs(last, "two")
  test.assertTrue(lastIs)
  after = machine.loadAddress(cell)
  test.assertTrue(after == nowhere)
  return

test localeTest "setlocale takes C, POSIX, the empty name, and NULL and refuses others; localeconv holds glibc's C values"
  verifies setLocale onlyC
  verifies localeConventions givesC
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere = machine.zero()
  current = setLocale(6, nowhere)
  currentIs = textIs(current, "C")
  test.assertTrue(currentIs)
  posix = textOf("POSIX")
  setPosix = setLocale(6, posix)
  posixIs = textIs(setPosix, "C")
  test.assertTrue(posixIs)
  plain = textOf("")
  setPlain = setLocale(0, plain)
  plainIs = textIs(setPlain, "C")
  test.assertTrue(plainIs)
  other = textOf("de_DE.UTF-8")
  setOther = setLocale(6, other)
  test.assertTrue(setOther == nowhere)
  conventions = localeConventions()
  point = machine.loadAddress(conventions)
  pointIs = textIs(point, ".")
  test.assertTrue(pointIs)
  calc secondSlot = conventions + 8
  second = machine.loadAddress(secondSlot)
  secondIs = textIs(second, "")
  test.assertTrue(secondIs)
  calc digitsSlot = conventions + 80
  digits = machine.loadByte(digitsSlot)
  digitsWide = convert.byteToInt64(digits)
  test.assertEqualInt64(127, digitsWide)
  calc lastSlot = conventions + 93
  lastDigit = machine.loadByte(lastSlot)
  lastWide = convert.byteToInt64(lastDigit)
  test.assertEqualInt64(127, lastWide)
  return

test randomTest "rand follows glibc for srand(1) and srand(0) and starts as srand(1)"
  verifies randomNumber followsGlibc
  effect use machine.memory
  uses memoryAccess
:begin
  seedRandom(1)
  direct = randomNumber()
  directWide = convert.int32ToInt64(direct)
  test.assertEqualInt64(1804289383, directWide)
  r1 = randomIs(846930886)
  test.assertTrue(r1)
  r2 = randomIs(1681692777)
  test.assertTrue(r2)
  r3 = randomIs(1714636915)
  test.assertTrue(r3)
  seedRandom(0)
  r0 = randomIs(1804289383)
  test.assertTrue(r0)
  made = kernel.stateAt(madeAt)
  machine.storeInt64(made, 0)
  fresh = randomIs(1804289383)
  test.assertTrue(fresh)
  return

test singleTest "strtof rounds to the nearest float, a number just above a halfway case up and just below down, and sets ERANGE past the floats"
  verifies toSingle roundsToFloat
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  sample = textOf("2")
  nowhere = machine.zero()
  direct = toSingle(sample, nowhere)
  directWide = convert.float32ToFloat64(direct)
  directBits = convert.float64BitsToUInt64(directWide)
  directInt = convert.uint64BitsToInt64(directBits)
  test.assertEqualInt64(4611686018427387904, directInt)
  tenth = floatBitsOf("0.1")
  tenthWide = convert.uint64BitsToInt64(tenth)
  test.assertEqualInt64(4591870180174331904, tenthWide)
  above = floatBitsOf("1.00000005960464477539062500000001")
  aboveWide = convert.uint64BitsToInt64(above)
  test.assertEqualInt64(4607182419336888320, aboveWide)
  tie = floatBitsOf("1.000000059604644775390625")
  tieWide = convert.uint64BitsToInt64(tie)
  test.assertEqualInt64(4607182418800017408, tieWide)
  below = floatBitsOf("1.00000005960464477539062499999999")
  belowWide = convert.uint64BitsToInt64(below)
  test.assertEqualInt64(4607182418800017408, belowWide)
  hexAbove = floatBitsOf("0x1.00000100000000000000000001p0")
  hexAboveWide = convert.uint64BitsToInt64(hexAbove)
  test.assertEqualInt64(4607182419336888320, hexAboveWide)
  big = floatBitsOf("16777217")
  bigWide = convert.uint64BitsToInt64(big)
  test.assertEqualInt64(4715268809856909312, bigWide)
  largest = floatBitsOf("3.40282356e38")
  largestWide = convert.uint64BitsToInt64(largest)
  test.assertEqualInt64(5183643170566569984, largestWide)
  clean = currentErrno()
  test.assertEqualInt64(0, convert.int32ToInt64(clean))
  over = floatBitsOf("1e39")
  overWide = convert.uint64BitsToInt64(over)
  test.assertEqualInt64(9218868437227405312, overWide)
  overErrno = currentErrno()
  test.assertEqualInt64(34, convert.int32ToInt64(overErrno))
  small = floatBitsOf("1e-45")
  smallWide = convert.uint64BitsToInt64(small)
  test.assertEqualInt64(3936146074321813504, smallWide)
  smallErrno = currentErrno()
  test.assertEqualInt64(34, convert.int32ToInt64(smallErrno))
  minus = floatBitsOf("-0x1.8p1")
  minusWide = convert.uint64BitsToInt64(minus)
  test.assertEqualInt64(-4609434218613702656, minusWide)
  return
