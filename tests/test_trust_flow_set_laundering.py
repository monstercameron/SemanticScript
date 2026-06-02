#!/usr/bin/env python3
"""R-220: trust/taint flows through `set` (mutable storage / mutable-let writes).

The trust-flow fixpoint propagated taint only through call `out` facts, never
through `set <tgt> <src...>` rows. So bouncing a rawExternal/secret value through
a plain-typed mutable binding and reading it back erased its provenance — a
universal laundering primitive that defeated SS3070 before any SQL/path/command/
HTML sink. The fixpoint now also propagates through `set`: if any source is
tainted, the target is tainted (iterated to fixpoint alongside the call flow).
"""
import importlib

import pytest

ss = importlib.import_module("semanticscript")


def _src(set_row):
    return (
        "RawBody is alias\nRawBody for String\nRawBody typeTrust rawExternal\n"
        "logIt is operation\nlogIt in line String\nlogIt out Int32\n"
        "logIt trustConstraint arg line\nlogIt let z immutable Int32 0\nlogIt return z\n"
        "handler is operation\nhandler out ExitCode\nhandler async no\n"
        'handler purpose "p"\nhandler invariant "i"\nhandler in body RawBody\n'
        'handler let scratch mutable String "init"\n'
        "handler let okCode immutable ExitCode 0\n"
        f"{set_row}\n"
        "handler do sinkCall\nhandler return okCode\n"
        "sinkCall is call\nsinkCall in handler\nsinkCall invokes logIt\n"
        "sinkCall arg line String scratch\nsinkCall out n Int32\n"
        "ExitCode is alias\nExitCode for Int32\n"
    )


def test_set_from_raw_external_launders_taint_rejected():
    # `set scratch body` writes the rawExternal `body` into the plain-String
    # `scratch`; reading scratch into the sink must still be SS3070.
    with pytest.raises(ss.EavError) as exc:
        ss.parse(_src("handler set scratch body"))
    assert getattr(exc.value, "code", None) == "SS3070"


def test_set_from_clean_source_not_flagged():
    # `set scratch okCode` (a clean ExitCode local) leaves scratch untainted —
    # no false positive at the same sink.
    assert "handler" in ss.parse(_src("handler set scratch okCode")).entities
