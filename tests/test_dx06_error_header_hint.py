#!/usr/bin/env python3
"""DX-06: operation failure metadata is typed, and control flow stays call-site.

`OP raises ErrorType` is now a real declarative row. The near-miss spellings
(`error`, `raise`, `throws`, `catch`, `mayFail`) still point users at the
executable shape: `CALL catch ...` plus `branch ifError`.
"""
import importlib

import pytest

ss = importlib.import_module("semanticscript")

_HEAD = "MyErr is error\nmain is operation\nmain out Int32\nmain async no\n"
_TAIL = "main let z immutable Int32 0\nmain return z\n"


def test_operation_raises_declared_error_parses():
    prog = ss.parse(_HEAD + "main raises MyErr\n" + _TAIL)
    row = prog.entities["main"].fact("raises")
    assert row is not None
    assert row.payload == ["MyErr"]


@pytest.mark.parametrize("bad_row", [
    "main raises",
    "main raises MissingErr",
])
def test_operation_raises_must_name_declared_error(bad_row):
    with pytest.raises(ss.EavError) as exc:
        ss.parse(_HEAD + bad_row + "\n" + _TAIL)
    assert exc.value.code == "SS2552"


@pytest.mark.parametrize("pred_row", [
    "main error MyErr", "main raise MyErr", "main throws MyErr",
    "main catch e MyErr", "main mayFail MyErr",
])
def test_error_header_near_miss_names_catch(pred_row):
    with pytest.raises(ss.EavError) as exc:
        ss.parse(_HEAD + pred_row + "\n" + _TAIL)
    msg = str(exc.value)
    assert "raises ErrorType" in msg
    assert "catch" in msg and "branch ifError" in msg
    assert "operation-header construct" in msg


def test_non_error_bad_predicate_stays_generic():
    with pytest.raises(ss.EavError) as exc:
        ss.parse("main is operation\nmain out Int32\nmain async no\n"
                 "main bogusPred X\n" + _TAIL)
    msg = str(exc.value)
    assert "not valid for a" in msg
    assert "catch" not in msg
