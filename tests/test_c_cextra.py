"""The runtime's strtok family and glibc's string extras, strtof, rand, aligned allocation, locale.h, assert.h, and
inttypes.h (module `cextra`), against glibc's results.

Models: rand and srand are glibc's TYPE_3 additive feedback generator (r[i] = r[i-3] + r[i-31], seeded by the 16807
LCG, 310 outputs thrown away, result >> 1) and rand_r its three-step linear congruence; strtof is rounded with exact
fractions (ties to even, halfway cases included) with ERANGE as glibc sets it for a float; strtok, strsep, and the
strtol family follow their C definitions.

Not provided: `imaxdiv`, which returns a 16-byte struct (imaxdiv_t) and waits for struct returns in the ABI rows.
On Windows a block aligned_alloc or posix_memalign gives for an alignment above 16 comes from probing HeapAlloc until
an address is aligned (HeapAlloc cannot align), and the block is a plain heap block, so free accepts it; a size too
large to probe with gives NULL. On Linux a block of a large size aligned above 32 leaks when freed.

Checks: the executable with no libc prints what the models compute; on Linux it prints what `refined run` prints,
which calls glibc; __assert_fail's message and abort are those of glibc; and the library's table holds exactly these
names, each exported by glibc.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_runtime_nolibc as base  # noqa: E402
import cextratour  # noqa: E402

caselib = base.caselib
RUNTIME = base.RUNTIME

# the C names the module's `abi library` operations have
NAMES = set(cextratour.NAMES)


def _tour(tmp_path):
    project = str(tmp_path / "cextratour")
    cextratour.write_project(project)
    caselib.approve(project)
    return project


@base.needs_windows_cc
def test_cextra_matches_the_models(tmp_path):
    """Built as an executable with no libc, the tour prints what the models compute for every function; on Linux it
    prints what `refined run` prints, which is glibc's answer."""
    project = _tour(tmp_path)
    exe = os.path.join(project, "program.exe")
    built = base._build(project, exe)
    assert built.returncode == 0, built.stdout + built.stderr
    base.assert_no_libc(exe)
    ran = base._exe(exe, project)
    assert ran.returncode == 0 and ran.stderr == "", ran.stderr
    want = cextratour.expected()
    got = ran.stdout.splitlines()
    bad = [(i, g, w) for i, (g, w) in enumerate(zip(got, want)) if g != w]
    assert len(got) == len(want) and bad == [], (len(got), len(want), bad[:20])
    if not base.WINDOWS:
        jit = base._jit(project)
        assert (jit.returncode, jit.stderr) == (ran.returncode, ran.stderr)
        # errno does not survive a ctypes call, so it is compared with the models above, not with refined run
        assert cextratour.without_errno(jit.stdout.splitlines()) == cextratour.without_errno(got)


@base.needs_windows_cc
@pytest.mark.parametrize("with_function", [True, False])
def test_assert_fail_writes_glibcs_message_and_aborts(tmp_path, with_function):
    """__assert_fail writes `<program>: <file>:<line>: <function>: Assertion `<text>' failed.` to standard error and
    aborts (SIGABRT on Linux, exit code 3 on Windows); the function and its colon are left out when it is NULL."""
    project = str(tmp_path / "assertour")
    cextratour.write_assert_project(project, with_function)
    caselib.approve(project)
    exe = os.path.join(project, "program.exe")
    built = base._build(project, exe)
    assert built.returncode == 0, built.stdout + built.stderr
    base.assert_no_libc(exe)
    ran = base._exe(exe, project)
    assert ran.stderr == cextratour.expected_assert_message(os.path.basename(exe), with_function), ran.stderr
    assert ran.stdout == ""
    assert ran.returncode == (3 if base.WINDOWS else -6), ran.returncode


def test_cextra_table_names_glibc_functions():
    """The `abi library` names of the module are the tour's list, and on Linux each is exported by glibc."""
    with open(os.path.join(RUNTIME, "cextra.sem"), encoding="utf-8") as fh:
        names = set(re.findall(r'^\w+ abi library "(\w+)"(?: variadic)?$', fh.read(), re.M))
    assert names == NAMES, (names - NAMES, NAMES - names)
    if not base.WINDOWS and base.PLATFORM:
        import ctypes
        import ctypes.util
        glibc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6")
        assert [n for n in sorted(names) if not hasattr(glibc, n)] == []


def test_models_agree_with_what_python_knows():
    """The tour's expected values come from models; pin them to values known from glibc and to Python."""
    # glibc's rand() after srand(1) (and with no srand): the sequence every C programmer has seen
    assert cextratour.glibc_rand_sequence(1, 5) == [1804289383, 846930886, 1681692777, 1714636915, 1957747793]
    assert cextratour.glibc_rand_sequence(0, 5) == cextratour.glibc_rand_sequence(1, 5)
    # strtof's model rounds as numpy's float32 does where it is installed, and ties to even
    import struct
    import math
    for text in ("0.1", "3.4028235e38", "1e-45", "16777217", "123456789012345678901234567890", "0.3"):
        value, _nan, _error, _end = cextratour.c_strtof(text)
        assert value == struct.unpack("<f", struct.pack("<f", float(text)))[0] if abs(float(text)) < 3.5e38 else True
    assert cextratour.c_strtof("1.000000059604644775390625")[0] == 1.0
    assert cextratour.c_strtof("1.00000005960464477539062500000001")[0] == 1.0000001192092896
    assert cextratour.c_strtof("1e39")[:3] == (math.inf, False, 34)
    assert cextratour.c_strtof("0x1p-149") == (1.401298464324817e-45, False, 0, 8)
    assert cextratour.c_strtol("0x1fz", 0, False) == (31, 0, 4)
    assert cextratour.c_strtol("0x", 16, False) == (0, 0, 1)
    assert cextratour.c_strtol("18446744073709551615", 10, True) == (-1, 0, 20)
