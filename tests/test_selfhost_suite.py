"""The self-hosted compiler against the whole test suite (docs/self-hosting-plan.md, criteria 4 and 5).

stage0, built once per session as a standalone executable (conftest.stage0_native), is given every single-file suite
program that `refined run` runs, as the project the suite makes of it. It either refuses the program (outside its
subset: exit 1, a located message, no C written) or builds it, and then the executable it built must print what
`refined run` prints and exit with the same code. A program stage0 accepts and gets wrong fails this test; a program
it refuses only counts against coverage, which is reported and may not fall below the floor recorded here as the
subset grows. The suite's project directories (programs of several modules) are swept the same way, with no floor."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

SUITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "suite")
sys.path.insert(0, SUITE)

import caselib  # noqa: E402
from conftest import EXE, c_compiler  # noqa: E402

# what stage0 passes the C compiler after the C file: the runtime the C is linked with, and on Windows the library
# the runtime needs for the command line
LINK = [os.path.join(caselib.ROOT, "semanticscript", "compiler", "refined", "native_runtime.c")] + \
    (["-lshell32"] if os.name == "nt" else [])
# the number of single-file suite programs the self-hosted compiler builds correctly; raise it as the subset grows
COVERAGE_FLOOR = 14
_LOCATED = re.compile(r"^[^\n:]+\.sem:\d+:\d+: .+\n$")

CC = c_compiler()


def _cases(directories: bool) -> list:
    return [c for c in caselib.discover()
            if c.mode == "run" and os.path.isdir(c.path) == directories and not c.args and not c.stdin
            and not c.missing_tools() and not os.path.exists(c.path[:-4] + ".test.sem")]


def _sweep(stage0: str, cases: list, workdir: str) -> list:
    def one(case):
        project = caselib.materialize(case, os.path.join(workdir, case.name.replace("/", "_")))
        proc = subprocess.run([stage0, ".", "build/program", CC, *LINK], capture_output=True, text=True, cwd=project,
                              timeout=600)
        if proc.returncode == 1:
            ok = proc.stdout == "" and _LOCATED.match(proc.stderr) is not None \
                and not os.path.exists(os.path.join(project, "build", "program.c"))
            return case.name, "refused", None if ok else f"bad refusal: {proc.stderr!r}"
        if proc.returncode != 0:
            return case.name, "error", f"stage0 exit {proc.returncode}: {proc.stdout}{proc.stderr}"
        ran = subprocess.run([os.path.join(project, "build", "program" + EXE)], capture_output=True, text=True,
                             timeout=120, cwd=project)
        reference = caselib.run_case(case, project)
        if (ran.stdout, ran.returncode) != (reference.stdout, reference.returncode):
            return case.name, "wrong", (f"built: {ran.returncode} {ran.stdout!r} {ran.stderr[-300:]!r}; "
                                        f"refined run: {reference.returncode} {reference.stdout!r}")
        return case.name, "built", None

    with ThreadPoolExecutor(6) as pool:
        return list(pool.map(one, cases))


@pytest.mark.skipif(CC is None, reason="no C compiler named cc, gcc, or clang on PATH")
def test_selfhosted_compiler_on_the_suite(stage0_native, tmp_path):
    cases = _cases(False)
    results = _sweep(stage0_native, cases, str(tmp_path / "cases"))
    built_ok = [r for r in results if r[1] == "built"]
    problems = [r for r in results if r[2] is not None]
    print(f"\nself-hosted compiler: {len(built_ok)} of {len(cases)} suite programs built and matched; "
          f"{sum(r[1] == 'refused' for r in results)} refused")
    for name, _, why in built_ok:
        print("  built:", name)
    assert not problems, "\n".join(f"{n}: {why}" for n, _, why in problems)
    assert len(built_ok) >= COVERAGE_FLOOR


@pytest.mark.skipif(CC is None, reason="no C compiler named cc, gcc, or clang on PATH")
def test_selfhosted_compiler_on_the_suite_projects(stage0_native, tmp_path):
    """The suite's programs of several modules: each is built correctly or refused with a located message."""
    cases = _cases(True)
    results = _sweep(stage0_native, cases, str(tmp_path / "projects"))
    problems = [r for r in results if r[2] is not None]
    print(f"\nself-hosted compiler: {sum(r[1] == 'built' for r in results)} of {len(cases)} suite projects built")
    assert not problems, "\n".join(f"{n}: {why}" for n, _, why in problems)
