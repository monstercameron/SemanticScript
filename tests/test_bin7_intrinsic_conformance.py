#!/usr/bin/env python3
"""BIN-7: intrinsic output-correctness conformance.

It is not enough that a builtin LOWERS — it must produce the spec'd VALUE. Each
intrinsic-family example is self-checking (`PASS ... (expected X, actual X)`), so
this gate runs every one through the real JIT and asserts it computes the right
result. Families covered (by filename prefix): integer + float math, bit ops
(and/or/shift/popcount/clz/ctz), numeric conversions (widen/narrow/int<->float),
comparisons, exact decimal/money, and checked arithmetic.

An intrinsic that silently computes the wrong value (a codegen/runtime defect that
`check` cannot see) turns the gate red.
"""
import glob
import importlib
import os
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SC = os.path.join(ROOT, "semanticscript", "compiler", "semanticscript.py")

_PREFIXES = ("bit_", "int_", "float_", "convert_", "compare_",
             "decimal_", "checked_", "math_", "count_", "string_")


def _intrinsic_examples():
    out = []
    for path in sorted(glob.glob(os.path.join(ROOT, "examples", "*.sem"))):
        base = os.path.basename(path)
        if base.startswith(_PREFIXES):
            out.append(base[:-4])  # strip .sem
    return out


INTRINSIC_EXAMPLES = _intrinsic_examples()


def test_bin7_corpus_has_broad_intrinsic_coverage():
    # Guard the gate itself isn't silently emptied.
    assert len(INTRINSIC_EXAMPLES) >= 30, (
        f"expected a broad intrinsic corpus, found {len(INTRINSIC_EXAMPLES)}")


@pytest.mark.parametrize("name", INTRINSIC_EXAMPLES)
def test_bin7_intrinsic_produces_expected_value(name):
    proc = subprocess.run([sys.executable, SC, "run",
                           os.path.join(ROOT, "examples", name + ".sem")],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60)
    assert proc.returncode == 0, f"{name}: exit {proc.returncode}\n{proc.stderr}"
    assert "PASS" in proc.stdout, f"{name}: no PASS line\n{proc.stdout}"
    assert "FAIL" not in proc.stdout, (
        f"{name}: an intrinsic computed the WRONG value\n{proc.stdout}")
