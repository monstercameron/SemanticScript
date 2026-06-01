#!/usr/bin/env python3
"""R-222/R-223: the observable-sink set covers the printf-family and every wire
serializer/encoder, not just console writes + JSON.

R-222 — a secret passed as a printf-family format ARGUMENT (printf / c.printf /
c.fprintf / c.sprintf / c.snprintf / console.format) leaks to stdout/stderr, so
those targets are observable sinks (distinct from the SS3088 format-constness
check).
R-223 — any serialize/encode/stringify/marshal/dump/render verb on any family
(yaml/toml/xml/csv/base64/…) surfaces a value into an external representation,
so it is an observable sink the same as json.serialize.
"""
import importlib

semanticscript = importlib.import_module("semanticscript")


def _codes_or_raise(src):
    try:
        return {d.code for d in semanticscript.lint(semanticscript.parse(src))}
    except semanticscript.EavError as e:
        return {getattr(e, "code", None)}


def test_r222_secret_to_console_format_rejected():
    rows = [
        "m is module", "m path a.b", 'm purpose "x"', 'm invariant "y"',
        "m exports run",
        "Token is alias", "Token for String", "Token typeTrust secret",
        'Token purpose "t"',
        "run is operation", "run out Int32", "run async no", 'run purpose "p"',
        'run invariant "i"',
        "run let tok immutable Token", 'run let fmt immutable String "%s"',
        "run let z immutable Int32 0",
        "run do leak", "run return z",
        "leak is call", "leak in run", "leak invokes console.format",
        "leak arg format String fmt", "leak arg value Token tok",
    ]
    assert "SS3072" in _codes_or_raise(chr(10).join(rows) + chr(10))


def test_r223_non_json_serializers_are_observable_sinks():
    sink = semanticscript._is_observable_sink
    # wire serializers/encoders across families are all sinks now
    for target in ("yaml.serialize", "toml.encode", "xml.render",
                   "base64.encode", "csv.dump", "json.serializeDocument",
                   "proto.marshal", "msgpack.stringify"):
        assert sink(target), target
    # non-serializing reads/lookups are NOT sinks (no false positives)
    for target in ("list.length", "map.get", "http.requestHeader",
                   "json.createDocument", "string.concat"):
        assert not sink(target), target


def test_r222_printf_family_targets_are_sinks():
    sink = semanticscript._is_observable_sink
    for target in ("printf", "c.printf", "c.fprintf", "c.sprintf",
                   "c.snprintf", "console.format"):
        assert sink(target), target
