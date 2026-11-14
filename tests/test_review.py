"""Regression tests for the adversarial review (D-108, D-109): findings that are about tools and the runtime rather
than the checker (those are conformance checks in tests/suite/conformance.py)."""
from __future__ import annotations

import os
import shutil
import sys

import pytest

SUITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "suite")
sys.path.insert(0, SUITE)

import caselib  # noqa: E402
import conformance  # noqa: E402
from refined.native import find_cc  # noqa: E402

EXAMPLES = os.path.join(caselib.ROOT, "docs", "refined-examples")


def _edit(path: str, old: str, new: str) -> None:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    assert text.count(old) == 1, old
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text.replace(old, new))


@pytest.mark.parametrize("row", ['warehouse allows  read fs.files "*"', 'warehouse allows read fs.files "*" # see review',
                                 'warehouse allows\tread fs.files "*"'])
def test_approval_reads_rows_as_the_compiler_does(tmp_path, row):
    """13 Capability escalation prevention: authority widened in build.sem with spacing or a comment the lexer
    accepts is still authority nobody approved (D-109)."""
    project = str(tmp_path / "warehouse")
    shutil.copytree(os.path.join(EXAMPLES, "warehouse"), project)
    _edit(os.path.join(project, "build.sem"), 'warehouse allows read fs.files "warehouse-*"', row)
    _edit(os.path.join(project, "warehouse.sem"), 'reportFiles grants read fs.files "warehouse-*"',
          'reportFiles grants read fs.files "*"')
    assert not caselib.diagnostics(project)
    proc = caselib.refined("run", project, "--no-cache", cwd=project)
    assert proc.returncode == 3 and 'allows read fs.files "*"' in proc.stderr, (proc.returncode, proc.stderr)


def test_run_one_test_is_approved_and_checks_its_names(tmp_path):
    """20 Test runner: the per-test runner needs approved authority like `test`, and an unknown test is an error,
    not a crash (D-109)."""
    project = str(tmp_path / "warehouse")
    shutil.copytree(os.path.join(EXAMPLES, "warehouse"), project)
    proc = caselib.refined("run-one-test", project, "pricing.noSuchTest", cwd=project)
    assert proc.returncode == 2 and "Traceback" not in proc.stderr, proc.stderr
    proc = caselib.refined("run-one-test", project, "nowhere.fullPriceTest", cwd=project)
    assert proc.returncode == 2 and "Traceback" not in proc.stderr, proc.stderr
    os.remove(os.path.join(project, "authority.approved"))
    proc = caselib.refined("run-one-test", project, "pricing.fullPriceTest", cwd=project)
    assert proc.returncode == 3, (proc.returncode, proc.stdout, proc.stderr)


def test_cache_sees_a_required_package_outside_the_project(tmp_path):
    """23 Build caching: a change in a required package outside the project's directory is not hidden by the
    cache (D-109)."""
    source = os.path.join(caselib.PROGRAMS, "09-modules", "package")
    app, kit = str(tmp_path / "app"), str(tmp_path / "geometryKit")
    shutil.copytree(source, app, ignore=shutil.ignore_patterns("packages"))
    shutil.copytree(os.path.join(source, "packages", "geometryKit"), kit)
    _edit(os.path.join(app, "build.sem"), '"packages/geometryKit"', '"../geometryKit"')
    caselib.approve(app)
    first = caselib.refined("run", app, cwd=app)
    assert first.returncode == 0, first.stderr
    _edit(os.path.join(kit, "area.sem"), "multiply invokes math.multiplyInt64", "multiply invokes math.addInt64")
    second = caselib.refined("run", app, cwd=app)
    fresh = caselib.refined("run", app, "--no-cache", cwd=app)
    assert second.stdout == fresh.stdout and second.stdout != first.stdout, (first.stdout, second.stdout)


def _hard_linked_cleanups(tmp_path) -> str:
    project = str(tmp_path / "cleanups")
    shutil.copytree(conformance.BASES["cleanups"], project)
    first = os.path.join(project, "cleanup-first.txt")
    with open(first, "w") as fh:
        fh.write("")
    try:
        os.link(first, os.path.join(project, "cleanup-second.txt"))
    except (OSError, NotImplementedError):
        pytest.skip("this file system has no hard links")
    return project


def test_hard_link_is_the_same_file(tmp_path):
    """12 File locking, 7 Ownership: a file open for writing cannot be opened again through a hard link, which
    `realpath` cannot see through; the file's identity is checked once it is open (D-109)."""
    project = _hard_linked_cleanups(tmp_path)
    proc = caselib.refined("run", project, "--no-cache", cwd=project)
    assert proc.returncode == 1 and proc.stdout.splitlines() == ["closing first"], (proc.stdout, proc.stderr)


def test_hard_link_is_the_same_file_in_an_executable(tmp_path):
    """The same rule in a standalone executable (D-109)."""
    if find_cc() is None:
        pytest.skip("no C compiler")
    project = _hard_linked_cleanups(tmp_path)
    exe = os.path.join(project, "cleanups.exe")
    built = caselib.refined("build", project, "--kind", "executable", "--output", exe, cwd=project)
    assert built.returncode == 0, built.stdout + built.stderr
    import subprocess
    proc = subprocess.run([exe], capture_output=True, text=True, cwd=project, timeout=60)
    assert proc.returncode == 1 and proc.stdout.splitlines() == ["closing first"], (proc.stdout, proc.stderr)
