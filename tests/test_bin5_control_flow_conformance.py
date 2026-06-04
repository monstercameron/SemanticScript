#!/usr/bin/env python3
"""BIN-5: control-flow lowering completeness.

Every control-flow construct must lower AND run correctly — not just parse/check.
This drives a curated corpus that spans the construct families through the real
JIT, asserting each self-checking example runs to its expected result:

  loops        : while_loop, nested_loops, retry_loop_bounded, countdown
  recursion    : factorial, fib_iterative, mutual_recursion (+ the deep-recursion
                 trap, proving the depth guard lowers)
  branch/goto  : branch_else_goto
  compound     : compound_and_or, compound_or  (AND/OR guard short-circuit)
  variant/error: variant_match (ifVariant), error_case_return (ifError)
  result arity : result_arity_ok_err

A lowering regression in any control construct turns this red.
"""
import importlib
import os
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SC = os.path.join(ROOT, "semanticscript", "compiler", "semanticscript.py")

# self-checking examples: exit 0, stdout contains PASS, never FAIL.
PASS_EXAMPLES = [
    "while_loop", "nested_loops", "retry_loop_bounded", "countdown",
    "factorial", "fib_iterative", "mutual_recursion",
    "branch_else_goto", "compound_and_or", "compound_or",
    "variant_match", "error_case_return", "result_arity_ok_err",
]


def _run(name):
    path = os.path.join(ROOT, "examples", name + ".sem")
    proc = subprocess.run([sys.executable, SC, "run", path],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=60)
    return proc.stdout, proc.stderr, proc.returncode


@pytest.mark.parametrize("name", PASS_EXAMPLES)
def test_bin5_control_flow_example_lowers_and_runs(name):
    if not os.path.exists(os.path.join(ROOT, "examples", name + ".sem")):
        pytest.skip(f"{name} not present")
    out, err, code = _run(name)
    assert code == 0, f"{name}: exit {code}\n{err}"
    assert "PASS" in out, f"{name}: no PASS line\n{out}"
    assert "FAIL" not in out, f"{name}: a FAIL line is present\n{out}"


def test_bin5_deep_recursion_trap_lowers_to_a_guarded_panic():
    # The unbounded-recursion guard is a control-flow lowering too: it must lower
    # to a structured panic (SSR0013) + the documented abort code, never silent UB.
    name = "deep_recursion_trap"
    if not os.path.exists(os.path.join(ROOT, "examples", name + ".sem")):
        pytest.skip(f"{name} not present")
    out, err, code = _run(name)
    assert code == 134, f"expected the panic abort code 134, got {code}"
    assert "SSR0013" in (out + err), "expected the recursion-depth panic SSR0013"
