#!/usr/bin/env python3
"""R-250: `branch ifValue`/`ifOut` use an unsigned predicate for unsigned operands.

R-214 fixed unsigned comparisons in `_emit_compare` but `_emit_branch`'s
ifValue/ifOut path still resolved the operand with a hardcoded "Int64" hint and
emitted `icmp_signed` unconditionally — so `branch ifValue x greaterThan y` on a
UInt32/UInt64 with the high bit set branched backwards. The branch now resolves
the operand with its declared type and selects icmp_unsigned/icmp_signed from it.
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
_TAIL = (
    "main let okc immutable ExitCode 0\n"
    'main let wrong immutable String "WRONG"\nmain let right immutable String "RIGHT"\n'
    "main branch ifValue a {cmp} b goto hit\n"
    "main do pWrong\nmain return okc\nmain at hit do pRight\nmain return okc\n"
    "pWrong is call\npWrong in main\npWrong invokes console.writeLine\npWrong arg text String wrong\n"
    "pRight is call\npRight in main\npRight invokes console.writeLine\npRight arg text String right\n"
)


def _run(ty, a, b, cmp):
    src = _HEAD + (f"main let a immutable {ty} {a}\nmain let b immutable {ty} {b}\n"
                   + _TAIL.format(cmp=cmp))
    out, err, code = ss._record_run_full(src)
    assert code == 0, err
    return out.strip()


def test_branch_ifvalue_unsigned_greater_than():
    # 2^63 > 1 unsigned; a signed compare would see 2^63 as negative -> WRONG
    assert _run("UInt64", "9223372036854775808", "1", "greaterThan") == "RIGHT"


def test_branch_ifvalue_signed_less_than_still_correct():
    # -5 < 1 signed -> branch taken (no regression for signed operands)
    assert _run("Int64", "-5", "1", "lessThan") == "RIGHT"
