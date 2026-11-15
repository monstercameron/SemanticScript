"""A program that calls the runtime's exact math functions and fenv.h through `ffi` and prints what each gives
(module `cmathbits`).

tests/test_c_cmathbits.py builds it with the runtime in SemanticScript, requires what it prints to be what
`expected()` computes here from models of the functions written in Python (exact rational arithmetic, so each
function's bound is bit-exact), and on Linux requires it to print what `refined run` prints, which calls glibc.

Every result is printed as bits: a double's 64 bits as a signed whole number (a float is widened first, which is
exact and keeps a NaN's payload), an int or long as itself, and what a function stores through a pointer is read
back a byte at a time with memchr. `nexttoward` is not in the tour: its second argument is a long double, which
x86_64 passes in an x87 slot the library's ABI cannot take.
"""
from __future__ import annotations

import math
import os
import struct
import sys
from fractions import Fraction

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "docs", "refined-examples", "stage0", "tools"))

# format: (precision, least unit exponent, greatest exponent)
FMT = {"d": (53, -1074, 1023), "f": (24, -149, 127)}
INT_MIN = -2 ** 31
INT_MAX = 2 ** 31 - 1
LONG_MIN = -2 ** 63
INF = math.inf


def dbits(x: float) -> int:
    return struct.unpack("<q", struct.pack("<d", x))[0]


def fbits(x: float) -> int:
    return struct.unpack("<I", struct.pack("<f", x))[0]


def from_dbits(b: int) -> float:
    return struct.unpack("<d", struct.pack("<Q", b & (2 ** 64 - 1)))[0]


def from_fbits(b: int) -> float:
    return struct.unpack("<f", struct.pack("<I", b))[0]


def _exp2(fr: Fraction) -> int:
    e = fr.numerator.bit_length() - fr.denominator.bit_length()
    return e if Fraction(2) ** e <= fr else e - 1


def rnd(fr: Fraction, t: str) -> float:
    """A rational number rounded once to nearest even in a format, as a double: an overflow is infinity."""
    p, umin, emax = FMT[t]
    if fr == 0:
        return 0.0
    neg = fr < 0
    a = abs(fr)
    u = max(_exp2(a) - (p - 1), umin)
    q = a / Fraction(2) ** u
    n = q.numerator // q.denominator
    rem = q - n
    if rem > Fraction(1, 2) or (rem == Fraction(1, 2) and n % 2 == 1):
        n += 1
    val = n * Fraction(2) ** u
    r = INF if val >= Fraction(2) ** (emax + 1) else float(val)
    return -r if neg else r


def conv(x: float, t: str) -> float:
    """A double in a format: rounded once, a NaN's payload cut to the format's."""
    if t == "d":
        return x
    if x != x or math.isinf(x):
        return from_fbits(fbits(x)) if x == x else from_fbits(fbits(x))
    if x == 0:
        return x
    return rnd(Fraction(x), "f")


def small(t: str, x: float) -> float:
    return conv(x, t)


# ---------------------------------------------------------------- models (the target is x86_64 unless `arm`)

class Models:
    def __init__(self, arm: bool = False):
        self.arm = arm
        self.round_mode = 0  # 0 nearest, 1 down, 2 up, 3 toward zero
        self.flags = 0
        self.default_nan = from_dbits(0x7ff8000000000000 if arm else -0x8000000000000)

    # frexp
    def frexp(self, t, x):
        if x != x or math.isinf(x) or x == 0:
            return conv(x + x, t), [0]
        m, e = math.frexp(x)
        return m, [e]

    def ldexp(self, t, x, n):
        if x != x or math.isinf(x) or x == 0:
            return conv(x + x, t)
        n = max(-5000, min(5000, n))
        r = rnd(Fraction(x) * Fraction(2) ** n, t)
        return math.copysign(r, x) if r == 0 else r

    scalbn = ldexp
    scalbln = ldexp

    def ilogb(self, t, x):
        if x == 0 or x != x:
            return INT_MIN
        if math.isinf(x):
            return INT_MAX
        return math.frexp(x)[1] - 1

    def logb(self, t, x):
        if x == 0:
            return -INF
        if x != x or math.isinf(x):
            return x * x
        return float(math.frexp(x)[1] - 1)

    def modf(self, t, x):
        if x != x:
            return x + x, [x + x]
        f, w = math.modf(x)
        return f, [w]

    def _round(self, x, mode):
        if x != x or math.isinf(x):
            return x + x
        if x == 0:
            return x
        fr = Fraction(x)
        if mode == 0:
            n = round(fr)
        elif mode == 1:
            n = math.floor(fr)
        elif mode == 2:
            n = math.ceil(fr)
        elif mode == 3:
            n = math.trunc(fr)
        else:
            n = math.floor(abs(fr) + Fraction(1, 2)) * (1 if fr > 0 else -1)
        return math.copysign(0.0, x) if n == 0 else float(n)

    def rint(self, t, x):
        return self._round(x, self.round_mode)

    nearbyint = rint

    def _long(self, r):
        if r != r or not -2.0 ** 63 <= r < 2.0 ** 63:
            if self.arm:
                return 0 if r != r else (2 ** 63 - 1 if r > 0 else LONG_MIN)
            return LONG_MIN
        return int(r)

    def lrint(self, t, x):
        return self._long(self._round(x, self.round_mode))

    llrint = lrint

    def lround(self, t, x):
        return self._long(self._round(x, 4))

    llround = lround

    def remainder(self, t, x, y):
        return self.remquo(t, x, y)[0]

    def remquo(self, t, x, y):
        if x != x:
            return x, [0]
        if y != y:
            return y, [0]
        if y == 0 or math.isinf(x):
            return self.default_nan, [0]
        if math.isinf(y) or x == 0:
            return x, [0]
        q = abs(Fraction(x) / Fraction(y))
        n = round(q)
        up = n > math.floor(q)
        low = n & 7
        if low == 0 and up:
            low = 8
        r = Fraction(x) - (n if (x > 0) == (y > 0) else -n) * Fraction(y)
        res = math.copysign(0.0, x) if r == 0 else float(r)
        neg = (math.copysign(1.0, x) < 0) != (math.copysign(1.0, y) < 0)
        return res, [-low if neg else low]

    def fdim(self, t, x, y):
        if x <= y:
            return 0.0
        return conv(x - y, t)

    def fmax(self, t, x, y):
        return x if (x >= y or y != y) else y

    def fmin(self, t, x, y):
        return x if (x <= y or y != y) else y

    def fma(self, t, x, y, z):
        specials = any(v != v or math.isinf(v) or v == 0 for v in (x, y, z))
        if specials:
            r = x * y + z
            if r != r and not any(v != v for v in (x, y, z)):
                return self.default_nan
            return conv(r, t)
        r = rnd(Fraction(x) * Fraction(y) + Fraction(z), t)
        if r == 0:
            if Fraction(x) * Fraction(y) + Fraction(z) == 0:
                return 0.0
            neg = (Fraction(x) * Fraction(y)) < 0 if abs(Fraction(x) * Fraction(y)) > abs(Fraction(z)) else z < 0
            return -0.0 if neg else 0.0
        return r

    def nextafter(self, t, x, y):
        if x != x or y != y:
            return conv(x + y, t)
        if x == y:
            return y
        if t == "d":
            return math.nextafter(x, y)
        if x == 0:
            return from_fbits((fbits(y) & 0x80000000) | 1)
        b = fbits(x)
        away = (x < y) == (x > 0)
        return from_fbits(b + 1 if away else b - 1)

    def nan(self, t, tag):
        n = 0
        while n < len(tag) and (tag[n] in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"):
            n += 1
        payload = 0
        stop = tag[n] if n < len(tag) else ""
        if stop in ("", ")") and n > 0:
            s = tag[:n]
            if len(s) >= 3 and s[0] == "0" and s[1] in "xX":
                base, digits = 16, s[2:]
            elif s[0] == "0" and len(s) >= 2:
                base, digits = 8, s[1:]
            else:
                base, digits = 10, s
            try:
                payload = int(digits, base)
                if digits.startswith(("_",)) or "_" in digits:
                    payload = 0
            except ValueError:
                payload = 0
            payload = min(payload, 2 ** 64 - 1)
        if t == "d":
            return from_dbits(0x7ff8000000000000 | (payload & 0x7ffffffffffff))
        return from_fbits(0x7fc00000 | (payload & 0x3fffff))


# ---------------------------------------------------------------- inputs

def _lcg(seed: int):
    state = seed
    while True:
        state = (state * 6364136223846793005 + 1442695040888963407) % 2 ** 64
        yield state


def _sweep_doubles(count: int, seed: int) -> list[float]:
    out = []
    gen = _lcg(seed)
    while len(out) < count:
        b = next(gen)
        x = from_dbits(b)
        if x == x and not math.isinf(x):
            out.append(x)
    return out


def _sweep_floats(count: int, seed: int) -> list[float]:
    out = []
    gen = _lcg(seed)
    while len(out) < count:
        x = from_fbits(next(gen) >> 32)
        if x == x and not math.isinf(x):
            out.append(x)
    return out


NAN_PAYLOAD_D = from_dbits(0x7ff8000000000123)
NAN_NEGATIVE_D = from_dbits(-0x8000000000000)
NAN_PAYLOAD_F = from_fbits(0x7fc00123)

DOUBLES = [0.0, -0.0, 0.5, -0.5, 1.5, -1.5, 2.5, -2.5, 0.49999999999999994, 0.5000000000000001, 1.0, -1.0, 3.75, -3.75,
           4503599627370495.5, 4503599627370497.0, 1e300, -1e300, 5e-324, -5e-324, 2.2250738585072014e-308,
           2.225073858507201e-308, 1.7976931348623157e308, INF, -INF, math.nan, NAN_NEGATIVE_D, NAN_PAYLOAD_D, 0.1,
           1e22, 123456.789, 9223372036854775808.0, -9223372036854775808.0, 9223372036854774784.0, 2147483647.5,
           2147483648.0, 0.9999999999999999, 7.0, 1024.0, 2.0 ** -1022, 3.0 * 2.0 ** -1074] + _sweep_doubles(14, 11)
FLOATS = [0.0, -0.0, 0.5, -0.5, 1.5, -1.5, 2.5, -2.5, 0.49999997, 1.0, -1.0, 3.75, 8388607.5, 8388609.0, 16777216.0,
          3.4028234663852886e38, -3.4028234663852886e38, 1.401298464324817e-45, -1.401298464324817e-45,
          1.1754943508222875e-38, 1.1754942106924411e-38, INF, -INF, math.nan, from_fbits(0xffc00000), NAN_PAYLOAD_F,
          0.1, 1e10, 123456.789, 2147483648.0, 9223372036854775808.0, 1.8446744073709552e19, 7.0, 1024.0] \
    + _sweep_floats(14, 17)
FLOATS = [conv(x, "f") for x in FLOATS]

EXPONENTS = [0, 1, -1, 3, -3, 52, -52, 53, 100, -100, 1023, -1023, 1024, -1024, 1074, -1074, 1075, -1075, 2000, -2000,
             6000, -6000, 2147483647, -2147483648, 24, -24, 127, -127, 128, -128, 149, -149, 150, -150]
LONGS = [0, 1, -1, 1024, -1074, 2 ** 40, -(2 ** 40), 2 ** 62, -(2 ** 62), 2 ** 63 - 1, -(2 ** 63)]

PAIR_D = [(7.5, 2.0), (-7.5, 2.0), (7.5, -2.0), (-7.5, -2.0), (1.0, 0.1), (0.3, 0.1), (1e300, 3e-300), (5e-324, 3e-310),
          (3e-310, 5e-324), (-0.0, 1.0), (0.0, -1.0), (1.0, 0.0), (INF, 1.0), (-INF, 1.0), (1.0, INF), (1.0, -INF),
          (1.0, math.nan), (math.nan, 1.0), (math.nan, math.nan), (NAN_PAYLOAD_D, 2.0), (2.0, 3.0), (-3.0, 3.0),
          (3.0, 3.0), (2.5, 1.0), (3.5, 1.0), (1.5, 1.0), (0.5, 1.0), (-0.5, 1.0), (0.25, 1.0), (7.0, 4.0), (8.0, 1.0),
          (7.75, 1.0), (15.5, 1.0), (16.0, 1.0), (16.0, 3.0), (1e22, 7.0), (1e308, 1e-308), (1e-308, 1e308),
          (1.7976931348623157e308, 5e-324), (1.7976931348623157e308, 1.7976931348623157e308),
          (1.7976931348623157e308, -1.7976931348623157e308), (5e-324, 5e-324), (5e-324, 1.0), (1.0, 5e-324),
          (2.2250738585072014e-308, 5e-324), (4503599627370496.0, 3.0), (9007199254740993.0, 2.0),
          (-1.0, -1.0), (1.0, 3.0), (-1e-320, 3e-320), (123456789.0, 0.001), (INF, INF), (INF, -INF), (INF, 0.0),
          (-5.0, INF), (5.0, 2.0 ** 1000), (2.0 ** 1000, 3.0)] + list(zip(_sweep_doubles(8, 23), _sweep_doubles(8, 29)))
PAIR_F = [(conv(a, "f"), conv(b, "f")) for a, b in PAIR_D[:-8]] + \
    list(zip(_sweep_floats(8, 31), _sweep_floats(8, 37)))

TRIPLE_D = [(2.0, 3.0, 4.0), (1.0 + 2.0 ** -52, 1.0 - 2.0 ** -52, -1.0), (0.1, 10.0, -1.0), (1e308, 10.0, -1e308),
            (1e308, 10.0, 1e308), (1e-200, 1e-200, 1e-300), (1e-200, 1e-200, -1e-300), (3.0, 2.0 ** -1074, 0.0),
            (2.0 ** -1074, 0.5, 0.0), (2.0 ** -1074, 0.5, 2.0 ** -1074), (2.0 ** -1074, 0.5, -2.0 ** -1074),
            (2.0 ** -537, 2.0 ** -537, 0.0), (2.0 ** -537, 2.0 ** -538, 2.0 ** -1074), (-1.0, 1.0, 1.0),
            (-1.0, 1.0, -0.0), (0.0, 1.0, -0.0), (-0.0, 1.0, -0.0), (0.0, INF, 1.0), (INF, 2.0, -INF),
            (INF, 2.0, 1.0), (2.0, 3.0, math.nan), (math.nan, 3.0, 1.0), (2.0, NAN_PAYLOAD_D, 1.0),
            (1.7976931348623157e308, 2.0, -1.7976931348623157e308), (1.7976931348623157e308, 1.0, 1e292),
            (1.7976931348623157e308, 1.0, 1e291), (9007199254740993.0, 1.0, 0.0), (1.0, 1.0, 2.0 ** -53),
            (1.0, 1.0, 2.0 ** -54), (1.0, 1.0 + 2.0 ** -52, 2.0 ** -106), (1.0, 1.0 + 2.0 ** -52, -2.0 ** -106),
            (134217729.0, 134217727.0, -1.0), (3.0, 1.0 / 3.0, -1.0), (1e-160, 1e-160, 1e-320),
            (1e150, 1e150, -1e300), (1.5, 2.0 ** -1073, 2.0 ** -1074)] + \
    list(zip(_sweep_doubles(10, 41), _sweep_doubles(10, 43), _sweep_doubles(10, 47)))
TRIPLE_F = [tuple(conv(v, "f") for v in t) for t in TRIPLE_D[:-10]] + \
    [(2.0 ** -75, 2.0 ** -75, 2.0 ** -150), (3.0, 0.1, -0.30000001192092896), (16777217.0, 1.0, 0.0),
     (1.0 + 2.0 ** -23, 1.0 + 2.0 ** -23, -1.0), (1.0, 1.0, 2.0 ** -24), (1.0, 1.0, 2.0 ** -25),
     (1.0, 1.0, 2.0 ** -25 + 2.0 ** -60), (3.4028234663852886e38, 2.0, -3.4028234663852886e38),
     (3.4028234663852886e38, 1.0, 1e31), (3.4028234663852886e38, 1.0, 1e30), (2.0 ** -126, 2.0 ** -23, 0.0),
     (2.0 ** -126, 0.5 + 2.0 ** -24, 0.0)] + \
    list(zip(_sweep_floats(8, 53), _sweep_floats(8, 59), _sweep_floats(8, 61)))
TRIPLE_F = [tuple(conv(v, "f") for v in t) for t in TRIPLE_F]

NAN_TAGS = ["", "1", "123", "0x1f", "077", "0", "ff", "abc", "12ab", "18446744073709551615", "18446744073709551616",
            "0x", "-1", "5)7", "0X7F", "00", "0xffffffffffffffff", "0x1ffffffffffffffff", "99999999999", "08", "0x8000",
            "4503599627370496", "2251799813685248", "4194304", "_1"]

ROUND_INPUTS = [2.5, -2.5, 0.3, -0.3, 1.5, -1.5, 3.0, 0.5, -0.5, 1e300, -0.0, 4503599627370497.0, 2147483648.5]
MODES_X86 = {"nearest": 0, "down": 0x400, "up": 0x800, "zero": 0xc00}
MODES_ARM = {"nearest": 0, "up": 0x400000, "down": 0x800000, "zero": 0xc00000}

# (C name, float or double, the kinds of its arguments, its result kind, its inputs)
# kinds: F the float type, I int, L long, PI a pointer to int (read back after), PT a pointer to the float type
FUNCS = []


def _add(name, ins, out, inputs_d, inputs_f):
    FUNCS.append((name, "d", ins, out, inputs_d))
    FUNCS.append((name + "f", "f", ins, out, inputs_f))


def _singles(values):
    return [(v,) for v in values]


def _with(values, others):
    return [(v, o) for v in values for o in others]


def _no_mixed_zero(pairs):
    return [(a, b) for a, b in pairs if not (a == 0 and b == 0 and math.copysign(1, a) != math.copysign(1, b))]


_add("frexp", ["F", "PI"], "F", _singles(DOUBLES), _singles(FLOATS))
_add("ldexp", ["F", "I"], "F", _with(DOUBLES[:30], EXPONENTS[:30]), _with(FLOATS[:30], EXPONENTS))
_add("scalbn", ["F", "I"], "F", _with(DOUBLES[8:26], EXPONENTS), _with(FLOATS[8:26], EXPONENTS))
_add("scalbln", ["F", "L"], "F", _with(DOUBLES[8:26], LONGS), _with(FLOATS[8:26], LONGS))
_add("ilogb", ["F"], "I", _singles(DOUBLES), _singles(FLOATS))
_add("logb", ["F"], "F", _singles(DOUBLES), _singles(FLOATS))
_add("modf", ["F", "PT"], "F", _singles(DOUBLES), _singles(FLOATS))
_add("rint", ["F"], "F", _singles(DOUBLES), _singles(FLOATS))
_add("nearbyint", ["F"], "F", _singles(DOUBLES), _singles(FLOATS))
_add("lrint", ["F"], "L", _singles(DOUBLES), _singles(FLOATS))
_add("llrint", ["F"], "L", _singles(DOUBLES), _singles(FLOATS))
_add("lround", ["F"], "L", _singles(DOUBLES), _singles(FLOATS))
_add("llround", ["F"], "L", _singles(DOUBLES), _singles(FLOATS))
_add("remainder", ["F", "F"], "F", PAIR_D, PAIR_F)
_add("remquo", ["F", "F", "PI"], "F", PAIR_D, PAIR_F)
_add("fdim", ["F", "F"], "F", PAIR_D, PAIR_F)
_add("fmax", ["F", "F"], "F", _no_mixed_zero(PAIR_D), _no_mixed_zero(PAIR_F))
_add("fmin", ["F", "F"], "F", _no_mixed_zero(PAIR_D), _no_mixed_zero(PAIR_F))
_add("fma", ["F", "F", "F"], "F", TRIPLE_D, TRIPLE_F)
_add("nextafter", ["F", "F"], "F", PAIR_D, PAIR_F)
FENV = ["feclearexcept", "feraiseexcept", "fetestexcept", "fegetround", "fesetround", "fegetexceptflag",
        "fesetexceptflag", "fegetenv", "fesetenv", "feholdexcept", "feupdateenv"]
# the C names the tour binds, and the names of the C library the table check expects of this module
NAMES = [f[0] for f in FUNCS] + ["nan", "nanf"] + FENV


def _inputs_of(entry):
    """The inputs of a float function made exact in its type."""
    name, t, ins, out, inputs = entry
    return [tuple(conv(v, t) if isinstance(v, float) else v for v in row) for row in inputs]


def _signature_inputs(entry):
    """The values of the non-pointer arguments, as the tour gives them."""
    return _inputs_of(entry)


def expected_lines(entry, models: Models) -> list[str]:
    name, t, ins, out, _ = entry
    base = name[:-1] if t == "f" else name
    fn = getattr(models, base)
    lines = []
    for row in _inputs_of(entry):
        got = fn(t, *row)
        extra = []
        if isinstance(got, tuple):
            got, extra = got
        if out == "F":
            lines.append(str(dbits(got)))
        else:
            lines.append(str(got))
        for kind, value in zip([k for k in ins if k.startswith("P")], extra):
            if kind == "PI":
                lines.append(str(value))
            else:
                lines.append(str(dbits(value)) if t == "d" else str(fbits(value)))
    return lines


def expected(arm: bool = False) -> list[str]:
    models = Models(arm)
    lines = []
    for entry in FUNCS:
        name = entry[0]
        base = name[:-1] if entry[1] == "f" else name
        if base in ("rint", "nearbyint", "lrint", "llrint", "lround", "llround") or True:
            models.round_mode = 0
        lines += expected_lines(entry, models)
    for t in "df":
        for tag in NAN_TAGS:
            v = models.nan(t, tag)
            lines.append(str(dbits(v)))
    lines += fenv_expected(arm)
    return lines


# ---------------------------------------------------------------- fenv.h: one script, run by the tour and by a model

def fenv_constants(arm: bool):
    """(invalid, divide by zero, overflow, underflow, inexact, all, modes by name) as the target's fenv.h has them."""
    if arm:
        return 1, 2, 4, 8, 16, 31, MODES_ARM
    return 1, 4, 8, 16, 32, 0x3d, MODES_X86


def fenv_script(arm: bool):
    inv, div, ovf, unf, inx, allx, modes = fenv_constants(arm)
    steps = [("clear", allx), ("test", allx), ("raise", ovf | inx), ("test", allx), ("test", ovf), ("test", div),
             ("clear", inx), ("test", allx), ("raise", inv), ("raise", 0x40), ("test", allx),
             ("getflag", allx), ("clear", allx), ("test", allx), ("setflag", ovf), ("test", allx),
             ("setflag", allx), ("test", allx),
             ("getenv", "env1"), ("clear", allx), ("raise", div), ("test", allx), ("hold", "env2"), ("test", allx),
             ("setenv", "env1"), ("test", allx), ("update", "env2"), ("test", allx), ("setenv", "default"),
             ("test", allx),
             ("clear", allx), ("call", "nearbyint", 2.5), ("test", inx), ("call", "rint", 2.5), ("test", inx),
             ("clear", allx), ("call", "lrint", 1e30), ("test", allx), ("clear", allx), ("call", "lrint", 2.5),
             ("test", allx), ("clear", allx), ("call", "rint", 3.0), ("test", allx), ("getround",)]
    for name in ("down", "up", "zero", "nearest"):
        steps += [("setround", modes[name]), ("getround",), ("rints",)]
    steps += [("setround", 0x123), ("getround",)]
    return steps


def fenv_expected(arm: bool) -> list[str]:
    inv, _div, _ovf, _unf, inx, allx, modes = fenv_constants(arm)
    flags, mode, cell, envs = 0, 0, 0, {}
    ext = {0: modes["nearest"], 1: modes["down"], 2: modes["up"], 3: modes["zero"]}
    models = Models(arm)
    out = []
    for step in fenv_script(arm):
        kind = step[0]
        if kind == "clear":
            flags &= ~(step[1] & allx)
            out.append("0")
        elif kind == "raise":
            flags |= step[1] & allx
            out.append("0")
        elif kind == "test":
            out.append(str(flags & step[1] & allx))
        elif kind == "getflag":
            cell = flags & step[1] & allx
            out += ["0", str(cell)]
        elif kind == "setflag":
            sel = step[1] & allx
            flags = (flags & ~sel) | (cell & sel)
            out.append("0")
        elif kind == "getenv":
            envs[step[1]] = (flags, mode)
            out.append("0")
        elif kind == "hold":
            envs[step[1]] = (flags, mode)
            flags = 0
            out.append("0")
        elif kind == "setenv":
            flags, mode = (0, 0) if step[1] == "default" else envs[step[1]]
            out.append("0")
        elif kind == "update":
            raised = flags
            flags, mode = envs[step[1]]
            flags |= raised
            out.append("0")
        elif kind == "getround":
            out.append(str(ext[mode]))
        elif kind == "setround":
            known = [i for i, v in ext.items() if v == step[1]]
            if known:
                mode = known[0]
                out.append("0")
            else:
                out.append("1")
        elif kind == "call":
            _, fn, x = step
            if fn == "lrint":
                out.append(str(models.lrint("d", x)))
                if not (-2.0 ** 63 <= x < 2.0 ** 63):
                    flags |= inv & allx
                elif x != math.floor(x):
                    flags |= inx & allx
            else:
                out.append(str(dbits(models.rint("d", x))))
                if fn == "rint" and x != math.floor(x):
                    flags |= inx & allx
        elif kind == "rints":
            models.round_mode = mode
            for x in ROUND_INPUTS:
                out += [str(dbits(models.rint("d", x))), str(models.lrint("d", x))]
    return out


# ---------------------------------------------------------------- the program

def _bits_literal(x: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def _type(kind: str, t: str) -> str:
    return {"F": "Float64" if t == "d" else "Float32", "I": "Int32", "L": "Int64", "PI": "Int64", "PT": "Int64"}[kind]


def _optype_name(ins, out, t):
    return "Fn" + "".join(ins) + "To" + out + t.upper()


def _optypes() -> str:
    seen, text = set(), []
    for name, t, ins, out, _ in FUNCS:
        key = _optype_name(ins, out, t)
        if key in seen:
            continue
        seen.add(key)
        text.append(f'optype {key} "The foreign function type of {name}"')
        for i, k in enumerate(ins):
            text.append(f"  input arg{i} {_type(k, t)} copied")
        text.append(f"  output {_type(out, t)}")
        text.append("")
        text.append(f'instance {key}Binding "Binds a function of this shape" ffi.Function {key}')
        text.append("")
    return "\n".join(text)


def _show_result(out: str, t: str, i: int) -> list[str]:
    if out == "F" and t == "d":
        return [f"  rb{i}: rbits{i} = convert.float64BitsToUInt64(r{i})",
                f"  rs{i}: rsigned{i} = convert.uint64BitsToInt64(rbits{i})", f"  show{i}: sayNumber(rsigned{i})"]
    if out == "F":
        return [f"  rw{i}: rwide{i} = convert.float32ToFloat64(r{i})",
                f"  rb{i}: rbits{i} = convert.float64BitsToUInt64(rwide{i})",
                f"  rs{i}: rsigned{i} = convert.uint64BitsToInt64(rbits{i})", f"  show{i}: sayNumber(rsigned{i})"]
    if out == "I":
        return [f"  rw{i}: rwide{i} = convert.int32ToInt64(r{i})", f"  show{i}: sayNumber(rwide{i})"]
    return [f"  show{i}: sayNumber(r{i})"]


def _run_op(entry) -> str:
    name, t, ins, out, _ = entry
    rows = _inputs_of(entry)
    pointer = any(k.startswith("P") for k in ins)
    lets, body = [], []
    for i, row in enumerate(rows):
        args, vi = [], 0
        for j, k in enumerate(ins):
            if k == "F":
                lets.append(f"  let a{i}x{j}Bits UInt64 {_bits_literal(row[vi])}")
                body.append(f"  rd{i}x{j}: a{i}x{j} = convert.uint64BitsToFloat64(a{i}x{j}Bits)")
                if t == "f":
                    body.append(f"  nr{i}x{j}: a{i}x{j}s = convert.float64ToFloat32(a{i}x{j})")
                    args.append(f"a{i}x{j}s")
                else:
                    args.append(f"a{i}x{j}")
                vi += 1
            elif k in ("I", "L"):
                args.append(f"n{i}x{j}={row[vi]}")
                vi += 1
            else:
                args.append("cell")
        if pointer:
            body.append(f"  clr{i}: cleared{i} = *setter(cell, zero{i}=0, size{i}=16)")
        body.append(f"  call{i}: r{i} = *callee({', '.join(args)})")
        body += _show_result(out, t, i)
        for j, k in enumerate(ins):
            if k == "PI":
                body += [f"  pk{i}: pv{i} = peekInt32(finder, cell)", f"  ps{i}: sayNumber(pv{i})"]
            elif k == "PT":
                reader = "peekWord" if t == "d" else "peekSingle"
                body += [f"  pk{i}: pv{i} = {reader}(finder, cell)", f"  ps{i}: sayNumber(pv{i})"]
    params = [f"  input callee {_optype_name(ins, out, t)} copied"]
    if pointer:
        params += ["  input finder FindFunction copied", "  input setter SetFunction copied", "  input cell Int64 copied"]
    nl = "\n"
    return f'''op run{name}Op "Call {name} with each of the tour's inputs and write what it gives"
{nl.join(params)}
  effect write console.stdout
  uses stdoutWriter
{nl.join(lets)}
:begin
{nl.join(body)}
  return
'''


def _nan_op(t: str) -> str:
    name = "nan" if t == "d" else "nanf"
    body = []
    for i, tag in enumerate(NAN_TAGS):
        for k, ch in enumerate(tag.encode() + b"\0"):
            body.append(f"  put{i}x{k}: putByteAt(setter, text, at{i}x{k}={k}, code{i}x{k}={ch})")
        body.append(f"  call{i}: r{i} = *callee(text)")
        body += _show_result("F", "d" if t == "d" else "f", i)
    nl = "\n"
    return f'''op run{name}Op "Call {name} with each of the tour's tags and write what it gives"
  input callee NanFn{t.upper()} copied
  input setter SetFunction copied
  input text Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
{nl.join(body)}
  return
'''


def _fenv_op(arm: bool) -> str:
    lines = []
    count = [0]

    def emit(kind: str, call: str):
        count[0] += 1
        i = count[0]
        lines.append(f"  fc{i}: fv{i} = *{call}")
        if kind == "I":
            lines.extend([f"  fw{i}: fx{i} = convert.int32ToInt64(fv{i})", f"  fs{i}: sayNumber(fx{i})"])
        else:
            lines.append(f"  fs{i}: sayNumber(fv{i})")

    for step in fenv_script(arm):
        kind = step[0]
        n = count[0] + 1
        if kind in ("clear", "raise", "test"):
            fn = {"clear": "clearFn", "raise": "raiseFn", "test": "testFn"}[kind]
            emit("I", f"{fn}(m{n}={step[1]})")
        elif kind in ("getflag", "setflag"):
            emit("I", f"{'getFlagFn' if kind == 'getflag' else 'setFlagFn'}(flagCell, m{n}={step[1]})")
            if kind == "getflag":
                count[0] += 1
                i = count[0]
                lines.extend([f"  fc{i}: fv{i} = peekInt32(finder, flagCell)", f"  fs{i}: sayNumber(fv{i})"])
        elif kind in ("getenv", "hold", "update", "setenv"):
            fn = {"getenv": "getEnvFn", "hold": "holdFn", "update": "updateFn", "setenv": "setEnvFn"}[kind]
            arg = {"env1": "env1", "env2": "env2"}.get(step[1], f"defaultEnv{n}=-1")
            emit("I", f"{fn}({arg})")
        elif kind == "getround":
            emit("I", "getRoundFn()")
        elif kind == "setround":
            emit("I", f"setRoundFn(m{n}={step[1]})")
        elif kind == "call":
            _, fn, x = step
            count[0] += 1
            i = count[0]
            lines.extend([f"  fr{i}: fa{i} = convert.uint64BitsToFloat64(fbits{i}={_bits_literal(x)})"])
            if fn == "lrint":
                lines.extend([f"  fl{i}: fe{i} = *lrintFn(fa{i})", f"  ft{i}: sayNumber(fe{i})"])
            else:
                lines.extend([f"  fi{i}: fb{i} = *{fn}Fn(fa{i})", f"  fj{i}: fc{i} = convert.float64BitsToUInt64(fb{i})",
                              f"  fk{i}: fd{i} = convert.uint64BitsToInt64(fc{i})", f"  fs{i}: sayNumber(fd{i})"])
        elif kind == "rints":
            for x in ROUND_INPUTS:
                count[0] += 1
                i = count[0]
                lines.extend([f"  fr{i}: fa{i} = convert.uint64BitsToFloat64(fbits{i}={_bits_literal(x)})",
                          f"  fi{i}: fb{i} = *rintFn(fa{i})",
                          f"  fj{i}: fc{i} = convert.float64BitsToUInt64(fb{i})",
                          f"  fk{i}: fd{i} = convert.uint64BitsToInt64(fc{i})", f"  fs{i}: sayNumber(fd{i})",
                          f"  fl{i}: fe{i} = *lrintFn(fa{i})", f"  ft{i}: sayNumber(fe{i})"])
    nl = "\n"
    return f'''op runfenvOp "Walk through fenv.h's functions and write what each gives"
  input clearFn IntFn copied
  input raiseFn IntFn copied
  input testFn IntFn copied
  input getRoundFn NoneFn copied
  input setRoundFn IntFn copied
  input getFlagFn PtrIntFn copied
  input setFlagFn PtrIntFn copied
  input getEnvFn PtrFn copied
  input setEnvFn PtrFn copied
  input holdFn PtrFn copied
  input updateFn PtrFn copied
  input rintFn RintFn copied
  input nearbyintFn RintFn copied
  input lrintFn LrintFn copied
  input finder FindFunction copied
  input flagCell Int64 copied
  input env1 Int64 copied
  input env2 Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
{nl.join(lines)}
  return
'''


FIXED_PART = '''
optype FindFunction "void *memchr(const void *, int, size_t)"
  input block Int64 copied
  input code Int32 copied
  input bytes Int64 copied
  output Int64

optype SetFunction "void *memset(void *, int, size_t)"
  input target Int64 copied
  input value Int32 copied
  input bytes Int64 copied
  output Int64

optype AllocFunction "void *calloc(size_t, size_t)"
  input count Int64 copied
  input size Int64 copied
  output Int64

optype NanFnD "double nan(const char *)"
  input tag Int64 copied
  output Float64

optype NanFnF "float nanf(const char *)"
  input tag Int64 copied
  output Float32

optype IntFn "int f(int)"
  input value Int32 copied
  output Int32

optype PtrIntFn "int f(void *, int)"
  input pointer Int64 copied
  input value Int32 copied
  output Int32

optype PtrFn "int f(void *)"
  input pointer Int64 copied
  output Int32

optype NoneFn "int f(void)"
  output Int32

optype RintFn "double rint(double)"
  input value Float64 copied
  output Float64

optype LrintFn "long lrint(double)"
  input value Float64 copied
  output Int64

instance FindBinding "Binds memchr" ffi.Function FindFunction

instance SetBinding "Binds memset" ffi.Function SetFunction

instance AllocBinding "Binds calloc" ffi.Function AllocFunction

instance NanBindingD "Binds the C function nan" ffi.Function NanFnD

instance NanBindingF "Binds the C function nanf" ffi.Function NanFnF

instance IntBinding "Binds a function of an int" ffi.Function IntFn

instance PtrIntBinding "Binds a function of a pointer and an int" ffi.Function PtrIntFn

instance PtrBinding "Binds a function of a pointer" ffi.Function PtrFn

instance NoneBinding "Binds a function of nothing" ffi.Function NoneFn

instance RintBinding "Binds rint" ffi.Function RintFn

instance LrintBinding "Binds lrint" ffi.Function LrintFn

op sayNumber "Write a whole number on a line"
  input value Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  write: console.writeIntegerLine(value) ~
  return

op putByteAt "Put one byte at an address moved on by an offset, through memset"
  input setter SetFunction copied
  input base Int64 copied
  input offset Int64 copied
  input code Int32 copied
:begin
  findAt: at = math.addInt64(base, offset)
  setIt: unused = *setter(at, code, one=1)
  return

op peekByte "The byte at an address, found by asking memchr for each value in turn"
  input finder FindFunction copied
  input address Int64 copied
  output Int64
  let candidate Int32 0 mut
  let limit Int64 300
:begin
  goto eachCandidate
:eachCandidate loop=while max=limit
  askIt: found = *finder(address, candidate, one=1)
  hitCheck: hit = compare.equalInt64(found, address)
  if hit done next
:next in=eachCandidate
  stepIt: stepped = math.addInt32(candidate, one32=1)
  set candidate stepped
  goto eachCandidate
:done
  widen: value = convert.int32ToInt64(candidate)
  return value

op peekWord "The eight bytes at an address, the lowest first, as a whole number"
  input finder FindFunction copied
  input address Int64 copied
  output Int64
:begin
  calc word = peekByte(finder, address) | (peekByte(finder, address + 1) << 8) | (peekByte(finder, address + 2) << 16) | (peekByte(finder, address + 3) << 24) | (peekByte(finder, address + 4) << 32) | (peekByte(finder, address + 5) << 40) | (peekByte(finder, address + 6) << 48) | (peekByte(finder, address + 7) << 56)
  return word

op peekSingle "The four bytes at an address, the lowest first, as a whole number below 2^32"
  input finder FindFunction copied
  input address Int64 copied
  output Int64
:begin
  calc word = peekByte(finder, address) | (peekByte(finder, address + 1) << 8) | (peekByte(finder, address + 2) << 16) | (peekByte(finder, address + 3) << 24)
  return word

op peekInt32 "The four bytes at an address as an int, in a whole number"
  input finder FindFunction copied
  input address Int64 copied
  output Int64
:begin
  word = peekSingle(finder, address)
  calc signed = (word ^ 2147483648) - 2147483648
  return signed
'''


def _dsl(arm: bool) -> str:
    nl = "\n"
    helper_names = ["calloc", "memchr", "memset"]
    caps = [f'capability {n}Symbol "Authority to bind the C function {n}" load ffi.symbols "{n}"'
            for n in NAMES + helper_names]
    uses = nl.join(f"  uses {c.split()[1]}" for c in caps)
    runs = nl.join(_run_op(e) for e in FUNCS)
    binds, calls = [], []
    for name, t, ins, out, _ in FUNCS:
        key = _optype_name(ins, out, t)
        binds.append(f'  bind{name}: {name}Fn = {key}Binding.bind(libc, {name}Name="{name}") ? failed')
        extra = ", finderFn, setFn, cell" if any(k.startswith("P") for k in ins) else ""
        calls.append(f"  run{name}: run{name}Op({name}Fn{extra})")
    for name, kind in (("nan", "D"), ("nanf", "F")):
        binds.append(f'  bind{name}: {name}Fn = NanBinding{kind}.bind(libc, {name}Name="{name}") ? failed')
        calls.append(f"  run{name}: run{name}Op({name}Fn, setFn, cell)")
    fe = {"feclearexcept": ("IntBinding", "clearFn"), "feraiseexcept": ("IntBinding", "raiseFn"),
          "fetestexcept": ("IntBinding", "testFn"), "fegetround": ("NoneBinding", "getRoundFn"),
          "fesetround": ("IntBinding", "setRoundFn"), "fegetexceptflag": ("PtrIntBinding", "getFlagFn"),
          "fesetexceptflag": ("PtrIntBinding", "setFlagFn"), "fegetenv": ("PtrBinding", "getEnvFn"),
          "fesetenv": ("PtrBinding", "setEnvFn"), "feholdexcept": ("PtrBinding", "holdFn"),
          "feupdateenv": ("PtrBinding", "updateFn")}
    for name, (binding, var) in fe.items():
        binds.append(f'  bindfe{name}: {var} = {binding}.bind(libc, {name}Name="{name}") ? failed')
    binds.append('  bindrintForModes: rintModeFn = RintBinding.bind(libc, rintName2="rint") ? failed')
    binds.append('  bindlrintForModes: lrintModeFn = LrintBinding.bind(libc, lrintName2="lrint") ? failed')
    binds.append('  bindnearbyintForModes: nearbyintModeFn = RintBinding.bind(libc, nearbyintName2="nearbyint") ? failed')
    calls.append("  runfenv: runfenvOp(clearFn, raiseFn, testFn, getRoundFn, setRoundFn, getFlagFn, setFlagFn, getEnvFn, "
                 "setEnvFn, holdFn, updateFn, rintModeFn, nearbyintModeFn, lrintModeFn, finderFn, flagCell, env1, env2)")
    return f'''module cmathbitstour "Call the runtime's exact math functions and fenv.h through ffi and print what each gives"
  path cmathbitstour
  imports standard.console standard.ffi standard.convert standard.compare standard.math standard.bits
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

capability cLibrary "Authority to load the C library and nothing else" load ffi.libraries "c"

{nl.join(c + nl for c in caps)}
{_optypes()}
{FIXED_PART}
{runs}
{_nan_op("d")}
{_nan_op("f")}
{_fenv_op(arm)}
op main "Open the C library, call each function, and write what it gives"
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
  bindmemchr: finderFn = FindBinding.bind(libc, memchrName="memchr") ? failed
  bindmemset: setFn = SetBinding.bind(libc, memsetName="memset") ? failed
  takeCell: cell = *callocFn(count=4, size=16)
  takeFlag: flagCell = *callocFn(count2=4, size2=16)
  takeEnv1: env1 = *callocFn(count3=8, size3=16)
  takeEnv2: env2 = *callocFn(count4=8, size4=16)
{nl.join(binds)}
{nl.join(calls)}
  closeIt: ffi.close(libc)
  return okCode
:failed
  closeFailed: ffi.close(libc)
  return failCode
:failedOpen
  return failCode
'''


def write_project(folder: str, arm: bool = False) -> None:
    """The project: build.sem and cmathbitstour.sem, generated from the DSL above."""
    from semgen import Generator, Module, Program
    from caselib import allows_rows
    dsl = _dsl(arm)
    prog = Program()
    m = Module("cmathbitstour")
    prog.modules["cmathbitstour"] = m
    g = Generator(prog, m)
    g.declare(dsl)
    g.parse(dsl)
    sem, _tests = g.render(["# The runtime's exact math functions through ffi (tests/cmathbitstour.py)."], None)
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
    with open(os.path.join(folder, "cmathbitstour.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(sem)
    rows = ["tourProject is project", 'tourProject purpose "Call the runtime\'s exact math functions through ffi"',
            "tourProject target console", 'tourProject version "0.1.0"', "tourProject language refined 1",
            "tourProject standardLibrary 1", *allows_rows("tourProject", [sem]), "tourProject requires none",
            "tourProject includesModule cmathbitstour", "tourProject entry cmathbitstour.main"]
    with open(os.path.join(folder, "build.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")
