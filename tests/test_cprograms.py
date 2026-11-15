"""C programs linked with the runtime's C library instead of glibc (D-161), on Linux.

`refined build semanticscript/runtime --kind clibrary` writes the runtime's C library (written in SemanticScript) as
one object. Each program in tests/cprograms is compiled once with the system's own compiler and glibc's headers, then
linked twice: with glibc as usual, and with `cc -nostdlib -static <program.o> <the object> -lgcc`. Both run in fresh
directories with the same standard input, and must give the same standard output, standard error, and exit code,
byte for byte; the second must be static, with no dynamic loader and nothing of glibc in it. Windows is not tested
here: MinGW's headers assume the Microsoft C runtime's ABI, so there `ffi` (tests/ctour.py) is the proof.
"""
from __future__ import annotations

import os
import struct
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROGRAMS = os.path.join(HERE, "cprograms")
sys.path.insert(0, os.path.join(ROOT, "semanticscript", "compiler"))

# what a program reads on standard input
STDIN = {"stdio_scanf": "Z 77 word x\n"}
# the compiler's options: each program is built both ways at each level
LEVELS = ["-O0", "-O2"]  # -O2 brings _FORTIFY_SOURCE (Ubuntu turns it on), so glibc's headers call the __*_chk names


def _linux_cc():
    if not sys.platform.startswith("linux"):
        return None
    from refined.native import find_cc, platform
    cc = find_cc()
    if cc is None:
        return None
    _machine, triple, _problem = platform(cc)
    return cc if triple and "linux" in triple else None


CC = _linux_cc()
needs_linux = pytest.mark.skipif(CC is None, reason="C programs link with the runtime's C library on Linux (D-161)")


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    out = str(tmp_path_factory.mktemp("clibrary") / "semanticscript-c.o")
    built = subprocess.run([sys.executable, "-m", "refined", "build", os.path.join(ROOT, "semanticscript", "runtime"),
                            "--kind", "clibrary", "--output", out], capture_output=True, text=True,
                           env={**os.environ, "PYTHONPATH": os.path.join(ROOT, "semanticscript", "compiler")})
    assert built.returncode == 0, built.stdout + built.stderr
    return out


def _static_and_clean(path: str) -> None:
    """No PT_INTERP or PT_DYNAMIC, and nothing linking glibc would leave."""
    with open(path, "rb") as fh:
        data = fh.read()
    phoff = struct.unpack_from("<Q", data, 0x20)[0]
    phentsize, phnum = struct.unpack_from("<HH", data, 0x36)
    kinds = [struct.unpack_from("<I", data, phoff + i * phentsize)[0] for i in range(phnum)]
    assert 2 not in kinds and 3 not in kinds, kinds
    for mark in (b"GLIBC_", b"__libc_start_main", b"/lib64/ld-linux", b"/lib/ld-linux"):
        assert mark not in data, mark


def _run(exe: str, folder: str, stdin: str) -> tuple[int, bytes, bytes]:
    os.makedirs(folder, exist_ok=True)
    done = subprocess.run([exe], cwd=folder, input=stdin.encode(), capture_output=True, timeout=120)
    return done.returncode, done.stdout, done.stderr


@needs_linux
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("name", sorted(f[:-2] for f in os.listdir(PROGRAMS) if f.endswith(".c")))
def test_c_program_matches_glibc(name, level, library, tmp_path):
    """Each C program gives exactly what it gives with glibc: standard output, standard error, and exit code."""
    source = os.path.join(PROGRAMS, name + ".c")
    obj = str(tmp_path / (name + ".o"))
    compiled = subprocess.run(CC + [level, "-w", "-c", source, "-o", obj], capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    with_glibc, with_ours = str(tmp_path / "glibc"), str(tmp_path / "ours")
    linked = subprocess.run(CC + [obj, "-o", with_glibc, "-lm"], capture_output=True, text=True)
    assert linked.returncode == 0, linked.stderr
    linked = subprocess.run(CC + ["-nostdlib", "-static", obj, library, "-lgcc", "-o", with_ours],
                            capture_output=True, text=True)
    assert linked.returncode == 0, linked.stderr
    _static_and_clean(with_ours)
    stdin = STDIN.get(name, "")
    want = _run(with_glibc, str(tmp_path / "run-glibc"), stdin)
    got = _run(with_ours, str(tmp_path / "run-ours"), stdin)
    assert got[0] == want[0], (got[0], want[0], got[2][-2000:])
    if got[1] != want[1]:
        theirs, ours = want[1].decode(errors="replace").splitlines(), got[1].decode(errors="replace").splitlines()
        differ = [(i, g, w) for i, (g, w) in enumerate(zip(ours, theirs)) if g != w][:15]
        assert got[1] == want[1], (len(ours), len(theirs), differ)
    assert got[2] == want[2], (got[2][-2000:], want[2][-2000:])
