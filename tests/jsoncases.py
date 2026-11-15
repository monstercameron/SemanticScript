"""The texts tests/jsontour.py is run on (D-151): one per line, valid JSON of every kind and texts broken at every
place, chosen deterministically from a seed so a failure can be reproduced."""
from __future__ import annotations

import json
import random

FIXED = [
    "null", "true", "false", "0", "-0", "1", "-1", "9223372036854775807", "-9223372036854775808",
    "9223372036854775808", "-9223372036854775809", "123456789012345678901234567890", "0.0", "-0.0", "1.5", "1e5",
    "1E5", "1e-5", "1e+5", "1.0e400", "-1e400", "1e-400", "2.5E-3", "0.1", "100.0", "1e16", "5e-324",
    "1.7976931348623157e308", "4.9e-324", "NaN", "Infinity", "-Infinity", "-NaN", "nan", "infinity", "01", "-01",
    "1.", ".5", "1.e5", "1e", "1e+", "1e-", "-", "+1", "--1", "1.5.5", "0x10", "1_000", "\"\"", "\"a\"",
    "\"\\\"\\\\\\/\\b\\f\\n\\r\\t\"", "\"\\u0041\\u00e9\\u20ac\\ud83d\\ude00\"", "\"\\ud800\"", "\"\\udc80\"",
    "\"\\udcff\\udc80\"", "\"\\ud800\\u0041\"", "\"\\ud800\\ud800\"", "\"\\ude00\\ud83d\"", "\"\\ud83d\\uZZZZ\"",
    "\"\\u12\"", "\"\\u12", "\"\\uGGGG\"", "\"\\x\"", "\"\\", "\"abc", "\"a\tb\"", "\"a\u007fb\"", "[]", "{}", "[ ]",
    "{ }", "[1,2,3]", "[1, 2, 3 ]", "[1,]", "[,1]", "[1 2]", "[", "]", "{", "}", "{\"a\":1}", "{\"a\" : 1 , \"b\":2}",
    "{\"a\":1,}", "{,}", "{\"a\"}", "{\"a\":}", "{a:1}", "{\"a\":1 \"b\":2}", "{\"a\":1,\"a\":2}",
    "{\"b\":1,\"a\":2,\"b\":3}", "{\"\":0}", "[[[[]]]]", "{\"a\":{\"a\":{\"a\":[]}}}", "  1  ", "\t[1]\t", "1 2",
    "[1] x", "\ufeff1", "\ufeff", "", " ", "tru", "fals", "nul", "truex", "true false", "\"é\"", "\"日本語\"",
    "{\"é\":\"日本\",\"a\":[\"\\u00e9\"]}", "[1.25, -3.5e10, 6.02e23, 1e-7, 123456789.123456789]",
    "[9007199254740993, 9007199254740993.0, 0.30000000000000004]", "{\"a\":[1,{\"b\":null}],\"c\":\"d\"}",
    "[\"\\u0000\", \"\\u001f\", \"\\u007f\", \"\\u2028\"]", "[1e1000, -1e1000, 1e-1000]", "[-0, -0.0, 0e0, 0E-0]",
    "[true,false,null,NaN,Infinity,-Infinity]", "{\"a\":NaN}", "[Infinityx]", "[-Infinit]", "[Nan]",
    "\"" + "x" * 2000 + "\"", "[" + ",".join(str(i) for i in range(500)) + "]",
    "{" + ",".join(f"\"k{i}\":{i}" for i in range(300)) + "}",
    "[" * 100 + "]" * 100, "[" * 100000 + "]" * 100000, "{\"a\":" * 50 + "1" + "}" * 50,
    "1" + "0" * 4300, "-" + "1" * 4300, "1" * 30 + ".5",
]
BAD_BYTES = [b"\xff", b"\xc3", b"\xc3\x28", b"\xe2\x82", b"\xed\xa0\x80", b"\xf0\x9f\x98", b"\xc0\xaf", b"\xf5\x80\x80\x80"]


def _value(rng: random.Random, depth: int):
    pick = rng.randrange(10 if depth < 4 else 7)
    if pick == 0:
        return None
    if pick == 1:
        return rng.random() < 0.5
    if pick == 2:
        return rng.choice([0, -1, 7, 2 ** 63 - 1, -2 ** 63, 2 ** 63, 10 ** 20, rng.randrange(-10 ** 6, 10 ** 6)])
    if pick == 3:
        return rng.choice([0.5, -2.25, 1e300, 1e-300, rng.uniform(-1e6, 1e6), 5e-324, float(rng.randrange(1000))])
    if pick in (4, 5, 6):
        alphabet = "ab \"\\/\n\t\x01é€\U0001F600\u2028\x7f"
        return "".join(rng.choice(alphabet) for _ in range(rng.randrange(8)))
    if pick in (7, 8):
        return [_value(rng, depth + 1) for _ in range(rng.randrange(5))]
    return {_value(rng, 9) if False else "".join(rng.choice("abé\"") for _ in range(rng.randrange(3))):
            _value(rng, depth + 1) for _ in range(rng.randrange(5))}


def lines(seed: int = 5, count: int = 600) -> list[bytes]:
    """Every fixed text, then `count` random documents written in random layouts, each followed by a copy broken in
    one place (a byte dropped, doubled, or replaced by a delimiter or a byte that is not UTF-8)."""
    rng = random.Random(seed)
    out = [t.encode("utf-8") for t in FIXED]
    out += [b"\"a" + bad + b"b\"" for bad in BAD_BYTES] + [b"[" + bad + b"]" for bad in BAD_BYTES]
    out += [b"{\"" + bad + b"\":1}" for bad in BAD_BYTES]
    for _ in range(count):
        doc = _value(rng, 0)
        text = json.dumps(doc, ensure_ascii=rng.random() < 0.3, separators=rng.choice([(",", ":"), (", ", ": ")]))
        if rng.random() < 0.2:
            text = text.replace(",", " ,\t").replace(":", "\r:")
        data = text.encode("utf-8")
        out.append(data)
        if data:
            at = rng.randrange(len(data))
            how = rng.randrange(4)
            if how == 0:
                broken = data[:at] + data[at + 1:]
            elif how == 1:
                broken = data[:at] + data[at:at + 1] + data[at:]
            elif how == 2:
                broken = data[:at] + rng.choice([b",", b":", b"]", b"}", b"\"", b"\\"]) + data[at:]
            else:
                broken = data[:at] + rng.choice(BAD_BYTES) + data[at:]
            out.append(broken)
    return [line for line in out if b"\n" not in line and b"\r" not in line[-1:] and not traps(line)]


def traps(line: bytes) -> bool:
    """Whether `refined run` traps on a text: an integer of more digits than int() reads, or text holding a surrogate
    that surrogateescape cannot write (each such text is run alone, since the trap ends the program)."""
    try:
        value = json.loads(line.decode("utf-8", "surrogateescape"))
    except (json.JSONDecodeError, RecursionError):
        return False
    except ValueError:
        return True
    try:
        json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8", "surrogateescape")
    except UnicodeEncodeError:
        return True
    except RecursionError:
        return False
    return False


# texts `refined run` traps on, each run alone: surrogates surrogateescape cannot write (in text and in a key, after
# others it can), and integers of more digits than int() reads
TRAPPING = [b'"\\ud800"', b'["a\\udc80b\\ud800x\\udc80"]', b'{"\\udbff":1}', b'"it\'s \\ud800\\t\\u00e9"',
            b"1" + b"0" * 4300, b"[-" + b"1" * 4301 + b"]"]
