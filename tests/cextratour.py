"""A program that calls the runtime's `cextra` functions through `ffi("c")` and prints what each gives.

tests/test_c_cextra.py builds it with the runtime in SemanticScript and requires what it prints to be what glibc gives
in the C locale: `expected()` below computes that with small models (glibc's TYPE_3 generator and rand_r, a strtof
rounded with exact fractions, strtol's rules), and on Linux, where `refined run` calls glibc itself, the executable
must print what `refined run` prints. A program cannot read memory through ffi, so a result stored in memory (an end
pointer, a pointer from posix_memalign) is checked with memcmp against bytes the program writes, and a string is read
back as a number with strtoull in base 36.

It binds, from `ffi.open("c")`: rand, srand, rand_r; strtok, strtok_r, strsep, strcoll, strxfrm, memccpy, mempcpy,
stpcpy, stpncpy, strchrnul, memrchr; strtof; aligned_alloc, posix_memalign; setlocale, localeconv; imaxabs,
strtoimax, strtoumax, wcstoimax, wcstoumax. `write_assert_project` makes a program that fails an assertion.
"""
from __future__ import annotations

import math
import os
import struct
import sys
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "docs", "refined-examples", "stage0", "tools"))

# the names this module adds to the runtime's C library (the test compares them with the .sem files)
NAMES = ["strtok", "strtok_r", "strsep", "strcoll", "strxfrm", "memccpy", "mempcpy", "stpcpy", "stpncpy",
         "strchrnul", "memrchr", "rand", "srand", "rand_r", "strtof", "aligned_alloc", "posix_memalign", "setlocale",
         "localeconv", "__assert_fail", "imaxabs", "strtoimax", "strtoumax", "wcstoimax", "wcstoumax", "__isoc23_strtoimax",
         "__isoc23_strtoumax", "__isoc23_wcstoimax", "__isoc23_wcstoumax"]

SEEDS = [1, 0, 12345, 42, 2147483647, -1, -2147483648, 987654321]
SEED_COUNT = 10
RAND_R_SEEDS = [1, 12345, 0xFFFFFFFF, 0, 0x80000000, 31337]
RAND_R_COUNT = 4

TOKEN_TEXTS = [(",;  alpha,,beta; gamma;", ",; "), ("one", ",;"), (";;;", ";"), ("a b  c", " ")]
SEP_TEXT = "a,b,,c"
SEP_DELIMITERS = ",;"
COLLATE = [("abc", "abc"), ("abc", "abd"), ("abd", "abc"), ("ab", "abc"), ("abc", "ab"), ("", "a"), ("a", ""),
           ("", ""), ("Z", "a"), ("a\x7f", "a")]
XFRM_SOURCE = "hello"
XFRM_COUNTS = [0, 3, 6, 12]

STRTOF = ["0", "-0", "1", "  \t3.5xyz", "0.1", "-0.1", "1e10", "1e39", "-1e39", "3.4028235e38", "3.40282356e38",
          "3.4028236e38", "1e-45", "1e-46", "7e-46", "1.4e-45", "1.17549435e-38", "16777217", "16777219",
          "1.00000005960464477539062500000001", "1.000000059604644775390625", "1.00000005960464477539062499999999",
          "0.000000000000000000000000000000000000000000001", "123456789012345678901234567890", ".5", "5.", "+.5e1", "1e",
          "1e+", "e5", "abc", "", "inf", "-Infinity", "infinit", "nan", "-nan(12ab)", "nan(", "0x10", "0x1p-149",
          "0x1.8p-149", "0x1p-150", "0x1.fffffep127", "0x1.ffffffp127", "0x1.00000100000000000000000001p0",
          "0x1.000001p0", "0x.8p1", "0x", "0xg", "0X1P3z", "1.5e3junk", "0.3", "8388608.5",
          "340282356779733661637539395458142568447", "340282356779733661637539395458142568448",
          "0.00000000000000000000000000000000000000000000140129846432481707"]

ALIGNED = [(16, 1), (32, 100), (64, 100), (128, 5000), (256, 16), (64, 0), (8, 40), (32, 1), (2048, 3000),
           (4096, 1), (4096, 100000), (65536, 70000), (65536, 1), (4096, 16777216), (65536, 16777216)]
# (rounds, alignment, size) of the aligned_alloc, realloc, free cycles: none may fail, and a leak would be gigabytes
ALIGNED_CYCLES = [(2000, 16, 100), (2000, 64, 1000), (2000, 2048, 5000), (1000, 4096, 20000), (1000, 65536, 100000),
                  (60, 65536, 16777216), (60, 4096, 16777216)]
ALIGN_BAD = [0, 3, 24]
POSIX = [(64, 100, 0), (8, 8, 0), (3, 8, 22), (4, 8, 22), (24, 8, 22), (0, 8, 22)]

IMAX_ABS = [0, 1, -1, 9223372036854775807, -9223372036854775807, -9223372036854775808, 123456789012]
IMAX = [("  -123abc", 10), ("0x1fz", 0), ("0x1fz", 16), ("077", 0), ("077", 8), ("9223372036854775807", 10),
        ("9223372036854775808", 10), ("-9223372036854775808", 10), ("-9223372036854775809", 10), ("zz", 36),
        ("12", 1), ("12", 37), ("", 10), ("   ", 10), ("0x", 16), ("-0x10", 0), ("18446744073709551615", 10),
        ("18446744073709551616", 10), ("-1", 10), ("+7", 10), ("08", 0), ("1010", 2)]
WIDE_IMAX = [("  -123abc", 10), ("0x1fz", 0), ("9223372036854775808", 10), ("18446744073709551615", 10), ("", 10),
             ("zz", 36), ("12", 99), ("7é", 10)]


def _bits(x: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def _wrap(value: int, bits: int) -> int:
    value &= (1 << bits) - 1
    return value - (1 << bits) if value >> (bits - 1) else value


# ---------------------------------------------------------------- the DSL

OPTYPES = [
    ("SetFunction", "void *memset(void *, int, size_t)", ["target:Int64", "value:Int32", "bytes:Int64"], "Int64"),
    ("CompareFunction", "int memcmp(const void *, const void *, size_t)", ["left:Int64", "right:Int64", "bytes:Int64"],
     "Int32"),
    ("CollateFunction", "int strcmp(const char *, const char *)", ["left:Int64", "right:Int64"], "Int32"),
    ("LongFunction", "long f(long)", ["value:Int64"], "Int64"),
    ("NoArgumentFunction", "long f(void)", [], "Int64"),
    ("PairFunction", "long f(long, long)", ["left:Int64", "right:Int64"], "Int64"),
    ("TripleFunction", "long f(long, long, long)", ["first:Int64", "second:Int64", "third:Int64"], "Int64"),
    ("AllocFunction", "void *calloc(size_t, size_t)", ["count:Int64", "size:Int64"], "Int64"),
    ("StrtolFunction", "long strtol(const char *, char **, int)", ["text:Int64", "end:Int64", "base:Int32"], "Int64"),
    ("CopyUntilFunction", "void *memccpy(void *, const void *, int, size_t)",
     ["target:Int64", "source:Int64", "value:Int32", "bytes:Int64"], "Int64"),
    ("FindFunction", "char *strchrnul(const char *, int)", ["text:Int64", "value:Int32"], "Int64"),
    ("FindBoundedFunction", "void *memrchr(const void *, int, size_t)",
     ["block:Int64", "value:Int32", "bytes:Int64"], "Int64"),
    ("SingleFunction", "float strtof(const char *, char **)", ["text:Int64", "end:Int64"], "Float32"),
    ("SeedFunction", "void srand(unsigned)", ["seed:Int32"], None),
    ("NumberFunction", "int rand(void)", [], "Int32"),
    ("ReentrantFunction", "int rand_r(unsigned *)", ["seed:Int64"], "Int32"),
    ("PosixFunction", "int posix_memalign(void **, size_t, size_t)", ["where:Int64", "alignment:Int64", "size:Int64"],
     "Int32"),
    ("LocaleFunction", "char *setlocale(int, const char *)", ["category:Int32", "name:Int64"], "Int64"),
]
# symbol -> optype
BINDINGS = {
    "memset": "SetFunction", "memcmp": "CompareFunction", "strcmp": "CollateFunction", "strlen": "LongFunction",
    "free": "LongFunction", "calloc": "AllocFunction", "strtoull": "StrtolFunction", "__errno_location": "NoArgumentFunction",
    "strtok": "PairFunction", "strtok_r": "TripleFunction", "strsep": "PairFunction", "strcoll": "CollateFunction",
    "strxfrm": "TripleFunction", "memccpy": "CopyUntilFunction", "mempcpy": "TripleFunction",
    "stpcpy": "PairFunction", "stpncpy": "TripleFunction", "strchrnul": "FindFunction", "memrchr": "FindBoundedFunction",
    "rand": "NumberFunction", "srand": "SeedFunction", "rand_r": "ReentrantFunction", "strtof": "SingleFunction",
    "aligned_alloc": "PairFunction", "realloc": "PairFunction", "posix_memalign": "PosixFunction", "setlocale": "LocaleFunction",
    "localeconv": "NoArgumentFunction", "imaxabs": "LongFunction", "strtoimax": "StrtolFunction",
    "strtoumax": "StrtolFunction", "wcstoimax": "StrtolFunction", "wcstoumax": "StrtolFunction",
}

HELPERS = '''op putByteAt "Put one byte at an address moved on by an offset, through memset"
  input setter SetFunction copied
  input base Int64 copied
  input offset Int64 copied
  input code Int32 copied
:begin
  findAt: at = math.addInt64(base, offset)
  setIt: unused = *setter(at, code, one=1)
  return

op putLong "Put a 64-bit number, least significant byte first, at an address moved on by an offset"
  input setter SetFunction copied
  input base Int64 copied
  input offset Int64 copied
  input value Int64 copied
:begin
  calc at = base + offset
  calc byte0 = value & 255
  code0 = convert.int64ToInt32(byte0)
  put0: unused0 = *setter(at, code0, one0=1)
{puts}
  return

op offsetOf "An address less a base, or 0 for the address 0"
  input address Int64 copied
  input base Int64 copied
  output Int64
:begin
  when address == 0 nothing found
:nothing
  return 0
:found
  calc offset = address - base
  return offset

op signOf "-1, 0, or 1 for a number below, at, or above 0"
  input value Int64 copied
  output Int64
:begin
  when value < 0 below notBelow
:below
  return -1
:notBelow
  when value > 0 above same
:above
  return 1
:same
  return 0

op errnoCode "34 when memcmp found errno equal to 34, 22 when equal to 22, 0 when equal to 0, else -1"
  input againstRange Int64 copied
  input againstInvalid Int64 copied
  input againstZero Int64 copied
  output Int64
:begin
  when againstRange == 0 range checkInvalid
:range
  return 34
:checkInvalid
  when againstInvalid == 0 invalid checkZero
:invalid
  return 22
:checkZero
  when againstZero == 0 clear other
:clear
  return 0
:other
  return -1

op isAligned "1 when an address is not 0 and a multiple of an alignment, else 0"
  input address Int64 copied
  input alignment Int64 copied
  output Int64
:begin
  when address == 0 missing check
:missing
  return 0
:check
  calc rest = address % alignment
  when rest == 0 aligned crooked
:aligned
  return 1
:crooked
  return 0

op alignedCycles "Many rounds of aligned_alloc, filling it, realloc to twice the size (its bytes kept: the first half is compared with 7s written to the second), and free; the number of rounds that went wrong"
  input allocate PairFunction copied
  input release LongFunction copied
  input grow PairFunction copied
  input setter SetFunction copied
  input comparer CompareFunction copied
  input count Int64 copied
  input alignment Int64 copied
  input size Int64 copied
  output Int64
  let done Int64 0 mut
  let failures Int64 0 mut
:begin
  goto eachRound
:eachRound loop=while max=9223372036854775807
  when done >= count finished round
:round in=eachRound
  block = *allocate(alignment, size)
  calc rest = block % alignment
  when block == 0 bad checkAlignment
:checkAlignment in=eachRound
  when rest == 0 fillIt bad
:fillIt in=eachRound
  filled = *setter(block, seven=7, size)
  calc bigger = size * 2
  moved = *grow(block, bigger)
  when moved == 0 bad keep
:keep in=eachRound
  calc second = moved + size
  filledMore = *setter(second, sevenAgain=7, size)
  same = *comparer(moved, second, size)
  freed = *release(moved)
  when same == 0 good bad
:good in=eachRound
  calc done := done + 1
  goto eachRound
:bad in=eachRound
  calc failures := failures + 1
  calc done := done + 1
  goto eachRound
:finished
  return failures

op say "Write a whole number on a line"
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

op sayText "Write a line"
  input text String borrowed
  effect write console.stdout
  uses stdoutWriter
:begin
  write: console.writeLine(text) ~
  return
'''




def _lines_put_long() -> str:
    out = []
    for k in range(1, 8):
        out.append(f"  calc shifted{k} = value >> {8 * k}")
        out.append(f"  calc byte{k} = shifted{k} & 255")
        out.append(f"  code{k} = convert.int64ToInt32(byte{k})")
        out.append(f"  calc at{k} = at + {k}")
        out.append(f"  put{k}: unused{k} = *setter(at{k}, code{k}, one{k}=1)")
    return "\n".join(out)


def is_arm() -> bool:
    """Whether the executables are built for AArch64, where char is unsigned (localeconv's CHAR_MAX is 255)."""
    from refined.native import find_cc, platform
    cc = find_cc()
    if cc is None:
        return False
    _machine, triple, _problem = platform(cc)
    return bool(triple) and triple.startswith("aarch64")


def ident(symbol: str) -> str:
    """A C name as a SemanticScript name: no leading underscore, snake case made camel case."""
    parts = [x for x in symbol.split("_") if x]
    return parts[0] + "".join(x[:1].upper() + x[1:] for x in parts[1:])


class Program:
    """The lines of `main` and the lines it should print, built together so they agree."""

    NOWHERE = "nowhere"

    def __init__(self):
        self.lines: list[str] = []
        self.out: list[str] = []
        self.errno_lines: list[int] = []
        self.n = 0

    def uid(self, prefix: str) -> str:
        self.n += 1
        return f"{prefix}{self.n}"

    def emit(self, line: str) -> None:
        self.lines.append("  " + line)

    def arg(self, value) -> str:
        return value if isinstance(value, str) else f"{self.uid('n')}={value}"

    def call(self, symbol: str, *args) -> str:
        result = self.uid("r")
        self.emit(f"{self.uid('c')}: {result} = *{ident(symbol)}Fn({', '.join(self.arg(a) for a in args)})")
        return result

    def call_void(self, symbol: str, *args) -> None:
        self.emit(f"{self.uid('c')}: *{ident(symbol)}Fn({', '.join(self.arg(a) for a in args)})")

    def call32(self, symbol: str, *args) -> str:
        result = self.call(symbol, *args)
        wide = self.uid("w")
        self.emit(f"{self.uid('x')}: {wide} = convert.int32ToInt64({result})")
        return wide

    def say(self, name: str, expected) -> None:
        self.emit(f"{self.uid('s')}: say({name})")
        self.out.append(str(expected))

    def say_double(self, name: str, expected: float) -> None:
        self.emit(f"{self.uid('s')}: sayDouble({name})")
        self.out.append(repr(expected))

    def add(self, base: str, offset: int) -> str:
        result = self.uid("a")
        self.emit(f"{self.uid('f')}: {result} = math.addInt64({base}, {self.arg(offset)})")
        return result

    def ptr(self, offset: int) -> str:
        return self.add("area", offset)

    def put_text(self, offset: int, data: bytes) -> None:
        for k, byte in enumerate(data + b"\0"):
            self.emit(f"{self.uid('p')}: putByteAt(memsetFn, area, {self.arg(offset + k)}, {self.arg(byte)})")

    def put_long(self, offset: int, value) -> None:
        self.emit(f"{self.uid('p')}: putLong(memsetFn, area, {self.arg(offset)}, {self.arg(value)})")

    def fill(self, at: str, byte: int, count: int) -> None:
        self.call("memset", at, byte, count)

    def offset_of(self, address: str, base: str = "area") -> str:
        result = self.uid("o")
        self.emit(f"{self.uid('q')}: {result} = offsetOf({address}, {base})")
        return result

    def sign_of(self, wide: str) -> str:
        result = self.uid("g")
        self.emit(f"{self.uid('q')}: {result} = signOf({wide})")
        return result

    def base36(self, at: str) -> str:
        return self.call("strtoull", at, 0, 36)

    def clear_errno(self) -> None:
        self.fill("errnoAt", 0, 4)

    def errno_code(self, expected: int) -> None:
        a = self.call32("memcmp", "errnoAt", self.ptr(ERRNO_RANGE), 4)
        b = self.call32("memcmp", "errnoAt", self.ptr(ERRNO_INVALID), 4)
        c = self.call32("memcmp", "errnoAt", self.ptr(ERRNO_ZERO), 4)
        code = self.uid("e")
        self.emit(f"{self.uid('g')}: {code} = errnoCode({a}, {b}, {c})")
        self.errno_lines.append(len(self.out))
        self.say(code, expected)


# memory map of the tour's calloc'd area (64 KiB)
ERRNO_ZERO = 64          # 8 zero bytes (the area is zeroed)
ERRNO_RANGE = 72         # 34, 0, 0, 0
ERRNO_INVALID = 80       # 22, 0, 0, 0
END_CELL = 128           # an end pointer
WANT_CELL = 144          # the pointer the end should be
SAVE_CELL = 160          # strtok_r's save pointer
SEP_CELL = 176           # strsep's pointer
SEED_CELL = 192          # rand_r's seed
ONES = 208               # 14 bytes of 127
POSIX_CELL = 240         # posix_memalign's pointer
TEXT = 1024              # the text of the current case
DELIMITERS = 1600
DST = 2048
SRC = 2304
WIDE = 4096              # wide text


# ---------------------------------------------------------------- what glibc gives, modelled

def glibc_rand_sequence(seed: int, count: int) -> list[int]:
    """glibc's TYPE_3 generator: 31 words seeded by the 16807 LCG, 310 outputs discarded, then r[i] = r[i-3] + r[i-31]."""
    seed &= 0xFFFFFFFF
    word = seed - (1 << 32) if seed >> 31 else seed
    if word == 0:
        word = 1
    state = [word & 0xFFFFFFFF]
    for _ in range(30):
        hi = int(word / 127773)
        lo = word - hi * 127773
        word = 16807 * lo - 2836 * hi
        if word < 0:
            word += 2147483647
        state.append(word & 0xFFFFFFFF)
    f, r = 3, 0
    out = []
    for _ in range(310 + count):
        state[f] = (state[f] + state[r]) & 0xFFFFFFFF
        out.append(state[f] >> 1)
        f = (f + 1) % 31
        r = (r + 1) % 31
    return out[310:]


def rand_r_sequence(seed: int, count: int) -> list[int]:
    nxt = seed & 0xFFFFFFFF
    out = []
    for _ in range(count):
        nxt = (nxt * 1103515245 + 12345) & 0xFFFFFFFF
        result = (nxt >> 16) % 2048
        nxt = (nxt * 1103515245 + 12345) & 0xFFFFFFFF
        result = (result << 10) ^ ((nxt >> 16) % 1024)
        nxt = (nxt * 1103515245 + 12345) & 0xFFFFFFFF
        result = (result << 10) ^ ((nxt >> 16) % 1024)
        out.append(result)
    return out


C_SPACE = " \t\n\v\f\r"
HEX = "0123456789abcdefABCDEF"


def round_single(x: Fraction, hexadecimal: bool) -> tuple[float, int]:
    """The float nearest a non-negative number (ties to even) as a double, and the errno strtof sets for it."""
    if x == 0:
        return 0.0, 0
    e = x.numerator.bit_length() - x.denominator.bit_length()
    if Fraction(2) ** e > x:
        e -= 1
    if Fraction(2) ** (e + 1) <= x:
        e += 1
    ulp = Fraction(2) ** (max(e, -126) - 23)
    q = x / ulp
    n = q.numerator // q.denominator
    rem = q - n
    if rem > Fraction(1, 2) or (rem == Fraction(1, 2) and n % 2 == 1):
        n += 1
    value = n * ulp
    if value >= Fraction(2) ** 128:
        return math.inf, 34
    error = 0
    if value < Fraction(2) ** -126:
        error = 34 if (value == 0 or not hexadecimal or value != x) else 0
    return float(value), error


def c_strtof(s: str):
    """(value as a double, sign bit of a NaN, errno, end) for strtof of a text, as glibc reads it in the C locale."""
    i = 0
    while i < len(s) and s[i] in C_SPACE:
        i += 1
    negative = False
    if i < len(s) and s[i] in "+-":
        negative = s[i] == "-"
        i += 1
    rest = s[i:]
    low = rest.lower()
    if low.startswith("inf"):
        end = i + (8 if low.startswith("infinity") else 3)
        return (-math.inf if negative else math.inf), negative, 0, end
    if low.startswith("nan"):
        end = i + 3
        if rest[3:4] == "(":
            j = 4
            while j < len(rest) and (rest[j].isascii() and rest[j].isalnum() or rest[j] == "_"):
                j += 1
            if rest[j:j + 1] == ")":
                end = i + j + 1
        return math.nan, negative, 0, end
    if low.startswith("0x"):
        j = 2
        whole = ""
        while j < len(rest) and rest[j] in HEX:
            whole += rest[j]
            j += 1
        fraction = ""
        if j < len(rest) and rest[j] == ".":
            k = j + 1
            while k < len(rest) and rest[k] in HEX:
                fraction += rest[k]
                k += 1
            if whole or fraction:
                j = k
        if not (whole or fraction):
            return (-0.0 if negative else 0.0), negative, 0, i + 1
        exponent = 0
        if j < len(rest) and rest[j] in "pP":
            k = j + 1
            sign = 1
            if k < len(rest) and rest[k] in "+-":
                sign = -1 if rest[k] == "-" else 1
                k += 1
            digits = ""
            while k < len(rest) and rest[k].isdigit():
                digits += rest[k]
                k += 1
            if digits:
                exponent = sign * int(digits)
                j = k
        mantissa = int(whole + fraction or "0", 16)
        x = Fraction(mantissa) * Fraction(2) ** (exponent - 4 * len(fraction))
        value, error = round_single(x, True)
        return (-value if negative else value), negative, error, i + j
    j = 0
    whole = ""
    while j < len(rest) and rest[j].isdigit():
        whole += rest[j]
        j += 1
    fraction = ""
    if j < len(rest) and rest[j] == ".":
        k = j + 1
        while k < len(rest) and rest[k].isdigit():
            fraction += rest[k]
            k += 1
        if whole or fraction:
            j = k
    if not (whole or fraction):
        return 0.0, False, 0, 0
    exponent = 0
    if j < len(rest) and rest[j] in "eE":
        k = j + 1
        sign = 1
        if k < len(rest) and rest[k] in "+-":
            sign = -1 if rest[k] == "-" else 1
            k += 1
        digits = ""
        while k < len(rest) and rest[k].isdigit():
            digits += rest[k]
            k += 1
        if digits:
            exponent = sign * int(digits)
            j = k
    x = Fraction(int(whole + fraction or "0")) * Fraction(10) ** (exponent - len(fraction))
    value, error = round_single(x, False)
    return (-value if negative else value), negative, error, i + j


def c_strtol(s: str, base: int, unsigned: bool):
    """(value as a signed 64-bit number, errno, end) for strtol or strtoul of a text in a base."""
    if base < 0 or base == 1 or base > 36:
        return 0, 22, 0
    i = 0
    while i < len(s) and s[i] in C_SPACE:
        i += 1
    negative = False
    if i < len(s) and s[i] in "+-":
        negative = s[i] == "-"
        i += 1
    prefixed = False
    if s[i:i + 1] == "0":
        if s[i + 1:i + 2] in ("x", "X") and base in (0, 16):
            prefixed = True
            base = 16
            i += 2
        elif base == 0:
            base = 8
    elif base == 0:
        base = 10
    start = i
    value = 0
    while i < len(s) and s[i].isascii() and s[i].isalnum():
        digit = int(s[i], 36)
        if digit >= base:
            break
        value = value * base + digit
        i += 1
    if i == start:
        return 0, 0, (start - 1 if prefixed else 0)
    if unsigned:
        if value >= 1 << 64:
            return _wrap((1 << 64) - 1, 64), 34, i
        return _wrap(-value if negative else value, 64), 0, i
    if negative:
        if value > 1 << 63:
            return -(1 << 63), 34, i
        return -value, 0, i
    if value > (1 << 63) - 1:
        return (1 << 63) - 1, 34, i
    return value, 0, i


def base36_value(text: bytes) -> int:
    """strtoull(text, NULL, 36) of the C string at the start of the bytes."""
    text = text.split(b"\0")[0]
    value = 0
    for byte in text:
        ch = chr(byte)
        if not (ch.isascii() and ch.isalnum()):
            break
        value = value * 36 + int(ch, 36)
    return _wrap(value, 64)


def strtok_model(text: bytes, delimiters: bytes, calls: int, base: int):
    """What strtok gives over a number of calls: (offset or 0, token) for each; the text's offsets begin at base."""
    buffer = bytearray(text + b"\0")
    save = 0
    out = []
    for call in range(calls):
        position = 0 if call == 0 else save
        while buffer[position] != 0 and buffer[position] in delimiters:
            position += 1
        if buffer[position] == 0:
            save = position
            out.append((0, None))
            continue
        start = position
        while buffer[position] != 0 and buffer[position] not in delimiters:
            position += 1
        token = bytes(buffer[start:position])
        if buffer[position] == 0:
            save = position
        else:
            buffer[position] = 0
            save = position + 1
        out.append((base + start, token))
    return out


def strsep_model(text: bytes, delimiters: bytes, base: int):
    buffer = bytearray(text + b"\0")
    position = 0
    out = []
    while position is not None:
        start = position
        while buffer[position] != 0 and buffer[position] not in delimiters:
            position += 1
        token = bytes(buffer[start:position])
        if buffer[position] == 0:
            position = None
        else:
            buffer[position] = 0
            position += 1
        out.append((base + start, token))
    return out


# ---------------------------------------------------------------- the program

def build_program() -> Program:
    p = Program()
    for sym in sorted(BINDINGS):
        p.emit(f"bind{ident(sym)}: {ident(sym)}Fn = {BINDINGS[sym]}Binding.bind(libc, {ident(sym)}Name=\"{sym}\") ? failed")
    p.emit("takeArea: area = *callocFn(areaCount=1, areaBytes=65536)")
    p.emit("findErrno: errnoAt = *errnoLocationFn()")
    p.emit("makeNowhere: nowhere = math.addInt64(zeroBase=0, zeroAdd=0)")
    p.put_long(ERRNO_RANGE, 34)
    p.put_long(ERRNO_INVALID, 22)
    p.fill(p.ptr(ONES), 255 if is_arm() else 127, 14)  # CHAR_MAX: char is unsigned on AArch64

    # rand starts as srand(1) does
    for value in glibc_rand_sequence(1, 3):
        p.say(p.call32("rand"), value)
    for seed in SEEDS:
        p.call_void("srand", seed)
        for value in glibc_rand_sequence(seed, SEED_COUNT):
            p.say(p.call32("rand"), value)
    for seed in RAND_R_SEEDS:
        p.put_long(SEED_CELL, seed)
        cell = p.ptr(SEED_CELL)
        for value in rand_r_sequence(seed, RAND_R_COUNT):
            p.say(p.call32("rand_r", cell), value)

    # strtok and strtok_r
    for use_r in (False, True):
        for text, delimiters in TOKEN_TEXTS:
            model = strtok_model(text.encode(), delimiters.encode(), len(text) + 3, TEXT)
            calls = next(k for k, (_o, token) in enumerate(model) if token is None) + 2
            p.put_text(TEXT, text.encode())
            p.put_text(DELIMITERS, delimiters.encode())
            text_at, delimiters_at = p.ptr(TEXT), p.ptr(DELIMITERS)
            save_at = None
            if use_r:
                p.put_long(SAVE_CELL, 0)
                save_at = p.ptr(SAVE_CELL)
            for k in range(calls):
                first = text_at if k == 0 else "nowhere"
                if use_r:
                    token_at = p.call("strtok_r", first, delimiters_at, save_at)
                else:
                    token_at = p.call("strtok", first, delimiters_at)
                got = model[k]
                p.say(p.offset_of(token_at), got[0])
                if got[1] is not None:
                    p.say(p.call("strlen", token_at), len(got[1]))
    p.put_text(TEXT, SEP_TEXT.encode())
    p.put_text(DELIMITERS, SEP_DELIMITERS.encode())
    text_at, delimiters_at = p.ptr(TEXT), p.ptr(DELIMITERS)
    p.put_long(SEP_CELL, text_at)
    cell = p.ptr(SEP_CELL)
    for offset, token in strsep_model(SEP_TEXT.encode(), SEP_DELIMITERS.encode(), TEXT):
        token_at = p.call("strsep", cell, delimiters_at)
        p.say(p.offset_of(token_at), offset)
        p.say(p.call("strlen", token_at), len(token))
    token_at = p.call("strsep", cell, delimiters_at)
    p.say(p.offset_of(token_at), 0)
    p.say(p.sign_of(p.call32("memcmp", cell, p.ptr(ERRNO_ZERO), 8)), 0)

    # strcoll and strxfrm
    for left, right in COLLATE:
        p.put_text(SRC, left.encode())
        p.put_text(DST, right.encode())
        order = p.call32("strcoll", p.ptr(SRC), p.ptr(DST))
        a, b = left.encode(), right.encode()
        p.say(p.sign_of(order), (a > b) - (a < b))
    p.put_text(SRC, XFRM_SOURCE.encode())
    for count in XFRM_COUNTS:
        p.fill(p.ptr(DST), 0, 32)
        p.fill(p.ptr(DST), 90, 10)
        target = p.ptr(DST) if count else "nowhere"
        p.say(p.call("strxfrm", target, p.ptr(SRC), count), len(XFRM_SOURCE))
        memory = bytearray(b"Z" * 10 + b"\0")
        source = XFRM_SOURCE.encode() + b"\0"
        if count:
            memory[:min(len(source), count)] = source[:min(len(source), count)]
        p.say(p.base36(p.ptr(DST)), base36_value(bytes(memory)))

    # the copies
    source_text = b"abcdef"
    p.put_text(SRC, source_text)
    for code, count in [(100, 6), (113, 3), (356, 6), (100, 2), (0, 7)]:
        p.fill(p.ptr(DST), 0, 32)
        p.fill(p.ptr(DST), 90, 10)
        target, source = p.ptr(DST), p.ptr(SRC)
        memory = bytearray(b"Z" * 10 + b"\0")
        source_full = source_text + b"\0"
        result = 0
        for k in range(min(count, len(source_full))):
            memory[k] = source_full[k]
            if source_full[k] == code & 255:
                result = k + 1
                break
        p.say(p.offset_of(p.call("memccpy", target, source, code, count), target), result)
        p.say(p.base36(target), base36_value(bytes(memory)))
    for count in (4, 0):
        p.fill(p.ptr(DST), 0, 32)
        p.fill(p.ptr(DST), 90, 10)
        target, source = p.ptr(DST), p.ptr(SRC)
        memory = bytearray(b"Z" * 10 + b"\0")
        memory[:count] = source_text[:count]
        p.say(p.offset_of(p.call("mempcpy", target, source, count), target), count)
        p.say(p.base36(target), base36_value(bytes(memory)))
    p.fill(p.ptr(DST), 0, 32)
    p.fill(p.ptr(DST), 90, 10)
    target, source = p.ptr(DST), p.ptr(SRC)
    p.say(p.offset_of(p.call("stpcpy", target, source), target), 6)
    p.say(p.base36(target), base36_value(source_text))
    for count in (10, 3, 6):
        p.fill(p.ptr(DST), 0, 32)
        p.fill(p.ptr(DST), 90, 10)
        target, source = p.ptr(DST), p.ptr(SRC)
        memory = bytearray(b"Z" * 10 + b"\0")
        memory[:count] = (source_text + b"\0" * 10)[:count]
        p.say(p.offset_of(p.call("stpncpy", target, source, count), target), min(count, len(source_text)))
        p.say(p.base36(target), base36_value(bytes(memory)))
        if count == 10:
            p.say(p.sign_of(p.call32("memcmp", p.add(target, 6), p.ptr(ERRNO_ZERO), 4)), 0)
    hello = b"hello"
    p.put_text(SRC, hello)
    for code in (108, 122, 0, 108 + 256, 255):
        source = p.ptr(SRC)
        wanted = code & 255
        expected = hello.index(bytes([wanted])) if bytes([wanted]) in hello else len(hello)
        p.say(p.offset_of(p.call("strchrnul", source, code), source), expected)
    both = b"hello,hello"
    p.put_text(SRC, both)
    for code, count in [(108, 11), (108, 3), (104, 11), (113, 11), (108, 0), (44, 11), (111, 11)]:
        source = p.ptr(SRC)
        index = both[:count].rfind(bytes([code & 255]))
        p.say(p.offset_of(p.call("memrchr", source, code, count), source), index if index > 0 else 0)

    # strtof
    for text in STRTOF:
        value, negative_nan, error, end = c_strtof(text)
        p.put_text(TEXT, text.encode())
        text_at, end_at, want_at = p.ptr(TEXT), p.ptr(END_CELL), p.ptr(WANT_CELL)
        p.clear_errno()
        result = p.call("strtof", text_at, end_at)
        wide = p.uid("d")
        p.emit(f"{p.uid('x')}: {wide} = convert.float32ToFloat64({result})")
        p.say_double(wide, value)
        if math.isnan(value):
            raw = p.uid("b")
            p.emit(f"{p.uid('x')}: {raw} = convert.float64BitsToUInt64({wide})")
            shifted = p.uid("h")
            p.emit(f"{p.uid('x')}: {shifted} = bits.shiftRightUInt64({raw}, {p.arg(63)})")
            signed = p.uid("k")
            p.emit(f"{p.uid('x')}: {signed} = convert.uint64ToInt64({shifted})")
            p.say(signed, int(negative_nan))
        p.errno_code(error)
        p.put_long(WANT_CELL, p.add(text_at, end))
        p.say(p.sign_of(p.call32("memcmp", end_at, want_at, 8)), 0)

    # aligned allocation
    for rounds, alignment, size in ALIGNED_CYCLES:
        failed = p.uid("y")
        p.emit(f"{p.uid('q')}: {failed} = alignedCycles(alignedAllocFn, freeFn, reallocFn, memsetFn, memcmpFn, "
               f"{p.arg(rounds)}, {p.arg(alignment)}, {p.arg(size)})")
        p.say(failed, 0)
    for alignment, size in ALIGNED:
        block = p.call("aligned_alloc", alignment, size)
        flag = p.uid("m")
        p.emit(f"{p.uid('q')}: {flag} = isAligned({block}, {p.arg(alignment)})")
        p.say(flag, 1)
        if size:
            p.fill(block, 7, size)
        p.call("free", block)
    cell = p.ptr(POSIX_CELL)
    for alignment, size, status in POSIX:
        p.put_long(POSIX_CELL, 0)
        p.say(p.call32("posix_memalign", cell, alignment, size), status)
        p.say(p.sign_of(p.call32("memcmp", cell, p.ptr(ERRNO_ZERO), 8)), 1 if status == 0 else 0)

    # locale
    p.put_text(SRC, b"C")
    p.put_text(DST, b"POSIX")
    p.put_text(TEXT, b"xx_NOWHERE")
    # the first call puts glibc in the C locale: under refined run the process is Python's, which has set its own
    named = p.call("setlocale", 6, p.ptr(DST))
    p.say(p.sign_of(p.call32("strcmp", named, p.ptr(SRC))), 0)
    current = p.call("setlocale", 6, "nowhere")
    p.say(p.sign_of(p.call32("strcmp", current, p.ptr(SRC))), 0)
    named = p.call("setlocale", 2, p.ptr(SRC))
    p.say(p.sign_of(p.call32("strcmp", named, p.ptr(SRC))), 0)
    refused = p.call("setlocale", 6, p.ptr(TEXT))
    p.say(p.offset_of(refused), 0)
    refused = p.call("setlocale", 13, p.ptr(SRC))
    p.say(p.offset_of(refused), 0)
    conventions = p.call("localeconv")
    p.say(p.sign_of(p.call32("memcmp", p.add(conventions, 80), p.ptr(ONES), 14)), 0)
    again = p.call("localeconv")
    p.say(p.offset_of(again, conventions), 0)

    # inttypes
    for value in IMAX_ABS:
        p.say(p.call("imaxabs", value), _wrap(abs(value), 64))
    for symbol, unsigned in (("strtoimax", False), ("strtoumax", True)):
        for text, base in IMAX:
            value, error, end = c_strtol(text, base, unsigned)
            p.put_text(TEXT, text.encode())
            text_at, end_at = p.ptr(TEXT), p.ptr(END_CELL)
            p.put_long(END_CELL, text_at)
            p.clear_errno()
            p.say(p.call(symbol, text_at, end_at, base), value)
            p.errno_code(error)
            p.put_long(WANT_CELL, p.add(text_at, end))
            p.say(p.sign_of(p.call32("memcmp", end_at, p.ptr(WANT_CELL), 8)), 0)
    for symbol, unsigned in (("wcstoimax", False), ("wcstoumax", True)):
        for text, base in WIDE_IMAX:
            value, error, end = c_strtol(text, base, unsigned)
            for k, ch in enumerate(text + "\0"):
                p.put_long(WIDE + 4 * k, ord(ch))
            wide_at, end_at = p.ptr(WIDE), p.ptr(END_CELL)
            p.put_long(END_CELL, wide_at)
            p.clear_errno()
            p.say(p.call(symbol, wide_at, end_at, base), value)
            p.errno_code(error)
            p.put_long(WANT_CELL, p.add(wide_at, 4 * end))
            p.say(p.sign_of(p.call32("memcmp", end_at, p.ptr(WANT_CELL), 8)), 0)
    p.call("free", "area")
    return p


def _declarations() -> tuple[str, str, str, str]:
    caps, optypes, instances = [], [], []
    symbols = sorted(BINDINGS)
    for sym in symbols:
        caps.append(f'capability {ident(sym)}Symbol "Authority to bind the C function {sym}" load ffi.symbols "{sym}"')
    for name, doc, params, output in OPTYPES:
        lines = [f'optype {name} "{doc}"']
        for param in params:
            pname, ptype = param.split(":")
            lines.append(f"  input {pname} {ptype} copied")
        if output:
            lines.append(f"  output {output}")
        optypes.append("\n".join(lines))
        instances.append(f'instance {name}Binding "Binds a C function of this shape" ffi.Function {name}')
    uses = "\n".join(f"  uses {ident(sym)}Symbol" for sym in symbols)
    return "\n\n".join(caps), "\n\n".join(optypes), "\n\n".join(instances), uses


def _dsl() -> str:
    program = build_program()
    caps, optypes, instances, uses = _declarations()
    helpers = HELPERS.replace("{puts}", _lines_put_long())
    body = "\n".join(program.lines)
    return f'''module cextratour "Call the runtime's cextra functions through ffi and print what each gives"
  path cextratour
  imports standard.console standard.ffi standard.convert standard.compare standard.math standard.bits
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

capability cLibrary "Authority to load the C library and nothing else" load ffi.libraries "c"

{caps}

{optypes}

{instances}

{helpers}
op main "Open the C library, call each function, and print what it gives"
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


def _write(folder: str, name: str, dsl: str) -> None:
    from semgen import Generator, Module, Program as SemProgram
    from caselib import allows_rows
    prog = SemProgram()
    m = Module(name)
    prog.modules[name] = m
    g = Generator(prog, m)
    g.declare(dsl)
    g.parse(dsl)
    sem, _tests = g.render(["# The runtime's cextra functions through ffi (tests/cextratour.py)."], None)
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
    with open(os.path.join(folder, f"{name}.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(sem)
    rows = [f"{name}Project is project", f'{name}Project purpose "Call the runtime\'s cextra functions through ffi"',
            f"{name}Project target console", f'{name}Project version "0.1.0"', f"{name}Project language refined 1",
            f"{name}Project standardLibrary 1", *allows_rows(f"{name}Project", [sem]), f"{name}Project requires none",
            f"{name}Project includesModule {name}", f"{name}Project entry {name}.main"]
    with open(os.path.join(folder, "build.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")


def write_project(folder: str) -> None:
    """The project: build.sem and cextratour.sem, generated from the DSL above."""
    _write(folder, "cextratour", _dsl())


def expected() -> list[str]:
    return build_program().out


def without_errno(lines: list[str]) -> list[str]:
    """The tour's output less the lines that show errno: under refined run the call goes through ctypes, which does
    not keep errno from one call to the next, so errno is compared only in the executable against the models."""
    skip = set(build_program().errno_lines)
    return [line for i, line in enumerate(lines) if i not in skip]


# ---------------------------------------------------------------- the assertion program

ASSERT_ARGUMENTS = ("x > 0 && y != 'z'", "demo/file.c", 42, "compute_it")

HELPERS_ASSERT = '''op putByteAt "Put one byte at an address moved on by an offset, through memset"
  input setter SetFunction copied
  input base Int64 copied
  input offset Int64 copied
  input code Int32 copied
:begin
  findAt: at = math.addInt64(base, offset)
  setIt: unused = *setter(at, code, one=1)
  return
'''

ASSERT_OPTYPES = '''optype AssertFunction "void __assert_fail(const char *, const char *, unsigned, const char *)"
  input assertion Int64 copied
  input file Int64 copied
  input line Int32 copied
  input function Int64 copied

optype SetFunction "void *memset(void *, int, size_t)"
  input target Int64 copied
  input value Int32 copied
  input bytes Int64 copied
  output Int64

optype AllocFunction "void *calloc(size_t, size_t)"
  input count Int64 copied
  input size Int64 copied
  output Int64

instance AssertBinding "Binds __assert_fail" ffi.Function AssertFunction

instance SetBinding "Binds memset" ffi.Function SetFunction

instance AllocBinding "Binds calloc" ffi.Function AllocFunction'''


def write_assert_project(folder: str, with_function: bool) -> None:
    """A program that fails an assertion (__assert_fail), with or without a function name."""
    assertion, file, line, function = ASSERT_ARGUMENTS
    p = Program()
    p.emit('bindAssert: assertFn = AssertBinding.bind(libc, assertName="__assert_fail") ? failed')
    p.emit('bindmemset: memsetFn = SetBinding.bind(libc, memsetName="memset") ? failed')
    p.emit('bindcalloc: callocFn = AllocBinding.bind(libc, callocName="calloc") ? failed')
    p.emit("takeArea: area = *callocFn(areaCount=1, areaBytes=4096)")
    p.put_text(0, assertion.encode())
    p.put_text(256, file.encode())
    p.put_text(512, function.encode())
    assertion_at, file_at, function_at = p.ptr(0), p.ptr(256), p.ptr(512)
    if not with_function:
        p.emit("makeNowhere: nowhere = math.addInt64(zeroBase=0, zeroAdd=0)")
        function_at = "nowhere"
    p.emit(f"failIt: *assertFn({assertion_at}, {file_at}, lineNumber={line}, {function_at})")
    dsl = f'''module assertour "Fail an assertion through ffi"
  path assertour
  imports standard.ffi standard.math
  exports main

capability cLibrary "Authority to load the C library and nothing else" load ffi.libraries "c"

capability assertSymbol "Authority to bind the C function __assert_fail" load ffi.symbols "__assert_fail"

capability memsetSymbol "Authority to bind the C function memset" load ffi.symbols "memset"

capability callocSymbol "Authority to bind the C function calloc" load ffi.symbols "calloc"

{ASSERT_OPTYPES}

{HELPERS_ASSERT}
op main "Open the C library and fail an assertion"
  output ExitCode
  effect load ffi.libraries
  effect load ffi.symbols
  uses cLibrary
  uses assertSymbol
  uses memsetSymbol
  uses callocSymbol
  let okCode ExitCode 0
  let failCode ExitCode 1
:begin
  openIt: libc = ffi.open(cName="c") ? failedOpen
{chr(10).join(p.lines)}
  closeIt: ffi.close(libc)
  return okCode
:failed
  closeFailed: ffi.close(libc)
  return failCode
:failedOpen
  return failCode
'''
    _write(folder, "assertour", dsl)


def expected_assert_message(program: str, with_function: bool) -> str:
    assertion, file, line, function = ASSERT_ARGUMENTS
    where = f"{function}: " if with_function else ""
    return f"{program}: {file}:{line}: {where}Assertion `{assertion}' failed.\n"
