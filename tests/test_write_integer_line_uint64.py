#!/usr/bin/env python3
"""R-269: console.writeIntegerLine prints a UInt64 with the high bit set unsigned.

The value was widened (zero-extended for unsigned narrows) but always printed
with the signed `%lld`, so a full-width UInt64 > 2^63-1 came out negative. The
lowering now selects `%llu` for an unsigned operand; signed values still use
`%lld`.
"""
import importlib

ss = importlib.import_module("semanticscript")

_HEAD = (
    "P is project\nP module m\nP target console\nP entry main\n"
    'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
    "ExitCode is alias\nExitCode for Int32\n"
    "main is operation\nmain out ExitCode\nmain async no\n"
    'main purpose "p"\nmain invariant "i"\n'
)


def _run(value_type, literal):
    src = _HEAD + (
        f"main let v immutable {value_type} {literal}\n"
        "main let okc immutable ExitCode 0\nmain do p\nmain return okc\n"
        f"p is call\np in main\np invokes console.writeIntegerLine\np arg value {value_type} v\n"
    )
    out, err, code = ss._record_run_full(src)
    assert code == 0, err
    return out.strip()


def test_uint64_high_bit_prints_unsigned():
    assert _run("UInt64", "18446744073709551615") == "18446744073709551615"


def test_uint64_above_signed_max_prints_unsigned():
    assert _run("UInt64", "9223372036854775808") == "9223372036854775808"


def test_signed_int64_negative_still_correct():
    assert _run("Int64", "-42") == "-42"
