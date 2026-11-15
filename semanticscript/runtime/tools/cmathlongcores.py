"""The functions of cmathlong: for each, a core on a long double's parts (any layout, so the tests reach all three formats
from any machine) and the `abi library` operation that wraps it (see cmathlonggen.py)."""
from __future__ import annotations

from cmathlongbuild import ADDR, Op, ALL, new, ld, ldi, st, sti, LIM, HEAD, N, BUF_P, BUF_Q, BUF_T, BUF_U, WS_BYTES, MASK
from cmathlongkernels import (mul, add, sub, cp, divs, muls, setint, const, shift, neg, recip, div, sqrt, zero_reg)
import cmathlongtables as T

LN2, INV_LN2, INV_LN10, PI, TWO_OVER_SQRT_PI, INV_SQRT_PI, HALF_LN_2PI = range(7)

LD = "machine.LongDouble"
NAN, INF, ZERO, FINITE = 3, 2, 0, 1
CORES = []            # (name, kind, abi name, doc) of every function for the tests and the table


def helpers():
    o = new("flag", "1 when a condition holds, else 0", [("condition", "Bool"), ("value", "Int64")], "Int64", ws=False,
            effects=False)
    nothing = o.const("Int64", "0", "nothing")
    o.if_("condition", lambda: o.ret("value"))
    o.ret(nothing)

    o = new("bitSet", "Whether bit n (counted from 0) of high * 2^64 + low is set", [("high", "UInt64"), ("low", "UInt64"),
            ("n", "Int64")], "Bool", ws=False, effects=False)
    yes = o.const("Bool", "true", "yes")
    no = o.const("Bool", "false", "no")
    o.if_("n < 0 || n >= 128", lambda: o.ret(no))
    v = o.var("UInt64", "0", "v")
    o.if_("n >= 64", lambda: o.set(v, "(high >> (n - 64)) & 1"), lambda: o.set(v, "(low >> n) & 1"))
    r = o.calc(f"{v} == 1")
    o.ret(r)

    o = new("bfNew", "A zeroed workspace for one function's registers and buffers", [], "machine.Address", ws=False)
    w = o.calc(f"heap.take({WS_BYTES})")
    o.ret(w)

    o = new("partsOfLong", "A long double's parts, in a new block", [("value", LD)], "machine.Address", ws=False)
    cell = o.calc("heap.take(16)")
    o.call(f"machine.storeLongDouble({cell}, value)")
    parts = o.calc("clong.partsNew()")
    o.call(f"clong.unpack({cell}, {parts})")
    o.call(f"heap.give({cell})")
    o.ret(parts)

    o = new("longOfParts", "The long double parts stand for, the parts' block given back", [("parts", ADDR)], LD, ws=False)
    cell = o.calc("heap.take(16)")
    o.call(f"clong.pack(parts, {cell})")
    v = o.calc(f"machine.loadLongDouble({cell})")
    o.call(f"heap.give({cell})")
    o.call("heap.give(parts)")
    o.ret(v)

    o = new("setSpecial", "Make parts a zero (0), a finite placeholder (1), an infinity (2), or a NaN (3) of a sign",
            [("parts", ADDR), ("kind", "Int64"), ("sign", "Int64")], ws=False)
    o.call("clong.setPart(parts, 0, sign)")
    o.call("clong.setPart(parts, 8, kind)")
    o.call("clong.setSignificand(parts, 0, 0)")
    o.ret()

    o = new("setSmallValue", "Make parts a small whole number times a power of two, settled to the layout",
            [("parts", ADDR), ("sign", "Int64"), ("value", "UInt64"), ("power", "Int64"), ("layout", "Int64")], ws=False)
    o.call("clong.setPart(parts, 0, sign)")
    o.call("clong.setPart(parts, 8, 1)")
    o.call("clong.setPart(parts, 16, power)")
    o.call("clong.setSignificand(parts, 0, value)")
    o.call("clong.settleAs(parts, 0, layout)")
    o.ret()

    o = new("invalidNaN", "A NaN for an invalid argument: EDOM, and the default NaN of the platform (sign set on x86_64)",
            [("parts", ADDR)], ws=False)
    o.call("clibrary.setErrno(33)")
    arm = o.calc("system.aarch64()")
    s = o.calc(f"1 - flag({arm}, 1)")
    o.call(f"setSpecial(parts, 3, {s})")
    o.ret()

    o = new("noteRange", "ERANGE when a result is an infinity or a zero from finite arguments", [("parts", ADDR)], ws=False)
    k = o.calc("clong.getPart(parts, 8)")
    o.if_(f"{k} == 2 || {k} == 0", lambda: o.call("clibrary.setErrno(34)"))
    o.ret()

    o = new("bfFinish", "Round a register into parts for the layout", [("r", "Int64"), ("parts", ADDR), ("layout", "Int64")])
    o.call("bfToParts(ws, r, parts, layout)")
    o.ret()

    o = new("magnitudeOf", "The power of two a finite nonzero value is below and not below half of (E plus its bits)",
            [("parts", ADDR)], "Int64", ws=False)
    hi = o.calc("clong.highOf(parts)")
    lo = o.calc("clong.lowOf(parts)")
    e = o.calc("clong.getPart(parts, 16)")
    n = o.calc(f"clong.bitLength({hi}, {lo})")
    r = o.calc(f"{e} + {n}")
    o.ret(r)

    o = new("isPowerOfTwo", "Whether a finite nonzero value is a power of two", [("parts", ADDR)], "Bool", ws=False)
    hi = o.calc("clong.highOf(parts)")
    lo = o.calc("clong.lowOf(parts)")
    n = o.calc(f"clong.bitLength({hi}, {lo})")
    low = o.calc(f"clong.lowBitsSet({hi}, {lo}, {n} - 1)")
    r = o.calc(f"!{low}")
    o.ret(r)

    o = new("integerKind", "For a finite nonzero value: 0 when it is not a whole number, 1 when it is an odd one, 2 when an even one",
            [("parts", ADDR)], "Int64", ws=False)
    odd = o.const("Int64", "1", "odd")
    even = o.const("Int64", "2", "even")
    notWhole = o.const("Int64", "0", "notWhole")
    hi = o.calc("clong.highOf(parts)")
    lo = o.calc("clong.lowOf(parts)")
    e = o.calc("clong.getPart(parts, 16)")

    def nonneg():
        o.if_(f"{e} == 0 && ({lo} & 1) == 1", lambda: o.ret(odd))
        o.ret(even)

    o.if_(f"{e} >= 0", nonneg)
    p = o.calc(f"0 - {e}")
    o.if_(f"{p} >= 128", lambda: o.ret(notWhole))
    low = o.calc(f"clong.lowBitsSet({hi}, {lo}, {p})")
    o.if_(low, lambda: o.ret(notWhole))
    o.if_(f"bitSet({hi}, {lo}, {p})", lambda: o.ret(odd))
    o.ret(even)


# ---------------------------------------------------------------- core scaffolding

def core(name, doc, body, extra=None, output=None):
    ins = [("parts", ADDR)] + (extra or []) + [("layout", "Int64")]
    o = new(name, doc, ins, output, ws=False)
    body(o)
    return o


def prelude(o, parts="parts"):
    return (o.calc(f"clong.getPart({parts}, 8)", "kind"), o.calc(f"clong.getPart({parts}, 0)", "sign"))


def begin(o):
    name = o.fresh("ws")
    o.emit(f"calc {name} = bfNew()")
    o.wsname = name


def finish(o, r, range_check=False):
    o.call(f"bfFinish(ws, {r}, parts, layout)")
    o.call("heap.give(ws)")
    if range_check:
        o.call("noteRange(parts)")
    o.ret()


def leave(o):
    """give the workspace back and return"""
    o.call("heap.give(ws)")
    o.ret()


def set_sign(o, r, sign):
    o.call(f"bfFixSign(ws, {r}, {sign})")


def one_result(o, sign="0"):
    o.call(f"setSmallValue(parts, {sign}, 1, 0, layout)")


def inf_result(o, sign, errno=True):
    o.call(f"setSpecial(parts, 2, {sign})")
    if errno:
        o.call("clibrary.setErrno(34)")


def zero_result(o, sign, errno=True):
    o.call(f"setSpecial(parts, 0, {sign})")
    if errno:
        o.call("clibrary.setErrno(34)")


def load_x(o, reg=0):
    o.call(f"bfFromParts(ws, {reg}, parts)")


def abs_reg(o, reg):
    o.call(f"setHead(ws, {reg}, 0, 0)")


# ---------------------------------------------------------------- exp family

def exp_core(mode):
    names = {"exp": ("expCore", "e^x"), "exp2": ("exp2Core", "2^x"), "expm1": ("expm1Core", "e^x - 1")}
    name, what = names[mode]

    def body(o):
        kind, sign = prelude(o)
        o.if_(f"{kind} == 3", o.ret)

        def infinite():
            def negative():
                if mode == "expm1":
                    o.call("setSmallValue(parts, 1, 1, 0, layout)")
                else:
                    o.call("setSpecial(parts, 0, 0)")

            o.if_(f"{sign} == 1", negative)
            o.ret()

        o.if_(f"{kind} == 2", infinite)

        def zero():
            if mode != "expm1":
                one_result(o)
            o.ret()

        o.if_(f"{kind} == 0", zero)
        mag = o.calc("magnitudeOf(parts)")

        def big():
            def over():
                inf_result(o, 0)

            def under():
                if mode == "expm1":
                    o.call("setSmallValue(parts, 1, 1, 0, layout)")
                else:
                    zero_result(o, 0)

            o.if_(f"{sign} == 0", over, under)
            o.ret()

        o.if_(f"{mag} > 15", big)
        begin(o)
        load_x(o, 0)
        if mode == "exp":
            o.call("bfExp(ws, 1, 0)")
        elif mode == "exp2":
            const(o, 2, LN2)
            mul(o, 3, 0, 2)
            o.call("bfExp(ws, 1, 3)")
        else:
            o.call("bfExpm1(ws, 1, 0)")
        finish(o, 1, True)

    core(name, f"{what} on parts: the correctly rounded value but for the rarest cases", body)
    return name


def log_core(mode):
    names = {0: ("logCore", "ln x"), 1: ("log2Core", "log2 x"), 2: ("log10Core", "log10 x"), 3: ("log1pCore", "ln (1 + x)")}
    name, what = names[mode]

    def body(o):
        kind, sign = prelude(o)
        o.if_(f"{kind} == 3", o.ret)

        def infinite():
            o.if_(f"{sign} == 1", lambda: (o.call("invalidNaN(parts)"), o.ret()))
            o.ret()

        o.if_(f"{kind} == 2", infinite)

        def zero():
            if mode != 3:
                inf_result(o, 1)
            o.ret()

        o.if_(f"{kind} == 0", zero)
        begin(o)
        load_x(o, 0)
        if mode == 3:
            def below():
                setint(o, 1, 1)
                add(o, 2, 1, 0)
                k = o.calc("getHead(ws, 2, 1)")
                s = o.calc("getHead(ws, 2, 0)")

                def pole():
                    o.call("heap.give(ws)")
                    inf_result(o, 1)
                    o.ret()

                o.if_(f"{k} == 0", pole)

                def domain():
                    o.call("heap.give(ws)")
                    o.call("invalidNaN(parts)")
                    o.ret()

                o.if_(f"{s} == 1", domain)

            o.if_(f"{sign} == 1", below)
            o.call("bfLog1p(ws, 1, 0)")
        else:
            def domain():
                o.call("heap.give(ws)")
                o.call("invalidNaN(parts)")
                o.ret()

            o.if_(f"{sign} == 1", domain)
            o.call("bfLog(ws, 1, 0)")
            if mode == 1:
                const(o, 2, INV_LN2)
                mul(o, 1, 1, 2)
            elif mode == 2:
                const(o, 2, INV_LN10)
                mul(o, 1, 1, 2)
        finish(o, 1)

    core(name, f"{what} on parts", body)
    return name


def pow_core():
    def body(o):
        kx, sx = prelude(o)
        ky = o.calc("clong.getPart(py, 8)", "ky")
        sy = o.calc("clong.getPart(py, 0)", "sy")
        # y = +-0 gives 1, whatever x is
        o.if_(f"{ky} == 0", lambda: (one_result(o), o.ret()))
        # +1 to any power is 1
        def maybe_one():
            m = o.calc("magnitudeOf(parts)")
            p2 = o.calc("isPowerOfTwo(parts)")
            o.if_(f"{m} == 1 && {p2}", lambda: (one_result(o), o.ret()))

        o.if_(f"{kx} == 1 && {sx} == 0", maybe_one)
        o.if_(f"{kx} == 3 || {ky} == 3", lambda: (o.call("setSpecial(parts, 3, 0)"), o.ret()))
        # |x| compared with 1 (finite or infinite x): -1 below, 0 equal, 1 above
        cmp1 = o.var("Int64", "0", "cmp")
        def set_cmp():
            def finite():
                m = o.calc("magnitudeOf(parts)")
                p2 = o.calc("isPowerOfTwo(parts)")
                o.if_(f"{m} <= 0", lambda: o.set(cmp1, "0 - 1"),
                      lambda: o.if_(f"{m} == 1 && {p2}", lambda: o.set(cmp1, "0"), lambda: o.set(cmp1, "1")))

            o.if_(f"{kx} == 2", lambda: o.set(cmp1, "1"),
                  lambda: o.if_(f"{kx} == 0", lambda: o.set(cmp1, "0 - 1"), finite))

        set_cmp()

        def y_infinite():
            o.if_(f"{cmp1} == 0", lambda: (one_result(o), o.ret()))
            above = o.calc(f"{cmp1} > 0")
            plus = o.calc(f"flag({sy} == 0, 1) == flag({above}, 1)")      # the result is +infinity: y > 0 with |x| > 1, or y < 0 with |x| < 1
            o.if_(plus, lambda: o.call("setSpecial(parts, 2, 0)"), lambda: o.call("setSpecial(parts, 0, 0)"))
            o.ret()

        o.if_(f"{ky} == 2", y_infinite)
        iy = o.calc("integerKind(py)", "iy")
        odd = o.calc(f"{iy} == 1", "odd")

        def x_infinite():
            def positive():
                o.if_(f"{sy} == 0", lambda: o.call("setSpecial(parts, 2, 0)"), lambda: o.call("setSpecial(parts, 0, 0)"))
                o.ret()

            o.if_(f"{sx} == 0", positive)
            sg = o.calc(f"flag({odd}, 1)")
            o.if_(f"{sy} == 0", lambda: o.call(f"setSpecial(parts, 2, {sg})"), lambda: o.call(f"setSpecial(parts, 0, {sg})"))
            o.ret()

        o.if_(f"{kx} == 2", x_infinite)

        def x_zero():
            sg = o.calc(f"flag({odd} && {sx} == 1, 1)")
            def pole():
                o.call(f"setSpecial(parts, 2, {sg})")
                o.call("clibrary.setErrno(34)")

            o.if_(f"{sy} == 1", pole, lambda: o.call(f"setSpecial(parts, 0, {sg})"))
            o.ret()

        o.if_(f"{kx} == 0", x_zero)
        # finite nonzero x and y
        res_neg = o.calc(f"flag({sx} == 1 && {odd}, 1)")
        o.if_(f"{sx} == 1 && {iy} == 0", lambda: (o.call("invalidNaN(parts)"), o.ret()))
        begin(o)
        load_x(o, 0)
        o.call("bfFromParts(ws, 1, py)")
        abs_reg(o, 0)
        o.call("bfLog(ws, 2, 0)")
        mul(o, 3, 1, 2)
        k3 = o.calc("getHead(ws, 3, 1)")
        o.if_(f"{k3} == 0", lambda: (setint(o, 4, 1)))
        def exponentiate():
            e2 = o.calc("bfLog2Of(ws, 3)")
            s3 = o.calc("getHead(ws, 3, 0)")

            def out_of_range():
                o.call("heap.give(ws)")
                o.if_(f"{s3} == 0", lambda: inf_result(o, res_neg), lambda: zero_result(o, res_neg))
                o.ret()

            o.if_(f"{e2} > 15", out_of_range)
            o.call("bfExp(ws, 4, 3)")

        o.if_(f"{k3} != 0", exponentiate)
        o.call(f"setHead(ws, 4, 0, {res_neg})")
        finish(o, 4, True)

    core("powCore", "x^y on parts with C99's special cases", body, extra=[("py", ADDR)])
    return "powCore"


def cbrt_core():
    def body(o):
        kind, sign = prelude(o)
        o.if_(f"{kind} != 1", o.ret)
        begin(o)
        load_x(o, 0)
        abs_reg(o, 0)
        o.call("bfLog(ws, 1, 0)")
        divs(o, 1, 1, 3)
        o.call("bfExp(ws, 2, 1)")
        o.call(f"setHead(ws, 2, 0, {sign})")
        finish(o, 2)

    core("cbrtCore", "The cube root on parts", body)


def hypot_core():
    def body(o):
        kx, sx = prelude(o)
        ky = o.calc("clong.getPart(py, 8)", "ky")
        o.if_(f"{kx} == 2 || {ky} == 2", lambda: (o.call("setSpecial(parts, 2, 0)"), o.ret()))
        o.if_(f"{kx} == 3 || {ky} == 3", lambda: (o.call("setSpecial(parts, 3, 0)"), o.ret()))
        o.if_(f"{kx} == 0 && {ky} == 0", lambda: (o.call("setSpecial(parts, 0, 0)"), o.ret()))
        begin(o)
        load_x(o, 0)
        o.call("bfFromParts(ws, 1, py)")
        mul(o, 2, 0, 0)
        mul(o, 3, 1, 1)
        add(o, 4, 2, 3)
        sqrt(o, 5, 4)
        finish(o, 5, True)

    core("hypotCore", "sqrt(x^2 + y^2) on parts", body, extra=[("py", ADDR)])


# ---------------------------------------------------------------- trigonometric

def trig_core(which):
    name = {"sin": "sinCore", "cos": "cosCore", "tan": "tanCore"}[which]

    def body(o):
        kind, sign = prelude(o)
        o.if_(f"{kind} == 3", o.ret)
        o.if_(f"{kind} == 2", lambda: (o.call("invalidNaN(parts)"), o.ret()))

        def zero():
            if which == "cos":
                one_result(o)
            o.ret()

        o.if_(f"{kind} == 0", zero)
        mag = o.calc("magnitudeOf(parts)")

        def tiny():
            if which == "cos":
                one_result(o)
            o.ret()

        o.if_(f"{mag} < -70", tiny)
        begin(o)
        q = o.calc("bfTrigReduce(ws, 0, parts)", "q")
        o.call("bfSinCos(ws, 1, 2, 0)")
        # the sine and cosine of x for the quadrant q: pick, with sign
        if which == "sin":
            reg = o.var("Int64", "0", "reg")
            flip = o.var("Int64", "0", "flip")
            o.if_(f"{q} == 0", lambda: (o.set(reg, "1"), o.set(flip, "0")),
                  lambda: o.if_(f"{q} == 1", lambda: (o.set(reg, "2"), o.set(flip, "0")),
                                lambda: o.if_(f"{q} == 2", lambda: (o.set(reg, "1"), o.set(flip, "1")),
                                              lambda: (o.set(reg, "2"), o.set(flip, "1")))))
            cp(o, 3, reg)
            o.if_(f"{flip} == 1", lambda: neg(o, 3))
        elif which == "cos":
            reg = o.var("Int64", "0", "reg")
            flip = o.var("Int64", "0", "flip")
            o.if_(f"{q} == 0", lambda: (o.set(reg, "2"), o.set(flip, "0")),
                  lambda: o.if_(f"{q} == 1", lambda: (o.set(reg, "1"), o.set(flip, "1")),
                                lambda: o.if_(f"{q} == 2", lambda: (o.set(reg, "2"), o.set(flip, "1")),
                                              lambda: (o.set(reg, "1"), o.set(flip, "0")))))
            cp(o, 3, reg)
            o.if_(f"{flip} == 1", lambda: neg(o, 3))
        else:
            even = o.calc(f"({q} & 1) == 0")
            o.if_(even, lambda: div(o, 3, 1, 2), lambda: (div(o, 3, 2, 1), neg(o, 3)))
        if which != "cos":
            o.if_(f"{sign} == 1", lambda: neg(o, 3))
        finish(o, 3)

    core(name, f"{which} on parts: Payne and Hanek's reduction and Taylor series", body)


def atan_helpers():
    o = new("bfAtanRatio", "d = atan(y / x) for nonnegative registers y and x, not both zero", [("d", "Int64"), ("y", "Int64"), ("x", "Int64")])
    ky = o.calc("getHead(ws, y, 1)")
    kx = o.calc("getHead(ws, x, 1)")

    def yzero():
        zero_reg(o, "d")
        o.ret()

    o.if_(f"{ky} == 0", yzero)

    def xzero():
        const(o, 96, PI)
        shift(o, 96, -1)
        cp(o, "d", 96)
        o.ret()

    o.if_(f"{kx} == 0", xzero)
    div(o, 96, "y", "x")
    o.call("bfAtan(ws, d, 96)")
    o.ret()

    o = new("bfFixSign", "Set a register's sign (a zero keeps none)", [("r", "Int64"), ("sign", "Int64")])
    k = o.calc("getHead(ws, r, 1)")
    o.if_(f"{k} != 0", lambda: o.call("setHead(ws, r, 0, sign)"))
    o.ret()


def atan_core():
    def body(o):
        kind, sign = prelude(o)
        o.if_(f"{kind} == 3 || {kind} == 0", o.ret)

        def infinite():
            begin(o)
            const(o, 1, PI)
            shift(o, 1, -1)
            set_sign(o, 1, sign)
            finish(o, 1)

        o.if_(f"{kind} == 2", infinite)
        begin(o)
        load_x(o, 0)
        abs_reg(o, 0)
        o.call("bfAtan(ws, 1, 0)")
        set_sign(o, 1, sign)
        finish(o, 1)

    core("atanCore", "atan on parts", body)


def unit_compare(o, parts="parts"):
    """For a finite nonzero value: -1 when |x| < 1, 0 when it is 1, 1 when above"""
    cmp1 = o.var("Int64", "0", "cmp")
    m = o.calc(f"magnitudeOf({parts})")
    p2 = o.calc(f"isPowerOfTwo({parts})")
    o.if_(f"{m} <= 0", lambda: o.set(cmp1, "0 - 1"),
          lambda: o.if_(f"{m} == 1 && {p2}", lambda: o.set(cmp1, "0"), lambda: o.set(cmp1, "1")))
    return cmp1


def asin_acos_cores():
    def asin_body(o):
        kind, sign = prelude(o)
        o.if_(f"{kind} == 3 || {kind} == 0", o.ret)
        o.if_(f"{kind} == 2", lambda: (o.call("invalidNaN(parts)"), o.ret()))
        c = unit_compare(o)
        o.if_(f"{c} > 0", lambda: (o.call("invalidNaN(parts)"), o.ret()))

        def edge():
            begin(o)
            const(o, 1, PI)
            shift(o, 1, -1)
            set_sign(o, 1, sign)
            finish(o, 1)

        o.if_(f"{c} == 0", edge)
        begin(o)
        load_x(o, 0)
        abs_reg(o, 0)
        setint(o, 1, 1)
        sub(o, 2, 1, 0)
        add(o, 3, 1, 0)
        mul(o, 2, 2, 3)
        sqrt(o, 2, 2)
        o.call("bfAtanRatio(ws, 4, 0, 2)")
        set_sign(o, 4, sign)
        finish(o, 4)

    core("asinCore", "asin on parts", asin_body)

    def acos_body(o):
        kind, sign = prelude(o)
        o.if_(f"{kind} == 3", o.ret)
        o.if_(f"{kind} == 2", lambda: (o.call("invalidNaN(parts)"), o.ret()))

        def zero():
            begin(o)
            const(o, 1, PI)
            shift(o, 1, -1)
            finish(o, 1)

        o.if_(f"{kind} == 0", zero)
        c = unit_compare(o)
        o.if_(f"{c} > 0", lambda: (o.call("invalidNaN(parts)"), o.ret()))

        def edge():
            def minus():
                begin(o)
                const(o, 1, PI)
                finish(o, 1)

            o.if_(f"{sign} == 1", minus, lambda: (o.call("setSpecial(parts, 0, 0)"), o.ret()))

        o.if_(f"{c} == 0", edge)
        begin(o)
        load_x(o, 0)
        abs_reg(o, 0)
        setint(o, 1, 1)
        sub(o, 2, 1, 0)
        add(o, 3, 1, 0)
        mul(o, 2, 2, 3)
        sqrt(o, 2, 2)
        o.call("bfAtanRatio(ws, 4, 2, 0)")

        def back():
            const(o, 5, PI)
            sub(o, 4, 5, 4)

        o.if_(f"{sign} == 1", back)
        finish(o, 4)

    core("acosCore", "acos on parts", acos_body)


def atan2_core():
    def body(o):
        ky, sy = prelude(o)                       # parts hold y
        kx = o.calc("clong.getPart(px, 8)", "kx")
        sx = o.calc("clong.getPart(px, 0)", "sx")
        o.if_(f"{ky} == 3 || {kx} == 3", lambda: (o.call("setSpecial(parts, 3, 0)"), o.ret()))

        def constant_result(num, den_shift, sign):
            """pi * num / 4 with the sign of y: num 1 (pi/4), 2 (pi/2), 3 (3pi/4), 4 (pi)"""
            begin(o)
            const(o, 1, PI)
            if num != 4:
                muls(o, 1, 1, num)
                shift(o, 1, -2)
            set_sign(o, 1, sy)
            finish(o, 1)

        def yzero():
            def positive():
                o.call(f"setSpecial(parts, 0, {sy})")
                o.ret()

            o.if_(f"{sx} == 0", positive)
            constant_result(4, 0, sy)

        o.if_(f"{ky} == 0", yzero)
        o.if_(f"{kx} == 0", lambda: constant_result(2, 0, sy))

        def yinf():
            def xinf():
                o.if_(f"{sx} == 0", lambda: constant_result(1, 0, sy), lambda: constant_result(3, 0, sy))

            o.if_(f"{kx} == 2", xinf)
            constant_result(2, 0, sy)

        o.if_(f"{ky} == 2", yinf)

        def xinf():
            o.if_(f"{sx} == 0", lambda: (o.call(f"setSpecial(parts, 0, {sy})"), o.ret()),
                  lambda: constant_result(4, 0, sy))

        o.if_(f"{kx} == 2", xinf)
        begin(o)
        load_x(o, 0)
        o.call("bfFromParts(ws, 1, px)")
        abs_reg(o, 0)
        abs_reg(o, 1)
        o.call("bfAtanRatio(ws, 2, 0, 1)")

        def left():
            const(o, 3, PI)
            sub(o, 2, 3, 2)

        o.if_(f"{sx} == 1", left)
        set_sign(o, 2, sy)
        finish(o, 2)

    core("atan2Core", "atan2 (y in the parts, x given) on parts, with Annex F's special values", body, extra=[("px", ADDR)])


# ---------------------------------------------------------------- hyperbolic

def hyperbolic_cores():
    def sinh_body(o):
        kind, sign = prelude(o)
        o.if_(f"{kind} != 1", o.ret)
        mag = o.calc("magnitudeOf(parts)")
        o.if_(f"{mag} > 14", lambda: (inf_result(o, sign), o.ret()))
        begin(o)
        load_x(o, 0)
        abs_reg(o, 0)
        e2 = o.calc("bfLog2Of(ws, 0)")

        def small():
            o.call("bfExpm1Small(ws, 1, 0)")
            setint(o, 2, 2)
            add(o, 3, 1, 2)
            mul(o, 4, 1, 3)
            setint(o, 5, 1)
            add(o, 5, 1, 5)
            shift(o, 5, 1)
            div(o, 6, 4, 5)

        def large():
            o.call("bfExp(ws, 1, 0)")
            recip(o, 2, 1)
            sub(o, 3, 1, 2)
            shift(o, 3, -1)
            cp(o, 6, 3)

        o.if_(f"{e2} <= 0", small, large)
        set_sign(o, 6, sign)
        finish(o, 6, True)

    core("sinhCore", "sinh on parts", sinh_body)

    def cosh_body(o):
        kind, sign = prelude(o)
        o.if_(f"{kind} == 3", o.ret)
        o.if_(f"{kind} == 2", lambda: (o.call("setSpecial(parts, 2, 0)"), o.ret()))
        o.if_(f"{kind} == 0", lambda: (one_result(o), o.ret()))
        mag = o.calc("magnitudeOf(parts)")
        o.if_(f"{mag} > 14", lambda: (inf_result(o, 0), o.ret()))
        begin(o)
        load_x(o, 0)
        o.call("bfExp(ws, 1, 0)")
        recip(o, 2, 1)
        add(o, 3, 1, 2)
        shift(o, 3, -1)
        finish(o, 3, True)

    core("coshCore", "cosh on parts", cosh_body)

    def tanh_body(o):
        kind, sign = prelude(o)
        o.if_(f"{kind} == 3 || {kind} == 0", o.ret)
        o.if_(f"{kind} == 2", lambda: (o.call(f"setSmallValue(parts, {sign}, 1, 0, layout)"), o.ret()))
        mag = o.calc("magnitudeOf(parts)")
        o.if_(f"{mag} > 7", lambda: (o.call(f"setSmallValue(parts, {sign}, 1, 0, layout)"), o.ret()))
        begin(o)
        load_x(o, 0)
        abs_reg(o, 0)
        cp(o, 1, 0)
        shift(o, 1, 1)
        o.call("bfExpm1(ws, 2, 1)")
        setint(o, 3, 2)
        add(o, 3, 2, 3)
        div(o, 4, 2, 3)
        set_sign(o, 4, sign)
        finish(o, 4)

    core("tanhCore", "tanh on parts", tanh_body)

    def asinh_body(o):
        kind, sign = prelude(o)
        o.if_(f"{kind} == 3 || {kind} == 0 || {kind} == 2", o.ret)
        begin(o)
        load_x(o, 0)
        abs_reg(o, 0)
        mul(o, 1, 0, 0)
        setint(o, 2, 1)
        add(o, 3, 1, 2)
        sqrt(o, 3, 3)
        add(o, 3, 3, 2)
        div(o, 4, 1, 3)
        add(o, 4, 4, 0)
        o.call("bfLog1p(ws, 5, 4)")
        set_sign(o, 5, sign)
        finish(o, 5)

    core("asinhCore", "asinh on parts", asinh_body)

    def acosh_body(o):
        kind, sign = prelude(o)
        o.if_(f"{kind} == 3", o.ret)
        o.if_(f"{kind} == 2", lambda: o.if_(f"{sign} == 1", lambda: (o.call("invalidNaN(parts)"), o.ret()), o.ret))
        o.if_(f"{kind} == 0 || {sign} == 1", lambda: (o.call("invalidNaN(parts)"), o.ret()))
        c = unit_compare(o)
        o.if_(f"{c} < 0", lambda: (o.call("invalidNaN(parts)"), o.ret()))
        o.if_(f"{c} == 0", lambda: (o.call("setSpecial(parts, 0, 0)"), o.ret()))
        begin(o)
        load_x(o, 0)
        setint(o, 1, 1)
        sub(o, 2, 0, 1)
        setint(o, 3, 2)
        add(o, 3, 3, 2)
        mul(o, 3, 3, 2)
        sqrt(o, 3, 3)
        add(o, 3, 3, 2)
        o.call("bfLog1p(ws, 4, 3)")
        finish(o, 4)

    core("acoshCore", "acosh on parts", acosh_body)

    def atanh_body(o):
        kind, sign = prelude(o)
        o.if_(f"{kind} == 3 || {kind} == 0", o.ret)
        o.if_(f"{kind} == 2", lambda: (o.call("invalidNaN(parts)"), o.ret()))
        c = unit_compare(o)
        o.if_(f"{c} > 0", lambda: (o.call("invalidNaN(parts)"), o.ret()))
        o.if_(f"{c} == 0", lambda: (inf_result(o, sign), o.ret()))
        begin(o)
        load_x(o, 0)
        abs_reg(o, 0)
        setint(o, 1, 1)
        sub(o, 2, 1, 0)
        cp(o, 3, 0)
        shift(o, 3, 1)
        div(o, 4, 3, 2)
        o.call("bfLog1p(ws, 5, 4)")
        shift(o, 5, -1)
        set_sign(o, 5, sign)
        finish(o, 5)

    core("atanhCore", "atanh on parts", atanh_body)


# ---------------------------------------------------------------- error function and gamma

def erf_cores():
    def erf_body(o):
        kind, sign = prelude(o)
        o.if_(f"{kind} == 3 || {kind} == 0", o.ret)
        o.if_(f"{kind} == 2", lambda: (o.call(f"setSmallValue(parts, {sign}, 1, 0, layout)"), o.ret()))
        mag = o.calc("magnitudeOf(parts)")
        o.if_(f"{mag} > 4", lambda: (o.call(f"setSmallValue(parts, {sign}, 1, 0, layout)"), o.ret()))
        begin(o)
        load_x(o, 0)
        abs_reg(o, 0)
        o.call("bfErfSeries(ws, 1, 0)")
        set_sign(o, 1, sign)
        finish(o, 1)

    core("erfCore", "erf on parts", erf_body)

    def erfc_body(o):
        kind, sign = prelude(o)
        o.if_(f"{kind} == 3", o.ret)

        def infinite():
            o.if_(f"{sign} == 0", lambda: o.call("setSpecial(parts, 0, 0)"),
                  lambda: o.call("setSmallValue(parts, 0, 1, 1, layout)"))
            o.ret()

        o.if_(f"{kind} == 2", infinite)
        o.if_(f"{kind} == 0", lambda: (one_result(o), o.ret()))
        mag = o.calc("magnitudeOf(parts)")

        def negative_big():
            o.call("setSmallValue(parts, 0, 1, 1, layout)")
            o.ret()

        o.if_(f"{sign} == 1 && {mag} > 3", negative_big)
        o.if_(f"{sign} == 0 && {mag} > 7", lambda: (zero_result(o, 0), o.ret()))
        begin(o)
        load_x(o, 0)
        abs_reg(o, 0)

        def tail():
            o.call("bfErfcFraction(ws, 3, 0)")

        def body_part():
            o.call("bfErfSeries(ws, 1, 0)")
            setint(o, 2, 1)
            o.if_(f"{sign} == 1", lambda: add(o, 3, 2, 1), lambda: sub(o, 3, 2, 1))

        o.if_(f"{mag} > 3", tail, body_part)
        finish(o, 3, True)

    core("erfcCore", "erfc on parts", erfc_body)


def gamma_cores():
    def gamma_body(o):
        kind, sign = prelude(o)
        o.if_(f"{kind} == 3", o.ret)

        def infinite():
            o.if_(f"{sign} == 1", lambda: o.call("invalidNaN(parts)"))
            o.ret()

        o.if_(f"{kind} == 2", infinite)
        o.if_(f"{kind} == 0", lambda: (inf_result(o, sign), o.ret()))
        iy = o.calc("integerKind(parts)")
        o.if_(f"{sign} == 1 && {iy} != 0", lambda: (o.call("invalidNaN(parts)"), o.ret()))
        mag = o.calc("magnitudeOf(parts)")

        def positive():
            o.if_(f"{mag} > 11", lambda: (inf_result(o, 0), o.ret()))
            begin(o)
            load_x(o, 0)
            n = o.calc("bfGammaShift(ws, 1, 2, 0)")
            o.call("bfStirling(ws, 3, 1)")
            o.call("bfExp(ws, 4, 3)")
            o.if_(f"{n} > 0", lambda: div(o, 4, 4, 2))
            finish(o, 4, True)

        o.if_(f"{sign} == 0", positive)
        begin(o)
        load_x(o, 0)
        par = o.calc("bfNearest(ws, 5, 6, 0)")
        setint(o, 1, 1)
        sub(o, 1, 1, 0)
        n = o.calc("bfGammaShift(ws, 7, 2, 1)")
        o.call("bfStirling(ws, 3, 7)")
        e2 = o.calc("bfLog2Of(ws, 3)")

        def underflow():
            fs = o.calc("getHead(ws, 6, 0)")
            sg = o.calc(f"({par} + {fs}) & 1")
            o.call("heap.give(ws)")
            zero_result(o, sg)
            o.ret()

        o.if_(f"{e2} > 15", underflow)
        o.call("bfExp(ws, 4, 3)")
        o.if_(f"{n} > 0", lambda: div(o, 4, 4, 2))
        o.call("bfSinPi(ws, 8, 6)")
        fs = o.calc("getHead(ws, 6, 0)")
        o.call("setHead(ws, 8, 0, 0)")
        mul(o, 9, 8, 4)
        const(o, 10, PI)
        div(o, 11, 10, 9)
        sg = o.calc(f"({par} + {fs}) & 1")
        set_sign(o, 11, sg)
        finish(o, 11, True)

    core("tgammaCore", "tgamma on parts", gamma_body)

    def lgamma_body(o):
        kind, sign = prelude(o)
        one = o.const("Int64", "1", "plus")
        minus = o.const("Int64", "-1", "minus")
        o.if_(f"{kind} == 3", lambda: o.ret(one))

        def infinite():
            o.call("setSpecial(parts, 2, 0)")
            o.ret(one)

        o.if_(f"{kind} == 2", infinite)

        def zero():
            inf_result(o, 0)
            o.if_(f"{sign} == 1", lambda: o.ret(minus), lambda: o.ret(one))

        o.if_(f"{kind} == 0", zero)
        iy = o.calc("integerKind(parts)")
        o.if_(f"{sign} == 1 && {iy} != 0", lambda: (inf_result(o, 0), o.ret(one)))

        def positive():
            begin(o)
            load_x(o, 0)
            setint(o, 1, 1)
            c1 = o.calc("bfCompare(ws, 0, 1)")
            setint(o, 1, 2)
            c2 = o.calc("bfCompare(ws, 0, 1)")

            def exact_zero():
                o.call("heap.give(ws)")
                o.call("setSpecial(parts, 0, 0)")
                o.ret(one)

            o.if_(f"{c1} == 0 || {c2} == 0", exact_zero)
            n = o.calc("bfGammaShift(ws, 1, 2, 0)")
            o.call("bfStirling(ws, 3, 1)")

            def with_product():
                o.call("bfLog(ws, 4, 2)")
                sub(o, 3, 3, 4)

            o.if_(f"{n} > 0", with_product)
            o.call("bfFinish(ws, 3, parts, layout)")
            o.call("heap.give(ws)")
            o.call("noteRange(parts)")
            o.ret(one)

        o.if_(f"{sign} == 0", positive)
        begin(o)
        load_x(o, 0)
        par = o.calc("bfNearest(ws, 5, 6, 0)")
        setint(o, 1, 1)
        sub(o, 1, 1, 0)
        n = o.calc("bfGammaShift(ws, 7, 2, 1)")
        o.call("bfStirling(ws, 3, 7)")

        def with_product():
            o.call("bfLog(ws, 4, 2)")
            sub(o, 3, 3, 4)

        o.if_(f"{n} > 0", with_product)
        o.call("bfSinPi(ws, 8, 6)")
        fs = o.calc("getHead(ws, 6, 0)")
        o.call("setHead(ws, 8, 0, 0)")
        o.call("bfLog(ws, 9, 8)")
        const(o, 12, PI)
        o.call("bfLog(ws, 10, 12)")
        sub(o, 10, 10, 9)
        sub(o, 10, 10, 3)
        sg = o.calc(f"({par} + {fs}) & 1")
        o.call("bfFinish(ws, 10, parts, layout)")
        o.call("heap.give(ws)")
        o.call("noteRange(parts)")
        o.if_(f"{sg} == 1", lambda: o.ret(minus), lambda: o.ret(one))

    core("lgammaCore", "lgamma on parts; gives the sign of gamma(x), 1 or -1", lgamma_body, output="Int64")


# ---------------------------------------------------------------- fma

def fma_core():
    def body(o):
        kx, sx = prelude(o)
        ky = o.calc("clong.getPart(py, 8)", "ky")
        sy = o.calc("clong.getPart(py, 0)", "sy")
        kz = o.calc("clong.getPart(pz, 8)", "kz")
        sz = o.calc("clong.getPart(pz, 0)", "sz")
        sp = o.calc(f"({sx} + {sy}) & 1", "sp")
        o.if_(f"({kx} == 2 && {ky} == 0) || ({kx} == 0 && {ky} == 2)", lambda: (o.call("invalidNaN(parts)"), o.ret()))
        o.if_(f"{kx} == 3 || {ky} == 3 || {kz} == 3", lambda: (o.call("setSpecial(parts, 3, 0)"), o.ret()))

        def prod_infinite():
            o.if_(f"{kz} == 2 && {sz} != {sp}", lambda: (o.call("invalidNaN(parts)"), o.ret()))
            o.call(f"setSpecial(parts, 2, {sp})")
            o.ret()

        o.if_(f"{kx} == 2 || {ky} == 2", prod_infinite)

        def z_infinite():
            o.call(f"setSpecial(parts, 2, {sz})")
            o.ret()

        o.if_(f"{kz} == 2", z_infinite)

        def product_zero():
            def both():
                # +0 unless both are -0
                o.call(f"setSpecial(parts, 0, {sp} & {sz})")
                o.ret()

            o.if_(f"{kz} == 0", both)
            o.call("clong.setPart(parts, 0, " + sz + ")")
            o.call("clong.setPart(parts, 8, 1)")
            o.call("clong.setPart(parts, 16, clong.getPart(pz, 16))")
            o.call("clong.setSignificand(parts, clong.highOf(pz), clong.lowOf(pz))")
            o.call("clong.settleAs(parts, 0, layout)")
            o.ret()

        o.if_(f"{kx} == 0 || {ky} == 0", product_zero)
        begin(o)
        o.call(f"fmaExact(ws, parts, py, pz, {sp}, {sz}, {kz}, layout)")
        o.call("heap.give(ws)")
        o.call("noteRange(parts)")
        o.ret()

    core("fmaCore", "fma on parts: x * y + z with one rounding", body, extra=[("py", ADDR), ("pz", ADDR)])

    # the exact sum: P (x's and y's significands multiplied, 8 limbs) and Z aligned to a common power in T and U
    o = new("fmaExact", "x * y + z exactly in 32-bit limbs, rounded once into parts (x in parts; x and y finite nonzero)",
            [("parts", ADDR), ("py", ADDR), ("pz", ADDR), ("sp", "Int64"), ("sz", "Int64"), ("kz", "Int64"),
             ("layout", "Int64")])
    kz, sp, sz = "kz", "sp", "sz"
    nothing = o.const("UInt64", "0", "nothing")
    one_cell = o.const("UInt64", "1", "oneCell")
    xh = o.calc("clong.highOf(parts)")
    xl = o.calc("clong.lowOf(parts)")
    yh = o.calc("clong.highOf(py)")
    yl = o.calc("clong.lowOf(py)")
    ex = o.calc("clong.getPart(parts, 16)")
    ey = o.calc("clong.getPart(py, 16)")
    # limbs of x in T[0..3], y in U[0..3]
    for base, hi, lo in ((BUF_T, xh, xl), (BUF_U, yh, yl)):
        o.call(st(f"{base}", f"{lo} & {MASK}"))
        o.call(st(f"{base} + 8", f"{lo} >> 32"))
        o.call(st(f"{base} + 16", f"{hi} & {MASK}"))
        o.call(st(f"{base} + 24", f"{hi} >> 32"))

    def clear(j):
        o.call(st(f"{BUF_P} + {j} * 8", nothing))

    o.for_(0, 10, clear)

    def row(i):
        carry = o.var("UInt64", "0", "c")
        o.set(carry, nothing)
        xi = o.calc(ld(f"{BUF_T} + {i} * 8"))

        def col(j):
            yj = o.calc(ld(f"{BUF_U} + {j} * 8"))
            at = f"{BUF_P} + ({i} + {j}) * 8"
            cur = o.calc(ld(at))
            t = o.calc(f"{xi} * {yj} + {cur} + {carry}")
            o.call(st(at, f"{t} & {MASK}"))
            o.set(carry, f"{t} >> 32")

        o.for_(0, 4, col)
        o.call(st(f"{BUF_P} + ({i} + 4) * 8", carry))

    o.for_(0, 4, row)
    # the product is in BUF_P (8 limbs) with power ep; z in BUF_Q (4 limbs) with power ez
    ep = o.calc(f"{ex} + {ey}")
    zh = o.calc("clong.highOf(pz)")
    zl = o.calc("clong.lowOf(pz)")
    ez = o.calc("clong.getPart(pz, 16)")
    o.call(st(f"{BUF_Q}", f"{zl} & {MASK}"))
    o.call(st(f"{BUF_Q} + 8", f"{zl} >> 32"))
    o.call(st(f"{BUF_Q} + 16", f"{zh} & {MASK}"))
    o.call(st(f"{BUF_Q} + 24", f"{zh} >> 32"))
    lp = o.var("Int64", "0", "lp")
    o.set(lp, "bitsOf(ws, " + str(BUF_P) + ", 8)")
    lz = o.var("Int64", "0", "lz")
    o.set(lz, "bitsOf(ws, " + str(BUF_Q) + ", 4)")
    tp = o.calc(f"{ep} + {lp}")
    tz = o.calc(f"{ez} + {lz}")
    # a z far below the product, or a product far below z, is only a sticky bit: replace it by a single bit 600 places down
    epv = o.var("Int64", "0", "epv")
    ezv = o.var("Int64", "0", "ezv")
    o.set(epv, ep)
    o.set(ezv, ez)
    far = o.const("Int64", "600", "far")
    z_zero = o.calc(f"{kz} == 0")

    def z_negligible():
        o.call(st(f"{BUF_Q}", one_cell))
        for j in (1, 2, 3):
            o.call(st(f"{BUF_Q} + {j} * 8", nothing))
        o.set(ezv, f"{tp} - {far} - 1")
        o.set(lz, "1")

    def z_missing():
        for j in range(4):
            o.call(st(f"{BUF_Q} + {j} * 8", nothing))
        o.set(ezv, f"{tp} - {far} - 1")
        o.set(lz, "0")

    o.if_(z_zero, z_missing, lambda: o.if_(f"{tp} - {tz} > {far}", z_negligible))
    tzv = o.calc(f"{ezv} + {lz}")

    def p_negligible():
        for j in range(8):
            o.call(st(f"{BUF_P} + {j} * 8", one_cell if j == 0 else nothing))
        o.set(epv, f"{tzv} - {far} - 1")
        o.set(lp, "1")

    o.if_(f"{tzv} - {tp} > {far} && !{z_zero}", p_negligible)
    # align to the lower power
    lower = o.calc(f"{epv} < {ezv}")
    base_power = o.var("Int64", "0", "e0")
    o.if_(lower, lambda: o.set(base_power, epv), lambda: o.set(base_power, ezv))
    sh_p = o.calc(f"{epv} - {base_power}")
    sh_z = o.calc(f"{ezv} - {base_power}")

    def fill(j):
        a = o.calc(f"bitsAt(ws, {BUF_P}, 8, {j} * 32 - {sh_p})")
        o.call(st(f"{BUF_T} + {j} * 8", a))
        b = o.calc(f"bitsAt(ws, {BUF_Q}, 4, {j} * 32 - {sh_z})")
        o.call(st(f"{BUF_U} + {j} * 8", b))

    o.for_(0, 39, fill)
    o.call(st(f"{BUF_T} + 39 * 8", nothing))
    o.call(st(f"{BUF_U} + 39 * 8", nothing))
    # same signs: add; different: subtract the smaller from the larger
    opposite = o.calc(f"{sp} != {sz}")
    rsign = o.var("Int64", "0", "rs")
    o.set(rsign, sp)

    def add_all():
        carry = o.var("UInt64", "0", "c")
        o.set(carry, nothing)

        def each(j):
            a = o.calc(ld(f"{BUF_T} + {j} * 8"))
            b = o.calc(ld(f"{BUF_U} + {j} * 8"))
            t = o.calc(f"{a} + {b} + {carry}")
            o.call(st(f"{BUF_T} + {j} * 8", f"{t} & {MASK}"))
            o.set(carry, f"{t} >> 32")

        o.for_(0, 40, each)

    def subtract():
        cmp = o.var("Int64", "0", "cmp")
        j = o.var("Int64", "0", "j")
        o.set(j, "39")

        def scan():
            a = o.calc(ld(f"{BUF_T} + {j} * 8"))
            b = o.calc(ld(f"{BUF_U} + {j} * 8"))
            o.if_(f"{a} > {b}", lambda: (o.set(cmp, "1"), o.exit_loop()))
            o.if_(f"{a} < {b}", lambda: (o.set(cmp, "0 - 1"), o.exit_loop()))
            o.set(j, f"{j} - 1")

        o.while_(f"{j} >= 0", scan)

        def swap():
            def each(j):
                a = o.calc(ld(f"{BUF_T} + {j} * 8"))
                b = o.calc(ld(f"{BUF_U} + {j} * 8"))
                o.call(st(f"{BUF_T} + {j} * 8", b))
                o.call(st(f"{BUF_U} + {j} * 8", a))

            o.for_(0, 40, each)
            o.set(rsign, sz)

        o.if_(f"{cmp} < 0", swap)
        borrow = o.var("UInt64", "0", "b")
        o.set(borrow, nothing)

        def each(j):
            a = o.calc(ld(f"{BUF_T} + {j} * 8"))
            b = o.calc(ld(f"{BUF_U} + {j} * 8"))
            owed = o.calc(f"{b} + {borrow}")
            t = o.var("UInt64", "0", "u")
            o.if_(f"{a} < {owed}", lambda: (o.set(t, f"{a} + 4294967296 - {owed}"), o.set(borrow, one_cell)),
                  lambda: (o.set(t, f"{a} - {owed}"), o.set(borrow, nothing)))
            o.call(st(f"{BUF_T} + {j} * 8", t))

        o.for_(0, 40, each)

    o.if_(opposite, subtract, add_all)
    # the top 128 bits and the sticky rest
    length = o.calc(f"bitsOf(ws, {BUF_T}, 40)")

    def exact_zero():
        o.call("clong.setPart(parts, 0, 0)")
        o.call("clong.setPart(parts, 8, 0)")
        o.call("clong.setSignificand(parts, 0, 0)")
        o.ret()

    o.if_(f"{length} == 0", exact_zero)
    low = o.calc(f"{length} - 128")
    w0 = o.calc(f"bitsAt(ws, {BUF_T}, 40, {low})")
    w1 = o.calc(f"bitsAt(ws, {BUF_T}, 40, {low} + 32)")
    w2 = o.calc(f"bitsAt(ws, {BUF_T}, 40, {low} + 64)")
    w3 = o.calc(f"bitsAt(ws, {BUF_T}, 40, {low} + 96)")
    sticky = o.var("Int64", "0", "sticky")

    def below():
        j = o.var("Int64", "0", "j")
        o.set(j, "0")

        def each():
            p = o.calc(f"{j} * 32")
            v = o.calc(f"bitsAt(ws, {BUF_T}, 40, {p})")
            more = o.calc(f"{p} + 32 > {low}")
            masked = o.var("UInt64", "0", "m")
            # only the bits strictly below `low` count
            o.if_(more, lambda: o.set(masked, f"{v} & (({one_cell} << ({low} - {p})) - {one_cell})"), lambda: o.set(masked, v))
            o.if_(f"{masked} != {nothing}", lambda: (o.set(sticky, "1"), o.exit_loop()))
            o.set(j, f"{j} + 1")

        o.while_(f"{j} * 32 < {low}", each)

    o.if_(f"{low} > 0", below)
    o.call(f"clong.setPart(parts, 0, {rsign})")
    o.call("clong.setPart(parts, 8, 1)")
    o.call(f"clong.setPart(parts, 16, {base_power} + {low})")
    o.call(f"clong.setSignificand(parts, ({w3} << 32) | {w2}, ({w1} << 32) | {w0})")
    o.call(f"clong.settleAs(parts, {sticky}, layout)")
    o.ret()

    o = new("bitsOf", "The bit length of an array of limbs (0 for zero)", [("base", "Int64"), ("count", "Int64")], "Int64")
    nothing = o.const("UInt64", "0", "nothing")
    zero = o.const("Int64", "0", "empty")
    i = o.var("Int64", "0", "i")
    o.set(i, "count - 1")

    def scan():
        c = o.calc(ld(f"base + {i} * 8"))

        def found():
            bits = o.calc(f"clong.bitLength({nothing}, {c})")
            r = o.calc(f"{i} * 32 + {bits}")
            o.ret(r)

        o.if_(f"{c} != {nothing}", found)
        o.set(i, f"{i} - 1")

    o.while_(f"{i} >= 0", scan)
    o.ret(zero)
