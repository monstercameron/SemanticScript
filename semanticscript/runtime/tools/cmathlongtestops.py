"""The DSL of cmathlong's tests: a table test over all three layouts and an abi test calling each `abi library`
operation of the system's own long double (see cmathlonggen.py and cmathlongtests.py)."""
from __future__ import annotations

import os
from cmathlongbuild import ADDR, Op
import cmathlongtests as X

LD = "machine.LongDouble"


def helper_ops(text):
    ops = []
    o = Op("caseTable", "The address of the table of cases", [], "machine.Address")
    ops.append(o)
    cases = o.const("String", '"' + text + '"', "cases")
    base = o.calc(f"machine.addressOfString({cases})")
    o.ret(base)

    o = Op("loadRecord", "Read a record of the table into parts: kind, sign, power, and the significand's two words",
           [("parts", ADDR), ("base", ADDR), ("at", "Int64")])
    ops.append(o)
    kind = o.calc("hexAt(base, at, 1)")
    sign = o.calc("hexAt(base, at + 1, 1)")
    power = o.calc("hexAt(base, at + 2, 16)")
    hi = o.calc("hexAt(base, at + 18, 16)")
    lo = o.calc("hexAt(base, at + 34, 16)")
    o.call(f"clong.setPart(parts, 8, convert.uint64ToInt64({kind}))")
    o.call(f"clong.setPart(parts, 0, convert.uint64ToInt64({sign}))")
    o.call(f"clong.setPart(parts, 16, convert.uint64BitsToInt64({power}))")
    o.call(f"clong.setSignificand(parts, {hi}, {lo})")
    o.ret()

    o = Op("runCase", "Run function number fn of the table on parts (x in px, y in py, z in pz)",
           [("fn", "Int64"), ("layout", "Int64"), ("px", ADDR), ("py", ADDR), ("pz", ADDR)])
    ops.append(o)

    def chain(i):
        if i == len(X.FUNCS):
            return
        name, core, nargs = X.FUNCS[i]
        if core == "lgammaCore":
            def call():
                o.calc("lgammaCore(px, layout)", "sign")
        elif nargs == 1:
            def call(c=core):
                o.call(f"{c}(px, layout)")
        elif nargs == 2:
            def call(c=core):
                o.call(f"{c}(px, py, layout)")
        else:
            def call(c=core):
                o.call(f"{c}(px, py, pz, layout)")
        o.if_(f"fn == {i}", lambda: (call(), o.ret()))
        chain(i + 1)

    chain(0)
    o.ret()

    o = Op("sameWithin", "How far a result's parts are from the expected ones: 0 when the same, the distance in units of the last place when the power and the sign agree, 99 otherwise",
           [("a", ADDR), ("b", ADDR)], "Int64")
    ops.append(o)
    far = o.const("Int64", "99", "far")
    same = o.const("Int64", "0", "same")
    ka = o.calc("clong.getPart(a, 8)")
    kb = o.calc("clong.getPart(b, 8)")
    o.if_(f"{ka} != {kb}", lambda: o.ret(far))
    o.if_(f"{ka} == 3", lambda: o.ret(same))
    sa = o.calc("clong.getPart(a, 0)")
    sb = o.calc("clong.getPart(b, 0)")
    o.if_(f"{sa} != {sb}", lambda: o.ret(far))
    o.if_(f"{ka} != 1", lambda: o.ret(same))
    ea = o.calc("clong.getPart(a, 16)")
    eb = o.calc("clong.getPart(b, 16)")
    o.if_(f"{ea} != {eb}", lambda: o.ret(far))
    ha = o.calc("clong.highOf(a)")
    hb = o.calc("clong.highOf(b)")
    o.if_(f"{ha} != {hb}", lambda: o.ret(far))
    la = o.calc("clong.lowOf(a)")
    lb = o.calc("clong.lowOf(b)")
    d = o.var("UInt64", "0", "d")
    o.if_(f"{la} >= {lb}", lambda: o.set(d, f"{la} - {lb}"), lambda: o.set(d, f"{lb} - {la}"))
    o.if_(f"{d} > 90", lambda: o.ret(far))
    r = o.calc(f"convert.uint64ToInt64({d})")
    o.ret(r)

    o = Op("prepareCase", "Load the first case of the table for a function and layout into parts, with the expected result; its tolerance, or -1 when there is none",
           [("base", ADDR), ("count", "Int64"), ("fn", "Int64"), ("layout", "Int64"), ("px", ADDR), ("py", ADDR),
            ("pz", ADDR), ("want", ADDR)], "Int64")
    ops.append(o)
    missing = o.const("Int64", "-1", "missing")
    i = o.var("Int64", "0", "i")
    o.set(i, "0")

    def each():
        at = o.calc(f"{i} * {X.CASE_WIDTH}")
        f = o.calc(f"convert.uint64ToInt64(hexAt(base, {at}, 2))")
        l = o.calc(f"convert.uint64ToInt64(hexAt(base, {at} + 2, 1))")

        def found():
            tol = o.calc(f"convert.uint64ToInt64(hexAt(base, {at} + 3, 1))")
            o.call(f"loadRecord(px, base, {at} + 4)")
            o.call(f"loadRecord(py, base, {at} + 54)")
            o.call(f"loadRecord(pz, base, {at} + 104)")
            o.call(f"loadRecord(want, base, {at} + 154)")
            o.ret(tol)

        o.if_(f"{f} == fn && {l} == layout", found)
        o.set(i, f"{i} + 1")

    o.while_(f"{i} < count", each)
    o.ret(missing)

    o = Op("checkResult", "Assert a long double is within a tolerance of the expected parts (which are given back)",
           [("result", LD), ("want", ADDR), ("tolerance", "Int64")])
    ops.append(o)
    parts = o.calc("partsOfLong(result)")
    diff = o.calc(f"sameWithin({parts}, want)")
    o.call(f"heap.give({parts})")
    o.call("heap.give(want)")
    o.call(f"test.assertTrue({diff} <= tolerance)")
    o.ret()

    o = Op("makeLong", "A long double of this system from a whole number times a power of two", [("sign", "Int64"), ("value", "UInt64"), ("power", "Int64")], LD)
    ops.append(o)
    parts = o.calc("clong.partsNew()")
    layout = o.calc("clong.format()")
    o.call(f"setSmallValue({parts}, sign, value, power, {layout})")
    v = o.calc(f"longOfParts({parts})")
    o.ret(v)
    return ops


def table_test(count):
    o = Op("checkTable", "The functions of cmathlong on the table of cases, on the double, x87, and binary128 layouts: every result within its tolerance of the correctly rounded value",
           [])
    base = o.calc("caseTable()")
    px = o.calc("clong.partsNew()")
    py = o.calc("clong.partsNew()")
    pz = o.calc("clong.partsNew()")
    want = o.calc("clong.partsNew()")
    bad = o.var("Int64", "0", "bad")
    o.set(bad, "0 - 1")

    def each(i):
        at = o.calc(f"{i} * {X.CASE_WIDTH}")
        fn = o.calc(f"convert.uint64ToInt64(hexAt({base}, {at}, 2))")
        layout = o.calc(f"convert.uint64ToInt64(hexAt({base}, {at} + 2, 1))")
        tol = o.calc(f"convert.uint64ToInt64(hexAt({base}, {at} + 3, 1))")
        o.call(f"loadRecord({px}, {base}, {at} + 4)")
        o.call(f"loadRecord({py}, {base}, {at} + 54)")
        o.call(f"loadRecord({pz}, {base}, {at} + 104)")
        o.call(f"loadRecord({want}, {base}, {at} + 154)")
        o.call(f"runCase({fn}, {layout}, {px}, {py}, {pz})")
        diff = o.calc(f"sameWithin({px}, {want})")
        if os.environ.get("CMATHLONG_LIST"):
            o.if_(f"{diff} > {tol}", lambda: o.call(f"test.assertEqualInt64({fn} * 1000 + {diff}, {at} / {X.CASE_WIDTH})"))
        else:
            o.if_(f"{diff} > {tol}", lambda: o.if_(f"{bad} < 0", lambda: o.set(bad, i)))

    only = os.environ.get("CMATHLONG_ONLY")
    if only:
        # debugging: run one case, then compare field by field so the failure names the values
        start = int(only)
        o.for_(start, start + 1, each)
        for what, getter in (("kind", "clong.getPart({p}, 8)"), ("sign", "clong.getPart({p}, 0)"),
                             ("power", "clong.getPart({p}, 16)"),
                             ("high", "convert.uint64BitsToInt64(clong.highOf({p}))"),
                             ("low", "convert.uint64BitsToInt64(clong.lowOf({p}))")):
            o.call(f"test.assertEqualInt64({getter.format(p=want)}, {getter.format(p=px)})")
    else:
        o.for_(0, count, each)
    o.call(f"test.assertEqualInt64(0 - 1, {bad})")
    o.ret()
    return o


def abi_test(count, names):
    """names: [(function name, abi op name, nargs, invariant)]"""
    o = Op("abiTest", "Each `abi library` operation on this system's own long double against the table's expected result for its layout, and lgammal_r's sign",
           [])
    o.call("checkTable()")
    base = o.calc("caseTable()")
    native = o.calc("clong.format()")
    for fname, op, nargs, _inv in names:
        if fname == "lgammal_r":
            continue
        fid = X.FN_ID[fname]
        px = o.calc("clong.partsNew()", "px")
        py = o.calc("clong.partsNew()", "py")
        pz = o.calc("clong.partsNew()", "pz")
        want = o.calc("clong.partsNew()", "want")
        tol = o.calc(f"prepareCase({base}, {count}, {fid}, {native}, {px}, {py}, {pz}, {want})", "tol")

        def run(px=px, py=py, pz=pz, want=want, tol=tol, op=op, nargs=nargs):
            lx = o.calc(f"longOfParts({px})", "lx")
            if nargs == 1:
                o.call(f"heap.give({py})")
                o.call(f"heap.give({pz})")
                r = o.calc(f"{op}({lx})", "r")
            elif nargs == 2:
                ly = o.calc(f"longOfParts({py})", "ly")
                o.call(f"heap.give({pz})")
                r = o.calc(f"{op}({lx}, {ly})", "r")
            else:
                ly = o.calc(f"longOfParts({py})", "ly")
                lz = o.calc(f"longOfParts({pz})", "lz")
                r = o.calc(f"{op}({lx}, {ly}, {lz})", "r")
            o.call(f"checkResult({r}, {want}, {tol})")

        def skip(px=px, py=py, pz=pz, want=want):
            for p in (px, py, pz, want):
                o.call(f"heap.give({p})")

        o.if_(f"{tol} >= 0", run, skip)
    cell = o.calc("heap.take(16)", "cell")
    half = o.calc("makeLong(0, 5, -1)", "half")
    value = o.calc(f"logGammaSignedLong({half}, {cell})", "value")
    sign = o.calc(f"machine.loadInt32({cell})", "sign")
    o.call(f"test.assertTrue({sign} == 1)")
    negative = o.calc("makeLong(1, 1, -1)", "negative")
    value2 = o.calc(f"logGammaSignedLong({negative}, {cell})", "value")
    sign2 = o.calc(f"machine.loadInt32({cell})", "sign")
    o.call(f"test.assertTrue({sign2} == convert.int64ToInt32(0 - 1))")
    o.call(f"heap.give({cell})")
    o.ret()
    return o
