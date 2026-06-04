#!/usr/bin/env python3
"""Normative compiler/language-standard requirements (BIN-* / AQ-*).

The organizing contract is check ⊇ codegen: anything that passes `check` must
lower and run. Each test pins one normative requirement from the trial reframing.
"""
import importlib

import pytest

semanticscript = importlib.import_module("semanticscript")


# --- AQ-1: camelCase-canonical names; SS0002 names the conforming spelling ---

def test_aq1_camel_case_suggestion():
    f = semanticscript._camel_case_suggestion
    assert f("helper_op") == "helperOp"
    assert f("user_id") == "userId"
    assert f("my-value") == "myValue"
    assert f("already_camelCase") == "alreadyCamelCase"
    assert f("alreadyFine") is None          # valid -> no suggestion
    assert f("__") is None                    # nothing usable


def test_aq1_ss0002_names_the_camel_form():
    src = ("P is project\nP module m\nP target console\nP entry main\n"
           "m is module\nm path x\nm exports main\n"
           "bad_name is operation\nbad_name out Int32\nbad_name async no\n"
           "bad_name return zeroLit\n"
           "zeroLit is storage\nzeroLit scope module\nzeroLit type Int32\n"
           "zeroLit value 0\n")
    with pytest.raises(semanticscript.EavError) as exc:
        semanticscript.parse(src)
    assert exc.value.code == "SS0002"
    assert "bad_name" in str(exc.value) and "badName" in str(exc.value)


# --- AQ-2: effect coverage counts a module-qualified (imported) capability ---

_AQ2 = (
    "P is project\nP module m\nP target console\nP entry main\n"
    "m is module\nm path x\nm exports main\nm purpose \"p\"\nm invariant \"i\"\n"
    "ExitCode is alias\nExitCode for Int32\nConsoleWriteError is error\n"
    "writeCap is capability\nwriteCap grants write console.stdout\n"
    "main is operation\nmain out ExitCode\nmain effect write console.stdout\n"
    "main uses {USES}\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
    "main let h immutable String \"hi\"\nmain let z immutable ExitCode 0\n"
    "main do w\nmain return z\n"
    "w is call\nw in main\nw invokes console.writeLine\nw arg text String h\n"
    "w catch e ConsoleWriteError\n"
)


def _codes(src):
    return {d.code for d in semanticscript.lint(semanticscript.parse(src))}


def test_aq2_qualified_imported_capability_covers_effect():
    # `uses authMod.writeCap` (imported) resolves to the bare capability.
    assert "SS1708" not in _codes(_AQ2.replace("{USES}", "authMod.writeCap"))
    # bare reference still works.
    assert "SS1708" not in _codes(_AQ2.replace("{USES}", "writeCap"))


def test_aq2_genuinely_missing_capability_still_uncovered():
    # a qualified name whose tail names no capability stays uncovered (sound) —
    # this fixture declares NO imports, so an unresolved `uses` is a real error,
    # not a deferred import. SS1708 is a deny-tier hard error, raised by lint.
    with pytest.raises(semanticscript.EavError) as exc:
        semanticscript.lint(semanticscript.parse(
            _AQ2.replace("{USES}", "authMod.noSuchCap")))
    assert exc.value.code == "SS1708"


# AQ-2 (the pervasive case): single-file inspection of a module that USES a
# capability defined in another module (imported) must not false-error SS1708 —
# the capability is genuinely absent from the single file, so coverage is deferred
# to the project-level compose.
_AQ2_IMPORTED = (
    "storeModule is module\nstoreModule path app.store\n"
    "storeModule imports auth app.auth\nstoreModule exports saveItem\n"
    "storeModule purpose \"p\"\nstoreModule invariant \"i\"\n"
    "ConsoleWriteError is error\nExitCode is alias\nExitCode for Int32\n"
    "saveItem is operation\nsaveItem out ExitCode\n"
    "saveItem effect write console.stdout\nsaveItem uses auth.stdoutWriter\n"
    "saveItem async no\nsaveItem purpose \"p\"\nsaveItem invariant \"i\"\n"
    "saveItem let line immutable String \"saved\"\n"
    "saveItem let z immutable ExitCode 0\nsaveItem do w\nsaveItem return z\n"
    "w is call\nw in saveItem\nw invokes console.writeLine\nw arg text String line\n"
    "w catch e ConsoleWriteError\n"
)


def test_aq2_single_file_imported_capability_not_false_uncovered():
    # `uses auth.stdoutWriter` — auth is a declared import alias; the capability
    # lives in module app.auth, absent in this single file. Must NOT raise SS1708.
    assert "SS1708" not in _codes(_AQ2_IMPORTED)


def test_aq2_unresolved_uses_without_imports_still_errors():
    # Remove the `imports` row: now the unresolved `uses auth.stdoutWriter` is not
    # a deferred import — it is a genuine coverage gap, so SS1708 still fires.
    no_imports = _AQ2_IMPORTED.replace(
        "storeModule imports auth app.auth\n", "")
    with pytest.raises(semanticscript.EavError) as exc:
        semanticscript.lint(semanticscript.parse(no_imports))
    assert exc.value.code == "SS1708"


# --- BIN-2: check ⊇ codegen — no program reaches a RAW codegen exception ---

def test_bin2_unexpected_codegen_exception_becomes_coded_ss5001():
    # Any unexpected backend failure (any site, any exception type — here a
    # KeyError, which the old narrow wrapper did NOT catch) must surface as a
    # coded SS5001, never a raw traceback.
    prog = semanticscript.parse(open("examples/hello_world.sem", encoding="utf-8").read())
    orig = semanticscript.EavCodegen.generate
    semanticscript.EavCodegen.generate = lambda self: (_ for _ in ()).throw(
        KeyError("synthetic backend blowup"))
    try:
        with pytest.raises(semanticscript.EavError) as exc:
            semanticscript.lower_to_llvm(prog)
        assert exc.value.code == "SS5001"
        assert "KeyError" in str(exc.value)
    finally:
        semanticscript.EavCodegen.generate = orig


def test_bin2_check_clean_console_examples_all_lower():
    # The corpus soundness assertion: every check-clean console-target example
    # lowers without raising. A check≠codegen regression (a program that passes
    # check but cannot lower) turns this red.
    import glob
    lowered = 0
    for path in sorted(glob.glob("examples/*.sem")):
        src = open(path, encoding="utf-8").read()
        try:
            prog = semanticscript.parse(src)
        except semanticscript.EavError:
            continue  # not parseable (negative fixture) — out of scope
        if semanticscript._program_target(prog) != "console":
            continue
        errs = [d for d in semanticscript.lint(prog) if d.severity == "error"]
        if errs:
            continue  # not check-clean — check is allowed to reject it
        semanticscript.lower_to_llvm(prog)  # must not raise
        lowered += 1
    assert lowered >= 50, f"expected to lower many console examples, got {lowered}"


# --- BIN-1: webServer lowers its declared route table (static + dynamic) ---

def test_bin1_webserver_route_table_lowers_static_and_dynamic_routes():
    # The webServer target must lower EVERY declared route — including dynamic
    # `:param` routes — into the dispatcher's route table. taskforge-web mixes
    # static (/api/todos) and dynamic (/api/todos/:id, /assets/:filename) routes;
    # the live dispatcher matches them (a GET /api/todos/:id returns the handler's
    # 501 stub, not a 404), and here we pin that they reach the lowered IR table.
    import os
    app = "apps/taskforge-web"
    if not os.path.isdir(app):
        pytest.skip("taskforge-web app not present")
    pytest.importorskip("llvmlite")
    prog = semanticscript.parse(semanticscript.load_project(app))
    prog.source_root = semanticscript._program_source_root_for_path(app)
    assert semanticscript._program_target(prog) == "webServer"
    ir = str(semanticscript.lower_to_llvm(prog))
    for route in ("/api/todos", "/api/todos/:id",
                  "/api/todos/:id/complete", "/assets/:filename"):
        assert route in ir, f"route {route!r} was not lowered into the dispatch table"


# --- AQ-4: the test runner realizes ALL declared lanes (incl. golden snapshots) ---

_GOLDEN_OP = (
    "P is project\nP module m\nP target console\nP entry goldenOp\n"
    "m is module\nm path x\nm exports goldenOp\nm purpose \"p\"\nm invariant \"i\"\n"
    "ExitCode is alias\nExitCode for Int32\nConsoleWriteError is error\n"
    "stdoutWriter is capability\nstdoutWriter grants write console.stdout\n"
    "goldenOp is operation\ngoldenOp tag test golden\ngoldenOp out ExitCode\n"
    "goldenOp effect write console.stdout\ngoldenOp uses stdoutWriter\n"
    "goldenOp async no\ngoldenOp purpose \"p\"\ngoldenOp invariant \"i\"\n"
    "goldenOp let g immutable String \"golden line\"\n"
    "goldenOp let z immutable ExitCode 0\ngoldenOp do w\ngoldenOp return z\n"
    "w is call\nw in goldenOp\nw invokes console.writeLine\nw arg text String g\n"
    "w catch e ConsoleWriteError\n"
)


def test_aq4_lane_detection_reads_all_tag_tokens():
    # `tag test golden` (one row, two tokens) must land in the golden lane — not
    # silently collapse to unit by reading only the first token.
    prog = semanticscript.parse(_GOLDEN_OP)
    assert semanticscript.discover_tests(prog) == {"golden": ["goldenOp"]}
    # a plain `tag test` is still a unit test.
    unit = semanticscript.parse(_GOLDEN_OP.replace(
        "goldenOp tag test golden", "goldenOp tag test"))
    assert list(semanticscript.discover_tests(unit).keys()) == ["unit"]


def test_aq4_golden_lane_compares_snapshot(tmp_path):
    pytest.importorskip("llvmlite")
    import os
    (tmp_path / "tests" / "golden").mkdir(parents=True)
    prog = semanticscript.parse(_GOLDEN_OP)
    prog.source_root = str(tmp_path)
    gp = tmp_path / "tests" / "golden" / "goldenOp.out"

    def status():
        return semanticscript.run_tests(prog)["tests"][0]

    # no snapshot -> the golden lane fails (a golden test needs a pinned snapshot).
    rec = status()
    assert rec["status"] == "fail" and rec["golden"] == "missing-golden"
    # matching snapshot -> pass.
    gp.write_text("golden line\n", newline="\n")
    rec = status()
    assert rec["status"] == "pass" and rec["golden"] == "matched"
    # divergent snapshot -> fail (exit 0 alone is NOT enough for the golden lane).
    gp.write_text("DIFFERENT\n", newline="\n")
    rec = status()
    assert rec["status"] == "fail" and rec["golden"] == "snapshot-mismatch"


# --- BIN-3: a handle->String view (c.cString) may not escape its borrowed source ---

_CSTRING_OP_HEAD = (
    "P is project\nP module m\nP target console\nP entry main\n"
    "m is module\nm path x\nm exports main\nm purpose \"p\"\nm invariant \"i\"\n"
    "ConsoleWriteError is error\nExitCode is alias\nExitCode for Int32\n"
    "stdoutWriter is capability\nstdoutWriter grants write console.stdout\n"
    "{LEAK}"
    "main is operation\nmain out Int32\nmain async no\nmain purpose \"p\"\n"
    "main invariant \"i\"\nmain let z immutable Int32 0\nmain return z\n"
)
# an op that allocates an owned handle, views it as a String via c.cString, and
# RETURNS the String out — escaping the op-local handle (a dangling scratch view).
_LEAK_ESCAPE = (
    "leak is operation\nleak out String\nleak async no\nleak purpose \"p\"\n"
    "leak invariant \"i\"\nleak do allocCall\nleak do viewCall\nleak return viewStr\n"
    "allocCall is call\nallocCall in leak\nallocCall invokes bcrypt.sessionTokenOwned\n"
    "allocCall out h OpaquePointer\nallocCall owns h\nallocCall cleanedBy freeDefer\n"
    "viewCall is call\nviewCall in leak\nviewCall invokes c.cString\n"
    "viewCall arg pointer OpaquePointer h\nviewCall out viewStr String\n"
    "freeDeferWorker is call\nfreeDeferWorker in leak\n"
    "freeDeferWorker invokes bcrypt.freeString\n"
    "freeDeferWorker arg handle OpaquePointer h\nfreeDeferWorker discards \"x\"\n"
    "freeDefer is cleanup\nfreeDefer in leak\nfreeDefer call freeDeferWorker\n"
    "freeDefer cleans h\n"
)


def test_bin3_cstring_view_escaping_its_handle_is_rejected():
    # Returning a c.cString String out of the op that owns the handle would let the
    # borrowed view outlive (dangle past) its source — SS1560.
    with pytest.raises(semanticscript.EavError) as exc:
        semanticscript.lint(semanticscript.parse(
            _CSTRING_OP_HEAD.replace("{LEAK}", _LEAK_ESCAPE)))
    assert exc.value.code == "SS1560"


def test_bin3_cstring_seeded_as_noescape_view_builtin():
    assert "c.cString" in semanticscript._INTRINSIC_VIEW_NOESCAPE_BUILTINS
