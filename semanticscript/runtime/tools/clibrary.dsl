module clibrary "The C standard library written in SemanticScript: what ffi.open of c binds, and what a library the loader maps finds for its C imports (D-153)"
  path clibrary
  imports standard.machine standard.system standard.string standard.math standard.compare standard.convert standard.bits standard.logic standard.list standard.test kernel memory output heap floats wide
  exports prepare lookup cStringLength cLibraryName byteAt setErrno lowInt32 boundedLength errorText errorMessage memoryFind charOf isSpaceByte digitOf parseWhole parseReal runHandlers checkFits errnoCell windowsErrno

capability memoryAccess "Authority to read and write the memory C callers hand the library" use machine.memory none

capability systemCalls "Authority to write to standard output and error, read the environment, take memory, and end the process" use system.calls none

## D-153: every function here is an `abi library "<name>"` operation: the C calling convention, its C name in the
## table the compiler builds (`machine.cLibrary`), never a linker symbol. Each behaves as glibc does in the C locale,
## on Windows too, so a program's foreign calls give the same results on both: `long` and `size_t` are 64 bits
## (LP64), ctype's functions give glibc's class bits, comparisons give the difference of the first differing bytes,
## and errno is one cell that `__errno_location` gives. Streams are the numbers 1 (stdout) and 2 (stderr), which the
## data symbols `stdout` and `stderr` hold. machine.state bytes 1536 to 1663 belong to this module: 1536 errno, 1544
## stdout's cell, 1552 stderr's, 1560 __stack_chk_guard, 1568 the block of ctype's tables (0 until first asked for),
## 1576 to 1599 the three cells `__ctype_b_loc` and its kin give, 1600 the block getenv last gave on Windows, 1608 a
## Float64 strtod reads into, 1616 the bits a hexadecimal strtod made, 1624 the stdin cell. Bytes 1792 to 1887 too: strerror's text and
## its digits.
constant errnoAt "Where errno is kept, in machine.state" Int64 1536

constant stdinAt "Where the stdin cell is kept, in machine.state" Int64 1624

constant stdoutAt "Where the stdout cell is kept, in machine.state" Int64 1544

constant stderrAt "Where the stderr cell is kept, in machine.state" Int64 1552

constant guardAt "Where __stack_chk_guard is kept, in machine.state" Int64 1560

constant tablesAt "Where the block of ctype's tables is kept, in machine.state" Int64 1568

constant classCellAt "Where the cell __ctype_b_loc gives is kept, in machine.state" Int64 1576

constant upperCellAt "Where the cell __ctype_toupper_loc gives is kept, in machine.state" Int64 1584

constant lowerCellAt "Where the cell __ctype_tolower_loc gives is kept, in machine.state" Int64 1592

constant environmentAt "Where the block getenv last gave on Windows is kept, in machine.state" Int64 1600

constant realAt "Where strtod reads a Float64 into, in machine.state" Int64 1608

constant hexBitsAt "Where a hexadecimal strtod puts the bits it made, in machine.state" Int64 1616

constant exitListAt "Where the list of atexit's handlers is kept (its block, how many, how many it holds), in machine.state (D-162)" Int64 27904

constant quickListAt "Where the list of at_quick_exit's handlers is kept, in machine.state" Int64 27928

record Quotient "ldiv_t, lldiv_t, and imaxdiv_t: a quotient and a remainder (D-157's pair, returned in two registers)"
  field quotient Int64
  field remainder Int64

constant errorTextAt "Where strerror writes its text, in machine.state (D-160): 64 bytes" Int64 1792

constant errorDigitsAt "Where strerror writes a number's digits before copying them, in machine.state: 32 bytes" Int64 1856

constant forever "The bound of a loop over text that ends at its 0 byte" Int64 9223372036854775807

constant largest "PTRDIFF_MAX: the most bytes malloc hands out" Int64 9223372036854775807

constant rangeError "ERANGE: a result past what its type holds" Int32 34

constant invalidError "EINVAL: an argument the function does not take" Int32 22

constant memoryError "ENOMEM: no memory for the block asked" Int32 12

constant infinityBits "The bits of +infinity" UInt64 9218868437227405312

constant nanBits "The bits of the quiet NaN glibc gives" UInt64 9221120237041090560

constant signBit "The sign bit of a Float64" UInt64 9223372036854775808

record WindowsError "A Windows error code and the errno that stands for it"
  field code Int32
  field errno Int32

table windowsErrors "Each Windows error code a call of the library can give, with the errno glibc's Linux number of the same failure (D-171); a code not here is EINVAL" WindowsError
  row code1 code=1 errno=22
  row code2 code=2 errno=2
  row code3 code=3 errno=2
  row code4 code=4 errno=24
  row code5 code=5 errno=13
  row code6 code=6 errno=9
  row code8 code=8 errno=12
  row code12 code=12 errno=13
  row code13 code=13 errno=22
  row code14 code=14 errno=12
  row code15 code=15 errno=2
  row code16 code=16 errno=13
  row code17 code=17 errno=18
  row code18 code=18 errno=2
  row code19 code=19 errno=30
  row code20 code=20 errno=19
  row code21 code=21 errno=5
  row code23 code=23 errno=5
  row code25 code=25 errno=29
  row code26 code=26 errno=5
  row code29 code=29 errno=5
  row code30 code=30 errno=5
  row code31 code=31 errno=5
  row code32 code=32 errno=13
  row code33 code=33 errno=13
  row code36 code=36 errno=24
  row code38 code=38 errno=5
  row code39 code=39 errno=28
  row code50 code=50 errno=95
  row code51 code=51 errno=112
  row code53 code=53 errno=2
  row code55 code=55 errno=19
  row code59 code=59 errno=5
  row code64 code=64 errno=104
  row code65 code=65 errno=13
  row code67 code=67 errno=2
  row code80 code=80 errno=17
  row code82 code=82 errno=13
  row code84 code=84 errno=12
  row code87 code=87 errno=22
  row code89 code=89 errno=11
  row code108 code=108 errno=13
  row code109 code=109 errno=32
  row code110 code=110 errno=2
  row code111 code=111 errno=36
  row code112 code=112 errno=28
  row code114 code=114 errno=9
  row code120 code=120 errno=38
  row code121 code=121 errno=110
  row code122 code=122 errno=34
  row code123 code=123 errno=2
  row code126 code=126 errno=2
  row code127 code=127 errno=2
  row code130 code=130 errno=9
  row code131 code=131 errno=22
  row code132 code=132 errno=29
  row code145 code=145 errno=39
  row code158 code=158 errno=13
  row code161 code=161 errno=2
  row code164 code=164 errno=11
  row code167 code=167 errno=13
  row code170 code=170 errno=16
  row code183 code=183 errno=17
  row code186 code=186 errno=22
  row code193 code=193 errno=8
  row code206 code=206 errno=36
  row code212 code=212 errno=13
  row code215 code=215 errno=11
  row code230 code=230 errno=32
  row code231 code=231 errno=16
  row code232 code=232 errno=32
  row code233 code=233 errno=107
  row code267 code=267 errno=20
  row code282 code=282 errno=84
  row code298 code=298 errno=11
  row code995 code=995 errno=4
  row code998 code=998 errno=14
  row code1006 code=1006 errno=19
  row code1110 code=1110 errno=5
  row code1117 code=1117 errno=5
  row code1224 code=1224 errno=13
  row code1450 code=1450 errno=12
  row code1455 code=1455 errno=12
  row code1460 code=1460 errno=110
  row code1784 code=1784 errno=14
  row code1816 code=1816 errno=12
  row code10004 code=10004 errno=4
  row code10013 code=10013 errno=13
  row code10014 code=10014 errno=14
  row code10022 code=10022 errno=22
  row code10024 code=10024 errno=24
  row code10035 code=10035 errno=11
  row code10036 code=10036 errno=115
  row code10037 code=10037 errno=114
  row code10038 code=10038 errno=88
  row code10040 code=10040 errno=90
  row code10047 code=10047 errno=97
  row code10048 code=10048 errno=98
  row code10049 code=10049 errno=99
  row code10050 code=10050 errno=100
  row code10051 code=10051 errno=101
  row code10053 code=10053 errno=103
  row code10054 code=10054 errno=104
  row code10055 code=10055 errno=105
  row code10056 code=10056 errno=106
  row code10057 code=10057 errno=107
  row code10060 code=10060 errno=110
  row code10061 code=10061 errno=111
  row code10065 code=10065 errno=113

## ---------------------------------------------------------------- the process and traps

op endProcess "End the process with an exit code: ExitProcess on Windows, exit_group on Linux (D-138)"
  input code Int32 copied
  effect use system.calls
  uses systemCalls
:begin
  osCheck: onLinux = system.linux()
  if onLinux linuxExit windowsExit
:linuxExit
  widenCode: wideCode = convert.int32ToInt64(code)
  callExit: exitResult = system.exitGroup(wideCode)
  return
:windowsExit
  callExitProcess: system.exitProcess(code)
  return

op writeStream "Write bytes to stream 1 (stdout) or 2 (stderr); gives 0, or -1 when the stream is neither or the write fails"
  input stream Int64 copied
  input text machine.Address copied
  input bytes Int64 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let failedStatus Int32 -1
  let okStatus Int32 0
:begin
  outCheck: isOut = compare.equalInt64(stream, one=1)
  errCheck: isErr = compare.equalInt64(stream, two=2)
  eitherCheck: known = logic.or(isOut, isErr)
  if known write refuse
:write
  narrowStream: stream32 = convert.int64ToInt32(stream)
  findHandle: handle = output.standardHandle(stream32)
  writeIt: status = output.writeAll(handle, text, bytes)
  okCheck: wrote = compare.equalInt32(status, okStatus)
  if wrote done refuse
:done
  return okStatus
:refuse
  return failedStatus

## ---------------------------------------------------------------- small pieces

op byteAt "The byte at an address moved on by an offset"
  invariant readsByte "Gives the byte at the base moved on by the offset"
  input base machine.Address copied
  input at Int64 copied
  output Byte
  effect use machine.memory
  uses memoryAccess
:begin
  findPlace: place = machine.offset(base, at)
  readByte: value = machine.loadByte(place)
  return value

op setErrno "Set errno, the cell __errno_location gives"
  invariant setsErrno "errno then holds the value"
  input value Int32 copied
  effect use machine.memory
  uses memoryAccess
:begin
  cell = errnoCell()
  storeIt: machine.storeInt32(cell, value)
  return

op errnoCell "The running thread's errno (D-166): machine.state's cell for the first thread (and wherever no C program started threads; on Windows for every thread, D-168), and 0x40 of its thread block for a thread threads.h started on Linux"
  invariant firstThreadsCell "The first thread's errno is machine.state's cell"
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  firstCell = kernel.stateAt(2352)
  first = machine.loadAddress(firstCell)
  nowhere = machine.zero()
  when first == nowhere shared ownCheck
:ownCheck
  pointer = machine.threadPointer()
  when pointer == first shared own
:own
  calc ownCell = pointer + 64
  return ownCell
:shared
  cell = kernel.stateAt(errnoAt)
  return cell

op lowInt32 "The low 32 bits of a whole number as an Int32, as C converts a long to an int"
  invariant wrapsLow "Keeps the low 32 bits as a signed int"
  input value Int64 copied
  output Int32
:begin
  lowBits: low = bits.andInt64(value, lowMask=4294967295)
  highCheck: high = compare.greaterThanInt64(low, intMax=2147483647)
  if high wrap keep
:wrap
  wrapIt: wrapped = math.subtractInt64(low, span=4294967296)
  narrowWrapped: wrappedValue = convert.int64ToInt32(wrapped)
  return wrappedValue
:keep
  narrowKept: keptValue = convert.int64ToInt32(low)
  return keptValue

op charOf "The unsigned char an int converts to: its low 8 bits"
  invariant keepsLowByte "Gives the int's low 8 bits"
  input code Int32 copied
  output Byte
:begin
  widenCode: wideCode = convert.int32ToInt64(code)
  lowBits: low = bits.andInt64(wideCode, byteMask=255)
  narrowIt: value = convert.int64ToByte(low)
  return value

op byteDifference "The difference of two bytes as unsigned chars, as an int"
  input left Byte copied
  input right Byte copied
  output Int32
:begin
  widenLeft: leftWide = convert.byteToInt64(left)
  widenRight: rightWide = convert.byteToInt64(right)
  subtractIt: difference = math.subtractInt64(leftWide, rightWide)
  narrowIt: result = convert.int64ToInt32(difference)
  return result

op lowerByte "A byte with A to Z made a to z"
  input value Byte copied
  output Byte
:begin
  lowCheck: aboveA = compare.greaterOrEqualByte(value, capitalA=65)
  highCheck: belowZ = compare.lessOrEqualByte(value, capitalZ=90)
  upperCheck: isUpper = logic.and(aboveA, belowZ)
  if isUpper lower keep
:lower
  lowerIt: lowered = math.addByte(value, caseGap=32)
  return lowered
:keep
  return value

op isSpaceByte "Whether a byte is white space in the C locale: space, or 9 to 13"
  invariant spacesLikeC "Space and 9 to 13 are white space, nothing else"
  input value Byte copied
  output Bool
:begin
  spaceCheck: isBlank = compare.equalByte(value, space=32)
  lowCheck: aboveTab = compare.greaterOrEqualByte(value, tab=9)
  highCheck: belowReturn = compare.lessOrEqualByte(value, carriageReturn=13)
  rangeCheck: inRange = logic.and(aboveTab, belowReturn)
  eitherCheck: white = logic.or(isBlank, inRange)
  return white

op isDigitByte "Whether a byte is a decimal digit"
  input value Byte copied
  output Bool
:begin
  lowCheck: aboveZero = compare.greaterOrEqualByte(value, digitZero=48)
  highCheck: belowNine = compare.lessOrEqualByte(value, digitNine=57)
  bothCheck: digit = logic.and(aboveZero, belowNine)
  return digit

op digitOf "The value of a digit in bases up to 36 (0 to 9, then a or A for 10 to z or Z for 35), or 99 for any other byte"
  invariant readsDigits "0 to 9 then letters of either case give 0 to 35, other bytes 99"
  input value Byte copied
  output UInt64
  let notDigit UInt64 99
:begin
  digitCheck: digit = isDigitByte(value)
  if digit decimal letter
:decimal
  decimalOf: decimalByte = math.subtractByte(value, digitZero=48)
  widenDecimal: decimalValue = convert.byteToUInt64(decimalByte)
  return decimalValue
:letter
  lowerIt: lowered = lowerByte(value)
  lowCheck: aboveA = compare.greaterOrEqualByte(lowered, smallA=97)
  highCheck: belowZ = compare.lessOrEqualByte(lowered, smallZ=122)
  bothCheck: isLetter = logic.and(aboveA, belowZ)
  if isLetter letterValue refuse
:letterValue
  letterOf: letterByte = math.subtractByte(lowered, letterBase=87)
  widenLetter: letterDigit = convert.byteToUInt64(letterByte)
  return letterDigit
:refuse
  return notDigit

op inSet "Whether a byte other than 0 is one of the bytes of a C string"
  input set machine.Address copied
  input value Byte copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let yes Bool true
  let no Bool false
:begin
  goto eachByte
:eachByte loop=while max=forever
  readIt: member = byteAt(set, at)
  endCheck: ended = compare.equalByte(member, nul=0)
  if ended absent compareIt
:compareIt in=eachByte
  sameCheck: same = compare.equalByte(member, value)
  if same present advance
:advance in=eachByte
  stepIt: next = math.addInt64(at, one=1)
  set at next
  goto eachByte
:present
  return yes
:absent
  return no

## ---------------------------------------------------------------- the table (D-153)

op cLibraryName "Whether a library name means the C library, which ffi.open binds to this module: `c` on every system, and on Linux the files the C library and its parts are (libc.so.6, libm.so.6, libpthread.so.0, libdl.so.2, librt.so.1, and `m`)"
  invariant namesC "c names the C library everywhere, libc.so.6 and its parts on Linux only, and other names never"
  input name machine.Address copied
  input bytes Int64 copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let yes Bool true
  let no Bool false
  let cText String "c"
  let mText String "m"
  let libcText String "libc.so.6"
  let libmText String "libm.so.6"
  let pthreadText String "libpthread.so.0"
  let dlText String "libdl.so.2"
  let rtText String "librt.so.1"
:begin
  checkC: isC = sameText(name, bytes, cText)
  if isC named linuxCheck
:linuxCheck
  osCheck: onLinux = system.linux()
  if onLinux checkM notNamed
:checkM
  matchM: isM = sameText(name, bytes, mText)
  if isM named checkLibc
:checkLibc
  matchLibc: isLibc = sameText(name, bytes, libcText)
  if isLibc named checkLibm
:checkLibm
  matchLibm: isLibm = sameText(name, bytes, libmText)
  if isLibm named checkPthread
:checkPthread
  matchPthread: isPthread = sameText(name, bytes, pthreadText)
  if isPthread named checkDl
:checkDl
  matchDl: isDl = sameText(name, bytes, dlText)
  if isDl named checkRt
:checkRt
  matchRt: isRt = sameText(name, bytes, rtText)
  if isRt named notNamed
:named
  return yes
:notNamed
  return no

op sameText "Whether a range of bytes is exactly a text"
  input name machine.Address copied
  input bytes Int64 copied
  input text String borrowed
  output Bool
  effect use machine.memory
  uses memoryAccess
  let no Bool false
:begin
  textLength: length = string.byteLength(text)
  lengthCheck: sameLength = compare.equalInt64(length, bytes)
  if sameLength compareIt differ
:compareIt
  findText: textAt = machine.addressOfString(text)
  compareBytes: order = machine.compare(name, textAt, bytes)
  sameCheck: same = compare.equalInt32(order, zero32=0)
  return same
:differ
  return no

op lookup "The address of a function or variable of the C library by its name, or the address 0 when it has absent: the compiler's table of `abi library` operations, then the data symbols stdin, stdout, stderr, and __stack_chk_guard"
  invariant findsByName "Finds strlen, abs, and toupper, stdout holding the address of its FILE block, and nothing for a name the library does not have"
  input name machine.Address copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let stdinText String "stdin"
  let stdoutText String "stdout"
  let stderrText String "stderr"
  let guardText String "__stack_chk_guard"
:begin
  prepare()
  findTable: table = machine.cLibrary()
  readCount: count = machine.loadInt64(table)
  goto eachRow
:eachRow loop=while max=count
  doneCheck: done = compare.greaterOrEqualInt64(at, count)
  if done data readRow
:readRow in=eachRow
  rowBytes: offset = math.multiplyInt64(at, rowSize=24)
  pastCount: rowOffset = math.addInt64(offset, eight=8)
  findRow: row = machine.offset(table, rowOffset)
  readName: rowName = machine.loadAddress(row)
  findLength: lengthAt = machine.offset(row, eight)
  readLength: rowLength = machine.loadInt64(lengthAt)
  lengthCheck: sameLength = compare.equalInt64(rowLength, bytes)
  if sameLength compareRow advance
:compareRow in=eachRow
  compareIt: order = machine.compare(rowName, name, bytes)
  sameCheck: same = compare.equalInt32(order, zero32=0)
  if same found advance
:advance in=eachRow
  stepIt: next = math.addInt64(at, one=1)
  set at next
  goto eachRow
:found
  findFunction: functionAt = machine.offset(row, sixteen=16)
  readFunction: function = machine.loadAddress(functionAt)
  return function
:data
  isStdin = sameText(name, bytes, stdinText)
  if isStdin giveStdin stdoutData
:giveStdin
  stdinCell = kernel.stateAt(stdinAt)
  return stdinCell
:stdoutData
  stdoutCheck: isStdout = sameText(name, bytes, stdoutText)
  if isStdout giveStdout stderrCheck
:giveStdout
  findStdout: stdoutCell = kernel.stateAt(stdoutAt)
  return stdoutCell
:stderrCheck
  matchStderr: isStderr = sameText(name, bytes, stderrText)
  if isStderr giveStderr guardCheck
:giveStderr
  findStderr: stderrCell = kernel.stateAt(stderrAt)
  return stderrCell
:guardCheck
  matchGuard: isGuard = sameText(name, bytes, guardText)
  if isGuard giveGuard absent
:giveGuard
  findGuard: guardCell = kernel.stateAt(guardAt)
  return guardCell
:absent
  nowhere: anywhere = machine.zero()
  return anywhere

op prepare "Set the data symbols' values: stdin, stdout, and stderr hold the addresses of their FILE blocks in machine.state, which the stdio module fills in when a stream is first used (D-160)"
  invariant pointsAtStreams "stdin, stdout, and stderr hold their FILE blocks' addresses"
  effect use machine.memory
  uses memoryAccess
:begin
  stdinCell = kernel.stateAt(stdinAt)
  stdinFile = kernel.stateAt(1920)
  machine.storeAddress(stdinCell, stdinFile)
  stdoutCell = kernel.stateAt(stdoutAt)
  stdoutFile = kernel.stateAt(2048)
  machine.storeAddress(stdoutCell, stdoutFile)
  stderrCell = kernel.stateAt(stderrAt)
  stderrFile = kernel.stateAt(2176)
  machine.storeAddress(stderrCell, stderrFile)
  return

## ---------------------------------------------------------------- ctype.h

op classBits "glibc's class bits of a character in the C locale (its table's word for the code): upper 256, lower 512, alpha 1024, digit 2048, xdigit 4096, space 8192, print 16384, graph 32768, blank 1, cntrl 2, punct 4, alnum 8; 0 outside 0 to 127"
  invariant classifiesLikeGlibc "Every code from -128 to 255 has the bits glibc's C locale gives it"
  input code Int32 copied
  output Int32
  let noClass Int32 0
  let control Int32 2
  let punctuation Int32 49156
  let tabBits Int32 8195
  let whiteBits Int32 8194
  let spaceBits Int32 24577
  let digitBits Int32 55304
  let upperHexBits Int32 54536
  let upperBits Int32 50440
  let lowerHexBits Int32 54792
  let lowerBits Int32 50696
:begin
  negativeCheck: negative = compare.lessThanInt32(code, zero32=0)
  if negative giveNoClass tabCheck
:tabCheck
  belowTab: control1 = compare.lessThanInt32(code, tab=9)
  if control1 giveControl isTab
:isTab
  tabSame: tabbed = compare.equalInt32(code, tab)
  if tabbed giveTab spaces
:giveTab
  return tabBits
:spaces
  belowShift: whiteControl = compare.lessOrEqualInt32(code, carriageReturn=13)
  if whiteControl giveWhite controls
:giveWhite
  return whiteBits
:controls
  belowSpace: control2 = compare.lessThanInt32(code, space=32)
  if control2 giveControl spaceCheck
:spaceCheck
  spaceSame: spaced = compare.equalInt32(code, space)
  if spaced giveSpace punctuation1
:giveSpace
  return spaceBits
:punctuation1
  belowDigits: punct1 = compare.lessThanInt32(code, digitZero=48)
  if punct1 givePunctuation digits
:digits
  belowColon: digit = compare.lessThanInt32(code, colon=58)
  if digit giveDigit punctuation2
:giveDigit
  return digitBits
:punctuation2
  belowCapitals: punct2 = compare.lessThanInt32(code, capitalA=65)
  if punct2 givePunctuation upperHex
:upperHex
  belowG: upperHexDigit = compare.lessThanInt32(code, capitalG=71)
  if upperHexDigit giveUpperHex upper
:giveUpperHex
  return upperHexBits
:upper
  belowBracket: upperLetter = compare.lessThanInt32(code, bracket=91)
  if upperLetter giveUpper punctuation3
:giveUpper
  return upperBits
:punctuation3
  belowSmall: punct3 = compare.lessThanInt32(code, smallA=97)
  if punct3 givePunctuation lowerHex
:lowerHex
  belowSmallG: lowerHexDigit = compare.lessThanInt32(code, smallG=103)
  if lowerHexDigit giveLowerHex lower
:giveLowerHex
  return lowerHexBits
:lower
  belowBrace: lowerLetter = compare.lessThanInt32(code, brace=123)
  if lowerLetter giveLower punctuation4
:giveLower
  return lowerBits
:punctuation4
  belowDelete: punct4 = compare.lessThanInt32(code, delete=127)
  if punct4 givePunctuation deleteCheck
:deleteCheck
  deleteSame: deleted = compare.equalInt32(code, delete)
  if deleted giveControl giveNoClass
:givePunctuation
  return punctuation
:giveControl
  return control
:giveNoClass
  return noClass

op upperClass "isupper: glibc's bit for an upper-case letter, A to Z, in the C locale (256), or 0"
  input code Int32 copied
  output Int32
  abi library "isupper"
:begin
  classOf: found = classBits(code)
  maskIt: masked = bits.andInt32(found, upperBit=256)
  return masked

op lowerClass "islower: glibc's bit for a lower-case letter, a to z, in the C locale (512), or 0"
  input code Int32 copied
  output Int32
  abi library "islower"
:begin
  classOf: found = classBits(code)
  maskIt: masked = bits.andInt32(found, lowerBit=512)
  return masked

op alphaClass "isalpha: glibc's bit for a letter in the C locale (1024), or 0"
  input code Int32 copied
  output Int32
  abi library "isalpha"
:begin
  classOf: found = classBits(code)
  maskIt: masked = bits.andInt32(found, alphaBit=1024)
  return masked

op digitClass "isdigit: glibc's bit for a decimal digit in the C locale (2048), or 0"
  input code Int32 copied
  output Int32
  abi library "isdigit"
:begin
  classOf: found = classBits(code)
  maskIt: masked = bits.andInt32(found, digitBit=2048)
  return masked

op hexClass "isxdigit: glibc's bit for a hexadecimal digit in the C locale (4096), or 0"
  input code Int32 copied
  output Int32
  abi library "isxdigit"
:begin
  classOf: found = classBits(code)
  maskIt: masked = bits.andInt32(found, hexBit=4096)
  return masked

op spaceClass "isspace: glibc's bit for white space (space, tab, line feed, vertical tab, form feed, carriage return) in the C locale (8192), or 0"
  input code Int32 copied
  output Int32
  abi library "isspace"
:begin
  classOf: found = classBits(code)
  maskIt: masked = bits.andInt32(found, spaceBit=8192)
  return masked

op printClass "isprint: glibc's bit for a printable character, space included, in the C locale (16384), or 0"
  input code Int32 copied
  output Int32
  abi library "isprint"
:begin
  classOf: found = classBits(code)
  maskIt: masked = bits.andInt32(found, printBit=16384)
  return masked

op graphClass "isgraph: glibc's bit for a printable character other than space in the C locale (32768), or 0"
  input code Int32 copied
  output Int32
  abi library "isgraph"
:begin
  classOf: found = classBits(code)
  maskIt: masked = bits.andInt32(found, graphBit=32768)
  return masked

op blankClass "isblank: glibc's bit for a space or a tab in the C locale (1), or 0"
  input code Int32 copied
  output Int32
  abi library "isblank"
:begin
  classOf: found = classBits(code)
  maskIt: masked = bits.andInt32(found, blankBit=1)
  return masked

op controlClass "iscntrl: glibc's bit for a control character, 0 to 31 and 127, in the C locale (2), or 0"
  input code Int32 copied
  output Int32
  abi library "iscntrl"
:begin
  classOf: found = classBits(code)
  maskIt: masked = bits.andInt32(found, controlBit=2)
  return masked

op punctuationClass "ispunct: glibc's bit for a printable character that is neither a letter, a digit, nor space, in the C locale (4), or 0"
  input code Int32 copied
  output Int32
  abi library "ispunct"
:begin
  classOf: found = classBits(code)
  maskIt: masked = bits.andInt32(found, punctuationBit=4)
  return masked

op alphanumericClass "isalnum: glibc's bit for a letter or a decimal digit in the C locale (8), or 0"
  input code Int32 copied
  output Int32
  abi library "isalnum"
:begin
  classOf: found = classBits(code)
  maskIt: masked = bits.andInt32(found, alphanumericBit=8)
  return masked

op isAscii "isascii: 1 for a code from 0 to 127, else 0"
  input code Int32 copied
  output Int32
  let yes32 Int32 1
  let no32 Int32 0
:begin
  highBits: high = bits.andInt32(code, notAscii=-128)
  asciiCheck: ascii = compare.equalInt32(high, no32)
  if ascii giveYes giveNo
:giveYes
  return yes32
:giveNo
  return no32

op isAsciiC "isascii, as the C library names it: 1 for a code from 0 to 127, else 0"
  input code Int32 copied
  output Int32
  abi library "isascii"
:begin
  checkIt: result = isAscii(code)
  return result

op toAscii "toascii: the low 7 bits of a code"
  input code Int32 copied
  output Int32
  abi library "toascii"
:begin
  maskIt: masked = bits.andInt32(code, asciiMask=127)
  return masked

op toUpper "toupper: a to z made A to Z; a signed char from -128 to -2 its unsigned value (glibc's C-locale table holds 128 to 254 there), and every other code, EOF (-1) among them, as it is"
  invariant upperCases "a to z become A to Z, -128 to -2 become 128 to 254, and every other code from -1 to 255 is unchanged"
  input code Int32 copied
  output Int32
  abi library "toupper"
:begin
  signedCheck: signedChar = isSignedChar(code)
  if signedChar unsigned letterCheck
:unsigned
  unsignedIt: unsignedCode = math.addInt32(code, charSpan=256)
  return unsignedCode
:letterCheck
  lowCheck: aboveA = compare.greaterOrEqualInt32(code, smallA=97)
  highCheck: belowZ = compare.lessOrEqualInt32(code, smallZ=122)
  bothCheck: isLower = logic.and(aboveA, belowZ)
  if isLower raise keep
:raise
  raiseIt: raised = math.subtractInt32(code, caseGap=32)
  return raised
:keep
  return code

op isSignedChar "Whether a code is a negative signed char other than EOF: -128 to -2"
  input code Int32 copied
  output Bool
:begin
  lowCheck: aboveLeast = compare.greaterOrEqualInt32(code, least=-128)
  highCheck: belowEof = compare.lessThanInt32(code, eof=-1)
  bothCheck: signedChar = logic.and(aboveLeast, belowEof)
  return signedChar

op toLower "tolower: A to Z made a to z; a signed char from -128 to -2 its unsigned value, as toupper; every other code as it is"
  invariant lowerCases "A to Z become a to z, -128 to -2 become 128 to 254, and every other code from -1 to 255 is unchanged"
  input code Int32 copied
  output Int32
  abi library "tolower"
:begin
  signedCheck: signedChar = isSignedChar(code)
  if signedChar unsigned letterCheck
:unsigned
  unsignedIt: unsignedCode = math.addInt32(code, charSpan=256)
  return unsignedCode
:letterCheck
  lowCheck: aboveA = compare.greaterOrEqualInt32(code, capitalA=65)
  highCheck: belowZ = compare.lessOrEqualInt32(code, capitalZ=90)
  bothCheck: isUpper = logic.and(aboveA, belowZ)
  if isUpper lower keep
:lower
  lowerIt: lowered = math.addInt32(code, caseGap=32)
  return lowered
:keep
  return code

op tables "ctype's tables as glibc's macros read them, made once: 384 class words (unsigned short) and two tables of 384 ints (toupper's and tolower's), each for the codes -128 to 255, and the three cells that point at each table's code 0"
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let code Int64 -128 mut
  let tableCodes Int64 384
:begin
  findTables: tablesSlot = kernel.stateAt(tablesAt)
  readTables: made = machine.loadAddress(tablesSlot)
  nowhere: anywhere = machine.zero()
  madeCheck: absent = machine.equal(made, anywhere)
  if absent make done
:make
  takeBlock: block = heap.take(tableBytes=3840)
  storeTables: machine.storeAddress(tablesSlot, block)
  goto eachCode
:eachCode loop=while max=tableCodes
  doneCheck: finished = compare.greaterOrEqualInt64(code, codeEnd=256)
  if finished cells fill
:fill in=eachCode
  indexOf: index = math.addInt64(code, codeStart=128)
  narrowCode: code32 = convert.int64ToInt32(code)
  classOf: found = classBits(code32)
  classOffset: classPlace = math.multiplyInt64(index, two=2)
  findClass: classAt = machine.offset(block, classPlace)
  lowClass: classLow = bits.andInt32(found, byteMask=255)
  widenLow: classLowWide = convert.int32ToInt64(classLow)
  lowByte: classByte = convert.int64ToByte(classLowWide)
  storeLow: machine.storeByte(classAt, classByte)
  highClass: classHigh = bits.shiftRightInt32(found, eight=8)
  widenHigh: classHighWide = convert.int32ToInt64(classHigh)
  highByte: highClassByte = convert.int64ToByte(classHighWide)
  findHigh: highAt = machine.offset(classAt, one=1)
  storeHigh: machine.storeByte(highAt, highClassByte)
  upperOf: upperCode = toUpper(code32)
  intOffset: intPlace = math.multiplyInt64(index, four=4)
  upperOffset: upperPlace = math.addInt64(intPlace, upperBase=768)
  findUpper: upperAt = machine.offset(block, upperPlace)
  storeUpper: machine.storeInt32(upperAt, upperCode)
  lowerOf: lowerCode = toLower(code32)
  lowerOffset: lowerPlace = math.addInt64(intPlace, lowerBase=2304)
  findLower: lowerAt = machine.offset(block, lowerPlace)
  storeLower: machine.storeInt32(lowerAt, lowerCode)
  stepIt: next = math.addInt64(code, one)
  set code next
  goto eachCode
:cells
  findClassZero: classZero = machine.offset(block, classZeroAt=256)
  findClassCell: classCell = kernel.stateAt(classCellAt)
  storeClassCell: machine.storeAddress(classCell, classZero)
  findUpperZero: upperZero = machine.offset(block, upperZeroAt=1280)
  findUpperCell: upperCell = kernel.stateAt(upperCellAt)
  storeUpperCell: machine.storeAddress(upperCell, upperZero)
  findLowerZero: lowerZero = machine.offset(block, lowerZeroAt=2816)
  findLowerCell: lowerCell = kernel.stateAt(lowerCellAt)
  storeLowerCell: machine.storeAddress(lowerCell, lowerZero)
  goto done
:done
  return

op classTable "__ctype_b_loc: the address of a cell that points at code 0 of glibc's class table (unsigned short words for -128 to 255)"
  invariant pointsAtClasses "The cell points at a word for each code from -128 to 255 that holds the code's class bits"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__ctype_b_loc"
:begin
  makeTables: tables()
  findCell: cell = kernel.stateAt(classCellAt)
  return cell

op upperTable "__ctype_toupper_loc: the address of a cell that points at code 0 of toupper's table (ints for -128 to 255)"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__ctype_toupper_loc"
:begin
  makeTables: tables()
  findCell: cell = kernel.stateAt(upperCellAt)
  return cell

op lowerTable "__ctype_tolower_loc: the address of a cell that points at code 0 of tolower's table (ints for -128 to 255)"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__ctype_tolower_loc"
:begin
  makeTables: tables()
  findCell: cell = kernel.stateAt(lowerCellAt)
  return cell

## ---------------------------------------------------------------- string.h

op cStringLength "strlen: how many bytes come before the first 0 byte"
  invariant countsToZero "Gives the number of bytes before the first 0 byte"
  input text machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "strlen"
  let at Int64 0 mut
:begin
  goto eachByte
:eachByte loop=while max=forever
  readIt: value = byteAt(text, at)
  endCheck: ended = compare.equalByte(value, nul=0)
  if ended done advance
:advance in=eachByte
  stepIt: next = math.addInt64(at, one=1)
  set at next
  goto eachByte
:done
  return at

op boundedLength "strnlen: how many bytes come before the first 0 byte, at most a limit"
  invariant stopsAtBound "Counts to the 0 byte or the bound, whichever comes first"
  input text machine.Address copied
  input most Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "strnlen"
  let at Int64 0 mut
:begin
  goto eachByte
:eachByte loop=while max=most
  limitCheck: atLimit = compare.greaterOrEqualInt64(at, most)
  if atLimit done readByte
:readByte in=eachByte
  readIt: value = byteAt(text, at)
  endCheck: ended = compare.equalByte(value, nul=0)
  if ended done advance
:advance in=eachByte
  stepIt: next = math.addInt64(at, one=1)
  set at next
  goto eachByte
:done
  return at

op compareStrings "strcmp and strncmp: the difference of the first differing bytes of two C strings as unsigned chars, looking at most at a number of bytes; 0 when they agree that far"
  invariant ordersLikeGlibc "Gives 0 for equal strings, else the first differing bytes' difference, and stops at a 0 byte or the limit"
  input left machine.Address copied
  input right machine.Address copied
  input most Int64 copied
  input folded Bool copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let equal Int32 0
:begin
  goto eachByte
:eachByte loop=while max=most
  limitCheck: atLimit = compare.greaterOrEqualInt64(at, most)
  if atLimit same readBytes
:readBytes in=eachByte
  readLeft: leftRaw = byteAt(left, at)
  readRight: rightRaw = byteAt(right, at)
  if folded fold compareRaw
:fold in=eachByte
  foldLeft: leftFolded = lowerByte(leftRaw)
  foldRight: rightFolded = lowerByte(rightRaw)
  foldedCheck: foldedSame = compare.equalByte(leftFolded, rightFolded)
  if foldedSame endCheck foldedDiffer
:compareRaw in=eachByte
  rawCheck: rawSame = compare.equalByte(leftRaw, rightRaw)
  if rawSame endCheck rawDiffer
:endCheck in=eachByte
  zeroCheck: ended = compare.equalByte(leftRaw, nul=0)
  if ended same advance
:advance in=eachByte
  stepIt: next = math.addInt64(at, one=1)
  set at next
  goto eachByte
:foldedDiffer
  foldedDifference: foldedResult = byteDifference(leftFolded, rightFolded)
  return foldedResult
:rawDiffer
  rawDifference: rawResult = byteDifference(leftRaw, rightRaw)
  return rawResult
:same
  return equal

op stringCompare "strcmp: the difference of the first differing bytes of two C strings, or 0"
  input left machine.Address copied
  input right machine.Address copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "strcmp"
:begin
  compareIt: order = compareStrings(left, right, forever, no=false)
  return order

op stringCompareBounded "strncmp: strcmp of at most a number of bytes"
  input left machine.Address copied
  input right machine.Address copied
  input most Int64 copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "strncmp"
:begin
  compareIt: order = compareStrings(left, right, most, no=false)
  return order

op stringCompareFolded "strcasecmp: strcmp of the strings with A to Z read as a to z"
  input left machine.Address copied
  input right machine.Address copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "strcasecmp"
:begin
  compareIt: order = compareStrings(left, right, forever, yes=true)
  return order

op stringCompareFoldedBounded "strncasecmp: strcasecmp of at most a number of bytes"
  input left machine.Address copied
  input right machine.Address copied
  input most Int64 copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "strncasecmp"
:begin
  compareIt: order = compareStrings(left, right, most, yes=true)
  return order

op memoryCompare "memcmp: the difference of the first differing bytes of two ranges as unsigned chars; 0 when none differs"
  invariant comparesRanges "Gives 0 for equal ranges, else the first differing bytes' difference"
  input left machine.Address copied
  input right machine.Address copied
  input bytes Int64 copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "memcmp"
  let at Int64 0 mut
  let equal Int32 0
:begin
  goto eachByte
:eachByte loop=while max=bytes
  limitCheck: atLimit = compare.greaterOrEqualInt64(at, bytes)
  if atLimit same readBytes
:readBytes in=eachByte
  readLeft: leftByte = byteAt(left, at)
  readRight: rightByte = byteAt(right, at)
  sameCheck: sameByte = compare.equalByte(leftByte, rightByte)
  if sameByte advance differ
:advance in=eachByte
  stepIt: next = math.addInt64(at, one=1)
  set at next
  goto eachByte
:differ
  differenceOf: result = byteDifference(leftByte, rightByte)
  return result
:same
  return equal

op memoryCopy "memcpy: copy a range of bytes to one that does not overlap it; gives the target"
  input target machine.Address copied
  input source machine.Address copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "memcpy"
:begin
  copyIt: copied = memory.copyForward(target, source, bytes)
  return copied

op memoryMove "memmove: copy a range of bytes to one that may overlap it; gives the target"
  input target machine.Address copied
  input source machine.Address copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "memmove"
:begin
  moveIt: moved = memory.moveBytes(target, source, bytes)
  return moved

op memorySet "memset: set every byte of a range to a value's low 8 bits; gives the target"
  input target machine.Address copied
  input value Int32 copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "memset"
:begin
  fillIt: filled = memory.fillBytes(target, value, bytes)
  return filled

op memoryFind "memchr: the address of the first byte of a range that is a value's unsigned char, or the address 0"
  invariant findsByte "Gives the first byte equal to the value's unsigned char, or 0"
  input text machine.Address copied
  input value Int32 copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "memchr"
  let at Int64 0 mut
:begin
  charIt: wanted = charOf(value)
  goto eachByte
:eachByte loop=while max=bytes
  limitCheck: atLimit = compare.greaterOrEqualInt64(at, bytes)
  if atLimit absent readByte
:readByte in=eachByte
  readIt: found = byteAt(text, at)
  sameCheck: same = compare.equalByte(found, wanted)
  if same present advance
:advance in=eachByte
  stepIt: next = math.addInt64(at, one=1)
  set at next
  goto eachByte
:present
  findIt: place = machine.offset(text, at)
  return place
:absent
  nowhere: anywhere = machine.zero()
  return anywhere

op stringFind "strchr and strrchr: the address of the first (or last) byte of a C string that is a value's unsigned char, the 0 byte included, or the address 0"
  invariant findsCharacter "Finds the first or last place of the character, the terminating 0 for 0, or nothing"
  input text machine.Address copied
  input value Int32 copied
  input last Bool copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let found Int64 -1 mut
:begin
  charIt: wanted = charOf(value)
  goto eachByte
:eachByte loop=while max=forever
  readIt: current = byteAt(text, at)
  sameCheck: same = compare.equalByte(current, wanted)
  if same mark endCheck
:mark in=eachByte
  set found at
  if last endCheck give
:endCheck in=eachByte
  zeroCheck: ended = compare.equalByte(current, nul=0)
  if ended give advance
:advance in=eachByte
  stepIt: next = math.addInt64(at, one=1)
  set at next
  goto eachByte
:give
  noneCheck: missing = compare.lessThanInt64(found, zero=0)
  if missing absent present
:present
  findIt: place = machine.offset(text, found)
  return place
:absent
  nowhere: anywhere = machine.zero()
  return anywhere

op stringFirst "strchr: the first place of a character in a C string, or the address 0"
  input text machine.Address copied
  input value Int32 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "strchr"
:begin
  findIt: place = stringFind(text, value, no=false)
  return place

op stringLast "strrchr: the last place of a character in a C string, or the address 0"
  input text machine.Address copied
  input value Int32 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "strrchr"
:begin
  findIt: place = stringFind(text, value, yes=true)
  return place

op stringSearch "strstr: the address of the first place a C string holds another, the text itself for an empty one, or the address 0"
  invariant findsText "Finds the first place the needle starts in the haystack, or nothing"
  input haystack machine.Address copied
  input needle machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "strstr"
  let at Int64 0 mut
:begin
  needleLength: wanted = cStringLength(needle)
  haystackLength: length = cStringLength(haystack)
  emptyCheck: empty = compare.equalInt64(wanted, zero=0)
  if empty whole search
:whole
  return haystack
:search
  lastStart: room = math.subtractInt64(length, wanted)
  goto eachStart
:eachStart loop=while max=length
  limitCheck: past = compare.greaterThanInt64(at, room)
  if past absent compareAt
:compareAt in=eachStart
  findStart: start = machine.offset(haystack, at)
  compareIt: order = machine.compare(start, needle, wanted)
  sameCheck: same = compare.equalInt32(order, zero32=0)
  if same present advance
:advance in=eachStart
  stepIt: next = math.addInt64(at, one=1)
  set at next
  goto eachStart
:present
  return start
:absent
  nowhere: anywhere = machine.zero()
  return anywhere

op spanOf "strspn and strcspn: how many bytes a C string starts with that are (or, with `outside`, are not) in another's bytes"
  invariant spansSet "Counts the first bytes in the set (or not in it), stopping at the 0 byte"
  input text machine.Address copied
  input set machine.Address copied
  input outside Bool copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  goto eachByte
:eachByte loop=while max=forever
  readIt: value = byteAt(text, at)
  endCheck: ended = compare.equalByte(value, nul=0)
  if ended done memberCheck
:memberCheck in=eachByte
  findMember: member = inSet(set, value)
  differentCheck: counted = logic.xor(member, outside)
  if counted advance done
:advance in=eachByte
  stepIt: next = math.addInt64(at, one=1)
  set at next
  goto eachByte
:done
  return at

op stringSpan "strspn: how many bytes a C string starts with that are in another's bytes"
  input text machine.Address copied
  input set machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "strspn"
:begin
  spanIt: counted = spanOf(text, set, no=false)
  return counted

op stringComplementSpan "strcspn: how many bytes a C string starts with that are not in another's bytes"
  input text machine.Address copied
  input set machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "strcspn"
:begin
  spanIt: counted = spanOf(text, set, yes=true)
  return counted

op stringBreak "strpbrk: the address of the first byte of a C string that is in another's bytes, or the address 0"
  input text machine.Address copied
  input set machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "strpbrk"
:begin
  spanIt: counted = spanOf(text, set, yes=true)
  readIt: value = byteAt(text, counted)
  endCheck: ended = compare.equalByte(value, nul=0)
  if ended absent present
:present
  findIt: place = machine.offset(text, counted)
  return place
:absent
  nowhere: anywhere = machine.zero()
  return anywhere

op stringCopy "strcpy: copy a C string with its 0 byte; gives the target"
  input target machine.Address copied
  input source machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "strcpy"
:begin
  measure: length = cStringLength(source)
  withEnd: bytes = math.addInt64(length, one=1)
  copyIt: machine.copy(target, source, bytes)
  return target

op stringCopyBounded "strncpy: copy at most a number of bytes of a C string, then 0 bytes until that many are written; gives the target"
  input target machine.Address copied
  input source machine.Address copied
  input most Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "strncpy"
:begin
  measure: length = boundedLength(source, most)
  copyIt: machine.copy(target, source, length)
  restOf: rest = math.subtractInt64(most, length)
  findRest: restAt = machine.offset(target, length)
  fillIt: machine.fill(restAt, nul=0, rest)
  return target

op stringAppend "strcat: copy a C string with its 0 byte to the end of another; gives the target"
  input target machine.Address copied
  input source machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "strcat"
:begin
  measureTarget: targetLength = cStringLength(target)
  findEnd: end = machine.offset(target, targetLength)
  copyIt: copied = stringCopy(end, source)
  return target

op stringAppendBounded "strncat: copy at most a number of bytes of a C string to the end of another, then a 0 byte; gives the target"
  input target machine.Address copied
  input source machine.Address copied
  input most Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "strncat"
:begin
  measureTarget: targetLength = cStringLength(target)
  findEnd: end = machine.offset(target, targetLength)
  measure: length = boundedLength(source, most)
  copyIt: machine.copy(end, source, length)
  findZero: zeroAt = machine.offset(end, length)
  storeZero: machine.storeByte(zeroAt, nul=0)
  return target

op stringDuplicate "strdup: a copy of a C string in a block malloc gives, or the address 0 with ENOMEM"
  input source machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "strdup"
:begin
  measure: length = cStringLength(source)
  duplicateIt: copy = duplicate(source, length)
  return copy

op stringDuplicateBounded "strndup: a copy of at most a number of bytes of a C string, with a 0 byte after it, in a block malloc gives"
  input source machine.Address copied
  input most Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "strndup"
:begin
  measure: length = boundedLength(source, most)
  duplicateIt: copy = duplicate(source, length)
  return copy

op duplicate "A copy of a number of bytes with a 0 byte after them, in a block malloc gives"
  invariant duplicatesBytes "The block holds the bytes and then a 0"
  input source machine.Address copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  withEnd: size = math.addInt64(bytes, one=1)
  takeIt: block = allocate(size)
  copyIt: machine.copy(block, source, bytes)
  findEnd: end = machine.offset(block, bytes)
  storeEnd: machine.storeByte(end, nul=0)
  return block

## ---------------------------------------------------------------- stdlib.h: numbers

op absolute "abs: the magnitude of an int; the most negative int is itself, as glibc's two's-complement negation gives it"
  invariant wrapsLikeGlibc "Gives the magnitude, and INT_MIN for INT_MIN"
  input value Int32 copied
  output Int32
  abi library "abs"
:begin
  negativeCheck: negative = compare.lessThanInt32(value, zero32=0)
  if negative negate keep
:negate
  negateIt: negated = math.wrappingSubtractInt32(zero32, value)
  return negated
:keep
  return value

op absoluteLong "labs and llabs: the magnitude of a long; the most negative long is itself"
  invariant wrapsLong "Gives the magnitude, and LONG_MIN for LONG_MIN"
  input value Int64 copied
  output Int64
  abi library "labs"
:begin
  negativeCheck: negative = compare.lessThanInt64(value, zero=0)
  if negative negate keep
:negate
  negateIt: negated = math.wrappingSubtractInt64(zero, value)
  return negated
:keep
  return value

op absoluteLongLong "llabs: the magnitude of a long long, which is a long (64 bits)"
  input value Int64 copied
  output Int64
  abi library "llabs"
:begin
  absoluteIt: magnitude = absoluteLong(value)
  return magnitude

op divide "div: an int's quotient (toward zero) and remainder as div_t, which every 64-bit C ABI returns in one register: the quotient in the low 32 bits, the remainder in the high 32"
  invariant packsQuotient "The low 32 bits hold the quotient and the high 32 the remainder"
  input numerator Int32 copied
  input denominator Int32 copied
  output Int64
:begin
  quotientOf: quotient = math.divideInt32(numerator, denominator)
  remainderOf: remainder = math.remainderInt32(numerator, denominator)
  widenQuotient: quotientWide = convert.int32ToInt64(quotient)
  lowOf: low = bits.andInt64(quotientWide, lowMask=4294967295)
  widenRemainder: remainderWide = convert.int32ToInt64(remainder)
  shiftIt: high = bits.shiftLeftInt64(remainderWide, thirtyTwo=32)
  joinIt: packed = bits.orInt64(high, low)
  return packed

op divideC "div, as the C library names it: the quotient and remainder of two ints, packed as div_t returns"
  input numerator Int32 copied
  input denominator Int32 copied
  output Int64
  abi library "div"
:begin
  divideIt: packed = divide(numerator, denominator)
  return packed

op parseWhole "strtol and its kin, as glibc reads them: white space, a sign, `0x` in base 16 or 0 and `0` for base 8 in base 0, then digits below the base; the value's bits, LONG_MIN or LONG_MAX (ULONG_MAX unsigned) with ERANGE past the range, EINVAL for a base that is neither 0 nor 2 to 36; the end of what was read is stored at `endAt` unless it is the address 0"
  invariant readsLikeStrtol "Reads the longest prefix strtol reads, with its value, errno, and end"
  input text machine.Address copied
  input endAt machine.Address copied
  input base Int32 copied
  input unsigned Bool copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let start Int64 0 mut
  let negative Bool false mut
  let overflow Bool false mut
  let radix UInt64 10 mut
  let value UInt64 0 mut
  let yes Bool true
  let noValue Int64 0
  let allOnes UInt64 18446744073709551615
  let mostSigned UInt64 9223372036854775807
  let sixteen UInt64 16
  let eightWide UInt64 8
  let leastSigned UInt64 9223372036854775808
:begin
  lowBase: badLow = compare.lessThanInt32(base, zero32=0)
  oneBase: baseOne = compare.equalInt32(base, one32=1)
  highBase: badHigh = compare.greaterThanInt32(base, base36=36)
  eitherBad: bad1 = logic.or(badLow, baseOne)
  anyBad: bad = logic.or(bad1, badHigh)
  if bad invalid spaces
:invalid
  errnoInvalid: setErrno(invalidError)
  return noValue
:spaces
  goto eachSpace
:eachSpace loop=while max=forever
  readSpace: leading = byteAt(text, at)
  spaceCheck: white = isSpaceByte(leading)
  if white skipSpace sign
:skipSpace in=eachSpace
  stepSpace: afterSpace = math.addInt64(at, one=1)
  set at afterSpace
  goto eachSpace
:sign
  minusCheck: minus = compare.equalByte(leading, minusSign=45)
  if minus takeMinus plusCheck
:takeMinus
  set negative yes
  stepMinus: afterMinus = math.addInt64(at, one)
  set at afterMinus
  goto prefix
:plusCheck
  plusSame: plus = compare.equalByte(leading, plusSign=43)
  if plus takePlus prefix
:takePlus
  stepPlus: afterPlus = math.addInt64(at, one)
  set at afterPlus
  goto prefix
:prefix
  readFirst: first = byteAt(text, at)
  zeroCheck: leadingZero = compare.equalByte(first, digitZero=48)
  if leadingZero zeroPrefix plainBase
:zeroPrefix
  nextOf: secondAt = math.addInt64(at, one)
  readSecond: second = byteAt(text, secondAt)
  lowerSecond: secondLower = lowerByte(second)
  xCheck: isX = compare.equalByte(secondLower, smallX=120)
  baseZero: autoBase = compare.equalInt32(base, zero32)
  baseSixteen: hexBase = compare.equalInt32(base, base16=16)
  hexAllowed: allowsX = logic.or(autoBase, hexBase)
  hexPrefix: takesX = logic.and(isX, allowsX)
  if takesX skipX octalCheck
:skipX
  stepX: afterX = math.addInt64(at, two=2)
  set at afterX
  set radix sixteen
  goto digits
:octalCheck
  if autoBase octal plainBase
:octal
  set radix eightWide
  goto digits
:plainBase
  zeroBase: givenZero = compare.equalInt32(base, zero32)
  if givenZero digits givenBase
:givenBase
  widenBase: baseWide = convert.int32ToInt64(base)
  unsignedBase: baseBits = convert.int64BitsToUInt64(baseWide)
  set radix baseBits
  goto digits
:digits
  set start at
  cutoffOf: cutoff = math.divideUInt64(allOnes, radix)
  cutlimOf: cutlim = math.remainderUInt64(allOnes, radix)
  goto eachDigit
:eachDigit loop=while max=forever
  readDigit: character = byteAt(text, at)
  digitOfIt: digit = digitOf(character)
  belowRadix: isDigit = compare.lessThanUInt64(digit, radix)
  if isDigit consider finish
:consider in=eachDigit
  if overflow advance limitCheck
:limitCheck in=eachDigit
  overCutoff: over = compare.greaterThanUInt64(value, cutoff)
  if over overflowed atCutoff
:atCutoff in=eachDigit
  sameCutoff: atLimit = compare.equalUInt64(value, cutoff)
  pastLimit: pastCut = compare.greaterThanUInt64(digit, cutlim)
  bothOver: overAtLimit = logic.and(atLimit, pastCut)
  if overAtLimit overflowed accumulate
:overflowed in=eachDigit
  set overflow yes
  goto advance
:accumulate in=eachDigit
  shiftUp: shifted = math.multiplyUInt64(value, radix)
  addOn: added = math.addUInt64(shifted, digit)
  set value added
  goto advance
:advance in=eachDigit
  stepDigit: afterDigit = math.addInt64(at, one)
  set at afterDigit
  goto eachDigit
:finish
  noneRead: empty = compare.equalInt64(at, start)
  if empty noConversion storeEnd
:noConversion
  nowhere: anywhere = machine.zero()
  noEndCheck: noEnd = machine.equal(endAt, anywhere)
  if noEnd giveNone xEnd
:xEnd
  farEnough: twoBefore = compare.greaterOrEqualInt64(start, two)
  if twoBefore xBefore textEnd
:xBefore
  beforeOf: beforeAt = math.subtractInt64(start, one)
  readBefore: before = byteAt(text, beforeAt)
  lowerBefore: beforeLower = lowerByte(before)
  xBeforeCheck: wasX = compare.equalByte(beforeLower, smallX)
  zeroBeforeOf: zeroBeforeAt = math.subtractInt64(start, two)
  readZeroBefore: zeroBefore = byteAt(text, zeroBeforeAt)
  zeroBeforeCheck: wasZero = compare.equalByte(zeroBefore, digitZero)
  bothBefore: wasPrefix = logic.and(wasX, wasZero)
  if wasPrefix endAtX textEnd
:endAtX
  findX: xPlace = machine.offset(text, beforeAt)
  storeX: machine.storeAddress(endAt, xPlace)
  return noValue
:textEnd
  storeText: machine.storeAddress(endAt, text)
  goto giveNone
:giveNone
  return noValue
:storeEnd
  nowhereEnd: noAddress = machine.zero()
  endCheck: noEndAddress = machine.equal(endAt, noAddress)
  if noEndAddress result storeIt
:storeIt
  findEnd: endPlace = machine.offset(text, at)
  storeEndPlace: machine.storeAddress(endAt, endPlace)
  goto result
:result
  if unsigned unsignedResult signedResult
:unsignedResult
  if overflow unsignedRange unsignedValue
:unsignedRange
  errnoUnsigned: setErrno(rangeError)
  allBits: allOnesValue = convert.uint64BitsToInt64(allOnes)
  return allOnesValue
:unsignedValue
  if negative negateUnsigned plainUnsigned
:negateUnsigned
  negateIt: negatedBits = math.wrappingSubtractUInt64(zeroWide=0, value)
  negatedValue: negatedResult = convert.uint64BitsToInt64(negatedBits)
  return negatedResult
:plainUnsigned
  plainValue: plainResult = convert.uint64BitsToInt64(value)
  return plainResult
:signedResult
  if overflow signedRange signedLimit
:signedLimit
  if negative negativeLimit positiveLimit
:negativeLimit
  belowLeast: tooNegative = compare.greaterThanUInt64(value, leastSigned)
  if tooNegative signedRange negateSigned
:positiveLimit
  aboveMost: tooPositive = compare.greaterThanUInt64(value, mostSigned)
  if tooPositive signedRange plainSigned
:negateSigned
  negateSignedIt: negatedSignedBits = math.wrappingSubtractUInt64(zeroWide, value)
  negatedSignedValue: negatedSigned = convert.uint64BitsToInt64(negatedSignedBits)
  return negatedSigned
:plainSigned
  plainSignedValue: plainSignedResult = convert.uint64BitsToInt64(value)
  return plainSignedResult
:signedRange
  errnoSigned: setErrno(rangeError)
  if negative giveLeast giveMost
:giveLeast
  leastValue: leastResult = convert.uint64BitsToInt64(leastSigned)
  return leastResult
:giveMost
  mostValue: mostResult = convert.uint64BitsToInt64(mostSigned)
  return mostResult

op toLong "strtol: a C string's leading whole number as a long, in a base"
  input text machine.Address copied
  input endAt machine.Address copied
  input base Int32 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "strtol"
:begin
  parseIt: value = parseWhole(text, endAt, base, no=false)
  return value

op toLongLong "strtoll: a C string's leading whole number as a long long, in a base"
  input text machine.Address copied
  input endAt machine.Address copied
  input base Int32 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "strtoll"
:begin
  parseIt: value = parseWhole(text, endAt, base, no=false)
  return value

op toUnsignedLong "strtoul: a C string's leading whole number as an unsigned long, in a base"
  input text machine.Address copied
  input endAt machine.Address copied
  input base Int32 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "strtoul"
:begin
  parseIt: value = parseWhole(text, endAt, base, yes=true)
  return value

op toUnsignedLongLong "strtoull: a C string's leading whole number as an unsigned long long, in a base"
  input text machine.Address copied
  input endAt machine.Address copied
  input base Int32 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "strtoull"
:begin
  parseIt: value = parseWhole(text, endAt, base, yes=true)
  return value

op toInt "atoi: strtol in base 10, its low 32 bits"
  input text machine.Address copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "atoi"
:begin
  nowhere: anywhere = machine.zero()
  parseIt: value = parseWhole(text, anywhere, ten32=10, no=false)
  narrowIt: narrowed = lowInt32(value)
  return narrowed

op toLongDecimal "atol: strtol in base 10"
  input text machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "atol"
:begin
  nowhere: anywhere = machine.zero()
  parseIt: value = parseWhole(text, anywhere, ten32=10, no=false)
  return value

op toLongLongDecimal "atoll: strtoll in base 10"
  input text machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "atoll"
:begin
  nowhere: anywhere = machine.zero()
  parseIt: value = parseWhole(text, anywhere, ten32=10, no=false)
  return value

op matchesFolded "Whether the bytes at an offset of a C string are a lower-case word, read with A to Z as a to z"
  input text machine.Address copied
  input at Int64 copied
  input word String borrowed
  output Bool
  effect use machine.memory
  uses memoryAccess
  let index Int64 0 mut
  let yes Bool true
  let no Bool false
:begin
  wordLength: length = string.byteLength(word)
  findWord: wordAt = machine.addressOfString(word)
  goto eachByte
:eachByte loop=while max=length
  doneCheck: done = compare.greaterOrEqualInt64(index, length)
  if done matched compareIt
:compareIt in=eachByte
  placeOf: place = math.addInt64(at, index)
  readText: textByte = byteAt(text, place)
  lowerText: textLower = lowerByte(textByte)
  readWord: wordByte = byteAt(wordAt, index)
  sameCheck: same = compare.equalByte(textLower, wordByte)
  if same advance differ
:advance in=eachByte
  stepIt: next = math.addInt64(index, one=1)
  set index next
  goto eachByte
:matched
  return yes
:differ
  return no

op scanDigits "Where the run of decimal digits that starts at an offset of a C string ends"
  input text machine.Address copied
  input start Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  set at start
  goto eachByte
:eachByte loop=while max=forever
  readIt: value = byteAt(text, at)
  digitCheck: digit = isDigitByte(value)
  if digit advance done
:advance in=eachByte
  stepIt: next = math.addInt64(at, one=1)
  set at next
  goto eachByte
:done
  return at

op parseReal "strtod, as glibc reads text in the C locale: white space, a sign, then inf or infinity, nan or nan(chars), a hexadecimal number (0x, digits with a point, p and a power of two), or a decimal one (digits with a point, e and a power of ten), each read correctly rounded; HUGE_VAL with ERANGE past the largest double, ERANGE for a decimal number that reads as a subnormal or as 0 (and a hexadecimal one that does so inexactly); the end of what was read is stored at `endAt` unless it is the address 0, the text itself when nothing was"
  invariant readsLikeStrtod "Reads the longest prefix strtod reads, with its value and end"
  input text machine.Address copied
  input endAt machine.Address copied
  output Float64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let negative Bool false mut
  let resultBits UInt64 0 mut
  let fractionStart Int64 0 mut
  let fractionEnd Int64 0 mut
  let exponentStart Int64 0 mut
  let exponentEnd Int64 0 mut
  let length Int64 0 mut
  let yes Bool true
  let infText String "inf"
  let finityText String "inity"
  let nanText String "nan"
  let zeroText String "0"
  let pointText String "."
  let exponentText String "e"
  let zeroWide UInt64 0
:begin
  goto eachSpace
:eachSpace loop=while max=forever
  readSpace: leading = byteAt(text, at)
  spaceCheck: white = isSpaceByte(leading)
  if white skipSpace sign
:skipSpace in=eachSpace
  stepSpace: afterSpace = math.addInt64(at, one=1)
  set at afterSpace
  goto eachSpace
:sign
  minusCheck: minus = compare.equalByte(leading, minusSign=45)
  if minus takeMinus plusCheck
:takeMinus
  set negative yes
  stepMinus: afterMinus = math.addInt64(at, one)
  set at afterMinus
  goto words
:plusCheck
  plusSame: plus = compare.equalByte(leading, plusSign=43)
  if plus takePlus words
:takePlus
  stepPlus: afterPlus = math.addInt64(at, one)
  set at afterPlus
  goto words
:words
  infCheck: isInf = matchesFolded(text, at, infText)
  if isInf infinity nanCheck
:infinity
  afterInfOf: afterInf = math.addInt64(at, three=3)
  set at afterInf
  set resultBits infinityBits
  longCheck: isLong = matchesFolded(text, afterInf, finityText)
  if isLong longInfinity signed
:longInfinity
  afterLongOf: afterLong = math.addInt64(afterInf, five=5)
  set at afterLong
  goto signed
:nanCheck
  matchNan: isNan = matchesFolded(text, at, nanText)
  if isNan notANumber hexCheck
:notANumber
  afterNanOf: afterNan = math.addInt64(at, three)
  set at afterNan
  set resultBits nanBits
  readOpen: open = byteAt(text, afterNan)
  openCheck: opens = compare.equalByte(open, openParenthesis=40)
  if opens payload signed
:payload
  firstOf: firstPayload = math.addInt64(afterNan, one)
  scanPayload: payloadEnd = scanPayloadChars(text, firstPayload)
  readClose: close = byteAt(text, payloadEnd)
  closeCheck: closes = compare.equalByte(close, closeParenthesis=41)
  if closes takePayload signed
:takePayload
  afterPayloadOf: afterPayload = math.addInt64(payloadEnd, one)
  set at afterPayload
  goto signed
:hexCheck
  readFirst: first = byteAt(text, at)
  zeroCheck: leadingZero = compare.equalByte(first, digitZero=48)
  if leadingZero xCheck decimal
:xCheck
  secondOf: secondAt = math.addInt64(at, one)
  readSecond: second = byteAt(text, secondAt)
  lowerSecond: secondLower = lowerByte(second)
  xSame: isX = compare.equalByte(secondLower, smallX=120)
  if isX hexadecimal decimal
:hexadecimal
  hexStart: digitsAt = math.addInt64(at, two=2)
  readHex: hexEnd = parseHexReal(text, digitsAt)
  hexFound: hexRead = compare.greaterOrEqualInt64(hexEnd, zero=0)
  if hexRead hexValue hexNone
:hexValue
  set at hexEnd
  findHexBits: hexCell = kernel.stateAt(hexBitsAt)
  readHexBits: hexBits = machine.loadUInt64(hexCell)
  set resultBits hexBits
  goto signed
:hexNone
  set at secondAt
  set resultBits zeroWide
  goto signed
:decimal
  integerStart: integerFrom = math.addInt64(at, zero)
  scanInteger: integerEnd = scanDigits(text, integerFrom)
  set fractionStart integerEnd
  set fractionEnd integerEnd
  readPoint: point = byteAt(text, integerEnd)
  pointCheck: hasPoint = compare.equalByte(point, dot=46)
  if hasPoint fraction counted
:fraction
  fractionFrom: afterPoint = math.addInt64(integerEnd, one)
  set fractionStart afterPoint
  scanFraction: fractionTo = scanDigits(text, afterPoint)
  set fractionEnd fractionTo
  goto counted
:counted
  integerDigits: integerCount = math.subtractInt64(integerEnd, integerFrom)
  fractionDigits: fractionCount = math.subtractInt64(fractionEnd, fractionStart)
  allDigits: digitCount = math.addInt64(integerCount, fractionCount)
  noneCheck: noDigits = compare.equalInt64(digitCount, zero)
  if noDigits noConversion afterNumber
:noConversion
  nowhereNone: noAddress = machine.zero()
  noEndCheck: noEnd = machine.equal(endAt, noAddress)
  zeroBits: zeroResult = convert.uint64BitsToFloat64(zeroWide)
  if noEnd giveZero storeText
:storeText
  storeTextEnd: machine.storeAddress(endAt, text)
  goto giveZero
:giveZero
  return zeroResult
:afterNumber
  set at fractionEnd
  set exponentStart fractionEnd
  set exponentEnd fractionEnd
  readE: letterE = byteAt(text, fractionEnd)
  lowerE: letterLower = lowerByte(letterE)
  eCheck: isE = compare.equalByte(letterLower, smallE=101)
  if isE exponentSign build
:exponentSign
  signOf: signAt = math.addInt64(fractionEnd, one)
  readSign: signByte = byteAt(text, signAt)
  minusExponent: exponentMinus = compare.equalByte(signByte, minusSign)
  plusExponent: exponentPlus = compare.equalByte(signByte, plusSign)
  eitherSign: hasSign = logic.or(exponentMinus, exponentPlus)
  if hasSign signedExponent exponentDigits
:signedExponent
  afterSignOf: afterSign = math.addInt64(signAt, one)
  scanSigned: signedEnd = scanDigits(text, afterSign)
  signedSome: signedHas = compare.greaterThanInt64(signedEnd, afterSign)
  if signedHas takeExponent build
:exponentDigits
  scanPlain: plainEnd = scanDigits(text, signAt)
  plainSome: plainHas = compare.greaterThanInt64(plainEnd, signAt)
  if plainHas takePlain build
:takePlain
  set exponentStart signAt
  set exponentEnd plainEnd
  set at plainEnd
  goto build
:takeExponent
  set exponentStart signAt
  set exponentEnd signedEnd
  set at signedEnd
  goto build
:build
  exponentBytes: exponentCount = math.subtractInt64(exponentEnd, exponentStart)
  roomFor: room1 = math.addInt64(digitCount, exponentCount)
  roomAll: room = math.addInt64(room1, eight=8)
  makeBuilder: builder = wide.builderNew()
  integerSome: hasInteger = compare.greaterThanInt64(integerCount, zero)
  if hasInteger addInteger addZero
:addInteger
  findInteger: integerAt = machine.offset(text, integerFrom)
  addIntegerIt: wide.builderAdd(builder, integerAt, integerCount)
  goto addFraction
:addZero
  findZero: zeroAt = machine.addressOfString(zeroText)
  addZeroIt: wide.builderAdd(builder, zeroAt, one)
  goto addFraction
:addFraction
  fractionSome: hasFraction = compare.greaterThanInt64(fractionCount, zero)
  if hasFraction addPoint addExponent
:addPoint
  findPointText: pointAt = machine.addressOfString(pointText)
  addPointIt: wide.builderAdd(builder, pointAt, one)
  findFraction: fractionAt = machine.offset(text, fractionStart)
  addFractionIt: wide.builderAdd(builder, fractionAt, fractionCount)
  goto addExponent
:addExponent
  exponentSome: hasExponent = compare.greaterThanInt64(exponentCount, zero)
  if hasExponent addE convert
:addE
  findEText: eAt = machine.addressOfString(exponentText)
  addEIt: wide.builderAdd(builder, eAt, one)
  findExponent: exponentAt = machine.offset(text, exponentStart)
  addExponentIt: wide.builderAdd(builder, exponentAt, exponentCount)
  goto convert
:convert
  builtText: built = wide.builderText(builder)
  builtLength: builtBytes = wide.builderLength(builder)
  findReal: realCell = kernel.stateAt(realAt)
  parseIt: status = floats.parseFloat(built, builtBytes, realCell)
  giveBuiltText: heap.give(built)
  giveBuilt: heap.give(builder)
  readReal: real = machine.loadFloat64(realCell)
  realBits: parsedBits = convert.float64BitsToUInt64(real)
  set resultBits parsedBits
  tooLarge: overflowed = compare.equalInt32(status, two32=2)
  if overflowed huge underflowCheck
:huge
  errnoHuge: setErrno(rangeError)
  set resultBits infinityBits
  goto signed
:underflowCheck
  zeroValue: isZero = compare.equalUInt64(parsedBits, zeroWide)
  if isZero nonzeroCheck subnormalCheck
:subnormalCheck
  exponentOf: exponentField = bits.andUInt64(parsedBits, exponentBitsMask=9218868437227405312)
  subnormalSame: isSubnormal = compare.equalUInt64(exponentField, zeroWide)
  if isSubnormal tiny signed
:nonzeroCheck
  findSignificant: significant = anyNonzero(text, integerFrom, fractionEnd)
  if significant tiny signed
:tiny
  errnoTiny: setErrno(rangeError)
  goto signed
:signed
  if negative flip storeEnd
:flip
  flipIt: flipped = bits.xorUInt64(resultBits, signBit)
  set resultBits flipped
  goto storeEnd
:storeEnd
  nowhere: anywhere = machine.zero()
  endCheck: noEndAddress = machine.equal(endAt, anywhere)
  if noEndAddress give storeIt
:storeIt
  findEnd: endPlace = machine.offset(text, at)
  storeEndPlace: machine.storeAddress(endAt, endPlace)
  goto give
:give
  asFloat: result = convert.uint64BitsToFloat64(resultBits)
  return result

op anyNonzero "Whether a range of a C string holds a digit from 1 to 9"
  input text machine.Address copied
  input start Int64 copied
  input end Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let yes Bool true
  let no Bool false
:begin
  set at start
  goto eachByte
:eachByte loop=while max=forever
  doneCheck: done = compare.greaterOrEqualInt64(at, end)
  if done absent readIt
:readIt in=eachByte
  readByte: value = byteAt(text, at)
  lowCheck: aboveZero = compare.greaterThanByte(value, digitZero=48)
  highCheck: belowNine = compare.lessOrEqualByte(value, digitNine=57)
  bothCheck: significant = logic.and(aboveZero, belowNine)
  if significant present advance
:advance in=eachByte
  stepIt: next = math.addInt64(at, one=1)
  set at next
  goto eachByte
:present
  return yes
:absent
  return no

op scanPayloadChars "Where the run of letters, digits, and `_` that starts at an offset of a C string ends (a NaN's payload)"
  input text machine.Address copied
  input start Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let notDigit UInt64 99
:begin
  set at start
  goto eachByte
:eachByte loop=while max=forever
  readIt: value = byteAt(text, at)
  digitOfIt: digit = digitOf(value)
  alnumCheck: alnum = compare.lessThanUInt64(digit, notDigit)
  underscoreCheck: underscore = compare.equalByte(value, underscoreByte=95)
  eitherCheck: payloadByte = logic.or(alnum, underscore)
  if payloadByte advance done
:advance in=eachByte
  stepIt: next = math.addInt64(at, one=1)
  set at next
  goto eachByte
:done
  return at

op parseHexReal "The hexadecimal part of strtod after `0x`: hex digits with a point, then p, a sign, and decimal digits; the bits of the nearest double (ties to even, subnormals included, infinity past the largest with ERANGE, zero with ERANGE when a nonzero value rounds to it) go to machine.state, and the end of what was read is given, or -1 when there is no hex digit"
  invariant readsHexadecimal "Reads 0x1p0 as 1, 0x1.8 as 1.5, 0x1p-1074 as the smallest subnormal, and rounds ties to even"
  input text machine.Address copied
  input start Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let mantissa UInt64 0 mut
  let sticky Bool false mut
  let exponent Int64 0 mut
  let digits Int64 0 mut
  let power Int64 0 mut
  let powerNegative Bool false mut
  let high Int64 0 mut
  let kept UInt64 0 mut
  let biased Int64 0 mut
  let yes Bool true
  let notFound Int64 -1
  let full UInt64 1152921504606846976
  let hidden UInt64 4503599627370496
  let carry UInt64 9007199254740992
:begin
  set at start
  goto eachInteger
:eachInteger loop=while max=forever
  readInteger: integerByte = byteAt(text, at)
  integerDigitOf: integerDigit = digitOf(integerByte)
  integerHex: isIntegerDigit = compare.lessThanUInt64(integerDigit, sixteen=16)
  if isIntegerDigit takeInteger point
:takeInteger in=eachInteger
  countInteger: integerCount = math.addInt64(digits, one=1)
  set digits integerCount
  roomCheck: roomy = compare.lessThanUInt64(mantissa, full)
  if roomy shiftInteger dropInteger
:shiftInteger in=eachInteger
  integerShift: integerShifted = math.multiplyUInt64(mantissa, sixteen)
  integerAdd: integerAdded = math.addUInt64(integerShifted, integerDigit)
  set mantissa integerAdded
  goto nextInteger
:dropInteger in=eachInteger
  integerExponent: integerUp = math.addInt64(exponent, four=4)
  set exponent integerUp
  integerZero: integerNonzero = compare.notEqualUInt64(integerDigit, zeroWide=0)
  if integerNonzero integerSticky nextInteger
:integerSticky in=eachInteger
  set sticky yes
  goto nextInteger
:nextInteger in=eachInteger
  stepInteger: afterInteger = math.addInt64(at, one)
  set at afterInteger
  goto eachInteger
:point
  pointCheck: hasPoint = compare.equalByte(integerByte, dot=46)
  if hasPoint fraction counted
:fraction
  pointSkip: afterPoint = math.addInt64(at, one)
  set at afterPoint
  goto eachFraction
:eachFraction loop=while max=forever
  readFraction: fractionByte = byteAt(text, at)
  fractionDigitOf: fractionDigit = digitOf(fractionByte)
  fractionHex: isFractionDigit = compare.lessThanUInt64(fractionDigit, sixteen)
  if isFractionDigit takeFraction counted
:takeFraction in=eachFraction
  countFraction: fractionCount = math.addInt64(digits, one)
  set digits fractionCount
  fractionRoom: fractionRoomy = compare.lessThanUInt64(mantissa, full)
  if fractionRoomy shiftFraction dropFraction
:shiftFraction in=eachFraction
  fractionShift: fractionShifted = math.multiplyUInt64(mantissa, sixteen)
  fractionAdd: fractionAdded = math.addUInt64(fractionShifted, fractionDigit)
  set mantissa fractionAdded
  fractionExponent: fractionDown = math.subtractInt64(exponent, four)
  set exponent fractionDown
  goto nextFraction
:dropFraction in=eachFraction
  fractionZero: fractionNonzero = compare.notEqualUInt64(fractionDigit, zeroWide)
  if fractionNonzero fractionSticky nextFraction
:fractionSticky in=eachFraction
  set sticky yes
  goto nextFraction
:nextFraction in=eachFraction
  stepFraction: afterFraction = math.addInt64(at, one)
  set at afterFraction
  goto eachFraction
:counted
  noneCheck: noDigits = compare.equalInt64(digits, zero=0)
  if noDigits refuse powerCheck
:refuse
  return notFound
:powerCheck
  readP: letterP = byteAt(text, at)
  lowerP: letterLower = lowerByte(letterP)
  pCheck: isP = compare.equalByte(letterLower, smallP=112)
  if isP powerSign scale
:powerSign
  signOf: signAt = math.addInt64(at, one)
  readSign: signByte = byteAt(text, signAt)
  minusPower: minus = compare.equalByte(signByte, minusSign=45)
  plusPower: plus = compare.equalByte(signByte, plusSign=43)
  eitherSign: hasSign = logic.or(minus, plus)
  powerFromOf: powerFrom = math.addInt64(signAt, zero)
  if hasSign afterSign powerDigits
:afterSign
  set powerNegative minus
  skipSign: afterSignAt = math.addInt64(signAt, one)
  set power afterSignAt
  goto powerScan
:powerDigits
  set power powerFrom
  goto powerScan
:powerScan
  scanPower: powerEnd = scanDigits(text, power)
  someCheck: hasPowerDigits = compare.greaterThanInt64(powerEnd, power)
  if hasPowerDigits readPower scale
:readPower
  valueOf: powerValue = smallDecimal(text, power, powerEnd)
  set at powerEnd
  if powerNegative lowerPower raisePower
:lowerPower
  powerDown: exponentDown = math.subtractInt64(exponent, powerValue)
  set exponent exponentDown
  goto scale
:raisePower
  powerUp: exponentUp = math.addInt64(exponent, powerValue)
  set exponent exponentUp
  goto scale
:scale
  findCell: cell = kernel.stateAt(hexBitsAt)
  zeroCheck: isZero = compare.equalUInt64(mantissa, zeroWide)
  if isZero giveZero normalize
:giveZero
  storeZero: machine.storeUInt64(cell, zeroWide)
  return at
:normalize
  highestOf: highest = highBit(mantissa)
  set high highest
  topOf: top = math.addInt64(highest, exponent)
  hugeCheck: tooLarge = compare.greaterThanInt64(top, maxExponent=1023)
  if tooLarge overflow dropCount
:overflow
  errnoHuge: setErrno(rangeError)
  storeHuge: machine.storeUInt64(cell, infinityBits)
  return at
:dropCount
  normalCheck: normal = compare.greaterOrEqualInt64(top, minExponent=-1022)
  normalDrop: dropNormal = math.subtractInt64(highest, fiftyTwo=52)
  belowMin: underBy = math.subtractInt64(minExponent, top)
  subnormalDrop: dropSubnormal = math.addInt64(dropNormal, underBy)
  if normal useNormal useSubnormal
:useNormal
  roundIt: rounded = roundMantissa(mantissa, dropNormal, sticky)
  set kept rounded
  carryCheck: carried = compare.equalUInt64(rounded, carry)
  if carried renormalize normalBits
:renormalize
  set kept hidden
  carryTop: carriedTop = math.addInt64(top, one)
  carryHuge: carriedHuge = compare.greaterThanInt64(carriedTop, maxExponent)
  if carriedHuge overflow carriedBits
:carriedBits
  biasCarried: carriedBiased = math.addInt64(carriedTop, bias=1023)
  set biased carriedBiased
  goto assemble
:normalBits
  biasTop: topBiased = math.addInt64(top, bias)
  set biased topBiased
  goto assemble
:assemble
  biasedBits: biasedWide = convert.int64BitsToUInt64(biased)
  exponentField: field = bits.shiftLeftUInt64(biasedWide, fiftyTwo)
  fractionField: fractionBits = math.subtractUInt64(kept, hidden)
  joinFields: assembled = bits.orUInt64(field, fractionBits)
  storeNormal: machine.storeUInt64(cell, assembled)
  return at
:useSubnormal
  roundSubnormal: subnormal = roundMantissa(mantissa, dropSubnormal, sticky)
  storeSubnormal: machine.storeUInt64(cell, subnormal)
  inexactCheck: inexact = isInexact(mantissa, dropSubnormal, sticky)
  if inexact tiny done
:tiny
  errnoTiny: setErrno(rangeError)
  goto done
:done
  return at

op smallDecimal "The value of a run of decimal digits, at most 1000000 (a larger power reads as that much, which is past any double)"
  input text machine.Address copied
  input start Int64 copied
  input end Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let value Int64 0 mut
  let most Int64 1000000
:begin
  set at start
  goto eachDigit
:eachDigit loop=while max=forever
  doneCheck: done = compare.greaterOrEqualInt64(at, end)
  if done finish readIt
:readIt in=eachDigit
  readByte: character = byteAt(text, at)
  digitOfIt: digitByte = math.subtractByte(character, digitZero=48)
  widenDigit: digit = convert.byteToInt64(digitByte)
  smallCheck: small = compare.lessThanInt64(value, most)
  if small accumulate advance
:accumulate in=eachDigit
  shiftUp: shifted = math.multiplyInt64(value, ten=10)
  addOn: added = math.addInt64(shifted, digit)
  set value added
  goto advance
:advance in=eachDigit
  stepIt: next = math.addInt64(at, one=1)
  set at next
  goto eachDigit
:finish
  return value

op highBit "The place of the highest bit set in a nonzero number, 0 to 63"
  input value UInt64 copied
  output Int64
  let place Int64 63 mut
  let sixtyFour Int64 64
:begin
  goto eachPlace
:eachPlace loop=while max=sixtyFour
  shiftIt: shifted = bits.shiftRightUInt64(value, place)
  setCheck: isSet = compare.notEqualUInt64(shifted, zeroWide=0)
  if isSet done lower
:lower in=eachPlace
  lowestCheck: lowest = compare.lessOrEqualInt64(place, zero=0)
  if lowest done stepDown
:stepDown in=eachPlace
  stepIt: next = math.subtractInt64(place, one=1)
  set place next
  goto eachPlace
:done
  return place

op roundMantissa "A number shifted right by a count of bits and rounded to the nearest, ties to even, with `sticky` standing for nonzero bits already dropped; a count of 0 or less shifts left, exactly"
  invariant roundsToEven "Rounds halfway to even, above halfway up, and below it down"
  input value UInt64 copied
  input drop Int64 copied
  input sticky Bool copied
  output UInt64
  let noBits UInt64 0
:begin
  exactCheck: exact = compare.lessOrEqualInt64(drop, zero=0)
  if exact shiftUp farCheck
:shiftUp
  amountOf: amount = math.negateInt64(drop)
  shiftLeftIt: shifted = bits.shiftLeftUInt64(value, amount)
  return shifted
:farCheck
  farOff: far = compare.greaterThanInt64(drop, sixtyFour=64)
  if far giveNone splitCheck
:giveNone
  return noBits
:splitCheck
  wholeDrop: dropAll = compare.equalInt64(drop, sixtyFour)
  if dropAll splitAll split
:splitAll
  allRest: restAll = math.addUInt64(value, noBits)
  halfAll: halfOfAll = bits.shiftLeftUInt64(oneWide=1, sixtyThree=63)
  roundAll: roundedAll = decideRound(noBits, restAll, halfOfAll, sticky)
  return roundedAll
:split
  keepIt: kept = bits.shiftRightUInt64(value, drop)
  maskOf: unit = bits.shiftLeftUInt64(oneWide, drop)
  maskBits: mask = math.subtractUInt64(unit, oneWide)
  restOf: rest = bits.andUInt64(value, mask)
  halfShift: halfAt = math.subtractInt64(drop, one=1)
  halfOf: half = bits.shiftLeftUInt64(oneWide, halfAt)
  roundIt: rounded = decideRound(kept, rest, half, sticky)
  return rounded

op decideRound "A kept number, one more when what was dropped is above half, or exactly half (with no sticky bits) and the kept number is odd"
  input kept UInt64 copied
  input rest UInt64 copied
  input half UInt64 copied
  input sticky Bool copied
  output UInt64
:begin
  aboveCheck: above = compare.greaterThanUInt64(rest, half)
  if above roundUp halfCheck
:halfCheck
  halfSame: atHalf = compare.equalUInt64(rest, half)
  if atHalf tieCheck keep
:tieCheck
  if sticky roundUp evenCheck
:evenCheck
  lowBit: odd = bits.andUInt64(kept, oneWide=1)
  oddCheck: isOdd = compare.equalUInt64(odd, oneWide)
  if isOdd roundUp keep
:roundUp
  addOne: bumped = math.addUInt64(kept, oneWide)
  return bumped
:keep
  return kept

op isInexact "Whether shifting a number right by a count of bits drops a nonzero bit, or `sticky` says one was dropped already"
  input value UInt64 copied
  input drop Int64 copied
  input sticky Bool copied
  output Bool
  let no Bool false
  let yes Bool true
:begin
  if sticky inexact countCheck
:countCheck
  exactCheck: exact = compare.lessOrEqualInt64(drop, zero=0)
  if exact giveExact farCheck
:farCheck
  farOff: far = compare.greaterOrEqualInt64(drop, sixtyFour=64)
  if far inexact maskIt
:maskIt
  unitOf: unit = bits.shiftLeftUInt64(oneWide=1, drop)
  maskOf: mask = math.subtractUInt64(unit, oneWide)
  restOf: rest = bits.andUInt64(value, mask)
  restCheck: nonzero = compare.notEqualUInt64(rest, zeroWide=0)
  return nonzero
:inexact
  return yes
:giveExact
  return no

op toDouble "strtod: a C string's leading number as a double, with where it ends"
  input text machine.Address copied
  input endAt machine.Address copied
  output Float64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "strtod"
:begin
  parseIt: value = parseReal(text, endAt)
  return value

op toDoubleDecimal "atof: strtod with no end"
  input text machine.Address copied
  output Float64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "atof"
:begin
  nowhere: anywhere = machine.zero()
  parseIt: value = parseReal(text, anywhere)
  return value

## ---------------------------------------------------------------- stdlib.h: memory

op allocate "malloc: a zeroed block of at least the bytes asked (one for 0), aligned for any value, from the runtime's heap; the address 0 with ENOMEM past PTRDIFF_MAX"
  invariant allocatesBlocks "Gives a writable block for a size, and the address 0 with ENOMEM for a size past PTRDIFF_MAX"
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "malloc"
:begin
  negativeCheck: tooLarge = compare.lessThanInt64(bytes, zero=0)
  if tooLarge refuse take
:refuse
  errnoMemory: setErrno(memoryError)
  nowhere: anywhere = machine.zero()
  return anywhere
:take
  takeIt: block = heap.take(bytes)
  return block

op allocateZeroed "calloc: a zeroed block for a count of items of a size; the address 0 with ENOMEM when the bytes pass PTRDIFF_MAX"
  input count Int64 copied
  input size Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "calloc"
:begin
  countCheck: countBad = compare.lessThanInt64(count, zero=0)
  sizeCheck: sizeBad = compare.lessThanInt64(size, zero)
  eitherBad: bad = logic.or(countBad, sizeBad)
  if bad refuse sizeZero
:sizeZero
  noSize: empty = compare.equalInt64(size, zero)
  if empty take overflowCheck
:overflowCheck
  mostOf: most = math.divideInt64(largest, size)
  overCheck: over = compare.greaterThanInt64(count, most)
  if over refuse take
:refuse
  errnoMemory: setErrno(memoryError)
  nowhere: anywhere = machine.zero()
  return anywhere
:take
  bytesOf: bytes = math.wrappingMultiplyInt64(count, size)
  takeIt: block = allocate(bytes)
  return block

op reallocate "realloc: a block grown or shrunk, its bytes kept; the address 0 gives a new block, and 0 bytes frees the block and gives the address 0"
  input block machine.Address copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "realloc"
:begin
  nowhere: anywhere = machine.zero()
  freshCheck: fresh = machine.equal(block, anywhere)
  if fresh takeNew zeroCheck
:takeNew
  takeIt: made = allocate(bytes)
  return made
:zeroCheck
  emptyCheck: empty = compare.equalInt64(bytes, zero=0)
  if empty freeIt sizeCheck
:freeIt
  giveIt: heap.give(block)
  return anywhere
:sizeCheck
  negativeCheck: tooLarge = compare.lessThanInt64(bytes, zero)
  if tooLarge refuse resize
:refuse
  errnoMemory: setErrno(memoryError)
  return anywhere
:resize
  resizeIt: resized = heap.resize(block, bytes)
  return resized

op release "free: give a block malloc gave back; the address 0 is nothing"
  input block machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "free"
:begin
  giveIt: heap.give(block)
  return

op errnoLocation "__errno_location: the address of errno, which strtol, strtod, and malloc set"
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "__errno_location"
:begin
  cell = errnoCell()
  return cell

op errorText "strerror: the text for an error number, in a block of machine.state the next call replaces; for now every number is `Unknown error N` (D-160: glibc's messages are a known gap)"
  invariant namesErrors "Gives `Unknown error N` with N the number in decimal, negative ones with their sign"
  input code Int32 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "strerror"
  let prefix String "Unknown error "
  let place Int64 31 mut
  let rest Int64 0 mut
:begin
  buffer = kernel.stateAt(errorTextAt)
  prefixAt = machine.addressOfString(prefix)
  machine.copy(buffer, prefixAt, 14)
  calc wideCode = convert.int32ToInt64(code)
  calc negative = wideCode < 0
  calc rest := absoluteWide(wideCode)
  digits = kernel.stateAt(errorDigitsAt)
  goto eachDigit
:eachDigit loop=while max=forever
  calc place := place - 1
  calc digit = convert.int64ToByte(rest % 10) + 48
  calc digitAt = digits + place
  machine.storeByte(digitAt, digit)
  calc rest := rest / 10
  when rest == 0 sign eachDigit
:sign
  if negative minus copyDigits
:minus
  calc place := place - 1
  calc minusAt = digits + place
  machine.storeByte(minusAt, 45)
  goto copyDigits
:copyDigits
  calc fromAt = digits + place
  calc count = 31 - place
  calc toAt = buffer + 14
  machine.copy(toAt, fromAt, count)
  calc endAt = buffer + 14 + count
  machine.storeByte(endAt, 0)
  return buffer

op absoluteWide "The magnitude of an Int64 that came from an Int32 (so it never overflows)"
  input value Int64 copied
  output Int64
:begin
  when value < 0 flip keep
:flip
  calc flipped = 0 - value
  return flipped
:keep
  return value

op errorMessage "The text strerror gives for errno now"
  invariant describesErrno "Gives strerror of errno"
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  cell = errnoCell()
  code = machine.loadInt32(cell)
  text = errorText(code)
  return text

op sortItems "qsort: sort a count of items of a size with a comparison, stably (glibc's merge sort keeps equal items in their order): runs of 1, 2, 4, and so on merged through a block of the same size"
  invariant sortsStably "Sorts by the comparison and keeps equal items in the order they were"
  input base machine.Address copied
  input count Int64 copied
  input size Int64 copied
  input comparison machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "qsort"
  let width Int64 1 mut
  let start Int64 0 mut
  let zero Int64 0
  let sixtyFour Int64 64
:begin
  fewCheck: few = compare.lessOrEqualInt64(count, one=1)
  if few done setUp
:setUp
  totalOf: total = math.multiplyInt64(count, size)
  takeSpare: spare = heap.take(total)
  goto eachWidth
:eachWidth loop=while max=sixtyFour
  widthCheck: sorted = compare.greaterOrEqualInt64(width, count)
  if sorted finish startRuns
:startRuns in=eachWidth
  set start zero
  goto eachPair
:eachPair loop=while max=count in=eachWidth
  pairCheck: pairsDone = compare.greaterOrEqualInt64(start, count)
  if pairsDone nextWidth mergePair
:mergePair in=eachPair
  middleOf: middle = lesserOf(start, width, count)
  doubleOf: span = math.multiplyInt64(width, two=2)
  endOf: end = lesserOf(start, span, count)
  mergeIt: mergeRuns(base, size, start, middle, end, spare, comparison)
  set start end
  goto eachPair
:nextWidth in=eachWidth
  doubleWidth: wider = math.multiplyInt64(width, two)
  set width wider
  goto eachWidth
:finish
  giveSpare: heap.give(spare)
  goto done
:done
  return

op lesserOf "A start moved on by a step, or a limit when that is less"
  input start Int64 copied
  input step Int64 copied
  input limit Int64 copied
  output Int64
:begin
  roomOf: room = math.subtractInt64(limit, start)
  fitCheck: fits = compare.lessThanInt64(step, room)
  if fits moved limited
:moved
  addIt: sum = math.addInt64(start, step)
  return sum
:limited
  return limit

op mergeRuns "Merge two sorted runs of items, from `start` to `middle` and from `middle` to `end`, through a spare block: an item of the left run goes first unless the comparison puts the right one before it"
  input base machine.Address copied
  input size Int64 copied
  input start Int64 copied
  input middle Int64 copied
  input end Int64 copied
  input spare machine.Address copied
  input comparison machine.Address copied
  effect use machine.memory
  uses memoryAccess
  let left Int64 0 mut
  let right Int64 0 mut
  let out Int64 0 mut
:begin
  set left start
  set right middle
  set out start
  countOf: items = math.subtractInt64(end, start)
  goto eachItem
:eachItem loop=while max=items
  outCheck: filled = compare.greaterOrEqualInt64(out, end)
  if filled copyBack choose
:choose in=eachItem
  leftCheck: leftDone = compare.greaterOrEqualInt64(left, middle)
  if leftDone takeRight rightCheck
:rightCheck in=eachItem
  rightDoneCheck: rightDone = compare.greaterOrEqualInt64(right, end)
  if rightDone takeLeft compareThem
:compareThem in=eachItem
  leftOffset: leftBytes = math.multiplyInt64(left, size)
  findLeft: leftAt = machine.offset(base, leftBytes)
  rightOffset: rightBytes = math.multiplyInt64(right, size)
  findRight: rightAt = machine.offset(base, rightBytes)
  compareIt: order = machine.callComparison(comparison, leftAt, rightAt)
  afterCheck: rightFirst = compare.greaterThanInt32(order, zero32=0)
  if rightFirst takeRight takeLeft
:takeLeft in=eachItem
  fromLeft: leftFrom = math.multiplyInt64(left, size)
  findFromLeft: leftSource = machine.offset(base, leftFrom)
  toLeft: leftTo = math.multiplyInt64(out, size)
  findToLeft: leftTarget = machine.offset(spare, leftTo)
  copyLeft: machine.copy(leftTarget, leftSource, size)
  stepLeft: nextLeft = math.addInt64(left, one=1)
  set left nextLeft
  goto advance
:takeRight in=eachItem
  fromRight: rightFrom = math.multiplyInt64(right, size)
  findFromRight: rightSource = machine.offset(base, rightFrom)
  toRight: rightTo = math.multiplyInt64(out, size)
  findToRight: rightTarget = machine.offset(spare, rightTo)
  copyRight: machine.copy(rightTarget, rightSource, size)
  stepRight: nextRight = math.addInt64(right, one)
  set right nextRight
  goto advance
:advance in=eachItem
  stepOut: nextOut = math.addInt64(out, one)
  set out nextOut
  goto eachItem
:copyBack
  startBytes: from = math.multiplyInt64(start, size)
  findSpare: spareAt = machine.offset(spare, from)
  findBase: baseAt = machine.offset(base, from)
  allBytes: bytes = math.multiplyInt64(items, size)
  copyAll: machine.copy(baseAt, spareAt, bytes)
  return

op searchItems "bsearch: glibc's binary search of a sorted array for an item the comparison finds equal to a key, halving [low, high) from the middle; the item's address, or the address 0"
  invariant searchesLikeGlibc "Finds an item equal to the key by glibc's halving, or nothing"
  input key machine.Address copied
  input base machine.Address copied
  input count Int64 copied
  input size Int64 copied
  input comparison machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "bsearch"
  let low Int64 0 mut
  let high Int64 0 mut
  let sixtyFour Int64 64
:begin
  set high count
  goto eachStep
:eachStep loop=while max=sixtyFour
  emptyCheck: empty = compare.greaterOrEqualInt64(low, high)
  if empty absent probe
:probe in=eachStep
  sumOf: sum = math.addInt64(low, high)
  middleOf: middle = math.divideInt64(sum, two=2)
  offsetOf: offset = math.multiplyInt64(middle, size)
  findItem: item = machine.offset(base, offset)
  compareIt: order = machine.callComparison(comparison, key, item)
  belowCheck: below = compare.lessThanInt32(order, zero32=0)
  if below lower aboveCheck
:lower in=eachStep
  set high middle
  goto eachStep
:aboveCheck in=eachStep
  aboveSame: above = compare.greaterThanInt32(order, zero32)
  if above raise found
:raise in=eachStep
  stepUp: next = math.addInt64(middle, one=1)
  set low next
  goto eachStep
:found
  return item
:absent
  nowhere: anywhere = machine.zero()
  return anywhere

## ---------------------------------------------------------------- stdlib.h: the process and the environment

op environmentValue "getenv: the address of a variable's value as a C string, or the address 0 when it is not set: on Linux the value in the environment the process started with, on Windows a copy as UTF-8 that the next getenv may replace (as C allows)"
  invariant readsEnvironment "Finds a variable the environment has and nothing for one it does not"
  input name machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "getenv"
  let at Int64 0 mut
:begin
  measure: bytes = cStringLength(name)
  nowhere: anywhere = machine.zero()
  emptyCheck: emptyName = compare.equalInt64(bytes, zero=0)
  if emptyName absent systemCheck
:systemCheck
  osCheck: onLinux = system.linux()
  if onLinux linuxLookUp windowsLookUp
:linuxLookUp
  readVector: vector = kernel.environmentVector()
  noVector: missingVector = machine.equal(vector, anywhere)
  if missingVector absent eachEntry
:eachEntry loop=while max=forever
  entryOffset: offset = math.multiplyInt64(at, eight=8)
  findEntry: entryAt = machine.offset(vector, offset)
  readEntry: entry = machine.loadAddress(entryAt)
  endCheck: ended = machine.equal(entry, anywhere)
  if ended absent compareName
:compareName in=eachEntry
  compareIt: order = compareStrings(entry, name, bytes, no=false)
  sameCheck: same = compare.equalInt32(order, zero32=0)
  if same equalsCheck advance
:equalsCheck in=eachEntry
  readEquals: equalsByte = byteAt(entry, bytes)
  isEquals: named = compare.equalByte(equalsByte, equalsSign=61)
  if named present advance
:advance in=eachEntry
  stepIt: next = math.addInt64(at, one=1)
  set at next
  goto eachEntry
:present
  valueOffset: valueAt = math.addInt64(bytes, one)
  findValue: value = machine.offset(entry, valueAt)
  return value
:absent
  return anywhere
:windowsLookUp
  wideName: nameWide = wide.widen(name, bytes)
  measureValue: units32 = system.getEnvironmentVariableW(nameWide, anywhere, none32=0)
  unitsOf: units = convert.int32ToInt64(units32)
  missingCheck: missing = compare.equalInt64(units, zero=0)
  if missing giveMissing read
:giveMissing
  giveNameMissing: heap.give(nameWide)
  return anywhere
:read
  sizeOf: size = math.multiplyInt64(units, two=2)
  takeBuffer: buffer = heap.take(size)
  readIt: read32 = system.getEnvironmentVariableW(nameWide, buffer, units32)
  readUnits: readWide = convert.int32ToInt64(read32)
  takeLength: lengthCell = heap.take(eight)
  narrowIt: narrowed = wide.narrow(buffer, readWide, lengthCell)
  giveLength: heap.give(lengthCell)
  giveBuffer: heap.give(buffer)
  giveName: heap.give(nameWide)
  findLast: lastCell = kernel.stateAt(environmentAt)
  readLast: last = machine.loadAddress(lastCell)
  giveLast: heap.give(last)
  storeLast: machine.storeAddress(lastCell, narrowed)
  return narrowed

op exitNow "_exit: end the process with a status at once"
  input code Int32 copied
  effect use system.calls
  uses systemCalls
  abi library "_exit"
:begin
  endIt: endProcess(code)
  return

op abortProcess "abort: on Linux SIGABRT with its default action, so the process ends by the signal as glibc's does; on Windows exit code 3, as the C runtime's abort ends it"
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  osCheck: onLinux = system.linux()
  if onLinux linuxAbort windowsAbort
:linuxAbort
  takeAction: action = heap.take(thirtyTwo=32)
  nowhere: anywhere = machine.zero()
  resetIt: reset = system.rtSigaction(abortSignal=6, action, anywhere, maskBytes=8)
  findSelf: self = system.getpid()
  killIt: killed = system.kill(self, abortSignal)
  endLinux: endProcess(abortCode=134)
  return
:windowsAbort
  endWindows: endProcess(windowsCode=3)
  return

op stackSmashed "__stack_chk_fail: a library's stack protector found its canary changed; write glibc's message to standard error and abort"
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__stack_chk_fail"
  let message String "*** stack smashing detected ***: terminated\n"
:begin
  findMessage: messageAt = machine.addressOfString(message)
  messageLength: bytes = string.byteLength(message)
  writeIt: status = writeStream(two=2, messageAt, bytes)
  abortIt: abortProcess()
  return

op finalize "__cxa_finalize: what a library's destructors register is never run (the process ends without running them, as at _exit); nothing to do"
  input handle machine.Address copied
  abi library "__cxa_finalize"
:begin
  return

op registerAtExit "__cxa_atexit: a function exit calls with an argument, after those registered later (atexit's own list, as glibc keeps one); 0"
  input function machine.Address copied
  input argument machine.Address copied
  input handle machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__cxa_atexit"
:begin
  result = registerHandler(exitListAt, function, argument)
  return result

## ---------------------------------------------------------------- math.h

op floatAbsolute "fabs: the value with its sign bit cleared"
  invariant clearsSign "Gives the magnitude, -0.0 as 0.0 and a NaN as a NaN"
  input value Float64 copied
  output Float64
  abi library "fabs"
:begin
  toBits: valueBits = convert.float64BitsToUInt64(value)
  clearIt: cleared = bits.andUInt64(valueBits, magnitudeMask=9223372036854775807)
  fromBits: result = convert.uint64BitsToFloat64(cleared)
  return result

op copySign "copysign: the magnitude of one value with the sign bit of another"
  input magnitude Float64 copied
  input sign Float64 copied
  output Float64
  abi library "copysign"
:begin
  magnitudeOf: magnitudeBits = convert.float64BitsToUInt64(magnitude)
  clearIt: cleared = bits.andUInt64(magnitudeBits, magnitudeMask=9223372036854775807)
  signOf: signBits = convert.float64BitsToUInt64(sign)
  keepSign: signOnly = bits.andUInt64(signBits, signBit)
  joinIt: joined = bits.orUInt64(cleared, signOnly)
  fromBits: result = convert.uint64BitsToFloat64(joined)
  return result

op squareRoot "sqrt: the correctly rounded square root (one instruction, llvm.sqrt); NaN below zero, -0.0 for -0.0"
  invariant rootsExactly "Gives the correctly rounded root"
  input value Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "sqrt"
:begin
  rootIt: root = machine.squareRoot(value)
  return root

op isWhole "Whether a double is a NaN, an infinity, or so large (2^52 or more) that it has no fraction"
  input value Float64 copied
  output Bool
:begin
  toBits: valueBits = convert.float64BitsToUInt64(value)
  exponentOf: shifted = bits.shiftRightUInt64(valueBits, fiftyTwo=52)
  exponentBits: exponent = bits.andUInt64(shifted, exponentMask=2047)
  largeCheck: large = compare.greaterOrEqualUInt64(exponent, wholeExponent=1075)
  return large

op truncate "trunc: the value with its fraction dropped, toward zero, keeping its sign (-0.5 is -0.0)"
  invariant dropsFraction "Gives the whole part with the value's sign; NaN, infinities, and whole numbers as they are"
  input value Float64 copied
  output Float64
  abi library "trunc"
:begin
  wholeCheck: whole = isWhole(value)
  if whole keep cut
:keep
  return value
:cut
  toWhole: integer = convert.float64ToInt64(value)
  backToFloat: truncated = convert.int64ToFloat64(integer)
  signIt: signed = copySign(truncated, value)
  return signed

op floorOf "floor: the greatest whole number not above the value"
  invariant roundsDown "Gives the whole number at or below the value, -0.0 for -0.0 and -1.0 for -0.5"
  input value Float64 copied
  output Float64
  abi library "floor"
  let oneFloat Float64 1.0
:begin
  truncateIt: truncated = truncate(value)
  aboveCheck: above = compare.greaterThanFloat64(truncated, value)
  if above down keep
:down
  lowerIt: lowered = math.subtractFloat64(truncated, oneFloat)
  return lowered
:keep
  return truncated

op ceilingOf "ceil: the least whole number not below the value"
  invariant roundsUp "Gives the whole number at or above the value, -0.0 for -0.5"
  input value Float64 copied
  output Float64
  abi library "ceil"
  let oneFloat Float64 1.0
:begin
  truncateIt: truncated = truncate(value)
  belowCheck: below = compare.lessThanFloat64(truncated, value)
  if below up keep
:up
  raiseIt: raised = math.addFloat64(truncated, oneFloat)
  return raised
:keep
  return truncated

op roundOf "round: the nearest whole number, halfway cases away from zero"
  invariant roundsHalfAway "Rounds 0.5 to 1.0, -2.5 to -3.0, and 0.49999999999999994 to 0.0"
  input value Float64 copied
  output Float64
  abi library "round"
  let oneFloat Float64 1.0
  let half Float64 0.5
:begin
  truncateIt: truncated = truncate(value)
  fractionOf: fraction = math.subtractFloat64(value, truncated)
  magnitudeOf: magnitude = floatAbsolute(fraction)
  halfCheck: away = compare.greaterOrEqualFloat64(magnitude, half)
  if away step keep
:step
  unitOf: unit = copySign(oneFloat, value)
  addIt: stepped = math.addFloat64(truncated, unit)
  return stepped
:keep
  return truncated

op floatRemainder "fmod: the remainder of x divided by y with the sign of x, exactly (musl's integer algorithm); NaN for y 0 or x infinite"
  invariant remaindersExactly "Gives x - n*y for the whole n toward zero, exactly"
  input x Float64 copied
  input y Float64 copied
  output Float64
  let xBits UInt64 0 mut
  let yBits UInt64 0 mut
  let xExponent Int64 0 mut
  let yExponent Int64 0 mut
  let probe UInt64 0 mut
  let hidden UInt64 4503599627370496
  let mantissaMask UInt64 4503599627370495
  let zeroFloat Float64 0.0
  let sixtyFour Int64 64
:begin
  readX: xRaw = convert.float64BitsToUInt64(x)
  readY: yRaw = convert.float64BitsToUInt64(y)
  set xBits xRaw
  set yBits yRaw
  xShift: xField = bits.shiftRightUInt64(xRaw, fiftyTwo=52)
  xMask: xExponentBits = bits.andUInt64(xField, exponentMask=2047)
  xWide: xExponentWide = convert.uint64BitsToInt64(xExponentBits)
  set xExponent xExponentWide
  yShift: yField = bits.shiftRightUInt64(yRaw, fiftyTwo)
  yMask: yExponentBits = bits.andUInt64(yField, exponentMask)
  yWide: yExponentWide = convert.uint64BitsToInt64(yExponentBits)
  set yExponent yExponentWide
  xSignOf: xSign = bits.andUInt64(xRaw, signBit)
  yDouble: yTwice = bits.shiftLeftUInt64(yRaw, oneShift=1)
  yZero: yIsZero = compare.equalUInt64(yTwice, zeroWide=0)
  yMagnitude: yAbsolute = bits.andUInt64(yRaw, magnitudeMask=9223372036854775807)
  yNan: yIsNan = compare.greaterThanUInt64(yAbsolute, infinityBits)
  xInfinite: xNotFinite = compare.equalInt64(xExponent, topExponent=2047)
  firstBad: bad1 = logic.or(yIsZero, yIsNan)
  allBad: bad = logic.or(bad1, xNotFinite)
  if bad nan magnitudes
:nan
  productOf: product = math.multiplyFloat64(x, y)
  quotientOf: nanResult = math.divideFloat64(product, product)
  return nanResult
:magnitudes
  xDouble: xTwice = bits.shiftLeftUInt64(xRaw, oneShift)
  notAbove: smaller = compare.lessOrEqualUInt64(xTwice, yTwice)
  if smaller smallX normalizeX
:smallX
  sameCheck: same = compare.equalUInt64(xTwice, yTwice)
  if same signedZero giveX
:giveX
  return x
:signedZero
  zeroOf: zeroResult = math.multiplyFloat64(zeroFloat, x)
  return zeroResult
:normalizeX
  xSubnormal: xNoExponent = compare.equalInt64(xExponent, zero=0)
  if xNoExponent subnormalX normalX
:subnormalX
  xLeading: xLead = leadingShift(xRaw)
  xExponentOf: xNewExponent = math.subtractInt64(zero, xLead)
  set xExponent xNewExponent
  xShiftAmount: xAmount = math.addInt64(xLead, one=1)
  xShiftIt: xShifted = bits.shiftLeftUInt64(xRaw, xAmount)
  set xBits xShifted
  goto normalizeY
:normalX
  xMantissa: xKept = bits.andUInt64(xRaw, mantissaMask)
  xHidden: xWithHidden = bits.orUInt64(xKept, hidden)
  set xBits xWithHidden
  goto normalizeY
:normalizeY
  ySubnormal: yNoExponent = compare.equalInt64(yExponent, zero)
  if yNoExponent subnormalY normalY
:subnormalY
  yLeading: yLead = leadingShift(yRaw)
  yExponentOf: yNewExponent = math.subtractInt64(zero, yLead)
  set yExponent yNewExponent
  yShiftAmount: yAmount = math.addInt64(yLead, one)
  yShiftIt: yShifted = bits.shiftLeftUInt64(yRaw, yAmount)
  set yBits yShifted
  goto reduce
:normalY
  yMantissa: yKept = bits.andUInt64(yRaw, mantissaMask)
  yHidden: yWithHidden = bits.orUInt64(yKept, hidden)
  set yBits yWithHidden
  goto reduce
:reduce
  goto eachStep
:eachStep loop=while max=forever
  moreCheck: more = compare.greaterThanInt64(xExponent, yExponent)
  if more subtractStep last
:subtractStep in=eachStep
  differenceOf: difference = math.wrappingSubtractUInt64(xBits, yBits)
  set probe difference
  topOf: topBit = bits.shiftRightUInt64(difference, sixtyThree=63)
  fitsCheck: fits = compare.equalUInt64(topBit, zeroWide)
  if fits fitStep doubleStep
:fitStep in=eachStep
  exactCheck: exact = compare.equalUInt64(difference, zeroWide)
  if exact signedZero keepDifference
:keepDifference in=eachStep
  set xBits difference
  goto doubleStep
:doubleStep in=eachStep
  doubleIt: doubled = bits.shiftLeftUInt64(xBits, oneShift)
  set xBits doubled
  stepDown: lowered = math.subtractInt64(xExponent, one)
  set xExponent lowered
  goto eachStep
:last
  lastDifference: finalDifference = math.wrappingSubtractUInt64(xBits, yBits)
  lastTop: finalTop = bits.shiftRightUInt64(finalDifference, sixtyThree)
  lastFits: finalFits = compare.equalUInt64(finalTop, zeroWide)
  if finalFits lastExact renormalize
:lastExact
  lastZero: finalExact = compare.equalUInt64(finalDifference, zeroWide)
  if finalExact signedZero keepLast
:keepLast
  set xBits finalDifference
  goto renormalize
:renormalize
  goto eachShift
:eachShift loop=while max=sixtyFour
  hiddenOf: hiddenPart = bits.shiftRightUInt64(xBits, fiftyTwo)
  normalCheck: normalized = compare.notEqualUInt64(hiddenPart, zeroWide)
  if normalized scale shiftUp
:shiftUp in=eachShift
  shiftOne: shiftedUp = bits.shiftLeftUInt64(xBits, oneShift)
  set xBits shiftedUp
  shiftExponent: shiftedExponent = math.subtractInt64(xExponent, one)
  set xExponent shiftedExponent
  goto eachShift
:scale
  positiveCheck: positive = compare.greaterThanInt64(xExponent, zero)
  if positive normalResult subnormalResult
:normalResult
  dropHidden: withoutHidden = math.subtractUInt64(xBits, hidden)
  exponentBack: exponentBits = convert.int64BitsToUInt64(xExponent)
  exponentPlace: exponentField = bits.shiftLeftUInt64(exponentBits, fiftyTwo)
  joinNormal: normalBits = bits.orUInt64(withoutHidden, exponentField)
  signNormal: signedNormal = bits.orUInt64(normalBits, xSign)
  normalValue: normalResultValue = convert.uint64BitsToFloat64(signedNormal)
  return normalResultValue
:subnormalResult
  shiftBack: backBy = math.subtractInt64(one, xExponent)
  shiftDown: subnormalBits = bits.shiftRightUInt64(xBits, backBy)
  signSubnormal: signedSubnormal = bits.orUInt64(subnormalBits, xSign)
  subnormalValue: subnormalResultValue = convert.uint64BitsToFloat64(signedSubnormal)
  return subnormalResultValue

op leadingShift "For a subnormal's bits: how many places past the 12 exponent and sign bits its first set bit is (musl's count for `ux <<= -ex + 1`)"
  input value UInt64 copied
  output Int64
  let count Int64 0 mut
  let probe UInt64 0 mut
  let sixtyFour Int64 64
:begin
  shiftOut: shifted = bits.shiftLeftUInt64(value, twelve=12)
  set probe shifted
  goto eachBit
:eachBit loop=while max=sixtyFour
  topOf: topBit = bits.shiftRightUInt64(probe, sixtyThree=63)
  setCheck: isSet = compare.notEqualUInt64(topBit, zeroWide=0)
  if isSet done shift
:shift in=eachBit
  shiftOne: shiftedOne = bits.shiftLeftUInt64(probe, one=1)
  set probe shiftedOne
  countOne: counted = math.addInt64(count, one)
  set count counted
  goto eachBit
:done
  return count

op floatRemainderC "fmod, as the C library names it: the exact remainder with the dividend's sign"
  input x Float64 copied
  input y Float64 copied
  output Float64
  abi library "fmod"
:begin
  remainderIt: remainder = floatRemainder(x, y)
  return remainder

## ---------------------------------------------------------------- exit handlers (D-162)

op registerHandler "Add a handler (a function and the argument it is called with) to the list kept at a place of machine.state: the list's block, how many, how many it holds; 0, or -1 when there is no memory"
  input listAt Int64 copied
  input function machine.Address copied
  input argument machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let fine Int32 0
:begin
  listCell = kernel.stateAt(listAt)
  calc countCell = listCell + 8
  calc capacityCell = listCell + 16
  count = machine.loadInt64(countCell)
  capacity = machine.loadInt64(capacityCell)
  when count < capacity store grow
:grow
  calc larger = capacity * 2 + 32
  block = machine.loadAddress(listCell)
  calc grown = heap.resize(block, larger * 16)
  machine.storeAddress(listCell, grown)
  machine.storeInt64(capacityCell, larger)
  goto store
:store
  entries = machine.loadAddress(listCell)
  calc entryAt = entries + count * 16
  machine.storeAddress(entryAt, function)
  calc argumentAt = entryAt + 8
  machine.storeAddress(argumentAt, argument)
  machine.storeInt64(countCell, count + 1)
  return fine

op runHandlers "Call the handlers of a list, the last registered first, each with its argument (one registered while they run runs too), and empty it"
  invariant runsInReverse "Handlers run in the reverse of the order they were registered"
  input listAt Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  listCell = kernel.stateAt(listAt)
  calc countCell = listCell + 8
  goto eachHandler
:eachHandler loop=while max=forever
  count = machine.loadInt64(countCell)
  when count <= 0 done call
:call in=eachHandler
  calc last = count - 1
  machine.storeInt64(countCell, last)
  entries = machine.loadAddress(listCell)
  calc entryAt = entries + last * 16
  function = machine.loadAddress(entryAt)
  calc argumentAt = entryAt + 8
  argument = machine.loadAddress(argumentAt)
  machine.callWithAddress(function, argument)
  goto eachHandler
:done
  return

op atExit "atexit: register a function exit calls, the last registered first; 0"
  input function machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "atexit"
:begin
  nowhere = machine.zero()
  result = registerHandler(exitListAt, function, nowhere)
  return result

op atQuickExit "at_quick_exit: register a function quick_exit calls, the last registered first; 0"
  input function machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "at_quick_exit"
:begin
  nowhere = machine.zero()
  result = registerHandler(quickListAt, function, nowhere)
  return result

op quickExit "quick_exit: call the at_quick_exit functions, then end the process at once, flushing nothing"
  input code Int32 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "quick_exit"
:begin
  runHandlers(quickListAt)
  endProcess(code)
  return

op exitAtOnce "_Exit: end the process at once"
  input code Int32 copied
  effect use system.calls
  uses systemCalls
  abi library "_Exit"
:begin
  endProcess(code)
  return

## ---------------------------------------------------------------- division of longs (D-157's pairs)

op longDivide "ldiv: a long's quotient (toward zero) and remainder, as ldiv_t"
  input numerator Int64 copied
  input denominator Int64 copied
  output Quotient
  abi library "ldiv"
:begin
  pair = divideWhole(numerator, denominator)
  return pair

op longLongDivide "lldiv: a long long's quotient and remainder, as lldiv_t"
  input numerator Int64 copied
  input denominator Int64 copied
  output Quotient
  abi library "lldiv"
:begin
  pair = divideWhole(numerator, denominator)
  return pair

op widestDivide "imaxdiv: an intmax_t's quotient and remainder, as imaxdiv_t"
  input numerator Int64 copied
  input denominator Int64 copied
  output Quotient
  abi library "imaxdiv"
:begin
  pair = divideWhole(numerator, denominator)
  return pair

op divideWhole "The quotient toward zero and the remainder of two whole numbers, as a pair"
  invariant dividesTowardZero "The quotient is truncated and quotient * denominator + remainder is the numerator"
  input numerator Int64 copied
  input denominator Int64 copied
  output Quotient
:begin
  calc quotient = numerator / denominator
  calc remainder = numerator % denominator
  pair = Quotient.new(quotient, remainder)
  return pair

## ---------------------------------------------------------------- _FORTIFY_SOURCE's checked functions (D-165)
##
## glibc's headers, under _FORTIFY_SOURCE (on by default with optimization on Ubuntu), call `__memcpy_chk` and its
## kin where the compiler knows the target's size. Each checks that what it writes fits that size, and otherwise
## writes glibc's message to standard error and aborts, as glibc's __chk_fail does; then it does what the unchecked
## function does.

op checkFailed "__chk_fail: a checked function was asked to write past its buffer: glibc's message on standard error, then abort"
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__chk_fail"
  let message String "*** buffer overflow detected ***: terminated\n"
:begin
  messageAt = machine.addressOfString(message)
  bytes = string.byteLength(message)
  writeStream(2, messageAt, bytes)
  abortProcess()
  return

op checkFits "Fail as __chk_fail does when `needed` bytes do not fit in `room` (both as unsigned sizes)"
  invariant passesWhatFits "Returns when the bytes fit, so the checked function goes on"
  input needed Int64 copied
  input room Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  when convert.int64BitsToUInt64(needed) > convert.int64BitsToUInt64(room) fail fits
:fail
  checkFailed()
  return
:fits
  return

op memoryCopyChecked "__memcpy_chk: memcpy, when the bytes fit the target"
  input target machine.Address copied
  input source machine.Address copied
  input bytes Int64 copied
  input room Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__memcpy_chk"
:begin
  checkFits(bytes, room)
  result = memoryCopy(target, source, bytes)
  return result

op memoryMoveChecked "__memmove_chk: memmove, when the bytes fit the target"
  input target machine.Address copied
  input source machine.Address copied
  input bytes Int64 copied
  input room Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__memmove_chk"
:begin
  checkFits(bytes, room)
  result = memoryMove(target, source, bytes)
  return result

op memorySetChecked "__memset_chk: memset, when the bytes fit the target"
  input target machine.Address copied
  input value Int32 copied
  input bytes Int64 copied
  input room Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__memset_chk"
:begin
  checkFits(bytes, room)
  result = memorySet(target, value, bytes)
  return result

op stringCopyChecked "__strcpy_chk: strcpy, when the text and its 0 fit the target"
  input target machine.Address copied
  input source machine.Address copied
  input room Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__strcpy_chk"
:begin
  length = cStringLength(source)
  checkFits(length + 1, room)
  result = stringCopy(target, source)
  return result

op stringCopyBoundedChecked "__strncpy_chk: strncpy, when its count fits the target"
  input target machine.Address copied
  input source machine.Address copied
  input count Int64 copied
  input room Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__strncpy_chk"
:begin
  checkFits(count, room)
  result = stringCopyBounded(target, source, count)
  return result

op stringAppendChecked "__strcat_chk: strcat, when both texts and the 0 fit the target"
  input target machine.Address copied
  input source machine.Address copied
  input room Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__strcat_chk"
:begin
  had = cStringLength(target)
  adds = cStringLength(source)
  checkFits(had + adds + 1, room)
  result = stringAppend(target, source)
  return result

op stringAppendBoundedChecked "__strncat_chk: strncat, when the target's text, what is appended, and the 0 fit the target"
  input target machine.Address copied
  input source machine.Address copied
  input count Int64 copied
  input room Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__strncat_chk"
:begin
  had = cStringLength(target)
  adds = boundedLength(source, count)
  checkFits(had + adds + 1, room)
  result = stringAppendBounded(target, source, count)
  return result

op windowsErrno "The errno for a Windows error code, by the table of windowsErrors: glibc's number for the same failure (ENOENT for a file or path not found, EACCES for access denied, EEXIST for a file that exists, EPIPE for a broken pipe, ENOSPC for a full disk, ...); EINVAL for any other code (D-171)"
  invariant mapsWindowsErrors "Every code the table names gives its errno, and any other EINVAL"
  input code Int32 copied
  output Int32
  let at Int64 1 mut
:begin
  count = windowsErrors.length()
  goto eachRow
:eachRow loop=while max=count
  when at > count unknown look
:look in=eachRow
  findRow: row = windowsErrors.rowAt(at) ! rowError
  iferr findRow missing compare
:compare in=eachRow
  rowCode = WindowsError.code(row)
  when rowCode == code found next
:next in=eachRow
  calc at := at + 1
  goto eachRow
:found
  mapped = WindowsError.errno(row)
  return mapped
:missing
  return invalidError
:unknown
  return invalidError

@tests

## Tests write C strings in the last 4 KiB of machine.state (from byte 61440), which the runtime's own state never
## reaches. Expected values are glibc's (tests/test_runtime_nolibc.py compares the library with glibc on Linux).

op firstScratch "The address of the tests' scratch bytes, with a text and a 0 byte written there"
  input text String borrowed
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  findScratch: place = machine.offset(state, scratchAt=61440)
  findText: textAt = machine.addressOfString(text)
  textLength: bytes = string.byteLength(text)
  copyIt: machine.copy(place, textAt, bytes)
  findEnd: end = machine.offset(place, bytes)
  storeEnd: machine.storeByte(end, nul=0)
  return place

op secondScratch "The address of a second scratch area, 2 KiB after the first, with a text and a 0 byte written there"
  input text String borrowed
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  findScratch: place = machine.offset(state, secondAt=63488)
  findText: textAt = machine.addressOfString(text)
  textLength: bytes = string.byteLength(text)
  copyIt: machine.copy(place, textAt, bytes)
  findEnd: end = machine.offset(place, bytes)
  storeEnd: machine.storeByte(end, nul=0)
  return place

op longMatches "Whether strtol (or strtoul) of a text in a base gives a value, reads a number of bytes, and leaves errno as expected"
  input text String borrowed
  input base Int32 copied
  input unsigned Bool copied
  input expected Int64 copied
  input expectedEnd Int64 copied
  input expectedErrno Int32 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
:begin
  writeIt: place = firstScratch(text)
  clearErrno: setErrno(zero32=0)
  findEnd: endCell = kernel.stateAt(realAt)
  presetEnd: machine.storeAddress(endCell, place)
  parseIt: value = parseWhole(place, endCell, base, unsigned)
  valueCheck: sameValue = compare.equalInt64(expected, value)
  readEnd: end = machine.loadAddress(endCell)
  offsetOf: read = machine.difference(end, place)
  endCheck: sameEnd = compare.equalInt64(expectedEnd, read)
  findErrno: errnoPlace = kernel.stateAt(errnoAt)
  readErrno: errno = machine.loadInt32(errnoPlace)
  errnoCheck: sameErrno = compare.equalInt32(expectedErrno, errno)
  firstTwo: valueAndEnd = logic.and(sameValue, sameEnd)
  allThree: matches = logic.and(valueAndEnd, sameErrno)
  return matches

op realMatches "Whether strtod of a text gives a double of the expected bits and reads a number of bytes"
  input text String borrowed
  input expectedBits UInt64 copied
  input expectedEnd Int64 copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  writeIt: place = firstScratch(text)
  findEnd: endCell = kernel.stateAt(hexBitsAt)
  parseIt: value = parseReal(place, endCell)
  toBits: valueBits = convert.float64BitsToUInt64(value)
  valueCheck: sameValue = compare.equalUInt64(expectedBits, valueBits)
  readEnd: end = machine.loadAddress(endCell)
  offsetOf: read = machine.difference(end, place)
  endCheck: sameEnd = compare.equalInt64(expectedEnd, read)
  bothCheck: matches = logic.and(sameValue, sameEnd)
  return matches

op sameFloat "Whether a double has the expected bits"
  input expectedBits UInt64 copied
  input actual Float64 copied
  output Bool
:begin
  toBits: actualBits = convert.float64BitsToUInt64(actual)
  sameCheck: same = compare.equalUInt64(expectedBits, actualBits)
  return same

op functionNamed "The address of a function of the C library by a name"
  input name String borrowed
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findName: nameAt = machine.addressOfString(name)
  nameLength: bytes = string.byteLength(name)
  findIt: function = lookup(nameAt, bytes)
  return function

op sameInt "Whether an int is the expected one"
  input expected Int32 copied
  input actual Int32 copied
  output Bool
:begin
  sameCheck: same = compare.equalInt32(expected, actual)
  return same

op markItems "Put a byte after each of four three-letter items, at 3, 7, 11, and 15"
  input base machine.Address copied
  input value Byte copied
  effect use machine.memory
  uses memoryAccess
:begin
  findFirst: first = machine.offset(base, three=3)
  storeFirst: machine.storeByte(first, value)
  findSecond: secondItem = machine.offset(base, seven=7)
  storeSecond: machine.storeByte(secondItem, value)
  findThird: third = machine.offset(base, eleven=11)
  storeThird: machine.storeByte(third, value)
  findFourth: fourth = machine.offset(base, fifteen=15)
  storeFourth: machine.storeByte(fourth, value)
  return

test classTest "Each character's class bits are glibc's, the ctype functions mask them, toupper and tolower change only letters, and the tables hold the same"
  verifies classBits classifiesLikeGlibc
  verifies toUpper upperCases
  verifies toLower lowerCases
  verifies classTable pointsAtClasses
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  classA: aBits = classBits(capitalA=65)
  checkA: aSame = sameInt(upperHexBits=54536, aBits)
  expectA: test.assertTrue(aSame)
  classTab: tabBits = classBits(tab=9)
  checkTab: tabSame = sameInt(tabClass=8195, tabBits)
  expectTab: test.assertTrue(tabSame)
  classHigh: highBits = classBits(high=200)
  checkHigh: highSame = sameInt(none32=0, highBits)
  expectHigh: test.assertTrue(highSame)
  classEof: eofBits = classBits(eof=-1)
  checkEof: eofSame = sameInt(none32, eofBits)
  expectEof: test.assertTrue(eofSame)
  alphaOf: alpha = alphaClass(smallQ=113)
  checkAlpha: alphaSame = sameInt(alphaBit=1024, alpha)
  expectAlpha: test.assertTrue(alphaSame)
  blankOf: blank = blankClass(space=32)
  checkBlank: blankSame = sameInt(blankBit=1, blank)
  expectBlank: test.assertTrue(blankSame)
  punctOf: punct = punctuationClass(atSign=64)
  checkPunct: punctSame = sameInt(punctBit=4, punct)
  expectPunct: test.assertTrue(punctSame)
  digitCheck: digit = digitClass(capitalA)
  checkDigit: digitSame = sameInt(none32, digit)
  expectDigit: test.assertTrue(digitSame)
  upperOf: upper = toUpper(smallQ)
  checkUpper: upperSame = sameInt(capitalQ=81, upper)
  expectUpper: test.assertTrue(upperSame)
  upperKeep: kept = toUpper(eof)
  checkKept: keptSame = sameInt(eof, kept)
  expectKept: test.assertTrue(keptSame)
  lowerOf: lower = toLower(capitalQ)
  checkLower: lowerSame = sameInt(smallQ, lower)
  expectLower: test.assertTrue(lowerSame)
  upperSigned: signedUpper = toUpper(minusTwo=-2)
  checkSigned: signedSame = sameInt(unsignedTwo=254, signedUpper)
  expectSigned: test.assertTrue(signedSame)
  findCell: cell = classTable()
  readZero: zeroAt = machine.loadAddress(cell)
  findWordA: wordA = machine.offset(zeroAt, wordOffset=130)
  readLowA: lowA = machine.loadByte(wordA)
  widenLowA: lowAWide = convert.byteToInt64(lowA)
  expectLowA: test.assertEqualInt64(lowAByte=8, lowAWide)
  findUpperCell: upperCell = upperTable()
  readUpperZero: upperZero = machine.loadAddress(upperCell)
  findUpperQ: upperQ = machine.offset(upperZero, upperOffset=452)
  readUpperQ: upperValue = machine.loadInt32(upperQ)
  checkUpperQ: upperQSame = sameInt(capitalQ, upperValue)
  expectUpperQ: test.assertTrue(upperQSame)
  findLowerCell: lowerCell = lowerTable()
  readLowerZero: lowerZero = machine.loadAddress(lowerCell)
  findLowerEof: lowerEof = machine.offset(lowerZero, eofOffset=-4)
  readLowerEof: lowerEofValue = machine.loadInt32(lowerEof)
  checkLowerEof: lowerEofSame = sameInt(eof, lowerEofValue)
  expectLowerEof: test.assertTrue(lowerEofSame)
  return

test stringTest "strlen counts to the 0 byte, strcmp and memcmp give byte differences, strchr, strrchr, strstr, and memchr find, strspn and strcspn count, and the copies copy"
  verifies cStringLength countsToZero
  verifies compareStrings ordersLikeGlibc
  verifies memoryCompare comparesRanges
  verifies stringFind findsCharacter
  verifies stringSearch findsText
  verifies spanOf spansSet
  verifies duplicate duplicatesBytes
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  writeHello: hello = firstScratch(helloText="hello, world")
  lengthOf: length = cStringLength(hello)
  expectLength: test.assertEqualInt64(twelve=12, length)
  writeHelp: help = secondScratch(helpText="help")
  compareIt: order = compareStrings(hello, help, length, no=false)
  checkOrder: orderSame = sameInt(lMinusP=-4, order)
  expectOrder: test.assertTrue(orderSame)
  compareFew: fewOrder = compareStrings(hello, help, three=3, no)
  checkFew: fewSame = sameInt(none32=0, fewOrder)
  expectFew: test.assertTrue(fewSame)
  writeUpper: upper = secondScratch(upperText="HELLO, WORLD")
  compareFolded: foldedOrder = compareStrings(hello, upper, length, yes=true)
  checkFolded: foldedSame = sameInt(none32, foldedOrder)
  expectFolded: test.assertTrue(foldedSame)
  compareRaw: rawOrder = memoryCompare(hello, upper, five=5)
  checkRaw: rawSame = sameInt(caseDifference=32, rawOrder)
  expectRaw: test.assertTrue(rawSame)
  findComma: comma = stringFind(hello, commaCode=44, no)
  commaOffset: commaAt = machine.difference(comma, hello)
  expectComma: test.assertEqualInt64(five, commaAt)
  findLastO: lastO = stringFind(hello, smallO=111, yes)
  lastOffset: lastAt = machine.difference(lastO, hello)
  expectLastO: test.assertEqualInt64(eight=8, lastAt)
  findEnd: end = stringFind(hello, none32, no)
  endOffset: endAt = machine.difference(end, hello)
  expectEndAt: test.assertEqualInt64(twelve, endAt)
  findMissing: missing = stringFind(hello, smallZ=122, no)
  nowhere: anywhere = machine.zero()
  missingCheck: isMissing = machine.equal(missing, anywhere)
  expectMissing: test.assertTrue(isMissing)
  writeWorld: world = secondScratch(worldText="wor")
  searchIt: found = stringSearch(hello, world)
  foundOffset: foundAt = machine.difference(found, hello)
  expectFound: test.assertEqualInt64(seven=7, foundAt)
  writeLetters: letters = secondScratch(lettersText="ehlo")
  spanIt: spanned = spanOf(hello, letters, no)
  expectSpan: test.assertEqualInt64(five, spanned)
  writePunct: punct = secondScratch(punctText=" ,")
  complementIt: before = spanOf(hello, punct, yes)
  expectComplement: test.assertEqualInt64(five, before)
  findW: w = memoryFind(hello, smallW=119, twelve)
  wOffset: wAt = machine.difference(w, hello)
  expectW: test.assertEqualInt64(seven, wAt)
  copyIt: copy = duplicate(hello, length)
  copyOrder: copyCompare = stringCompare(copy, hello)
  checkCopy: copySame = sameInt(none32, copyCompare)
  expectCopy: test.assertTrue(copySame)
  freeCopy: release(copy)
  return

test numberTest "strtol reads glibc's prefixes, bases, ends, and limits; abs wraps; div packs"
  verifies parseWhole readsLikeStrtol
  verifies absolute wrapsLikeGlibc
  verifies absoluteLong wrapsLong
  verifies divide packsQuotient
  effect use machine.memory
  uses memoryAccess
:begin
  writeDirect: direct = firstScratch(directText="12")
  nowhere: anywhere = machine.zero()
  parseDirect: directValue = parseWhole(direct, anywhere, ten32=10, no=false)
  expectDirect: test.assertEqualInt64(twelve=12, directValue)
  readPlain: plain = longMatches(plainText="  -42xyz", ten32, no, minusFortyTwo=-42, five=5, none32=0)
  expectPlain: test.assertTrue(plain)
  readHex: hex = longMatches(hexText="0x1fZ", zero32=0, no, thirtyOne=31, four=4, none32)
  expectHex: test.assertTrue(hex)
  readOctal: octal = longMatches(octalText="0777", zero32, no, octalValue=511, four, none32)
  expectOctal: test.assertTrue(octal)
  readBareX: bareX = longMatches(bareXText="0xg", zero32, no, zero=0, one=1, none32)
  expectBareX: test.assertTrue(bareX)
  readNone: noDigits = longMatches(noneText="  +", ten32, no, zero, zero, none32)
  expectNone: test.assertTrue(noDigits)
  readBig: big = longMatches(bigText="99999999999999999999", ten32, no, most=9223372036854775807, twenty=20, range32=34)
  expectBig: test.assertTrue(big)
  readSmall: small = longMatches(smallText="-9223372036854775808", ten32, no, least=-9223372036854775808, twenty, none32)
  expectSmall: test.assertTrue(small)
  readUnsigned: unsignedOne = longMatches(minusOneText="-1", ten32, yes=true, minusOne=-1, two=2, none32)
  expectUnsigned: test.assertTrue(unsignedOne)
  readBase36: base36Value = longMatches(zText="zz", base36=36, no, zzValue=1295, two, none32)
  expectBase36: test.assertTrue(base36Value)
  readInvalid: invalid = longMatches(invalidText="12", one32=1, no, zero, zero, invalid32=22)
  expectInvalid: test.assertTrue(invalid)
  absoluteIt: magnitude = absolute(minusSeven=-7)
  checkMagnitude: magnitudeSame = sameInt(seven=7, magnitude)
  expectMagnitude: test.assertTrue(magnitudeSame)
  absoluteMin: minMagnitude = absolute(intMin=-2147483648)
  checkMin: minSame = sameInt(intMin, minMagnitude)
  expectMin: test.assertTrue(minSame)
  absoluteLongIt: longMagnitude = absoluteLong(least)
  expectLongMin: test.assertEqualInt64(least, longMagnitude)
  divideIt: packed = divide(minusSeven, two32=2)
  expectPacked: test.assertEqualInt64(minusThree=-3, packed)
  return

test realTest "strtod reads decimal, hexadecimal, infinity, and NaN text as glibc does, with its ends"
  verifies parseReal readsLikeStrtod
  verifies parseHexReal readsHexadecimal
  verifies roundMantissa roundsToEven
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  writeDirect: direct = firstScratch(directText="2.5")
  nowhere: anywhere = machine.zero()
  parseDirect: directValue = parseReal(direct, anywhere)
  checkDirect: directSame = sameFloat(twoAndHalf=4612811918334230528, directValue)
  expectDirect: test.assertTrue(directSame)
  writeHex: hexText = firstScratch(hexDigits="1.8p1")
  parseHex: hexEnd = parseHexReal(hexText, zero=0)
  expectHexEnd: test.assertEqualInt64(five=5, hexEnd)
  roundTie: tie = roundMantissa(tieValue=20, three=3, no=false)
  tieSigned: tieWide = convert.uint64BitsToInt64(tie)
  expectTie: test.assertEqualInt64(two=2, tieWide)
  readHalf: half = realMatches(halfText=" 0.5x", halfBits=4602678819172646912, four=4)
  expectHalf: test.assertTrue(half)
  readPoint: point = realMatches(pointText="1.", oneBits=4607182418800017408, two=2)
  expectPoint: test.assertTrue(point)
  readLead: lead = realMatches(leadText="-.25e1", minusTwoAndHalfBits=13836183955189006336, six=6)
  expectLead: test.assertTrue(lead)
  readBareE: bareE = realMatches(bareEText="3e+", threeBits=4613937818241073152, one=1)
  expectBareE: test.assertTrue(bareE)
  readHexValue: hexValue = realMatches(hexValueText="0x1.8p1", threeBits, seven=7)
  expectHexValue: test.assertTrue(hexValue)
  readBareHex: bareHex = realMatches(bareHexText="0xz", zeroBits=0, one)
  expectBareHex: test.assertTrue(bareHex)
  readTiny: tiny = realMatches(tinyText="0x1p-1074", tinyBits=1, nine=9)
  expectTiny: test.assertTrue(tiny)
  readHexTie: hexTie = realMatches(hexTieText="0x1.00000000000008p0", oneBits, twenty=20)
  expectHexTie: test.assertTrue(hexTie)
  readInf: inf = realMatches(infText="-Infinity", minusInfinity=18442240474082181120, nine)
  expectInf: test.assertTrue(inf)
  readInfShort: infShort = realMatches(infShortText="infinit", infinityValue=9218868437227405312, three)
  expectInfShort: test.assertTrue(infShort)
  readNan: nan = realMatches(nanText="nan(abc)", nanValue=9221120237041090560, eight=8)
  expectNan: test.assertTrue(nan)
  readNone: noDigits = realMatches(noneText="-x", zeroBits, zero)
  expectNone: test.assertTrue(noDigits)
  readHuge: huge = realMatches(hugeText="1e999", infinityValue, five)
  expectHuge: test.assertTrue(huge)
  return

test mathTest "fabs, trunc, floor, ceil, round, fmod, and sqrt give glibc's values, signs of zero included"
  verifies floatAbsolute clearsSign
  verifies truncate dropsFraction
  verifies floorOf roundsDown
  verifies ceilingOf roundsUp
  verifies roundOf roundsHalfAway
  verifies floatRemainder remaindersExactly
  verifies squareRoot rootsExactly
  effect use machine.memory
  uses memoryAccess
  let minusHalf Float64 -0.5
  let minusTwoAndHalf Float64 -2.5
  let belowHalf Float64 0.49999999999999994
  let minusSevenAndHalf Float64 -7.5
  let two Float64 2.0
:begin
  absoluteIt: magnitude = floatAbsolute(minusHalf)
  checkMagnitude: magnitudeSame = sameFloat(halfBits=4602678819172646912, magnitude)
  expectMagnitude: test.assertTrue(magnitudeSame)
  truncateIt: truncated = truncate(minusHalf)
  checkTruncated: truncatedSame = sameFloat(minusZero=9223372036854775808, truncated)
  expectTruncated: test.assertTrue(truncatedSame)
  floorIt: floored = floorOf(minusHalf)
  checkFloored: flooredSame = sameFloat(minusOneBits=13830554455654793216, floored)
  expectFloored: test.assertTrue(flooredSame)
  ceilIt: ceiled = ceilingOf(minusHalf)
  checkCeiled: ceiledSame = sameFloat(minusZero, ceiled)
  expectCeiled: test.assertTrue(ceiledSame)
  roundIt: rounded = roundOf(minusTwoAndHalf)
  checkRounded: roundedSame = sameFloat(minusThree=13837309855095848960, rounded)
  expectRounded: test.assertTrue(roundedSame)
  roundBelow: roundedBelow = roundOf(belowHalf)
  checkBelow: belowSame = sameFloat(zeroBits=0, roundedBelow)
  expectBelow: test.assertTrue(belowSame)
  remainderIt: remainder = floatRemainder(minusSevenAndHalf, two)
  checkRemainder: remainderSame = sameFloat(minusOneAndHalf=13832806255468478464, remainder)
  expectRemainder: test.assertTrue(remainderSame)
  bigOf: big = convert.uint64BitsToFloat64(bigBits=9094988921128908188)
  tinyOf: tiny = convert.uint64BitsToFloat64(tinyBits=126121232842798723)
  remainderTiny: tinyRemainder = floatRemainder(big, tiny)
  checkTiny: tinySame = sameFloat(tinyRemainderBits=118396640582041260, tinyRemainder)
  expectTiny: test.assertTrue(tinySame)
  rootIt: root = squareRoot(two)
  checkRoot: rootSame = sameFloat(rootTwo=4609047870845172685, root)
  expectRoot: test.assertTrue(rootSame)
  return

test sortTest "qsort sorts with a C comparison, keeping equal items in order, and bsearch finds what it sorted"
  verifies sortItems sortsStably
  verifies searchItems searchesLikeGlibc
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let items String "dog_Cat_ant_cat_"
  let sorted String "ant_Cat_cat_dog_"
  let foldedName String "strcasecmp"
:begin
  placeItems: base = firstScratch(items)
  endItems: markItems(base, nul=0)
  findCompare: comparison = functionNamed(foldedName)
  sortIt: sortItems(base, four=4, four, comparison)
  showItems: markItems(base, underscore=95)
  viewSorted: view = machine.stringAt(base, sixteen=16)
  expectSorted: test.assertEqualString(sorted, view)
  endAgain: markItems(base, nul)
  writeKey: key = secondScratch(keyText="DOG")
  searchIt: found = searchItems(key, base, four, four, comparison)
  foundOffset: foundAt = machine.difference(found, base)
  expectFound: test.assertEqualInt64(twelve=12, foundAt)
  writeMissing: missingKey = secondScratch(missingText="bee")
  searchMissing: missing = searchItems(missingKey, base, four, four, comparison)
  nowhere: anywhere = machine.zero()
  missingCheck: isMissing = machine.equal(missing, anywhere)
  expectMissing: test.assertTrue(isMissing)
  return

test lookupTest "The table finds abs and stdout, which holds 1; a name the library lacks is nothing; c names the C library; malloc gives blocks; getenv finds PATH"
  verifies lookup findsByName
  verifies cLibraryName namesC
  verifies allocate allocatesBlocks
  verifies environmentValue readsEnvironment
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let absName String "abs"
  let stdoutName String "stdout"
  let missingName String "semanticscriptNoSuchSymbol"
  let cName String "c"
  let libcName String "libc.so.6"
  let pathName String "PATH"
  let unsetName String "SEMANTICSCRIPT_SURELY_UNSET_42"
:begin
  findAbsName: absAt = machine.addressOfString(absName)
  absLength: absBytes = string.byteLength(absName)
  findAbs: absFunction = lookup(absAt, absBytes)
  nowhere: anywhere = machine.zero()
  absFound: absMissing = machine.equal(absFunction, anywhere)
  absPresent: hasAbs = logic.not(absMissing)
  expectAbs: test.assertTrue(hasAbs)
  findStdoutName: stdoutNameAt = machine.addressOfString(stdoutName)
  stdoutLength: stdoutBytes = string.byteLength(stdoutName)
  findStdout: stdoutCell = lookup(stdoutNameAt, stdoutBytes)
  readStdout: stdoutValue = machine.loadAddress(stdoutCell)
  stdoutFile = kernel.stateAt(2048)
  test.assertTrue(stdoutValue == stdoutFile)
  findMissingName: missingAt = machine.addressOfString(missingName)
  missingLength: missingBytes = string.byteLength(missingName)
  findMissing: missingFunction = lookup(missingAt, missingBytes)
  missingCheck: isMissing = machine.equal(missingFunction, anywhere)
  expectMissing: test.assertTrue(isMissing)
  findC: cAt = machine.addressOfString(cName)
  checkC: isC = cLibraryName(cAt, one=1)
  expectC: test.assertTrue(isC)
  findLibc: libcAt = machine.addressOfString(libcName)
  libcLength: libcBytes = string.byteLength(libcName)
  checkLibc: isLibc = cLibraryName(libcAt, libcBytes)
  osCheck: onLinux = system.linux()
  sameAnswer: agrees = logic.xor(isLibc, onLinux)
  disagree: expected = logic.not(agrees)
  expectLibc: test.assertTrue(expected)
  takeBlock: block = allocate(hundred=100)
  blockCheck: noBlock = machine.equal(block, anywhere)
  blockPresent: hasBlock = logic.not(noBlock)
  expectBlock: test.assertTrue(hasBlock)
  freeBlock: release(block)
  takeHuge: huge = allocate(minusOne=-1)
  hugeCheck: noHuge = machine.equal(huge, anywhere)
  expectHuge: test.assertTrue(noHuge)
  writePath: path = firstScratch(pathName)
  findPath: pathValue = environmentValue(path)
  pathCheck: noPath = machine.equal(pathValue, anywhere)
  pathPresent: hasPath = logic.not(noPath)
  pathOrJit: pathFine = logic.or(hasPath, onLinux)
  expectPath: test.assertTrue(pathFine)
  writeUnset: unsetText = firstScratch(unsetName)
  findUnset: unsetValue = environmentValue(unsetText)
  unsetCheck: noUnset = machine.equal(unsetValue, anywhere)
  expectUnset: test.assertTrue(noUnset)
  return

test helpersTest "The pieces the other C library modules call: a byte at an offset, errno set, an int's low 32 bits, and a length bounded"
  verifies byteAt readsByte
  verifies setErrno setsErrno
  verifies lowInt32 wrapsLow
  verifies boundedLength stopsAtBound
  verifies errorText namesErrors
  verifies errorMessage describesErrno
  verifies memoryFind findsByte
  verifies charOf keepsLowByte
  verifies runHandlers runsInReverse
  verifies checkFits passesWhatFits
  verifies errnoCell firstThreadsCell
  verifies windowsErrno mapsWindowsErrors
  verifies divideWhole dividesTowardZero
  verifies prepare pointsAtStreams
  verifies isSpaceByte spacesLikeC
  verifies digitOf readsDigits
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let sample String "hello"
  let absText String "abs"
:begin
  place = firstScratch(sample)
  second = byteAt(place, 1)
  test.assertTrue(second == 101)
  setErrno(34)
  errnoPlace = kernel.stateAt(errnoAt)
  errno = machine.loadInt32(errnoPlace)
  test.assertTrue(errno == 34)
  setErrno(0)
  low = lowInt32(4294967295)
  test.assertTrue(low == -1)
  bounded = boundedLength(place, 3)
  test.assertEqualInt64(3, bounded)
  whole = boundedLength(place, 99)
  test.assertEqualInt64(5, whole)
  setErrno(-5)
  message = errorMessage()
  messageLength = cStringLength(message)
  test.assertEqualInt64(16, messageLength)
  shown = errorText(1234)
  shownLength = cStringLength(shown)
  test.assertEqualInt64(18, shownLength)
  found = memoryFind(place, 108, 5)
  calc foundAt = place + 2
  test.assertTrue(found == foundAt)
  lowByte = charOf(300)
  test.assertTrue(lowByte == 44)
  tabSpace = isSpaceByte(9)
  test.assertTrue(tabSpace)
  letterValue = digitOf(90)
  test.assertTrue(letterValue == 35)
  prepare()
  stdinCell = kernel.stateAt(stdinAt)
  stdinValue = machine.loadAddress(stdinCell)
  stdinFile = kernel.stateAt(1920)
  test.assertTrue(stdinValue == stdinFile)
  absName = machine.addressOfString(absText)
  absAt = lookup(absName, 3)
  registerHandler(quickListAt, absAt, absAt)
  runHandlers(quickListAt)
  quickCell = kernel.stateAt(quickListAt + 8)
  left = machine.loadInt64(quickCell)
  test.assertEqualInt64(0, left)
  checkFits(4, 4)
  notFound = windowsErrno(2)
  test.assertTrue(notFound == 2)
  brokenPipe = windowsErrno(109)
  test.assertTrue(brokenPipe == 32)
  unknownCode = windowsErrno(99999)
  test.assertTrue(unknownCode == 22)
  sharedErrno = errnoCell()
  stateErrno = kernel.stateAt(errnoAt)
  test.assertTrue(sharedErrno == stateErrno)
  checkFits(0, 0)
  pair = divideWhole(-7, 2)
  quotient = Quotient.quotient(pair)
  remainder = Quotient.remainder(pair)
  test.assertEqualInt64(-3, quotient)
  test.assertEqualInt64(-1, remainder)
  setErrno(0)
  return
