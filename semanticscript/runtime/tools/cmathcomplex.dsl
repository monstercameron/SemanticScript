module cmathcomplex "complex.h written in SemanticScript: cabs, carg, cimag, creal, conj, cproj, cexp, clog, cpow, csqrt and the trigonometric, hyperbolic, and inverse functions, for double complex and float complex, as glibc gives them in the C locale (D-153, D-175)"
  path cmathcomplex
  imports standard.machine standard.math standard.compare standard.convert standard.bits standard.logic standard.test clibrary cmathexp cmathtrig
  exports none

capability memoryAccess "Authority to call this library's real functions, which set errno in machine.state, and to restore it" use machine.memory none

record Complex "double complex: the real part, then the imaginary part (D-175: two Float64, passed in floating registers as glibc does)"
  field real Float64
  field imag Float64

record ComplexSingle "float complex: the real part, then the imaginary part (D-175: two Float32, packed in one register on x86_64)"
  field real Float32
  field imag Float32

record DoubleDouble "A value as the unevaluated sum of two doubles, about 106 bits"
  field high Float64
  field low Float64

record Kernel "What Hull's inverse-sine kernel gives for x, y >= 0: the real part of asin(x+iy), the real part of acos(x+iy), and the common imaginary part of both"
  field asinReal Float64
  field acosReal Float64
  field imag Float64

## ---------------------------------------------------------------- how this module works
##
## complex.h in the C locale, as glibc's libm gives it. A function is two layers. The parts layer (`...Parts`) takes the
## real and the imaginary part as two doubles and gives a Complex; it is the whole algorithm. The wrappers (the
## generated block `wrappers`, an `abi library` operation per C name) take and give the C ABI's struct: `double
## complex` is a Complex (two doubles in floating registers), `float complex` a ComplexSingle (D-175). The f forms widen
## to double, run the double algorithm, and narrow each part once (so they are within 0.5 ulp of the double result
## rounded, plus the double's own error).
##
## Errno. The C99 complex functions raise floating-point exceptions and do not set errno; the real functions this
## module calls (exp, log, sin, atan2 of cmathexp and cmathtrig) do, as a side effect. Every wrapper keeps errno as it
## found it, so no complex function sets it (D-176).
##
## The algorithms. Everything is built from the double-precision real functions of cmathexp and cmathtrig (each within
## 1 ulp), the hardware square root, and double-double sums where a cancellation would lose digits:
## - |z| is the correctly rounded square root of a double-double sum of squares (scaled by powers of two against
##   overflow and underflow), one Newton correction on a double-double residual; log|z| near |z| = 1 is log1p of
##   x*x + y*y - 1 summed in double-double.
## - cexp scales e^x in two steps past +-700, so the product with cos y or sin y overflows or underflows only at the end.
## - csqrt is the usual one with no cancellation: t = sqrt((|x| + |z|)/2), and the other part y/(2t); scaled by even
##   powers of two.
## - csinh and ccosh are sinh x cos y, cosh x sin y and their kin, with sinh by a Taylor series below 1 and by e^x above,
##   and the same two-step scaling past 700. ctanh is Kahan's formula with t = tan y, beta = 1 + t*t, and for |x| >= 20
##   the limit 1 + 4 i sin y cos y e^(-2|x|).
## - casinh, cacosh, cacos start from Hull, Fairgrieve and Tang's kernel (the real part of asin by asin, acos, or atan
##   according to B = x/A, A = (R+S)/2; the imaginary part by log1p of A - 1 and its root when A is below 1.5), applied to
##   the magnitudes and given the signs of the arguments; the rest follow from the identities casin(z) = -i casinh(iz),
##   catan(z) = -i catanh(iz), csin(z) = -i csinh(iz), ctan(z) = -i ctanh(iz), ccos(z) = ccosh(iz), cacos(z) built from
##   cacosh(z), as Annex G states them.
## - catanh is (1/4) log1p(4x/((1-x)^2 + y^2)) for the real part, (1/2) atan2(2y, 1 - x^2 - y^2) for the imaginary part
##   with that difference summed in double-double.
## - cpow is cexp(y clog x) with C99's multiplication (Annex G's recovery of infinities).
## Annex G's special values are written out case by case. Where Annex G leaves a sign or an exception unspecified,
## glibc's choice is followed (a NaN is the default NaN of the operation; see each operation's note).

## @generated polynomials
op sinhPoly "The Taylor coefficients of sinh past x, in z = x*x: 1/3! + z/5! + ... to x^23 (exact 1/k! rounded to doubles)"
  input z Float64 copied
  output Float64
:begin
  calc value = ((((((((((0x1.761b41316381ap-75) * z + 0x1.71b8ef6dcf572p-66) * z + 0x1.2f49b46814157p-57) * z + 0x1.952c77030ad4ap-49) * z + 0x1.ae7f3e733b81fp-41) * z + 0x1.6124613a86d09p-33) * z + 0x1.ae64567f544e4p-26) * z + 0x1.71de3a556c734p-19) * z + 0x1.a01a01a01a01ap-13) * z + 0x1.1111111111111p-7) * z + 0x1.5555555555555p-3
  return value
## @end polynomials

## ---------------------------------------------------------------- bits and tests of a double

op absoluteOf "The magnitude of a double: its sign bit cleared"
  input x Float64 copied
  output Float64
:begin
  calc field = convert.float64BitsToUInt64(x)
  calc cleared = field & 9223372036854775807
  calc value = convert.uint64BitsToFloat64(cleared)
  return value

op signedLike "The magnitude of a double with the sign bit of another"
  input magnitude Float64 copied
  input sign Float64 copied
  output Float64
:begin
  calc magnitudeBits = convert.float64BitsToUInt64(magnitude)
  calc signBits = convert.float64BitsToUInt64(sign)
  calc joined = (magnitudeBits & 9223372036854775807) | (signBits & 9223372036854775808)
  calc value = convert.uint64BitsToFloat64(joined)
  return value

op isNanOf "Whether a double is a NaN"
  input x Float64 copied
  output Bool
:begin
  calc nan = !(x == x)
  return nan

op isInfiniteOf "Whether a double is an infinity"
  input x Float64 copied
  output Bool
:begin
  calc a = absoluteOf(x)
  calc infinite = a > 0x1.fffffffffffffp+1023
  return infinite

op isFiniteOf "Whether a double is neither an infinity nor a NaN"
  input x Float64 copied
  output Bool
:begin
  calc a = absoluteOf(x)
  calc finite = a <= 0x1.fffffffffffffp+1023
  return finite

op plusInfinity "Positive infinity"
  output Float64
:begin
  calc value = convert.uint64BitsToFloat64(9218868437227405312)
  return value

op notANumber "A quiet NaN"
  output Float64
:begin
  calc value = convert.uint64BitsToFloat64(9221120237041090560)
  return value

op largerOf "The larger of two non-negative doubles"
  input a Float64 copied
  input b Float64 copied
  output Float64
:begin
  when a > b giveA giveB
:giveA
  return a
:giveB
  return b

op smallerOf "The smaller of two non-negative doubles"
  input a Float64 copied
  input b Float64 copied
  output Float64
:begin
  when a > b giveB giveA
:giveA
  return a
:giveB
  return b

op quotientOrZero "n / d, or 0 when both are 0 (a term of Hull's sums whose numerator is zero)"
  input n Float64 copied
  input d Float64 copied
  output Float64
  let nothing Float64 0.0
:begin
  when d == 0.0 giveNothing divide
:giveNothing
  return nothing
:divide
  calc quotient = n / d
  return quotient

## ---------------------------------------------------------------- errno

op keepErrno "The value errno has now"
  output Int32
  effect use machine.memory
  uses memoryAccess
:begin
  cell = clibrary.errnoCell()
  value = machine.loadInt32(cell)
  return value

op restoreErrno "Put back a value errno had"
  input value Int32 copied
  effect use machine.memory
  uses memoryAccess
:begin
  clibrary.setErrno(value)
  return

## ---------------------------------------------------------------- double-double pieces

op sumErrorOf "The error of s = a + b in doubles, exactly (Knuth's two-sum): a + b = s + error"
  input a Float64 copied
  input b Float64 copied
  input s Float64 copied
  output Float64
:begin
  calc virtual = s - a
  calc error = (a - (s - virtual)) + (b - virtual)
  return error

op highPart "The top 26 bits of a double (Dekker's split by 2^27 + 1)"
  input a Float64 copied
  output Float64
:begin
  calc scaled = 134217729.0 * a
  calc high = scaled - (scaled - a)
  return high

op productErrorOf "The error of p = a * b, exactly (Dekker's product): a * b = p + error"
  input a Float64 copied
  input b Float64 copied
  input p Float64 copied
  output Float64
:begin
  calc aHigh = highPart(a)
  calc aLow = a - aHigh
  calc bHigh = highPart(b)
  calc bLow = b - bHigh
  calc error = (((aHigh * bHigh - p) + aHigh * bLow) + aLow * bHigh) + aLow * bLow
  return error

op powerOfTwo "2 to a power from -1022 to 1023"
  input power Int64 copied
  output Float64
:begin
  calc field = convert.int64ToUInt64((power + 1023) << 52)
  calc value = convert.uint64BitsToFloat64(field)
  return value

op oneMinusSquares "1 - x*x - y*y, summed in double-double and rounded once (for |x|, |y| below 2^500)"
  input x Float64 copied
  input y Float64 copied
  output Float64
:begin
  calc xx = x * x
  calc xxError = productErrorOf(x, x, xx)
  calc yy = y * y
  calc yyError = productErrorOf(y, y, yy)
  calc first = 1.0 - xx
  calc firstError = sumErrorOf(1.0, -xx, first)
  calc second = first - yy
  calc secondError = sumErrorOf(first, -yy, second)
  calc rest = ((firstError + secondError) - xxError) - yyError
  calc value = second + rest
  return value

op squaresMinusOne "x*x + y*y - 1, summed in double-double and rounded once (for |x|, |y| below 2^500)"
  input x Float64 copied
  input y Float64 copied
  output Float64
:begin
  calc xx = x * x
  calc xxError = productErrorOf(x, x, xx)
  calc yy = y * y
  calc yyError = productErrorOf(y, y, yy)
  calc first = xx - 1.0
  calc firstError = sumErrorOf(xx, -1.0, first)
  calc second = first + yy
  calc secondError = sumErrorOf(first, yy, second)
  calc rest = (((firstError + secondError) + xxError) + yyError)
  calc value = second + rest
  return value

## ---------------------------------------------------------------- real functions the complex ones need

op hypotenuseOf "sqrt(a*a + b*b), within 0.51 ulp: Annex F's infinity for an infinite argument even beside a NaN"
  input a Float64 copied
  input b Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  let scale Float64 1.0 mut
  let unscale Float64 1.0 mut
:begin
  calc ax = absoluteOf(a)
  calc ay = absoluteOf(b)
  calc aInfinite = isInfiniteOf(ax)
  calc bInfinite = isInfiniteOf(ay)
  calc anyInfinite = aInfinite || bInfinite
  when anyInfinite giveInfinity checkNan
:giveInfinity
  calc infinity = plusInfinity()
  return infinity
:checkNan
  calc aNan = !(ax == ax)
  calc bNan = !(ay == ay)
  calc anyNan = aNan || bNan
  when anyNan giveNan sizes
:giveNan
  calc nan = ax + ay
  return nan
:sizes
  calc big = largerOf(ax, ay)
  calc small = smallerOf(ax, ay)
  when small == 0.0 giveBig scaling
:giveBig
  return big
:scaling
  when big > 0x1p+500 shrink checkSmall
:shrink
  calc scale := 0x1p-600
  calc unscale := 0x1p+600
  goto combine
:checkSmall
  when big < 0x1p-500 grow combine
:grow
  calc scale := 0x1p+600
  calc unscale := 0x1p-600
  goto combine
:combine
  calc sa = ax * scale
  calc sb = ay * scale
  calc pa = sa * sa
  calc ea = productErrorOf(sa, sa, pa)
  calc pb = sb * sb
  calc eb = productErrorOf(sb, sb, pb)
  calc total = pa + pb
  calc totalError = sumErrorOf(pa, pb, total)
  calc lowPart = (ea + eb) + totalError
  calc high = total + lowPart
  calc low = lowPart - (high - total)
  calc root = machine.squareRoot(high)
  calc square = root * root
  calc squareError = productErrorOf(root, root, square)
  calc residue = ((high - square) - squareError) + low
  calc refined = root + residue / (2.0 * root)
  calc final = refined * unscale
  return final

op logOnePlusOf "log(1 + x) for x >= -1: log(u) + (x - (u - 1))/u with u = 1 + x rounded, so a small x keeps its digits"
  input x Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc infinite = x > 0x1.fffffffffffffp+1023
  when infinite giveSelf finite
:giveSelf
  return x
:finite
  calc u = 1.0 + x
  when u == 1.0 giveX notOne
:giveX
  return x
:notOne
  when u <= 0.0 giveLog notNonPositive
:giveLog
  calc edge = cmathexp.naturalLogarithm(u)
  return edge
:notNonPositive
  calc l = cmathexp.naturalLogarithm(u)
  calc correction = (x - (u - 1.0)) / u
  calc value = l + correction
  return value

op sinhSeries "sinh(x) for |x| below 1 by its Taylor series x + x^3/6 + ..."
  input x Float64 copied
  output Float64
:begin
  calc z = x * x
  calc poly = sinhPoly(z)
  calc value = x + (x * z) * poly
  return value

op hyperbolicSine "sinh(a) for 0 <= a < 700"
  input a Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  when a < 1.0 series checkMiddle
:series
  calc small = sinhSeries(a)
  return small
:checkMiddle
  calc e = cmathexp.exponential(a)
  when a < 22.0 middle large
:middle
  calc difference = (e - 1.0 / e) * 0.5
  return difference
:large
  calc half = e * 0.5
  return half

op hyperbolicCosine "cosh(a) for 0 <= a < 700"
  input a Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc e = cmathexp.exponential(a)
  when a < 22.0 middle large
:middle
  calc sum = (e + 1.0 / e) * 0.5
  return sum
:large
  calc half = e * 0.5
  return half

op sinhTimes "sinh(x) * t, for finite x and a finite t that is not zero where sinh x overflows: the exponential is taken in two steps past 700"
  input x Float64 copied
  input t Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc a = absoluteOf(x)
  when a < 700.0 direct scaled
:direct
  calc h = hyperbolicSine(a)
  calc product = h * t
  calc signed = product * signedLike(1.0, x)
  return signed
:scaled
  calc lowExponential = cmathexp.exponential(a - 700.0)
  calc half = lowExponential * 0.5
  calc inner = half * t
  calc highExponential = cmathexp.exponential(700.0)
  calc big = inner * highExponential
  calc bigSigned = big * signedLike(1.0, x)
  return bigSigned

op coshTimes "cosh(x) * t, for finite x and a nonzero finite t: the exponential is taken in two steps past 700"
  input x Float64 copied
  input t Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc a = absoluteOf(x)
  when a < 700.0 direct scaled
:direct
  calc h = hyperbolicCosine(a)
  calc product = h * t
  return product
:scaled
  calc lowExponential = cmathexp.exponential(a - 700.0)
  calc half = lowExponential * 0.5
  calc inner = half * t
  calc highExponential = cmathexp.exponential(700.0)
  calc big = inner * highExponential
  return big

## ---------------------------------------------------------------- |z|, carg, clog

op logOfMagnitude "log(|x + iy|), within 1 ulp and nearly exact near |z| = 1; -inf for 0, +inf for an infinite part, NaN otherwise for a NaN"
  input x Float64 copied
  input y Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc ax = absoluteOf(x)
  calc ay = absoluteOf(y)
  calc xInfinite = isInfiniteOf(ax)
  calc yInfinite = isInfiniteOf(ay)
  calc anyInfinite = xInfinite || yInfinite
  when anyInfinite giveInfinity checkNan
:giveInfinity
  calc infinity = plusInfinity()
  return infinity
:checkNan
  calc anyNan = !(ax == ax) || !(ay == ay)
  when anyNan giveNan sizes
:giveNan
  calc nan = ax + ay
  return nan
:sizes
  calc big = largerOf(ax, ay)
  calc small = smallerOf(ax, ay)
  when big == 0.0 giveMinusInfinity checkHuge
:giveMinusInfinity
  calc minusInfinity = cmathexp.naturalLogarithm(0.0)
  return minusInfinity
:checkHuge
  when big > 0x1p+500 huge checkTiny
:huge
  calc hugeLength = hypotenuseOf(ax * 0x1p-600, ay * 0x1p-600)
  calc hugeLog = cmathexp.naturalLogarithm(hugeLength)
  calc hugeBase = hugeLog + 0x1.62e42fee00000p-1 * 600.0
  calc hugeValue = hugeBase + 0x1.a39ef35793c76p-33 * 600.0
  return hugeValue
:checkTiny
  when big < 0x1p-500 tiny moderate
:tiny
  calc tinyLength = hypotenuseOf(ax * 0x1p+600, ay * 0x1p+600)
  calc tinyLog = cmathexp.naturalLogarithm(tinyLength)
  calc tinyBase = tinyLog - 0x1.62e42fee00000p-1 * 600.0
  calc tinyValue = tinyBase - 0x1.a39ef35793c76p-33 * 600.0
  return tinyValue
:moderate
  calc inBand = (big >= 0.5) && (big <= 1.5)
  when inBand band plain
:band
  calc v = squaresMinusOne(ax, ay)
  calc l1 = logOnePlusOf(v)
  calc halved = l1 * 0.5
  return halved
:plain
  calc length = hypotenuseOf(ax, ay)
  calc plainLog = cmathexp.naturalLogarithm(length)
  return plainLog

## ---------------------------------------------------------------- cexp, clog, cpow, csqrt

op exponentialParts "cexp(x + iy): e^x cis(y), Annex G's cases for infinities and NaN"
  input x Float64 copied
  input y Float64 copied
  output Complex
  effect use machine.memory
  uses memoryAccess
:begin
  calc xNan = isNanOf(x)
  when xNan realNan realNotNan
:realNan
  when y == 0.0 nanZero nanBoth
:nanZero
  nanZeroResult = Complex.new(x, y)
  return nanZeroResult
:nanBoth
  calc bothNan = notANumber()
  nanBothResult = Complex.new(bothNan, bothNan)
  return nanBothResult
:realNotNan
  calc xInfinite = isInfiniteOf(x)
  calc yFinite = isFiniteOf(y)
  when xInfinite realInfinite realFinite
:realInfinite
  calc positive = x > 0.0
  when positive plusInfinityCase minusInfinityCase
:plusInfinityCase
  when yFinite plusFinite plusOther
:plusFinite
  when y == 0.0 plusZero plusAngle
:plusZero
  plusZeroResult = Complex.new(x, y)
  return plusZeroResult
:plusAngle
  calc plusCosine = cmathtrig.cosineOf(y)
  calc plusSine = cmathtrig.sineOf(y)
  calc plusReal = signedLike(x, plusCosine)
  calc plusImag = signedLike(x, plusSine)
  plusAngleResult = Complex.new(plusReal, plusImag)
  return plusAngleResult
:plusOther
  calc plusNan = notANumber()
  plusOtherResult = Complex.new(x, plusNan)
  return plusOtherResult
:minusInfinityCase
  when yFinite minusFinite minusOther
:minusFinite
  when y == 0.0 minusZero minusAngle
:minusZero
  minusZeroResult = Complex.new(0.0, y)
  return minusZeroResult
:minusAngle
  calc minusCosine = cmathtrig.cosineOf(y)
  calc minusSine = cmathtrig.sineOf(y)
  calc minusReal = signedLike(0.0, minusCosine)
  calc minusImag = signedLike(0.0, minusSine)
  minusAngleResult = Complex.new(minusReal, minusImag)
  return minusAngleResult
:minusOther
  calc otherImag = signedLike(0.0, y)
  minusOtherResult = Complex.new(0.0, otherImag)
  return minusOtherResult
:realFinite
  when yFinite finiteBoth badImag
:badImag
  calc badNan = notANumber()
  badImagResult = Complex.new(badNan, badNan)
  return badImagResult
:finiteBoth
  when y == 0.0 realOnly general
:realOnly
  calc realOnlyValue = cmathexp.exponential(x)
  realOnlyResult = Complex.new(realOnlyValue, y)
  return realOnlyResult
:general
  calc cosine = cmathtrig.cosineOf(y)
  calc sine = cmathtrig.sineOf(y)
  when x > 700.0 scaledUp checkDown
:scaledUp
  calc upLow = cmathexp.exponential(x - 700.0)
  calc upHigh = cmathexp.exponential(700.0)
  calc upReal = (cosine * upLow) * upHigh
  calc upImag = (sine * upLow) * upHigh
  scaledUpResult = Complex.new(upReal, upImag)
  return scaledUpResult
:checkDown
  when x < -700.0 scaledDown plain
:scaledDown
  calc downHigh = cmathexp.exponential(x + 700.0)
  calc downLow = cmathexp.exponential(-700.0)
  calc downReal = (cosine * downHigh) * downLow
  calc downImag = (sine * downHigh) * downLow
  scaledDownResult = Complex.new(downReal, downImag)
  return scaledDownResult
:plain
  calc magnitude = cmathexp.exponential(x)
  calc plainReal = cosine * magnitude
  calc plainImag = sine * magnitude
  plainResult = Complex.new(plainReal, plainImag)
  return plainResult

op logarithmParts "clog(x + iy): log|z| + i carg(z), Annex G's cases following from log|z| and atan2"
  input x Float64 copied
  input y Float64 copied
  output Complex
  effect use machine.memory
  uses memoryAccess
:begin
  calc real = logOfMagnitude(x, y)
  calc imag = cmathtrig.arcTangent2Of(y, x)
  result = Complex.new(real, imag)
  return result

op squareRootParts "csqrt(x + iy): the root with a non-negative real part, the imaginary part with y's sign; Annex G's cases"
  input x Float64 copied
  input y Float64 copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  let factor Float64 1.0 mut
  let back Float64 1.0 mut
:begin
  calc yInfinite = isInfiniteOf(y)
  when yInfinite imagInfinite checkRealInfinite
:imagInfinite
  calc infinityA = plusInfinity()
  imagInfiniteResult = Complex.new(infinityA, y)
  return imagInfiniteResult
:checkRealInfinite
  calc xInfinite = isInfiniteOf(x)
  when xInfinite realInfinite checkNan
:realInfinite
  calc yNanA = isNanOf(y)
  calc positive = x > 0.0
  when positive plusCase minusCase
:plusCase
  when yNanA plusNan plusSigned
:plusNan
  calc plusNanValue = notANumber()
  plusNanResult = Complex.new(x, plusNanValue)
  return plusNanResult
:plusSigned
  calc plusImag = signedLike(0.0, y)
  plusSignedResult = Complex.new(x, plusImag)
  return plusSignedResult
:minusCase
  when yNanA minusNan minusSigned
:minusNan
  calc minusNanValue = notANumber()
  calc minusInfinity = plusInfinity()
  minusNanResult = Complex.new(minusNanValue, minusInfinity)
  return minusNanResult
:minusSigned
  calc minusInfinityB = plusInfinity()
  calc minusImagB = signedLike(minusInfinityB, y)
  minusSignedResult = Complex.new(0.0, minusImagB)
  return minusSignedResult
:checkNan
  calc anyNan = !(x == x) || !(y == y)
  when anyNan giveNan finite
:giveNan
  calc nanValue = notANumber()
  nanResult = Complex.new(nanValue, nanValue)
  return nanResult
:finite
  calc ax = absoluteOf(x)
  calc ay = absoluteOf(y)
  calc big = largerOf(ax, ay)
  when big == 0.0 zeroCase checkHuge
:zeroCase
  zeroResult = Complex.new(0.0, y)
  return zeroResult
:checkHuge
  when big > 0x1p+1000 shrink checkSmall
:shrink
  calc factor := 0x1p-4
  calc back := 0x1p+2
  goto root
:checkSmall
  when big < 0x1p-500 grow root
:grow
  calc factor := 0x1p+200
  calc back := 0x1p-100
  goto root
:root
  calc sx = x * factor
  calc sy = y * factor
  calc h = hypotenuseOf(sx, sy)
  when sx >= 0.0 rightHalf leftHalf
:rightHalf
  calc rightSum = (sx + h) * 0.5
  calc t = machine.squareRoot(rightSum)
  calc rightImag = sy / (2.0 * t)
  calc rightRealOut = t * back
  calc rightImagOut = rightImag * back
  rightResult = Complex.new(rightRealOut, rightImagOut)
  return rightResult
:leftHalf
  calc leftSum = (h - sx) * 0.5
  calc u = machine.squareRoot(leftSum)
  calc leftReal = absoluteOf(sy) / (2.0 * u)
  calc leftImag = signedLike(u, y)
  calc leftRealOut = leftReal * back
  calc leftImagOut = leftImag * back
  leftResult = Complex.new(leftRealOut, leftImagOut)
  return leftResult


op infinityUnit "1 with the sign of v when v is an infinity, else 0 with v's sign"
  input v Float64 copied
  output Float64
:begin
  calc infinite = isInfiniteOf(v)
  when infinite unit nothing
:unit
  calc signedUnit = signedLike(1.0, v)
  return signedUnit
:nothing
  calc signedNothing = signedLike(0.0, v)
  return signedNothing

op zeroIfNan "v, or 0 with v's sign when v is a NaN"
  input v Float64 copied
  output Float64
:begin
  when v == v keep clear
:keep
  return v
:clear
  calc cleared = signedLike(0.0, v)
  return cleared

op productParts "(a + ib)(c + id) as C99 gives it: ac - bd and ad + bc, with Annex G's recovery of infinities from a NaN result"
  input a Float64 copied
  input b Float64 copied
  input c Float64 copied
  input d Float64 copied
  output Complex
  let pa Float64 0.0 mut
  let pb Float64 0.0 mut
  let pc Float64 0.0 mut
  let pd Float64 0.0 mut
  let recalc Bool false mut
:begin
  calc ac = a * c
  calc bd = b * d
  calc ad = a * d
  calc bc = b * c
  calc real = ac - bd
  calc imag = ad + bc
  calc bothNan = !(real == real) && !(imag == imag)
  when bothNan recover plain
:plain
  plainResult = Complex.new(real, imag)
  return plainResult
:recover
  calc pa := a
  calc pb := b
  calc pc := c
  calc pd := d
  calc leftInfinite = isInfiniteOf(a) || isInfiniteOf(b)
  calc rightInfinite = isInfiniteOf(c) || isInfiniteOf(d)
  when leftInfinite fixLeft afterLeft
:fixLeft
  calc pa := infinityUnit(a)
  calc pb := infinityUnit(b)
  calc pc := zeroIfNan(c)
  calc pd := zeroIfNan(d)
  calc recalc := true
  goto afterLeft
:afterLeft
  when rightInfinite fixRight afterRight
:fixRight
  calc pc := infinityUnit(c)
  calc pd := infinityUnit(d)
  calc pa := zeroIfNan(pa)
  calc pb := zeroIfNan(pb)
  calc recalc := true
  goto afterRight
:afterRight
  calc overflowed = isInfiniteOf(ac) || isInfiniteOf(bd) || isInfiniteOf(ad) || isInfiniteOf(bc)
  calc needThird = overflowed && !recalc
  when needThird fixThird checkRecalc
:fixThird
  calc pa := zeroIfNan(a)
  calc pb := zeroIfNan(b)
  calc pc := zeroIfNan(c)
  calc pd := zeroIfNan(d)
  calc recalc := true
  goto checkRecalc
:checkRecalc
  when recalc again plain
:again
  calc infinity = plusInfinity()
  calc newReal = (pa * pc) - (pb * pd)
  calc newImag = (pa * pd) + (pb * pc)
  calc finalReal = infinity * newReal
  calc finalImag = infinity * newImag
  againResult = Complex.new(finalReal, finalImag)
  return againResult

op powerParts "cpow(x, y) = cexp(y clog x), as glibc computes it"
  input a Float64 copied
  input b Float64 copied
  input c Float64 copied
  input d Float64 copied
  output Complex
  effect use machine.memory
  uses memoryAccess
:begin
  l = logarithmParts(a, b)
  lr = Complex.real(l)
  li = Complex.imag(l)
  p = productParts(c, d, lr, li)
  pr = Complex.real(p)
  pi = Complex.imag(p)
  result = exponentialParts(pr, pi)
  return result

## ---------------------------------------------------------------- csinh, ccosh, ctanh

op hyperbolicSineParts "csinh(x + iy) = sinh x cos y + i cosh x sin y, Annex G's cases"
  input x Float64 copied
  input y Float64 copied
  output Complex
  effect use machine.memory
  uses memoryAccess
:begin
  calc xNan = isNanOf(x)
  when xNan nanReal notNanReal
:nanReal
  when y == 0.0 nanZero nanBoth
:nanZero
  nanZeroResult = Complex.new(x, y)
  return nanZeroResult
:nanBoth
  calc bothNan = notANumber()
  nanBothResult = Complex.new(bothNan, bothNan)
  return nanBothResult
:notNanReal
  calc xInfinite = isInfiniteOf(x)
  calc yFinite = isFiniteOf(y)
  when xInfinite infiniteReal finiteReal
:infiniteReal
  when yFinite infiniteFinite infiniteOther
:infiniteFinite
  when y == 0.0 infiniteZero infiniteAngle
:infiniteZero
  infiniteZeroResult = Complex.new(x, y)
  return infiniteZeroResult
:infiniteAngle
  calc infiniteCosine = cmathtrig.cosineOf(y)
  calc infiniteSine = cmathtrig.sineOf(y)
  calc infinity = plusInfinity()
  calc signedCosine = infiniteCosine * signedLike(1.0, x)
  calc infiniteReal2 = signedLike(infinity, signedCosine)
  calc infiniteImag2 = signedLike(infinity, infiniteSine)
  infiniteAngleResult = Complex.new(infiniteReal2, infiniteImag2)
  return infiniteAngleResult
:infiniteOther
  calc infiniteNan = notANumber()
  infiniteOtherResult = Complex.new(x, infiniteNan)
  return infiniteOtherResult
:finiteReal
  when yFinite finiteImag finiteBad
:finiteBad
  calc badNan = notANumber()
  when x == 0.0 zeroBad nonzeroBad
:zeroBad
  zeroBadResult = Complex.new(x, badNan)
  return zeroBadResult
:nonzeroBad
  nonzeroBadResult = Complex.new(badNan, badNan)
  return nonzeroBadResult
:finiteImag
  when y == 0.0 yZero yAngle
:yZero
  calc zeroSine = sinhTimes(x, 1.0)
  yZeroResult = Complex.new(zeroSine, y)
  return yZeroResult
:yAngle
  calc cosine = cmathtrig.cosineOf(y)
  calc sine = cmathtrig.sineOf(y)
  calc sineReal = sinhTimes(x, cosine)
  calc sineImag = coshTimes(x, sine)
  yAngleResult = Complex.new(sineReal, sineImag)
  return yAngleResult

op hyperbolicCosineParts "ccosh(x + iy) = cosh x cos y + i sinh x sin y, Annex G's cases"
  input x Float64 copied
  input y Float64 copied
  output Complex
  effect use machine.memory
  uses memoryAccess
:begin
  calc xNan = isNanOf(x)
  when xNan nanReal notNanReal
:nanReal
  when y == 0.0 nanZero nanBoth
:nanZero
  nanZeroResult = Complex.new(x, y)
  return nanZeroResult
:nanBoth
  calc bothNan = notANumber()
  nanBothResult = Complex.new(bothNan, bothNan)
  return nanBothResult
:notNanReal
  calc xInfinite = isInfiniteOf(x)
  calc yFinite = isFiniteOf(y)
  when xInfinite infiniteReal finiteReal
:infiniteReal
  when yFinite infiniteFinite infiniteOther
:infiniteFinite
  when y == 0.0 infiniteZero infiniteAngle
:infiniteZero
  calc infinityZero = plusInfinity()
  calc zeroImag = signedLike(1.0, x) * y
  infiniteZeroResult = Complex.new(infinityZero, zeroImag)
  return infiniteZeroResult
:infiniteAngle
  calc infiniteCosine = cmathtrig.cosineOf(y)
  calc infiniteSine = cmathtrig.sineOf(y)
  calc infinity = plusInfinity()
  calc signedSine = infiniteSine * signedLike(1.0, x)
  calc infiniteReal2 = signedLike(infinity, infiniteCosine)
  calc infiniteImag2 = signedLike(infinity, signedSine)
  infiniteAngleResult = Complex.new(infiniteReal2, infiniteImag2)
  return infiniteAngleResult
:infiniteOther
  calc infinityOther = plusInfinity()
  calc infiniteNan = notANumber()
  infiniteOtherResult = Complex.new(infinityOther, infiniteNan)
  return infiniteOtherResult
:finiteReal
  when yFinite finiteImag finiteBad
:finiteBad
  calc badNan = notANumber()
  when x == 0.0 zeroBad nonzeroBad
:zeroBad
  calc badZero = signedLike(0.0, x)
  zeroBadResult = Complex.new(badNan, badZero)
  return zeroBadResult
:nonzeroBad
  nonzeroBadResult = Complex.new(badNan, badNan)
  return nonzeroBadResult
:finiteImag
  when y == 0.0 yZero yAngle
:yZero
  calc zeroCosine = coshTimes(x, 1.0)
  calc yZeroImag = signedLike(1.0, x) * y
  yZeroResult = Complex.new(zeroCosine, yZeroImag)
  return yZeroResult
:yAngle
  calc cosine = cmathtrig.cosineOf(y)
  calc sine = cmathtrig.sineOf(y)
  calc coshReal = coshTimes(x, cosine)
  calc coshImag = sinhTimes(x, sine)
  yAngleResult = Complex.new(coshReal, coshImag)
  return yAngleResult

op hyperbolicTangentParts "ctanh(x + iy): Kahan's formula, (x finite, y infinite) gives a zero with the sign of sin 2x and a NaN as glibc does (so ctan(inf + iy) is a NaN and a zero), and for |x| >= 20 the limit +-1 + 4 i sin y cos y e^(-2|x|); Annex G's cases"
  input x Float64 copied
  input y Float64 copied
  output Complex
  effect use machine.memory
  uses memoryAccess
:begin
  calc xNan = isNanOf(x)
  when xNan nanReal notNanReal
:nanReal
  when y == 0.0 nanZero nanBoth
:nanZero
  nanZeroResult = Complex.new(x, y)
  return nanZeroResult
:nanBoth
  calc bothNan = notANumber()
  nanBothResult = Complex.new(bothNan, bothNan)
  return nanBothResult
:notNanReal
  calc xInfinite = isInfiniteOf(x)
  calc yFinite = isFiniteOf(y)
  when xInfinite infiniteReal finiteReal
:infiniteReal
  calc infiniteOne = signedLike(1.0, x)
  when yFinite infiniteFinite infiniteOther
:infiniteFinite
  when y == 0.0 infiniteZero infiniteAngle
:infiniteZero
  infiniteZeroResult = Complex.new(infiniteOne, y)
  return infiniteZeroResult
:infiniteAngle
  calc infiniteCosine = cmathtrig.cosineOf(y)
  calc infiniteSine = cmathtrig.sineOf(y)
  calc infiniteProduct = infiniteSine * infiniteCosine
  calc infiniteImag = signedLike(0.0, infiniteProduct)
  infiniteAngleResult = Complex.new(infiniteOne, infiniteImag)
  return infiniteAngleResult
:infiniteOther
  calc otherImag = signedLike(0.0, y)
  infiniteOtherResult = Complex.new(infiniteOne, otherImag)
  return infiniteOtherResult
:finiteReal
  when yFinite finiteImag finiteBad
:finiteBad
  calc badNan = notANumber()
  calc badInfinite = isInfiniteOf(y)
  when badInfinite badInfiniteCase badBoth
:badInfiniteCase
  when x == 0.0 badZero badSigned
:badZero
  badZeroResult = Complex.new(x, badNan)
  return badZeroResult
:badSigned
  calc badSine = cmathtrig.sineOf(x)
  calc badCosine = cmathtrig.cosineOf(x)
  calc badProduct = badSine * badCosine
  calc badReal = signedLike(0.0, badProduct)
  badSignedResult = Complex.new(badReal, badNan)
  return badSignedResult
:badBoth
  badResult = Complex.new(badNan, badNan)
  return badResult
:finiteImag
  calc ax = absoluteOf(x)
  when ax >= 20.0 saturated moderate
:saturated
  calc satCosine = cmathtrig.cosineOf(y)
  calc satSine = cmathtrig.sineOf(y)
  calc decay = cmathexp.exponential(-2.0 * ax)
  calc satImag = ((4.0 * satSine) * satCosine) * decay
  calc satReal = signedLike(1.0, x)
  saturatedResult = Complex.new(satReal, satImag)
  return saturatedResult
:moderate
  calc t = cmathtrig.tangentOf(y)
  calc beta = 1.0 + t * t
  calc s = hyperbolicSine(ax)
  calc rho = hyperbolicCosine(ax)
  calc denominator = 1.0 + (beta * s) * s
  calc signedS = s * signedLike(1.0, x)
  calc moderateReal = ((beta * rho) * signedS) / denominator
  calc moderateImag = t / denominator
  moderateResult = Complex.new(moderateReal, moderateImag)
  return moderateResult

## ---------------------------------------------------------------- Hull's kernel and the inverse functions

op hullKernel "For x, y >= 0 finite: Re asin(x + iy), Re acos(x + iy) and their common imaginary part, by Hull, Fairgrieve and Tang (ACM TOMS 23, 1997)"
  input x Float64 copied
  input y Float64 copied
  output Kernel
  effect use machine.memory
  uses memoryAccess
  let am1 Float64 0.0 mut
  let amx Float64 0.0 mut
  let sineReal Float64 0.0 mut
  let cosineReal Float64 0.0 mut
  let imag Float64 0.0 mut
:begin
  calc m = largerOf(x, y)
  when m < 0x1p-250 tinyCase checkHuge
:tinyCase
  calc tinyCosine = 0x1.921fb54442d18p+0 - x
  tinyResult = Kernel.new(x, tinyCosine, y)
  return tinyResult
:checkHuge
  when m > 0x1p+500 hugeCase moderate
:hugeCase
  calc hugeSine = cmathtrig.arcTangent2Of(x, y)
  calc hugeCosine = cmathtrig.arcTangent2Of(y, x)
  calc hugeLog = logOfMagnitude(x, y)
  calc hugeImag = hugeLog + 0x1.62e42fefa39efp-1
  hugeResult = Kernel.new(hugeSine, hugeCosine, hugeImag)
  return hugeResult
:moderate
  calc xPlusOne = x + 1.0
  calc xMinusOne = x - 1.0
  calc r = hypotenuseOf(xPlusOne, y)
  calc s = hypotenuseOf(xMinusOne, y)
  calc a = (r + s) * 0.5
  calc b = x / a
  calc ySquared = y * y
  calc rSum = r + xPlusOne
  calc part1 = ySquared / rSum
  calc sSumHigh = s + xMinusOne
  when x <= 1.0 lowX highX
:lowX
  calc oneMinusX = 1.0 - x
  calc sSumLow = s + oneMinusX
  calc part2 = quotientOrZero(ySquared, sSumLow)
  calc amLow = (part1 + part2) * 0.5
  calc am1 := amLow
  calc amxLow = (part1 + sSumLow) * 0.5
  calc amx := amxLow
  goto haveAm1
:highX
  calc amHigh = (part1 + sSumHigh) * 0.5
  calc am1 := amHigh
  goto haveAm1
:haveAm1
  when b <= 0.6417 smallB largeB
:smallB
  calc smallSine = cmathtrig.arcSineOf(b)
  calc smallCosine = cmathtrig.arcCosineOf(b)
  calc sineReal := smallSine
  calc cosineReal := smallCosine
  goto realDone
:largeB
  when x <= 1.0 largeLow largeHigh
:largeLow
  calc lowRoot = machine.squareRoot((a + x) * amx)
  calc lowSine = cmathtrig.arcTangent2Of(x, lowRoot)
  calc lowCosine = cmathtrig.arcTangent2Of(lowRoot, x)
  calc sineReal := lowSine
  calc cosineReal := lowCosine
  goto realDone
:largeHigh
  calc apx = a + x
  calc inner = 0.5 * (apx / rSum + apx / sSumHigh)
  calc highRoot = machine.squareRoot(inner)
  calc scaledRoot = y * highRoot
  calc highSine = cmathtrig.arcTangent2Of(x, scaledRoot)
  calc highCosine = cmathtrig.arcTangent2Of(scaledRoot, x)
  calc sineReal := highSine
  calc cosineReal := highCosine
  goto realDone
:realDone
  when a <= 1.5 nearOne farOne
:nearOne
  calc nearRoot = machine.squareRoot(am1 * (a + 1.0))
  calc nearImag = logOnePlusOf(am1 + nearRoot)
  calc imag := nearImag
  goto finish
:farOne
  calc farRoot = machine.squareRoot((a - 1.0) * (a + 1.0))
  calc farImag = cmathexp.naturalLogarithm(a + farRoot)
  calc imag := farImag
  goto finish
:finish
  result = Kernel.new(sineReal, cosineReal, imag)
  return result

op inverseHyperbolicSineParts "casinh(x + iy): odd, conjugate-symmetric, from the kernel at (|y|, |x|); Annex G's cases"
  input x Float64 copied
  input y Float64 copied
  output Complex
  effect use machine.memory
  uses memoryAccess
:begin
  calc xInfinite = isInfiniteOf(x)
  calc yInfinite = isInfiniteOf(y)
  calc xNan = isNanOf(x)
  calc yNan = isNanOf(y)
  when xInfinite realInfinite checkImagInfinite
:realInfinite
  when yInfinite bothInfinite realInfiniteOnly
:bothInfinite
  calc quarter = signedLike(0x1.921fb54442d18p-1, y)
  bothResult = Complex.new(x, quarter)
  return bothResult
:realInfiniteOnly
  when yNan realInfiniteNan realInfiniteFinite
:realInfiniteNan
  calc nanA = notANumber()
  realInfiniteNanResult = Complex.new(x, nanA)
  return realInfiniteNanResult
:realInfiniteFinite
  calc zeroA = signedLike(0.0, y)
  realInfiniteFiniteResult = Complex.new(x, zeroA)
  return realInfiniteFiniteResult
:checkImagInfinite
  when yInfinite imagInfinite checkNan
:imagInfinite
  calc infinityZ = plusInfinity()
  when xNan imagInfiniteNan imagInfiniteSigned
:imagInfiniteNan
  calc infinityA = signedLike(infinityZ, x)
  calc nanB = notANumber()
  imagInfiniteNanResult = Complex.new(infinityA, nanB)
  return imagInfiniteNanResult
:imagInfiniteSigned
  calc infinityB = signedLike(infinityZ, x)
  calc halfTurn = signedLike(0x1.921fb54442d18p+0, y)
  imagInfiniteSignedResult = Complex.new(infinityB, halfTurn)
  return imagInfiniteSignedResult
:checkNan
  calc anyNan = xNan || yNan
  when anyNan nanCase finite
:nanCase
  when xNan nanReal nanImag
:nanReal
  when y == 0.0 nanRealZero nanBoth
:nanRealZero
  nanRealZeroResult = Complex.new(x, y)
  return nanRealZeroResult
:nanImag
  goto nanBoth
:nanBoth
  calc nanD = notANumber()
  nanBothResult = Complex.new(nanD, nanD)
  return nanBothResult
:finite
  calc ax = absoluteOf(x)
  calc ay = absoluteOf(y)
  k = hullKernel(ay, ax)
  kImag = Kernel.imag(k)
  kSine = Kernel.asinReal(k)
  calc real = signedLike(kImag, x)
  calc imag = signedLike(kSine, y)
  result = Complex.new(real, imag)
  return result

op inverseHyperbolicCosineParts "cacosh(x + iy): from the kernel at (|x|, |y|): real part Im asin, imaginary part acos with y's sign (pi minus it for x < 0); Annex G's cases"
  input x Float64 copied
  input y Float64 copied
  output Complex
  effect use machine.memory
  uses memoryAccess
:begin
  calc xInfinite = isInfiniteOf(x)
  calc yInfinite = isInfiniteOf(y)
  calc xNan = isNanOf(x)
  calc yNan = isNanOf(y)
  calc infinity = plusInfinity()
  when yInfinite imagInfinite checkRealInfinite
:imagInfinite
  when xNan imagInfiniteNan imagInfiniteReal
:imagInfiniteNan
  calc nanA = notANumber()
  imagInfiniteNanResult = Complex.new(infinity, nanA)
  return imagInfiniteNanResult
:imagInfiniteReal
  when xInfinite imagInfiniteBoth imagInfiniteFinite
:imagInfiniteBoth
  when x > 0.0 bothPlus bothMinus
:bothPlus
  calc plusAngle = signedLike(0x1.921fb54442d18p-1, y)
  bothPlusResult = Complex.new(infinity, plusAngle)
  return bothPlusResult
:bothMinus
  calc minusAngle = signedLike(0x1.2d97c7f3321d2p+1, y)
  bothMinusResult = Complex.new(infinity, minusAngle)
  return bothMinusResult
:imagInfiniteFinite
  calc halfTurn = signedLike(0x1.921fb54442d18p+0, y)
  imagInfiniteFiniteResult = Complex.new(infinity, halfTurn)
  return imagInfiniteFiniteResult
:checkRealInfinite
  when xInfinite realInfinite checkNan
:realInfinite
  when yNan realInfiniteNan realInfiniteFinite
:realInfiniteNan
  calc nanB = notANumber()
  realInfiniteNanResult = Complex.new(infinity, nanB)
  return realInfiniteNanResult
:realInfiniteFinite
  when x > 0.0 finitePlus finiteMinus
:finitePlus
  calc plusZero = signedLike(0.0, y)
  finitePlusResult = Complex.new(infinity, plusZero)
  return finitePlusResult
:finiteMinus
  calc minusPi = signedLike(0x1.921fb54442d18p+1, y)
  finiteMinusResult = Complex.new(infinity, minusPi)
  return finiteMinusResult
:checkNan
  when xNan nanBoth checkImagNan
:checkImagNan
  when yNan imagNan finite
:imagNan
  calc nanC = notANumber()
  when x == 0.0 imagNanZero nanBoth
:imagNanZero
  imagNanZeroResult = Complex.new(nanC, 0x1.921fb54442d18p+0)
  return imagNanZeroResult
:nanBoth
  calc nanD = notANumber()
  nanBothResult = Complex.new(nanD, nanD)
  return nanBothResult
:finite
  calc ax = absoluteOf(x)
  calc ay = absoluteOf(y)
  k = hullKernel(ax, ay)
  kImag = Kernel.imag(k)
  kCosine = Kernel.acosReal(k)
  when x < 0.0 negative positive
:negative
  calc turned = (0x1.921fb54442d18p+1 - kCosine) + 0x1.1a62633145c07p-53
  calc negativeImag = signedLike(turned, y)
  negativeResult = Complex.new(kImag, negativeImag)
  return negativeResult
:positive
  calc positiveImag = signedLike(kCosine, y)
  positiveResult = Complex.new(kImag, positiveImag)
  return positiveResult

op inverseCosineParts "cacos(z), built from cacosh(z): (|Im|, -Re with y's sign), which gives Annex G's cases"
  input x Float64 copied
  input y Float64 copied
  output Complex
  effect use machine.memory
  uses memoryAccess
:begin
  p = inverseHyperbolicCosineParts(x, y)
  pr = Complex.real(p)
  pi = Complex.imag(p)
  calc real = absoluteOf(pi)
  calc imag = signedLike(pr, y) * -1.0
  result = Complex.new(real, imag)
  return result

op inverseHyperbolicTangentParts "catanh(x + iy) = (1/4) log1p(4x/((1-x)^2 + y^2)) + i (1/2) atan2(2y, 1 - x^2 - y^2); Annex G's cases"
  input x Float64 copied
  input y Float64 copied
  output Complex
  effect use machine.memory
  uses memoryAccess
:begin
  calc xInfinite = isInfiniteOf(x)
  calc yInfinite = isInfiniteOf(y)
  calc xNan = isNanOf(x)
  calc yNan = isNanOf(y)
  calc zeroOfX = signedLike(0.0, x)
  when yInfinite imagInfinite checkRealInfinite
:imagInfinite
  calc imagHalf = signedLike(0x1.921fb54442d18p+0, y)
  imagInfiniteResult = Complex.new(zeroOfX, imagHalf)
  return imagInfiniteResult
:checkRealInfinite
  when xInfinite realInfinite checkNan
:realInfinite
  when yNan realInfiniteNan realInfiniteFinite
:realInfiniteNan
  realInfiniteNanResult = Complex.new(zeroOfX, y)
  return realInfiniteNanResult
:realInfiniteFinite
  calc finiteHalf = signedLike(0x1.921fb54442d18p+0, y)
  realInfiniteFiniteResult = Complex.new(zeroOfX, finiteHalf)
  return realInfiniteFiniteResult
:checkNan
  when xNan nanReal checkImagNan
:nanReal
  calc nanA = notANumber()
  nanRealResult = Complex.new(nanA, nanA)
  return nanRealResult
:checkImagNan
  when yNan imagNan finite
:imagNan
  calc nanB = notANumber()
  when x == 0.0 imagNanZero imagNanOther
:imagNanZero
  imagNanZeroResult = Complex.new(x, nanB)
  return imagNanZeroResult
:imagNanOther
  imagNanOtherResult = Complex.new(nanB, nanB)
  return imagNanOtherResult
:finite
  calc ax = absoluteOf(x)
  calc ay = absoluteOf(y)
  calc m = largerOf(ax, ay)
  when m > 0x1p+500 huge moderate
:huge
  calc sx = ax / m
  calc sy = ay / m
  calc sum = sx * sx + sy * sy
  calc hugeReal = sx / (m * sum)
  calc hugeAngle = cmathtrig.arcTangent2Of((2.0 * sy) / m, -sum)
  calc hugeImag = hugeAngle * 0.5
  calc hugeRealSigned = signedLike(hugeReal, x)
  calc hugeImagSigned = signedLike(hugeImag, y)
  hugeResult = Complex.new(hugeRealSigned, hugeImagSigned)
  return hugeResult
:moderate
  calc d1 = 1.0 - ax
  calc denominator = d1 * d1 + ay * ay
  calc ratio = (4.0 * ax) / denominator
  calc moderateLog = logOnePlusOf(ratio)
  calc moderateReal = moderateLog * 0.25
  calc numerator = oneMinusSquares(ax, ay)
  calc angle = cmathtrig.arcTangent2Of(2.0 * ay, numerator)
  calc moderateImag = angle * 0.5
  calc realSigned = signedLike(moderateReal, x)
  calc imagSigned = signedLike(moderateImag, y)
  moderateResult = Complex.new(realSigned, imagSigned)
  return moderateResult

## ---------------------------------------------------------------- the rest, by Annex G's identities

op sineParts "csin(z) = -i csinh(iz)"
  input x Float64 copied
  input y Float64 copied
  output Complex
  effect use machine.memory
  uses memoryAccess
:begin
  calc rotated = y * -1.0
  w = hyperbolicSineParts(rotated, x)
  wr = Complex.real(w)
  wi = Complex.imag(w)
  calc imag = wr * -1.0
  result = Complex.new(wi, imag)
  return result

op cosineParts "ccos(z) = ccosh(iz)"
  input x Float64 copied
  input y Float64 copied
  output Complex
  effect use machine.memory
  uses memoryAccess
:begin
  calc rotated = y * -1.0
  result = hyperbolicCosineParts(rotated, x)
  return result

op tangentParts "ctan(z) = -i ctanh(iz)"
  input x Float64 copied
  input y Float64 copied
  output Complex
  effect use machine.memory
  uses memoryAccess
:begin
  calc rotated = y * -1.0
  w = hyperbolicTangentParts(rotated, x)
  wr = Complex.real(w)
  wi = Complex.imag(w)
  calc imag = wr * -1.0
  result = Complex.new(wi, imag)
  return result

op inverseSineParts "casin(z) = -i casinh(iz)"
  input x Float64 copied
  input y Float64 copied
  output Complex
  effect use machine.memory
  uses memoryAccess
:begin
  calc rotated = y * -1.0
  w = inverseHyperbolicSineParts(rotated, x)
  wr = Complex.real(w)
  wi = Complex.imag(w)
  calc imag = wr * -1.0
  result = Complex.new(wi, imag)
  return result

op inverseTangentParts "catan(z) = -i catanh(iz)"
  input x Float64 copied
  input y Float64 copied
  output Complex
  effect use machine.memory
  uses memoryAccess
:begin
  calc rotated = y * -1.0
  w = inverseHyperbolicTangentParts(rotated, x)
  wr = Complex.real(w)
  wi = Complex.imag(w)
  calc imag = wr * -1.0
  result = Complex.new(wi, imag)
  return result

op projectionParts "cproj(z): z, or (+inf, +-0) for a z with an infinite part"
  input x Float64 copied
  input y Float64 copied
  output Complex
:begin
  calc infinite = isInfiniteOf(x) || isInfiniteOf(y)
  when infinite projected same
:projected
  calc infinity = plusInfinity()
  calc zeroOfY = signedLike(0.0, y)
  projectedResult = Complex.new(infinity, zeroOfY)
  return projectedResult
:same
  sameResult = Complex.new(x, y)
  return sameResult

op magnitudeOf "cabs(z) = hypot(x, y)"
  input x Float64 copied
  input y Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc value = hypotenuseOf(x, y)
  return value

op argumentOf "carg(z) = atan2(y, x)"
  input x Float64 copied
  input y Float64 copied
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  calc value = cmathtrig.arcTangent2Of(y, x)
  return value

op conjugateParts "conj(z): the imaginary part negated"
  input x Float64 copied
  input y Float64 copied
  output Complex
:begin
  calc negated = y * -1.0
  result = Complex.new(x, negated)
  return result

op realPartOf "creal: the real part of x + iy, which is x"
  input x Float64 copied
  input y Float64 copied
  output Float64
:begin
  return x

op imaginaryPartOf "cimag: the imaginary part of x + iy, which is y"
  input x Float64 copied
  input y Float64 copied
  output Float64
:begin
  return y

op narrowToSingle "A double as a Float32, rounded to nearest: infinity for one that rounds past the largest float (convert would trap), a NaN or infinity as it is"
  input value Float64 copied
  output Float32
:begin
  calc bits = convert.float64BitsToUInt64(value)
  calc magnitude = bits & 9223372036854775807
  calc overflow = magnitude >= 5183643170835005440 && magnitude < 9218868437227405312
  when overflow toInfinity plain
:toInfinity
  calc infiniteBits = (bits & 9223372036854775808) | 9218868437227405312
  calc infinite = convert.uint64BitsToFloat64(infiniteBits)
  calc result = convert.float64ToFloat32(infinite)
  return result
:plain
  calc narrowed = convert.float64ToFloat32(value)
  return narrowed

## ---------------------------------------------------------------- the C names

## @generated wrappers
op complexExponential "cexp: e to the power z, for a double complex"
  invariant givesCexp "Gives cexp, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "cexp"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  saved = keepErrno()
  wide = exponentialParts(zRe, zIm)
  restoreErrno(saved)
  return wide

op complexLogarithm "clog: the natural logarithm, with the imaginary part in -pi to pi, for a double complex"
  invariant givesClog "Gives clog, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "clog"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  saved = keepErrno()
  wide = logarithmParts(zRe, zIm)
  restoreErrno(saved)
  return wide

op complexSquareRoot "csqrt: the square root with a non-negative real part, for a double complex"
  invariant givesCsqrt "Gives csqrt, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "csqrt"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  saved = keepErrno()
  wide = squareRootParts(zRe, zIm)
  restoreErrno(saved)
  return wide

op complexSine "csin: the sine, for a double complex"
  invariant givesCsin "Gives csin, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "csin"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  saved = keepErrno()
  wide = sineParts(zRe, zIm)
  restoreErrno(saved)
  return wide

op complexCosine "ccos: the cosine, for a double complex"
  invariant givesCcos "Gives ccos, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "ccos"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  saved = keepErrno()
  wide = cosineParts(zRe, zIm)
  restoreErrno(saved)
  return wide

op complexTangent "ctan: the tangent, for a double complex"
  invariant givesCtan "Gives ctan, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "ctan"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  saved = keepErrno()
  wide = tangentParts(zRe, zIm)
  restoreErrno(saved)
  return wide

op complexInverseSine "casin: the arc sine, for a double complex"
  invariant givesCasin "Gives casin, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "casin"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  saved = keepErrno()
  wide = inverseSineParts(zRe, zIm)
  restoreErrno(saved)
  return wide

op complexInverseCosine "cacos: the arc cosine, for a double complex"
  invariant givesCacos "Gives cacos, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "cacos"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  saved = keepErrno()
  wide = inverseCosineParts(zRe, zIm)
  restoreErrno(saved)
  return wide

op complexInverseTangent "catan: the arc tangent, for a double complex"
  invariant givesCatan "Gives catan, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "catan"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  saved = keepErrno()
  wide = inverseTangentParts(zRe, zIm)
  restoreErrno(saved)
  return wide

op complexHyperbolicSine "csinh: the hyperbolic sine, for a double complex"
  invariant givesCsinh "Gives csinh, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "csinh"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  saved = keepErrno()
  wide = hyperbolicSineParts(zRe, zIm)
  restoreErrno(saved)
  return wide

op complexHyperbolicCosine "ccosh: the hyperbolic cosine, for a double complex"
  invariant givesCcosh "Gives ccosh, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "ccosh"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  saved = keepErrno()
  wide = hyperbolicCosineParts(zRe, zIm)
  restoreErrno(saved)
  return wide

op complexHyperbolicTangent "ctanh: the hyperbolic tangent, for a double complex"
  invariant givesCtanh "Gives ctanh, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "ctanh"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  saved = keepErrno()
  wide = hyperbolicTangentParts(zRe, zIm)
  restoreErrno(saved)
  return wide

op complexInverseHyperbolicSine "casinh: the inverse hyperbolic sine, for a double complex"
  invariant givesCasinh "Gives casinh, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "casinh"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  saved = keepErrno()
  wide = inverseHyperbolicSineParts(zRe, zIm)
  restoreErrno(saved)
  return wide

op complexInverseHyperbolicCosine "cacosh: the inverse hyperbolic cosine, for a double complex"
  invariant givesCacosh "Gives cacosh, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "cacosh"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  saved = keepErrno()
  wide = inverseHyperbolicCosineParts(zRe, zIm)
  restoreErrno(saved)
  return wide

op complexInverseHyperbolicTangent "catanh: the inverse hyperbolic tangent, for a double complex"
  invariant givesCatanh "Gives catanh, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "catanh"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  saved = keepErrno()
  wide = inverseHyperbolicTangentParts(zRe, zIm)
  restoreErrno(saved)
  return wide

op complexConjugate "conj: the complex conjugate, for a double complex"
  invariant givesConj "Gives conj, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "conj"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  saved = keepErrno()
  wide = conjugateParts(zRe, zIm)
  restoreErrno(saved)
  return wide

op complexProjection "cproj: the projection onto the Riemann sphere, for a double complex"
  invariant givesCproj "Gives cproj, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "cproj"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  saved = keepErrno()
  wide = projectionParts(zRe, zIm)
  restoreErrno(saved)
  return wide

op complexMagnitude "cabs: the magnitude hypot(x, y), for a double complex"
  invariant givesCabs "Gives cabs, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "cabs"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  saved = keepErrno()
  wide = magnitudeOf(zRe, zIm)
  restoreErrno(saved)
  return wide

op complexArgument "carg: the argument atan2(y, x), for a double complex"
  invariant givesCarg "Gives carg, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "carg"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  saved = keepErrno()
  wide = argumentOf(zRe, zIm)
  restoreErrno(saved)
  return wide

op complexRealPart "creal: the real part, for a double complex"
  invariant givesCreal "Gives creal, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "creal"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  saved = keepErrno()
  wide = realPartOf(zRe, zIm)
  restoreErrno(saved)
  return wide

op complexImaginaryPart "cimag: the imaginary part, for a double complex"
  invariant givesCimag "Gives cimag, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "cimag"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  saved = keepErrno()
  wide = imaginaryPartOf(zRe, zIm)
  restoreErrno(saved)
  return wide

op complexPower "cpow: x to the power y, as cexp(y clog x), for a double complex"
  invariant givesCpow "Gives cpow, within the module's stated bound, with Annex G's special values"
  input z Complex copied
  input w Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "cpow"
:begin
  zRe = Complex.real(z)
  zIm = Complex.imag(z)
  wRe = Complex.real(w)
  wIm = Complex.imag(w)
  saved = keepErrno()
  wide = powerParts(zRe, zIm, wRe, wIm)
  restoreErrno(saved)
  return wide

op complexExponentialSingle "cexpf: e to the power z, for a float complex (computed in double, each part rounded once)"
  invariant givesCexpf "Gives cexpf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  output ComplexSingle
  effect use machine.memory
  uses memoryAccess
  abi library "cexpf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  saved = keepErrno()
  wide = exponentialParts(zRe, zIm)
  restoreErrno(saved)
  wideRe = Complex.real(wide)
  wideIm = Complex.imag(wide)
  calc narrowRe = narrowToSingle(wideRe)
  calc narrowIm = narrowToSingle(wideIm)
  result = ComplexSingle.new(narrowRe, narrowIm)
  return result

op complexLogarithmSingle "clogf: the natural logarithm, with the imaginary part in -pi to pi, for a float complex (computed in double, each part rounded once)"
  invariant givesClogf "Gives clogf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  output ComplexSingle
  effect use machine.memory
  uses memoryAccess
  abi library "clogf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  saved = keepErrno()
  wide = logarithmParts(zRe, zIm)
  restoreErrno(saved)
  wideRe = Complex.real(wide)
  wideIm = Complex.imag(wide)
  calc narrowRe = narrowToSingle(wideRe)
  calc narrowIm = narrowToSingle(wideIm)
  result = ComplexSingle.new(narrowRe, narrowIm)
  return result

op complexSquareRootSingle "csqrtf: the square root with a non-negative real part, for a float complex (computed in double, each part rounded once)"
  invariant givesCsqrtf "Gives csqrtf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  output ComplexSingle
  effect use machine.memory
  uses memoryAccess
  abi library "csqrtf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  saved = keepErrno()
  wide = squareRootParts(zRe, zIm)
  restoreErrno(saved)
  wideRe = Complex.real(wide)
  wideIm = Complex.imag(wide)
  calc narrowRe = narrowToSingle(wideRe)
  calc narrowIm = narrowToSingle(wideIm)
  result = ComplexSingle.new(narrowRe, narrowIm)
  return result

op complexSineSingle "csinf: the sine, for a float complex (computed in double, each part rounded once)"
  invariant givesCsinf "Gives csinf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  output ComplexSingle
  effect use machine.memory
  uses memoryAccess
  abi library "csinf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  saved = keepErrno()
  wide = sineParts(zRe, zIm)
  restoreErrno(saved)
  wideRe = Complex.real(wide)
  wideIm = Complex.imag(wide)
  calc narrowRe = narrowToSingle(wideRe)
  calc narrowIm = narrowToSingle(wideIm)
  result = ComplexSingle.new(narrowRe, narrowIm)
  return result

op complexCosineSingle "ccosf: the cosine, for a float complex (computed in double, each part rounded once)"
  invariant givesCcosf "Gives ccosf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  output ComplexSingle
  effect use machine.memory
  uses memoryAccess
  abi library "ccosf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  saved = keepErrno()
  wide = cosineParts(zRe, zIm)
  restoreErrno(saved)
  wideRe = Complex.real(wide)
  wideIm = Complex.imag(wide)
  calc narrowRe = narrowToSingle(wideRe)
  calc narrowIm = narrowToSingle(wideIm)
  result = ComplexSingle.new(narrowRe, narrowIm)
  return result

op complexTangentSingle "ctanf: the tangent, for a float complex (computed in double, each part rounded once)"
  invariant givesCtanf "Gives ctanf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  output ComplexSingle
  effect use machine.memory
  uses memoryAccess
  abi library "ctanf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  saved = keepErrno()
  wide = tangentParts(zRe, zIm)
  restoreErrno(saved)
  wideRe = Complex.real(wide)
  wideIm = Complex.imag(wide)
  calc narrowRe = narrowToSingle(wideRe)
  calc narrowIm = narrowToSingle(wideIm)
  result = ComplexSingle.new(narrowRe, narrowIm)
  return result

op complexInverseSineSingle "casinf: the arc sine, for a float complex (computed in double, each part rounded once)"
  invariant givesCasinf "Gives casinf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  output ComplexSingle
  effect use machine.memory
  uses memoryAccess
  abi library "casinf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  saved = keepErrno()
  wide = inverseSineParts(zRe, zIm)
  restoreErrno(saved)
  wideRe = Complex.real(wide)
  wideIm = Complex.imag(wide)
  calc narrowRe = narrowToSingle(wideRe)
  calc narrowIm = narrowToSingle(wideIm)
  result = ComplexSingle.new(narrowRe, narrowIm)
  return result

op complexInverseCosineSingle "cacosf: the arc cosine, for a float complex (computed in double, each part rounded once)"
  invariant givesCacosf "Gives cacosf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  output ComplexSingle
  effect use machine.memory
  uses memoryAccess
  abi library "cacosf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  saved = keepErrno()
  wide = inverseCosineParts(zRe, zIm)
  restoreErrno(saved)
  wideRe = Complex.real(wide)
  wideIm = Complex.imag(wide)
  calc narrowRe = narrowToSingle(wideRe)
  calc narrowIm = narrowToSingle(wideIm)
  result = ComplexSingle.new(narrowRe, narrowIm)
  return result

op complexInverseTangentSingle "catanf: the arc tangent, for a float complex (computed in double, each part rounded once)"
  invariant givesCatanf "Gives catanf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  output ComplexSingle
  effect use machine.memory
  uses memoryAccess
  abi library "catanf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  saved = keepErrno()
  wide = inverseTangentParts(zRe, zIm)
  restoreErrno(saved)
  wideRe = Complex.real(wide)
  wideIm = Complex.imag(wide)
  calc narrowRe = narrowToSingle(wideRe)
  calc narrowIm = narrowToSingle(wideIm)
  result = ComplexSingle.new(narrowRe, narrowIm)
  return result

op complexHyperbolicSineSingle "csinhf: the hyperbolic sine, for a float complex (computed in double, each part rounded once)"
  invariant givesCsinhf "Gives csinhf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  output ComplexSingle
  effect use machine.memory
  uses memoryAccess
  abi library "csinhf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  saved = keepErrno()
  wide = hyperbolicSineParts(zRe, zIm)
  restoreErrno(saved)
  wideRe = Complex.real(wide)
  wideIm = Complex.imag(wide)
  calc narrowRe = narrowToSingle(wideRe)
  calc narrowIm = narrowToSingle(wideIm)
  result = ComplexSingle.new(narrowRe, narrowIm)
  return result

op complexHyperbolicCosineSingle "ccoshf: the hyperbolic cosine, for a float complex (computed in double, each part rounded once)"
  invariant givesCcoshf "Gives ccoshf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  output ComplexSingle
  effect use machine.memory
  uses memoryAccess
  abi library "ccoshf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  saved = keepErrno()
  wide = hyperbolicCosineParts(zRe, zIm)
  restoreErrno(saved)
  wideRe = Complex.real(wide)
  wideIm = Complex.imag(wide)
  calc narrowRe = narrowToSingle(wideRe)
  calc narrowIm = narrowToSingle(wideIm)
  result = ComplexSingle.new(narrowRe, narrowIm)
  return result

op complexHyperbolicTangentSingle "ctanhf: the hyperbolic tangent, for a float complex (computed in double, each part rounded once)"
  invariant givesCtanhf "Gives ctanhf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  output ComplexSingle
  effect use machine.memory
  uses memoryAccess
  abi library "ctanhf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  saved = keepErrno()
  wide = hyperbolicTangentParts(zRe, zIm)
  restoreErrno(saved)
  wideRe = Complex.real(wide)
  wideIm = Complex.imag(wide)
  calc narrowRe = narrowToSingle(wideRe)
  calc narrowIm = narrowToSingle(wideIm)
  result = ComplexSingle.new(narrowRe, narrowIm)
  return result

op complexInverseHyperbolicSineSingle "casinhf: the inverse hyperbolic sine, for a float complex (computed in double, each part rounded once)"
  invariant givesCasinhf "Gives casinhf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  output ComplexSingle
  effect use machine.memory
  uses memoryAccess
  abi library "casinhf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  saved = keepErrno()
  wide = inverseHyperbolicSineParts(zRe, zIm)
  restoreErrno(saved)
  wideRe = Complex.real(wide)
  wideIm = Complex.imag(wide)
  calc narrowRe = narrowToSingle(wideRe)
  calc narrowIm = narrowToSingle(wideIm)
  result = ComplexSingle.new(narrowRe, narrowIm)
  return result

op complexInverseHyperbolicCosineSingle "cacoshf: the inverse hyperbolic cosine, for a float complex (computed in double, each part rounded once)"
  invariant givesCacoshf "Gives cacoshf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  output ComplexSingle
  effect use machine.memory
  uses memoryAccess
  abi library "cacoshf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  saved = keepErrno()
  wide = inverseHyperbolicCosineParts(zRe, zIm)
  restoreErrno(saved)
  wideRe = Complex.real(wide)
  wideIm = Complex.imag(wide)
  calc narrowRe = narrowToSingle(wideRe)
  calc narrowIm = narrowToSingle(wideIm)
  result = ComplexSingle.new(narrowRe, narrowIm)
  return result

op complexInverseHyperbolicTangentSingle "catanhf: the inverse hyperbolic tangent, for a float complex (computed in double, each part rounded once)"
  invariant givesCatanhf "Gives catanhf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  output ComplexSingle
  effect use machine.memory
  uses memoryAccess
  abi library "catanhf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  saved = keepErrno()
  wide = inverseHyperbolicTangentParts(zRe, zIm)
  restoreErrno(saved)
  wideRe = Complex.real(wide)
  wideIm = Complex.imag(wide)
  calc narrowRe = narrowToSingle(wideRe)
  calc narrowIm = narrowToSingle(wideIm)
  result = ComplexSingle.new(narrowRe, narrowIm)
  return result

op complexConjugateSingle "conjf: the complex conjugate, for a float complex (computed in double, each part rounded once)"
  invariant givesConjf "Gives conjf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  output ComplexSingle
  effect use machine.memory
  uses memoryAccess
  abi library "conjf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  saved = keepErrno()
  wide = conjugateParts(zRe, zIm)
  restoreErrno(saved)
  wideRe = Complex.real(wide)
  wideIm = Complex.imag(wide)
  calc narrowRe = narrowToSingle(wideRe)
  calc narrowIm = narrowToSingle(wideIm)
  result = ComplexSingle.new(narrowRe, narrowIm)
  return result

op complexProjectionSingle "cprojf: the projection onto the Riemann sphere, for a float complex (computed in double, each part rounded once)"
  invariant givesCprojf "Gives cprojf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  output ComplexSingle
  effect use machine.memory
  uses memoryAccess
  abi library "cprojf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  saved = keepErrno()
  wide = projectionParts(zRe, zIm)
  restoreErrno(saved)
  wideRe = Complex.real(wide)
  wideIm = Complex.imag(wide)
  calc narrowRe = narrowToSingle(wideRe)
  calc narrowIm = narrowToSingle(wideIm)
  result = ComplexSingle.new(narrowRe, narrowIm)
  return result

op complexMagnitudeSingle "cabsf: the magnitude hypot(x, y), for a float complex (computed in double, each part rounded once)"
  invariant givesCabsf "Gives cabsf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "cabsf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  saved = keepErrno()
  wide = magnitudeOf(zRe, zIm)
  restoreErrno(saved)
  calc narrow = narrowToSingle(wide)
  return narrow

op complexArgumentSingle "cargf: the argument atan2(y, x), for a float complex (computed in double, each part rounded once)"
  invariant givesCargf "Gives cargf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "cargf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  saved = keepErrno()
  wide = argumentOf(zRe, zIm)
  restoreErrno(saved)
  calc narrow = narrowToSingle(wide)
  return narrow

op complexRealPartSingle "crealf: the real part, for a float complex (computed in double, each part rounded once)"
  invariant givesCrealf "Gives crealf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "crealf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  saved = keepErrno()
  wide = realPartOf(zRe, zIm)
  restoreErrno(saved)
  calc narrow = narrowToSingle(wide)
  return narrow

op complexImaginaryPartSingle "cimagf: the imaginary part, for a float complex (computed in double, each part rounded once)"
  invariant givesCimagf "Gives cimagf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "cimagf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  saved = keepErrno()
  wide = imaginaryPartOf(zRe, zIm)
  restoreErrno(saved)
  calc narrow = narrowToSingle(wide)
  return narrow

op complexPowerSingle "cpowf: x to the power y, as cexp(y clog x), for a float complex (computed in double, each part rounded once)"
  invariant givesCpowf "Gives cpowf, within the module's stated bound, with Annex G's special values"
  input z ComplexSingle copied
  input w ComplexSingle copied
  output ComplexSingle
  effect use machine.memory
  uses memoryAccess
  abi library "cpowf"
:begin
  zRealSingle = ComplexSingle.real(z)
  zImagSingle = ComplexSingle.imag(z)
  calc zRe = convert.float32ToFloat64(zRealSingle)
  calc zIm = convert.float32ToFloat64(zImagSingle)
  wRealSingle = ComplexSingle.real(w)
  wImagSingle = ComplexSingle.imag(w)
  calc wRe = convert.float32ToFloat64(wRealSingle)
  calc wIm = convert.float32ToFloat64(wImagSingle)
  saved = keepErrno()
  wide = powerParts(zRe, zIm, wRe, wIm)
  restoreErrno(saved)
  wideRe = Complex.real(wide)
  wideIm = Complex.imag(wide)
  calc narrowRe = narrowToSingle(wideRe)
  calc narrowIm = narrowToSingle(wideIm)
  result = ComplexSingle.new(narrowRe, narrowIm)
  return result

op complexExponentialLong "cexpl: e to the power z, for a long double complex, which is a double complex on Windows (D-174): exactly cexp"
  invariant givesCexpl "Gives cexpl, which is cexp's result bit for bit"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "cexpl" windows
:begin
  result = complexExponential(z)
  return result

op complexLogarithmLong "clogl: the natural logarithm, with the imaginary part in -pi to pi, for a long double complex, which is a double complex on Windows (D-174): exactly clog"
  invariant givesClogl "Gives clogl, which is clog's result bit for bit"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "clogl" windows
:begin
  result = complexLogarithm(z)
  return result

op complexSquareRootLong "csqrtl: the square root with a non-negative real part, for a long double complex, which is a double complex on Windows (D-174): exactly csqrt"
  invariant givesCsqrtl "Gives csqrtl, which is csqrt's result bit for bit"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "csqrtl" windows
:begin
  result = complexSquareRoot(z)
  return result

op complexSineLong "csinl: the sine, for a long double complex, which is a double complex on Windows (D-174): exactly csin"
  invariant givesCsinl "Gives csinl, which is csin's result bit for bit"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "csinl" windows
:begin
  result = complexSine(z)
  return result

op complexCosineLong "ccosl: the cosine, for a long double complex, which is a double complex on Windows (D-174): exactly ccos"
  invariant givesCcosl "Gives ccosl, which is ccos's result bit for bit"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "ccosl" windows
:begin
  result = complexCosine(z)
  return result

op complexTangentLong "ctanl: the tangent, for a long double complex, which is a double complex on Windows (D-174): exactly ctan"
  invariant givesCtanl "Gives ctanl, which is ctan's result bit for bit"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "ctanl" windows
:begin
  result = complexTangent(z)
  return result

op complexInverseSineLong "casinl: the arc sine, for a long double complex, which is a double complex on Windows (D-174): exactly casin"
  invariant givesCasinl "Gives casinl, which is casin's result bit for bit"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "casinl" windows
:begin
  result = complexInverseSine(z)
  return result

op complexInverseCosineLong "cacosl: the arc cosine, for a long double complex, which is a double complex on Windows (D-174): exactly cacos"
  invariant givesCacosl "Gives cacosl, which is cacos's result bit for bit"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "cacosl" windows
:begin
  result = complexInverseCosine(z)
  return result

op complexInverseTangentLong "catanl: the arc tangent, for a long double complex, which is a double complex on Windows (D-174): exactly catan"
  invariant givesCatanl "Gives catanl, which is catan's result bit for bit"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "catanl" windows
:begin
  result = complexInverseTangent(z)
  return result

op complexHyperbolicSineLong "csinhl: the hyperbolic sine, for a long double complex, which is a double complex on Windows (D-174): exactly csinh"
  invariant givesCsinhl "Gives csinhl, which is csinh's result bit for bit"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "csinhl" windows
:begin
  result = complexHyperbolicSine(z)
  return result

op complexHyperbolicCosineLong "ccoshl: the hyperbolic cosine, for a long double complex, which is a double complex on Windows (D-174): exactly ccosh"
  invariant givesCcoshl "Gives ccoshl, which is ccosh's result bit for bit"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "ccoshl" windows
:begin
  result = complexHyperbolicCosine(z)
  return result

op complexHyperbolicTangentLong "ctanhl: the hyperbolic tangent, for a long double complex, which is a double complex on Windows (D-174): exactly ctanh"
  invariant givesCtanhl "Gives ctanhl, which is ctanh's result bit for bit"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "ctanhl" windows
:begin
  result = complexHyperbolicTangent(z)
  return result

op complexInverseHyperbolicSineLong "casinhl: the inverse hyperbolic sine, for a long double complex, which is a double complex on Windows (D-174): exactly casinh"
  invariant givesCasinhl "Gives casinhl, which is casinh's result bit for bit"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "casinhl" windows
:begin
  result = complexInverseHyperbolicSine(z)
  return result

op complexInverseHyperbolicCosineLong "cacoshl: the inverse hyperbolic cosine, for a long double complex, which is a double complex on Windows (D-174): exactly cacosh"
  invariant givesCacoshl "Gives cacoshl, which is cacosh's result bit for bit"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "cacoshl" windows
:begin
  result = complexInverseHyperbolicCosine(z)
  return result

op complexInverseHyperbolicTangentLong "catanhl: the inverse hyperbolic tangent, for a long double complex, which is a double complex on Windows (D-174): exactly catanh"
  invariant givesCatanhl "Gives catanhl, which is catanh's result bit for bit"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "catanhl" windows
:begin
  result = complexInverseHyperbolicTangent(z)
  return result

op complexConjugateLong "conjl: the complex conjugate, for a long double complex, which is a double complex on Windows (D-174): exactly conj"
  invariant givesConjl "Gives conjl, which is conj's result bit for bit"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "conjl" windows
:begin
  result = complexConjugate(z)
  return result

op complexProjectionLong "cprojl: the projection onto the Riemann sphere, for a long double complex, which is a double complex on Windows (D-174): exactly cproj"
  invariant givesCprojl "Gives cprojl, which is cproj's result bit for bit"
  input z Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "cprojl" windows
:begin
  result = complexProjection(z)
  return result

op complexMagnitudeLong "cabsl: the magnitude hypot(x, y), for a long double complex, which is a double complex on Windows (D-174): exactly cabs"
  invariant givesCabsl "Gives cabsl, which is cabs's result bit for bit"
  input z Complex copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "cabsl" windows
:begin
  result = complexMagnitude(z)
  return result

op complexArgumentLong "cargl: the argument atan2(y, x), for a long double complex, which is a double complex on Windows (D-174): exactly carg"
  invariant givesCargl "Gives cargl, which is carg's result bit for bit"
  input z Complex copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "cargl" windows
:begin
  result = complexArgument(z)
  return result

op complexRealPartLong "creall: the real part, for a long double complex, which is a double complex on Windows (D-174): exactly creal"
  invariant givesCreall "Gives creall, which is creal's result bit for bit"
  input z Complex copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "creall" windows
:begin
  result = complexRealPart(z)
  return result

op complexImaginaryPartLong "cimagl: the imaginary part, for a long double complex, which is a double complex on Windows (D-174): exactly cimag"
  invariant givesCimagl "Gives cimagl, which is cimag's result bit for bit"
  input z Complex copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "cimagl" windows
:begin
  result = complexImaginaryPart(z)
  return result

op complexPowerLong "cpowl: x to the power y, as cexp(y clog x), for a long double complex, which is a double complex on Windows (D-174): exactly cpow"
  invariant givesCpowl "Gives cpowl, which is cpow's result bit for bit"
  input z Complex copied
  input w Complex copied
  output Complex
  effect use machine.memory
  uses memoryAccess
  abi library "cpowl" windows
:begin
  result = complexPower(z, w)
  return result
## @end wrappers

@tests

op partMatches "Whether a part is what the case expects: exact bits (tolerance 0), within a tolerance, a NaN, a zero, an infinity, or anything"
  input expectedBits UInt64 copied
  input toleranceBits UInt64 copied
  input actual Float64 copied
  output Bool
  let yes Bool true
:begin
  when toleranceBits == 18444492273895866368 wantNan checkAny
:wantNan
  calc isNan = !(actual == actual)
  return isNan
:checkAny
  when toleranceBits == 18442240474082181121 wantAny checkZero
:wantAny
  return yes
:checkZero
  when toleranceBits == 18442240474082181122 wantZero checkInfinite
:wantZero
  calc isZero = actual == 0.0
  return isZero
:checkInfinite
  when toleranceBits == 18442240474082181123 wantInfinite checkExact
:wantInfinite
  calc isInfinite = isInfiniteOf(actual)
  return isInfinite
:checkExact
  calc actualBits = convert.float64BitsToUInt64(actual)
  when toleranceBits == 0 exact near
:exact
  calc same = actualBits == expectedBits
  return same
:near
  calc expected = convert.uint64BitsToFloat64(expectedBits)
  calc tolerance = convert.uint64BitsToFloat64(toleranceBits)
  calc difference = absoluteOf(actual - expected)
  calc close = difference <= tolerance
  return close

op hexWord "Read digits of lower-case hexadecimal text as a number"
  input base machine.Address copied
  input start Int64 copied
  input digits Int64 copied
  output UInt64
  effect use machine.memory
  uses memoryAccess
  let value UInt64 0 mut
  let at Int64 0 mut
  let sixteen Int64 16
:begin
  calc at := start
  calc stop = start + digits
  goto eachDigit
:eachDigit loop=while max=sixteen
  when at < stop digit finish
:digit in=eachDigit
  calc place = base + at
  calc letter = convert.byteToInt64(machine.loadByte(place))
  calc nibble = (letter & 15) + 9 * (letter >> 6)
  calc value := (value << 4) | convert.int64ToUInt64(nibble)
  calc at := at + 1
  goto eachDigit
:finish
  return value

op checkTable "Run the rows of a table on the function at an index: 0 when every row matches, else the number of the first row that does not (from 1)"
  input text String borrowed
  input count Int64 copied
  input index Int64 copied
  output Int64
  effect use machine.memory
  uses memoryAccess
  let row Int64 0 mut
  let limit Int64 100000
  let clean Int64 0
:begin
  calc base = machine.addressOfString(text)
  calc row := 0
  goto eachRow
:eachRow loop=while max=limit
  when row < count readRow allMatch
:readRow in=eachRow
  calc start = row * 128
  calc a = convert.uint64BitsToFloat64(hexWord(base, start, 16))
  calc b = convert.uint64BitsToFloat64(hexWord(base, start + 16, 16))
  calc c = convert.uint64BitsToFloat64(hexWord(base, start + 32, 16))
  calc d = convert.uint64BitsToFloat64(hexWord(base, start + 48, 16))
  result = callFunction(index, a, b, c, d)
  re = Complex.real(result)
  im = Complex.imag(result)
  calc realBits = hexWord(base, start + 64, 16)
  calc realTolerance = hexWord(base, start + 80, 16)
  calc imagBits = hexWord(base, start + 96, 16)
  calc imagTolerance = hexWord(base, start + 112, 16)
  calc realOk = partMatches(realBits, realTolerance, re)
  calc imagOk = partMatches(imagBits, imagTolerance, im)
  calc bothOk = realOk && imagOk
  when bothOk nextRow mismatch
:nextRow in=eachRow
  calc row := row + 1
  goto eachRow
:mismatch
  calc failedRow = row + 1
  return failedRow
:allMatch
  return clean

## @generated tests
op callFunction "The result of the wrapper at an index of the table, on the arguments of a row (a Complex of doubles; a real result is its real part)"
  input index Int64 copied
  input a Float64 copied
  input b Float64 copied
  input c Float64 copied
  input d Float64 copied
  output Complex
  effect use machine.memory
  uses memoryAccess
:begin
  when index == 0 call0 next1
:call0
  z0 = Complex.new(a, b)
  r0 = complexExponential(z0)
  return r0
:next1
  when index == 1 call1 next2
:call1
  z1 = Complex.new(a, b)
  r1 = complexLogarithm(z1)
  return r1
:next2
  when index == 2 call2 next3
:call2
  z2 = Complex.new(a, b)
  r2 = complexSquareRoot(z2)
  return r2
:next3
  when index == 3 call3 next4
:call3
  z3 = Complex.new(a, b)
  r3 = complexSine(z3)
  return r3
:next4
  when index == 4 call4 next5
:call4
  z4 = Complex.new(a, b)
  r4 = complexCosine(z4)
  return r4
:next5
  when index == 5 call5 next6
:call5
  z5 = Complex.new(a, b)
  r5 = complexTangent(z5)
  return r5
:next6
  when index == 6 call6 next7
:call6
  z6 = Complex.new(a, b)
  r6 = complexInverseSine(z6)
  return r6
:next7
  when index == 7 call7 next8
:call7
  z7 = Complex.new(a, b)
  r7 = complexInverseCosine(z7)
  return r7
:next8
  when index == 8 call8 next9
:call8
  z8 = Complex.new(a, b)
  r8 = complexInverseTangent(z8)
  return r8
:next9
  when index == 9 call9 next10
:call9
  z9 = Complex.new(a, b)
  r9 = complexHyperbolicSine(z9)
  return r9
:next10
  when index == 10 call10 next11
:call10
  z10 = Complex.new(a, b)
  r10 = complexHyperbolicCosine(z10)
  return r10
:next11
  when index == 11 call11 next12
:call11
  z11 = Complex.new(a, b)
  r11 = complexHyperbolicTangent(z11)
  return r11
:next12
  when index == 12 call12 next13
:call12
  z12 = Complex.new(a, b)
  r12 = complexInverseHyperbolicSine(z12)
  return r12
:next13
  when index == 13 call13 next14
:call13
  z13 = Complex.new(a, b)
  r13 = complexInverseHyperbolicCosine(z13)
  return r13
:next14
  when index == 14 call14 next15
:call14
  z14 = Complex.new(a, b)
  r14 = complexInverseHyperbolicTangent(z14)
  return r14
:next15
  when index == 15 call15 next16
:call15
  z15 = Complex.new(a, b)
  r15 = complexConjugate(z15)
  return r15
:next16
  when index == 16 call16 next17
:call16
  z16 = Complex.new(a, b)
  r16 = complexProjection(z16)
  return r16
:next17
  when index == 17 call17 next18
:call17
  z17 = Complex.new(a, b)
  r17 = complexMagnitude(z17)
  calc re17 = r17 * 1.0
  out17 = Complex.new(re17, 0.0)
  return out17
:next18
  when index == 18 call18 next19
:call18
  z18 = Complex.new(a, b)
  r18 = complexArgument(z18)
  calc re18 = r18 * 1.0
  out18 = Complex.new(re18, 0.0)
  return out18
:next19
  when index == 19 call19 next20
:call19
  z19 = Complex.new(a, b)
  r19 = complexRealPart(z19)
  calc re19 = r19 * 1.0
  out19 = Complex.new(re19, 0.0)
  return out19
:next20
  when index == 20 call20 next21
:call20
  z20 = Complex.new(a, b)
  r20 = complexImaginaryPart(z20)
  calc re20 = r20 * 1.0
  out20 = Complex.new(re20, 0.0)
  return out20
:next21
  when index == 21 call21 next22
:call21
  z21 = Complex.new(a, b)
  w21 = Complex.new(c, d)
  r21 = complexPower(z21, w21)
  return r21
:next22
  when index == 22 call22 next23
:call22
  calc a22 = convert.float64ToFloat32(a)
  calc b22 = convert.float64ToFloat32(b)
  calc c22 = convert.float64ToFloat32(c)
  calc d22 = convert.float64ToFloat32(d)
  z22 = ComplexSingle.new(a22, b22)
  r22 = complexExponentialSingle(z22)
  rr22 = ComplexSingle.real(r22)
  ri22 = ComplexSingle.imag(r22)
  calc re22 = convert.float32ToFloat64(rr22)
  calc im22 = convert.float32ToFloat64(ri22)
  out22 = Complex.new(re22, im22)
  return out22
:next23
  when index == 23 call23 next24
:call23
  calc a23 = convert.float64ToFloat32(a)
  calc b23 = convert.float64ToFloat32(b)
  calc c23 = convert.float64ToFloat32(c)
  calc d23 = convert.float64ToFloat32(d)
  z23 = ComplexSingle.new(a23, b23)
  r23 = complexLogarithmSingle(z23)
  rr23 = ComplexSingle.real(r23)
  ri23 = ComplexSingle.imag(r23)
  calc re23 = convert.float32ToFloat64(rr23)
  calc im23 = convert.float32ToFloat64(ri23)
  out23 = Complex.new(re23, im23)
  return out23
:next24
  when index == 24 call24 next25
:call24
  calc a24 = convert.float64ToFloat32(a)
  calc b24 = convert.float64ToFloat32(b)
  calc c24 = convert.float64ToFloat32(c)
  calc d24 = convert.float64ToFloat32(d)
  z24 = ComplexSingle.new(a24, b24)
  r24 = complexSquareRootSingle(z24)
  rr24 = ComplexSingle.real(r24)
  ri24 = ComplexSingle.imag(r24)
  calc re24 = convert.float32ToFloat64(rr24)
  calc im24 = convert.float32ToFloat64(ri24)
  out24 = Complex.new(re24, im24)
  return out24
:next25
  when index == 25 call25 next26
:call25
  calc a25 = convert.float64ToFloat32(a)
  calc b25 = convert.float64ToFloat32(b)
  calc c25 = convert.float64ToFloat32(c)
  calc d25 = convert.float64ToFloat32(d)
  z25 = ComplexSingle.new(a25, b25)
  r25 = complexSineSingle(z25)
  rr25 = ComplexSingle.real(r25)
  ri25 = ComplexSingle.imag(r25)
  calc re25 = convert.float32ToFloat64(rr25)
  calc im25 = convert.float32ToFloat64(ri25)
  out25 = Complex.new(re25, im25)
  return out25
:next26
  when index == 26 call26 next27
:call26
  calc a26 = convert.float64ToFloat32(a)
  calc b26 = convert.float64ToFloat32(b)
  calc c26 = convert.float64ToFloat32(c)
  calc d26 = convert.float64ToFloat32(d)
  z26 = ComplexSingle.new(a26, b26)
  r26 = complexCosineSingle(z26)
  rr26 = ComplexSingle.real(r26)
  ri26 = ComplexSingle.imag(r26)
  calc re26 = convert.float32ToFloat64(rr26)
  calc im26 = convert.float32ToFloat64(ri26)
  out26 = Complex.new(re26, im26)
  return out26
:next27
  when index == 27 call27 next28
:call27
  calc a27 = convert.float64ToFloat32(a)
  calc b27 = convert.float64ToFloat32(b)
  calc c27 = convert.float64ToFloat32(c)
  calc d27 = convert.float64ToFloat32(d)
  z27 = ComplexSingle.new(a27, b27)
  r27 = complexTangentSingle(z27)
  rr27 = ComplexSingle.real(r27)
  ri27 = ComplexSingle.imag(r27)
  calc re27 = convert.float32ToFloat64(rr27)
  calc im27 = convert.float32ToFloat64(ri27)
  out27 = Complex.new(re27, im27)
  return out27
:next28
  when index == 28 call28 next29
:call28
  calc a28 = convert.float64ToFloat32(a)
  calc b28 = convert.float64ToFloat32(b)
  calc c28 = convert.float64ToFloat32(c)
  calc d28 = convert.float64ToFloat32(d)
  z28 = ComplexSingle.new(a28, b28)
  r28 = complexInverseSineSingle(z28)
  rr28 = ComplexSingle.real(r28)
  ri28 = ComplexSingle.imag(r28)
  calc re28 = convert.float32ToFloat64(rr28)
  calc im28 = convert.float32ToFloat64(ri28)
  out28 = Complex.new(re28, im28)
  return out28
:next29
  when index == 29 call29 next30
:call29
  calc a29 = convert.float64ToFloat32(a)
  calc b29 = convert.float64ToFloat32(b)
  calc c29 = convert.float64ToFloat32(c)
  calc d29 = convert.float64ToFloat32(d)
  z29 = ComplexSingle.new(a29, b29)
  r29 = complexInverseCosineSingle(z29)
  rr29 = ComplexSingle.real(r29)
  ri29 = ComplexSingle.imag(r29)
  calc re29 = convert.float32ToFloat64(rr29)
  calc im29 = convert.float32ToFloat64(ri29)
  out29 = Complex.new(re29, im29)
  return out29
:next30
  when index == 30 call30 next31
:call30
  calc a30 = convert.float64ToFloat32(a)
  calc b30 = convert.float64ToFloat32(b)
  calc c30 = convert.float64ToFloat32(c)
  calc d30 = convert.float64ToFloat32(d)
  z30 = ComplexSingle.new(a30, b30)
  r30 = complexInverseTangentSingle(z30)
  rr30 = ComplexSingle.real(r30)
  ri30 = ComplexSingle.imag(r30)
  calc re30 = convert.float32ToFloat64(rr30)
  calc im30 = convert.float32ToFloat64(ri30)
  out30 = Complex.new(re30, im30)
  return out30
:next31
  when index == 31 call31 next32
:call31
  calc a31 = convert.float64ToFloat32(a)
  calc b31 = convert.float64ToFloat32(b)
  calc c31 = convert.float64ToFloat32(c)
  calc d31 = convert.float64ToFloat32(d)
  z31 = ComplexSingle.new(a31, b31)
  r31 = complexHyperbolicSineSingle(z31)
  rr31 = ComplexSingle.real(r31)
  ri31 = ComplexSingle.imag(r31)
  calc re31 = convert.float32ToFloat64(rr31)
  calc im31 = convert.float32ToFloat64(ri31)
  out31 = Complex.new(re31, im31)
  return out31
:next32
  when index == 32 call32 next33
:call32
  calc a32 = convert.float64ToFloat32(a)
  calc b32 = convert.float64ToFloat32(b)
  calc c32 = convert.float64ToFloat32(c)
  calc d32 = convert.float64ToFloat32(d)
  z32 = ComplexSingle.new(a32, b32)
  r32 = complexHyperbolicCosineSingle(z32)
  rr32 = ComplexSingle.real(r32)
  ri32 = ComplexSingle.imag(r32)
  calc re32 = convert.float32ToFloat64(rr32)
  calc im32 = convert.float32ToFloat64(ri32)
  out32 = Complex.new(re32, im32)
  return out32
:next33
  when index == 33 call33 next34
:call33
  calc a33 = convert.float64ToFloat32(a)
  calc b33 = convert.float64ToFloat32(b)
  calc c33 = convert.float64ToFloat32(c)
  calc d33 = convert.float64ToFloat32(d)
  z33 = ComplexSingle.new(a33, b33)
  r33 = complexHyperbolicTangentSingle(z33)
  rr33 = ComplexSingle.real(r33)
  ri33 = ComplexSingle.imag(r33)
  calc re33 = convert.float32ToFloat64(rr33)
  calc im33 = convert.float32ToFloat64(ri33)
  out33 = Complex.new(re33, im33)
  return out33
:next34
  when index == 34 call34 next35
:call34
  calc a34 = convert.float64ToFloat32(a)
  calc b34 = convert.float64ToFloat32(b)
  calc c34 = convert.float64ToFloat32(c)
  calc d34 = convert.float64ToFloat32(d)
  z34 = ComplexSingle.new(a34, b34)
  r34 = complexInverseHyperbolicSineSingle(z34)
  rr34 = ComplexSingle.real(r34)
  ri34 = ComplexSingle.imag(r34)
  calc re34 = convert.float32ToFloat64(rr34)
  calc im34 = convert.float32ToFloat64(ri34)
  out34 = Complex.new(re34, im34)
  return out34
:next35
  when index == 35 call35 next36
:call35
  calc a35 = convert.float64ToFloat32(a)
  calc b35 = convert.float64ToFloat32(b)
  calc c35 = convert.float64ToFloat32(c)
  calc d35 = convert.float64ToFloat32(d)
  z35 = ComplexSingle.new(a35, b35)
  r35 = complexInverseHyperbolicCosineSingle(z35)
  rr35 = ComplexSingle.real(r35)
  ri35 = ComplexSingle.imag(r35)
  calc re35 = convert.float32ToFloat64(rr35)
  calc im35 = convert.float32ToFloat64(ri35)
  out35 = Complex.new(re35, im35)
  return out35
:next36
  when index == 36 call36 next37
:call36
  calc a36 = convert.float64ToFloat32(a)
  calc b36 = convert.float64ToFloat32(b)
  calc c36 = convert.float64ToFloat32(c)
  calc d36 = convert.float64ToFloat32(d)
  z36 = ComplexSingle.new(a36, b36)
  r36 = complexInverseHyperbolicTangentSingle(z36)
  rr36 = ComplexSingle.real(r36)
  ri36 = ComplexSingle.imag(r36)
  calc re36 = convert.float32ToFloat64(rr36)
  calc im36 = convert.float32ToFloat64(ri36)
  out36 = Complex.new(re36, im36)
  return out36
:next37
  when index == 37 call37 next38
:call37
  calc a37 = convert.float64ToFloat32(a)
  calc b37 = convert.float64ToFloat32(b)
  calc c37 = convert.float64ToFloat32(c)
  calc d37 = convert.float64ToFloat32(d)
  z37 = ComplexSingle.new(a37, b37)
  r37 = complexConjugateSingle(z37)
  rr37 = ComplexSingle.real(r37)
  ri37 = ComplexSingle.imag(r37)
  calc re37 = convert.float32ToFloat64(rr37)
  calc im37 = convert.float32ToFloat64(ri37)
  out37 = Complex.new(re37, im37)
  return out37
:next38
  when index == 38 call38 next39
:call38
  calc a38 = convert.float64ToFloat32(a)
  calc b38 = convert.float64ToFloat32(b)
  calc c38 = convert.float64ToFloat32(c)
  calc d38 = convert.float64ToFloat32(d)
  z38 = ComplexSingle.new(a38, b38)
  r38 = complexProjectionSingle(z38)
  rr38 = ComplexSingle.real(r38)
  ri38 = ComplexSingle.imag(r38)
  calc re38 = convert.float32ToFloat64(rr38)
  calc im38 = convert.float32ToFloat64(ri38)
  out38 = Complex.new(re38, im38)
  return out38
:next39
  when index == 39 call39 next40
:call39
  calc a39 = convert.float64ToFloat32(a)
  calc b39 = convert.float64ToFloat32(b)
  calc c39 = convert.float64ToFloat32(c)
  calc d39 = convert.float64ToFloat32(d)
  z39 = ComplexSingle.new(a39, b39)
  r39 = complexMagnitudeSingle(z39)
  calc re39 = convert.float32ToFloat64(r39)
  out39 = Complex.new(re39, 0.0)
  return out39
:next40
  when index == 40 call40 next41
:call40
  calc a40 = convert.float64ToFloat32(a)
  calc b40 = convert.float64ToFloat32(b)
  calc c40 = convert.float64ToFloat32(c)
  calc d40 = convert.float64ToFloat32(d)
  z40 = ComplexSingle.new(a40, b40)
  r40 = complexArgumentSingle(z40)
  calc re40 = convert.float32ToFloat64(r40)
  out40 = Complex.new(re40, 0.0)
  return out40
:next41
  when index == 41 call41 next42
:call41
  calc a41 = convert.float64ToFloat32(a)
  calc b41 = convert.float64ToFloat32(b)
  calc c41 = convert.float64ToFloat32(c)
  calc d41 = convert.float64ToFloat32(d)
  z41 = ComplexSingle.new(a41, b41)
  r41 = complexRealPartSingle(z41)
  calc re41 = convert.float32ToFloat64(r41)
  out41 = Complex.new(re41, 0.0)
  return out41
:next42
  when index == 42 call42 next43
:call42
  calc a42 = convert.float64ToFloat32(a)
  calc b42 = convert.float64ToFloat32(b)
  calc c42 = convert.float64ToFloat32(c)
  calc d42 = convert.float64ToFloat32(d)
  z42 = ComplexSingle.new(a42, b42)
  r42 = complexImaginaryPartSingle(z42)
  calc re42 = convert.float32ToFloat64(r42)
  out42 = Complex.new(re42, 0.0)
  return out42
:next43
  when index == 43 call43 call43
:call43
  calc a43 = convert.float64ToFloat32(a)
  calc b43 = convert.float64ToFloat32(b)
  calc c43 = convert.float64ToFloat32(c)
  calc d43 = convert.float64ToFloat32(d)
  z43 = ComplexSingle.new(a43, b43)
  w43 = ComplexSingle.new(c43, d43)
  r43 = complexPowerSingle(z43, w43)
  rr43 = ComplexSingle.real(r43)
  ri43 = ComplexSingle.imag(r43)
  calc re43 = convert.float32ToFloat64(rr43)
  calc im43 = convert.float32ToFloat64(ri43)
  out43 = Complex.new(re43, im43)
  return out43

op sameBits "Whether two doubles have the same bits"
  input left Float64 copied
  input right Float64 copied
  output Bool
:begin
  calc leftBits = convert.float64BitsToUInt64(left)
  calc rightBits = convert.float64BitsToUInt64(right)
  calc same = leftBits == rightBits
  return same

op sameComplex "Whether two complex numbers have the same bits in both parts"
  input left Complex copied
  input right Complex copied
  output Bool
:begin
  leftRe = Complex.real(left)
  leftIm = Complex.imag(left)
  rightRe = Complex.real(right)
  rightIm = Complex.imag(right)
  realSame = sameBits(leftRe, rightRe)
  imagSame = sameBits(leftIm, rightIm)
  calc both = realSame && imagSame
  return both

test longFormsTest "the long double complex functions (cabsl to catanhl), which are the double ones on Windows, give the double functions' bits on ordinary points, infinities, NaNs, and signed zeros"
  verifies complexExponentialLong givesCexpl
  verifies complexLogarithmLong givesClogl
  verifies complexSquareRootLong givesCsqrtl
  verifies complexSineLong givesCsinl
  verifies complexCosineLong givesCcosl
  verifies complexTangentLong givesCtanl
  verifies complexInverseSineLong givesCasinl
  verifies complexInverseCosineLong givesCacosl
  verifies complexInverseTangentLong givesCatanl
  verifies complexHyperbolicSineLong givesCsinhl
  verifies complexHyperbolicCosineLong givesCcoshl
  verifies complexHyperbolicTangentLong givesCtanhl
  verifies complexInverseHyperbolicSineLong givesCasinhl
  verifies complexInverseHyperbolicCosineLong givesCacoshl
  verifies complexInverseHyperbolicTangentLong givesCatanhl
  verifies complexConjugateLong givesConjl
  verifies complexProjectionLong givesCprojl
  verifies complexMagnitudeLong givesCabsl
  verifies complexArgumentLong givesCargl
  verifies complexRealPartLong givesCreall
  verifies complexImaginaryPartLong givesCimagl
  verifies complexPowerLong givesCpowl
  effect use machine.memory
  uses memoryAccess
:begin
  calc za1 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb1 = convert.uint64BitsToFloat64(13826050856027422720)
  z1 = Complex.new(za1, zb1)
  d1 = complexExponential(z1)
  l1 = complexExponentialLong(z1)
  s1 = sameComplex(d1, l1)
  expect1: test.assertTrue(s1)
  calc za2 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb2 = convert.uint64BitsToFloat64(4613937818241073152)
  z2 = Complex.new(za2, zb2)
  d2 = complexExponential(z2)
  l2 = complexExponentialLong(z2)
  s2 = sameComplex(d2, l2)
  expect2: test.assertTrue(s2)
  calc za3 = convert.uint64BitsToFloat64(0)
  calc zb3 = convert.uint64BitsToFloat64(4607182418800017408)
  z3 = Complex.new(za3, zb3)
  d3 = complexExponential(z3)
  l3 = complexExponentialLong(z3)
  s3 = sameComplex(d3, l3)
  expect3: test.assertTrue(s3)
  calc za4 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb4 = convert.uint64BitsToFloat64(18318360957983683996)
  z4 = Complex.new(za4, zb4)
  d4 = complexExponential(z4)
  l4 = complexExponentialLong(z4)
  s4 = sameComplex(d4, l4)
  expect4: test.assertTrue(s4)
  calc za5 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb5 = convert.uint64BitsToFloat64(9221120237041090560)
  z5 = Complex.new(za5, zb5)
  d5 = complexExponential(z5)
  l5 = complexExponentialLong(z5)
  s5 = sameComplex(d5, l5)
  expect5: test.assertTrue(s5)
  calc za6 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb6 = convert.uint64BitsToFloat64(0)
  z6 = Complex.new(za6, zb6)
  d6 = complexExponential(z6)
  l6 = complexExponentialLong(z6)
  s6 = sameComplex(d6, l6)
  expect6: test.assertTrue(s6)
  calc za7 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb7 = convert.uint64BitsToFloat64(9223372036854775808)
  z7 = Complex.new(za7, zb7)
  d7 = complexExponential(z7)
  l7 = complexExponentialLong(z7)
  s7 = sameComplex(d7, l7)
  expect7: test.assertTrue(s7)
  calc za8 = convert.uint64BitsToFloat64(0)
  calc zb8 = convert.uint64BitsToFloat64(9223372036854775808)
  z8 = Complex.new(za8, zb8)
  d8 = complexExponential(z8)
  l8 = complexExponentialLong(z8)
  s8 = sameComplex(d8, l8)
  expect8: test.assertTrue(s8)
  calc za9 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb9 = convert.uint64BitsToFloat64(4611686018427387904)
  z9 = Complex.new(za9, zb9)
  d9 = complexExponential(z9)
  l9 = complexExponentialLong(z9)
  s9 = sameComplex(d9, l9)
  expect9: test.assertTrue(s9)
  calc za10 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb10 = convert.uint64BitsToFloat64(13826050856027422720)
  z10 = Complex.new(za10, zb10)
  d10 = complexLogarithm(z10)
  l10 = complexLogarithmLong(z10)
  s10 = sameComplex(d10, l10)
  expect10: test.assertTrue(s10)
  calc za11 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb11 = convert.uint64BitsToFloat64(4613937818241073152)
  z11 = Complex.new(za11, zb11)
  d11 = complexLogarithm(z11)
  l11 = complexLogarithmLong(z11)
  s11 = sameComplex(d11, l11)
  expect11: test.assertTrue(s11)
  calc za12 = convert.uint64BitsToFloat64(0)
  calc zb12 = convert.uint64BitsToFloat64(4607182418800017408)
  z12 = Complex.new(za12, zb12)
  d12 = complexLogarithm(z12)
  l12 = complexLogarithmLong(z12)
  s12 = sameComplex(d12, l12)
  expect12: test.assertTrue(s12)
  calc za13 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb13 = convert.uint64BitsToFloat64(18318360957983683996)
  z13 = Complex.new(za13, zb13)
  d13 = complexLogarithm(z13)
  l13 = complexLogarithmLong(z13)
  s13 = sameComplex(d13, l13)
  expect13: test.assertTrue(s13)
  calc za14 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb14 = convert.uint64BitsToFloat64(9221120237041090560)
  z14 = Complex.new(za14, zb14)
  d14 = complexLogarithm(z14)
  l14 = complexLogarithmLong(z14)
  s14 = sameComplex(d14, l14)
  expect14: test.assertTrue(s14)
  calc za15 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb15 = convert.uint64BitsToFloat64(0)
  z15 = Complex.new(za15, zb15)
  d15 = complexLogarithm(z15)
  l15 = complexLogarithmLong(z15)
  s15 = sameComplex(d15, l15)
  expect15: test.assertTrue(s15)
  calc za16 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb16 = convert.uint64BitsToFloat64(9223372036854775808)
  z16 = Complex.new(za16, zb16)
  d16 = complexLogarithm(z16)
  l16 = complexLogarithmLong(z16)
  s16 = sameComplex(d16, l16)
  expect16: test.assertTrue(s16)
  calc za17 = convert.uint64BitsToFloat64(0)
  calc zb17 = convert.uint64BitsToFloat64(9223372036854775808)
  z17 = Complex.new(za17, zb17)
  d17 = complexLogarithm(z17)
  l17 = complexLogarithmLong(z17)
  s17 = sameComplex(d17, l17)
  expect17: test.assertTrue(s17)
  calc za18 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb18 = convert.uint64BitsToFloat64(4611686018427387904)
  z18 = Complex.new(za18, zb18)
  d18 = complexLogarithm(z18)
  l18 = complexLogarithmLong(z18)
  s18 = sameComplex(d18, l18)
  expect18: test.assertTrue(s18)
  calc za19 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb19 = convert.uint64BitsToFloat64(13826050856027422720)
  z19 = Complex.new(za19, zb19)
  d19 = complexSquareRoot(z19)
  l19 = complexSquareRootLong(z19)
  s19 = sameComplex(d19, l19)
  expect19: test.assertTrue(s19)
  calc za20 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb20 = convert.uint64BitsToFloat64(4613937818241073152)
  z20 = Complex.new(za20, zb20)
  d20 = complexSquareRoot(z20)
  l20 = complexSquareRootLong(z20)
  s20 = sameComplex(d20, l20)
  expect20: test.assertTrue(s20)
  calc za21 = convert.uint64BitsToFloat64(0)
  calc zb21 = convert.uint64BitsToFloat64(4607182418800017408)
  z21 = Complex.new(za21, zb21)
  d21 = complexSquareRoot(z21)
  l21 = complexSquareRootLong(z21)
  s21 = sameComplex(d21, l21)
  expect21: test.assertTrue(s21)
  calc za22 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb22 = convert.uint64BitsToFloat64(18318360957983683996)
  z22 = Complex.new(za22, zb22)
  d22 = complexSquareRoot(z22)
  l22 = complexSquareRootLong(z22)
  s22 = sameComplex(d22, l22)
  expect22: test.assertTrue(s22)
  calc za23 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb23 = convert.uint64BitsToFloat64(9221120237041090560)
  z23 = Complex.new(za23, zb23)
  d23 = complexSquareRoot(z23)
  l23 = complexSquareRootLong(z23)
  s23 = sameComplex(d23, l23)
  expect23: test.assertTrue(s23)
  calc za24 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb24 = convert.uint64BitsToFloat64(0)
  z24 = Complex.new(za24, zb24)
  d24 = complexSquareRoot(z24)
  l24 = complexSquareRootLong(z24)
  s24 = sameComplex(d24, l24)
  expect24: test.assertTrue(s24)
  calc za25 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb25 = convert.uint64BitsToFloat64(9223372036854775808)
  z25 = Complex.new(za25, zb25)
  d25 = complexSquareRoot(z25)
  l25 = complexSquareRootLong(z25)
  s25 = sameComplex(d25, l25)
  expect25: test.assertTrue(s25)
  calc za26 = convert.uint64BitsToFloat64(0)
  calc zb26 = convert.uint64BitsToFloat64(9223372036854775808)
  z26 = Complex.new(za26, zb26)
  d26 = complexSquareRoot(z26)
  l26 = complexSquareRootLong(z26)
  s26 = sameComplex(d26, l26)
  expect26: test.assertTrue(s26)
  calc za27 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb27 = convert.uint64BitsToFloat64(4611686018427387904)
  z27 = Complex.new(za27, zb27)
  d27 = complexSquareRoot(z27)
  l27 = complexSquareRootLong(z27)
  s27 = sameComplex(d27, l27)
  expect27: test.assertTrue(s27)
  calc za28 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb28 = convert.uint64BitsToFloat64(13826050856027422720)
  z28 = Complex.new(za28, zb28)
  d28 = complexSine(z28)
  l28 = complexSineLong(z28)
  s28 = sameComplex(d28, l28)
  expect28: test.assertTrue(s28)
  calc za29 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb29 = convert.uint64BitsToFloat64(4613937818241073152)
  z29 = Complex.new(za29, zb29)
  d29 = complexSine(z29)
  l29 = complexSineLong(z29)
  s29 = sameComplex(d29, l29)
  expect29: test.assertTrue(s29)
  calc za30 = convert.uint64BitsToFloat64(0)
  calc zb30 = convert.uint64BitsToFloat64(4607182418800017408)
  z30 = Complex.new(za30, zb30)
  d30 = complexSine(z30)
  l30 = complexSineLong(z30)
  s30 = sameComplex(d30, l30)
  expect30: test.assertTrue(s30)
  calc za31 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb31 = convert.uint64BitsToFloat64(18318360957983683996)
  z31 = Complex.new(za31, zb31)
  d31 = complexSine(z31)
  l31 = complexSineLong(z31)
  s31 = sameComplex(d31, l31)
  expect31: test.assertTrue(s31)
  calc za32 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb32 = convert.uint64BitsToFloat64(9221120237041090560)
  z32 = Complex.new(za32, zb32)
  d32 = complexSine(z32)
  l32 = complexSineLong(z32)
  s32 = sameComplex(d32, l32)
  expect32: test.assertTrue(s32)
  calc za33 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb33 = convert.uint64BitsToFloat64(0)
  z33 = Complex.new(za33, zb33)
  d33 = complexSine(z33)
  l33 = complexSineLong(z33)
  s33 = sameComplex(d33, l33)
  expect33: test.assertTrue(s33)
  calc za34 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb34 = convert.uint64BitsToFloat64(9223372036854775808)
  z34 = Complex.new(za34, zb34)
  d34 = complexSine(z34)
  l34 = complexSineLong(z34)
  s34 = sameComplex(d34, l34)
  expect34: test.assertTrue(s34)
  calc za35 = convert.uint64BitsToFloat64(0)
  calc zb35 = convert.uint64BitsToFloat64(9223372036854775808)
  z35 = Complex.new(za35, zb35)
  d35 = complexSine(z35)
  l35 = complexSineLong(z35)
  s35 = sameComplex(d35, l35)
  expect35: test.assertTrue(s35)
  calc za36 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb36 = convert.uint64BitsToFloat64(4611686018427387904)
  z36 = Complex.new(za36, zb36)
  d36 = complexSine(z36)
  l36 = complexSineLong(z36)
  s36 = sameComplex(d36, l36)
  expect36: test.assertTrue(s36)
  calc za37 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb37 = convert.uint64BitsToFloat64(13826050856027422720)
  z37 = Complex.new(za37, zb37)
  d37 = complexCosine(z37)
  l37 = complexCosineLong(z37)
  s37 = sameComplex(d37, l37)
  expect37: test.assertTrue(s37)
  calc za38 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb38 = convert.uint64BitsToFloat64(4613937818241073152)
  z38 = Complex.new(za38, zb38)
  d38 = complexCosine(z38)
  l38 = complexCosineLong(z38)
  s38 = sameComplex(d38, l38)
  expect38: test.assertTrue(s38)
  calc za39 = convert.uint64BitsToFloat64(0)
  calc zb39 = convert.uint64BitsToFloat64(4607182418800017408)
  z39 = Complex.new(za39, zb39)
  d39 = complexCosine(z39)
  l39 = complexCosineLong(z39)
  s39 = sameComplex(d39, l39)
  expect39: test.assertTrue(s39)
  calc za40 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb40 = convert.uint64BitsToFloat64(18318360957983683996)
  z40 = Complex.new(za40, zb40)
  d40 = complexCosine(z40)
  l40 = complexCosineLong(z40)
  s40 = sameComplex(d40, l40)
  expect40: test.assertTrue(s40)
  calc za41 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb41 = convert.uint64BitsToFloat64(9221120237041090560)
  z41 = Complex.new(za41, zb41)
  d41 = complexCosine(z41)
  l41 = complexCosineLong(z41)
  s41 = sameComplex(d41, l41)
  expect41: test.assertTrue(s41)
  calc za42 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb42 = convert.uint64BitsToFloat64(0)
  z42 = Complex.new(za42, zb42)
  d42 = complexCosine(z42)
  l42 = complexCosineLong(z42)
  s42 = sameComplex(d42, l42)
  expect42: test.assertTrue(s42)
  calc za43 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb43 = convert.uint64BitsToFloat64(9223372036854775808)
  z43 = Complex.new(za43, zb43)
  d43 = complexCosine(z43)
  l43 = complexCosineLong(z43)
  s43 = sameComplex(d43, l43)
  expect43: test.assertTrue(s43)
  calc za44 = convert.uint64BitsToFloat64(0)
  calc zb44 = convert.uint64BitsToFloat64(9223372036854775808)
  z44 = Complex.new(za44, zb44)
  d44 = complexCosine(z44)
  l44 = complexCosineLong(z44)
  s44 = sameComplex(d44, l44)
  expect44: test.assertTrue(s44)
  calc za45 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb45 = convert.uint64BitsToFloat64(4611686018427387904)
  z45 = Complex.new(za45, zb45)
  d45 = complexCosine(z45)
  l45 = complexCosineLong(z45)
  s45 = sameComplex(d45, l45)
  expect45: test.assertTrue(s45)
  calc za46 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb46 = convert.uint64BitsToFloat64(13826050856027422720)
  z46 = Complex.new(za46, zb46)
  d46 = complexTangent(z46)
  l46 = complexTangentLong(z46)
  s46 = sameComplex(d46, l46)
  expect46: test.assertTrue(s46)
  calc za47 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb47 = convert.uint64BitsToFloat64(4613937818241073152)
  z47 = Complex.new(za47, zb47)
  d47 = complexTangent(z47)
  l47 = complexTangentLong(z47)
  s47 = sameComplex(d47, l47)
  expect47: test.assertTrue(s47)
  calc za48 = convert.uint64BitsToFloat64(0)
  calc zb48 = convert.uint64BitsToFloat64(4607182418800017408)
  z48 = Complex.new(za48, zb48)
  d48 = complexTangent(z48)
  l48 = complexTangentLong(z48)
  s48 = sameComplex(d48, l48)
  expect48: test.assertTrue(s48)
  calc za49 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb49 = convert.uint64BitsToFloat64(18318360957983683996)
  z49 = Complex.new(za49, zb49)
  d49 = complexTangent(z49)
  l49 = complexTangentLong(z49)
  s49 = sameComplex(d49, l49)
  expect49: test.assertTrue(s49)
  calc za50 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb50 = convert.uint64BitsToFloat64(9221120237041090560)
  z50 = Complex.new(za50, zb50)
  d50 = complexTangent(z50)
  l50 = complexTangentLong(z50)
  s50 = sameComplex(d50, l50)
  expect50: test.assertTrue(s50)
  calc za51 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb51 = convert.uint64BitsToFloat64(0)
  z51 = Complex.new(za51, zb51)
  d51 = complexTangent(z51)
  l51 = complexTangentLong(z51)
  s51 = sameComplex(d51, l51)
  expect51: test.assertTrue(s51)
  calc za52 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb52 = convert.uint64BitsToFloat64(9223372036854775808)
  z52 = Complex.new(za52, zb52)
  d52 = complexTangent(z52)
  l52 = complexTangentLong(z52)
  s52 = sameComplex(d52, l52)
  expect52: test.assertTrue(s52)
  calc za53 = convert.uint64BitsToFloat64(0)
  calc zb53 = convert.uint64BitsToFloat64(9223372036854775808)
  z53 = Complex.new(za53, zb53)
  d53 = complexTangent(z53)
  l53 = complexTangentLong(z53)
  s53 = sameComplex(d53, l53)
  expect53: test.assertTrue(s53)
  calc za54 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb54 = convert.uint64BitsToFloat64(4611686018427387904)
  z54 = Complex.new(za54, zb54)
  d54 = complexTangent(z54)
  l54 = complexTangentLong(z54)
  s54 = sameComplex(d54, l54)
  expect54: test.assertTrue(s54)
  calc za55 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb55 = convert.uint64BitsToFloat64(13826050856027422720)
  z55 = Complex.new(za55, zb55)
  d55 = complexInverseSine(z55)
  l55 = complexInverseSineLong(z55)
  s55 = sameComplex(d55, l55)
  expect55: test.assertTrue(s55)
  calc za56 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb56 = convert.uint64BitsToFloat64(4613937818241073152)
  z56 = Complex.new(za56, zb56)
  d56 = complexInverseSine(z56)
  l56 = complexInverseSineLong(z56)
  s56 = sameComplex(d56, l56)
  expect56: test.assertTrue(s56)
  calc za57 = convert.uint64BitsToFloat64(0)
  calc zb57 = convert.uint64BitsToFloat64(4607182418800017408)
  z57 = Complex.new(za57, zb57)
  d57 = complexInverseSine(z57)
  l57 = complexInverseSineLong(z57)
  s57 = sameComplex(d57, l57)
  expect57: test.assertTrue(s57)
  calc za58 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb58 = convert.uint64BitsToFloat64(18318360957983683996)
  z58 = Complex.new(za58, zb58)
  d58 = complexInverseSine(z58)
  l58 = complexInverseSineLong(z58)
  s58 = sameComplex(d58, l58)
  expect58: test.assertTrue(s58)
  calc za59 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb59 = convert.uint64BitsToFloat64(9221120237041090560)
  z59 = Complex.new(za59, zb59)
  d59 = complexInverseSine(z59)
  l59 = complexInverseSineLong(z59)
  s59 = sameComplex(d59, l59)
  expect59: test.assertTrue(s59)
  calc za60 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb60 = convert.uint64BitsToFloat64(0)
  z60 = Complex.new(za60, zb60)
  d60 = complexInverseSine(z60)
  l60 = complexInverseSineLong(z60)
  s60 = sameComplex(d60, l60)
  expect60: test.assertTrue(s60)
  calc za61 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb61 = convert.uint64BitsToFloat64(9223372036854775808)
  z61 = Complex.new(za61, zb61)
  d61 = complexInverseSine(z61)
  l61 = complexInverseSineLong(z61)
  s61 = sameComplex(d61, l61)
  expect61: test.assertTrue(s61)
  calc za62 = convert.uint64BitsToFloat64(0)
  calc zb62 = convert.uint64BitsToFloat64(9223372036854775808)
  z62 = Complex.new(za62, zb62)
  d62 = complexInverseSine(z62)
  l62 = complexInverseSineLong(z62)
  s62 = sameComplex(d62, l62)
  expect62: test.assertTrue(s62)
  calc za63 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb63 = convert.uint64BitsToFloat64(4611686018427387904)
  z63 = Complex.new(za63, zb63)
  d63 = complexInverseSine(z63)
  l63 = complexInverseSineLong(z63)
  s63 = sameComplex(d63, l63)
  expect63: test.assertTrue(s63)
  calc za64 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb64 = convert.uint64BitsToFloat64(13826050856027422720)
  z64 = Complex.new(za64, zb64)
  d64 = complexInverseCosine(z64)
  l64 = complexInverseCosineLong(z64)
  s64 = sameComplex(d64, l64)
  expect64: test.assertTrue(s64)
  calc za65 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb65 = convert.uint64BitsToFloat64(4613937818241073152)
  z65 = Complex.new(za65, zb65)
  d65 = complexInverseCosine(z65)
  l65 = complexInverseCosineLong(z65)
  s65 = sameComplex(d65, l65)
  expect65: test.assertTrue(s65)
  calc za66 = convert.uint64BitsToFloat64(0)
  calc zb66 = convert.uint64BitsToFloat64(4607182418800017408)
  z66 = Complex.new(za66, zb66)
  d66 = complexInverseCosine(z66)
  l66 = complexInverseCosineLong(z66)
  s66 = sameComplex(d66, l66)
  expect66: test.assertTrue(s66)
  calc za67 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb67 = convert.uint64BitsToFloat64(18318360957983683996)
  z67 = Complex.new(za67, zb67)
  d67 = complexInverseCosine(z67)
  l67 = complexInverseCosineLong(z67)
  s67 = sameComplex(d67, l67)
  expect67: test.assertTrue(s67)
  calc za68 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb68 = convert.uint64BitsToFloat64(9221120237041090560)
  z68 = Complex.new(za68, zb68)
  d68 = complexInverseCosine(z68)
  l68 = complexInverseCosineLong(z68)
  s68 = sameComplex(d68, l68)
  expect68: test.assertTrue(s68)
  calc za69 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb69 = convert.uint64BitsToFloat64(0)
  z69 = Complex.new(za69, zb69)
  d69 = complexInverseCosine(z69)
  l69 = complexInverseCosineLong(z69)
  s69 = sameComplex(d69, l69)
  expect69: test.assertTrue(s69)
  calc za70 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb70 = convert.uint64BitsToFloat64(9223372036854775808)
  z70 = Complex.new(za70, zb70)
  d70 = complexInverseCosine(z70)
  l70 = complexInverseCosineLong(z70)
  s70 = sameComplex(d70, l70)
  expect70: test.assertTrue(s70)
  calc za71 = convert.uint64BitsToFloat64(0)
  calc zb71 = convert.uint64BitsToFloat64(9223372036854775808)
  z71 = Complex.new(za71, zb71)
  d71 = complexInverseCosine(z71)
  l71 = complexInverseCosineLong(z71)
  s71 = sameComplex(d71, l71)
  expect71: test.assertTrue(s71)
  calc za72 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb72 = convert.uint64BitsToFloat64(4611686018427387904)
  z72 = Complex.new(za72, zb72)
  d72 = complexInverseCosine(z72)
  l72 = complexInverseCosineLong(z72)
  s72 = sameComplex(d72, l72)
  expect72: test.assertTrue(s72)
  calc za73 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb73 = convert.uint64BitsToFloat64(13826050856027422720)
  z73 = Complex.new(za73, zb73)
  d73 = complexInverseTangent(z73)
  l73 = complexInverseTangentLong(z73)
  s73 = sameComplex(d73, l73)
  expect73: test.assertTrue(s73)
  calc za74 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb74 = convert.uint64BitsToFloat64(4613937818241073152)
  z74 = Complex.new(za74, zb74)
  d74 = complexInverseTangent(z74)
  l74 = complexInverseTangentLong(z74)
  s74 = sameComplex(d74, l74)
  expect74: test.assertTrue(s74)
  calc za75 = convert.uint64BitsToFloat64(0)
  calc zb75 = convert.uint64BitsToFloat64(4607182418800017408)
  z75 = Complex.new(za75, zb75)
  d75 = complexInverseTangent(z75)
  l75 = complexInverseTangentLong(z75)
  s75 = sameComplex(d75, l75)
  expect75: test.assertTrue(s75)
  calc za76 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb76 = convert.uint64BitsToFloat64(18318360957983683996)
  z76 = Complex.new(za76, zb76)
  d76 = complexInverseTangent(z76)
  l76 = complexInverseTangentLong(z76)
  s76 = sameComplex(d76, l76)
  expect76: test.assertTrue(s76)
  calc za77 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb77 = convert.uint64BitsToFloat64(9221120237041090560)
  z77 = Complex.new(za77, zb77)
  d77 = complexInverseTangent(z77)
  l77 = complexInverseTangentLong(z77)
  s77 = sameComplex(d77, l77)
  expect77: test.assertTrue(s77)
  calc za78 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb78 = convert.uint64BitsToFloat64(0)
  z78 = Complex.new(za78, zb78)
  d78 = complexInverseTangent(z78)
  l78 = complexInverseTangentLong(z78)
  s78 = sameComplex(d78, l78)
  expect78: test.assertTrue(s78)
  calc za79 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb79 = convert.uint64BitsToFloat64(9223372036854775808)
  z79 = Complex.new(za79, zb79)
  d79 = complexInverseTangent(z79)
  l79 = complexInverseTangentLong(z79)
  s79 = sameComplex(d79, l79)
  expect79: test.assertTrue(s79)
  calc za80 = convert.uint64BitsToFloat64(0)
  calc zb80 = convert.uint64BitsToFloat64(9223372036854775808)
  z80 = Complex.new(za80, zb80)
  d80 = complexInverseTangent(z80)
  l80 = complexInverseTangentLong(z80)
  s80 = sameComplex(d80, l80)
  expect80: test.assertTrue(s80)
  calc za81 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb81 = convert.uint64BitsToFloat64(4611686018427387904)
  z81 = Complex.new(za81, zb81)
  d81 = complexInverseTangent(z81)
  l81 = complexInverseTangentLong(z81)
  s81 = sameComplex(d81, l81)
  expect81: test.assertTrue(s81)
  calc za82 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb82 = convert.uint64BitsToFloat64(13826050856027422720)
  z82 = Complex.new(za82, zb82)
  d82 = complexHyperbolicSine(z82)
  l82 = complexHyperbolicSineLong(z82)
  s82 = sameComplex(d82, l82)
  expect82: test.assertTrue(s82)
  calc za83 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb83 = convert.uint64BitsToFloat64(4613937818241073152)
  z83 = Complex.new(za83, zb83)
  d83 = complexHyperbolicSine(z83)
  l83 = complexHyperbolicSineLong(z83)
  s83 = sameComplex(d83, l83)
  expect83: test.assertTrue(s83)
  calc za84 = convert.uint64BitsToFloat64(0)
  calc zb84 = convert.uint64BitsToFloat64(4607182418800017408)
  z84 = Complex.new(za84, zb84)
  d84 = complexHyperbolicSine(z84)
  l84 = complexHyperbolicSineLong(z84)
  s84 = sameComplex(d84, l84)
  expect84: test.assertTrue(s84)
  calc za85 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb85 = convert.uint64BitsToFloat64(18318360957983683996)
  z85 = Complex.new(za85, zb85)
  d85 = complexHyperbolicSine(z85)
  l85 = complexHyperbolicSineLong(z85)
  s85 = sameComplex(d85, l85)
  expect85: test.assertTrue(s85)
  calc za86 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb86 = convert.uint64BitsToFloat64(9221120237041090560)
  z86 = Complex.new(za86, zb86)
  d86 = complexHyperbolicSine(z86)
  l86 = complexHyperbolicSineLong(z86)
  s86 = sameComplex(d86, l86)
  expect86: test.assertTrue(s86)
  calc za87 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb87 = convert.uint64BitsToFloat64(0)
  z87 = Complex.new(za87, zb87)
  d87 = complexHyperbolicSine(z87)
  l87 = complexHyperbolicSineLong(z87)
  s87 = sameComplex(d87, l87)
  expect87: test.assertTrue(s87)
  calc za88 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb88 = convert.uint64BitsToFloat64(9223372036854775808)
  z88 = Complex.new(za88, zb88)
  d88 = complexHyperbolicSine(z88)
  l88 = complexHyperbolicSineLong(z88)
  s88 = sameComplex(d88, l88)
  expect88: test.assertTrue(s88)
  calc za89 = convert.uint64BitsToFloat64(0)
  calc zb89 = convert.uint64BitsToFloat64(9223372036854775808)
  z89 = Complex.new(za89, zb89)
  d89 = complexHyperbolicSine(z89)
  l89 = complexHyperbolicSineLong(z89)
  s89 = sameComplex(d89, l89)
  expect89: test.assertTrue(s89)
  calc za90 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb90 = convert.uint64BitsToFloat64(4611686018427387904)
  z90 = Complex.new(za90, zb90)
  d90 = complexHyperbolicSine(z90)
  l90 = complexHyperbolicSineLong(z90)
  s90 = sameComplex(d90, l90)
  expect90: test.assertTrue(s90)
  calc za91 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb91 = convert.uint64BitsToFloat64(13826050856027422720)
  z91 = Complex.new(za91, zb91)
  d91 = complexHyperbolicCosine(z91)
  l91 = complexHyperbolicCosineLong(z91)
  s91 = sameComplex(d91, l91)
  expect91: test.assertTrue(s91)
  calc za92 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb92 = convert.uint64BitsToFloat64(4613937818241073152)
  z92 = Complex.new(za92, zb92)
  d92 = complexHyperbolicCosine(z92)
  l92 = complexHyperbolicCosineLong(z92)
  s92 = sameComplex(d92, l92)
  expect92: test.assertTrue(s92)
  calc za93 = convert.uint64BitsToFloat64(0)
  calc zb93 = convert.uint64BitsToFloat64(4607182418800017408)
  z93 = Complex.new(za93, zb93)
  d93 = complexHyperbolicCosine(z93)
  l93 = complexHyperbolicCosineLong(z93)
  s93 = sameComplex(d93, l93)
  expect93: test.assertTrue(s93)
  calc za94 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb94 = convert.uint64BitsToFloat64(18318360957983683996)
  z94 = Complex.new(za94, zb94)
  d94 = complexHyperbolicCosine(z94)
  l94 = complexHyperbolicCosineLong(z94)
  s94 = sameComplex(d94, l94)
  expect94: test.assertTrue(s94)
  calc za95 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb95 = convert.uint64BitsToFloat64(9221120237041090560)
  z95 = Complex.new(za95, zb95)
  d95 = complexHyperbolicCosine(z95)
  l95 = complexHyperbolicCosineLong(z95)
  s95 = sameComplex(d95, l95)
  expect95: test.assertTrue(s95)
  calc za96 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb96 = convert.uint64BitsToFloat64(0)
  z96 = Complex.new(za96, zb96)
  d96 = complexHyperbolicCosine(z96)
  l96 = complexHyperbolicCosineLong(z96)
  s96 = sameComplex(d96, l96)
  expect96: test.assertTrue(s96)
  calc za97 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb97 = convert.uint64BitsToFloat64(9223372036854775808)
  z97 = Complex.new(za97, zb97)
  d97 = complexHyperbolicCosine(z97)
  l97 = complexHyperbolicCosineLong(z97)
  s97 = sameComplex(d97, l97)
  expect97: test.assertTrue(s97)
  calc za98 = convert.uint64BitsToFloat64(0)
  calc zb98 = convert.uint64BitsToFloat64(9223372036854775808)
  z98 = Complex.new(za98, zb98)
  d98 = complexHyperbolicCosine(z98)
  l98 = complexHyperbolicCosineLong(z98)
  s98 = sameComplex(d98, l98)
  expect98: test.assertTrue(s98)
  calc za99 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb99 = convert.uint64BitsToFloat64(4611686018427387904)
  z99 = Complex.new(za99, zb99)
  d99 = complexHyperbolicCosine(z99)
  l99 = complexHyperbolicCosineLong(z99)
  s99 = sameComplex(d99, l99)
  expect99: test.assertTrue(s99)
  calc za100 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb100 = convert.uint64BitsToFloat64(13826050856027422720)
  z100 = Complex.new(za100, zb100)
  d100 = complexHyperbolicTangent(z100)
  l100 = complexHyperbolicTangentLong(z100)
  s100 = sameComplex(d100, l100)
  expect100: test.assertTrue(s100)
  calc za101 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb101 = convert.uint64BitsToFloat64(4613937818241073152)
  z101 = Complex.new(za101, zb101)
  d101 = complexHyperbolicTangent(z101)
  l101 = complexHyperbolicTangentLong(z101)
  s101 = sameComplex(d101, l101)
  expect101: test.assertTrue(s101)
  calc za102 = convert.uint64BitsToFloat64(0)
  calc zb102 = convert.uint64BitsToFloat64(4607182418800017408)
  z102 = Complex.new(za102, zb102)
  d102 = complexHyperbolicTangent(z102)
  l102 = complexHyperbolicTangentLong(z102)
  s102 = sameComplex(d102, l102)
  expect102: test.assertTrue(s102)
  calc za103 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb103 = convert.uint64BitsToFloat64(18318360957983683996)
  z103 = Complex.new(za103, zb103)
  d103 = complexHyperbolicTangent(z103)
  l103 = complexHyperbolicTangentLong(z103)
  s103 = sameComplex(d103, l103)
  expect103: test.assertTrue(s103)
  calc za104 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb104 = convert.uint64BitsToFloat64(9221120237041090560)
  z104 = Complex.new(za104, zb104)
  d104 = complexHyperbolicTangent(z104)
  l104 = complexHyperbolicTangentLong(z104)
  s104 = sameComplex(d104, l104)
  expect104: test.assertTrue(s104)
  calc za105 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb105 = convert.uint64BitsToFloat64(0)
  z105 = Complex.new(za105, zb105)
  d105 = complexHyperbolicTangent(z105)
  l105 = complexHyperbolicTangentLong(z105)
  s105 = sameComplex(d105, l105)
  expect105: test.assertTrue(s105)
  calc za106 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb106 = convert.uint64BitsToFloat64(9223372036854775808)
  z106 = Complex.new(za106, zb106)
  d106 = complexHyperbolicTangent(z106)
  l106 = complexHyperbolicTangentLong(z106)
  s106 = sameComplex(d106, l106)
  expect106: test.assertTrue(s106)
  calc za107 = convert.uint64BitsToFloat64(0)
  calc zb107 = convert.uint64BitsToFloat64(9223372036854775808)
  z107 = Complex.new(za107, zb107)
  d107 = complexHyperbolicTangent(z107)
  l107 = complexHyperbolicTangentLong(z107)
  s107 = sameComplex(d107, l107)
  expect107: test.assertTrue(s107)
  calc za108 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb108 = convert.uint64BitsToFloat64(4611686018427387904)
  z108 = Complex.new(za108, zb108)
  d108 = complexHyperbolicTangent(z108)
  l108 = complexHyperbolicTangentLong(z108)
  s108 = sameComplex(d108, l108)
  expect108: test.assertTrue(s108)
  calc za109 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb109 = convert.uint64BitsToFloat64(13826050856027422720)
  z109 = Complex.new(za109, zb109)
  d109 = complexInverseHyperbolicSine(z109)
  l109 = complexInverseHyperbolicSineLong(z109)
  s109 = sameComplex(d109, l109)
  expect109: test.assertTrue(s109)
  calc za110 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb110 = convert.uint64BitsToFloat64(4613937818241073152)
  z110 = Complex.new(za110, zb110)
  d110 = complexInverseHyperbolicSine(z110)
  l110 = complexInverseHyperbolicSineLong(z110)
  s110 = sameComplex(d110, l110)
  expect110: test.assertTrue(s110)
  calc za111 = convert.uint64BitsToFloat64(0)
  calc zb111 = convert.uint64BitsToFloat64(4607182418800017408)
  z111 = Complex.new(za111, zb111)
  d111 = complexInverseHyperbolicSine(z111)
  l111 = complexInverseHyperbolicSineLong(z111)
  s111 = sameComplex(d111, l111)
  expect111: test.assertTrue(s111)
  calc za112 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb112 = convert.uint64BitsToFloat64(18318360957983683996)
  z112 = Complex.new(za112, zb112)
  d112 = complexInverseHyperbolicSine(z112)
  l112 = complexInverseHyperbolicSineLong(z112)
  s112 = sameComplex(d112, l112)
  expect112: test.assertTrue(s112)
  calc za113 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb113 = convert.uint64BitsToFloat64(9221120237041090560)
  z113 = Complex.new(za113, zb113)
  d113 = complexInverseHyperbolicSine(z113)
  l113 = complexInverseHyperbolicSineLong(z113)
  s113 = sameComplex(d113, l113)
  expect113: test.assertTrue(s113)
  calc za114 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb114 = convert.uint64BitsToFloat64(0)
  z114 = Complex.new(za114, zb114)
  d114 = complexInverseHyperbolicSine(z114)
  l114 = complexInverseHyperbolicSineLong(z114)
  s114 = sameComplex(d114, l114)
  expect114: test.assertTrue(s114)
  calc za115 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb115 = convert.uint64BitsToFloat64(9223372036854775808)
  z115 = Complex.new(za115, zb115)
  d115 = complexInverseHyperbolicSine(z115)
  l115 = complexInverseHyperbolicSineLong(z115)
  s115 = sameComplex(d115, l115)
  expect115: test.assertTrue(s115)
  calc za116 = convert.uint64BitsToFloat64(0)
  calc zb116 = convert.uint64BitsToFloat64(9223372036854775808)
  z116 = Complex.new(za116, zb116)
  d116 = complexInverseHyperbolicSine(z116)
  l116 = complexInverseHyperbolicSineLong(z116)
  s116 = sameComplex(d116, l116)
  expect116: test.assertTrue(s116)
  calc za117 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb117 = convert.uint64BitsToFloat64(4611686018427387904)
  z117 = Complex.new(za117, zb117)
  d117 = complexInverseHyperbolicSine(z117)
  l117 = complexInverseHyperbolicSineLong(z117)
  s117 = sameComplex(d117, l117)
  expect117: test.assertTrue(s117)
  calc za118 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb118 = convert.uint64BitsToFloat64(13826050856027422720)
  z118 = Complex.new(za118, zb118)
  d118 = complexInverseHyperbolicCosine(z118)
  l118 = complexInverseHyperbolicCosineLong(z118)
  s118 = sameComplex(d118, l118)
  expect118: test.assertTrue(s118)
  calc za119 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb119 = convert.uint64BitsToFloat64(4613937818241073152)
  z119 = Complex.new(za119, zb119)
  d119 = complexInverseHyperbolicCosine(z119)
  l119 = complexInverseHyperbolicCosineLong(z119)
  s119 = sameComplex(d119, l119)
  expect119: test.assertTrue(s119)
  calc za120 = convert.uint64BitsToFloat64(0)
  calc zb120 = convert.uint64BitsToFloat64(4607182418800017408)
  z120 = Complex.new(za120, zb120)
  d120 = complexInverseHyperbolicCosine(z120)
  l120 = complexInverseHyperbolicCosineLong(z120)
  s120 = sameComplex(d120, l120)
  expect120: test.assertTrue(s120)
  calc za121 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb121 = convert.uint64BitsToFloat64(18318360957983683996)
  z121 = Complex.new(za121, zb121)
  d121 = complexInverseHyperbolicCosine(z121)
  l121 = complexInverseHyperbolicCosineLong(z121)
  s121 = sameComplex(d121, l121)
  expect121: test.assertTrue(s121)
  calc za122 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb122 = convert.uint64BitsToFloat64(9221120237041090560)
  z122 = Complex.new(za122, zb122)
  d122 = complexInverseHyperbolicCosine(z122)
  l122 = complexInverseHyperbolicCosineLong(z122)
  s122 = sameComplex(d122, l122)
  expect122: test.assertTrue(s122)
  calc za123 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb123 = convert.uint64BitsToFloat64(0)
  z123 = Complex.new(za123, zb123)
  d123 = complexInverseHyperbolicCosine(z123)
  l123 = complexInverseHyperbolicCosineLong(z123)
  s123 = sameComplex(d123, l123)
  expect123: test.assertTrue(s123)
  calc za124 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb124 = convert.uint64BitsToFloat64(9223372036854775808)
  z124 = Complex.new(za124, zb124)
  d124 = complexInverseHyperbolicCosine(z124)
  l124 = complexInverseHyperbolicCosineLong(z124)
  s124 = sameComplex(d124, l124)
  expect124: test.assertTrue(s124)
  calc za125 = convert.uint64BitsToFloat64(0)
  calc zb125 = convert.uint64BitsToFloat64(9223372036854775808)
  z125 = Complex.new(za125, zb125)
  d125 = complexInverseHyperbolicCosine(z125)
  l125 = complexInverseHyperbolicCosineLong(z125)
  s125 = sameComplex(d125, l125)
  expect125: test.assertTrue(s125)
  calc za126 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb126 = convert.uint64BitsToFloat64(4611686018427387904)
  z126 = Complex.new(za126, zb126)
  d126 = complexInverseHyperbolicCosine(z126)
  l126 = complexInverseHyperbolicCosineLong(z126)
  s126 = sameComplex(d126, l126)
  expect126: test.assertTrue(s126)
  calc za127 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb127 = convert.uint64BitsToFloat64(13826050856027422720)
  z127 = Complex.new(za127, zb127)
  d127 = complexInverseHyperbolicTangent(z127)
  l127 = complexInverseHyperbolicTangentLong(z127)
  s127 = sameComplex(d127, l127)
  expect127: test.assertTrue(s127)
  calc za128 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb128 = convert.uint64BitsToFloat64(4613937818241073152)
  z128 = Complex.new(za128, zb128)
  d128 = complexInverseHyperbolicTangent(z128)
  l128 = complexInverseHyperbolicTangentLong(z128)
  s128 = sameComplex(d128, l128)
  expect128: test.assertTrue(s128)
  calc za129 = convert.uint64BitsToFloat64(0)
  calc zb129 = convert.uint64BitsToFloat64(4607182418800017408)
  z129 = Complex.new(za129, zb129)
  d129 = complexInverseHyperbolicTangent(z129)
  l129 = complexInverseHyperbolicTangentLong(z129)
  s129 = sameComplex(d129, l129)
  expect129: test.assertTrue(s129)
  calc za130 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb130 = convert.uint64BitsToFloat64(18318360957983683996)
  z130 = Complex.new(za130, zb130)
  d130 = complexInverseHyperbolicTangent(z130)
  l130 = complexInverseHyperbolicTangentLong(z130)
  s130 = sameComplex(d130, l130)
  expect130: test.assertTrue(s130)
  calc za131 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb131 = convert.uint64BitsToFloat64(9221120237041090560)
  z131 = Complex.new(za131, zb131)
  d131 = complexInverseHyperbolicTangent(z131)
  l131 = complexInverseHyperbolicTangentLong(z131)
  s131 = sameComplex(d131, l131)
  expect131: test.assertTrue(s131)
  calc za132 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb132 = convert.uint64BitsToFloat64(0)
  z132 = Complex.new(za132, zb132)
  d132 = complexInverseHyperbolicTangent(z132)
  l132 = complexInverseHyperbolicTangentLong(z132)
  s132 = sameComplex(d132, l132)
  expect132: test.assertTrue(s132)
  calc za133 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb133 = convert.uint64BitsToFloat64(9223372036854775808)
  z133 = Complex.new(za133, zb133)
  d133 = complexInverseHyperbolicTangent(z133)
  l133 = complexInverseHyperbolicTangentLong(z133)
  s133 = sameComplex(d133, l133)
  expect133: test.assertTrue(s133)
  calc za134 = convert.uint64BitsToFloat64(0)
  calc zb134 = convert.uint64BitsToFloat64(9223372036854775808)
  z134 = Complex.new(za134, zb134)
  d134 = complexInverseHyperbolicTangent(z134)
  l134 = complexInverseHyperbolicTangentLong(z134)
  s134 = sameComplex(d134, l134)
  expect134: test.assertTrue(s134)
  calc za135 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb135 = convert.uint64BitsToFloat64(4611686018427387904)
  z135 = Complex.new(za135, zb135)
  d135 = complexInverseHyperbolicTangent(z135)
  l135 = complexInverseHyperbolicTangentLong(z135)
  s135 = sameComplex(d135, l135)
  expect135: test.assertTrue(s135)
  calc za136 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb136 = convert.uint64BitsToFloat64(13826050856027422720)
  z136 = Complex.new(za136, zb136)
  d136 = complexConjugate(z136)
  l136 = complexConjugateLong(z136)
  s136 = sameComplex(d136, l136)
  expect136: test.assertTrue(s136)
  calc za137 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb137 = convert.uint64BitsToFloat64(4613937818241073152)
  z137 = Complex.new(za137, zb137)
  d137 = complexConjugate(z137)
  l137 = complexConjugateLong(z137)
  s137 = sameComplex(d137, l137)
  expect137: test.assertTrue(s137)
  calc za138 = convert.uint64BitsToFloat64(0)
  calc zb138 = convert.uint64BitsToFloat64(4607182418800017408)
  z138 = Complex.new(za138, zb138)
  d138 = complexConjugate(z138)
  l138 = complexConjugateLong(z138)
  s138 = sameComplex(d138, l138)
  expect138: test.assertTrue(s138)
  calc za139 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb139 = convert.uint64BitsToFloat64(18318360957983683996)
  z139 = Complex.new(za139, zb139)
  d139 = complexConjugate(z139)
  l139 = complexConjugateLong(z139)
  s139 = sameComplex(d139, l139)
  expect139: test.assertTrue(s139)
  calc za140 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb140 = convert.uint64BitsToFloat64(9221120237041090560)
  z140 = Complex.new(za140, zb140)
  d140 = complexConjugate(z140)
  l140 = complexConjugateLong(z140)
  s140 = sameComplex(d140, l140)
  expect140: test.assertTrue(s140)
  calc za141 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb141 = convert.uint64BitsToFloat64(0)
  z141 = Complex.new(za141, zb141)
  d141 = complexConjugate(z141)
  l141 = complexConjugateLong(z141)
  s141 = sameComplex(d141, l141)
  expect141: test.assertTrue(s141)
  calc za142 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb142 = convert.uint64BitsToFloat64(9223372036854775808)
  z142 = Complex.new(za142, zb142)
  d142 = complexConjugate(z142)
  l142 = complexConjugateLong(z142)
  s142 = sameComplex(d142, l142)
  expect142: test.assertTrue(s142)
  calc za143 = convert.uint64BitsToFloat64(0)
  calc zb143 = convert.uint64BitsToFloat64(9223372036854775808)
  z143 = Complex.new(za143, zb143)
  d143 = complexConjugate(z143)
  l143 = complexConjugateLong(z143)
  s143 = sameComplex(d143, l143)
  expect143: test.assertTrue(s143)
  calc za144 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb144 = convert.uint64BitsToFloat64(4611686018427387904)
  z144 = Complex.new(za144, zb144)
  d144 = complexConjugate(z144)
  l144 = complexConjugateLong(z144)
  s144 = sameComplex(d144, l144)
  expect144: test.assertTrue(s144)
  calc za145 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb145 = convert.uint64BitsToFloat64(13826050856027422720)
  z145 = Complex.new(za145, zb145)
  d145 = complexProjection(z145)
  l145 = complexProjectionLong(z145)
  s145 = sameComplex(d145, l145)
  expect145: test.assertTrue(s145)
  calc za146 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb146 = convert.uint64BitsToFloat64(4613937818241073152)
  z146 = Complex.new(za146, zb146)
  d146 = complexProjection(z146)
  l146 = complexProjectionLong(z146)
  s146 = sameComplex(d146, l146)
  expect146: test.assertTrue(s146)
  calc za147 = convert.uint64BitsToFloat64(0)
  calc zb147 = convert.uint64BitsToFloat64(4607182418800017408)
  z147 = Complex.new(za147, zb147)
  d147 = complexProjection(z147)
  l147 = complexProjectionLong(z147)
  s147 = sameComplex(d147, l147)
  expect147: test.assertTrue(s147)
  calc za148 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb148 = convert.uint64BitsToFloat64(18318360957983683996)
  z148 = Complex.new(za148, zb148)
  d148 = complexProjection(z148)
  l148 = complexProjectionLong(z148)
  s148 = sameComplex(d148, l148)
  expect148: test.assertTrue(s148)
  calc za149 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb149 = convert.uint64BitsToFloat64(9221120237041090560)
  z149 = Complex.new(za149, zb149)
  d149 = complexProjection(z149)
  l149 = complexProjectionLong(z149)
  s149 = sameComplex(d149, l149)
  expect149: test.assertTrue(s149)
  calc za150 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb150 = convert.uint64BitsToFloat64(0)
  z150 = Complex.new(za150, zb150)
  d150 = complexProjection(z150)
  l150 = complexProjectionLong(z150)
  s150 = sameComplex(d150, l150)
  expect150: test.assertTrue(s150)
  calc za151 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb151 = convert.uint64BitsToFloat64(9223372036854775808)
  z151 = Complex.new(za151, zb151)
  d151 = complexProjection(z151)
  l151 = complexProjectionLong(z151)
  s151 = sameComplex(d151, l151)
  expect151: test.assertTrue(s151)
  calc za152 = convert.uint64BitsToFloat64(0)
  calc zb152 = convert.uint64BitsToFloat64(9223372036854775808)
  z152 = Complex.new(za152, zb152)
  d152 = complexProjection(z152)
  l152 = complexProjectionLong(z152)
  s152 = sameComplex(d152, l152)
  expect152: test.assertTrue(s152)
  calc za153 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb153 = convert.uint64BitsToFloat64(4611686018427387904)
  z153 = Complex.new(za153, zb153)
  d153 = complexProjection(z153)
  l153 = complexProjectionLong(z153)
  s153 = sameComplex(d153, l153)
  expect153: test.assertTrue(s153)
  calc za154 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb154 = convert.uint64BitsToFloat64(13826050856027422720)
  z154 = Complex.new(za154, zb154)
  d154 = complexMagnitude(z154)
  l154 = complexMagnitudeLong(z154)
  s154 = sameBits(d154, l154)
  expect154: test.assertTrue(s154)
  calc za155 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb155 = convert.uint64BitsToFloat64(4613937818241073152)
  z155 = Complex.new(za155, zb155)
  d155 = complexMagnitude(z155)
  l155 = complexMagnitudeLong(z155)
  s155 = sameBits(d155, l155)
  expect155: test.assertTrue(s155)
  calc za156 = convert.uint64BitsToFloat64(0)
  calc zb156 = convert.uint64BitsToFloat64(4607182418800017408)
  z156 = Complex.new(za156, zb156)
  d156 = complexMagnitude(z156)
  l156 = complexMagnitudeLong(z156)
  s156 = sameBits(d156, l156)
  expect156: test.assertTrue(s156)
  calc za157 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb157 = convert.uint64BitsToFloat64(18318360957983683996)
  z157 = Complex.new(za157, zb157)
  d157 = complexMagnitude(z157)
  l157 = complexMagnitudeLong(z157)
  s157 = sameBits(d157, l157)
  expect157: test.assertTrue(s157)
  calc za158 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb158 = convert.uint64BitsToFloat64(9221120237041090560)
  z158 = Complex.new(za158, zb158)
  d158 = complexMagnitude(z158)
  l158 = complexMagnitudeLong(z158)
  s158 = sameBits(d158, l158)
  expect158: test.assertTrue(s158)
  calc za159 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb159 = convert.uint64BitsToFloat64(0)
  z159 = Complex.new(za159, zb159)
  d159 = complexMagnitude(z159)
  l159 = complexMagnitudeLong(z159)
  s159 = sameBits(d159, l159)
  expect159: test.assertTrue(s159)
  calc za160 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb160 = convert.uint64BitsToFloat64(9223372036854775808)
  z160 = Complex.new(za160, zb160)
  d160 = complexMagnitude(z160)
  l160 = complexMagnitudeLong(z160)
  s160 = sameBits(d160, l160)
  expect160: test.assertTrue(s160)
  calc za161 = convert.uint64BitsToFloat64(0)
  calc zb161 = convert.uint64BitsToFloat64(9223372036854775808)
  z161 = Complex.new(za161, zb161)
  d161 = complexMagnitude(z161)
  l161 = complexMagnitudeLong(z161)
  s161 = sameBits(d161, l161)
  expect161: test.assertTrue(s161)
  calc za162 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb162 = convert.uint64BitsToFloat64(4611686018427387904)
  z162 = Complex.new(za162, zb162)
  d162 = complexMagnitude(z162)
  l162 = complexMagnitudeLong(z162)
  s162 = sameBits(d162, l162)
  expect162: test.assertTrue(s162)
  calc za163 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb163 = convert.uint64BitsToFloat64(13826050856027422720)
  z163 = Complex.new(za163, zb163)
  d163 = complexArgument(z163)
  l163 = complexArgumentLong(z163)
  s163 = sameBits(d163, l163)
  expect163: test.assertTrue(s163)
  calc za164 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb164 = convert.uint64BitsToFloat64(4613937818241073152)
  z164 = Complex.new(za164, zb164)
  d164 = complexArgument(z164)
  l164 = complexArgumentLong(z164)
  s164 = sameBits(d164, l164)
  expect164: test.assertTrue(s164)
  calc za165 = convert.uint64BitsToFloat64(0)
  calc zb165 = convert.uint64BitsToFloat64(4607182418800017408)
  z165 = Complex.new(za165, zb165)
  d165 = complexArgument(z165)
  l165 = complexArgumentLong(z165)
  s165 = sameBits(d165, l165)
  expect165: test.assertTrue(s165)
  calc za166 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb166 = convert.uint64BitsToFloat64(18318360957983683996)
  z166 = Complex.new(za166, zb166)
  d166 = complexArgument(z166)
  l166 = complexArgumentLong(z166)
  s166 = sameBits(d166, l166)
  expect166: test.assertTrue(s166)
  calc za167 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb167 = convert.uint64BitsToFloat64(9221120237041090560)
  z167 = Complex.new(za167, zb167)
  d167 = complexArgument(z167)
  l167 = complexArgumentLong(z167)
  s167 = sameBits(d167, l167)
  expect167: test.assertTrue(s167)
  calc za168 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb168 = convert.uint64BitsToFloat64(0)
  z168 = Complex.new(za168, zb168)
  d168 = complexArgument(z168)
  l168 = complexArgumentLong(z168)
  s168 = sameBits(d168, l168)
  expect168: test.assertTrue(s168)
  calc za169 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb169 = convert.uint64BitsToFloat64(9223372036854775808)
  z169 = Complex.new(za169, zb169)
  d169 = complexArgument(z169)
  l169 = complexArgumentLong(z169)
  s169 = sameBits(d169, l169)
  expect169: test.assertTrue(s169)
  calc za170 = convert.uint64BitsToFloat64(0)
  calc zb170 = convert.uint64BitsToFloat64(9223372036854775808)
  z170 = Complex.new(za170, zb170)
  d170 = complexArgument(z170)
  l170 = complexArgumentLong(z170)
  s170 = sameBits(d170, l170)
  expect170: test.assertTrue(s170)
  calc za171 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb171 = convert.uint64BitsToFloat64(4611686018427387904)
  z171 = Complex.new(za171, zb171)
  d171 = complexArgument(z171)
  l171 = complexArgumentLong(z171)
  s171 = sameBits(d171, l171)
  expect171: test.assertTrue(s171)
  calc za172 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb172 = convert.uint64BitsToFloat64(13826050856027422720)
  z172 = Complex.new(za172, zb172)
  d172 = complexRealPart(z172)
  l172 = complexRealPartLong(z172)
  s172 = sameBits(d172, l172)
  expect172: test.assertTrue(s172)
  calc za173 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb173 = convert.uint64BitsToFloat64(4613937818241073152)
  z173 = Complex.new(za173, zb173)
  d173 = complexRealPart(z173)
  l173 = complexRealPartLong(z173)
  s173 = sameBits(d173, l173)
  expect173: test.assertTrue(s173)
  calc za174 = convert.uint64BitsToFloat64(0)
  calc zb174 = convert.uint64BitsToFloat64(4607182418800017408)
  z174 = Complex.new(za174, zb174)
  d174 = complexRealPart(z174)
  l174 = complexRealPartLong(z174)
  s174 = sameBits(d174, l174)
  expect174: test.assertTrue(s174)
  calc za175 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb175 = convert.uint64BitsToFloat64(18318360957983683996)
  z175 = Complex.new(za175, zb175)
  d175 = complexRealPart(z175)
  l175 = complexRealPartLong(z175)
  s175 = sameBits(d175, l175)
  expect175: test.assertTrue(s175)
  calc za176 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb176 = convert.uint64BitsToFloat64(9221120237041090560)
  z176 = Complex.new(za176, zb176)
  d176 = complexRealPart(z176)
  l176 = complexRealPartLong(z176)
  s176 = sameBits(d176, l176)
  expect176: test.assertTrue(s176)
  calc za177 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb177 = convert.uint64BitsToFloat64(0)
  z177 = Complex.new(za177, zb177)
  d177 = complexRealPart(z177)
  l177 = complexRealPartLong(z177)
  s177 = sameBits(d177, l177)
  expect177: test.assertTrue(s177)
  calc za178 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb178 = convert.uint64BitsToFloat64(9223372036854775808)
  z178 = Complex.new(za178, zb178)
  d178 = complexRealPart(z178)
  l178 = complexRealPartLong(z178)
  s178 = sameBits(d178, l178)
  expect178: test.assertTrue(s178)
  calc za179 = convert.uint64BitsToFloat64(0)
  calc zb179 = convert.uint64BitsToFloat64(9223372036854775808)
  z179 = Complex.new(za179, zb179)
  d179 = complexRealPart(z179)
  l179 = complexRealPartLong(z179)
  s179 = sameBits(d179, l179)
  expect179: test.assertTrue(s179)
  calc za180 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb180 = convert.uint64BitsToFloat64(4611686018427387904)
  z180 = Complex.new(za180, zb180)
  d180 = complexRealPart(z180)
  l180 = complexRealPartLong(z180)
  s180 = sameBits(d180, l180)
  expect180: test.assertTrue(s180)
  calc za181 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb181 = convert.uint64BitsToFloat64(13826050856027422720)
  z181 = Complex.new(za181, zb181)
  d181 = complexImaginaryPart(z181)
  l181 = complexImaginaryPartLong(z181)
  s181 = sameBits(d181, l181)
  expect181: test.assertTrue(s181)
  calc za182 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb182 = convert.uint64BitsToFloat64(4613937818241073152)
  z182 = Complex.new(za182, zb182)
  d182 = complexImaginaryPart(z182)
  l182 = complexImaginaryPartLong(z182)
  s182 = sameBits(d182, l182)
  expect182: test.assertTrue(s182)
  calc za183 = convert.uint64BitsToFloat64(0)
  calc zb183 = convert.uint64BitsToFloat64(4607182418800017408)
  z183 = Complex.new(za183, zb183)
  d183 = complexImaginaryPart(z183)
  l183 = complexImaginaryPartLong(z183)
  s183 = sameBits(d183, l183)
  expect183: test.assertTrue(s183)
  calc za184 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb184 = convert.uint64BitsToFloat64(18318360957983683996)
  z184 = Complex.new(za184, zb184)
  d184 = complexImaginaryPart(z184)
  l184 = complexImaginaryPartLong(z184)
  s184 = sameBits(d184, l184)
  expect184: test.assertTrue(s184)
  calc za185 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb185 = convert.uint64BitsToFloat64(9221120237041090560)
  z185 = Complex.new(za185, zb185)
  d185 = complexImaginaryPart(z185)
  l185 = complexImaginaryPartLong(z185)
  s185 = sameBits(d185, l185)
  expect185: test.assertTrue(s185)
  calc za186 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb186 = convert.uint64BitsToFloat64(0)
  z186 = Complex.new(za186, zb186)
  d186 = complexImaginaryPart(z186)
  l186 = complexImaginaryPartLong(z186)
  s186 = sameBits(d186, l186)
  expect186: test.assertTrue(s186)
  calc za187 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb187 = convert.uint64BitsToFloat64(9223372036854775808)
  z187 = Complex.new(za187, zb187)
  d187 = complexImaginaryPart(z187)
  l187 = complexImaginaryPartLong(z187)
  s187 = sameBits(d187, l187)
  expect187: test.assertTrue(s187)
  calc za188 = convert.uint64BitsToFloat64(0)
  calc zb188 = convert.uint64BitsToFloat64(9223372036854775808)
  z188 = Complex.new(za188, zb188)
  d188 = complexImaginaryPart(z188)
  l188 = complexImaginaryPartLong(z188)
  s188 = sameBits(d188, l188)
  expect188: test.assertTrue(s188)
  calc za189 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb189 = convert.uint64BitsToFloat64(4611686018427387904)
  z189 = Complex.new(za189, zb189)
  d189 = complexImaginaryPart(z189)
  l189 = complexImaginaryPartLong(z189)
  s189 = sameBits(d189, l189)
  expect189: test.assertTrue(s189)
  calc za190 = convert.uint64BitsToFloat64(4609434218613702656)
  calc zb190 = convert.uint64BitsToFloat64(13826050856027422720)
  z190 = Complex.new(za190, zb190)
  calc wa190 = convert.uint64BitsToFloat64(13835058055282163712)
  calc wb190 = convert.uint64BitsToFloat64(4613937818241073152)
  w190 = Complex.new(wa190, wb190)
  d190 = complexPower(z190, w190)
  l190 = complexPowerLong(z190, w190)
  s190 = sameComplex(d190, l190)
  expect190: test.assertTrue(s190)
  calc za191 = convert.uint64BitsToFloat64(13835058055282163712)
  calc zb191 = convert.uint64BitsToFloat64(4613937818241073152)
  z191 = Complex.new(za191, zb191)
  calc wa191 = convert.uint64BitsToFloat64(0)
  calc wb191 = convert.uint64BitsToFloat64(4607182418800017408)
  w191 = Complex.new(wa191, wb191)
  d191 = complexPower(z191, w191)
  l191 = complexPowerLong(z191, w191)
  s191 = sameComplex(d191, l191)
  expect191: test.assertTrue(s191)
  calc za192 = convert.uint64BitsToFloat64(0)
  calc zb192 = convert.uint64BitsToFloat64(4607182418800017408)
  z192 = Complex.new(za192, zb192)
  calc wa192 = convert.uint64BitsToFloat64(9094988921128908188)
  calc wb192 = convert.uint64BitsToFloat64(18318360957983683996)
  w192 = Complex.new(wa192, wb192)
  d192 = complexPower(z192, w192)
  l192 = complexPowerLong(z192, w192)
  s192 = sameComplex(d192, l192)
  expect192: test.assertTrue(s192)
  calc za193 = convert.uint64BitsToFloat64(9094988921128908188)
  calc zb193 = convert.uint64BitsToFloat64(18318360957983683996)
  z193 = Complex.new(za193, zb193)
  calc wa193 = convert.uint64BitsToFloat64(9218868437227405312)
  calc wb193 = convert.uint64BitsToFloat64(9221120237041090560)
  w193 = Complex.new(wa193, wb193)
  d193 = complexPower(z193, w193)
  l193 = complexPowerLong(z193, w193)
  s193 = sameComplex(d193, l193)
  expect193: test.assertTrue(s193)
  calc za194 = convert.uint64BitsToFloat64(9218868437227405312)
  calc zb194 = convert.uint64BitsToFloat64(9221120237041090560)
  z194 = Complex.new(za194, zb194)
  calc wa194 = convert.uint64BitsToFloat64(9221120237041090560)
  calc wb194 = convert.uint64BitsToFloat64(0)
  w194 = Complex.new(wa194, wb194)
  d194 = complexPower(z194, w194)
  l194 = complexPowerLong(z194, w194)
  s194 = sameComplex(d194, l194)
  expect194: test.assertTrue(s194)
  calc za195 = convert.uint64BitsToFloat64(9221120237041090560)
  calc zb195 = convert.uint64BitsToFloat64(0)
  z195 = Complex.new(za195, zb195)
  calc wa195 = convert.uint64BitsToFloat64(9223372036854775808)
  calc wb195 = convert.uint64BitsToFloat64(9223372036854775808)
  w195 = Complex.new(wa195, wb195)
  d195 = complexPower(z195, w195)
  l195 = complexPowerLong(z195, w195)
  s195 = sameComplex(d195, l195)
  expect195: test.assertTrue(s195)
  calc za196 = convert.uint64BitsToFloat64(9223372036854775808)
  calc zb196 = convert.uint64BitsToFloat64(9223372036854775808)
  z196 = Complex.new(za196, zb196)
  calc wa196 = convert.uint64BitsToFloat64(0)
  calc wb196 = convert.uint64BitsToFloat64(9223372036854775808)
  w196 = Complex.new(wa196, wb196)
  d196 = complexPower(z196, w196)
  l196 = complexPowerLong(z196, w196)
  s196 = sameComplex(d196, l196)
  expect196: test.assertTrue(s196)
  calc za197 = convert.uint64BitsToFloat64(0)
  calc zb197 = convert.uint64BitsToFloat64(9223372036854775808)
  z197 = Complex.new(za197, zb197)
  calc wa197 = convert.uint64BitsToFloat64(18442240474082181120)
  calc wb197 = convert.uint64BitsToFloat64(4611686018427387904)
  w197 = Complex.new(wa197, wb197)
  d197 = complexPower(z197, w197)
  l197 = complexPowerLong(z197, w197)
  s197 = sameComplex(d197, l197)
  expect197: test.assertTrue(s197)
  calc za198 = convert.uint64BitsToFloat64(18442240474082181120)
  calc zb198 = convert.uint64BitsToFloat64(4611686018427387904)
  z198 = Complex.new(za198, zb198)
  calc wa198 = convert.uint64BitsToFloat64(4609434218613702656)
  calc wb198 = convert.uint64BitsToFloat64(13826050856027422720)
  w198 = Complex.new(wa198, wb198)
  d198 = complexPower(z198, w198)
  l198 = complexPowerLong(z198, w198)
  s198 = sameComplex(d198, l198)
  expect198: test.assertTrue(s198)
  return

test complexTableTest "every function of complex.h on the special values of Annex G and some ordinary points, against an exact reference: a row is the arguments and the expected parts as bits and tolerances"
  verifies complexExponential givesCexp
  verifies complexLogarithm givesClog
  verifies complexSquareRoot givesCsqrt
  verifies complexSine givesCsin
  verifies complexCosine givesCcos
  verifies complexTangent givesCtan
  verifies complexInverseSine givesCasin
  verifies complexInverseCosine givesCacos
  verifies complexInverseTangent givesCatan
  verifies complexHyperbolicSine givesCsinh
  verifies complexHyperbolicCosine givesCcosh
  verifies complexHyperbolicTangent givesCtanh
  verifies complexInverseHyperbolicSine givesCasinh
  verifies complexInverseHyperbolicCosine givesCacosh
  verifies complexInverseHyperbolicTangent givesCatanh
  verifies complexConjugate givesConj
  verifies complexProjection givesCproj
  verifies complexMagnitude givesCabs
  verifies complexArgument givesCarg
  verifies complexRealPart givesCreal
  verifies complexImaginaryPart givesCimag
  verifies complexPower givesCpow
  verifies complexExponentialSingle givesCexpf
  verifies complexLogarithmSingle givesClogf
  verifies complexSquareRootSingle givesCsqrtf
  verifies complexSineSingle givesCsinf
  verifies complexCosineSingle givesCcosf
  verifies complexTangentSingle givesCtanf
  verifies complexInverseSineSingle givesCasinf
  verifies complexInverseCosineSingle givesCacosf
  verifies complexInverseTangentSingle givesCatanf
  verifies complexHyperbolicSineSingle givesCsinhf
  verifies complexHyperbolicCosineSingle givesCcoshf
  verifies complexHyperbolicTangentSingle givesCtanhf
  verifies complexInverseHyperbolicSineSingle givesCasinhf
  verifies complexInverseHyperbolicCosineSingle givesCacoshf
  verifies complexInverseHyperbolicTangentSingle givesCatanhf
  verifies complexConjugateSingle givesConjf
  verifies complexProjectionSingle givesCprojf
  verifies complexMagnitudeSingle givesCabsf
  verifies complexArgumentSingle givesCargf
  verifies complexRealPartSingle givesCrealf
  verifies complexImaginaryPartSingle givesCimagf
  verifies complexPowerSingle givesCpowf
  effect use machine.memory
  uses memoryAccess
  let table0 String "00000000000000000000000000000000000000000000000000000000000000003ff00000000000003cc80000000000000000000000000000000000000000000000000000000000008000000000000000000000000000000000000000000000003ff00000000000003cc80000000000008000000000000000000000000000000000000000000000003ff0000000000000000000000000000000000000000000003fe14a280fb5068c3cb80000000000003feaed548f090cee3cb800000000000000000000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff800000000000000000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff800000000000080000000000000000000000000000000000000000000000000000000000000003ff00000000000003cc80000000000000000000000000000000000000000000080000000000000008000000000000000000000000000000000000000000000003ff00000000000003cc80000000000008000000000000000000000000000000080000000000000003ff0000000000000000000000000000000000000000000003fe14a280fb5068c3cb80000000000003feaed548f090cee3cb800000000000080000000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff800000000000080000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003ff00000000000000000000000000000000000000000000000000000000000004005bf0a8b1457693cd8000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000004005bf0a8b1457693cd8000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003ff77fc5377c5a963cc800000000000040024c80edc620643cd80000000000003ff00000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000007ff00000000000000000000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000000000000000000000fff00000000000010000000000000000fff80000000000007ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff00000000000010000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000000000000000000000000000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f10c8942543fb04a6ece53d613000000000000000000000000000000003ff032b3021f03e53cc80000000000003fb083c30075f9ce3c88000000000000bfa8410510668fa6bfc2e30a9e501b7d000000000000000000000000000000003fee3016009c43253cb8000000000000bfc1f2a036b8bfe63c980000000000004085e000000000003ff0000000000000000000000000000000000000000000007efff6bc16ca21a27bc80000000000007f08e3ed589698667bd800000000000040863000000000003ff0000000000000000000000000000000000000000000007fe57c636cf4f5f87cb80000000000007ff00000000000000000000000000000c08720000000000040000000000000000000000000000000000000000000000080000000000000230000000000000003000000000000004d000000000000000340862c00000000003fe0000000000000000000000000000000000000000000007fe52aba22deb5cc7cb80000000000007fd720873894974b7ca8000000000000"
  let table1 String "0000000000000000000000000000000000000000000000000000000000000000fff00000000000000000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff000000000000000000000000000008000000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000000000000000000000000000000000023ff921fb54442d183cc000000000000000000000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000003ff921fb54442d18000000000000000000000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000008000000000000000000000000000000000000000000000000000000000000000fff00000000000000000000000000000400921fb54442d1800000000000000008000000000000000800000000000000000000000000000000000000000000000fff00000000000000000000000000000c00921fb54442d18000000000000000080000000000000003ff000000000000000000000000000000000000000000000000000000000000000000000000000023ff921fb54442d183cc000000000000080000000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000003ff921fb54442d18000000000000000080000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003ff000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000002000000000000000000000000000000003ff000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000002800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003fd62e42fefa39ef3ca00000000000003fe921fb54442d183cb00000000000003ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000003ff921fb54442d1800000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000007ff00000000000000000000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000003fe921fb54442d1800000000000000007ff00000000000007ff8000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff80000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f10c8942543fb04a6ece53d61300000000000000000000000000000000c005d6bdb48471233cd00000000000003ff596dfe3700c503cc0000000000000bfa8410510668fa6bfc2e30a9e501b7d00000000000000000000000000000000bffdd50d804f8b363cc0000000000000bffe1a65edbf1a833cc00000000000003ff00000000000003e112e0be826d695000000000000000000000000000000003c22725dd1d243ac38f00000000000003e112e0be826d6953ae00000000000003ff00000000000003c670ef54646d4970000000000000000000000000000000038d09d8792fb4c4a35a00000000000003c670ef54646d49739300000000000003fefffffffffffff000000000000000000000000000000000000000000000000bca00000000000003970000000000000000000000000000000000000000000003ff00000000000010000000000000000000000000000000000000000000000003cafffffffffffff397000000000000000000000000000000000000000000000"
  let table2 String "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000008000000000000000000000000000000000000000000000003ff0000000000000000000000000000000000000000000003fe6a09e667f3bcd3cb00000000000003fe6a09e667f3bcd3cb000000000000000000000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff0000000000000000000000000000000000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff8000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000008000000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000008000000000000000000000000000000080000000000000003ff0000000000000000000000000000000000000000000003fe6a09e667f3bcd3cb00000000000003fe6a09e667f3bcd3cb000000000000080000000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff0000000000000000000000000000080000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003ff00000000000000000000000000000000000000000000000000000000000003ff00000000000003cc0000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003ff00000000000003cc0000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003ff19435caffa9f93cc00000000000003fdd203138f6c8283ca00000000000003ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff000000000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000007ff00000000000000000000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff000000000000000000000000000007ff00000000000007ff8000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff000000000000000000000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f10c8942543fb04a6ece53d613000000000000000000000000000000003fc9876ad4f1d43d3c900000000000003fc46b8b6e0deda33c90000000000000bfa8410510668fa6bfc2e30a9e501b7d000000000000000000000000000000003fcdb07dfc9be28f3c90000000000000bfd45b540bb615f93ca00000000000007e37e43c8800759c7e37e43c8800759c000000000000000000000000000000005f157b2468f15c935be00000000000005f01cba37a2eacf65bd0000000000000fe37e43c8800759c7e37e43c8800759c000000000000000000000000000000005f01cba37a2eacf65bd00000000000005f157b2468f15c935be0000000000000000012688b70e62b000012688b70e62b000000000000000000000000000000001fc2db09474a8f601c900000000000001faf3db20d2b2e5c1c70000000000000800012688b70e62b0000000000000001000000000000000000000000000000001cedd55745cbb7fa19b00000000000001fc1297872d9cbae1c90000000000000"
  let table3 String "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000008000000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000000000000000000000000000000000003ff2cd9fc44eb9823cd000000000000000000000000000007ff000000000000000000000000000000000000000000000000000000000000000000000000000007ff0000000000000000000000000000000000000000000007ff800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000000000000000000000000000000000000080000000000000000000000000000000000000000000000000000000000000008000000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000008000000000000000000000000000000080000000000000003ff000000000000000000000000000000000000000000000800000000000000000000000000000003ff2cd9fc44eb9823cd000000000000080000000000000007ff000000000000000000000000000000000000000000000800000000000000000000000000000007ff0000000000000000000000000000080000000000000007ff800000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff80000000000003ff00000000000000000000000000000000000000000000000000000000000003feaed548f090cee3cc0000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003feaed548f090cee3cc0000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003ff4c67b74f6cc4f3cd00000000000003fe4519fd8047f923cc00000000000003ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff000000000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000027ff00000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000027ff00000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000037ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000027ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000027ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000037ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f10c8942543fb04a6ece53d613000000000000000000000000000000003f8d66e626fee90d3c600000000000003fb04cd1db6b5c173c90000000000000bfa8410510668fa6bfc2e30a9e501b7d00000000000000000000000000000000bfa882631177f19e3c80000000000000bfc2ef296a9e1bcf3ca00000000000003ff00000000000004085e00000000000000000000000000000000000000000007ef8e3ed589698667bd00000000000007eeff6bc16ca21a27bc00000000000003ff00000000000004086300000000000000000000000000000000000000000007fe0bb2c7615833d7cc00000000000007fd57c636cf4f5f87cb000000000000041cdcd65000000004008000000000000000000000000000000000000000000004015fb41943b86513cf00000000000004020c9a69306714b3d00000000000000"
  let table4 String "00000000000000000000000000000000000000000000000000000000000000003ff000000000000000000000000000008000000000000000000000000000000000000000000000008000000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000000000000000000000000000000000003ff0000000000000000000000000000000000000000000003ff8b07551d9f5503cd00000000000008000000000000000000000000000000000000000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000008000000000000000000000000000000000000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff000000000000280000000000000000000000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000000000000000000080000000000000008000000000000000000000000000000000000000000000003ff000000000000000000000000000008000000000000000000000000000000080000000000000003ff0000000000000000000000000000000000000000000003ff8b07551d9f5503cd00000000000000000000000000000000000000000000080000000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000000000000000000080000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000023ff00000000000000000000000000000000000000000000000000000000000003fe14a280fb5068c3cc0000000000000800000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003fe14a280fb5068c3cc0000000000000000000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003feaadea96f4359a3cc0000000000000bfefa50ccd2ae8f33cc00000000000003ff00000000000007ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000fff000000000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000027ff00000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000027ff00000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000007ff0000000000000000000000000000000000000000000000000000000000000fff00000000000030000000000000000fff80000000000007ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000027ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000027ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff80000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f10c8942543fb04a6ece53d613000000000000000000000000000000003ff007dffab0931e3cd0000000000000bf4de559b75013523c20000000000000bfa8410510668fa6bfc2e30a9e501b7d000000000000000000000000000000003ff02806764dc53b3cd0000000000000bf7cb92ffb24861a3c500000000000003ff00000000000004085e00000000000000000000000000000000000000000007eeff6bc16ca21a27bc0000000000000fef8e3ed589698667bd00000000000003ff00000000000004086300000000000000000000000000000000000000000007fd57c636cf4f5f87cb0000000000000ffe0bb2c7615833d7cc000000000000041cdcd65000000004008000000000000000000000000000000000000000000004020df025de951233d00000000000000c015df6d916d23a03cf0000000000000"
  let table5 String "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000008000000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000000000000000000000000000000000003fe85efab514f3943cc800000000000000000000000000007ff000000000000000000000000000000000000000000000000000000000000000000000000000003ff0000000000000000000000000000000000000000000007ff800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000000000000000000000000000000000000080000000000000000000000000000000000000000000000000000000000000008000000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000008000000000000000000000000000000080000000000000003ff000000000000000000000000000000000000000000000800000000000000000000000000000003fe85efab514f3943cc800000000000080000000000000007ff000000000000000000000000000000000000000000000800000000000000000000000000000003ff0000000000000000000000000000080000000000000007ff800000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff80000000000003ff00000000000000000000000000000000000000000000000000000000000003ff8eb245cbee3a63cd8000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003ff8eb245cbee3a63cd8000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003fd16464f4a33f883cb80000000000003ff157bffca4a8bd3cd80000000000003ff00000000000007ff000000000000000000000000000000000000000000000000000000000000000000000000000003ff000000000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000000000000000000000fff8000000000000000000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000000000000000000000fff00000000000023ff000000000000000000000000000007ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff00000000000023ff000000000000000000000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f10c8942543fb04a6ece53d613000000000000000000000000000000003f8d3a1c1262a9093c680000000000003fb045aa083baf513c98000000000000bfa8410510668fa6bfc2e30a9e501b7d00000000000000000000000000000000bfa7c007b46da1483c88000000000000bfc2cacf890a0ae73ca80000000000003ff00000000000004039000000000000000000000000000000000000000000003b7a80b698a6350f38580000000000003ff00000000000003cd800000000000040390000000000003ff000000000000000000000000000000000000000000000bfac6afa54ac9dbf3c880000000000003fe88d37ba800a1d3cc80000000000003ff921fb54442d183e112e0be826d69500000000000000000000000000000000404e9dbd50d3393b3d2800000000000041cdcd64ffffffe03ea80000000000003ff00000000000003ff921fb54442d18000000000000000000000000000000003fb4d4350e9affe43c980000000000003ff088aea145b5e03cd8000000000000"
  let table6 String "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000008000000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000000000000000000000000000000000003fec34366179d4273cc000000000000000000000000000007ff000000000000000000000000000000000000000000000000000000000000000000000000000007ff0000000000000000000000000000000000000000000007ff800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000000000000000000000000000000000000080000000000000000000000000000000000000000000000000000000000000008000000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000008000000000000000000000000000000080000000000000003ff000000000000000000000000000000000000000000000800000000000000000000000000000003fec34366179d4273cc000000000000080000000000000007ff000000000000000000000000000000000000000000000800000000000000000000000000000007ff0000000000000000000000000000080000000000000007ff800000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff80000000000003ff00000000000000000000000000000000000000000000000000000000000003ff921fb54442d183cd0000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003ff921fb54442d183cd0000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003fe551d55bbb8ced3cc00000000000003ff0fafb8f2f147f3cd00000000000003ff00000000000007ff000000000000000000000000000000000000000000000000000000000000000000000000000007ff000000000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000003ff921fb54442d1800000000000000007ff000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000003ff921fb54442d180000000000000000fff000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000003ff921fb54442d1800000000000000007ff000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000003fe921fb54442d1800000000000000007ff000000000000000000000000000007ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000037ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000007ff000000000000000000000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f10c8942543fb04a6ece53d613000000000000000000000000000000003f8d4907baded06d3c600000000000003fb0480c7e2abef13c90000000000000bfa8410510668fa6bfc2e30a9e501b7d00000000000000000000000000000000bfa8009e56a9e15f3c80000000000000bfc2d6ed5bfd11263ca000000000000040000000000000003e112e0be826d695000000000000000000000000000000003ff921fb541c803e3cd00000000000003ff51242719804353cd00000000000003fe00000000000003e112e0be826d695000000000000000000000000000000003fe0c152382d73663cc00000000000003e13d66d3a8506d93af00000000000003ff00000000000003e112e0be826d695000000000000000000000000000000003ff921da2b9783ec3cd00000000000003f00945654a1d0d83be00000000000003e112e0be826d6953e112e0be826d695000000000000000000000000000000003e112e0be826d6953af00000000000003e112e0be826d6953af0000000000000"
  let table7 String "00000000000000000000000000000000000000000000000000000000000000003ff921fb54442d1800000000000000008000000000000000000000000000000000000000000000008000000000000000000000000000000000000000000000003ff921fb54442d1800000000000000000000000000000000000000000000000000000000000000003ff0000000000000000000000000000000000000000000003ff921fb54442d183cd0000000000000bfec34366179d4273cc000000000000000000000000000007ff0000000000000000000000000000000000000000000003ff921fb54442d180000000000000000fff0000000000000000000000000000000000000000000007ff8000000000000000000000000000000000000000000003ff921fb54442d1800000000000000000000000000000000fff800000000000080000000000000000000000000000000000000000000000000000000000000003ff921fb54442d1800000000000000008000000000000000000000000000000080000000000000008000000000000000000000000000000000000000000000003ff921fb54442d1800000000000000000000000000000000000000000000000080000000000000003ff0000000000000000000000000000000000000000000003ff921fb54442d183cd0000000000000bfec34366179d4273cc000000000000080000000000000007ff0000000000000000000000000000000000000000000003ff921fb54442d180000000000000000fff0000000000000000000000000000080000000000000007ff8000000000000000000000000000000000000000000003ff921fb54442d1800000000000000000000000000000000fff80000000000003ff000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000003ff000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003fecf2214ccccd443cc0000000000000bff0fafb8f2f147f3cd00000000000003ff00000000000007ff0000000000000000000000000000000000000000000003ff921fb54442d180000000000000000fff000000000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff000000000000000000000000000007ff0000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000007ff000000000000000000000000000007ff00000000000003ff00000000000000000000000000000000000000000000000000000000000000000000000000000fff000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000003fe921fb54442d180000000000000000fff000000000000000000000000000007ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000037ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff8000000000000fff000000000000000000000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f10c8942543fb04a6ece53d613000000000000000000000000000000003ff8e76944ce6f773cd0000000000000bfb0480c7e2abef13c90000000000000bfa8410510668fa6bfc2e30a9e501b7d000000000000000000000000000000003ff9e20046f97c233cd00000000000003fc2d6ed5bfd11263ca000000000000040000000000000003e112e0be826d695000000000000000000000000000000003e03d66d3a8506d93ae0000000000000bff51242719804353cd00000000000003fe00000000000003e112e0be826d695000000000000000000000000000000003ff0c152382d73663cd0000000000000be13d66d3a8506d93af00000000000003ff00000000000003e112e0be826d695000000000000000000000000000000003f0094565495f2a13be0000000000000bf00945654a1d0d83be00000000000003e112e0be826d6953e112e0be826d695000000000000000000000000000000003ff921fb53ff74e93cd0000000000000be112e0be826d6953af0000000000000"
  let table8 String "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000008000000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000000000000000000000000000000000007ff0000000000000000000000000000000000000000000007ff0000000000000000000000000000000000000000000003ff921fb54442d1800000000000000000000000000000000000000000000000000000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff8000000000000800000000000000000000000000000000000000000000000000000000000000080000000000000000000000000000000000000000000000000000000000000008000000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000008000000000000000000000000000000080000000000000003ff000000000000000000000000000000000000000000000800000000000000000000000000000007ff0000000000000000000000000000080000000000000007ff000000000000000000000000000000000000000000000bff921fb54442d1800000000000000000000000000000000000000000000000080000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003ff00000000000000000000000000000000000000000000000000000000000003fe921fb54442d183cc8000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003fe921fb54442d183cc8000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003ff0468a8ace4df63cd80000000000003fd9c041f7ed8d333cb80000000000003ff00000000000007ff0000000000000000000000000000000000000000000003ff921fb54442d180000000000000000000000000000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000003ff921fb54442d180000000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000003ff921fb54442d180000000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000003ff921fb54442d180000000000000000000000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000003ff921fb54442d180000000000000000000000000000000000000000000000007ff00000000000007ff8000000000000000000000000000000000000000000003ff921fb54442d1800000000000000000000000000000000fff00000000000027ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000000000000000000000000000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff8000000000000000000000000000000000000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f10c8942543fb04a6ece53d613000000000000000000000000000000003f8d75f557e562413c680000000000003fb04f368843e38f3c98000000000000bfa8410510668fa6bfc2e30a9e501b7d00000000000000000000000000000000bfa8c5ef5ad8132c3c88000000000000bfc2fb491ff7788b3ca80000000000003ff00000000000003e112e0be826d695000000000000000000000000000000003fe921fb54442d183cc80000000000003e012e0be826d6953ae80000000000003feffffffff241903e112e0be826d695000000000000000000000000000000003fe921fb543d4de03cc80000000000003e012e0be82e37873ae80000000000007e37e43c8800759c3ff0000000000000000000000000000000000000000000003ff921fb54442d183cd8000000000000000000000000000000000000000000063ff00000000000007e37e43c8800759c000000000000000000000000000000003ff921fb54442d183cd800000000000001a56e1fc2f8f359000000000c000000"
  let table9 String "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000008000000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000000000000000000000000000000000003feaed548f090cee3cc000000000000000000000000000007ff0000000000000000000000000000000000000000000000000000000000000fff00000000000020000000000000000fff800000000000000000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff00000000000020000000000000000fff8000000000000800000000000000000000000000000000000000000000000000000000000000080000000000000000000000000000000000000000000000000000000000000008000000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000008000000000000000000000000000000080000000000000003ff000000000000000000000000000000000000000000000800000000000000000000000000000003feaed548f090cee3cc000000000000080000000000000007ff0000000000000000000000000000000000000000000000000000000000000fff00000000000020000000000000000fff800000000000080000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff00000000000020000000000000000fff80000000000003ff00000000000000000000000000000000000000000000000000000000000003ff2cd9fc44eb9823cd0000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003ff2cd9fc44eb9823cd0000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003fe4519fd8047f923cc00000000000003ff4c67b74f6cc4f3cd00000000000003ff00000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000007ff00000000000000000000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000000000000000000000fff00000000000030000000000000000fff80000000000007ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff00000000000030000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000000000000000000000000000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f10c8942543fb04a6ece53d613000000000000000000000000000000003f8d48fe4ef72a413c600000000000003fb0480be706aad03c90000000000000bfa8410510668fa6bfc2e30a9e501b7d00000000000000000000000000000000bfa7ffd90a01a2f13c80000000000000bfc2d6ec0a2965c13ca00000000000004085e000000000003ff0000000000000000000000000000000000000000000007eeff6bc16ca21a27bc00000000000007ef8e3ed589698667bd000000000000040863000000000003ff0000000000000000000000000000000000000000000007fd57c636cf4f5f87cb00000000000007fe0bb2c7615833d7cc0000000000000c0872000000000004000000000000000000000000000000000000000000000007ff000000000000000000000000000007ff0000000000000000000000000000040862c00000000003fe0000000000000000000000000000000000000000000007fd52aba22deb5cc7cb00000000000007fc720873894974b7ca0000000000000"
  let table10 String "00000000000000000000000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000000000000000000000000000000000008000000000000000000000000000000000000000000000003ff000000000000000000000000000008000000000000000000000000000000000000000000000003ff0000000000000000000000000000000000000000000003fe14a280fb5068c3cc00000000000000000000000000000000000000000000000000000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff000000000000200000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff000000000000280000000000000000000000000000000000000000000000000000000000000003ff000000000000000000000000000008000000000000000000000000000000080000000000000008000000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000000000000000000080000000000000003ff0000000000000000000000000000000000000000000003fe14a280fb5068c3cc00000000000008000000000000000000000000000000080000000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff000000000000280000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000023ff00000000000000000000000000000000000000000000000000000000000003ff8b07551d9f5503cd0000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003ff8b07551d9f5503cd0000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003feaadea96f4359a3cc00000000000003fefa50ccd2ae8f33cc00000000000003ff00000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000007ff00000000000000000000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000000000000000000000fff00000000000030000000000000000fff80000000000007ff00000000000007ff8000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000027ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000027ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f10c8942543fb04a6ece53d613000000000000000000000000000000003feff0420b022b213cc00000000000003f4ddb8cb7a77f023c20000000000000bfa8410510668fa6bfc2e30a9e501b7d000000000000000000000000000000003fefb013913c5d543cc00000000000003f7c897a6e14bb643c500000000000004085e000000000003ff0000000000000000000000000000000000000000000007eeff6bc16ca21a27bc00000000000007ef8e3ed589698667bd000000000000040863000000000003ff0000000000000000000000000000000000000000000007fd57c636cf4f5f87cb00000000000007fe0bb2c7615833d7cc0000000000000c087200000000000400000000000000000000000000000000000000000000000fff00000000000000000000000000000fff0000000000000000000000000000040862c00000000003fe0000000000000000000000000000000000000000000007fd52aba22deb5cc7cb00000000000007fc720873894974b7ca0000000000000"
  let table11 String "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000008000000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000000000000000000000000000000000003ff8eb245cbee3a63cd800000000000000000000000000007ff000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff800000000000000000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff8000000000000800000000000000000000000000000000000000000000000000000000000000080000000000000000000000000000000000000000000000000000000000000008000000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000008000000000000000000000000000000080000000000000003ff000000000000000000000000000000000000000000000800000000000000000000000000000003ff8eb245cbee3a63cd800000000000080000000000000007ff000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff800000000000080000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003ff00000000000000000000000000000000000000000000000000000000000003fe85efab514f3943cc8000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003fe85efab514f3943cc8000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003ff157bffca4a8bd3cd80000000000003fd16464f4a33f883cb80000000000003ff00000000000007ff000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000003ff00000000000000000000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000003ff00000000000000000000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000003ff00000000000000000000000000000000000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff00000000000027ff00000000000007ff8000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff00000000000027ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000000000000000000000000000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f10c8942543fb04a6ece53d613000000000000000000000000000000003f8d75ebd4f0429c3c680000000000003fb04f35f1113d473c98000000000000bfa8410510668fa6bfc2e30a9e501b7d00000000000000000000000000000000bfa8c5221db395e53c88000000000000bfc2fb49317ed1343ca80000000000003ff00000000000004039000000000000000000000000000000000000000000003fe88d37ba800a1d3cc8000000000000bfac6afa54ac9dbf3c8800000000000040390000000000003ff0000000000000000000000000000000000000000000003ff00000000000003cd80000000000003b7a80b698a6350f38580000000000003ff921fb54442d183e112e0be826d695000000000000000000000000000000003fed594fdae482ba3cc80000000000003de5d463cec6ca2e3ac80000000000003ff00000000000003ff921fb54442d18000000000000000000000000000000003ff50231499b6b1d3cd80000000000003c898ed656361e273968000000000000"
  let table12 String "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000008000000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000000000000000000000000000000000003ff921fb54442d183cd000000000000000000000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000003ff921fb54442d18000000000000000000000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff8000000000000800000000000000000000000000000000000000000000000000000000000000080000000000000000000000000000000000000000000000000000000000000008000000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000008000000000000000000000000000000080000000000000003ff000000000000000000000000000000000000000000000800000000000000000000000000000003ff921fb54442d183cd000000000000080000000000000007ff000000000000000000000000000000000000000000000fff000000000000000000000000000003ff921fb54442d18000000000000000080000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003ff00000000000000000000000000000000000000000000000000000000000003fec34366179d4273cc0000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003fec34366179d4273cc0000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003ff0fafb8f2f147f3cd00000000000003fe551d55bbb8ced3cc00000000000003ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000003ff921fb54442d1800000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000007ff00000000000000000000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000003fe921fb54442d1800000000000000007ff00000000000007ff8000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000000000000000000000000000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff00000000000030000000000000000fff80000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f10c8942543fb04a6ece53d613000000000000000000000000000000003f8d66efa23e21e53c600000000000003fb04cd2729988443c90000000000000bfa8410510668fa6bfc2e30a9e501b7d00000000000000000000000000000000bfa8832da34e53f23c80000000000000bfc2ef29d3b17a0a3ca000000000000040000000000000003e112e0be826d695000000000000000000000000000000003ff719218313d0873cd00000000000003dfebb76fb6789ff3ad00000000000003fe00000000000003e112e0be826d695000000000000000000000000000000003fdecc2caec5160a3cb00000000000003e0ebb76fb6789ff3ae00000000000003ff00000000000003e112e0be826d695000000000000000000000000000000003fec34366179d4273cc00000000000003e084bc6eb0aa98a3ae00000000000003e112e0be826d6953e112e0be826d695000000000000000000000000000000003e112e0be826d6953af00000000000003e112e0be826d6953af0000000000000"
  let table13 String "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000003ff921fb54442d180000000000000000000000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000bff921fb54442d18000000000000000000000000000000003ff0000000000000000000000000000000000000000000003fec34366179d4273cc00000000000003ff921fb54442d183cd000000000000000000000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000003ff921fb54442d18000000000000000000000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000003ff921fb54442d1800000000000000008000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000003ff921fb54442d180000000000000000800000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000bff921fb54442d18000000000000000080000000000000003ff0000000000000000000000000000000000000000000003fec34366179d4273cc00000000000003ff921fb54442d183cd000000000000080000000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000003ff921fb54442d18000000000000000080000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000003ff921fb54442d1800000000000000003ff000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000003ff000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003ff0fafb8f2f147f3cd00000000000003fecf2214ccccd443cc00000000000003ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000003ff921fb54442d1800000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000007ff00000000000000000000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000003fe921fb54442d1800000000000000007ff00000000000007ff8000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff80000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f10c8942543fb04a6ece53d613000000000000000000000000000000003fb0480c7e2abef13c900000000000003ff8e76944ce6f773cd0000000000000bfa8410510668fa6bfc2e30a9e501b7d000000000000000000000000000000003fc2d6ed5bfd11263ca0000000000000bff9e20046f97c233cd000000000000040000000000000003e112e0be826d695000000000000000000000000000000003ff51242719804353cd00000000000003e03d66d3a8506d93ae00000000000003fe00000000000003e112e0be826d695000000000000000000000000000000003e13d66d3a8506d93af00000000000003ff0c152382d73663cd00000000000003ff00000000000003e112e0be826d695000000000000000000000000000000003f00945654a1d0d83be00000000000003f0094565495f2a13be00000000000003e112e0be826d6953e112e0be826d695000000000000000000000000000000003e112e0be826d6953af00000000000003ff921fb53ff74e93cd0000000000000"
  let table14 String "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000008000000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000000000000000000000000000000000003fe921fb54442d183cc000000000000000000000000000007ff000000000000000000000000000000000000000000000000000000000000000000000000000003ff921fb54442d18000000000000000000000000000000007ff800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000000000000000000000000000000000000080000000000000000000000000000000000000000000000000000000000000008000000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000008000000000000000000000000000000080000000000000003ff000000000000000000000000000000000000000000000800000000000000000000000000000003fe921fb54442d183cc000000000000080000000000000007ff000000000000000000000000000000000000000000000800000000000000000000000000000003ff921fb54442d18000000000000000080000000000000007ff800000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff80000000000003ff00000000000000000000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000007ff00000000000000000000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003fd9c041f7ed8d333cb00000000000003ff0468a8ace4df63cd00000000000003ff00000000000007ff000000000000000000000000000000000000000000000000000000000000000000000000000003ff921fb54442d1800000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000003ff921fb54442d1800000000000000007ff000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000bff921fb54442d1800000000000000007ff00000000000003ff000000000000000000000000000000000000000000000000000000000000000000000000000003ff921fb54442d1800000000000000007ff00000000000007ff000000000000000000000000000000000000000000000000000000000000000000000000000003ff921fb54442d1800000000000000007ff00000000000007ff800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff00000000000023ff921fb54442d1800000000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f10c8942543fb04a6ece53d613000000000000000000000000000000003f8d3a2576a899703c600000000000003fb045aa9f5a26f43c90000000000000bfa8410510668fa6bfc2e30a9e501b7d00000000000000000000000000000000bfa7c0ca676d37e73c80000000000000bfc2cad149342a4a3ca00000000000003ff00000000000003e112e0be826d6950000000000000000000000000000000040256a9a0b23d1883d000000000000003fe921fb546689303cc00000000000003feffffffff241903e112e0be826d6950000000000000000000000000000000040256953fdb3492f3d000000000000003fe789bd2a0567313cc00000000000007e37e43c8800759c3ff00000000000000000000000000000000000000000000001a56e1fc2f8f35900000000080000003ff921fb54442d183cd00000000000003ff00000000000007e37e43c8800759c00000000000000000000000000000000000000000000000000000000000000043ff921fb54442d183cd0000000000000"
  let table15 String "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000003ff00000000000000000000000000000000000000000000000000000000000000000000000000000bff0000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000000000000000000000fff0000000000000000000000000000000000000000000007ff800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000000000000000000000000000000000000080000000000000000000000000000000800000000000000000000000000000008000000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000000000000000000080000000000000003ff00000000000000000000000000000000000000000000080000000000000000000000000000000bff0000000000000000000000000000080000000000000007ff00000000000000000000000000000000000000000000080000000000000000000000000000000fff0000000000000000000000000000080000000000000007ff800000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff80000000000003ff00000000000000000000000000000000000000000000000000000000000003ff00000000000000000000000000000800000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003ff00000000000000000000000000000000000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003ff00000000000000000000000000000bff000000000000000000000000000003ff00000000000007ff0000000000000000000000000000000000000000000003ff00000000000000000000000000000fff000000000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000000000000000000000800000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000bff000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000fff000000000000000000000000000007ff00000000000007ff8000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff8000000000000000000000000000000000000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff8000000000000bff000000000000000000000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff8000000000000fff000000000000000000000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f10c8942543fb04a6ece53d613000000000000000000000000000000003f8d57f10c8942540000000000000000bfb04a6ece53d6130000000000000000bfa8410510668fa6bfc2e30a9e501b7d00000000000000000000000000000000bfa8410510668fa600000000000000003fc2e30a9e501b7d0000000000000000"
  let table16 String "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000008000000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000000000000000000000000000000000003ff0000000000000000000000000000000000000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000000000000000000000000000000000007ff800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000000000000000000000000000000000000080000000000000000000000000000000000000000000000000000000000000008000000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000008000000000000000000000000000000080000000000000003ff000000000000000000000000000000000000000000000800000000000000000000000000000003ff0000000000000000000000000000080000000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000000000000000000080000000000000007ff800000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff80000000000003ff00000000000000000000000000000000000000000000000000000000000003ff00000000000000000000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003ff00000000000000000000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003ff000000000000000000000000000003ff000000000000000000000000000003ff00000000000007ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000007ff00000000000000000000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000007ff8000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000027ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000000000000000000000000000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000003ff000000000000000000000000000007ff80000000000007ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f10c8942543fb04a6ece53d613000000000000000000000000000000003f8d57f10c89425400000000000000003fb04a6ece53d6130000000000000000bfa8410510668fa6bfc2e30a9e501b7d00000000000000000000000000000000bfa8410510668fa60000000000000000bfc2e30a9e501b7d0000000000000000"
  let table17 String "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000000fff00000000000010000000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000000fff000000000000100000000000000003ff0000000000000000000000000000000000000000000003ff00000000000003cb00000000000000000000000000000fff000000000000100000000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff000000000000100000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000000fff00000000000018000000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000010000000000000000fff000000000000180000000000000003ff0000000000000000000000000000000000000000000003ff00000000000003cb00000000000000000000000000000fff000000000000180000000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff000000000000180000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000013ff00000000000000000000000000000000000000000000000000000000000003ff00000000000003cb00000000000000000000000000000fff00000000000013ff00000000000008000000000000000000000000000000000000000000000003ff00000000000003cb00000000000000000000000000000fff00000000000013ff00000000000003ff0000000000000000000000000000000000000000000003ff6a09e667f3bcd3cb00000000000000000000000000000fff00000000000013ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000013ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff00000000000000000000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000008000000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000003ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000007ff8000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000013f8d57f10c8942543fb04a6ece53d613000000000000000000000000000000003fb0b2d5d9f2140f3c700000000000000000000000000000fff0000000000001bfa8410510668fa6bfc2e30a9e501b7d000000000000000000000000000000003fc3d61a26ec453f3c800000000000000000000000000000fff0000000000001400800000000000040100000000000000000000000000000000000000000000040140000000000003cd00000000000000000000000000000fff00000000000017e37e43c8800759c7e37e43c8800759c000000000000000000000000000000007e40e4d50f99b2117b000000000000000000000000000000fff000000000000101a56e1fc2f8f35901a56e1fc2f8f3590000000000000000000000000000000001ae4e8d1276222500000000020000000000000000000000fff00000000000010000000000000001000000000000000100000000000000000000000000000000000000000000000100000000000000010000000000000000fff0000000000001"
  let table18 String "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff00000000000010000000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff000000000000100000000000000003ff0000000000000000000000000000000000000000000003ff921fb54442d1800000000000000000000000000000000fff000000000000100000000000000007ff0000000000000000000000000000000000000000000003ff921fb54442d1800000000000000000000000000000000fff000000000000100000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000018000000000000000000000000000000000000000000000000000000000000000400921fb54442d1800000000000000000000000000000000fff00000000000018000000000000000800000000000000000000000000000000000000000000000c00921fb54442d1800000000000000000000000000000000fff000000000000180000000000000003ff0000000000000000000000000000000000000000000003ff921fb54442d1800000000000000000000000000000000fff000000000000180000000000000007ff0000000000000000000000000000000000000000000003ff921fb54442d1800000000000000000000000000000000fff000000000000180000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000013ff0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff00000000000013ff0000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff00000000000013ff00000000000003ff0000000000000000000000000000000000000000000003fe921fb54442d183ca00000000000000000000000000000fff00000000000013ff00000000000007ff0000000000000000000000000000000000000000000003ff921fb54442d1800000000000000000000000000000000fff00000000000013ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff00000000000017ff0000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff00000000000017ff00000000000003ff000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff00000000000017ff00000000000007ff0000000000000000000000000000000000000000000003fe921fb54442d1800000000000000000000000000000000fff00000000000017ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000013f8d57f10c8942543fb04a6ece53d613000000000000000000000000000000003ff596dfe3700c503cb00000000000000000000000000000fff0000000000001bfa8410510668fa6bfc2e30a9e501b7d00000000000000000000000000000000bffe1a65edbf1a833cb00000000000000000000000000000fff000000000000140080000000000004010000000000000000000000000000000000000000000003fedac670561bb4f3ca00000000000000000000000000000fff00000000000017e37e43c8800759c7e37e43c8800759c000000000000000000000000000000003fe921fb54442d183ca00000000000000000000000000000fff000000000000101a56e1fc2f8f35901a56e1fc2f8f359000000000000000000000000000000003fe921fb54442d183ca00000000000000000000000000000fff000000000000100000000000000010000000000000001000000000000000000000000000000003fe921fb54442d183ca00000000000000000000000000000fff0000000000001"
  let table19 String "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff00000000000010000000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff000000000000100000000000000003ff000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff000000000000100000000000000007ff000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff000000000000100000000000000007ff800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff00000000000018000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff00000000000018000000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff000000000000180000000000000003ff000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff000000000000180000000000000007ff000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff000000000000180000000000000007ff800000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff00000000000013ff00000000000000000000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff00000000000013ff00000000000008000000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff00000000000013ff00000000000003ff0000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff00000000000013ff00000000000007ff0000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff00000000000013ff00000000000007ff8000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000000000000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000008000000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000003ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000007ff8000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000013f8d57f10c8942543fb04a6ece53d613000000000000000000000000000000003f8d57f10c89425400000000000000000000000000000000fff0000000000001bfa8410510668fa6bfc2e30a9e501b7d00000000000000000000000000000000bfa8410510668fa600000000000000000000000000000000fff0000000000001"
  let table20 String "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff00000000000010000000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff000000000000100000000000000003ff0000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff000000000000100000000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff000000000000100000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000018000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff00000000000018000000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff000000000000180000000000000003ff0000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff000000000000180000000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff000000000000180000000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000013ff0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff00000000000013ff0000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff00000000000013ff00000000000003ff0000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff00000000000013ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000013ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff00000000000017ff0000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff00000000000017ff00000000000003ff0000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff8000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff00000000000017ff8000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff00000000000017ff80000000000003ff0000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff00000000000017ff80000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000013f8d57f10c8942543fb04a6ece53d613000000000000000000000000000000003fb04a6ece53d61300000000000000000000000000000000fff0000000000001bfa8410510668fa6bfc2e30a9e501b7d00000000000000000000000000000000bfc2e30a9e501b7d00000000000000000000000000000000fff0000000000001"
  let table21 String "3fc6e9039537afb63ff0f4b81f4aae4dbff000000000000000000000000000003fc3d5818ff6bb3e3cd0654aab388766bfed5bc36557060e3cd0654aab388766bfcb4121d2d157d8bfb3e0eb21801a473ff00000000000003ff0000000000000bff8fc9729f920b93cfb9f66b3c1b63a400aceb7da9246f43cfb9f66b3c1b63a3ffc7c49c74858cabfcc894d88bd52d100000000000000003ff00000000000003fee39f8c166e0483cd04ccef0f967d63fe4008c2b994d883cd04ccef0f967d63fd7a27a2c69bf0cbfdcea60fdc10a6b40000000000000000000000000000000bfb1582ba2159f453cbba36378c32dd4bfd55b46a71afb3f3cbba36378c32dd4400000000000000000000000000000003fd7a27a2c69bf0cbfdcea60fdc10a6b3ff3a98b5176bd453cd1972929bca8eebfd977ec6f59f41b3cd1972929bca8ee00000000000000003ff00000000000003ffc7c49c74858cabfcc894d88bd52d1bff55efdd3fe265c3ce0843fbad4fa083fdeb95d7e3194943ce0843fbad4fa083ff00000000000003ff0000000000000bfcb4121d2d157d8bfb3e0eb21801a473feeffcf0e4908663cc93b35d04d0462bfc86154c1e9e84f3cc93b35d04d0462bff000000000000000000000000000003fc6e9039537afb63ff0f4b81f4aae4d3f9f07e61001c86d3c8d3c09ee7c07113f938ded135e8a833c8d3c09ee7c07113ff00000000000003ff00000000000004000000000000000000000000000000080000000000000003ce2de2351256bb340000000000000003ce2de2351256bb33ff00000000000003ff00000000000003fe000000000000000000000000000003ff19435caffa9f93cd04ff119c036143fdd203138f6c8283cd04ff119c036143ff00000000000003ff000000000000000000000000000003ff00000000000003fdb71ef3767123d3cbc25c59fe218903fc3d2d66bf43e2c3cbc25c59fe218903ff00000000000003ff00000000000007ff000000000000000000000000000000000000000000000fff00000000000010000000000000000fff00000000000013ff00000000000003ff00000000000007ff800000000000000000000000000000000000000000000fff00000000000010000000000000000fff0000000000001400000000000000000000000000000004000000000000000000000000000000040100000000000003cf18b90bfbe8e7c00000000000000003cf18b90bfbe8e7c400000000000000000000000000000003fe000000000000000000000000000003ff6a09e667f3bcd3cd2ee5b3217186a00000000000000003cd2ee5b3217186a4000000000000000000000000000000000000000000000003ff00000000000003fe89d9ae6856a553ccd8b90bfbe8e7c3fe4725eeb25adec3ccd8b90bfbe8e7c400000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000010000000000000000fff0000000000001400000000000000000000000000000007ff800000000000000000000000000000000000000000000fff00000000000010000000000000000fff000000000000100000000000000003ff000000000000040000000000000000000000000000000bff00000000000003cd890fdaa22168c00000000000000003cd890fdaa22168c00000000000000003ff00000000000003fe000000000000000000000000000003fe6a09e667f3bcd3cce487ed5110b463fe6a09e667f3bcd3cce487ed5110b4600000000000000003ff000000000000000000000000000003ff00000000000003fca9bcc46f767df3cae67d5d454c4c400000000000000003cae67d5d454c4c400000000000000003ff00000000000007ff000000000000000000000000000000000000000000000fff00000000000010000000000000000fff000000000000100000000000000003ff00000000000007ff800000000000000000000000000000000000000000000fff00000000000010000000000000000fff0000000000001"
  let table22 String "3ff00000000000000000000000000000000000000000000000000000000000004005bf0a800000003eb0000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000004005bf0a800000003eb0000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003ff77fc5400000003ea000000000000040024c80e00000003eb00000000000003ff00000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000007ff00000000000000000000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000000000000000000000fff00000000000010000000000000000fff80000000000007ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff00000000000010000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000000000000000000000000000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f1000000003fb04a6ec0000000000000000000000000000000000000003ff032b3000000003ea00000000000003fb083c3000000003e60000000000000bfa8410520000000bfc2e30aa0000000000000000000000000000000000000003fee3016000000003e90000000000000bfc1f2a0400000003e700000000000004085e000000000003ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff0000000000000000000000000000040863000000000003ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff00000000000000000000000000000"
  let table23 String "3ff0000000000000000000000000000000000000000000000000000000000000000000000000000036b8000000000000000000000000000000000000000000003ff0000000000000800000000000000000000000000000000000000000000000000000000000000036b8000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003fd62e43000000003e780000000000003fe921fb600000003e880000000000003ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000003ff921fb6000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000007ff00000000000000000000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000003fe921fb6000000000000000000000007ff00000000000007ff8000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff80000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f1000000003fb04a6ec000000000000000000000000000000000000000c005d6bdc00000003ea80000000000003ff596dfe00000003e98000000000000bfa8410520000000bfc2e30aa000000000000000000000000000000000000000bffdd50d800000003e98000000000000bffe1a66000000003e980000000000003ff00000000000003e112e0be0000000000000000000000000000000000000003c22725dc00000003ac80000000000003e112e0be00000003cb80000000000003ff00000000000003c670ef5400000000000000000000000000000000000000038d09d878000000037780000000000003c670ef5400000003b08000000000000"
  let table24 String "3ff00000000000000000000000000000000000000000000000000000000000003ff00000000000003e98000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003ff00000000000003e98000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003ff19435c00000003e980000000000003fdd2031400000003e780000000000003ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff000000000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000007ff00000000000000000000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff000000000000000000000000000007ff00000000000007ff8000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff000000000000000000000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f1000000003fb04a6ec0000000000000000000000000000000000000003fc9876ac00000003e680000000000003fc46b8b600000003e68000000000000bfa8410520000000bfc2e30aa0000000000000000000000000000000000000003fcdb07e000000003e68000000000000bfd45b54000000003e78000000000000"
  let table25 String "3ff00000000000000000000000000000000000000000000000000000000000003feaed54800000003e94000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003feaed54800000003e94000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003ff4c67b800000003ea40000000000003fe4519fe00000003e940000000000003ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff000000000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000027ff00000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000027ff00000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000037ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000027ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000027ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000037ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f1000000003fb04a6ec0000000000000000000000000000000000000003f8d66e6200000003e340000000000003fb04cd1c00000003e64000000000000bfa8410520000000bfc2e30aa000000000000000000000000000000000000000bfa88263200000003e54000000000000bfc2ef29600000003e740000000000003ff00000000000004085e00000000000000000000000000000000000000000007ff000000000000000000000000000007ff000000000000000000000000000003ff00000000000004086300000000000000000000000000000000000000000007ff000000000000000000000000000007ff00000000000000000000000000000"
  let table26 String "3ff00000000000000000000000000000000000000000000000000000000000003fe14a28000000003e94000000000000800000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003fe14a28000000003e94000000000000000000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003feaadeaa00000003e94000000000000bfefa50cc00000003e940000000000003ff00000000000007ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000fff000000000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000027ff00000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000027ff00000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000007ff0000000000000000000000000000000000000000000000000000000000000fff00000000000030000000000000000fff80000000000007ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000027ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000027ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff80000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f1000000003fb04a6ec0000000000000000000000000000000000000003ff007e0000000003ea4000000000000bf4de559a00000003df4000000000000bfa8410520000000bfc2e30aa0000000000000000000000000000000000000003ff02806800000003ea4000000000000bf7cb930200000003e240000000000003ff00000000000004085e00000000000000000000000000000000000000000007ff00000000000000000000000000000fff000000000000000000000000000003ff00000000000004086300000000000000000000000000000000000000000007ff00000000000000000000000000000fff00000000000000000000000000000"
  let table27 String "3ff00000000000000000000000000000000000000000000000000000000000003ff8eb24600000003eac000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003ff8eb24600000003eac000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003fd16465000000003e8c0000000000003ff157c0000000003eac0000000000003ff00000000000007ff000000000000000000000000000000000000000000000000000000000000000000000000000003ff000000000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000000000000000000000fff8000000000000000000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000000000000000000000fff00000000000023ff000000000000000000000000000007ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff00000000000023ff000000000000000000000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f1000000003fb04a6ec0000000000000000000000000000000000000003f8d3a1c000000003e3c0000000000003fb045aa000000003e6c000000000000bfa8410520000000bfc2e30aa000000000000000000000000000000000000000bfa7c007c00000003e5c000000000000bfc2cacf800000003e7c0000000000003ff00000000000004039000000000000000000000000000000000000000000003b7a80b6a00000003a2c0000000000003ff00000000000003eac00000000000040390000000000003ff000000000000000000000000000000000000000000000bfac6afa600000003e5c0000000000003fe88d37c00000003e9c000000000000"
  let table28 String "3ff00000000000000000000000000000000000000000000000000000000000003ff921fb600000003ea4000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003ff921fb600000003ea4000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003fe551d5600000003e940000000000003ff0fafb800000003ea40000000000003ff00000000000007ff000000000000000000000000000000000000000000000000000000000000000000000000000007ff000000000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000003ff921fb6000000000000000000000007ff000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000003ff921fb600000000000000000000000fff000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000003ff921fb6000000000000000000000007ff000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000003fe921fb6000000000000000000000007ff000000000000000000000000000007ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000037ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000007ff000000000000000000000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f1000000003fb04a6ec0000000000000000000000000000000000000003f8d4907a00000003e340000000000003fb0480c600000003e64000000000000bfa8410520000000bfc2e30aa000000000000000000000000000000000000000bfa8009e600000003e54000000000000bfc2d6ed600000003e7400000000000040000000000000003e112e0be0000000000000000000000000000000000000003ff921fb600000003ea40000000000003ff51242800000003ea40000000000003fe00000000000003e112e0be0000000000000000000000000000000000000003fe0c152400000003e940000000000003e13d66d400000003cc4000000000000"
  let table29 String "3ff000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000003ff000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003fecf221400000003e94000000000000bff0fafb800000003ea40000000000003ff00000000000007ff0000000000000000000000000000000000000000000003ff921fb600000000000000000000000fff000000000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff000000000000000000000000000007ff0000000000000800000000000000000000000000000000000000000000000000000000000000000000000000000007ff000000000000000000000000000007ff00000000000003ff00000000000000000000000000000000000000000000000000000000000000000000000000000fff000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000003fe921fb600000000000000000000000fff000000000000000000000000000007ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000037ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff8000000000000fff000000000000000000000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f1000000003fb04a6ec0000000000000000000000000000000000000003ff8e769400000003ea4000000000000bfb0480c600000003e64000000000000bfa8410520000000bfc2e30aa0000000000000000000000000000000000000003ff9e200400000003ea40000000000003fc2d6ed600000003e7400000000000040000000000000003e112e0be0000000000000000000000000000000000000003e03d66d400000003cb4000000000000bff51242800000003ea40000000000003fe00000000000003e112e0be0000000000000000000000000000000000000003ff0c152400000003ea4000000000000be13d66d400000003cc4000000000000"
  let table30 String "3ff00000000000000000000000000000000000000000000000000000000000003fe921fb600000003e9c000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003fe921fb600000003e9c000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003ff0468a800000003eac0000000000003fd9c042000000003e8c0000000000003ff00000000000007ff0000000000000000000000000000000000000000000003ff921fb600000000000000000000000000000000000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000003ff921fb600000000000000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000003ff921fb600000000000000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000003ff921fb600000000000000000000000000000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000003ff921fb600000000000000000000000000000000000000000000000000000007ff00000000000007ff8000000000000000000000000000000000000000000003ff921fb6000000000000000000000000000000000000000fff00000000000027ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000000000000000000000000000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff8000000000000000000000000000000000000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f1000000003fb04a6ec0000000000000000000000000000000000000003f8d75f5400000003e3c0000000000003fb04f36800000003e6c000000000000bfa8410520000000bfc2e30aa000000000000000000000000000000000000000bfa8c5ef600000003e5c000000000000bfc2fb49200000003e7c0000000000003ff00000000000003e112e0be0000000000000000000000000000000000000003fe921fb600000003e9c0000000000003e012e0be00000003cbc0000000000003ff00000000000003e112e0be0000000000000000000000000000000000000003fe921fb600000003e9c0000000000003e012e0be00000003cbc000000000000"
  let table31 String "3ff00000000000000000000000000000000000000000000000000000000000003ff2cd9fc00000003ea4000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003ff2cd9fc00000003ea4000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003fe4519fe00000003e940000000000003ff4c67b800000003ea40000000000003ff00000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000007ff00000000000000000000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000000000000000000000fff00000000000030000000000000000fff80000000000007ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff00000000000030000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000000000000000000000000000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f1000000003fb04a6ec0000000000000000000000000000000000000003f8d48fe400000003e340000000000003fb0480be00000003e64000000000000bfa8410520000000bfc2e30aa000000000000000000000000000000000000000bfa7ffd9200000003e54000000000000bfc2d6ec000000003e740000000000004085e000000000003ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff0000000000000000000000000000040863000000000003ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff00000000000000000000000000000"
  let table32 String "3ff00000000000000000000000000000000000000000000000000000000000003ff8b075600000003ea4000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003ff8b075600000003ea4000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003feaadeaa00000003e940000000000003fefa50cc00000003e940000000000003ff00000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000007ff00000000000000000000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000000000000000000000fff00000000000030000000000000000fff80000000000007ff00000000000007ff8000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000027ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000027ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f1000000003fb04a6ec0000000000000000000000000000000000000003feff042000000003e940000000000003f4ddb8ca00000003df4000000000000bfa8410520000000bfc2e30aa0000000000000000000000000000000000000003fefb013a00000003e940000000000003f7c897a800000003e240000000000004085e000000000003ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff0000000000000000000000000000040863000000000003ff0000000000000000000000000000000000000000000007ff000000000000000000000000000007ff00000000000000000000000000000"
  let table33 String "3ff00000000000000000000000000000000000000000000000000000000000003fe85efac00000003e9c000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003fe85efac00000003e9c000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003ff157c0000000003eac0000000000003fd16465000000003e8c0000000000003ff00000000000007ff000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000003ff00000000000000000000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000003ff00000000000000000000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000003ff00000000000000000000000000000000000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff00000000000027ff00000000000007ff8000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff00000000000027ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000000000000000000000000000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f1000000003fb04a6ec0000000000000000000000000000000000000003f8d75ebc00000003e3c0000000000003fb04f35e00000003e6c000000000000bfa8410520000000bfc2e30aa000000000000000000000000000000000000000bfa8c522200000003e5c000000000000bfc2fb49400000003e7c0000000000003ff00000000000004039000000000000000000000000000000000000000000003fe88d37c00000003e9c000000000000bfac6afa600000003e5c00000000000040390000000000003ff0000000000000000000000000000000000000000000003ff00000000000003eac0000000000003b7a80b6a00000003a2c000000000000"
  let table34 String "3ff00000000000000000000000000000000000000000000000000000000000003fec3436600000003e94000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003fec3436600000003e94000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003ff0fafb800000003ea40000000000003fe551d5600000003e940000000000003ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000003ff921fb6000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000007ff00000000000000000000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000003fe921fb6000000000000000000000007ff00000000000007ff8000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000000000000000000000000000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff00000000000030000000000000000fff80000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f1000000003fb04a6ec0000000000000000000000000000000000000003f8d66efa00000003e340000000000003fb04cd2600000003e64000000000000bfa8410520000000bfc2e30aa000000000000000000000000000000000000000bfa8832dc00000003e54000000000000bfc2ef29e00000003e7400000000000040000000000000003e112e0be0000000000000000000000000000000000000003ff71921800000003ea40000000000003dfebb76e00000003ca40000000000003fe00000000000003e112e0be0000000000000000000000000000000000000003fdecc2ca00000003e840000000000003e0ebb76e00000003cb4000000000000"
  let table35 String "3ff000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000003ff000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003ff0fafb800000003ea40000000000003fecf221400000003e940000000000003ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000003ff921fb6000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000007ff00000000000000000000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000003fe921fb6000000000000000000000007ff00000000000007ff8000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff80000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f1000000003fb04a6ec0000000000000000000000000000000000000003fb0480c600000003e640000000000003ff8e769400000003ea4000000000000bfa8410520000000bfc2e30aa0000000000000000000000000000000000000003fc2d6ed600000003e74000000000000bff9e200400000003ea400000000000040000000000000003e112e0be0000000000000000000000000000000000000003ff51242800000003ea40000000000003e03d66d400000003cb40000000000003fe00000000000003e112e0be0000000000000000000000000000000000000003e13d66d400000003cc40000000000003ff0c152400000003ea4000000000000"
  let table36 String "3ff00000000000000000000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000007ff00000000000000000000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003fd9c042000000003e840000000000003ff0468a800000003ea40000000000003ff00000000000007ff000000000000000000000000000000000000000000000000000000000000000000000000000003ff921fb6000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000003ff921fb6000000000000000000000007ff000000000000080000000000000000000000000000000000000000000000000000000000000000000000000000000bff921fb6000000000000000000000007ff00000000000003ff000000000000000000000000000000000000000000000000000000000000000000000000000003ff921fb6000000000000000000000007ff00000000000007ff000000000000000000000000000000000000000000000000000000000000000000000000000003ff921fb6000000000000000000000007ff00000000000007ff800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff00000000000023ff921fb6000000000000000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f1000000003fb04a6ec0000000000000000000000000000000000000003f8d3a25600000003e340000000000003fb045aaa00000003e64000000000000bfa8410520000000bfc2e30aa000000000000000000000000000000000000000bfa7c0ca800000003e54000000000000bfc2cad1400000003e740000000000003ff00000000000003e112e0be00000000000000000000000000000000000000040256a9a000000003ed40000000000003fe921fb600000003e940000000000003ff00000000000003e112e0be00000000000000000000000000000000000000040256a9a000000003ed40000000000003fe921fb600000003e94000000000000"
  let table37 String "3ff00000000000000000000000000000000000000000000000000000000000003ff00000000000000000000000000000800000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003ff00000000000000000000000000000000000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003ff00000000000000000000000000000bff000000000000000000000000000003ff00000000000007ff0000000000000000000000000000000000000000000003ff00000000000000000000000000000fff000000000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000000000000000000000800000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000bff000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000fff000000000000000000000000000007ff00000000000007ff8000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff80000000000007ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff8000000000000000000000000000000000000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff8000000000000bff000000000000000000000000000007ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff8000000000000fff000000000000000000000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f1000000003fb04a6ec0000000000000000000000000000000000000003f8d57f1000000000000000000000000bfb04a6ec00000000000000000000000bfa8410520000000bfc2e30aa000000000000000000000000000000000000000bfa841052000000000000000000000003fc2e30aa00000000000000000000000"
  let table38 String "3ff00000000000000000000000000000000000000000000000000000000000003ff00000000000000000000000000000000000000000000000000000000000003ff00000000000008000000000000000000000000000000000000000000000003ff00000000000000000000000000000800000000000000000000000000000003ff00000000000003ff0000000000000000000000000000000000000000000003ff000000000000000000000000000003ff000000000000000000000000000003ff00000000000007ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000003ff00000000000007ff8000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff80000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000008000000000000000000000000000000000000000000000007ff00000000000000000000000000000800000000000000000000000000000007ff00000000000003ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000007ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff00000000000007ff8000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000027ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff8000000000000000000000000000000000000000000007ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff8000000000000800000000000000000000000000000007ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000003ff000000000000000000000000000007ff80000000000007ff0000000000000000000000000000000000000000000007ff00000000000000000000000000000000000000000000000000000000000007ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff80000000000003f8d57f1000000003fb04a6ec0000000000000000000000000000000000000003f8d57f10000000000000000000000003fb04a6ec00000000000000000000000bfa8410520000000bfc2e30aa000000000000000000000000000000000000000bfa84105200000000000000000000000bfc2e30aa00000000000000000000000"
  let table39 String "3ff00000000000000000000000000000000000000000000000000000000000003ff00000000000003e900000000000000000000000000000fff00000000000013ff00000000000008000000000000000000000000000000000000000000000003ff00000000000003e900000000000000000000000000000fff00000000000013ff00000000000003ff0000000000000000000000000000000000000000000003ff6a09e600000003e900000000000000000000000000000fff00000000000013ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000013ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff00000000000000000000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000008000000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000003ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000007ff8000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000013f8d57f1000000003fb04a6ec0000000000000000000000000000000000000003fb0b2d5c00000003e500000000000000000000000000000fff0000000000001bfa8410520000000bfc2e30aa0000000000000000000000000000000000000003fc3d61a200000003e600000000000000000000000000000fff0000000000001400800000000000040100000000000000000000000000000000000000000000040140000000000003eb00000000000000000000000000000fff0000000000001"
  let table40 String "3ff0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff00000000000013ff0000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff00000000000013ff00000000000003ff0000000000000000000000000000000000000000000003fe921fb600000003e800000000000000000000000000000fff00000000000013ff00000000000007ff0000000000000000000000000000000000000000000003ff921fb6000000000000000000000000000000000000000fff00000000000013ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff00000000000017ff0000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff00000000000017ff00000000000003ff000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff00000000000017ff00000000000007ff0000000000000000000000000000000000000000000003fe921fb6000000000000000000000000000000000000000fff00000000000017ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000013f8d57f1000000003fb04a6ec0000000000000000000000000000000000000003ff596dfe00000003e900000000000000000000000000000fff0000000000001bfa8410520000000bfc2e30aa000000000000000000000000000000000000000bffe1a66000000003e900000000000000000000000000000fff000000000000140080000000000004010000000000000000000000000000000000000000000003fedac67000000003e800000000000000000000000000000fff0000000000001"
  let table41 String "3ff00000000000000000000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff00000000000013ff00000000000008000000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff00000000000013ff00000000000003ff0000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff00000000000013ff00000000000007ff0000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff00000000000013ff00000000000007ff8000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000000000000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000008000000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000003ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000007ff8000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff80000000000000000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000008000000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000003ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000007ff0000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000013f8d57f1000000003fb04a6ec0000000000000000000000000000000000000003f8d57f10000000000000000000000000000000000000000fff0000000000001bfa8410520000000bfc2e30aa000000000000000000000000000000000000000bfa841052000000000000000000000000000000000000000fff0000000000001"
  let table42 String "3ff0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff00000000000013ff0000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff00000000000013ff00000000000003ff0000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff00000000000013ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000013ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff00000000000017ff0000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff00000000000017ff00000000000003ff0000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff00000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000017ff8000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000fff00000000000017ff8000000000000800000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000fff00000000000017ff80000000000003ff0000000000000000000000000000000000000000000003ff000000000000000000000000000000000000000000000fff00000000000017ff80000000000007ff0000000000000000000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000017ff80000000000007ff8000000000000000000000000000000000000000000000000000000000000fff80000000000000000000000000000fff00000000000013f8d57f1000000003fb04a6ec0000000000000000000000000000000000000003fb04a6ec000000000000000000000000000000000000000fff0000000000001bfa8410520000000bfc2e30aa000000000000000000000000000000000000000bfc2e30aa000000000000000000000000000000000000000fff0000000000001"
  let table43 String "3fc6e9039537afb63ff0f4b81f4aae4dbff000000000000000000000000000003fc3d581800000003ea0654aab388766bfed5bc3600000003ea0654aab388766bfcb4121d2d157d8bfb3e0eb21801a473ff00000000000003ff0000000000000bff8fc97200000003ecb9f66b3c1b63a400aceb7e00000003ecb9f66b3c1b63a3ffc7c49c74858cabfcc894d88bd52d100000000000000003ff00000000000003fee39f8c00000003ea04ccef0f967d63fe4008c200000003ea04ccef0f967d63fd7a27a2c69bf0cbfdcea60fdc10a6b40000000000000000000000000000000bfb1582ba00000003e8ba36378c32dd4bfd55b46a00000003e8ba36378c32dd4400000000000000000000000000000003fd7a27a2c69bf0cbfdcea60fdc10a6b3ff3a98b600000003ea1972929bca8eebfd977ec600000003ea1972929bca8ee00000000000000003ff00000000000003ffc7c49c74858cabfcc894d88bd52d1bff55efde00000003eb0843fbad4fa083fdeb95d800000003eb0843fbad4fa083ff00000000000003ff0000000000000bfcb4121d2d157d8bfb3e0eb21801a473feeffcf000000003e993b35d04d0462bfc86154c00000003e993b35d04d0462bff000000000000000000000000000003fc6e9039537afb63ff0f4b81f4aae4d3f9f07e6200000003e5d3c09ee7c07113f938ded200000003e5d3c09ee7c07113ff00000000000003ff00000000000004000000000000000000000000000000080000000000000003eb2de2351256bb340000000000000003eb2de2351256bb33ff00000000000003ff00000000000003fe000000000000000000000000000003ff19435c00000003ea04ff119c036143fdd2031400000003ea04ff119c036143ff00000000000003ff000000000000000000000000000003ff00000000000003fdb71ef400000003e8c25c59fe218903fc3d2d6600000003e8c25c59fe218903ff00000000000003ff00000000000007ff000000000000000000000000000000000000000000000fff00000000000010000000000000000fff00000000000013ff00000000000003ff00000000000007ff800000000000000000000000000000000000000000000fff00000000000010000000000000000fff0000000000001400000000000000000000000000000004000000000000000000000000000000040100000000000003ec18b90bfbe8e7c00000000000000003ec18b90bfbe8e7c400000000000000000000000000000003fe000000000000000000000000000003ff6a09e600000003ea2ee5b3217186a00000000000000003ea2ee5b3217186a4000000000000000000000000000000000000000000000003ff00000000000003fe89d9ae00000003e9d8b90bfbe8e7c3fe4725ee00000003e9d8b90bfbe8e7c400000000000000000000000000000007ff000000000000000000000000000000000000000000000fff00000000000010000000000000000fff0000000000001400000000000000000000000000000007ff800000000000000000000000000000000000000000000fff00000000000010000000000000000fff000000000000100000000000000003ff000000000000040000000000000000000000000000000bff00000000000003ea890fdaa22168c00000000000000003ea890fdaa22168c00000000000000003ff00000000000003fe000000000000000000000000000003fe6a09e600000003e9e487ed5110b463fe6a09e600000003e9e487ed5110b4600000000000000003ff000000000000000000000000000003ff00000000000003fca9bcc400000003e7e67d5d454c4c400000000000000003e7e67d5d454c4c400000000000000003ff00000000000007ff000000000000000000000000000000000000000000000fff00000000000010000000000000000fff000000000000100000000000000003ff00000000000007ff800000000000000000000000000000000000000000000fff00000000000010000000000000000fff0000000000001"
:begin
  failed0 = checkTable(table0, 31, 0)
  expectcexp: test.assertEqualInt64(0, failed0)
  probe0 = Complex.new(1.0, 0.5)
  direct0 = complexExponential(probe0)
  failed1 = checkTable(table1, 31, 1)
  expectclog: test.assertEqualInt64(0, failed1)
  probe1 = Complex.new(1.0, 0.5)
  direct1 = complexLogarithm(probe1)
  failed2 = checkTable(table2, 31, 2)
  expectcsqrt: test.assertEqualInt64(0, failed2)
  probe2 = Complex.new(1.0, 0.5)
  direct2 = complexSquareRoot(probe2)
  failed3 = checkTable(table3, 30, 3)
  expectcsin: test.assertEqualInt64(0, failed3)
  probe3 = Complex.new(1.0, 0.5)
  direct3 = complexSine(probe3)
  failed4 = checkTable(table4, 30, 4)
  expectccos: test.assertEqualInt64(0, failed4)
  probe4 = Complex.new(1.0, 0.5)
  direct4 = complexCosine(probe4)
  failed5 = checkTable(table5, 31, 5)
  expectctan: test.assertEqualInt64(0, failed5)
  probe5 = Complex.new(1.0, 0.5)
  direct5 = complexTangent(probe5)
  failed6 = checkTable(table6, 31, 6)
  expectcasin: test.assertEqualInt64(0, failed6)
  probe6 = Complex.new(1.0, 0.5)
  direct6 = complexInverseSine(probe6)
  failed7 = checkTable(table7, 31, 7)
  expectcacos: test.assertEqualInt64(0, failed7)
  probe7 = Complex.new(1.0, 0.5)
  direct7 = complexInverseCosine(probe7)
  failed8 = checkTable(table8, 31, 8)
  expectcatan: test.assertEqualInt64(0, failed8)
  probe8 = Complex.new(1.0, 0.5)
  direct8 = complexInverseTangent(probe8)
  failed9 = checkTable(table9, 31, 9)
  expectcsinh: test.assertEqualInt64(0, failed9)
  probe9 = Complex.new(1.0, 0.5)
  direct9 = complexHyperbolicSine(probe9)
  failed10 = checkTable(table10, 31, 10)
  expectccosh: test.assertEqualInt64(0, failed10)
  probe10 = Complex.new(1.0, 0.5)
  direct10 = complexHyperbolicCosine(probe10)
  failed11 = checkTable(table11, 31, 11)
  expectctanh: test.assertEqualInt64(0, failed11)
  probe11 = Complex.new(1.0, 0.5)
  direct11 = complexHyperbolicTangent(probe11)
  failed12 = checkTable(table12, 31, 12)
  expectcasinh: test.assertEqualInt64(0, failed12)
  probe12 = Complex.new(1.0, 0.5)
  direct12 = complexInverseHyperbolicSine(probe12)
  failed13 = checkTable(table13, 31, 13)
  expectcacosh: test.assertEqualInt64(0, failed13)
  probe13 = Complex.new(1.0, 0.5)
  direct13 = complexInverseHyperbolicCosine(probe13)
  failed14 = checkTable(table14, 31, 14)
  expectcatanh: test.assertEqualInt64(0, failed14)
  probe14 = Complex.new(1.0, 0.5)
  direct14 = complexInverseHyperbolicTangent(probe14)
  failed15 = checkTable(table15, 27, 15)
  expectconj: test.assertEqualInt64(0, failed15)
  probe15 = Complex.new(1.0, 0.5)
  direct15 = complexConjugate(probe15)
  failed16 = checkTable(table16, 27, 16)
  expectcproj: test.assertEqualInt64(0, failed16)
  probe16 = Complex.new(1.0, 0.5)
  direct16 = complexProjection(probe16)
  failed17 = checkTable(table17, 31, 17)
  expectcabs: test.assertEqualInt64(0, failed17)
  probe17 = Complex.new(1.0, 0.5)
  direct17 = complexMagnitude(probe17)
  failed18 = checkTable(table18, 31, 18)
  expectcarg: test.assertEqualInt64(0, failed18)
  probe18 = Complex.new(1.0, 0.5)
  direct18 = complexArgument(probe18)
  failed19 = checkTable(table19, 27, 19)
  expectcreal: test.assertEqualInt64(0, failed19)
  probe19 = Complex.new(1.0, 0.5)
  direct19 = complexRealPart(probe19)
  failed20 = checkTable(table20, 27, 20)
  expectcimag: test.assertEqualInt64(0, failed20)
  probe20 = Complex.new(1.0, 0.5)
  direct20 = complexImaginaryPart(probe20)
  failed21 = checkTable(table21, 23, 21)
  expectcpow: test.assertEqualInt64(0, failed21)
  probe21 = Complex.new(1.0, 0.5)
  direct21 = complexPower(probe21, probe21)
  failed22 = checkTable(table22, 19, 22)
  expectcexpf: test.assertEqualInt64(0, failed22)
  probe22 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct22 = complexExponentialSingle(probe22)
  failed23 = checkTable(table23, 19, 23)
  expectclogf: test.assertEqualInt64(0, failed23)
  probe23 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct23 = complexLogarithmSingle(probe23)
  failed24 = checkTable(table24, 17, 24)
  expectcsqrtf: test.assertEqualInt64(0, failed24)
  probe24 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct24 = complexSquareRootSingle(probe24)
  failed25 = checkTable(table25, 19, 25)
  expectcsinf: test.assertEqualInt64(0, failed25)
  probe25 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct25 = complexSineSingle(probe25)
  failed26 = checkTable(table26, 19, 26)
  expectccosf: test.assertEqualInt64(0, failed26)
  probe26 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct26 = complexCosineSingle(probe26)
  failed27 = checkTable(table27, 19, 27)
  expectctanf: test.assertEqualInt64(0, failed27)
  probe27 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct27 = complexTangentSingle(probe27)
  failed28 = checkTable(table28, 19, 28)
  expectcasinf: test.assertEqualInt64(0, failed28)
  probe28 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct28 = complexInverseSineSingle(probe28)
  failed29 = checkTable(table29, 19, 29)
  expectcacosf: test.assertEqualInt64(0, failed29)
  probe29 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct29 = complexInverseCosineSingle(probe29)
  failed30 = checkTable(table30, 19, 30)
  expectcatanf: test.assertEqualInt64(0, failed30)
  probe30 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct30 = complexInverseTangentSingle(probe30)
  failed31 = checkTable(table31, 19, 31)
  expectcsinhf: test.assertEqualInt64(0, failed31)
  probe31 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct31 = complexHyperbolicSineSingle(probe31)
  failed32 = checkTable(table32, 19, 32)
  expectccoshf: test.assertEqualInt64(0, failed32)
  probe32 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct32 = complexHyperbolicCosineSingle(probe32)
  failed33 = checkTable(table33, 19, 33)
  expectctanhf: test.assertEqualInt64(0, failed33)
  probe33 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct33 = complexHyperbolicTangentSingle(probe33)
  failed34 = checkTable(table34, 19, 34)
  expectcasinhf: test.assertEqualInt64(0, failed34)
  probe34 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct34 = complexInverseHyperbolicSineSingle(probe34)
  failed35 = checkTable(table35, 19, 35)
  expectcacoshf: test.assertEqualInt64(0, failed35)
  probe35 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct35 = complexInverseHyperbolicCosineSingle(probe35)
  failed36 = checkTable(table36, 19, 36)
  expectcatanhf: test.assertEqualInt64(0, failed36)
  probe36 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct36 = complexInverseHyperbolicTangentSingle(probe36)
  failed37 = checkTable(table37, 17, 37)
  expectconjf: test.assertEqualInt64(0, failed37)
  probe37 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct37 = complexConjugateSingle(probe37)
  failed38 = checkTable(table38, 17, 38)
  expectcprojf: test.assertEqualInt64(0, failed38)
  probe38 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct38 = complexProjectionSingle(probe38)
  failed39 = checkTable(table39, 18, 39)
  expectcabsf: test.assertEqualInt64(0, failed39)
  probe39 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct39 = complexMagnitudeSingle(probe39)
  failed40 = checkTable(table40, 18, 40)
  expectcargf: test.assertEqualInt64(0, failed40)
  probe40 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct40 = complexArgumentSingle(probe40)
  failed41 = checkTable(table41, 17, 41)
  expectcrealf: test.assertEqualInt64(0, failed41)
  probe41 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct41 = complexRealPartSingle(probe41)
  failed42 = checkTable(table42, 17, 42)
  expectcimagf: test.assertEqualInt64(0, failed42)
  probe42 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct42 = complexImaginaryPartSingle(probe42)
  failed43 = checkTable(table43, 23, 43)
  expectcpowf: test.assertEqualInt64(0, failed43)
  probe43 = ComplexSingle.new(convert.float64ToFloat32(1.0), convert.float64ToFloat32(0.5))
  direct43 = complexPowerSingle(probe43, probe43)
  return
## @end tests
