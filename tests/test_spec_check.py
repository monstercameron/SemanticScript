#!/usr/bin/env python3
"""SPEC executable-docs drift gate."""
import importlib
import json
from pathlib import Path

ss = importlib.import_module("semanticscript")


def _payload(capsys):
    return json.loads(capsys.readouterr().out)


def test_spec_check_current_process_runs_advertised_surfaces(capsys):
    assert ss.main(["spec-check", "--json"]) == 0
    payload = _payload(capsys)
    assert payload["surface"] == "sem.specCheck.v1"
    assert payload["ok"] is True
    assert payload["status"] == "ok"
    assert payload["runner"] == "current-process"
    assert payload["passed"] == payload["caseCount"]
    ids = {case["id"] for case in payload["results"]}
    assert {"synth-json", "verify-json", "run-json"} <= ids


def test_spec_check_is_mcp_discoverable_and_callable():
    tools = ss.mcp_handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert any(tool["name"] == "spec_check" for tool in tools["result"]["tools"])
    resp = ss.mcp_handle({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "spec_check", "arguments": {}},
    })
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["surface"] == "sem.specCheck.v1"
    assert payload["ok"] is True
    assert payload["passed"] == payload["caseCount"]


def test_agent_docs_and_toolchain_skill_do_not_advertise_stale_mcp_counts(capsys):
    assert ss.main(["agent-docs", "--json"]) == 0
    docs = _payload(capsys)["rules"]
    assert "synth" in docs
    assert "sem-edit" in docs
    assert "spec-check" in docs
    assert "improve" in docs
    assert "verify --adversarial" in docs
    assert "tools/list" in docs
    assert "22 tools" not in docs

    assert ss.main(["skills", "eav-toolchain", "--json"]) == 0
    skill = _payload(capsys)["skills"][0]["body"]
    assert "synth" in skill
    assert "sem-edit" in skill
    assert "spec-check" in skill
    assert "improve" in skill
    assert "verify --adversarial" in skill
    assert "tools/list" in skill
    assert "22 tools" not in skill


def test_spec2_ahead_of_impl_features_are_labeled_or_current():
    doc = (Path(__file__).resolve().parents[1] / "docs" / "LANGUAGE.md").read_text(
        encoding="utf-8")
    normalized = " ".join(doc.split())
    assert "The `sem test --lane` surface described in §28.7 is shipped" in normalized
    assert "The `--lane` flag is **proposed**" not in doc
    assert "project test composition parses `.test.sem` fragments" in normalized
    assert "bare-name calls from a test to sibling operations are implemented" in normalized
    assert "initialized `let` rows are not fully order-independent" in normalized
    assert "`let` initializer may only name bindings already in scope" in normalized
    assert "`sem docs --get <target>`" in normalized
    assert "external/not-yet distribution artifact" in normalized
