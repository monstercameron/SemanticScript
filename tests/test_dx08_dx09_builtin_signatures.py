#!/usr/bin/env python3
"""DX-08/DX-09: expose built-in target signatures, and validate call args at check.

DX-08 — an agent could not look up a built-in intrinsic's arg slots (it guessed
`lhs`/`rhs` for math.divideInt64's `left`/`right`). `targets --signature <target>`
and `describe <target>` now return the declared signature (slot names + types +
out) from the target's standard.<module>.semsig.

DX-09 — `check` now validates a math.* call's arg slots/types against that
signature (SS1201, the arg-slot sibling of SS1198/SS1199): an unknown slot, a
missing required slot, or a wrong type was a false green caught only at run.
math.* is the scope because its code generator reads operands BY slot name;
positional families (convert.*/buffer.*) accept any name and are not flagged.
"""
import importlib
import json

import pytest

ss = importlib.import_module("semanticscript")

_HEAD = (
    "P is project\nP module m\nP target console\nP entry main\n"
    'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
    "ExitCode is alias\nExitCode for Int32\n"
    "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
    "main let a immutable Int64 10\nmain let b immutable Int64 2\nmain let okc immutable ExitCode 0\n"
    "main do divCall\nmain return okc\n"
    "divCall is call\ndivCall in main\ndivCall invokes math.divideInt64\n"
)


def _codes(arg_rows):
    src = _HEAD + arg_rows + "divCall out q Int64\n"
    return {d.code for d in ss.lint(ss.parse(src)) if d.severity == "error"}


# --- DX-08 ---

def test_signature_lookup_returns_slots_and_out():
    sig = ss._builtin_target_signature("math.divideInt64")
    assert [(a["slot"], a["type"]) for a in sig["args"]] == [("left", "Int64"), ("right", "Int64")]
    assert sig["out"] == "Int64"


def test_unknown_target_has_no_signature():
    assert ss._builtin_target_signature("math.nope") is None
    assert ss._builtin_target_signature("notamodule.x") is None


def test_targets_signature_command(capsys):
    rc = ss.main(["targets", "--signature", "math.divideInt64", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert rc == 0 and data["surface"] == "sem.targetSignature.v1"
    assert {a["slot"] for a in data["args"]} == {"left", "right"}


# --- DX-09 ---

def test_wrong_slot_names_rejected_at_check():
    assert "SS1201" in _codes("divCall arg lhs Int64 a\ndivCall arg rhs Int64 b\n")


def test_correct_slot_names_accepted():
    assert "SS1201" not in _codes("divCall arg left Int64 a\ndivCall arg right Int64 b\n")


def test_missing_required_slot_rejected():
    assert "SS1201" in _codes("divCall arg left Int64 a\n")


def test_positional_family_not_flagged():
    # convert.toFloat64's semsig slot is `value`, but the family lowers positionally
    # so a different slot name (`inputValue`) must NOT be flagged.
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
        "main let n immutable Int64 3\nmain let okc immutable ExitCode 0\n"
        "main do cv\nmain return okc\n"
        "cv is call\ncv in main\ncv invokes convert.toFloat64\n"
        "cv arg inputValue Int64 n\ncv out f Float64\n"
    )
    assert "SS1201" not in {d.code for d in ss.lint(ss.parse(src))}
