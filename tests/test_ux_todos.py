#!/usr/bin/env python3
import contextlib
import importlib
import io
import json
import os
import subprocess
import sys

import pytest


ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, "semanticscript", "compiler"))
ss = importlib.import_module("semanticscript")
EXAMPLES = os.path.join(ROOT, "examples")


_T3_WARNING_PROGRAM = (
    "P is project\nP module m\nP target console\nP entry main\n"
    'm is module\nm path examples.strict\nm purpose "m"\n'
    'm invariant "i"\nm exports main\n'
    "ExitCode is alias\nExitCode for Int32\n"
    "helper is operation\nhelper in n ExitCode\nhelper out ExitCode\n"
    "helper async no\nhelper return n\n"
    "main is operation\nmain out ExitCode\nmain async no\n"
    'main purpose "entry"\nmain invariant "ret"\n'
    "main let zero immutable ExitCode 0\nmain do callHelper\nmain return code\n"
    "callHelper is call\ncallHelper in main\ncallHelper invokes helper\n"
    "callHelper arg n ExitCode zero\ncallHelper out code ExitCode\n"
)


def test_check_envelope_says_static_only_and_warns_not_enforced(tmp_path, capsys):
    src = tmp_path / "warn.sem"
    src.write_text(_T3_WARNING_PROGRAM, encoding="utf-8")

    rc = ss.main(["check", str(src), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["surface"] == "sem.check.v1"
    assert payload["status"] == "ok-with-warnings"
    assert payload["lane"] == "static-source"
    assert payload["strict"] is False
    assert payload["warningCount"] == 1
    assert "not enforced" in payload["note"]
    commands = [c["argv"][0] for c in payload["nextCommands"]]
    assert "run" in commands
    assert "build" in commands

    strict_rc = ss.main(["check", str(src), "--strict", "--json"])
    strict_payload = json.loads(capsys.readouterr().out)
    assert strict_rc == 1
    assert strict_payload["strict"] is True
    assert strict_payload["status"] == "lint-diagnostics"


def test_fmt_check_teaches_canonical_order(tmp_path, capsys):
    drift = tmp_path / "drift.sem"
    drift.write_text(
        "main is operation\nmain out ExitCode\n"
        "ExitCode is alias\nExitCode for Int32\n",
        encoding="utf-8",
    )

    rc = ss.main(["fmt", str(drift), "--check"])
    captured = capsys.readouterr()

    assert rc == 1
    assert "expected entity order" in captured.err
    assert "capability -> error -> errorCase -> alias" in captured.err


def test_builtin_lookup_works_in_describe_docs_and_targets(capsys):
    path = os.path.join(EXAMPLES, "hello_world.sem")

    assert ss.main(["describe", path, "math.divideInt64"]) == 0
    describe = capsys.readouterr().out
    assert "intrinsic math.divideInt64" in describe
    assert "arg left Int64" in describe
    assert "risk" in describe

    assert ss.main(["docs", path, "--get", "math.divideInt64", "--json"]) == 0
    docs = json.loads(capsys.readouterr().out)
    assert docs["entity"]["kind"] == "intrinsic"
    assert docs["entity"]["signature"]["target"] == "math.divideInt64"
    assert docs["entity"]["signature"]["args"][0] == {"slot": "left", "type": "Int64"}

    assert ss.main(["targets", "--signature", "math.divideInt64", "--json"]) == 0
    target = json.loads(capsys.readouterr().out)
    assert target["surface"] == "sem.targetSignature.v1"
    assert target["out"] == "Int64"


def test_ss3111_mentions_non_constant_divisor_for_runtime_guard():
    src = (
        "calc is operation\ncalc out Int64\ncalc async no\n"
        'calc purpose "p"\ncalc invariant "i"\n'
        "calc let n immutable Int64 10\ncalc let zero immutable Int64 0\n"
        "calc do div\ncalc return q\n"
        "div is call\ndiv in calc\ndiv invokes math.divideInt64\n"
        "div arg left Int64 n\ndiv arg right Int64 zero\ndiv out q Int64\n"
    )
    with pytest.raises(ss.EavError) as exc:
        ss.parse(src)
    assert getattr(exc.value, "code", None) == "SS3111"
    assert "non-constant" in str(exc.value)
    repair = ss.format_repair("SS3111")
    assert "runtime" in repair
    assert "guard" in repair


def test_fallible_operation_recipe_is_discoverable(capsys):
    assert ss.main(["skills", "eav-fallible-operation", "--json"]) == 0
    skill = json.loads(capsys.readouterr().out)
    assert "branch ifError" in skill["skills"][0]["body"]

    assert ss.main(["task", "model-fallible-operation", "--json"]) == 0
    task = json.loads(capsys.readouterr().out)
    assert "<op> branch ifError <call> goto failed" in task["rowsToAdd"]

    scaffolded = ss.scaffold("fallible-operation")
    program = ss.parse(scaffolded)
    assert not [d for d in ss.lint(program) if d.severity == "error"]


def test_human_diagnostics_are_ascii_safe_for_windows_console():
    rendered = ss.Diagnostic(
        "SS0000", "warning", "README §33.5 — use A → B"
    ).render()
    repair = ss.format_repair("SS1502")
    combined = rendered + "\n" + repair
    assert "\ufffd" not in combined
    assert "§" not in combined
    assert all(ord(ch) < 128 for ch in combined)
    assert "README ss33.5 - use A -> B" in rendered
    assert "README ss12" in repair


def test_reserved_words_are_discoverable(capsys):
    assert ss.main(["reserved-words", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["surface"] == "sem.reservedWords.v1"
    assert "branch" in payload["words"]
    assert "ifTrue" in payload["words"]


def test_iftrue_branch_lowers_like_if():
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
        "main let flag immutable Bool true\nmain let okc immutable ExitCode 0\n"
        "main let fail immutable ExitCode 1\n"
        "main branch ifTrue flag goto success\nmain return fail\n"
        "main at success return okc\n"
    )
    out, err, code = ss._record_run_full(src)
    assert code == 0, err
    assert out == ""


def test_result_nil_error_allows_opaque_pointer_null_sentinel():
    src = (
        "P is project\nP module m\nP target console\nP entry op\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports op\n'
        "op is operation\nop out Result OpaquePointer Int32\nop async no\n"
        'op purpose "p"\nop invariant "i"\n'
        "op let err immutable Int32 7\nop return nil err\n"
    )
    program = ss.parse(src)
    assert "SS3049" not in {d.code for d in ss.lint(program)}
    ss.lower_to_llvm(program)


def test_ss3111_constants_are_scoped_per_operation():
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
        "main let n immutable Int64 10\nmain let divisor immutable Int64 2\n"
        "main let okc immutable ExitCode 0\nmain do div\nmain return okc\n"
        "div is call\ndiv in main\ndiv invokes math.divideInt64\n"
        "div arg left Int64 n\ndiv arg right Int64 divisor\ndiv out q Int64\n"
        "helper is operation\nhelper out ExitCode\nhelper async no\n"
        "helper let divisor immutable Int64 0\nhelper return divisor\n"
    )
    program = ss.parse(src)
    assert not [d for d in ss.lint(program) if d.code == "SS3111"]


def test_frozen_self_spawn_omits_bundled_script_path(monkeypatch):
    monkeypatch.setattr(ss.sys, "executable", r"C:\app\semanticscript.exe")
    monkeypatch.setattr(ss.sys, "frozen", True, raising=False)
    assert ss._self_cli_argv() == [r"C:\app\semanticscript.exe"]

    monkeypatch.setattr(ss.sys, "frozen", False, raising=False)
    argv = ss._self_cli_argv()
    assert argv[0] == r"C:\app\semanticscript.exe"
    assert argv[1].endswith("semanticscript.py")


def test_windows_explicit_build_output_gets_exe_suffix(monkeypatch):
    monkeypatch.setattr(ss.sys, "platform", "win32")
    assert ss._default_build_output("app.sem", "dist/app") == os.path.join("dist", "app.exe")
    assert ss._default_build_output("app.sem", "dist/app.exe") == os.path.join("dist", "app.exe")


def test_bench_reports_run_timing_for_native_runtime_sqlite():
    proc = subprocess.run(
        [
            sys.executable,
            os.path.join(ROOT, "semanticscript", "compiler", "semanticscript.py"),
            "bench",
            os.path.join(ROOT, "examples", "sqlite_query.sem"),
            "--runs",
            "1",
            "--json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["surface"] == "sem.bench.v1"
    assert payload["runnable"] is True
    assert payload["runStatus"] == "ok"
    assert payload["runMsBest"] is not None


def test_assert_equal_int64_cannot_be_discarded():
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
        "main let left immutable Int64 1\nmain let right immutable Int64 2\n"
        "main let okc immutable ExitCode 0\nmain do checkIt\nmain return okc\n"
        "checkIt is call\ncheckIt in main\ncheckIt invokes assert.equalInt64\n"
        "checkIt arg left Int64 left\ncheckIt arg right Int64 right\n"
        "checkIt discards \"assertions should not fail the test\"\n"
    )
    with pytest.raises(ss.EavError) as exc:
        ss.parse(src)
    assert getattr(exc.value, "code", None) == "SS1204"


def test_builtin_sqlite_sql_slot_requires_sqltext_not_string():
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "SqliteDatabase is alias\nSqliteDatabase for Int64\n"
        "SqlText is alias\nSqlText for String\nSqlText typeTrust validated\n"
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
        "main let db immutable SqliteDatabase 0\nmain let raw immutable String \"SELECT 1\"\n"
        "main let okc immutable ExitCode 0\nmain do runQuery\nmain return okc\n"
        "runQuery is call\nrunQuery in main\nrunQuery invokes sqlite.exec\n"
        "runQuery arg database SqliteDatabase db\nrunQuery arg sql String raw\n"
        "runQuery discards \"status not relevant\"\n"
    )
    codes = {d.code for d in ss.lint(ss.parse(src)) if d.severity == "error"}
    assert "SS1201" in codes

    safe = src.replace('raw immutable String "SELECT 1"', 'safeSql immutable SqlText "SELECT 1"')
    safe = safe.replace("arg sql String raw", "arg sql SqlText safeSql")
    codes = {d.code for d in ss.lint(ss.parse(safe)) if d.severity == "error"}
    assert "SS1201" not in codes

    sqlite_sig = open(
        os.path.join(ROOT, "semanticscript", "sigs", "standard.sqlite.semsig"),
        encoding="utf-8",
    ).read()
    assert "SqlText typeTrust validated" in sqlite_sig

    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = ss.main(["scaffold", "db-roundtrip"])
    assert rc == 0
    assert "SqlText typeTrust validated" in stdout.getvalue()
