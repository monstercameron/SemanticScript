module loader "A loader of ELF shared libraries on Linux, for ffi.open in an executable with no C library: segments mapped, relocations applied, symbols found by their hash tables, and C imports resolved against the runtime's C library (D-154)"
  path loader
  imports standard.machine standard.system standard.string standard.math standard.compare standard.convert standard.bits standard.logic standard.test kernel memory heap frames wide clibrary
  exports openLibrary symbolOf gnuHash elfHash

capability memoryAccess "Authority to map a library's segments and write its relocations" use machine.memory none

capability systemCalls "Authority to open a library's file, map it, and run its initializers" use system.calls none

## D-154: `ffi.open` of a library other than the C library, on Linux, maps it as ld.so would: the file found as dlopen
## finds a name (a path when it has a `/`, else each directory of LD_LIBRARY_PATH, the asking library's RUNPATH or
## RPATH with $ORIGIN, and the system's library directories), its PT_LOAD segments mapped from the file at a base the
## kernel picks, RELATIVE, GLOB_DAT, JUMP_SLOT, and 64 (ABS64) relocations applied (DT_RELA, DT_JMPREL, DT_RELR), its
## DT_NEEDED libraries loaded first (the C library and its parts, libc.so.6, libm.so.6, and the like, are the
## runtime's own, D-153), its undefined symbols looked up in it, then its libraries breadth first, then the runtime's
## C library, all bound at once as RTLD_NOW binds them; then DT_INIT and DT_INIT_ARRAY run. What the loader cannot do
## right it refuses with a trap that says why, never loading a library wrongly: thread-local storage (PT_TLS, TLS
## relocations), ifunc (IRELATIVE, STT_GNU_IFUNC), text relocations, DT_REL, and a symbol nothing defines. A file that
## is not an ELF shared object for this machine is notFound, as dlopen's failure is. Loaded libraries stay loaded (a
## library is loaded once, known by its device and inode). On x86_64 the thread pointer is set (arch_prctl) to a block
## whose word at 0x28 is the stack protector's canary, which compiled code reads at %fs:0x28; on AArch64 the canary
## is __stack_chk_guard (D-153), filled from getrandom.
## machine.state bytes 1664 to 1791 belong to this module: 1664 the first loaded library, 1672 the thread block (0
## until set), 1680 the page size (0 until read), 1688 to 1831 a struct stat.
constant listAt "Where the first loaded library is kept, in machine.state" Int64 1664

constant threadAt "Where the thread block is kept, in machine.state" Int64 1672

constant pageAt "Where the page size is kept, in machine.state" Int64 1680

constant statAt "Where fstat writes a struct stat, in machine.state" Int64 1688

constant objectBytes "The bytes of a loaded library's record" Int64 256

constant nextAt "A library's record: the next library loaded" Int64 0

constant baseAt "A library's record: its load bias, the address its virtual address 0 is at" Int64 8

constant symtabAt "A library's record: the address of its dynamic symbols" Int64 16

constant strtabAt "A library's record: the address of its dynamic strings" Int64 24

constant gnuHashAt "A library's record: the address of its DT_GNU_HASH table, or 0" Int64 32

constant hashAt "A library's record: the address of its DT_HASH table, or 0" Int64 40

constant depsAt "A library's record: the block of its libraries' records" Int64 48

constant depCountAt "A library's record: how many libraries it needs (not the C library)" Int64 56

constant needsCAt "A library's record: 1 when it needs the C library" Int64 64

constant deviceAt "A library's record: its file's device" Int64 72

constant inodeAt "A library's record: its file's inode" Int64 80

constant stateField "A library's record: 1 while it is loaded, 2 when it is ready" Int64 88

constant initAt "A library's record: DT_INIT's address, or 0" Int64 96

constant initArrayAt "A library's record: DT_INIT_ARRAY's address, or 0" Int64 104

constant initArrayBytesAt "A library's record: DT_INIT_ARRAYSZ" Int64 112

constant relaAt "A library's record: DT_RELA's address, or 0" Int64 120

constant relaBytesAt "A library's record: DT_RELASZ" Int64 128

constant jmprelAt "A library's record: DT_JMPREL's address, or 0" Int64 136

constant jmprelBytesAt "A library's record: DT_PLTRELSZ" Int64 144

constant relrAt "A library's record: DT_RELR's address, or 0" Int64 152

constant relrBytesAt "A library's record: DT_RELRSZ" Int64 160

constant runpathAt "A library's record: its DT_RUNPATH (or DT_RPATH) as an offset into its strings, plus 1; 0 for none" Int64 168

constant originAt "A library's record: the block of its file's directory, for $ORIGIN" Int64 176

constant originBytesAt "A library's record: its directory's bytes" Int64 184

constant pathAt "A library's record: the block of its file's path, for messages" Int64 192

constant pathBytesAt "A library's record: its path's bytes" Int64 200

constant neededAt "A library's record: the block of its DT_NEEDED names as offsets into its strings" Int64 208

constant neededCountAt "A library's record: how many DT_NEEDED rows it has" Int64 216

constant dynamicAt "A library's record: the address of its dynamic section" Int64 224

constant forever "The bound of a loop over a table that ends at a 0 row" Int64 9223372036854775807

constant mostDepth "How deep libraries may need libraries" Int64 32

## ---------------------------------------------------------------- traps and small pieces

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

op addText "Add a text's bytes to a builder"
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

op refuse "Trap because a library cannot be loaded right: `ffi.open` cannot load `<path>` in an executable with no C library, then why, then `(D-154); run the program with refined run`"
  input object machine.Address copied
  input reason String borrowed
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  makeBuilder: builder = wide.builderNew()
  addLead: addText(builder, lead="`ffi.open` cannot load `")
  readPath: path = getAddress(object, pathAt)
  readPathBytes: pathBytes = getField(object, pathBytesAt)
  addPath: wide.builderAdd(builder, path, pathBytes)
  addMiddle: addText(builder, middle="` in an executable with no C library: ")
  addReason: addText(builder, reason)
  addTail: addText(builder, tail=" (D-154); run the program with `refined run`")
  failIt: failBuilt(builder)
  return

op refuseSymbol "Trap because no library and not the runtime's C library defines a symbol a library needs"
  input object machine.Address copied
  input name machine.Address copied
  input bytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  makeBuilder: builder = wide.builderNew()
  addLead: addText(builder, lead="`ffi.open` cannot load `")
  readPath: path = getAddress(object, pathAt)
  readPathBytes: pathBytes = getField(object, pathBytesAt)
  addPath: wide.builderAdd(builder, path, pathBytes)
  addMiddle: addText(builder, middle="` in an executable with no C library: it needs `")
  addName: wide.builderAdd(builder, name, bytes)
  addTail: addText(builder, tail="`, which neither its libraries nor the runtime's C library (D-153) define (D-154); run the program with `refined run`")
  failIt: failBuilt(builder)
  return

op failBuilt "Report a trap whose message a builder holds and end the process with exit code 70"
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

op getField "A word of a record"
  input record machine.Address copied
  input offset Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findPlace: place = machine.offset(record, offset)
  readIt: value = machine.loadInt64(place)
  return value

op getAddress "An address in a record"
  input record machine.Address copied
  input offset Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findPlace: place = machine.offset(record, offset)
  readIt: value = machine.loadAddress(place)
  return value

op putField "Store a word in a record"
  input record machine.Address copied
  input offset Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  findPlace: place = machine.offset(record, offset)
  storeIt: machine.storeInt64(place, value)
  return

op putAddress "Store an address in a record"
  input record machine.Address copied
  input offset Int64 copied
  input value machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  findPlace: place = machine.offset(record, offset)
  storeIt: machine.storeAddress(place, value)
  return

op halfWordAt "An unsigned 16-bit number at an offset"
  input base machine.Address copied
  input offset Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findLow: low = machine.offset(base, offset)
  readLow: lowByte = machine.loadByte(low)
  findHigh: high = machine.offset(low, one=1)
  readHigh: highByte = machine.loadByte(high)
  widenLow: lowValue = convert.byteToInt64(lowByte)
  widenHigh: highValue = convert.byteToInt64(highByte)
  shiftHigh: highPart = bits.shiftLeftInt64(highValue, eight=8)
  joinIt: value = bits.orInt64(highPart, lowValue)
  return value

op wordAt32 "An unsigned 32-bit number at an offset"
  input base machine.Address copied
  input offset Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findPlace: place = machine.offset(base, offset)
  readIt: value32 = machine.loadInt32(place)
  widenIt: wideValue = convert.int32ToInt64(value32)
  maskIt: value = bits.andInt64(wideValue, lowMask=4294967295)
  return value

op wordAt64 "A 64-bit word at an offset"
  input base machine.Address copied
  input offset Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findPlace: place = machine.offset(base, offset)
  readIt: value = machine.loadInt64(place)
  return value

op pageSize "The system's page size: AT_PAGESZ of the auxiliary vector after envp, read once; 4096 when the process was not started by refined_entry"
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let size Int64 4096 mut
:begin
  findSlot: slot = kernel.stateAt(pageAt)
  readKept: kept = machine.loadInt64(slot)
  keptCheck: known = compare.greaterThanInt64(kept, zero=0)
  if known giveKept scan
:giveKept
  return kept
:scan
  readVector: vector = kernel.environmentVector()
  nowhere: anywhere = machine.zero()
  noVector: missing = machine.equal(vector, anywhere)
  if missing keep eachEntry
:eachEntry loop=while max=forever
  entryOffset: offset = math.multiplyInt64(at, eight=8)
  readEntry: entry = wordAt64(vector, offset)
  endCheck: ended = compare.equalInt64(entry, zero)
  if ended auxiliary advance
:advance in=eachEntry
  stepIt: next = math.addInt64(at, one=1)
  set at next
  goto eachEntry
:auxiliary
  afterEnd: auxiliaryStart = math.addInt64(at, one)
  set at auxiliaryStart
  goto eachPair
:eachPair loop=while max=forever
  pairOffset: pairAt = math.multiplyInt64(at, eight)
  readType: kind = wordAt64(vector, pairAt)
  typeEnd: typeEnded = compare.equalInt64(kind, zero)
  if typeEnded keep pageCheck
:pageCheck in=eachPair
  pageSame: isPage = compare.equalInt64(kind, pageSizeType=6)
  if isPage takePage nextPair
:takePage in=eachPair
  valueOffset: valueAt = math.addInt64(pairAt, eight)
  readValue: pageValue = wordAt64(vector, valueAt)
  set size pageValue
  goto keep
:nextPair in=eachPair
  stepPair: afterPair = math.addInt64(at, two=2)
  set at afterPair
  goto eachPair
:keep
  storeSize: machine.storeInt64(slot, size)
  return size

op pageFloor "An address rounded down to its page"
  input value Int64 copied
  input page Int64 copied
  output Int64
:begin
  maskOf: mask = math.subtractInt64(page, one=1)
  belowOf: below = bits.andInt64(value, mask)
  floorOf: floor = math.subtractInt64(value, below)
  return floor

op pageCeiling "An address rounded up to a page"
  input value Int64 copied
  input page Int64 copied
  output Int64
:begin
  maskOf: mask = math.subtractInt64(page, one=1)
  upOf: up = math.addInt64(value, mask)
  floorIt: ceiling = pageFloor(up, page)
  return ceiling

## ---------------------------------------------------------------- hashes (the System V ABI's and GNU's)

op gnuHash "The GNU hash of a name (DT_GNU_HASH): h = h * 33 + byte from 5381, in 32 bits"
  invariant hashesLikeGnu "Gives 5381 for the empty name and 0x156b2bb8 for printf"
  input name machine.Address copied
  input bytes Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let hash Int64 5381 mut
:begin
  goto eachByte
:eachByte loop=while max=bytes
  doneCheck: done = compare.greaterOrEqualInt64(at, bytes)
  if done finish addByte
:addByte in=eachByte
  findByte: place = machine.offset(name, at)
  readByte: value = machine.loadByte(place)
  widenByte: wideValue = convert.byteToInt64(value)
  timesOf: times = math.multiplyInt64(hash, thirtyThree=33)
  addOf: added = math.addInt64(times, wideValue)
  maskIt: masked = bits.andInt64(added, lowMask=4294967295)
  set hash masked
  stepIt: next = math.addInt64(at, one=1)
  set at next
  goto eachByte
:finish
  return hash

op elfHash "The System V hash of a name (DT_HASH)"
  invariant hashesLikeElf "Gives 0 for the empty name and 0x077905a6 for printf"
  input name machine.Address copied
  input bytes Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let hash Int64 0 mut
:begin
  goto eachByte
:eachByte loop=while max=bytes
  doneCheck: done = compare.greaterOrEqualInt64(at, bytes)
  if done finish addByte
:addByte in=eachByte
  findByte: place = machine.offset(name, at)
  readByte: value = machine.loadByte(place)
  widenByte: wideValue = convert.byteToInt64(value)
  shiftOf: shifted = bits.shiftLeftInt64(hash, four=4)
  addOf: added = math.addInt64(shifted, wideValue)
  topOf: top = bits.andInt64(added, topMask=4026531840)
  downOf: down = bits.shiftRightInt64(top, twentyFour=24)
  mixOf: mixed = bits.xorInt64(added, down)
  clearOf: cleared = bits.andInt64(mixed, keepMask=268435455)
  set hash cleared
  stepIt: next = math.addInt64(at, one=1)
  set at next
  goto eachByte
:finish
  return hash

## ---------------------------------------------------------------- symbols

op nameIs "Whether a symbol's name in a library's strings is exactly a name"
  input object machine.Address copied
  input nameOffset Int64 copied
  input name machine.Address copied
  input bytes Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let no Bool false
:begin
  readStrings: strings = getAddress(object, strtabAt)
  findName: symbolName = machine.offset(strings, nameOffset)
  compareIt: order = machine.compare(symbolName, name, bytes)
  sameCheck: same = compare.equalInt32(order, zero32=0)
  if same endCheck differ
:endCheck
  findEnd: end = machine.offset(symbolName, bytes)
  readEnd: endByte = machine.loadByte(end)
  zeroCheck: ended = compare.equalByte(endByte, nul=0)
  return ended
:differ
  return no


op definedValue "The address a library's symbol of an index defines, when the symbol has that name and is defined, global or weak, and neither thread-local nor an ifunc (which trap); 0 otherwise"
  input object machine.Address copied
  input index Int64 copied
  input name machine.Address copied
  input bytes Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let noValue Int64 0
:begin
  readSymbols: symbols = getAddress(object, symtabAt)
  entryOf: entryOffset = math.multiplyInt64(index, twentyFour=24)
  findEntry: entry = machine.offset(symbols, entryOffset)
  readSection: section = halfWordAt(entry, six=6)
  undefinedCheck: undefined = compare.equalInt64(section, zero=0)
  if undefined giveNone bindCheck
:bindCheck
  findInfo: infoAt = machine.offset(entry, four=4)
  readInfo: infoByte = machine.loadByte(infoAt)
  widenInfo: info = convert.byteToInt64(infoByte)
  bindOf: binding = bits.shiftRightInt64(info, four)
  localCheck: local = compare.equalInt64(binding, zero)
  if local giveNone nameCheck
:nameCheck
  readNameOffset: nameOffset = wordAt32(entry, zero)
  matchName: named = nameIs(object, nameOffset, name, bytes)
  if named typeCheck giveNone
:typeCheck
  checkKind: checkSymbolKind(object, info)
  readValue: symbolValue = wordAt64(entry, eight=8)
  readBase: base = getField(object, baseAt)
  withBase: address = math.wrappingAddInt64(base, symbolValue)
  return address
:giveNone
  return noValue

op checkSymbolKind "Trap when a symbol is thread-local (STT_TLS) or an ifunc (STT_GNU_IFUNC), which the loader cannot bind right"
  input object machine.Address copied
  input info Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  typeOf: kind = bits.andInt64(info, fifteen=15)
  tlsCheck: threadLocal = compare.equalInt64(kind, tlsType=6)
  if threadLocal refuseTls ifuncCheck
:refuseTls
  refuseIt: refuse(object, tlsReason="it has thread-local variables, which only the C library's dynamic loader sets up")
  return
:ifuncCheck
  ifuncSame: indirect = compare.equalInt64(kind, ifuncType=10)
  if indirect refuseIfunc done
:refuseIfunc
  refuseIfuncIt: refuse(object, ifuncReason="it has an ifunc, a function the C library's dynamic loader chooses by running the library's own code")
  return
:done
  return

op lookupIn "The address a library defines for a name, found through its DT_GNU_HASH table (or DT_HASH when it has none); 0 when it defines none"
  input object machine.Address copied
  input name machine.Address copied
  input bytes Int64 copied
  input gnu Int64 copied
  input elf Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let index Int64 0 mut
  let noValue Int64 0
:begin
  readGnu: table = getAddress(object, gnuHashAt)
  nowhere: anywhere = machine.zero()
  noGnu: missingGnu = machine.equal(table, anywhere)
  if missingGnu sysv gnuLookup
:gnuLookup
  readBuckets: buckets = wordAt32(table, zero=0)
  emptyCheck: noBuckets = compare.equalInt64(buckets, zero)
  if noBuckets giveNone gnuBucket
:gnuBucket
  readOffset: symbolOffset = wordAt32(table, four=4)
  readBloom: bloomWords = wordAt32(table, eight=8)
  bloomBytes: bloomSpan = math.multiplyInt64(bloomWords, eight)
  bucketsOf: bucketsStart = math.addInt64(bloomSpan, sixteen=16)
  bucketOf: bucket = math.remainderInt64(gnu, buckets)
  bucketBytes: bucketOffset = math.multiplyInt64(bucket, four)
  bucketPlace: bucketAt = math.addInt64(bucketsStart, bucketOffset)
  readFirst: first = wordAt32(table, bucketAt)
  firstCheck: noFirst = compare.equalInt64(first, zero)
  if noFirst giveNone chains
:chains
  set index first
  allBuckets: bucketsSpan = math.multiplyInt64(buckets, four)
  chainsOf: chainsStart = math.addInt64(bucketsStart, bucketsSpan)
  hashLow: wantedHash = bits.orInt64(gnu, one=1)
  goto eachChain
:eachChain loop=while max=forever
  chainIndex: chainNumber = math.subtractInt64(index, symbolOffset)
  chainBytes: chainOffset = math.multiplyInt64(chainNumber, four)
  chainPlace: chainAt = math.addInt64(chainsStart, chainOffset)
  readChain: chainHash = wordAt32(table, chainAt)
  chainLow: givenHash = bits.orInt64(chainHash, one)
  sameCheck: sameHash = compare.equalInt64(givenHash, wantedHash)
  if sameHash tryChain chainEnd
:tryChain in=eachChain
  tryIt: chainValue = definedValue(object, index, name, bytes)
  foundCheck: chainFound = compare.notEqualInt64(chainValue, zero)
  if chainFound giveChain chainEnd
:chainEnd in=eachChain
  lastBit: last = bits.andInt64(chainHash, one)
  lastCheck: isLast = compare.equalInt64(last, one)
  if isLast giveNone nextChain
:nextChain in=eachChain
  stepChain: nextIndex = math.addInt64(index, one)
  set index nextIndex
  goto eachChain
:giveChain
  return chainValue
:sysv
  readHash: hashTable = getAddress(object, hashAt)
  noHash: missingHash = machine.equal(hashTable, anywhere)
  if missingHash giveNone sysvLookup
:sysvLookup
  readCount: bucketCount = wordAt32(hashTable, zero)
  emptyHash: noHashBuckets = compare.equalInt64(bucketCount, zero)
  if noHashBuckets giveNone sysvBucket
:sysvBucket
  sysvBucketOf: sysvIndex = math.remainderInt64(elf, bucketCount)
  sysvBucketBytes: sysvBucketOffset = math.multiplyInt64(sysvIndex, four)
  sysvBucketPlace: sysvBucketAt = math.addInt64(sysvBucketOffset, eight)
  readSysvFirst: sysvFirst = wordAt32(hashTable, sysvBucketAt)
  set index sysvFirst
  sysvBuckets: sysvBucketsSpan = math.multiplyInt64(bucketCount, four)
  sysvChains: sysvChainsStart = math.addInt64(sysvBucketsSpan, eight)
  goto eachLink
:eachLink loop=while max=forever
  linkEnd: linkDone = compare.equalInt64(index, zero)
  if linkDone giveNone tryLink
:tryLink in=eachLink
  tryLinkIt: linkValue = definedValue(object, index, name, bytes)
  linkFound: linkHas = compare.notEqualInt64(linkValue, zero)
  if linkHas giveLink nextLink
:nextLink in=eachLink
  linkBytes: linkOffset = math.multiplyInt64(index, four)
  linkPlace: linkAt = math.addInt64(sysvChainsStart, linkOffset)
  readLink: nextLinkIndex = wordAt32(hashTable, linkAt)
  set index nextLinkIndex
  goto eachLink
:giveLink
  return linkValue
:giveNone
  return noValue

op scopeLookup "The address of a name in a library's scope: the library, then the libraries it needs, breadth first, then the runtime's C library when `withC` is 1, or when it is 2 and a library of the scope needs the C library; the address 0 when none defines it"
  input object machine.Address copied
  input name machine.Address copied
  input bytes Int64 copied
  input withC Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let count Int64 1 mut
  let seen Int64 0 mut
  let needsC Bool false mut
  let yes Bool true
  let most Int64 256
:begin
  hashGnu: gnu = gnuHash(name, bytes)
  hashElf: elf = elfHash(name, bytes)
  takeQueue: queue = heap.take(queueBytes=2048)
  storeFirst: machine.storeAddress(queue, object)
  goto eachObject
:eachObject loop=while max=most
  doneCheck: done = compare.greaterOrEqualInt64(at, count)
  if done fallback visit
:visit in=eachObject
  placeOf: placeOffset = math.multiplyInt64(at, eight=8)
  findPlace: place = machine.offset(queue, placeOffset)
  readObject: current = machine.loadAddress(place)
  lookIt: found = lookupIn(current, name, bytes, gnu, elf)
  foundCheck: hasFound = compare.notEqualInt64(found, zero=0)
  if hasFound give needs
:needs in=eachObject
  readNeeds: currentNeeds = getField(current, needsCAt)
  needsCheck: needing = compare.equalInt64(currentNeeds, one=1)
  if needing markNeeds dependencies
:markNeeds in=eachObject
  set needsC yes
  goto dependencies
:dependencies in=eachObject
  readDeps: deps = getAddress(current, depsAt)
  readDepCount: depCount = getField(current, depCountAt)
  set seen zero
  goto eachDep
:eachDep loop=while max=depCount in=eachObject
  depsDone: allSeen = compare.greaterOrEqualInt64(seen, depCount)
  if allSeen nextObject addDep
:addDep in=eachDep
  depOffset: depAt = math.multiplyInt64(seen, eight)
  findDep: depPlace = machine.offset(deps, depAt)
  readDep: dep = machine.loadAddress(depPlace)
  queuedCheck: queued = inQueue(queue, count, dep)
  roomCheck: full = compare.greaterOrEqualInt64(count, most)
  skipCheck: skip = logic.or(queued, full)
  if skip nextDep enqueue
:enqueue in=eachDep
  endOffset: endAt = math.multiplyInt64(count, eight)
  findEnd: endPlace = machine.offset(queue, endAt)
  storeDep: machine.storeAddress(endPlace, dep)
  growCount: grown = math.addInt64(count, one)
  set count grown
  goto nextDep
:nextDep in=eachDep
  stepDep: afterDep = math.addInt64(seen, one)
  set seen afterDep
  goto eachDep
:nextObject in=eachObject
  stepObject: afterObject = math.addInt64(at, one)
  set at afterObject
  goto eachObject
:give
  giveQueue: heap.give(queue)
  addressOf: address = machine.fromInt64(found)
  return address
:fallback
  giveQueueAgain: heap.give(queue)
  alwaysCheck: always = compare.equalInt64(withC, one)
  neededCheck: whenNeeded = compare.equalInt64(withC, two=2)
  neededAndNeeds: neededHere = logic.and(whenNeeded, needsC)
  eitherCheck: useC = logic.or(always, neededHere)
  if useC library nothing
:library
  findInLibrary: libraryAddress = clibrary.lookup(name, bytes)
  return libraryAddress
:nothing
  nowhere: anywhere = machine.zero()
  return anywhere

op inQueue "Whether one of the first records of a queue is a record"
  input queue machine.Address copied
  input count Int64 copied
  input record machine.Address copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let yes Bool true
  let no Bool false
:begin
  goto eachPlace
:eachPlace loop=while max=count
  doneCheck: done = compare.greaterOrEqualInt64(at, count)
  if done absent compareIt
:compareIt in=eachPlace
  placeOf: offset = math.multiplyInt64(at, eight=8)
  findPlace: place = machine.offset(queue, offset)
  readIt: held = machine.loadAddress(place)
  sameCheck: same = machine.equal(held, record)
  if same present advance
:advance in=eachPlace
  stepIt: next = math.addInt64(at, one=1)
  set at next
  goto eachPlace
:present
  return yes
:absent
  return no

op symbolOf "ffi.Function.bind on a loaded library: the address of a name in its scope (dlsym's: the library, then the libraries it needs, then the runtime's C library when one of them needs it), or the address 0"
  invariant findsInScope "A library that needs the C library finds strlen through it; one that does not finds nothing"
  input object machine.Address copied
  input name machine.Address copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findIt: address = scopeLookup(object, name, bytes, whenNeeded=2)
  return address

## ---------------------------------------------------------------- relocations

op symbolAddress "The value a relocation's symbol has: 0 for symbol 0; the library's own definition; else the address its scope or the runtime's C library gives, 0 for a weak symbol nothing defines, and a trap for any other"
  input object machine.Address copied
  input index Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let noValue Int64 0
:begin
  zeroCheck: noSymbol = compare.equalInt64(index, zero=0)
  if noSymbol giveNone readEntry
:readEntry
  readSymbols: symbols = getAddress(object, symtabAt)
  entryOf: entryOffset = math.multiplyInt64(index, twentyFour=24)
  findEntry: entry = machine.offset(symbols, entryOffset)
  findInfo: infoAt = machine.offset(entry, four=4)
  readInfo: infoByte = machine.loadByte(infoAt)
  widenInfo: info = convert.byteToInt64(infoByte)
  readSection: section = halfWordAt(entry, six=6)
  undefinedCheck: undefined = compare.equalInt64(section, zero)
  if undefined lookUp own
:own
  checkKind: checkSymbolKind(object, info)
  readValue: symbolValue = wordAt64(entry, eight=8)
  readBase: base = getField(object, baseAt)
  withBase: address = math.wrappingAddInt64(base, symbolValue)
  return address
:lookUp
  checkUndefinedKind: checkSymbolKind(object, info)
  readNameOffset: nameOffset = wordAt32(entry, zero)
  readStrings: strings = getAddress(object, strtabAt)
  findName: name = machine.offset(strings, nameOffset)
  measureName: nameBytes = clibrary.cStringLength(name)
  scopeIt: found = scopeLookup(object, name, nameBytes, always=1)
  foundValue: foundNumber = machine.toInt64(found)
  foundCheck: hasFound = compare.notEqualInt64(foundNumber, zero)
  if hasFound giveFound weakCheck
:giveFound
  return foundNumber
:weakCheck
  bindOf: binding = bits.shiftRightInt64(info, four)
  weakSame: weak = compare.equalInt64(binding, two=2)
  if weak giveNone missing
:missing
  refuseIt: refuseSymbol(object, name, nameBytes)
  return noValue
:giveNone
  return noValue

op relocationKind "What a relocation type asks, by its number on x86_64 or AArch64: 0 nothing, 1 the base plus the addend (RELATIVE), 2 the symbol plus the addend (64, ABS64, GLOB_DAT, JUMP_SLOT), 3 thread-local storage, 4 an ifunc (IRELATIVE), 5 anything else (COPY, text relocations)"
  invariant kindsLikeTheAbi "R_X86_64_RELATIVE and R_AARCH64_RELATIVE are 1, JUMP_SLOT 2, TPOFF64 3, IRELATIVE 4, PC32 5"
  input kind Int64 copied
  input aarch64 Bool copied
  output Int64
  let nothing Int64 0
  let relative Int64 1
  let symbolic Int64 2
  let threadLocal Int64 3
  let indirect Int64 4
  let other Int64 5
:begin
  if aarch64 arm intel
:intel
  noneCheck: isNone = compare.equalInt64(kind, zero=0)
  if isNone giveNothing intelRelative
:intelRelative
  relativeCheck: isRelative = compare.equalInt64(kind, intelRelativeType=8)
  if isRelative giveRelative intelAbsolute
:intelAbsolute
  absoluteCheck: isAbsolute = compare.equalInt64(kind, one=1)
  globCheck: isGlob = compare.equalInt64(kind, six=6)
  slotCheck: isSlot = compare.equalInt64(kind, seven=7)
  eitherFirst: symbolic1 = logic.or(isAbsolute, isGlob)
  eitherAll: isSymbolic = logic.or(symbolic1, isSlot)
  if isSymbolic giveSymbolic intelIndirect
:intelIndirect
  indirectCheck: isIndirect = compare.equalInt64(kind, intelIndirectType=37)
  if isIndirect giveIndirect intelThread
:intelThread
  lowThread: aboveThread = compare.greaterOrEqualInt64(kind, sixteen=16)
  highThread: belowThread = compare.lessOrEqualInt64(kind, intelThreadLast=24)
  rangeThread: inThread = logic.and(aboveThread, belowThread)
  descriptorCheck: isDescriptor = compare.equalInt64(kind, intelDescriptor=36)
  eitherThread: isThread = logic.or(inThread, isDescriptor)
  if isThread giveThread giveOther
:arm
  armNone: isArmNone = compare.equalInt64(kind, zero)
  armNoneAlt: isArmNoneAlt = compare.equalInt64(kind, armNoneType=256)
  armNothing: armNothingAtAll = logic.or(isArmNone, isArmNoneAlt)
  if armNothingAtAll giveNothing armRelative
:armRelative
  armRelativeCheck: isArmRelative = compare.equalInt64(kind, armRelativeType=1027)
  if isArmRelative giveRelative armSymbolic
:armSymbolic
  armAbsolute: isArmAbsolute = compare.equalInt64(kind, armAbsoluteType=257)
  armGlob: isArmGlob = compare.equalInt64(kind, armGlobType=1025)
  armSlot: isArmSlot = compare.equalInt64(kind, armSlotType=1026)
  armFirst: armSymbolic1 = logic.or(isArmAbsolute, isArmGlob)
  armAll: isArmSymbolic = logic.or(armSymbolic1, isArmSlot)
  if isArmSymbolic giveSymbolic armIndirect
:armIndirect
  armIndirectCheck: isArmIndirect = compare.equalInt64(kind, armIndirectType=1032)
  if isArmIndirect giveIndirect armThread
:armThread
  armLow: aboveArmThread = compare.greaterOrEqualInt64(kind, armThreadFirst=1028)
  armHigh: belowArmThread = compare.lessOrEqualInt64(kind, armThreadLast=1031)
  armRange: isArmThread = logic.and(aboveArmThread, belowArmThread)
  if isArmThread giveThread giveOther
:giveNothing
  return nothing
:giveRelative
  return relative
:giveSymbolic
  return symbolic
:giveIndirect
  return indirect
:giveThread
  return threadLocal
:giveOther
  return other

op relocateTable "Apply a table of Elf64_Rela relocations (24 bytes each: offset, info, addend)"
  input object machine.Address copied
  input table machine.Address copied
  input bytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  countOf: count = math.divideInt64(bytes, twentyFour=24)
  readBase: base = getField(object, baseAt)
  archCheck: onArm = system.aarch64()
  goto eachEntry
:eachEntry loop=while max=count
  doneCheck: done = compare.greaterOrEqualInt64(at, count)
  if done finish apply
:apply in=eachEntry
  entryOf: entryOffset = math.multiplyInt64(at, twentyFour)
  findEntry: entry = machine.offset(table, entryOffset)
  readOffset: offset = wordAt64(entry, zero=0)
  readInfo: info = wordAt64(entry, eight=8)
  readAddend: addend = wordAt64(entry, sixteen=16)
  typeOf: kind = bits.andInt64(info, lowMask=4294967295)
  symbolOfIt: symbol = bits.shiftRightInt64(info, thirtyTwo=32)
  whereOf: whereNumber = math.wrappingAddInt64(base, offset)
  whereAddress: where = machine.fromInt64(whereNumber)
  kindOf: action = relocationKind(kind, onArm)
  nothingCheck: isNothing = compare.equalInt64(action, zero)
  if isNothing advance relativeCheck
:relativeCheck in=eachEntry
  relativeSame: isRelative = compare.equalInt64(action, one=1)
  if isRelative relative symbolicCheck
:relative in=eachEntry
  relativeValue: relativeNumber = math.wrappingAddInt64(base, addend)
  storeRelative: machine.storeInt64(where, relativeNumber)
  goto advance
:symbolicCheck in=eachEntry
  symbolicSame: isSymbolic = compare.equalInt64(action, two=2)
  if isSymbolic symbolic refusals
:symbolic in=eachEntry
  valueOf: symbolValue = symbolAddress(object, symbol)
  addAddend: symbolicNumber = math.wrappingAddInt64(symbolValue, addend)
  storeSymbolic: machine.storeInt64(where, symbolicNumber)
  goto advance
:refusals in=eachEntry
  threadSame: isThread = compare.equalInt64(action, three=3)
  if isThread refuseThread indirectCheck
:refuseThread in=eachEntry
  refuseThreadIt: refuse(object, threadReason="it uses thread-local storage, which only the C library's dynamic loader sets up")
  goto advance
:indirectCheck in=eachEntry
  indirectSame: isIndirect = compare.equalInt64(action, four=4)
  if isIndirect refuseIndirect refuseOther
:refuseIndirect in=eachEntry
  refuseIndirectIt: refuse(object, indirectReason="it has an ifunc (an IRELATIVE relocation), a function the C library's dynamic loader chooses by running the library's own code")
  goto advance
:refuseOther in=eachEntry
  refuseOtherIt: refuse(object, otherReason="it has a relocation of a kind the loader does not apply (only RELATIVE, GLOB_DAT, JUMP_SLOT, and 64-bit absolute ones)")
  goto advance
:advance in=eachEntry
  stepIt: next = math.addInt64(at, one)
  set at next
  goto eachEntry
:finish
  return

op relocateCompact "Apply DT_RELR's compact relative relocations: an even word is an address to add the base to, then the next word's; an odd word's bits 1 to 63 say which of the 63 words after the last address get the base too"
  input object machine.Address copied
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let where Int64 0 mut
  let bit Int64 0 mut
  let sixtyThree Int64 63
  let zeroBit Int64 0
:begin
  readTable: table = getAddress(object, relrAt)
  readBytes: bytes = getField(object, relrBytesAt)
  countOf: count = math.divideInt64(bytes, eight=8)
  readBase: base = getField(object, baseAt)
  goto eachEntry
:eachEntry loop=while max=count
  doneCheck: done = compare.greaterOrEqualInt64(at, count)
  if done finish readIt
:readIt in=eachEntry
  entryOf: entryOffset = math.multiplyInt64(at, eight)
  readEntry: entry = wordAt64(table, entryOffset)
  oddOf: odd = bits.andInt64(entry, one=1)
  oddCheck: isBitmap = compare.equalInt64(odd, one)
  if isBitmap bitmap addressEntry
:addressEntry in=eachEntry
  addressOf: addressNumber = math.wrappingAddInt64(base, entry)
  addAt: addBase(addressNumber, base)
  afterOf: afterAddress = math.wrappingAddInt64(addressNumber, eight)
  set where afterAddress
  goto advance
:bitmap in=eachEntry
  set bit zeroBit
  entryBits: entryWide = convert.int64BitsToUInt64(entry)
  goto eachBit
:eachBit loop=while max=sixtyThree in=eachEntry
  bitsDone: allBits = compare.greaterOrEqualInt64(bit, sixtyThree)
  if allBits nextBitmap testBit
:testBit in=eachBit
  bitPlace: bitIndex = math.addInt64(bit, one)
  shiftIt: shifted = bits.shiftRightUInt64(entryWide, bitIndex)
  lowBit: low = bits.andUInt64(shifted, oneWide=1)
  setCheck: isSet = compare.equalUInt64(low, oneWide)
  if isSet addBit nextBit
:addBit in=eachBit
  bitBytes: bitOffset = math.multiplyInt64(bit, eight)
  bitAddress: bitWhere = math.wrappingAddInt64(where, bitOffset)
  addBitIt: addBase(bitWhere, base)
  goto nextBit
:nextBit in=eachBit
  stepBit: afterBit = math.addInt64(bit, one)
  set bit afterBit
  goto eachBit
:nextBitmap in=eachEntry
  spanOf: span = math.multiplyInt64(sixtyThree, eight)
  moveOn: movedWhere = math.wrappingAddInt64(where, span)
  set where movedWhere
  goto advance
:advance in=eachEntry
  stepIt: next = math.addInt64(at, one)
  set at next
  goto eachEntry
:finish
  return

op addBase "Add the load bias to the word at an address"
  input where Int64 copied
  input base Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  addressOf: place = machine.fromInt64(where)
  readIt: value = machine.loadInt64(place)
  addIt: moved = math.wrappingAddInt64(value, base)
  storeIt: machine.storeInt64(place, moved)
  return

## ---------------------------------------------------------------- mapping

op mapLibrary "Map an open ELF file as a library's record: its file's device and inode first (a library loaded already is that record), then the ELF header checked (a 64-bit little-endian shared object for this machine, else the address 0 for notFound), its span reserved, and each PT_LOAD segment mapped from the file with its protection, its bytes past the file zeroed; PT_TLS traps. The file is closed"
  input fd Int64 copied
  input path machine.Address copied
  input pathBytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let low Int64 9223372036854775807 mut
  let high Int64 0 mut
  let dynamic Int64 -1 mut
  let machineType Int64 62 mut
  let armMachineType Int64 183
:begin
  nowhere: anywhere = machine.zero()
  findStat: stat = kernel.stateAt(statAt)
  statIt: statResult = system.fstat(fd, stat)
  statFailed: noStat = kernel.failed(statResult)
  if noStat notLibrary known
:known
  readDevice: device = wordAt64(stat, zero=0)
  readInode: inode = wordAt64(stat, eight=8)
  readSize: size = wordAt64(stat, fortyEight=48)
  findKnown: loaded = loadedRecord(device, inode)
  loadedCheck: isLoaded = machine.equal(loaded, anywhere)
  if isLoaded mapImage giveLoaded
:giveLoaded
  closeLoaded: closedLoaded = system.close(fd)
  return loaded
:mapImage
  smallCheck: tooSmall = compare.lessThanInt64(size, sixtyFour=64)
  if tooSmall notLibrary mapIt
:mapIt
  mapFile: imageNumber = system.mmap(anywhere, size, readOnly=1, private=2, fd, zero)
  mapFailed: noImage = kernel.failed(imageNumber)
  if noImage notLibrary checkHeader
:checkHeader
  imageOf: image = machine.fromInt64(imageNumber)
  readMagic: magic = wordAt32(image, zero)
  magicCheck: isElf = compare.equalInt64(magic, elfMagic=1179403647)
  readClass: classBytes = halfWordAt(image, four=4)
  classCheck: isLittle64 = compare.equalInt64(classBytes, class64Little=258)
  readType: fileType = halfWordAt(image, sixteen=16)
  typeCheck: isShared = compare.equalInt64(fileType, sharedType=3)
  archCheck: onArm = system.aarch64()
  if onArm armMachine headerChecks
:armMachine
  set machineType armMachineType
  goto headerChecks
:headerChecks
  readMachine: fileMachine = halfWordAt(image, eighteen=18)
  machineCheck: isThisMachine = compare.equalInt64(fileMachine, machineType)
  firstTwo: header1 = logic.and(isElf, isLittle64)
  firstThree: header2 = logic.and(header1, isShared)
  allFour: headerOk = logic.and(header2, isThisMachine)
  if headerOk record unmapNotLibrary
:unmapNotLibrary
  unmapBad: unmappedBad = system.munmap(image, size)
  goto notLibrary
:record
  takeRecord: object = heap.take(objectBytes)
  storeDevice: putField(object, deviceAt, device)
  storeInode: putField(object, inodeAt, inode)
  keepPath: keepNames(object, path, pathBytes)
  readHeaders: headersAt = wordAt64(image, thirtyTwo=32)
  readCount: headerCount = halfWordAt(image, fiftySix=56)
  findHeaders: headers = machine.offset(image, headersAt)
  goto eachSpan
:eachSpan loop=while max=headerCount
  spanDone: spansDone = compare.greaterOrEqualInt64(at, headerCount)
  if spansDone reserve spanHeader
:spanHeader in=eachSpan
  headerOffset: headerAt = math.multiplyInt64(at, fiftySix)
  findHeader: header = machine.offset(headers, headerAt)
  readKind: kind = wordAt32(header, zero)
  loadCheck: isLoad = compare.equalInt64(kind, one=1)
  if isLoad widen dynamicCheck
:widen in=eachSpan
  readStart: start = wordAt64(header, sixteen)
  readMemory: memoryBytes = wordAt64(header, forty=40)
  endOf: end = math.addInt64(start, memoryBytes)
  lowCheck: lower = compare.lessThanInt64(start, low)
  if lower takeLow highCheck
:takeLow in=eachSpan
  set low start
  goto highCheck
:highCheck in=eachSpan
  higherCheck: higher = compare.greaterThanInt64(end, high)
  if higher takeHigh nextSpan
:takeHigh in=eachSpan
  set high end
  goto nextSpan
:dynamicCheck in=eachSpan
  dynamicSame: isDynamic = compare.equalInt64(kind, two=2)
  if isDynamic takeDynamic tlsCheck
:takeDynamic in=eachSpan
  readDynamicStart: dynamicStart = wordAt64(header, sixteen)
  set dynamic dynamicStart
  goto nextSpan
:tlsCheck in=eachSpan
  tlsSame: isTls = compare.equalInt64(kind, tlsSegment=7)
  if isTls refuseTls nextSpan
:refuseTls in=eachSpan
  refuseIt: refuse(object, tlsReason="it has thread-local variables (PT_TLS), which only the C library's dynamic loader sets up")
  goto nextSpan
:nextSpan in=eachSpan
  stepSpan: afterSpan = math.addInt64(at, one)
  set at afterSpan
  goto eachSpan
:reserve
  noLoad: emptySpan = compare.greaterOrEqualInt64(low, high)
  noDynamic: missingDynamic = compare.lessThanInt64(dynamic, zero)
  eitherMissing: unusable = logic.or(emptySpan, missingDynamic)
  if unusable unmapNotLibrary reserveIt
:reserveIt
  readPage: page = pageSize()
  floorLow: lowPage = pageFloor(low, page)
  ceilHigh: highPage = pageCeiling(high, page)
  spanOf: span = math.subtractInt64(highPage, lowPage)
  reserveSpan: regionNumber = system.mmap(anywhere, span, noAccess=0, privateAnonymous=34, noFile=-1, zero)
  reserveFailed: noRegion = kernel.failed(regionNumber)
  if noRegion refuseMemory segments
:refuseMemory
  refuseMemoryIt: refuse(object, memoryReason="there is no memory to map it")
  goto segments
:segments
  baseOf: base = math.subtractInt64(regionNumber, lowPage)
  storeBase: putField(object, baseAt, base)
  set at zero
  goto eachSegment
:eachSegment loop=while max=headerCount
  segmentsDone: allMapped = compare.greaterOrEqualInt64(at, headerCount)
  if allMapped dynamicSection segmentHeader
:segmentHeader in=eachSegment
  segmentOffset: segmentAt = math.multiplyInt64(at, fiftySix)
  findSegment: segment = machine.offset(headers, segmentAt)
  readSegmentKind: segmentKind = wordAt32(segment, zero)
  segmentLoad: isSegmentLoad = compare.equalInt64(segmentKind, one)
  if isSegmentLoad mapSegmentIt nextSegment
:mapSegmentIt in=eachSegment
  mapOne: mapSegment(object, segment, fd, base, page)
  goto nextSegment
:nextSegment in=eachSegment
  stepSegment: afterSegment = math.addInt64(at, one)
  set at afterSegment
  goto eachSegment
:dynamicSection
  dynamicAddress: dynamicNumber = math.wrappingAddInt64(base, dynamic)
  dynamicOf: dynamicPlace = machine.fromInt64(dynamicNumber)
  storeDynamic: putAddress(object, dynamicAt, dynamicPlace)
  unmapImage: unmappedImage = system.munmap(image, size)
  closeIt: closed = system.close(fd)
  return object
:notLibrary
  closeNot: closedNot = system.close(fd)
  return anywhere

op mapSegment "Map one PT_LOAD segment at the base: its file bytes from the file (MAP_FIXED, private), the rest of its last file page zeroed, and pages past the file anonymous, each with the segment's protection"
  input object machine.Address copied
  input segment machine.Address copied
  input fd Int64 copied
  input base Int64 copied
  input page Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let protection Int64 0 mut
:begin
  readFlags: flags = wordAt32(segment, four=4)
  readFileOffset: fileOffset = wordAt64(segment, eight=8)
  readStart: start = wordAt64(segment, sixteen=16)
  readFileBytes: fileBytes = wordAt64(segment, thirtyTwo=32)
  readMemoryBytes: memoryBytes = wordAt64(segment, forty=40)
  executeOf: execute = bits.andInt64(flags, one=1)
  executeCheck: executable = compare.equalInt64(execute, one)
  if executable addExecute writeBit
:addExecute
  set protection four
  goto writeBit
:writeBit
  writeOf: write = bits.andInt64(flags, two=2)
  writeCheck: writable = compare.equalInt64(write, two)
  if writable addWrite readBit
:addWrite
  withWrite: protectionWrite = bits.orInt64(protection, two)
  set protection protectionWrite
  goto readBit
:readBit
  readOf: read = bits.andInt64(flags, four)
  readCheck: readable = compare.equalInt64(read, four)
  if readable addRead layout
:addRead
  withRead: protectionRead = bits.orInt64(protection, one)
  set protection protectionRead
  goto layout
:layout
  startPage: startFloor = pageFloor(start, page)
  offsetPage: offsetFloor = pageFloor(fileOffset, page)
  fileEndOf: fileEnd = math.addInt64(start, fileBytes)
  fileEndPage: fileEndCeiling = pageCeiling(fileEnd, page)
  memoryEndOf: memoryEnd = math.addInt64(start, memoryBytes)
  memoryEndPage: memoryEndCeiling = pageCeiling(memoryEnd, page)
  noFileCheck: fileless = compare.equalInt64(fileBytes, zero=0)
  if fileless anonymousAll fileMap
:fileMap
  fileSpan: fileMapBytes = math.subtractInt64(fileEndCeiling, startFloor)
  placeOf: placeNumber = math.wrappingAddInt64(base, startFloor)
  placeAddress: place = machine.fromInt64(placeNumber)
  mapIt: mapped = system.mmap(place, fileMapBytes, protection, privateFixed=18, fd, offsetFloor)
  mapFailed: refused = kernel.failed(mapped)
  if refused refuseMap zeroCheck
:refuseMap
  refuseIt: refuse(object, mapReason="a segment of it could not be mapped")
  return
:zeroCheck
  tailCheck: hasTail = compare.lessThanInt64(fileEnd, fileEndCeiling)
  moreCheck: memoryPast = compare.greaterThanInt64(memoryBytes, fileBytes)
  bothCheck: zeroTail = logic.and(hasTail, memoryPast)
  if zeroTail zeroIt anonymousCheck
:zeroIt
  tailStart: tailNumber = math.wrappingAddInt64(base, fileEnd)
  tailAddress: tail = machine.fromInt64(tailNumber)
  tailBytes: tailLength = math.subtractInt64(fileEndCeiling, fileEnd)
  fillIt: machine.fill(tail, nul=0, tailLength)
  goto anonymousCheck
:anonymousCheck
  pastCheck: pagesPast = compare.greaterThanInt64(memoryEndCeiling, fileEndCeiling)
  if pagesPast anonymousRest done
:anonymousRest
  restPlace: restNumber = math.wrappingAddInt64(base, fileEndCeiling)
  restAddress: rest = machine.fromInt64(restNumber)
  restSpan: restBytes = math.subtractInt64(memoryEndCeiling, fileEndCeiling)
  mapRest: restMapped = system.mmap(rest, restBytes, protection, anonymousFixed=50, noFile=-1, zero)
  goto done
:anonymousAll
  allPlace: allNumber = math.wrappingAddInt64(base, startFloor)
  allAddress: allStart = machine.fromInt64(allNumber)
  allSpan: allBytes = math.subtractInt64(memoryEndCeiling, startFloor)
  mapAll: allMapped = system.mmap(allStart, allBytes, protection, anonymousFixed, noFile, zero)
  goto done
:done
  return

op keepNames "Keep a copy of a library's path, and its directory for $ORIGIN (`.` when the path has no `/`), in its record"
  input object machine.Address copied
  input path machine.Address copied
  input bytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let slash Int64 -1 mut
  let at Int64 0 mut
  let dotText String "."
:begin
  withEnd: size = math.addInt64(bytes, one=1)
  takePath: pathCopy = heap.take(size)
  copyPath: machine.copy(pathCopy, path, bytes)
  storePath: putAddress(object, pathAt, pathCopy)
  storePathBytes: putField(object, pathBytesAt, bytes)
  goto eachByte
:eachByte loop=while max=bytes
  doneCheck: done = compare.greaterOrEqualInt64(at, bytes)
  if done origin readIt
:readIt in=eachByte
  findByte: place = machine.offset(path, at)
  readByte: value = machine.loadByte(place)
  slashCheck: isSlash = compare.equalByte(value, slashByte=47)
  if isSlash markSlash advance
:markSlash in=eachByte
  set slash at
  goto advance
:advance in=eachByte
  stepIt: next = math.addInt64(at, one)
  set at next
  goto eachByte
:origin
  noSlash: withoutSlash = compare.lessThanInt64(slash, zero=0)
  if withoutSlash dotOrigin pathOrigin
:dotOrigin
  takeDot: dot = heap.take(two=2)
  findDot: dotAt = machine.addressOfString(dotText)
  copyDot: machine.copy(dot, dotAt, one)
  storeDot: putAddress(object, originAt, dot)
  storeDotBytes: putField(object, originBytesAt, one)
  return
:pathOrigin
  originSize: originWithEnd = math.addInt64(slash, one)
  takeOrigin: originCopy = heap.take(originWithEnd)
  copyOrigin: machine.copy(originCopy, path, slash)
  storeOrigin: putAddress(object, originAt, originCopy)
  storeOriginBytes: putField(object, originBytesAt, slash)
  return

op loadedRecord "The record of a library loaded already from a file of a device and inode, or the address 0"
  input device Int64 copied
  input inode Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  let current Int64 0 mut
:begin
  findList: listSlot = kernel.stateAt(listAt)
  readFirst: first = machine.loadInt64(listSlot)
  set current first
  nowhere: anywhere = machine.zero()
  goto eachRecord
:eachRecord loop=while max=forever
  endCheck: ended = compare.equalInt64(current, zero=0)
  if ended absent compareIt
:compareIt in=eachRecord
  recordOf: record = machine.fromInt64(current)
  readDevice: recordDevice = getField(record, deviceAt)
  readInode: recordInode = getField(record, inodeAt)
  deviceSame: sameDevice = compare.equalInt64(recordDevice, device)
  inodeSame: sameInode = compare.equalInt64(recordInode, inode)
  bothSame: same = logic.and(sameDevice, sameInode)
  if same present advance
:advance in=eachRecord
  readNext: next = getField(record, nextAt)
  set current next
  goto eachRecord
:present
  return record
:absent
  return anywhere

## ---------------------------------------------------------------- the dynamic section

op readDynamic "Read a library's dynamic section into its record: its tables, relocations, initializers, RUNPATH, and DT_NEEDED names; DT_REL, DT_TEXTREL, and DF_TEXTREL or DF_STATIC_TLS trap"
  input object machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let needed Int64 0 mut
  let rpath Int64 0 mut
  let runpath Int64 0 mut
:begin
  readDynamicAddress: dynamic = getAddress(object, dynamicAt)
  readBase: base = getField(object, baseAt)
  goto eachCount
:eachCount loop=while max=forever
  countOffset: countAt = math.multiplyInt64(at, sixteen=16)
  readCountTag: countTag = wordAt64(dynamic, countAt)
  countEnd: countEnded = compare.equalInt64(countTag, zero=0)
  if countEnded counted countNeeded
:countNeeded in=eachCount
  neededSame: isNeeded = compare.equalInt64(countTag, one=1)
  if isNeeded addNeeded nextCount
:addNeeded in=eachCount
  moreNeeded: neededCount = math.addInt64(needed, one)
  set needed neededCount
  goto nextCount
:nextCount in=eachCount
  stepCount: afterCount = math.addInt64(at, one)
  set at afterCount
  goto eachCount
:counted
  neededBytes: neededSize = math.multiplyInt64(needed, eight=8)
  neededRoom: neededBlockSize = math.addInt64(neededSize, eight)
  takeNeeded: neededBlock = heap.take(neededBlockSize)
  storeNeeded: putAddress(object, neededAt, neededBlock)
  set needed zero
  set at zero
  goto eachEntry
:eachEntry loop=while max=forever
  entryOffset: entryAt = math.multiplyInt64(at, sixteen)
  readTag: tag = wordAt64(dynamic, entryAt)
  valueOffset: valueAt = math.addInt64(entryAt, eight)
  readValue: value = wordAt64(dynamic, valueAt)
  pointerOf: pointer = math.wrappingAddInt64(base, value)
  entryEnd: ended = compare.equalInt64(tag, zero)
  if ended finish takeEntry
:takeEntry in=eachEntry
  takeIt: kind = takeTag(object, tag, value, pointer)
  neededCheck: isNeededEntry = compare.equalInt64(kind, one)
  if isNeededEntry keepNeeded pathCheck
:keepNeeded in=eachEntry
  neededPlace: neededOffset = math.multiplyInt64(needed, eight)
  findNeeded: neededSlot = machine.offset(neededBlock, neededOffset)
  storeNeededName: machine.storeInt64(neededSlot, value)
  nextNeeded: afterNeeded = math.addInt64(needed, one)
  set needed afterNeeded
  goto advance
:pathCheck in=eachEntry
  rpathSame: isRpath = compare.equalInt64(tag, rpathTag=15)
  if isRpath keepRpath runpathCheck
:keepRpath in=eachEntry
  rpathPlus: rpathValue = math.addInt64(value, one)
  set rpath rpathValue
  goto advance
:runpathCheck in=eachEntry
  runpathSame: isRunpath = compare.equalInt64(tag, runpathTag=29)
  if isRunpath keepRunpath advance
:keepRunpath in=eachEntry
  runpathPlus: runpathValue = math.addInt64(value, one)
  set runpath runpathValue
  goto advance
:advance in=eachEntry
  stepIt: next = math.addInt64(at, one)
  set at next
  goto eachEntry
:finish
  storeCount: putField(object, neededCountAt, needed)
  runpathNone: noRunpath = compare.equalInt64(runpath, zero)
  if noRunpath useRpath useRunpath
:useRpath
  storeRpath: putField(object, runpathAt, rpath)
  return
:useRunpath
  storeRunpath: putField(object, runpathAt, runpath)
  return

op takeTag "Note one dynamic entry in a library's record; gives 1 for DT_NEEDED, else 0"
  input object machine.Address copied
  input tag Int64 copied
  input value Int64 copied
  input pointer Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let noValue Int64 0
  let neededKind Int64 1
:begin
  pointerAddress: place = machine.fromInt64(pointer)
  neededCheck: isNeeded = compare.equalInt64(tag, one=1)
  if isNeeded giveNeeded pltBytes
:giveNeeded
  return neededKind
:pltBytes
  pltSame: isPltBytes = compare.equalInt64(tag, two=2)
  if isPltBytes storePltBytes hash
:storePltBytes
  storeJmprelBytes: putField(object, jmprelBytesAt, value)
  return noValue
:hash
  hashSame: isHash = compare.equalInt64(tag, four=4)
  if isHash storeHash strings
:storeHash
  storeHashIt: putAddress(object, hashAt, place)
  return noValue
:strings
  stringsSame: isStrings = compare.equalInt64(tag, five=5)
  if isStrings storeStrings symbols
:storeStrings
  storeStringsIt: putAddress(object, strtabAt, place)
  return noValue
:symbols
  symbolsSame: isSymbols = compare.equalInt64(tag, six=6)
  if isSymbols storeSymbols rela
:storeSymbols
  storeSymbolsIt: putAddress(object, symtabAt, place)
  return noValue
:rela
  relaSame: isRela = compare.equalInt64(tag, seven=7)
  if isRela storeRela relaBytes
:storeRela
  storeRelaIt: putAddress(object, relaAt, place)
  return noValue
:relaBytes
  relaBytesSame: isRelaBytes = compare.equalInt64(tag, eight=8)
  if isRelaBytes storeRelaBytes init
:storeRelaBytes
  storeRelaBytesIt: putField(object, relaBytesAt, value)
  return noValue
:init
  initSame: isInit = compare.equalInt64(tag, twelve=12)
  if isInit storeInit relCheck
:storeInit
  storeInitIt: putAddress(object, initAt, place)
  return noValue
:relCheck
  relSame: isRel = compare.equalInt64(tag, relTag=17)
  if isRel refuseRel pltKind
:refuseRel
  refuseRelIt: refuse(object, relReason="it has DT_REL relocations, which x86_64 and AArch64 libraries do not use")
  return noValue
:pltKind
  pltKindSame: isPltKind = compare.equalInt64(tag, pltrelTag=20)
  if isPltKind pltKindCheck textCheck
:pltKindCheck
  relaKind: isRelaKind = compare.equalInt64(value, seven)
  if isRelaKind giveNone refuseRel
:textCheck
  textSame: isText = compare.equalInt64(tag, textrelTag=22)
  if isText refuseText jmprel
:refuseText
  refuseTextIt: refuse(object, textReason="it has text relocations (DT_TEXTREL), which write to its code")
  return noValue
:jmprel
  jmprelSame: isJmprel = compare.equalInt64(tag, jmprelTag=23)
  if isJmprel storeJmprel initArray
:storeJmprel
  storeJmprelIt: putAddress(object, jmprelAt, place)
  return noValue
:initArray
  initArraySame: isInitArray = compare.equalInt64(tag, initArrayTag=25)
  if isInitArray storeInitArray initArrayBytes
:storeInitArray
  storeInitArrayIt: putAddress(object, initArrayAt, place)
  return noValue
:initArrayBytes
  initArrayBytesSame: isInitArrayBytes = compare.equalInt64(tag, initArrayBytesTag=27)
  if isInitArrayBytes storeInitArrayBytes flagsCheck
:storeInitArrayBytes
  storeInitArrayBytesIt: putField(object, initArrayBytesAt, value)
  return noValue
:flagsCheck
  flagsSame: isFlags = compare.equalInt64(tag, flagsTag=30)
  if isFlags flagBits relrBytes
:flagBits
  textFlag: textBit = bits.andInt64(value, four)
  textFlagCheck: hasTextFlag = compare.notEqualInt64(textBit, zero=0)
  if hasTextFlag refuseText tlsFlag
:tlsFlag
  tlsFlagBit: tlsBit = bits.andInt64(value, sixteen=16)
  tlsFlagCheck: hasTlsFlag = compare.notEqualInt64(tlsBit, zero)
  if hasTlsFlag refuseTls giveNone
:refuseTls
  refuseTlsIt: refuse(object, tlsReason="it uses static thread-local storage (DF_STATIC_TLS), which only the C library's dynamic loader sets up")
  return noValue
:relrBytes
  relrBytesSame: isRelrBytes = compare.equalInt64(tag, relrBytesTag=35)
  if isRelrBytes storeRelrBytes relr
:storeRelrBytes
  storeRelrBytesIt: putField(object, relrBytesAt, value)
  return noValue
:relr
  relrSame: isRelr = compare.equalInt64(tag, relrTag=36)
  if isRelr storeRelr gnuHashEntry
:storeRelr
  storeRelrIt: putAddress(object, relrAt, place)
  return noValue
:gnuHashEntry
  gnuHashSame: isGnuHash = compare.equalInt64(tag, gnuHashTag=1879047925)
  if isGnuHash storeGnuHash giveNone
:storeGnuHash
  storeGnuHashIt: putAddress(object, gnuHashAt, place)
  return noValue
:giveNone
  return noValue

## ---------------------------------------------------------------- finding files

op searchList "Open a library's name in each directory of a colon-separated list (an empty one is `.`, and $ORIGIN at the start of one is the asking library's directory), the path found left in a builder; the descriptor, or -1 when no directory has it"
  input list machine.Address copied
  input listBytes Int64 copied
  input name machine.Address copied
  input bytes Int64 copied
  input requester machine.Address copied
  input builder machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let start Int64 0 mut
  let end Int64 0 mut
  let noValue Int64 -1
  let colonText String ":"
  let originText String "$ORIGIN"
  let dotText String "."
  let slashText String "/"
:begin
  findColon: colonAt = machine.addressOfString(colonText)
  findOrigin: originWord = machine.addressOfString(originText)
  nowhere: anywhere = machine.zero()
  goto eachDirectory
:eachDirectory loop=while max=forever
  pastCheck: past = compare.greaterThanInt64(start, listBytes)
  if past giveNone findEnd
:findEnd in=eachDirectory
  findStart: segment = machine.offset(list, start)
  restOf: rest = math.subtractInt64(listBytes, start)
  searchColon: colonOffset = memory.findBytes(segment, rest, colonAt, one=1)
  colonCheck: hasColon = compare.greaterOrEqualInt64(colonOffset, zero=0)
  if hasColon colonEnd listEnd
:colonEnd in=eachDirectory
  set end colonOffset
  goto build
:listEnd in=eachDirectory
  set end rest
  goto build
:build in=eachDirectory
  findLength: lengthSlot = machine.offset(builder, eight=8)
  clearLength: machine.storeInt64(lengthSlot, zero)
  emptyCheck: empty = compare.equalInt64(end, zero)
  if empty addDot originCheck
:addDot in=eachDirectory
  findDot: dotAt = machine.addressOfString(dotText)
  addDotIt: wide.builderAdd(builder, dotAt, one)
  goto addName
:originCheck in=eachDirectory
  longEnough: roomy = compare.greaterOrEqualInt64(end, seven=7)
  hasRequester: asked = machine.equal(requester, anywhere)
  someRequester: fromLibrary = logic.not(asked)
  bothOrigin: mayBeOrigin = logic.and(roomy, fromLibrary)
  if mayBeOrigin compareOrigin addSegment
:compareOrigin in=eachDirectory
  compareIt: order = machine.compare(segment, originWord, seven)
  sameCheck: isOrigin = compare.equalInt32(order, zero32=0)
  if isOrigin addOrigin addSegment
:addOrigin in=eachDirectory
  readOrigin: origin = getAddress(requester, originAt)
  readOriginBytes: originBytes = getField(requester, originBytesAt)
  addOriginIt: wide.builderAdd(builder, origin, originBytes)
  findAfter: after = machine.offset(segment, seven)
  afterBytes: afterLength = math.subtractInt64(end, seven)
  addAfterIt: wide.builderAdd(builder, after, afterLength)
  goto addName
:addSegment in=eachDirectory
  addSegmentIt: wide.builderAdd(builder, segment, end)
  goto addName
:addName in=eachDirectory
  findSlash: slashAt = machine.addressOfString(slashText)
  addSlashIt: wide.builderAdd(builder, slashAt, one)
  addNameIt: wide.builderAdd(builder, name, bytes)
  addEndIt: wide.builderAddByte(builder, nul=0)
  readPath: path = wide.builderText(builder)
  openIt: fd = system.openat(currentDirectory=-100, path, closeOnExec=524288, zero)
  openFailed: missing = kernel.failed(fd)
  if missing nextDirectory found
:nextDirectory in=eachDirectory
  afterEnd: nextStart = math.addInt64(start, end)
  skipColon: afterColon = math.addInt64(nextStart, one)
  set start afterColon
  goto eachDirectory
:found
  return fd
:giveNone
  return noValue

op findFile "Open the file of a library's name as dlopen finds it: a name with `/` is a path; any other is looked for in LD_LIBRARY_PATH, then the asking library's RUNPATH or RPATH, then the system's library directories; the path found is left in a builder. The descriptor, or -1"
  input name machine.Address copied
  input bytes Int64 copied
  input requester machine.Address copied
  input builder machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let slashText String "/"
  let variableText String "LD_LIBRARY_PATH="
  let intelDirectories String "/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu:/lib64:/usr/lib64:/lib:/usr/lib"
  let armDirectories String "/lib/aarch64-linux-gnu:/usr/lib/aarch64-linux-gnu:/lib64:/usr/lib64:/lib:/usr/lib"
:begin
  findSlash: slashAt = machine.addressOfString(slashText)
  searchSlash: slashOffset = memory.findBytes(name, bytes, slashAt, one=1)
  slashCheck: isPath = compare.greaterOrEqualInt64(slashOffset, zero=0)
  if isPath openPath environment
:openPath
  addPath: wide.builderAdd(builder, name, bytes)
  addEnd: wide.builderAddByte(builder, nul=0)
  readPath: path = wide.builderText(builder)
  openIt: fd = system.openat(currentDirectory=-100, path, closeOnExec=524288, zero)
  return fd
:environment
  findVariable: variable = environmentList(variableText)
  nowhere: anywhere = machine.zero()
  noVariable: unsetVariable = machine.equal(variable, anywhere)
  if unsetVariable runpath searchVariable
:searchVariable
  variableLength: variableBytes = clibrary.cStringLength(variable)
  emptyVariable: noDirectories = compare.equalInt64(variableBytes, zero)
  if noDirectories runpath searchVariable2
:searchVariable2
  searchIt: variableFd = searchList(variable, variableBytes, name, bytes, requester, builder)
  variableFound: inVariable = compare.greaterOrEqualInt64(variableFd, zero)
  if inVariable giveVariable runpath
:giveVariable
  return variableFd
:runpath
  noRequester: unasked = machine.equal(requester, anywhere)
  if unasked defaults runpathCheck
:runpathCheck
  readRunpath: runpathPlus = getField(requester, runpathAt)
  runpathNone: noRunpath = compare.equalInt64(runpathPlus, zero)
  if noRunpath defaults searchRunpath
:searchRunpath
  runpathOffset: runpathAt0 = math.subtractInt64(runpathPlus, one)
  readStrings: strings = getAddress(requester, strtabAt)
  findRunpath: runpathText = machine.offset(strings, runpathAt0)
  runpathLength: runpathBytes = clibrary.cStringLength(runpathText)
  searchRunpathIt: runpathFd = searchList(runpathText, runpathBytes, name, bytes, requester, builder)
  runpathFound: inRunpath = compare.greaterOrEqualInt64(runpathFd, zero)
  if inRunpath giveRunpath defaults
:giveRunpath
  return runpathFd
:defaults
  archCheck: onArm = system.aarch64()
  if onArm armDefaults intelDefaults
:armDefaults
  findArm: armAt = machine.addressOfString(armDirectories)
  armLength: armBytes = string.byteLength(armDirectories)
  searchArm: armFd = searchList(armAt, armBytes, name, bytes, requester, builder)
  return armFd
:intelDefaults
  findIntel: intelAt = machine.addressOfString(intelDirectories)
  intelLength: intelBytes = string.byteLength(intelDirectories)
  searchIntel: intelFd = searchList(intelAt, intelBytes, name, bytes, requester, builder)
  return intelFd

op environmentList "The value of an environment variable the process started with, given `NAME=`, as a C string, or the address 0"
  input prefix String borrowed
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  findPrefix: prefixAt = machine.addressOfString(prefix)
  prefixLength: prefixBytes = string.byteLength(prefix)
  readVector: vector = kernel.environmentVector()
  nowhere: anywhere = machine.zero()
  noVector: missing = machine.equal(vector, anywhere)
  if missing absent eachEntry
:eachEntry loop=while max=forever
  entryOffset: offset = math.multiplyInt64(at, eight=8)
  findEntry: entryAt = machine.offset(vector, offset)
  readEntry: entry = machine.loadAddress(entryAt)
  endCheck: ended = machine.equal(entry, anywhere)
  if ended absent compareIt
:compareIt in=eachEntry
  entryLength: entryBytes = clibrary.cStringLength(entry)
  longEnough: roomy = compare.greaterOrEqualInt64(entryBytes, prefixBytes)
  if roomy compareBytes advance
:compareBytes in=eachEntry
  compareEntry: order = machine.compare(entry, prefixAt, prefixBytes)
  sameCheck: same = compare.equalInt32(order, zero32=0)
  if same present advance
:advance in=eachEntry
  stepIt: next = math.addInt64(at, one=1)
  set at next
  goto eachEntry
:present
  findValue: value = machine.offset(entry, prefixBytes)
  return value
:absent
  return anywhere

## ---------------------------------------------------------------- loading

op isCPart "Whether a DT_NEEDED name is the C library or a part of it the runtime's C library stands for: the names ffi.open binds to it, and the dynamic loader itself"
  input name machine.Address copied
  input bytes Int64 copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let intelLoader String "ld-linux-x86-64.so.2"
  let armLoader String "ld-linux-aarch64.so.1"
  let yes Bool true
  let no Bool false
:begin
  libraryCheck: isLibrary = clibrary.cLibraryName(name, bytes)
  if isLibrary give intelCheck
:intelCheck
  intelLength: intelBytes = string.byteLength(intelLoader)
  intelSize: intelSame = compare.equalInt64(intelBytes, bytes)
  if intelSame intelCompare armCheck
:intelCompare
  findIntel: intelAt = machine.addressOfString(intelLoader)
  compareIntel: intelOrder = machine.compare(name, intelAt, bytes)
  intelZero: isIntel = compare.equalInt32(intelOrder, zero32=0)
  if isIntel give armCheck
:armCheck
  armLength: armBytes = string.byteLength(armLoader)
  armSize: armSame = compare.equalInt64(armBytes, bytes)
  if armSame armCompare notPart
:armCompare
  findArm: armAt = machine.addressOfString(armLoader)
  compareArm: armOrder = machine.compare(name, armAt, bytes)
  armZero: isArm = compare.equalInt32(armOrder, zero32)
  if isArm give notPart
:give
  return yes
:notPart
  return no

op loadNeeded "Load each library a library needs (DT_NEEDED), noting when it needs the C library; false when one is not found"
  input object machine.Address copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  recursion 32
  let at Int64 0 mut
  let count Int64 0 mut
  let yes Bool true
  let no Bool false
:begin
  readCount: needed = getField(object, neededCountAt)
  readNames: names = getAddress(object, neededAt)
  readStrings: strings = getAddress(object, strtabAt)
  sizeOf: depsBytes = math.multiplyInt64(needed, eight=8)
  roomOf: depsSize = math.addInt64(depsBytes, eight)
  takeDeps: deps = heap.take(depsSize)
  storeDeps: putAddress(object, depsAt, deps)
  nowhere: anywhere = machine.zero()
  goto eachName
:eachName loop=while max=needed
  doneCheck: done = compare.greaterOrEqualInt64(at, needed)
  if done finish readName
:readName in=eachName
  nameOffset: nameAt = math.multiplyInt64(at, eight)
  readOffset: offset = wordAt64(names, nameAt)
  findName: name = machine.offset(strings, offset)
  measureName: nameBytes = clibrary.cStringLength(name)
  partCheck: isPart = isCPart(name, nameBytes)
  if isPart markC loadIt
:markC in=eachName
  storeNeedsC: putField(object, needsCAt, one=1)
  goto advance
:loadIt in=eachName
  loadDep: dep = openNamed(name, nameBytes, object)
  missingCheck: missing = machine.equal(dep, anywhere)
  if missing notFound keepDep
:keepDep in=eachName
  depOffset: depAt = math.multiplyInt64(count, eight)
  findDep: depSlot = machine.offset(deps, depAt)
  storeDep: machine.storeAddress(depSlot, dep)
  moreDeps: depCount = math.addInt64(count, one)
  set count depCount
  goto advance
:advance in=eachName
  stepIt: next = math.addInt64(at, one)
  set at next
  goto eachName
:finish
  storeCount: putField(object, depCountAt, count)
  return yes
:notFound
  storeSome: putField(object, depCountAt, count)
  return no

op openNamed "A library loaded by a name as dlopen loads it with RTLD_NOW, for a library that asks (or none): found, mapped, linked into the list, its libraries loaded, relocated, and initialized; one loaded already is that record; the address 0 when it or a library it needs is not found or is not an ELF shared object for this machine"
  input name machine.Address copied
  input bytes Int64 copied
  input requester machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  recursion 32
:begin
  nowhere: anywhere = machine.zero()
  makeBuilder: builder = wide.builderNew()
  findIt: fd = findFile(name, bytes, requester, builder)
  missingCheck: missing = kernel.failed(fd)
  if missing giveNothing mapIt
:mapIt
  readPath: path = wide.builderText(builder)
  readPathBytes: pathWithEnd = wide.builderLength(builder)
  pathOnly: pathBytes = math.subtractInt64(pathWithEnd, one=1)
  mapItNow: object = mapLibrary(fd, path, pathBytes)
  giveText: heap.give(path)
  giveBuilder: heap.give(builder)
  noObject: notLibrary = machine.equal(object, anywhere)
  if notLibrary nothing stateCheck
:stateCheck
  readState: state = getField(object, stateField)
  freshCheck: fresh = compare.equalInt64(state, zero=0)
  if fresh load brokenCheck
:brokenCheck
  brokenSame: broken = compare.lessThanInt64(state, zero)
  if broken nothing give
:load
  markLoading: putField(object, stateField, one)
  findList: listSlot = kernel.stateAt(listAt)
  readFirst: first = machine.loadAddress(listSlot)
  linkIt: putAddress(object, nextAt, first)
  storeFirst: machine.storeAddress(listSlot, object)
  dynamicIt: readDynamic(object)
  loadDeps: loaded = loadNeeded(object)
  if loaded relocate markBroken
:markBroken
  storeBroken: putField(object, stateField, minusOne=-1)
  return anywhere
:relocate
  relocateIt: relocateLibrary(object)
  pointerIt: threadPointer()
  initIt: runInitializers(object)
  markReady: putField(object, stateField, two=2)
  return object
:give
  return object
:giveNothing
  giveTextMissing: readMissingText = wide.builderText(builder)
  giveMissingText: heap.give(readMissingText)
  giveMissingBuilder: heap.give(builder)
  return anywhere
:nothing
  return anywhere

op relocateLibrary "Apply a library's relocations: DT_RELR's, DT_RELA's, then DT_JMPREL's, each bound now"
  input object machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  compactIt: relocateCompact(object)
  readRela: rela = getAddress(object, relaAt)
  readRelaBytes: relaBytes = getField(object, relaBytesAt)
  relaIt: relocateTable(object, rela, relaBytes)
  readJmprel: jmprel = getAddress(object, jmprelAt)
  readJmprelBytes: jmprelBytes = getField(object, jmprelBytesAt)
  jmprelIt: relocateTable(object, jmprel, jmprelBytes)
  return

op threadPointer "Set up what a library's stack protector reads, once: on x86_64 the thread pointer (arch_prctl ARCH_SET_FS) to a block that points at itself, with a random canary at 0x28, but only in an executable (under `refined run` the thread pointer is the C library's); on AArch64 a random __stack_chk_guard"
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let guardName String "__stack_chk_guard"
:begin
  archCheck: onArm = system.aarch64()
  if onArm armGuard intelCheck
:armGuard
  findGuardName: guardNameAt = machine.addressOfString(guardName)
  guardLength: guardBytes = string.byteLength(guardName)
  findGuard: guard = clibrary.lookup(guardNameAt, guardBytes)
  readGuard: guardValue = machine.loadInt64(guard)
  guardSet: hasGuard = compare.notEqualInt64(guardValue, zero=0)
  if hasGuard done fillGuard
:fillGuard
  fillGuardIt: guardFilled = system.getrandom(guard, eight=8, zero)
  return
:intelCheck
  findSlot: slot = kernel.stateAt(threadAt)
  readBlock: made = machine.loadAddress(slot)
  nowhere: anywhere = machine.zero()
  madeCheck: notMade = machine.equal(made, anywhere)
  readVector: vector = kernel.argumentVector()
  startedCheck: notStarted = machine.equal(vector, anywhere)
  started: inExecutable = logic.not(notStarted)
  bothCheck: makeIt = logic.and(notMade, inExecutable)
  if makeIt make done
:make
  takeBlock: block = heap.take(blockBytes=256)
  storeSelf: machine.storeAddress(block, block)
  findSelf: selfAt = machine.offset(block, sixteen=16)
  storeSelfAgain: machine.storeAddress(selfAt, block)
  findCanary: canary = machine.offset(block, canaryAt=40)
  fillCanary: canaryFilled = system.getrandom(canary, eight, zero)
  setIt: setResult = system.archPrctl(setFs=4098, block)
  storeBlock: machine.storeAddress(slot, block)
  goto done
:done
  return

op runInitializers "Run a library's DT_INIT, then each function of its DT_INIT_ARRAY in order (0 and -1 are none)"
  input object machine.Address copied
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  nowhere: anywhere = machine.zero()
  readInit: init = getAddress(object, initAt)
  noInit: missingInit = machine.equal(init, anywhere)
  if missingInit array callInit
:callInit
  callIt: machine.callWithAddress(init, anywhere)
  goto array
:array
  readArray: functions = getAddress(object, initArrayAt)
  readArrayBytes: arrayBytes = getField(object, initArrayBytesAt)
  countOf: count = math.divideInt64(arrayBytes, eight=8)
  goto eachFunction
:eachFunction loop=while max=count
  doneCheck: done = compare.greaterOrEqualInt64(at, count)
  if done finish readFunction
:readFunction in=eachFunction
  functionOffset: offset = math.multiplyInt64(at, eight)
  readIt: function = wordAt64(functions, offset)
  zeroCheck: isZero = compare.equalInt64(function, zero=0)
  minusCheck: isMinus = compare.equalInt64(function, minusOne=-1)
  noneCheck: isNone = logic.or(isZero, isMinus)
  if isNone advance callFunction
:callFunction in=eachFunction
  functionAddress: functionAt = machine.fromInt64(function)
  callFunctionIt: machine.callWithAddress(functionAt, anywhere)
  goto advance
:advance in=eachFunction
  stepIt: next = math.addInt64(at, one=1)
  set at next
  goto eachFunction
:finish
  return

op openLibrary "ffi.open of a library other than the C library on Linux: the library's record, loaded as dlopen loads it (D-154), or the address 0 for notFound"
  invariant opensOrRefuses "A name no file has is the address 0"
  input name machine.Address copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere: anywhere = machine.zero()
  openIt: object = openNamed(name, bytes, anywhere)
  return object

@tests

test hashTest "The GNU and System V hashes of names are the ones linkers write"
  verifies gnuHash hashesLikeGnu
  verifies elfHash hashesLikeElf
  effect use machine.memory
  uses memoryAccess
  let printfName String "printf"
  let strlenName String "strlen"
:begin
  findPrintf: printfAt = machine.addressOfString(printfName)
  gnuPrintf: printfGnu = gnuHash(printfAt, six=6)
  expectGnuPrintf: test.assertEqualInt64(printfGnuValue=359345080, printfGnu)
  gnuEmpty: emptyGnu = gnuHash(printfAt, zero=0)
  expectGnuEmpty: test.assertEqualInt64(emptyGnuValue=5381, emptyGnu)
  elfPrintf: printfElf = elfHash(printfAt, six)
  expectElfPrintf: test.assertEqualInt64(printfElfValue=125371814, printfElf)
  findStrlen: strlenAt = machine.addressOfString(strlenName)
  gnuStrlen: strlenGnu = gnuHash(strlenAt, six)
  expectGnuStrlen: test.assertEqualInt64(strlenGnuValue=479443869, strlenGnu)
  elfStrlen: strlenElf = elfHash(strlenAt, six)
  expectElfStrlen: test.assertEqualInt64(strlenElfValue=128684734, strlenElf)
  return

test kindTest "Relocation types are read as the x86_64 and AArch64 ABIs number them"
  verifies relocationKind kindsLikeTheAbi
:begin
  intelRelative: relative = relocationKind(eight=8, no=false)
  expectRelative: test.assertEqualInt64(one=1, relative)
  armRelative: armRelativeKind = relocationKind(armRelativeType=1027, yes=true)
  expectArmRelative: test.assertEqualInt64(one, armRelativeKind)
  intelSlot: slot = relocationKind(seven=7, no)
  expectSlot: test.assertEqualInt64(two=2, slot)
  intelThread: thread = relocationKind(tpoff=18, no)
  expectThread: test.assertEqualInt64(three=3, thread)
  armIndirect: indirect = relocationKind(armIrelative=1032, yes)
  expectIndirect: test.assertEqualInt64(four=4, indirect)
  intelOther: other = relocationKind(pc32=2, no)
  expectOther: test.assertEqualInt64(five=5, other)
  return

test scopeTest "A library's scope falls back to the runtime's C library only when it needs it, for bind; a name no file has opens nothing"
  verifies symbolOf findsInScope
  verifies openLibrary opensOrRefuses
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let strlenName String "strlen"
  let missingPath String "/semanticscript/surely/missing/libnothing.so"
:begin
  takeRecord: object = heap.take(objectBytes)
  findStrlen: strlenAt = machine.addressOfString(strlenName)
  bindAlone: alone = symbolOf(object, strlenAt, six=6)
  nowhere: anywhere = machine.zero()
  aloneCheck: noneAlone = machine.equal(alone, anywhere)
  expectAlone: test.assertTrue(noneAlone)
  markC: putField(object, needsCAt, one=1)
  bindWithC: withC = symbolOf(object, strlenAt, six)
  withCCheck: noneWithC = machine.equal(withC, anywhere)
  someWithC: foundWithC = logic.not(noneWithC)
  expectWithC: test.assertTrue(foundWithC)
  giveRecord: heap.give(object)
  osCheck: onLinux = system.linux()
  if onLinux openMissing done
:openMissing
  findPath: missingAt = machine.addressOfString(missingPath)
  pathLength: pathBytes = string.byteLength(missingPath)
  openIt: opened = openLibrary(missingAt, pathBytes)
  openCheck: noneOpened = machine.equal(opened, anywhere)
  expectOpened: test.assertTrue(noneOpened)
  goto done
:done
  return
