#!/usr/bin/env python3
"""W2-B / W2-G / W2-H: the auth⊗db seam — owned-handle -> String + verify on a server.

W2-B: binding an owned handle (OpaquePointer, e.g. bcrypt.hashPasswordOwned /
      sessionTokenOwned) directly to `out X String` (i8*) used to slip through
      `check` and crash the code generator with a handle/String mismatch
      (SS5001). It is now caught at check time as SS1205 with a c.cString repair
      hint.
W2-G: `c.cString` (the sanctioned OpaquePointer->String reinterpret) now has a
      discoverable builtin signature, so `targets --signature c.cString` / describe
      surface it and the SS1205 hint is actionable.
W2-H: `verify` on a `webServer` target no longer drives the never-terminating
      server through the run lane (which wedged until the eval timeout); the run
      lane is skipped for a non-console target, the way `bench` reports it.
"""
import importlib

semanticscript = importlib.import_module("semanticscript")

_TOKEN_HEADER = (
    "Repro is project\nRepro module m\nRepro target console\nRepro entry main\n"
    "m is module\nm path repro\nm exports main\n"
    "ExitCode is alias\nExitCode for Int32\n"
    "ConsoleWriteError is error\n"
    "main is operation\nmain out ExitCode\nmain async no\n"
    "main let zero immutable ExitCode 0\n"
    "main do tokenCall\nmain do writeCall\nmain return zero\n"
)


def _codes(src):
    return {d.code for d in semanticscript.lint(semanticscript.parse(src))}


def test_w2b_handle_bound_to_string_out_is_ss1205_not_codegen_crash():
    # bcrypt.sessionTokenOwned returns an OpaquePointer handle; binding it
    # straight to `out tok String` is the i8*/i64 confusion.
    src = _TOKEN_HEADER + (
        "tokenCall is call\ntokenCall in main\n"
        "tokenCall invokes bcrypt.sessionTokenOwned\n"
        "tokenCall out tok String\n"
        "writeCall is call\nwriteCall in main\n"
        "writeCall invokes console.writeLine\n"
        "writeCall arg text String tok\n"
        "writeCall catch writeError ConsoleWriteError\n"
    )
    assert "SS1205" in _codes(src)


def test_w2b_correct_pattern_handle_then_cstring_is_clean():
    # The blessed flow: bind the handle as OpaquePointer, then c.cString -> String.
    src = _TOKEN_HEADER.replace(
        "main do tokenCall\nmain do writeCall",
        "main do tokenCall\nmain do viewCall\nmain do writeCall",
    ) + (
        "tokenCall is call\ntokenCall in main\n"
        "tokenCall invokes bcrypt.sessionTokenOwned\n"
        "tokenCall out tok OpaquePointer\n"
        "viewCall is call\nviewCall in main\n"
        "viewCall invokes c.cString\n"
        "viewCall arg pointer OpaquePointer tok\n"
        "viewCall out tokStr String\n"
        "writeCall is call\nwriteCall in main\n"
        "writeCall invokes console.writeLine\n"
        "writeCall arg text String tokStr\n"
        "writeCall catch writeError ConsoleWriteError\n"
    )
    assert "SS1205" not in _codes(src)


def test_w2g_cstring_signature_is_discoverable():
    sig = semanticscript._builtin_target_signature("c.cString")
    assert sig is not None, "c.cString must have a discoverable signature (W2-G)"
    assert sig.get("out") == "String"
    assert [(a["slot"], a["type"]) for a in sig["args"]] == [("pointer", "OpaquePointer")]
    # SS1205 must be a registered diagnostic with a repair that names c.cString.
    entry = semanticscript.DIAGNOSTICS.get("SS1205")
    assert entry is not None
    assert "c.cString" in entry.get("suggested", "")


# --- R-06 (SEAM-1): own a borrowed C-string view with string.fromCString --------
#
# The composition tax: `c.cString` is a borrowed view (mayEscape no), so an op that
# produces a session token / hash and tries to RETURN it tripped SS1560 — forcing
# the agent to collapse produce+consume into one fat op. The fix is a first-class
# owning copy (`string.fromCString`) plus a signature that says "borrowed" up front
# and an SS1560 that names the owning call.

# An operation that produces an owned handle, views it, and tries to return the view.
_LEAK_OP = (
    "Tok is project\nTok module m\nTok target console\nTok entry borrow\n"
    "m is module\nm path tok\nm exports borrow\n"
    "borrow is operation\nborrow out String\nborrow async no\n"
    'borrow purpose "produce a session token string"\nborrow invariant "i"\n'
    "borrow do tokenCall\nborrow do viewCall\nborrow return tokStr\n"
    "tokenCall is call\ntokenCall in borrow\n"
    "tokenCall invokes bcrypt.sessionTokenOwned\ntokenCall out tok OpaquePointer\n"
    "viewCall is call\nviewCall in borrow\nviewCall invokes c.cString\n"
    "viewCall arg pointer OpaquePointer tok\nviewCall out tokStr String\n"
)


def test_r06_returning_cstring_view_is_ss1560_naming_fromcstring():
    # Returning the borrowed c.cString view out of the op is the escape SS1560
    # guards — and the diagnostic must hand the agent the owning call.
    import pytest
    with pytest.raises(semanticscript.EavError) as exc:
        semanticscript.parse(_LEAK_OP)
    assert getattr(exc.value, "code", None) == "SS1560"
    assert "string.fromCString" in str(exc.value)


def test_r06_fromcstring_owns_the_view_so_it_escapes():
    # The blessed fix: copy the handle into an OWNED String with string.fromCString;
    # that result escapes the op, so no SS1560. This is the composition the tax used
    # to forbid — produce in one op, return the string, consume elsewhere.
    src = (
        "Tok is project\nTok module m\nTok target console\nTok entry borrow\n"
        "m is module\nm path tok\nm exports borrow\n"
        "borrow is operation\nborrow out String\nborrow async no\n"
        'borrow purpose "produce a session token string"\nborrow invariant "i"\n'
        "borrow do tokenCall\nborrow do ownCall\nborrow return owned\n"
        "tokenCall is call\ntokenCall in borrow\n"
        "tokenCall invokes bcrypt.sessionTokenOwned\ntokenCall out tok OpaquePointer\n"
        "ownCall is call\nownCall in borrow\nownCall invokes string.fromCString\n"
        "ownCall arg pointer OpaquePointer tok\nownCall out owned String\n"
    )
    # Parses (the view checker runs at parse) and SS1560 is absent from lint.
    assert "SS1560" not in _codes(src)


def test_r06_fromcstring_signature_is_owned_and_modeled():
    sig = semanticscript._builtin_target_signature("string.fromCString")
    assert sig is not None, "string.fromCString must have a discoverable signature"
    assert sig.get("out") == "String"
    assert sig.get("ownership") == "owned"
    assert [(a["slot"], a["type"]) for a in sig["args"]] == [("pointer", "OpaquePointer")]
    # Modeled by the code generator (in the runnable vocabulary), not a false green.
    assert semanticscript._codegen_modeled_target(
        "string.fromCString", semanticscript.parse(
            "P is project\nP module m\nP target console\nP entry main\n"
            "m is module\nm path m\n"))


def test_r06_cstring_signature_marks_out_borrowed():
    # AQ-6: the lifetime lives in the signature, discoverable via targets/describe,
    # not learned by tripping SS1560.
    sig = semanticscript._builtin_target_signature("c.cString")
    assert sig.get("ownership") == "borrowed"


def test_r06_ss1560_repair_names_fromcstring():
    entry = semanticscript.DIAGNOSTICS.get("SS1560")
    assert entry is not None
    assert "string.fromCString" in entry.get("suggested", "")


def test_w2h_verify_skips_run_lane_for_webserver_target():
    # _program_target drives the run-lane skip; a webServer entry must not be
    # run to exit (it never terminates).
    ws = semanticscript.parse(
        "Srv is project\nSrv module m\nSrv target webServer\nSrv entry api\n"
        "m is module\nm path srv\n"
    )
    console = semanticscript.parse(
        "App is project\nApp module m\nApp target console\nApp entry main\n"
        "m is module\nm path app\n"
    )
    assert semanticscript._program_target(ws) == "webServer"
    assert semanticscript._program_target(console) == "console"
