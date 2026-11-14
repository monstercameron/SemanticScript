#!/usr/bin/env python3
"""DX-03: shipped scaffold patterns pass `check --strict` clean (zero diagnostics).

The fallible-write scaffold declared a `WriteFailed` error CASE that was never
constructed or matched (the failure path uses `catch` + `branch ifError` on the
error TYPE), so `check --strict` reported SS0803 ("error case declared but never
used") out of the box — a brand-new project that does not pass the strict gate it
models. The scaffold now ships a bare error type, so both patterns lint with no
diagnostics of any tier.
"""
import importlib

import pytest

ss = importlib.import_module("semanticscript")


@pytest.mark.parametrize("pattern", list(ss.SCAFFOLD_PATTERNS))
def test_scaffold_is_strict_clean(pattern):
    diags = ss.lint(ss.parse(ss.scaffold(pattern)))
    # strict-clean means NO diagnostics at all (not even a T3/T4 warning that
    # --strict would surface) — a freshly scaffolded program is pristine.
    assert diags == [], [d.render() for d in diags]


def test_fallible_write_no_unused_error_case_warning():
    diags = ss.lint(ss.parse(ss.scaffold("fallible-write")))
    assert "SS0803" not in {d.code for d in diags}
