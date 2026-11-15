"""Generate tools/cmathlong.dsl: math.h's transcendental long double functions in SemanticScript (cmathlong).

    python cmathlonggen.py            # writes cmathlong.dsl next to this file

Method (one method for all three formats of long double, D-174): every function is computed on a 320-bit floating
point number of its own ("bf": a sign, a kind, a power of two, and ten 32-bit limbs, normalized), held in the 128
registers of a workspace taken from the heap for the call, and rounded once to the format through clong's `settleAs`.
So a result is accurate to about 2^-300 before that rounding, and is the correctly rounded value of the format
except when the exact value lies that close to a rounding boundary: the same code, with the same bound, serves x87's
64 bits, binary128's 113 bits and a double (Windows), and its tests run on all three layouts from any machine. No long
double arithmetic is used. Every constant (ln 2, pi, the Bernoulli numbers, the bits of 2/pi) is computed here with
Python integers and written as hexadecimal text.

  exp, exp2, expm1: x = n ln 2 + r, expm1(r/256) by Taylor series, eight doublings p <- 2p + p^2.
  log, log2, log10, log1p: x = 2^k m, m near 1, ln m = 2 atanh((m-1)/(m+1)) by its series.
  pow: exp(y ln|x|); cbrt: exp(ln|x| / 3); hypot: Newton's square root of x^2 + y^2.
  sin, cos, tan: Payne and Hanek's reduction with 2/pi to 17,200 bits, then Taylor series; asin, acos, atan, atan2:
      three halvings atan t = 2 atan (t / (1 + sqrt(1 + t^2))) and the series.
  sinh, cosh, tanh, asinh, acosh, atanh: from expm1, exp and log1p so that nothing cancels.
  erf, erfc: the series e^(-x^2) sum 2^n x^(2n+1) / (1 3 ... (2n+1)) (no cancellation) and Laplace's continued fraction.
  tgamma, lgamma: Stirling's series after shifting the argument to 64 or more, reflection below 0.
  fma: exact integer arithmetic on 32-bit limbs, with the one rounding of settleAs.
"""
from __future__ import annotations

import os
import sys
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cmathlongbuild import ADDR, Op, ALL, new, ld, ldi, st, sti, LIM, HEAD, N, REG, BUF_P, BUF_Q, BUF_T, BUF_U, WS_BYTES, MASK  # noqa: E402
import cmathlongtables as T  # noqa: E402


def prims():
    o = new("limbOr", "A cell of an array of limbs in the workspace, 0 outside the array",
            [("base", "Int64"), ("count", "Int64"), ("w", "Int64")], "UInt64")
    nothing = o.const("UInt64", "0", "nothing")
    o.if_("w < 0 || w >= count", lambda: o.ret(nothing))
    v = o.calc(ld("base + w * 8"))
    o.ret(v)

    o = new("bitsAt", "32 bits of an array of limbs from a bit place (which may be below 0 or past the end: zeros)",
            [("base", "Int64"), ("count", "Int64"), ("p", "Int64")], "UInt64")
    q = o.calc("p + 1024")
    w = o.calc(f"({q} >> 5) - 32")
    b = o.calc(f"{q} & 31")
    lo = o.calc(f"limbOr(ws, base, count, {w})")
    hi = o.calc(f"limbOr(ws, base, count, {w} + 1)")
    sh = o.calc(f"32 - {b}")
    v = o.calc(f"(({lo} >> {b}) | ({hi} << {sh})) & {MASK}")
    o.ret(v)

    o = new("getHead", "A register's sign (0), kind (1: 0 zero, 1 finite), or power (2)",
            [("r", "Int64"), ("k", "Int64")], "Int64")
    v = o.calc(ldi("r * 128 + k * 8").replace("loadInt64", "loadInt64"))
    o.ret(v)

    o = new("setHead", "Set a register's sign, kind, or power", [("r", "Int64"), ("k", "Int64"), ("v", "Int64")])
    o.call(sti("r * 128 + k * 8", "v"))
    o.ret()

    o = new("getLimb", "A register's limb, from the lowest", [("r", "Int64"), ("i", "Int64")], "UInt64")
    v = o.calc(ld(LIM("r", "i")))
    o.ret(v)

    o = new("setLimb", "Set a register's limb", [("r", "Int64"), ("i", "Int64"), ("v", "UInt64")])
    o.call(st(LIM("r", "i"), "v"))
    o.ret()

    # bfPack: an array of limbs times 2^exp, normalized into a register
    o = new("bfPack", "Put the value of an array of limbs (cells of the workspace, from the lowest) times 2 to a power in a register: normalized to ten limbs, the bits below truncated",
            [("d", "Int64"), ("base", "Int64"), ("count", "Int64"), ("sign", "Int64"), ("power", "Int64")])
    nothing = o.const("UInt64", "0", "nothing")
    i = o.var("Int64", "0", "i")
    o.set(i, "count - 1")

    def scan():
        c = o.calc(ld(f"base + {i} * 8"))
        o.if_(f"{c} != {nothing}", o.exit_loop)
        o.set(i, f"{i} - 1")

    o.while_(f"{i} >= 0", scan)

    def zero():
        o.call("setHead(ws, d, 0, sign)")
        o.call("setHead(ws, d, 1, 0)")
        o.ret()

    o.if_(f"{i} < 0", zero)
    top = o.calc(ld(f"base + {i} * 8"))
    bits = o.calc(f"clong.bitLength({nothing}, {top})")
    length = o.calc(f"{i} * 32 + {bits}")
    o.call("setHead(ws, d, 0, sign)")
    o.call("setHead(ws, d, 1, 1)")
    o.call(f"setHead(ws, d, 2, power + {length} - 320)")

    def put(j):
        v = o.calc(f"bitsAt(ws, base, count, {length} - 320 + {j} * 32)")
        o.call(f"setLimb(ws, d, {j}, {v})")

    o.for_(0, N, put)
    o.ret()

    o = new("bfCopy", "Copy a register", [("d", "Int64"), ("a", "Int64")])

    def cp(k):
        o.call(st(HEAD("d", 0) + f" + {k} * 8", ld(HEAD("a", 0) + f" + {k} * 8")))

    o.for_(0, 13, cp)
    o.ret()

    o = new("bfNegate", "Flip a register's sign", [("a", "Int64")])
    s = o.calc("getHead(ws, a, 0)")
    o.call(f"setHead(ws, a, 0, 1 - {s})")
    o.ret()

    o = new("bfShift", "Multiply a register by 2 to a power", [("a", "Int64"), ("k", "Int64")])
    e = o.calc("getHead(ws, a, 2)")
    o.call(f"setHead(ws, a, 2, {e} + k)")
    o.ret()

    o = new("bfSetInt", "Set a register to a whole number (below 2^62 in magnitude) times 2 to a power",
            [("d", "Int64"), ("v", "Int64"), ("power", "Int64")])
    neg = o.calc("v < 0")
    mag = o.var("Int64", "0", "m")
    o.if_(neg, lambda: o.set(mag, "0 - v"), lambda: o.set(mag, "v"))
    mu = o.calc(f"convert.int64ToUInt64({mag})")
    o.call(st(f"{BUF_P}", f"{mu} & {MASK}"))
    o.call(st(f"{BUF_P} + 8", f"{mu} >> 32"))
    sg = o.var("Int64", "0", "s")
    o.if_(neg, lambda: o.set(sg, "1"))
    o.call(f"bfPack(ws, d, {BUF_P}, 2, {sg}, power)")
    o.ret()

    o = new("bfKind", "A register's kind (0 zero, 1 finite)", [("a", "Int64")], "Int64")
    v = o.calc("getHead(ws, a, 1)")
    o.ret(v)

    o = new("bfLog2Of", "floor(log2 |a|) + 1 of a nonzero register: its value is below 2 to this and not below half of it",
            [("a", "Int64")], "Int64")
    e = o.calc("getHead(ws, a, 2)")
    v = o.calc(f"{e} + 320")
    o.ret(v)

    # ---------------------------------------------------------------- multiply
    o = new("bfMul", "d = a * b (the product truncated to the register's 320 bits)",
            [("d", "Int64"), ("a", "Int64"), ("b", "Int64")])
    sa = o.calc("getHead(ws, a, 0)")
    sb = o.calc("getHead(ws, b, 0)")
    sign = o.calc(f"({sa} + {sb}) & 1")
    ka = o.calc("getHead(ws, a, 1)")
    kb = o.calc("getHead(ws, b, 1)")

    def zero():
        o.call(f"setHead(ws, d, 0, {sign})")
        o.call("setHead(ws, d, 1, 0)")
        o.ret()

    o.if_(f"{ka} == 0 || {kb} == 0", zero)
    ea = o.calc("getHead(ws, a, 2)")
    eb = o.calc("getHead(ws, b, 2)")
    nothing = o.const("UInt64", "0", "nothing")

    def clear(j):
        o.call(st(f"{BUF_P} + {j} * 8", nothing))

    o.for_(0, 2 * N, clear)

    def outer(i):
        carry = o.var("UInt64", "0", "c")
        o.set(carry, nothing)
        ai = o.calc(ld(LIM("a", i)))

        def inner(j):
            bj = o.calc(ld(LIM("b", j)))
            at = f"{BUF_P} + ({i} + {j}) * 8"
            cur = o.calc(ld(at))
            t = o.calc(f"{ai} * {bj} + {cur} + {carry}")
            o.call(st(at, f"{t} & {MASK}"))
            o.set(carry, f"{t} >> 32")

        o.for_(0, N, inner)
        o.call(st(f"{BUF_P} + ({i} + {N}) * 8", carry))

    o.for_(0, N, outer)
    o.call(f"bfPack(ws, d, {BUF_P}, {2 * N}, {sign}, {ea} + {eb})")
    o.ret()

    # ---------------------------------------------------------------- magnitude compare, compare
    o = new("bfCompareMagnitude", "How |a| compares with |b|: -1, 0, or 1", [("a", "Int64"), ("b", "Int64")], "Int64")
    less = o.const("Int64", "-1", "less")
    same = o.const("Int64", "0", "same")
    more = o.const("Int64", "1", "more")
    ka = o.calc("getHead(ws, a, 1)")
    kb = o.calc("getHead(ws, b, 1)")
    o.if_(f"{ka} == 0 && {kb} == 0", lambda: o.ret(same))
    o.if_(f"{ka} == 0", lambda: o.ret(less))
    o.if_(f"{kb} == 0", lambda: o.ret(more))
    ea = o.calc("getHead(ws, a, 2)")
    eb = o.calc("getHead(ws, b, 2)")
    o.if_(f"{ea} < {eb}", lambda: o.ret(less))
    o.if_(f"{ea} > {eb}", lambda: o.ret(more))
    i = o.var("Int64", "0", "i")
    o.set(i, "9")

    def each():
        la = o.calc(ld(LIM("a", i)))
        lb = o.calc(ld(LIM("b", i)))
        o.if_(f"{la} < {lb}", lambda: o.ret(less))
        o.if_(f"{la} > {lb}", lambda: o.ret(more))
        o.set(i, f"{i} - 1")

    o.while_(f"{i} >= 0", each)
    o.ret(same)

    o = new("bfCompare", "How a compares with b: -1, 0, or 1", [("a", "Int64"), ("b", "Int64")], "Int64")
    less = o.const("Int64", "-1", "less")
    more = o.const("Int64", "1", "more")
    ka = o.calc("getHead(ws, a, 1)")
    kb = o.calc("getHead(ws, b, 1)")
    sa = o.calc(f"getHead(ws, a, 0) * {ka}")
    sb = o.calc(f"getHead(ws, b, 0) * {kb}")
    o.if_(f"{sa} != {sb}", lambda: o.if_(f"{sa} == 1", lambda: o.ret(less), lambda: o.ret(more)))
    m = o.calc("bfCompareMagnitude(ws, a, b)")
    res = o.var("Int64", "0", "res")
    o.if_(f"{sa} == 1", lambda: o.set(res, f"0 - {m}"), lambda: o.set(res, m))
    o.ret(res)

    o = new("bfSmall", "Whether a term is negligible against a sum: zero, or below the sum's top bit by more than 330 bits",
            [("term", "Int64"), ("sum", "Int64")], "Bool")
    yes = o.const("Bool", "true", "yes")
    no = o.const("Bool", "false", "no")
    kt = o.calc("getHead(ws, term, 1)")
    o.if_(f"{kt} == 0", lambda: o.ret(yes))
    ks = o.calc("getHead(ws, sum, 1)")
    o.if_(f"{ks} == 0", lambda: o.ret(no))
    et = o.calc("getHead(ws, term, 2)")
    es = o.calc("getHead(ws, sum, 2)")
    r = o.calc(f"{et} < {es} - 330")
    o.ret(r)

    # ---------------------------------------------------------------- add
    o = new("bfAdd", "d = a + b, or a - b when negate is 1, exact in a window of 640 bits below the larger",
            [("d", "Int64"), ("a", "Int64"), ("b", "Int64"), ("negate", "Int64")])
    nothing = o.const("UInt64", "0", "nothing")
    ka = o.calc("getHead(ws, a, 1)")
    kb = o.calc("getHead(ws, b, 1)")
    sa = o.calc("getHead(ws, a, 0)")
    sb = o.calc("(getHead(ws, b, 0) + negate) & 1")

    def b_is_zero():
        o.if_("d != a", lambda: o.call("bfCopy(ws, d, a)"))
        o.ret()

    def a_is_zero():
        o.call("bfCopy(ws, d, b)")
        o.if_(f"{kb} != 0", lambda: o.call(f"setHead(ws, d, 0, {sb})"))
        o.ret()

    o.if_(f"{kb} == 0", b_is_zero)
    o.if_(f"{ka} == 0", a_is_zero)
    order = o.calc("bfCompareMagnitude(ws, a, b)")
    big = o.var("Int64", "0", "big")
    small = o.var("Int64", "0", "small")
    sbig = o.var("Int64", "0", "sbig")
    o.if_(f"{order} >= 0", lambda: (o.set(big, "a"), o.set(small, "b"), o.set(sbig, sa)),
          lambda: (o.set(big, "b"), o.set(small, "a"), o.set(sbig, sb)))
    ebig = o.calc(f"getHead(ws, {big}, 2)")
    esmall = o.calc(f"getHead(ws, {small}, 2)")
    diff = o.calc(f"{ebig} - {esmall}")

    def far():
        o.if_("d != " + big, lambda: o.call(f"bfCopy(ws, d, {big})"))
        o.call(f"setHead(ws, d, 0, {sbig})")
        o.ret()

    o.if_(f"{diff} > 700", far)

    def fill(j):
        a1 = o.calc(f"bitsAt(ws, ({big}) * 128 + 24, 10, {j} * 32 - 320)")
        o.call(st(f"{BUF_P} + {j} * 8", a1))
        a2 = o.calc(f"bitsAt(ws, ({small}) * 128 + 24, 10, {j} * 32 - 320 + {diff})")
        o.call(st(f"{BUF_Q} + {j} * 8", a2))

    o.for_(0, 2 * N, fill)
    o.call(st(f"{BUF_P} + {2 * N} * 8", nothing))
    o.call(st(f"{BUF_Q} + {2 * N} * 8", nothing))
    one_cell = o.const("UInt64", "1", "oneCell")
    carry = o.var("UInt64", "0", "c")
    o.set(carry, nothing)
    sub_bit = o.calc(f"({sa} + {sb}) & 1")

    def addloop(j):
        pj = o.calc(ld(f"{BUF_P} + {j} * 8"))
        qj = o.calc(ld(f"{BUF_Q} + {j} * 8"))
        t = o.calc(f"{pj} + {qj} + {carry}")
        o.call(st(f"{BUF_P} + {j} * 8", f"{t} & {MASK}"))
        o.set(carry, f"{t} >> 32")

    def subloop(j):
        pj = o.calc(ld(f"{BUF_P} + {j} * 8"))
        qj = o.calc(ld(f"{BUF_Q} + {j} * 8"))
        owed = o.calc(f"{qj} + {carry}")
        short = o.calc(f"{pj} < {owed}")
        t = o.var("UInt64", "0", "u")
        o.if_(short, lambda: (o.set(t, f"{pj} + 4294967296 - {owed}"), o.set(carry, one_cell)),
              lambda: (o.set(t, f"{pj} - {owed}"), o.set(carry, nothing)))
        o.call(st(f"{BUF_P} + {j} * 8", t))

    o.if_(f"{sub_bit} == 0", lambda: o.for_(0, 2 * N + 1, addloop), lambda: o.for_(0, 2 * N + 1, subloop))
    o.call(f"bfPack(ws, d, {BUF_P}, {2 * N + 1}, {sbig}, {ebig} - 320)")
    o.ret()

    # ---------------------------------------------------------------- small multiples and divisions
    o = new("bfMulSmall", "d = a * k for a whole number k below 2^31", [("d", "Int64"), ("a", "Int64"), ("k", "Int64")])
    nothing = o.const("UInt64", "0", "nothing")
    ka = o.calc("getHead(ws, a, 1)")
    sa = o.calc("getHead(ws, a, 0)")

    def zero():
        o.call(f"setHead(ws, d, 0, {sa})")
        o.call("setHead(ws, d, 1, 0)")
        o.ret()

    o.if_(f"{ka} == 0 || k == 0", zero)
    kk = o.calc("convert.int64ToUInt64(k)")
    carry = o.var("UInt64", "0", "c")
    o.set(carry, nothing)

    def each(j):
        lj = o.calc(ld(LIM("a", j)))
        t = o.calc(f"{lj} * {kk} + {carry}")
        o.call(st(f"{BUF_P} + {j} * 8", f"{t} & {MASK}"))
        o.set(carry, f"{t} >> 32")

    o.for_(0, N, each)
    o.call(st(f"{BUF_P} + {N} * 8", carry))
    e = o.calc("getHead(ws, a, 2)")
    o.call(f"bfPack(ws, d, {BUF_P}, {N + 1}, {sa}, {e})")
    o.ret()

    o = new("bfDivSmall", "d = a / k for a whole number k from 1 to 2^31 (the quotient truncated to 320 bits)",
            [("d", "Int64"), ("a", "Int64"), ("k", "Int64")])
    nothing = o.const("UInt64", "0", "nothing")
    ka = o.calc("getHead(ws, a, 1)")
    sa = o.calc("getHead(ws, a, 0)")

    def zero():
        o.call(f"setHead(ws, d, 0, {sa})")
        o.call("setHead(ws, d, 1, 0)")
        o.ret()

    o.if_(f"{ka} == 0", zero)
    kk = o.calc("convert.int64ToUInt64(k)")
    rem = o.var("UInt64", "0", "r")
    o.set(rem, nothing)

    def each(j):
        # j counts 0..N+1 from the top: the limb is a's limb N-1-j, or 0 past the lowest
        idx = o.calc(f"{N - 1} - {j}")
        limb = o.var("UInt64", "0", "l")
        o.if_(f"{idx} >= 0", lambda: o.set(limb, ld(LIM("a", idx))), lambda: o.set(limb, nothing))
        cur = o.calc(f"({rem} << 32) | {limb}")
        q = o.calc(f"{cur} / {kk}")
        o.set(rem, f"{cur} % {kk}")
        o.call(st(f"{BUF_P} + ({N + 1} - {j}) * 8", q))

    o.for_(0, N + 2, each)
    e = o.calc("getHead(ws, a, 2)")
    o.call(f"bfPack(ws, d, {BUF_P}, {N + 2}, {sa}, {e} - 64)")
    o.ret()


if __name__ == "__main__":
    import cmathlongabi
    cmathlongabi.main()
