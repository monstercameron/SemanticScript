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
