"""A program that calls the runtime's wide-character and multibyte C functions through `ffi` (D-153) and prints what
each gives (wctype.h, wchar.h, stdlib.h's multibyte functions, uchar.h).

tests/test_c_cwide.py builds it with the runtime in SemanticScript and requires what it prints to be what glibc gives
in the C locale: `Tour` below writes the program and, call by call, computes in Python what it must print. On Linux,
where `refined run` calls glibc itself through ctypes, the executable must print exactly what `refined run` prints.

What a function wrote into memory is checked with memcmp against the bytes the Python model says it wrote, and prints
1 when they are equal; so are errno (read through `__errno_location`) and the end pointers the number parsers and the
restartable converters store (the model's expected address is stored in memory a byte at a time, by the program, and
compared). The classifiers print whether the answer is nonzero, not the class bit (glibc's isw functions give some
nonzero int); wctype and wctrans print whether the handle is nonzero. glibc's C locale converts ASCII only (D-177):
the bytes 0x80 to 0xFF are invalid sequences under mbrtowc and its kin, a wide character past 127 has no byte under
wcrtomb and its kin (EILSEQ either way), and btowc and wctob give WEOF and EOF for them; the section "high bytes"
checks exactly that.
"""
from __future__ import annotations

import math
import os
import re
import struct
import sys
from fractions import Fraction

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "docs", "refined-examples", "stage0", "tools"))

ISW = ["iswalnum", "iswalpha", "iswblank", "iswcntrl", "iswdigit", "iswgraph", "iswlower", "iswprint", "iswpunct",
       "iswspace", "iswupper", "iswxdigit"]
CLASS_NAMES = [n[3:] for n in ISW]
EXTRA_CODES = [8364, 65297, 1114111, 1114112]
AREA = 98304

TYPES = {"p": "Int64", "i": "Int32", "d": "Float64", "f": "Float32"}


def _class_of(name: str, c: int) -> bool:
    if not 0 <= c <= 127:
        return False
    ch = chr(c)
    return {
        "alnum": ch.isalnum(), "alpha": ch.isalpha(), "blank": ch in " \t", "cntrl": c < 32 or c == 127,
        "digit": ch.isdigit(), "graph": 32 < c < 127, "lower": ch.islower(), "print": 32 <= c < 127,
        "punct": 32 < c < 127 and not ch.isalnum(), "space": ch in " \t\n\v\f\r", "upper": ch.isupper(),
        "xdigit": ch in "0123456789abcdefABCDEF"}[name]


def _wrap(value: int, bits: int) -> int:
    value &= (1 << bits) - 1
    return value - (1 << bits) if value >> (bits - 1) else value


def _round_even(q: Fraction) -> int:
    n = q.numerator // q.denominator
    rest = q - n
    if rest > Fraction(1, 2) or (rest == Fraction(1, 2) and n % 2 == 1):
        n += 1
    return n


def to_float32(x: Fraction) -> float:
    """The float nearest a non-negative number (ties to even), as a double: the number itself rounded once."""
    if x == 0:
        return 0.0
    e = x.numerator.bit_length() - x.denominator.bit_length()
    if Fraction(2) ** e > x:
        e -= 1
    exp = max(e, -126) - 23
    n = _round_even(x / Fraction(2) ** exp)
    value = Fraction(n) * Fraction(2) ** exp
    if value >= Fraction(2) ** 128:
        return math.inf
    return float(value)


_HEX = r"0[xX](?:[0-9a-fA-F]+\.?[0-9a-fA-F]*|\.[0-9a-fA-F]+)(?:[pP][+-]?[0-9]+)?"
_DEC = r"(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
_REAL = re.compile(r"[ \t\n\v\f\r]*([+-]?)(inf(?:inity)?|nan|" + _HEX + "|" + _DEC + ")", re.I)


def _hex_fraction(text: str) -> Fraction:
    m = re.match(r"0[xX]([0-9a-fA-F]*)\.?([0-9a-fA-F]*)(?:[pP]([+-]?[0-9]+))?$", text)
    whole, frac, exp = m.group(1), m.group(2), int(m.group(3) or 0)
    return Fraction(int(whole + frac or "0", 16), 16 ** len(frac)) * Fraction(2) ** exp


def parse_real(units: list[int], single: bool):
    """(value, units read, errno) of strtod (strtof when single) over a wide text, as glibc reads it."""
    text = "".join(chr(u) if 0 <= u < 128 else "\x80" for u in units)
    m = _REAL.match(text)
    if m is None:
        return 0.0, 0, 0
    sign, body = -1.0 if m.group(1) == "-" else 1.0, m.group(2)
    low = body.lower()
    if low.startswith("inf"):
        return math.copysign(math.inf, sign), m.end(), 0
    if low == "nan":
        return math.nan, m.end(), 0
    exact = _hex_fraction(body) if low.startswith("0x") else Fraction(body)
    if single:
        value = to_float32(exact)
        inexact = value != exact if not math.isinf(value) else True
        tiny = value < 2.0 ** -126
        errno = 34 if math.isinf(value) or (tiny and (exact != 0) and (inexact or value == 0)) else 0
        return math.copysign(value, sign), m.end(), errno
    value = float(exact) if abs(exact) < Fraction(2) ** 1024 else math.inf
    try:
        value = float(exact)
    except OverflowError:
        value = math.inf
    errno = 34 if math.isinf(value) or (value == 0 and exact != 0) else 0
    return math.copysign(value, sign), m.end(), errno


def parse_int(units: list[int], base: int, unsigned: bool):
    """(value as the signed 64 bits the function returns, units read, errno) of strtol/strtoul over a wide text."""
    def get(k):
        return units[k] if k < len(units) else 0

    def digit(u):
        if 48 <= u <= 57:
            return u - 48
        if 97 <= u <= 122:
            return u - 87
        if 65 <= u <= 90:
            return u - 55
        return 99

    i = 0
    while get(i) in (32, 9, 10, 11, 12, 13):
        i += 1
    negative = False
    if get(i) in (43, 45):
        negative = get(i) == 45
        i += 1
    if base in (0, 16) and get(i) == 48 and get(i + 1) in (120, 88) and digit(get(i + 2)) < 16:
        i += 2
        base = 16
    elif base == 0:
        base = 8 if get(i) == 48 else 10
    start, value = i, 0
    while digit(get(i)) < base:
        value = value * base + digit(get(i))
        i += 1
    if i == start:
        return 0, 0, 0
    if unsigned:
        if value > (1 << 64) - 1:
            return -1, i, 34
        return _wrap(-value if negative else value, 64), i, 0
    if negative:
        if value > 1 << 63:
            return -(1 << 63), i, 34
        return -value, i, 0
    if value > (1 << 63) - 1:
        return (1 << 63) - 1, i, 34
    return value, i, 0


def ident(name: str) -> str:
    parts = name.strip("_").split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


class P:
    """An argument that is the address of a byte offset of the program's area."""

    def __init__(self, off: int):
        self.off = off


NUL = "nul"


class Tour:
    def __init__(self):
        self.n = 0
        self.top = 64
        self.mem = bytearray(AREA)
        self.body: list[str] = []
        self.binds: list[str] = []
        self.caps: list[str] = []
        self.sigs: dict[str, str] = {}
        self.bound: dict[str, str] = {}
        self.out: list[str] = []
        self.sections: list[tuple[int, str]] = []
        self.ptrs: dict[int, str] = {}
        self.err = None

    # ------------------------------------------------------------ plumbing

    def uid(self) -> int:
        self.n += 1
        return self.n

    def section(self, name: str) -> None:
        self.sections.append((len(self.out), name))

    def emit(self, line: str) -> None:
        self.body.append("  " + line)

    def bind(self, fname: str, sig: str) -> str:
        """The variable bound to a C function; `sig` is `<argument letters>><result letter>`."""
        if fname in self.bound:
            return self.bound[fname]
        if sig not in self.sigs:
            args, result = sig.split(">")
            name = "Sig" + args.upper() + "To" + result.upper()
            decl = [f'optype {name}Function "{fname} and its kin: {sig}"']
            for k, a in enumerate(args):
                decl.append(f"  input arg{k} {TYPES[a]} copied")
            decl.append(f"  output {TYPES[result]}")
            decl.append("")
            decl.append(f'instance {name}Binding "Binds a C function of the shape {sig}" ffi.Function {name}Function')
            self.sigs[sig] = "\n".join(decl)
            self.sigs[sig + "#name"] = name
        name = self.sigs[sig + "#name"]
        var = f"{ident(fname)}Fn"
        self.caps.append(f'capability {ident(fname)}Symbol "Authority to bind the C function {fname}" '
                         f'load ffi.symbols "{fname}"')
        self.binds.append(f'  bind{ident(fname)}: {var} = {name}Binding.bind(libc, {ident(fname)}Name="{fname}") ? failed')
        self.bound[fname] = var
        return var

    def alloc(self, nbytes: int) -> int:
        off = self.top
        self.top += (nbytes + 15) // 16 * 16
        assert self.top < AREA
        return off

    def ptr(self, off: int) -> str:
        if off not in self.ptrs:
            k = self.uid()
            self.emit(f"ptr{k}: p{k} = math.addInt64(area, off{k}={off})")
            self.ptrs[off] = f"p{k}"
        return self.ptrs[off]

    def put_byte(self, off: int, value: int) -> None:
        self.mem[off] = value
        if value:
            k = self.uid()
            self.emit(f"put{k}: putByteAt(memsetFn, area, at{k}={off}, code{k}={value})")

    def put_unit(self, off: int, i: int, value: int) -> None:
        for b, byte in enumerate(struct.pack("<I", value & 0xffffffff)):
            self.put_byte(off + 4 * i + b, byte)

    def wstr(self, text, extra: int = 16) -> int:
        units = [ord(c) for c in text] if isinstance(text, str) else list(text)
        off = self.alloc((len(units) + 1 + extra) * 4)
        for i, u in enumerate(units):
            self.put_unit(off, i, u)
        return off

    def bstr(self, data, extra: int = 16) -> int:
        data = data.encode("latin-1") if isinstance(data, str) else bytes(data)
        off = self.alloc(len(data) + 1 + extra)
        for i, b in enumerate(data):
            self.put_byte(off + i, b)
        return off

    def buf(self, nbytes: int) -> int:
        return self.alloc(nbytes)

    def wfill(self, off: int, count: int, value: int) -> None:
        for i in range(count):
            self.put_unit(off, i, value)

    def units(self, off: int, count: int) -> list[int]:
        return list(struct.unpack_from(f"<{count}i", self.mem, off))

    def unit(self, off: int, i: int) -> int:
        return struct.unpack_from("<i", self.mem, off + 4 * i)[0]

    def set_unit(self, off: int, i: int, value: int) -> None:
        struct.pack_into("<I", self.mem, off + 4 * i, value & 0xffffffff)

    def wlen(self, off: int) -> int:
        n = 0
        while self.unit(off, n) != 0:
            n += 1
        return n

    def text_units(self, off: int) -> list[int]:
        return self.units(off, self.wlen(off))

    # ------------------------------------------------------------ calls

    def call(self, fname: str, sig: str, args: list):
        fn = self.bind(fname, sig)
        letters, result = sig.split(">")
        parts = []
        k = self.uid()
        for j, (a, letter) in enumerate(zip(args, letters)):
            if isinstance(a, P):
                parts.append(self.ptr(a.off))
            elif a == NUL:
                parts.append(f"nul{k}x{j}=0")
            else:
                parts.append(f"v{k}x{j}={a}")
        self.emit(f"call{k}: r{k} = *{fn}({', '.join(parts)})")
        return f"r{k}", result

    def show(self, var: str, kind: str, shown: str, base: int | None = None) -> None:
        """Write what a call gave: `kind` is its letter, `shown` how (number, flag, place, double); the expected line
        is appended by the caller through `out`."""
        k = self.uid()
        if kind == "i" and shown in ("number", "flag", "sign"):
            self.emit(f"widen{k}: wide{k} = convert.int32ToInt64({var})")
            var = f"wide{k}"
        if kind == "f":
            self.emit(f"widen{k}: wide{k} = convert.float32ToFloat64({var})")
            var = f"wide{k}"
        if shown == "number":
            self.emit(f"show{k}: sayNumber({var})")
        elif shown == "sign":
            self.emit(f"show{k}: saySign({var})")
        elif shown == "flag":
            self.emit(f"show{k}: sayFlag({var})")
        elif shown == "place":
            self.emit(f"show{k}: sayPlace({var}, {self.ptr(base)})")
        elif shown == "double":
            self.emit(f"show{k}: sayDouble({var})")

    def run(self, fname, sig, args, shown, expected, base=None):
        var, kind = self.call(fname, sig, args)
        if shown is not None:
            self.show(var, kind, shown, base)
            self.out.append(str(expected))
        return var

    # ------------------------------------------------------------ checks

    def check_region(self, off: int, nbytes: int) -> None:
        """memcmp the bytes the call wrote with the model's, which the program stores in a region of its own."""
        want = self.alloc(nbytes)
        for i in range(nbytes):
            self.put_byte(want + i, self.mem[off + i])
        var, _ = self.call("memcmp", "ppp>i", [P(off), P(want), nbytes])
        k = self.uid()
        self.emit(f"widen{k}: wide{k} = convert.int32ToInt64({var})")
        self.emit(f"show{k}: sayEqual(wide{k})")
        self.out.append("1")

    def errno_clear(self) -> None:
        if self.err is None:
            var, _ = self.call("__errno_location", ">p", [])
            self.err = var
        k = self.uid()
        self.emit(f"clear{k}: cleared{k} = *memsetFn({self.err}, zero{k}=0, four{k}=4)")

    def errno_check(self, value: int) -> None:
        want = self.alloc(4)
        for b, byte in enumerate(struct.pack("<i", value)):
            self.put_byte(want + b, byte)
        k = self.uid()
        self.emit(f"cmp{k}: d{k} = *memcmpFn({self.err}, {self.ptr(want)}, four{k}=4)")
        self.emit(f"widen{k}: wide{k} = convert.int32ToInt64(d{k})")
        self.emit(f"show{k}: sayEqual(wide{k})")
        self.out.append("1")

    def prefill(self, off: int, nbytes: int) -> None:
        k = self.uid()
        self.emit(f"fill{k}: filled{k} = *memsetFn({self.ptr(off)}, ones{k}=255, size{k}={nbytes})")

    def end_check(self, cell: int, target: int | None) -> None:
        """The pointer stored at a cell is the address of a byte offset of the area (None: the null pointer)."""
        want = self.alloc(8)
        k = self.uid()
        if target is not None:
            self.emit(f"addr{k}: putAddress(memsetFn, {self.ptr(want)}, {self.ptr(target)})")
        self.emit(f"cmp{k}: d{k} = *memcmpFn({self.ptr(cell)}, {self.ptr(want)}, eight{k}=8)")
        self.emit(f"widen{k}: wide{k} = convert.int32ToInt64(d{k})")
        self.emit(f"show{k}: sayEqual(wide{k})")
        self.out.append("1")


# ---------------------------------------------------------------- the cases

INT_CASES = [("  -42xyz", 10), ("0x1F", 16), ("0x1F", 0), ("017", 0), ("abc", 10), ("0xg", 16), ("+7", 10),
             ("99999999999999999999", 10), ("-99999999999999999999", 10), ("zz", 36), ("  ", 10), ("-", 10),
             ("0", 0), ("08", 0), ("1_000", 10), ("-9223372036854775808", 10), ("9223372036854775807", 10),
             ("9223372036854775808", 10), ("18446744073709551615", 10), ("18446744073709551616", 10),
             ("-1", 10), ("\t\n 12", 10), ("0X7fffffffffffffff", 16), ("-0x10", 0), ("101", 2), ("12", 2),
             ([49, 50, 8364, 51], 10), ([65297, 50], 10), ([32, 160, 49], 10)]
REAL_CASES = ["3.25e2xyz", "  -0.5", ".5", "0x1p-2", "inf", "-infinity", "nan", "xyz", "1e400", "1e-400",
              "123456789012345678901234567890", "0.1", "-0", "1e", "1e+", "0x", "0x.8", "1.5e3z", "5.", "+.e1",
              "0x1.8p1", "1e22", "2.2250738585072014e-308", "1.7976931348623157e308", "  \t7", "-INF", "NaN",
              [49, 46, 53, 8364], [8364], "0.30000000000000004", "9007199254740993"]
FLOAT_CASES = ["0.1", "16777217", "1.000000059604644775390625", "1.00000005960464477539062500000001",
               "1.00000005960464477539062499999999", "0x1.00000100000000000000000001p0", "-0x1.8p1", "1e39",
               "3.4028235e38", "3.4028236e38", "1e-45", "0", "-0.0", "2.5", "340282356779733661637539395458142568447",
               "340282356779733661637539395458142568448", "16777219", "8388609.5", "1e-50", "inf",
               "nan", "abc", "3.14159265358979323846"]
STRINGS_CMP = [("abc", "abc"), ("abc", "abd"), ("abd", "abc"), ("ab", "abc"), ("abc", "ab"), ("", "a"), ("a", ""),
               ("", ""), ([256], [255]), ([8364], [97]), ([97, 98, 99, 88], [97, 98, 99, 89])]


def build() -> Tour:
    t = Tour()
    t.bind("calloc", "pp>p")
    t.bind("memset", "pip>p")
    t.bind("memcmp", "ppp>i")
    t.bind("free", "p>p")
    t.emit(f"takeArea: area = *callocFn(areaBytes={AREA}, one=1)")
    # Python has called setlocale(LC_CTYPE, "") (and may have coerced C to C.UTF-8), so glibc under `refined run` would
    # classify and convert as Unicode; the tour asks for the C locale itself first
    t.section("locale")
    name = t.bstr("C")
    t.run("setlocale", "ip>p", [6, P(name)], "flag", 1)
    t.section("classes")
    for name in ISW:
        t.bind(name, "i>i")
        t.emit(f"run{name}: everyFlag({name}Fn)")
        for c in range(-1, 301):
            t.out.append("1" if _class_of(name[3:], c) else "0")
        for k, c in enumerate(EXTRA_CODES):
            kk = t.uid()
            t.emit(f"extra{kk}: er{kk} = *{name}Fn(ex{kk}={c})")
            t.show(f"er{kk}", "i", "flag")
            t.out.append("1" if _class_of(name[3:], c) else "0")
    t.section("case")
    for name, delta, lo, hi in (("towlower", 32, 65, 90), ("towupper", -32, 97, 122)):
        t.bind(name, "i>i")
        t.emit(f"run{name}: everyRaw({name}Fn)")
        for c in range(-1, 301):
            t.out.append(str(c + delta if lo <= c <= hi else c))
        for c in EXTRA_CODES:
            kk = t.uid()
            t.emit(f"extra{kk}: er{kk} = *{name}Fn(ex{kk}={c})")
            t.show(f"er{kk}", "i", "number")
            t.out.append(str(c))
    t.section("names")
    names = CLASS_NAMES + ["", "unknown", "alnumx", "alnu", "ALPHA"]
    handles = {}
    t.bind("wctype", "p>p")
    t.bind("iswctype", "ip>i")
    for nm in names:
        off = t.bstr(nm)
        var = t.run("wctype", "p>p", [P(off)], "flag", 1 if nm in CLASS_NAMES else 0)
        handles[nm] = var
    for nm in CLASS_NAMES:
        t.emit(f"handle{nm}: everyHandle(iswctypeFn, {handles[nm]})")
        for c in range(-1, 201):
            t.out.append("1" if _class_of(nm, c) else "0")
    t.bind("wctrans", "p>p")
    t.bind("towctrans", "ip>i")
    trans = {}
    for nm in ("tolower", "toupper", "tocase", "", "TOLOWER"):
        off = t.bstr(nm)
        trans[nm] = t.run("wctrans", "p>p", [P(off)], "flag", 1 if nm in ("tolower", "toupper") else 0)
    for nm, delta, lo, hi in (("tolower", 32, 65, 90), ("toupper", -32, 97, 122)):
        t.emit(f"trans{nm}: everyTrans(towctransFn, {trans[nm]})")
        for c in range(-1, 201):
            t.out.append(str(c + delta if lo <= c <= hi else c))
    t.section("btowc")
    for name in ("btowc", "wctob"):
        t.bind(name, "i>i")
        t.emit(f"run{name}: everyRaw({name}Fn)")
        for c in range(-1, 301):
            t.out.append(str(c if 0 <= c <= 127 else -1))
    strings(t)
    numbers(t)
    multibyte(t)
    return t


def strings(t: Tour) -> None:
    t.section("lengths")
    for text in ("", "a", "hello", [104, 233, 8364, 108]):
        off = t.wstr(text)
        t.run("wcslen", "p>p", [P(off)], "number", len(text))
    for text, most in (("hello", 3), ("hello", 5), ("hello", 10), ("hello", 0), ("", 4)):
        off = t.wstr(text)
        t.run("wcsnlen", "pp>p", [P(off), most], "number", min(len(text), most))
    t.section("copies")
    src = t.wstr("hello")
    dst = t.wstr("")
    t.wfill(dst, 12, 120)
    t.run("wcscpy", "pp>p", [P(dst), P(src)], "place", 0, base=dst)
    for i, u in enumerate([104, 101, 108, 108, 111, 0]):
        t.set_unit(dst, i, u)
    t.check_region(dst, 14 * 4)
    for text, n in (("abc", 6), ("abcdef", 3), ("", 2), ("ab", 2), ("abc", 0)):
        s = t.wstr(text)
        d = t.wstr("")
        t.wfill(d, 10, 120)
        t.run("wcsncpy", "ppp>p", [P(d), P(s), n], "place", 0, base=d)
        units = [ord(c) for c in text][:n]
        for i in range(n):
            t.set_unit(d, i, units[i] if i < len(units) else 0)
        t.check_region(d, 12 * 4)
    for first, second in (("ab", "cde"), ("", "xyz"), ("abc", "")):
        d = t.wstr(first)
        s = t.wstr(second)
        t.run("wcscat", "pp>p", [P(d), P(s)], "place", 0, base=d)
        for i, u in enumerate([ord(c) for c in first + second] + [0]):
            t.set_unit(d, i, u)
        t.check_region(d, (len(first + second) + 3) * 4)
    for first, second, n in (("ab", "cdefg", 3), ("x", "yz", 5), ("ab", "cd", 0), ("", "abc", 3)):
        d = t.wstr(first)
        t.wfill(d, 0, 0)
        for i in range(len(first) + 1, len(first) + 9):
            t.put_unit(d, i, 121)
        s = t.wstr(second)
        t.run("wcsncat", "ppp>p", [P(d), P(s), n], "place", 0, base=d)
        for i, u in enumerate([ord(c) for c in first + second[:n]] + [0]):
            t.set_unit(d, i, u)
        t.check_region(d, (len(first) + n + 4) * 4)
    s = t.wstr([104, 233, 8364, 108, 111])
    var = t.run("wcsdup", "p>p", [P(s)], None, None)
    want = t.alloc(24)
    for i, u in enumerate(t.units(s, 6)):
        t.put_unit(want, i, u)
    k = t.uid()
    t.emit(f"dupcmp{k}: dd{k} = *memcmpFn({var}, {t.ptr(want)}, size{k}=24)")
    t.emit(f"widen{k}: wide{k} = convert.int32ToInt64(dd{k})")
    t.emit(f"show{k}: sayEqual(wide{k})")
    t.out.append("1")
    t.emit(f"dupfree{k}: freed{k} = *freeFn({var})")
    t.section("compares")
    for a, b in STRINGS_CMP:
        sa, sb = t.wstr(a), t.wstr(b)
        ua = [ord(c) for c in a] if isinstance(a, str) else a
        ub = [ord(c) for c in b] if isinstance(b, str) else b
        order = (ua > ub) - (ua < ub)
        t.run("wcscmp", "pp>i", [P(sa), P(sb)], "sign", order)
        t.run("wcscoll", "pp>i", [P(sa), P(sb)], "sign", order)
        for n in (0, 1, 3, 4):
            order_n = (ua[:n] > ub[:n]) - (ua[:n] < ub[:n])
            t.run("wcsncmp", "ppp>i", [P(sa), P(sb), n], "sign", order_n)
            t.run("wmemcmp", "ppp>i", [P(sa), P(sb), n], "sign",
                  (( (ua + [0] * 4)[:n] > (ub + [0] * 4)[:n]) - ((ua + [0] * 4)[:n] < (ub + [0] * 4)[:n])))
    t.bind("wcsxfrm", "ppp>p")
    for n in (10, 3, 6, 5, 1):
        s = t.wstr("hello")
        d = t.wstr("")
        t.wfill(d, 10, 120)
        t.run("wcsxfrm", "ppp>p", [P(d), P(s), n], "number", 5)
        for i, u in enumerate([104, 101, 108, 108, 111, 0][:n]):
            t.set_unit(d, i, u)
        t.check_region(d, 12 * 4)
    t.run("wcsxfrm", "ppp>p", [NUL, P(t.wstr("hello")), 0], "number", 5)
    t.section("searches")
    for text, value in (("hello", 108), ("hello", 111), ("hello", 0), ("hello", 122), ([97, 8364, 98], 8364),
                        ("", 0), ("", 97)):
        s = t.wstr(text)
        units = [ord(c) for c in text] if isinstance(text, str) else text
        first = (units + [0]).index(value) if value in units + [0] else -1
        last = len(units) - 1 - units[::-1].index(value) if value in units else (len(units) if value == 0 else -1)
        t.run("wcschr", "pi>p", [P(s), value], "place", first, base=s)
        t.run("wcsrchr", "pi>p", [P(s), value], "place", last, base=s)
    for hay, needle in (("hello world", "o w"), ("hello world", ""), ("abc", "d"), ("ab", "abc"), ("aab", "ab"),
                        ("aaaa", "aa"), ("hello world", "ld"), ("", "a"), ("", ""), ("abcabc", "cab")):
        h, n = t.wstr(hay), t.wstr(needle)
        t.run("wcsstr", "pp>p", [P(h), P(n)], "place", hay.find(needle), base=h)
    for text, other in (("abcde", "cba"), ("abc", ""), ("abc", "cba"), ("hello", "xl"), ("hello", "xyz"), ("", "a"),
                        ("hello", "ol"), ("hello", "lo")):
        s, o = t.wstr(text), t.wstr(other)
        span = 0
        while span < len(text) and text[span] in other:
            span += 1
        cspan = 0
        while cspan < len(text) and text[cspan] not in other:
            cspan += 1
        t.run("wcsspn", "pp>p", [P(s), P(o)], "number", span)
        t.run("wcscspn", "pp>p", [P(s), P(o)], "number", cspan)
        t.run("wcspbrk", "pp>p", [P(s), P(o)], "place", cspan if cspan < len(text) else -1, base=s)
    for value, n in ((108, 5), (108, 2), (0, 6), (111, 0), (104, 1), (122, 5)):
        s = t.wstr("hello")
        units = [104, 101, 108, 108, 111, 0, 0]
        found = units[:n].index(value) if value in units[:n] else -1
        t.run("wmemchr", "pip>p", [P(s), value, n], "place", found, base=s)
    t.section("memory")
    s = t.wstr("abcdef")
    d = t.wstr("")
    t.run("wmemcpy", "ppp>p", [P(d), P(s), 4], "place", 0, base=d)
    for i in range(4):
        t.set_unit(d, i, t.unit(s, i))
    t.check_region(d, 8 * 4)
    for dst_at, src_at, n in ((1, 0, 5), (0, 2, 4), (0, 0, 3), (2, 2, 0)):
        s = t.wstr("abcdef")
        t.run("wmemmove", "ppp>p", [P(s + 4 * dst_at), P(s + 4 * src_at), n], "place", dst_at, base=s)
        moved = t.units(s + 4 * src_at, n)
        for i, u in enumerate(moved):
            t.set_unit(s, dst_at + i, u)
        t.check_region(s, 8 * 4)
    d = t.wstr("")
    t.run("wmemset", "pip>p", [P(d), 65, 4], "place", 0, base=d)
    for i in range(4):
        t.set_unit(d, i, 65)
    t.check_region(d, 6 * 4)
    d = t.wstr("")
    t.run("wmemset", "pip>p", [P(d), 8364, 3], "place", 0, base=d)
    for i in range(3):
        t.set_unit(d, i, 8364)
    t.check_region(d, 5 * 4)
    t.section("tokens")
    delimiters = t.wstr(",;")
    save = t.buf(8)
    for text, tokens in ((",,a,b;;cc,,", None), ("word", None), ("", None), (",;,", None), ("x,y", None)):
        s = t.wstr(text)
        units = [ord(c) for c in text]
        walk = 0
        first = True
        result = []
        position = 0
        # the walk glibc's wcstok makes: skip delimiters, take up to the next one
        cur = 0
        while True:
            while cur < len(units) and chr(units[cur]) in ",;":
                cur += 1
            if cur >= len(units):
                result.append(-1)
                break
            begin = cur
            while cur < len(units) and chr(units[cur]) not in ",;":
                cur += 1
            result.append(begin)
            if cur < len(units):
                units[cur] = 0
                cur += 1
        for k, expected in enumerate(result):
            t.run("wcstok", "ppp>p", [P(s) if k == 0 else NUL, P(delimiters), P(save)], "place", expected, base=s)
        for i, u in enumerate(units):
            t.set_unit(s, i, u)
        t.check_region(s, (len(units) + 1) * 4)
        # a further call after the end gives nothing
        t.run("wcstok", "ppp>p", [NUL, P(delimiters), P(save)], "place", -1, base=s)


def numbers(t: Tour) -> None:
    t.section("integers")
    for name, unsigned in (("wcstol", False), ("wcstoll", False), ("wcstoul", True), ("wcstoull", True)):
        for text, base in INT_CASES:
            units = [ord(c) for c in text] if isinstance(text, str) else text
            s = t.wstr(text)
            cell = t.buf(8)
            t.prefill(cell, 8)
            t.errno_clear()
            value, end, errno = parse_int(units, base, unsigned)
            var, kind = t.call(name, "ppi>p", [P(s), P(cell), base])
            t.errno_check(errno)
            t.show(var, kind, "number")
            t.out.append(str(value))
            t.end_check(cell, s + 4 * end)
    s = t.wstr("77")
    t.run("wcstol", "ppi>p", [P(s), NUL, 10], "number", 77)
    t.section("reals")
    for text in REAL_CASES:
        units = [ord(c) for c in text] if isinstance(text, str) else text
        s = t.wstr(text)
        cell = t.buf(8)
        t.prefill(cell, 8)
        t.errno_clear()
        value, end, errno = parse_real(units, False)
        var, kind = t.call("wcstod", "pp>d", [P(s), P(cell)])
        t.errno_check(errno)
        t.show(var, kind, "double")
        t.out.append(repr(value))
        t.end_check(cell, s + 4 * end)
    t.section("floats")
    for text in FLOAT_CASES:
        units = [ord(c) for c in text] if isinstance(text, str) else text
        s = t.wstr(text)
        cell = t.buf(8)
        t.prefill(cell, 8)
        t.errno_clear()
        value, end, errno = parse_real(units, True)
        var, kind = t.call("wcstof", "pp>f", [P(s), P(cell)])
        t.errno_check(errno)
        t.show(var, kind, "double")
        t.out.append(repr(value))
        t.end_check(cell, s + 4 * end)


def multibyte(t: Tour) -> None:
    t.section("state")
    state = t.buf(8)
    t.run("mbsinit", "p>i", [P(state)], "flag", 1)
    t.run("mbsinit", "p>i", [NUL], "flag", 1)
    t.section("mbrlen")
    for byte, n in ((65, 1), (0, 1), (65, 0), (65, 4), (127, 1)):
        s = t.bstr([byte])
        expected = -2 if n == 0 else (0 if byte == 0 else 1)
        t.run("mbrlen", "ppp>p", [P(s), n, P(state)], "number", expected)
    t.section("mbrtowc")
    for byte, n in ((65, 1), (0, 1), (65, 0), (122, 3), (127, 1)):
        s = t.bstr([byte])
        w = t.buf(4)
        t.put_unit(w, 0, 7)
        expected = -2 if n == 0 else (0 if byte == 0 else 1)
        t.run("mbrtowc", "pppp>p", [P(w), P(s), n, P(state)], "number", expected)
        if n:
            t.set_unit(w, 0, byte)
        t.check_region(w, 4)
    s = t.bstr("A")
    t.run("mbrtowc", "pppp>p", [NUL, P(s), 1, NUL], "number", 1)
    t.section("wcrtomb")
    for wide in (65, 0, 127, 66, 256, 8364, 1114111):
        d = t.buf(8)
        t.put_byte(d, 33)
        t.errno_clear()
        ok = 0 <= wide <= 127
        var, kind = t.call("wcrtomb", "pip>p", [P(d), wide, P(state)])
        t.errno_check(0 if ok else 84)
        t.show(var, kind, "number")
        t.out.append("1" if ok else "-1")
        if ok:
            t.mem[d] = wide
        t.check_region(d, 4)
    t.run("wcrtomb", "pip>p", [NUL, 8364, NUL], "number", 1)
    t.section("mblen")
    for byte, n in ((65, 1), (0, 1), (65, 0), (90, 2)):
        s = t.bstr([byte])
        t.run("mblen", "pp>i", [P(s), n], "number", -1 if n == 0 else (0 if byte == 0 else 1))
    t.run("mblen", "pp>i", [NUL, 0], "number", 0)
    t.section("mbtowc")
    for byte, n in ((65, 1), (0, 1), (65, 0), (90, 2)):
        s = t.bstr([byte])
        w = t.buf(4)
        t.put_unit(w, 0, 7)
        expected = -1 if n == 0 else (0 if byte == 0 else 1)
        t.run("mbtowc", "ppp>i", [P(w), P(s), n], "number", expected)
        if n:
            t.set_unit(w, 0, byte)
        t.check_region(w, 4)
    t.run("mbtowc", "ppp>i", [NUL, NUL, 0], "number", 0)
    t.section("wctomb")
    for wide in (65, 0, 66, 256, 8364):
        d = t.buf(8)
        t.put_byte(d, 33)
        ok = 0 <= wide <= 127
        t.run("wctomb", "pi>i", [P(d), wide], "number", 1 if ok else -1)
        if ok:
            t.mem[d] = wide
        t.check_region(d, 4)
    t.run("wctomb", "pi>i", [NUL, 0], "number", 0)
    t.section("mbstowcs")
    for text, n in (("hello", 10), ("hello", 3), ("hello", 5), ("hello", 6), ("", 4), ("hello", 0)):
        s = t.bstr(text)
        d = t.wstr("")
        t.wfill(d, 12, 120)
        count = min(len(text), n)
        t.run("mbstowcs", "ppp>p", [P(d), P(s), n], "number", count)
        for i, ch in enumerate(text[:count]):
            t.set_unit(d, i, ord(ch))
        if count < n:
            t.set_unit(d, count, 0)
        t.check_region(d, 14 * 4)
    t.run("mbstowcs", "ppp>p", [NUL, P(t.bstr("hello")), 0], "number", 5)
    t.section("wcstombs")
    for units, n in (([104, 101, 108, 108, 111], 10), ([104, 101, 108, 108, 111], 3), ([104, 101, 108, 108, 111], 5),
                     ([104, 101, 108, 108, 111], 6), ([], 4), ([97, 8364, 98], 10), ([97, 98, 256], 10),
                     ([97, 98, 256], 2)):
        s = t.wstr(units)
        d = t.buf(16)
        for i in range(12):
            t.put_byte(d + i, 120)
        t.errno_clear()
        bad = next((i for i, u in enumerate(units) if u > 127), None)
        if bad is not None and bad < n:
            expected, errno = -1, 84
        else:
            count = min(len(units), n)
            expected, errno = count, 0
            for i in range(count):
                t.mem[d + i] = units[i]
            if count < n:
                t.mem[d + count] = 0
        var, kind = t.call("wcstombs", "ppp>p", [P(d), P(s), n])
        t.errno_check(errno)
        t.show(var, kind, "number")
        t.out.append(str(expected))
        if expected >= 0:
            t.check_region(d, 12)
    t.run("wcstombs", "ppp>p", [NUL, P(t.wstr("hello")), 0], "number", 5)
    t.errno_clear()
    var, kind = t.call("wcstombs", "ppp>p", [NUL, P(t.wstr([97, 8364])), 0])
    t.errno_check(84)
    t.show(var, kind, "number")
    t.out.append("-1")
    t.section("mbsrtowcs")
    cell = t.buf(8)
    s = t.bstr("hello")
    d = t.wstr("")
    t.wfill(d, 12, 120)
    for n, start in ((3, 0), (10, 3)):
        # the cell holds the source's address, which the program stores a byte at a time
        k = t.uid()
        t.emit(f"src{k}: putAddress(memsetFn, {t.ptr(cell)}, {t.ptr(s + start)})")
        if n == 3:
            t.run("mbsrtowcs", "pppp>p", [P(d), P(cell), n, P(state)], "number", 3)
            for i, ch in enumerate("hel"):
                t.set_unit(d, i, ord(ch))
            t.check_region(d, 14 * 4)
            t.end_check(cell, s + 3)
        else:
            t.run("mbsrtowcs", "pppp>p", [P(d + 12), P(cell), n, P(state)], "number", 2)
            for i, ch in enumerate("lo"):
                t.set_unit(d, 3 + i, ord(ch))
            t.set_unit(d, 5, 0)
            t.check_region(d, 14 * 4)
            t.end_check(cell, None)
    k = t.uid()
    t.emit(f"src{k}: putAddress(memsetFn, {t.ptr(cell)}, {t.ptr(s)})")
    t.run("mbsrtowcs", "pppp>p", [NUL, P(cell), 0, P(state)], "number", 5)
    t.end_check(cell, s)
    t.section("wcsrtombs")
    w = t.wstr("abcde")
    d = t.buf(16)
    k = t.uid()
    t.emit(f"src{k}: putAddress(memsetFn, {t.ptr(cell)}, {t.ptr(w)})")
    t.run("wcsrtombs", "pppp>p", [P(d), P(cell), 2, P(state)], "number", 2)
    t.mem[d], t.mem[d + 1] = 97, 98
    t.check_region(d, 8)
    t.end_check(cell, w + 8)
    t.run("wcsrtombs", "pppp>p", [P(d), P(cell), 10, P(state)], "number", 3)
    t.mem[d:d + 4] = bytes([99, 100, 101, 0])
    t.check_region(d, 8)
    t.end_check(cell, None)
    k = t.uid()
    t.emit(f"src{k}: putAddress(memsetFn, {t.ptr(cell)}, {t.ptr(w)})")
    t.run("wcsrtombs", "pppp>p", [NUL, P(cell), 0, P(state)], "number", 5)
    t.end_check(cell, w)
    bad = t.wstr([97, 98, 8364, 99])
    k = t.uid()
    t.emit(f"src{k}: putAddress(memsetFn, {t.ptr(cell)}, {t.ptr(bad)})")
    t.errno_clear()
    var, kind = t.call("wcsrtombs", "pppp>p", [P(d), P(cell), 10, P(state)])
    t.errno_check(84)
    t.show(var, kind, "number")
    t.out.append("-1")
    t.end_check(cell, bad + 8)
    t.section("uchar")
    for byte, n in ((90, 1), (0, 1), (90, 0)):
        s = t.bstr([byte])
        w = t.buf(4)
        t.put_unit(w, 0, 7)
        expected = -2 if n == 0 else (0 if byte == 0 else 1)
        t.run("mbrtoc16", "pppp>p", [P(w), P(s), n, P(state)], "number", expected)
        if n:
            struct.pack_into("<H", t.mem, w, byte)
        t.check_region(w, 2)
        w32 = t.buf(4)
        t.put_unit(w32, 0, 7)
        t.run("mbrtoc32", "pppp>p", [P(w32), P(s), n, P(state)], "number", expected)
        if n:
            t.set_unit(w32, 0, byte)
        t.check_region(w32, 4)
    for wide in (70, 0, 256, 8364):
        for name in ("c16rtomb", "c32rtomb"):
            d = t.buf(8)
            t.put_byte(d, 33)
            t.errno_clear()
            ok = 0 <= wide <= 127
            var, kind = t.call(name, "pip>p", [P(d), wide, P(state)])
            t.errno_check(0 if ok else 84)
            t.show(var, kind, "number")
            t.out.append("1" if ok else "-1")
            if ok:
                t.mem[d] = wide
            t.check_region(d, 4)
    t.section("high bytes")
    for byte in (128, 233, 255):
        s = t.bstr([byte])
        w = t.buf(4)
        t.put_unit(w, 0, 7)
        t.run("mbrlen", "ppp>p", [P(s), 1, NUL], "number", -1)
        t.errno_clear()
        var, kind = t.call("mbrtowc", "pppp>p", [P(w), P(s), 1, NUL])
        t.errno_check(84)
        t.show(var, kind, "number")
        t.out.append("-1")
        t.check_region(w, 4)
        d = t.buf(8)
        t.errno_clear()
        var, kind = t.call("wcrtomb", "pip>p", [P(d), byte, NUL])
        t.errno_check(84)
        t.show(var, kind, "number")
        t.out.append("-1")
        t.check_region(d, 4)


# ---------------------------------------------------------------- the program

def _dsl(t: Tour) -> str:
    optypes = "\n".join(v for k, v in t.sigs.items() if not k.endswith("#name"))
    caps = "\n\n".join(dict.fromkeys(t.caps))
    uses = "\n".join(f"  uses {c.split()[1]}" for c in dict.fromkeys(t.caps))
    body = "\n".join(t.binds) + "\n" + "\n".join(t.body)
    return f'''module cwidetour "Call the runtime's wide-character and multibyte C functions through ffi and print what each gives"
  path cwidetour
  imports standard.console standard.ffi standard.convert standard.compare standard.math standard.bits
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

capability cLibrary "Authority to load the C library and nothing else" load ffi.libraries "c"

{caps}

{optypes}

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

op sayFlag "Write 1 for a whole number that is not 0, else 0"
  input value Int64 copied
  effect write console.stdout
  uses stdoutWriter
  let zero Int64 0
  let yes Int64 1
:begin
  zeroCheck: isZero = compare.equalInt64(value, zero)
  if isZero zeroCase some
:zeroCase
  noLine: sayNumber(zero)
  return
:some
  yesLine: sayNumber(yes)
  return

op saySign "Write -1, 0, or 1 as a whole number is negative, 0, or positive"
  input value Int64 copied
  effect write console.stdout
  uses stdoutWriter
  let zero Int64 0
  let minus Int64 -1
  let plus Int64 1
:begin
  zeroCheck: isZero = compare.equalInt64(value, zero)
  if isZero zeroCase signCheck
:zeroCase
  zeroLine: sayNumber(zero)
  return
:signCheck
  negativeCheck: negative = compare.lessThanInt64(value, zero)
  if negative below above
:below
  minusLine: sayNumber(minus)
  return
:above
  plusLine: sayNumber(plus)
  return

op sayEqual "Write 1 for a memcmp result of 0, else 0"
  input value Int64 copied
  effect write console.stdout
  uses stdoutWriter
  let zero Int64 0
  let yes Int64 1
:begin
  zeroCheck: isZero = compare.equalInt64(value, zero)
  if isZero same differs
:same
  yesLine: sayNumber(yes)
  return
:differs
  noLine: sayNumber(zero)
  return

op sayPlace "Write the index of a wide place in an array, or -1 for the address 0"
  input place Int64 copied
  input base Int64 copied
  effect write console.stdout
  uses stdoutWriter
  let zero Int64 0
  let four Int64 4
  let missing Int64 -1
:begin
  zeroCheck: isZero = compare.equalInt64(place, zero)
  if isZero absent present
:absent
  missingLine: sayNumber(missing)
  return
:present
  distance: bytes = math.subtractInt64(place, base)
  index: units = math.divideInt64(bytes, four)
  indexLine: sayNumber(units)
  return

op putByteAt "Put one byte at an address moved on by an offset, through memset"
  input setter SigPIPToPFunction copied
  input base Int64 copied
  input offset Int64 copied
  input code Int32 copied
:begin
  findAt: at = math.addInt64(base, offset)
  setIt: unused = *setter(at, code, one=1)
  return

op putAddress "Put an address at an address, a byte at a time through memset (low byte first)"
  input setter SigPIPToPFunction copied
  input target Int64 copied
  input value Int64 copied
  let step Int64 0 mut
  let eight Int64 8
  let eightBits Int64 8
  let mask Int64 255
  let unit Int64 1
:begin
  goto eachByte
:eachByte loop=while max=eight
  doneCheck: done = compare.greaterOrEqualInt64(step, eight)
  if done finish store
:store in=eachByte
  shiftBy: shift = math.multiplyInt64(step, eightBits)
  shifted: moved = bits.shiftRightInt64(value, shift)
  lowBits: low = bits.andInt64(moved, mask)
  narrow: lowInt = convert.int64ToInt32(low)
  findAt: at = math.addInt64(target, step)
  setIt: unused = *setter(at, lowInt, unit)
  stepIt: next = math.addInt64(step, unit)
  set step next
  goto eachByte
:finish
  return

op everyFlag "Call a function of an int with each code from -1 to 300 and write whether it is not 0"
  input callee SigIToIFunction copied
  effect write console.stdout
  uses stdoutWriter
  let code Int32 -1 mut
  let codes Int64 400
:begin
  goto eachCode
:eachCode loop=while max=codes
  doneCheck: done = compare.greaterThanInt32(code, last=300)
  if done finish call
:call in=eachCode
  callIt: result = *callee(code)
  widenIt: wide = convert.int32ToInt64(result)
  showIt: sayFlag(wide)
  stepIt: next = math.addInt32(code, one32=1)
  set code next
  goto eachCode
:finish
  return

op everyRaw "Call a function of an int with each code from -1 to 300 and write what it gives"
  input callee SigIToIFunction copied
  effect write console.stdout
  uses stdoutWriter
  let code Int32 -1 mut
  let codes Int64 400
:begin
  goto eachCode
:eachCode loop=while max=codes
  doneCheck: done = compare.greaterThanInt32(code, last=300)
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

op everyHandle "Call iswctype with each code from -1 to 200 and a handle and write whether it is not 0"
  input callee SigIPToIFunction copied
  input handle Int64 copied
  effect write console.stdout
  uses stdoutWriter
  let code Int32 -1 mut
  let codes Int64 400
:begin
  goto eachCode
:eachCode loop=while max=codes
  doneCheck: done = compare.greaterThanInt32(code, last=200)
  if done finish call
:call in=eachCode
  callIt: result = *callee(code, handle)
  widenIt: wide = convert.int32ToInt64(result)
  showIt: sayFlag(wide)
  stepIt: next = math.addInt32(code, one32=1)
  set code next
  goto eachCode
:finish
  return

op everyTrans "Call towctrans with each code from -1 to 200 and a handle and write what it gives"
  input callee SigIPToIFunction copied
  input handle Int64 copied
  effect write console.stdout
  uses stdoutWriter
  let code Int32 -1 mut
  let codes Int64 400
:begin
  goto eachCode
:eachCode loop=while max=codes
  doneCheck: done = compare.greaterThanInt32(code, last=200)
  if done finish call
:call in=eachCode
  callIt: result = *callee(code, handle)
  widenIt: wide = convert.int32ToInt64(result)
  showIt: sayNumber(wide)
  stepIt: next = math.addInt32(code, one32=1)
  set code next
  goto eachCode
:finish
  return

op main "Open the C library, call each function, and write what it gave"
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


def write_project(folder: str) -> "Tour":
    """The project: build.sem and cwidetour.sem, generated from the DSL above; the Tour that wrote it."""
    from semgen import Generator, Module, Program
    from caselib import allows_rows
    t = build()
    dsl = _dsl(t)
    prog = Program()
    m = Module("cwidetour")
    prog.modules["cwidetour"] = m
    g = Generator(prog, m)
    g.declare(dsl)
    g.parse(dsl)
    sem, _tests = g.render(["# The runtime's wide-character C functions through ffi (tests/cwidetour.py)."], None)
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
    with open(os.path.join(folder, "cwidetour.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(sem)
    rows = ["tourProject is project", 'tourProject purpose "Call the runtime\'s wide-character C functions through ffi"',
            "tourProject target console", 'tourProject version "0.1.0"', "tourProject language refined 1",
            "tourProject standardLibrary 1", *allows_rows("tourProject", [sem]), "tourProject requires none",
            "tourProject includesModule cwidetour", "tourProject entry cwidetour.main"]
    with open(os.path.join(folder, "build.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")
    return t


def expected() -> list[str]:
    """What the tour prints when the C library behaves as glibc does in the C locale."""
    return build().out
