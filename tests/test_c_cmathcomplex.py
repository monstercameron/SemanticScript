"""The runtime's complex functions (D-153, D-175): complex.h for double complex and float complex, written in
SemanticScript (semanticscript/runtime/tools/cmathcomplex.dsl), bound through `ffi.open("c")` in an executable with no C
library. The tour (tests/cmathcomplextour.py) is also the first end-to-end test of the complex ABI: a record of two
Float64 or two Float32 crosses the foreign boundary by value as C's `double complex` and `float complex`.

The bounds this module guarantees, held by the tests below (the doubles' own ulp, or the floats' own, measured against
an exact reference of decimals in tools/cmathcomplexgen.py, and not against any libm; the bound of a function is the
number of ulps each part may differ by, `BOUND` there; a float function is within that plus 1 ulp of the float, since
it computes in double and rounds each part once):
- cabs, carg, creal, cimag, conj, cproj: 1, 1, exact, exact, exact, exact;
- clog, csqrt: 2; cexp: 3; csin, ccos, csinh, ccosh, casin, cacos, casinh, cacosh, catanh: 4; ctan, ctanh, catan: 6
  (measured worst over the tour: 3 ulp, ctan, ctanh, and catan; 2 for the others, 1 for clog, csqrt, cabs, carg);
- cpow: not per part; the error of the result as a whole is at most (6 + 2 |y log x|) * 2^-53 times its magnitude (the
  logarithm's rounding is multiplied by y).
Annex G's special values are exact: signed zeros, infinities and NaN in each part, the branch cuts on the right side
of a signed zero (the reference perturbs a zero part by 1e-400 of its sign), and where Annex G leaves a sign open the
test accepts either. errno is left as the caller had it. On Linux, where `refined run` calls glibc's libm through ctypes,
the executable's results differ from glibc's by at most GLIBC_DIFFERENCE ulps per part (glibc's own errors for these
functions are a few ulps, and its cpow, casin and the like use other formulas)."""
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
import cmathcomplexgen as G  # noqa: E402
import cmathcomplextour as T  # noqa: E402
import test_runtime_nolibc as nolibc  # noqa: E402

GLIBC_DIFFERENCE = 24.0
NAMES = set(G.ALL_NAMES)


def _to_float(text: str) -> float:
    return float(text)


def _bits64(x: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", x))[0]


def _output_by_function(lines: list[str]) -> dict:
    out, at = {}, 0
    for name in T.expected_names():
        count = len(T.inputs(name)) * T.lines_per_call(name)
        out[name] = lines[at:at + count]
        at += count
    assert at == len(lines), (at, len(lines))
    return out


def _check_part(name, args, which, want, value, single, worst):
    """Hold one part of one result to its expectation; record the error in ulps in worst[name]."""
    if isinstance(want, float) and math.isnan(want):
        want = "N"
    if want == "A":
        return
    if want == "N":
        assert math.isnan(value), (name, args, which, value)
    elif want == "Z":
        assert value == 0, (name, args, which, value)
    elif want == "I":
        assert math.isinf(value), (name, args, which, value)
    elif isinstance(want, tuple):
        _kind, expected, tol = want
        assert abs(value - expected) <= tol, (name, args, which, value, expected, tol)
        if tol and not name.startswith("cpow"):
            ulp = G.ulp_of(expected, single)
            if ulp:
                worst[name] = max(worst.get(name, 0.0), abs(value - expected) / ulp)
    else:
        if single:
            want = G.narrow(want)
        assert not math.isnan(value), (name, args, which, value, want)
        assert _bits64(value) == _bits64(want), (name, args, which, value, want)


def _check_function(name: str, got: list[str], worst: dict) -> None:
    single = name.endswith("f")
    base = name[:-1] if single else name
    kind = T.kind_of(name)
    args_list = T.inputs(name)
    per = T.lines_per_call(name)
    assert len(got) == len(args_list) * per, name
    for k, args in enumerate(args_list):
        texts = got[k * per:(k + 1) * per]
        if kind == "Binary":
            (x, y), w = args
        else:
            (x, y), w = args, None
        want = G.expectation(base, x, y, w, single)
        if want is None:
            continue
        values = [_to_float(t) for t in texts]
        if kind == "Real":
            _check_part(name, args, "value", want[0], values[0], single, worst)
        else:
            _check_part(name, args, "real", want[0], values[0], single, worst)
            _check_part(name, args, "imag", want[1], values[1], single, worst)


@pytest.fixture(scope="module")
def tour(tmp_path_factory):
    """The tour built as an executable with no C library, and what it printed."""
    project = str(tmp_path_factory.mktemp("cmathcomplextour") / "cmathcomplextour")
    T.write_project(project)
    caselib.approve(project)
    exe = os.path.join(project, "program.exe")
    built = nolibc._build(project, exe)
    assert built.returncode == 0, built.stdout + built.stderr
    nolibc.assert_no_libc(exe)
    ran = nolibc._exe(exe, project)
    assert ran.returncode == 0 and ran.stderr == "", ran.stderr
    return project, ran


@nolibc.needs_windows_cc
def test_c_complex_is_within_its_bounds_of_the_exact_value(tour):
    """The executable, which holds no C library, gives the 44 functions of complex.h within the stated bounds of the
    exact value over the tour's special grid and sweeps, and as Annex G says for infinities, NaN and signed zeros."""
    _project, ran = tour
    by_function = _output_by_function(ran.stdout.splitlines())
    assert set(by_function) == NAMES
    worst: dict = {}
    for name, got in by_function.items():
        _check_function(name, got, worst)
    if os.environ.get("CMATHCOMPLEX_REPORT"):
        for name in sorted(worst):
            print(f"{name:10} worst {worst[name]:.2f} ulp")


@nolibc.needs_windows_cc
def test_c_complex_matches_glibc_on_linux(tour):
    """On Linux `refined run` calls glibc's libm through ctypes: every result of the executable is within
    GLIBC_DIFFERENCE ulps of glibc's per part, NaN, infinities and zeros equal where the value is not a NaN's."""
    if nolibc.WINDOWS:
        pytest.skip("glibc's libm is only called by `refined run` on Linux")
    project, ran = tour
    jit = nolibc._jit(project)
    assert jit.returncode == 0, jit.stderr
    mine = _output_by_function(ran.stdout.splitlines())
    theirs = _output_by_function(jit.stdout.splitlines())
    for name in NAMES:
        single = name.endswith("f")
        base = name[:-1] if single else name
        for k, (a, b) in enumerate(zip(mine[name], theirs[name])):
            x, y = _to_float(a), _to_float(b)
            if math.isnan(x) or math.isnan(y):
                # a part glibc leaves a NaN may be one here only where the annex says NaN
                assert math.isnan(x) == math.isnan(y) or base == "cpow", (name, k, a, b)
                continue
            if math.isinf(x) or math.isinf(y) or x == 0 or y == 0:
                if base == "cpow":
                    continue
                assert x == y or abs(x) < 1e-300 and abs(y) < 1e-300, (name, k, a, b)
                continue
            spacing = G.ulp_of(y, single)
            assert abs(x - y) <= GLIBC_DIFFERENCE * spacing or base == "cpow" and abs(x - y) <= 1e-12 * abs(y), (name, k, a, b)


def test_c_complex_table_names_glibc_functions():
    """The `abi library` operations of cmathcomplex.sem are exactly the names this test lists, and on Linux each is a
    name glibc's libm exports."""
    path = os.path.join(nolibc.RUNTIME, "cmathcomplex.sem")
    with open(path, encoding="utf-8") as fh:
        names = set(re.findall(r'^\w+ abi library "(\w+)"(?: variadic)?$', fh.read(), re.M))
    assert names == NAMES, (names - NAMES, NAMES - names)
    if not nolibc.WINDOWS and nolibc.PLATFORM:
        import ctypes
        import ctypes.util
        libm = ctypes.CDLL(ctypes.util.find_library("m") or "libm.so.6")
        assert [n for n in sorted(names) if not hasattr(libm, n)] == []


def test_c_complex_generated_blocks_are_current():
    """The wrappers and the polynomial of cmathcomplex.dsl are what cmathcomplexgen.py writes (the unit tests block is
    checked by running it, since the reference is slow)."""
    with open(os.path.join(os.path.dirname(HERE), "semanticscript", "runtime", "tools", "cmathcomplex.dsl"),
              encoding="utf-8") as fh:
        text = fh.read()
    for name in ("polynomials", "wrappers"):
        m = re.search(rf"## @generated {name}\n(.*?)## @end {name}\n", text, re.S)
        assert m and m.group(1) == G.BLOCKS[name](), name
