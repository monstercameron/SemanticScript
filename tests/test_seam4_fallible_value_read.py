#!/usr/bin/env python3
"""SEAM-4: a fallible value read with no catch is surfaced (kills json silent-empty).

A fallible structured-data accessor (a json/sqlite read whose .semsig declares a
`catch <Error>` and returns a value, e.g. json.cursorString -> String) that binds
NO `catch` and does not `discards` silently turns a missing/wrong-kind field into
an empty/zero value that flows downstream as a blank field. SS3502 (T3) names that
failure mode. Scoped to json/sqlite reads — where a catch is the only guard — so
it is zero-false-positive on the disciplined corpus (list/map gets, which can be
guarded by a separate length/contains check, are intentionally NOT flagged).
"""
import importlib

semanticscript = importlib.import_module("semanticscript")

_HDR = (
    "P is project\nP module m\nP target console\nP entry main\n"
    "m is module\nm path x\nm exports main\n"
    "main is operation\nmain out Int32\nmain async no\n"
    "main let z immutable Int32 0\nmain do readCall\nmain return z\n"
)
_READ = (
    "readCall is call\nreadCall in main\nreadCall invokes json.cursorString\n"
    "readCall arg document JsonDocument d\nreadCall out v String\n"
)


def _codes(src):
    return {d.code for d in semanticscript.lint(semanticscript.parse(src))}


def test_seam4_uncaught_json_value_read_warns_ss3502():
    assert "SS3502" in _codes(_HDR + _READ)


def test_seam4_caught_json_value_read_is_clean():
    assert "SS3502" not in _codes(_HDR + _READ + "readCall catch e JsonAccessError\n")


def test_seam4_discarded_json_value_read_is_clean():
    assert "SS3502" not in _codes(_HDR + _READ + 'readCall discards "default ok"\n')


def test_seam4_scope_excludes_writers_and_unguarded_families():
    raises = semanticscript._silent_value_read_raises
    assert raises("json.cursorString") == "JsonAccessError"   # value read -> flagged
    assert raises("json.asInt") == "JsonAccessError"
    assert raises("json.setObjectFieldString") is None        # writer -> not flagged
    assert raises("json.createDocument") is None              # factory/handle -> not
    assert raises("list.get") is None                         # separable guard -> not
    assert raises("map.get") is None
    # SS3502 must be a registered T3 diagnostic.
    entry = semanticscript.DIAGNOSTICS.get("SS3502")
    assert entry is not None and entry.get("tier") == "T3"
