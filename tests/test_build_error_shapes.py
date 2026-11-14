#!/usr/bin/env python3
"""R-235: `build` never leaks an OSError traceback and has one error shape.

cmd_build was not JSON-native, so main()'s OSError handler re-raised — an
unwritable/invalid output path (os.makedirs / file write in build_executable)
crashed with a raw traceback. And the command had three output shapes (a
sem.build.v1 envelope on unknown-platform, a bare exe-path string on success, a
plaintext stderr line on EavError). cmd_build now catches OSError, routes every
failure through the structured sem.build.v1 error shape under --json (a clean
`semanticscript:` line otherwise), and emits a sem.build.v1 success envelope
under --json — so a --json consumer sees exactly one shape.
"""
import importlib
import json
import os

ss = importlib.import_module("semanticscript")

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EXAMPLE = os.path.join(_REPO, "examples", "add_two.sem")
# a parent component that is an existing FILE -> makedirs/open raises OSError,
# before any toolchain is invoked (so the test is fast and host-independent).
_BAD_OUT = os.path.join(_EXAMPLE, "nope", "app.exe")


def test_bad_output_path_no_traceback_plain(capsys):
    rc = ss.main(["build", _EXAMPLE, "-o", _BAD_OUT])     # must NOT raise
    captured = capsys.readouterr()
    assert rc == 2
    assert captured.err.startswith("semanticscript:")     # clean line, not a traceback
    assert "Traceback" not in captured.err


def test_bad_output_path_json_envelope(capsys):
    rc = ss.main(["build", _EXAMPLE, "--json", "-o", _BAD_OUT])  # must NOT raise
    data = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert data["surface"] == "sem.build.v1"
    assert data["ok"] is False
    assert data["status"] == "io-error"


def test_build_is_json_native(capsys):
    # R-097: --json must not fall through to the "json-unsupported" envelope now
    # that build emits sem.build.v1; the bad-path run above already exercised the
    # native path, so a json error envelope (not sem.unsupported.v1) confirms it.
    ss.main(["build", _EXAMPLE, "--json", "-o", _BAD_OUT])
    data = json.loads(capsys.readouterr().out)
    assert data["surface"] == "sem.build.v1"
