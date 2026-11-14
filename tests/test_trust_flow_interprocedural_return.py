#!/usr/bin/env python3
"""R-221: trust/taint is interprocedural on RETURN values.

The trust-flow fixpoint computed each op's taint in isolation and tainted a
call's `out` only when the call passed a tainted ARG. A helper that took no
tainted args but internally read a module-global rawExternal/secret storage and
returned it (plain out type) never marked its out tainted at the call site — so
any module-global untrusted/secret state could be laundered through a helper
into a SQL/path/command/HTML sink, bypassing SS3070.

The fixpoint now computes an interprocedural `returns_tainted` summary: an op
whose returned value carries taint, and whose out type is not a trust boundary,
taints its result at EVERY call site regardless of arg taint — iterated to a
global fixpoint so the summary propagates across call chains.
"""
import importlib

import pytest

ss = importlib.import_module("semanticscript")


def _src(b_return):
    # module storage `cfg` is rawExternal; helper B returns `b_return`; handler
    # binds B's result and passes it into a trust-sensitive sink.
    return (
        "Cfg is alias\nCfg for String\nCfg typeTrust rawExternal\n"
        "cfg is storage\ncfg type Cfg\n"
        "logIt is operation\nlogIt in line String\nlogIt out Int32\n"
        "logIt trustConstraint arg line\nlogIt let z immutable Int32 0\nlogIt return z\n"
        f"B is operation\nB out String\nB let r immutable String \"x\"\nB return {b_return}\n"
        "handler is operation\nhandler out ExitCode\nhandler async no\n"
        'handler purpose "p"\nhandler invariant "i"\n'
        "handler let okCode immutable ExitCode 0\n"
        "handler do bCall\nhandler do sinkCall\nhandler return okCode\n"
        "bCall is call\nbCall in handler\nbCall invokes B\nbCall out result String\n"
        "sinkCall is call\nsinkCall in handler\nsinkCall invokes logIt\n"
        "sinkCall arg line String result\nsinkCall out n Int32\n"
        "ExitCode is alias\nExitCode for Int32\n"
    )


def test_helper_returning_module_global_taint_rejected():
    # B returns the rawExternal module storage `cfg`; handler sinking B's result
    # must be SS3070 even though it passed no tainted arg to B.
    with pytest.raises(ss.EavError) as exc:
        ss.parse(_src("cfg"))
    assert getattr(exc.value, "code", None) == "SS3070"


def test_helper_returning_clean_value_not_flagged():
    # B returns its own clean local `r` — no interprocedural taint, no false positive.
    assert "handler" in ss.parse(_src("r")).entities
