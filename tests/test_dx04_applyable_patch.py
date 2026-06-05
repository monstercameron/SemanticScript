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


def test_fix_replaces_unused_call_out_with_discards(tmp_path, capsys):
    src = tmp_path / "unused-out.sem"
    src.write_text(_HEAD + (
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let okc immutable ExitCode 0\nmain let one immutable Int64 1\n"
        "main let two immutable Int64 2\nmain do sumCall\nmain return okc\n"
        "sumCall is call\nsumCall in main\nsumCall invokes math.addInt64\n"
        "sumCall arg left Int64 one\nsumCall arg right Int64 two\n"
        "sumCall out total Int64\n"
    ), encoding="utf-8")

    plan = _fix(src, capsys)
    assert plan["planUsable"] is True
    assert any(e["op"] == "replaceRow" and e["code"] == "SS0807" for e in plan["edits"])

    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    applied = _patch(plan_file, "--apply", capsys)
    assert applied["status"] == "applied"
    text = src.read_text(encoding="utf-8")
    assert "sumCall out total Int64" not in text
    assert 'sumCall discards "unused result explicitly discarded by fix plan"' in text
    ss.main(["check", str(src), "--strict", "--json"])
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_fix_renames_unambiguous_builtin_arg_slots(tmp_path, capsys):
    src = tmp_path / "bad-slots.sem"
    src.write_text(_HEAD + (
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let leftValue immutable Int64 84\n"
        "main let rightValue immutable Int64 2\nmain do divCall\nmain return quotient\n"
        "divCall is call\ndivCall in main\ndivCall invokes math.divideInt64\n"
        "divCall arg lhs Int64 leftValue\n"
        "divCall arg rhs Int64 rightValue\n"
        "divCall out quotient Int64\n"
    ), encoding="utf-8")

    plan = _fix(src, capsys)
    assert plan["planUsable"] is True
    slot_edits = [e for e in plan["edits"] if e["op"] == "replaceRow" and e["code"] == "SS1201"]
    assert {e["new"].split()[2] for e in slot_edits} == {"left", "right"}

    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    applied = _patch(plan_file, "--apply", capsys)
    assert applied["status"] == "applied"
    text = src.read_text(encoding="utf-8")
    assert "divCall arg lhs" not in text
    assert "divCall arg rhs" not in text
    assert "divCall arg left Int64 leftValue" in text
    assert "divCall arg right Int64 rightValue" in text
    ss.main(["check", str(src), "--strict", "--json"])
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
