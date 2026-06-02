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


def _secret_error_ctor_program(invoke):
    rows = [
        "m is module", "m path a.b", 'm purpose "x"', 'm invariant "y"',
        "m exports run",
        "Token is alias", "Token for String", "Token typeTrust secret",
        'Token purpose "t"',
        "LoginError is error",
        "run is operation", "run out Int32", "run async no", 'run purpose "p"',
        'run invariant "i"',
        "run let tok immutable Token", "run let z immutable Int32 0",
        "run do mk", "run return z",
        "mk is call", "mk in run", "mk invokes " + invoke,
        "mk arg payload Token tok",
    ]
    return chr(10).join(rows) + chr(10)


def _secret_launder_program(body_type):
    # a `body_type` value flows through the plain-String wrapper `clean` and the
    # laundered result reaches console.writeLine.
    return chr(10).join([
        "Secret is alias", "Secret for String", "Secret typeTrust secret",
        "clean is operation", f"clean in raw {body_type}", "clean out String",
        "clean let r immutable Int32 0", "clean return r",
        "handler is operation", "handler out ExitCode", "handler async no",
        'handler purpose "p"', 'handler invariant "i"', f"handler in body {body_type}",
        "handler let okCode immutable ExitCode 0",
        "handler do launderCall", "handler do sinkCall", "handler return okCode",
        "launderCall is call", "launderCall in handler", "launderCall invokes clean",
        f"launderCall arg raw {body_type} body", "launderCall out cleaned String",
        "sinkCall is call", "sinkCall in handler", "sinkCall invokes console.writeLine",
        "sinkCall arg text String cleaned",
        "ExitCode is alias", "ExitCode for Int32",
    ]) + chr(10)


def test_r219_secret_laundered_through_plain_wrapper_rejected():
    # R-219: secret leakage is value PROVENANCE, not just the declared type at the
    # sink. A secret laundered through a wrapper that returns a plain String still
    # carries secret provenance, so reaching console.writeLine is SS3072 — a plain
    # value at the same sink is unaffected (no false positive).
    assert "SS3072" in _codes_or_raise(_secret_launder_program("Secret"))
    assert "SS3072" not in _codes_or_raise(_secret_launder_program("String"))


def test_r224_secret_into_error_case_constructor_rejected():
    # R-224: the owning error is the segment BEFORE the case, so a module-qualified
    # constructor (`Mod.LoginError.BadToken`) whose first segment is the module —
    # not the error — must still be flagged. The unqualified form is the guard that
    # the previous behavior is preserved.
    assert "SS3072" in _codes_or_raise(_secret_error_ctor_program("LoginError.BadToken"))
    assert "SS3072" in _codes_or_raise(_secret_error_ctor_program("Mod.LoginError.BadToken"))
