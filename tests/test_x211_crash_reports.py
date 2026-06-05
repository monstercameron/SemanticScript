#!/usr/bin/env python3
"""X-211: end-to-end coverage for the crash-reporting corpus (§1K).

A runtime trap lowers to a structured `ss_panic` that prints
`EAV PANIC <CODE> <kind>` + op/line/operands to stderr and exits 134. This runs
each shipped panic example through the real `run` lane and asserts the exact
panic code, the trapping op, and the stable 134 exit — the §X1c e2e contract for
the crash-reporting area.
"""
import importlib
import os
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")
SEMANTICSCRIPT = semanticscript.__file__
EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")

# example -> (expected panic code, trapping op)
_PANICS = {
    "panic_div0_report": ("SSR0010", "main"),         # divide-by-zero
    "panic_narrowing_report": ("SSR0012", "main"),     # narrowing-overflow
    "panic_recursion_report": ("SSR0013", "loopRec"),  # recursion-depth-exceeded
}


@pytest.mark.parametrize("name,code_op", sorted(_PANICS.items()))
def test_panic_example_reports_structured_trap(name, code_op):
    code, op = code_op
    path = os.path.join(EXAMPLES, name + ".sem")
    assert os.path.isfile(path), path
    proc = subprocess.run([sys.executable, SEMANTICSCRIPT, "run", path],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 134, (proc.returncode, proc.stderr)   # 128 + SIGABRT
    assert "EAV PANIC" in proc.stderr
    assert code in proc.stderr                                       # exact panic code
    assert op in proc.stderr                                        # trapping op named


def test_crash_area_examples_present():
    present = [n for n in _PANICS if os.path.isfile(os.path.join(EXAMPLES, n + ".sem"))]
    assert len(present) == len(_PANICS), present
