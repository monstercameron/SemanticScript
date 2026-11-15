module sockets "TCP over IPv4 for a standalone executable: the net targets, through Winsock on Windows and socket system calls on Linux, with a resolver of names written here for Linux"
  path sockets
  imports standard.machine standard.system standard.string standard.math standard.compare standard.convert standard.bits standard.logic standard.test kernel memory numbers frames heap handles regions slots tasks files
  exports netCall

capability memoryAccess "Authority to keep sockets, addresses, and data in memory and read a call's slots" use machine.memory none

capability systemCalls "Authority to make, connect, and close sockets, read the resolver's files, and wait for the network" use system.calls none

## D-148: the net targets as host.py has them, IPv4 TCP only. A socket never blocks the program: it is
## non-blocking (WSAEventSelect on Windows, SOCK_NONBLOCK on Linux), and a call that would block waits through the
## scheduler (tasks.wait) on the socket's event (Windows) or its descriptor (Linux, read as POLLIN or POLLOUT), so
## other tasks run meanwhile, a deadline holds, and accept and read stop for a cancelled task as host.py's
## `_until_ready` stops them (connect and write, as host.py's, are not cancelled). Errors are what host.py's
## `_net_error` makes of Python's: a timeout (and ETIMEDOUT) timedOut, ECONNREFUSED refused, a reset, an abort, a
## broken pipe, or a shut-down socket closed, anything else failed with Python's errno (on Windows the Winsock code,
## as winerror_to_errno leaves it); a port that is not a whole number is failed 22. `net.listen` binds the host of
## the capability's scope (127.0.0.1 when it names none) with SO_REUSEADDR on Linux, as Python's socket does there,
## and listens with a backlog of 128. Names are resolved as getaddrinfo resolves them for create_connection, IPv4
## only: on Windows by ws2_32's getaddrinfo; on Linux (D-149) a numeric address in any form inet_aton reads, else the
## first IPv4 line of /etc/hosts that names the host, else an A query over UDP to the first nameserver of
## /etc/resolv.conf (127.0.0.1 when there is none), five seconds a try and two tries, as glibc's defaults are;
## a name that does not exist is EAI_NONAME (-2), one with no address EAI_NODATA (-5), no answer EAI_AGAIN (-3).
## A Listener or Connection is a heap block: at 0 the socket (Windows) or descriptor (Linux), 8 the Windows event.
## machine.state bytes 1248 to 1423 belong to this module: 1248 whether Winsock was started, 1256 a sockaddr_in,
## 1272 a WSANETWORKEVENTS, 1320 a length or option, 1328 getaddrinfo's result, 1336 its hints, 1384 the address a
## name resolved to, 1392 a number's digits, 1416 a number read from text.
constant startedAt "Where whether Winsock was started is kept, in machine.state" Int64 1248

constant addressAt "Where a sockaddr_in is put together, in machine.state" Int64 1256

constant eventsAt "Where WSAEnumNetworkEvents writes, in machine.state" Int64 1272

constant lengthAt "Where a length or an option's value is put, in machine.state" Int64 1320

constant infoAt "Where getaddrinfo writes its result, in machine.state" Int64 1328

constant hintsAt "Where getaddrinfo's hints are put together, in machine.state" Int64 1336

constant resolvedAt "Where the address a name resolved to is kept, in machine.state" Int64 1384

constant digitsAt "Where a number's digits are written, in machine.state" Int64 1392

constant kindListener "The kind of a TCP listener's handle" Int64 13

constant kindConnection "The kind of a TCP connection's handle" Int64 14

constant closedError "net.NetError.closed, numbered from 1" Int32 1

constant timedOutError "net.NetError.timedOut, numbered from 1" Int32 2

constant refusedError "net.NetError.refused, numbered from 1" Int32 3

constant cancelledError "net.NetError.cancelled, numbered from 1" Int32 4

constant failedError "net.NetError.failed, numbered from 1" Int32 5

constant wouldBlock "WSAEWOULDBLOCK" Int64 10035

constant again "EAGAIN on Linux" Int64 11

constant inProgress "EINPROGRESS on Linux" Int64 115

constant never "time.Deadline.never" Int64 -1

constant forever "The bound of a loop that waits as long as it takes" Int64 9223372036854775807

constant mostRead "The most bytes one read takes from a socket at once" Int64 1048576

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

op failText "Report a trap with a message and end the process with exit code 70"
  input text String borrowed
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  findText: textAt = machine.addressOfString(text)
  textLength: bytes = string.byteLength(text)
  writeReport: status = frames.report(textAt, bytes)
  exit: endProcess(trapCode=70)
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

op byteOf "The byte of a text at a position, as a whole number"
  input text machine.Address copied
  input at Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  locate: place = machine.offset(text, at)
  readByte: byte = machine.loadByte(place)
  widen: value = convert.byteToInt64(byte)
  return value

op storeByteValue "Store a byte given as a whole number at a position"
  input target machine.Address copied
  input at Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  locate: place = machine.offset(target, at)
  lowOf: low = bits.andInt64(value, n255=255)
  narrowIt: byte = convert.int64ToByte(low)
  storeIt: machine.storeByte(place, byte)
  return

## ---------------------------------------------------------------- errors

op winsockErrno "A Winsock error as the errno Python gives it (winerror_to_errno): the six Winsock copies of C errnos become them, the rest stay as they are"
  input code Int64 copied
  output Int64
  let n4 Int64 4
  let n9 Int64 9
  let n13 Int64 13
  let n14 Int64 14
  let n22 Int64 22
  let n24 Int64 24
:begin
  interruptCheck: isInterrupt = compare.equalInt64(code, n10004=10004)
  if isInterrupt giveInterrupt badCheck
:giveInterrupt
  return n4
:badCheck
  checkBad: isBad = compare.equalInt64(code, n10009=10009)
  if isBad giveBad accessCheck
:giveBad
  return n9
:accessCheck
  checkAccess: isAccess = compare.equalInt64(code, n10013=10013)
  if isAccess giveAccess faultCheck
:giveAccess
  return n13
:faultCheck
  checkFault: isFault = compare.equalInt64(code, n10014=10014)
  if isFault giveFault invalidCheck
:giveFault
  return n14
:invalidCheck
  checkInvalid: isInvalid = compare.equalInt64(code, n10022=10022)
  if isInvalid giveInvalid filesCheck
:giveInvalid
  return n22
:filesCheck
  checkFiles: isFiles = compare.equalInt64(code, n10024=10024)
  if isFiles giveFiles giveSame
:giveFiles
  return n24
:giveSame
  return code

op lastWinsock "The last Winsock error as Python's errno"
  output Int64
  effect use system.calls
  uses systemCalls
:begin
  readIt: code = system.wsaGetLastError()
  widen: wide1 = convert.int32ToInt64(code)
  mapIt: errno = winsockErrno(wide1)
  return errno

op netError "The NetError host.py's _net_error makes of an errno: timedOut, refused, closed, or failed with it (1 for 0)"
  input payload machine.Address copied
  input errno Int64 copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  let value Int64 0 mut
  let one Int64 1
:begin
  set value errno
  timeLinux: isTimeLinux = compare.equalInt64(errno, n110=110)
  timeWindows: isTimeWindows = compare.equalInt64(errno, n10060=10060)
  timeCheck: isTime = logic.or(isTimeLinux, isTimeWindows)
  if isTime giveTimedOut refusedCheck
:giveTimedOut
  timedStatus: status1 = slots.failWith(payload, timedOutError, zero=0)
  return status1
:refusedCheck
  refusedLinux: isRefusedLinux = compare.equalInt64(errno, n111=111)
  refusedWindows: isRefusedWindows = compare.equalInt64(errno, n10061=10061)
  checkRefused: isRefused = logic.or(isRefusedLinux, isRefusedWindows)
  if isRefused giveRefused closedCheck
:giveRefused
  refusedStatus: status2 = slots.failWith(payload, refusedError, zero)
  return status2
:closedCheck
  resetLinux: isResetLinux = compare.equalInt64(errno, n104=104)
  abortLinux: isAbortLinux = compare.equalInt64(errno, n103=103)
  pipeLinux: isPipe = compare.equalInt64(errno, n32=32)
  downLinux: isDownLinux = compare.equalInt64(errno, n108=108)
  resetWindows: isResetWindows = compare.equalInt64(errno, n10054=10054)
  abortWindows: isAbortWindows = compare.equalInt64(errno, n10053=10053)
  downWindows: isDownWindows = compare.equalInt64(errno, n10058=10058)
  either1: closed1 = logic.or(isResetLinux, isAbortLinux)
  either2: closed2 = logic.or(isPipe, isDownLinux)
  either3: closed3 = logic.or(isResetWindows, isAbortWindows)
  either4: closed4 = logic.or(closed1, closed2)
  either5: closed5 = logic.or(closed3, isDownWindows)
  either6: isClosed = logic.or(closed4, closed5)
  if isClosed giveClosed failed
:giveClosed
  closedStatus: status3 = slots.failWith(payload, closedError, zero)
  return status3
:failed
  zeroCheck: isZero = compare.equalInt64(errno, zero)
  if isZero one1 giveFailed
:one1
  set value one
  goto giveFailed
:giveFailed
  failedStatus: status4 = slots.failWith(payload, failedError, value)
  return status4

op cancelledStatus "net.NetError.cancelled"
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  uses memoryAccess
:begin
  giveIt: status = slots.failWith(payload, cancelledError, zero=0)
  return status

op timedOutStatus "net.NetError.timedOut"
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  uses memoryAccess
:begin
  giveIt: status = slots.failWith(payload, timedOutError, zero=0)
  return status

## ---------------------------------------------------------------- sockets

op startWinsock "Start Winsock 2.2 the first time a socket is made (Windows)"
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readStarted: started = stateWord(startedAt)
  startedCheck: done = compare.notEqualInt64(started, zero=0)
  if done finish start
:start
  takeData: data = heap.take(n512=512)
  startIt: status = system.wsaStartup(version=514, data)
  findStarted: startedSlot = kernel.stateAt(startedAt)
  storeStarted: machine.storeInt64(startedSlot, one=1)
  goto finish
:finish
  return

op makeObject "A Listener or Connection's heap block, holding a socket and its Windows event"
  input socket Int64 copied
  input event machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  takeIt: object = heap.take(sixteen=16)
  storeSocket: machine.storeInt64(object, socket)
  findEvent: eventSlot = machine.offset(object, eight=8)
  storeEvent: machine.storeAddress(eventSlot, event)
  return object

op socketOf "The socket a Listener or Connection holds"
  input object machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  readIt: socket = machine.loadInt64(object)
  return socket

op eventOf "The Windows event a Listener or Connection holds"
  input object machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findEvent: eventSlot = machine.offset(object, eight=8)
  readIt: event = machine.loadAddress(eventSlot)
  return event

op closeSocket "Close a socket (closesocket, or close on Linux) and its Windows event"
  input socket Int64 copied
  input event machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  osCheck: onLinux = system.posix()
  if onLinux closeLinux closeWindows
:closeLinux
  closeIt: closed = system.close(socket)
  return
:closeWindows
  asAddress: handle = machine.fromInt64(socket)
  closeSocketIt: socketClosed = system.closesocket(handle)
  nowhere: anywhere = machine.zero()
  noEventCheck: noEvent = machine.equal(event, anywhere)
  if noEvent done closeEvent
:closeEvent
  closeEventIt: eventClosed = system.closeHandle(event)
  goto done
:done
  return

op selectEvents "Tie a socket to a new event that its network events set, which makes it non-blocking (WSAEventSelect)"
  input socket Int64 copied
  input events Int32 copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere: anywhere = machine.zero()
  makeEvent: event = system.createEventW(anywhere, manual=1, notSignalled=0, anywhere)
  asAddress: handle = machine.fromInt64(socket)
  selectIt: selected = system.wsaEventSelect(handle, event, events)
  return event

op waitFor "Wait through the scheduler for a socket to be ready: its event (Windows) or its descriptor for reading or writing (Linux); 2 cancelled (when the wait is cancellable), 1 past the deadline, else 0"
  input object machine.Address copied
  input deadline Int64 copied
  input cancellable Int64 copied
  input writing Bool copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let external machine.Address unset mut
:begin
  osCheck: onLinux = system.posix()
  if onLinux linuxExternal windowsExternal
:windowsExternal
  readEvent: event = eventOf(object)
  set external event
  goto waitIt
:linuxExternal
  readSocket: fd = socketOf(object)
  plusOne: entry = math.addInt64(fd, one=1)
  if writing forWriting forReading
:forWriting
  markWrite: writeEntry = math.addInt64(entry, writeMark=4294967296)
  writeAddress: writeExternal = machine.fromInt64(writeEntry)
  set external writeExternal
  goto waitIt
:forReading
  readAddress: readExternal = machine.fromInt64(entry)
  set external readExternal
  goto waitIt
:waitIt
  waitOnce: outcome = tasks.wait(networkText="a network wait", deadline, cancellable, external)
  return outcome

op deadlinePassed "Whether a deadline has passed (never for time.Deadline.never)"
  input deadline Int64 copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let no Bool false
:begin
  neverCheck: isNever = compare.equalInt64(deadline, never)
  if isNever notYet compareIt
:notYet
  return no
:compareIt
  readNow: moment = tasks.now()
  pastCheck: past = compare.greaterOrEqualInt64(moment, deadline)
  return past

op prepare "Ready a socket for an attempt: reset its Windows event, so what the attempt leaves undone sets it again"
  input object machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  osCheck: onLinux = system.posix()
  if onLinux done reset
:reset
  readEvent: event = eventOf(object)
  resetIt: wasReset = system.resetEvent(event)
  return
:done
  return

op putAddress "Put a sockaddr_in in machine.state for an IPv4 address (a whole number, its first byte highest) and a port, and give it"
  input address Int64 copied
  input port Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  findAddress: sockaddr = kernel.stateAt(addressAt)
  clearIt: machine.fill(sockaddr, zeroByte=0, sixteen=16)
  storeFamily: storeByteValue(sockaddr, zero=0, two=2)
  portHigh: high = bits.shiftRightInt64(port, eight=8)
  storePortHigh: storeByteValue(sockaddr, two, high)
  storePortLow: storeByteValue(sockaddr, three=3, port)
  byte0: a = bits.shiftRightInt64(address, twentyFour=24)
  storeA: storeByteValue(sockaddr, four=4, a)
  byte1: b = bits.shiftRightInt64(address, sixteen)
  storeB: storeByteValue(sockaddr, five=5, b)
  byte2: c = bits.shiftRightInt64(address, eight)
  storeC: storeByteValue(sockaddr, six=6, c)
  storeD: storeByteValue(sockaddr, seven=7, address)
  return sockaddr

## ---------------------------------------------------------------- addresses and names

op dottedQuad "Read text as inet_pton reads an IPv4 address (four decimal parts of 0 to 255, no leading zeros) into resolvedAt: 1 when it is one, else 0"
  input text machine.Address copied
  input bytes Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let part Int64 0 mut
  let parts Int64 0 mut
  let digits Int64 0 mut
  let value Int64 0 mut
  let first Int64 0 mut
  let no Int64 0
  let yes Int64 1
:begin
  goto eachByte
:eachByte loop=while max=bytes
  endCheck: atEnd = compare.greaterOrEqualInt64(at, bytes)
  if atEnd lastPart readOne
:readOne in=eachByte
  readIt: byte = byteOf(text, at)
  dotCheck: isDot = compare.equalInt64(byte, dot=46)
  if isDot endPart digitCheck
:digitCheck in=eachByte
  lowDigit: aboveZero = compare.greaterOrEqualInt64(byte, digitZero=48)
  highDigit: belowNine = compare.lessOrEqualInt64(byte, digitNine=57)
  isDigitCheck: isDigit = logic.and(aboveZero, belowNine)
  if isDigit addDigit refuse
:addDigit in=eachByte
  leadingCheck: hasDigits = compare.greaterThanInt64(digits, no)
  zeroLead: leadZero = compare.equalInt64(first, digitZero)
  bothLead: badLead = logic.and(hasDigits, leadZero)
  if badLead refuse takeDigit
:takeDigit in=eachByte
  firstCheck: noDigits = compare.equalInt64(digits, no)
  if noDigits keepFirst accumulate
:keepFirst in=eachByte
  set first byte
  goto accumulate
:accumulate in=eachByte
  tenTimes: shifted = math.multiplyInt64(part, ten=10)
  digitOf: digit = math.subtractInt64(byte, digitZero)
  addIt: grown = math.addInt64(shifted, digit)
  set part grown
  moreDigits: afterDigits = math.addInt64(digits, yes)
  set digits afterDigits
  bigCheck: tooBig = compare.greaterThanInt64(part, n255=255)
  if tooBig refuse advance
:endPart in=eachByte
  emptyCheck: empty = compare.equalInt64(digits, no)
  manyCheck: many = compare.greaterOrEqualInt64(parts, three=3)
  badPart: bad = logic.or(empty, many)
  if bad refuse keepPart
:keepPart in=eachByte
  shiftValue: moved = bits.shiftLeftInt64(value, eight=8)
  joinValue: joined = bits.orInt64(moved, part)
  set value joined
  moreParts: afterParts = math.addInt64(parts, yes)
  set parts afterParts
  set part no
  set digits no
  goto advance
:advance in=eachByte
  nextAt: after = math.addInt64(at, yes)
  set at after
  goto eachByte
:lastPart
  lastEmpty: emptyLast = compare.equalInt64(digits, no)
  threeCheck: allParts = compare.equalInt64(parts, three)
  goodCheck: notEmpty = logic.not(emptyLast)
  bothCheck: good = logic.and(notEmpty, allParts)
  if good give refuse
:give
  shiftLast: movedLast = bits.shiftLeftInt64(value, eight)
  joinLast: address = bits.orInt64(movedLast, part)
  findResolved: resolved = kernel.stateAt(resolvedAt)
  storeIt: machine.storeInt64(resolved, address)
  return yes
:refuse
  return no

op atonPart "Read one part of an inet_aton address from a position (hexadecimal after 0x, octal after a leading 0, else decimal) into resolvedAt+8; give the position after it, or -1 when it is not a number"
  input text machine.Address copied
  input bytes Int64 copied
  input from Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let base Int64 10 mut
  let value Int64 0 mut
  let digits Int64 0 mut
  let bad Int64 -1
  let limit Int64 4294967295
  let sixteen Int64 16
  let eight Int64 8
:begin
  set at from
  zeroCheck: startsZero = startsWith(text, bytes, at, digitZero=48)
  if startsZero octalOrHex eachDigit
:octalOrHex
  afterZero: next = math.addInt64(at, one=1)
  smallX: isSmallX = startsWith(text, bytes, next, smallXCode=120)
  bigX: isBigX = startsWith(text, bytes, next, bigXCode=88)
  eitherX: isX = logic.or(isSmallX, isBigX)
  if isX hex octal
:hex
  set base sixteen
  pastX: afterX = math.addInt64(next, one)
  set at afterX
  set digits one
  goto eachDigit
:octal
  set base eight
  goto eachDigit
:eachDigit loop=while max=bytes
  endCheck: atEnd = compare.greaterOrEqualInt64(at, bytes)
  if atEnd finish readOne
:readOne in=eachDigit
  readIt: byte = byteOf(text, at)
  valueOf: digit = digitValue(byte)
  noDigit: notDigit = compare.lessThanInt64(digit, zero=0)
  pastBase: overBase = compare.greaterOrEqualInt64(digit, base)
  stopCheck: stop = logic.or(notDigit, overBase)
  if stop finish take
:take in=eachDigit
  timesBase: shifted = math.multiplyInt64(value, base)
  addIt: grown = math.addInt64(shifted, digit)
  set value grown
  bigCheck: tooBig = compare.greaterThanInt64(grown, limit)
  if tooBig refuse advance
:advance in=eachDigit
  moreDigits: afterDigits = math.addInt64(digits, one)
  set digits afterDigits
  nextAt: after = math.addInt64(at, one)
  set at after
  goto eachDigit
:finish
  hexOnly: emptyHex = compare.equalInt64(base, sixteen)
  oneDigit: onlyX = compare.equalInt64(digits, one)
  bareX: bare = logic.and(emptyHex, onlyX)
  noneCheck: nothing = compare.equalInt64(digits, zero)
  badCheck: refused = logic.or(bare, nothing)
  if refused refuse give
:give
  findValue: valueSlot = kernel.stateAt(partAt=1416)
  storeIt: machine.storeInt64(valueSlot, value)
  return at
:refuse
  return bad

op startsWith "Whether a position is inside a text and holds a byte"
  input text machine.Address copied
  input bytes Int64 copied
  input at Int64 copied
  input wanted Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let no Bool false
:begin
  insideCheck: inside = compare.lessThanInt64(at, bytes)
  if inside readIt outside
:outside
  return no
:readIt
  readByte: byte = byteOf(text, at)
  sameCheck: same = compare.equalInt64(byte, wanted)
  return same

op digitValue "A byte's value as a digit of up to base 16, or -1"
  input byte Int64 copied
  output Int64
  let bad Int64 -1
:begin
  lowDigit: aboveZero = compare.greaterOrEqualInt64(byte, digitZero=48)
  highDigit: belowNine = compare.lessOrEqualInt64(byte, digitNine=57)
  isDigitCheck: isDigit = logic.and(aboveZero, belowNine)
  if isDigit giveDigit lowerCheck
:giveDigit
  digitOf: digit = math.subtractInt64(byte, digitZero)
  return digit
:lowerCheck
  lowA: aboveA = compare.greaterOrEqualInt64(byte, smallA=97)
  lowF: belowF = compare.lessOrEqualInt64(byte, smallF=102)
  isLowerCheck: isLower = logic.and(aboveA, belowF)
  if isLower giveLower upperCheck
:giveLower
  lowerOf: lower = math.subtractInt64(byte, n87=87)
  return lower
:upperCheck
  upA: aboveBigA = compare.greaterOrEqualInt64(byte, bigA=65)
  upF: belowBigF = compare.lessOrEqualInt64(byte, bigF=70)
  isUpperCheck: isUpper = logic.and(aboveBigA, belowBigF)
  if isUpper giveUpper giveBad
:giveUpper
  upperOf: upper = math.subtractInt64(byte, n55=55)
  return upper
:giveBad
  return bad

op atonAddress "Read text as glibc's inet_aton reads an IPv4 address, the whole text: one to four parts (each decimal, octal, or hexadecimal), the last filling the bytes left; 1 into resolvedAt when it is one, else 0"
  input text machine.Address copied
  input bytes Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let parts Int64 0 mut
  let value Int64 0 mut
  let no Int64 0
  let yes Int64 1
:begin
  emptyCheck: empty = compare.equalInt64(bytes, no)
  if empty refuse eachPart
:eachPart loop=while max=4
  readPart: after = atonPart(text, bytes, at)
  badCheck: bad = compare.lessThanInt64(after, no)
  if bad refuse keep
:keep in=eachPart
  findValue: valueSlot = kernel.stateAt(partAt=1416)
  readValue: part = machine.loadInt64(valueSlot)
  moreParts: count = math.addInt64(parts, yes)
  set parts count
  endCheck: atEnd = compare.greaterOrEqualInt64(after, bytes)
  if atEnd last dotCheck
:dotCheck in=eachPart
  isDotCheck: isDot = startsWith(text, bytes, after, dot=46)
  smallCheck: fewParts = compare.lessThanInt64(count, four=4)
  bothCheck: goOn = logic.and(isDot, fewParts)
  if goOn middle refuse
:middle in=eachPart
  byteCheck: fits = compare.lessOrEqualInt64(part, n255=255)
  if fits addMiddle refuse
:addMiddle in=eachPart
  shiftValue: moved = bits.shiftLeftInt64(value, eight=8)
  joinValue: joined = bits.orInt64(moved, part)
  set value joined
  pastDot: next = math.addInt64(after, yes)
  set at next
  goto eachPart
:last
  leftOf: left = math.subtractInt64(four, count)
  plusOne: spare = math.addInt64(left, yes)
  bitsOf: room = math.multiplyInt64(spare, eight)
  fullCheck: allRoom = compare.greaterOrEqualInt64(room, thirtyTwo=32)
  if allRoom joinLast limitCheck
:limitCheck
  limitOf: limit = bits.shiftLeftInt64(yes, room)
  overCheck: over = compare.greaterOrEqualInt64(part, limit)
  if over refuse joinLast
:joinLast
  movedOf: shifted = bits.shiftLeftInt64(value, room)
  wordLimit: wordFits = compare.lessOrEqualInt64(part, n4294967295=4294967295)
  if wordFits store refuse
:store
  joinIt: address = bits.orInt64(shifted, part)
  maskIt: masked = bits.andInt64(address, n4294967295)
  findResolved: resolved = kernel.stateAt(resolvedAt)
  storeIt: machine.storeInt64(resolved, masked)
  return yes
:refuse
  return no

op readSmallFile "A file's bytes (up to 1 MiB) in a new heap block, its length stored at an address; the address 0 when it cannot be read (Linux)"
  input path String borrowed
  input length machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let total Int64 0 mut
  let most Int64 1048576
:begin
  findPath: pathAt = machine.addressOfString(path)
  pathBytes: bytes = string.byteLength(path)
  copySize: copyBytes = math.addInt64(bytes, one=1)
  takeName: name = heap.take(copyBytes)
  copyName: machine.copy(name, pathAt, bytes)
  openIt: fd = system.openat(currentDirectory=-100, name, readOnlyCloseOnExec=524288, zero=0)
  giveName: heap.give(name)
  failedCheck: refused = kernel.failed(fd)
  if refused giveNone read
:giveNone
  nowhere: anywhere = machine.zero()
  return anywhere
:read
  roomOf: room = math.addInt64(most, one)
  takeData: data = heap.take(room)
  goto eachRead
:eachRead loop=while max=most
  fullCheck: full = compare.greaterOrEqualInt64(total, most)
  if full finish readSome
:readSome in=eachRead
  findPlace: place = machine.offset(data, total)
  leftOf: left = math.subtractInt64(most, total)
  readIt: got = system.read(fd, place, left)
  stopCheck: stop = compare.lessOrEqualInt64(got, zero)
  if stop finish count
:count in=eachRead
  moreTotal: after = math.addInt64(total, got)
  set total after
  goto eachRead
:finish
  closeIt: closed = system.close(fd)
  storeLength: machine.storeInt64(length, total)
  return data

op lowerByte "A byte lower-cased if it is an ASCII capital"
  input value Int64 copied
  output Int64
:begin
  lowCheck: aboveA = compare.greaterOrEqualInt64(value, bigA=65)
  highCheck: belowZ = compare.lessOrEqualInt64(value, bigZ=90)
  capitalCheck: capital = logic.and(aboveA, belowZ)
  if capital lower keep
:lower
  lowered: small = math.addInt64(value, thirtyTwo=32)
  return small
:keep
  return value

op sameName "Whether a range of bytes is a name in any case of ASCII"
  input text machine.Address copied
  input start Int64 copied
  input end Int64 copied
  input name machine.Address copied
  input nameBytes Int64 copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let yes Bool true
  let no Bool false
:begin
  lengthOf: length = math.subtractInt64(end, start)
  lengthCheck: sameLength = compare.equalInt64(length, nameBytes)
  if sameLength eachByte differ
:eachByte loop=while max=nameBytes
  doneCheck: done = compare.greaterOrEqualInt64(at, nameBytes)
  if done same compareOne
:compareOne in=eachByte
  placeOf: place = math.addInt64(start, at)
  readOne: left = byteOf(text, place)
  readOther: right = byteOf(name, at)
  lowerOne: leftLower = lowerByte(left)
  lowerOther: rightLower = lowerByte(right)
  equalCheck: equal = compare.equalInt64(leftLower, rightLower)
  if equal advance differ
:advance in=eachByte
  nextAt: after = math.addInt64(at, one=1)
  set at after
  goto eachByte
:same
  return yes
:differ
  return no

op isSpace "Whether a byte separates the fields of /etc/hosts and /etc/resolv.conf: space or tab"
  input value Int64 copied
  output Bool
:begin
  spaceCheck: isSpace1 = compare.equalInt64(value, space=32)
  tabCheck: isTab = compare.equalInt64(value, tab=9)
  either: blank = logic.or(isSpace1, isTab)
  return blank

op fieldEnd "The end of the field that starts at a position: the next space, tab, line end, or comment, or the line's end"
  input text machine.Address copied
  input from Int64 copied
  input to Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  set at from
  goto eachByte
:eachByte loop=while max=to
  endCheck: atEnd = compare.greaterOrEqualInt64(at, to)
  if atEnd give readOne
:readOne in=eachByte
  readIt: byte = byteOf(text, at)
  blankCheck: blank = isSpace(byte)
  hashCheck: isHash = compare.equalInt64(byte, hash=35)
  stopCheck: stop = logic.or(blank, isHash)
  if stop give advance
:advance in=eachByte
  nextAt: after = math.addInt64(at, one=1)
  set at after
  goto eachByte
:give
  return at

op fieldStart "The first position from one that is not a space or a tab, or the line's end"
  input text machine.Address copied
  input from Int64 copied
  input to Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  set at from
  goto eachByte
:eachByte loop=while max=to
  endCheck: atEnd = compare.greaterOrEqualInt64(at, to)
  if atEnd give readOne
:readOne in=eachByte
  readIt: byte = byteOf(text, at)
  blankCheck: blank = isSpace(byte)
  if blank advance give
:advance in=eachByte
  nextAt: after = math.addInt64(at, one=1)
  set at after
  goto eachByte
:give
  return at

op lineEnd "The position of the next line feed from a position, or the text's end"
  input text machine.Address copied
  input from Int64 copied
  input to Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  set at from
  goto eachByte
:eachByte loop=while max=to
  endCheck: atEnd = compare.greaterOrEqualInt64(at, to)
  if atEnd give readOne
:readOne in=eachByte
  readIt: byte = byteOf(text, at)
  lineCheck: isLine = compare.equalInt64(byte, lineFeed=10)
  if isLine give advance
:advance in=eachByte
  nextAt: after = math.addInt64(at, one=1)
  set at after
  goto eachByte
:give
  return at

op hostsLookup "The first IPv4 line of /etc/hosts that names a host (in any case of ASCII), its address into resolvedAt: 1 when found, else 0"
  input name machine.Address copied
  input nameBytes Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let found Int64 0 mut
  let address Int64 0 mut
  let field Int64 0 mut
  let no Int64 0
  let yes Int64 1
:begin
  findLength: lengthSlot = kernel.stateAt(lengthAt)
  readIt: text = readSmallFile(hostsPath="/etc/hosts", lengthSlot)
  nowhere: anywhere = machine.zero()
  missingCheck: missing = machine.equal(text, anywhere)
  if missing giveNo scan
:giveNo
  return no
:scan
  readLength: bytes = machine.loadInt64(lengthSlot)
  goto eachLine
:eachLine loop=while max=bytes
  endCheck: atEnd = compare.greaterOrEqualInt64(at, bytes)
  if atEnd finish readLine
:readLine in=eachLine
  lineStop: stop = lineEnd(text, at, bytes)
  addressStart: start = fieldStart(text, at, stop)
  addressEnd: end = fieldEnd(text, start, stop)
  findAddress: addressText = machine.offset(text, start)
  addressLength: addressBytes = math.subtractInt64(end, start)
  quadIt: isQuad = dottedQuad(addressText, addressBytes)
  quadCheck: quad = compare.equalInt64(isQuad, yes)
  if quad keepAddress nextLine
:keepAddress in=eachLine
  findResolved: resolved = kernel.stateAt(resolvedAt)
  readAddress: lineAddress = machine.loadInt64(resolved)
  set address lineAddress
  set field end
  goto eachName
:eachName loop=while max=bytes in=eachLine
  nameStart: nameFrom = fieldStart(text, field, stop)
  lineDone: noMore = compare.greaterOrEqualInt64(nameFrom, stop)
  commentCheck: isComment = startsWith(text, bytes, nameFrom, hash=35)
  doneCheck: done = logic.or(noMore, isComment)
  if done nextLine compareName
:compareName in=eachName
  nameEnd: nameTo = fieldEnd(text, nameFrom, stop)
  sameCheck: same = sameName(text, nameFrom, nameTo, name, nameBytes)
  if same foundIt nextName
:nextName in=eachName
  set field nameTo
  goto eachName
:foundIt
  set found yes
  goto finish
:nextLine in=eachLine
  pastLine: after = math.addInt64(stop, yes)
  set at after
  goto eachLine
:finish
  giveText: heap.give(text)
  foundCheck: wasFound = compare.equalInt64(found, yes)
  if wasFound storeFound giveFound
:storeFound
  findResolvedAgain: resolvedAgain = kernel.stateAt(resolvedAt)
  storeIt: machine.storeInt64(resolvedAgain, address)
  goto giveFound
:giveFound
  return found

op nameserver "The first IPv4 nameserver /etc/resolv.conf names, or 127.0.0.1 (0x7f000001) when it names none"
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
  let server Int64 2130706433 mut
  let keyword String "nameserver"
:begin
  findLength: lengthSlot = kernel.stateAt(lengthAt)
  readIt: text = readSmallFile(resolvPath="/etc/resolv.conf", lengthSlot)
  nowhere: anywhere = machine.zero()
  missingCheck: missing = machine.equal(text, anywhere)
  if missing give scan
:scan
  readLength: bytes = machine.loadInt64(lengthSlot)
  goto eachLine
:eachLine loop=while max=bytes
  endCheck: atEnd = compare.greaterOrEqualInt64(at, bytes)
  if atEnd finish readLine
:readLine in=eachLine
  lineStop: stop = lineEnd(text, at, bytes)
  keyStart: start = fieldStart(text, at, stop)
  keyEnd: end = fieldEnd(text, start, stop)
  findKeyword: keywordAt = machine.addressOfString(keyword)
  sameCheck: isKeyword = sameName(text, start, end, keywordAt, ten=10)
  if isKeyword readServer nextLine
:readServer in=eachLine
  serverStart: serverFrom = fieldStart(text, end, stop)
  serverEnd: serverTo = fieldEnd(text, serverFrom, stop)
  findServer: serverText = machine.offset(text, serverFrom)
  serverLength: serverBytes = math.subtractInt64(serverTo, serverFrom)
  quadIt: isQuad = dottedQuad(serverText, serverBytes)
  quadCheck: quad = compare.equalInt64(isQuad, one=1)
  if quad keepServer nextLine
:keepServer
  findResolved: resolved = kernel.stateAt(resolvedAt)
  readServerAddress: address = machine.loadInt64(resolved)
  set server address
  goto finish
:nextLine in=eachLine
  pastLine: after = math.addInt64(stop, one)
  set at after
  goto eachLine
:finish
  giveText: heap.give(text)
  goto give
:give
  return server

op putName "Write a host name as DNS labels at a position of a query; the position after them, or -1 when a label is empty or longer than 63 bytes or the name longer than 253"
  input query machine.Address copied
  input from Int64 copied
  input name machine.Address copied
  input nameBytes Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let out Int64 0 mut
  let bad Int64 -1
  let size Int64 0 mut
:begin
  set size nameBytes
  trailingCheck: hasBytes = compare.greaterThanInt64(nameBytes, zero=0)
  if hasBytes lastDot tooLongCheck
:lastDot
  lastOf: lastAt = math.subtractInt64(nameBytes, one=1)
  readLast: last = byteOf(name, lastAt)
  dotCheck: endsDot = compare.equalInt64(last, dot=46)
  if endsDot dropDot tooLongCheck
:dropDot
  set size lastAt
  goto tooLongCheck
:tooLongCheck
  longCheck: tooLong = compare.greaterThanInt64(size, n253=253)
  emptyCheck: empty = compare.equalInt64(size, zero)
  badName: refused = logic.or(tooLong, empty)
  if refused refuse labels
:labels
  set out from
  goto eachLabel
:eachLabel loop=while max=nameBytes
  labelEnd: end = labelStop(name, at, size)
  labelLength: length = math.subtractInt64(end, at)
  emptyLabel: noBytes = compare.equalInt64(length, zero)
  longLabel: over = compare.greaterThanInt64(length, n63=63)
  badLabel: badOne = logic.or(noBytes, over)
  if badOne refuse writeLabel
:writeLabel in=eachLabel
  storeLength: storeByteValue(query, out, length)
  afterLength: dataAt = math.addInt64(out, one)
  findTarget: target = machine.offset(query, dataAt)
  findSource: source = machine.offset(name, at)
  copyLabel: machine.copy(target, source, length)
  afterLabel: next = math.addInt64(dataAt, length)
  set out next
  lastCheck: isLast = compare.greaterOrEqualInt64(end, size)
  if isLast finish nextLabel
:nextLabel in=eachLabel
  pastDot: afterDot = math.addInt64(end, one)
  set at afterDot
  goto eachLabel
:finish
  storeRoot: storeByteValue(query, out, zero)
  afterRoot: done = math.addInt64(out, one)
  return done
:refuse
  return bad

op labelStop "The position of the next dot from a position, or the name's end"
  input name machine.Address copied
  input from Int64 copied
  input size Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  set at from
  goto eachByte
:eachByte loop=while max=size
  endCheck: atEnd = compare.greaterOrEqualInt64(at, size)
  if atEnd give readOne
:readOne in=eachByte
  readIt: byte = byteOf(name, at)
  dotCheck: isDot = compare.equalInt64(byte, dot=46)
  if isDot give advance
:advance in=eachByte
  nextAt: after = math.addInt64(at, one=1)
  set at after
  goto eachByte
:give
  return at

op word16 "A big-endian 16-bit number at a position of a reply"
  input reply machine.Address copied
  input at Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  readHigh: high = byteOf(reply, at)
  nextAt: lowAt = math.addInt64(at, one=1)
  readLow: low = byteOf(reply, lowAt)
  shiftHigh: moved = bits.shiftLeftInt64(high, eight=8)
  joinIt: value = bits.orInt64(moved, low)
  return value

op skipName "The position after a DNS name in a reply (labels, or a pointer that ends it), or -1 when it runs past the reply"
  input reply machine.Address copied
  input bytes Int64 copied
  input from Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let bad Int64 -1
:begin
  set at from
  goto eachLabel
:eachLabel loop=while max=bytes
  endCheck: atEnd = compare.greaterOrEqualInt64(at, bytes)
  if atEnd refuse readOne
:readOne in=eachLabel
  readLength: length = byteOf(reply, at)
  rootCheck: isRoot = compare.equalInt64(length, zero=0)
  if isRoot giveRoot pointerCheck
:giveRoot
  afterRoot: pastRoot = math.addInt64(at, one=1)
  return pastRoot
:pointerCheck in=eachLabel
  checkPointer: isPointer = compare.greaterOrEqualInt64(length, n192=192)
  if isPointer givePointer label
:givePointer
  afterPointer: pastPointer = math.addInt64(at, two=2)
  return pastPointer
:label in=eachLabel
  pastLabel: next = math.addInt64(at, length)
  pastLength: afterLabel = math.addInt64(next, one)
  set at afterLabel
  goto eachLabel
:refuse
  return bad

op readAnswer "The first A record of a DNS reply into resolvedAt: 0 when found, else the getaddrinfo error: EAI_NONAME (-2) for a name that does not exist, EAI_AGAIN (-3) for a server's failure, EAI_NODATA (-5) for a name with no address"
  input reply machine.Address copied
  input bytes Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 12 mut
  let k Int64 0 mut
  let noName Int64 -2
  let tryAgain Int64 -3
  let noData Int64 -5
  let found Int64 0
:begin
  shortCheck: short = compare.lessThanInt64(bytes, twelve=12)
  if short giveAgain header
:header
  readFlags: flags = word16(reply, two=2)
  codeOf: rcode = bits.andInt64(flags, fifteen=15)
  nameCheck: noSuchName = compare.equalInt64(rcode, three=3)
  if noSuchName giveNoName failureCheck
:failureCheck
  okCheck: fine = compare.equalInt64(rcode, zero=0)
  if fine counts giveAgain
:counts
  readQuestions: questions = word16(reply, four=4)
  readAnswers: answers = word16(reply, six=6)
  goto eachQuestion
:eachQuestion loop=while max=questions
  questionsDone: allQuestions = compare.greaterOrEqualInt64(k, questions)
  if allQuestions startAnswers skipQuestion
:skipQuestion in=eachQuestion
  skipIt: afterName = skipName(reply, bytes, at)
  badCheck: bad = compare.lessThanInt64(afterName, zero)
  if bad giveAgain pastQuestion
:pastQuestion in=eachQuestion
  pastFixed: afterQuestion = math.addInt64(afterName, four)
  set at afterQuestion
  nextQuestion: afterK = math.addInt64(k, one=1)
  set k afterK
  goto eachQuestion
:startAnswers
  set k zero
  goto eachAnswer
:eachAnswer loop=while max=answers
  answersDone: allAnswers = compare.greaterOrEqualInt64(k, answers)
  if allAnswers giveNoData readRecord
:readRecord in=eachAnswer
  skipOwner: afterOwner = skipName(reply, bytes, at)
  badOwner: ownerBad = compare.lessThanInt64(afterOwner, zero)
  endOfFixed: fixedEnd = math.addInt64(afterOwner, ten=10)
  pastReply: beyond = compare.greaterThanInt64(fixedEnd, bytes)
  broken: brokenRecord = logic.or(ownerBad, beyond)
  if brokenRecord giveAgain fields
:fields in=eachAnswer
  readType: kind = word16(reply, afterOwner)
  classAt: classPlace = math.addInt64(afterOwner, two)
  readClass: klass = word16(reply, classPlace)
  lengthPlace: dataLengthAt = math.addInt64(afterOwner, eight=8)
  readDataLength: dataLength = word16(reply, dataLengthAt)
  dataEnd: recordEnd = math.addInt64(fixedEnd, dataLength)
  overCheck: over = compare.greaterThanInt64(recordEnd, bytes)
  if over giveAgain typeCheck
:typeCheck in=eachAnswer
  isA: aType = compare.equalInt64(kind, one)
  isIn: inClass = compare.equalInt64(klass, one)
  isFour: fourBytes = compare.equalInt64(dataLength, four)
  bothCheck: aIn = logic.and(aType, inClass)
  allCheck: isAddress = logic.and(aIn, fourBytes)
  if isAddress giveAddress nextRecord
:nextRecord in=eachAnswer
  set at recordEnd
  nextAnswer: afterAnswer = math.addInt64(k, one)
  set k afterAnswer
  goto eachAnswer
:giveAddress
  readA: a = byteOf(reply, fixedEnd)
  placeB: bAt = math.addInt64(fixedEnd, one)
  readB: b = byteOf(reply, bAt)
  placeC: cAt = math.addInt64(fixedEnd, two)
  readC: c = byteOf(reply, cAt)
  placeD: dAt = math.addInt64(fixedEnd, three)
  readD: d = byteOf(reply, dAt)
  shiftA: a24 = bits.shiftLeftInt64(a, twentyFour=24)
  shiftB: b16 = bits.shiftLeftInt64(b, sixteen=16)
  shiftC: c8 = bits.shiftLeftInt64(c, eight)
  joinAB: ab = bits.orInt64(a24, b16)
  joinCD: cd = bits.orInt64(c8, d)
  joinAll: address = bits.orInt64(ab, cd)
  findResolved: resolved = kernel.stateAt(resolvedAt)
  storeIt: machine.storeInt64(resolved, address)
  return found
:giveNoName
  return noName
:giveAgain
  return tryAgain
:giveNoData
  return noData

op queryServer "Ask a nameserver for a name's A record over UDP, five seconds a try and two tries; 0 with the address in resolvedAt, else the getaddrinfo error"
  input name machine.Address copied
  input nameBytes Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  output Int64
  let tries Int64 0 mut
  let outcome Int64 -3 mut
  let noName Int64 -2
  let tryAgain Int64 -3
  let datagram Int64 526338
:begin
  takeQuery: query = heap.take(n512=512)
  readNow: moment = tasks.now()
  idOf: id = bits.andInt64(moment, n65535=65535)
  idHigh: high = bits.shiftRightInt64(id, eight=8)
  storeIdHigh: storeByteValue(query, zero=0, high)
  storeIdLow: storeByteValue(query, one=1, id)
  storeRecursion: storeByteValue(query, two=2, recursionDesired=1)
  storeQuestions: storeByteValue(query, five=5, one)
  writeName: afterName = putName(query, twelve=12, name, nameBytes)
  badCheck: bad = compare.lessThanInt64(afterName, zero)
  if bad refuse finishQuery
:finishQuery
  storeTypeHigh: storeByteValue(query, afterName, zero)
  typeLowAt: typeLow = math.addInt64(afterName, one)
  storeTypeLow: storeByteValue(query, typeLow, one)
  classHighAt: classHigh = math.addInt64(afterName, two)
  storeClassHigh: storeByteValue(query, classHigh, zero)
  classLowAt: classLow = math.addInt64(afterName, three=3)
  storeClassLow: storeByteValue(query, classLow, one)
  lengthOf: queryBytes = math.addInt64(afterName, four=4)
  serverOf: server = nameserver()
  socketIt: fd = system.socket(two, datagram, zero)
  socketFailed: noSocket = kernel.failed(fd)
  if noSocket refuseAgain connect
:connect
  addressOf: sockaddr = putAddress(server, fiftyThree=53)
  connectIt: connected = system.connect(fd, sockaddr, sixteen=16)
  connectFailed: notConnected = kernel.failed(connected)
  if notConnected closeAgain makeObject2
:makeObject2
  nowhere: anywhere = machine.zero()
  objectIt: object = makeObject(fd, anywhere)
  takeReply: reply = heap.take(n4096=4096)
  goto eachTry
:eachTry loop=while max=2
  triesDone: allTries = compare.greaterOrEqualInt64(tries, two)
  if allTries closeAll send
:send in=eachTry
  moreTries: afterTries = math.addInt64(tries, one)
  set tries afterTries
  sendIt: sent = system.sendto(fd, query, queryBytes, zero, anywhere, zero)
  readStart: started = tasks.now()
  limitOf: limit = math.addInt64(started, fiveSeconds=5000)
  goto eachReply
:eachReply loop=while max=forever in=eachTry
  receiveIt: got = system.recvfrom(fd, reply, n4096, zero, anywhere, anywhere)
  receiveFailed: noReply = kernel.failed(got)
  if noReply waitReply checkReply
:waitReply in=eachReply
  waitIt: waited = waitFor(object, limit, zero, no=false)
  timedCheck: timed = compare.equalInt64(waited, one)
  if timed eachTry eachReply
:checkReply in=eachReply
  shortCheck: short = compare.lessThanInt64(got, twelve)
  if short eachReply idCheck
:idCheck in=eachReply
  readId: replyId = word16(reply, zero)
  sameId: same = compare.equalInt64(replyId, id)
  if same answer eachReply
:answer
  answerIt: answered = readAnswer(reply, got)
  set outcome answered
  goto closeAll
:closeAll
  giveReply: heap.give(reply)
  giveObject: heap.give(object)
  closeIt: closed = system.close(fd)
  goto give
:closeAgain
  closeFailed: closedAgain = system.close(fd)
  goto refuseAgain
:refuseAgain
  set outcome tryAgain
  goto give
:refuse
  set outcome noName
  goto give
:give
  giveQuery: heap.give(query)
  return outcome

op resolve "A host name's IPv4 address on Linux as getaddrinfo finds it there (D-149): numeric as inet_aton reads it, else /etc/hosts, else DNS; 0 with the address in resolvedAt, else the getaddrinfo error"
  input name machine.Address copied
  input nameBytes Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let found Int64 0
  let minusTwo Int64 -2
:begin
  atonIt: numeric = atonAddress(name, nameBytes)
  numericCheck: isNumeric = compare.equalInt64(numeric, one=1)
  if isNumeric give hosts
:hosts
  hostsIt: listed = hostsLookup(name, nameBytes)
  listedCheck: isListed = compare.equalInt64(listed, one)
  if isListed give dns
:dns
  emptyCheck: empty = compare.equalInt64(nameBytes, zero=0)
  if empty noName ask
:noName
  return minusTwo
:ask
  askIt: outcome = queryServer(name, nameBytes)
  return outcome
:give
  return found

op bindAddress "The address `net.listen` binds a host to, as Python's setipaddr reads it for AF_INET: `<broadcast>`, a numeric address as inet_pton reads it, else the name resolved; 0 with it in resolvedAt, else the error (a getaddrinfo error, or on Windows its code)"
  input host machine.Address copied
  input hostBytes Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let found Int64 0
  let broadcast String "<broadcast>"
:begin
  findBroadcast: broadcastAt = machine.addressOfString(broadcast)
  broadcastCheck: same = memory.bytesEqual(host, hostBytes, broadcastAt, eleven=11)
  isBroadcast: wantsBroadcast = compare.notEqualInt32(same, zero32=0)
  if wantsBroadcast giveBroadcast numeric
:giveBroadcast
  findResolved: resolved = kernel.stateAt(resolvedAt)
  storeAll: machine.storeInt64(resolved, allOnes=4294967295)
  return found
:numeric
  quadIt: quad = dottedQuad(host, hostBytes)
  quadCheck: isQuad = compare.equalInt64(quad, one=1)
  if isQuad give named
:named
  osCheck: onLinux = system.posix()
  if onLinux linuxName windowsName
:linuxName
  resolveIt: outcome = resolve(host, hostBytes)
  return outcome
:windowsName
  winIt: winOutcome = windowsLookup(host, hostBytes, anyService=0)
  return winOutcome
:give
  return found

op windowsLookup "A host name's first IPv4 address on Windows by getaddrinfo (AF_INET hints), into resolvedAt: 0, or getaddrinfo's error code"
  input host machine.Address copied
  input hostBytes Int64 copied
  input service Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let found Int64 0
:begin
  startIt: startWinsock()
  copySize: nameBytes = math.addInt64(hostBytes, one=1)
  takeName: name = heap.take(nameBytes)
  copyName: machine.copy(name, host, hostBytes)
  findHints: hints = kernel.stateAt(hintsAt)
  clearHints: machine.fill(hints, zeroByte=0, fortyEight=48)
  familyAt: familySlot = machine.offset(hints, four=4)
  storeFamily: machine.storeInt32(familySlot, inet=2)
  findResult: resultSlot = kernel.stateAt(infoAt)
  nowhere: anywhere = machine.zero()
  lookIt: status = system.getaddrinfo(name, anywhere, hints, resultSlot)
  giveName: heap.give(name)
  failedCheck: failed = compare.notEqualInt32(status, zero32=0)
  if failed giveError readFirst
:giveError
  widenStatus: code = convert.int32ToInt64(status)
  return code
:readFirst
  readInfo: info = machine.loadAddress(resultSlot)
  addrAt: addrSlot = machine.offset(info, thirtyTwo=32)
  readAddr: sockaddr = machine.loadAddress(addrSlot)
  readA: a = byteOf(sockaddr, four)
  readB: b = byteOf(sockaddr, five=5)
  readC: c = byteOf(sockaddr, six=6)
  readD: d = byteOf(sockaddr, seven=7)
  shiftA: a24 = bits.shiftLeftInt64(a, twentyFour=24)
  shiftB: b16 = bits.shiftLeftInt64(b, sixteen=16)
  shiftC: c8 = bits.shiftLeftInt64(c, eight=8)
  joinAB: ab = bits.orInt64(a24, b16)
  joinCD: cd = bits.orInt64(c8, d)
  joinAll: address = bits.orInt64(ab, cd)
  findResolved: resolved = kernel.stateAt(resolvedAt)
  storeIt: machine.storeInt64(resolved, address)
  freeIt: system.freeaddrinfo(info)
  return found

## ---------------------------------------------------------------- targets

op listenTarget "net.listen: a TCP listener on the scope's host (127.0.0.1 when it names none) and a port, as host.py's listen makes one; a port outside 0 to 65535 traps as Python's bind refuses it"
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
  let host machine.Address unset mut
  let hostBytes Int64 0 mut
  let stream Int64 526337
  let loopback String "127.0.0.1"
  let nine Int64 9
:begin
  readPort: port = slots.argOf(shape, args, zero=0)
  readHost: given = files.textAt(shape, args, one=1)
  readHostBytes: givenBytes = files.textBytes(shape, args, one)
  set host given
  set hostBytes givenBytes
  emptyCheck: empty = compare.equalInt64(givenBytes, zero)
  if empty useLoopback portCheck
:useLoopback
  findLoopback: loopbackAt = machine.addressOfString(loopback)
  set host loopbackAt
  set hostBytes nine
  goto portCheck
:portCheck
  lowCheck: negative = compare.lessThanInt64(port, zero)
  highCheck: tooHigh = compare.greaterThanInt64(port, n65535=65535)
  outsideCheck: outside = logic.or(negative, tooHigh)
  if outside badPort socket
:badPort
  failPort: failText(portText="`net.listen` failed inside the runtime: OverflowError('bind(): port must be 0-65535.')")
  return ok
:socket
  osCheck: onLinux = system.posix()
  if onLinux linuxSocket windowsSocket
:linuxSocket
  socketIt: fd = system.socket(two=2, stream, zero)
  socketFailed: noSocket = kernel.failed(fd)
  if noSocket linuxSocketError reuse
:linuxSocketError
  socketErrno: socketCode = kernel.errnoOf(fd)
  socketStatus: status1 = netError(payload, socketCode)
  return status1
:reuse
  findOption: option = kernel.stateAt(lengthAt)
  storeOne: machine.storeInt64(option, one)
  reuseIt: reused = system.setsockopt(fd, one, two, option, four=4)
  addressIt: lookup = bindAddress(host, hostBytes)
  lookupCheck: lookupFailed = compare.notEqualInt64(lookup, zero)
  if lookupFailed linuxLookupError linuxBind
:linuxLookupError
  closeLookup: closedLookup = system.close(fd)
  lookupStatus: status2 = netError(payload, lookup)
  return status2
:linuxBind
  findResolved: resolved = kernel.stateAt(resolvedAt)
  readAddress: address = machine.loadInt64(resolved)
  sockaddrOf: sockaddr = putAddress(address, port)
  bindIt: bound = system.bind(fd, sockaddr, sixteen=16)
  bindFailed: notBound = kernel.failed(bound)
  if notBound linuxError linuxListen
:linuxListen
  listenIt: listening = system.listen(fd, backlog=128)
  listenFailed: notListening = kernel.failed(listening)
  if notListening linuxListenError linuxDone
:linuxListenError
  listenErrno: listenCode = kernel.errnoOf(listening)
  closeListen: closedListen = system.close(fd)
  listenStatus: status3 = netError(payload, listenCode)
  return status3
:linuxError
  bindErrno: bindCode = kernel.errnoOf(bound)
  closeBind: closedBind = system.close(fd)
  bindStatus: status4 = netError(payload, bindCode)
  return status4
:linuxDone
  nowhere: anywhere = machine.zero()
  makeLinux: linuxObject = makeObject(fd, anywhere)
  linuxHandle: handle1 = handles.newHandle(kindListener, linuxObject, anywhere)
  storeLinux: machine.storeInt64(results, handle1)
  return ok
:windowsSocket
  startIt: startWinsock()
  winSocketIt: winSocket = system.winsockSocket(inet32=2, streamKind=1, protocol=0)
  winSocketValue: socketValue = machine.toInt64(winSocket)
  nowhereW: anywhereW = machine.zero()
  invalidCheck: invalid = compare.equalInt64(socketValue, minusOne=-1)
  if invalid windowsError windowsLookup2
:windowsLookup2
  winAddressIt: winLookup = bindAddress(host, hostBytes)
  winLookupCheck: winLookupFailed = compare.notEqualInt64(winLookup, zero)
  if winLookupFailed windowsLookupError windowsBind
:windowsLookupError
  closeWinLookup: closeSocket(socketValue, anywhereW)
  winLookupStatus: status5 = netError(payload, winLookup)
  return status5
:windowsBind
  findWinResolved: winResolved = kernel.stateAt(resolvedAt)
  readWinAddress: winAddress = machine.loadInt64(winResolved)
  winSockaddrOf: winSockaddr = putAddress(winAddress, port)
  winBindIt: winBound = system.winsockBind(winSocket, winSockaddr, sixteen32=16)
  winBindCheck: winNotBound = compare.notEqualInt32(winBound, protocol)
  if winNotBound windowsCloseError windowsListen
:windowsListen
  winListenIt: winListening = system.winsockListen(winSocket, backlog32=128)
  winListenCheck: winNotListening = compare.notEqualInt32(winListening, protocol)
  if winNotListening windowsCloseError windowsDone
:windowsCloseError
  winErrno: winCode = lastWinsock()
  nowhere2: anywhere2 = machine.zero()
  closeWin: closeSocket(socketValue, anywhere2)
  winStatus: status6 = netError(payload, winCode)
  return status6
:windowsError
  winSocketErrno: winSocketCode = lastWinsock()
  winSocketStatus: status7 = netError(payload, winSocketCode)
  return status7
:windowsDone
  selectIt: event = selectEvents(socketValue, acceptEvents=8)
  makeWindows: windowsObject = makeObject(socketValue, event)
  nowhere3: noRegion = machine.zero()
  windowsHandle: handle2 = handles.newHandle(kindListener, windowsObject, noRegion)
  storeWindows: machine.storeInt64(results, handle2)
  return ok

op closeListenerTarget "net.closeListener: close a listener's socket and its handle"
  input shape machine.Address copied
  input args machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findObject: object = handles.objectOf(handle, kindListener)
  readSocket: socket = socketOf(object)
  readEvent: event = eventOf(object)
  dropIt: handles.drop(handle)
  closeIt: closeSocket(socket, event)
  return

op acceptTarget "net.accept: the next connection to a listener, waiting through the scheduler; cancelled or timedOut first when the task is cancelled or the deadline has passed, as host.py's _until_ready checks"
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
  let acceptFlags Int64 526336
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findObject: object = handles.objectOf(handle, kindListener)
  readSocket: socket = socketOf(object)
  readDeadline: deadline = slots.argOf(shape, args, one=1)
  nowhere: anywhere = machine.zero()
  goto eachTry
:eachTry loop=while max=forever
  cancelCheck: isCancelled = tasks.cancelled()
  if isCancelled giveCancelled deadlineCheck
:deadlineCheck in=eachTry
  pastCheck: past = deadlinePassed(deadline)
  if past giveTimedOut attempt
:attempt in=eachTry
  prepareIt: prepare(object)
  osCheck: onLinux = system.posix()
  if onLinux linuxAccept windowsAccept
:linuxAccept in=eachTry
  acceptIt: fd = system.accept4(socket, anywhere, anywhere, acceptFlags)
  acceptFailed: refused = kernel.failed(fd)
  if refused linuxRefused linuxDone
:linuxRefused in=eachTry
  acceptErrno: code = kernel.errnoOf(fd)
  againCheck: isAgain = compare.equalInt64(code, again)
  interruptedCheck: isInterrupted = compare.equalInt64(code, four=4)
  retryCheck: retry = logic.or(isAgain, isInterrupted)
  if retry waitIt giveError
:windowsAccept in=eachTry
  asHandle: listening = machine.fromInt64(socket)
  winAcceptIt: winSocket = system.winsockAccept(listening, anywhere, anywhere)
  winValue: winFd = machine.toInt64(winSocket)
  invalidCheck: invalid = compare.equalInt64(winFd, minusOne=-1)
  if invalid windowsRefused windowsDone
:windowsRefused in=eachTry
  winErrno: winCode = lastWinsock()
  blockCheck: blocked = compare.equalInt64(winCode, wouldBlock)
  if blocked waitIt giveWinError
:waitIt in=eachTry
  waitOnce: outcome = waitFor(object, deadline, one=1, reading=false)
  waitCancelled: stopped = compare.equalInt64(outcome, two=2)
  if stopped giveCancelled waitTimed
:waitTimed in=eachTry
  waitTimedCheck: timed = compare.equalInt64(outcome, one)
  if timed giveTimedOut eachTry
:linuxDone
  makeLinux: linuxObject = makeObject(fd, anywhere)
  linuxHandle: handle1 = handles.newHandle(kindConnection, linuxObject, anywhere)
  storeLinux: machine.storeInt64(results, handle1)
  return ok
:windowsDone
  selectIt: event = selectEvents(winFd, connectionEvents=35)
  makeWindows: windowsObject = makeObject(winFd, event)
  windowsHandle: handle2 = handles.newHandle(kindConnection, windowsObject, anywhere)
  storeWindows: machine.storeInt64(results, handle2)
  return ok
:giveError
  errorStatus: status1 = netError(payload, code)
  return status1
:giveWinError
  winStatus: status2 = netError(payload, winCode)
  return status2
:giveCancelled
  cancelledIt: status3 = cancelledStatus(payload)
  return status3
:giveTimedOut
  timedIt: status4 = timedOutStatus(payload)
  return status4

op parsePort "Read the port of an address as Python's int() reads text (ASCII white space around it, a sign, digits with single underscores between them) into digitsAt+8: 1 when it is a whole number, else 0"
  input text machine.Address copied
  input from Int64 copied
  input to Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let end Int64 0 mut
  let value Int64 0 mut
  let digits Int64 0 mut
  let negative Bool false mut
  let underscore Bool false mut
  let yes Bool true
  let no Bool false
  let refusedValue Int64 0
  let accepted Int64 1
  let limit Int64 100000000000000000
:begin
  startOf: start = skipBlank(text, from, to)
  set at start
  endOf: last = trimBlank(text, start, to)
  set end last
  signCheck: hasSign = compare.lessThanInt64(start, last)
  if hasSign readSign eachDigit
:readSign
  readFirst: first = byteOf(text, start)
  minusCheck: isMinus = compare.equalInt64(first, minus=45)
  plusCheck: isPlus = compare.equalInt64(first, plus=43)
  eitherSign: isSign = logic.or(isMinus, isPlus)
  if isSign takeSign eachDigit
:takeSign
  set negative isMinus
  pastSign: afterSign = math.addInt64(start, one=1)
  set at afterSign
  goto eachDigit
:eachDigit loop=while max=to
  endCheck: atEnd = compare.greaterOrEqualInt64(at, end)
  if atEnd finish readOne
:readOne in=eachDigit
  readByte: byte = byteOf(text, at)
  underscoreCheck: isUnderscore = compare.equalInt64(byte, underscoreByte=95)
  if isUnderscore takeUnderscore digitCheck
:takeUnderscore in=eachDigit
  afterDigit: hadDigit = compare.greaterThanInt64(digits, zero=0)
  notTwice: single = logic.not(underscore)
  bothCheck: allowed = logic.and(hadDigit, single)
  if allowed markUnderscore refuse
:markUnderscore in=eachDigit
  set underscore yes
  goto advance
:digitCheck in=eachDigit
  lowDigit: aboveZero = compare.greaterOrEqualInt64(byte, digitZero=48)
  highDigit: belowNine = compare.lessOrEqualInt64(byte, digitNine=57)
  isDigitCheck: isDigit = logic.and(aboveZero, belowNine)
  if isDigit takeDigit refuse
:takeDigit in=eachDigit
  set underscore no
  bigCheck: big = compare.greaterThanInt64(value, limit)
  if big countDigit accumulate
:accumulate in=eachDigit
  tenTimes: shifted = math.multiplyInt64(value, ten=10)
  digitOf: digit = math.subtractInt64(byte, digitZero)
  addIt: grown = math.addInt64(shifted, digit)
  set value grown
  goto countDigit
:countDigit in=eachDigit
  moreDigits: afterDigits = math.addInt64(digits, one)
  set digits afterDigits
  goto advance
:advance in=eachDigit
  nextAt: after = math.addInt64(at, one)
  set at after
  goto eachDigit
:finish
  noneCheck: noDigits = compare.equalInt64(digits, zero)
  endUnderscore: trailing = logic.or(noDigits, underscore)
  if trailing refuse give
:give
  if negative flip store
:flip
  flipped: negated = math.subtractInt64(zero, value)
  set value negated
  goto store
:store
  findValue: valueSlot = kernel.stateAt(portAt=1416)
  storeIt: machine.storeInt64(valueSlot, value)
  return accepted
:refuse
  return refusedValue

op isBlank "Whether a byte is ASCII white space as int() strips it"
  input value Int64 copied
  output Bool
:begin
  spaceCheck: isSpace2 = compare.equalInt64(value, space=32)
  lowCheck: aboveTab = compare.greaterOrEqualInt64(value, tab=9)
  highCheck: belowReturn = compare.lessOrEqualInt64(value, carriageReturn=13)
  controlCheck: isControl = logic.and(aboveTab, belowReturn)
  eitherCheck: blank = logic.or(isSpace2, isControl)
  return blank

op skipBlank "The first position from one that is not white space"
  input text machine.Address copied
  input from Int64 copied
  input to Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  set at from
  goto eachByte
:eachByte loop=while max=to
  endCheck: atEnd = compare.greaterOrEqualInt64(at, to)
  if atEnd give readOne
:readOne in=eachByte
  readIt: byte = byteOf(text, at)
  blankCheck: blank = isBlank(byte)
  if blank advance give
:advance in=eachByte
  nextAt: after = math.addInt64(at, one=1)
  set at after
  goto eachByte
:give
  return at

op trimBlank "The end of a range less the white space it ends with"
  input text machine.Address copied
  input from Int64 copied
  input to Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  set at to
  goto eachByte
:eachByte loop=while max=to
  startCheck: atStart = compare.lessOrEqualInt64(at, from)
  if atStart give readOne
:readOne in=eachByte
  lastOf: last = math.subtractInt64(at, one=1)
  readIt: byte = byteOf(text, last)
  blankCheck: blank = isBlank(byte)
  if blank back give
:back in=eachByte
  set at last
  goto eachByte
:give
  return at

op connectSocket "Connect a new non-blocking socket to an address and port, waiting through the scheduler until the deadline (not cancelled, as host.py's create_connection is not); 0 and the socket in lengthAt, else an errno, or -1 for a timeout"
  input address machine.Address copied
  input addressBytes Int64 copied
  input family Int64 copied
  input deadline Int64 copied
  input immediate Bool copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let stream Int64 526337
  let timedOutCode Int64 -1
  let done Int64 0
:begin
  nowhere: anywhere = machine.zero()
  osCheck: onLinux = system.posix()
  if onLinux linuxSocket windowsSocket
:linuxSocket
  socketIt: fd = system.socket(family, stream, zero=0)
  socketFailed: noSocket = kernel.failed(fd)
  if noSocket linuxSocketError linuxConnect
:linuxSocketError
  socketErrno: socketCode = kernel.errnoOf(fd)
  return socketCode
:linuxConnect
  connectIt: connected = system.connect(fd, address, addressBytes)
  connectFailed: notConnected = kernel.failed(connected)
  if notConnected linuxPending linuxDone
:linuxPending
  pendingErrno: pendingCode = kernel.errnoOf(connected)
  progressCheck: inProgress2 = compare.equalInt64(pendingCode, inProgress)
  if inProgress2 linuxWaitCheck linuxClose
:linuxWaitCheck
  if immediate linuxClose linuxObject
:linuxObject
  objectIt: object = makeObject(fd, anywhere)
  goto linuxWait
:linuxWait
  waitIt: outcome = waitFor(object, deadline, zero, writing=true)
  timedCheck: timed = compare.equalInt64(outcome, one=1)
  if timed linuxTimedOut linuxReady
:linuxReady
  findOption: option = kernel.stateAt(lengthAt)
  storeZero: machine.storeInt64(option, zero)
  findLength: lengthSlot = machine.offset(option, eight=8)
  storeFour: machine.storeInt64(lengthSlot, four=4)
  readError: got = system.getsockopt(fd, one, soError=4, option, lengthSlot)
  readOption: optionValue = machine.loadInt32(option)
  widenOption: socketError = convert.int32ToInt64(optionValue)
  giveObjectReady: heap.give(object)
  readyCheck: fine = compare.equalInt64(socketError, zero)
  if fine linuxDone linuxReadyClose
:linuxReadyClose
  closeReady: closedReady = system.close(fd)
  return socketError
:linuxTimedOut
  giveObjectTimed: heap.give(object)
  closeTimed: closedTimed = system.close(fd)
  return timedOutCode
:linuxClose
  closeIt: closed = system.close(fd)
  return pendingCode
:linuxDone
  findSocket: socketSlot = kernel.stateAt(lengthAt)
  storeSocket: machine.storeInt64(socketSlot, fd)
  return done
:windowsSocket
  narrowFamily: family32 = convert.int64ToInt32(family)
  winSocketIt: winSocket = system.winsockSocket(family32, streamKind=1, protocol=0)
  winValue: winFd = machine.toInt64(winSocket)
  invalidCheck: invalid = compare.equalInt64(winFd, minusOne=-1)
  if invalid windowsSocketError windowsSelect
:windowsSocketError
  winSocketErrno: winSocketCode = lastWinsock()
  return winSocketCode
:windowsSelect
  selectIt: event = selectEvents(winFd, allEvents=51)
  winObject: object2 = makeObject(winFd, event)
  narrowBytes: addressBytes32 = convert.int64ToInt32(addressBytes)
  winConnectIt: winConnected = system.winsockConnect(winSocket, address, addressBytes32)
  winConnectCheck: winNotConnected = compare.notEqualInt32(winConnected, protocol)
  if winNotConnected windowsPending windowsDone
:windowsPending
  winErrno: winCode = lastWinsock()
  blockCheck: blocked = compare.equalInt64(winCode, wouldBlock)
  if blocked windowsWaitCheck windowsClose
:windowsWaitCheck
  if immediate windowsClose windowsWait
:windowsWait loop=while max=forever
  winWaitIt: winOutcome = waitFor(object2, deadline, zero, true2=true)
  winTimedCheck: winTimed = compare.equalInt64(winOutcome, one)
  if winTimed windowsTimedOut windowsEvents
:windowsEvents in=windowsWait
  findEvents: events = kernel.stateAt(eventsAt)
  enumIt: enumerated = system.wsaEnumNetworkEvents(winSocket, event, events)
  readEvents: happened = machine.loadInt32(events)
  connectBit: connectedBit = bits.andInt32(happened, connectEvent=16)
  connectCheck: hasConnect = compare.notEqualInt32(connectedBit, protocol)
  if hasConnect windowsResult windowsWait
:windowsResult
  findCode: codeSlot = machine.offset(events, twenty=20)
  readCode: code32 = machine.loadInt32(codeSlot)
  widenCode: rawCode = convert.int32ToInt64(code32)
  mapCode: mapped = winsockErrno(rawCode)
  winReadyCheck: winFine = compare.equalInt64(mapped, zero)
  if winFine windowsDone windowsFailed
:windowsFailed
  readFailedEvent: failedEvent = eventOf(object2)
  giveFailedObject: heap.give(object2)
  closeFailed: closeSocket(winFd, failedEvent)
  return mapped
:windowsTimedOut
  readTimedEvent: timedEvent = eventOf(object2)
  giveTimedObject: heap.give(object2)
  closeWinTimed: closeSocket(winFd, timedEvent)
  return timedOutCode
:windowsClose
  readCloseEvent: closeEvent = eventOf(object2)
  giveCloseObject: heap.give(object2)
  closeWin: closeSocket(winFd, closeEvent)
  return winCode
:windowsDone
  giveDoneObject: heap.give(object2)
  findWinSocket: winSocketSlot = kernel.stateAt(lengthAt)
  storeWinSocket: machine.storeInt64(winSocketSlot, winFd)
  findWinEvent: winEventSlot = machine.offset(winSocketSlot, eight=8)
  storeWinEvent: machine.storeAddress(winEventSlot, event)
  return done

op connectTarget "net.connect: a connection to `host:port` as host.py's create_connection makes one: the port read as int() reads it (else failed 22), the host resolved (IPv4), each address tried in turn until the deadline; a deadline already passed tries once without waiting, as a timeout of 0 does"
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
  let colon Int64 58
  let at Int64 0 mut
  let split Int64 -1 mut
  let last Int64 0 mut
  let immediate Bool false mut
  let yes Bool true
:begin
  readAddress: text = files.textAt(shape, args, zero=0)
  readBytes: bytes = files.textBytes(shape, args, zero)
  readDeadline: deadline = slots.argOf(shape, args, one=1)
  neverCheck: isNever = compare.equalInt64(deadline, never)
  if isNever findColon pastCheck
:pastCheck
  pastIt: past = deadlinePassed(deadline)
  if past markImmediate findColon
:markImmediate
  set immediate yes
  goto findColon
:findColon
  set at bytes
  goto eachByte
:eachByte loop=while max=bytes
  startCheck: atStart = compare.lessOrEqualInt64(at, zero)
  if atStart splitDone readOne
:readOne in=eachByte
  backOne: previous = math.subtractInt64(at, one=1)
  readIt: byte = byteOf(text, previous)
  colonCheck: isColon = compare.equalInt64(byte, colon)
  if isColon found back
:back in=eachByte
  set at previous
  goto eachByte
:found
  set split previous
  goto splitDone
:splitDone
  hostEnd: hostBytes = splitHost(split)
  portStart: portFrom = math.addInt64(split, one)
  portIt: isPort = parsePort(text, portFrom, bytes)
  portCheck: hasPort = compare.equalInt64(isPort, one)
  if hasPort resolveHost badPort
:badPort
  badPortStatus: status1 = netError(payload, n22=22)
  return status1
:resolveHost
  findPort: portSlot = kernel.stateAt(portAt=1416)
  readPort: port = machine.loadInt64(portSlot)
  osCheck: onLinux = system.posix()
  if onLinux linuxResolve windowsResolve
:linuxResolve
  resolveIt: outcome = resolve(text, hostBytes)
  resolvedCheck: unresolved = compare.notEqualInt64(outcome, zero)
  if unresolved giveResolveError linuxConnect
:giveResolveError
  resolveStatus: status2 = netError(payload, outcome)
  return status2
:linuxConnect
  findResolved: resolved = kernel.stateAt(resolvedAt)
  readResolved: address = machine.loadInt64(resolved)
  portBits: port16 = bits.andInt64(port, n65535=65535)
  sockaddrOf: sockaddr = putAddress(address, port16)
  connectIt: result = connectSocket(sockaddr, sixteen=16, two=2, deadline, immediate)
  doneCheck: connected = compare.equalInt64(result, zero)
  if connected linuxDone giveConnectError
:linuxDone
  findSocket: socketSlot = kernel.stateAt(lengthAt)
  readSocket: fd = machine.loadInt64(socketSlot)
  nowhere: anywhere = machine.zero()
  makeLinux: linuxObject = makeObject(fd, anywhere)
  linuxHandle: handle1 = handles.newHandle(kindConnection, linuxObject, anywhere)
  storeLinux: machine.storeInt64(results, handle1)
  return ok
:giveConnectError
  timedCheck: timed = compare.equalInt64(result, minusOne=-1)
  if timed giveTimedOut giveErrno
:giveTimedOut
  timedIt: status3 = timedOutStatus(payload)
  return status3
:giveErrno
  errnoIt: status4 = netError(payload, result)
  return status4
:windowsResolve
  startIt: startWinsock()
  findDigits: digits = kernel.stateAt(digitsAt)
  formatIt: digitCount = numbers.formatDecimal(port, digits)
  findEnd: digitsEnd = machine.offset(digits, digitCount)
  endDigits: machine.storeByte(digitsEnd, zeroByte=0)
  nameSize: nameBytes = math.addInt64(hostBytes, one)
  takeName: name = heap.take(nameBytes)
  copyName: machine.copy(name, text, hostBytes)
  findHints: hints = kernel.stateAt(hintsAt)
  clearHints: machine.fill(hints, zeroByte, fortyEight=48)
  familyAt: familySlot = machine.offset(hints, four=4)
  storeFamily: machine.storeInt32(familySlot, inet=2)
  kindAt: kindSlot = machine.offset(hints, eight=8)
  storeKind: machine.storeInt32(kindSlot, streamKind=1)
  findInfo: infoSlot = kernel.stateAt(infoAt)
  lookIt: lookStatus = system.getaddrinfo(name, digits, hints, infoSlot)
  giveName: heap.give(name)
  lookFailed: notFound = compare.notEqualInt32(lookStatus, zero32=0)
  if notFound giveLookError tryAll
:giveLookError
  widenLook: lookCode = convert.int32ToInt64(lookStatus)
  lookErrorStatus: status5 = netError(payload, lookCode)
  return status5
:tryAll
  readFirst: first = machine.loadAddress(infoSlot)
  set last one
  set at zero
  goto eachAddress
:eachAddress loop=while max=forever
  readInfo: info = loadInfo(first, at)
  nowhereInfo: noInfo = machine.zero()
  endCheck: atEnd = machine.equal(info, noInfo)
  if atEnd tried attempt
:attempt in=eachAddress
  familyOf: familySlot2 = machine.offset(info, four)
  readFamily: family32 = machine.loadInt32(familySlot2)
  widenFamily: family = convert.int32ToInt64(family32)
  lengthOf: lengthSlot2 = machine.offset(info, sixteen)
  readLength: addressBytes = machine.loadInt64(lengthSlot2)
  addrOf: addrSlot = machine.offset(info, thirtyTwo=32)
  readAddr: winAddress = machine.loadAddress(addrSlot)
  tryIt: winResult = connectSocket(winAddress, addressBytes, family, deadline, immediate)
  winConnectedCheck: winConnected = compare.equalInt64(winResult, zero)
  if winConnected windowsDone nextAddress
:nextAddress in=eachAddress
  set last winResult
  moreAt: afterAt = math.addInt64(at, one)
  set at afterAt
  goto eachAddress
:tried
  freeTried: system.freeaddrinfo(first)
  timedWinCheck: winTimed = compare.equalInt64(last, minusOne)
  if winTimed giveTimedOut giveLast
:giveLast
  lastStatus: status6 = netError(payload, last)
  return status6
:windowsDone
  freeDone: system.freeaddrinfo(first)
  findWinSocket: winSocketSlot = kernel.stateAt(lengthAt)
  readWinSocket: winFd = machine.loadInt64(winSocketSlot)
  findWinEvent: winEventSlot = machine.offset(winSocketSlot, eight)
  readWinEvent: winEvent = machine.loadAddress(winEventSlot)
  makeWindows: windowsObject = makeObject(winFd, winEvent)
  nowhereWin: noRegion = machine.zero()
  windowsHandle: handle2 = handles.newHandle(kindConnection, windowsObject, noRegion)
  storeWindows: machine.storeInt64(results, handle2)
  return ok

op splitHost "How many bytes of an address are its host: those before its last colon, or none when it has no colon"
  input split Int64 copied
  output Int64
:begin
  noneCheck: noColon = compare.lessThanInt64(split, zero=0)
  if noColon giveNone giveSplit
:giveNone
  return zero
:giveSplit
  return split

op loadInfo "The n-th result of a getaddrinfo list, or the address 0 past its end"
  input first machine.Address copied
  input index Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  let k Int64 0 mut
  let info machine.Address unset mut
:begin
  set info first
  goto eachInfo
:eachInfo loop=while max=index
  doneCheck: done = compare.greaterOrEqualInt64(k, index)
  if done give advance
:advance in=eachInfo
  nowhere: anywhere = machine.zero()
  endCheck: atEnd = machine.equal(info, anywhere)
  if atEnd give follow
:follow in=eachInfo
  findNext: nextSlot = machine.offset(info, forty=40)
  readNext: next = machine.loadAddress(nextSlot)
  set info next
  moreK: afterK = math.addInt64(k, one=1)
  set k afterK
  goto eachInfo
:give
  return info

op readTarget "net.read: up to a number of bytes a connection has (at least one), into a region; closed at the end of its stream; cancelled or timedOut first, as host.py's _until_ready checks"
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
  let size Int64 1 mut
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findObject: object = handles.objectOf(handle, kindConnection)
  readSocket: socket = socketOf(object)
  readRegion: region = slots.addressArg(shape, args, one=1)
  readLimit: limit = slots.argOf(shape, args, two=2)
  readDeadline: deadline = slots.argOf(shape, args, three=3)
  positiveCheck: positive = compare.greaterThanInt64(limit, one=1)
  if positive capCheck sized
:capCheck
  set size limit
  bigCheck: big = compare.greaterThanInt64(limit, mostRead)
  if big capIt sized
:capIt
  set size mostRead
  goto sized
:sized
  takeBuffer: buffer = heap.take(size)
  nowhere: anywhere = machine.zero()
  goto eachTry
:eachTry loop=while max=forever
  cancelCheck: isCancelled = tasks.cancelled()
  if isCancelled giveCancelled deadlineCheck
:deadlineCheck in=eachTry
  pastCheck: past = deadlinePassed(deadline)
  if past giveTimedOut attempt
:attempt in=eachTry
  prepareIt: prepare(object)
  osCheck: onLinux = system.posix()
  if onLinux linuxRead windowsRead
:linuxRead in=eachTry
  receiveIt: got = system.recvfrom(socket, buffer, size, zero, anywhere, anywhere)
  receiveFailed: refused = kernel.failed(got)
  if refused linuxRefused received
:linuxRefused in=eachTry
  receiveErrno: code = kernel.errnoOf(got)
  againCheck: isAgain = compare.equalInt64(code, again)
  interruptedCheck: isInterrupted = compare.equalInt64(code, four=4)
  retryCheck: retry = logic.or(isAgain, isInterrupted)
  if retry waitIt giveError
:windowsRead in=eachTry
  asHandle: winSocket = machine.fromInt64(socket)
  narrowSize: size32 = convert.int64ToInt32(size)
  winReceiveIt: winGot = system.winsockRecv(winSocket, buffer, size32, flags=0)
  failedCheck: winFailed = compare.lessThanInt32(winGot, flags)
  if winFailed windowsRefused windowsReceived
:windowsReceived in=eachTry
  widenGot: winBytes = convert.int32ToInt64(winGot)
  set size winBytes
  goto put
:windowsRefused in=eachTry
  winErrno: winCode = lastWinsock()
  blockCheck: blocked = compare.equalInt64(winCode, wouldBlock)
  if blocked waitIt giveWinError
:received in=eachTry
  set size got
  goto put
:waitIt in=eachTry
  waitOnce: outcome = waitFor(object, deadline, one, reading=false)
  waitCancelled: stopped = compare.equalInt64(outcome, two)
  if stopped giveCancelled waitTimed
:waitTimed in=eachTry
  waitTimedCheck: timed = compare.equalInt64(outcome, one)
  if timed giveTimedOut eachTry
:put
  endCheck: atEnd = compare.equalInt64(size, zero)
  if atEnd giveClosed copyOut
:copyOut
  putIt: slots.putText(region, buffer, size, results)
  giveBuffer: heap.give(buffer)
  return ok
:giveClosed
  giveClosedBuffer: heap.give(buffer)
  closedStatus: status1 = slots.failWith(payload, closedError, zero)
  return status1
:giveError
  giveErrorBuffer: heap.give(buffer)
  errorStatus: status2 = netError(payload, code)
  return status2
:giveWinError
  giveWinBuffer: heap.give(buffer)
  winStatus: status3 = netError(payload, winCode)
  return status3
:giveCancelled
  giveCancelledBuffer: heap.give(buffer)
  cancelledIt: status4 = cancelledStatus(payload)
  return status4
:giveTimedOut
  giveTimedBuffer: heap.give(buffer)
  timedIt: status5 = timedOutStatus(payload)
  return status5

op writeTarget "net.write: every byte to a connection, as sendall sends them with the deadline's time left (a deadline already passed sends once without waiting); not cancelled, as host.py's write is not"
  input shape machine.Address copied
  input args machine.Address copied
  input payload machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let ok Int32 0
  let sent Int64 0 mut
  let noSignal Int64 16384
  let immediate Bool false mut
  let yes Bool true
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findObject: object = handles.objectOf(handle, kindConnection)
  readSocket: socket = socketOf(object)
  readData: data = files.textAt(shape, args, one=1)
  readBytes: bytes = files.textBytes(shape, args, one)
  readDeadline: deadline = slots.argOf(shape, args, two=2)
  pastNow: pastAtStart = deadlinePassed(deadline)
  if pastAtStart markImmediate start
:markImmediate
  set immediate yes
  goto start
:start
  nowhere: anywhere = machine.zero()
  goto eachSend
:eachSend loop=while max=forever
  allCheck: all = compare.greaterOrEqualInt64(sent, bytes)
  if all done attempt
:attempt in=eachSend
  prepareIt: prepare(object)
  findPlace: place = machine.offset(data, sent)
  leftOf: left = math.subtractInt64(bytes, sent)
  osCheck: onLinux = system.posix()
  if onLinux linuxSend windowsSend
:linuxSend in=eachSend
  sendIt: got = system.sendto(socket, place, left, noSignal, anywhere, zero)
  sendFailed: refused = kernel.failed(got)
  if refused linuxRefused counted
:counted in=eachSend
  moreSent: afterSent = math.addInt64(sent, got)
  set sent afterSent
  goto eachSend
:linuxRefused in=eachSend
  sendErrno: code = kernel.errnoOf(got)
  againCheck: isAgain = compare.equalInt64(code, again)
  interruptedCheck: isInterrupted = compare.equalInt64(code, four=4)
  if isInterrupted eachSend againOrError
:againOrError in=eachSend
  if isAgain blockedLinux giveError
:blockedLinux in=eachSend
  if immediate giveError waitIt
:windowsSend in=eachSend
  asHandle: winSocket = machine.fromInt64(socket)
  chunkCheck: chunk = smaller(left, n1073741824=1073741824)
  narrowLeft: left32 = convert.int64ToInt32(chunk)
  winSendIt: winGot = system.winsockSend(winSocket, place, left32, flags=0)
  failedCheck: winFailed = compare.lessThanInt32(winGot, flags)
  if winFailed windowsRefused windowsCounted
:windowsCounted in=eachSend
  widenGot: winBytes = convert.int32ToInt64(winGot)
  moreWinSent: afterWinSent = math.addInt64(sent, winBytes)
  set sent afterWinSent
  goto eachSend
:windowsRefused in=eachSend
  winErrno: winCode = lastWinsock()
  blockCheck: blocked = compare.equalInt64(winCode, wouldBlock)
  if blocked blockedWindows giveWinError
:blockedWindows in=eachSend
  if immediate giveWinError waitIt
:waitIt in=eachSend
  waitOnce: outcome = waitFor(object, deadline, zero, writing=true)
  waitTimed: timed = compare.equalInt64(outcome, one)
  if timed giveTimedOut eachSend
:done
  return ok
:giveError
  errorStatus: status1 = netError(payload, code)
  return status1
:giveWinError
  winStatus: status2 = netError(payload, winCode)
  return status2
:giveTimedOut
  timedIt: status3 = timedOutStatus(payload)
  return status3

op smaller "The smaller of two whole numbers"
  input left Int64 copied
  input right Int64 copied
  output Int64
:begin
  lessCheck: less = compare.lessThanInt64(left, right)
  if less giveLeft giveRight
:giveLeft
  return left
:giveRight
  return right

op closeTarget "net.close: shut a connection down both ways (its failure ignored) and close its socket and handle"
  input shape machine.Address copied
  input args machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  readHandle: handle = slots.argOf(shape, args, zero=0)
  findObject: object = handles.objectOf(handle, kindConnection)
  readSocket: socket = socketOf(object)
  readEvent: event = eventOf(object)
  dropIt: handles.drop(handle)
  osCheck: onLinux = system.posix()
  if onLinux linuxShutdown windowsShutdown
:linuxShutdown
  shutdownIt: shut = system.shutdown(socket, both=2)
  goto close
:windowsShutdown
  asHandle: winSocket = machine.fromInt64(socket)
  winShutdownIt: winShut = system.winsockShutdown(winSocket, both32=2)
  goto close
:close
  closeIt: closeSocket(socket, event)
  return

op netCall "Run a net target by its place among them (1 listen, 2 closeListener, 3 accept, 4 connect, 5 read, 6 write, 7 close): 0, or an error's variant number with its payload stored"
  invariant runsNet "Each target does what host.py's net handler does: listening, accepting, connecting, reading, and writing IPv4 TCP with its deadlines, cancellation, and errors"
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
  listenCheck: isListen = compare.equalInt64(which, one=1)
  if isListen runListen closeListenerCheck
:runListen
  listenIt: listenStatus = listenTarget(shape, args, results, payload)
  return listenStatus
:closeListenerCheck
  checkCloseListener: isCloseListener = compare.equalInt64(which, two=2)
  if isCloseListener runCloseListener acceptCheck
:runCloseListener
  closeListenerIt: closeListenerTarget(shape, args)
  return ok
:acceptCheck
  checkAccept: isAccept = compare.equalInt64(which, three=3)
  if isAccept runAccept connectCheck
:runAccept
  acceptIt: acceptStatus = acceptTarget(shape, args, results, payload)
  return acceptStatus
:connectCheck
  checkConnect: isConnect = compare.equalInt64(which, four=4)
  if isConnect runConnect readCheck
:runConnect
  connectIt: connectStatus = connectTarget(shape, args, results, payload)
  return connectStatus
:readCheck
  checkRead: isRead = compare.equalInt64(which, five=5)
  if isRead runRead writeCheck
:runRead
  readIt: readStatus = readTarget(shape, args, results, payload)
  return readStatus
:writeCheck
  checkWrite: isWrite = compare.equalInt64(which, six=6)
  if isWrite runWrite runClose
:runWrite
  writeIt: writeStatus = writeTarget(shape, args, payload)
  return writeStatus
:runClose
  closeIt: closeTarget(shape, args)
  return ok

@tests

## Tests build a shape and a call's slots in the last 4 KiB of machine.state: the shape from byte 61440, the
## arguments from 61952, the results from 62016, the payload at 62080.

op setShape "Make the tests' shape from the slot counts of up to four parameters (0 for none)"
  input first Int64 copied
  input second Int64 copied
  input third Int64 copied
  input fourth Int64 copied
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
  findFourth: fourthCount = machine.offset(counts, twentyFour=24)
  storeFourth: machine.storeInt64(fourthCount, fourth)
  findFourthStart: fourthStart = machine.offset(starts, twentyFour)
  fourthAt: fourth0 = math.addInt64(third0, third)
  storeFourthStart: machine.storeInt64(fourthStart, fourth0)
  findParams: paramsAt = machine.offset(shape, twentyFour)
  storeParams: machine.storeInt64(paramsAt, four=4)
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

op setNumber "Set an argument slot of the tests' call to a number"
  input slot Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  findSlot: address = argAt(slot)
  storeIt: machine.storeInt64(address, value)
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

op callNet "Call a net target with the tests' slots and give its status"
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
  callIt: status = netCall(which, shape, args, results, payload)
  widen: wide1 = convert.int32ToInt64(status)
  return wide1

op firstResult "The first result slot of the tests' call"
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findResults: results = kernel.stateAt(resultsOffset=62016)
  readIt: value = machine.loadInt64(results)
  return value

op expectText "Compare the text in the first two result slots with what is expected"
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

test netTest "A listener on a loopback port takes a connection, which carries bytes both ways and sees the other end close; a port with nothing listening is refused, a port that is not a number failed 22; inet_aton reads every form of an IPv4 address"
  verifies netCall runsNet
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let label String "net test"
  let never2 Int64 -1
:begin
  findLabel: labelAt = machine.addressOfString(label)
  labelLength: labelBytes = string.byteLength(label)
  make: region = regions.newRegion(capacity=65536, labelAt, labelBytes)
  shapeListen: setShape(one=1, two=2, zero=0, zero)
  setPort: setNumber(zero, port=47853)
  setHost: setTextArg(one, host="127.0.0.1")
  listenIt: listened = callNet(one)
  test.assertEqualInt64(zero, listened)
  readListener: listener = firstResult()
  shapeConnect: setShape(two, one, zero, zero)
  setAddress: setTextArg(zero, address="127.0.0.1:47853")
  setDeadline: setNumber(two, never2)
  connectIt: connected = callNet(four=4)
  test.assertEqualInt64(zero, connected)
  readClient: client = firstResult()
  shapeAccept: setShape(one, one, zero, zero)
  setListener: setNumber(zero, listener)
  setAcceptDeadline: setNumber(one, never2)
  acceptIt: accepted = callNet(three=3)
  test.assertEqualInt64(zero, accepted)
  readServer: server = firstResult()
  shapeWrite: setShape(one, two, one, zero)
  setWriter: setNumber(zero, client)
  setData: setTextArg(one, ping="ping")
  setWriteDeadline: setNumber(three, never2)
  writeIt: written = callNet(six=6)
  test.assertEqualInt64(zero, written)
  shapeRead: setShape(one, one, one, one)
  setReader: setNumber(zero, server)
  findRegionSlot: regionSlot = argAt(one)
  setRegion: machine.storeAddress(regionSlot, region)
  setLimit: setNumber(two, sixtyFour=64)
  setReadDeadline: setNumber(three, never2)
  readIt: readStatus = callNet(five=5)
  test.assertEqualInt64(zero, readStatus)
  expectPing: expectText(ping)
  shapeClose: setShape(one, zero, zero, zero)
  setClosed: setNumber(zero, client)
  closeIt: closedStatus = callNet(seven=7)
  test.assertEqualInt64(zero, closedStatus)
  shapeReadAgain: setShape(one, one, one, one)
  setReaderAgain: setNumber(zero, server)
  setRegionAgain: machine.storeAddress(regionSlot, region)
  setLimitAgain: setNumber(two, sixtyFour)
  setReadDeadlineAgain: setNumber(three, never2)
  readEndIt: endStatus = callNet(five)
  test.assertEqualInt64(one, endStatus)
  shapeCloseServer: setShape(one, zero, zero, zero)
  setServer: setNumber(zero, server)
  closeServerIt: serverClosed = callNet(seven)
  test.assertEqualInt64(zero, serverClosed)
  setListenerClose: setNumber(zero, listener)
  closeListenerIt: listenerClosed = callNet(two)
  test.assertEqualInt64(zero, listenerClosed)
  shapeRefused: setShape(two, one, zero, zero)
  setRefused: setTextArg(zero, refusedAddress="127.0.0.1:47854")
  setRefusedDeadline: setNumber(two, never2)
  findShape: shape = kernel.stateAt(shapeAt=61440)
  findArgs: args = kernel.stateAt(argsOffset=61952)
  findResults: results = kernel.stateAt(resultsOffset=62016)
  findPayload: payload = kernel.stateAt(payloadOffset=62080)
  refusedIt: refused = netCall(four, shape, args, results, payload)
  widenRefused: refusedValue = convert.int32ToInt64(refused)
  test.assertEqualInt64(three, refusedValue)
  setBadPort: setTextArg(zero, badAddress="127.0.0.1:http")
  badIt: badPort = callNet(four)
  test.assertEqualInt64(five, badPort)
  readPayload: payloadValue = machine.loadInt64(payload)
  test.assertEqualInt64(n22=22, payloadValue)
  findShort: shortAt = machine.addressOfString(short="127.1")
  atonShort: shortOk = atonAddress(shortAt, five)
  test.assertEqualInt64(one, shortOk)
  findResolved: resolved = kernel.stateAt(resolvedAt)
  readShort: shortAddress = machine.loadInt64(resolved)
  test.assertEqualInt64(loopback=2130706433, shortAddress)
  findHex: hexAt = machine.addressOfString(hex="0x7f.0.0.01")
  atonHex: hexOk = atonAddress(hexAt, eleven=11)
  test.assertEqualInt64(one, hexOk)
  readHex: hexAddress = machine.loadInt64(resolved)
  test.assertEqualInt64(loopbackOne=2130706433, hexAddress)
  findBad: badAt = machine.addressOfString(badQuad="1.2.3.4.5")
  atonBad: badOk = atonAddress(badAt, nine=9)
  test.assertEqualInt64(zero, badOk)
  quadLeading: leadingAt = machine.addressOfString(leading="01.2.3.4")
  quadIt: leadingOk = dottedQuad(leadingAt, eight=8)
  test.assertEqualInt64(zero, leadingOk)
  free: regions.release(region)
  return
