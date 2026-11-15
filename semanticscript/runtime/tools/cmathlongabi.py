"""The `abi library` operations of cmathlong and the writing of cmathlong.dsl (see cmathlonggen.py)."""
from __future__ import annotations

import os

from cmathlongbuild import ADDR, Op, ALL, new
import cmathlonggen as G
import cmathlongkernels as K
import cmathlongmath as M
import cmathlongcores as C

LD = "machine.LongDouble"
HERE = os.path.dirname(os.path.abspath(__file__))

# name in C, core, doc
ONE = [
    ("sinl", "sinCore", "sine"), ("cosl", "cosCore", "cosine"), ("tanl", "tanCore", "tangent"),
    ("asinl", "asinCore", "arc sine"), ("acosl", "acosCore", "arc cosine"), ("atanl", "atanCore", "arc tangent"),
    ("expl", "expCore", "e to the power x"), ("exp2l", "exp2Core", "2 to the power x"),
    ("expm1l", "expm1Core", "e to the power x less 1"), ("logl", "logCore", "natural logarithm"),
    ("log2l", "log2Core", "base 2 logarithm"), ("log10l", "log10Core", "base 10 logarithm"),
    ("log1pl", "log1pCore", "natural logarithm of 1 + x"), ("cbrtl", "cbrtCore", "cube root"),
    ("sinhl", "sinhCore", "hyperbolic sine"), ("coshl", "coshCore", "hyperbolic cosine"),
    ("tanhl", "tanhCore", "hyperbolic tangent"), ("asinhl", "asinhCore", "inverse hyperbolic sine"),
    ("acoshl", "acoshCore", "inverse hyperbolic cosine"), ("atanhl", "atanhCore", "inverse hyperbolic tangent"),
    ("erfl", "erfCore", "error function"), ("erfcl", "erfcCore", "complementary error function"),
    ("tgammal", "tgammaCore", "gamma function"), ("lgammal", "lgammaCore", "natural logarithm of |gamma(x)|"),
]
TWO = [("atan2l", "atan2Core", "arc tangent of y / x"), ("powl", "powCore", "x to the power y"),
       ("hypotl", "hypotCore", "square root of x*x + y*y")]
NAMES = [n for n, _c, _d in ONE] + [n for n, _c, _d in TWO] + ["fmal", "lgammal_r"]
OP_NAMES = {}
INVARIANT = {}


def opname(cname):
    return cname[:-1] + "Long"


def wrappers():
    for cname, core, doc in ONE:
        name = opname(cname)
        OP_NAMES[cname] = name
        INVARIANT[cname] = f"{cname}IsAccurate"
        o = new(name, f"{cname}: the {doc} of a long double, within 1 ulp of the exact value (the method's own error is 2^-300)",
                [("x", LD)], LD, abi=cname, invariant=(f"{cname}IsAccurate", f"Gives the {doc} correctly rounded but for the rarest cases"),
                ws=False)
        o.call_text = None
        parts = o.calc("partsOfLong(x)", "parts")
        layout = o.calc("clong.format()", "layout")
        if core == "lgammaCore":
            o.calc(f"lgammaCore({parts}, {layout})", "sign")
        else:
            o.call(f"{core}({parts}, {layout})")
        v = o.calc(f"longOfParts({parts})", "result")
        o.ret(v)
    for cname, core, doc in TWO:
        name = opname(cname)
        OP_NAMES[cname] = name
        first, second = ("y", "x") if cname == "atan2l" else ("x", "y")
        INVARIANT[cname] = f"{cname}IsAccurate"
        o = new(name, f"{cname}: the {doc} of long doubles", [(first, LD), (second, LD)], LD, abi=cname,
                invariant=(f"{cname}IsAccurate", f"Gives the {doc} correctly rounded but for the rarest cases"), ws=False)
        pa = o.calc(f"partsOfLong({first})", "parts")
        pb = o.calc(f"partsOfLong({second})", "other")
        layout = o.calc("clong.format()", "layout")
        o.call(f"{core}({pa}, {pb}, {layout})")
        o.call(f"heap.give({pb})")
        v = o.calc(f"longOfParts({pa})", "result")
        o.ret(v)
    o = new("fusedMultiplyAddLong", "fmal: x * y + z of long doubles with one rounding", [("x", LD), ("y", LD), ("z", LD)], LD,
            abi="fmal", invariant=("fmalIsExact", "Gives x * y + z correctly rounded, whatever the sizes of the three"), ws=False)
    OP_NAMES["fmal"] = "fusedMultiplyAddLong"
    INVARIANT["fmal"] = "fmalIsExact"
    pa = o.calc("partsOfLong(x)", "parts")
    pb = o.calc("partsOfLong(y)", "other")
    pc = o.calc("partsOfLong(z)", "third")
    layout = o.calc("clong.format()", "layout")
    o.call(f"fmaCore({pa}, {pb}, {pc}, {layout})")
    o.call(f"heap.give({pb})")
    o.call(f"heap.give({pc})")
    v = o.calc(f"longOfParts({pa})", "result")
    o.ret(v)
    o = new("logGammaSignedLong", "lgammal_r: lgammal with the sign of gamma(x) stored through a pointer as an int",
            [("x", LD), ("signp", ADDR)], LD, abi="lgammal_r",
            invariant=("lgammalrIsAccurate", "Gives what lgammal gives and stores the sign of gamma(x)"), ws=False)
    OP_NAMES["lgammal_r"] = "logGammaSignedLong"
    INVARIANT["lgammal_r"] = "lgammalrIsAccurate"
    parts = o.calc("partsOfLong(x)", "parts")
    layout = o.calc("clong.format()", "layout")
    sign = o.calc(f"lgammaCore({parts}, {layout})", "sign")
    o.call(f"machine.storeInt32(signp, convert.int64ToInt32({sign}))")
    v = o.calc(f"longOfParts({parts})", "result")
    o.ret(v)


def build_ops():
    del ALL[:]
    G.prims()
    K.hexpart()
    K.conversions()
    K.newton()
    M.exp_kernels()
    M.log_kernels()
    M.trig_kernels()
    M.special_kernels()
    C.helpers()
    C.atan_helpers()
    C.exp_core("exp")
    C.exp_core("exp2")
    C.exp_core("expm1")
    for mode in range(4):
        C.log_core(mode)
    C.pow_core()
    C.cbrt_core()
    C.hypot_core()
    for which in ("sin", "cos", "tan"):
        C.trig_core(which)
    C.atan_core()
    C.asin_acos_cores()
    C.atan2_core()
    C.hyperbolic_cores()
    C.erf_cores()
    C.gamma_cores()
    C.fma_core()
    wrappers()


HEAD = '''module cmathlong "math.h's transcendental long double functions in SemanticScript: sinl, cosl, tanl, asinl, acosl, atanl, atan2l, expl, exp2l, expm1l, logl, log2l, log10l, log1pl, powl, cbrtl, hypotl, sinhl, coshl, tanhl, asinhl, acoshl, atanhl, erfl, erfcl, tgammal, lgammal, lgammal_r, and fmal, on 320-bit numbers for x87, binary128 and double layouts alike"
  path cmathlong
  imports standard.machine standard.system standard.math standard.compare standard.convert standard.bits standard.logic standard.test heap clibrary clong
  exports none

capability memoryAccess "Authority to read and write a call's workspace and a long double's parts" use machine.memory none

capability systemCalls "Authority to take memory for a call's workspace" use system.calls none

## Each function works on a 320-bit floating point number of its own (a sign, a kind, a power of two, ten
## 32-bit limbs), in the 128 registers of a workspace taken from the heap for the call (nothing is shared, so every
## function is reentrant), and the result is rounded once into the layout by clong's settleAs. The code is the same
## for x87's 64 bits, binary128's 113 and a double's 53, so its tests run on all three layouts from any machine. The
## generator tools/cmathlonggen.py writes this file (and the tables in it).
constant forever "The bound of a loop that ends when its work does" Int64 9223372036854775807

'''


def render(tests_text):
    nl = chr(10)
    body = (nl + nl).join(o.render() for o in ALL)
    return HEAD + body + nl + nl + "@tests" + nl + nl + tests_text + nl


def main():
    from cmathlongbuild import assign_effects
    import cmathlongtests as X
    import cmathlongtestops as TO
    nl = chr(10)
    build_ops()
    table, count = X.table_text()
    helpers = TO.helper_ops(table)
    names = [(n, OP_NAMES[n], nargs, INVARIANT[n]) for n, _c, nargs in X.FUNCS] + [("lgammal_r", OP_NAMES["lgammal_r"], 2, INVARIANT["lgammal_r"])]
    t1 = TO.table_test(count)
    t2 = TO.abi_test(count, names)
    assign_effects(ALL + helpers + [t1, t2])
    verifies = [(OP_NAMES[c], INVARIANT[c]) for c in NAMES]
    tests_text = (nl + nl).join([o.render() for o in helpers] + [t1.render(), t2.render_test(verifies)])
    text = render(tests_text)
    path = os.path.join(HERE, "cmathlong.dsl")
    with open(path, "w", encoding="utf-8", newline=nl) as fh:
        fh.write(text)
    print(path, text.count(nl), "lines,", count, "cases")


if __name__ == "__main__":
    main()
