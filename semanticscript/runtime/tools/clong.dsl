module clong "long double for the runtime's C library: the exact l-suffixed functions of math.h, done on the format's bits (D-174)"
  path clong
  imports standard.machine standard.system standard.math standard.compare standard.convert standard.bits standard.logic standard.test heap clibrary
  exports format unpack pack unpackAs packAs precisionOf settle settleAs partsNew roundingMode greatestPower lowBitsSet getPart setPart highOf lowOf setSignificand bitLength leastPower

capability memoryAccess "Authority to read and write long doubles in memory and the blocks their parts are kept in" use machine.memory none

capability systemCalls "Authority to take memory for a long double's parts" use system.calls none

## D-174: C's long double is x87's 80 bits on x86_64 Linux (64 bits of significand with its leading bit written out),
## IEEE binary128 on AArch64 Linux (113 bits, the leading one hidden), and a double on Windows (53). The functions here
## work on its parts: a heap block of 48 bytes, 0 the sign (0 or 1), 8 its kind (0 zero, 1 finite, 2 infinite, 3 NaN),
## 16 the power of two E, 24 and 32 the significand M's high and low 64 bits, the value being M * 2^E. A finite value
## packs when M is normalized (its top bit at P-1, P the precision) or subnormal (E the least there is and M below
## 2^(P-1)); `settle` rounds any M and E to that, as the rounding mode rounds. Nothing here does a long double's
## arithmetic, so each function is exact on every format.
constant forever "The bound of a loop that ends when its work does" Int64 9223372036854775807

constant topBit "The highest bit of a 64-bit word" UInt64 9223372036854775808

## ---------------------------------------------------------------- the rounding mode

op roundingMode "The rounding mode in force (fesetround's): 0 to nearest, 1 downward, 2 upward, 3 toward zero; from MXCSR's rounding bits on x86_64 and FPCR's RMode on AArch64 (where upward is 1 and downward 2)"
  invariant readsMode "Gives 0 until the rounding mode is changed"
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let nearest Int64 0
  let downward Int64 1
  let upward Int64 2
  let towardZero Int64 3
:begin
  control = machine.loadFloatControl()
  onArm = system.aarch64()
  if onArm arm intel
:intel
  calc intelMode = convert.uint64ToInt64((control >> 13) & 3)
  return intelMode
:arm
  calc armMode = (control >> 22) & 3
  when armMode == 0 giveNearest notNearest
:giveNearest
  return nearest
:notNearest
  when armMode == 1 giveUpward notUpward
:giveUpward
  return upward
:notUpward
  when armMode == 2 giveDownward giveZero
:giveDownward
  return downward
:giveZero
  return towardZero

## ---------------------------------------------------------------- the format

op format "The format of long double here: 0 a double (Windows), 1 x87's 80 bits (x86_64 Linux), 2 binary128 (AArch64 Linux)"
  invariant namesFormat "Gives the format this system's C ABI uses for long double"
  output Int64
  effect use system.calls
  uses systemCalls
  let double Int64 0
  let extended Int64 1
  let quad Int64 2
:begin
  onLinux = system.posix()
  if onLinux linux windows
:windows
  return double
:linux
  onArm = system.aarch64()
  if onArm arm intel
:arm
  return quad
:intel
  return extended

op precisionOf "The bits of a format's significand: 53 (0, double), 64 (1, x87), 113 (2, binary128), 24 (3, float)"
  invariant countsBits "Gives each format's significand bits"
  input kind Int64 copied
  output Int64
  let doubleBits Int64 53
  let extendedBits Int64 64
  let quadBits Int64 113
  let floatBits Int64 24
:begin
  when kind == 0 giveDouble notDouble
:giveDouble
  return doubleBits
:notDouble
  when kind == 3 giveFloat notFloat
:giveFloat
  return floatBits
:notFloat
  when kind == 1 giveExtended giveQuad
:giveExtended
  return extendedBits
:giveQuad
  return quadBits

op leastPower "The power of two of a format's subnormals (and its least normal): -1074, -16445, or -16494"
  invariant givesLeast "Gives -1074 for a double"
  input kind Int64 copied
  output Int64
  let doublePower Int64 -1074
  let extendedPower Int64 -16445
  let quadPower Int64 -16494
  let floatPower Int64 -149
:begin
  when kind == 0 giveDouble notDouble
:giveDouble
  return doublePower
:notDouble
  when kind == 3 giveFloat notFloat
:giveFloat
  return floatPower
:notFloat
  when kind == 1 giveExtended giveQuad
:giveExtended
  return extendedPower
:giveQuad
  return quadPower

op greatestPower "The power of two of a format's largest finite values: 971, 16320, or 16271"
  invariant givesGreatest "Gives 971 for a double"
  input kind Int64 copied
  output Int64
  let doublePower Int64 971
  let extendedPower Int64 16320
  let quadPower Int64 16271
  let floatPower Int64 104
:begin
  when kind == 0 giveDouble notDouble
:giveDouble
  return doublePower
:notDouble
  when kind == 3 giveFloat notFloat
:giveFloat
  return floatPower
:notFloat
  when kind == 1 giveExtended giveQuad
:giveExtended
  return extendedPower
:giveQuad
  return quadPower

## ---------------------------------------------------------------- parts

op partsNew "A zeroed block for a long double's parts"
  invariant givesZeroed "Gives a zeroed block of parts: +0"
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  parts = heap.take(48)
  return parts

op getPart "A part of a long double's parts, as a whole number: 0 sign, 8 kind, 16 power"
  invariant readsPart "Gives what setPart set"
  input parts machine.Address copied
  input offset Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  calc at = parts + offset
  value = machine.loadInt64(at)
  return value

op setPart "Set a part of a long double's parts"
  invariant writesPart "getPart then gives the value"
  input parts machine.Address copied
  input offset Int64 copied
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc at = parts + offset
  machine.storeInt64(at, value)
  return

op highOf "The significand's high 64 bits"
  invariant readsHigh "Gives the high word setSignificand set"
  input parts machine.Address copied
  output UInt64
  effect use machine.memory
  uses memoryAccess
:begin
  calc at = parts + 24
  value = machine.loadUInt64(at)
  return value

op lowOf "The significand's low 64 bits"
  invariant readsLow "Gives the low word setSignificand set"
  input parts machine.Address copied
  output UInt64
  effect use machine.memory
  uses memoryAccess
:begin
  calc at = parts + 32
  value = machine.loadUInt64(at)
  return value

op setSignificand "Set the significand's two words"
  invariant writesSignificand "highOf and lowOf then give the words"
  input parts machine.Address copied
  input high UInt64 copied
  input low UInt64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  calc highAt = parts + 24
  machine.storeUInt64(highAt, high)
  calc lowAt = parts + 32
  machine.storeUInt64(lowAt, low)
  return

op unpack "Read the long double at an address into parts"
  invariant readsParts "A long double written by pack reads back as the same parts"
  input source machine.Address copied
  input parts machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  layout = format()
  unpackAs(source, parts, layout)
  return

op unpackAs "Read a value of a layout (0 double, 1 x87, 2 binary128, 3 float) at an address into parts"
  invariant readsLayout "Reads a float's bits as its parts"
  input source machine.Address copied
  input parts machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  uses memoryAccess
  let kind Int64 1 mut
:begin
  low = machine.loadUInt64(source)
  calc highAt = source + 8
  high = machine.loadUInt64(highAt)
  when layout == 3 single notSingle
:single
  calc singleBits = low & 4294967295
  calc singleSign = convert.uint64ToInt64(singleBits >> 31)
  calc singleField = convert.uint64ToInt64((singleBits >> 23) & 255)
  calc singleFraction = singleBits & 8388607
  setPart(parts, 0, singleSign)
  when singleField == 255 singleSpecial singleFinite
:singleSpecial
  setSignificand(parts, 0, singleFraction)
  calc kind := 2 + choose(singleFraction != 0, 1)
  goto finish
:singleFinite
  when singleField == 0 singleSubnormal singleNormal
:singleSubnormal
  setSignificand(parts, 0, singleFraction)
  setPart(parts, 16, -149)
  calc kind := choose(singleFraction != 0, 1)
  goto finish
:singleNormal
  setSignificand(parts, 0, singleFraction | 8388608)
  setPart(parts, 16, singleField - 150)
  goto finish
:notSingle
  when layout == 0 double notDouble
:double
  calc doubleSign = convert.uint64ToInt64(low >> 63)
  calc doubleField = convert.uint64ToInt64((low >> 52) & 2047)
  calc doubleFraction = low & 4503599627370495
  setPart(parts, 0, doubleSign)
  when doubleField == 2047 doubleSpecial doubleFinite
:doubleSpecial
  setSignificand(parts, 0, doubleFraction)
  calc kind := 2 + choose(doubleFraction != 0, 1)
  goto finish
:doubleFinite
  when doubleField == 0 doubleSubnormal doubleNormal
:doubleSubnormal
  setSignificand(parts, 0, doubleFraction)
  setPart(parts, 16, -1074)
  calc kind := choose(doubleFraction != 0, 1)
  goto finish
:doubleNormal
  setSignificand(parts, 0, doubleFraction | 4503599627370496)
  setPart(parts, 16, doubleField - 1075)
  goto finish
:notDouble
  when layout == 1 extended quad
:extended
  calc extendedTop = high & 65535
  calc extendedSign = convert.uint64ToInt64(extendedTop >> 15)
  calc extendedField = convert.uint64ToInt64(extendedTop & 32767)
  setPart(parts, 0, extendedSign)
  setSignificand(parts, 0, low)
  when extendedField == 32767 extendedSpecial extendedFinite
:extendedSpecial
  calc kind := 2 + choose((low << 1) != 0, 1)
  goto finish
:extendedFinite
  when extendedField == 0 extendedSubnormal extendedNormal
:extendedSubnormal
  setPart(parts, 16, -16445)
  calc kind := choose(low != 0, 1)
  goto finish
:extendedNormal
  setPart(parts, 16, extendedField - 16446)
  goto finish
:quad
  calc quadSign = convert.uint64ToInt64(high >> 63)
  calc quadField = convert.uint64ToInt64((high >> 48) & 32767)
  calc quadFraction = high & 281474976710655
  setPart(parts, 0, quadSign)
  when quadField == 32767 quadSpecial quadFinite
:quadSpecial
  setSignificand(parts, quadFraction, low)
  calc kind := 2 + choose(quadFraction != 0 || low != 0, 1)
  goto finish
:quadFinite
  when quadField == 0 quadSubnormal quadNormal
:quadSubnormal
  setSignificand(parts, quadFraction, low)
  setPart(parts, 16, -16494)
  calc kind := choose(quadFraction != 0 || low != 0, 1)
  goto finish
:quadNormal
  setSignificand(parts, quadFraction | 281474976710656, low)
  setPart(parts, 16, quadField - 16495)
  goto finish
:finish
  setPart(parts, 8, kind)
  return

op choose "1 when a condition holds, else 0"
  input condition Bool copied
  input value Int64 copied
  output Int64
  let zero Int64 0
:begin
  if condition give noValue
:give
  return value
:noValue
  return zero

op pack "Write parts as a long double at an address: a zero, an infinity, a NaN (quiet), or a finite value whose significand is normalized or subnormal (settle makes it so)"
  invariant writesParts "Writes the format's bits for the parts"
  input parts machine.Address copied
  input target machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  layout = format()
  packAs(parts, target, layout)
  return

op packAs "Write parts as a value of a layout (0 double, 1 x87, 2 binary128, 3 float) at an address: a zero, an infinity, a NaN (quiet), or a finite value whose significand is normalized or subnormal"
  invariant writesLayout "Writes a float's bits for its parts"
  input parts machine.Address copied
  input target machine.Address copied
  input layout Int64 copied
  effect use machine.memory
  uses memoryAccess
  let field UInt64 0 mut
:begin
  sign = getPart(parts, 0)
  kind = getPart(parts, 8)
  power = getPart(parts, 16)
  high = highOf(parts)
  low = lowOf(parts)
  calc signWord = convert.int64ToUInt64(sign)
  calc size = 16 - choose(layout == 0, 8) - choose(layout == 3, 12)
  machine.fill(target, 0, size)
  precision = precisionOf(layout)
  calc normal = kind == 1 && topSet(high, low, precision - 1)
  when layout == 3 single notSingle
:single
  when kind == 2 singleInfinite singleNan
:singleInfinite
  machine.storeInt32(target, clibrary.lowInt32(convert.uint64ToInt64((signWord << 31) | 2139095040)))
  return
:singleNan
  when kind == 3 singleQuiet singleFinite
:singleQuiet
  machine.storeInt32(target, clibrary.lowInt32(convert.uint64ToInt64((signWord << 31) | 2143289344)))
  return
:singleFinite
  calc singleField = convert.int64ToUInt64(choose(normal, power + 150))
  machine.storeInt32(target, clibrary.lowInt32(convert.uint64ToInt64((signWord << 31) | (singleField << 23) | (low & 8388607))))
  return
:notSingle
  when layout == 0 double notDouble
:double
  when kind == 2 doubleInfinite doubleNan
:doubleInfinite
  machine.storeUInt64(target, (signWord << 63) | 9218868437227405312)
  return
:doubleNan
  when kind == 3 doubleQuiet doubleFinite
:doubleQuiet
  machine.storeUInt64(target, (signWord << 63) | 9221120237041090560 | (low & 4503599627370495))
  return
:doubleFinite
  when normal doubleNormal doubleSmall
:doubleNormal
  calc field := convert.int64ToUInt64(power + 1075)
  goto doubleWrite
:doubleSmall
  calc field := 0
  goto doubleWrite
:doubleWrite
  machine.storeUInt64(target, (signWord << 63) | (field << 52) | (low & 4503599627370495))
  return
:notDouble
  when layout == 1 extended quad
:extended
  calc extendedHighAt = target + 8
  when kind == 2 extendedInfinite extendedNan
:extendedInfinite
  machine.storeUInt64(target, topBit)
  machine.storeUInt64(extendedHighAt, (signWord << 15) | 32767)
  return
:extendedNan
  when kind == 3 extendedQuiet extendedFinite
:extendedQuiet
  machine.storeUInt64(target, low | 13835058055282163712)
  machine.storeUInt64(extendedHighAt, (signWord << 15) | 32767)
  return
:extendedFinite
  when normal extendedNormal extendedSmall
:extendedNormal
  calc field := convert.int64ToUInt64(power + 16446)
  goto extendedWrite
:extendedSmall
  calc field := 0
  goto extendedWrite
:extendedWrite
  machine.storeUInt64(target, low)
  machine.storeUInt64(extendedHighAt, (signWord << 15) | field)
  return
:quad
  calc quadHighAt = target + 8
  when kind == 2 quadInfinite quadNan
:quadInfinite
  machine.storeUInt64(quadHighAt, (signWord << 63) | 9223090561878065152)
  return
:quadNan
  when kind == 3 quadQuiet quadFinite
:quadQuiet
  machine.storeUInt64(target, low)
  machine.storeUInt64(quadHighAt, (signWord << 63) | 9223231299366420480 | (high & 281474976710655))
  return
:quadFinite
  when normal quadNormal quadSmall
:quadNormal
  calc field := convert.int64ToUInt64(power + 16495)
  goto quadWrite
:quadSmall
  calc field := 0
  goto quadWrite
:quadWrite
  machine.storeUInt64(target, low)
  machine.storeUInt64(quadHighAt, (signWord << 63) | (field << 48) | (high & 281474976710655))
  return

op topSet "Whether bit n (counted from 0) of high * 2^64 + low is set"
  input high UInt64 copied
  input low UInt64 copied
  input position Int64 copied
  output Bool
:begin
  when position >= 64 inHigh inLow
:inHigh
  calc highSet = ((high >> (position - 64)) & 1) == 1
  return highSet
:inLow
  calc lowSet = ((low >> position) & 1) == 1
  return lowSet

## ---------------------------------------------------------------- 128-bit significands

op mask64 "A word of the low `count` bits set (0 to 64)"
  input count Int64 copied
  output UInt64
  let all UInt64 18446744073709551615
  let noBits UInt64 0
:begin
  when count >= 64 full partial
:full
  return all
:partial
  when count <= 0 empty some
:empty
  return noBits
:some
  calc bitsSet = (convert.int64ToUInt64(1) << count) - 1
  return bitsSet

op lowBitsSet "Whether any of the low `count` bits of high * 2^64 + low is set"
  invariant seesLowBits "Sees a set bit just inside the count and not one just past it"
  input high UInt64 copied
  input low UInt64 copied
  input count Int64 copied
  output Bool
:begin
  when count <= 64 lowOnly both
:lowOnly
  calc fromLow = (low & mask64(count)) != 0
  return fromLow
:both
  calc fromBoth = low != 0 || (high & mask64(count - 64)) != 0
  return fromBoth

op bitLength "How many bits high * 2^64 + low takes: 0 for 0"
  invariant countsLength "Gives 65 for 2^64"
  input high UInt64 copied
  input low UInt64 copied
  output Int64
  let length Int64 0 mut
  let rest UInt64 0 mut
:begin
  when high != 0 fromHigh fromLow
:fromHigh
  set rest high
  calc length := 64
  goto eachBit
:fromLow
  set rest low
  goto eachBit
:eachBit loop=while max=forever
  when rest == 0 finish count
:count in=eachBit
  calc length := length + 1
  calc rest := rest >> 1
  goto eachBit
:finish
  return length

op shiftUp "Shift a parts' significand left by 0 to 127 bits (no bit it keeps is lost: the caller knows it fits)"
  input parts machine.Address copied
  input count Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  high = highOf(parts)
  low = lowOf(parts)
  when count == 0 done notZero
:notZero
  when count >= 64 far near
:far
  setSignificand(parts, low << (count - 64), 0)
  return
:near
  setSignificand(parts, (high << count) | (low >> (64 - count)), low << count)
  return
:done
  return

op shiftDown "Shift a parts' significand right by a count of bits (0 or more), and say what was dropped: 0 nothing, 1 less than half a unit of the last bit kept, 2 exactly half, 3 more than half"
  input parts machine.Address copied
  input count Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let exact Int64 0
  let below Int64 1
  let half Int64 2
  let above Int64 3
  let state Int64 0 mut
:begin
  high = highOf(parts)
  low = lowOf(parts)
  when count == 0 nothing some
:nothing
  return exact
:some
  when count > 128 allGone notAll
:allGone
  setSignificand(parts, 0, 0)
  when high != 0 || low != 0 giveBelow nothing
:giveBelow
  return below
:notAll
  halfSet = topSet(high, low, count - 1)
  restSet = lowBitsSet(high, low, count - 1)
  when halfSet halfOrAbove belowOrNone
:halfOrAbove
  calc state := half + choose(restSet, 1)
  goto move
:belowOrNone
  calc state := choose(restSet, 1)
  goto move
:move
  when count >= 128 cleared notCleared
:cleared
  setSignificand(parts, 0, 0)
  return state
:notCleared
  when count >= 64 far near
:far
  setSignificand(parts, 0, high >> (count - 64))
  return state
:near
  setSignificand(parts, high >> count, (low >> count) | (high << (64 - count)))
  return state

op addOne "Add 1 to a parts' significand"
  input parts machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  high = highOf(parts)
  low = lowOf(parts)
  when low == 18446744073709551615 carry plain
:carry
  setSignificand(parts, high + 1, 0)
  return
:plain
  setSignificand(parts, high, low + 1)
  return

op roundsUp "Whether a significand cut with what shiftDown said (0 to 3) goes up one, as the rounding mode rounds a value of that sign: to nearest ties to even (the kept significand's last bit), downward, upward, toward zero"
  input dropped Int64 copied
  input lastOdd Bool copied
  input negative Bool copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  when dropped == 0 keepCut rounding
:rounding
  mode = roundingMode()
  when mode == 0 nearest notNearest
:nearest
  calc nearestUp = dropped == 3 || (dropped == 2 && lastOdd)
  return nearestUp
:notNearest
  when mode == 1 downward notDownward
:downward
  return negative
:notDownward
  when mode == 2 upward keepCut
:upward
  calc upwardUp = !negative
  return upwardUp
:keepCut
  return false

op settle "Make a finite parts' significand and power representable in long double's format (settleAs)"
  invariant roundsToFormat "Leaves parts the format can hold, rounded as the rounding mode rounds"
  input parts machine.Address copied
  input dropped Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  layout = format()
  settleAs(parts, dropped, layout)
  return

op settleAs "Make a finite parts' significand and power representable in a layout (0 double, 1 x87, 2 binary128, 3 float): shifted to its precision (or to the subnormals' power), rounded as the rounding mode rounds (what was dropped before, 0 to 3, counts as sticky); past the largest finite value an infinity, or the largest itself where the rounding mode rounds toward zero for that sign; a zero significand is a zero"
  invariant roundsToLayout "Leaves parts the layout can hold"
  input parts machine.Address copied
  input dropped Int64 copied
  input layout Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let shift Int64 0 mut
  let power Int64 0 mut
  let lost Int64 0 mut
:begin
  precision = precisionOf(layout)
  least = leastPower(layout)
  greatest = greatestPower(layout)
  high = highOf(parts)
  low = lowOf(parts)
  length = bitLength(high, low)
  when length == 0 && dropped == 0 zeroValue nonzero
:zeroValue
  setPart(parts, 8, 0)
  return
:nonzero
  calc shift := length - precision
  calc power := getPart(parts, 16) + shift
  when power < least subnormal placed
:subnormal
  calc shift := shift + (least - power)
  set power least
  goto placed
:placed
  when shift > 0 down raise
:raise
  shiftUp(parts, 0 - shift)
  set lost dropped
  goto check
:down
  calc cut = shiftDown(parts, shift)
  calc lost := mergeDropped(cut, dropped)
  goto check
:check
  sign = getPart(parts, 0)
  kept = lowOf(parts)
  calc odd = (kept & 1) == 1
  calc goesUp = roundsUp(lost, odd, sign == 1)
  if goesUp increment range
:increment
  addOne(parts)
  newHigh = highOf(parts)
  newLow = lowOf(parts)
  calc newLength = bitLength(newHigh, newLow)
  when newLength > precision carried range
:carried
  shiftDown(parts, 1)
  calc power := power + 1
  goto range
:range
  setPart(parts, 16, power)
  when power > greatest overflow fine
:overflow
  mode = roundingMode()
  calc negative = sign == 1
  when mode == 3 || (mode == 1 && !negative) || (mode == 2 && negative) largest infinite
:largest
  setPart(parts, 16, greatest)
  setSignificand(parts, 0, 0)
  setTop(parts, precision)
  subtractOne(parts)
  setPart(parts, 8, 1)
  return
:infinite
  setPart(parts, 8, 2)
  setSignificand(parts, 0, 0)
  return
:fine
  finalHigh = highOf(parts)
  finalLow = lowOf(parts)
  calc empty = finalHigh == 0 && finalLow == 0
  calc finalKind = 1 - choose(empty, 1)
  setPart(parts, 8, finalKind)
  return

op mergeDropped "What two cuts dropped together, the second from below the first: the first's half and above, made more than half (or below half from nothing) when the second dropped anything"
  input first Int64 copied
  input second Int64 copied
  output Int64
  let above Int64 3
  let below Int64 1
:begin
  when second == 0 keep merge
:keep
  return first
:merge
  when first == 2 giveAbove notHalf
:giveAbove
  return above
:notHalf
  when first == 0 giveBelow keep
:giveBelow
  return below

op partsOf "A long double's parts, in a new block"
  input value machine.LongDouble copied
  output machine.Address
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  cell = heap.take(16)
  machine.storeLongDouble(cell, value)
  parts = partsNew()
  unpack(cell, parts)
  heap.give(cell)
  return parts

op valueOf "The long double parts stand for, the parts' block given back"
  input parts machine.Address copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  cell = heap.take(16)
  pack(parts, cell)
  value = machine.loadLongDouble(cell)
  heap.give(cell)
  heap.give(parts)
  return value

## ---------------------------------------------------------------- signs, classes, and powers of two

op absoluteLong "fabsl: the value with its sign cleared"
  input value machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fabsl"
:begin
  parts = partsOf(value)
  setPart(parts, 0, 0)
  result = valueOf(parts)
  return result

op copySignLong "copysignl: the magnitude of one value with the sign of another"
  input magnitude machine.LongDouble copied
  input sign machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "copysignl"
:begin
  parts = partsOf(magnitude)
  signParts = partsOf(sign)
  signBit = getPart(signParts, 0)
  heap.give(signParts)
  setPart(parts, 0, signBit)
  result = valueOf(parts)
  return result

op normalize "Shift a finite nonzero parts' significand up until its top bit is at the precision's place, lowering its power (past the subnormals' power, as frexp and ilogb need)"
  input parts machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  layout = format()
  precision = precisionOf(layout)
  high = highOf(parts)
  low = lowOf(parts)
  length = bitLength(high, low)
  calc gap = precision - length
  when gap > 0 && length > 0 shift done
:shift
  shiftUp(parts, gap)
  power = getPart(parts, 16)
  setPart(parts, 16, power - gap)
  return
:done
  return

op splitLong "frexpl: the value as a fraction in [0.5, 1) times 2^n, n stored; zero, infinities, and NaN as they are (n 0)"
  input value machine.LongDouble copied
  input exponent machine.Address copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "frexpl"
:begin
  parts = partsOf(value)
  kind = getPart(parts, 8)
  when kind == 1 finite other
:other
  machine.storeInt32(exponent, 0)
  result = valueOf(parts)
  return result
:finite
  normalize(parts)
  layout = format()
  precision = precisionOf(layout)
  power = getPart(parts, 16)
  machine.storeInt32(exponent, clibrary.lowInt32(power + precision))
  setPart(parts, 16, 0 - precision)
  fraction = valueOf(parts)
  return fraction

op scaleParts "A long double times 2^n, rounded as the rounding mode rounds where it falls among the subnormals, an infinity past the largest; whether it overflowed or underflowed (for ldexp's ERANGE) is stored at an address"
  input value machine.LongDouble copied
  input count Int64 copied
  input ranged machine.Address copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  machine.storeInt64(ranged, 0)
  parts = partsOf(value)
  kind = getPart(parts, 8)
  when kind == 1 finite other
:other
  result = valueOf(parts)
  return result
:finite
  normalize(parts)
  power = getPart(parts, 16)
  calc bounded = highestOf(lowestOf(count, 70000), -70000)
  setPart(parts, 16, power + bounded)
  settle(parts, 0)
  after = getPart(parts, 8)
  when after != 1 rangeError fine
:rangeError
  machine.storeInt64(ranged, 1)
  goto fine
:fine
  scaled = valueOf(parts)
  return scaled

op lowestOf "The smaller of two whole numbers"
  input left Int64 copied
  input right Int64 copied
  output Int64
:begin
  when left <= right giveLeft giveRight
:giveLeft
  return left
:giveRight
  return right

op highestOf "The larger of two whole numbers"
  input left Int64 copied
  input right Int64 copied
  output Int64
:begin
  when left >= right giveLeft giveRight
:giveLeft
  return left
:giveRight
  return right

op loadExponentLong "ldexpl: a long double times 2^n, ERANGE when it overflows to an infinity or underflows to 0"
  input value machine.LongDouble copied
  input count Int32 copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "ldexpl"
:begin
  ranged = heap.take(8)
  result = scaleParts(value, convert.int32ToInt64(count), ranged)
  flag = machine.loadInt64(ranged)
  heap.give(ranged)
  when flag == 1 setRange done
:setRange
  clibrary.setErrno(34)
  goto done
:done
  return result

op scaleLong "scalbnl: a long double times 2^n"
  input value machine.LongDouble copied
  input count Int32 copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "scalbnl"
:begin
  ranged = heap.take(8)
  result = scaleParts(value, convert.int32ToInt64(count), ranged)
  heap.give(ranged)
  return result

op scaleLongLong "scalblnl: a long double times 2^n, n a long"
  input value machine.LongDouble copied
  input count Int64 copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "scalblnl"
:begin
  ranged = heap.take(8)
  result = scaleParts(value, count, ranged)
  heap.give(ranged)
  return result

op exponentOfLong "ilogbl: the exponent of a long double as an int: FP_ILOGB0 (INT_MIN) for 0, FP_ILOGBNAN (INT_MIN) for NaN, INT_MAX for an infinity, each with EDOM"
  input value machine.LongDouble copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "ilogbl"
  let least Int32 -2147483648
  let most Int32 2147483647
:begin
  parts = partsOf(value)
  kind = getPart(parts, 8)
  when kind == 1 finite special
:special
  heap.give(parts)
  clibrary.setErrno(33)
  when kind == 2 infinite zeroOrNan
:infinite
  return most
:zeroOrNan
  return least
:finite
  normalize(parts)
  layout = format()
  precision = precisionOf(layout)
  power = getPart(parts, 16)
  heap.give(parts)
  calc exponent = clibrary.lowInt32(power + precision - 1)
  return exponent

op logbLong "logbl: the exponent of a long double as a long double: -infinity for 0, +infinity for an infinity, NaN for NaN"
  input value machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "logbl"
:begin
  parts = partsOf(value)
  kind = getPart(parts, 8)
  when kind == 1 finite special
:special
  when kind == 0 zero notZero
:zero
  setPart(parts, 0, 1)
  setPart(parts, 8, 2)
  result = valueOf(parts)
  return result
:notZero
  setPart(parts, 0, 0)
  same = valueOf(parts)
  return same
:finite
  normalize(parts)
  layout = format()
  precision = precisionOf(layout)
  power = getPart(parts, 16)
  heap.give(parts)
  calc exponent = power + precision - 1
  logb = machine.longDoubleFromInt64(exponent)
  return logb

op notANumberLong "nanl: a quiet NaN (the text's payload is not kept)"
  input text machine.Address copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "nanl"
:begin
  parts = partsNew()
  setPart(parts, 8, 3)
  result = valueOf(parts)
  return result

## ---------------------------------------------------------------- whole numbers

op roundParts "Round a finite parts to a whole number in place: 0 toward zero (trunc), 1 down (floor), 2 up (ceil), 3 to nearest with halves away from zero (round), 4 as the rounding mode rounds (rint)"
  input parts machine.Address copied
  input way Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let up Bool false mut
:begin
  power = getPart(parts, 16)
  when power >= 0 done cut
:cut
  calc dropped = shiftDown(parts, 0 - power)
  setPart(parts, 16, 0)
  sign = getPart(parts, 0)
  calc negative = sign == 1
  kept = lowOf(parts)
  calc odd = (kept & 1) == 1
  when way == 1 floorWay notFloor
:floorWay
  calc up := negative && dropped != 0
  goto apply
:notFloor
  when way == 2 ceilWay notCeil
:ceilWay
  calc up := !negative && dropped != 0
  goto apply
:notCeil
  when way == 3 roundWay notRound
:roundWay
  calc up := dropped >= 2
  goto apply
:notRound
  when way == 4 rintWay apply
:rintWay
  calc up := roundsUp(dropped, odd, negative)
  goto apply
:apply
  if up bump settleIt
:bump
  addOne(parts)
  goto settleIt
:settleIt
  settle(parts, 0)
  return
:done
  return

op roundLong "A long double rounded to a whole number one of roundParts's ways; zero, infinities, and NaN as they are"
  input value machine.LongDouble copied
  input way Int64 copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  parts = partsOf(value)
  kind = getPart(parts, 8)
  when kind == 1 finite done
:finite
  roundParts(parts, way)
  goto done
:done
  result = valueOf(parts)
  return result

op truncLong "truncl: the whole number toward zero"
  input value machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "truncl"
:begin
  result = roundLong(value, 0)
  return result

op floorLong "floorl: the greatest whole number not above"
  input value machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "floorl"
:begin
  result = roundLong(value, 1)
  return result

op ceilLong "ceill: the least whole number not below"
  input value machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "ceill"
:begin
  result = roundLong(value, 2)
  return result

op roundHalfAwayLong "roundl: the nearest whole number, halves away from zero"
  input value machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "roundl"
:begin
  result = roundLong(value, 3)
  return result

op rintLong "rintl: the whole number the rounding mode rounds to"
  input value machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "rintl"
:begin
  result = roundLong(value, 4)
  return result

op nearbyLong "nearbyintl: rintl (no exception is raised either way here)"
  input value machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "nearbyintl"
:begin
  result = roundLong(value, 4)
  return result

op wholeOf "A long double rounded one of roundParts's ways, as a long: past a long's range (and NaN) x86_64's conversion gives LONG_MIN and AArch64's the nearest limit (0 for NaN), as glibc's on each"
  input value machine.LongDouble copied
  input way Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let least Int64 -9223372036854775808
  let most Int64 9223372036854775807
  let zero Int64 0
  let magnitude UInt64 0 mut
:begin
  parts = partsOf(value)
  kind = getPart(parts, 8)
  sign = getPart(parts, 0)
  when kind == 0 giveZero notZero
:giveZero
  heap.give(parts)
  return zero
:notZero
  when kind == 1 finite outside
:finite
  roundParts(parts, way)
  power = getPart(parts, 16)
  high = highOf(parts)
  low = lowOf(parts)
  roundedKind = getPart(parts, 8)
  heap.give(parts)
  when roundedKind == 0 giveZero sized
:sized
  when power < 0 shrink grow
:shrink
  calc shift = 0 - power
  when shift >= 64 shrinkFar shrinkNear
:shrinkFar
  calc magnitude := high >> (shift - 64)
  goto ranged
:shrinkNear
  calc magnitude := (low >> shift) | (high << (64 - shift))
  goto ranged
:grow
  when power >= 64 || high != 0 outside fits
:fits
  calc magnitude := low << power
  calc back = magnitude >> power
  when back == low ranged outside
:ranged
  when sign == 1 negativeRange positiveRange
:negativeRange
  when magnitude <= 9223372036854775808 negativeFits outside
:negativeFits
  calc negativeValue = convert.uint64BitsToInt64(math.wrappingSubtractUInt64(0, magnitude))
  return negativeValue
:positiveRange
  when magnitude <= 9223372036854775807 positiveFits outside
:positiveFits
  calc positiveValue = convert.uint64ToInt64(magnitude)
  return positiveValue
:outside
  onArm = system.aarch64()
  if onArm saturate intelLeast
:intelLeast
  return least
:saturate
  when kind == 3 giveZero saturateSign
:saturateSign
  when sign == 1 intelLeast giveMost
:giveMost
  return most

op lrintLong "lrintl: rintl as a long"
  input value machine.LongDouble copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "lrintl"
:begin
  result = wholeOf(value, 4)
  return result

op llrintLong "llrintl: rintl as a long long"
  input value machine.LongDouble copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "llrintl"
:begin
  result = wholeOf(value, 4)
  return result

op lroundLong "lroundl: roundl as a long"
  input value machine.LongDouble copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "lroundl"
:begin
  result = wholeOf(value, 3)
  return result

op llroundLong "llroundl: roundl as a long long"
  input value machine.LongDouble copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "llroundl"
:begin
  result = wholeOf(value, 3)
  return result

op splitWholeLong "modfl: the fraction, with the whole part (toward zero) stored; both keep the value's sign, an infinity's fraction is 0, a NaN gives NaN to both"
  input value machine.LongDouble copied
  input whole machine.Address copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  whole0 = roundLong(value, 0)
  machine.storeLongDouble(whole, whole0)
  parts = partsOf(value)
  kind = getPart(parts, 8)
  power = getPart(parts, 16)
  when kind == 3 nan notNan
:nan
  same = valueOf(parts)
  return same
:notNan
  when kind == 2 || (kind == 1 && power >= 0) zeroFraction fraction
:zeroFraction
  setPart(parts, 8, 0)
  noFraction = valueOf(parts)
  return noFraction
:fraction
  high = highOf(parts)
  low = lowOf(parts)
  calc bits = 0 - power
  when bits >= 128 keep masked
:masked
  when bits > 64 maskHigh maskLow
:maskHigh
  setSignificand(parts, high & mask64(bits - 64), low)
  goto keep
:maskLow
  setSignificand(parts, 0, low & mask64(bits))
  goto keep
:keep
  settle(parts, 0)
  rest = valueOf(parts)
  return rest

op splitWholeLongC "modfl, as the C library's table holds it"
  input value machine.LongDouble copied
  input whole machine.Address copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "modfl"
:begin
  result = splitWholeLong(value, whole)
  return result

## ---------------------------------------------------------------- comparisons

op compareParts "How two finite or infinite parts compare by value: -1, 0, or 1 (zeros of either sign are equal)"
  input left machine.Address copied
  input right machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let less Int64 -1
  let same Int64 0
  let more Int64 1
:begin
  leftKind = getPart(left, 8)
  rightKind = getPart(right, 8)
  leftSign = getPart(left, 0)
  rightSign = getPart(right, 0)
  when leftKind == 0 && rightKind == 0 giveSame signs
:signs
  calc leftNegative = leftSign == 1 && leftKind != 0
  calc rightNegative = rightSign == 1 && rightKind != 0
  when leftNegative && !rightNegative giveLess notLess
:notLess
  when !leftNegative && rightNegative giveMore magnitudes
:magnitudes
  calc order = compareMagnitude(left, right)
  when leftNegative flip keep
:flip
  calc flipped = 0 - order
  return flipped
:keep
  return order
:giveLess
  return less
:giveMore
  return more
:giveSame
  return same

op compareMagnitude "How two parts' magnitudes compare: -1, 0, or 1 (an infinity above every finite value, zero below)"
  input left machine.Address copied
  input right machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let less Int64 -1
  let same Int64 0
  let more Int64 1
:begin
  leftKind = getPart(left, 8)
  rightKind = getPart(right, 8)
  calc leftRank = rankOf(leftKind)
  calc rightRank = rankOf(rightKind)
  when leftRank < rightRank giveLess notLess
:notLess
  when leftRank > rightRank giveMore sameRank
:sameRank
  when leftKind != 1 giveSame finite
:finite
  normalize(left)
  normalize(right)
  leftPower = getPart(left, 16)
  rightPower = getPart(right, 16)
  when leftPower < rightPower giveLess notLower
:notLower
  when leftPower > rightPower giveMore words
:words
  leftHigh = highOf(left)
  rightHigh = highOf(right)
  when leftHigh < rightHigh giveLess notHighLess
:notHighLess
  when leftHigh > rightHigh giveMore lows
:lows
  leftLow = lowOf(left)
  rightLow = lowOf(right)
  when leftLow < rightLow giveLess notLowLess
:notLowLess
  when leftLow > rightLow giveMore giveSame
:giveLess
  return less
:giveMore
  return more
:giveSame
  return same

op rankOf "The order of a kind of value by magnitude: zero 0, finite 1, infinite 2 (NaN, never compared, 3)"
  input kind Int64 copied
  output Int64
:begin
  return kind

op largerLong "fmaxl: the larger value; a NaN gives way to the other"
  input left machine.LongDouble copied
  input right machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fmaxl"
:begin
  choice = pickLong(left, right, 1)
  return choice

op smallerLong "fminl: the smaller value; a NaN gives way to the other"
  input left machine.LongDouble copied
  input right machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fminl"
:begin
  choice = pickLong(left, right, -1)
  return choice

op pickLong "fmaxl (want 1) or fminl (want -1): the larger or smaller value; a NaN gives way to the other; between zeros of both signs +0 is larger"
  input left machine.LongDouble copied
  input right machine.LongDouble copied
  input want Int64 copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  leftParts = partsOf(left)
  rightParts = partsOf(right)
  leftKind = getPart(leftParts, 8)
  rightKind = getPart(rightParts, 8)
  when leftKind == 3 giveRight notLeftNan
:notLeftNan
  when rightKind == 3 giveLeft compareThem
:compareThem
  order = compareParts(leftParts, rightParts)
  when order == 0 && leftKind == 0 zeros ordered
:zeros
  leftSign = getPart(leftParts, 0)
  calc leftPositive = leftSign == 0
  calc leftWins = (want == 1 && leftPositive) || (want == -1 && !leftPositive)
  if leftWins giveLeft giveRight
:ordered
  when order == want || order == 0 giveLeft giveRight
:giveLeft
  heap.give(leftParts)
  heap.give(rightParts)
  return left
:giveRight
  heap.give(leftParts)
  heap.give(rightParts)
  return right

op differenceLong "fdiml: left less right when left is larger, else +0; NaN for a NaN"
  input left machine.LongDouble copied
  input right machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fdiml"
:begin
  leftParts = partsOf(left)
  rightParts = partsOf(right)
  leftKind = getPart(leftParts, 8)
  rightKind = getPart(rightParts, 8)
  when leftKind == 3 || rightKind == 3 nan compareThem
:nan
  heap.give(rightParts)
  heap.give(leftParts)
  sum = machine.addLongDouble(left, right)
  return sum
:compareThem
  order = compareParts(leftParts, rightParts)
  heap.give(rightParts)
  when order > 0 subtract zero
:subtract
  heap.give(leftParts)
  difference = machine.subtractLongDouble(left, right)
  return difference
:zero
  setPart(leftParts, 0, 0)
  setPart(leftParts, 8, 0)
  positiveZero = valueOf(leftParts)
  return positiveZero

## ---------------------------------------------------------------- the next value

op stepParts "Move finite or infinite parts of a layout to the next value toward zero or away from it (an infinity's next toward zero is the largest finite, 0's away is the least subnormal, the largest's away is an infinity)"
  input parts machine.Address copied
  input layout Int64 copied
  input towardZero Bool copied
  effect use machine.memory
  uses memoryAccess
:begin
  precision = precisionOf(layout)
  least = leastPower(layout)
  greatest = greatestPower(layout)
  kind = getPart(parts, 8)
  when kind == 2 fromInfinity notInfinity
:fromInfinity
  setPart(parts, 8, 1)
  setTop(parts, precision)
  subtractOne(parts)
  setPart(parts, 16, greatest)
  return
:notInfinity
  when kind == 0 fromZero finite
:fromZero
  setPart(parts, 8, 1)
  setSignificand(parts, 0, 1)
  setPart(parts, 16, least)
  return
:finite
  power = getPart(parts, 16)
  if towardZero down up
:up
  addOne(parts)
  high = highOf(parts)
  low = lowOf(parts)
  calc length = bitLength(high, low)
  when length > precision carry done
:carry
  shiftDown(parts, 1)
  setPart(parts, 16, power + 1)
  when power + 1 > greatest overflow done
:overflow
  setPart(parts, 8, 2)
  setSignificand(parts, 0, 0)
  return
:down
  downHigh = highOf(parts)
  downLow = lowOf(parts)
  calc atTop = bitLength(downHigh, downLow) == precision && !lowBitsSet(downHigh, downLow, precision - 1)
  when atTop && power > least borrow plain
:borrow
  setTop(parts, precision)
  subtractOne(parts)
  setPart(parts, 16, power - 1)
  return
:plain
  subtractOne(parts)
  afterHigh = highOf(parts)
  afterLow = lowOf(parts)
  when afterHigh == 0 && afterLow == 0 becameZero done
:becameZero
  setPart(parts, 8, 0)
  return
:done
  return

op setTop "Set a parts' significand to 2^precision"
  input parts machine.Address copied
  input precision Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  when precision >= 64 high low
:high
  setSignificand(parts, convert.int64ToUInt64(1) << (precision - 64), 0)
  return
:low
  setSignificand(parts, 0, convert.int64ToUInt64(1) << precision)
  return

op subtractOne "Take 1 from a parts' nonzero significand"
  input parts machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  high = highOf(parts)
  low = lowOf(parts)
  when low == 0 borrow plain
:borrow
  setSignificand(parts, high - 1, 18446744073709551615)
  return
:plain
  setSignificand(parts, high, low - 1)
  return

op nextParts "nextafter's work on parts of a layout toward a target's parts: a NaN stays (the target's when it is the NaN), equal values give the target, else one step toward it; ERANGE when the step gives an infinity, a subnormal, or 0"
  input parts machine.Address copied
  input layout Int64 copied
  input target machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  kind = getPart(parts, 8)
  targetKind = getPart(target, 8)
  when kind == 3 done notNan
:notNan
  when targetKind == 3 takeNan compareThem
:takeNan
  setPart(parts, 8, 3)
  setSignificand(parts, 0, 0)
  return
:compareThem
  order = compareParts(parts, target)
  when order == 0 equal step
:equal
  targetSign = getPart(target, 0)
  setPart(parts, 0, targetSign)
  return
:step
  sign = getPart(parts, 0)
  when kind == 0 fromZero fromValue
:fromZero
  calc towardSign = choose(order > 0, 1)
  setPart(parts, 0, towardSign)
  stepParts(parts, layout, false)
  goto range
:fromValue
  calc towardZero = (order > 0 && sign == 0) || (order < 0 && sign == 1)
  stepParts(parts, layout, towardZero)
  goto range
:range
  after = getPart(parts, 8)
  power = getPart(parts, 16)
  least = leastPower(layout)
  precision = precisionOf(layout)
  high = highOf(parts)
  low = lowOf(parts)
  calc subnormal = after == 1 && power == least && bitLength(high, low) < precision
  when after == 2 || after == 0 || subnormal rangeError done
:rangeError
  clibrary.setErrno(34)
  return
:done
  return

op nextLong "nextafterl and nexttowardl: the next long double after one toward another"
  input value machine.LongDouble copied
  input toward machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "nextafterl"
:begin
  parts = partsOf(value)
  target = partsOf(toward)
  layout = format()
  nextParts(parts, layout, target)
  heap.give(target)
  result = valueOf(parts)
  return result

op nextTowardLong "nexttowardl: nextafterl"
  input value machine.LongDouble copied
  input toward machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "nexttowardl"
:begin
  result = nextLong(value, toward)
  return result

op nextTowardDouble "nexttoward: the next double after one toward a long double"
  input value Float64 copied
  input toward machine.LongDouble copied
  output Float64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "nexttoward"
:begin
  cell = heap.take(16)
  machine.storeFloat64(cell, value)
  parts = partsNew()
  unpackAs(cell, parts, 0)
  target = partsOf(toward)
  nextParts(parts, 0, target)
  heap.give(target)
  packAs(parts, cell, 0)
  result = machine.loadFloat64(cell)
  heap.give(parts)
  heap.give(cell)
  return result

op nextTowardFloat "nexttowardf: the next float after one toward a long double"
  input value Float32 copied
  input toward machine.LongDouble copied
  output Float32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "nexttowardf"
:begin
  cell = heap.take(16)
  machine.storeFloat32(cell, value)
  parts = partsNew()
  unpackAs(cell, parts, 3)
  target = partsOf(toward)
  nextParts(parts, 3, target)
  heap.give(target)
  packAs(parts, cell, 3)
  result = machine.loadFloat32(cell)
  heap.give(parts)
  heap.give(cell)
  return result

## ---------------------------------------------------------------- remainders

op compareSignificands "How two parts' significands compare as whole numbers: -1, 0, or 1"
  input left machine.Address copied
  input right machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let less Int64 -1
  let same Int64 0
  let more Int64 1
:begin
  leftHigh = highOf(left)
  rightHigh = highOf(right)
  when leftHigh < rightHigh giveLess notLess
:notLess
  when leftHigh > rightHigh giveMore lows
:lows
  leftLow = lowOf(left)
  rightLow = lowOf(right)
  when leftLow < rightLow giveLess notLowLess
:notLowLess
  when leftLow > rightLow giveMore giveSame
:giveLess
  return less
:giveMore
  return more
:giveSame
  return same

op subtractSignificand "Take a parts' significand from another's, which is not smaller"
  input target machine.Address copied
  input amount machine.Address copied
  effect use machine.memory
  uses memoryAccess
:begin
  targetHigh = highOf(target)
  targetLow = lowOf(target)
  amountHigh = highOf(amount)
  amountLow = lowOf(amount)
  calc lowDifference = math.wrappingSubtractUInt64(targetLow, amountLow)
  calc borrow = choose(targetLow < amountLow, 1)
  calc highDifference = targetHigh - amountHigh - convert.int64ToUInt64(borrow)
  setSignificand(target, highDifference, lowDifference)
  return

op remainderCore "fmod's work on finite nonzero parts: the remainder of |x| by |y| left in x's parts (exactly, at y's power), and the quotient's low three bits given"
  input x machine.Address copied
  input y machine.Address copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let quotient Int64 0 mut
  let power Int64 0 mut
:begin
  normalize(x)
  normalize(y)
  calc power := getPart(x, 16)
  yPower = getPart(y, 16)
  when power < yPower small loop
:small
  return quotient
:loop loop=while max=forever
  order = compareSignificands(x, y)
  when order >= 0 take keep
:take in=loop
  subtractSignificand(x, y)
  calc quotient := (quotient * 2 + 1) & 7
  goto next
:keep in=loop
  calc quotient := (quotient * 2) & 7
  goto next
:next in=loop
  when power == yPower finish shift
:shift in=loop
  shiftUp(x, 1)
  calc power := power - 1
  goto loop
:finish
  setPart(x, 16, yPower)
  return quotient

op remainderSpecial "Whether fmod, remainder, and remquo of two parts are a special case (a NaN, an infinite x, a zero y, which give NaN with EDOM but for a NaN; a zero x or an infinite y, which give x); 0 when neither, 1 for NaN, 2 for x"
  input x machine.Address copied
  input y machine.Address copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let neither Int64 0
  let nan Int64 1
  let keepX Int64 2
:begin
  xKind = getPart(x, 8)
  yKind = getPart(y, 8)
  when xKind == 3 || yKind == 3 giveNan domain
:domain
  when xKind == 2 || yKind == 0 domainError ordinary
:domainError
  clibrary.setErrno(33)
  goto giveNan
:ordinary
  when xKind == 0 || yKind == 2 giveX giveNeither
:giveNan
  setPart(x, 8, 3)
  setSignificand(x, 0, 0)
  return nan
:giveX
  return keepX
:giveNeither
  return neither

op modLong "fmodl: x less the whole multiple of y toward zero, exactly, with x's sign"
  input left machine.LongDouble copied
  input right machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fmodl"
:begin
  x = partsOf(left)
  y = partsOf(right)
  special = remainderSpecial(x, y)
  when special == 0 ordinary done
:ordinary
  remainderCore(x, y)
  settle(x, 0)
  goto done
:done
  heap.give(y)
  result = valueOf(x)
  return result

op nearestRemainder "remainder's last step on parts remainderCore left: when twice the remainder passes |y| (or equals it with an odd quotient) take it from |y| and flip the sign; gives the quotient's low bits, moved on"
  input x machine.Address copied
  input y machine.Address copied
  input quotient Int64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  twice = partsNew()
  xHigh = highOf(x)
  xLow = lowOf(x)
  setSignificand(twice, xHigh, xLow)
  shiftUp(twice, 1)
  order = compareSignificands(twice, y)
  heap.give(twice)
  calc odd = (quotient & 1) == 1
  when order > 0 || (order == 0 && odd) flip keep
:flip
  remainder = partsNew()
  setSignificand(remainder, xHigh, xLow)
  yHigh = highOf(y)
  yLow = lowOf(y)
  setSignificand(x, yHigh, yLow)
  subtractSignificand(x, remainder)
  heap.give(remainder)
  sign = getPart(x, 0)
  setPart(x, 0, 1 - sign)
  calc moved = (quotient + 1) & 7
  return moved
:keep
  return quotient

op remainderLong "remainderl: x less the nearest whole multiple of y (ties to the even multiple), exactly"
  input left machine.LongDouble copied
  input right machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "remainderl"
:begin
  x = partsOf(left)
  y = partsOf(right)
  special = remainderSpecial(x, y)
  when special == 0 ordinary done
:ordinary
  quotient = remainderCore(x, y)
  nearestRemainder(x, y, quotient)
  settle(x, 0)
  goto done
:done
  heap.give(y)
  result = valueOf(x)
  return result

op remainderQuotientLong "remquol: remainderl, with the quotient's low three bits stored, signed as x / y"
  input left machine.LongDouble copied
  input right machine.LongDouble copied
  input quotientAt machine.Address copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "remquol"
  let bits Int64 0 mut
:begin
  x = partsOf(left)
  y = partsOf(right)
  xSign = getPart(x, 0)
  ySign = getPart(y, 0)
  special = remainderSpecial(x, y)
  when special == 0 ordinary store
:ordinary
  core = remainderCore(x, y)
  calc bits := nearestRemainder(x, y, core)
  settle(x, 0)
  goto store
:store
  calc signed = bits * (1 - 2 * choose(xSign != ySign, 1))
  machine.storeInt32(quotientAt, clibrary.lowInt32(signed))
  heap.give(y)
  result = valueOf(x)
  return result

## ---------------------------------------------------------------- the square root

op squareRootLong "sqrtl: the square root, correctly rounded as the rounding mode rounds, found bit by bit from the significand; -0 for -0, NaN with EDOM below zero"
  input value machine.LongDouble copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "sqrtl"
  let index Int64 0 mut
  let remainderHigh UInt64 0 mut
  let remainderLow UInt64 0 mut
  let rootHigh UInt64 0 mut
  let rootLow UInt64 0 mut
:begin
  parts = partsOf(value)
  kind = getPart(parts, 8)
  sign = getPart(parts, 0)
  when kind == 3 || kind == 0 || (kind == 2 && sign == 0) same notSame
:same
  result = valueOf(parts)
  return result
:notSame
  when sign == 1 negative positive
:negative
  clibrary.setErrno(33)
  setPart(parts, 8, 3)
  setSignificand(parts, 0, 0)
  nan = valueOf(parts)
  return nan
:positive
  normalize(parts)
  layout = format()
  precision = precisionOf(layout)
  power = getPart(parts, 16)
  calc odd = (power & 1) != 0
  when odd makeEven even
:makeEven
  shiftUp(parts, 1)
  setPart(parts, 16, power - 1)
  goto even
:even
  evenPower = getPart(parts, 16)
  high = highOf(parts)
  low = lowOf(parts)
  calc length = bitLength(high, low)
  calc pairs = (length + 1) / 2
  calc extra = precision + 2 - pairs
  calc rounds = pairs + extra
  goto eachPair
:eachPair loop=while max=rounds
  when index >= rounds finish digit
:digit in=eachPair
  calc bitAt = 2 * (pairs - 1 - index)
  calc pair = pairOf(high, low, bitAt)
  calc remainderHigh := (remainderHigh << 2) | (remainderLow >> 62)
  calc remainderLow := (remainderLow << 2) | pair
  calc trialHigh = (rootHigh << 2) | (rootLow >> 62)
  calc trialLow = (rootLow << 2) | 1
  calc fits = remainderHigh > trialHigh || (remainderHigh == trialHigh && remainderLow >= trialLow)
  calc rootHigh := (rootHigh << 1) | (rootLow >> 63)
  calc rootLow := rootLow << 1
  if fits take next
:take in=eachPair
  calc borrow = remainderLow < trialLow
  calc remainderLow := math.wrappingSubtractUInt64(remainderLow, trialLow)
  calc remainderHigh := remainderHigh - trialHigh - convert.int64ToUInt64(choose(borrow, 1))
  calc rootLow := rootLow | 1
  goto next
:next in=eachPair
  calc index := index + 1
  goto eachPair
:finish
  setSignificand(parts, rootHigh, rootLow)
  setPart(parts, 16, evenPower / 2 - extra)
  calc sticky = choose(remainderHigh != 0 || remainderLow != 0, 1)
  settle(parts, sticky)
  root = valueOf(parts)
  return root

op pairOf "The two bits of high * 2^64 + low from a position up (0 to 3), 0 below position 0"
  input high UInt64 copied
  input low UInt64 copied
  input position Int64 copied
  output UInt64
  let noPair UInt64 0
:begin
  when position < 0 below inside
:below
  return noPair
:inside
  when position >= 64 fromHigh notHigh
:fromHigh
  calc highPair = (high >> (position - 64)) & 3
  return highPair
:notHigh
  when position == 63 straddle fromLow
:straddle
  calc straddlePair = (low >> 63) | ((high & 1) << 1)
  return straddlePair
:fromLow
  calc lowPair = (low >> position) & 3
  return lowPair

@tests

op longOf "A double as this system's long double, exactly (made through parts, with no long double arithmetic)"
  input value Float64 copied
  output machine.LongDouble
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  cell = heap.take(16)
  machine.storeFloat64(cell, value)
  parts = partsNew()
  unpackAs(cell, parts, 0)
  heap.give(cell)
  kind = getPart(parts, 8)
  when kind == 1 finite done
:finite
  settle(parts, 0)
  goto done
:done
  result = valueOf(parts)
  return result

op sameLong "Whether two long doubles have the same bits"
  input left machine.LongDouble copied
  input right machine.LongDouble copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  leftCell = heap.take(16)
  rightCell = heap.take(16)
  machine.storeLongDouble(leftCell, left)
  machine.storeLongDouble(rightCell, right)
  order = machine.compare(leftCell, rightCell, 16)
  heap.give(leftCell)
  heap.give(rightCell)
  calc same = order == 0
  return same

op expectLong "Assert a long double is a double's value"
  input actual machine.LongDouble copied
  input expected Float64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  wanted = longOf(expected)
  same = sameLong(actual, wanted)
  test.assertTrue(same)
  return

test exactTest "The exact long double functions on this system's format: signs, frexpl and ldexpl, the whole-number family, modfl, fmodl, remainderl, remquol, sqrtl of squares, nextafterl both ways, nexttoward and nexttowardf, fmaxl and fminl with NaN, ilogbl"
  verifies format namesFormat
  verifies precisionOf countsBits
  verifies unpack readsParts
  verifies pack writesParts
  verifies partsNew givesZeroed
  verifies settle roundsToFormat
  verifies roundingMode readsMode
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  mode = roundingMode()
  test.assertEqualInt64(0, mode)
  layout = format()
  precision = precisionOf(layout)
  onLinux = system.posix()
  onArm = system.aarch64()
  calc expectedPrecision = 53 + choose(onLinux, 11) + choose(onLinux && onArm, 49)
  test.assertEqualInt64(expectedPrecision, precision)
  minusTwoHalf = longOf(-2.5)
  expectLong(absoluteLong(minusTwoHalf), 2.5)
  expectLong(copySignLong(longOf(3.0), longOf(-0.0)), -3.0)
  exponentCell = heap.take(8)
  fraction = splitLong(longOf(48.0), exponentCell)
  expectLong(fraction, 0.75)
  exponent = machine.loadInt32(exponentCell)
  test.assertTrue(exponent == 6)
  expectLong(loadExponentLong(longOf(0.75), 6), 48.0)
  expectLong(truncLong(minusTwoHalf), -2.0)
  expectLong(floorLong(minusTwoHalf), -3.0)
  expectLong(ceilLong(minusTwoHalf), -2.0)
  expectLong(roundHalfAwayLong(longOf(2.5)), 3.0)
  expectLong(rintLong(longOf(2.5)), 2.0)
  expectLong(rintLong(longOf(3.5)), 4.0)
  rounded = lrintLong(longOf(2.5))
  test.assertEqualInt64(2, rounded)
  away = lroundLong(minusTwoHalf)
  test.assertEqualInt64(-3, away)
  wholeCell = heap.take(16)
  part = splitWholeLong(longOf(-3.25), wholeCell)
  expectLong(part, -0.25)
  whole = machine.loadLongDouble(wholeCell)
  expectLong(whole, -3.0)
  expectLong(modLong(longOf(7.5), longOf(2.0)), 1.5)
  expectLong(remainderLong(longOf(7.5), longOf(2.0)), -0.5)
  quotientCell = heap.take(8)
  expectLong(remainderQuotientLong(longOf(7.5), longOf(2.0), quotientCell), -0.5)
  quotient = machine.loadInt32(quotientCell)
  test.assertTrue(quotient == 4)
  expectLong(squareRootLong(longOf(6.25)), 2.5)
  expectLong(squareRootLong(longOf(0.0)), 0.0)
  one = longOf(1.0)
  above = nextLong(one, longOf(2.0))
  differs = sameLong(above, one)
  test.assertTrue(!differs)
  expectLong(nextLong(above, longOf(0.0)), 1.0)
  nextDouble = nextTowardDouble(1.0, longOf(2.0))
  test.assertTrue(convert.float64BitsToUInt64(nextDouble) == 4607182418800017409)
  nextSingle = nextTowardFloat(convert.float64ToFloat32(1.0), longOf(0.0))
  test.assertTrue(convert.float32ToFloat64(nextSingle) == 0x1.fffffep-1)
  nan = notANumberLong(exponentCell)
  expectLong(largerLong(nan, longOf(-1.0)), -1.0)
  expectLong(smallerLong(longOf(2.0), longOf(-1.0)), -1.0)
  logarithm = exponentOfLong(longOf(48.0))
  test.assertTrue(logarithm == 5)
  roundTrip = partsNew()
  source = heap.take(16)
  machine.storeLongDouble(source, longOf(-0.375))
  unpack(source, roundTrip)
  settle(roundTrip, 0)
  copy = heap.take(16)
  pack(roundTrip, copy)
  order = machine.compare(source, copy, 16)
  test.assertTrue(order == 0)
  return

test partsTest "Parts by layout: the double layout's powers, parts and significand words read back, low bits and lengths of 128-bit significands, 3 settled and packed as a float and read back"
  verifies leastPower givesLeast
  verifies greatestPower givesGreatest
  verifies getPart readsPart
  verifies setPart writesPart
  verifies highOf readsHigh
  verifies lowOf readsLow
  verifies setSignificand writesSignificand
  verifies unpackAs readsLayout
  verifies packAs writesLayout
  verifies lowBitsSet seesLowBits
  verifies bitLength countsLength
  verifies settleAs roundsToLayout
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let topWord UInt64 1
  let lowWord UInt64 3
  let noWord UInt64 0
:begin
  least = leastPower(0)
  test.assertEqualInt64(-1074, least)
  greatest = greatestPower(0)
  test.assertEqualInt64(971, greatest)
  parts = partsNew()
  setPart(parts, 16, -3)
  power = getPart(parts, 16)
  test.assertEqualInt64(-3, power)
  setSignificand(parts, topWord, lowWord)
  high = highOf(parts)
  low = lowOf(parts)
  test.assertTrue(high == 1 && low == 3)
  inside = lowBitsSet(topWord, noWord, 65)
  test.assertTrue(inside)
  past = lowBitsSet(topWord, noWord, 64)
  test.assertTrue(!past)
  length = bitLength(topWord, noWord)
  test.assertEqualInt64(65, length)
  setSignificand(parts, noWord, lowWord)
  setPart(parts, 16, 0)
  setPart(parts, 8, 1)
  settleAs(parts, 0, 3)
  settledLow = lowOf(parts)
  settledPower = getPart(parts, 16)
  test.assertTrue(settledLow == 12582912)
  test.assertEqualInt64(-22, settledPower)
  cell = heap.take(16)
  packAs(parts, cell, 3)
  single = machine.loadInt32(cell)
  test.assertTrue(single == 1077936128)
  again = partsNew()
  unpackAs(cell, again, 3)
  againPower = getPart(again, 16)
  test.assertEqualInt64(-22, againPower)
  heap.give(again)
  heap.give(cell)
  heap.give(parts)
  return
