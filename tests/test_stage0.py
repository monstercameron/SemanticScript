"""stage0 (docs/refined-examples/stage0): the first stage of a SemanticScript compiler written in SemanticScript.

stage0 runs under `refined run`, reads a sample module, checks that it is in the stage0 subset, writes it as C, and
builds it with the C compiler through `process.run`. Each executable it builds must print what `refined run` prints
for the same sample and exit with the same code, a loop that passes its bound included."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

SUITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "suite")
sys.path.insert(0, SUITE)

import caselib  # noqa: E402

STAGE0 = os.path.join(caselib.ROOT, "docs", "refined-examples", "stage0")

# what each sample prints and its exit code, under `refined run` and as an executable
SAMPLES = {
    "hello": ("Hello, world!\n", 0),
    "squares": ("1\n4\n9\n16\n25\n", 0),
    "branch": ("left is smaller\ngap: -19\n", 3),
    "overrun": ("1\n2\n3\n4\n", 70),
}


def _compiler() -> str | None:
    """stage0 may run only a C compiler named exactly cc, gcc, or clang: those are its capability's scopes."""
    for name in ("cc", "gcc", "clang"):
        if shutil.which(name):
            return name
    return None


CC = _compiler()


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> str:
    """A copy of stage0 to run in: it writes under build/ in its working directory."""
    dst = str(tmp_path_factory.mktemp("stage0") / "stage0")
    shutil.copytree(STAGE0, dst, ignore=shutil.ignore_patterns("build"))
    return dst


def _stage0(project: str, *arguments: str) -> subprocess.CompletedProcess:
    return caselib.refined("run", project, "--", *arguments, cwd=project, timeout=900)


@pytest.mark.skipif(CC is None, reason="no C compiler named cc, gcc, or clang on PATH")
@pytest.mark.parametrize("sample", sorted(SAMPLES))
def test_stage0_builds_executables_that_behave_like_refined_run(project, sample):
    built = _stage0(project, f"samples/{sample}/{sample}.sem", f"build/{sample}", CC)
    assert built.returncode == 0, built.stdout + built.stderr
    assert built.stdout == f"stage0: samples/{sample}/{sample}.sem -> build/{sample}.c -> build/{sample}\n"
    assert os.path.isfile(os.path.join(project, "build", f"{sample}.c"))
    reference = caselib.refined("run", os.path.join(project, "samples", sample), cwd=project)
    executable = os.path.join(project, "build", sample + (".exe" if os.name == "nt" else ""))
    ran = subprocess.run([executable], capture_output=True, text=True, timeout=60)
    assert (reference.stdout, reference.returncode) == SAMPLES[sample], reference.stderr
    assert (ran.stdout, ran.returncode) == (reference.stdout, reference.returncode), ran.stderr


def test_stage0_refuses_a_source_outside_its_subset(project):
    """A refused source is reported as `path:line:column: message (word)` with exit code 1, and nothing is written;
    no arguments is a usage error, exit code 2."""
    proc = _stage0(project, "samples/outside/outside.sem", "build/outside")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert proc.stdout == ""
    assert proc.stderr == "samples/outside/outside.sem:12:10: this entity kind is outside the stage0 subset (record)\n"
    assert not os.path.exists(os.path.join(project, "build", "outside.c"))
    proc = caselib.refined("run", project, cwd=project)
    assert proc.returncode == 2 and proc.stderr.startswith("usage: "), proc.stderr


def test_stage0_module_tests_pass():
    """Every exported invariant of stage0's modules is verified by a test, and every test passes."""
    proc = caselib.refined("test", STAGE0, timeout=900)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "16 of 16 tests passed" in proc.stdout
