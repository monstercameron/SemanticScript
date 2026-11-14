"""The bootstrap of the self-hosted compiler (docs/self-hosting-plan.md, criteria 2 and 3).

stage0 built by the Python compiler (conftest.stage0_native) compiles stage0's own source into a second executable,
stage0b. stage0b compiles every sample to C byte-identical to what stage0 writes, and the executables built from it
behave the same; then stage0b compiles stage0's source again, and the C it writes is byte-identical to the C stage0
wrote for stage0b: the fixed point, from which the Python compiler is no longer needed to build the compiler."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

SUITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "suite")
sys.path.insert(0, SUITE)

import caselib  # noqa: E402
from conftest import EXE, STAGE0, c_compiler  # noqa: E402
from test_stage0 import LINK, OUTSIDE, REFUSED, SAMPLES  # noqa: E402

CC = c_compiler()


def _copy(dst: str) -> str:
    """stage0's project, as stage0 reads it: build.sem, its modules, and the samples (it writes under build/)."""
    shutil.copytree(STAGE0, dst, ignore=shutil.ignore_patterns("build", "tools"))
    return dst


def _compile(stage0: str, cwd: str, project: str, output: str) -> subprocess.CompletedProcess:
    return subprocess.run([stage0, project, output, CC, *LINK], capture_output=True, text=True, cwd=cwd, timeout=900)


def _read(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


@pytest.mark.skipif(CC is None, reason="no C compiler named cc, gcc, or clang on PATH")
def test_stage0_compiles_itself_to_a_fixed_point(stage0_native, tmp_path):
    first = _copy(str(tmp_path / "first"))
    built = _compile(stage0_native, first, ".", "build/stage0b")
    assert built.returncode == 0, built.stdout + built.stderr
    assert built.stdout == "stage0: . -> build/stage0b.c -> build/stage0b\n"
    stage0b = os.path.join(first, "build", "stage0b" + EXE)
    assert os.path.isfile(stage0b)

    # stage0b compiles the samples to the C stage0 writes, and what it builds behaves the same
    second = _copy(str(tmp_path / "second"))
    for sample in sorted(SAMPLES):
        a = _compile(stage0_native, first, f"samples/{sample}", f"build/{sample}")
        b = _compile(stage0b, second, f"samples/{sample}", f"build/{sample}")
        assert (a.returncode, b.returncode) == (0, 0), a.stdout + a.stderr + b.stdout + b.stderr
        assert b.stdout == a.stdout
        assert _read(os.path.join(second, "build", f"{sample}.c")) == _read(os.path.join(first, "build",
                                                                                         f"{sample}.c")), sample
        ran = subprocess.run([os.path.join(second, "build", sample + EXE)], capture_output=True, text=True,
                             cwd=second, timeout=60)
        assert (ran.stdout, ran.returncode) == SAMPLES[sample], ran.stderr
    refused = _compile(stage0b, second, "samples/outside", "build/outside")
    assert (refused.returncode, refused.stdout, refused.stderr) == (1, "", OUTSIDE)
    for program, where in sorted(REFUSED.items()):
        refused = _compile(stage0b, second, f"samples/refused/{program}", f"build/{program}")
        assert (refused.returncode, refused.stdout, refused.stderr) == \
            (1, "", f"samples/refused/{program}/{where}\n"), program
        assert not os.path.exists(os.path.join(second, "build", f"{program}.c"))

    # stage0b compiles stage0's source to the same C stage0 wrote for stage0b: the fixed point
    again = _compile(stage0b, second, ".", "build/stage0c")
    assert again.returncode == 0, again.stdout + again.stderr
    assert _read(os.path.join(second, "build", "stage0c.c")) == _read(os.path.join(first, "build", "stage0b.c"))
    print(f"\nbootstrap: stage0b.c is {os.path.getsize(os.path.join(first, 'build', 'stage0b.c'))} bytes; "
          "stage0b compiles stage0 to the same C")
