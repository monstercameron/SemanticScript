#!/usr/bin/env python3
"""R-258: `return nil <err>` on a non-pointer Result OK type is rejected.

`_emit_return` lowered `return nil` to the OK type's null/zero. For a POINTER OK
type the caller null-checks the handle, so null signals the error. For a
NON-pointer OK type (Int64/Bool/…), the OK-typed 0 is a valid OK value
indistinguishable from the error sentinel — the error was silently lost. Now
rejected: at check (SS3049, _lint_result_nil_error_loss) and as a lowering guard.
"""
import importlib

import pytest

ss = importlib.import_module("semanticscript")

_HEAD = (
    "P is project\nP module m\nP target console\nP entry main\n"
    'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
    "ExitCode is alias\nExitCode for Int32\nSomeError is error\n"
    "main is operation\nmain out ExitCode\nmain async no\n"
    'main purpose "p"\nmain invariant "i"\nmain let okc immutable ExitCode 0\nmain return okc\n'
)


def _codes(src):
    return {d.code for d in ss.lint(ss.parse(src)) if d.severity == "error"}


def _op(ok_type):
    return _HEAD + (
        f"f is operation\nf out Result {ok_type} SomeError\nf async no\n"
        'f purpose "p"\nf invariant "i"\nf let e immutable SomeError 0\nf return nil e\n'
    )


def test_return_nil_error_on_result_with_int_ok_type():
    assert "SS3049" in _codes(_op("Int64"))


def test_return_nil_error_on_result_with_pointer_ok_type_ok():
    # a String (pointer) OK type can carry the error as a null sentinel
    assert "SS3049" not in _codes(_op("String"))


def test_lowering_guard_rejects_int_ok_nil_error():
    # the lowering backstop raises too (not just the lint)
    with pytest.raises(ss.EavError) as exc:
        ss.lower_to_llvm(ss.parse(_op("Int64")))
    assert getattr(exc.value, "code", None) == "SS3049"
