"""The generated blocks of cmathcomplex.dsl, and an exact reference for complex.h (D-153, D-175).

`python cmathcomplexgen.py` rewrites the blocks between `## @generated <name>` and `## @end <name>` lines of
tools/cmathcomplex.dsl: the sinh polynomial (exact Taylor coefficients in fractions, rounded once), the `abi library`
wrappers (one operation per C name, double and float), and the unit tests. tools/build.py then writes cmathcomplex.sem.

The reference (`ref(name, x, y)`) gives the exact value of a function at a pair of finite doubles to about 100 digits, in
decimals: the exponential, logarithm, sine, cosine and arctangent of cmathtriggen's decimal code, and complex
arithmetic here. A zero part of an argument is replaced by +-1e-120 of its sign (so that the sign of a zero picks the
side of a branch cut), and a part of the value that comes out below 1e-90 is a zero with the sign it has. The special
values (infinities, NaN, signed zeros) are Annex G's, written in `special`; a case it leaves open is "any".
"""
from __future__ import annotations

import math
import os
import re
import struct
import sys
from decimal import Decimal, getcontext
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmathtriggen as T  # noqa: E402

INF = math.inf
NAN = math.nan
PI = math.pi
PI2 = math.pi / 2
PI4 = math.pi / 4
PI34 = 3 * math.pi / 4

# ---------------------------------------------------------------- the C names

UNARY = [  # (C name, parts operation, op name, purpose)
    ("cexp", "exponentialParts", "complexExponential", "e to the power z"),
    ("clog", "logarithmParts", "complexLogarithm", "the natural logarithm, with the imaginary part in -pi to pi"),
    ("csqrt", "squareRootParts", "complexSquareRoot", "the square root with a non-negative real part"),
    ("csin", "sineParts", "complexSine", "the sine"),
    ("ccos", "cosineParts", "complexCosine", "the cosine"),
    ("ctan", "tangentParts", "complexTangent", "the tangent"),
    ("casin", "inverseSineParts", "complexInverseSine", "the arc sine"),
    ("cacos", "inverseCosineParts", "complexInverseCosine", "the arc cosine"),
    ("catan", "inverseTangentParts", "complexInverseTangent", "the arc tangent"),
    ("csinh", "hyperbolicSineParts", "complexHyperbolicSine", "the hyperbolic sine"),
    ("ccosh", "hyperbolicCosineParts", "complexHyperbolicCosine", "the hyperbolic cosine"),
    ("ctanh", "hyperbolicTangentParts", "complexHyperbolicTangent", "the hyperbolic tangent"),
    ("casinh", "inverseHyperbolicSineParts", "complexInverseHyperbolicSine", "the inverse hyperbolic sine"),
    ("cacosh", "inverseHyperbolicCosineParts", "complexInverseHyperbolicCosine", "the inverse hyperbolic cosine"),
    ("catanh", "inverseHyperbolicTangentParts", "complexInverseHyperbolicTangent", "the inverse hyperbolic tangent"),
    ("conj", "conjugateParts", "complexConjugate", "the complex conjugate"),
    ("cproj", "projectionParts", "complexProjection", "the projection onto the Riemann sphere"),
]
REALS = [  # (C name, parts operation, op name, purpose, how a part is shown)
    ("cabs", "magnitudeOf", "complexMagnitude", "the magnitude hypot(x, y)"),
    ("carg", "argumentOf", "complexArgument", "the argument atan2(y, x)"),
    ("creal", "realPartOf", "complexRealPart", "the real part"),
    ("cimag", "imaginaryPartOf", "complexImaginaryPart", "the imaginary part"),
]
BINARY = [("cpow", "powerParts", "complexPower", "x to the power y, as cexp(y clog x)")]
NAMES = [n for n, *_ in UNARY] + [n for n, *_ in REALS] + [n for n, *_ in BINARY]
ALL_NAMES = NAMES + [n + "f" for n in NAMES]


def hexf(x: float) -> str:
    return float(x).hex()


# ---------------------------------------------------------------- blocks of the DSL


def polynomials() -> str:
    coeffs = [float(Fraction(1, math.factorial(2 * k + 1))) for k in range(1, 12)]
    expr = hexf(coeffs[-1])
    for c in reversed(coeffs[:-1]):
        expr = f"({expr}) * z + {hexf(c)}"
    return (f'op sinhPoly "The Taylor coefficients of sinh past x, in z = x*x: 1/3! + z/5! + ... to x^23 (exact 1/k! rounded to doubles)"\n'
            f"  input z Float64 copied\n  output Float64\n:begin\n  calc value = {expr}\n  return value\n")


def _read(parts: str, args: str) -> str:
    return parts


def _wrapper(cname: str, parts: str, op: str, purpose: str, kind: str, single: bool) -> str:
    """One `abi library` operation. kind: unary (complex to complex), real (complex to real), binary."""
    cn = cname + ("f" if single else "")
    opname = op + ("Single" if single else "")
    rec = "ComplexSingle" if single else "Complex"
    scalar = "Float32" if single else "Float64"
    kindword = "float complex" if single else "double complex"
    lines = [f'op {opname} "{cn}: {purpose}, for a {kindword}' + (" (computed in double, each part rounded once)" if single else "") + '"']
    lines.append(f'  invariant gives{cn[0].upper()}{cn[1:]} "Gives {cn}, within the module\'s stated bound, with Annex G\'s special values"')
    nargs = 2 if kind == "binary" else 1
    names = ["z", "w"][:nargs]
    for n in names:
        lines.append(f"  input {n} {rec} copied")
    lines.append(f"  output {scalar if kind == 'real' else rec}")
    lines += ["  effect use machine.memory", "  uses memoryAccess", f'  abi library "{cn}"', ":begin"]
    args = []
    for n in names:
        if single:
            lines.append(f"  {n}RealSingle = ComplexSingle.real({n})")
            lines.append(f"  {n}ImagSingle = ComplexSingle.imag({n})")
            lines.append(f"  calc {n}Re = convert.float32ToFloat64({n}RealSingle)")
            lines.append(f"  calc {n}Im = convert.float32ToFloat64({n}ImagSingle)")
        else:
            lines.append(f"  {n}Re = Complex.real({n})")
            lines.append(f"  {n}Im = Complex.imag({n})")
        args += [f"{n}Re", f"{n}Im"]
    lines.append("  saved = keepErrno()")
    if kind == "real":
        lines.append(f"  wide = {parts}({', '.join(args)})")
    else:
        lines.append(f"  wide = {parts}({', '.join(args)})")
    lines.append("  restoreErrno(saved)")
    if kind == "real":
        if single:
            lines.append("  calc narrow = narrowToSingle(wide)")
            lines.append("  return narrow")
        else:
            lines.append("  return wide")
    else:
        if single:
            lines += ["  wideRe = Complex.real(wide)", "  wideIm = Complex.imag(wide)",
                      "  calc narrowRe = narrowToSingle(wideRe)",
                      "  calc narrowIm = narrowToSingle(wideIm)",
                      "  result = ComplexSingle.new(narrowRe, narrowIm)", "  return result"]
        else:
            lines.append("  return wide")
    return "\n".join(lines) + "\n"


def wrappers() -> str:
    out = []
    for single in (False, True):
        for cname, parts, op, purpose in UNARY:
            out.append(_wrapper(cname, parts, op, purpose, "unary", single))
        for cname, parts, op, purpose in REALS:
            out.append(_wrapper(cname, parts, op, purpose, "real", single))
        for cname, parts, op, purpose in BINARY:
            out.append(_wrapper(cname, parts, op, purpose, "binary", single))
    return "\n".join(out)


# ---------------------------------------------------------------- the exact reference

PREC = 500
_PI: dict = {}


def _ctx(prec=None):
    global PREC
    if prec is not None:
        PREC = prec
    getcontext().prec = PREC
    getcontext().Emax = 999999999
    getcontext().Emin = -999999999


def D(x) -> Decimal:
    return Decimal(x)


def _atan_inverse(n: int) -> Decimal:
    """atan(1/n) for an integer n > 1 by its series, at the current precision."""
    x = Decimal(1) / n
    x2 = x * x
    term = x
    total = x
    k = 1
    eps = Decimal(10) ** (-(getcontext().prec + 5))
    while abs(term) > eps:
        term = -term * x2
        k += 2
        total += term / k
    return total


def _pi() -> Decimal:
    """pi at the current precision (Machin's formula), kept per precision."""
    prec = getcontext().prec
    if prec not in _PI:
        getcontext().prec = prec + 10
        value = 16 * _atan_inverse(5) - 4 * _atan_inverse(239)
        getcontext().prec = prec
        _PI[prec] = +value
    return _PI[prec]


def datan(x: Decimal) -> Decimal:
    """atan on decimals: argument halving (atan x = 2 atan(x / (1 + sqrt(1 + x^2)))) then the Taylor series."""
    neg = x < 0
    x = abs(x)
    invert = x > 1
    if invert:
        x = 1 / x
    halvings = 0
    while x > Decimal("0.01"):
        x = x / (1 + (1 + x * x).sqrt())
        halvings += 1
    total = x
    term = x
    x2 = x * x
    k = 1
    eps = Decimal(10) ** (-(getcontext().prec + 5))
    while abs(term) > eps * abs(total) and abs(term) > Decimal(10) ** -(getcontext().prec * 2 + 400):
        term = -term * x2
        k += 2
        total += term / k
    total *= 2 ** halvings
    if invert:
        total = _pi() / 2 - total
    return -total if neg else total


def _taylor_sincos(x: Decimal) -> tuple[Decimal, Decimal]:
    s = c = Decimal(0)
    term = Decimal(1)
    k = 0
    eps = Decimal(10) ** (-(getcontext().prec + 5))
    while abs(term) > eps or k < 4:
        if k % 4 == 0:
            c += term
        elif k % 4 == 1:
            s += term
        elif k % 4 == 2:
            c -= term
        else:
            s -= term
        k += 1
        term = term * x / k
        if term == 0:
            break
    return s, c


def sincos(x: Decimal) -> tuple[Decimal, Decimal]:
    """sin and cos of a decimal of any size (pi is taken to enough digits for the reduction)."""
    base = getcontext().prec
    extra = max(0, x.adjusted()) + 20
    getcontext().prec = base + extra
    pio2 = _pi() / 2
    n = int((x / pio2).to_integral_value())
    r = x - n * pio2
    getcontext().prec = base
    r = +r
    s, c = _taylor_sincos(r)
    return [(s, c), (c, -s), (-s, -c), (-c, s)][n % 4]


def datan2(y: Decimal, x: Decimal) -> Decimal:
    pi = _pi()
    if x == 0:
        return pi / 2 if y > 0 else -pi / 2
    a = datan(abs(y) / abs(x))
    if x < 0:
        a = pi - a
    return a if y >= 0 else -a


def dsinh(x: Decimal) -> Decimal:
    e = x.exp()
    return (e - 1 / e) / 2


def dcosh(x: Decimal) -> Decimal:
    e = x.exp()
    return (e + 1 / e) / 2


def cadd(a, b): return (a[0] + b[0], a[1] + b[1])
def csub(a, b): return (a[0] - b[0], a[1] - b[1])
def cmul(a, b): return (a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0])


def cdiv(a, b):
    d = b[0] * b[0] + b[1] * b[1]
    return ((a[0] * b[0] + a[1] * b[1]) / d, (a[1] * b[0] - a[0] * b[1]) / d)


def cabsd(a): return (a[0] * a[0] + a[1] * a[1]).sqrt()


def clogd(a):
    return ((a[0] * a[0] + a[1] * a[1]).ln() / 2, datan2(a[1], a[0]))


def cexpd(a):
    e = a[0].exp()
    s, c = sincos(a[1])
    return (e * c, e * s)


def csqrtd(a):
    r = cabsd(a)
    if a[0] >= 0:
        t = ((r + a[0]) / 2).sqrt()
        return (t, a[1] / (2 * t))
    u = ((r - a[0]) / 2).sqrt()
    return (abs(a[1]) / (2 * u), u if a[1] >= 0 else -u)


def times_i(a): return (-a[1], a[0])
def times_minus_i(a): return (a[1], -a[0])


def csinhd(a):
    s, c = sincos(a[1])
    return (dsinh(a[0]) * c, dcosh(a[0]) * s)


def ccoshd(a):
    s, c = sincos(a[1])
    return (dcosh(a[0]) * c, dsinh(a[0]) * s)


def ctanhd(a):
    s2, c2 = sincos(2 * a[1])
    d = dcosh(2 * a[0]) + c2
    return (dsinh(2 * a[0]) / d, s2 / d)


ONE = (Decimal(1), Decimal(0))


def casinhd(a):
    z2p1 = cadd(cmul(a, a), ONE)
    return clogd(cadd(a, csqrtd(z2p1)))


def cacoshd(a):
    return clogd(cadd(a, cmul(csqrtd(cadd(a, ONE)), csqrtd(csub(a, ONE)))))


def catanhd(a):
    l = csub(clogd(cadd(ONE, a)), clogd(csub(ONE, a)))
    return (l[0] / 2, l[1] / 2)


def casind(a): return times_minus_i(casinhd(times_i(a)))
def catand(a): return times_minus_i(catanhd(times_i(a)))
def csind(a): return times_minus_i(csinhd(times_i(a)))
def ccosd(a): return ccoshd(times_i(a))
def ctand(a): return times_minus_i(ctanhd(times_i(a)))


def cacosd(a):
    s = casind(a)
    return (_pi() / 2 - s[0], -s[1])


DEC = {"cexp": cexpd, "clog": clogd, "csqrt": csqrtd, "csin": csind, "ccos": ccosd, "ctan": ctand, "casin": casind,
       "cacos": cacosd, "catan": catand, "csinh": csinhd, "ccosh": ccoshd, "ctanh": ctanhd, "casinh": casinhd,
       "cacosh": cacoshd, "catanh": catanhd}

TINY = Decimal("1e-400")


def _part(v: float, tiny: Decimal = None) -> Decimal:
    tiny = tiny or TINY
    if v == 0:
        return tiny if math.copysign(1.0, v) > 0 else -tiny
    return D(v)


def ref(name: str, x: float, y: float, w: tuple | None = None):
    """The exact value of a function at finite doubles: ((re, im) Decimals, zero flags), where a flag is True for a
    part that is below 1e-90 and so is a zero with the sign of the value (for the arguments that had a zero part)."""
    mags = [D(abs(v)) for v in (x, y, *(w or ())) if v != 0]
    hi = max((m.adjusted() for m in mags), default=0)
    lo = min((m.adjusted() for m in mags), default=0)
    perturbed = (x == 0 or y == 0) and name in DEC
    _ctx((500 if (perturbed or name == "cpow") else 160) + 2 * max(0, hi) + 2 * max(0, -lo))
    a = (_part(x), _part(y))
    if name == "cabs":
        v = (cabsd((D(x), D(y))), Decimal(0))
    elif name == "carg":
        v = (datan2(D(y), D(x)), Decimal(0))
    elif name == "cpow":
        b = (_part(w[0]), _part(w[1]))
        v = cexpd(cmul(b, clogd(a)))
        perturbed = False
    elif name == "conj":
        v = (D(x), -D(y))
    elif name == "cproj":
        v = (D(x), D(y))
    elif name == "creal":
        v = (D(x), Decimal(0))
    elif name == "cimag":
        v = (D(y), Decimal(0))
    else:
        v = DEC[name](a)
    zero = [False, False]
    if perturbed:
        v2 = DEC[name]((_part(x, TINY / 4), _part(y, TINY / 4)))
        zero = [abs(p) < Decimal("1e-100") and abs(p - q) > abs(p) * Decimal("0.1") for p, q in zip(v, v2)]
    return v, zero


def to_float(v: Decimal) -> float:
    try:
        return float(v)
    except OverflowError:
        return math.copysign(INF, float(v.copy_sign(1)) if False else (1 if v > 0 else -1))


def bits(x: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def bits32(x: float) -> int:
    return struct.unpack("<I", struct.pack("<f", x))[0]


def narrow(x: float) -> float:
    try:
        return struct.unpack("<f", struct.pack("<f", x))[0]
    except OverflowError:
        return math.copysign(INF, x)


def ulp_of(x: float, single: bool = False) -> float:
    """The spacing of the format at x (the lowest spacing for zero and subnormals)."""
    if single:
        a = abs(x)
        if a < 1.1754943508222875e-38:
            return 2.0 ** -149
        e = math.frexp(a)[1]
        return 2.0 ** (e - 24)
    return max(math.ulp(x), 5e-324) if x == x and not math.isinf(x) else 0.0


# ---------------------------------------------------------------- Annex G's special values
# 'N' a NaN, 'A' anything, 'Z' a zero of either sign, 'I' an infinity of either sign, otherwise the exact double

def sg(v, s):
    if isinstance(s, float) and math.isnan(s):
        return "Z" if v == 0 else ("I" if math.isinf(v) else v)
    return math.copysign(v, s)


def _isnan(v): return isinstance(v, float) and math.isnan(v)


def _finite(v): return isinstance(v, float) and math.isfinite(v)


def _cs(y):
    return math.cos(y), math.sin(y)


def special(name: str, x: float, y: float, w=None):
    """Annex G's value, as a pair of expectations, when the arguments are not both finite or sit on a rule of the
    annex; None when the general (reference) rule decides."""
    xn, yn = math.isnan(x), math.isnan(y)
    xi, yi = math.isinf(x), math.isinf(y)
    xf, yf = math.isfinite(x), math.isfinite(y)
    if name == "conj":
        return (x if xn else x, "N" if yn else -y)
    if name == "cproj":
        if xi or yi:
            return (INF, sg(0.0, y))
        return (x, y)
    if name == "creal":
        return (x, 0.0)
    if name == "cimag":
        return (y, 0.0)
    if name == "cabs":
        if xi or yi:
            return (INF, 0.0)
        if xn or yn:
            return ("N", 0.0)
        return None
    if name == "carg":
        if xn or yn:
            return ("N", 0.0)
        if x == 0 or y == 0 or xi or yi:
            return (_atan2(y, x), 0.0)
        return None
    if name == "cpow":
        return None if (xf and yf and w is not None and all(math.isfinite(v) for v in w) and not (x == 0 and y == 0)) else ("A", "A")
    f = SPECIAL.get(name)
    if f is None:
        return None
    return f(x, y, xn, yn, xi, yi, xf, yf)


def _atan2(y, x):
    return math.atan2(y, x)


def _exp(x, y, xn, yn, xi, yi, xf, yf):
    if xf:
        if not yf:
            return ("N", "N")
        return None
    if xn:
        return ("N", y) if y == 0 else ("N", "N")
    if x > 0:
        if yf:
            if y == 0:
                return (INF, y)
            c, s = _cs(y)
            return (sg(INF, c), sg(INF, s))
        return ("A", "N") if True else None
    if yf:
        if y == 0:
            return (0.0, y)
        c, s = _cs(y)
        return (sg(0.0, c), sg(0.0, s))
    return ("Z", "Z")


def _log(x, y, xn, yn, xi, yi, xf, yf):
    if x == 0 and y == 0:
        return (-INF, sg(PI, y) if math.copysign(1.0, x) < 0 else y)
    if yi:
        if xn:
            return (INF, "N")
        if xi:
            return (INF, sg(PI34 if x < 0 else PI4, y))
        return (INF, sg(PI2, y))
    if xi:
        if yn:
            return (INF, "N")
        return (INF, sg(PI, y) if x < 0 else sg(0.0, y))
    if xn or yn:
        return ("N", "N")
    return None


def _sqrt(x, y, xn, yn, xi, yi, xf, yf):
    if yi:
        return (INF, sg(INF, y))
    if xi:
        if x > 0:
            return (INF, "N") if yn else (INF, sg(0.0, y))
        return ("N", "I") if yn else (0.0, sg(INF, y))
    if xn or yn:
        return ("N", "N")
    if x == 0 and y == 0:
        return (0.0, y)
    return None


def _sinh(x, y, xn, yn, xi, yi, xf, yf):
    if xf:
        if x == 0:
            if y == 0:
                return (x, y)
            if yf:
                return None
            return ("Z", "N")
        if not yf:
            return ("N", "N")
        return None
    if xn:
        return ("N", y) if y == 0 else ("N", "N")
    if yf:
        if y == 0:
            return (x, y)
        c, s = _cs(y)
        return (sg(INF, c * math.copysign(1.0, x)), sg(INF, s))
    return ("I", "N")


def _cosh(x, y, xn, yn, xi, yi, xf, yf):
    if xf:
        if x == 0:
            if yf:
                return (1.0, math.copysign(1.0, x) * y) if y == 0 else None
            return ("N", "Z")
        if not yf:
            return ("N", "N")
        return None
    if xn:
        return ("N", "Z") if y == 0 else ("N", "N")
    if yf:
        if y == 0:
            return (INF, math.copysign(1.0, x) * y)
        c, s = _cs(y)
        return (sg(INF, c), sg(INF, s * math.copysign(1.0, x)))
    return ("I", "N") if yi else (INF, "N")


def _tanh(x, y, xn, yn, xi, yi, xf, yf):
    if xf:
        if not yf:
            return ("N", "N")
        if x == 0 and y == 0:
            return (x, y)
        return None
    if xn:
        return ("N", y) if y == 0 else ("N", "N")
    one = math.copysign(1.0, x)
    if yf:
        if y == 0:
            return (one, y)
        return (one, sg(0.0, math.sin(2 * y)))
    return (one, "Z")


def _asinh(x, y, xn, yn, xi, yi, xf, yf):
    if xi:
        if yi:
            return (x, sg(PI4, y))
        if yn:
            return (x, "N")
        return (x, sg(0.0, y))
    if yi:
        if xn:
            return ("I", "N")
        return (sg(INF, x), sg(PI2, y))
    if xn:
        return (x, y) if y == 0 else ("N", "N")
    if yn:
        return ("N", "N")
    if x == 0 and y == 0:
        return (x, y)
    return None


def _acosh(x, y, xn, yn, xi, yi, xf, yf):
    if yi:
        if xn:
            return (INF, "N")
        if xi:
            return (INF, sg(PI4 if x > 0 else PI34, y))
        return (INF, sg(PI2, y))
    if xi:
        if yn:
            return (INF, "N")
        return (INF, sg(0.0, y) if x > 0 else sg(PI, y))
    if xn:
        return ("N", "N")
    if yn:
        return ("N", PI2) if x == 0 else ("N", "N")
    if x == 0 and y == 0:
        return (0.0, sg(PI2, y))
    return None


def _acos(x, y, xn, yn, xi, yi, xf, yf):
    if xn and yi:
        return ("N", -y)
    r = _acosh(x, y, xn, yn, xi, yi, xf, yf)
    if r is None:
        if x == 0 and y == 0:
            return (PI2, -y)
        return None
    re, im = r
    if x == 0 and yn:
        return (PI2, "N")
    if xn and yn:
        return ("N", "N")
    if yn and xi:
        return ("N", "I")
    if x == 0 and y == 0:
        return (PI2, -y)
    # (|Im cacosh|, -Re cacosh with y's sign)
    out_re = abs(im) if isinstance(im, float) else im
    out_im = "N" if re == "N" else (-sg(re, y) if isinstance(re, float) else re)
    return (out_re, out_im)


def _atanh(x, y, xn, yn, xi, yi, xf, yf):
    if abs(x) == 1.0 and y == 0:
        return (sg(INF, x), y)
    if yi:
        return (sg(0.0, x), sg(PI2, y))
    if xi:
        return (sg(0.0, x), "N") if yn else (sg(0.0, x), sg(PI2, y))
    if xn:
        return ("N", "N")
    if yn:
        return (x, "N") if x == 0 else ("N", "N")
    if x == 0 and y == 0:
        return (x, y)
    return None


def _rotated(base):
    """f(z) = -i g(iz): the expectation of f from the one of g at iz = (-y, x), turned back."""
    def f(x, y, xn, yn, xi, yi, xf, yf):
        r = SPECIAL[base](-y, x, yn, xn, yi, xi, yf, xf)
        if r is None:
            return None
        a, b = r
        return (b, _neg(a))
    return f


def _neg(v):
    return -v if isinstance(v, float) else v


def _cos_special(x, y, xn, yn, xi, yi, xf, yf):
    return SPECIAL["ccosh"](-y, x, yn, xn, yi, xi, yf, xf)


SPECIAL = {"cexp": _exp, "clog": _log, "csqrt": _sqrt, "csinh": _sinh, "ccosh": _cosh, "ctanh": _tanh,
           "casinh": _asinh, "cacosh": _acosh, "cacos": _acos, "catanh": _atanh}
SPECIAL["csin"] = _rotated("csinh")
SPECIAL["ctan"] = _rotated("ctanh")
SPECIAL["casin"] = _rotated("casinh")
SPECIAL["catan"] = _rotated("catanh")
SPECIAL["ccos"] = _cos_special

# ---------------------------------------------------------------- the arguments

UNIT_VALUES = [0.0, -0.0, 1.0, INF, NAN]
SPECIAL_VALUES = [0.0, -0.0, 0.5, -0.5, 1.0, -1.0, 2.0, -2.0, INF, -INF, NAN]


def special_inputs() -> list[tuple[float, float]]:
    return [(a, b) for a in SPECIAL_VALUES for b in SPECIAL_VALUES]


MULT = 6364136223846793005
INCR = 1442695040888963407
MASK = (1 << 64) - 1


def sweep(seed: int, count: int, lo: int, span: int, parts: int = 2) -> list[tuple]:
    """Deterministic finite arguments: each part has an exponent from 2^lo up over `span` values."""
    state = seed
    out = []
    for _ in range(count):
        item = []
        for _p in range(parts):
            state = (state * MULT + INCR) & MASK
            sign = state >> 63
            exp = 1023 + lo + ((state >> 40) & 0xFFFFFF) % span
            mant = state & ((1 << 52) - 1)
            item.append(struct.unpack("<d", struct.pack("<Q", (sign << 63) | (exp << 52) | mant))[0])
        out.append(tuple(item))
    return out


def domain_sweeps(name: str) -> list[tuple]:
    """The finite arguments tested for a function besides the special grid (and the tour's too)."""
    wide = sweep(12345, 24, -30, 40)       # 1e-9 to 1e3
    near = sweep(777, 16, -6, 8)           # 0.015 to 4
    if name in ("cexp", "csinh", "ccosh"):
        return wide + near + [(700.0, 1.0), (710.0, 1.0), (-740.0, 2.0), (709.5, 0.5), (1000.0, 1.0), (-1000.0, 1.0),
                              (30.0, 1e9), (1.0, 1e22), (1e-300, 1e-300), (0.0, 1e300)]
    if name in ("csin", "ccos"):
        return wide + near + [(1.0, 700.0), (1.0, 710.0), (1e9, 3.0), (3.0, 1e22), (1e-300, 1e-300)]
    if name in ("ctan", "ctanh"):
        return wide + near + [(1.0, 25.0), (25.0, 1.0), (1.5707963267948966, 1e-9), (1.0, 1.5707963267948966),
                              (400.0, 1.0), (1e-300, 1e-300), (0.5, 710.0)]
    if name == "clog":
        return wide + near + [(1.0, 1e-9), (1.0, 1e-17), (0.9999999999999999, 0.0), (1.0000000000000002, 0.0), (0.6, 0.8),
                              (0.8, 0.6), (1e200, 1e200), (1e-200, 1e-200), (1e308, 1e308), (5e-324, 5e-324),
                              (0.7071067811865476, 0.7071067811865476)]
    if name == "csqrt":
        return wide + near + [(1e300, 1e300), (-1e300, 1e300), (1e-310, 1e-310), (-1e-310, 5e-324), (3.0, 4.0),
                              (-3.0, 4.0), (1.7976931348623157e308, 1.7976931348623157e308), (1.0, 1e-300)]
    if name in ("casin", "cacos", "casinh", "cacosh"):
        return wide + near + [(2.0, 1e-9), (0.5, 1e-9), (1.0, 1e-9), (1e-9, 1e-9), (1e10, 1e10), (1e200, 1.0),
                              (1.0, 1e200), (1e300, 1e300), (-3.0, 0.5), (3.0, -0.5), (0.999999, 1e-6), (1e-200, 1e-200),
                              (1.0000001, 0.0), (5.0, 0.0), (0.0, 5.0), (0.0, 0.5), (-5.0, 0.0), (0.0, -5.0)]
    if name in ("catan", "catanh"):
        return wide + near + [(1.0, 1e-9), (0.9999999999, 1e-9), (1e300, 1.0), (1.0, 1e300), (1e200, 1e200),
                              (1e-9, 1e-9), (2.0, 0.0), (0.5, 0.0), (0.0, 2.0), (0.0, 0.5), (1e-200, 1e-200)]
    if name == "cpow":
        return sweep(99, 24, -4, 8) + [(2.0, 0.0), (0.0, 1.0), (1.0, 1.0), (-1.0, 0.0)]
    if name in ("cabs", "carg"):
        return wide + near + [(3.0, 4.0), (1e300, 1e300), (1e-300, 1e-300), (5e-324, 5e-324), (1.7976931348623157e308, 1.7976931348623157e308),
                              (1e300, 1e-300), (1e-310, 3e-310), (1.0, 1e-17), (0.0, 1e-310), (-3.0, 4.0), (4.0, -3.0)]
    return wide + near


# ---------------------------------------------------------------- expectations

NAN_MARK = 0xFFF8000000000000  # tolerance bits that mean "a NaN"
ANY_MARK = 0xFFF0000000000001  # tolerance bits that mean "anything"
ZERO_MARK = 0xFFF0000000000002  # a zero of either sign
INF_MARK = 0xFFF0000000000003  # an infinity of either sign

# bound in ulps per component of the double functions (stated in the module's notes); a float function's bound is
# this plus 1 ulp of the float
BOUND = {"cexp": 3, "clog": 2, "csqrt": 2, "csin": 4, "ccos": 4, "ctan": 6, "casin": 4, "cacos": 4, "catan": 6,
         "csinh": 4, "ccosh": 4, "ctanh": 6, "casinh": 4, "cacosh": 4, "catanh": 4, "cabs": 1, "carg": 1,
         "creal": 0, "cimag": 0, "conj": 0, "cproj": 0}


def expect_part(kind, single: bool = False):
    """(expected value, tolerance bits) for one part: an exact double, a NaN, anything, or a double with a tolerance."""
    return kind


def _encode(exp, single: bool):
    """exp: 'N', 'A', 'Z', 'I', a float (exact), or ('near', float, tol). Returns (expected bits, tolerance bits)."""
    if exp == "N" or (isinstance(exp, float) and math.isnan(exp)):
        return 0, NAN_MARK
    if exp == "A":
        return 0, ANY_MARK
    if exp == "Z":
        return 0, ZERO_MARK
    if exp == "I":
        return 0, INF_MARK
    if isinstance(exp, tuple):
        _k, val, tol = exp
        return bits(val), bits(tol)
    if single:
        exp = narrow(exp)
    return bits(exp), 0


def expectation(name: str, x: float, y: float, w=None, single: bool = False, tol_scale: float = 1.0):
    """The expectation (a pair of encodable items) of a function at one argument, or None to skip the case."""
    sp = special(name, x, y, w)
    if sp is not None:
        return sp
    if not (math.isfinite(x) and math.isfinite(y)):
        return ("A", "A")
    try:
        v, zero = ref(name, x, y, w)
    except ArithmeticError:
        return None
    items = []
    k = BOUND[name] + (1 if single else 0) if name != "cpow" else 0
    for i, part in enumerate(v):
        if zero[i]:
            items.append(sg(0.0, 1.0 if part > 0 else -1.0))
            continue
        f = to_float(part)
        if single:
            f = narrow(f)
        if name in ("creal", "cimag", "conj", "cproj"):
            items.append(f)
            continue
        if math.isinf(f) or abs(f) > 1.7976931348623157e308 * (1 - 2.0 ** -54) and not single:
            items.append(("near", f, 0.0) if False else f)
            continue
        if name == "cpow":
            mag = to_float((v[0] * v[0] + v[1] * v[1]).sqrt())
            wl = float(abs(clogd_fl(x, y)) * math.hypot(*w)) if w else 0.0
            tol = (6 + 2 * wl) * (2.0 ** -53 if not single else 2.0 ** -24) * mag
            items.append(("near", f, tol))
        else:
            tol = k * tol_scale * ulp_of(f, single)
            items.append(("near", f, tol))
    return tuple(items)


def clogd_fl(x, y):
    _ctx()
    _ctx(600)
    r = clogd((D(x), D(y)))
    return abs(complex(float(r[0]), float(r[1])))


# ---------------------------------------------------------------- the tests block

def _lit(x: float) -> str:
    return f"convert.uint64BitsToFloat64({bits(x)})"


def _lit32(x: float) -> str:
    return f"convert.float64ToFloat32(convert.uint64BitsToFloat64({bits(x)}))"


def _case(idx: int, opname: str, args: list[tuple[float, float]], exp, single: bool, real_result: bool) -> list[str]:
    lines = []
    ctor = "ComplexSingle" if single else "Complex"
    lit = _lit32 if single else _lit
    for j, (a, b) in enumerate(args):
        lines.append(f"  a{idx}x{j} = {ctor}.new({lit(a)}, {lit(b)})")
    names = ", ".join(f"a{idx}x{j}" for j in range(len(args)))
    lines.append(f"  r{idx} = {opname}({names})")
    if real_result:
        parts = [(f"r{idx}", exp[0])]
        if single:
            lines.append(f"  calc g{idx} = convert.float32ToFloat64(r{idx})")
            parts = [(f"g{idx}", exp[0])]
    else:
        lines.append(f"  p{idx}r = {ctor}.real(r{idx})")
        lines.append(f"  p{idx}i = {ctor}.imag(r{idx})")
        if single:
            lines.append(f"  calc g{idx}r = convert.float32ToFloat64(p{idx}r)")
            lines.append(f"  calc g{idx}i = convert.float32ToFloat64(p{idx}i)")
            parts = [(f"g{idx}r", exp[0]), (f"g{idx}i", exp[1])]
        else:
            parts = [(f"p{idx}r", exp[0]), (f"p{idx}i", exp[1])]
    for tag, e in parts:
        eb, tb = _encode(e, single)
        if tb == ANY_MARK:
            continue
        lines.append(f"  calc m{tag} = partMatches({eb}, {tb}, {tag})")
        lines.append(f"  expect{tag}: test.assertTrue(m{tag})")
    return lines


def function_list() -> list:
    """(C name, op name, kind, parts op, single) in table order: the double functions, then the float ones."""
    out = []
    for single in (False, True):
        for group, kind in ((UNARY, "unary"), (REALS, "real"), (BINARY, "binary")):
            for cname, parts, op, purpose in group:
                out.append((cname + ("f" if single else ""), op + ("Single" if single else ""), kind, parts, single))
    return out


def dispatch() -> str:
    """callFunction: the wrapper of an index, called on the four doubles of a table row, giving a Complex of doubles."""
    funcs = function_list()
    lines = ['op callFunction "The result of the wrapper at an index of the table, on the arguments of a row (a Complex of doubles; a real result is its real part)"',
             "  input index Int64 copied", "  input a Float64 copied", "  input b Float64 copied",
             "  input c Float64 copied", "  input d Float64 copied", "  output Complex",
             "  effect use machine.memory", "  uses memoryAccess", ":begin"]
    for k, (cname, op, kind, parts, single) in enumerate(funcs):
        if k:
            lines.append(f":next{k}")
        nxt = f"next{k + 1}" if k + 1 < len(funcs) else f"call{k}"
        lines.append(f"  when index == {k} call{k} {nxt}")
        lines.append(f":call{k}")
        rec = "ComplexSingle" if single else "Complex"
        if single:
            for nm in ("a", "b", "c", "d"):
                lines.append(f"  calc {nm}{k} = convert.float64ToFloat32({nm})")
            xa, xb, xc, xd = (f"{n}{k}" for n in "abcd")
        else:
            xa, xb, xc, xd = "a", "b", "c", "d"
        lines.append(f"  z{k} = {rec}.new({xa}, {xb})")
        args = f"z{k}"
        if kind == "binary":
            lines.append(f"  w{k} = {rec}.new({xc}, {xd})")
            args = f"z{k}, w{k}"
        lines.append(f"  r{k} = {op}({args})")
        if kind == "real":
            if single:
                lines.append(f"  calc re{k} = convert.float32ToFloat64(r{k})")
            else:
                lines.append(f"  calc re{k} = r{k} * 1.0")
            lines.append(f"  out{k} = Complex.new(re{k}, 0.0)")
        elif single:
            lines.append(f"  rr{k} = ComplexSingle.real(r{k})")
            lines.append(f"  ri{k} = ComplexSingle.imag(r{k})")
            lines.append(f"  calc re{k} = convert.float32ToFloat64(rr{k})")
            lines.append(f"  calc im{k} = convert.float32ToFloat64(ri{k})")
            lines.append(f"  out{k} = Complex.new(re{k}, im{k})")
        else:
            lines.append(f"  return r{k}")
            continue
        lines.append(f"  return out{k}")
    return "\n".join(lines) + "\n"


def _row(args, exp, single: bool) -> str:
    vals = [args[0][0], args[0][1]] + (list(args[1]) if len(args) > 1 else [0.0, 0.0])
    fields = [bits(v) for v in vals]
    for part in exp:
        eb, tb = _encode(part, single)
        fields += [eb, tb]
    return "".join(f"{f:016x}" for f in fields)


def cases_for(cname: str, single: bool):
    """(arguments, expectation) of the unit tests of one function: Annex G's special values on a small grid and a few
    ordinary points (the sweeps are the tour's)."""
    real = any(cname == r[0] for r in REALS)
    out = []
    if cname == "cpow":
        pw = domain_sweeps("cpow")
        pw = pw[:4] + pw[24:]
        pairs = [((a, b), (c, d)) for (a, b), (c, d) in zip(pw, reversed(pw))]
        for (a, b) in [(1.0, 1.0), (2.0, 0.0), (0.0, 1.0)]:
            for (c, d) in [(2.0, 0.0), (0.5, 0.0), (0.0, 1.0), (INF, 0.0), (NAN, 0.0)]:
                pairs.append(((a, b), (c, d)))
        for (a, b), (c, d) in pairs:
            exp = expectation("cpow", a, b, (c, d), single)
            if exp is not None:
                out.append((((a, b), (c, d)), exp))
        return out
    grid = [(a, b) for a, b in special_inputs() if a in UNIT_VALUES and b in UNIT_VALUES]
    swept = domain_sweeps(cname)
    swept = swept[:2] + swept[40:44]
    if single:
        swept = [(narrow(a), narrow(b)) for a, b in swept if _fits32(a, b)][:4]
        grid = [g for g in grid if g[0] in (1.0, INF, NAN) and g[1] in (0.0, 1.0, INF, NAN)]
    for a, b in grid + swept:
        exp = expectation(cname, a, b, None, single)
        if exp is None:
            continue
        if real:
            exp = (exp[0], "A")
        out.append((((a, b),), exp))
    return out


def tests() -> str:
    funcs = function_list()
    lines = []
    uses = []
    for k, (cname, op, kind, parts, single) in enumerate(funcs):
        base = cname[:-1] if single else cname
        rows = cases_for(base, single)
        text = "".join(_row(args, exp, single) for args, exp in rows)
        lines.append(f'  let table{k} String "{text}"')
        uses.append(f"  failed{k} = checkTable(table{k}, {len(rows)}, {k})")
        uses.append(f"  expect{cname}: test.assertEqualInt64(0, failed{k})")
        rec = "ComplexSingle" if single else "Complex"
        uses.append(f"  probe{k} = {rec}.new({'convert.float64ToFloat32(1.0)' if single else '1.0'}, {'convert.float64ToFloat32(0.5)' if single else '0.5'})")
        uses.append(f"  direct{k} = {op}({'probe%d, probe%d' % (k, k) if kind == 'binary' else 'probe%d' % k})")
    verifies = [f"  verifies {op} gives{c[0].upper()}{c[1:]}" for c, op, *_ in funcs]
    return (dispatch() + "\n"
            + 'test complexTableTest "every function of complex.h on the special values of Annex G and some ordinary points, against an exact reference: a row is the arguments and the expected parts as bits and tolerances"\n'
            + "\n".join(verifies) + "\n  effect use machine.memory\n  uses memoryAccess\n"
            + "\n".join(lines) + "\n:begin\n" + "\n".join(uses) + "\n  return\n")


def _fits32(a, b):
    return all(x == 0 or (1.2e-38 <= abs(x) <= 3.4e38) for x in (a, b))


BLOCKS = {"polynomials": polynomials, "wrappers": wrappers, "tests": tests}


def write_dsl(path: str | None = None, only=None) -> None:
    path = path or os.path.join(HERE, "cmathcomplex.dsl")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for name, make in BLOCKS.items():
        if only and name not in only:
            continue
        pattern = re.compile(rf"(## @generated {name}\n).*?(## @end {name}\n)", re.S)
        if not pattern.search(text):
            raise SystemExit(f"no block {name}")
        block = make()
        text = pattern.sub(lambda m: m.group(1) + block + m.group(2), text)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


if __name__ == "__main__":
    write_dsl(only=sys.argv[1:] or None)
