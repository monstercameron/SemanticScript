#!/usr/bin/env python3
"""X-205: end-to-end coverage for the effects / capabilities corpus (§8/§15/§2I).

Runs the positive, self-asserting effect/capability examples through the real
`run` lane and asserts each reaches its green harness summary — the §X1c e2e
contract for the effects area: capability-backed effect use, an effect declared
where it is used, a transitive effect flowing up from a called op, and a purity
proof for a no-effect operation. (The negative cases — uncovered/undeclared
effect, effect-bound escape — are gate-rejections covered by the effect-coverage
tests in test_semanticscript.py and the capability_ungranted_use fixture.)
"""
import importlib
import os
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")
SEMANTICSCRIPT = semanticscript.__file__
EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")

_POSITIVE = [
    "capability_grant_use",        # capability-backed effect use
    "effect_covered_console",      # a covered console effect
    "effect_declare_match",        # declared effect matches the capability
    "effect_declared_where_used",  # effect declared at its use site
    "effect_transitive_user_op",   # effect flows up from a called op (new)
    "effect_pure_helper",          # purity proof for a no-effect op (new)
]


@pytest.mark.parametrize("name", _POSITIVE)
def test_effect_example_runs_green(name):
    path = os.path.join(EXAMPLES, name + ".sem")
    assert os.path.isfile(path), path
    proc = subprocess.run([sys.executable, SEMANTICSCRIPT, "run", path],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert "PASS" in proc.stdout and "FAIL" not in proc.stdout, proc.stdout
