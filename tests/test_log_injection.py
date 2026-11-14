#!/usr/bin/env python3
"""R-268: ss_log_write_line neutralizes embedded record separators (log injection).

ss_log_write_line is a first-class public log API that wrote its argument verbatim
+ '\\n', so a caller passing a raw '\\n'/'\\r' could split one call into multiple
log records (forged entries). The ss_log_event/access wrappers pre-escape control
chars, but a direct caller did not. The write path now replaces '\\n'/'\\r' with a
space so one call is always exactly one record.

Asserted at the source level (matching the other sem_log_runtime.c tests); the fix
is also behaviorally verified out-of-band (a C harness that injects a newline
produces two records, not three, with the separator sanitized to a space).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SRC = (ROOT / "semanticscript" / "runtime" / "native_log" / "sem_log_runtime.c").read_text(
    encoding="utf-8")


def _ss_log_write_line_body():
    m = re.search(r"int ss_log_write_line\(const char \*line\)\s*\{.*?\n\}", _SRC, re.S)
    assert m, "ss_log_write_line not found"
    return m.group(0)


def test_write_line_neutralizes_newlines():
    body = _ss_log_write_line_body()
    # the record separators are replaced as the line is written
    assert "'\\n'" in body and "'\\r'" in body
    assert "? ' ' :" in body, "expected newline/CR -> space neutralization"
    # R-150 error reporting is preserved (a write failure is still surfaced)
    assert "SS_LOG_ERR_ENGINE" in body


def test_write_line_no_longer_blind_fwrite():
    # the verbatim fwrite(line, ...) path is gone (it could not sanitize)
    body = _ss_log_write_line_body()
    assert "fwrite(line" not in body
