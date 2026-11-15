"""The unit tests of cmathlong: a table of cases (function, layout, arguments, the expected correctly rounded result,
computed here with Python decimals at 150+ digits) read by one test op, on all three layouts (0 double, 1 x87, 2 binary128)
from any machine; the cases whose layout is this system's long double also go through the `abi library` operation.
(see cmathlonggen.py)"""
from __future__ import annotations

import math
import os
import sys
from decimal import Decimal as D, localcontext
from fractions import Fraction as F

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cmathlongbuild import ADDR, Op, ALL, new, ld, ldi, st, sti, LIM, HEAD, N
import cmathlongtables as T

PRECISION = {0: 53, 1: 64, 2: 113}
LEAST = {0: -1074, 1: -16445, 2: -16494}
GREATEST = {0: 971, 1: 16320, 2: 16271}

# ---------------------------------------------------------------- rounding to a layout


def round_value(layout: int, value: F):
    """(kind, sign, E, M) of a Fraction rounded to nearest even in the layout."""
    if value == 0:
        return (0, 0, 0, 0)
    sign = 1 if value < 0 else 0
    a = -value if sign else value
    p = PRECISION[layout]
    e = a.numerator.bit_length() - a.denominator.bit_length() - p
    while True:
        # M = a / 2^E should be in [2^(p-1), 2^p) for E = e
        if a >= F(2) ** (e + p):
            e += 1
        elif a < F(2) ** (e + p - 1):
            e -= 1
        else:
            break
    power = max(e, LEAST[layout])
    scaled = a / F(2) ** power
    m = scaled.numerator // scaled.denominator
    rest = scaled - m
    if rest > F(1, 2) or (rest == F(1, 2) and m % 2 == 1):
        m += 1
    if m == 0:
        return (0, sign, 0, 0)
    if m == 1 << p:
        m >>= 1
        power += 1
    if power > GREATEST[layout]:
        return (2, sign, 0, 0)
    return (1, sign, power, m)


# ---------------------------------------------------------------- the reference (decimals)


def pi_decimal(prec):
    bits = int(prec * 3.33) + 64
    return D(T.pi_fixed(bits)) / D(1 << bits)


def ctx_prec(extra=0):
    return 170 + extra


def dec(x: F) -> D:
    """a Fraction as an exact Decimal (its denominators are powers of two)"""
    with localcontext() as c:
        c.prec = int(x.numerator.bit_length() * 0.31 + x.denominator.bit_length() * 0.31) + 30
        return D(x.numerator) / D(x.denominator)


def ref_sincos(x: D):
    """(sin x, cos x)"""
    adj = max(0, x.adjusted())
    with localcontext() as c:
        c.prec = ctx_prec(adj + 10)
        pi = pi_decimal(c.prec)
        half = pi / 2
        n = int((x / half).to_integral_value())
        r = x - n * half
        # Taylor
        s = c_ = D(0)
        term, k = r, 1
        sn = D(0)
        t = r
        sn = r
        r2 = r * r
        for k in range(1, 400):
            t = -t * r2 / ((2 * k) * (2 * k + 1))
            sn += t
            if abs(t) < D(10) ** (-c.prec - 5) * max(abs(sn), D(10) ** -300):
                break
        t = D(1)
        cs = D(1)
        for k in range(1, 400):
            t = -t * r2 / ((2 * k - 1) * (2 * k))
            cs += t
            if abs(t) < D(10) ** (-c.prec - 5):
                break
        q = n % 4
        if q == 0:
            return sn, cs
        if q == 1:
            return cs, -sn
        if q == 2:
            return -sn, -cs
        return -cs, sn


def ref_atan(x: D) -> D:
    with localcontext() as c:
        c.prec = ctx_prec(20)
        neg = x < 0
        a = -x if neg else x
        flip = a > 1
        if flip:
            a = 1 / a
        for _ in range(4):
            a = a / (1 + (1 + a * a).sqrt())
        s = t = a
        a2 = a * a
        for k in range(1, 3000):
            t = -t * a2
            term = t / (2 * k + 1)
            s += term
            if abs(term) < D(10) ** (-c.prec - 5) * s:
                break
        s *= 16
        if flip:
            s = pi_decimal(c.prec) / 2 - s
        return -s if neg else s


def ref_erf(x: D) -> D:
    with localcontext() as c:
        c.prec = ctx_prec(int(float(x) ** 2 * 0.87) + 20)
        s = t = x
        x2 = x * x
        for n in range(1, 20000):
            t = -t * x2 / n
            term = t / (2 * n + 1)
            s += term
            if abs(term) < D(10) ** (-c.prec - 5):
                break
        return 2 / pi_decimal(c.prec).sqrt() * s


def ref_erfc(x: D) -> D:
    if x <= -8:
        with localcontext() as c:
            c.prec = 220
            return 2 - ref_erfc(-x)
    if x >= 8:
        with localcontext() as c:
            c.prec = 220
            t = x
            for k in range(4000, 0, -1):
                t = x + (D(k) / 2) / t
            return (-x * x).exp() / (pi_decimal(c.prec).sqrt() * t)
    extra = int(float(abs(x)) ** 2 * 0.87) + 20
    with localcontext() as c:
        c.prec = ctx_prec(2 * extra)
        return 1 - ref_erf(x)


def bernoulli():
    return T.bernoulli_numbers(200)


_B = None


def ref_lgamma_pos(z: D) -> D:
    global _B
    if _B is None:
        _B = bernoulli()
    with localcontext() as c:
        c.prec = ctx_prec(30)
        shift = D(0)
        prod = D(1)
        w = z
        while w < 80:
            prod *= w
            w += 1
        s = (w - D("0.5")) * w.ln() - w + (2 * pi_decimal(c.prec)).ln() / 2
        for k in range(1, 100):
            b = _B[2 * k]
            s += D(b.numerator) / D(b.denominator * 2 * k * (2 * k - 1)) / w ** (2 * k - 1)
        return s - prod.ln()


def ref_gamma(x: D):
    """(gamma(x), sign) for a finite non-pole x"""
    with localcontext() as c:
        c.prec = ctx_prec(30)
        if x > 0:
            return ref_lgamma_pos(x).exp()
        pi = pi_decimal(c.prec)
        s = ref_sincos(pi * x)[0]
        return pi / (s * ref_lgamma_pos(1 - x).exp())


def ref_lgamma(x: D) -> D:
    with localcontext() as c:
        c.prec = ctx_prec(30)
        if x > 0:
            return ref_lgamma_pos(x)
        pi = pi_decimal(c.prec)
        s = ref_sincos(pi * x)[0]
        return (pi / abs(s)).ln() - ref_lgamma_pos(1 - x)


def compute(name: str, args):
    """The exact value of a function at exact Fractions, as a Decimal (or a Fraction), or None for a special value."""
    a = dec(args[0])
    with localcontext() as c:
        c.prec = ctx_prec(40) + 2 * max(0, -a.adjusted()) if a != 0 else ctx_prec(40)
        if name == "sinl":
            return ref_sincos(a)[0]
        if name == "cosl":
            return ref_sincos(a)[1]
        if name == "tanl":
            s, co = ref_sincos(a)
            return s / co
        if name == "atanl":
            return ref_atan(a)
        if name == "asinl":
            return ref_atan(a / (1 - a * a).sqrt())
        if name == "acosl":
            return pi_decimal(c.prec) / 2 - ref_atan(a / (1 - a * a).sqrt())
        if name == "atan2l":
            y, x = a, dec(args[1])
            if x > 0:
                return ref_atan(y / x)
            if x < 0:
                base = ref_atan(y / x)
                return base + (pi_decimal(c.prec) if y >= 0 else -pi_decimal(c.prec))
            return pi_decimal(c.prec) / 2 * (1 if y > 0 else -1)
        if name == "expl":
            return a.exp()
        if name == "exp2l":
            return (a * D(2).ln()).exp()
        if name == "expm1l":
            return a.exp() - 1
        if name == "logl":
            return a.ln()
        if name == "log2l":
            return a.ln() / D(2).ln()
        if name == "log10l":
            return a.log10()
        if name == "log1pl":
            return (1 + a).ln()
        if name == "powl":
            y = dec(args[1])
            if a > 0:
                return (y * a.ln()).exp()
            r = (y * (-a).ln()).exp()
            return -r if (args[1].denominator == 1 and args[1].numerator % 2 == 1) else r
        if name == "cbrtl":
            r = (abs(a).ln() / 3).exp()
            return -r if a < 0 else r
        if name == "hypotl":
            return (a * a + dec(args[1]) ** 2).sqrt()
        if name == "sinhl":
            return (a.exp() - (-a).exp()) / 2
        if name == "coshl":
            return (a.exp() + (-a).exp()) / 2
        if name == "tanhl":
            e2 = (2 * a).exp()
            return (e2 - 1) / (e2 + 1)
        if name == "asinhl":
            return (abs(a) + (a * a + 1).sqrt()).ln() * (1 if a >= 0 else -1)
        if name == "acoshl":
            return (a + (a * a - 1).sqrt()).ln()
        if name == "atanhl":
            return ((1 + a) / (1 - a)).ln() / 2
        if name == "erfl":
            return ref_erf(a)
        if name == "erfcl":
            return ref_erfc(a)
        if name == "tgammal":
            return ref_gamma(a)
        if name == "lgammal":
            return ref_lgamma(a)
        if name == "fmal":
            return args[0] * args[1] + args[2]
    raise KeyError(name)


# ---------------------------------------------------------------- the functions and their cases

FUNCS = [
    ("sinl", "sinCore", 1), ("cosl", "cosCore", 1), ("tanl", "tanCore", 1), ("asinl", "asinCore", 1),
    ("acosl", "acosCore", 1), ("atanl", "atanCore", 1), ("atan2l", "atan2Core", 2), ("expl", "expCore", 1),
    ("exp2l", "exp2Core", 1), ("expm1l", "expm1Core", 1), ("logl", "logCore", 1), ("log2l", "log2Core", 1),
    ("log10l", "log10Core", 1), ("log1pl", "log1pCore", 1), ("powl", "powCore", 2), ("cbrtl", "cbrtCore", 1),
    ("hypotl", "hypotCore", 2), ("sinhl", "sinhCore", 1), ("coshl", "coshCore", 1), ("tanhl", "tanhCore", 1),
    ("asinhl", "asinhCore", 1), ("acoshl", "acoshCore", 1), ("atanhl", "atanhCore", 1), ("erfl", "erfCore", 1),
    ("erfcl", "erfcCore", 1), ("tgammal", "tgammaCore", 1), ("lgammal", "lgammaCore", 1), ("fmal", "fmaCore", 3),
]
FN_ID = {n: i for i, (n, _c, _a) in enumerate(FUNCS)}

SPECIAL = {
    # (arguments, expected)
    "sinl": [(["0"], "0"), (["-0"], "-0"), (["inf"], "nan"), (["-inf"], "nan"), (["nan"], "nan")],
    "cosl": [(["0"], "1"), (["-0"], "1"), (["inf"], "nan"), (["nan"], "nan")],
    "tanl": [(["0"], "0"), (["-0"], "-0"), (["-inf"], "nan")],
    "asinl": [(["0"], "0"), (["-0"], "-0"), (["2"], "nan"), (["-1.5"], "nan"), (["inf"], "nan")],
    "acosl": [(["1"], "0"), (["2"], "nan"), (["-inf"], "nan")],
    "atanl": [(["0"], "0"), (["-0"], "-0"), (["inf"], "PI/2"), (["-inf"], "-PI/2")],
    "atan2l": [(["0", "1"], "0"), (["-0", "1"], "-0"), (["0", "-1"], "PI"), (["-0", "-1"], "-PI"), (["1", "0"], "PI/2"),
               (["-1", "-0"], "-PI/2"), (["inf", "inf"], "PI/4"), (["inf", "-inf"], "3PI/4"), (["-inf", "-inf"], "-3PI/4"),
               (["1", "inf"], "0"), (["-1", "inf"], "-0"), (["1", "-inf"], "PI"), (["-1", "-inf"], "-PI"),
               (["inf", "1"], "PI/2"), (["nan", "1"], "nan"), (["1", "nan"], "nan"), (["0", "0"], "0"), (["0", "-0"], "PI")],
    "expl": [(["0"], "1"), (["-0"], "1"), (["inf"], "inf"), (["-inf"], "0"), (["nan"], "nan"), (["20000"], "inf"),
             (["-20000"], "0")],
    "exp2l": [(["0"], "1"), (["inf"], "inf"), (["-inf"], "0"), (["40000"], "inf"), (["-40000"], "0")],
    "expm1l": [(["0"], "0"), (["-0"], "-0"), (["inf"], "inf"), (["-inf"], "-1"), (["20000"], "inf"), (["-20000"], "-1")],
    "logl": [(["1"], "0"), (["0"], "-inf"), (["-0"], "-inf"), (["-1"], "nan"), (["inf"], "inf"), (["-inf"], "nan")],
    "log2l": [(["1"], "0"), (["0"], "-inf"), (["8"], "3"), (["0.25"], "-2"), (["-2"], "nan"), (["inf"], "inf")],
    "log10l": [(["1"], "0"), (["0"], "-inf"), (["1000"], "3"), (["-2"], "nan"), (["inf"], "inf")],
    "log1pl": [(["0"], "0"), (["-0"], "-0"), (["-1"], "-inf"), (["-2"], "nan"), (["inf"], "inf")],
    "powl": [(["2", "0"], "1"), (["nan", "0"], "1"), (["1", "nan"], "1"), (["-1", "inf"], "1"), (["-1", "-inf"], "1"),
             (["0", "-1"], "inf"), (["-0", "-3"], "-inf"), (["-0", "3"], "-0"), (["0", "2"], "0"), (["-0", "-2"], "inf"),
             (["0.5", "inf"], "0"), (["0.5", "-inf"], "inf"), (["2", "inf"], "inf"), (["2", "-inf"], "0"),
             (["-inf", "3"], "-inf"), (["-inf", "-3"], "-0"), (["-inf", "2"], "inf"), (["inf", "-1"], "0"),
             (["inf", "2"], "inf"), (["-8", "0.5"], "nan"), (["-2", "3"], "-8"), (["-2", "4"], "16"), (["2", "10"], "1024"),
             (["2", "100000"], "inf"), (["2", "-100000"], "0"), (["nan", "1"], "nan")],
    "cbrtl": [(["0"], "0"), (["-0"], "-0"), (["inf"], "inf"), (["-inf"], "-inf"), (["27"], "3"), (["-8"], "-2"),
              (["nan"], "nan")],
    "hypotl": [(["3", "4"], "5"), (["inf", "nan"], "inf"), (["nan", "-inf"], "inf"), (["0", "0"], "0"), (["nan", "1"], "nan"),
               (["5", "12"], "13")],
    "sinhl": [(["0"], "0"), (["-0"], "-0"), (["inf"], "inf"), (["-inf"], "-inf"), (["20000"], "inf"), (["-20000"], "-inf")],
    "coshl": [(["0"], "1"), (["inf"], "inf"), (["-inf"], "inf"), (["20000"], "inf")],
    "tanhl": [(["0"], "0"), (["-0"], "-0"), (["inf"], "1"), (["-inf"], "-1"), (["100"], "1"), (["-100"], "-1")],
    "asinhl": [(["0"], "0"), (["-0"], "-0"), (["inf"], "inf"), (["-inf"], "-inf")],
    "acoshl": [(["1"], "0"), (["0.5"], "nan"), (["-1"], "nan"), (["inf"], "inf"), (["-inf"], "nan"), (["0"], "nan")],
    "atanhl": [(["0"], "0"), (["-0"], "-0"), (["1"], "inf"), (["-1"], "-inf"), (["2"], "nan"), (["inf"], "nan")],
    "erfl": [(["0"], "0"), (["-0"], "-0"), (["inf"], "1"), (["-inf"], "-1"), (["20"], "1"), (["-20"], "-1")],
    "erfcl": [(["0"], "1"), (["inf"], "0"), (["-inf"], "2"), (["-20"], "2"), (["200"], "0")],
    "tgammal": [(["0"], "inf"), (["-0"], "-inf"), (["-1"], "nan"), (["-3"], "nan"), (["inf"], "inf"), (["-inf"], "nan"),
                (["1"], "1"), (["2"], "1"), (["5"], "24"), (["3000"], "inf"), (["nan"], "nan")],
    "lgammal": [(["1"], "0"), (["2"], "0"), (["0"], "inf"), (["-0"], "inf"), (["-1"], "inf"), (["-5"], "inf"), (["inf"], "inf"),
                (["-inf"], "inf"), (["nan"], "nan")],
    "fmal": [(["inf", "0", "1"], "nan"), (["0", "inf", "1"], "nan"), (["inf", "1", "-inf"], "nan"), (["inf", "1", "1"], "inf"),
             (["1", "1", "-inf"], "-inf"), (["0", "1", "0"], "0"), (["-0", "1", "-0"], "-0"), (["-0", "1", "0"], "0"),
             (["2", "3", "-6"], "0"), (["2", "3", "4"], "10"), (["nan", "1", "1"], "nan"), (["1.5", "0", "-0"], "0"),
             (["0", "5", "7"], "7")],
}

NUMERIC = {
    "sinl": ["0.5", "1", "-2", "3", "100", "1e10", "1e30", "1e300", "1e4000", "0.001", "7e-5", "1.5707963267948966", "3.141592653589793"],
    "cosl": ["0.5", "1", "-2", "3", "100", "1e10", "1e300", "1e4000", "1e-9", "1.5707963267948966"],
    "tanl": ["0.5", "1", "-2", "3", "100", "1e10", "1e300", "1e4000", "1e-9", "1.5707963267948966"],
    "asinl": ["0.5", "-0.25", "0.9", "0.999", "1e-10", "0.75", "-0.5"],
    "acosl": ["0.5", "-0.25", "0.9", "0.999", "-0.999", "1e-10", "0.75", "0"],
    "atanl": ["0.5", "-2", "10", "1e10", "1e-10", "1e300", "1e-300", "1", "0.3", "1e4000", "1e-4000"],
    "atan2l": [("1", "2"), ("-3", "2"), ("3", "-2"), ("-3", "-2"), ("1e300", "1e-300"), ("1e-300", "1e300"), ("0.5", "0.5"),
               ("10", "1")],
    "expl": ["0.5", "-0.5", "1", "-1", "11356.52", "-11355", "-11357", "-11433", "-11434", "10", "-10", "100", "1e-10", "-1e-20", "700", "-700", "11000", "-11000", "11356.5", "-11400",
             "0.6931471805599453", "5e-4000"],
    "exp2l": ["0.5", "-0.5", "1", "10", "-10", "100", "0.1", "16000", "-16000", "-16450", "16383.99", "1e-10"],
    "expm1l": ["0.5", "-0.5", "1", "-1", "10", "1e-10", "-1e-20", "1e-300", "700", "-700", "0.3", "-0.3", "1e-4000"],
    "logl": ["0.5", "2", "10", "1e10", "1e-10", "1.0000001", "0.9999999", "1e4000", "1e-4000", "3", "0.75"],
    "log2l": ["0.5", "3", "10", "1e10", "1e-10", "1.0000001", "1e4000", "1e-4000"],
    "log10l": ["0.5", "3", "100", "1e10", "1e-10", "1.0000001", "1e4000", "1e-4000"],
    "log1pl": ["0.5", "-0.5", "1", "-0.999", "10", "1e-10", "-1e-20", "1e-300", "1e4000", "0.1", "-0.1", "1e-4000"],
    "powl": [("2", "0.5"), ("10", "-3"), ("1.5", "100"), ("0.5", "30.5"), ("3", "1e-10"), ("2", "16383"), ("2", "-16445"), ("10", "4000"),
             ("0.5", "-1000"), ("7", "7"), ("1.0000001", "1e9"), ("100", "0.001")],
    "cbrtl": ["2", "10", "-10", "1e-10", "1e300", "1e4000", "1e-4000", "0.001", "1000", "3"],
    "hypotl": [("1", "1"), ("1e300", "1e300"), ("1e-300", "1e-300"), ("3e4000", "4e4000"), ("1.1e4932", "1.1e4932"), ("1e4931", "1e4931"), ("1", "1e-30"), ("1e-30", "1"), ("2", "3")],
    "sinhl": ["0.5", "-0.5", "1", "10", "-10", "1e-10", "-1e-20", "700", "11000", "11356", "0.3", "1e-300", "1e-4000"],
    "coshl": ["0.5", "-0.5", "1", "10", "-10", "1e-10", "700", "11000", "11356", "1e-4000"],
    "tanhl": ["0.5", "-0.5", "1", "10", "-10", "1e-10", "-1e-20", "30", "1e-300", "63", "0.3", "1e-4000"],
    "asinhl": ["0.5", "-0.5", "1", "10", "-10", "1e-10", "-1e-20", "1e300", "1e4000", "0.3", "1e-4000"],
    "acoshl": ["1.5", "2", "10", "1e10", "1.0000001", "1.000000000000001", "1e300", "1e4000"],
    "atanhl": ["0.5", "-0.5", "0.9", "0.999", "1e-10", "-1e-20", "0.3", "1e-4000"],
    "erfl": ["0.5", "-0.5", "1", "2", "-3", "5", "1e-10", "-1e-20", "8", "9.5", "0.01", "1e-4000"],
    "erfcl": ["0.5", "-0.5", "1", "2", "-3", "5", "7", "8", "10", "20", "50", "100", "105", "1e-10", "-1e-20", "-7"],
    "tgammal": ["0.5", "1.5", "2.5", "10.5", "-0.5", "-1.5", "-2.5", "-10.5", "100.5", "1700.5", "-170.5", "1e-10", "-1e-10", "0.001", "30", "64.5", "-1760.5", "-1e-5", "1e-4940", "1755", "1755.5", "1756", "-1750.5", "-1000.5", "170.25"],
    "lgammal": ["0.5", "1.5", "2.5", "10.5", "-0.5", "-1.5", "-2.5", "-10.5", "100.5", "1e10", "1e300", "-170.5", "1e-10", "-1e-10", "0.001", "1.0000001", "2.0000001", "0.9999999", "-2.4570247382208", "1e4000", "1e-4000", "1e4900", "-100000.5", "3.5", "1e-30", "-3.0000001", "0.5000001", "1.0000000000000000000000000000000002", "0.9999999999999999999999999999999998", "2.0000000000000000000000000000000004"],
    "fmal": [("1.5", "2.5", "-3.75"), ("0.1", "0.1", "-0.01"), ("1e300", "1e300", "-1e300"), ("1e-300", "1e-300", "1"),
             ("3", "5", "1e-4000"), ("1", "1", "1e-30"), ("1e4000", "1e4000", "-1e8000"), ("0.3", "3", "-0.9"),
             ("1", "1", "-1e-30"), ("123456789", "987654321", "-121932631112635269")],
}

CONSTANTS = {"PI": T.PI, "PI/2": T.PI / 2, "PI/4": T.PI / 4, "3PI/4": T.PI * 3 / 4}


def parse_value(layout: int, text: str):
    """(kind, sign, E, M) of an argument text, or None when it does not fit the layout."""
    if text in ("inf", "-inf"):
        return (2, 1 if text[0] == "-" else 0, 0, 0)
    if text == "nan":
        return (3, 0, 0, 0)
    if text in ("0", "-0"):
        return (0, 1 if text[0] == "-" else 0, 0, 0)
    value = F(D(text))
    rec = round_value(layout, value)
    if rec[0] != 1:
        return None
    return rec


def rec_value(rec) -> F:
    kind, sign, e, m = rec
    if kind != 1:
        return F(0)
    v = F(m) * F(2) ** e
    return -v if sign else v


def expected_record(layout: int, name: str, args_text, spec, argrecs):
    """(kind, sign, E, M) of the expected result."""
    if spec is not None:
        if spec == "nan":
            return (3, 0, 0, 0)
        if spec in ("inf", "-inf"):
            return (2, 1 if spec[0] == "-" else 0, 0, 0)
        if spec in ("0", "-0"):
            return (0, 1 if spec[0] == "-" else 0, 0, 0)
        neg = spec.startswith("-")
        key = spec[1:] if neg else spec
        if key in CONSTANTS:
            v = F(CONSTANTS[key])
            return round_value(layout, -v if neg else v)
        return round_value(layout, F(D(spec)))
    values = [rec_value(r) for r in argrecs]
    if name == "lgammal" and values[0] in (1, 2):
        return (0, 0, 0, 0)
    got = compute(name, values)
    if isinstance(got, F):
        return round_value(layout, got)
    return round_value(layout, F(got))


def cases():
    out = []
    for name, _core, nargs in FUNCS:
        for layout in (0, 1, 2):
            for args, spec in SPECIAL.get(name, []):
                recs = [parse_value(layout, a) for a in args]
                if any(r is None for r in recs):
                    continue
                exp = expected_record(layout, name, args, spec, recs)
                out.append((name, layout, recs, exp, 0))
            for item in NUMERIC.get(name, []):
                args = list(item) if isinstance(item, tuple) else [item]
                recs = [parse_value(layout, a) for a in args]
                if any(r is None for r in recs):
                    continue
                exp = expected_record(layout, name, args, None, recs)
                if exp[0] == 3:
                    continue
                if exp[0] == 2 and exp[1] == 0 and layout == 0 and False:
                    continue
                out.append((name, layout, recs, exp, 0))
    out += fma_edge_cases()
    n = os.environ.get("CMATHLONG_STRESS")
    if n:
        out = out + stress_cases(int(n), int(os.environ.get("CMATHLONG_SEED", "1")))
    return out


def fma_edge_cases():
    """fma where the single rounding matters: an exact cancellation of the product's last bits, a sum that is exactly
    halfway (to even), and one that is halfway and a hair over (up)"""
    out = []
    for layout in (0, 1, 2):
        p = PRECISION[layout]
        one = F(1)
        u = F(1, 1 << (p - 1))
        half_ulp = F(1, 1 << p)

        def rec(v):
            return round_value(layout, v)

        def case(x, y, z):
            args = [rec(x), rec(y), rec(z)]
            assert all(a[0] == 1 and rec_value(a) == v for a, v in zip(args, (x, y, z)))
            exact_value = x * y + z
            out.append(("fmal", layout, args, round_value(layout, exact_value), 0))

        case(one + u, one + u, -(one + 2 * u))
        case(one, one, half_ulp)
        case(one, one, half_ulp + u * half_ulp)
        case(one, one, -half_ulp)
        case(one, one, -half_ulp - u * half_ulp)
        case(one + u, one - u / 2, -one)
        case(one + u, one + u, F(1, 1 << (3 * p)))
        case(-(one + u), one + u, one + 2 * u)
    return out


def stress_cases(per_function: int, seed: int):
    """Random arguments of full precision, for hunting errors (CMATHLONG_STRESS=<n> adds n per function and layout)."""
    import random
    rng = random.Random(seed)
    out = []

    def rnd(layout, lo, hi, signed=True, positive=False):
        p = PRECISION[layout]
        e2 = rng.randint(lo, hi)
        m = rng.getrandbits(p - 1) | (1 << (p - 1))
        e = e2 - (p - 1)
        if e < LEAST[layout] or e + p > GREATEST[layout] + p:
            return None
        sign = 0 if positive else (rng.randint(0, 1) if signed else 0)
        return (1, sign, e, m)

    ranges = {
        "sinl": [(-30, 70), (-30, 70), (70, 16000)], "cosl": [(-30, 70), (-30, 70), (70, 16000)],
        "tanl": [(-30, 70), (-30, 70), (70, 16000)], "asinl": [(-60, -1)], "acosl": [(-60, -1)],
        "atanl": [(-60, 400)], "expl": [(-60, 13)], "exp2l": [(-60, 14)], "expm1l": [(-60, 13)],
        "sinhl": [(-60, 13)], "coshl": [(-60, 13)], "tanhl": [(-60, 7)], "asinhl": [(-60, 200)],
        "erfl": [(-60, 3)], "erfcl": [(-60, 6)], "tgammal": [(-20, 10)], "lgammal": [(-30, 30), (-30, 8)],
        "cbrtl": [(-16000, 16000)],
    }
    for name, _core, nargs in FUNCS:
        for layout in (0, 1, 2):
            made = 0
            tries = 0
            while made < per_function and tries < per_function * 20:
                tries += 1
                args = []
                if name in ranges:
                    lo, hi = rng.choice(ranges[name])
                    args = [rnd(layout, lo, hi)]
                    if name in ("sinhl", "coshl", "tanhl", "asinhl", "expl", "expm1l", "exp2l") and args[0]:
                        pass
                elif name in ("logl", "log2l", "log10l"):
                    args = [rnd(layout, -16000, 16000, positive=True)]
                elif name == "log1pl":
                    args = [rnd(layout, -60, 200) if rng.random() < 0.5 else rnd(layout, -60, -1)]
                    if args[0] and args[0][1] == 1 and rng.random() < 0.3:
                        pass
                elif name == "acoshl":
                    args = [rnd(layout, 0, 200, positive=True)]
                elif name == "atanhl":
                    args = [rnd(layout, -60, -1)]
                elif name == "atan2l":
                    args = [rnd(layout, -40, 40), rnd(layout, -40, 40)]
                elif name == "powl":
                    x = rnd(layout, -20, 20, positive=True)
                    y = rnd(layout, -10, 8)
                    args = [x, y]
                elif name == "hypotl":
                    args = [rnd(layout, -50, 50), rnd(layout, -50, 50)]
                elif name == "fmal":
                    x, y = rnd(layout, -80, 80), rnd(layout, -80, 80)
                    z = rnd(layout, -160, 160)
                    if x and y and rng.random() < 0.5:
                        prod = rec_value(x) * rec_value(y)
                        r = round_value(layout, -prod)
                        if r[0] == 1:
                            z = r
                    args = [x, y, z]
                else:
                    continue
                if any(a is None for a in args):
                    continue
                values = [rec_value(a) for a in args]
                try:
                    exp = expected_record(layout, name, None, None, args)
                except Exception:
                    continue
                if exp[0] == 3:
                    continue
                out.append((name, layout, args, exp, 0))
                made += 1
    return out


def record_text(rec) -> str:
    kind, sign, e, m = rec
    return f"{kind:x}{sign:x}{e & 0xFFFFFFFFFFFFFFFF:016x}{m >> 64:016x}{m & 0xFFFFFFFFFFFFFFFF:016x}"


def cached_cases():
    # the tolerance is applied after the cache

    """cases(), kept in the file named by CMATHLONG_CACHE (when set) while this file is unchanged"""
    import hashlib
    import pickle
    path = os.environ.get("CMATHLONG_CACHE")
    if not path:
        return cases()
    with open(__file__, "rb") as fh:
        key = hashlib.md5(fh.read()).hexdigest()
    if os.path.exists(path):
        with open(path, "rb") as fh:
            saved = pickle.load(fh)
        if saved[0] == key:
            return saved[1]
    result = cases()
    with open(path, "wb") as fh:
        pickle.dump((key, result), fh)
    return result


def table_text():
    parts = []
    count = 0
    for name, layout, recs, exp, tol in cached_cases():
        recs = recs + [(0, 0, 0, 0)] * (3 - len(recs))
        parts.append(f"{FN_ID[name]:02x}{layout:x}{tol:x}" + "".join(record_text(r) for r in recs) + record_text(exp))
        count += 1
    return "".join(parts), count


CASE_WIDTH = 4 + 50 * 4


# ---------------------------------------------------------------- the DSL of the tests


