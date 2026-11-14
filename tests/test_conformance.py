"""Runs the conformance suite (tests/suite/conformance.py): every safety guarantee's checks, and the generated
docs/safety-guarantees.md."""
from __future__ import annotations

import os
import shutil
import sys

import pytest

SUITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "suite")
sys.path.insert(0, SUITE)

import caselib  # noqa: E402
import conformance  # noqa: E402
from mutations import MUTATIONS  # noqa: E402

CHECKS = [(g, c) for g in conformance.GUARANTEES for c in g.checks]


def _apply(tmp_path, check) -> str:
    project = str(tmp_path / check.base)
    shutil.copytree(conformance.BASES[check.base], project)
    for file, old, new in check.edits:
        path = os.path.join(project, file)
        with open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
        if old == "<append>":
            text = text.rstrip("\n") + "\n\n" + new.strip("\n") + "\n"
        else:
            assert text.count(old) == 1, f"{check.id}: expected exactly one {old[:60]!r}, found {text.count(old)}"
            text = text.replace(old, new)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    return project


@pytest.mark.parametrize("g,check", CHECKS, ids=[f"{g.key}/{c.id}" for g, c in CHECKS])
def test_conformance(g, check, tmp_path):
    project = _apply(tmp_path, check)
    diags = caselib.check_path(project).diagnostics
    if check.kind == "reject":
        got = sorted({d.code for d in diags})
        shown = "\n".join(d.format() for d in diags)
        assert got == sorted(set(check.codes)), f"{check.id}: codes {got}, expected {sorted(check.codes)}\n{shown}"
        own = [d for d in diags if d.code == check.codes[0]]
        assert any(check.detail in d.message for d in own), \
            f"{check.id}: no {check.codes[0]} diagnostic says {check.detail!r}\n{shown}"
        return
    assert not diags, "\n".join(d.format() for d in diags)
    proc = caselib.refined("run", project, "--no-cache", cwd=project)
    if check.lines:
        assert proc.stdout.splitlines() == list(check.lines), (proc.stdout, proc.stderr)
    if check.kind == "trap":
        assert proc.returncode == caselib.TRAP_EXIT_CODE and check.detail in proc.stderr, (proc.returncode, proc.stderr)
    else:
        assert proc.returncode == check.exit, (proc.returncode, proc.stderr)
        assert check.detail in proc.stdout.splitlines(), proc.stdout


def test_evidence_names_real_tests():
    mutation_ids = {m.id for m in MUTATIONS}
    case_names = {c.name for c in caselib.discover()}
    test_names = set()
    tests_dir = os.path.dirname(os.path.abspath(__file__))
    for f in os.listdir(tests_dir):
        if f.startswith("test_") and f.endswith(".py"):
            with open(os.path.join(tests_dir, f), encoding="utf-8") as fh:
                test_names |= {line.split("(")[0][4:] for line in fh if line.startswith("def test_")}
    missing = []
    for g in conformance.GUARANTEES:
        assert any(c.kind == "reject" for c in g.checks) or g.key in ("regions",), f"{g.key} has no rejection check"
        for e in g.evidence:
            kind, name = e.split(":", 1)
            pool = {"mutation": mutation_ids, "case": case_names, "test": test_names}[kind]
            if name not in pool:
                missing.append(e)
    assert not missing, f"evidence that names no test: {missing}"
    ids = [c.id for _g, c in CHECKS]
    assert len(ids) == len(set(ids)), "check ids are unique"


def test_safety_guarantees_doc_is_current():
    with open(conformance.DOC, encoding="utf-8") as fh:
        assert fh.read() == conformance.render(), "run `python tests/suite/conformance.py --write`"


def test_base_matches_the_example_syntax():
    """The frozen base checks clean, so every rejection above is caused by its edit alone."""
    for base in conformance.BASES.values():
        assert not caselib.check_path(base).diagnostics, base


def test_warehouse_example_runs_and_reports_both_failures(tmp_path):
    """The warehouse example (docs/refined-examples/warehouse), rebuilt on these guarantees: it prices the order in
    two tasks and reports; when a line is invalid both tasks fail, the second failure is reported on standard
    error, and the first decides the exit code."""
    example = os.path.join(caselib.ROOT, "docs", "refined-examples", "warehouse")
    good = str(tmp_path / "good")
    shutil.copytree(example, good)
    proc = caselib.refined("run", good, "--no-cache", cwd=good)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["3750", "3375", "list=3750 discounted=3375"]
    bad = str(tmp_path / "bad")
    shutil.copytree(example, bad)
    path = os.path.join(bad, "warehouse.sem")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text.replace("order cell gadget quantity 2", "order cell gadget quantity -2"))
    proc = caselib.refined("run", bad, "--no-cache", cwd=bad)
    assert proc.returncode == 2, (proc.stdout, proc.stderr)
    assert proc.stdout == "" and "the discount total failed too" in proc.stderr
