"""The elementary kernels of cmathlong on 320-bit registers: exp, log, sin and cos, atan, the reduction of a trig
argument, the nearest whole number, Stirling's series, and erf (see cmathlonggen.py for the registers)."""
from __future__ import annotations

from cmathlongbuild import ADDR, Op, ALL, new, ld, ldi, st, sti, LIM, HEAD, N, BUF_P, BUF_Q, BUF_T, BUF_U, MASK
from cmathlongkernels import (mul, add, sub, cp, divs, muls, setint, const, shift, neg, recip, div, sqrt, zero_reg)
import cmathlongtables as T

LN2, INV_LN2, INV_LN10, PI, TWO_OVER_SQRT_PI, INV_SQRT_PI, HALF_LN_2PI = range(7)


def exp_kernels():
    # expm1 of a register of magnitude at most 1, with full relative accuracy
    o = new("bfExpm1Small", "d = e^x - 1 for |x| up to 1: x / 256 by Taylor's series, then eight times p <- 2p + p^2",
            [("d", "Int64"), ("x", "Int64")])
    k = o.calc("getHead(ws, x, 1)")

    def zero():
        zero_reg(o, "d")
        o.ret()

    o.if_(f"{k} == 0", zero)
    cp(o, 40, "x")
    shift(o, 40, -8)
    cp(o, 41, 40)
    cp(o, 42, 40)

    def each(j):
        kk = o.calc(f"{j} + 2")
        mul(o, 41, 41, 40)
        divs(o, 41, 41, kk)
        add(o, 42, 42, 41)
        small = o.calc("bfSmall(ws, 41, 42)")
        o.if_(small, o.exit_loop)

    o.for_(0, 60, each)

    def double(_j):
        mul(o, 43, 42, 42)
        shift(o, 42, 1)
        add(o, 42, 42, 43)

    o.for_(0, 8, double)
    cp(o, "d", 42)
    o.ret()

    o = new("bfExp", "d = e^x for a register below 2^15 in magnitude: x = n ln 2 + r, e^r - 1 by bfExpm1Small, 2^n scaled in",
            [("d", "Int64"), ("x", "Int64")])
    const(o, 32, INV_LN2)
    mul(o, 33, "x", 32)
    n = o.calc("bfRoundInt(ws, 33)")
    setint(o, 34, n)
    const(o, 35, LN2)
    mul(o, 34, 34, 35)
    sub(o, 32, "x", 34)
    o.call("bfExpm1Small(ws, 33, 32)")
    setint(o, 34, 1)
    add(o, 33, 33, 34)
    shift(o, 33, n)
    cp(o, "d", 33)
    o.ret()

    o = new("bfExpm1", "d = e^x - 1 for any register below 2^15 in magnitude", [("d", "Int64"), ("x", "Int64")])
    k = o.calc("getHead(ws, x, 1)")

    def zero():
        zero_reg(o, "d")
        o.ret()

    o.if_(f"{k} == 0", zero)
    e2 = o.calc("getHead(ws, x, 2) + 320")

    def small():
        o.call("bfExpm1Small(ws, d, x)")
        o.ret()

    o.if_(f"{e2} <= 0", small)
    o.call("bfExp(ws, 36, x)")
    setint(o, 37, 1)
    sub(o, "d", 36, 37)
    o.ret()


def log_kernels():
    # 2 atanh(s) for a register s with |s| below 1/2
    o = new("bfAtanhTwice", "d = 2 atanh(s) = 2 (s + s^3/3 + s^5/5 + ...) for |s| below 1/2", [("d", "Int64"), ("s", "Int64")])
    k = o.calc("getHead(ws, s, 1)")

    def zero():
        zero_reg(o, "d")
        o.ret()

    o.if_(f"{k} == 0", zero)
    mul(o, 29, "s", "s")
    cp(o, 30, "s")
    cp(o, 31, "s")

    def each(j):
        kk = o.calc(f"{j} * 2 + 3")
        mul(o, 30, 30, 29)
        divs(o, 27, 30, kk)
        add(o, 31, 31, 27)
        small = o.calc("bfSmall(ws, 27, 31)")
        o.if_(small, o.exit_loop)

    o.for_(0, 400, each)
    shift(o, 31, 1)
    cp(o, "d", 31)
    o.ret()

    o = new("bfLog", "d = ln x for a positive register: x = 2^k m with m from 0.707 to 1.414, ln m = 2 atanh((m - 1) / (m + 1))",
            [("d", "Int64"), ("x", "Int64")])
    k = o.var("Int64", "0", "k")
    o.set(k, "getHead(ws, x, 2) + 319")
    cp(o, 24, "x")
    o.call("setHead(ws, 24, 0, 0)")
    o.call("setHead(ws, 24, 2, -319)")
    md = o.calc("bfTopDouble(ws, 24)")

    def halve():
        shift(o, 24, -1)
        o.set(k, f"{k} + 1")

    o.if_(f"{md} > 1.4142135623730951", halve)
    setint(o, 25, 1)
    sub(o, 26, 24, 25)
    add(o, 25, 24, 25)
    div(o, 26, 26, 25)
    o.call("bfAtanhTwice(ws, 26, 26)")

    def with_k():
        setint(o, 25, k)
        const(o, 24, LN2)
        mul(o, 25, 25, 24)
        add(o, 26, 26, 25)

    o.if_(f"{k} != 0", with_k)
    cp(o, "d", 26)
    o.ret()

    o = new("bfLog1p", "d = ln(1 + u) for a register u above -1: 2 atanh(u / (2 + u)) when |u| is below 1/2, else ln(1 + u)",
            [("d", "Int64"), ("u", "Int64")])
    k = o.calc("getHead(ws, u, 1)")

    def zero():
        zero_reg(o, "d")
        o.ret()

    o.if_(f"{k} == 0", zero)
    e2 = o.calc("getHead(ws, u, 2) + 320")

    def near():
        setint(o, 25, 2)
        add(o, 25, 25, "u")
        div(o, 26, "u", 25)
        o.call("bfAtanhTwice(ws, d, 26)")

    def far():
        setint(o, 25, 1)
        add(o, 25, 25, "u")
        o.call("bfLog(ws, d, 25)")

    o.if_(f"{e2} < 0", near, far)
    o.ret()


def trig_kernels():
    o = new("bfSinCos", "ds = sin r and dc = cos r for |r| up to 0.8 (Taylor series)",
            [("ds", "Int64"), ("dc", "Int64"), ("r", "Int64")])
    mul(o, 48, "r", "r")
    cp(o, 49, "r")
    cp(o, 50, "r")
    setint(o, 51, 1)
    setint(o, 52, 1)

    def each(j):
        two = o.calc(f"({j} + 1) * 2")
        a = o.calc(f"{two} * ({two} + 1)")
        b = o.calc(f"({two} - 1) * {two}")
        mul(o, 49, 49, 48)
        divs(o, 49, 49, a)
        neg(o, 49)
        add(o, 50, 50, 49)
        mul(o, 51, 51, 48)
        divs(o, 51, 51, b)
        neg(o, 51)
        add(o, 52, 52, 51)

    o.for_(0, 36, each)
    cp(o, "ds", 50)
    cp(o, "dc", 52)
    o.ret()

    o = new("bfAtan", "d = atan t for a nonnegative register: 1/t above 1, three halvings t / (1 + sqrt(1 + t^2)), then the series",
            [("d", "Int64"), ("t", "Int64")])
    k = o.calc("getHead(ws, t, 1)")

    def zero():
        zero_reg(o, "d")
        o.ret()

    o.if_(f"{k} == 0", zero)
    flag = o.var("Int64", "0", "flag")
    cp(o, 56, "t")
    setint(o, 57, 1)
    big = o.calc("bfCompare(ws, 56, 57)")

    def invert():
        recip(o, 56, 56)
        o.set(flag, "1")

    o.if_(f"{big} > 0", invert)

    def halving(_j):
        mul(o, 57, 56, 56)
        setint(o, 58, 1)
        add(o, 57, 57, 58)
        sqrt(o, 57, 57)
        add(o, 57, 57, 58)
        div(o, 56, 56, 57)

    o.for_(0, 3, halving)
    mul(o, 57, 56, 56)
    cp(o, 58, 56)
    cp(o, 59, 56)

    def each(j):
        kk = o.calc(f"{j} * 2 + 3")
        mul(o, 58, 58, 57)
        neg(o, 58)
        divs(o, 60, 58, kk)
        add(o, 59, 59, 60)
        small = o.calc("bfSmall(ws, 60, 59)")
        o.if_(small, o.exit_loop)

    o.for_(0, 120, each)
    shift(o, 59, 3)

    def back():
        const(o, 60, PI)
        shift(o, 60, -1)
        sub(o, 59, 60, 59)

    o.if_(f"{flag} == 1", back)
    cp(o, "d", 59)
    o.ret()

    # the reduction of a trig argument: |x| = M 2^E, the quadrant and r = |x| - n pi/2 in [-pi/4, pi/4]
    o = new("bfTrigReduce", "The quadrant (0 to 3) and the remainder r in [-pi/4, pi/4] (register d) of a long double's magnitude by pi/2: Payne and Hanek with 2/pi's bits",
            [("d", "Int64"), ("parts", ADDR)], "Int64")
    nothing = o.const("UInt64", "0", "nothing")
    one_cell = o.const("UInt64", "1", "oneCell")
    hi = o.calc("clong.highOf(parts)")
    lo = o.calc("clong.lowOf(parts)")
    power = o.calc("clong.getPart(parts, 16)")
    o.call(st(f"{BUF_U}", f"{lo} & {MASK}"))
    o.call(st(f"{BUF_U} + 8", f"{lo} >> 32"))
    o.call(st(f"{BUF_U} + 16", f"{hi} & {MASK}"))
    o.call(st(f"{BUF_U} + 24", f"{hi} >> 32"))

    def window(k):
        bits = o.calc(f"twoOverPiBits({power} + 512 - {k} * 32 - 31)")
        o.call(st(f"{BUF_T} + {k} * 8", bits))
        o.call(st(f"{BUF_P} + {k} * 8", nothing))

    o.for_(0, 17, window)
    o.call(st(f"{BUF_P} + 17 * 8", nothing))

    def row(i):
        carry = o.var("UInt64", "0", "c")
        o.set(carry, nothing)
        mi = o.calc(ld(f"{BUF_U} + {i} * 8"))

        def col(j):
            qj = o.calc(ld(f"{BUF_T} + {j} * 8"))
            at = f"{BUF_P} + ({i} + {j}) * 8"
            cur = o.calc(ld(at))
            t = o.calc(f"{mi} * {qj} + {cur} + {carry}")
            o.call(st(at, f"{t} & {MASK}"))
            o.set(carry, f"{t} >> 32")

        o.for_(0, f"17 - {i}", col)

    o.for_(0, 4, row)
    top = o.calc(ld(f"{BUF_P} + 16 * 8"))
    quadrant = o.var("Int64", "0", "q")
    o.set(quadrant, f"convert.uint64ToInt64({top} & 3)")
    high = o.calc(ld(f"{BUF_P} + 15 * 8"))
    negative = o.var("Int64", "0", "n")

    def flip():
        o.set(negative, "1")
        o.set(quadrant, f"({quadrant} + 1) & 3")
        carry = o.var("UInt64", "0", "c")
        o.set(carry, one_cell)

        def each(j):
            v = o.calc(ld(f"{BUF_P} + {j} * 8"))
            t = o.calc(f"({v} ^ {MASK}) + {carry}")
            o.call(st(f"{BUF_P} + {j} * 8", f"{t} & {MASK}"))
            o.set(carry, f"{t} >> 32")

        o.for_(0, 16, each)

    o.if_(f"({high} >> 31) == 1", flip)
    o.call(f"bfPack(ws, d, {BUF_P}, 16, {negative}, -512)")
    const(o, 64, PI)
    shift(o, 64, -1)
    mul(o, "d", "d", 64)
    o.ret(quadrant)

    # the nearest whole number of a register, and what is left
    o = new("bfNearest", "dI = the whole number nearest a register (halves up in magnitude), dF = x - dI; gives dI's parity (0 or 1)",
            [("dI", "Int64"), ("dF", "Int64"), ("x", "Int64")], "Int64")
    nothing = o.const("UInt64", "0", "nothing")
    even = o.const("Int64", "0", "even")
    k = o.calc("getHead(ws, x, 1)")

    def zero():
        zero_reg(o, "dI")
        zero_reg(o, "dF")
        o.ret(even)

    o.if_(f"{k} == 0", zero)
    sign = o.calc("getHead(ws, x, 0)")
    e2 = o.calc("getHead(ws, x, 2) + 320")

    def tiny():
        zero_reg(o, "dI")
        cp(o, "dF", "x")
        o.ret(even)

    o.if_(f"{e2} < 0", tiny)

    def whole():
        cp(o, "dI", "x")
        zero_reg(o, "dF")
        p0 = o.calc(f"0 - ({e2} - 320)")
        par = o.var("Int64", "0", "par")
        o.if_(f"{p0} == 0", lambda: o.set(par, "convert.uint64ToInt64(getLimb(ws, x, 0) & 1)"))
        o.ret(par)

    o.if_(f"{e2} >= 320", whole)
    p = o.calc(f"320 - {e2}")

    def part(j):
        v = o.calc(f"bitsAt(ws, x * 128 + 24, 10, {p} + {j} * 32)")
        o.call(st(f"{BUF_T} + {j} * 8", v))

    o.for_(0, 10, part)
    half = o.calc(f"bitsAt(ws, x * 128 + 24, 10, {p} - 1) & 1")
    one_cell = o.const("UInt64", "1", "oneCell")

    def round_up():
        carry = o.var("UInt64", "0", "c")
        o.set(carry, one_cell)

        def each(j):
            v = o.calc(ld(f"{BUF_T} + {j} * 8"))
            t = o.calc(f"{v} + {carry}")
            o.call(st(f"{BUF_T} + {j} * 8", f"{t} & {MASK}"))
            o.set(carry, f"{t} >> 32")

        o.for_(0, 10, each)

    o.if_(f"{half} == 1", round_up)
    o.call(f"bfPack(ws, dI, {BUF_T}, 10, {sign}, 0)")
    sub(o, "dF", "x", "dI")
    par = o.calc(f"convert.uint64ToInt64({ld(BUF_T)} & 1)")
    o.ret(par)

    o = new("bfSinPi", "d = sin(pi f) for a register with |f| up to 1/2", [("d", "Int64"), ("f", "Int64")])
    cp(o, 88, "f")
    sign = o.calc("getHead(ws, f, 0)")
    o.call("setHead(ws, 88, 0, 0)")
    setint(o, 89, 1, -2)
    c = o.calc("bfCompare(ws, 88, 89)")

    def direct():
        const(o, 90, PI)
        mul(o, 90, 90, 88)
        o.call("bfSinCos(ws, 91, 92, 90)")
        cp(o, "d", 91)

    def reflected():
        setint(o, 89, 1, -1)
        sub(o, 89, 89, 88)
        const(o, 90, PI)
        mul(o, 90, 90, 89)
        o.call("bfSinCos(ws, 91, 92, 90)")
        cp(o, "d", 92)

    o.if_(f"{c} <= 0", direct, reflected)
    k = o.calc("getHead(ws, d, 1)")
    o.if_(f"{k} != 0", lambda: o.call(f"setHead(ws, d, 0, {sign})"))
    o.ret()


def special_kernels():
    o = new("bfStirling", "d = ln gamma(z) for a register z of 64 or more: (z - 1/2) ln z - z + ln(2 pi)/2 + sum of B(2k) / (2k (2k - 1) z^(2k-1))",
            [("d", "Int64"), ("z", "Int64")])
    o.call("bfLog(ws, 72, z)")
    setint(o, 73, 1, -1)
    sub(o, 74, "z", 73)
    mul(o, 75, 74, 72)
    sub(o, 75, 75, "z")
    const(o, 76, HALF_LN_2PI)
    add(o, 75, 75, 76)
    recip(o, 77, "z")
    mul(o, 78, 77, 77)
    cp(o, 79, 77)

    def each(j):
        idx = o.calc(f"{j} + 16")
        o.call(f"bfConst(ws, 80, {idx})")
        mul(o, 81, 80, 79)
        odd = o.calc(f"({j} & 1) == 1")
        o.if_(odd, lambda: neg(o, 81))
        add(o, 75, 75, 81)
        mul(o, 79, 79, 78)
        small = o.calc("bfSmall(ws, 81, 75)")
        o.if_(small, o.exit_loop)

    o.for_(0, T.BERNOULLI_TERMS, each)
    cp(o, "d", 75)
    o.ret()

    o = new("bfGammaShift", "z moved up to 64 or more: dz = z + n and dp = z (z + 1) ... (z + n - 1); gives n (0 when z is 64 or more, and dp is then 1)",
            [("dz", "Int64"), ("dp", "Int64"), ("z", "Int64")], "Int64")
    nothing = o.const("Int64", "0", "nothing")
    setint(o, 82, 1)
    cp(o, "dz", "z")
    e2 = o.calc("getHead(ws, z, 2) + 320")
    setint(o, "dp", 1)

    def shifted():
        r = o.calc("bfRoundInt(ws, z)")
        n = o.calc(f"65 - {r}")
        cp(o, 83, "z")
        setint(o, 84, 1)

        def each(i):
            mul(o, "dp", "dp", 83)
            add(o, 83, 83, 84)

        o.for_(0, n, each)
        cp(o, "dz", 83)
        o.ret(n)

    o.if_(f"{e2} <= 6", shifted)
    o.ret(nothing)

    # erf by its series, 0 <= x < 10
    o = new("bfErfSeries", "d = erf x for a register from 0 to 10: 2/sqrt(pi) e^(-x^2) sum 2^n x^(2n+1) / (1 3 ... (2n+1)) (all terms positive)",
            [("d", "Int64"), ("x", "Int64")])
    mul(o, 89, "x", "x")
    cp(o, 90, 89)
    shift(o, 90, 1)
    cp(o, 91, "x")
    cp(o, 92, "x")

    def each(j):
        kk = o.calc(f"{j} * 2 + 3")
        mul(o, 91, 91, 90)
        divs(o, 91, 91, kk)
        add(o, 92, 92, 91)
        small = o.calc("bfSmall(ws, 91, 92)")
        o.if_(small, o.exit_loop)

    o.for_(0, 2000, each)
    cp(o, 93, 89)
    neg(o, 93)
    o.call("bfExp(ws, 94, 93)")
    mul(o, 92, 92, 94)
    const(o, 93, TWO_OVER_SQRT_PI)
    mul(o, "d", 92, 93)
    o.ret()

    o = new("bfErfcFraction", "d = erfc x for a register of 8 or more: e^(-x^2) / (sqrt(pi) (x + (1/2) / (x + 1 / (x + (3/2) / (x + ...)))))",
            [("d", "Int64"), ("x", "Int64")])
    cp(o, 88, "x")

    def each(j):
        kk = o.calc(f"200 - {j}")
        recip(o, 89, 88)
        muls(o, 89, 89, kk)
        shift(o, 89, -1)
        add(o, 88, "x", 89)

    o.for_(0, 200, each)
    mul(o, 90, "x", "x")
    neg(o, 90)
    o.call("bfExp(ws, 91, 90)")
    const(o, 92, INV_SQRT_PI)
    mul(o, 91, 91, 92)
    recip(o, 93, 88)
    mul(o, "d", 91, 93)
    o.ret()
