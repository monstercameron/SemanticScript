"""D-112: a module's test file may declare operations its tests share. A helper states `invariant none`, is never
exported, and only tests and other helpers call it."""
from __future__ import annotations

import os
import shutil
import sys

SUITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "suite")
sys.path.insert(0, SUITE)

import caselib  # noqa: E402

WAREHOUSE = os.path.join(caselib.ROOT, "docs", "refined-examples", "warehouse")

HELPER = '''
doubled is operation
doubled purpose "Twice a number, for tests that compare a doubled charge"
doubled invariant {invariant}
doubled typeParameter none
doubled input value Int64 copied
doubled output Int64
doubled outputOwnedBy none
doubled raises none
doubled effect none
doubled uses none
doubled memoryHeap false
doubled async false
doubled maxRecursion none
doubled label begin loopKind none
doubled label begin within none
doubled let none
doubled at begin do addItself
doubled at begin return ok twice

addItself is call
addItself in doubled
addItself invokes math.addInt64
addItself argument left Int64 value copy
addItself argument right Int64 value copy
addItself result twice Int64
addItself ownedBy none
addItself cleanedBy none
addItself borrows none
addItself catch none
addItself suppresses none
'''

USE_IN_TEST = '''
doubleCharge is call
doubleCharge in fullPriceTest
doubleCharge invokes doubled
doubleCharge argument value Int64 charged copy
doubleCharge result doubledCharge Int64
doubleCharge ownedBy none
doubleCharge cleanedBy none
doubleCharge borrows none
doubleCharge catch none
doubleCharge suppresses none

expectDoubled is call
expectDoubled in fullPriceTest
expectDoubled invokes test.assertEqualInt64
expectDoubled argument expected Int64 {expected} copy
expectDoubled argument actual Int64 doubledCharge copy
expectDoubled result none
expectDoubled ownedBy none
expectDoubled cleanedBy none
expectDoubled borrows none
expectDoubled catch none
expectDoubled suppresses none
'''


def _edit(path: str, old: str, new: str) -> None:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    assert text.count(old) == 1, old
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text.replace(old, new))


def _project(tmp_path, invariant: str = "none", expected: str = "twice") -> str:
    project = str(tmp_path / "warehouse")
    shutil.copytree(WAREHOUSE, project)
    tests = os.path.join(project, "pricing.test.sem")
    _edit(tests, "fullPriceTest let amount Int64 1234 immutable\n",
          "fullPriceTest let amount Int64 1234 immutable\nfullPriceTest let twice Int64 2468 immutable\n"
          "fullPriceTest let thrice Int64 3702 immutable\n")
    _edit(tests, "fullPriceTest at begin do expectSame\n",
          "fullPriceTest at begin do expectSame\nfullPriceTest at begin do doubleCharge\n"
          "fullPriceTest at begin do expectDoubled\n")
    with open(tests, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(HELPER.format(invariant=invariant) + USE_IN_TEST.format(expected=expected))
    return project


def _codes(project: str) -> list[str]:
    return sorted({d.split(": ")[1].split()[0] for d in caselib.diagnostics(project)})


def test_a_helper_in_the_test_file_is_shared_by_tests(tmp_path):
    project = _project(tmp_path)
    assert not caselib.diagnostics(project)
    proc = caselib.refined("test", project, cwd=project)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    ran = caselib.refined("run", project, "--no-cache", cwd=project)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    failing = _project(tmp_path / "failing", expected="thrice")
    proc = caselib.refined("test", failing, cwd=failing)
    assert proc.returncode != 0 and "fullPriceTest" in proc.stdout + proc.stderr, proc.stdout + proc.stderr


def test_a_helper_states_invariant_none(tmp_path):
    project = _project(tmp_path, invariant='doubles "Returns twice its input"')
    assert "R604" in _codes(project)


def test_a_helper_is_not_called_by_the_module(tmp_path):
    project = _project(tmp_path)
    _edit(os.path.join(project, "pricing.sem"), "fullPrice at begin return ok cents\n",
          "fullPrice at begin do sneak\nfullPrice at begin return ok cents\n")
    with open(os.path.join(project, "pricing.sem"), "a", encoding="utf-8", newline="\n") as fh:
        fh.write("\nsneak is call\nsneak in fullPrice\nsneak invokes doubled\nsneak argument value Int64 cents copy\n"
                 "sneak result sneaked Int64\nsneak ownedBy none\nsneak cleanedBy none\nsneak borrows none\n"
                 "sneak catch none\nsneak suppresses none\n")
    diags = caselib.diagnostics(project)
    assert any("R402" in d and "test helper" in d for d in diags), diags


def test_a_helper_is_never_exported(tmp_path):
    project = _project(tmp_path)
    _edit(os.path.join(project, "pricing.sem"), "pricing exports listTotal\n",
          "pricing exports listTotal\npricing exports doubled\n")
    diags = caselib.diagnostics(project)
    assert any("R402" in d and "never exported" in d for d in diags), diags
