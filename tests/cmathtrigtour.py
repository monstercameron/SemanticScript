"""A program that calls the runtime's trigonometric functions through `ffi` (D-153) and prints what each gives.

tests/test_c_cmathtrig.py builds it with the runtime in SemanticScript and no C library, and compares what it prints
with an exact reference (semanticscript/runtime/tools/cmathtriggen.py: decimals and Taylor series, with pi from
Machin's formula). It binds from `ffi.open("c")`: sin, cos, tan, asin, acos, atan and atan2 and their f forms. Each
is called on a list of special values (signed zeros, infinities, NaN, subnormals, the largest and smallest numbers, the
boundaries of the reductions) and on deterministic sweeps: a 64-bit generator makes the bits of each argument, with an
exponent drawn from a range (`SWEEPS`), so that arguments reach from 2^-60 to the largest double, the reduction by
Payne and Hanek included. `inputs(name)` gives the same arguments in Python.
"""
from __future__ import annotations

import math
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "docs", "refined-examples", "stage0", "tools"))

ONE = ["sin", "cos", "tan", "asin", "acos", "atan"]
ONE_F = [n + "f" for n in ONE]
TWO = ["atan2"]
TWO_F = ["atan2f"]

# the arguments a function is called with besides the sweeps
SPECIALS = [0.0, -0.0, 5e-324, -5e-324, 2.2250738585072014e-308, 1e-300, 1e-10, -1e-10, 7.450580596923828e-09,
            1.4901161193847656e-08, 0.1, -0.1, 0.5, -0.5, 0.7853981633974483, 0.7853981633974484, 1.0, -1.0,
            0.9999999999999999, -0.9999999999999999, 1.0000000000000002, 1.5, 1.5707963267948966, -1.5707963267948966,
            2.0, 3.141592653589793, 6.283185307179586, 10.0, 100.0, 1599999.9999999998, 1600000.0, 1600001.0,
            105414357.0, 1e9, 1e15, 1e22, 1.7976931348623157e308, -1.7976931348623157e308, math.inf, -math.inf,
            math.nan, 6381956970095103.0 * 2.0 ** 797, 8.98846567431158e307, 1e300, -1e300,
            5.319372648326541e+255]  # tan near a pole after Payne and Hanek: 0.36 ulp here, glibc's is 14 ulp off
PAIR_SPECIALS = [(0.0, 0.0), (0.0, -0.0), (-0.0, 0.0), (-0.0, -0.0), (0.0, 1.0), (0.0, -1.0), (-0.0, 1.0), (-0.0, -1.0),
                 (1.0, 0.0), (1.0, -0.0), (-1.0, 0.0), (-1.0, -0.0), (math.inf, math.inf), (math.inf, -math.inf),
                 (-math.inf, math.inf), (-math.inf, -math.inf), (math.inf, 1.0), (-math.inf, -1.0), (1.0, math.inf),
                 (1.0, -math.inf), (-1.0, math.inf), (-1.0, -math.inf), (0.0, math.inf), (0.0, -math.inf),
                 (-0.0, math.inf), (-0.0, -math.inf), (math.inf, 0.0), (math.inf, math.nan), (math.nan, 1.0),
                 (1.0, math.nan), (math.nan, math.nan), (1.0, 2.0), (-1.0, -2.0), (2.0, -1.0), (-2.0, 1.0),
                 (1.0, 1.0), (1.0, -1.0), (5e-324, 1.0), (1.0, 5e-324), (5e-324, 5e-324), (1e-310, 3e-310),
                 (1e300, 1e-300), (1e-300, 1e300), (1e300, 3e299), (1.7976931348623157e308, 1.7976931348623157e308),
                 (1.7976931348623157e308, -1.0), (3.0, 4.0), (-3.0, 4.0), (4.0, -3.0), (1e-5, 1.0), (1.0, 1e-5),
                 (1.0, 1e20), (1e20, 1.0)]

# the specials a float function is called with: those a float holds (a double too large for a float does not convert),
# and floats of their own
SINGLE_SPECIALS = [x for x in SPECIALS if math.isnan(x) or math.isinf(x) or x == 0 or 1.2e-38 <= abs(x) <= 3.4e38] +     [1.401298464324817e-45, -1.401298464324817e-45, 1.1754943508222875e-38, 3.4028234663852886e38,
     -3.4028234663852886e38, 16777216.0, 1e-30]

# (smallest biased exponent, how many exponents, arguments) of the sweeps of each kind of function
SWEEPS = {
    "sin": [(1023 - 40, 40, 60), (1023, 8, 60), (1023 + 8, 12, 40), (1023 + 20, 8, 40), (1023 + 28, 990, 80)],
    "asin": [(1023 - 60, 60, 80), (1022, 2, 40)],
    "atan": [(1023 - 60, 60, 60), (1023, 70, 60)],
    "atan2": [(1023 - 40, 80, 80), (1023 - 400, 800, 40)],
}
KIND = {"sin": "sin", "cos": "sin", "tan": "sin", "asin": "asin", "acos": "asin", "atan": "atan", "atan2": "atan2"}

MULTIPLIER = 6364136223846793005
INCREMENT = 1442695040888963407
MASK = (1 << 64) - 1


def _bits(x: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def _double(bits: int) -> float:
    return struct.unpack("<d", struct.pack("<Q", bits))[0]


def _argument(state: int, base: int, span: int, single: bool) -> float:
    sign = state >> 63
    exponent = base + ((state >> 40) & 0xFFFFFF) % span
    mantissa = state & ((1 << 52) - 1)
    if single:
        mantissa &= ~((1 << 29) - 1)
        if exponent < 897 or exponent > 1150:
            exponent = 897 + exponent % 254
    return _double((sign << 63) | (exponent << 52) | mantissa)


def sweep_arguments(kind: str, single: bool) -> list[float]:
    """The arguments the sweeps of one kind of function make, in order (a pair takes two draws)."""
    out = []
    state = 12345
    for base, span, count in SWEEPS[kind]:
        for _ in range(count):
            state = (state * MULTIPLIER + INCREMENT) & MASK
            out.append(_argument(state, base, span, single))
    return out


def sweep_pairs(single: bool) -> list[tuple[float, float]]:
    out = []
    state = 12345
    for base, span, count in SWEEPS["atan2"]:
        for _ in range(count):
            state = (state * MULTIPLIER + INCREMENT) & MASK
            y = _argument(state, base, span, single)
            state = (state * MULTIPLIER + INCREMENT) & MASK
            out.append((y, _argument(state, base, span, single)))
    return out


def _fits(x: float) -> bool:
    return math.isnan(x) or math.isinf(x) or x == 0 or 1.2e-38 <= abs(x) <= 3.4e38


def narrow(x: float) -> float:
    """A double rounded to a float (the specials of the float forms)."""
    try:
        return struct.unpack("<f", struct.pack("<f", x))[0]
    except OverflowError:
        return math.copysign(math.inf, x)


def inputs(name: str) -> list:
    """The arguments the tour calls `name` with: floats for the f forms (as the doubles that hold them), in order."""
    single = name.endswith("f")
    base = name[:-1] if name.endswith("f") else name
    if base == "atan2":
        specials = PAIR_SPECIALS
        pairs = [(narrow(y), narrow(x)) for y, x in specials if _fits(y) and _fits(x)] if single else list(specials)
        return pairs + sweep_pairs(single)
    specials = [narrow(x) for x in SINGLE_SPECIALS] if single else list(SPECIALS)
    return specials + sweep_arguments(KIND[base], single)




HEAD = '''module cmathtrigtour "Call the runtime's trigonometric functions through ffi and print what each gives"
  path cmathtrigtour
  imports standard.console standard.ffi standard.convert standard.compare standard.math standard.bits standard.logic
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

capability cLibrary "Authority to load the C library and nothing else" load ffi.libraries "c"

{caps}

constant forever "The bound of a loop that ends on its count" Int64 9223372036854775807

optype DoubleFunction "double f(double)"
  input value Float64 copied
  output Float64

optype FloatFunction "float f(float)"
  input value Float32 copied
  output Float32

optype DoublePairFunction "double f(double, double)"
  input first Float64 copied
  input second Float64 copied
  output Float64

optype FloatPairFunction "float f(float, float)"
  input first Float32 copied
  input second Float32 copied
  output Float32

instance DoubleBinding "Binds a C function of a double" ffi.Function DoubleFunction

instance FloatBinding "Binds a C function of a float" ffi.Function FloatFunction

instance DoublePairBinding "Binds a C function of two doubles" ffi.Function DoublePairFunction

instance FloatPairBinding "Binds a C function of two floats" ffi.Function FloatPairFunction

op sayDouble "Write a double on a line, as repr writes it"
  input value Float64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  write: console.writeFloatLine(value) ~
  return

op nextState "The generator's next state: state * 6364136223846793005 + 1442695040888963407, modulo 2^64"
  input state UInt64 copied
  output UInt64
:begin
  calc product = math.wrappingMultiplyUInt64(state, 6364136223846793005)
  calc next = math.wrappingAddUInt64(product, 1442695040888963407)
  return next

op argumentFrom "The double a state makes: its top bit the sign, an exponent from base up over span values, and 52 (or 23) bits of mantissa; a float's exponent is wrapped into the float range 897 to 1150"
  input state UInt64 copied
  input base Int64 copied
  input span Int64 copied
  input single Bool copied
  output Float64
  let mantissa UInt64 0 mut
  let exponent Int64 0 mut
:begin
  calc sign = state >> 63
  calc draw = convert.uint64ToInt64((state >> 40) & 16777215)
  calc raw = base + draw % span
  calc whole = state & 4503599627370495
  calc exponent := raw
  calc mantissa := whole
  when single floatCase joined
:floatCase
  calc mantissa := whole & 4503599090499584
  calc outside = (raw < 897) || (raw > 1150)
  when outside wrap joined
:wrap
  calc exponent := 897 + raw % 254
  goto joined
:joined
  calc field = (sign << 63) | (convert.int64ToUInt64(exponent) << 52) | mantissa
  calc value = convert.uint64BitsToFloat64(field)
  return value

{ops}

op main "Open the C library, call each function, and write what it gives"
  output ExitCode
  effect load ffi.libraries
  effect load ffi.symbols
  effect write console.stdout
  uses cLibrary
{uses}
  uses stdoutWriter
  let okCode ExitCode 0
  let failCode ExitCode 1
:begin
  openIt: libc = ffi.open(cName="c") ? failedOpen
{body}
  closeIt: ffi.close(libc)
  return okCode
:failed
  closeFailed: ffi.close(libc)
  return failCode
:failedOpen
  return failCode
'''


def _sweep_op(pair: bool, single: bool) -> str:
    kind = ("Float" if single else "Double") + ("Pair" if pair else "")
    callee = f"{kind}Function"
    lines = [f'op sweep{kind} "Call a function with arguments a generator makes and write what it gives; gives the generator\'s state"',
             f"  input callee {callee} copied", "  input start UInt64 copied", "  input base Int64 copied",
             "  input span Int64 copied", "  input count Int64 copied", "  output UInt64",
             "  effect write console.stdout", "  uses stdoutWriter", "  let state UInt64 0 mut", "  let done Int64 0 mut",
             ":begin", "  calc state := start", "  goto eachCall", ":eachCall loop=while max=forever",
             "  when done < count call finish", ":call in=eachCall", "  calc state := nextState(state)"]
    wide = "single" if single else "wide"
    if single:
        lines.append("  calc firstWide = argumentFrom(state, base, span, true)")
        lines.append("  calc first = convert.float64ToFloat32(firstWide)")
    else:
        lines.append("  calc first = argumentFrom(state, base, span, false)")
    if pair:
        lines.append("  calc state := nextState(state)")
        if single:
            lines.append("  calc secondWide = argumentFrom(state, base, span, true)")
            lines.append("  calc second = convert.float64ToFloat32(secondWide)")
        else:
            lines.append("  calc second = argumentFrom(state, base, span, false)")
        lines.append("  callIt: result = *callee(first, second)")
    else:
        lines.append("  callIt: result = *callee(first)")
    if single:
        lines.append("  calc shown = convert.float32ToFloat64(result)")
        lines.append("  showIt: sayDouble(shown)")
    else:
        lines.append("  showIt: sayDouble(result)")
    lines += ["  calc done := done + 1", "  goto eachCall", ":finish", "  return state"]
    del wide
    return "\n".join(lines)


def _specials_op(pair: bool, single: bool) -> str:
    kind = ("Float" if single else "Double") + ("Pair" if pair else "")
    callee = f"{kind}Function"
    lines = [f'op specials{kind} "Call a function with each special argument and write what it gives"',
             f"  input callee {callee} copied", "  effect write console.stdout", "  uses stdoutWriter"]
    if pair:
        items = PAIR_SPECIALS if not single else [(narrow(y), narrow(x)) for y, x in PAIR_SPECIALS if _fits(y) and _fits(x)]
    else:
        items = [(x,) for x in (SINGLE_SPECIALS if single else SPECIALS)]
    for idx, item in enumerate(items):
        for pos, v in enumerate(item):
            lines.append(f"  let special{idx}x{pos} UInt64 {_bits(v)}")
    lines.append(":begin")
    for idx, item in enumerate(items):
        args = []
        for pos in range(len(item)):
            lines.append(f"  calc wide{idx}x{pos} = convert.uint64BitsToFloat64(special{idx}x{pos})")
            if single:
                lines.append(f"  calc value{idx}x{pos} = convert.float64ToFloat32(wide{idx}x{pos})")
                args.append(f"value{idx}x{pos}")
            else:
                args.append(f"wide{idx}x{pos}")
        lines.append(f"  call{idx}: result{idx} = *callee({', '.join(args)})")
        if single:
            lines.append(f"  calc shown{idx} = convert.float32ToFloat64(result{idx})")
            lines.append(f"  show{idx}: sayDouble(shown{idx})")
        else:
            lines.append(f"  show{idx}: sayDouble(result{idx})")
    lines.append("  return")
    return "\n".join(lines)


def _dsl() -> str:
    caps, uses, body = [], [], []
    for name in ONE + ONE_F + TWO + TWO_F:
        caps.append(f'capability {name}Symbol "Authority to bind the C function {name}" load ffi.symbols "{name}"')
        uses.append(f"  uses {name}Symbol")
    ops = [_specials_op(p, s) for p in (False, True) for s in (False, True)]
    ops += [_sweep_op(p, s) for p in (False, True) for s in (False, True)]
    for name in ONE + ONE_F + TWO + TWO_F:
        single = name.endswith("f")
        base = name[:-1] if single else name
        pair = base == "atan2"
        kind = ("Float" if single else "Double") + ("Pair" if pair else "")
        body.append(f"  bind{name}: {name}Fn = {kind}Binding.bind(libc, {name}Name=\"{name}\") ? failed")
        body.append(f"  special{name}: specials{kind}({name}Fn)")
        prev = f"initial{name}"
        body.append(f"  start{name}: {prev} = nextStateOf(seed=12345)")
        for k, (b, span, count) in enumerate(SWEEPS[KIND[base]]):
            cur = f"state{name}{k}"
            body.append(f"  sweep{name}{k}: {cur} = sweep{kind}({name}Fn, {prev}, base{name}{k}={b}, span{name}{k}={span}, "
                        f"count{name}{k}={count})")
            prev = cur
    # the first state is a literal: make it with a call that returns its argument
    ops.append('op nextStateOf "A state as it is: the generator starts at the number it is given"\n'
               "  input seed UInt64 copied\n  output UInt64\n:begin\n  return seed")
    return HEAD.format(caps="\n\n".join(caps), uses="\n".join(uses), ops="\n\n".join(ops), body="\n".join(body))


def write_project(folder: str) -> None:
    """The project: build.sem and cmathtrigtour.sem, generated from the DSL above."""
    from semgen import Generator, Module, Program
    from caselib import allows_rows
    dsl = _dsl()
    prog = Program()
    m = Module("cmathtrigtour")
    prog.modules["cmathtrigtour"] = m
    g = Generator(prog, m)
    g.declare(dsl)
    g.parse(dsl)
    sem, _tests = g.render(["# The runtime's trigonometric functions through ffi (tests/cmathtrigtour.py)."], None)
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
    with open(os.path.join(folder, "cmathtrigtour.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(sem)
    rows = ["tourProject is project", 'tourProject purpose "Call the runtime\'s trigonometric functions through ffi"',
            "tourProject target console", 'tourProject version "0.1.0"', "tourProject language refined 1",
            "tourProject standardLibrary 1", *allows_rows("tourProject", [sem]), "tourProject requires none",
            "tourProject includesModule cmathtrigtour", "tourProject entry cmathtrigtour.main"]
    with open(os.path.join(folder, "build.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")


def expected_names() -> list[str]:
    """The functions in the order the tour calls them; each one's lines are `len(inputs(name))` long."""
    return ONE + ONE_F + TWO + TWO_F
