#!/usr/bin/env python3
"""FIX-1: scaffold/signature coherence — generated code must check clean.

A scaffold the agent reaches for must produce code that passes `check` (and thus
lower/run), or the tool is teaching incoherent code. This guards every scaffold
pattern.
"""
import importlib
import os
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SC = os.path.join(ROOT, "semanticscript", "compiler", "semanticscript.py")

PATTERNS = list(getattr(semanticscript, "SCAFFOLD_PATTERNS",
                        ("console-program", "fallible-write", "fallible-operation",
                         "trust-boundary", "json-output", "json-decode",
                         "db-roundtrip", "logged-op")))


def _scaffold_error_count(pattern):
    src = subprocess.run([sys.executable, SC, "scaffold", pattern],
                         capture_output=True, text=True, encoding="utf-8").stdout
    out = subprocess.run([sys.executable, SC, "check", "-", "--json"],
                         input=src, capture_output=True, text=True, encoding="utf-8")
    import json
    return json.loads(out.stdout).get("errorCount", -1), src


@pytest.mark.parametrize("pattern", PATTERNS)
def test_fix1_scaffold_checks_clean(pattern):
    errc, src = _scaffold_error_count(pattern)
    assert errc == 0, f"scaffold {pattern!r} does not check clean ({errc} errors):\n{src[:300]}"
