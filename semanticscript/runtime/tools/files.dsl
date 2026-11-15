module files "Files and directories, paths resolved as Python resolves them, capability scopes on paths at run time, and one writer per file"
  path files
  imports standard.machine standard.system standard.string standard.math standard.compare standard.convert standard.bits standard.logic standard.test kernel memory numbers output frames heap handles regions slots wide tasks
  exports winErrno fileError resolve pathWithin checkScope textAt textBytes copyBytes fsOpenRead fsOpenWrite fsCreate fsOpenAppend fsRead fsWrite fsClose fsExists fsRemove fsCreateDirectory fsRemoveDirectory fsReadAll fsWriteAll fsLock fsUnlock fsListDirectory fsEntryCount fsEntryName

capability memoryAccess "Authority to read a call's paths and data and keep the open files and their claims in memory" use machine.memory none

capability systemCalls "Authority to open, read, write, lock, list, make, and remove files and directories, and resolve paths" use system.calls none

## As host.py and the C runtime: errors are classified as Python classifies them (a Windows error becomes an errno
## as Python's winerror_to_errno makes it, then notFound, denied, exists, or failed with the errno); D-52: one file,
## however it is named, is open for writing by one handle at most and never while another reads it, its key the
## path resolved as os.path.normcase(os.path.realpath(path)) and, once it is open, D-109: its identity, the volume
## and file index, so a hard link names the same file; D-38: a scoped path is resolved the same way and must lie in
## a scope of a capability the operation uses.
## machine.state bytes 704 to 767 belong to this module: 704 the address of the table of claims, 712 how many it
## holds, 720 how many it has room for, 728 to 759 a number's digits, 760 a count a system call writes; bytes 49664
## to 49727 a file's information (GetFileInformationByHandle), 49728 to 50319 a directory entry (FindFirstFileW).
## D-138, on Linux: 760 holds the errno of the last file call that failed, 49728 to 49871 a struct stat; a file's
## handle is its descriptor, paths are resolved as posixpath.realpath resolves them (links followed one component
## at a time, at most 40 of them), names are compared as they are (normcase changes nothing), and the claims, the
## scopes, and the errors are the same code as on Windows, with the errno the system call gave.
## A claim (32 bytes): the address of its key (a heap block), the key's length, how many read it, how many write it.
## A file (a heap block of fileBytes): 0 its handle, 8 its key and 16 the key's length, 24 its identity and 32 its
## length (0 when the system gives none), 40 whether it writes, 48 whether it is readable, 56 whether it is
## writable, 64 whether it appends.
constant claimsAt "Where the address of the table of claims is kept, in machine.state" Int64 704

constant claimCountAt "Where the number of claims is kept, in machine.state" Int64 712

constant claimCapacityAt "Where the number of claims the table has room for is kept, in machine.state" Int64 720

constant digitsAt "Where a number's digits are put together, in machine.state" Int64 728

constant countedAt "Where a system call writes a count, in machine.state" Int64 760

constant infoAt "Where a file's information is put, in machine.state" Int64 49664

constant foundAt "Where a directory entry is put, in machine.state" Int64 49728

constant claimBytes "The bytes of a claim" Int64 32

constant fileBytes "The bytes of a file" Int64 72

constant kindFile "The kind of a file's handle" Int64 1

constant kindListing "The kind of a directory listing's handle" Int64 2

constant openRead "Open for reading" Int64 0

constant openWrite "Open an existing file for reading and writing, emptied" Int64 1

constant openCreate "Create a new file for writing" Int64 2

constant openAppend "Open for writing at the end, made if missing" Int64 3

constant notFound "fs.FileError.notFound, numbered from 1" Int32 1

constant denied "fs.FileError.denied, numbered from 1" Int32 2

constant exists "fs.FileError.exists, numbered from 1" Int32 3

constant tooLarge "fs.FileError.tooLarge, numbered from 1" Int32 4

constant timedOut "fs.FileError.timedOut, numbered from 1" Int32 5

constant cancelledError "fs.FileError.cancelled, numbered from 1" Int32 6

constant busy "fs.FileError.busy, numbered from 1" Int32 7

constant failed "fs.FileError.failed, numbered from 1" Int32 8

constant outOfRange "fs.EntryIndexError.outOfRange, numbered from 1" Int32 1

constant genericRead "GENERIC_READ" Int32 -2147483648

constant genericWrite "GENERIC_WRITE" Int32 1073741824

constant genericReadWrite "GENERIC_READ and GENERIC_WRITE" Int32 -1073741824

constant shareReadWrite "FILE_SHARE_READ and FILE_SHARE_WRITE, as the C library opens files" Int32 3

constant shareAll "FILE_SHARE_READ, FILE_SHARE_WRITE, and FILE_SHARE_DELETE" Int32 7

constant normalFile "FILE_ATTRIBUTE_NORMAL" Int32 128

constant backupSemantics "FILE_FLAG_BACKUP_SEMANTICS, which opens a directory too" Int32 33554432

constant createNew "CREATE_NEW" Int32 1

constant openExisting "OPEN_EXISTING" Int32 3

constant openAlways "OPEN_ALWAYS" Int32 4

constant chunk "How many bytes one ReadFile asks for" Int64 65536

constant statAt "Where a struct stat is put on Linux, in machine.state" Int64 49728

constant atWorkingDirectory "AT_FDCWD: a path relative to the working directory" Int64 -100

constant closeOnExec "O_CLOEXEC: a child process does not inherit the descriptor" Int64 524288

constant typeMask "S_IFMT: the bits of st_mode that say what a path names" Int64 61440

constant typeDirectory "S_IFDIR: st_mode names a directory" Int64 16384

constant typeRegular "S_IFREG: st_mode names a regular file" Int64 32768

constant typeLink "S_IFLNK: st_mode names a symbolic link" Int64 40960

constant mostLinks "How many symbolic links one path resolves through, as the kernel's limit" Int64 40

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

op field "A whole number of a block at an offset"
  input block machine.Address copied
  input offset Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findField: place = machine.offset(block, offset)
  readField: value = machine.loadInt64(place)
  return value

op setField "Store a whole number in a block at an offset"
  input block machine.Address copied
  input offset Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  findField: place = machine.offset(block, offset)
  storeField: machine.storeInt64(place, value)
  return

op link "An address kept in a block at an offset"
  input block machine.Address copied
  input offset Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findField: place = machine.offset(block, offset)
  readField: value = machine.loadAddress(place)
  return value

op setLink "Store an address in a block at an offset"
  input block machine.Address copied
  input offset Int64 copied
  input value machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  findField: place = machine.offset(block, offset)
  storeField: machine.storeAddress(place, value)
  return

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

op textAt "The address of a call's text parameter's bytes"
  invariant readsTextAddress "Gives the first of the parameter's two slots as an address"
  input shape machine.Address copied
  input args machine.Address copied
  input parameter Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findSlot: slot = slots.slotOf(shape, args, parameter)
  readText: text = machine.loadAddress(slot)
  return text

op textBytes "How many bytes a call's text parameter has"
  invariant readsTextLength "Gives the second of the parameter's two slots"
  input shape machine.Address copied
  input args machine.Address copied
  input parameter Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findSlot: slot = slots.slotOf(shape, args, parameter)
  findLength: lengthSlot = machine.offset(slot, eight=8)
  readLength: bytes = machine.loadInt64(lengthSlot)
  return bytes

op copyBytes "A copy of some bytes in a new heap block, with a 0 byte after them"
  invariant copiesBytes "The block holds the bytes, then a 0"
  input data machine.Address copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  withEnd: size = math.addInt64(bytes, one=1)
  takeCopy: copy = heap.take(size)
  copyIn: machine.copy(copy, data, bytes)
  return copy

op cPath "A copy of a path's bytes with a 0 after them, for a Linux system call"
  input path machine.Address copied
  input bytes Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  copyIt: copied = copyBytes(path, bytes)
  return copied

op keepErrno "Keep the errno of a Linux system call's result that failed, for keptCode and lastFileError"
  input result Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  errnoOf: errno = kernel.errnoOf(result)
  findSlot: slot = stateAt(countedAt)
  storeIt: machine.storeInt64(slot, errno)
  return

op linuxMode "The st_mode of a struct stat on Linux, its type bits only"
  input status machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  modeOf: mode = unsignedAt(status, twentyFour=24)
  typeOf: kind = bits.andInt64(mode, typeMask)
  return kind

op statPath "newfstatat of a path on Linux into machine.state's struct stat, links followed or not: the kernel's result"
  input path machine.Address copied
  input bytes Int64 copied
  input follow Bool copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let flags Int64 0 mut
  let noFollowFlag Int64 256
:begin
  if follow statIt noFollow
:noFollow
  set flags noFollowFlag
  goto statIt
:statIt
  copyPath: name = cPath(path, bytes)
  findStatus: status = stateAt(statAt)
  callStat: result = system.newfstatat(atWorkingDirectory, name, status, flags)
  giveName: heap.give(name)
  return result

op closeFile "Close a file's handle: CloseHandle on Windows, close on Linux; nonzero when it worked, 0 when it failed (its error kept for lastFileError)"
  input handle machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let worked Int32 1
  let refused Int32 0
:begin
  osCheck: onLinux = system.linux()
  if onLinux linuxClose windowsClose
:linuxClose
  descriptorOf: fd = machine.toInt64(handle)
  closeIt: closed = system.close(fd)
  failedCheck: isFailure = kernel.failed(closed)
  if isFailure keepIt giveWorked
:keepIt
  keepCode: keepErrno(closed)
  return refused
:giveWorked
  return worked
:windowsClose
  closeHandleIt: closedHandle = system.closeHandle(handle)
  return closedHandle

op invalidHandle "Whether a handle is INVALID_HANDLE_VALUE (all bits set)"
  input handle machine.Address copied
  output Bool
  effect use machine.memory
  uses memoryAccess
:begin
  valueOf: value = machine.toInt64(handle)
  invalidCheck: invalid = compare.equalInt64(value, minusOne=-1)
  return invalid

op failText "Report a trap with a message and end the process with exit code 70"
  input text String borrowed
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findText: textAt2 = machine.addressOfString(text)
  textLength: bytes = string.byteLength(text)
  writeReport: status = frames.report(textAt2, bytes)
  exit: endProcess(trapCode=70)
  return

## ---------------------------------------------------------------- errors

op winErrno "A Windows error code as the errno Python's winerror_to_errno makes it, for the errors file and directory calls report; on Linux the code is the errno already"
  invariant mapsErrors "File and path not found are ENOENT (2), access and sharing errors EACCES (13), already exists EEXIST (17), and so on; any other is EINVAL (22)"
  input code Int32 copied
  output Int64
  effect use system.calls
  uses systemCalls
  let enoent Int64 2
  let ebadf Int64 9
  let eacces Int64 13
  let eexist Int64 17
  let exdev Int64 18
  let enotdir Int64 20
  let einval Int64 22
  let emfile Int64 24
  let enospc Int64 28
  let epipe Int64 32
  let enotempty Int64 41
:begin
  widenCode: value = convert.int32ToInt64(code)
  osCheck: onLinux = system.linux()
  if onLinux giveErrno mapWindows
:giveErrno
  return value
:mapWindows
  is2: c2 = compare.equalInt64(value, two=2)
  is3: c3 = compare.equalInt64(value, three=3)
  is15: c15 = compare.equalInt64(value, fifteen=15)
  is18: c18 = compare.equalInt64(value, eighteen=18)
  is53: c53 = compare.equalInt64(value, fiftyThree=53)
  is67: c67 = compare.equalInt64(value, sixtySeven=67)
  is161: c161 = compare.equalInt64(value, oneSixtyOne=161)
  is206: c206 = compare.equalInt64(value, twoOhSix=206)
  is123: c123 = compare.equalInt64(value, oneTwentyThree=123)
  or1: a1 = logic.or(c2, c3)
  or2: a2 = logic.or(a1, c15)
  or3: a3 = logic.or(a2, c18)
  or4: a4 = logic.or(a3, c53)
  or5: a5 = logic.or(a4, c67)
  or6: a6 = logic.or(a5, c161)
  or7: a7 = logic.or(a6, c206)
  or8: missing = logic.or(a7, c123)
  if missing giveNotFound accessCheck
:giveNotFound
  return enoent
:accessCheck
  is5: d5 = compare.equalInt64(value, five=5)
  is16: d16 = compare.equalInt64(value, sixteen=16)
  is19: d19 = compare.equalInt64(value, nineteen=19)
  is32: d32 = compare.equalInt64(value, thirtyTwo=32)
  is33: d33 = compare.equalInt64(value, thirtyThree=33)
  is65: d65 = compare.equalInt64(value, sixtyFive=65)
  is82: d82 = compare.equalInt64(value, eightyTwo=82)
  orA: b1 = logic.or(d5, d16)
  orB: b2 = logic.or(b1, d19)
  orC: b3 = logic.or(b2, d32)
  orD: b4 = logic.or(b3, d33)
  orE: b5 = logic.or(b4, d65)
  orF: refused = logic.or(b5, d82)
  if refused giveAccess existsCheck
:giveAccess
  return eacces
:existsCheck
  is80: e80 = compare.equalInt64(value, eighty=80)
  is183: e183 = compare.equalInt64(value, oneEightyThree=183)
  orExists: there = logic.or(e80, e183)
  if there giveExists othersCheck
:giveExists
  return eexist
:othersCheck
  is4: f4 = compare.equalInt64(value, four=4)
  if f4 giveFiles handleCheck
:giveFiles
  return emfile
:handleCheck
  is6: f6 = compare.equalInt64(value, six=6)
  if f6 giveBadHandle deviceCheck
:giveBadHandle
  return ebadf
:deviceCheck
  is17: f17 = compare.equalInt64(value, seventeen=17)
  if f17 giveDevice emptyCheck
:giveDevice
  return exdev
:emptyCheck
  is145: f145 = compare.equalInt64(value, oneFortyFive=145)
  if f145 giveNotEmpty directoryCheck
:giveNotEmpty
  return enotempty
:directoryCheck
  is267: f267 = compare.equalInt64(value, twoSixtySeven=267)
  if f267 giveNotDirectory fullCheck
:giveNotDirectory
  return enotdir
:fullCheck
  is112: f112 = compare.equalInt64(value, oneTwelve=112)
  is39: f39 = compare.equalInt64(value, thirtyNine=39)
  orFull: full = logic.or(f112, f39)
  if full giveFull pipeCheck
:giveFull
  return enospc
:pipeCheck
  is109: f109 = compare.equalInt64(value, oneOhNine=109)
  is232: f232 = compare.equalInt64(value, twoThirtyTwo=232)
  orPipe: broken = logic.or(f109, f232)
  if broken givePipe giveInvalid
:givePipe
  return epipe
:giveInvalid
  return einval

op fileError "An errno as fs.FileError, as Python classifies it: no such file is notFound, permission denied, already exists exists, any other failed with the errno; the variant's number, its payload stored"
  invariant classifiesErrno "ENOENT gives notFound, EACCES and EPERM denied, EEXIST exists, any other failed with the errno (1 for 0)"
  input payload machine.Address copied
  input errno Int64 copied
  output Int32
  effect use machine.memory
  uses memoryAccess
:begin
  missingCheck: isMissing = compare.equalInt64(errno, two=2)
  if isMissing giveMissing accessCheck
:giveMissing
  missingStatus: status1 = slots.failWith(payload, notFound, zero=0)
  return status1
:accessCheck
  accessCheck1: isAccess = compare.equalInt64(errno, thirteen=13)
  permissionCheck: isPermission = compare.equalInt64(errno, one=1)
  eitherCheck: isDenied = logic.or(isAccess, isPermission)
  if isDenied giveDenied existsCheck
:giveDenied
  deniedStatus: status2 = slots.failWith(payload, denied, zero)
  return status2
:existsCheck
  existsCheck1: isExists = compare.equalInt64(errno, seventeen=17)
  if isExists giveExists giveFailed
:giveExists
  existsStatus: status3 = slots.failWith(payload, exists, zero)
  return status3
:giveFailed
  zeroCheck: isZero = compare.equalInt64(errno, zero)
  if isZero giveOne giveErrno
:giveOne
  oneStatus: status4 = slots.failWith(payload, failed, one)
  return status4
:giveErrno
  errnoStatus: status5 = slots.failWith(payload, failed, errno)
  return status5

op lastFileError "The system's last error as fs.FileError"
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  osCheck: onLinux = system.linux()
  if onLinux linuxError windowsError
:linuxError
  findSlot: slot = stateAt(countedAt)
  readErrno: linuxErrno = machine.loadInt64(slot)
  classifyLinux: linuxStatus = fileError(payload, linuxErrno)
  return linuxStatus
:windowsError
  readError: code = system.getLastError()
  mapIt: errno = winErrno(code)
  classify: status = fileError(payload, errno)
  return status

## ---------------------------------------------------------------- paths: resolved as os.path.normcase(os.path.realpath(path))

op finalPath "The final path of something that exists, links and junctions followed, without its `\\\\?\\` prefix, as UTF-8 in a new heap block (its length stored at an address); the address 0 when it cannot be opened"
  input path machine.Address copied
  input bytes Int64 copied
  input lengthAt machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let skip Int64 0 mut
  let uncPrefix String "\\\\?\\UNC\\"
  let longPrefix String "\\\\?\\"
:begin
  nowhere: anywhere = machine.zero()
  wideName: name = wide.widen(path, bytes)
  open: handle = system.createFileW(name, noAccess=0, shareAll, anywhere, openExisting, backupSemantics, anywhere)
  giveName: heap.give(name)
  invalidCheck: invalid = invalidHandle(handle)
  if invalid giveNothing measure
:giveNothing
  return anywhere
:measure
  measureIt: units32 = system.getFinalPathNameByHandleW(handle, anywhere, noAccess, normalized=0)
  unitsOf: units = convert.int32ToInt64(units32)
  emptyCheck: empty = compare.equalInt64(units, zero=0)
  if empty closeNothing read
:closeNothing
  closeEmpty: closedEmpty = system.closeHandle(handle)
  return anywhere
:read
  withEnd: room = math.addInt64(units, one=1)
  sizeOf: size = math.multiplyInt64(room, two=2)
  takeBuffer: buffer = heap.take(size)
  roomNarrow: room32 = convert.int64ToInt32(room)
  readIt: got32 = system.getFinalPathNameByHandleW(handle, buffer, room32, normalized)
  closeIt: closed = system.closeHandle(handle)
  gotOf: got = convert.int32ToInt64(got32)
  failedCheck: failedRead = compare.equalInt64(got, zero)
  if failedRead giveBuffer narrowIt
:giveBuffer
  giveIt: heap.give(buffer)
  return anywhere
:narrowIt
  makeText: text = wide.narrow(buffer, got, lengthAt)
  giveWide: heap.give(buffer)
  readLength: length = machine.loadInt64(lengthAt)
  findUnc: uncAt = machine.addressOfString(uncPrefix)
  uncLength: uncBytes = string.byteLength(uncPrefix)
  uncFits: uncRoom = compare.greaterOrEqualInt64(length, uncBytes)
  if uncRoom compareUnc longCheck
:compareUnc
  sameUnc: uncOrder = machine.compare(text, uncAt, uncBytes)
  uncCheck: isUnc = compare.equalInt32(uncOrder, zero32=0)
  if isUnc stripUnc longCheck
:stripUnc
  keepFrom: uncSkip = math.subtractInt64(uncBytes, two)
  set skip uncSkip
  findFirst: first = machine.offset(text, skip)
  storeSlash: machine.storeByte(first, backslash=92)
  findSecond: second = machine.offset(first, one)
  storeSlashAgain: machine.storeByte(second, backslash)
  goto strip
:longCheck
  findLong: longAt = machine.addressOfString(longPrefix)
  longLength: longBytes = string.byteLength(longPrefix)
  longFits: longRoom = compare.greaterOrEqualInt64(length, longBytes)
  if longRoom compareLong strip
:compareLong
  sameLong: longOrder = machine.compare(text, longAt, longBytes)
  longPrefixCheck: isLong = compare.equalInt32(longOrder, zero32)
  if isLong stripLong strip
:stripLong
  set skip longBytes
  goto strip
:strip
  restOf: rest = math.subtractInt64(length, skip)
  findRest: restAt = machine.offset(text, skip)
  copyRest: result = copyBytes(restAt, rest)
  giveText: heap.give(text)
  storeLength: machine.storeInt64(lengthAt, rest)
  return result

op resolveFull "An absolute, normalized path with its longest existing prefix resolved (links followed) and the rest kept as written, as UTF-8 in a new heap block; its length stored at an address"
  input full machine.Address copied
  input bytes Int64 copied
  input lengthAt machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  recursion 256
  let at Int64 0 mut
  let headBytes Int64 0 mut
  let backslash Byte 92
  let colon Byte 58
:begin
  tryFinal: done = finalPath(full, bytes, lengthAt)
  nowhere: anywhere = machine.zero()
  missingCheck: missing = machine.equal(done, anywhere)
  if missing split giveDone
:giveDone
  return done
:split
  set at bytes
  goto eachByte
:eachByte loop=while max=bytes
  startCheck: atStart = compare.lessOrEqualInt64(at, zero=0)
  if atStart splitDone checkByte
:checkByte in=eachByte
  before: previous = math.subtractInt64(at, one=1)
  readByte: byte = byteAt(full, previous)
  separatorCheck: atSeparator = compare.equalByte(byte, backslash)
  if atSeparator splitDone stepBack
:stepBack in=eachByte
  set at previous
  goto eachByte
:splitDone
  noSplitCheck: noSplit = compare.equalInt64(at, zero)
  wholeCheck: whole = compare.equalInt64(at, bytes)
  keepCheck: keepWhole = logic.or(noSplit, whole)
  if keepWhole giveCopy findHead
:giveCopy
  copyIt: copy = copyBytes(full, bytes)
  storeLength: machine.storeInt64(lengthAt, bytes)
  return copy
:findHead
  headOf: head = math.subtractInt64(at, one)
  set headBytes head
  rootCheck: atRoot = compare.equalInt64(head, zero)
  if atRoot keepSeparator driveCheck
:driveCheck
  twoCheck: isTwo = compare.equalInt64(head, two=2)
  if isTwo driveColon headCompare
:driveColon
  readColon: second = byteAt(full, one)
  colonCheck: isDrive = compare.equalByte(second, colon)
  if isDrive keepSeparator headCompare
:keepSeparator
  withSeparator: rootBytes = math.addInt64(head, one)
  set headBytes rootBytes
  goto headCompare
:headCompare
  sameCheck: same = compare.equalInt64(headBytes, bytes)
  if same giveCopy resolveHead
:resolveHead
  resolveIt: base = resolveFull(full, headBytes, lengthAt)
  readBase: baseBytes = machine.loadInt64(lengthAt)
  tailOf: tailBytes = math.subtractInt64(bytes, at)
  findTail: tail = machine.offset(full, at)
  makeBuilder: builder = wide.builderNew()
  addBase: wide.builderAdd(builder, base, baseBytes)
  emptyCheck: baseEmpty = compare.equalInt64(baseBytes, zero)
  if baseEmpty addSeparator lastCheck
:lastCheck
  lastOf: lastAt = math.subtractInt64(baseBytes, one)
  readLast: last = byteAt(base, lastAt)
  endsCheck: endsWithSeparator = compare.equalByte(last, backslash)
  if endsWithSeparator addTail addSeparator
:addSeparator
  addIt: wide.builderAddByte(builder, backslash)
  goto addTail
:addTail
  addRest: wide.builderAdd(builder, tail, tailBytes)
  giveBase: heap.give(base)
  readBuilt: built = wide.builderText(builder)
  readBuiltLength: builtBytes = wide.builderLength(builder)
  copyBuilt: result = copyBytes(built, builtBytes)
  giveBuilt: heap.give(built)
  giveBuilder: heap.give(builder)
  storeResultLength: machine.storeInt64(lengthAt, builtBytes)
  return result

op resolve "A path as Python's os.path.normcase(os.path.realpath(path)) gives it on Windows, as UTF-8 in a new heap block; its length stored at an address. An empty path is `.`"
  invariant resolvesPath "Gives the absolute path with links followed, in lower case, every separator `\\`"
  input path machine.Address copied
  input bytes Int64 copied
  input lengthAt machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let sourceValue Int64 0 mut
  let sourceBytes Int64 0 mut
  let dot String "."
:begin
  emptyCheck: empty = compare.equalInt64(bytes, zero=0)
  if empty useDot usePath
:useDot
  findDot: dotAt = machine.addressOfString(dot)
  copyDot: dotCopy = copyBytes(dotAt, one=1)
  dotValue: dotCopyValue = machine.toInt64(dotCopy)
  set sourceValue dotCopyValue
  set sourceBytes one
  goto full
:usePath
  copyPath: pathCopy = copyBytes(path, bytes)
  pathValue: pathCopyValue = machine.toInt64(pathCopy)
  set sourceValue pathCopyValue
  set sourceBytes bytes
  goto full
:full
  osCheck: onLinux = system.linux()
  if onLinux linuxResolve windowsResolve
:linuxResolve
  linuxSource: linuxFrom = machine.fromInt64(sourceValue)
  realLinux: linuxReal = resolveLinux(linuxFrom, sourceBytes, lengthAt)
  giveLinuxSource: heap.give(linuxFrom)
  return linuxReal
:windowsResolve
  nowhere: anywhere = machine.zero()
  sourceOf: source = machine.fromInt64(sourceValue)
  wideName: name = wide.widen(source, sourceBytes)
  measure: units32 = system.getFullPathNameW(name, zero32=0, anywhere, anywhere)
  unitsOf: units = convert.int32ToInt64(units32)
  noneCheck: noUnits = compare.equalInt64(units, zero)
  if noUnits keepSource fullPath
:fullPath
  withRoom: room = math.addInt64(units, two=2)
  sizeOf: size = math.multiplyInt64(room, two)
  takeBuffer: buffer = heap.take(size)
  roomUnits: roomCount = math.addInt64(units, one)
  narrowRoom: room32 = convert.int64ToInt32(roomCount)
  fill: got32 = system.getFullPathNameW(name, room32, buffer, anywhere)
  gotOf: got = convert.int32ToInt64(got32)
  failCheck: notFilled = compare.equalInt64(got, zero)
  if notFilled dropBuffer narrowFull
:dropBuffer
  giveBuffer: heap.give(buffer)
  goto keepSource
:narrowFull
  makeFull: fullText = wide.narrow(buffer, got, lengthAt)
  giveFullBuffer: heap.give(buffer)
  readFullLength: fullBytes = machine.loadInt64(lengthAt)
  giveSource: heap.give(source)
  fullValue: fullTextValue = machine.toInt64(fullText)
  set sourceValue fullTextValue
  set sourceBytes fullBytes
  goto resolveIt
:keepSource
  goto resolveIt
:resolveIt
  giveName: heap.give(name)
  finalOf: finalSource = machine.fromInt64(sourceValue)
  realOf: real = resolveFull(finalSource, sourceBytes, lengthAt)
  readReal: realBytes = machine.loadInt64(lengthAt)
  lowerIt: lowered = wide.lowercase(real, realBytes, lengthAt)
  giveReal: heap.give(real)
  giveFinal: heap.give(finalSource)
  return lowered

op resolveLinux "A path as posixpath.realpath gives it on Linux, as UTF-8 in a new heap block; its length stored at an address: absolute (from the working directory), `.` and empty names dropped, `..` taking off the name before it, each symbolic link replaced by what it holds (an absolute one starting again at `/`), at most 40 of them; names past one that is not there are kept as written"
  input path machine.Address copied
  input bytes Int64 copied
  input lengthAt machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let start Int64 0 mut
  let links Int64 0 mut
  let resultBytes Int64 0 mut
  let yes Bool true
  let no Bool false
  let slash Byte 47
  let dot Byte 46
  let most Int64 1048576
  let roomBytes Int64 4096
:begin
  makeResult: result = wide.builderNew()
  makeRest: rest = wide.builderNew()
  addPath: wide.builderAdd(rest, path, bytes)
  takeBuffer: buffer = heap.take(roomBytes)
  emptyCheck: empty = compare.equalInt64(bytes, zero=0)
  if empty fromWorking firstCheck
:firstCheck
  readFirst: first = byteAt(path, zero)
  absoluteCheck: absolute = compare.equalByte(first, slash)
  if absolute eachName fromWorking
:fromWorking
  askCwd: got = system.getcwd(buffer, roomBytes)
  cwdFailed: noCwd = kernel.failed(got)
  if noCwd eachName addCwd
:addCwd
  withoutEnd: cwdBytes = math.subtractInt64(got, one=1)
  rootCheck: isRoot = compare.lessOrEqualInt64(cwdBytes, one)
  if isRoot eachName addWorking
:addWorking
  addCwdText: wide.builderAdd(result, buffer, cwdBytes)
  goto eachName
:eachName loop=while max=most
  readRest: restText = wide.builderText(rest)
  readRestBytes: restBytes = wide.builderLength(rest)
  endCheck: atEnd = compare.greaterOrEqualInt64(at, restBytes)
  if atEnd finish skipCheck
:skipCheck in=eachName
  readHere: here = byteAt(restText, at)
  slashCheck: isSlash = compare.equalByte(here, slash)
  if isSlash skipSlash nameStart
:skipSlash in=eachName
  pastSlash: afterSlash = math.addInt64(at, one)
  set at afterSlash
  goto eachName
:nameStart in=eachName
  set start at
  goto eachByte
:eachByte loop=while max=most in=eachName
  byteEnd: atByteEnd = compare.greaterOrEqualInt64(at, restBytes)
  if atByteEnd nameFound checkByte
:checkByte in=eachByte
  readByte: byte = byteAt(restText, at)
  byteSlash: byteIsSlash = compare.equalByte(byte, slash)
  if byteIsSlash nameFound nextByte
:nextByte in=eachByte
  pastByte: afterByte = math.addInt64(at, one)
  set at afterByte
  goto eachByte
:nameFound in=eachName
  lengthOf: nameBytes = math.subtractInt64(at, start)
  findName: name = machine.offset(restText, start)
  oneCheck: isOne = compare.equalInt64(nameBytes, one)
  if isOne dotCheck dotsCheck
:dotCheck in=eachName
  readDot: onlyByte = byteAt(name, zero)
  isDotCheck: isDot = compare.equalByte(onlyByte, dot)
  if isDot eachName joinName
:dotsCheck in=eachName
  twoCheck: isTwo = compare.equalInt64(nameBytes, two=2)
  if isTwo dotsFirst joinName
:dotsFirst in=eachName
  readDotOne: dotOne = byteAt(name, zero)
  readDotTwo: dotTwo = byteAt(name, one)
  firstDot: isDotOne = compare.equalByte(dotOne, dot)
  secondDot: isDotTwo = compare.equalByte(dotTwo, dot)
  bothDots: isParent = logic.and(isDotOne, isDotTwo)
  if isParent parent joinName
:parent in=eachName
  readResultBytes: haveBytes = wide.builderLength(result)
  set resultBytes haveBytes
  goto eachBack
:eachBack loop=while max=most in=eachName
  backDone: noneLeft = compare.lessOrEqualInt64(resultBytes, zero)
  if noneLeft cutParent backByte
:backByte in=eachBack
  lastOf: lastAt = math.subtractInt64(resultBytes, one)
  readResultText: resultText = wide.builderText(result)
  readLast: last = byteAt(resultText, lastAt)
  set resultBytes lastAt
  lastSlash: isLastSlash = compare.equalByte(last, slash)
  if isLastSlash cutParent eachBack
:cutParent in=eachName
  findLength: resultLengthSlot = machine.offset(result, eight=8)
  storeLength: machine.storeInt64(resultLengthSlot, resultBytes)
  goto eachName
:joinName in=eachName
  readBefore: beforeBytes = wide.builderLength(result)
  addSlash: wide.builderAddByte(result, slash)
  addName: wide.builderAdd(result, name, nameBytes)
  readCandidate: candidate = wide.builderText(result)
  readCandidateBytes: candidateBytes = wide.builderLength(result)
  statIt: statResult = statPath(candidate, candidateBytes, no)
  statFailed: missing = kernel.failed(statResult)
  if missing eachName linkCheck
:linkCheck in=eachName
  findStatus: status = stateAt(statAt)
  readMode: mode = linuxMode(status)
  isLinkCheck: isLink = compare.equalInt64(mode, typeLink)
  tooManyCheck: tooMany = compare.greaterOrEqualInt64(links, mostLinks)
  notTooMany: underLimit = logic.not(tooMany)
  followCheck: follow = logic.and(isLink, underLimit)
  if follow readLink eachName
:readLink in=eachName
  copyCandidate: linkName = cPath(candidate, candidateBytes)
  readIt: linkBytes = system.readlinkat(atWorkingDirectory, linkName, buffer, roomBytes)
  giveLinkName: heap.give(linkName)
  linkFailed: noLink = kernel.failed(linkBytes)
  if noLink eachName expand
:expand in=eachName
  moreLinks: linksNow = math.addInt64(links, one)
  set links linksNow
  goto expandRest
:expandRest in=eachName
  findBeforeLength: beforeSlot = machine.offset(result, eight)
  storeBefore: machine.storeInt64(beforeSlot, beforeBytes)
  makeNewRest: newRest = wide.builderNew()
  addTarget: wide.builderAdd(newRest, buffer, linkBytes)
  addRestSlash: wide.builderAddByte(newRest, slash)
  tailOf: tailBytes = math.subtractInt64(restBytes, at)
  findTail: tail = machine.offset(restText, at)
  addTail: wide.builderAdd(newRest, tail, tailBytes)
  readOldRest: oldRestText = wide.builderText(rest)
  giveOldRestText: heap.give(oldRestText)
  readNewText: newText = wide.builderText(newRest)
  storeNewText: machine.storeAddress(rest, newText)
  findNewLength: newLengthSlot = machine.offset(newRest, eight)
  readNewLength: newLength = machine.loadInt64(newLengthSlot)
  findRestLength: restLengthSlot = machine.offset(rest, eight)
  storeRestLength: machine.storeInt64(restLengthSlot, newLength)
  findNewRoom: newRoomSlot = machine.offset(newRest, sixteen=16)
  readNewRoom: newRoom = machine.loadInt64(newRoomSlot)
  findRestRoom: restRoomSlot = machine.offset(rest, sixteen)
  storeRestRoom: machine.storeInt64(restRoomSlot, newRoom)
  giveNewRest: heap.give(newRest)
  set at zero
  readTargetFirst: targetFirst = byteAt(buffer, zero)
  absoluteTarget: targetAbsolute = compare.equalByte(targetFirst, slash)
  if targetAbsolute restartRoot eachName
:restartRoot in=eachName
  findRootLength: rootLengthSlot = machine.offset(result, eight)
  storeRoot: machine.storeInt64(rootLengthSlot, zero)
  goto eachName
:finish
  readFinal: finalBytes = wide.builderLength(result)
  emptyResult: noBytes = compare.equalInt64(finalBytes, zero)
  if noBytes giveRoot giveResult
:giveRoot
  addRoot: wide.builderAddByte(result, slash)
  goto giveResult
:giveResult
  readResultFinal: resultFinal = wide.builderText(result)
  readResultFinalBytes: resultFinalBytes = wide.builderLength(result)
  copyResult: resolved = copyBytes(resultFinal, resultFinalBytes)
  storeResolvedLength: machine.storeInt64(lengthAt, resultFinalBytes)
  giveResultText: heap.give(resultFinal)
  giveResultBuilder: heap.give(result)
  readRestFinal: restFinal = wide.builderText(rest)
  giveRestText: heap.give(restFinal)
  giveRestBuilder: heap.give(rest)
  giveBuffer: heap.give(buffer)
  return resolved

op pathSeparator "The path separator: `\\` on Windows, `/` on Linux"
  output Byte
  effect use system.calls
  uses systemCalls
  let slashByte Byte 47
  let backslashByte Byte 92
:begin
  osCheck: onLinux = system.linux()
  if onLinux giveSlash giveBackslash
:giveSlash
  return slashByte
:giveBackslash
  return backslashByte

op isSeparator "Whether a byte is a path separator: on Windows `/` or `\\`, on Linux `/`"
  input byte Byte copied
  output Bool
  effect use system.calls
  uses systemCalls
:begin
  slashCheck: isSlash = compare.equalByte(byte, slash=47)
  backslashCheck: isBackslash = compare.equalByte(byte, backslash=92)
  osCheck: onLinux = system.linux()
  if onLinux giveSlash giveEither
:giveSlash
  return isSlash
:giveEither
  eitherCheck: either = logic.or(isSlash, isBackslash)
  return either

op asPrefix "A resolved path with its trailing separators taken off and one `\\` put back, in a new heap block; its length stored at an address"
  input base machine.Address copied
  input bytes Int64 copied
  input lengthAt machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  findSeparator: backslash = pathSeparator()
  set at bytes
  goto eachByte
:eachByte loop=while max=bytes
  startCheck: atStart = compare.lessOrEqualInt64(at, zero=0)
  if atStart make checkByte
:checkByte in=eachByte
  before: previous = math.subtractInt64(at, one=1)
  readByte: byte = byteAt(base, previous)
  separatorCheck: isSlash = compare.equalByte(byte, backslash)
  if isSlash stepBack make
:stepBack in=eachByte
  set at previous
  goto eachByte
:make
  withSeparator: size = math.addInt64(at, two=2)
  takePrefix: prefix = heap.take(size)
  copyBase: machine.copy(prefix, base, at)
  findEnd: endAt = machine.offset(prefix, at)
  storeSeparator: machine.storeByte(endAt, backslash)
  lengthOf: length = math.addInt64(at, one)
  storeLength: machine.storeInt64(lengthAt, length)
  return prefix

op startsWith "Whether a text starts with another"
  input text machine.Address copied
  input bytes Int64 copied
  input prefix machine.Address copied
  input prefixBytes Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let no Bool false
:begin
  longEnough: fits = compare.greaterOrEqualInt64(bytes, prefixBytes)
  if fits compareIt notIt
:compareIt
  compareBytes: order = machine.compare(text, prefix, prefixBytes)
  sameCheck: same = compare.equalInt32(order, zero32=0)
  return same
:notIt
  return no

op pathWithin "library.path_within with links resolved: whether a path lies in a directory scope (`data/`) or matches a name pattern (`suite-*`)"
  invariant checksScope "A path inside the scope's directory, or the directory itself, is within `dir/`; a path whose name in the scope's directory starts with the pattern is within `dir/prefix*`; nothing is within a scope that ends otherwise"
  input path machine.Address copied
  input pathBytes Int64 copied
  input scope machine.Address copied
  input scopeBytes Int64 copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let headBytes Int64 0 mut
  let length Int64 0 mut
  let no Bool false
  let slash Byte 47
  let star Byte 42
:begin
  findSeparator: backslash = pathSeparator()
  emptyCheck: empty = compare.equalInt64(scopeBytes, zero=0)
  if empty notIt readLast
:notIt
  return no
:readLast
  lastOf: lastAt = math.subtractInt64(scopeBytes, one=1)
  readLastByte: last = byteAt(scope, lastAt)
  slashCheck: isDirectory = compare.equalByte(last, slash)
  starCheck: isPattern = compare.equalByte(last, star)
  eitherCheck: either = logic.or(isDirectory, isPattern)
  if either resolvePath notIt
:resolvePath
  takeCell: cell = heap.take(eight=8)
  realOf: real = resolve(path, pathBytes, cell)
  readReal: realBytes = machine.loadInt64(cell)
  if isDirectory directory pattern
:directory
  baseOf: base = resolve(scope, lastAt, cell)
  readBase: baseBytes = machine.loadInt64(cell)
  prefixOf: prefix = asPrefix(base, baseBytes, cell)
  readPrefix: prefixBytes = machine.loadInt64(cell)
  sameLength: sameSize = compare.equalInt64(realBytes, baseBytes)
  if sameSize compareBase compareDirectoryPrefix
:compareBase
  compareSame: sameOrder = machine.compare(real, base, baseBytes)
  sameCheck: isSame = compare.equalInt32(sameOrder, zero32=0)
  if isSame directoryInside compareDirectoryPrefix
:compareDirectoryPrefix
  insideCheck: inside = startsWith(real, realBytes, prefix, prefixBytes)
  if inside directoryInside directoryOutside
:directoryInside
  giveRealIn: heap.give(real)
  giveBaseIn: heap.give(base)
  givePrefixIn: heap.give(prefix)
  giveCellIn: heap.give(cell)
  return isDirectory
:directoryOutside
  giveRealOut: heap.give(real)
  giveBaseOut: heap.give(base)
  givePrefixOut: heap.give(prefix)
  giveCellOut: heap.give(cell)
  return no
:pattern
  set at lastAt
  goto eachTail
:eachTail loop=while max=scopeBytes
  tailStart: atStart = compare.lessOrEqualInt64(at, zero)
  if atStart tailFound checkTail
:checkTail in=eachTail
  beforeTail: previous = math.subtractInt64(at, one)
  readTail: tailByte = byteAt(scope, previous)
  tailSeparator: tailIsSeparator = isSeparator(tailByte)
  if tailIsSeparator tailFound stepTail
:stepTail in=eachTail
  set at previous
  goto eachTail
:tailFound
  set headBytes at
  goto eachHead
:eachHead loop=while max=scopeBytes
  headShort: short = compare.lessOrEqualInt64(headBytes, one)
  if short headFound checkHead
:checkHead in=eachHead
  beforeHead: headPrevious = math.subtractInt64(headBytes, one)
  readHead: headByte = byteAt(scope, headPrevious)
  headSeparator: headIsSeparator = isSeparator(headByte)
  if headIsSeparator stepHead headFound
:stepHead in=eachHead
  set headBytes headPrevious
  goto eachHead
:headFound
  patternBase: patternRoot = resolve(scope, headBytes, cell)
  readPatternBase: patternRootBytes = machine.loadInt64(cell)
  patternPrefixOf: patternPrefix = asPrefix(patternRoot, patternRootBytes, cell)
  readPatternPrefix: patternPrefixBytes = machine.loadInt64(cell)
  underCheck: under = startsWith(real, realBytes, patternPrefix, patternPrefixBytes)
  if under firstName patternOutside
:firstName
  findFirst: first = machine.offset(real, patternPrefixBytes)
  restOf: restBytes = math.subtractInt64(realBytes, patternPrefixBytes)
  set length zero
  goto eachName
:eachName loop=while max=restBytes
  nameEnd: atNameEnd = compare.greaterOrEqualInt64(length, restBytes)
  if atNameEnd compareName checkName
:checkName in=eachName
  readName: nameByte = byteAt(first, length)
  nameSeparator: nameIsSeparator = compare.equalByte(nameByte, backslash)
  if nameIsSeparator compareName stepName
:stepName in=eachName
  nextName: afterName = math.addInt64(length, one)
  set length afterName
  goto eachName
:compareName
  findTailText: tailText = machine.offset(scope, at)
  tailLength: tailBytes = math.subtractInt64(lastAt, at)
  wantOf: want = wide.lowercase(tailText, tailBytes, cell)
  readWant: wantBytes = machine.loadInt64(cell)
  fitsCheck: fitsName = compare.lessOrEqualInt64(wantBytes, length)
  if fitsName compareWant patternGiveWant
:compareWant
  matchCheck: matches = startsWith(first, length, want, wantBytes)
  giveWant: heap.give(want)
  if matches patternInside patternOutside
:patternGiveWant
  giveWantOut: heap.give(want)
  goto patternOutside
:patternInside
  giveRealPattern: heap.give(real)
  giveRootPattern: heap.give(patternRoot)
  givePrefixPattern: heap.give(patternPrefix)
  giveCellPattern: heap.give(cell)
  return isPattern
:patternOutside
  giveRealNo: heap.give(real)
  giveRootNo: heap.give(patternRoot)
  givePrefixNo: heap.give(patternPrefix)
  giveCellNo: heap.give(cell)
  return no

## ---------------------------------------------------------------- capability scopes at run time (D-38)

op resourceOf "The scoped resource a scope line names after its first space: 1 net.tcp, 2 net.outbound, 3 fs.files, 4 process.programs, 5 ffi.libraries, 6 ffi.symbols; 0 when it is not a header"
  input line machine.Address copied
  input bytes Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let none0 Int64 0
  let tcp1 Int64 1
  let outbound2 Int64 2
  let files3 Int64 3
  let programs4 Int64 4
  let libraries5 Int64 5
  let symbols6 Int64 6
  let space Byte 32
  let tcp String "net.tcp"
  let outbound String "net.outbound"
  let fsFiles String "fs.files"
  let programs String "process.programs"
  let libraries String "ffi.libraries"
  let symbols String "ffi.symbols"
:begin
  goto eachByte
:eachByte loop=while max=bytes
  endCheck: atEnd = compare.greaterOrEqualInt64(at, bytes)
  if atEnd notHeader checkByte
:checkByte in=eachByte
  readByte: byte = byteAt(line, at)
  spaceCheck: isSpace = compare.equalByte(byte, space)
  if isSpace found advance
:advance in=eachByte
  nextByte: after = math.addInt64(at, one=1)
  set at after
  goto eachByte
:notHeader
  return none0
:found
  startOf: start = math.addInt64(at, one)
  findName: name = machine.offset(line, start)
  nameLength: nameBytes = math.subtractInt64(bytes, start)
  findTcp: tcpAt = machine.addressOfString(tcp)
  tcpLength: tcpBytes = string.byteLength(tcp)
  tcpCheck: isTcp = memory.bytesEqual(name, nameBytes, tcpAt, tcpBytes)
  tcpFound: tcpHit = compare.notEqualInt32(isTcp, zero32=0)
  if tcpHit giveTcp outboundCheck
:giveTcp
  return tcp1
:outboundCheck
  findOutbound: outboundAt = machine.addressOfString(outbound)
  outboundLength: outboundBytes = string.byteLength(outbound)
  checkOutbound: isOutbound = memory.bytesEqual(name, nameBytes, outboundAt, outboundBytes)
  outboundFound: outboundHit = compare.notEqualInt32(isOutbound, zero32)
  if outboundHit giveOutbound filesCheck
:giveOutbound
  return outbound2
:filesCheck
  findFiles: filesAt = machine.addressOfString(fsFiles)
  filesLength: filesBytes = string.byteLength(fsFiles)
  checkFiles: isFiles = memory.bytesEqual(name, nameBytes, filesAt, filesBytes)
  filesFound: filesHit = compare.notEqualInt32(isFiles, zero32)
  if filesHit giveFiles programsCheck
:giveFiles
  return files3
:programsCheck
  findPrograms: programsAt = machine.addressOfString(programs)
  programsLength: programsBytes = string.byteLength(programs)
  checkPrograms: isPrograms = memory.bytesEqual(name, nameBytes, programsAt, programsBytes)
  programsFound: programsHit = compare.notEqualInt32(isPrograms, zero32)
  if programsHit givePrograms librariesCheck
:givePrograms
  return programs4
:librariesCheck
  findLibraries: librariesAt = machine.addressOfString(libraries)
  librariesLength: librariesBytes = string.byteLength(libraries)
  checkLibraries: isLibraries = memory.bytesEqual(name, nameBytes, librariesAt, librariesBytes)
  librariesFound: librariesHit = compare.notEqualInt32(isLibraries, zero32)
  if librariesHit giveLibraries symbolsCheck
:giveLibraries
  return libraries5
:symbolsCheck
  findSymbols: symbolsAt = machine.addressOfString(symbols)
  symbolsLength: symbolsBytes = string.byteLength(symbols)
  checkSymbols: isSymbols = memory.bytesEqual(name, nameBytes, symbolsAt, symbolsBytes)
  symbolsFound: symbolsHit = compare.notEqualInt32(isSymbols, zero32)
  if symbolsHit giveSymbols notHeaderEither
:giveSymbols
  return symbols6
:notHeaderEither
  return none0

op addRepr "Add a text to a builder as Python's repr writes a str: in single quotes (double when it holds a single and no double), with \\\\, the quote, \\n, \\r, \\t, and other control bytes escaped"
  input builder machine.Address copied
  input text machine.Address copied
  input bytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let quote Byte 39 mut
  let single Byte 39
  let double Byte 34
  let backslash Byte 92
  let newline Byte 10
  let carriage Byte 13
  let tab Byte 9
  let hexDigits String "0123456789abcdef"
:begin
  findSingle: singleAt = machine.addressOfString(singleText="'")
  findDouble: doubleAt = machine.addressOfString(doubleText="\"")
  singleSearch: singleFound = memory.findBytes(text, bytes, singleAt, one=1)
  doubleSearch: doubleFound = memory.findBytes(text, bytes, doubleAt, one)
  hasSingle: holdsSingle = compare.greaterOrEqualInt64(singleFound, zero=0)
  hasDouble: holdsDouble = compare.greaterOrEqualInt64(doubleFound, zero)
  noDouble: lacksDouble = logic.not(holdsDouble)
  useDoubleCheck: useDouble = logic.and(holdsSingle, lacksDouble)
  if useDouble doubleQuote open
:doubleQuote
  set quote double
  goto open
:open
  addOpen: wide.builderAddByte(builder, quote)
  goto eachByte
:eachByte loop=while max=bytes
  doneCheck: done = compare.greaterOrEqualInt64(at, bytes)
  if done close readByte
:readByte in=eachByte
  readIt: byte = byteAt(text, at)
  backslashCheck: isBackslash = compare.equalByte(byte, backslash)
  quoteCheck: isQuote = compare.equalByte(byte, quote)
  escapeCheck: escapeSelf = logic.or(isBackslash, isQuote)
  if escapeSelf escapeIt newlineCheck
:escapeIt in=eachByte
  addEscape: wide.builderAddByte(builder, backslash)
  addSelf: wide.builderAddByte(builder, byte)
  goto advance
:newlineCheck in=eachByte
  checkNewline: isNewline = compare.equalByte(byte, newline)
  if isNewline addNewline carriageCheck
:addNewline in=eachByte
  addN: wide.builderAddByte(builder, backslash)
  addLetterN: wide.builderAddByte(builder, letterN=110)
  goto advance
:carriageCheck in=eachByte
  checkCarriage: isCarriage = compare.equalByte(byte, carriage)
  if isCarriage addCarriage tabCheck
:addCarriage in=eachByte
  addR: wide.builderAddByte(builder, backslash)
  addLetterR: wide.builderAddByte(builder, letterR=114)
  goto advance
:tabCheck in=eachByte
  checkTab: isTab = compare.equalByte(byte, tab)
  if isTab addTab controlCheck
:addTab in=eachByte
  addT: wide.builderAddByte(builder, backslash)
  addLetterT: wide.builderAddByte(builder, letterT=116)
  goto advance
:controlCheck in=eachByte
  lowCheck: isLow = compare.lessThanByte(byte, spaceByte=32)
  deleteCheck: isDelete = compare.equalByte(byte, deleteByte=127)
  controlEither: isControl = logic.or(isLow, isDelete)
  if isControl addHex addPlain
:addHex in=eachByte
  addX: wide.builderAddByte(builder, backslash)
  addLetterX: wide.builderAddByte(builder, letterX=120)
  widenByte: value = convert.byteToInt64(byte)
  highOf: high = bits.shiftRightInt64(value, four=4)
  lowOf: low = bits.andInt64(value, fifteen=15)
  findDigits: digitsText = machine.addressOfString(hexDigits)
  findHigh: highAt = machine.offset(digitsText, high)
  addHigh: wide.builderAdd(builder, highAt, one)
  findLow: lowAt = machine.offset(digitsText, low)
  addLow: wide.builderAdd(builder, lowAt, one)
  goto advance
:addPlain in=eachByte
  addByte: wide.builderAddByte(builder, byte)
  goto advance
:advance in=eachByte
  nextByte: after = math.addInt64(at, one)
  set at after
  goto eachByte
:close
  addClose: wide.builderAddByte(builder, quote)
  return

op checkScope "host._check_scope: a scoped argument must fall inside a scope of a capability the operation uses for the call's effect; otherwise trap, naming the target, the value, and every scope. The scope text is lines, each `<verb> <resource>` header followed by that resource's scopes"
  invariant checksScopes "A value inside one of the listed scopes passes; any other traps naming the target, the value, and the scopes in Python's repr"
  input target String borrowed
  input value machine.Address copied
  input valueBytes Int64 copied
  input scopes machine.Address copied
  input scopesBytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let start Int64 0 mut
  let resource Int64 0 mut
  let allowed Bool false mut
  let listed Int64 0 mut
  let yes Bool true
  let newline Byte 10
  let separator String ", "
:begin
  makeListed: list = wide.builderNew()
  goto eachLine
:eachLine loop=while max=scopesBytes
  set at start
  goto findEnd
:findEnd in=eachLine
  goto eachByte
:eachByte loop=while max=scopesBytes in=eachLine
  endCheck: atEnd = compare.greaterOrEqualInt64(at, scopesBytes)
  if atEnd lineFound checkByte
:checkByte in=eachByte
  readByte: byte = byteAt(scopes, at)
  newlineCheck: isNewline = compare.equalByte(byte, newline)
  if isNewline lineFound advance
:advance in=eachByte
  nextByte: after = math.addInt64(at, one=1)
  set at after
  goto eachByte
:lineFound in=eachLine
  findLine: line = machine.offset(scopes, start)
  lineLength: lineBytes = math.subtractInt64(at, start)
  headerOf: header = resourceOf(line, lineBytes)
  headerCheck: isHeader = compare.greaterThanInt64(header, zero=0)
  if isHeader newResource scopeLine
:newResource in=eachLine
  set resource header
  goto nextLine
:scopeLine in=eachLine
  alreadyCheck: already = logic.not(allowed)
  if already testLine listLine
:testLine in=eachLine
  filesCheck: isFiles = compare.equalInt64(resource, three=3)
  if isFiles testPath tcpCheck
:tcpCheck in=eachLine
  checkTcp: isTcp = compare.equalInt64(resource, one=1)
  if isTcp testPort outboundCheck
:testPort in=eachLine
  portIt: portAllowed = portWithin(value, valueBytes, line, lineBytes)
  if portAllowed allow listLine
:outboundCheck in=eachLine
  checkOutbound: isOutbound = compare.equalInt64(resource, two=2)
  if isOutbound testAddress exactCheck
:testAddress in=eachLine
  addressIt: addressAllowed = addressWithin(value, valueBytes, line, lineBytes)
  if addressAllowed allow listLine
:testPath in=eachLine
  withinCheck: within = pathWithin(value, valueBytes, line, lineBytes)
  if within allow listLine
:exactCheck in=eachLine
  exactResource: exactKind = compare.greaterOrEqualInt64(resource, four=4)
  if exactKind testExact listLine
:testExact in=eachLine
  sameCheck: sameText = memory.bytesEqual(value, valueBytes, line, lineBytes)
  sameFound: same = compare.notEqualInt32(sameText, zero32=0)
  if same allow listLine
:allow in=eachLine
  set allowed yes
  goto listLine
:listLine in=eachLine
  anyListed: hasListed = compare.greaterThanInt64(listed, zero)
  if hasListed addSeparator addLine
:addSeparator in=eachLine
  findSeparator: separatorAt = machine.addressOfString(separator)
  addComma: wide.builderAdd(list, separatorAt, two=2)
  goto addLine
:addLine in=eachLine
  addIt: addRepr(list, line, lineBytes)
  moreListed: listedAfter = math.addInt64(listed, one)
  set listed listedAfter
  goto nextLine
:nextLine in=eachLine
  lastCheck: lastLine = compare.greaterOrEqualInt64(at, scopesBytes)
  if lastLine decide stepLine
:stepLine in=eachLine
  pastNewline: nextStart = math.addInt64(at, one)
  set start nextStart
  goto eachLine
:decide
  if allowed pass refuse
:pass
  readList: listText = wide.builderText(list)
  giveList: heap.give(listText)
  giveBuilder: heap.give(list)
  return
:refuse
  makeMessage: message = wide.builderNew()
  addOpen: addString(message, openText="`")
  addTarget: addString(message, target)
  addGiven: addString(message, givenText="` was given `")
  addValue: wide.builderAdd(message, value, valueBytes)
  addWhich: addString(message, whichText="`, which no capability this operation uses allows (scopes: ")
  noneListed: nothingListed = compare.equalInt64(listed, zero)
  if nothingListed addNone addListed
:addNone
  addNoneText: addString(message, noneText="none")
  goto finish
:addListed
  readListed: listedText = wide.builderText(list)
  readListedLength: listedBytes = wide.builderLength(list)
  addAll: wide.builderAdd(message, listedText, listedBytes)
  goto finish
:finish
  addEnd: addString(message, endText=")")
  readMessage: messageText = wide.builderText(message)
  readMessageLength: messageBytes = wide.builderLength(message)
  writeReport: status = frames.report(messageText, messageBytes)
  exit: endProcess(trapCode=70)
  return

op portWithin "Whether a port's decimal text is a `net.tcp` scope's port, as host.py compares them: the scope's text after its last colon (all of it when it has none)"
  input value machine.Address copied
  input valueBytes Int64 copied
  input scope machine.Address copied
  input scopeBytes Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let start Int64 0 mut
  let colon Byte 58
:begin
  set at scopeBytes
  goto eachByte
:eachByte loop=while max=scopeBytes
  startCheck: atStart = compare.lessOrEqualInt64(at, zero=0)
  if atStart compare readByte
:readByte in=eachByte
  lastOf: last = math.subtractInt64(at, one=1)
  readIt: byte = byteAt(scope, last)
  colonCheck: isColon = compare.equalByte(byte, colon)
  if isColon found back
:back in=eachByte
  set at last
  goto eachByte
:found
  set start at
  goto compare
:compare
  findPort: port = machine.offset(scope, start)
  portLength: portBytes = math.subtractInt64(scopeBytes, start)
  sameIt: same = memory.bytesEqual(value, valueBytes, port, portBytes)
  sameCheck: equal = compare.notEqualInt32(same, zero32=0)
  return equal

op addressWithin "Whether an address falls inside a `net.outbound` scope, as semantics.address_within decides: the same text, or the scope's text then a colon or slash (or the scope ends with one)"
  input value machine.Address copied
  input valueBytes Int64 copied
  input scope machine.Address copied
  input scopeBytes Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let yes Bool true
  let no Bool false
  let colon Byte 58
  let slash Byte 47
:begin
  shortCheck: short = compare.lessThanInt64(valueBytes, scopeBytes)
  if short refuse prefix
:prefix
  sameIt: same = memory.bytesEqual(value, scopeBytes, scope, scopeBytes)
  sameCheck: starts = compare.notEqualInt32(same, zero32=0)
  if starts lengthCheck refuse
:lengthCheck
  equalCheck: equal = compare.equalInt64(valueBytes, scopeBytes)
  if equal allow scopeEnd
:scopeEnd
  emptyCheck: emptyScope = compare.equalInt64(scopeBytes, zero=0)
  if emptyScope nextByte lastByte
:lastByte
  lastOf: last = math.subtractInt64(scopeBytes, one=1)
  readLast: ending = byteAt(scope, last)
  colonCheck: endsColon = compare.equalByte(ending, colon)
  slashCheck: endsSlash = compare.equalByte(ending, slash)
  endCheck: endsOpen = logic.or(endsColon, endsSlash)
  if endsOpen allow nextByte
:nextByte
  readNext: following = byteAt(value, scopeBytes)
  nextColon: isColon = compare.equalByte(following, colon)
  nextSlash: isSlash = compare.equalByte(following, slash)
  nextCheck: separated = logic.or(isColon, isSlash)
  if separated allow refuse
:allow
  return yes
:refuse
  return no

op addString "Add a text to a builder"
  input builder machine.Address copied
  input text String borrowed
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findText: textAt2 = machine.addressOfString(text)
  textLength: bytes = string.byteLength(text)
  addIt: wide.builderAdd(builder, textAt2, bytes)
  return

## ---------------------------------------------------------------- claims (D-52, D-109)

op claimAt "The address of a claim by its position in the table"
  input position Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findTable: tableSlot = stateAt(claimsAt)
  readTable: table = machine.loadAddress(tableSlot)
  offsetOf: offset = math.multiplyInt64(position, claimBytes)
  locateClaim: located = machine.offset(table, offset)
  return located

op findClaim "The position of the claim of a key, or -1 when no handle holds it"
  input key machine.Address copied
  input bytes Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let missingPosition Int64 -1
:begin
  findCount: countSlot = stateAt(claimCountAt)
  readCount: count = machine.loadInt64(countSlot)
  goto eachClaim
:eachClaim loop=while max=count
  doneCheck: done = compare.greaterOrEqualInt64(at, count)
  if done missing compareOne
:compareOne in=eachClaim
  findOne: claimed = claimAt(at)
  readKey: claimKey = machine.loadAddress(claimed)
  readBytes: claimKeyBytes = field(claimed, eight=8)
  compareKeys: same = memory.bytesEqual(claimKey, claimKeyBytes, key, bytes)
  sameCheck: found = compare.notEqualInt32(same, zero32=0)
  if found give advance
:advance in=eachClaim
  nextClaim: after = math.addInt64(at, one=1)
  set at after
  goto eachClaim
:give
  return at
:missing
  return missingPosition

op claim "Claim a key for reading or writing: false (busy) when it is held for writing, or for anything when writing is asked"
  input key machine.Address copied
  input bytes Int64 copied
  input writes Int64 copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let capacity Int64 0 mut
  let position2 Int64 0 mut
  let yes Bool true
  let no Bool false
:begin
  findIt: position = findClaim(key, bytes)
  heldCheck: held = compare.greaterOrEqualInt64(position, zero=0)
  if held conflictCheck add
:conflictCheck
  existing: claimed = claimAt(position)
  readWriters: writers = field(claimed, twentyFour=24)
  writingCheck: wantsWrite = compare.notEqualInt64(writes, zero)
  writersCheck: hasWriters = compare.greaterThanInt64(writers, zero)
  conflict: refused = logic.or(wantsWrite, hasWriters)
  if refused giveBusy existingClaim
:giveBusy
  return no
:add
  findCount: countSlot = stateAt(claimCountAt)
  readCount: count = machine.loadInt64(countSlot)
  findCapacity: capacitySlot = stateAt(claimCapacityAt)
  readCapacity: room = machine.loadInt64(capacitySlot)
  roomCheck: fits = compare.lessThanInt64(count, room)
  if fits place grow
:grow
  doubleIt: doubled = math.multiplyInt64(room, two=2)
  moreRoom: grown = math.addInt64(doubled, eight=8)
  set capacity grown
  findTable: tableSlot = stateAt(claimsAt)
  readTable: table = machine.loadAddress(tableSlot)
  sizeOf: size = math.multiplyInt64(capacity, claimBytes)
  growTable: bigger = heap.resize(table, size)
  storeTable: machine.storeAddress(tableSlot, bigger)
  storeCapacity: machine.storeInt64(capacitySlot, capacity)
  goto place
:place
  newClaim: fresh = claimAt(count)
  copyKey: keyCopy = copyBytes(key, bytes)
  storeKey: machine.storeAddress(fresh, keyCopy)
  storeBytes: setField(fresh, eight, bytes)
  storeReaders: setField(fresh, sixteen=16, zero)
  storeWriters: setField(fresh, twentyFour, zero)
  oneMore: moreCount = math.addInt64(count, one=1)
  storeCount: machine.storeInt64(countSlot, moreCount)
  set position2 count
  goto countIt
:existingClaim
  set position2 position
  goto countIt
:countIt
  thisClaim: target = claimAt(position2)
  writeCheck: forWriting = compare.notEqualInt64(writes, zero)
  if forWriting addWriter addReader
:addWriter
  readW: w = field(target, twentyFour)
  moreW: w2 = math.addInt64(w, one)
  storeW: setField(target, twentyFour, w2)
  return yes
:addReader
  readR: r = field(target, sixteen)
  moreR: r2 = math.addInt64(r, one)
  storeR: setField(target, sixteen, r2)
  return yes

op unclaim "Give back a claim of a key for reading or writing; the claim goes when nothing holds it. No key (the address 0) is nothing to give back"
  input key machine.Address copied
  input bytes Int64 copied
  input writes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere: anywhere = machine.zero()
  noKeyCheck: noKey = machine.equal(key, anywhere)
  if noKey done findIt
:findIt
  findPosition: position = findClaim(key, bytes)
  missingCheck: missing = compare.lessThanInt64(position, zero=0)
  if missing done drop
:drop
  claimed: target = claimAt(position)
  writeCheck: forWriting = compare.notEqualInt64(writes, zero)
  if forWriting dropWriter dropReader
:dropWriter
  readW: w = field(target, twentyFour=24)
  lessW: w2 = math.subtractInt64(w, one=1)
  storeW: setField(target, twentyFour, w2)
  goto emptyCheck
:dropReader
  readR: r = field(target, sixteen=16)
  lessR: r2 = math.subtractInt64(r, one)
  storeR: setField(target, sixteen, r2)
  goto emptyCheck
:emptyCheck
  readReaders: readers = field(target, sixteen)
  readWriters: writers = field(target, twentyFour)
  sumOf: holders = math.addInt64(readers, writers)
  unheldCheck: unheld = compare.lessOrEqualInt64(holders, zero)
  if unheld remove done
:remove
  readKey: claimKey = machine.loadAddress(target)
  giveKey: heap.give(claimKey)
  findCount: countSlot = stateAt(claimCountAt)
  readCount: count = machine.loadInt64(countSlot)
  lastOf: last = math.subtractInt64(count, one)
  lastClaim: lastAt = claimAt(last)
  moveLast: machine.copy(target, lastAt, claimBytes)
  storeCount: machine.storeInt64(countSlot, last)
  goto done
:done
  return

op unsignedAt "A DWORD of a block at an offset, as a whole number from 0"
  input block machine.Address copied
  input offset Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findIt: place = machine.offset(block, offset)
  readIt: value = machine.loadInt32(place)
  widenIt: wide64 = convert.int32ToInt64(value)
  maskIt: unsigned = bits.andInt64(wide64, mask=4294967295)
  return unsigned

op addNumber "Add a whole number in decimal to a builder"
  input builder machine.Address copied
  input value Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findDigits: digits = stateAt(digitsAt)
  format: length = numbers.formatDecimal(value, digits)
  addIt: wide.builderAdd(builder, digits, length)
  return

op identityKey "D-109: the file itself, `#<volume>:<index high>:<index low>`, in a new heap block (its length stored at an address); the address 0 when the system gives no file index"
  input handle machine.Address copied
  input lengthAt machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere: anywhere = machine.zero()
  osCheck: onLinux = system.linux()
  if onLinux linuxIdentity windowsIdentity
:linuxIdentity
  descriptorOf: fd = machine.toInt64(handle)
  findStatus: status = stateAt(statAt)
  statIt: statResult = system.fstat(fd, status)
  statFailed: noStatus = kernel.failed(statResult)
  if noStatus giveNothing linuxKey
:linuxKey
  keyOf: linuxKeyText = statusIdentity(status, lengthAt)
  return linuxKeyText
:windowsIdentity
  findInfo: info = stateAt(infoAt)
  readInfo: got = system.getFileInformationByHandle(handle, info)
  failedCheck: notRead = compare.equalInt32(got, zero32=0)
  if notRead giveNothing readIndex
:giveNothing
  return anywhere
:readIndex
  volume: volumeNumber = unsignedAt(info, twentyEight=28)
  indexHigh: high = unsignedAt(info, fortyFour=44)
  indexLow: low = unsignedAt(info, fortyEight=48)
  bothZero: either = bits.orInt64(high, low)
  zeroCheck: noIndex = compare.equalInt64(either, zero=0)
  if noIndex giveNothing format
:format
  makeKey: builder = wide.builderNew()
  addHash: wide.builderAddByte(builder, hash=35)
  addVolume: addNumber(builder, volumeNumber)
  addColon: wide.builderAddByte(builder, colon=58)
  addHigh: addNumber(builder, high)
  addColonAgain: wide.builderAddByte(builder, colon)
  addLow: addNumber(builder, low)
  readKey: key = wide.builderText(builder)
  readLength: length = wide.builderLength(builder)
  storeLength: machine.storeInt64(lengthAt, length)
  giveBuilder: heap.give(builder)
  return key

op statusIdentity "D-109 on Linux: the file a struct stat describes, `#<st_dev>:<st_ino>` as host.py writes it, in a new heap block (its length stored at an address); the address 0 when st_ino is 0"
  input status machine.Address copied
  input lengthAt machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readDevice: device = machine.loadInt64(status)
  findInode: inodeSlot = machine.offset(status, eight=8)
  readInode: inode = machine.loadInt64(inodeSlot)
  zeroCheck: noInode = compare.equalInt64(inode, zero=0)
  if noInode giveNothing format
:giveNothing
  nowhere: anywhere = machine.zero()
  return anywhere
:format
  makeKey: builder = wide.builderNew()
  addHash: wide.builderAddByte(builder, hash=35)
  addDevice: addNumber(builder, device)
  addColon: wide.builderAddByte(builder, colon=58)
  addInode: addNumber(builder, inode)
  readKey: key = wide.builderText(builder)
  readLength: length = wide.builderLength(builder)
  storeLength: machine.storeInt64(lengthAt, length)
  giveBuilder: heap.give(builder)
  return key

op isRegularFile "Whether a path names something that is not a directory (on Linux, a regular file, as os.path.isfile has it)"
  input path machine.Address copied
  input bytes Int64 copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let no Bool false
  let yes Bool true
:begin
  osCheck: onLinux = system.linux()
  if onLinux linuxCheck windowsCheck
:linuxCheck
  statIt: statResult = statPath(path, bytes, yes)
  statFailed: missing = kernel.failed(statResult)
  if missing giveNo modeCheck
:giveNo
  return no
:modeCheck
  findStatus: status = stateAt(statAt)
  readMode: mode = linuxMode(status)
  regularMode: isRegular = compare.equalInt64(mode, typeRegular)
  return isRegular
:windowsCheck
  wideName: name = wide.widen(path, bytes)
  readAttributes: attributes = system.getFileAttributesW(name)
  giveName: heap.give(name)
  invalidCheck: invalid = compare.equalInt32(attributes, minusOne32=-1)
  widenAttributes: value = convert.int32ToInt64(attributes)
  directoryBit: directory = bits.andInt64(value, sixteen=16)
  directoryCheck: isDirectory = compare.notEqualInt64(directory, zero=0)
  eitherCheck: notFile = logic.or(invalid, isDirectory)
  regularCheck: regular = logic.not(notFile)
  return regular

## ---------------------------------------------------------------- reading and writing

op readUpTo "Read up to a number of bytes from a handle, as a buffered read does (until that many or the end), into a builder; the system's error code (0 for none) is stored at an address"
  input handle machine.Address copied
  input limit Int64 copied
  input errorAt machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let length Int64 0 mut
  let want Int64 0 mut
:begin
  makeBuilder: builder = wide.builderNew()
  takeChunk: buffer = heap.take(chunk)
  storeNoError: machine.storeInt64(errorAt, zero=0)
  findCounted: counted = stateAt(countedAt)
  nowhere: anywhere = machine.zero()
  goto eachRead
:eachRead loop=while max=limit
  leftOf: left = math.subtractInt64(limit, length)
  doneCheck: done = compare.lessOrEqualInt64(left, zero)
  if done finish sizeIt
:sizeIt in=eachRead
  set want left
  bigCheck: big = compare.greaterThanInt64(left, chunk)
  if big useChunk readSome
:useChunk in=eachRead
  set want chunk
  goto readSome
:readSome in=eachRead
  osCheck: onLinux = system.linux()
  if onLinux readLinux readWindows
:readLinux in=eachRead
  descriptorOf: fd = machine.toInt64(handle)
  readFd: gotLinux = system.read(fd, buffer, want)
  linuxFailed: refusedLinux = kernel.failed(gotLinux)
  if refusedLinux linuxReadFailed linuxCount
:linuxReadFailed
  errnoOf: readErrno = kernel.errnoOf(gotLinux)
  storeErrno: machine.storeInt64(errorAt, readErrno)
  goto finish
:linuxCount in=eachRead
  linuxEnd: atLinuxEnd = compare.equalInt64(gotLinux, zero)
  if atLinuxEnd finish keepLinux
:keepLinux in=eachRead
  addLinux: wide.builderAdd(builder, buffer, gotLinux)
  moreLinux: afterLinux = math.addInt64(length, gotLinux)
  set length afterLinux
  goto eachRead
:readWindows in=eachRead
  narrowWant: want32 = convert.int64ToInt32(want)
  readIt: ok = system.readFile(handle, buffer, want32, counted, anywhere)
  failedCheck: refused = compare.equalInt32(ok, zero32=0)
  if refused readFailed countIt
:readFailed
  readError: code = system.getLastError()
  widenError: codeValue = convert.int32ToInt64(code)
  brokenCheck: broken = compare.equalInt64(codeValue, oneOhNine=109)
  if broken finish storeError
:storeError
  storeCode: machine.storeInt64(errorAt, codeValue)
  goto finish
:countIt in=eachRead
  readCount: got32 = machine.loadInt32(counted)
  widenCount: got = convert.int32ToInt64(got32)
  endCheck: atEnd = compare.equalInt64(got, zero)
  if atEnd finish keep
:keep in=eachRead
  addIt: wide.builderAdd(builder, buffer, got)
  moreLength: after = math.addInt64(length, got)
  set length after
  goto eachRead
:finish
  giveChunk: heap.give(buffer)
  return builder

op seekTo "Move a handle's position: method 0 from the start, 2 from the end; gives whether it moved"
  input handle machine.Address copied
  input distance Int64 copied
  input method Int32 copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  osCheck: onLinux = system.linux()
  if onLinux seekLinux seekWindows
:seekLinux
  descriptorOf: fd = machine.toInt64(handle)
  widenMethod: whence = convert.int32ToInt64(method)
  seekIt: position = system.lseek(fd, distance, whence)
  seekFailed: refused = kernel.failed(position)
  if refused keepIt giveMoved
:keepIt
  keepCode: keepErrno(position)
  goto giveMoved
:giveMoved
  movedLinux: linuxOk = logic.not(refused)
  return linuxOk
:seekWindows
  nowhere: anywhere = machine.zero()
  moveIt: moved = system.setFilePointerEx(handle, distance, anywhere, method)
  movedCheck: ok = compare.notEqualInt32(moved, zero32=0)
  return ok

op emptyFile "Empty an open file: its position to the start and its end there; gives the system's error code, 0 when it worked"
  input handle machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  toStart: moved = seekTo(handle, zero=0, fromStart=0)
  osCheck: onLinux = system.linux()
  if onLinux truncateLinux windowsEmpty
:truncateLinux
  descriptorOf: fd = machine.toInt64(handle)
  truncateIt: truncated = system.ftruncate(fd, zero)
  truncateFailed: refused = kernel.failed(truncated)
  if refused giveErrno worked
:giveErrno
  errnoOf: errno = kernel.errnoOf(truncated)
  narrowErrno: code32 = convert.int64ToInt32(errno)
  return code32
:windowsEmpty
  if moved cut failedEmpty
:cut
  cutIt: cut32 = system.setEndOfFile(handle)
  cutCheck: cutOk = compare.notEqualInt32(cut32, fromStart)
  if cutOk worked failedEmpty
:worked
  return fromStart
:failedEmpty
  readError: code = system.getLastError()
  return code

op openPath "CreateFileW of a UTF-8 path with an access, a share mode, a disposition, and flags; INVALID_HANDLE_VALUE when it fails, its error then kept for keptCode"
  input path machine.Address copied
  input bytes Int64 copied
  input access Int32 copied
  input share Int32 copied
  input disposition Int32 copied
  input flags Int32 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  osCheck: onLinux = system.linux()
  if onLinux linuxOpen windowsOpen
:linuxOpen
  linuxIt: linuxHandle = openPathLinux(path, bytes, access, disposition)
  return linuxHandle
:windowsOpen
  wideName: name = wide.widen(path, bytes)
  nowhere: anywhere = machine.zero()
  openIt: handle = system.createFileW(name, access, share, anywhere, disposition, flags, anywhere)
  readError: code = system.getLastError()
  giveName: heap.give(name)
  findCounted: counted = stateAt(countedAt)
  storeCode: machine.storeInt32(counted, code)
  return handle

op openPathLinux "openat of a path on Linux for the access and disposition openPath names (read: O_RDONLY; read and write: O_RDWR; a new file: O_WRONLY, O_CREAT, O_EXCL; at the end: O_WRONLY, O_CREAT, O_APPEND), never inherited; a directory opened for reading is EISDIR, as Python's open gives it; -1 when it fails, its errno kept"
  input path machine.Address copied
  input bytes Int64 copied
  input access Int32 copied
  input disposition Int32 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let flags Int64 0 mut
  let readWriteFlags Int64 2
  let createFlags Int64 193
  let appendFlags Int64 1089
  let eisdirResult Int64 -21
:begin
  failedValue: invalid = machine.fromInt64(minusOne=-1)
  readWriteCheck: isReadWrite = compare.equalInt32(access, genericReadWrite)
  if isReadWrite useReadWrite createCheck
:useReadWrite
  set flags readWriteFlags
  goto open
:createCheck
  newCheck: isNew = compare.equalInt32(disposition, createNew)
  if isNew useCreate appendCheck
:useCreate
  set flags createFlags
  goto open
:appendCheck
  alwaysCheck: isAlways = compare.equalInt32(disposition, openAlways)
  if isAlways useAppend open
:useAppend
  set flags appendFlags
  goto open
:open
  withClose: allFlags = bits.orInt64(flags, closeOnExec)
  copyPath: name = cPath(path, bytes)
  openIt: fd = system.openat(atWorkingDirectory, name, allFlags, readWriteAll=438)
  giveName: heap.give(name)
  openFailed: refused = kernel.failed(fd)
  if refused keepFailure statIt
:keepFailure
  keepCode: keepErrno(fd)
  return invalid
:statIt
  findStatus: status = stateAt(statAt)
  statFd: statResult = system.fstat(fd, status)
  readMode: mode = linuxMode(status)
  directoryCheck: isDirectory = compare.equalInt64(mode, typeDirectory)
  if isDirectory refuseDirectory giveFd
:refuseDirectory
  closeIt: closed = system.close(fd)
  keepDirectory: keepErrno(eisdirResult)
  return invalid
:giveFd
  handleOf: handle = machine.fromInt64(fd)
  return handle

op keptCode "The error code openPath kept (on Linux, the errno)"
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findCounted: counted = stateAt(countedAt)
  osCheck: onLinux = system.linux()
  if onLinux linuxCode windowsCode
:linuxCode
  readErrno: errno = machine.loadInt64(counted)
  narrowErrno: errno32 = convert.int64ToInt32(errno)
  return errno32
:windowsCode
  readCode: code = machine.loadInt32(counted)
  return code

op flagOf "1 for true, 0 for false"
  input value Bool copied
  output Int64
  let yesValue Int64 1
  let noValue Int64 0
:begin
  if value giveOne giveZero
:giveOne
  return yesValue
:giveZero
  return noValue

## ---------------------------------------------------------------- fs targets: open and close

op openFile "fs.openRead, openWrite, create, openAppend: claim the path, open it, claim the file's identity, and give a File handle"
  input how Int64 copied
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let writes Int64 1 mut
  let access Int32 0 mut
  let disposition Int32 0 mut
  let errno Int64 0 mut
  let ok Int32 0
  let enoentValue Int64 2
:begin
  nowhere: anywhere = machine.zero()
  readPath: path = textAt(shape, args, zero=0)
  readBytes: bytes = textBytes(shape, args, zero)
  takeCell: cell = heap.take(sixteen=16)
  findIdentityCell: identityCell = machine.offset(cell, eight=8)
  readCheck: forReading = compare.equalInt64(how, openRead)
  writeCheck: forWrite = compare.equalInt64(how, openWrite)
  if forReading reading claimPath
:reading
  set writes zero
  goto claimPath
:claimPath
  keyOf: key = resolve(path, bytes, cell)
  readKeyBytes: keyBytes = machine.loadInt64(cell)
  claimIt: claimed = claim(key, keyBytes, writes)
  if claimed modes refuseBusy
:refuseBusy
  giveKeyBusy: heap.give(key)
  giveCellBusy: heap.give(cell)
  busyStatus: status1 = slots.failWith(payload, busy, zero)
  return status1
:modes
  set access genericRead
  set disposition openExisting
  if forWrite writeMode createCheck
:writeMode
  set access genericReadWrite
  regularCheck: regular = isRegularFile(path, bytes)
  if regular open noFile
:noFile
  set errno enoentValue
  goto failedOpen
:createCheck
  checkCreate: forCreate = compare.equalInt64(how, openCreate)
  if forCreate createMode appendCheck
:createMode
  set access genericWrite
  set disposition createNew
  goto open
:appendCheck
  checkAppend: forAppend = compare.equalInt64(how, openAppend)
  if forAppend appendMode open
:appendMode
  set access genericWrite
  set disposition openAlways
  goto open
:open
  openIt: handle = openPath(path, bytes, access, shareReadWrite, disposition, normalFile)
  invalidCheck: invalid = invalidHandle(handle)
  if invalid openRefused identity
:openRefused
  readCode: code = keptCode()
  mapCode: mapped = winErrno(code)
  set errno mapped
  goto failedOpen
:identity
  identityOf: ident = identityKey(handle, identityCell)
  noIdentCheck: noIdent = machine.equal(ident, anywhere)
  if noIdent noIdentity claimIdentity
:noIdentity
  storeNoIdent: machine.storeInt64(identityCell, zero)
  goto emptyCheck
:claimIdentity
  readIdentBytes: identBytes = machine.loadInt64(identityCell)
  claimIdent: identClaimed = claim(ident, identBytes, writes)
  if identClaimed emptyCheck identityBusy
:identityBusy
  closeBusy: closedBusy = closeFile(handle)
  unclaimBusy: unclaim(key, keyBytes, writes)
  giveKeyTaken: heap.give(key)
  giveIdentTaken: heap.give(ident)
  giveCellTaken: heap.give(cell)
  takenStatus: status2 = slots.failWith(payload, busy, zero)
  return status2
:emptyCheck
  if forWrite empty keepFile
:empty
  emptied: emptyCode = emptyFile(handle)
  emptyFailed: notEmptied = compare.notEqualInt32(emptyCode, zero32=0)
  if notEmptied emptyRefused keepFile
:emptyRefused
  mapEmpty: emptyErrno = winErrno(emptyCode)
  set errno emptyErrno
  closeEmpty: closedEmpty = closeFile(handle)
  readKeptBytes: keptBytes = machine.loadInt64(identityCell)
  unclaimIdent: unclaim(ident, keptBytes, writes)
  giveIdentEmpty: heap.give(ident)
  goto failedOpen
:failedOpen
  unclaimKey: unclaim(key, keyBytes, writes)
  giveKey: heap.give(key)
  giveCell: heap.give(cell)
  failIt: status3 = fileError(payload, errno)
  return status3
:keepFile
  takeFile: file = heap.take(fileBytes)
  storeHandle: setLink(file, zero, handle)
  storeKey: setLink(file, eight, key)
  storeKeyBytes: setField(file, sixteen, keyBytes)
  storeIdent: setLink(file, twentyFour=24, ident)
  readFinalIdentBytes: finalIdentBytes = machine.loadInt64(identityCell)
  storeIdentBytes: setField(file, thirtyTwo=32, finalIdentBytes)
  storeWrites: setField(file, forty=40, writes)
  readableCheck: readable = logic.or(forReading, forWrite)
  readableValue: readableFlag = flagOf(readable)
  storeReadable: setField(file, fortyEight=48, readableFlag)
  storeWritable: setField(file, fiftySix=56, writes)
  appendFlagCheck: appends = compare.equalInt64(how, openAppend)
  appendValue: appendFlag = flagOf(appends)
  storeAppend: setField(file, sixtyFour=64, appendFlag)
  giveCellKept: heap.give(cell)
  makeHandle: fileHandle = handles.newHandle(kindFile, file, anywhere)
  holdIt: frames.holdResource(one=1, handle)
  storeResult: machine.storeInt64(results, fileHandle)
  return ok

op fsOpenRead "fs.openRead: open a file for reading"
  invariant opensForReading "Gives a File handle that reads, or busy while the file is open for writing, or the error"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  openIt: status = openFile(openRead, shape, args, results, payload)
  return status

op fsOpenWrite "fs.openWrite: open an existing file for reading and writing, emptied"
  invariant opensForWriting "Gives a File handle that reads and writes an emptied file, or busy while the file is open, or notFound"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  openIt: status = openFile(openWrite, shape, args, results, payload)
  return status

op fsCreate "fs.create: create a new file for writing"
  invariant createsFile "Gives a File handle of a new empty file, or exists when it is there"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  openIt: status = openFile(openCreate, shape, args, results, payload)
  return status

op fsOpenAppend "fs.openAppend: open a file for writing at its end, made if it is missing"
  invariant opensForAppending "Gives a File handle whose writes go to the end"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  openIt: status = openFile(openAppend, shape, args, results, payload)
  return status

op fsClose "fs.close: give back the file's claims and close it"
  invariant closesFile "The handle is closed and the file's claims given back"
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
  readHandle: fileHandle = slots.argOf(shape, args, zero=0)
  findFile: file = handles.objectOf(fileHandle, kindFile)
  readOs: handle = link(file, zero)
  readKey: key = link(file, eight=8)
  readKeyBytes: keyBytes = field(file, sixteen=16)
  readIdent: ident = link(file, twentyFour=24)
  readIdentBytes: identBytes = field(file, thirtyTwo=32)
  readWrites: writes = field(file, forty=40)
  dropIt: handles.drop(fileHandle)
  unclaimKey: unclaim(key, keyBytes, writes)
  unclaimIdent: unclaim(ident, identBytes, writes)
  giveKey: heap.give(key)
  giveIdent: heap.give(ident)
  giveFile: heap.give(file)
  letGo: frames.letGoResource(handle)
  closeIt: closed = closeFile(handle)
  closedCheck: refused = compare.equalInt32(closed, zero32=0)
  if refused failed2 done
:failed2
  status: closeStatus = lastFileError(payload)
  return closeStatus
:done
  return ok

## ---------------------------------------------------------------- fs targets: read and write

op fsRead "fs.read: up to a number of bytes from where the file is (fewer at its end), into a region; a file not open for reading is failed 1"
  invariant readsFile "Gives the next bytes of the file, as many as asked or to its end"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let limit Int64 0 mut
  let ok Int32 0
:begin
  readHandle: fileHandle = slots.argOf(shape, args, zero=0)
  findFile: file = handles.objectOf(fileHandle, kindFile)
  readReadable: readable = field(file, fortyEight=48)
  readableCheck: canRead = compare.notEqualInt64(readable, zero)
  if canRead read notReadable
:notReadable
  refuse: status1 = slots.failWith(payload, failed, one=1)
  return status1
:read
  readLimit: asked = slots.argOf(shape, args, two=2)
  positiveCheck: positive = compare.greaterThanInt64(asked, zero)
  if positive useAsked readIt
:useAsked
  set limit asked
  goto readIt
:readIt
  readOs: handle = link(file, zero)
  takeCell: errorAt = heap.take(eight=8)
  readAll: builder = readUpTo(handle, limit, errorAt)
  readError: code = machine.loadInt64(errorAt)
  giveCell: heap.give(errorAt)
  readText: data = wide.builderText(builder)
  readLength: length = wide.builderLength(builder)
  errorCheck: hasError = compare.notEqualInt64(code, zero)
  if hasError readFailed put
:readFailed
  giveData: heap.give(data)
  giveBuilder: heap.give(builder)
  narrowCode: code32 = convert.int64ToInt32(code)
  mapIt: errno = winErrno(code32)
  status: status2 = fileError(payload, errno)
  return status2
:put
  readRegion: region = slots.addressArg(shape, args, one)
  putIt: slots.putText(region, data, length, results)
  giveDataPut: heap.give(data)
  giveBuilderPut: heap.give(builder)
  return ok

op fsWrite "fs.write: write bytes where the file is (at its end for an appending file); a file not open for writing is failed 1"
  invariant writesFile "The bytes are written, all of them"
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
  readHandle: fileHandle = slots.argOf(shape, args, zero=0)
  findFile: file = handles.objectOf(fileHandle, kindFile)
  readWritable: writable = field(file, fiftySix=56)
  writableCheck: canWrite = compare.notEqualInt64(writable, zero)
  if canWrite write notWritable
:notWritable
  refuse: status1 = slots.failWith(payload, failed, one=1)
  return status1
:write
  readOs: handle = link(file, zero)
  readAppend: appends = field(file, sixtyFour=64)
  appendCheck: atEnd = compare.notEqualInt64(appends, zero)
  if atEnd toEnd writeIt
:toEnd
  moveIt: moved = seekTo(handle, zero, fromEnd=2)
  goto writeIt
:writeIt
  readData: data = textAt(shape, args, one)
  readBytes: bytes = textBytes(shape, args, one)
  writeAll: code = output.writeAll(handle, data, bytes)
  failedCheck: refused = compare.notEqualInt32(code, zero32=0)
  if refused writeFailed done
:writeFailed
  mapIt: errno = winErrno(code)
  status: status2 = fileError(payload, errno)
  return status2
:done
  return ok

op deadlineCheck "A local file read or write does not block for long, so cancellation and the deadline are checked before it starts: cancelled, timedOut, or 0"
  input deadline Int64 copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok Int32 0
:begin
  cancelCheck: isCancelled = tasks.cancelled()
  if isCancelled giveCancelled timeCheck
:giveCancelled
  cancelledStatus: status1 = slots.failWith(payload, cancelledError, zero=0)
  return status1
:timeCheck
  neverCheck: isNever = compare.equalInt64(deadline, minusOne=-1)
  if isNever fine compare
:compare
  readNow: moment = tasks.now()
  pastCheck: past = compare.greaterOrEqualInt64(moment, deadline)
  if past giveTimedOut fine
:giveTimedOut
  timedStatus: status2 = slots.failWith(payload, timedOut, zero)
  return status2
:fine
  return ok

op fsReadAll "fs.readAll: a whole file into a region, at most a number of bytes (tooLarge past it); the deadline is checked before it starts"
  invariant readsWholeFile "Gives the file's bytes, or tooLarge when it has more than the limit"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let want Int64 0 mut
  let errno Int64 0 mut
  let ok Int32 0
  let most Int64 9223372036854775807
:begin
  nowhere: anywhere = machine.zero()
  readDeadline: deadline = slots.argOf(shape, args, three=3)
  lateCheck: late = deadlineCheck(deadline, payload)
  lateStatus: isLate = compare.notEqualInt32(late, ok)
  if isLate giveLate begin2
:giveLate
  return late
:begin2
  readPath: path = textAt(shape, args, zero=0)
  readBytes: bytes = textBytes(shape, args, zero)
  readLimit: limit = slots.argOf(shape, args, two=2)
  takeCell: cell = heap.take(sixteen=16)
  findIdentityCell: identityCell = machine.offset(cell, eight=8)
  keyOf: key = resolve(path, bytes, cell)
  readKeyBytes: keyBytes = machine.loadInt64(cell)
  claimIt: claimed = claim(key, keyBytes, zero)
  if claimed open refuseBusy
:refuseBusy
  giveKeyBusy: heap.give(key)
  giveCellBusy: heap.give(cell)
  busyStatus: status1 = slots.failWith(payload, busy, zero)
  return status1
:open
  openIt: handle = openPath(path, bytes, genericRead, shareReadWrite, openExisting, normalFile)
  invalidCheck: invalid = invalidHandle(handle)
  if invalid openRefused identity
:openRefused
  readCode: code = keptCode()
  mapCode: mapped = winErrno(code)
  set errno mapped
  unclaimOpen: unclaim(key, keyBytes, zero)
  giveKeyOpen: heap.give(key)
  giveCellOpen: heap.give(cell)
  openStatus: status2 = fileError(payload, errno)
  return status2
:identity
  identityOf: ident = identityKey(handle, identityCell)
  noIdentCheck: noIdent = machine.equal(ident, anywhere)
  if noIdent noIdentity claimIdentity
:noIdentity
  storeNoIdent: machine.storeInt64(identityCell, zero)
  goto sizeLimit
:claimIdentity
  readIdentBytes: identBytes = machine.loadInt64(identityCell)
  claimIdent: identClaimed = claim(ident, identBytes, zero)
  if identClaimed sizeLimit identityBusy
:identityBusy
  closeBusy: closedBusy = closeFile(handle)
  unclaimBusy: unclaim(key, keyBytes, zero)
  giveKeyTaken: heap.give(key)
  giveIdentTaken: heap.give(ident)
  giveCellTaken: heap.give(cell)
  takenStatus: status3 = slots.failWith(payload, busy, zero)
  return status3
:sizeLimit
  negativeCheck: negative = compare.lessThanInt64(limit, zero)
  if negative readIt topCheck
:topCheck
  atTop: isMost = compare.equalInt64(limit, most)
  if isMost useMost oneMore
:useMost
  set want most
  goto readIt
:oneMore
  plusOne: past = math.addInt64(limit, one=1)
  set want past
  goto readIt
:readIt
  takeError: errorAt = heap.take(eight=8)
  readAll: builder = readUpTo(handle, want, errorAt)
  readError: errorCode = machine.loadInt64(errorAt)
  giveErrorCell: heap.give(errorAt)
  closeIt: closed = closeFile(handle)
  unclaimKey: unclaim(key, keyBytes, zero)
  readFinalIdentBytes: finalIdentBytes = machine.loadInt64(identityCell)
  unclaimIdent: unclaim(ident, finalIdentBytes, zero)
  giveKey: heap.give(key)
  giveIdent: heap.give(ident)
  giveCell: heap.give(cell)
  readText: data = wide.builderText(builder)
  readLength: length = wide.builderLength(builder)
  errorCheck: hasError = compare.notEqualInt64(errorCode, zero)
  if hasError readFailed sizeCheck
:readFailed
  giveDataFailed: heap.give(data)
  giveBuilderFailed: heap.give(builder)
  narrowCode: code32 = convert.int64ToInt32(errorCode)
  mapRead: readErrno = winErrno(code32)
  readStatus: status4 = fileError(payload, readErrno)
  return status4
:sizeCheck
  overCheck: over = compare.greaterThanInt64(length, limit)
  if over refuseLarge put
:refuseLarge
  giveDataLarge: heap.give(data)
  giveBuilderLarge: heap.give(builder)
  largeStatus: status5 = slots.failWith(payload, tooLarge, zero)
  return status5
:put
  readRegion: region = slots.addressArg(shape, args, one)
  putIt: slots.putText(region, data, length, results)
  giveData: heap.give(data)
  giveBuilder: heap.give(builder)
  return ok

op fsWriteAll "fs.writeAll: a file's whole content, the file made if missing and emptied once it is known to be no one else's; the deadline is checked before it starts"
  invariant writesWholeFile "The file holds exactly the bytes, or busy while it is open, or the error"
  input shape machine.Address copied
  input args machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let errno Int64 0 mut
  let ok Int32 0
:begin
  nowhere: anywhere = machine.zero()
  readDeadline: deadline = slots.argOf(shape, args, two=2)
  lateCheck: late = deadlineCheck(deadline, payload)
  lateStatus: isLate = compare.notEqualInt32(late, ok)
  if isLate giveLate begin2
:giveLate
  return late
:begin2
  readPath: path = textAt(shape, args, zero=0)
  readBytes: bytes = textBytes(shape, args, zero)
  takeCell: cell = heap.take(sixteen=16)
  findIdentityCell: identityCell = machine.offset(cell, eight=8)
  keyOf: key = resolve(path, bytes, cell)
  readKeyBytes: keyBytes = machine.loadInt64(cell)
  claimIt: claimed = claim(key, keyBytes, one=1)
  if claimed open refuseBusy
:refuseBusy
  giveKeyBusy: heap.give(key)
  giveCellBusy: heap.give(cell)
  busyStatus: status1 = slots.failWith(payload, busy, zero)
  return status1
:open
  openIt: handle = openPath(path, bytes, genericWrite, shareReadWrite, openAlways, normalFile)
  invalidCheck: invalid = invalidHandle(handle)
  if invalid openRefused identity
:openRefused
  readCode: code = keptCode()
  mapCode: mapped = winErrno(code)
  set errno mapped
  unclaimOpen: unclaim(key, keyBytes, one)
  giveKeyOpen: heap.give(key)
  giveCellOpen: heap.give(cell)
  openStatus: status2 = fileError(payload, errno)
  return status2
:identity
  identityOf: ident = identityKey(handle, identityCell)
  noIdentCheck: noIdent = machine.equal(ident, anywhere)
  if noIdent noIdentity claimIdentity
:noIdentity
  storeNoIdent: machine.storeInt64(identityCell, zero)
  goto emptyIt
:claimIdentity
  readIdentBytes: identBytes = machine.loadInt64(identityCell)
  claimIdent: identClaimed = claim(ident, identBytes, one)
  if identClaimed emptyIt identityBusy
:identityBusy
  closeBusy: closedBusy = closeFile(handle)
  unclaimBusy: unclaim(key, keyBytes, one)
  giveKeyTaken: heap.give(key)
  giveIdentTaken: heap.give(ident)
  giveCellTaken: heap.give(cell)
  takenStatus: status3 = slots.failWith(payload, busy, zero)
  return status3
:emptyIt
  emptied: emptyCode = emptyFile(handle)
  emptyFailed: notEmptied = compare.notEqualInt32(emptyCode, ok)
  if notEmptied emptyRefused writeIt
:emptyRefused
  mapEmpty: emptyErrno = winErrno(emptyCode)
  set errno emptyErrno
  goto finish
:writeIt
  readData: data = textAt(shape, args, one)
  readDataBytes: dataBytes = textBytes(shape, args, one)
  writeAll: writeCode = output.writeAll(handle, data, dataBytes)
  writeFailed: notWritten = compare.notEqualInt32(writeCode, ok)
  if notWritten writeRefused finish
:writeRefused
  mapWrite: writeErrno = winErrno(writeCode)
  set errno writeErrno
  goto finish
:finish
  closeIt: closed = closeFile(handle)
  unclaimKey: unclaim(key, keyBytes, one)
  readFinalIdentBytes: finalIdentBytes = machine.loadInt64(identityCell)
  unclaimIdent: unclaim(ident, finalIdentBytes, one)
  giveKey: heap.give(key)
  giveIdent: heap.give(ident)
  giveCell: heap.give(cell)
  errorCheck: hasError = compare.notEqualInt64(errno, zero)
  if hasError giveError done
:giveError
  status: status4 = fileError(payload, errno)
  return status4
:done
  return ok

## ---------------------------------------------------------------- fs targets: paths

op fsExists "fs.exists: whether a path names something, links followed; an empty path names nothing"
  invariant findsPath "Gives 1 for a file or directory that is there, otherwise 0"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let yes Bool true
:begin
  readPath: path = textAt(shape, args, zero=0)
  readBytes: bytes = textBytes(shape, args, zero)
  emptyCheck: empty = compare.equalInt64(bytes, zero)
  if empty giveNo probe
:giveNo
  storeNo: machine.storeInt64(results, zero)
  return
:probe
  osCheck: onLinux = system.linux()
  if onLinux probeLinux probeWindows
:probeLinux
  statIt: statResult = statPath(path, bytes, yes)
  statFailed: missingLinux = kernel.failed(statResult)
  if missingLinux giveNo giveYesLinux
:giveYesLinux
  storeYesLinux: machine.storeInt64(results, one=1)
  return
:probeWindows
  openIt: handle = openPath(path, bytes, noAccess=0, shareAll, openExisting, backupSemantics)
  invalidCheck: invalid = invalidHandle(handle)
  if invalid sharingCheck giveYes
:giveYes
  closeIt: closed = closeFile(handle)
  storeYes: machine.storeInt64(results, one)
  return
:sharingCheck
  readCode: code = keptCode()
  sharing: isSharing = compare.equalInt32(code, sharingViolation=32)
  if isSharing attributes giveNo
:attributes
  regularCheck: regular = isRegularFile(path, bytes)
  wideName: name = wide.widen(path, bytes)
  readAttributes: found = system.getFileAttributesW(name)
  giveName: heap.give(name)
  missingCheck: missing = compare.equalInt32(found, minusOne32=-1)
  if missing giveNo giveYesAttributes
:giveYesAttributes
  storeYesAttributes: machine.storeInt64(results, one)
  return

op fsRemove "fs.remove: delete a file; busy while it is open under this or another name (D-52, D-109)"
  invariant removesFile "The file is gone, or busy while the program holds it open, or the error"
  input shape machine.Address copied
  input args machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok Int32 0
  let yes Bool true
:begin
  nowhere: anywhere = machine.zero()
  readPath: path = textAt(shape, args, zero=0)
  readBytes: bytes = textBytes(shape, args, zero)
  takeCell: cell = heap.take(eight=8)
  keyOf: key = resolve(path, bytes, cell)
  readKeyBytes: keyBytes = machine.loadInt64(cell)
  findIt: held = findClaim(key, keyBytes)
  giveKey: heap.give(key)
  heldCheck: isHeld = compare.greaterOrEqualInt64(held, zero)
  if isHeld refuseBusy probe
:refuseBusy
  giveCellBusy: heap.give(cell)
  busyStatus: status1 = slots.failWith(payload, busy, zero)
  return status1
:probe
  osCheck: onLinux = system.linux()
  if onLinux probeLinux probeWindows
:probeLinux
  statIt: statResult = statPath(path, bytes, yes)
  statFailed: missingLinux = kernel.failed(statResult)
  if missingLinux delete identifyLinux
:identifyLinux
  findStatus: linuxStatusBlock = stateAt(statAt)
  identityLinux: linuxIdent = statusIdentity(linuxStatusBlock, cell)
  noLinuxIdent: noIdentLinux = machine.equal(linuxIdent, anywhere)
  if noIdentLinux delete findLinuxIdent
:findLinuxIdent
  readLinuxIdentBytes: linuxIdentBytes = machine.loadInt64(cell)
  findLinuxHeld: linuxIdentHeld = findClaim(linuxIdent, linuxIdentBytes)
  giveLinuxIdent: heap.give(linuxIdent)
  linuxHeldCheck: isLinuxHeld = compare.greaterOrEqualInt64(linuxIdentHeld, zero)
  if isLinuxHeld refuseBusy delete
:probeWindows
  openIt: handle = openPath(path, bytes, noAccess=0, shareAll, openExisting, backupSemantics)
  invalidCheck: invalid = invalidHandle(handle)
  if invalid delete identify
:identify
  identityOf: ident = identityKey(handle, cell)
  closeIt: closed = closeFile(handle)
  noIdentCheck: noIdent = machine.equal(ident, anywhere)
  if noIdent delete findIdent
:findIdent
  readIdentBytes: identBytes = machine.loadInt64(cell)
  findHeld: identHeld = findClaim(ident, identBytes)
  giveIdent: heap.give(ident)
  identHeldCheck: isIdentHeld = compare.greaterOrEqualInt64(identHeld, zero)
  if isIdentHeld refuseBusy delete
:delete
  giveCell: heap.give(cell)
  osDeleteCheck: deleteOnLinux = system.linux()
  if deleteOnLinux deleteLinux deleteWindows
:deleteLinux
  copyPath: linuxName = cPath(path, bytes)
  unlinkIt: unlinked = system.unlinkat(atWorkingDirectory, linuxName, zero)
  giveLinuxName: heap.give(linuxName)
  unlinkFailed: refusedLinux = kernel.failed(unlinked)
  if refusedLinux failedUnlink done
:failedUnlink
  unlinkErrno: linuxErrno = kernel.errnoOf(unlinked)
  unlinkStatus: status3 = fileError(payload, linuxErrno)
  return status3
:deleteWindows
  wideName: name = wide.widen(path, bytes)
  deleteIt: deleted = system.deleteFileW(name)
  readError: code = system.getLastError()
  giveName: heap.give(name)
  deletedCheck: refused = compare.equalInt32(deleted, noAccess)
  if refused failedDelete done
:failedDelete
  mapIt: errno = winErrno(code)
  status: status2 = fileError(payload, errno)
  return status2
:done
  return ok

op fsCreateDirectory "fs.createDirectory: make a directory"
  invariant makesDirectory "The directory is there, or exists, or the error"
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
  readPath: path = textAt(shape, args, zero=0)
  readBytes: bytes = textBytes(shape, args, zero)
  osCheck: onLinux = system.linux()
  if onLinux makeLinux makeWindows
:makeLinux
  copyPath: linuxName = cPath(path, bytes)
  mkdirIt: madeLinux = system.mkdirat(atWorkingDirectory, linuxName, everyone=511)
  giveLinuxName: heap.give(linuxName)
  mkdirFailed: refusedLinux = kernel.failed(madeLinux)
  if refusedLinux failedLinux done
:failedLinux
  mkdirErrno: linuxErrno = kernel.errnoOf(madeLinux)
  linuxStatus: status2 = fileError(payload, linuxErrno)
  return status2
:makeWindows
  wideName: name = wide.widen(path, bytes)
  nowhere: anywhere = machine.zero()
  makeIt: made = system.createDirectoryW(name, anywhere)
  readError: code = system.getLastError()
  giveName: heap.give(name)
  madeCheck: refused = compare.equalInt32(made, ok)
  if refused failedMake done
:failedMake
  mapIt: errno = winErrno(code)
  status: status1 = fileError(payload, errno)
  return status1
:done
  return ok

op fsRemoveDirectory "fs.removeDirectory: remove an empty directory"
  invariant removesDirectory "The directory is gone, or the error (failed with ENOTEMPTY for one that is not empty)"
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
  readPath: path = textAt(shape, args, zero=0)
  readBytes: bytes = textBytes(shape, args, zero)
  osCheck: onLinux = system.linux()
  if onLinux removeLinux removeWindows
:removeLinux
  copyPath: linuxName = cPath(path, bytes)
  rmdirIt: removedLinux = system.unlinkat(atWorkingDirectory, linuxName, removeDirectoryFlag=512)
  giveLinuxName: heap.give(linuxName)
  rmdirFailed: refusedLinux = kernel.failed(removedLinux)
  if refusedLinux failedLinux done
:failedLinux
  rmdirErrno: linuxErrno = kernel.errnoOf(removedLinux)
  linuxStatus: status2 = fileError(payload, linuxErrno)
  return status2
:removeWindows
  wideName: name = wide.widen(path, bytes)
  removeIt: removed = system.removeDirectoryW(name)
  readError: code = system.getLastError()
  giveName: heap.give(name)
  removedCheck: refused = compare.equalInt32(removed, ok)
  if refused failedRemove done
:failedRemove
  mapIt: errno = winErrno(code)
  status: status1 = fileError(payload, errno)
  return status1
:done
  return ok

## ---------------------------------------------------------------- fs targets: locks

op fsLock "fs.lock: take an exclusive lock on a file, trying every 50 ms until the deadline (timedOut) or a cancel (cancelled)"
  invariant locksFile "The file is locked by this handle, or timedOut, or cancelled"
  input shape machine.Address copied
  input args machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok Int32 0
  let forever Int64 9223372036854775807
  let poll Int64 0 mut
:begin
  nowhere: anywhere = machine.zero()
  readHandle: fileHandle = slots.argOf(shape, args, zero=0)
  findFile: file = handles.objectOf(fileHandle, kindFile)
  readOs: handle = link(file, zero)
  readDeadline: deadline = slots.argOf(shape, args, one=1)
  goto eachTry
:eachTry loop=while max=forever
  osCheck: onLinux = system.linux()
  if onLinux lockLinux lockWindows
:lockLinux in=eachTry
  descriptorOf: fd = machine.toInt64(handle)
  flockIt: flocked = system.flock(fd, exclusiveNow=6)
  flockFailed: refusedLinux = kernel.failed(flocked)
  if refusedLinux heldCheck done
:heldCheck in=eachTry
  flockErrno: linuxErrno = kernel.errnoOf(flocked)
  againCheck: isAgain = compare.equalInt64(linuxErrno, eagain=11)
  if isAgain pastCheck failedLock
:failedLock
  lockStatus: status3 = fileError(payload, linuxErrno)
  return status3
:lockWindows in=eachTry
  lockIt: locked = system.lockFile(handle, ok, ok, oneByte=1, ok)
  lockedCheck: gotIt = compare.notEqualInt32(locked, ok)
  if gotIt done pastCheck
:pastCheck in=eachTry
  readNow: moment = tasks.now()
  neverCheck: isNever = compare.equalInt64(deadline, minusOne=-1)
  if isNever pause compareDeadline
:compareDeadline in=eachTry
  passedCheck: passed = compare.greaterOrEqualInt64(moment, deadline)
  if passed giveTimedOut pause
:pause in=eachTry
  later: pollAt = math.addInt64(moment, fifty=50)
  set poll pollAt
  earlierCheck: deadlineFirst = compare.lessThanInt64(deadline, pollAt)
  notNever: hasDeadline = logic.not(isNever)
  useDeadlineCheck: useDeadline = logic.and(hasDeadline, deadlineFirst)
  if useDeadline useDeadlineTime waitIt
:useDeadlineTime in=eachTry
  set poll deadline
  goto waitIt
:waitIt in=eachTry
  waitOnce: outcome = tasks.wait(lockText="a wait for a file lock", poll, one2=1, anywhere)
  cancelledCheck: isCancelled = compare.equalInt64(outcome, two=2)
  if isCancelled giveCancelled eachTry
:giveTimedOut
  timedStatus: status1 = slots.failWith(payload, timedOut, zero)
  return status1
:giveCancelled
  cancelledStatus: status2 = slots.failWith(payload, cancelledError, zero)
  return status2
:done
  return ok

op fsUnlock "fs.unlock: give back a file's lock; one not held is denied, as the C library's locking reports it"
  invariant unlocksFile "The lock is given back, or denied when the handle did not hold it"
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
  readHandle: fileHandle = slots.argOf(shape, args, zero=0)
  findFile: file = handles.objectOf(fileHandle, kindFile)
  readOs: handle = link(file, zero)
  osCheck: onLinux = system.linux()
  if onLinux unlockLinux unlockWindows
:unlockLinux
  descriptorOf: fd = machine.toInt64(handle)
  flockIt: unflocked = system.flock(fd, unlockOperation=8)
  flockFailed: refusedLinux = kernel.failed(unflocked)
  if refusedLinux failedUnlock done
:failedUnlock
  flockErrno: linuxErrno = kernel.errnoOf(unflocked)
  unlockStatus: status2 = fileError(payload, linuxErrno)
  return status2
:unlockWindows
  unlockIt: unlocked = system.unlockFile(handle, ok, ok, oneByte=1, ok)
  unlockedCheck: refused = compare.equalInt32(unlocked, ok)
  if refused giveDenied done
:giveDenied
  status: status1 = fileError(payload, thirteen=13)
  return status1
:done
  return ok

## ---------------------------------------------------------------- fs targets: listings

op sortNames "Sort a list of names by their bytes, as Python's sorted orders `str`"
  input names machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 1 mut
  let back Int64 0 mut
:begin
  readCount: count = handles.nameCount(names)
  takeHeld: held = heap.take(sixteen=16)
  goto eachName
:eachName loop=while max=count
  doneCheck: done = compare.greaterOrEqualInt64(at, count)
  if done finish takeOut
:takeOut in=eachName
  findCurrent: current = handles.nameAt(names, at)
  keepCurrent: machine.copy(held, current, sixteen)
  set back at
  goto eachBack
:eachBack loop=while max=count in=eachName
  startCheck: atStart = compare.lessOrEqualInt64(back, zero=0)
  if atStart place compareBack
:compareBack in=eachBack
  before: previous = math.subtractInt64(back, one=1)
  findPrevious: previousSlot = handles.nameAt(names, previous)
  readPrevious: previousText = machine.loadAddress(previousSlot)
  readPreviousBytes: previousBytes = field(previousSlot, eight=8)
  readHeld: heldText = machine.loadAddress(held)
  readHeldBytes: heldBytes = field(held, eight)
  orderOf: order = wide.textOrder(previousText, previousBytes, heldText, heldBytes)
  laterCheck: later = compare.greaterThanInt64(order, zero)
  if later shift place
:shift in=eachBack
  findTarget: targetSlot = handles.nameAt(names, back)
  moveUp: machine.copy(targetSlot, previousSlot, sixteen)
  set back previous
  goto eachBack
:place in=eachName
  findPlace: placeSlot = handles.nameAt(names, back)
  putBack: machine.copy(placeSlot, held, sixteen)
  nextName: after = math.addInt64(at, one)
  set at after
  goto eachName
:finish
  giveHeld: heap.give(held)
  return

op fsListDirectory "fs.listDirectory: the names in a directory, but `.` and `..`, sorted, as a Listing owned by a region"
  invariant listsDirectory "Gives a Listing of the directory's names in order, or the error"
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
  let forever Int64 9223372036854775807
  let backslash Byte 92
  let pattern String "*.*"
:begin
  readPath: path = textAt(shape, args, zero=0)
  readBytes: bytes = textBytes(shape, args, zero)
  osCheck: onLinux = system.linux()
  if onLinux listLinux listWindows
:listLinux
  linuxIt: linuxStatus = listDirectoryLinux(path, bytes, shape, args, results, payload)
  return linuxStatus
:listWindows
  makeBuilder: builder = wide.builderNew()
  addPath: wide.builderAdd(builder, path, bytes)
  emptyCheck: empty = compare.equalInt64(bytes, zero)
  if empty addPattern lastCheck
:lastCheck
  lastOf: lastAt = math.subtractInt64(bytes, one=1)
  readLast: last = byteAt(path, lastAt)
  separatorCheck: endsInSeparator = isSeparator(last)
  colonCheck: endsInColon = compare.equalByte(last, colon=58)
  eitherCheck: noSeparator = logic.or(endsInSeparator, endsInColon)
  if noSeparator addPattern addSeparator
:addSeparator
  addIt: wide.builderAddByte(builder, backslash)
  goto addPattern
:addPattern
  findPattern: patternAt = machine.addressOfString(pattern)
  addStar: wide.builderAdd(builder, patternAt, three=3)
  readText: searchText = wide.builderText(builder)
  readLength: searchBytes = wide.builderLength(builder)
  wideSearch: search = wide.widen(searchText, searchBytes)
  giveText: heap.give(searchText)
  giveBuilder: heap.give(builder)
  findFound: found = stateAt(foundAt)
  findFirst: handle = system.findFirstFileW(search, found)
  readError: code = system.getLastError()
  giveSearch: heap.give(search)
  invalidCheck: invalid = invalidHandle(handle)
  if invalid failedList listIt
:failedList
  mapIt: errno = winErrno(code)
  status: status1 = fileError(payload, errno)
  return status1
:listIt
  takeNames: names = heap.take(twentyFour=24)
  takeCell: cell = heap.take(eight=8)
  findName: nameAt = machine.offset(found, fortyFour=44)
  goto eachEntry
:eachEntry loop=while max=forever
  countUnits: units = wide.wideUnits(nameAt)
  narrowName: name = wide.narrow(nameAt, units, cell)
  readNameBytes: nameBytes = machine.loadInt64(cell)
  dotCheck: isDot = isDots(name, nameBytes)
  if isDot skip add
:add in=eachEntry
  addName: handles.addName(names, name, nameBytes)
  goto skip
:skip in=eachEntry
  giveName: heap.give(name)
  findNext: more = system.findNextFileW(handle, found)
  moreCheck: hasMore = compare.notEqualInt32(more, ok)
  if hasMore eachEntry finish
:finish
  closeFind: closed = system.findClose(handle)
  giveCell: heap.give(cell)
  sortIt: sortNames(names)
  readRegion: region = slots.addressArg(shape, args, one)
  makeHandle: listing = handles.newHandle(kindListing, names, region)
  storeListing: machine.storeInt64(results, listing)
  return ok

op listDirectoryLinux "fs.listDirectory on Linux: the names getdents64 gives for a directory, but `.` and `..`, sorted, as a Listing owned by a region"
  input path machine.Address copied
  input bytes Int64 copied
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
  let forever Int64 9223372036854775807
  let entriesBytes Int64 32768
  let directoryFlags Int64 589824
:begin
  copyPath: name = cPath(path, bytes)
  openIt: fd = system.openat(atWorkingDirectory, name, directoryFlags, zero=0)
  giveName: heap.give(name)
  openFailed: refused = kernel.failed(fd)
  if refused failedOpen listIt
:failedOpen
  openErrno: errno = kernel.errnoOf(fd)
  openStatus: status1 = fileError(payload, errno)
  return status1
:listIt
  takeNames: names = heap.take(twentyFour=24)
  takeEntries: entries = heap.take(entriesBytes)
  goto eachRead
:eachRead loop=while max=forever
  readEntries: got = system.getdents64(fd, entries, entriesBytes)
  readFailed: failedRead = kernel.failed(got)
  if failedRead refuseRead endCheck
:endCheck in=eachRead
  doneCheck: done = compare.lessOrEqualInt64(got, zero)
  if done finish firstEntry
:firstEntry in=eachRead
  set at zero
  goto eachEntry
:eachEntry loop=while max=got in=eachRead
  entriesDone: allRead = compare.greaterOrEqualInt64(at, got)
  if allRead eachRead readEntry
:readEntry in=eachEntry
  findEntry: entry = machine.offset(entries, at)
  findLength: lengthAt = machine.offset(entry, sixteen=16)
  readLength: recordBytes = unsignedAt(lengthAt, zero)
  shortLength: recordLength = bits.andInt64(recordBytes, lowSixteen=65535)
  findEntryName: entryName = machine.offset(entry, nineteen=19)
  measure: nameBytes = cLength(entryName, recordLength)
  dotCheck: isDot = isDots(entryName, nameBytes)
  if isDot skip add
:add in=eachEntry
  addName: handles.addName(names, entryName, nameBytes)
  goto skip
:skip in=eachEntry
  nextEntry: after = math.addInt64(at, recordLength)
  set at after
  goto eachEntry
:refuseRead
  readErrno: listErrno = kernel.errnoOf(got)
  closeFailed: closedFailed = system.close(fd)
  giveEntriesFailed: heap.give(entries)
  giveNamesFailed: heap.give(names)
  readStatus: status2 = fileError(payload, listErrno)
  return status2
:finish
  closeIt: closed = system.close(fd)
  giveEntries: heap.give(entries)
  sortIt: sortNames(names)
  readRegion: region = slots.addressArg(shape, args, one=1)
  makeHandle: listing = handles.newHandle(kindListing, names, region)
  storeListing: machine.storeInt64(results, listing)
  return ok

op cLength "How many bytes come before the first 0 byte of a text, looking at most at a number of them"
  input text machine.Address copied
  input most Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  goto eachByte
:eachByte loop=while max=most
  doneCheck: done = compare.greaterOrEqualInt64(at, most)
  if done give readByte
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

op isDots "Whether a name is `.` or `..`"
  input name machine.Address copied
  input bytes Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let no Bool false
  let dots String ".."
:begin
  shortCheck: short = compare.lessOrEqualInt64(bytes, two=2)
  emptyCheck: notEmpty = compare.greaterThanInt64(bytes, zero=0)
  sizeCheck: fits = logic.and(short, notEmpty)
  if fits compareIt notDots
:compareIt
  findDots: dotsAt = machine.addressOfString(dots)
  compareDots: order = machine.compare(name, dotsAt, bytes)
  sameCheck: same = compare.equalInt32(order, zero32=0)
  return same
:notDots
  return no

op fsEntryCount "fs.entryCount: how many names a listing holds"
  invariant countsEntries "Gives the number of names"
  input shape machine.Address copied
  input args machine.Address copied
  input results machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readHandle: listing = slots.argOf(shape, args, zero=0)
  findNames: names = handles.objectOf(listing, kindListing)
  countIt: count = handles.nameCount(names)
  storeCount: machine.storeInt64(results, count)
  return

op fsEntryName "fs.entryName: the name at a position of a listing, into a region; outOfRange with the position past it"
  invariant namesEntry "Gives the name at the position, or outOfRange"
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
  readHandle: listing = slots.argOf(shape, args, zero=0)
  findNames: names = handles.objectOf(listing, kindListing)
  readIndex: index = slots.argOf(shape, args, one=1)
  countIt: count = handles.nameCount(names)
  lowCheck: low = compare.lessThanInt64(index, zero)
  highCheck: high = compare.greaterOrEqualInt64(index, count)
  outsideCheck: outside = logic.or(low, high)
  if outside refuse give
:refuse
  status: status1 = slots.failWith(payload, outOfRange, index)
  return status1
:give
  findName: nameSlot = handles.nameAt(names, index)
  readName: name = machine.loadAddress(nameSlot)
  readBytes: bytes = field(nameSlot, eight=8)
  readRegion: region = slots.addressArg(shape, args, two=2)
  putIt: slots.putText(region, name, bytes, results)
  return ok

@tests

## Tests build a call's shape and slots in the last 4 KiB of machine.state: the shape from byte 61440, the
## arguments from 61952 (eight slots), the results from 62016, the payload at 62080. They make and remove a file
## `refined-runtime-files.tmp` and a directory `refined-runtime-dir.tmp` in the working directory.

op testShape "Make the tests' shape from the slot counts of up to four parameters (0 for none) and give it"
  input first Int64 copied
  input second Int64 copied
  input third Int64 copied
  input fourth Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findShape: shape = stateAt(shapeAt=61440)
  storeFirst: setField(shape, forty=40, first)
  storeSecond: setField(shape, fortyEight=48, second)
  storeThird: setField(shape, fiftySix=56, third)
  storeFourth: setField(shape, sixtyFour=64, fourth)
  storeFirstStart: setField(shape, twoThirtyTwo=232, zero=0)
  secondStart: afterFirst = math.addInt64(first, zero)
  storeSecondStart: setField(shape, twoForty=240, afterFirst)
  thirdStart: afterSecond = math.addInt64(afterFirst, second)
  storeThirdStart: setField(shape, twoFortyEight=248, afterSecond)
  fourthStart: afterThird = math.addInt64(afterSecond, third)
  storeFourthStart: setField(shape, twoFiftySix=256, afterThird)
  firstCheck: hasFirst = compare.greaterThanInt64(first, zero)
  secondCheck: hasSecond = compare.greaterThanInt64(second, zero)
  thirdCheck: hasThird = compare.greaterThanInt64(third, zero)
  fourthCheck: hasFourth = compare.greaterThanInt64(fourth, zero)
  firstFlag: countFirst = flagOf(hasFirst)
  secondFlag: countSecond = flagOf(hasSecond)
  thirdFlag: countThird = flagOf(hasThird)
  fourthFlag: countFourth = flagOf(hasFourth)
  sumTwo: two = math.addInt64(countFirst, countSecond)
  sumThree: three = math.addInt64(two, countThird)
  sumFour: four = math.addInt64(three, countFourth)
  storeParams: setField(shape, twentyFour=24, four)
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
  findText: textAt2 = machine.addressOfString(text)
  textLength: bytes = string.byteLength(text)
  findSlot: address = argSlot(slot)
  storeAddress: machine.storeAddress(address, textAt2)
  findLength: lengthSlot = machine.offset(address, eight=8)
  storeLength: machine.storeInt64(lengthSlot, bytes)
  return

op resultsAt "The address of the tests' result slots"
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findResults: results = stateAt(resultsOffset=62016)
  return results

op payloadAt "The address of the tests' payload slot"
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findPayload: payload = stateAt(payloadOffset=62080)
  return payload

op expectStatus "Compare a call's status with what is expected"
  input wanted Int64 copied
  input status Int32 copied
:begin
  widenStatus: statusValue = convert.int32ToInt64(status)
  compareIt: test.assertEqualInt64(wanted, statusValue)
  return

op expectResultText "Compare the text in the first two result slots with what is expected"
  input wanted String borrowed
  effect use machine.memory
  uses memoryAccess
:begin
  readResults: results = resultsAt()
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

op resultHandle "The handle in the first result slot"
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  readResults: results = resultsAt()
  readHandle: handle = machine.loadInt64(results)
  return handle

op preparePath "Make the tests' call one path"
  input path String borrowed
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  shapeOf: shape = testShape(two=2, zero=0, zero, zero)
  setPath: setTextArg(zero, path)
  return shape

op prepareWrite "Make the tests' call a handle, a text, and no deadline"
  input handle Int64 copied
  input text String borrowed
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  shapeOf: shape = testShape(one=1, two=2, one, zero=0)
  setHandle: setArg(zero, handle)
  setData: setTextArg(one, text)
  setDeadline: setArg(three=3, minusOne=-1)
  return shape

op prepareHandle "Make the tests' call a handle and no deadline"
  input handle Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  shapeOf: shape = testShape(one=1, one, zero=0, zero)
  setHandle: setArg(zero, handle)
  setDeadline: setArg(one, minusOne=-1)
  return shape

op prepareRead "Make the tests' call a handle, a region, a number of bytes, and no deadline"
  input handle Int64 copied
  input region machine.Address copied
  input most Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  shapeOf: shape = testShape(one=1, one, one, one)
  setHandle: setArg(zero=0, handle)
  setRegion: setAddressArg(one, region)
  setMost: setArg(two=2, most)
  setDeadline: setArg(three=3, minusOne=-1)
  return shape

op prepareReadAll "Make the tests' call a path, a region, a number of bytes, and no deadline"
  input path String borrowed
  input region machine.Address copied
  input most Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  shapeOf: shape = testShape(two=2, one=1, one, one)
  setPath: setTextArg(zero=0, path)
  setRegion: setAddressArg(two, region)
  setMost: setArg(three=3, most)
  setDeadline: setArg(four=4, minusOne=-1)
  return shape

op prepareWriteAll "Make the tests' call a path, a text, and no deadline"
  input path String borrowed
  input text String borrowed
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  shapeOf: shape = testShape(two=2, two, one=1, zero=0)
  setPath: setTextArg(zero, path)
  setData: setTextArg(two, text)
  setDeadline: setArg(four=4, minusOne=-1)
  return shape

op cleanUp "Remove a file or an empty directory a test may have left, whatever is there"
  input path String borrowed
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findPath: pathAt = machine.addressOfString(path)
  pathLength: bytes = string.byteLength(path)
  osCheck: onLinux = system.linux()
  if onLinux cleanLinux cleanWindows
:cleanLinux
  copyPath: linuxName = cPath(pathAt, bytes)
  unlinkIt: unlinked = system.unlinkat(atWorkingDirectory, linuxName, zero=0)
  rmdirIt: removedLinux = system.unlinkat(atWorkingDirectory, linuxName, removeDirectoryFlag=512)
  giveLinuxName: heap.give(linuxName)
  return
:cleanWindows
  wideName: name = wide.widen(pathAt, bytes)
  deleteIt: deleted = system.deleteFileW(name)
  removeIt: removed = system.removeDirectoryW(name)
  giveName: heap.give(name)
  return

test fileTest "Files are made, written, read, appended, emptied, locked, listed in order, and removed as host.py does them, with busy for a file open for writing and the errors Python reports"
  verifies textAt readsTextAddress
  verifies textBytes readsTextLength
  verifies fsCreate createsFile
  verifies fsWrite writesFile
  verifies fsOpenRead opensForReading
  verifies fsClose closesFile
  verifies fsRead readsFile
  verifies fsReadAll readsWholeFile
  verifies fsWriteAll writesWholeFile
  verifies fsOpenAppend opensForAppending
  verifies fsOpenWrite opensForWriting
  verifies fsLock locksFile
  verifies fsUnlock unlocksFile
  verifies fsExists findsPath
  verifies fsCreateDirectory makesDirectory
  verifies fsListDirectory listsDirectory
  verifies fsEntryCount countsEntries
  verifies fsEntryName namesEntry
  verifies fsRemove removesFile
  verifies fsRemoveDirectory removesDirectory
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let file String "refined-runtime-files.tmp"
  let directory String "refined-runtime-dir.tmp"
  let inA String "refined-runtime-dir.tmp/b"
  let inB String "refined-runtime-dir.tmp/a"
  let label String "files test"
  let hello String "hello"
:begin
  cleanFile: cleanUp(file)
  cleanA: cleanUp(inA)
  cleanB: cleanUp(inB)
  cleanDirectory: cleanUp(directory)
  findLabel: labelAt = machine.addressOfString(label)
  labelLength: labelBytes = string.byteLength(label)
  make: region = regions.newRegion(capacity=65536, labelAt, labelBytes)
  findArgs: args = argSlot(zero=0)
  readResults: results = resultsAt()
  readPayload: payload = payloadAt()
  pathShape: shape1 = preparePath(file)
  readTextAt: fileText = textAt(shape1, args, zero)
  readTextBytes: pathLength = textBytes(shape1, args, zero)
  findFile: fileAt = machine.addressOfString(file)
  sameText: sameAddress = machine.equal(fileText, fileAt)
  expectTextAt: test.assertTrue(sameAddress)
  expectTextBytes: test.assertEqualInt64(twentyFive=25, pathLength)
  create: created = fsCreate(shape1, args, results, payload)
  expectCreated: expectStatus(zero, created)
  readCreated: writer = resultHandle()
  writeShape: shape2 = prepareWrite(writer, hello)
  write: wrote = fsWrite(shape2, args, payload)
  expectWrote: expectStatus(zero, wrote)
  pathShape2: shape3 = preparePath(file)
  readBusy: busyStatus = fsOpenRead(shape3, args, results, payload)
  expectBusy: expectStatus(seven=7, busyStatus)
  closeShape: shape4 = prepareHandle(writer)
  closeWriter: closedWriter = fsClose(shape4, args, payload)
  expectClosed: expectStatus(zero, closedWriter)
  pathShape3: shape5 = preparePath(file)
  createAgain: again = fsCreate(shape5, args, results, payload)
  expectExists: expectStatus(three=3, again)
  openReader: opened = fsOpenRead(shape5, args, results, payload)
  expectOpened: expectStatus(zero, opened)
  readReader: reader = resultHandle()
  readShape: shape6 = prepareRead(reader, region, hundred=100)
  readIt: readStatus = fsRead(shape6, args, results, payload)
  expectRead: expectStatus(zero, readStatus)
  expectHello: expectResultText(hello)
  writeShape2: shape7 = prepareWrite(reader, nope="nope")
  writeReader: refused = fsWrite(shape7, args, payload)
  expectRefused: expectStatus(eight=8, refused)
  closeShape2: shape8 = prepareHandle(reader)
  closeReader: closedReader = fsClose(shape8, args, payload)
  readAllShape: shape9 = prepareReadAll(file, region, three)
  readSmall: tooLargeStatus = fsReadAll(shape9, args, results, payload)
  expectTooLarge: expectStatus(four=4, tooLargeStatus)
  readAllShape2: shape10 = prepareReadAll(file, region, hundred)
  readAll: wholeStatus = fsReadAll(shape10, args, results, payload)
  expectWhole: expectStatus(zero, wholeStatus)
  expectWholeText: expectResultText(hello)
  writeAllShape: shape11 = prepareWriteAll(file, bye="bye")
  writeAll: replaced = fsWriteAll(shape11, args, payload)
  expectReplaced: expectStatus(zero, replaced)
  pathShape4: shape12 = preparePath(file)
  openAppender: appendOpened = fsOpenAppend(shape12, args, results, payload)
  expectAppendOpened: expectStatus(zero, appendOpened)
  readAppender: appender = resultHandle()
  lockShape: shape13 = prepareHandle(appender)
  lockIt: locked = fsLock(shape13, args, payload)
  expectLocked: expectStatus(zero, locked)
  unlockIt: unlocked = fsUnlock(shape13, args, payload)
  expectUnlocked: expectStatus(zero, unlocked)
  unlockAgain: notLocked = fsUnlock(shape13, args, payload)
  unlockOs: unlockOnLinux = system.linux()
  if unlockOnLinux linuxUnlocked windowsUnlocked
:linuxUnlocked
  expectLinuxUnlocked: expectStatus(zero32Status=0, notLocked)
  goto afterUnlock
:windowsUnlocked
  expectNotLocked: expectStatus(two=2, notLocked)
  goto afterUnlock
:afterUnlock
  writeShape3: shape14 = prepareWrite(appender, bang="!")
  appendIt: appended = fsWrite(shape14, args, payload)
  expectAppended: expectStatus(zero, appended)
  closeShape3: shape15 = prepareHandle(appender)
  closeAppender: closedAppender = fsClose(shape15, args, payload)
  readAllShape3: shape16 = prepareReadAll(file, region, hundred)
  readAppended: appendedStatus = fsReadAll(shape16, args, results, payload)
  expectAppendedText: expectResultText(byeBang="bye!")
  pathShape5: shape17 = preparePath(file)
  openEmptied: emptiedStatus = fsOpenWrite(shape17, args, results, payload)
  expectEmptied: expectStatus(zero, emptiedStatus)
  readEmptied: emptied = resultHandle()
  readShape2: shape18 = prepareRead(emptied, region, hundred)
  readNothing: nothingStatus = fsRead(shape18, args, results, payload)
  expectNothing: expectResultText(empty="")
  closeShape4: shape19 = prepareHandle(emptied)
  closeEmptied: closedEmptied = fsClose(shape19, args, payload)
  pathShape6: shape20 = preparePath(file)
  existsFile: fsExists(shape20, args, results)
  readPresent: present = machine.loadInt64(results)
  expectPresent: test.assertEqualInt64(one=1, present)
  pathShape7: shape21 = preparePath(directory)
  makeDirectory: madeDirectory = fsCreateDirectory(shape21, args, payload)
  expectMade: expectStatus(zero, madeDirectory)
  makeAgain: madeAgain = fsCreateDirectory(shape21, args, payload)
  expectMadeAgain: expectStatus(three, madeAgain)
  writeAllShape2: shape22 = prepareWriteAll(inA, hello)
  writeA: wroteA = fsWriteAll(shape22, args, payload)
  writeAllShape3: shape23 = prepareWriteAll(inB, hello)
  writeB: wroteB = fsWriteAll(shape23, args, payload)
  listShape: shape24 = testShape(two, one, zero, zero)
  setListPath: setTextArg(zero, directory)
  setListRegion: setAddressArg(two, region)
  listIt: listed = fsListDirectory(shape24, args, results, payload)
  expectListed: expectStatus(zero, listed)
  readListing: listing = resultHandle()
  countShape: shape25 = testShape(one, zero, zero, zero)
  setListing: setArg(zero, listing)
  countIt: fsEntryCount(shape25, args, results)
  readCount: count = machine.loadInt64(results)
  expectCount: test.assertEqualInt64(two, count)
  nameShape: shape26 = testShape(one, one, one, zero)
  setListingAgain: setArg(zero, listing)
  setIndex: setArg(one, zero)
  setNameRegion: setAddressArg(two, region)
  nameIt: named = fsEntryName(shape26, args, results, payload)
  expectNamed: expectStatus(zero, named)
  expectFirstName: expectResultText(nameA="a")
  setFar: setArg(one, two)
  nameFar: farStatus = fsEntryName(shape26, args, results, payload)
  expectFar: expectStatus(one, farStatus)
  pathShape8: shape27 = preparePath(inA)
  removeA: removedA = fsRemove(shape27, args, payload)
  pathShape9: shape28 = preparePath(inB)
  removeB: removedB = fsRemove(shape28, args, payload)
  pathShape10: shape29 = preparePath(directory)
  removeDirectory: removedDirectory = fsRemoveDirectory(shape29, args, payload)
  expectRemovedDirectory: expectStatus(zero, removedDirectory)
  pathShape11: shape30 = preparePath(file)
  removeFile: removed = fsRemove(shape30, args, payload)
  expectRemoved: expectStatus(zero, removed)
  existsGone: fsExists(shape30, args, results)
  readAbsent: absent = machine.loadInt64(results)
  expectAbsent: test.assertEqualInt64(zero, absent)
  removeAgain: missing = fsRemove(shape30, args, payload)
  expectMissing: expectStatus(one, missing)
  openMissing: missingOpen = fsOpenRead(shape30, args, results, payload)
  expectMissingOpen: expectStatus(one, missingOpen)
  free: regions.release(region)
  return

test pathTest "Paths resolve as Python's normcase(realpath()) does, scopes take in what lies inside them, errors map as Python maps them, and bytes are copied"
  verifies resolve resolvesPath
  verifies pathWithin checksScope
  verifies checkScope checksScopes
  verifies winErrno mapsErrors
  verifies fileError classifiesErrno
  verifies copyBytes copiesBytes
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let plain String "Some/Name"
  let plainLinux String "some/name"
  let plainValue Int64 0 mut
  let plainLength Int64 0 mut
  let roundabout String "some/other/../name"
  let inside String "data/x.txt"
  let outside String "other/x.txt"
  let directoryScope String "data/"
  let named String "suite-12"
  let patternScope String "suite-*"
  let scopes String "read fs.files\ndata/\nsuite-*"
  let programs String "run process.programs\ntool"
  let tool String "tool"
:begin
  takeCell: cell = heap.take(eight=8)
  findPlain: plainAt = machine.addressOfString(plain)
  plainOf: plainBytes = string.byteLength(plain)
  plainAddress: plainAtValue = machine.toInt64(plainAt)
  set plainValue plainAtValue
  set plainLength plainBytes
  osCheck: onLinux = system.linux()
  if onLinux linuxPlain resolveIt
:linuxPlain
  findLinuxPlain: linuxPlainAt = machine.addressOfString(plainLinux)
  linuxPlainLength: linuxPlainBytes = string.byteLength(plainLinux)
  linuxPlainAddress: linuxPlainValue = machine.toInt64(linuxPlainAt)
  set plainValue linuxPlainValue
  set plainLength linuxPlainBytes
  goto resolveIt
:resolveIt
  chosenPlain: chosenAt = machine.fromInt64(plainValue)
  resolvePlain: first = resolve(chosenAt, plainLength, cell)
  readFirst: firstBytes = machine.loadInt64(cell)
  findRoundabout: roundaboutAt = machine.addressOfString(roundabout)
  roundaboutLength: roundaboutBytes = string.byteLength(roundabout)
  resolveRoundabout: second = resolve(roundaboutAt, roundaboutBytes, cell)
  readSecond: secondBytes = machine.loadInt64(cell)
  compareResolved: same = memory.bytesEqual(first, firstBytes, second, secondBytes)
  sameWide: sameValue = convert.int32ToInt64(same)
  expectSame: test.assertEqualInt64(one=1, sameValue)
  findInside: insideAt = machine.addressOfString(inside)
  insideLength: insideBytes = string.byteLength(inside)
  findDirectory: directoryAt = machine.addressOfString(directoryScope)
  directoryLength: directoryBytes = string.byteLength(directoryScope)
  withinCheck: within = pathWithin(insideAt, insideBytes, directoryAt, directoryBytes)
  expectWithin: test.assertTrue(within)
  findOutside: outsideAt = machine.addressOfString(outside)
  outsideLength: outsideBytes = string.byteLength(outside)
  outsideCheck: notWithin = pathWithin(outsideAt, outsideBytes, directoryAt, directoryBytes)
  notOutside: isOutside = logic.not(notWithin)
  expectOutside: test.assertTrue(isOutside)
  findNamed: namedAt = machine.addressOfString(named)
  namedLength: namedBytes = string.byteLength(named)
  findPattern: patternAt = machine.addressOfString(patternScope)
  patternLength: patternBytes = string.byteLength(patternScope)
  patternCheck: matches = pathWithin(namedAt, namedBytes, patternAt, patternBytes)
  expectMatches: test.assertTrue(matches)
  findScopes: scopesAt = machine.addressOfString(scopes)
  scopesLength: scopesBytes = string.byteLength(scopes)
  checkInside: checkScope(target="fs.readAll", insideAt, insideBytes, scopesAt, scopesBytes)
  checkNamed: checkScope(target, namedAt, namedBytes, scopesAt, scopesBytes)
  findPrograms: programsAt = machine.addressOfString(programs)
  programsLength: programsBytes = string.byteLength(programs)
  findTool: toolAt = machine.addressOfString(tool)
  toolLength: toolBytes = string.byteLength(tool)
  checkTool: checkScope(runTarget="process.run", toolAt, toolBytes, programsAt, programsBytes)
  mapMissing: missingErrno = winErrno(two32=2)
  expectMissing: test.assertEqualInt64(two=2, missingErrno)
  mapDenied: deniedErrno = winErrno(five32=5)
  mapExists: existsErrno = winErrno(eighty32=80)
  mapNotEmpty: notEmptyErrno = winErrno(oneFortyFive32=145)
  if onLinux linuxErrnos windowsErrnos
:linuxErrnos
  expectSameDenied: test.assertEqualInt64(five=5, deniedErrno)
  expectSameExists: test.assertEqualInt64(eighty=80, existsErrno)
  expectSameNotEmpty: test.assertEqualInt64(oneFortyFive=145, notEmptyErrno)
  goto classifyIt
:windowsErrnos
  expectDenied: test.assertEqualInt64(thirteen=13, deniedErrno)
  expectExists: test.assertEqualInt64(seventeen=17, existsErrno)
  expectNotEmpty: test.assertEqualInt64(fortyOne=41, notEmptyErrno)
  goto classifyIt
:classifyIt
  findPayload: payload = payloadAt()
  classify: classified = fileError(payload, twentyTwo=22)
  expectFailed: expectStatus(eight=8, classified)
  readPayload: stored = machine.loadInt64(payload)
  expectPayload: test.assertEqualInt64(twentyTwo, stored)
  copyIt: copy = copyBytes(plainAt, plainBytes)
  compareCopy: copied = memory.bytesEqual(copy, plainBytes, plainAt, plainBytes)
  copiedWide: copiedValue = convert.int32ToInt64(copied)
  expectCopy: test.assertEqualInt64(one, copiedValue)
  giveFirst: heap.give(first)
  giveSecond: heap.give(second)
  giveCopy: heap.give(copy)
  giveCell: heap.give(cell)
  return
