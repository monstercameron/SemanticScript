#!/usr/bin/env python3
"""R-233: run-probe helpers survive a program that emits non-UTF-8 bytes.

The JIT'd child writes to fd 1/2 from the C runtime, so a program can emit a
lone non-UTF-8 byte (trivial on Windows). The isolated-child probes shared by
eval / run --json / test / bench decode that output with encoding="utf-8"; with
no errors= they raised UnicodeDecodeError inside subprocess.run, crashing the
toolchain command (and any in-process MCP call) instead of returning a result.
The probes now decode with errors="replace", so a bad byte becomes U+FFFD and
the run is still classified normally.
"""
import importlib

ss = importlib.import_module("semanticscript")

# c.putchar(128) writes a lone 0x80 to stdout — not valid UTF-8.
_EMIT_BAD_BYTE = (
    "P is project\nP module m\nP target console\nP entry main\n"
    'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
    "ExitCode is alias\nExitCode for Int32\n"
    "ffiCap is capability\nffiCap grants ffi libc\nffiCap purpose \"raw byte\"\n"
    "main is operation\nmain out ExitCode\nmain async no\n"
    "main uses ffiCap\nmain effect ffi libc\n"
    'main purpose "emit a lone 0x80"\nmain invariant "i"\n'
    "main let b immutable Int32 128\nmain let okCode immutable ExitCode 0\n"
    "main do putCall\nmain return okCode\n"
    "putCall is call\nputCall in main\nputCall invokes c.putchar\n"
    "putCall arg ch Int32 b\nputCall out wrote Int32\n"
)


def test_record_run_full_survives_non_utf8_stdout():
    out, err, code = ss._record_run_full(_EMIT_BAD_BYTE)   # must not raise
    assert code == 0
    assert "�" in out                                  # 0x80 -> replacement
    assert ss._classify_run(out, err, code)[0] == "ok"


def test_record_run_entry_survives_non_utf8_stdout():
    # the test runner's per-op probe shares the same decode path
    out, err, code = ss._record_run_entry(_EMIT_BAD_BYTE, "main")  # must not raise
    assert code == 0
    assert "�" in out
