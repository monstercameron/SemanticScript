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
