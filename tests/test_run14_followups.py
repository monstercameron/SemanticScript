#!/usr/bin/env python3
"""SSDX run-14 follow-ups: fixes for the run-14 rough-spot ledger.

Each test pins one R-## finding closed. Scoped to areas not under concurrent edit
by the parallel webServer/http-runtime/string-stdlib effort.
"""
import importlib
import json
import os
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SC = os.path.join(ROOT, "semanticscript", "compiler", "semanticscript.py")

SCAFFOLDS = list(getattr(semanticscript, "SCAFFOLD_PATTERNS", ()))


# --- R-17: `scaffold` output is canonical (passes `fmt --check`) ---

_ENUM_PROG = (
    "P is project\nP module m\nP target console\nP entry main\n"
    "m is module\nm path m\nm exports main\nm purpose \"p\"\nm invariant \"i\"\n"
    "ExitCode is alias\nExitCode for Int32\n"
    "Color is enum\nColor variant red\nColor variant green\n"
    "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\n"
    "main invariant \"i\"\n{LET}\nmain let z immutable ExitCode 0\nmain return z\n")


def _lint_codes(src):
    prog = semanticscript.parse(src)
    return [(d.code, d.message) for d in semanticscript.lint(prog) if d.severity == "error"]


# --- R-08 / R-10 / Root-A: an invalid enum variant is a check error (not a false green) ---

def test_r08_invalid_enum_variant_in_let_is_check_error_listing_legal_values():
    """R-08/R-10 (Root A): `let x Color purple` where `purple` isn't a Color variant
    passed `check` then crashed codegen ("not in scope"). It must be a check-time
    error that NAMES the legal variants (R-08)."""
    codes = _lint_codes(_ENUM_PROG.format(LET="main let hue immutable Color purple"))
    bad = [m for c, m in codes if c == "SS1033" and "not a variant of enum 'Color'" in m]
    assert bad, f"invalid enum variant not rejected: {codes}"
    assert "green, red" in bad[0], "diagnostic must list the legal variants (R-08)"


def test_r08_invalid_enum_variant_in_call_arg_is_check_error():
    src = (_ENUM_PROG.format(LET="main let hue immutable Color red\nmain do useColor")
           + "useColor is call\nuseColor in main\nuseColor invokes console.writeLine\n"
             "useColor arg text Color purple\n")
    codes = _lint_codes(src)
    assert any(c == "SS1033" and "value 'purple'" in m for c, m in codes), codes


def test_r08_valid_variant_and_binding_ref_are_accepted():
    """A declared variant and a genuine binding reference must NOT be flagged."""
    assert not [c for c, _ in _lint_codes(
        _ENUM_PROG.format(LET="main let hue immutable Color green")) if c == "SS1033"]
    # a binding that holds a Color, referenced by another let, is not a variant typo.
    src = _ENUM_PROG.format(
        LET="main let baseHue immutable Color red\nmain let hue immutable Color baseHue")
    assert not [c for c, _ in _lint_codes(src) if c == "SS1033"]


@pytest.mark.parametrize("pattern", SCAFFOLDS)
def test_r17_scaffold_output_is_fmt_canonical(pattern):
    """R-17: `cmd_scaffold` advertises "canonical" output, but emitted templates in
    authoring order — so a freshly-scaffolded, check-GREEN program failed
    `fmt --check`, breaking the scaffold->check->fmt loop an agent runs every time.
    The CLI now emits the canonical form: check-clean AND fmt-clean."""
    src = subprocess.run([sys.executable, SC, "scaffold", pattern],
                         capture_output=True, text=True, encoding="utf-8").stdout
    assert src.strip(), f"scaffold {pattern!r} produced no output"
    # check-green
    chk = subprocess.run([sys.executable, SC, "check", "-", "--json"],
                         input=src, capture_output=True, text=True, encoding="utf-8")
    assert json.loads(chk.stdout).get("errorCount") == 0, f"{pattern} not check-green"
    # and fmt-canonical: a second fmt pass is a no-op (idempotent canonical form).
    prog = semanticscript.parse(src)
    assert semanticscript.format_program(prog).strip() == src.strip(), (
        f"scaffold {pattern!r} output is not fmt-canonical (would drift on fmt --check)")
