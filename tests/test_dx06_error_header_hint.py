#!/usr/bin/env python3
"""DX-06: an error-declaration attempt on an operation header names `catch`.

Errors are not part of an operation's signature in SemanticScript — a fallible
call's error is bound with `catch` at the call site and routed with
`branch ifError`. An agent reaching for `main error E` / `raises` / `throws` /
`catch` on the op header used to get a bare "predicate 'X' is not valid for a
operation entity"; the rejection now names the real construct.
"""
import importlib

import pytest

ss = importlib.import_module("semanticscript")

_HEAD = "MyErr is error\nmain is operation\nmain out Int32\nmain async no\n"
_TAIL = "main let z immutable Int32 0\nmain return z\n"


@pytest.mark.parametrize("pred_row", [
    "main error MyErr", "main raises MyErr", "main throws MyErr",
    "main catch e MyErr", "main mayFail MyErr",
])
def test_error_header_predicate_names_catch(pred_row):
    with pytest.raises(ss.EavError) as exc:
        ss.parse(_HEAD + pred_row + "\n" + _TAIL)
    msg = str(exc.value)
    assert "catch" in msg and "branch ifError" in msg
    assert "operation-header construct" in msg


def test_non_error_bad_predicate_stays_generic():
    with pytest.raises(ss.EavError) as exc:
        ss.parse("main is operation\nmain out Int32\nmain async no\n"
                 "main bogusPred X\n" + _TAIL)
    msg = str(exc.value)
    assert "not valid for a" in msg
    assert "catch" not in msg
