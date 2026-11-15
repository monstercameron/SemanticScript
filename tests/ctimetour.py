"""A program that calls the runtime's time.h functions through `ffi` and prints what each gives (module `ctime`).

tests/test_c_ctime.py builds it with the runtime in SemanticScript, requires what it prints to be what `expected()`
computes here from models written in Python (the calendar by Python's own date arithmetic where it has it, POSIX time
zone rules, glibc's strftime conversions, and gnulib's mktime search that glibc uses), and on Linux requires it to print
what `refined run` prints, which calls glibc. The same program runs under several TZ values (ZONES).

Every struct tm is compared with the model's by memcmp (the nine ints, then tm_gmtoff), and printed as 0 for equal;
text (strftime, asctime, ctime) is written with puts, which glibc's and the runtime's stdout both buffer as one stream,
so each puts is followed by fflush(NULL). Ambiguous mktime cases (a time inside a spring-forward gap or twice at a
fall-back) depend on the offset the previous call found, which the models keep as glibc does; they are in the tour.
"""
from __future__ import annotations

import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "docs", "refined-examples", "stage0", "tools"))

NAMES = ["time", "clock", "difftime", "mktime", "gmtime", "gmtime_r", "localtime", "localtime_r", "asctime",
         "asctime_r", "ctime", "ctime_r", "strftime", "timespec_get"]

# the TZ values the tour runs under (None leaves TZ unset: the system's zone, glibc's own answer on Linux)
ZONES = ["UTC", "EST5EDT,M3.2.0,M11.1.0", "<+0530>-5:30", "AEST-10AEDT,M10.1.0,M4.1.0/3", "PST8PDT"]
FILE_ZONES = ["America/New_York", "Europe/London", "Asia/Kolkata", "Australia/Sydney"]

INT_MIN, INT_MAX = -2 ** 31, 2 ** 31 - 1
EPOCH = datetime.date(1970, 1, 1).toordinal()

DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


# ---------------------------------------------------------------- the calendar

def is_leap(y: int) -> bool:
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_from_civil(y: int, m: int, d: int) -> int:
    """Days from 1970-01-01 by counting whole years, then the months of the year (not the algorithm the library uses)."""
    yy = y - 1
    days = 365 * yy + yy // 4 - yy // 100 + yy // 400
    cumulative = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    days += cumulative[m - 1] + (1 if m > 2 and is_leap(y) else 0) + d
    return days - 719163  # the proleptic Gregorian day number of 1970-01-01 is 719163


def civil_from_days(days: int):
    y = 1970 + (days * 400) // 146097
    while days_from_civil(y + 1, 1, 1) <= days:
        y += 1
    while days_from_civil(y, 1, 1) > days:
        y -= 1
    rest = days - days_from_civil(y, 1, 1)
    lengths = [31, 29 if is_leap(y) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    for m, n in enumerate(lengths):
        if rest < n:
            return y, m + 1, rest + 1
        rest -= n
    raise AssertionError


def check_calendar() -> None:
    for days in range(-800000, 800000, 997):
        ordinal = days + EPOCH
        if 1 <= ordinal <= 3652059:
            d = datetime.date.fromordinal(ordinal)
            assert civil_from_days(days) == (d.year, d.month, d.day), days
            assert days_from_civil(d.year, d.month, d.day) == days


class Tm:
    """A struct tm: the nine ints, tm_gmtoff, and the zone's name (None for a null tm_zone)."""
    FIELDS = ("sec", "min", "hour", "mday", "mon", "year", "wday", "yday", "isdst")

    def __init__(self, sec=0, min=0, hour=0, mday=1, mon=0, year=70, wday=4, yday=0, isdst=0, gmtoff=0, zone=None):
        self.sec, self.min, self.hour, self.mday, self.mon, self.year = sec, min, hour, mday, mon, year
        self.wday, self.yday, self.isdst, self.gmtoff, self.zone = wday, yday, isdst, gmtoff, zone

    def ints(self):
        return [getattr(self, f) for f in self.FIELDS]

    def copy(self):
        return Tm(*self.ints(), self.gmtoff, self.zone)


def break_down(t: int, offset: int):
    """The nine ints of a time with an offset, or None when the year does not fit an int."""
    if not -2 ** 62 <= t <= 2 ** 62:
        return None
    local = t + offset
    days, rest = divmod(local, 86400)
    y, m, d = civil_from_days(days)
    if not INT_MIN <= y - 1900 <= INT_MAX:
        return None
    return Tm(rest % 60, rest // 60 % 60, rest // 3600, d, m - 1, y - 1900, (days + 4) % 7,
              days - days_from_civil(y, 1, 1), 0, offset)


def gmtime(t: int):
    tm = break_down(t, 0)
    if tm:
        tm.zone = "GMT"
    return tm


# ---------------------------------------------------------------- time zones

def _nth_weekday(year: int, month: int, week: int, weekday: int) -> int:
    """Day number of the `week`th (5 is the last) `weekday` (0 Sunday) of a month."""
    first = days_from_civil(year, month, 1)
    shift = (weekday - (first + 4) % 7) % 7
    day = 1 + shift + 7 * (week - 1)
    length = [31, 29 if is_leap(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    while day > length:
        day -= 7
    return first + day - 1


class Zone:
    """A POSIX TZ string with rules Mm.w.d (and /time)."""

    def __init__(self, spec: str):
        import re
        self.spec = spec
        m = re.match(r"^(<[^>]+>|[A-Za-z]{3,})([-+]?[0-9:]+)(?:(<[^>]+>|[A-Za-z]{3,})([-+]?[0-9:]+)?(?:,M(\d+)\.(\d+)\.(\d+)"
                     r"(?:/(-?[0-9:]+))?,M(\d+)\.(\d+)\.(\d+)(?:/(-?[0-9:]+))?)?)?$", spec)
        assert m, spec
        self.std = m.group(1).strip("<>")
        self.std_off = -self._seconds(m.group(2))
        self.dst = m.group(3).strip("<>") if m.group(3) else None
        self.dst_off = (-self._seconds(m.group(4)) if m.group(4) else self.std_off + 3600) if self.dst else self.std_off
        if self.dst:
            if m.group(5):
                self.start = (int(m.group(5)), int(m.group(6)), int(m.group(7)),
                              self._seconds(m.group(8)) if m.group(8) else 7200)
                self.end = (int(m.group(9)), int(m.group(10)), int(m.group(11)),
                            self._seconds(m.group(12)) if m.group(12) else 7200)
            else:
                self.start, self.end = (3, 2, 0, 7200), (11, 1, 0, 7200)
        self.guess = 0  # mktime's static offset
        self.failed = False

    @staticmethod
    def _seconds(text: str) -> int:
        sign = -1 if text.startswith("-") else 1
        parts = [int(p) for p in text.lstrip("+-").split(":")]
        parts += [0] * (3 - len(parts))
        return sign * (parts[0] * 3600 + parts[1] * 60 + parts[2])

    def at(self, t: int):
        """(UTC offset, isdst, abbreviation) at a time: the rule of the time's UTC year."""
        if not self.dst:
            return self.std_off, 0, self.std
        year = civil_from_days(t // 86400)[0]
        start = _nth_weekday(year, self.start[0], self.start[1], self.start[2]) * 86400 + self.start[3] - self.std_off
        end = _nth_weekday(year, self.end[0], self.end[1], self.end[2]) * 86400 + self.end[3] - self.dst_off
        daylight = (t < end or t >= start) if start > end else (start <= t < end)
        return (self.dst_off, 1, self.dst) if daylight else (self.std_off, 0, self.std)

    def localtime(self, t: int):
        off, dst, name = self.at(t)
        tm = break_down(t, off)
        if tm:
            tm.isdst, tm.zone = dst, name
        return tm

    def mktime(self, tm: Tm):
        """gnulib's mktime search as glibc runs it, with the offset the last call found kept in `guess`."""
        isdst = tm.isdst
        mon_years, mon = divmod(tm.mon, 12)
        year = tm.year + 1900 + mon_years
        sec = min(max(tm.sec, 0), 59)
        requested = (days_from_civil(year, mon + 1, 1) + tm.mday - 1) * 86400 + tm.hour * 3600 + tm.min * 60 + sec

        def differ(a, b):
            return a >= 0 and b >= 0 and (a != 0) != (b != 0)
        t = t1 = t2 = requested + self.guess
        dst2 = 0
        probes = 6
        found = False
        while True:
            off, dst, _ = self.at(t)
            candidate = requested - off
            if candidate == t:
                break
            if t == t1 and t != t2 and ((dst2 <= dst) if isdst < 0 else differ(isdst, dst)):
                found = True
                break
            probes -= 1
            if probes == 0:
                self.failed = True
                return -1
            t1, t2, t, dst2 = t2, t, candidate, dst
        if not found and differ(isdst, dst):
            done = False
            delta = 601200
            while delta < 268828200 and not done:
                for direction in (-1, 1):
                    other = t + delta * direction
                    o_off, o_dst, _ = self.at(other)
                    if not differ(isdst, o_dst):
                        t = requested - o_off
                        done = True
                        break
                delta += 601200
            if not done:
                self.failed = True
                return -1
        self.guess = t - requested
        t += tm.sec - sec
        filled = self.localtime(t)
        for f in Tm.FIELDS:
            setattr(tm, f, getattr(filled, f))
        tm.gmtoff, tm.zone = filled.gmtoff, filled.zone
        return t


# ---------------------------------------------------------------- strftime (glibc, C locale)

def _iso_days(yday: int, wday: int) -> int:
    value = yday - wday + 4 + 378
    return yday - (value - 7 * (value // 7)) + 3


def iso_year_week(tm: Tm):
    year = tm.year + 1900
    days = _iso_days(tm.yday, tm.wday)
    if days < 0:
        year -= 1
        days = _iso_days(tm.yday + 365 + is_leap(year), tm.wday)
    else:
        d = _iso_days(tm.yday - (365 + is_leap(year)), tm.wday)
        if d >= 0:
            year += 1
            days = d
    return year, days // 7 + 1


COMPOSITES = {"c": "%a %b %e %H:%M:%S %Y", "D": "%m/%d/%y", "F": "%Y-%m-%d", "r": "%I:%M:%S %p", "R": "%H:%M",
              "T": "%H:%M:%S", "x": "%m/%d/%y", "X": "%H:%M:%S"}
E_OK, O_OK = "cCxXyY", "deHImMSuUVwWy"


def strftime(fmt: str, tm: Tm, size: int = 4096, mktime=None, tzname=("UTC", "UTC"), localtime=None):
    """glibc's strftime: (the text written, or None when it did not fit, and the bytes written so far)."""
    out = []
    total = [0]

    def add(piece: str, flags) -> bool:
        pad, width = flags["pad"], flags["width"]
        if flags["upper"]:
            piece = piece.upper()
        if flags["lower"]:
            piece = piece.lower()
        fill = max(width - len(piece), 0)
        if len(piece) + fill >= size - total[0]:
            return False
        out.append((("0" if pad == "0" else " ") * fill) + piece)
        total[0] += len(piece) + fill
        return True

    def number(value: int, digits: int, space: bool, flags) -> bool:
        pad = flags["pad"]
        if space and pad not in ("0", "-"):
            pad = "_"
        wanted = max(digits, flags["width"])
        text = str(abs(value))
        sign = "-" if value < 0 else ""
        if pad == "-":
            body = sign + text
        elif pad == "_":
            body = (sign + text).rjust(wanted)
        else:
            body = sign + text.rjust(wanted - len(sign), "0")
        return add(body, flags)

    def simple(c: str, flags) -> int:
        hour12 = tm.hour - 12 if tm.hour > 12 else (12 if tm.hour == 0 else tm.hour)
        if c in "aAbBh":
            flags["upper"] = flags["upper"] or flags["hash"]
            flags["lower"] = flags["lower"] and not flags["hash"]
        if c in "pZ":
            if flags["hash"]:
                flags["upper"], flags["lower"] = False, True
        if c == "P":
            flags["upper"], flags["lower"] = False, True
        if c == "a":
            return add(DAYS[tm.wday][:3] if 0 <= tm.wday <= 6 else "?", flags)
        if c == "A":
            return add(DAYS[tm.wday] if 0 <= tm.wday <= 6 else "?", flags)
        if c in "bh":
            return add(MONTHS[tm.mon][:3] if 0 <= tm.mon <= 11 else "?", flags)
        if c == "B":
            return add(MONTHS[tm.mon] if 0 <= tm.mon <= 11 else "?", flags)
        if c == "C":
            y = tm.year + 1900
            return number(int(y / 100) - (1 if int(y - 100 * int(y / 100)) < 0 else 0), 1, False, flags)
        if c == "d":
            return number(tm.mday, 2, False, flags)
        if c == "e":
            return number(tm.mday, 2, True, flags)
        if c == "G":
            return number(iso_year_week(tm)[0], 1, False, flags)
        if c == "g":
            return number(iso_year_week(tm)[0] % 100, 2, False, flags)
        if c == "H":
            return number(tm.hour, 2, False, flags)
        if c == "I":
            return number(hour12, 2, False, flags)
        if c == "j":
            return number(tm.yday + 1, 3, False, flags)
        if c == "k":
            return number(tm.hour, 2, True, flags)
        if c == "l":
            return number(hour12, 2, True, flags)
        if c == "m":
            return number(tm.mon + 1, 2, False, flags)
        if c == "M":
            return number(tm.min, 2, False, flags)
        if c == "n":
            return add("\n", flags)
        if c in "pP":
            return add("PM" if tm.hour > 11 else "AM", flags)
        if c == "s":
            copy = tm.copy()
            t = mktime(copy)
            if t == -1:
                again = localtime(-1)
                if again is None or any(getattr(copy, f) != getattr(again, f) for f in
                                        ("sec", "min", "hour", "mday", "mon", "year", "isdst")):
                    return True
            return number(t, 1, False, flags)
        if c == "S":
            return number(tm.sec, 2, False, flags)
        if c == "t":
            return add("\t", flags)
        if c == "u":
            return number((tm.wday - 1) % 7 + 1, 1, False, flags)
        if c == "U":
            return number(int((tm.yday - tm.wday + 7) / 7), 2, False, flags)
        if c == "V":
            return number(iso_year_week(tm)[1], 2, False, flags)
        if c == "w":
            return number(tm.wday, 1, False, flags)
        if c == "W":
            return number(int((tm.yday - (tm.wday - 1) % 7 + 7) / 7), 2, False, flags)
        if c == "y":
            return number(tm.year % 100, 2, False, flags)
        if c == "Y":
            return number(tm.year + 1900, 1, False, flags)
        if c == "z":
            if tm.isdst < 0:
                return True
            if not add("-" if tm.gmtoff < 0 else "+", flags):
                return False
            minutes = abs(tm.gmtoff) // 60
            return number(minutes // 60 * 100 + minutes % 60, 4, False, flags)
        if c == "Z":
            zone = tm.zone
            if not zone and tm.isdst >= 0:
                zone = tzname[1 if tm.isdst else 0]
            return add(zone or "", flags)
        if c == "%":
            return add("%", flags)
        return 2

    i = 0
    while i < len(fmt):
        flags = {"pad": "", "upper": False, "lower": False, "hash": False, "width": -1}
        if fmt[i] != "%":
            if not add(fmt[i], flags):
                return None, "".join(out)
            i += 1
            continue
        start = i
        i += 1
        while i < len(fmt) and fmt[i] in "_-0^#":
            if fmt[i] in "_-0":
                flags["pad"] = fmt[i]
            elif fmt[i] == "^":
                flags["upper"] = True
            else:
                flags["hash"] = True
            i += 1
        if i < len(fmt) and fmt[i].isdigit():
            flags["width"] = 0
            while i < len(fmt) and fmt[i].isdigit():
                flags["width"] = flags["width"] * 10 + int(fmt[i])
                i += 1
        modifier = ""
        if i < len(fmt) and fmt[i] in "EO":
            modifier = fmt[i]
            i += 1
        c = fmt[i] if i < len(fmt) else ""
        ok = not modifier or (modifier == "E" and c and c in E_OK) or (modifier == "O" and c and c in O_OK)
        status = 2
        if ok and c:
            if c in COMPOSITES:
                inner = {"pad": "", "upper": False, "lower": False, "hash": False, "width": -1}
                big = [""]
                saved = (list(out), total[0])
                out.clear()
                total[0] = -10 ** 9  # room without limit
                j = 0
                text = COMPOSITES[c]
                while j < len(text):
                    if text[j] == "%":
                        if not simple(text[j + 1], dict(inner)):
                            raise AssertionError
                        j += 2
                    else:
                        add(text[j], dict(inner))
                        j += 1
                piece = "".join(out)
                out[:] = saved[0]
                total[0] = saved[1]
                status = 1 if add(piece, flags) else 0
            else:
                result = simple(c, flags)
                status = 1 if result is True else (0 if result is False else 2)
        if status == 0:
            return None, "".join(out)
        if status == 2:
            piece = fmt[start:i + 1] if c else fmt[start:i]
            if not add(piece, flags):
                return None, "".join(out)
            i += 1 if c else 0
            if not c:
                break
            continue
        i += 1
    return "".join(out), "".join(out)


def asctime(tm: Tm):
    days = "SunMonTueWedThuFriSat"
    months = "JanFebMarAprMayJunJulAugSepOctNovDec"
    wday = days[tm.wday * 3:tm.wday * 3 + 3] if 0 <= tm.wday <= 6 else "???"
    mon = months[tm.mon * 3:tm.mon * 3 + 3] if 0 <= tm.mon <= 11 else "???"
    year = (tm.year + 1900 + 2 ** 31) % 2 ** 32 - 2 ** 31

    def two(v):
        return ("-" if v < 0 else "") + str(abs(v)).rjust(2, "0")
    text = f"{wday} {mon}{tm.mday:3d} {two(tm.hour)}:{two(tm.min)}:{two(tm.sec)} {year}\n"
    return text if len(text) < 26 else None


# ---------------------------------------------------------------- the cases

def _transitions(zone: "Zone", year: int):
    """The UTC times (to the second) at which a zone's offset changes in a year."""
    out = []
    start = datetime.date(year, 1, 1).toordinal() - EPOCH
    prev = zone.at(start * 86400 - 1)[0]
    for d in range(start, start + 366):
        for h in range(24):
            now = zone.at(d * 86400 + h * 3600)[0]
            if now != prev:
                out.append(d * 86400 + h * 3600)
                prev = now
    return out


def _all_transitions():
    out = []
    for spec in ("EST5EDT,M3.2.0,M11.1.0", "AEST-10AEDT,M10.1.0,M4.1.0/3"):
        for year in (2024, 2007, 1999):
            for t in _transitions(Zone(spec), year):
                out += [t - 1, t, t + 1]
    return out


def _min_time() -> int:
    return days_from_civil(1900 + INT_MIN, 1, 1) * 86400


def _max_time() -> int:
    return days_from_civil(1900 + INT_MAX + 1, 1, 1) * 86400 - 1


GM_TIMES = [0, 1, -1, 59, 86399, 86400, 951782400, 951868800, 1583020800, 1709164800, 1710055800, 1700000000,
            2147483647, 2147483648, 4102444800, -2208988800, -31536000, 253402300799, 253402300800, -62135596800,
            -62167219200, -62135596801, 32503680000, 1234567890, 951782399, 4107542399, 78840000000,
            _max_time(), _max_time() + 1, _min_time(), _min_time() - 1, 9223372036854775807, -9223372036854775808,
            4611686018427387904, 4611686018427387905]
LOCAL_TIMES = [0, 1700000000, 1720000000, 2147483647, -1, 4102444800, -2208988800, 1262304000, 1735689599, 1735689600,
               1230768000] + _all_transitions() + [_max_time() - 20000, _min_time() + 20000]

MKTIME_CASES = [
    ((0, 0, 12, 15, 5, 124), -1), ((30, 59, 23, 31, 11, 99), -1), ((0, 0, 0, 1, 0, 70), -1),
    ((59, 59, 23, 29, 1, 124), -1), ((0, 0, 0, 32, 0, 124), -1), ((0, 0, 0, 0, 2, 124), -1),
    ((0, 0, 25, 28, 1, 123), -1), ((70, 70, 70, 1, 13, 100), -1), ((0, 0, 0, 1, -1, 100), -1),
    ((-1, 0, 0, 1, 0, 100), -1), ((0, -1, 0, 1, 0, 100), -1), ((0, 0, 0, 1, 24, 100), -1),
    ((0, 0, 12, 10, 2, 124), -1), ((0, 0, 12, 3, 10, 124), -1), ((0, 0, 12, 1, 0, 0), -1),
    ((59, 59, 23, 31, 11, 137), -1), ((0, 0, 0, 1, 0, 1), -1), ((61, 0, 0, 1, 0, 100), -1),
    ((0, 0, 12, 15, 0, 124), 1), ((0, 0, 12, 15, 6, 124), 0), ((0, 0, 12, 15, 6, 124), 1), ((0, 0, 12, 15, 0, 124), 0),
    ((0, 0, 0, 1, 0, 100000), -1), ((0, 0, 0, 1, 0, -100000), -1), ((0, 0, 0, 1, 0, 2147483647), -1),
    ((0, 0, 0, 1, 0, -2147483648), -1), ((2147483647, 2147483647, 2147483647, 2147483647, 2147483647, 100), -1),
    ((0, 0, 0, 29, 1, 100), -1), ((0, 0, 0, 29, 1, 104), -1), ((0, 0, 0, 29, 1, 99), -1),
]
# inside a spring-forward gap and a fall-back overlap of the northern and the southern zone (they depend on the offset the
# previous call found, which the models keep)
AMBIGUOUS = [
    ((0, 30, 2, 10, 2, 124), -1), ((0, 30, 2, 10, 2, 124), 0), ((0, 30, 2, 10, 2, 124), 1),
    ((0, 30, 1, 3, 10, 124), -1), ((0, 30, 1, 3, 10, 124), 0), ((0, 30, 1, 3, 10, 124), 1),
    ((0, 30, 2, 7, 3, 124), -1), ((0, 30, 2, 7, 3, 124), 0), ((0, 30, 2, 7, 3, 124), 1),
    ((0, 30, 2, 6, 9, 124), -1), ((0, 30, 2, 6, 9, 124), 1), ((0, 30, 12, 15, 0, 124), -1),
]

ASCTIME_TMS = [(0, 0, 0, 1, 0, 70, 4, 0, 0), (59, 59, 23, 31, 11, 99, 5, 364, 0), (5, 4, 3, 9, 5, 124, 0, 160, 0),
               (0, 0, 0, 1, 0, 70, 7, 0, 0), (0, 0, 0, 1, 12, 70, -1, 0, 0), (-5, 0, 0, 1, 0, 70, 4, 0, 0),
               (0, 0, 0, 1, 0, 8100, 4, 0, 0), (0, 0, 0, 1, 0, 8099, 4, 0, 0), (0, 0, 0, 1, 0, -2000, 4, 0, 0),
               (123, 456, 789, 1000, 5, 70, 3, 0, 0), (0, 0, 0, 99, 0, 70, 3, 0, 0), (0, 0, 0, -9, 0, 70, 3, 0, 0),
               (0, 0, 0, 1, 0, 2147483647, 4, 0, 0)]

FORMATS = ["%Y-%m-%d %H:%M:%S", "%a %A %b %B %h", "%c", "%D|%F|%r|%R|%T|%x|%X", "%C %y %g %G %V %U %W %u %w %j",
           "%e|%k|%l|%I|%p|%P|%H|%M|%S", "%Z %z", "%%|%n|%t|", "%s", "%-d|%_d|%^a|%#b|%05e|%_5m|%10Y|%-H|%-j|%_j|%0e",
           "%Ey %Od %EY %OH %Ec %Ex %EX %EC %Om %OM %OS %Ou %OU %OV %Ow %OW %Oy", "%Q %E %Ed %Ea %O %Oa % %-", "plain text",
           "", "%10a|%-10a|%^B|%#Z|%^p|%#p|%^A|%#A|%^h", "%12c", "%15F|%-15F|%_15T", "%^c|%#c", "%3d|%03d|%_3d|%-3d",
           "%A, %d %B %Y", "%G-W%V-%u", "%y%m%d%H%M%S", "%1d|%2d|%0d|%6Y", "%%%", "%5%|%-5%", "%Z%Z%z%z"]
SIZES = [(0, "%Y"), (1, "%Y"), (4, "%Y"), (5, "%Y"), (8, "%Y-%m-%d"), (9, "%Y-%m-%d"), (3, "abc"), (4, "abc"),
         (20, "%c"), (24, "%c"), (25, "%c"), (10, "%A %B"), (11, "%A %B"), (6, "%10a"), (11, "%10a"), (12, "%10a")]
HAND_TMS = [  # (ints, gmtoff)
    ((5, 4, 3, 2, 1, 100, 0, 32, 0), 0), ((5, 4, 3, 2, 1, 100, 0, 32, 1), -14400), ((5, 4, 3, 2, 1, 100, 0, 32, -1), 0),
    ((70, 70, 25, 40, 12, -1900, 7, 366, 1), 3600), ((0, 0, 0, 1, 0, 70, 4, 0, 0), 0), ((0, 0, 12, 1, 5, 70, 1, 151, 0), 0),
    ((0, 0, 13, 31, 11, 99, 5, 364, 0), -19800), ((59, 59, 23, 1, 0, 123, 0, 0, 1), 34200), ((0, 0, 0, 29, 1, 124, 4, 59, 0), 0),
    ((0, 0, 0, 31, 11, 120, 4, 365, 0), 0), ((0, 0, 0, 1, 0, 121, 5, 0, 0), 0), ((0, 0, 0, 3, 0, 125, 5, 2, 0), 0),
    ((-1, -1, -1, -1, -1, -1, -1, -1, 0), 0), ((0, 0, 0, 1, 0, 70, 4, 0, 0), -45296), ((0, 0, 0, 1, 0, 70, 4, 0, 0), 45296),
]
STRFTIME_TIMES = [0, 1710055800, 1709164800, 951782400, 1735689599, 2147483648, -1, -2208988800, 1704067200, 1700000000]
def _sweep(count: int, seed: int):
    """Times from a fixed linear congruence: years 1900 to 2100 mostly, with leap days and the year ends among them."""
    out, state = [], seed
    for i in range(count):
        state = (state * 6364136223846793005 + 1442695040888963407) % 2 ** 64
        out.append(state % 6600000000 - 2300000000)
    for year in (1900, 1904, 1999, 2000, 2001, 2004, 2024, 2038, 2100):
        for month, day in ((2, 28), (3, 1), (12, 31)):
            out.append(days_from_civil(year, month, day) * 86400 + 86399)
    return out


SWEEP = _sweep(70, 12345)
SWEEP_FORMAT = "%a %A %b %B %d %H %I %j %m %M %p %S %U %w %W %y %Y %%"
DIFFTIMES = [(10, 5), (5, 10), (0, 0), (9223372036854775807, -9223372036854775808), (-9223372036854775808, 9223372036854775807),
             (1710055800, 951782400), (-1, 1), (9007199254740993, 0), (1, 9007199254740993)]


def tm_groups(tm: "Tm"):
    return (f"{tm.sec} {tm.min} {tm.hour} {tm.mday}", f"{tm.mon} {tm.year} {tm.wday} {tm.yday}", f"{tm.isdst}",
            f"{tm.gmtoff}")


def hand_tm(ints, gmtoff):
    return Tm(*ints, gmtoff=gmtoff)


# ---------------------------------------------------------------- the program

OPTYPES = '''optype PtrFunction "T f(T), one whole number in and out: mktime, gmtime, localtime, asctime, ctime, time"
  input value Int64 copied
  output Int64

optype Ptr2Function "T f(T, T): gmtime_r, localtime_r, asctime_r, ctime_r"
  input first Int64 copied
  input second Int64 copied
  output Int64

optype ClockFunction "clock_t clock(void)"
  output Int64

optype DiffFunction "double difftime(time_t, time_t)"
  input later Int64 copied
  input earlier Int64 copied
  output Float64

optype SpecFunction "int timespec_get(struct timespec *, int)"
  input spec Int64 copied
  input base Int32 copied
  output Int32

optype StrftimeFunction "size_t strftime(char *, size_t, const char *, const struct tm *)"
  input buffer Int64 copied
  input size Int64 copied
  input format Int64 copied
  input tm Int64 copied
  output Int64

optype AllocFunction "void *calloc(size_t, size_t)"
  input count Int64 copied
  input size Int64 copied
  output Int64

optype SetFunction "void *memset(void *, int, size_t)"
  input target Int64 copied
  input value Int32 copied
  input bytes Int64 copied
  output Int64

optype ScanFunction "int sscanf(const char *, const char *, void *, void *, void *, void *)"
  input text Int64 copied
  input format Int64 copied
  input first Int64 copied
  input second Int64 copied
  input third Int64 copied
  input fourth Int64 copied
  output Int32

optype PutsFunction "int puts(const char *)"
  input text Int64 copied
  output Int32

optype FlushFunction "int fflush(FILE *)"
  input stream Int64 copied
  output Int32

optype CompareFunction "int memcmp(const void *, const void *, size_t)"
  input left Int64 copied
  input right Int64 copied
  input bytes Int64 copied
  output Int32

instance PtrBinding "Binds a C function of one whole number" ffi.Function PtrFunction

instance Ptr2Binding "Binds a C function of two whole numbers" ffi.Function Ptr2Function

instance ClockBinding "Binds clock" ffi.Function ClockFunction

instance DiffBinding "Binds difftime" ffi.Function DiffFunction

instance SpecBinding "Binds timespec_get" ffi.Function SpecFunction

instance StrftimeBinding "Binds strftime" ffi.Function StrftimeFunction

instance AllocBinding "Binds calloc" ffi.Function AllocFunction

instance SetBinding "Binds memset" ffi.Function SetFunction

instance ScanBinding "Binds sscanf for four pointers" ffi.Function ScanFunction

instance PutsBinding "Binds puts" ffi.Function PutsFunction

instance FlushBinding "Binds fflush" ffi.Function FlushFunction

instance CompareBinding "Binds memcmp" ffi.Function CompareFunction
'''

SYMBOLS = {"time": "time", "clock": "clock", "difftime": "difftime", "mktime": "mktime", "gmtime": "gmtime",
           "gmtimeR": "gmtime_r", "localtime": "localtime", "localtimeR": "localtime_r", "asctime": "asctime",
           "asctimeR": "asctime_r", "ctime": "ctime", "ctimeR": "ctime_r", "strftime": "strftime",
           "timespecGet": "timespec_get", "calloc": "calloc", "memset": "memset", "sscanf": "sscanf", "puts": "puts",
           "fflush": "fflush", "memcmp": "memcmp"}
# the type of each binding, in the order main binds them
BINDINGS = [("time", "Ptr"), ("clock", "Clock"), ("difftime", "Diff"), ("mktime", "Ptr"), ("gmtime", "Ptr"),
            ("gmtimeR", "Ptr2"), ("localtime", "Ptr"), ("localtimeR", "Ptr2"), ("asctime", "Ptr"), ("asctimeR", "Ptr2"),
            ("ctime", "Ptr"), ("ctimeR", "Ptr2"), ("strftime", "Strftime"), ("timespecGet", "Spec"),
            ("calloc", "Alloc"), ("memset", "Set"), ("sscanf", "Scan"), ("puts", "Puts"), ("fflush", "Flush"),
            ("memcmp", "Compare")]

# the area calloc gives: where each thing lives
TM_IN, TM_EXP, TM_OUT, TEXT, FORMAT_AT, BUF, CELL_T, CELL_U, SPEC_AT = 256, 320, 384, 1024, 2048, 4096, 8192, 8208, 8256
SCAN4, SCAN1, SCANL = 1280, 1296, 1312

HELPERS = '''op say "Write a line"
  input text String borrowed
  effect write console.stdout
  uses stdoutWriter
:begin
  write: console.writeLine(text) ~
  return

op sayNumber "Write a whole number on a line"
  input value Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  write: console.writeIntegerLine(value) ~
  return

op sayDouble "Write a double on a line, as repr writes it"
  input value Float64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  write: console.writeFloatLine(value) ~
  return

op sayNull "Write 1 for an address that is not 0, else 0"
  input value Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  when value == 0 nullValue someValue
:nullValue
  sayNumber(0)
  return
:someValue
  sayNumber(1)
  return

op sayEqual "Write 1 when two whole numbers are equal, else 0"
  input left Int64 copied
  input right Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  when left == right equalCase unequalCase
:equalCase
  sayNumber(1)
  return
:unequalCase
  sayNumber(0)
  return

op putText "Write a text and a 0 byte at an address, through memset"
  input setter SetFunction copied
  input base Int64 copied
  input text String borrowed
  let at Int64 0 mut
:begin
  length = string.byteLength(text)
  goto each
:each loop=while max=length
  when at >= length finish next
:next in=each
  letter = string.byteAtOrTrap(text, at)
  code = convert.int64ToInt32(convert.byteToInt64(letter))
  calc target = base + at
  put: unused = *setter(target, code, one=1)
  calc at := at + 1
  goto each
:finish
  calc end = base + length
  putEnd: unusedEnd = *setter(end, zero32=0, oneEnd=1)
  return

op loadTm "Set a struct tm at an address from four groups of numbers: the nine ints (sec min hour mday / mon year wday yday / isdst) and tm_gmtoff; tm_zone is 0"
  input setter SetFunction copied
  input scanner ScanFunction copied
  input area Int64 copied
  input tm Int64 copied
  input first String borrowed
  input second String borrowed
  input third String borrowed
  input fourth String borrowed
:begin
  clear: unusedClear = *setter(tm, zero32=0, size=56)
  calc text = area + 1024
  calc fourFormat = area + 1280
  calc oneFormat = area + 1296
  calc longFormat = area + 1312
  calc p4 = tm + 4
  calc p8 = tm + 8
  calc p12 = tm + 12
  calc p16 = tm + 16
  calc p20 = tm + 20
  calc p24 = tm + 24
  calc p28 = tm + 28
  calc p32 = tm + 32
  calc p40 = tm + 40
  putText(setter, text, first)
  scanFirst: unusedFirst = *scanner(text, fourFormat, tm, p4, p8, p12)
  putText(setter, text, second)
  scanSecond: unusedSecond = *scanner(text, fourFormat, p16, p20, p24, p28)
  putText(setter, text, third)
  scanThird: unusedThird = *scanner(text, oneFormat, p32, zeroA=0, zeroB=0, zeroC=0)
  putText(setter, text, fourth)
  scanFourth: unusedFourth = *scanner(text, longFormat, p40, zeroD=0, zeroE=0, zeroF=0)
  return

op storeLong "Set a long at an address from its decimal text"
  input setter SetFunction copied
  input scanner ScanFunction copied
  input area Int64 copied
  input cell Int64 copied
  input value String borrowed
:begin
  calc text = area + 1024
  calc longFormat = area + 1312
  putText(setter, text, value)
  scan: unusedScan = *scanner(text, longFormat, cell, zeroA=0, zeroB=0, zeroC=0)
  return

op sameBytes "Write 0 when two ranges of bytes are equal, else 1"
  input comparer CompareFunction copied
  input left Int64 copied
  input right Int64 copied
  input bytes Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  compareIt: difference = *comparer(left, right, bytes)
  when difference == 0 equalCase unequalCase
:equalCase
  sayNumber(0)
  return
:unequalCase
  sayNumber(1)
  return

op checkTm "Write 0 and 0 when the struct tm at an address holds the nine ints and tm_gmtoff of four groups of numbers, else 1 for the part that differs"
  input setter SetFunction copied
  input scanner ScanFunction copied
  input comparer CompareFunction copied
  input area Int64 copied
  input actual Int64 copied
  input first String borrowed
  input second String borrowed
  input third String borrowed
  input fourth String borrowed
  effect write console.stdout
  uses stdoutWriter
:begin
  calc expected = area + 320
  loadTm(setter, scanner, area, expected, first, second, third, fourth)
  calc actualOffset = actual + 40
  calc expectedOffset = expected + 40
  sameBytes(comparer, actual, expected, 36)
  sameBytes(comparer, actualOffset, expectedOffset, 8)
  return

op showFormat "strftime a struct tm into a buffer of a size (filled with X first, and a 0 after it), write the length it gives and the buffer as a line"
  input setter SetFunction copied
  input formatter StrftimeFunction copied
  input outputter PutsFunction copied
  input flusher FlushFunction copied
  input area Int64 copied
  input tm Int64 copied
  input format String borrowed
  input size Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  calc formatAt = area + 2048
  calc buffer = area + 4096
  putText(setter, formatAt, format)
  calc fillBytes = size + 4
  calc endAt = buffer + fillBytes
  fill: unusedFill = *setter(buffer, x88=88, fillBytes)
  fillEnd: unusedEnd = *setter(endAt, zero32=0, one=1)
  run: written = *formatter(buffer, size, formatAt, tm)
  sayNumber(written)
  show: unusedShow = *outputter(buffer)
  flush: unusedFlush = *flusher(zeroStream=0)
  return

op showText "Write 1 and the C string at an address as a line, or 0 for the address 0"
  input outputter PutsFunction copied
  input flusher FlushFunction copied
  input text Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  when text == 0 absent present
:absent
  sayNumber(0)
  return
:present
  sayNumber(1)
  show: unusedShow = *outputter(text)
  flush: unusedFlush = *flusher(zeroStream=0)
  return
'''


SHOW = "%Y-%m-%d %H:%M:%S %Z %z %j %w %e"


class Tour:
    """The tour for one zone: the lines of main's body and the text they print, built together so they cannot drift."""

    def __init__(self, spec: str):
        self.zone = Zone(spec if spec != "UTC" else "UTC0")
        self.k = 0
        self.body: list[str] = []
        self.out: list[str] = []

    # -- helpers
    def n(self) -> int:
        self.k += 1
        return self.k

    def say(self, value) -> None:
        self.out.append(f"{value}\n")

    def line(self, text: str) -> None:
        self.body.append("  " + text)

    def tzname(self):
        return self.zone.std, self.zone.dst or self.zone.std

    def model_format(self, fmt: str, tm: Tm, size: int) -> None:
        """What showFormat prints for a format, a struct tm, and a buffer size."""
        text, partial = strftime(fmt, tm, size, mktime=self.zone.mktime, tzname=self.tzname(), localtime=self.zone.localtime)
        self.say(len(text) if text is not None else 0)
        if text is not None and size > 0:
            self.out.append(text + "\n")
        else:
            self.out.append(partial + "X" * (size + 4 - len(partial)) + "\n")

    def show(self, pointer: str, fmt: str, size: int) -> None:
        self.line(f'showFormat(memsetFn, strftimeFn, putsFn, fflushFn, area, {pointer}, "{fmt}", {size})')

    def load(self, address: str, tm: Tm) -> None:
        a, b, c, d = tm_groups(tm)
        self.line(f'loadTm(memsetFn, sscanfFn, area, {address}, "{a}", "{b}", "{c}", "{d}")')

    def check(self, pointer: str, tm: Tm) -> None:
        a, b, c, d = tm_groups(tm)
        self.line(f'checkTm(memsetFn, sscanfFn, memcmpFn, area, {pointer}, "{a}", "{b}", "{c}", "{d}")')
        self.say(0)
        self.say(0)

    def store_time(self, t: int) -> None:
        self.line(f'storeLong(memsetFn, sscanfFn, area, cellT, "{t}")')

    # -- the cases
    def broken_down(self, kind: str, t: int) -> None:
        """gmtime, gmtime_r, localtime, localtime_r of a time."""
        k = self.n()
        tm = gmtime(t) if kind.startswith("gm") else self.zone.localtime(t)
        self.store_time(t)
        reentrant = kind.endswith("R")
        function = {"gmtime": "gmtimeFn", "gmtimeR": "gmtimeRFn", "localtime": "localtimeFn",
                    "localtimeR": "localtimeRFn"}[kind]
        if reentrant:
            self.line(f"r{k}: result{k} = *{function}(cellT, tmOut)")
        else:
            self.line(f"r{k}: result{k} = *{function}(cellT)")
        self.line(f"sayNull(result{k})")
        self.say(1 if tm else 0)
        if reentrant:
            self.line(f"sayEqual(result{k}, tmOut)")
            self.say(1 if tm else 0)
        if tm:
            self.check(f"result{k}", tm)
            self.show(f"result{k}", SHOW, 256)
            self.model_format(SHOW, tm, 256)

    def make_time(self, fields, isdst: int) -> None:
        k = self.n()
        tm = Tm(*fields, 0, 0, isdst, 0)
        self.load("tmIn", tm)
        self.line(f"m{k}: made{k} = *mktimeFn(tmIn)")
        self.line(f"sayNumber(made{k})")
        copy = tm.copy()
        self.zone.failed = False
        t = self.zone.mktime(copy)
        self.say(t)
        if not self.zone.failed:
            self.check("tmIn", copy)
            fmt = "%Y-%m-%d %H:%M:%S %Z %z %j %w"
            self.show("tmIn", fmt, 256)
            self.model_format(fmt, copy, 256)

    def text(self, kind: str, source) -> None:
        """asctime, asctime_r, ctime, ctime_r."""
        k = self.n()
        if kind.startswith("asctime"):
            tm = Tm(*source)
            self.load("tmIn", tm)
            argument = "tmIn"
        else:
            tm = self.zone.localtime(source)
            self.store_time(source)
            argument = "cellT"
        text = asctime(tm) if tm else None
        function = {"asctime": "asctimeFn", "asctimeR": "asctimeRFn", "ctime": "ctimeFn", "ctimeR": "ctimeRFn"}[kind]
        if kind.endswith("R"):
            self.line(f"t{k}: result{k} = *{function}({argument}, buf)")
        else:
            self.line(f"t{k}: result{k} = *{function}({argument})")
        self.line(f"showText(putsFn, fflushFn, result{k})")
        if text is None:
            self.say(0)
        else:
            self.say(1)
            self.out.append(text + "\n")
        if kind.endswith("R"):
            self.line(f"sayEqual(result{k}, buf)")
            self.say(1 if text is not None else 0)

    def formatted(self, source, fmt: str, size: int) -> None:
        k = self.n()
        if source[0] == "hand":
            tm = hand_tm(source[1], source[2])
            self.load("tmIn", tm)
            pointer = "tmIn"
        else:
            t = source[1]
            tm = gmtime(t) if source[0] == "gm" else self.zone.localtime(t)
            if tm is None:
                return
            self.store_time(t)
            function = "gmtimeFn" if source[0] == "gm" else "localtimeFn"
            self.line(f"f{k}: broken{k} = *{function}(cellT)")
            pointer = f"broken{k}"
        self.show(pointer, fmt, size)
        self.model_format(fmt, tm, size)

    def difference(self, a: int, b: int) -> None:
        k = self.n()
        self.line(f"d{k}: gap{k} = *difftimeFn(later{k}={a}, earlier{k}={b})")
        self.line(f"sayDouble(gap{k})")
        self.say(repr(float(a) - float(b)))

    def clocks(self) -> None:
        """time, timespec_get, and clock: only what does not depend on the moment they run."""
        self.line("c1: now = *timeFn(nothing=0)")
        self.line("calc scaledNow = now / 1000000000")
        self.line("sayNumber(scaledNow)")
        self.say(1)
        self.line("c2: stored = *timeFn(cellU)")
        self.line("c3: brokenStored = *gmtimeFn(cellU)")
        self.show("brokenStored", "%C", 16)
        self.say(2)
        self.say("20")
        self.line("c4: spec = *timespecGetFn(specAt, utc=1)")
        self.line("calc specWide = convert.int32ToInt64(spec)")
        self.line("sayNumber(specWide)")
        self.say(1)
        self.line("c5: brokenSpec = *gmtimeFn(specAt)")
        self.show("brokenSpec", "%C", 16)
        self.say(2)
        self.say("20")
        for k, base in enumerate((0, 2, 3, -1, 100)):
            self.line(f"b{k}: other{k} = *timespecGetFn(specAt, base{k}={base})")
            self.line(f"calc otherWide{k} = convert.int32ToInt64(other{k})")
            self.line(f"sayNumber(otherWide{k})")
            self.say(0)
        self.line("c6: ticks = *clockFn()")
        self.line("calc scaledTicks = ticks / 100000000")
        self.line("sayNumber(scaledTicks)")
        self.say(0)
        self.line("calc positive = (ticks + 100000000000) / 100000000000")
        self.line("sayNumber(positive)")
        self.say(1)

    def statics(self) -> None:
        """gmtime and localtime give the one static struct tm; asctime and ctime the one static buffer."""
        self.store_time(1710055800)
        self.line("s1: first = *gmtimeFn(cellT)")
        self.line("s2: second = *localtimeFn(cellT)")
        self.line("sayEqual(first, second)")
        self.say(1)
        self.line("s3: third = *gmtimeFn(cellT)")
        self.line("sayEqual(first, third)")
        self.say(1)
        self.line("s4: written = *asctimeFn(first)")
        self.line("s5: timeText = *ctimeFn(cellT)")
        self.line("sayEqual(written, timeText)")
        self.say(1)

    def build(self) -> None:
        for t in GM_TIMES:
            self.broken_down("gmtime", t)
            self.broken_down("gmtimeR", t)
        for t in SWEEP:
            self.broken_down("gmtime", t)
            self.formatted(("gm", t), SWEEP_FORMAT, 256)
        for t in SWEEP[:50]:
            tm = gmtime(t)
            self.make_time((tm.sec, tm.min, tm.hour, tm.mday, tm.mon, tm.year), -1)
        for t in LOCAL_TIMES:
            self.broken_down("localtime", t)
            self.broken_down("localtimeR", t)
        for fields, isdst in MKTIME_CASES + AMBIGUOUS:
            self.make_time(fields, isdst)
        for tm in ASCTIME_TMS:
            self.text("asctime", tm)
            self.text("asctimeR", tm)
        for t in (0, 1710055800, -1, 253402300799, 4102444800, 9223372036854775807, -2208988800, 951782400):
            self.text("ctime", t)
            self.text("ctimeR", t)
        for fmt in FORMATS:
            for t in STRFTIME_TIMES:
                self.formatted(("gm", t), fmt, 512)
                self.formatted(("local", t), fmt, 512)
            for ints, off in HAND_TMS:
                self.formatted(("hand", ints, off), fmt, 512)
        for size, fmt in SIZES:
            self.formatted(("gm", 1710055800), fmt, size)
            self.formatted(("local", 1710055800), fmt, size)
        for a, b in DIFFTIMES:
            self.difference(a, b)
        self.statics()
        self.clocks()


def program_dsl(spec: str):
    tour = Tour(spec)
    tour.build()
    caps = [f'capability {n}Symbol "Authority to bind the C function {c}" load ffi.symbols "{c}"'
            for n, c in SYMBOLS.items()]
    uses = "\n".join(f"  uses {n}Symbol" for n in SYMBOLS)
    bindings = "\n".join(f'  bind{n}: {n}Fn = {t}Binding.bind(libc, {n}Name="{SYMBOLS[n]}") ? failed'
                         for n, t in BINDINGS)
    body = chr(10).join(tour.body)
    dsl = f'''module ctimetour "Call the runtime's time.h functions through ffi and print what each gives"
  path ctimetour
  imports standard.console standard.ffi standard.convert standard.compare standard.math standard.string
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

capability cLibrary "Authority to load the C library and nothing else" load ffi.libraries "c"

{chr(10).join(c + chr(10) for c in caps)}
{OPTYPES}
{HELPERS}
op main "Open the C library, call each function, and write what it gives"
  output ExitCode
  effect load ffi.libraries
  effect load ffi.symbols
  effect write console.stdout
  uses cLibrary
{uses}
  uses stdoutWriter
  let okCode ExitCode 0
  let failCode ExitCode 1
:begin
  openIt: libc = ffi.open(cName="c") ? failedOpen
{bindings}
  takeArea: area = *callocFn(areaBytes=16384, one=1)
  calc cellT = area + {CELL_T}
  calc cellU = area + {CELL_U}
  calc specAt = area + {SPEC_AT}
  calc tmIn = area + {TM_IN}
  calc tmOut = area + {TM_OUT}
  calc buf = area + {BUF}
  calc fourAt = area + {SCAN4}
  putText(memsetFn, fourAt, "%d %d %d %d")
  calc oneAt = area + {SCAN1}
  putText(memsetFn, oneAt, "%d")
  calc longAt = area + {SCANL}
  putText(memsetFn, longAt, "%ld")
{body}
  closeIt: ffi.close(libc)
  return okCode
:failed
  closeFailed: ffi.close(libc)
  return failCode
:failedOpen
  return failCode
'''
    return dsl, tour


def write_project(folder: str, spec: str = "UTC") -> None:
    """The project: build.sem and ctimetour.sem, generated from the DSL above for a zone's expected text."""
    from semgen import Generator, Module, Program
    from caselib import allows_rows
    dsl, _tour = program_dsl(spec)
    prog = Program()
    m = Module("ctimetour")
    prog.modules["ctimetour"] = m
    g = Generator(prog, m)
    g.declare(dsl)
    g.parse(dsl)
    sem, _tests = g.render(["# The runtime's time.h functions through ffi (tests/ctimetour.py)."], None)
    owner, target, lines = "", "", []
    for line in sem.split("\n"):
        parts = line.split()
        if len(parts) == 3 and parts[1] == "in":
            owner = parts[2]
        if len(parts) == 3 and parts[1] == "invokes":
            target = parts[2]
        if len(parts) == 3 and parts[1] == "ownedBy" and parts[2] == "none" and target == "ffi.open":
            line = line.replace("ownedBy none", f"ownedBy {owner}")
        lines.append(line)
    sem = "\n".join(lines)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "ctimetour.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(sem)
    rows = ["tourProject is project", 'tourProject purpose "Call the runtime\'s time.h functions through ffi"',
            "tourProject target console", 'tourProject version "0.1.0"', "tourProject language refined 1",
            "tourProject standardLibrary 1", *allows_rows("tourProject", [sem]), "tourProject requires none",
            "tourProject includesModule ctimetour", "tourProject entry ctimetour.main"]
    with open(os.path.join(folder, "build.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")


def expected(spec: str) -> str:
    """What the tour prints when the library behaves as glibc does under TZ=spec."""
    tour = Tour(spec)
    tour.build()
    return "".join(tour.out)
