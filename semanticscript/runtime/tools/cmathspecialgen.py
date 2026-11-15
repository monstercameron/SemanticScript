"""Writes cmathspecial.dsl: the special functions of math.h (sinh, cosh, tanh, asinh, acosh, atanh, erf, erfc,
tgamma, lgamma, and their f-forms) in SemanticScript.

    python cmathspecialgen.py        # rewrites cmathspecial.dsl next to this file

The DSL is generated because its constants (the double-double splits of ln 2, pi, the Stirling coefficients, the
series coefficients) and its unrolled Horner steps are computed here with exact arithmetic. The methods are the
standard ones, written for this module: double-double arithmetic with Dekker products (no fused multiply-add is
assumed), exp by a Cody-Waite reduction with ln 2 in three parts and a Taylor series squared back up, log by one
Newton step on that exp, erf by the positive series and by Laplace's continued fraction for erfc, lgamma by
Stirling's series after shifting the argument above 24 and by the reflection formula below 0.
"""
from __future__ import annotations

import math
import os
import sys
from decimal import Decimal as D, getcontext
from fractions import Fraction as F

getcontext().prec = 130
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "tests"))

PI = D("3.14159265358979323846264338327950288419716939937510582097494459230781640628620899862803482534211706798214808651")
EG = D("0.57721566490153286060651209008240243104215933593992359880576723488486772677766467093694706329174674951463144724980708")
Z3 = D("1.2020569031595942853997381615114499907649862923404988817922715553418382057863130901864558736093352581461991577952607")
Z2 = PI * PI / 6
Z4 = PI ** 4 / 90
LN2 = D(2).ln()


def hx(x: float) -> str:
    return float(x).hex()


def dd(d) -> tuple[str, str]:
    d = D(d)
    h = float(d)
    return hx(h), hx(float(d - D(h)))


def split_bits(x: float, bits: int) -> float:
    m, e = math.frexp(x)
    return math.ldexp(round(math.ldexp(m, bits)), e - bits)


L2 = float(LN2)
C1 = split_bits(L2, 30)
R = LN2 - D(C1)
C2 = split_bits(float(R), 30)
C3 = float(R - D(C2))


def frac(n: int, d: int):
    return D(n) / D(d)


def bernoulli(n: int):
    a = [F(0)] * (n + 1)
    out = []
    for m in range(n + 1):
        a[m] = F(1, m + 1)
        for j in range(m, 0, -1):
            a[j - 1] = j * (a[j - 1] - a[j])
        out.append(a[0])
    return out


BN = bernoulli(40)
KSTIRLING = 16


def dfr(f: F) -> D:
    return D(f.numerator) / D(f.denominator)


# ------------------------------------------------------------------------------------------------ emit helpers
class Op:
    """The text of one operation, built a line at a time."""

    def __init__(self, name, doc, inputs=(), output=None, abi=None, invariant=None, lets=(), memory=True):
        self.lines = [f'op {name} "{doc}"']
        if invariant:
            self.lines.append(f'  invariant {invariant[0]} "{invariant[1]}"')
        for n, t in inputs:
            mode = "copied"
            self.lines.append(f"  input {n} {t} {mode}")
        if output:
            self.lines.append(f"  output {output}")
        if memory:
            self.lines.append("  effect use machine.memory")
            self.lines.append("  uses memoryAccess")
        if abi:
            self.lines.append(f'  abi library "{abi}"')
        for l in lets:
            self.lines.append(f"  let {l}")
        self.lines.append(":begin")
        self.n = 0

    def add(self, *ls):
        for l in ls:
            self.lines.append(l if l.startswith(":") else "  " + l)
        return self

    def calc(self, name, expr):
        self.lines.append(f"  calc {name} = {expr}")
        return self

    def set(self, name, expr):
        self.lines.append(f"  calc {name} := {expr}")
        return self

    def dd(self, op, hi, lo, *args):
        """hi, lo = op(args) for a double-double operation that leaves its low half in the cell."""
        self.lines.append(f"  calc {hi} = {op}({', '.join(args)})")
        if lo:
            self.lines.append(f"  calc {lo} = loadLow()")
        return self

    def text(self):
        return "\n".join(self.lines)


OPS: list[str] = []


def emit(op: Op):
    OPS.append(op.text())


def raw(text: str):
    OPS.append(text.strip("\n"))


MAXF = "1.7976931348623157e308"
INFBITS = "9218868437227405312"
NANBITS = "9221120237041090560"
SIGNBIT = "9223372036854775808"
MAGMASK = "9223372036854775807"

HEADER = '''module cmathspecial "The special functions of math.h in SemanticScript: sinh, cosh, tanh, asinh, acosh, atanh, erf, erfc, tgamma, and lgamma, for double and float, as glibc gives them in the C locale (D-153)"
  path cmathspecial
  imports standard.machine standard.math standard.compare standard.convert standard.bits standard.logic standard.test kernel clibrary
  exports none

capability memoryAccess "Authority to read and write the module's cells in machine.state" use machine.memory none

## The cells of machine.state that belong to this module, bytes 24576 to 24831: 24576 the low half of the
## double-double a routine last gave, 24584 the power of two an exp left out of its result, 24592 the sign lgamma
## last gave as an int (what glibc keeps in `signgam`, which a C library cannot export as a data symbol here), 24600
## the sign lgamma's core left for its callers.
constant lowAt "Where the low half of a double-double result is kept, in machine.state" Int64 24576

constant scaleAt "Where the power of two an exp leaves out of its result is kept, in machine.state" Int64 24584

constant signAt "Where the sign lgamma last gave, an int, is kept, in machine.state" Int64 24592

constant signWorkAt "Where the sign the gamma core found is kept, in machine.state" Int64 24600
'''


def build_small():
    raw('''
op loadLow "The low half of the double-double the last routine gave"
  output Float64
  effect use machine.memory
  uses memoryAccess
:begin
  cell = kernel.stateAt(lowAt)
  value = machine.loadFloat64(cell)
  return value

op storeLow "Keep the low half of a double-double result"
  input value Float64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  cell = kernel.stateAt(lowAt)
  machine.storeFloat64(cell, value)
  return

op loadScale "The power of two the last exp left out of its result"
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  cell = kernel.stateAt(scaleAt)
  value = machine.loadInt64(cell)
  return value

op storeScale "Keep the power of two an exp leaves out of its result"
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  cell = kernel.stateAt(scaleAt)
  machine.storeInt64(cell, value)
  return

op loadSignWork "The sign (1 or -1) the gamma core last found"
  output Int64
  effect use machine.memory
  uses memoryAccess
:begin
  cell = kernel.stateAt(signWorkAt)
  value = machine.loadInt64(cell)
  return value

op storeSignWork "Keep the sign (1 or -1) the gamma core found"
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  cell = kernel.stateAt(signWorkAt)
  machine.storeInt64(cell, value)
  return

op storeSignInt "Keep the sign lgamma gave, as the int glibc's signgam holds"
  input value Int64 copied
  effect use machine.memory
  uses memoryAccess
:begin
  cell = kernel.stateAt(signAt)
  calc narrow = convert.int64ToInt32(value)
  machine.storeInt32(cell, narrow)
  return

op magnitudeOf "The value with its sign bit cleared"
  input value Float64 copied
  output Float64
:begin
  calc cleared = convert.float64BitsToUInt64(value) & 9223372036854775807
  calc result = convert.uint64BitsToFloat64(cleared)
  return result

op withSign "The magnitude of one value with the sign of another"
  input magnitude Float64 copied
  input sign Float64 copied
  output Float64
:begin
  calc cleared = convert.float64BitsToUInt64(magnitude) & 9223372036854775807
  calc signOnly = convert.float64BitsToUInt64(sign) & 9223372036854775808
  calc result = convert.uint64BitsToFloat64(cleared | signOnly)
  return result

op isNotNumber "Whether a double is a NaN"
  input value Float64 copied
  output Bool
:begin
  calc cleared = convert.float64BitsToUInt64(value) & 9223372036854775807
  calc nan = cleared > 9218868437227405312
  return nan

op powerOfTwo "2 to a power from -1022 to 1023, made from its bits"
  input power Int64 copied
  output Float64
:begin
  calc field = convert.int64BitsToUInt64(power + 1023)
  calc result = convert.uint64BitsToFloat64(field << 52)
  return result

op scaleBy "A double times 2 to a power, exactly except for the one rounding of a subnormal or an overflow (the power is kept within 2040)"
  input value Float64 copied
  input power Int64 copied
  output Float64
  let k Int64 0 mut
:begin
  calc k := power
  when k > 2040 clampHigh checkLow
:clampHigh
  calc k := 2040
  goto split
:checkLow
  when k < -2040 clampLow split
:clampLow
  calc k := -2040
  goto split
:split
  calc half = k / 2
  calc rest = k - half
  calc first = value * powerOfTwo(half)
  calc second = first * powerOfTwo(rest)
  return second

op floorValue "The greatest whole number not above a double of magnitude under 2^62"
  input value Float64 copied
  output Float64
:begin
  calc truncated = convert.int64ToFloat64(convert.float64ToInt64(value))
  when truncated > value lower keep
:lower
  calc lowered = truncated - 1.0
  return lowered
:keep
  return truncated
''')


def build_dd():
    # ddAdd: Shewchuk's accurate sum of two double-doubles
    o = Op("ddAdd", "The sum of two double-doubles (their high halves with two-sum, their low halves likewise), the low half left in the cell",
           [("ah", "Float64"), ("al", "Float64"), ("bh", "Float64"), ("bl", "Float64")], "Float64")
    o.calc("s", "ah + bh").calc("bb", "s - ah").calc("e", "(ah - (s - bb)) + (bh - bb)")
    o.calc("t", "al + bl").calc("bt", "t - al").calc("f", "(al - (t - bt)) + (bl - bt)")
    o.calc("e2", "e + t").calc("s2", "s + e2").calc("e3", "e2 - (s2 - s)").calc("e4", "e3 + f")
    o.calc("s3", "s2 + e4").calc("lo", "e4 - (s3 - s2)").add("storeLow(lo)", "return s3")
    emit(o)
    o = Op("ddMul", "The product of two double-doubles with Dekker's exact product of the high halves (no fused multiply-add), the low half left in the cell",
           [("ah", "Float64"), ("al", "Float64"), ("bh", "Float64"), ("bl", "Float64")], "Float64")
    o.calc("p", "ah * bh")
    o.calc("a1", "ah * 134217729.0").calc("a2", "a1 - (a1 - ah)").calc("a3", "ah - a2")
    o.calc("b1", "bh * 134217729.0").calc("b2", "b1 - (b1 - bh)").calc("b3", "bh - b2")
    o.calc("e", "((a2 * b2 - p) + a2 * b3 + a3 * b2) + a3 * b3")
    o.calc("e2", "e + (ah * bl + al * bh)").calc("s", "p + e2").calc("lo", "e2 - (s - p)")
    o.add("storeLow(lo)", "return s")
    emit(o)
    o = Op("ddDivide", "The quotient of two double-doubles by three corrections, the low half left in the cell",
           [("ah", "Float64"), ("al", "Float64"), ("bh", "Float64"), ("bl", "Float64")], "Float64")
    o.calc("q1", "ah / bh")
    o.dd("ddMul", "p1", "p1l", "q1", "0.0", "bh", "bl")
    o.dd("ddAdd", "r1", "r1l", "ah", "al", "-p1", "-p1l")
    o.calc("q2", "r1 / bh")
    o.dd("ddMul", "p2", "p2l", "q2", "0.0", "bh", "bl")
    o.dd("ddAdd", "r2", "r2l", "r1", "r1l", "-p2", "-p2l")
    o.calc("q3", "r2 / bh")
    o.calc("s1", "q1 + q2").calc("l1", "q2 - (s1 - q1)")
    o.dd("ddAdd", "result", None, "s1", "l1", "q3", "0.0")
    o.add("return result")
    emit(o)
    o = Op("ddSquareRoot", "The square root of a positive double-double: the root of its high half and one correction, the low half left in the cell",
           [("ah", "Float64"), ("al", "Float64")], "Float64")
    o.calc("s", "machine.squareRoot(ah)")
    o.dd("ddMul", "p", "pl", "s", "0.0", "s", "0.0")
    o.dd("ddAdd", "r", "rl", "ah", "al", "-p", "-pl")
    o.calc("c", "(r + rl) / (2.0 * s)")
    o.calc("t", "s + c").calc("l", "c - (t - s)").add("storeLow(l)", "return t")
    emit(o)


def build_exp_log():
    taylor = [1.0 / math.factorial(n) for n in range(0, 12)]
    inv6 = dd(D(1) / D(6))
    o = Op("expScaled", "e to the power of a double-double, as a double-double times 2 to a power: the high half is the result, the low half is left in the cell and the power in its own",
           [("xh", "Float64"), ("xl", "Float64")], "Float64")
    o.calc("kd", f"xh * {hx(1 / L2)}")
    o.calc("kk", "convert.float64ToInt64(kd + 4096.5) - 4096")
    o.calc("kf", "convert.int64ToFloat64(kk)")
    o.calc("r0", f"xh - kf * {hx(C1)}")
    o.calc("kc2", f"kf * {hx(C2)}")
    o.calc("r1", "r0 - kc2").calc("bb", "r1 - r0")
    o.calc("e1", "(r0 - (r1 - bb)) + ((0.0 - kc2) - bb)")
    o.calc("e2", f"0.0 - kf * {hx(C3)}")
    o.calc("u", "e1 + e2").calc("r2", "r1 + u").calc("bb2", "r2 - r1")
    o.calc("e3", "(r1 - (r2 - bb2)) + (u - bb2)")
    o.dd("ddAdd", "rh", "rl", "r2", "e3", "xl", "0.0")
    o.calc("sh", "rh * 0.00390625").calc("sl", "rl * 0.00390625")
    o.dd("ddMul", "s2h", "s2l", "sh", "sl", "sh", "sl")
    o.dd("ddMul", "s3h", "s3l", "s2h", "s2l", "sh", "sl")
    t = f"{hx(taylor[4])} + sh * ({hx(taylor[5])} + sh * ({hx(taylor[6])} + sh * ({hx(taylor[7])} + sh * {hx(taylor[8])})))"
    o.calc("tail", t)
    o.calc("s4", "s2h * s2h")
    o.dd("ddAdd", "p1", "p1l", "sh", "sl", "s2h * 0.5", "s2l * 0.5")
    o.dd("ddMul", "q3", "q3l", "s3h", "s3l", inv6[0], inv6[1])
    o.dd("ddAdd", "p2", "p2l", "p1", "p1l", "q3", "q3l")
    o.dd("ddAdd", "p3", "p3l", "p2", "p2l", "s4 * tail", "0.0")
    ph, pl = "p3", "p3l"
    for i in range(8):
        o.dd("ddMul", f"sq{i}", f"sq{i}l", ph, pl, ph, pl)
        o.dd("ddAdd", f"pw{i}", f"pw{i}l", f"2.0 * {ph}", f"2.0 * {pl}", f"sq{i}", f"sq{i}l")
        ph, pl = f"pw{i}", f"pw{i}l"
    o.dd("ddAdd", "m", None, "1.0", "0.0", ph, pl)
    o.add("storeScale(kk)", "return m")
    emit(o)

    o = Op("expPlain", "e to the power of a double-double with the power of two applied, as a double-double; the low half is left in the cell",
           [("xh", "Float64"), ("xl", "Float64")], "Float64")
    o.calc("m", "expScaled(xh, xl)").calc("lo", "loadLow()").calc("k", "loadScale()")
    o.calc("hi2", "scaleBy(m, k)").calc("lo2", "scaleBy(lo, k)").add("storeLow(lo2)", "return hi2")
    emit(o)

    # the log of a double in [0.7071, 1.4142): 2 atanh((m-1)/(m+1)) as a series in s squared
    cs = [1 / 25.0, 1 / 23.0, 1 / 21.0, 1 / 19.0, 1 / 17.0, 1 / 15.0, 1 / 13.0, 1 / 11.0, 1 / 9.0, 1 / 7.0, 1 / 5.0, 1 / 3.0]
    o = Op("crudeLog", "The natural log of a double from 0.7 to 1.42 to about 2^-52 relative (a series in ((m-1)/(m+1))^2)",
           [("m", "Float64")], "Float64", memory=False)
    o.calc("s", "(m - 1.0) / (m + 1.0)").calc("z", "s * s")
    o.calc("p1", f"{hx(cs[0])} + z * {hx(1 / 27.0)}")
    for i in range(1, len(cs)):
        o.calc(f"p{i + 1}", f"{hx(cs[i])} + z * p{i}")
    o.calc("result", f"2.0 * s * (1.0 + z * p{len(cs)})")
    o.add("return result")
    emit(o)

    # logNormal: log of a double-double whose high half is a positive normal number
    o = Op("logNormal", "The natural log of a double-double whose high half is a normal positive number, as a double-double: the high half is the result, the low half is left in the cell",
           [("xh", "Float64"), ("xl", "Float64")], "Float64",
           lets=["a Float64 1.0 mut", "e Int64 0 mut"])
    o.calc("bits0", "convert.float64BitsToUInt64(xh)")
    o.calc("field", "convert.uint64BitsToInt64((bits0 >> 52) & 2047)")
    o.calc("mbits", "(bits0 & 4503599627370495) | 4607182418800017408")
    o.calc("m", "convert.uint64BitsToFloat64(mbits)")
    o.calc("exponent0", "field - 1023")
    o.add("when m >= 1.4142135623730951 high keep",
          ":high", "calc a := m * 0.5", "calc e := exponent0 + 1", "goto joined",
          ":keep", "calc a := m", "calc e := exponent0", "goto joined",
          ":joined")
    o.calc("al", "scaleBy(xl, 0 - e)")
    o.calc("y0", "crudeLog(a)")
    o.calc("eh", "expScaled(-y0, 0.0)").calc("el", "loadLow()").calc("ek", "loadScale()")
    o.calc("eh2", "scaleBy(eh, ek)").calc("el2", "scaleBy(el, ek)")
    o.dd("ddMul", "ph", "pl", "a", "al", "eh2", "el2")
    o.dd("ddAdd", "dh", "dl", "ph", "pl", "-1.0", "0.0")
    o.calc("corr", "dh - 0.5 * dh * dh")
    o.dd("ddAdd", "rh", "rl", "y0", "0.0", "corr", "dl")
    o.add("when e == 0 plain shifted",
          ":plain", "return rh",
          ":shifted")
    o.calc("ef", "convert.int64ToFloat64(e)")
    o.calc("t1", f"ef * {hx(C1)}").calc("t2", f"ef * {hx(C2)}")
    o.calc("ts", "t1 + t2").calc("tb", "ts - t1").calc("te", "(t1 - (ts - tb)) + (t2 - tb)")
    o.dd("ddAdd", "lh", "ll", "ts", "te", f"ef * {hx(C3)}", "0.0")
    o.dd("ddAdd", "result", None, "lh", "ll", "rh", "rl")
    o.add("return result")
    emit(o)

    o = Op("logDD", "The natural log of a positive double-double, as a double-double: the high half is the result, the low half is left in the cell",
           [("xh", "Float64"), ("xl", "Float64")], "Float64")
    o.calc("field", "convert.uint64BitsToInt64((convert.float64BitsToUInt64(xh) >> 52) & 2047)")
    o.add("when field == 0 subnormal normal",
          ":subnormal")
    o.calc("sh", f"xh * {hx(2.0 ** 200)}").calc("sl", f"xl * {hx(2.0 ** 200)}")
    o.dd("logNormal", "lh", "ll", "sh", "sl")
    o.dd("ddAdd", "ah", "al", "lh", "ll", f"-(200.0 * {hx(C1)})", "0.0")
    o.dd("ddAdd", "bh", None, "ah", "al", f"-(200.0 * {hx(C2)})", f"-(200.0 * {hx(C3)})")
    o.add("return bh", ":normal")
    o.dd("logNormal", "result", None, "xh", "xl")
    o.add("return result")
    emit(o)


ABI: dict[str, tuple[str, str]] = {}


def abi_op(name, doc, cname, inv, lets=()):
    ABI[name] = (cname, inv[0])
    return Op(name, doc, [("value", "Float64")], "Float64", abi=cname, invariant=inv, lets=lets)


def nan_check(o, label):
    """Return a quiet NaN for a NaN argument."""
    o.add(f"when isNotNumber(value) {label}Nan {label}Number", f":{label}Nan", "calc quiet = value + value", "return quiet", f":{label}Number")


def build_hyperbolic():
    # sinh: (e^x - e^-x) / 2 from a double-double e^|x|; e^|x| / 2 from 40 up; x below 2^-27
    o = abi_op("hyperbolicSine", "sinh: the hyperbolic sine, within 0.5001 ulp (correctly rounded but for the rarest cases); +-0 and +-infinity as they are, an overflow +-infinity with ERANGE", "sinh",
               ("sineIsAccurate", "Gives sinh within 0.51 ulp, keeping the sign of zero and infinity"), lets=["argument Float64 0.0 mut"])
    nan_check(o, "s")
    o.calc("magnitude", "magnitudeOf(value)")
    o.add("when magnitude < 0x1p-27 same checkInfinite", ":same", "return value", ":checkInfinite",
          f"when magnitude > {MAXF} same checkLarge", ":checkLarge", "when magnitude >= 40.0 large middle",
          ":large", "calc argument := magnitude", "when magnitude > 1000.0 clamp compute", ":clamp", "calc argument := 1000.0", "goto compute", ":compute")
    o.calc("e0", "expScaled(argument, 0.0)").calc("k", "loadScale()").calc("big", "scaleBy(e0, k - 1)")
    o.add(f"when big > {MAXF} overflowed finish", ":overflowed", "clibrary.setErrno(34)", "goto finish", ":finish")
    o.calc("signedBig", "withSign(big, value)").add("return signedBig", ":middle")
    o.calc("eh", "expPlain(magnitude, 0.0)").calc("el", "loadLow()")
    o.dd("ddDivide", "ih", "il", "1.0", "0.0", "eh", "el")
    o.dd("ddAdd", "dh", None, "eh", "el", "-ih", "-il")
    o.calc("half", "dh * 0.5").calc("signedHalf", "withSign(half, value)").add("return signedHalf")
    emit(o)

    o = abi_op("hyperbolicCosine", "cosh: the hyperbolic cosine, within 0.5001 ulp; +infinity for +-infinity, an overflow +infinity with ERANGE", "cosh",
               ("cosineIsAccurate", "Gives cosh within 0.51 ulp, 1 for 0"), lets=["unity Float64 1.0", "argument Float64 0.0 mut"])
    nan_check(o, "c")
    o.calc("magnitude", "magnitudeOf(value)")
    o.add(f"when magnitude > {MAXF} infinite checkTiny", ":infinite", "return magnitude", ":checkTiny",
          "when magnitude < 0x1p-27 small checkLarge", ":small", "return unity", ":checkLarge",
          "when magnitude >= 40.0 large middle", ":large", "calc argument := magnitude", "when magnitude > 1000.0 clamp compute", ":clamp", "calc argument := 1000.0", "goto compute", ":compute")
    o.calc("e0", "expScaled(argument, 0.0)").calc("k", "loadScale()").calc("big", "scaleBy(e0, k - 1)")
    o.add(f"when big > {MAXF} overflowed finish", ":overflowed", "clibrary.setErrno(34)", "goto finish", ":finish", "return big", ":middle")
    o.calc("eh", "expPlain(magnitude, 0.0)").calc("el", "loadLow()")
    o.dd("ddDivide", "ih", "il", "1.0", "0.0", "eh", "el")
    o.dd("ddAdd", "dh", None, "eh", "el", "ih", "il")
    o.calc("half", "dh * 0.5").add("return half")
    emit(o)

    o = abi_op("hyperbolicTangent", "tanh: the hyperbolic tangent, within 0.5001 ulp; +-1 from 22 up", "tanh",
               ("tangentIsAccurate", "Gives tanh within 0.51 ulp, keeping the sign of zero"))
    nan_check(o, "t")
    o.calc("magnitude", "magnitudeOf(value)")
    o.add("when magnitude < 0x1p-27 same checkLarge", ":same", "return value", ":checkLarge",
          "when magnitude >= 22.0 one middle", ":one")
    o.calc("signedOne", "withSign(1.0, value)").add("return signedOne", ":middle")
    o.calc("eh", "expPlain(2.0 * magnitude, 0.0)").calc("el", "loadLow()")
    o.dd("ddAdd", "nh", "nl", "eh", "el", "-1.0", "0.0")
    o.dd("ddAdd", "dh", "dl", "eh", "el", "1.0", "0.0")
    o.dd("ddDivide", "qh", None, "nh", "nl", "dh", "dl")
    o.calc("signed", "withSign(qh, value)").add("return signed")
    emit(o)

    o = abi_op("inverseHyperbolicSine", "asinh: the inverse hyperbolic sine, within 0.5001 ulp: log(|x| + sqrt(x^2 + 1)) in double-double, log(2|x|) from 2^28", "asinh",
               ("asinhIsAccurate", "Gives asinh within 0.51 ulp, keeping the sign of zero and infinity"))
    nan_check(o, "a")
    o.calc("magnitude", "magnitudeOf(value)")
    o.add(f"when magnitude < 0x1p-27 same checkInfinite", ":same", "return value", ":checkInfinite",
          f"when magnitude > {MAXF} same checkLarge", ":checkLarge", "when magnitude >= 0x1p28 large middle", ":large")
    o.dd("logDD", "lh", "ll", "magnitude", "0.0")
    o.dd("ddAdd", "rh", None, "lh", "ll", hx(C1 + C2), hx(C3))
    o.calc("signedLarge", "withSign(rh, value)").add("return signedLarge", ":middle")
    o.dd("ddMul", "ph", "pl", "magnitude", "0.0", "magnitude", "0.0")
    o.dd("ddAdd", "qh", "ql", "ph", "pl", "1.0", "0.0")
    o.dd("ddSquareRoot", "sh", "sl", "qh", "ql")
    o.dd("ddAdd", "wh", "wl", "magnitude", "0.0", "sh", "sl")
    o.dd("logDD", "mh", None, "wh", "wl")
    o.calc("signedMiddle", "withSign(mh, value)").add("return signedMiddle")
    emit(o)

    o = abi_op("inverseHyperbolicCosine", "acosh: the inverse hyperbolic cosine, within 0.5001 ulp; NaN below 1 with EDOM", "acosh",
               ("acoshIsAccurate", "Gives acosh within 0.51 ulp, 0 for 1, NaN below 1"), lets=["nothing Float64 0.0"])
    nan_check(o, "c")
    o.add("when value < 1.0 below checkOne", ":below", "clibrary.setErrno(33)", "calc invalid = convert.uint64BitsToFloat64(9221120237041090560)", "return invalid",
          ":checkOne", "when value == 1.0 zero checkInfinite", ":zero", "return nothing", ":checkInfinite",
          f"when value > {MAXF} same checkLarge", ":same", "return value", ":checkLarge", "when value >= 0x1p28 large middle", ":large")
    o.dd("logDD", "lh", "ll", "value", "0.0")
    o.dd("ddAdd", "rh", None, "lh", "ll", hx(C1 + C2), hx(C3))
    o.add("return rh", ":middle")
    o.calc("t", "value - 1.0")
    o.dd("ddMul", "ph", "pl", "t", "0.0", "t", "0.0")
    o.dd("ddAdd", "qh", "ql", "2.0 * t", "0.0", "ph", "pl")
    o.dd("ddSquareRoot", "sh", "sl", "qh", "ql")
    o.dd("ddAdd", "wh", "wl", "t", "0.0", "sh", "sl")
    o.dd("ddAdd", "uh", "ul", "1.0", "0.0", "wh", "wl")
    o.dd("logDD", "mh", None, "uh", "ul")
    o.add("return mh")
    emit(o)

    o = abi_op("inverseHyperbolicTangent", "atanh: the inverse hyperbolic tangent, within 0.5001 ulp: half the log of (1+x)/(1-x) in double-double; +-1 gives +-infinity with ERANGE, more than 1 NaN with EDOM", "atanh",
               ("atanhIsAccurate", "Gives atanh within 0.51 ulp, keeping the sign of zero; +-infinity at +-1; NaN beyond"))
    nan_check(o, "t")
    o.calc("magnitude", "magnitudeOf(value)")
    o.add("when magnitude > 1.0 beyond checkOne", ":beyond", "clibrary.setErrno(33)", "calc invalid = convert.uint64BitsToFloat64(9221120237041090560)", "return invalid",
          ":checkOne", "when magnitude == 1.0 pole checkTiny", ":pole", "clibrary.setErrno(34)",
          f"calc infinity = convert.uint64BitsToFloat64({INFBITS})", "calc signedInfinity = withSign(infinity, value)", "return signedInfinity",
          ":checkTiny", "when magnitude < 0x1p-27 same middle", ":same", "return value", ":middle")
    o.calc("s1", "1.0 - magnitude").calc("bb", "s1 - 1.0").calc("e", "(1.0 - (s1 - bb)) + ((0.0 - magnitude) - bb)")
    o.dd("ddDivide", "uh", "ul", "2.0 * magnitude", "0.0", "s1", "e")
    o.dd("ddAdd", "vh", "vl", "1.0", "0.0", "uh", "ul")
    o.dd("logDD", "lh", None, "vh", "vl")
    o.calc("half", "lh * 0.5").calc("signed", "withSign(half, value)").add("return signed")
    emit(o)


def build_erf():
    sq = PI.sqrt()
    ts = dd(2 / sq)
    isq = dd(1 / sq)
    o = Op("erfSeries", "erf of a double from 2^-30 to 3 as a double-double, by the series with no cancellation: 2/sqrt(pi) e^(-x^2) times the sum of 2^n x^(2n+1) / (1 3 5 ... (2n+1)); the low half is left in the cell",
           [("x", "Float64")], "Float64",
           lets=["th Float64 0.0 mut", "tl Float64 0.0 mut", "sh Float64 0.0 mut", "sl Float64 0.0 mut", "nf Float64 3.0 mut"])
    o.dd("ddMul", "ph", "pl", "x", "0.0", "x", "0.0")
    o.calc("wh", "2.0 * ph").calc("wl", "2.0 * pl")
    o.set("th", "x").set("sh", "x")
    o.add("calc tl := 0.0", "calc sl := 0.0", "calc nf := 3.0", "goto eachTerm",
          ":eachTerm loop=while max=400", "when th < sh * 0x1p-110 finished term", ":term in=eachTerm")
    o.dd("ddMul", "t1", "t1l", "th", "tl", "wh", "wl")
    o.dd("ddDivide", "t2", "t2l", "t1", "t1l", "nf", "0.0")
    o.dd("ddAdd", "s1", "s1l", "sh", "sl", "t2", "t2l")
    o.set("th", "t2").set("tl", "t2l").set("sh", "s1").set("sl", "s1l").set("nf", "nf + 2.0")
    o.add("goto eachTerm", ":finished")
    o.dd("expPlain", "eh", "el", "-ph", "-pl")
    o.dd("ddMul", "mh", "ml", "sh", "sl", "eh", "el")
    o.dd("ddMul", "rh", None, "mh", "ml", ts[0], ts[1])
    o.add("return rh")
    emit(o)

    o = Op("erfcLarge", "erfc of a double from 3 to 27.3 as a double-double times a power of two, by Laplace's continued fraction evaluated from the bottom: e^(-x^2) / (sqrt(pi) (x + (1/2) / (x + (2/2) / (x + ...)))); the low half and the power are left in their cells",
           [("x", "Float64")], "Float64",
           lets=["th Float64 0.0 mut", "tl Float64 0.0 mut", "kf Float64 0.0 mut"])
    o.calc("depth", "convert.int64ToFloat64(convert.float64ToInt64(6.0 + 240.0 / x))")
    o.set("kf", "depth").set("th", "x")
    o.add("calc tl := 0.0", "goto eachLevel", ":eachLevel loop=while max=400", "when kf < 0.5 finished level", ":level in=eachLevel")
    o.dd("ddDivide", "qh", "ql", "kf * 0.5", "0.0", "th", "tl")
    o.dd("ddAdd", "nh", "nl", "x", "0.0", "qh", "ql")
    o.set("th", "nh").set("tl", "nl").set("kf", "kf - 1.0")
    o.add("goto eachLevel", ":finished")
    o.dd("ddMul", "ph", "pl", "x", "0.0", "x", "0.0")
    o.dd("expScaled", "eh", "el", "-ph", "-pl")
    o.calc("k", "loadScale()")
    o.dd("ddDivide", "dh", "dl", "eh", "el", "th", "tl")
    o.dd("ddMul", "rh", None, "dh", "dl", isq[0], isq[1])
    o.add("storeScale(k)", "return rh")
    emit(o)

    o = abi_op("errorFunction", "erf: the error function, within 0.5001 ulp; +-0 as it is, +-1 for +-infinity", "erf",
               ("erfIsAccurate", "Gives erf within 0.51 ulp, odd, keeping the sign of zero, +-1 from 6 up"))
    nan_check(o, "e")
    o.calc("magnitude", "magnitudeOf(value)")
    o.add("when magnitude < 0x1p-30 tiny checkLarge", ":tiny",
          "when magnitude == 0.0 same scaled", ":same", "return value", ":scaled")
    o.calc("y", "value * 0x1p100").dd("ddMul", "th", None, "y", "0.0", ts[0], ts[1])
    o.calc("small", "scaleBy(th, -100)").add("return small", ":checkLarge",
                                              "when magnitude >= 6.0 saturated checkSmall", ":saturated")
    o.calc("signedOne", "withSign(1.0, value)").add("return signedOne", ":checkSmall", "when magnitude < 3.0 series continued", ":series")
    o.calc("sh", "erfSeries(magnitude)").calc("signedSeries", "withSign(sh, value)").add("return signedSeries", ":continued")
    o.dd("erfcLarge", "ch", "cl", "magnitude")
    o.calc("k", "loadScale()").calc("sch", "scaleBy(ch, k)").calc("scl", "scaleBy(cl, k)")
    o.dd("ddAdd", "rh", None, "1.0", "0.0", "-sch", "-scl")
    o.calc("signedContinued", "withSign(rh, value)").add("return signedContinued")
    emit(o)

    o = abi_op("complementaryErrorFunction", "erfc: 1 - erf, within 0.5001 ulp (an underflow to a subnormal or 0 sets ERANGE); 0 for +infinity, 2 for -infinity", "erfc",
               ("erfcIsAccurate", "Gives erfc within 0.51 ulp, 2 from -6 down, 0 from 27.3 up"), lets=["nothing Float64 0.0", "pair Float64 2.0", "unity Float64 1.0"])
    nan_check(o, "e")
    o.add(f"when value > {MAXF} zero checkMinusInfinity", ":zero", "return nothing", ":checkMinusInfinity",
          f"when value < -{MAXF} twice checkNegative", ":twice", "return pair", ":checkNegative",
          "when value < -6.0 twice checkPositive", ":checkPositive", "when value > 27.25 vanished checkTiny",
          ":vanished", "clibrary.setErrno(34)", "return nothing", ":checkTiny")
    o.calc("magnitude", "magnitudeOf(value)")
    o.add("when magnitude < 0x1p-60 whole checkRange", ":whole", "return unity", ":checkRange", "when magnitude < 3.0 smallRange largeRange", ":smallRange")
    o.dd("erfSeries", "eh", "el", "magnitude")
    o.dd("ddAdd", "ch", "cl", "1.0", "0.0", "-eh", "-el")
    o.add("when value < 0.0 negativeSmall positiveSmall", ":positiveSmall", "return ch", ":negativeSmall")
    o.dd("ddAdd", "rh", None, "2.0", "0.0", "-ch", "-cl")
    o.add("return rh", ":largeRange")
    o.dd("erfcLarge", "lh", "ll", "magnitude")
    o.calc("k", "loadScale()")
    o.add("when value < 0.0 negativeLarge positiveLarge", ":positiveLarge")
    o.calc("scaled", "scaleBy(lh, k)")
    o.add("when scaled < 2.2250738585072014e-308 underflowed finish", ":underflowed", "clibrary.setErrno(34)", "goto finish", ":finish", "return scaled", ":negativeLarge")
    o.calc("sh", "scaleBy(lh, k)").calc("sl", "scaleBy(ll, k)")
    o.dd("ddAdd", "nh", None, "2.0", "0.0", "-sh", "-sl")
    o.add("return nh")
    emit(o)


def horner(o, pre, coefficients, wh, wl):
    """Evaluate a polynomial in w (a double-double) from its coefficients (double-double pairs, highest first)."""
    sh, sl = coefficients[0]
    cur_h, cur_l = sh, sl
    for i, (ch, cl) in enumerate(coefficients[1:]):
        o.dd("ddMul", f"{pre}m{i}", f"{pre}m{i}l", cur_h, cur_l, wh, wl)
        o.dd("ddAdd", f"{pre}a{i}", f"{pre}a{i}l", f"{pre}m{i}", f"{pre}m{i}l", ch, cl)
        cur_h, cur_l = f"{pre}a{i}", f"{pre}a{i}l"
    return cur_h, cur_l


def build_gamma():
    ck = [dd(dfr(BN[2 * k] / (2 * k * (2 * k - 1)))) for k in range(1, KSTIRLING + 1)]
    lnpi = dd(PI.ln())
    hln2pi = dd((2 * PI).ln() / 2)
    pi_dd = dd(PI)

    o = Op("stirling", "ln gamma of a double-double of 24 or more, as a double-double, by Stirling's series: (z - 1/2) ln z - z + (1/2) ln 2 pi plus the Bernoulli terms up to 2^30, where they are dropped; the low half is left in the cell",
           [("zh", "Float64"), ("zl", "Float64")], "Float64")
    o.dd("logDD", "lh", "ll", "zh", "zl")
    o.dd("ddAdd", "ah", "al", "zh", "zl", "-0.5", "0.0")
    o.dd("ddMul", "ph", "pl", "ah", "al", "lh", "ll")
    o.dd("ddAdd", "qh", "ql", "ph", "pl", "-zh", "-zl")
    o.dd("ddAdd", "rh", "rl", "qh", "ql", hln2pi[0], hln2pi[1])
    o.add("when zh < 0x1p30 series done", ":done", "return rh", ":series")
    o.dd("ddDivide", "ih", "il", "1.0", "0.0", "zh", "zl")
    o.dd("ddMul", "wh", "wl", "ih", "il", "ih", "il")
    sh, sl = horner(o, "h", list(reversed(ck)), "wh", "wl")
    o.dd("ddMul", "th", "tl", sh, sl, "ih", "il")
    o.dd("ddAdd", "fh", None, "rh", "rl", "th", "tl")
    o.add("return fh")
    emit(o)

    o = Op("lnGammaPositive", "ln gamma of a positive double-double: Stirling's series from 24, below that the argument shifted up by the product x (x+1) ... (x+n-1) whose log is taken off; the low half is left in the cell",
           [("xh", "Float64"), ("xl", "Float64")], "Float64",
           lets=["i Float64 0.0 mut", "ph Float64 1.0 mut", "pl Float64 0.0 mut"])
    o.add("when xh >= 24.0 direct prepare", ":direct")
    o.dd("stirling", "dh", None, "xh", "xl")
    o.add("return dh", ":prepare")
    o.calc("n", "convert.int64ToFloat64(convert.float64ToInt64(24.0 - xh)) + 1.0")
    o.add("goto eachFactor", ":eachFactor loop=while max=64", "when i >= n shifted factor", ":factor in=eachFactor")
    o.calc("ah0", "xh + i").calc("bb", "ah0 - xh").calc("e0", "(xh - (ah0 - bb)) + (i - bb)").calc("al0", "e0 + xl")
    o.calc("ah", "ah0 + al0").calc("al", "al0 - (ah - ah0)")
    o.dd("ddMul", "mh", "ml", "ph", "pl", "ah", "al")
    o.set("ph", "mh").set("pl", "ml").set("i", "i + 1.0")
    o.add("goto eachFactor", ":shifted")
    o.dd("ddAdd", "zh", "zl", "xh", "xl", "n", "0.0")
    o.dd("stirling", "sh", "sl", "zh", "zl")
    o.dd("logDD", "lh", "ll", "ph", "pl")
    o.dd("ddAdd", "rh", None, "sh", "sl", "-lh", "-ll")
    o.add("return rh")
    emit(o)

    z2h = Z2
    for name, doc, lead, quad, cub, base in (
            ("lgammaNearOne", "ln gamma of 1 + z for z under 2^-16, as a double-double: z (-gamma + z (zeta(2)/2 - z zeta(3)/3 + ...)) to the z^4 term", dd(-EG), Z2 / 2, -Z3 / 3, Z4 / 4),
            ("lgammaNearTwo", "ln gamma of 2 + z for z under 2^-16, as a double-double: z ((1 - gamma) + z ((zeta(2)-1)/2 - z (zeta(3)-1)/3 + ...)) to the z^4 term", dd(1 - EG), (Z2 - 1) / 2, -(Z3 - 1) / 3, (Z4 - 1) / 4)):
        o = Op(name, doc, [("z", "Float64")], "Float64")
        o.calc("inner", f"{hx(quad)} + z * ({hx(cub)} + z * {hx(base)})")
        o.calc("t", "z * inner")
        o.dd("ddAdd", "ah", "al", lead[0], lead[1], "t", "0.0")
        o.dd("ddMul", "rh", None, "ah", "al", "z", "0.0")
        o.add("return rh")
        emit(o)

    for name, kind in (("sinPiSeries", "sin"), ("cosPiSeries", "cos")):
        if kind == "sin":
            co = [dd(D((-1) ** k) / D(math.factorial(2 * k + 1))) for k in range(14)]
        else:
            co = [dd(D((-1) ** k) / D(math.factorial(2 * k))) for k in range(14)]
        o = Op(name, f"{kind}(pi b) for b from 0 to 1/4 as a double-double, by its Taylor series in (pi b)^2; the low half is left in the cell",
               [("b", "Float64")], "Float64")
        o.dd("ddMul", "uh", "ul", "b", "0.0", pi_dd[0], pi_dd[1])
        o.dd("ddMul", "wh", "wl", "uh", "ul", "uh", "ul")
        sh, sl = horner(o, "q", list(reversed(co)), "wh", "wl")
        if kind == "sin":
            o.dd("ddMul", "rh", None, sh, sl, "uh", "ul")
            o.add("return rh")
        else:
            o.add(f"return {sh}")
        emit(o)

    o = Op("sinPi", "sin(pi a) for a from 0 to 1/2 as a double-double (the cosine of the rest from 1/4 up); the low half is left in the cell",
           [("a", "Float64")], "Float64")
    o.add("when a > 0.25 cosine sine", ":cosine")
    o.calc("rest", "0.5 - a").dd("cosPiSeries", "ch", None, "rest")
    o.add("return ch", ":sine")
    o.dd("sinPiSeries", "sh", None, "a")
    o.add("return sh")
    emit(o)

    o = Op("lgammaCore", "ln |gamma(x)| of a finite double that is not 0, a negative whole number, 1 or 2 (x of 2^-70 or less in magnitude: -ln |x|), as a double-double with the low half in the cell and the sign of gamma(x) kept for the callers; for a negative x the reflection formula ln(pi / |sin(pi x)|) - ln gamma(1 - x)",
           [("x", "Float64")], "Float64")
    o.calc("magnitude", "magnitudeOf(x)")
    o.add("when magnitude < 0x1p-70 tiny checkSign", ":tiny")
    o.dd("logDD", "lh", "ll", "magnitude", "0.0")
    o.calc("signBitTiny", "convert.uint64BitsToInt64(convert.float64BitsToUInt64(x) >> 63)")
    o.add("storeSignWork(1 - 2 * signBitTiny)", "storeLow(-ll)", "calc negated = -lh", "return negated", ":checkSign",
          "when x > 0.0 positive negative", ":positive", "storeSignWork(1)")
    o.calc("distanceOne", "magnitudeOf(x - 1.0)")
    o.add("when distanceOne < 0x1p-16 nearOne checkTwo", ":nearOne")
    o.calc("zOne", "x - 1.0").dd("lgammaNearOne", "oh", None, "zOne")
    o.add("return oh", ":checkTwo")
    o.calc("distanceTwo", "magnitudeOf(x - 2.0)")
    o.add("when distanceTwo < 0x1p-16 nearTwo checkHuge", ":nearTwo")
    o.calc("zTwo", "x - 2.0").dd("lgammaNearTwo", "wh", None, "zTwo")
    o.add("return wh", ":checkHuge", "when x >= 0x1p400 huge ordinary", ":huge")
    o.calc("scaled", "x * 0x1p-600")
    o.dd("logDD", "hh", "hl", "x", "0.0")
    o.dd("ddAdd", "mh", "ml", "hh", "hl", "-1.0", "0.0")
    o.dd("ddMul", "ph", "pl", "scaled", "0.0", "mh", "ml")
    o.calc("bigHigh", "scaleBy(ph, 600)").calc("bigLow", "scaleBy(pl, 600)")
    o.add("storeLow(bigLow)", "return bigHigh", ":ordinary")
    o.dd("lnGammaPositive", "gh", None, "x", "0.0")
    o.add("return gh", ":negative")
    o.calc("floored", "floorValue(x + 0.5)")
    o.calc("r", "x - floored").calc("ra", "magnitudeOf(r)")
    o.dd("sinPi", "sh", "sl", "ra")
    o.calc("parity", "convert.float64ToInt64(floored) & 1")
    o.calc("rBit", "convert.uint64BitsToInt64(convert.float64BitsToUInt64(r) >> 63)")
    o.calc("sgn", "(1 - 2 * parity) * (1 - 2 * rBit)")
    o.dd("logDD", "sinLogH", "sinLogL", "sh", "sl")
    o.calc("g1", "1.0 - x").calc("gb", "g1 - 1.0").calc("g2", "(1.0 - (g1 - gb)) + ((0.0 - x) - gb)")
    o.dd("lnGammaPositive", "gh2", "gl2", "g1", "g2")
    o.dd("ddAdd", "th", "tl", lnpi[0], lnpi[1], "-sinLogH", "-sinLogL")
    o.dd("ddAdd", "rh", None, "th", "tl", "-gh2", "-gl2")
    o.add("storeSignWork(sgn)", "return rh")
    emit(o)

    o = abi_op("gammaFunction", "tgamma: the gamma function, within 0.5001 ulp (exp of ln gamma in double-double); a negative whole number gives NaN with EDOM, +-0 gives +-infinity with ERANGE, and an overflow or an underflow sets ERANGE", "tgamma",
               ("gammaIsAccurate", "Gives gamma within 0.51 ulp, exact at whole numbers, with Annex F's poles"))
    nan_check(o, "g")
    o.add(f"when value > {MAXF} same checkMinusInfinity", ":same", "return value", ":checkMinusInfinity",
          f"when value < -{MAXF} invalid checkZero", ":invalid", "clibrary.setErrno(33)", f"calc notNumber = convert.uint64BitsToFloat64({NANBITS})", "return notNumber", ":checkZero",
          "when value == 0.0 pole checkTiny", ":pole", "clibrary.setErrno(34)", "calc infinite = 1.0 / value", "return infinite", ":checkTiny")
    o.calc("magnitude", "magnitudeOf(value)")
    o.add("when magnitude < 0x1p-54 tiny general", ":tiny", "calc reciprocal = 1.0 / value",
          f"when magnitudeOf(reciprocal) > {MAXF} reciprocalOverflow reciprocalFine", ":reciprocalOverflow", "clibrary.setErrno(34)", "return reciprocal",
          ":reciprocalFine", "return reciprocal", ":general", "when value < 0.0 negative positive", ":negative",
          "when magnitude >= 0x1p52 invalid2 checkInteger", ":invalid2", "clibrary.setErrno(33)", f"calc notNumber2 = convert.uint64BitsToFloat64({NANBITS})", "return notNumber2",
          ":checkInteger", "calc truncated = convert.int64ToFloat64(convert.float64ToInt64(magnitude))",
          "when truncated == magnitude invalid2 compute", ":positive", "when value >= 172.0 overflowing compute", ":overflowing", "clibrary.setErrno(34)",
          f"calc infinity = convert.uint64BitsToFloat64({INFBITS})", "return infinity", ":compute")
    o.dd("lgammaCore", "lh", "ll", "value")
    o.calc("sign", "loadSignWork()").calc("signValue", "convert.int64ToFloat64(sign)")
    o.add("when lh < -800.0 underflow exponent", ":underflow", "clibrary.setErrno(34)", "calc signedZero = 0.0 * signValue", "return signedZero", ":exponent")
    o.calc("mh", "expScaled(lh, ll)").calc("k", "loadScale()").calc("r", "scaleBy(mh, k)")
    o.add(f"when r > {MAXF} range checkSmall", ":checkSmall", "when r < 2.2250738585072014e-308 range fine", ":range", "clibrary.setErrno(34)", "goto fine", ":fine")
    o.calc("signed", "r * signValue").add("return signed")
    emit(o)

    o = Op("lgammaValue", "lgamma without the sign's store: ln |gamma(x)| within 0.5001 ulp, the sign of gamma(x) kept in the gamma core's cell; +infinity with ERANGE at 0 and the negative whole numbers, +0 at 1 and 2, +infinity for +-infinity",
           [("value", "Float64")], "Float64", lets=["nothing Float64 0.0"])
    o.add("when isNotNumber(value) notNumber checkInfinite", ":notNumber", "storeSignWork(1)", "calc quiet = value + value", "return quiet", ":checkInfinite")
    o.calc("magnitude", "magnitudeOf(value)")
    o.add(f"when magnitude > {MAXF} infinite checkZero", ":infinite", "storeSignWork(1)", "return magnitude", ":checkZero",
          "when value == 0.0 zero other", ":zero")
    o.calc("signBit", "convert.uint64BitsToInt64(convert.float64BitsToUInt64(value) >> 63)")
    o.add("storeSignWork(1 - 2 * signBit)", "clibrary.setErrno(34)", f"calc poleZero = convert.uint64BitsToFloat64({INFBITS})", "return poleZero",
          ":other", "when value < 0.0 negative positive", ":negative", "when magnitude >= 0x1p52 pole checkInteger", ":pole",
          "storeSignWork(-1)", "clibrary.setErrno(34)", f"calc poleInfinity = convert.uint64BitsToFloat64({INFBITS})", "return poleInfinity", ":checkInteger",
          "calc truncated = convert.int64ToFloat64(convert.float64ToInt64(magnitude))", "when truncated == magnitude pole compute",
          ":positive", "when value == 1.0 zeroResult checkTwo", ":checkTwo", "when value == 2.0 zeroResult compute", ":zeroResult", "storeSignWork(1)", "return nothing", ":compute")
    o.dd("lgammaCore", "lh", None, "value")
    o.add(f"when lh > {MAXF} overflowed finished", ":overflowed", "clibrary.setErrno(34)", "goto finished", ":finished", "return lh")
    emit(o)

    o = abi_op("logGamma", "lgamma: ln |gamma(x)|, within 0.5001 ulp away from its zeros near -2.457, -2.747, ... and accurate to 2^-70 of the function's scale near them; the sign of gamma(x) is kept in a cell of machine.state (what glibc keeps in `signgam`, a data symbol the C library here does not export; lgamma_r gives it)", "lgamma",
               ("lgammaIsAccurate", "Gives ln |gamma| within 0.51 ulp, +infinity at the poles, +0 at 1 and 2"))
    o.calc("result", "lgammaValue(value)").calc("sign", "loadSignWork()").add("storeSignInt(sign)", "return result")
    emit(o)

    ABI["logGammaSigned"] = ("lgamma_r", "lgammaRIsAccurate")
    emit_text = '''op logGammaSigned "lgamma_r: lgamma with the sign of gamma(x) stored through a pointer"
  invariant lgammaRIsAccurate "Gives what lgamma gives and stores the sign of gamma(x) as an int"
  input value Float64 copied
  input signp machine.Address copied
  output Float64
  effect use machine.memory
  uses memoryAccess
  abi library "lgamma_r"
:begin
  calc result = lgammaValue(value)
  calc sign = loadSignWork()
  calc narrow = convert.int64ToInt32(sign)
  machine.storeInt32(signp, narrow)
  return result'''
    raw(emit_text)


FLOAT_NAMES = {}


def build_floats():
    raw('''
op narrowResult "A double as a float, an overflow to infinity (not a trap) with ERANGE"
  input value Float64 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
:begin
  calc magnitude = magnitudeOf(value)
  when magnitude >= 0x1.ffffffp127 large fits
:large
  when magnitude > 1.7976931348623157e308 infinite finite
:finite
  clibrary.setErrno(34)
  goto infinite
:infinite
  calc infinity = convert.uint64BitsToFloat64(9218868437227405312)
  calc signed = withSign(infinity, value)
  calc inf32 = convert.float64ToFloat32(signed)
  return inf32
:fits
  calc narrowed = convert.float64ToFloat32(value)
  return narrowed
''')
    for double_name, (cname, inv) in list(ABI.items()):
        if double_name == "logGammaSigned":
            continue
        fname = double_name + "Float"
        FLOAT_NAMES[cname] = fname
        fc = cname + "f"
        ABI[fname] = (fc, cname + "fIsAccurate")
        raw(f'''op {fname} "{fc}: {cname} of a float, computed in double and rounded once to float, so within 0.5001 ulp of a float"
  invariant {cname}fIsAccurate "Gives {cname} of the float rounded to float, within 0.51 ulp of a float"
  input value Float32 copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "{fc}"
:begin
  calc wide = convert.float32ToFloat64(value)
  calc result = {double_name}(wide)
  calc narrowed = narrowResult(result)
  return narrowed''')
    ABI["logGammaSignedFloat"] = ("lgammaf_r", "lgammafRIsAccurate")
    raw('''op logGammaSignedFloat "lgammaf_r: lgammaf with the sign of gamma(x) stored through a pointer"
  invariant lgammafRIsAccurate "Gives what lgammaf gives and stores the sign of gamma(x) as an int"
  input value Float32 copied
  input signp machine.Address copied
  output Float32
  effect use machine.memory
  uses memoryAccess
  abi library "lgammaf_r"
:begin
  calc wide = convert.float32ToFloat64(value)
  calc result = lgammaValue(wide)
  calc sign = loadSignWork()
  calc narrow = convert.int64ToInt32(sign)
  machine.storeInt32(signp, narrow)
  calc narrowed = narrowResult(result)
  return narrowed''')


TESTS: list[str] = []
NAN = float("nan")
INF = float("inf")

UNIT_INPUTS = {
    "sinh": [0.0, -0.0, 1e-10, 0.5, -1.25, 3.0, 20.0, 39.5, 41.0, 700.0, 710.4, 711.0, INF, -INF, NAN, 5e-324],
    "cosh": [0.0, 1e-9, 0.5, -2.5, 30.0, 45.0, 710.4, 711.0, INF, -INF, NAN],
    "tanh": [0.0, -0.0, 1e-10, 0.3, -0.9, 5.0, 21.9, 22.0, -30.0, INF, -INF, NAN],
    "asinh": [0.0, -0.0, 1e-10, 0.5, -3.0, 100.0, 2.0 ** 28, 1e10, 1e300, INF, -INF, NAN],
    "acosh": [1.0, 1 + 2.0 ** -52, 1.0000001, 1.5, 3.0, 1e5, 2.0 ** 28, 1e300, INF, 0.5, -INF, NAN],
    "atanh": [0.0, -0.0, 1e-10, 0.25, -0.5, 0.9999, 1 - 2.0 ** -53, 1.0, -1.0, 1.5, INF, NAN],
    "erf": [0.0, -0.0, 1e-310, 1e-9, 0.1, 0.5, -1.0, 2.9, 3.0, 4.5, 5.9, 6.0, INF, -INF, NAN],
    "erfc": [0.0, -0.0, 1e-20, 0.1, -0.1, 1.0, 2.9, 3.0, 5.0, 10.0, 26.0, 27.0, 27.3, -5.0, -6.5, INF, -INF, NAN],
    "tgamma": [0.5, 1.0, 2.0, 3.0, 5.5, 10.0, 0.001, 1e-20, -0.5, -1.5, -2.5, -10.5, 100.5, 171.0, 171.7, 172.0, -170.5,
               -180.5, -0.0, 0.0, -1.0, -3.0, INF, -INF, NAN, 1e-310],
    "lgamma": [0.5, 1.0, 2.0, 3.0, 10.5, 100.0, 1e5, 1e20, 1e300, 1e305, 3e305, 0.001, 1e-20, 1e-310, 1.0000001, 0.9999999,
               2.0000001, 1 + 2.0 ** -20, -0.5, -1.5, -2.5, -10.3, -100.5, -0.0, 0.0, -1.0, -5.0, INF, -INF, NAN],
}
FLOAT_UNIT = {
    "sinh": [0.0, 0.5, -3.0, 88.0, 89.5, 100.0],
    "cosh": [0.5, -3.0, 88.0, 89.5],
    "tanh": [0.0, 0.3, -2.0, 12.0],
    "asinh": [0.5, -3.0, 1e20],
    "acosh": [1.0, 1.5, 100.0, 0.5],
    "atanh": [0.25, -0.5, 1.0, 2.0],
    "erf": [0.1, -1.0, 3.5, 6.0],
    "erfc": [0.1, 1.0, 5.0, 10.0, 12.0, -3.0],
    "tgamma": [0.5, 5.5, -1.5, 34.5, 36.0, -3.0],
    "lgamma": [0.5, 10.5, 1e30, 1e37, -2.5, 0.0],
}
BASES = [("sinh", "hyperbolicSine"), ("cosh", "hyperbolicCosine"), ("tanh", "hyperbolicTangent"), ("asinh", "inverseHyperbolicSine"),
         ("acosh", "inverseHyperbolicCosine"), ("atanh", "inverseHyperbolicTangent"), ("erf", "errorFunction"),
         ("erfc", "complementaryErrorFunction"), ("tgamma", "gammaFunction"), ("lgamma", "logGamma")]


def bits64(x: float) -> int:
    import struct
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def literal(x: float) -> str:
    if x != x:
        return f"convert.uint64BitsToFloat64({NANBITS})"
    if x == INF:
        return f"convert.uint64BitsToFloat64({INFBITS})"
    if x == -INF:
        return "convert.uint64BitsToFloat64(18442240474082181120)"
    return hx(x)


def build_tests():
    import cmathspecialtour as ref
    TESTS.append('''op closeBits "Whether a double is within some ulps of the double with the expected bits (the same sign)"
  input expected UInt64 copied
  input actual Float64 copied
  input allowed Int64 copied
  output Bool
:begin
  calc a = convert.uint64BitsToInt64(expected)
  calc b = convert.uint64BitsToInt64(convert.float64BitsToUInt64(actual))
  calc d = math.wrappingSubtractInt64(a, b)
  calc ok = d >= 0 - allowed && d <= allowed
  return ok''')
    TESTS.append('''op sameBits "Whether a double has exactly the expected bits"
  input expected UInt64 copied
  input actual Float64 copied
  output Bool
:begin
  calc same = convert.float64BitsToUInt64(actual) == expected
  return same''')
    TESTS.append('''op storeScratch "The address of an int cell in this module's part of machine.state, cleared"
  output machine.Address
  effect use machine.memory
  uses memoryAccess
:begin
  cell = kernel.stateAt(24608)
  machine.storeInt64(cell, 0)
  return cell''')
    for base, opname in BASES:
        cname, inv = ABI[opname]
        t = [f'test {base}Test "{cname} and {cname}f give the correctly rounded value (within 1 ulp for double, exactly for float) and Annex F\'s special cases"',
             f"  verifies {opname} {inv}",
             f"  verifies {opname}Float {ABI[opname + 'Float'][1]}"]
        if base == "lgamma":
            t += ["  verifies logGammaSigned lgammaRIsAccurate", "  verifies logGammaSignedFloat lgammafRIsAccurate"]
        t += ["  effect use machine.memory", "  uses memoryAccess", ":begin"]
        n = 0
        for x in UNIT_INPUTS[base]:
            e = ref.expected(base, x)
            n += 1
            t.append(f"  calc r{n} = {opname}({literal(x)})")
            t += check_lines(f"r{n}", e, False, n)
            if base == "lgamma":
                if x != x or math.isinf(x):
                    m = 1
                elif x == 0:
                    m = ref.lgamma_sign(x)
                elif x < 0 and x == math.floor(x):
                    m = -1
                else:
                    m = ref.lgamma_sign(x)
                t += [f"  cell{n} = storeScratch()", f"  calc q{n} = logGammaSigned({literal(x)}, cell{n})"]
                t += check_lines(f"q{n}", e, False, n)
                t += [f"  calc s{n} = machine.loadInt32(cell{n})", f"  test.assertTrue(s{n} == {m})"]
        for x in FLOAT_UNIT[base]:
            n += 1
            xf = ref.to_float32(x)
            e = ref.expected(base, xf, True)
            t.append(f"  calc f{n} = {opname}Float(convert.float64ToFloat32({literal(xf)}))")
            t.append(f"  calc g{n} = convert.float32ToFloat64(f{n})")
            t += check_lines(f"g{n}", e, True, n)
            if base == "lgamma":
                m = -1 if xf < 0 and xf == math.floor(xf) else 1 if xf != xf or math.isinf(xf) else ref.lgamma_sign(xf)
                t += [f"  cell{n} = storeScratch()", f"  calc h{n} = logGammaSignedFloat(convert.float64ToFloat32({literal(xf)}), cell{n})",
                      f"  calc i{n} = convert.float32ToFloat64(h{n})"]
                t += check_lines(f"i{n}", e, True, n)
                t += [f"  calc s{n} = machine.loadInt32(cell{n})", f"  test.assertTrue(s{n} == {m})"]
        t.append("  return")
        TESTS.append("\n".join(t))


def check_lines(name, e, single, n):
    if e != e:
        return [f"  test.assertTrue(isNotNumber({name}))"]
    exact = single or math.isinf(e) or e == 0
    fn = "sameBits" if exact else "closeBits"
    extra = "" if exact else ", 1"
    return [f"  calc ok{name} = {fn}({bits64(e)}, {name}{extra})", f"  test.assertTrue(ok{name})"]


def main():
    build_small()
    build_dd()
    build_exp_log()
    for name in ("build_hyperbolic", "build_erf", "build_gamma", "build_floats", "build_tests"):
        fn = globals().get(name)
        if fn:
            fn()
    text = HEADER + "\n" + "\n\n".join(OPS) + "\n"
    tests = globals().get("TESTS")
    if tests:
        text += "\n@tests\n\n" + "\n\n".join(tests) + "\n"
    with open(os.path.join(HERE, "cmathspecial.dsl"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("cmathspecial.dsl:", text.count("\n"), "lines")


if __name__ == "__main__":
    main()
