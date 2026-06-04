#!/usr/bin/env python3
"""SSDX run-14 follow-ups: fixes for the run-14 rough-spot ledger.

Each test pins one R-## finding closed. Scoped to areas not under concurrent edit
by the parallel webServer/http-runtime/string-stdlib effort.
"""
import importlib
import json
import os
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SC = os.path.join(ROOT, "semanticscript", "compiler", "semanticscript.py")

SCAFFOLDS = list(getattr(semanticscript, "SCAFFOLD_PATTERNS", ()))


# --- R-17: `scaffold` output is canonical (passes `fmt --check`) ---

_ENUM_PROG = (
    "P is project\nP module m\nP target console\nP entry main\n"
    "m is module\nm path m\nm exports main\nm purpose \"p\"\nm invariant \"i\"\n"
    "ExitCode is alias\nExitCode for Int32\n"
    "Color is enum\nColor variant red\nColor variant green\n"
    "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\n"
    "main invariant \"i\"\n{LET}\nmain let z immutable ExitCode 0\nmain return z\n")


def _lint_codes(src):
    prog = semanticscript.parse(src)
    return [(d.code, d.message) for d in semanticscript.lint(prog) if d.severity == "error"]


# --- R-08 / R-10 / Root-A: an invalid enum variant is a check error (not a false green) ---

def test_r08_invalid_enum_variant_in_let_is_check_error_listing_legal_values():
    """R-08/R-10 (Root A): `let x Color purple` where `purple` isn't a Color variant
    passed `check` then crashed codegen ("not in scope"). It must be a check-time
    error that NAMES the legal variants (R-08)."""
    codes = _lint_codes(_ENUM_PROG.format(LET="main let hue immutable Color purple"))
    bad = [m for c, m in codes if c == "SS1033" and "not a variant of enum 'Color'" in m]
    assert bad, f"invalid enum variant not rejected: {codes}"
    assert "green, red" in bad[0], "diagnostic must list the legal variants (R-08)"


def test_r08_invalid_enum_variant_in_call_arg_is_check_error():
    src = (_ENUM_PROG.format(LET="main let hue immutable Color red\nmain do useColor")
           + "useColor is call\nuseColor in main\nuseColor invokes console.writeLine\n"
             "useColor arg text Color purple\n")
    codes = _lint_codes(src)
    assert any(c == "SS1033" and "value 'purple'" in m for c, m in codes), codes


def test_r08_valid_variant_and_binding_ref_are_accepted():
    """A declared variant and a genuine binding reference must NOT be flagged."""
    assert not [c for c, _ in _lint_codes(
        _ENUM_PROG.format(LET="main let hue immutable Color green")) if c == "SS1033"]
    # a binding that holds a Color, referenced by another let, is not a variant typo.
    src = _ENUM_PROG.format(
        LET="main let baseHue immutable Color red\nmain let hue immutable Color baseHue")
    assert not [c for c, _ in _lint_codes(src) if c == "SS1033"]


# --- R-04: `scaffold --name` re-homes the project/module to match `new <Name>` ---

def test_r04_scaffold_name_rehomes_project_and_module():
    """R-04: a scaffold ships a hardcoded project name (`JsonOutputScaffold`) that
    collides with the agent's `new <Name>` project. `scaffold --name <Name>` renames
    the project to <Name> and the module to <name> (the `new` convention), so the
    scaffold composes with the project instead of clashing on two `project` rows. The
    result is still check-green; without `--name` the original name is preserved."""
    out = subprocess.run([sys.executable, SC, "scaffold", "json-output", "--name", "Myapp"],
                         capture_output=True, text=True, encoding="utf-8").stdout
    assert "Myapp is project" in out and "Myapp module myapp" in out
    assert "myapp is module" in out
    assert "JsonOutputScaffold" not in out and "jsonOutputModule" not in out
    # still check-green
    chk = subprocess.run([sys.executable, SC, "check", "-", "--json"],
                         input=out, capture_output=True, text=True, encoding="utf-8")
    assert json.loads(chk.stdout).get("errorCount") == 0
    # default (no --name) keeps the original project name.
    default = subprocess.run([sys.executable, SC, "scaffold", "json-output"],
                             capture_output=True, text=True, encoding="utf-8").stdout
    assert "JsonOutputScaffold is project" in default


# --- R-05: `--json` parity (describe gains a structured envelope) ---

_DESC_PROG = (
    "P is project\nP module m\nP target console\nP entry main\n"
    "m is module\nm path m\nm exports main\nm purpose \"p\"\nm invariant \"i\"\n"
    "ExitCode is alias\nExitCode for Int32\n"
    "main is operation\nmain out ExitCode\nmain async no\n"
    "main purpose \"the main op\"\nmain invariant \"i\"\n"
    "main let z immutable ExitCode 0\nmain return z\n")


def test_r05_describe_has_json_parity(tmp_path):
    """R-05: `describe` emitted plain text only — no `--json`. It now has parity: a
    `sem.describe.v1` envelope for a program entity, a builtin signature, and an
    unknown entity, while the plain form is unchanged."""
    p = tmp_path / "d.sem"
    p.write_text(_DESC_PROG, encoding="utf-8")

    def describe_json(entity):
        r = subprocess.run([sys.executable, SC, "describe", str(p), entity, "--json"],
                           capture_output=True, text=True, encoding="utf-8")
        return r.returncode, json.loads(r.stdout)

    rc, d = describe_json("main")
    assert rc == 0 and d["surface"] == "sem.describe.v1"
    assert d["kind"] == "operation" and d.get("description")
    rc, d = describe_json("math.divideInt64")
    assert rc == 0 and d["kind"] == "intrinsic" and d["source"] == "signature"
    rc, d = describe_json("nope")
    assert rc == 2 and d.get("ok") is False and d["status"] == "unknown-entity"
    # plain (non-json) form unchanged.
    plain = subprocess.run([sys.executable, SC, "describe", str(p), "main"],
                           capture_output=True, text=True, encoding="utf-8")
    assert plain.returncode == 0 and "operation" in plain.stdout


# --- R-11: an undefined webServer route handler is a check (not codegen) error ---

def _webserver(route_handler, extra="", imports=""):
    return (
        "W is project\nW module m\nW target webServer\nW entry api\n"
        "m is module\nm path m\nm exports api\nm purpose \"p\"\nm invariant \"i\"\n"
        + imports +
        "HttpRequest is alias\nHttpRequest for OpaquePointer\n"
        "HttpResponse is alias\nHttpResponse for OpaquePointer\n"
        "api is webServer\napi host \"0.0.0.0\"\napi port 8080\n"
        f"api route GET \"/x\" {route_handler}\n" + extra)


_REAL_HANDLER = (
    "realHandler is operation\nrealHandler in request HttpRequest\n"
    "realHandler in response HttpResponse\nrealHandler out Int32\n"
    "realHandler async no\nrealHandler purpose \"p\"\nrealHandler invariant \"i\"\n"
    "realHandler let st immutable Int32 200\nrealHandler return st\n")


def test_r11_undefined_route_handler_is_a_check_error():
    """R-11 (Root A): an undefined route handler was caught only at codegen
    ("build, not check") — a false green. It is now SS2617 in the static lint."""
    codes = _lint_codes(_webserver("missingHandler"))
    assert any(c == "SS2617" and "missingHandler" in m for c, m in codes), codes
    # a defined handler resolves cleanly.
    assert not [c for c, _ in _lint_codes(
        _webserver("realHandler", extra=_REAL_HANDLER)) if c == "SS2617"]


def test_r11_defers_on_a_partial_multi_module_view():
    """R-15: a single-file check of an app whose handler lives in an imported sibling
    module must NOT false-flag it — the handler resolves only in the composed
    project. A non-stdlib import of an absent module defers the check."""
    src = _webserver("homePageHandler",
                     imports="m imports pages app.demo.pages\n")
    assert not [c for c, _ in _lint_codes(src) if c == "SS2617"], \
        "must defer when the handler may live in an absent imported module"


# --- R-09: `fix`/`patch` auto-inserts the missing `branch ifError` error path ---

_SS3501_PROG = (
    "P is project\nP module m\nP target console\nP entry main\n"
    "m is module\nm path m\nm exports main\nm purpose \"p\"\nm invariant \"i\"\n"
    "ExitCode is alias\nExitCode for Int32\n"
    "ConsoleWriteError is error\n"
    "stdoutWriter is capability\nstdoutWriter grants write console.stdout\n"
    "main is operation\nmain out ExitCode\nmain effect write console.stdout\n"
    "main uses stdoutWriter\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
    "main let greeting immutable String \"hi\"\nmain let okCode immutable ExitCode 0\n"
    "main do writeIt\nmain return okCode\n"
    "writeIt is call\nwriteIt in main\nwriteIt invokes console.writeLine\n"
    "writeIt arg text String greeting\nwriteIt catch werr ConsoleWriteError\n")


def test_r09_fix_plan_emits_the_missing_branch_iferror_edits():
    prog = semanticscript.parse(_SS3501_PROG)
    diag = next(d for d in semanticscript.lint(prog) if d.code == "SS3501")
    edits = semanticscript._fix_edits_for(diag, prog)
    blob = " ".join(e.get("new", "") for e in edits)
    assert "branch ifError writeIt goto writeItFailed" in blob
    assert "at writeItFailed return" in blob
    assert any("FailCode" in e.get("new", "") for e in edits), "no failure code synthesized"


def test_r09_fix_then_patch_resolves_ss3501_and_stays_lowerable(tmp_path):
    p = tmp_path / "fallible.sem"
    p.write_text(_SS3501_PROG, encoding="utf-8")
    fix = subprocess.run([sys.executable, SC, "fix", str(p), "--include-warnings",
                          "--json"], capture_output=True, text=True, encoding="utf-8")
    plan = json.loads(fix.stdout)
    assert plan.get("planUsable") is True
    planpath = tmp_path / "plan.json"
    planpath.write_text(fix.stdout, encoding="utf-8")
    patch = subprocess.run([sys.executable, SC, "patch", str(planpath), "--apply"],
                           capture_output=True, text=True, encoding="utf-8")
    assert patch.returncode == 0, patch.stdout
    # SS3501 is gone and the repaired program is check-clean AND lowers.
    repaired = semanticscript.parse(p.read_text(encoding="utf-8"))
    diags = semanticscript.lint(repaired)
    assert not any(d.code == "SS3501" for d in diags)
    assert not [d for d in diags if d.severity == "error"]
    semanticscript.lower_to_llvm(repaired)


@pytest.mark.parametrize("pattern", SCAFFOLDS)
def test_r17_scaffold_output_is_fmt_canonical(pattern):
    """R-17: `cmd_scaffold` advertises "canonical" output, but emitted templates in
    authoring order — so a freshly-scaffolded, check-GREEN program failed
    `fmt --check`, breaking the scaffold->check->fmt loop an agent runs every time.
    The CLI now emits the canonical form: check-clean AND fmt-clean."""
    src = subprocess.run([sys.executable, SC, "scaffold", pattern],
                         capture_output=True, text=True, encoding="utf-8").stdout
    assert src.strip(), f"scaffold {pattern!r} produced no output"
    # check-green
    chk = subprocess.run([sys.executable, SC, "check", "-", "--json"],
                         input=src, capture_output=True, text=True, encoding="utf-8")
    assert json.loads(chk.stdout).get("errorCount") == 0, f"{pattern} not check-green"
    # and fmt-canonical: a second fmt pass is a no-op (idempotent canonical form).
    prog = semanticscript.parse(src)
    assert semanticscript.format_program(prog).strip() == src.strip(), (
        f"scaffold {pattern!r} output is not fmt-canonical (would drift on fmt --check)")
