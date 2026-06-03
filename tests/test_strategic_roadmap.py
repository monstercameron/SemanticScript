#!/usr/bin/env python3
"""S1-S5/G1/G3/G4 roadmap regressions.

These tests pin the agent-facing contracts that remove the old dead ends:
concrete signed targets, check-time rejection for broad unmodeled prefixes,
tool-reachable subsystem recipes, the verify one-shot, runnable composition
scaffolds, and fmt -w.
"""
import importlib
import json

ss = importlib.import_module("semanticscript")


def _read_json(capsys):
    return json.loads(capsys.readouterr().out)


def test_targets_catalog_is_concrete_signed_and_labeled(capsys):
    assert ss.main(["targets", "--json"]) == 0
    payload = _read_json(capsys)
    assert payload["surface"] == "sem.targets.v1"
    assert payload["version"] == "sem.targets.v1"
    assert payload["targets"]

    row_by_target = {row["target"]: row for row in payload["targets"]}
    for family, targets in payload["families"].items():
        assert "<" not in " ".join(targets)
        assert family in payload["familyStatus"]
        for target in targets:
            assert target in row_by_target
            assert ss._builtin_target_signature(target) is not None
            row = row_by_target[target]
            assert row["family"] == family
            assert row["maturity"] in ("proven", "experimental")
            assert "signature" in row


def test_docs_and_targets_signature_families_agree_for_catalog_families(capsys):
    for family in sorted(ss._target_catalog()["families"]):
        pattern = f"{family}.*"
        assert ss.main(["targets", "--signature", pattern, "--json"]) == 0
        target_payload = _read_json(capsys)
        assert target_payload["surface"] == "sem.targetSignatures.v1"

        assert ss.main(["docs", "examples/hello_world.sem", "--get", pattern, "--json"]) == 0
        docs_payload = _read_json(capsys)
        assert docs_payload["surface"] == "sem.docs.v1"
        assert docs_payload["entity"]["signatureCount"] == target_payload["count"]
        assert [s["target"] for s in docs_payload["entity"]["signatures"]] == [
            s["target"] for s in target_payload["signatures"]
        ]


def test_broad_builtin_prefix_without_signature_is_check_error():
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm exports main\nm purpose "p"\nm invariant "i"\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let ok immutable ExitCode 0\nmain do bogus\nmain return ok\n"
        "bogus is call\nbogus in main\nbogus invokes buffer.notARealTarget\n"
        'bogus discards "not a modeled builtin"\n'
    )
    errors = [d for d in ss.lint(ss.parse(src)) if d.severity == "error"]
    assert "SS1198" in {d.code for d in errors}


def test_subsystem_recipes_are_skill_and_search_reachable(capsys):
    assert ss.main(["skills", "--json"]) == 0
    skills_payload = _read_json(capsys)
    skill_names = {item["name"] for item in skills_payload["skills"]}
    for family in ss._target_catalog()["families"]:
        assert f"eav-subsystem-{family}" in skill_names

    assert ss.main(["search", "json output scaffold", "--source", "skill", "--json"]) == 0
    search_payload = _read_json(capsys)
    ids = {item["id"] for item in search_payload["matches"]}
    assert "eav-subsystem-json" in ids


def test_verify_one_shot_runs_check_tests_and_run(tmp_path, capsys):
    path = tmp_path / "hello.sem"
    path.write_text(ss.scaffold("console-program"), encoding="utf-8")
    assert ss.main(["verify", str(path), "--json"]) == 0
    payload = _read_json(capsys)
    assert payload["surface"] == "sem.verify.v1"
    assert payload["ok"] is True
    assert payload["lanes"]["check"]["status"] == "ok"
    assert payload["lanes"]["test"]["status"] == "skipped"
    assert payload["lanes"]["run"]["stdoutLines"] == ["edit me"]


def test_verify_watch_emits_bounded_snapshot(tmp_path, capsys):
    path = tmp_path / "hello.sem"
    path.write_text(ss.scaffold("console-program"), encoding="utf-8")
    assert ss.main([
        "verify", str(path), "--json", "--watch",
        "--watch-interval", "0.05", "--watch-count", "1",
    ]) == 0
    payload = _read_json(capsys)
    assert payload["surface"] == "sem.verify.v1"
    assert payload["watch"]["mode"] == "watch"
    assert payload["watch"]["sequence"] == 1
    assert payload["watch"]["fileCount"] == 1
    assert payload["lanes"]["run"]["stdoutLines"] == ["edit me"]


def test_project_parse_cache_reuses_unchanged_file_graph(tmp_path, monkeypatch):
    project = tmp_path / "app"
    src_dir = project / "src"
    src_dir.mkdir(parents=True)
    (project / "build.sem").write_text(
        "P is project\nP module m\nP target console\nP entry main\n",
        encoding="utf-8",
    )
    main_source = (
        'm is module\nm path a.b\nm exports main\nm purpose "p"\nm invariant "i"\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let ok immutable ExitCode 0\nmain return ok\n"
    )
    main_path = src_dir / "main.sem"
    main_path.write_text(main_source, encoding="utf-8")
    ss._PARSE_COMPACT_CACHE.clear()
    ss._PARSE_COMPACT_CACHE_ORDER.clear()

    real_parse = ss.parse
    calls = []

    def counted_parse(source):
        calls.append(source)
        return real_parse(source)

    monkeypatch.setattr(ss, "parse", counted_parse)
    _source, first = ss._load_program_for_path(str(project))
    _source, second = ss._load_program_for_path(str(project))
    assert len(calls) == 1
    assert first is not second

    first.entities["main"].kind = "mutated"
    _source, third = ss._load_program_for_path(str(project))
    assert third.entities["main"].kind == "operation"
    assert len(calls) == 1

    main_path.write_text(main_source.replace("ExitCode 0", "ExitCode 1"), encoding="utf-8")
    _source, changed = ss._load_program_for_path(str(project))
    assert changed.entities["main"].fact("let").payload[-1] == "1"
    assert len(calls) == 2


def test_verify_blocks_static_errors_before_runtime(tmp_path, capsys):
    path = tmp_path / "bad.sem"
    path.write_text(
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm exports main\nm purpose "p"\nm invariant "i"\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let ok immutable ExitCode 0\nmain do bogus\nmain return ok\n"
        "bogus is call\nbogus in main\nbogus invokes test.assertDefinitelyMissing\n"
        'bogus discards "not a modeled assertion"\n',
        encoding="utf-8",
    )
    assert ss.main(["verify", str(path), "--json"]) == 1
    payload = _read_json(capsys)
    assert payload["status"] == "blocked"
    assert payload["lanes"]["check"]["status"] == "lint-diagnostics"
    assert payload["lanes"]["run"]["status"] == "skipped"


def test_composition_scaffolds_are_runnable():
    expected = {
        "json-output": '{"answer":42}\n',
        "db-roundtrip": "---- 2 passed, 0 failed ----",
        "logged-op": "",
    }
    for pattern, marker in expected.items():
        out, err, code = ss._record_run_full(ss.scaffold(pattern))
        assert code == 0, (pattern, err)
        assert marker in out


def test_fmt_write_rewrites_file(tmp_path, capsys):
    source = ss.scaffold("console-program").rstrip("\n")
    path = tmp_path / "needs_fmt.sem"
    path.write_text(source, encoding="utf-8")

    assert ss.main(["fmt", str(path), "-w"]) == 0
    capsys.readouterr()

    expected = ss.format_program(ss.parse_compact(source))
    assert path.read_text(encoding="utf-8") == expected
