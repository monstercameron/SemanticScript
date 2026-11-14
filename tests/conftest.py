"""Pytest fixture-discovery hook for the SemanticScript test suite.

Puts semanticscript/compiler/ on sys.path so every test under tests/ can
`import refined` regardless of pytest's import mode or the directory the suite
is launched from, and builds the self-hosted compiler once per session for the
tests that run it (test_stage0, test_selfhost_suite, test_bootstrap).
"""
import os
import shutil
import subprocess
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "semanticscript", "compiler"))

STAGE0 = os.path.join(_ROOT, "docs", "refined-examples", "stage0")
EXE = ".exe" if os.name == "nt" else ""


def c_compiler():
    """stage0 may run only a C compiler named exactly cc, gcc, or clang: those are its capability's scopes."""
    for name in ("cc", "gcc", "clang"):
        if shutil.which(name):
            return name
    return None


@pytest.fixture(scope="session")
def stage0_native(tmp_path_factory) -> str:
    """stage0 built once as a standalone executable by the Python compiler (`refined build --kind executable`): the
    first step of the bootstrap, and the stage0 the sample, suite, and bootstrap tests run."""
    if c_compiler() is None:
        pytest.skip("no C compiler named cc, gcc, or clang on PATH")
    exe = str(tmp_path_factory.mktemp("stage0native") / ("stage0" + EXE))
    built = subprocess.run([sys.executable, os.path.join(_ROOT, "semanticscript", "compiler", "refined"), "build",
                            STAGE0, "--kind", "executable", "--output", exe], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", cwd=STAGE0, timeout=1800)
    assert built.returncode == 0, built.stdout + built.stderr
    return exe
