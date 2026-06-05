#!/usr/bin/env python3
"""RUN-13 follow-ups: FIX-2 (build identity), TEST-2 (test lanes), AQ-7 (trusted ctors)."""
import glob
import importlib
import json
import os
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SC = os.path.join(ROOT, "semanticscript", "compiler", "semanticscript.py")

_CONSOLE = (
    "P is project\nP module m\nP target console\nP entry main\n"
    "m is module\nm path x\nm exports main\nm purpose \"p\"\nm invariant \"i\"\n"
    "ExitCode is alias\nExitCode for Int32\n"
    "stdoutWriter is capability\nstdoutWriter grants write console.stdout\n"
    "ConsoleWriteError is error\n"
    "main is operation\nmain out ExitCode\nmain effect write console.stdout\n"
    "main uses stdoutWriter\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
    "main let h immutable String \"hi\"\nmain let z immutable ExitCode 0\n"
    "main do w\nmain return z\n"
    "w is call\nw in main\nw invokes console.writeLine\nw arg text String h\n"
    "w catch e ConsoleWriteError\n"
)


# --- FIX-2: build surfaces a content-addressed identity ---

def test_fix2_build_surfaces_reproducible_identity(tmp_path):
    if semanticscript._find_c_compiler() is None:
        pytest.skip("no C compiler to build")
    p = tmp_path / "p.sem"
    p.write_text(_CONSOLE, encoding="utf-8")

    def build():
        r = subprocess.run([sys.executable, SC, "build", str(p), "--json"],
                           capture_output=True, text=True, encoding="utf-8", timeout=120)
        return json.loads(r.stdout)

    d1 = build()
    ident = d1.get("identity") or {}
    assert len(ident.get("irSha256") or "") == 64
    assert ident.get("contractVersion") and ident.get("releaseVersion")
    # reproducible: same source+toolchain -> same IR hash.
    assert build()["identity"]["irSha256"] == ident["irSha256"]


def test_fix2_build_identity_unit():
    prog = semanticscript.parse(_CONSOLE)
    ident = semanticscript._build_identity(prog)
    assert len(ident["irSha256"]) == 64
    assert ident["contractVersion"] == semanticscript.CONTRACT_VERSION


# --- AQ-9 / S4: every scaffold (incl. compositions) is reachable from `skills` ---

def test_aq9_every_scaffold_has_a_reachable_skill_recipe():
    """AQ-9 / S4 (the recurring 'idiom not reachable from the tool' dead-end): every
    scaffold pattern — especially the multi-subsystem composition ones (db-roundtrip,
    json-output, logged-op, handler-route) — must be discoverable as a `skills`
    recipe, not only via `scaffold <name>`. A composition idiom that can't be found
    from the discovery surface is what burned whole runs."""
    patterns = list(getattr(semanticscript, "SCAFFOLD_PATTERNS", ()))
    assert patterns, "no scaffold patterns"
    skills = semanticscript.EAV_SKILLS
    for p in patterns:
        key = f"eav-scaffold-{p}"
        assert key in skills, f"scaffold {p!r} has no reachable skill recipe"
        assert skills[key].get("body"), f"skill {key} has no body"
        # the recipe must point back at the runnable template.
        assert p in skills[key]["body"], f"skill {key} does not name `scaffold {p}`"
        guards = skills[key].get("guards") or []
        assert guards, f"skill {key} has no executable guard references"
        assert "Executable guards:" in skills[key]["body"]
        for guard in guards:
            guard_file = guard.split("::", 1)[0].replace("/", os.sep)
            assert os.path.exists(os.path.join(ROOT, guard_file)), guard
    assert any("golden" in g for g in
               skills["eav-scaffold-db-roundtrip"]["guards"])


def test_w2g1_subsystem_cookbook_recipes_carry_guard_sources():
    """W2-G1: cookbook recipes must name the tests/goldens that keep them true."""
    for family in ["json", "sqlite", "log", "assert", "test"]:
        key = f"eav-subsystem-{family}"
        skill = semanticscript.EAV_SKILLS[key]
        assert "Executable guards:" in skill["body"]
        assert skill.get("guards"), key
        for guard in skill["guards"]:
            guard_file = guard.split("::", 1)[0].replace("/", os.sep)
            assert os.path.exists(os.path.join(ROOT, guard_file)), guard


def test_aq9_scaffold_skill_is_served_by_the_skills_command():
    """The recipe is actually reachable through the CLI surface an agent queries."""
    proc = subprocess.run([sys.executable, SC, "skills", "eav-scaffold-db-roundtrip",
                           "--json"], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    d = json.loads(proc.stdout)
    blob = json.dumps(d)
    assert "db-roundtrip" in blob and "sqlite" in blob.lower()
    assert any("golden" in g for g in d["skills"][0]["guards"])


# --- NS-1/AQ-1: identical duplicate type declarations compose across modules ---

def _two_module_project(tmp_path, b_exitcode_base):
    proj = tmp_path / "p"
    (proj / "src").mkdir(parents=True)
    (proj / "build.sem").write_text(
        "Proj is project\nProj module modA\nProj target console\nProj entry main\n",
        encoding="utf-8")
    (proj / "src" / "a.sem").write_text(
        "modA is module\nmodA path src.a\nmodA imports modB src.b\n"
        "modA exports main\nmodA purpose \"p\"\nmodA invariant \"i\"\n"
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\n"
        "main invariant \"i\"\nmain let z immutable ExitCode 0\nmain return z\n",
        encoding="utf-8")
    (proj / "src" / "b.sem").write_text(
        "modB is module\nmodB path src.b\nmodB exports helper\n"
        "modB purpose \"p\"\nmodB invariant \"i\"\n"
        f"ExitCode is alias\nExitCode for {b_exitcode_base}\n"
        "helper is operation\nhelper out ExitCode\nhelper async no\n"
        "helper purpose \"p\"\nhelper invariant \"i\"\n"
        "helper let z immutable ExitCode 0\nhelper return z\n",
        encoding="utf-8")
    return proj


def test_ns1_identical_duplicate_type_decls_compose(tmp_path):
    """NS-1/AQ-1 (R-006): two modules that each declare the SAME standard type
    (`ExitCode is alias for Int32` — the scaffold-taught alias pain) must compose:
    identical declarations name the same type, so the flat-namespace `duplicate is`
    error is wrong. The composed project checks clean."""
    proj = _two_module_project(tmp_path, "Int32")
    src = semanticscript.load_project(str(proj))
    # the dedup elides the byte-identical second ExitCode block.
    assert src.count("ExitCode is alias") == 1
    prog = semanticscript.parse(src)
    assert not [d for d in semanticscript.lint(prog) if d.severity == "error"]


def test_ns1_conflicting_redeclaration_still_errors(tmp_path):
    """A *differing* redeclaration (ExitCode for Int64 vs Int32) is a genuine
    conflict and must still reach the duplicate-`is` hard error — the dedup only
    elides byte-identical copies, never merges conflicting ones."""
    proj = _two_module_project(tmp_path, "Int64")
    with pytest.raises(semanticscript.EavError) as exc:
        semanticscript.parse(semanticscript.load_project(str(proj)))
    assert "duplicate `is` row" in str(exc.value)


def test_ns1_dedup_is_a_noop_without_duplicates():
    """Blast-radius guard: a source with no duplicate type declarations passes
    through unchanged (so every existing project's composition is byte-identical)."""
    src = ("m is module\nm path m\nExitCode is alias\nExitCode for Int32\n"
           "Other is alias\nOther for Int64\nmain is operation\nmain out ExitCode\n")
    assert semanticscript._dedupe_identical_type_declarations(src) == src


# --- NS-1/AQ-1: module-private operation names are module-scoped, not flat ---

def _two_module_private_helper_project(tmp_path):
    """A project whose two modules each declare a DIFFERENT module-private helper
    operation under the same bare name `openDb`, each invoked in-module — the
    run-15 case the flat namespace rejected with `duplicate is row`."""
    proj = tmp_path / "p"
    (proj / "src").mkdir(parents=True)
    (proj / "build.sem").write_text(
        "Proj is project\nProj module modA\nProj module modB\n"
        "Proj target console\nProj entry main\n", encoding="utf-8")
    (proj / "src" / "a.sem").write_text(
        "modA is module\nmodA path src.a\nmodA exports main\n"
        "modA purpose \"p\"\nmodA invariant \"i\"\nExitCode is alias\nExitCode for Int32\n"
        "openDb is operation\nopenDb out Int32\nopenDb async no\nopenDb purpose \"A open\"\n"
        "openDb invariant \"i\"\nopenDb let z immutable Int32 7\nopenDb return z\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\n"
        "main invariant \"i\"\nmain let z immutable ExitCode 0\nmain do c1\nmain return z\n"
        "c1 is call\nc1 in main\nc1 invokes openDb\nc1 out r Int32\n", encoding="utf-8")
    (proj / "src" / "b.sem").write_text(
        "modB is module\nmodB path src.b\nmodB exports helper\n"
        "modB purpose \"p\"\nmodB invariant \"i\"\n"
        "openDb is operation\nopenDb out Int32\nopenDb async no\nopenDb purpose \"B open\"\n"
        "openDb invariant \"i\"\nopenDb let z immutable Int32 9\nopenDb return z\n"
        "helper is operation\nhelper out Int32\nhelper async no\nhelper purpose \"p\"\n"
        "helper invariant \"i\"\nhelper let z immutable Int32 0\nhelper do c2\nhelper return z\n"
        "c2 is call\nc2 in helper\nc2 invokes openDb\nc2 out r Int32\n", encoding="utf-8")
    return proj


def test_ns1_module_private_operation_name_reused_across_modules(tmp_path):
    """NS-1/AQ-1: two modules may each define a module-private operation `openDb`
    with different bodies; the project composes, checks clean, and each module's
    in-module `invokes openDb` resolves to ITS OWN definition — not the other
    module's (the flat-namespace bug that forced manual prefixing of every helper)."""
    proj = _two_module_private_helper_project(tmp_path)
    prog = semanticscript.parse(semanticscript.load_project(str(proj)))
    assert not [d for d in semanticscript.lint(prog) if d.severity == "error"]
    # The first module keeps the bare symbol; the second is module-qualified.
    a_target = prog.entities["c1"].fact("invokes").payload[0]
    b_target = prog.entities["c2"].fact("invokes").payload[0]
    assert a_target != b_target, "both calls collapsed onto one openDb (flat namespace)"
    assert prog.entities[a_target].fact("purpose").payload == ['"A open"']
    assert prog.entities[b_target].fact("purpose").payload == ['"B open"']


def test_ns1_same_module_duplicate_operation_still_errors():
    """Per-module uniqueness is still enforced: re-declaring `openDb` inside ONE
    module is a genuine duplicate, not a module-scoped distinct operation."""
    src = ("m is module\nm path m\nm purpose \"p\"\nm invariant \"i\"\n"
           "openDb is operation\nopenDb out Int32\nopenDb async no\n"
           "openDb purpose \"a\"\nopenDb invariant \"i\"\nopenDb let z immutable Int32 0\nopenDb return z\n"
           "openDb is operation\nopenDb out Int32\nopenDb async no\n"
           "openDb purpose \"b\"\nopenDb invariant \"i\"\nopenDb let z immutable Int32 1\nopenDb return z\n")
    with pytest.raises(semanticscript.EavError) as exc:
        semanticscript.parse(src, validate=False)
    assert "duplicate `is` row" in str(exc.value)


def test_ns1_exported_operation_collision_still_errors():
    """Scoping is for module-PRIVATE helpers only. An *exported* operation is part
    of the module's public API (importers resolve it by its bare name), so a
    cross-module clash on an exported name is a real conflict and still errors —
    it is not silently renamed out from under its importers."""
    src = ("a is module\na path a\na exports openDb\na purpose \"p\"\na invariant \"i\"\n"
           "openDb is operation\nopenDb out Int32\nopenDb async no\n"
           "openDb purpose \"a\"\nopenDb invariant \"i\"\nopenDb let z immutable Int32 0\nopenDb return z\n"
           "b is module\nb path b\nb exports openDb\nb purpose \"p\"\nb invariant \"i\"\n"
           "openDb is operation\nopenDb out Int32\nopenDb async no\n"
           "openDb purpose \"b\"\nopenDb invariant \"i\"\nopenDb let z immutable Int32 1\nopenDb return z\n")
    with pytest.raises(semanticscript.EavError) as exc:
        semanticscript.parse(src, validate=False)
    assert "duplicate `is` row" in str(exc.value)


def test_ns1_single_module_namespace_is_unchanged():
    """Blast-radius guard: with no cross-module reuse, no symbol is renamed — every
    entity keeps its bare name, so existing single-module programs are untouched."""
    src = ("m is module\nm path m\n"
           "openDb is operation\nopenDb out Int32\nopenDb async no\n"
           "openDb purpose \"a\"\nopenDb invariant \"i\"\nopenDb let z immutable Int32 0\nopenDb return z\n")
    prog = semanticscript.parse(src, validate=False)
    assert sorted(prog.entities) == ["m", "openDb"]
    assert prog.entity_module == {"m": "m", "openDb": "m"}


def test_ns1_module_private_operation_names_build_and_run_distinct_symbols(tmp_path):
    """The namespace fix reaches native codegen: two private `openDb` helpers with
    different module owners both lower and link, then main observes both values."""
    if semanticscript._find_c_compiler() is None:
        pytest.skip("no C compiler available for native namespace build")
    proj = tmp_path / "p"
    (proj / "src").mkdir(parents=True)
    (proj / "build.sem").write_text(
        "Proj is project\nProj module modA\nProj module modB\n"
        "Proj target console\nProj entry main\n", encoding="utf-8")
    (proj / "src" / "a.sem").write_text(
        "modA is module\nmodA path src.a\nmodA imports modB src.b\n"
        "modA exports main\nmodA purpose \"p\"\nmodA invariant \"i\"\n"
        "ExitCode is alias\nExitCode for Int32\n"
        "stdoutWriter is capability\nstdoutWriter grants write console.stdout\n"
        "openDb is operation\nopenDb out Int64\nopenDb async no\n"
        "openDb purpose \"A open\"\nopenDb invariant \"i\"\n"
        "openDb let z immutable Int64 7\nopenDb return z\n"
        "main is operation\nmain out ExitCode\nmain async no\n"
        "main effect write console.stdout\nmain uses stdoutWriter\n"
        "main purpose \"p\"\nmain invariant \"i\"\n"
        "main let ok immutable ExitCode 0\n"
        "main do aCall\nmain do bCall\nmain do addCall\nmain do writeCall\n"
        "main return ok\n"
        "aCall is call\naCall in main\naCall invokes openDb\naCall out aValue Int64\n"
        "bCall is call\nbCall in main\nbCall invokes modB.helper\nbCall out bValue Int64\n"
        "addCall is call\naddCall in main\naddCall invokes math.addInt64\n"
        "addCall arg left Int64 aValue\naddCall arg right Int64 bValue\n"
        "addCall out totalValue Int64\n"
        "writeCall is call\nwriteCall in main\nwriteCall invokes console.writeIntegerLine\n"
        "writeCall arg value Int64 totalValue\n", encoding="utf-8")
    (proj / "src" / "b.sem").write_text(
        "modB is module\nmodB path src.b\nmodB exports helper\n"
        "modB purpose \"p\"\nmodB invariant \"i\"\n"
        "openDb is operation\nopenDb out Int64\nopenDb async no\n"
        "openDb purpose \"B open\"\nopenDb invariant \"i\"\n"
        "openDb let z immutable Int64 9\nopenDb return z\n"
        "helper is operation\nhelper out Int64\nhelper async no\nhelper purpose \"p\"\n"
        "helper invariant \"i\"\nhelper do c2\nhelper return r\n"
        "c2 is call\nc2 in helper\nc2 invokes openDb\nc2 out r Int64\n",
        encoding="utf-8")
    out = proj / ("p.exe" if os.name == "nt" else "p")
    rc = semanticscript.main(["build", str(proj), "--output", str(out), "--json"])
    assert rc == 0
    proc = subprocess.run([str(out)], capture_output=True, text=True,
                          encoding="utf-8")
    assert proc.returncode == 0
    assert proc.stdout.strip() == "16"


# --- WEB-1: startup-owned handle that can't reach handlers is flagged (R-9) ---

def _webserver_with_startup(owns_cleanup: bool):
    """A webServer whose `startup` handler opens+owns a DB handle. With
    owns_cleanup=False it's the R-9 anti-pattern (the handle can't reach request
    handlers); with True it releases the handle in startup (correct)."""
    cleanup_rows = ("initDb defer closeDb\n" if owns_cleanup else "")
    open_cleanup = ("openDb cleanedBy closeDb\n" if owns_cleanup else "")
    cleanup_ent = (
        "closeWorker is call\ncloseWorker in initDb\n"
        "closeWorker invokes sqlite.closeDatabase\n"
        "closeWorker arg database SqliteDatabase dbHandle\n"
        "closeWorker discards \"x\"\n"
        "closeDb is cleanup\ncloseDb in initDb\ncloseDb call closeWorker\n"
        "closeDb cleans dbHandle\ncloseDb because \"release\"\n"
    ) if owns_cleanup else ""
    return (
        "Demo is project\nDemo module m\nDemo target webServer\nDemo entry api\n"
        'm is module\nm path a.b\nm exports api\nm purpose "p"\nm invariant "i"\n'
        "HttpRequest is alias\nHttpRequest for OpaquePointer\n"
        "HttpResponse is alias\nHttpResponse for OpaquePointer\n"
        "ServerContext is alias\nServerContext for OpaquePointer\n"
        "ExitCode is alias\nExitCode for Int32\n"
        "SqliteDatabase is alias\nSqliteDatabase for Int64\n"
        "dbWriter is capability\ndbWriter grants write sqlite.database\n"
        "api is webServer\napi host \"127.0.0.1\"\napi port 8080\n"
        "api startup initDb\napi route GET \"/health\" healthHandler\n"
        "initDb is operation\ninitDb in serverContext ServerContext\ninitDb out ExitCode\n"
        "initDb effect write sqlite.database\ninitDb uses dbWriter\n"
        'initDb async no\ninitDb purpose "open the app db"\ninitDb invariant "i"\n'
        "initDb let okCode immutable ExitCode 0\ninitDb do openDb\n"
        + cleanup_rows +
        "initDb return okCode\n"
        "openDb is call\nopenDb in initDb\nopenDb invokes sqlite.openInMemory\n"
        "openDb out dbHandle SqliteDatabase\nopenDb owns dbHandle\n"
        + open_cleanup + cleanup_ent +
        "healthHandler is operation\nhealthHandler in request HttpRequest\n"
        "healthHandler in response HttpResponse\nhealthHandler out Int32\n"
        'healthHandler async no\nhealthHandler purpose "p"\nhealthHandler invariant "i"\n'
        "healthHandler let status immutable Int32 200\nhealthHandler return status\n")


def test_web1_startup_owned_handle_that_cant_reach_handlers_is_flagged():
    """WEB-1 (R-9): a `startup` handler that owns a resource with no cleanup can't
    propagate it to request handlers (they get only request/response, §14), so the
    app silently gets a fresh/0-byte resource per request. The toolchain must name
    that specific bug (SS2616), not pass silently — and a startup that releases its
    handle is clean."""
    codes = lambda src: {d.code for d in semanticscript.lint(semanticscript.parse(src))}
    assert "SS2616" in codes(_webserver_with_startup(owns_cleanup=False))
    # releasing the handle in startup is the correct lifecycle — no SS2616.
    clean = codes(_webserver_with_startup(owns_cleanup=True))
    assert "SS2616" not in clean and "SS3900" not in clean


def test_web1_does_not_false_positive_the_per_request_pattern():
    """The valid pattern (share a DB path via module storage, open per-request — what
    taskforge-web does) has no startup-owned handle, so it must not trip SS2616."""
    import os
    app = os.path.join(ROOT, "apps", "taskforge-web")
    if not os.path.isdir(app):
        pytest.skip("taskforge-web app fixture not present")
    prog = semanticscript.load_project(app)
    diags = semanticscript.lint(semanticscript.parse(prog))
    assert not [d for d in diags if d.code == "SS2616"], "false-positive on per-request app"


# --- ERG-3: `bench` on a webServer is server-aware, not a silent skip ---

def test_erg3_bench_on_webserver_is_server_aware(tmp_path):
    """ERG-3 (R-12): `bench` skips the in-process run lane for a webServer (it
    doesn't terminate), but must not leave a silent `runMsBest: null` the agent
    reads as "unmeasurable". It now reports `serverAware` + the bounded
    serve->probe->stop lane and the exact commands that DO measure request
    latency."""
    app = os.path.join(ROOT, "apps", "http-runtime-gauntlet")
    if not os.path.isdir(app):
        pytest.skip("http-runtime-gauntlet app fixture not present")
    r = subprocess.run([sys.executable, SC, "bench", app, "--runs", "1", "--json"],
                       capture_output=True, text=True, encoding="utf-8")
    d = json.loads(r.stdout)
    assert d.get("runnable") is False and d.get("serverAware") is True
    assert d.get("serverLane") == "serve-probe-stop"
    assert d.get("serverLaneCommands"), "no actionable commands to measure latency"
    assert "latency" in (d.get("note") or "")


# --- TRUE-1: `task` with no template lists templates (self-describing surface) ---

def test_true1_task_with_no_template_lists_the_catalog():
    """TRUE-1 (R-15): `task` with no template must list the available templates,
    not die with an argparse "required arg" error. A self-describing toolchain has
    to answer "what can I do?" — the way `docs` (no path) returns its catalog."""
    proc = subprocess.run([sys.executable, SC, "task", "--json"],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    d = json.loads(proc.stdout)
    assert d.get("ok") is True and d.get("status") == "catalog"
    assert d.get("templates"), "no templates listed"
    # and a named template still emits its checklist.
    one = d["templates"][0]
    p2 = subprocess.run([sys.executable, SC, "task", one, "--json"],
                        capture_output=True, text=True, encoding="utf-8")
    assert p2.returncode == 0 and json.loads(p2.stdout).get("template") == one


# --- TRUST-1 / BIN-2: a check-clean enum-repr program must lower (no false green) ---

def test_trust1_enum_shadowing_builtin_role_type_lowers():
    """TRUST-1/BIN-2 (R-4): a check-clean program may not crash codegen. A user enum
    whose name shadows a builtin role type (the json scaffold's `JsonValueKind`,
    which normalizes to Int32) had its variant resolution skipped at lowering —
    `let k JsonValueKind objectJson` passed `check` but crashed `run` with
    "objectJson is not in scope (expected an integer binding)". The variant must
    resolve against the declared enum, so the program lowers."""
    src = ("P is project\nP module m\nP target console\nP entry main\n"
           "m is module\nm path m\nm exports main\nm purpose \"p\"\nm invariant \"i\"\n"
           "ExitCode is alias\nExitCode for Int32\n"
           "JsonValueKind is enum\nJsonValueKind variant objectJson\n"
           "JsonValueKind repr objectJson 5\n"
           "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\n"
           "main invariant \"i\"\nmain let k immutable JsonValueKind objectJson\n"
           "main let z immutable ExitCode 0\nmain return z\n")
    prog = semanticscript.parse(src)
    assert not [d for d in semanticscript.lint(prog) if d.severity == "error"]
    # the crux: lowering must not raise the false-green codegen error.
    semanticscript.lower_to_llvm(prog)


def test_trust1_string_literal_to_nontext_type_is_a_check_error():
    """TRUST-1 (R-7): a quoted string literal bound to a non-text type (`let codeVal
    ExitCode ""`) used to pass `check` — the numeric/identifier validators skip
    strings — then crash codegen ("not in scope, expected an integer binding"). It
    must now be a check-time error (SS3306), and a String/text target still accepts
    the literal."""
    bad = ("P is project\nP module m\nP target console\nP entry main\n"
           "m is module\nm path m\nm exports main\nm purpose \"p\"\nm invariant \"i\"\n"
           "ExitCode is alias\nExitCode for Int32\n"
           "g is operation\ng out ExitCode\ng async no\ng purpose \"p\"\ng invariant \"i\"\n"
           "g let codeVal immutable ExitCode \"\"\ng return codeVal\n"
           "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\n"
           "main invariant \"i\"\nmain let z immutable ExitCode 0\nmain return z\n")
    with pytest.raises(semanticscript.EavError) as exc:
        semanticscript.parse(bad)
    assert exc.value.code == "SS3306"
    # a String/text target still accepts a string literal — clean parse.
    semanticscript.parse(
        "P is project\nP module m\nP target console\nP entry main\n"
        "m is module\nm path m\nm exports main\nm purpose \"p\"\nm invariant \"i\"\n"
        "ExitCode is alias\nExitCode for Int32\n"
        "g is operation\ng out String\ng async no\ng purpose \"p\"\ng invariant \"i\"\n"
        "g let s immutable String \"\"\ng return s\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\n"
        "main invariant \"i\"\nmain let z immutable ExitCode 0\nmain return z\n")


def test_trust1_json_output_scaffold_checks_clean_and_lowers():
    """The json-output scaffold (a documented, agent-reachable idiom) must not be a
    false green: it builds a `JsonValueKind` enum + `json.createEmptyDocument` and
    previously crashed `run`/`build` at the enum-repr arg. It must now check clean
    AND lower."""
    src = semanticscript.scaffold("json-output")
    prog = semanticscript.parse(src)
    assert not [d for d in semanticscript.lint(prog) if d.severity == "error"]
    semanticscript.lower_to_llvm(prog)


# --- TEST-2: the runner realizes all declared lanes (not just advertises them) ---

def _lane_op(name, lane):
    return (f"{name} is operation\n{name} out ExitCode\n{name} async no\n"
            f"{name} tag test {lane}\n{name} purpose \"p\"\n{name} invariant \"i\"\n"
            f"{name} let r immutable ExitCode 0\n{name} return r\n")


def test_test2_all_declared_lanes_are_discoverable():
    body = ("P is project\nP module m\nP target console\nP entry uTest\n"
            "m is module\nm path x\nm exports uTest\nm purpose \"p\"\nm invariant \"i\"\n"
            "ExitCode is alias\nExitCode for Int32\n"
            + _lane_op("uTest", "unit").replace("tag test unit", "tag test")
            + _lane_op("cTest", "component") + _lane_op("iTest", "integration")
            + _lane_op("eTest", "e2e") + _lane_op("gTest", "golden"))
    lanes = semanticscript.discover_tests(semanticscript.parse(body))
    # every advertised lane is actually populated from its tag — none collapse away.
    for lane in semanticscript.TEST_LANES:
        assert lane in lanes and lanes[lane], f"lane {lane!r} not realized: {lanes}"


# --- TEST-1 / AQ-4: the runner's verdict is correct (pass/fail/error distinct) ---

def _harness_test_op(name, truth_literal):
    """A standard.test harness op: assertTrue then test.summary, returning the
    failure-count ExitCode. `truth_literal` drives pass (`true`) vs assertion
    failure (`false`) vs can't-isolate (`yes`, an invalid Bool literal)."""
    return (f"{name} is operation\n{name} out ExitCode\n{name} async no\n"
            f"{name} purpose \"p\"\n{name} invariant \"i\"\n{name} tag test\n"
            f"{name} let nm immutable String \"{name}\"\n"
            f"{name} let truth immutable Bool {truth_literal}\n"
            f"{name} do {name}A\n{name} do {name}S\n{name} return {name}C\n"
            f"{name}A is call\n{name}A in {name}\n{name}A invokes test.assertTrue\n"
            f"{name}A arg name String nm\n{name}A arg value Bool truth\n"
            f"{name}S is call\n{name}S in {name}\n{name}S invokes test.summary\n"
            f"{name}S out {name}C ExitCode\n")


def _run_harness_project(tmp_path, ops_src):
    proj = tmp_path / "proj"
    (proj / "src").mkdir(parents=True)
    (proj / "build.sem").write_text(
        "Harn is project\nHarn module harn\nHarn target console\nHarn entry main\n",
        encoding="utf-8")
    (proj / "src" / "harn.sem").write_text(
        "harn is module\nharn path src.harn\nharn exports main\n"
        "harn purpose \"p\"\nharn invariant \"i\"\n"
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\n"
        "main invariant \"i\"\nmain let z immutable ExitCode 0\nmain return z\n",
        encoding="utf-8")
    (proj / "src" / "harn.test.sem").write_text(
        "harnTest is module\nharnTest path src.harnTest\n"
        "harnTest imports test standard.test\n"
        "harnTest exports " + " ".join(name for name, _ in ops_src) + "\n"
        "harnTest purpose \"t\"\nharnTest invariant \"i\"\n"
        + "".join(_harness_test_op(name, lit) for name, lit in ops_src),
        encoding="utf-8")
    report = semanticscript.run_tests(semanticscript.load_test_project(str(proj)))
    return {t["name"]: t for t in report["tests"]}


def test_test1_runner_distinguishes_pass_fail_and_cant_run(tmp_path):
    """TEST-1/AQ-4 (R-16): a passing `tag test` harness op must grade `pass`, a
    real assertion failure must grade `fail`, and an op that cannot compile/run in
    isolation must grade `error` (with the reason) — NOT `fail`. Previously every
    op that exited 2 because it couldn't be isolated was mis-graded as a failed
    assertion, so passing tests showed `exitCode 2 / fail`."""
    # a passing op and a genuinely-failing op (valid source) grade independently.
    good = _run_harness_project(tmp_path / "ok", [("tPass", "true"), ("tFail", "false")])
    assert good["tPass"]["status"] == "pass" and good["tPass"]["exitCode"] == 0
    # a real assertion failure: test.summary returns failure count 1 -> exit 1.
    assert good["tFail"]["status"] == "fail" and good["tFail"]["exitCode"] == 1
    # an op that cannot compile/run in isolation (invalid Bool literal -> SS parse
    # error, exit 2) grades `error` (with the reason surfaced), NOT `fail` — the
    # core R-16 mis-grade. Isolated in its own project so its bad source can't
    # poison the others' shared formatted run source.
    bad = _run_harness_project(tmp_path / "err", [("tErr", "yes")])
    assert bad["tErr"]["status"] == "error", bad["tErr"]
    assert "semanticscript:" in (bad["tErr"].get("error") or "")


# --- AQ-7: every trusted/validated type has a reachable constructor ---

# Trusted types constructed by a source-level construct (a trust-typed literal /
# island) rather than an intrinsic output. SqlText is built by a `storage type
# SqlText` literal (and sql islands); record here so the gate stays honest.
_SOURCE_CONSTRUCTED_TRUSTED = {"SqlText"}


def test_aq7_every_trusted_type_has_a_reachable_constructor():
    trusted, constructors = {}, set()
    for sp in glob.glob(os.path.join(ROOT, "semanticscript", "sigs", "standard.*.semsig")):
        try:
            prog = semanticscript.load_semsig(open(sp, encoding="utf-8").read())
        except Exception:
            continue
        for n, e in prog.entities.items():
            if e.kind == "alias":
                tt = e.fact("typeTrust")
                if tt and tt.payload and tt.payload[0] in ("validated", "trusted", "secret"):
                    trusted[e.name] = tt.payload[0]
        for _, ent in semanticscript.semsig_targets(prog).items():
            o = ent.fact("out")
            if o and o.payload:
                constructors.add(o.payload[-1])
    assert trusted, "expected some trusted/validated types in the shipped signatures"
    unreachable = [t for t in trusted
                   if t not in constructors and t not in _SOURCE_CONSTRUCTED_TRUSTED]
    assert not unreachable, (
        f"trusted types with no reachable constructor (unusable): {unreachable}")


# --- ERG-1: a reserved-word entity name names a usable alternative ---

def test_erg1_ss0003_suggests_a_non_reserved_name():
    f = semanticscript._reserved_word_suggestion
    sug = f("type")
    assert sug and sug not in semanticscript.RESERVED_WORDS
    src = ("P is project\nP module m\nP target console\nP entry main\n"
           "m is module\nm path x\nm exports main\n"
           "type is operation\ntype out Int32\ntype return z\n"
           "z is storage\nz scope module\nz type Int32\nz value 0\n")
    with pytest.raises(semanticscript.EavError) as exc:
        semanticscript.parse(src)
    assert exc.value.code == "SS0003"
    assert "try" in str(exc.value) and sug in str(exc.value)


# --- AQ-11: first-class whole-program semantic summary ---

def test_aq11_program_summary_aggregates_the_whole_program():
    src = ("P is project\nP module m\nP target console\nP entry main\n"
           "m is module\nm path x\nm exports main\nm purpose \"p\"\nm invariant \"i\"\n"
           "ExitCode is alias\nExitCode for Int32\n"
           "stdoutWriter is capability\nstdoutWriter grants write console.stdout\n"
           "ConsoleWriteError is error\n"
           "main is operation\nmain out ExitCode\nmain effect write console.stdout\n"
           "main uses stdoutWriter\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
           "main let h immutable String \"hi\"\nmain let z immutable ExitCode 0\n"
           "main do w\nmain return z\n"
           "w is call\nw in main\nw invokes console.writeLine\nw arg text String h\n"
           "w catch e ConsoleWriteError\n")
    s = semanticscript._program_summary(semanticscript.parse(src))
    assert s["target"] == "console"
    assert s["entityCounts"].get("operation") == 1 and s["entityCounts"].get("capability") == 1
    assert any(o["name"] == "main" and "write console.stdout" in o["effects"]
               and "stdoutWriter" in o["uses"] and "console.writeLine" in o["invokes"]
               for o in s["operations"])
    assert "write console.stdout" in s["effects"]
    assert {"from": "main", "to": "console.writeLine"} in s["callGraph"]


def test_aq11_summary_command_is_registered_and_runs():
    proc = subprocess.run([sys.executable, SC, "summary",
                           os.path.join(ROOT, "examples", "hello_world.sem"), "--json"],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    d = json.loads(proc.stdout)
    assert d.get("surface") == "sem.summary.v1" and d.get("target") == "console"


def test_w2g3_explain_program_reports_touches_authority_and_failures(tmp_path):
    p = tmp_path / "prog.sem"
    p.write_text(
        "P is project\nP module m\nP target console\nP entry main\n"
        "m is module\nm path x\nm exports main\nm purpose \"p\"\nm invariant \"i\"\n"
        "ExitCode is alias\nExitCode for Int32\n"
        "stdoutWriter is capability\nstdoutWriter grants write console.stdout\n"
        "ConsoleWriteError is error\n"
        "main is operation\nmain out ExitCode\nmain effect write console.stdout\n"
        "main uses stdoutWriter\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
        "main let h immutable String \"hi\"\nmain let z immutable ExitCode 0\n"
        "main do w\nmain return z\n"
        "w is call\nw in main\nw invokes console.writeLine\nw arg text String h\n"
        "w catch e ConsoleWriteError\n",
        encoding="utf-8")
    proc = subprocess.run([sys.executable, SC, "explain-program", str(p), "--json"],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["surface"] == "sem.programExplain.v1"
    assert payload["touches"]["target"] == "console"
    assert "console.writeLine" in payload["touches"]["runtimeTargets"]
    assert payload["authority"]["declaredEffects"] == ["write console.stdout"]
    assert payload["authority"]["capabilityGrants"][0]["name"] == "stdoutWriter"
    fallible = [m for m in payload["failureModes"] if m["kind"] == "fallible-calls"]
    assert fallible and fallible[0]["calls"][0]["error"] == "ConsoleWriteError"


# --- ERG-2: analysis commands accept a project directory, not only a file ---

def test_erg2_analysis_commands_accept_a_project_directory(tmp_path):
    proj = tmp_path / "proj"
    subprocess.run([sys.executable, SC, "new", str(proj)],
                   capture_output=True, text=True)
    # the program-analysis family must all accept a project dir uniformly
    # (inventory was the file-only outlier, now fixed).
    for cmd in ("inventory", "summary", "graph", "symbols", "context", "size"):
        r = subprocess.run([sys.executable, SC, cmd, str(proj)],
                           capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, f"`{cmd} <project-dir>` failed: {r.stderr[-200:]}"


# --- AQ-3: refactoring (rename) operates at project scope ---

# --- AQ-5: the style tier is machine-applyable (fmt-as-fix) ---

def test_aq5_style_tier_repair_is_a_formatsource_edit():
    # an SS1340 (ifValue/ifOut sugar, T4 style) diagnostic yields a whole-source
    # formatSource edit — `fix`/`patch` now cover the style tier, not just blockers.
    prog = semanticscript.parse(
        open(os.path.join(ROOT, "examples", "ifvalue.sem"), encoding="utf-8").read())
    diags = [d for d in semanticscript.lint(prog) if d.code == "SS1340"]
    assert diags, "the ifvalue example should raise the SS1340 style diagnostic"
    edits = semanticscript._fix_edits_for(diags[0], prog)
    assert edits and edits[0]["op"] == "formatSource" and edits[0]["code"] == "SS1340"


def test_aq5_patch_applies_the_style_fix_end_to_end(tmp_path):
    import json
    p = tmp_path / "ifvalue.sem"
    p.write_text(open(os.path.join(ROOT, "examples", "ifvalue.sem"),
                      encoding="utf-8").read(), encoding="utf-8")
    assert "branch ifValue" in p.read_text(encoding="utf-8")
    # fix --include-warnings surfaces the style tier and emits an applyable plan.
    fix = subprocess.run(
        [sys.executable, SC, "fix", str(p), "--include-warnings", "--json"],
        capture_output=True, text=True, encoding="utf-8")
    plan = json.loads(fix.stdout)
    assert plan.get("planUsable") is True
    assert any(e.get("op") == "formatSource" for e in plan.get("edits", []))
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(fix.stdout, encoding="utf-8")
    # patch realizes the fix: the sugar is canonicalized to compare + `branch if`.
    patch = subprocess.run([sys.executable, SC, "patch", str(plan_path), "--apply"],
                           capture_output=True, text=True, encoding="utf-8")
    assert patch.returncode == 0, patch.stdout + patch.stderr
    out = p.read_text(encoding="utf-8")
    assert "branch ifValue" not in out and "branch if " in out
    # and the canonicalized source still parses (never persisted broken).
    semanticscript.parse(out)


def test_aq3_rename_rewrites_entity_and_refs_across_the_project(tmp_path):
    proj = tmp_path / "p"
    (proj / "src").mkdir(parents=True)
    (proj / "build.sem").write_text(
        "Proj is project\nProj module appMod\nProj target console\nProj entry main\n",
        encoding="utf-8")
    (proj / "src" / "main.sem").write_text(
        "appMod is module\nappMod path src.main\nappMod exports main\n"
        "appMod purpose \"p\"\nappMod invariant \"i\"\n"
        "ExitCode is alias\nExitCode for Int32\n"
        "helperValue is storage\nhelperValue scope module\nhelperValue type Int32\n"
        "helperValue value 42\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\n"
        "main invariant \"i\"\nmain return helperValue\n", encoding="utf-8")
    r = subprocess.run([sys.executable, SC, "rename", str(proj),
                        "helperValue", "answerValue", "--write"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    txt = (proj / "src" / "main.sem").read_text(encoding="utf-8")
    assert "helperValue" not in txt
    assert "answerValue is storage" in txt and "main return answerValue" in txt


def test_w23_rename_rewrites_imported_capability_and_reverifies_project(tmp_path):
    proj = tmp_path / "p"
    (proj / "src").mkdir(parents=True)
    (proj / "build.sem").write_text(
        "App is project\nApp module mainModule\nApp module authModule\n"
        "App target console\nApp entry main\n",
        encoding="utf-8")
    (proj / "src" / "main.sem").write_text(
        "mainModule is module\nmainModule path app.main\n"
        "mainModule imports auth app.auth\nmainModule exports main\n"
        "mainModule purpose \"p\"\nmainModule invariant \"i\"\n"
        "ExitCode is alias\nExitCode for Int32\nConsoleWriteError is error\n"
        "main is operation\nmain out ExitCode\nmain effect write console.stdout\n"
        "main uses auth.stdoutWriter\nmain async no\n"
        "main purpose \"p\"\nmain invariant \"i\"\n"
        "main let text immutable String \"hi\"\n"
        "main let ok immutable ExitCode 0\nmain do w\nmain return ok\n"
        "w is call\nw in main\nw invokes console.writeLine\n"
        "w arg text String text\nw catch e ConsoleWriteError\n",
        encoding="utf-8")
    (proj / "src" / "auth.sem").write_text(
        "authModule is module\nauthModule path app.auth\n"
        "authModule exports stdoutWriter\n"
        "authModule purpose \"p\"\nauthModule invariant \"i\"\n"
        "stdoutWriter is capability\nstdoutWriter grants write console.stdout\n"
        "stdoutWriter purpose \"p\"\n",
        encoding="utf-8")

    r = subprocess.run([sys.executable, SC, "rename", str(proj),
                        "stdoutWriter", "consoleWriter", "--write"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    main_txt = (proj / "src" / "main.sem").read_text(encoding="utf-8")
    auth_txt = (proj / "src" / "auth.sem").read_text(encoding="utf-8")
    assert "main uses auth.consoleWriter" in main_txt
    assert "authModule exports consoleWriter" in auth_txt
    assert "consoleWriter is capability" in auth_txt
    assert "stdoutWriter" not in main_txt + auth_txt

    verify = subprocess.run([sys.executable, SC, "verify", str(proj), "--json"],
                            capture_output=True, text=True, encoding="utf-8")
    assert verify.returncode == 0, verify.stdout + verify.stderr
    assert json.loads(verify.stdout)["status"] == "ok"
