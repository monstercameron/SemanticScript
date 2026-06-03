#!/usr/bin/env python3
"""SEAM-2: composition conformance — the cross-subsystem round-trip is a collected CI golden.

The per-subsystem bars (auth, db, json, http) each pass in isolation; the live
blockers were always at the *seams*. This pins the register -> login -> create ->
list round-trip as a pytest-collected golden so the composition cannot silently
regress. It exercises, end to end against the real native runtime:

  * auth⊗db   — bcrypt hash -> store in sqlite -> read back -> constant-time verify
  * json⊗http — JSON request body parse + typed JSON response serialize over HTTP
  * db⊗json   — sqlite rows projected into JSON list payloads

Reuses the proven driver in test_apps.py so there is one source of truth for the
round-trip. Skipped (not failed) when no C compiler is available to build the
native sqlite/bcrypt/json runtime.
"""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
test_apps = importlib.import_module("test_apps")
semanticscript = importlib.import_module("semanticscript")


def test_seam2_register_login_tasks_round_trip_golden():
    if semanticscript._find_c_compiler() is None:
        pytest.skip("no C compiler for the native taskforge-web composition golden")
    # A port distinct from test_apps.py's 18090 so the script and this collected
    # test never contend for the same socket (the W2-I zombie-port hazard).
    ok, message = test_apps._run_webserver_crud("taskforge-web", 18097)
    assert ok, f"composition round-trip failed: {message}"
