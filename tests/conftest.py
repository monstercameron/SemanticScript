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
RUNTIME = os.path.join(_ROOT, "semanticscript", "runtime")
EXE = ".exe" if os.name == "nt" else ""
# D-142: what stage0 passes the C compiler after the C file: the runtime in SemanticScript as an object (built once
# per session by `stage0_native`, which puts its path first), then the flags that link it with no C library
LINK: list[str] = []
LINK_FLAGS = (["-nostdlib", "-nostartfiles", "-Wl,-e,refined_entry", "-Wl,--stack,268435456", "-lkernel32",
               "-lws2_32", "-lbcrypt", "-lgcc"]
              if os.name == "nt" else ["-nostdlib", "-nostartfiles", "-static", "-fno-stack-protector", "-lgcc"])


def c_compiler():
    """stage0 may run only a C compiler named exactly cc, gcc, or clang: those are its capability's scopes."""
    for name in ("cc", "gcc", "clang"):
        if shutil.which(name):
            return name
    return None


@pytest.fixture(scope="session")
def stage0_native(tmp_path_factory) -> str:
    """stage0 built once as a standalone executable by the Python compiler (`refined build --kind executable`): the
    first step of the bootstrap, and the stage0 the sample, suite, and bootstrap tests run. It also builds the runtime
    object stage0's C links (`refined build semanticscript/runtime --kind runtime`) and fills `LINK`."""
    if c_compiler() is None:
        pytest.skip("no C compiler named cc, gcc, or clang on PATH")
    folder = tmp_path_factory.mktemp("stage0native")
    exe = str(folder / ("stage0" + EXE))
    compiler = os.path.join(_ROOT, "semanticscript", "compiler", "refined")
    built = subprocess.run([sys.executable, compiler, "build", STAGE0, "--kind", "executable", "--output", exe],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=STAGE0,
                           timeout=1800)
    assert built.returncode == 0, built.stdout + built.stderr
    if not LINK:
        runtime_object = str(folder / "runtime.o")
        made = subprocess.run([sys.executable, compiler, "build", RUNTIME, "--kind", "runtime", "--output",
                               runtime_object], capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=1800)
        assert made.returncode == 0, made.stdout + made.stderr
        LINK[:] = [runtime_object, *LINK_FLAGS]
    return exe
