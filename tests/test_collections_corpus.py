#!/usr/bin/env python3
"""Collections corpus (X-207/X-209): growable-list iteration runs end to end.

The list runtime (list.create/append/length/get/release) is real and runnable.
These examples build a list and fold over it with a goto-loop — a sum and a
maximum — proving the result comes from iterating the list, not a constant (each
fails under a no-op lowering). Run through the real `run` lane and asserted green.
"""
import importlib
import os
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")
SEMANTICSCRIPT = semanticscript.__file__
EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")

_LIST = {
    "collections_list_sum": "210",  # 10+20+30+40+50+60
    "list_find_max": "60",          # max(10,50,30,60,20,40)
    "list_count_above": "3",        # # elements > 35: 50,60,40 (guarded loop)
}


@pytest.mark.parametrize("name,expected", sorted(_LIST.items()))
def test_list_example_runs_green(name, expected):
    path = os.path.join(EXAMPLES, name + ".sem")
    assert os.path.isfile(path), path
    proc = subprocess.run([sys.executable, SEMANTICSCRIPT, "run", path],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert "PASS" in proc.stdout and "FAIL" not in proc.stdout, proc.stdout
    assert expected in proc.stdout
