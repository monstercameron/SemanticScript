#!/usr/bin/env python3
"""R-214..R-217: codegen must respect unsigned integer types.

Previously every integer compare used a signed predicate (R-214), int widening
sign-extended (R-215), the narrowing round-trip check sign-extended — falsely
trapping valid unsigned values (R-216), and int<->float used sitofp/fptosi with
signed bounds (R-217). Each is now keyed on the operand's signedness. These run
real programs (or check the lowered IR) where a signed misread produces a
different, observably-wrong answer.
"""
import importlib
import os
import subprocess
import sys

semanticscript = importlib.import_module("semanticscript")
SEMANTICSCRIPT = semanticscript.__file__

_HEAD = (
    "P is project\nP module m\nP target console\nP entry main\n"
    'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
    "ExitCode is alias\nExitCode for Int32\n"
)


def _run(src):
    proc = subprocess.run(
        [sys.executable, SEMANTICSCRIPT, "run", "-"],
        input=src, capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, proc.stdout.strip(), proc.stderr


def _ir(src):
    return str(semanticscript.lower_to_llvm(semanticscript.parse(src)))


def test_r214_unsigned_ordering_uses_unsigned_predicate():
    # 3_000_000_000 > 1 is true for UInt32; a signed compare reads the left
    # operand (high bit set) as negative and returns false.
    src = _HEAD + (
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let big immutable UInt32 3000000000\n"
        "main let one immutable UInt32 1\n"
        "main let okCode immutable ExitCode 0\nmain let failCode immutable ExitCode 7\n"
        "main do cmp\nmain branch if isGt goto bigger\nmain return failCode\n"
        "main at bigger return okCode\n"
        "cmp is call\ncmp in main\ncmp invokes compare.greaterThanUInt32\n"
        "cmp arg left UInt32 big\ncmp arg right UInt32 one\ncmp out isGt Bool\n")
    rc, out, err = _run(src)
    assert rc == 0, "unsigned 3e9 > 1 must be true (rc=%s, %s)" % (rc, err)
    assert "icmp ugt" in _ir(src)


def test_r215_unsigned_widening_zero_extends():
    # UInt8 200 widened to Int64 is 200; sign-extension would give -56.
    src = _HEAD + (
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let small immutable UInt8 200\nmain let okCode immutable ExitCode 0\n"
        "main do widen\nmain do show\nmain return okCode\n"
        "widen is call\nwiden in main\nwiden invokes convert.toInt64\n"
        "widen arg value UInt8 small\nwiden out big Int64\n"
        "show is call\nshow in main\nshow invokes console.writeIntegerLine\n"
        "show arg value Int64 big\n")
    rc, out, err = _run(src)
    assert rc == 0, err
    assert out == "200", "UInt8 200 -> Int64 must be 200, got %r" % out


def test_r216_in_range_unsigned_narrowing_does_not_trap():
    # UInt16 200 fits UInt8; the round-trip check must zero-extend, else sext of
    # trunc(200) == -56 falsely trips the narrowing-overflow trap (SSR0012).
    src = _HEAD + (
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let mid immutable UInt16 200\nmain let okCode immutable ExitCode 0\n"
        "main do narrow\nmain do widen\nmain do show\nmain return okCode\n"
        "narrow is call\nnarrow in main\nnarrow invokes convert.toUInt8\n"
        "narrow arg value UInt16 mid\nnarrow out small UInt8\n"
        "widen is call\nwiden in main\nwiden invokes convert.toInt64\n"
        "widen arg value UInt8 small\nwiden out big Int64\n"
        "show is call\nshow in main\nshow invokes console.writeIntegerLine\n"
        "show arg value Int64 big\n")
    rc, out, err = _run(src)
    assert rc == 0, "valid in-range unsigned narrow must not trap (%s)" % err
    assert out == "200", out


def test_r217_int_to_float_uses_uitofp_for_unsigned():
    src = _HEAD + (
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let big immutable UInt32 3000000000\nmain let okCode immutable ExitCode 0\n"
        "main do conv\nmain return okCode\n"
        "conv is call\nconv in main\nconv invokes convert.toFloat64\n"
        "conv arg value UInt32 big\nconv out f Float64\n")
    assert "uitofp" in _ir(src)


def test_r218_negative_int32_prints_with_sign():
    # console.writeIntegerLine of Int32 -1 must print -1; the old zext-of-narrow
    # printed 4294967295.
    src = _HEAD + (
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let n immutable Int32 -1\nmain let okCode immutable ExitCode 0\n"
        "main do show\nmain return okCode\n"
        "show is call\nshow in main\nshow invokes console.writeIntegerLine\n"
        "show arg value Int32 n\n")
    rc, out, err = _run(src)
    assert rc == 0, err
    assert out == "-1", "Int32 -1 must print as -1, got %r" % out


def test_r218_mixed_width_negative_equality_holds():
    # assertEqualInt64(expected Int64 -1, actual Int32 -1) must be equal: the
    # narrow actual sign-extends to -1, not zero-extends to 4294967295.
    src = _HEAD + (
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let wide immutable Int64 -1\nmain let narrow immutable Int32 -1\n"
        'main let caseName immutable String "neg"\nmain let okCode immutable ExitCode 0\n'
        "main do check\nmain do report\nmain return code\n"
        "check is call\ncheck in main\ncheck invokes test.assertEqualInt64\n"
        "check arg name String caseName\ncheck arg expected Int64 wide\n"
        "check arg actual Int32 narrow\n"
        "report is call\nreport in main\nreport invokes test.summary\n"
        "report out code ExitCode\n")
    rc, out, err = _run(src)
    assert rc == 0, "mixed-width -1 == -1 must pass (rc=%s, out=%r, %s)" % (rc, out, err)
    assert "1 passed, 0 failed" in out or "actual -1" in out, out


def test_r217_float_to_unsigned_int_uses_fptoui():
    src = _HEAD + (
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let f immutable Float64 3000000000.0\nmain let okCode immutable ExitCode 0\n"
        "main do conv\nmain return okCode\n"
        "conv is call\nconv in main\nconv invokes convert.toUInt32\n"
        "conv arg value Float64 f\nconv out n UInt32\n")
    assert "fptoui" in _ir(src)
