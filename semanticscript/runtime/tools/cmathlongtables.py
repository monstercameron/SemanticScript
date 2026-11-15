"""The constants of cmathlong, computed with Python integers, fractions and decimals (nothing pasted from a table):
ln 2, 1/ln 2, 1/ln 10, pi, 2/sqrt(pi), 1/sqrt(pi), ln(2 pi)/2, the Bernoulli coefficients of Stirling's series, each
as a 320-bit significand (rounded to nearest) with its power of two, and the bits of 2/pi.
"""
from __future__ import annotations

from decimal import Decimal, getcontext
from fractions import Fraction

getcontext().prec = 260

LIMBS = 10
BITS = 32 * LIMBS            # 320
TWO_OVER_PI_BITS = 17200
BERNOULLI_TERMS = 56         # c_1 .. c_56 of Stirling's series


def _atan_inverse(n: int, bits: int) -> int:
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
    """pi * 2^bits (Machin's formula on integers, 40 guard bits)."""
    guard = 40
    b = bits + guard
    return (16 * _atan_inverse(5, b) - 4 * _atan_inverse(239, b)) >> guard


PI_FRACTION = Fraction(pi_fixed(1200), 1 << 1200)
PI = Decimal(PI_FRACTION.numerator) / Decimal(PI_FRACTION.denominator)
LN2 = Decimal(2).ln()
LN10 = Decimal(10).ln()


def dec_to_fraction(x: Decimal) -> Fraction:
    return Fraction(x)


def limbs_of(value: Fraction):
    """(power, [limb0 .. limb9]) with value ~ M * 2^power, M in [2^319, 2^320) rounded to nearest."""
    assert value > 0
    num, den = value.numerator, value.denominator
    # find e with 2^319 <= value * 2^-e < 2^320
    e = num.bit_length() - den.bit_length() - BITS
    while True:
        m_num = num << max(0, -e)
        m_den = den << max(0, e)
        m = (2 * m_num + m_den) // (2 * m_den)       # round to nearest
        if m >= 1 << BITS:
            e += 1
        elif m < 1 << (BITS - 1):
            e -= 1
        else:
            break
    return e, [(m >> (32 * i)) & 0xFFFFFFFF for i in range(LIMBS)]


def entry_hex(value: Fraction) -> str:
    e, limbs = limbs_of(value)
    return f"{e & 0xFFFFFFFFFFFFFFFF:016x}" + "".join(f"{l:08x}" for l in limbs)


def bernoulli_numbers(count: int):
    a = [Fraction(0)] * (count + 1)
    out = []
    for m in range(count + 1):
        a[m] = Fraction(1, m + 1)
        for j in range(m, 0, -1):
            a[j - 1] = j * (a[j - 1] - a[j])
        out.append(a[0])
    return out


NAMES = ["LN2", "INV_LN2", "INV_LN10", "PI", "TWO_OVER_SQRT_PI", "INV_SQRT_PI", "HALF_LN_2PI"]
FIRST_COEFFICIENT = 16        # index of c_1


def constant_values():
    """{index: Fraction} of the constants table."""
    out = {}
    out[0] = dec_to_fraction(LN2)
    out[1] = dec_to_fraction(1 / LN2)
    out[2] = dec_to_fraction(1 / LN10)
    out[3] = dec_to_fraction(PI)
    out[4] = dec_to_fraction(2 / PI.sqrt())
    out[5] = dec_to_fraction(1 / PI.sqrt())
    out[6] = dec_to_fraction((2 * PI).ln() / 2)
    bern = bernoulli_numbers(2 * BERNOULLI_TERMS + 2)
    for k in range(1, BERNOULLI_TERMS + 1):
        b = bern[2 * k]
        out[FIRST_COEFFICIENT + k - 1] = abs(b) / (2 * k * (2 * k - 1))
    return out


def constants_text() -> str:
    values = constant_values()
    top = max(values)
    parts = []
    for i in range(top + 1):
        parts.append(entry_hex(values[i]) if i in values else "0" * 96)
    return "".join(parts)


def two_over_pi_text() -> str:
    bits = TWO_OVER_PI_BITS
    pi_big = pi_fixed(bits + 80)           # pi * 2^(bits+80)
    value = (2 << (bits + 80 + bits)) // pi_big     # floor(2/pi * 2^bits)
    assert value < 1 << bits
    digits = bits // 4
    return f"{value:0{digits}x}"


if __name__ == "__main__":
    print(len(constants_text()), len(two_over_pi_text()))
    t = two_over_pi_text()
    print(t[:40])
