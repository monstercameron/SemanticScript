"""Writes tests/cprograms/long_math.c: math.h's transcendental long double functions (the module `cmathlong`) against
references computed here with Python decimals at 170 digits.

    python tests/cmathlongtour.py

Each case names a function, arguments that are exact in x87's 64 bits and in binary128 alike (small dyadic fractions
and whole numbers, so the reference is the same for both), and the reference to 45 digits. The C program calls the
function through a pointer (the compiler cannot fold it), reads the reference with strtold (correctly rounded by
glibc and by the runtime), and prints `ok` when the result is within the case's ulps (the distance measured with
nextafterl), or the `%La` bits of both when it is not; NaN, the infinities, and the sign of zero are compared exactly.
Both libraries therefore print the same lines, though glibc's functions are within a few ulps and these are within one.
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal as D, localcontext
from fractions import Fraction as F

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "semanticscript", "runtime", "tools"))
import cmathlongtests as X  # noqa: E402

TWO = F(2)
ARGS = {
    "sinl": [F(1, 2), F(-9, 4), F(3), F(100), F(1, 1024), TWO ** 100, TWO ** 200, F(1, 1 << 40)],
    "cosl": [F(1, 2), F(-9, 4), F(3), F(100), F(1, 1024), TWO ** 100, TWO ** 200],
    "tanl": [F(1, 2), F(-9, 4), F(3), F(100), F(1, 1024), TWO ** 100, TWO ** 200],
    "asinl": [F(1, 2), F(-3, 4), F(1, 1024), F(255, 256), F(-1, 1 << 30)],
    "acosl": [F(1, 2), F(-3, 4), F(1, 1024), F(255, 256), F(-255, 256)],
    "atanl": [F(1, 2), F(-5), F(1000), TWO ** 100, F(1, 1 << 40), F(-3, 4)],
    "atan2l": [(F(1), F(2)), (F(-3), F(2)), (F(3), F(-2)), (F(-3), F(-2)), (TWO ** 100, F(1, 1 << 100)), (F(1, 1024), F(7))],
    "expl": [F(1, 2), F(-9, 4), F(10), F(-10), F(100), F(1, 1 << 30), F(11000), F(-11000), F(11356)],
    "exp2l": [F(1, 2), F(-9, 4), F(10), F(-10), F(100), F(16000), F(-16000)],
    "expm1l": [F(1, 2), F(-9, 4), F(10), F(1, 1 << 30), F(-1, 1 << 40), F(700)],
    "logl": [F(1, 2), F(5), F(1 << 20), F(1, 1 << 30), F(1) + F(1, 1 << 30), TWO ** 4000, F(1) / TWO ** 4000],
    "log2l": [F(1, 2), F(5), F(1 << 20), F(1, 1 << 30), F(1) + F(1, 1 << 30), TWO ** 4000],
    "log10l": [F(1, 2), F(5), F(1000), F(1, 1 << 30), F(1) + F(1, 1 << 30), TWO ** 4000],
    "log1pl": [F(1, 2), F(-1, 2), F(5), F(1, 1 << 30), F(-1, 1 << 40), F(-1023, 1024), TWO ** 100],
    "powl": [(F(2), F(1, 2)), (F(10), F(-3)), (F(3, 2), F(100)), (F(1, 2), F(61, 2)), (F(2), F(16383)), (F(7), F(7)), (F(-2), F(3)),
             (F(-3), F(4)), (F(1) + F(1, 1 << 20), F(1 << 20))],
    "cbrtl": [F(2), F(-10), F(27), F(1, 1 << 30), TWO ** 3000, F(1000)],
    "hypotl": [(F(3), F(4)), (TWO ** 300, TWO ** 300), (F(1, 1 << 300), F(1, 1 << 300)), (F(1), F(1, 1 << 30)), (F(2), F(3))],
    "sinhl": [F(1, 2), F(-9, 4), F(10), F(1, 1 << 30), F(700), F(11000)],
    "coshl": [F(1, 2), F(-9, 4), F(10), F(1, 1 << 30), F(700), F(11000)],
    "tanhl": [F(1, 2), F(-9, 4), F(10), F(1, 1 << 30), F(30), F(-1, 1 << 40)],
    "asinhl": [F(1, 2), F(-9, 4), F(10), F(1, 1 << 30), TWO ** 200, F(-1, 1 << 40)],
    "acoshl": [F(3, 2), F(2), F(10), F(1) + F(1, 1 << 30), TWO ** 200],
    "atanhl": [F(1, 2), F(-3, 4), F(1023, 1024), F(1, 1 << 30), F(-1, 1 << 40)],
    "erfl": [F(1, 2), F(-3, 4), F(2), F(5), F(1, 1 << 30), F(-7, 2), F(9)],
    "erfcl": [F(1, 2), F(-3, 4), F(2), F(5), F(8), F(30), F(100), F(-4)],
    "tgammal": [F(1, 2), F(3, 2), F(21, 2), F(-1, 2), F(-5, 2), F(-21, 2), F(201, 2), F(1, 1 << 20), F(30), F(-1, 1 << 20)],
    "lgammal": [F(1, 2), F(3, 2), F(21, 2), F(-1, 2), F(-5, 2), F(-21, 2), F(201, 2), F(1, 1 << 20), TWO ** 100,
                F(1) + F(1, 1 << 20), F(2) + F(1, 1 << 20), F(-12, 5)],
    "fmal": [(F(3, 2), F(5, 2), F(-15, 4)), (F(5, 16), F(3), F(-15, 16)), (F(1) + F(1, 1 << 30), F(1) + F(1, 1 << 30), -F(1) - F(1, 1 << 29)), (TWO ** 1000, TWO ** 1000, -TWO ** 2000),
             (F(1, 1 << 100), F(1, 1 << 100), F(1)), (F(3), F(5), F(1, 1 << 600)),
             (F(1) + F(1, 1 << 60), F(1) - F(1, 1 << 60), F(-1)), (F(1, 1 << 8000), F(1, 1 << 8000), F(1))],
}
ULPS = {"tgammal": 64, "lgammal": 64, "erfcl": 64, "fmal": 0}
DEFAULT_ULPS = 16
FUNCTIONS = [n for n, _c, _a in X.FUNCS]
ARITY = {n: a for n, _c, a in X.FUNCS}


def exact(x: F) -> str:
    """The exact decimal text of a dyadic rational."""
    with localcontext() as c:
        c.prec = x.numerator.bit_length() * 1 + x.denominator.bit_length() * 1 + 40
        if x.denominator == 1:
            return str(x.numerator)
        return format(D(x.numerator) / D(x.denominator), "f") if abs(x) > F(1, 10 ** 6) and abs(x) < 10 ** 20 else \
            format(D(x.numerator) / D(x.denominator), "e")


def digits(v) -> str:
    with localcontext() as c:
        c.prec = 45
        if isinstance(v, str):
            return v
        if isinstance(v, F):
            if v == 0:
                return "0"
            v = D(v.numerator) / D(v.denominator)
        return format(+D(v), "e")


def reference(name: str, args) -> str:
    return digits(X.compute(name, list(args)))


SPECIALS = [
    ("sinl", ["0"], "0"), ("sinl", ["-0"], "-0"), ("sinl", ["inf"], "nan"), ("cosl", ["0"], "1"), ("cosl", ["-inf"], "nan"),
    ("tanl", ["-0"], "-0"), ("asinl", ["2"], "nan"), ("acosl", ["1"], "0"), ("acosl", ["-2"], "nan"),
    ("atanl", ["inf"], digits(X.T.PI / 2)), ("atanl", ["-inf"], digits(-X.T.PI / 2)), ("atanl", ["-0"], "-0"),
    ("atan2l", ["0", "-1"], digits(X.T.PI)), ("atan2l", ["-0", "-1"], digits(-X.T.PI)), ("atan2l", ["0", "1"], "0"),
    ("atan2l", ["-0", "1"], "-0"), ("atan2l", ["1", "0"], digits(X.T.PI / 2)), ("atan2l", ["inf", "inf"], digits(X.T.PI / 4)),
    ("atan2l", ["inf", "-inf"], digits(X.T.PI * 3 / 4)), ("atan2l", ["1", "-inf"], digits(X.T.PI)),
    ("atan2l", ["-1", "inf"], "-0"),
    ("expl", ["0"], "1"), ("expl", ["-inf"], "0"), ("expl", ["inf"], "inf"), ("expl", ["20000"], "inf"), ("expl", ["-20000"], "0"),
    ("exp2l", ["inf"], "inf"), ("exp2l", ["-inf"], "0"), ("expm1l", ["-inf"], "-1"), ("expm1l", ["-0"], "-0"),
    ("logl", ["0"], "-inf"), ("logl", ["-1"], "nan"), ("logl", ["1"], "0"), ("logl", ["inf"], "inf"),
    ("log2l", ["8"], "3"), ("log2l", ["0"], "-inf"), ("log10l", ["1000"], "3"), ("log10l", ["-2"], "nan"),
    ("log1pl", ["-1"], "-inf"), ("log1pl", ["-2"], "nan"), ("log1pl", ["-0"], "-0"),
    ("powl", ["2", "0"], "1"), ("powl", ["nan", "0"], "1"), ("powl", ["1", "nan"], "1"), ("powl", ["-1", "inf"], "1"),
    ("powl", ["0", "-1"], "inf"), ("powl", ["-0", "-3"], "-inf"), ("powl", ["-0", "3"], "-0"), ("powl", ["0.5", "inf"], "0"),
    ("powl", ["2", "-inf"], "0"), ("powl", ["-inf", "3"], "-inf"), ("powl", ["-inf", "-3"], "-0"), ("powl", ["inf", "-1"], "0"),
    ("powl", ["-8", "0.5"], "nan"), ("powl", ["2", "100000"], "inf"), ("powl", ["2", "-100000"], "0"), ("powl", ["2", "10"], "1024"),
    ("cbrtl", ["-0"], "-0"), ("cbrtl", ["-inf"], "-inf"), ("cbrtl", ["27"], "3"), ("cbrtl", ["-8"], "-2"),
    ("hypotl", ["inf", "nan"], "inf"), ("hypotl", ["nan", "1"], "nan"), ("hypotl", ["3", "4"], "5"), ("hypotl", ["0", "0"], "0"),
    ("sinhl", ["-0"], "-0"), ("sinhl", ["-inf"], "-inf"), ("sinhl", ["20000"], "inf"), ("coshl", ["-inf"], "inf"),
    ("coshl", ["0"], "1"), ("tanhl", ["inf"], "1"), ("tanhl", ["-inf"], "-1"), ("tanhl", ["-0"], "-0"),
    ("asinhl", ["-0"], "-0"), ("asinhl", ["-inf"], "-inf"), ("acoshl", ["1"], "0"), ("acoshl", ["0.5"], "nan"),
    ("acoshl", ["inf"], "inf"), ("atanhl", ["1"], "inf"), ("atanhl", ["-1"], "-inf"), ("atanhl", ["2"], "nan"),
    ("erfl", ["inf"], "1"), ("erfl", ["-inf"], "-1"), ("erfl", ["-0"], "-0"), ("erfcl", ["inf"], "0"), ("erfcl", ["-inf"], "2"),
    ("erfcl", ["-30"], "2"), ("erfcl", ["200"], "0"),
    ("tgammal", ["0"], "inf"), ("tgammal", ["-0"], "-inf"), ("tgammal", ["-3"], "nan"), ("tgammal", ["-inf"], "nan"),
    ("tgammal", ["inf"], "inf"), ("tgammal", ["5"], "24"), ("tgammal", ["3000"], "inf"),
    ("lgammal", ["1"], "0"), ("lgammal", ["2"], "0"), ("lgammal", ["0"], "inf"), ("lgammal", ["-5"], "inf"),
    ("lgammal", ["-inf"], "inf"), ("lgammal", ["inf"], "inf"),
    ("fmal", ["inf", "0", "1"], "nan"), ("fmal", ["inf", "1", "-inf"], "nan"), ("fmal", ["1", "1", "-inf"], "-inf"),
    ("fmal", ["-0", "1", "-0"], "-0"), ("fmal", ["-0", "1", "0"], "0"), ("fmal", ["2", "3", "-6"], "0"), ("fmal", ["2", "3", "4"], "10"),
]


def c_string(s: str) -> str:
    return '"' + s + '"'


def main():
    rows = {1: [], 2: [], 3: []}
    for name in FUNCTIONS:
        for item in ARGS.get(name, []):
            args = list(item) if isinstance(item, tuple) else [item]
            want = reference(name, args)
            texts = [exact(a) for a in args]
            rows[len(args)].append((name, texts, want, ULPS.get(name, DEFAULT_ULPS)))
    for name, texts, want in SPECIALS:
        rows[len(texts)].append((name, texts, want, 0))

    out = []
    w = out.append
    w("""/* math.h's transcendental long double functions (the runtime's cmathlong): each result against a reference computed
   with Python decimals (tests/cmathlongtour.py writes this file), within a few ulps or, for NaN, the infinities, and
   the sign of zero, exactly; the same lines are printed with glibc and with the runtime's library. */
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef long double (*one_t)(long double);
typedef long double (*two_t)(long double, long double);
typedef long double (*three_t)(long double, long double, long double);

struct one { const char *name; one_t f; const char *x; const char *want; int ulps; };
struct two { const char *name; two_t f; const char *x; const char *y; const char *want; int ulps; };
struct three { const char *name; three_t f; const char *x; const char *y; const char *z; const char *want; int ulps; };

static int near_enough(long double got, long double want, int ulps) {
    if (isnan(want))
        return isnan(got);
    if (isnan(got))
        return 0;
    if (isinf(want) || want == 0.0L)
        return got == want && !!signbit(got) == !!signbit(want);
    if (isinf(got) || !!signbit(got) != !!signbit(want))
        return 0;
    long double a = fabsl(want);
    long double unit = nextafterl(a, INFINITY) - a;
    return fabsl(got - want) <= ulps * unit;
}

static void report(const char *name, const char *args, long double got, long double want, int ulps) {
    if (near_enough(got, want, ulps))
        printf("%s(%s) ok\\n", name, args);
    else
        printf("%s(%s) BAD got %La want %La\\n", name, args, got, want);
}
""".replace("\\\\n", "\\n"))
    names1 = {n for n, *_ in rows[1]}
    names2 = {n for n, *_ in rows[2]}
    names3 = {n for n, *_ in rows[3]}
    w("static const struct one ones[] = {")
    for name, texts, want, ulps in rows[1]:
        w(f"    {{{c_string(name)}, {name}, {c_string(texts[0])}, {c_string(want)}, {ulps}}},")
    w("};")
    w("static const struct two twos[] = {")
    for name, texts, want, ulps in rows[2]:
        w(f"    {{{c_string(name)}, {name}, {c_string(texts[0])}, {c_string(texts[1])}, {c_string(want)}, {ulps}}},")
    w("};")
    w("static const struct three threes[] = {")
    for name, texts, want, ulps in rows[3]:
        w(f"    {{{c_string(name)}, {name}, {c_string(texts[0])}, {c_string(texts[1])}, {c_string(texts[2])}, {c_string(want)}, {ulps}}},")
    w("};")
    w("""
static void errno_case(const char *name, long double got) {
    printf("%s errno %d %s\\n", name, errno, isinf(got) ? "inf" : isnan(got) ? "nan" : "number");
}

int main(void) {
    for (unsigned i = 0; i < sizeof ones / sizeof ones[0]; i++) {
        long double x = strtold(ones[i].x, NULL), want = strtold(ones[i].want, NULL);
        report(ones[i].name, ones[i].x, ones[i].f(x), want, ones[i].ulps);
    }
    for (unsigned i = 0; i < sizeof twos / sizeof twos[0]; i++) {
        long double x = strtold(twos[i].x, NULL), y = strtold(twos[i].y, NULL), want = strtold(twos[i].want, NULL);
        char args[200];
        snprintf(args, sizeof args, "%s, %s", twos[i].x, twos[i].y);
        report(twos[i].name, args, twos[i].f(x, y), want, twos[i].ulps);
    }
    for (unsigned i = 0; i < sizeof threes / sizeof threes[0]; i++) {
        long double x = strtold(threes[i].x, NULL), y = strtold(threes[i].y, NULL), z = strtold(threes[i].z, NULL);
        long double want = strtold(threes[i].want, NULL);
        char args[300];
        snprintf(args, sizeof args, "%s, %s, %s", threes[i].x, threes[i].y, threes[i].z);
        report(threes[i].name, args, threes[i].f(x, y, z), want, threes[i].ulps);
    }

    /* lgammal_r's sign */
    int sign = 0;
    volatile long double half = 0.5L, minus_half = -0.5L, minus_one_and_half = -1.5L;
    long double value = lgammal_r(half, &sign);
    printf("lgammal_r(0.5) sign %d near %d\\n", sign, near_enough(value, strtold("5.72364942924700087071713675676529356e-1", NULL), 16));
    value = lgammal_r(minus_half, &sign);
    printf("lgammal_r(-0.5) sign %d\\n", sign);
    value = lgammal_r(minus_one_and_half, &sign);
    printf("lgammal_r(-1.5) sign %d\\n", sign);

    /* errno where glibc and the runtime agree: overflow and poles ERANGE, a domain error EDOM */
    volatile long double big = 20000.0L, zero = 0.0L, minus_one = -1.0L, two = 2.0L, tenth = 0.5L, minus_three = -3.0L;
    errno = 0; errno_case("expl(20000)", expl(big));
    errno = 0; errno_case("logl(0)", logl(zero));
    errno = 0; errno_case("logl(-1)", logl(minus_one));
    errno = 0; errno_case("asinl(2)", asinl(two));
    errno = 0; errno_case("acoshl(0.5)", acoshl(tenth));
    errno = 0; errno_case("powl(0, -1)", powl(zero, minus_one));
    errno = 0; errno_case("tgammal(-3)", tgammal(minus_three));
    errno = 0; errno_case("lgammal(0)", lgammal(zero));
    errno = 0; errno_case("sinhl(20000)", sinhl(big));
    return 0;
}
""".replace("\\\\n", "\\n"))
    path = os.path.join(ROOT, "tests", "cprograms", "long_math.c")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
    print(path, sum(len(v) for v in rows.values()), "cases")


if __name__ == "__main__":
    main()
