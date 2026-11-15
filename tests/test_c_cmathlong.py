"""math.h's transcendental long double functions written in SemanticScript (the module `cmathlong`): sinl, cosl, tanl,
asinl, acosl, atanl, atan2l, expl, exp2l, expm1l, logl, log2l, log10l, log1pl, powl, cbrtl, hypotl, sinhl, coshl,
tanhl, asinhl, acoshl, atanhl, erfl, erfcl, tgammal, lgammal, lgammal_r, and fmal.

Three checks:
- the unit test (any machine): the module's `abiTest` runs 1,500 cases (tools/cmathlongtests.py computes each expected
  result with Python decimals at 170 digits, rounded to nearest even) on the double, x87, and binary128 layouts, whatever
  the machine, and then each `abi library` operation on the system's own long double; every result must be within the
  case's tolerance (1 ulp for the transcendental functions, 0 for fmal and the special values) of the correctly rounded
  value. Locally every result is the correctly rounded one;
- the Linux check (skipped elsewhere): tests/cprograms/long_math.c, which test_cprograms.py compiles against glibc and
  against the runtime's C library and compares byte for byte (it prints where each result is within a few ulps of a
  reference, and the `%La` bits otherwise, so glibc's own last-place differences do not show);
- the table check: the `abi library` names of the module are exactly the list here, and on Linux glibc's libm exports
  each.

The bounds the module guarantees: every function is within 1 ulp of the exact value on each layout (the method computes
on 320-bit numbers, so the error before the one rounding is about 2^-300, and the result is the correctly rounded one
except where the exact value lies that close to a rounding boundary); fmal is exactly rounded; Annex F's special
values are exact; lgammal near its zeros at negative arguments is correct to 2^-250 absolutely.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from test_runtime_nolibc import RUNTIME, WINDOWS, PLATFORM  # noqa: E402

EXPECTED_NAMES = {
    "sinl", "cosl", "tanl", "asinl", "acosl", "atanl", "atan2l",
    "expl", "exp2l", "expm1l", "logl", "log2l", "log10l", "log1pl", "powl", "cbrtl", "hypotl",
    "sinhl", "coshl", "tanhl", "asinhl", "acoshl", "atanhl",
    "erfl", "erfcl", "tgammal", "lgammal", "lgammal_r", "fmal",
}


def test_long_math_table_names_glibc_functions():
    """The module's `abi library` operations are exactly the functions of this list, each a name glibc exports
    (math.h's from libm)."""
    with open(os.path.join(RUNTIME, "cmathlong.sem"), encoding="utf-8") as fh:
        names = set(re.findall(r'^\w+ abi library "(\w+)"(?: variadic)?$', fh.read(), re.M))
    assert names == EXPECTED_NAMES, (names - EXPECTED_NAMES, EXPECTED_NAMES - names)
    if not WINDOWS and PLATFORM:
        import ctypes
        import ctypes.util
        glibc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6")
        libm = ctypes.CDLL(ctypes.util.find_library("m") or "libm.so.6")
        assert [n for n in sorted(names) if not hasattr(glibc, n) and not hasattr(libm, n)] == []


def test_long_math_unit_test_passes_on_all_three_layouts():
    """The module's `abiTest` (about 1,500 cases on the double, x87, and binary128 layouts, then every `abi library`
    operation on this system's own long double) passes in the runtime project, run under `refined run-one-test`."""
    env = {**os.environ, "PYTHONPATH": os.path.join(os.path.dirname(HERE), "semanticscript", "compiler")}
    done = subprocess.run([sys.executable, "-m", "refined", "run-one-test", RUNTIME, "cmathlong.abiTest"],
                          capture_output=True, text=True, env=env, timeout=1800)
    last = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else ""
    assert '"status": "pass"' in last, (done.stdout[-2000:], done.stderr[-2000:])


def test_long_math_sources_are_generated():
    """cmathlong.dsl is what tools/cmathlonggen.py writes, so the module can be regenerated from the generator alone
    (the table of cases takes minutes, so this compares only the generated operations, not the test table)."""
    tools = os.path.join(RUNTIME, "tools")
    sys.path.insert(0, tools)
    try:
        import cmathlongabi
    finally:
        sys.path.pop(0)
    cmathlongabi.build_ops()
    from cmathlongbuild import assign_effects, ALL
    assign_effects(ALL)
    with open(os.path.join(tools, "cmathlong.dsl"), encoding="utf-8") as fh:
        dsl = fh.read()
    body = (chr(10) + chr(10)).join(o.render() for o in ALL)
    assert body in dsl
