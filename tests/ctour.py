"""A program that calls the runtime's C library through `ffi` (D-153) and prints what each function gives.

tests/test_runtime_nolibc.py builds it with the runtime in SemanticScript and requires what it prints to be what glibc
gives in the C locale: `expected()` below computes that, and on Linux, where `refined run` calls glibc itself through
ctypes, the executable must print exactly what `refined run` prints too. It binds, from `ffi.open("c")`: ctype's
classifiers and case changes over every code from -128 to 255 (glibc's class bits), abs, labs, llabs, and div at their
limits, fabs, trunc, floor, ceil, round, sqrt, fmod, and copysign over signed zeros, halves, subnormals, the largest
doubles, infinities, and NaN, and calloc, memset, strlen, strtol, atoi, strtod, and free on a string made in memory
the library gave (a program passes addresses as whole numbers); and a name the library does not have.
"""
from __future__ import annotations

import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cstdio  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "docs", "refined-examples", "stage0", "tools"))

CTYPE = ["isalnum", "isalpha", "isblank", "iscntrl", "isdigit", "isgraph", "islower", "isprint", "ispunct", "isspace",
         "isupper", "isxdigit", "toupper", "tolower"]
LONGS = ["labs", "llabs"]
DOUBLES = ["fabs", "trunc", "floor", "ceil", "round", "sqrt"]
PAIRS = ["fmod", "copysign"]
POINTERS = ["calloc", "memset", "strlen", "strtol", "atoi", "strtod", "free"]

# the doubles each function of one double is called with: bits, so every value is exact
DOUBLE_INPUTS = [0.0, -0.0, 0.5, -0.5, 1.5, -1.5, 2.5, -2.5, 0.49999999999999994, -0.49999999999999994, 1.0, -1.0,
                 3.75, -3.75, 4503599627370495.5, -4503599627370495.5, 4503599627370497.0, 1e300, -1e300,
                 5e-324, -5e-324, 2.2250738585072014e-308, 1.7976931348623157e308, math.inf, -math.inf, math.nan, 2.0,
                 0.1, 1e22]
PAIR_INPUTS = [(7.5, 2.0), (-7.5, 2.0), (7.5, -2.0), (1.0, 0.1), (1e300, 3e-300), (5e-324, 3e-310), (3e-310, 5e-324),
               (-0.0, 1.0), (0.0, -1.0), (1.0, 0.0), (math.inf, 1.0), (1.0, math.inf), (1.0, math.nan), (2.0, 3.0),
               (-3.0, 3.0), (1e22, 7.0)]
INTS = [0, 1, -1, 2147483647, -2147483647, -2147483648, 12345, -12345]
LONG_INPUTS = [0, 1, -1, 9223372036854775807, -9223372036854775807, -9223372036854775808]
DIV_INPUTS = [(7, 2), (-7, 2), (7, -2), (-7, -2), (0, 5), (2147483647, -1), (-2147483647, 3)]


def _bits(x: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def _dsl() -> str:
    stdio_caps, stdio_optypes, stdio_helpers, stdio_body = cstdio.dsl_parts()
    caps, ops, lets = [], [], []
    for name in CTYPE + ["abs", "div"] + LONGS + DOUBLES + PAIRS + POINTERS + ["semanticscriptNoSuchSymbol"]:
        caps.append(f'capability {name}Symbol "Authority to bind the C function {name}" load ffi.symbols "{name}"')
    uses = "\n".join(f"  uses {c.split()[1]}" for c in caps)
    body = []
    for name in CTYPE:
        body.append(f'  bind{name}: {name}Fn = IntBinding.bind(libc, {name}Name="{name}") ? failed\n'
                    f'  run{name}: everyCode({name}Fn)')
    body.append('  bindabs: absFn = IntBinding.bind(libc, absName="abs") ? failed')
    for i, v in enumerate(INTS):
        body.append(f'  abs{i}: absValue{i} = *absFn(int{i}={v})\n  widenAbs{i}: absWide{i} = convert.int32ToInt64(absValue{i})\n'
                    f'  showAbs{i}: sayNumber(absWide{i})')
    body.append('  binddiv: divFn = DivBinding.bind(libc, divName="div") ? failed')
    for i, (a, b) in enumerate(DIV_INPUTS):
        body.append(f'  div{i}: divValue{i} = *divFn(numerator{i}={a}, denominator{i}={b})\n  showDiv{i}: sayNumber(divValue{i})')
    for name in LONGS:
        body.append(f'  bind{name}: {name}Fn = LongBinding.bind(libc, {name}Name="{name}") ? failed')
        for i, v in enumerate(LONG_INPUTS):
            body.append(f'  {name}{i}: {name}Value{i} = *{name}Fn(long{i}={v})\n  show{name}{i}: sayNumber({name}Value{i})')
    for i, x in enumerate(DOUBLE_INPUTS):
        lets.append(f"  let double{i}Bits UInt64 {_bits(x)}")
    for name in DOUBLES:
        body.append(f'  bind{name}: {name}Fn = DoubleBinding.bind(libc, {name}Name="{name}") ? failed\n'
                    f'  run{name}: everyDouble({name}Fn)')
    for name in PAIRS:
        body.append(f'  bind{name}: {name}Fn = PairBinding.bind(libc, {name}Name="{name}") ? failed\n'
                    f'  run{name}: everyPair({name}Fn)')
    body.append('''  bindcalloc: callocFn = AllocBinding.bind(libc, callocName="calloc") ? failed
  bindmemset: memsetFn = SetBinding.bind(libc, memsetName="memset") ? failed
  bindstrlen: strlenFn = LongBinding.bind(libc, strlenName="strlen") ? failed
  bindstrtol: strtolFn = StrtolBinding.bind(libc, strtolName="strtol") ? failed
  bindatoi: atoiFn = AtoiBinding.bind(libc, atoiName="atoi") ? failed
  bindstrtod: strtodFn = StrtodBinding.bind(libc, strtodName="strtod") ? failed
  bindfree: freeFn = LongBinding.bind(libc, freeName="free") ? failed
  takeBlock: block = *callocFn(count=32, size=1)
  fillLetters: filled = *memsetFn(block, letterA=65, fifteen=15)
  measureLetters: letters = *strlenFn(block)
  showLetters: sayNumber(letters)
  fillDigits: digits = *memsetFn(block, digitSeven=55, three=3)
  readLong: sevens = *strtolFn(block, noEnd=0, ten32=10)
  showSevens: sayNumber(sevens)
  readInt: sevensInt = *atoiFn(block)
  widenInt: sevensWide = convert.int32ToInt64(sevensInt)
  showSevensInt: sayNumber(sevensWide)
  readDouble: sevensDouble = *strtodFn(block, noEnd)
  showSevensDouble: sayDouble(sevensDouble)
  freeBlock: freed = *freeFn(block)
STDIO_BODY
  bindMissing: missingFn = IntBinding.bind(libc, missingName="semanticscriptNoSuchSymbol") ! missingError
  iferr bindMissing reportMissing failed''')
    body[-1] = body[-1].replace("STDIO_BODY", chr(10).join(stdio_body))
    dsl = f'''module ctour "Call the runtime's C library through ffi and print what each function gives"
  path ctour
  imports standard.console standard.ffi standard.convert standard.compare standard.math
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

capability cLibrary "Authority to load the C library and nothing else" load ffi.libraries "c"

{chr(10).join(c + chr(10) for c in caps + stdio_caps)}
{stdio_optypes}
optype IntFunction "int f(int)"
  input value Int32 copied
  output Int32

optype LongFunction "long f(long)"
  input value Int64 copied
  output Int64

optype DivFunction "div: div_t div(int, int), its two ints in one 64-bit register"
  input numerator Int32 copied
  input denominator Int32 copied
  output Int64

optype DoubleFunction "double f(double)"
  input value Float64 copied
  output Float64

optype PairFunction "double f(double, double)"
  input left Float64 copied
  input right Float64 copied
  output Float64

optype AllocFunction "void *calloc(size_t, size_t), the address as a whole number"
  input count Int64 copied
  input size Int64 copied
  output Int64

optype SetFunction "void *memset(void *, int, size_t)"
  input target Int64 copied
  input value Int32 copied
  input bytes Int64 copied
  output Int64

optype StrtolFunction "long strtol(const char *, char **, int)"
  input text Int64 copied
  input end Int64 copied
  input base Int32 copied
  output Int64

optype AtoiFunction "int atoi(const char *)"
  input text Int64 copied
  output Int32

optype StrtodFunction "double strtod(const char *, char **)"
  input text Int64 copied
  input end Int64 copied
  output Float64

instance IntBinding "Binds a C function of an int" ffi.Function IntFunction

instance LongBinding "Binds a C function of a long" ffi.Function LongFunction

instance DivBinding "Binds the C library's div" ffi.Function DivFunction

instance DoubleBinding "Binds a C function of a double" ffi.Function DoubleFunction

instance PairBinding "Binds a C function of two doubles" ffi.Function PairFunction

instance AllocBinding "Binds the C library's calloc" ffi.Function AllocFunction

instance SetBinding "Binds the C library's memset" ffi.Function SetFunction

instance StrtolBinding "Binds the C library's strtol" ffi.Function StrtolFunction

instance AtoiBinding "Binds the C library's atoi" ffi.Function AtoiFunction

instance StrtodBinding "Binds the C library's strtod" ffi.Function StrtodFunction

op say "Write a line"
  input text String borrowed
  effect write console.stdout
  uses stdoutWriter
:begin
  write: console.writeLine(text) ~
  return

op sayNumber "Write a whole number on a line"
  input value Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  write: console.writeIntegerLine(value) ~
  return

op sayDouble "Write a double on a line, as repr writes it"
  input value Float64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  write: console.writeFloatLine(value) ~
  return

{stdio_helpers}
op everyCode "Call a function of an int with every code from -128 to 255 and write what it gives"
  input callee IntFunction copied
  effect write console.stdout
  uses stdoutWriter
  let code Int32 -128 mut
  let codes Int64 384
:begin
  goto eachCode
:eachCode loop=while max=codes
  doneCheck: done = compare.greaterThanInt32(code, last=255)
  if done finish call
:call in=eachCode
  callIt: result = *callee(code)
  widenIt: wide = convert.int32ToInt64(result)
  showIt: sayNumber(wide)
  stepIt: next = math.addInt32(code, one32=1)
  set code next
  goto eachCode
:finish
  return

op everyDouble "Call a function of a double with each of the tour's doubles and write what it gives"
  input callee DoubleFunction copied
  effect write console.stdout
  uses stdoutWriter
{chr(10).join(lets)}
:begin
{chr(10).join(f"  read{i}: value{i} = convert.uint64BitsToFloat64(double{i}Bits)" + chr(10) + f"  call{i}: result{i} = *callee(value{i})" + chr(10) + f"  show{i}: sayDouble(result{i})" for i in range(len(DOUBLE_INPUTS)))}
  return

op everyPair "Call a function of two doubles with each of the tour's pairs and write what it gives"
  input callee PairFunction copied
  effect write console.stdout
  uses stdoutWriter
{chr(10).join(f"  let left{i}Bits UInt64 {_bits(a)}" + chr(10) + f"  let right{i}Bits UInt64 {_bits(b)}" for i, (a, b) in enumerate(PAIR_INPUTS))}
:begin
{chr(10).join(f"  readLeft{i}: left{i} = convert.uint64BitsToFloat64(left{i}Bits)" + chr(10) + f"  readRight{i}: right{i} = convert.uint64BitsToFloat64(right{i}Bits)" + chr(10) + f"  call{i}: result{i} = *callee(left{i}, right{i})" + chr(10) + f"  show{i}: sayDouble(result{i})" for i in range(len(PAIR_INPUTS)))}
  return

op main "Open the C library, call each function, and report a name it does not have"
  output ExitCode
  effect load ffi.libraries
  effect load ffi.symbols
  effect write console.stdout
  uses cLibrary
{uses}
{chr(10).join("  uses " + c.split()[1] for c in stdio_caps)}
  uses stdoutWriter
  let okCode ExitCode 0
  let failCode ExitCode 1
:begin
  openIt: libc = ffi.open(cName="c") ? failedOpen
{chr(10).join(body)}
:reportMissing
  showMissing: say(missingText="symbolMissing")
  closeIt: ffi.close(libc)
  return okCode
:failed
  closeFailed: ffi.close(libc)
  return failCode
:failedOpen
  return failCode
'''
    return dsl


def write_project(folder: str) -> None:
    """The project: build.sem and ctour.sem, generated from the DSL above."""
    from semgen import Generator, Module, Program
    from caselib import allows_rows
    dsl = _dsl()
    prog = Program()
    m = Module("ctour")
    prog.modules["ctour"] = m
    g = Generator(prog, m)
    g.declare(dsl)
    g.parse(dsl)
    sem, _tests = g.render(["# The runtime's C library through ffi (tests/ctour.py)."], None)
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
    with open(os.path.join(folder, "ctour.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(sem)
    rows = ["tourProject is project", 'tourProject purpose "Call the runtime\'s C library through ffi"',
            "tourProject target console", 'tourProject version "0.1.0"', "tourProject language refined 1",
            "tourProject standardLibrary 1", *allows_rows("tourProject", [sem]), "tourProject requires none",
            "tourProject includesModule ctour", "tourProject entry ctour.main"]
    with open(os.path.join(folder, "build.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")


# ---------------------------------------------------------------- what glibc gives, in the C locale

def _class_bits(c: int) -> int:
    """glibc's class word of a code (its C locale table, little-endian bit layout)."""
    if not 0 <= c <= 127:
        return 0
    ch = chr(c)
    bits = 0
    if ch.isupper():
        bits |= 256
    if ch.islower():
        bits |= 512
    if ch.isalpha():
        bits |= 1024
    if ch.isdigit():
        bits |= 2048
    if ch in "0123456789abcdefABCDEF":
        bits |= 4096
    if ch in " \t\n\v\f\r":
        bits |= 8192
    if 32 <= c < 127:
        bits |= 16384
    if 32 < c < 127:
        bits |= 32768
    if ch in " \t":
        bits |= 1
    if c < 32 or c == 127:
        bits |= 2
    if 32 < c < 127 and not ch.isalnum():
        bits |= 4
    if ch.isalnum():
        bits |= 8
    return bits


MASKS = {"isalnum": 8, "isalpha": 1024, "isblank": 1, "iscntrl": 2, "isdigit": 2048, "isgraph": 32768,
         "islower": 512, "isprint": 16384, "ispunct": 4, "isspace": 8192, "isupper": 256, "isxdigit": 4096}


def _wrap(value: int, bits: int) -> int:
    value &= (1 << bits) - 1
    return value - (1 << bits) if value >> (bits - 1) else value


def _c_trunc(x: float) -> float:
    if math.isnan(x) or math.isinf(x) or abs(x) >= 2.0 ** 52:
        return x
    return math.copysign(float(math.trunc(x)), x)


def _c_floor(x: float) -> float:
    if math.isnan(x) or math.isinf(x) or abs(x) >= 2.0 ** 52:
        return x
    return math.copysign(float(math.floor(x)), x) if math.floor(x) == 0 else float(math.floor(x))


def _c_ceil(x: float) -> float:
    if math.isnan(x) or math.isinf(x) or abs(x) >= 2.0 ** 52:
        return x
    return math.copysign(float(math.ceil(x)), x) if math.ceil(x) == 0 else float(math.ceil(x))


def _c_round(x: float) -> float:
    if math.isnan(x) or math.isinf(x) or abs(x) >= 2.0 ** 52:
        return x
    t = _c_trunc(x)
    if abs(x - t) >= 0.5:
        t += math.copysign(1.0, x)
    return t


def _c_sqrt(x: float) -> float:
    return math.nan if x < 0 or math.isnan(x) else math.sqrt(x)


def _c_fmod(x: float, y: float) -> float:
    if math.isnan(x) or math.isnan(y) or math.isinf(x) or y == 0:
        return math.nan
    return math.fmod(x, y)


def expected() -> list[str]:
    """What the tour prints when the C library behaves as glibc does in the C locale."""
    out = []
    for name in CTYPE:
        for c in range(-128, 256):
            if name in ("toupper", "tolower") and -128 <= c <= -2:
                out.append(str(c + 256))  # glibc's C-locale tables hold the unsigned char there
            elif name == "toupper":
                out.append(str(c - 32 if 97 <= c <= 122 else c))
            elif name == "tolower":
                out.append(str(c + 32 if 65 <= c <= 90 else c))
            else:
                out.append(str(_class_bits(c) & MASKS[name]))
    out += [str(_wrap(abs(v), 32)) for v in INTS]
    for a, b in DIV_INPUTS:
        q = _wrap(int(a / b) if b else 0, 32)
        r = _wrap(a - q * b, 32)
        out.append(str(_wrap(((r & 0xffffffff) << 32) | (q & 0xffffffff), 64)))
    for _name in LONGS:
        out += [str(_wrap(abs(v), 64)) for v in LONG_INPUTS]
    funcs = {"fabs": abs, "trunc": _c_trunc, "floor": _c_floor, "ceil": _c_ceil, "round": _c_round, "sqrt": _c_sqrt}
    for name in DOUBLES:
        out += [repr(funcs[name](x)) for x in DOUBLE_INPUTS]
    for name in PAIRS:
        for a, b in PAIR_INPUTS:
            out.append(repr(_c_fmod(a, b) if name == "fmod" else math.copysign(a, b)))
    out += ["15", "777", "777", "777.0"]
    out += cstdio.expected()  # D-159, D-160: printf and sscanf through ffi
    out += ["symbolMissing"]
    return out
