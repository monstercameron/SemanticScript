module cmathbits "math.h's exact functions (frexp, ldexp, scalbn, ilogb, logb, modf, rint, lrint, lround, remainder, remquo, fdim, fmax, fmin, fma, nan, nextafter, double and float forms) and fenv.h, as glibc gives them, bit for bit"
  path cmathbits
  imports standard.machine standard.system standard.string standard.math standard.compare standard.convert standard.bits standard.logic standard.test kernel clibrary
  exports none

capability memoryAccess "Authority to read and write the memory C callers hand the library, and this module's cells of machine.state" use machine.memory none

capability systemCalls "Authority to ask which machine the program was compiled for (fenv.h's constants and lrint's out-of-range results differ on AArch64)" use system.calls none

## Every function here is exact in IEEE arithmetic: its result is the one real number the definition names, rounded once
## (or not at all), so each gives glibc's bits, signed zeros and NaN payloads included. A float form widens its
## arguments to double (exactly), computes there, and narrows the result (exactly, or by the one rounding the C
## function does: fmaf rounds to 24 bits itself, never through a double).
##
## Methods: scalbn, remainder, and remquo follow the exact integer methods of fdlibm and musl (MIT); nan reads its tag as
## glibc's strtod does; fma is the hardware's fused multiply-add. fenv.h reads and writes the hardware's own
## floating-point state (see below), and rint, lrint, and the rest obey its rounding mode. The functions raise the
## flags glibc's raise and set errno through clibrary where glibc's do (ERANGE, EDOM). Bytes 24832 to 25087 of
## machine.state belong to this module: 24848 eight bytes where a Float32's bits are moved.
constant scratchAt "Where a Float32's bits are moved, in machine.state" Int64 24848

constant indexOne "The rounding mode index of downward" Int64 1

constant indexTwo "The rounding mode index of upward" Int64 2

constant okStatus "A successful status" Int32 0

constant refusedStatus "A refused status" Int32 1

constant rangeError "ERANGE: a result past what its type holds" Int32 34

constant domainError "EDOM: an argument outside the function's domain" Int32 33

constant forever "The bound of a loop that ends when its work does" Int64 9223372036854775807

## ---------------------------------------------------------------- small pieces

op bitLength "How many bits a whole number takes: 0 for 0, otherwise one more than the place of its highest set bit"
  input value UInt64 copied
  output Int64
  let rest UInt64 0 mut
  let count Int64 0 mut
:begin
  calc rest := value
  goto eachBit
:eachBit loop=while max=forever
  when rest == 0 done step
:step in=eachBit
  calc rest := rest >> 1
  calc count := count + 1
  goto eachBit
:done
  return count

op normalMantissa "A nonzero finite double's mantissa shifted up until its top bit is bit 52 (a subnormal's too)"
  input bits UInt64 copied
  output UInt64
:begin
  calc field = (bits >> 52) & 2047
  calc mantissa = bits & 0xfffffffffffff
  when field == 0 subnormal normal
:subnormal
  calc length = bitLength(mantissa)
  calc shifted = mantissa << (53 - length)
  return shifted
:normal
  calc withHidden = mantissa | 0x10000000000000
  return withHidden

op normalExponent "The biased exponent of normalMantissa: below 1 for a subnormal, so that value = mantissa * 2^(exponent - 1075)"
  input bits UInt64 copied
  output Int64
:begin
  calc field = convert.uint64BitsToInt64((bits >> 52) & 2047)
  calc mantissa = bits & 0xfffffffffffff
  when field == 0 subnormal normal
:subnormal
  calc length = bitLength(mantissa)
  calc lowered = length - 52
  return lowered
:normal
  return field

op singleBits "A Float32's bits as a whole number below 2^32"
  input value Float32 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  cell = kernel.stateAt(scratchAt)
  machine.storeFloat32(cell, value)
  raw = machine.loadInt32(cell)
  wide = convert.int32ToInt64(raw)
  calc masked = wide & 0xffffffff
  return masked

op singleFromBits "The Float32 whose bits are the low 32 of a whole number"
  input bits Int64 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
:begin
  low = clibrary.lowInt32(bits)
  cell = kernel.stateAt(scratchAt)
  machine.storeInt32(cell, low)
  value = machine.loadFloat32(cell)
  return value

op narrow "A double that a float holds exactly, or one that rounds to infinity or to a float, as a Float32 (infinity where convert would trap)"
  input value Float64 copied
  output Float32
:begin
  bits = convert.float64BitsToUInt64(value)
  calc magnitude = bits & 0x7fffffffffffffff
  calc overflow = magnitude >= 0x47effffff0000000 && magnitude < 0x7ff0000000000000
  when overflow toInfinity plain
:toInfinity
  calc infiniteBits = (bits & 0x8000000000000000) | 0x7ff0000000000000
  infinite = convert.uint64BitsToFloat64(infiniteBits)
  result = convert.float64ToFloat32(infinite)
  return result
:plain
  narrowed = convert.float64ToFloat32(value)
  return narrowed

op signedZero "A zero with the sign bit of a double's bits"
  input bits UInt64 copied
  output Float64
:begin
  calc zeroBits = bits & 0x8000000000000000
  zeroValue = convert.uint64BitsToFloat64(zeroBits)
  return zeroValue

## ---------------------------------------------------------------- scalbn

op scalbnCore "x times 2 to the n, rounded once to nearest even: a subnormal result is rounded as the hardware would, an overflow is an infinity; zero, infinity, and NaN give x + x"
  input x Float64 copied
  input n Int64 copied
  output Float64
  let amount Int64 0 mut
  let q UInt64 0 mut
  let unit UInt64 1
:begin
  bits = convert.float64BitsToUInt64(x)
  calc magnitude = bits & 0x7fffffffffffffff
  calc sign = bits & 0x8000000000000000
  calc field = convert.uint64BitsToInt64(magnitude >> 52)
  when magnitude == 0 passThrough checkField
:checkField
  when field == 2047 passThrough finite
:passThrough
  calc doubled = x + x
  return doubled
:finite
  calc mantissa = normalMantissa(bits)
  calc exponent = normalExponent(bits)
  calc amount := n
  when n > 5000 clampHigh checkLow
:clampHigh
  calc amount := 5000
  goto place
:checkLow
  when n < -5000 clampLow place
:clampLow
  calc amount := -5000
  goto place
:place
  calc k = exponent + amount
  when k >= 2047 overflow notOverflow
:overflow
  calc infiniteBits = sign | 0x7ff0000000000000
  infinite = convert.uint64BitsToFloat64(infiniteBits)
  return infinite
:notOverflow
  when k >= 1 normalResult subnormalResult
:normalResult
  calc resultBits = sign | (convert.int64BitsToUInt64(k) << 52) | (mantissa & 0xfffffffffffff)
  result = convert.uint64BitsToFloat64(resultBits)
  return result
:subnormalResult
  calc shift = 1 - k
  when shift >= 54 underflow round
:underflow
  tiny = signedZero(sign)
  return tiny
:round
  calc q := mantissa >> shift
  calc low = mantissa & ((unit << shift) - 1)
  calc half = unit << (shift - 1)
  calc up = low > half || (low == half && (q & 1) == 1)
  when up bump pack
:bump
  calc q := q + 1
  goto pack
:pack
  calc packed = sign | q
  value = convert.uint64BitsToFloat64(packed)
  return value

## ---------------------------------------------------------------- rounding to a whole number

op roundWith "A double rounded to a whole number by a mode: 0 to nearest even, 1 down, 2 up, 3 toward zero, 4 to nearest with halves away from zero; the sign of zero is kept"
  input x Float64 copied
  input mode Int64 copied
  output Float64
  let whole UInt64 0 mut
  let unit UInt64 1
:begin
  bits = convert.float64BitsToUInt64(x)
  calc magnitude = bits & 0x7fffffffffffffff
  calc sign = bits & 0x8000000000000000
  calc field = magnitude >> 52
  calc nearest = mode == 0
  calc down = mode == 1
  calc upward = mode == 2
  calc away = mode == 4
  when field >= 1075 large small
:large
  when field == 2047 special keepIt
:special
  calc doubled = x + x
  return doubled
:keepIt
  return x
:small
  when field < 1023 tiny fraction
:tiny
  when magnitude == 0 keepIt bumpTiny
:bumpTiny
  calc bumpNearest = nearest && magnitude > 0x3fe0000000000000
  calc bumpAway = away && magnitude >= 0x3fe0000000000000
  calc bumpDown = down && sign != 0
  calc bumpUp = upward && sign == 0
  calc bump = bumpNearest || bumpAway || bumpDown || bumpUp
  when bump toOne toZero
:toOne
  calc oneBits = sign | 0x3ff0000000000000
  oneValue = convert.uint64BitsToFloat64(oneBits)
  return oneValue
:toZero
  zeroValue = signedZero(bits)
  return zeroValue
:fraction
  calc shift = convert.uint64BitsToInt64(1075 - field)
  calc mantissa = (magnitude & 0xfffffffffffff) | 0x10000000000000
  calc whole := mantissa >> shift
  calc low = mantissa & ((unit << shift) - 1)
  calc half = unit << (shift - 1)
  calc odd = (whole & 1) == 1
  calc nonzero = low != 0
  calc bumpNear = nearest && (low > half || (low == half && odd))
  calc bumpHalf = away && low >= half
  calc bumpBelow = down && sign != 0 && nonzero
  calc bumpAbove = upward && sign == 0 && nonzero
  calc roundUp = bumpNear || bumpHalf || bumpBelow || bumpAbove
  when roundUp plusOne finish
:plusOne
  calc whole := whole + 1
  goto finish
:finish
  asFloat = convert.int64ToFloat64(convert.uint64BitsToInt64(whole))
  floatBits = convert.float64BitsToUInt64(asFloat)
  calc signed = floatBits | sign
  result = convert.uint64BitsToFloat64(signed)
  return result

## ---------------------------------------------------------------- the floating-point environment (fenv.h)
##
## The hardware's own state, through machine.loadFloatControl and machine.storeFloatControl: on x86_64 MXCSR in the
## low 32 bits (flags IE 1, DE 2, ZE 4, OE 8, UE 16, PE 32; rounding control in bits 13 and 14), on AArch64 FPCR in
## the low and FPSR in the high 32 bits (flags IOC 1, DZC 2, OFC 4, UFC 8, IXC 16 in FPSR; RMode in FPCR bits 22
## and 23). glibc's FE_ constants are the target's own: x86_64 invalid 1, divide by zero 4, overflow 8, underflow 16,
## inexact 32 (FE_ALL_EXCEPT 0x3d: the denormal flag is not one of them), rounding to nearest 0, downward 0x400, upward
## 0x800, toward zero 0xc00; AArch64 1, 2, 4, 8, 16 (all 0x1f), and nearest 0, upward 0x400000, downward 0x800000,
## toward zero 0xc00000. Only the SSE state is mirrored on x86_64 (what compiled floating-point code uses); the x87
## status of fenv_t is written as a fresh x87 would have it and never read back.

op flagConstant "The target's FE_ constant of a flag: 0 invalid, 1 divide by zero, 2 overflow, 3 underflow, 4 inexact"
  input kind Int64 copied
  output Int64
  effect use system.calls
  uses systemCalls
:begin
  onArm = system.aarch64()
  when onArm arm x86
:arm
  calc armCode = 1 << kind
  return armCode
:x86
  when kind == 0 invalid others
:invalid
  calc invalidCode = 1 << kind
  return invalidCode
:others
  calc x86Code = 1 << (kind + 1)
  return x86Code

op allFlags "FE_ALL_EXCEPT: the five flags in the target's numbering"
  output Int64
  effect use system.calls
  uses systemCalls
:begin
  calc every = flagConstant(0) | flagConstant(1) | flagConstant(2) | flagConstant(3) | flagConstant(4)
  return every

op raisedFlags "The exception flags now raised, as the target's FE_ constants"
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  control = machine.loadFloatControl()
  every = allFlags()
  onArm = system.aarch64()
  when onArm arm x86
:arm
  calc armFlags = convert.uint64BitsToInt64(control >> 32) & every
  return armFlags
:x86
  calc x86Flags = convert.uint64BitsToInt64(control & 0xffffffff) & every
  return x86Flags

op changeFlags "Lower the exception flags of one set of FE_ constants and then raise those of another (numbers outside FE_ALL_EXCEPT are ignored)"
  input lowered Int64 copied
  input raised Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  control = machine.loadFloatControl()
  every = allFlags()
  calc lowerBits = convert.int64BitsToUInt64(lowered & every)
  calc raiseBits = convert.int64BitsToUInt64(raised & every)
  onArm = system.aarch64()
  when onArm arm x86
:arm
  calc armNext = (control & ~(lowerBits << 32)) | (raiseBits << 32)
  machine.storeFloatControl(armNext)
  return
:x86
  calc x86Next = (control & ~lowerBits) | raiseBits
  machine.storeFloatControl(x86Next)
  return

op raiseFlags "Raise exception flags, as arithmetic that signals them would"
  input flags Int64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  changeFlags(0, flags)
  return

op currentMode "The hardware's rounding mode: 0 to nearest, 1 down, 2 up, 3 toward zero"
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  control = machine.loadFloatControl()
  onArm = system.aarch64()
  when onArm arm x86
:x86
  calc x86Mode = convert.uint64BitsToInt64((control >> 13) & 3)
  return x86Mode
:arm
  calc field = convert.uint64BitsToInt64((control >> 22) & 3)
  when field == 1 armUp checkDown
:armUp
  return indexTwo
:checkDown
  when field == 2 armDown armSame
:armDown
  return indexOne
:armSame
  return field

op externalMode "The hardware's rounding mode as the target's FE_ constant"
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  control = machine.loadFloatControl()
  onArm = system.aarch64()
  when onArm arm x86
:arm
  calc armMode = convert.uint64BitsToInt64(control & 0xc00000)
  return armMode
:x86
  calc x86Mode = convert.uint64BitsToInt64((control >> 3) & 0xc00)
  return x86Mode

op changeMode "Set the hardware's rounding mode to an FE_ constant; false (and no change) for a number that is no mode"
  input mode Int64 copied
  output Bool
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let yes Bool true
  let no Bool false
:begin
  control = machine.loadFloatControl()
  onArm = system.aarch64()
  when onArm arm x86
:arm
  calc armValid = mode == 0 || mode == 0x400000 || mode == 0x800000 || mode == 0xc00000
  calc armField = convert.int64BitsToUInt64(mode)
  calc armNext = (control & ~0xc00000) | armField
  when armValid armApply refuse
:armApply
  machine.storeFloatControl(armNext)
  return yes
:x86
  calc x86Valid = mode == 0 || mode == 0x400 || mode == 0x800 || mode == 0xc00
  calc x86Field = convert.int64BitsToUInt64(mode) << 3
  calc x86Next = (control & ~0x6000) | x86Field
  when x86Valid x86Apply refuse
:x86Apply
  machine.storeFloatControl(x86Next)
  return yes
:refuse
  return no

op saveEnvironment "Store the floating-point environment as glibc's fenv_t holds it: x86_64's 28 bytes of x87 environment (a fresh one) and MXCSR, AArch64's FPCR and FPSR"
  input envp machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  control = machine.loadFloatControl()
  onArm = system.aarch64()
  when onArm arm x86
:arm
  low = clibrary.lowInt32(convert.uint64BitsToInt64(control & 0xffffffff))
  high = clibrary.lowInt32(convert.uint64BitsToInt64(control >> 32))
  machine.storeInt32(envp, low)
  machine.storeInt32(envp + 4, high)
  return
:x86
  mxcsr = clibrary.lowInt32(convert.uint64BitsToInt64(control & 0xffffffff))
  machine.storeInt32(envp, 895)
  machine.storeInt32(envp + 4, 0)
  machine.storeInt32(envp + 8, 65535)
  machine.storeInt32(envp + 12, 0)
  machine.storeInt32(envp + 16, 0)
  machine.storeInt32(envp + 20, 0)
  machine.storeInt32(envp + 24, 0)
  machine.storeInt32(envp + 28, mxcsr)
  return

op loadEnvironment "Set the floating-point environment from a fenv_t, or to the default for FE_DFL_ENV (-1) and FE_NOMASK_ENV (-2, whose unmasked exceptions are not taken: it is the default)"
  input envp machine.Address copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  address = machine.toInt64(envp)
  onArm = system.aarch64()
  calc isDefault = address == -1 || address == -2
  when onArm arm x86
:arm
  when isDefault armDefault armRead
:armDefault
  machine.storeFloatControl(0)
  return
:armRead
  low = machine.loadInt32(envp)
  high = machine.loadInt32(envp + 4)
  calc armControl = convert.int64BitsToUInt64(convert.int32ToInt64(low) & 0xffffffff) | (convert.int64BitsToUInt64(convert.int32ToInt64(high) & 0xffffffff) << 32)
  machine.storeFloatControl(armControl)
  return
:x86
  when isDefault x86Default x86Read
:x86Default
  machine.storeFloatControl(0x1f80)
  return
:x86Read
  mxcsr = machine.loadInt32(envp + 28)
  calc x86Control = convert.int64BitsToUInt64(convert.int32ToInt64(mxcsr) & 0xffffffff)
  machine.storeFloatControl(x86Control)
  return

op toLong "A rounded double as a long, raising invalid when it does not fit (x86_64's cvtsd2si gives the least long for NaN and out of range, AArch64 saturates and gives 0 for NaN) and inexact when asked and the rounding changed it"
  input rounded Float64 copied
  input original Float64 copied
  input signalsInexact Bool copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let lowestLong Int64 -9223372036854775808
  let highestLong Int64 9223372036854775807
  let zeroLong Int64 0
:begin
  calc inRange = rounded >= -9223372036854775808.0 && rounded < 9223372036854775808.0
  when inRange fits outside
:fits
  when signalsInexact checkChange convertIt
:checkChange
  when rounded == original convertIt raiseInexact
:raiseInexact
  raiseFlags(flagConstant(4))
  goto convertIt
:convertIt
  value = convert.float64ToInt64(rounded)
  return value
:outside
  raiseFlags(flagConstant(0))
  onArm = system.aarch64()
  when onArm saturate least
:least
  return lowestLong
:saturate
  when !(rounded == rounded) zeroResult signed
:zeroResult
  return zeroLong
:signed
  when rounded > 0.0 highest least
:highest
  return highestLong

op rintSignals "Raise inexact when rint changed a finite number"
  input x Float64 copied
  input result Float64 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc changed = x == x && !(result == x)
  when changed raise done
:raise
  raiseFlags(flagConstant(4))
  return
:done
  return

op ilogbSignals "ilogb of 0, infinity, or NaN raises invalid and sets EDOM"
  input result Int32 copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
:begin
  calc wide = convert.int32ToInt64(result)
  calc special = wide == -2147483648 || wide == 2147483647
  when special raise done
:raise
  raiseFlags(flagConstant(0))
  clibrary.setErrno(domainError)
  return
:done
  return

op domainSignals "remainder and remquo of y 0 or x infinite, neither NaN, set EDOM (their arithmetic raised invalid)"
  input x Float64 copied
  input y Float64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  xb = convert.float64BitsToUInt64(x)
  yb = convert.float64BitsToUInt64(y)
  calc xm = xb & 0x7fffffffffffffff
  calc ym = yb & 0x7fffffffffffffff
  calc bad = (ym == 0 || xm == 0x7ff0000000000000) && xm <= 0x7ff0000000000000 && ym <= 0x7ff0000000000000
  when bad domain done
:domain
  clibrary.setErrno(domainError)
  return
:done
  return

op rangeSignals "A result that is infinity from finite operands sets ERANGE"
  input result Float64 copied
  input x Float64 copied
  input y Float64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  rb = convert.float64BitsToUInt64(result)
  xb = convert.float64BitsToUInt64(x)
  yb = convert.float64BitsToUInt64(y)
  calc finite = (xb & 0x7fffffffffffffff) < 0x7ff0000000000000 && (yb & 0x7fffffffffffffff) < 0x7ff0000000000000
  calc overflowed = (rb & 0x7fffffffffffffff) == 0x7ff0000000000000 && finite
  when overflowed range done
:range
  clibrary.setErrno(rangeError)
  return
:done
  return

op scaleSignals "The flags and errno of ldexp and scalbn: overflow and inexact for an infinity from a finite number, underflow and inexact for a tiny inexact result, and (ldexp) ERANGE for an infinity or a zero"
  input x Float64 copied
  input result Float64 copied
  input n Int64 copied
  input tiny Float64 copied
  input setsErrno Bool copied
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  let reverse Int64 0 mut
:begin
  xb = convert.float64BitsToUInt64(x)
  rb = convert.float64BitsToUInt64(result)
  calc xm = xb & 0x7fffffffffffffff
  calc rm = rb & 0x7fffffffffffffff
  when xm == 0 || xm >= 0x7ff0000000000000 done check
:check
  when rm >= 0x7ff0000000000000 overflow checkTiny
:overflow
  raiseFlags(flagConstant(2) | flagConstant(4))
  goto errnoCheck
:checkTiny
  absolute = convert.uint64BitsToFloat64(rm)
  when absolute < tiny underflow errnoCheck
:underflow
  when n > 5000 reverseLow checkLow
:reverseLow
  calc reverse := -5000
  goto compareBack
:checkLow
  when n < -5000 reverseHigh reverseExact
:reverseHigh
  calc reverse := 5000
  goto compareBack
:reverseExact
  calc reverse := 0 - n
  goto compareBack
:compareBack
  back = scalbnCore(result, reverse)
  when back == x errnoCheck inexact
:inexact
  raiseFlags(flagConstant(3) | flagConstant(4))
  goto errnoCheck
:errnoCheck
  calc ranged = setsErrno && (rm == 0 || rm >= 0x7ff0000000000000)
  when ranged range done
:range
  clibrary.setErrno(rangeError)
  return
:done
  return


## ---------------------------------------------------------------- remainder and remquo

op storeQuotient "Store the quotient's low bits as an int where remquo's caller asked (not when the address is 0)"
  input quoAt machine.Address copied
  input quotient Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  nowhere = machine.zero()
  when quoAt == nowhere skip store
:store
  narrowed = clibrary.lowInt32(quotient)
  machine.storeInt32(quoAt, narrowed)
  return
:skip
  return

op remainderCore "IEEE remainder x - n*y, n the nearest whole number to x/y (halves to even), exact; with an address for remquo, the sign of x/y with the low 3 bits of n (8 where glibc gives 8 for a quotient that is a multiple of 8 rounded up)"
  input x Float64 copied
  input y Float64 copied
  input quoAt machine.Address copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  let ax UInt64 0 mut
  let ay UInt64 0 mut
  let ex Int64 0 mut
  let ey Int64 0 mut
  let q UInt64 0 mut
  let steps Int64 0 mut
  let mm UInt64 0 mut
  let low UInt64 0 mut
  let flip UInt64 0 mut
  let signedQuotient Int64 0 mut
:begin
  xb = convert.float64BitsToUInt64(x)
  yb = convert.float64BitsToUInt64(y)
  calc xm = xb & 0x7fffffffffffffff
  calc ym = yb & 0x7fffffffffffffff
  calc xField = convert.uint64BitsToInt64(xm >> 52)
  calc yField = convert.uint64BitsToInt64(ym >> 52)
  calc invalid = ym == 0 || ym > 0x7ff0000000000000 || xField == 2047
  when invalid makeNan checkZero
:makeNan
  calc product = x * y
  calc nanValue = product / product
  return nanValue
:checkZero
  when xm == 0 giveX checkInfinity
:checkInfinity
  when yField == 2047 giveX normalize
:giveX
  storeQuotient(quoAt, 0)
  return x
:normalize
  calc ax := normalMantissa(xb)
  calc ex := normalExponent(xb)
  calc ay := normalMantissa(yb)
  calc ey := normalExponent(yb)
  when ex < ey - 1 giveX near
:near
  when ex == ey - 1 adjacent divide
:adjacent
  calc ay := ay * 2
  calc ey := ex
  goto decide
:divide
  calc steps := ex - ey
  goto eachStep
:eachStep loop=while max=forever
  when steps == 0 lastStep step
:step in=eachStep
  when ax >= ay takeOne takeZero
:takeOne in=eachStep
  calc ax := (ax - ay) << 1
  calc q := (q << 1) | 1
  goto stepped
:takeZero in=eachStep
  calc ax := ax << 1
  calc q := q << 1
  goto stepped
:stepped in=eachStep
  calc steps := steps - 1
  goto eachStep
:lastStep
  when ax >= ay lastOne lastZero
:lastOne
  calc ax := ax - ay
  calc q := (q << 1) | 1
  goto decide
:lastZero
  calc q := q << 1
  goto decide
:decide
  calc twice = ax * 2
  calc odd = (q & 1) == 1
  calc roundUp = twice > ay || (twice == ay && odd)
  calc mm := ax
  calc low := q & 7
  when roundUp reduceUp finish
:reduceUp
  calc mm := ay - ax
  calc flip := 1
  calc low := ((q & 7) + 1) & 7
  when low == 0 eight finish
:eight
  calc low := 8
  goto finish
:finish
  calc lowLong = convert.uint64BitsToInt64(low)
  calc signedQuotient := lowLong
  when ((xb ^ yb) >> 63) == 1 negate report
:negate
  calc signedQuotient := 0 - lowLong
  goto report
:report
  storeQuotient(quoAt, signedQuotient)
  when mm == 0 zeroResult nonzero
:zeroResult
  zeroValue = signedZero(xb)
  return zeroValue
:nonzero
  asFloat = convert.int64ToFloat64(convert.uint64BitsToInt64(mm))
  value = scalbnCore(asFloat, ey - 1075)
  valueBits = convert.float64BitsToUInt64(value)
  calc resultSign = ((xb >> 63) ^ flip) << 63
  calc resultBits = valueBits | resultSign
  result = convert.uint64BitsToFloat64(resultBits)
  return result

## ---------------------------------------------------------------- frexp, ldexp, scalbn, ilogb, logb, modf

op frexpDouble "frexp: x as a fraction of magnitude in [0.5, 1) times 2 to a power, which is stored through the pointer; 0, infinity, and NaN give x + x and the power 0"
  invariant splitsFraction "Gives a fraction of magnitude in [0.5, 1) and stores the power of two that restores x"
  input x Float64 copied
  input exponentAt machine.Address copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "frexp"
:begin
  bits = convert.float64BitsToUInt64(x)
  calc magnitude = bits & 0x7fffffffffffffff
  when magnitude >= 0x7ff0000000000000 || magnitude == 0 passThrough scale
:passThrough
  machine.storeInt32(exponentAt, 0)
  calc doubled = x + x
  return doubled
:scale
  calc mantissa = normalMantissa(bits)
  calc exponent = normalExponent(bits)
  calc fractionBits = (bits & 0x8000000000000000) | 0x3fe0000000000000 | (mantissa & 0xfffffffffffff)
  fraction = convert.uint64BitsToFloat64(fractionBits)
  stored = clibrary.lowInt32(exponent - 1022)
  machine.storeInt32(exponentAt, stored)
  return fraction

op frexpSingle "frexpf: frexp of a float"
  input x Float32 copied
  input exponentAt machine.Address copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "frexpf"
:begin
  wide = convert.float32ToFloat64(x)
  result = frexpDouble(wide, exponentAt)
  narrowed = narrow(result)
  return narrowed

op ldexpDouble "ldexp: x times 2 to the n; ERANGE when a finite nonzero x gives infinity or zero"
  invariant scalesExactly "Gives x times 2 to the n rounded once, to a subnormal or to infinity when it must be"
  input x Float64 copied
  input n Int32 copied
  output Float64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "ldexp"
  let tinyBits UInt64 4503599627370496
  let yes Bool true
:begin
  tinyLimit = convert.uint64BitsToFloat64(tinyBits)
  amount = convert.int32ToInt64(n)
  result = scalbnCore(x, amount)
  scaleSignals(x, result, amount, tinyLimit, yes)
  return result

op ldexpSingle "ldexpf: x times 2 to the n; ERANGE when a finite nonzero x gives infinity or zero"
  input x Float32 copied
  input n Int32 copied
  output Float32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "ldexpf"
  let tinyBits UInt64 4039728865751334912
  let yes Bool true
:begin
  tinyLimit = convert.uint64BitsToFloat64(tinyBits)
  wide = convert.float32ToFloat64(x)
  amount = convert.int32ToInt64(n)
  result = scalbnCore(wide, amount)
  narrowed = narrow(result)
  back = convert.float32ToFloat64(narrowed)
  scaleSignals(wide, back, amount, tinyLimit, yes)
  return narrowed

op scalbnDouble "scalbn: x times 2 to the n"
  input x Float64 copied
  input n Int32 copied
  output Float64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "scalbn"
  let tinyBits UInt64 4503599627370496
  let no Bool false
:begin
  tinyLimit = convert.uint64BitsToFloat64(tinyBits)
  amount = convert.int32ToInt64(n)
  result = scalbnCore(x, amount)
  scaleSignals(x, result, amount, tinyLimit, no)
  return result

op scalbnSingle "scalbnf: x times 2 to the n"
  input x Float32 copied
  input n Int32 copied
  output Float32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "scalbnf"
  let tinyBits UInt64 4039728865751334912
  let no Bool false
:begin
  tinyLimit = convert.uint64BitsToFloat64(tinyBits)
  wide = convert.float32ToFloat64(x)
  amount = convert.int32ToInt64(n)
  result = scalbnCore(wide, amount)
  narrowed = narrow(result)
  back = convert.float32ToFloat64(narrowed)
  scaleSignals(wide, back, amount, tinyLimit, no)
  return narrowed

op scalblnDouble "scalbln: x times 2 to the n, n a long"
  input x Float64 copied
  input n Int64 copied
  output Float64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "scalbln"
  let tinyBits UInt64 4503599627370496
  let no Bool false
:begin
  tinyLimit = convert.uint64BitsToFloat64(tinyBits)
  result = scalbnCore(x, n)
  scaleSignals(x, result, n, tinyLimit, no)
  return result

op scalblnSingle "scalblnf: x times 2 to the n, n a long"
  input x Float32 copied
  input n Int64 copied
  output Float32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "scalblnf"
  let tinyBits UInt64 4039728865751334912
  let no Bool false
:begin
  tinyLimit = convert.uint64BitsToFloat64(tinyBits)
  wide = convert.float32ToFloat64(x)
  result = scalbnCore(wide, n)
  narrowed = narrow(result)
  back = convert.float32ToFloat64(narrowed)
  scaleSignals(wide, back, n, tinyLimit, no)
  return narrowed

op ilogbCore "The unbiased exponent of a double as an int: the least int for 0 and for NaN, the greatest for infinity (x86_64's FP_ILOGB0, FP_ILOGBNAN, and INT_MAX)"
  input x Float64 copied
  output Int32
  let leastInt Int32 -2147483648
  let greatestInt Int32 2147483647
:begin
  bits = convert.float64BitsToUInt64(x)
  calc magnitude = bits & 0x7fffffffffffffff
  when magnitude == 0 least checkSpecial
:checkSpecial
  when magnitude > 0x7ff0000000000000 least checkInfinite
:checkInfinite
  when magnitude == 0x7ff0000000000000 greatest finite
:least
  return leastInt
:greatest
  return greatestInt
:finite
  calc exponent = normalExponent(bits) - 1023
  narrowed = clibrary.lowInt32(exponent)
  return narrowed

op ilogbDouble "ilogb: the unbiased exponent of x as an int; EDOM and the invalid flag for 0, infinity, and NaN"
  invariant givesExponent "Gives the unbiased exponent, the least int for 0 and NaN, the greatest for infinity"
  input x Float64 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "ilogb"
:begin
  result = ilogbCore(x)
  ilogbSignals(result)
  return result

op ilogbSingle "ilogbf: the unbiased exponent of x as an int; EDOM and the invalid flag for 0, infinity, and NaN"
  input x Float32 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "ilogbf"
:begin
  wide = convert.float32ToFloat64(x)
  result = ilogbCore(wide)
  ilogbSignals(result)
  return result

op logbCore "The unbiased exponent of a double as a double: -1 / |x| (-infinity, with the divide-by-zero flag) for 0, x * x (infinity, or NaN as it was) for infinity and NaN"
  input x Float64 copied
  output Float64
  let minusOne Float64 -1.0
:begin
  bits = convert.float64BitsToUInt64(x)
  calc magnitude = bits & 0x7fffffffffffffff
  when magnitude == 0 minusInfinity checkSpecial
:minusInfinity
  absolute = convert.uint64BitsToFloat64(magnitude)
  calc negative = minusOne / absolute
  return negative
:checkSpecial
  when magnitude >= 0x7ff0000000000000 special finite
:special
  calc squared = x * x
  return squared
:finite
  calc exponent = normalExponent(bits) - 1023
  result = convert.int64ToFloat64(exponent)
  return result

op logbDouble "logb: the unbiased exponent of x as a double"
  input x Float64 copied
  output Float64
  abi library "logb"
:begin
  result = logbCore(x)
  return result

op logbSingle "logbf: the unbiased exponent of x as a float"
  input x Float32 copied
  output Float32
  abi library "logbf"
:begin
  wide = convert.float32ToFloat64(x)
  result = logbCore(wide)
  narrowed = narrow(result)
  return narrowed

op fractionCore "modf's fractional part of a double given its whole part: the sign of x on a zero, x + x for NaN"
  input x Float64 copied
  input whole Float64 copied
  output Float64
:begin
  bits = convert.float64BitsToUInt64(x)
  when !(x == x) nanCase checkWhole
:nanCase
  calc doubled = x + x
  return doubled
:checkWhole
  when whole == x zeroCase fractional
:zeroCase
  zeroValue = signedZero(bits)
  return zeroValue
:fractional
  calc difference = x - whole
  return difference

op modfDouble "modf: the fraction of x (with its sign) is returned and the whole part, toward zero, stored through the pointer"
  invariant splitsWhole "Gives the fraction with the sign of x and stores the whole part toward zero"
  input x Float64 copied
  input wholeAt machine.Address copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "modf"
:begin
  whole = roundWith(x, 3)
  machine.storeFloat64(wholeAt, whole)
  fraction = fractionCore(x, whole)
  return fraction

op modfSingle "modff: the fraction of x is returned and the whole part, toward zero, stored through the pointer"
  input x Float32 copied
  input wholeAt machine.Address copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "modff"
:begin
  wide = convert.float32ToFloat64(x)
  whole = roundWith(wide, 3)
  wholeSingle = narrow(whole)
  machine.storeFloat32(wholeAt, wholeSingle)
  fraction = fractionCore(wide, whole)
  narrowed = narrow(fraction)
  return narrowed

## ---------------------------------------------------------------- rint, nearbyint, lrint, lround

op rintDouble "rint: x rounded to a whole number in the current rounding mode, raising inexact when that changes it"
  invariant roundsToMode "Rounds to a whole number in the current mode, halves to even in the default one"
  input x Float64 copied
  output Float64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "rint"
:begin
  mode = currentMode()
  result = roundWith(x, mode)
  rintSignals(x, result)
  return result

op rintSingle "rintf: x rounded to a whole number in the current rounding mode, raising inexact when that changes it"
  input x Float32 copied
  output Float32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "rintf"
:begin
  wide = convert.float32ToFloat64(x)
  mode = currentMode()
  result = roundWith(wide, mode)
  rintSignals(wide, result)
  narrowed = narrow(result)
  return narrowed

op nearbyintDouble "nearbyint: x rounded to a whole number in the current rounding mode, never raising inexact"
  input x Float64 copied
  output Float64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "nearbyint"
:begin
  mode = currentMode()
  result = roundWith(x, mode)
  return result

op nearbyintSingle "nearbyintf: x rounded to a whole number in the current rounding mode, never raising inexact"
  input x Float32 copied
  output Float32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "nearbyintf"
:begin
  wide = convert.float32ToFloat64(x)
  mode = currentMode()
  result = roundWith(wide, mode)
  narrowed = narrow(result)
  return narrowed

op lrintDouble "lrint: x rounded in the current mode, as a long"
  input x Float64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "lrint"
  let yes Bool true
:begin
  mode = currentMode()
  rounded = roundWith(x, mode)
  result = toLong(rounded, x, yes)
  return result

op lrintSingle "lrintf: x rounded in the current mode, as a long"
  input x Float32 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "lrintf"
  let yes Bool true
:begin
  wide = convert.float32ToFloat64(x)
  mode = currentMode()
  rounded = roundWith(wide, mode)
  result = toLong(rounded, wide, yes)
  return result

op llrintDouble "llrint: x rounded in the current mode, as a long long"
  input x Float64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "llrint"
  let yes Bool true
:begin
  mode = currentMode()
  rounded = roundWith(x, mode)
  result = toLong(rounded, x, yes)
  return result

op llrintSingle "llrintf: x rounded in the current mode, as a long long"
  input x Float32 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "llrintf"
  let yes Bool true
:begin
  wide = convert.float32ToFloat64(x)
  mode = currentMode()
  rounded = roundWith(wide, mode)
  result = toLong(rounded, wide, yes)
  return result

op lroundDouble "lround: x rounded to the nearest whole number, halves away from zero, as a long"
  input x Float64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "lround"
  let no Bool false
:begin
  rounded = roundWith(x, 4)
  result = toLong(rounded, x, no)
  return result

op lroundSingle "lroundf: x rounded to the nearest whole number, halves away from zero, as a long"
  input x Float32 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "lroundf"
  let no Bool false
:begin
  wide = convert.float32ToFloat64(x)
  rounded = roundWith(wide, 4)
  result = toLong(rounded, wide, no)
  return result

op llroundDouble "llround: x rounded to the nearest whole number, halves away from zero, as a long long"
  input x Float64 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "llround"
  let no Bool false
:begin
  rounded = roundWith(x, 4)
  result = toLong(rounded, x, no)
  return result

op llroundSingle "llroundf: x rounded to the nearest whole number, halves away from zero, as a long long"
  input x Float32 copied
  output Int64
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "llroundf"
  let no Bool false
:begin
  wide = convert.float32ToFloat64(x)
  rounded = roundWith(wide, 4)
  result = toLong(rounded, wide, no)
  return result

## ---------------------------------------------------------------- remainder, remquo

op remainderDouble "remainder: x - n*y for the whole number n nearest x/y (halves to even), exactly; EDOM for y 0 or x infinite"
  invariant remaindersExactly "Gives x - n*y exactly for the whole number n nearest x/y"
  input x Float64 copied
  input y Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "remainder"
:begin
  nowhere = machine.zero()
  result = remainderCore(x, y, nowhere)
  domainSignals(x, y)
  return result

op remainderSingle "remainderf: x - n*y for the whole number n nearest x/y (halves to even), exactly; EDOM for y 0 or x infinite"
  input x Float32 copied
  input y Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "remainderf"
:begin
  nowhere = machine.zero()
  wideX = convert.float32ToFloat64(x)
  wideY = convert.float32ToFloat64(y)
  result = remainderCore(wideX, wideY, nowhere)
  domainSignals(wideX, wideY)
  narrowed = narrow(result)
  return narrowed

op remquoDouble "remquo: remainder, and through the pointer the sign of x/y with the low bits of the quotient"
  input x Float64 copied
  input y Float64 copied
  input quoAt machine.Address copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "remquo"
:begin
  result = remainderCore(x, y, quoAt)
  domainSignals(x, y)
  return result

op remquoSingle "remquof: remainderf, and through the pointer the sign of x/y with the low bits of the quotient"
  input x Float32 copied
  input y Float32 copied
  input quoAt machine.Address copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "remquof"
:begin
  wideX = convert.float32ToFloat64(x)
  wideY = convert.float32ToFloat64(y)
  result = remainderCore(wideX, wideY, quoAt)
  domainSignals(wideX, wideY)
  narrowed = narrow(result)
  return narrowed

## ---------------------------------------------------------------- fdim, fmax, fmin, fma

op fdimDouble "fdim: x - y when x is greater than y (or either is NaN), otherwise 0; ERANGE when it overflows"
  input x Float64 copied
  input y Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "fdim"
:begin
  result = fdimCore(x, y)
  rangeSignals(result, x, y)
  return result

op fdimSingle "fdimf: x - y when x is greater than y (or either is NaN), otherwise 0; ERANGE when it overflows"
  input x Float32 copied
  input y Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "fdimf"
:begin
  result = fdimSingleCore(x, y)
  wideResult = convert.float32ToFloat64(result)
  wideX = convert.float32ToFloat64(x)
  wideY = convert.float32ToFloat64(y)
  rangeSignals(wideResult, wideX, wideY)
  return result

op fmaxDouble "fmax: the greater of two, the other if one is NaN, x if both are"
  input x Float64 copied
  input y Float64 copied
  output Float64
  abi library "fmax"
:begin
  calc takeX = x >= y || !(y == y)
  when takeX giveX giveY
:giveX
  return x
:giveY
  return y

op fmaxSingle "fmaxf: the greater of two, the other if one is NaN, x if both are"
  input x Float32 copied
  input y Float32 copied
  output Float32
  abi library "fmaxf"
:begin
  calc takeX = x >= y || !(y == y)
  when takeX giveX giveY
:giveX
  return x
:giveY
  return y

op fminDouble "fmin: the lesser of two, the other if one is NaN, x if both are"
  input x Float64 copied
  input y Float64 copied
  output Float64
  abi library "fmin"
:begin
  calc takeX = x <= y || !(y == y)
  when takeX giveX giveY
:giveX
  return x
:giveY
  return y

op fminSingle "fminf: the lesser of two, the other if one is NaN, x if both are"
  input x Float32 copied
  input y Float32 copied
  output Float32
  abi library "fminf"
:begin
  calc takeX = x <= y || !(y == y)
  when takeX giveX giveY
:giveX
  return x
:giveY
  return y

op fmaDouble "fma: x * y + z, rounded once (the hardware's fused multiply-add)"
  invariant roundsOnce "Gives x*y+z rounded once"
  input x Float64 copied
  input y Float64 copied
  input z Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "fma"
:begin
  result = machine.fusedMultiplyAdd(x, y, z)
  return result

op fmaSingle "fmaf: x * y + z, rounded once to a float (the hardware's fused multiply-add)"
  input x Float32 copied
  input y Float32 copied
  input z Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "fmaf"
:begin
  result = machine.fusedMultiplyAdd32(x, y, z)
  return result

## ---------------------------------------------------------------- nextafter

op nextafterCore "nextafter: the double next to x toward y; y when they are equal, x + y when either is NaN"
  input x Float64 copied
  input y Float64 copied
  output Float64
:begin
  xb = convert.float64BitsToUInt64(x)
  yb = convert.float64BitsToUInt64(y)
  calc unordered = !(x == x) || !(y == y)
  when unordered sum checkEqual
:sum
  calc total = x + y
  return total
:checkEqual
  when x == y giveY checkZero
:giveY
  return y
:checkZero
  when (xb & 0x7fffffffffffffff) == 0 fromZero step
:fromZero
  calc smallest = (yb & 0x8000000000000000) | 1
  tiny = convert.uint64BitsToFloat64(smallest)
  return tiny
:step
  calc positive = x > 0.0
  calc rising = x < y
  calc away = (rising && positive) || (!rising && !positive)
  when away up down
:up
  calc upBits = xb + 1
  upValue = convert.uint64BitsToFloat64(upBits)
  return upValue
:down
  calc downBits = xb - 1
  downValue = convert.uint64BitsToFloat64(downBits)
  return downValue

op nextafterDouble "nextafter: the double next to x toward y; ERANGE when it overflows"
  invariant stepsOneUnit "Gives the double next to x toward y"
  input x Float64 copied
  input y Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "nextafter"
:begin
  result = nextafterCore(x, y)
  rangeSignals(result, x, x)
  return result

op nextafterSingle "nextafterf: the float next to x toward y; ERANGE when it overflows"
  input x Float32 copied
  input y Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "nextafterf"
:begin
  result = nextafterSingleCore(x, y)
  wideResult = convert.float32ToFloat64(result)
  wideX = convert.float32ToFloat64(x)
  rangeSignals(wideResult, wideX, wideX)
  return result

op fdimCore "fdim: x - y when x is greater than y (or either is NaN), otherwise 0"
  input x Float64 copied
  input y Float64 copied
  output Float64
  let zeroValue Float64 0.0
:begin
  when x <= y giveZero subtract
:giveZero
  return zeroValue
:subtract
  calc difference = x - y
  return difference

op fdimSingleCore "fdimf: x - y when x is greater than y (or either is NaN), otherwise 0"
  input x Float32 copied
  input y Float32 copied
  output Float32
  let zeroValue Float32 0.0
:begin
  when x <= y giveZero subtract
:giveZero
  return zeroValue
:subtract
  calc difference = x - y
  return difference

op nextafterSingleCore "nextafterf: the float next to x toward y; y when they are equal, x + y when either is NaN"
  input x Float32 copied
  input y Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
:begin
  xb = singleBits(x)
  yb = singleBits(y)
  calc unordered = !(x == x) || !(y == y)
  when unordered sum checkEqual
:sum
  calc total = x + y
  return total
:checkEqual
  when x == y giveY checkZero
:giveY
  return y
:checkZero
  when (xb & 0x7fffffff) == 0 fromZero step
:fromZero
  calc smallest = (yb & 0x80000000) | 1
  tiny = singleFromBits(smallest)
  return tiny
:step
  calc positive = x > 0.0
  calc rising = x < y
  calc away = (rising && positive) || (!rising && !positive)
  when away up down
:up
  calc upBits = xb + 1
  upValue = singleFromBits(upBits)
  return upValue
:down
  calc downBits = xb - 1
  downValue = singleFromBits(downBits)
  return downValue

## ---------------------------------------------------------------- nan

op digitValue "The value of a hexadecimal digit's character, -1 for any other"
  input c Int64 copied
  output Int64
:begin
  calc isDigit = c >= 48 && c <= 57
  calc isLower = c >= 97 && c <= 102
  calc isUpper = c >= 65 && c <= 70
  when isDigit digit checkLower
:digit
  calc fromDigit = c - 48
  return fromDigit
:checkLower
  when isLower lower checkUpper
:lower
  calc fromLower = c - 87
  return fromLower
:checkUpper
  when isUpper upper other
:upper
  calc fromUpper = c - 55
  return fromUpper
:other
  calc invalid = 0 - 1
  return invalid

op isIdentifier "Whether a character is a letter, a digit, or an underscore"
  input c Int64 copied
  output Bool
:begin
  calc ok = (c >= 48 && c <= 57) || (c >= 65 && c <= 90) || (c >= 97 && c <= 122) || c == 95
  return ok

op nanPayload "The number strtod makes of a NAN(tag) sequence: the tag read as strtoull in base 0 when all of it is that number, otherwise 0"
  input tag machine.Address copied
  output UInt64
  effect use machine.memory
  uses memoryAccess
  let length Int64 0 mut
  let index Int64 0 mut
  let base Int64 10 mut
  let value UInt64 0 mut
  let saturated Bool false mut
  let nothingWord UInt64 0
  let everything UInt64 18446744073709551615
:begin
  goto scan
:scan loop=while max=forever
  calc c = convert.byteToInt64(machine.loadByte(tag + length))
  ident = isIdentifier(c)
  when ident scanNext scanEnd
:scanNext in=scan
  calc length := length + 1
  goto scan
:scanEnd
  calc stop = convert.byteToInt64(machine.loadByte(tag + length))
  calc closed = stop == 0 || stop == 41
  calc usable = closed && length > 0
  when usable classify noPayload
:noPayload
  return nothingWord
:classify
  calc first = convert.byteToInt64(machine.loadByte(tag))
  calc second = convert.byteToInt64(machine.loadByte(tag + 1))
  calc hexPrefix = length >= 3 && first == 48 && (second == 120 || second == 88)
  when hexPrefix hex checkOctal
:hex
  calc base := 16
  calc index := 2
  goto digits
:checkOctal
  when first == 48 && length >= 2 octal decimal
:octal
  calc base := 8
  calc index := 1
  goto digits
:decimal
  calc base := 10
  calc index := 0
  goto digits
:digits loop=while max=forever
  when index >= length finish digit
:digit in=digits
  calc c2 = convert.byteToInt64(machine.loadByte(tag + index))
  d = digitValue(c2)
  calc bad = d < 0 || d >= base
  when bad noPayload accumulate
:accumulate in=digits
  calc dWord = convert.int64BitsToUInt64(d)
  calc baseWord = convert.int64BitsToUInt64(base)
  calc limit = (everything - dWord) / baseWord
  when value > limit saturate add
:saturate in=digits
  calc saturated := true
  goto advance
:add in=digits
  calc value := value * baseWord + dWord
  goto advance
:advance in=digits
  calc index := index + 1
  goto digits
:finish
  when saturated allOnes number
:allOnes
  return everything
:number
  return value

op nanDouble "nan: a quiet NaN whose payload is the tag read as a number (glibc's strtod of NAN(tag))"
  invariant carriesTag "Gives a quiet NaN with the payload the tag names"
  input tag machine.Address copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "nan"
:begin
  payload = nanPayload(tag)
  calc bits = 0x7ff8000000000000 | (payload & 0x7ffffffffffff)
  result = convert.uint64BitsToFloat64(bits)
  return result

op nanSingle "nanf: a quiet NaN whose payload is the tag read as a number"
  input tag machine.Address copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "nanf"
:begin
  payload = nanPayload(tag)
  calc bits = 0x7fc00000 | (payload & 0x3fffff)
  result = singleFromBits(convert.uint64BitsToInt64(bits))
  return result

## ---------------------------------------------------------------- fenv.h

op feclearexceptC "feclearexcept: lower the listed exception flags; 0"
  input excepts Int32 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "feclearexcept"
:begin
  wide = convert.int32ToInt64(excepts)
  changeFlags(wide, 0)
  return okStatus

op feraiseexceptC "feraiseexcept: raise the listed exception flags; 0"
  input excepts Int32 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "feraiseexcept"
:begin
  wide = convert.int32ToInt64(excepts)
  changeFlags(0, wide)
  return okStatus

op fetestexceptC "fetestexcept: which of the listed exception flags are raised"
  input excepts Int32 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fetestexcept"
:begin
  wide = convert.int32ToInt64(excepts)
  flags = raisedFlags()
  calc hit = flags & wide
  result = clibrary.lowInt32(hit)
  return result

op fegetroundC "fegetround: the rounding mode's FE_ constant"
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fegetround"
:begin
  mode = externalMode()
  result = clibrary.lowInt32(mode)
  return result

op fesetroundC "fesetround: set the rounding mode; 0, or 1 (and no change) for a number that is no mode"
  invariant setsMode "Sets the rounding mode a later fegetround gives, and refuses a number that is no mode"
  input mode Int32 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fesetround"
:begin
  wide = convert.int32ToInt64(mode)
  accepted = changeMode(wide)
  when accepted accept refuse
:accept
  return okStatus
:refuse
  return refusedStatus

op fegetexceptflagC "fegetexceptflag: store which of the listed flags are raised, as a fexcept_t (an unsigned short on x86_64, an unsigned int on AArch64); 0"
  input flagp machine.Address copied
  input excepts Int32 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fegetexceptflag"
:begin
  wide = convert.int32ToInt64(excepts)
  flags = raisedFlags()
  calc held = flags & wide
  onArm = system.aarch64()
  when onArm arm x86
:arm
  low = clibrary.lowInt32(held)
  machine.storeInt32(flagp, low)
  return okStatus
:x86
  machine.storeByte(flagp, convert.int64ToByte(held & 255))
  machine.storeByte(flagp + 1, convert.int64ToByte((held >> 8) & 255))
  return okStatus

op fesetexceptflagC "fesetexceptflag: set the listed flags to what a fexcept_t holds; 0"
  input flagp machine.Address copied
  input excepts Int32 copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fesetexceptflag"
  let held Int64 0 mut
:begin
  onArm = system.aarch64()
  when onArm arm x86
:arm
  armWord = machine.loadInt32(flagp)
  calc held := convert.int32ToInt64(armWord) & 0xffffffff
  goto apply
:x86
  lowByte = machine.loadByte(flagp)
  highByte = machine.loadByte(flagp + 1)
  calc held := convert.byteToInt64(lowByte) | (convert.byteToInt64(highByte) << 8)
  goto apply
:apply
  wide = convert.int32ToInt64(excepts)
  every = allFlags()
  calc selected = wide & every
  changeFlags(selected, held & selected)
  return okStatus

op fegetenvC "fegetenv: store the floating-point environment; 0"
  input envp machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fegetenv"
:begin
  saveEnvironment(envp)
  return okStatus

op fesetenvC "fesetenv: set the floating-point environment from a stored one, or FE_DFL_ENV; 0"
  input envp machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "fesetenv"
:begin
  loadEnvironment(envp)
  return okStatus

op feholdexceptC "feholdexcept: store the environment and lower every flag (exceptions stay masked); 0"
  input envp machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "feholdexcept"
:begin
  saveEnvironment(envp)
  every = allFlags()
  changeFlags(every, 0)
  return okStatus

op feupdateenvC "feupdateenv: set the environment from a stored one, then raise the flags that were raised; 0"
  input envp machine.Address copied
  output Int32
  effect use machine.memory
  effect use system.calls
  uses memoryAccess
  uses systemCalls
  abi library "feupdateenv"
:begin
  raised = raisedFlags()
  loadEnvironment(envp)
  changeFlags(0, raised)
  return okStatus
@tests

## Tests keep a pointer's target in the last 4 KiB of machine.state (byte 61440) and a C string from byte 62464.
## Expected values are the exact models' in tests/cmathbitstour.py, which the executable check holds against glibc.

op sameBits "Whether a double has the expected bits"
  input expected UInt64 copied
  input actual Float64 copied
  output Bool
:begin
  actualBits = convert.float64BitsToUInt64(actual)
  calc same = expected == actualBits
  return same

op scratchCell "The address of the tests' scratch cell"
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  place = kernel.stateAt(61440)
  return place

op flagCode "An exception flag set (this module's numbering) as the target's FE_ constants give it"
  input internal Int64 copied
  output Int32
  effect use system.calls
  uses systemCalls
:begin
  onArm = system.aarch64()
  when onArm arm x86
:arm
  armCode = clibrary.lowInt32(internal)
  return armCode
:x86
  calc shifted = (internal & 1) | ((internal & 30) << 1)
  x86Code = clibrary.lowInt32(shifted)
  return x86Code

op modeCode "A rounding mode index (0 nearest, 1 down, 2 up, 3 toward zero) as the target's FE_ constant"
  input index Int64 copied
  output Int32
  effect use system.calls
  uses systemCalls
:begin
  onArm = system.aarch64()
  when onArm arm x86
:x86
  calc x86Mode = index << 10
  x86Code = clibrary.lowInt32(x86Mode)
  return x86Code
:arm
  when index == 1 armDown checkUp
:armDown
  calc downMode = 2 << 22
  downCode = clibrary.lowInt32(downMode)
  return downCode
:checkUp
  when index == 2 armUp armSame
:armUp
  calc upMode = 1 << 22
  upCode = clibrary.lowInt32(upMode)
  return upCode
:armSame
  calc sameMode = index << 22
  sameCode = clibrary.lowInt32(sameMode)
  return sameCode

op scratchText "The address of a C string written in the tests' scratch bytes"
  input text String borrowed
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  place = kernel.stateAt(62464)
  source = machine.addressOfString(text)
  bytes = string.byteLength(text)
  machine.copy(place, source, bytes)
  calc end = place + bytes
  machine.storeByte(end, 0)
  return place

test frexpTest "frexp and frexpf give the fraction and store the power, 0 and infinity as they are"
  verifies frexpDouble splitsFraction
  effect use machine.memory
  uses memoryAccess
:begin
  v1 = frexpDouble(convert.uint64BitsToFloat64(4620693217682128896), scratchCell())
  v2 = sameBits(4602678819172646912, v1)
  test.assertTrue(v2)
  v3 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(4, convert.int32ToInt64(v3))
  v4 = frexpDouble(convert.uint64BitsToFloat64(9223372036854775808), scratchCell())
  v5 = sameBits(9223372036854775808, v4)
  test.assertTrue(v5)
  v6 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(0, convert.int32ToInt64(v6))
  v7 = frexpDouble(convert.uint64BitsToFloat64(1), scratchCell())
  v8 = sameBits(4602678819172646912, v7)
  test.assertTrue(v8)
  v9 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(-1073, convert.int32ToInt64(v9))
  v10 = frexpDouble(convert.uint64BitsToFloat64(9218868437227405312), scratchCell())
  v11 = sameBits(9218868437227405312, v10)
  test.assertTrue(v11)
  v12 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(0, convert.int32ToInt64(v12))
  v13 = frexpDouble(convert.uint64BitsToFloat64(13838998704956112896), scratchCell())
  v14 = sameBits(13829991505701371904, v13)
  test.assertTrue(v14)
  v15 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(2, convert.int32ToInt64(v15))
  v16 = frexpDouble(convert.uint64BitsToFloat64(9214871658872686752), scratchCell())
  v17 = sameBits(4603185640445298848, v16)
  test.assertTrue(v17)
  v18 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(1024, convert.int32ToInt64(v18))
  v19 = frexpSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4620693217682128896)), scratchCell())
  v20 = convert.float32ToFloat64(v19)
  v21 = sameBits(4602678819172646912, v20)
  test.assertTrue(v21)
  v22 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(4, convert.int32ToInt64(v22))
  v23 = frexpSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(3936146074321813504)), scratchCell())
  v24 = convert.float32ToFloat64(v23)
  v25 = sameBits(4602678819172646912, v24)
  test.assertTrue(v25)
  v26 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(-148, convert.int32ToInt64(v26))
  return

test scaleTest "ldexp, scalbn, and scalbln round once, to a subnormal or to infinity, and keep the sign of zero; the float forms too"
  verifies ldexpDouble scalesExactly
  effect use machine.memory
  uses memoryAccess
  effect use system.calls
  uses systemCalls
:begin
  v1 = ldexpDouble(convert.uint64BitsToFloat64(4607182418800017408), 1024)
  v2 = sameBits(9218868437227405312, v1)
  test.assertTrue(v2)
  v3 = scalbnDouble(convert.uint64BitsToFloat64(4607182418800017408), 1024)
  v4 = sameBits(9218868437227405312, v3)
  test.assertTrue(v4)
  v5 = scalblnDouble(convert.uint64BitsToFloat64(4607182418800017408), 1024)
  v6 = sameBits(9218868437227405312, v5)
  test.assertTrue(v6)
  v7 = ldexpDouble(convert.uint64BitsToFloat64(4609434218613702656), -1074)
  v8 = sameBits(2, v7)
  test.assertTrue(v8)
  v9 = scalbnDouble(convert.uint64BitsToFloat64(4609434218613702656), -1074)
  v10 = sameBits(2, v9)
  test.assertTrue(v10)
  v11 = scalblnDouble(convert.uint64BitsToFloat64(4609434218613702656), -1074)
  v12 = sameBits(2, v11)
  test.assertTrue(v12)
  v13 = ldexpDouble(convert.uint64BitsToFloat64(1), 1074)
  v14 = sameBits(4607182418800017408, v13)
  test.assertTrue(v14)
  v15 = scalbnDouble(convert.uint64BitsToFloat64(1), 1074)
  v16 = sameBits(4607182418800017408, v15)
  test.assertTrue(v16)
  v17 = scalblnDouble(convert.uint64BitsToFloat64(1), 1074)
  v18 = sameBits(4607182418800017408, v17)
  test.assertTrue(v18)
  v19 = ldexpDouble(convert.uint64BitsToFloat64(9223372036854775808), 5)
  v20 = sameBits(9223372036854775808, v19)
  test.assertTrue(v20)
  v21 = scalbnDouble(convert.uint64BitsToFloat64(9223372036854775808), 5)
  v22 = sameBits(9223372036854775808, v21)
  test.assertTrue(v22)
  v23 = scalblnDouble(convert.uint64BitsToFloat64(9223372036854775808), 5)
  v24 = sameBits(9223372036854775808, v23)
  test.assertTrue(v24)
  v25 = ldexpDouble(convert.uint64BitsToFloat64(4613937818241073152), -1076)
  v26 = sameBits(1, v25)
  test.assertTrue(v26)
  v27 = scalbnDouble(convert.uint64BitsToFloat64(4613937818241073152), -1076)
  v28 = sameBits(1, v27)
  test.assertTrue(v28)
  v29 = scalblnDouble(convert.uint64BitsToFloat64(4613937818241073152), -1076)
  v30 = sameBits(1, v29)
  test.assertTrue(v30)
  v31 = ldexpDouble(convert.uint64BitsToFloat64(4607182418800017408), 2147483647)
  v32 = sameBits(9218868437227405312, v31)
  test.assertTrue(v32)
  v33 = scalbnDouble(convert.uint64BitsToFloat64(4607182418800017408), 2147483647)
  v34 = sameBits(9218868437227405312, v33)
  test.assertTrue(v34)
  v35 = scalblnDouble(convert.uint64BitsToFloat64(4607182418800017408), 2147483647)
  v36 = sameBits(9218868437227405312, v35)
  test.assertTrue(v36)
  v37 = ldexpDouble(convert.uint64BitsToFloat64(4610560118520545280), -1073)
  v38 = sameBits(4, v37)
  test.assertTrue(v38)
  v39 = scalbnDouble(convert.uint64BitsToFloat64(4610560118520545280), -1073)
  v40 = sameBits(4, v39)
  test.assertTrue(v40)
  v41 = scalblnDouble(convert.uint64BitsToFloat64(4610560118520545280), -1073)
  v42 = sameBits(4, v41)
  test.assertTrue(v42)
  v43 = ldexpDouble(convert.uint64BitsToFloat64(4604930618986332160), -1074)
  v44 = sameBits(1, v43)
  test.assertTrue(v44)
  v45 = scalbnDouble(convert.uint64BitsToFloat64(4604930618986332160), -1074)
  v46 = sameBits(1, v45)
  test.assertTrue(v46)
  v47 = scalblnDouble(convert.uint64BitsToFloat64(4604930618986332160), -1074)
  v48 = sameBits(1, v47)
  test.assertTrue(v48)
  v49 = ldexpDouble(convert.uint64BitsToFloat64(13830554455654793216), -1075)
  v50 = sameBits(9223372036854775808, v49)
  test.assertTrue(v50)
  v51 = scalbnDouble(convert.uint64BitsToFloat64(13830554455654793216), -1075)
  v52 = sameBits(9223372036854775808, v51)
  test.assertTrue(v52)
  v53 = scalblnDouble(convert.uint64BitsToFloat64(13830554455654793216), -1075)
  v54 = sameBits(9223372036854775808, v53)
  test.assertTrue(v54)
  v55 = ldexpDouble(convert.uint64BitsToFloat64(4607182418800017408), -1074)
  v56 = sameBits(1, v55)
  test.assertTrue(v56)
  v57 = scalbnDouble(convert.uint64BitsToFloat64(4607182418800017408), -1074)
  v58 = sameBits(1, v57)
  test.assertTrue(v58)
  v59 = scalblnDouble(convert.uint64BitsToFloat64(4607182418800017408), -1074)
  v60 = sameBits(1, v59)
  test.assertTrue(v60)
  v61 = scalblnDouble(convert.uint64BitsToFloat64(4607182418800017408), 4611686018427387904)
  v62 = sameBits(9218868437227405312, v61)
  test.assertTrue(v62)
  v63 = scalblnDouble(convert.uint64BitsToFloat64(4607182418800017408), -4611686018427387904)
  v64 = sameBits(0, v63)
  test.assertTrue(v64)
  v65 = ldexpSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), 128)
  v66 = convert.float32ToFloat64(v65)
  v67 = sameBits(9218868437227405312, v66)
  test.assertTrue(v67)
  v68 = scalbnSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), 128)
  v69 = convert.float32ToFloat64(v68)
  v70 = sameBits(9218868437227405312, v69)
  test.assertTrue(v70)
  v71 = scalblnSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), 128)
  v72 = convert.float32ToFloat64(v71)
  v73 = sameBits(9218868437227405312, v72)
  test.assertTrue(v73)
  v74 = ldexpSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), -149)
  v75 = convert.float32ToFloat64(v74)
  v76 = sameBits(3936146074321813504, v75)
  test.assertTrue(v76)
  v77 = scalbnSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), -149)
  v78 = convert.float32ToFloat64(v77)
  v79 = sameBits(3936146074321813504, v78)
  test.assertTrue(v79)
  v80 = scalblnSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), -149)
  v81 = convert.float32ToFloat64(v80)
  v82 = sameBits(3936146074321813504, v81)
  test.assertTrue(v82)
  v83 = ldexpSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), -150)
  v84 = convert.float32ToFloat64(v83)
  v85 = sameBits(0, v84)
  test.assertTrue(v85)
  v86 = scalbnSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), -150)
  v87 = convert.float32ToFloat64(v86)
  v88 = sameBits(0, v87)
  test.assertTrue(v88)
  v89 = scalblnSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), -150)
  v90 = convert.float32ToFloat64(v89)
  v91 = sameBits(0, v90)
  test.assertTrue(v91)
  v92 = ldexpSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4609434218613702656)), -149)
  v93 = convert.float32ToFloat64(v92)
  v94 = sameBits(3940649673949184000, v93)
  test.assertTrue(v94)
  v95 = scalbnSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4609434218613702656)), -149)
  v96 = convert.float32ToFloat64(v95)
  v97 = sameBits(3940649673949184000, v96)
  test.assertTrue(v97)
  v98 = scalblnSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4609434218613702656)), -149)
  v99 = convert.float32ToFloat64(v98)
  v100 = sameBits(3940649673949184000, v99)
  test.assertTrue(v100)
  v101 = ldexpSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4613937818241073152)), 127)
  v102 = convert.float32ToFloat64(v101)
  v103 = sameBits(9218868437227405312, v102)
  test.assertTrue(v103)
  v104 = scalbnSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4613937818241073152)), 127)
  v105 = convert.float32ToFloat64(v104)
  v106 = sameBits(9218868437227405312, v105)
  test.assertTrue(v106)
  v107 = scalblnSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4613937818241073152)), 127)
  v108 = convert.float32ToFloat64(v107)
  v109 = sameBits(9218868437227405312, v108)
  test.assertTrue(v109)
  v110 = ldexpSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(13830554455654793216)), -150)
  v111 = convert.float32ToFloat64(v110)
  v112 = sameBits(9223372036854775808, v111)
  test.assertTrue(v112)
  v113 = scalbnSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(13830554455654793216)), -150)
  v114 = convert.float32ToFloat64(v113)
  v115 = sameBits(9223372036854775808, v114)
  test.assertTrue(v115)
  v116 = scalblnSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(13830554455654793216)), -150)
  v117 = convert.float32ToFloat64(v116)
  v118 = sameBits(9223372036854775808, v117)
  test.assertTrue(v118)
  v119 = ldexpSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(0)), 7)
  v120 = convert.float32ToFloat64(v119)
  v121 = sameBits(0, v120)
  test.assertTrue(v121)
  v122 = scalbnSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(0)), 7)
  v123 = convert.float32ToFloat64(v122)
  v124 = sameBits(0, v123)
  test.assertTrue(v124)
  v125 = scalblnSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(0)), 7)
  v126 = convert.float32ToFloat64(v125)
  v127 = sameBits(0, v126)
  test.assertTrue(v127)
  return

test logTest "ilogb and logb give the exponent, with the least int, the greatest int, and the infinities for 0, infinity, and NaN"
  verifies ilogbDouble givesExponent
  effect use machine.memory
  uses memoryAccess
  effect use system.calls
  uses systemCalls
:begin
  v1 = ilogbDouble(convert.uint64BitsToFloat64(4620693217682128896))
  test.assertEqualInt64(3, convert.int32ToInt64(v1))
  v2 = logbDouble(convert.uint64BitsToFloat64(4620693217682128896))
  v3 = sameBits(4613937818241073152, v2)
  test.assertTrue(v3)
  v4 = ilogbDouble(convert.uint64BitsToFloat64(0))
  test.assertEqualInt64(-2147483648, convert.int32ToInt64(v4))
  v5 = logbDouble(convert.uint64BitsToFloat64(0))
  v6 = sameBits(18442240474082181120, v5)
  test.assertTrue(v6)
  v7 = ilogbDouble(convert.uint64BitsToFloat64(9218868437227405312))
  test.assertEqualInt64(2147483647, convert.int32ToInt64(v7))
  v8 = logbDouble(convert.uint64BitsToFloat64(9218868437227405312))
  v9 = sameBits(9218868437227405312, v8)
  test.assertTrue(v9)
  v10 = ilogbDouble(convert.uint64BitsToFloat64(18442240474082181120))
  test.assertEqualInt64(2147483647, convert.int32ToInt64(v10))
  v11 = logbDouble(convert.uint64BitsToFloat64(18442240474082181120))
  v12 = sameBits(9218868437227405312, v11)
  test.assertTrue(v12)
  v13 = ilogbDouble(convert.uint64BitsToFloat64(1))
  test.assertEqualInt64(-1074, convert.int32ToInt64(v13))
  v14 = logbDouble(convert.uint64BitsToFloat64(1))
  v15 = sameBits(13875810354254053376, v14)
  test.assertTrue(v15)
  v16 = ilogbDouble(convert.uint64BitsToFloat64(9221120237041090560))
  test.assertEqualInt64(-2147483648, convert.int32ToInt64(v16))
  v17 = logbDouble(convert.uint64BitsToFloat64(9221120237041090560))
  v18 = sameBits(9221120237041090560, v17)
  test.assertTrue(v18)
  v19 = ilogbDouble(convert.uint64BitsToFloat64(9214871658872686752))
  test.assertEqualInt64(1023, convert.int32ToInt64(v19))
  v20 = logbDouble(convert.uint64BitsToFloat64(9214871658872686752))
  v21 = sameBits(4652209618980700160, v20)
  test.assertTrue(v21)
  v22 = ilogbDouble(convert.uint64BitsToFloat64(4604930618986332160))
  test.assertEqualInt64(-1, convert.int32ToInt64(v22))
  v23 = logbDouble(convert.uint64BitsToFloat64(4604930618986332160))
  v24 = sameBits(13830554455654793216, v23)
  test.assertTrue(v24)
  v25 = ilogbSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4620693217682128896)))
  test.assertEqualInt64(3, convert.int32ToInt64(v25))
  v26 = logbSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4620693217682128896)))
  v27 = convert.float32ToFloat64(v26)
  v28 = sameBits(4613937818241073152, v27)
  test.assertTrue(v28)
  v29 = ilogbSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(0)))
  test.assertEqualInt64(-2147483648, convert.int32ToInt64(v29))
  v30 = logbSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(0)))
  v31 = convert.float32ToFloat64(v30)
  v32 = sameBits(18442240474082181120, v31)
  test.assertTrue(v32)
  v33 = ilogbSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(3936146074321813504)))
  test.assertEqualInt64(-149, convert.int32ToInt64(v33))
  v34 = logbSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(3936146074321813504)))
  v35 = convert.float32ToFloat64(v34)
  v36 = sameBits(13862818524860252160, v35)
  test.assertTrue(v36)
  v37 = ilogbSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(9218868437227405312)))
  test.assertEqualInt64(2147483647, convert.int32ToInt64(v37))
  v38 = logbSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(9218868437227405312)))
  v39 = convert.float32ToFloat64(v38)
  v40 = sameBits(9218868437227405312, v39)
  test.assertTrue(v40)
  return

test modfTest "modf and modff give the fraction with the sign of x and store the whole part toward zero"
  verifies modfDouble splitsWhole
  effect use machine.memory
  uses memoryAccess
:begin
  v1 = modfDouble(convert.uint64BitsToFloat64(4615626668101337088), scratchCell())
  v2 = sameBits(4604930618986332160, v1)
  test.assertTrue(v2)
  v3 = machine.loadFloat64(scratchCell())
  v4 = sameBits(4613937818241073152, v3)
  test.assertTrue(v4)
  v5 = modfDouble(convert.uint64BitsToFloat64(13826050856027422720), scratchCell())
  v6 = sameBits(13826050856027422720, v5)
  test.assertTrue(v6)
  v7 = machine.loadFloat64(scratchCell())
  v8 = sameBits(9223372036854775808, v7)
  test.assertTrue(v8)
  v9 = modfDouble(convert.uint64BitsToFloat64(9218868437227405312), scratchCell())
  v10 = sameBits(0, v9)
  test.assertTrue(v10)
  v11 = machine.loadFloat64(scratchCell())
  v12 = sameBits(9218868437227405312, v11)
  test.assertTrue(v12)
  v13 = modfDouble(convert.uint64BitsToFloat64(18442240474082181120), scratchCell())
  v14 = sameBits(9223372036854775808, v13)
  test.assertTrue(v14)
  v15 = machine.loadFloat64(scratchCell())
  v16 = sameBits(18442240474082181120, v15)
  test.assertTrue(v16)
  v17 = modfDouble(convert.uint64BitsToFloat64(9223372036854775808), scratchCell())
  v18 = sameBits(9223372036854775808, v17)
  test.assertTrue(v18)
  v19 = machine.loadFloat64(scratchCell())
  v20 = sameBits(9223372036854775808, v19)
  test.assertTrue(v20)
  v21 = modfDouble(convert.uint64BitsToFloat64(1), scratchCell())
  v22 = sameBits(1, v21)
  test.assertTrue(v22)
  v23 = machine.loadFloat64(scratchCell())
  v24 = sameBits(0, v23)
  test.assertTrue(v24)
  v25 = modfDouble(convert.uint64BitsToFloat64(4841369599423283201), scratchCell())
  v26 = sameBits(0, v25)
  test.assertTrue(v26)
  v27 = machine.loadFloat64(scratchCell())
  v28 = sameBits(4841369599423283201, v27)
  test.assertTrue(v28)
  v29 = modfDouble(convert.uint64BitsToFloat64(13835058055282163712), scratchCell())
  v30 = sameBits(9223372036854775808, v29)
  test.assertTrue(v30)
  v31 = machine.loadFloat64(scratchCell())
  v32 = sameBits(13835058055282163712, v31)
  test.assertTrue(v32)
  v33 = modfSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4615626668101337088)), scratchCell())
  v34 = convert.float32ToFloat64(v33)
  v35 = sameBits(4604930618986332160, v34)
  test.assertTrue(v35)
  v36 = machine.loadFloat32(scratchCell())
  v37 = convert.float32ToFloat64(v36)
  v38 = sameBits(4613937818241073152, v37)
  test.assertTrue(v38)
  v39 = modfSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(13826050856027422720)), scratchCell())
  v40 = convert.float32ToFloat64(v39)
  v41 = sameBits(13826050856027422720, v40)
  test.assertTrue(v41)
  v42 = machine.loadFloat32(scratchCell())
  v43 = convert.float32ToFloat64(v42)
  v44 = sameBits(9223372036854775808, v43)
  test.assertTrue(v44)
  v45 = modfSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4710765210766409728)), scratchCell())
  v46 = convert.float32ToFloat64(v45)
  v47 = sameBits(0, v46)
  test.assertTrue(v47)
  v48 = machine.loadFloat32(scratchCell())
  v49 = convert.float32ToFloat64(v48)
  v50 = sameBits(4710765210766409728, v49)
  test.assertTrue(v50)
  return

test roundTest "rint, nearbyint, lrint, llrint, lround, and llround round halves to even or away from zero; a long out of range is the least long on x86_64"
  verifies rintDouble roundsToMode
  effect use machine.memory
  uses memoryAccess
  effect use system.calls
  uses systemCalls
:begin
  v1 = rintDouble(convert.uint64BitsToFloat64(4612811918334230528))
  v2 = sameBits(4611686018427387904, v1)
  test.assertTrue(v2)
  v3 = nearbyintDouble(convert.uint64BitsToFloat64(4612811918334230528))
  v4 = sameBits(4611686018427387904, v3)
  test.assertTrue(v4)
  v5 = rintDouble(convert.uint64BitsToFloat64(4615063718147915776))
  v6 = sameBits(4616189618054758400, v5)
  test.assertTrue(v6)
  v7 = nearbyintDouble(convert.uint64BitsToFloat64(4615063718147915776))
  v8 = sameBits(4616189618054758400, v7)
  test.assertTrue(v8)
  v9 = rintDouble(convert.uint64BitsToFloat64(13826050856027422720))
  v10 = sameBits(9223372036854775808, v9)
  test.assertTrue(v10)
  v11 = nearbyintDouble(convert.uint64BitsToFloat64(13826050856027422720))
  v12 = sameBits(9223372036854775808, v11)
  test.assertTrue(v12)
  v13 = rintDouble(convert.uint64BitsToFloat64(4602678819172646913))
  v14 = sameBits(4607182418800017408, v13)
  test.assertTrue(v14)
  v15 = nearbyintDouble(convert.uint64BitsToFloat64(4602678819172646913))
  v16 = sameBits(4607182418800017408, v15)
  test.assertTrue(v16)
  v17 = rintDouble(convert.uint64BitsToFloat64(13836183955189006336))
  v18 = sameBits(13835058055282163712, v17)
  test.assertTrue(v18)
  v19 = nearbyintDouble(convert.uint64BitsToFloat64(13836183955189006336))
  v20 = sameBits(13835058055282163712, v19)
  test.assertTrue(v20)
  v21 = rintDouble(convert.uint64BitsToFloat64(4602678819172646911))
  v22 = sameBits(0, v21)
  test.assertTrue(v22)
  v23 = nearbyintDouble(convert.uint64BitsToFloat64(4602678819172646911))
  v24 = sameBits(0, v23)
  test.assertTrue(v24)
  v25 = rintDouble(convert.uint64BitsToFloat64(4841369599423283201))
  v26 = sameBits(4841369599423283201, v25)
  test.assertTrue(v26)
  v27 = nearbyintDouble(convert.uint64BitsToFloat64(4841369599423283201))
  v28 = sameBits(4841369599423283201, v27)
  test.assertTrue(v28)
  v29 = rintDouble(convert.uint64BitsToFloat64(9094988921128908188))
  v30 = sameBits(9094988921128908188, v29)
  test.assertTrue(v30)
  v31 = nearbyintDouble(convert.uint64BitsToFloat64(9094988921128908188))
  v32 = sameBits(9094988921128908188, v31)
  test.assertTrue(v32)
  v33 = rintDouble(convert.uint64BitsToFloat64(9218868437227405312))
  v34 = sameBits(9218868437227405312, v33)
  test.assertTrue(v34)
  v35 = nearbyintDouble(convert.uint64BitsToFloat64(9218868437227405312))
  v36 = sameBits(9218868437227405312, v35)
  test.assertTrue(v36)
  v37 = lrintDouble(convert.uint64BitsToFloat64(4612811918334230528))
  test.assertEqualInt64(2, v37)
  v38 = llrintDouble(convert.uint64BitsToFloat64(4612811918334230528))
  test.assertEqualInt64(2, v38)
  v39 = lroundDouble(convert.uint64BitsToFloat64(4612811918334230528))
  test.assertEqualInt64(3, v39)
  v40 = llroundDouble(convert.uint64BitsToFloat64(4612811918334230528))
  test.assertEqualInt64(3, v40)
  v41 = lrintDouble(convert.uint64BitsToFloat64(13836183955189006336))
  test.assertEqualInt64(-2, v41)
  v42 = llrintDouble(convert.uint64BitsToFloat64(13836183955189006336))
  test.assertEqualInt64(-2, v42)
  v43 = lroundDouble(convert.uint64BitsToFloat64(13836183955189006336))
  test.assertEqualInt64(-3, v43)
  v44 = llroundDouble(convert.uint64BitsToFloat64(13836183955189006336))
  test.assertEqualInt64(-3, v44)
  v45 = lrintDouble(convert.uint64BitsToFloat64(14114281232179134464))
  test.assertEqualInt64(-9223372036854775808, v45)
  v46 = llrintDouble(convert.uint64BitsToFloat64(14114281232179134464))
  test.assertEqualInt64(-9223372036854775808, v46)
  v47 = lroundDouble(convert.uint64BitsToFloat64(14114281232179134464))
  test.assertEqualInt64(-9223372036854775808, v47)
  v48 = llroundDouble(convert.uint64BitsToFloat64(14114281232179134464))
  test.assertEqualInt64(-9223372036854775808, v48)
  v49 = lrintDouble(convert.uint64BitsToFloat64(4890909195324358655))
  test.assertEqualInt64(9223372036854774784, v49)
  v50 = llrintDouble(convert.uint64BitsToFloat64(4890909195324358655))
  test.assertEqualInt64(9223372036854774784, v50)
  v51 = lroundDouble(convert.uint64BitsToFloat64(4890909195324358655))
  test.assertEqualInt64(9223372036854774784, v51)
  v52 = llroundDouble(convert.uint64BitsToFloat64(4890909195324358655))
  test.assertEqualInt64(9223372036854774784, v52)
  v53 = lrintDouble(convert.uint64BitsToFloat64(4600877379321698714))
  test.assertEqualInt64(0, v53)
  v54 = llrintDouble(convert.uint64BitsToFloat64(4600877379321698714))
  test.assertEqualInt64(0, v54)
  v55 = lroundDouble(convert.uint64BitsToFloat64(4600877379321698714))
  test.assertEqualInt64(0, v55)
  v56 = llroundDouble(convert.uint64BitsToFloat64(4600877379321698714))
  test.assertEqualInt64(0, v56)
  v57 = lrintDouble(convert.uint64BitsToFloat64(13826951575952896819))
  test.assertEqualInt64(-1, v57)
  v58 = llrintDouble(convert.uint64BitsToFloat64(13826951575952896819))
  test.assertEqualInt64(-1, v58)
  v59 = lroundDouble(convert.uint64BitsToFloat64(13826951575952896819))
  test.assertEqualInt64(-1, v59)
  v60 = llroundDouble(convert.uint64BitsToFloat64(13826951575952896819))
  test.assertEqualInt64(-1, v60)
  v61 = rintSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4612811918334230528)))
  v62 = convert.float32ToFloat64(v61)
  v63 = sameBits(4611686018427387904, v62)
  test.assertTrue(v63)
  v64 = nearbyintSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4612811918334230528)))
  v65 = convert.float32ToFloat64(v64)
  v66 = sameBits(4611686018427387904, v65)
  test.assertTrue(v66)
  v67 = lrintSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4612811918334230528)))
  test.assertEqualInt64(2, v67)
  v68 = lroundSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4612811918334230528)))
  test.assertEqualInt64(3, v68)
  v69 = rintSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(13826050856027422720)))
  v70 = convert.float32ToFloat64(v69)
  v71 = sameBits(9223372036854775808, v70)
  test.assertTrue(v71)
  v72 = nearbyintSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(13826050856027422720)))
  v73 = convert.float32ToFloat64(v72)
  v74 = sameBits(9223372036854775808, v73)
  test.assertTrue(v74)
  v75 = lrintSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(13826050856027422720)))
  test.assertEqualInt64(0, v75)
  v76 = lroundSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(13826050856027422720)))
  test.assertEqualInt64(-1, v76)
  v77 = rintSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4615063718147915776)))
  v78 = convert.float32ToFloat64(v77)
  v79 = sameBits(4616189618054758400, v78)
  test.assertTrue(v79)
  v80 = nearbyintSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4615063718147915776)))
  v81 = convert.float32ToFloat64(v80)
  v82 = sameBits(4616189618054758400, v81)
  test.assertTrue(v82)
  v83 = lrintSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4615063718147915776)))
  test.assertEqualInt64(4, v83)
  v84 = lroundSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4615063718147915776)))
  test.assertEqualInt64(4, v84)
  v85 = fesetroundC(modeCode(2))
  test.assertEqualInt64(0, convert.int32ToInt64(v85))
  v86 = rintDouble(convert.uint64BitsToFloat64(4612811918334230528))
  v87 = sameBits(4613937818241073152, v86)
  test.assertTrue(v87)
  v88 = lrintDouble(convert.uint64BitsToFloat64(4612811918334230528))
  test.assertEqualInt64(3, v88)
  v89 = rintDouble(convert.uint64BitsToFloat64(13836183955189006336))
  v90 = sameBits(13835058055282163712, v89)
  test.assertTrue(v90)
  v91 = lrintDouble(convert.uint64BitsToFloat64(13836183955189006336))
  test.assertEqualInt64(-2, v91)
  v92 = rintDouble(convert.uint64BitsToFloat64(4599075939470750515))
  v93 = sameBits(4607182418800017408, v92)
  test.assertTrue(v93)
  v94 = lrintDouble(convert.uint64BitsToFloat64(4599075939470750515))
  test.assertEqualInt64(1, v94)
  v95 = rintDouble(convert.uint64BitsToFloat64(13822447976325526323))
  v96 = sameBits(9223372036854775808, v95)
  test.assertTrue(v96)
  v97 = lrintDouble(convert.uint64BitsToFloat64(13822447976325526323))
  test.assertEqualInt64(0, v97)
  v98 = fesetroundC(modeCode(1))
  test.assertEqualInt64(0, convert.int32ToInt64(v98))
  v99 = rintDouble(convert.uint64BitsToFloat64(4612811918334230528))
  v100 = sameBits(4611686018427387904, v99)
  test.assertTrue(v100)
  v101 = lrintDouble(convert.uint64BitsToFloat64(4612811918334230528))
  test.assertEqualInt64(2, v101)
  v102 = rintDouble(convert.uint64BitsToFloat64(13836183955189006336))
  v103 = sameBits(13837309855095848960, v102)
  test.assertTrue(v103)
  v104 = lrintDouble(convert.uint64BitsToFloat64(13836183955189006336))
  test.assertEqualInt64(-3, v104)
  v105 = rintDouble(convert.uint64BitsToFloat64(4599075939470750515))
  v106 = sameBits(0, v105)
  test.assertTrue(v106)
  v107 = lrintDouble(convert.uint64BitsToFloat64(4599075939470750515))
  test.assertEqualInt64(0, v107)
  v108 = rintDouble(convert.uint64BitsToFloat64(13822447976325526323))
  v109 = sameBits(13830554455654793216, v108)
  test.assertTrue(v109)
  v110 = lrintDouble(convert.uint64BitsToFloat64(13822447976325526323))
  test.assertEqualInt64(-1, v110)
  v111 = fesetroundC(modeCode(3))
  test.assertEqualInt64(0, convert.int32ToInt64(v111))
  v112 = rintDouble(convert.uint64BitsToFloat64(4612811918334230528))
  v113 = sameBits(4611686018427387904, v112)
  test.assertTrue(v113)
  v114 = lrintDouble(convert.uint64BitsToFloat64(4612811918334230528))
  test.assertEqualInt64(2, v114)
  v115 = rintDouble(convert.uint64BitsToFloat64(13836183955189006336))
  v116 = sameBits(13835058055282163712, v115)
  test.assertTrue(v116)
  v117 = lrintDouble(convert.uint64BitsToFloat64(13836183955189006336))
  test.assertEqualInt64(-2, v117)
  v118 = rintDouble(convert.uint64BitsToFloat64(4599075939470750515))
  v119 = sameBits(0, v118)
  test.assertTrue(v119)
  v120 = lrintDouble(convert.uint64BitsToFloat64(4599075939470750515))
  test.assertEqualInt64(0, v120)
  v121 = rintDouble(convert.uint64BitsToFloat64(13822447976325526323))
  v122 = sameBits(9223372036854775808, v121)
  test.assertTrue(v122)
  v123 = lrintDouble(convert.uint64BitsToFloat64(13822447976325526323))
  test.assertEqualInt64(0, v123)
  v124 = fesetroundC(modeCode(0))
  test.assertEqualInt64(0, convert.int32ToInt64(v124))
  return

test remainderTest "remainder and remquo are exact, with the sign of the quotient and its low three bits stored; float forms too"
  verifies remainderDouble remaindersExactly
  effect use machine.memory
  uses memoryAccess
:begin
  v1 = remainderDouble(convert.uint64BitsToFloat64(4620130267728707584), convert.uint64BitsToFloat64(4611686018427387904))
  v2 = sameBits(13826050856027422720, v1)
  test.assertTrue(v2)
  machine.storeInt32(scratchCell(), 0)
  v4 = remquoDouble(convert.uint64BitsToFloat64(4620130267728707584), convert.uint64BitsToFloat64(4611686018427387904), scratchCell())
  v5 = sameBits(13826050856027422720, v4)
  test.assertTrue(v5)
  v6 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(4, convert.int32ToInt64(v6))
  v7 = remainderDouble(convert.uint64BitsToFloat64(13843502304583483392), convert.uint64BitsToFloat64(4611686018427387904))
  v8 = sameBits(4602678819172646912, v7)
  test.assertTrue(v8)
  machine.storeInt32(scratchCell(), 0)
  v10 = remquoDouble(convert.uint64BitsToFloat64(13843502304583483392), convert.uint64BitsToFloat64(4611686018427387904), scratchCell())
  v11 = sameBits(4602678819172646912, v10)
  test.assertTrue(v11)
  v12 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(-4, convert.int32ToInt64(v12))
  v13 = remainderDouble(convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(4591870180066957722))
  v14 = sameBits(13587360075776786432, v13)
  test.assertTrue(v14)
  machine.storeInt32(scratchCell(), 0)
  v16 = remquoDouble(convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(4591870180066957722), scratchCell())
  v17 = sameBits(13587360075776786432, v16)
  test.assertTrue(v17)
  v18 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(2, convert.int32ToInt64(v18))
  v19 = remainderDouble(convert.uint64BitsToFloat64(9094988921128908188), convert.uint64BitsToFloat64(126121232842798723))
  v20 = sameBits(118396640582041260, v19)
  test.assertTrue(v20)
  machine.storeInt32(scratchCell(), 0)
  v22 = remquoDouble(convert.uint64BitsToFloat64(9094988921128908188), convert.uint64BitsToFloat64(126121232842798723), scratchCell())
  v23 = sameBits(118396640582041260, v22)
  test.assertTrue(v23)
  v24 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(7, convert.int32ToInt64(v24))
  v25 = remainderDouble(convert.uint64BitsToFloat64(1), convert.uint64BitsToFloat64(60720675992193))
  v26 = sameBits(1, v25)
  test.assertTrue(v26)
  machine.storeInt32(scratchCell(), 0)
  v28 = remquoDouble(convert.uint64BitsToFloat64(1), convert.uint64BitsToFloat64(60720675992193), scratchCell())
  v29 = sameBits(1, v28)
  test.assertTrue(v29)
  v30 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(0, convert.int32ToInt64(v30))
  v31 = remainderDouble(convert.uint64BitsToFloat64(4620411742705418240), convert.uint64BitsToFloat64(4607182418800017408))
  v32 = sameBits(13821547256400052224, v31)
  test.assertTrue(v32)
  machine.storeInt32(scratchCell(), 0)
  v34 = remquoDouble(convert.uint64BitsToFloat64(4620411742705418240), convert.uint64BitsToFloat64(4607182418800017408), scratchCell())
  v35 = sameBits(13821547256400052224, v34)
  test.assertTrue(v35)
  v36 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(8, convert.int32ToInt64(v36))
  v37 = remainderDouble(convert.uint64BitsToFloat64(13839561654909534208), convert.uint64BitsToFloat64(4611686018427387904))
  v38 = sameBits(9223372036854775808, v37)
  test.assertTrue(v38)
  machine.storeInt32(scratchCell(), 0)
  v40 = remquoDouble(convert.uint64BitsToFloat64(13839561654909534208), convert.uint64BitsToFloat64(4611686018427387904), scratchCell())
  v41 = sameBits(9223372036854775808, v40)
  test.assertTrue(v41)
  v42 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(-2, convert.int32ToInt64(v42))
  v43 = remainderDouble(convert.uint64BitsToFloat64(4617315517961601024), convert.uint64BitsToFloat64(9218868437227405312))
  v44 = sameBits(4617315517961601024, v43)
  test.assertTrue(v44)
  machine.storeInt32(scratchCell(), 0)
  v46 = remquoDouble(convert.uint64BitsToFloat64(4617315517961601024), convert.uint64BitsToFloat64(9218868437227405312), scratchCell())
  v47 = sameBits(4617315517961601024, v46)
  test.assertTrue(v47)
  v48 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(0, convert.int32ToInt64(v48))
  v49 = remainderDouble(convert.uint64BitsToFloat64(4599075939470750515), convert.uint64BitsToFloat64(4591870180066957722))
  v50 = sameBits(13582856476149415936, v49)
  test.assertTrue(v50)
  machine.storeInt32(scratchCell(), 0)
  v52 = remquoDouble(convert.uint64BitsToFloat64(4599075939470750515), convert.uint64BitsToFloat64(4591870180066957722), scratchCell())
  v53 = sameBits(13582856476149415936, v52)
  test.assertTrue(v53)
  v54 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(3, convert.int32ToInt64(v54))
  v55 = remainderDouble(convert.uint64BitsToFloat64(4613937818241073152), convert.uint64BitsToFloat64(4616189618054758400))
  v56 = sameBits(13830554455654793216, v55)
  test.assertTrue(v56)
  machine.storeInt32(scratchCell(), 0)
  v58 = remquoDouble(convert.uint64BitsToFloat64(4613937818241073152), convert.uint64BitsToFloat64(4616189618054758400), scratchCell())
  v59 = sameBits(13830554455654793216, v58)
  test.assertTrue(v59)
  v60 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(1, convert.int32ToInt64(v60))
  v61 = remainderDouble(convert.uint64BitsToFloat64(4612811918334230528), convert.uint64BitsToFloat64(4607182418800017408))
  v62 = sameBits(4602678819172646912, v61)
  test.assertTrue(v62)
  machine.storeInt32(scratchCell(), 0)
  v64 = remquoDouble(convert.uint64BitsToFloat64(4612811918334230528), convert.uint64BitsToFloat64(4607182418800017408), scratchCell())
  v65 = sameBits(4602678819172646912, v64)
  test.assertTrue(v65)
  v66 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(2, convert.int32ToInt64(v66))
  v67 = remainderDouble(convert.uint64BitsToFloat64(4845873199050653696), convert.uint64BitsToFloat64(4611686018427387904))
  v68 = sameBits(0, v67)
  test.assertTrue(v68)
  machine.storeInt32(scratchCell(), 0)
  v70 = remquoDouble(convert.uint64BitsToFloat64(4845873199050653696), convert.uint64BitsToFloat64(4611686018427387904), scratchCell())
  v71 = sameBits(0, v70)
  test.assertTrue(v71)
  v72 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(0, convert.int32ToInt64(v72))
  v73 = remainderSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4620130267728707584)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4611686018427387904)))
  v74 = convert.float32ToFloat64(v73)
  v75 = sameBits(13826050856027422720, v74)
  test.assertTrue(v75)
  machine.storeInt32(scratchCell(), 0)
  v76 = remquoSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4620130267728707584)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4611686018427387904)), scratchCell())
  v77 = convert.float32ToFloat64(v76)
  v78 = sameBits(13826050856027422720, v77)
  test.assertTrue(v78)
  v79 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(4, convert.int32ToInt64(v79))
  v80 = remainderSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(13843502304583483392)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4611686018427387904)))
  v81 = convert.float32ToFloat64(v80)
  v82 = sameBits(4602678819172646912, v81)
  test.assertTrue(v82)
  machine.storeInt32(scratchCell(), 0)
  v83 = remquoSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(13843502304583483392)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4611686018427387904)), scratchCell())
  v84 = convert.float32ToFloat64(v83)
  v85 = sameBits(4602678819172646912, v84)
  test.assertTrue(v85)
  v86 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(-4, convert.int32ToInt64(v86))
  v87 = remainderSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4591870180174331904)))
  v88 = convert.float32ToFloat64(v87)
  v89 = sameBits(13713460865343160320, v88)
  test.assertTrue(v89)
  machine.storeInt32(scratchCell(), 0)
  v90 = remquoSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4591870180174331904)), scratchCell())
  v91 = convert.float32ToFloat64(v90)
  v92 = sameBits(13713460865343160320, v91)
  test.assertTrue(v92)
  v93 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(2, convert.int32ToInt64(v93))
  v94 = remainderSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4620411742705418240)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)))
  v95 = convert.float32ToFloat64(v94)
  v96 = sameBits(13821547256400052224, v95)
  test.assertTrue(v96)
  machine.storeInt32(scratchCell(), 0)
  v97 = remquoSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4620411742705418240)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), scratchCell())
  v98 = convert.float32ToFloat64(v97)
  v99 = sameBits(13821547256400052224, v98)
  test.assertTrue(v99)
  v100 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(8, convert.int32ToInt64(v100))
  v101 = remainderSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4613937818241073152)), convert.float64ToFloat32(convert.uint64BitsToFloat64(9218868437227405312)))
  v102 = convert.float32ToFloat64(v101)
  v103 = sameBits(4613937818241073152, v102)
  test.assertTrue(v103)
  machine.storeInt32(scratchCell(), 0)
  v104 = remquoSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4613937818241073152)), convert.float64ToFloat32(convert.uint64BitsToFloat64(9218868437227405312)), scratchCell())
  v105 = convert.float32ToFloat64(v104)
  v106 = sameBits(4613937818241073152, v105)
  test.assertTrue(v106)
  v107 = machine.loadInt32(scratchCell())
  test.assertEqualInt64(0, convert.int32ToInt64(v107))
  return

test pickTest "fdim, fmax, fmin, and nextafter give the exact value they name, NaN as glibc does; float forms too"
  verifies nextafterDouble stepsOneUnit
  effect use machine.memory
  uses memoryAccess
:begin
  v1 = fdimDouble(convert.uint64BitsToFloat64(4613937818241073152), convert.uint64BitsToFloat64(4607182418800017408))
  v2 = sameBits(4611686018427387904, v1)
  test.assertTrue(v2)
  v3 = fmaxDouble(convert.uint64BitsToFloat64(4613937818241073152), convert.uint64BitsToFloat64(4607182418800017408))
  v4 = sameBits(4613937818241073152, v3)
  test.assertTrue(v4)
  v5 = fminDouble(convert.uint64BitsToFloat64(4613937818241073152), convert.uint64BitsToFloat64(4607182418800017408))
  v6 = sameBits(4607182418800017408, v5)
  test.assertTrue(v6)
  v7 = fdimDouble(convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(4613937818241073152))
  v8 = sameBits(0, v7)
  test.assertTrue(v8)
  v9 = fmaxDouble(convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(4613937818241073152))
  v10 = sameBits(4613937818241073152, v9)
  test.assertTrue(v10)
  v11 = fminDouble(convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(4613937818241073152))
  v12 = sameBits(4607182418800017408, v11)
  test.assertTrue(v12)
  v13 = fdimDouble(convert.uint64BitsToFloat64(9221120237041090560), convert.uint64BitsToFloat64(4607182418800017408))
  v14 = sameBits(9221120237041090560, v13)
  test.assertTrue(v14)
  v15 = fmaxDouble(convert.uint64BitsToFloat64(9221120237041090560), convert.uint64BitsToFloat64(4607182418800017408))
  v16 = sameBits(4607182418800017408, v15)
  test.assertTrue(v16)
  v17 = fminDouble(convert.uint64BitsToFloat64(9221120237041090560), convert.uint64BitsToFloat64(4607182418800017408))
  v18 = sameBits(4607182418800017408, v17)
  test.assertTrue(v18)
  v19 = fdimDouble(convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(9221120237041090560))
  v20 = sameBits(9221120237041090560, v19)
  test.assertTrue(v20)
  v21 = fmaxDouble(convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(9221120237041090560))
  v22 = sameBits(4607182418800017408, v21)
  test.assertTrue(v22)
  v23 = fminDouble(convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(9221120237041090560))
  v24 = sameBits(4607182418800017408, v23)
  test.assertTrue(v24)
  v25 = fdimDouble(convert.uint64BitsToFloat64(9218868437227405312), convert.uint64BitsToFloat64(9218868437227405312))
  v26 = sameBits(0, v25)
  test.assertTrue(v26)
  v27 = fmaxDouble(convert.uint64BitsToFloat64(9218868437227405312), convert.uint64BitsToFloat64(9218868437227405312))
  v28 = sameBits(9218868437227405312, v27)
  test.assertTrue(v28)
  v29 = fminDouble(convert.uint64BitsToFloat64(9218868437227405312), convert.uint64BitsToFloat64(9218868437227405312))
  v30 = sameBits(9218868437227405312, v29)
  test.assertTrue(v30)
  v31 = fdimDouble(convert.uint64BitsToFloat64(9218868437227405312), convert.uint64BitsToFloat64(18442240474082181120))
  v32 = sameBits(9218868437227405312, v31)
  test.assertTrue(v32)
  v33 = fmaxDouble(convert.uint64BitsToFloat64(9218868437227405312), convert.uint64BitsToFloat64(18442240474082181120))
  v34 = sameBits(9218868437227405312, v33)
  test.assertTrue(v34)
  v35 = fminDouble(convert.uint64BitsToFloat64(9218868437227405312), convert.uint64BitsToFloat64(18442240474082181120))
  v36 = sameBits(18442240474082181120, v35)
  test.assertTrue(v36)
  v37 = fdimDouble(convert.uint64BitsToFloat64(9214871658872686752), convert.uint64BitsToFloat64(18438243695727462560))
  v38 = sameBits(9218868437227405312, v37)
  test.assertTrue(v38)
  v39 = fmaxDouble(convert.uint64BitsToFloat64(9214871658872686752), convert.uint64BitsToFloat64(18438243695727462560))
  v40 = sameBits(9214871658872686752, v39)
  test.assertTrue(v40)
  v41 = fminDouble(convert.uint64BitsToFloat64(9214871658872686752), convert.uint64BitsToFloat64(18438243695727462560))
  v42 = sameBits(18438243695727462560, v41)
  test.assertTrue(v42)
  v43 = fdimDouble(convert.uint64BitsToFloat64(0), convert.uint64BitsToFloat64(9223372036854775808))
  v44 = sameBits(0, v43)
  test.assertTrue(v44)
  v45 = nextafterDouble(convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(4611686018427387904))
  v46 = sameBits(4607182418800017409, v45)
  test.assertTrue(v46)
  v47 = nextafterDouble(convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(0))
  v48 = sameBits(4607182418800017407, v47)
  test.assertTrue(v48)
  v49 = nextafterDouble(convert.uint64BitsToFloat64(0), convert.uint64BitsToFloat64(4607182418800017408))
  v50 = sameBits(1, v49)
  test.assertTrue(v50)
  v51 = nextafterDouble(convert.uint64BitsToFloat64(0), convert.uint64BitsToFloat64(13830554455654793216))
  v52 = sameBits(9223372036854775809, v51)
  test.assertTrue(v52)
  v53 = nextafterDouble(convert.uint64BitsToFloat64(13830554455654793216), convert.uint64BitsToFloat64(0))
  v54 = sameBits(13830554455654793215, v53)
  test.assertTrue(v54)
  v55 = nextafterDouble(convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(4607182418800017408))
  v56 = sameBits(4607182418800017408, v55)
  test.assertTrue(v56)
  v57 = nextafterDouble(convert.uint64BitsToFloat64(9218868437227405311), convert.uint64BitsToFloat64(9218868437227405312))
  v58 = sameBits(9218868437227405312, v57)
  test.assertTrue(v58)
  v59 = nextafterDouble(convert.uint64BitsToFloat64(9218868437227405312), convert.uint64BitsToFloat64(0))
  v60 = sameBits(9218868437227405311, v59)
  test.assertTrue(v60)
  v61 = nextafterDouble(convert.uint64BitsToFloat64(9223372036854775808), convert.uint64BitsToFloat64(0))
  v62 = sameBits(0, v61)
  test.assertTrue(v62)
  v63 = nextafterDouble(convert.uint64BitsToFloat64(1), convert.uint64BitsToFloat64(0))
  v64 = sameBits(0, v63)
  test.assertTrue(v64)
  v65 = nextafterDouble(convert.uint64BitsToFloat64(9221120237041090560), convert.uint64BitsToFloat64(4607182418800017408))
  v66 = sameBits(9221120237041090560, v65)
  test.assertTrue(v66)
  v67 = fdimSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4613937818241073152)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)))
  v68 = convert.float32ToFloat64(v67)
  v69 = sameBits(4611686018427387904, v68)
  test.assertTrue(v69)
  v70 = fmaxSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4613937818241073152)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)))
  v71 = convert.float32ToFloat64(v70)
  v72 = sameBits(4613937818241073152, v71)
  test.assertTrue(v72)
  v73 = fminSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4613937818241073152)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)))
  v74 = convert.float32ToFloat64(v73)
  v75 = sameBits(4607182418800017408, v74)
  test.assertTrue(v75)
  v76 = fdimSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4613937818241073152)))
  v77 = convert.float32ToFloat64(v76)
  v78 = sameBits(0, v77)
  test.assertTrue(v78)
  v79 = fmaxSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4613937818241073152)))
  v80 = convert.float32ToFloat64(v79)
  v81 = sameBits(4613937818241073152, v80)
  test.assertTrue(v81)
  v82 = fminSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4613937818241073152)))
  v83 = convert.float32ToFloat64(v82)
  v84 = sameBits(4607182418800017408, v83)
  test.assertTrue(v84)
  v85 = fdimSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(9221120237041090560)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)))
  v86 = convert.float32ToFloat64(v85)
  v87 = sameBits(9221120237041090560, v86)
  test.assertTrue(v87)
  v88 = fmaxSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(9221120237041090560)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)))
  v89 = convert.float32ToFloat64(v88)
  v90 = sameBits(4607182418800017408, v89)
  test.assertTrue(v90)
  v91 = fminSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(9221120237041090560)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)))
  v92 = convert.float32ToFloat64(v91)
  v93 = sameBits(4607182418800017408, v92)
  test.assertTrue(v93)
  v94 = fdimSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(5183643170566569984)), convert.float64ToFloat32(convert.uint64BitsToFloat64(14407015207421345792)))
  v95 = convert.float32ToFloat64(v94)
  v96 = sameBits(9218868437227405312, v95)
  test.assertTrue(v96)
  v97 = fmaxSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(5183643170566569984)), convert.float64ToFloat32(convert.uint64BitsToFloat64(14407015207421345792)))
  v98 = convert.float32ToFloat64(v97)
  v99 = sameBits(5183643170566569984, v98)
  test.assertTrue(v99)
  v100 = fminSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(5183643170566569984)), convert.float64ToFloat32(convert.uint64BitsToFloat64(14407015207421345792)))
  v101 = convert.float32ToFloat64(v100)
  v102 = sameBits(14407015207421345792, v101)
  test.assertTrue(v102)
  v103 = nextafterSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4611686018427387904)))
  v104 = convert.float32ToFloat64(v103)
  v105 = sameBits(4607182419336888320, v104)
  test.assertTrue(v105)
  v106 = nextafterSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), convert.float64ToFloat32(convert.uint64BitsToFloat64(0)))
  v107 = convert.float32ToFloat64(v106)
  v108 = sameBits(4607182418263146496, v107)
  test.assertTrue(v108)
  v109 = nextafterSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(0)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)))
  v110 = convert.float32ToFloat64(v109)
  v111 = sameBits(3936146074321813504, v110)
  test.assertTrue(v111)
  v112 = nextafterSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(0)), convert.float64ToFloat32(convert.uint64BitsToFloat64(13830554455654793216)))
  v113 = convert.float32ToFloat64(v112)
  v114 = sameBits(13159518111176589312, v113)
  test.assertTrue(v114)
  v115 = nextafterSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(5183643170566569984)), convert.float64ToFloat32(convert.uint64BitsToFloat64(9218868437227405312)))
  v116 = convert.float32ToFloat64(v115)
  v117 = sameBits(9218868437227405312, v116)
  test.assertTrue(v117)
  v118 = nextafterSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)))
  v119 = convert.float32ToFloat64(v118)
  v120 = sameBits(4607182418800017408, v119)
  test.assertTrue(v120)
  return

test fmaTest "fma rounds x*y+z once: a sum that a product-then-sum rounds twice, cancellation, subnormals, overflow, and zeros"
  verifies fmaDouble roundsOnce
  effect use machine.memory
  uses memoryAccess
:begin
  v1 = fmaDouble(convert.uint64BitsToFloat64(4611686018427387904), convert.uint64BitsToFloat64(4613937818241073152), convert.uint64BitsToFloat64(4616189618054758400))
  v2 = sameBits(4621819117588971520, v1)
  test.assertTrue(v2)
  v3 = fmaDouble(convert.uint64BitsToFloat64(4607182418800017409), convert.uint64BitsToFloat64(4607182418800017406), convert.uint64BitsToFloat64(13830554455654793216))
  v4 = sameBits(13362180094408261632, v3)
  test.assertTrue(v4)
  v5 = fmaDouble(convert.uint64BitsToFloat64(9214871658872686752), convert.uint64BitsToFloat64(4621819117588971520), convert.uint64BitsToFloat64(18438243695727462560))
  v6 = sameBits(9218868437227405312, v5)
  test.assertTrue(v6)
  v7 = fmaDouble(convert.uint64BitsToFloat64(1614679632300144556), convert.uint64BitsToFloat64(1614679632300144556), convert.uint64BitsToFloat64(118622047889322841))
  v8 = sameBits(118622047889322841, v7)
  test.assertTrue(v8)
  v9 = fmaDouble(convert.uint64BitsToFloat64(4613937818241073152), convert.uint64BitsToFloat64(1), convert.uint64BitsToFloat64(0))
  v10 = sameBits(3, v9)
  test.assertTrue(v10)
  v11 = fmaDouble(convert.uint64BitsToFloat64(1), convert.uint64BitsToFloat64(4602678819172646912), convert.uint64BitsToFloat64(1))
  v12 = sameBits(2, v11)
  test.assertTrue(v12)
  v13 = fmaDouble(convert.uint64BitsToFloat64(2188749418902061056), convert.uint64BitsToFloat64(2188749418902061056), convert.uint64BitsToFloat64(0))
  v14 = sameBits(1, v13)
  test.assertTrue(v14)
  v15 = fmaDouble(convert.uint64BitsToFloat64(13830554455654793216), convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(4607182418800017408))
  v16 = sameBits(0, v15)
  test.assertTrue(v16)
  v17 = fmaDouble(convert.uint64BitsToFloat64(13830554455654793216), convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(9223372036854775808))
  v18 = sameBits(13830554455654793216, v17)
  test.assertTrue(v18)
  v19 = fmaDouble(convert.uint64BitsToFloat64(0), convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(9223372036854775808))
  v20 = sameBits(0, v19)
  test.assertTrue(v20)
  v21 = fmaDouble(convert.uint64BitsToFloat64(9218868437227405312), convert.uint64BitsToFloat64(4611686018427387904), convert.uint64BitsToFloat64(4607182418800017408))
  v22 = sameBits(9218868437227405312, v21)
  test.assertTrue(v22)
  v23 = fmaDouble(convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(4368491638549381120))
  v24 = sameBits(4607182418800017408, v23)
  test.assertTrue(v24)
  v25 = fmaDouble(convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(4607182418800017409), convert.uint64BitsToFloat64(4129800858298744832))
  v26 = sameBits(4607182418800017409, v25)
  test.assertTrue(v26)
  v27 = fmaDouble(convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(4607182418800017409), convert.uint64BitsToFloat64(13353172895153520640))
  v28 = sameBits(4607182418800017409, v27)
  test.assertTrue(v28)
  v29 = fmaDouble(convert.uint64BitsToFloat64(4728779608772575232), convert.uint64BitsToFloat64(4728779608671911936), convert.uint64BitsToFloat64(13830554455654793216))
  v30 = sameBits(4850376798678024191, v29)
  test.assertTrue(v30)
  v31 = fmaDouble(convert.uint64BitsToFloat64(9218868437227405311), convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(8975683443661690106))
  v32 = sameBits(9218868437227405312, v31)
  test.assertTrue(v32)
  v33 = fmaDouble(convert.uint64BitsToFloat64(9218868437227405311), convert.uint64BitsToFloat64(4607182418800017408), convert.uint64BitsToFloat64(8960376836716005366))
  v34 = sameBits(9218868437227405311, v33)
  test.assertTrue(v34)
  v35 = fmaDouble(convert.uint64BitsToFloat64(4609434218613702656), convert.uint64BitsToFloat64(2), convert.uint64BitsToFloat64(1))
  v36 = sameBits(4, v35)
  test.assertTrue(v36)
  v37 = fmaSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4611686018427387904)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4613937818241073152)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4616189618054758400)))
  v38 = convert.float32ToFloat64(v37)
  v39 = sameBits(4621819117588971520, v38)
  test.assertTrue(v39)
  v40 = fmaSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182419336888320)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182419336888320)), convert.float64ToFloat32(convert.uint64BitsToFloat64(13830554455654793216)))
  v41 = convert.float32ToFloat64(v40)
  v42 = sameBits(4508103226997866496, v41)
  test.assertTrue(v42)
  v43 = fmaSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4499096027743125504)))
  v44 = convert.float32ToFloat64(v43)
  v45 = sameBits(4607182418800017408, v44)
  test.assertTrue(v45)
  v46 = fmaSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4494592428115755008)))
  v47 = convert.float32ToFloat64(v46)
  v48 = sameBits(4607182418800017408, v47)
  test.assertTrue(v48)
  v49 = fmaSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4494592428115755008)))
  v50 = convert.float32ToFloat64(v49)
  v51 = sameBits(4607182418800017408, v50)
  test.assertTrue(v51)
  v52 = fmaSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(5183643170566569984)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4611686018427387904)), convert.float64ToFloat32(convert.uint64BitsToFloat64(14407015207421345792)))
  v53 = convert.float32ToFloat64(v52)
  v54 = sameBits(5183643170566569984, v53)
  test.assertTrue(v54)
  v55 = fmaSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(5183643170566569984)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), convert.float64ToFloat32(convert.uint64BitsToFloat64(5070927765226651648)))
  v56 = convert.float32ToFloat64(v55)
  v57 = sameBits(5183643170566569984, v56)
  test.assertTrue(v57)
  v58 = fmaSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4039728865751334912)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4503599627370496000)), convert.float64ToFloat32(convert.uint64BitsToFloat64(0)))
  v59 = convert.float32ToFloat64(v58)
  v60 = sameBits(3936146074321813504, v59)
  test.assertTrue(v60)
  v61 = fmaSingle(convert.float64ToFloat32(convert.uint64BitsToFloat64(4715268809856909312)), convert.float64ToFloat32(convert.uint64BitsToFloat64(4607182418800017408)), convert.float64ToFloat32(convert.uint64BitsToFloat64(0)))
  v62 = convert.float32ToFloat64(v61)
  v63 = sameBits(4715268809856909312, v62)
  test.assertTrue(v63)
  return

test nanTest "nan and nanf give a quiet NaN whose payload is the tag read as strtoull reads it"
  verifies nanDouble carriesTag
  effect use machine.memory
  uses memoryAccess
:begin
  place0 = scratchText("")
  v1 = nanDouble(place0)
  v2 = sameBits(9221120237041090560, v1)
  test.assertTrue(v2)
  v3 = nanSingle(place0)
  v4 = convert.float32ToFloat64(v3)
  v5 = sameBits(9221120237041090560, v4)
  test.assertTrue(v5)
  place8 = scratchText("1")
  v6 = nanDouble(place8)
  v7 = sameBits(9221120237041090561, v6)
  test.assertTrue(v7)
  v8 = nanSingle(place8)
  v9 = convert.float32ToFloat64(v8)
  v10 = sameBits(9221120237577961472, v9)
  test.assertTrue(v10)
  place16 = scratchText("123")
  v11 = nanDouble(place16)
  v12 = sameBits(9221120237041090683, v11)
  test.assertTrue(v12)
  v13 = nanSingle(place16)
  v14 = convert.float32ToFloat64(v13)
  v15 = sameBits(9221120303076212736, v14)
  test.assertTrue(v15)
  place24 = scratchText("0x1f")
  v16 = nanDouble(place24)
  v17 = sameBits(9221120237041090591, v16)
  test.assertTrue(v17)
  v18 = nanSingle(place24)
  v19 = convert.float32ToFloat64(v18)
  v20 = sameBits(9221120253684088832, v19)
  test.assertTrue(v20)
  place32 = scratchText("077")
  v21 = nanDouble(place32)
  v22 = sameBits(9221120237041090623, v21)
  test.assertTrue(v22)
  v23 = nanSingle(place32)
  v24 = convert.float32ToFloat64(v23)
  v25 = sameBits(9221120270863958016, v24)
  test.assertTrue(v25)
  place40 = scratchText("ff")
  v26 = nanDouble(place40)
  v27 = sameBits(9221120237041090560, v26)
  test.assertTrue(v27)
  v28 = nanSingle(place40)
  v29 = convert.float32ToFloat64(v28)
  v30 = sameBits(9221120237041090560, v29)
  test.assertTrue(v30)
  place48 = scratchText("-1")
  v31 = nanDouble(place48)
  v32 = sameBits(9221120237041090560, v31)
  test.assertTrue(v32)
  v33 = nanSingle(place48)
  v34 = convert.float32ToFloat64(v33)
  v35 = sameBits(9221120237041090560, v34)
  test.assertTrue(v35)
  place56 = scratchText("5)7")
  v36 = nanDouble(place56)
  v37 = sameBits(9221120237041090565, v36)
  test.assertTrue(v37)
  v38 = nanSingle(place56)
  v39 = convert.float32ToFloat64(v38)
  v40 = sameBits(9221120239725445120, v39)
  test.assertTrue(v40)
  place64 = scratchText("18446744073709551616")
  v41 = nanDouble(place64)
  v42 = sameBits(9223372036854775807, v41)
  test.assertTrue(v42)
  v43 = nanSingle(place64)
  v44 = convert.float32ToFloat64(v43)
  v45 = sameBits(9223372036317904896, v44)
  test.assertTrue(v45)
  return

test environmentTest "fenv.h's flags are raised, tested, cleared, saved and restored; the rounding mode is set and read back, and a number that is no mode is refused"
  verifies fesetroundC setsMode
  effect use machine.memory
  uses memoryAccess
  effect use system.calls
  uses systemCalls
:begin
  everything = flagCode(31)
  overflowAndInexact = flagCode(20)
  overflow = flagCode(4)
  v1 = feclearexceptC(everything)
  test.assertEqualInt64(0, convert.int32ToInt64(v1))
  v2 = feraiseexceptC(overflowAndInexact)
  test.assertEqualInt64(0, convert.int32ToInt64(v2))
  v3 = fetestexceptC(everything)
  test.assertEqualInt64(convert.int32ToInt64(overflowAndInexact), convert.int32ToInt64(v3))
  v4 = fetestexceptC(overflow)
  test.assertEqualInt64(convert.int32ToInt64(overflow), convert.int32ToInt64(v4))
  v5 = fegetexceptflagC(scratchCell(), everything)
  test.assertEqualInt64(0, convert.int32ToInt64(v5))
  v6 = feclearexceptC(everything)
  test.assertEqualInt64(0, convert.int32ToInt64(v6))
  v7 = fetestexceptC(everything)
  test.assertEqualInt64(0, convert.int32ToInt64(v7))
  v8 = fesetexceptflagC(scratchCell(), overflow)
  test.assertEqualInt64(0, convert.int32ToInt64(v8))
  v9 = fetestexceptC(everything)
  test.assertEqualInt64(convert.int32ToInt64(overflow), convert.int32ToInt64(v9))
  v10 = fegetenvC(scratchText(""))
  test.assertEqualInt64(0, convert.int32ToInt64(v10))
  v11 = feholdexceptC(scratchText(""))
  test.assertEqualInt64(0, convert.int32ToInt64(v11))
  v12 = fetestexceptC(everything)
  test.assertEqualInt64(0, convert.int32ToInt64(v12))
  v13 = fesetenvC(scratchText(""))
  test.assertEqualInt64(0, convert.int32ToInt64(v13))
  v14 = fetestexceptC(everything)
  test.assertEqualInt64(convert.int32ToInt64(overflow), convert.int32ToInt64(v14))
  v15 = feclearexceptC(everything)
  test.assertEqualInt64(0, convert.int32ToInt64(v15))
  inexact = flagCode(16)
  v16 = feclearexceptC(everything)
  test.assertEqualInt64(0, convert.int32ToInt64(v16))
  v17 = nearbyintDouble(convert.uint64BitsToFloat64(4612811918334230528))
  v18 = sameBits(4611686018427387904, v17)
  test.assertTrue(v18)
  v19 = fetestexceptC(inexact)
  test.assertEqualInt64(0, convert.int32ToInt64(v19))
  v20 = rintDouble(convert.uint64BitsToFloat64(4612811918334230528))
  v21 = sameBits(4611686018427387904, v20)
  test.assertTrue(v21)
  v22 = fetestexceptC(inexact)
  test.assertEqualInt64(convert.int32ToInt64(inexact), convert.int32ToInt64(v22))
  v23 = feclearexceptC(everything)
  test.assertEqualInt64(0, convert.int32ToInt64(v23))
  down = modeCode(1)
  nearest = modeCode(0)
  v24 = fegetroundC()
  test.assertEqualInt64(convert.int32ToInt64(nearest), convert.int32ToInt64(v24))
  v25 = fesetroundC(down)
  test.assertEqualInt64(0, convert.int32ToInt64(v25))
  v26 = fegetroundC()
  test.assertEqualInt64(convert.int32ToInt64(down), convert.int32ToInt64(v26))
  v27 = fesetroundC(291)
  test.assertEqualInt64(1, convert.int32ToInt64(v27))
  v28 = fegetroundC()
  test.assertEqualInt64(convert.int32ToInt64(down), convert.int32ToInt64(v28))
  v29 = fesetroundC(nearest)
  test.assertEqualInt64(0, convert.int32ToInt64(v29))
  return
