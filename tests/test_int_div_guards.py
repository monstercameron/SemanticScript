#!/usr/bin/env python3
"""R-248/R-249: integer divide/modulo trap instead of executing UB.

R-248 — Int32 divide/modulo previously fell through to the unguarded sdiv/srem
path, so a zero divisor was UB/SIGFPE (the Int64 variants were already guarded).
R-249 — sdiv/srem of INT_MIN by -1 overflows (UB / SIGFPE on x86); now guarded on
every width. Both raise the structured SSR0010 panic (nonzero exit), never UB.
Operands are derived at runtime (subtraction) so the runtime guard is exercised.
"""
import importlib
import subprocess
import sys

semanticscript = importlib.import_module("semanticscript")
SEMANTICSCRIPT = semanticscript.__file__

_HEAD = (
    "P is project\nP module m\nP target console\nP entry main\n"
    'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
    "ExitCode is alias\nExitCode for Int32\n"
)


def _run(src):
    return subprocess.run(
        [sys.executable, SEMANTICSCRIPT, "run", "-"],
        input=src, capture_output=True, text=True, encoding="utf-8")


def test_r248_int32_divide_by_zero_traps():
    # zero = a - a (runtime), then a / zero must trap, not UB.
    src = _HEAD + (
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let a immutable Int32 1000000\nmain let okCode immutable ExitCode 0\n"
        "main do mkzero\nmain do divide\nmain return okCode\n"
        "mkzero is call\nmkzero in main\nmkzero invokes math.subtractInt32\n"
        "mkzero arg left Int32 a\nmkzero arg right Int32 a\nmkzero out zero Int32\n"
        "divide is call\ndivide in main\ndivide invokes math.divideInt32\n"
        "divide arg left Int32 a\ndivide arg right Int32 zero\ndivide out q Int32\n")
    proc = _run(src)
    assert proc.returncode != 0, "Int32 /0 must trap (got rc=0)"
    assert "SSR0010" in (proc.stdout + proc.stderr) or "divide" in (proc.stdout + proc.stderr).lower()


def test_r249_int32_intmin_over_neg_one_traps():
    # negOne = zero - one (runtime); INT_MIN / -1 overflows -> must trap.
    src = _HEAD + (
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let intmin immutable Int32 -2147483648\n"
        "main let one immutable Int32 1\nmain let z immutable Int32 0\n"
        "main let okCode immutable ExitCode 0\n"
        "main do mkneg\nmain do divide\nmain return okCode\n"
        "mkneg is call\nmkneg in main\nmkneg invokes math.subtractInt32\n"
        "mkneg arg left Int32 z\nmkneg arg right Int32 one\nmkneg out negOne Int32\n"
        "divide is call\ndivide in main\ndivide invokes math.divideInt32\n"
        "divide arg left Int32 intmin\ndivide arg right Int32 negOne\ndivide out q Int32\n")
    proc = _run(src)
    assert proc.returncode != 0, "INT_MIN / -1 must trap (got rc=0)"
    assert "SSR0010" in (proc.stdout + proc.stderr) or "overflow" in (proc.stdout + proc.stderr).lower()


def test_int32_normal_divide_still_works():
    # a guard must not break valid division.
    src = _HEAD + (
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let a immutable Int32 100\nmain let b immutable Int32 7\n"
        "main let okCode immutable ExitCode 0\n"
        "main do divide\nmain do show\nmain return okCode\n"
        "divide is call\ndivide in main\ndivide invokes math.divideInt32\n"
        "divide arg left Int32 a\ndivide arg right Int32 b\ndivide out q Int32\n"
        "show is call\nshow in main\nshow invokes console.writeIntegerLine\n"
        "show arg value Int32 q\n")
    proc = _run(src)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "14"  # 100 / 7 == 14
