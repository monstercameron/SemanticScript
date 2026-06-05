#!/usr/bin/env python3
"""X-208 / X-212: e2e coverage for the shipped file-I/O and JSON/SQL/HTML examples.

These two areas are not yet at the ≥10-app bar (they need more programs written —
multi-session content), but the runtime examples that DO exist are pinned here:
each self-asserting `tag test` program is run through the real `run` lane and
checked to self-assert green. Covers asset embedding + digest, file stat, path
join/normalize (X-208) and the json codec, sql query, and sqlite query/render
(X-212), so a regression in those runtimes turns the suite red.
"""
import importlib
import os
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")
SEMANTICSCRIPT = semanticscript.__file__
EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")

_FILE = ["asset_embed", "record_file_stat", "string_path_join", "string_path_normalize"]
_RUNTIME = ["json_codec_decode", "sql_execute_query", "sqlite_query"]


@pytest.mark.parametrize("name", sorted(_FILE + _RUNTIME))
def test_runtime_example_runs_green(name):
    path = os.path.join(EXAMPLES, name + ".sem")
    if not os.path.isfile(path):
        pytest.skip(f"{name} not present")
    proc = subprocess.run([sys.executable, SEMANTICSCRIPT, "run", path],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert "PASS" in proc.stdout and "FAIL" not in proc.stdout, proc.stdout
