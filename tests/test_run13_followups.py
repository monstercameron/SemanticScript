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
