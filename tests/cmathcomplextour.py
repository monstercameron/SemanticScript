"""A program that calls the runtime's complex functions through `ffi` (D-153, D-175) and prints what each gives.

tests/test_c_cmathcomplex.py builds it with the runtime in SemanticScript and no C library, and compares what it prints
with an exact reference (semanticscript/runtime/tools/cmathcomplexgen.py: decimals, with Annex G's special values). It
binds from `ffi.open("c")` the 44 functions of complex.h for double complex and float complex (cabs, carg, cimag, creal,
conj, cproj, cexp, clog, cpow, csqrt, csin, ccos, ctan, casin, cacos, catan, csinh, ccosh, ctanh, casinh, cacosh,
catanh, and each f form). A `double complex` crosses the foreign boundary as a record of two Float64 and a `float
complex` as a record of two Float32 (D-175), so this tour is the first end-to-end test of the complex ABI: x86_64's two
SSE registers (and one packed register for float), AArch64's homogeneous aggregates, Windows x64's hidden pointers.

Each function is called on a grid of special values (signed zeros, infinities, NaN, +-1, 0.5, 2) in every combination,
and on deterministic sweeps: a 64-bit generator makes the bits of each part, with an exponent drawn from a range
(`SWEEPS`). A result is printed as one line per part. `inputs(name)` gives the same arguments in Python.
"""
from __future__ import annotations

import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "docs", "refined-examples", "stage0", "tools"))
sys.path.insert(0, os.path.join(ROOT, "semanticscript", "runtime", "tools"))
sys.path.insert(0, HERE)

import cmathcomplexgen as G  # noqa: E402
import cmathtrigtour  # noqa: E402

INF = math.inf
NAN = math.nan

UNARY = [n for n, *_ in G.UNARY]
REAL = [n for n, *_ in G.REALS]
BINARY = [n for n, *_ in G.BINARY]
KINDS = ("Unary", "Real", "Binary")


def kind_of(name: str) -> str:
    base = name[:-1] if name.endswith("f") else name
    return "Unary" if base in UNARY else "Real" if base in REAL else "Binary"


GRID_VALUES = [0.0, -0.0, 1.0, -1.0, 0.5, 2.0, INF, -INF, NAN]
# (smallest biased exponent, how many exponents, pairs): 1e-9 to 1e3, 0.015 to 4, 1e-18 to 1e18, 32 to 2048
SWEEPS = [(1023 - 30, 40, 50), (1023 - 6, 8, 40), (1023 - 60, 120, 30), (1023 + 5, 6, 20)]
BASES = [(2.0, 0.0), (1.0, 1.0), (-1.0, 2.0), (0.5, -0.5), (3.0, 4.0), (0.0, 1.0), (-2.0, 0.0), (10.0, 0.25)]
EXPONENTS = [(2.0, 0.0), (0.5, 0.0), (0.0, 1.0), (-1.0, 0.5), (1.5, -2.0), (INF, 0.0), (NAN, 0.0), (0.0, 0.0)]

MULTIPLIER = 6364136223846793005
INCREMENT = 1442695040888963407
MASK = (1 << 64) - 1


def _bits(x: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def _fits(x: float) -> bool:
    return math.isnan(x) or math.isinf(x) or x == 0 or 1.2e-38 <= abs(x) <= 3.4e38


def narrow(x: float) -> float:
    return G.narrow(x)


def sweep_pairs(single: bool) -> list[tuple[float, float]]:
    out = []
    state = 12345
    for base, span, count in SWEEPS:
        for _ in range(count):
            state = (state * MULTIPLIER + INCREMENT) & MASK
            x = cmathtrigtour._argument(state, base, span, single)
            state = (state * MULTIPLIER + INCREMENT) & MASK
            out.append((x, cmathtrigtour._argument(state, base, span, single)))
    return out


def grid(single: bool) -> list[tuple[float, float]]:
    return [(a, b) for a in GRID_VALUES for b in GRID_VALUES]


def inputs(name: str) -> list:
    """The arguments the tour calls `name` with: pairs, or pairs of pairs for cpow (floats for the f forms, as the
    doubles that hold them), in the order of the output."""
    single = name.endswith("f")
    base = name[:-1] if single else name
    if base in BINARY:
        return [(b, e) for b in BASES for e in EXPONENTS]
    return grid(single) + sweep_pairs(single)


def expected_names() -> list[str]:
    return UNARY + REAL + BINARY + [n + "f" for n in UNARY + REAL + BINARY]


def lines_per_call(name: str) -> int:
    return 1 if kind_of(name) == "Real" else 2


HEAD = '''module cmathcomplextour "Call the runtime's complex functions through ffi and print what each gives"
  path cmathcomplextour
  imports standard.console standard.ffi standard.convert standard.compare standard.math standard.bits standard.logic
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

capability cLibrary "Authority to load the C library and nothing else" load ffi.libraries "c"

{caps}

constant forever "The bound of a loop that ends on its count" Int64 9223372036854775807

record Complex "double complex"
  field real Float64
  field imag Float64

record ComplexSingle "float complex"
  field real Float32
  field imag Float32

optype ComplexFunction "double complex f(double complex)"
  input value Complex copied
  output Complex

optype ComplexRealFunction "double f(double complex)"
  input value Complex copied
  output Float64

optype ComplexPairFunction "double complex f(double complex, double complex)"
  input first Complex copied
  input second Complex copied
  output Complex

optype ComplexSingleFunction "float complex f(float complex)"
  input value ComplexSingle copied
  output ComplexSingle

optype ComplexSingleRealFunction "float f(float complex)"
  input value ComplexSingle copied
  output Float32

optype ComplexSinglePairFunction "float complex f(float complex, float complex)"
  input first ComplexSingle copied
  input second ComplexSingle copied
  output ComplexSingle

instance ComplexBinding "Binds a C function of a double complex" ffi.Function ComplexFunction

instance ComplexRealBinding "Binds a C function of a double complex that gives a double" ffi.Function ComplexRealFunction

instance ComplexPairBinding "Binds a C function of two double complex" ffi.Function ComplexPairFunction

instance ComplexSingleBinding "Binds a C function of a float complex" ffi.Function ComplexSingleFunction

instance ComplexSingleRealBinding "Binds a C function of a float complex that gives a float" ffi.Function ComplexSingleRealFunction

instance ComplexSinglePairBinding "Binds a C function of two float complex" ffi.Function ComplexSinglePairFunction

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

op nextStateOf "A state as it is: the generator starts at the number it is given"
  input seed UInt64 copied
  output UInt64
:begin
  return seed

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

op sayComplex "Write the two parts of a double complex on two lines"
  input value Complex copied
  effect write console.stdout
  uses stdoutWriter
:begin
  real = Complex.real(value)
  imag = Complex.imag(value)
  sayReal: sayDouble(real)
  sayImag: sayDouble(imag)
  return

op sayComplexSingle "Write the two parts of a float complex on two lines, widened"
  input value ComplexSingle copied
  effect write console.stdout
  uses stdoutWriter
:begin
  real = ComplexSingle.real(value)
  imag = ComplexSingle.imag(value)
  calc wideReal = convert.float32ToFloat64(real)
  calc wideImag = convert.float32ToFloat64(imag)
  sayReal: sayDouble(wideReal)
  sayImag: sayDouble(wideImag)
  return

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


def _type(kind: str, single: bool) -> str:
    return "Complex" + ("Single" if single else "") + ("Real" if kind == "Real" else "Pair" if kind == "Binary" else "") + "Function"


def _binding(kind: str, single: bool) -> str:
    return "Complex" + ("Single" if single else "") + ("Real" if kind == "Real" else "Pair" if kind == "Binary" else "") + "Binding"


def _print_result(kind: str, single: bool, name: str) -> list[str]:
    if kind == "Real":
        if single:
            return [f"  calc shown = convert.float32ToFloat64({name})", "  showIt: sayDouble(shown)"]
        return [f"  showIt: sayDouble({name})"]
    return [f"  showIt: {'sayComplexSingle' if single else 'sayComplex'}({name})"]


def _literal_args(kind: str, single: bool, prefix: str, item) -> tuple[list[str], list[str]]:
    """Lets and calc rows that make the arguments of one call from literal bits; the argument names."""
    rec = "ComplexSingle" if single else "Complex"
    pairs = list(item) if kind == "Binary" else [item]
    rows, names = [], []
    for j, (a, b) in enumerate(pairs):
        parts = []
        for k, v in enumerate((a, b)):
            rows.append(f"  calc w{prefix}{j}{k} = convert.uint64BitsToFloat64({_bits(v)})")
            if single:
                rows.append(f"  calc n{prefix}{j}{k} = convert.float64ToFloat32(w{prefix}{j}{k})")
                parts.append(f"n{prefix}{j}{k}")
            else:
                parts.append(f"w{prefix}{j}{k}")
        rows.append(f"  arg{prefix}{j} = {rec}.new({parts[0]}, {parts[1]})")
        names.append(f"arg{prefix}{j}")
    return rows, names


def _specials_op(kind: str, single: bool) -> str:
    ty = _type(kind, single)
    stem = ("Single" if single else "") + kind
    items = [(b, e) for b in BASES for e in EXPONENTS] if kind == "Binary" else grid(single)
    lines = [f'op specials{stem} "Call a function with each special argument and write what it gives"',
             f"  input callee {ty} copied", "  effect write console.stdout", "  uses stdoutWriter", ":begin"]
    for idx, item in enumerate(items):
        rows, names = _literal_args(kind, single, str(idx), item)
        lines += rows
        lines.append(f"  call{idx}: result{idx} = *callee({', '.join(names)})")
        for r in _print_result(kind, single, f"result{idx}"):
            lines.append(r.replace("shown", f"shown{idx}").replace("showIt", f"show{idx}"))
    lines.append("  return")
    return "\n".join(lines)


def _sweep_op(single: bool) -> str:
    kind = "Unary" if True else ""
    ty = _type("Unary", single)
    rec = "ComplexSingle" if single else "Complex"
    stem = ("Single" if single else "") + "Sweep"
    lines = [f'op sweep{stem} "Call a function with arguments a generator makes and write what it gives; gives the generator\'s state"',
             f"  input callee {ty} copied", "  input start UInt64 copied", "  input base Int64 copied",
             "  input span Int64 copied", "  input count Int64 copied", "  output UInt64",
             "  effect write console.stdout", "  uses stdoutWriter", "  let state UInt64 0 mut", "  let done Int64 0 mut",
             ":begin", "  calc state := start", "  goto eachCall", ":eachCall loop=while max=forever",
             "  when done < count call finish", ":call in=eachCall"]
    for k, nm in enumerate(("x", "y")):
        lines.append("  calc state := nextState(state)")
        lines.append(f"  calc {nm}Wide = argumentFrom(state, base, span, {'true' if single else 'false'})")
        if single:
            lines.append(f"  calc {nm} = convert.float64ToFloat32({nm}Wide)")
        else:
            lines.append(f"  calc {nm} = {nm}Wide + 0.0")
    lines.append(f"  argument = {rec}.new(x, y)")
    lines.append("  callIt: result = *callee(argument)")
    lines += _print_result("Unary", single, "result")
    lines += ["  calc done := done + 1", "  goto eachCall", ":finish", "  return state"]
    return "\n".join(lines)


def _real_sweep_op(single: bool) -> str:
    ty = _type("Real", single)
    rec = "ComplexSingle" if single else "Complex"
    stem = ("Single" if single else "") + "RealSweep"
    lines = [f'op sweep{stem} "Call a function of a complex number that gives a real with arguments a generator makes and write what it gives"',
             f"  input callee {ty} copied", "  input start UInt64 copied", "  input base Int64 copied",
             "  input span Int64 copied", "  input count Int64 copied", "  output UInt64",
             "  effect write console.stdout", "  uses stdoutWriter", "  let state UInt64 0 mut", "  let done Int64 0 mut",
             ":begin", "  calc state := start", "  goto eachCall", ":eachCall loop=while max=forever",
             "  when done < count call finish", ":call in=eachCall"]
    for nm in ("x", "y"):
        lines.append("  calc state := nextState(state)")
        lines.append(f"  calc {nm}Wide = argumentFrom(state, base, span, {'true' if single else 'false'})")
        if single:
            lines.append(f"  calc {nm} = convert.float64ToFloat32({nm}Wide)")
        else:
            lines.append(f"  calc {nm} = {nm}Wide + 0.0")
    lines.append(f"  argument = {rec}.new(x, y)")
    lines.append("  callIt: result = *callee(argument)")
    lines += _print_result("Real", single, "result")
    lines += ["  calc done := done + 1", "  goto eachCall", ":finish", "  return state"]
    return "\n".join(lines)


def _dsl() -> str:
    caps, uses, body, ops = [], [], [], []
    for single in (False, True):
        for kind in KINDS:
            ops.append(_specials_op(kind, single))
        ops.append(_sweep_op(single))
        ops.append(_real_sweep_op(single))
    for name in expected_names():
        caps.append(f'capability {name}Symbol "Authority to bind the C function {name}" load ffi.symbols "{name}"')
        uses.append(f"  uses {name}Symbol")
        single = name.endswith("f")
        kind = kind_of(name)
        bind = _binding(kind, single)
        stem = ("Single" if single else "") + kind
        body.append(f"  bind{name}: {name}Fn = {bind}.bind(libc, {name}Name=\"{name}\") ? failed")
        body.append(f"  special{name}: specials{stem}({name}Fn)")
        if kind != "Binary":
            prev = f"initial{name}"
            body.append(f"  start{name}: {prev} = nextStateOf(seed=12345)")
            sweep_op = ("sweep" + ("Single" if single else "") + ("RealSweep" if kind == "Real" else "Sweep"))
            for k, (b, span, count) in enumerate(SWEEPS):
                cur = f"state{name}{k}"
                body.append(f"  sweep{name}{k}: {cur} = {sweep_op}({name}Fn, {prev}, base{name}{k}={b}, "
                            f"span{name}{k}={span}, count{name}{k}={count})")
                prev = cur
    return HEAD.format(caps="\n\n".join(caps), uses="\n".join(uses), ops="\n\n".join(ops), body="\n".join(body))


def write_project(folder: str) -> None:
    """The project: build.sem and cmathcomplextour.sem, generated from the DSL above."""
    from semgen import Generator, Module, Program
    from caselib import allows_rows
    dsl = _dsl()
    prog = Program()
    m = Module("cmathcomplextour")
    prog.modules["cmathcomplextour"] = m
    g = Generator(prog, m)
    g.declare(dsl)
    g.parse(dsl)
    sem, _tests = g.render(["# The runtime's complex functions through ffi (tests/cmathcomplextour.py)."], None)
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
    with open(os.path.join(folder, "cmathcomplextour.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(sem)
    rows = ["tourProject is project", 'tourProject purpose "Call the runtime\'s complex functions through ffi"',
            "tourProject target console", 'tourProject version "0.1.0"', "tourProject language refined 1",
            "tourProject standardLibrary 1", *allows_rows("tourProject", [sem]), "tourProject requires none",
            "tourProject includesModule cmathcomplextour", "tourProject entry cmathcomplextour.main"]
    with open(os.path.join(folder, "build.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")
