#!/usr/bin/env python3
"""R-057: `sem profile` emits a performance/IR baseline (sem.profile.v1).

The profiling roadmap gap had no actionable owner. `profile` now times parse +
lower (best of N) and reports IR-quality metrics (defined functions, basic
blocks, instructions, IR text size) and the source footprint (entity count by
kind) — a stable, machine-readable baseline for regression gates. (Runtime
allocation counters are a deeper slice needing C-runtime instrumentation.)
"""
import importlib
import json
import os

ss = importlib.import_module("semanticscript")
SEMANTICSCRIPT = ss.__file__
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _profile_json(rel, capsys):
    rc = ss.main(["profile", os.path.join(_REPO, rel), "--runs", "2", "--json"])
    out = capsys.readouterr().out
    return rc, json.loads(out)


def test_profile_emits_ir_and_source_metrics(capsys):
    rc, d = _profile_json("examples/add_two.sem", capsys)
    assert rc == 0 and d["surface"] == "sem.profile.v1"
    assert d["ir"]["functionsDefined"] >= 1
    assert d["ir"]["instructions"] > 0
    assert d["ir"]["textBytes"] > 0
    assert d["source"]["entities"] > 0
    assert isinstance(d["source"]["byKind"], dict) and d["source"]["byKind"]
    assert d["parseMsBest"] is not None and d["lowerMsBest"] is not None


def test_profile_surface_is_registered():
    # R-123: the surface must be in the version registry (version --json contract)
    assert "sem.profile.v1" in ss.SEM_SURFACES


def test_profile_json_error_envelope_on_bad_source(capsys):
    # profile is JSON-native, so a parse error is a structured envelope, not a crash
    rc = ss.main(["profile", os.path.join(_REPO, "tests", "invalid_corpus",
                                          "03_unknown_kind.sem"), "--json"])
    d = json.loads(capsys.readouterr().out)
    assert rc == 2 and d["ok"] is False and d["surface"] == "sem.error.v1"
