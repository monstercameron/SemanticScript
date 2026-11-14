#!/usr/bin/env python3
"""CYC-31..48 agent-loop smoothing regressions."""
import importlib
import json
import socket

import pytest

ss = importlib.import_module("semanticscript")


def _payload(capsys):
    return json.loads(capsys.readouterr().out)


def _bad_target_source():
    return (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm exports main\nm purpose "p"\nm invariant "i"\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let ok immutable ExitCode 0\nmain do bogus\nmain return ok\n"
        "bogus is call\nbogus in main\nbogus invokes buffer.notARealTarget\n"
        'bogus discards "not a modeled builtin"\n'
    )


def test_derive_record_contract_covers_json_sql_handlers_and_tests(tmp_path, capsys):
    path = tmp_path / "record.sem"
    path.write_text(
        "Todo is record\n"
        "Todo field id Int64\n"
        "Todo field title String\n"
        "Todo field done Bool\n",
        encoding="utf-8",
    )
    assert ss.main(["derive", str(path), "Todo", "--json"]) == 0
    payload = _payload(capsys)
    contract = payload
    assert payload["surface"] == "sem.derive.v1"
    assert contract["sql"]["createTableSql"] == (
        "CREATE TABLE IF NOT EXISTS todo (id INTEGER, title TEXT, done INTEGER)"
    )
    assert contract["sql"]["insertSql"] == (
        "INSERT INTO todo (id, title, done) VALUES (?, ?, ?)"
    )
    assert {c["target"] for c in contract["jsonCodec"]["encodeCalls"]} == {
        "json.setObjectFieldInt64",
        "json.setObjectFieldString",
        "json.setObjectFieldBool",
    }
    assert contract["handler"]["validation"][0]["rule"] == "required"
    assert "clock" in contract["testControls"]
    assert "rng" in contract["testControls"]


def test_new_scaffold_patterns_parse_and_rich_assertions_run():
    for pattern in [
        "crud-endpoint",
        "migration",
        "audit-log",
        "pagination",
        "test-fixture",
        "http-drive-test",
    ]:
        program = ss.parse_compact(ss.scaffold(pattern))
        assert program.order
    assert ss._record_run_full(ss.scaffold("test-fixture"))[2] == 0
    assert ss._record_run_full(ss.scaffold("http-drive-test"))[2] == 0


def test_query_usages_and_api_docs_are_navigation_surfaces(tmp_path, capsys):
    path = tmp_path / "handler.sem"
    path.write_text(ss.scaffold("handler-route"), encoding="utf-8")
    assert ss.main(["query", "usages", str(path), "--name", "healthHandler", "--json"]) == 0
    usages = _payload(capsys)
    assert any("route" in row for row in usages["results"])
    assert ss.main(["query", "api-docs", str(path), "--json"]) == 0
    docs = _payload(capsys)
    assert any(row.startswith("route GET /health") for row in docs["results"])


def test_http_drive_builds_requests_asserts_and_stops(tmp_path, capsys):
    if ss._find_c_compiler() is None:
        pytest.skip("no C compiler available for native webServer drive")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    path = tmp_path / "handler.sem"
    path.write_text(
        ss.scaffold("handler-route").replace("api port 8080", f"api port {port}"),
        encoding="utf-8",
    )
    assert ss.main([
        "http-drive", str(path), "--path", "/health",
        "--expect-status", "200", "--expect-body", "ok",
        "--timeout", "10", "--json",
    ]) == 0
    payload = _payload(capsys)
    assert payload["surface"] == "sem.httpDrive.v1"
    assert payload["ok"] is True
    assert payload["response"]["status"] == 200
    assert payload["checks"] and all(check["ok"] for check in payload["checks"])


def test_doctor_without_path_returns_env_health(capsys):
    assert ss.main(["doctor", "--json"]) == 0
    payload = _payload(capsys)
    assert payload["surface"] == "sem.doctor.v1"
    assert payload["status"] in ("env-only", "ok", "diagnostics")
    assert "env" in payload
    assert "cCompilerAvailable" in payload["env"]


def test_checkpoint_and_undo_restore_source_file(tmp_path, capsys):
    path = tmp_path / "prog.sem"
    original = ss.scaffold("console-program")
    path.write_text(original, encoding="utf-8")
    assert ss.main(["checkpoint", str(path), "--name", "before", "--json"]) == 0
    checkpoint = _payload(capsys)["checkpoint"]
    path.write_text(original.replace("edit me", "changed"), encoding="utf-8")
    assert "changed" in path.read_text(encoding="utf-8")
    assert ss.main(["undo", checkpoint, "--json"]) == 0
    payload = _payload(capsys)
    assert payload["surface"] == "sem.undo.v1"
    assert path.read_text(encoding="utf-8") == original


def test_brief_targets_and_diagnostic_next_commands(tmp_path, capsys):
    assert ss.main(["targets", "--brief", "--json"]) == 0
    targets = _payload(capsys)
    assert targets["surface"] == "sem.targets.v1"
    assert targets["brief"] is True
    assert targets["count"] == len(targets["targets"])

    path = tmp_path / "bad.sem"
    path.write_text(_bad_target_source(), encoding="utf-8")
    assert ss.main(["check", str(path), "--jobs", "4", "--json"]) == 1
    check = _payload(capsys)
    assert check["requestedJobs"] == 4
    assert check["parallelEligible"] is True
    assert check["diagnostics"][0]["nextCommands"]

    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    (workspace_root / "a.sem").write_text(ss.scaffold("console-program"), encoding="utf-8")
    (workspace_root / "b.sem").write_text(ss.scaffold("console-program"), encoding="utf-8")
    assert ss.main(["check", str(workspace_root), "--jobs", "2", "--json"]) == 0
    workspace = _payload(capsys)
    assert workspace["status"] == "workspace"
    assert workspace["executionMode"] == "parallel"
    assert workspace["workerCount"] == 2


def test_lint_fix_delegates_to_autofix_plan(tmp_path, capsys):
    src = tmp_path / "prog.sem"
    src.write_text(
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "MyErr is error\nDeadCase is errorCase\nDeadCase of MyErr\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let okc immutable ExitCode 0\nmain return okc\n",
        encoding="utf-8",
    )
    assert ss.main(["lint", str(src), "--fix", "--json"]) == 0
    plan = _payload(capsys)
    assert plan["surface"] == "sem.fixPlan.v1"
    assert plan["autofixAll"] is True
    assert plan["nextCommands"]
