#!/usr/bin/env python3
"""DX-04: `fix --plan` emits an applyable patch for SS0803/SS0900 and `patch` applies it.

The repair loop never closed: `fix` plans were always `planUsable: false`
(advisory text only), so `patch` had nothing to apply. Now a diagnostic with a
deterministic, safe repair carries a machine-applicable edit:

  * SS0803 (error case declared but never used) -> remove the whole entity.
  * SS0900 over-declared `effect` -> remove that one `effect` row.

`patch` applies the content-addressed edits, re-validates before writing, and
fails closed on a stale plan (an edit that no longer matches the source).
"""
import importlib
import json

import pytest

ss = importlib.import_module("semanticscript")

_HEAD = (
    "P is project\nP module m\nP target console\nP entry main\n"
    'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
    "ExitCode is alias\nExitCode for Int32\n"
)
_DEAD_CASE = _HEAD + (
    "MyErr is error\nDeadCase is errorCase\nDeadCase of MyErr\n"
    "main is operation\nmain out ExitCode\nmain async no\n"
    'main purpose "p"\nmain invariant "i"\nmain let okc immutable ExitCode 0\nmain return okc\n'
)


def _fix(path, capsys):
    ss.main(["fix", str(path), "--plan", "--include-warnings", "--json"])
    return json.loads(capsys.readouterr().out)


def _patch(plan_path, flag, capsys):
    ss.main(["patch", str(plan_path), flag, "--json"])
    return json.loads(capsys.readouterr().out)


def test_fix_emits_applyable_edit_and_patch_closes_loop(tmp_path, capsys):
    src = tmp_path / "prog.sem"
    src.write_text(_DEAD_CASE, encoding="utf-8")
    plan = _fix(src, capsys)
    assert plan["planUsable"] is True
    assert plan["status"] == "applyable"
    assert {e["op"] for e in plan["edits"]} == {"removeEntity"}
    assert plan["edits"][0]["entity"] == "DeadCase"

    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    # dry-run does not modify the file
    dry = _patch(plan_file, "--dry-run", capsys)
    assert dry["status"] == "dry-run" and dry["ok"]
    assert "DeadCase" in src.read_text(encoding="utf-8")
    # apply removes the dead case and the result re-checks clean
    applied = _patch(plan_file, "--apply", capsys)
    assert applied["status"] == "applied" and applied["applied"] == 1
    assert "DeadCase" not in src.read_text(encoding="utf-8")
    ss.main(["check", str(src), "--strict", "--json"])
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_patch_fails_closed_on_stale_plan(tmp_path, capsys):
    src = tmp_path / "prog.sem"
    src.write_text(_DEAD_CASE, encoding="utf-8")
    plan = _fix(src, capsys)
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    # the source changed since `fix` — the dead case is already gone
    src.write_text(_HEAD + ("main is operation\nmain out ExitCode\nmain async no\n"
                            'main purpose "p"\nmain invariant "i"\n'
                            "main let okc immutable ExitCode 0\nmain return okc\n"),
                   encoding="utf-8")
    res = _patch(plan_file, "--apply", capsys)
    assert res["ok"] is False and res["status"] == "stale-plan"


def test_clean_program_has_no_applyable_edits(tmp_path, capsys):
    src = tmp_path / "ok.sem"
    src.write_text(_HEAD + ("main is operation\nmain out ExitCode\nmain async no\n"
                            'main purpose "p"\nmain invariant "i"\n'
                            "main let okc immutable ExitCode 0\nmain return okc\n"),
                   encoding="utf-8")
    plan = _fix(src, capsys)
    assert plan["planUsable"] is False
    assert plan["edits"] == []
