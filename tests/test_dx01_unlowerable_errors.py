#!/usr/bin/env python3
"""DX-01: error constructs are either lint-blocked or proven lowerable.

The original DX-01 false-green was a source shape that passed `check` but failed
only at backend lowering. Data-carrying error-case construction and `ifVariant`
over error cases are now supported by codegen, so the trust regression is that
they stay lint-clean *and* lower successfully.
"""
import importlib

semanticscript = importlib.import_module("semanticscript")


def _codes(src):
    return {d.code for d in semanticscript.lint(semanticscript.parse(src))
            if d.severity == "error"}


def _assert_check_clean_lowers(src):
    program = semanticscript.parse(src)
    errors = [d for d in semanticscript.lint(program) if d.severity == "error"]
    assert errors == []
    semanticscript.lower_to_llvm(program)


_HEAD = (
    "P is project\nP module m\nP target console\nP entry op\nm is module\nm path a.b\n"
    'm purpose "p"\nm invariant "i"\nm exports op\n'
    "ExitCode is alias\nExitCode for Int32\n"
)


def _ctor_program(extra_case_rows, ctor_arg_rows):
    return _HEAD + (
        "MyErr is error\nBadThing is errorCase\nBadThing of MyErr\n" + extra_case_rows +
        "op is operation\nop out ExitCode\nop async no\nop purpose \"p\"\nop invariant \"i\"\n"
        "op let n immutable Int64 42\nop let okc immutable ExitCode 0\n"
        "op do mk\nop return okc\n"
        "mk is call\nmk in op\nmk invokes MyErr.BadThing\n" + ctor_arg_rows + "mk out e MyErr\n")


def test_data_carrying_error_construction_check_clean_and_lowers():
    _assert_check_clean_lowers(
        _ctor_program("BadThing payload Int64\n", "mk arg detail Int64 n\n"))


def test_payloadless_error_construction_clean():
    # no payload row, no arg -> legal, must not be flagged
    assert "SS3047" not in _codes(_ctor_program("", ""))


def test_ifvariant_on_error_case_check_clean_and_lowers():
    src = _HEAD + (
        "MyErr is error\nCaseA is errorCase\nCaseA of MyErr\n"
        "op is operation\nop out ExitCode\nop async no\nop purpose \"p\"\nop invariant \"i\"\n"
        "op let okc immutable ExitCode 0\n"
        "op do mk\nop branch ifVariant e CaseA goto isA\nop return okc\nop at isA return okc\n"
        "mk is call\nmk in op\nmk invokes MyErr.CaseA\nmk out e MyErr\n")
    _assert_check_clean_lowers(src)


def test_ifvariant_on_enum_clean():
    src = _HEAD + (
        "Status is enum\nStatus variant open\nStatus variant done\n"
        "op is operation\nop out ExitCode\nop async no\nop purpose \"p\"\nop invariant \"i\"\n"
        "op let s immutable Status open\nop let okc immutable ExitCode 0\n"
        "op branch ifVariant s done goto isDone\nop return okc\nop at isDone return okc\n")
    assert "SS1355" not in _codes(src)
