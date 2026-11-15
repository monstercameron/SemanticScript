"""The runtime's trigonometric functions (D-153): sin, cos, tan, asin, acos, atan, atan2 and their f forms, written in
SemanticScript (semanticscript/runtime/tools/cmathtrig.dsl), bound through `ffi.open("c")` in an executable with no C
library.

The bound this module guarantees, held by the tests below: every result is within 1.0 ulp of the exact value (the
doubles' and the floats' own ulp; measured against an exact reference computed with Python decimals and Taylor series in
tools/cmathtriggen.py, and not against `math.sin`) for every argument of the tour, which reaches from 2^-60 to the
largest double, Payne and Hanek's reduction included (the measured worst case is 0.64 ulp (tan) for the doubles and 0.50 for
the floats); Annex F's special values are exact: sin(+-0) = +-0, cos(+-0) = 1, tan(+-0) = +-0, sin, cos, and tan of an
infinity are NaN, asin and acos outside -1 to 1 are NaN, asin(+-1) and acos(+-1) are exact, atan(+-inf) = +-pi/2, and
atan2's cases for zeros and infinities. On Linux, where `refined run` calls glibc's libm through ctypes, the executable's
results differ from glibc's by at most 2 ulp (both are within 1 ulp of the exact value; glibc's sinf and cosf are
ARM's optimized routines, whose method is not copied here, so the float forms are not bit-identical to them)."""
from __future__ import annotations

import math
import os
import re
import struct
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "suite"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "semanticscript", "runtime", "tools"))

import caselib  # noqa: E402
import cmathtriggen  # noqa: E402
import cmathtrigtour  # noqa: E402
import test_runtime_nolibc as nolibc  # noqa: E402

BOUND = 1.0
GLIBC_DIFFERENCE = 2.0

NAMES = {"sin", "cos", "tan", "asin", "acos", "atan", "atan2", "sinf", "cosf", "tanf", "asinf", "acosf", "atanf",
         "atan2f"}


def _to_float(text: str) -> float:
    return float(text)


def _bits64(x: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def _bits32(x: float) -> int:
    return struct.unpack("<I", struct.pack("<f", x))[0]


def _atan2_special(y: float, x: float):
    """Annex F's value, or None when the pair is not one of its zero or infinity cases."""
    if math.isnan(y) or math.isnan(x):
        return math.nan
    if y == 0:
        return math.copysign(math.pi, y) if math.copysign(1.0, x) < 0 else y
    if x == 0:
        return math.copysign(math.pi / 2, y)
    if math.isinf(y):
        if math.isinf(x):
            return math.copysign(0.75 * math.pi if x < 0 else 0.25 * math.pi, y)
        return math.copysign(math.pi / 2, y)
    if math.isinf(x):
        return math.copysign(math.pi if x < 0 else 0.0, y)
    return None


def _expected(base: str, args: tuple):
    """(kind, value): ('nan', None), ('exact', float), or ('ulp', Decimal) for one call of a function."""
    if base == "atan2":
        y, x = args
        special = _atan2_special(y, x)
        if special is not None:
            return ("nan", None) if math.isnan(special) else ("exact", special)
        return "ulp", cmathtriggen.ref_atan2(y, x)
    (x,) = args
    if math.isnan(x):
        return "nan", None
    if base in ("sin", "cos", "tan"):
        if math.isinf(x):
            return "nan", None
        if x == 0:
            return "exact", {"sin": x, "cos": 1.0, "tan": x}[base]
    elif base in ("asin", "acos"):
        if abs(x) > 1:
            return "nan", None
        if base == "asin" and x == 0:
            return "exact", x
        if base == "asin" and abs(x) == 1:
            return "exact", math.copysign(math.pi / 2, x)
        if base == "acos" and x == 1:
            return "exact", 0.0
        if base == "acos" and x == -1:
            return "exact", math.pi
    elif base == "atan":
        if x == 0:
            return "exact", x
        if math.isinf(x):
            return "exact", math.copysign(math.pi / 2, x)
    return "ulp", cmathtriggen.REFERENCE[base](x)


def _output_by_function(lines: list[str]) -> dict:
    out, at = {}, 0
    for name in cmathtrigtour.expected_names():
        count = len(cmathtrigtour.inputs(name))
        out[name] = lines[at:at + count]
        at += count
    assert at == len(lines), (at, len(lines))
    return out


def _check_function(name: str, got: list[str]) -> float:
    """Hold one function's results to the bound; gives the worst error in ulps."""
    single = name.endswith("f")
    base = name[:-1] if single else name
    args_list = cmathtrigtour.inputs(name)
    assert len(got) == len(args_list), name
    worst = 0.0
    for args, text in zip(args_list, got):
        args = args if isinstance(args, tuple) else (args,)
        value = _to_float(text)
        kind, want = _expected(base, args)
        if kind == "nan":
            assert math.isnan(value), (name, args, text)
        elif kind == "exact":
            want = cmathtrigtour.narrow(want) if single else want
            assert not math.isnan(value) and _bits64(value) == _bits64(want), (name, args, text, want)
        else:
            error = cmathtriggen.ulp_error(value, want, single=single)
            assert error <= BOUND, (name, args, text, error)
            if single:
                assert cmathtrigtour.narrow(value) == value, (name, args, text)
            worst = max(worst, error)
    return worst


def _distance(a: float, b: float, single: bool) -> float:
    """The difference of two results in numbers between them (NaN is equal to NaN)."""
    if math.isnan(a) or math.isnan(b):
        return 0.0 if math.isnan(a) and math.isnan(b) else math.inf
    if a == b:
        return 0.0 if (a != 0 or math.copysign(1.0, a) == math.copysign(1.0, b)) else math.inf
    if math.isinf(a) or math.isinf(b):
        return math.inf
    bits = _bits32 if single else _bits64
    top = 1 << (31 if single else 63)

    def ordered(x: float) -> int:
        n = bits(x)
        return -(n & (top - 1)) if n & top else n

    return abs(ordered(a) - ordered(b))


@pytest.fixture(scope="module")
def tour(tmp_path_factory):
    """The tour built as an executable with no C library, and what it printed."""
    project = str(tmp_path_factory.mktemp("cmathtrigtour") / "cmathtrigtour")
    cmathtrigtour.write_project(project)
    caselib.approve(project)
    exe = os.path.join(project, "program.exe")
    built = nolibc._build(project, exe)
    assert built.returncode == 0, built.stdout + built.stderr
    nolibc.assert_no_libc(exe)
    ran = nolibc._exe(exe, project)
    assert ran.returncode == 0 and ran.stderr == "", ran.stderr
    return project, ran


@nolibc.needs_windows_cc
def test_c_trigonometry_is_within_one_ulp_of_the_exact_value(tour):
    """The executable, which holds no C library, gives sin, cos, tan, asin, acos, atan, atan2 and their f forms to within
    1 ulp of the exact value over the tour's special values and sweeps (2^-60 to 1.8e308), and exactly where Annex F says."""
    _project, ran = tour
    by_function = _output_by_function(ran.stdout.splitlines())
    assert set(by_function) == NAMES
    for name, got in by_function.items():
        _check_function(name, got)


@nolibc.needs_windows_cc
def test_c_trigonometry_matches_glibc_on_linux(tour):
    """On Linux `refined run` calls glibc's libm through ctypes: every result of the executable is within 2 ulp of
    glibc's (both are within 1 ulp of the exact value), special values and NaN included."""
    if nolibc.WINDOWS:
        pytest.skip("glibc's libm is only called by `refined run` on Linux")
    project, ran = tour
    jit = nolibc._jit(project)
    assert jit.returncode == 0, jit.stderr
    mine = _output_by_function(ran.stdout.splitlines())
    theirs = _output_by_function(jit.stdout.splitlines())
    for name in NAMES:
        single = name.endswith("f")
        for args, a, b in zip(cmathtrigtour.inputs(name), mine[name], theirs[name]):
            d = _distance(_to_float(a), _to_float(b), single)
            assert d <= GLIBC_DIFFERENCE, (name, args, a, b, d)


def test_c_trigonometry_table_names_glibc_functions():
    """The `abi library` operations of cmathtrig.sem are exactly the names this test lists, and on Linux each is a name
    glibc's libm exports."""
    path = os.path.join(nolibc.RUNTIME, "cmathtrig.sem")
    with open(path, encoding="utf-8") as fh:
        names = set(re.findall(r'^\w+ abi library "(\w+)"(?: variadic)?$', fh.read(), re.M))
    assert names == NAMES, (names - NAMES, NAMES - names)
    if not nolibc.WINDOWS and nolibc.PLATFORM:
        import ctypes
        import ctypes.util
        libm = ctypes.CDLL(ctypes.util.find_library("m") or "libm.so.6")
        assert [n for n in sorted(names) if not hasattr(libm, n)] == []
