"""The runtime's time.h (module `ctime`), against the models of tests/ctimetour.py and glibc.

time, clock, difftime, mktime, gmtime, gmtime_r, localtime, localtime_r, asctime, asctime_r, ctime, ctime_r, strftime,
and timespec_get, each as glibc behaves in the C locale: struct tm is glibc's 56 bytes (nine ints, tm_gmtoff, tm_zone),
gmtime and localtime give one static struct tm, the time zone is found as tzset finds it (TZ as a TZif file under
/usr/share/zoneinfo or as a POSIX string, else /etc/localtime on Linux and the system's zone on Windows), mktime runs
gnulib's search (the one glibc runs, with the offset it found last), and strftime writes every C11 conversion, glibc's
extensions, and its flags and widths.

Checks: the executable with no libc prints what the Python models compute for TZ set to each of three zones (UTC and
two POSIX rules, one in each hemisphere); on Linux it prints what `refined run` prints, which calls glibc, under those
zones and under TZif files and the system's zone; the library's table holds exactly these names, each exported by
glibc; and the models are pinned to Python's datetime, calendar, and time modules where those have the function.
"""
from __future__ import annotations

import calendar
import datetime
import difflib
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_runtime_nolibc as base  # noqa: E402
import ctimetour  # noqa: E402

caselib = base.caselib
RUNTIME = base.RUNTIME
NAMES = set(ctimetour.NAMES)
MODELLED = ["UTC", "EST5EDT,M3.2.0,M11.1.0", "AEST-10AEDT,M10.1.0,M4.1.0/3"]
BUILT: dict = {}


def _environment(tz):
    env = dict(os.environ)
    env.pop("TZ", None)
    if tz is not None:
        env["TZ"] = tz
    return env


def _run_exe(exe: str, project: str, tz):
    return subprocess.run([exe], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=project,
                          env=_environment(tz), timeout=300)


def _run_jit(project: str, tz):
    return subprocess.run([sys.executable, caselib.COMPILER, "run", project, "--no-cache"], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", cwd=project, env=_environment(tz),
                          timeout=900)


def _tour(tmp_path_factory, spec: str):
    """The tour program for a zone, built once as an executable with no libc."""
    if spec not in BUILT:
        folder = tmp_path_factory.mktemp("ctimetour")
        project = str(folder / "ctimetour")
        ctimetour.write_project(project, spec)
        caselib.approve(project)
        exe = os.path.join(project, "program.exe")
        built = base._build(project, exe)
        assert built.returncode == 0, built.stdout + built.stderr
        base.assert_no_libc(exe)
        BUILT[spec] = (project, exe)
    return BUILT[spec]


def _same(got: str, want: str) -> None:
    if got != want:
        diff = list(difflib.unified_diff(want.splitlines(), got.splitlines(), "expected", "got", lineterm="", n=2))
        raise AssertionError("\n".join(diff[:400]))


@base.needs_windows_cc
@pytest.mark.parametrize("spec", MODELLED)
def test_time_functions_match_the_models(spec, tmp_path_factory):
    """Built as an executable with no libc, the tour prints for TZ=<spec> exactly what the models compute: gmtime and
    localtime over boundary times (negative, 1900, year 1 and 9999, 2038, the last year an int holds, every daylight
    change and a second either side), mktime over out-of-range fields, leap days, gaps, and overlaps, asctime and ctime,
    and strftime of every conversion and flag over many struct tm and buffer sizes. On Linux it prints what `refined
    run` prints, which is glibc's answer."""
    project, exe = _tour(tmp_path_factory, spec)
    ran = _run_exe(exe, project, spec)
    assert ran.returncode == 0 and ran.stderr == "", ran.stderr
    _same(ran.stdout, ctimetour.expected(spec))
    if not base.WINDOWS:
        jit = _run_jit(project, spec)
        assert (jit.returncode, jit.stderr) == (0, ""), jit.stderr
        _same(jit.stdout, ran.stdout)


@pytest.mark.skipif(base.WINDOWS or not base.PLATFORM, reason="the zones are glibc's on Linux")
def test_zone_files_and_the_system_zone_match_glibc(tmp_path_factory):
    """The tour under TZ naming TZif files, under TZ unset (/etc/localtime), and under a few spellings glibc takes (a
    leading colon, an empty TZ, a name with no file) prints what `refined run` prints."""
    project, exe = _tour(tmp_path_factory, "UTC")
    zones = [None, "", ":UTC", "UTC", "Nowhere/Nothing", "<+03>-3", "PST8PDT", "EST", "GMT0BST,M3.5.0/1,M10.5.0"]
    zones += [z for z in ctimetour.FILE_ZONES if os.path.exists("/usr/share/zoneinfo/" + z)]
    zones += [":" + z for z in ctimetour.FILE_ZONES if os.path.exists("/usr/share/zoneinfo/" + z)]
    for tz in zones:
        ran = _run_exe(exe, project, tz)
        assert ran.returncode == 0 and ran.stderr == "", (tz, ran.stderr)
        jit = _run_jit(project, tz)
        assert (jit.returncode, jit.stderr) == (0, ""), (tz, jit.stderr)
        try:
            _same(jit.stdout, ran.stdout)
        except AssertionError as error:
            raise AssertionError(f"TZ={tz!r}\n{error}")


def test_ctime_table_names_glibc_functions():
    """The `abi library` names of the module are the tour's list, and on Linux each is exported by glibc."""
    with open(os.path.join(RUNTIME, "ctime.sem"), encoding="utf-8") as fh:
        names = set(re.findall(r'^\w+ abi library "(\w+)"(?: variadic)?$', fh.read(), re.M))
    assert names == NAMES, (names - NAMES, NAMES - names)
    if not base.WINDOWS and base.PLATFORM:
        import ctypes
        import ctypes.util
        glibc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6")
        assert [n for n in sorted(names) if not hasattr(glibc, n)] == []


def test_models_agree_with_python():
    """The tour's expected values come from models; pin them to Python's datetime, calendar, and time modules where
    those have the function, over a sweep of times (negative, 1900, 2038 and after, leap years)."""
    ctimetour.check_calendar()
    times = ctimetour.SWEEP + [0, -1, 951782400, 2147483648, 4102444800, -2208988800, 253402300799, -62135596800,
                               1709164800, 1078012800, 4107542400]
    zone = ctimetour.Zone("UTC0")
    for t in times:
        moment = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=t)
        tm = ctimetour.gmtime(t)
        assert tm.ints()[:8] == [moment.second, moment.minute, moment.hour, moment.day, moment.month - 1,
                                 moment.year - 1900, (moment.weekday() + 1) % 7, moment.timetuple().tm_yday - 1], t
        fields = ctimetour.Tm(tm.sec, tm.min, tm.hour, tm.mday, tm.mon, tm.year, 0, 0, -1)
        assert zone.mktime(fields) == calendar.timegm(moment.timetuple()) == t
        assert fields.ints()[:8] == tm.ints()[:8]
        # strftime: the conversions every C library has, as datetime writes them
        fmt = "%a %A %b %B %d %H %I %j %m %M %p %S %U %w %W %y %Y %%"
        want = moment.strftime(fmt) if moment.year >= 1900 else None
        if want is not None:
            assert ctimetour.strftime(fmt, tm)[0] == want, (t, want)
        assert ctimetour.asctime(tm) == (moment.strftime("%a %b ") + f"{moment.day:2d}" + moment.strftime(" %H:%M:%S %Y\n")
                                         if moment.year >= 1900 else ctimetour.asctime(tm))
    # the ISO week conversions against isocalendar
    for t in times:
        moment = datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=t)
        tm = ctimetour.gmtime(t)
        year, week, weekday = moment.isocalendar()
        text = ctimetour.strftime("%G %V %u %g", tm)[0]
        assert text == f"{year} {week:02d} {weekday} {year % 100:02d}", (t, text)
    # a rule zone against Python's own date arithmetic: the second Sunday of March at 02:00 local
    north = ctimetour.Zone("EST5EDT,M3.2.0,M11.1.0")
    assert north.at(1710054000)[:2] == (-14400, 1) and north.at(1710053999)[:2] == (-18000, 0)
    assert north.at(1730613599)[:2] == (-14400, 1) and north.at(1730613600)[:2] == (-18000, 0)
    south = ctimetour.Zone("AEST-10AEDT,M10.1.0,M4.1.0/3")
    assert south.at(1712419199)[:2] == (39600, 1) and south.at(1712419200)[:2] == (36000, 0)
    start = calendar.timegm((2024, 10, 5, 16, 0, 0))
    assert south.at(start - 1)[:2] == (36000, 0) and south.at(start)[:2] == (39600, 1)
