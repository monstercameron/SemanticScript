"""A program that writes and reads back a large table of floating-point numbers, and what it must print.

tests/test_runtime_nolibc.py builds it with the runtime in SemanticScript and compares what it prints with what
Python prints for the same values; `refined run` writes a Float64 as Python's repr and reads text as Python's
float() does, so that is what the program must print (D-125, D-129). The values are random doubles over all their
bits and over ordinary magnitudes, subnormals, every power of two, powers of ten, and, for reading, texts of every
shape: shortest and 17-digit forms, exact halfway points between neighbouring doubles and texts just off them, long
significands, and texts that are not numbers or too large.
"""
from __future__ import annotations

import math
import os
import random
import re
import struct
import sys
from decimal import Decimal, getcontext

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "docs", "refined-examples", "stage0", "tools"))

getcontext().prec = 2000
TEXT = re.compile(r"-?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?")


def bits_of(v: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", v))[0]


def float_of(b: int) -> float:
    return struct.unpack("<d", struct.pack("<Q", b))[0]


def format_values(seed: int, count: int) -> list[float]:
    rng = random.Random(seed)
    out = [0.0, -0.0, float("nan"), float("inf"), float("-inf"), 5e-324, 2.2250738585072014e-308,
           1.7976931348623157e308, 0.1, 100.0, 1e15, 1e16, 1e-4, 1e-5, 123456789012345678.0]
    out += [2.0 ** k for k in range(-1074, 1024, 7)]
    out += [float(f"1e{k}") for k in range(-323, 309, 3)]
    out += [float_of(rng.getrandbits(64)) for _ in range(count)]
    out += [rng.uniform(-1e6, 1e6) for _ in range(count // 2)]
    out += [float_of(rng.getrandbits(52)) for _ in range(count // 8)]  # subnormals
    out += [rng.randint(1, 10 ** 17) * 1.0 for _ in range(count // 8)]
    out += [math.nextafter(2.0 ** k, 0.0) for k in range(-1020, 1024, 37)]  # just below powers of two
    return out


def parse_texts(seed: int, count: int) -> list[str]:
    rng = random.Random(seed)
    out = ["0", "-0", "1", "1.5", "0.1", "1e10", "1E-5", "2.5e+3", "-123.456", "1.7976931348623157e308",
           "1.7976931348623158e308", "1.7976931348623159e308", "1e309", "-1e309", "1e-400", "2.4703282292062328e-324",
           "2.4703282292062327e-324", "9007199254740993", "9007199254740995", "1" + "0" * 400,
           "0." + "0" * 400 + "1", "+1", "1.", ".5", "1e", "abc", "", "-", "1.5e+", " 1", "1e+-5", "nan", "inf",
           "1e99999999999999999999", "1e-99999999999999999999", "0e99999999999999999999"]
    for _ in range(count):
        v = float_of(rng.getrandbits(64))
        if math.isnan(v) or math.isinf(v):
            continue
        shape = rng.randrange(6)
        if shape == 0:
            out.append(repr(v).replace("inf", "1e999"))
        elif shape == 1:
            out.append("%.17g" % v)
        elif shape == 2:
            out.append("%.25e" % v)
        elif shape == 3 and v != 0.0:
            # the exact halfway point to its neighbour above, and a hair either side of it
            up = math.nextafter(v, math.inf)
            if math.isinf(up):
                continue
            mid = (Decimal(v) + Decimal(up)) / 2
            out.append(_plain(mid))
            out.append(_plain(mid + mid.copy_abs() * Decimal("1e-40")))
            out.append(_plain(mid - mid.copy_abs() * Decimal("1e-40")))
        elif shape == 4:
            out.append(str(rng.randint(0, 10 ** rng.randint(1, 40))))
        else:
            out.append(f"{rng.randint(1, 999999)}.{rng.randint(0, 999999):06d}e{rng.randint(-330, 310)}")
    return out


def _plain(d: Decimal) -> str:
    """A Decimal as text the language reads: digits, an optional fraction, an optional exponent."""
    sign, digits, exponent = d.as_tuple()
    text = "".join(map(str, digits)) or "0"
    return ("-" if sign else "") + text[0] + ("." + text[1:] if len(text) > 1 else "") + \
        f"e{exponent + len(text) - 1}"


def expected_parse(text: str) -> str:
    if not TEXT.fullmatch(text):
        return "notANumber"
    v = float(text)
    if math.isinf(v):
        return "outOfRange"
    b = bits_of(v)
    return str(b - (1 << 64) if b >= 1 << 63 else b)


def expected_output(formats: list[float], parses: list[str]) -> list[str]:
    lines = []
    for v in formats:
        lines += [repr(v), repr(v)]
    lines += [expected_parse(t) for t in parses]
    return lines


def _q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def program_dsl(formats: list[float], parses: list[str]) -> str:
    rows_f = "\n".join(f"  row f{i} value={bits_of(v)}" for i, v in enumerate(formats))
    rows_p = "\n".join(f"  row p{i} text={_q(t)}" for i, t in enumerate(parses))
    return f'''module floattable "Write a table of floating-point numbers and read a table of texts as numbers"
  path floattable
  imports standard.console standard.string standard.convert standard.compare standard.math standard.list
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

record FormatRow "A Float64 by its bits"
  field value UInt64

table formats "The numbers to write" FormatRow
{rows_f}

record ParseRow "A text to read as a number"
  field text String

table parses "The texts to read" ParseRow
{rows_p}

op main "Write each number twice (console.writeFloatLine and string.fromFloat64), then each text read as a number's bits"
  output ExitCode
  effect write console.stdout
  uses stdoutWriter
  region scratch 16777216
  let at Int64 0 mut
  let code ExitCode 0
  let failed ExitCode 1
  let zero Int64 0
:begin
  countFormats: total = formats.length()
  goto eachFormat
:eachFormat loop=while max=total
  formatsDone: doneFormats = compare.greaterOrEqualInt64(at, total)
  if doneFormats startParses writeOne
:writeOne in=eachFormat
  rowNumber: position = math.addInt64(at, one=1)
  readRow: row = formats.rowAt(position) ? lost
  readValue: value = FormatRow.value(row)
  asFloat: number = convert.uint64BitsToFloat64(value)
  writeNumber: console.writeFloatLine(number) ~
  textOf: text = string.fromFloat64(number, scratch)
  writeText: console.writeLine(text) ~
  set at position
  goto eachFormat
:startParses
  set at zero
  countParses: parseTotal = parses.length()
  goto eachParse
:eachParse loop=while max=parseTotal
  parsesDone: doneParses = compare.greaterOrEqualInt64(at, parseTotal)
  if doneParses finish readOne
:readOne in=eachParse
  parseNumber: parsePosition = math.addInt64(at, one)
  readParseRow: parseRow = parses.rowAt(parsePosition) ? lost
  readText: source = ParseRow.text(parseRow)
  parse: parsed = string.toFloat64(source) ? refused
  bitsOf: parsedBits = convert.float64BitsToUInt64(parsed)
  signedOf: signedBits = convert.uint64BitsToInt64(parsedBits)
  writeBits: console.writeIntegerLine(signedBits) ~
  goto nextParse
:refused in=eachParse
  match parseError
  case notANumber notNumber
  case outOfRange tooLarge
:notNumber in=eachParse
  writeNotNumber: console.writeLine(notNumberText="notANumber") ~
  goto nextParse
:tooLarge in=eachParse
  writeTooLarge: console.writeLine(tooLargeText="outOfRange") ~
  goto nextParse
:nextParse in=eachParse
  advanceParse: afterParse = math.addInt64(at, one)
  set at afterParse
  goto eachParse
:finish
  return code
:lost
  return failed
'''


def write_project(folder: str, formats: list[float], parses: list[str]) -> None:
    """The project: build.sem and floattable.sem, generated from the DSL above."""
    from semgen import Generator, Module, Program
    prog = Program()
    m = Module("floattable")
    prog.modules["floattable"] = m
    text = program_dsl(formats, parses)
    g = Generator(prog, m)
    g.declare(text)
    g.parse(text)
    sem, _tests = g.render(["# A table of floating-point numbers written and read back (tests/floattable.py)."], None)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "floattable.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(sem)
    rows = ["floatProject is project", 'floatProject purpose "Write and read a table of floating-point numbers"',
            "floatProject target console", 'floatProject version "0.1.0"', "floatProject language refined 1",
            "floatProject standardLibrary 1", "floatProject allows write console.stdout none",
            "floatProject requires none", "floatProject includesModule floattable",
            "floatProject entry floattable.main"]
    with open(os.path.join(folder, "build.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")
