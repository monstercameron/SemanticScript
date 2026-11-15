module cstreams "stdio for the runtime's C library: FILE streams buffered as glibc buffers them, the printf and scanf families, and the files stdio names (D-160)"
  path cstreams
  imports standard.machine standard.system standard.string standard.math standard.compare standard.convert standard.bits standard.logic standard.test kernel heap output wide clibrary cformat
  exports flushAll

capability memoryAccess "Authority to read and write streams' blocks and the memory C callers hand the library" use machine.memory none

capability systemCalls "Authority to read, write, open, close, seek, rename, and remove files, and end the process" use system.calls none

## D-160: a FILE is a heap block of 128 bytes (stdin, stdout, and stderr are blocks in machine.state, which the data
## symbols point at): 0 flags (1 readable, 2 writable, 4 append, 8 end of file, 16 error, 32 unbuffered, 64 line
## buffered, 128 the buffer is the stream's own, 256 the buffering is decided, 512 closed), 8 the handle (a Linux
## descriptor, a Windows HANDLE), 16 the buffer, 24 its size, 32 where reading is in it, 40 where the bytes read
## end, 48 how many bytes wait to be written, 56 how many bytes ungetc pushed back, 64 those bytes (8 at most, the
## last pushed first), 80 the next stream opened, 88 1 for a string sscanf reads, 96 its orientation (0 none yet, 1
## wide, -1 bytes: D-176). Buffering is glibc's: a stream
## that is a terminal is line buffered, any other fully buffered with a buffer of the file's block size (st_blksize,
## 4096 on Windows), and stderr unbuffered; end of file is sticky, as since glibc 2.28. Bytes are never translated
## (`b` is accepted and changes nothing, on Windows too). exit and fflush(NULL) flush every stream; a program of
## SemanticScript that wrote to a C stream has its streams flushed when it ends (the address of fflush is kept at
## machine.state byte 2336, which the start module calls). machine.state bytes 1888 to 2343 belong to this module:
## 1888 whether the standard streams are ready, 1896 the first stream opened, 1912 one byte, 1920 stdin's FILE,
## 2048 stdout's, 2176 stderr's, 2304 tmpnam's name, 2336 the flush the runtime calls at the end.
constant readyAt "Where whether the standard streams are ready is kept, in machine.state" Int64 1888

constant listAt "Where the first stream fopen opened is kept, in machine.state" Int64 1896

constant byteAt "Where one byte is put to be written, in machine.state" Int64 1912

constant stdinFileAt "Where stdin's FILE is, in machine.state" Int64 1920

constant stdoutFileAt "Where stdout's FILE is, in machine.state" Int64 2048

constant stderrFileAt "Where stderr's FILE is, in machine.state" Int64 2176

constant nameAt "Where tmpnam writes a name when given no buffer, in machine.state" Int64 2304

constant hookAt "Where the address of fflush is kept for the runtime to call at the end, in machine.state" Int64 2336

constant forever "The bound of a loop that ends when its work does" Int64 9223372036854775807

constant readable "A FILE flag: it may be read" Int64 1

constant writable "A FILE flag: it may be written" Int64 2

constant appending "A FILE flag: every write goes to the end" Int64 4

constant atEnd "A FILE flag: end of file was reached" Int64 8

constant failed "A FILE flag: a read or write failed" Int64 16

constant unbuffered "A FILE flag: written at once" Int64 32

constant lineBuffered "A FILE flag: written at each line end" Int64 64

constant ownBuffer "A FILE flag: the buffer is the stream's own" Int64 128

constant decided "A FILE flag: the buffering is decided" Int64 256

constant closed "A FILE flag: fclose closed it" Int64 512

constant badFile "EBADF: a stream that cannot be read or written that way" Int32 9

constant invalid "EINVAL: an argument the function does not take" Int32 22

## ---------------------------------------------------------------- orientation (D-176)
##
## A stream has no orientation until it is first used, then keeps the one that use gave it until freopen: the wide
## functions make it wide, the byte functions make it bytes (fwide does either, or tells). As in glibc, printf,
## scanf, fputs, puts, and fwrite on a wide stream fail (and wprintf, wscanf, fputwc, and fputws on a byte stream),
## while getc, fgets, fread, and putc only orient a stream that has none.

op orient "fwide's rule: a stream with no orientation takes the one wanted (1 wide, -1 bytes, 0 none); gives the stream's orientation after"
  invariant keepsFirst "The first orientation a stream is given stays"
  input stream machine.Address copied
  input want Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  current = field(stream, 96)
  when current == 0 && want != 0 take keep
:take
  calc wanted = choose(want > 0, 1) - choose(want < 0, 1)
  setField(stream, 96, wanted)
  return wanted
:keep
  return current

## ---------------------------------------------------------------- fields

op field "A FILE's field at an offset, as a whole number"
  input stream machine.Address copied
  input offset Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  calc at = stream + offset
  value = machine.loadInt64(at)
  return value

op setField "Set a FILE's field at an offset"
  input stream machine.Address copied
  input offset Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc at = stream + offset
  machine.storeInt64(at, value)
  return

op hasFlag "Whether a FILE has a flag"
  input stream machine.Address copied
  input flag Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
:begin
  flags = machine.loadInt64(stream)
  calc present = (flags & flag) != 0
  return present

op addFlag "Give a FILE a flag"
  input stream machine.Address copied
  input flag Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  flags = machine.loadInt64(stream)
  calc more = flags | flag
  machine.storeInt64(stream, more)
  return

op dropFlag "Take a flag from a FILE"
  input stream machine.Address copied
  input flag Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  flags = machine.loadInt64(stream)
  calc fewer = flags & ~flag
  machine.storeInt64(stream, fewer)
  return

op handleOf "A FILE's handle as an address, for Windows's functions"
  input stream machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  value = field(stream, 8)
  handle = machine.fromInt64(value)
  return handle

## ---------------------------------------------------------------- the operating system

op setWindowsErrno "Set errno from GetLastError"
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  code = system.getLastError()
  calc mapped = clibrary.windowsErrno(code)
  clibrary.setErrno(mapped)
  return

op setLinuxErrno "Set errno from a failed system call's result (a negative errno)"
  input result Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc code = clibrary.lowInt32(0 - result)
  clibrary.setErrno(code)
  return

op rawWrite "Write bytes to a handle, all of them; whether it worked (errno set when not)"
  input handle Int64 copied
  input data machine.Address copied
  input bytes Int64 copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc target = machine.fromInt64(handle)
  status = output.writeAll(target, data, bytes)
  when status == 0 wrote failedWrite
:wrote
  return true
:failedWrite
  onLinux = system.linux()
  if onLinux linuxCode windowsCode
:linuxCode
  clibrary.setErrno(status)
  return false
:windowsCode
  calc mapped = clibrary.windowsErrno(status)
  clibrary.setErrno(mapped)
  return false

op rawRead "Read up to a number of bytes from a handle: how many (0 at the end of the file), or -1 (errno set)"
  input handle Int64 copied
  input buffer machine.Address copied
  input bytes Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let nothing Int64 0
  let failure Int64 -1
:begin
  onLinux = system.linux()
  if onLinux linux windows
:linux
  result = system.read(handle, buffer, bytes)
  when result < 0 linuxFailed linuxRead
:linuxFailed
  setLinuxErrno(result)
  return failure
:linuxRead
  return result
:windows
  countCell = kernel.stateAt(byteAt)
  calc target = machine.fromInt64(handle)
  calc asked = clibrary.lowInt32(lowest(bytes, 1073741824))
  nowhere = machine.zero()
  machine.storeInt32(countCell, 0)
  ok = system.readFile(target, buffer, asked, countCell, nowhere)
  when ok == 0 windowsFailed windowsRead
:windowsFailed
  code = system.getLastError()
  when code == 109 || code == 38 ended windowsError
:ended
  return nothing
:windowsError
  calc mapped = clibrary.windowsErrno(code)
  clibrary.setErrno(mapped)
  return failure
:windowsRead
  readCount = machine.loadInt32(countCell)
  calc gotten = convert.int32ToInt64(readCount)
  return gotten

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

op isTerminal "Whether a handle is a terminal: TCGETS works on it on Linux, GetFileType says FILE_TYPE_CHAR on Windows"
  input handle Int64 copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  onLinux = system.linux()
  if onLinux linux windows
:linux
  settings = heap.take(64)
  result = system.ioctl(handle, 21505, settings)
  heap.give(settings)
  calc terminal = result == 0
  return terminal
:windows
  calc target = machine.fromInt64(handle)
  kind = system.getFileType(target)
  calc character = kind == 2
  return character

op blockSize "The buffer a fully buffered stream gets: the file's st_blksize on Linux (8192 when it says none), 4096 on Windows"
  input handle Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let fallback Int64 8192
  let windowsSize Int64 4096
:begin
  onLinux = system.linux()
  if onLinux linux windows
:linux
  status = heap.take(160)
  result = system.fstat(handle, status)
  calc sizeAt = status + 56
  size = machine.loadInt32(sizeAt)
  heap.give(status)
  when result == 0 && size > 0 given noneCase
:given
  calc wide = convert.int32ToInt64(size)
  return wide
:noneCase
  return fallback
:windows
  return windowsSize

op seekHandle "Move a handle's file position (whence 0 from the start, 1 from here, 2 from the end): the new position, or -1 (errno set: ESPIPE for a pipe or terminal)"
  input handle Int64 copied
  input offset Int64 copied
  input whence Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let failure Int64 -1
:begin
  onLinux = system.linux()
  if onLinux linux windows
:linux
  result = system.lseek(handle, offset, whence)
  when result < 0 linuxFailed linuxDone
:linuxFailed
  setLinuxErrno(result)
  return failure
:linuxDone
  return result
:windows
  calc target = machine.fromInt64(handle)
  kind = system.getFileType(target)
  when kind == 1 disk notDisk
:notDisk
  clibrary.setErrno(29)
  return failure
:disk
  cell = heap.take(8)
  calc method = clibrary.lowInt32(whence)
  ok = system.setFilePointerEx(target, offset, cell, method)
  position = machine.loadInt64(cell)
  heap.give(cell)
  when ok == 0 windowsFailed windowsDone
:windowsFailed
  setWindowsErrno()
  return failure
:windowsDone
  return position

op closeHandle "Close a handle: whether it worked (errno set when not)"
  input handle Int64 copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  onLinux = system.linux()
  if onLinux linux windows
:linux
  result = system.close(handle)
  when result < 0 linuxFailed closedOk
:linuxFailed
  setLinuxErrno(result)
  return false
:windows
  calc target = machine.fromInt64(handle)
  ok = system.closeHandle(target)
  when ok == 0 windowsFailed closedOk
:windowsFailed
  setWindowsErrno()
  return false
:closedOk
  return true

op standardHandle "The handle of standard input (0), output (1), or error (2): the descriptor on Linux, GetStdHandle's on Windows"
  input which Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  onLinux = system.linux()
  if onLinux linux windows
:linux
  return which
:windows
  calc code = clibrary.lowInt32(-10 - which)
  handle = system.getStdHandle(code)
  value = machine.toInt64(handle)
  return value

## ---------------------------------------------------------------- the standard streams and buffers

op standardStream "Fill in a standard stream's FILE: its flags and its handle"
  input offset Int64 copied
  input flags Int64 copied
  input which Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  stream = kernel.stateAt(offset)
  machine.fill(stream, 0, 128)
  machine.storeInt64(stream, flags)
  handle = standardHandle(which)
  setField(stream, 8, handle)
  return

op ensureStandard "Make the standard streams ready, once: stdin readable, stdout writable, stderr writable and unbuffered; the data symbols point at them, and the runtime will flush them at the end"
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let flushName String "fflush"
:begin
  readyCell = kernel.stateAt(readyAt)
  ready = machine.loadInt64(readyCell)
  when ready == 0 prepare done
:prepare
  machine.storeInt64(readyCell, 1)
  standardStream(stdinFileAt, readable, 0)
  standardStream(stdoutFileAt, writable, 1)
  calc errorFlags = writable | unbuffered | decided
  standardStream(stderrFileAt, errorFlags, 2)
  clibrary.prepare()
  flushNameAt = machine.addressOfString(flushName)
  flush = clibrary.lookup(flushNameAt, 6)
  hookCell = kernel.stateAt(hookAt)
  machine.storeAddress(hookCell, flush)
  goto done
:done
  return

op stdoutStream "stdout's FILE, made ready"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  ensureStandard()
  stream = kernel.stateAt(stdoutFileAt)
  return stream

op stdinStream "stdin's FILE, made ready"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  ensureStandard()
  stream = kernel.stateAt(stdinFileAt)
  return stream

op stderrStream "stderr's FILE, made ready"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  ensureStandard()
  stream = kernel.stateAt(stderrFileAt)
  return stream

op decideBuffer "Give a stream its buffer the first time it reads or writes, unless setvbuf did: a terminal is line buffered (1024 bytes), anything else fully buffered (its block size); an unbuffered stream gets one byte to read through"
  input stream machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let size Int64 1 mut
:begin
  isDecided = hasFlag(stream, decided)
  if isDecided bufferCheck decide
:decide
  addFlag(stream, decided)
  handle = field(stream, 8)
  terminal = isTerminal(handle)
  if terminal line full
:line
  addFlag(stream, lineBuffered)
  calc size := 1024
  goto allocate
:full
  calc size := blockSize(handle)
  goto allocate
:bufferCheck
  buffer = field(stream, 16)
  when buffer == 0 oneByte done
:oneByte
  calc size := 1
  goto allocate
:allocate
  block = heap.take(size)
  calc blockValue = machine.toInt64(block)
  setField(stream, 16, blockValue)
  setField(stream, 24, size)
  addFlag(stream, ownBuffer)
  goto done
:done
  return

op flushPendingHeld "Write the bytes waiting in a stream's buffer: 0, or -1 when the write fails (the error flag set)"
  input stream machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let fine Int32 0
  let failure Int32 -1
:begin
  pending = field(stream, 48)
  when pending > 0 write nothingWaiting
:nothingWaiting
  return fine
:write
  setField(stream, 48, 0)
  appendMode = hasFlag(stream, appending)
  onLinux = system.linux()
  calc seekFirst = appendMode && !onLinux
  handle = field(stream, 8)
  if seekFirst toEnd writeIt
:toEnd
  seekHandle(handle, 0, 2)
  goto writeIt
:writeIt
  bufferValue = field(stream, 16)
  buffer = machine.fromInt64(bufferValue)
  wrote = rawWrite(handle, buffer, pending)
  if wrote written writeFailed
:written
  return fine
:writeFailed
  addFlag(stream, failed)
  return failure

op dropReadAhead "Give back what a stream read ahead: move the file back over the bytes buffered and pushed back that were not read, and forget them"
  input stream machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  kind = field(stream, 88)
  position = field(stream, 32)
  ending = field(stream, 40)
  pushed = field(stream, 56)
  calc unread = ending - position + pushed
  setField(stream, 32, 0)
  setField(stream, 40, 0)
  setField(stream, 56, 0)
  when unread > 0 && kind == 0 seekBack done
:seekBack
  handle = field(stream, 8)
  seekHandle(handle, 0 - unread, 1)
  goto done
:done
  return

op putBytesHeld "Write bytes to a stream as its buffering says: how many were taken (all of them, or 0 when the stream cannot be written or the write fails, errno set)"
  input stream machine.Address copied
  input data machine.Address copied
  input bytes Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let done Int64 0 mut
  let nothing Int64 0
:begin
  canWrite = hasFlag(stream, writable)
  if canWrite prepare refuse
:refuse
  addFlag(stream, failed)
  clibrary.setErrno(badFile)
  return nothing
:prepare
  ending = field(stream, 40)
  pushed = field(stream, 56)
  when ending > 0 || pushed > 0 dropRead decide
:dropRead
  dropReadAhead(stream)
  goto decide
:decide
  decideBuffer(stream)
  direct = hasFlag(stream, unbuffered)
  if direct writeDirect copyLoop
:writeDirect
  handle = field(stream, 8)
  wrote = rawWrite(handle, data, bytes)
  if wrote allTaken directFailed
:directFailed
  addFlag(stream, failed)
  return nothing
:copyLoop loop=while max=forever
  when done >= bytes lineCheck copyChunk
:copyChunk in=copyLoop
  size = field(stream, 24)
  pending = field(stream, 48)
  calc room = size - pending
  when room == 0 flushFull copyIn
:flushFull in=copyLoop
  flushed = flushPending(stream)
  when flushed == 0 copyLoop chunkFailed
:copyIn in=copyLoop
  calc chunk = lowest(room, bytes - done)
  bufferValue = field(stream, 16)
  calc target = machine.fromInt64(bufferValue) + pending
  calc source = data + done
  machine.copy(target, source, chunk)
  setField(stream, 48, pending + chunk)
  calc done := done + chunk
  goto copyLoop
:chunkFailed
  return nothing
:lineCheck
  isLine = hasFlag(stream, lineBuffered)
  if isLine findLine allTaken
:findLine
  nowhere = machine.zero()
  found = clibrary.memoryFind(data, 10, bytes)
  calc hasLine = found != nowhere
  if hasLine flushLine allTaken
:flushLine
  lineFlushed = flushPending(stream)
  when lineFlushed == 0 allTaken chunkFailed
:allTaken
  return bytes

op fillBuffer "Read into a stream's empty buffer: how many bytes came (0 at the end, -1 for an error, the stream's flags set)"
  input stream machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let nothing Int64 0
  let failure Int64 -1
:begin
  kind = field(stream, 88)
  when kind == 1 stringEnd fileRead
:stringEnd
  addFlag(stream, atEnd)
  return nothing
:fileRead
  pending = field(stream, 48)
  when pending > 0 flushFirst lineFlush
:flushFirst
  flushPending(stream)
  goto lineFlush
:lineFlush
  decideBuffer(stream)
  interactive = hasFlag(stream, lineBuffered | unbuffered)
  if interactive flushOut readIt
:flushOut
  out = stdoutStream()
  outLine = hasFlag(out, lineBuffered)
  if outLine flushStdout readIt
:flushStdout
  flushPending(out)
  goto readIt
:readIt
  handle = field(stream, 8)
  bufferValue = field(stream, 16)
  buffer = machine.fromInt64(bufferValue)
  size = field(stream, 24)
  count = rawRead(handle, buffer, size)
  setField(stream, 32, 0)
  when count > 0 gotBytes noBytes
:gotBytes
  setField(stream, 40, count)
  return count
:noBytes
  setField(stream, 40, 0)
  when count == 0 ended readFailed
:ended
  addFlag(stream, atEnd)
  return nothing
:readFailed
  addFlag(stream, failed)
  return failure

op getByteHeld "Read one byte from a stream as an unsigned char, or -1 (EOF) at the end or on an error; what ungetc pushed back comes first, and the end of file stays once reached"
  input stream machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let endOfFile Int64 -1
:begin
  pushed = field(stream, 56)
  when pushed > 0 popBack buffered
:popBack
  calc last = pushed - 1
  setField(stream, 56, last)
  calc backAt = stream + 64 + last
  back = machine.loadByte(backAt)
  calc backValue = convert.byteToInt64(back)
  return backValue
:buffered
  position = field(stream, 32)
  ending = field(stream, 40)
  when position < ending take empty
:empty
  canRead = hasFlag(stream, readable)
  if canRead endCheck refuse
:refuse
  addFlag(stream, failed)
  clibrary.setErrno(badFile)
  return endOfFile
:endCheck
  ended = hasFlag(stream, atEnd)
  if ended giveEnd fill
:fill
  count = fillBuffer(stream)
  when count > 0 takeFresh giveEnd
:takeFresh
  freshValue = field(stream, 16)
  freshAt = machine.fromInt64(freshValue)
  fresh = machine.loadByte(freshAt)
  setField(stream, 32, 1)
  calc freshByte = convert.byteToInt64(fresh)
  return freshByte
:take
  bufferValue = field(stream, 16)
  calc at = machine.fromInt64(bufferValue) + position
  value = machine.loadByte(at)
  setField(stream, 32, position + 1)
  calc valueByte = convert.byteToInt64(value)
  return valueByte
:giveEnd
  return endOfFile

op ungetByteHeld "ungetc: push a byte back onto a stream (8 at most), clearing its end of file; gives the byte, or EOF for EOF or when there is no room"
  input stream machine.Address copied
  input value Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let endOfFile Int64 -1
:begin
  when value == -1 refuse room
:room
  pushed = field(stream, 56)
  when pushed >= 8 refuse push
:push
  calc low = value & 255
  calc backAt = stream + 64 + pushed
  machine.storeByte(backAt, convert.int64ToByte(low))
  setField(stream, 56, pushed + 1)
  dropFlag(stream, atEnd)
  return low
:refuse
  return endOfFile

op flushAllHeld "fflush(NULL): write what every stream holds, the standard ones and those fopen opened; 0, or -1 when a write failed"
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let status Int32 0 mut
  let current machine.Address unset mut
:begin
  readyCell = kernel.stateAt(readyAt)
  ready = machine.loadInt64(readyCell)
  when ready == 0 done standard
:standard
  out = kernel.stateAt(stdoutFileAt)
  outStatus = flushPending(out)
  errorStream = kernel.stateAt(stderrFileAt)
  errorStatus = flushPending(errorStream)
  calc status := outStatus | errorStatus
  listCell = kernel.stateAt(listAt)
  calc current := machine.loadAddress(listCell)
  goto eachStream
:eachStream loop=while max=forever
  nowhere = machine.zero()
  when current == nowhere done flushOne
:flushOne in=eachStream
  oneStatus = flushPending(current)
  calc status := status | oneStatus
  nextValue = field(current, 80)
  calc current := machine.fromInt64(nextValue)
  goto eachStream
:done
  return status

## ---------------------------------------------------------------- opening and closing

op modeCode "Read fopen's mode: the stream's flags (readable, writable, appending) and, from bit 16, create, truncate, exclusive (`x`), close on exec (`e`); -1 for a mode that starts with neither r, w, nor a"
  input mode machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let code Int64 0 mut
  let at Int64 1 mut
  let bad Int64 -1
:begin
  first = clibrary.byteAt(mode, 0)
  when first == 114 reading notReading
:reading
  calc code := readable
  goto rest
:notReading
  when first == 119 writing notWriting
:writing
  calc code := writable | 65536 | 131072
  goto rest
:notWriting
  when first == 97 appendingMode refuse
:appendingMode
  calc code := writable | appending | 65536
  goto rest
:refuse
  clibrary.setErrno(invalid)
  return bad
:rest loop=while max=forever
  letter = clibrary.byteAt(mode, at)
  when letter == 0 finish plusCheck
:plusCheck in=rest
  when letter == 43 plus exclusiveCheck
:plus in=rest
  calc code := code | readable | writable
  goto advance
:exclusiveCheck in=rest
  when letter == 120 exclusive execCheck
:exclusive in=rest
  calc code := code | 262144
  goto advance
:execCheck in=rest
  when letter == 101 closeOnExec advance
:closeOnExec in=rest
  calc code := code | 524288
  goto advance
:advance in=rest
  calc at := at + 1
  goto rest
:finish
  return code

op openPath "Open a file for a mode code: its handle, or -1 (errno set)"
  input path machine.Address copied
  input code Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let flags Int64 0 mut
  let access Int32 0 mut
  let disposition Int32 3 mut
  let failure Int64 -1
:begin
  calc both = (code & 3) == 3
  calc writeOnly = (code & 3) == 2
  onLinux = system.linux()
  if onLinux linux windows
:linux
  when both linuxBoth linuxOne
:linuxBoth
  calc flags := 2
  goto linuxRest
:linuxOne
  when writeOnly linuxWrite linuxRest
:linuxWrite
  calc flags := 1
  goto linuxRest
:linuxRest
  calc create = (code & 65536) != 0
  calc truncate = (code & 131072) != 0
  calc exclusive = (code & 262144) != 0
  calc appendTo = (code & appending) != 0
  calc closeOnExec = (code & 524288) != 0
  calc flags := flags | choose(create, 64) | choose(truncate, 512) | choose(exclusive, 128)
  calc flags := flags | choose(appendTo, 1024) | choose(closeOnExec, 524288)
  result = system.openat(-100, path, flags, 438)
  when result < 0 linuxFailed linuxOpened
:linuxFailed
  setLinuxErrno(result)
  return failure
:linuxOpened
  return result
:windows
  calc wantRead = (code & readable) != 0
  calc wantWrite = (code & writable) != 0
  when wantRead && wantWrite windowsBoth windowsOne
:windowsBoth
  calc access := -1073741824
  goto windowsDisposition
:windowsOne
  when wantWrite windowsWrite windowsRead
:windowsWrite
  calc access := 1073741824
  goto windowsDisposition
:windowsRead
  calc access := -2147483648
  goto windowsDisposition
:windowsDisposition
  calc truncates = (code & 131072) != 0
  calc creates = (code & 65536) != 0
  calc exclusiveCreate = (code & 262144) != 0
  when exclusiveCreate createNew notNew
:createNew
  calc disposition := 1
  goto windowsOpen
:notNew
  when truncates createAlways notTruncate
:createAlways
  calc disposition := 2
  goto windowsOpen
:notTruncate
  when creates openAlways windowsOpen
:openAlways
  calc disposition := 4
  goto windowsOpen
:windowsOpen
  length = clibrary.cStringLength(path)
  widePath = wide.widen(path, length)
  nowhere = machine.zero()
  handle = system.createFileW(widePath, access, 7, nowhere, disposition, 128, nowhere)
  heap.give(widePath)
  handleValue = machine.toInt64(handle)
  when handleValue == -1 windowsFailed windowsOpened
:windowsFailed
  setWindowsErrno()
  return failure
:windowsOpened
  return handleValue

op choose "A value when a condition holds, else 0"
  input condition Bool copied
  input value Int64 copied
  output Int64
  let zero Int64 0
:begin
  if condition give noneCase
:give
  return value
:noneCase
  return zero

op newStream "A new FILE for an open handle, with the flags of a mode code, first in the list of streams fflush(NULL) flushes"
  input handle Int64 copied
  input code Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  stream = heap.take(128)
  calc flags = code & 7
  machine.storeInt64(stream, flags)
  setField(stream, 8, handle)
  listCell = kernel.stateAt(listAt)
  first = machine.loadAddress(listCell)
  calc firstValue = machine.toInt64(first)
  setField(stream, 80, firstValue)
  machine.storeAddress(listCell, stream)
  return stream

op unlinkStream "Take a stream out of the list of streams fopen opened"
  input stream machine.Address copied
  effect use machine.memory
  uses memoryAccess
  let previous machine.Address unset mut
  let current machine.Address unset mut
:begin
  listCell = kernel.stateAt(listAt)
  first = machine.loadAddress(listCell)
  nowhere = machine.zero()
  set previous nowhere
  set current first
  goto eachStream
:eachStream loop=while max=forever
  when current == nowhere done check
:check in=eachStream
  when current == stream found next
:next in=eachStream
  set previous current
  nextValue = field(current, 80)
  calc current := machine.fromInt64(nextValue)
  goto eachStream
:found
  after = field(stream, 80)
  when previous == nowhere head middle
:head
  calc afterAddress = machine.fromInt64(after)
  machine.storeAddress(listCell, afterAddress)
  return
:middle
  setField(previous, 80, after)
  return
:done
  return

op openFile "fopen: open a file with a mode (r, w, a, each with +, b, x, e): its FILE, or NULL (errno set)"
  input path machine.Address copied
  input mode machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fopen"
:begin
  ensureStandard()
  nowhere = machine.zero()
  code = modeCode(mode)
  when code < 0 refuse open
:open
  handle = openPath(path, code)
  when handle < 0 refuse made
:made
  stream = newStream(handle, code)
  return stream
:refuse
  return nowhere

op releaseBuffer "Give back a stream's own buffer"
  input stream machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  owned = hasFlag(stream, ownBuffer)
  if owned give done
:give
  bufferValue = field(stream, 16)
  calc buffer = machine.fromInt64(bufferValue)
  heap.give(buffer)
  setField(stream, 16, 0)
  dropFlag(stream, ownBuffer | decided)
  goto done
:done
  return

op isStandard "Whether a FILE is one of the standard streams' blocks in machine.state"
  input stream machine.Address copied
  output Bool
  effect use machine.memory
  uses memoryAccess
:begin
  first = kernel.stateAt(stdinFileAt)
  last = kernel.stateAt(stderrFileAt)
  calc standard = !(stream < first) && !(last < stream)
  return standard

op closeFile "fclose: write what the stream holds, close its file, and free it: 0, or EOF when the write or the close failed"
  input stream machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fclose"
  let fine Int32 0
  let endOfFile Int32 -1
:begin
  ensureStandard()
  flushed = flushPending(stream)
  handle = field(stream, 8)
  closedFine = closeHandle(handle)
  releaseBuffer(stream)
  standard = isStandard(stream)
  if standard markClosed free
:markClosed
  machine.storeInt64(stream, closed)
  goto status
:free
  unlinkStream(stream)
  heap.give(stream)
  goto status
:status
  when flushed == 0 && closedFine good bad
:good
  return fine
:bad
  return endOfFile

op reopenFile "freopen: close a stream's file and open another with a mode in the same FILE (a NULL path keeps the file and takes the mode's flags): the FILE, or NULL (errno set)"
  input path machine.Address copied
  input mode machine.Address copied
  input stream machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "freopen"
:begin
  ensureStandard()
  setField(stream, 96, 0)
  nowhere = machine.zero()
  code = modeCode(mode)
  when code < 0 refuse flush
:flush
  flushPending(stream)
  dropReadAhead(stream)
  calc keep = path == nowhere
  if keep sameFile otherFile
:sameFile
  calc keptFlags = code & 7
  machine.storeInt64(stream, keptFlags)
  return stream
:otherFile
  oldHandle = field(stream, 8)
  closeHandle(oldHandle)
  releaseBuffer(stream)
  handle = openPath(path, code)
  when handle < 0 refuse reuse
:reuse
  calc flags = code & 7
  machine.storeInt64(stream, flags)
  setField(stream, 8, handle)
  setField(stream, 32, 0)
  setField(stream, 40, 0)
  setField(stream, 48, 0)
  setField(stream, 56, 0)
  return stream
:refuse
  return nowhere

op flushStream "fflush: write what a stream holds (every stream for NULL); a stream being read gives back what it read ahead: 0, or EOF when a write failed"
  input stream machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fflush"
  let fine Int32 0
  let endOfFile Int32 -1
:begin
  ensureStandard()
  nowhere = machine.zero()
  when stream == nowhere every one
:every
  status = flushAll()
  when status == 0 good bad
:one
  oneStatus = flushPending(stream)
  ending = field(stream, 40)
  pushed = field(stream, 56)
  when ending > 0 || pushed > 0 dropRead checked
:dropRead
  dropReadAhead(stream)
  goto checked
:checked
  when oneStatus == 0 good bad
:good
  return fine
:bad
  return endOfFile

## ---------------------------------------------------------------- characters and blocks

op putOne "Write one byte to a stream: the byte as an unsigned char, or EOF"
  input stream machine.Address copied
  input value Int32 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let endOfFile Int32 -1
:begin
  ensureStandard()
  orient(stream, -1)
  cell = kernel.stateAt(byteAt)
  calc low = clibrary.charOf(value)
  machine.storeByte(cell, low)
  taken = putBytes(stream, cell, 1)
  when taken == 1 wrote refuse
:wrote
  calc result = clibrary.lowInt32(convert.byteToInt64(low))
  return result
:refuse
  return endOfFile

op putCharacterOn "fputc: write a character to a stream"
  input value Int32 copied
  input stream machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fputc"
:begin
  result = putOne(stream, value)
  return result

op putCharacterStream "putc: fputc"
  input value Int32 copied
  input stream machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "putc"
:begin
  result = putOne(stream, value)
  return result

op putCharacter "putchar: write a character to stdout"
  input value Int32 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "putchar"
:begin
  out = stdoutStream()
  result = putOne(out, value)
  return result

op putStream "fputs: write a C string to a stream: a nonnegative number, or EOF"
  input text machine.Address copied
  input stream machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fputs"
  let endOfFile Int32 -1
:begin
  ensureStandard()
  orientation = orient(stream, -1)
  when orientation != -1 wrongOrientation byteOriented
:wrongOrientation
  return endOfFile
:byteOriented
  length = clibrary.cStringLength(text)
  taken = putBytes(stream, text, length)
  when taken == length wrote refuse
:wrote
  calc result = clibrary.lowInt32(lowest(length, 2147483647))
  return result
:refuse
  return endOfFile

op putString "puts: a C string and a line feed on stdout: a nonnegative number, or EOF"
  input text machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "puts"
  let endOfFile Int32 -1
:begin
  out = stdoutStream()
  orientation = orient(out, -1)
  when orientation != -1 wrongOrientation byteOriented
:wrongOrientation
  return endOfFile
:byteOriented
  length = clibrary.cStringLength(text)
  taken = putBytes(out, text, length)
  when taken == length line refuse
:line
  ended = putOne(out, 10)
  when ended == 10 wrote refuse
:wrote
  calc result = clibrary.lowInt32(lowest(length + 1, 2147483647))
  return result
:refuse
  return endOfFile

op writeItems "fwrite: write a count of items of a size to a stream: how many items were written"
  input data machine.Address copied
  input size Int64 copied
  input count Int64 copied
  input stream machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fwrite"
  let nothing Int64 0
:begin
  ensureStandard()
  orientation = orient(stream, -1)
  when orientation != -1 wrongOrientation byteOriented
:wrongOrientation
  return nothing
:byteOriented
  when size == 0 || count == 0 noneCase some
:some
  calc bytes = math.wrappingMultiplyInt64(size, count)
  taken = putBytes(stream, data, bytes)
  calc items = taken / size
  return items
:noneCase
  return nothing

op getOne "fgetc: read a character from a stream as an unsigned char, or EOF"
  input stream machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fgetc"
:begin
  ensureStandard()
  orient(stream, -1)
  value = getByte(stream)
  calc result = clibrary.lowInt32(value)
  return result

op getCharacterStream "getc: fgetc"
  input stream machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "getc"
:begin
  ensureStandard()
  value = getByte(stream)
  calc result = clibrary.lowInt32(value)
  return result

op getCharacter "getchar: read a character from stdin"
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "getchar"
:begin
  inStream = stdinStream()
  value = getByte(inStream)
  calc result = clibrary.lowInt32(value)
  return result

op ungetCharacter "ungetc: push a character back onto a stream"
  input value Int32 copied
  input stream machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "ungetc"
:begin
  ensureStandard()
  calc wide = convert.int32ToInt64(value)
  pushed = ungetByte(stream, wide)
  calc result = clibrary.lowInt32(pushed)
  return result

op getLine "fgets: read a line (its line feed kept) of at most n-1 bytes into a buffer and end it with 0: the buffer, or NULL when the end came before any byte or a read failed"
  input buffer machine.Address copied
  input limit Int32 copied
  input stream machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fgets"
  let count Int64 0 mut
:begin
  ensureStandard()
  orient(stream, -1)
  nowhere = machine.zero()
  calc most = convert.int32ToInt64(limit) - 1
  when most < 0 refuse eachByte
:eachByte loop=while max=forever
  when count >= most finish read
:read in=eachByte
  value = getByte(stream)
  when value < 0 ended store
:store in=eachByte
  calc at = buffer + count
  machine.storeByte(at, convert.int64ToByte(value))
  calc count := count + 1
  when value == 10 finish eachByte
:ended
  readFailed = hasFlag(stream, failed)
  when count == 0 || readFailed refuse finish
:finish
  calc endAt = buffer + count
  machine.storeByte(endAt, 0)
  return buffer
:refuse
  return nowhere

op readItems "fread: read a count of items of a size from a stream: how many whole items were read"
  input data machine.Address copied
  input size Int64 copied
  input count Int64 copied
  input stream machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fread"
  let done Int64 0 mut
  let nothing Int64 0
:begin
  ensureStandard()
  orient(stream, -1)
  when size == 0 || count == 0 noneCase prepare
:prepare
  calc bytes = math.wrappingMultiplyInt64(size, count)
  pending = field(stream, 48)
  when pending > 0 flushFirst eachChunk
:flushFirst
  flushPending(stream)
  goto eachChunk
:eachChunk loop=while max=forever
  when done >= bytes finish chunk
:chunk in=eachChunk
  pushed = field(stream, 56)
  position = field(stream, 32)
  ending = field(stream, 40)
  when pushed > 0 pushedByte buffered
:pushedByte in=eachChunk
  single = getByte(stream)
  calc singleAt = data + done
  machine.storeByte(singleAt, convert.int64ToByte(single))
  calc done := done + 1
  goto eachChunk
:buffered in=eachChunk
  when position < ending copyOut refill
:copyOut in=eachChunk
  calc chunkBytes = lowest(ending - position, bytes - done)
  bufferValue = field(stream, 16)
  calc source = machine.fromInt64(bufferValue) + position
  calc target = data + done
  machine.copy(target, source, chunkBytes)
  setField(stream, 32, position + chunkBytes)
  calc done := done + chunkBytes
  goto eachChunk
:refill in=eachChunk
  first = getByte(stream)
  when first < 0 finish keepFirst
:keepFirst in=eachChunk
  calc firstAt = data + done
  machine.storeByte(firstAt, convert.int64ToByte(first))
  calc done := done + 1
  goto eachChunk
:finish
  calc items = done / size
  return items
:noneCase
  return nothing

## ---------------------------------------------------------------- positions and status

op seekStream "fseek: write what waits, forget what was read ahead (a move from here counts it), move the file, and clear end of file: 0, or -1 (errno set)"
  input stream machine.Address copied
  input offset Int64 copied
  input whence Int32 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fseek"
  let fine Int32 0
  let failure Int32 -1
  let distance Int64 0 mut
:begin
  ensureStandard()
  when whence < 0 || whence > 2 refuse flush
:refuse
  clibrary.setErrno(invalid)
  return failure
:flush
  flushed = flushPending(stream)
  when flushed != 0 failedSeek adjust
:adjust
  set distance offset
  position = field(stream, 32)
  ending = field(stream, 40)
  pushed = field(stream, 56)
  when whence == 1 fromHere move
:fromHere
  calc distance := offset - (ending - position + pushed)
  goto move
:move
  setField(stream, 32, 0)
  setField(stream, 40, 0)
  setField(stream, 56, 0)
  handle = field(stream, 8)
  calc whenceWide = convert.int32ToInt64(whence)
  moved = seekHandle(handle, distance, whenceWide)
  when moved < 0 failedSeek done
:done
  dropFlag(stream, atEnd)
  return fine
:failedSeek
  return failure

op tellStream "ftell: where the stream is: the file's position less what was read ahead and pushed back, plus what waits to be written; -1 (errno set) when the file cannot say"
  input stream machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "ftell"
  let failure Int64 -1
:begin
  ensureStandard()
  handle = field(stream, 8)
  here = seekHandle(handle, 0, 1)
  when here < 0 refuse count
:count
  position = field(stream, 32)
  ending = field(stream, 40)
  pushed = field(stream, 56)
  pending = field(stream, 48)
  calc place = here - (ending - position) - pushed + pending
  when place < 0 negative fine
:negative
  clibrary.setErrno(invalid)
  return failure
:fine
  return place
:refuse
  return failure

op getPosition "fgetpos: store ftell's position in an fpos_t (glibc's: the offset, then a zeroed mbstate_t): 0, or -1"
  input stream machine.Address copied
  input position machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fgetpos"
  let fine Int32 0
  let failure Int32 -1
:begin
  place = tellStream(stream)
  when place < 0 refuse store
:store
  machine.storeInt64(position, place)
  calc stateAt = position + 8
  machine.storeInt64(stateAt, 0)
  return fine
:refuse
  return failure

op setPosition "fsetpos: move a stream to where an fpos_t says: 0, or -1"
  input stream machine.Address copied
  input position machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fsetpos"
:begin
  place = machine.loadInt64(position)
  result = seekStream(stream, place, 0)
  return result

op rewindStream "rewind: fseek to the start and clear the error flag"
  input stream machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "rewind"
:begin
  seekStream(stream, 0, 0)
  dropFlag(stream, failed)
  return

op streamAtEnd "feof: whether a stream reached its end (nonzero)"
  input stream machine.Address copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "feof"
:begin
  ended = hasFlag(stream, atEnd)
  calc result = clibrary.lowInt32(choose(ended, 1))
  return result

op errorOf "ferror: whether a read or write of a stream failed (nonzero)"
  input stream machine.Address copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "ferror"
:begin
  failedOnce = hasFlag(stream, failed)
  calc result = clibrary.lowInt32(choose(failedOnce, 1))
  return result

op clearErrors "clearerr: clear a stream's end of file and error"
  input stream machine.Address copied
  effect use machine.memory
  uses memoryAccess
  abi library "clearerr"
:begin
  dropFlag(stream, atEnd | failed)
  return

op setBuffering "setvbuf: choose a stream's buffering before it is used: _IOFBF (0) full, _IOLBF (1) by line, _IONBF (2) none, with the caller's buffer or one of the stream's own; 0, or nonzero for another mode (errno untouched, as glibc leaves it)"
  input stream machine.Address copied
  input buffer machine.Address copied
  input mode Int32 copied
  input size Int64 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "setvbuf"
  let fine Int32 0
  let failure Int32 -1
  let bytes Int64 0 mut
:begin
  ensureStandard()
  when mode < 0 || mode > 2 refuse release
:refuse
  return failure
:release
  releaseBuffer(stream)
  dropFlag(stream, unbuffered | lineBuffered)
  addFlag(stream, decided)
  when mode == 2 noneCase sized
:noneCase
  addFlag(stream, unbuffered)
  return fine
:sized
  when mode == 1 line keepSize
:line
  addFlag(stream, lineBuffered)
  goto keepSize
:keepSize
  set bytes size
  nowhere = machine.zero()
  when buffer == nowhere own given
:given
  when size <= 0 own useGiven
:useGiven
  calc bufferValue = machine.toInt64(buffer)
  setField(stream, 16, bufferValue)
  setField(stream, 24, bytes)
  return fine
:own
  when bytes <= 0 defaultSize allocate
:defaultSize
  calc bytes := 8192
  goto allocate
:allocate
  block = heap.take(bytes)
  calc blockValue = machine.toInt64(block)
  setField(stream, 16, blockValue)
  setField(stream, 24, bytes)
  addFlag(stream, ownBuffer)
  return fine

op setBuffer "setbuf: setvbuf with a buffer of BUFSIZ (8192) bytes, or no buffering for NULL"
  input stream machine.Address copied
  input buffer machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "setbuf"
:begin
  nowhere = machine.zero()
  when buffer == nowhere noneCase full
:noneCase
  setBuffering(stream, buffer, 2, 0)
  return
:full
  setBuffering(stream, buffer, 0, 8192)
  return

## ---------------------------------------------------------------- files by name

op linuxResult "0 for a system call that worked, else -1 with errno set from its result"
  input result Int64 copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  let fine Int32 0
  let failure Int32 -1
:begin
  when result < 0 refuse good
:good
  return fine
:refuse
  setLinuxErrno(result)
  return failure

op windowsResult "0 for a Windows function that worked (nonzero), else -1 with errno set from GetLastError"
  input ok Int32 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let fine Int32 0
  let failure Int32 -1
:begin
  when ok == 0 refuse good
:good
  return fine
:refuse
  setWindowsErrno()
  return failure

op removeFile "remove: delete a file, or an empty directory: 0, or -1 (errno set)"
  input path machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "remove"
:begin
  onLinux = system.linux()
  if onLinux linux windows
:linux
  result = system.unlinkat(-100, path, 0)
  when result == -21 directory linuxDone
:directory
  removed = system.unlinkat(-100, path, 512)
  directoryStatus = linuxResult(removed)
  return directoryStatus
:linuxDone
  status = linuxResult(result)
  return status
:windows
  length = clibrary.cStringLength(path)
  widePath = wide.widen(path, length)
  deleted = system.deleteFileW(widePath)
  when deleted == 0 tryDirectory windowsDone
:tryDirectory
  directoryGone = system.removeDirectoryW(widePath)
  heap.give(widePath)
  directoryResult = windowsResult(directoryGone)
  return directoryResult
:windowsDone
  heap.give(widePath)
  windowsStatus = windowsResult(deleted)
  return windowsStatus

op renameFile "rename: give a file another name, replacing a file that had it: 0, or -1 (errno set)"
  input oldPath machine.Address copied
  input newPath machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "rename"
:begin
  onLinux = system.linux()
  if onLinux linux windows
:linux
  result = system.renameat2(-100, oldPath, -100, newPath, 0)
  status = linuxResult(result)
  return status
:windows
  oldLength = clibrary.cStringLength(oldPath)
  wideOld = wide.widen(oldPath, oldLength)
  newLength = clibrary.cStringLength(newPath)
  wideNew = wide.widen(newPath, newLength)
  moved = system.moveFileExW(wideOld, wideNew, 1)
  heap.give(wideOld)
  heap.give(wideNew)
  windowsStatus = windowsResult(moved)
  return windowsStatus

op randomBytes "Fill bytes with random values: getrandom on Linux; on Windows a generator seeded from the tick count, which a name only needs to be unlikely"
  input target machine.Address copied
  input bytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let state UInt64 0 mut
:begin
  onLinux = system.linux()
  if onLinux linux windows
:linux
  system.getrandom(target, bytes, 0)
  return
:windows
  seedCell = kernel.stateAt(2344)
  calc state := machine.loadUInt64(seedCell)
  when state == 0 seed eachByte
:seed
  ticks = system.getTickCount64()
  calc state := convert.int64BitsToUInt64(ticks) | 1
  goto eachByte
:eachByte loop=while max=bytes
  when at >= bytes finish next
:next in=eachByte
  calc state := math.wrappingAddUInt64(math.wrappingMultiplyUInt64(state, 6364136223846793005), 1442695040888963407)
  calc randomAt = target + at
  machine.storeByte(randomAt, convert.uint64ToByte(state >> 56))
  calc at := at + 1
  goto eachByte
:finish
  machine.storeUInt64(seedCell, state)
  return

op freeName "Whether no file has a name: newfstatat says ENOENT on Linux, GetFileAttributesW finds nothing on Windows"
  input path machine.Address copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  onLinux = system.linux()
  if onLinux linux windows
:linux
  status = heap.take(160)
  result = system.newfstatat(-100, path, status, 256)
  heap.give(status)
  calc absent = result == -2
  return absent
:windows
  length = clibrary.cStringLength(path)
  widePath = wide.widen(path, length)
  attributes = system.getFileAttributesW(widePath)
  heap.give(widePath)
  calc missing = attributes == -1
  return missing

op makeName "Write a name no file has into a buffer: `/tmp/file` and six letters or digits on Linux (glibc's tmpnam), `file` and six on Windows, in the current directory; whether it found one"
  input buffer machine.Address copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let linuxPrefix String "/tmp/file"
  let windowsPrefix String "file"
  let letters String "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
  let prefixBytes Int64 4 mut
  let tries Int64 0 mut
  let at Int64 0 mut
:begin
  onLinux = system.linux()
  if onLinux linuxName windowsName
:linuxName
  linuxAt = machine.addressOfString(linuxPrefix)
  machine.copy(buffer, linuxAt, 9)
  calc prefixBytes := 9
  goto attempt
:windowsName
  windowsAt = machine.addressOfString(windowsPrefix)
  machine.copy(buffer, windowsAt, 4)
  goto attempt
:attempt loop=while max=forever
  when tries >= 100 giveUp fill
:fill in=attempt
  calc tries := tries + 1
  calc lettersAt = buffer + prefixBytes
  randomBytes(lettersAt, 6)
  set at 0
  goto eachLetter
:eachLetter loop=while max=forever in=attempt
  when at >= 6 check pick
:pick in=eachLetter
  calc letterAt = lettersAt + at
  raw = machine.loadByte(letterAt)
  calc index = convert.byteToInt64(raw) % 62
  calc chosenAt = machine.addressOfString(letters) + index
  chosen = machine.loadByte(chosenAt)
  machine.storeByte(letterAt, chosen)
  calc at := at + 1
  goto eachLetter
:check in=attempt
  calc endAt = buffer + prefixBytes + 6
  machine.storeByte(endAt, 0)
  free = freeName(buffer)
  if free found attempt
:found
  return true
:giveUp
  return false

op temporaryName "tmpnam: a name no file has, in the buffer given (L_tmpnam, 20 bytes) or one of machine.state that the next call replaces; NULL when none was found"
  input buffer machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "tmpnam"
  let target machine.Address unset mut
:begin
  nowhere = machine.zero()
  set target buffer
  when buffer == nowhere own named
:own
  calc target := kernel.stateAt(nameAt)
  goto named
:named
  made = makeName(target)
  if made give refuse
:give
  return target
:refuse
  return nowhere

op temporaryFile "tmpfile: a new file opened `w+b` that is removed when it is closed: on Linux an O_TMPFILE file in /tmp (or a named one removed at once), on Windows a file deleted on close; NULL (errno set) when none could be made"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "tmpfile"
  let tmpDirectory String "/tmp"
  let flags Int64 4259842 mut
:begin
  ensureStandard()
  nowhere = machine.zero()
  calc code = readable | writable
  name = heap.take(64)
  onLinux = system.linux()
  if onLinux linux windows
:linux
  directoryAt = machine.addressOfString(tmpDirectory)
  machine.copy(name, directoryAt, 4)
  onArm = system.aarch64()
  if onArm armFlags open
:armFlags
  calc flags := 4210690
  goto open
:open
  result = system.openat(-100, name, flags, 384)
  when result >= 0 made named
:named
  found = makeName(name)
  if found create refuse
:create
  created = system.openat(-100, name, 194, 384)
  when created < 0 linuxFailed unlink
:linuxFailed
  setLinuxErrno(created)
  goto refuse
:unlink
  system.unlinkat(-100, name, 0)
  heap.give(name)
  namedStream = newStream(created, code)
  return namedStream
:made
  heap.give(name)
  stream = newStream(result, code)
  return stream
:windows
  windowsFound = makeName(name)
  if windowsFound windowsCreate refuse
:windowsCreate
  length = clibrary.cStringLength(name)
  widePath = wide.widen(name, length)
  handle = system.createFileW(widePath, -1073741824, 7, nowhere, 1, 67109120, nowhere)
  heap.give(widePath)
  handleValue = machine.toInt64(handle)
  when handleValue == -1 windowsFailed windowsMade
:windowsFailed
  setWindowsErrno()
  goto refuse
:windowsMade
  heap.give(name)
  windowsStream = newStream(handleValue, code)
  return windowsStream
:refuse
  heap.give(name)
  return nowhere

op printError "perror: write a text, `: `, and strerror of errno, then a line feed, to stderr (the text and `: ` only when the text is not empty)"
  input text machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "perror"
  let separator String ": "
:begin
  message = clibrary.errorMessage()
  errorStream = stderrStream()
  nowhere = machine.zero()
  when text == nowhere describe nonEmpty
:nonEmpty
  first = clibrary.byteAt(text, 0)
  when first == 0 describe prefix
:prefix
  length = clibrary.cStringLength(text)
  putBytes(errorStream, text, length)
  separatorAt = machine.addressOfString(separator)
  putBytes(errorStream, separatorAt, 2)
  goto describe
:describe
  messageLength = clibrary.cStringLength(message)
  putBytes(errorStream, message, messageLength)
  putOne(errorStream, 10)
  return

## ---------------------------------------------------------------- the end of the process

op endProcess "End the process with an exit code: ExitProcess on Windows, exit_group on Linux (D-138)"
  input code Int32 copied
  effect use system.calls
  uses systemCalls
:begin
  onLinux = system.linux()
  if onLinux linuxExit windowsExit
:linuxExit
  calc wideCode = convert.int32ToInt64(code)
  system.exitGroup(wideCode)
  return
:windowsExit
  system.exitProcess(code)
  return

op exitProcess "exit: call the atexit and __cxa_atexit functions, the last registered first, write what every stream holds, then end the process with a status (D-162)"
  input code Int32 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "exit"
:begin
  clibrary.runHandlers(27904)
  flushAll()
  endProcess(code)
  return

## ---------------------------------------------------------------- the printf family

op listFor "The address of a va_list a v-function was handed: on Linux the argument is already its address (an array), on Windows it is the list itself (a pointer), kept in a new cell"
  input list machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  onLinux = system.linux()
  if onLinux linux windows
:linux
  return list
:windows
  cell = heap.take(8)
  machine.storeAddress(cell, list)
  return cell

op releaseList "Give back the cell listFor made on Windows"
  input cell machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  onLinux = system.linux()
  if onLinux done windows
:windows
  heap.give(cell)
  return
:done
  return

op writeFormatted "Format into a stream: the bytes written as an int, or -1 when the format or the write failed"
  input stream machine.Address copied
  input format machine.Address copied
  input list machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let failure Int32 -1
:begin
  ensureStandard()
  orientation = orient(stream, -1)
  when orientation != -1 wrongOrientation byteOriented
:wrongOrientation
  return failure
:byteOriented
  cursor = cformat.cursorNew(list)
  builder = wide.builderNew()
  count = cformat.formatAll(format, cursor, builder)
  text = wide.builderText(builder)
  length = wide.builderLength(builder)
  cformat.cursorFree(cursor)
  when count < 0 refuse write
:write
  taken = putBytes(stream, text, length)
  heap.give(text)
  heap.give(builder)
  when taken == length wrote writeFailed
:wrote
  calc result = clibrary.lowInt32(count)
  return result
:writeFailed
  return failure
:refuse
  heap.give(text)
  heap.give(builder)
  return failure

op storeFormatted "Format into memory: at most limit - 1 bytes and a 0 when limit is 1 or more (a negative limit: no bound); the bytes the whole text has as an int, or -1"
  input target machine.Address copied
  input limit Int64 copied
  input format machine.Address copied
  input list machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let failure Int32 -1
  let kept Int64 0 mut
:begin
  cursor = cformat.cursorNew(list)
  builder = wide.builderNew()
  count = cformat.formatAll(format, cursor, builder)
  text = wide.builderText(builder)
  length = wide.builderLength(builder)
  cformat.cursorFree(cursor)
  set kept length
  when limit == 0 skip bounded
:bounded
  when limit > 0 && length > limit - 1 shorten copy
:shorten
  calc kept := limit - 1
  goto copy
:copy
  machine.copy(target, text, kept)
  calc endAt = target + kept
  machine.storeByte(endAt, 0)
  goto skip
:skip
  heap.give(text)
  heap.give(builder)
  when count < 0 refuse done
:done
  calc result = clibrary.lowInt32(count)
  return result
:refuse
  return failure

op printFormatted "printf: format to stdout"
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "printf" variadic
:begin
  list = machine.variadicStart()
  out = stdoutStream()
  result = writeFormatted(out, format, list)
  return result

op printFormattedTo "fprintf: format to a stream"
  input stream machine.Address copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fprintf" variadic
:begin
  list = machine.variadicStart()
  result = writeFormatted(stream, format, list)
  return result

op printFormattedInto "sprintf: format into memory, with no bound"
  input target machine.Address copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "sprintf" variadic
:begin
  list = machine.variadicStart()
  result = storeFormatted(target, -1, format, list)
  return result

op printFormattedBounded "snprintf: format into memory, at most n - 1 bytes and a 0"
  input target machine.Address copied
  input limit Int64 copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "snprintf" variadic
:begin
  list = machine.variadicStart()
  result = storeFormatted(target, limit, format, list)
  return result

op printList "vprintf: format to stdout from a va_list"
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "vprintf"
:begin
  list = listFor(arguments)
  out = stdoutStream()
  result = writeFormatted(out, format, list)
  releaseList(list)
  return result

op printListTo "vfprintf: format to a stream from a va_list"
  input stream machine.Address copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "vfprintf"
:begin
  list = listFor(arguments)
  result = writeFormatted(stream, format, list)
  releaseList(list)
  return result

op printListInto "vsprintf: format into memory from a va_list, with no bound"
  input target machine.Address copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "vsprintf"
:begin
  list = listFor(arguments)
  result = storeFormatted(target, -1, format, list)
  releaseList(list)
  return result

op printListBounded "vsnprintf: format into memory from a va_list, at most n - 1 bytes and a 0"
  input target machine.Address copied
  input limit Int64 copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "vsnprintf"
:begin
  list = listFor(arguments)
  result = storeFormatted(target, limit, format, list)
  releaseList(list)
  return result

## ---------------------------------------------------------------- scanf's reading
##
## A scanner (a heap block of 24 bytes): 0 the stream, 8 how many bytes it consumed (what %n stores), 16 1 once a
## read found the end of the input or failed. A conversion's text is gathered byte by byte, as long as it can still
## become a number, and read with strtol's or strtod's own code; a byte that ends it goes back with ungetc, so, as
## in glibc, a conversion consumes what it looked at except that last byte.

op scanGet "Read a byte for scanf: its value, or -1 at the end (which is noted)"
  input scanner machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  streamValue = field(scanner, 0)
  stream = machine.fromInt64(streamValue)
  value = getByte(stream)
  when value >= 0 counted ended
:counted
  consumed = field(scanner, 8)
  setField(scanner, 8, consumed + 1)
  return value
:ended
  setField(scanner, 16, 1)
  return value

op scanUnget "Give a byte scanf read back to its stream (nothing for -1)"
  input scanner machine.Address copied
  input value Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  when value >= 0 giveBack done
:giveBack
  streamValue = field(scanner, 0)
  stream = machine.fromInt64(streamValue)
  ungetByte(stream, value)
  consumed = field(scanner, 8)
  setField(scanner, 8, consumed - 1)
  return
:done
  return

op isSpaceValue "Whether a value read (a byte, or -1) is white space in the C locale"
  input value Int64 copied
  output Bool
:begin
  when value >= 0 && value < 256 byteCheck notSpace
:byteCheck
  calc space = clibrary.isSpaceByte(convert.int64ToByte(value))
  return space
:notSpace
  return false

op skipSpace "Read past white space; gives the first other byte, which goes back, or -1 at the end"
  input scanner machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let value Int64 0 mut
:begin
  goto eachByte
:eachByte loop=while max=forever
  calc value := scanGet(scanner)
  space = isSpaceValue(value)
  if space eachByte finish
:finish
  scanUnget(scanner, value)
  return value

op digitValue "The value of a byte read as a digit in a base (the byte -1 and other bytes are 99)"
  input value Int64 copied
  output UInt64
  let notDigit UInt64 99
:begin
  when value >= 0 && value < 256 digit notOne
:digit
  calc found = clibrary.digitOf(convert.int64ToByte(value))
  return found
:notOne
  return notDigit

op lowerValue "A value read with A to Z made a to z"
  input value Int64 copied
  output Int64
:begin
  when value >= 65 && value <= 90 lower keep
:lower
  calc lowered = value + 32
  return lowered
:keep
  return value

op collectInteger "Gather the text of an integer in a base (0 for strtol's choice) into a buffer, at most `width` bytes: a sign, `0x` where the base allows it, digits; gives how many bytes, or -1 when no digit came"
  input scanner machine.Address copied
  input width Int64 copied
  input base Int64 copied
  input buffer machine.Address copied
  input binary Bool copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let count Int64 0 mut
  let value Int64 0 mut
  let digits Int64 0 mut
  let radix Int64 10 mut
  let failure Int64 -1
:begin
  set radix base
  calc value := scanGet(scanner)
  when (value == 43 || value == 45) && count < width sign prefix
:sign
  storeValue(buffer, count, value)
  calc count := count + 1
  calc value := scanGet(scanner)
  goto prefix
:prefix
  when (base == 0 || base == 16 || (binary && base == 2)) && value == 48 && count < width zeroPrefix noPrefix
:zeroPrefix
  storeValue(buffer, count, value)
  calc count := count + 1
  calc digits := digits + 1
  calc value := scanGet(scanner)
  when lowerValue(value) == 120 && count < width && base != 2 hexMark binaryCheck
:binaryCheck
  when binary && lowerValue(value) == 98 && count < width && (base == 0 || base == 2) binaryMark notHex
:binaryMark
  storeValue(buffer, count, value)
  calc count := count + 1
  calc radix := 2
  calc value := scanGet(scanner)
  goto eachDigit
:hexMark
  storeValue(buffer, count, value)
  calc count := count + 1
  calc radix := 16
  calc value := scanGet(scanner)
  goto eachDigit
:notHex
  when base == 0 octal eachDigit
:octal
  calc radix := 8
  goto eachDigit
:noPrefix
  when base == 0 decimal eachDigit
:decimal
  calc radix := 10
  goto eachDigit
:eachDigit loop=while max=forever
  calc digit = digitValue(value)
  when count < width && convert.uint64ToInt64(digit) < radix keep finish
:keep in=eachDigit
  storeValue(buffer, count, value)
  calc count := count + 1
  calc digits := digits + 1
  calc value := scanGet(scanner)
  goto eachDigit
:finish
  scanUnget(scanner, value)
  calc endAt = buffer + count
  machine.storeByte(endAt, 0)
  when digits == 0 refuse done
:done
  return count
:refuse
  return failure

op storeValue "Put a byte read at a position of a buffer"
  input buffer machine.Address copied
  input at Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc place = buffer + at
  machine.storeByte(place, convert.int64ToByte(value & 255))
  return

op matchWord "Gather the bytes of a word (in lower case) as they come in any case, while the width allows: how many matched; the byte after them is left in `pending`"
  input scanner machine.Address copied
  input word String borrowed
  input buffer machine.Address copied
  input count Int64 copied
  input width Int64 copied
  input pending machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let matched Int64 0 mut
  let value Int64 0 mut
:begin
  calc value := machine.loadInt64(pending)
  length = string.byteLength(word)
  wordAt = machine.addressOfString(word)
  goto eachLetter
:eachLetter loop=while max=forever
  when matched >= length || count + matched >= width finish compare
:compare in=eachLetter
  letter = clibrary.byteAt(wordAt, matched)
  when lowerValue(value) == convert.byteToInt64(letter) take finish
:take in=eachLetter
  storeValue(buffer, count + matched, value)
  calc matched := matched + 1
  calc value := scanGet(scanner)
  goto eachLetter
:finish
  machine.storeInt64(pending, value)
  return matched

op collectReal "Gather the text of a floating number into a buffer, at most `width` bytes: a sign, then inf or infinity, nan (glibc's scanf reads no (chars) after it), or a hexadecimal or decimal number with its point and exponent; gives how many bytes, or -1 when what came cannot be a number"
  input scanner machine.Address copied
  input width Int64 copied
  input buffer machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let count Int64 0 mut
  let value Int64 0 mut
  let digits Int64 0 mut
  let radix Int64 10 mut
  let marker Int64 101 mut
  let failure Int64 -1
  let infinityWord String "inf"
  let infinityRest String "inity"
  let nanWord String "nan"
:begin
  pending = heap.take(8)
  calc value := scanGet(scanner)
  when (value == 43 || value == 45) && count < width sign kind
:sign
  storeValue(buffer, count, value)
  calc count := count + 1
  calc value := scanGet(scanner)
  goto kind
:kind
  when lowerValue(value) == 105 infinity notInfinity
:infinity
  machine.storeInt64(pending, value)
  infMatched = matchWord(scanner, infinityWord, buffer, count, width, pending)
  calc count := count + infMatched
  when infMatched == 3 infinityTail wordFailed
:infinityTail
  restMatched = matchWord(scanner, infinityRest, buffer, count, width, pending)
  calc count := count + restMatched
  calc digits := 1
  goto wordDone
:notInfinity
  when lowerValue(value) == 110 notNumber number
:notNumber
  machine.storeInt64(pending, value)
  nanMatched = matchWord(scanner, nanWord, buffer, count, width, pending)
  calc count := count + nanMatched
  when nanMatched == 3 nanDone wordFailed
:nanDone
  calc digits := 1
  goto wordDone
:wordDone
  calc value := machine.loadInt64(pending)
  goto finish
:wordFailed
  calc value := machine.loadInt64(pending)
  calc digits := 0
  goto finish
:number
  when value == 48 && count < width leadingZero whole
:leadingZero
  storeValue(buffer, count, value)
  calc count := count + 1
  calc digits := 1
  calc value := scanGet(scanner)
  when lowerValue(value) == 120 && count < width hexMark whole
:hexMark
  storeValue(buffer, count, value)
  calc count := count + 1
  calc radix := 16
  calc marker := 112
  calc digits := 0
  calc value := scanGet(scanner)
  goto whole
:whole loop=while max=forever
  when count < width && convert.uint64ToInt64(digitValue(value)) < radix wholeDigit point
:wholeDigit in=whole
  storeValue(buffer, count, value)
  calc count := count + 1
  calc digits := digits + 1
  calc value := scanGet(scanner)
  goto whole
:point
  when value == 46 && count < width takePoint exponent
:takePoint
  storeValue(buffer, count, value)
  calc count := count + 1
  calc value := scanGet(scanner)
  goto fraction
:fraction loop=while max=forever
  when count < width && convert.uint64ToInt64(digitValue(value)) < radix fractionDigit exponent
:fractionDigit in=fraction
  storeValue(buffer, count, value)
  calc count := count + 1
  calc digits := digits + 1
  calc value := scanGet(scanner)
  goto fraction
:exponent
  when digits > 0 && lowerValue(value) == marker && count < width takeMarker finish
:takeMarker
  storeValue(buffer, count, value)
  calc count := count + 1
  calc value := scanGet(scanner)
  when (value == 43 || value == 45) && count < width exponentSign power
:exponentSign
  storeValue(buffer, count, value)
  calc count := count + 1
  calc value := scanGet(scanner)
  goto power
:power loop=while max=forever
  when count < width && convert.uint64ToInt64(digitValue(value)) < 10 powerDigit finish
:powerDigit in=power
  storeValue(buffer, count, value)
  calc count := count + 1
  calc value := scanGet(scanner)
  goto power
:finish
  heap.give(pending)
  scanUnget(scanner, value)
  calc endAt = buffer + count
  machine.storeByte(endAt, 0)
  when digits == 0 refuse done
:done
  return count
:refuse
  return failure

op scanSet "Read a %[ scanset that starts at a position of a format (after the `[`) into a table of 256 bytes, 1 for each byte it takes (`^` first takes the others; `]` first is a member; `a-z` is a range); gives the position after its `]`"
  input format machine.Address copied
  input at Int64 copied
  input table machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let place Int64 0 mut
  let negate Bool false mut
  let previous Int64 -1 mut
  let index Int64 0 mut
:begin
  set place at
  machine.fill(table, 0, 256)
  first = clibrary.byteAt(format, place)
  when first == 94 negated firstMember
:negated
  calc negate := true
  calc place := place + 1
  goto firstMember
:firstMember
  member = clibrary.byteAt(format, place)
  when member == 93 bracketMember eachMember
:bracketMember
  markByte(table, 93)
  calc previous := 93
  calc place := place + 1
  goto eachMember
:eachMember loop=while max=forever
  current = clibrary.byteAt(format, place)
  when current == 0 finish notEnd
:notEnd in=eachMember
  when current == 93 closing notClosing
:closing in=eachMember
  calc place := place + 1
  goto finish
:notClosing in=eachMember
  calc following = clibrary.byteAt(format, place + 1)
  when current == 45 && previous >= 0 && following != 93 && following != 0 range single
:range in=eachMember
  calc high = convert.byteToInt64(following)
  calc index := previous
  goto rangeFill
:rangeFill loop=while max=forever in=eachMember
  when index > high rangeDone rangeMark
:rangeMark in=rangeFill
  markByte(table, index)
  calc index := index + 1
  goto rangeFill
:rangeDone in=eachMember
  calc previous := -1
  calc place := place + 2
  goto eachMember
:single in=eachMember
  calc currentValue = convert.byteToInt64(current)
  markByte(table, currentValue)
  set previous currentValue
  calc place := place + 1
  goto eachMember
:finish
  if negate flip done
:flip
  set index 0
  goto flipLoop
:flipLoop loop=while max=forever
  when index >= 256 done flipOne
:flipOne in=flipLoop
  calc flipAt = table + index
  was = machine.loadByte(flipAt)
  calc flipped = 1 - was
  machine.storeByte(flipAt, flipped)
  calc index := index + 1
  goto flipLoop
:done
  return place

op markByte "Mark a byte as a member of a scanset's table"
  input table machine.Address copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc at = table + value
  machine.storeByte(at, 1)
  return

op inSet "Whether a value read (a byte, or -1) is in a scanset's table"
  input table machine.Address copied
  input value Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
:begin
  when value < 0 outside lookUp
:lookUp
  calc at = table + value
  member = machine.loadByte(at)
  calc inside = member == 1
  return inside
:outside
  return false

## ---------------------------------------------------------------- scanf's storing

op storeWhole "Store a whole number where a conversion's argument points, in the size its length gives: hh a char, h a short, none an int, the others 64 bits"
  input target machine.Address copied
  input value Int64 copied
  input length Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  when length == 1 charSize notChar
:charSize
  machine.storeByte(target, convert.int64ToByte(value & 255))
  return
:notChar
  when length == 2 shortSize notShort
:shortSize
  machine.storeByte(target, convert.int64ToByte(value & 255))
  calc highAt = target + 1
  machine.storeByte(highAt, convert.int64ToByte((value >> 8) & 255))
  return
:notShort
  when length == 0 intSize longSize
:intSize
  machine.storeInt32(target, clibrary.lowInt32(value))
  return
:longSize
  machine.storeInt64(target, value)
  return

op narrowReal "A double rounded to a float, overflowing to an infinity as C's conversion does (not trapping)"
  input value Float64 copied
  output Float32
:begin
  calc magnitude = value * choose64(value < 0.0)
  when magnitude >= 0x1.ffffffp127 overflow fits
:overflow
  calc infinite = convert.float64ToFloat32(convert.uint64BitsToFloat64(9218868437227405312) * choose64(value < 0.0))
  return infinite
:fits
  calc narrowed = convert.float64ToFloat32(value)
  return narrowed

op choose64 "-1.0 for true, 1.0 for false: a sign to multiply by"
  input negative Bool copied
  output Float64
  let minusOne Float64 -1.0
  let plusOne Float64 1.0
:begin
  if negative giveMinus givePlus
:giveMinus
  return minusOne
:givePlus
  return plusOne

op storeLongDouble "Store a double as a long double where an argument points: x87's 80 bits on x86_64 Linux, binary128 on AArch64 Linux, a double on Windows; every double is exactly a long double"
  input target machine.Address copied
  input value Float64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let exponent Int64 0 mut
  let significand UInt64 0 mut
  let top UInt64 0 mut
:begin
  machine.fill(target, 0, 16)
  onLinux = system.linux()
  if onLinux linux windows
:windows
  machine.storeFloat64(target, value)
  return
:linux
  bitsOf = convert.float64BitsToUInt64(value)
  calc sign = bitsOf >> 63
  calc biased = convert.uint64ToInt64((bitsOf >> 52) & 2047)
  calc fraction = bitsOf & 4503599627370495
  when biased == 2047 special finite
:special
  calc exponent := 32767
  calc significand := (fraction << 11) | 9223372036854775808
  when fraction != 0 quiet encode
:quiet
  calc significand := significand | 4611686018427387904
  goto encode
:finite
  when biased == 0 && fraction == 0 encode subnormalCheck
:subnormalCheck
  when biased == 0 subnormal normal
:normal
  calc exponent := biased - 1023 + 16383
  calc significand := (fraction << 11) | 9223372036854775808
  goto encode
:subnormal
  calc exponent := 16383 - 1022
  calc significand := fraction << 11
  goto normalize
:normalize loop=while max=forever
  when (significand >> 63) == 1 encode shift
:shift in=normalize
  calc significand := significand << 1
  calc exponent := exponent - 1
  goto normalize
:encode
  calc top := (sign << 15) | convert.int64ToUInt64(exponent)
  onArm = system.aarch64()
  if onArm quad extended
:extended
  machine.storeUInt64(target, significand)
  calc topAt = target + 8
  machine.storeUInt64(topAt, top)
  return
:quad
  calc fractionBits = significand << 1
  calc low = (fractionBits & 65535) << 48
  calc high = (top << 48) | (fractionBits >> 16)
  machine.storeUInt64(target, low)
  calc highAt = target + 8
  machine.storeUInt64(highAt, high)
  return

op storeReal "Store a floating value where a conversion's argument points: none a float, l a double, L a long double"
  input target machine.Address copied
  input value Float64 copied
  input length Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  when length == 0 single notSingle
:single
  machine.storeFloat32(target, narrowReal(value))
  return
:notSingle
  when length == 5 longDouble double
:longDouble
  storeLongDouble(target, value)
  return
:double
  machine.storeFloat64(target, value)
  return

## ---------------------------------------------------------------- scanf's directives

op scanAll "scanf's engine (glibc's __isoc99 forms): match a format against a stream, storing each conversion where the next argument points: white space skips white space, other bytes must match, and %d %i %u %o %x %X %p %c %s %[ %n %a %e %f %g with `*`, a width, and hh h l ll L j z t q; gives how many were stored, or EOF when the input ended before the first was"
  invariant scansLikeGlibc "Conversions read, stop, and count as glibc's scanf in the C locale"
  input stream machine.Address copied
  input format machine.Address copied
  input cursor machine.Address copied
  input c23 Bool copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let place Int64 0 mut
  let assigned Int64 0 mut
  let suppress Bool false mut
  let width Int64 0 mut
  let length Int64 0 mut
  let count Int64 0 mut
  let value Int64 0 mut
  let base Int64 10 mut
  let step Int64 1 mut
  let targetValue Int64 0 mut
  let ended Int32 -1
:begin
  scanner = heap.take(24)
  calc streamValue = machine.toInt64(stream)
  setField(scanner, 0, streamValue)
  buffer = heap.take(4104)
  table = heap.take(256)
  widthCell = heap.take(8)
  goto eachDirective
:eachDirective loop=while max=forever
  directive = clibrary.byteAt(format, place)
  when directive == 0 finish notEnd
:notEnd in=eachDirective
  space = clibrary.isSpaceByte(directive)
  if space formatSpace notSpace
:formatSpace in=eachDirective
  calc place := place + 1
  skipSpace(scanner)
  goto eachDirective
:notSpace in=eachDirective
  when directive == 37 percent literal
:literal in=eachDirective
  calc place := place + 1
  calc literalRead = scanGet(scanner)
  when literalRead == -1 inputFailure literalCheck
:literalCheck in=eachDirective
  when literalRead == convert.byteToInt64(directive) eachDirective literalMismatch
:literalMismatch
  scanUnget(scanner, literalRead)
  goto finish
:percent in=eachDirective
  calc place := place + 1
  second = clibrary.byteAt(format, place)
  when second == 37 percentLiteral conversionStart
:percentLiteral in=eachDirective
  calc place := place + 1
  skipSpace(scanner)
  calc percentRead = scanGet(scanner)
  when percentRead == -1 inputFailure percentCheck
:percentCheck in=eachDirective
  when percentRead == 37 eachDirective percentMismatch
:percentMismatch
  scanUnget(scanner, percentRead)
  goto finish
:conversionStart in=eachDirective
  calc suppress := second == 42
  if suppress skipStar widthDigits
:skipStar in=eachDirective
  calc place := place + 1
  goto widthDigits
:widthDigits in=eachDirective
  calc place := readDigits(format, place, widthCell)
  calc width := machine.loadInt64(widthCell)
  calc place := readLength(format, place, widthCell)
  calc length := machine.loadInt64(widthCell)
  conversion = clibrary.byteAt(format, place)
  calc place := place + 1
  when conversion == 110 countStore notCount
:countStore in=eachDirective
  if suppress eachDirective countWrite
:countWrite in=eachDirective
  countTarget = machine.fromInt64(cformat.readWord(cursor))
  consumed = field(scanner, 8)
  storeWhole(countTarget, consumed, length)
  goto eachDirective
:notCount in=eachDirective
  when conversion == 91 setStart notSet
:setStart in=eachDirective
  calc place := scanSet(format, place, table)
  goto characters
:notSet in=eachDirective
  when conversion == 99 characters skipFirst
:skipFirst in=eachDirective
  firstValue = skipSpace(scanner)
  when firstValue == -1 inputFailure dispatch
:dispatch in=eachDirective
  when conversion == 115 characters numbers
:characters in=eachDirective
  calc step := 1
  when length == 3 wideUnits widthDefault
:wideUnits in=eachDirective
  calc step := 4
  goto widthDefault
:widthDefault in=eachDirective
  when width == 0 && conversion == 99 oneCharacter widthOpen
:oneCharacter in=eachDirective
  calc width := 1
  goto charactersTarget
:widthOpen in=eachDirective
  when width == 0 noWidth charactersTarget
:noWidth in=eachDirective
  calc width := 9223372036854775807
  goto charactersTarget
:charactersTarget in=eachDirective
  calc count := 0
  nowhere = machine.zero()
  if suppress noTarget takeTarget
:takeTarget in=eachDirective
  calc characterTarget = machine.fromInt64(cformat.readWord(cursor))
  calc targetValue := machine.toInt64(characterTarget)
  goto eachCharacter
:noTarget in=eachDirective
  calc targetValue := machine.toInt64(nowhere)
  goto eachCharacter
:eachCharacter loop=while max=forever in=eachDirective
  when count >= width charactersDone readCharacter
:readCharacter in=eachCharacter
  calc value := scanGet(scanner)
  when value == -1 charactersEnded accepts
:accepts in=eachCharacter
  calc stopsString = conversion == 115 && isSpaceValue(value)
  calc stopsSet = conversion == 91 && !inSet(table, value)
  when stopsString || stopsSet charactersStop keepCharacter
:keepCharacter in=eachCharacter
  when targetValue == 0 counted storeCharacter
:storeCharacter in=eachCharacter
  calc characterAt = machine.fromInt64(targetValue) + count * step
  storeUnit(characterAt, value, step)
  goto counted
:counted in=eachCharacter
  calc count := count + 1
  goto eachCharacter
:charactersStop in=eachDirective
  scanUnget(scanner, value)
  goto charactersDone
:charactersEnded in=eachDirective
  when count == 0 inputFailure charactersShort
:charactersShort in=eachDirective
  when conversion == 99 inputFailure charactersDone
:charactersDone in=eachDirective
  when count == 0 finish charactersStored
:charactersStored in=eachDirective
  when targetValue != 0 && conversion != 99 terminate charactersCounted
:terminate in=eachDirective
  calc endAt = machine.fromInt64(targetValue) + count * step
  storeUnit(endAt, 0, step)
  goto charactersCounted
:charactersCounted in=eachDirective
  if suppress eachDirective addAssigned
:addAssigned in=eachDirective
  calc assigned := assigned + 1
  goto eachDirective
:numbers in=eachDirective
  calc limit = choose(width == 0, 4000) + choose(width != 0, lowest(width, 4000))
  isReal = realConversion(conversion)
  if isReal real whole
:real in=eachDirective
  realBytes = collectReal(scanner, limit, buffer)
  when realBytes < 0 finish realStore
:realStore in=eachDirective
  nowhereEnd = machine.zero()
  realValue = clibrary.parseReal(buffer, nowhereEnd)
  if suppress eachDirective realWrite
:realWrite in=eachDirective
  realTarget = machine.fromInt64(cformat.readWord(cursor))
  when length == 5 longWrite shortWrite
:longWrite in=eachDirective
  cformat.scanLong(buffer, realTarget)
  goto addAssigned
:shortWrite in=eachDirective
  storeReal(realTarget, realValue, length)
  goto addAssigned
:whole in=eachDirective
  calc base := baseOf(conversion)
  when c23 && conversion == 98 binaryConversion baseKnown
:binaryConversion in=eachDirective
  calc base := 2
  goto baseKnown
:baseKnown in=eachDirective
  when base < 0 finish wholeRead
:wholeRead in=eachDirective
  wholeBytes = collectInteger(scanner, limit, base, buffer, c23)
  when wholeBytes < 0 finish wholeStore
:wholeStore in=eachDirective
  calc unsigned = conversion != 100 && conversion != 105
  nowhereWhole = machine.zero()
  wholeValue = readWhole(buffer, nowhereWhole, clibrary.lowInt32(base), unsigned, c23)
  if suppress eachDirective wholeWrite
:wholeWrite in=eachDirective
  wholeTarget = machine.fromInt64(cformat.readWord(cursor))
  calc wholeLength = length + choose(conversion == 112, 3)
  storeWhole(wholeTarget, wholeValue, wholeLength)
  goto addAssigned
:inputFailure
  when assigned == 0 giveEnd finish
:giveEnd
  releaseScan(scanner, buffer, table, widthCell)
  return ended
:finish
  releaseScan(scanner, buffer, table, widthCell)
  calc result = clibrary.lowInt32(assigned)
  return result

op readWhole "strtol's reading of the text a conversion gathered: C23's (0b too) for the __isoc23_ forms"
  input text machine.Address copied
  input endAt machine.Address copied
  input base Int32 copied
  input unsigned Bool copied
  input binary Bool copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  if binary c23 c17
:c23
  newer = clibrary.parseWholeBinary(text, endAt, base, unsigned)
  return newer
:c17
  older = clibrary.parseWhole(text, endAt, base, unsigned)
  return older

op releaseScan "Give back a scan's blocks"
  input scanner machine.Address copied
  input buffer machine.Address copied
  input table machine.Address copied
  input cell machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  heap.give(scanner)
  heap.give(buffer)
  heap.give(table)
  heap.give(cell)
  return

op storeUnit "Store a character read as a byte, or as a 4-byte wchar_t for %lc, %ls, %l["
  input target machine.Address copied
  input value Int64 copied
  input step Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  when step == 4 wideUnit byteUnit
:wideUnit
  machine.storeInt32(target, clibrary.lowInt32(value))
  return
:byteUnit
  machine.storeByte(target, convert.int64ToByte(value & 255))
  return

op realConversion "Whether a scanf conversion reads a floating number: a A e E f F g G"
  input conversion Byte copied
  output Bool
:begin
  calc lower = conversion | 32
  calc floating = lower == 97 || lower == 101 || lower == 102 || lower == 103
  return floating

op baseOf "The base a scanf integer conversion reads in: d u 10, i 0 (strtol's choice), o 8, x X p 16; -1 for any other conversion"
  input conversion Byte copied
  output Int64
  let decimal Int64 10
  let chosen Int64 0
  let octal Int64 8
  let hexadecimal Int64 16
  let unknown Int64 -1
:begin
  when conversion == 100 || conversion == 117 giveDecimal notDecimal
:giveDecimal
  return decimal
:notDecimal
  when conversion == 105 giveChosen notChosen
:giveChosen
  return chosen
:notChosen
  when conversion == 111 giveOctal notOctal
:giveOctal
  return octal
:notOctal
  when conversion == 120 || conversion == 88 || conversion == 112 giveHex giveUnknown
:giveHex
  return hexadecimal
:giveUnknown
  return unknown

op readDigits "Read a run of decimal digits at a position of a format into a cell (0 when none) and give the position after them"
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
  when current >= 48 && current <= 57 && value < 100000000 add finish
:add in=eachDigit
  calc value := value * 10 + convert.byteToInt64(current) - 48
  calc place := place + 1
  goto eachDigit
:finish
  machine.storeInt64(cell, value)
  return place

op readLength "Read a scanf length modifier into a cell (0 none, 1 hh, 2 h, 3 l, 4 ll or q, 5 L, 6 j, 7 z, 8 t) and give the position after it"
  input format machine.Address copied
  input at Int64 copied
  input cell machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let place Int64 0 mut
  let length Int64 0 mut
:begin
  set place at
  first = clibrary.byteAt(format, place)
  calc second = clibrary.byteAt(format, place + 1)
  when first == 104 && second == 104 charLength notChar
:charLength
  calc length := 1
  calc place := place + 2
  goto finish
:notChar
  when first == 104 shortLength notShort
:shortLength
  calc length := 2
  calc place := place + 1
  goto finish
:notShort
  when first == 108 && second == 108 longLongLength notLongLong
:longLongLength
  calc length := 4
  calc place := place + 2
  goto finish
:notLongLong
  when first == 108 longLength notLong
:longLength
  calc length := 3
  calc place := place + 1
  goto finish
:notLong
  when first == 76 longDouble notLongDouble
:longDouble
  calc length := 5
  calc place := place + 1
  goto finish
:notLongDouble
  when first == 113 quad notQuad
:quad
  calc length := 4
  calc place := place + 1
  goto finish
:notQuad
  when first == 106 || first == 122 || first == 116 wide finish
:wide
  calc length := 6
  calc place := place + 1
  goto finish
:finish
  machine.storeInt64(cell, length)
  return place

## ---------------------------------------------------------------- the scanf family

op scanWith "scanf's engine over the arguments a va_list holds (C23's %b and 0b for the __isoc23_ forms)"
  input stream machine.Address copied
  input format machine.Address copied
  input list machine.Address copied
  input c23 Bool copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let wrongWay Int32 -1
:begin
  orientation = orient(stream, -1)
  when orientation != -1 wrongOrientation byteOriented
:wrongOrientation
  return wrongWay
:byteOriented
  cursor = cformat.cursorNew(list)
  result = scanAll(stream, format, cursor, c23)
  cformat.cursorFree(cursor)
  return result

op textStream "A FILE that reads a C string, for sscanf: readable, its buffer the string, never filled again"
  input text machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  stream = heap.take(128)
  calc flags = readable | decided
  machine.storeInt64(stream, flags)
  calc textValue = machine.toInt64(text)
  setField(stream, 16, textValue)
  length = clibrary.cStringLength(text)
  setField(stream, 24, length)
  setField(stream, 40, length)
  setField(stream, 88, 1)
  return stream

op scanStandard "scanf: read stdin by a format"
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "scanf" variadic
:begin
  list = machine.variadicStart()
  inStream = stdinStream()
  result = scanWith(inStream, format, list, false)
  return result

op scanStream "fscanf: read a stream by a format"
  input stream machine.Address copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fscanf" variadic
:begin
  list = machine.variadicStart()
  ensureStandard()
  result = scanWith(stream, format, list, false)
  return result

op scanText "sscanf: read a C string by a format"
  input text machine.Address copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "sscanf" variadic
:begin
  list = machine.variadicStart()
  source = textStream(text)
  result = scanWith(source, format, list, false)
  heap.give(source)
  return result

op scanStandardList "vscanf: read stdin by a format, from a va_list"
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "vscanf"
:begin
  list = listFor(arguments)
  inStream = stdinStream()
  result = scanWith(inStream, format, list, false)
  releaseList(list)
  return result

op scanStreamList "vfscanf: read a stream by a format, from a va_list"
  input stream machine.Address copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "vfscanf"
:begin
  list = listFor(arguments)
  ensureStandard()
  result = scanWith(stream, format, list, false)
  releaseList(list)
  return result

op scanTextList "vsscanf: read a C string by a format, from a va_list"
  input text machine.Address copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "vsscanf"
:begin
  list = listFor(arguments)
  source = textStream(text)
  result = scanWith(source, format, list, false)
  heap.give(source)
  releaseList(list)
  return result

op scanStandardGlibc "__isoc99_scanf: read stdin by a format (the name glibc's headers give it in C99 and later)"
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc99_scanf" variadic
:begin
  list = machine.variadicStart()
  inStream = stdinStream()
  result = scanWith(inStream, format, list, false)
  return result

op scanStreamGlibc "__isoc99_fscanf: read a stream by a format (the name glibc's headers give it in C99 and later)"
  input stream machine.Address copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc99_fscanf" variadic
:begin
  list = machine.variadicStart()
  ensureStandard()
  result = scanWith(stream, format, list, false)
  return result

op scanTextGlibc "__isoc99_sscanf: read a C string by a format (the name glibc's headers give it in C99 and later)"
  input text machine.Address copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc99_sscanf" variadic
:begin
  list = machine.variadicStart()
  source = textStream(text)
  result = scanWith(source, format, list, false)
  heap.give(source)
  return result

op scanStandardListGlibc "__isoc99_vscanf: read stdin by a format, from a va_list (the name glibc's headers give it in C99 and later)"
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc99_vscanf"
:begin
  list = listFor(arguments)
  inStream = stdinStream()
  result = scanWith(inStream, format, list, false)
  releaseList(list)
  return result

op scanStreamListGlibc "__isoc99_vfscanf: read a stream by a format, from a va_list (the name glibc's headers give it in C99 and later)"
  input stream machine.Address copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc99_vfscanf"
:begin
  list = listFor(arguments)
  ensureStandard()
  result = scanWith(stream, format, list, false)
  releaseList(list)
  return result

op scanTextListGlibc "__isoc99_vsscanf: read a C string by a format, from a va_list (the name glibc's headers give it in C99 and later)"
  input text machine.Address copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc99_vsscanf"
:begin
  list = listFor(arguments)
  source = textStream(text)
  result = scanWith(source, format, list, false)
  heap.give(source)
  releaseList(list)
  return result

## ---------------------------------------------------------------- _FORTIFY_SOURCE's checked stdio (D-165)

op storeChecked "Format into memory as sprintf (limit -1) or snprintf does, failing as __chk_fail does when the bound is past the target's size or (with no bound) the text and its 0 are"
  input target machine.Address copied
  input limit Int64 copied
  input room Int64 copied
  input format machine.Address copied
  input list machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let failure Int32 -1
:begin
  when limit >= 0 withBound withoutBound
:withBound
  clibrary.checkFits(limit, room)
  result = storeFormatted(target, limit, format, list)
  return result
:withoutBound
  cursor = cformat.cursorNew(list)
  builder = wide.builderNew()
  count = cformat.formatAll(format, cursor, builder)
  text = wide.builderText(builder)
  length = wide.builderLength(builder)
  cformat.cursorFree(cursor)
  when count < 0 refuse copy
:refuse
  heap.give(text)
  heap.give(builder)
  return failure
:copy
  clibrary.checkFits(length + 1, room)
  machine.copy(target, text, length)
  calc endAt = target + length
  machine.storeByte(endAt, 0)
  heap.give(text)
  heap.give(builder)
  calc written = clibrary.lowInt32(count)
  return written

op getLineChecked "__fgets_chk: fgets, failing as __chk_fail does when the count passes the buffer's size"
  input buffer machine.Address copied
  input room Int64 copied
  input limit Int32 copied
  input stream machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__fgets_chk"
:begin
  clibrary.checkFits(convert.int32ToInt64(limit), room)
  result = getLine(buffer, limit, stream)
  return result

op readItemsChecked "__fread_chk: fread, failing as __chk_fail does when the items pass the buffer's size"
  input data machine.Address copied
  input room Int64 copied
  input size Int64 copied
  input count Int64 copied
  input stream machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__fread_chk"
:begin
  calc bytes = math.wrappingMultiplyInt64(size, count)
  clibrary.checkFits(bytes, room)
  result = readItems(data, size, count, stream)
  return result

op printChecked "__printf_chk: printf, the name glibc's headers call under _FORTIFY_SOURCE (the flag asks nothing more here)"
  input flag Int32 copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__printf_chk" variadic
:begin
  list = machine.variadicStart()
  out = stdoutStream()
  result = writeFormatted(out, format, list)
  return result

op printToChecked "__fprintf_chk: fprintf under _FORTIFY_SOURCE"
  input stream machine.Address copied
  input flag Int32 copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__fprintf_chk" variadic
:begin
  list = machine.variadicStart()
  result = writeFormatted(stream, format, list)
  return result

op printIntoChecked "__sprintf_chk: sprintf, failing as __chk_fail does when the text and its 0 pass the target's size"
  input target machine.Address copied
  input flag Int32 copied
  input room Int64 copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__sprintf_chk" variadic
:begin
  list = machine.variadicStart()
  result = storeChecked(target, -1, room, format, list)
  return result

op printBoundedChecked "__snprintf_chk: snprintf, failing as __chk_fail does when its bound passes the target's size"
  input target machine.Address copied
  input limit Int64 copied
  input flag Int32 copied
  input room Int64 copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__snprintf_chk" variadic
:begin
  list = machine.variadicStart()
  result = storeChecked(target, limit, room, format, list)
  return result

op printListChecked "__vprintf_chk: vprintf under _FORTIFY_SOURCE"
  input flag Int32 copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__vprintf_chk"
:begin
  list = listFor(arguments)
  out = stdoutStream()
  result = writeFormatted(out, format, list)
  releaseList(list)
  return result

op printListToChecked "__vfprintf_chk: vfprintf under _FORTIFY_SOURCE"
  input stream machine.Address copied
  input flag Int32 copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__vfprintf_chk"
:begin
  list = listFor(arguments)
  result = writeFormatted(stream, format, list)
  releaseList(list)
  return result

op printListIntoChecked "__vsprintf_chk: vsprintf, failing when the text passes the target's size"
  input target machine.Address copied
  input flag Int32 copied
  input room Int64 copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__vsprintf_chk"
:begin
  list = listFor(arguments)
  result = storeChecked(target, -1, room, format, list)
  releaseList(list)
  return result

op printListBoundedChecked "__vsnprintf_chk: vsnprintf, failing when its bound passes the target's size"
  input target machine.Address copied
  input limit Int64 copied
  input flag Int32 copied
  input room Int64 copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__vsnprintf_chk"
:begin
  list = listFor(arguments)
  result = storeChecked(target, limit, room, format, list)
  releaseList(list)
  return result

## ---------------------------------------------------------------- wide streams (D-176)
##
## A wide stream reads and writes the C locale's bytes, one for each wide character from 0 to 255 (as glibc 2.35 and
## later have it); writing a wide character past 255 fails with EILSEQ and sets the stream's error, what came before
## it written. A stream becomes wide through these functions and then refuses printf, fputs, and the other byte
## functions that check (orientation above). The wide printf family runs cformat's engine in wide mode over the wide
## format made bytes (cformat.addUnit), so %lc and %ls keep every character for swprintf; the wide scanf family runs
## scanf's engine over the wide format's bytes up to its first character past 255, which no input of the C locale's
## bytes could match, and swscanf reads its wide text's characters up to its first past 255.

constant illegalSequence "EILSEQ: a wide character with no byte in the C locale" Int32 84

op wideOrientation "fwide: give a stream wide (mode above 0) or byte (below 0) orientation unless it has one; gives the orientation, above 0 wide, below 0 bytes, 0 none"
  input stream machine.Address copied
  input mode Int32 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fwide"
:begin
  ensureStandard()
  orientation = orient(stream, convert.int32ToInt64(mode))
  calc result = clibrary.lowInt32(orientation)
  return result

op widePut "fputwc: write a wide character to a stream as its byte: the character, or WEOF for a byte stream, a character past 255 (EILSEQ, the error set), or a failed write"
  input stream machine.Address copied
  input value Int32 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let endOfFile Int32 -1
:begin
  ensureStandard()
  orientation = orient(stream, 1)
  when orientation != 1 refuse oriented
:oriented
  calc code = convert.int32ToInt64(value) & 4294967295
  when code > 255 noByte write
:noByte
  clibrary.setErrno(illegalSequence)
  addFlag(stream, failed)
  return endOfFile
:write
  cell = kernel.stateAt(byteAt)
  machine.storeByte(cell, convert.int64ToByte(code))
  taken = putBytes(stream, cell, 1)
  when taken == 1 wrote refuse
:wrote
  return value
:refuse
  return endOfFile

op widePutOn "fputwc: write a wide character to a stream"
  input value Int32 copied
  input stream machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fputwc"
:begin
  result = widePut(stream, value)
  return result

op widePutStream "putwc: fputwc"
  input value Int32 copied
  input stream machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "putwc"
:begin
  result = widePut(stream, value)
  return result

op widePutStandard "putwchar: fputwc to stdout"
  input value Int32 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "putwchar"
:begin
  out = stdoutStream()
  result = widePut(out, value)
  return result

op widePutText "fputws: write a wide string to a stream as its bytes: 1, or WEOF (-1) for a byte stream, a character past 255 (EILSEQ, the error set, the characters before it written), or a failed write"
  input text machine.Address copied
  input stream machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fputws"
  let count Int64 0 mut
  let succeeded Int32 1
  let endOfFile Int32 -1
:begin
  ensureStandard()
  orientation = orient(stream, 1)
  when orientation != 1 refuse measure
:measure loop=while max=forever
  calc unitAt = text + count * 4
  calc code = convert.int32ToInt64(machine.loadInt32(unitAt)) & 4294967295
  when code == 0 || code > 255 measured copyCheck
:copyCheck in=measure
  calc count := count + 1
  goto measure
:measured
  calc bytes = heap.take(count + 1)
  goto copyEach
:copyEach
  narrowUnits(text, count, bytes)
  taken = putBytes(stream, bytes, count)
  heap.give(bytes)
  when taken == count written refuse
:written
  calc stopAt = text + count * 4
  stopper = machine.loadInt32(stopAt)
  when stopper == 0 wrote noByte
:noByte
  clibrary.setErrno(illegalSequence)
  addFlag(stream, failed)
  return endOfFile
:wrote
  return succeeded
:refuse
  return endOfFile

op narrowUnits "Copy a count of wide characters (each below 256) as bytes"
  input text machine.Address copied
  input count Int64 copied
  input bytes machine.Address copied
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  goto eachUnit
:eachUnit loop=while max=forever
  when at >= count done copyOne
:copyOne in=eachUnit
  calc unitAt = text + at * 4
  calc byteCode = convert.int32ToInt64(machine.loadInt32(unitAt)) & 255
  calc placeAt = bytes + at
  machine.storeByte(placeAt, convert.int64ToByte(byteCode))
  calc at := at + 1
  goto eachUnit
:done
  return

op wideGet "fgetwc: read a wide character from a stream (its byte), or WEOF at the end or on an error"
  input stream machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  ensureStandard()
  orient(stream, 1)
  value = getByte(stream)
  calc result = clibrary.lowInt32(value)
  return result

op wideGetOn "fgetwc: read a wide character from a stream"
  input stream machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fgetwc"
:begin
  result = wideGet(stream)
  return result

op wideGetStream "getwc: fgetwc"
  input stream machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "getwc"
:begin
  result = wideGet(stream)
  return result

op wideGetStandard "getwchar: fgetwc from stdin"
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "getwchar"
:begin
  inStream = stdinStream()
  result = wideGet(inStream)
  return result

op wideGetLine "fgetws: read a line (its line feed kept) of at most n-1 wide characters into a buffer and end it with 0: the buffer, or NULL when the end came before any character or a read failed"
  input buffer machine.Address copied
  input limit Int32 copied
  input stream machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fgetws"
  let count Int64 0 mut
:begin
  ensureStandard()
  orient(stream, 1)
  nowhere = machine.zero()
  calc most = convert.int32ToInt64(limit) - 1
  when most < 0 refuse eachUnit
:eachUnit loop=while max=forever
  when count >= most finish read
:read in=eachUnit
  value = getByte(stream)
  when value < 0 ended store
:store in=eachUnit
  calc at = buffer + count * 4
  machine.storeInt32(at, clibrary.lowInt32(value))
  calc count := count + 1
  when value == 10 finish eachUnit
:ended
  readFailed = hasFlag(stream, failed)
  when count == 0 || readFailed refuse finish
:finish
  calc endAt = buffer + count * 4
  machine.storeInt32(endAt, clibrary.lowInt32(0))
  return buffer
:refuse
  return nowhere

op wideGetLineChecked "__fgetws_chk: fgetws, failing as __chk_fail does when the count passes the buffer's size in wide characters"
  input buffer machine.Address copied
  input room Int64 copied
  input limit Int32 copied
  input stream machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__fgetws_chk"
:begin
  calc wanted = convert.int32ToInt64(limit)
  when wanted > 0 check read
:check
  clibrary.checkFits(wanted, room)
  goto read
:read
  result = wideGetLine(buffer, limit, stream)
  return result

op wideUnget "ungetwc: push a wide character back onto a stream as its byte: the character, or WEOF for WEOF, a character past 255, or no room"
  input value Int32 copied
  input stream machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "ungetwc"
  let endOfFile Int32 -1
:begin
  ensureStandard()
  orient(stream, 1)
  calc code = convert.int32ToInt64(value) & 4294967295
  when code > 255 refuse push
:push
  pushed = ungetByte(stream, code)
  when pushed < 0 refuse pushedBack
:pushedBack
  return value
:refuse
  return endOfFile

## ---------------------------------------------------------------- wprintf

op wideFormatBytes "A wide format as the bytes cformat's wide mode reads, in a new block ending with 0"
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

op unitCodeAt "The wide character a wide mode text holds at a position: its byte, or the escape's bits after a 255"
  input text machine.Address copied
  input at Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let piece Int64 1 mut
  let code Int64 0 mut
:begin
  first = clibrary.byteAt(text, at)
  calc firstCode = convert.byteToInt64(first)
  when firstCode == 255 escaped plain
:plain
  return firstCode
:escaped loop=while max=forever
  when piece > 6 decoded addPiece
:addPiece in=escaped
  calc pieceAt = at + piece
  calc bits = convert.byteToInt64(clibrary.byteAt(text, pieceAt)) & 63
  calc code := (code << 6) | bits
  calc piece := piece + 1
  goto escaped
:decoded
  calc unsigned = code & 4294967295
  return unsigned

op unitStep "How many bytes a wide mode text's character at a position takes: 7 for an escape, else 1"
  input text machine.Address copied
  input at Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let escape Int64 7
  let single Int64 1
:begin
  first = clibrary.byteAt(text, at)
  when first == 255 giveEscape giveSingle
:giveEscape
  return escape
:giveSingle
  return single

op wideWriteFormatted "Format a wide format into a stream as wfprintf: the wide characters written as an int, or -1 for a byte stream, a format error, a character past 255 (EILSEQ, the error set, what came before written), or a failed write"
  invariant writesWideBytes "Writes the C locale's byte of each wide character and counts characters"
  input stream machine.Address copied
  input format machine.Address copied
  input cursor machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let failure Int32 -1
  let at Int64 0 mut
  let kept Int64 0 mut
  let refused Bool false mut
:begin
  ensureStandard()
  orientation = orient(stream, 1)
  when orientation != 1 refuse formatIt
:formatIt
  formatBytes = wideFormatBytes(format)
  builder = wide.builderNew()
  count = cformat.formatAllAs(formatBytes, cursor, builder, true)
  heap.give(formatBytes)
  text = wide.builderText(builder)
  length = wide.builderLength(builder)
  heap.give(builder)
  when count < 0 giveUp narrow
:narrow
  calc bytes = heap.take(length + 1)
  goto eachUnit
:eachUnit loop=while max=forever
  when at >= length write convertUnit
:convertUnit in=eachUnit
  code = unitCodeAt(text, at)
  when code > 255 noByte keep
:noByte in=eachUnit
  calc refused := true
  goto write
:keep in=eachUnit
  calc keptAt = bytes + kept
  machine.storeByte(keptAt, convert.int64ToByte(code))
  calc kept := kept + 1
  step = unitStep(text, at)
  calc at := at + step
  goto eachUnit
:write
  heap.give(text)
  taken = putBytes(stream, bytes, kept)
  heap.give(bytes)
  when taken != kept refuse wroteAll
:wroteAll
  if refused failSequence wrote
:failSequence
  clibrary.setErrno(illegalSequence)
  addFlag(stream, failed)
  return failure
:wrote
  calc result = clibrary.lowInt32(count)
  return result
:giveUp
  heap.give(text)
  return failure
:refuse
  return failure

op wideStoreFormatted "Format a wide format into wide memory as swprintf: at most limit - 1 characters and a 0; the characters written as an int, or -1 when they and the 0 do not fit (the first limit - 1 written, no 0) or the format fails"
  invariant storesWide "Keeps every wide character, and refuses with -1 a text that does not fit with its 0"
  input target machine.Address copied
  input limit Int64 copied
  input format machine.Address copied
  input cursor machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let failure Int32 -1
  let at Int64 0 mut
  let stored Int64 0 mut
:begin
  when limit == 0 refuse formatIt
:formatIt
  formatBytes = wideFormatBytes(format)
  builder = wide.builderNew()
  count = cformat.formatAllAs(formatBytes, cursor, builder, true)
  heap.give(formatBytes)
  text = wide.builderText(builder)
  length = wide.builderLength(builder)
  heap.give(builder)
  when count < 0 giveUp eachUnit
:eachUnit loop=while max=forever
  when at >= length || stored >= limit - 1 copied storeOne
:storeOne in=eachUnit
  code = unitCodeAt(text, at)
  calc unitAt = target + stored * 4
  machine.storeInt32(unitAt, clibrary.lowInt32(code))
  calc stored := stored + 1
  step = unitStep(text, at)
  calc at := at + step
  goto eachUnit
:copied
  heap.give(text)
  when count > limit - 1 refuse terminate
:terminate
  calc endAt = target + stored * 4
  machine.storeInt32(endAt, clibrary.lowInt32(0))
  calc result = clibrary.lowInt32(count)
  return result
:giveUp
  heap.give(text)
  return failure
:refuse
  return failure

op wideWriteList "wfprintf's work from a va_list's address (a v-function's argument made a list by listFor)"
  input stream machine.Address copied
  input format machine.Address copied
  input list machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  cursor = cformat.cursorNew(list)
  result = wideWriteFormatted(stream, format, cursor)
  cformat.cursorFree(cursor)
  return result

op wideStoreList "swprintf's work from a va_list"
  input target machine.Address copied
  input limit Int64 copied
  input format machine.Address copied
  input list machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  cursor = cformat.cursorNew(list)
  result = wideStoreFormatted(target, limit, format, cursor)
  cformat.cursorFree(cursor)
  return result

op widePrintStandard "wprintf: format to stdout"
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "wprintf" variadic
:begin
  list = machine.variadicStart()
  out = stdoutStream()
  result = wideWriteList(out, format, list)
  return result

op widePrintStream "fwprintf: format to a stream"
  input stream machine.Address copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fwprintf" variadic
:begin
  list = machine.variadicStart()
  result = wideWriteList(stream, format, list)
  return result

op widePrintInto "swprintf: format into wide memory, at most n - 1 characters and a 0, -1 when the text does not fit"
  input target machine.Address copied
  input limit Int64 copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "swprintf" variadic
:begin
  list = machine.variadicStart()
  result = wideStoreList(target, limit, format, list)
  return result

op widePrintStandardList "vwprintf: format to stdout from a va_list"
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "vwprintf"
:begin
  list = listFor(arguments)
  out = stdoutStream()
  result = wideWriteList(out, format, list)
  releaseList(list)
  return result

op widePrintStreamList "vfwprintf: format to a stream from a va_list"
  input stream machine.Address copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "vfwprintf"
:begin
  list = listFor(arguments)
  result = wideWriteList(stream, format, list)
  releaseList(list)
  return result

op widePrintIntoList "vswprintf: format into wide memory from a va_list"
  input target machine.Address copied
  input limit Int64 copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "vswprintf"
:begin
  list = listFor(arguments)
  result = wideStoreList(target, limit, format, list)
  releaseList(list)
  return result

op widePrintStandardChecked "__wprintf_chk: wprintf (the flag asks for checks this library always makes)"
  input flag Int32 copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__wprintf_chk" variadic
:begin
  list = machine.variadicStart()
  out = stdoutStream()
  result = wideWriteList(out, format, list)
  return result

op widePrintStreamChecked "__fwprintf_chk: fwprintf"
  input stream machine.Address copied
  input flag Int32 copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__fwprintf_chk" variadic
:begin
  list = machine.variadicStart()
  result = wideWriteList(stream, format, list)
  return result

op widePrintIntoChecked "__swprintf_chk: swprintf, failing as __chk_fail does when its bound passes the target's size in wide characters"
  input target machine.Address copied
  input limit Int64 copied
  input flag Int32 copied
  input room Int64 copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__swprintf_chk" variadic
:begin
  list = machine.variadicStart()
  clibrary.checkFits(limit, room)
  result = wideStoreList(target, limit, format, list)
  return result

op widePrintStandardListChecked "__vwprintf_chk: vwprintf"
  input flag Int32 copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__vwprintf_chk"
:begin
  list = listFor(arguments)
  out = stdoutStream()
  result = wideWriteList(out, format, list)
  releaseList(list)
  return result

op widePrintStreamListChecked "__vfwprintf_chk: vfwprintf"
  input stream machine.Address copied
  input flag Int32 copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__vfwprintf_chk"
:begin
  list = listFor(arguments)
  result = wideWriteList(stream, format, list)
  releaseList(list)
  return result

op widePrintIntoListChecked "__vswprintf_chk: vswprintf, failing as __chk_fail does when its bound passes the target's size"
  input target machine.Address copied
  input limit Int64 copied
  input flag Int32 copied
  input room Int64 copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__vswprintf_chk"
:begin
  clibrary.checkFits(limit, room)
  list = listFor(arguments)
  result = wideStoreList(target, limit, format, list)
  releaseList(list)
  return result

## ---------------------------------------------------------------- wscanf

op wideScanBytes "A wide text's characters as bytes up to its end or its first character past 255, in a new block ending with 0"
  input text machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let count Int64 0 mut
:begin
  goto measure
:measure loop=while max=forever
  calc unitAt = text + count * 4
  calc code = convert.int32ToInt64(machine.loadInt32(unitAt)) & 4294967295
  when code == 0 || code > 255 measured countIt
:countIt in=measure
  calc count := count + 1
  goto measure
:measured
  calc bytes = heap.take(count + 1)
  narrowUnits(text, count, bytes)
  return bytes

op wideScan "wscanf's engine: scanf's over a stream made wide, by the wide format's bytes; EOF (-1) for a byte stream"
  invariant scansWide "Reads a wide stream by a wide format as scanf reads the same bytes"
  input stream machine.Address copied
  input format machine.Address copied
  input cursor machine.Address copied
  input c23 Bool copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let wrongWay Int32 -1
:begin
  ensureStandard()
  orientation = orient(stream, 1)
  when orientation != 1 refuse scan
:scan
  formatBytes = wideScanBytes(format)
  result = scanAll(stream, formatBytes, cursor, c23)
  heap.give(formatBytes)
  return result
:refuse
  return wrongWay

op wideScanText "swscanf's engine: scanf's over a wide text's characters, by the wide format's bytes"
  invariant scansWideText "Reads a wide text by a wide format as sscanf reads the same bytes"
  input text machine.Address copied
  input format machine.Address copied
  input cursor machine.Address copied
  input c23 Bool copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  textBytes = wideScanBytes(text)
  source = textStream(textBytes)
  formatBytes = wideScanBytes(format)
  result = scanAll(source, formatBytes, cursor, c23)
  heap.give(formatBytes)
  heap.give(source)
  heap.give(textBytes)
  return result

op wideScanList "wscanf's engine over a va_list (C23's %b and 0b for the __isoc23_ forms)"
  input stream machine.Address copied
  input format machine.Address copied
  input list machine.Address copied
  input c23 Bool copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  cursor = cformat.cursorNew(list)
  result = wideScan(stream, format, cursor, c23)
  cformat.cursorFree(cursor)
  return result

op wideScanTextList "swscanf's engine over a va_list"
  input text machine.Address copied
  input format machine.Address copied
  input list machine.Address copied
  input c23 Bool copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  cursor = cformat.cursorNew(list)
  result = wideScanText(text, format, cursor, c23)
  cformat.cursorFree(cursor)
  return result

op wideScanStandard "wscanf: read stdin by a wide format"
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "wscanf" variadic
:begin
  list = machine.variadicStart()
  inStream = stdinStream()
  result = wideScanList(inStream, format, list, false)
  return result

op wideScanStream "fwscanf: read a stream by a wide format"
  input stream machine.Address copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fwscanf" variadic
:begin
  list = machine.variadicStart()
  result = wideScanList(stream, format, list, false)
  return result

op wideScanString "swscanf: read a wide string by a wide format"
  input text machine.Address copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "swscanf" variadic
:begin
  list = machine.variadicStart()
  result = wideScanTextList(text, format, list, false)
  return result

op wideScanStandardList "vwscanf: read stdin by a wide format, from a va_list"
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "vwscanf"
:begin
  list = listFor(arguments)
  inStream = stdinStream()
  result = wideScanList(inStream, format, list, false)
  releaseList(list)
  return result

op wideScanStreamList "vfwscanf: read a stream by a wide format, from a va_list"
  input stream machine.Address copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "vfwscanf"
:begin
  list = listFor(arguments)
  result = wideScanList(stream, format, list, false)
  releaseList(list)
  return result

op wideScanStringList "vswscanf: read a wide string by a wide format, from a va_list"
  input text machine.Address copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "vswscanf"
:begin
  list = listFor(arguments)
  result = wideScanTextList(text, format, list, false)
  releaseList(list)
  return result

op wideScanStandardC99 "wscanf: read stdin by a wide format (glibc's C99 name)"
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc99_wscanf" variadic
:begin
  list = machine.variadicStart()
  inStream = stdinStream()
  result = wideScanList(inStream, format, list, false)
  return result

op wideScanStreamC99 "fwscanf: read a stream by a wide format (glibc's C99 name)"
  input stream machine.Address copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc99_fwscanf" variadic
:begin
  list = machine.variadicStart()
  result = wideScanList(stream, format, list, false)
  return result

op wideScanStringC99 "swscanf: read a wide string by a wide format (glibc's C99 name)"
  input text machine.Address copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc99_swscanf" variadic
:begin
  list = machine.variadicStart()
  result = wideScanTextList(text, format, list, false)
  return result

op wideScanStandardListC99 "vwscanf: read stdin by a wide format, from a va_list (glibc's C99 name)"
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc99_vwscanf"
:begin
  list = listFor(arguments)
  inStream = stdinStream()
  result = wideScanList(inStream, format, list, false)
  releaseList(list)
  return result

op wideScanStreamListC99 "vfwscanf: read a stream by a wide format, from a va_list (glibc's C99 name)"
  input stream machine.Address copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc99_vfwscanf"
:begin
  list = listFor(arguments)
  result = wideScanList(stream, format, list, false)
  releaseList(list)
  return result

op wideScanStringListC99 "vswscanf: read a wide string by a wide format, from a va_list (glibc's C99 name)"
  input text machine.Address copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc99_vswscanf"
:begin
  list = listFor(arguments)
  result = wideScanTextList(text, format, list, false)
  releaseList(list)
  return result

op wideScanStandardC23 "wscanf: read stdin by a wide format (glibc's C23 name: %b and 0b)"
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc23_wscanf" variadic
:begin
  list = machine.variadicStart()
  inStream = stdinStream()
  result = wideScanList(inStream, format, list, true)
  return result

op wideScanStreamC23 "fwscanf: read a stream by a wide format (glibc's C23 name: %b and 0b)"
  input stream machine.Address copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc23_fwscanf" variadic
:begin
  list = machine.variadicStart()
  result = wideScanList(stream, format, list, true)
  return result

op wideScanStringC23 "swscanf: read a wide string by a wide format (glibc's C23 name: %b and 0b)"
  input text machine.Address copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc23_swscanf" variadic
:begin
  list = machine.variadicStart()
  result = wideScanTextList(text, format, list, true)
  return result

op wideScanStandardListC23 "vwscanf: read stdin by a wide format, from a va_list (glibc's C23 name: %b and 0b)"
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc23_vwscanf"
:begin
  list = listFor(arguments)
  inStream = stdinStream()
  result = wideScanList(inStream, format, list, true)
  releaseList(list)
  return result

op wideScanStreamListC23 "vfwscanf: read a stream by a wide format, from a va_list (glibc's C23 name: %b and 0b)"
  input stream machine.Address copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc23_vfwscanf"
:begin
  list = listFor(arguments)
  result = wideScanList(stream, format, list, true)
  releaseList(list)
  return result

op wideScanStringListC23 "vswscanf: read a wide string by a wide format, from a va_list (glibc's C23 name: %b and 0b)"
  input text machine.Address copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc23_vswscanf"
:begin
  list = listFor(arguments)
  result = wideScanTextList(text, format, list, true)
  releaseList(list)
  return result

## ---------------------------------------------------------------- the streams' lock (D-166)
##
## Once a C program starts a thread, the stream operations below hold one lock for every stream: a futex word at
## machine.state 28976 (0 free, 1 held, 2 held with waiters), its holder's thread id at 28984 and how many times it
## holds it at 28992, so an operation that calls another under the lock takes it again.

op lockStreams "Take the streams' lock when threads were started; its holder takes it again"
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  started = heap.threaded()
  if started take done
:take
  word = kernel.stateAt(28976)
  holderCell = kernel.stateAt(28984)
  depthCell = kernel.stateAt(28992)
  self = lockerId()
  holder = machine.loadInt64(holderCell)
  when holder == self again acquire
:again
  depth = machine.loadInt64(depthCell)
  machine.storeInt64(depthCell, depth + 1)
  return
:acquire
  first = machine.compareExchange32(word, 0, 1)
  when first == 0 held contended
:contended loop=while max=forever
  previous = machine.compareExchange32(word, 1, 2)
  when previous == 0 retake wait
:wait in=contended
  waitOn(word)
  goto retake
:retake in=contended
  taken = machine.compareExchange32(word, 0, 2)
  when taken == 0 held contended
:held
  machine.storeInt64(holderCell, self)
  machine.storeInt64(depthCell, 1)
  return
:done
  return

op lockerId "The running thread's id: gettid on Linux, GetCurrentThreadId on Windows"
  output Int64
  effect use system.calls
  uses systemCalls
:begin
  onLinux = system.linux()
  if onLinux linux windows
:linux
  id = system.gettid()
  return id
:windows
  windowsId = system.getCurrentThreadId()
  calc wideId = convert.int32ToInt64(windowsId)
  return wideId

op waitOn "Wait on the lock's word: a futex wait while it holds 2 on Linux, a millisecond's sleep on Windows"
  input word machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  onLinux = system.linux()
  if onLinux linux windows
:linux
  nowhere = machine.zero()
  system.futex(word, 128, 2, nowhere, nowhere, 0)
  return
:windows
  system.sleep(1)
  return

op wakeOn "Wake a waiter on the lock's word: a futex wake on Linux; on Windows the waiter looks again on its own"
  input word machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  onLinux = system.linux()
  if onLinux linux done
:linux
  nowhere = machine.zero()
  system.futex(word, 129, 1, nowhere, nowhere, 0)
  return
:done
  return

op unlockStreams "Give the streams' lock back when its holder's count comes to 0, waking a waiter"
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  started = heap.threaded()
  if started release done
:release
  word = kernel.stateAt(28976)
  holderCell = kernel.stateAt(28984)
  depthCell = kernel.stateAt(28992)
  depth = machine.loadInt64(depthCell)
  when depth > 1 down free
:down
  machine.storeInt64(depthCell, depth - 1)
  return
:free
  machine.storeInt64(depthCell, 0)
  machine.storeInt64(holderCell, 0)
  previous = machine.compareExchange32(word, 1, 0)
  when previous == 1 done wake
:wake
  machine.storeInt32(word, 0)
  wakeOn(word)
  return
:done
  return

op putBytes "Write bytes to a stream as its buffering says: how many were taken (all of them, or 0 when the stream cannot be written or the write fails, errno set); under the streams' lock once threads were started (D-166)"
  input stream machine.Address copied
  input data machine.Address copied
  input bytes Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  lockStreams()
  result = putBytesHeld(stream, data, bytes)
  unlockStreams()
  return result

op getByte "Read one byte from a stream as an unsigned char, or -1 (EOF) at the end or on an error; what ungetc pushed back comes first, and the end of file stays once reached; under the streams' lock once threads were started (D-166)"
  input stream machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  lockStreams()
  result = getByteHeld(stream)
  unlockStreams()
  return result

op ungetByte "ungetc: push a byte back onto a stream (8 at most), clearing its end of file; gives the byte, or EOF for EOF or when there is no room; under the streams' lock once threads were started (D-166)"
  input stream machine.Address copied
  input value Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  lockStreams()
  result = ungetByteHeld(stream, value)
  unlockStreams()
  return result

op flushPending "Write the bytes waiting in a stream's buffer: 0, or -1 when the write fails (the error flag set); under the streams' lock once threads were started (D-166)"
  input stream machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  lockStreams()
  result = flushPendingHeld(stream)
  unlockStreams()
  return result

op flushAll "fflush(NULL): write what every stream holds, the standard ones and those fopen opened; 0, or -1 when a write failed; under the streams' lock once threads were started (D-166)"
  invariant flushesEvery "Every stream's waiting bytes are written"
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  lockStreams()
  result = flushAllHeld()
  unlockStreams()
  return result

op scanStandardC23 "__isoc23_scanf: scanf (glibc's C23 name: %b and 0b read binary)"
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc23_scanf" variadic
:begin
  list = machine.variadicStart()
  inStream = stdinStream()
  result = scanWith(inStream, format, list, true)
  return result

op scanStreamC23 "__isoc23_fscanf: fscanf (glibc's C23 name: %b and 0b read binary)"
  input stream machine.Address copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc23_fscanf" variadic
:begin
  list = machine.variadicStart()
  ensureStandard()
  result = scanWith(stream, format, list, true)
  return result

op scanTextC23 "__isoc23_sscanf: sscanf (glibc's C23 name: %b and 0b read binary)"
  input text machine.Address copied
  input format machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc23_sscanf" variadic
:begin
  list = machine.variadicStart()
  source = textStream(text)
  result = scanWith(source, format, list, true)
  heap.give(source)
  return result

op scanStandardListC23 "__isoc23_vscanf: vscanf (glibc's C23 name: %b and 0b read binary)"
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc23_vscanf"
:begin
  list = listFor(arguments)
  inStream = stdinStream()
  result = scanWith(inStream, format, list, true)
  releaseList(list)
  return result

op scanStreamListC23 "__isoc23_vfscanf: vfscanf (glibc's C23 name: %b and 0b read binary)"
  input stream machine.Address copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc23_vfscanf"
:begin
  list = listFor(arguments)
  ensureStandard()
  result = scanWith(stream, format, list, true)
  releaseList(list)
  return result

op scanTextListC23 "__isoc23_vsscanf: vsscanf (glibc's C23 name: %b and 0b read binary)"
  input text machine.Address copied
  input format machine.Address copied
  input arguments machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc23_vsscanf"
:begin
  list = listFor(arguments)
  source = textStream(text)
  result = scanWith(source, format, list, true)
  heap.give(source)
  releaseList(list)
  return result

@tests

op cText "A C string in a new heap block: a text's bytes and a 0"
  input text String borrowed
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  bytes = string.byteLength(text)
  calc block = heap.take(bytes + 1)
  at = machine.addressOfString(text)
  machine.copy(block, at, bytes)
  return block

op slotCursor "A cursor over eight-byte argument slots (the layout the tests use on every system), the slots holding the addresses of a block's cells: the first cell's at 0, the next 8 bytes on"
  input cells machine.Address copied
  input count Int64 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  calc slots = heap.take(count * 8 + 8)
  goto eachSlot
:eachSlot loop=while max=count
  when at >= count finish fill
:fill in=eachSlot
  calc cellAt = cells + at * 64
  calc slotAt = slots + at * 8
  machine.storeAddress(slotAt, cellAt)
  calc at := at + 1
  goto eachSlot
:finish
  cell = heap.take(8)
  machine.storeAddress(cell, slots)
  cursor = heap.take(16)
  machine.storeInt64(cursor, 3)
  calc cursorListAt = cursor + 8
  machine.storeAddress(cursorListAt, cell)
  return cursor

test streamTest "A temporary file is written through its buffer, flushed, read back by line, and scanned: %s %d %i %lf %3c read what glibc's scanf reads; sscanf of blanks is EOF, of a letter 0, and %n counts"
  verifies flushAll flushesEvery
  verifies scanAll scansLikeGlibc
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let line String "abc 42 -0x1f 3.25 xyzw"
  let firstFormat String "%s %d %i %lf %3c"
  let blankText String "   "
  let letterText String "x"
  let numberText String "12abc"
  let numberFormat String "%d"
  let countFormat String "%d%n"
  let word String "abc"
:begin
  file = temporaryFile()
  nowhere = machine.zero()
  test.assertTrue(file != nowhere)
  lineText = cText(line)
  putStream(lineText, file)
  status = flushAll()
  test.assertTrue(status == 0)
  where = tellStream(file)
  test.assertEqualInt64(22, where)
  rewindStream(file)
  buffer = heap.take(64)
  back = getLine(buffer, 64, file)
  test.assertTrue(back == buffer)
  backLength = clibrary.cStringLength(buffer)
  test.assertEqualInt64(22, backLength)
  rewindStream(file)
  cells = heap.take(320)
  cursor = slotCursor(cells, 5)
  formatText = cText(firstFormat)
  stored = scanAll(file, formatText, cursor, false)
  test.assertTrue(stored == 5)
  wordLength = clibrary.cStringLength(cells)
  test.assertEqualInt64(3, wordLength)
  calc secondCell = cells + 64
  second = machine.loadInt32(secondCell)
  test.assertTrue(second == 42)
  calc thirdCell = cells + 128
  third = machine.loadInt32(thirdCell)
  test.assertTrue(third == -31)
  calc fourthCell = cells + 192
  fourth = machine.loadFloat64(fourthCell)
  test.assertTrue(fourth == 3.25)
  calc fifthCell = cells + 256
  fifth = machine.loadByte(fifthCell)
  test.assertTrue(fifth == 120)
  closeFile(file)
  blank = cText(blankText)
  blankStream = textStream(blank)
  numberFormatText = cText(numberFormat)
  blankCursor = slotCursor(cells, 1)
  blankResult = scanAll(blankStream, numberFormatText, blankCursor, false)
  test.assertTrue(blankResult == -1)
  letter = cText(letterText)
  letterStream = textStream(letter)
  letterCursor = slotCursor(cells, 1)
  letterResult = scanAll(letterStream, numberFormatText, letterCursor, false)
  test.assertTrue(letterResult == 0)
  number = cText(numberText)
  numberStream = textStream(number)
  countFormatText = cText(countFormat)
  countCursor = slotCursor(cells, 2)
  countResult = scanAll(numberStream, countFormatText, countCursor, false)
  test.assertTrue(countResult == 1)
  firstNumber = machine.loadInt32(cells)
  test.assertTrue(firstNumber == 12)
  counted = machine.loadInt32(secondCell)
  test.assertTrue(counted == 2)
  return

op wideOf "An ASCII text as a wide string (wchar_t of 4 bytes and a 0) in a new block"
  input text String borrowed
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
  when at >= bytes done copyOne
:copyOne in=eachByte
  calc sourceAt = textAt + at
  calc code = convert.byteToInt64(machine.loadByte(sourceAt))
  calc unitAt = block + at * 4
  machine.storeInt32(unitAt, clibrary.lowInt32(code))
  calc at := at + 1
  goto eachByte
:done
  return block

op cursorOf "A cursor of the tests' layout (one 8-byte slot an argument) over three words, its slots' block stored at an address"
  input first Int64 copied
  input second Int64 copied
  input third Int64 copied
  input slotsAt machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  slots = heap.take(40)
  machine.storeInt64(slots, first)
  calc secondAt = slots + 8
  machine.storeInt64(secondAt, second)
  calc thirdAt = slots + 16
  machine.storeInt64(thirdAt, third)
  calc cellAt = slots + 32
  machine.storeAddress(cellAt, slots)
  cursor = heap.take(16)
  machine.storeInt64(cursor, 3)
  calc listPlace = cursor + 8
  machine.storeAddress(listPlace, cellAt)
  machine.storeAddress(slotsAt, slots)
  return cursor

op unitOf "The wide character at an index of a wide string"
  input text machine.Address copied
  input index Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  calc unitAt = text + index * 4
  unit = machine.loadInt32(unitAt)
  calc code = convert.int32ToInt64(unit)
  return code

op narrowOf "A text as a C string in a new block"
  input text String borrowed
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  bytes = string.byteLength(text)
  textAt = machine.addressOfString(text)
  calc block = heap.take(bytes + 1)
  machine.copy(block, textAt, bytes)
  return block

test wideStreamTest "A stream made wide keeps its orientation and refuses fputs; fputwc, fwprintf's engine, fgetwc, fgetws, and ungetwc read and write the C locale's bytes; a character past 255 fails with EILSEQ; swprintf keeps every character and refuses what does not fit; swscanf and wscanf's engine read by wide formats"
  verifies orient keepsFirst
  verifies wideWriteFormatted writesWideBytes
  verifies wideStoreFormatted storesWide
  verifies wideScan scansWide
  verifies wideScanText scansWideText
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let nowhere Int64 0
:begin
  stream = temporaryFile()
  before = wideOrientation(stream, clibrary.lowInt32(0))
  test.assertTrue(before == 0)
  firstPut = widePut(stream, clibrary.lowInt32(104))
  test.assertTrue(firstPut == 104)
  kept = orient(stream, -1)
  test.assertEqualInt64(1, kept)
  bytes = narrowOf("x")
  refused = putStream(bytes, stream)
  test.assertTrue(refused == -1)
  pieces = wideOf("ab")
  slotsCell = heap.take(8)
  cursor = cursorOf(machine.toInt64(pieces), 42, 120, slotsCell)
  wideFormat = wideOf("%ls=%d|%3lc")
  written = wideWriteFormatted(stream, wideFormat, cursor)
  test.assertTrue(written == 9)
  heap.give(cursor)
  heap.give(machine.loadAddress(slotsCell))
  heap.give(wideFormat)
  noByte = widePut(stream, clibrary.lowInt32(20013))
  test.assertTrue(noByte == -1)
  errnoAt = clibrary.errnoCell()
  code = machine.loadInt32(errnoAt)
  test.assertTrue(code == 84)
  clearErrors(stream)
  rewindStream(stream)
  again = wideGet(stream)
  test.assertTrue(again == 104)
  line = heap.take(80)
  got = wideGetLine(line, clibrary.lowInt32(20), stream)
  sameLine = machine.equal(got, line)
  test.assertTrue(sameLine)
  test.assertEqualInt64(97, unitOf(line, 0))
  test.assertEqualInt64(52, unitOf(line, 3))
  test.assertEqualInt64(120, unitOf(line, 8))
  test.assertEqualInt64(0, unitOf(line, 9))
  wideRefused = wideUnget(clibrary.lowInt32(20013), stream)
  test.assertTrue(wideRefused == -1)
  pushed = wideUnget(clibrary.lowInt32(122), stream)
  test.assertTrue(pushed == 122)
  back = wideGet(stream)
  test.assertTrue(back == 122)
  closeFile(stream)
  target = heap.take(64)
  longText = wideOf("abcdef")
  longCursor = cursorOf(machine.toInt64(longText), 0, 0, slotsCell)
  textFormat = wideOf("%ls")
  tooLong = wideStoreFormatted(target, 4, textFormat, longCursor)
  test.assertTrue(tooLong == -1)
  test.assertEqualInt64(99, unitOf(target, 2))
  heap.give(longCursor)
  heap.give(machine.loadAddress(slotsCell))
  fitCursor = cursorOf(machine.toInt64(longText), 0, 0, slotsCell)
  fits = wideStoreFormatted(target, 10, textFormat, fitCursor)
  test.assertTrue(fits == 6)
  test.assertEqualInt64(102, unitOf(target, 5))
  test.assertEqualInt64(0, unitOf(target, 6))
  heap.give(fitCursor)
  heap.give(machine.loadAddress(slotsCell))
  charCursor = cursorOf(20013, 0, 0, slotsCell)
  charFormat = wideOf("<%lc>")
  oneChar = wideStoreFormatted(target, 10, charFormat, charCursor)
  test.assertTrue(oneChar == 3)
  test.assertEqualInt64(20013, unitOf(target, 1))
  test.assertEqualInt64(62, unitOf(target, 2))
  heap.give(charCursor)
  heap.give(machine.loadAddress(slotsCell))
  number = heap.take(8)
  word = heap.take(64)
  scanCursor = cursorOf(machine.toInt64(number), machine.toInt64(word), 0, slotsCell)
  inputText = wideOf(" 12 ab")
  scanFormat = wideOf("%d %ls")
  assigned = wideScanText(inputText, scanFormat, scanCursor, false)
  test.assertTrue(assigned == 2)
  scanned = machine.loadInt32(number)
  test.assertTrue(scanned == 12)
  test.assertEqualInt64(97, unitOf(word, 0))
  test.assertEqualInt64(98, unitOf(word, 1))
  test.assertEqualInt64(0, unitOf(word, 2))
  heap.give(scanCursor)
  heap.give(machine.loadAddress(slotsCell))
  fileStream = temporaryFile()
  putStream(narrowOf("7 x"), fileStream)
  rewindStream(fileStream)
  byteCursor = cursorOf(machine.toInt64(number), 0, 0, slotsCell)
  wideRead = wideScan(fileStream, scanFormat, byteCursor, false)
  test.assertTrue(wideRead == -1)
  heap.give(byteCursor)
  heap.give(machine.loadAddress(slotsCell))
  closeFile(fileStream)
  heap.give(inputText)
  heap.give(scanFormat)
  heap.give(word)
  heap.give(number)
  heap.give(charFormat)
  heap.give(textFormat)
  heap.give(longText)
  heap.give(target)
  heap.give(line)
  heap.give(pieces)
  heap.give(slotsCell)
  return
