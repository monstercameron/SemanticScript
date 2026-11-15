"""The special functions of math.h written in SemanticScript (the module `cmathspecial`, D-153): sinh, cosh, tanh,
asinh, acosh, atanh, erf, erfc, tgamma and lgamma for double and float, and lgamma_r and lgammaf_r.

Three checks:
- the executable check: tests/cmathspecialtour.py is built as an executable with the runtime in SemanticScript and no
  C library, calls every function through `ffi` over special values and a deterministic sweep, and what it prints is
  held to an exact reference computed with decimal arithmetic (series and continued fractions, not the math module);
- the Linux check (skipped elsewhere): the executable's output against `refined run`, which calls glibc through ctypes;
- the table check: the `abi library` names of the module are exactly the list here, and on Linux glibc exports each.

The bounds the module guarantees (what the first check enforces):
- sinh, cosh, tanh, asinh, acosh, atanh, erf, erfc: at most 1 ulp from the exact value for double (the method is
  double-double arithmetic with about 2^-75 relative error, so the result is the nearest double except when the exact
  value lies within 2^-20 of a ulp from a rounding boundary, which a sweep like this one does not meet); the f-forms
  compute in double and round once, and the bound enforced is 1 float ulp;
- tgamma and lgamma: the same 1 ulp bound, except that lgamma near its zeros at negative arguments (where the value is
  below 0.01 in magnitude) is held to an absolute error of 2^-72, since a relative one is meaningless there (glibc
  documents its errors near these zeros likewise);
- Annex F's special cases are exact: signs of zero, infinities, NaN, tgamma at negative whole numbers (NaN), tgamma
  of +-0 (+-infinity), lgamma at non-positive whole numbers (+infinity), lgamma at 1 and 2 (+0), the sign lgamma_r
  stores (1 or -1 for the sign of gamma(x), -1 for -0).
The Linux check allows the distance between the module and glibc to be the sum of glibc's own documented errors for
x86_64 (LINUX_ULPS below) and the module's one ulp.
"""
from __future__ import annotations

import math
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from test_runtime_nolibc import RUNTIME, WINDOWS, PLATFORM, _build, _exe, _jit, assert_no_libc, needs_windows_cc  # noqa: E402
import caselib  # noqa: E402  (tests/suite is on the path through test_runtime_nolibc)
import cmathspecialtour as tour  # noqa: E402

ULPS = 1.0
LINUX_ULPS = {"sinh": 4.0, "cosh": 4.0, "tanh": 4.0, "asinh": 4.0, "acosh": 4.0, "atanh": 4.0, "erf": 4.0, "erfc": 5.0,
              "tgamma": 12.0, "lgamma": 8.0}
ZERO_ABSOLUTE = 2.0 ** -72       # lgamma below 0.01 in magnitude at a negative argument (measured: 2^-84)
LINUX_ZERO_ABSOLUTE = 2.0 ** -40
EXPECTED_NAMES = set(tour.ALL_NAMES)


def _signbit(x: float) -> bool:
    return math.copysign(1.0, x) < 0


def _same(a: float, b: float) -> bool:
    if math.isnan(a) and math.isnan(b):
        return True
    return tour.bits(a) == tour.bits(b)


def _parse(text: str) -> float:
    return float(text)


def _results(lines: list[str]):
    """Pair every call of the tour with what the executable printed for it."""
    at = 0
    for name, base, x in tour.CALLS:
        got = _parse(lines[at])
        at += 1
        sign = None
        if name.endswith("_r"):
            length = int(lines[at])
            at += 1
            sign = 1 if length == 1 else -1 if length == 4 else length
        yield name, base, x, got, sign
    assert at == len(lines), (at, len(lines))


def _judge(name: str, base: str, x: float, got: float) -> str | None:
    """None when a result is within the module's bound, otherwise why not."""
    single = tour.is_float(name)
    want = tour.expected(base, x, single)
    if math.isnan(want):
        return None if math.isnan(got) else f"want NaN, got {got!r}"
    if _same(got, want):
        return None
    if math.isinf(want) or math.isnan(got) or math.isinf(got):
        return f"want {want!r}, got {got!r}"
    ref = tour.reference(base, x)
    unit = tour.ulp_of(want if want != 0 else 0.0, single)
    from decimal import Decimal as D
    error = abs(D(got) - ref)
    if base == "lgamma" and x < 0 and abs(ref) < D("0.01") and error <= D(ZERO_ABSOLUTE):
        return None
    if error / D(unit) <= D(ULPS):
        return None
    return f"want {want!r}, got {got!r}, {float(error / D(unit)):.3f} ulp"


def _build_tour(tmp_path):
    project = str(tmp_path / "cmathspecialtour")
    tour.write_project(project)
    caselib.approve(project)
    exe = os.path.join(project, "program.exe")
    built = _build(project, exe)
    assert built.returncode == 0, built.stdout + built.stderr
    assert_no_libc(exe)
    return project, exe


@needs_windows_cc
def test_special_functions_in_an_executable_match_the_exact_values(tmp_path):
    """D-153: sinh, cosh, tanh, asinh, acosh, atanh, erf, erfc, tgamma, lgamma, their f-forms, lgamma_r and lgammaf_r,
    bound through `ffi.open("c")` in an executable with no C library, give the exact value to within 1 ulp (lgamma
    near its negative zeros to within 2^-72) and Annex F's special cases exactly."""
    project, exe = _build_tour(tmp_path)
    ran = _exe(exe, project)
    assert ran.returncode == 0 and ran.stderr == "", ran.stderr
    lines = ran.stdout.splitlines()
    problems = []
    for name, base, x, got, sign in _results(lines):
        why = _judge(name, base, x, got)
        if why:
            problems.append((name, x, why))
        if sign is not None and sign != tour.expected_sign(x):
            problems.append((name, x, f"sign {sign}, want {tour.expected_sign(x)}"))
    assert problems == [], problems[:20]


@pytest.mark.skipif(WINDOWS or not PLATFORM, reason="`refined run` calls glibc through ctypes on Linux")
def test_special_functions_match_glibc(tmp_path):
    """The executable prints what glibc does, within the sum of glibc's documented errors and the module's one ulp,
    exactly for NaN, infinities, signed zeros and the signs lgamma_r stores."""
    project, exe = _build_tour(tmp_path)
    ran = _exe(exe, project)
    jit = _jit(project)
    assert ran.returncode == 0 and jit.returncode == 0, (ran.stderr, jit.stderr)
    ours, theirs = ran.stdout.splitlines(), jit.stdout.splitlines()
    assert len(ours) == len(theirs)
    problems = []
    for (name, base, x, got, sign), (_n, _b, _x, glibc, glibc_sign) in zip(_results(ours), _results(theirs)):
        if sign != glibc_sign:
            problems.append((name, x, f"sign {sign} against {glibc_sign}"))
            continue
        if _same(got, glibc):
            continue
        if math.isnan(got) != math.isnan(glibc) or math.isinf(got) or math.isinf(glibc):
            problems.append((name, x, got, glibc))
            continue
        single = tour.is_float(name)
        unit = tour.ulp_of(glibc, single)
        if base == "lgamma" and x < 0 and abs(glibc) < 0.01 and abs(got - glibc) <= LINUX_ZERO_ABSOLUTE:
            continue
        if abs(got - glibc) / unit > LINUX_ULPS[base] + ULPS:
            problems.append((name, x, got, glibc, abs(got - glibc) / unit))
    assert problems == [], problems[:20]


def test_special_function_table_names_glibc_functions():
    """The module's `abi library` operations are exactly the functions of this list, each a name glibc exports
    (math.h's from libm)."""
    with open(os.path.join(RUNTIME, "cmathspecial.sem"), encoding="utf-8") as fh:
        names = set(re.findall(r'^\w+ abi library "(\w+)"(?: variadic)?$', fh.read(), re.M))
    assert names == EXPECTED_NAMES, (names - EXPECTED_NAMES, EXPECTED_NAMES - names)
    if not WINDOWS and PLATFORM:
        import ctypes
        import ctypes.util
        glibc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6")
        libm = ctypes.CDLL(ctypes.util.find_library("m") or "libm.so.6")
        assert [n for n in sorted(names) if not hasattr(glibc, n) and not hasattr(libm, n)] == []
