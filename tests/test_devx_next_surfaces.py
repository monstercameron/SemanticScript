#!/usr/bin/env python3
"""DEVX-NEXT first-class surfaces."""
import importlib
import json

ss = importlib.import_module("semanticscript")


def _payload(capsys):
    return json.loads(capsys.readouterr().out)


def test_synth_target_generates_signature_typed_rows(capsys):
    assert ss.main([
        "synth",
        "--target", "math.addInt64",
        "--operation", "add",
        "--call", "addCall",
        "--json",
    ]) == 0
    payload = _payload(capsys)
    assert payload["surface"] == "sem.synth.v1"
    assert payload["target"] == "math.addInt64"
    assert "addCall arg left Int64 <left>" in payload["rows"]
    assert "addCall arg right Int64 <right>" in payload["rows"]
    assert "addCall out addCallResult Int64" in payload["rows"]
    assert payload["signature"]["target"] == "math.addInt64"


def test_synth_intent_returns_ranked_candidates(capsys):
    assert ss.main(["synth", "--intent", "crud endpoint route store test", "--json"]) == 0
    payload = _payload(capsys)
    assert payload["surface"] == "sem.synth.v1"
    assert payload["candidates"]
    assert any(c["kind"] == "scaffold" and c["name"] == "crud-endpoint"
               for c in payload["candidates"])


def test_synth_is_mcp_discoverable_and_callable():
    tools = ss.mcp_handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert any(tool["name"] == "synth" for tool in tools["result"]["tools"])
    resp = ss.mcp_handle({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "synth",
            "arguments": {"target": "log.logInfo", "operation": "main"},
        },
    })
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["surface"] == "sem.synth.v1"
    assert any(row.startswith("logInfoCall arg messageText String")
               for row in payload["rows"])


def test_diff_json_reports_effect_and_authority_delta(tmp_path, capsys):
    old = tmp_path / "old.sem"
    new = tmp_path / "new.sem"
    old.write_text(ss.scaffold("console-program"), encoding="utf-8")
    new.write_text(
        ss.scaffold("console-program").replace(
            "main return okCode",
            "main effect read audit.log\nmain uses auditReader\nmain return okCode",
        ) + "auditReader is capability\nauditReader grants read audit.log\n",
        encoding="utf-8",
    )
    assert ss.main(["diff", str(old), str(new), "--json"]) == 0
    payload = _payload(capsys)
    assert payload["surface"] == "sem.diff.v1"
    assert any(c["kind"] == "effect-added" and c["entity"] == "main"
               for c in payload["changes"])
    assert any(c["kind"] == "authority-use-added" and c["entity"] == "main"
               for c in payload["changes"])


def test_devx_mock_authority_and_server_perf_modes(tmp_path, capsys):
    console = tmp_path / "console.sem"
    console.write_text(ss.scaffold("console-program"), encoding="utf-8")
    assert ss.main(["devx", str(console), "--mode", "mock", "--json"]) == 0
    mock = _payload(capsys)
    assert mock["surface"] == "sem.devx.v1"
    assert mock["seams"]
    assert mock["failureInjection"] == "by capability/effect seam"

    assert ss.main(["devx", str(console), "--mode", "authority", "--json"]) == 0
    authority = _payload(capsys)
    assert authority["surface"] == "sem.devx.v1"
    assert authority["operations"]

    server = tmp_path / "server.sem"
    server.write_text(ss.scaffold("handler-route"), encoding="utf-8")
    assert ss.main(["devx", str(server), "--mode", "perf", "--json"]) == 0
    perf = _payload(capsys)
    assert perf["surface"] == "sem.devx.v1"
    assert perf["lane"] == "serve-probe-stop"
    assert ["bench", str(server), "--probe-server", "--json"] in perf["commands"]
    assert ["http-drive", str(server), "--json"] in perf["commands"]


def test_verify_adversarial_lane_blocks_default_green_warnings(tmp_path, capsys):
    clean = tmp_path / "clean.sem"
    clean.write_text(ss.scaffold("console-program"), encoding="utf-8")
    assert ss.main(["verify", str(clean), "--adversarial", "--json"]) == 0
    payload = _payload(capsys)
    assert payload["surface"] == "sem.verify.v1"
    assert payload["lanes"]["adversarial"]["status"] == "pass"
    assert payload["lanes"]["adversarial"]["edgeProbePlan"]
    assert "failurePathChecks" in payload["lanes"]["adversarial"]

    risky = tmp_path / "risky.sem"
    risky.write_text(
        ss.scaffold("console-program").replace(
            'main invariant "Always returns 0"\n', ""),
        encoding="utf-8",
    )
    assert ss.main(["verify", str(risky), "--json"]) == 0
    default_payload = _payload(capsys)
    assert default_payload["lanes"]["check"]["status"] == "ok-with-warnings"
    assert default_payload["lanes"]["adversarial"]["status"] == "not-run"

    assert ss.main(["verify", str(risky), "--adversarial", "--json"]) == 1
    blocked = _payload(capsys)
    assert blocked["status"] == "blocked"
    assert blocked["lanes"]["adversarial"]["status"] == "blocked"
    assert blocked["lanes"]["adversarial"]["edgeProbePlan"]
    assert any(d["code"] == "MD1012"
               for d in blocked["lanes"]["adversarial"]["blockers"])

    resp = ss.mcp_handle({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "verify",
            "arguments": {"path": str(clean), "adversarial": True},
        },
    })
    mcp_payload = json.loads(resp["result"]["content"][0]["text"])
    assert mcp_payload["surface"] == "sem.verify.v1"
    assert mcp_payload["lanes"]["adversarial"]["status"] == "pass"


def test_improve_plans_and_applies_canonical_metadata(tmp_path, capsys):
    src = tmp_path / "needs_improve.sem"
    src.write_text(
        ss.scaffold("console-program").replace(
            'main invariant "Always returns 0"\n', ""),
        encoding="utf-8",
    )
    assert ss.main(["improve", str(src), "--json"]) == 0
    plan = _payload(capsys)
    assert plan["surface"] == "sem.improve.v1"
    assert plan["applyable"] is True
    assert any("main invariant" in edit["row"] for edit in plan["canonicalEdits"])

    assert ss.main(["improve", str(src), "--apply", "--json"]) == 0
    applied = _payload(capsys)
    assert applied["surface"] == "sem.improve.v1"
    assert applied["status"] == "applied"
    assert applied["applied"] >= 1
    assert "main invariant" in src.read_text(encoding="utf-8")

    assert ss.main(["check", str(src), "--strict", "--json"]) == 0
    checked = _payload(capsys)
    assert checked["status"] == "ok"

    tools = ss.mcp_handle({"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
    assert any(tool["name"] == "improve" for tool in tools["result"]["tools"])
    resp = ss.mcp_handle({
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {"name": "improve", "arguments": {"path": str(src)}},
    })
    mcp_payload = json.loads(resp["result"]["content"][0]["text"])
    assert mcp_payload["surface"] == "sem.improve.v1"


def test_sem_edit_applies_structured_call_rows(tmp_path, capsys):
    src = tmp_path / "editable.sem"
    src.write_text(
        _checked_contract_source("main return okCode\n"),
        encoding="utf-8",
    )
    moves = [
        {"op": "addLet", "operation": "main", "name": "leftVal",
         "type": "Int64", "value": "2"},
        {"op": "addLet", "operation": "main", "name": "rightVal",
         "type": "Int64", "value": "3"},
        {"op": "addCall", "operation": "main", "target": "math.addInt64",
         "call": "addNumbers",
         "args": {"left": "leftVal", "right": "rightVal"},
         "out": "sum"},
    ]

    assert ss.main(["sem-edit", str(src), "--edit", json.dumps(moves),
                    "--apply", "--json"]) == 0
    payload = _payload(capsys)
    assert payload["surface"] == "sem.semEdit.v1"
    assert payload["status"] == "applied"
    assert payload["moveCount"] == 3
    text = src.read_text(encoding="utf-8")
    assert "addNumbers invokes math.addInt64" in text
    assert "addNumbers arg left Int64 leftVal" in text
    assert text.index("main do addNumbers") < text.index("main return okCode")


def test_sem_edit_rejects_missing_signature_slot(tmp_path, capsys):
    src = tmp_path / "bad_edit.sem"
    src.write_text(
        _checked_contract_source(
            "main let leftVal immutable Int64 2\n"
            "main return okCode\n"),
        encoding="utf-8",
    )
    move = {"op": "addCall", "operation": "main", "target": "math.addInt64",
            "call": "addNumbers", "args": {"left": "leftVal"}, "out": "sum"}

    assert ss.main(["sem-edit", str(src), "--edit", json.dumps(move), "--json"]) == 1
    payload = _payload(capsys)
    assert payload["surface"] == "sem.semEdit.v1"
    assert payload["status"] == "invalid-move"
    assert "missing required arg slot" in payload["diagnostics"][0]["message"]


def test_sem_edit_is_mcp_discoverable_and_accepts_object_edit(tmp_path):
    src = tmp_path / "mcp_edit.sem"
    src.write_text(
        _checked_contract_source("main return okCode\n"),
        encoding="utf-8",
    )
    tools = ss.mcp_handle({"jsonrpc": "2.0", "id": 6, "method": "tools/list"})
    sem_edit = next(tool for tool in tools["result"]["tools"]
                    if tool["name"] == "sem_edit")
    assert sem_edit["inputSchema"]["properties"]["edit"]["oneOf"]
    resp = ss.mcp_handle({
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {
            "name": "sem_edit",
            "arguments": {
                "path": str(src),
                "edit": {"op": "addLet", "operation": "main",
                         "name": "mcpTemp", "type": "Int64", "value": "4"},
            },
        },
    })
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["surface"] == "sem.semEdit.v1"
    assert payload["status"] == "planned"
    assert "main let mcpTemp immutable Int64 4" in payload["canonical"]


def test_repl_reports_live_signature_and_native_boundary(tmp_path, capsys):
    src = tmp_path / "repl.sem"
    src.write_text(
        _checked_contract_source("main return okCode\n"),
        encoding="utf-8",
    )

    assert ss.main(["repl", str(src), "--target", "sqlite.openDatabase",
                    "--json"]) == 0
    payload = _payload(capsys)
    assert payload["surface"] == "sem.repl.v1"
    assert payload["signatureLive"] is True
    assert payload["signature"]["target"] == "sqlite.openDatabase"
    assert payload["signature"]["status"] == "native"
    assert payload["executionLanes"]["jit"]["status"] == "available"
    native_targets = payload["executionLanes"]["nativeBuild"]["coversTargets"]
    assert any(t["target"] == "sqlite.openDatabase" for t in native_targets)
    assert payload["callSkeleton"]["signature"]["target"] == "sqlite.openDatabase"
    assert any(row.startswith("openDatabaseCall arg path String")
               for row in payload["callSkeleton"]["rows"])


def test_repl_run_executes_console_session(tmp_path, capsys):
    src = tmp_path / "run_repl.sem"
    src.write_text(
        _checked_contract_source("main return okCode\n"),
        encoding="utf-8",
    )

    assert ss.main(["repl", str(src), "--run", "--json"]) == 0
    payload = _payload(capsys)
    assert payload["surface"] == "sem.repl.v1"
    assert payload["run"]["exitCode"] == 0
    assert payload["run"]["status"] == "ok"


def test_repl_is_mcp_discoverable_and_callable(tmp_path):
    src = tmp_path / "mcp_repl.sem"
    src.write_text(
        _checked_contract_source("main return okCode\n"),
        encoding="utf-8",
    )
    tools = ss.mcp_handle({"jsonrpc": "2.0", "id": 8, "method": "tools/list"})
    repl = next(tool for tool in tools["result"]["tools"]
                if tool["name"] == "repl")
    assert repl["inputSchema"]["properties"]["run"]["type"] == "boolean"
    assert repl["inputSchema"]["properties"]["native"]["type"] == "boolean"
    resp = ss.mcp_handle({
        "jsonrpc": "2.0",
        "id": 9,
        "method": "tools/call",
        "params": {
            "name": "repl",
            "arguments": {"path": str(src), "target": "math.addInt64"},
        },
    })
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["surface"] == "sem.repl.v1"
    assert payload["signature"]["target"] == "math.addInt64"


def _checked_contract_source(extra_rows: str) -> str:
    return (
        "P is project\nP module m\nP target console\nP entry main\n"
        'P purpose "checked contract test"\nP invariant "entry is checked"\n'
        "m is module\nm path checked.contract\nm exports main\n"
        'm purpose "checked contract module"\nm invariant "module is checked"\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain memory heap no\n"
        'main purpose "entry"\nmain invariant "Always returns 0"\n'
        "main let okCode immutable ExitCode 0\n"
        f"{extra_rows}"
    )


def test_checked_contracts_prove_guarantee_rows(tmp_path, capsys):
    src = tmp_path / "proved.sem"
    src.write_text(
        _checked_contract_source(
            'main guarantee "returns ExitCode 0"\n'
            "main return okCode\n"),
        encoding="utf-8",
    )

    assert ss.main(["check", str(src), "--json"]) == 0
    checked = _payload(capsys)
    assert checked["status"] == "ok"

    assert ss.main(["devx", str(src), "--mode", "contracts", "--json"]) == 0
    contracts = _payload(capsys)
    claims = contracts["checkedClaims"]
    assert any(c["predicate"] == "guarantee"
               and c["claim"] == "returnsZero"
               and c["status"] == "proved"
               for c in claims)


def test_checked_contracts_reject_contradicted_guarantee(tmp_path, capsys):
    src = tmp_path / "contradicted.sem"
    src.write_text(
        _checked_contract_source(
            'main guarantee "returns 0"\n'
            "main let failCode immutable ExitCode 1\n"
            "main return failCode\n"),
        encoding="utf-8",
    )

    assert ss.main(["check", str(src), "--json"]) == 1
    payload = _payload(capsys)
    assert any(d["code"] == "SS1880" for d in payload["diagnostics"])


def test_checked_contracts_surface_contradicted_no_network(tmp_path, capsys):
    src = tmp_path / "network.sem"
    src.write_text(
        _checked_contract_source(
            'main guarantee "performs no network"\n'
            "main effect write http.response\n"
            "main uses responder\n"
            "main return okCode\n"
            "responder is capability\n"
            "responder grants write http.response\n"),
        encoding="utf-8",
    )

    assert ss.main(["devx", str(src), "--mode", "contracts", "--json"]) == 0
    contracts = _payload(capsys)
    assert any(c["claim"] == "noNetwork" and c["status"] == "contradicted"
               for c in contracts["checkedClaims"])
    assert any(d["code"] == "SS1880" for d in contracts["diagnostics"])
