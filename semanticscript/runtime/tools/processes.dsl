module processes "The program's arguments, the environment and secrets, standard input, child processes with their pipes, and foreign libraries"
  path processes
  imports standard.machine standard.system standard.string standard.math standard.compare standard.convert standard.bits standard.logic standard.test memory heap handles regions slots wide tasks files frames
  exports argumentCount argument environmentGet readLine newArguments addArgument processRun processRunCaptured splitCommandLine commandLine secretFromText secretFromEnvironment secretReveal secretMatches secretLength ffiOpen ffiClose ffiBind

capability memoryAccess "Authority to read the command line, the environment, standard input, and a child's output into memory" use machine.memory none

capability systemCalls "Authority to read the command line and the environment, read standard input, and start, wait for, and stop child processes" use system.calls none

## As host.py and the C runtime (D-82): `process.argument 0` is the first word after the program's name on its
## command line, split as CommandLineToArgvW splits it (written here: that function is shell32's); a child process
## gets a command line made as subprocess.list2cmdline makes it, and with runCaptured its three standard streams are
## pipes, written and read a piece at a time between other tasks, so a child that fills one pipe while it is being
## written cannot stall it; a child that is still running when a trap ends the program is stopped (D-51).
## machine.state bytes 768 to 831 belong to this module: 768 the list of the program's arguments (0 until it is
## first asked for), 776 the builder of standard input read but not yet taken, 784 whether standard input has
## ended, 792 a count a system call writes, 800 how many bytes a pipe has to read.
constant argumentsAt "Where the list of the program's arguments is kept, in machine.state" Int64 768

constant stdinAt "Where the builder of standard input read but not yet taken is kept, in machine.state" Int64 776

constant stdinDoneAt "Where whether standard input has ended is kept, in machine.state" Int64 784

constant countedAt "Where a system call writes a count, in machine.state" Int64 792

constant availableAt "Where PeekNamedPipe writes how many bytes a pipe has, in machine.state" Int64 800

constant kindArguments "The kind of a child process's list of arguments" Int64 6

constant kindSecret "The kind of a secret: a heap block of its bytes, then how many" Int64 8

constant kindLibrary "The kind of a foreign library: a heap block holding its module handle" Int64 10

constant notFoundLibrary "ffi.LoadError.notFound, numbered from 1" Int32 1

constant symbolMissing "ffi.LoadError.symbolMissing, numbered from 1" Int32 2

constant pipeBytes "The bytes a pipe to or from a child holds" Int64 65536

constant chunk "How many bytes one read asks for" Int64 65536

constant never "time.Deadline.never" Int64 -1

constant forever "The bound of a loop that waits as long as it takes" Int64 9223372036854775807

constant argumentOutOfRange "process.ArgumentError.outOfRange, numbered from 1" Int32 1

constant missingVariable "environment.MissingError.missing, numbered from 1" Int32 1

constant endOfInput "console.ReadError.endOfInput, numbered from 1" Int32 1

constant tooLong "console.ReadError.tooLong, numbered from 1" Int32 2

constant readTimedOut "console.ReadError.timedOut, numbered from 1" Int32 3

constant readCancelled "console.ReadError.cancelled, numbered from 1" Int32 4

constant readFailed "console.ReadError.failed, numbered from 1" Int32 5

constant runNotFound "process.RunError.notFound, numbered from 1" Int32 1

constant runTimedOut "process.RunError.timedOut, numbered from 1" Int32 2

constant runCancelled "process.RunError.cancelled, numbered from 1" Int32 3

constant runTooLarge "process.RunError.tooLarge, numbered from 1" Int32 4

constant runFailed "process.RunError.failed, numbered from 1" Int32 5

## ---------------------------------------------------------------- small helpers

op stateAt "The address of a byte of machine.state"
  input offset Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findState: state = machine.state()
  findPlace: place = machine.offset(state, offset)
  return place

op byteAt "The byte of a text at a position"
  input text machine.Address copied
  input position Int64 copied
  output Byte
  effect use machine.memory
  uses memoryAccess
:begin
  findByte: place = machine.offset(text, position)
  readByte: byte = machine.loadByte(place)
  return byte

op isBlank "Whether a byte is a space or a tab"
  input byte Byte copied
  output Bool
:begin
  spaceCheck: isSpace = compare.equalByte(byte, space=32)
  tabCheck: isTab = compare.equalByte(byte, tab=9)
  eitherCheck: blank = logic.or(isSpace, isTab)
  return blank

op shorten "Take bytes off the end of a builder"
  input builder machine.Address copied
  input bytes Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  findLength: lengthSlot = machine.offset(builder, eight=8)
  readLength: length = machine.loadInt64(lengthSlot)
  lessOf: shorter = math.subtractInt64(length, bytes)
  storeLength: machine.storeInt64(lengthSlot, shorter)
  return

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

op closeIfOpen "Close an operating-system handle unless it is the address 0"
  input handle machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere: anywhere = machine.zero()
  noneCheck: isNone = machine.equal(handle, anywhere)
  if isNone done close
:close
  closeIt: closed = system.closeHandle(handle)
  goto done
:done
  return

op minimum "The smaller of two whole numbers"
  input left Int64 copied
  input right Int64 copied
  output Int64
:begin
  lessCheck: leftLess = compare.lessThanInt64(left, right)
  if leftLess giveLeft giveRight
:giveLeft
  return left
:giveRight
  return right

## ---------------------------------------------------------------- the command line

op splitCommandLine "Split a command line into its words after the program's name, as CommandLineToArgvW does: blanks separate words outside quotes, 2n backslashes and a quote are n backslashes and a quote that opens or closes, 2n+1 and a quote n backslashes and a literal quote, and the program's name ends at its closing quote or first blank"
  invariant splitsLikeWindows "Gives the words CommandLineToArgvW gives after the first"
  input line machine.Address copied
  input bytes Int64 copied
  input names machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let quotes Int64 0 mut
  let slashes Int64 0 mut
  let open Bool false mut
  let yes Bool true
  let no Bool false
  let quote Byte 34
  let backslash Byte 92
  let afterOpening Int64 1
:begin
  makeWord: word = wide.builderNew()
  emptyCheck: empty = compare.equalInt64(bytes, zero=0)
  if empty finish firstQuote
:firstQuote
  readFirst: first = byteAt(line, zero)
  quotedCheck: quoted = compare.equalByte(first, quote)
  if quoted startQuoted eachProgramByte
:startQuoted
  set at afterOpening
  goto eachQuotedByte
:eachQuotedByte loop=while max=bytes
  quotedEnd: quotedDone = compare.greaterOrEqualInt64(at, bytes)
  if quotedDone skipBlanks readQuoted
:readQuoted in=eachQuotedByte
  readIt: quotedByte = byteAt(line, at)
  stepQuoted: afterQuoted = math.addInt64(at, one=1)
  set at afterQuoted
  closeCheck: closes = compare.equalByte(quotedByte, quote)
  if closes skipBlanks eachQuotedByte
:eachProgramByte loop=while max=bytes
  programEnd: programDone = compare.greaterOrEqualInt64(at, bytes)
  if programDone skipBlanks readProgram
:readProgram in=eachProgramByte
  readProgramByte: programByte = byteAt(line, at)
  programBlank: blankHere = isBlank(programByte)
  if blankHere skipBlanks stepProgram
:stepProgram in=eachProgramByte
  advanceProgram: afterProgram = math.addInt64(at, one)
  set at afterProgram
  goto eachProgramByte
:skipBlanks
  goto eachBlank
:eachBlank loop=while max=bytes
  blankEnd: blanksDone = compare.greaterOrEqualInt64(at, bytes)
  if blanksDone wordsStart readBlank
:readBlank in=eachBlank
  readBlankByte: blankByte = byteAt(line, at)
  blankCheck: isBlankByte = isBlank(blankByte)
  if isBlankByte stepBlank wordsStart
:stepBlank in=eachBlank
  advanceBlank: afterBlank = math.addInt64(at, one)
  set at afterBlank
  goto eachBlank
:wordsStart
  moreCheck: more = compare.lessThanInt64(at, bytes)
  if more openWord finish
:openWord
  set open yes
  goto eachByte
:eachByte loop=while max=bytes
  doneCheck: done = compare.greaterOrEqualInt64(at, bytes)
  if done finish readByte
:readByte in=eachByte
  readWordByte: byte = byteAt(line, at)
  blankWordCheck: blank = isBlank(byte)
  outsideCheck: outside = compare.equalInt64(quotes, zero)
  separatorCheck: separates = logic.and(blank, outside)
  if separates endWord slashCheck
:endWord in=eachByte
  readWord: wordText = wide.builderText(word)
  readWordLength: wordBytes = wide.builderLength(word)
  addWord: handles.addName(names, wordText, wordBytes)
  resetWord: shorten(word, wordBytes)
  set slashes zero
  set open no
  goto eachSeparator
:eachSeparator loop=while max=bytes in=eachByte
  separatorEnd: separatorsDone = compare.greaterOrEqualInt64(at, bytes)
  if separatorsDone eachByte readSeparator
:readSeparator in=eachSeparator
  readSeparatorByte: separatorByte = byteAt(line, at)
  separatorBlank: stillBlank = isBlank(separatorByte)
  if stillBlank stepSeparator reopen
:stepSeparator in=eachSeparator
  advanceSeparator: afterSeparator = math.addInt64(at, one)
  set at afterSeparator
  goto eachSeparator
:reopen in=eachByte
  set open yes
  goto eachByte
:slashCheck in=eachByte
  backslashCheck: isBackslash = compare.equalByte(byte, backslash)
  if isBackslash addSlash quoteCheck
:addSlash in=eachByte
  addBackslash: wide.builderAddByte(word, backslash)
  moreSlashes: slashCount = math.addInt64(slashes, one)
  set slashes slashCount
  stepSlash: afterSlash = math.addInt64(at, one)
  set at afterSlash
  goto eachByte
:quoteCheck in=eachByte
  checkQuote: isQuote = compare.equalByte(byte, quote)
  if isQuote handleQuote addPlain
:handleQuote in=eachByte
  halfOf: half = math.divideInt64(slashes, two=2)
  oddOf: odd = math.remainderInt64(slashes, two)
  evenCheck: even = compare.equalInt64(odd, zero)
  if even evenSlashes oddSlashes
:evenSlashes in=eachByte
  dropHalf: shorten(word, half)
  moreQuotes: quoteCount = math.addInt64(quotes, one)
  set quotes quoteCount
  goto pastQuote
:oddSlashes in=eachByte
  halfAndOne: dropped = math.addInt64(half, one)
  dropMore: shorten(word, dropped)
  addLiteral: wide.builderAddByte(word, quote)
  goto pastQuote
:pastQuote in=eachByte
  stepQuote: afterQuote = math.addInt64(at, one)
  set at afterQuote
  set slashes zero
  goto eachRunQuote
:eachRunQuote loop=while max=bytes in=eachByte
  runEnd: runDone = compare.greaterOrEqualInt64(at, bytes)
  if runDone settleQuotes readRun
:readRun in=eachRunQuote
  readRunByte: runByte = byteAt(line, at)
  runQuoteCheck: runIsQuote = compare.equalByte(runByte, quote)
  if runIsQuote countRun settleQuotes
:countRun in=eachRunQuote
  oneMoreQuote: runQuotes = math.addInt64(quotes, one)
  set quotes runQuotes
  threeCheck: isThree = compare.equalInt64(runQuotes, three=3)
  if isThree literalRun stepRun
:literalRun in=eachRunQuote
  addRunQuote: wide.builderAddByte(word, quote)
  set quotes zero
  goto stepRun
:stepRun in=eachRunQuote
  advanceRun: afterRun = math.addInt64(at, one)
  set at afterRun
  goto eachRunQuote
:settleQuotes in=eachByte
  twoCheck: isTwo = compare.equalInt64(quotes, two)
  if isTwo resetQuotes eachByte
:resetQuotes in=eachByte
  set quotes zero
  goto eachByte
:addPlain in=eachByte
  addByte: wide.builderAddByte(word, byte)
  set slashes zero
  stepPlain: afterPlain = math.addInt64(at, one)
  set at afterPlain
  goto eachByte
:finish
  if open lastWord done2
:lastWord
  readLast: lastText = wide.builderText(word)
  readLastLength: lastBytes = wide.builderLength(word)
  addLast: handles.addName(names, lastText, lastBytes)
  goto done2
:done2
  giveWord: giveBuilder(word)
  return

op programArguments "The words after the program's name on its command line, split the first time they are asked for"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findList: listSlot = stateAt(argumentsAt)
  readList: list = machine.loadAddress(listSlot)
  nowhere: anywhere = machine.zero()
  missingCheck: missing = machine.equal(list, anywhere)
  if missing split give
:give
  return list
:split
  takeList: names = heap.take(twentyFour=24)
  fetchLine: wideLine = system.getCommandLineW()
  countUnits: units = wide.wideUnits(wideLine)
  takeCell: cell = heap.take(eight=8)
  narrowLine: line = wide.narrow(wideLine, units, cell)
  readBytes: bytes = machine.loadInt64(cell)
  splitIt: splitCommandLine(line, bytes, names)
  giveLine: heap.give(line)
  giveCell: heap.give(cell)
  storeList: machine.storeAddress(listSlot, names)
  return names

op argumentCount "process.argumentCount: how many words follow the program's name on its command line"
  invariant countsArguments "The result slot holds the number of arguments"
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readList: names = programArguments()
  countIt: count = handles.nameCount(names)
  storeCount: machine.storeInt64(results, count)
  return

op argument "process.argument: the word at a position after the program's name, into a region; outOfRange with the position past them"
  invariant givesArgument "The result slots hold the argument, or the status is outOfRange"
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
  readIndex: index = slots.argOf(shape, args, zero=0)
  readList: names = programArguments()
  countIt: count = handles.nameCount(names)
  lowCheck: low = compare.lessThanInt64(index, zero)
  highCheck: high = compare.greaterOrEqualInt64(index, count)
  outsideCheck: outside = logic.or(low, high)
  if outside refuse give
:refuse
  status: status1 = slots.failWith(payload, argumentOutOfRange, index)
  return status1
:give
  findName: nameSlot = handles.nameAt(names, index)
  readName: name = machine.loadAddress(nameSlot)
  findLength: lengthSlot = machine.offset(nameSlot, eight=8)
  readLength: length = machine.loadInt64(lengthSlot)
  readRegion: region = slots.addressArg(shape, args, one=1)
  putIt: slots.putText(region, name, length, results)
  return ok

## ---------------------------------------------------------------- the environment

op environmentGet "environment.get: a variable's value, into a region; missing when it is not set (and for an empty name, or one with `=` or a 0 byte in it)"
  invariant readsVariable "The result slots hold the variable's value, or the status is missing"
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
  let equalsText String "="
:begin
  readName: name = files.textAt(shape, args, zero=0)
  readBytes: bytes = files.textBytes(shape, args, zero)
  emptyCheck: empty = compare.equalInt64(bytes, zero)
  if empty refuse equalsCheck
:refuse
  status: status1 = slots.failWith(payload, missingVariable, zero)
  return status1
:equalsCheck
  findEquals: equalsAt = machine.addressOfString(equalsText)
  searchEquals: equalsFound = memory.findBytes(name, bytes, equalsAt, one=1)
  hasEquals: withEquals = compare.greaterOrEqualInt64(equalsFound, zero)
  if withEquals refuse zeroCheck
:zeroCheck
  nulFound: nulAt = findNul(name, bytes)
  hasNul: withNul = compare.greaterOrEqualInt64(nulAt, zero)
  if withNul refuse lookUp
:lookUp
  wideName: nameWide = wide.widen(name, bytes)
  nowhere: anywhere = machine.zero()
  measure: units32 = system.getEnvironmentVariableW(nameWide, anywhere, zero32=0)
  unitsOf: units = convert.int32ToInt64(units32)
  missingCheck: missing = compare.equalInt64(units, zero)
  if missing refuseMissing read
:refuseMissing
  giveNameMissing: heap.give(nameWide)
  status2: missingStatus = slots.failWith(payload, missingVariable, zero)
  return missingStatus
:read
  withEnd: room = math.addInt64(units, one)
  sizeOf: size = math.multiplyInt64(room, two=2)
  takeBuffer: buffer = heap.take(size)
  roomNarrow: room32 = convert.int64ToInt32(room)
  readIt: got32 = system.getEnvironmentVariableW(nameWide, buffer, room32)
  gotOf: got = convert.int32ToInt64(got32)
  takeCell: cell = heap.take(eight=8)
  narrowIt: value = wide.narrow(buffer, got, cell)
  readValueBytes: valueBytes = machine.loadInt64(cell)
  readRegion: region = slots.addressArg(shape, args, one)
  putIt: slots.putText(region, value, valueBytes, results)
  giveName: heap.give(nameWide)
  giveBuffer: heap.give(buffer)
  giveValue: heap.give(value)
  giveCell: heap.give(cell)
  return ok

op findNul "The position of the first 0 byte of a text, or -1"
  input text machine.Address copied
  input bytes Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let notFoundAt Int64 -1
:begin
  goto eachByte
:eachByte loop=while max=bytes
  doneCheck: done = compare.greaterOrEqualInt64(at, bytes)
  if done missing readByte
:readByte in=eachByte
  readIt: byte = byteAt(text, at)
  zeroCheck: isZero = compare.equalByte(byte, zeroByte=0)
  if isZero give advance
:advance in=eachByte
  nextByte: after = math.addInt64(at, one=1)
  set at after
  goto eachByte
:give
  return at
:missing
  return notFoundAt

## ---------------------------------------------------------------- standard input

op stdinBuffer "The builder of standard input read but not yet taken, made the first time it is asked for"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findSlot: slot = stateAt(stdinAt)
  readBuffer: buffer = machine.loadAddress(slot)
  nowhere: anywhere = machine.zero()
  missingCheck: missing = machine.equal(buffer, anywhere)
  if missing make give
:make
  makeBuffer: fresh = wide.builderNew()
  storeBuffer: machine.storeAddress(slot, fresh)
  return fresh
:give
  return buffer

op stdinFill "Read what standard input has next into its builder; its end is noted. Gives 0, or the errno of a read that failed"
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok Int64 0
:begin
  readBuffer: buffer = stdinBuffer()
  findInput: input = system.getStdHandle(stdInput=-10)
  takeChunk: block = heap.take(chunk)
  findCounted: counted = stateAt(countedAt)
  storeNone: machine.storeInt32(counted, zero32=0)
  nowhere: anywhere = machine.zero()
  narrowChunk: chunk32 = convert.int64ToInt32(chunk)
  readIt: read = system.readFile(input, block, chunk32, counted, anywhere)
  failedCheck: refused = compare.equalInt32(read, zero32)
  if refused failure counted2
:failure
  readError: code = system.getLastError()
  brokenCheck: broken = compare.equalInt32(code, brokenPipe=109)
  endCheck: atEnd = compare.equalInt32(code, handleEof=38)
  eitherCheck: ended = logic.or(broken, atEnd)
  if ended noteEnd mapError
:mapError
  giveChunkFailed: heap.give(block)
  mapIt: errno = files.winErrno(code)
  return errno
:counted2
  readCount: got32 = machine.loadInt32(counted)
  widenCount: got = convert.int32ToInt64(got32)
  nothingCheck: nothing = compare.equalInt64(got, zero=0)
  if nothing noteEnd keep
:keep
  addIt: wide.builderAdd(buffer, block, got)
  giveChunk: heap.give(block)
  return ok
:noteEnd
  findDone: doneSlot = stateAt(stdinDoneAt)
  storeDone: machine.storeInt64(doneSlot, one=1)
  giveChunkEnd: heap.give(block)
  return ok

op stdinWait "Wait until standard input has something to read or has ended, letting other tasks run: 0 when it may be read, 1 at the deadline, 2 when the task is cancelled"
  input deadline Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let poll Int64 0 mut
  let ready Int64 0
  let late Int64 1
  let stopped Int64 2
:begin
  findInput: input = system.getStdHandle(stdInput=-10)
  readType: type = system.getFileType(input)
  pipeCheck: isPipe = compare.equalInt32(type, pipeType=3)
  charCheck: isChar = compare.equalInt32(type, charType=2)
  nowhere: anywhere = machine.zero()
  findAvailable: available = stateAt(availableAt)
  goto eachTry
:eachTry loop=while max=forever
  if isPipe peek charTry
:peek in=eachTry
  storeNone: machine.storeInt32(available, zero32=0)
  peekIt: peeked = system.peekNamedPipe(input, anywhere, zero32, anywhere, available, anywhere)
  peekFailed: refused = compare.equalInt32(peeked, zero32)
  readAvailable: count = machine.loadInt32(available)
  someCheck: some = compare.greaterThanInt32(count, zero32)
  readyCheck: canRead = logic.or(refused, some)
  if canRead giveReady pipeWait
:pipeWait in=eachTry
  readNow: moment = tasks.now()
  soon: pollAt = math.addInt64(moment, ten=10)
  set poll pollAt
  neverCheck: isNever = compare.equalInt64(deadline, never)
  earlierCheck: deadlineFirst = compare.lessThanInt64(deadline, pollAt)
  notNever: hasDeadline = logic.not(isNever)
  useCheck: useDeadline = logic.and(hasDeadline, deadlineFirst)
  if useDeadline useDeadlineTime waitPipe
:useDeadlineTime in=eachTry
  set poll deadline
  goto waitPipe
:waitPipe in=eachTry
  waitIt: outcome = tasks.wait(readText="a read of standard input", poll, one=1, anywhere)
  cancelledCheck: isCancelled = compare.equalInt64(outcome, two=2)
  if isCancelled giveStopped pastCheck
:charTry in=eachTry
  if isChar charPoll giveReady
:charPoll in=eachTry
  pollChar: signalled = system.waitForSingleObject(input, zero32)
  signalledCheck: isSignalled = compare.equalInt32(signalled, zero32)
  if isSignalled giveReady charWait
:charWait in=eachTry
  waitChar: charOutcome = tasks.wait(readText, deadline, one, input)
  charCancelled: isCharCancelled = compare.equalInt64(charOutcome, two)
  if isCharCancelled giveStopped pastCheck
:pastCheck in=eachTry
  readLater: later = tasks.now()
  noDeadline: isNeverAgain = compare.equalInt64(deadline, never)
  if isNeverAgain eachTry comparePast
:comparePast in=eachTry
  pastNow: past = compare.greaterOrEqualInt64(later, deadline)
  if past giveLate eachTry
:giveReady
  return ready
:giveLate
  return late
:giveStopped
  return stopped

op readLine "console.readLine: the next line of standard input without its line end (`\\n`, and `\\r` before it), into a region; endOfInput, tooLong (the line is still taken), timedOut, cancelled, or failed"
  invariant readsLine "Gives the next line, or the status says why there is none"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let take Int64 0 mut
  let length Int64 0 mut
  let status Int32 0 mut
  let ok Int32 0
  let lineEnd String "\n"
:begin
  readDeadline: deadline = slots.argOf(shape, args, two=2)
  readLimit: limit = slots.argOf(shape, args, one=1)
  readBuffer: buffer = stdinBuffer()
  findLineEnd: lineEndAt = machine.addressOfString(lineEnd)
  findDone: doneSlot = stateAt(stdinDoneAt)
  goto eachFill
:eachFill loop=while max=forever
  readData: data = wide.builderText(buffer)
  readLength: bytes = wide.builderLength(buffer)
  searchLine: found = memory.findBytes(data, bytes, lineEndAt, one)
  foundCheck: hasLine = compare.greaterOrEqualInt64(found, zero=0)
  if hasLine haveLine endedCheck
:endedCheck in=eachFill
  readDone: done = machine.loadInt64(doneSlot)
  doneCheck: ended = compare.notEqualInt64(done, zero)
  if ended noLine waitCheck
:waitCheck in=eachFill
  neverCheck: isNever = compare.equalInt64(deadline, never)
  if isNever fill waitInput
:waitInput in=eachFill
  waitIt: outcome = stdinWait(deadline)
  lateCheck: isLate = compare.equalInt64(outcome, one)
  if isLate giveLate stoppedCheck
:stoppedCheck in=eachFill
  checkStopped: isStopped = compare.equalInt64(outcome, two)
  if isStopped giveStopped fill
:fill in=eachFill
  fillIt: errno = stdinFill()
  errorCheck: failedRead = compare.notEqualInt64(errno, zero)
  if failedRead giveFailed eachFill
:giveLate
  lateStatus: status1 = slots.failWith(payload, readTimedOut, zero)
  return status1
:giveStopped
  stoppedStatus: status2 = slots.failWith(payload, readCancelled, zero)
  return status2
:giveFailed
  failedStatus: status3 = slots.failWith(payload, readFailed, errno)
  return status3
:haveLine
  withEnd: lineBytes = math.addInt64(found, one)
  set take lineBytes
  goto taken
:noLine
  readLeft: leftData = wide.builderText(buffer)
  readLeftLength: leftBytes = wide.builderLength(buffer)
  set take leftBytes
  nothingCheck: nothing = compare.equalInt64(leftBytes, zero)
  if nothing giveEnd taken
:giveEnd
  endStatus: status4 = slots.failWith(payload, endOfInput, zero)
  return status4
:taken
  readTaken: takenData = wide.builderText(buffer)
  readAll: allBytes = wide.builderLength(buffer)
  set length take
  anyCheck: any = compare.greaterThanInt64(length, zero)
  if any newlineCheck carriageCheck
:newlineCheck
  lastOf: lastAt = math.subtractInt64(length, one)
  readLast: last = byteAt(takenData, lastAt)
  isNewline: endsNewline = compare.equalByte(last, newline=10)
  if endsNewline dropNewline carriageCheck
:dropNewline
  set length lastAt
  goto carriageCheck
:carriageCheck
  anyLeft: anyAfter = compare.greaterThanInt64(length, zero)
  if anyAfter checkCarriage limitCheck
:checkCarriage
  lastAgain: beforeAt = math.subtractInt64(length, one)
  readBefore: before = byteAt(takenData, beforeAt)
  isCarriage: endsCarriage = compare.equalByte(before, carriage=13)
  if endsCarriage dropCarriage limitCheck
:dropCarriage
  set length beforeAt
  goto limitCheck
:limitCheck
  overCheck: over = compare.greaterThanInt64(length, limit)
  if over refuseLong put
:refuseLong
  longStatus: status5 = slots.failWith(payload, tooLong, zero)
  set status status5
  goto consume
:put
  readRegion: region = slots.addressArg(shape, args, zero)
  putIt: slots.putText(region, takenData, length, results)
  goto consume
:consume
  leftOf: rest = math.subtractInt64(allBytes, take)
  findRest: restAt = machine.offset(takenData, take)
  moveRest: machine.copy(takenData, restAt, rest)
  dropTaken: shorten(buffer, take)
  return status

## ---------------------------------------------------------------- child processes

op newArguments "process.newArguments: an empty list of arguments for a child, owned by a region"
  invariant makesArguments "The result slot holds a new Arguments handle with no arguments"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  takeNames: names = heap.take(twentyFour=24)
  readRegion: region = slots.addressArg(shape, args, zero=0)
  makeHandle: handle = handles.newHandle(kindArguments, names, region)
  storeHandle: machine.storeInt64(results, handle)
  return

op addArgument "process.addArgument: add a word to a list of arguments"
  invariant addsArgument "The list holds the word last"
  input shape machine.Address copied
  input args machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findNames: names = handles.objectOf(handle, kindArguments)
  readText: text = files.textAt(shape, args, one=1)
  readBytes: bytes = files.textBytes(shape, args, one)
  addIt: handles.addName(names, text, bytes)
  return

op quoteWord "Add a word to a command line as subprocess.list2cmdline quotes it: in double quotes when it is empty or holds a blank, a quote as \\\", and backslashes doubled where a quote follows them"
  input line machine.Address copied
  input word machine.Address copied
  input bytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let slashes Int64 0 mut
  let tail Int64 0 mut
  let each Int64 0 mut
  let quote Byte 34
  let backslash Byte 92
  let spaceText String " "
  let tabText String "\t"
:begin
  emptyCheck: empty = compare.equalInt64(bytes, zero=0)
  findSpace: spaceAt = machine.addressOfString(spaceText)
  searchSpace: spaceFound = memory.findBytes(word, bytes, spaceAt, one=1)
  findTab: tabAt = machine.addressOfString(tabText)
  searchTab: tabFound = memory.findBytes(word, bytes, tabAt, one)
  hasSpace: withSpace = compare.greaterOrEqualInt64(spaceFound, zero)
  hasTab: withTab = compare.greaterOrEqualInt64(tabFound, zero)
  blankEither: withBlank = logic.or(withSpace, withTab)
  quoteEither: needsQuote = logic.or(empty, withBlank)
  if needsQuote openQuote eachByte
:openQuote
  addOpen: wide.builderAddByte(line, quote)
  goto eachByte
:eachByte loop=while max=bytes
  doneCheck: done = compare.greaterOrEqualInt64(at, bytes)
  if done tailSlashes readByte
:readByte in=eachByte
  readIt: byte = byteAt(word, at)
  slashCheck: isSlash = compare.equalByte(byte, backslash)
  if isSlash countSlash quoteCheck
:countSlash in=eachByte
  moreSlashes: slashCount = math.addInt64(slashes, one)
  set slashes slashCount
  goto advance
:quoteCheck in=eachByte
  checkQuote: isQuote = compare.equalByte(byte, quote)
  if isQuote escapeQuote plain
:escapeQuote in=eachByte
  doubleOf: doubled = math.multiplyInt64(slashes, two=2)
  set each doubled
  goto eachDouble
:eachDouble loop=while max=doubled in=eachByte
  doubleDone: noneLeft = compare.lessOrEqualInt64(each, zero)
  if noneLeft addEscaped addDouble
:addDouble in=eachDouble
  addSlash: wide.builderAddByte(line, backslash)
  lessOne: fewer = math.subtractInt64(each, one)
  set each fewer
  goto eachDouble
:addEscaped in=eachByte
  set slashes zero
  addEscape: wide.builderAddByte(line, backslash)
  addQuote: wide.builderAddByte(line, quote)
  goto advance
:plain in=eachByte
  set each slashes
  goto eachPending
:eachPending loop=while max=bytes in=eachByte
  pendingDone: nonePending = compare.lessOrEqualInt64(each, zero)
  if nonePending addPlain addPending
:addPending in=eachPending
  addPendingSlash: wide.builderAddByte(line, backslash)
  lessPending: fewerPending = math.subtractInt64(each, one)
  set each fewerPending
  goto eachPending
:addPlain in=eachByte
  set slashes zero
  addByte: wide.builderAddByte(line, byte)
  goto advance
:advance in=eachByte
  nextByte: after = math.addInt64(at, one)
  set at after
  goto eachByte
:tailSlashes
  set tail slashes
  if needsQuote doubleTail writeTail
:doubleTail
  twiceTail: tailTwice = math.multiplyInt64(slashes, two)
  set tail tailTwice
  goto writeTail
:writeTail
  set each tail
  boundOf: tailBound = math.multiplyInt64(bytes, two)
  goto eachTail
:eachTail loop=while max=tailBound
  tailDone: noTail = compare.lessOrEqualInt64(each, zero)
  if noTail closeCheck addTail
:addTail in=eachTail
  addTailSlash: wide.builderAddByte(line, backslash)
  lessTail: fewerTail = math.subtractInt64(each, one)
  set each fewerTail
  goto eachTail
:closeCheck
  if needsQuote closeQuote done2
:closeQuote
  addClose: wide.builderAddByte(line, quote)
  goto done2
:done2
  return

op commandLine "A child's command line as subprocess.list2cmdline makes it from the program and its arguments, in a new builder"
  invariant quotesLikePython "Gives the words joined by spaces, each quoted as list2cmdline quotes it"
  input program machine.Address copied
  input programBytes Int64 copied
  input names machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  makeLine: line = wide.builderNew()
  addProgram: quoteWord(line, program, programBytes)
  countIt: count = handles.nameCount(names)
  goto eachWord
:eachWord loop=while max=count
  doneCheck: done = compare.greaterOrEqualInt64(at, count)
  if done finish addWord
:addWord in=eachWord
  addSpace: wide.builderAddByte(line, space=32)
  findName: nameSlot = handles.nameAt(names, at)
  readName: name = machine.loadAddress(nameSlot)
  findLength: lengthSlot = machine.offset(nameSlot, eight=8)
  readLength: length = machine.loadInt64(lengthSlot)
  addIt: quoteWord(line, name, length)
  nextWord: after = math.addInt64(at, one=1)
  set at after
  goto eachWord
:finish
  return line

op makePipe "A pipe for a child's stream: the end the child gets is inheritable, the other is not; stores this program's end, then the child's, at an address"
  input ends machine.Address copied
  input forInput Bool copied
  input security machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findWrite: writeSlot = machine.offset(ends, sixteen=16)
  findRead: readSlot = machine.offset(ends, twentyFour=24)
  narrowBytes: bytes32 = convert.int64ToInt32(pipeBytes)
  makeIt: made = system.createPipe(readSlot, writeSlot, security, bytes32)
  readReadEnd: readEnd = machine.loadAddress(readSlot)
  readWriteEnd: writeEnd = machine.loadAddress(writeSlot)
  findTheirs: theirsSlot = machine.offset(ends, eight=8)
  if forInput inputEnds outputEnds
:inputEnds
  storeOurs: machine.storeAddress(ends, writeEnd)
  storeTheirs: machine.storeAddress(theirsSlot, readEnd)
  keepOurs: kept = system.setHandleInformation(writeEnd, inherit=1, zero32=0)
  return
:outputEnds
  storeOursOut: machine.storeAddress(ends, readEnd)
  storeTheirsOut: machine.storeAddress(theirsSlot, writeEnd)
  keepOursOut: keptOut = system.setHandleInformation(readEnd, inherit, zero32)
  return

op inheritStandard "A child's copy of one of this program's standard handles, inheritable, stored at an address (0 when there is none)"
  input which Int32 copied
  input at machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere: anywhere = machine.zero()
  storeNone: machine.storeAddress(at, anywhere)
  findHandle: handle = system.getStdHandle(which)
  noneCheck: isNone = machine.equal(handle, anywhere)
  handleValue: value = machine.toInt64(handle)
  invalidCheck: invalid = compare.equalInt64(value, minusOne=-1)
  missingCheck: missing = logic.or(isNone, invalid)
  if missing done copy
:copy
  findMe: me = system.getCurrentProcess()
  duplicate: copied = system.duplicateHandle(me, handle, me, at, zero32=0, yes32=1, sameAccess=2)
  goto done
:done
  return

op readPipe "Read what a pipe from a child has into a builder: 1 when it gave something, 0 when it had nothing yet, -1 when it has ended"
  input pipe machine.Address copied
  input into machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let gave Int64 1
  let nothing Int64 0
  let ended Int64 -1
:begin
  nowhere: anywhere = machine.zero()
  findAvailable: available = stateAt(availableAt)
  storeNone: machine.storeInt32(available, zero32=0)
  peekIt: peeked = system.peekNamedPipe(pipe, anywhere, zero32, anywhere, available, anywhere)
  peekFailed: refused = compare.equalInt32(peeked, zero32)
  if refused giveEnded countIt
:countIt
  readAvailable: count32 = machine.loadInt32(available)
  widenCount: count = convert.int32ToInt64(count32)
  someCheck: some = compare.greaterThanInt64(count, zero=0)
  if some read giveNothing
:read
  smaller: want = minimum(count, chunk)
  takeBlock: block = heap.take(want)
  narrowWant: want32 = convert.int64ToInt32(want)
  findCounted: counted = stateAt(countedAt)
  readIt: read32 = system.readFile(pipe, block, want32, counted, anywhere)
  readCount: got32 = machine.loadInt32(counted)
  widenGot: got = convert.int32ToInt64(got32)
  addIt: wide.builderAdd(into, block, got)
  giveBlock: heap.give(block)
  return gave
:giveNothing
  return nothing
:giveEnded
  return ended

op runChild "Run a child to its end or stop it at the deadline or a cancel; with `captured`, its streams are pipes: the input written to its standard input, its output and errors read into builders. Gives 0 with the exit code at an address, or an error's number with its payload stored"
  input program machine.Address copied
  input programBytes Int64 copied
  input names machine.Address copied
  input deadline Int64 copied
  input captured Bool copied
  input input machine.Address copied
  input inputBytes Int64 copied
  input out machine.Address copied
  input errors machine.Address copied
  input codeAt machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let written Int64 0 mut
  let inputOpen Bool false mut
  let outOpen Bool false mut
  let errorsOpen Bool false mut
  let progress Bool false mut
  let poll Int64 0 mut
  let yes Bool true
  let no Bool false
  let ok Int32 0
  let childText String "a wait for a child process"
:begin
  nowhere: anywhere = machine.zero()
  makeLine: line = commandLine(program, programBytes, names)
  fetchLineText: lineText = wide.builderText(line)
  readLineBytes: lineBytes = wide.builderLength(line)
  wideLine: commandWide = wide.widen(lineText, lineBytes)
  giveLine: giveBuilder(line)
  takeSecurity: security = heap.take(twentyFour=24)
  storeSecurityLength: machine.storeInt32(security, twentyFour32=24)
  findInherit: inheritSlot = machine.offset(security, sixteen=16)
  storeInherit: machine.storeInt32(inheritSlot, one32=1)
  takeStartup: startup = heap.take(oneOhFour=104)
  storeStartupLength: machine.storeInt32(startup, oneOhFour32=104)
  findFlags: flagsSlot = machine.offset(startup, sixty=60)
  storeFlags: machine.storeInt32(flagsSlot, useStandardHandles=256)
  findInputSlot: childInput = machine.offset(startup, eighty=80)
  findOutputSlot: childOutput = machine.offset(startup, eightyEight=88)
  findErrorSlot: childError = machine.offset(startup, ninetySix=96)
  takeInformation: information = heap.take(twentyFour)
  takeEnds: ends = heap.take(oneTwentyEight=128)
  findOutEnds: outEnds = machine.offset(ends, thirtyTwo=32)
  findErrorEnds: errorEnds = machine.offset(ends, sixtyFour=64)
  findPeek: peekSlot = machine.offset(ends, ninetySix=96)
  if captured pipes inherit
:pipes
  inputPipe: makePipe(ends, yes, security)
  outputPipe: makePipe(outEnds, no, security)
  errorPipe: makePipe(errorEnds, no, security)
  findTheirInput: theirInputSlot = machine.offset(ends, eight=8)
  readTheirInput: theirInput = machine.loadAddress(theirInputSlot)
  findMe: me = system.getCurrentProcess()
  keepPeek: peekCopied = system.duplicateHandle(me, theirInput, me, peekSlot, zero32=0, zero32, sameAccess=2)
  storeChildInput: machine.storeAddress(childInput, theirInput)
  findTheirOutput: theirOutputSlot = machine.offset(outEnds, eight)
  readTheirOutput: theirOutput = machine.loadAddress(theirOutputSlot)
  storeChildOutput: machine.storeAddress(childOutput, theirOutput)
  findTheirError: theirErrorSlot = machine.offset(errorEnds, eight)
  readTheirError: theirError = machine.loadAddress(theirErrorSlot)
  storeChildError: machine.storeAddress(childError, theirError)
  goto start
:inherit
  inheritInput: inheritStandard(stdInput=-10, childInput)
  inheritOutput: inheritStandard(stdOutput=-11, childOutput)
  inheritError: inheritStandard(stdError=-12, childError)
  goto start
:start
  createIt: started = system.createProcessW(anywhere, commandWide, anywhere, anywhere, one32, zero32, anywhere, anywhere, startup, information)
  readStartError: startError = system.getLastError()
  giveCommand: heap.give(commandWide)
  readChildInput: givenInput = machine.loadAddress(childInput)
  closeChildInput: closeIfOpen(givenInput)
  readChildOutput: givenOutput = machine.loadAddress(childOutput)
  closeChildOutput: closeIfOpen(givenOutput)
  readChildError: givenError = machine.loadAddress(childError)
  closeChildError: closeIfOpen(givenError)
  startedCheck: notStarted = compare.equalInt32(started, zero32)
  if notStarted refuseStart running
:refuseStart
  readOurInput: ourInputFailed = machine.loadAddress(ends)
  closeOurInput: closeIfOpen(ourInputFailed)
  readOurOutput: ourOutputFailed = machine.loadAddress(outEnds)
  closeOurOutput: closeIfOpen(ourOutputFailed)
  readOurError: ourErrorFailed = machine.loadAddress(errorEnds)
  closeOurError: closeIfOpen(ourErrorFailed)
  readPeekFailed: peekFailed = machine.loadAddress(peekSlot)
  closePeekFailed: closeIfOpen(peekFailed)
  giveSecurityFailed: heap.give(security)
  giveStartupFailed: heap.give(startup)
  giveInformationFailed: heap.give(information)
  giveEndsFailed: heap.give(ends)
  missingCheck: isMissing = compare.equalInt32(startError, two32=2)
  pathCheck: isPathMissing = compare.equalInt32(startError, three32=3)
  eitherCheck: notThere = logic.or(isMissing, isPathMissing)
  if notThere giveNotFound giveFailed
:giveNotFound
  notFoundStatus: status1 = slots.failWith(payload, runNotFound, zero=0)
  return status1
:giveFailed
  mapError: errno = files.winErrno(startError)
  failedStatus: status2 = slots.failWith(payload, runFailed, errno)
  return status2
:running
  readProcess: process = machine.loadAddress(information)
  findThread: threadSlot = machine.offset(information, eight)
  readThread: thread = machine.loadAddress(threadSlot)
  closeThread: closedThread = system.closeHandle(thread)
  holdIt: frames.holdResource(two=2, process)
  readOurs: ourInput = machine.loadAddress(ends)
  readOurOut: ourOut = machine.loadAddress(outEnds)
  readOurErrors: ourErrors = machine.loadAddress(errorEnds)
  readPeek: peekEnd = machine.loadAddress(peekSlot)
  if captured startPump waitChild
:startPump
  set outOpen yes
  set errorsOpen yes
  anyInput: hasInput = compare.greaterThanInt64(inputBytes, zero)
  if hasInput keepInput closeInput
:keepInput
  set inputOpen yes
  goto eachPump
:closeInput
  closeInputNow: closeIfOpen(ourInput)
  closePeekNow: closeIfOpen(peekEnd)
  goto eachPump
:eachPump loop=while max=forever
  set progress no
  if inputOpen writeSome readOut
:writeSome in=eachPump
  findAvailable: available = stateAt(availableAt)
  storeNone: machine.storeInt32(available, zero32)
  peekInput: peeked = system.peekNamedPipe(peekEnd, anywhere, zero32, anywhere, available, anywhere)
  readQueued: queued32 = machine.loadInt32(available)
  widenQueued: queued = convert.int32ToInt64(queued32)
  freeOf: free = math.subtractInt64(pipeBytes, queued)
  freeCheck: hasRoom = compare.greaterThanInt64(free, zero)
  if hasRoom writeInput inputDoneCheck
:writeInput in=eachPump
  leftOf: left = math.subtractInt64(inputBytes, written)
  sizeOf: want = minimum(free, left)
  findFrom: from = machine.offset(input, written)
  narrowWant: want32 = convert.int64ToInt32(want)
  findCounted: counted = stateAt(countedAt)
  writeIt: wrote = system.writeFile(ourInput, from, want32, counted, anywhere)
  wroteCheck: refused = compare.equalInt32(wrote, zero32)
  if refused inputBroken countWritten
:inputBroken in=eachPump
  set written inputBytes
  goto inputDoneCheck
:countWritten in=eachPump
  readWrote: done32 = machine.loadInt32(counted)
  widenWrote: doneBytes = convert.int32ToInt64(done32)
  addWritten: moreWritten = math.addInt64(written, doneBytes)
  set written moreWritten
  set progress yes
  goto inputDoneCheck
:inputDoneCheck in=eachPump
  allCheck: allWritten = compare.greaterOrEqualInt64(written, inputBytes)
  if allWritten finishInput readOut
:finishInput in=eachPump
  closeInputEnd: closeIfOpen(ourInput)
  closePeekEnd: closeIfOpen(peekEnd)
  set inputOpen no
  set progress yes
  goto readOut
:readOut in=eachPump
  if outOpen pumpOut readErrors
:pumpOut in=eachPump
  readOutPipe: outResult = readPipe(ourOut, out)
  outEndCheck: outEnded = compare.lessThanInt64(outResult, zero)
  if outEnded endOut outGaveCheck
:endOut in=eachPump
  closeOut: closeIfOpen(ourOut)
  set outOpen no
  set progress yes
  goto readErrors
:outGaveCheck in=eachPump
  outGave: gotOut = compare.greaterThanInt64(outResult, zero)
  if gotOut outProgress readErrors
:outProgress in=eachPump
  set progress yes
  goto readErrors
:readErrors in=eachPump
  if errorsOpen pumpErrors pumpCheck
:pumpErrors in=eachPump
  readErrorPipe: errorResult = readPipe(ourErrors, errors)
  errorEndCheck: errorEnded = compare.lessThanInt64(errorResult, zero)
  if errorEnded endErrors errorGaveCheck
:endErrors in=eachPump
  closeErrors: closeIfOpen(ourErrors)
  set errorsOpen no
  set progress yes
  goto pumpCheck
:errorGaveCheck in=eachPump
  errorGave: gotError = compare.greaterThanInt64(errorResult, zero)
  if gotError errorProgress pumpCheck
:errorProgress in=eachPump
  set progress yes
  goto pumpCheck
:pumpCheck in=eachPump
  bothOpen: streamsOpen = logic.or(outOpen, errorsOpen)
  if streamsOpen pumpDeadline pumpDone
:pumpDeadline in=eachPump
  readPumpNow: pumpMoment = tasks.now()
  pumpNever: pumpNoDeadline = compare.equalInt64(deadline, never)
  if pumpNoDeadline pumpPause pumpPast
:pumpPast in=eachPump
  pumpPastCheck: pumpLate = compare.greaterOrEqualInt64(pumpMoment, deadline)
  if pumpLate stopLate pumpPause
:pumpPause in=eachPump
  if progress eachPump pumpWait
:pumpWait in=eachPump
  pollSoon: soon = math.addInt64(pumpMoment, one=1)
  set poll soon
  earlierCheck: deadlineFirst = compare.lessThanInt64(deadline, soon)
  notNever: hasDeadline = logic.not(pumpNoDeadline)
  useCheck: useDeadline = logic.and(hasDeadline, deadlineFirst)
  if useDeadline useDeadlineTime waitPump
:useDeadlineTime in=eachPump
  set poll deadline
  goto waitPump
:waitPump in=eachPump
  waitIt: outcome = tasks.wait(childText, poll, one, process)
  cancelledCheck: isCancelled = compare.equalInt64(outcome, two)
  if isCancelled stopCancelled eachPump
:pumpDone
  if inputOpen closeLeftInput waitChild
:closeLeftInput
  closeLeft: closeIfOpen(ourInput)
  closeLeftPeek: closeIfOpen(peekEnd)
  goto waitChild
:waitChild
  goto eachWait
:eachWait loop=while max=forever
  pollProcess: exited = system.waitForSingleObject(process, zero32)
  exitedCheck: hasExited = compare.equalInt32(exited, zero32)
  if hasExited finished waitDeadline
:waitDeadline in=eachWait
  readWaitNow: waitMoment = tasks.now()
  waitNever: waitNoDeadline = compare.equalInt64(deadline, never)
  if waitNoDeadline waitMore waitPast
:waitPast in=eachWait
  waitPastCheck: waitLate = compare.greaterOrEqualInt64(waitMoment, deadline)
  if waitLate stopLate waitMore
:waitMore in=eachWait
  waitOnce: waitOutcome = tasks.wait(childText, deadline, one, process)
  waitCancelledCheck: waitCancelled = compare.equalInt64(waitOutcome, two)
  if waitCancelled stopCancelled eachWait
:stopLate
  stopIt: stoppedLate = system.terminateProcess(process, one32)
  closeOutLate: closeIfOpen(ourOut)
  closeErrorsLate: closeIfOpen(ourErrors)
  letGoLate: frames.letGoResource(process)
  closeLate: closedLate = system.closeHandle(process)
  giveSecurityLate: heap.give(security)
  giveStartupLate: heap.give(startup)
  giveInformationLate: heap.give(information)
  giveEndsLate: heap.give(ends)
  lateStatus: status3 = slots.failWith(payload, runTimedOut, zero)
  return status3
:stopCancelled
  stopCancel: stoppedCancel = system.terminateProcess(process, one32)
  closeOutCancel: closeIfOpen(ourOut)
  closeErrorsCancel: closeIfOpen(ourErrors)
  letGoCancel: frames.letGoResource(process)
  closeCancel: closedCancel = system.closeHandle(process)
  giveSecurityCancel: heap.give(security)
  giveStartupCancel: heap.give(startup)
  giveInformationCancel: heap.give(information)
  giveEndsCancel: heap.give(ends)
  cancelStatus: status4 = slots.failWith(payload, runCancelled, zero)
  return status4
:finished
  readCode: gotCode = system.getExitCodeProcess(process, codeAt)
  letGo: frames.letGoResource(process)
  closeProcess: closedProcess = system.closeHandle(process)
  giveSecurity: heap.give(security)
  giveStartup: heap.give(startup)
  giveInformation: heap.give(information)
  giveEnds: heap.give(ends)
  return ok

op processRun "process.run: run a program with arguments to its end, sharing this program's streams; its exit code, or notFound, timedOut, cancelled, failed"
  invariant runsChild "The result slot holds the child's exit code, or the status is an error"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let no Bool false
  let ok Int32 0
:begin
  readProgram: program = files.textAt(shape, args, zero=0)
  readProgramBytes: programBytes = files.textBytes(shape, args, zero)
  readHandle: handle = slots.argOf(shape, args, one=1)
  findNames: names = handles.objectOf(handle, kindArguments)
  readDeadline: deadline = slots.argOf(shape, args, two=2)
  nowhere: anywhere = machine.zero()
  takeCode: codeAt = heap.take(eight=8)
  runIt: status = runChild(program, programBytes, names, deadline, no, anywhere, zero, anywhere, anywhere, codeAt, payload)
  failedCheck: refused = compare.notEqualInt32(status, ok)
  if refused giveError giveCode
:giveError
  giveCodeFailed: heap.give(codeAt)
  return status
:giveCode
  readCode: code32 = machine.loadInt32(codeAt)
  widenCode: code = convert.int32ToInt64(code32)
  storeCode: machine.storeInt64(results, code)
  giveCodeCell: heap.give(codeAt)
  return ok

op processRunCaptured "process.runCaptured: run a program with arguments, its standard input given and its output and errors kept (each at most a number of bytes, tooLarge past it), into a region"
  invariant capturesChild "The result slots hold the exit code, the output, and the errors, or the status is an error"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let yes Bool true
  let ok Int32 0
:begin
  readProgram: program = files.textAt(shape, args, zero=0)
  readProgramBytes: programBytes = files.textBytes(shape, args, zero)
  readHandle: handle = slots.argOf(shape, args, one=1)
  findNames: names = handles.objectOf(handle, kindArguments)
  readInput: input = files.textAt(shape, args, two=2)
  readInputBytes: inputBytes = files.textBytes(shape, args, two)
  readRegion: region = slots.addressArg(shape, args, three=3)
  readLimit: limit = slots.argOf(shape, args, four=4)
  readDeadline: deadline = slots.argOf(shape, args, five=5)
  makeOut: out = wide.builderNew()
  makeErrors: errors = wide.builderNew()
  takeCode: codeAt = heap.take(eight=8)
  runIt: status = runChild(program, programBytes, names, deadline, yes, input, inputBytes, out, errors, codeAt, payload)
  failedCheck: refused = compare.notEqualInt32(status, ok)
  if refused giveError sizeCheck
:giveError
  giveOutFailed: giveBuilder(out)
  giveErrorsFailed: giveBuilder(errors)
  giveCodeFailed: heap.give(codeAt)
  return status
:sizeCheck
  readOut: outText = wide.builderText(out)
  readOutBytes: outBytes = wide.builderLength(out)
  readErrors: errorsText = wide.builderText(errors)
  readErrorsBytes: errorsBytes = wide.builderLength(errors)
  outOver: outLarge = compare.greaterThanInt64(outBytes, limit)
  errorsOver: errorsLarge = compare.greaterThanInt64(errorsBytes, limit)
  eitherOver: large = logic.or(outLarge, errorsLarge)
  if large refuseLarge give
:refuseLarge
  giveOutLarge: giveBuilder(out)
  giveErrorsLarge: giveBuilder(errors)
  giveCodeLarge: heap.give(codeAt)
  largeStatus: status2 = slots.failWith(payload, runTooLarge, zero)
  return status2
:give
  readCode: code32 = machine.loadInt32(codeAt)
  widenCode: code = convert.int32ToInt64(code32)
  storeCode: machine.storeInt64(results, code)
  findOutSlots: outSlots = machine.offset(results, eight=8)
  putOut: slots.putText(region, outText, outBytes, outSlots)
  findErrorSlots: errorSlots = machine.offset(results, twentyFour=24)
  putErrors: slots.putText(region, errorsText, errorsBytes, errorSlots)
  giveOut: giveBuilder(out)
  giveErrors: giveBuilder(errors)
  giveCodeCell: heap.give(codeAt)
  return ok

## ---------------------------------------------------------------- secrets

op makeSecret "A new Secret handle owned by a region, holding a copy of some bytes"
  input data machine.Address copied
  input bytes Int64 copied
  input region machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  takeSecret: secret = heap.take(sixteen=16)
  takeBytes: copy = heap.take(bytes)
  copyIn: machine.copy(copy, data, bytes)
  storeBytes: machine.storeAddress(secret, copy)
  findLength: lengthSlot = machine.offset(secret, eight=8)
  storeLength: machine.storeInt64(lengthSlot, bytes)
  makeHandle: handle = handles.newHandle(kindSecret, secret, region)
  return handle

op secretFromText "secret.fromText: a Secret holding a text, owned by a region"
  invariant keepsText "The result slot holds a Secret whose bytes are the text's"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readText: text = files.textAt(shape, args, zero=0)
  readBytes: bytes = files.textBytes(shape, args, zero)
  readRegion: region = slots.addressArg(shape, args, one=1)
  makeIt: handle = makeSecret(text, bytes, region)
  storeHandle: machine.storeInt64(results, handle)
  return

op secretFromEnvironment "secret.fromEnvironment: a Secret holding a variable's value, owned by a region; missing when it is not set"
  invariant keepsVariable "The result slot holds a Secret of the variable's value, or the status is missing"
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
  takeSlots: value = heap.take(sixteen=16)
  readIt: status = environmentGet(shape, args, value, payload)
  failedCheck: refused = compare.notEqualInt32(status, ok)
  if refused giveError keep
:giveError
  giveSlots: heap.give(value)
  return status
:keep
  readValue: text = machine.loadAddress(value)
  findLength: lengthSlot = machine.offset(value, eight=8)
  readLength: bytes = machine.loadInt64(lengthSlot)
  readRegion: region = slots.addressArg(shape, args, one=1)
  makeIt: handle = makeSecret(text, bytes, region)
  storeHandle: machine.storeInt64(results, handle)
  giveValue: heap.give(value)
  return ok

op secretReveal "secret.reveal: a Secret's text, into a region"
  invariant revealsText "The result slots hold the Secret's bytes"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findSecret: secret = handles.objectOf(handle, kindSecret)
  readBytes: data = machine.loadAddress(secret)
  findLength: lengthSlot = machine.offset(secret, eight=8)
  readLength: bytes = machine.loadInt64(lengthSlot)
  readRegion: region = slots.addressArg(shape, args, one=1)
  putIt: slots.putText(region, data, bytes, results)
  return

op secretMatches "secret.matches: whether a text is the Secret's, compared in time that depends on the lengths only, as hmac.compare_digest compares"
  invariant matchesText "The result slot holds 1 when the text's bytes are the Secret's, otherwise 0"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let differ Int64 0 mut
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findSecret: secret = handles.objectOf(handle, kindSecret)
  readBytes: data = machine.loadAddress(secret)
  findLength: lengthSlot = machine.offset(secret, eight=8)
  readLength: bytes = machine.loadInt64(lengthSlot)
  readCandidate: candidate = files.textAt(shape, args, one=1)
  readCandidateBytes: candidateBytes = files.textBytes(shape, args, one)
  sameLength: equalLength = compare.equalInt64(bytes, candidateBytes)
  if equalLength eachByte different
:eachByte loop=while max=bytes
  doneCheck: done = compare.greaterOrEqualInt64(at, bytes)
  if done decide compareByte
:compareByte in=eachByte
  readLeft: left = byteAt(data, at)
  readRight: right = byteAt(candidate, at)
  widenLeft: leftValue = convert.byteToInt64(left)
  widenRight: rightValue = convert.byteToInt64(right)
  mixIt: mixed = bits.xorInt64(leftValue, rightValue)
  keepIt: kept = bits.orInt64(differ, mixed)
  set differ kept
  nextByte: after = math.addInt64(at, one)
  set at after
  goto eachByte
:decide
  sameCheck: same = compare.equalInt64(differ, zero)
  if same matched different
:matched
  storeYes: machine.storeInt64(results, one)
  return
:different
  storeNo: machine.storeInt64(results, zero)
  return

op secretLength "secret.length: how many bytes a Secret holds"
  invariant countsSecret "The result slot holds the Secret's length"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findSecret: secret = handles.objectOf(handle, kindSecret)
  findLength: lengthSlot = machine.offset(secret, eight=8)
  readLength: bytes = machine.loadInt64(lengthSlot)
  storeLength: machine.storeInt64(results, bytes)
  return

## ---------------------------------------------------------------- foreign libraries

op loadNamed "LoadLibraryW of a UTF-8 name; the address 0 when it cannot be loaded"
  input name machine.Address copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  wideName: wideText = wide.widen(name, bytes)
  loadIt: library = system.loadLibraryW(wideText)
  giveName: heap.give(wideText)
  return library

op ffiOpen "ffi.open: load a library by name, `c` naming the C library (ucrtbase, else msvcrt), as host.py loads it with ctypes; notFound when none loads"
  invariant loadsLibrary "The result slot holds a Library handle, or the status is notFound"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let library Int64 0 mut
  let ok Int32 0
  let cName String "c"
  let ucrt String "ucrtbase"
  let msvcrt String "msvcrt"
:begin
  readName: name = files.textAt(shape, args, zero=0)
  readBytes: bytes = files.textBytes(shape, args, zero)
  findC: cAt = machine.addressOfString(cName)
  compareC: same = memory.bytesEqual(name, bytes, cAt, one=1)
  cCheck: isC = compare.notEqualInt32(same, zero32=0)
  if isC loadUcrt loadIt
:loadUcrt
  findUcrt: ucrtAt = machine.addressOfString(ucrt)
  ucrtLength: ucrtBytes = string.byteLength(ucrt)
  loadUcrtIt: ucrtLibrary = loadNamed(ucrtAt, ucrtBytes)
  ucrtValue: ucrtNumber = machine.toInt64(ucrtLibrary)
  set library ucrtNumber
  ucrtCheck: noUcrt = compare.equalInt64(ucrtNumber, zero)
  if noUcrt loadMsvcrt loaded
:loadMsvcrt
  findMsvcrt: msvcrtAt = machine.addressOfString(msvcrt)
  msvcrtLength: msvcrtBytes = string.byteLength(msvcrt)
  loadMsvcrtIt: msvcrtLibrary = loadNamed(msvcrtAt, msvcrtBytes)
  msvcrtValue: msvcrtNumber = machine.toInt64(msvcrtLibrary)
  set library msvcrtNumber
  goto loaded
:loadIt
  loadNamedIt: namedLibrary = loadNamed(name, bytes)
  namedValue: namedNumber = machine.toInt64(namedLibrary)
  set library namedNumber
  goto loaded
:loaded
  missingCheck: missing = compare.equalInt64(library, zero)
  if missing refuse give
:refuse
  status: status1 = slots.failWith(payload, notFoundLibrary, zero)
  return status1
:give
  takeLibrary: object = heap.take(eight=8)
  storeLibrary: machine.storeInt64(object, library)
  nowhere: anywhere = machine.zero()
  makeHandle: handle = handles.newHandle(kindLibrary, object, anywhere)
  storeHandle: machine.storeInt64(results, handle)
  return ok

op ffiClose "ffi.close: give back a Library handle; the library stays loaded, as under the C runtime"
  invariant closesLibrary "The handle is closed"
  input shape machine.Address copied
  input args machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findLibrary: object = handles.objectOf(handle, kindLibrary)
  dropIt: handles.drop(handle)
  giveIt: heap.give(object)
  return

op ffiBind "ffi.Function.bind: the address of a library's function by its name, which compiled code calls as the operation type says; symbolMissing when the library has none"
  invariant bindsSymbol "The result slot holds the function's address, or the status is symbolMissing"
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
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findLibrary: object = handles.objectOf(handle, kindLibrary)
  readLibrary: library = machine.loadAddress(object)
  readName: name = files.textAt(shape, args, one=1)
  readBytes: bytes = files.textBytes(shape, args, one)
  copyName: cName = files.copyBytes(name, bytes)
  findIt: function = system.getProcAddress(library, cName)
  giveName: heap.give(cName)
  functionValue: address = machine.toInt64(function)
  missingCheck: missing = compare.equalInt64(address, zero)
  if missing refuse give
:refuse
  status: status1 = slots.failWith(payload, symbolMissing, zero)
  return status1
:give
  storeAddress: machine.storeInt64(results, address)
  return ok

@tests

## Tests build a call's shape and slots in the last 4 KiB of machine.state: the shape from byte 61440, the
## arguments from 61952 (eight slots), the results from 62016, the payload at 62080.

op testShape "Make the tests' shape from the slot counts of up to six parameters (0 for none) and give it"
  input first Int64 copied
  input second Int64 copied
  input third Int64 copied
  input fourth Int64 copied
  input fifth Int64 copied
  input sixth Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let start Int64 0 mut
  let params Int64 0 mut
:begin
  findShape: shape = stateAt(shapeAt=61440)
  findCounts: counts = stateAt(countsAt=62208)
  storeFirst: machine.storeInt64(counts, first)
  findSecond: secondSlot = machine.offset(counts, eight=8)
  storeSecond: machine.storeInt64(secondSlot, second)
  findThird: thirdSlot = machine.offset(counts, sixteen=16)
  storeThird: machine.storeInt64(thirdSlot, third)
  findFourth: fourthSlot = machine.offset(counts, twentyFour=24)
  storeFourth: machine.storeInt64(fourthSlot, fourth)
  findFifth: fifthSlot = machine.offset(counts, thirtyTwo=32)
  storeFifth: machine.storeInt64(fifthSlot, fifth)
  findSixth: sixthSlot = machine.offset(counts, forty=40)
  storeSixth: machine.storeInt64(sixthSlot, sixth)
  goto eachParam
:eachParam loop=while max=six
  doneCheck: done = compare.greaterOrEqualInt64(at, six=6)
  if done finish readCount
:readCount in=eachParam
  countOffset: countAt = math.multiplyInt64(at, eight)
  findCount: countSlot = machine.offset(counts, countAt)
  loadCount: count = machine.loadInt64(countSlot)
  presentCheck: present = compare.greaterThanInt64(count, zero=0)
  if present place finish
:place in=eachParam
  shapeCountOffset: shapeCountAt = math.addInt64(countAt, forty)
  findShapeCount: shapeCount = machine.offset(shape, shapeCountAt)
  storeCount: machine.storeInt64(shapeCount, count)
  shapeStartOffset: shapeStartAt = math.addInt64(countAt, twoThirtyTwo=232)
  findShapeStart: shapeStart = machine.offset(shape, shapeStartAt)
  storeStart: machine.storeInt64(shapeStart, start)
  moveStart: nextStart = math.addInt64(start, count)
  set start nextStart
  nextParam: after = math.addInt64(at, one=1)
  set at after
  set params after
  goto eachParam
:finish
  findParams: paramsSlot = machine.offset(shape, twentyFourAgain=24)
  storeParams: machine.storeInt64(paramsSlot, params)
  return shape

op argSlot "The address of an argument slot of the tests' call"
  input slot Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  offsetOf: offset = math.multiplyInt64(slot, eight=8)
  withBase: place = math.addInt64(offset, argsOffset=61952)
  findSlot: address = stateAt(place)
  return address

op setArg "Set an argument slot of the tests' call to a number"
  input slot Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  findSlot: address = argSlot(slot)
  storeIt: machine.storeInt64(address, value)
  return

op setAddressArg "Set an argument slot of the tests' call to an address"
  input slot Int64 copied
  input value machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  findSlot: address = argSlot(slot)
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
  findSlot: address = argSlot(slot)
  storeAddress: machine.storeAddress(address, textAt)
  findLength: lengthSlot = machine.offset(address, eight=8)
  storeLength: machine.storeInt64(lengthSlot, bytes)
  return

op expectText "Compare a text at an address with what is expected"
  input text machine.Address copied
  input bytes Int64 copied
  input wanted String borrowed
  effect use machine.memory
  uses memoryAccess
:begin
  findWanted: wantedAt = machine.addressOfString(wanted)
  wantedLength: wantedBytes = string.byteLength(wanted)
  compareLength: test.assertEqualInt64(wantedBytes, bytes)
  compareText: same = memory.bytesEqual(text, bytes, wantedAt, wantedBytes)
  sameWide: sameValue = convert.int32ToInt64(same)
  compareIt: test.assertEqualInt64(one=1, sameValue)
  return

op expectName "Compare a name of a list with what is expected"
  input names machine.Address copied
  input position Int64 copied
  input wanted String borrowed
  effect use machine.memory
  uses memoryAccess
:begin
  findName: nameSlot = handles.nameAt(names, position)
  readName: name = machine.loadAddress(nameSlot)
  findLength: lengthSlot = machine.offset(nameSlot, eight=8)
  readLength: length = machine.loadInt64(lengthSlot)
  compareIt: expectText(name, length, wanted)
  return

op expectStatus "Compare a call's status with what is expected"
  input wanted Int64 copied
  input status Int32 copied
:begin
  widenStatus: statusValue = convert.int32ToInt64(status)
  compareIt: test.assertEqualInt64(wanted, statusValue)
  return

op expectSlotText "Compare the text in two result slots with what is expected"
  input slot machine.Address copied
  input wanted String borrowed
  effect use machine.memory
  uses memoryAccess
:begin
  readText: text = machine.loadAddress(slot)
  findLength: lengthSlot = machine.offset(slot, eight=8)
  readLength: length = machine.loadInt64(lengthSlot)
  compareIt: expectText(text, length, wanted)
  return

test splitTest "A command line splits into words as CommandLineToArgvW splits it, and a child's command line is quoted as subprocess.list2cmdline quotes it"
  verifies splitCommandLine splitsLikeWindows
  verifies commandLine quotesLikePython
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let first String "prog.exe \"a b\" c\\\"d e\\\\\"f g\" \"\" h"
  let second String "p a\\\\\\b \"c\\\\\" d\"\"e \"\"\"f\"\"\" \"\""
  let program String "prog"
  let listed String "prog \"a b\" \"\" x\\\"y back\\ t\\\\\\\"q"
:begin
  takeFirst: firstNames = heap.take(twentyFour=24)
  findFirst: firstAt = machine.addressOfString(first)
  firstLength: firstBytes = string.byteLength(first)
  splitFirst: splitCommandLine(firstAt, firstBytes, firstNames)
  countFirst: firstCount = handles.nameCount(firstNames)
  expectFirstCount: test.assertEqualInt64(five=5, firstCount)
  expectA: expectName(firstNames, zero=0, wordA="a b")
  expectB: expectName(firstNames, one=1, wordB="c\"d")
  expectC: expectName(firstNames, two=2, wordC="e\\f g")
  expectD: expectName(firstNames, three=3, wordD="")
  expectE: expectName(firstNames, four=4, wordE="h")
  takeSecond: secondNames = heap.take(twentyFour)
  findSecond: secondAt = machine.addressOfString(second)
  secondLength: secondBytes = string.byteLength(second)
  splitSecond: splitCommandLine(secondAt, secondBytes, secondNames)
  countSecond: secondCount = handles.nameCount(secondNames)
  expectSecondCount: test.assertEqualInt64(five, secondCount)
  expectF: expectName(secondNames, zero, wordF="a\\\\\\b")
  expectG: expectName(secondNames, one, wordG="c\\")
  expectH: expectName(secondNames, two, wordH="de")
  expectI: expectName(secondNames, three, wordI="\"f\"")
  expectJ: expectName(secondNames, four, wordJ="")
  takeWords: words = heap.take(twentyFour)
  addSpace: addTestWord(words, spaced="a b")
  addEmpty: addTestWord(words, nothing="")
  addQuote: addTestWord(words, quoted="x\"y")
  addBack: addTestWord(words, backslashed="back\\")
  addBoth: addTestWord(words, both="t\\\"q")
  findProgram: programAt = machine.addressOfString(program)
  makeLine: line = commandLine(programAt, four, words)
  readLine2: lineText = wide.builderText(line)
  readLineBytes: lineBytes = wide.builderLength(line)
  expectLine: expectText(lineText, lineBytes, listed)
  return

op addTestWord "Add a word to a list of names"
  input names machine.Address copied
  input word String borrowed
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findWord: wordAt = machine.addressOfString(word)
  wordLength: bytes = string.byteLength(word)
  addIt: handles.addName(names, wordAt, bytes)
  return

test environmentTest "The program's arguments are counted and read up to their end, a variable that is set is read and one that is not is missing, and an Arguments list keeps what is added"
  verifies argumentCount countsArguments
  verifies argument givesArgument
  verifies environmentGet readsVariable
  verifies newArguments makesArguments
  verifies addArgument addsArgument
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let label String "environment test"
:begin
  findLabel: labelAt = machine.addressOfString(label)
  labelLength: labelBytes = string.byteLength(label)
  make: region = regions.newRegion(capacity=65536, labelAt, labelBytes)
  findArgs: args = argSlot(zero=0)
  findResults: results = stateAt(resultsOffset=62016)
  findPayload: payload = stateAt(payloadOffset=62080)
  countIt: argumentCount(results)
  readCount: count = machine.loadInt64(results)
  shapeArgument: shape1 = testShape(one=1, one, zero, zero, zero, zero)
  setIndex: setArg(zero, count)
  setRegion: setAddressArg(one, region)
  readPast: past = argument(shape1, args, results, payload)
  expectPast: expectStatus(one, past)
  readPayload: stored = machine.loadInt64(payload)
  expectPayload: test.assertEqualInt64(count, stored)
  shapeVariable: shape2 = testShape(two=2, one, zero, zero, zero, zero)
  setName: setTextArg(zero, root="SystemRoot")
  setVariableRegion: setAddressArg(two, region)
  readRoot: rootStatus = environmentGet(shape2, args, results, payload)
  expectRoot: expectStatus(zero, rootStatus)
  findRootLength: rootLengthSlot = machine.offset(results, eight=8)
  readRootLength: rootLength = machine.loadInt64(rootLengthSlot)
  someRoot: hasRoot = compare.greaterThanInt64(rootLength, two)
  expectSomeRoot: test.assertTrue(hasRoot)
  setMissing: setTextArg(zero, absent="REFINED_RUNTIME_SURELY_MISSING_42")
  readMissing: missingStatus = environmentGet(shape2, args, results, payload)
  expectMissing: expectStatus(one, missingStatus)
  setEquals: setTextArg(zero, equalsName="A=B")
  readEquals: equalsStatus = environmentGet(shape2, args, results, payload)
  expectEquals: expectStatus(one, equalsStatus)
  shapeNew: shape3 = testShape(one, zero, zero, zero, zero, zero)
  setNewRegion: setAddressArg(zero, region)
  newIt: newArguments(shape3, args, results)
  readHandle: handle = machine.loadInt64(results)
  shapeAdd: shape4 = testShape(one, two, zero, zero, zero, zero)
  setHandle: setArg(zero, handle)
  setWord: setTextArg(one, word="word")
  addIt: addArgument(shape4, args)
  findNames: names = handles.objectOf(handle, kindArguments)
  countNames: namesCount = handles.nameCount(names)
  expectOne: test.assertEqualInt64(one, namesCount)
  expectWord: expectName(names, zero, word)
  free: regions.release(region)
  return

test readLineTest "Standard input already read gives its lines without their line ends, then the end of input"
  verifies readLine readsLine
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let label String "read line test"
  let input String "one\x0d\ntwo-is-long\nthree"
:begin
  findLabel: labelAt = machine.addressOfString(label)
  labelLength: labelBytes = string.byteLength(label)
  make: region = regions.newRegion(capacity=65536, labelAt, labelBytes)
  readBuffer: buffer = stdinBuffer()
  findInput: inputAt = machine.addressOfString(input)
  inputLength: inputBytes = string.byteLength(input)
  addInput: wide.builderAdd(buffer, inputAt, inputBytes)
  findDone: doneSlot = stateAt(stdinDoneAt)
  storeDone: machine.storeInt64(doneSlot, one=1)
  findArgs: args = argSlot(zero=0)
  findResults: results = stateAt(resultsOffset=62016)
  findPayload: payload = stateAt(payloadOffset=62080)
  shapeOf: shape = testShape(one, one, one, zero, zero, zero)
  setRegion: setAddressArg(zero, region)
  setLimit: setArg(one, eight=8)
  setDeadline: setArg(two=2, minusOne=-1)
  readFirst: firstStatus = readLine(shape, args, results, payload)
  expectFirst: expectStatus(zero, firstStatus)
  expectOne: expectSlotText(results, oneLine="one")
  readSecond: secondStatus = readLine(shape, args, results, payload)
  expectLong: expectStatus(two, secondStatus)
  readThird: thirdStatus = readLine(shape, args, results, payload)
  expectThird: expectStatus(zero, thirdStatus)
  expectThree: expectSlotText(results, threeLine="three")
  readEnd: endStatus = readLine(shape, args, results, payload)
  widenEnd: endValue = convert.int32ToInt64(endStatus)
  expectEnd: test.assertEqualInt64(one, endValue)
  storeNotDone: machine.storeInt64(doneSlot, zero)
  free: regions.release(region)
  return

test childTest "A child runs to its end with its exit code, and a captured child's output comes back"
  verifies processRun runsChild
  verifies processRunCaptured capturesChild
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let label String "child test"
:begin
  findLabel: labelAt = machine.addressOfString(label)
  labelLength: labelBytes = string.byteLength(label)
  make: region = regions.newRegion(capacity=65536, labelAt, labelBytes)
  findArgs: args = argSlot(zero=0)
  findResults: results = stateAt(resultsOffset=62016)
  findPayload: payload = stateAt(payloadOffset=62080)
  takeNames: names = heap.take(twentyFour=24)
  makeHandle: handle = handles.newHandle(kindArguments, names, region)
  addSlash: addTestWord(names, slashC="/c")
  addExit: addTestWord(names, exitWord="exit")
  addCode: addTestWord(names, codeWord="3")
  shapeRun: shape1 = testShape(two=2, one=1, one, zero, zero, zero)
  setProgram: setTextArg(zero, cmd="cmd.exe")
  setHandle: setArg(two, handle)
  setDeadline: setArg(three=3, minusOne=-1)
  runIt: runStatus = processRun(shape1, args, results, payload)
  expectRun: expectStatus(zero, runStatus)
  readCode: code = machine.loadInt64(results)
  expectCode: test.assertEqualInt64(three, code)
  takeEchoNames: echoNames = heap.take(twentyFour)
  makeEchoHandle: echoHandle = handles.newHandle(kindArguments, echoNames, region)
  addEchoSlash: addTestWord(echoNames, slashC)
  addEcho: addTestWord(echoNames, echoWord="echo")
  addHi: addTestWord(echoNames, hiWord="hi")
  shapeCaptured: shape2 = testShape(two, one, two, one, one, one)
  setCapturedProgram: setTextArg(zero, cmd)
  setEchoHandle: setArg(two, echoHandle)
  setInput: setTextArg(three, nothing="")
  setRegion: setAddressArg(five=5, region)
  setLimit: setArg(six=6, thousand=1000)
  setCapturedDeadline: setArg(seven=7, minusOne)
  captureIt: capturedStatus = processRunCaptured(shape2, args, results, payload)
  expectCaptured: expectStatus(zero, capturedStatus)
  readCapturedCode: capturedCode = machine.loadInt64(results)
  expectCapturedCode: test.assertEqualInt64(zero, capturedCode)
  findOut: outSlot = machine.offset(results, eight=8)
  expectOut: expectSlotText(outSlot, hiLine="hi\x0d\n")
  free: regions.release(region)
  return

test secretTest "A Secret keeps its text, reveals it, matches only the same text, counts its bytes, and comes from the environment or is missing"
  verifies secretFromText keepsText
  verifies secretFromEnvironment keepsVariable
  verifies secretReveal revealsText
  verifies secretMatches matchesText
  verifies secretLength countsSecret
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let label String "secret test"
:begin
  findLabel: labelAt = machine.addressOfString(label)
  labelLength: labelBytes = string.byteLength(label)
  make: region = regions.newRegion(capacity=65536, labelAt, labelBytes)
  findArgs: args = argSlot(zero=0)
  findResults: results = stateAt(resultsOffset=62016)
  findPayload: payload = stateAt(payloadOffset=62080)
  shapeText: shape1 = testShape(two=2, one=1, zero, zero, zero, zero)
  setText: setTextArg(zero, hidden="hunter2")
  setRegion: setAddressArg(two, region)
  makeIt: secretFromText(shape1, args, results)
  readHandle: handle = machine.loadInt64(results)
  shapeOne: shape2 = testShape(one, one, zero, zero, zero, zero)
  setHandle: setArg(zero, handle)
  setRevealRegion: setAddressArg(one, region)
  revealIt: secretReveal(shape2, args, results)
  expectRevealed: expectSlotText(results, hidden)
  shapeLength: shape3 = testShape(one, zero, zero, zero, zero, zero)
  lengthIt: secretLength(shape3, args, results)
  readLength: length = machine.loadInt64(results)
  expectLength: test.assertEqualInt64(seven=7, length)
  shapeMatch: shape4 = testShape(one, two, zero, zero, zero, zero)
  setCandidate: setTextArg(one, hidden)
  matchIt: secretMatches(shape4, args, results)
  readMatch: matched = machine.loadInt64(results)
  expectMatch: test.assertEqualInt64(one, matched)
  setOther: setTextArg(one, other="hunter3")
  otherIt: secretMatches(shape4, args, results)
  readOther: otherMatched = machine.loadInt64(results)
  expectOther: test.assertEqualInt64(zero, otherMatched)
  setShort: setTextArg(one, short="hunt")
  shortIt: secretMatches(shape4, args, results)
  readShort: shortMatched = machine.loadInt64(results)
  expectShort: test.assertEqualInt64(zero, shortMatched)
  shapeEnvironment: shape5 = testShape(two, one, zero, zero, zero, zero)
  setName: setTextArg(zero, root="SystemRoot")
  setEnvironmentRegion: setAddressArg(two, region)
  fromEnvironment: rootStatus = secretFromEnvironment(shape5, args, results, payload)
  expectRoot: expectStatus(zero, rootStatus)
  setMissing: setTextArg(zero, absent="REFINED_RUNTIME_SURELY_MISSING_42")
  fromMissing: missingStatus = secretFromEnvironment(shape5, args, results, payload)
  expectMissing: expectStatus(one, missingStatus)
  free: regions.release(region)
  return

test ffiTest "The C library loads by the name `c`, its functions bind by name, a missing function is symbolMissing, a missing library notFound, and a Library closes"
  verifies ffiOpen loadsLibrary
  verifies ffiBind bindsSymbol
  verifies ffiClose closesLibrary
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findArgs: args = argSlot(zero=0)
  findResults: results = stateAt(resultsOffset=62016)
  findPayload: payload = stateAt(payloadOffset=62080)
  shapeOpen: shape1 = testShape(two=2, zero, zero, zero, zero, zero)
  setName: setTextArg(zero, cName="c")
  openIt: opened = ffiOpen(shape1, args, results, payload)
  expectOpened: expectStatus(zero, opened)
  readHandle: handle = machine.loadInt64(results)
  shapeBind: shape2 = testShape(one=1, two, zero, zero, zero, zero)
  setHandle: setArg(zero, handle)
  setSymbol: setTextArg(one, absName="abs")
  bindIt: bound = ffiBind(shape2, args, results, payload)
  expectBound: expectStatus(zero, bound)
  readAddress: address = machine.loadInt64(results)
  someCheck: found = compare.notEqualInt64(address, zero)
  expectFound: test.assertTrue(found)
  setMissing: setTextArg(one, missingName="semanticscriptNoSuchSymbol")
  bindMissing: missingStatus = ffiBind(shape2, args, results, payload)
  expectMissing: expectStatus(two, missingStatus)
  shapeClose: shape3 = testShape(one, zero, zero, zero, zero, zero)
  closeIt: ffiClose(shape3, args)
  setNoLibrary: setTextArg(zero, noLibrary="refined-surely-missing-library-42")
  openMissing: notFoundStatus = ffiOpen(shape1, args, results, payload)
  expectNotFound: expectStatus(one, notFoundStatus)
  return
