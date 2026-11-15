"""The 320-bit floating point of cmathlong and the kernels built on it: conversions, Newton's reciprocal and square
root, the constants, and exp, log, sin and cos, atan, gamma, erf (see cmathlonggen.py).

Registers (of 128 in a workspace): 0-15 a function's own, 16-23 and 72-111 the composite kernels', 24-31 log and its
atanh series, 32-39 exp, 40-47 expm1, 48-55 sin and cos, 56-63 atan, 64-71 the reduction of a trig argument, 120-127
Newton's iterations (a kernel may use the registers above its own number and the primitives, never a lower tier).
"""
from __future__ import annotations

from cmathlongbuild import ADDR, Op, ALL, new, ld, ldi, st, sti, LIM, HEAD, N, BUF_P, BUF_Q, BUF_T, BUF_U, MASK
import cmathlongtables as T


def mul(o, d, a, b):
    o.call(f"bfMul(ws, {d}, {a}, {b})")


def add(o, d, a, b):
    o.call(f"bfAdd(ws, {d}, {a}, {b}, 0)")


def sub(o, d, a, b):
    o.call(f"bfAdd(ws, {d}, {a}, {b}, 1)")


def cp(o, d, a):
    o.call(f"bfCopy(ws, {d}, {a})")


def divs(o, d, a, k):
    o.call(f"bfDivSmall(ws, {d}, {a}, {k})")


def muls(o, d, a, k):
    o.call(f"bfMulSmall(ws, {d}, {a}, {k})")


def setint(o, r, v, e=0):
    o.call(f"bfSetInt(ws, {r}, {v}, {e})")


def const(o, r, i):
    o.call(f"bfConst(ws, {r}, {i})")


def shift(o, r, k):
    o.call(f"bfShift(ws, {r}, {k})")


def neg(o, r):
    o.call(f"bfNegate(ws, {r})")


def recip(o, d, a):
    o.call(f"bfRecip(ws, {d}, {a})")


def div(o, d, a, b):
    o.call(f"bfDivide(ws, {d}, {a}, {b})")


def sqrt(o, d, a):
    o.call(f"bfSqrt(ws, {d}, {a})")


def zero_reg(o, d, sign=0):
    o.call(f"setHead(ws, {d}, 0, {sign})")
    o.call(f"setHead(ws, {d}, 1, 0)")


def hexpart():
    o = new("hexAt", "Digits of lower-case hexadecimal text read as a number", [("base", ADDR), ("start", "Int64"),
            ("digits", "Int64")], "UInt64", ws=False)
    value = o.var("UInt64", "0", "v")
    at = o.var("Int64", "0", "a")
    o.set(at, "start")
    stop = o.calc("start + digits")

    def each():
        place = o.calc(f"base + {at}")
        letter = o.calc(f"convert.byteToInt64(machine.loadByte({place}))")
        nibble = o.calc(f"({letter} & 15) + 9 * ({letter} >> 6)")
        o.set(value, f"({value} << 4) | convert.int64ToUInt64({nibble})")
        o.set(at, f"{at} + 1")

    o.while_(f"{at} < {stop}", each)
    o.ret(value)

    o = new("bfConst", "Load a constant of the table (ln 2, pi, ...; the Bernoulli coefficients from 16) into a register",
            [("d", "Int64"), ("index", "Int64")])
    text = o.const("String", '"' + T.constants_text() + '"', "constants")
    base = o.calc(f"machine.addressOfString({text})")
    at = o.calc("index * 96")
    e = o.calc(f"hexAt({base}, {at}, 16)")
    o.call(f"setHead(ws, d, 2, convert.uint64BitsToInt64({e}))")
    o.call("setHead(ws, d, 0, 0)")
    o.call("setHead(ws, d, 1, 1)")

    def each(j):
        v = o.calc(f"hexAt({base}, {at} + 16 + {j} * 8, 8)")
        o.call(f"setLimb(ws, d, {j}, {v})")

    o.for_(0, N, each)
    o.ret()

    o = new("twoOverPiBits", "32 bits of 2/pi's binary expansion from a place counted from 1 (0 outside the table)",
            [("first", "Int64")], "UInt64", ws=False)
    text = o.const("String", '"' + T.two_over_pi_text() + '"', "bits")
    base = o.calc(f"machine.addressOfString({text})")
    value = o.var("UInt64", "0", "v")
    nothing = o.const("UInt64", "0", "nothing")
    o.set(value, nothing)

    def each(b):
        i = o.calc(f"first + {b}")
        bit = o.var("UInt64", "0", "bit")
        o.set(bit, nothing)

        def inside():
            idx = o.calc(f"({i} - 1) >> 2")
            place = o.calc(f"{base} + {idx}")
            letter = o.calc(f"convert.byteToInt64(machine.loadByte({place}))")
            nibble = o.calc(f"({letter} & 15) + 9 * ({letter} >> 6)")
            b1 = o.calc(f"({nibble} >> (3 - (({i} - 1) & 3))) & 1")
            o.set(bit, f"convert.int64ToUInt64({b1})")

        o.if_(f"{i} >= 1 && {i} <= {T.TWO_OVER_PI_BITS}", inside)
        o.set(value, f"({value} << 1) | {bit}")

    o.for_(0, 32, each)
    o.ret(value)


def conversions():
    o = new("bfFromParts", "Load a register from a long double's parts (a zero or a finite value)",
            [("d", "Int64"), ("parts", ADDR)])
    kind = o.calc("clong.getPart(parts, 8)")
    sign = o.calc("clong.getPart(parts, 0)")

    def zero():
        o.call(f"setHead(ws, d, 0, {sign})")
        o.call("setHead(ws, d, 1, 0)")
        o.ret()

    o.if_(f"{kind} == 0", zero)
    hi = o.calc("clong.highOf(parts)")
    lo = o.calc("clong.lowOf(parts)")
    power = o.calc("clong.getPart(parts, 16)")
    o.call(st(f"{BUF_P}", f"{lo} & {MASK}"))
    o.call(st(f"{BUF_P} + 8", f"{lo} >> 32"))
    o.call(st(f"{BUF_P} + 16", f"{hi} & {MASK}"))
    o.call(st(f"{BUF_P} + 24", f"{hi} >> 32"))
    o.call(f"bfPack(ws, d, {BUF_P}, 4, {sign}, {power})")
    o.ret()

    o = new("bfToParts", "Round a register to the layout (0 double, 1 x87, 2 binary128) into parts: the top 128 bits and what is below them as the sticky part of the rounding",
            [("a", "Int64"), ("parts", ADDR), ("layout", "Int64")])
    kind = o.calc("getHead(ws, a, 1)")
    sign = o.calc("getHead(ws, a, 0)")

    def zero():
        o.call(f"clong.setPart(parts, 0, {sign})")
        o.call("clong.setPart(parts, 8, 0)")
        o.call("clong.setSignificand(parts, 0, 0)")
        o.ret()

    o.if_(f"{kind} == 0", zero)
    l = [o.calc(f"getLimb(ws, a, {j})") for j in range(10)]
    hi = o.calc(f"({l[9]} << 32) | {l[8]}")
    lo = o.calc(f"({l[7]} << 32) | {l[6]}")
    rest = o.calc(f"{l[5]} | {l[4]} | {l[3]} | {l[2]} | {l[1]} | {l[0]}")
    power = o.calc("getHead(ws, a, 2) + 192")
    o.call(f"clong.setPart(parts, 0, {sign})")
    o.call("clong.setPart(parts, 8, 1)")
    o.call(f"clong.setPart(parts, 16, {power})")
    o.call(f"clong.setSignificand(parts, {hi}, {lo})")
    dropped = o.calc(f"flag({rest} != 0, 1)")
    o.call(f"clong.settleAs(parts, {dropped}, layout)")
    o.ret()

    o = new("bfTopDouble", "The top 53 bits of a nonzero register as a double from 1 to 2", [("a", "Int64")], "Float64")
    l9 = o.calc("getLimb(ws, a, 9)")
    l8 = o.calc("getLimb(ws, a, 8)")
    top = o.calc(f"({l9} << 21) | ({l8} >> 11)")
    v = o.calc(f"convert.int64ToFloat64(convert.uint64ToInt64({top})) * 0x1p-52")
    o.ret(v)

    o = new("bfRoundInt", "A register rounded to the nearest whole number (halves away from zero), as an Int64 (below 2^61)",
            [("a", "Int64")], "Int64")
    nothing = o.const("Int64", "0", "nothing")
    big = o.const("Int64", "2305843009213693952", "most")
    kind = o.calc("getHead(ws, a, 1)")
    o.if_(f"{kind} == 0", lambda: o.ret(nothing))
    e2 = o.calc("getHead(ws, a, 2) + 320")
    o.if_(f"{e2} < 0", lambda: o.ret(nothing))
    o.if_(f"{e2} > 61", lambda: o.ret(big))
    p = o.calc(f"320 - {e2}")
    lo = o.calc(f"bitsAt(ws, a * 128 + 24, 10, {p})")
    hi = o.calc(f"bitsAt(ws, a * 128 + 24, 10, {p} + 32)")
    half = o.calc(f"bitsAt(ws, a * 128 + 24, 10, {p} - 1) & 1")
    n = o.calc(f"convert.uint64ToInt64(({hi} << 32) | {lo}) + convert.uint64ToInt64({half})")
    sign = o.calc("getHead(ws, a, 0)")
    res = o.var("Int64", "0", "res")
    o.if_(f"{sign} == 1", lambda: o.set(res, f"0 - {n}"), lambda: o.set(res, n))
    o.ret(res)


def newton():
    o = new("bfRecip", "d = 1 / a for a nonzero register (Newton's iteration from a double's reciprocal, three times)",
            [("d", "Int64"), ("a", "Int64")])
    sa = o.calc("getHead(ws, a, 0)")
    o.call("bfCopy(ws, 124, a)")
    o.call("setHead(ws, 124, 0, 0)")
    e2 = o.calc("getHead(ws, 124, 2) + 320")
    md = o.calc("bfTopDouble(ws, 124)")
    r0 = o.calc(f"1.0 / {md}")
    ri = o.calc(f"convert.float64ToInt64({r0} * 0x1p53)")
    o.call(f"bfSetInt(ws, 120, {ri}, -52 - {e2})")
    o.call("bfSetInt(ws, 122, 2, 0)")

    def step(_i):
        o.call("bfMul(ws, 121, 124, 120)")
        o.call("bfAdd(ws, 121, 122, 121, 1)")
        o.call("bfMul(ws, 120, 120, 121)")

    o.for_(0, 3, step)
    o.call("bfCopy(ws, d, 120)")
    o.call(f"setHead(ws, d, 0, {sa})")
    o.ret()

    o = new("bfDivide", "d = a / b for a nonzero register b", [("d", "Int64"), ("a", "Int64"), ("b", "Int64")])
    o.call("bfRecip(ws, 125, b)")
    o.call("bfMul(ws, d, a, 125)")
    o.ret()

    o = new("bfRsqrt", "d = 1 / sqrt(a) for a positive register (Newton's iteration from a double's, three times)",
            [("d", "Int64"), ("a", "Int64")])
    o.call("bfCopy(ws, 124, a)")
    o.call("setHead(ws, 124, 0, 0)")
    ef = o.var("Int64", "0", "ef")
    o.set(ef, "getHead(ws, 124, 2) + 319")
    md = o.var("Float64", "0.0", "md")
    o.set(md, "bfTopDouble(ws, 124)")
    o.if_(f"({ef} & 1) != 0", lambda: (o.set(md, f"{md} * 2.0"), o.set(ef, f"{ef} - 1")))
    rs = o.calc(f"1.0 / machine.squareRoot({md})")
    ri = o.calc(f"convert.float64ToInt64({rs} * 0x1p53)")
    o.call(f"bfSetInt(ws, 120, {ri}, -53 - {ef} / 2)")
    o.call("bfSetInt(ws, 123, 3, 0)")

    def step(_i):
        o.call("bfMul(ws, 121, 120, 120)")
        o.call("bfMul(ws, 121, 121, 124)")
        o.call("bfAdd(ws, 121, 123, 121, 1)")
        o.call("bfMul(ws, 120, 120, 121)")
        o.call("bfShift(ws, 120, -1)")

    o.for_(0, 3, step)
    o.call("bfCopy(ws, d, 120)")
    o.ret()

    o = new("bfSqrt", "d = sqrt(a) for a nonnegative register", [("d", "Int64"), ("a", "Int64")])
    k = o.calc("getHead(ws, a, 1)")

    def zero():
        o.call("setHead(ws, d, 0, 0)")
        o.call("setHead(ws, d, 1, 0)")
        o.ret()

    o.if_(f"{k} == 0", zero)
    o.call("bfRsqrt(ws, 126, a)")
    o.call("bfMul(ws, d, 126, a)")
    o.ret()
