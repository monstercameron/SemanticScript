module requests "HTTP requests and responses as text: the http targets, as host.py reads and writes them"
  path requests
  imports standard.machine standard.string standard.math standard.compare standard.convert standard.logic standard.test kernel memory numbers heap tables values handles regions slots wide files
  exports httpCall

capability memoryAccess "Authority to read a request's bytes and keep its headers and the responses in memory" use machine.memory none

capability systemCalls "Authority to take memory for headers, responses, and their text" use system.calls none

## `http.parseRequest` reads a request as host.py does: the head ends at the first blank line (`\x0d\n\x0d\n`, else
## `\n\n`, else the whole text), its lines are split at `\n` with a `\x0d` before one dropped, the first is exactly
## three parts split at single spaces (a method of the seven HttpMethod names in any case of ASCII, a path that
## starts with `/`, a version that starts with `HTTP/`), and every other line is a header `name: value`, the
## name trimmed of ASCII white space and lower-cased (each byte that is not ASCII stands for U+FFFD, as
## `decode("ascii", "replace")` reads it), the value trimmed and copied into the request's region. The headers are
## kept by the address of the request's path, as host.py keeps them, so `http.header` finds them for the record
## the parse gave and its copies (a lookup lower-cases the name as `str.lower` does: ASCII letters, and the Kelvin
## sign that becomes `k`). machine.state bytes 1080 to 1095 belong to this module: 1080 the address of the table of
## requests' headers (a heap block, 0 before the first parse), 1088 a path's address while it is looked up.
## A list of headers is a heap block: at 0 how many, 8 how many it holds, then for each 32 bytes, the address of a
## heap copy of its name, the name's bytes, the value's address in the region, and the value's bytes.
constant tableAt "Where the address of the table of requests' headers is kept, in machine.state" Int64 1080

constant pathKeyAt "Where a path's address is put while its headers are looked up, in machine.state" Int64 1088

constant kindResponse "The kind of an HTTP response's handle" Int64 12

constant malformed "http.HttpParseError.malformed, numbered from 1" Int32 1

constant absent "string.NotFound.absent, numbered from 1" Int32 1

constant entryBytes "The bytes of a header in a list of headers" Int64 32

op byteOf "The byte of a text at a position, as a whole number"
  input text machine.Address copied
  input at Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  locateByte: place = machine.offset(text, at)
  readByte: byte = machine.loadByte(place)
  widen: value = convert.byteToInt64(byte)
  return value

op findByte "The first position from `from` up to `to` that holds a byte, or `to` when none does"
  input text machine.Address copied
  input from Int64 copied
  input to Int64 copied
  input wanted Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  set at from
  goto eachByte
:eachByte loop=while max=to
  endCheck: atEnd = compare.greaterOrEqualInt64(at, to)
  if atEnd giveEnd checkByte
:checkByte in=eachByte
  readIt: value = byteOf(text, at)
  sameCheck: same = compare.equalInt64(value, wanted)
  if same giveAt advance
:advance in=eachByte
  nextAt: after = math.addInt64(at, one=1)
  set at after
  goto eachByte
:giveEnd
  return to
:giveAt
  return at

op isBlank "Whether a byte is ASCII white space as bytes.strip() strips it: space, tab, line feed, vertical tab, form feed, carriage return"
  input value Int64 copied
  output Bool
:begin
  spaceCheck: isSpace = compare.equalInt64(value, space=32)
  lowCheck: aboveTab = compare.greaterOrEqualInt64(value, tab=9)
  highCheck: belowReturn = compare.lessOrEqualInt64(value, carriageReturn=13)
  controlCheck: isControl = logic.and(aboveTab, belowReturn)
  eitherCheck: blank = logic.or(isSpace, isControl)
  return blank

op trimStart "The first position of a range that is not white space, or its end"
  input text machine.Address copied
  input start Int64 copied
  input end Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  set at start
  goto eachByte
:eachByte loop=while max=end
  endCheck: atEnd = compare.greaterOrEqualInt64(at, end)
  if atEnd give checkByte
:checkByte in=eachByte
  readIt: value = byteOf(text, at)
  blankCheck: blank = isBlank(value)
  if blank advance give
:advance in=eachByte
  nextAt: after = math.addInt64(at, one=1)
  set at after
  goto eachByte
:give
  return at

op trimEnd "The end of a range less the white space it ends with"
  input text machine.Address copied
  input start Int64 copied
  input end Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  set at end
  goto eachByte
:eachByte loop=while max=end
  startCheck: atStart = compare.lessOrEqualInt64(at, start)
  if atStart give checkByte
:checkByte in=eachByte
  lastOf: last = math.subtractInt64(at, one=1)
  readIt: value = byteOf(text, last)
  blankCheck: blank = isBlank(value)
  if blank back give
:back in=eachByte
  set at last
  goto eachByte
:give
  return at

op lowerOf "A byte lower-cased as bytes.lower() does: ASCII capitals only"
  input value Int64 copied
  output Int64
:begin
  lowCheck: aboveA = compare.greaterOrEqualInt64(value, capitalA=65)
  highCheck: belowZ = compare.lessOrEqualInt64(value, capitalZ=90)
  capitalCheck: capital = logic.and(aboveA, belowZ)
  if capital lower keep
:lower
  lowered: small = math.addInt64(value, thirtyTwo=32)
  return small
:keep
  return value

op sameWord "Whether a range of bytes is a lower-case ASCII word in any case of ASCII"
  input text machine.Address copied
  input start Int64 copied
  input end Int64 copied
  input word String borrowed
  output Bool
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let yes Bool true
  let no Bool false
:begin
  wordLength: wordBytes = string.byteLength(word)
  rangeLength: rangeBytes = math.subtractInt64(end, start)
  lengthCheck: sameLength = compare.equalInt64(wordBytes, rangeBytes)
  if sameLength eachByte differ
:eachByte loop=while max=wordBytes
  doneCheck: done = compare.greaterOrEqualInt64(at, wordBytes)
  if done same compareByte
:compareByte in=eachByte
  placeOf: place = math.addInt64(start, at)
  readIt: value = byteOf(text, place)
  lowerIt: lowered = lowerOf(value)
  findWord: wordAt = machine.addressOfString(word)
  readWord: wanted = byteOf(wordAt, at)
  equalCheck: equal = compare.equalInt64(lowered, wanted)
  if equal advance differ
:advance in=eachByte
  nextAt: after = math.addInt64(at, one=1)
  set at after
  goto eachByte
:same
  return yes
:differ
  return no

op methodOf "The HttpMethod a range names (its number from 0: get, head, post, put, delete, options, patch), or -1"
  input text machine.Address copied
  input start Int64 copied
  input end Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let zero Int64 0
  let one Int64 1
  let two Int64 2
  let three Int64 3
  let four Int64 4
  let five Int64 5
  let six Int64 6
  let minusOne Int64 -1
:begin
  getCheck: isGet = sameWord(text, start, end, getText="get")
  if isGet giveGet headCheck
:giveGet
  return zero
:headCheck
  checkHead: isHead = sameWord(text, start, end, headText="head")
  if isHead giveHead postCheck
:giveHead
  return one
:postCheck
  checkPost: isPost = sameWord(text, start, end, postText="post")
  if isPost givePost putCheck
:givePost
  return two
:putCheck
  checkPut: isPut = sameWord(text, start, end, putText="put")
  if isPut givePut deleteCheck
:givePut
  return three
:deleteCheck
  checkDelete: isDelete = sameWord(text, start, end, deleteText="delete")
  if isDelete giveDelete optionsCheck
:giveDelete
  return four
:optionsCheck
  checkOptions: isOptions = sameWord(text, start, end, optionsText="options")
  if isOptions giveOptions patchCheck
:giveOptions
  return five
:patchCheck
  checkPatch: isPatch = sameWord(text, start, end, patchText="patch")
  if isPatch givePatch unknown
:givePatch
  return six
:unknown
  return minusOne

## ---------------------------------------------------------------- headers

op headerTable "The table of requests' headers, by the address of their path: made the first time"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findSlot: slot = kernel.stateAt(tableAt)
  readTable: table = machine.loadAddress(slot)
  nowhere: anywhere = machine.zero()
  missingCheck: missing = machine.equal(table, anywhere)
  if missing make give
:make
  takeTable: made = heap.take(tableBytes=88)
  prepareIt: tables.prepare(made, zero=0, one=1, one)
  storeTable: machine.storeAddress(slot, made)
  return made
:give
  return table

op pathKey "Put a path's address in the slot its headers are looked up by, and give the slot"
  input path machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findSlot: slot = kernel.stateAt(pathKeyAt)
  storePath: machine.storeAddress(slot, path)
  return slot

op giveList "Give back a list of headers and the copies of its names"
  input list machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  readCount: count = machine.loadInt64(list)
  goto eachHeader
:eachHeader loop=while max=count
  doneCheck: done = compare.greaterOrEqualInt64(at, count)
  if done finish giveName
:giveName in=eachHeader
  offsetOf: offset = math.multiplyInt64(at, entryBytes)
  entryOffset: place = math.addInt64(offset, sixteen=16)
  findEntry: entry = machine.offset(list, place)
  readName: name = machine.loadAddress(entry)
  giveIt: heap.give(name)
  nextHeader: after = math.addInt64(at, one=1)
  set at after
  goto eachHeader
:finish
  giveBlock: heap.give(list)
  return

op keepHeaders "Keep a list of headers by the address of a request's path, giving back any list kept for it before"
  input path machine.Address copied
  input list machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findTable: table = headerTable()
  findKey: key = pathKey(path)
  hashIt: hash = tables.hashKey(table, key)
  findIt: row = tables.find(table, key, hash)
  missingCheck: missing = compare.lessThanInt64(row, zero=0)
  if missing insert replace
:replace
  findRow: rowAt = tables.rowAddress(table, row)
  findValue: valueSlot = machine.offset(rowAt, twentyFour=24)
  readOld: old = machine.loadAddress(valueSlot)
  giveOld: giveList(old)
  storeNew: machine.storeAddress(valueSlot, list)
  return
:insert
  insertIt: newRow = tables.insert(table, key, hash)
  findNewValue: newSlot = machine.offset(newRow, twentyFour)
  storeList: machine.storeAddress(newSlot, list)
  return

op headersOf "The list of headers kept for a request's path, or the address 0"
  input path machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findTable: table = headerTable()
  findKey: key = pathKey(path)
  hashIt: hash = tables.hashKey(table, key)
  findIt: row = tables.find(table, key, hash)
  missingCheck: missing = compare.lessThanInt64(row, zero=0)
  if missing giveNone readList
:giveNone
  nowhere: anywhere = machine.zero()
  return anywhere
:readList
  findRow: rowAt = tables.rowAddress(table, row)
  findValue: valueSlot = machine.offset(rowAt, twentyFour=24)
  readValue: list = machine.loadAddress(valueSlot)
  return list

op addHeader "Add a header to a list (its name a heap copy the list keeps, its value in the region) and give the list, grown when full"
  input list machine.Address copied
  input name machine.Address copied
  input nameBytes Int64 copied
  input value machine.Address copied
  input valueBytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let grown machine.Address unset mut
:begin
  set grown list
  readCount: count = machine.loadInt64(list)
  findCapacity: capacitySlot = machine.offset(list, eight=8)
  readCapacity: capacity = machine.loadInt64(capacitySlot)
  fullCheck: full = compare.greaterOrEqualInt64(count, capacity)
  if full grow store
:grow
  twice: doubled = math.multiplyInt64(capacity, two=2)
  more: grownCapacity = math.addInt64(doubled, four=4)
  entriesOf: entries = math.multiplyInt64(grownCapacity, entryBytes)
  bytesOf: bytes = math.addInt64(entries, sixteen=16)
  resizeIt: resized = heap.resize(list, bytes)
  set grown resized
  findGrownCapacity: grownSlot = machine.offset(resized, eight)
  storeCapacity: machine.storeInt64(grownSlot, grownCapacity)
  goto store
:store
  offsetOf: offset = math.multiplyInt64(count, entryBytes)
  entryOffset: place = math.addInt64(offset, sixteen)
  findEntry: entry = machine.offset(grown, place)
  storeName: machine.storeAddress(entry, name)
  findNameBytes: nameBytesSlot = machine.offset(entry, eight)
  storeNameBytes: machine.storeInt64(nameBytesSlot, nameBytes)
  findValue: valueSlot = machine.offset(entry, sixteen)
  storeValue: machine.storeAddress(valueSlot, value)
  findValueBytes: valueBytesSlot = machine.offset(entry, twentyFour=24)
  storeValueBytes: machine.storeInt64(valueBytesSlot, valueBytes)
  moreCount: after = math.addInt64(count, one=1)
  storeCount: machine.storeInt64(grown, after)
  return grown

op headerName "A header's name as host.py keys it, in a new builder: trimmed, ASCII lower-cased, each byte that is not ASCII U+FFFD"
  input text machine.Address copied
  input start Int64 copied
  input end Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let replacement String "\xef\xbf\xbd"
:begin
  makeName: name = wide.builderNew()
  set at start
  goto eachByte
:eachByte loop=while max=end
  doneCheck: done = compare.greaterOrEqualInt64(at, end)
  if done finish readByte
:readByte in=eachByte
  readIt: value = byteOf(text, at)
  asciiCheck: ascii = compare.lessThanInt64(value, n128=128)
  if ascii addAscii addReplacement
:addAscii in=eachByte
  lowerIt: lowered = lowerOf(value)
  narrowIt: byte = convert.int64ToByte(lowered)
  addIt: wide.builderAddByte(name, byte)
  goto advance
:addReplacement in=eachByte
  findReplacement: replacementAt = machine.addressOfString(replacement)
  addMark: wide.builderAdd(name, replacementAt, three=3)
  goto advance
:advance in=eachByte
  nextAt: after = math.addInt64(at, one=1)
  set at after
  goto eachByte
:finish
  return name

op lookupName "A name to look a header up by, lower-cased as str.lower() lower-cases it, in a new builder; 0 in the first slot of `ok` when it holds a character no header name can hold"
  input text machine.Address copied
  input bytes Int64 copied
  input ok machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let replacement String "\xef\xbf\xbd"
:begin
  storeOk: machine.storeInt64(ok, one=1)
  makeName: name = wide.builderNew()
  findCode: codeAt = machine.offset(ok, eight=8)
  goto eachCharacter
:eachCharacter loop=while max=bytes
  doneCheck: done = compare.greaterOrEqualInt64(at, bytes)
  if done finish readCharacter
:readCharacter in=eachCharacter
  decodeIt: taken = values.decodeAt(text, bytes, at, codeAt)
  readCode: code = machine.loadInt64(codeAt)
  asciiCheck: ascii = compare.lessThanInt64(code, n128=128)
  validCheck: valid = compare.greaterOrEqualInt64(code, zero=0)
  plainCheck: plain = logic.and(ascii, valid)
  if plain addAscii otherCheck
:addAscii in=eachCharacter
  lowerIt: lowered = lowerOf(code)
  narrowIt: byte = convert.int64ToByte(lowered)
  addIt: wide.builderAddByte(name, byte)
  goto advance
:otherCheck in=eachCharacter
  kelvinCheck: kelvin = compare.equalInt64(code, kelvinSign=8490)
  if kelvin addK replacementCheck
:addK in=eachCharacter
  addSmallK: wide.builderAddByte(name, smallK=107)
  goto advance
:replacementCheck in=eachCharacter
  invalidCheck: invalid = logic.not(valid)
  markCheck: isMark = compare.equalInt64(code, replacementCode=65533)
  eitherCheck: replaced = logic.or(invalid, isMark)
  if replaced addReplacement unmatched
:addReplacement in=eachCharacter
  findReplacement: replacementAt = machine.addressOfString(replacement)
  addMark: wide.builderAdd(name, replacementAt, three=3)
  goto advance
:unmatched in=eachCharacter
  storeNo: machine.storeInt64(ok, zero)
  goto advance
:advance in=eachCharacter
  nextAt: after = math.addInt64(at, taken)
  set at after
  goto eachCharacter
:finish
  return name

## ---------------------------------------------------------------- targets

op parseTarget "http.parseRequest: the request's method and path, its headers kept by the path's address; malformed as host.py finds it"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let headEnd Int64 0 mut
  let lineEnd Int64 0 mut
  let start Int64 0 mut
  let end Int64 0 mut
  let list machine.Address unset mut
  let ok Int32 0
  let newline Int64 10
  let space Int64 32
  let carriageReturn Int64 13
  let crlfTwice String "\x0d\n\x0d\n"
  let lfTwice String "\n\n"
  let version String "HTTP/"
  let forever Int64 9223372036854775807
:begin
  readRaw: raw = slots.addressArg(shape, args, zero=0)
  findLength: lengthSlot = slots.slotOf(shape, args, zero)
  findBytes: bytesSlot = machine.offset(lengthSlot, eight=8)
  readBytes: bytes = machine.loadInt64(bytesSlot)
  readRegion: region = slots.addressArg(shape, args, one=1)
  findCrlf: crlfAt = machine.addressOfString(crlfTwice)
  searchCrlf: crlfFound = memory.findBytes(raw, bytes, crlfAt, four=4)
  set headEnd crlfFound
  crlfCheck: noCrlf = compare.lessThanInt64(crlfFound, zero)
  if noCrlf searchLf firstLine
:searchLf
  findLf: lfAt = machine.addressOfString(lfTwice)
  searchIt: lfFound = memory.findBytes(raw, bytes, lfAt, two=2)
  set headEnd lfFound
  lfCheck: noLf = compare.lessThanInt64(lfFound, zero)
  if noLf wholeHead firstLine
:wholeHead
  set headEnd bytes
  goto firstLine
:firstLine
  firstEnd: firstNewline = findByte(raw, zero, headEnd, newline)
  set lineEnd firstNewline
  set end firstNewline
  moreCheck: hasMore = compare.lessThanInt64(firstNewline, headEnd)
  emptyCheck: hasBytes = compare.greaterThanInt64(firstNewline, zero)
  returnCheck: mayStrip = logic.and(hasMore, hasBytes)
  if mayStrip checkReturn split
:checkReturn
  lastOf: lastAt = math.subtractInt64(firstNewline, one)
  readLast: last = byteOf(raw, lastAt)
  isReturnCheck: isReturn = compare.equalInt64(last, carriageReturn)
  if isReturn stripReturn split
:stripReturn
  set end lastAt
  goto split
:split
  blankCheck: blank = compare.equalInt64(end, zero)
  if blank giveMalformed findFirstSpace
:findFirstSpace
  firstSpace: s1 = findByte(raw, zero, end, space)
  noFirstCheck: noFirst = compare.greaterOrEqualInt64(s1, end)
  if noFirst giveMalformed findSecondSpace
:findSecondSpace
  afterFirst: pathStart = math.addInt64(s1, one)
  secondSpace: s2 = findByte(raw, pathStart, end, space)
  noSecondCheck: noSecond = compare.greaterOrEqualInt64(s2, end)
  if noSecond giveMalformed findThirdSpace
:findThirdSpace
  afterSecond: versionStart = math.addInt64(s2, one)
  thirdSpace: s3 = findByte(raw, versionStart, end, space)
  extraCheck: extra = compare.lessThanInt64(s3, end)
  if extra giveMalformed checkVersion
:checkVersion
  versionLength: versionBytes = math.subtractInt64(end, versionStart)
  longCheck: longEnough = compare.greaterOrEqualInt64(versionBytes, five=5)
  if longEnough compareVersion giveMalformed
:compareVersion
  findVersion: versionAt = machine.offset(raw, versionStart)
  findWanted: wantedAt = machine.addressOfString(version)
  sameVersion: versionSame = memory.bytesEqual(versionAt, five, wantedAt, five)
  versionCheck: isVersion = compare.notEqualInt32(versionSame, ok)
  if isVersion checkPath giveMalformed
:checkPath
  pathLength: pathBytes = math.subtractInt64(s2, pathStart)
  pathEmptyCheck: pathEmpty = compare.equalInt64(pathBytes, zero)
  if pathEmpty giveMalformed checkSlash
:checkSlash
  readSlash: slash = byteOf(raw, pathStart)
  slashCheck: isSlash = compare.equalInt64(slash, slashByte=47)
  if isSlash checkMethod giveMalformed
:checkMethod
  methodIt: method = methodOf(raw, zero, s1)
  unknownCheck: unknown = compare.lessThanInt64(method, zero)
  if unknown giveMalformed putPath
:putPath
  findPath: pathAt = machine.offset(raw, pathStart)
  pathResult: pathSlots = machine.offset(results, sixteen=16)
  putIt: slots.putText(region, pathAt, pathBytes, pathSlots)
  readCopy: pathCopy = machine.loadAddress(pathSlots)
  storeMethod: machine.storeInt64(results, method)
  findPayloadSlot: methodPayload = machine.offset(results, eight)
  storeNoPayload: machine.storeInt64(methodPayload, zero)
  takeList: newList = heap.take(listBytes=144)
  storeListCapacity: listCapacitySlot = machine.offset(newList, eight)
  storeCapacity: machine.storeInt64(listCapacitySlot, four=4)
  set list newList
  noMoreCheck: noMore = compare.greaterOrEqualInt64(lineEnd, headEnd)
  if noMore keep startLines
:startLines
  afterLine: nextStart = math.addInt64(lineEnd, one)
  set start nextStart
  goto eachLine
:eachLine loop=while max=forever
  findLineEnd: thisEnd = findByte(raw, start, headEnd, newline)
  set lineEnd thisEnd
  set end thisEnd
  lineMoreCheck: lineHasMore = compare.lessThanInt64(thisEnd, headEnd)
  lineBytesCheck: lineHasBytes = compare.greaterThanInt64(thisEnd, start)
  lineStripCheck: lineMayStrip = logic.and(lineHasMore, lineHasBytes)
  if lineMayStrip lineReturn findColon
:lineReturn in=eachLine
  lineLastOf: lineLastAt = math.subtractInt64(thisEnd, one)
  readLineLast: lineLast = byteOf(raw, lineLastAt)
  lineReturnCheck: lineIsReturn = compare.equalInt64(lineLast, carriageReturn)
  if lineIsReturn lineStrip findColon
:lineStrip in=eachLine
  set end lineLastAt
  goto findColon
:findColon in=eachLine
  colonOf: colon = findByte(raw, start, end, colonByte=58)
  colonCheck: noColon = compare.greaterOrEqualInt64(colon, end)
  if noColon dropMalformed header
:header in=eachLine
  nameStart: nameFrom = trimStart(raw, start, colon)
  nameEnd: nameTo = trimEnd(raw, nameFrom, colon)
  afterColon: valueStart = math.addInt64(colon, one)
  valueStartOf: valueFrom = trimStart(raw, valueStart, end)
  valueEndOf: valueTo = trimEnd(raw, valueFrom, end)
  findValue: valueAt = machine.offset(raw, valueFrom)
  valueLength: valueBytes = math.subtractInt64(valueTo, valueFrom)
  findScratch: scratch = kernel.stateAt(scratchAt=1096)
  putValue: slots.putText(region, valueAt, valueBytes, scratch)
  readValueCopy: valueCopy = machine.loadAddress(scratch)
  nameOf: nameBuilder = headerName(raw, nameFrom, nameTo)
  readName: name = wide.builderText(nameBuilder)
  readNameLength: nameBytes = wide.builderLength(nameBuilder)
  copySize: copyBytes = math.addInt64(nameBytes, one)
  takeCopy: nameCopy = heap.take(copyBytes)
  copyName: machine.copy(nameCopy, name, nameBytes)
  giveText: heap.give(name)
  giveBuilder: heap.give(nameBuilder)
  addIt: added = addHeader(list, nameCopy, nameBytes, valueCopy, valueBytes)
  set list added
  lastLineCheck: lastLine = compare.greaterOrEqualInt64(lineEnd, headEnd)
  if lastLine keep nextLine
:nextLine in=eachLine
  afterThis: following = math.addInt64(lineEnd, one)
  set start following
  goto eachLine
:keep
  keepIt: keepHeaders(pathCopy, list)
  return ok
:dropMalformed
  dropList: giveList(list)
  goto giveMalformed
:giveMalformed
  malformedStatus: status = slots.failWith(payload, malformed, zero)
  return status

op headerTarget "http.header: the value of a request's header by its name in any case, or string.NotFound.absent"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let ok Int32 0
:begin
  findRequest: request = slots.slotOf(shape, args, zero=0)
  findPathSlot: pathSlot = machine.offset(request, sixteen=16)
  readPath: path = machine.loadAddress(pathSlot)
  readName: name = files.textAt(shape, args, one=1)
  readNameBytes: nameBytes = files.textBytes(shape, args, one)
  findList: list = headersOf(path)
  nowhere: anywhere = machine.zero()
  noListCheck: noList = machine.equal(list, anywhere)
  if noList giveAbsent lower
:lower
  findOk: okSlots = kernel.stateAt(okAt=1104)
  lowerIt: wanted = lookupName(name, nameBytes, okSlots)
  readOk: matchable = machine.loadInt64(okSlots)
  readWanted: wantedText = wide.builderText(wanted)
  readWantedLength: wantedBytes = wide.builderLength(wanted)
  readCount: count = machine.loadInt64(list)
  set at count
  unmatchableCheck: unmatchable = compare.equalInt64(matchable, zero)
  if unmatchable giveBack eachHeader
:eachHeader loop=while max=count
  doneCheck: done = compare.lessOrEqualInt64(at, zero)
  if done giveBack compareOne
:compareOne in=eachHeader
  backOne: previous = math.subtractInt64(at, one)
  set at previous
  offsetOf: offset = math.multiplyInt64(previous, entryBytes)
  entryOffset: place = math.addInt64(offset, sixteen)
  findEntry: entry = machine.offset(list, place)
  readEntryName: entryName = machine.loadAddress(entry)
  findEntryBytes: entryBytesSlot = machine.offset(entry, eight=8)
  readEntryBytes: entryLength = machine.loadInt64(entryBytesSlot)
  sameCheck: same = memory.bytesEqual(entryName, entryLength, wantedText, wantedBytes)
  foundCheck: found = compare.notEqualInt32(same, ok)
  if found give eachHeader
:give
  findValue: valueSlot = machine.offset(entry, sixteen)
  readValue: value = machine.loadAddress(valueSlot)
  findValueBytes: valueBytesSlot = machine.offset(entry, twentyFour=24)
  readValueBytes: valueBytes = machine.loadInt64(valueBytesSlot)
  storeValue: machine.storeAddress(results, value)
  findLengthSlot: lengthSlot = machine.offset(results, eight)
  storeLength: machine.storeInt64(lengthSlot, valueBytes)
  giveText: heap.give(wantedText)
  giveBuilder: heap.give(wanted)
  return ok
:giveBack
  giveUnmatched: heap.give(wantedText)
  giveUnmatchedBuilder: heap.give(wanted)
  goto giveAbsent
:giveAbsent
  absentStatus: status = slots.failWith(payload, absent, zero)
  return status

op responseTarget "http.response: a response of a status and a body, owned by a region"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readStatus: status = slots.argOf(shape, args, zero=0)
  readBody: body = files.textAt(shape, args, one=1)
  readBodyBytes: bodyBytes = files.textBytes(shape, args, one)
  readRegion: region = slots.addressArg(shape, args, two=2)
  takeResponse: response = heap.take(twentyFour=24)
  storeStatus: machine.storeInt64(response, status)
  sizeOf: copyBytes = math.addInt64(bodyBytes, one)
  takeBody: copy = heap.take(copyBytes)
  copyBody: machine.copy(copy, body, bodyBytes)
  findBody: bodySlot = machine.offset(response, eight=8)
  storeBody: machine.storeAddress(bodySlot, copy)
  findLength: lengthSlot = machine.offset(response, sixteen=16)
  storeLength: machine.storeInt64(lengthSlot, bodyBytes)
  makeHandle: handle = handles.newHandle(kindResponse, response, region)
  storeHandle: machine.storeInt64(results, handle)
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
  findDigits: digits = kernel.stateAt(digitsAt=1112)
  writeIt: count = numbers.formatDecimal(value, digits)
  addIt: wide.builderAdd(builder, digits, count)
  return

op addReason "Add the reason phrase host.py writes for a status to a builder: those it names, otherwise `Status`"
  input builder machine.Address copied
  input status Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok String "OK"
  let created String "Created"
  let noContent String "No Content"
  let badRequest String "Bad Request"
  let notFound String "Not Found"
  let notAllowed String "Method Not Allowed"
  let serverError String "Internal Server Error"
  let other String "Status"
:begin
  okCheck: isOk = compare.equalInt64(status, n200=200)
  if isOk giveOk createdCheck
:giveOk
  addOk: addText(builder, ok)
  return
:createdCheck
  checkCreated: isCreated = compare.equalInt64(status, n201=201)
  if isCreated giveCreated noContentCheck
:giveCreated
  addCreated: addText(builder, created)
  return
:noContentCheck
  checkNoContent: isNoContent = compare.equalInt64(status, n204=204)
  if isNoContent giveNoContent badRequestCheck
:giveNoContent
  addNoContent: addText(builder, noContent)
  return
:badRequestCheck
  checkBadRequest: isBadRequest = compare.equalInt64(status, n400=400)
  if isBadRequest giveBadRequest notFoundCheck
:giveBadRequest
  addBadRequest: addText(builder, badRequest)
  return
:notFoundCheck
  checkNotFound: isNotFound = compare.equalInt64(status, n404=404)
  if isNotFound giveNotFound notAllowedCheck
:giveNotFound
  addNotFound: addText(builder, notFound)
  return
:notAllowedCheck
  checkNotAllowed: isNotAllowed = compare.equalInt64(status, n405=405)
  if isNotAllowed giveNotAllowed serverErrorCheck
:giveNotAllowed
  addNotAllowed: addText(builder, notAllowed)
  return
:serverErrorCheck
  checkServerError: isServerError = compare.equalInt64(status, n500=500)
  if isServerError giveServerError giveOther
:giveServerError
  addServerError: addText(builder, serverError)
  return
:giveOther
  addOther: addText(builder, other)
  return

op serializeTarget "http.serializeResponse: the response as bytes, its status line and headers as host.py writes them, then its body"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findResponse: response = handles.objectOf(handle, kindResponse)
  readRegion: region = slots.addressArg(shape, args, one=1)
  readStatus: status = machine.loadInt64(response)
  findBody: bodySlot = machine.offset(response, eight=8)
  readBody: body = machine.loadAddress(bodySlot)
  findLength: lengthSlot = machine.offset(response, sixteen=16)
  readLength: bodyBytes = machine.loadInt64(lengthSlot)
  makeText: text = wide.builderNew()
  addStart: addText(text, startText="HTTP/1.1 ")
  addStatus: addNumber(text, status)
  addSpace: addText(text, spaceText=" ")
  addReasonIt: addReason(text, status)
  addType: addText(text, typeText="\x0d\nContent-Type: text/plain; charset=utf-8\x0d\nContent-Length: ")
  addLength: addNumber(text, bodyBytes)
  addClose: addText(text, closeText="\x0d\nConnection: close\x0d\n\x0d\n")
  addBody: wide.builderAdd(text, body, bodyBytes)
  readText: bytes = wide.builderText(text)
  readTextLength: count = wide.builderLength(text)
  putIt: slots.putText(region, bytes, count, results)
  giveText: heap.give(bytes)
  giveBuilder: heap.give(text)
  return

op httpCall "Run an http target by its place among them (1 parseRequest, 2 header, 3 response, 4 serializeResponse): 0, or an error's variant number with its payload stored"
  invariant runsHttp "Each target reads and writes what host.py's http handlers read and write, malformed and absent included"
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
  if isParse runParse headerCheck
:runParse
  parseIt: parseStatus = parseTarget(shape, args, results, payload)
  return parseStatus
:headerCheck
  checkHeader: isHeader = compare.equalInt64(which, two=2)
  if isHeader runHeader responseCheck
:runHeader
  headerIt: headerStatus = headerTarget(shape, args, results, payload)
  return headerStatus
:responseCheck
  checkResponse: isResponse = compare.equalInt64(which, three=3)
  if isResponse runResponse runSerialize
:runResponse
  responseIt: responseTarget(shape, args, results)
  return ok
:runSerialize
  serializeIt: serializeTarget(shape, args, results)
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

op setText "Set two argument slots of the tests' call to a text's address and length"
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

op call "Call an http target with the tests' slots and give its status"
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
  callIt: status = httpCall(which, shape, args, results, payload)
  widen: wide = convert.int32ToInt64(status)
  return wide

op expectResultText "Compare the text in the result slots, from a slot on, with what is expected"
  input slot Int64 copied
  input wanted String borrowed
  effect use machine.memory
  uses memoryAccess
:begin
  offsetOf: offset = math.multiplyInt64(slot, eight=8)
  withBase: place = math.addInt64(offset, resultsOffset=62016)
  findSlot: address = kernel.stateAt(place)
  readText: text = machine.loadAddress(address)
  findLength: lengthSlot = machine.offset(address, eight)
  readLength: length = machine.loadInt64(lengthSlot)
  findWanted: wantedAt = machine.addressOfString(wanted)
  wantedLength: wantedBytes = string.byteLength(wanted)
  compareLength: test.assertEqualInt64(wantedBytes, length)
  compareText: same = memory.bytesEqual(text, length, wantedAt, wantedBytes)
  sameWide: sameValue = convert.int32ToInt64(same)
  compareIt: test.assertEqualInt64(one=1, sameValue)
  return

op expectHeader "Look a header of the parsed request up and compare its value"
  input name String borrowed
  input wanted String borrowed
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  shapeIt: setShape(four=4, two=2, zero=0)
  findRequest: request = argAt(zero)
  findResults: results = kernel.stateAt(resultsOffset=62016)
  copyRequest: machine.copy(request, results, thirtyTwo=32)
  setName: setText(four, name)
  callIt: status = call(two)
  expectFound: test.assertEqualInt64(zero, status)
  expectIt: expectResultText(zero, wanted)
  copyBack: machine.copy(results, request, thirtyTwo)
  return

test httpTest "A request's method, path, and headers are read as host.py reads them; malformed requests are malformed; a response is written with its status line, headers, and body"
  verifies httpCall runsHttp
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let label String "http test"
  let request String "pOsT /items?x=1 HTTP/1.1\x0d\nHost: example.com \x0d\nX-Count:\t3\x0d\nx-count: 4\x0d\nWeird\xff: yes\x0d\nKind: k1\x0d\n\x0d\nbody"
  let bare String "GET / HTTP/1.0"
  let lines String "DELETE /a HTTP/2\nA: 1\n\nrest"
:begin
  findLabel: labelAt = machine.addressOfString(label)
  labelLength: labelBytes = string.byteLength(label)
  make: region = regions.newRegion(capacity=65536, labelAt, labelBytes)
  shapeParse: setShape(two=2, one=1, zero=0)
  setRequest: setText(zero, request)
  findRegionSlot: regionSlot = argAt(two)
  setRegion: machine.storeAddress(regionSlot, region)
  parseIt: parsed = call(one=1)
  expectParsed: test.assertEqualInt64(zero, parsed)
  findResults: results = kernel.stateAt(resultsOffset=62016)
  readMethod: method = machine.loadInt64(results)
  expectMethod: test.assertEqualInt64(two, method)
  expectPath: expectResultText(two, pathText="/items?x=1")
  host: expectHeader(hostName="HOST", hostValue="example.com")
  count: expectHeader(countName="X-Count", countValue="4")
  weird: expectHeader(weirdName="weird\xef\xbf\xbd", yesValue="yes")
  kelvin: expectHeader(kelvinName="\xe2\x84\xaaIND", kindValue="k1")
  shapeMissing: setShape(four=4, two, zero)
  setMissing: setText(four, missingName="Accept")
  findShape: shape = kernel.stateAt(shapeAt=61440)
  findArgs: args = kernel.stateAt(argsOffset=61952)
  findPayload: payload = kernel.stateAt(payloadOffset=62080)
  missingIt: missing = httpCall(two, shape, args, results, payload)
  widenMissing: missingValue = convert.int32ToInt64(missing)
  test.assertEqualInt64(one, missingValue)
  shapeBare: setShape(two, one, zero)
  setBare: setText(zero, bare)
  setBareRegion: machine.storeAddress(regionSlot, region)
  bareIt: bareStatus = call(one)
  test.assertEqualInt64(zero, bareStatus)
  setLines: setText(zero, lines)
  setLinesRegion: machine.storeAddress(regionSlot, region)
  linesIt: linesStatus = call(one)
  test.assertEqualInt64(zero, linesStatus)
  readDelete: deleteMethod = machine.loadInt64(results)
  test.assertEqualInt64(four, deleteMethod)
  setBad: setText(zero, badText="GET  / HTTP/1.1")
  setBadRegion: machine.storeAddress(regionSlot, region)
  badIt: badStatus = call(one)
  test.assertEqualInt64(one, badStatus)
  setNoColon: setText(zero, noColonText="GET / HTTP/1.1\x0d\nNoColon\x0d\n\x0d\n")
  setNoColonRegion: machine.storeAddress(regionSlot, region)
  noColonIt: noColonStatus = call(one)
  test.assertEqualInt64(one, noColonStatus)
  setUnknown: setText(zero, unknownText="FETCH / HTTP/1.1")
  setUnknownRegion: machine.storeAddress(regionSlot, region)
  unknownIt: unknownStatus = call(one)
  test.assertEqualInt64(one, unknownStatus)
  shapeResponse: setShape(one, two, one)
  findStatus: statusSlot = argAt(zero)
  storeStatus: machine.storeInt64(statusSlot, n404=404)
  setBody: setText(one, bodyText="gone")
  findResponseRegion: responseRegionSlot = argAt(three=3)
  setResponseRegion: machine.storeAddress(responseRegionSlot, region)
  responseIt: responseStatus = call(three)
  test.assertEqualInt64(zero, responseStatus)
  readHandle: handle = machine.loadInt64(results)
  shapeSerialize: setShape(one, one, zero)
  storeHandle: machine.storeInt64(statusSlot, handle)
  findSerializeRegion: serializeRegionSlot = argAt(one)
  setSerializeRegion: machine.storeAddress(serializeRegionSlot, region)
  serializeIt: serializeStatus = call(four)
  test.assertEqualInt64(zero, serializeStatus)
  expectSerialized: expectResultText(zero, wholeText="HTTP/1.1 404 Not Found\x0d\nContent-Type: text/plain; charset=utf-8\x0d\nContent-Length: 4\x0d\nConnection: close\x0d\n\x0d\ngone")
  free: regions.release(region)
  return
