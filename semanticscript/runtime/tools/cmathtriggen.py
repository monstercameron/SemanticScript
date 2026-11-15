"""Constants and an exact reference for the `cmathtrig` module (sin, cos, tan, asin, acos, atan, atan2 and their
f-suffixed forms), all computed here with Python integers, fractions, and decimals.

`python cmathtriggen.py` rewrites the generated blocks of tools/cmathtrig.dsl (between `## @generated <name>` and
`## @end <name>` lines); tools/build.py then writes cmathtrig.sem from the .dsl as for every module. Nothing here is
pasted from a table: pi comes from Machin's formula on integers, 2/pi from one exact integer division, the polynomial
coefficients from exact Taylor series in fractions (rounded once to the nearest double), and the arctangent table from
Taylor series on decimals. The reference functions (`ref_sin` and the rest) give the exact value of a function at a
double to 60 significant digits, and `ulp_error` measures a result against it; the tests use them.
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

# ---------------------------------------------------------------- pi, exactly


def _atan_inverse(n: int, bits: int) -> int:
    """atan(1/n) as a fixed-point integer with `bits` fractional bits (Taylor series on integers)."""
    one = 1 << bits
    term = one // n
    total = term
    n2 = n * n
    k = 1
    sign = -1
    while term:
        term //= n2
        k += 2
        total += sign * (term // k)
        sign = -sign
    return total


def pi_fixed(bits: int) -> int:
    """pi * 2^bits, to within a few units in the last place: Machin's pi = 16 atan(1/5) - 4 atan(1/239)."""
    guard = 32
    b = bits + guard
    value = 16 * _atan_inverse(5, b) - 4 * _atan_inverse(239, b)
    return value >> guard


PI_BITS = 1700
PI = pi_fixed(PI_BITS)  # pi * 2^1700


def two_over_pi_limbs(count: int) -> list[int]:
    """The first `count` 32-bit limbs of the binary fraction 2/pi = 0.b1 b2 b3 ... (limb k holds bits 32k+1 to
    32k+32)."""
    total = 32 * count
    # floor(2 * 2^total / pi) with pi = PI / 2^PI_BITS; the quotient is below 2^total (2/pi < 1)
    value = (2 << (total + PI_BITS)) // PI
    assert value < (1 << total)
    return [(value >> (32 * (count - 1 - k))) & 0xFFFFFFFF for k in range(count)]


def split_bits(value: Fraction, count: int) -> tuple[float, Fraction]:
    """The double holding the top `count` significant bits of a positive fraction, and what is left of it."""
    e = 0
    while value >= 2 ** (e + 1):
        e += 1
    while value < 2 ** e:
        e -= 1
    unit = Fraction(2) ** (e - count + 1)
    head = (value // unit) * unit
    return float(head), value - head


def pi_fraction() -> Fraction:
    return Fraction(PI, 1 << PI_BITS)


def pio2_pieces() -> list[float]:
    """pi/2 as pieces of 33 bits (so that a whole number below 2^20 times a piece is exact), then a last piece of 53."""
    rest = pi_fraction() / 2
    pieces = []
    for _ in range(3):
        piece, rest = split_bits(rest, 33)
        pieces.append(piece)
    pieces.append(float(rest))
    return pieces


def dd_of(value: Fraction, parts: int = 3) -> list[float]:
    """A value as `parts` doubles that sum to it, each rounded to nearest."""
    out = []
    rest = value
    for _ in range(parts):
        piece = float(rest)
        out.append(piece)
        rest -= Fraction(piece)
    return out


# ---------------------------------------------------------------- Taylor coefficients (exact fractions)


def factorial(n: int) -> int:
    return math.factorial(n)


def sin_coefficients(first: int, last: int) -> list[float]:
    """The coefficients of x^k for odd k from `first` to `last`, as 1/k! with alternating signs, rounded to doubles:
    sin x = x + c3 x^3 + c5 x^5 + ..."""
    return [float(Fraction((-1) ** (k // 2), factorial(k))) for k in range(first, last + 1, 2)]


def cos_coefficients(first: int, last: int) -> list[float]:
    return [float(Fraction((-1) ** (k // 2), factorial(k))) for k in range(first, last + 1, 2)]


def tan_series(terms: int) -> list[Fraction]:
    """The coefficients of x^1, x^3, x^5, ... of tan x, by dividing the series of sin by the series of cos."""
    n = 2 * terms + 2
    sin_c = [Fraction(0)] * n
    cos_c = [Fraction(0)] * n
    for k in range(n):
        if k % 2:
            sin_c[k] = Fraction((-1) ** (k // 2), factorial(k))
        else:
            cos_c[k] = Fraction((-1) ** (k // 2), factorial(k))
    quotient = [Fraction(0)] * n
    for k in range(n):
        acc = sin_c[k] - sum(quotient[j] * cos_c[k - j] for j in range(k))
        quotient[k] = acc / cos_c[0]
    return [quotient[k] for k in range(1, n, 2)][:terms]


def atan_coefficients(first: int, last: int) -> list[float]:
    """atan x = x - x^3/3 + x^5/5 - ...: the coefficients of the odd powers from `first` to `last`."""
    return [float(Fraction((-1) ** (k // 2), k)) for k in range(first, last + 1, 2)]


# the arctangent table: atan(k/8) for k = 0 to 64 as a pair of doubles (high, then the rest rounded to a double)
def atan_table() -> list[tuple[float, float]]:
    getcontext().prec = 80
    out = []
    for k in range(65):
        value = _dec_atan(Decimal(k) / Decimal(8))
        exact = Fraction(value)
        hi = float(exact)
        lo = float(exact - Fraction(hi))
        out.append((hi, lo))
    return out


# ---------------------------------------------------------------- an exact reference on decimals


def _setup(prec: int = 120) -> None:
    getcontext().prec = prec


def _dec_pi() -> Decimal:
    return Decimal(PI) / Decimal(1 << PI_BITS)


def _dec_atan(x: Decimal) -> Decimal:
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
    while abs(term) > eps * abs(total) and abs(term) > Decimal(10) ** -400:
        term = -term * x2
        k += 2
        total += term / k
    total *= 2 ** halvings
    if invert:
        total = _dec_pi() / 2 - total
    return -total if neg else total


def _dec_sincos(x: Decimal) -> tuple[Decimal, Decimal]:
    """sin and cos of a decimal whose magnitude is at most about 1, by Taylor series."""
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


def _reduce(x: float) -> tuple[int, Decimal]:
    """x = n pi/2 + r with r in [-pi/4, pi/4]: (n mod 4, r), exactly enough (pi to 1700 bits)."""
    getcontext().prec = 560
    pio2 = _dec_pi() / 2
    xd = Decimal(x)
    n = int((xd / pio2).to_integral_value())
    r = xd - n * pio2
    getcontext().prec = 120
    return n % 4, +r


def ref_sin(x: float) -> Decimal:
    _setup()
    n, r = _reduce(x)
    s, c = _dec_sincos(r)
    return [s, c, -s, -c][n]


def ref_cos(x: float) -> Decimal:
    _setup()
    n, r = _reduce(x)
    s, c = _dec_sincos(r)
    return [c, -s, -c, s][n]


def ref_tan(x: float) -> Decimal:
    _setup()
    n, r = _reduce(x)
    s, c = _dec_sincos(r)
    return s / c if n % 2 == 0 else -c / s


def ref_atan(x: float) -> Decimal:
    _setup()
    return _dec_atan(Decimal(x))


def ref_asin(x: float) -> Decimal:
    _setup()
    d = Decimal(x)
    if abs(d) == 1:
        return _dec_pi() / 2 * (1 if d > 0 else -1)
    return _dec_atan(d / (1 - d * d).sqrt())


def ref_acos(x: float) -> Decimal:
    _setup()
    d = Decimal(x)
    if d == 1:
        return Decimal(0)
    if d == -1:
        return _dec_pi()
    if d == 0:
        return _dec_pi() / 2
    a = _dec_atan((1 - d * d).sqrt() / abs(d))
    return a if d > 0 else _dec_pi() - a


def ref_atan2(y: float, x: float) -> Decimal:
    """For finite y and x, not both zero (the special cases are Annex F's, not a reference's)."""
    _setup()
    dy, dx = Decimal(y), Decimal(x)
    pi = _dec_pi()
    if dx == 0:
        return pi / 2 if dy > 0 else -pi / 2
    if dy == 0:
        return Decimal(0) if dx > 0 else pi
    a = _dec_atan(abs(dy) / abs(dx))
    if dx < 0:
        a = pi - a
    return a if dy > 0 else -a


REFERENCE = {"sin": ref_sin, "cos": ref_cos, "tan": ref_tan, "asin": ref_asin, "acos": ref_acos, "atan": ref_atan,
             "atan2": ref_atan2}


def ulp_error(approx: float, exact: Decimal, single: bool = False) -> float:
    """How many units in the last place of the correctly rounded result `approx` differs from `exact` (a Decimal):
    |approx - exact| / ulp, with ulp the spacing of the format's numbers at the exact value."""
    if exact == 0:
        return 0.0 if approx == 0 else math.inf
    if math.isnan(approx) or math.isinf(approx):
        return math.inf
    mant = 24 if single else 53
    lowest = -149 if single else -1074
    m, e = math.frexp(float(exact))  # float(exact) is within a few ulps; only its binade matters
    # the spacing of the binade holding |exact|: 2^(e - mant)
    if abs(float(exact)) < 2.0 ** (-126 if single else -1022):
        spacing = Decimal(2) ** lowest
    else:
        # in case float() rounded across a power of two, take the exact value's own binade
        spacing = Decimal(2) ** (e - mant)
        if abs(exact) < Decimal(2) ** (e - 1):
            spacing = Decimal(2) ** (e - 1 - mant)
    return float(abs(Decimal(approx) - exact) / spacing)




# ---------------------------------------------------------------- the generated blocks of cmathtrig.dsl


def hexf(x: float) -> str:
    return float(x).hex()


def _horner(coeffs: list[float], var: str = "z") -> str:
    expr = hexf(coeffs[-1])
    for c in reversed(coeffs[:-1]):
        expr = f"({expr}) * {var} + {hexf(c)}"
    return expr


def _poly_op(name: str, doc: str, coeffs: list[float]) -> str:
    return (f'op {name} "{doc}"\n  input z Float64 copied\n  output Float64\n:begin\n'
            f'  calc value = {_horner(coeffs)}\n  return value\n')


SIN_TERMS = (3, 19)     # x^3 to x^19: sin x = x + x^3 (c3 + c5 z + ...)
COS_TERMS = (4, 18)     # x^4 to x^18: the part of cos x past 1 - x^2/2, as z^2 (c4 + c6 z + ...)
TAN_COUNT = 32          # the series of tan x holds x, x^3, ..., x^63
ATAN_TERMS = (3, 21)    # x^3 to x^21


def block_polynomials() -> str:
    tan = [float(c) for c in tan_series(TAN_COUNT)]
    return "\n".join([
        _poly_op("sinPoly", "The Taylor coefficients of sin past x, in z = x*x: c3 + c5 z + ... to x^19 (exact 1/k! rounded to doubles)",
                 sin_coefficients(*SIN_TERMS)),
        _poly_op("cosPoly", "The Taylor coefficients of cos from x^4, in z = x*x: c4 + c6 z + ... to x^18",
                 cos_coefficients(*COS_TERMS)),
        _poly_op("tanPoly", "The series of tan from x^5, in z = x*x, to x^63 (exact, from the division of the series of sin by cos's)",
                 tan[2:]),
        _poly_op("atanPoly", "The Taylor coefficients of atan from x^3, in z = x*x: -1/3 + z/5 - ... to x^21",
                 atan_coefficients(*ATAN_TERMS)),
    ])


def block_tables() -> str:
    limbs = [0, 0] + two_over_pi_limbs(41)
    text = "".join(f"{limb:08x}" for limb in limbs)
    atan = "".join(f"{struct.unpack('<Q', struct.pack('<d', v))[0]:016x}" for pair in atan_table() for v in pair)
    parts = [
        "## 2/pi: 41 limbs of 32 bits after two limbs of zeros (so that an index never goes below 0)",
        'op twoOverPiLimb "A 32-bit limb of the bits of 2/pi, after two limbs of zeros"',
        "  input index Int64 copied", "  output UInt64", "  effect use machine.memory", "  uses memoryAccess",
        f'  let text String "{text}"', ":begin",
        "  calc base = machine.addressOfString(text)", "  calc value = hexWord(base, index * 8, 8)", "  return value", "",
        "## the bits of the 65 pairs (high, low) of doubles that sum to atan(k/8)",
        'op atanEntry "A double of the arctangent table: entry 2k is the high part of atan(k/8) and 2k+1 its low part"',
        "  input index Int64 copied", "  output Float64", "  effect use machine.memory", "  uses memoryAccess",
        f'  let text String "{atan}"', ":begin",
        "  calc base = machine.addressOfString(text)", "  calc field = hexWord(base, index * 16, 16)",
        "  calc value = convert.uint64BitsToFloat64(field)", "  return value",
    ]
    return "\n".join(parts) + "\n"


MULTIPLY_HEAD = """op multiplyWindow "Multiply the significand by nine limbs of 2/pi from limb `start` on, into the product words of the scratch (32 bits each)"
  input mantissa UInt64 copied
  input start Int64 copied
  effect use machine.memory
  uses memoryAccess
  let carry UInt64 0 mut
:begin
  calc low = mantissa & 4294967295
  calc high = mantissa >> 32"""

MASK_HEAD = """op maskFraction "Clear the product's bits from place `fractionBits` up, keeping the fraction"
  input fractionBits Int64 copied
  effect use machine.memory
  uses memoryAccess
  let bitOne UInt64 1
:begin"""

NEGATE_HEAD = """op negateFraction "Replace the product's nine low limbs by their two's complement"
  effect use machine.memory
  uses memoryAccess
  let carry UInt64 1 mut
:begin"""

HIGHEST_HEAD = """op highestBit "The place of the highest set bit of the product's nine low limbs, or -1 when they are all 0"
  output Int64
  effect use machine.memory
  uses memoryAccess
  let minusOne Int64 -1
:begin"""


def block_rows() -> str:
    out = [MULTIPLY_HEAD]
    for i in range(9):
        out.append(f"  calc limb{i} = twoOverPiLimb(start + {8 - i})")
        out.append(f"  calc total{i} = low * limb{i} + carry")
        out.append(f"  keep{i}: storeWord(slotProduct + {8 * i}, total{i} & 4294967295)")
        out.append(f"  calc carry := total{i} >> 32")
    out.append("  keepCarry: storeWord(slotProduct + 72, carry)")
    out.append("  calc carry := 0")
    for i in range(9):
        out.append(f"  calc limbB{i} = twoOverPiLimb(start + {8 - i})")
        out.append(f"  calc totalB{i} = high * limbB{i} + loadWord(slotProduct + {8 * (i + 1)}) + carry")
        out.append(f"  keepB{i}: storeWord(slotProduct + {8 * (i + 1)}, totalB{i} & 4294967295)")
        out.append(f"  calc carry := totalB{i} >> 32")
    out.append("  keepCarryB: storeWord(slotProduct + 80, carry)")
    out.append("  clearA: storeWord(slotProduct + 88, 0)")
    out.append("  clearB: storeWord(slotProduct + 96, 0)")
    out.append("  return")
    out.append("")
    out.append(MASK_HEAD)
    for i in range(9):
        out.append(f"  calc kept{i} = clampBits(fractionBits - {32 * i})")
        out.append(f"  calc mask{i} = (bitOne << kept{i}) - 1")
        out.append(f"  mask{i}Word: storeWord(slotProduct + {8 * i}, loadWord(slotProduct + {8 * i}) & mask{i})")
    out.append("  return")
    out.append("")
    out.append(NEGATE_HEAD)
    for i in range(9):
        out.append(f"  calc word{i} = loadWord(slotProduct + {8 * i})")
        out.append(f"  calc total{i} = ((~word{i}) & 4294967295) + carry")
        out.append(f"  keep{i}: storeWord(slotProduct + {8 * i}, total{i} & 4294967295)")
        out.append(f"  calc carry := total{i} >> 32")
    out.append("  return")
    out.append("")
    out.append(HIGHEST_HEAD)
    for i in range(8, -1, -1):
        out.append(f"  calc word{i} = loadWord(slotProduct + {8 * i})")
        out.append(f"  when word{i} != 0 found{i} next{i}")
        out.append(f":found{i}")
        out.append(f"  calc place{i} = floorLog2(word{i}) + {32 * i}")
        out.append(f"  return place{i}")
        out.append(f":next{i}")
    out.append("  return minusOne")
    return "\n".join(out) + "\n"


# the inputs of the module's own tests
TEST_CASES = [
    ("sineOf", "sin", "sineWithin", [0.5, 1.0, -3.0, 100.0, 1.5707963267948966, 3.141592653589793, 1e22, 1.7976931348623157e308]),
    ("cosineOf", "cos", "cosineWithin", [0.5, 1.0, -3.0, 100.0, 1.5707963267948966, 3.141592653589793, 1e22, 1.7976931348623157e308]),
    ("tangentOf", "tan", "tangentWithin", [0.5, 1.0, -3.0, 100.0, 1.5707963267948966, 1e22, 1.7976931348623157e308]),
    ("arcSineOf", "asin", "arcSineWithin", [0.5, -0.25, 0.9999999999999999, -1e-5]),
    ("arcCosineOf", "acos", "arcCosineWithin", [0.5, -0.5, 0.9999999999999999, -0.9999999999999999, 1e-9]),
    ("arcTangentOf", "atan", "arcTangentWithin", [0.5, -2.0, 10.0, 1e10, 1e300, 0.125]),
]
TEST_PAIRS = [(1.0, 2.0), (-1.0, -2.0), (2.0, -1.0), (-3.0, 4.0), (1e-300, 3e-300), (5e-324, 1.0), (1.0, 1e300)]


def _bits(x: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def _atan2_special(y: float, x: float) -> float:
    """Annex F's value of atan2 for a zero or infinite argument."""
    if y == 0:
        return math.copysign(3.141592653589793, y) if math.copysign(1.0, x) < 0 else y
    if x == 0:
        return math.copysign(1.5707963267948966, y)
    if math.isinf(y):
        if math.isinf(x):
            return math.copysign(2.356194490192345 if x < 0 else 0.7853981633974483, y)
        return math.copysign(1.5707963267948966, y)
    if math.isinf(x):
        return math.copysign(3.141592653589793 if x < 0 else 0.0, y)
    return float(ref_atan2(y, x))


def block_tests() -> str:
    inf = math.inf
    out = []
    names = {"sineOf": "sine", "cosineOf": "cosine", "tangentOf": "tangent", "arcSineOf": "arcSine",
             "arcCosineOf": "arcCosine", "arcTangentOf": "arcTangent", "arcTangent2Of": "arcTangent2"}
    invariants = {"sineOf": "sineWithin", "cosineOf": "cosineWithin", "tangentOf": "tangentWithin",
                  "arcSineOf": "arcSineWithin", "arcCosineOf": "arcCosineWithin", "arcTangentOf": "arcTangentWithin",
                  "arcTangent2Of": "arcTangent2Within"}
    exact = {"sineOf": ([0.0, -0.0], [0.0, -0.0]),
             "tangentOf": ([-0.0], [-0.0]),
             "cosineOf": ([-0.0], [1.0]),
             "arcSineOf": ([-0.0, 1.0, -1.0], [-0.0, 1.5707963267948966, -1.5707963267948966]),
             "arcCosineOf": ([1.0, -1.0, 0.0], [0.0, 3.141592653589793, 1.5707963267948966]),
             "arcTangentOf": ([inf, -inf, -0.0], [1.5707963267948966, -1.5707963267948966, -0.0])}
    nans = {"sineOf": [inf, -inf], "cosineOf": [-inf], "tangentOf": [inf], "arcSineOf": [1.5, math.nan],
            "arcCosineOf": [-inf]}

    def emit(op: str, checks: list[tuple[str, str]]) -> None:
        lines = [f'test {names[op]}Test "{op}: the correctly rounded result or a neighbor of it, and exact special values"',
                 f"  verifies {op} {invariants[op]}", "  effect use machine.memory", "  uses memoryAccess", ":begin"]
        for n, (call, test_line) in enumerate(checks):
            lines.append(f"  calc r{n} = {call}")
            lines.append(f"  calc ok{n} = {test_line.format(r=f'r{n}')}")
            lines.append(f"  expect{n}: test.assertTrue(ok{n})")
        lines.append("  return")
        out.append("\n".join(lines) + "\n")

    for op, c, _inv, xs in TEST_CASES:
        checks = []
        for x in xs:
            want = _bits(float(REFERENCE[c](x)))
            checks.append((f"{op}(convert.uint64BitsToFloat64({_bits(x)}))", f"closeBits({want}, {{r}})"))
        for x, w in zip(*exact.get(op, ([], []))):
            checks.append((f"{op}(convert.uint64BitsToFloat64({_bits(x)}))", f"sameBits({_bits(w)}, {{r}})"))
        for x in nans.get(op, []):
            checks.append((f"{op}(convert.uint64BitsToFloat64({_bits(x)}))", "!({r} == {r})"))
        emit(op, checks)
    checks = []
    for y, x in TEST_PAIRS:
        want = _bits(float(ref_atan2(y, x)))
        checks.append((f"arcTangent2Of(convert.uint64BitsToFloat64({_bits(y)}), convert.uint64BitsToFloat64({_bits(x)}))",
                       f"closeBits({want}, {{r}})"))
    specials = [0.0, -0.0, 1.0, -1.0, inf, -inf]
    for y in specials:
        for x in specials:
            if abs(y) == 1.0 and not (math.isinf(x) or x == 0):
                continue
            checks.append((f"arcTangent2Of(convert.uint64BitsToFloat64({_bits(y)}), convert.uint64BitsToFloat64({_bits(x)}))",
                           f"sameBits({_bits(_atan2_special(y, x))}, {{r}})"))
    emit("arcTangent2Of", checks)
    return "\n".join(out)


BLOCKS = {"polynomials": block_polynomials, "tables": block_tables, "rows": block_rows, "tests": block_tests}


def write_dsl(path: str | None = None) -> None:
    path = path or os.path.join(HERE, "cmathtrig.dsl")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    for name, make in BLOCKS.items():
        pattern = re.compile(rf"(## @generated {name}\n).*?(## @end {name}\n)", re.S)
        if not pattern.search(text):
            raise SystemExit(f"no block {name}")
        text = pattern.sub(lambda m: m.group(1) + make() + m.group(2), text)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


if __name__ == "__main__":
    write_dsl()
