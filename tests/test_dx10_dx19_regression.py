#!/usr/bin/env python3
"""Regression pins for DX-10 and DX-19 (both confirmed fixed; lock them down).

DX-10 — `targets --signature` was blind to opaque-handle targets (console / log /
json / sqlite-open / assert): it returned no signature for any target whose out is
an opaque pointer, leaving search-the-corpus as the only discovery path. The fix
generates a fallback signature so every modeled target answers. This pins that the
five representative opaque-handle targets each resolve to `sem.targetSignature.v1`.

DX-19 — the spec-canonical Bool test op (`out TestResult`, an alias for Bool,
returning a TestResult-typed value) miscompiled to invalid LLVM IR: `ret i1` into a
function whose return slot was lowered wider, tripping SSR0001 at JIT time. The fix
makes the function return type and the returned value agree. This pins that such an
op — actually CALLED from main so it is lowered and executed — checks clean and runs
green end to end (not merely parses).

Both are guarded here because they live in a file under heavy concurrent edit; a
refactor must not silently regress either without turning this red.
"""
import importlib
import json
import os
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")
SEMANTICSCRIPT = semanticscript.__file__


def _run(*args, **kw):
    return subprocess.run([sys.executable, SEMANTICSCRIPT, *args],
                          capture_output=True, text=True, encoding="utf-8", **kw)


# --- DX-10 -----------------------------------------------------------------

# Representative real targets across the families the bug named, deliberately
# including ones whose `out` is an OPAQUE handle pointer (JsonDocument, JsonCursor,
# SqliteDatabase) — exactly the case DX-10 said was blind. `out` is the expected
# return type ("" means a void/no-out target like a writer or close). Each must now
# resolve (`ok` true) instead of falling through to `unknown-target`.
_OPAQUE_TARGETS = [
    ("console.writeLine", ""),            # write target, no out
    ("log.logInfo", "Int32"),             # event/log family
    ("json.createDocument", "JsonDocument"),   # opaque-handle out
    ("json.documentRoot", "JsonCursor"),       # opaque-cursor out
    ("sqlite.openDatabase", "SqliteDatabase"), # opaque-db-handle out
    ("assert.equalInt64", "Bool"),        # assert family
]


@pytest.mark.parametrize("target,expected_out", _OPAQUE_TARGETS)
def test_dx10_opaque_target_has_signature(target, expected_out):
    proc = _run("targets", "--signature", target, "--json")
    payload = json.loads(proc.stdout)
    assert payload.get("surface") == "sem.targetSignature.v1", proc.stdout
    assert payload.get("ok") is True, "%s should resolve, got %s" % (target, proc.stdout)
    assert payload.get("status") == "ok", proc.stdout
    if expected_out:
        assert payload.get("out") == expected_out, proc.stdout


def test_dx10_genuinely_unknown_target_is_rejected():
    # the guard cuts the other way too: a name that is NOT in the vocabulary must
    # still report unknown-target (the fix generates fallbacks for MODELED targets,
    # it does not invent signatures for typos).
    proc = _run("targets", "--signature", "console.print", "--json")
    payload = json.loads(proc.stdout)
    assert payload.get("ok") is False, proc.stdout
    assert payload.get("status") == "unknown-target", proc.stdout


# --- DX-19 -----------------------------------------------------------------

# A Bool test op in the spec-canonical shape: `out TestResult` (alias for Bool),
# returning a TestResult-typed value, and CALLED from main so it is lowered and
# executed. Pre-fix this emitted `ret i1` into a wider return slot -> SSR0001.
_DX19_PROGRAM = """\
P is project
P module m
P target console
P entry main
m is module
m path a.b
m exports main
m purpose "p"
m invariant "i"
ExitCode is alias
ExitCode for Int32
TestResult is alias
TestResult for Bool
isPositive is operation
isPositive in n Int64
isPositive out TestResult
isPositive async no
isPositive purpose "p"
isPositive invariant "i"
isPositive let zero immutable Int64 0
isPositive do cmp
isPositive return result
cmp is call
cmp in isPositive
cmp invokes math.greaterThanInt64
cmp arg left Int64 n
cmp arg right Int64 zero
cmp out result TestResult
main is operation
main out ExitCode
main async no
main purpose "p"
main invariant "i"
main let five immutable Int64 5
main let expected immutable Int64 1
main let nm immutable String "isPositive(5) is true"
main do callit
main do checkit
main do rep
main return code
callit is call
callit in main
callit invokes isPositive
callit arg n Int64 five
callit out got TestResult
checkit is call
checkit in main
checkit invokes test.assertEqualInt64
checkit arg name String nm
checkit arg expected Int64 expected
checkit arg actual Int64 got
rep is call
rep in main
rep invokes test.summary
rep out code ExitCode
"""


@pytest.fixture
def dx19_path(tmp_path):
    p = tmp_path / "dx19_bool_op.sem"
    p.write_text(_DX19_PROGRAM, encoding="utf-8")
    return str(p)


def test_dx19_bool_op_checks_clean(dx19_path):
    proc = _run("check", dx19_path, "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload.get("status") == "ok", payload


def test_dx19_bool_op_runs_green(dx19_path):
    proc = _run("run", dx19_path)
    assert proc.returncode == 0, proc.stderr
    # no invalid-IR / JIT envelope
    assert "SSR0001" not in (proc.stdout + proc.stderr), proc.stdout + proc.stderr
    assert "PASS" in proc.stdout and "FAIL" not in proc.stdout, proc.stdout
    assert "1 passed, 0 failed" in proc.stdout, proc.stdout
