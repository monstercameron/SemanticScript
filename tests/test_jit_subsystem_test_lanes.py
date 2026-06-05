#!/usr/bin/env python3
"""ITER-1 / BIN-4 regression guard: the JIT links the native runtime, so the
component / integration test lanes actually *run* native-runtime subsystems
(sqlite, bcrypt) — no native `build` required.

This was once the #1 structural gap: `run`/`eval`/the test runner could not
execute sqlite/bcrypt programs ("not modeled by the LLVM console code
generator"), so two-thirds of the testing pyramid (component + integration)
was unrunnable and behavior could only be proved on the native binary. The JIT
now builds + loads the native runtime DLLs through `_register_runtime_symbols`
(see `jit_run`), closing the gap. These tests lock it shut so it cannot
silently re-open:

  * a sqlite-backed test op tagged `component` runs green under the JIT test
    runner and produces *real* query output under `run` (not a constant);
  * a bcrypt-backed test op tagged `integration` runs green under the JIT test
    runner (the owned hash actually allocates, so the ifError branch is NOT
    taken);
  * none of these paths emit the "not modeled by the LLVM console code
    generator" diagnostic, and none require a `build`.
"""
import importlib
import json
import os
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")
SEMANTICSCRIPT = semanticscript.__file__
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQLITE_EXAMPLE = os.path.join(ROOT, "examples", "sqlite_query.sem")

_NOT_MODELED = "not modeled by the LLVM console code generator"


def _requires_cc():
    if semanticscript._find_c_compiler() is None:
        pytest.skip("no C compiler to build the native runtime libs the JIT loads")


def _cli(*args, stdin=None):
    proc = subprocess.run(
        [sys.executable, SEMANTICSCRIPT, *args],
        input=stdin, capture_output=True, text=True, encoding="utf-8",
    )
    return proc


def _tagged(source: str, lane: str) -> str:
    """Tag the example's `main` as a test op in `lane` (an op with no lane tag is
    a unit test; `tag test <lane>` realizes the component/integration/... lanes)."""
    return source.replace(
        "main async no\n",
        f"main async no\nmain tag test\nmain tag {lane}\n",
        1,
    )


_BCRYPT_PROGRAM = (
    "P is project\nP module m\nP target console\nP entry main\n"
    "m is module\nm path a.b\nm purpose \"p\"\nm invariant \"i\"\nm exports main\n"
    "ExitCode is alias\nExitCode for Int32\n"
    "HashError is error\n"
    "bcryptHashCompute is capability\n"
    "bcryptHashCompute grants compute bcryptHash\n"
    "bcryptHashCompute purpose \"run bcrypt\"\n"
    "main is operation\nmain out ExitCode\nmain async no\n"
    "main tag test\nmain tag integration\n"
    "main effect compute bcryptHash\nmain uses bcryptHashCompute\n"
    "main purpose \"p\"\nmain invariant \"i\"\n"
    "main let pw immutable String \"secret-pw\"\n"
    "main let cost immutable Int32 12\n"
    "main let okCode immutable ExitCode 0\n"
    "main let failCode immutable ExitCode 7\n"
    "main do hashIt\nmain branch ifError hashIt goto failed\n"
    "main do freeIt\nmain return okCode\n"
    "main at failed return failCode\n"
    "hashIt is call\nhashIt in main\nhashIt invokes bcrypt.hashPasswordOwned\n"
    "hashIt arg plaintext String pw\nhashIt arg cost Int32 cost\n"
    "hashIt out hashHandle OpaquePointer\nhashIt catch hashErr HashError\n"
    "freeIt is call\nfreeIt in main\nfreeIt invokes bcrypt.freeString\n"
    "freeIt arg handle OpaquePointer hashHandle\nfreeIt discards \"freed\"\n"
)


@pytest.mark.parametrize("lane", ["component", "integration"])
def test_sqlite_lane_runs_under_jit_test_runner(lane):
    """A sqlite-backed `tag test <lane>` op passes through the JIT test runner."""
    _requires_cc()
    with open(SQLITE_EXAMPLE, encoding="utf-8") as fh:
        source = _tagged(fh.read(), lane)
    proc = _cli("test", "-", "--lane", lane, "--json", stdin=source)
    assert _NOT_MODELED not in (proc.stdout + proc.stderr)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    data = json.loads(proc.stdout)
    assert data["compositeStatus"] == "pass", data
    assert data["runtimeHarnessStatus"] == "pass", data
    assert [t["lane"] for t in data["tests"]] == [lane]
    assert all(t["status"] == "pass" for t in data["tests"]), data


def test_sqlite_run_produces_real_query_output_under_jit():
    """`run` (JIT) executes real SQL — not a type-check, not a constant."""
    _requires_cc()
    proc = _cli("run", SQLITE_EXAMPLE, "--json")
    assert _NOT_MODELED not in (proc.stdout + proc.stderr)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    data = json.loads(proc.stdout)
    assert data["status"] == "ok", data
    # SUM(n)=60 is an aggregate over the inserted rows; a stub/constant could not
    # produce it alongside COUNT(*)=3 from the same in-memory db.
    assert "SUM(n) is 60" in data["stdout"], data
    assert "4 passed, 0 failed" in data["stdout"], data


def test_bcrypt_integration_lane_runs_under_jit_test_runner():
    """A bcrypt-backed `tag test integration` op passes through the JIT test
    runner: the owned hash allocates a non-null handle, so the ifError branch is
    not taken and the op returns 0."""
    _requires_cc()
    proc = _cli("test", "-", "--lane", "integration", "--json",
                stdin=_BCRYPT_PROGRAM)
    assert _NOT_MODELED not in (proc.stdout + proc.stderr)
    assert proc.returncode == 0, proc.stderr or proc.stdout
    data = json.loads(proc.stdout)
    assert data["compositeStatus"] == "pass", data
    assert data["runtimeHarnessStatus"] == "pass", data
    assert [t["lane"] for t in data["tests"]] == ["integration"]
    assert data["tests"][0]["status"] == "pass", data
