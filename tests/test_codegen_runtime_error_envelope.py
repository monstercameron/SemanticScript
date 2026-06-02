#!/usr/bin/env python3
"""R-231: a RuntimeError from the codegen/verify path becomes a JSON envelope.

llvmlite raises RuntimeError when LLVM rejects malformed or unverifiable IR
(llvm.parse_assembly / module.verify). That path is reachable from JSON-native
commands (bench, inspect-ir, run, emit-ir), but main()'s dispatch only mapped
EavError/OSError to an envelope — a RuntimeError escaped as a raw Python
traceback and nonzero abort, which an MCP/agent consumer cannot parse. main() now
maps RuntimeError to a sem.error.v1 `codegen-error` envelope.

The fix is the central mapping, so the test forces the codegen path to raise a
RuntimeError (a stand-in for an LLVM rejection) and asserts the commands return a
structured envelope rather than propagating the exception.
"""
import importlib
import json
import os

import pytest

ss = importlib.import_module("semanticscript")

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EXAMPLE = os.path.join(_REPO, "examples", "add_two.sem")


def _raise_runtime(*_a, **_k):
    raise RuntimeError("LLVM ERROR: instruction does not dominate all uses (verify)")


@pytest.mark.parametrize("command", ["bench", "inspect-ir"])
def test_codegen_runtime_error_is_structured_envelope(command, monkeypatch, capsys):
    # both commands lower via lower_to_llvm before any IR text/verify; raising
    # there reproduces "the codegen path raised a RuntimeError" without needing a
    # pathological program that actually produces verify-rejected IR.
    monkeypatch.setattr(ss, "lower_to_llvm", _raise_runtime)
    argv = [command, _EXAMPLE, "--json"]
    if command == "bench":
        argv[2:2] = ["--runs", "1"]
    rc = ss.main(argv)               # must NOT raise
    out = capsys.readouterr().out
    data = json.loads(out)           # must be a single JSON envelope
    assert rc == 2
    assert data["surface"] == "sem.error.v1"
    assert data["status"] == "codegen-error"
    assert data["ok"] is False
    assert data["command"] == command
