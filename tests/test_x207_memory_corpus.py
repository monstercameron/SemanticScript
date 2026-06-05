#!/usr/bin/env python3
"""X-207: end-to-end coverage for the memory / regions / buffers corpus (§1J).

Each memory example is a self-asserting `tag test` program (`PASS …`, exit 0).
This discovers the shipped buffer/region/view/memory/transfer examples and runs
each through the real `run` lane, asserting it self-asserts green — the §X1c e2e
contract for the memory area (buffer get/set + round-trip, region arena alloc/
free + escape analysis, read-only views, alloc/dealloc, use-after-free and
double-free discipline, owned-resource transfer/move). Excludes `defer_*`
(covered by the cleanup area, X-206).
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


def _memory_examples():
    names = set()
    for pat in ("buffer*.sem", "region_*.sem", "view_*.sem", "memory_*.sem",
                "owned_resource_*.sem", "record_readonly_view.sem"):
        for p in glob.glob(os.path.join(EXAMPLES, pat)):
            names.add(os.path.basename(p))
    return sorted(names)


_EXAMPLES = _memory_examples()


def test_memory_area_has_at_least_ten_examples():
    assert len(_EXAMPLES) >= 10, _EXAMPLES


@pytest.mark.parametrize("name", _EXAMPLES)
def test_memory_example_runs_green(name):
    proc = subprocess.run([sys.executable, SEMANTICSCRIPT, "run", os.path.join(EXAMPLES, name)],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert "PASS" in proc.stdout and "FAIL" not in proc.stdout, proc.stdout
