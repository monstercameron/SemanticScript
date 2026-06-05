#!/usr/bin/env python3
"""R-11 / R-21: the read-only/format agent commands accept a project directory.

R-21: `fmt`, `describe`, `lower`, and `fix` used to reject a project root with
"is a directory; this command reads a single file" (exit 2). They now compose /
format the project like the other project-aware commands.

R-11: `fmt --check` on a project dir must exit NONZERO when any file drifts — a
directory check that printed a drift line but exited 0 was a CI false-green.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SC = os.path.join(ROOT, "semanticscript", "compiler", "semanticscript.py")

_BUILD = (
    "Demo is project\n"
    "Demo module demoMod\n"
    "Demo target console\n"
    "Demo entry main\n"
    'Demo languageVersion "1.0"\n'
    'Demo toolchain "semanticscript"\n'
)

_MODULE = (
    "demoMod is module\n"
    "demoMod path demo\n"
    "demoMod exports main\n"
    'demoMod purpose "p"\n'
    'demoMod invariant "i"\n'
    "ExitCode is alias\n"
    "ExitCode for Int32\n"
    "main is operation\n"
    "main out ExitCode\n"
    "main async no\n"
    'main purpose "p"\n'
    'main invariant "i"\n'
    "main let z immutable ExitCode 0\n"
    "main return z\n"
)


def _run(*argv):
    return subprocess.run([sys.executable, SC, *argv],
                          capture_output=True, text=True, encoding="utf-8")


def _make_project(tmp_path):
    (tmp_path / "build.sem").write_text(_BUILD, encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.sem").write_text(_MODULE, encoding="utf-8")
    return tmp_path


def test_r21_fmt_describe_lower_fix_accept_a_project_root(tmp_path):
    proj = str(_make_project(tmp_path))
    # canonicalize first so the surfaces operate on a clean tree.
    w = _run("fmt", "-w", proj)
    assert w.returncode == 0, w.stderr
    assert "formatted" in w.stdout

    # describe resolves an entity from the composed project (was exit 2).
    d = _run("describe", proj, "main")
    assert d.returncode == 0, d.stderr
    assert "operation" in d.stdout

    # lower emits IR for the composed project (was exit 2).
    lo = _run("lower", proj)
    assert lo.returncode == 0, lo.stderr
    assert "ModuleID" in lo.stdout

    # fix emits a plan envelope for the composed project (was exit 2).
    fx = _run("fix", proj, "--json")
    assert fx.returncode == 0, fx.stderr
    assert "sem.fixPlan.v1" in fx.stdout

    # slice resolves an entity from the composed project (same project-root contract).
    sl = _run("slice", proj, "main", "--json")
    assert sl.returncode == 0, sl.stderr
    assert "sem.slice.v1" in sl.stdout


def test_r21_fmt_check_clean_project_exits_zero(tmp_path):
    proj = str(_make_project(tmp_path))
    assert _run("fmt", "-w", proj).returncode == 0
    chk = _run("fmt", "--check", proj)
    assert chk.returncode == 0, (chk.returncode, chk.stderr)


def test_r11_fmt_check_on_drifting_project_exits_nonzero(tmp_path):
    """R-11: the false-success guard — drift in any file is exit 1, not 0."""
    proj = _make_project(tmp_path)
    assert _run("fmt", "-w", str(proj)).returncode == 0
    # introduce boundary-whitespace drift (R-114) in one file.
    drifting = proj / "src" / "main.sem"
    drifting.write_text(drifting.read_text(encoding="utf-8") + "\n\n",
                        encoding="utf-8")

    chk = _run("fmt", "--check", str(proj))
    assert chk.returncode == 1, (chk.returncode, chk.stdout, chk.stderr)
    assert "drift" in chk.stderr
    # the specific drifting file is named so an agent can act on it.
    assert "main.sem" in chk.stderr


def test_r11_fmt_write_then_check_is_idempotent(tmp_path):
    proj = _make_project(tmp_path)
    # author a deliberately non-canonical file, format it, then re-check clean.
    (proj / "src" / "main.sem").write_text("\n\n" + _MODULE + "\n", encoding="utf-8")
    assert _run("fmt", "-w", str(proj)).returncode == 0
    assert _run("fmt", "--check", str(proj)).returncode == 0
    # and the composed project still checks clean after formatting.
    assert _run("check", str(proj)).returncode == 0
