module cwide "The C wide-character and multibyte functions in SemanticScript: wctype.h's classes and cases, wchar.h's text without formatted I/O, stdlib.h's multibyte functions, and uchar.h's, as glibc behaves in the C locale (wchar_t is 32 bits)"
  path cwide
  imports standard.machine standard.string standard.math standard.compare standard.convert standard.bits standard.logic standard.test kernel memory heap bignum clibrary
  exports none

capability memoryAccess "Authority to read and write the memory C callers hand the library" use machine.memory none

capability systemCalls "Authority to take memory from the heap and to read the text wcstod reads" use system.calls none

## Every function here is an `abi library "<name>"` operation (D-153, D-155): the C calling convention under its C name.
## In the C locale glibc classifies and changes case for ASCII only, so codes outside 0 to 127 are in no class and
## keep their case. A wide character is 32 bits (wchar_t is int on Linux; on Windows it is kept 32 bits too). The
## C locale's multibyte encoding is ASCII, as glibc's is (D-177): the bytes 0 to 127 are the wide characters 0 to
## 127, a byte from 128 to 255 is an invalid sequence and a wide character past 127 has no byte (EILSEQ either way;
## btowc and wctob give WEOF and EOF). MB_CUR_MAX is 1.
## machine.state bytes 26624 to 26879 belong to this module: the tests' scratch text (which the library never reads).

constant wideSize "sizeof(wchar_t): 4 bytes" Int64 4

constant forever "The bound of a loop that ends by its own test" Int64 9223372036854775807

constant eilseqError "EILSEQ: a wide character with no byte in the C locale" Int32 84

constant scratchAt "Where the tests write their text, in machine.state" Int64 26624

constant singleInexactAt "Where nearestSingle says whether the float differs from the double, in machine.state" Int64 26864

constant rangeErrorNumber "ERANGE: a result past what its type holds" Int32 34

constant alnumBit "isalnum's class bit" Int64 8

constant alphaBit "isalpha's class bit" Int64 1024

constant blankBit "isblank's class bit" Int64 1

constant cntrlBit "iscntrl's class bit" Int64 2

constant digitBit "isdigit's class bit" Int64 2048

constant graphBit "isgraph's class bit" Int64 32768

constant lowerBit "islower's class bit" Int64 512

constant printBit "isprint's class bit" Int64 16384

constant punctBit "ispunct's class bit" Int64 4

constant spaceBit "isspace's class bit" Int64 8192

constant upperBit "isupper's class bit" Int64 256

constant xdigitBit "isxdigit's class bit" Int64 4096

## ---------------------------------------------------------------- pieces

op unitAt "The wchar_t at an index of an array of them"
  input base machine.Address copied
  input index Int64 copied
  output Int32
  effect use machine.memory
  uses memoryAccess
:begin
  scaleIt: offset = math.multiplyInt64(index, wideSize)
  findPlace: place = machine.offset(base, offset)
  readIt: value = machine.loadInt32(place)
  return value

op putUnit "Store a wchar_t at an index of an array of them"
  input base machine.Address copied
  input index Int64 copied
  input value Int32 copied
  effect use machine.memory
  uses memoryAccess
:begin
  scaleIt: offset = math.multiplyInt64(index, wideSize)
  findPlace: place = machine.offset(base, offset)
  storeIt: machine.storeInt32(place, value)
  return

op byteValueAt "The unsigned char at an offset of an address, as an Int64"
  input base machine.Address copied
  input index Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  findPlace: place = machine.offset(base, index)
  readIt: value = machine.loadByte(place)
  widen: wide = convert.byteToInt64(value)
  return wide

op putByteAt "Store a byte at an offset of an address from an Int64 that is 0 to 255"
  input base machine.Address copied
  input index Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  findPlace: place = machine.offset(base, index)
  narrowIt: byteValue = convert.int64ToByte(value)
  storeIt: machine.storeByte(place, byteValue)
  return

op putUnitIf "Store a wchar_t at an index of an array, unless the array is the address 0 (nothing is written then)"
  input base machine.Address copied
  input index Int64 copied
  input value Int32 copied
  effect use machine.memory
  uses memoryAccess
:begin
  nowhere: anywhere = machine.zero()
  nullCheck: absent = machine.equal(base, anywhere)
  if absent done store
:store
  storeIt: putUnit(base, index, value)
  goto done
:done
  return

op putByteIf "Store a byte at an index of an array, unless the array is the address 0 (nothing is written then)"
  input base machine.Address copied
  input index Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  nowhere: anywhere = machine.zero()
  nullCheck: absent = machine.equal(base, anywhere)
  if absent done store
:store
  storeIt: putByteAt(base, index, value)
  goto done
:done
  return

op betweenCodes "Whether a code is from low to high, both included"
  input code Int32 copied
  input low Int32 copied
  input high Int32 copied
  output Bool
:begin
  aboveCheck: above = compare.greaterOrEqualInt32(code, low)
  belowCheck: below = compare.lessOrEqualInt32(code, high)
  bothCheck: inside = logic.and(above, below)
  return inside

op letterCode "Whether a code is an ASCII letter"
  input code Int32 copied
  output Bool
:begin
  upperCheck: upper = betweenCodes(code, lit1=65, lit2=90)
  lowerCheck: lower = betweenCodes(code, lit3=97, lit4=122)
  eitherCheck: letter = logic.or(upper, lower)
  return letter

op alnumCode "Whether a code is an ASCII letter or decimal digit"
  input code Int32 copied
  output Bool
:begin
  letterCheck: letter = letterCode(code)
  digitCheck: digit = betweenCodes(code, lit5=48, lit6=57)
  eitherCheck: alnum = logic.or(letter, digit)
  return alnum

op nameIs "Whether a C string is exactly a text: its bytes, then a 0 byte"
  input name machine.Address copied
  input text String borrowed
  output Bool
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let yes Bool true
  let no Bool false
:begin
  textLength: length = string.byteLength(text)
  findText: textAt = machine.addressOfString(text)
  goto eachByte
:eachByte loop=while max=forever
  atEndCheck: atEnd = compare.greaterOrEqualInt64(at, length)
  if atEnd endCheck readByte
:readByte in=eachByte
  nameByte: nameValue = byteValueAt(name, at)
  textByte: textValue = byteValueAt(textAt, at)
  sameCheck: same = compare.equalInt64(nameValue, textValue)
  if same advance missed
:advance in=eachByte
  stepIt: next = math.addInt64(at, lit7=1)
  set at next
  goto eachByte
:endCheck
  nameEnd: endValue = byteValueAt(name, length)
  zeroCheck: ended = compare.equalInt64(endValue, lit8=0)
  if ended matched missed
:matched
  return yes
:missed
  return no

## ---------------------------------------------------------------- wctype.h: classes

op iswalnum "iswalnum: glibc's class bit for a letter or decimal digit in the C locale (8), or 0"
  input code Int32 copied
  output Int32
  abi library "iswalnum"
  let found Int32 8
  let nothing Int32 0
:begin
  alnumCheck: alnum = alnumCode(code)
  if alnum matched missed
:matched
  return found
:missed
  return nothing

op iswalpha "iswalpha: glibc's class bit for a letter in the C locale (1024), or 0"
  invariant alphaIsAscii "Is nonzero for an ASCII letter and 0 for every other code, negative or above 255 included"
  input code Int32 copied
  output Int32
  abi library "iswalpha"
  let found Int32 1024
  let nothing Int32 0
:begin
  letterCheck: letter = letterCode(code)
  if letter matched missed
:matched
  return found
:missed
  return nothing

op iswblank "iswblank: glibc's class bit for a space or a tab in the C locale (1), or 0"
  input code Int32 copied
  output Int32
  abi library "iswblank"
  let found Int32 1
  let nothing Int32 0
:begin
  tabCheck: tab = compare.equalInt32(code, lit9=9)
  if tab matched spaceCheck
:spaceCheck
  spaceCheckNow: blank = compare.equalInt32(code, lit10=32)
  if blank matched missed
:matched
  return found
:missed
  return nothing

op iswcntrl "iswcntrl: glibc's class bit for a control character, 0 to 31 and 127, in the C locale (2), or 0"
  input code Int32 copied
  output Int32
  abi library "iswcntrl"
  let found Int32 2
  let nothing Int32 0
:begin
  lowCheck: low = betweenCodes(code, lit11=0, lit12=31)
  if low matched deleteCheck
:deleteCheck
  deleteNow: deleted = compare.equalInt32(code, lit13=127)
  if deleted matched missed
:matched
  return found
:missed
  return nothing

op iswdigit "iswdigit: glibc's class bit for a decimal digit in the C locale (2048), or 0"
  input code Int32 copied
  output Int32
  abi library "iswdigit"
  let found Int32 2048
  let nothing Int32 0
:begin
  digitCheck: digit = betweenCodes(code, lit14=48, lit15=57)
  if digit matched missed
:matched
  return found
:missed
  return nothing

op iswgraph "iswgraph: glibc's class bit for a printable character other than space in the C locale (32768), or 0"
  input code Int32 copied
  output Int32
  abi library "iswgraph"
  let found Int32 32768
  let nothing Int32 0
:begin
  graphCheck: graph = betweenCodes(code, lit16=33, lit17=126)
  if graph matched missed
:matched
  return found
:missed
  return nothing

op iswlower "iswlower: glibc's class bit for a lower-case letter, a to z, in the C locale (512), or 0"
  input code Int32 copied
  output Int32
  abi library "iswlower"
  let found Int32 512
  let nothing Int32 0
:begin
  lowerCheck: lower = betweenCodes(code, lit18=97, lit19=122)
  if lower matched missed
:matched
  return found
:missed
  return nothing

op iswprint "iswprint: glibc's class bit for a printable character, space included, in the C locale (16384), or 0"
  input code Int32 copied
  output Int32
  abi library "iswprint"
  let found Int32 16384
  let nothing Int32 0
:begin
  printCheck: printable = betweenCodes(code, lit20=32, lit21=126)
  if printable matched missed
:matched
  return found
:missed
  return nothing

op iswpunct "iswpunct: glibc's class bit for a printable character that is neither a letter, a digit, nor space, in the C locale (4), or 0"
  input code Int32 copied
  output Int32
  abi library "iswpunct"
  let found Int32 4
  let nothing Int32 0
:begin
  graphCheck: graph = betweenCodes(code, lit22=33, lit23=126)
  if graph alnumCheck missed
:alnumCheck
  alnumNow: alnum = alnumCode(code)
  notAlnum: other = logic.not(alnum)
  bothCheck: punct = logic.and(graph, other)
  if punct matched missed
:matched
  return found
:missed
  return nothing

op iswspace "iswspace: glibc's class bit for white space (space, 9 to 13) in the C locale (8192), or 0"
  input code Int32 copied
  output Int32
  abi library "iswspace"
  let found Int32 8192
  let nothing Int32 0
:begin
  controlCheck: controls = betweenCodes(code, lit24=9, lit25=13)
  if controls matched spaceCheck
:spaceCheck
  spaceNow: blank = compare.equalInt32(code, lit26=32)
  if blank matched missed
:matched
  return found
:missed
  return nothing

op iswupper "iswupper: glibc's class bit for an upper-case letter, A to Z, in the C locale (256), or 0"
  input code Int32 copied
  output Int32
  abi library "iswupper"
  let found Int32 256
  let nothing Int32 0
:begin
  upperCheck: upper = betweenCodes(code, lit27=65, lit28=90)
  if upper matched missed
:matched
  return found
:missed
  return nothing

op iswxdigit "iswxdigit: glibc's class bit for a hexadecimal digit in the C locale (4096), or 0"
  input code Int32 copied
  output Int32
  abi library "iswxdigit"
  let found Int32 4096
  let nothing Int32 0
:begin
  digitCheck: digit = betweenCodes(code, lit29=48, lit30=57)
  if digit matched upperCheck
:upperCheck
  upperNow: upperHex = betweenCodes(code, lit31=65, lit32=70)
  if upperHex matched lowerCheck
:lowerCheck
  lowerNow: lowerHex = betweenCodes(code, lit33=97, lit34=102)
  if lowerHex matched missed
:matched
  return found
:missed
  return nothing

op towupper "towupper: a to z made A to Z, every other code (outside 0 to 127 too) as it is in the C locale"
  invariant raisesAscii "Turns a to z into A to Z and leaves every other code as it is"
  input code Int32 copied
  output Int32
  abi library "towupper"
  let gap Int32 32
:begin
  lowerCheck: lower = betweenCodes(code, lit35=97, lit36=122)
  if lower shift keep
:shift
  shiftIt: raised = math.subtractInt32(code, gap)
  return raised
:keep
  return code

op towlower "towlower: A to Z made a to z, every other code (outside 0 to 127 too) as it is in the C locale"
  invariant lowersAscii "Turns A to Z into a to z and leaves every other code as it is"
  input code Int32 copied
  output Int32
  abi library "towlower"
  let gap Int32 32
:begin
  upperCheck: upper = betweenCodes(code, lit37=65, lit38=90)
  if upper shift keep
:shift
  shiftIt: lowered = math.addInt32(code, gap)
  return lowered
:keep
  return code

op wctype "wctype: the class's handle (its class bit, never 0) for a class name of the C locale, or 0 for any other name"
  input name machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "wctype"
  let alnumText String "alnum"
  let alphaText String "alpha"
  let blankText String "blank"
  let cntrlText String "cntrl"
  let digitText String "digit"
  let graphText String "graph"
  let lowerText String "lower"
  let printText String "print"
  let punctText String "punct"
  let spaceText String "space"
  let upperText String "upper"
  let xdigitText String "xdigit"
  let nothing Int64 0
:begin
  alnumCheck: isAlnum = nameIs(name, alnumText)
  if isAlnum giveAlnum alphaCheck
:giveAlnum
  return alnumBit
:alphaCheck
  alphaNow: isAlpha = nameIs(name, alphaText)
  if isAlpha giveAlpha blankCheck
:giveAlpha
  return alphaBit
:blankCheck
  blankNow: isBlank = nameIs(name, blankText)
  if isBlank giveBlank cntrlCheck
:giveBlank
  return blankBit
:cntrlCheck
  cntrlNow: isCntrl = nameIs(name, cntrlText)
  if isCntrl giveCntrl digitCheck
:giveCntrl
  return cntrlBit
:digitCheck
  digitNow: isDigit = nameIs(name, digitText)
  if isDigit giveDigit graphCheck
:giveDigit
  return digitBit
:graphCheck
  graphNow: isGraph = nameIs(name, graphText)
  if isGraph giveGraph lowerCheck
:giveGraph
  return graphBit
:lowerCheck
  lowerNow: isLower = nameIs(name, lowerText)
  if isLower giveLower printCheck
:giveLower
  return lowerBit
:printCheck
  printNow: isPrint = nameIs(name, printText)
  if isPrint givePrint punctCheck
:givePrint
  return printBit
:punctCheck
  punctNow: isPunct = nameIs(name, punctText)
  if isPunct givePunct spaceCheck
:givePunct
  return punctBit
:spaceCheck
  spaceNow: isSpace = nameIs(name, spaceText)
  if isSpace giveSpace upperCheck
:giveSpace
  return spaceBit
:upperCheck
  upperNow: isUpper = nameIs(name, upperText)
  if isUpper giveUpper xdigitCheck
:giveUpper
  return upperBit
:xdigitCheck
  xdigitNow: isXdigit = nameIs(name, xdigitText)
  if isXdigit giveXdigit missed
:giveXdigit
  return xdigitBit
:missed
  return nothing

op iswctype "iswctype: the class's bit for a wint_t when the handle is that class's (the result of wctype), or 0"
  invariant handlesAgree "Gives the class function's result when the handle is wctype's for that class, and 0 for a handle that is not"
  input code Int32 copied
  input desc Int64 copied
  output Int32
  abi library "iswctype"
  let nothing Int32 0
:begin
  alnumCheck: isAlnum = compare.equalInt64(desc, lit39=8)
  if isAlnum alnumCase alphaCheck
:alnumCase
  alnumNow: alnumResult = iswalnum(code)
  return alnumResult
:alphaCheck
  alphaHandle: isAlpha = compare.equalInt64(desc, lit40=1024)
  if isAlpha alphaCase blankCheck
:alphaCase
  alphaNow: alphaResult = iswalpha(code)
  return alphaResult
:blankCheck
  blankHandle: isBlank = compare.equalInt64(desc, lit41=1)
  if isBlank blankCase cntrlCheck
:blankCase
  blankNow: blankResult = iswblank(code)
  return blankResult
:cntrlCheck
  cntrlHandle: isCntrl = compare.equalInt64(desc, lit42=2)
  if isCntrl cntrlCase digitCheck
:cntrlCase
  cntrlNow: cntrlResult = iswcntrl(code)
  return cntrlResult
:digitCheck
  digitHandle: isDigit = compare.equalInt64(desc, lit43=2048)
  if isDigit digitCase graphCheck
:digitCase
  digitNow: digitResult = iswdigit(code)
  return digitResult
:graphCheck
  graphHandle: isGraph = compare.equalInt64(desc, lit44=32768)
  if isGraph graphCase lowerCheck
:graphCase
  graphNow: graphResult = iswgraph(code)
  return graphResult
:lowerCheck
  lowerHandle: isLower = compare.equalInt64(desc, lit45=512)
  if isLower lowerCase printCheck
:lowerCase
  lowerNow: lowerResult = iswlower(code)
  return lowerResult
:printCheck
  printHandle: isPrint = compare.equalInt64(desc, lit46=16384)
  if isPrint printCase punctCheck
:printCase
  printNow: printResult = iswprint(code)
  return printResult
:punctCheck
  punctHandle: isPunct = compare.equalInt64(desc, lit47=4)
  if isPunct punctCase spaceCheck
:punctCase
  punctNow: punctResult = iswpunct(code)
  return punctResult
:spaceCheck
  spaceHandle: isSpace = compare.equalInt64(desc, lit48=8192)
  if isSpace spaceCase upperCheck
:spaceCase
  spaceNow: spaceResult = iswspace(code)
  return spaceResult
:upperCheck
  upperHandle: isUpper = compare.equalInt64(desc, lit49=256)
  if isUpper upperCase xdigitCheck
:upperCase
  upperNow: upperResult = iswupper(code)
  return upperResult
:xdigitCheck
  xdigitHandle: isXdigit = compare.equalInt64(desc, lit50=4096)
  if isXdigit xdigitCase missed
:xdigitCase
  xdigitNow: xdigitResult = iswxdigit(code)
  return xdigitResult
:missed
  return nothing

op wctrans "wctrans: the handle of \"tolower\" (1) or \"toupper\" (2), or 0 for any other name"
  input name machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "wctrans"
  let lowerText String "tolower"
  let upperText String "toupper"
  let nothing Int64 0
  let lowerHandle Int64 1
  let upperHandle Int64 2
:begin
  lowerCheck: isLower = nameIs(name, lowerText)
  if isLower giveLower upperCheck
:giveLower
  return lowerHandle
:upperCheck
  upperCheckNow: isUpper = nameIs(name, upperText)
  if isUpper giveUpper missed
:giveUpper
  return upperHandle
:missed
  return nothing

op towctrans "towctrans: the wint_t mapped by a handle of wctrans (1 tolower, 2 toupper); any other handle gives the code as it is"
  input code Int32 copied
  input desc Int64 copied
  output Int32
  abi library "towctrans"
:begin
  lowerCheck: isLower = compare.equalInt64(desc, lit51=1)
  if isLower lowering upperCheck
:lowering
  lowered: result = towlower(code)
  return result
:upperCheck
  upperCheckNow: isUpper = compare.equalInt64(desc, lit52=2)
  if isUpper raising keep
:raising
  raised: result2 = towupper(code)
  return result2
:keep
  return code

## ---------------------------------------------------------------- wchar.h: strings (wide characters)

op wcslen "wcslen: how many wide characters come before the first 0"
  input text machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "wcslen"
  let at Int64 0 mut
:begin
  goto eachUnit
:eachUnit loop=while max=forever
  readIt: value = unitAt(text, at)
  endCheck: ended = compare.equalInt32(value, lit53=0)
  if ended done advance
:advance in=eachUnit
  stepIt: next = math.addInt64(at, lit54=1)
  set at next
  goto eachUnit
:done
  return at

op wcsnlen "wcsnlen: how many wide characters come before the first 0, at most a limit"
  input text machine.Address copied
  input most Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "wcsnlen"
  let at Int64 0 mut
:begin
  goto eachUnit
:eachUnit loop=while max=forever
  limitCheck: atLimit = compare.greaterOrEqualInt64(at, most)
  if atLimit done readUnit
:readUnit in=eachUnit
  readIt: value = unitAt(text, at)
  endCheck: ended = compare.equalInt32(value, lit55=0)
  if ended done advance
:advance in=eachUnit
  stepIt: next = math.addInt64(at, lit56=1)
  set at next
  goto eachUnit
:done
  return at

op fillUnits "Set a number of wchar_t of an array to a value"
  input target machine.Address copied
  input value Int32 copied
  input count Int64 copied
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  goto eachUnit
:eachUnit loop=while max=forever
  doneCheck: finished = compare.greaterOrEqualInt64(at, count)
  if finished finish store
:store in=eachUnit
  putIt: putUnit(target, at, value)
  stepIt: next = math.addInt64(at, lit57=1)
  set at next
  goto eachUnit
:finish
  return

op compareUnits "The difference-sign of two wchar_t runs: -1 or 1 at the first differing one (the smaller is -1), or 0; stops at 0 when stopAtNul is set, and at most `most` units"
  input left machine.Address copied
  input right machine.Address copied
  input most Int64 copied
  input stopAtNul Bool copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let minus Int32 -1
  let plus Int32 1
  let nothing Int32 0
:begin
  goto eachUnit
:eachUnit loop=while max=forever
  limitCheck: atLimit = compare.greaterOrEqualInt64(at, most)
  if atLimit matched readLeft
:readLeft in=eachUnit
  leftIt: a = unitAt(left, at)
  rightIt: b = unitAt(right, at)
  sameCheck: same = compare.equalInt32(a, b)
  if same sameUnit differs
:sameUnit in=eachUnit
  endCheck: ended = compare.equalInt32(a, lit58=0)
  stopCheck: stopNow = logic.and(ended, stopAtNul)
  if stopNow matched advance
:advance in=eachUnit
  stepIt: next = math.addInt64(at, lit59=1)
  set at next
  goto eachUnit
:differs
  lessCheck: smaller = compare.lessThanInt32(a, b)
  if smaller lower higher
:lower
  return minus
:higher
  return plus
:matched
  return nothing

op firstOutside "The index of the first wchar_t from a start that is 0 or not in a set of wchar_t (a 0-ended array)"
  input text machine.Address copied
  input start Int64 copied
  input set machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  set at start
  goto eachUnit
:eachUnit loop=while max=forever
  readIt: value = unitAt(text, at)
  endCheck: ended = compare.equalInt32(value, lit60=0)
  if ended matched testSet
:testSet in=eachUnit
  memberCheck: inside = inUnitSet(value, set)
  if inside advance matched
:advance in=eachUnit
  stepIt: next = math.addInt64(at, lit61=1)
  set at next
  goto eachUnit
:matched
  return at

op firstInside "The index of the first wchar_t from a start that is 0 or in a set of wchar_t (a 0-ended array)"
  input text machine.Address copied
  input start Int64 copied
  input set machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  set at start
  goto eachUnit
:eachUnit loop=while max=forever
  readIt: value = unitAt(text, at)
  endCheck: ended = compare.equalInt32(value, lit62=0)
  if ended matched testSet
:testSet in=eachUnit
  memberCheck: inside = inUnitSet(value, set)
  if inside matched advance
:advance in=eachUnit
  stepIt: next = math.addInt64(at, lit63=1)
  set at next
  goto eachUnit
:matched
  return at

op inUnitSet "Whether a wchar_t (not 0) is one of the wchar_t of a 0-ended array"
  input value Int32 copied
  input set machine.Address copied
  output Bool
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let yes Bool true
  let no Bool false
:begin
  goto eachUnit
:eachUnit loop=while max=forever
  readIt: member = unitAt(set, at)
  endCheck: ended = compare.equalInt32(member, lit64=0)
  if ended absent testMember
:testMember in=eachUnit
  sameCheck: same = compare.equalInt32(member, value)
  if same present advance
:advance in=eachUnit
  stepIt: next = math.addInt64(at, lit65=1)
  set at next
  goto eachUnit
:absent
  return no
:present
  return yes

op unitFind "The index of the first wchar_t of a 0-ended array that is a value, the 0 included, or -1"
  input text machine.Address copied
  input value Int32 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let missing Int64 -1
:begin
  goto eachUnit
:eachUnit loop=while max=forever
  readIt: unit = unitAt(text, at)
  sameCheck: same = compare.equalInt32(unit, value)
  if same found checkEnd
:checkEnd in=eachUnit
  endCheck: ended = compare.equalInt32(unit, lit66=0)
  if ended absent advance
:advance in=eachUnit
  stepIt: next = math.addInt64(at, lit67=1)
  set at next
  goto eachUnit
:found
  return at
:absent
  return missing

op unitFindLast "The index of the last wchar_t of a 0-ended array that is a value, the 0 included, or -1"
  input text machine.Address copied
  input value Int32 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let found Int64 -1 mut
  let missing Int64 -1
:begin
  goto eachUnit
:eachUnit loop=while max=forever
  readIt: unit = unitAt(text, at)
  sameCheck: same = compare.equalInt32(unit, value)
  if same remember checkEnd
:remember in=eachUnit
  set found at
  goto checkEnd
:checkEnd in=eachUnit
  endCheck: ended = compare.equalInt32(unit, lit68=0)
  if ended finish advance
:advance in=eachUnit
  stepIt: next = math.addInt64(at, lit69=1)
  set at next
  goto eachUnit
:finish
  return found

op scaledPlace "The address of an index of an array of wchar_t"
  input base machine.Address copied
  input index Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  scaleIt: offset = math.multiplyInt64(index, wideSize)
  findPlace: place = machine.offset(base, offset)
  return place

op wcscpy "wcscpy: copy a 0-ended wchar_t array, the 0 included; gives the target"
  invariant copiesWide "Copies the wide characters and the 0, and gives the target"
  input target machine.Address copied
  input source machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "wcscpy"
:begin
  lengthIt: count = wcslen(source)
  withEnd: units = math.addInt64(count, lit70=1)
  bytesIt: bytes = math.multiplyInt64(units, wideSize)
  copyIt: copiedAt = memory.copyForward(target, source, bytes)
  return target

op wcsncpy "wcsncpy: copy at most a count of wchar_t of a 0-ended array, then 0s until the count is written; gives the target"
  invariant padsWithZeros "Copies at most the count and pads with 0s up to the count, with no 0 when the text fills it"
  input target machine.Address copied
  input source machine.Address copied
  input most Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "wcsncpy"
:begin
  lengthIt: count = wcsnlen(source, most)
  bytesIt: bytes = math.multiplyInt64(count, wideSize)
  copyIt: copiedAt = memory.copyForward(target, source, bytes)
  restIt: rest = math.subtractInt64(most, count)
  restPlace: restAt = scaledPlace(target, count)
  padIt: fillUnits(restAt, lit71=0, rest)
  return target

op wcscat "wcscat: copy a 0-ended wchar_t array to the end of another, the 0 included; gives the target"
  input target machine.Address copied
  input source machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "wcscat"
:begin
  lengthIt: filled = wcslen(target)
  endPlace: endAt = scaledPlace(target, filled)
  sourceLength: count = wcslen(source)
  withEnd: units = math.addInt64(count, lit72=1)
  bytesIt: bytes = math.multiplyInt64(units, wideSize)
  copyIt: copiedAt = memory.copyForward(endAt, source, bytes)
  return target

op wcsncat "wcsncat: copy at most a count of wchar_t of a 0-ended array to the end of another, then a 0; gives the target"
  input target machine.Address copied
  input source machine.Address copied
  input most Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "wcsncat"
:begin
  lengthIt: filled = wcslen(target)
  endPlace: endAt = scaledPlace(target, filled)
  countIt: count = wcsnlen(source, most)
  bytesIt: bytes = math.multiplyInt64(count, wideSize)
  copyIt: copiedAt = memory.copyForward(endAt, source, bytes)
  putIt: putUnit(endAt, count, lit73=0)
  return target

op wcscmp "wcscmp: -1, 0, or 1 as the first differing wchar_t of two 0-ended arrays is smaller, or they are equal"
  invariant ordersBySign "Gives -1, 0, or 1 by the first differing wide character"
  input left machine.Address copied
  input right machine.Address copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "wcscmp"
  let stops Bool true
:begin
  compareIt: order = compareUnits(left, right, forever, stops)
  return order

op wcsncmp "wcsncmp: wcscmp of at most a count of wchar_t"
  input left machine.Address copied
  input right machine.Address copied
  input most Int64 copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "wcsncmp"
  let stops Bool true
:begin
  compareIt: order = compareUnits(left, right, most, stops)
  return order

op wcscoll "wcscoll: wcscmp, which is the C locale's collation"
  input left machine.Address copied
  input right machine.Address copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "wcscoll"
:begin
  compareIt: order = wcscmp(left, right)
  return order

op wcsxfrm "wcsxfrm: the length of a 0-ended array; in the C locale the transformed text is the text, of which the first count wchar_t (the 0 among them when they reach it) are copied"
  input target machine.Address copied
  input source machine.Address copied
  input most Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "wcsxfrm"
:begin
  lengthIt: count = wcslen(source)
  withEnd: units = math.addInt64(count, lit74=1)
  fitCheck: fits = compare.lessThanInt64(units, most)
  if fits whole partial
:whole
  bytesWhole: bytes = math.multiplyInt64(units, wideSize)
  copyWhole: copiedAt = memory.copyForward(target, source, bytes)
  return count
:partial
  bytesPart: partBytes = math.multiplyInt64(most, wideSize)
  copyPart: partAt = memory.copyForward(target, source, partBytes)
  return count

op wcschr "wcschr: the address of the first wchar_t of a 0-ended array that is a value (the 0 counts), or the address 0"
  invariant findsUnit "Gives the address of the first wide character that is the value, the 0 counting, or the address 0"
  input text machine.Address copied
  input value Int32 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "wcschr"
:begin
  findIt: index = unitFind(text, value)
  missingCheck: missing = compare.lessThanInt64(index, lit75=0)
  if missing nowhere here
:here
  placeIt: place = scaledPlace(text, index)
  return place
:nowhere
  zeroIt: anywhere = machine.zero()
  return anywhere

op wcsrchr "wcsrchr: the address of the last wchar_t of a 0-ended array that is a value (the 0 counts), or the address 0"
  input text machine.Address copied
  input value Int32 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "wcsrchr"
:begin
  findIt: index = unitFindLast(text, value)
  missingCheck: missing = compare.lessThanInt64(index, lit76=0)
  if missing nowhere here
:here
  placeIt: place = scaledPlace(text, index)
  return place
:nowhere
  zeroIt: anywhere = machine.zero()
  return anywhere

op wcsstr "wcsstr: the address of the first place a 0-ended array holds another, the text itself for an empty one, or the address 0"
  invariant findsWideText "Gives the address of the first place the needle starts, the haystack for an empty needle, or the address 0"
  input haystack machine.Address copied
  input needle machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "wcsstr"
  let at Int64 0 mut
  let no Bool false
:begin
  needleLength: units = wcslen(needle)
  emptyCheck: empty = compare.equalInt64(units, lit77=0)
  if empty whole scan
:whole
  return haystack
:scan
  goto eachStart
:eachStart loop=while max=forever
  readIt: value = unitAt(haystack, at)
  endCheck: ended = compare.equalInt32(value, lit78=0)
  if ended missing testStart
:testStart in=eachStart
  startPlace: startAt = scaledPlace(haystack, at)
  compareIt: order = compareUnits(startAt, needle, units, no)
  sameCheck: same = compare.equalInt32(order, lit79=0)
  if same matched advance
:advance in=eachStart
  stepIt: next = math.addInt64(at, lit80=1)
  set at next
  goto eachStart
:matched
  foundPlace: found = scaledPlace(haystack, at)
  return found
:missing
  zeroIt: anywhere = machine.zero()
  return anywhere

op wcsspn "wcsspn: how many wchar_t a 0-ended array starts with that are in another's"
  input text machine.Address copied
  input accept machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "wcsspn"
:begin
  spanIt: count = firstOutside(text, lit81=0, accept)
  return count

op wcscspn "wcscspn: how many wchar_t a 0-ended array starts with that are not in another's"
  input text machine.Address copied
  input reject machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "wcscspn"
:begin
  spanIt: count = firstInside(text, lit82=0, reject)
  return count

op wcspbrk "wcspbrk: the address of the first wchar_t of a 0-ended array that is in another's, or the address 0"
  input text machine.Address copied
  input accept machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "wcspbrk"
:begin
  findIt: index = firstInside(text, lit83=0, accept)
  readIt: value = unitAt(text, index)
  endCheck: ended = compare.equalInt32(value, lit84=0)
  if ended nowhere here
:here
  placeIt: place = scaledPlace(text, index)
  return place
:nowhere
  zeroIt: anywhere = machine.zero()
  return anywhere

op tokenFrom "wcstok's walk from a start (0 gives 0): the token, and the save pointer kept in the cell"
  input start machine.Address copied
  input delim machine.Address copied
  input saveAt machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  nowhere: anywhere = machine.zero()
  startCheck: nobody = machine.equal(start, anywhere)
  if nobody absent skipFirst
:absent
  return anywhere
:skipFirst
  headIt: head = firstOutside(start, lit85=0, delim)
  headPlace: headAt = scaledPlace(start, head)
  headUnit: headValue = unitAt(start, head)
  headEnd: headEnded = compare.equalInt32(headValue, lit86=0)
  if headEnded noTokens findEnd
:noTokens
  storeNone: machine.storeAddress(saveAt, headAt)
  return anywhere
:findEnd
  tailIt: tail = firstInside(start, head, delim)
  tailPlace: tailAt = scaledPlace(start, tail)
  tailUnit: tailValue = unitAt(start, tail)
  tailEnd: tailEnded = compare.equalInt32(tailValue, lit87=0)
  if tailEnded lastToken cutToken
:lastToken
  storeLast: machine.storeAddress(saveAt, tailAt)
  return headAt
:cutToken
  cutIt: putUnit(start, tail, lit88=0)
  afterPlace: afterAt = machine.offset(tailAt, wideSize)
  storeNext: machine.storeAddress(saveAt, afterAt)
  return headAt

op wcstok "wcstok: the next token of a 0-ended array, its delimiters in another, with the walk kept in the cell saveptr (on a NULL text it resumes there)"
  invariant cutsTokens "Gives each token in turn, cutting at a delimiter, keeping its place in the cell, and the address 0 at the end"
  input text machine.Address copied
  input delim machine.Address copied
  input saveAt machine.Address copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "wcstok"
:begin
  nowhere: anywhere = machine.zero()
  freshCheck: fresh = machine.equal(text, anywhere)
  if fresh resume continueWalk
:resume
  readSaved: saved = machine.loadAddress(saveAt)
  resumeIt: token = tokenFrom(saved, delim, saveAt)
  return token
:continueWalk
  walkIt: walked = tokenFrom(text, delim, saveAt)
  return walked

op wcsdup "wcsdup: a copy of a 0-ended wchar_t array in a block malloc gives"
  input text machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "wcsdup"
:begin
  lengthIt: count = wcslen(text)
  withEnd: units = math.addInt64(count, lit89=1)
  bytesIt: bytes = math.multiplyInt64(units, wideSize)
  takeIt: block = heap.take(bytes)
  copyIt: copiedAt = memory.copyForward(block, text, bytes)
  return block

op wmemchr "wmemchr: the address of the first of n wchar_t that is a value, or the address 0"
  input text machine.Address copied
  input value Int32 copied
  input count Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "wmemchr"
  let at Int64 0 mut
:begin
  goto eachUnit
:eachUnit loop=while max=forever
  doneCheck: finished = compare.greaterOrEqualInt64(at, count)
  if finished nowhere readUnit
:readUnit in=eachUnit
  readIt: unit = unitAt(text, at)
  sameCheck: same = compare.equalInt32(unit, value)
  if same found advance
:advance in=eachUnit
  stepIt: next = math.addInt64(at, lit90=1)
  set at next
  goto eachUnit
:found
  foundPlace: place = scaledPlace(text, at)
  return place
:nowhere
  zeroIt: anywhere = machine.zero()
  return anywhere

op wmemcmp "wmemcmp: -1, 0, or 1 as the first differing of n wchar_t is smaller, or they are equal"
  input left machine.Address copied
  input right machine.Address copied
  input count Int64 copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "wmemcmp"
  let no Bool false
:begin
  compareIt: order = compareUnits(left, right, count, no)
  return order

op wmemcpy "wmemcpy: copy n wchar_t; gives the target"
  input target machine.Address copied
  input source machine.Address copied
  input count Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "wmemcpy"
:begin
  bytesIt: bytes = math.multiplyInt64(count, wideSize)
  copyIt: copiedAt = memory.copyForward(target, source, bytes)
  return target

op wmemmove "wmemmove: copy n wchar_t that may overlap; gives the target"
  input target machine.Address copied
  input source machine.Address copied
  input count Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "wmemmove"
:begin
  bytesIt: bytes = math.multiplyInt64(count, wideSize)
  moveIt: movedAt = memory.moveBytes(target, source, bytes)
  return target

op wmemset "wmemset: set n wchar_t to a value; gives the target"
  input target machine.Address copied
  input value Int32 copied
  input count Int64 copied
  output machine.Address
  effect use machine.memory
  uses memoryAccess
  abi library "wmemset"
:begin
  fillIt: fillUnits(target, value, count)
  return target

## ---------------------------------------------------------------- stdlib.h and wchar.h: numbers in text

op narrowUnits "Copy the wchar_t of a text to bytes: each that is 0 to 127 as itself, any other as 128 (which no number reads)"
  input text machine.Address copied
  input count Int64 copied
  input block machine.Address copied
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let code Int64 128 mut
  let big Int64 128
:begin
  goto eachUnit
:eachUnit loop=while max=forever
  doneCheck: finished = compare.greaterOrEqualInt64(at, count)
  if finished finish readUnit
:readUnit in=eachUnit
  readIt: value = unitAt(text, at)
  asciiCheck: ascii = betweenCodes(value, lit91=0, lit92=127)
  if ascii keep replace
:keep in=eachUnit
  widenIt: widened = convert.int32ToInt64(value)
  set code widened
  goto store
:replace in=eachUnit
  set code big
  goto store
:store in=eachUnit
  putIt: putByteAt(block, at, code)
  stepIt: next = math.addInt64(at, lit93=1)
  set at next
  goto eachUnit
:finish
  return

op narrowText "A block holding a wchar_t text as bytes (1:1 for ASCII) with a 0 byte, and room after it for a parse's end cell; its bytes are heap memory"
  input text machine.Address copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  countIt: units = wcslen(text)
  roomIt: room = math.addInt64(units, lit94=9)
  takeIt: block = heap.take(room)
  narrowIt: narrowUnits(text, units, block)
  return block

op storeWideEnd "Store, at an address unless it is 0, the wide place where a parse over a narrowed block ended"
  input text machine.Address copied
  input block machine.Address copied
  input cell machine.Address copied
  input endAt machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  nowhere: anywhere = machine.zero()
  readEnd: end = machine.loadAddress(cell)
  consumedIt: consumed = machine.difference(end, block)
  widthIt: wideBytes = math.multiplyInt64(consumed, wideSize)
  wideAt: place = machine.offset(text, wideBytes)
  nullCheck: absent = machine.equal(endAt, anywhere)
  if absent done store
:store
  storeIt: machine.storeAddress(endAt, place)
  goto done
:done
  return

op parseWide "wcstol and its kin: the wide text as bytes, read by parseWhole (C17) or parseWholeBinary (C23's 0b, D-173), the end stored as a wide place"
  input text machine.Address copied
  input endAt machine.Address copied
  input base Int32 copied
  input unsigned Bool copied
  input binary Bool copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  narrowIt: block = narrowText(text)
  countIt: units = wcslen(text)
  cellIndex: afterUnits = math.addInt64(units, lit95=1)
  cellPlace: cell = machine.offset(block, afterUnits)
  value = readWhole(block, cell, base, unsigned, binary)
  endIt: storeWideEnd(text, block, cell, endAt)
  giveIt: heap.give(block)
  return value

op parseWideReal "wcstod: the wide text as bytes, read by parseReal (strtod), the end stored as a wide place"
  input text machine.Address copied
  input endAt machine.Address copied
  output Float64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  narrowIt: block = narrowText(text)
  countIt: units = wcslen(text)
  cellIndex: afterUnits = math.addInt64(units, lit96=1)
  cellPlace: cell = machine.offset(block, afterUnits)
  parseIt: value = clibrary.parseReal(block, cell)
  endIt: storeWideEnd(text, block, cell, endAt)
  giveIt: heap.give(block)
  return value

op wcstol "wcstol: a wide text's leading whole number as a long in a base, with the end stored at endptr unless it is 0"
  invariant readsWideNumber "Reads a number from wide text as strtol does from bytes, stopping at any wide character that is not ASCII"
  input text machine.Address copied
  input endAt machine.Address copied
  input base Int32 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "wcstol"
  let mode Bool false
:begin
  parseIt: value = parseWide(text, endAt, base, mode, false)
  return value

op wcstoll "wcstoll: a wide text's leading whole number as a long long in a base, with the end stored at endptr unless it is 0"
  input text machine.Address copied
  input endAt machine.Address copied
  input base Int32 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "wcstoll"
  let mode Bool false
:begin
  parseIt: value = parseWide(text, endAt, base, mode, false)
  return value

op wcstoul "wcstoul: a wide text's leading whole number as an unsigned long in a base, with the end stored at endptr unless it is 0"
  input text machine.Address copied
  input endAt machine.Address copied
  input base Int32 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "wcstoul"
  let mode Bool true
:begin
  parseIt: value = parseWide(text, endAt, base, mode, false)
  return value

op wcstoull "wcstoull: a wide text's leading whole number as an unsigned long long in a base, with the end stored at endptr unless it is 0"
  input text machine.Address copied
  input endAt machine.Address copied
  input base Int32 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "wcstoull"
  let mode Bool true
:begin
  parseIt: value = parseWide(text, endAt, base, mode, false)
  return value

op wcstod "wcstod: a wide text's leading number as a double (strtod's reading), with the end stored at endptr unless it is 0"
  input text machine.Address copied
  input endAt machine.Address copied
  output Float64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "wcstod"
:begin
  parseIt: value = parseWideReal(text, endAt)
  return value

## wcstof (D-164 wrote strtof the same way): the double strtod reads, rounded to a float on integer bits, so no float
## operation can trap or round twice. A double rounds to a different float than the number itself does only when the
## double lies exactly halfway between two floats and the number does not; then the number's digits are compared with
## that halfway value in bignum. ERANGE is set as for strtof: past the largest float, and for a decimal number that
## reads as a subnormal float or as 0 (a hexadecimal one only when inexact).

op hexLeading "Whether a C string, after white space and a sign, starts with 0x or 0X"
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

op exactOrder "How the number a C string starts with compares with a double given as mantissa times 2 to an exponent: -1 below it, 0 equal, 1 above; the text's digits are kept to 700 decimal (400 hexadecimal) places with a last 1 standing for any dropped that are not zero, and both sides are made whole numbers in bignum"
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

op nearestSingle "The bits of the float nearest a positive finite double (ties to even), judged by the number the text gives when the double is exactly halfway between two floats; the cell singleInexactAt holds 1 unless the float is the double itself"
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
  flagCell = kernel.stateAt(singleInexactAt)
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
  order = exactOrder(text, significand, q)
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

op singleFromBytes "A C string's leading number as a float, correctly rounded (the double strtod reads is corrected where it lies exactly between two floats), the cell given receiving where it ends; ERANGE as glibc's strtof sets it"
  input text machine.Address copied
  input endCell machine.Address copied
  output Float32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let singleBits UInt64 0 mut
  let doubleBits UInt64 0 mut
:begin
  errnoCell = clibrary.errnoCell()
  saved = machine.loadInt32(errnoCell)
  machine.storeInt32(errnoCell, 0)
  parsedValue = clibrary.parseReal(text, endCell)
  parsed = machine.loadInt32(errnoCell)
  machine.storeInt32(errnoCell, saved)
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
  when parsed != 0 setRange build
:finite
  singleMagnitude = nearestSingle(text, magnitude)
  inexactCell = kernel.stateAt(singleInexactAt)
  inexact = machine.loadInt64(inexactCell)
  calc singleBits := signPart | singleMagnitude
  when singleMagnitude >= 2139095040 setRange tinyCheck
:setRange
  clibrary.setErrno(rangeErrorNumber)
  goto build
:tinyCheck
  when singleMagnitude < 8388608 tiny build
:tiny
  when magnitude == 0 zeroValue nonzeroTiny
:zeroValue
  when parsed != 0 setRange build
:nonzeroTiny
  isHexText = hexLeading(text)
  when isHexText hexTiny setRange
:hexTiny
  calc hexReason = inexact != 0 || parsed != 0
  when hexReason setRange build
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

op wcstof "wcstof: a wide text's leading number as a float, correctly rounded once from the text itself, with the end stored at endptr unless it is 0"
  invariant roundsOnce "Gives the float nearest the number the text holds, even where the double it rounds to is exactly between two floats"
  input text machine.Address copied
  input endAt machine.Address copied
  output Float32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "wcstof"
:begin
  narrowIt: block = narrowText(text)
  countIt: units = wcslen(text)
  cellIndex: afterUnits = math.addInt64(units, lit96b=1)
  cellPlace: cell = machine.offset(block, afterUnits)
  parseIt: value = singleFromBytes(block, cell)
  endIt: storeWideEnd(text, block, cell, endAt)
  giveIt: heap.give(block)
  return value

## ---------------------------------------------------------------- wchar.h and stdlib.h: multibyte text

op lengthOfLead "How many wide characters a decoded byte (0 for NUL, which is 0 bytes, else 1) takes"
  input value Int64 copied
  output Int64
  let one Int64 1
  let zero Int64 0
:begin
  nulCheck: nul = compare.equalInt64(value, lit97=0)
  if nul empty counted
:empty
  return zero
:counted
  return one

op decodeLead "The first byte of a multibyte text as its value 0 to 127, 0 for a null pointer, -2 when n is 0 (incomplete), or -1 with EILSEQ for a byte past 127 (not ASCII, so no character of the C locale)"
  input text machine.Address copied
  input bytes Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let incomplete Int64 -2
  let zeroValue Int64 0
  let invalidSequence Int64 -1
:begin
  nowhere: anywhere = machine.zero()
  nullCheck: absent = machine.equal(text, anywhere)
  if absent nothing sized
:nothing
  return zeroValue
:sized
  emptyCheck: empty = compare.equalInt64(bytes, lit98=0)
  if empty incompleteCase readIt
:incompleteCase
  return incomplete
:readIt
  readValue: value = byteValueAt(text, lit99=0)
  asciiCheck: ascii = compare.lessThanInt64(value, lit99b=128)
  if ascii giveValue invalid
:giveValue
  return value
:invalid
  setErrnoIt: clibrary.setErrno(eilseqError)
  return invalidSequence

op mbrlen "mbrlen: mbrtowc without the wide character"
  input text machine.Address copied
  input bytes Int64 copied
  input state machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "mbrlen"
:begin
  decodeIt: value = decodeLead(text, bytes)
  incompleteCheck: incomplete = compare.lessThanInt64(value, lit100=0)
  if incomplete waiting taken
:taken
  lengthIt: length = lengthOfLead(value)
  return length
:waiting
  return value

op mbrtowc "mbrtowc: the bytes of one multibyte character as a wchar_t (its byte value), with the bytes it took (0 for NUL, -2 when none of n is there)"
  invariant readsOneByte "Gives a byte as the wide character of the same value, 0 for a 0 byte, and -2 when no byte is given"
  input wide machine.Address copied
  input text machine.Address copied
  input bytes Int64 copied
  input state machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "mbrtowc"
:begin
  decodeIt: value = decodeLead(text, bytes)
  incompleteCheck: incomplete = compare.lessThanInt64(value, lit101=0)
  if incomplete waiting storeIt
:storeIt
  narrowIt: wideValue = convert.int64ToInt32(value)
  putIt: putUnitIf(wide, lit102=0, wideValue)
  lengthIt: length = lengthOfLead(value)
  return length
:waiting
  return value

op mblen "mblen: the bytes of the multibyte character at a text (0 for NUL, 1 otherwise), -1 for an incomplete one; 0 for a null pointer (stateless)"
  input text machine.Address copied
  input bytes Int64 copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "mblen"
  let failure Int32 -1
  let zeroOut Int32 0
:begin
  nowhere: anywhere = machine.zero()
  nullCheck: absent = machine.equal(text, anywhere)
  if absent noState measure
:noState
  return zeroOut
:measure
  decodeIt: value = decodeLead(text, bytes)
  incompleteCheck: incomplete = compare.lessThanInt64(value, lit103=0)
  if incomplete failed counted
:counted
  lengthIt: length = lengthOfLead(value)
  narrowIt: result = convert.int64ToInt32(length)
  return result
:failed
  return failure

op mbtowc "mbtowc: mblen, also giving the wchar_t of the character at pwc unless it is 0"
  input wide machine.Address copied
  input text machine.Address copied
  input bytes Int64 copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "mbtowc"
  let failure Int32 -1
  let zeroOut Int32 0
:begin
  nowhere: anywhere = machine.zero()
  nullCheck: absent = machine.equal(text, anywhere)
  if absent noState measure
:noState
  return zeroOut
:measure
  decodeIt: value = decodeLead(text, bytes)
  incompleteCheck: incomplete = compare.lessThanInt64(value, lit104=0)
  if incomplete failed storeIt
:storeIt
  narrowIt: wideValue = convert.int64ToInt32(value)
  putIt: putUnitIf(wide, lit105=0, wideValue)
  lengthIt: length = lengthOfLead(value)
  result: count = convert.int64ToInt32(length)
  return count
:failed
  return failure

op encodeOne "Store a wide value as one byte at s (unless s is 0): 1 for a value 0 to 127, else EILSEQ and -1"
  input text machine.Address copied
  input value Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let minus Int64 -1
  let one Int64 1
:begin
  lowCheck: negative = compare.lessThanInt64(value, lit106=0)
  if negative invalid highCheck
:highCheck
  highValue: tooBig = compare.greaterThanInt64(value, lit107=127)
  if tooBig invalid write
:write
  nowhere: anywhere = machine.zero()
  nullCheck: absent = machine.equal(text, anywhere)
  if absent done storeIt
:storeIt
  storeByte: putByteAt(text, lit108=0, value)
  goto done
:done
  return one
:invalid
  setErrnoIt: clibrary.setErrno(eilseqError)
  return minus

op wcrtomb "wcrtomb: the byte of a wide character written at s, 1 (a null s is wcrtomb of 0 into a scratch buffer: 1 whatever the character), or -1 with EILSEQ"
  invariant writesOneByte "Writes a wide character of 0 to 127 as a byte, and gives -1 with EILSEQ above 127"
  input text machine.Address copied
  input wide Int32 copied
  input state machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "wcrtomb"
  let one Int64 1
:begin
  nowhere: anywhere = machine.zero()
  nullCheck: absent = machine.equal(text, anywhere)
  if absent giveOne convert
:giveOne
  return one
:convert
  widenIt: value = convert.int32ToInt64(wide)
  encodeIt: result = encodeOne(text, value)
  return result

op wctomb "wctomb: wcrtomb without a state (0 for a null pointer), an int"
  input text machine.Address copied
  input wide Int32 copied
  output Int32
  effect use machine.memory
  uses memoryAccess
  abi library "wctomb"
  let failure Int32 -1
  let zeroOut Int32 0
:begin
  nowhere: anywhere = machine.zero()
  nullCheck: absent = machine.equal(text, anywhere)
  if absent noState measure
:noState
  return zeroOut
:measure
  widenIt: value = convert.int32ToInt64(wide)
  encodeIt: result = encodeOne(text, value)
  failedCheck: failed = compare.lessThanInt64(result, lit109=0)
  if failed giveFailure giveCount
:giveCount
  narrowIt: count = convert.int64ToInt32(result)
  return count
:giveFailure
  return failure

op mbsinit "mbsinit: 1, since the C locale's encoding has no shift state"
  input state machine.Address copied
  output Int32
  abi library "mbsinit"
  let one Int32 1
:begin
  return one

op btowc "btowc: the wint_t of an ASCII byte (0 to 127), or WEOF (-1) for EOF, a byte past 127, and any other int"
  input code Int32 copied
  output Int32
  abi library "btowc"
  let eof Int32 -1
:begin
  rangeCheck: inside = betweenCodes(code, lit110=0, lit111=127)
  if inside keep weof
:keep
  return code
:weof
  return eof

op wctob "wctob: the byte of a wint_t of 0 to 127, or EOF (-1) for WEOF and any other wint_t"
  input code Int32 copied
  output Int32
  abi library "wctob"
  let eof Int32 -1
:begin
  rangeCheck: inside = betweenCodes(code, lit112=0, lit113=127)
  if inside keep weof
:keep
  return code
:weof
  return eof

op mbstowcs "mbstowcs: the wide characters of a multibyte text (up to n, the 0 written when there is room), or the count of them when wide is 0"
  invariant convertsToWide "Converts bytes to wide characters up to the count, counting only when there is no target"
  input wide machine.Address copied
  input text machine.Address copied
  input most Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "mbstowcs"
:begin
  nowhere: anywhere = machine.zero()
  nullCheck: noWide = machine.equal(wide, anywhere)
  if noWide countAll bounded
:countAll
  countIt: counted = bytesToWide(wide, text, forever, anywhere)
  return counted
:bounded
  boundIt: limitedCount = bytesToWide(wide, text, most, anywhere)
  return limitedCount

op wcstombs "wcstombs: the bytes of a wide text (up to n, the 0 written when there is room), or -1 with EILSEQ"
  invariant convertsToBytes "Converts wide characters to bytes up to the count, and gives -1 with EILSEQ above 127"
  input text machine.Address copied
  input wide machine.Address copied
  input most Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "wcstombs"
:begin
  nowhere: anywhere = machine.zero()
  nullCheck: noText = machine.equal(text, anywhere)
  if noText countAll bounded
:countAll
  countIt: counted = wideToBytes(text, wide, forever, anywhere)
  return counted
:bounded
  boundIt: limitedCount = wideToBytes(text, wide, most, anywhere)
  return limitedCount

op bytesToWide "Convert up to a limit of bytes to wide characters at dst (0: count only), the 0 written when there is room; the source cell gets where it stopped (0 at the NUL), if it is not 0; gives the count, or -1 with EILSEQ at a byte past 127 (the source cell then at that byte)"
  input wide machine.Address copied
  input text machine.Address copied
  input limit Int64 copied
  input srcCell machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let minus Int64 -1
  let yes Bool true
  let no Bool false
:begin
  goto eachByte
:eachByte loop=while max=forever
  limitCheck: atLimit = compare.greaterOrEqualInt64(at, limit)
  if atLimit ended readByte
:readByte in=eachByte
  valueIt: value = byteValueAt(text, at)
  nulCheck: nul = compare.equalInt64(value, lit114=0)
  if nul nulEnd asciiByte
:asciiByte in=eachByte
  asciiCheck: ascii = compare.lessThanInt64(value, lit114b=128)
  if ascii storeChar invalid
:storeChar in=eachByte
  narrowIt: wideValue = convert.int64ToInt32(value)
  storeIt: putUnitIf(wide, at, wideValue)
  stepIt: next = math.addInt64(at, lit115=1)
  set at next
  goto eachByte
:nulEnd
  finishNul: finishTransfer(wide, srcCell, text, at, yes)
  return at
:ended
  finishEnd: finishTransfer(wide, srcCell, text, at, no)
  return at
:invalid
  setErrnoIt: clibrary.setErrno(eilseqError)
  nowhereCell: anywhereCell = machine.zero()
  noCell: noSrc = machine.equal(srcCell, anywhereCell)
  if noSrc refused remember
:remember
  stopPlace: stopAt = machine.offset(text, at)
  storeStop: machine.storeAddress(srcCell, stopAt)
  return minus
:refused
  return minus

op finishTransfer "After a byte to wide conversion: the 0 wide character when the text ended (if there is room), and the source cell's place (0 at the end, else the place reached)"
  input wide machine.Address copied
  input srcCell machine.Address copied
  input text machine.Address copied
  input at Int64 copied
  input ended Bool copied
  effect use machine.memory
  uses memoryAccess
:begin
  nowhere: anywhere = machine.zero()
  noWideCheck: noWide = machine.equal(wide, anywhere)
  if noWide done writeCheck
:writeCheck
  if ended writeNul cellPart
:writeNul
  endPut: putUnitIf(wide, at, lit116=0)
  goto cellPart
:cellPart
  noCell: noSrc = machine.equal(srcCell, anywhere)
  if noSrc done cellWork
:cellWork
  if ended storeZero storePlace
:storeZero
  zeroIt: machine.storeAddress(srcCell, anywhere)
  return
:storePlace
  placeIt: place = machine.offset(text, at)
  storePlaceIt: machine.storeAddress(srcCell, place)
  return
:done
  return

op wideToBytes "Convert up to a limit of wide characters to bytes at dst (0: count only), the 0 byte written when there is room; the source cell gets where it stopped (0 at the NUL), if it is not 0; gives the count, or -1 with EILSEQ"
  input text machine.Address copied
  input wide machine.Address copied
  input limit Int64 copied
  input srcCell machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
  let minus Int64 -1
  let yes Bool true
  let no Bool false
:begin
  goto eachUnit
:eachUnit loop=while max=forever
  limitCheck: atLimit = compare.greaterOrEqualInt64(at, limit)
  if atLimit ended readUnit
:readUnit in=eachUnit
  valueIt: value = unitAt(wide, at)
  nulCheck: nul = compare.equalInt32(value, lit117=0)
  if nul nulEnd rangeCheck
:rangeCheck in=eachUnit
  rangeNow: ok = betweenCodes(value, lit118=0, lit119=127)
  if ok storeChar invalid
:storeChar in=eachUnit
  narrowIt: byteValue = convert.int32ToInt64(value)
  putIt: putByteIf(text, at, byteValue)
  stepIt: next = math.addInt64(at, lit120=1)
  set at next
  goto eachUnit
:nulEnd
  finishNul: finishNarrow(text, srcCell, wide, at, yes)
  return at
:ended
  finishEnd: finishNarrow(text, srcCell, wide, at, no)
  return at
:invalid
  setErrnoIt: clibrary.setErrno(eilseqError)
  nowhereCell: anywhereCell = machine.zero()
  noCell: noSrc = machine.equal(srcCell, anywhereCell)
  if noSrc refused remember
:remember
  stopPlace: stopAt = scaledPlace(wide, at)
  storeStop: machine.storeAddress(srcCell, stopAt)
  return minus
:refused
  return minus

op finishNarrow "After a wide to byte conversion: the 0 byte when the text ended (if there is room), and the source cell's place (0 at the end, else the place reached in wide characters)"
  input text machine.Address copied
  input srcCell machine.Address copied
  input wide machine.Address copied
  input at Int64 copied
  input ended Bool copied
  effect use machine.memory
  uses memoryAccess
:begin
  nowhere: anywhere = machine.zero()
  noWideCheck: noWide = machine.equal(wide, anywhere)
  if noWide done writeCheck
:writeCheck
  if ended writeNul cellPart
:writeNul
  endPut: putByteIf(text, at, lit121=0)
  goto cellPart
:cellPart
  noCell: noSrc = machine.equal(srcCell, anywhere)
  if noSrc done cellWork
:cellWork
  if ended storeZero storePlace
:storeZero
  zeroIt: machine.storeAddress(srcCell, anywhere)
  return
:storePlace
  placeIt: place = scaledPlace(wide, at)
  storePlaceIt: machine.storeAddress(srcCell, place)
  return
:done
  return

op mbsrtowcs "mbsrtowcs: convert the bytes at *src to wide characters at dst (up to len, a 0 when the text ends), updating *src; with dst 0, count them"
  input wide machine.Address copied
  input srcCell machine.Address copied
  input most Int64 copied
  input state machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "mbsrtowcs"
:begin
  srcLoad: srcAt = machine.loadAddress(srcCell)
  nowhere: anywhere = machine.zero()
  nullCheck: noWide = machine.equal(wide, anywhere)
  if noWide countAll bounded
:countAll
  countIt: counted = bytesToWide(wide, srcAt, forever, anywhere)
  return counted
:bounded
  boundIt: limitedCount = bytesToWide(wide, srcAt, most, srcCell)
  return limitedCount

op wcsrtombs "wcsrtombs: convert the wide characters at *src to bytes at dst (up to len, a 0 when the text ends), updating *src; with dst 0, count them; -1 with EILSEQ for a wide character above 127"
  input text machine.Address copied
  input srcCell machine.Address copied
  input most Int64 copied
  input state machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "wcsrtombs"
:begin
  srcLoad: srcAt = machine.loadAddress(srcCell)
  nowhere: anywhere = machine.zero()
  nullCheck: noText = machine.equal(text, anywhere)
  if noText countAll bounded
:countAll
  countIt: counted = wideToBytes(text, srcAt, forever, anywhere)
  return counted
:bounded
  boundIt: limitedCount = wideToBytes(text, srcAt, most, srcCell)
  return limitedCount

## ---------------------------------------------------------------- uchar.h

op mbrtoc16 "mbrtoc16: the char16_t of one multibyte character (its byte value), with the bytes it took (0 for NUL, -2 when none of n is there)"
  input wide machine.Address copied
  input text machine.Address copied
  input bytes Int64 copied
  input state machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "mbrtoc16"
:begin
  decodeIt: value = decodeLead(text, bytes)
  incompleteCheck: incomplete = compare.lessThanInt64(value, lit122=0)
  if incomplete waiting storeIt
:storeIt
  putIt: putByteIf(wide, lit123=0, value)
  putHigh: putByteIf(wide, lit124=1, lit125=0)
  lengthIt: length = lengthOfLead(value)
  return length
:waiting
  return value

op mbrtoc32 "mbrtoc32: the char32_t of one multibyte character (its byte value), with the bytes it took (0 for NUL, -2 when none of n is there)"
  input wide machine.Address copied
  input text machine.Address copied
  input bytes Int64 copied
  input state machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "mbrtoc32"
:begin
  decodeIt: value = decodeLead(text, bytes)
  incompleteCheck: incomplete = compare.lessThanInt64(value, lit126=0)
  if incomplete waiting storeIt
:storeIt
  narrowIt: wideValue = convert.int64ToInt32(value)
  putIt: putUnitIf(wide, lit127=0, wideValue)
  lengthIt: length = lengthOfLead(value)
  return length
:waiting
  return value

op c16rtomb "c16rtomb: the byte of a char16_t (its low 16 bits) written at s, 1, or -1 with EILSEQ above 127"
  input text machine.Address copied
  input char16 Int32 copied
  input state machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "c16rtomb"
:begin
  widenIt: value = convert.int32ToInt64(char16)
  lowIt: low = bits.andInt64(value, lit128=65535)
  encodeIt: result = encodeOne(text, low)
  return result

op c32rtomb "c32rtomb: the byte of a char32_t written at s, 1, or -1 with EILSEQ above 127"
  input text machine.Address copied
  input char32 Int32 copied
  input state machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  abi library "c32rtomb"
:begin
  widenIt: value = convert.int32ToInt64(char32)
  encodeIt: result = encodeOne(text, value)
  return result

op wcstolC23 "__isoc23_wcstol: cstol as C23 reads it, `0b` binary included (D-173)"
  input text machine.Address copied
  input endAt machine.Address copied
  input base Int32 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc23_wcstol"
:begin
  value = parseWide(text, endAt, base, false, true)
  return value

op wcstollC23 "__isoc23_wcstoll: cstoll as C23 reads it, `0b` binary included (D-173)"
  input text machine.Address copied
  input endAt machine.Address copied
  input base Int32 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc23_wcstoll"
:begin
  value = parseWide(text, endAt, base, false, true)
  return value

op wcstoulC23 "__isoc23_wcstoul: cstoul as C23 reads it, `0b` binary included (D-173)"
  input text machine.Address copied
  input endAt machine.Address copied
  input base Int32 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc23_wcstoul"
:begin
  value = parseWide(text, endAt, base, true, true)
  return value

op wcstoullC23 "__isoc23_wcstoull: cstoull as C23 reads it, `0b` binary included (D-173)"
  input text machine.Address copied
  input endAt machine.Address copied
  input base Int32 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "__isoc23_wcstoull"
:begin
  value = parseWide(text, endAt, base, true, true)
  return value

op readWhole "strtol's reading of bytes, as C17 reads them or (binary) as C23 does"
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

@tests

## Tests build their text in heap blocks (wide arrays of wchar_t, C strings of bytes), not in the scratch bytes
## machine.state keeps for this module. Expected values are glibc's in the C locale (tests/test_c_cwide.py compares
## the library with glibc itself on Linux).

op wideOf "A wchar_t array holding an ASCII String and a 0, with room for 32 more wchar_t, in a new heap block"
  input text String borrowed
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let at Int64 0 mut
:begin
  bytes = string.byteLength(text)
  calc size = (bytes + 33) * 4
  block = heap.take(size)
  source = machine.addressOfString(text)
  goto eachByte
:eachByte loop=while max=9223372036854775807
  when at >= bytes finish store
:store in=eachByte
  value = byteValueAt(source, at)
  unit = convert.int64ToInt32(value)
  putUnit(block, at, unit)
  calc at := at + 1
  goto eachByte
:finish
  return block

op textOf "A C string holding a String, with room for 32 more bytes, in a new heap block"
  input text String borrowed
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  bytes = string.byteLength(text)
  calc size = bytes + 33
  block = heap.take(size)
  source = machine.addressOfString(text)
  machine.copy(block, source, bytes)
  return block

op wideIs "Whether a wchar_t array holds exactly an ASCII String and then a 0"
  input array machine.Address copied
  input text String borrowed
  output Bool
  effect use machine.memory
  uses memoryAccess
  let at Int64 0 mut
:begin
  bytes = string.byteLength(text)
  source = machine.addressOfString(text)
  goto eachByte
:eachByte loop=while max=9223372036854775807
  when at >= bytes endCheck compareUnit
:compareUnit in=eachByte
  want = byteValueAt(source, at)
  have = unitAt(array, at)
  haveWide = convert.int32ToInt64(have)
  when want == haveWide advance differs
:advance in=eachByte
  calc at := at + 1
  goto eachByte
:endCheck
  last = unitAt(array, bytes)
  calc answer = last == 0
  return answer
:differs
  return false

op classResult "The result of the isw function numbered 0 to 11 (alnum, alpha, blank, cntrl, digit, graph, lower, print, punct, space, upper, xdigit) for a code"
  input kind Int32 copied
  input code Int32 copied
  output Int32
:begin
  when kind == 0 caseAlnum try1
:caseAlnum
  r0 = iswalnum(code)
  return r0
:try1
  when kind == 1 caseAlpha try2
:caseAlpha
  r1 = iswalpha(code)
  return r1
:try2
  when kind == 2 caseBlank try3
:caseBlank
  r2 = iswblank(code)
  return r2
:try3
  when kind == 3 caseCntrl try4
:caseCntrl
  r3 = iswcntrl(code)
  return r3
:try4
  when kind == 4 caseDigit try5
:caseDigit
  r4 = iswdigit(code)
  return r4
:try5
  when kind == 5 caseGraph try6
:caseGraph
  r5 = iswgraph(code)
  return r5
:try6
  when kind == 6 caseLower try7
:caseLower
  r6 = iswlower(code)
  return r6
:try7
  when kind == 7 casePrint try8
:casePrint
  r7 = iswprint(code)
  return r7
:try8
  when kind == 8 casePunct try9
:casePunct
  r8 = iswpunct(code)
  return r8
:try9
  when kind == 9 caseSpace try10
:caseSpace
  r9 = iswspace(code)
  return r9
:try10
  when kind == 10 caseUpper caseXdigit
:caseUpper
  r10 = iswupper(code)
  return r10
:caseXdigit
  r11 = iswxdigit(code)
  return r11

op classSummary "How many codes from -1 to 300 an isw function is nonzero for, times 100000, plus their sum"
  input kind Int32 copied
  output Int64
  let code Int32 -1 mut
  let count Int64 0 mut
  let total Int64 0 mut
:begin
  goto eachCode
:eachCode loop=while max=1000
  when code > 300 finish test
:test in=eachCode
  result = classResult(kind, code)
  when result != 0 member advance
:member in=eachCode
  wideCode = convert.int32ToInt64(code)
  calc count := count + 1
  calc total := total + wideCode
  goto advance
:advance in=eachCode
  calc code := code + 1
  goto eachCode
:finish
  calc packed = count * 100000 + total
  return packed

op handleSummary "How many codes from -1 to 300 iswctype is nonzero for with a handle, times 100000, plus their sum"
  input handle Int64 copied
  output Int64
  let code Int32 -1 mut
  let count Int64 0 mut
  let total Int64 0 mut
:begin
  goto eachCode
:eachCode loop=while max=1000
  when code > 300 finish test
:test in=eachCode
  result = iswctype(code, handle)
  when result != 0 member advance
:member in=eachCode
  wideCode = convert.int32ToInt64(code)
  calc count := count + 1
  calc total := total + wideCode
  goto advance
:advance in=eachCode
  calc code := code + 1
  goto eachCode
:finish
  calc packed = count * 100000 + total
  return packed

op currentErrno "The value errno holds now"
  output Int32
  effect use machine.memory
  uses memoryAccess
:begin
  cell = clibrary.errnoCell()
  value = machine.loadInt32(cell)
  return value

op longCase "wcstol (or wcstoul) of an ASCII String in a base: the value, the units it read, and errno as expected"
  input text String borrowed
  input base Int32 copied
  input unsigned Bool copied
  input expected Int64 copied
  input expectedEnd Int64 copied
  input expectedErrno Int32 copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let value Int64 0 mut
:begin
  array = wideOf(text)
  cell = heap.take(8)
  clibrary.setErrno(0)
  when unsigned unsignedParse signedParse
:signedParse
  signedValue = wcstol(array, cell, base)
  calc value := signedValue
  goto finish
:unsignedParse
  unsignedValue = wcstoul(array, cell, base)
  calc value := unsignedValue
  goto finish
:finish
  end = machine.loadAddress(cell)
  read = machine.difference(end, array)
  errno = currentErrno()
  calc answer = value == expected && read == expectedEnd * 4 && errno == expectedErrno
  return answer

op realCase "wcstod of an ASCII String: the bits of the double, and the units it read"
  input text String borrowed
  input expectedBits UInt64 copied
  input expectedEnd Int64 copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  array = wideOf(text)
  cell = heap.take(8)
  value = wcstod(array, cell)
  bits = convert.float64BitsToUInt64(value)
  end = machine.loadAddress(cell)
  read = machine.difference(end, array)
  calc answer = bits == expectedBits && read == expectedEnd * 4
  return answer

op floatCase "wcstof of an ASCII String: the bits of the float read as a double, the units it read, and errno as expected"
  input text String borrowed
  input expectedBits UInt64 copied
  input expectedEnd Int64 copied
  input expectedErrno Int32 copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  array = wideOf(text)
  cell = heap.take(8)
  clibrary.setErrno(0)
  value = wcstof(array, cell)
  wide = convert.float32ToFloat64(value)
  bits = convert.float64BitsToUInt64(wide)
  end = machine.loadAddress(cell)
  read = machine.difference(end, array)
  errno = currentErrno()
  calc answer = bits == expectedBits && read == expectedEnd * 4 && errno == expectedErrno
  return answer

test classTest "Each isw function is nonzero for exactly the C locale's members of its class, whatever the code (negative and above 255 included), and iswctype with wctype's handle agrees"
  verifies iswalpha alphaIsAscii
  verifies iswctype handlesAgree
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  alnum = classSummary(0)
  test.assertEqualInt64(6205387, alnum)
  alpha = classSummary(1)
  test.assertEqualInt64(5204862, alpha)
  blank = classSummary(2)
  test.assertEqualInt64(200041, blank)
  cntrl = classSummary(3)
  test.assertEqualInt64(3300623, cntrl)
  digit = classSummary(4)
  test.assertEqualInt64(1000525, digit)
  graph = classSummary(5)
  test.assertEqualInt64(9407473, graph)
  lower = classSummary(6)
  test.assertEqualInt64(2602847, lower)
  printable = classSummary(7)
  test.assertEqualInt64(9507505, printable)
  punct = classSummary(8)
  test.assertEqualInt64(3202086, punct)
  space = classSummary(9)
  test.assertEqualInt64(600087, space)
  upper = classSummary(10)
  test.assertEqualInt64(2602015, upper)
  xdigit = classSummary(11)
  test.assertEqualInt64(2201527, xdigit)
  alphaBits = iswalpha(113)
  test.assertTrue(alphaBits == 1024)
  digitBits = iswdigit(55)
  test.assertTrue(digitBits == 2048)
  euro = iswalpha(8364)
  test.assertTrue(euro == 0)
  highest = iswprint(1114111)
  test.assertTrue(highest == 0)
  negative = iswspace(-5)
  test.assertTrue(negative == 0)
  alnumName = textOf("alnum")
  alnumHandle = wctype(alnumName)
  alnumViaHandle = handleSummary(alnumHandle)
  test.assertEqualInt64(6205387, alnumViaHandle)
  xdigitName = textOf("xdigit")
  xdigitHandle = wctype(xdigitName)
  xdigitViaHandle = handleSummary(xdigitHandle)
  test.assertEqualInt64(2201527, xdigitViaHandle)
  punctName = textOf("punct")
  punctHandle = wctype(punctName)
  punctViaHandle = handleSummary(punctHandle)
  test.assertEqualInt64(3202086, punctViaHandle)
  unknownName = textOf("unknown")
  unknownHandle = wctype(unknownName)
  test.assertEqualInt64(0, unknownHandle)
  emptyName = textOf("")
  emptyHandle = wctype(emptyName)
  test.assertEqualInt64(0, emptyHandle)
  prefixName = textOf("alnu")
  prefixHandle = wctype(prefixName)
  test.assertEqualInt64(0, prefixHandle)
  longName = textOf("alnumx")
  longHandle = wctype(longName)
  test.assertEqualInt64(0, longHandle)
  noClass = iswctype(65, unknownHandle)
  test.assertTrue(noClass == 0)
  return

test caseTest "towupper and towlower change the ASCII letters and nothing else, and wctrans with towctrans does the same by name"
  verifies towupper raisesAscii
  verifies towlower lowersAscii
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  up = towupper(97)
  test.assertTrue(up == 65)
  upEnd = towupper(122)
  test.assertTrue(upEnd == 90)
  upBefore = towupper(96)
  test.assertTrue(upBefore == 96)
  upAfter = towupper(123)
  test.assertTrue(upAfter == 123)
  upKept = towupper(65)
  test.assertTrue(upKept == 65)
  upLatin = towupper(233)
  test.assertTrue(upLatin == 233)
  upWide = towupper(8364)
  test.assertTrue(upWide == 8364)
  upNegative = towupper(-1)
  test.assertTrue(upNegative == -1)
  down = towlower(65)
  test.assertTrue(down == 97)
  downEnd = towlower(90)
  test.assertTrue(downEnd == 122)
  downBefore = towlower(64)
  test.assertTrue(downBefore == 64)
  downAfter = towlower(91)
  test.assertTrue(downAfter == 91)
  downLatin = towlower(201)
  test.assertTrue(downLatin == 201)
  downWide = towlower(1114111)
  test.assertTrue(downWide == 1114111)
  lowerName = textOf("tolower")
  lowerHandle = wctrans(lowerName)
  test.assertTrue(lowerHandle != 0)
  upperName = textOf("toupper")
  upperHandle = wctrans(upperName)
  test.assertTrue(upperHandle != 0)
  test.assertTrue(upperHandle != lowerHandle)
  otherName = textOf("tocase")
  otherHandle = wctrans(otherName)
  test.assertEqualInt64(0, otherHandle)
  emptyName = textOf("")
  emptyHandle = wctrans(emptyName)
  test.assertEqualInt64(0, emptyHandle)
  viaLower = towctrans(81, lowerHandle)
  test.assertTrue(viaLower == 113)
  viaUpper = towctrans(113, upperHandle)
  test.assertTrue(viaUpper == 81)
  viaLowerKept = towctrans(49, lowerHandle)
  test.assertTrue(viaLowerKept == 49)
  return

test lengthTest "wcslen and wcsnlen count to the 0, wcscpy, wcsncpy, wcscat, wcsncat, wcsdup, and the wmem functions copy, pad, and move as glibc's do"
  verifies wcscpy copiesWide
  verifies wcsncpy padsWithZeros
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  hello = wideOf("hello")
  length = wcslen(hello)
  test.assertEqualInt64(5, length)
  bounded = wcsnlen(hello, 3)
  test.assertEqualInt64(3, bounded)
  whole = wcsnlen(hello, 10)
  test.assertEqualInt64(5, whole)
  empty = wideOf("")
  emptyLength = wcslen(empty)
  test.assertEqualInt64(0, emptyLength)
  target = wideOf("")
  copied = wcscpy(target, hello)
  test.assertTrue(copied == target)
  check1 = wideIs(target, "hello")
  test.assertTrue(check1)
  part1 = wideOf(", world")
  joined = wcscat(target, part1)
  test.assertTrue(joined == target)
  check2 = wideIs(target, "hello, world")
  test.assertTrue(check2)
  jointLength = wcslen(target)
  test.assertEqualInt64(12, jointLength)
  padded = wideOf("")
  wmemset(padded, 120, 10)
  part2 = wideOf("abc")
  wcsncpy(padded, part2, 6)
  c0 = unitAt(padded, 2)
  test.assertTrue(c0 == 99)
  c1 = unitAt(padded, 3)
  test.assertTrue(c1 == 0)
  c2 = unitAt(padded, 5)
  test.assertTrue(c2 == 0)
  c3 = unitAt(padded, 6)
  test.assertTrue(c3 == 120)
  cut = wideOf("")
  wmemset(cut, 120, 10)
  part3 = wideOf("abcdef")
  wcsncpy(cut, part3, 3)
  d0 = unitAt(cut, 2)
  test.assertTrue(d0 == 99)
  d1 = unitAt(cut, 3)
  test.assertTrue(d1 == 120)
  tail = wideOf("ab")
  part4 = scaledPlace(tail, 6)
  wmemset(part4, 121, 10)
  part5 = wideOf("cdefg")
  wcsncat(tail, part5, 3)
  check3 = wideIs(tail, "abcde")
  test.assertTrue(check3)
  tailAfter = unitAt(tail, 6)
  test.assertTrue(tailAfter == 121)
  short = wideOf("x")
  part6 = wideOf("yz")
  wcsncat(short, part6, 9)
  check4 = wideIs(short, "xyz")
  test.assertTrue(check4)
  duplicate = wcsdup(hello)
  test.assertTrue(duplicate != hello)
  check5 = wideIs(duplicate, "hello")
  test.assertTrue(check5)
  copyTarget = wideOf("")
  wmemcpy(copyTarget, hello, 3)
  check6 = wideIs(copyTarget, "hel")
  test.assertTrue(check6)
  overlap = wideOf("abcdef")
  part7 = scaledPlace(overlap, 1)
  wmemmove(part7, overlap, 5)
  check7 = wideIs(overlap, "aabcde")
  test.assertTrue(check7)
  backward = wideOf("abcdef")
  part8 = scaledPlace(backward, 2)
  wmemmove(backward, part8, 4)
  check8 = wideIs(backward, "cdefef")
  test.assertTrue(check8)
  filled = wideOf("")
  wmemset(filled, 65, 4)
  check9 = wideIs(filled, "AAAA")
  test.assertTrue(check9)
  return

test compareTest "wcscmp, wcsncmp, wcscoll, and wmemcmp give -1, 0, or 1 by the first differing wchar_t, and wcsxfrm keeps the text"
  verifies wcscmp ordersBySign
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  part9 = wideOf("abc")
  part10 = wideOf("abd")
  below = wcscmp(part9, part10)
  test.assertTrue(below == -1)
  part11 = wideOf("abd")
  part12 = wideOf("abc")
  above = wcscmp(part11, part12)
  test.assertTrue(above == 1)
  part13 = wideOf("abc")
  part14 = wideOf("abc")
  same = wcscmp(part13, part14)
  test.assertTrue(same == 0)
  part15 = wideOf("ab")
  part16 = wideOf("abc")
  prefix = wcscmp(part15, part16)
  test.assertTrue(prefix == -1)
  part17 = wideOf("abc")
  part18 = wideOf("ab")
  longer = wcscmp(part17, part18)
  test.assertTrue(longer == 1)
  big = wideOf("a")
  putUnit(big, 0, 256)
  small = wideOf("a")
  putUnit(small, 0, 255)
  bigger = wcscmp(big, small)
  test.assertTrue(bigger == 1)
  part19 = wideOf("abcX")
  part20 = wideOf("abcY")
  limited = wcsncmp(part19, part20, 3)
  test.assertTrue(limited == 0)
  part21 = wideOf("abcX")
  part22 = wideOf("abcY")
  differing = wcsncmp(part21, part22, 4)
  test.assertTrue(differing == -1)
  part23 = wideOf("a")
  part24 = wideOf("b")
  nothing = wcsncmp(part23, part24, 0)
  test.assertTrue(nothing == 0)
  part25 = wideOf("b")
  part26 = wideOf("a")
  collated = wcscoll(part25, part26)
  test.assertTrue(collated == 1)
  part27 = wideOf("abc")
  part28 = wideOf("abd")
  memBelow = wmemcmp(part27, part28, 3)
  test.assertTrue(memBelow == -1)
  part29 = wideOf("abc")
  part30 = wideOf("abd")
  memSame = wmemcmp(part29, part30, 2)
  test.assertTrue(memSame == 0)
  zeroInside = wideOf("ab")
  zeroOther = wideOf("ab")
  putUnit(zeroOther, 3, 7)
  memZero = wmemcmp(zeroInside, zeroOther, 4)
  test.assertTrue(memZero == -1)
  roomy = wideOf("")
  wmemset(roomy, 120, 10)
  part31 = wideOf("hello")
  transformed = wcsxfrm(roomy, part31, 10)
  test.assertEqualInt64(5, transformed)
  check10 = wideIs(roomy, "hello")
  test.assertTrue(check10)
  squeezed = wideOf("")
  wmemset(squeezed, 120, 10)
  part32 = wideOf("hello")
  squeezedLength = wcsxfrm(squeezed, part32, 3)
  test.assertEqualInt64(5, squeezedLength)
  s0 = unitAt(squeezed, 2)
  test.assertTrue(s0 == 108)
  s1 = unitAt(squeezed, 3)
  test.assertTrue(s1 == 120)
  nowhere = machine.zero()
  part33 = wideOf("hello")
  counted = wcsxfrm(nowhere, part33, 0)
  test.assertEqualInt64(5, counted)
  return

test searchTest "wcschr, wcsrchr, wcsstr, wcspbrk, wcsspn, wcscspn, and wmemchr find what glibc's do, the 0 included, and the address 0 when nothing is there"
  verifies wcschr findsUnit
  verifies wcsstr findsWideText
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  hello = wideOf("hello")
  nowhere = machine.zero()
  first = wcschr(hello, 108)
  calc firstWant = hello + 8
  test.assertTrue(first == firstWant)
  last = wcsrchr(hello, 108)
  calc lastWant = hello + 12
  test.assertTrue(last == lastWant)
  endFind = wcschr(hello, 0)
  calc endWant = hello + 20
  test.assertTrue(endFind == endWant)
  endLast = wcsrchr(hello, 0)
  test.assertTrue(endLast == endWant)
  missing = wcschr(hello, 122)
  test.assertTrue(missing == nowhere)
  missingLast = wcsrchr(hello, 122)
  test.assertTrue(missingLast == nowhere)
  wideValue = wideOf("a")
  putUnit(wideValue, 1, 8364)
  wideFound = wcschr(wideValue, 8364)
  calc wideWant = wideValue + 4
  test.assertTrue(wideFound == wideWant)
  world = wideOf("hello world")
  part34 = wideOf("o w")
  inside = wcsstr(world, part34)
  calc insideWant = world + 16
  test.assertTrue(inside == insideWant)
  part35 = wideOf("")
  emptyNeedle = wcsstr(world, part35)
  test.assertTrue(emptyNeedle == world)
  part36 = wideOf("xyz")
  absentNeedle = wcsstr(world, part36)
  test.assertTrue(absentNeedle == nowhere)
  part37 = wideOf("ab")
  part38 = wideOf("abc")
  tooLong = wcsstr(part37, part38)
  test.assertTrue(tooLong == nowhere)
  part39 = wideOf("aab")
  part40 = wideOf("ab")
  restart = wcsstr(part39, part40)
  test.assertTrue(restart != nowhere)
  part41 = wideOf("ld")
  atEnd = wcsstr(world, part41)
  calc atEndWant = world + 36
  test.assertTrue(atEnd == atEndWant)
  part42 = wideOf("abcde")
  part43 = wideOf("cba")
  span = wcsspn(part42, part43)
  test.assertEqualInt64(3, span)
  part44 = wideOf("abc")
  part45 = wideOf("")
  spanNothing = wcsspn(part44, part45)
  test.assertEqualInt64(0, spanNothing)
  part46 = wideOf("abc")
  part47 = wideOf("cba")
  spanAll = wcsspn(part46, part47)
  test.assertEqualInt64(3, spanAll)
  part48 = wideOf("xl")
  cspan = wcscspn(hello, part48)
  test.assertEqualInt64(2, cspan)
  part49 = wideOf("xyz")
  cspanAll = wcscspn(hello, part49)
  test.assertEqualInt64(5, cspanAll)
  part50 = wideOf("")
  cspanEmpty = wcscspn(hello, part50)
  test.assertEqualInt64(5, cspanEmpty)
  part51 = wideOf("ol")
  brk = wcspbrk(hello, part51)
  calc brkWant = hello + 8
  test.assertTrue(brk == brkWant)
  part52 = wideOf("xyz")
  brkNone = wcspbrk(hello, part52)
  test.assertTrue(brkNone == nowhere)
  memFound = wmemchr(hello, 108, 5)
  test.assertTrue(memFound == firstWant)
  memShort = wmemchr(hello, 108, 2)
  test.assertTrue(memShort == nowhere)
  memZero = wmemchr(hello, 0, 6)
  test.assertTrue(memZero == endWant)
  return

test tokenTest "wcstok skips leading delimiters, cuts at the next one, keeps its place in the cell it is given, and gives the address 0 when no token is left"
  verifies wcstok cutsTokens
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere = machine.zero()
  delimiters = wideOf(",;")
  save = heap.take(8)
  text = wideOf(",,a,b;;cc,,")
  one = wcstok(text, delimiters, save)
  calc oneWant = text + 8
  test.assertTrue(one == oneWant)
  check11 = wideIs(one, "a")
  test.assertTrue(check11)
  two = wcstok(nowhere, delimiters, save)
  calc twoWant = text + 16
  test.assertTrue(two == twoWant)
  check12 = wideIs(two, "b")
  test.assertTrue(check12)
  three = wcstok(nowhere, delimiters, save)
  calc threeWant = text + 28
  test.assertTrue(three == threeWant)
  check13 = wideIs(three, "cc")
  test.assertTrue(check13)
  four = wcstok(nowhere, delimiters, save)
  test.assertTrue(four == nowhere)
  again = wcstok(nowhere, delimiters, save)
  test.assertTrue(again == nowhere)
  onlyDelimiters = wideOf(",;,")
  noToken = wcstok(onlyDelimiters, delimiters, save)
  test.assertTrue(noToken == nowhere)
  emptyText = wideOf("")
  nothing = wcstok(emptyText, delimiters, save)
  test.assertTrue(nothing == nowhere)
  plain = wideOf("word")
  whole = wcstok(plain, delimiters, save)
  test.assertTrue(whole == plain)
  check14 = wideIs(whole, "word")
  test.assertTrue(check14)
  rest = wcstok(nowhere, delimiters, save)
  test.assertTrue(rest == nowhere)
  return

test integerTest "wcstol, wcstoll, wcstoul, and wcstoull read glibc's prefixes, bases, ends, and limits from wide text, and stop at a wide character that is not ASCII"
  verifies wcstol readsWideNumber
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  spaced = longCase("  -42xyz", 10, false, -42, 5, 0)
  test.assertTrue(spaced)
  hexPrefix = longCase("0x1F", 16, false, 31, 4, 0)
  test.assertTrue(hexPrefix)
  autoHex = longCase("0x1F", 0, false, 31, 4, 0)
  test.assertTrue(autoHex)
  autoOctal = longCase("017", 0, false, 15, 3, 0)
  test.assertTrue(autoOctal)
  noDigits = longCase("abc", 10, false, 0, 0, 0)
  test.assertTrue(noDigits)
  hexNoDigits = longCase("0xg", 16, false, 0, 1, 0)
  test.assertTrue(hexNoDigits)
  plus = longCase("+7", 10, false, 7, 2, 0)
  test.assertTrue(plus)
  tooBig = longCase("99999999999999999999", 10, false, 9223372036854775807, 20, 34)
  test.assertTrue(tooBig)
  tooSmall = longCase("-99999999999999999999", 10, false, -9223372036854775808, 21, 34)
  test.assertTrue(tooSmall)
  lowest = longCase("-9223372036854775808", 10, false, -9223372036854775808, 20, 0)
  test.assertTrue(lowest)
  base36 = longCase("zz", 36, false, 1295, 2, 0)
  test.assertTrue(base36)
  unsignedNegative = longCase("-1", 10, true, -1, 2, 0)
  test.assertTrue(unsignedNegative)
  unsignedBig = longCase("18446744073709551615", 10, true, -1, 20, 0)
  test.assertTrue(unsignedBig)
  unsignedOver = longCase("18446744073709551616", 10, true, -1, 20, 34)
  test.assertTrue(unsignedOver)
  array = wideOf("12")
  putUnit(array, 2, 8364)
  putUnit(array, 3, 51)
  putUnit(array, 4, 0)
  cell = heap.take(8)
  stopped = wcstoll(array, cell, 10)
  test.assertEqualInt64(12, stopped)
  stopEnd = machine.loadAddress(cell)
  stopRead = machine.difference(stopEnd, array)
  test.assertEqualInt64(8, stopRead)
  fullwidth = wideOf("")
  putUnit(fullwidth, 0, 65297)
  putUnit(fullwidth, 1, 0)
  fullValue = wcstoull(fullwidth, cell, 10)
  test.assertEqualInt64(0, fullValue)
  fullEnd = machine.loadAddress(cell)
  test.assertTrue(fullEnd == fullwidth)
  nowhere = machine.zero()
  part53 = wideOf("77")
  noCell = wcstol(part53, nowhere, 10)
  test.assertEqualInt64(77, noCell)
  return

test realTest "wcstod reads decimal, hexadecimal, infinity, and NaN text as strtod does, with its ends; wcstof rounds the text itself once to a float, not the double it rounds to"
  verifies wcstof roundsOnce
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere = machine.zero()
  twoText = wideOf("2.5")
  direct = wcstof(twoText, nowhere)
  directWide = convert.float32ToFloat64(direct)
  directBits = convert.float64BitsToUInt64(directWide)
  directInt = convert.uint64ToInt64(directBits)
  test.assertEqualInt64(4612811918334230528, directInt)
  plain = realCase("3.25e2xyz", 4644425076656046080, 6)
  test.assertTrue(plain)
  negative = realCase("  -0.5", 13826050856027422720, 6)
  test.assertTrue(negative)
  leadingPoint = realCase(".5", 4602678819172646912, 2)
  test.assertTrue(leadingPoint)
  hexValue = realCase("0x1p-2", 4598175219545276416, 6)
  test.assertTrue(hexValue)
  infinite = realCase("inf", 9218868437227405312, 3)
  test.assertTrue(infinite)
  noNumber = realCase("xyz", 0, 0)
  test.assertTrue(noNumber)
  overflow = realCase("1e400", 9218868437227405312, 5)
  test.assertTrue(overflow)
  tenth = floatCase("0.1", 4591870180174331904, 3, 0)
  test.assertTrue(tenth)
  rounded = floatCase("16777217", 4715268809856909312, 8, 0)
  test.assertTrue(rounded)
  tie = floatCase("1.000000059604644775390625", 4607182418800017408, 26, 0)
  test.assertTrue(tie)
  above = floatCase("1.00000005960464477539062500000001", 4607182419336888320, 34, 0)
  test.assertTrue(above)
  below = floatCase("1.00000005960464477539062499999999", 4607182418800017408, 34, 0)
  test.assertTrue(below)
  hexAbove = floatCase("0x1.00000100000000000000000001p0", 4607182419336888320, 32, 0)
  test.assertTrue(hexAbove)
  hexNegative = floatCase("-0x1.8p1", 13837309855095848960, 8, 0)
  test.assertTrue(hexNegative)
  floatOverflow = floatCase("1e39", 9218868437227405312, 4, 34)
  test.assertTrue(floatOverflow)
  floatTiny = floatCase("1e-45", 3936146074321813504, 5, 34)
  test.assertTrue(floatTiny)
  return

test multibyteTest "The C locale's multibyte functions map one byte to one wide character and back, report -2 for no input and EILSEQ past 127 either way, and have no state"
  verifies mbrtowc readsOneByte
  verifies wcrtomb writesOneByte
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere = machine.zero()
  state = heap.take(8)
  initial = mbsinit(state)
  test.assertTrue(initial != 0)
  initialNull = mbsinit(nowhere)
  test.assertTrue(initialNull != 0)
  letter = textOf("A")
  lenLetter = mbrlen(letter, 1, state)
  test.assertEqualInt64(1, lenLetter)
  part54 = textOf("")
  lenNul = mbrlen(part54, 1, state)
  test.assertEqualInt64(0, lenNul)
  lenNone = mbrlen(letter, 0, state)
  test.assertEqualInt64(-2, lenNone)
  cell = heap.take(8)
  got = mbrtowc(cell, letter, 1, state)
  test.assertEqualInt64(1, got)
  gotWide = machine.loadInt32(cell)
  test.assertTrue(gotWide == 65)
  part55 = textOf("")
  gotNul = mbrtowc(cell, part55, 1, state)
  test.assertEqualInt64(0, gotNul)
  gotNulWide = machine.loadInt32(cell)
  test.assertTrue(gotNulWide == 0)
  gotNone = mbrtowc(cell, letter, 0, state)
  test.assertEqualInt64(-2, gotNone)
  gotNoCell = mbrtowc(nowhere, letter, 1, state)
  test.assertEqualInt64(1, gotNoCell)
  highText = textOf("")
  putByteAt(highText, 0, 233)
  clibrary.setErrno(0)
  gotHigh = mbrtowc(cell, highText, 1, state)
  test.assertEqualInt64(-1, gotHigh)
  highErrno = currentErrno()
  test.assertTrue(highErrno == 84)
  buffer = textOf("")
  made = wcrtomb(buffer, 66, state)
  test.assertEqualInt64(1, made)
  madeByte = byteValueAt(buffer, 0)
  test.assertEqualInt64(66, madeByte)
  clibrary.setErrno(0)
  refused = wcrtomb(buffer, 8364, state)
  test.assertEqualInt64(-1, refused)
  refusedErrno = currentErrno()
  test.assertTrue(refusedErrno == 84)
  madeNull = wcrtomb(nowhere, 8364, state)
  test.assertEqualInt64(1, madeNull)
  madeHigh = wcrtomb(buffer, 233, state)
  test.assertEqualInt64(-1, madeHigh)
  madeAscii = wcrtomb(buffer, 127, state)
  test.assertEqualInt64(1, madeAscii)
  lengthOne = mblen(letter, 1)
  test.assertTrue(lengthOne == 1)
  part56 = textOf("")
  lengthNul = mblen(part56, 1)
  test.assertTrue(lengthNul == 0)
  lengthNull = mblen(nowhere, 1)
  test.assertTrue(lengthNull == 0)
  lengthNone = mblen(letter, 0)
  test.assertTrue(lengthNone == -1)
  toWide = mbtowc(cell, letter, 1)
  test.assertTrue(toWide == 1)
  toWideValue = machine.loadInt32(cell)
  test.assertTrue(toWideValue == 65)
  toWideNull = mbtowc(cell, nowhere, 1)
  test.assertTrue(toWideNull == 0)
  toByte = wctomb(buffer, 67)
  test.assertTrue(toByte == 1)
  toByteNull = wctomb(nowhere, 67)
  test.assertTrue(toByteNull == 0)
  toByteBad = wctomb(buffer, 300)
  test.assertTrue(toByteBad == -1)
  wideOfByte = btowc(65)
  test.assertTrue(wideOfByte == 65)
  wideOfEof = btowc(-1)
  test.assertTrue(wideOfEof == -1)
  wideOfBig = btowc(300)
  test.assertTrue(wideOfBig == -1)
  wideOfHigh = btowc(233)
  test.assertTrue(wideOfHigh == -1)
  byteOfWide = wctob(65)
  test.assertTrue(byteOfWide == 65)
  byteOfEof = wctob(-1)
  test.assertTrue(byteOfEof == -1)
  byteOfBig = wctob(300)
  test.assertTrue(byteOfBig == -1)
  byteOfHigh = wctob(233)
  test.assertTrue(byteOfHigh == -1)
  return

test stringConversionTest "mbstowcs, wcstombs, mbsrtowcs, and wcsrtombs convert whole strings and as many as fit, count with no target, and stop at a wide character above 127; uchar.h's functions give the same as wchar.h's"
  verifies mbstowcs convertsToWide
  verifies wcstombs convertsToBytes
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  nowhere = machine.zero()
  state = heap.take(8)
  hello = textOf("hello")
  target = wideOf("")
  wmemset(target, 120, 12)
  converted = mbstowcs(target, hello, 10)
  test.assertEqualInt64(5, converted)
  check15 = wideIs(target, "hello")
  test.assertTrue(check15)
  counted = mbstowcs(nowhere, hello, 0)
  test.assertEqualInt64(5, counted)
  limited = wideOf("")
  wmemset(limited, 120, 12)
  limitedCount = mbstowcs(limited, hello, 3)
  test.assertEqualInt64(3, limitedCount)
  limitedAfter = unitAt(limited, 3)
  test.assertTrue(limitedAfter == 120)
  exact = wideOf("")
  wmemset(exact, 120, 12)
  exactCount = mbstowcs(exact, hello, 5)
  test.assertEqualInt64(5, exactCount)
  exactAfter = unitAt(exact, 5)
  test.assertTrue(exactAfter == 120)
  bytes = textOf("")
  part57 = wideOf("hello")
  made = wcstombs(bytes, part57, 10)
  test.assertEqualInt64(5, made)
  check16 = nameIs(bytes, "hello")
  test.assertTrue(check16)
  part58 = wideOf("hello")
  madeCounted = wcstombs(nowhere, part58, 0)
  test.assertEqualInt64(5, madeCounted)
  part59 = wideOf("abcdefg")
  madeLimited = wcstombs(bytes, part59, 3)
  test.assertEqualInt64(3, madeLimited)
  clibrary.setErrno(0)
  euro = wideOf("ab")
  putUnit(euro, 2, 8364)
  refused = wcstombs(bytes, euro, 10)
  test.assertEqualInt64(-1, refused)
  refusedErrno = currentErrno()
  test.assertTrue(refusedErrno == 84)
  refusedCounted = wcstombs(nowhere, euro, 0)
  test.assertEqualInt64(-1, refusedCounted)
  cursor = heap.take(8)
  machine.storeAddress(cursor, hello)
  restart = wideOf("")
  wmemset(restart, 120, 12)
  partial = mbsrtowcs(restart, cursor, 3, state)
  test.assertEqualInt64(3, partial)
  partialAt = machine.loadAddress(cursor)
  calc partialWant = hello + 3
  test.assertTrue(partialAt == partialWant)
  rest = mbsrtowcs(restart, cursor, 10, state)
  test.assertEqualInt64(2, rest)
  restAt = machine.loadAddress(cursor)
  test.assertTrue(restAt == nowhere)
  restUnit = unitAt(restart, 2)
  test.assertTrue(restUnit == 0)
  machine.storeAddress(cursor, hello)
  restCount = mbsrtowcs(nowhere, cursor, 0, state)
  test.assertEqualInt64(5, restCount)
  keptAt = machine.loadAddress(cursor)
  test.assertTrue(keptAt == hello)
  wides = wideOf("abcde")
  machine.storeAddress(cursor, wides)
  back = textOf("")
  backPart = wcsrtombs(back, cursor, 2, state)
  test.assertEqualInt64(2, backPart)
  backAt = machine.loadAddress(cursor)
  calc backWant = wides + 8
  test.assertTrue(backAt == backWant)
  backRest = wcsrtombs(back, cursor, 10, state)
  test.assertEqualInt64(3, backRest)
  check17 = nameIs(back, "cde")
  test.assertTrue(check17)
  backEnd = machine.loadAddress(cursor)
  test.assertTrue(backEnd == nowhere)
  machine.storeAddress(cursor, wides)
  backCount = wcsrtombs(nowhere, cursor, 0, state)
  test.assertEqualInt64(5, backCount)
  machine.storeAddress(cursor, euro)
  clibrary.setErrno(0)
  backRefused = wcsrtombs(back, cursor, 10, state)
  test.assertEqualInt64(-1, backRefused)
  backErrno = currentErrno()
  test.assertTrue(backErrno == 84)
  refusedAt = machine.loadAddress(cursor)
  calc refusedWant = euro + 8
  test.assertTrue(refusedAt == refusedWant)
  cell = heap.take(8)
  letter = textOf("Z")
  smallGot = mbrtoc16(cell, letter, 1, state)
  test.assertEqualInt64(1, smallGot)
  smallValue = machine.loadInt32(cell)
  test.assertTrue(smallValue == 90)
  wideGot = mbrtoc32(cell, letter, 1, state)
  test.assertEqualInt64(1, wideGot)
  wideValue = machine.loadInt32(cell)
  test.assertTrue(wideValue == 90)
  noneGot = mbrtoc32(cell, letter, 0, state)
  test.assertEqualInt64(-2, noneGot)
  smallMade = c16rtomb(back, 70, state)
  test.assertEqualInt64(1, smallMade)
  smallByte = byteValueAt(back, 0)
  test.assertEqualInt64(70, smallByte)
  wideMade = c32rtomb(back, 71, state)
  test.assertEqualInt64(1, wideMade)
  wideByte = byteValueAt(back, 0)
  test.assertEqualInt64(71, wideByte)
  wideRefused = c32rtomb(back, 8364, state)
  test.assertEqualInt64(-1, wideRefused)
  return
