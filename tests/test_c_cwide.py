"""The wide-character and multibyte C functions of the runtime in SemanticScript (module `cwide`, D-153): wctype.h,
wchar.h, stdlib.h's multibyte functions, and uchar.h, as glibc behaves in the C locale.

tests/cwidetour.py writes a program that calls them through `ffi`. It is built with the runtime and no libc and must
print what the Python model of glibc says (classes, case, strings, number parsing, multibyte conversions, errno, end
pointers); on Linux, where `refined run` calls glibc itself through ctypes, it must print exactly what that prints.
"""
from __future__ import annotations

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "suite"))
import caselib  # noqa: E402
import cwidetour  # noqa: E402
from test_runtime_nolibc import PLATFORM, WINDOWS, RUNTIME, _build, _exe, _jit, assert_no_libc  # noqa: E402

pytestmark = pytest.mark.skipif(not PLATFORM, reason="the runtime in SemanticScript links on Windows (MinGW) "
                                "and x86_64 Linux")

CWIDE = {
    # wctype.h
    "iswalnum", "iswalpha", "iswblank", "iswcntrl", "iswdigit", "iswgraph", "iswlower", "iswprint", "iswpunct",
    "iswspace", "iswupper", "iswxdigit", "towlower", "towupper", "wctype", "iswctype", "wctrans", "towctrans",
    # wchar.h
    "wcslen", "wcsnlen", "wcscpy", "wcsncpy", "wcscat", "wcsncat", "wcscmp", "wcsncmp", "wcschr", "wcsrchr", "wcsstr",
    "wcsspn", "wcscspn", "wcspbrk", "wcstok", "wcsdup", "wmemchr", "wmemcmp", "wmemcpy", "wmemmove", "wmemset",
    "wcstol", "wcstoll", "wcstoul", "wcstoull", "wcstod", "wcstof", "wcscoll", "wcsxfrm", "btowc", "wctob", "mbsinit",
    "mbrlen", "mbrtowc", "wcrtomb", "mbsrtowcs", "wcsrtombs",
    # stdlib.h
    "mblen", "mbtowc", "wctomb", "mbstowcs", "wcstombs",
    # uchar.h
    "mbrtoc16", "c16rtomb", "mbrtoc32", "c32rtomb",
}


def test_cwide_table_names_glibc_functions():
    """D-153: the module's `abi library` operations are the wide-character functions in scope, each under its C
    name and nothing else; on Linux every one is a name glibc exports."""
    with open(os.path.join(RUNTIME, "cwide.sem"), encoding="utf-8") as fh:
        names = set(re.findall(r'^\w+ abi library "(\w+)"(?: variadic)?$', fh.read(), re.M))
    assert names == CWIDE, (names - CWIDE, CWIDE - names)
    if not WINDOWS:
        import ctypes
        import ctypes.util
        glibc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6")
        assert [n for n in sorted(names) if not hasattr(glibc, n)] == []


def test_cwide_tour_model_is_consistent():
    """The Python model keeps its own books: every printed line has an expected line, and the sections are in order."""
    tour = cwidetour.build()
    assert tour.out and [i for i, _ in tour.sections] == sorted(i for i, _ in tour.sections)


def test_c_wide_library_matches_glibc(tmp_path):
    """The executable (no libc) prints what glibc gives in the C locale, as the Python model computes it; on Linux it
    prints exactly what `refined run` prints, which calls glibc itself. Where glibc could go either way (bytes 0x80
    to 0xFF) the comparison with glibc decides."""
    project = str(tmp_path / "cwidetour")
    tour = cwidetour.write_project(project)
    caselib.approve(project)
    exe = os.path.join(project, "program.exe")
    built = _build(project, exe)
    assert built.returncode == 0, built.stdout + built.stderr
    assert_no_libc(exe)
    ran = _exe(exe, project)
    assert ran.returncode == 0 and ran.stderr == "", ran.stderr
    want, got = tour.out, ran.stdout.splitlines()
    marks = tour.sections

    def where(i):
        name = [n for at, n in marks if at <= i]
        return name[-1] if name else ""
    bad = [(i, where(i), g, w) for i, (g, w) in enumerate(zip(got, want)) if g != w]
    assert len(got) == len(want) and bad == [], (len(got), len(want), bad[:20])
    if not WINDOWS:
        jit = _jit(project)
        assert jit.returncode == ran.returncode and jit.stderr == ran.stderr
        mine, theirs = ran.stdout.splitlines(), jit.stdout.splitlines()
        diff = [(i, where(i), a, b) for i, (a, b) in enumerate(zip(mine, theirs)) if a != b]
        assert len(mine) == len(theirs) and diff == [], (len(mine), len(theirs), diff[:20])
