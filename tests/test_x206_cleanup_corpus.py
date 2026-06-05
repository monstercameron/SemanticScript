#!/usr/bin/env python3
"""X-206: end-to-end coverage for the cleanup / ownership / defer corpus (§15.6).

Each cleanup/defer example is a self-asserting `tag test` program (prints `PASS …`
and exits 0). This discovers every shipped defer/cleanup/owned example and runs
it through the real `run` lane, asserting it self-asserts green — the §X1c e2e
contract for the cleanup area (reverse-order defers, lock/mutex release, env
restore, memory free, error-path cleanup, owned-resource disposal, …).
"""
import glob
import importlib
import os
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")
SEMANTICSCRIPT = semanticscript.__file__
EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")


def _cleanup_examples():
    names = set()
    for pat in ("defer_*.sem", "*cleanup*.sem", "owned_*.sem", "*owns*.sem"):
        for p in glob.glob(os.path.join(EXAMPLES, pat)):
            names.add(os.path.basename(p))
    return sorted(names)


_EXAMPLES = _cleanup_examples()


def test_cleanup_area_has_at_least_ten_examples():
    assert len(_EXAMPLES) >= 10, _EXAMPLES


@pytest.mark.parametrize("name", _EXAMPLES)
def test_cleanup_example_runs_green(name):
    proc = subprocess.run([sys.executable, SEMANTICSCRIPT, "run", os.path.join(EXAMPLES, name)],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert "PASS" in proc.stdout and "FAIL" not in proc.stdout, proc.stdout
