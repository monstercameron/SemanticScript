"""The self-hosted compiler against the whole test suite (docs/self-hosting-plan.md, criteria 4 and 5).

stage0, built as a standalone executable, is given every single-file suite program that `refined run` runs. It
either refuses the program (outside its subset: exit 1, a located message, no C written) or builds it, and then
the executable it built must print what `refined run` prints and exit with the same code. A program stage0
accepts and gets wrong fails this test; a program it refuses only counts against coverage, which is reported
and may not fall below the floor recorded here as the subset grows."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

SUITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "suite")
sys.path.insert(0, SUITE)

import caselib  # noqa: E402

STAGE0 = os.path.join(caselib.ROOT, "docs", "refined-examples", "stage0")
EXE = ".exe" if os.name == "nt" else ""
# the number of suite programs the self-hosted compiler builds correctly; raise it as the subset grows
COVERAGE_FLOOR = 3
_LOCATED = re.compile(r"^[^\n:]+\.sem:\d+:\d+: .+\n$")


def _compiler() -> str | None:
    for name in ("cc", "gcc", "clang"):
        if shutil.which(name):
            return name
    return None


CC = _compiler()


def _cases() -> list:
    return [c for c in caselib.discover()
            if c.mode == "run" and not os.path.isdir(c.path) and not c.args and not c.stdin and not c.missing_tools()
            and not os.path.exists(c.path[:-4] + ".test.sem")]


@pytest.mark.skipif(CC is None, reason="no C compiler named cc, gcc, or clang on PATH")
def test_selfhosted_compiler_on_the_suite(tmp_path):
    exe = str(tmp_path / ("stage0" + EXE))
    built = caselib.refined("build", STAGE0, "--kind", "executable", "--output", exe, cwd=STAGE0, timeout=900)
    assert built.returncode == 0, built.stdout + built.stderr

    def one(case):
        project = caselib.materialize(case, str(tmp_path / "cases" / case.name.replace("/", "_")))
        source = os.path.relpath(caselib.module_file(project), project).replace(os.sep, "/")
        name = os.path.basename(source)[:-4]
        proc = subprocess.run([exe, source, f"build/{name}", CC], capture_output=True, text=True, cwd=project,
                              timeout=300)
        if proc.returncode == 1:
            ok = proc.stdout == "" and _LOCATED.match(proc.stderr) is not None \
                and not os.path.exists(os.path.join(project, "build", name + ".c"))
            return case.name, "refused", None if ok else f"bad refusal: {proc.stderr!r}"
        if proc.returncode != 0:
            return case.name, "error", f"stage0 exit {proc.returncode}: {proc.stdout}{proc.stderr}"
        ran = subprocess.run([os.path.join(project, "build", name + EXE)], capture_output=True, text=True,
                             timeout=120, cwd=project)
        reference = caselib.run_case(case, project)
        if (ran.stdout, ran.returncode) != (reference.stdout, reference.returncode):
            return case.name, "wrong", (f"built: {ran.returncode} {ran.stdout!r} {ran.stderr[-300:]!r}; "
                                        f"refined run: {reference.returncode} {reference.stdout!r}")
        return case.name, "built", None

    cases = _cases()
    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(one, cases))
    built_ok = [r for r in results if r[1] == "built"]
    problems = [r for r in results if r[2] is not None]
    print(f"\nself-hosted compiler: {len(built_ok)} of {len(cases)} suite programs built and matched; "
          f"{sum(r[1] == 'refused' for r in results)} refused")
    for name, _, why in built_ok:
        print("  built:", name)
    assert not problems, "\n".join(f"{n}: {why}" for n, _, why in problems)
    assert len(built_ok) >= COVERAGE_FLOOR
