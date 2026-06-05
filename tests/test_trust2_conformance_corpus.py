#!/usr/bin/env python3
"""TRUST-2 (P0): the `check ⊇ codegen` conformance corpus — the structural
forcing-function that keeps the check and codegen lanes in sync.

The trust gap (TRUST-1/BIN-2) is that a program can pass `check` and then die at
`lower`/`run`/`build`. A one-off fix closes one false green; this corpus closes the
*class*: for every scaffold pattern and every shipped example, a clean `check` MUST
imply a successful lowering. The day a check-accepted construct stops lowering (a
new false green), one of these goes red — so the two lanes can never silently drift.

Lowering (llvmlite IR generation) is the deterministic codegen gate and needs no C
toolchain, so this runs everywhere in CI. Native `build`/`run` equivalence is
covered by the e2e suites (conformance matrix, composition goldens); here we pin the
check→codegen implication itself.

The contract is an *implication*: if `check` is clean then `lower` must succeed. A
program that legitimately fails `check` (an intentional negative, or an in-flight
parallel defect) is simply not check-clean, so it does not constrain this gate.
"""
import glob
import importlib
import os

import pytest

semanticscript = importlib.import_module("semanticscript")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCAFFOLDS = list(getattr(semanticscript, "SCAFFOLD_PATTERNS",
                         ("console-program", "fallible-write", "fallible-operation",
                          "trust-boundary", "json-output", "json-decode",
                          "db-roundtrip", "logged-op")))
EXAMPLES = sorted(glob.glob(os.path.join(ROOT, "examples", "*.sem")))


def _check_clean(program):
    return not any(d.severity == "error" for d in semanticscript.lint(program))


def _assert_check_implies_lower(program, label):
    """The core TRUST-2 implication: check-clean ⟹ lowers."""
    if not _check_clean(program):
        pytest.skip(f"{label}: not check-clean (does not constrain check⊇codegen)")
    try:
        semanticscript.lower_to_llvm(program)
    except Exception as exc:  # noqa: BLE001 — any codegen failure is the regression
        pytest.fail(
            f"FALSE GREEN: {label} passes `check` but fails to lower "
            f"(check ⊇ codegen violated): {type(exc).__name__}: {exc}")


@pytest.mark.parametrize("pattern", SCAFFOLDS)
def test_trust2_every_scaffold_that_checks_clean_lowers(pattern):
    """Every agent-reachable scaffold must honor check ⊇ codegen — a scaffold that
    teaches a false-green construct is worse than none."""
    program = semanticscript.parse(semanticscript.scaffold(pattern))
    _assert_check_implies_lower(program, f"scaffold {pattern!r}")


@pytest.mark.parametrize("path", EXAMPLES, ids=[os.path.basename(p) for p in EXAMPLES])
def test_trust2_every_example_that_checks_clean_lowers(path):
    """Every shipped example must honor check ⊇ codegen."""
    try:
        program = semanticscript.parse(open(path, encoding="utf-8").read())
    except semanticscript.EavError as exc:
        pytest.skip(f"does not parse standalone: {exc}")
    _assert_check_implies_lower(program, os.path.basename(path))


def test_trust2_corpus_is_substantial():
    """The forcing-function only forces if the corpus is real: guard against the
    gate silently degenerating to zero scaffolds/examples (which would pass
    vacuously)."""
    assert len(SCAFFOLDS) >= 8, f"suspiciously few scaffolds: {SCAFFOLDS}"
    assert len(EXAMPLES) >= 100, f"suspiciously few examples: {len(EXAMPLES)}"
    # and a meaningful fraction must actually be check-clean (else the implication
    # is vacuously satisfied corpus-wide).
    clean = sum(
        1 for p in EXAMPLES
        if _example_checks_clean(p))
    assert clean >= 100, f"only {clean} check-clean examples exercise the gate"


def _example_checks_clean(path):
    try:
        return _check_clean(semanticscript.parse(open(path, encoding="utf-8").read()))
    except semanticscript.EavError:
        return False
