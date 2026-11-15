"""The runtime's exact math functions and fenv.h (module `cmathbits`), against glibc's results.

Accuracy bound of every function: bit-exact, signed zeros and NaN payloads included. frexp, ldexp, scalbn, scalbln,
ilogb, logb, modf, rint, nearbyint, lrint, llrint, lround, llround, remainder, remquo, fdim, fmax, fmin, fma, nan, and
nextafter, each in its double and its f-suffixed float form, give the one value their definition names (a result
rounded once, to the format's own precision), so there is no error to bound. The fenv.h functions work on an emulated
environment (no machine primitive reads MXCSR or FPCR): their results are glibc's for flags and modes set through
fenv.h itself, which rint and lrint obey; flags arithmetic would raise are not raised.

`nexttoward` and `nexttowardf` are not provided: their second argument is a long double, which x86_64 passes on the
x87 stack, outside what the runtime's ABI rows take.

Checks: the executable with no libc prints what the Python models compute; on Linux it prints what `refined run`
prints, which calls glibc; and the library's table holds exactly these names, each exported by glibc.
"""
from __future__ import annotations

import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_runtime_nolibc as base  # noqa: E402
import cmathbitstour  # noqa: E402

caselib = base.caselib
RUNTIME = base.RUNTIME

# the C names the module's `abi library` operations have
NAMES = set(cmathbitstour.NAMES)


def _arm() -> bool:
    """Whether the executables are built for AArch64 (the models' constants differ there)."""
    from refined.native import find_cc, platform
    cc = find_cc()
    if cc is None:
        return False
    _machine, triple, _problem = platform(cc)
    return bool(triple) and triple.startswith("aarch64")


def _tour(tmp_path):
    arm = _arm()
    project = str(tmp_path / "cmathbitstour")
    cmathbitstour.write_project(project, arm)
    caselib.approve(project)
    return project, arm


@base.needs_windows_cc
def test_exact_math_matches_the_models(tmp_path):
    """Built as an executable with no libc, the tour prints, for every function over special values and a sweep, the
    bits the exact models compute; on Linux it prints what `refined run` prints, which is glibc's answer."""
    project, arm = _tour(tmp_path)
    exe = os.path.join(project, "program.exe")
    built = base._build(project, exe)
    assert built.returncode == 0, built.stdout + built.stderr
    base.assert_no_libc(exe)
    ran = base._exe(exe, project)
    assert ran.returncode == 0 and ran.stderr == "", ran.stderr
    want = cmathbitstour.expected(arm)
    got = ran.stdout.splitlines()
    bad = [(i, g, w) for i, (g, w) in enumerate(zip(got, want)) if g != w]
    assert len(got) == len(want) and bad == [], (len(got), len(want), bad[:20])
    if not base.WINDOWS:
        jit = base._jit(project)
        assert (jit.returncode, jit.stdout, jit.stderr) == (ran.returncode, ran.stdout, ran.stderr)


def test_cmathbits_table_names_glibc_functions():
    """The `abi library` names of the module are the tour's list, and on Linux each is exported by glibc or libm."""
    with open(os.path.join(RUNTIME, "cmathbits.sem"), encoding="utf-8") as fh:
        names = set(re.findall(r'^\w+ abi library "(\w+)"(?: variadic)?$', fh.read(), re.M))
    assert names == NAMES, (names - NAMES, NAMES - names)
    if not base.WINDOWS and base.PLATFORM:
        import ctypes
        import ctypes.util
        glibc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6")
        libm = ctypes.CDLL(ctypes.util.find_library("m") or "libm.so.6")
        assert [n for n in sorted(names) if not hasattr(glibc, n) and not hasattr(libm, n)] == []


def test_models_agree_with_python_where_python_has_the_function():
    """The tour's expected values are built from models; pin them to Python's own math where it has the same
    function, so the models cannot drift from what they claim."""
    import math
    m = cmathbitstour.Models()
    for x in (0.5, -3.75, 1e300, 5e-324, -0.0):
        assert m.frexp("d", x)[0] == math.frexp(x)[0] and m.frexp("d", x)[1] == [math.frexp(x)[1]]
        assert math.copysign(1, m.modf("d", x)[0]) == math.copysign(1, math.modf(x)[0])
    for x, y in ((7.5, 2.0), (-7.5, 2.0), (1.0, 0.1), (1e300, 3e-300)):
        assert m.remainder("d", x, y) == math.remainder(x, y)
        assert m.nextafter("d", x, y) == math.nextafter(x, y)
    assert m.fma("d", 1.0 + 2.0 ** -52, 1.0 - 2.0 ** -52, -1.0) == -(2.0 ** -104)
