module documents "JSON for a standalone executable: the json targets, reading text as Python's json.loads reads it and writing values as json.dumps writes them"
  path documents
  imports standard.machine standard.system standard.string standard.math standard.compare standard.convert standard.bits standard.logic standard.test kernel memory numbers frames heap tables values handles regions slots floats wide files
  exports jsonCall

capability memoryAccess "Authority to read a call's text, keep JSON values in memory, and write their text" use machine.memory none

capability systemCalls "Authority to take memory for JSON values and their text, and end the process on a trap" use system.calls none

## `json.parse` is `json.loads(text.decode("utf-8", "surrogateescape"))` as host.py calls it (D-151): the text's
## bytes are read as code points (each byte that is not part of valid UTF-8 the surrogate U+DC80 to U+DCFF), and
## positions are counted in code points, as CPython's scanner (Modules/_json.c) counts them. Accepted: what the
## scanner accepts, NaN, Infinity, and -Infinity among it; a leading U+FEFF is an error at 0; whitespace is space,
## tab, line feed, and carriage return. Each error is invalidAt with the scanner's position: `Expecting value` at
## the value's start, `Extra data`, `Expecting ',' delimiter`, `Expecting ':' delimiter`, `Expecting property
## name`, `Invalid control character`, `Invalid \escape` and `Invalid \uXXXX escape` where the scanner puts them,
## and `Unterminated string` at the opening quote. Nesting deeper than 2994 arrays and objects is tooDeep, where
## CPython 3.12's recursion limit stops `refined run`'s scanner. A whole number with more than 4300 digits traps
## as Python's int() refuses it. Duplicate keys keep their first place and their last value, as a dict does.
## `json.stringify` is `json.dumps(value, separators=(",", ":"), ensure_ascii=False)` encoded with
## surrogateescape: keys in order, text escaped as the C encoder escapes it, floats as repr writes them (NaN,
## Infinity, -Infinity), and a lone surrogate that is not one of surrogateescape's traps as the encoder raises.
## machine.state bytes 1120 to 1215 belong to this module: 1120 where the scanner went on, 1128 the error found (1
## invalidAt, 2 tooDeep), 1136 its position, 1144 a code point read, 1152 to 1183 a float's text, 1184 to 1215 a
## whole number's text.
constant kindJson "The kind of a JSON value's handle" Int64 11

constant deepest "How many arrays and objects may nest: CPython 3.12's recursion limit as `refined run` reaches it" Int64 2994

constant mostDigits "The most digits Python's int() reads from text" Int64 4300

constant scannedAt "Where the scanner went on, in machine.state" Int64 1120

constant errorAt "Where the error found is kept, in machine.state" Int64 1128

constant positionAt "Where the error's position is kept, in machine.state" Int64 1136

constant codeAt "Where a code point read is put, in machine.state" Int64 1144

constant floatTextAt "Where a float's text is written, in machine.state" Int64 1152

constant digitsAt "Where a whole number's text is written, in machine.state" Int64 1184

constant kindNull "A null value's kind" Int64 1

constant kindBoolean "A boolean value's kind" Int64 2

constant kindWhole "The kind of a whole number that fits an Int64" Int64 3

constant kindBig "The kind of a whole number too large for an Int64" Int64 4

constant kindFloat "A Float64 value's kind" Int64 5

constant kindText "A text value's kind" Int64 6

constant kindArray "An array's kind" Int64 7

constant kindObject "An object's kind" Int64 8

constant invalidAt "json.ParseError.invalidAt, numbered from 1" Int32 1

constant tooDeep "json.ParseError.tooDeep, numbered from 1" Int32 2

constant wrongKind "json.AccessError.wrongKind, numbered from 1" Int32 1

constant missing "json.AccessError.missing, numbered from 1" Int32 2

constant outOfRange "json.AccessError.outOfRange, numbered from 1" Int32 3

constant notWhole "json.AccessError.notWhole, numbered from 1" Int32 4

constant forever "The bound of a loop that runs as long as its text" Int64 9223372036854775807

op endProcess "End the process with an exit code: ExitProcess on Windows, exit_group on Linux (D-138)"
  input code Int32 copied
  effect use system.calls
  uses systemCalls
:begin
  osCheck: onLinux = system.posix()
  if onLinux linuxExit windowsExit
:linuxExit
  widenCode: wideCode = convert.int32ToInt64(code)
  callExit: exitResult = system.exitGroup(wideCode)
  return
:windowsExit
  callExitProcess: system.exitProcess(code)
  return

op failBuilt "Report a trap whose message a builder holds, and end the process with exit code 70"
  input builder machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readText: text = wide.builderText(builder)
  readLength: bytes = wide.builderLength(builder)
  writeReport: status = frames.report(text, bytes)
  exit: endProcess(trapCode=70)
  return

op addText "Add a text to a builder"
  input builder machine.Address copied
  input text String borrowed
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findText: textAt = machine.addressOfString(text)
  textLength: bytes = string.byteLength(text)
  addIt: wide.builderAdd(builder, textAt, bytes)
  return

op addNumber "Add a whole number's decimal text to a builder"
  input builder machine.Address copied
  input value Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findDigits: digits = kernel.stateAt(digitsAt)
  writeIt: count = numbers.formatDecimal(value, digits)
  addIt: wide.builderAdd(builder, digits, count)
  return

op failInside "Trap as `refined run` does when a json target raises a Python exception: `<target>` failed inside the runtime, then the exception"
  input target String borrowed
  input problem String borrowed
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  makeMessage: message = wide.builderNew()
  addOpen: addText(message, openText="`")
  addTarget: addText(message, target)
  addFailed: addText(message, failedText="` failed inside the runtime: ")
  addProblem: addText(message, problem)
  failIt: failBuilt(message)
  return

op word "A whole number of a value at an offset"
  input node machine.Address copied
  input offset Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findPart: at = machine.offset(node, offset)
  readPart: value = machine.loadInt64(at)
  return value

op setWord "Store a whole number of a value at an offset"
  input node machine.Address copied
  input offset Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  findPart: at = machine.offset(node, offset)
  storePart: machine.storeInt64(at, value)
  return

op stateWord "A whole number of this module's part of machine.state"
  input offset Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findSlot: slot = kernel.stateAt(offset)
  readSlot: value = machine.loadInt64(slot)
  return value

op setStateWord "Store a whole number in this module's part of machine.state"
  input offset Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  findSlot: slot = kernel.stateAt(offset)
  storeSlot: machine.storeInt64(slot, value)
  return

## ---------------------------------------------------------------- code points

op codeOf "The code point at a position of the text's code points"
  input codes machine.Address copied
  input at Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  offsetOf: offset = math.multiplyInt64(at, four=4)
  findCode: place = machine.offset(codes, offset)
  readCode: code = machine.loadInt32(place)
  widen: value = convert.int32ToInt64(code)
  return value

op decodeInput "The text's code points as surrogateescape reads its bytes: each valid UTF-8 sequence its code point, each other byte U+DC80 to U+DCFF; a heap block of 32-bit code points, their count stored at an address"
  input text machine.Address copied
  input bytes Int64 copied
  input count machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let made Int64 0 mut
:begin
  sizeOf: blockBytes = math.multiplyInt64(bytes, four=4)
  moreOf: takeBytes = math.addInt64(blockBytes, four)
  takeCodes: codes = heap.take(takeBytes)
  findCode: codeSlot = kernel.stateAt(codeAt)
  goto eachCode
:eachCode loop=while max=bytes
  doneCheck: done = compare.greaterOrEqualInt64(at, bytes)
  if done finish readOne
:readOne in=eachCode
  decodeIt: taken = values.decodeAt(text, bytes, at, codeSlot)
  readCode: code = machine.loadInt64(codeSlot)
  invalidCheck: invalid = compare.lessThanInt64(code, zero=0)
  if invalid escapeByte keepCode
:escapeByte in=eachCode
  findByte: place = machine.offset(text, at)
  readByte: byte = machine.loadByte(place)
  widenByte: byteValue = convert.byteToInt64(byte)
  escapeIt: escaped = math.addInt64(byteValue, escapeBase=56320)
  storeEscaped: storeCode(codes, made, escaped)
  nextByte: afterByte = math.addInt64(at, one=1)
  set at afterByte
  goto counted
:keepCode in=eachCode
  storeIt: storeCode(codes, made, code)
  nextCode: afterCode = math.addInt64(at, taken)
  set at afterCode
  goto counted
:counted in=eachCode
  moreMade: afterMade = math.addInt64(made, one)
  set made afterMade
  goto eachCode
:finish
  storeCount: machine.storeInt64(count, made)
  return codes

op storeCode "Store a code point at a position of a block of 32-bit code points"
  input codes machine.Address copied
  input at Int64 copied
  input code Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  offsetOf: offset = math.multiplyInt64(at, four=4)
  findCode: place = machine.offset(codes, offset)
  narrowIt: narrow = convert.int64ToInt32(code)
  storeIt: machine.storeInt32(place, narrow)
  return

op addCode "Add a code point to a builder in UTF-8, a surrogate as the three bytes it would take (as Python's str holds it)"
  input builder machine.Address copied
  input code Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  oneCheck: oneByte = compare.lessThanInt64(code, n128=128)
  if oneByte addOne twoCheck
:addOne
  narrowOne: byteOne = convert.int64ToByte(code)
  addFirst: wide.builderAddByte(builder, byteOne)
  return
:twoCheck
  checkTwo: twoBytes = compare.lessThanInt64(code, n2048=2048)
  if twoBytes addTwo threeCheck
:addTwo
  highTwo: twoHigh = bits.shiftRightInt64(code, six=6)
  leadTwo: twoLead = bits.orInt64(twoHigh, n192=192)
  addTwoLead: addByteValue(builder, twoLead)
  addTwoLast: addTrail(builder, code, zero=0)
  return
:threeCheck
  checkThree: threeBytes = compare.lessThanInt64(code, n65536=65536)
  if threeBytes addThree addFour
:addThree
  highThree: threeHigh = bits.shiftRightInt64(code, twelve=12)
  leadThree: threeLead = bits.orInt64(threeHigh, n224=224)
  addThreeLead: addByteValue(builder, threeLead)
  addThreeMiddle: addTrail(builder, code, six)
  addThreeLast: addTrail(builder, code, zero)
  return
:addFour
  highFour: fourHigh = bits.shiftRightInt64(code, eighteen=18)
  leadFour: fourLead = bits.orInt64(fourHigh, n240=240)
  addFourLead: addByteValue(builder, fourLead)
  addFourFirst: addTrail(builder, code, twelve)
  addFourSecond: addTrail(builder, code, six)
  addFourLast: addTrail(builder, code, zero)
  return

op addByteValue "Add a byte given as a whole number to a builder"
  input builder machine.Address copied
  input value Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  narrowIt: byte = convert.int64ToByte(value)
  addIt: wide.builderAddByte(builder, byte)
  return

op addTrail "Add a UTF-8 continuation byte of a code point's six bits from a shift"
  input builder machine.Address copied
  input code Int64 copied
  input shift Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  shiftIt: shifted = bits.shiftRightInt64(code, shift)
  maskIt: six = bits.andInt64(shifted, n63=63)
  markIt: marked = bits.orInt64(six, n128=128)
  addIt: addByteValue(builder, marked)
  return

op replaced "Text as host.py reads it with decode(\"utf-8\", \"replace\"): valid UTF-8 kept, each part that is not U+FFFD, in a new builder"
  input text machine.Address copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let replacement String "\xef\xbf\xbd"
:begin
  makeIt: builder = wide.builderNew()
  findCode: codeSlot = kernel.stateAt(codeAt)
  goto eachCode
:eachCode loop=while max=bytes
  doneCheck: done = compare.greaterOrEqualInt64(at, bytes)
  if done finish readOne
:readOne in=eachCode
  decodeIt: taken = values.decodeAt(text, bytes, at, codeSlot)
  readCode: code = machine.loadInt64(codeSlot)
  invalidCheck: invalid = compare.lessThanInt64(code, zero=0)
  if invalid addReplacement keep
:addReplacement in=eachCode
  findReplacement: replacementAt = machine.addressOfString(replacement)
  addMark: wide.builderAdd(builder, replacementAt, three=3)
  goto advance
:keep in=eachCode
  findPart: part = machine.offset(text, at)
  addPart: wide.builderAdd(builder, part, taken)
  goto advance
:advance in=eachCode
  nextAt: after = math.addInt64(at, taken)
  set at after
  goto eachCode
:finish
  return builder

op giveBuilder "Give back a builder and its bytes"
  input builder machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readText: text = wide.builderText(builder)
  giveText: heap.give(text)
  giveIt: heap.give(builder)
  return

op textNode "A text value that takes over a builder's bytes; the builder itself is given back"
  input builder machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  makeNode: node = values.newValue(kindText)
  readText: text = wide.builderText(builder)
  readLength: bytes = wide.builderLength(builder)
  textAddress: textAt = machine.toInt64(text)
  storeText: setWord(node, sixteen=16, textAt)
  storeLength: setWord(node, twentyFour=24, bytes)
  giveIt: heap.give(builder)
  return node

## ---------------------------------------------------------------- reading

op fail "Note a parse error (1 invalidAt with its position, 2 tooDeep) and give the address 0"
  input kind Int64 copied
  input position Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  storeKind: setStateWord(errorAt, kind)
  storePosition: setStateWord(positionAt, position)
  nowhere: anywhere = machine.zero()
  return anywhere

op isWhite "Whether a code point is JSON's white space: space, tab, line feed, carriage return"
  input code Int64 copied
  output Bool
:begin
  spaceCheck: isSpace = compare.equalInt64(code, space=32)
  tabCheck: isTab = compare.equalInt64(code, tab=9)
  lineCheck: isLine = compare.equalInt64(code, lineFeed=10)
  returnCheck: isReturn = compare.equalInt64(code, carriageReturn=13)
  firstPair: spaceOrTab = logic.or(isSpace, isTab)
  secondPair: lineOrReturn = logic.or(isLine, isReturn)
  either: white = logic.or(spaceOrTab, lineOrReturn)
  return white

op skipWhite "The first position from one that is not white space, or the end"
  input codes machine.Address copied
  input count Int64 copied
  input from Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  set at from
  goto eachCode
:eachCode loop=while max=count
  endCheck: atEnd = compare.greaterOrEqualInt64(at, count)
  if atEnd give readOne
:readOne in=eachCode
  readCode: code = codeOf(codes, at)
  whiteCheck: white = isWhite(code)
  if white advance give
:advance in=eachCode
  nextAt: after = math.addInt64(at, one=1)
  set at after
  goto eachCode
:give
  return at

op codeIs "Whether a position is inside the text and holds a code point"
  input codes machine.Address copied
  input count Int64 copied
  input at Int64 copied
  input wanted Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let no Bool false
:begin
  insideCheck: inside = compare.lessThanInt64(at, count)
  if inside readIt outside
:outside
  return no
:readIt
  readCode: code = codeOf(codes, at)
  sameCheck: same = compare.equalInt64(code, wanted)
  return same

op wordAt "Whether the code points from a position spell an ASCII word, all of them inside the text"
  input codes machine.Address copied
  input count Int64 copied
  input at Int64 copied
  input spelled String borrowed
  output Bool
  effect use machine.memory
  uses memoryAccess
  let k Int64 0 mut
  let yes Bool true
  let no Bool false
:begin
  wordLength: length = string.byteLength(spelled)
  endOf: end = math.addInt64(at, length)
  fitsCheck: fits = compare.lessOrEqualInt64(end, count)
  if fits eachCode differ
:eachCode loop=while max=length
  doneCheck: done = compare.greaterOrEqualInt64(k, length)
  if done same compareOne
:compareOne in=eachCode
  placeOf: place = math.addInt64(at, k)
  readCode: code = codeOf(codes, place)
  findWord: wordStart = machine.addressOfString(spelled)
  findByte: byteAt = machine.offset(wordStart, k)
  readByte: byte = machine.loadByte(byteAt)
  widenByte: wanted = convert.byteToInt64(byte)
  equalCheck: equal = compare.equalInt64(code, wanted)
  if equal advance differ
:advance in=eachCode
  nextK: afterK = math.addInt64(k, one=1)
  set k afterK
  goto eachCode
:same
  return yes
:differ
  return no

op isDigit "Whether a code point is an ASCII digit"
  input code Int64 copied
  output Bool
:begin
  lowCheck: aboveZero = compare.greaterOrEqualInt64(code, digitZero=48)
  highCheck: belowNine = compare.lessOrEqualInt64(code, digitNine=57)
  bothCheck: digit = logic.and(aboveZero, belowNine)
  return digit

op digitAt "Whether a position is inside the text and holds an ASCII digit"
  input codes machine.Address copied
  input count Int64 copied
  input at Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let no Bool false
:begin
  insideCheck: inside = compare.lessThanInt64(at, count)
  if inside readIt outside
:outside
  return no
:readIt
  readCode: code = codeOf(codes, at)
  digitCheck: digit = isDigit(code)
  return digit

op skipDigits "The first position from one that does not hold a digit, or the end"
  input codes machine.Address copied
  input count Int64 copied
  input from Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  set at from
  goto eachCode
:eachCode loop=while max=count
  digitCheck: digit = digitAt(codes, count, at)
  if digit advance give
:advance in=eachCode
  nextAt: after = math.addInt64(at, one=1)
  set at after
  goto eachCode
:give
  return at

op hexOf "The value of four hexadecimal digits from a position (all inside the text), or -1 when one is not a digit"
  input codes machine.Address copied
  input at Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let k Int64 0 mut
  let value Int64 0 mut
  let bad Int64 -1
:begin
  goto eachDigit
:eachDigit loop=while max=4
  doneCheck: done = compare.greaterOrEqualInt64(k, four=4)
  if done give readDigit
:readDigit in=eachDigit
  placeOf: place = math.addInt64(at, k)
  readCode: code = codeOf(codes, place)
  shiftValue: shifted = bits.shiftLeftInt64(value, four)
  decimalCheck: decimal = isDigit(code)
  if decimal addDecimal lowerCheck
:addDecimal in=eachDigit
  decimalOf: decimalValue = math.subtractInt64(code, digitZero=48)
  addIt: withDecimal = math.addInt64(shifted, decimalValue)
  set value withDecimal
  goto advance
:lowerCheck in=eachDigit
  lowA: aboveSmallA = compare.greaterOrEqualInt64(code, smallA=97)
  lowF: belowSmallF = compare.lessOrEqualInt64(code, smallF=102)
  lowBoth: isLower = logic.and(aboveSmallA, belowSmallF)
  if isLower addLower upperCheck
:addLower in=eachDigit
  lowerOf: lowerValue = math.subtractInt64(code, n87=87)
  addLowerIt: withLower = math.addInt64(shifted, lowerValue)
  set value withLower
  goto advance
:upperCheck in=eachDigit
  upA: aboveA = compare.greaterOrEqualInt64(code, capitalA=65)
  upF: belowF = compare.lessOrEqualInt64(code, capitalF=70)
  upBoth: isUpper = logic.and(aboveA, belowF)
  if isUpper addUpper giveBad
:addUpper in=eachDigit
  upperOf: upperValue = math.subtractInt64(code, n55=55)
  addUpperIt: withUpper = math.addInt64(shifted, upperValue)
  set value withUpper
  goto advance
:advance in=eachDigit
  nextK: afterK = math.addInt64(k, one=1)
  set k afterK
  goto eachDigit
:giveBad
  return bad
:give
  return value

op escapeOf "The code point a backslash escape other than `u` stands for, or -1"
  input code Int64 copied
  output Int64
  let quote Int64 34
  let backslash Int64 92
  let slash Int64 47
  let bad Int64 -1
  let backspace Int64 8
  let formFeed Int64 12
  let lineFeed Int64 10
  let carriageReturn Int64 13
  let tab Int64 9
:begin
  quoteCheck: isQuote = compare.equalInt64(code, quote)
  if isQuote giveQuote backslashCheck
:giveQuote
  return quote
:backslashCheck
  checkBackslash: isBackslash = compare.equalInt64(code, backslash)
  if isBackslash giveBackslash slashCheck
:giveBackslash
  return backslash
:slashCheck
  checkSlash: isSlash = compare.equalInt64(code, slash)
  if isSlash giveSlash bCheck
:giveSlash
  return slash
:bCheck
  checkB: isB = compare.equalInt64(code, smallB=98)
  if isB giveB fCheck
:giveB
  return backspace
:fCheck
  checkF: isF = compare.equalInt64(code, smallF=102)
  if isF giveF nCheck
:giveF
  return formFeed
:nCheck
  checkN: isN = compare.equalInt64(code, smallN=110)
  if isN giveN rCheck
:giveN
  return lineFeed
:rCheck
  checkR: isR = compare.equalInt64(code, smallR=114)
  if isR giveR tCheck
:giveR
  return carriageReturn
:tCheck
  checkT: isT = compare.equalInt64(code, smallT=116)
  if isT giveT giveBad
:giveT
  return tab
:giveBad
  return bad

op readString "A string from just after its opening quote, as CPython's scanstring_unicode reads it (strict): a text value, the scanner going on after the closing quote, or the address 0 with the error noted"
  input codes machine.Address copied
  input count Int64 copied
  input start Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let next Int64 0 mut
  let end Int64 0 mut
  let code Int64 0 mut
  let invalid Int64 1
  let quote Int64 34
  let backslash Int64 92
  let smallU Int64 117
:begin
  openingOf: opening = math.subtractInt64(start, one=1)
  makeText: builder = wide.builderNew()
  set end start
  goto eachChunk
:eachChunk loop=while max=forever
  set next end
  goto scanChunk
:scanChunk in=eachChunk
  goto eachCode
:eachCode loop=while max=count in=eachChunk
  endCheck: atEnd = compare.greaterOrEqualInt64(next, count)
  if atEnd unterminated readOne
:readOne in=eachCode
  readCode: current = codeOf(codes, next)
  quoteCheck: isQuote = compare.equalInt64(current, quote)
  backslashCheck: isBackslash = compare.equalInt64(current, backslash)
  stopCheck: stop = logic.or(isQuote, isBackslash)
  if stop stopped controlCheck
:controlCheck in=eachCode
  checkControl: isControl = compare.lessOrEqualInt64(current, n31=31)
  if isControl controlFound keepCode
:keepCode in=eachCode
  addIt: addCode(builder, current)
  nextCode: afterCode = math.addInt64(next, one)
  set next afterCode
  goto eachCode
:stopped in=eachChunk
  readStop: stopCode = codeOf(codes, next)
  pastStop: afterStop = math.addInt64(next, one)
  set next afterStop
  closedCheck: closed = compare.equalInt64(stopCode, quote)
  if closed finish escape
:escape in=eachChunk
  lastCheck: atLast = compare.equalInt64(next, count)
  if atLast unterminated readEscape
:readEscape in=eachChunk
  readKind: escaped = codeOf(codes, next)
  unicodeCheck: isUnicode = compare.equalInt64(escaped, smallU)
  if isUnicode unicodeEscape simpleEscape
:simpleEscape in=eachChunk
  afterEscape: simpleEnd = math.addInt64(next, one)
  set end simpleEnd
  meaningOf: meaning = escapeOf(escaped)
  badCheck: isBad = compare.lessThanInt64(meaning, zero=0)
  if isBad badEscape addMeaningBlock
:addMeaningBlock in=eachChunk
  addMeaning: addCode(builder, meaning)
  goto eachChunk
:badEscape
  backslashAt: escapeStart = math.subtractInt64(end, two=2)
  failEscape: badEscapeResult = fail(invalid, escapeStart)
  giveEscape: giveBuilder(builder)
  return badEscapeResult
:unicodeEscape in=eachChunk
  afterU: digitsStart = math.addInt64(next, one)
  set next digitsStart
  endOfDigits: digitsEnd = math.addInt64(digitsStart, four=4)
  set end digitsEnd
  shortCheck: short = compare.greaterOrEqualInt64(digitsEnd, count)
  if short shortEscape readHex
:shortEscape
  uPlaceOf: shortAt = math.subtractInt64(digitsStart, one)
  failShort: shortResult = fail(invalid, shortAt)
  giveShort: giveBuilder(builder)
  return shortResult
:readHex in=eachChunk
  hexIt: value = hexOf(codes, digitsStart)
  hexBadCheck: hexBad = compare.lessThanInt64(value, zero)
  if hexBad badHex pairCheck
:badHex
  badHexAt: hexAt = math.subtractInt64(end, five=5)
  failHex: hexResult = fail(invalid, hexAt)
  giveHex: giveBuilder(builder)
  return hexResult
:pairCheck in=eachChunk
  set code value
  set next end
  highLow: aboveHigh = compare.greaterOrEqualInt64(value, highFirst=55296)
  highHigh: belowHigh = compare.lessOrEqualInt64(value, highLast=56319)
  highCheck: isHigh = logic.and(aboveHigh, belowHigh)
  if isHigh roomCheck addUnicode
:roomCheck in=eachChunk
  pairEnd: sixOn = math.addInt64(end, six=6)
  roomFits: hasRoom = compare.lessThanInt64(sixOn, count)
  if hasRoom secondBackslash addUnicode
:secondBackslash in=eachChunk
  backslashThere: isSecondBackslash = codeIs(codes, count, end, backslash)
  if isSecondBackslash secondU addUnicode
:secondU in=eachChunk
  uPlace: uAt = math.addInt64(end, one)
  uThere: isSecondU = codeIs(codes, count, uAt, smallU)
  if isSecondU readSecond addUnicode
:readSecond in=eachChunk
  secondStart: secondDigits = math.addInt64(end, two)
  secondHex: low = hexOf(codes, secondDigits)
  set end sixOn
  secondBadCheck: secondBad = compare.lessThanInt64(low, zero)
  if secondBad badSecond lowCheck
:badSecond
  badSecondAt: secondAt = math.subtractInt64(end, five)
  failSecond: secondResult = fail(invalid, secondAt)
  giveSecond: giveBuilder(builder)
  return secondResult
:lowCheck in=eachChunk
  lowLow: aboveLow = compare.greaterOrEqualInt64(low, lowFirst=56320)
  lowHigh: belowLow = compare.lessOrEqualInt64(low, lowLast=57343)
  isLowCheck: isLow = logic.and(aboveLow, belowLow)
  if isLow join unjoined
:join in=eachChunk
  highBits: highPart = math.subtractInt64(value, highFirst)
  shiftHigh: shifted = bits.shiftLeftInt64(highPart, ten=10)
  lowBits: lowPart = math.subtractInt64(low, lowFirst)
  joinBits: joined = bits.orInt64(shifted, lowPart)
  addBase: full = math.addInt64(joined, n65536=65536)
  set code full
  goto addUnicode
:unjoined in=eachChunk
  backSix: unjoinedEnd = math.subtractInt64(end, six)
  set end unjoinedEnd
  goto addUnicode
:addUnicode in=eachChunk
  addValue: addCode(builder, code)
  goto eachChunk
:controlFound
  failControl: controlResult = fail(invalid, next)
  giveControl: giveBuilder(builder)
  return controlResult
:unterminated
  failOpen: openResult = fail(invalid, opening)
  giveOpen: giveBuilder(builder)
  return openResult
:finish
  storeNext: setStateWord(scannedAt, next)
  makeNode: node = textNode(builder)
  return node

op wholeNode "A whole number from its digits (an optional minus and ASCII digits): an Int64 when it fits, else kept as its text; more digits than Python's int() reads traps as it refuses them"
  input codes machine.Address copied
  input start Int64 copied
  input end Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let digits Int64 0 mut
:begin
  makeText: builder = wide.builderNew()
  set at start
  goto eachCode
:eachCode loop=while max=end
  doneCheck: done = compare.greaterOrEqualInt64(at, end)
  if done read addOne
:addOne in=eachCode
  readCode: code = codeOf(codes, at)
  addIt: addCode(builder, code)
  nextAt: after = math.addInt64(at, one=1)
  set at after
  goto eachCode
:read
  readText: text = wide.builderText(builder)
  readLength: bytes = wide.builderLength(builder)
  set digits bytes
  readFirst: first = machine.loadByte(text)
  minusCheck: isMinus = compare.equalByte(first, minus=45)
  if isMinus lessOne limitCheck
:lessOne
  withoutMinus: unsigned = math.subtractInt64(bytes, one)
  set digits unsigned
  goto limitCheck
:limitCheck
  tooManyCheck: tooMany = compare.greaterThanInt64(digits, mostDigits)
  if tooMany refuse parse
:refuse
  makeMessage: message = wide.builderNew()
  addStart: addText(message, startText="`json.parse` failed inside the runtime: ValueError('Exceeds the limit (4300 digits) for integer string conversion: value has ")
  addCount: addNumber(message, digits)
  addEnd: addText(message, endText=" digits; use sys.set_int_max_str_digits() to increase the limit')")
  failIt: failBuilt(message)
  nowhere: anywhere = machine.zero()
  return anywhere
:parse
  findResult: result = kernel.stateAt(digitsAt)
  parseIt: status = numbers.parseDecimal(text, bytes, result)
  fitsCheck: fits = compare.equalInt32(status, zero32=0)
  if fits whole big
:whole
  loadValue: value = machine.loadInt64(result)
  makeWhole: wholeValue = values.newValue(kindWhole)
  storeValue: setWord(wholeValue, sixteen=16, value)
  giveIt: giveBuilder(builder)
  return wholeValue
:big
  makeBig: bigValue = textNode(builder)
  storeKind: setWord(bigValue, eight=8, kindBig)
  return bigValue

op floatNode "A Float64 from its text, correctly rounded as float() reads it; past the largest is infinity of its sign"
  input codes machine.Address copied
  input start Int64 copied
  input end Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let bitsValue UInt64 0 mut
  let positiveInfinity UInt64 9218868437227405312
  let negativeInfinity UInt64 18442240474082181120
:begin
  makeText: builder = wide.builderNew()
  set at start
  goto eachCode
:eachCode loop=while max=end
  doneCheck: done = compare.greaterOrEqualInt64(at, end)
  if done read addOne
:addOne in=eachCode
  readCode: code = codeOf(codes, at)
  addIt: addCode(builder, code)
  nextAt: after = math.addInt64(at, one=1)
  set at after
  goto eachCode
:read
  readText: text = wide.builderText(builder)
  readLength: bytes = wide.builderLength(builder)
  findResult: result = kernel.stateAt(floatTextAt)
  parseIt: status = floats.parseFloat(text, bytes, result)
  largeCheck: large = compare.equalInt32(status, two32=2)
  if large infinite finite
:finite
  loadValue: value = machine.loadUInt64(result)
  set bitsValue value
  goto make
:infinite
  set bitsValue positiveInfinity
  readFirst: first = machine.loadByte(text)
  minusCheck: isMinus = compare.equalByte(first, minus=45)
  if isMinus negative make
:negative
  set bitsValue negativeInfinity
  goto make
:make
  giveIt: giveBuilder(builder)
  makeFloat: node = values.newValue(kindFloat)
  asWhole: stored = convert.uint64BitsToInt64(bitsValue)
  storeValue: setWord(node, sixteen=16, stored)
  return node

op constantFloat "A Float64 value of the bits of NaN or an infinity, the scanner going on after its name"
  input bitsValue Int64 copied
  input next Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  makeFloat: node = values.newValue(kindFloat)
  storeValue: setWord(node, sixteen=16, bitsValue)
  storeNext: setStateWord(scannedAt, next)
  return node

op readNumber "A number from a position as CPython's _match_number_unicode reads it: a minus, digits with no leading zero, a fraction only before a digit, an exponent only with a digit (else left for what follows); the address 0 with invalidAt its start when there are no digits"
  input codes machine.Address copied
  input count Int64 copied
  input start Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let isFloat Bool false mut
  let yes Bool true
  let invalid Int64 1
  let minus Int64 45
  let digitZero Int64 48
  let point Int64 46
:begin
  lastOf: endIndex = math.subtractInt64(count, one=1)
  set at start
  minusCheck: isMinus = codeIs(codes, count, start, minus)
  if isMinus afterMinus integer
:afterMinus
  pastMinus: afterSign = math.addInt64(start, one)
  set at afterSign
  pastEndCheck: pastEnd = compare.greaterThanInt64(afterSign, endIndex)
  if pastEnd noDigits integer
:integer
  readFirst: first = codeOf(codes, at)
  zeroCheck: isZero = compare.equalInt64(first, digitZero)
  if isZero afterZero nonZeroCheck
:afterZero
  pastZero: afterZeroAt = math.addInt64(at, one)
  set at afterZeroAt
  goto fraction
:nonZeroCheck
  digitCheck: isDigit1 = isDigit(first)
  if isDigit1 digitsRun noDigits
:digitsRun
  pastFirst: afterFirst = math.addInt64(at, one)
  runEnd: afterRun = skipDigits(codes, count, afterFirst)
  set at afterRun
  goto fraction
:fraction
  beforeEndCheck: beforeEnd = compare.lessThanInt64(at, endIndex)
  if beforeEnd pointCheck exponent
:pointCheck
  isPointCheck: isPoint = codeIs(codes, count, at, point)
  if isPoint pointDigit exponent
:pointDigit
  afterPoint: fractionAt = math.addInt64(at, one)
  fractionDigit: hasDigit = digitAt(codes, count, fractionAt)
  if hasDigit fractionRun exponent
:fractionRun
  set isFloat yes
  pastPoint: fractionStart = math.addInt64(at, two=2)
  fractionEnd: afterFraction = skipDigits(codes, count, fractionStart)
  set at afterFraction
  goto exponent
:exponent
  expRoom: expBeforeEnd = compare.lessThanInt64(at, endIndex)
  if expBeforeEnd expCheck finish
:expCheck
  smallECheck: isSmallE = codeIs(codes, count, at, smallE=101)
  bigECheck: isBigE = codeIs(codes, count, at, bigE=69)
  eitherE: isE = logic.or(isSmallE, isBigE)
  if isE expSign finish
:expSign
  pastE: afterE = math.addInt64(at, one)
  signRoom: signBeforeEnd = compare.lessThanInt64(afterE, endIndex)
  if signBeforeEnd signCheck expDigits
:signCheck
  minusSign: isMinusSign = codeIs(codes, count, afterE, minus)
  plusSign: isPlusSign = codeIs(codes, count, afterE, plus=43)
  eitherSign: isSign = logic.or(isMinusSign, isPlusSign)
  if isSign skipSign expDigits
:skipSign
  pastSign: afterSignE = math.addInt64(afterE, one)
  expAfterSign: signDigitsEnd = skipDigits(codes, count, afterSignE)
  lastDigitSigned: lastSigned = math.subtractInt64(signDigitsEnd, one)
  signedDigitCheck: signedDigit = digitAt(codes, count, lastSigned)
  if signedDigit takeSigned finish
:takeSigned
  set at signDigitsEnd
  set isFloat yes
  goto finish
:expDigits
  expEnd: expDigitsEnd = skipDigits(codes, count, afterE)
  lastDigit: lastExp = math.subtractInt64(expDigitsEnd, one)
  expDigitCheck: expDigit = digitAt(codes, count, lastExp)
  if expDigit takeExp finish
:takeExp
  set at expDigitsEnd
  set isFloat yes
  goto finish
:finish
  storeNext: setStateWord(scannedAt, at)
  if isFloat makeFloat makeWhole
:makeFloat
  floatIt: floatValue = floatNode(codes, start, at)
  return floatValue
:makeWhole
  wholeIt: wholeValue = wholeNode(codes, start, at)
  return wholeValue
:noDigits
  failIt: failed = fail(invalid, start)
  return failed

op readValue "A JSON value from a position as CPython's scan_once_unicode reads it: the value, the scanner going on after it (machine.state), or the address 0 with the error noted; arrays and objects read their items in turn, nested no deeper than CPython lets them"
  input codes machine.Address copied
  input count Int64 copied
  input at Int64 copied
  input depth Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  recursion 2996
  let i Int64 0 mut
  let invalid Int64 1
  let deep Int64 2
  let quote Int64 34
  let openArray Int64 91
  let closeArray Int64 93
  let openObject Int64 123
  let closeObject Int64 125
  let comma Int64 44
  let colon Int64 58
  let nullWord String "null"
  let trueWord String "true"
  let falseWord String "false"
  let nanWord String "NaN"
  let infinityWord String "Infinity"
  let minusInfinityWord String "-Infinity"
  let nanBits Int64 9221120237041090560
  let infinityBits Int64 9218868437227405312
  let minusInfinityBits Int64 -4503599627370496
:begin
  endCheck: atEnd = compare.greaterOrEqualInt64(at, count)
  if atEnd expecting readFirst
:expecting
  failExpecting: expectingResult = fail(invalid, at)
  return expectingResult
:readFirst
  readCode: first = codeOf(codes, at)
  afterFirst: next = math.addInt64(at, one=1)
  quoteCheck: isQuote = compare.equalInt64(first, quote)
  if isQuote string arrayCheck
:string
  readIt: text = readString(codes, count, next)
  return text
:arrayCheck
  checkArray: isArray = compare.equalInt64(first, openArray)
  if isArray arrayDepth objectCheck
:arrayDepth
  arrayDeeper: arrayDepthNow = math.addInt64(depth, one)
  arrayTooDeep: arrayDeep = compare.greaterThanInt64(arrayDepthNow, deepest)
  if arrayDeep failDeep array
:array
  makeArray: list = values.newValue(kindArray)
  firstItem: itemAt = skipWhite(codes, count, next)
  set i itemAt
  emptyCheck: isEmpty = codeIs(codes, count, itemAt, closeArray)
  if isEmpty closeList eachItem
:eachItem loop=while max=forever
  readItem: item = readValue(codes, count, i, arrayDepthNow)
  nowhere: anywhere = machine.zero()
  itemFailed: noItem = machine.equal(item, anywhere)
  if noItem dropList addItem
:addItem in=eachItem
  appendIt: values.appendItem(list, item)
  readNext: afterItem = stateWord(scannedAt)
  delimiter: delimiterAt = skipWhite(codes, count, afterItem)
  set i delimiterAt
  closeCheck: closes = codeIs(codes, count, delimiterAt, closeArray)
  if closes closeList commaCheck
:commaCheck in=eachItem
  isCommaCheck: isComma = codeIs(codes, count, delimiterAt, comma)
  if isComma nextItem badList
:nextItem in=eachItem
  pastComma: afterComma = math.addInt64(delimiterAt, one)
  nextItemAt: nextAt2 = skipWhite(codes, count, afterComma)
  set i nextAt2
  goto eachItem
:badList
  failList: listResult = fail(invalid, i)
  dropBadList: listFreed = values.release(list)
  return listResult
:dropList
  dropFailed: failedFreed = values.release(list)
  return item
:closeList
  pastClose: afterList = math.addInt64(i, one)
  storeListNext: setStateWord(scannedAt, afterList)
  return list
:objectCheck
  checkObject: isObject = compare.equalInt64(first, openObject)
  if isObject objectDepth literals
:objectDepth
  objectDeeper: objectDepthNow = math.addInt64(depth, one)
  objectTooDeep: objectDeep = compare.greaterThanInt64(objectDepthNow, deepest)
  if objectDeep failDeep object
:object
  makeObject: fields = values.newValue(kindObject)
  firstKey: keyAt = skipWhite(codes, count, next)
  set i keyAt
  emptyObjectCheck: isEmptyObject = codeIs(codes, count, keyAt, closeObject)
  if isEmptyObject closeObjectBlock eachField
:eachField loop=while max=forever
  keyQuoteCheck: hasQuote = codeIs(codes, count, i, quote)
  if hasQuote readKey badName
:readKey in=eachField
  afterQuote: keyStart = math.addInt64(i, one)
  readName: key = readString(codes, count, keyStart)
  nowhereKey: noAddress = machine.zero()
  keyFailed: noKey = machine.equal(key, noAddress)
  if noKey dropObject colonCheck
:colonCheck in=eachField
  readAfterKey: afterKey = stateWord(scannedAt)
  colonAt: colonPlace = skipWhite(codes, count, afterKey)
  set i colonPlace
  isColonCheck: isColon = codeIs(codes, count, colonPlace, colon)
  if isColon readField badColon
:readField in=eachField
  pastColon: afterColon = math.addInt64(colonPlace, one)
  valueAt: valuePlace = skipWhite(codes, count, afterColon)
  readFieldValue: fieldValue = readValue(codes, count, valuePlace, objectDepthNow)
  fieldFailed: noValue = machine.equal(fieldValue, noAddress)
  if noValue dropKeyAndObject putIt
:putIt in=eachField
  readKeyText: keyTextAt = word(key, sixteen=16)
  keyAddress: keyText = machine.fromInt64(keyTextAt)
  readKeyBytes: keyBytes = word(key, twentyFour=24)
  putField: values.putField(fields, keyText, keyBytes, fieldValue)
  letKeyGo: keyFreed = values.release(key)
  readAfterValue: afterValue = stateWord(scannedAt)
  fieldDelimiter: fieldDelimiterAt = skipWhite(codes, count, afterValue)
  set i fieldDelimiterAt
  closeObjectCheck: closesObject = codeIs(codes, count, fieldDelimiterAt, closeObject)
  if closesObject closeObjectBlock fieldCommaCheck
:fieldCommaCheck in=eachField
  isFieldCommaCheck: isFieldComma = codeIs(codes, count, fieldDelimiterAt, comma)
  if isFieldComma nextField badObject
:nextField in=eachField
  pastFieldComma: afterFieldComma = math.addInt64(fieldDelimiterAt, one)
  nextFieldAt: nextKeyAt = skipWhite(codes, count, afterFieldComma)
  set i nextKeyAt
  goto eachField
:badName
  failName: nameResult = fail(invalid, i)
  dropNamed: nameFreed = values.release(fields)
  return nameResult
:badColon
  failColon: colonResult = fail(invalid, i)
  dropColonKey: colonKeyFreed = values.release(key)
  dropColonObject: colonFreed = values.release(fields)
  return colonResult
:badObject
  failObject: objectResult = fail(invalid, i)
  dropBadObject: badFreed = values.release(fields)
  return objectResult
:dropKeyAndObject
  dropValueKey: valueKeyFreed = values.release(key)
  dropValueObject: valueObjectFreed = values.release(fields)
  return fieldValue
:dropObject
  dropKeyObject: keyObjectFreed = values.release(fields)
  return key
:closeObjectBlock
  pastObject: afterObject = math.addInt64(i, one)
  storeObjectNext: setStateWord(scannedAt, afterObject)
  return fields
:failDeep
  failDeepNow: deepResult = fail(deep, at)
  return deepResult
:literals
  nullCheck: isNull = wordAt(codes, count, at, nullWord)
  if isNull giveNull trueCheck
:giveNull
  makeNull: nullValue = values.newValue(kindNull)
  nullEnd: afterNull = math.addInt64(at, four=4)
  storeNullNext: setStateWord(scannedAt, afterNull)
  return nullValue
:trueCheck
  checkTrue: isTrue = wordAt(codes, count, at, trueWord)
  if isTrue giveTrue falseCheck
:giveTrue
  makeTrue: trueValue = values.newValue(kindBoolean)
  storeTrue: setWord(trueValue, sixteen, one)
  trueEnd: afterTrue = math.addInt64(at, four)
  storeTrueNext: setStateWord(scannedAt, afterTrue)
  return trueValue
:falseCheck
  checkFalse: isFalse = wordAt(codes, count, at, falseWord)
  if isFalse giveFalse nanCheck
:giveFalse
  makeFalse: falseValue = values.newValue(kindBoolean)
  falseEnd: afterFalse = math.addInt64(at, five=5)
  storeFalseNext: setStateWord(scannedAt, afterFalse)
  return falseValue
:nanCheck
  checkNan: isNan = wordAt(codes, count, at, nanWord)
  if isNan giveNan infinityCheck
:giveNan
  nanEnd: afterNan = math.addInt64(at, three=3)
  makeNan: nanValue = constantFloat(nanBits, afterNan)
  return nanValue
:infinityCheck
  checkInfinity: isInfinity = wordAt(codes, count, at, infinityWord)
  if isInfinity giveInfinity minusInfinityCheck
:giveInfinity
  infinityEnd: afterInfinity = math.addInt64(at, eight=8)
  makeInfinity: infinityValue = constantFloat(infinityBits, afterInfinity)
  return infinityValue
:minusInfinityCheck
  checkMinusInfinity: isMinusInfinity = wordAt(codes, count, at, minusInfinityWord)
  if isMinusInfinity giveMinusInfinity number
:giveMinusInfinity
  minusInfinityEnd: afterMinusInfinity = math.addInt64(at, nine=9)
  makeMinusInfinity: minusInfinityValue = constantFloat(minusInfinityBits, afterMinusInfinity)
  return minusInfinityValue
:number
  readIt2: numberValue = readNumber(codes, count, at)
  return numberValue

op parseDocument "A whole text as json.loads reads it: its value, or the address 0 with the error noted (a leading U+FEFF, a value that is not there, or anything but white space after it is invalidAt)"
  input text machine.Address copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let invalid Int64 1
:begin
  findCount: countSlot = kernel.stateAt(codeAt)
  decodeIt: codes = decodeInput(text, bytes, countSlot)
  readCount: count = machine.loadInt64(countSlot)
  bomCheck: hasBom = codeIs(codes, count, zero=0, bom=65279)
  if hasBom failBom read
:failBom
  failAtStart: bomResult = fail(invalid, zero)
  giveBomCodes: heap.give(codes)
  return bomResult
:read
  startOf: start = skipWhite(codes, count, zero)
  readIt: value = readValue(codes, count, start, zero)
  nowhere: anywhere = machine.zero()
  failedCheck: failed = machine.equal(value, anywhere)
  if failed giveFailed extraCheck
:giveFailed
  giveFailedCodes: heap.give(codes)
  return value
:extraCheck
  readNext: after = stateWord(scannedAt)
  endOf: end = skipWhite(codes, count, after)
  allCheck: all = compare.equalInt64(end, count)
  if all give extra
:extra
  failExtra: extraResult = fail(invalid, end)
  dropValue: dropped = values.release(value)
  giveExtraCodes: heap.give(codes)
  return extraResult
:give
  giveCodes: heap.give(codes)
  return value

## ---------------------------------------------------------------- writing

op addEscaped "Add text to a builder between quotes, escaped as CPython's C encoder escapes it with ensure_ascii off: quote, backslash, \\b \\f \\n \\r \\t, other control characters as \\u00XX in lower case; everything else as it is"
  input builder machine.Address copied
  input text machine.Address copied
  input bytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let quote Byte 34
  let backslash Byte 92
  let hexDigits String "0123456789abcdef"
:begin
  addOpen: wide.builderAddByte(builder, quote)
  goto eachByte
:eachByte loop=while max=bytes
  doneCheck: done = compare.greaterOrEqualInt64(at, bytes)
  if done finish readOne
:readOne in=eachByte
  findByte: place = machine.offset(text, at)
  readByte: byte = machine.loadByte(place)
  widen: value = convert.byteToInt64(byte)
  quoteCheck: isQuote = compare.equalByte(byte, quote)
  backslashCheck: isBackslash = compare.equalByte(byte, backslash)
  slashCheck: needsSlash = logic.or(isQuote, isBackslash)
  if needsSlash addSlashed controlCheck
:addSlashed in=eachByte
  addSlash: wide.builderAddByte(builder, backslash)
  addItself: wide.builderAddByte(builder, byte)
  goto advance
:controlCheck in=eachByte
  checkControl: isControl = compare.lessThanInt64(value, n32=32)
  if isControl control plain
:plain in=eachByte
  addPlain: wide.builderAddByte(builder, byte)
  goto advance
:control in=eachByte
  shortOf: short = escapeLetter(value)
  shortCheck: hasShort = compare.greaterThanInt64(short, zero=0)
  if hasShort addShort addLong
:addShort in=eachByte
  addShortSlash: wide.builderAddByte(builder, backslash)
  addLetter: addByteValue(builder, short)
  goto advance
:addLong in=eachByte
  addLongSlash: wide.builderAddByte(builder, backslash)
  addU: addText(builder, uText="u00")
  highOf: high = bits.shiftRightInt64(value, four=4)
  lowOf: low = bits.andInt64(value, fifteen=15)
  findDigits: digitsStart = machine.addressOfString(hexDigits)
  findHigh: highAt = machine.offset(digitsStart, high)
  addHigh: wide.builderAdd(builder, highAt, one=1)
  findLow: lowAt = machine.offset(digitsStart, low)
  addLow: wide.builderAdd(builder, lowAt, one)
  goto advance
:advance in=eachByte
  nextAt: after = math.addInt64(at, one)
  set at after
  goto eachByte
:finish
  addClose: wide.builderAddByte(builder, quote)
  return

op escapeLetter "The letter of a control character's two-character escape (b f n r t), or 0 when it has none"
  input value Int64 copied
  output Int64
  let noLetter Int64 0
  let smallB Int64 98
  let smallF Int64 102
  let smallN Int64 110
  let smallR Int64 114
  let smallT Int64 116
:begin
  bCheck: isB = compare.equalInt64(value, eight=8)
  if isB giveB fCheck
:giveB
  return smallB
:fCheck
  checkF: isF = compare.equalInt64(value, twelve=12)
  if isF giveF nCheck
:giveF
  return smallF
:nCheck
  checkN: isN = compare.equalInt64(value, ten=10)
  if isN giveN rCheck
:giveN
  return smallN
:rCheck
  checkR: isR = compare.equalInt64(value, thirteen=13)
  if isR giveR tCheck
:giveR
  return smallR
:tCheck
  checkT: isT = compare.equalInt64(value, nine=9)
  if isT giveT giveNone
:giveT
  return smallT
:giveNone
  return noLetter

op addFloat "Add a Float64 as json.dumps writes it: NaN, Infinity, -Infinity, or repr"
  input builder machine.Address copied
  input bitsValue Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let positiveInfinity Int64 9218868437227405312
  let negativeInfinity Int64 -4503599627370496
:begin
  wideBits: unsigned = convert.int64BitsToUInt64(bitsValue)
  asFloat: value = convert.uint64BitsToFloat64(unsigned)
  selfCheck: same = compare.equalFloat64(value, value)
  if same infinityCheck addNan
:addNan
  addNanText: addText(builder, nanText="NaN")
  return
:infinityCheck
  checkInfinity: isInfinity = compare.equalInt64(bitsValue, positiveInfinity)
  if isInfinity addInfinity minusCheck
:addInfinity
  addInfinityText: addText(builder, infinityText="Infinity")
  return
:minusCheck
  checkMinus: isMinusInfinity = compare.equalInt64(bitsValue, negativeInfinity)
  if isMinusInfinity addMinusInfinity addShortest
:addMinusInfinity
  addMinusText: addText(builder, minusInfinityText="-Infinity")
  return
:addShortest
  findText: target = kernel.stateAt(floatTextAt)
  writeIt: count = floats.formatFloat(value, target)
  addIt: wide.builderAdd(builder, target, count)
  return

op writeValue "Add a value to a builder as json.dumps writes it with separators (\",\", \":\"); a value that holds itself traps as the encoder refuses it, and so does nesting deeper than it can"
  input builder machine.Address copied
  input node machine.Address copied
  input depth Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  recursion 2996
  let at Int64 0 mut
  let comma Byte 44
  let colon Byte 58
  let target String "json.stringify"
:begin
  readKind: kind = word(node, eight=8)
  nullCheck: isNull = compare.equalInt64(kind, kindNull)
  if isNull addNull booleanCheck
:addNull
  addNullText: addText(builder, nullText="null")
  return
:booleanCheck
  checkBoolean: isBoolean = compare.equalInt64(kind, kindBoolean)
  if isBoolean addBoolean wholeCheck
:addBoolean
  readFlag: flag = word(node, sixteen=16)
  flagCheck: isTrue = compare.notEqualInt64(flag, zero=0)
  if isTrue addTrue addFalse
:addTrue
  addTrueText: addText(builder, trueText="true")
  return
:addFalse
  addFalseText: addText(builder, falseText="false")
  return
:wholeCheck
  checkWhole: isWhole = compare.equalInt64(kind, kindWhole)
  if isWhole addWhole floatCheck
:addWhole
  readWhole: whole = word(node, sixteen)
  addWholeText: addNumber(builder, whole)
  return
:floatCheck
  checkFloat: isFloat = compare.equalInt64(kind, kindFloat)
  if isFloat addFloatValue bigCheck
:addFloatValue
  readBits: floatBits = word(node, sixteen)
  addFloatText: addFloat(builder, floatBits)
  return
:bigCheck
  readBytes: textAt = word(node, sixteen)
  textAddress: text = machine.fromInt64(textAt)
  readLength: bytes = word(node, twentyFour=24)
  checkBig: isBig = compare.equalInt64(kind, kindBig)
  if isBig addBig textCheck
:addBig
  addBigText: wide.builderAdd(builder, text, bytes)
  return
:textCheck
  checkText: isText = compare.equalInt64(kind, kindText)
  if isText addTextValue container
:addTextValue
  addQuoted: addEscaped(builder, text, bytes)
  return
:container
  readMark: writing = word(node, n128=128)
  markCheck: isWriting = compare.notEqualInt64(writing, zero)
  if isWriting circular depthCheck
:circular
  failCircular: failInside(target, circularText="ValueError('Circular reference detected')")
  return
:depthCheck
  deeper: inner = math.addInt64(depth, one=1)
  deepCheck: tooDeep2 = compare.greaterThanInt64(inner, deepest)
  if tooDeep2 recursionFailed mark
:recursionFailed
  failRecursion: failInside(target, recursionText="RecursionError('maximum recursion depth exceeded while encoding a JSON object')")
  return
:mark
  storeMark: setWord(node, n128, one)
  checkArray: isArray = compare.equalInt64(kind, kindArray)
  if isArray openList openObject
:openList
  addOpenList: addText(builder, openListText="[")
  readItems: itemsAt = word(node, sixteen)
  itemsAddress: items = machine.fromInt64(itemsAt)
  goto eachItem
:eachItem loop=while max=bytes
  itemsDone: allItems = compare.greaterOrEqualInt64(at, bytes)
  if allItems closeList writeItem
:writeItem in=eachItem
  firstCheck: isFirst = compare.equalInt64(at, zero)
  if isFirst itemValue itemComma
:itemComma in=eachItem
  addItemComma: wide.builderAddByte(builder, comma)
  goto itemValue
:itemValue in=eachItem
  itemOffset: itemPlace = math.multiplyInt64(at, eight)
  findItem: itemSlot = machine.offset(items, itemPlace)
  readItem: item = machine.loadAddress(itemSlot)
  writeItemValue: writeValue(builder, item, inner)
  nextItem: afterItem = math.addInt64(at, one)
  set at afterItem
  goto eachItem
:closeList
  addCloseList: addText(builder, closeListText="]")
  goto unmark
:openObject
  addOpenObject: addText(builder, openObjectText="{")
  findTable: table = machine.offset(node, forty=40)
  goto eachField
:eachField loop=while max=bytes
  fieldsDone: allFields = compare.greaterOrEqualInt64(at, bytes)
  if allFields closeObject writeField
:writeField in=eachField
  firstFieldCheck: isFirstField = compare.equalInt64(at, zero)
  if isFirstField fieldKey fieldComma
:fieldComma in=eachField
  addFieldComma: wide.builderAddByte(builder, comma)
  goto fieldKey
:fieldKey in=eachField
  findRow: row = tables.rowAddress(table, at)
  findKey: keySlot = machine.offset(row, sixteen)
  readKey: key = machine.loadAddress(keySlot)
  findKeyBytes: keyBytesSlot = machine.offset(row, twentyFour)
  readKeyBytes: keyBytes = machine.loadInt64(keyBytesSlot)
  addKey: addEscaped(builder, key, keyBytes)
  addColon: wide.builderAddByte(builder, colon)
  findChild: childSlot = machine.offset(row, thirtyTwo=32)
  readChild: child = machine.loadAddress(childSlot)
  writeChild: writeValue(builder, child, inner)
  nextField: afterField = math.addInt64(at, one)
  set at afterField
  goto eachField
:closeObject
  addCloseObject: addText(builder, closeObjectText="}")
  goto unmark
:unmark
  clearMark: setWord(node, n128, zero)
  return

## ---------------------------------------------------------------- text out, as surrogateescape writes it

op codeAtByte "The code point UTF-8 (with surrogates) holds at a byte, the bytes it takes stored at an address"
  input text machine.Address copied
  input bytes Int64 copied
  input at Int64 copied
  input taken machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findByte: place = machine.offset(text, at)
  readByte: byte = machine.loadByte(place)
  widen: first = convert.byteToInt64(byte)
  oneCheck: one1 = compare.lessThanInt64(first, n128=128)
  if one1 giveOne twoCheck
:giveOne
  storeOne: machine.storeInt64(taken, one=1)
  return first
:twoCheck
  checkTwo: two1 = compare.lessThanInt64(first, n224=224)
  if two1 giveTwo threeCheck
:giveTwo
  lowTwo: twoBits = bits.andInt64(first, n31=31)
  joinTwo: twoValue = joinTrail(text, at, twoBits, one)
  storeTwo: machine.storeInt64(taken, two=2)
  return twoValue
:threeCheck
  checkThree: three1 = compare.lessThanInt64(first, n240=240)
  if three1 giveThree giveFour
:giveThree
  lowThree: threeBits = bits.andInt64(first, n15=15)
  joinThree: threeValue = joinTrail(text, at, threeBits, two)
  storeThree: machine.storeInt64(taken, three=3)
  return threeValue
:giveFour
  lowFour: fourBits = bits.andInt64(first, n7=7)
  joinFour: fourValue = joinTrail(text, at, fourBits, three)
  storeFour: machine.storeInt64(taken, four=4)
  return fourValue

op joinTrail "A code point's value from its lead bits and a number of continuation bytes after a position"
  input text machine.Address copied
  input at Int64 copied
  input lead Int64 copied
  input trail Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let k Int64 0 mut
  let value Int64 0 mut
:begin
  set value lead
  goto eachTrail
:eachTrail loop=while max=trail
  doneCheck: done = compare.greaterOrEqualInt64(k, trail)
  if done give takeTrail
:takeTrail in=eachTrail
  nextK: afterK = math.addInt64(k, one=1)
  placeOf: place = math.addInt64(at, afterK)
  findByte: byteAt = machine.offset(text, place)
  readByte: byte = machine.loadByte(byteAt)
  widen: trailByte = convert.byteToInt64(byte)
  sixOf: six = bits.andInt64(trailByte, n63=63)
  shiftIt: shifted = bits.shiftLeftInt64(value, sixBits=6)
  joinIt: joined = bits.orInt64(shifted, six)
  set value joined
  set k afterK
  goto eachTrail
:give
  return value

op isSurrogate "Whether a code point is a surrogate, U+D800 to U+DFFF"
  input code Int64 copied
  output Bool
:begin
  lowCheck: above = compare.greaterOrEqualInt64(code, surrogateFirst=55296)
  highCheck: below = compare.lessOrEqualInt64(code, surrogateLast=57343)
  bothCheck: surrogate = logic.and(above, below)
  return surrogate

op isEscapable "Whether a code point is one of surrogateescape's, U+DC80 to U+DCFF"
  input code Int64 copied
  output Bool
:begin
  lowCheck: above = compare.greaterOrEqualInt64(code, escapeFirst=56448)
  highCheck: below = compare.lessOrEqualInt64(code, escapeLast=56575)
  bothCheck: escapable = logic.and(above, below)
  return escapable

op addRepr "Add a text's repr as Python writes it: in single quotes unless it holds one and no double quote, the quote and backslash escaped, tab, line feed, and carriage return as escapes, other control characters and those of Latin-1 that do not print as \\xNN, surrogates as \\uXXXX"
  input builder machine.Address copied
  input text machine.Address copied
  input bytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let quote Int64 39 mut
  let single Int64 0 mut
  let double Int64 0 mut
  let n34 Int64 34
  let hexDigits String "0123456789abcdef"
:begin
  findSingle: singleAt = machine.addressOfString(singleQuote="'")
  hasSingle: singleFound = memory.findBytes(text, bytes, singleAt, one=1)
  set single singleFound
  findDouble: doubleAt = machine.addressOfString(doubleQuote="\"")
  hasDouble: doubleFound = memory.findBytes(text, bytes, doubleAt, one)
  set double doubleFound
  singleCheck: anySingle = compare.greaterOrEqualInt64(single, zero=0)
  doubleCheck: noDouble = compare.lessThanInt64(double, zero)
  useDoubleCheck: useDouble = logic.and(anySingle, noDouble)
  if useDouble chooseDouble open
:chooseDouble
  set quote n34
  goto open
:open
  addOpen: addByteValue(builder, quote)
  findTaken: taken = kernel.stateAt(codeAt)
  goto eachCode
:eachCode loop=while max=bytes
  doneCheck: done = compare.greaterOrEqualInt64(at, bytes)
  if done finish readOne
:readOne in=eachCode
  readCode: code = codeAtByte(text, bytes, at, taken)
  readTaken: length = machine.loadInt64(taken)
  quoteCheck: isQuote = compare.equalInt64(code, quote)
  backslashCheck: isBackslash = compare.equalInt64(code, n92=92)
  slashCheck: slashed = logic.or(isQuote, isBackslash)
  if slashed addSlashed tabCheck
:addSlashed in=eachCode
  addSlash: addByteValue(builder, n92)
  addItself: addByteValue(builder, code)
  goto advance
:tabCheck in=eachCode
  checkTab: isTab = compare.equalInt64(code, nine=9)
  if isTab addTab lineCheck
:addTab in=eachCode
  addTabText: addText(builder, tabText="\\t")
  goto advance
:lineCheck in=eachCode
  checkLine: isLine = compare.equalInt64(code, ten=10)
  if isLine addLine returnCheck
:addLine in=eachCode
  addLineText: addText(builder, lineText="\\n")
  goto advance
:returnCheck in=eachCode
  checkReturn: isReturn = compare.equalInt64(code, thirteen=13)
  if isReturn addReturn hexCheck
:addReturn in=eachCode
  addReturnText: addText(builder, returnText="\\r")
  goto advance
:hexCheck in=eachCode
  lowControl: isLowControl = compare.lessThanInt64(code, n32=32)
  deleteCheck: isDelete = compare.equalInt64(code, n127=127)
  highLow: aboveDelete = compare.greaterOrEqualInt64(code, n128=128)
  highHigh: belowSpace = compare.lessOrEqualInt64(code, n160=160)
  highControl: isHighControl = logic.and(aboveDelete, belowSpace)
  softCheck: isSoft = compare.equalInt64(code, n173=173)
  firstPair: lowOrDelete = logic.or(isLowControl, isDelete)
  secondPair: highOrSoft = logic.or(isHighControl, isSoft)
  anyHex: needsHex = logic.or(lowOrDelete, highOrSoft)
  if needsHex addHex surrogateCheck
:addHex in=eachCode
  addX: addText(builder, xText="\\x")
  hexHigh: highNibble = bits.shiftRightInt64(code, four=4)
  hexLow: lowNibble = bits.andInt64(code, fifteen=15)
  findDigits: digitsStart = machine.addressOfString(hexDigits)
  findHigh: highAt = machine.offset(digitsStart, highNibble)
  addHigh: wide.builderAdd(builder, highAt, one)
  findLow: lowAt = machine.offset(digitsStart, lowNibble)
  addLow: wide.builderAdd(builder, lowAt, one)
  goto advance
:surrogateCheck in=eachCode
  checkSurrogate: surrogate = isSurrogate(code)
  if surrogate addSurrogate addPlain
:addSurrogate in=eachCode
  addUEscape: addText(builder, uEscapeText="\\u")
  findDigitsU: digitsU = machine.addressOfString(hexDigits)
  nibble3: n3 = bits.shiftRightInt64(code, twelve=12)
  findN3: n3At = machine.offset(digitsU, n3)
  addN3: wide.builderAdd(builder, n3At, one)
  shift2: s2 = bits.shiftRightInt64(code, eight=8)
  nibble2: n2 = bits.andInt64(s2, fifteen)
  findN2: n2At = machine.offset(digitsU, n2)
  addN2: wide.builderAdd(builder, n2At, one)
  shift1: s1 = bits.shiftRightInt64(code, four)
  nibble1: n1 = bits.andInt64(s1, fifteen)
  findN1: n1At = machine.offset(digitsU, n1)
  addN1: wide.builderAdd(builder, n1At, one)
  nibble0: n0 = bits.andInt64(code, fifteen)
  findN0: n0At = machine.offset(digitsU, n0)
  addN0: wide.builderAdd(builder, n0At, one)
  goto advance
:addPlain in=eachCode
  findPlain: plainAt = machine.offset(text, at)
  addPlainBytes: wide.builderAdd(builder, plainAt, length)
  goto advance
:advance in=eachCode
  nextAt: after = math.addInt64(at, length)
  set at after
  goto eachCode
:finish
  addClose: addByteValue(builder, quote)
  return

op failEncode "Trap as `refined run` does when the encoder refuses a surrogate surrogateescape cannot write: UnicodeEncodeError('utf-8', <the text>, start, end, 'surrogates not allowed'), the first such surrogate and the end of its run of surrogates"
  input target String borrowed
  input text machine.Address copied
  input bytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let index Int64 0 mut
  let start Int64 -1 mut
  let end Int64 -1 mut
:begin
  findTaken: taken = kernel.stateAt(codeAt)
  goto eachCode
:eachCode loop=while max=bytes
  doneCheck: done = compare.greaterOrEqualInt64(at, bytes)
  if done report readOne
:readOne in=eachCode
  readCode: code = codeAtByte(text, bytes, at, taken)
  readTaken: length = machine.loadInt64(taken)
  surrogateCheck: surrogate = isSurrogate(code)
  if surrogate inRun outRun
:inRun in=eachCode
  startedCheck: started = compare.greaterOrEqualInt64(start, zero=0)
  if started extend firstCheck
:firstCheck in=eachCode
  escapableCheck: escapable = isEscapable(code)
  if escapable advance markStart
:markStart in=eachCode
  set start index
  goto extend
:extend in=eachCode
  afterIndex: runEnd = math.addInt64(index, one=1)
  set end runEnd
  goto advance
:outRun in=eachCode
  endedCheck: ended = compare.greaterOrEqualInt64(start, zero)
  if ended report advance
:advance in=eachCode
  nextAt: after = math.addInt64(at, length)
  set at after
  nextIndex: afterIndex2 = math.addInt64(index, one)
  set index afterIndex2
  goto eachCode
:report
  makeMessage: message = wide.builderNew()
  addOpen: addText(message, openText="`")
  addTarget: addText(message, target)
  addFailed: addText(message, failedText="` failed inside the runtime: UnicodeEncodeError('utf-8', ")
  addTheText: addRepr(message, text, bytes)
  addComma: addText(message, commaText=", ")
  addStart: addNumber(message, start)
  addComma2: addText(message, commaText)
  addEnd: addNumber(message, end)
  addReason: addText(message, reasonText=", 'surrogates not allowed')")
  failIt: failBuilt(message)
  return

op putOut "Copy text into a region as surrogateescape encodes it, into two result slots: U+DC80 to U+DCFF as the byte each stands for; any other surrogate traps as the encoder refuses it"
  input target String borrowed
  input text machine.Address copied
  input bytes Int64 copied
  input region machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let made Int64 0 mut
  let lead Byte 237
:begin
  findLead: leadAt = machine.addressOfString(leadText="\xed")
  anyCheck: firstLead = memory.findBytes(text, bytes, leadAt, one=1)
  noLeadCheck: noLead = compare.lessThanInt64(firstLead, zero=0)
  if noLead copyAll convert
:copyAll
  putAll: slots.putText(region, text, bytes, results)
  return
:convert
  takeCopy: copy = regions.allocate(region, bytes)
  goto eachByte
:eachByte loop=while max=bytes
  doneCheck: done = compare.greaterOrEqualInt64(at, bytes)
  if done finish readOne
:readOne in=eachByte
  findByte: place = machine.offset(text, at)
  readByte: byte = machine.loadByte(place)
  leadCheck: isLead = compare.equalByte(byte, lead)
  if isLead secondCheck copyByte
:secondCheck in=eachByte
  secondAt: secondPlace = machine.offset(place, one)
  readSecond: second = machine.loadByte(secondPlace)
  widenSecond: secondValue = convert.byteToInt64(second)
  surrogateCheck: isSurrogate2 = compare.greaterOrEqualInt64(secondValue, n160=160)
  if isSurrogate2 escapeCheck copyByte
:escapeCheck in=eachByte
  lowSecond: aboveB2 = compare.greaterOrEqualInt64(secondValue, n178=178)
  highSecond: belowB3 = compare.lessOrEqualInt64(secondValue, n179=179)
  bothSecond: escapable = logic.and(aboveB2, belowB3)
  if escapable escapeByte refuse
:escapeByte in=eachByte
  thirdAt: thirdPlace = machine.offset(place, two=2)
  readThird: third = machine.loadByte(thirdPlace)
  widenThird: thirdValue = convert.byteToInt64(third)
  lowBits: low = bits.andInt64(thirdValue, n63=63)
  secondBit: secondLow = bits.andInt64(secondValue, one64=1)
  shiftSecond: secondShifted = bits.shiftLeftInt64(secondLow, six=6)
  joinBits: joined = bits.orInt64(secondShifted, low)
  markIt: original = bits.orInt64(joined, n128=128)
  narrowIt: escaped = convert.int64ToByte(original)
  findOut: outAt = machine.offset(copy, made)
  storeEscaped: machine.storeByte(outAt, escaped)
  pastThree: afterThree = math.addInt64(at, three=3)
  set at afterThree
  goto counted
:copyByte in=eachByte
  findPlain: plainAt = machine.offset(copy, made)
  storePlain: machine.storeByte(plainAt, byte)
  pastOne: afterOne = math.addInt64(at, one)
  set at afterOne
  goto counted
:counted in=eachByte
  moreMade: afterMade = math.addInt64(made, one)
  set made afterMade
  goto eachByte
:refuse
  failIt: failEncode(target, text, bytes)
  return
:finish
  storeAddress: machine.storeAddress(results, copy)
  findLength: lengthSlot = machine.offset(results, eight=8)
  storeLength: machine.storeInt64(lengthSlot, made)
  return

## ---------------------------------------------------------------- targets

op valueArg "The value a call's parameter names (a json.Value handle)"
  input shape machine.Address copied
  input args machine.Address copied
  input parameter Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readHandle: handle = slots.argOf(shape, args, parameter)
  findValue: node = handles.objectOf(handle, kindJson)
  return node

op giveValue "A new handle for a value in a region, stored in the first result slot; the handle takes over the caller's hold"
  input node machine.Address copied
  input region machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  makeHandle: handle = handles.newHandle(kindJson, node, region)
  storeHandle: machine.storeInt64(results, handle)
  return

op kindOfNode "A value's json.Kind, numbered from 0: null, boolean, number, text, array, object"
  input node machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let zero Int64 0
  let one Int64 1
  let two Int64 2
  let three Int64 3
  let four Int64 4
  let five Int64 5
:begin
  readKind: kind = word(node, eight=8)
  nullCheck: isNull = compare.equalInt64(kind, kindNull)
  if isNull giveNull booleanCheck
:giveNull
  return zero
:booleanCheck
  checkBoolean: isBoolean = compare.equalInt64(kind, kindBoolean)
  if isBoolean giveBoolean textCheck
:giveBoolean
  return one
:textCheck
  checkText: isText = compare.equalInt64(kind, kindText)
  if isText giveText arrayCheck
:giveText
  return three
:arrayCheck
  checkArray: isArray = compare.equalInt64(kind, kindArray)
  if isArray giveArray objectCheck
:giveArray
  return four
:objectCheck
  checkObject: isObject = compare.equalInt64(kind, kindObject)
  if isObject giveObject giveNumber
:giveObject
  return five
:giveNumber
  return two

op parseTarget "json.parse: a value owned by a region, or invalidAt with its position, or tooDeep"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok Int32 0
:begin
  readText: text = files.textAt(shape, args, zero=0)
  readBytes: bytes = files.textBytes(shape, args, zero)
  readRegion: region = slots.addressArg(shape, args, one=1)
  parseIt: node = parseDocument(text, bytes)
  nowhere: anywhere = machine.zero()
  failedCheck: failed = machine.equal(node, anywhere)
  if failed giveError give
:give
  giveIt: giveValue(node, region, results)
  return ok
:giveError
  readKind: kind = stateWord(errorAt)
  deepCheck: isDeep = compare.equalInt64(kind, two=2)
  if isDeep giveDeep giveInvalid
:giveDeep
  deepStatus: status1 = slots.failWith(payload, tooDeep, zero)
  return status1
:giveInvalid
  readPosition: position = stateWord(positionAt)
  invalidStatus: status2 = slots.failWith(payload, invalidAt, position)
  return status2

op readTarget "json.kind, asInt64, asBool, asText, length (2 to 6): what a value holds, or wrongKind and notWhole as host.py gives them"
  input which Int64 copied
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok Int32 0
  let at Int64 0 mut
  let codes Int64 0 mut
  let least Float64 -9223372036854775808.0
  let limit Float64 9223372036854775808.0
:begin
  readNode: node = valueArg(shape, args, zero=0)
  readKind: kind = word(node, eight=8)
  loadValue: value = word(node, sixteen=16)
  readLength: length = word(node, twentyFour=24)
  kindCheck: isKind = compare.equalInt64(which, two=2)
  if isKind giveKind intCheck
:giveKind
  kindOf: tag = kindOfNode(node)
  storeTag: machine.storeInt64(results, tag)
  findPayloadSlot: tagPayload = machine.offset(results, eight)
  storeNoPayload: machine.storeInt64(tagPayload, zero)
  return ok
:intCheck
  checkInt: isInt = compare.equalInt64(which, three=3)
  if isInt asInt boolCheck
:asInt
  wholeCheck: isWhole = compare.equalInt64(kind, kindWhole)
  if isWhole giveWhole bigCheck
:giveWhole
  storeWhole: machine.storeInt64(results, value)
  return ok
:bigCheck
  checkBig: isBig = compare.equalInt64(kind, kindBig)
  if isBig giveNotWhole floatCheck
:floatCheck
  checkFloat: isFloat = compare.equalInt64(kind, kindFloat)
  if isFloat floatWhole giveWrongKind
:floatWhole
  wideBits: unsigned = convert.int64BitsToUInt64(value)
  asFloat: number = convert.uint64BitsToFloat64(unsigned)
  lowCheck: aboveLeast = compare.greaterOrEqualFloat64(number, least)
  highCheck: belowLimit = compare.lessThanFloat64(number, limit)
  rangeCheck: inRange = logic.and(aboveLeast, belowLimit)
  if inRange integralCheck giveNotWhole
:integralCheck
  truncate: truncated = convert.float64ToInt64(number)
  back: again = convert.int64ToFloat64(truncated)
  sameCheck: same = compare.equalFloat64(again, number)
  if same giveTruncated giveNotWhole
:giveTruncated
  storeTruncated: machine.storeInt64(results, truncated)
  return ok
:boolCheck
  checkBool: isBool = compare.equalInt64(which, four=4)
  if isBool asBool textCheck
:asBool
  booleanCheck: isBoolean = compare.equalInt64(kind, kindBoolean)
  if isBoolean giveBool giveWrongKind
:giveBool
  storeBool: machine.storeInt64(results, value)
  return ok
:textCheck
  checkText: isTextTarget = compare.equalInt64(which, five=5)
  if isTextTarget asText lengthTarget
:asText
  textKindCheck: isText = compare.equalInt64(kind, kindText)
  if isText giveText giveWrongKind
:giveText
  textAddress: text = machine.fromInt64(value)
  readRegion: region = slots.addressArg(shape, args, one=1)
  putIt: putOut(asTextName="json.asText", text, length, region, results)
  return ok
:lengthTarget
  arrayCheck: isArray = compare.equalInt64(kind, kindArray)
  objectCheck: isObject = compare.equalInt64(kind, kindObject)
  containerCheck: isContainer = logic.or(isArray, isObject)
  if isContainer giveCount lengthTextCheck
:giveCount
  storeCount: machine.storeInt64(results, length)
  return ok
:lengthTextCheck
  checkLengthText: isLengthText = compare.equalInt64(kind, kindText)
  if isLengthText countCodes giveWrongKind
:countCodes
  countAddress: countText = machine.fromInt64(value)
  goto eachByte
:eachByte loop=while max=length
  doneCheck: done = compare.greaterOrEqualInt64(at, length)
  if done giveCodes readByte
:readByte in=eachByte
  findByte: place = machine.offset(countText, at)
  readIt: byte = machine.loadByte(place)
  widen: byteValue = convert.byteToInt64(byte)
  trailLow: aboveTrail = compare.greaterOrEqualInt64(byteValue, n128=128)
  trailHigh: belowTrail = compare.lessOrEqualInt64(byteValue, n191=191)
  trailCheck: isTrail = logic.and(aboveTrail, belowTrail)
  if isTrail advance countOne
:countOne in=eachByte
  moreCodes: afterCodes = math.addInt64(codes, one=1)
  set codes afterCodes
  goto advance
:advance in=eachByte
  nextAt: after = math.addInt64(at, one)
  set at after
  goto eachByte
:giveCodes
  storeCodes: machine.storeInt64(results, codes)
  return ok
:giveNotWhole
  notWholeStatus: status1 = slots.failWith(payload, notWhole, zero)
  return status1
:giveWrongKind
  wrongStatus: status2 = slots.failWith(payload, wrongKind, zero)
  return status2

op childTarget "json.item and json.field (7 and 8): the value at an index of an array or under a name of an object, shared, with a new handle in a region; wrongKind, outOfRange with the index, or missing"
  input which Int64 copied
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok Int32 0
:begin
  readNode: node = valueArg(shape, args, zero=0)
  readKind: kind = word(node, eight=8)
  itemCheck: isItem = compare.equalInt64(which, seven=7)
  if isItem item field
:item
  arrayCheck: isArray = compare.equalInt64(kind, kindArray)
  if isArray readIndex giveWrongKind
:readIndex
  indexOf: index = slots.argOf(shape, args, one=1)
  readCount: count = word(node, twentyFour=24)
  lowCheck: negative = compare.lessThanInt64(index, zero)
  highCheck: past = compare.greaterOrEqualInt64(index, count)
  outsideCheck: outside = logic.or(negative, past)
  if outside giveOutOfRange giveItem
:giveItem
  readItems: itemsAt = word(node, sixteen=16)
  itemsAddress: items = machine.fromInt64(itemsAt)
  itemOffset: offset = math.multiplyInt64(index, eight=8)
  findItem: itemSlot = machine.offset(items, offset)
  readItem: child = machine.loadAddress(itemSlot)
  holdItem: values.retain(child)
  readItemRegion: itemRegion = slots.addressArg(shape, args, two=2)
  giveIt: giveValue(child, itemRegion, results)
  return ok
:giveOutOfRange
  outStatus: status1 = slots.failWith(payload, outOfRange, index)
  return status1
:field
  objectCheck: isObject = compare.equalInt64(kind, kindObject)
  if isObject readName giveWrongKind
:readName
  nameOf: name = files.textAt(shape, args, one)
  nameBytesOf: nameBytes = files.textBytes(shape, args, one)
  replaceIt: key = replaced(name, nameBytes)
  readKey: keyText = wide.builderText(key)
  readKeyBytes: keyBytes = wide.builderLength(key)
  findIt: found = values.findField(node, keyText, keyBytes)
  giveKey: giveBuilder(key)
  nowhere: anywhere = machine.zero()
  missingCheck: isMissing = machine.equal(found, anywhere)
  if isMissing giveMissing giveField
:giveField
  holdField: values.retain(found)
  readFieldRegion: fieldRegion = slots.addressArg(shape, args, two)
  giveFieldIt: giveValue(found, fieldRegion, results)
  return ok
:giveMissing
  missingStatus: status2 = slots.failWith(payload, missing, zero)
  return status2
:giveWrongKind
  wrongStatus: status3 = slots.failWith(payload, wrongKind, zero)
  return status3

op newTarget "json.newObject and json.newArray (9 and 10): an empty object or array owned by a region"
  input which Int64 copied
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let kind Int64 8 mut
:begin
  arrayCheck: isArray = compare.equalInt64(which, ten=10)
  if isArray chooseArray make
:chooseArray
  set kind kindArray
  goto make
:make
  makeIt: node = values.newValue(kind)
  readRegion: region = slots.addressArg(shape, args, zero=0)
  giveIt: giveValue(node, region, results)
  return

op textValue "A text value of a call's text parameter, read as host.py reads it (invalid UTF-8 as U+FFFD)"
  input shape machine.Address copied
  input args machine.Address copied
  input parameter Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readText: text = files.textAt(shape, args, parameter)
  readBytes: bytes = files.textBytes(shape, args, parameter)
  replaceIt: builder = replaced(text, bytes)
  makeNode: node = textNode(builder)
  return node

op setTarget "json.setInt64, setText, setBool, setValue (11 to 14): set an object's key to a number, a text, a flag, or a value it then shares; wrongKind for anything but an object"
  input which Int64 copied
  input shape machine.Address copied
  input args machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok Int32 0
  let child machine.Address unset mut
:begin
  readNode: node = valueArg(shape, args, zero=0)
  readKind: kind = word(node, eight=8)
  objectCheck: isObject = compare.equalInt64(kind, kindObject)
  if isObject makeChild giveWrongKind
:makeChild
  numberCheck: isNumber = compare.equalInt64(which, eleven=11)
  if isNumber makeNumber textCheck
:makeNumber
  loadNumber: number = slots.argOf(shape, args, two=2)
  makeWhole: whole = values.newValue(kindWhole)
  storeNumber: setWord(whole, sixteen=16, number)
  set child whole
  goto put
:textCheck
  checkText: isText = compare.equalInt64(which, twelve=12)
  if isText makeText flagCheck
:makeText
  textIt: text = textValue(shape, args, two)
  set child text
  goto put
:flagCheck
  checkFlag: isFlag = compare.equalInt64(which, thirteen=13)
  if isFlag makeFlag shareValue
:makeFlag
  readFlag: flag = slots.argOf(shape, args, two)
  flagSet: isSet = compare.notEqualInt64(flag, zero)
  makeBoolean: boolean = values.newValue(kindBoolean)
  set child boolean
  if isSet storeTrue put
:storeTrue
  storeOne: setWord(boolean, sixteen, one=1)
  goto put
:shareValue
  readShared: shared = valueArg(shape, args, two)
  holdShared: values.retain(shared)
  set child shared
  goto put
:put
  readName: name = files.textAt(shape, args, one)
  readNameBytes: nameBytes = files.textBytes(shape, args, one)
  replaceName: key = replaced(name, nameBytes)
  readKey: keyText = wide.builderText(key)
  readKeyBytes: keyBytes = wide.builderLength(key)
  putIt: values.putField(node, keyText, keyBytes, child)
  giveKey: giveBuilder(key)
  return ok
:giveWrongKind
  wrongStatus: status = slots.failWith(payload, wrongKind, zero)
  return status

op appendTarget "json.appendInt64 and appendText (15 and 16): add a number or a text to the end of an array; wrongKind for anything but an array"
  input which Int64 copied
  input shape machine.Address copied
  input args machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok Int32 0
:begin
  readNode: node = valueArg(shape, args, zero=0)
  readKind: kind = word(node, eight=8)
  arrayCheck: isArray = compare.equalInt64(kind, kindArray)
  if isArray chooseItem giveWrongKind
:chooseItem
  numberCheck: isNumber = compare.equalInt64(which, fifteen=15)
  if isNumber addNumberItem addTextItem
:addNumberItem
  loadNumber: number = slots.argOf(shape, args, one=1)
  makeWhole: whole = values.newValue(kindWhole)
  storeNumber: setWord(whole, sixteen=16, number)
  appendWhole: values.appendItem(node, whole)
  return ok
:addTextItem
  textIt: text = textValue(shape, args, one)
  appendText: values.appendItem(node, text)
  return ok
:giveWrongKind
  wrongStatus: status = slots.failWith(payload, wrongKind, zero)
  return status

op stringifyTarget "json.stringify: a value's text as json.dumps writes it, into a region"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readNode: node = valueArg(shape, args, zero=0)
  readRegion: region = slots.addressArg(shape, args, one=1)
  makeText: builder = wide.builderNew()
  writeIt: writeValue(builder, node, zero)
  readText: text = wide.builderText(builder)
  readLength: bytes = wide.builderLength(builder)
  putIt: putOut(stringifyName="json.stringify", text, bytes, region, results)
  giveIt: giveBuilder(builder)
  return

op jsonCall "Run a json target by its place among them (1 parse, 2 kind, 3 asInt64, 4 asBool, 5 asText, 6 length, 7 item, 8 field, 9 newObject, 10 newArray, 11 setInt64, 12 setText, 13 setBool, 14 setValue, 15 appendInt64, 16 appendText, 17 stringify): 0, or an error's variant number with its payload stored"
  invariant runsJson "Each target gives what host.py's json handler gives under `refined run`: json.loads and json.dumps, their errors and positions included"
  input which Int64 copied
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok Int32 0
:begin
  parseCheck: isParse = compare.equalInt64(which, one=1)
  if isParse runParse readCheck
:runParse
  parseIt: parseStatus = parseTarget(shape, args, results, payload)
  return parseStatus
:readCheck
  checkRead: isRead = compare.lessOrEqualInt64(which, six=6)
  if isRead runRead childCheck
:runRead
  readIt: readStatus = readTarget(which, shape, args, results, payload)
  return readStatus
:childCheck
  checkChild: isChild = compare.lessOrEqualInt64(which, eight=8)
  if isChild runChild newCheck
:runChild
  childIt: childStatus = childTarget(which, shape, args, results, payload)
  return childStatus
:newCheck
  checkNew: isNew = compare.lessOrEqualInt64(which, ten=10)
  if isNew runNew setCheck
:runNew
  newIt: newTarget(which, shape, args, results)
  return ok
:setCheck
  checkSet: isSet = compare.lessOrEqualInt64(which, fourteen=14)
  if isSet runSet appendCheck
:runSet
  setIt: setStatus = setTarget(which, shape, args, payload)
  return setStatus
:appendCheck
  checkAppend: isAppend = compare.lessOrEqualInt64(which, sixteen=16)
  if isAppend runAppend runStringify
:runAppend
  appendIt: appendStatus = appendTarget(which, shape, args, payload)
  return appendStatus
:runStringify
  stringifyIt: stringifyTarget(shape, args, results)
  return ok

@tests

## Tests build a shape and a call's slots in the last 4 KiB of machine.state: the shape from byte 61440, the
## arguments from 61952, the results from 62016, the payload at 62080.

op setShape "Make the tests' shape from the slot counts of up to three parameters (0 for none)"
  input first Int64 copied
  input second Int64 copied
  input third Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  findShape: shape = kernel.stateAt(shapeAt=61440)
  findCounts: counts = machine.offset(shape, forty=40)
  findStarts: starts = machine.offset(shape, twoThirtyTwo=232)
  storeFirst: machine.storeInt64(counts, first)
  storeFirstStart: machine.storeInt64(starts, zero=0)
  findSecond: secondCount = machine.offset(counts, eight=8)
  storeSecond: machine.storeInt64(secondCount, second)
  findSecondStart: secondStart = machine.offset(starts, eight)
  storeSecondStart: machine.storeInt64(secondStart, first)
  findThird: thirdCount = machine.offset(counts, sixteen=16)
  storeThird: machine.storeInt64(thirdCount, third)
  findThirdStart: thirdStart = machine.offset(starts, sixteen)
  thirdAt: third0 = math.addInt64(first, second)
  storeThirdStart: machine.storeInt64(thirdStart, third0)
  findParams: paramsAt = machine.offset(shape, twentyFour=24)
  storeParams: machine.storeInt64(paramsAt, three=3)
  return

op argAt "The address of an argument slot of the tests' call"
  input slot Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  offsetOf: offset = math.multiplyInt64(slot, eight=8)
  withBase: place = math.addInt64(offset, argsOffset=61952)
  findSlot: address = kernel.stateAt(place)
  return address

op setNumberArg "Set an argument slot of the tests' call to a number"
  input slot Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  findSlot: address = argAt(slot)
  storeIt: machine.storeInt64(address, value)
  return

op setAddressArg "Set an argument slot of the tests' call to an address"
  input slot Int64 copied
  input value machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  findSlot: address = argAt(slot)
  storeIt: machine.storeAddress(address, value)
  return

op setTextArg "Set two argument slots of the tests' call to a text's address and length"
  input slot Int64 copied
  input text String borrowed
  effect use machine.memory
  uses memoryAccess
:begin
  findText: textAt = machine.addressOfString(text)
  textLength: bytes = string.byteLength(text)
  findSlot: address = argAt(slot)
  storeAddress: machine.storeAddress(address, textAt)
  findLength: lengthSlot = machine.offset(address, eight=8)
  storeLength: machine.storeInt64(lengthSlot, bytes)
  return

op callJson "Call a json target with the tests' slots and give its status"
  input which Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findShape: shape = kernel.stateAt(shapeAt=61440)
  findArgs: args = kernel.stateAt(argsOffset=61952)
  findResults: results = kernel.stateAt(resultsOffset=62016)
  findPayload: payload = kernel.stateAt(payloadOffset=62080)
  callIt: status = jsonCall(which, shape, args, results, payload)
  widen: wide1 = convert.int32ToInt64(status)
  return wide1

op resultSlot "A result slot of the tests' call"
  input slot Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  offsetOf: offset = math.multiplyInt64(slot, eight=8)
  withBase: place = math.addInt64(offset, resultsOffset=62016)
  findSlot: address = kernel.stateAt(place)
  readIt: value = machine.loadInt64(address)
  return value

op payloadValue "The payload of the tests' call"
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findPayload: payload = kernel.stateAt(payloadOffset=62080)
  readIt: value = machine.loadInt64(payload)
  return value

op expectResultText "Compare the text in the first two result slots with what is expected"
  input wanted String borrowed
  effect use machine.memory
  uses memoryAccess
:begin
  findResults: results = kernel.stateAt(resultsOffset=62016)
  readText: text = machine.loadAddress(results)
  findLength: lengthSlot = machine.offset(results, eight=8)
  readLength: length = machine.loadInt64(lengthSlot)
  findWanted: wantedAt = machine.addressOfString(wanted)
  wantedLength: wantedBytes = string.byteLength(wanted)
  compareLength: test.assertEqualInt64(wantedBytes, length)
  compareText: same = memory.bytesEqual(text, length, wantedAt, wantedBytes)
  sameWide: sameValue = convert.int32ToInt64(same)
  compareIt: test.assertEqualInt64(one=1, sameValue)
  return

op parseInto "Parse a text into a region and give the status; the handle is the first result slot"
  input text String borrowed
  input region machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  shapeIt: setShape(two=2, one=1, zero=0)
  putTheText: setTextArg(zero, text)
  setRegion: setAddressArg(two, region)
  callIt: status = callJson(one)
  return status

op expectRound "Parse a text and compare what stringify writes for it with what is expected"
  input text String borrowed
  input wanted String borrowed
  input region machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  parseIt: status = parseInto(text, region)
  test.assertEqualInt64(zero=0, status)
  readHandle: handle = resultSlot(zero)
  shapeIt: setShape(one=1, one, zero)
  setHandle: setNumberArg(zero, handle)
  setRegion: setAddressArg(one, region)
  writeIt: written = callJson(seventeen=17)
  test.assertEqualInt64(zero, written)
  expectIt: expectResultText(wanted)
  return

op expectInvalid "Parse a text and compare the position of its error with what is expected"
  input text String borrowed
  input wanted Int64 copied
  input region machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  parseIt: status = parseInto(text, region)
  test.assertEqualInt64(one=1, status)
  readPosition: position = payloadValue()
  test.assertEqualInt64(wanted, position)
  return

test jsonTest "Texts read as json.loads reads them, with its errors and positions, and values written as json.dumps writes them; values are shared, set, appended, and read by kind"
  verifies jsonCall runsJson
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let label String "json test"
:begin
  findLabel: labelAt = machine.addressOfString(label)
  labelLength: labelBytes = string.byteLength(label)
  make: region = regions.newRegion(capacity=1048576, labelAt, labelBytes)
  round1: expectRound(text1=" {\"b\": [1, 2.50, -0.0, 1e400, true, null, \"x\\u00e9\\ud83d\\ude00\"], \"a\": {}, \"b\": -12} ", want1="{\"b\":-12,\"a\":{}}", region)
  round2: expectRound(text2="[NaN, Infinity, -Infinity, 123456789012345678901234567890, 1E2, 0.1]", want2="[NaN,Infinity,-Infinity,123456789012345678901234567890,100.0,0.1]", region)
  round3: expectRound(text3="\"tab\\t q\\\" s\\/ ctl\\u0001 \\udcffx\"", want3="\"tab\\t q\\\" s/ ctl\\u0001 \xffx\"", region)
  round4: expectRound(text4="\"\xff\xc3\"", want4="\"\xff\xc3\"", region)
  bad1: expectInvalid(bad1Text="[1, 2", five=5, region)
  bad2: expectInvalid(bad2Text="{\"a\" 1}", five, region)
  bad3: expectInvalid(bad3Text="[1,]", three=3, region)
  bad4: expectInvalid(bad4Text="\"abc", zero=0, region)
  bad5: expectInvalid(bad5Text="\"\\x\"", one=1, region)
  bad6: expectInvalid(bad6Text="\"\\u12\"", two=2, region)
  bad7: expectInvalid(bad7Text="1 2", two, region)
  bad8: expectInvalid(bad8Text="\xc3\xa9x", zero, region)
  bad9: expectInvalid(bad9Text="[\xff, 1]", one, region)
  bad10: expectInvalid(bad10Text="-", zero, region)
  bad11: expectInvalid(bad11Text="1.e5", one, region)
  findShape: shape = kernel.stateAt(shapeAt=61440)
  findArgs: args = kernel.stateAt(argsOffset=61952)
  findResults: results = kernel.stateAt(resultsOffset=62016)
  findPayload: payload = kernel.stateAt(payloadOffset=62080)
  parseList: listStatus = parseInto(listText="[5, \"two\", [3]]", region)
  test.assertEqualInt64(zero, listStatus)
  readList: list = resultSlot(zero)
  shapeItem: setShape(one, one, one)
  setList: setNumberArg(zero, list)
  setIndex: setNumberArg(one, two)
  setItemRegion: setAddressArg(two, region)
  itemIt: itemStatus = jsonCall(seven=7, shape, args, results, payload)
  widenItem: itemValue = convert.int32ToInt64(itemStatus)
  test.assertEqualInt64(zero, itemValue)
  readInner: inner = resultSlot(zero)
  shapeAppend: setShape(one, one, zero)
  setInner: setNumberArg(zero, inner)
  setNumber: setNumberArg(one, n42=42)
  appendIt: appended = callJson(fifteen=15)
  test.assertEqualInt64(zero, appended)
  shapeWrite: setShape(one, one, zero)
  setWritten: setNumberArg(zero, list)
  setWriteRegion: setAddressArg(one, region)
  writeIt: written = callJson(seventeen=17)
  test.assertEqualInt64(zero, written)
  expectShared: expectResultText(sharedText="[5,\"two\",[3,42]]")
  setPast: setNumberArg(one, three=3)
  shapePast: setShape(one, one, one)
  setPastList: setNumberArg(zero, list)
  setPastIndex: setNumberArg(one, three)
  setPastRegion: setAddressArg(two, region)
  pastIt: pastStatus = callJson(seven)
  test.assertEqualInt64(three, pastStatus)
  readPast: pastIndex = payloadValue()
  test.assertEqualInt64(three, pastIndex)
  shapeLength: setShape(one, zero, zero)
  setLength: setNumberArg(zero, list)
  lengthIt: lengthStatus = callJson(six=6)
  test.assertEqualInt64(zero, lengthStatus)
  readLength: length = resultSlot(zero)
  test.assertEqualInt64(three, length)
  free: regions.release(region)
  return
