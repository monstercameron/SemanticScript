#!/usr/bin/env python3
"""D1/A1/A9: `check` rejects call targets the code generator can't lower, and
`sem targets` lists the runnable vocabulary.

Before, an untyped/unmodeled target like `math.divide` passed `check` (false
green) and only failed at `run`/`build` ("not modeled by the LLVM console code
generator"). Now `check` rejects it (SS1198, a deny-tier lint mirroring the
SS1195 runtimeBinding check), and `sem targets` surfaces the runnable variant
(`math.divideInt64`) so the fix is discoverable.
"""
import importlib
import json
import os
import subprocess
import sys

semanticscript = importlib.import_module("semanticscript")
SEMANTICSCRIPT = semanticscript.__file__

_HEAD = (
    "P is project\nP module m\nP target console\nP entry main\n"
    'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
    "ExitCode is alias\nExitCode for Int32\n"
)


def _div_program(target):
    return _HEAD + (
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let a immutable Int64 10\nmain let b immutable Int64 2\n"
        "main let okCode immutable ExitCode 0\n"
        "main do divideCall\nmain return okCode\n"
        "divideCall is call\ndivideCall in main\ndivideCall invokes " + target + "\n"
        "divideCall arg left Int64 a\ndivideCall arg right Int64 b\n"
        "divideCall out q Int64\n")


def _codes(src):
    return {d.code for d in semanticscript.lint(semanticscript.parse(src))}


def test_unmodeled_math_target_rejected_at_check():
    # math.divide is not modeled by the code generator -> SS1198 (no false green)
    assert "SS1198" in _codes(_div_program("math.divide"))


def test_runnable_width_typed_target_accepted():
    # the runnable variant the generator DOES model is not flagged
    assert "SS1198" not in _codes(_div_program("math.divideInt64"))


def test_user_records_and_modules_not_flagged():
    # a dotted target in a non-builtin namespace (record ctor / cross-module op)
    # is user-defined, not a builtin — must not be flagged
    assert "SS1198" not in _codes(_div_program("MyRecord.new"))
    assert "SS1198" not in _codes(_div_program("components.render"))


def _print_program(target, value_type):
    return _HEAD + (
        "main is operation\nmain out ExitCode\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let v immutable %s 42\nmain let okCode immutable ExitCode 0\n"
        "main do printCall\nmain return okCode\n"
        "printCall is call\nprintCall in main\nprintCall invokes %s\n"
        "printCall arg text %s v\n" % (value_type, target, value_type))


def test_a2_integer_to_writeline_rejected_and_steered():
    # an Int64 to console.writeLine (which prints a String) crashed run with a raw
    # i8*-vs-i64 traceback; now rejected at check (SS1199) steering to the int op
    codes = _codes(_print_program("console.writeLine", "Int64"))
    assert "SS1199" in codes


def test_a2_correct_console_ops_not_flagged():
    # the right op for each type is accepted
    assert "SS1199" not in _codes(_print_program("console.writeIntegerLine", "Int64"))
    assert "SS1199" not in _codes(_print_program("console.writeFloatLine", "Float64"))


def test_sem_targets_lists_runnable_vocabulary():
    proc = subprocess.run([sys.executable, SEMANTICSCRIPT, "targets", "--json"],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["version"] == "sem.targets.v1"
    math = data["families"]["math"]
    assert "math.divideInt64" in math          # the runnable variant for D1
    assert "math.divide" not in math           # the unmodeled one is absent
