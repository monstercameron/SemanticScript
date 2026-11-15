"""The stdio part of tests/ctour.py (D-159, D-160): printf through `ffi` with doubles and pairs of longs, each line
flushed at once (fflush(NULL)) so C's output and the program's keep their order under `refined run` too, and sscanf
of numbers and words, each stored value compared with the bytes glibc would store (memcmp).

`dsl_parts()` gives what ctour's DSL needs: capabilities, optypes, bindings, helper operations, and the lines of
`main`; `expected()` what glibc prints for them, computed here: Python's own `%` formatting where it is C's, and
small models of C's integer conversions, of infinities and NaN padded with spaces, and of %a.
"""
from __future__ import annotations

import math
import struct

DOUBLE_FORMATS = ["[%.3f]", "[%e]", "[%g]", "[%a]", "[%10.4f]", "[%-12.3e]", "[%+.0f]", "[%#g]", "[%G]",
                  "[%.17g]", "[%08.2f]", "[%.0e]", "[%.1a]", "[%A]"]
LONG_FORMATS = ["[%ld %lx]", "[%5d|%-5d]", "[%+i % d]", "[%08.3x|%#X]", "[%lu %lo]", "[%hhd %hu]",
                "[%.0d|%.5i]", "[%#o %#lx]"]
LONG_PAIRS = [(0, 0), (1, -1), (255, -255), (2147483647, -2147483648), (9223372036854775807, -9223372036854775808),
              (4294967296, 65535)]
SCAN_TEXT = "  42 -0x1F 3.25e2 word rest"
SCAN_FORMAT = "%d %i %lf %4s"


def _bits(x: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def _wrap(value: int, bits: int) -> int:
    value &= (1 << bits) - 1
    return value - (1 << bits) if value >> (bits - 1) else value


# ---------------------------------------------------------------- C's conversions, modelled

def _spec(text: str):
    """(flags, width, precision or None, length, conversion) of a conversion like `%-08.3lx`."""
    i = 1
    flags = ""
    while text[i] in "-+ #0":
        flags += text[i]
        i += 1
    width = ""
    while text[i].isdigit():
        width += text[i]
        i += 1
    precision = None
    if text[i] == ".":
        i += 1
        digits = ""
        while text[i].isdigit():
            digits += text[i]
            i += 1
        precision = int(digits or "0")
    length = ""
    while text[i] in "hl":
        length += text[i]
        i += 1
    return flags, int(width or "0"), precision, length, text[i]


def _pad(flags: str, width: int, sign: str, prefix: str, body: str, zero_ok: bool) -> str:
    pad = width - len(sign) - len(prefix) - len(body)
    if pad <= 0:
        return sign + prefix + body
    if "-" in flags:
        return sign + prefix + body + " " * pad
    if "0" in flags and zero_ok:
        return sign + prefix + "0" * pad + body
    return " " * pad + sign + prefix + body


def c_integer(spec: str, value: int) -> str:
    flags, width, precision, length, conv = _spec(spec)
    bits = {"hh": 8, "h": 16, "": 32, "l": 64, "ll": 64}[length]
    signed = conv in "di"
    v = value & ((1 << bits) - 1)
    if signed:
        v = _wrap(v, bits)
    negative, magnitude = v < 0, abs(v)
    base = {"d": "d", "i": "d", "u": "d", "o": "o", "x": "x", "X": "X"}[conv]
    digits = "" if magnitude == 0 and precision == 0 else format(magnitude, base)
    if precision is not None and precision > len(digits):
        digits = "0" * (precision - len(digits)) + digits
    prefix = ""
    if "#" in flags:
        if conv == "o" and not digits.startswith("0"):
            digits = "0" + digits
        if conv in "xX" and magnitude:
            prefix = "0" + conv
    sign = "-" if negative else ("+" if "+" in flags and signed else (" " if " " in flags and signed else ""))
    return _pad(flags, width, sign, prefix, digits, precision is None)


def _hex_body(x: float, precision, flags: str) -> str:
    b = _bits(abs(x))
    biased, fraction = b >> 52, b & ((1 << 52) - 1)
    if b == 0:
        lead, exp = 0, 0
    elif biased == 0:
        lead, exp = 0, -1022
    else:
        lead, exp = 1, biased - 1023
    digits = "%013x" % fraction
    if precision is None:
        digits = digits.rstrip("0")
    elif precision < 13:
        kept, rest = int(digits[:precision] or "0", 16), digits[precision:]
        half = "8" + "0" * (len(rest) - 1)
        parity = kept if precision else lead
        if rest > half or (rest == half and parity % 2 == 1):
            kept += 1
            if kept == 16 ** precision:
                kept, lead = 0, lead + 1
        digits = ("%0*x" % (precision, kept)) if precision else ""
    else:
        digits += "0" * (precision - 13)
    point = "." if digits or "#" in flags else ""
    return f"{lead}{point}{digits}p{'+' if exp >= 0 else '-'}{abs(exp)}"


def c_double(spec: str, x: float) -> str:
    flags, width, precision, _length, conv = _spec(spec)
    negative = math.copysign(1.0, x) < 0
    sign = "-" if negative else ("+" if "+" in flags else (" " if " " in flags else ""))
    if math.isinf(x) or math.isnan(x):
        body = "inf" if math.isinf(x) else "nan"
        return _pad(flags, width, sign, "", body.upper() if conv.isupper() else body, False)
    if conv in "aA":
        body = _hex_body(x, precision, flags)
        prefix = "0x"
        if conv == "A":
            body, prefix = body.upper(), "0X"
        return _pad(flags, width, sign, prefix, body, True)
    shown = ("%" + flags.replace("-", "").replace("0", "") + ("" if precision is None else f".{precision}") + conv) % abs(x)
    shown = shown.lstrip("+ ")
    return _pad(flags, width, sign, "", shown, True)


def c_format(fmt: str, values) -> str:
    """A whole format of the kinds the tour uses, with its values in order."""
    out, i, at = "", 0, 0
    while i < len(fmt):
        if fmt[i] != "%":
            out += fmt[i]
            i += 1
            continue
        j = i + 1
        while fmt[j] not in "diuoxXfFeEgGaA":
            j += 1
        spec = fmt[i:j + 1]
        value = values[at]
        at += 1
        out += c_double(spec, value) if spec[-1] in "fFeEgGaA" else c_integer(spec, value)
        i = j + 1
    return out


# ---------------------------------------------------------------- the DSL

def _write_text(name: str, offset: int, text: str) -> list[str]:
    """Lines of `main` that put a C string at area + offset, a byte at a time through memset."""
    lines = []
    for k, ch in enumerate(text.encode() + b"\0"):
        lines.append(f"  put{name}{k}: putByteAt(memsetFn, area, at{name}{k}={offset + k}, code{name}{k}={ch})")
    return lines


def dsl_parts():
    caps = [f'capability {n}Symbol "Authority to bind the C function {n}" load ffi.symbols "{n}"'
            for n in ("printf", "fflush", "sscanf", "memcmp", "puts")]
    optypes = '''optype PrintDoubleFunction "int printf(const char *, double)"
  input format Int64 copied
  input value Float64 copied
  output Int32

optype PrintLongsFunction "int printf(const char *, long, long)"
  input format Int64 copied
  input first Int64 copied
  input second Int64 copied
  output Int32

optype FlushFunction "int fflush(FILE *)"
  input stream Int64 copied
  output Int32

optype ScanFunction "int sscanf(const char *, const char *, void *, void *, void *, void *)"
  input text Int64 copied
  input format Int64 copied
  input first Int64 copied
  input second Int64 copied
  input third Int64 copied
  input fourth Int64 copied
  output Int32

optype CompareFunction "int memcmp(const void *, const void *, size_t)"
  input left Int64 copied
  input right Int64 copied
  input bytes Int64 copied
  output Int32

optype PutsFunction "int puts(const char *)"
  input text Int64 copied
  output Int32

instance PrintDoubleBinding "Binds printf for one double" ffi.Function PrintDoubleFunction

instance PrintLongsBinding "Binds printf for two longs" ffi.Function PrintLongsFunction

instance FlushBinding "Binds fflush" ffi.Function FlushFunction

instance ScanBinding "Binds sscanf for four pointers" ffi.Function ScanFunction

instance CompareBinding "Binds memcmp" ffi.Function CompareFunction

instance PutsBinding "Binds puts" ffi.Function PutsFunction
'''
    lets = "\n".join(f"  let double{i}Bits UInt64 {_bits(x)}" for i, x in enumerate(_doubles()))
    reads = "\n".join(f"  read{i}: value{i} = convert.uint64BitsToFloat64(double{i}Bits)\n"
                      f"  print{i}: count{i} = *printFn(format, value{i})\n"
                      f"  flush{i}: flushed{i} = *flushFn(nothing=0)\n"
                      f"  widen{i}: wide{i} = convert.int32ToInt64(count{i})\n"
                      f"  show{i}: sayNumber(wide{i})" for i in range(len(_doubles())))
    pairs = "\n".join(f"  print{i}: count{i} = *printFn(format, first{i}={a}, second{i}={b})\n"
                      f"  flush{i}: flushed{i} = *flushFn(nothing=0)\n"
                      f"  widen{i}: wide{i} = convert.int32ToInt64(count{i})\n"
                      f"  show{i}: sayNumber(wide{i})" for i, (a, b) in enumerate(LONG_PAIRS))
    helpers = f'''op putByteAt "Put one byte at an address moved on by an offset, through memset"
  input setter SetFunction copied
  input base Int64 copied
  input offset Int64 copied
  input code Int32 copied
:begin
  findAt: at = math.addInt64(base, offset)
  setIt: unused = *setter(at, code, one=1)
  return

op everyDoubleFormat "printf one format with each of the tour's doubles, flushing after each, and write how many bytes each wrote"
  input printFn PrintDoubleFunction copied
  input flushFn FlushFunction copied
  input format Int64 copied
  effect write console.stdout
  uses stdoutWriter
{lets}
:begin
{reads}
  return

op everyLongPair "printf one format with each of the tour's pairs of longs, flushing after each, and write how many bytes each wrote"
  input printFn PrintLongsFunction copied
  input flushFn FlushFunction copied
  input format Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
{pairs}
  return
'''
    body = ['  bindprintfDouble: printFn = PrintDoubleBinding.bind(libc, printfName="printf") ? failed',
            '  bindprintfLongs: printLongsFn = PrintLongsBinding.bind(libc, printfName2="printf") ? failed',
            '  bindfflush: flushFn = FlushBinding.bind(libc, fflushName="fflush") ? failed',
            '  bindsscanf: scanFn = ScanBinding.bind(libc, sscanfName="sscanf") ? failed',
            '  bindmemcmp: compareFn = CompareBinding.bind(libc, memcmpName="memcmp") ? failed',
            '  bindputs: putsFn = PutsBinding.bind(libc, putsName="puts") ? failed',
            '  takeArea: area = *callocFn(areaBytes=8192, one=1)']
    offset = 0
    for k, fmt in enumerate(DOUBLE_FORMATS):
        body += _write_text(f"D{k}", offset, fmt + "\n")
        body.append(f"  findD{k}: formatD{k} = math.addInt64(area, offD{k}={offset})")
        body.append(f"  runD{k}: everyDoubleFormat(printFn, flushFn, formatD{k})")
        offset += len(fmt) + 2
    for k, fmt in enumerate(LONG_FORMATS):
        body += _write_text(f"L{k}", offset, fmt + "\n")
        body.append(f"  findL{k}: formatL{k} = math.addInt64(area, offL{k}={offset})")
        body.append(f"  runL{k}: everyLongPair(printLongsFn, flushFn, formatL{k})")
        offset += len(fmt) + 2
    text_at, format_at, cells_at, want_at = 4096, 4160, 4224, 4480
    body += _write_text("T", text_at, SCAN_TEXT)
    body += _write_text("F", format_at, SCAN_FORMAT)
    body.append(f"  findT: scanText = math.addInt64(area, textOff={text_at})")
    body.append(f"  findF: scanFormat = math.addInt64(area, formatOff={format_at})")
    for c in range(4):
        body.append(f"  findC{c}: cell{c} = math.addInt64(area, cellOff{c}={cells_at + 64 * c})")
    body.append("  scanIt: scanned = *scanFn(scanText, scanFormat, cell0, cell1, cell2, cell3)")
    body.append("  widenScanned: scannedWide = convert.int32ToInt64(scanned)")
    body.append("  showScanned: sayNumber(scannedWide)")
    stored = [struct.pack("<i", 42), struct.pack("<i", -31), struct.pack("<d", 325.0)]
    for c, data in enumerate(stored):
        for k, byte in enumerate(data):
            body.append(f"  wantC{c}b{k}: putByteAt(memsetFn, area, wantOff{c}x{k}={want_at + 16 * c + k}, "
                        f"wantByte{c}x{k}={byte})")
        body.append(f"  findWant{c}: want{c} = math.addInt64(area, wantAt{c}={want_at + 16 * c})")
        body.append(f"  compareC{c}: same{c} = *compareFn(cell{c}, want{c}, bytes{c}={len(data)})")
        body.append(f"  widenSame{c}: sameWide{c} = convert.int32ToInt64(same{c})")
        body.append(f"  showSame{c}: sayNumber(sameWide{c})")
    body.append("  putWord: wordCount = *putsFn(cell3)")
    body.append("  flushWord: wordFlushed = *flushFn(nothing=0)")
    body.append("  freeArea: areaFreed = *freeFn(area)")
    return caps, optypes, helpers, body


def _doubles():
    import ctour
    return ctour.DOUBLE_INPUTS


def expected() -> list[str]:
    out = []
    for fmt in DOUBLE_FORMATS:
        for x in _doubles():
            line = c_format(fmt, [x])
            out += [line, str(len(line) + 1)]
    for fmt in LONG_FORMATS:
        for a, b in LONG_PAIRS:
            line = c_format(fmt, [a, b])
            out += [line, str(len(line) + 1)]
    out += ["4", "0", "0", "0", "word"]
    return out
