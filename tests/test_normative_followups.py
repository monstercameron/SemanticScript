#!/usr/bin/env python3
"""Normative compiler/language-standard requirements (BIN-* / AQ-*).

The organizing contract is check ⊇ codegen: anything that passes `check` must
lower and run. Each test pins one normative requirement from the trial reframing.
"""
import importlib

import pytest

semanticscript = importlib.import_module("semanticscript")


# --- AQ-1: camelCase-canonical names; SS0002 names the conforming spelling ---

def test_aq1_camel_case_suggestion():
    f = semanticscript._camel_case_suggestion
    assert f("helper_op") == "helperOp"
    assert f("user_id") == "userId"
    assert f("my-value") == "myValue"
    assert f("already_camelCase") == "alreadyCamelCase"
    assert f("alreadyFine") is None          # valid -> no suggestion
    assert f("__") is None                    # nothing usable


def test_aq1_ss0002_names_the_camel_form():
    src = ("P is project\nP module m\nP target console\nP entry main\n"
           "m is module\nm path x\nm exports main\n"
           "bad_name is operation\nbad_name out Int32\nbad_name async no\n"
           "bad_name return zeroLit\n"
           "zeroLit is storage\nzeroLit scope module\nzeroLit type Int32\n"
           "zeroLit value 0\n")
    with pytest.raises(semanticscript.EavError) as exc:
        semanticscript.parse(src)
    assert exc.value.code == "SS0002"
    assert "bad_name" in str(exc.value) and "badName" in str(exc.value)


# --- AQ-2: effect coverage counts a module-qualified (imported) capability ---

_AQ2 = (
    "P is project\nP module m\nP target console\nP entry main\n"
    "m is module\nm path x\nm exports main\nm purpose \"p\"\nm invariant \"i\"\n"
    "ExitCode is alias\nExitCode for Int32\nConsoleWriteError is error\n"
    "writeCap is capability\nwriteCap grants write console.stdout\n"
    "main is operation\nmain out ExitCode\nmain effect write console.stdout\n"
    "main uses {USES}\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
    "main let h immutable String \"hi\"\nmain let z immutable ExitCode 0\n"
    "main do w\nmain return z\n"
    "w is call\nw in main\nw invokes console.writeLine\nw arg text String h\n"
    "w catch e ConsoleWriteError\n"
)


def _codes(src):
    return {d.code for d in semanticscript.lint(semanticscript.parse(src))}


def test_aq2_qualified_imported_capability_covers_effect():
    # `uses authMod.writeCap` (imported) resolves to the bare capability.
    assert "SS1708" not in _codes(_AQ2.replace("{USES}", "authMod.writeCap"))
    # bare reference still works.
    assert "SS1708" not in _codes(_AQ2.replace("{USES}", "writeCap"))


def test_aq2_genuinely_missing_capability_still_uncovered():
    # a qualified name whose tail names no capability stays uncovered (sound).
    # SS1708 is a deny-tier hard error, raised (not returned) by lint.
    with pytest.raises(semanticscript.EavError) as exc:
        semanticscript.lint(semanticscript.parse(
            _AQ2.replace("{USES}", "authMod.noSuchCap")))
    assert exc.value.code == "SS1708"
