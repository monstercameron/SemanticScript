"""Generate tools/cmathexp.dsl: math.h's exponentials, logarithms, pow, cbrt and hypot, in SemanticScript.

    python cmathexpgen.py            # writes cmathexp.dsl next to this file

The algorithms are double-double ("two doubles") arithmetic after Dekker and Knuth (error-free transforms), table
free: every constant (ln 2 in parts, 1/n!, 1/(2n+1), ...) is computed here with `decimal` and `fractions` at 100
digits and written into the DSL as exact hexadecimal literals. The functions of one double are evaluated to about
2^-60 relative error or better, so they are correctly rounded except when the true value lies within that of a
rounding boundary; the f-suffixed forms evaluate the double function and narrow once.

  exp, exp2, expm1: x = k ln2 + r with |r| <= ln2/2 (r in double-double); expm1(r) by Taylor series of r/8 in
      double-double (the first terms) and double (the tail) followed by three doublings p <- 2p + p^2.
  log, log2, log10, log1p: x = 2^e m with m in [sqrt(1/2), sqrt(2)); log m = 2 atanh((m-1)/(m+1)) by its series,
      the first three terms in double-double.
  pow: exp(y log |x|) with log in double-double, y times it in double-double, then the exp above.
  cbrt: Newton in double on the mantissa, then one double-double correction of the residual.
  hypot: the squares in double-double, a double-double correction of the square root.
(The structure of glibc's exp/log/pow, ARM optimized-routines, is table driven; these are not that algorithm.)
"""
from __future__ import annotations

import os
from decimal import Decimal, getcontext
from fractions import Fraction

getcontext().prec = 110
HERE = os.path.dirname(os.path.abspath(__file__))
MAXD = 1.7976931348623157e308


def hx(x: float) -> str:
    return float.hex(x)


def lit(x: float) -> str:
    """A literal the expression grammar reads: exact hexadecimal."""
    return hx(x)


def dd_of(v: Fraction):
    hi = float(v)
    lo = float(v - Fraction(hi))
    return hi, lo


LN2 = Fraction(Decimal(2).ln())
LN10 = Fraction(Decimal(10).ln())


def trunc_bits(v: Fraction, bits: int) -> Fraction:
    if v == 0:
        return Fraction(0)
    neg = v < 0
    a = -v if neg else v
    e = 0
    while a >= 2:
        a /= 2
        e += 1
    while a < 1:
        a *= 2
        e -= 1
    q = Fraction(2) ** (e - bits + 1)
    r = round((-v if neg else v) / q) * q
    return -r if neg else r


L1 = trunc_bits(LN2, 32)
L2 = trunc_bits(LN2 - L1, 32)
L3 = float(LN2 - L1 - L2)
LN2H, LN2L = dd_of(LN2)
INVLN2 = float(1 / LN2)
INVLN2H, INVLN2L = dd_of(1 / LN2)
LOG10_2H, LOG10_2L = dd_of(LN2 / LN10)
INVLN10H, INVLN10L = dd_of(1 / LN10)


class Op:
    def __init__(self, name, doc, inputs, output=None, invariant=None, abi=None, effect=False):
        self.name, self.doc, self.inputs, self.output = name, doc, inputs, output
        self.invariant, self.abi, self.effect = invariant, abi, effect
        self.lines, self.lets, self.n, self.nl = [], [], 0, 0

    def fresh(self, base="t"):
        self.n += 1
        return f"{base}{self.n}"

    def t(self, expr, base="t"):
        name = self.fresh(base)
        self.lines.append(f"  calc {name} = {expr}")
        return name

    def call(self, expr, base="c"):
        return self.t(expr, base)

    def var(self, typ, init, base="v"):
        name = self.fresh(base)
        self.lets.append(f"  let {name} {typ} {init} mut")
        return name

    def const(self, value, typ="Float64"):
        name = self.fresh("k")
        self.lets.append(f"  let {name} {typ} {value}")
        return name

    def setv(self, var, value):
        self.lines.append(f"  set {var} {value}")

    def calc_set(self, var, expr):
        self.lines.append(f"  calc {var} := {expr}")

    def label(self, name):
        self.lines.append(f":{name}")

    def lab(self, base="l"):
        self.nl += 1
        return f"{base}{self.nl}"

    def when(self, cond, yes, no):
        self.lines.append(f"  when {cond} {yes} {no}")

    def goto(self, label):
        self.lines.append(f"  goto {label}")

    def ret(self, name=None):
        self.lines.append(f"  return {name}" if name else "  return")

    def early(self, cond, build):
        """if cond: build() (which must return) then continue."""
        yes, no = self.lab("yes"), self.lab("no")
        self.when(cond, yes, no)
        self.label(yes)
        build()
        self.label(no)

    def render(self):
        out = [f'op {self.name} "{self.doc}"']
        if self.invariant:
            out.append(f'  invariant {self.invariant[0]} "{self.invariant[1]}"')
        for nm, ty in self.inputs:
            out.append(f"  input {nm} {ty} copied")
        if self.output:
            out.append(f"  output {self.output}")
        if self.effect:
            out += ["  effect use machine.memory", "  uses memoryAccess"]
        if self.abi:
            out.append(f'  abi library "{self.abi}"')
        out += self.lets
        out.append(":begin")
        out += self.lines
        return "\n".join(out)


# ---------------------------------------------------------------- double-double macros

def two_sum(o, a, b):
    s = o.t(f"{a} + {b}")
    bb = o.t(f"{s} - {a}")
    e = o.t(f"({a} - ({s} - {bb})) + ({b} - {bb})")
    return s, e


def fast_two_sum(o, a, b):
    s = o.t(f"{a} + {b}")
    e = o.t(f"{b} - ({s} - {a})")
    return s, e


def split(o, a):
    c = o.t(f"{a} * 134217729.0")
    hi = o.t(f"{c} - ({c} - {a})")
    lo = o.t(f"{a} - {hi}")
    return hi, lo


def two_prod(o, a, b):
    p = o.t(f"{a} * {b}")
    ah, al = split(o, a)
    bh, bl = split(o, b)
    e = o.t(f"(((({ah} * {bh}) - {p}) + ({ah} * {bl})) + ({al} * {bh})) + ({al} * {bl})")
    return p, e


def dd_add(o, ah, al, bh, bl):
    s, e = two_sum(o, ah, bh)
    e2 = o.t(f"{e} + ({al} + {bl})")
    return two_sum(o, s, e2)


def dd_add_d(o, ah, al, b):
    s, e = two_sum(o, ah, b)
    e2 = o.t(f"{e} + {al}")
    return two_sum(o, s, e2)


def dd_mul(o, ah, al, bh, bl):
    p, e = two_prod(o, ah, bh)
    e2 = o.t(f"{e} + (({ah} * {bl}) + ({al} * {bh}))")
    return fast_two_sum(o, p, e2)


def dd_mul_d(o, ah, al, b):
    p, e = two_prod(o, ah, b)
    e2 = o.t(f"{e} + ({al} * {b})")
    return fast_two_sum(o, p, e2)


MAGIC = lit(6755399441055744.0)


def round_nearest(o, t):
    u = o.t(f"{t} + {MAGIC}")
    return o.t(f"{u} - {MAGIC}")


def reduce_exp(o, xh, xl):
    """k (Int64) and the double-double r = x - k ln2 for x = xh + xl (|k| < 2^11)."""
    t = o.t(f"{xh} * {lit(INVLN2)}")
    kf = round_nearest(o, t)
    k = o.t(f"convert.float64ToInt64({kf})", "k")
    p1 = o.t(f"{kf} * {lit(float(L1))}")
    p2 = o.t(f"{kf} * {lit(float(L2))}")
    p3 = o.t(f"{kf} * {lit(L3)}")
    s1, e1 = two_sum(o, xh, f"(0.0 - {p1})")
    s2, e2 = two_sum(o, s1, f"(0.0 - {p2})")
    lo = o.t(f"((({e1} + {e2}) - {p3}) + {xl})" if xl else f"(({e1} + {e2}) - {p3})")
    rh, rl = fast_two_sum(o, s2, lo)
    return k, rh, rl


def expm1_core(o, rh, rl):
    a = o.t(f"{rh} * 0.125")
    b = o.t(f"{rl} * 0.125")
    sh, sl = dd_mul(o, a, b, a, b)
    q2h = o.t(f"{sh} * 0.5")
    q2l = o.t(f"{sl} * 0.5")
    a2 = o.t(f"{a} * {a}")
    a3 = o.t(f"{a2} * {a}")
    fact = [1] * 14
    for i in range(1, 14):
        fact[i] = fact[i - 1] * i
    h = lit(1 / fact[11])
    first = True
    for n in range(10, 2, -1):
        c = lit(float(Fraction(1, fact[n])))
        h = o.t(f"{c} + ({a} * {h})")
    tail = o.t(f"{a3} * {h}")
    qh, ql = dd_add_d(o, q2h, q2l, tail)
    ph, pl = dd_add(o, a, b, qh, ql)
    for _ in range(3):
        sh, sl = dd_mul(o, ph, pl, ph, pl)
        dh = o.t(f"{ph} * 2.0")
        dl = o.t(f"{pl} * 2.0")
        ph, pl = dd_add(o, dh, dl, sh, sl)
    return ph, pl


def series_consts(n):
    return dd_of(Fraction(1, n))


def log_core(o, uh, ul, which, extra):
    """Body of logParts (selected by `which`)."""
    bitsu = o.t(f"convert.float64BitsToUInt64({uh})")
    fld = o.t(f"({bitsu} >> 52) & 2047")
    exb = o.t(f"convert.uint64BitsToInt64({fld})")
    ex = o.t(f"{exb} - 1023")
    mant = o.t(f"{bitsu} & 4503599627370495")
    comb = o.t(f"{mant} | 4607182418800017408")
    m0 = o.t(f"convert.uint64BitsToFloat64({comb})")
    eadj = o.var("Int64", "0")
    big, small, join = o.lab("big"), o.lab("small"), o.lab("join")
    o.when(f"{m0} > {lit(1.4142135623730951)}", big, small)
    o.label(big)
    o.calc_set(eadj, f"{ex} + 1")
    o.goto(join)
    o.label(small)
    o.setv(eadj, ex)
    o.goto(join)
    o.label(join)
    ef = o.t(f"convert.int64ToFloat64({eadj})")
    total = o.t(f"{ef} + {extra}")
    zero_case, go = o.lab("e"), o.lab("go")
    o.when(f"{which} == 0", zero_case, go)
    o.label(zero_case)
    o.ret(total)
    o.label(go)
    nege = o.t(f"0 - {eadj}")
    mh = o.t(f"scaleBy({uh}, {nege})")
    ml = o.t(f"scaleBy({ul}, {nege})")
    n = o.t(f"{mh} - 1.0")
    nh, nl = two_sum(o, n, ml)
    dh0, dl0 = two_sum(o, mh, "1.0")
    dl = o.t(f"{dl0} + {ml}")
    q1 = o.t(f"{nh} / {dh0}")
    pp, pe = two_prod(o, q1, dh0)
    r = o.t(f"((({nh} - {pp}) - {pe}) + {nl}) - ({q1} * {dl})")
    q2 = o.t(f"{r} / {dh0}")
    sh, sl = fast_two_sum(o, q1, q2)
    s2h, s2l = dd_mul(o, sh, sl, sh, sl)
    # n = 4..15: 1/(2n+1) + s2 * (...)
    h = lit(1 / 31)
    for n_ in range(14, 3, -1):
        h = o.t(f"{lit(1 / (2 * n_ + 1))} + ({s2h} * {h})")
    prod = o.t(f"{s2h} * {h}")
    c7h, c7l = series_consts(7)
    a3h, a3l = dd_add_d(o, lit(c7h), lit(c7l), prod)
    mh2, ml2 = dd_mul(o, s2h, s2l, a3h, a3l)
    c5h, c5l = series_consts(5)
    a2h, a2l = dd_add(o, lit(c5h), lit(c5l), mh2, ml2)
    mh3, ml3 = dd_mul(o, s2h, s2l, a2h, a2l)
    c3h, c3l = series_consts(3)
    a1h, a1l = dd_add(o, lit(c3h), lit(c3l), mh3, ml3)
    t1h, t1l = dd_mul(o, s2h, s2l, a1h, a1l)
    t2h, t2l = dd_mul(o, sh, sl, t1h, t1l)
    uh2, ul2 = dd_add(o, sh, sl, t2h, t2l)
    lh = o.t(f"{uh2} * 2.0")
    ll = o.t(f"{ul2} * 2.0")
    one_case, two_case = o.lab("one"), o.lab("two")
    o.when(f"{which} == 1", one_case, two_case)
    o.label(one_case)
    o.ret(lh)
    o.label(two_case)
    o.ret(ll)


def build_ops():
    ops = []

    # ---------------------------------------------------------------- small helpers
    o = Op("infinityValue", "Positive infinity", [], "Float64")
    r = o.t("convert.uint64BitsToFloat64(9218868437227405312)")
    o.ret(r)
    ops.append(o)

    o = Op("invalidValue", "The quiet NaN the hardware gives for an invalid operation (the sign bit set, as glibc's x86_64 results print)", [], "Float64")
    r = o.t("convert.uint64BitsToFloat64(18444492273895866368)")
    o.ret(r)
    ops.append(o)

    o = Op("absoluteOf", "The magnitude of a double", [("value", "Float64")], "Float64")
    b = o.t("convert.float64BitsToUInt64(value)")
    m = o.t(f"{b} & 9223372036854775807")
    r = o.t(f"convert.uint64BitsToFloat64({m})")
    o.ret(r)
    ops.append(o)

    o = Op("signedLike", "The magnitude of one double with the sign of another", [("magnitude", "Float64"), ("sign", "Float64")], "Float64")
    b = o.t("convert.float64BitsToUInt64(magnitude)")
    m = o.t(f"{b} & 9223372036854775807")
    sb = o.t("convert.float64BitsToUInt64(sign)")
    s = o.t(f"{sb} & 9223372036854775808")
    j = o.t(f"{m} | {s}")
    r = o.t(f"convert.uint64BitsToFloat64({j})")
    o.ret(r)
    ops.append(o)

    o = Op("powerOfTwo", "2 to a power from -1022 to 1023, exactly", [("steps", "Int64")], "Float64")
    b = o.t("steps + 1023")
    f = o.t(f"convert.int64BitsToUInt64({b})")
    m = o.t(f"{f} << 52")
    r = o.t(f"convert.uint64BitsToFloat64({m})")
    o.ret(r)
    ops.append(o)

    o = Op("scaleBy", "A double times 2 to a power from -2044 to 2044 in two exact steps, so only the last rounds", [("value", "Float64"), ("steps", "Int64")], "Float64")
    h = o.t("steps / 2")
    rest = o.t(f"steps - {h}")
    a = o.t(f"powerOfTwo({h})")
    b = o.t(f"powerOfTwo({rest})")
    f1 = o.t(f"value * {a}")
    f2 = o.t(f"{f1} * {b}")
    o.ret(f2)
    ops.append(o)

    o = Op("integerKind", "For a finite double: 0 when it is not a whole number, 1 when it is an odd one, 2 when an even one", [("value", "Float64")], "Int64")
    two, zero, one = o.const(2, "Int64"), o.const(0, "Int64"), o.const(1, "Int64")
    a = o.t("absoluteOf(value)")
    o.early(f"{a} >= 9007199254740992.0", lambda: o.ret(two))
    i = o.t("convert.float64ToInt64(value)")
    back = o.t(f"convert.int64ToFloat64({i})")
    o.early(f"{back} != value", lambda: o.ret(zero))
    low = o.t(f"{i} & 1")
    o.early(f"{low} == 1", lambda: o.ret(one))
    o.ret(two)
    ops.append(o)

    o = Op("narrowOf", "A double as a float, rounded once; a magnitude that rounds past the largest float is an infinity", [("value", "Float64")], "Float32")
    a = o.t("absoluteOf(value)")
    big, small = o.lab("big"), o.lab("small")
    o.when(f"{a} >= {lit(3.4028235677973366e38)}", big, small)
    o.label(big)
    inf = o.t("infinityValue()")
    sg = o.t(f"signedLike({inf}, value)")
    r = o.t(f"convert.float64ToFloat32({sg})")
    o.ret(r)
    o.label(small)
    r2 = o.t("convert.float64ToFloat32(value)")
    o.ret(r2)
    ops.append(o)

    # errno helpers
    o = Op("noteRange", "Set errno to ERANGE when a result is an infinity from finite arguments, or a zero from a computation that underflowed", [("value", "Float64"), ("overflows", "Bool"), ("underflows", "Bool")], None, effect=True)
    a = o.t("absoluteOf(value)")
    o.early(f"{a} > {lit(MAXD)}", lambda: (o.when("overflows", "setIt", "skipIt"), o.label("setIt"), o.t("clibrary.setErrno(34)", "x") if False else o.lines.append("  clibrary.setErrno(34)"), o.ret(), o.label("skipIt"), o.ret()))
    o.early("value == 0.0", lambda: (o.when("underflows", "setZero", "skipZero"), o.label("setZero"), o.lines.append("  clibrary.setErrno(34)"), o.ret(), o.label("skipZero"), o.ret()))
    o.ret()
    ops.append(o)

    o = Op("noteDomain", "Set errno for log: ERANGE at the pole, EDOM below it (a NaN argument sets nothing)", [("value", "Float64"), ("pole", "Float64")], None, effect=True)
    o.early(f"value == pole", lambda: (o.lines.append("  clibrary.setErrno(34)"), o.ret()))
    o.early(f"value < pole", lambda: (o.lines.append("  clibrary.setErrno(33)"), o.ret()))
    o.ret()
    ops.append(o)

    o = Op("noteInvalid", "Set errno to EDOM when a result is a NaN though no argument was", [("value", "Float64"), ("fromArguments", "Bool")], None, effect=True)
    o.early("!(value == value)", lambda: (o.when("fromArguments", "keepIt", "setIt"), o.label("setIt"), o.lines.append("  clibrary.setErrno(33)"), o.ret(), o.label("keepIt"), o.ret()))
    o.ret()
    ops.append(o)

    # ---------------------------------------------------------------- exp core
    o = Op("expScaled", "2 to the power k times e to the power r, r = rh + rl with |r| up to 0.35, rounded once", [("rh", "Float64"), ("rl", "Float64"), ("k", "Int64")], "Float64")
    ph, pl = expm1_core(o, "rh", "rl")
    s, e = two_sum(o, "1.0", ph)
    e2 = o.t(f"{e} + {pl}")
    qh, ql = fast_two_sum(o, s, e2)
    r = o.t(f"scaleBy({qh}, k)")
    o.ret(r)
    ops.append(o)

    o = Op("expm1Scaled", "2 to the power k times e to the power r, less 1, r = rh + rl with |r| up to 0.35, rounded once", [("rh", "Float64"), ("rl", "Float64"), ("k", "Int64")], "Float64")
    ph, pl = expm1_core(o, "rh", "rl")
    z = o.t(f"{ph} + {pl}")
    o.early("k == 0", lambda: o.ret(z))
    s, e = two_sum(o, "1.0", ph)
    e2 = o.t(f"{e} + {pl}")
    qh, ql = fast_two_sum(o, s, e2)
    big = o.t(f"scaleBy({qh}, k)")
    o.early("k >= 60", lambda: o.ret(big))
    m1 = o.const(-1.0)
    o.early("k <= -60", lambda: o.ret(m1))
    sc = o.t("powerOfTwo(k)")
    bh = o.t(f"{qh} * {sc}")
    bl = o.t(f"{ql} * {sc}")
    s2, e3 = two_sum(o, bh, "(0.0 - 1.0)")
    e4 = o.t(f"{e3} + {bl}")
    r = o.t(f"{s2} + {e4}")
    o.ret(r)
    ops.append(o)

    o = Op("logParts", "For u = uh + ul > 0: which 0 gives the exponent e (plus extra) with u = 2^e m, m from 0.7 to 1.4; 1 and 2 give the high and low parts of ln m as a double-double", [("uh", "Float64"), ("ul", "Float64"), ("extra", "Float64"), ("which", "Int64")], "Float64")
    log_core(o, "uh", "ul", "which", "extra")
    ops.append(o)

    # ---------------------------------------------------------------- exp family values
    nanret = lambda o, x: (lambda: o.ret(o.t(f"{x} + {x}")))

    def exp_head(o):
        o.early("!(x == x)", lambda: o.ret(o.t("x + x")))

    o = Op("expValue", "e to the power x, as a double", [("x", "Float64")], "Float64")
    exp_head(o)
    o.early("x > 710.0", lambda: o.ret(o.t("infinityValue()")))
    zero = o.const(0.0)
    o.early("x < -746.0", lambda: o.ret(zero))
    k, rh, rl = reduce_exp(o, "x", None)
    r = o.t(f"expScaled({rh}, {rl}, {k})")
    o.ret(r)
    ops.append(o)

    o = Op("exp2Value", "2 to the power x, as a double", [("x", "Float64")], "Float64")
    exp_head(o)
    o.early("x >= 1024.0", lambda: o.ret(o.t("infinityValue()")))
    zero = o.const(0.0)
    o.early("x < -1080.0", lambda: o.ret(zero))
    kf = round_nearest(o, "x")
    k = o.t(f"convert.float64ToInt64({kf})")
    f = o.t(f"x - {kf}")
    p, e = two_prod(o, f, lit(LN2H))
    e2 = o.t(f"{e} + ({f} * {lit(LN2L)})")
    uh, ul = fast_two_sum(o, p, e2)
    r = o.t(f"expScaled({uh}, {ul}, {k})")
    o.ret(r)
    ops.append(o)

    o = Op("expm1Value", "e to the power x less 1, as a double", [("x", "Float64")], "Float64")
    exp_head(o)
    o.early("x > 710.0", lambda: o.ret(o.t("infinityValue()")))
    m1 = o.const(-1.0)
    o.early("x < -40.0", lambda: o.ret(m1))
    a = o.t("absoluteOf(x)")
    o.early(f"{a} < {lit(2.0 ** -54)}", lambda: o.ret("x"))
    k, rh, rl = reduce_exp(o, "x", None)
    r = o.t(f"expm1Scaled({rh}, {rl}, {k})")
    o.ret(r)
    ops.append(o)

    # ---------------------------------------------------------------- log family values
    def log_prep(o, src):
        """Scaled argument and extra for a positive finite double."""
        xs = o.var("Float64", "1.0")
        ex = o.var("Float64", "0.0")
        o.setv(xs, src)
        sub, norm = o.lab("sub"), o.lab("norm")
        o.when(f"{src} < {lit(2.2250738585072014e-308)}", sub, norm)
        o.label(sub)
        o.calc_set(xs, f"{src} * {lit(18014398509481984.0)}")
        o.calc_set(ex, "0.0 - 54.0")
        o.goto(norm)
        o.label(norm)
        return xs, ex

    def log_triple(o, xs, ex, ulv):
        E = o.t(f"logParts({xs}, {ulv}, {ex}, 0)")
        lh = o.t(f"logParts({xs}, {ulv}, {ex}, 1)")
        ll = o.t(f"logParts({xs}, {ulv}, {ex}, 2)")
        return E, lh, ll

    def log_head(o, x, pole_value):
        o.early(f"!({x} == {x})", lambda: o.ret(o.t(f"{x} + {x}")))
        o.early(f"{x} < 0.0", lambda: o.ret(o.t("invalidValue()")))
        ninf = o.const(-1.0)
        o.early(f"{x} == 0.0", lambda: o.ret(o.t(f"{ninf} / 0.0")))
        o.early(f"{x} > {lit(MAXD)}", lambda: o.ret(o.t("infinityValue()")))
        zero = o.const(0.0)
        o.early(f"{x} == 1.0", lambda: o.ret(zero))

    def finish_ln(o, E, lh, ll):
        p, e = two_prod(o, E, lit(LN2H))
        e2 = o.t(f"{e} + ({E} * {lit(LN2L)})")
        th, tl = dd_add(o, p, e2, lh, ll)
        return th

    def finish_log2(o, E, lh, ll):
        ph, pl = dd_mul(o, lh, ll, lit(INVLN2H), lit(INVLN2L))
        sh, sl = two_sum(o, E, ph)
        e2 = o.t(f"{sl} + {pl}")
        return o.t(f"{sh} + {e2}")

    def finish_log10(o, E, lh, ll):
        p, e = two_prod(o, E, lit(LOG10_2H))
        e2 = o.t(f"{e} + ({E} * {lit(LOG10_2L)})")
        ph, pl = dd_mul(o, lh, ll, lit(INVLN10H), lit(INVLN10L))
        th, tl = dd_add(o, p, e2, ph, pl)
        return th

    for name, doc, fin in (("logValue", "The natural logarithm of x, as a double", finish_ln),
                           ("log2Value", "The base 2 logarithm of x, as a double", finish_log2),
                           ("log10Value", "The base 10 logarithm of x, as a double", finish_log10)):
        o = Op(name, doc, [("x", "Float64")], "Float64")
        log_head(o, "x", None)
        xs, ex = log_prep(o, "x")
        z = o.const(0.0)
        E, lh, ll = log_triple(o, xs, ex, z)
        r = fin(o, E, lh, ll)
        o.ret(r)
        ops.append(o)

    o = Op("log1pValue", "The natural logarithm of 1 + x, as a double", [("x", "Float64")], "Float64")
    o.early("!(x == x)", lambda: o.ret(o.t("x + x")))
    o.early("x == -1.0", lambda: o.ret(o.t(f"{o.const(-1.0)} / 0.0")))
    o.early("x < -1.0", lambda: o.ret(o.t("invalidValue()")))
    o.early(f"x > {lit(MAXD)}", lambda: o.ret(o.t("infinityValue()")))
    a = o.t("absoluteOf(x)")
    o.early(f"{a} < {lit(2.0 ** -54)}", lambda: o.ret("x"))
    uh, ul = two_sum(o, "1.0", "x")
    z = o.const(0.0)
    E, lh, ll = log_triple(o, uh, z, ul)
    r = finish_ln(o, E, lh, ll)
    o.ret(r)
    ops.append(o)

    # ---------------------------------------------------------------- pow
    o = Op("powValue", "x to the power y, as a double, with C99's special values", [("x", "Float64"), ("y", "Float64")], "Float64")
    one = o.const(1.0)
    zero = o.const(0.0)
    o.early("y == 0.0", lambda: o.ret(one))
    o.early("x == 1.0", lambda: o.ret(one))
    o.early("(!(x == x)) || (!(y == y))", lambda: o.ret(o.t("x + y")))
    ax = o.t("absoluteOf(x)")
    ay = o.t("absoluteOf(y)")

    def yinf():
        o.early(f"{ax} == 1.0", lambda: o.ret(one))
        up, down = o.lab("up"), o.lab("down")
        o.when("y > 0.0", up, down)
        o.label(up)
        o.early(f"{ax} > 1.0", lambda: o.ret(o.t("infinityValue()")))
        o.ret(zero)
        o.label(down)
        o.early(f"{ax} > 1.0", lambda: o.ret(zero))
        o.ret(o.t("infinityValue()"))
    o.early(f"{ay} > {lit(MAXD)}", yinf)
    kind = o.t("integerKind(y)")

    def xzero():
        neg, pos = o.lab("neg"), o.lab("pos")
        o.when("y < 0.0", neg, pos)
        o.label(neg)
        o.early(f"{kind} == 1", lambda: o.ret(o.t("signedLike(infinityValue(), x)")))
        o.ret(o.t("infinityValue()"))
        o.label(pos)
        o.early(f"{kind} == 1", lambda: o.ret("x"))
        o.ret(zero)
    o.early("x == 0.0", xzero)

    def xinf():
        pinf, ninf = o.lab("pinf"), o.lab("ninf")
        o.when("x > 0.0", pinf, ninf)
        o.label(pinf)
        o.early("y < 0.0", lambda: o.ret(zero))
        o.ret(o.t("infinityValue()"))
        o.label(ninf)
        yn, yp = o.lab("yn"), o.lab("yp")
        o.when("y < 0.0", yn, yp)
        o.label(yn)
        o.early(f"{kind} == 1", lambda: o.ret(o.t("signedLike(0.0, x)")))
        o.ret(zero)
        o.label(yp)
        o.early(f"{kind} == 1", lambda: o.ret("x"))
        o.ret(o.t("infinityValue()"))
    o.early(f"{ax} > {lit(MAXD)}", xinf)
    o.early(f"(x < 0.0) && ({kind} == 0)", lambda: o.ret(o.t("invalidValue()")))
    flip = o.t(f"(x < 0.0) && ({kind} == 1)")
    xs, ex = log_prep(o, ax)
    z = o.const(0.0)
    E, lh, ll = log_triple(o, xs, ex, z)
    p, e = two_prod(o, E, lit(LN2H))
    e2 = o.t(f"{e} + ({E} * {lit(LN2L)})")
    Lh, Ll = dd_add(o, p, e2, lh, ll)
    yc = o.var("Float64", "0.0")
    o.setv(yc, "y")
    big, keep = o.lab("big"), o.lab("keep")
    o.when(f"{ay} > {lit(2.0 ** 100)}", big, keep)
    o.label(big)
    o.calc_set(yc, f"signedLike({lit(2.0 ** 100)}, y)")
    o.goto(keep)
    o.label(keep)
    zp, ze = two_prod(o, Lh, yc)
    ze2 = o.t(f"{ze} + ({Ll} * {yc})")
    zh, zl = fast_two_sum(o, zp, ze2)
    res = o.var("Float64", "0.0")
    sign_it = o.lab("sign")
    over, nover = o.lab("over"), o.lab("nover")
    o.when(f"{zh} > 710.0", over, nover)
    o.label(over)
    o.calc_set(res, "infinityValue()")
    o.goto(sign_it)
    o.label(nover)
    under, nunder = o.lab("under"), o.lab("nunder")
    o.when(f"{zh} < -746.0", under, nunder)
    o.label(under)
    o.setv(res, zero)
    o.goto(sign_it)
    o.label(nunder)
    k, rh, rl = reduce_exp(o, zh, zl)
    mag = o.t(f"expScaled({rh}, {rl}, {k})")
    o.setv(res, mag)
    o.goto(sign_it)
    o.label(sign_it)
    flipit, keepit = o.lab("flip"), o.lab("keepit")
    o.when(flip, flipit, keepit)
    o.label(flipit)
    neg = o.t(f"{res} * -1.0")
    o.ret(neg)
    o.label(keepit)
    o.ret(res)
    ops.append(o)

    # ---------------------------------------------------------------- cbrt
    o = Op("cbrtValue", "The cube root of x, as a double", [("x", "Float64")], "Float64")
    o.early("!(x == x)", lambda: o.ret(o.t("x + x")))
    o.early("x == 0.0", lambda: o.ret("x"))
    o.early(f"(x > {lit(MAXD)}) || (x < {lit(-MAXD)})", lambda: o.ret("x"))
    ax = o.t("absoluteOf(x)")
    xs = o.var("Float64", "1.0")
    qa = o.var("Int64", "0")
    o.setv(xs, ax)
    sub, norm = o.lab("sub"), o.lab("norm")
    o.when(f"{ax} < {lit(2.2250738585072014e-308)}", sub, norm)
    o.label(sub)
    o.calc_set(xs, f"{ax} * {lit(18014398509481984.0)}")
    o.calc_set(qa, "0 - 18")
    o.goto(norm)
    o.label(norm)
    bitsu = o.t(f"convert.float64BitsToUInt64({xs})")
    fld = o.t(f"({bitsu} >> 52) & 2047")
    exb = o.t(f"convert.uint64BitsToInt64({fld})")
    ex = o.t(f"({exb} - 1023) + 3000")
    qq = o.t(f"{ex} / 3")
    rem = o.t(f"{ex} - (3 * {qq})")
    q = o.t(f"({qq} - 1000) + {qa}")
    q3 = o.t(f"3 * ({qq} - 1000)")
    nq3 = o.t(f"0 - {q3}")
    m = o.t(f"scaleBy({xs}, {nq3})")
    y = o.var("Float64", "1.5")
    for _ in range(9):
        y2 = o.t(f"{y} * {y}")
        d = o.t(f"{m} / {y2}")
        nxt = o.t(f"(({y} * 2.0) + {d}) / 3.0")
        o.setv(y, nxt)
    pp, pe = two_prod(o, y, y)
    c3h, c3l = dd_mul_d(o, pp, pe, y)
    res_ = o.t(f"(({m} - {c3h}) - {c3l})")
    y2 = o.t(f"({y} * {y}) * 3.0")
    delta = o.t(f"{res_} / {y2}")
    yy = o.t(f"{y} + {delta}")
    sc = o.t(f"scaleBy({yy}, {q})")
    r = o.t(f"signedLike({sc}, x)")
    o.ret(r)
    ops.append(o)

    # ---------------------------------------------------------------- hypot
    o = Op("hypotValue", "The square root of x*x + y*y without undue overflow or underflow, as a double", [("x", "Float64"), ("y", "Float64")], "Float64", effect=True)
    ax = o.t("absoluteOf(x)")
    ay = o.t("absoluteOf(y)")
    o.early(f"({ax} > {lit(MAXD)}) || ({ay} > {lit(MAXD)})", lambda: o.ret(o.t("infinityValue()")))
    o.early("(!(x == x)) || (!(y == y))", lambda: o.ret(o.t("x + y")))
    big = o.var("Float64", "0.0")
    small = o.var("Float64", "0.0")
    o.setv(big, ax)
    o.setv(small, ay)
    sw, nsw = o.lab("sw"), o.lab("nsw")
    o.when(f"{ay} > {ax}", sw, nsw)
    o.label(sw)
    o.setv(big, ay)
    o.setv(small, ax)
    o.goto(nsw)
    o.label(nsw)
    o.early(f"{small} <= ({big} * {lit(2.0 ** -30)})", lambda: o.ret(big))
    bitsu = o.t(f"convert.float64BitsToUInt64({big})")
    fld = o.t(f"({bitsu} >> 52) & 2047")
    exb = o.t(f"convert.uint64BitsToInt64({fld})")
    ex = o.var("Int64", "0")
    o.calc_set(ex, f"{exb} - 1023")
    sub, norm = o.lab("sub"), o.lab("norm")
    bigs = o.var("Float64", "0.0")
    smalls = o.var("Float64", "0.0")
    adj = o.var("Int64", "0")
    o.setv(bigs, big)
    o.setv(smalls, small)
    o.when(f"{exb} == 0", sub, norm)
    o.label(sub)
    o.calc_set(bigs, f"{big} * {lit(2.0 ** 200)}")
    o.calc_set(smalls, f"{small} * {lit(2.0 ** 200)}")
    o.calc_set(adj, "0 - 200")
    o.goto(norm)
    o.label(norm)
    bits2 = o.t(f"convert.float64BitsToUInt64({bigs})")
    fld2 = o.t(f"({bits2} >> 52) & 2047")
    exb2 = o.t(f"convert.uint64BitsToInt64({fld2})")
    e2_ = o.t(f"{exb2} - 1023")
    ne = o.t(f"0 - {e2_}")
    a_ = o.t(f"scaleBy({bigs}, {ne})")
    b_ = o.t(f"scaleBy({smalls}, {ne})")
    h1, l1 = two_prod(o, a_, a_)
    h2, l2 = two_prod(o, b_, b_)
    sh, sl = dd_add(o, h1, l1, h2, l2)
    root = o.t(f"machine.squareRoot({sh})")
    ph, pl = two_prod(o, root, root)
    diff = o.t(f"((({sh} - {ph}) - {pl}) + {sl})")
    corr = o.t(f"{diff} / ({root} * 2.0)")
    rr = o.t(f"{root} + {corr}")
    tot = o.t(f"{e2_} + {adj}")
    out = o.t(f"scaleBy({rr}, {tot})")
    o.ret(out)
    ops.append(o)

    # ---------------------------------------------------------------- the C functions
    def public(cname, vop, arity, errno):
        names = {"x": "x", "y": "y"}
        args = ["x", "y"][:arity]
        inputs = [(a, "Float64") for a in args]
        pub = Op(PUBLIC[cname][0], PUBLIC[cname][1], inputs, "Float64",
                 invariant=(PUBLIC[cname][2], PUBLIC[cname][3]), abi=cname, effect=cname != "cbrt")
        r = pub.t(f"{vop}({', '.join(args)})")
        errno(pub, r, [f"{a}" for a in args], "Float64")
        pub.ret(r)
        return pub

    def single(cname, vop, arity, errno):
        args = ["x", "y"][:arity]
        inputs = [(a, "Float32") for a in args]
        pub = Op(PUBLIC[cname][0] + "Single", PUBLIC[cname][1].replace(", as a double", "") + " for floats", inputs,
                 "Float32", invariant=(PUBLIC[cname][2], PUBLIC[cname][3]), abi=cname + "f", effect=cname != "cbrt")
        wide = [pub.t(f"convert.float32ToFloat64({a})", "w") for a in args]
        v = pub.t(f"{vop}({', '.join(wide)})")
        r = pub.t(f"narrowOf({v})")
        back = pub.t(f"convert.float32ToFloat64({r})")
        errno(pub, back, wide, "Float32")
        pub.ret(r)
        return pub

    def exp_errno(over, under):
        def f(o, r, args, ty):
            x = args[0]
            fin = o.t(f"absoluteOf({x}) <= {lit(MAXD)}")
            un = fin if under else o.const("false", "Bool")
            o.lines.append(f"  noteRange({r}, {fin}, {un})")
        return f

    def log_errno(pole):
        def f(o, r, args, ty):
            pk = o.const(pole)
            o.lines.append(f"  noteDomain({args[0]}, {pk})")
        return f

    def pow_errno(o, r, args, ty):
        x, y = args
        fx = o.t(f"absoluteOf({x}) <= {lit(MAXD)}")
        fy = o.t(f"absoluteOf({y}) <= {lit(MAXD)}")
        fin = o.t(f"{fx} && {fy}")
        nz = o.t(f"{fin} && ({x} != 0.0)")
        o.lines.append(f"  noteRange({r}, {fin}, {nz})")
        nn = o.t(f"({x} == {x}) && ({y} == {y})")
        o.lines.append(f"  noteInvalid({r}, {nn})")

    def hyp_errno(o, r, args, ty):
        x, y = args
        fx = o.t(f"absoluteOf({x}) <= {lit(MAXD)}")
        fy = o.t(f"absoluteOf({y}) <= {lit(MAXD)}")
        fin = o.t(f"{fx} && {fy}")
        o.lines.append(f"  noteRange({r}, {fin}, {o.const('false', 'Bool')})")

    def none(o, r, args, ty):
        pass

    table = [("exp", "expValue", 1, exp_errno(True, True)),
             ("exp2", "exp2Value", 1, exp_errno(True, True)),
             ("expm1", "expm1Value", 1, exp_errno(True, False)),
             ("log", "logValue", 1, log_errno("0.0")),
             ("log2", "log2Value", 1, log_errno("0.0")),
             ("log10", "log10Value", 1, log_errno("0.0")),
             ("log1p", "log1pValue", 1, log_errno("-1.0")),
             ("pow", "powValue", 2, pow_errno),
             ("cbrt", "cbrtValue", 1, none),
             ("hypot", "hypotValue", 2, hyp_errno)]
    for cname, vop, arity, errno in table:
        ops.append(public(cname, vop, arity, errno))
        ops.append(single(cname, vop, arity, errno))
    return ops


PUBLIC = {
    "exp": ("exponential", "exp: e to the power x, as a double", "givesExp", "Gives e^x correctly rounded but for the rarest cases: 1 at 0, infinity past 709.78, 0 below -745.13"),
    "exp2": ("exponentialBase2", "exp2: 2 to the power x, as a double", "givesExp2", "Gives 2^x, exact for whole x, infinity from 1024, 0 below -1075"),
    "expm1": ("exponentialMinusOne", "expm1: e to the power x less 1, as a double", "givesExpm1", "Gives e^x - 1 accurately for small x, -1 below -40, x itself for tiny x and for -0"),
    "log": ("naturalLogarithm", "log: the natural logarithm, as a double", "givesLog", "Gives ln x: -infinity at 0, NaN below 0, 0 at 1"),
    "log2": ("logarithmBase2", "log2: the base 2 logarithm, as a double", "givesLog2", "Gives log2 x, exact at powers of 2"),
    "log10": ("logarithmBase10", "log10: the base 10 logarithm, as a double", "givesLog10", "Gives log10 x, exact at powers of 10"),
    "log1p": ("logarithmOnePlus", "log1p: the natural logarithm of 1 + x, as a double", "givesLog1p", "Gives ln(1 + x) accurately for small x, -infinity at -1, NaN below"),
    "pow": ("power", "pow: x to the power y, as a double", "givesPow", "Gives x^y with C99's special values: 1 for y 0 and for x 1, NaN for a negative x and a fractional y"),
    "cbrt": ("cubeRoot", "cbrt: the cube root, as a double", "givesCbrt", "Gives the cube root of any sign, exact at cubes"),
    "hypot": ("hypotenuse", "hypot: the square root of x*x + y*y, as a double", "givesHypot", "Gives sqrt(x*x + y*y) without overflow in the squares, infinity if either is infinite"),
}


# ---------------------------------------------------------------- unit tests

def f32(a):
    import struct
    try:
        return struct.unpack("<f", struct.pack("<f", a))[0]
    except OverflowError:
        return float("inf")


def exact(fname, args):
    """The correctly rounded value of a function at doubles (Decimal at 110 digits)."""
    D = Decimal
    x = D(args[0])
    ln2 = Decimal(2).ln()
    if fname == "exp":
        v = x.exp()
    elif fname == "exp2":
        v = (x * ln2).exp()
    elif fname == "expm1":
        v = x.exp() - 1
    elif fname == "log":
        v = x.ln()
    elif fname == "log2":
        v = x.ln() / ln2
    elif fname == "log10":
        v = x.log10()
    elif fname == "log1p":
        v = x if abs(x) < Decimal("1e-40") else (1 + x).ln()
    elif fname == "cbrt":
        v = abs(x) ** (D(1) / 3)
        for _ in range(3):
            v = v - (v ** 3 - abs(x)) / (3 * v * v)
        if x < 0:
            v = -v
    elif fname == "hypot":
        y = D(args[1])
        v = (x * x + y * y).sqrt()
    elif fname == "pow":
        y = D(args[1])
        v = (y * abs(x).ln()).exp()
        if x < 0 and y == int(y) and int(y) % 2 == 1:
            v = -v
    return float(v)


CASES = {
    "exp": [[0.0], [1.0], [-1.0], [0.5], [10.0], [-10.0], [100.0], [709.0], [-700.0], [1e-10], [0.3], [-740.0],
            [-745.0], [20.5], [-0.0001]],
    "exp2": [[0.0], [1.0], [-1.0], [0.5], [10.0], [-10.5], [100.25], [1023.5], [-1060.0], [1e-10], [0.3], [-1074.0],
             [3.0]],
    "expm1": [[1.0], [-1.0], [0.5], [10.0], [-10.0], [1e-10], [-1e-10], [0.3], [-0.3], [700.0], [-30.0], [1e-3],
              [0.34657359027997264]],
    "log": [[1.0000001], [2.0], [0.5], [10.0], [1e-300], [5e-324], [1.7976931348623157e308], [0.9999999], [3.0],
            [100.0], [2.718281828459045]],
    "log2": [[8.0], [1.0000001], [0.1], [10.0], [1e-300], [5e-324], [1024.0], [3.0], [0.75], [1.7976931348623157e308]],
    "log10": [[1000.0], [1e-5], [2.0], [0.001], [1.0000001], [5e-324], [12345.678], [1e22]],
    "log1p": [[1e-10], [-1e-10], [0.5], [-0.5], [1.0], [1e10], [-0.9999999], [1e-300], [3.0], [-0.99]],
    "cbrt": [[27.0], [-27.0], [2.0], [0.001], [1e300], [5e-324], [-8.0], [1.7976931348623157e308], [10.0], [0.125]],
    "hypot": [[3.0, 4.0], [1e300, 1e300], [1e-300, 1e-300], [5e-324, 5e-324], [1.0, 1e-20], [0.1, 0.2], [-5.0, 12.0],
              [1e307, 1e307]],
    "pow": [[2.0, 10.0], [2.0, 0.5], [10.0, -3.0], [-2.0, 3.0], [-2.0, 4.0], [1.0000001, 1e7], [0.5, 1074.0],
            [1.5, 100.0], [10.0, 308.0], [2.0, -1074.0], [3.0, 0.3333333333333333], [7.0, 2.0], [100.0, 0.5],
            [0.1, 20.0]],
}

WITHIN = """op withinUlps "Whether a double is the expected one or a neighbour of it"
  input expected Float64 copied
  input actual Float64 copied
  input limit Int64 copied
  output Bool
:begin
  calc same = expected == actual
  when same yes check
:yes
  return same
:check
  calc eb = convert.float64BitsToUInt64(absoluteOf(expected))
  calc ab = convert.float64BitsToUInt64(absoluteOf(actual))
  calc ei = convert.uint64BitsToInt64(eb)
  calc ai = convert.uint64BitsToInt64(ab)
  calc gap = ei - ai
  calc distance = ai - ei
  calc negative = (expected < 0.0) && (actual < 0.0)
  calc positive = (expected >= 0.0) && (actual >= 0.0)
  calc sameSign = negative || positive
  calc near1 = (gap <= limit) && (distance <= limit)
  calc result = sameSign && near1
  return result

op closeSingle "Whether a float is within a float's last place of an expected double"
  input expected Float64 copied
  input actual Float32 copied
  output Bool
:begin
  calc wide = convert.float32ToFloat64(actual)
  calc diff = absoluteOf(wide - expected)
  calc bound = absoluteOf(expected) * 1.1920929e-7
  calc near = diff <= bound
  return near
"""


def tests_text():
    out = [WITHIN]
    for fam, names in (("exp", ["exp", "exp2", "expm1"]), ("log", ["log", "log2", "log10", "log1p"]),
                       ("pow", ["pow"]), ("root", ["cbrt", "hypot"])):
        lines, verifies = [], []
        for cname in names:
            pubname, _doc, inv, _d = PUBLIC[cname]
            verifies += [f"  verifies {pubname} {inv}", f"  verifies {pubname}Single {inv}"]
            for i, args in enumerate(CASES[cname]):
                e = exact(cname, args)
                arg = ", ".join(lit(a) for a in args)
                lines.append(f"  calc {cname}d{i} = {pubname}({arg})")
                lines.append(f"  calc {cname}dok{i} = withinUlps({lit(e)}, {cname}d{i}, 1)")
                lines.append(f"  test.assertTrue({cname}dok{i})")
                fa = [f32(a) for a in args]
                if fa != args:
                    continue
                e32 = e
                if not all(a == 0 or 1.5e-38 < abs(a) < 3.0e38 for a in args) or not (1.5e-38 < abs(e32) < 3.0e38):
                    continue
                sarg = ", ".join(f"convert.float64ToFloat32({lit(a)})" for a in args)
                lines.append(f"  calc {cname}f{i} = {pubname}Single({sarg})")
                lines.append(f"  calc {cname}fok{i} = closeSingle({lit(e32)}, {cname}f{i})")
                lines.append(f"  test.assertTrue({cname}fok{i})")
        out.append(f'test {fam}Test "{", ".join(names)} give the correctly rounded value within one last place at sample points, in double and float forms"')
        out += verifies
        out += ["  effect use machine.memory", "  uses memoryAccess", ":begin"] + lines + ["  return", ""]
    sp = []
    n = [0]

    def chk(expr):
        n[0] += 1
        sp.append(f"  calc sp{n[0]} = {expr}")
        sp.append(f"  test.assertTrue(sp{n[0]})")
    sp.append("  calc inf = convert.uint64BitsToFloat64(9218868437227405312)")
    sp.append("  calc ninf = convert.uint64BitsToFloat64(18442240474082181120)")
    sp.append("  calc nan = convert.uint64BitsToFloat64(9221120237041090560)")
    for e in ["exponential(inf) == inf", "exponential(ninf) == 0.0", "exponential(800.0) == inf",
              "exponential(-800.0) == 0.0", "!(exponential(nan) == exponential(nan))",
              "exponentialMinusOne(ninf) == -1.0", "exponentialMinusOne(-0.0) == 0.0",
              "exponentialBase2(1024.0) == inf", "exponentialBase2(-1075.0) == 0.0",
              "exponentialBase2(-1074.0) == 5e-324", "naturalLogarithm(0.0) == ninf",
              "!(naturalLogarithm(-1.0) == naturalLogarithm(-1.0))", "naturalLogarithm(inf) == inf",
              "naturalLogarithm(1.0) == 0.0", "logarithmOnePlus(-1.0) == ninf", "logarithmBase2(8.0) == 3.0",
              "logarithmBase10(1000.0) == 3.0", "power(5.0, 0.0) == 1.0", "power(nan, 0.0) == 1.0",
              "power(1.0, nan) == 1.0", "!(power(nan, 2.0) == power(nan, 2.0))", "power(0.0, -1.0) == inf",
              "power(-0.0, -3.0) == ninf", "power(0.0, 3.0) == 0.0", "power(-1.0, inf) == 1.0",
              "power(0.5, inf) == 0.0", "power(2.0, ninf) == 0.0", "power(2.0, inf) == inf",
              "power(ninf, 3.0) == ninf", "power(ninf, -3.0) == 0.0", "power(ninf, 2.0) == inf",
              "!(power(-2.0, 0.5) == power(-2.0, 0.5))", "power(10.0, 2.0) == 100.0", "power(2.0, 1024.0) == inf",
              "power(-2.0, 1025.0) == ninf", "power(2.0, -1080.0) == 0.0", "cubeRoot(27.0) == 3.0",
              "cubeRoot(-8.0) == -2.0", "cubeRoot(inf) == inf", "hypotenuse(3.0, 4.0) == 5.0",
              "hypotenuse(nan, inf) == inf", "hypotenuse(ninf, 1.0) == inf", "hypotenuse(0.0, -0.0) == 0.0"]:
        chk(e)
    out.append('test specialTest "Infinities, zeros, NaNs, overflow and underflow, and the whole-number cases of pow, as C99 Annex F gives them"')
    out += ["  verifies power givesPow", "  effect use machine.memory", "  uses memoryAccess", ":begin"] + sp + ["  return", ""]
    return "\n".join(out)


def main():
    ops = build_ops()
    head = ('module cmathexp "math.h\'s exponentials, logarithms, pow, cbrt and hypot written in SemanticScript, double and float forms, as glibc gives them to within one unit in the last place"\n'
            "  path cmathexp\n"
            "  imports standard.machine standard.math standard.compare standard.convert standard.bits standard.logic standard.test clibrary\n"
            "  exports exponential naturalLogarithm power\n\n"
            'capability memoryAccess "Authority to set errno and to take a square root" use machine.memory none\n\n'
            "## cmathexp: written by tools/cmathexpgen.py, which computes every constant (ln 2 in parts, series coefficients)\n"
            "## with Decimal and Fraction. Do not edit by hand. The algorithms are double-double (Dekker, Knuth); see the generator.\n")
    body = "\n\n".join(o.render() for o in ops)
    tests = tests_text()
    with open(os.path.join(HERE, "cmathexp.dsl"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(head + "\n" + body + "\n" + (("\n@tests\n\n" + tests) if tests else ""))
    print("cmathexp.dsl written:", len(ops), "ops")


if __name__ == "__main__":
    main()
