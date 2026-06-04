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
