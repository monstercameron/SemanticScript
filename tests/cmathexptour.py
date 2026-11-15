"""A program that calls the runtime's math.h exponentials, logarithms, pow, cbrt and hypot through `ffi` and prints
what each gives, for the double forms and the f-suffixed float forms (module cmathexp).

tests/test_c_cmathexp.py builds it as an executable with no C library and compares what it prints with the correctly
rounded values `expected()` computes here (Decimal at 110 digits, with C99 Annex F's special values written out
independently of the implementation). On Linux, where `refined run` calls glibc, it also compares the two.
"""
from __future__ import annotations

import math
import os
import random
import struct
import sys
from decimal import Decimal, getcontext

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "docs", "refined-examples", "stage0", "tools"))

getcontext().prec = 110
getcontext().Emax = 999999999
getcontext().Emin = -999999999

INF = math.inf
NAN = math.nan
MAXD = 1.7976931348623157e308
UNARY = ["exp", "exp2", "expm1", "log", "log2", "log10", "log1p", "cbrt"]
BINARY = ["pow", "hypot"]
NAMES = UNARY + BINARY
FLOAT_NAMES = [n + "f" for n in NAMES]


def bits(x: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def f32(x: float) -> float:
    try:
        return struct.unpack("<f", struct.pack("<f", x))[0]
    except OverflowError:
        return math.copysign(INF, x)


def _spread(rng, lo_exp, hi_exp, n):
    """n doubles of both signs whose binary exponents are spread between lo_exp and hi_exp."""
    out = []
    for _ in range(n):
        e = rng.randint(lo_exp, hi_exp)
        out.append(math.ldexp(1 + rng.random(), e) * rng.choice((1, -1)))
    return out


def double_points(name: str) -> list:
    rng = random.Random(f"cmathexp-{name}")
    specials = [0.0, -0.0, 1.0, -1.0, INF, -INF, NAN, 5e-324, -5e-324, 2.2250738585072014e-308, MAXD, -MAXD, 0.5,
                -0.5, 2.0, 3.0, 10.0, 1e-10, 0.1]
    if name == "exp":
        return specials + [709.782712893384, 709.79, 710.0, 700.0, -745.1332191019411, -745.14, -744.4, -708.5, -708.4,
                           1e-300, 36.04365338911715, 0.34657359027997264, 1e-17] + \
            [rng.uniform(-746, 710) for _ in range(70)] + [rng.uniform(-3, 3) for _ in range(30)]
    if name == "exp2":
        return specials + [1023.9999999999999, 1024.0, -1074.0, -1075.0, -1022.0, -1023.5, 0.25, 1e-300] + \
            [rng.uniform(-1080, 1024) for _ in range(70)] + [rng.uniform(-3, 3) for _ in range(30)]
    if name == "expm1":
        return specials + [709.782712893384, 710.0, -40.0, -37.5, -36.0, 1e-17, -1e-17, 0.34657359027997264, 1.0e-5] + \
            [rng.uniform(-40, 710) for _ in range(40)] + [rng.uniform(-1, 1) for _ in range(40)] + \
            _spread(rng, -60, -2, 20)
    if name in ("log", "log2", "log10"):
        base = [abs(v) for v in _spread(rng, -1074, 1023, 60)] + [abs(v) for v in _spread(rng, -3, 3, 40)]
        return specials + [1.0000001, 0.9999999, 1.0 + 2.0 ** -52, 1.0 - 2.0 ** -53, 1024.0, 1000.0, 1e22, 1e-5,
                           8.0, 0.125] + base
    if name == "log1p":
        return specials + [-0.9999999, -0.99, 1e-300, 1e-17, -1e-17, 1e10, 1e300, -0.5, 0.41421356237309503,
                           -0.2928932188134524] + [rng.uniform(-1, 1) for _ in range(40)] + \
            [abs(v) for v in _spread(rng, -60, 60, 40)] + [-abs(v) for v in _spread(rng, -60, -1, 10)]
    if name == "cbrt":
        return specials + [27.0, -27.0, 8.0, 1e300, -1e300, 0.001, 1e-300, 64.0] + _spread(rng, -1074, 1023, 70) + \
            _spread(rng, -8, 8, 30)
    raise KeyError(name)


def pair_points(name: str) -> list:
    rng = random.Random(f"cmathexp-{name}")
    sp = [0.0, -0.0, 1.0, -1.0, INF, -INF, NAN, 2.0, -2.0, 0.5, -0.5, 3.0, 10.0, 0.1, MAXD, 5e-324, 1e-300, -3.0]
    pts = []
    for a in sp:
        for b in (0.0, -0.0, 1.0, -1.0, 2.0, -3.0, 0.5, INF, -INF, NAN, 1e300, 1075.0, -1075.0):
            pts.append((a, b))
    if name == "pow":
        pts += [(2.0, 10.0), (-2.0, 3.0), (-2.0, 4.0), (-8.0, 1.0 / 3), (10.0, 308.0), (10.0, 309.0), (10.0, -323.0),
                (0.5, 1074.0), (0.5, 1075.0), (2.0, -1074.0), (2.0, -1075.0), (1.0000001, 1e7), (1.5, 100.0),
                (7.0, 2.0), (-7.0, -3.0), (0.1, 20.0), (9.0, 0.5), (1e-300, 1.5), (1e300, 0.5), (2.0, 0.5),
                (-0.0, -3.0), (-0.0, -2.0), (-0.0, 3.0), (0.0, 2.5), (-INF, 3.0), (-INF, -3.0), (-INF, 2.0),
                (1.0 + 2.0 ** -52, 2.0 ** 52), (-1.0 - 2.0 ** -52, 2.0 ** 53), (0.999999, -1e9)]
        pts += [(abs(v), rng.uniform(-30, 30)) for v in _spread(rng, -10, 10, 60)]
        pts += [(rng.uniform(0.5, 2.0), rng.uniform(-700, 700)) for _ in range(30)]
        pts += [(-rng.uniform(0.5, 20.0), float(rng.randint(-40, 40))) for _ in range(20)]
    else:
        pts += [(3.0, 4.0), (-5.0, 12.0), (1e300, 1e300), (1e-300, 1e-300), (5e-324, 5e-324), (1.0, 1e-20),
                (0.1, 0.2), (MAXD, MAXD), (MAXD, 1.0), (1e308, 1e307), (1e-310, 1e-310), (3e-320, 4e-320),
                (1.0, 2.0 ** -27), (1.0, 2.0 ** -26)]
        pts += [(a, b) for a, b in zip(_spread(rng, -1074, 1023, 40), _spread(rng, -1074, 1023, 40))]
        pts += [(a, b) for a, b in zip(_spread(rng, -5, 5, 40), _spread(rng, -5, 5, 40))]
    return pts


def float_points(name: str) -> list:
    rng = random.Random(f"cmathexp-f-{name}")
    sp = [0.0, -0.0, 1.0, -1.0, INF, -INF, NAN, 1e-45, -1e-45, 1.1754943508222875e-38, 3.4028234663852886e38,
          -3.4028234663852886e38, 0.5, 2.0, 3.0, 10.0, 0.1]
    if name in UNARY:
        pts = [f32(v) for v in sp]
        if name in ("exp", "expm1"):
            pts += [f32(v) for v in (88.72283, 88.73, 89.0, -87.3, -103.9, -104.0, -17.3, 1e-9)] + \
                [f32(rng.uniform(-105, 89)) for _ in range(30)]
        elif name == "exp2":
            pts += [f32(v) for v in (127.99999, 128.0, -149.0, -150.0, -126.0)] + \
                [f32(rng.uniform(-152, 128)) for _ in range(30)]
        elif name == "cbrt":
            pts += [f32(v) for v in (27.0, -27.0, 1e30, 1e-30)] + [f32(v) for v in _spread(rng, -148, 127, 30)]
        elif name == "log1p":
            pts += [f32(v) for v in (-0.99999, 1e-9, 1e30)] + [f32(rng.uniform(-1, 3)) for _ in range(30)]
        else:
            pts += [f32(v) for v in (1.0000001, 0.9999999, 1000.0, 8.0)] + \
                [f32(abs(v)) for v in _spread(rng, -149, 127, 30)]
        return pts
    sp2 = [0.0, -0.0, 1.0, -1.0, INF, -INF, NAN, 2.0, -2.0, 0.5, 3.0, 10.0, 3.4028234663852886e38, 1e-45]
    pts = [(a, b) for a in sp2 for b in (0.0, -0.0, 1.0, -1.0, 2.0, 0.5, -3.0, INF, -INF, NAN, 100.0)]
    if name == "pow":
        pts += [(2.0, 10.0), (-2.0, 3.0), (2.0, 127.0), (2.0, 128.0), (2.0, -149.0), (2.0, -150.0), (10.0, 38.0),
                (10.0, 39.0), (1.0000001, 1e6), (7.0, 2.0), (9.0, 0.5)]
        pts += [(f32(abs(v)), f32(rng.uniform(-20, 20))) for v in _spread(rng, -6, 6, 30)]
    else:
        pts += [(3.0, 4.0), (1e30, 1e30), (1e-30, 1e-30), (1e-45, 1e-45), (3e38, 3e38), (1.0, 1e-8), (0.1, 0.2)]
        pts += [(f32(a), f32(b)) for a, b in zip(_spread(rng, -70, 60, 30), _spread(rng, -70, 60, 30))]
    return [(f32(a), f32(b)) for a, b in pts]


# ---------------------------------------------------------------- the reference: C99 Annex F + exact rounding

def _is_int(y: float):
    """(is a whole number, is odd) for a finite double."""
    if abs(y) >= 2.0 ** 53:
        return True, False
    return y == math.floor(y), int(y) % 2 == 1 if y == math.floor(y) else False


def _to_float(v: Decimal) -> float:
    return float(v)


def ref1(name: str, x: float) -> float:
    """The correctly rounded value of a one-argument function (C99 Annex F for the special values)."""
    ln2 = Decimal(2).ln()
    if math.isnan(x):
        return NAN
    if name == "exp":
        if x == INF:
            return INF
        if x == -INF:
            return 0.0
        if x > 720:
            return INF
        if x < -760:
            return 0.0
        return _to_float(Decimal(x).exp())
    if name == "exp2":
        if x == INF:
            return INF
        if x == -INF:
            return 0.0
        if x >= 1100:
            return INF
        if x < -1100:
            return 0.0
        return _to_float((Decimal(x) * ln2).exp())
    if name == "expm1":
        if x == INF:
            return INF
        if x == -INF:
            return -1.0
        if x > 720:
            return INF
        if x < -60:
            return -1.0
        if abs(x) < 1e-40:
            return x
        return _to_float(Decimal(x).exp() - 1)
    if name in ("log", "log2", "log10"):
        if x == 0:
            return -INF
        if x < 0:
            return NAN
        if x == INF:
            return INF
        d = Decimal(x)
        if name == "log":
            v = d.ln()
        elif name == "log2":
            v = d.ln() / ln2
        else:
            v = d.log10()
        return _to_float(v)
    if name == "log1p":
        if x == -1:
            return -INF
        if x < -1:
            return NAN
        if x == INF:
            return INF
        if abs(x) < 1e-40:
            return x
        return _to_float((1 + Decimal(x)).ln())
    if name == "cbrt":
        if x == 0 or math.isinf(x):
            return x
        a = abs(Decimal(x))
        v = (a.ln() / 3).exp()
        for _ in range(4):
            v = v - (v ** 3 - a) / (3 * v * v)
        r = _to_float(v)
        return -r if x < 0 else r
    raise KeyError(name)


def ref2(name: str, x: float, y: float) -> float:
    if name == "hypot":
        if math.isinf(x) or math.isinf(y):
            return INF
        if math.isnan(x) or math.isnan(y):
            return NAN
        return _to_float((Decimal(x) ** 2 + Decimal(y) ** 2).sqrt())
    if y == 0:
        return 1.0
    if x == 1:
        return 1.0
    if math.isnan(x) or math.isnan(y):
        return NAN
    if math.isinf(y):
        if abs(x) == 1:
            return 1.0
        return INF if (abs(x) > 1) == (y > 0) else 0.0
    whole, odd = _is_int(y)
    if x == 0:
        if y < 0:
            return math.copysign(INF, x) if odd else INF
        return x if odd else 0.0
    if math.isinf(x):
        if x > 0:
            return 0.0 if y < 0 else INF
        if y < 0:
            return -0.0 if odd else 0.0
        return -INF if odd else INF
    if x < 0 and not whole:
        return NAN
    z = Decimal(y) * abs(Decimal(x)).ln()
    if z > 800:
        v = INF
    elif z < -800:
        v = 0.0
    else:
        v = _to_float(z.exp())
    return -v if (x < 0 and odd) else v


def ulps(a: float, b: float, single: bool = False) -> int:
    """The distance in units in the last place between two values (NaNs equal, signed zeros equal, infinities as
    the next value past the largest)."""
    if math.isnan(a) or math.isnan(b):
        return 0 if math.isnan(a) and math.isnan(b) else 1 << 60
    if a == b:
        return 0

    def key(v):
        if single:
            n = struct.unpack("<I", struct.pack("<f", v))[0]
            return -(n & 0x7FFFFFFF) if n >> 31 else n
        n = bits(v)
        return -(n & 0x7FFFFFFFFFFFFFFF) if n >> 63 else n
    return abs(key(a) - key(b))


# ---------------------------------------------------------------- the program

def _dsl() -> str:
    caps, bindings, ops, body, uses = [], [], [], [], []
    for cname in NAMES + FLOAT_NAMES:
        caps.append(f'capability {cname}Symbol "Authority to bind the C function {cname}" load ffi.symbols "{cname}"')
        uses.append(f"  uses {cname}Symbol")
    for cname in NAMES:
        unary = cname in UNARY
        kind = "Double" if unary else "Pair"
        # the double sweep
        pts = double_points(cname) if unary else pair_points(cname)
        lets, lines = [], []
        for i, p in enumerate(pts):
            if unary:
                lets.append(f"  let p{i}Bits UInt64 {bits(p)}")
                lines.append(f"  read{i}: v{i} = convert.uint64BitsToFloat64(p{i}Bits)\n"
                             f"  call{i}: r{i} = *callee(v{i})\n  show{i}: sayDouble(r{i})")
            else:
                lets.append(f"  let l{i}Bits UInt64 {bits(p[0])}\n  let r{i}Bits UInt64 {bits(p[1])}")
                lines.append(f"  readL{i}: a{i} = convert.uint64BitsToFloat64(l{i}Bits)\n"
                             f"  readR{i}: b{i} = convert.uint64BitsToFloat64(r{i}Bits)\n"
                             f"  call{i}: r{i} = *callee(a{i}, b{i})\n  show{i}: sayDouble(r{i})")
        ops.append(f'op sweep{cname.capitalize()} "Call {cname} at its tour points and write what it gives"\n'
                   f"  input callee {kind}Function copied\n  effect write console.stdout\n  uses stdoutWriter\n"
                   + "\n".join(lets) + "\n:begin\n" + "\n".join(lines) + "\n  return\n")
        body.append(f'  bind{cname}: {cname}Fn = {kind}Binding.bind(libc, {cname}Name="{cname}") ? failed\n'
                    f'  run{cname}: sweep{cname.capitalize()}({cname}Fn)')
        # the float sweep
        fpts = float_points(cname)
        lets, lines = [], []
        for i, p in enumerate(fpts):
            if unary:
                lets.append(f"  let p{i}Bits UInt64 {bits(p)}")
                lines.append(f"  read{i}: w{i} = convert.uint64BitsToFloat64(p{i}Bits)\n"
                             f"  narrow{i}: v{i} = convert.float64ToFloat32(w{i})\n"
                             f"  call{i}: r{i} = *callee(v{i})\n  widen{i}: d{i} = convert.float32ToFloat64(r{i})\n"
                             f"  show{i}: sayDouble(d{i})")
            else:
                lets.append(f"  let l{i}Bits UInt64 {bits(p[0])}\n  let r{i}Bits UInt64 {bits(p[1])}")
                lines.append(f"  readL{i}: wa{i} = convert.uint64BitsToFloat64(l{i}Bits)\n"
                             f"  readR{i}: wb{i} = convert.uint64BitsToFloat64(r{i}Bits)\n"
                             f"  narrowL{i}: a{i} = convert.float64ToFloat32(wa{i})\n"
                             f"  narrowR{i}: b{i} = convert.float64ToFloat32(wb{i})\n"
                             f"  call{i}: r{i} = *callee(a{i}, b{i})\n  widen{i}: d{i} = convert.float32ToFloat64(r{i})\n"
                             f"  show{i}: sayDouble(d{i})")
        ops.append(f'op sweep{cname.capitalize()}f "Call {cname}f at its tour points and write what it gives, as a double"\n'
                   f"  input callee Single{kind}Function copied\n  effect write console.stdout\n  uses stdoutWriter\n"
                   + "\n".join(lets) + "\n:begin\n" + "\n".join(lines) + "\n  return\n")
        body.append(f'  bind{cname}f: {cname}fFn = Single{kind}Binding.bind(libc, {cname}fName="{cname}f") ? failed\n'
                    f'  run{cname}f: sweep{cname.capitalize()}f({cname}fFn)')
    return f'''module cmathexptour "Call the runtime's math.h functions through ffi and print what each gives"
  path cmathexptour
  imports standard.console standard.ffi standard.convert
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

capability cLibrary "Authority to load the C library and nothing else" load ffi.libraries "c"

{chr(10).join(c + chr(10) for c in caps)}
optype DoubleFunction "double f(double)"
  input value Float64 copied
  output Float64

optype PairFunction "double f(double, double)"
  input left Float64 copied
  input right Float64 copied
  output Float64

optype SingleDoubleFunction "float f(float)"
  input value Float32 copied
  output Float32

optype SinglePairFunction "float f(float, float)"
  input left Float32 copied
  input right Float32 copied
  output Float32

instance DoubleBinding "Binds a C function of a double" ffi.Function DoubleFunction

instance PairBinding "Binds a C function of two doubles" ffi.Function PairFunction

instance SingleDoubleBinding "Binds a C function of a float" ffi.Function SingleDoubleFunction

instance SinglePairBinding "Binds a C function of two floats" ffi.Function SinglePairFunction

op sayDouble "Write a double on a line, as repr writes it"
  input value Float64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  write: console.writeFloatLine(value) ~
  return

{chr(10).join(ops)}
op main "Open the C library, call each function at its points, and write what it gives"
  output ExitCode
  effect load ffi.libraries
  effect load ffi.symbols
  effect write console.stdout
  uses cLibrary
{chr(10).join(uses)}
  uses stdoutWriter
  let okCode ExitCode 0
  let failCode ExitCode 1
:begin
  openIt: libc = ffi.open(cName="c") ? failedOpen
{chr(10).join(body)}
  closeIt: ffi.close(libc)
  return okCode
:failed
  closeFailed: ffi.close(libc)
  return failCode
:failedOpen
  return failCode
'''


def write_project(folder: str) -> None:
    """The project: build.sem and cmathexptour.sem, generated from the DSL above."""
    from semgen import Generator, Module, Program
    from caselib import allows_rows
    dsl = _dsl()
    prog = Program()
    m = Module("cmathexptour")
    prog.modules["cmathexptour"] = m
    g = Generator(prog, m)
    g.declare(dsl)
    g.parse(dsl)
    sem, _tests = g.render(["# The runtime's math.h functions through ffi (tests/cmathexptour.py)."], None)
    owner, target, lines = "", "", []
    for line in sem.split("\n"):
        parts = line.split()
        if len(parts) == 3 and parts[1] == "in":
            owner = parts[2]
        if len(parts) == 3 and parts[1] == "invokes":
            target = parts[2]
        if len(parts) == 3 and parts[1] == "ownedBy" and parts[2] == "none" and target == "ffi.open":
            line = line.replace("ownedBy none", f"ownedBy {owner}")
        lines.append(line)
    sem = "\n".join(lines)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "cmathexptour.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(sem)
    rows = ["tourProject is project", 'tourProject purpose "Call the runtime\'s math.h functions through ffi"',
            "tourProject target console", 'tourProject version "0.1.0"', "tourProject language refined 1",
            "tourProject standardLibrary 1", *allows_rows("tourProject", [sem]), "tourProject requires none",
            "tourProject includesModule cmathexptour", "tourProject entry cmathexptour.main"]
    with open(os.path.join(folder, "build.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")


# ---------------------------------------------------------------- what is printed

def expected() -> list:
    """Per function: its double sweep then its float sweep, each value the correctly rounded one as a double's repr."""
    out = []
    for cname in NAMES:
        if cname in UNARY:
            out += [ref1(cname, x) for x in double_points(cname)]
            out += [f32(ref1(cname, x)) for x in float_points(cname)]
        else:
            out += [ref2(cname, a, b) for a, b in pair_points(cname)]
            out += [f32(ref2(cname, a, b)) for a, b in float_points(cname)]
    return out


def layout() -> list:
    """For each printed line: (function, is a float form), in the order the program prints them."""
    out = []
    for cname in NAMES:
        n = len(double_points(cname)) if cname in UNARY else len(pair_points(cname))
        out += [(cname, False)] * n
        out += [(cname, True)] * len(float_points(cname))
    return out
