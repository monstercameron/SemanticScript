#!/usr/bin/env python3
"""FIX-3: the formatter is TOTAL and IDEMPOTENT.

Total: format_program succeeds on every parseable program (the canonicalizer the
rest of the toolchain rests on must never crash on valid source). Idempotent:
format_program(parse(format_program(p))) == format_program(p) — a single fixed
canonical form per program. This is the pytest gate for the property the
run_examples script also checks, so a regression turns CI red here too.
"""
import glob
import importlib
import os

semanticscript = importlib.import_module("semanticscript")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _examples():
    pats = [os.path.join(ROOT, "examples", "*.sem"),
            os.path.join(ROOT, "examples", "**", "*.sem")]
    seen = set()
    for pat in pats:
        for p in sorted(glob.glob(pat, recursive=True)):
            if p not in seen:
                seen.add(p)
                yield p


def test_fix3_fmt_is_total_and_idempotent_over_the_corpus():
    checked = 0
    for path in _examples():
        src = open(path, encoding="utf-8").read()
        try:
            prog = semanticscript.parse(src)
        except semanticscript.EavError:
            continue  # an intentional negative/parse-error fixture — out of scope
        # Total: must not raise on a parseable program.
        once = semanticscript.format_program(prog)
        # Idempotent: a second round-trip is a fixed point.
        twice = semanticscript.format_program(semanticscript.parse(once))
        assert once == twice, f"{os.path.relpath(path, ROOT)}: fmt is not idempotent"
        checked += 1
    assert checked >= 100, f"expected to format many examples, got {checked}"


def test_fix3_fmt_write_dedupes_identical_type_declarations(tmp_path, capsys):
    path = tmp_path / "dup.sem"
    path.write_text(
        "ExitCode is alias\nExitCode for Int32\n"
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        "main let z immutable ExitCode 0\nmain return z\n",
        encoding="utf-8",
    )

    assert semanticscript.main(["fmt", "-w", str(path)]) == 0
    capsys.readouterr()
    out = path.read_text(encoding="utf-8")
    assert out.count("ExitCode is alias") == 1
    semanticscript.parse(out)
