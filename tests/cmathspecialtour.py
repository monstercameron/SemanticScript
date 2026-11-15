"""The special functions of math.h (the module `cmathspecial`), called through `ffi` in an executable with no libc.

tests/test_c_cmathspecial.py builds this program with the runtime in SemanticScript and compares what it prints with an
exact high-precision reference computed here with decimal arithmetic (series and continued fractions, not the math
module): sinh, cosh, tanh, asinh, acosh, atanh, erf, erfc, tgamma and lgamma for double and the f-forms for float, over
special values (signed zeros, infinities, NaN, subnormals, the ends of each function's range, poles) and a
deterministic sweep, plus lgamma_r and lgammaf_r (the sign lgamma stores).

The reference half of this file (`reference`, `ulps`, `cases`) is also what the module's own unit tests were generated
from (semanticscript/runtime/tools/cmathspecialgen.py imports it).
"""
from __future__ import annotations

import math
import os
import struct
import sys
from decimal import Decimal as D, localcontext

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "docs", "refined-examples", "stage0", "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests", "suite"))

PRECISION = 140

PI = D("3.14159265358979323846264338327950288419716939937510582097494459230781640628620899862803482534211706798214808651328230664709384460955058223172535940812848111745028410270193852110555964462294895493038196")
SQRT_PI_TEXT = None

DOUBLE_FUNCTIONS = ["sinh", "cosh", "tanh", "asinh", "acosh", "atanh", "erf", "erfc", "tgamma", "lgamma"]
FLOAT_FUNCTIONS = [n + "f" for n in DOUBLE_FUNCTIONS]
ALL_NAMES = DOUBLE_FUNCTIONS + FLOAT_FUNCTIONS + ["lgamma_r", "lgammaf_r"]


def bits(x: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def from_bits(n: int) -> float:
    return struct.unpack("<d", struct.pack("<Q", n))[0]


def to_float32(x: float) -> float:
    try:
        return struct.unpack("<f", struct.pack("<f", x))[0]
    except OverflowError:
        return math.copysign(math.inf, x)


def float32_bits(x: float) -> int:
    return struct.unpack("<I", struct.pack("<f", x))[0]


# ---------------------------------------------------------------- the reference (decimal arithmetic)

def _bernoulli(n: int):
    from fractions import Fraction as F
    a = [F(0)] * (n + 1)
    out = []
    for m in range(n + 1):
        a[m] = F(1, m + 1)
        for j in range(m, 0, -1):
            a[j - 1] = j * (a[j - 1] - a[j])
        out.append(a[0])
    return out


_BN = _bernoulli(100)


def _sqrt_pi():
    return PI.sqrt()


def _sinh(x: D) -> D:
    if abs(x) < D("0.01"):
        s, t, n = D(0), x, 1
        while abs(t) > D(10) ** -(PRECISION + 20) * max(abs(x), D(10) ** -400) or n < 4:
            s += t
            t = t * x * x / ((n + 1) * (n + 2))
            n += 2
        return s
    return (x.exp() - (-x).exp()) / 2


def _cosh(x: D) -> D:
    return (x.exp() + (-x).exp()) / 2


def _tanh(x: D) -> D:
    if abs(x) > 400:
        return D(1) if x > 0 else D(-1)
    return _sinh(x) / _cosh(x)


def _asinh(x: D) -> D:
    a = abs(x)
    with localcontext() as c:
        c.prec = 500
        t = a + a * a / (1 + (a * a + 1).sqrt())
        r = (1 + t).ln()
    return r if x >= 0 else -r


def _acosh(x: D) -> D:
    with localcontext() as c:
        c.prec = 500
        t = x - 1
        r = (1 + t + (t * t + 2 * t).sqrt()).ln()
    return r


def _atanh(x: D) -> D:
    with localcontext() as c:
        c.prec = 500
        r = ((1 + x) / (1 - x)).ln() / 2
    return r


def _erf_series(x: D) -> D:
    # erf(x) = 2/sqrt(pi) * sum (-1)^n x^(2n+1) / (n! (2n+1)), with enough working digits for the cancellation
    with localcontext() as c:
        c.prec = PRECISION + 120
        s, t, n = D(0), x, 0
        while True:
            term = t / (2 * n + 1)
            s += term if n % 2 == 0 else -term
            n += 1
            t = t * x * x / n
            if abs(t) < D(10) ** -(PRECISION + 60) and n > 10:
                break
        r = 2 / _sqrt_pi() * s
    return r


def _erfc_cf(x: D) -> D:
    t = x
    depth = 3000 if x < 6 else 800
    for k in range(depth, 0, -1):
        t = x + (D(k) / 2) / t
    return (-(x * x)).exp() / _sqrt_pi() / t


def _erf(x: D) -> D:
    a = abs(x)
    if a < 4:
        r = _erf_series(a)
    else:
        r = 1 - _erfc_cf(a)
    return r if x >= 0 else -r


def _erfc(x: D) -> D:
    if x < 0:
        return 2 - _erfc(-x)
    if x < 4:
        return 1 - _erf_series(x)
    return _erfc_cf(x)


def _lgamma_positive(x: D) -> D:
    n, p, z = 0, D(1), x
    while z < 70:
        p *= z
        z += 1
    s = (z - D("0.5")) * z.ln() - z + (2 * PI).ln() / 2
    for k in range(1, 50):
        b = _BN[2 * k]
        s += D(b.numerator) / D(b.denominator) / (2 * k * (2 * k - 1)) / z ** (2 * k - 1)
    return s - p.ln()


def _sin_pi_fraction(r: D) -> D:
    with localcontext() as c:
        c.prec = PRECISION + 80
        u = PI * r
        s, t, n = D(0), u, 1
        while abs(t) > D(10) ** -(PRECISION + 70) * abs(u) or n < 4:
            s += t
            t = -t * u * u / ((n + 1) * (n + 2))
            n += 2
    return s


def _lgamma_signed(x: D):
    if x > 0:
        return _lgamma_positive(x), 1
    n = (x + D("0.5")).to_integral_value(rounding="ROUND_FLOOR")
    r = x - n
    s = _sin_pi_fraction(r) * (1 if n % 2 == 0 else -1)
    return (PI / abs(s)).ln() - _lgamma_positive(1 - x), (1 if s > 0 else -1)


def _tgamma(x: D) -> D:
    if x > 0:
        return _lgamma_positive(x).exp()
    l, s = _lgamma_signed(x)
    return s * l.exp()


def reference(name: str, x: float) -> D:
    """The exact value (to 100 digits) of a function at a finite double in the function's domain."""
    base = name[:-1] if name.endswith("f") and name != "erf" and name[:-1] in DOUBLE_FUNCTIONS else name
    if name.endswith("_r"):
        base = name[:-2].rstrip("f")
    d = D(x)
    with localcontext() as c:
        c.prec = PRECISION
        c.Emax = 999999
        c.Emin = -999999
        if base == "sinh":
            return _sinh(d)
        if base == "cosh":
            return _cosh(d)
        if base == "tanh":
            return _tanh(d)
        if base == "asinh":
            return _asinh(d)
        if base == "acosh":
            return _acosh(d)
        if base == "atanh":
            return _atanh(d)
        if base == "erf":
            return _erf(d)
        if base == "erfc":
            return _erfc(d)
        if base == "tgamma":
            return _tgamma(d)
        if base == "lgamma":
            return _lgamma_signed(d)[0]
    raise ValueError(name)


def lgamma_sign(x: float) -> int:
    if x > 0:
        return 1
    if x == 0:
        return -1 if math.copysign(1.0, x) < 0 else 1
    with localcontext() as c:
        c.prec = PRECISION
        return _lgamma_signed(D(x))[1]


def is_float(name: str) -> bool:
    return name.endswith("f") and name[:-1] in DOUBLE_FUNCTIONS or name == "lgammaf_r"


def ulp_of(value: float, single: bool) -> float:
    """The spacing of doubles (or floats) at a value."""
    if single:
        a = abs(value)
        if a < 2.0 ** -126:
            return 2.0 ** -149
        e = math.frexp(a)[1]
        return 2.0 ** (e - 24)
    return math.ulp(value)


def ulps(got: float, name: str, x: float) -> float:
    """How many ulps a result is from the exact one (inf when it is not a finite number the function should give)."""
    single = is_float(name)
    ref = reference(name, x)
    if single:
        # the exact value rounded to float is the nearest float: measure from the exact value
        exact = float(ref) if abs(ref) < D("3.4e38") else math.copysign(math.inf, ref)
        u = ulp_of(to_float32(exact) if math.isfinite(exact) else 3.4028234663852886e38, True)
    else:
        try:
            exact = float(ref)
        except OverflowError:
            exact = math.copysign(math.inf, ref)
        u = ulp_of(exact if math.isfinite(exact) else 1.7976931348623157e308, False)
    if math.isnan(got):
        return math.inf
    if math.isinf(got):
        limit = 3.4028235677973366e38 if single else 1.7976931348623157e308
        return 0.0 if abs(ref) >= D(limit) else math.inf
    return float(abs(D(got) - ref) / D(u))


# ---------------------------------------------------------------- correct rounding and the expected value of a call

def round_ref(ref: D, single: bool) -> float:
    """The double (or float, as a double) nearest to an exact value, ties to even; infinity past the largest."""
    from fractions import Fraction
    if ref == 0:
        return 0.0
    f = Fraction(ref)
    sign = -1 if f < 0 else 1
    a = abs(f)
    p, emin, emax = (24, -126, 127) if single else (53, -1022, 1023)
    e = a.numerator.bit_length() - a.denominator.bit_length()
    if Fraction(2) ** e > a:
        e -= 1
    if Fraction(2) ** (e + 1) <= a:
        e += 1
    e = max(e, emin)
    unit = Fraction(2) ** (e - p + 1)
    n = a / unit
    q, r = divmod(n.numerator, n.denominator)
    twice = 2 * r
    if twice > n.denominator or (twice == n.denominator and q % 2 == 1):
        q += 1
    value = q * unit
    if value >= Fraction(2) ** (emax + 1):
        return sign * math.inf
    return sign * float(value)


def _is_integer(x: float) -> bool:
    return math.isfinite(x) and x == math.floor(x)


def expected(base: str, x: float, single: bool = False) -> float:
    """What glibc gives (Annex F's special cases, and the exact value correctly rounded otherwise)."""
    nan, inf = math.nan, math.inf
    if math.isnan(x):
        return nan
    if base in ("sinh", "asinh", "erf") and (x == 0 or math.isinf(x)):
        return x if base != "erf" or x == 0 else math.copysign(1.0, x)
    if base == "cosh" and math.isinf(x):
        return inf
    if base == "tanh" and math.isinf(x):
        return math.copysign(1.0, x)
    if base == "tanh" and x == 0:
        return x
    if base == "acosh":
        if x < 1:
            return nan
        if x == 1:
            return 0.0
        if math.isinf(x):
            return inf
    if base == "atanh":
        if abs(x) > 1:
            return nan
        if abs(x) == 1:
            return math.copysign(inf, x)
        if x == 0:
            return x
    if base == "erfc" and math.isinf(x):
        return 0.0 if x > 0 else 2.0
    if base == "tgamma":
        if x == math.inf:
            return inf
        if x == -math.inf or (x < 0 and _is_integer(x)):
            return nan
        if x == 0:
            return math.copysign(inf, x)
    if base == "lgamma":
        if math.isinf(x) or x == 0 or (x < 0 and _is_integer(x)):
            return inf
        if x in (1.0, 2.0):
            return 0.0
    if base in ("sinh", "cosh") and abs(x) > 1000:
        return math.copysign(inf, x) if base == "sinh" else inf
    return round_ref(reference(base, x), single)


# ---------------------------------------------------------------- the inputs of the tour

def _sweep(low: float, high: float, count: int, seed: int, signed: bool = False) -> list[float]:
    """Deterministic values spread evenly in the log of their magnitude from low to high, signs alternating if asked."""
    out = []
    state = seed
    for i in range(count):
        state = (state * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
        u = ((state >> 11) / float(1 << 53) + i) / count
        v = math.exp(math.log(low) + u * (math.log(high) - math.log(low)))
        out.append(-v if signed and (state >> 62) & 1 else v)
    return out


MAX = 1.7976931348623157e308
S27 = 2.0 ** -27

TOUR_INPUTS = {
    "sinh": [0.0, -0.0, 5e-324, -5e-324, S27 * 0.99, S27, S27 * 1.01, 1e-5, 0.5, 1.0, -1.0, 39.99, 40.0, 40.01, 709.78,
             710.4758600739439, 710.475860073944, 711.0, -711.0, 1e10, MAX, math.inf, -math.inf, math.nan]
            + _sweep(1e-8, 700, 30, 1, True),
    "cosh": [0.0, -0.0, 5e-324, S27, 1e-5, 1.0, -1.0, 39.99, 40.0, 710.4758600739439, 710.475860073944, 1e10, MAX,
             math.inf, -math.inf, math.nan] + _sweep(1e-8, 700, 30, 2, True),
    "tanh": [0.0, -0.0, 5e-324, S27, 1e-5, 0.5, -0.5, 1.0, 21.9, 22.0, 22.1, 40.0, 1e300, math.inf, -math.inf, math.nan]
            + _sweep(1e-6, 20, 30, 3, True),
    "asinh": [0.0, -0.0, 5e-324, S27, 1e-5, 1.0, -1.0, 2.0 ** 28 - 1, 2.0 ** 28, 2.0 ** 28 + 1, 1e10, 1e300, MAX,
              math.inf, -math.inf, math.nan] + _sweep(1e-8, 1e12, 30, 4, True),
    "acosh": [1.0, 1 + 2.0 ** -52, 1 + 2.0 ** -30, 1.5, 2.0, 2.0 ** 28 - 1, 2.0 ** 28, 1e10, MAX, math.inf, 0.99999, 0.0,
              -1.0, -math.inf, math.nan] + [1 + v for v in _sweep(1e-12, 1e3, 30, 5)],
    "atanh": [0.0, -0.0, 5e-324, S27, 1e-5, 0.5, -0.5, 0.999, 1 - 2.0 ** -53, -(1 - 2.0 ** -53), 1.0, -1.0, 1 + 2.0 ** -52,
              2.0, math.inf, -math.inf, math.nan] + [1 - 2.0 ** -k for k in range(2, 53, 5)]
            + [(-1 if i % 2 else 1) * (1 - v) for i, v in enumerate(_sweep(1e-9, 0.9, 20, 6))],
    "erf": [0.0, -0.0, 5e-324, 1e-310, 2.0 ** -30 * 0.99, 2.0 ** -30, 2.0 ** -30 * 1.01, 1e-9, 0.5, 1.0, -1.0, 2.0, 2.9999,
            3.0, 3.0001, 5.9, 6.0, 6.0001, 10.0, math.inf, -math.inf, math.nan] + _sweep(1e-5, 6, 30, 7, True),
    "erfc": [0.0, -0.0, 5e-324, 2.0 ** -60, 1e-9, 0.5, 1.0, -1.0, 2.9999, 3.0, 5.0, 9.0, 10.0, 20.0, 26.0, 26.5, 27.0,
             27.2, 27.25, 27.3, 28.0, -3.0, -5.9, -6.0, -6.1, -30.0, math.inf, -math.inf, math.nan]
            + _sweep(1e-3, 27, 30, 8, True),
    "tgamma": [0.0, -0.0, 5e-324, 1e-310, 2.0 ** -54, 2.0 ** -53, 1e-10, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 20.0, 23.9,
               24.0, 24.1, 100.0, 170.0, 171.0, 171.6, 171.62, 171.63, 172.0, 1000.0, -0.5, -1.0, -1.5, -2.0, -2.5, -3.5,
               -10.5, -100.5, -150.5, -170.5, -171.5, -180.5, -185.5, -190.5, -1e10, -1e300, math.inf, -math.inf,
               math.nan] + _sweep(0.01, 170, 30, 9) + [-v for v in _sweep(0.01, 170, 20, 10)],
    "lgamma": [0.0, -0.0, 5e-324, 1e-310, 1e-20, 0.5, 1.0, 1 - 2.0 ** -52, 1 + 2.0 ** -52, 1.0000001, 0.9999, 1.5, 2.0,
               2 + 2.0 ** -52, 2 - 2.0 ** -51, 3.0, 10.0, 100.0, 1e5, 1e10, 1e100, 1e300, 2.5e305, 2.6e305, MAX, -0.5,
               -1.0, -1.5, -2.0, -2.457024738220797, -2.747682646727412, -3.1435809, -10.5, -100.5, -10000000000.5,
               -4503599627370495.5, -1e15, -2.0 ** 52, -1e300, math.inf, -math.inf, math.nan]
              + _sweep(0.01, 1000, 30, 11) + [-v for v in _sweep(0.01, 30, 20, 12)],
}
# the float forms get every other one of the same values, and the floats' own limits
FLOAT_EXTRA = {
    "sinh": [88.0, 89.0, 89.4, 89.5, 100.0, 3.4028234663852886e38],
    "cosh": [88.0, 89.0, 89.4, 89.5],
    "tanh": [8.0, 9.0, 10.0],
    "erfc": [9.0, 10.0, 10.5, 11.0, 25.0, 88.0],
    "tgamma": [34.5, 35.0, 36.0, 37.0, -34.5, -38.5, -45.5],
    "lgamma": [1e30, 4e36, 5e36, 3.4028234663852886e38, 1e-40, -3.0000002],
}


def float_inputs(base: str) -> list[float]:
    values = [to_float32(x) for x in TOUR_INPUTS[base][::2]] + [to_float32(x) for x in FLOAT_EXTRA.get(base, [])]
    out = []
    for v in values:
        if not any(bits(v) == bits(w) for w in out):
            out.append(v)
    return out


CALLS: list[tuple[str, str, float]] = []  # (name, base, x) in the order the tour prints them
for _base in DOUBLE_FUNCTIONS:
    CALLS += [(_base, _base, x) for x in TOUR_INPUTS[_base]]
for _base in DOUBLE_FUNCTIONS:
    CALLS += [(_base + "f", _base, x) for x in float_inputs(_base)]
LGAMMA_R_INPUTS = [x for x in TOUR_INPUTS["lgamma"][::3]]
LGAMMAF_R_INPUTS = [to_float32(x) for x in TOUR_INPUTS["lgamma"][::5]]
CALLS += [("lgamma_r", "lgamma", x) for x in LGAMMA_R_INPUTS]
CALLS += [("lgammaf_r", "lgamma", x) for x in LGAMMAF_R_INPUTS]


def _dsl() -> str:
    caps = [f'capability {n.replace("_", "")}Symbol "Authority to bind the C function {n}" load ffi.symbols "{n}"'
            for n in ALL_NAMES + ["calloc", "strlen"]]
    uses = "\n".join(f"  uses {c.split()[1]}" for c in caps)
    ops, body = [], []
    for name in ALL_NAMES:
        single = is_float(name)
        signed = name.endswith("_r")
        inputs = [x for (n, _b, x) in CALLS if n == name]
        opname = "run" + "".join(p.capitalize() for p in name.split("_"))
        kind = ("Signed" if signed else "") + ("Float" if single else "Double")
        head = [f'op {opname} "Call {name} with each of the values of the tour and write what it gives"',
                f"  input callee {kind}Function copied"]
        if signed:
            head += ["  input allocate AllocFunction copied", "  input measure LengthFunction copied"]
        head += ["  effect write console.stdout", "  uses stdoutWriter"]
        for i, x in enumerate(inputs):
            head.append(f"  let x{i}Bits UInt64 {bits(x)}")
        stmts = [":begin"]
        for i in range(len(inputs)):
            stmts.append(f"  read{i}: wide{i} = convert.uint64BitsToFloat64(x{i}Bits)")
            arg = f"wide{i}"
            if single:
                stmts.append(f"  narrow{i}: single{i} = convert.float64ToFloat32(wide{i})")
                arg = f"single{i}"
            if signed:
                stmts.append(f"  block{i}: place{i} = *allocate(count{i}=32, size{i}=1)")
                stmts.append(f"  call{i}: result{i} = *callee({arg}, place{i})")
            else:
                stmts.append(f"  call{i}: result{i} = *callee({arg})")
            if single:
                stmts.append(f"  widen{i}: shown{i} = convert.float32ToFloat64(result{i})")
            shown = f"shown{i}" if single else f"result{i}"
            stmts.append(f"  show{i}: sayDouble({shown})")
            if signed:
                stmts.append(f"  length{i}: measured{i} = *measure(place{i})")
                stmts.append(f"  showSign{i}: sayNumber(measured{i})")
        stmts.append("  return")
        ops.append("\n".join(head + stmts))
        extra = ", callocFn, strlenFn" if signed else ""
        ident = name.replace("_", "")
        body.append(f'  bind{ident}: {ident}Fn = {kind}Binding.bind(libc, {ident}Name="{name}") ? failed\n'
                    f"  run{ident}: {opname}({ident}Fn{extra})")
    return f'''module cmathspecialtour "Call the special functions of math.h through ffi and print what each gives"
  path cmathspecialtour
  imports standard.console standard.ffi standard.convert
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

capability cLibrary "Authority to load the C library and nothing else" load ffi.libraries "c"

{chr(10).join(c + chr(10) for c in caps)}
optype DoubleFunction "double f(double)"
  input value Float64 copied
  output Float64

optype FloatFunction "float f(float)"
  input value Float32 copied
  output Float32

optype SignedDoubleFunction "double lgamma_r(double, int *)"
  input value Float64 copied
  input sign Int64 copied
  output Float64

optype SignedFloatFunction "float lgammaf_r(float, int *)"
  input value Float32 copied
  input sign Int64 copied
  output Float32

optype AllocFunction "void *calloc(size_t, size_t), the address as a whole number"
  input count Int64 copied
  input size Int64 copied
  output Int64

optype LengthFunction "size_t strlen(const char *)"
  input text Int64 copied
  output Int64

instance DoubleBinding "Binds a C function of a double" ffi.Function DoubleFunction

instance FloatBinding "Binds a C function of a float" ffi.Function FloatFunction

instance SignedDoubleBinding "Binds lgamma_r" ffi.Function SignedDoubleFunction

instance SignedFloatBinding "Binds lgammaf_r" ffi.Function SignedFloatFunction

instance AllocBinding "Binds calloc" ffi.Function AllocFunction

instance LengthBinding "Binds strlen" ffi.Function LengthFunction

op sayDouble "Write a double on a line, as repr writes it"
  input value Float64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  write: console.writeFloatLine(value) ~
  return

op sayNumber "Write a whole number on a line"
  input value Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  write: console.writeIntegerLine(value) ~
  return

{chr(10).join(ops)}

op main "Open the C library, call each function, and report"
  output ExitCode
  effect load ffi.libraries
  effect load ffi.symbols
  effect write console.stdout
  uses cLibrary
{uses}
  uses stdoutWriter
  let okCode ExitCode 0
  let failCode ExitCode 1
:begin
  openIt: libc = ffi.open(cName="c") ? failedOpen
  bindcalloc: callocFn = AllocBinding.bind(libc, callocName="calloc") ? failed
  bindstrlen: strlenFn = LengthBinding.bind(libc, strlenName="strlen") ? failed
{chr(10).join(body)}
  closeIt: ffi.close(libc)
  return okCode
:failed
  closeFailed: ffi.close(libc)
  return failCode
:failedOpen
  return failCode
'''


def write_project(folder: str) -> None:
    """The project: build.sem and cmathspecialtour.sem, generated from the DSL above."""
    from semgen import Generator, Module, Program
    from caselib import allows_rows
    dsl = _dsl()
    prog = Program()
    m = Module("cmathspecialtour")
    prog.modules["cmathspecialtour"] = m
    g = Generator(prog, m)
    g.declare(dsl)
    g.parse(dsl)
    sem, _tests = g.render(["# The special functions of math.h through ffi (tests/cmathspecialtour.py)."], None)
    owner, target, lines = "", "", []
    for line in sem.split("\n"):
        parts = line.split()
        if len(parts) == 3 and parts[1] == "in":
            owner = parts[2]
        if len(parts) == 3 and parts[1] == "invokes":
            target = parts[2]
        if len(parts) == 3 and parts[1] == "ownedBy" and parts[2] == "none" and target == "ffi.open":
            line = line.replace("ownedBy none", f"ownedBy {owner}")
        lines.append(line)
    sem = "\n".join(lines)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "cmathspecialtour.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(sem)
    rows = ["tourProject is project", 'tourProject purpose "Call the special functions of math.h through ffi"',
            "tourProject target console", 'tourProject version "0.1.0"', "tourProject language refined 1",
            "tourProject standardLibrary 1", *allows_rows("tourProject", [sem]), "tourProject requires none",
            "tourProject includesModule cmathspecialtour", "tourProject entry cmathspecialtour.main"]
    with open(os.path.join(folder, "build.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")


def expected_sign(x: float) -> int:
    """The sign lgamma_r stores: 1 at NaN, infinity and the negative whole numbers, -1 at -0, else gamma(x)'s sign."""
    if math.isnan(x) or math.isinf(x) or (x < 0 and x == math.floor(x)):
        return 1
    return lgamma_sign(x)
