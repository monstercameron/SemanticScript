"""math.h's exponentials, logarithms, pow, cbrt and hypot in the runtime's C library (module cmathexp).

The accuracy bounds this module guarantees, tested here:
  * every function, double and f-suffixed float form, is within 1 unit in the last place of the correctly rounded
    result at every tour point (measured on the sweep: almost all are the correctly rounded value), and the special
    values of C99 Annex F (zeros with their signs, infinities, NaN, overflow, underflow) are exactly the standard's;
  * on Linux, against glibc: within 2 ulp for every function (both are within 1 ulp of the exact value, glibc's
    cbrt is documented up to 4 ulp, so cbrt is held to 4), NaN and infinities and the sign of zero equal.
The algorithms are not glibc's table driven ones, so results are not claimed bit-identical to glibc's.
"""
from __future__ import annotations

import math
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "suite"))
sys.path.insert(0, HERE)

import caselib  # noqa: E402
import cmathexptour  # noqa: E402
from test_runtime_nolibc import PLATFORM, WINDOWS, _build, _exe, _jit, assert_no_libc  # noqa: E402

RUNTIME = os.path.join(ROOT, "semanticscript", "runtime")

# the `abi library` names of cmathexp.sem
C_NAMES = {"exp", "exp2", "expm1", "log", "log2", "log10", "log1p", "pow", "cbrt", "hypot",
           "expf", "exp2f", "expm1f", "logf", "log2f", "log10f", "log1pf", "powf", "cbrtf", "hypotf"}

EXACT_BOUND = 1
GLIBC_BOUND = {"cbrt": 4}


def _parse(lines):
    out = []
    for line in lines:
        out.append(float(line))
    return out


def _same_special(want: float, got: float) -> bool:
    """NaN is NaN, an infinity is that infinity, a zero is a zero of the same sign."""
    if math.isnan(want) or math.isnan(got):
        return math.isnan(want) and math.isnan(got)
    if math.isinf(want) or math.isinf(got):
        return want == got
    if want == 0 or got == 0:
        return want == got and math.copysign(1, want) == math.copysign(1, got)
    return True


def _run(tmp_path):
    project = str(tmp_path / "cmathexptour")
    cmathexptour.write_project(project)
    caselib.approve(project)
    exe = os.path.join(project, "program.exe")
    built = _build(project, exe)
    assert built.returncode == 0, built.stdout + built.stderr
    assert_no_libc(exe)
    ran = _exe(exe, project)
    assert ran.returncode == 0 and ran.stderr == "", ran.stderr
    return project, ran


def test_c_math_exp_family_has_the_names():
    """Table check: the `abi library` names of cmathexp.sem are the ones this test lists; on Linux glibc exports each."""
    with open(os.path.join(RUNTIME, "cmathexp.sem"), encoding="utf-8") as fh:
        names = set(re.findall(r'^\w+ abi library "(\w+)"$', fh.read(), re.M))
    assert names == C_NAMES, (names - C_NAMES, C_NAMES - names)
    if PLATFORM and not WINDOWS:
        import ctypes
        import ctypes.util
        libm = ctypes.CDLL(ctypes.util.find_library("m") or "libm.so.6")
        assert [n for n in sorted(names) if not hasattr(libm, n)] == []


@pytest.mark.skipif(not PLATFORM, reason="the runtime in SemanticScript links on Windows (MinGW) and x86_64 Linux")
def test_c_math_exp_family_is_accurate(tmp_path):
    """The executable, with no C library, prints values within 1 ulp of the correctly rounded ones (Decimal at 110
    digits), the special values exactly; on Linux it is also compared with glibc through `refined run`."""
    project, ran = _run(tmp_path)
    got = _parse(ran.stdout.splitlines())
    want = cmathexptour.expected()
    where = cmathexptour.layout()
    assert len(got) == len(want) == len(where), (len(got), len(want), len(where))
    bad, exact, total, worst = [], 0, 0, 0
    for i, (g, w, (name, single)) in enumerate(zip(got, want, where)):
        if not _same_special(w, g):
            bad.append((i, name, single, g, w))
            continue
        d = cmathexptour.ulps(g, w, single)
        total += 1
        exact += d == 0
        worst = max(worst, d)
        if d > EXACT_BOUND:
            bad.append((i, name, single, g, w, d))
    assert bad == [], bad[:20]
    print(f"cmathexp: {exact} of {total} values are the correctly rounded ones; worst error {worst} ulp")
    assert exact >= 0.97 * total
    if not WINDOWS:
        jit = _jit(project)
        assert jit.returncode == 0, jit.stderr
        glibc = _parse(jit.stdout.splitlines())
        assert len(glibc) == len(got)
        off = []
        for i, (g, h, (name, single)) in enumerate(zip(got, glibc, where)):
            if not _same_special(h, g):
                off.append((i, name, single, g, h))
            elif cmathexptour.ulps(g, h, single) > GLIBC_BOUND.get(name, 2):
                off.append((i, name, single, g, h, cmathexptour.ulps(g, h, single)))
        assert off == [], off[:20]
