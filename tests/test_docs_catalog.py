#!/usr/bin/env python3
"""R1: `docs` with no path browses the builtin/stdlib catalog (list / get / search).

`docs --help` advertises a docs catalog (list/get/search), but the command used to
require a path: no path returned {ok:false, status:"missing-path"}, and --get/
--search only ran against a source file's entities — the catalog was reachable
only via `docs search --db`. Now `docs` (no path) lists the catalog, `docs --get
NAME` resolves a builtin signature, and `docs --search QUERY` ranks the catalog;
a path still selects per-file entities.
"""
import importlib
import json
import os
import subprocess
import sys

semanticscript = importlib.import_module("semanticscript")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SC = os.path.join(ROOT, "semanticscript", "compiler", "semanticscript.py")


def _docs(*args):
    proc = subprocess.run([sys.executable, SC, "docs", *args],
                          capture_output=True, text=True, encoding="utf-8")
    return json.loads(proc.stdout), proc.returncode


def test_r1_docs_no_path_lists_catalog():
    payload, rc = _docs()
    assert rc == 0
    assert payload.get("source") == "catalog"
    assert payload.get("count", 0) > 50          # the full builtin/stdlib surface
    names = {e["name"] for e in payload.get("entries", [])}
    assert "math.divideInt64" in names


def test_r1_docs_get_resolves_a_catalog_signature():
    payload, rc = _docs("--get", "math.divideInt64")
    assert rc == 0 and payload.get("ok") is True
    assert payload.get("source") == "catalog"
    assert payload["entity"]["name"] == "math.divideInt64"
    assert payload["entity"].get("signature") is not None


def test_r1_docs_search_ranks_the_catalog():
    payload, rc = _docs("--search", "divide")
    assert rc == 0
    assert payload.get("source") == "catalog"
    results = payload.get("results", [])
    assert results and any("divide" in r["name"].lower() for r in results)


def test_r1_docs_with_path_still_uses_file_entities():
    payload, rc = _docs(os.path.join(ROOT, "examples", "hello_world.sem"))
    assert rc == 0
    assert payload.get("source", "").endswith("hello_world.sem")
    assert payload.get("count", 0) >= 1
