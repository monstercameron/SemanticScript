"""Write the floats module's test cases into its DSL (expected values from Python, which `refined run` uses)."""
import math
import os
import re
import struct
import sys

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "floats.dsl")


def bits(v: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", v))[0]


def q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


FORMAT = [0.0, -0.0, 1.0, 0.1, 100.0, 1e15, 1e16, 1e-5, 0.0001, 5e-324, 2.2250738585072014e-308,
          1.7976931348623157e308, 0.1 + 0.2, 123456789012345678.0, float("nan"), float("inf"), float("-inf"),
          -1.5, 2.0 ** -1000, 2.0 ** 60, 2.0 ** -1022, 2.0 ** -1021, 1 / 3, 2 / 3, 1e23, 1.5e-7, 2.0 ** 1023,
          4.35, 0.5, 2.5, 1e100, 1234.5678, 9.999999999999999e22, 1e22, 2.0 ** 52, 2.0 ** 53 + 2, 5e-324 * 3,
          1.0000000000000002, 0.9999999999999999, 1e-4, 9.5367431640625e-07, -2.0 ** -1074 * 12345,
          4.940656458412465e-324 * 2 ** 52, 8.98846567431158e307]
PARSE = ["0", "-0", "1", "1.5", "0.1", "1e10", "1E-5", "2.5e+3", "-123.456", "1.7976931348623157e308",
         "1.7976931348623158e308", "1.7976931348623159e308", "1e309", "-1e309", "1e-400", "-1e-400",
         "2.4703282292062328e-324", "2.4703282292062327e-324", "4.9406564584124654e-324",
         "2.2250738585072011e-308", "2.2250738585072012e-308", "9007199254740993", "9007199254740995",
         "0.000000000000000000000000000000000001", "123456789012345678901234567890", "00012", "0.30000000000000004",
         "1" + "0" * 30 + "e-30", "0." + "0" * 10 + "1" * 850, "9" * 820 + "e-820", "7e-10000000000000000000000",
         "1e99999999999999999999", "0e99999999999999999999", "+1", "1.", ".5", "1e", "abc", "", "-", "1.5e+", "1_0",
         " 1", "1e+-5", "--1", "1.2.3", "nan", "inf"]
TEXT = re.compile(r"-?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?")


def parse_case(text: str):
    if not TEXT.fullmatch(text):
        return 1, 0
    v = float(text)
    if math.isinf(v):
        return 2, 0
    return 0, bits(v)


def tests() -> str:
    out = []
    for n, chunk in enumerate([FORMAT[i:i + 15] for i in range(0, len(FORMAT), 15)], 1):
        rows = [f'test formatTest{n} "Floats are written as `refined run` writes them (Python\'s repr), part {n}"',
                "  verifies formatFloat writesRepr", "  effect use machine.memory", "  effect use system.calls",
                "  uses memoryAccess", "  uses systemCalls", ":begin",
                "  findState: state = machine.state()", "  findScratch: scratch = machine.offset(state, scratchAt=61440)",
                f"  asFloat: first = convert.uint64BitsToFloat64({bits(chunk[0])})",
                "  formatFirst: length = formatFloat(first, scratch)", "  viewFirst: text = machine.stringAt(scratch, length)",
                f"  expectFirst: test.assertEqualString({q(repr(chunk[0]))}, text)"]
        for i, v in enumerate(chunk[1:], 1):
            rows.append(f"  case{i}: expectFormat({bits(v)}, {q(repr(v))})")
        rows.append("  return")
        out.append("\n".join(rows))
    for n, chunk in enumerate([PARSE[i:i + 16] for i in range(0, len(PARSE), 16)], 1):
        rows = [f'test parseTest{n} "Text is read as `refined run` reads it, correctly rounded, part {n}"',
                "  verifies parseFloat readsCorrectlyRounded", "  effect use machine.memory", "  effect use system.calls",
                "  uses memoryAccess", "  uses systemCalls", ":begin",
                "  findState: state = machine.state()", "  findScratch: scratch = machine.offset(state, scratchAt=61440)",
                f"  findFirst: firstAt = machine.addressOfString({q(chunk[0])})",
                f"  parseFirst: got = parseFloat(firstAt, {len(chunk[0].encode())}, scratch)",
                "  widenFirst: gotStatus = convert.int32ToInt64(got)",
                f"  expectFirst: test.assertEqualInt64({parse_case(chunk[0])[0]}, gotStatus)"]
        for i, t in enumerate(chunk[1:], 1):
            status, b = parse_case(t)
            rows.append(f"  case{i}: expectParse({q(t)}, {status}, {b})")
        rows.append("  return")
        out.append("\n".join(rows))
    return "\n\n".join(out) + "\n"


if __name__ == "__main__":
    with open(P, encoding="utf-8") as fh:
        text = fh.read()
    marker = "## ---------------------------------------------------------------- generated cases\n"
    head = text.split(marker)[0] if marker in text else text.replace("@formatCases\n\n@parseCases\n", "")
    with open(P, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(head.rstrip("\n") + "\n\n" + marker + "\n" + tests())
