"""Lexer for the refined syntax (LR-11, LR-21, LR-42 A23).

Rules:
- Source is UTF-8. CRLF and CR are normalized to LF.
- Only space and tab separate tokens. Any other whitespace or control
  character outside a string is an error.
- A string starts with `"` at the start of a token and ends with `"`, and must
  be followed by whitespace or the end of the line. Escapes: \\" \\\\ \\n \\t
  \\xNN. A raw control character inside a string is an error.
- A quote anywhere else in a token is an error.
- `#` at the start of a token begins a comment that runs to the end of the
  line. Comments are kept (attached to rows) but never checked.
"""
from __future__ import annotations

from .diagnostics import Sink
from .model import Line, Token

_ESCAPES = {'"': '"', "\\": "\\", "n": "\n", "t": "\t"}
_HEX = set("0123456789abcdefABCDEF")


def lex(text: str, sink: Sink) -> list[Line]:
    if text.startswith("﻿"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return [_lex_line(raw, n, sink) for n, raw in enumerate(text.split("\n"), 1)]


def _bad_char(c: str) -> str | None:
    o = ord(c)
    if c in " \t":
        return None
    if c.isspace():
        return "R101"
    if o < 32 or o == 127 or 0x80 <= o < 0xA0:
        return "R102"
    return None


def _lex_line(raw: str, lineno: int, sink: Sink) -> Line:
    tokens: list[Token] = []
    comment = None
    i, n = 0, len(raw)
    while i < n:
        c = raw[i]
        if c in " \t":
            i += 1
            continue
        if c == "#":
            comment = raw[i + 1:].strip()
            break
        if c == '"':
            start = i
            i += 1
            buf: list[str] = []
            closed = False
            while i < n:
                ch = raw[i]
                if ch == "\\":
                    nxt = raw[i + 1] if i + 1 < n else ""
                    if nxt in _ESCAPES:
                        buf.append(_ESCAPES[nxt])
                        i += 2
                        continue
                    hex_digits = raw[i + 2:i + 4]
                    if nxt == "x" and len(hex_digits) == 2 and all(h in _HEX for h in hex_digits):
                        byte = int(hex_digits, 16)
                        # bytes above 0x7F are raw bytes, kept as surrogate escapes so the
                        # backend encodes them exactly (str.encode("utf-8", "surrogateescape"))
                        buf.append(chr(byte) if byte < 0x80 else chr(0xDC00 + byte))
                        i += 4
                        continue
                    sink.error("R105", lineno, f"unsupported escape `\\{nxt}` in a string; "
                               "use \\\" \\\\ \\n \\t or \\xNN")
                    i += 2
                    continue
                if ch == '"':
                    closed = True
                    i += 1
                    break
                code = _bad_char(ch)
                if code == "R102":
                    sink.error("R102", lineno, f"raw control character U+{ord(ch):04X} inside a string; "
                               "write it as \\xNN")
                buf.append(ch)
                i += 1
            if not closed:
                sink.error("R106", lineno, "string is not closed before the end of the line")
            tokens.append(Token("string", raw[start:i], "".join(buf), start + 1))
            if i < n and raw[i] not in " \t":
                sink.error("R104", lineno, "a string must be followed by a space, a tab, or the end of the line")
            continue
        start = i
        while i < n and raw[i] not in " \t":
            ch = raw[i]
            if ch == '"':
                sink.error("R104", lineno, "a quote may only begin a string token")
            elif ch == "#":
                sink.error("R104", lineno, "`#` begins a comment only at the start of a token")
            else:
                code = _bad_char(ch)
                if code == "R101":
                    sink.error("R101", lineno, f"only space and tab separate tokens; found U+{ord(ch):04X}")
                elif code == "R102":
                    sink.error("R102", lineno, f"control character U+{ord(ch):04X} outside a string")
            i += 1
        tokens.append(Token("word", raw[start:i], raw[start:i], start + 1))
    return Line(lineno, tokens, comment)
