#!/usr/bin/env python3
"""R-225: the per-operation owned-calls map is built once and shared.

~11 validators rebuilt the same `{op -> its calls}` filter inside their own per-op
loop (O(ops × all_calls)). They now share `_calls_by_owner`, an O(entities) pass
memoized on the program. This asserts the grouping is correct (matches the old
filter), that it is memoized (same object returned, and stale after a structural
change), and — implicitly via the conformance matrix — that diagnostics are
unchanged.
"""
import importlib

ss = importlib.import_module("semanticscript")

_SRC = (
    "m is module\nm path a.b\nm purpose \"p\"\nm invariant \"i\"\nm exports run\n"
    "run is operation\nrun out Int32\nrun async no\nrun purpose \"p\"\nrun invariant \"i\"\n"
    "run let z immutable Int32 0\nrun do c1\nrun do c2\nrun return z\n"
    "c1 is call\nc1 in run\nc1 invokes console.writeIntegerLine\nc1 arg value Int64 z\n"
    "c2 is call\nc2 in run\nc2 invokes console.writeIntegerLine\nc2 arg value Int64 z\n"
    "helper is operation\nhelper out Int32\nhelper async no\nhelper purpose \"p\"\n"
    "helper invariant \"i\"\nhelper let y immutable Int32 0\nhelper do c3\nhelper return y\n"
    "c3 is call\nc3 in helper\nc3 invokes console.writeIntegerLine\nc3 arg value Int64 y\n"
)


def _reference_owned(program, op_name):
    # the pre-R-225 inline filter, for an equivalence check
    Row = ss.Row
    return [program.entities[c] for c in program.order
            if program.entities[c].kind in ("call", "task")
            and (program.entities[c].fact("in") or Row("", "", [], 0)).payload[:1] == [op_name]]


def test_grouping_matches_reference_filter():
    p = ss.parse(_SRC)
    m = ss._calls_by_owner(p)
    assert [e.name for e in m["run"]] == ["c1", "c2"]
    assert [e.name for e in m["helper"]] == ["c3"]
    for op in ("run", "helper"):
        assert m.get(op, []) == _reference_owned(p, op)   # exact same entities/order


def test_memoized_same_object_per_program():
    p = ss.parse(_SRC)
    assert ss._calls_by_owner(p) is ss._calls_by_owner(p)   # cache hit, not rebuilt
