#!/usr/bin/env python3
"""`check ok:true` is a compiler trust statement, not just a lint statement."""
import importlib
import json
import os

import pytest

ss = importlib.import_module("semanticscript")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELLO = os.path.join(ROOT, "examples", "hello_world.sem")


def test_check_green_means_can_compile(capsys):
    rc = ss.main(["check", HELLO, "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["surface"] == "sem.check.v1"
    assert payload["ok"] is True
    assert payload["canCompile"] is True
    assert payload["cantCompile"] is False
    assert payload["compileProof"] == "lowered-llvm"


def test_check_fails_closed_when_backend_lowering_fails(monkeypatch, capsys):
    def fail_lower(*_args, **_kwargs):
        raise RuntimeError("synthetic LLVM verifier rejection")

    monkeypatch.setattr(ss, "lower_to_llvm", fail_lower)

    rc = ss.main(["check", HELLO, "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 1
    assert payload["surface"] == "sem.check.v1"
    assert payload["status"] == "codegen-error"
    assert payload["ok"] is False
    assert payload["canCompile"] is False
    assert payload["cantCompile"] is True
    assert payload["compileProof"] == "codegen-error"
    assert payload["compileDiagnostic"]["code"] == "SS5001"
    assert payload["diagnostics"][-1]["code"] == "SS5001"
    assert payload["nextCommands"][0]["argv"] == [
        "compensate", HELLO, "--mode", "codegen", "--json"]


def test_lint_blocked_check_never_runs_backend(monkeypatch, tmp_path, capsys):
    src = tmp_path / "bad.sem"
    src.write_text(
        "P is project\nP module m\nP target console\nP entry main\n"
        "m is module\nm path x.y\nm exports main\n"
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain let ok immutable ExitCode 0\n"
        "main return ok\n",
        encoding="utf-8",
    )

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("check lowered despite lint errors")

    monkeypatch.setattr(ss, "lower_to_llvm", fail_if_called)

    rc = ss.main(["check", str(src), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 1
    assert payload["status"] == "lint-diagnostics"
    assert payload["ok"] is False
    assert payload["canCompile"] is False
    assert payload["cantCompile"] is True
    assert payload["compileProof"] == "blocked-by-lint"
    assert {d["code"] for d in payload["diagnostics"]} >= {"MD1001", "MD1002"}
