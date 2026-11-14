#!/usr/bin/env python3
"""R-257: the catch variable carries the call's real error flag, not a constant 0.

_emit_call bound the catch variable to ir.Constant(i32, 0), so any program that
inspected the caught error (branched on its value, reported it, mapped it to a
Result) saw 0 unconditionally — `caughtErr != 0` never fired. It is now bound to
the call's actual error indicator (`err`) widened to i32. `branch ifError` only
reaches the error block when `err` is non-zero, so the caught value reflects that
an error occurred there (the console subset models a caught error as this i32
flag; a richer per-error discriminant is the tagged-error ABI, R-054/R-258).
"""
import importlib

semanticscript = importlib.import_module("semanticscript")


def _ir(src):
    return str(semanticscript.lower_to_llvm(semanticscript.parse(src)))


_SRC = (
    "P is project\nP module m\nP target console\nP entry main\n"
    'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
    "ExitCode is alias\nExitCode for Int32\nHashError is error\n"
    "hc is capability\nhc grants compute bcryptHash\nhc purpose \"p\"\n"
    "main is operation\nmain out ExitCode\nmain async no\nmain uses hc\nmain effect compute bcryptHash\n"
    'main purpose "p"\nmain invariant "i"\n'
    'main let pw immutable String "x"\nmain let cost immutable Int32 12\n'
    "main let okc immutable ExitCode 0\nmain let failCode immutable ExitCode 7\n"
    "main do hashIt\nmain branch ifError hashIt goto failed\nmain return okc\n"
    "main at failed do showErr\nmain return failCode\n"
    "hashIt is call\nhashIt in main\nhashIt invokes bcrypt.hashPasswordOwned\n"
    "hashIt arg plaintext String pw\nhashIt arg cost Int32 cost\nhashIt out h OpaquePointer\n"
    "hashIt catch e HashError\n"
    "showErr is call\nshowErr in main\nshowErr invokes console.writeIntegerLine\n"
    "showErr arg value Int32 e\n"
)


def test_catch_variable_widens_the_error_flag():
    ir = _ir(_SRC)
    # the caught value is the error flag widened to i32 (i1 -> i32), not a constant
    assert "zext i1" in ir


def test_catch_program_still_lowers_and_runs_clean():
    # no regression: the program lowers and the run probe classifies it ok
    out, err, code = semanticscript._record_run_full(_SRC)
    assert code == 0, err
