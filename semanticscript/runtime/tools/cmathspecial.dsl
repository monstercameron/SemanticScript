module cmathspecial "The special functions of math.h in SemanticScript: sinh, cosh, tanh, asinh, acosh, atanh, erf, erfc, tgamma, and lgamma, for double and float, as glibc gives them in the C locale (D-153)"
  path cmathspecial
  imports standard.machine standard.math standard.compare standard.convert standard.bits standard.logic standard.test kernel clibrary
  exports none

capability memoryAccess "Authority to read and write the module's cells in machine.state" use machine.memory none

## The cells of machine.state that belong to this module, bytes 24576 to 24831: 24576 the low half of the
## double-double a routine last gave, 24584 the power of two an exp left out of its result, 24592 the sign lgamma
## last gave as an int (what glibc keeps in `signgam`, which a C library cannot export as a data symbol here), 24600
## the sign lgamma's core left for its callers.
constant lowAt "Where the low half of a double-double result is kept, in machine.state" Int64 24576

constant scaleAt "Where the power of two an exp leaves out of its result is kept, in machine.state" Int64 24584

constant signAt "Where the sign lgamma last gave, an int, is kept, in machine.state" Int64 24592

constant signWorkAt "Where the sign the gamma core found is kept, in machine.state" Int64 24600

op loadLow "The low half of the double-double the last routine gave"
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  cell = kernel.stateAt(lowAt)
  value = machine.loadFloat64(cell)
  return value

op storeLow "Keep the low half of a double-double result"
  input value Float64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  cell = kernel.stateAt(lowAt)
  machine.storeFloat64(cell, value)
  return

op loadScale "The power of two the last exp left out of its result"
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  cell = kernel.stateAt(scaleAt)
  value = machine.loadInt64(cell)
  return value

op storeScale "Keep the power of two an exp leaves out of its result"
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  cell = kernel.stateAt(scaleAt)
  machine.storeInt64(cell, value)
  return

op loadSignWork "The sign (1 or -1) the gamma core last found"
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  cell = kernel.stateAt(signWorkAt)
  value = machine.loadInt64(cell)
  return value

op storeSignWork "Keep the sign (1 or -1) the gamma core found"
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  cell = kernel.stateAt(signWorkAt)
  machine.storeInt64(cell, value)
  return

op storeSignInt "Keep the sign lgamma gave, as the int glibc's signgam holds"
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  cell = kernel.stateAt(signAt)
  calc narrow = convert.int64ToInt32(value)
  machine.storeInt32(cell, narrow)
  return

op magnitudeOf "The value with its sign bit cleared"
  input value Float64 copied
  output Float64
:begin
  calc cleared = convert.float64BitsToUInt64(value) & 9223372036854775807
  calc result = convert.uint64BitsToFloat64(cleared)
  return result

op withSign "The magnitude of one value with the sign of another"
  input magnitude Float64 copied
  input sign Float64 copied
  output Float64
:begin
  calc cleared = convert.float64BitsToUInt64(magnitude) & 9223372036854775807
  calc signOnly = convert.float64BitsToUInt64(sign) & 9223372036854775808
  calc result = convert.uint64BitsToFloat64(cleared | signOnly)
  return result

op isNotNumber "Whether a double is a NaN"
  input value Float64 copied
  output Bool
:begin
  calc cleared = convert.float64BitsToUInt64(value) & 9223372036854775807
  calc nan = cleared > 9218868437227405312
  return nan

op powerOfTwo "2 to a power from -1022 to 1023, made from its bits"
  input power Int64 copied
  output Float64
:begin
  calc field = convert.int64BitsToUInt64(power + 1023)
  calc result = convert.uint64BitsToFloat64(field << 52)
  return result

op scaleBy "A double times 2 to a power, exactly except for the one rounding of a subnormal or an overflow (the power is kept within 2040)"
  input value Float64 copied
  input power Int64 copied
  output Float64
  let k Int64 0 mut
:begin
  calc k := power
  when k > 2040 clampHigh checkLow
:clampHigh
  calc k := 2040
  goto split
:checkLow
  when k < -2040 clampLow split
:clampLow
  calc k := -2040
  goto split
:split
  calc half = k / 2
  calc rest = k - half
  calc first = value * powerOfTwo(half)
  calc second = first * powerOfTwo(rest)
  return second

op floorValue "The greatest whole number not above a double of magnitude under 2^62"
  input value Float64 copied
  output Float64
:begin
  calc truncated = convert.int64ToFloat64(convert.float64ToInt64(value))
  when truncated > value lower keep
:lower
  calc lowered = truncated - 1.0
  return lowered
:keep
  return truncated

op ddAdd "The sum of two double-doubles (their high halves with two-sum, their low halves likewise), the low half left in the cell"
  input ah Float64 copied
  input al Float64 copied
  input bh Float64 copied
  input bl Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc s = ah + bh
  calc bb = s - ah
  calc e = (ah - (s - bb)) + (bh - bb)
  calc t = al + bl
  calc bt = t - al
  calc f = (al - (t - bt)) + (bl - bt)
  calc e2 = e + t
  calc s2 = s + e2
  calc e3 = e2 - (s2 - s)
  calc e4 = e3 + f
  calc s3 = s2 + e4
  calc lo = e4 - (s3 - s2)
  storeLow(lo)
  return s3

op ddMul "The product of two double-doubles with Dekker's exact product of the high halves (no fused multiply-add), the low half left in the cell"
  input ah Float64 copied
  input al Float64 copied
  input bh Float64 copied
  input bl Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc p = ah * bh
  calc a1 = ah * 134217729.0
  calc a2 = a1 - (a1 - ah)
  calc a3 = ah - a2
  calc b1 = bh * 134217729.0
  calc b2 = b1 - (b1 - bh)
  calc b3 = bh - b2
  calc e = ((a2 * b2 - p) + a2 * b3 + a3 * b2) + a3 * b3
  calc e2 = e + (ah * bl + al * bh)
  calc s = p + e2
  calc lo = e2 - (s - p)
  storeLow(lo)
  return s

op ddDivide "The quotient of two double-doubles by three corrections, the low half left in the cell"
  input ah Float64 copied
  input al Float64 copied
  input bh Float64 copied
  input bl Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc q1 = ah / bh
  calc p1 = ddMul(q1, 0.0, bh, bl)
  calc p1l = loadLow()
  calc r1 = ddAdd(ah, al, -p1, -p1l)
  calc r1l = loadLow()
  calc q2 = r1 / bh
  calc p2 = ddMul(q2, 0.0, bh, bl)
  calc p2l = loadLow()
  calc r2 = ddAdd(r1, r1l, -p2, -p2l)
  calc r2l = loadLow()
  calc q3 = r2 / bh
  calc s1 = q1 + q2
  calc l1 = q2 - (s1 - q1)
  calc result = ddAdd(s1, l1, q3, 0.0)
  return result

op ddSquareRoot "The square root of a positive double-double: the root of its high half and one correction, the low half left in the cell"
  input ah Float64 copied
  input al Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc s = machine.squareRoot(ah)
  calc p = ddMul(s, 0.0, s, 0.0)
  calc pl = loadLow()
  calc r = ddAdd(ah, al, -p, -pl)
  calc rl = loadLow()
  calc c = (r + rl) / (2.0 * s)
  calc t = s + c
  calc l = c - (t - s)
  storeLow(l)
  return t

op expScaled "e to the power of a double-double, as a double-double times 2 to a power: the high half is the result, the low half is left in the cell and the power in its own"
  input xh Float64 copied
  input xl Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc kd = xh * 0x1.71547652b82fep+0
  calc kk = convert.float64ToInt64(kd + 4096.5) - 4096
  calc kf = convert.int64ToFloat64(kk)
  calc r0 = xh - kf * 0x1.62e42ff000000p-1
  calc kc2 = kf * -0x1.718432a000000p-35
  calc r1 = r0 - kc2
  calc bb = r1 - r0
  calc e1 = (r0 - (r1 - bb)) + ((0.0 - kc2) - bb)
  calc e2 = 0.0 - kf * -0x1.b0e2633fe0685p-67
  calc u = e1 + e2
  calc r2 = r1 + u
  calc bb2 = r2 - r1
  calc e3 = (r1 - (r2 - bb2)) + (u - bb2)
  calc rh = ddAdd(r2, e3, xl, 0.0)
  calc rl = loadLow()
  calc sh = rh * 0.00390625
  calc sl = rl * 0.00390625
  calc s2h = ddMul(sh, sl, sh, sl)
  calc s2l = loadLow()
  calc s3h = ddMul(s2h, s2l, sh, sl)
  calc s3l = loadLow()
  calc tail = 0x1.5555555555555p-5 + sh * (0x1.1111111111111p-7 + sh * (0x1.6c16c16c16c17p-10 + sh * (0x1.a01a01a01a01ap-13 + sh * 0x1.a01a01a01a01ap-16)))
  calc s4 = s2h * s2h
  calc p1 = ddAdd(sh, sl, s2h * 0.5, s2l * 0.5)
  calc p1l = loadLow()
  calc q3 = ddMul(s3h, s3l, 0x1.5555555555555p-3, 0x1.5555555555555p-57)
  calc q3l = loadLow()
  calc p2 = ddAdd(p1, p1l, q3, q3l)
  calc p2l = loadLow()
  calc p3 = ddAdd(p2, p2l, s4 * tail, 0.0)
  calc p3l = loadLow()
  calc sq0 = ddMul(p3, p3l, p3, p3l)
  calc sq0l = loadLow()
  calc pw0 = ddAdd(2.0 * p3, 2.0 * p3l, sq0, sq0l)
  calc pw0l = loadLow()
  calc sq1 = ddMul(pw0, pw0l, pw0, pw0l)
  calc sq1l = loadLow()
  calc pw1 = ddAdd(2.0 * pw0, 2.0 * pw0l, sq1, sq1l)
  calc pw1l = loadLow()
  calc sq2 = ddMul(pw1, pw1l, pw1, pw1l)
  calc sq2l = loadLow()
  calc pw2 = ddAdd(2.0 * pw1, 2.0 * pw1l, sq2, sq2l)
  calc pw2l = loadLow()
  calc sq3 = ddMul(pw2, pw2l, pw2, pw2l)
  calc sq3l = loadLow()
  calc pw3 = ddAdd(2.0 * pw2, 2.0 * pw2l, sq3, sq3l)
  calc pw3l = loadLow()
  calc sq4 = ddMul(pw3, pw3l, pw3, pw3l)
  calc sq4l = loadLow()
  calc pw4 = ddAdd(2.0 * pw3, 2.0 * pw3l, sq4, sq4l)
  calc pw4l = loadLow()
  calc sq5 = ddMul(pw4, pw4l, pw4, pw4l)
  calc sq5l = loadLow()
  calc pw5 = ddAdd(2.0 * pw4, 2.0 * pw4l, sq5, sq5l)
  calc pw5l = loadLow()
  calc sq6 = ddMul(pw5, pw5l, pw5, pw5l)
  calc sq6l = loadLow()
  calc pw6 = ddAdd(2.0 * pw5, 2.0 * pw5l, sq6, sq6l)
  calc pw6l = loadLow()
  calc sq7 = ddMul(pw6, pw6l, pw6, pw6l)
  calc sq7l = loadLow()
  calc pw7 = ddAdd(2.0 * pw6, 2.0 * pw6l, sq7, sq7l)
  calc pw7l = loadLow()
  calc m = ddAdd(1.0, 0.0, pw7, pw7l)
  storeScale(kk)
  return m

op expPlain "e to the power of a double-double with the power of two applied, as a double-double; the low half is left in the cell"
  input xh Float64 copied
  input xl Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc m = expScaled(xh, xl)
  calc lo = loadLow()
  calc k = loadScale()
  calc hi2 = scaleBy(m, k)
  calc lo2 = scaleBy(lo, k)
  storeLow(lo2)
  return hi2

op crudeLog "The natural log of a double from 0.7 to 1.42 to about 2^-52 relative (a series in ((m-1)/(m+1))^2)"
  input m Float64 copied
  output Float64
:begin
  calc s = (m - 1.0) / (m + 1.0)
  calc z = s * s
  calc p1 = 0x1.47ae147ae147bp-5 + z * 0x1.2f684bda12f68p-5
  calc p2 = 0x1.642c8590b2164p-5 + z * p1
  calc p3 = 0x1.8618618618618p-5 + z * p2
  calc p4 = 0x1.af286bca1af28p-5 + z * p3
  calc p5 = 0x1.e1e1e1e1e1e1ep-5 + z * p4
  calc p6 = 0x1.1111111111111p-4 + z * p5
  calc p7 = 0x1.3b13b13b13b14p-4 + z * p6
  calc p8 = 0x1.745d1745d1746p-4 + z * p7
  calc p9 = 0x1.c71c71c71c71cp-4 + z * p8
  calc p10 = 0x1.2492492492492p-3 + z * p9
  calc p11 = 0x1.999999999999ap-3 + z * p10
  calc p12 = 0x1.5555555555555p-2 + z * p11
  calc result = 2.0 * s * (1.0 + z * p12)
  return result

op logNormal "The natural log of a double-double whose high half is a normal positive number, as a double-double: the high half is the result, the low half is left in the cell"
  input xh Float64 copied
  input xl Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  let a Float64 1.0 mut
  let e Int64 0 mut
:begin
  calc bits0 = convert.float64BitsToUInt64(xh)
  calc field = convert.uint64BitsToInt64((bits0 >> 52) & 2047)
  calc mbits = (bits0 & 4503599627370495) | 4607182418800017408
  calc m = convert.uint64BitsToFloat64(mbits)
  calc exponent0 = field - 1023
  when m >= 1.4142135623730951 high keep
:high
  calc a := m * 0.5
  calc e := exponent0 + 1
  goto joined
:keep
  calc a := m
  calc e := exponent0
  goto joined
:joined
  calc al = scaleBy(xl, 0 - e)
  calc y0 = crudeLog(a)
  calc eh = expScaled(-y0, 0.0)
  calc el = loadLow()
  calc ek = loadScale()
  calc eh2 = scaleBy(eh, ek)
  calc el2 = scaleBy(el, ek)
  calc ph = ddMul(a, al, eh2, el2)
  calc pl = loadLow()
  calc dh = ddAdd(ph, pl, -1.0, 0.0)
  calc dl = loadLow()
  calc corr = dh - 0.5 * dh * dh
  calc rh = ddAdd(y0, 0.0, corr, dl)
  calc rl = loadLow()
  when e == 0 plain shifted
:plain
  return rh
:shifted
  calc ef = convert.int64ToFloat64(e)
  calc t1 = ef * 0x1.62e42ff000000p-1
  calc t2 = ef * -0x1.718432a000000p-35
  calc ts = t1 + t2
  calc tb = ts - t1
  calc te = (t1 - (ts - tb)) + (t2 - tb)
  calc lh = ddAdd(ts, te, ef * -0x1.b0e2633fe0685p-67, 0.0)
  calc ll = loadLow()
  calc result = ddAdd(lh, ll, rh, rl)
  return result

op logDD "The natural log of a positive double-double, as a double-double: the high half is the result, the low half is left in the cell"
  input xh Float64 copied
  input xl Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc field = convert.uint64BitsToInt64((convert.float64BitsToUInt64(xh) >> 52) & 2047)
  when field == 0 subnormal normal
:subnormal
  calc sh = xh * 0x1.0000000000000p+200
  calc sl = xl * 0x1.0000000000000p+200
  calc lh = logNormal(sh, sl)
  calc ll = loadLow()
  calc ah = ddAdd(lh, ll, -(200.0 * 0x1.62e42ff000000p-1), 0.0)
  calc al = loadLow()
  calc bh = ddAdd(ah, al, -(200.0 * -0x1.718432a000000p-35), -(200.0 * -0x1.b0e2633fe0685p-67))
  return bh
:normal
  calc result = logNormal(xh, xl)
  return result

op hyperbolicSine "sinh: the hyperbolic sine, within 0.5001 ulp (correctly rounded but for the rarest cases); +-0 and +-infinity as they are, an overflow +-infinity with ERANGE"
  invariant sineIsAccurate "Gives sinh within 0.51 ulp, keeping the sign of zero and infinity"
  input value Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "sinh"
  let argument Float64 0.0 mut
:begin
  when isNotNumber(value) sNan sNumber
:sNan
  calc quiet = value + value
  return quiet
:sNumber
  calc magnitude = magnitudeOf(value)
  when magnitude < 0x1p-27 same checkInfinite
:same
  return value
:checkInfinite
  when magnitude > 1.7976931348623157e308 same checkLarge
:checkLarge
  when magnitude >= 40.0 large middle
:large
  calc argument := magnitude
  when magnitude > 1000.0 clamp compute
:clamp
  calc argument := 1000.0
  goto compute
:compute
  calc e0 = expScaled(argument, 0.0)
  calc k = loadScale()
  calc big = scaleBy(e0, k - 1)
  when big > 1.7976931348623157e308 overflowed finish
:overflowed
  clibrary.setErrno(34)
  goto finish
:finish
  calc signedBig = withSign(big, value)
  return signedBig
:middle
  calc eh = expPlain(magnitude, 0.0)
  calc el = loadLow()
  calc ih = ddDivide(1.0, 0.0, eh, el)
  calc il = loadLow()
  calc dh = ddAdd(eh, el, -ih, -il)
  calc half = dh * 0.5
  calc signedHalf = withSign(half, value)
  return signedHalf

op hyperbolicCosine "cosh: the hyperbolic cosine, within 0.5001 ulp; +infinity for +-infinity, an overflow +infinity with ERANGE"
  invariant cosineIsAccurate "Gives cosh within 0.51 ulp, 1 for 0"
  input value Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "cosh"
  let unity Float64 1.0
  let argument Float64 0.0 mut
:begin
  when isNotNumber(value) cNan cNumber
:cNan
  calc quiet = value + value
  return quiet
:cNumber
  calc magnitude = magnitudeOf(value)
  when magnitude > 1.7976931348623157e308 infinite checkTiny
:infinite
  return magnitude
:checkTiny
  when magnitude < 0x1p-27 small checkLarge
:small
  return unity
:checkLarge
  when magnitude >= 40.0 large middle
:large
  calc argument := magnitude
  when magnitude > 1000.0 clamp compute
:clamp
  calc argument := 1000.0
  goto compute
:compute
  calc e0 = expScaled(argument, 0.0)
  calc k = loadScale()
  calc big = scaleBy(e0, k - 1)
  when big > 1.7976931348623157e308 overflowed finish
:overflowed
  clibrary.setErrno(34)
  goto finish
:finish
  return big
:middle
  calc eh = expPlain(magnitude, 0.0)
  calc el = loadLow()
  calc ih = ddDivide(1.0, 0.0, eh, el)
  calc il = loadLow()
  calc dh = ddAdd(eh, el, ih, il)
  calc half = dh * 0.5
  return half

op hyperbolicTangent "tanh: the hyperbolic tangent, within 0.5001 ulp; +-1 from 22 up"
  invariant tangentIsAccurate "Gives tanh within 0.51 ulp, keeping the sign of zero"
  input value Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "tanh"
:begin
  when isNotNumber(value) tNan tNumber
:tNan
  calc quiet = value + value
  return quiet
:tNumber
  calc magnitude = magnitudeOf(value)
  when magnitude < 0x1p-27 same checkLarge
:same
  return value
:checkLarge
  when magnitude >= 22.0 one middle
:one
  calc signedOne = withSign(1.0, value)
  return signedOne
:middle
  calc eh = expPlain(2.0 * magnitude, 0.0)
  calc el = loadLow()
  calc nh = ddAdd(eh, el, -1.0, 0.0)
  calc nl = loadLow()
  calc dh = ddAdd(eh, el, 1.0, 0.0)
  calc dl = loadLow()
  calc qh = ddDivide(nh, nl, dh, dl)
  calc signed = withSign(qh, value)
  return signed

op inverseHyperbolicSine "asinh: the inverse hyperbolic sine, within 0.5001 ulp: log(|x| + sqrt(x^2 + 1)) in double-double, log(2|x|) from 2^28"
  invariant asinhIsAccurate "Gives asinh within 0.51 ulp, keeping the sign of zero and infinity"
  input value Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "asinh"
:begin
  when isNotNumber(value) aNan aNumber
:aNan
  calc quiet = value + value
  return quiet
:aNumber
  calc magnitude = magnitudeOf(value)
  when magnitude < 0x1p-27 same checkInfinite
:same
  return value
:checkInfinite
  when magnitude > 1.7976931348623157e308 same checkLarge
:checkLarge
  when magnitude >= 0x1p28 large middle
:large
  calc lh = logDD(magnitude, 0.0)
  calc ll = loadLow()
  calc rh = ddAdd(lh, ll, 0x1.62e42fefa39efp-1, -0x1.b0e2633fe0685p-67)
  calc signedLarge = withSign(rh, value)
  return signedLarge
:middle
  calc ph = ddMul(magnitude, 0.0, magnitude, 0.0)
  calc pl = loadLow()
  calc qh = ddAdd(ph, pl, 1.0, 0.0)
  calc ql = loadLow()
  calc sh = ddSquareRoot(qh, ql)
  calc sl = loadLow()
  calc wh = ddAdd(magnitude, 0.0, sh, sl)
  calc wl = loadLow()
  calc mh = logDD(wh, wl)
  calc signedMiddle = withSign(mh, value)
  return signedMiddle

op inverseHyperbolicCosine "acosh: the inverse hyperbolic cosine, within 0.5001 ulp; NaN below 1 with EDOM"
  invariant acoshIsAccurate "Gives acosh within 0.51 ulp, 0 for 1, NaN below 1"
  input value Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "acosh"
  let nothing Float64 0.0
:begin
  when isNotNumber(value) cNan cNumber
:cNan
  calc quiet = value + value
  return quiet
:cNumber
  when value < 1.0 below checkOne
:below
  clibrary.setErrno(33)
  calc invalid = convert.uint64BitsToFloat64(9221120237041090560)
  return invalid
:checkOne
  when value == 1.0 zero checkInfinite
:zero
  return nothing
:checkInfinite
  when value > 1.7976931348623157e308 same checkLarge
:same
  return value
:checkLarge
  when value >= 0x1p28 large middle
:large
  calc lh = logDD(value, 0.0)
  calc ll = loadLow()
  calc rh = ddAdd(lh, ll, 0x1.62e42fefa39efp-1, -0x1.b0e2633fe0685p-67)
  return rh
:middle
  calc t = value - 1.0
  calc ph = ddMul(t, 0.0, t, 0.0)
  calc pl = loadLow()
  calc qh = ddAdd(2.0 * t, 0.0, ph, pl)
  calc ql = loadLow()
  calc sh = ddSquareRoot(qh, ql)
  calc sl = loadLow()
  calc wh = ddAdd(t, 0.0, sh, sl)
  calc wl = loadLow()
  calc uh = ddAdd(1.0, 0.0, wh, wl)
  calc ul = loadLow()
  calc mh = logDD(uh, ul)
  return mh

op inverseHyperbolicTangent "atanh: the inverse hyperbolic tangent, within 0.5001 ulp: half the log of (1+x)/(1-x) in double-double; +-1 gives +-infinity with ERANGE, more than 1 NaN with EDOM"
  invariant atanhIsAccurate "Gives atanh within 0.51 ulp, keeping the sign of zero; +-infinity at +-1; NaN beyond"
  input value Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "atanh"
:begin
  when isNotNumber(value) tNan tNumber
:tNan
  calc quiet = value + value
  return quiet
:tNumber
  calc magnitude = magnitudeOf(value)
  when magnitude > 1.0 beyond checkOne
:beyond
  clibrary.setErrno(33)
  calc invalid = convert.uint64BitsToFloat64(9221120237041090560)
  return invalid
:checkOne
  when magnitude == 1.0 pole checkTiny
:pole
  clibrary.setErrno(34)
  calc infinity = convert.uint64BitsToFloat64(9218868437227405312)
  calc signedInfinity = withSign(infinity, value)
  return signedInfinity
:checkTiny
  when magnitude < 0x1p-27 same middle
:same
  return value
:middle
  calc s1 = 1.0 - magnitude
  calc bb = s1 - 1.0
  calc e = (1.0 - (s1 - bb)) + ((0.0 - magnitude) - bb)
  calc uh = ddDivide(2.0 * magnitude, 0.0, s1, e)
  calc ul = loadLow()
  calc vh = ddAdd(1.0, 0.0, uh, ul)
  calc vl = loadLow()
  calc lh = logDD(vh, vl)
  calc half = lh * 0.5
  calc signed = withSign(half, value)
  return signed

op erfSeries "erf of a double from 2^-30 to 3 as a double-double, by the series with no cancellation: 2/sqrt(pi) e^(-x^2) times the sum of 2^n x^(2n+1) / (1 3 5 ... (2n+1)); the low half is left in the cell"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  let th Float64 0.0 mut
  let tl Float64 0.0 mut
  let sh Float64 0.0 mut
  let sl Float64 0.0 mut
  let nf Float64 3.0 mut
:begin
  calc ph = ddMul(x, 0.0, x, 0.0)
  calc pl = loadLow()
  calc wh = 2.0 * ph
  calc wl = 2.0 * pl
  calc th := x
  calc sh := x
  calc tl := 0.0
  calc sl := 0.0
  calc nf := 3.0
  goto eachTerm
:eachTerm loop=while max=400
  when th < sh * 0x1p-110 finished term
:term in=eachTerm
  calc t1 = ddMul(th, tl, wh, wl)
  calc t1l = loadLow()
  calc t2 = ddDivide(t1, t1l, nf, 0.0)
  calc t2l = loadLow()
  calc s1 = ddAdd(sh, sl, t2, t2l)
  calc s1l = loadLow()
  calc th := t2
  calc tl := t2l
  calc sh := s1
  calc sl := s1l
  calc nf := nf + 2.0
  goto eachTerm
:finished
  calc eh = expPlain(-ph, -pl)
  calc el = loadLow()
  calc mh = ddMul(sh, sl, eh, el)
  calc ml = loadLow()
  calc rh = ddMul(mh, ml, 0x1.20dd750429b6dp+0, 0x1.1ae3a914fed80p-56)
  return rh

op erfcLarge "erfc of a double from 3 to 27.3 as a double-double times a power of two, by Laplace's continued fraction evaluated from the bottom: e^(-x^2) / (sqrt(pi) (x + (1/2) / (x + (2/2) / (x + ...)))); the low half and the power are left in their cells"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  let th Float64 0.0 mut
  let tl Float64 0.0 mut
  let kf Float64 0.0 mut
:begin
  calc depth = convert.int64ToFloat64(convert.float64ToInt64(6.0 + 240.0 / x))
  calc kf := depth
  calc th := x
  calc tl := 0.0
  goto eachLevel
:eachLevel loop=while max=400
  when kf < 0.5 finished level
:level in=eachLevel
  calc qh = ddDivide(kf * 0.5, 0.0, th, tl)
  calc ql = loadLow()
  calc nh = ddAdd(x, 0.0, qh, ql)
  calc nl = loadLow()
  calc th := nh
  calc tl := nl
  calc kf := kf - 1.0
  goto eachLevel
:finished
  calc ph = ddMul(x, 0.0, x, 0.0)
  calc pl = loadLow()
  calc eh = expScaled(-ph, -pl)
  calc el = loadLow()
  calc k = loadScale()
  calc dh = ddDivide(eh, el, th, tl)
  calc dl = loadLow()
  calc rh = ddMul(dh, dl, 0x1.20dd750429b6dp-1, 0x1.1ae3a914fed80p-57)
  storeScale(k)
  return rh

op errorFunction "erf: the error function, within 0.5001 ulp; +-0 as it is, +-1 for +-infinity"
  invariant erfIsAccurate "Gives erf within 0.51 ulp, odd, keeping the sign of zero, +-1 from 6 up"
  input value Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "erf"
:begin
  when isNotNumber(value) eNan eNumber
:eNan
  calc quiet = value + value
  return quiet
:eNumber
  calc magnitude = magnitudeOf(value)
  when magnitude < 0x1p-30 tiny checkLarge
:tiny
  when magnitude == 0.0 same scaled
:same
  return value
:scaled
  calc y = value * 0x1p100
  calc th = ddMul(y, 0.0, 0x1.20dd750429b6dp+0, 0x1.1ae3a914fed80p-56)
  calc small = scaleBy(th, -100)
  return small
:checkLarge
  when magnitude >= 6.0 saturated checkSmall
:saturated
  calc signedOne = withSign(1.0, value)
  return signedOne
:checkSmall
  when magnitude < 3.0 series continued
:series
  calc sh = erfSeries(magnitude)
  calc signedSeries = withSign(sh, value)
  return signedSeries
:continued
  calc ch = erfcLarge(magnitude)
  calc cl = loadLow()
  calc k = loadScale()
  calc sch = scaleBy(ch, k)
  calc scl = scaleBy(cl, k)
  calc rh = ddAdd(1.0, 0.0, -sch, -scl)
  calc signedContinued = withSign(rh, value)
  return signedContinued

op complementaryErrorFunction "erfc: 1 - erf, within 0.5001 ulp (an underflow to a subnormal or 0 sets ERANGE); 0 for +infinity, 2 for -infinity"
  invariant erfcIsAccurate "Gives erfc within 0.51 ulp, 2 from -6 down, 0 from 27.3 up"
  input value Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "erfc"
  let nothing Float64 0.0
  let pair Float64 2.0
  let unity Float64 1.0
:begin
  when isNotNumber(value) eNan eNumber
:eNan
  calc quiet = value + value
  return quiet
:eNumber
  when value > 1.7976931348623157e308 zero checkMinusInfinity
:zero
  return nothing
:checkMinusInfinity
  when value < -1.7976931348623157e308 twice checkNegative
:twice
  return pair
:checkNegative
  when value < -6.0 twice checkPositive
:checkPositive
  when value > 27.25 vanished checkTiny
:vanished
  clibrary.setErrno(34)
  return nothing
:checkTiny
  calc magnitude = magnitudeOf(value)
  when magnitude < 0x1p-60 whole checkRange
:whole
  return unity
:checkRange
  when magnitude < 3.0 smallRange largeRange
:smallRange
  calc eh = erfSeries(magnitude)
  calc el = loadLow()
  calc ch = ddAdd(1.0, 0.0, -eh, -el)
  calc cl = loadLow()
  when value < 0.0 negativeSmall positiveSmall
:positiveSmall
  return ch
:negativeSmall
  calc rh = ddAdd(2.0, 0.0, -ch, -cl)
  return rh
:largeRange
  calc lh = erfcLarge(magnitude)
  calc ll = loadLow()
  calc k = loadScale()
  when value < 0.0 negativeLarge positiveLarge
:positiveLarge
  calc scaled = scaleBy(lh, k)
  when scaled < 2.2250738585072014e-308 underflowed finish
:underflowed
  clibrary.setErrno(34)
  goto finish
:finish
  return scaled
:negativeLarge
  calc sh = scaleBy(lh, k)
  calc sl = scaleBy(ll, k)
  calc nh = ddAdd(2.0, 0.0, -sh, -sl)
  return nh

op stirling "ln gamma of a double-double of 24 or more, as a double-double, by Stirling's series: (z - 1/2) ln z - z + (1/2) ln 2 pi plus the Bernoulli terms up to 2^30, where they are dropped; the low half is left in the cell"
  input zh Float64 copied
  input zl Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc lh = logDD(zh, zl)
  calc ll = loadLow()
  calc ah = ddAdd(zh, zl, -0.5, 0.0)
  calc al = loadLow()
  calc ph = ddMul(ah, al, lh, ll)
  calc pl = loadLow()
  calc qh = ddAdd(ph, pl, -zh, -zl)
  calc ql = loadLow()
  calc rh = ddAdd(qh, ql, 0x1.d67f1c864beb5p-1, -0x1.65b5a1b7ff5dfp-55)
  calc rl = loadLow()
  when zh < 0x1p30 series done
:done
  return rh
:series
  calc ih = ddDivide(1.0, 0.0, zh, zl)
  calc il = loadLow()
  calc wh = ddMul(ih, il, ih, il)
  calc wl = loadLow()
  calc hm0 = ddMul(-0x1.d1089b142d357p+23, -0x1.e2030b4d5de20p-31, wh, wl)
  calc hm0l = loadLow()
  calc ha0 = ddAdd(hm0, hm0l, 0x1.51a2089a6e11ap+19, 0x1.c219ee4fdc447p-36)
  calc ha0l = loadLow()
  calc hm1 = ddMul(ha0, ha0l, wh, wl)
  calc hm1l = loadLow()
  calc ha1 = ddAdd(hm1, hm1l, -0x1.1a198ae1c4ab8p+15, 0x1.4c012227b696ep-41)
  calc ha1l = loadLow()
  calc hm2 = ddMul(ha1, ha1l, wh, wl)
  calc hm2l = loadLow()
  calc ha2 = ddAdd(hm2, hm2l, 0x1.12234e81b4e82p+11, -0x1.2c5f92c5f92c6p-43)
  calc ha2l = loadLow()
  calc hm3 = ddMul(ha2, ha2l, wh, wl)
  calc hm3l = loadLow()
  calc ha3 = ddAdd(hm3, hm3l, -0x1.39b2525cccc1bp+7, 0x1.52604768a30fcp-47)
  calc ha3l = loadLow()
  calc hm4 = ddMul(ha3, ha3l, wh, wl)
  calc hm4l = loadLow()
  calc ha4 = ddAdd(hm4, hm4l, 0x1.ace44322ce006p+3, -0x1.62c2b1bbcdd32p-51)
  calc ha4l = loadLow()
  calc hm5 = ddMul(ha4, ha4l, wh, wl)
  calc hm5l = loadLow()
  calc ha5 = ddAdd(hm5, hm5l, -0x1.6476701181f3ap+0, 0x1.24246319da678p-56)
  calc ha5l = loadLow()
  calc hm6 = ddMul(ha5, ha5l, wh, wl)
  calc hm6l = loadLow()
  calc ha6 = ddAdd(hm6, hm6l, 0x1.6fe96381e0680p-3, -0x1.79e2405a71f88p-61)
  calc ha6l = loadLow()
  calc hm7 = ddMul(ha6, ha6l, wh, wl)
  calc hm7l = loadLow()
  calc ha7 = ddAdd(hm7, hm7l, -0x1.e4286cb0f5398p-6, 0x1.1efcdab896745p-61)
  calc ha7l = loadLow()
  calc hm8 = ddMul(ha7, ha7l, wh, wl)
  calc hm8l = loadLow()
  calc ha8 = ddAdd(hm8, hm8l, 0x1.a41a41a41a41ap-8, 0x1.0690690690690p-62)
  calc ha8l = loadLow()
  calc hm9 = ddMul(ha8, ha8l, wh, wl)
  calc hm9l = loadLow()
  calc ha9 = ddAdd(hm9, hm9l, -0x1.f6ab0d9993c7dp-10, 0x1.f82553c999b0ep-64)
  calc ha9l = loadLow()
  calc hm10 = ddMul(ha9, ha9l, wh, wl)
  calc hm10l = loadLow()
  calc ha10 = ddAdd(hm10, hm10l, 0x1.b951e2b18ff23p-11, 0x1.5c3a9ce01b952p-65)
  calc ha10l = loadLow()
  calc hm11 = ddMul(ha10, ha10l, wh, wl)
  calc hm11l = loadLow()
  calc ha11 = ddAdd(hm11, hm11l, -0x1.3813813813814p-11, 0x1.fb1fb1fb1fb20p-65)
  calc ha11l = loadLow()
  calc hm12 = ddMul(ha11, ha11l, wh, wl)
  calc hm12l = loadLow()
  calc ha12 = ddAdd(hm12, hm12l, 0x1.a01a01a01a01ap-11, 0x1.a01a01a01a01ap-71)
  calc ha12l = loadLow()
  calc hm13 = ddMul(ha12, ha12l, wh, wl)
  calc hm13l = loadLow()
  calc ha13 = ddAdd(hm13, hm13l, -0x1.6c16c16c16c17p-9, 0x1.f49f49f49f49fp-64)
  calc ha13l = loadLow()
  calc hm14 = ddMul(ha13, ha13l, wh, wl)
  calc hm14l = loadLow()
  calc ha14 = ddAdd(hm14, hm14l, 0x1.5555555555555p-4, 0x1.5555555555555p-58)
  calc ha14l = loadLow()
  calc th = ddMul(ha14, ha14l, ih, il)
  calc tl = loadLow()
  calc fh = ddAdd(rh, rl, th, tl)
  return fh

op lnGammaPositive "ln gamma of a positive double-double: Stirling's series from 24, below that the argument shifted up by the product x (x+1) ... (x+n-1) whose log is taken off; the low half is left in the cell"
  input xh Float64 copied
  input xl Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  let i Float64 0.0 mut
  let ph Float64 1.0 mut
  let pl Float64 0.0 mut
:begin
  when xh >= 24.0 direct prepare
:direct
  calc dh = stirling(xh, xl)
  return dh
:prepare
  calc n = convert.int64ToFloat64(convert.float64ToInt64(24.0 - xh)) + 1.0
  goto eachFactor
:eachFactor loop=while max=64
  when i >= n shifted factor
:factor in=eachFactor
  calc ah0 = xh + i
  calc bb = ah0 - xh
  calc e0 = (xh - (ah0 - bb)) + (i - bb)
  calc al0 = e0 + xl
  calc ah = ah0 + al0
  calc al = al0 - (ah - ah0)
  calc mh = ddMul(ph, pl, ah, al)
  calc ml = loadLow()
  calc ph := mh
  calc pl := ml
  calc i := i + 1.0
  goto eachFactor
:shifted
  calc zh = ddAdd(xh, xl, n, 0.0)
  calc zl = loadLow()
  calc sh = stirling(zh, zl)
  calc sl = loadLow()
  calc lh = logDD(ph, pl)
  calc ll = loadLow()
  calc rh = ddAdd(sh, sl, -lh, -ll)
  return rh

op lgammaNearOne "ln gamma of 1 + z for z under 2^-16, as a double-double: z (-gamma + z (zeta(2)/2 - z zeta(3)/3 + ...)) to the z^4 term"
  input z Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc inner = 0x1.a51a6625307d3p-1 + z * (-0x1.9a4d55beab2d7p-2 + z * 0x1.151322ac7d848p-2)
  calc t = z * inner
  calc ah = ddAdd(-0x1.2788cfc6fb619p-1, 0x1.6cb90701fbfabp-58, t, 0.0)
  calc al = loadLow()
  calc rh = ddMul(ah, al, z, 0.0)
  return rh

op lgammaNearTwo "ln gamma of 2 + z for z under 2^-16, as a double-double: z ((1 - gamma) + z ((zeta(2)-1)/2 - z (zeta(3)-1)/3 + ...)) to the z^4 term"
  input z Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc inner = 0x1.4a34cc4a60fa6p-2 + z * (-0x1.13e001a557607p-4 + z * 0x1.51322ac7d8483p-6)
  calc t = z * inner
  calc ah = ddAdd(0x1.b0ee6072093cep-2, 0x1.6cb90701fbfabp-58, t, 0.0)
  calc al = loadLow()
  calc rh = ddMul(ah, al, z, 0.0)
  return rh

op sinPiSeries "sin(pi b) for b from 0 to 1/4 as a double-double, by its Taylor series in (pi b)^2; the low half is left in the cell"
  input b Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc uh = ddMul(b, 0.0, 0x1.921fb54442d18p+1, 0x1.1a62633145c07p-53)
  calc ul = loadLow()
  calc wh = ddMul(uh, ul, uh, ul)
  calc wl = loadLow()
  calc qm0 = ddMul(-0x1.d1ab1c2dccea3p-94, -0x1.054d0c78aea14p-149, wh, wl)
  calc qm0l = loadLow()
  calc qa0 = ddAdd(qm0, qm0l, 0x1.3f3ccdd165fa9p-84, -0x1.58ddadf344487p-139)
  calc qa0l = loadLow()
  calc qm1 = ddMul(qa0, qa0l, wh, wl)
  calc qm1l = loadLow()
  calc qa1 = ddAdd(qm1, qm1l, -0x1.761b41316381ap-75, 0x1.3423c7d91404fp-130)
  calc qa1l = loadLow()
  calc qm2 = ddMul(qa1, qa1l, wh, wl)
  calc qm2l = loadLow()
  calc qa2 = ddAdd(qm2, qm2l, 0x1.71b8ef6dcf572p-66, -0x1.d043ae40c4647p-120)
  calc qa2l = loadLow()
  calc qm3 = ddMul(qa2, qa2l, wh, wl)
  calc qm3l = loadLow()
  calc qa3 = ddAdd(qm3, qm3l, -0x1.2f49b46814157p-57, -0x1.2650f61dbdcb4p-112)
  calc qa3l = loadLow()
  calc qm4 = ddMul(qa3, qa3l, wh, wl)
  calc qm4l = loadLow()
  calc qa4 = ddAdd(qm4, qm4l, 0x1.952c77030ad4ap-49, 0x1.ac981465ddc6cp-103)
  calc qa4l = loadLow()
  calc qm5 = ddMul(qa4, qa4l, wh, wl)
  calc qm5l = loadLow()
  calc qa5 = ddAdd(qm5, qm5l, -0x1.ae7f3e733b81fp-41, -0x1.1d8656b0ee8cbp-97)
  calc qa5l = loadLow()
  calc qm6 = ddMul(qa5, qa5l, wh, wl)
  calc qm6l = loadLow()
  calc qa6 = ddAdd(qm6, qm6l, 0x1.6124613a86d09p-33, 0x1.f28e0cc748ebep-87)
  calc qa6l = loadLow()
  calc qm7 = ddMul(qa6, qa6l, wh, wl)
  calc qm7l = loadLow()
  calc qa7 = ddAdd(qm7, qm7l, -0x1.ae64567f544e4p-26, 0x1.c062e06d1f209p-80)
  calc qa7l = loadLow()
  calc qm8 = ddMul(qa7, qa7l, wh, wl)
  calc qm8l = loadLow()
  calc qa8 = ddAdd(qm8, qm8l, 0x1.71de3a556c734p-19, -0x1.c154f8ddc6c00p-73)
  calc qa8l = loadLow()
  calc qm9 = ddMul(qa8, qa8l, wh, wl)
  calc qm9l = loadLow()
  calc qa9 = ddAdd(qm9, qm9l, -0x1.a01a01a01a01ap-13, -0x1.a01a01a01a01ap-73)
  calc qa9l = loadLow()
  calc qm10 = ddMul(qa9, qa9l, wh, wl)
  calc qm10l = loadLow()
  calc qa10 = ddAdd(qm10, qm10l, 0x1.1111111111111p-7, 0x1.1111111111111p-63)
  calc qa10l = loadLow()
  calc qm11 = ddMul(qa10, qa10l, wh, wl)
  calc qm11l = loadLow()
  calc qa11 = ddAdd(qm11, qm11l, -0x1.5555555555555p-3, -0x1.5555555555555p-57)
  calc qa11l = loadLow()
  calc qm12 = ddMul(qa11, qa11l, wh, wl)
  calc qm12l = loadLow()
  calc qa12 = ddAdd(qm12, qm12l, 0x1.0000000000000p+0, 0x0.0p+0)
  calc qa12l = loadLow()
  calc rh = ddMul(qa12, qa12l, uh, ul)
  return rh

op cosPiSeries "cos(pi b) for b from 0 to 1/4 as a double-double, by its Taylor series in (pi b)^2; the low half is left in the cell"
  input b Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc uh = ddMul(b, 0.0, 0x1.921fb54442d18p+1, 0x1.1a62633145c07p-53)
  calc ul = loadLow()
  calc wh = ddMul(uh, ul, uh, ul)
  calc wl = loadLow()
  calc qm0 = ddMul(-0x1.88e85fc6a4e5ap-89, 0x1.71c37ebd16540p-143, wh, wl)
  calc qm0l = loadLow()
  calc qa0 = ddAdd(qm0, qm0l, 0x1.f2cf01972f578p-80, -0x1.9ada5fcc1ab14p-135)
  calc qa0l = loadLow()
  calc qm1 = ddMul(qa0, qa0l, wh, wl)
  calc qm1l = loadLow()
  calc qa1 = ddAdd(qm1, qm1l, -0x1.0ce396db7f853p-70, 0x1.aebcdbd20331cp-124)
  calc qa1l = loadLow()
  calc qm2 = ddMul(qa1, qa1l, wh, wl)
  calc qm2l = loadLow()
  calc qa2 = ddAdd(qm2, qm2l, 0x1.e542ba4020225p-62, 0x1.ea72b4afe3c2fp-120)
  calc qa2l = loadLow()
  calc qm3 = ddMul(qa2, qa2l, wh, wl)
  calc qm3l = loadLow()
  calc qa3 = ddAdd(qm3, qm3l, -0x1.6827863b97d97p-53, -0x1.eec01221a8b0bp-107)
  calc qa3l = loadLow()
  calc qm4 = ddMul(qa3, qa3l, wh, wl)
  calc qm4l = loadLow()
  calc qa4 = ddAdd(qm4, qm4l, 0x1.ae7f3e733b81fp-45, 0x1.1d8656b0ee8cbp-101)
  calc qa4l = loadLow()
  calc qm5 = ddMul(qa4, qa4l, wh, wl)
  calc qm5l = loadLow()
  calc qa5 = ddAdd(qm5, qm5l, -0x1.93974a8c07c9dp-37, -0x1.05d6f8a2efd1fp-92)
  calc qa5l = loadLow()
  calc qm6 = ddMul(qa5, qa5l, wh, wl)
  calc qm6l = loadLow()
  calc qa6 = ddAdd(qm6, qm6l, 0x1.1eed8eff8d898p-29, -0x1.2aec959e14c06p-83)
  calc qa6l = loadLow()
  calc qm7 = ddMul(qa6, qa6l, wh, wl)
  calc qm7l = loadLow()
  calc qa7 = ddAdd(qm7, qm7l, -0x1.27e4fb7789f5cp-22, -0x1.cbbc05b4fa99ap-76)
  calc qa7l = loadLow()
  calc qm8 = ddMul(qa7, qa7l, wh, wl)
  calc qm8l = loadLow()
  calc qa8 = ddAdd(qm8, qm8l, 0x1.a01a01a01a01ap-16, 0x1.a01a01a01a01ap-76)
  calc qa8l = loadLow()
  calc qm9 = ddMul(qa8, qa8l, wh, wl)
  calc qm9l = loadLow()
  calc qa9 = ddAdd(qm9, qm9l, -0x1.6c16c16c16c17p-10, 0x1.f49f49f49f49fp-65)
  calc qa9l = loadLow()
  calc qm10 = ddMul(qa9, qa9l, wh, wl)
  calc qm10l = loadLow()
  calc qa10 = ddAdd(qm10, qm10l, 0x1.5555555555555p-5, 0x1.5555555555555p-59)
  calc qa10l = loadLow()
  calc qm11 = ddMul(qa10, qa10l, wh, wl)
  calc qm11l = loadLow()
  calc qa11 = ddAdd(qm11, qm11l, -0x1.0000000000000p-1, 0x0.0p+0)
  calc qa11l = loadLow()
  calc qm12 = ddMul(qa11, qa11l, wh, wl)
  calc qm12l = loadLow()
  calc qa12 = ddAdd(qm12, qm12l, 0x1.0000000000000p+0, 0x0.0p+0)
  calc qa12l = loadLow()
  return qa12

op sinPi "sin(pi a) for a from 0 to 1/2 as a double-double (the cosine of the rest from 1/4 up); the low half is left in the cell"
  input a Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  when a > 0.25 cosine sine
:cosine
  calc rest = 0.5 - a
  calc ch = cosPiSeries(rest)
  return ch
:sine
  calc sh = sinPiSeries(a)
  return sh

op lgammaCore "ln |gamma(x)| of a finite double that is not 0, a negative whole number, 1 or 2 (x of 2^-70 or less in magnitude: -ln |x|), as a double-double with the low half in the cell and the sign of gamma(x) kept for the callers; for a negative x the reflection formula ln(pi / |sin(pi x)|) - ln gamma(1 - x)"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc magnitude = magnitudeOf(x)
  when magnitude < 0x1p-70 tiny checkSign
:tiny
  calc lh = logDD(magnitude, 0.0)
  calc ll = loadLow()
  calc signBitTiny = convert.uint64BitsToInt64(convert.float64BitsToUInt64(x) >> 63)
  storeSignWork(1 - 2 * signBitTiny)
  storeLow(-ll)
  calc negated = -lh
  return negated
:checkSign
  when x > 0.0 positive negative
:positive
  storeSignWork(1)
  calc distanceOne = magnitudeOf(x - 1.0)
  when distanceOne < 0x1p-16 nearOne checkTwo
:nearOne
  calc zOne = x - 1.0
  calc oh = lgammaNearOne(zOne)
  return oh
:checkTwo
  calc distanceTwo = magnitudeOf(x - 2.0)
  when distanceTwo < 0x1p-16 nearTwo checkHuge
:nearTwo
  calc zTwo = x - 2.0
  calc wh = lgammaNearTwo(zTwo)
  return wh
:checkHuge
  when x >= 0x1p400 huge ordinary
:huge
  calc scaled = x * 0x1p-600
  calc hh = logDD(x, 0.0)
  calc hl = loadLow()
  calc mh = ddAdd(hh, hl, -1.0, 0.0)
  calc ml = loadLow()
  calc ph = ddMul(scaled, 0.0, mh, ml)
  calc pl = loadLow()
  calc bigHigh = scaleBy(ph, 600)
  calc bigLow = scaleBy(pl, 600)
  storeLow(bigLow)
  return bigHigh
:ordinary
  calc gh = lnGammaPositive(x, 0.0)
  return gh
:negative
  calc floored = floorValue(x + 0.5)
  calc r = x - floored
  calc ra = magnitudeOf(r)
  calc sh = sinPi(ra)
  calc sl = loadLow()
  calc parity = convert.float64ToInt64(floored) & 1
  calc rBit = convert.uint64BitsToInt64(convert.float64BitsToUInt64(r) >> 63)
  calc sgn = (1 - 2 * parity) * (1 - 2 * rBit)
  calc sinLogH = logDD(sh, sl)
  calc sinLogL = loadLow()
  calc g1 = 1.0 - x
  calc gb = g1 - 1.0
  calc g2 = (1.0 - (g1 - gb)) + ((0.0 - x) - gb)
  calc gh2 = lnGammaPositive(g1, g2)
  calc gl2 = loadLow()
  calc th = ddAdd(0x1.250d048e7a1bdp+0, 0x1.7abf2ad8d5088p-57, -sinLogH, -sinLogL)
  calc tl = loadLow()
  calc rh = ddAdd(th, tl, -gh2, -gl2)
  storeSignWork(sgn)
  return rh

op gammaFunction "tgamma: the gamma function, within 0.5001 ulp (exp of ln gamma in double-double); a negative whole number gives NaN with EDOM, +-0 gives +-infinity with ERANGE, and an overflow or an underflow sets ERANGE"
  invariant gammaIsAccurate "Gives gamma within 0.51 ulp, exact at whole numbers, with Annex F's poles"
  input value Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "tgamma"
:begin
  when isNotNumber(value) gNan gNumber
:gNan
  calc quiet = value + value
  return quiet
:gNumber
  when value > 1.7976931348623157e308 same checkMinusInfinity
:same
  return value
:checkMinusInfinity
  when value < -1.7976931348623157e308 invalid checkZero
:invalid
  clibrary.setErrno(33)
  calc notNumber = convert.uint64BitsToFloat64(9221120237041090560)
  return notNumber
:checkZero
  when value == 0.0 pole checkTiny
:pole
  clibrary.setErrno(34)
  calc infinite = 1.0 / value
  return infinite
:checkTiny
  calc magnitude = magnitudeOf(value)
  when magnitude < 0x1p-54 tiny general
:tiny
  calc reciprocal = 1.0 / value
  when magnitudeOf(reciprocal) > 1.7976931348623157e308 reciprocalOverflow reciprocalFine
:reciprocalOverflow
  clibrary.setErrno(34)
  return reciprocal
:reciprocalFine
  return reciprocal
:general
  when value < 0.0 negative positive
:negative
  when magnitude >= 0x1p52 invalid2 checkInteger
:invalid2
  clibrary.setErrno(33)
  calc notNumber2 = convert.uint64BitsToFloat64(9221120237041090560)
  return notNumber2
:checkInteger
  calc truncated = convert.int64ToFloat64(convert.float64ToInt64(magnitude))
  when truncated == magnitude invalid2 compute
:positive
  when value >= 172.0 overflowing compute
:overflowing
  clibrary.setErrno(34)
  calc infinity = convert.uint64BitsToFloat64(9218868437227405312)
  return infinity
:compute
  calc lh = lgammaCore(value)
  calc ll = loadLow()
  calc sign = loadSignWork()
  calc signValue = convert.int64ToFloat64(sign)
  when lh < -800.0 underflow exponent
:underflow
  clibrary.setErrno(34)
  calc signedZero = 0.0 * signValue
  return signedZero
:exponent
  calc mh = expScaled(lh, ll)
  calc k = loadScale()
  calc r = scaleBy(mh, k)
  when r > 1.7976931348623157e308 range checkSmall
:checkSmall
  when r < 2.2250738585072014e-308 range fine
:range
  clibrary.setErrno(34)
  goto fine
:fine
  calc signed = r * signValue
  return signed

op lgammaValue "lgamma without the sign's store: ln |gamma(x)| within 0.5001 ulp, the sign of gamma(x) kept in the gamma core's cell; +infinity with ERANGE at 0 and the negative whole numbers, +0 at 1 and 2, +infinity for +-infinity"
  input value Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  let nothing Float64 0.0
:begin
  when isNotNumber(value) notNumber checkInfinite
:notNumber
  storeSignWork(1)
  calc quiet = value + value
  return quiet
:checkInfinite
  calc magnitude = magnitudeOf(value)
  when magnitude > 1.7976931348623157e308 infinite checkZero
:infinite
  storeSignWork(1)
  return magnitude
:checkZero
  when value == 0.0 zero other
:zero
  calc signBit = convert.uint64BitsToInt64(convert.float64BitsToUInt64(value) >> 63)
  storeSignWork(1 - 2 * signBit)
  clibrary.setErrno(34)
  calc poleZero = convert.uint64BitsToFloat64(9218868437227405312)
  return poleZero
:other
  when value < 0.0 negative positive
:negative
  when magnitude >= 0x1p52 pole checkInteger
:pole
  storeSignWork(-1)
  clibrary.setErrno(34)
  calc poleInfinity = convert.uint64BitsToFloat64(9218868437227405312)
  return poleInfinity
:checkInteger
  calc truncated = convert.int64ToFloat64(convert.float64ToInt64(magnitude))
  when truncated == magnitude pole compute
:positive
  when value == 1.0 zeroResult checkTwo
:checkTwo
  when value == 2.0 zeroResult compute
:zeroResult
  storeSignWork(1)
  return nothing
:compute
  calc lh = lgammaCore(value)
  when lh > 1.7976931348623157e308 overflowed finished
:overflowed
  clibrary.setErrno(34)
  goto finished
:finished
  return lh

op logGamma "lgamma: ln |gamma(x)|, within 0.5001 ulp away from its zeros near -2.457, -2.747, ... and accurate to 2^-70 of the function's scale near them; the sign of gamma(x) is kept in a cell of machine.state (what glibc keeps in `signgam`, a data symbol the C library here does not export; lgamma_r gives it)"
  invariant lgammaIsAccurate "Gives ln |gamma| within 0.51 ulp, +infinity at the poles, +0 at 1 and 2"
  input value Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "lgamma"
:begin
  calc result = lgammaValue(value)
  calc sign = loadSignWork()
  storeSignInt(sign)
  return result

op logGammaSigned "lgamma_r: lgamma with the sign of gamma(x) stored through a pointer"
  invariant lgammaRIsAccurate "Gives what lgamma gives and stores the sign of gamma(x) as an int"
  input value Float64 copied
  input signp machine.Address copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "lgamma_r"
:begin
  calc result = lgammaValue(value)
  calc sign = loadSignWork()
  calc narrow = convert.int64ToInt32(sign)
  machine.storeInt32(signp, narrow)
  return result

op narrowResult "A double as a float, an overflow to infinity (not a trap) with ERANGE"
  input value Float64 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
:begin
  calc magnitude = magnitudeOf(value)
  when magnitude >= 0x1.ffffffp127 large fits
:large
  when magnitude > 1.7976931348623157e308 infinite finite
:finite
  clibrary.setErrno(34)
  goto infinite
:infinite
  calc infinity = convert.uint64BitsToFloat64(9218868437227405312)
  calc signed = withSign(infinity, value)
  calc inf32 = convert.float64ToFloat32(signed)
  return inf32
:fits
  calc narrowed = convert.float64ToFloat32(value)
  return narrowed

op hyperbolicSineFloat "sinhf: sinh of a float, computed in double and rounded once to float, so within 0.5001 ulp of a float"
  invariant sinhfIsAccurate "Gives sinh of the float rounded to float, within 0.51 ulp of a float"
  input value Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "sinhf"
:begin
  calc wide = convert.float32ToFloat64(value)
  calc result = hyperbolicSine(wide)
  calc narrowed = narrowResult(result)
  return narrowed

op hyperbolicCosineFloat "coshf: cosh of a float, computed in double and rounded once to float, so within 0.5001 ulp of a float"
  invariant coshfIsAccurate "Gives cosh of the float rounded to float, within 0.51 ulp of a float"
  input value Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "coshf"
:begin
  calc wide = convert.float32ToFloat64(value)
  calc result = hyperbolicCosine(wide)
  calc narrowed = narrowResult(result)
  return narrowed

op hyperbolicTangentFloat "tanhf: tanh of a float, computed in double and rounded once to float, so within 0.5001 ulp of a float"
  invariant tanhfIsAccurate "Gives tanh of the float rounded to float, within 0.51 ulp of a float"
  input value Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "tanhf"
:begin
  calc wide = convert.float32ToFloat64(value)
  calc result = hyperbolicTangent(wide)
  calc narrowed = narrowResult(result)
  return narrowed

op inverseHyperbolicSineFloat "asinhf: asinh of a float, computed in double and rounded once to float, so within 0.5001 ulp of a float"
  invariant asinhfIsAccurate "Gives asinh of the float rounded to float, within 0.51 ulp of a float"
  input value Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "asinhf"
:begin
  calc wide = convert.float32ToFloat64(value)
  calc result = inverseHyperbolicSine(wide)
  calc narrowed = narrowResult(result)
  return narrowed

op inverseHyperbolicCosineFloat "acoshf: acosh of a float, computed in double and rounded once to float, so within 0.5001 ulp of a float"
  invariant acoshfIsAccurate "Gives acosh of the float rounded to float, within 0.51 ulp of a float"
  input value Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "acoshf"
:begin
  calc wide = convert.float32ToFloat64(value)
  calc result = inverseHyperbolicCosine(wide)
  calc narrowed = narrowResult(result)
  return narrowed

op inverseHyperbolicTangentFloat "atanhf: atanh of a float, computed in double and rounded once to float, so within 0.5001 ulp of a float"
  invariant atanhfIsAccurate "Gives atanh of the float rounded to float, within 0.51 ulp of a float"
  input value Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "atanhf"
:begin
  calc wide = convert.float32ToFloat64(value)
  calc result = inverseHyperbolicTangent(wide)
  calc narrowed = narrowResult(result)
  return narrowed

op errorFunctionFloat "erff: erf of a float, computed in double and rounded once to float, so within 0.5001 ulp of a float"
  invariant erffIsAccurate "Gives erf of the float rounded to float, within 0.51 ulp of a float"
  input value Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "erff"
:begin
  calc wide = convert.float32ToFloat64(value)
  calc result = errorFunction(wide)
  calc narrowed = narrowResult(result)
  return narrowed

op complementaryErrorFunctionFloat "erfcf: erfc of a float, computed in double and rounded once to float, so within 0.5001 ulp of a float"
  invariant erfcfIsAccurate "Gives erfc of the float rounded to float, within 0.51 ulp of a float"
  input value Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "erfcf"
:begin
  calc wide = convert.float32ToFloat64(value)
  calc result = complementaryErrorFunction(wide)
  calc narrowed = narrowResult(result)
  return narrowed

op gammaFunctionFloat "tgammaf: tgamma of a float, computed in double and rounded once to float, so within 0.5001 ulp of a float"
  invariant tgammafIsAccurate "Gives tgamma of the float rounded to float, within 0.51 ulp of a float"
  input value Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "tgammaf"
:begin
  calc wide = convert.float32ToFloat64(value)
  calc result = gammaFunction(wide)
  calc narrowed = narrowResult(result)
  return narrowed

op logGammaFloat "lgammaf: lgamma of a float, computed in double and rounded once to float, so within 0.5001 ulp of a float"
  invariant lgammafIsAccurate "Gives lgamma of the float rounded to float, within 0.51 ulp of a float"
  input value Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "lgammaf"
:begin
  calc wide = convert.float32ToFloat64(value)
  calc result = logGamma(wide)
  calc narrowed = narrowResult(result)
  return narrowed

op logGammaSignedFloat "lgammaf_r: lgammaf with the sign of gamma(x) stored through a pointer"
  invariant lgammafRIsAccurate "Gives what lgammaf gives and stores the sign of gamma(x) as an int"
  input value Float32 copied
  input signp machine.Address copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "lgammaf_r"
:begin
  calc wide = convert.float32ToFloat64(value)
  calc result = lgammaValue(wide)
  calc sign = loadSignWork()
  calc narrow = convert.int64ToInt32(sign)
  machine.storeInt32(signp, narrow)
  calc narrowed = narrowResult(result)
  return narrowed

@tests

op closeBits "Whether a double is within some ulps of the double with the expected bits (the same sign)"
  input expected UInt64 copied
  input actual Float64 copied
  input allowed Int64 copied
  output Bool
:begin
  calc a = convert.uint64BitsToInt64(expected)
  calc b = convert.uint64BitsToInt64(convert.float64BitsToUInt64(actual))
  calc d = math.wrappingSubtractInt64(a, b)
  calc ok = d >= 0 - allowed && d <= allowed
  return ok

op sameBits "Whether a double has exactly the expected bits"
  input expected UInt64 copied
  input actual Float64 copied
  output Bool
:begin
  calc same = convert.float64BitsToUInt64(actual) == expected
  return same

op storeScratch "The address of an int cell in this module's part of machine.state, cleared"
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  cell = kernel.stateAt(24608)
  machine.storeInt64(cell, 0)
  return cell

test sinhTest "sinh and sinhf give the correctly rounded value (within 1 ulp for double, exactly for float) and Annex F's special cases"
  verifies hyperbolicSine sineIsAccurate
  verifies hyperbolicSineFloat sinhfIsAccurate
  effect use machine.memory
  uses memoryAccess
:begin
  calc r1 = hyperbolicSine(0x0.0p+0)
  calc okr1 = sameBits(0, r1)
  test.assertTrue(okr1)
  calc r2 = hyperbolicSine(-0x0.0p+0)
  calc okr2 = sameBits(9223372036854775808, r2)
  test.assertTrue(okr2)
  calc r3 = hyperbolicSine(0x1.b7cdfd9d7bdbbp-34)
  calc okr3 = closeBits(4457293557087583675, r3, 1)
  test.assertTrue(okr3)
  calc r4 = hyperbolicSine(0x1.0000000000000p-1)
  calc okr4 = closeBits(4602868828792568727, r4, 1)
  test.assertTrue(okr4)
  calc r5 = hyperbolicSine(-0x1.4000000000000p+0)
  calc okr5 = closeBits(13833265258200543206, r5, 1)
  test.assertTrue(okr5)
  calc r6 = hyperbolicSine(0x1.8000000000000p+1)
  calc okr6 = closeBits(4621829180278524334, r6, 1)
  test.assertTrue(okr6)
  calc r7 = hyperbolicSine(0x1.4000000000000p+4)
  calc okr7 = closeBits(4732415730390722564, r7, 1)
  test.assertTrue(okr7)
  calc r8 = hyperbolicSine(0x1.3c00000000000p+5)
  calc okr8 = closeBits(4859299822501854941, r8, 1)
  test.assertTrue(okr8)
  calc r9 = hyperbolicSine(0x1.4800000000000p+5)
  calc okr9 = closeBits(4868886374853339234, r9, 1)
  test.assertTrue(okr9)
  calc r10 = hyperbolicSine(0x1.5e00000000000p+9)
  calc okr10 = closeBits(9150633149149539470, r10, 1)
  test.assertTrue(okr10)
  calc r11 = hyperbolicSine(0x1.6333333333333p+9)
  calc okr11 = closeBits(9218210424404664587, r11, 1)
  test.assertTrue(okr11)
  calc r12 = hyperbolicSine(0x1.6380000000000p+9)
  calc okr12 = sameBits(9218868437227405312, r12)
  test.assertTrue(okr12)
  calc r13 = hyperbolicSine(convert.uint64BitsToFloat64(9218868437227405312))
  calc okr13 = sameBits(9218868437227405312, r13)
  test.assertTrue(okr13)
  calc r14 = hyperbolicSine(convert.uint64BitsToFloat64(18442240474082181120))
  calc okr14 = sameBits(18442240474082181120, r14)
  test.assertTrue(okr14)
  calc r15 = hyperbolicSine(convert.uint64BitsToFloat64(9221120237041090560))
  test.assertTrue(isNotNumber(r15))
  calc r16 = hyperbolicSine(0x0.0000000000001p-1022)
  calc okr16 = closeBits(1, r16, 1)
  test.assertTrue(okr16)
  calc f17 = hyperbolicSineFloat(convert.float64ToFloat32(0x0.0p+0))
  calc g17 = convert.float32ToFloat64(f17)
  calc okg17 = sameBits(0, g17)
  test.assertTrue(okg17)
  calc f18 = hyperbolicSineFloat(convert.float64ToFloat32(0x1.0000000000000p-1))
  calc g18 = convert.float32ToFloat64(f18)
  calc okg18 = sameBits(4602868828525821952, g18)
  test.assertTrue(okg18)
  calc f19 = hyperbolicSineFloat(convert.float64ToFloat32(-0x1.8000000000000p+1))
  calc g19 = convert.float32ToFloat64(f19)
  calc okg19 = sameBits(13845201217015250944, g19)
  test.assertTrue(okg19)
  calc f20 = hyperbolicSineFloat(convert.float64ToFloat32(0x1.6000000000000p+6))
  calc g20 = convert.float32ToFloat64(f20)
  calc okg20 = sameBits(5174372462183317504, g20)
  test.assertTrue(okg20)
  calc f21 = hyperbolicSineFloat(convert.float64ToFloat32(0x1.6600000000000p+6))
  calc g21 = convert.float32ToFloat64(f21)
  calc okg21 = sameBits(9218868437227405312, g21)
  test.assertTrue(okg21)
  calc f22 = hyperbolicSineFloat(convert.float64ToFloat32(0x1.9000000000000p+6))
  calc g22 = convert.float32ToFloat64(f22)
  calc okg22 = sameBits(9218868437227405312, g22)
  test.assertTrue(okg22)
  return

test coshTest "cosh and coshf give the correctly rounded value (within 1 ulp for double, exactly for float) and Annex F's special cases"
  verifies hyperbolicCosine cosineIsAccurate
  verifies hyperbolicCosineFloat coshfIsAccurate
  effect use machine.memory
  uses memoryAccess
:begin
  calc r1 = hyperbolicCosine(0x0.0p+0)
  calc okr1 = closeBits(4607182418800017408, r1, 1)
  test.assertTrue(okr1)
  calc r2 = hyperbolicCosine(0x1.12e0be826d695p-30)
  calc okr2 = closeBits(4607182418800017408, r2, 1)
  test.assertTrue(okr2)
  calc r3 = hyperbolicCosine(0x1.0000000000000p-1)
  calc okr3 = closeBits(4607757195049363664, r3, 1)
  test.assertTrue(okr3)
  calc r4 = hyperbolicCosine(-0x1.4000000000000p+1)
  calc okr4 = closeBits(4618590362581273251, r4, 1)
  test.assertTrue(okr4)
  calc r5 = hyperbolicCosine(0x1.e000000000000p+4)
  calc okr5 = closeBits(4797301478507948269, r5, 1)
  test.assertTrue(okr5)
  calc r6 = hyperbolicCosine(0x1.6800000000000p+5)
  calc okr6 = closeBits(4894934470466881982, r6, 1)
  test.assertTrue(okr6)
  calc r7 = hyperbolicCosine(0x1.6333333333333p+9)
  calc okr7 = closeBits(9218210424404664587, r7, 1)
  test.assertTrue(okr7)
  calc r8 = hyperbolicCosine(0x1.6380000000000p+9)
  calc okr8 = sameBits(9218868437227405312, r8)
  test.assertTrue(okr8)
  calc r9 = hyperbolicCosine(convert.uint64BitsToFloat64(9218868437227405312))
  calc okr9 = sameBits(9218868437227405312, r9)
  test.assertTrue(okr9)
  calc r10 = hyperbolicCosine(convert.uint64BitsToFloat64(18442240474082181120))
  calc okr10 = sameBits(9218868437227405312, r10)
  test.assertTrue(okr10)
  calc r11 = hyperbolicCosine(convert.uint64BitsToFloat64(9221120237041090560))
  test.assertTrue(isNotNumber(r11))
  calc f12 = hyperbolicCosineFloat(convert.float64ToFloat32(0x1.0000000000000p-1))
  calc g12 = convert.float32ToFloat64(f12)
  calc okg12 = sameBits(4607757194945888256, g12)
  test.assertTrue(okg12)
  calc f13 = hyperbolicCosineFloat(convert.float64ToFloat32(-0x1.8000000000000p+1))
  calc g13 = convert.float32ToFloat64(f13)
  calc okg13 = sameBits(4621857208043307008, g13)
  test.assertTrue(okg13)
  calc f14 = hyperbolicCosineFloat(convert.float64ToFloat32(0x1.6000000000000p+6))
  calc g14 = convert.float32ToFloat64(f14)
  calc okg14 = sameBits(5174372462183317504, g14)
  test.assertTrue(okg14)
  calc f15 = hyperbolicCosineFloat(convert.float64ToFloat32(0x1.6600000000000p+6))
  calc g15 = convert.float32ToFloat64(f15)
  calc okg15 = sameBits(9218868437227405312, g15)
  test.assertTrue(okg15)
  return

test tanhTest "tanh and tanhf give the correctly rounded value (within 1 ulp for double, exactly for float) and Annex F's special cases"
  verifies hyperbolicTangent tangentIsAccurate
  verifies hyperbolicTangentFloat tanhfIsAccurate
  effect use machine.memory
  uses memoryAccess
:begin
  calc r1 = hyperbolicTangent(0x0.0p+0)
  calc okr1 = sameBits(0, r1)
  test.assertTrue(okr1)
  calc r2 = hyperbolicTangent(-0x0.0p+0)
  calc okr2 = sameBits(9223372036854775808, r2)
  test.assertTrue(okr2)
  calc r3 = hyperbolicTangent(0x1.b7cdfd9d7bdbbp-34)
  calc okr3 = closeBits(4457293557087583675, r3, 1)
  test.assertTrue(okr3)
  calc r4 = hyperbolicTangent(0x1.3333333333333p-2)
  calc okr4 = closeBits(4598919441409447162, r4, 1)
  test.assertTrue(okr4)
  calc r5 = hyperbolicTangent(-0x1.ccccccccccccdp-1)
  calc okr5 = closeBits(13827999094042681437, r5, 1)
  test.assertTrue(okr5)
  calc r6 = hyperbolicTangent(0x1.4000000000000p+2)
  calc okr6 = closeBits(4607181600984719121, r6, 1)
  test.assertTrue(okr6)
  calc r7 = hyperbolicTangent(0x1.5e66666666666p+4)
  calc okr7 = closeBits(4607182418800017408, r7, 1)
  test.assertTrue(okr7)
  calc r8 = hyperbolicTangent(0x1.6000000000000p+4)
  calc okr8 = closeBits(4607182418800017408, r8, 1)
  test.assertTrue(okr8)
  calc r9 = hyperbolicTangent(-0x1.e000000000000p+4)
  calc okr9 = closeBits(13830554455654793216, r9, 1)
  test.assertTrue(okr9)
  calc r10 = hyperbolicTangent(convert.uint64BitsToFloat64(9218868437227405312))
  calc okr10 = closeBits(4607182418800017408, r10, 1)
  test.assertTrue(okr10)
  calc r11 = hyperbolicTangent(convert.uint64BitsToFloat64(18442240474082181120))
  calc okr11 = closeBits(13830554455654793216, r11, 1)
  test.assertTrue(okr11)
  calc r12 = hyperbolicTangent(convert.uint64BitsToFloat64(9221120237041090560))
  test.assertTrue(isNotNumber(r12))
  calc f13 = hyperbolicTangentFloat(convert.float64ToFloat32(0x0.0p+0))
  calc g13 = convert.float32ToFloat64(f13)
  calc okg13 = sameBits(0, g13)
  test.assertTrue(okg13)
  calc f14 = hyperbolicTangentFloat(convert.float64ToFloat32(0x1.3333340000000p-2))
  calc g14 = convert.float32ToFloat64(f14)
  calc okg14 = sameBits(4598919441814650880, g14)
  test.assertTrue(okg14)
  calc f15 = hyperbolicTangentFloat(convert.float64ToFloat32(-0x1.0000000000000p+1))
  calc g15 = convert.float32ToFloat64(f15)
  calc okg15 = sameBits(13830230444932595712, g15)
  test.assertTrue(okg15)
  calc f16 = hyperbolicTangentFloat(convert.float64ToFloat32(0x1.8000000000000p+3))
  calc g16 = convert.float32ToFloat64(f16)
  calc okg16 = sameBits(4607182418800017408, g16)
  test.assertTrue(okg16)
  return

test asinhTest "asinh and asinhf give the correctly rounded value (within 1 ulp for double, exactly for float) and Annex F's special cases"
  verifies inverseHyperbolicSine asinhIsAccurate
  verifies inverseHyperbolicSineFloat asinhfIsAccurate
  effect use machine.memory
  uses memoryAccess
:begin
  calc r1 = inverseHyperbolicSine(0x0.0p+0)
  calc okr1 = sameBits(0, r1)
  test.assertTrue(okr1)
  calc r2 = inverseHyperbolicSine(-0x0.0p+0)
  calc okr2 = sameBits(9223372036854775808, r2)
  test.assertTrue(okr2)
  calc r3 = inverseHyperbolicSine(0x1.b7cdfd9d7bdbbp-34)
  calc okr3 = closeBits(4457293557087583675, r3, 1)
  test.assertTrue(okr3)
  calc r4 = inverseHyperbolicSine(0x1.0000000000000p-1)
  calc okr4 = closeBits(4602340361502004746, r4, 1)
  test.assertTrue(okr4)
  calc r5 = inverseHyperbolicSine(-0x1.8000000000000p+1)
  calc okr5 = closeBits(13834240410823613454, r5, 1)
  test.assertTrue(okr5)
  calc r6 = inverseHyperbolicSine(0x1.9000000000000p+6)
  calc okr6 = closeBits(4617651421603249194, r6, 1)
  test.assertTrue(okr6)
  calc r7 = inverseHyperbolicSine(0x1.0000000000000p+28)
  calc okr7 = closeBits(4626351221690778753, r7, 1)
  test.assertTrue(okr7)
  calc r8 = inverseHyperbolicSine(0x1.2a05f20000000p+33)
  calc okr8 = closeBits(4627369522122882090, r8, 1)
  test.assertTrue(okr8)
  calc r9 = inverseHyperbolicSine(0x1.7e43c8800759cp+996)
  calc okr9 = closeBits(4649293438606917188, r9, 1)
  test.assertTrue(okr9)
  calc r10 = inverseHyperbolicSine(convert.uint64BitsToFloat64(9218868437227405312))
  calc okr10 = sameBits(9218868437227405312, r10)
  test.assertTrue(okr10)
  calc r11 = inverseHyperbolicSine(convert.uint64BitsToFloat64(18442240474082181120))
  calc okr11 = sameBits(18442240474082181120, r11)
  test.assertTrue(okr11)
  calc r12 = inverseHyperbolicSine(convert.uint64BitsToFloat64(9221120237041090560))
  test.assertTrue(isNotNumber(r12))
  calc f13 = inverseHyperbolicSineFloat(convert.float64ToFloat32(0x1.0000000000000p-1))
  calc g13 = convert.float32ToFloat64(f13)
  calc okg13 = sameBits(4602340361254207488, g13)
  test.assertTrue(okg13)
  calc f14 = inverseHyperbolicSineFloat(convert.float64ToFloat32(-0x1.8000000000000p+1))
  calc g14 = convert.float32ToFloat64(f14)
  calc okg14 = sameBits(13834240411083735040, g14)
  test.assertTrue(okg14)
  calc f15 = inverseHyperbolicSineFloat(convert.float64ToFloat32(0x1.5af1d80000000p+66))
  calc g15 = convert.float32ToFloat64(f15)
  calc okg15 = sameBits(4631775570114379776, g15)
  test.assertTrue(okg15)
  return

test acoshTest "acosh and acoshf give the correctly rounded value (within 1 ulp for double, exactly for float) and Annex F's special cases"
  verifies inverseHyperbolicCosine acoshIsAccurate
  verifies inverseHyperbolicCosineFloat acoshfIsAccurate
  effect use machine.memory
  uses memoryAccess
:begin
  calc r1 = inverseHyperbolicCosine(0x1.0000000000000p+0)
  calc okr1 = sameBits(0, r1)
  test.assertTrue(okr1)
  calc r2 = inverseHyperbolicCosine(0x1.0000000000001p+0)
  calc okr2 = closeBits(4491954280533539788, r2, 1)
  test.assertTrue(okr2)
  calc r3 = inverseHyperbolicCosine(0x1.000001ad7f29bp+0)
  calc okr3 = closeBits(4556885258320333540, r3, 1)
  test.assertTrue(okr3)
  calc r4 = inverseHyperbolicCosine(0x1.8000000000000p+0)
  calc okr4 = closeBits(4606843961129375242, r4, 1)
  test.assertTrue(okr4)
  calc r5 = inverseHyperbolicCosine(0x1.8000000000000p+1)
  calc okr5 = closeBits(4610617526688797735, r5, 1)
  test.assertTrue(okr5)
  calc r6 = inverseHyperbolicCosine(0x1.86a0000000000p+16)
  calc okr6 = closeBits(4623061026082002688, r6, 1)
  test.assertTrue(okr6)
  calc r7 = inverseHyperbolicCosine(0x1.0000000000000p+28)
  calc okr7 = closeBits(4626351221690778753, r7, 1)
  test.assertTrue(okr7)
  calc r8 = inverseHyperbolicCosine(0x1.7e43c8800759cp+996)
  calc okr8 = closeBits(4649293438606917188, r8, 1)
  test.assertTrue(okr8)
  calc r9 = inverseHyperbolicCosine(convert.uint64BitsToFloat64(9218868437227405312))
  calc okr9 = sameBits(9218868437227405312, r9)
  test.assertTrue(okr9)
  calc r10 = inverseHyperbolicCosine(0x1.0000000000000p-1)
  test.assertTrue(isNotNumber(r10))
  calc r11 = inverseHyperbolicCosine(convert.uint64BitsToFloat64(18442240474082181120))
  test.assertTrue(isNotNumber(r11))
  calc r12 = inverseHyperbolicCosine(convert.uint64BitsToFloat64(9221120237041090560))
  test.assertTrue(isNotNumber(r12))
  calc f13 = inverseHyperbolicCosineFloat(convert.float64ToFloat32(0x1.0000000000000p+0))
  calc g13 = convert.float32ToFloat64(f13)
  calc okg13 = sameBits(0, g13)
  test.assertTrue(okg13)
  calc f14 = inverseHyperbolicCosineFloat(convert.float64ToFloat32(0x1.8000000000000p+0))
  calc g14 = convert.float32ToFloat64(f14)
  calc okg14 = sameBits(4606843960881577984, g14)
  test.assertTrue(okg14)
  calc f15 = inverseHyperbolicCosineFloat(convert.float64ToFloat32(0x1.9000000000000p+6))
  calc g15 = convert.float32ToFloat64(f15)
  calc okg15 = sameBits(4617651365076795392, g15)
  test.assertTrue(okg15)
  calc f16 = inverseHyperbolicCosineFloat(convert.float64ToFloat32(0x1.0000000000000p-1))
  calc g16 = convert.float32ToFloat64(f16)
  test.assertTrue(isNotNumber(g16))
  return

test atanhTest "atanh and atanhf give the correctly rounded value (within 1 ulp for double, exactly for float) and Annex F's special cases"
  verifies inverseHyperbolicTangent atanhIsAccurate
  verifies inverseHyperbolicTangentFloat atanhfIsAccurate
  effect use machine.memory
  uses memoryAccess
:begin
  calc r1 = inverseHyperbolicTangent(0x0.0p+0)
  calc okr1 = sameBits(0, r1)
  test.assertTrue(okr1)
  calc r2 = inverseHyperbolicTangent(-0x0.0p+0)
  calc okr2 = sameBits(9223372036854775808, r2)
  test.assertTrue(okr2)
  calc r3 = inverseHyperbolicTangent(0x1.b7cdfd9d7bdbbp-34)
  calc okr3 = closeBits(4457293557087583675, r3, 1)
  test.assertTrue(okr3)
  calc r4 = inverseHyperbolicTangent(0x1.0000000000000p-2)
  calc okr4 = closeBits(4598272728095593554, r4, 1)
  test.assertTrue(okr4)
  calc r5 = inverseHyperbolicTangent(-0x1.0000000000000p-1)
  calc okr5 = closeBits(13826494966293922571, r5, 1)
  test.assertTrue(okr5)
  calc r6 = inverseHyperbolicTangent(0x1.fff2e48e8a71ep-1)
  calc okr6 = closeBits(4617261158135595341, r6, 1)
  test.assertTrue(okr6)
  calc r7 = inverseHyperbolicTangent(0x1.fffffffffffffp-1)
  calc okr7 = closeBits(4625961014517768418, r7, 1)
  test.assertTrue(okr7)
  calc r8 = inverseHyperbolicTangent(0x1.0000000000000p+0)
  calc okr8 = sameBits(9218868437227405312, r8)
  test.assertTrue(okr8)
  calc r9 = inverseHyperbolicTangent(-0x1.0000000000000p+0)
  calc okr9 = sameBits(18442240474082181120, r9)
  test.assertTrue(okr9)
  calc r10 = inverseHyperbolicTangent(0x1.8000000000000p+0)
  test.assertTrue(isNotNumber(r10))
  calc r11 = inverseHyperbolicTangent(convert.uint64BitsToFloat64(9218868437227405312))
  test.assertTrue(isNotNumber(r11))
  calc r12 = inverseHyperbolicTangent(convert.uint64BitsToFloat64(9221120237041090560))
  test.assertTrue(isNotNumber(r12))
  calc f13 = inverseHyperbolicTangentFloat(convert.float64ToFloat32(0x1.0000000000000p-2))
  calc g13 = convert.float32ToFloat64(f13)
  calc okg13 = sameBits(4598272728187797504, g13)
  test.assertTrue(okg13)
  calc f14 = inverseHyperbolicTangentFloat(convert.float64ToFloat32(-0x1.0000000000000p-1))
  calc g14 = convert.float32ToFloat64(f14)
  calc okg14 = sameBits(13826494966383247360, g14)
  test.assertTrue(okg14)
  calc f15 = inverseHyperbolicTangentFloat(convert.float64ToFloat32(0x1.0000000000000p+0))
  calc g15 = convert.float32ToFloat64(f15)
  calc okg15 = sameBits(9218868437227405312, g15)
  test.assertTrue(okg15)
  calc f16 = inverseHyperbolicTangentFloat(convert.float64ToFloat32(0x1.0000000000000p+1))
  calc g16 = convert.float32ToFloat64(f16)
  test.assertTrue(isNotNumber(g16))
  return

test erfTest "erf and erff give the correctly rounded value (within 1 ulp for double, exactly for float) and Annex F's special cases"
  verifies errorFunction erfIsAccurate
  verifies errorFunctionFloat erffIsAccurate
  effect use machine.memory
  uses memoryAccess
:begin
  calc r1 = errorFunction(0x0.0p+0)
  calc okr1 = sameBits(0, r1)
  test.assertTrue(okr1)
  calc r2 = errorFunction(-0x0.0p+0)
  calc okr2 = sameBits(9223372036854775808, r2)
  test.assertTrue(okr2)
  calc r3 = errorFunction(0x0.012688b70e62bp-1022)
  calc okr3 = closeBits(22838648600516, r3, 1)
  test.assertTrue(okr3)
  calc r4 = errorFunction(0x1.12e0be826d695p-30)
  calc okr4 = closeBits(4473027337189200093, r4, 1)
  test.assertTrue(okr4)
  calc r5 = errorFunction(0x1.999999999999ap-4)
  calc okr5 = closeBits(4592768227809932084, r5, 1)
  test.assertTrue(okr5)
  calc r6 = errorFunction(0x1.0000000000000p-1)
  calc okr6 = closeBits(4602863465656806866, r6, 1)
  test.assertTrue(okr6)
  calc r7 = errorFunction(-0x1.0000000000000p+0)
  calc okr7 = closeBits(13829137630354278539, r7, 1)
  test.assertTrue(okr7)
  calc r8 = errorFunction(0x1.7333333333333p+1)
  calc okr8 = closeBits(4607182048623240419, r8, 1)
  test.assertTrue(okr8)
  calc r9 = errorFunction(0x1.8000000000000p+1)
  calc okr9 = closeBits(4607182219826509305, r9, 1)
  test.assertTrue(okr9)
  calc r10 = errorFunction(0x1.2000000000000p+2)
  calc okr10 = closeBits(4607182418798246448, r10, 1)
  test.assertTrue(okr10)
  calc r11 = errorFunction(0x1.799999999999ap+2)
  calc okr11 = closeBits(4607182418800017407, r11, 1)
  test.assertTrue(okr11)
  calc r12 = errorFunction(0x1.8000000000000p+2)
  calc okr12 = closeBits(4607182418800017408, r12, 1)
  test.assertTrue(okr12)
  calc r13 = errorFunction(convert.uint64BitsToFloat64(9218868437227405312))
  calc okr13 = closeBits(4607182418800017408, r13, 1)
  test.assertTrue(okr13)
  calc r14 = errorFunction(convert.uint64BitsToFloat64(18442240474082181120))
  calc okr14 = closeBits(13830554455654793216, r14, 1)
  test.assertTrue(okr14)
  calc r15 = errorFunction(convert.uint64BitsToFloat64(9221120237041090560))
  test.assertTrue(isNotNumber(r15))
  calc f16 = errorFunctionFloat(convert.float64ToFloat32(0x1.99999a0000000p-4))
  calc g16 = convert.float32ToFloat64(f16)
  calc okg16 = sameBits(4592768227771154432, g16)
  test.assertTrue(okg16)
  calc f17 = errorFunctionFloat(convert.float64ToFloat32(-0x1.0000000000000p+0))
  calc g17 = convert.float32ToFloat64(f17)
  calc okg17 = sameBits(13829137630232576000, g17)
  test.assertTrue(okg17)
  calc f18 = errorFunctionFloat(convert.float64ToFloat32(0x1.c000000000000p+1))
  calc g18 = convert.float32ToFloat64(f18)
  calc okg18 = sameBits(4607182412357566464, g18)
  test.assertTrue(okg18)
  calc f19 = errorFunctionFloat(convert.float64ToFloat32(0x1.8000000000000p+2))
  calc g19 = convert.float32ToFloat64(f19)
  calc okg19 = sameBits(4607182418800017408, g19)
  test.assertTrue(okg19)
  return

test erfcTest "erfc and erfcf give the correctly rounded value (within 1 ulp for double, exactly for float) and Annex F's special cases"
  verifies complementaryErrorFunction erfcIsAccurate
  verifies complementaryErrorFunctionFloat erfcfIsAccurate
  effect use machine.memory
  uses memoryAccess
:begin
  calc r1 = complementaryErrorFunction(0x0.0p+0)
  calc okr1 = closeBits(4607182418800017408, r1, 1)
  test.assertTrue(okr1)
  calc r2 = complementaryErrorFunction(-0x0.0p+0)
  calc okr2 = closeBits(4607182418800017408, r2, 1)
  test.assertTrue(okr2)
  calc r3 = complementaryErrorFunction(0x1.79ca10c924223p-67)
  calc okr3 = closeBits(4607182418800017408, r3, 1)
  test.assertTrue(okr3)
  calc r4 = complementaryErrorFunction(0x1.999999999999ap-4)
  calc okr4 = closeBits(4606169442906671513, r4, 1)
  test.assertTrue(okr4)
  calc r5 = complementaryErrorFunction(-0x1.999999999999ap-4)
  calc okr5 = closeBits(4607688906746690355, r5, 1)
  test.assertTrue(okr5)
  calc r6 = complementaryErrorFunction(0x1.0000000000000p+0)
  calc okr6 = closeBits(4594835321492594133, r6, 1)
  test.assertTrue(okr6)
  calc r7 = complementaryErrorFunction(0x1.7333333333333p+1)
  calc okr7 = closeBits(4541189801076275314, r7, 1)
  test.assertTrue(okr7)
  calc r8 = complementaryErrorFunction(0x1.8000000000000p+1)
  calc okr8 = closeBits(4537141189048222250, r8, 1)
  test.assertTrue(okr8)
  calc r9 = complementaryErrorFunction(0x1.4000000000000p+2)
  calc okr9 = closeBits(4430147966231082809, r9, 1)
  test.assertTrue(okr9)
  calc r10 = complementaryErrorFunction(0x1.4000000000000p+3)
  calc okr10 = closeBits(3938354615001064144, r10, 1)
  test.assertTrue(okr10)
  calc r11 = complementaryErrorFunction(0x1.a000000000000p+4)
  calc okr11 = closeBits(189860093964970532, r11, 1)
  test.assertTrue(okr11)
  calc r12 = complementaryErrorFunction(0x1.b000000000000p+4)
  calc okr12 = closeBits(105999, r12, 1)
  test.assertTrue(okr12)
  calc r13 = complementaryErrorFunction(0x1.b4ccccccccccdp+4)
  calc okr13 = sameBits(0, r13)
  test.assertTrue(okr13)
  calc r14 = complementaryErrorFunction(-0x1.4000000000000p+2)
  calc okr14 = closeBits(4611686018427380980, r14, 1)
  test.assertTrue(okr14)
  calc r15 = complementaryErrorFunction(-0x1.a000000000000p+2)
  calc okr15 = closeBits(4611686018427387904, r15, 1)
  test.assertTrue(okr15)
  calc r16 = complementaryErrorFunction(convert.uint64BitsToFloat64(9218868437227405312))
  calc okr16 = sameBits(0, r16)
  test.assertTrue(okr16)
  calc r17 = complementaryErrorFunction(convert.uint64BitsToFloat64(18442240474082181120))
  calc okr17 = closeBits(4611686018427387904, r17, 1)
  test.assertTrue(okr17)
  calc r18 = complementaryErrorFunction(convert.uint64BitsToFloat64(9221120237041090560))
  test.assertTrue(isNotNumber(r18))
  calc f19 = complementaryErrorFunctionFloat(convert.float64ToFloat32(0x1.99999a0000000p-4))
  calc g19 = convert.float32ToFloat64(f19)
  calc okg19 = sameBits(4606169442710192128, g19)
  test.assertTrue(okg19)
  calc f20 = complementaryErrorFunctionFloat(convert.float64ToFloat32(0x1.0000000000000p+0))
  calc g20 = convert.float32ToFloat64(f20)
  calc okg20 = sameBits(4594835321442533376, g20)
  test.assertTrue(okg20)
  calc f21 = complementaryErrorFunctionFloat(convert.float64ToFloat32(0x1.4000000000000p+2))
  calc g21 = convert.float32ToFloat64(f21)
  calc okg21 = sameBits(4430147966405181440, g21)
  test.assertTrue(okg21)
  calc f22 = complementaryErrorFunctionFloat(convert.float64ToFloat32(0x1.4000000000000p+3))
  calc g22 = convert.float32ToFloat64(f22)
  calc okg22 = sameBits(3936146074321813504, g22)
  test.assertTrue(okg22)
  calc f23 = complementaryErrorFunctionFloat(convert.float64ToFloat32(0x1.8000000000000p+3))
  calc g23 = convert.float32ToFloat64(f23)
  calc okg23 = sameBits(0, g23)
  test.assertTrue(okg23)
  calc f24 = complementaryErrorFunctionFloat(convert.float64ToFloat32(-0x1.8000000000000p+1))
  calc g24 = convert.float32ToFloat64(f24)
  calc okg24 = sameBits(4611685919106269184, g24)
  test.assertTrue(okg24)
  return

test tgammaTest "tgamma and tgammaf give the correctly rounded value (within 1 ulp for double, exactly for float) and Annex F's special cases"
  verifies gammaFunction gammaIsAccurate
  verifies gammaFunctionFloat tgammafIsAccurate
  effect use machine.memory
  uses memoryAccess
:begin
  calc r1 = gammaFunction(0x1.0000000000000p-1)
  calc okr1 = closeBits(4610661241675116395, r1, 1)
  test.assertTrue(okr1)
  calc r2 = gammaFunction(0x1.0000000000000p+0)
  calc okr2 = closeBits(4607182418800017408, r2, 1)
  test.assertTrue(okr2)
  calc r3 = gammaFunction(0x1.0000000000000p+1)
  calc okr3 = closeBits(4607182418800017408, r3, 1)
  test.assertTrue(okr3)
  calc r4 = gammaFunction(0x1.8000000000000p+1)
  calc okr4 = closeBits(4611686018427387904, r4, 1)
  test.assertTrue(okr4)
  calc r5 = gammaFunction(0x1.6000000000000p+2)
  calc okr5 = closeBits(4632563408388438514, r5, 1)
  test.assertTrue(okr5)
  calc r6 = gammaFunction(0x1.4000000000000p+3)
  calc okr6 = closeBits(4689977843394805760, r6, 1)
  test.assertTrue(okr6)
  calc r7 = gammaFunction(0x1.0624dd2f1a9fcp-10)
  calc okr7 = closeBits(4652002240290361922, r7, 1)
  test.assertTrue(okr7)
  calc r8 = gammaFunction(0x1.79ca10c924223p-67)
  calc okr8 = closeBits(4906019910204099648, r8, 1)
  test.assertTrue(okr8)
  calc r9 = gammaFunction(-0x1.0000000000000p-1)
  calc okr9 = closeBits(13838536878157262699, r9, 1)
  test.assertTrue(okr9)
  calc r10 = gammaFunction(-0x1.8000000000000p+0)
  calc okr10 = closeBits(4612504033801663730, r10, 1)
  test.assertTrue(okr10)
  calc r11 = gammaFunction(-0x1.4000000000000p+1)
  calc okr11 = closeBits(13830061840402686339, r11, 1)
  test.assertTrue(okr11)
  calc r12 = gammaFunction(-0x1.5000000000000p+3)
  calc okr12 = closeBits(13731958713343690737, r12, 1)
  test.assertTrue(okr12)
  calc r13 = gammaFunction(0x1.9200000000000p+6)
  calc okr13 = closeBits(6955169173795998731, r13, 1)
  test.assertTrue(okr13)
  calc r14 = gammaFunction(0x1.5600000000000p+7)
  calc okr14 = closeBits(9197664872563836473, r14, 1)
  test.assertTrue(okr14)
  calc r15 = gammaFunction(0x1.5766666666666p+7)
  calc okr15 = sameBits(9218868437227405312, r15)
  test.assertTrue(okr15)
  calc r16 = gammaFunction(0x1.5800000000000p+7)
  calc okr16 = sameBits(9218868437227405312, r16)
  test.assertTrue(okr16)
  calc r17 = gammaFunction(-0x1.5500000000000p+7)
  calc okr17 = closeBits(9230077096292571770, r17, 1)
  test.assertTrue(okr17)
  calc r18 = gammaFunction(-0x1.6900000000000p+7)
  calc okr18 = sameBits(9223372036854775808, r18)
  test.assertTrue(okr18)
  calc r19 = gammaFunction(-0x0.0p+0)
  calc okr19 = sameBits(18442240474082181120, r19)
  test.assertTrue(okr19)
  calc r20 = gammaFunction(0x0.0p+0)
  calc okr20 = sameBits(9218868437227405312, r20)
  test.assertTrue(okr20)
  calc r21 = gammaFunction(-0x1.0000000000000p+0)
  test.assertTrue(isNotNumber(r21))
  calc r22 = gammaFunction(-0x1.8000000000000p+1)
  test.assertTrue(isNotNumber(r22))
  calc r23 = gammaFunction(convert.uint64BitsToFloat64(9218868437227405312))
  calc okr23 = sameBits(9218868437227405312, r23)
  test.assertTrue(okr23)
  calc r24 = gammaFunction(convert.uint64BitsToFloat64(18442240474082181120))
  test.assertTrue(isNotNumber(r24))
  calc r25 = gammaFunction(convert.uint64BitsToFloat64(9221120237041090560))
  test.assertTrue(isNotNumber(r25))
  calc r26 = gammaFunction(0x0.012688b70e62bp-1022)
  calc okr26 = sameBits(9218868437227405312, r26)
  test.assertTrue(okr26)
  calc f27 = gammaFunctionFloat(convert.float64ToFloat32(0x1.0000000000000p-1))
  calc g27 = convert.float32ToFloat64(f27)
  calc okg27 = sameBits(4610661241914916864, g27)
  test.assertTrue(okg27)
  calc f28 = gammaFunctionFloat(convert.float64ToFloat32(0x1.6000000000000p+2))
  calc g28 = convert.float32ToFloat64(f28)
  calc okg28 = sameBits(4632563408313516032, g28)
  test.assertTrue(okg28)
  calc f29 = gammaFunctionFloat(convert.float64ToFloat32(-0x1.8000000000000p+0))
  calc g29 = convert.float32ToFloat64(f29)
  calc okg29 = sameBits(4612504033603616768, g29)
  test.assertTrue(okg29)
  calc f30 = gammaFunctionFloat(convert.float64ToFloat32(0x1.1400000000000p+5))
  calc g30 = convert.float32ToFloat64(f30)
  calc okg30 = sameBits(5170969972448428032, g30)
  test.assertTrue(okg30)
  calc f31 = gammaFunctionFloat(convert.float64ToFloat32(0x1.2000000000000p+5))
  calc g31 = convert.float32ToFloat64(f31)
  calc okg31 = sameBits(9218868437227405312, g31)
  test.assertTrue(okg31)
  calc f32 = gammaFunctionFloat(convert.float64ToFloat32(-0x1.8000000000000p+1))
  calc g32 = convert.float32ToFloat64(f32)
  test.assertTrue(isNotNumber(g32))
  return

test lgammaTest "lgamma and lgammaf give the correctly rounded value (within 1 ulp for double, exactly for float) and Annex F's special cases"
  verifies logGamma lgammaIsAccurate
  verifies logGammaFloat lgammafIsAccurate
  verifies logGammaSigned lgammaRIsAccurate
  verifies logGammaSignedFloat lgammafRIsAccurate
  effect use machine.memory
  uses memoryAccess
:begin
  calc r1 = logGamma(0x1.0000000000000p-1)
  calc okr1 = closeBits(4603330624632627645, r1, 1)
  test.assertTrue(okr1)
  cell1 = storeScratch()
  calc q1 = logGammaSigned(0x1.0000000000000p-1, cell1)
  calc okq1 = closeBits(4603330624632627645, q1, 1)
  test.assertTrue(okq1)
  calc s1 = machine.loadInt32(cell1)
  test.assertTrue(s1 == 1)
  calc r2 = logGamma(0x1.0000000000000p+0)
  calc okr2 = sameBits(0, r2)
  test.assertTrue(okr2)
  cell2 = storeScratch()
  calc q2 = logGammaSigned(0x1.0000000000000p+0, cell2)
  calc okq2 = sameBits(0, q2)
  test.assertTrue(okq2)
  calc s2 = machine.loadInt32(cell2)
  test.assertTrue(s2 == 1)
  calc r3 = logGamma(0x1.0000000000000p+1)
  calc okr3 = sameBits(0, r3)
  test.assertTrue(okr3)
  cell3 = storeScratch()
  calc q3 = logGammaSigned(0x1.0000000000000p+1, cell3)
  calc okq3 = sameBits(0, q3)
  test.assertTrue(okq3)
  calc s3 = machine.loadInt32(cell3)
  test.assertTrue(s3 == 1)
  calc r4 = logGamma(0x1.8000000000000p+1)
  calc okr4 = closeBits(4604418534313441775, r4, 1)
  test.assertTrue(okr4)
  cell4 = storeScratch()
  calc q4 = logGammaSigned(0x1.8000000000000p+1, cell4)
  calc okq4 = closeBits(4604418534313441775, q4, 1)
  test.assertTrue(okq4)
  calc s4 = machine.loadInt32(cell4)
  test.assertTrue(s4 == 1)
  calc r5 = logGamma(0x1.5000000000000p+3)
  calc okr5 = closeBits(4624037492372685716, r5, 1)
  test.assertTrue(okr5)
  cell5 = storeScratch()
  calc q5 = logGammaSigned(0x1.5000000000000p+3, cell5)
  calc okq5 = closeBits(4624037492372685716, q5, 1)
  test.assertTrue(okq5)
  calc s5 = machine.loadInt32(cell5)
  test.assertTrue(s5 == 1)
  calc r6 = logGamma(0x1.9000000000000p+6)
  calc okr6 = closeBits(4645025571947385954, r6, 1)
  test.assertTrue(okr6)
  cell6 = storeScratch()
  calc q6 = logGammaSigned(0x1.9000000000000p+6, cell6)
  calc okq6 = closeBits(4645025571947385954, q6, 1)
  test.assertTrue(okq6)
  calc s6 = machine.loadInt32(cell6)
  test.assertTrue(s6 == 1)
  calc r7 = logGamma(0x1.86a0000000000p+16)
  calc okr7 = closeBits(4697266058048785454, r7, 1)
  test.assertTrue(okr7)
  cell7 = storeScratch()
  calc q7 = logGammaSigned(0x1.86a0000000000p+16, cell7)
  calc okq7 = closeBits(4697266058048785454, q7, 1)
  test.assertTrue(okq7)
  calc s7 = machine.loadInt32(cell7)
  test.assertTrue(s7 == 1)
  calc r8 = logGamma(0x1.5af1d78b58c40p+66)
  calc okr8 = closeBits(4931027322910784150, r8, 1)
  test.assertTrue(okr8)
  cell8 = storeScratch()
  calc q8 = logGammaSigned(0x1.5af1d78b58c40p+66, cell8)
  calc okq8 = closeBits(4931027322910784150, q8, 1)
  test.assertTrue(okq8)
  calc s8 = machine.loadInt32(cell8)
  test.assertTrue(s8 == 1)
  calc r9 = logGamma(0x1.7e43c8800759cp+996)
  calc okr9 = closeBits(9137829978769595061, r9, 1)
  test.assertTrue(okr9)
  cell9 = storeScratch()
  calc q9 = logGammaSigned(0x1.7e43c8800759cp+996, cell9)
  calc okq9 = closeBits(9137829978769595061, q9, 1)
  test.assertTrue(okq9)
  calc s9 = machine.loadInt32(cell9)
  test.assertTrue(s9 == 1)
  calc r10 = logGamma(0x1.23a516e82d9bap+1013)
  calc okr10 = closeBits(9212385138992644430, r10, 1)
  test.assertTrue(okr10)
  cell10 = storeScratch()
  calc q10 = logGammaSigned(0x1.23a516e82d9bap+1013, cell10)
  calc okq10 = closeBits(9212385138992644430, q10, 1)
  test.assertTrue(okq10)
  calc s10 = machine.loadInt32(cell10)
  test.assertTrue(s10 == 1)
  calc r11 = logGamma(0x1.b577a25c44697p+1014)
  calc okr11 = sameBits(9218868437227405312, r11)
  test.assertTrue(okr11)
  cell11 = storeScratch()
  calc q11 = logGammaSigned(0x1.b577a25c44697p+1014, cell11)
  calc okq11 = sameBits(9218868437227405312, q11)
  test.assertTrue(okq11)
  calc s11 = machine.loadInt32(cell11)
  test.assertTrue(s11 == 1)
  calc r12 = logGamma(0x1.0624dd2f1a9fcp-10)
  calc okr12 = closeBits(4619462810490986924, r12, 1)
  test.assertTrue(okr12)
  cell12 = storeScratch()
  calc q12 = logGammaSigned(0x1.0624dd2f1a9fcp-10, cell12)
  calc okq12 = closeBits(4619462810490986924, q12, 1)
  test.assertTrue(okq12)
  calc s12 = machine.loadInt32(cell12)
  test.assertTrue(s12 == 1)
  calc r13 = logGamma(0x1.79ca10c924223p-67)
  calc okr13 = closeBits(4631678018163747419, r13, 1)
  test.assertTrue(okr13)
  cell13 = storeScratch()
  calc q13 = logGammaSigned(0x1.79ca10c924223p-67, cell13)
  calc okq13 = closeBits(4631678018163747419, q13, 1)
  test.assertTrue(okq13)
  calc s13 = machine.loadInt32(cell13)
  test.assertTrue(s13 == 1)
  calc r14 = logGamma(0x0.012688b70e62bp-1022)
  calc okr14 = closeBits(4649489879146534152, r14, 1)
  test.assertTrue(okr14)
  cell14 = storeScratch()
  calc q14 = logGammaSigned(0x0.012688b70e62bp-1022, cell14)
  calc okq14 = closeBits(4649489879146534152, q14, 1)
  test.assertTrue(okq14)
  calc s14 = machine.loadInt32(cell14)
  test.assertTrue(s14 == 1)
  calc r15 = logGamma(0x1.000001ad7f29bp+0)
  calc okr15 = closeBits(13722183500615194809, r15, 1)
  test.assertTrue(okr15)
  cell15 = storeScratch()
  calc q15 = logGammaSigned(0x1.000001ad7f29bp+0, cell15)
  calc okq15 = closeBits(13722183500615194809, q15, 1)
  test.assertTrue(okq15)
  calc s15 = machine.loadInt32(cell15)
  test.assertTrue(s15 == 1)
  calc r16 = logGamma(0x1.fffffca501acbp-1)
  calc okr16 = closeBits(4498811466236489011, r16, 1)
  test.assertTrue(okr16)
  cell16 = storeScratch()
  calc q16 = logGammaSigned(0x1.fffffca501acbp-1, cell16)
  calc okq16 = closeBits(4498811466236489011, q16, 1)
  test.assertTrue(okq16)
  calc s16 = machine.loadInt32(cell16)
  test.assertTrue(s16 == 1)
  calc r17 = logGamma(0x1.000000d6bf94dp+1)
  calc okr17 = closeBits(4496477765200591161, r17, 1)
  test.assertTrue(okr17)
  cell17 = storeScratch()
  calc q17 = logGammaSigned(0x1.000000d6bf94dp+1, cell17)
  calc okq17 = closeBits(4496477765200591161, q17, 1)
  test.assertTrue(okq17)
  calc s17 = machine.loadInt32(cell17)
  test.assertTrue(s17 == 1)
  calc r18 = logGamma(0x1.0000100000000p+0)
  calc okr18 = closeBits(13736674353294433478, r18, 1)
  test.assertTrue(okr18)
  cell18 = storeScratch()
  calc q18 = logGammaSigned(0x1.0000100000000p+0, cell18)
  calc okq18 = closeBits(13736674353294433478, q18, 1)
  test.assertTrue(okq18)
  calc s18 = machine.loadInt32(cell18)
  test.assertTrue(s18 == 1)
  calc r19 = logGamma(-0x1.0000000000000p-1)
  calc okr19 = closeBits(4608378179100405206, r19, 1)
  test.assertTrue(okr19)
  cell19 = storeScratch()
  calc q19 = logGammaSigned(-0x1.0000000000000p-1, cell19)
  calc okq19 = closeBits(4608378179100405206, q19, 1)
  test.assertTrue(okq19)
  calc s19 = machine.loadInt32(cell19)
  test.assertTrue(s19 == -1)
  calc r20 = logGamma(-0x1.8000000000000p+0)
  calc okr20 = closeBits(4605921834381217670, r20, 1)
  test.assertTrue(okr20)
  cell20 = storeScratch()
  calc q20 = logGammaSigned(-0x1.8000000000000p+0, cell20)
  calc okq20 = closeBits(4605921834381217670, q20, 1)
  test.assertTrue(okq20)
  calc s20 = machine.loadInt32(cell20)
  test.assertTrue(s20 == 1)
  calc r21 = logGamma(-0x1.4000000000000p+1)
  calc okr21 = closeBits(13811638431671717654, r21, 1)
  test.assertTrue(okr21)
  cell21 = storeScratch()
  calc q21 = logGammaSigned(-0x1.4000000000000p+1, cell21)
  calc okq21 = closeBits(13811638431671717654, q21, 1)
  test.assertTrue(okq21)
  calc s21 = machine.loadInt32(cell21)
  test.assertTrue(s21 == -1)
  calc r22 = logGamma(-0x1.499999999999ap+3)
  calc okr22 = closeBits(13847700512553083735, r22, 1)
  test.assertTrue(okr22)
  cell22 = storeScratch()
  calc q22 = logGammaSigned(-0x1.499999999999ap+3, cell22)
  calc okq22 = closeBits(13847700512553083735, q22, 1)
  test.assertTrue(okq22)
  calc s22 = machine.loadInt32(cell22)
  test.assertTrue(s22 == -1)
  calc r23 = logGamma(-0x1.9200000000000p+6)
  calc okr23 = closeBits(13868499058768673681, r23, 1)
  test.assertTrue(okr23)
  cell23 = storeScratch()
  calc q23 = logGammaSigned(-0x1.9200000000000p+6, cell23)
  calc okq23 = closeBits(13868499058768673681, q23, 1)
  test.assertTrue(okq23)
  calc s23 = machine.loadInt32(cell23)
  test.assertTrue(s23 == -1)
  calc r24 = logGamma(-0x0.0p+0)
  calc okr24 = sameBits(9218868437227405312, r24)
  test.assertTrue(okr24)
  cell24 = storeScratch()
  calc q24 = logGammaSigned(-0x0.0p+0, cell24)
  calc okq24 = sameBits(9218868437227405312, q24)
  test.assertTrue(okq24)
  calc s24 = machine.loadInt32(cell24)
  test.assertTrue(s24 == -1)
  calc r25 = logGamma(0x0.0p+0)
  calc okr25 = sameBits(9218868437227405312, r25)
  test.assertTrue(okr25)
  cell25 = storeScratch()
  calc q25 = logGammaSigned(0x0.0p+0, cell25)
  calc okq25 = sameBits(9218868437227405312, q25)
  test.assertTrue(okq25)
  calc s25 = machine.loadInt32(cell25)
  test.assertTrue(s25 == 1)
  calc r26 = logGamma(-0x1.0000000000000p+0)
  calc okr26 = sameBits(9218868437227405312, r26)
  test.assertTrue(okr26)
  cell26 = storeScratch()
  calc q26 = logGammaSigned(-0x1.0000000000000p+0, cell26)
  calc okq26 = sameBits(9218868437227405312, q26)
  test.assertTrue(okq26)
  calc s26 = machine.loadInt32(cell26)
  test.assertTrue(s26 == -1)
  calc r27 = logGamma(-0x1.4000000000000p+2)
  calc okr27 = sameBits(9218868437227405312, r27)
  test.assertTrue(okr27)
  cell27 = storeScratch()
  calc q27 = logGammaSigned(-0x1.4000000000000p+2, cell27)
  calc okq27 = sameBits(9218868437227405312, q27)
  test.assertTrue(okq27)
  calc s27 = machine.loadInt32(cell27)
  test.assertTrue(s27 == -1)
  calc r28 = logGamma(convert.uint64BitsToFloat64(9218868437227405312))
  calc okr28 = sameBits(9218868437227405312, r28)
  test.assertTrue(okr28)
  cell28 = storeScratch()
  calc q28 = logGammaSigned(convert.uint64BitsToFloat64(9218868437227405312), cell28)
  calc okq28 = sameBits(9218868437227405312, q28)
  test.assertTrue(okq28)
  calc s28 = machine.loadInt32(cell28)
  test.assertTrue(s28 == 1)
  calc r29 = logGamma(convert.uint64BitsToFloat64(18442240474082181120))
  calc okr29 = sameBits(9218868437227405312, r29)
  test.assertTrue(okr29)
  cell29 = storeScratch()
  calc q29 = logGammaSigned(convert.uint64BitsToFloat64(18442240474082181120), cell29)
  calc okq29 = sameBits(9218868437227405312, q29)
  test.assertTrue(okq29)
  calc s29 = machine.loadInt32(cell29)
  test.assertTrue(s29 == 1)
  calc r30 = logGamma(convert.uint64BitsToFloat64(9221120237041090560))
  test.assertTrue(isNotNumber(r30))
  cell30 = storeScratch()
  calc q30 = logGammaSigned(convert.uint64BitsToFloat64(9221120237041090560), cell30)
  test.assertTrue(isNotNumber(q30))
  calc s30 = machine.loadInt32(cell30)
  test.assertTrue(s30 == 1)
  calc f31 = logGammaFloat(convert.float64ToFloat32(0x1.0000000000000p-1))
  calc g31 = convert.float32ToFloat64(f31)
  calc okg31 = sameBits(4603330624483229696, g31)
  test.assertTrue(okg31)
  cell31 = storeScratch()
  calc h31 = logGammaSignedFloat(convert.float64ToFloat32(0x1.0000000000000p-1), cell31)
  calc i31 = convert.float32ToFloat64(h31)
  calc oki31 = sameBits(4603330624483229696, i31)
  test.assertTrue(oki31)
  calc s31 = machine.loadInt32(cell31)
  test.assertTrue(s31 == 1)
  calc f32 = logGammaFloat(convert.float64ToFloat32(0x1.5000000000000p+3))
  calc g32 = convert.float32ToFloat64(f32)
  calc okg32 = sameBits(4624037492356546560, g32)
  test.assertTrue(okg32)
  cell32 = storeScratch()
  calc h32 = logGammaSignedFloat(convert.float64ToFloat32(0x1.5000000000000p+3), cell32)
  calc i32 = convert.float32ToFloat64(h32)
  calc oki32 = sameBits(4624037492356546560, i32)
  test.assertTrue(oki32)
  calc s32 = machine.loadInt32(cell32)
  test.assertTrue(s32 == 1)
  calc f33 = logGammaFloat(convert.float64ToFloat32(0x1.93e5940000000p+99))
  calc g33 = convert.float32ToFloat64(f33)
  calc okg33 = sameBits(5083114906727743488, g33)
  test.assertTrue(okg33)
  cell33 = storeScratch()
  calc h33 = logGammaSignedFloat(convert.float64ToFloat32(0x1.93e5940000000p+99), cell33)
  calc i33 = convert.float32ToFloat64(h33)
  calc oki33 = sameBits(5083114906727743488, i33)
  test.assertTrue(oki33)
  calc s33 = machine.loadInt32(cell33)
  test.assertTrue(s33 == 1)
  calc f34 = logGammaFloat(convert.float64ToFloat32(0x1.e17b840000000p+122))
  calc g34 = convert.float32ToFloat64(f34)
  calc okg34 = sameBits(9218868437227405312, g34)
  test.assertTrue(okg34)
  cell34 = storeScratch()
  calc h34 = logGammaSignedFloat(convert.float64ToFloat32(0x1.e17b840000000p+122), cell34)
  calc i34 = convert.float32ToFloat64(h34)
  calc oki34 = sameBits(9218868437227405312, i34)
  test.assertTrue(oki34)
  calc s34 = machine.loadInt32(cell34)
  test.assertTrue(s34 == 1)
  calc f35 = logGammaFloat(convert.float64ToFloat32(-0x1.4000000000000p+1))
  calc g35 = convert.float32ToFloat64(f35)
  calc okg35 = sameBits(13811638431840731136, g35)
  test.assertTrue(okg35)
  cell35 = storeScratch()
  calc h35 = logGammaSignedFloat(convert.float64ToFloat32(-0x1.4000000000000p+1), cell35)
  calc i35 = convert.float32ToFloat64(h35)
  calc oki35 = sameBits(13811638431840731136, i35)
  test.assertTrue(oki35)
  calc s35 = machine.loadInt32(cell35)
  test.assertTrue(s35 == -1)
  calc f36 = logGammaFloat(convert.float64ToFloat32(0x0.0p+0))
  calc g36 = convert.float32ToFloat64(f36)
  calc okg36 = sameBits(9218868437227405312, g36)
  test.assertTrue(okg36)
  cell36 = storeScratch()
  calc h36 = logGammaSignedFloat(convert.float64ToFloat32(0x0.0p+0), cell36)
  calc i36 = convert.float32ToFloat64(h36)
  calc oki36 = sameBits(9218868437227405312, i36)
  test.assertTrue(oki36)
  calc s36 = machine.loadInt32(cell36)
  test.assertTrue(s36 == 1)
  return
