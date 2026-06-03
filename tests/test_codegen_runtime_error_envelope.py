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
    assert data["diagnostics"][0]["code"] == "SS5001"


def test_call_codegen_error_keeps_source_line(monkeypatch):
    source = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm exports main\nm purpose "p"\nm invariant "i"\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        'main let text immutable String "hello"\n'
        "main let ok immutable ExitCode 0\nmain do show\nmain return ok\n"
        "show is call\nshow in main\nshow invokes console.writeLine\n"
        "show arg text String text\n"
        'show discards "console status"\n'
    )
    program = ss.parse_compact(source)
    expected_line = program.entities["show"].line

    def raise_from_call(self, call, builder, sym, let_mut):
        raise RuntimeError("LLVM type mismatch: i8* != i64")

    monkeypatch.setattr(ss.EavCodegen, "_emit_call_impl", raise_from_call)
    with pytest.raises(ss.EavError) as excinfo:
        ss.lower_to_llvm(program)
    assert excinfo.value.code == "SS5001"
    assert excinfo.value.line == expected_line
    assert "show" in excinfo.value.message
    assert "console.writeLine" in excinfo.value.message
