#!/usr/bin/env python3
"""Harden the JIT test runner against a transient harness-startup flake.

The runner isolates each `tag test` op in a spawned `run` child (R-102). The
non-frozen child re-reads + recompiles the large compiler source on every spawn;
on Windows a concurrent / AV-interrupted read of that file can surface as a
transient SyntaxError at import time. Such a child never ran the op, so the
result is a *harness* flake — not a test outcome.

These tests lock the two-part hardening:
  1. `_is_harness_startup_failure` recognizes the crash (raw interpreter
     traceback, empty stdout, nonzero exit) and nothing else (a real
     `semanticscript:` diagnostic, an ss_panic, or a clean/output run are NOT
     harness failures);
  2. `_run_child_with_retry` retries it (so a one-off flake recovers); and
  3. `run_tests` grades a *persistent* harness crash as `error` (broken harness),
     never a test `fail`.
"""
import importlib
import types

import pytest

semanticscript = importlib.import_module("semanticscript")

_PY_TRACEBACK = (
    'Traceback (most recent call last):\n'
    '  File "semanticscript.py", line 9004\n'
    '    for c in program.entities.values():\n'
    '                  ^\n'
    "SyntaxError: expected ':'\n"
)


# ---- 1. the detector -------------------------------------------------------

def test_raw_interpreter_traceback_is_a_harness_failure():
    assert semanticscript._is_harness_startup_failure("", _PY_TRACEBACK, 1)


def test_clean_run_is_not_a_harness_failure():
    assert not semanticscript._is_harness_startup_failure("PASS\n", "", 0)


def test_output_with_nonzero_exit_is_not_a_harness_failure():
    # the program ran and printed before exiting nonzero — a real result
    assert not semanticscript._is_harness_startup_failure("partial\n", _PY_TRACEBACK, 1)


def test_structured_diagnostic_is_not_a_harness_failure():
    # a `semanticscript:` compile/check diagnostic is a legitimate program result
    err = "semanticscript: SS1198 call target not modeled\n"
    assert not semanticscript._is_harness_startup_failure("", err, 2)


def test_ss_panic_trap_is_not_a_harness_failure():
    # an ss_panic trap is a legitimate (crashed) result, not a startup flake.
    # `_parse_panic` keys on the `EAV PANIC SSR#### <kind>` marker (WS1-135).
    panic_err = "EAV PANIC SSR0001 assert\nop: main\nat line: 3\n"
    assert semanticscript._parse_panic(panic_err) is not None  # guard the fixture
    assert not semanticscript._is_harness_startup_failure("", panic_err, 134)


# ---- 2. the retry ----------------------------------------------------------

def test_retry_recovers_a_transient_startup_crash(monkeypatch):
    import subprocess
    import time

    calls = {"n": 0}
    flake = types.SimpleNamespace(stdout="", stderr=_PY_TRACEBACK, returncode=1)
    good = types.SimpleNamespace(stdout="ok\n", stderr="", returncode=0)

    def fake_run(*a, **k):
        calls["n"] += 1
        return flake if calls["n"] < 3 else good  # flake twice, then succeed

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(time, "sleep", lambda *_: None)  # no real backoff

    proc = semanticscript._run_child_with_retry(["run", "-"], "src", None, 5.0)
    assert proc.returncode == 0
    assert proc.stdout == "ok\n"
    assert calls["n"] == 3  # two flakes retried, third attempt returned the result


def test_retry_gives_up_after_the_bound(monkeypatch):
    import subprocess
    import time

    calls = {"n": 0}
    flake = types.SimpleNamespace(stdout="", stderr=_PY_TRACEBACK, returncode=1)

    def fake_run(*a, **k):
        calls["n"] += 1
        return flake  # always flakes

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    proc = semanticscript._run_child_with_retry(["run", "-"], "src", None, 5.0)
    assert proc.returncode == 1  # returns the last (failed) attempt, doesn't hang
    assert calls["n"] == semanticscript._HARNESS_SPAWN_RETRIES + 1


def test_clean_run_is_not_retried(monkeypatch):
    import subprocess

    calls = {"n": 0}
    good = types.SimpleNamespace(stdout="done\n", stderr="", returncode=0)

    def fake_run(*a, **k):
        calls["n"] += 1
        return good

    monkeypatch.setattr(subprocess, "run", fake_run)
    proc = semanticscript._run_child_with_retry(["run", "-"], "src", None, 5.0)
    assert proc.returncode == 0
    assert calls["n"] == 1  # the happy path spawns exactly once, never sleeps


# ---- 3. grading: a persistent harness crash is `error`, not `fail` ---------

_TEST_PROGRAM = (
    "P is project\nP module m\nP target console\nP entry main\n"
    'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
    "ExitCode is alias\nExitCode for Int32\n"
    "main is operation\nmain out ExitCode\nmain async no\nmain tag test\n"
    'main purpose "p"\nmain invariant "i"\n'
    "main let okCode immutable ExitCode 0\nmain return okCode\n"
)


def test_persistent_harness_crash_grades_as_error_not_fail(monkeypatch):
    program = semanticscript.parse(_TEST_PROGRAM)
    # sanity: the program lints clean, so preflight passes and the op is discovered
    assert not any(d.severity == "error" for d in semanticscript.lint(program))

    monkeypatch.setattr(
        semanticscript, "_record_run_entry",
        lambda *a, **k: ("", _PY_TRACEBACK, 1))  # simulate a persistent crash

    result = semanticscript.run_tests(program)
    assert result["tests"], result
    rec = result["tests"][0]
    assert rec["status"] == "error", rec       # NOT "fail"
    assert "harness" in rec, rec               # carries the harness reason
    # the runtime/composite status reflects a non-pass, but as an error not a fail
    assert result["runtimeHarnessStatus"] != "pass"


def test_real_assertion_failure_still_grades_as_fail(monkeypatch):
    # a genuine nonzero exit with program output (assertions failed) stays `fail` —
    # the hardening must not swallow real test failures.
    program = semanticscript.parse(_TEST_PROGRAM)
    monkeypatch.setattr(
        semanticscript, "_record_run_entry",
        lambda *a, **k: ("---- 0 passed, 1 failed ----\n", "", 1))

    result = semanticscript.run_tests(program)
    rec = result["tests"][0]
    assert rec["status"] == "fail", rec
    assert "harness" not in rec, rec
